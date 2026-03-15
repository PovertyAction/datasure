"""Comprehensive tests for the outliers module with 100% code coverage."""

# Standard library imports
from unittest.mock import patch

# Third-party imports
import pandas as pd
import polars as pl
import pytest
from pydantic import ValidationError

# Local application imports
from datasure.checks.outliers import (
    # Pydantic Models
    ConstraintBounds,
    ConstraintMetrics,
    OutlierBounds,
    OutlierColumnConfig,
    # Enums
    OutlierMethod,
    OutlierMetrics,
    OutlierOptionsConfig,
    OutlierSettings,
    OutlierStatistics,
    SearchType,
    # Refactored helper functions
    _add_statistics_columns,
    _build_include_cols,
    _build_outlier_expression,
    _compute_column_stats,
    _compute_iqr_bounds,
    _compute_sd_bounds,
    _compute_single_column_stats,
    _ensure_list,
    _merge_outlier_results,
    _process_outlier_configs,
    _process_single_column_outliers,
    _process_single_config,
    _should_expand_row,
    _update_unlocked_cols,
    # Statistical functions
    compute_column_outlier_summary,
    compute_constraint_violations,
    compute_outlier_output,
    compute_outlier_stats_polars,
    # Utility functions
    expand_col_names,
    # Settings functions
    load_default_settings,
    safe_to_numeric,
    stack_outlier_columns,
    update_unlocked_cols,
)
from datasure.utils.dataframe_utils import (
    convert_dataframe_column_to_numeric,
    convert_series_to_numeric,
    sanitize_df_for_join,
)

# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests.
    """
    pass


@pytest.fixture
def sample_polars_df():
    """Create a sample Polars DataFrame for testing."""
    from datetime import date

    return pl.DataFrame(
        {
            "survey_key": ["K001", "K002", "K003", "K004", "K005"],
            "survey_id": ["S001", "S002", "S003", "S004", "S005"],
            "enumerator": ["E001", "E002", "E001", "E003", "E002"],
            "team": ["T1", "T2", "T1", "T3", "T2"],
            "survey_date": [date(2024, 1, i) for i in range(1, 6)],
            "numeric_col1": [1.0, 2.0, 3.0, 100.0, 5.0],  # outlier: 100.0
            "numeric_col2": [10.0, 20.0, 30.0, 40.0, 500.0],  # outlier: 500.0
            "string_col": ["A", "B", "C", "D", "E"],
        }
    )


@pytest.fixture
def sample_pandas_df():
    """Create a sample pandas DataFrame for testing."""
    return pd.DataFrame(
        {
            "survey_key": ["K001", "K002", "K003", "K004", "K005"],
            "survey_id": ["S001", "S002", "S003", "S004", "S005"],
            "enumerator": ["E001", "E002", "E001", "E003", "E002"],
            "numeric_col1": [1.0, 2.0, 3.0, 100.0, 5.0],
            "numeric_col2": [10.0, 20.0, 30.0, 40.0, 500.0],
        }
    )


@pytest.fixture
def outlier_column_config():
    """Create sample outlier column configuration."""
    return pl.DataFrame(
        {
            "search_type": ["exact"],
            "pattern": [None],
            "column_name": [["numeric_col1"]],
            "grouped_columns": [False],
            "locked": [False],
            "outlier_enabled": [True],
            "outlier_method": ["Interquartile Range (IQR)"],
            "outlier_multiplier": [1.5],
            "outlier_threshold": [3],
            "hard_min": [None],
            "soft_min": [0.0],
            "soft_max": [50.0],
            "hard_max": [None],
        }
    )


@pytest.fixture
def outlier_settings():
    """Create sample outlier settings."""
    return OutlierSettings(
        survey_key="survey_key",
        survey_id="survey_id",
        survey_date="survey_date",
        enumerator="enumerator",
        team="team",
    )


# ============================================================================
# PYDANTIC MODEL TESTS
# ============================================================================


class TestOutlierBounds:
    """Test OutlierBounds Pydantic model."""

    def test_valid_bounds(self):
        """Test creating valid outlier bounds."""
        bounds = OutlierBounds(lower_bound=0.0, upper_bound=100.0)
        assert bounds.lower_bound == 0.0
        assert bounds.upper_bound == 100.0

    def test_negative_bounds(self):
        """Test bounds with negative values."""
        bounds = OutlierBounds(lower_bound=-50.0, upper_bound=50.0)
        assert bounds.lower_bound == -50.0
        assert bounds.upper_bound == 50.0


class TestOutlierOptionsConfig:
    """Test OutlierOptionsConfig Pydantic model."""

    def test_valid_config(self):
        """Test creating valid outlier options config."""
        config = OutlierOptionsConfig(
            outlier_method=OutlierMethod.IQR,
            outlier_multiplier=1.5,
            outlier_threshold=20,
        )
        assert config.outlier_method == OutlierMethod.IQR
        assert config.outlier_multiplier == 1.5
        assert config.outlier_threshold == 20

    def test_invalid_multiplier_zero(self):
        """Test that zero multiplier raises validation error."""
        with pytest.raises(ValidationError):
            OutlierOptionsConfig(
                outlier_method=OutlierMethod.IQR,
                outlier_multiplier=0.0,
                outlier_threshold=20,
            )

    def test_invalid_multiplier_negative(self):
        """Test that negative multiplier raises validation error."""
        with pytest.raises(ValidationError):
            OutlierOptionsConfig(
                outlier_method=OutlierMethod.IQR,
                outlier_multiplier=-1.5,
                outlier_threshold=20,
            )

    def test_invalid_threshold_zero(self):
        """Test that zero threshold raises validation error."""
        with pytest.raises(ValidationError):
            OutlierOptionsConfig(
                outlier_method=OutlierMethod.IQR,
                outlier_multiplier=1.5,
                outlier_threshold=0,
            )


class TestConstraintBounds:
    """Test ConstraintBounds Pydantic model."""

    def test_valid_bounds_all_fields(self):
        """Test creating valid constraint bounds with all fields."""
        bounds = ConstraintBounds(
            hard_min=0.0, soft_min=10.0, soft_max=90.0, hard_max=100.0
        )
        assert bounds.hard_min == 0.0
        assert bounds.soft_min == 10.0
        assert bounds.soft_max == 90.0
        assert bounds.hard_max == 100.0

    def test_valid_bounds_partial(self):
        """Test creating valid constraint bounds with partial fields."""
        bounds = ConstraintBounds(soft_min=10.0, soft_max=90.0)
        assert bounds.hard_min is None
        assert bounds.soft_min == 10.0
        assert bounds.soft_max == 90.0
        assert bounds.hard_max is None

    def test_invalid_bounds_hierarchy(self):
        """Test that invalid hierarchy raises validation error."""
        with pytest.raises(ValidationError, match="Bounds must follow hierarchy"):
            ConstraintBounds(
                hard_min=50.0,
                soft_min=10.0,  # hard_min > soft_min
            )

    def test_invalid_soft_bounds(self):
        """Test that soft_min > soft_max raises validation error."""
        with pytest.raises(ValidationError):
            ConstraintBounds(soft_min=90.0, soft_max=10.0)

    def test_negative_bounds(self):
        """Test constraint bounds with negative values."""
        bounds = ConstraintBounds(
            hard_min=-100.0, soft_min=-50.0, soft_max=50.0, hard_max=100.0
        )
        assert bounds.hard_min == -100.0


class TestConstraintMetrics:
    """Test ConstraintMetrics Pydantic model."""

    def test_valid_metrics(self):
        """Test creating valid constraint metrics."""
        metrics = ConstraintMetrics(
            columns_checked=5,
            total_violations=10,
            hard_min_violations=2,
            soft_min_violations=3,
            soft_max_violations=3,
            hard_max_violations=2,
        )
        assert metrics.total_violations == 10

    def test_negative_values_invalid(self):
        """Test that negative values raise validation error."""
        with pytest.raises(ValidationError):
            ConstraintMetrics(
                columns_checked=-1,
                total_violations=0,
                hard_min_violations=0,
                soft_min_violations=0,
                soft_max_violations=0,
                hard_max_violations=0,
            )


class TestOutlierMetrics:
    """Test OutlierMetrics Pydantic model."""

    def test_valid_metrics(self):
        """Test creating valid outlier metrics."""
        metrics = OutlierMetrics(
            columns_checked=5,
            columns_with_outliers=3,
            total_outliers=10,
            enumerators_with_outliers=2,
        )
        assert metrics.columns_checked == 5
        assert metrics.total_outliers == 10


class TestOutlierStatistics:
    """Test OutlierStatistics Pydantic model."""

    def test_valid_statistics(self):
        """Test creating valid outlier statistics."""
        stats = OutlierStatistics(
            count=100,
            min_value=0.0,
            max_value=100.0,
            mean=50.0,
            median=48.0,
            sd=15.0,
            iqr=25.0,
            lower_bound=10.0,
            upper_bound=90.0,
        )
        assert stats.count == 100
        assert stats.mean == 50.0
        assert stats.sd == 15.0

    def test_alias_std(self):
        """Test that 'sd' alias works for std field."""
        stats = OutlierStatistics(
            count=100,
            min_value=0.0,
            max_value=100.0,
            mean=50.0,
            median=48.0,
            sd=15.0,  # Using alias
            iqr=25.0,
            lower_bound=10.0,
            upper_bound=90.0,
        )
        assert stats.sd == 15.0


class TestOutlierColumnConfig:
    """Test OutlierColumnConfig Pydantic model."""

    def test_valid_config_exact(self):
        """Test creating valid config with exact search."""
        config = OutlierColumnConfig(
            search_type=SearchType.EXACT,
            pattern=None,
            outlier_cols=["col1", "col2"],
            lock_cols=False,
            grouped_cols=False,
            outlier_method=OutlierMethod.IQR,
            outlier_multiplier=1.5,
        )
        assert config.search_type == SearchType.EXACT

    def test_invalid_pattern_required(self):
        """Test that pattern is required for non-exact search types."""
        with pytest.raises(ValidationError):
            OutlierColumnConfig(
                search_type=SearchType.STARTSWITH,
                pattern=None,  # Should be required
                outlier_cols=["col1"],
                outlier_method=OutlierMethod.IQR,
                outlier_multiplier=1.5,
            )

    def test_invalid_soft_bounds(self):
        """Test that soft_max must be greater than soft_min."""
        with pytest.raises(ValidationError):
            OutlierColumnConfig(
                search_type=SearchType.EXACT,
                outlier_cols=["col1"],
                outlier_method=OutlierMethod.IQR,
                outlier_multiplier=1.5,
                soft_min=50.0,
                soft_max=10.0,  # Less than soft_min
            )


class TestOutlierSettings:
    """Test OutlierSettings Pydantic model."""

    def test_valid_settings(self):
        """Test creating valid outlier settings."""
        settings = OutlierSettings(
            survey_key="key",
            survey_id="id",
            survey_date="date",
            enumerator="enum",
            team="team",
        )
        assert settings.survey_key == "key"

    def test_minimal_settings(self):
        """Test creating minimal valid settings."""
        settings = OutlierSettings(survey_key="key")
        assert settings.survey_key == "key"
        assert settings.survey_id is None


# ============================================================================
# UTILITY FUNCTION TESTS
# ============================================================================


class TestExpandColNames:
    """Test expand_col_names function."""

    def test_exact_match(self):
        """Test exact matching."""
        cols = ["age", "income", "education"]
        result = expand_col_names(cols, "age", "exact")
        assert result == ["age"]

    def test_startswith_match(self):
        """Test startswith matching."""
        cols = ["hh_member_1", "hh_member_2", "other"]
        result = expand_col_names(cols, "hh_", "startswith")
        assert result == ["hh_member_1", "hh_member_2"]

    def test_endswith_match(self):
        """Test endswith matching."""
        cols = ["col_1_age", "col_2_age", "other"]
        result = expand_col_names(cols, "_age", "endswith")
        assert result == ["col_1_age", "col_2_age"]

    def test_contains_match(self):
        """Test contains matching."""
        cols = ["hh_member_1", "hh_member_2", "other"]
        result = expand_col_names(cols, "member", "contains")
        assert result == ["hh_member_1", "hh_member_2"]

    def test_regex_match(self):
        """Test regex matching."""
        cols = ["var_1", "var_2", "other"]
        result = expand_col_names(cols, r"var_\d+", "regex")
        assert result == ["var_1", "var_2"]

    def test_invalid_input_not_list(self):
        """Test with invalid input type."""
        with pytest.raises(TypeError):
            expand_col_names("not_a_list", "pattern", "exact")

    def test_invalid_pattern_none(self):
        """Test with None pattern."""
        with pytest.raises(TypeError):
            expand_col_names(["col1"], None, "exact")

    def test_invalid_search_type(self):
        """Test with invalid search type."""
        with pytest.raises(ValueError):
            expand_col_names(["col1"], "pattern", "invalid")


class TestSafeToNumeric:
    """Test safe_to_numeric function."""

    def test_convert_series_already_numeric(self):
        """Test converting series that's already numeric."""
        series = pl.Series([1, 2, 3])
        result = safe_to_numeric(series)
        assert result.dtype in pl.NUMERIC_DTYPES

    def test_convert_series_string_numbers(self):
        """Test converting string series with numbers."""
        series = pl.Series(["1", "2", "3"])
        result = safe_to_numeric(series)
        assert result.dtype in pl.NUMERIC_DTYPES

    def test_convert_dataframe_column(self):
        """Test converting DataFrame column."""
        df = pl.DataFrame({"col": ["1", "2", "3"]})
        result = safe_to_numeric(df, "col")
        assert result["col"].dtype in pl.NUMERIC_DTYPES

    def test_convert_dataframe_no_column(self):
        """Test that column is required for DataFrames."""
        df = pl.DataFrame({"col": [1, 2, 3]})
        with pytest.raises(ValueError, match="Column is required"):
            safe_to_numeric(df)

    def test_invalid_type(self):
        """Test with invalid input type."""
        with pytest.raises(TypeError):
            safe_to_numeric([1, 2, 3])


class TestComputeOutlierStatsPolars:
    """Test compute_outlier_stats_polars function."""

    def test_iqr_method(self):
        """Test with IQR method."""
        series = pl.Series([1, 2, 3, 4, 5, 100])
        result = compute_outlier_stats_polars(series, OutlierMethod.IQR.value, 1.5)
        assert isinstance(result, OutlierStatistics)
        assert result.count == 6
        assert result.lower_bound < result.upper_bound

    def test_sd_method(self):
        """Test with Standard Deviation method."""
        series = pl.Series([1, 2, 3, 4, 5, 100])
        result = compute_outlier_stats_polars(series, OutlierMethod.SD.value, 3.0)
        assert isinstance(result, OutlierStatistics)
        assert result.count == 6

    def test_empty_series(self):
        """Test with empty series."""
        series = pl.Series([])
        with pytest.raises(ValueError, match="The Series is empty"):
            compute_outlier_stats_polars(series, OutlierMethod.IQR.value, 1.5)

    def test_invalid_method(self):
        """Test with invalid outlier method."""
        series = pl.Series([1, 2, 3])
        with pytest.raises(ValueError, match="Invalid outlier type"):
            compute_outlier_stats_polars(series, "Invalid", 1.5)

    def test_invalid_multiplier(self):
        """Test with invalid multiplier."""
        series = pl.Series([1, 2, 3])
        with pytest.raises(ValueError, match="Multiplier must be a positive"):
            compute_outlier_stats_polars(series, OutlierMethod.IQR.value, -1.5)

    def test_default_multiplier_iqr(self):
        """Test with default IQR multiplier."""
        series = pl.Series([1, 2, 3, 4, 5])
        result = compute_outlier_stats_polars(series, OutlierMethod.IQR.value, None)
        assert result.lower_bound is not None

    def test_default_multiplier_sd(self):
        """Test with default SD multiplier."""
        series = pl.Series([1, 2, 3, 4, 5])
        result = compute_outlier_stats_polars(series, OutlierMethod.SD.value, None)
        assert result.lower_bound is not None

    def test_series_with_nulls(self):
        """Test with series containing null values."""
        series = pl.Series([1, 2, None, 4, 5])
        result = compute_outlier_stats_polars(series, OutlierMethod.IQR.value, 1.5)
        assert result.count == 4  # Nulls are dropped


class TestStackOutlierColumns:
    """Test stack_outlier_columns function."""

    def test_stack_basic(self, sample_polars_df):
        """Test basic stacking functionality."""
        result = stack_outlier_columns(
            sample_polars_df, ["numeric_col1", "numeric_col2"]
        )
        assert isinstance(result, pl.Series)
        assert result.len() == 10  # 5 rows x 2 columns

    def test_stack_single_column(self, sample_polars_df):
        """Test stacking single column."""
        result = stack_outlier_columns(sample_polars_df, ["numeric_col1"])
        assert result.len() == 5

    @pytest.mark.skip(
        reason="Empty DataFrame causes Rust panic in Polars/Streamlit caching"
    )
    def test_stack_empty_dataframe(self):
        """Test with empty DataFrame."""
        df = pl.DataFrame()
        with pytest.raises(ValueError, match="The DataFrame is empty"):
            stack_outlier_columns(df, ["col1"])

    def test_stack_missing_column(self, sample_polars_df):
        """Test with missing column."""
        with pytest.raises(ValueError, match="does not exist"):
            stack_outlier_columns(sample_polars_df, ["nonexistent"])

    def test_stack_non_numeric_column(self, sample_polars_df):
        """Test with non-numeric column."""
        with pytest.raises(ValueError, match="cannot be converted"):
            stack_outlier_columns(sample_polars_df, ["string_col"])


# ============================================================================
# COMPUTATION FUNCTION TESTS
# ============================================================================


class TestComputeOutlierOutput:
    """Test compute_outlier_output function."""

    def test_basic_computation(
        self, sample_polars_df, outlier_settings, outlier_column_config
    ):
        """Test basic outlier computation."""
        result = compute_outlier_output(
            sample_polars_df, outlier_settings, outlier_column_config
        )
        assert isinstance(result, pl.DataFrame)
        assert "outlier reason" in result.columns
        assert "column name" in result.columns

    def test_empty_dataframe(self, outlier_settings, outlier_column_config):
        """Test with empty DataFrame."""
        df = pl.DataFrame()
        with pytest.raises(ValueError, match="The DataFrame is empty"):
            compute_outlier_output(df, outlier_settings, outlier_column_config)

    def test_no_outliers_enabled(self, sample_polars_df, outlier_settings):
        """Test when no outliers are enabled."""
        config = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["numeric_col1"]],
                "outlier_enabled": [False],  # Disabled
                "grouped_columns": [False],
                "locked": [False],
                "outlier_method": ["Interquartile Range (IQR)"],
                "outlier_multiplier": [1.5],
                "outlier_threshold": [3],
                "hard_min": [None],
                "soft_min": [None],
                "soft_max": [None],
                "hard_max": [None],
            }
        )
        result = compute_outlier_output(sample_polars_df, outlier_settings, config)
        assert result.is_empty()


class TestComputeConstraintViolations:
    """Test compute_constraint_violations function."""

    def test_basic_computation(
        self, sample_polars_df, outlier_settings, outlier_column_config
    ):
        """Test basic constraint violation computation."""
        result = compute_constraint_violations(
            sample_polars_df, outlier_settings, outlier_column_config
        )
        assert isinstance(result, pl.DataFrame)
        if not result.is_empty():
            assert "violation reason" in result.columns

    def test_no_bounds_set(self, sample_polars_df, outlier_settings):
        """Test when no constraint bounds are set."""
        config = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["numeric_col1"]],
                "hard_min": [None],
                "soft_min": [None],
                "soft_max": [None],
                "hard_max": [None],
            }
        )
        result = compute_constraint_violations(
            sample_polars_df, outlier_settings, config
        )
        assert result.is_empty()


class TestComputeColumnOutlierSummary:
    """Test compute_column_outlier_summary function."""

    def test_basic_summary(self):
        """Test basic summary computation."""
        outlier_data = pl.DataFrame(
            {
                "survey_key": ["K001", "K002", "K003"],
                "column name": ["col1", "col1", "col2"],
                "outlier reason": ["outlier", "no outlier", "outlier"],
                "min_value": [1, 1, 5],
                "max_value": [100, 100, 200],
                "mean": [50.0, 50.0, 100.0],
                "median": [45.0, 45.0, 95.0],
                "std": [25.0, 25.0, 50.0],
                "iqr": [30.0, 30.0, 60.0],
                "lower_bound": [10.0, 10.0, 20.0],
                "upper_bound": [90.0, 90.0, 180.0],
            }
        )
        result = compute_column_outlier_summary(outlier_data, "survey_key")
        assert isinstance(result, pl.DataFrame)
        assert "outlier count" in result.columns

    def test_empty_dataframe(self):
        """Test with empty DataFrame."""
        df = pl.DataFrame()
        result = compute_column_outlier_summary(df, "survey_key")
        assert result.is_empty()


# ============================================================================
# SETTINGS FUNCTION TESTS
# ============================================================================


class TestLoadDefaultSettings:
    """Test load_default_settings function."""

    @patch("datasure.checks.outliers.load_check_settings")
    def test_load_with_saved_settings(self, mock_load):
        """Test loading with saved settings."""
        mock_load.return_value = {"survey_id": "test_id"}
        config = OutlierSettings(survey_key="key", survey_id="default_id")
        result = load_default_settings("settings.json", config)
        assert result.survey_id == "test_id"
        assert result.survey_key == "key"

    @patch("datasure.checks.outliers.load_check_settings")
    def test_load_with_empty_settings(self, mock_load):
        """Test loading with empty saved settings."""
        mock_load.return_value = {}
        config = OutlierSettings(survey_key="key", survey_id="id")
        result = load_default_settings("settings.json", config)
        assert result.survey_id == "id"
        assert result.survey_key == "key"


# ============================================================================
# INTEGRATION TESTS
# ============================================================================


class TestIntegration:
    """Integration tests for the outliers module."""

    def test_complete_outlier_workflow(
        self, sample_polars_df, outlier_settings, outlier_column_config
    ):
        """Test complete outlier detection workflow."""
        # Compute outliers
        outlier_data = compute_outlier_output(
            sample_polars_df, outlier_settings, outlier_column_config
        )

        # Compute summary
        summary = compute_column_outlier_summary(outlier_data, "survey_key")

        # Verify results
        assert isinstance(outlier_data, pl.DataFrame)
        assert isinstance(summary, pl.DataFrame)
        assert not outlier_data.is_empty()

    def test_constraint_workflow(
        self, sample_polars_df, outlier_settings, outlier_column_config
    ):
        """Test constraint violation workflow."""
        # Compute violations
        violations = compute_constraint_violations(
            sample_polars_df, outlier_settings, outlier_column_config
        )

        # Verify results
        assert isinstance(violations, pl.DataFrame)


# ============================================================================
# Additional Core Logic Tests for Coverage
# ============================================================================


class TestGetOutlierCols:
    """Test get_outlier_cols function."""

    def test_with_numpy_array(self):
        """Test with numpy array in outlier_cols."""
        import numpy as np
        import pandas as pd

        from datasure.checks.outliers import get_outlier_cols

        df = pd.DataFrame(
            {
                "outlier_cols": [
                    np.array(["col1"]),
                    np.array(["col2"]),
                ]
            }
        )
        result = get_outlier_cols(df)
        assert result == ["col1", "col2"]

    def test_with_list(self):
        """Test with list in outlier_cols."""
        import pandas as pd

        from datasure.checks.outliers import get_outlier_cols

        df = pd.DataFrame(
            {
                "outlier_cols": [
                    ["col1", "col2"],
                    ["col3"],
                ]
            }
        )
        result = get_outlier_cols(df)
        assert result == ["col1", "col2", "col3"]

    def test_mixed_types(self):
        """Test with mixed numpy array and list."""
        import numpy as np
        import pandas as pd

        from datasure.checks.outliers import get_outlier_cols

        df = pd.DataFrame(
            {
                "outlier_cols": [
                    np.array(["col1"]),
                    ["col2", "col3"],
                ]
            }
        )
        result = get_outlier_cols(df)
        assert result == ["col1", "col2", "col3"]


class TestComputeMetrics:
    """Test metrics computation functions."""

    def test_compute_constraint_metrics(self):
        """Test _compute_constraint_metrics function."""
        from datasure.checks.outliers import _compute_constraint_metrics

        violation_data = pl.DataFrame(
            {
                "column name": ["col1", "col1", "col2", "col3"],
                "violation reason": [
                    "Value is below hard minimum 0",
                    "Value is below soft minimum 5",
                    "Value is above soft maximum 100",
                    "Value is above hard maximum 150",
                ],
            }
        )

        metrics = _compute_constraint_metrics(violation_data)

        assert metrics.columns_checked == 3
        assert metrics.total_violations == 4
        assert metrics.hard_min_violations == 1
        assert metrics.soft_min_violations == 1
        assert metrics.soft_max_violations == 1
        assert metrics.hard_max_violations == 1

    def test_compute_outlier_metrics_with_enumerator(self):
        """Test _compute_outlier_metrics with enumerator column."""
        from datasure.checks.outliers import _compute_outlier_metrics

        outliers_data = pl.DataFrame(
            {
                "column name": ["col1", "col1", "col2"],
                "outlier reason": [
                    "Value is below lower bound 10.0",
                    "Value is above upper bound 100.0",
                    "no outlier",
                ],
                "enumerator": ["enum1", "enum2", "enum1"],
            }
        )

        metrics = _compute_outlier_metrics(outliers_data, "enumerator")

        assert metrics.columns_checked == 2
        assert metrics.columns_with_outliers == 1
        assert metrics.total_outliers == 2
        assert metrics.enumerators_with_outliers == 2

    def test_compute_outlier_metrics_without_enumerator(self):
        """Test _compute_outlier_metrics without enumerator column."""
        from datasure.checks.outliers import _compute_outlier_metrics

        outliers_data = pl.DataFrame(
            {
                "column name": ["col1", "col2"],
                "outlier reason": [
                    "Value is below lower bound 10.0",
                    "no outlier",
                ],
            }
        )

        metrics = _compute_outlier_metrics(outliers_data, None)

        assert metrics.columns_checked == 2
        assert metrics.columns_with_outliers == 1
        assert metrics.total_outliers == 1
        assert metrics.enumerators_with_outliers == 0


class TestComputeOutlierOutputEdgeCases:
    """Test compute_outlier_output edge cases."""

    def test_with_grouped_columns_single_column(self):
        """Test outlier detection with grouped columns (single column)."""
        data = pl.DataFrame(
            {
                "survey_key": ["K001", "K002", "K003"],
                "numeric_col1": [1.0, 2.0, 100.0],
            }
        )

        settings = OutlierSettings(survey_key="survey_key")

        column_config = pl.DataFrame(
            [
                {
                    "column_name": ["numeric_col1"],
                    "grouped_columns": False,
                    "outlier_enabled": True,
                    "outlier_method": OutlierMethod.IQR.value,
                    "outlier_multiplier": 1.5,
                    "outlier_threshold": 2,
                }
            ]
        )

        result = compute_outlier_output(data, settings, column_config)

        assert not result.is_empty()
        assert "outlier reason" in result.columns

    def test_with_grouped_columns_multiple(self):
        """Test outlier detection with grouped columns (multiple columns)."""
        data = pl.DataFrame(
            {
                "survey_key": ["K001", "K002", "K003"],
                "numeric_col1": [1.0, 2.0, 3.0],
                "numeric_col2": [10.0, 20.0, 100.0],
            }
        )

        settings = OutlierSettings(survey_key="survey_key")

        column_config = pl.DataFrame(
            [
                {
                    "column_name": ["numeric_col1", "numeric_col2"],
                    "grouped_columns": True,
                    "outlier_enabled": True,
                    "outlier_method": OutlierMethod.IQR.value,
                    "outlier_multiplier": 1.5,
                    "outlier_threshold": 2,
                }
            ]
        )

        result = compute_outlier_output(data, settings, column_config)

        assert not result.is_empty()
        assert "column name" in result.columns

    def test_with_ungrouped_multiple_columns(self):
        """Test outlier detection with ungrouped multiple columns."""
        data = pl.DataFrame(
            {
                "survey_key": ["K001", "K002", "K003"],
                "numeric_col1": [1.0, 2.0, 100.0],
                "numeric_col2": [10.0, 20.0, 30.0],
            }
        )

        settings = OutlierSettings(survey_key="survey_key")

        column_config = pl.DataFrame(
            [
                {
                    "column_name": ["numeric_col1", "numeric_col2"],
                    "grouped_columns": False,
                    "outlier_enabled": True,
                    "outlier_method": OutlierMethod.SD.value,
                    "outlier_multiplier": 3.0,
                    "outlier_threshold": 2,
                }
            ]
        )

        result = compute_outlier_output(data, settings, column_config)

        assert not result.is_empty()
        assert len(result["column name"].unique()) == 2


class TestConstraintValidation:
    """Test constraint bounds validation."""

    def test_constraint_bounds_all_none(self):
        """Test ConstraintBounds with all None values."""
        bounds = ConstraintBounds()
        assert bounds.hard_min is None
        assert bounds.soft_min is None
        assert bounds.soft_max is None
        assert bounds.hard_max is None

    def test_constraint_bounds_partial(self):
        """Test ConstraintBounds with partial values."""
        bounds = ConstraintBounds(soft_min=10, soft_max=100)
        assert bounds.soft_min == 10
        assert bounds.soft_max == 100
        assert bounds.hard_min is None
        assert bounds.hard_max is None

    def test_constraint_bounds_invalid_order(self):
        """Test ConstraintBounds with invalid hierarchy."""
        with pytest.raises(ValidationError, match="must be <="):
            ConstraintBounds(hard_min=100, soft_min=50)

    def test_constraint_bounds_negative_values(self):
        """Test ConstraintBounds with negative values."""
        bounds = ConstraintBounds(
            hard_min=-100, soft_min=-50, soft_max=50, hard_max=100
        )
        assert bounds.hard_min == -100
        assert bounds.soft_min == -50


class TestOutlierColumnConfigValidation:
    """Test OutlierColumnConfig validation edge cases."""

    def test_pattern_required_for_non_exact(self):
        """Test that pattern is required for non-exact search types."""
        with pytest.raises(ValidationError, match="Pattern is required"):
            OutlierColumnConfig(
                search_type=SearchType.STARTSWITH,
                pattern=None,
                outlier_cols=["col1"],
                outlier_multiplier=1.5,
            )

    def test_soft_max_validation(self):
        """Test soft_max must be greater than soft_min."""
        with pytest.raises(ValidationError, match="soft_max must be greater"):
            OutlierColumnConfig(
                search_type=SearchType.EXACT,
                outlier_cols=["col1"],
                outlier_multiplier=1.5,
                soft_min=100,
                soft_max=50,
            )

    def test_valid_config_with_constraints(self):
        """Test valid configuration with all constraints."""
        config = OutlierColumnConfig(
            search_type=SearchType.EXACT,
            outlier_cols=["col1"],
            outlier_multiplier=1.5,
            soft_min=10,
            soft_max=100,
        )
        assert config.soft_min == 10
        assert config.soft_max == 100


class TestSafeToNumericEdgeCases:
    """Test safe_to_numeric edge cases."""

    def test_series_with_utf8_decimal(self):
        """Test Series conversion with UTF-8 decimal strings."""
        series = pl.Series(["1.5", "2.5", "3.5"])
        result = safe_to_numeric(series)
        assert result.dtype == pl.Float64

    def test_series_already_numeric(self):
        """Test Series that's already numeric."""
        series = pl.Series([1, 2, 3])
        result = safe_to_numeric(series)
        assert result.dtype in pl.NUMERIC_DTYPES

    def test_dataframe_without_column(self):
        """Test DataFrame without specifying column."""
        df = pl.DataFrame({"col1": [1, 2, 3]})
        with pytest.raises(ValueError, match="Column is required"):
            safe_to_numeric(df)

    def test_invalid_input_type(self):
        """Test with invalid input type."""
        with pytest.raises(TypeError, match="must be a Polars DataFrame or Series"):
            safe_to_numeric("invalid")

    def test_dataframe_utf8_conversion(self):
        """Test DataFrame column UTF-8 conversion."""
        df = pl.DataFrame({"col1": ["1.5", "2.5", "3.5"]})
        result = safe_to_numeric(df, "col1")
        assert result["col1"].dtype == pl.Float64


class TestExpandColNamesEdgeCases:
    """Test expand_col_names edge cases."""

    def test_invalid_col_names_type(self):
        """Test with invalid col_names type."""
        with pytest.raises(TypeError, match="col_names must be a list"):
            expand_col_names("not_a_list", "pattern")

    def test_empty_pattern(self):
        """Test with empty pattern."""
        with pytest.raises(TypeError, match="pattern must be provided"):
            expand_col_names(["col1", "col2"], "")

    def test_invalid_pattern_type(self):
        """Test with invalid pattern type."""
        with pytest.raises(TypeError, match="pattern must be a string"):
            expand_col_names(["col1", "col2"], 123)

    def test_invalid_search_type(self):
        """Test with invalid search type."""
        with pytest.raises(ValueError, match="Invalid search_type"):
            expand_col_names(["col1", "col2"], "col", search_type="invalid")

    def test_regex_pattern(self):
        """Test with regex pattern."""
        cols = ["col_1", "col_2", "other_1"]
        result = expand_col_names(cols, r"col_\d+", search_type="regex")
        assert result == ["col_1", "col_2"]


# ============================================================================
# Tests for Refactored Helper Functions
# ============================================================================


class TestEnsureList:
    """Test _ensure_list function."""

    def test_string_input(self):
        """Test converting string to list."""
        result = _ensure_list("column_name")
        assert result == ["column_name"]

    def test_list_input(self):
        """Test list input returns same list."""
        input_list = ["col1", "col2"]
        result = _ensure_list(input_list)
        assert result == ["col1", "col2"]

    def test_tuple_input(self):
        """Test tuple input converts to list."""
        result = _ensure_list(("col1", "col2"))
        assert result == ["col1", "col2"]

    def test_numpy_array_input(self):
        """Test numpy array input converts to list."""
        import numpy as np

        result = _ensure_list(np.array(["col1", "col2"]))
        assert result == ["col1", "col2"]


class TestBuildIncludeCols:
    """Test _build_include_cols function."""

    def test_all_columns_provided(self):
        """Test with all columns provided."""
        result = _build_include_cols(
            survey_key="key",
            survey_id="id",
            survey_date="date",
            enumerator="enum",
            team="team",
        )
        assert result == ["key", "id", "date", "enum", "team"]

    def test_only_survey_key(self):
        """Test with only survey key provided."""
        result = _build_include_cols(
            survey_key="key",
            survey_id=None,
            survey_date=None,
            enumerator=None,
            team=None,
        )
        assert result == ["key"]

    def test_deduplication(self):
        """Test that duplicate columns are removed."""
        result = _build_include_cols(
            survey_key="key",
            survey_id="key",  # Same as survey_key
            survey_date="date",
            enumerator=None,
            team=None,
        )
        assert result == ["key", "date"]

    def test_partial_columns(self):
        """Test with partial columns provided."""
        result = _build_include_cols(
            survey_key="key",
            survey_id="id",
            survey_date=None,
            enumerator="enum",
            team=None,
        )
        assert result == ["key", "id", "enum"]


class TestSanitizeDfForJoin:
    """Test sanitize_df_for_join function."""

    def test_no_overlapping_columns(self):
        """Test with no overlapping columns."""
        main_df = pl.DataFrame({"key": [1], "col1": [10]})
        join_df = pl.DataFrame({"key": [1], "col2": [20]})

        result = sanitize_df_for_join(main_df, join_df, "key")
        assert set(result.columns) == {"key", "col2"}

    def test_overlapping_columns(self):
        """Test with overlapping columns (excluding join key)."""
        main_df = pl.DataFrame({"key": [1], "col1": [10], "col2": [15]})
        join_df = pl.DataFrame({"key": [1], "col1": [20], "col3": [30]})

        result = sanitize_df_for_join(main_df, join_df, "key")
        # col1 should be excluded since it's in main_df
        assert "col1" not in result.columns or result.columns == ["key", "col3"]

    def test_join_key_preserved(self):
        """Test that join key is always preserved."""
        main_df = pl.DataFrame({"key": [1], "col1": [10]})
        join_df = pl.DataFrame({"key": [1], "col2": [20]})

        result = sanitize_df_for_join(main_df, join_df, "key")
        assert "key" in result.columns


class TestConvertSeriesToNumeric:
    """Test convert_series_to_numeric function."""

    def test_already_numeric_int(self):
        """Test series already numeric (int)."""
        series = pl.Series([1, 2, 3])
        result = convert_series_to_numeric(series)
        assert result.dtype == pl.Float64

    def test_already_numeric_float(self):
        """Test series already numeric (float)."""
        series = pl.Series([1.0, 2.0, 3.0])
        result = convert_series_to_numeric(series)
        assert result.dtype == pl.Float64

    def test_utf8_to_numeric(self):
        """Test UTF-8 string to numeric conversion."""
        series = pl.Series(["1.5", "2.5", "3.5"])
        result = convert_series_to_numeric(series)
        assert result.dtype == pl.Float64


class TestConvertDataframeColumnToNumeric:
    """Test convert_dataframe_column_to_numeric function."""

    def test_already_numeric(self):
        """Test column already numeric."""
        df = pl.DataFrame({"col": [1, 2, 3]})
        result = convert_dataframe_column_to_numeric(df, "col")
        assert result["col"].dtype == pl.Float64

    def test_utf8_column(self):
        """Test UTF-8 column conversion."""
        df = pl.DataFrame({"col": ["1.5", "2.5", "3.5"]})
        result = convert_dataframe_column_to_numeric(df, "col")
        assert result["col"].dtype == pl.Float64


class TestShouldExpandRow:
    """Test _should_expand_row function."""

    def test_exact_search_type(self):
        """Test row with exact search type should not expand."""
        row = {"search_type": "exact", "locked": False}
        assert _should_expand_row(row) is False

    def test_startswith_unlocked(self):
        """Test startswith search type unlocked should expand."""
        row = {"search_type": "startswith", "locked": False}
        assert _should_expand_row(row) is True

    def test_startswith_locked(self):
        """Test startswith search type locked should not expand."""
        row = {"search_type": "startswith", "locked": True}
        assert _should_expand_row(row) is False

    def test_contains_unlocked(self):
        """Test contains search type unlocked should expand."""
        row = {"search_type": "contains", "locked": False}
        assert _should_expand_row(row) is True


class TestComputeIqrBounds:
    """Test _compute_iqr_bounds function."""

    def test_basic_iqr_bounds(self):
        """Test basic IQR bounds computation."""
        series = pl.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        result = _compute_iqr_bounds(series, 1.5)

        assert isinstance(result, OutlierBounds)
        assert result.lower_bound < result.upper_bound

    def test_iqr_bounds_with_outlier(self):
        """Test IQR bounds with extreme values."""
        series = pl.Series([1, 2, 3, 4, 5, 100])
        result = _compute_iqr_bounds(series, 1.5)

        # 100 should be outside the upper bound
        assert result.upper_bound < 100


class TestComputeSdBounds:
    """Test _compute_sd_bounds function."""

    def test_basic_sd_bounds(self):
        """Test basic SD bounds computation."""
        series = pl.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        result = _compute_sd_bounds(series, 3.0)

        assert isinstance(result, OutlierBounds)
        assert result.lower_bound < result.upper_bound

    def test_sd_bounds_symmetry(self):
        """Test SD bounds are symmetric around mean."""
        series = pl.Series([1, 2, 3, 4, 5, 6, 7, 8, 9, 10])
        result = _compute_sd_bounds(series, 3.0)

        mean = series.mean()
        # Bounds should be equidistant from mean
        assert abs((mean - result.lower_bound) - (result.upper_bound - mean)) < 0.001


class TestBuildOutlierExpression:
    """Test _build_outlier_expression function."""

    def test_value_below_lower_bound(self):
        """Test expression flags values below lower bound."""
        df = pl.DataFrame({"col": [1, 50, 100]})
        expr = _build_outlier_expression("col", 10.0, 90.0)
        result = df.select(expr.alias("reason"))

        reasons = result["reason"].to_list()
        assert "below lower bound" in reasons[0]
        assert reasons[1] == "no outlier"
        assert "above upper bound" in reasons[2]

    def test_no_outliers(self):
        """Test expression when all values are within bounds."""
        df = pl.DataFrame({"col": [20, 50, 80]})
        expr = _build_outlier_expression("col", 10.0, 90.0)
        result = df.select(expr.alias("reason"))

        reasons = result["reason"].to_list()
        assert all(r == "no outlier" for r in reasons)


class TestAddStatisticsColumns:
    """Test _add_statistics_columns function."""

    def test_adds_all_columns(self):
        """Test that all statistics columns are added."""
        col_df = pl.DataFrame({"key": [1, 2, 3], "value": [10, 20, 30]})
        stats = OutlierStatistics(
            count=3,
            min_value=10.0,
            max_value=30.0,
            mean=20.0,
            median=20.0,
            sd=10.0,
            iqr=10.0,
            lower_bound=5.0,
            upper_bound=35.0,
        )

        result = _add_statistics_columns(
            col_df, stats, "Interquartile Range (IQR)", 1.5, "test_col"
        )

        expected_cols = [
            "min_value",
            "max_value",
            "mean",
            "median",
            "std",
            "iqr",
            "lower_bound",
            "upper_bound",
            "outlier_method",
            "outlier_multiplier",
            "column name",
        ]
        for col in expected_cols:
            assert col in result.columns

    def test_column_values(self):
        """Test that column values are correct."""
        col_df = pl.DataFrame({"key": [1], "value": [10]})
        stats = OutlierStatistics(
            count=1,
            min_value=10.0,
            max_value=10.0,
            mean=10.0,
            median=10.0,
            sd=0.0,
            iqr=0.0,
            lower_bound=10.0,
            upper_bound=10.0,
        )

        result = _add_statistics_columns(col_df, stats, "IQR", 1.5, "my_col")

        assert result["column name"][0] == "my_col"
        assert result["outlier_method"][0] == "IQR"
        assert result["outlier_multiplier"][0] == 1.5


class TestComputeColumnStats:
    """Test _compute_column_stats function."""

    def test_single_column(self):
        """Test stats computation for single column."""
        df = pl.DataFrame({"key": [1, 2, 3], "col1": [10.0, 20.0, 30.0]})
        stats, count = _compute_column_stats(
            df, ["col1"], False, "Interquartile Range (IQR)", 1.5
        )

        assert stats is not None
        assert isinstance(stats, OutlierStatistics)
        assert count == 3

    def test_grouped_columns(self):
        """Test stats computation for grouped columns."""
        df = pl.DataFrame(
            {"key": [1, 2, 3], "col1": [10.0, 20.0, 30.0], "col2": [15.0, 25.0, 35.0]}
        )
        stats, count = _compute_column_stats(
            df, ["col1", "col2"], True, "Interquartile Range (IQR)", 1.5
        )

        assert stats is not None
        assert isinstance(stats, OutlierStatistics)
        # Grouped count should be 6 (3 rows x 2 columns)
        assert count == 6

    def test_ungrouped_multiple_columns(self):
        """Test stats computation for ungrouped multiple columns returns None."""
        df = pl.DataFrame(
            {"key": [1, 2, 3], "col1": [10.0, 20.0, 30.0], "col2": [15.0, 25.0, 35.0]}
        )
        stats, count = _compute_column_stats(
            df, ["col1", "col2"], False, "Interquartile Range (IQR)", 1.5
        )

        # Should return None to signal per-column computation
        assert stats is None
        assert count == 0


class TestComputeSingleColumnStats:
    """Test _compute_single_column_stats function."""

    def test_basic_stats(self):
        """Test basic single column stats computation."""
        df = pl.DataFrame({"col": [10.0, 20.0, 30.0, 40.0, 50.0]})
        stats, count = _compute_single_column_stats(
            df, "col", "Interquartile Range (IQR)", 1.5
        )

        assert isinstance(stats, OutlierStatistics)
        assert count == 5
        assert stats.mean == 30.0

    def test_with_nulls(self):
        """Test stats computation with null values."""
        df = pl.DataFrame({"col": [10.0, None, 30.0, None, 50.0]})
        stats, count = _compute_single_column_stats(
            df, "col", "Interquartile Range (IQR)", 1.5
        )

        assert count == 3  # Only non-null values


class TestMergeOutlierResults:
    """Test _merge_outlier_results function."""

    def test_empty_results_list(self):
        """Test with empty results list."""
        admin_df = pl.DataFrame({"key": [1, 2, 3]})
        result = _merge_outlier_results([], admin_df, "key")

        assert result.is_empty()

    def test_empty_admin_data(self):
        """Test with empty admin data."""
        results = [pl.DataFrame({"key": [1], "outlier": ["yes"]})]
        admin_df = pl.DataFrame()
        result = _merge_outlier_results(results, admin_df, "key")

        assert not result.is_empty()
        assert "outlier" in result.columns

    def test_merge_with_admin_data(self):
        """Test merge with admin data."""
        # Results must have same schema for concat
        results = [
            pl.DataFrame({"key": [1, 2], "outlier": ["yes", "no"]}),
            pl.DataFrame({"key": [3, 4], "outlier": ["no", "yes"]}),
        ]
        admin_df = pl.DataFrame({"key": [1, 2, 3, 4], "name": ["A", "B", "C", "D"]})
        result = _merge_outlier_results(results, admin_df, "key")

        assert "name" in result.columns
        assert "outlier" in result.columns
        assert result.height == 4


class TestProcessOutlierConfigs:
    """Test _process_outlier_configs function."""

    def test_disabled_config_skipped(self):
        """Test that disabled configurations are skipped."""
        data = pl.DataFrame({"key": [1, 2], "col1": [10.0, 20.0]})
        config = pl.DataFrame(
            {
                "column_name": [["col1"]],
                "outlier_enabled": [False],
                "grouped_columns": [False],
                "outlier_method": ["Interquartile Range (IQR)"],
                "outlier_multiplier": [1.5],
                "outlier_threshold": [2],
            }
        )

        results = _process_outlier_configs(data, config, "key")
        assert results == []

    def test_enabled_config_processed(self):
        """Test that enabled configurations are processed."""
        data = pl.DataFrame(
            {"key": [1, 2, 3, 4, 5], "col1": [10.0, 20.0, 30.0, 40.0, 50.0]}
        )
        config = pl.DataFrame(
            {
                "column_name": [["col1"]],
                "outlier_enabled": [True],
                "grouped_columns": [False],
                "outlier_method": ["Interquartile Range (IQR)"],
                "outlier_multiplier": [1.5],
                "outlier_threshold": [2],
            }
        )

        results = _process_outlier_configs(data, config, "key")
        assert len(results) == 1
        assert not results[0].is_empty()


class TestProcessSingleConfig:
    """Test _process_single_config function."""

    def test_single_column_config(self):
        """Test processing single column configuration."""
        data = pl.DataFrame(
            {"key": [1, 2, 3, 4, 5], "col1": [10.0, 20.0, 30.0, 40.0, 100.0]}
        )
        row = {
            "column_name": ["col1"],
            "grouped_columns": False,
            "outlier_enabled": True,
            "outlier_method": "Interquartile Range (IQR)",
            "outlier_multiplier": 1.5,
            "outlier_threshold": 2,
        }

        results = _process_single_config(data, row, "key")

        assert len(results) == 1
        assert "outlier reason" in results[0].columns

    def test_multiple_columns_ungrouped(self):
        """Test processing multiple ungrouped columns."""
        data = pl.DataFrame(
            {
                "key": [1, 2, 3, 4, 5],
                "col1": [10.0, 20.0, 30.0, 40.0, 50.0],
                "col2": [15.0, 25.0, 35.0, 45.0, 55.0],
            }
        )
        row = {
            "column_name": ["col1", "col2"],
            "grouped_columns": False,
            "outlier_enabled": True,
            "outlier_method": "Interquartile Range (IQR)",
            "outlier_multiplier": 1.5,
            "outlier_threshold": 2,
        }

        results = _process_single_config(data, row, "key")

        # Should return one result per column
        assert len(results) == 2

    def test_multiple_columns_grouped(self):
        """Test processing multiple grouped columns."""
        data = pl.DataFrame(
            {
                "key": [1, 2, 3, 4, 5],
                "col1": [10.0, 20.0, 30.0, 40.0, 50.0],
                "col2": [15.0, 25.0, 35.0, 45.0, 55.0],
            }
        )
        row = {
            "column_name": ["col1", "col2"],
            "grouped_columns": True,
            "outlier_enabled": True,
            "outlier_method": "Interquartile Range (IQR)",
            "outlier_multiplier": 1.5,
            "outlier_threshold": 2,
        }

        results = _process_single_config(data, row, "key")

        # Should still return one result per column
        assert len(results) == 2


class TestProcessSingleColumnOutliers:
    """Test _process_single_column_outliers function."""

    def test_basic_outlier_detection(self):
        """Test basic outlier detection for single column."""
        df = pl.DataFrame(
            {"key": [1, 2, 3, 4, 5], "col": [10.0, 20.0, 30.0, 40.0, 100.0]}
        )
        stats = OutlierStatistics(
            count=5,
            min_value=10.0,
            max_value=100.0,
            mean=40.0,
            median=30.0,
            sd=35.0,
            iqr=20.0,
            lower_bound=0.0,
            upper_bound=60.0,
        )

        result = _process_single_column_outliers(
            df_polars=df,
            col="col",
            survey_key="key",
            outlier_stats=stats,
            outlier_method="Interquartile Range (IQR)",
            outlier_multiplier=1.5,
            min_threshold=3,
            non_null_count=5,
        )

        assert "outlier reason" in result.columns
        assert "column name" in result.columns
        assert "column value" in result.columns

        # Check that 100.0 is flagged as outlier
        outlier_flags = result.filter(pl.col("column value") == 100.0)["outlier reason"]
        assert "above upper bound" in outlier_flags[0]

    def test_below_threshold(self):
        """Test when non-null count is below threshold."""
        df = pl.DataFrame({"key": [1, 2], "col": [10.0, 100.0]})
        stats = OutlierStatistics(
            count=2,
            min_value=10.0,
            max_value=100.0,
            mean=55.0,
            median=55.0,
            sd=45.0,
            iqr=45.0,
            lower_bound=0.0,
            upper_bound=60.0,
        )

        result = _process_single_column_outliers(
            df_polars=df,
            col="col",
            survey_key="key",
            outlier_stats=stats,
            outlier_method="Interquartile Range (IQR)",
            outlier_multiplier=1.5,
            min_threshold=5,  # Higher than non_null_count
            non_null_count=2,
        )

        # All should be "no outlier" since count < threshold
        assert all(r == "no outlier" for r in result["outlier reason"].to_list())


# ============================================================================
# Tests for _update_unlocked_cols and update_unlocked_cols
# ============================================================================


class TestUpdateUnlockedCols:
    """Test _update_unlocked_cols function."""

    def test_exact_search_type_not_expanded(self):
        """Test that exact search type rows are not expanded."""
        config = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["col1"]],
                "locked": [False],
            }
        )
        col_names = ["col1", "col2", "col3"]
        result = _update_unlocked_cols(config, col_names)

        assert result.height == 1
        assert result["column_name"][0].to_list() == ["col1"]

    def test_startswith_unlocked_expanded(self):
        """Test that startswith unlocked rows get expanded."""
        config = pl.DataFrame(
            {
                "search_type": ["startswith"],
                "pattern": ["num_"],
                "column_name": [["num_"]],
                "locked": [False],
            }
        )
        col_names = ["num_1", "num_2", "other_col"]
        result = _update_unlocked_cols(config, col_names)

        assert result.height == 1
        assert result["outlier_cols"][0].to_list() == ["num_1", "num_2"]

    def test_locked_row_not_expanded(self):
        """Test that locked rows are not expanded."""
        config = pl.DataFrame(
            {
                "search_type": ["startswith"],
                "pattern": ["num_"],
                "column_name": [["num_1"]],
                "locked": [True],
            }
        )
        col_names = ["num_1", "num_2", "num_3"]
        result = _update_unlocked_cols(config, col_names)

        assert result.height == 1
        # Should not have outlier_cols since it wasn't expanded
        assert "outlier_cols" not in result.columns

    def test_missing_required_columns_raises(self):
        """Test that missing required columns raises ValueError."""
        config = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
            }
        )
        with pytest.raises(ValueError, match="Missing required columns"):
            _update_unlocked_cols(config, ["col1"])

    def test_multiple_rows_mixed(self):
        """Test with multiple rows of mixed search types."""
        config = pl.DataFrame(
            {
                "search_type": ["exact", "contains", "startswith"],
                "pattern": [None, "age", "hh_"],
                "column_name": [["income"], ["age"], ["hh_"]],
                "locked": [False, False, True],
            }
        )
        col_names = ["income", "age_1", "age_2", "hh_member_1", "hh_member_2"]
        result = _update_unlocked_cols(config, col_names)

        assert result.height == 3

    def test_endswith_unlocked_expanded(self):
        """Test endswith search type with unlocked rows."""
        config = pl.DataFrame(
            {
                "search_type": ["endswith"],
                "pattern": ["_age"],
                "column_name": [["_age"]],
                "locked": [False],
            }
        )
        col_names = ["member_age", "head_age", "income"]
        result = _update_unlocked_cols(config, col_names)

        assert result["outlier_cols"][0].to_list() == ["member_age", "head_age"]

    def test_regex_unlocked_expanded(self):
        """Test regex search type with unlocked rows."""
        config = pl.DataFrame(
            {
                "search_type": ["regex"],
                "pattern": [r"var_\d+"],
                "column_name": [["var_"]],
                "locked": [False],
            }
        )
        col_names = ["var_1", "var_2", "other"]
        result = _update_unlocked_cols(config, col_names)

        assert result["outlier_cols"][0].to_list() == ["var_1", "var_2"]


class TestUpdateUnlockedColsPublic:
    """Test update_unlocked_cols public wrapper."""

    def test_delegates_to_private(self):
        """Test that public wrapper delegates to private implementation."""
        config = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["col1"]],
                "locked": [False],
            }
        )
        col_names = ["col1", "col2"]

        result_public = update_unlocked_cols(config, col_names)
        result_private = _update_unlocked_cols(config, col_names)

        assert result_public.shape == result_private.shape
        assert result_public.columns == result_private.columns


# ============================================================================
# Additional Edge Case Tests for Refactored Functions
# ============================================================================


class TestComputeColumnStatsEdgeCases:
    """Additional edge case tests for _compute_column_stats."""

    def test_single_column_with_nulls(self):
        """Test single column stats with null values."""
        df = pl.DataFrame(
            {"key": [1, 2, 3, 4, 5], "col1": [10.0, None, 30.0, None, 50.0]}
        )
        stats, count = _compute_column_stats(
            df, ["col1"], False, OutlierMethod.IQR.value, 1.5
        )

        assert stats is not None
        assert count == 3

    def test_single_column_sd_method(self):
        """Test single column stats with SD method."""
        df = pl.DataFrame(
            {"key": [1, 2, 3, 4, 5], "col1": [10.0, 20.0, 30.0, 40.0, 50.0]}
        )
        stats, count = _compute_column_stats(
            df, ["col1"], False, OutlierMethod.SD.value, 3.0
        )

        assert stats is not None
        assert stats.sd is not None
        assert count == 5

    def test_grouped_columns_with_different_ranges(self):
        """Test grouped stats with columns having different value ranges."""
        df = pl.DataFrame(
            {
                "key": [1, 2, 3],
                "col1": [1.0, 2.0, 3.0],
                "col2": [100.0, 200.0, 300.0],
            }
        )
        stats, count = _compute_column_stats(
            df, ["col1", "col2"], True, OutlierMethod.IQR.value, 1.5
        )

        assert stats is not None
        assert count == 6
        # Mean should reflect the combined range
        assert stats.mean > 3.0

    def test_grouped_three_columns(self):
        """Test grouped stats with three columns."""
        df = pl.DataFrame(
            {
                "key": [1, 2],
                "a": [10.0, 20.0],
                "b": [30.0, 40.0],
                "c": [50.0, 60.0],
            }
        )
        stats, count = _compute_column_stats(
            df, ["a", "b", "c"], True, OutlierMethod.IQR.value, 1.5
        )

        assert stats is not None
        assert count == 6


class TestComputeSingleColumnStatsEdgeCases:
    """Additional edge case tests for _compute_single_column_stats."""

    def test_sd_method(self):
        """Test with SD method."""
        df = pl.DataFrame({"col": [10.0, 20.0, 30.0, 40.0, 50.0]})
        stats, count = _compute_single_column_stats(
            df, "col", OutlierMethod.SD.value, 3.0
        )

        assert isinstance(stats, OutlierStatistics)
        assert count == 5
        assert stats.sd is not None

    def test_all_same_values(self):
        """Test column where all values are identical."""
        df = pl.DataFrame({"col": [5.0, 5.0, 5.0, 5.0, 5.0]})
        stats, count = _compute_single_column_stats(
            df, "col", OutlierMethod.IQR.value, 1.5
        )

        assert count == 5
        assert stats.mean == 5.0
        assert stats.iqr == 0.0

    def test_two_values(self):
        """Test with minimal data (two values)."""
        df = pl.DataFrame({"col": [1.0, 100.0]})
        stats, count = _compute_single_column_stats(
            df, "col", OutlierMethod.IQR.value, 1.5
        )

        assert count == 2
        assert stats.min_value == 1.0
        assert stats.max_value == 100.0

    def test_all_nulls(self):
        """Test column with all null values."""
        df = pl.DataFrame({"col": pl.Series([None, None, None], dtype=pl.Float64)})
        stats, count = _compute_single_column_stats(
            df, "col", OutlierMethod.IQR.value, 1.5
        )

        assert count == 0


class TestMergeOutlierResultsEdgeCases:
    """Additional edge case tests for _merge_outlier_results."""

    def test_single_result(self):
        """Test merging a single result DataFrame."""
        results = [
            pl.DataFrame({"key": [1, 2], "outlier reason": ["outlier", "no outlier"]})
        ]
        admin_df = pl.DataFrame({"key": [1, 2], "name": ["A", "B"]})
        result = _merge_outlier_results(results, admin_df, "key")

        assert result.height == 2
        assert "name" in result.columns
        assert "outlier reason" in result.columns

    def test_multiple_results_same_keys(self):
        """Test merging multiple results with overlapping keys."""
        results = [
            pl.DataFrame(
                {
                    "key": [1, 2],
                    "column name": ["col1", "col1"],
                    "outlier reason": ["outlier", "no outlier"],
                }
            ),
            pl.DataFrame(
                {
                    "key": [1, 2],
                    "column name": ["col2", "col2"],
                    "outlier reason": ["no outlier", "outlier"],
                }
            ),
        ]
        admin_df = pl.DataFrame({"key": [1, 2], "name": ["A", "B"]})
        result = _merge_outlier_results(results, admin_df, "key")

        assert result.height == 4
        assert "name" in result.columns

    def test_admin_data_with_extra_rows(self):
        """Test when admin data has rows not in results."""
        results = [pl.DataFrame({"key": [1], "outlier reason": ["outlier"]})]
        admin_df = pl.DataFrame({"key": [1, 2, 3], "name": ["A", "B", "C"]})
        result = _merge_outlier_results(results, admin_df, "key")

        # Left join from admin, so all admin rows present
        assert result.height == 3


class TestProcessOutlierConfigsEdgeCases:
    """Additional edge case tests for _process_outlier_configs."""

    def test_multiple_enabled_configs(self):
        """Test processing multiple enabled configurations."""
        data = pl.DataFrame(
            {
                "key": [1, 2, 3, 4, 5],
                "col1": [10.0, 20.0, 30.0, 40.0, 50.0],
                "col2": [15.0, 25.0, 35.0, 45.0, 55.0],
            }
        )
        config = pl.DataFrame(
            {
                "column_name": [["col1"], ["col2"]],
                "outlier_enabled": [True, True],
                "grouped_columns": [False, False],
                "outlier_method": [OutlierMethod.IQR.value, OutlierMethod.SD.value],
                "outlier_multiplier": [1.5, 3.0],
                "outlier_threshold": [2, 2],
            }
        )

        results = _process_outlier_configs(data, config, "key")
        assert len(results) == 2

    def test_mixed_enabled_disabled(self):
        """Test with mix of enabled and disabled configs."""
        data = pl.DataFrame(
            {
                "key": [1, 2, 3, 4, 5],
                "col1": [10.0, 20.0, 30.0, 40.0, 50.0],
                "col2": [15.0, 25.0, 35.0, 45.0, 55.0],
            }
        )
        config = pl.DataFrame(
            {
                "column_name": [["col1"], ["col2"]],
                "outlier_enabled": [True, False],
                "grouped_columns": [False, False],
                "outlier_method": [OutlierMethod.IQR.value, OutlierMethod.IQR.value],
                "outlier_multiplier": [1.5, 1.5],
                "outlier_threshold": [2, 2],
            }
        )

        results = _process_outlier_configs(data, config, "key")
        assert len(results) == 1

    def test_missing_outlier_enabled_defaults_to_false(self):
        """Test config without outlier_enabled column defaults to False."""
        data = pl.DataFrame(
            {"key": [1, 2, 3, 4, 5], "col1": [10.0, 20.0, 30.0, 40.0, 50.0]}
        )
        config = pl.DataFrame(
            {
                "column_name": [["col1"]],
                "grouped_columns": [False],
                "outlier_method": [OutlierMethod.IQR.value],
                "outlier_multiplier": [1.5],
                "outlier_threshold": [2],
            }
        )

        results = _process_outlier_configs(data, config, "key")
        assert results == []

    def test_empty_config(self):
        """Test with empty config DataFrame."""
        data = pl.DataFrame({"key": [1, 2, 3], "col1": [10.0, 20.0, 30.0]})
        config = pl.DataFrame(
            {
                "column_name": pl.Series([], dtype=pl.List(pl.Utf8)),
                "outlier_enabled": pl.Series([], dtype=pl.Boolean),
                "grouped_columns": pl.Series([], dtype=pl.Boolean),
                "outlier_method": pl.Series([], dtype=pl.Utf8),
                "outlier_multiplier": pl.Series([], dtype=pl.Float64),
                "outlier_threshold": pl.Series([], dtype=pl.Int64),
            }
        )

        results = _process_outlier_configs(data, config, "key")
        assert results == []


class TestProcessSingleConfigEdgeCases:
    """Additional edge case tests for _process_single_config."""

    def test_sd_method(self):
        """Test processing with SD method."""
        data = pl.DataFrame(
            {"key": [1, 2, 3, 4, 5], "col1": [10.0, 20.0, 30.0, 40.0, 100.0]}
        )
        row = {
            "column_name": ["col1"],
            "grouped_columns": False,
            "outlier_enabled": True,
            "outlier_method": OutlierMethod.SD.value,
            "outlier_multiplier": 3.0,
            "outlier_threshold": 2,
        }

        results = _process_single_config(data, row, "key")
        assert len(results) == 1
        assert "outlier reason" in results[0].columns

    def test_high_threshold_no_outliers_flagged(self):
        """Test that high threshold prevents outlier flagging."""
        data = pl.DataFrame({"key": [1, 2, 3], "col1": [10.0, 20.0, 1000.0]})
        row = {
            "column_name": ["col1"],
            "grouped_columns": False,
            "outlier_enabled": True,
            "outlier_method": OutlierMethod.IQR.value,
            "outlier_multiplier": 1.5,
            "outlier_threshold": 100,  # Much higher than data count
        }

        results = _process_single_config(data, row, "key")
        assert len(results) == 1
        reasons = results[0]["outlier reason"].to_list()
        assert all(r == "no outlier" for r in reasons)

    def test_defaults_used_when_missing(self):
        """Test that defaults are used for missing config values."""
        data = pl.DataFrame(
            {"key": [1, 2, 3, 4, 5], "col1": [10.0, 20.0, 30.0, 40.0, 50.0]}
        )
        row = {
            "column_name": ["col1"],
        }

        results = _process_single_config(data, row, "key")
        assert len(results) == 1
        # Should use default IQR method
        assert results[0]["outlier_method"][0] == OutlierMethod.IQR.value

    def test_grouped_two_columns_with_outlier(self):
        """Test grouped columns where outlier exists in combined distribution."""
        data = pl.DataFrame(
            {
                "key": [1, 2, 3, 4, 5],
                "col1": [10.0, 20.0, 30.0, 40.0, 50.0],
                "col2": [10.0, 20.0, 30.0, 40.0, 500.0],
            }
        )
        row = {
            "column_name": ["col1", "col2"],
            "grouped_columns": True,
            "outlier_enabled": True,
            "outlier_method": OutlierMethod.IQR.value,
            "outlier_multiplier": 1.5,
            "outlier_threshold": 2,
        }

        results = _process_single_config(data, row, "key")
        assert len(results) == 2

        # col2 should have the 500.0 flagged as outlier
        col2_result = results[1]
        outlier_rows = col2_result.filter(pl.col("outlier reason") != "no outlier")
        assert outlier_rows.height > 0


class TestProcessSingleColumnOutliersEdgeCases:
    """Additional edge case tests for _process_single_column_outliers."""

    def test_all_values_within_bounds(self):
        """Test when all values are within bounds."""
        df = pl.DataFrame(
            {"key": [1, 2, 3, 4, 5], "col": [20.0, 30.0, 40.0, 50.0, 60.0]}
        )
        stats = OutlierStatistics(
            count=5,
            min_value=20.0,
            max_value=60.0,
            mean=40.0,
            median=40.0,
            sd=15.8,
            iqr=20.0,
            lower_bound=0.0,
            upper_bound=80.0,
        )

        result = _process_single_column_outliers(
            df_polars=df,
            col="col",
            survey_key="key",
            outlier_stats=stats,
            outlier_method=OutlierMethod.IQR.value,
            outlier_multiplier=1.5,
            min_threshold=3,
            non_null_count=5,
        )

        reasons = result["outlier reason"].to_list()
        assert all(r == "no outlier" for r in reasons)

    def test_multiple_outliers_both_sides(self):
        """Test with outliers on both lower and upper bounds."""
        df = pl.DataFrame(
            {
                "key": [1, 2, 3, 4, 5],
                "col": [-100.0, 30.0, 40.0, 50.0, 200.0],
            }
        )
        stats = OutlierStatistics(
            count=5,
            min_value=-100.0,
            max_value=200.0,
            mean=44.0,
            median=40.0,
            sd=100.0,
            iqr=20.0,
            lower_bound=10.0,
            upper_bound=70.0,
        )

        result = _process_single_column_outliers(
            df_polars=df,
            col="col",
            survey_key="key",
            outlier_stats=stats,
            outlier_method=OutlierMethod.IQR.value,
            outlier_multiplier=1.5,
            min_threshold=3,
            non_null_count=5,
        )

        reasons = result["outlier reason"].to_list()
        assert "below lower bound" in reasons[0]
        assert reasons[1] == "no outlier"
        assert "above upper bound" in reasons[4]

    def test_output_column_order(self):
        """Test that output has correct column order."""
        df = pl.DataFrame({"key": [1, 2, 3], "col": [10.0, 20.0, 30.0]})
        stats = OutlierStatistics(
            count=3,
            min_value=10.0,
            max_value=30.0,
            mean=20.0,
            median=20.0,
            sd=10.0,
            iqr=10.0,
            lower_bound=5.0,
            upper_bound=35.0,
        )

        result = _process_single_column_outliers(
            df_polars=df,
            col="col",
            survey_key="key",
            outlier_stats=stats,
            outlier_method=OutlierMethod.SD.value,
            outlier_multiplier=3.0,
            min_threshold=2,
            non_null_count=3,
        )

        expected_cols = [
            "key",
            "column name",
            "column value",
            "min_value",
            "max_value",
            "mean",
            "median",
            "std",
            "iqr",
            "lower_bound",
            "upper_bound",
            "outlier reason",
            "outlier_method",
            "outlier_multiplier",
        ]
        assert result.columns == expected_cols

    def test_sd_method_metadata(self):
        """Test that SD method metadata is correctly set."""
        df = pl.DataFrame({"key": [1, 2, 3], "col": [10.0, 20.0, 30.0]})
        stats = OutlierStatistics(
            count=3,
            min_value=10.0,
            max_value=30.0,
            mean=20.0,
            median=20.0,
            sd=10.0,
            iqr=10.0,
            lower_bound=5.0,
            upper_bound=35.0,
        )

        result = _process_single_column_outliers(
            df_polars=df,
            col="col",
            survey_key="key",
            outlier_stats=stats,
            outlier_method=OutlierMethod.SD.value,
            outlier_multiplier=3.0,
            min_threshold=2,
            non_null_count=3,
        )

        assert result["outlier_method"][0] == OutlierMethod.SD.value
        assert result["outlier_multiplier"][0] == 3.0
        assert result["column name"][0] == "col"
