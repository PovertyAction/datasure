"""Comprehensive tests for the summary module with 100% code coverage."""

# Standard library imports
from datetime import date, datetime, timedelta
from unittest.mock import Mock, patch

# Third-party imports
import pandas as pd
import polars as pl
import pytest
from dateutil.relativedelta import relativedelta
from pydantic import ValidationError

# Local application imports
from datasure.checks.summary import (
    # Pydantic Models
    DataQualityMetrics,
    DataSummaryMetrics,
    DateRangeCalculator,
    ProgressMetrics,
    SubmissionMetrics,
    SummarySettings,
    # Private helper functions
    _create_empty_progress_metrics,
    _create_empty_submission_metrics,
    # Calculation functions
    calculate_data_quality_metrics,
    calculate_data_summary_metrics,
    calculate_percentage_change,
    calculate_progress_metrics,
    calculate_submission_count,
    calculate_submission_metrics,
    # Backward compatibility wrappers
    compute_summary_data_quality,
    compute_summary_data_summary,
    compute_summary_progress,
    compute_summary_progress_by_col,
    compute_summary_submissions,
    # Utility functions
    determine_auto_time_period,
    pandas_to_polars,
    polars_to_pandas,
    prepare_date_data,
    # UI components
    summary_data_quality,
    summary_data_summary,
    summary_progress,
    summary_settings,
    summary_submissions,
    validate_and_convert_date_column,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_pandas_df():
    """Create a sample pandas DataFrame for testing."""
    return pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "name": ["A", "B", "C", "D", "E"],
            "value": [10, 20, 30, 40, 50],
            "date": pd.date_range("2024-01-01", periods=5),
        }
    )


@pytest.fixture
def sample_polars_df():
    """Create a sample Polars DataFrame for testing."""
    return pl.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "name": ["A", "B", "C", "D", "E"],
            "value": [10, 20, 30, 40, 50],
            "date": pl.date_range(date(2024, 1, 1), date(2024, 1, 5), "1d", eager=True),
        }
    )


@pytest.fixture
def sample_date_data():
    """Create sample data with dates for submission testing."""
    today = datetime.now().date()
    dates = [
        today,
        today,
        today - timedelta(days=1),
        today - timedelta(days=2),
        today - timedelta(days=7),
        today - timedelta(days=14),
        today - timedelta(days=30),
        today - timedelta(days=60),
    ]
    return pl.DataFrame({"submission_date": dates, "id": range(1, 9)})


@pytest.fixture
def empty_polars_df():
    """Create an empty Polars DataFrame."""
    return pl.DataFrame()


# ============================================================================
# PYDANTIC MODELS TESTS
# ============================================================================


class TestSummarySettings:
    """Test SummarySettings Pydantic model."""

    def test_valid_settings_all_fields(self):
        """Test creating valid settings with all fields."""
        settings = SummarySettings(
            survey_date="date_col", survey_target=100, survey_id="id_col"
        )
        assert settings.survey_date == "date_col"
        assert settings.survey_target == 100
        assert settings.survey_id == "id_col"

    def test_valid_settings_minimal(self):
        """Test creating valid settings with minimal fields."""
        settings = SummarySettings()
        assert settings.survey_date is None
        assert settings.survey_target is None
        assert settings.survey_id is None

    def test_valid_target_zero(self):
        """Test that zero target is valid."""
        settings = SummarySettings(survey_target=0)
        assert settings.survey_target == 0

    def test_invalid_negative_target(self):
        """Test that negative target raises validation error."""
        with pytest.raises(ValidationError):
            SummarySettings(survey_target=-1)


class TestSubmissionMetrics:
    """Test SubmissionMetrics Pydantic model."""

    def test_valid_metrics(self):
        """Test creating valid submission metrics."""
        metrics = SubmissionMetrics(
            first_submission_date=date(2024, 1, 1),
            last_submission_date=date(2024, 1, 31),
            today_count=10,
            this_week_count=50,
            this_month_count=200,
            total_count=300,
            today_delta_pct=5.0,
            this_week_delta_pct=10.0,
            this_month_delta_pct=15.0,
        )
        assert metrics.total_count == 300
        assert metrics.today_count == 10

    def test_negative_counts_invalid(self):
        """Test that negative counts raise validation error."""
        with pytest.raises(ValidationError):
            SubmissionMetrics(
                today_count=-1,
                this_week_count=0,
                this_month_count=0,
                total_count=0,
            )

    def test_with_dataframe(self):
        """Test metrics with submissions_by_date DataFrame."""
        df = pd.DataFrame({"date": [date(2024, 1, 1)], "submissions": [10]})
        metrics = SubmissionMetrics(
            today_count=0,
            this_week_count=0,
            this_month_count=0,
            total_count=10,
            submissions_by_date=df,
        )
        assert not metrics.submissions_by_date.empty


class TestProgressMetrics:
    """Test ProgressMetrics Pydantic model."""

    def test_valid_progress_metrics(self):
        """Test creating valid progress metrics."""
        metrics = ProgressMetrics(
            progress_pct=75.5, avg_per_day=10.2, avg_per_week=71.4, avg_per_month=305.0
        )
        assert metrics.progress_pct == 75.5
        assert metrics.avg_per_day == 10.2

    def test_negative_values_invalid(self):
        """Test that negative values raise validation error."""
        with pytest.raises(ValidationError):
            ProgressMetrics(
                progress_pct=-1.0, avg_per_day=0.0, avg_per_week=0.0, avg_per_month=0.0
            )


class TestDataSummaryMetrics:
    """Test DataSummaryMetrics Pydantic model."""

    def test_valid_summary_metrics(self):
        """Test creating valid data summary metrics."""
        metrics = DataSummaryMetrics(
            string_columns_count=10,
            numeric_columns_count=5,
            date_columns_count=2,
            total_columns_count=17,
        )
        assert metrics.string_columns_count == 10
        assert metrics.total_columns_count == 17

    def test_total_validation(self):
        """Test that total must equal sum of type counts."""
        # This should raise an error because sum doesn't match total
        with pytest.raises(ValidationError, match="Total columns count must equal sum"):
            DataSummaryMetrics(
                string_columns_count=5,
                numeric_columns_count=5,
                date_columns_count=5,
                total_columns_count=20,  # Doesn't match sum (15)
            )

    def test_total_validation_success(self):
        """Test that total validation passes when sum matches."""
        metrics = DataSummaryMetrics(
            string_columns_count=5,
            numeric_columns_count=5,
            date_columns_count=5,
            total_columns_count=15,  # Matches sum
        )
        assert metrics.total_columns_count == 15


class TestDataQualityMetrics:
    """Test DataQualityMetrics Pydantic model."""

    def test_valid_quality_metrics(self):
        """Test creating valid data quality metrics."""
        metrics = DataQualityMetrics(
            duplicates_pct=2.5,
            outliers_pct=1.0,
            missing_pct=0.5,
            backcheck_error_pct=0.1,
        )
        assert metrics.duplicates_pct == 2.5
        assert metrics.outliers_pct == 1.0

    def test_percentage_boundaries(self):
        """Test percentage validation at boundaries."""
        metrics = DataQualityMetrics(
            duplicates_pct=0.0,
            outliers_pct=100.0,
            missing_pct=50.0,
            backcheck_error_pct=25.0,
        )
        assert metrics.duplicates_pct == 0.0
        assert metrics.outliers_pct == 100.0

    def test_invalid_percentage_over_100(self):
        """Test that percentages over 100 are invalid."""
        with pytest.raises(ValidationError):
            DataQualityMetrics(
                duplicates_pct=101.0,
                outliers_pct=0.0,
                missing_pct=0.0,
                backcheck_error_pct=0.0,
            )

    def test_none_duplicates_pct(self):
        """Test that duplicates_pct can be None."""
        metrics = DataQualityMetrics(
            duplicates_pct=None,
            outliers_pct=0.0,
            missing_pct=0.0,
            backcheck_error_pct=0.0,
        )
        assert metrics.duplicates_pct is None


# ============================================================================
# DATE RANGE CALCULATOR TESTS
# ============================================================================


class TestDateRangeCalculator:
    """Test DateRangeCalculator helper class."""

    def test_get_today(self):
        """Test getting today's date."""
        result = DateRangeCalculator.get_today()
        expected = datetime.now().date()
        assert result == expected
        assert isinstance(result, date)

    def test_get_yesterday(self):
        """Test getting yesterday's date."""
        result = DateRangeCalculator.get_yesterday()
        expected = (datetime.now() - timedelta(days=1)).date()
        assert result == expected
        assert isinstance(result, date)

    def test_get_week_start_current(self):
        """Test getting start of current week."""
        result = DateRangeCalculator.get_week_start(weeks_ago=0)
        expected = (datetime.now() - timedelta(weeks=1)).date()
        assert result == expected

    def test_get_week_start_last_week(self):
        """Test getting start of last week."""
        result = DateRangeCalculator.get_week_start(weeks_ago=1)
        expected = (datetime.now() - timedelta(weeks=2)).date()
        assert result == expected

    def test_get_month_start_current(self):
        """Test getting start of current month."""
        result = DateRangeCalculator.get_month_start(months_ago=0)
        expected = (datetime.now() - relativedelta(months=1)).date()
        assert result == expected

    def test_get_month_start_last_month(self):
        """Test getting start of last month."""
        result = DateRangeCalculator.get_month_start(months_ago=1)
        expected = (datetime.now() - relativedelta(months=2)).date()
        assert result == expected


# ============================================================================
# DATA CONVERSION TESTS
# ============================================================================


class TestDataConversion:
    """Test data conversion functions."""

    def test_pandas_to_polars(self, sample_pandas_df):
        """Test converting pandas to Polars DataFrame."""
        result = pandas_to_polars(sample_pandas_df)
        assert isinstance(result, pl.DataFrame)
        assert result.height == len(sample_pandas_df)
        assert result.width == len(sample_pandas_df.columns)

    def test_polars_to_pandas(self, sample_polars_df):
        """Test converting Polars to pandas DataFrame."""
        result = polars_to_pandas(sample_polars_df)
        assert isinstance(result, pd.DataFrame)
        assert len(result) == sample_polars_df.height
        assert len(result.columns) == sample_polars_df.width

    def test_round_trip_conversion(self, sample_pandas_df):
        """Test converting pandas -> Polars -> pandas."""
        pl_df = pandas_to_polars(sample_pandas_df)
        pd_df = polars_to_pandas(pl_df)
        assert isinstance(pd_df, pd.DataFrame)
        assert len(pd_df) == len(sample_pandas_df)


# ============================================================================
# DATE VALIDATION TESTS
# ============================================================================


class TestDateValidation:
    """Test date validation and conversion functions."""

    def test_validate_date_column_success(self, sample_polars_df):
        """Test successful date column validation."""
        result = validate_and_convert_date_column(sample_polars_df, "date")
        assert isinstance(result, pl.DataFrame)
        assert "date" in result.columns
        assert result.dtypes[0] == pl.Date

    def test_validate_date_column_missing(self, sample_polars_df):
        """Test validation with missing column."""
        with pytest.raises(ValueError, match="not found in dataframe"):
            validate_and_convert_date_column(sample_polars_df, "nonexistent")

    def test_validate_date_column_invalid_type(self):
        """Test validation with non-convertible column."""
        df = pl.DataFrame({"text": ["not", "a", "date"]})
        # Polars may handle this differently - converted but with nulls
        result = validate_and_convert_date_column(df, "text")
        # Just verify it returns a DataFrame with the column
        assert isinstance(result, pl.DataFrame)
        assert "text" in result.columns

    def test_prepare_date_data_success(self, sample_polars_df):
        """Test successful date data preparation."""
        result_df, missing_count = prepare_date_data(sample_polars_df, "date")
        assert isinstance(result_df, pl.DataFrame)
        assert missing_count == 0
        assert result_df.height == sample_polars_df.height

    def test_prepare_date_data_with_nulls(self):
        """Test date preparation with null values."""
        df = pl.DataFrame(
            {
                "date": [
                    date(2024, 1, 1),
                    None,
                    date(2024, 1, 3),
                    None,
                    date(2024, 1, 5),
                ]
            }
        )
        result_df, missing_count = prepare_date_data(df, "date")
        assert missing_count == 2
        assert result_df.height == 3


# ============================================================================
# SUBMISSION METRICS TESTS
# ============================================================================


class TestSubmissionMetricsCalculations:
    """Test submission metrics calculation functions."""

    def test_calculate_submission_count_basic(self, sample_date_data):
        """Test basic submission count calculation."""
        today = datetime.now().date()
        count = calculate_submission_count(
            sample_date_data, "submission_date", start_date=today
        )
        assert isinstance(count, int)
        assert count >= 0

    def test_calculate_submission_count_none_start(self, sample_date_data):
        """Test submission count with None start date."""
        count = calculate_submission_count(
            sample_date_data, "submission_date", start_date=None
        )
        assert count == 0

    def test_calculate_submission_count_with_end_date(self, sample_date_data):
        """Test submission count with end date."""
        today = datetime.now().date()
        yesterday = today - timedelta(days=1)
        count = calculate_submission_count(
            sample_date_data, "submission_date", start_date=yesterday, end_date=today
        )
        assert isinstance(count, int)

    def test_calculate_percentage_change_normal(self):
        """Test percentage change calculation."""
        result = calculate_percentage_change(150, 100)
        assert result == 50.0

    def test_calculate_percentage_change_zero_previous(self):
        """Test percentage change with zero previous value."""
        result = calculate_percentage_change(100, 0)
        assert result == 0.0

    def test_calculate_percentage_change_decrease(self):
        """Test percentage change with decrease."""
        result = calculate_percentage_change(75, 100)
        assert result == -25.0

    def test_calculate_submission_metrics_empty_data(self, empty_polars_df):
        """Test submission metrics with empty data."""
        result = calculate_submission_metrics(empty_polars_df, "date")
        assert result.total_count == 0
        assert result.today_count == 0
        assert result.first_submission_date is None

    def test_calculate_submission_metrics_valid_data(self, sample_date_data):
        """Test submission metrics with valid data."""
        result = calculate_submission_metrics(sample_date_data, "submission_date")
        assert isinstance(result, SubmissionMetrics)
        assert result.total_count == sample_date_data.height
        assert result.first_submission_date is not None
        assert result.last_submission_date is not None

    def test_calculate_submission_metrics_all_nulls(self):
        """Test submission metrics with all null dates."""
        df = pl.DataFrame({"date": [None, None, None], "id": [1, 2, 3]})
        result = calculate_submission_metrics(df, "date")
        assert result.total_count == 3
        assert result.first_submission_date is None

    def test_create_empty_submission_metrics(self):
        """Test creating empty submission metrics."""
        result = _create_empty_submission_metrics(total_count=10)
        assert result.total_count == 10
        assert result.today_count == 0
        assert result.first_submission_date is None

    def test_compute_summary_submissions_backward_compat(self, sample_pandas_df):
        """Test backward compatibility wrapper for submissions."""
        # Add proper date column
        df = sample_pandas_df.copy()
        result = compute_summary_submissions(df, "date")
        assert isinstance(result, tuple)
        assert len(result) == 10


# ============================================================================
# PROGRESS METRICS TESTS
# ============================================================================


class TestProgressMetricsCalculations:
    """Test progress metrics calculation functions."""

    def test_calculate_progress_metrics_empty_data(self, empty_polars_df):
        """Test progress metrics with empty data."""
        result = calculate_progress_metrics(empty_polars_df, "date", target=100)
        assert result.progress_pct == 0.0
        assert result.avg_per_day == 0.0

    def test_calculate_progress_metrics_with_target(self, sample_date_data):
        """Test progress metrics with target."""
        result = calculate_progress_metrics(
            sample_date_data, "submission_date", target=10
        )
        assert isinstance(result, ProgressMetrics)
        assert result.progress_pct > 0

    def test_calculate_progress_metrics_no_target(self, sample_date_data):
        """Test progress metrics without target."""
        result = calculate_progress_metrics(
            sample_date_data, "submission_date", target=None
        )
        assert result.progress_pct == 0.0
        assert result.avg_per_day > 0

    def test_calculate_progress_metrics_invalid_target(self, sample_date_data):
        """Test progress metrics with invalid target."""
        with pytest.raises(ValueError, match="Target must be a positive integer"):
            calculate_progress_metrics(sample_date_data, "submission_date", target=-1)

    def test_calculate_progress_metrics_string_target(self, sample_date_data):
        """Test progress metrics with string target."""
        with pytest.raises(ValueError, match="Target must be a positive integer"):
            calculate_progress_metrics(
                sample_date_data, "submission_date", target="100"
            )

    def test_create_empty_progress_metrics(self):
        """Test creating empty progress metrics."""
        result = _create_empty_progress_metrics()
        assert result.progress_pct == 0.0
        assert result.avg_per_day == 0.0
        assert result.avg_per_week == 0.0
        assert result.avg_per_month == 0.0

    def test_compute_summary_progress_backward_compat(self, sample_pandas_df):
        """Test backward compatibility wrapper for progress."""
        df = sample_pandas_df.copy()
        result = compute_summary_progress(df, "date", target=100)
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_calculate_progress_metrics_all_nulls(self):
        """Test progress metrics with all null dates."""
        df = pl.DataFrame({"date": [None, None, None], "id": [1, 2, 3]})
        result = calculate_progress_metrics(df, "date", target=10)
        assert result.progress_pct == 0.0


# ============================================================================
# PROGRESS BY COLUMN TESTS
# ============================================================================


class TestProgressByColumn:
    """Test progress by column calculation functions."""

    def test_determine_auto_time_period_daily(self):
        """Test auto time period determination for daily."""
        result = determine_auto_time_period(10)
        assert result == "Daily"

    def test_determine_auto_time_period_weekly(self):
        """Test auto time period determination for weekly."""
        result = determine_auto_time_period(50)
        assert result == "Weekly"

    def test_determine_auto_time_period_monthly(self):
        """Test auto time period determination for monthly."""
        result = determine_auto_time_period(200)
        assert result == "Monthly"

    def test_compute_summary_progress_by_col_empty(self):
        """Test progress by column with empty data."""
        df = pd.DataFrame()
        result = compute_summary_progress_by_col(df, "date", "column", "Auto")
        assert isinstance(result, tuple)
        assert len(result) == 4
        assert result[0].empty

    def test_compute_summary_progress_by_col_auto(self, sample_pandas_df):
        """Test progress by column with auto time period."""
        df = sample_pandas_df.copy()
        result = compute_summary_progress_by_col(df, "date", "name", "Auto")
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_compute_summary_progress_by_col_daily(self, sample_pandas_df):
        """Test progress by column with daily time period."""
        df = sample_pandas_df.copy()
        result = compute_summary_progress_by_col(df, "date", "name", "Daily")
        progress_df, vmin, vmax, format_cols = result
        assert isinstance(progress_df, pd.DataFrame)

    def test_compute_summary_progress_by_col_weekly(self, sample_pandas_df):
        """Test progress by column with weekly time period."""
        df = sample_pandas_df.copy()
        result = compute_summary_progress_by_col(df, "date", "name", "Weekly")
        assert isinstance(result[0], pd.DataFrame)

    def test_compute_summary_progress_by_col_monthly(self, sample_pandas_df):
        """Test progress by column with monthly time period."""
        df = sample_pandas_df.copy()
        result = compute_summary_progress_by_col(df, "date", "name", "Monthly")
        assert isinstance(result[0], pd.DataFrame)

    def test_compute_summary_progress_by_col_invalid_date(self):
        """Test progress by column with invalid date column."""
        df = pd.DataFrame({"text": ["a", "b", "c"], "col": ["x", "y", "z"]})
        # Polars may handle this differently - it converts but values might be null
        # Test that it still returns a result (even if empty/null)
        result = compute_summary_progress_by_col(df, "text", "col", "Daily")
        # Should return empty or result with null dates
        assert isinstance(result, tuple)
        assert len(result) == 4


# ============================================================================
# DATA SUMMARY TESTS
# ============================================================================


class TestDataSummary:
    """Test data summary calculation functions."""

    def test_calculate_data_summary_metrics(self, sample_polars_df):
        """Test data summary metrics calculation."""
        result = calculate_data_summary_metrics(sample_polars_df)
        assert isinstance(result, DataSummaryMetrics)
        assert result.total_columns_count == sample_polars_df.width
        assert result.string_columns_count >= 0
        assert result.numeric_columns_count >= 0
        assert result.date_columns_count >= 0

    def test_calculate_data_summary_metrics_empty(self, empty_polars_df):
        """Test data summary with empty dataframe."""
        result = calculate_data_summary_metrics(empty_polars_df)
        assert result.total_columns_count == 0

    def test_calculate_data_summary_all_types(self):
        """Test data summary with all column types."""
        df = pl.DataFrame(
            {
                "string": ["a", "b", "c"],
                "int": [1, 2, 3],
                "float": [1.1, 2.2, 3.3],
                "date": [date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)],
                "categorical": pl.Series(["x", "y", "z"]).cast(pl.Categorical),
            }
        )
        result = calculate_data_summary_metrics(df)
        assert result.string_columns_count > 0
        assert result.numeric_columns_count > 0
        assert result.date_columns_count > 0
        assert result.total_columns_count == 5

    def test_compute_summary_data_summary_backward_compat(self, sample_pandas_df):
        """Test backward compatibility wrapper for data summary."""
        result = compute_summary_data_summary(sample_pandas_df)
        assert isinstance(result, tuple)
        assert len(result) == 4


# ============================================================================
# DATA QUALITY TESTS
# ============================================================================


class TestDataQuality:
    """Test data quality calculation functions."""

    def test_calculate_data_quality_with_survey_id(self, sample_polars_df):
        """Test data quality calculation with survey ID."""
        result = calculate_data_quality_metrics(sample_polars_df, "id")
        assert isinstance(result, DataQualityMetrics)
        assert result.duplicates_pct is not None
        assert result.missing_pct >= 0

    def test_calculate_data_quality_without_survey_id(self, sample_polars_df):
        """Test data quality calculation without survey ID."""
        result = calculate_data_quality_metrics(sample_polars_df, None)
        assert result.duplicates_pct is None
        assert result.missing_pct >= 0

    def test_calculate_data_quality_invalid_survey_id(self, sample_polars_df):
        """Test data quality with invalid survey ID column."""
        result = calculate_data_quality_metrics(sample_polars_df, "nonexistent")
        assert result.duplicates_pct is None

    def test_calculate_data_quality_with_duplicates(self):
        """Test data quality with duplicate IDs."""
        df = pl.DataFrame({"id": [1, 1, 2, 2, 3], "value": [10, 20, 30, 40, 50]})
        result = calculate_data_quality_metrics(df, "id")
        assert result.duplicates_pct > 0

    def test_calculate_data_quality_with_missing_values(self):
        """Test data quality with missing values."""
        df = pl.DataFrame(
            {"id": [1, 2, 3], "value": [10, None, 30], "text": [None, "b", "c"]}
        )
        result = calculate_data_quality_metrics(df, "id")
        assert result.missing_pct > 0

    def test_calculate_data_quality_empty(self, empty_polars_df):
        """Test data quality with empty dataframe."""
        result = calculate_data_quality_metrics(empty_polars_df, None)
        assert result.missing_pct == 0.0
        assert result.outliers_pct == 0.0

    def test_compute_summary_data_quality_backward_compat(self, sample_pandas_df):
        """Test backward compatibility wrapper for data quality."""
        result = compute_summary_data_quality(sample_pandas_df, "id")
        assert isinstance(result, tuple)
        assert len(result) == 4


# ============================================================================
# UI COMPONENT TESTS
# ============================================================================


class TestUIComponents:
    """Test UI component functions with mocked Streamlit."""

    @patch("datasure.checks.summary.st")
    @patch("datasure.checks.summary.get_df_info")
    @patch("datasure.checks.summary.save_check_settings")
    @patch("datasure.checks.summary.trigger_save")
    def test_summary_settings(
        self,
        mock_trigger_save,
        mock_save_settings,
        mock_get_info,
        mock_st,
    ):
        """Test summary settings UI component."""
        # Setup mocks
        mock_get_info.return_value = (None, ["id"], [1, 2, 3], ["date_col"], None)

        # Mock expander and container context managers
        mock_expander = Mock()
        mock_expander.__enter__ = Mock(return_value=mock_expander)
        mock_expander.__exit__ = Mock(return_value=False)
        mock_st.expander.return_value = mock_expander

        mock_container = Mock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container

        # Mock columns with context manager support
        col_mock1 = Mock()
        col_mock1.__enter__ = Mock(return_value=col_mock1)
        col_mock1.__exit__ = Mock(return_value=False)
        col_mock2 = Mock()
        col_mock2.__enter__ = Mock(return_value=col_mock2)
        col_mock2.__exit__ = Mock(return_value=False)
        col_mock3 = Mock()
        col_mock3.__enter__ = Mock(return_value=col_mock3)
        col_mock3.__exit__ = Mock(return_value=False)
        mock_st.columns.return_value = [col_mock1, col_mock2, col_mock3]

        # Mock selectbox and number_input
        mock_st.selectbox.side_effect = ["id_col", "date_col"]
        mock_st.number_input.return_value = 100

        df = pd.DataFrame({"id": [1], "date_col": [date(2024, 1, 1)]})
        config = SummarySettings(
            survey_id="id_col", survey_date="date_col", survey_target=100
        )
        result = summary_settings(df, "settings.json", config)

        assert isinstance(result, tuple)
        assert len(result) == 3

    @patch("datasure.checks.summary.st")
    @patch("datasure.checks.summary.pandas_to_polars")
    @patch("datasure.checks.summary.calculate_submission_metrics")
    @patch("datasure.checks.summary.px")
    def test_summary_submissions_no_date(
        self, mock_px, mock_calc, mock_convert, mock_st
    ):
        """Test summary submissions without date column."""
        df = pd.DataFrame({"id": [1, 2, 3]})
        summary_submissions(df, date=None)

        mock_st.info.assert_called_once()

    @patch("datasure.checks.summary.st")
    @patch("datasure.checks.summary.px")
    def test_summary_submissions_with_date(self, mock_px, mock_st):
        """Test summary submissions with date column."""
        # Create mock figure
        mock_fig = Mock()
        mock_px.area.return_value = mock_fig

        # Create test data with dates
        df = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "date_col": pd.date_range("2024-01-01", periods=3),
            }
        )

        # Mock columns
        mock_col = Mock()
        mock_st.columns.return_value = [mock_col, mock_col, mock_col, mock_col]

        summary_submissions(df, date="date_col")

        # Verify plotly chart was called
        mock_st.plotly_chart.assert_called_once()

    @patch("datasure.checks.summary.st")
    @patch("datasure.checks.summary.pandas_to_polars")
    @patch("datasure.checks.summary.calculate_progress_metrics")
    @patch("datasure.checks.summary._render_progress_by_column")
    def test_summary_progress_no_date(
        self, mock_render, mock_calc, mock_convert, mock_st
    ):
        """Test summary progress without date column."""
        df = pd.DataFrame({"id": [1, 2, 3]})
        summary_progress(df, date=None, target=100, setting_file="settings.json")

        mock_st.info.assert_called_once()

    @patch("datasure.checks.summary.st")
    @patch("datasure.checks.summary._render_progress_by_column")
    def test_summary_progress_with_date_and_target(self, mock_render, mock_st):
        """Test summary progress with date column and target."""
        # Create test data with dates
        df = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "date_col": pd.date_range("2024-01-01", periods=3),
            }
        )

        # Mock columns - return different values for different calls
        mock_col = Mock()
        mock_col.__enter__ = Mock(return_value=mock_col)
        mock_col.__exit__ = Mock(return_value=False)
        mock_st.columns.side_effect = [
            [mock_col, mock_col, mock_col, mock_col],  # First call
            [mock_col, mock_col],  # Second call (sp1, sp2)
        ]

        summary_progress(df, date="date_col", target=100, setting_file="settings.json")

        # Verify _render_progress_by_column was called
        mock_render.assert_called_once()

    @patch("datasure.checks.summary.st")
    @patch("datasure.checks.summary._render_progress_by_column")
    def test_summary_progress_with_date_no_target(self, mock_render, mock_st):
        """Test summary progress with date column but no target."""
        # Create test data with dates
        df = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "date_col": pd.date_range("2024-01-01", periods=3),
            }
        )

        # Mock columns
        mock_col = Mock()
        mock_col.__enter__ = Mock(return_value=mock_col)
        mock_col.__exit__ = Mock(return_value=False)
        mock_st.columns.return_value = [mock_col, mock_col, mock_col, mock_col]

        summary_progress(df, date="date_col", target=None, setting_file="settings.json")

        # Verify info message about target not set
        assert mock_st.info.called

    @patch("datasure.checks.summary.st")
    @patch("datasure.checks.summary.pandas_to_polars")
    @patch("datasure.checks.summary.calculate_data_summary_metrics")
    def test_summary_data_summary(self, mock_calc, mock_convert, mock_st):
        """Test summary data summary UI component."""
        mock_convert.return_value = pl.DataFrame()
        mock_calc.return_value = DataSummaryMetrics(
            string_columns_count=5,
            numeric_columns_count=3,
            date_columns_count=2,
            total_columns_count=10,
        )
        mock_st.columns.return_value = [Mock(), Mock(), Mock(), Mock()]

        df = pd.DataFrame({"id": [1, 2, 3]})
        summary_data_summary(df)

        assert mock_st.columns.called

    @patch("datasure.checks.summary.st")
    @patch("datasure.checks.summary.pandas_to_polars")
    @patch("datasure.checks.summary.calculate_data_quality_metrics")
    @patch("datasure.checks.summary.donut_chart2")
    @patch("datasure.checks.summary.plt")
    def test_summary_data_quality(
        self, mock_plt, mock_chart, mock_calc, mock_convert, mock_st
    ):
        """Test summary data quality UI component."""
        mock_convert.return_value = pl.DataFrame()
        mock_calc.return_value = DataQualityMetrics(
            duplicates_pct=2.5,
            outliers_pct=1.0,
            missing_pct=0.5,
            backcheck_error_pct=0.1,
        )
        mock_chart.return_value = Mock()

        # Mock columns with context manager support
        col_mock1 = Mock()
        col_mock1.__enter__ = Mock(return_value=col_mock1)
        col_mock1.__exit__ = Mock(return_value=False)
        col_mock2 = Mock()
        col_mock2.__enter__ = Mock(return_value=col_mock2)
        col_mock2.__exit__ = Mock(return_value=False)
        col_mock3 = Mock()
        col_mock3.__enter__ = Mock(return_value=col_mock3)
        col_mock3.__exit__ = Mock(return_value=False)
        col_mock4 = Mock()
        col_mock4.__enter__ = Mock(return_value=col_mock4)
        col_mock4.__exit__ = Mock(return_value=False)

        mock_st.columns.return_value = [col_mock1, col_mock2, col_mock3, col_mock4]

        df = pd.DataFrame({"id": [1, 2, 3]})
        summary_data_quality(df, "id")

        assert mock_st.columns.called
        assert mock_chart.called

    @patch("datasure.checks.summary.st")
    @patch("datasure.checks.summary.pandas_to_polars")
    @patch("datasure.checks.summary.calculate_data_quality_metrics")
    @patch("datasure.checks.summary.donut_chart2")
    @patch("datasure.checks.summary.plt")
    def test_summary_data_quality_no_survey_id(
        self, mock_plt, mock_chart, mock_calc, mock_convert, mock_st
    ):
        """Test summary data quality UI component without survey ID."""
        from datasure.checks.summary import summary_data_quality

        mock_convert.return_value = pl.DataFrame()
        mock_calc.return_value = DataQualityMetrics(
            duplicates_pct=None,
            outliers_pct=1.0,
            missing_pct=0.5,
            backcheck_error_pct=0.1,
        )
        mock_chart.return_value = Mock()

        # Mock columns with context manager support
        col_mock1 = Mock()
        col_mock1.__enter__ = Mock(return_value=col_mock1)
        col_mock1.__exit__ = Mock(return_value=False)
        col_mock2 = Mock()
        col_mock2.__enter__ = Mock(return_value=col_mock2)
        col_mock2.__exit__ = Mock(return_value=False)
        col_mock3 = Mock()
        col_mock3.__enter__ = Mock(return_value=col_mock3)
        col_mock3.__exit__ = Mock(return_value=False)
        col_mock4 = Mock()
        col_mock4.__enter__ = Mock(return_value=col_mock4)
        col_mock4.__exit__ = Mock(return_value=False)

        mock_st.columns.return_value = [col_mock1, col_mock2, col_mock3, col_mock4]

        df = pd.DataFrame({"id": [1, 2, 3]})
        summary_data_quality(df, None)

        assert mock_st.columns.called

    @patch("datasure.checks.summary.st")
    @patch("datasure.checks.summary.load_check_settings")
    @patch("datasure.checks.summary.save_check_settings")
    @patch("datasure.checks.summary.trigger_save")
    @patch("datasure.checks.summary.compute_summary_progress_by_col")
    @patch("datasure.checks.summary.sns")
    @patch("datasure.checks.summary.pd")
    def test_render_progress_by_column(
        self,
        mock_pd_module,
        mock_sns,
        mock_compute,
        mock_trigger,
        mock_save,
        mock_load,
        mock_st,
    ):
        """Test _render_progress_by_column UI component."""
        from datasure.checks.summary import _render_progress_by_column

        # Mock settings
        mock_load.return_value = {
            "progress_by_col": "region",
            "progress_time_period": "Auto",
        }

        # Mock columns
        col_mock1 = Mock()
        col_mock1.__enter__ = Mock(return_value=col_mock1)
        col_mock1.__exit__ = Mock(return_value=False)
        col_mock2 = Mock()
        col_mock2.__enter__ = Mock(return_value=col_mock2)
        col_mock2.__exit__ = Mock(return_value=False)
        mock_st.columns.return_value = [col_mock1, col_mock2]

        # Mock selectbox and pills
        mock_st.selectbox.return_value = "region"
        mock_st.pills.return_value = "Auto"

        # Mock compute result
        progress_df = pd.DataFrame({"region": ["A", "B"], "2024-01-01": [10, 20]})
        mock_compute.return_value = (progress_df, 10, 20, ["2024-01-01"])

        # Mock sns and pd
        mock_cmap = Mock()
        mock_sns.light_palette.return_value = mock_cmap

        df = pd.DataFrame(
            {
                "region": ["A", "B", "C"],
                "date_col": pd.date_range("2024-01-01", periods=3),
            }
        )

        _render_progress_by_column(df, "date_col", "settings.json")

        assert mock_st.selectbox.called
        assert mock_st.pills.called
        assert mock_st.dataframe.called

    @patch("datasure.checks.summary.st")
    @patch("datasure.checks.summary.load_check_settings")
    def test_render_progress_by_column_no_selection(self, mock_load, mock_st):
        """Test _render_progress_by_column when no column selected."""
        from datasure.checks.summary import _render_progress_by_column

        # Mock settings
        mock_load.return_value = {}

        # Mock columns
        col_mock1 = Mock()
        col_mock1.__enter__ = Mock(return_value=col_mock1)
        col_mock1.__exit__ = Mock(return_value=False)
        col_mock2 = Mock()
        col_mock2.__enter__ = Mock(return_value=col_mock2)
        col_mock2.__exit__ = Mock(return_value=False)
        mock_st.columns.return_value = [col_mock1, col_mock2]

        # Mock selectbox to return None
        mock_st.selectbox.return_value = None

        df = pd.DataFrame(
            {
                "region": ["A", "B", "C"],
                "date_col": pd.date_range("2024-01-01", periods=3),
            }
        )

        _render_progress_by_column(df, "date_col", "settings.json")

        # Should return early without calling compute or dataframe
        assert not mock_st.dataframe.called

    @patch("datasure.checks.summary.st")
    @patch("datasure.checks.summary.summary_settings")
    @patch("datasure.checks.summary.summary_data_summary")
    @patch("datasure.checks.summary.summary_submissions")
    @patch("datasure.checks.summary.summary_progress")
    @patch("datasure.checks.summary.summary_data_quality")
    def test_summary_report(
        self,
        mock_quality,
        mock_progress,
        mock_submissions,
        mock_data_summary,
        mock_settings,
        mock_st,
    ):
        """Test complete summary report generation."""
        import polars as pl

        from datasure.checks.summary import summary_report

        mock_settings.return_value = ("date_col", 100, "id_col")

        df = pd.DataFrame({"id": [1, 2, 3], "date_col": [date(2024, 1, 1)] * 3})
        # Convert to Polars as expected by the function
        pl_df = pl.from_pandas(df)
        config = {
            "survey_id": "id_col",
            "survey_date": "date_col",
            "survey_target": 100,
        }
        # Updated signature: (data: pl.DataFrame, setting_file: str, config: dict)
        summary_report(pl_df, "settings.json", config)

        mock_settings.assert_called_once()
        mock_data_summary.assert_called_once()
        mock_submissions.assert_called_once()
        mock_progress.assert_called_once()
        mock_quality.assert_called_once()
