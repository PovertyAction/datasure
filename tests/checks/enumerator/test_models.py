"""Tests for datasure.checks.enumerator.models."""

import pytest
from pydantic import ValidationError

from datasure.checks.enumerator.models import (
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
)

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
