"""Tests for enumerator module.

This module tests the refactored enumerator performance analysis system using
Polars DataFrames and Pydantic models for validation and configuration.
"""

import importlib
import json
import sys
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from polars.exceptions import ColumnNotFoundError
from pydantic import ValidationError

from datasure.checks.enumerator import (
    ALLOWED_STATISTICS,
    ALLOWED_STATISTICS_OVERTIME,
    ALLOWED_TIME_PERIODS,
    TAB_NAME,
    WEEKDAY_NAMES,
    WEEKDAY_OFFSET_MAP,
    WEEKDAY_OFFSET_TO_NUMERIC,
    ConsentOutcomeSettings,
    EnumeratorOverviewMetrics,
    EnumeratorSettings,
    ProductivitySettings,
    StatisticsOvertimeSettings,
    StatisticsSettings,
    _create_enum_data_on_settings,
    _get_numeric_columns,
    _load_statistics_overtime_settings,
    _load_statistics_settings,
    _render_column_selector,
    _render_column_selector_single,
    _render_enumerator_overview_metrics,
    _render_enumerator_productivity,
    _render_enumerator_statistics,
    _render_enumerator_statistics_overtime,
    _render_period_selector_overtime,
    _render_statistic_selector,
    _render_statistics_selector,
    _render_time_period_selector,
    _render_weekday_selector,
    _render_weekday_selector_overtime,
    _trigger_success_message,
    compute_enumerator_missing_table,
    compute_enumerator_overview,
    compute_enumerator_productivity,
    compute_enumerator_statistics,
    compute_enumerator_statistics_overtime,
    compute_enumerator_summary,
    load_default_enumerator_settings,
)
from datasure.models.schemas import ColumnByType

# ============================================
# MOCK STREAMLIT HELPERS AND UI FIXTURES
# ============================================


def _make_mock_st():
    """Create a mock Streamlit module for testing UI render functions."""

    def make_col():
        col = MagicMock()
        col.number_input.return_value = 0.0
        col.selectbox.return_value = None
        col.text_input.return_value = ""
        col.multiselect.return_value = []
        return col

    def _col_factory(n_or_spec, **kwargs):
        if isinstance(n_or_spec, int):
            n = n_or_spec
        elif isinstance(n_or_spec, list | tuple):
            n = len(n_or_spec)
        else:
            n = 2
        return tuple(make_col() for _ in range(n))

    mock_st = MagicMock()
    mock_st.fragment = lambda func: func
    mock_st.dialog = lambda *args, **kwargs: lambda func: func
    mock_st.columns.side_effect = _col_factory
    mock_st.selectbox.return_value = None
    mock_st.multiselect.return_value = []
    mock_st.pills.return_value = None
    mock_st.button.return_value = False
    mock_st.toggle.return_value = False
    mock_st.number_input.return_value = 0
    mock_st.text_input.return_value = ""
    mock_st.session_state = {}
    return mock_st


@pytest.fixture
def patched_enum():
    """Patch st in enumerator module for non-fragment UI function tests."""
    mock_st = _make_mock_st()
    with (
        patch("datasure.checks.enumerator.st", mock_st),
        patch("datasure.checks.enumerator.save_check_settings"),
        patch("datasure.checks.enumerator.load_check_settings", return_value={}),
        patch("datasure.checks.enumerator.trigger_save"),
        patch(
            "datasure.checks.enumerator.duckdb_get_table",
            return_value=pl.DataFrame(),
        ),
        patch("datasure.checks.enumerator.duckdb_save_table"),
        patch("datasure.checks.enumerator.demo_callout"),
        patch("datasure.utils.onboarding_utils.is_demo_project", return_value=False),
    ):
        yield mock_st


@pytest.fixture
def enum_bc():
    """Reload enumerator module with mocked Streamlit to strip fragment decorators."""
    mock_st = _make_mock_st()
    original_st = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock_st
    import datasure.checks.enumerator as enum_module

    try:
        importlib.reload(enum_module)
        enum_module.load_check_settings = MagicMock(return_value={})
        enum_module.save_check_settings = MagicMock()
        enum_module.trigger_save = MagicMock()
        enum_module.duckdb_get_table = MagicMock(return_value=pl.DataFrame())
        enum_module.duckdb_save_table = MagicMock()
        enum_module.demo_callout = MagicMock()
        enum_module.load_missing_codes_from_db = MagicMock(return_value=pl.DataFrame())
        with patch(
            "datasure.utils.onboarding_utils.is_demo_project", return_value=False
        ):
            yield enum_module
    finally:
        if original_st is not None:
            sys.modules["streamlit"] = original_st
        else:
            sys.modules.pop("streamlit", None)
        importlib.reload(enum_module)


# ============================================
# FIXTURES FOR ENUMERATOR-SPECIFIC DATA
# ============================================


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests.
    """
    pass


@pytest.fixture
def sample_enumerator_data():
    """Create sample enumerator data as Polars DataFrame."""
    today = date.today()
    return pl.DataFrame(
        {
            "survey_id": ["S001", "S002", "S003", "S004", "S005", "S006"],
            "submission_date": [
                today - timedelta(days=1),
                today - timedelta(days=2),
                today - timedelta(days=3),
                today - timedelta(days=1),
                today - timedelta(days=8),
                today,
            ],
            "enumerator": ["E1", "E1", "E2", "E2", "E3", "E1"],
            "team": ["T1", "T1", "T1", "T2", "T2", "T1"],
            "duration": [3600, 4200, 3800, 4000, 3900, 3700],
            "formversion": ["v1", "v1", "v2", "v2", "v1", "v2"],
            "age": [25, 30, 35, 28, 32, 27],
            "income": [50000, 60000, 55000, 52000, 58000, 51000],
            "consent_granted_agg_col": [1, 1, 1, 0, 1, 1],
            "completed_survey_agg_col": [1, 1, 1, 1, 0, 1],
        }
    )


@pytest.fixture
def sample_enumerator_settings():
    """Create sample EnumeratorSettings for testing."""
    return EnumeratorSettings(
        survey_key="survey_id",
        survey_id="survey_id",
        survey_date="submission_date",
        enumerator="enumerator",
        formversion="formversion",
        duration="duration",
        duration_unit="seconds",
        team="team",
    )


@pytest.fixture
def sample_missing_codes_config():
    """Create sample missing codes configuration."""
    return pl.DataFrame(
        {
            "label": ["Refused", "Don't know"],
            "codes": ["-99", "-88"],
        }
    )


@pytest.fixture
def enumerator_settings_file(tmp_path):
    """Create a temporary enumerator settings file."""
    settings = {
        "enumerators": {
            "survey_key": "survey_id",
            "survey_id": "survey_id",
            "survey_date": "submission_date",
            "enumerator": "enumerator",
            "team": "team",
        }
    }
    file_path = tmp_path / "enumerator_settings.json"
    file_path.write_text(json.dumps(settings))
    return str(file_path)


# ============================================
# CONSTANTS TESTS
# ============================================


def test_constants():
    """Test that all constants are defined correctly."""
    assert TAB_NAME == "enumerators"
    assert len(ALLOWED_STATISTICS) == 8
    assert "count" in ALLOWED_STATISTICS
    assert "mean" in ALLOWED_STATISTICS
    assert "median" in ALLOWED_STATISTICS
    assert len(ALLOWED_STATISTICS_OVERTIME) == 9
    assert "missing" in ALLOWED_STATISTICS_OVERTIME
    assert len(ALLOWED_TIME_PERIODS) == 3
    assert "Daily" in ALLOWED_TIME_PERIODS
    assert "Weekly" in ALLOWED_TIME_PERIODS
    assert "Monthly" in ALLOWED_TIME_PERIODS


def test_weekday_constants():
    """Test weekday mapping constants."""
    assert len(WEEKDAY_NAMES) == 7
    assert "Monday" in WEEKDAY_NAMES
    assert len(WEEKDAY_OFFSET_MAP) == 7
    assert WEEKDAY_OFFSET_MAP["Monday"] == "SUN"
    assert len(WEEKDAY_OFFSET_TO_NUMERIC) == 7
    assert WEEKDAY_OFFSET_TO_NUMERIC["SUN"] == 0


# ============================================
# PYDANTIC MODELS TESTS
# ============================================


def test_enumerator_settings_model_valid():
    """Test EnumeratorSettings model with valid data."""
    settings = EnumeratorSettings(
        survey_key="survey_id",
        survey_id="survey_id",
        survey_date="submission_date",
        enumerator="enumerator",
        formversion="formversion",
        duration="duration",
        duration_unit="seconds",
        team="team",
    )
    assert settings.survey_key == "survey_id"
    assert settings.survey_id == "survey_id"
    assert settings.enumerator == "enumerator"
    assert settings.team == "team"


def test_enumerator_settings_model_required_survey_id():
    """Test EnumeratorSettings model requires survey_id."""
    with pytest.raises(ValidationError):
        EnumeratorSettings(survey_id="")


def test_enumerator_settings_model_optional_fields():
    """Test EnumeratorSettings model with optional fields."""
    settings = EnumeratorSettings(
        survey_key="survey_id",
        survey_id="survey_id",
    )
    assert settings.survey_date is None
    assert settings.enumerator is None
    assert settings.team is None


def test_consent_outcome_settings_model():
    """Test ConsentOutcomeSettings model."""
    settings = ConsentOutcomeSettings(
        consent="consent_col",
        consent_vals=["yes", "agreed"],
        outcome="outcome_col",
        outcome_vals=["completed"],
    )
    assert settings.consent == "consent_col"
    assert settings.consent_vals == ["yes", "agreed"]
    assert settings.outcome == "outcome_col"
    assert settings.outcome_vals == ["completed"]


def test_consent_outcome_settings_defaults():
    """Test ConsentOutcomeSettings model with defaults."""
    settings = ConsentOutcomeSettings()
    assert settings.consent is None
    assert settings.consent_vals is None
    assert settings.outcome is None
    assert settings.outcome_vals is None


def test_productivity_settings_model():
    """Test ProductivitySettings model."""
    settings = ProductivitySettings(
        view_option="Weekly",
        weekstartday="Monday",
    )
    assert settings.view_option == "Weekly"
    assert settings.weekstartday == "Monday"


def test_productivity_settings_validation_view_option():
    """Test ProductivitySettings validation for view_option."""
    with pytest.raises(ValidationError, match="view_option must be one of"):
        ProductivitySettings(view_option="Invalid")


def test_productivity_settings_validation_weekstartday():
    """Test ProductivitySettings validation for weekstartday."""
    with pytest.raises(ValidationError, match="weekstartday must be one of"):
        ProductivitySettings(weekstartday="InvalidDay")


def test_productivity_settings_defaults():
    """Test ProductivitySettings model with defaults."""
    settings = ProductivitySettings()
    assert settings.view_option == "Daily"
    assert settings.weekstartday == "Monday"


def test_statistics_settings_model():
    """Test StatisticsSettings model."""
    settings = StatisticsSettings(
        statscols=["age", "income"],
        stats=["count", "mean", "median"],
    )
    assert settings.statscols == ["age", "income"]
    assert settings.stats == ["count", "mean", "median"]


def test_statistics_settings_validation():
    """Test StatisticsSettings validation for stats."""
    with pytest.raises(ValidationError, match="Invalid statistic"):
        StatisticsSettings(stats=["invalid_stat"])


def test_statistics_settings_defaults():
    """Test StatisticsSettings model with defaults."""
    settings = StatisticsSettings()
    assert settings.statscols is None
    assert settings.stats == ["count", "mean"]


def test_statistics_overtime_settings_model():
    """Test StatisticsOvertimeSettings model."""
    settings = StatisticsOvertimeSettings(
        period_overtime="Weekly",
        weekstartday="Tuesday",
        stat="median",
        statscol="age",
    )
    assert settings.period_overtime == "Weekly"
    assert settings.weekstartday == "Tuesday"
    assert settings.stat == "median"
    assert settings.statscol == "age"


def test_statistics_overtime_settings_validation_period():
    """Test StatisticsOvertimeSettings validation for period."""
    with pytest.raises(ValidationError, match="Invalid period"):
        StatisticsOvertimeSettings(period_overtime="InvalidPeriod")


def test_statistics_overtime_settings_validation_weekstartday():
    """Test StatisticsOvertimeSettings validation for weekstartday."""
    with pytest.raises(ValidationError, match="Invalid weekstartday"):
        StatisticsOvertimeSettings(weekstartday="InvalidDay")


def test_statistics_overtime_settings_validation_stat():
    """Test StatisticsOvertimeSettings validation for stat."""
    with pytest.raises(ValidationError, match="Invalid statistic"):
        StatisticsOvertimeSettings(stat="invalid_stat")


def test_statistics_overtime_settings_defaults():
    """Test StatisticsOvertimeSettings model with defaults."""
    settings = StatisticsOvertimeSettings()
    assert settings.period_overtime == "Week"
    assert settings.weekstartday == "Monday"
    assert settings.stat == "count"
    assert settings.statscol is None


def test_enumerator_overview_metrics_model():
    """Test EnumeratorOverviewMetrics model."""
    metrics = EnumeratorOverviewMetrics(
        all_submissions=100,
        num_active_enumerators=5,
        num_enumerators=10,
        num_teams=3,
        min_submissions=5,
        max_submissions=25,
        avg_submissions=15,
        pct_active_enumerators="50%",
    )
    assert metrics.all_submissions == 100
    assert metrics.num_active_enumerators == 5
    assert metrics.num_enumerators == 10
    assert metrics.num_teams == 3
    assert metrics.min_submissions == 5
    assert metrics.max_submissions == 25
    assert metrics.avg_submissions == 15
    assert metrics.pct_active_enumerators == "50%"


def test_enumerator_overview_metrics_validation():
    """Test EnumeratorOverviewMetrics validation for non-negative integers."""
    with pytest.raises(ValidationError):
        EnumeratorOverviewMetrics(
            all_submissions=-1,
            num_active_enumerators=5,
            num_enumerators=10,
            num_teams=3,
            min_submissions=5,
            max_submissions=25,
            avg_submissions=15,
            pct_active_enumerators="50%",
        )


def test_enumerator_overview_metrics_num_teams_string():
    """Test EnumeratorOverviewMetrics allows string for num_teams."""
    metrics = EnumeratorOverviewMetrics(
        all_submissions=100,
        num_active_enumerators=5,
        num_enumerators=10,
        num_teams="n/a",
        min_submissions=5,
        max_submissions=25,
        avg_submissions=15,
        pct_active_enumerators="50%",
    )
    assert metrics.num_teams == "n/a"


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


@patch("datasure.checks.enumerator.st")
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

    with patch("datasure.checks.enumerator.duckdb_save_table") as mock_save:
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

    with patch("datasure.checks.enumerator.duckdb_save_table") as mock_save:
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

    with patch("datasure.checks.enumerator.duckdb_save_table") as mock_save:
        _create_enum_data_on_settings("test_project", data, config)

        saved_data = mock_save.call_args[0][1]
        # Outcome should default to 1
        assert saved_data["completed_survey_agg_col"].to_list() == [1, 1]


# ============================================
# COMPUTE_ENUMERATOR_OVERVIEW TESTS
# ============================================


def test_compute_enumerator_overview_basic(sample_enumerator_data):
    """Test basic enumerator overview computation."""
    result = compute_enumerator_overview(
        sample_enumerator_data, "submission_date", "enumerator", "team"
    )

    assert result.all_submissions == 6
    assert result.num_enumerators == 3
    assert result.num_teams == 2
    assert result.num_active_enumerators >= 0
    assert result.min_submissions > 0
    assert result.max_submissions > 0
    assert result.avg_submissions > 0


def test_compute_enumerator_overview_without_team(sample_enumerator_data):
    """Test enumerator overview without team column."""
    result = compute_enumerator_overview(
        sample_enumerator_data, "submission_date", "enumerator", None
    )

    assert result.all_submissions == 6
    assert result.num_enumerators == 3
    assert result.num_teams == "n/a"


def test_compute_enumerator_overview_empty_data():
    """Test enumerator overview with empty data."""
    empty_data = pl.DataFrame(
        schema={"submission_date": pl.Date, "enumerator": pl.Utf8}
    )

    with pytest.raises(ValueError, match="Input data is empty"):
        compute_enumerator_overview(empty_data, "submission_date", "enumerator", None)


def test_compute_enumerator_overview_active_enumerators():
    """Test active enumerators calculation."""
    today = date.today()
    data = pl.DataFrame(
        {
            "submission_date": [
                today - timedelta(days=1),
                today - timedelta(days=10),
                today,
            ],
            "enumerator": ["E1", "E2", "E1"],
            "team": ["T1", "T1", "T1"],
        }
    )

    result = compute_enumerator_overview(data, "submission_date", "enumerator", "team")

    # Only E1 should be active (has submissions in past 7 days)
    assert result.num_active_enumerators == 1
    assert result.num_enumerators == 2


# ============================================
# COMPUTE_ENUMERATOR_MISSING_TABLE TESTS
# ============================================


def test_compute_enumerator_missing_table_empty_config(sample_enumerator_data):
    """Test missing table with empty missing codes config."""
    empty_config = pl.DataFrame()

    result = compute_enumerator_missing_table(
        sample_enumerator_data, empty_config, ["enumerator"]
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns
    assert "% Null values" in result.columns


def test_compute_enumerator_missing_table_with_config(
    sample_enumerator_data, sample_missing_codes_config
):
    """Test missing table with missing codes config."""
    result = compute_enumerator_missing_table(
        sample_enumerator_data, sample_missing_codes_config, ["enumerator"]
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns


def test_compute_enumerator_missing_table_with_team(sample_enumerator_data):
    """Test missing table with team grouping."""
    empty_config = pl.DataFrame()

    result = compute_enumerator_missing_table(
        sample_enumerator_data, empty_config, ["enumerator", "team"]
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns
    assert "team" in result.columns


# ============================================
# COMPUTE_ENUMERATOR_SUMMARY TESTS
# ============================================


@patch("datasure.checks.enumerator.load_missing_codes_from_db")
def test_compute_enumerator_summary_basic(mock_load_missing, sample_enumerator_data):
    """Test basic enumerator summary computation."""
    mock_load_missing.return_value = pl.DataFrame()

    result = compute_enumerator_summary(
        "test_project",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        "formversion",
        "duration",
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns
    assert "team" in result.columns
    assert "# submissions" in result.columns
    assert "first submission" in result.columns
    assert "last submission" in result.columns


@patch("datasure.checks.enumerator.load_missing_codes_from_db")
def test_compute_enumerator_summary_without_team(
    mock_load_missing, sample_enumerator_data
):
    """Test enumerator summary without team."""
    mock_load_missing.return_value = pl.DataFrame()

    result = compute_enumerator_summary(
        "test_project",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "formversion",
        "duration",
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns
    assert "team" not in result.columns


@patch("datasure.checks.enumerator.load_missing_codes_from_db")
def test_compute_enumerator_summary_without_duration(
    mock_load_missing, sample_enumerator_data
):
    """Test enumerator summary without duration."""
    mock_load_missing.return_value = pl.DataFrame()

    result = compute_enumerator_summary(
        "test_project",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        "formversion",
        None,
    )

    assert not result.is_empty()
    assert "min duration" not in result.columns


@patch("datasure.checks.enumerator.load_missing_codes_from_db")
def test_compute_enumerator_summary_without_formversion(
    mock_load_missing, sample_enumerator_data
):
    """Test enumerator summary without formversion."""
    mock_load_missing.return_value = pl.DataFrame()

    result = compute_enumerator_summary(
        "test_project",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        None,
        "duration",
    )

    assert not result.is_empty()
    assert "# form versions" not in result.columns


@patch("datasure.checks.enumerator.load_missing_codes_from_db")
def test_compute_enumerator_summary_with_consent(
    mock_load_missing, sample_enumerator_data
):
    """Test enumerator summary with consent column."""
    mock_load_missing.return_value = pl.DataFrame()

    result = compute_enumerator_summary(
        "test_project",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        "formversion",
        "duration",
    )

    assert not result.is_empty()
    assert "% consent" in result.columns


@patch("datasure.checks.enumerator.load_missing_codes_from_db")
def test_compute_enumerator_summary_with_outcome(
    mock_load_missing, sample_enumerator_data
):
    """Test enumerator summary with outcome column."""
    mock_load_missing.return_value = pl.DataFrame()

    result = compute_enumerator_summary(
        "test_project",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        "formversion",
        "duration",
    )

    assert not result.is_empty()
    assert "% completed survey" in result.columns


# ============================================
# COMPUTE_ENUMERATOR_PRODUCTIVITY TESTS
# ============================================


def test_compute_enumerator_productivity_daily(sample_enumerator_data):
    """Test productivity computation with daily period."""
    result = compute_enumerator_productivity(
        sample_enumerator_data, "submission_date", ["enumerator"], "Daily", "SUN"
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns


def test_compute_enumerator_productivity_weekly(sample_enumerator_data):
    """Test productivity computation with weekly period."""
    result = compute_enumerator_productivity(
        sample_enumerator_data, "submission_date", ["enumerator"], "Weekly", "MON"
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns


def test_compute_enumerator_productivity_monthly(sample_enumerator_data):
    """Test productivity computation with monthly period."""
    result = compute_enumerator_productivity(
        sample_enumerator_data, "submission_date", ["enumerator"], "Monthly", "SUN"
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns


def test_compute_enumerator_productivity_legacy_period_names(sample_enumerator_data):
    """Test productivity with legacy period names."""
    # Test "Day" -> "Daily"
    result = compute_enumerator_productivity(
        sample_enumerator_data, "submission_date", ["enumerator"], "Day", "SUN"
    )
    assert not result.is_empty()

    # Test "Week" -> "Weekly"
    result = compute_enumerator_productivity(
        sample_enumerator_data, "submission_date", ["enumerator"], "Week", "MON"
    )
    assert not result.is_empty()

    # Test "Month" -> "Monthly"
    result = compute_enumerator_productivity(
        sample_enumerator_data, "submission_date", ["enumerator"], "Month", "SUN"
    )
    assert not result.is_empty()


def test_compute_enumerator_productivity_with_team(sample_enumerator_data):
    """Test productivity with team grouping."""
    result = compute_enumerator_productivity(
        sample_enumerator_data,
        "submission_date",
        ["enumerator", "team"],
        "Daily",
        "SUN",
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns
    assert "team" in result.columns


def test_compute_enumerator_productivity_different_weekstarts(sample_enumerator_data):
    """Test productivity with different week start days."""
    for weekstart in ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]:
        result = compute_enumerator_productivity(
            sample_enumerator_data,
            "submission_date",
            ["enumerator"],
            "Weekly",
            weekstart,
        )
        assert not result.is_empty()


# ============================================
# COMPUTE_ENUMERATOR_STATISTICS TESTS
# ============================================


def test_compute_enumerator_statistics_basic(sample_enumerator_data):
    """Test basic statistics computation."""
    with patch("streamlit.cache_data", lambda ttl: lambda f: f):
        result = compute_enumerator_statistics(
            sample_enumerator_data,
            ["enumerator"],
            ["age", "income"],
            ["count", "mean"],
        )

    assert not result.is_empty()
    assert "enumerator" in result.columns
    assert "age_count" in result.columns
    assert "age_mean" in result.columns
    assert "income_count" in result.columns
    assert "income_mean" in result.columns


def test_compute_enumerator_statistics_all_stats(sample_enumerator_data):
    """Test statistics with all stat types."""
    with patch("streamlit.cache_data", lambda ttl: lambda f: f):
        result = compute_enumerator_statistics(
            sample_enumerator_data,
            ["enumerator"],
            ["age"],
            [
                "count",
                "min",
                "mean",
                "median",
                "max",
                "std",
                "25th percentile",
                "75th percentile",
            ],
        )

    assert not result.is_empty()
    assert "age_count" in result.columns
    assert "age_min" in result.columns
    assert "age_mean" in result.columns
    assert "age_median" in result.columns
    assert "age_max" in result.columns
    assert "age_std" in result.columns
    assert "age_25th percentile" in result.columns
    assert "age_75th percentile" in result.columns


def test_compute_enumerator_statistics_with_team(sample_enumerator_data):
    """Test statistics with team grouping."""
    with patch("streamlit.cache_data", lambda ttl: lambda f: f):
        result = compute_enumerator_statistics(
            sample_enumerator_data,
            ["enumerator", "team"],
            ["age"],
            ["mean"],
        )

    assert not result.is_empty()
    assert "enumerator" in result.columns
    assert "team" in result.columns


def test_compute_enumerator_statistics_multiple_columns(sample_enumerator_data):
    """Test statistics with multiple columns."""
    with patch("streamlit.cache_data", lambda ttl: lambda f: f):
        result = compute_enumerator_statistics(
            sample_enumerator_data,
            ["enumerator"],
            ["age", "income", "duration"],
            ["mean", "median"],
        )

    assert not result.is_empty()
    assert len([col for col in result.columns if "_mean" in col]) == 3
    assert len([col for col in result.columns if "_median" in col]) == 3


# ============================================
# COMPUTE_ENUMERATOR_STATISTICS_OVERTIME TESTS
# ============================================


def test_compute_enumerator_statistics_overtime_daily(sample_enumerator_data):
    """Test statistics overtime with daily period."""
    result = compute_enumerator_statistics_overtime(
        sample_enumerator_data,
        "submission_date",
        ["enumerator"],
        "age",
        "mean",
        "Daily",
        "SUN",
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns


def test_compute_enumerator_statistics_overtime_weekly(sample_enumerator_data):
    """Test statistics overtime with weekly period."""
    result = compute_enumerator_statistics_overtime(
        sample_enumerator_data,
        "submission_date",
        ["enumerator"],
        "age",
        "mean",
        "Weekly",
        "MON",
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns


def test_compute_enumerator_statistics_overtime_monthly(sample_enumerator_data):
    """Test statistics overtime with monthly period."""
    result = compute_enumerator_statistics_overtime(
        sample_enumerator_data,
        "submission_date",
        ["enumerator"],
        "age",
        "mean",
        "Monthly",
        "SUN",
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns


def test_compute_enumerator_statistics_overtime_missing_stat(sample_enumerator_data):
    """Test statistics overtime with missing statistic."""
    # Add some null values
    data_with_nulls = sample_enumerator_data.clone()
    data_with_nulls = data_with_nulls.with_columns(
        pl.when(pl.col("enumerator") == "E1")
        .then(None)
        .otherwise(pl.col("age"))
        .alias("age")
    )

    result = compute_enumerator_statistics_overtime(
        data_with_nulls,
        "submission_date",
        ["enumerator"],
        "age",
        "missing",
        "Daily",
        "SUN",
    )

    assert not result.is_empty()


def test_compute_enumerator_statistics_overtime_percentile_stats(
    sample_enumerator_data,
):
    """Test statistics overtime with percentile statistics."""
    result_25th = compute_enumerator_statistics_overtime(
        sample_enumerator_data,
        "submission_date",
        ["enumerator"],
        "age",
        "25th percentile",
        "Daily",
        "SUN",
    )
    assert not result_25th.is_empty()

    result_75th = compute_enumerator_statistics_overtime(
        sample_enumerator_data,
        "submission_date",
        ["enumerator"],
        "age",
        "75th percentile",
        "Daily",
        "SUN",
    )
    assert not result_75th.is_empty()


def test_compute_enumerator_statistics_overtime_legacy_periods(sample_enumerator_data):
    """Test statistics overtime with legacy period names."""
    # Test "Day" -> "Daily"
    result = compute_enumerator_statistics_overtime(
        sample_enumerator_data,
        "submission_date",
        ["enumerator"],
        "age",
        "mean",
        "Day",
        "SUN",
    )
    assert not result.is_empty()

    # Test "Week" -> "Weekly"
    result = compute_enumerator_statistics_overtime(
        sample_enumerator_data,
        "submission_date",
        ["enumerator"],
        "age",
        "mean",
        "Week",
        "MON",
    )
    assert not result.is_empty()

    # Test "Month" -> "Monthly"
    result = compute_enumerator_statistics_overtime(
        sample_enumerator_data,
        "submission_date",
        ["enumerator"],
        "age",
        "mean",
        "Month",
        "SUN",
    )
    assert not result.is_empty()


def test_compute_enumerator_statistics_overtime_with_team(sample_enumerator_data):
    """Test statistics overtime with team grouping."""
    result = compute_enumerator_statistics_overtime(
        sample_enumerator_data,
        "submission_date",
        ["enumerator", "team"],
        "age",
        "mean",
        "Daily",
        "SUN",
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns
    assert "team" in result.columns


# ============================================
# HELPER FUNCTIONS TESTS
# ============================================


def test_get_numeric_columns():
    """Test _get_numeric_columns helper function."""
    data = pl.DataFrame(
        {
            "age": [25, 30, 35],
            "income": [50000, 60000, 55000],
            "name": ["Alice", "Bob", "Charlie"],
            "is_active": [True, False, True],
        }
    )

    result = _get_numeric_columns(data)
    assert "age" in result
    assert "income" in result
    assert "name" not in result
    assert "is_active" not in result


def test_get_numeric_columns_with_exclude():
    """Test _get_numeric_columns with exclude list."""
    data = pl.DataFrame(
        {
            "age": [25, 30, 35],
            "income": [50000, 60000, 55000],
            "duration": [3600, 4200, 3800],
        }
    )

    result = _get_numeric_columns(data, exclude_cols=["duration"])
    assert "age" in result
    assert "income" in result
    assert "duration" not in result


def test_get_numeric_columns_empty_dataframe():
    """Test _get_numeric_columns with empty DataFrame."""
    data = pl.DataFrame()
    result = _get_numeric_columns(data)
    assert result == []


def test_get_numeric_columns_no_numeric():
    """Test _get_numeric_columns with no numeric columns."""
    data = pl.DataFrame(
        {
            "name": ["Alice", "Bob"],
            "city": ["NYC", "LA"],
        }
    )
    result = _get_numeric_columns(data)
    assert result == []


# ============================================
# EDGE CASES AND ERROR HANDLING TESTS
# ============================================


def test_edge_case_single_enumerator():
    """Test handling of single enumerator."""
    data = pl.DataFrame(
        {
            "submission_date": [date.today(), date.today() - timedelta(days=1)],
            "enumerator": ["E1", "E1"],
            "age": [25, 30],
        }
    )

    result = compute_enumerator_overview(data, "submission_date", "enumerator", None)
    assert result.num_enumerators == 1
    assert result.all_submissions == 2


def test_edge_case_all_null_values():
    """Test handling of all null values in column."""
    data = pl.DataFrame(
        {
            "submission_date": [date.today(), date.today()],
            "enumerator": ["E1", "E2"],
            "age": [None, None],
        }
    )

    with patch("streamlit.cache_data", lambda ttl: lambda f: f):
        result = compute_enumerator_statistics(
            data,
            ["enumerator"],
            ["age"],
            ["mean"],
        )

    assert not result.is_empty()
    # Mean of nulls should be null
    assert result["age_mean"].is_null().any()


def test_edge_case_single_submission():
    """Test handling of single submission."""
    data = pl.DataFrame(
        {
            "submission_date": [date.today()],
            "enumerator": ["E1"],
            "team": ["T1"],
            "age": [25],
        }
    )

    result = compute_enumerator_overview(data, "submission_date", "enumerator", "team")
    assert result.all_submissions == 1
    assert result.num_enumerators == 1


def test_edge_case_date_ranges():
    """Test handling of various date ranges."""
    today = date.today()
    data = pl.DataFrame(
        {
            "submission_date": [
                today,
                today - timedelta(days=365),
                today - timedelta(days=1000),
            ],
            "enumerator": ["E1", "E2", "E3"],
        }
    )

    result = compute_enumerator_productivity(
        data, "submission_date", ["enumerator"], "Monthly", "SUN"
    )
    assert not result.is_empty()


# ============================================
# INTEGRATION TESTS
# ============================================


@patch("datasure.checks.enumerator.load_missing_codes_from_db")
def test_full_enumerator_workflow(mock_load_missing, sample_enumerator_data):
    """Test complete enumerator workflow from overview to statistics."""
    mock_load_missing.return_value = pl.DataFrame()

    # Step 1: Compute overview
    overview = compute_enumerator_overview(
        sample_enumerator_data, "submission_date", "enumerator", "team"
    )
    assert overview.num_enumerators == 3

    # Step 2: Compute summary
    summary = compute_enumerator_summary(
        "test_project",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        "formversion",
        "duration",
    )
    assert len(summary) > 0

    # Step 3: Compute productivity
    productivity = compute_enumerator_productivity(
        sample_enumerator_data, "submission_date", ["enumerator"], "Daily", "SUN"
    )
    assert not productivity.is_empty()

    # Step 4: Compute statistics
    with patch("streamlit.cache_data", lambda ttl: lambda f: f):
        statistics = compute_enumerator_statistics(
            sample_enumerator_data,
            ["enumerator"],
            ["age", "income"],
            ["mean", "median"],
        )
    assert not statistics.is_empty()

    # Step 5: Compute statistics overtime
    stats_overtime = compute_enumerator_statistics_overtime(
        sample_enumerator_data,
        "submission_date",
        ["enumerator"],
        "age",
        "mean",
        "Daily",
        "SUN",
    )
    assert not stats_overtime.is_empty()


def test_enumerator_workflow_with_missing_data():
    """Test enumerator workflow with missing data."""
    data = pl.DataFrame(
        {
            "submission_date": [date.today(), date.today() - timedelta(days=1)],
            "enumerator": ["E1", "E2"],
            "age": [25, None],
            "income": [50000, 60000],
        }
    )

    # Overview should work with missing data
    overview = compute_enumerator_overview(data, "submission_date", "enumerator", None)
    assert overview.all_submissions == 2

    # Statistics should handle missing values
    with patch("streamlit.cache_data", lambda ttl: lambda f: f):
        statistics = compute_enumerator_statistics(
            data,
            ["enumerator"],
            ["age", "income"],
            ["count", "mean"],
        )
    assert not statistics.is_empty()


def test_enumerator_workflow_different_time_periods(sample_enumerator_data):
    """Test enumerator workflow with different time periods."""
    periods = ["Daily", "Weekly", "Monthly"]

    for period in periods:
        # Test productivity
        productivity = compute_enumerator_productivity(
            sample_enumerator_data, "submission_date", ["enumerator"], period, "MON"
        )
        assert not productivity.is_empty()

        # Test statistics overtime
        stats_overtime = compute_enumerator_statistics_overtime(
            sample_enumerator_data,
            "submission_date",
            ["enumerator"],
            "age",
            "mean",
            period,
            "MON",
        )
        assert not stats_overtime.is_empty()


@patch("datasure.checks.enumerator.duckdb_save_table")
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
# BRANCH MISS TESTS (COMPUTE FUNCTIONS)
# ============================================


@patch("datasure.checks.enumerator.load_missing_codes_from_db")
def test_compute_enumerator_summary_without_consent_outcome_cols(mock_load_missing):
    """compute_enumerator_summary skips consent/outcome when cols are absent."""
    mock_load_missing.return_value = pl.DataFrame()
    data = pl.DataFrame(
        {
            "submission_date": [date.today()],
            "enumerator": ["E1"],
        }
    )
    result = compute_enumerator_summary(
        "proj", data, "submission_date", "enumerator", None, None, None
    )
    assert not result.is_empty()
    assert "% consent" not in result.columns
    assert "% completed survey" not in result.columns


def test_compute_enumerator_productivity_unknown_period(sample_enumerator_data):
    """compute_enumerator_productivity falls through period branches on unknown."""
    with pytest.raises(ColumnNotFoundError):
        compute_enumerator_productivity(
            sample_enumerator_data,
            "submission_date",
            ["enumerator"],
            "UnknownPeriod",
            "SUN",
        )


def test_compute_enumerator_statistics_overtime_unknown_period(sample_enumerator_data):
    """compute_enumerator_statistics_overtime falls through period branches."""
    with pytest.raises(ColumnNotFoundError):
        compute_enumerator_statistics_overtime(
            sample_enumerator_data,
            "submission_date",
            ["enumerator"],
            "age",
            "mean",
            "UnknownPeriod",
            "SUN",
        )


# ============================================
# PATCHED_ENUM UI FUNCTION TESTS
# ============================================


def test_render_enumerator_overview_no_date_enum(patched_enum):
    """_render_enumerator_overview_metrics shows info when date/enum is None."""
    _render_enumerator_overview_metrics(pl.DataFrame(), None, None, None)
    patched_enum.info.assert_called()


def test_render_enumerator_overview_with_data(patched_enum, sample_enumerator_data):
    """_render_enumerator_overview_metrics renders metrics with valid data."""
    _render_enumerator_overview_metrics(
        sample_enumerator_data, "submission_date", "enumerator", "team"
    )
    patched_enum.columns.assert_called()


def test_render_enumerator_overview_no_team(patched_enum, sample_enumerator_data):
    """_render_enumerator_overview_metrics renders without team column."""
    _render_enumerator_overview_metrics(
        sample_enumerator_data, "submission_date", "enumerator", None
    )
    patched_enum.columns.assert_called()


def test_render_time_period_selector_default(patched_enum):
    """_render_time_period_selector returns Day when pills returns None."""
    result = _render_time_period_selector("settings.json")
    assert result == "Day"
    patched_enum.pills.assert_called()


def test_render_time_period_selector_week(patched_enum):
    """_render_time_period_selector returns Week when pills returns Week."""
    patched_enum.pills.return_value = "Week"
    result = _render_time_period_selector("settings.json")
    assert result == "Week"


def test_render_weekday_selector(patched_enum):
    """_render_weekday_selector returns offset code for the selected weekday."""
    patched_enum.selectbox.return_value = "Monday"
    result = _render_weekday_selector("settings.json")
    assert result == "SUN"


def test_load_statistics_settings_default(patched_enum):
    """_load_statistics_settings returns default StatisticsSettings."""
    result = _load_statistics_settings("settings.json")
    assert result.stats == ["count", "mean"]


def test_render_column_selector(patched_enum):
    """_render_column_selector returns list from multiselect."""
    result = _render_column_selector(["age", "income"], None, "settings.json")
    assert isinstance(result, list)
    patched_enum.multiselect.assert_called()


def test_render_statistics_selector(patched_enum):
    """_render_statistics_selector returns list from multiselect."""
    result = _render_statistics_selector(["count", "mean"], "settings.json")
    assert isinstance(result, list)
    patched_enum.multiselect.assert_called()


def test_render_enumerator_statistics_no_enum(patched_enum):
    """_render_enumerator_statistics shows info when enumerator is None."""
    _render_enumerator_statistics(pl.DataFrame(), None, None, "settings.json")
    patched_enum.info.assert_called()


def test_load_statistics_overtime_settings_default(patched_enum):
    """_load_statistics_overtime_settings returns default settings."""
    result = _load_statistics_overtime_settings("settings.json")
    assert result.stat == "count"


def test_render_period_selector_overtime_default(patched_enum):
    """_render_period_selector_overtime returns Day when pills returns None."""
    result = _render_period_selector_overtime("settings.json")
    assert result == "Day"
    patched_enum.pills.assert_called()


def test_render_period_selector_overtime_week(patched_enum):
    """_render_period_selector_overtime returns Week when pills returns Week."""
    patched_enum.pills.return_value = "Week"
    result = _render_period_selector_overtime("settings.json", default_period="Week")
    assert result == "Week"


def test_render_weekday_selector_overtime(patched_enum):
    """_render_weekday_selector_overtime returns offset code."""
    patched_enum.selectbox.return_value = "Tuesday"
    result = _render_weekday_selector_overtime("Monday", "settings.json")
    assert result == "MON"


def test_render_statistic_selector(patched_enum):
    """_render_statistic_selector returns the selectbox value."""
    patched_enum.selectbox.return_value = "mean"
    result = _render_statistic_selector("count", "settings.json")
    assert result == "mean"


def test_render_column_selector_single_default_none(patched_enum):
    """_render_column_selector_single returns None when selectbox returns None."""
    result = _render_column_selector_single(["age", "income"], None, "settings.json")
    assert result is None
    patched_enum.selectbox.assert_called()


def test_render_column_selector_single_with_value(patched_enum):
    """_render_column_selector_single returns the selectbox value."""
    patched_enum.selectbox.return_value = "age"
    result = _render_column_selector_single(["age", "income"], "age", "settings.json")
    assert result == "age"


def test_render_enumerator_productivity_no_enum(patched_enum):
    """_render_enumerator_productivity shows info when enum/date is None."""
    _render_enumerator_productivity(pl.DataFrame(), None, None, None, "settings.json")
    patched_enum.info.assert_called()


def test_render_enumerator_statistics_overtime_no_enum(patched_enum):
    """_render_enumerator_statistics_overtime shows info when enum/date is None."""
    _render_enumerator_statistics_overtime(
        pl.DataFrame(), None, None, None, "settings.json"
    )
    patched_enum.info.assert_called()


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


def test_render_enumerator_summary_table_no_date_enum(enum_bc):
    """_render_enumerator_summary_table shows info when date/enum is None."""
    enum_bc._render_enumerator_summary_table(
        "proj", pl.DataFrame(), None, None, None, None, None
    )
    enum_bc.st.info.assert_called()


def test_render_enumerator_summary_table_with_data(enum_bc, sample_enumerator_data):
    """_render_enumerator_summary_table renders table with valid data."""
    enum_bc._render_enumerator_summary_table(
        "proj",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        "formversion",
        "duration",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_summary_table_with_show_info(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_summary_table filters columns when show_info selected."""
    enum_bc.st.pills.return_value = ["submissions"]
    enum_bc._render_enumerator_summary_table(
        "proj",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "formversion",
        "duration",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_productivity_table_day(enum_bc, sample_enumerator_data):
    """_render_enumerator_productivity_table renders with Day period."""
    enum_bc._render_enumerator_productivity_table(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "settings.json",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_productivity_table_week(enum_bc, sample_enumerator_data):
    """_render_enumerator_productivity_table renders weekday selector for Week."""
    enum_bc.st.pills.return_value = "Week"
    enum_bc.st.selectbox.return_value = "Monday"
    enum_bc._render_enumerator_productivity_table(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        "settings.json",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_statistics_table_no_enum(enum_bc):
    """_render_enumerator_statistics_table shows info when enum is None."""
    enum_bc._render_enumerator_statistics_table(pl.DataFrame(), None, None, "s.json")
    enum_bc.st.info.assert_called()


def test_render_enumerator_statistics_table_no_cols(enum_bc, sample_enumerator_data):
    """_render_enumerator_statistics_table shows info when no cols selected."""
    enum_bc._render_enumerator_statistics_table(
        sample_enumerator_data, "enumerator", None, "settings.json"
    )
    enum_bc.st.info.assert_called()


def test_render_enumerator_statistics_table_with_cols(enum_bc, sample_enumerator_data):
    """_render_enumerator_statistics_table renders table when cols selected."""
    enum_bc.st.multiselect.side_effect = [["age"], ["count", "mean"]]
    enum_bc._render_enumerator_statistics_table(
        sample_enumerator_data, "enumerator", "team", "settings.json"
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_statistics_with_enum(enum_bc, sample_enumerator_data):
    """_render_enumerator_statistics calls the fragment table function."""
    enum_bc._render_enumerator_statistics(
        sample_enumerator_data, "enumerator", None, "settings.json"
    )
    enum_bc.st.info.assert_called()


def test_render_enumerator_statistics_overtime_table_no_statscol(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_statistics_overtime_table shows info when statscol None."""
    enum_bc._render_enumerator_statistics_overtime_table(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "settings.json",
    )
    enum_bc.st.info.assert_called()


def test_render_enumerator_statistics_overtime_table_with_col(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_statistics_overtime_table renders with valid col."""
    enum_bc.st.selectbox.side_effect = ["age", "count"]
    enum_bc._render_enumerator_statistics_overtime_table(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "settings.json",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_statistics_overtime_table_week_period(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_statistics_overtime_table handles Week period."""
    enum_bc.st.pills.return_value = "Week"
    enum_bc.st.selectbox.side_effect = ["age", "count", "Monday"]
    enum_bc._render_enumerator_statistics_overtime_table(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        "settings.json",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_productivity_with_valid_params(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_productivity calls the table fragment when params valid."""
    enum_bc._render_enumerator_productivity(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "settings.json",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_statistics_overtime_with_valid_params(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_statistics_overtime calls the table fragment."""
    enum_bc._render_enumerator_statistics_overtime(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "settings.json",
    )
    enum_bc.st.info.assert_called()


def test_enumerator_report_empty_data(enum_bc):
    """enumerator_report shows info and returns early when data is empty."""
    survey_cols = ColumnByType(
        categorical_columns=["survey_id", "enumerator"],
        datetime_columns=["submission_date"],
    )
    enum_bc.enumerator_report(
        "proj_id",
        pl.DataFrame(),
        "settings.json",
        {"survey_id": "survey_id"},
        survey_cols,
    )
    enum_bc.st.info.assert_called()


def test_enumerator_report_with_data(enum_bc, sample_enumerator_data):
    """enumerator_report renders full report with valid data."""
    survey_cols = ColumnByType(
        categorical_columns=list(sample_enumerator_data.columns),
        datetime_columns=["submission_date"],
    )
    enum_bc._render_consent_outcome_settings = MagicMock()

    def _selectbox_side_effect(label, options=None, **kwargs):
        if options and "seconds" in options:
            return "seconds"
        return None

    enum_bc.st.selectbox.side_effect = _selectbox_side_effect
    enum_bc.enumerator_report(
        "proj_id",
        sample_enumerator_data,
        "settings.json",
        {"survey_id": "survey_id"},
        survey_cols,
    )
    enum_bc.st.title.assert_called()


def test_load_statistics_settings_fallback(patched_enum):
    """_load_statistics_settings returns defaults when saved settings invalid."""
    with patch(
        "datasure.checks.enumerator.load_check_settings",
        return_value={"stats": ["not_a_real_stat"]},
    ):
        result = _load_statistics_settings("settings.json")
    assert result.stats == ["count", "mean"]


def test_load_statistics_overtime_settings_fallback(patched_enum):
    """_load_statistics_overtime_settings returns defaults when settings invalid."""
    with patch(
        "datasure.checks.enumerator.load_check_settings",
        return_value={"period_overtime": "bad_period"},
    ):
        result = _load_statistics_overtime_settings("settings.json")
    assert result.stat == "count"


def test_render_enumerator_statistics_table_with_cols_no_team(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_statistics_table uses else column config when no team."""
    enum_bc.st.multiselect.side_effect = [["age"], ["count"]]
    enum_bc._render_enumerator_statistics_table(
        sample_enumerator_data, "enumerator", None, "settings.json"
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_statistics_overtime_table_early_return(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_statistics_overtime_table returns early when enum None."""
    enum_bc._render_enumerator_statistics_overtime_table(
        sample_enumerator_data, "submission_date", None, None, "settings.json"
    )
    enum_bc.st.dataframe.assert_not_called()


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
