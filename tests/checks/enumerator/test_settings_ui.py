"""Tests for datasure.checks.enumerator.settings_ui."""

import importlib
import sys
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks.enumerator.models import ConsentOutcomeSettings, EnumeratorSettings
from datasure.checks.enumerator.settings_ui import (
    _create_enum_data_on_settings,
    _trigger_success_message,
    load_default_enumerator_settings,
)
from tests.checks.enumerator.conftest import make_mock_st

# ============================================
# ENUM_BC FIXTURE (reload settings_ui with mocked streamlit)
# ============================================


@pytest.fixture
def enum_bc():
    """Reload settings_ui module with mocked Streamlit to strip fragment decorators."""
    mock_st = make_mock_st()
    original_st = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock_st
    import datasure.checks.enumerator.settings_ui as settings_ui_module

    try:
        importlib.reload(settings_ui_module)
        settings_ui_module.load_check_settings = MagicMock(return_value={})
        settings_ui_module.save_check_settings = MagicMock()
        settings_ui_module.trigger_save = MagicMock()
        settings_ui_module.duckdb_save_table = MagicMock()
        with patch(
            "datasure.utils.onboarding_utils.is_demo_project", return_value=False
        ):
            yield settings_ui_module
    finally:
        if original_st is not None:
            sys.modules["streamlit"] = original_st
        else:
            sys.modules.pop("streamlit", None)
        importlib.reload(settings_ui_module)


# ============================================
# SETTINGS TESTS
# ============================================


def test_load_default_enumerator_settings_valid(enumerator_settings_file):
    """Test loading enumerator settings from valid file."""
    config = EnumeratorSettings(
        survey_key="default_key",
        survey_id="default_id",
    )
    with patch("streamlit.cache_data", lambda ttl: lambda f: f):
        result = load_default_enumerator_settings(enumerator_settings_file, config)

    # Saved settings should override defaults
    assert result.survey_key == "survey_id"
    assert result.enumerator == "enumerator"


def test_load_default_enumerator_settings_missing_file():
    """Test loading enumerator settings when file doesn't exist."""
    config = EnumeratorSettings(
        survey_key="default_key",
        survey_id="default_id",
        enumerator="default_enum",
    )
    with patch("streamlit.cache_data", lambda ttl: lambda f: f):
        result = load_default_enumerator_settings("nonexistent.json", config)

    # Should return default config when file doesn't exist
    assert result.survey_key == "default_key"
    assert result.enumerator == "default_enum"


@patch("datasure.checks.enumerator.settings_ui.st")
def test_trigger_success_message(mock_st):
    """Test _trigger_success_message function."""
    mock_st.session_state = {}

    _trigger_success_message("test_button")
    assert mock_st.session_state["test_button"] is True


def test_create_enum_data_on_settings_with_consent_and_outcome():
    """Test _create_enum_data_on_settings with consent and outcome values."""
    data = pl.DataFrame(
        {
            "survey_id": ["S001", "S002", "S003"],
            "consent": ["yes", "no", "yes"],
            "outcome": ["completed", "incomplete", "completed"],
        }
    )

    config = ConsentOutcomeSettings(
        consent="consent",
        consent_vals=["yes"],
        outcome="outcome",
        outcome_vals=["completed"],
    )

    with patch("datasure.checks.enumerator.settings_ui.duckdb_save_table") as mock_save:
        _create_enum_data_on_settings("test_project", data, config)

        # Verify function was called
        mock_save.assert_called_once()
        saved_data = mock_save.call_args[0][1]

        # Check that consent and outcome columns were created
        assert "consent_granted_agg_col" in saved_data.columns
        assert "completed_survey_agg_col" in saved_data.columns
        assert saved_data["consent_granted_agg_col"].to_list() == [1, 0, 1]
        assert saved_data["completed_survey_agg_col"].to_list() == [1, 0, 1]


def test_create_enum_data_on_settings_without_consent():
    """Test _create_enum_data_on_settings without consent values."""
    data = pl.DataFrame(
        {
            "survey_id": ["S001", "S002"],
            "outcome": ["completed", "completed"],
        }
    )

    config = ConsentOutcomeSettings(
        consent=None,
        consent_vals=None,
        outcome="outcome",
        outcome_vals=["completed"],
    )

    with patch("datasure.checks.enumerator.settings_ui.duckdb_save_table") as mock_save:
        _create_enum_data_on_settings("test_project", data, config)

        saved_data = mock_save.call_args[0][1]
        # Consent should default to 1
        assert saved_data["consent_granted_agg_col"].to_list() == [1, 1]


def test_create_enum_data_on_settings_without_outcome():
    """Test _create_enum_data_on_settings without outcome values."""
    data = pl.DataFrame(
        {
            "survey_id": ["S001", "S002"],
            "consent": ["yes", "yes"],
        }
    )

    config = ConsentOutcomeSettings(
        consent="consent",
        consent_vals=["yes"],
        outcome=None,
        outcome_vals=None,
    )

    with patch("datasure.checks.enumerator.settings_ui.duckdb_save_table") as mock_save:
        _create_enum_data_on_settings("test_project", data, config)

        saved_data = mock_save.call_args[0][1]
        # Outcome should default to 1
        assert saved_data["completed_survey_agg_col"].to_list() == [1, 1]


# ============================================
# INTEGRATION TESTS
# ============================================


@patch("datasure.checks.enumerator.settings_ui.duckdb_save_table")
def test_consent_outcome_integration(mock_save, sample_enumerator_data):
    """Test consent and outcome settings integration."""
    # Create consent and outcome settings
    config = ConsentOutcomeSettings(
        consent="consent",
        consent_vals=["yes"],
        outcome="outcome",
        outcome_vals=["completed"],
    )

    # Add consent and outcome columns
    data = sample_enumerator_data.with_columns(
        [
            pl.lit("yes").alias("consent"),
            pl.lit("completed").alias("outcome"),
        ]
    )

    # Create enum data with settings
    _create_enum_data_on_settings("test_project", data, config)

    # Verify the data was saved
    assert mock_save.called


# ============================================
# ENUM_BC UI FRAGMENT TESTS
# ============================================


def test_enumerator_report_settings_basic(enum_bc, sample_enumerator_data):
    """enumerator_report_settings returns EnumeratorSettings from UI."""
    enum_bc.st.selectbox.return_value = "survey_id"
    categorical_cols = list(sample_enumerator_data.columns)
    datetime_cols = ["submission_date"]
    config = EnumeratorSettings(survey_id="survey_id")
    result = enum_bc.enumerator_report_settings(
        "proj_id",
        "settings.json",
        sample_enumerator_data,
        config,
        categorical_cols,
        datetime_cols,
    )
    assert result is not None


def test_render_consent_outcome_settings(enum_bc, sample_enumerator_data):
    """_render_consent_outcome_settings renders consent/outcome selectors."""
    enum_bc.st.selectbox.return_value = "survey_id"
    categorical_cols = list(sample_enumerator_data.columns)
    enum_bc._render_consent_outcome_settings(
        "proj_id", sample_enumerator_data, categorical_cols, "settings.json"
    )
    enum_bc.st.button.assert_called()


def test_render_consent_outcome_settings_button_click(enum_bc, sample_enumerator_data):
    """_render_consent_outcome_settings calls create when button clicked."""
    enum_bc.st.selectbox.return_value = "survey_id"
    enum_bc.st.button.return_value = True
    categorical_cols = list(sample_enumerator_data.columns)
    enum_bc._render_consent_outcome_settings(
        "proj_id", sample_enumerator_data, categorical_cols, "settings.json"
    )
    enum_bc.duckdb_save_table.assert_called()


def test_enumerator_report_settings_success_flag(enum_bc, sample_enumerator_data):
    """enumerator_report_settings shows success message when consent flag set."""
    enum_bc.st.selectbox.return_value = "survey_id"
    enum_bc.st.session_state["st_apply_consent_outcome_enumerator"] = True
    categorical_cols = list(sample_enumerator_data.columns)
    config = EnumeratorSettings(survey_id="survey_id")
    enum_bc.enumerator_report_settings(
        "proj_id",
        "settings.json",
        sample_enumerator_data,
        config,
        categorical_cols,
        ["submission_date"],
    )
    enum_bc.st.success.assert_called()
