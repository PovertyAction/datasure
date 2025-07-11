"""Tests for the progress module."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.checks.progress import (
    compute_attempted_interviews,
    compute_progress_chart,
    compute_progress_overtime,
    compute_progress_summary,
    load_default_progress_settings,
)


class TestComputeProgressSummary:
    """Test compute_progress_summary function."""

    def test_compute_progress_summary_structure(self, sample_dataframe):
        """Test that compute_progress_summary returns expected structure."""
        result = compute_progress_summary(sample_dataframe, 10)

        assert isinstance(result, tuple)
        assert len(result) == 3
        assert isinstance(result[0], int)  # total_submitted
        assert isinstance(result[1], int)  # target
        assert isinstance(result[2], float)  # percentage_completed

    def test_compute_progress_summary_values_with_target(self, sample_dataframe):
        """Test compute_progress_summary with valid target."""
        target = 10
        result = compute_progress_summary(sample_dataframe, target)

        expected_total = len(sample_dataframe)
        expected_percentage = (expected_total / target) * 100

        assert result[0] == expected_total
        assert result[1] == target
        assert result[2] == expected_percentage

    def test_compute_progress_summary_no_target(self, sample_dataframe):
        """Test compute_progress_summary with no target."""
        result = compute_progress_summary(sample_dataframe, None)

        assert result[0] == len(sample_dataframe)
        assert result[1] is None
        assert result[2] == 0

    def test_compute_progress_summary_zero_target(self, sample_dataframe):
        """Test compute_progress_summary with zero target."""
        result = compute_progress_summary(sample_dataframe, 0)

        assert result[0] == len(sample_dataframe)
        assert result[1] == 0
        assert result[2] == 0

    def test_compute_progress_summary_empty_data(self):
        """Test compute_progress_summary with empty dataframe."""
        empty_df = pd.DataFrame()
        result = compute_progress_summary(empty_df, 10)

        assert result[0] == 0
        assert result[1] == 10
        assert result[2] == 0


class TestComputeProgressChart:
    """Test compute_progress_chart function."""

    def test_compute_progress_chart_structure(self, sample_dataframe):
        """Test that compute_progress_chart returns expected structure."""
        result = compute_progress_chart(
            sample_dataframe, "consent", ["Yes"], "outcome", ["Complete"]
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], float)  # consent_percentage
        assert isinstance(result[1], float)  # completion_percentage

    def test_compute_progress_chart_with_valid_data(self, sample_dataframe):
        """Test compute_progress_chart with valid consent and outcome data."""
        consent_vals = ["Yes"]
        outcome_vals = ["Complete"]

        result = compute_progress_chart(
            sample_dataframe, "consent", consent_vals, "outcome", outcome_vals
        )

        # Calculate expected values
        total_submitted = len(sample_dataframe)
        valid_consent_count = len(
            sample_dataframe[sample_dataframe["consent"].isin(consent_vals)]
        )
        completed_count = len(
            sample_dataframe[sample_dataframe["outcome"].isin(outcome_vals)]
        )

        expected_consent_percentage = (valid_consent_count / total_submitted) * 100
        expected_completion_percentage = (completed_count / total_submitted) * 100

        assert result[0] == expected_consent_percentage
        assert result[1] == expected_completion_percentage

    def test_compute_progress_chart_no_consent_col(self, sample_dataframe):
        """Test compute_progress_chart with no consent column."""
        result = compute_progress_chart(
            sample_dataframe, None, ["Yes"], "outcome", ["Complete"]
        )

        assert result[0] == 0  # consent_percentage should be 0
        assert isinstance(
            result[1], float
        )  # completion_percentage should still be calculated

    def test_compute_progress_chart_no_outcome_col(self, sample_dataframe):
        """Test compute_progress_chart with no outcome column."""
        result = compute_progress_chart(
            sample_dataframe, "consent", ["Yes"], None, ["Complete"]
        )

        assert isinstance(
            result[0], float
        )  # consent_percentage should still be calculated
        assert result[1] == 0  # completion_percentage should be 0

    def test_compute_progress_chart_empty_data(self):
        """Test compute_progress_chart with empty dataframe."""
        empty_df = pd.DataFrame(columns=["consent", "outcome"])
        result = compute_progress_chart(
            empty_df, "consent", ["Yes"], "outcome", ["Complete"]
        )

        assert result[0] == 0
        assert result[1] == 0


class TestComputeProgressOvertime:
    """Test compute_progress_overtime function."""

    @pytest.fixture
    def datetime_data(self):
        """Create sample data with datetime column for testing."""
        dates = pd.date_range("2024-01-01", "2024-01-10", freq="D")
        return pd.DataFrame({"submission_date": dates, "survey_id": range(1, 11)})

    def test_compute_progress_overtime_structure(self, datetime_data):
        """Test that compute_progress_overtime returns expected structure."""
        result = compute_progress_overtime(datetime_data, "submission_date", "Day")

        assert isinstance(result, tuple)
        assert len(result) == 2
        assert isinstance(result[0], pd.DataFrame)  # period_stats
        assert isinstance(result[1], float)  # average_interviews

    def test_compute_progress_overtime_daily(self, datetime_data):
        """Test compute_progress_overtime with daily period."""
        result = compute_progress_overtime(datetime_data, "submission_date", "Day")

        period_stats, average_interviews = result

        # Should have one entry per day
        assert len(period_stats) == 10
        assert "time_period" in period_stats.columns
        assert "num_interviews" in period_stats.columns
        assert period_stats["num_interviews"].sum() == len(datetime_data)
        assert average_interviews == 1.0  # One interview per day

    def test_compute_progress_overtime_weekly(self, datetime_data):
        """Test compute_progress_overtime with weekly period."""
        result = compute_progress_overtime(datetime_data, "submission_date", "Week")

        period_stats, average_interviews = result

        # Should group by weeks
        assert len(period_stats) > 0
        assert "time_period" in period_stats.columns
        assert "num_interviews" in period_stats.columns
        assert period_stats["num_interviews"].sum() == len(datetime_data)

    def test_compute_progress_overtime_monthly(self, datetime_data):
        """Test compute_progress_overtime with monthly period."""
        result = compute_progress_overtime(datetime_data, "submission_date", "Month")

        period_stats, average_interviews = result

        # Should group by months
        assert len(period_stats) > 0
        assert "time_period" in period_stats.columns
        assert "num_interviews" in period_stats.columns
        assert period_stats["num_interviews"].sum() == len(datetime_data)


class TestComputeAttemptedInterviews:
    """Test compute_attempted_interviews function."""

    @pytest.fixture
    def attempted_data(self):
        """Create sample data with multiple attempts for testing."""
        return pd.DataFrame(
            {
                "survey_id": ["ID001", "ID001", "ID001", "ID002", "ID002", "ID003"],
                "submission_date": pd.to_datetime(
                    [
                        "2024-01-01",
                        "2024-01-02",
                        "2024-01-03",
                        "2024-01-01",
                        "2024-01-02",
                        "2024-01-01",
                    ]
                ),
                "enumerator": ["E1", "E1", "E1", "E2", "E2", "E3"],
                "district": [
                    "District A",
                    "District A",
                    "District A",
                    "District B",
                    "District B",
                    "District C",
                ],
            }
        )

    def test_compute_attempted_interviews_structure(self, attempted_data):
        """Test that compute_attempted_interviews returns expected structure."""
        result = compute_attempted_interviews(
            attempted_data, "survey_id", "submission_date", ["enumerator", "district"]
        )

        assert isinstance(result, tuple)
        assert len(result) == 5
        assert isinstance(result[0], pd.DataFrame)  # attempted_interviews
        assert isinstance(result[1], int | np.int32 | np.int64)  # total_submitted
        assert isinstance(result[2], int | np.int32 | np.int64)  # number_of_unique_ids
        assert isinstance(result[3], int | np.int32 | np.int64)  # min_attempts
        assert isinstance(result[4], int | np.int32 | np.int64)  # max_attempts

    def test_compute_attempted_interviews_values(self, attempted_data):
        """Test compute_attempted_interviews calculation values."""
        display_cols = ["enumerator", "district"]
        result = compute_attempted_interviews(
            attempted_data, "survey_id", "submission_date", display_cols
        )

        (
            attempted_interviews,
            total_submitted,
            number_of_unique_ids,
            min_attempts,
            max_attempts,
        ) = result

        # Check aggregate statistics
        assert total_submitted == 6
        assert number_of_unique_ids == 3
        assert min_attempts == 1  # ID003 has 1 attempt
        assert max_attempts == 3  # ID001 has 3 attempts

        # Check dataframe structure
        expected_cols = [
            "survey_id",
            "num_interviews",
            "last_attempt_date",
        ] + display_cols
        for col in expected_cols:
            assert col in attempted_interviews.columns

        # Check specific values
        id001_row = attempted_interviews[
            attempted_interviews["survey_id"] == "ID001"
        ].iloc[0]
        assert id001_row["num_interviews"] == 3
        assert id001_row["enumerator"] == "E1"
        assert id001_row["district"] == "District A"

    def test_compute_attempted_interviews_single_attempt(self):
        """Test compute_attempted_interviews with single attempts only."""
        single_attempt_data = pd.DataFrame(
            {
                "survey_id": ["ID001", "ID002", "ID003"],
                "submission_date": pd.to_datetime(
                    ["2024-01-01", "2024-01-02", "2024-01-03"]
                ),
                "enumerator": ["E1", "E2", "E3"],
            }
        )

        result = compute_attempted_interviews(
            single_attempt_data, "survey_id", "submission_date", ["enumerator"]
        )

        (
            attempted_interviews,
            total_submitted,
            number_of_unique_ids,
            min_attempts,
            max_attempts,
        ) = result

        assert total_submitted == 3
        assert number_of_unique_ids == 3
        assert min_attempts == 1
        assert max_attempts == 1
        assert len(attempted_interviews) == 3

    def test_compute_attempted_interviews_empty_display_cols(self, attempted_data):
        """Test compute_attempted_interviews with empty display columns."""
        result = compute_attempted_interviews(
            attempted_data, "survey_id", "submission_date", []
        )

        attempted_interviews = result[0]
        basic_cols = ["survey_id", "num_interviews", "last_attempt_date"]

        # Should still have basic columns
        for col in basic_cols:
            assert col in attempted_interviews.columns


class TestLoadDefaultProgressSettings:
    """Test load_default_progress_settings function."""

    @patch("src.checks.progress.get_check_config_settings")
    @patch("src.checks.progress.load_check_settings")
    @patch("os.path.exists")
    def test_load_default_progress_settings_with_existing_file(
        self, mock_exists, mock_load_settings, mock_get_config
    ):
        """Test loading settings when settings file exists."""
        # Mock return values
        mock_exists.return_value = True
        mock_get_config.return_value = (
            "v1",
            "project",
            "form",
            "survey_id",
            "date_col",
            "enum_col",
            "consent",
            "outcome",
        )
        mock_load_settings.return_value = {
            "survey_id": "custom_survey_id",
            "enumerator": "custom_enum",
            "date": "custom_date",
            "target": 100,
        }

        result = load_default_progress_settings("test_project", "settings.json", 1)

        assert len(result) == 4
        assert result[0] == "custom_survey_id"  # survey_id
        assert result[1] == "custom_enum"  # enumerator
        assert result[2] == "custom_date"  # date
        assert result[3] == 100  # target

    @patch("src.checks.progress.get_check_config_settings")
    @patch("src.checks.progress.load_check_settings")
    @patch("os.path.exists")
    def test_load_default_progress_settings_no_file(
        self, mock_exists, mock_load_settings, mock_get_config
    ):
        """Test loading settings when settings file doesn't exist."""
        # Mock return values
        mock_exists.return_value = False
        mock_get_config.return_value = (
            "v1",
            "project",
            "form",
            "survey_id",
            "date_col",
            "enum_col",
            "consent",
            "outcome",
        )
        mock_load_settings.return_value = {}

        result = load_default_progress_settings("test_project", "settings.json", 1)

        assert len(result) == 4
        assert result[0] == "survey_id"  # survey_id from config
        assert result[1] == "enum_col"  # enumerator from config
        assert result[2] == "date_col"  # date from config
        assert result[3] is None  # target should be None

    @patch("src.checks.progress.get_check_config_settings")
    @patch("src.checks.progress.load_check_settings")
    @patch("os.path.exists")
    def test_load_default_progress_settings_fallback_target(
        self, mock_exists, mock_load_settings, mock_get_config
    ):
        """Test loading settings with fallback target from summary settings."""
        # Mock return values
        mock_exists.return_value = True
        mock_get_config.return_value = (
            "v1",
            "project",
            "form",
            "survey_id",
            "date_col",
            "enum_col",
            "consent",
            "outcome",
        )

        # Mock load_check_settings to return different values for different calls
        def mock_load_side_effect(file_path, check_name):
            if check_name == "progress":
                return {
                    "survey_id": "survey_id",
                    "enumerator": "enum_col",
                    "date": "date_col",
                    "target": 300,  # No target in progress settings
                }
            elif check_name == "summary":
                return {"target": 500}  # Target available in summary settings
            return {}

        mock_load_settings.side_effect = mock_load_side_effect

        result = load_default_progress_settings("test_project", "settings.json", 1)

        assert result[3] == 300  # Should get target from summary settings


class TestIntegration:
    """Integration tests for progress functions."""

    def test_progress_workflow(self, sample_dataframe):
        """Test complete progress workflow with sample data."""
        # Test progress summary
        target = 10
        summary_result = compute_progress_summary(sample_dataframe, target)
        assert len(summary_result) == 3

        # Test progress chart
        chart_result = compute_progress_chart(
            sample_dataframe, "consent", ["Yes"], "outcome", ["Complete"]
        )
        assert len(chart_result) == 2

        # Test attempted interviews
        attempted_result = compute_attempted_interviews(
            sample_dataframe, "id", "submission_date", ["enumid", "team"]
        )
        assert len(attempted_result) == 5

    def test_edge_cases_empty_data(self):
        """Test all functions with empty data."""
        empty_df = pd.DataFrame()

        # Progress summary with empty data
        summary_result = compute_progress_summary(empty_df, 10)
        assert summary_result == (0, 10, 0)

        # Progress chart with empty data
        chart_result = compute_progress_chart(empty_df, None, None, None, None)
        assert chart_result == (0, 0)
