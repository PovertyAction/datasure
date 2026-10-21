"""Tests for datasure.checks.enumerator.compute."""

from datetime import date, datetime, timedelta
from unittest.mock import patch

import polars as pl
import pytest
from polars.exceptions import ColumnNotFoundError

from datasure.checks.enumerator.compute import (
    compute_enumerator_missing_table,
    compute_enumerator_overview,
    compute_enumerator_productivity,
    compute_enumerator_statistics,
    compute_enumerator_statistics_overtime,
    compute_enumerator_summary,
    compute_latest_submission_date,
)

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


@patch("datasure.checks.enumerator.compute.load_missing_codes_from_db")
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


@patch("datasure.checks.enumerator.compute.load_missing_codes_from_db")
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


@patch("datasure.checks.enumerator.compute.load_missing_codes_from_db")
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


@patch("datasure.checks.enumerator.compute.load_missing_codes_from_db")
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


@patch("datasure.checks.enumerator.compute.load_missing_codes_from_db")
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


@patch("datasure.checks.enumerator.compute.load_missing_codes_from_db")
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


@patch("datasure.checks.enumerator.compute.load_missing_codes_from_db")
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


# ============================================
# BRANCH MISS TESTS (COMPUTE FUNCTIONS)
# ============================================


@patch("datasure.checks.enumerator.compute.load_missing_codes_from_db")
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
# ZERO-ROW INPUT TESTS
# ============================================


@pytest.mark.parametrize("period", ["Daily", "Weekly", "Monthly"])
def test_compute_enumerator_productivity_zero_rows(sample_enumerator_data, period):
    """Data a step emptied gives an empty productivity table, not an error."""
    result = compute_enumerator_productivity(
        sample_enumerator_data.clear(), "submission_date", ["enumerator"], period, "MON"
    )

    assert result.is_empty()


def test_compute_enumerator_statistics_zero_rows(sample_enumerator_data):
    """Data a step emptied gives an empty statistics table, not an error."""
    result = compute_enumerator_statistics(
        sample_enumerator_data.clear(), ["enumerator"], ["age"], ["mean", "median"]
    )

    assert result.is_empty()


@pytest.mark.parametrize("period", ["Daily", "Weekly", "Monthly"])
def test_compute_enumerator_statistics_overtime_zero_rows(
    sample_enumerator_data, period
):
    """Data a step emptied gives an empty over-time table, not an error."""
    result = compute_enumerator_statistics_overtime(
        sample_enumerator_data.clear(),
        "submission_date",
        ["enumerator"],
        "age",
        "mean",
        period,
        "MON",
    )

    assert result.is_empty()


def test_compute_enumerator_missing_table_zero_rows(sample_enumerator_data):
    """Data a step emptied gives an empty missing table, not an error."""
    result = compute_enumerator_missing_table(
        sample_enumerator_data.clear(), pl.DataFrame(), ["enumerator"]
    )

    assert result.is_empty()


@patch("datasure.checks.enumerator.compute.load_missing_codes_from_db")
def test_compute_enumerator_summary_dates_across_two_months(mock_load_missing):
    """Dates compare as dates, not text, when the data spans two months."""
    mock_load_missing.return_value = pl.DataFrame()
    data = pl.DataFrame(
        {
            "submission_date": [
                date(2026, 9, 28),
                date(2026, 9, 30),
                date(2026, 10, 14),
            ],
            "enumerator": ["E1", "E1", "E1"],
        }
    )

    result = compute_enumerator_summary(
        project_id="test_project",
        data=data,
        date="submission_date",
        enumerator="enumerator",
        team=None,
        formversion=None,
        duration=None,
        today=date(2026, 10, 14),
    )

    row = result.row(0, named=True)
    assert row["first submission"] == "Sep 28, 2026"
    assert row["last submission"] == "Oct 14, 2026"
    assert row["# submissions today"] == 1
    # 14 Oct 2026 is a Wednesday, so the week starts on Monday 12 Oct.
    assert row["# submissions this week"] == 1
    assert row["# submissions this month"] == 1


@patch("datasure.checks.enumerator.compute.load_missing_codes_from_db")
def test_compute_enumerator_summary_datetimes_across_two_years(mock_load_missing):
    """Datetimes spanning two years keep date order and day-level grouping."""
    mock_load_missing.return_value = pl.DataFrame()
    data = pl.DataFrame(
        {
            "submission_date": [
                datetime(2025, 12, 30, 9, 0),
                datetime(2026, 1, 15, 8, 0),
                datetime(2026, 1, 15, 17, 30),
                datetime(2026, 1, 20, 10, 0),
            ],
            "enumerator": ["E1", "E1", "E2", "E2"],
            "formversion": [1, 1, 2, 2],
        }
    )

    result = compute_enumerator_summary(
        project_id="test_project",
        data=data,
        date="submission_date",
        enumerator="enumerator",
        team=None,
        formversion="formversion",
        duration=None,
        today=date(2026, 1, 20),
    ).sort("enumerator")

    e1, e2 = result.rows(named=True)
    assert e1["first submission"] == "Dec 30, 2025"
    assert e1["last submission"] == "Jan 15, 2026"
    assert e1["# submissions this month"] == 1
    assert e1["# submissions this week"] == 0
    # E1's 08:00 submission on 15 Jan is outdated against E2's 17:30 one on
    # the same day, which it would not be if grouped per timestamp.
    assert e1["# of outdated form versions"] == 1
    assert e2["first submission"] == "Jan 15, 2026"
    assert e2["last submission"] == "Jan 20, 2026"
    assert e2["# submissions today"] == 1
    assert e2["# submissions this week"] == 1
    assert e2["# submissions this month"] == 2
    assert e2["# of outdated form versions"] == 0


@patch("datasure.checks.enumerator.compute.load_missing_codes_from_db")
def test_compute_enumerator_summary_timezone_aware_uses_local_day(mock_load_missing):
    """Timezone-aware datetimes count on their local day, not the UTC day."""
    mock_load_missing.return_value = pl.DataFrame()
    data = pl.DataFrame(
        {
            # 23:30 UTC on 14 Oct is 08:30 on 15 Oct in Tokyo.
            "submission_date": pl.Series([datetime(2026, 10, 14, 23, 30)])
            .dt.replace_time_zone("UTC")
            .dt.convert_time_zone("Asia/Tokyo"),
            "enumerator": ["E1"],
        }
    )

    result = compute_enumerator_summary(
        project_id="test_project",
        data=data,
        date="submission_date",
        enumerator="enumerator",
        team=None,
        formversion=None,
        duration=None,
        today=date(2026, 10, 15),
    )

    row = result.row(0, named=True)
    assert row["first submission"] == "Oct 15, 2026"
    assert row["# submissions today"] == 1


def test_compute_enumerator_overview_active_uses_injected_today():
    """The active cut-off counts back 7 days from the injected date."""
    data = pl.DataFrame(
        {
            "submission_date": [date(2026, 10, 14), date(2026, 10, 7)],
            "enumerator": ["E1", "E2"],
        }
    )

    result = compute_enumerator_overview(
        data, "submission_date", "enumerator", None, today=date(2026, 10, 14)
    )

    # 7 Oct is exactly one week before 14 Oct, so E2 is not active.
    assert result.num_active_enumerators == 1


def test_compute_enumerator_overview_timezone_aware_uses_local_day():
    """The active cut-off uses the local day, as the summary table does."""
    data = pl.DataFrame(
        {
            # 23:30 UTC on 7 Oct is 08:30 on 8 Oct in Tokyo.
            "submission_date": pl.Series([datetime(2026, 10, 7, 23, 30)])
            .dt.replace_time_zone("UTC")
            .dt.convert_time_zone("Asia/Tokyo"),
            "enumerator": ["E1"],
        }
    )

    result = compute_enumerator_overview(
        data, "submission_date", "enumerator", None, today=date(2026, 10, 14)
    )

    assert result.num_active_enumerators == 1


def test_compute_latest_submission_date_cuts_datetimes_to_day():
    """The latest submission is returned as a date, by date order."""
    data = pl.DataFrame(
        {
            "submission_date": [
                datetime(2026, 9, 30, 18, 0),
                datetime(2026, 10, 2, 7, 45),
            ]
        }
    )

    assert compute_latest_submission_date(data, "submission_date") == date(2026, 10, 2)


def test_compute_latest_submission_date_empty():
    """No submissions gives None, so the "Data as of" note is skipped."""
    data = pl.DataFrame({"submission_date": pl.Series([], dtype=pl.Date)})

    assert compute_latest_submission_date(data, "submission_date") is None


@patch("datasure.checks.enumerator.compute.load_missing_codes_from_db")
def test_compute_enumerator_summary_zero_rows(
    mock_load_missing, sample_enumerator_data
):
    """Data a step emptied gives an empty summary, not an error."""
    mock_load_missing.return_value = pl.DataFrame()

    result = compute_enumerator_summary(
        "test_project",
        sample_enumerator_data.clear(),
        "submission_date",
        "enumerator",
        "team",
        "formversion",
        "duration",
    )

    assert result.is_empty()
    assert "# submissions" in result.columns
