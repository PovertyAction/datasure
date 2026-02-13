"""Tests for the progress module with comprehensive coverage."""

import math
from unittest.mock import patch

import polars as pl
import pytest
from pydantic import ValidationError

from datasure.checks.progress import (
    AttemptedInterviewsMetrics,
    AttemptedInterviewsResult,
    ProgressChartMetrics,
    ProgressSettings,
    ProgressSummary,
    TimePeriodConfig,
    _aggregate_attempts_by_survey_id,
    _compute_summary_stats,
    _expand_attempt_dates,
    _get_unique_values,
    _prepare_display_columns,
    compute_attempted_interviews,
    compute_average_interviews,
    compute_progress_chart,
    compute_progress_overtime,
    compute_progress_summary,
)


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests.
    """
    pass


class TestComputeProgressSummary:
    """Test compute_progress_summary function."""

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_summary_structure(self, sample_dataframe):
        """Test that compute_progress_summary returns ProgressSummary model."""
        data_pl = pl.from_pandas(sample_dataframe)
        result = compute_progress_summary(data_pl, 10)

        assert isinstance(result, ProgressSummary)
        assert hasattr(result, "total_submitted")
        assert hasattr(result, "target")
        assert hasattr(result, "percentage_completed")

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_summary_values_with_target(self, sample_dataframe):
        """Test compute_progress_summary with valid target."""
        data_pl = pl.from_pandas(sample_dataframe)
        target = 10
        result = compute_progress_summary(data_pl, target)

        expected_total = len(sample_dataframe)
        expected_percentage = (expected_total / target) * 100

        assert result.total_submitted == expected_total
        assert result.target == target
        assert result.percentage_completed == expected_percentage

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_summary_no_target(self, sample_dataframe):
        """Test compute_progress_summary with no target."""
        data_pl = pl.from_pandas(sample_dataframe)
        result = compute_progress_summary(data_pl, None)

        assert result.total_submitted == len(sample_dataframe)
        assert result.target is None
        assert result.percentage_completed == 0

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_summary_zero_target(self, sample_dataframe):
        """Test compute_progress_summary with zero target."""
        data_pl = pl.from_pandas(sample_dataframe)
        result = compute_progress_summary(data_pl, 0)

        assert result.total_submitted == len(sample_dataframe)
        assert result.target == 0
        assert result.percentage_completed == 0

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_summary_empty_data(self):
        """Test compute_progress_summary with empty dataframe (no rows)."""
        # Empty DataFrame with columns to avoid Polars hashing issues
        empty_pl = pl.DataFrame({"col1": [], "col2": []})
        result = compute_progress_summary(empty_pl, 10)

        assert result.total_submitted == 0
        assert result.target == 10
        assert result.percentage_completed == 0


class TestComputeProgressChart:
    """Test compute_progress_chart function."""

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_chart_structure(self, sample_dataframe):
        """Test that compute_progress_chart returns expected structure."""
        data_pl = pl.from_pandas(sample_dataframe)
        result = compute_progress_chart(
            data_pl, "consent", ["Yes"], "outcome", ["Complete"]
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)  # consent_percentage
        assert isinstance(result[1], float)  # completion_percentage

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_chart_with_valid_data(self, sample_dataframe):
        """Test compute_progress_chart with valid consent and outcome data."""
        data_pl = pl.from_pandas(sample_dataframe)
        consent_vals = ["Yes"]
        outcome_vals = ["Complete"]

        result = compute_progress_chart(
            data_pl, "consent", consent_vals, "outcome", outcome_vals
        )

        # Calculate expected values using Polars
        total_submitted = data_pl.height
        valid_consent_count = data_pl.filter(
            pl.col("consent").is_in(consent_vals)
        ).height
        completed_count = data_pl.filter(pl.col("outcome").is_in(outcome_vals)).height

        expected_consent_percentage = (valid_consent_count / total_submitted) * 100
        expected_completion_percentage = (completed_count / total_submitted) * 100

        assert result[0] == expected_consent_percentage
        assert result[1] == expected_completion_percentage

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_chart_no_consent_col(self, sample_dataframe):
        """Test compute_progress_chart with no consent column."""
        data_pl = pl.from_pandas(sample_dataframe)
        result = compute_progress_chart(data_pl, None, ["Yes"], "outcome", ["Complete"])

        assert result[0] == 0  # consent_percentage should be 0
        assert isinstance(
            result[1], float
        )  # completion_percentage should still be calculated

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_chart_no_outcome_col(self, sample_dataframe):
        """Test compute_progress_chart with no outcome column."""
        data_pl = pl.from_pandas(sample_dataframe)
        result = compute_progress_chart(data_pl, "consent", ["Yes"], None, ["Complete"])

        assert isinstance(
            result[0], float
        )  # consent_percentage should still be calculated
        assert result[1] == 0  # completion_percentage should be 0

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_chart_empty_data(self):
        """Test compute_progress_chart with empty dataframe."""
        empty_pl = pl.DataFrame({"consent": [], "outcome": []})
        result = compute_progress_chart(
            empty_pl, "consent", ["Yes"], "outcome", ["Complete"]
        )

        assert result[0] == 0
        assert result[1] == 0


# ==============================================================================
# New Tests for Pydantic Models and Helper Functions
# ==============================================================================


class TestPydanticModels:
    """Test Pydantic models for data validation."""

    def test_progress_summary_valid(self):
        """Test creating valid ProgressSummary."""
        summary = ProgressSummary(
            total_submitted=100, target=150, percentage_completed=66.67
        )
        assert summary.total_submitted == 100
        assert summary.target == 150
        assert math.isclose(summary.percentage_completed, 66.67)

    def test_progress_summary_no_target(self):
        """Test ProgressSummary with no target."""
        summary = ProgressSummary(
            total_submitted=50, target=None, percentage_completed=0.0
        )
        assert summary.total_submitted == 50
        assert summary.target is None
        assert math.isclose(summary.percentage_completed, 0.0)

    def test_progress_chart_metrics_valid(self):
        """Test creating valid ProgressChartMetrics."""
        metrics = ProgressChartMetrics(
            consent_percentage=85.5, completion_percentage=92.3
        )
        assert math.isclose(metrics.consent_percentage, 85.5)
        assert math.isclose(metrics.completion_percentage, 92.3)

    def test_progress_chart_metrics_bounds(self):
        """Test ProgressChartMetrics percentage bounds."""
        with pytest.raises(ValidationError):
            ProgressChartMetrics(
                consent_percentage=-10.0,  # Below 0
                completion_percentage=50.0,
            )

        with pytest.raises(ValidationError):
            ProgressChartMetrics(
                consent_percentage=50.0,
                completion_percentage=105.0,  # Above 100
            )

    def test_attempted_interviews_metrics_valid(self):
        """Test creating valid AttemptedInterviewsMetrics."""
        metrics = AttemptedInterviewsMetrics(
            total_submitted=200,
            number_of_unique_ids=180,
            min_attempts=1,
            max_attempts=5,
        )
        assert metrics.total_submitted == 200
        assert metrics.number_of_unique_ids == 180
        assert metrics.min_attempts == 1
        assert metrics.max_attempts == 5

    def test_progress_settings_valid(self):
        """Test creating valid ProgressSettings."""
        settings = ProgressSettings(
            survey_key="key_col",
            survey_id="id_col",
            survey_date="date_col",
            enumerator="enum_col",
            survey_target=1000,
            target_submissions_per_period=50,
        )
        assert settings.survey_key == "key_col"
        assert settings.survey_id == "id_col"
        assert settings.survey_target == 1000

    def test_progress_settings_negative_target(self):
        """Test ProgressSettings rejects negative targets."""
        with pytest.raises(ValidationError):
            ProgressSettings(survey_key="key", survey_id="id", survey_target=-10)

    def test_time_period_config_valid(self):
        """Test creating valid TimePeriodConfig."""
        for period in ["Day", "Week", "Month"]:
            config = TimePeriodConfig(time_period=period)
            assert config.time_period == period

    def test_time_period_config_invalid(self):
        """Test TimePeriodConfig rejects invalid periods."""
        with pytest.raises(ValidationError):
            TimePeriodConfig(time_period="Year")

    def test_attempted_interviews_result_valid(self):
        """Test creating valid AttemptedInterviewsResult."""
        df = pl.DataFrame({"survey_id": ["ID1", "ID2"], "num_interviews": [1, 2]})
        result = AttemptedInterviewsResult(
            attempted_interviews=df,
            total_submitted=10,
            number_of_unique_ids=2,
            min_attempts=1,
            max_attempts=2,
        )
        assert result.total_submitted == 10
        assert result.number_of_unique_ids == 2


class TestHelperFunctions:
    """Test helper functions."""

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_get_unique_values(self):
        """Test _get_unique_values helper."""
        data = pl.DataFrame({"col1": ["A", "B", "A", "C", "B"]})
        unique_vals = _get_unique_values(data, "col1")

        assert isinstance(unique_vals, list)
        assert set(unique_vals) == {"A", "B", "C"}
        assert len(unique_vals) == 3

    def test_aggregate_attempts_by_survey_id(self):
        """Test _aggregate_attempts_by_survey_id helper."""
        import datetime

        data = pl.DataFrame(
            {
                "survey_id": ["ID1", "ID1", "ID2", "ID3"],
                "date": [
                    datetime.datetime(2024, 1, 1),
                    datetime.datetime(2024, 1, 2),
                    datetime.datetime(2024, 1, 3),
                    datetime.datetime(2024, 1, 4),
                ],
            }
        )

        result = _aggregate_attempts_by_survey_id(data, "survey_id", "date")

        assert isinstance(result, pl.DataFrame)
        assert "num_interviews" in result.columns
        assert "last_attempt_date" in result.columns
        assert "attempt_dates" in result.columns
        assert result.height == 3  # 3 unique survey IDs

    def test_expand_attempt_dates(self):
        """Test _expand_attempt_dates helper."""
        import datetime

        data = pl.DataFrame(
            {
                "survey_id": ["ID1", "ID2"],
                "num_interviews": [2, 3],
                "attempt_dates": [
                    [datetime.datetime(2024, 1, 1), datetime.datetime(2024, 1, 2)],
                    [
                        datetime.datetime(2024, 1, 3),
                        datetime.datetime(2024, 1, 4),
                        datetime.datetime(2024, 1, 5),
                    ],
                ],
            }
        )

        result = _expand_attempt_dates(data)

        assert isinstance(result, pl.DataFrame)
        assert "Attempt Date 1" in result.columns
        assert "Attempt Date 2" in result.columns
        assert "Attempt Date 3" in result.columns
        assert "attempt_dates" not in result.columns

    def test_prepare_display_columns_empty(self):
        """Test _prepare_display_columns with empty display_cols."""
        data = pl.DataFrame(
            {
                "survey_id": ["ID1", "ID2", "ID3"],
                "date": [1, 2, 3],
                "col1": ["A", "B", "C"],
            }
        )

        result = _prepare_display_columns(data, "survey_id", "date", [])

        assert isinstance(result, pl.DataFrame)
        assert "survey_id" in result.columns
        assert result.height == 3

    def test_prepare_display_columns_with_cols(self):
        """Test _prepare_display_columns with display columns."""
        data = pl.DataFrame(
            {
                "survey_id": ["ID1", "ID1", "ID2"],
                "date": [1, 2, 3],
                "enum": ["E1", None, "E2"],
                "team": [None, "T1", "T2"],
            }
        )

        result = _prepare_display_columns(data, "survey_id", "date", ["enum", "team"])

        assert isinstance(result, pl.DataFrame)
        assert "enum" in result.columns
        assert "team" in result.columns
        assert result.height == 2  # 2 unique survey IDs

    def test_compute_summary_stats(self):
        """Test _compute_summary_stats helper."""
        data = pl.DataFrame(
            {"survey_id": ["ID1", "ID2", "ID3"], "num_interviews": [1, 3, 2]}
        )

        num_unique, min_attempts, max_attempts = _compute_summary_stats(data)

        assert num_unique == 3
        assert min_attempts == 1
        assert max_attempts == 3

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_average_interviews(self):
        """Test compute_average_interviews function."""
        period_stats = pl.DataFrame(
            {
                "time_period": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "num_interviews": [10, 15, 20],
            }
        )

        avg = compute_average_interviews(period_stats)

        assert isinstance(avg, float)
        assert math.isclose(avg, 15.0)


class TestComputeProgressOvertimeUpdated:
    """Test compute_progress_overtime with new Polars API."""

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_overtime_day(self):
        """Test compute_progress_overtime with Day aggregation."""
        import datetime

        data = pl.DataFrame(
            {
                "date": [
                    datetime.datetime(2024, 1, 1),
                    datetime.datetime(2024, 1, 1),
                    datetime.datetime(2024, 1, 2),
                    datetime.datetime(2024, 1, 2),
                    datetime.datetime(2024, 1, 2),
                ]
            }
        )

        result = compute_progress_overtime(data, "date", "Day")

        assert isinstance(result, pl.DataFrame)
        assert "time_period" in result.columns
        assert "num_interviews" in result.columns
        assert result.height == 2  # 2 unique days

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_overtime_week(self):
        """Test compute_progress_overtime with Week aggregation."""
        import datetime

        data = pl.DataFrame(
            {
                "date": [
                    datetime.datetime(2024, 1, 1),
                    datetime.datetime(2024, 1, 3),
                    datetime.datetime(2024, 1, 8),
                    datetime.datetime(2024, 1, 10),
                ]
            }
        )

        result = compute_progress_overtime(data, "date", "Week")

        assert isinstance(result, pl.DataFrame)
        assert "time_period" in result.columns
        assert "num_interviews" in result.columns

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_overtime_month(self):
        """Test compute_progress_overtime with Month aggregation."""
        import datetime

        data = pl.DataFrame(
            {
                "date": [
                    datetime.datetime(2024, 1, 5),
                    datetime.datetime(2024, 1, 15),
                    datetime.datetime(2024, 2, 5),
                    datetime.datetime(2024, 2, 20),
                ]
            }
        )

        result = compute_progress_overtime(data, "date", "Month")

        assert isinstance(result, pl.DataFrame)
        assert result.height == 2  # 2 unique months

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_progress_overtime_invalid_period(self):
        """Test compute_progress_overtime rejects invalid period."""
        import datetime

        data = pl.DataFrame({"date": [datetime.datetime(2024, 1, 1)]})

        with pytest.raises(ValidationError):
            compute_progress_overtime(data, "date", "Year")


class TestComputeAttemptedInterviewsUpdated:
    """Test compute_attempted_interviews with new Polars/Pydantic API."""

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_attempted_interviews_basic(self):
        """Test compute_attempted_interviews basic functionality."""
        import datetime

        data = pl.DataFrame(
            {
                "survey_id": ["ID1", "ID1", "ID2", "ID3", "ID3", "ID3"],
                "date": [
                    datetime.datetime(2024, 1, 1),
                    datetime.datetime(2024, 1, 2),
                    datetime.datetime(2024, 1, 3),
                    datetime.datetime(2024, 1, 4),
                    datetime.datetime(2024, 1, 5),
                    datetime.datetime(2024, 1, 6),
                ],
            }
        )

        result = compute_attempted_interviews(data, "survey_id", "date", [])

        assert isinstance(result, AttemptedInterviewsResult)
        assert result.total_submitted == 6
        assert result.number_of_unique_ids == 3
        assert result.min_attempts == 1
        assert result.max_attempts == 3

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_attempted_interviews_with_display_cols(self):
        """Test compute_attempted_interviews with display columns."""
        import datetime

        data = pl.DataFrame(
            {
                "survey_id": ["ID1", "ID1", "ID2"],
                "date": [
                    datetime.datetime(2024, 1, 1),
                    datetime.datetime(2024, 1, 2),
                    datetime.datetime(2024, 1, 3),
                ],
                "enumerator": ["E1", "E1", "E2"],
                "team": ["T1", "T1", "T2"],
            }
        )

        result = compute_attempted_interviews(
            data, "survey_id", "date", ["enumerator", "team"]
        )

        assert isinstance(result, AttemptedInterviewsResult)
        assert "enumerator" in result.attempted_interviews.columns
        assert "team" in result.attempted_interviews.columns
