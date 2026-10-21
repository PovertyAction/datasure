"""Tests for datasure.checks.enumerator.settings_ui."""

import importlib
import json
import sys
from unittest.mock import MagicMock, patch

import pytest

from datasure.checks.enumerator.models import EnumeratorSettings
from datasure.checks.enumerator.settings_ui import (
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
        "settings.json",
        sample_enumerator_data,
        config,
        categorical_cols,
        datetime_cols,
    )
    assert result is not None


def test_render_consent_outcome_settings_has_no_apply_button(
    enum_bc, sample_enumerator_data
):
    """Consent and outcome settings apply as saved; there is no Apply button."""
    enum_bc.st.selectbox.return_value = "survey_id"
    categorical_cols = list(sample_enumerator_data.columns)
    enum_bc._render_consent_outcome_settings(
        sample_enumerator_data, categorical_cols, "settings.json"
    )
    enum_bc.st.button.assert_not_called()


def test_unsaved_consent_column_is_not_preselected(enum_bc, sample_enumerator_data):
    """With nothing saved, no column shows as chosen, so the UI matches the
    saved settings the report uses.
    """
    enum_bc.st.selectbox.return_value = None
    categorical_cols = list(sample_enumerator_data.columns)
    settings = enum_bc._render_consent_outcome_settings(
        sample_enumerator_data, categorical_cols, "settings.json"
    )
    assert settings.consent is None
    assert settings.outcome is None
    for call in enum_bc.st.selectbox.call_args_list:
        assert call.kwargs["index"] is None
    for call in enum_bc.st.multiselect.call_args_list:
        assert call.kwargs["options"] == []


@pytest.mark.parametrize("field_key", ["consent", "outcome"])
def test_changing_column_saves_the_values_shown_for_it(
    enum_bc, sample_enumerator_data, tmp_path, field_key
):
    """Old values are not left saved for a new column the report would read."""
    from datasure.utils import settings_utils

    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps({enum_bc.TAB_NAME: {field_key: "team", f"{field_key}_vals": ["T1"]}})
    )
    enum_bc.load_check_settings = settings_utils.load_check_settings
    enum_bc.save_check_settings = settings_utils.save_check_settings
    enum_bc.trigger_save = settings_utils.trigger_save
    categorical_cols = list(sample_enumerator_data.columns)

    with patch.object(settings_utils.st, "session_state", {}):
        enum_bc.st.selectbox.return_value = "team"
        enum_bc._render_consent_outcome_settings(
            sample_enumerator_data, categorical_cols, str(settings_file)
        )
        column_select = next(
            c
            for c in enum_bc.st.selectbox.call_args_list
            if c.kwargs["key"] == f"{field_key}_enumerator"
        )

        # The user picks a new column; the values picker shows nothing chosen.
        column_select.kwargs["on_change"](**column_select.kwargs["kwargs"])
        enum_bc.st.selectbox.return_value = "formversion"
        enum_bc.st.multiselect.return_value = []
        enum_bc._render_consent_outcome_settings(
            sample_enumerator_data, categorical_cols, str(settings_file)
        )

    saved = json.loads(settings_file.read_text())[enum_bc.TAB_NAME]
    assert saved[field_key] == "formversion"
    assert saved[f"{field_key}_vals"] == []
