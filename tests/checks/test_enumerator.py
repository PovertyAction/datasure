"""Tests for enumerator module.

This module tests the refactored enumerator performance analysis system using
Polars DataFrames and Pydantic models for validation and configuration.
"""

import json
from datetime import date, timedelta
from unittest.mock import patch

import polars as pl
import pytest
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
    _trigger_success_message,
    compute_enumerator_missing_table,
    compute_enumerator_overview,
    compute_enumerator_productivity,
    compute_enumerator_statistics,
    compute_enumerator_statistics_overtime,
    compute_enumerator_summary,
    load_default_enumerator_settings,
)

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
    return pl.DataFrame({
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
    })


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
    return pl.DataFrame({
        "label": ["Refused", "Don't know"],
        "codes": ["-99", "-88"],
    })


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
    assert settings.period_overtime == "Daily"
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


def test_trigger_success_message():
    """Test _trigger_success_message function."""
    import streamlit as st
    st.session_state = {}

    _trigger_success_message("test_button")
    assert st.session_state["test_button"] is True


def test_create_enum_data_on_settings_with_consent_and_outcome():
    """Test _create_enum_data_on_settings with consent and outcome values."""
    data = pl.DataFrame({
        "survey_id": ["S001", "S002", "S003"],
        "consent": ["yes", "no", "yes"],
        "outcome": ["completed", "incomplete", "completed"],
    })

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
    data = pl.DataFrame({
        "survey_id": ["S001", "S002"],
        "outcome": ["completed", "completed"],
    })

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
    data = pl.DataFrame({
        "survey_id": ["S001", "S002"],
        "consent": ["yes", "yes"],
    })

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
    empty_data = pl.DataFrame(schema={"submission_date": pl.Date, "enumerator": pl.Utf8})

    with pytest.raises(ValueError, match="Input data is empty"):
        compute_enumerator_overview(empty_data, "submission_date", "enumerator", None)


def test_compute_enumerator_overview_active_enumerators():
    """Test active enumerators calculation."""
    today = date.today()
    data = pl.DataFrame({
        "submission_date": [
            today - timedelta(days=1),
            today - timedelta(days=10),
            today,
        ],
        "enumerator": ["E1", "E2", "E1"],
        "team": ["T1", "T1", "T1"],
    })

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


def test_compute_enumerator_missing_table_with_config(sample_enumerator_data, sample_missing_codes_config):
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
def test_compute_enumerator_summary_without_team(mock_load_missing, sample_enumerator_data):
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
def test_compute_enumerator_summary_without_duration(mock_load_missing, sample_enumerator_data):
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
def test_compute_enumerator_summary_without_formversion(mock_load_missing, sample_enumerator_data):
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
def test_compute_enumerator_summary_with_consent(mock_load_missing, sample_enumerator_data):
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
def test_compute_enumerator_summary_with_outcome(mock_load_missing, sample_enumerator_data):
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
        sample_enumerator_data, "submission_date", ["enumerator", "team"], "Daily", "SUN"
    )

    assert not result.is_empty()
    assert "enumerator" in result.columns
    assert "team" in result.columns


def test_compute_enumerator_productivity_different_weekstarts(sample_enumerator_data):
    """Test productivity with different week start days."""
    for weekstart in ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"]:
        result = compute_enumerator_productivity(
            sample_enumerator_data, "submission_date", ["enumerator"], "Weekly", weekstart
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
            ["count", "min", "mean", "median", "max", "std", "25th percentile", "75th percentile"],
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


def test_compute_enumerator_statistics_overtime_percentile_stats(sample_enumerator_data):
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
    data = pl.DataFrame({
        "age": [25, 30, 35],
        "income": [50000, 60000, 55000],
        "name": ["Alice", "Bob", "Charlie"],
        "is_active": [True, False, True],
    })

    result = _get_numeric_columns(data)
    assert "age" in result
    assert "income" in result
    assert "name" not in result
    assert "is_active" not in result


def test_get_numeric_columns_with_exclude():
    """Test _get_numeric_columns with exclude list."""
    data = pl.DataFrame({
        "age": [25, 30, 35],
        "income": [50000, 60000, 55000],
        "duration": [3600, 4200, 3800],
    })

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
    data = pl.DataFrame({
        "name": ["Alice", "Bob"],
        "city": ["NYC", "LA"],
    })
    result = _get_numeric_columns(data)
    assert result == []


# ============================================
# EDGE CASES AND ERROR HANDLING TESTS
# ============================================


def test_edge_case_single_enumerator():
    """Test handling of single enumerator."""
    data = pl.DataFrame({
        "submission_date": [date.today(), date.today() - timedelta(days=1)],
        "enumerator": ["E1", "E1"],
        "age": [25, 30],
    })

    result = compute_enumerator_overview(data, "submission_date", "enumerator", None)
    assert result.num_enumerators == 1
    assert result.all_submissions == 2


def test_edge_case_all_null_values():
    """Test handling of all null values in column."""
    data = pl.DataFrame({
        "submission_date": [date.today(), date.today()],
        "enumerator": ["E1", "E2"],
        "age": [None, None],
    })

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
    data = pl.DataFrame({
        "submission_date": [date.today()],
        "enumerator": ["E1"],
        "team": ["T1"],
        "age": [25],
    })

    result = compute_enumerator_overview(data, "submission_date", "enumerator", "team")
    assert result.all_submissions == 1
    assert result.num_enumerators == 1


def test_edge_case_date_ranges():
    """Test handling of various date ranges."""
    today = date.today()
    data = pl.DataFrame({
        "submission_date": [
            today,
            today - timedelta(days=365),
            today - timedelta(days=1000),
        ],
        "enumerator": ["E1", "E2", "E3"],
    })

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
    data = pl.DataFrame({
        "submission_date": [date.today(), date.today() - timedelta(days=1)],
        "enumerator": ["E1", "E2"],
        "age": [25, None],
        "income": [50000, 60000],
    })

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
    data = sample_enumerator_data.with_columns([
        pl.lit("yes").alias("consent"),
        pl.lit("completed").alias("outcome"),
    ])

    # Create enum data with settings
    _create_enum_data_on_settings("test_project", data, config)

    # Verify the data was saved
    assert mock_save.called
