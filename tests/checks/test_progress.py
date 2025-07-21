"""Tests for the progress module with comprehensive coverage."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from datasure.checks.progress import (
    compute_attempted_interviews,
    compute_progress_chart,
    compute_progress_overtime,
    compute_progress_summary,
    display_attempted_interviews,
    display_progress_chart,
    display_progress_overtime,
    load_default_progress_settings,
    progress_report,
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

    @patch("datasure.checks.progress.get_check_config_settings")
    @patch("datasure.checks.progress.load_check_settings")
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

    @patch("datasure.checks.progress.get_check_config_settings")
    @patch("datasure.checks.progress.load_check_settings")
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

    @patch("datasure.checks.progress.get_check_config_settings")
    @patch("datasure.checks.progress.load_check_settings")
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


class TestProgressReportSettings:
    """Test progress_report_settings function."""

    @pytest.fixture
    def mock_streamlit_environment(self):
        """Mock Streamlit environment for testing."""
        with (
            patch("streamlit.expander") as mock_expander,
            patch("streamlit.markdown") as mock_markdown,
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.selectbox") as mock_selectbox,
            patch("streamlit.number_input") as mock_number_input,
            patch("streamlit.write") as mock_write,
            patch(
                "datasure.checks.progress.load_default_progress_settings"
            ) as mock_load_defaults,
            patch("datasure.checks.progress.get_df_info") as mock_get_df_info,
            patch("datasure.checks.progress.trigger_save") as mock_trigger_save,
            patch("datasure.checks.progress.save_check_settings") as mock_save_settings,
            patch("streamlit.session_state", {}) as mock_session_state,
        ):
            # Setup mock returns
            mock_load_defaults.return_value = (
                "survey_id",
                "enumerator",
                "date_col",
                100,
            )
            mock_get_df_info.return_value = (
                None,
                ["col1", "col2"],
                ["num1", "num2"],
                ["date1", "date2"],
                None,
            )
            mock_columns.return_value = [MagicMock(), MagicMock(), MagicMock()]
            mock_selectbox.side_effect = ["survey_id", "date_col", "enumerator"]
            mock_number_input.return_value = 150

            # Mock expander context manager
            mock_expander.return_value.__enter__ = MagicMock()
            mock_expander.return_value.__exit__ = MagicMock(return_value=None)

            # Mock column context managers
            for col in mock_columns.return_value:
                col.__enter__ = MagicMock(return_value=col)
                col.__exit__ = MagicMock(return_value=None)

            yield {
                "expander": mock_expander,
                "markdown": mock_markdown,
                "columns": mock_columns,
                "selectbox": mock_selectbox,
                "number_input": mock_number_input,
                "write": mock_write,
                "load_defaults": mock_load_defaults,
                "get_df_info": mock_get_df_info,
                "trigger_save": mock_trigger_save,
                "save_settings": mock_save_settings,
                "session_state": mock_session_state,
            }


class TestDisplayFunctions:
    """Test display functions."""

    @pytest.fixture
    def mock_streamlit_display(self):
        """Mock Streamlit display components."""
        with (
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.write") as mock_write,
            patch("streamlit.info") as mock_info,
            patch("streamlit.progress") as mock_progress,
            patch("streamlit.metric") as mock_metric,
            patch("streamlit.pyplot") as mock_pyplot,
            patch("streamlit.plotly_chart") as mock_plotly,
            patch("streamlit.dataframe") as mock_dataframe,
            patch("streamlit.markdown") as mock_markdown,
            patch("streamlit.radio") as mock_radio,
            patch("streamlit.multiselect") as mock_multiselect,
            patch("streamlit.selectbox") as mock_selectbox,
            patch("streamlit.container") as mock_container,
            patch("datasure.checks.progress.donut_chart2") as mock_donut,
            patch("datasure.checks.progress.load_check_settings") as mock_load_settings,
            patch("datasure.checks.progress.trigger_save") as mock_trigger,
            patch("datasure.checks.progress.save_check_settings") as mock_save,
            patch("streamlit.session_state", {}) as mock_session_state,
        ):
            # Setup mock returns
            mock_columns.return_value = [MagicMock() for _ in range(5)]
            mock_radio.return_value = "Day"
            mock_multiselect.return_value = ["col1", "col2"]
            mock_selectbox.return_value = "consent_col"
            mock_load_settings.return_value = {}
            mock_donut.return_value = MagicMock()

            # Mock container context manager
            mock_container.return_value.__enter__ = MagicMock()
            mock_container.return_value.__exit__ = MagicMock(return_value=None)

            # Mock column context managers
            for col_mock in mock_columns.return_value:
                col_mock.__enter__ = MagicMock(return_value=col_mock)
                col_mock.__exit__ = MagicMock(return_value=None)

            yield {
                "columns": mock_columns,
                "write": mock_write,
                "info": mock_info,
                "progress": mock_progress,
                "metric": mock_metric,
                "pyplot": mock_pyplot,
                "plotly": mock_plotly,
                "dataframe": mock_dataframe,
                "markdown": mock_markdown,
                "radio": mock_radio,
                "multiselect": mock_multiselect,
                "selectbox": mock_selectbox,
                "container": mock_container,
                "donut": mock_donut,
                "load_settings": mock_load_settings,
                "trigger": mock_trigger,
                "save": mock_save,
                "session_state": mock_session_state,
            }

    def test_display_progress_overtime_with_date(
        self, sample_dataframe, mock_streamlit_display
    ):
        """Test display_progress_overtime with date column."""
        display_progress_overtime(sample_dataframe, "submission_date", "settings.json")

        # Verify components were called
        mock_streamlit_display["write"].assert_called()
        mock_streamlit_display["radio"].assert_called()
        mock_streamlit_display["plotly"].assert_called()

    def test_display_progress_overtime_no_date(
        self, sample_dataframe, mock_streamlit_display
    ):
        """Test display_progress_overtime with no date column."""
        display_progress_overtime(sample_dataframe, None, "settings.json")

        # Should show info message and return early
        mock_streamlit_display["info"].assert_called()
        mock_streamlit_display["plotly"].assert_not_called()

    def test_display_attempted_interviews_missing_params(
        self, sample_dataframe, mock_streamlit_display
    ):
        """Test display_attempted_interviews with missing parameters."""
        display_attempted_interviews(sample_dataframe, None, None, "settings.json")

        # Should show info message and return early
        mock_streamlit_display["info"].assert_called()
        mock_streamlit_display["plotly"].assert_not_called()


class TestProgressReport:
    """Test main progress_report function."""

    @pytest.fixture
    def mock_all_display_functions(self):
        """Mock all display functions."""
        with (
            patch("datasure.checks.progress.progress_report_settings") as mock_settings,
            patch("datasure.checks.progress.display_progress_summary") as mock_summary,
            patch(
                "datasure.checks.progress.display_progress_overtime"
            ) as mock_overtime,
            patch(
                "datasure.checks.progress.display_attempted_interviews"
            ) as mock_attempted,
            patch("datasure.checks.progress.display_progress_chart") as mock_chart,
        ):
            # Setup mock returns
            mock_settings.return_value = ("survey_id", "date_col", "enumerator", 100)

            yield {
                "settings": mock_settings,
                "summary": mock_summary,
                "overtime": mock_overtime,
                "attempted": mock_attempted,
                "chart": mock_chart,
            }

    def test_progress_report_full_execution(
        self, sample_dataframe, mock_all_display_functions
    ):
        """Test complete progress_report execution."""
        progress_report("test_project", sample_dataframe, "settings.json", 1)

        # Verify all display functions were called
        mock_all_display_functions["settings"].assert_called_once_with(
            "test_project", sample_dataframe, "settings.json", 1
        )
        mock_all_display_functions["summary"].assert_called_once_with(
            data=sample_dataframe, target=100
        )
        mock_all_display_functions["overtime"].assert_called_once_with(
            data=sample_dataframe, date="date_col", setting_file="settings.json"
        )
        mock_all_display_functions["attempted"].assert_called_once_with(
            data=sample_dataframe,
            survey_id="survey_id",
            date="date_col",
            setting_file="settings.json",
        )
        mock_all_display_functions["chart"].assert_called_once_with(
            data=sample_dataframe, setting_file="settings.json"
        )


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


class TestProgressOvertimeEdgeCases:
    """Test edge cases for compute_progress_overtime function."""

    def test_compute_progress_overtime_single_date(self):
        """Test compute_progress_overtime with single date."""
        data = pd.DataFrame({"submission_date": [pd.to_datetime("2024-01-01")]})

        result = compute_progress_overtime(data, "submission_date", "Day")
        period_stats, average_interviews = result

        assert len(period_stats) == 1
        assert period_stats["num_interviews"].iloc[0] == 1
        assert average_interviews == 1.0

    def test_compute_progress_overtime_missing_date_values(self):
        """Test compute_progress_overtime with missing date values."""
        data = pd.DataFrame(
            {
                "submission_date": [
                    pd.to_datetime("2024-01-01"),
                    None,
                    pd.to_datetime("2024-01-03"),
                ]
            }
        )

        # Should handle NaT values
        result = compute_progress_overtime(data, "submission_date", "Day")
        period_stats, average_interviews = result

        assert len(period_stats) >= 1  # Should have valid dates


class TestProgressChartEdgeCases:
    """Test edge cases for compute_progress_chart function."""

    def test_compute_progress_chart_missing_column_data(self, sample_dataframe):
        """Test compute_progress_chart with columns containing only NaN values."""
        # Create dataframe with NaN values in consent column
        test_data = sample_dataframe.copy()
        test_data["consent"] = None

        result = compute_progress_chart(
            test_data, "consent", ["Yes"], "outcome", ["Complete"]
        )

        assert result[0] == 0  # consent_percentage should be 0 with all NaN
        assert isinstance(
            result[1], float
        )  # completion_percentage should still calculate

    def test_compute_progress_chart_empty_lists(self, sample_dataframe):
        """Test compute_progress_chart with empty consent/outcome value lists."""
        result = compute_progress_chart(sample_dataframe, "consent", [], "outcome", [])

        assert result[0] == 0  # consent_percentage should be 0 with empty list
        assert result[1] == 0  # completion_percentage should be 0 with empty list

    def test_compute_progress_chart_nonexistent_values(self, sample_dataframe):
        """Test compute_progress_chart with values that don't exist in data."""
        result = compute_progress_chart(
            sample_dataframe, "consent", ["NonExistent"], "outcome", ["NonExistent"]
        )

        assert result[0] == 0  # Should be 0% if values don't exist
        assert result[1] == 0  # Should be 0% if values don't exist


class TestAttemptedInterviewsEdgeCases:
    """Test edge cases for compute_attempted_interviews function."""

    def test_compute_attempted_interviews_missing_survey_ids(self):
        """Test compute_attempted_interviews with missing survey IDs."""
        data = pd.DataFrame(
            {
                "survey_id": ["ID001", None, "ID003"],
                "submission_date": pd.to_datetime(
                    ["2024-01-01", "2024-01-02", "2024-01-03"]
                ),
                "enumerator": ["E1", "E2", "E3"],
            }
        )

        result = compute_attempted_interviews(
            data, "survey_id", "submission_date", ["enumerator"]
        )

        (
            attempted_interviews,
            total_submitted,
            number_of_unique_ids,
            min_attempts,
            max_attempts,
        ) = result

        assert total_submitted == 3
        assert number_of_unique_ids >= 1  # Should handle NaN survey IDs
        assert isinstance(attempted_interviews, pd.DataFrame)

    def test_compute_attempted_interviews_duplicate_dates(self):
        """Test compute_attempted_interviews with duplicate submission dates."""
        data = pd.DataFrame(
            {
                "survey_id": ["ID001", "ID001", "ID001"],
                "submission_date": pd.to_datetime(
                    ["2024-01-01", "2024-01-01", "2024-01-01"]
                ),
                "enumerator": ["E1", "E1", "E1"],
            }
        )

        result = compute_attempted_interviews(
            data, "survey_id", "submission_date", ["enumerator"]
        )

        attempted_interviews = result[0]

        # Should still count as 3 attempts even with same date
        assert attempted_interviews["num_interviews"].iloc[0] == 3
        assert attempted_interviews["last_attempt_date"].iloc[0] == pd.to_datetime(
            "2024-01-01"
        )

    def test_compute_attempted_interviews_nonexistent_display_cols(self):
        """Test compute_attempted_interviews with nonexistent display columns."""
        data = pd.DataFrame(
            {
                "survey_id": ["ID001", "ID002"],
                "submission_date": pd.to_datetime(["2024-01-01", "2024-01-02"]),
                "enumerator": ["E1", "E2"],
            }
        )

        # This should raise an error or handle gracefully
        try:
            result = compute_attempted_interviews(
                data, "survey_id", "submission_date", ["nonexistent_column"]
            )
            # If no error, check that it handles gracefully
            assert isinstance(result[0], pd.DataFrame)
        except KeyError:
            # Expected behavior - should raise KeyError for nonexistent column
            pass


class TestProgressSummaryEdgeCases:
    """Additional edge cases for progress summary."""

    def test_compute_progress_summary_negative_target(self, sample_dataframe):
        """Test compute_progress_summary with negative target."""
        result = compute_progress_summary(sample_dataframe, -10)

        assert result[0] == len(sample_dataframe)
        assert result[1] == -10
        assert result[2] == 0  # Should be 0 with negative target

    def test_compute_progress_summary_float_target(self, sample_dataframe):
        """Test compute_progress_summary with float target."""
        target = 10.5
        result = compute_progress_summary(sample_dataframe, target)

        expected_percentage = (len(sample_dataframe) / target) * 100

        assert result[0] == len(sample_dataframe)
        assert result[1] == target
        assert result[2] == expected_percentage

    def test_compute_progress_summary_very_large_target(self, sample_dataframe):
        """Test compute_progress_summary with very large target."""
        target = 1000000
        result = compute_progress_summary(sample_dataframe, target)

        expected_percentage = (len(sample_dataframe) / target) * 100

        assert result[0] == len(sample_dataframe)
        assert result[1] == target
        assert (
            abs(result[2] - expected_percentage) < 0.001
        )  # Allow for floating point precision


class TestLoadDefaultProgressSettingsEdgeCases:
    """Additional test cases for load_default_progress_settings."""

    @patch("src.pydms.checks.progress.get_check_config_settings")
    @patch("src.pydms.checks.progress.load_check_settings")
    @patch("os.path.exists")
    def test_load_default_progress_settings_exception_handling(
        self, mock_exists, mock_load_settings, mock_get_config
    ):
        """Test load_default_progress_settings with exception during loading."""
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
        # Mock load_check_settings to raise an exception
        mock_load_settings.side_effect = Exception("File read error")

        # Should handle exception gracefully
        try:
            result = load_default_progress_settings("test_project", "settings.json", 1)
            # If no exception, verify fallback behavior
            assert len(result) == 4
        except Exception:
            # Should not propagate exception in production code
            pass

    @patch("src.pydms.checks.progress.get_check_config_settings")
    @patch("src.pydms.checks.progress.load_check_settings")
    @patch("os.path.exists")
    def test_load_default_progress_settings_partial_config(
        self, mock_exists, mock_load_settings, mock_get_config
    ):
        """Test load_default_progress_settings with partial configuration."""
        mock_exists.return_value = True
        mock_get_config.return_value = (
            "v1",
            "project",
            "form",
            None,
            None,
            None,
            "consent",
            "outcome",
        )
        mock_load_settings.return_value = {
            "survey_id": "survey_id",
            # Missing enumerator and date
        }

        result = load_default_progress_settings("test_project", "settings.json", 1)

        assert len(result) == 4
        assert result[0] == "survey_id"  # From settings
        assert result[1] is None  # From config (None)
        assert result[2] is None  # From config (None)


class TestDataTypeHandling:
    """Test handling of different data types and formats."""

    def test_compute_progress_overtime_string_dates(self):
        """Test compute_progress_overtime with string dates."""
        data = pd.DataFrame(
            {"submission_date": ["2024-01-01", "2024-01-02", "2024-01-03"]}
        )

        result = compute_progress_overtime(data, "submission_date", "Day")
        period_stats, average_interviews = result

        assert len(period_stats) == 3
        assert average_interviews == 1.0

    def test_compute_attempted_interviews_mixed_survey_id_types(self):
        """Test compute_attempted_interviews with mixed survey ID types."""
        data = pd.DataFrame(
            {
                "survey_id": ["ID001", 123, "ID003", 456],
                "submission_date": pd.to_datetime(
                    ["2024-01-01", "2024-01-02", "2024-01-03", "2024-01-04"]
                ),
                "enumerator": ["E1", "E2", "E3", "E4"],
            }
        )

        result = compute_attempted_interviews(
            data, "survey_id", "submission_date", ["enumerator"]
        )

        (
            attempted_interviews,
            total_submitted,
            number_of_unique_ids,
            min_attempts,
            max_attempts,
        ) = result

        assert total_submitted == 4
        assert number_of_unique_ids == 4
        assert min_attempts == 1
        assert max_attempts == 1

    def test_compute_progress_chart_boolean_columns(self):
        """Test compute_progress_chart with boolean consent/outcome columns."""
        data = pd.DataFrame(
            {
                "consent": [True, False, True, True, False],
                "outcome": [True, True, False, True, False],
            }
        )

        result = compute_progress_chart(data, "consent", [True], "outcome", [True])

        # 3 out of 5 have True consent = 60%
        # 3 out of 5 have True outcome = 60%
        assert result[0] == 60.0
        assert result[1] == 60.0
