"""Comprehensive tests for the outliers module with 100% code coverage."""

# Standard library imports
import importlib
import sys
from unittest.mock import MagicMock, patch

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
    # Rendering/UI helpers
    _create_search_type_info,
    _delete_outlier_column,
    _ensure_column_formats,
    _ensure_list,
    _format_constraint_validation_error,
    _format_outlier_validation_error,
    _merge_outlier_results,
    _process_outlier_configs,
    _process_single_column_outliers,
    _process_single_config,
    _render_column_grouping_options,
    _render_constraint_metrics,
    _render_constraint_options,
    _render_constraint_violations_table,
    _render_outlier_column_actions,
    _render_outlier_column_inspection,
    _render_outlier_metrics,
    _render_outlier_options,
    _render_outlier_settings_table,
    _render_outlier_table,
    _render_search_type_selection,
    _should_expand_row,
    _update_outlier_column_config,
    _update_unlocked_cols,
    _validate_constraint_settings,
    _validate_outlier_settings,
    # Statistical functions
    compute_column_outlier_summary,
    compute_constraint_violations,
    compute_outlier_output,
    compute_outlier_stats_polars,
    # Utility / top-level functions
    expand_col_names,
    get_outlier_cols,
    # Settings functions
    load_default_settings,
    outliers_report,
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


# =============================================================================
# HELPERS FOR ST-MOCKED TESTS
# =============================================================================


def _columns_side_effect(*args, **kwargs):
    """Return a list of MagicMocks whose length matches the columns argument."""
    n = args[0] if args else 1
    count = len(n) if isinstance(n, list | tuple) else int(n)
    return [MagicMock() for _ in range(count)]


def _make_st_mock():
    """Create a MagicMock for streamlit with sensible defaults."""
    st_mock = MagicMock()
    st_mock.columns.side_effect = _columns_side_effect
    return st_mock


# =============================================================================
# OUTLIERS_MOD FIXTURE (reimport with mocked streamlit)
# =============================================================================


@pytest.fixture
def outliers_mod():
    """Reimport the outliers module with mocked streamlit for decorator tests."""
    orig = sys.modules.pop("datasure.checks.outliers", None)
    orig_st = sys.modules.get("streamlit")

    st_mock = _make_st_mock()

    def mock_cache_data(func=None, **kwargs):
        if callable(func):
            return func
        return lambda f: f

    st_mock.cache_data = mock_cache_data
    st_mock.dialog = lambda *args, **kwargs: (lambda f: f)

    sys.modules["streamlit"] = st_mock
    try:
        with patch(
            "datasure.utils.onboarding_utils.demo_output_onboarding",
            lambda tab: (lambda f: f),
        ):
            mod = importlib.import_module("datasure.checks.outliers")
            sys.modules.pop("datasure.checks.outliers", None)
    finally:
        if orig_st is not None:
            sys.modules["streamlit"] = orig_st
        else:
            sys.modules.pop("streamlit", None)
        if orig is not None:
            sys.modules["datasure.checks.outliers"] = orig

    return mod


# =============================================================================
# TESTS: get_outlier_cols  (list branch)
# =============================================================================


class TestGetOutlierColsList:
    """Test get_outlier_cols function."""

    def test_list_branch_extends_cols(self):
        df = pd.DataFrame({"outlier_cols": [["col1", "col2"], ["col3"]]})
        result = get_outlier_cols(df)
        assert result == ["col1", "col2", "col3"]

    def test_numpy_array_branch(self):
        import numpy as np

        df = pd.DataFrame({"outlier_cols": [np.array(["col1"])]})
        result = get_outlier_cols(df)
        assert result == ["col1"]

    def test_empty_settings(self):
        df = pd.DataFrame({"outlier_cols": []})
        assert get_outlier_cols(df) == []


# =============================================================================
# TESTS: stack_outlier_columns  (empty-df branch via reimport)
# =============================================================================


class TestStackOutlierColumnsEmpty:
    """Test stack_outlier_columns edge cases with empty or invalid data."""

    def test_raises_on_empty_df(self, outliers_mod):
        df = pl.DataFrame({"col": []})
        with pytest.raises(ValueError, match="empty"):
            outliers_mod.stack_outlier_columns(df, ["col"])

    def test_raises_on_missing_column(self, outliers_mod):
        df = pl.DataFrame({"col1": [1.0, 2.0]})
        with pytest.raises(ValueError, match="does not exist"):
            outliers_mod.stack_outlier_columns(df, ["nonexistent"])

    def test_raises_on_non_numeric_column(self, outliers_mod):
        df = pl.DataFrame({"col": ["a", "b"]})
        with pytest.raises(ValueError, match="cannot be converted"):
            outliers_mod.stack_outlier_columns(df, ["col"])


# =============================================================================
# TESTS: _create_box_plot and _create_descriptive_stats (via reimport)
# =============================================================================


class TestCreateBoxPlot:
    """Test _create_box_plot function."""

    def test_returns_figure(self, outliers_mod):
        import plotly.graph_objects as go

        series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        fig = outliers_mod._create_box_plot(series, "Test Title")
        assert isinstance(fig, go.Figure)

    def test_figure_has_box_trace(self, outliers_mod):
        import plotly.graph_objects as go

        series = pd.Series([1.0, 2.0, 3.0])
        fig = outliers_mod._create_box_plot(series, "Col")
        assert len(fig.data) == 1
        assert isinstance(fig.data[0], go.Box)


class TestCreateDescriptiveStats:
    """Test _create_descriptive_stats function."""

    def test_returns_polars_dataframe(self, outliers_mod):
        df = pl.DataFrame({"val": [1.0, 2.0, 3.0, 4.0, 5.0]})
        result = outliers_mod._create_descriptive_stats(df)
        assert isinstance(result, pl.DataFrame)

    def test_has_statistic_and_value_columns(self, outliers_mod):
        df = pl.DataFrame({"val": [1.0, 2.0, 3.0]})
        result = outliers_mod._create_descriptive_stats(df)
        assert "statistic" in result.columns
        assert "value" in result.columns

    def test_renames_statistics(self, outliers_mod):
        df = pl.DataFrame({"val": [1.0, 2.0, 3.0]})
        result = outliers_mod._create_descriptive_stats(df)
        stat_names = result["statistic"].to_list()
        assert "Mean" in stat_names
        assert "Median (Q2)" in stat_names


# =============================================================================
# TESTS: _validate_constraint_settings
# =============================================================================


class TestValidateConstraintSettings:
    """Test _validate_constraint_settings function."""

    def test_valid_settings_returns_bounds_and_true(self):
        result, valid = _validate_constraint_settings(
            {"soft_min": 0.0, "soft_max": 100.0}
        )
        assert valid is True
        assert result is not None

    def test_invalid_hierarchy_returns_none_and_false(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            result, valid = _validate_constraint_settings(
                {"hard_min": 50.0, "soft_min": 10.0}
            )
        assert valid is False
        assert result is None
        st_mock.error.assert_called_once()

    def test_all_none_settings_valid(self):
        result, valid = _validate_constraint_settings(
            {"hard_min": None, "soft_min": None, "soft_max": None, "hard_max": None}
        )
        assert valid is True


# =============================================================================
# TESTS: _validate_outlier_settings
# =============================================================================


class TestValidateOutlierSettings:
    """Test _validate_outlier_settings function."""

    def test_valid_settings_returns_config_and_true(self):
        result, valid = _validate_outlier_settings(
            {
                "outlier_method": OutlierMethod.IQR.value,
                "outlier_multiplier": 1.5,
                "outlier_threshold": 20,
            }
        )
        assert valid is True
        assert result is not None

    def test_invalid_multiplier_returns_none_and_false(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            result, valid = _validate_outlier_settings(
                {
                    "outlier_method": OutlierMethod.IQR.value,
                    "outlier_multiplier": 0.0,
                    "outlier_threshold": 20,
                }
            )
        assert valid is False
        assert result is None
        st_mock.error.assert_called_once()


# =============================================================================
# TESTS: _format_constraint_validation_error
# =============================================================================


class TestFormatConstraintValidationError:
    """Test _format_constraint_validation_error function."""

    def test_value_error_type(self):
        try:
            ConstraintBounds(hard_min=50.0, soft_min=10.0)
        except ValidationError as e:
            msg = _format_constraint_validation_error(e)
        assert "Invalid constraint configuration" in msg

    def test_float_not_finite_type(self):
        """Test float_not_finite error type produces finite-number message."""
        mock_error = MagicMock()
        mock_error.errors.return_value = [
            {
                "loc": ("hard_min",),
                "msg": "value is not a finite number",
                "type": "float_not_finite",
            }
        ]
        msg = _format_constraint_validation_error(mock_error)
        assert "Invalid constraint configuration" in msg
        assert "finite number" in msg

    def test_value_error_type_uses_msg(self):
        """Test value_error type includes the custom validation message."""
        mock_error = MagicMock()
        mock_error.errors.return_value = [
            {
                "loc": ("hard_min",),
                "msg": "Bounds must follow hierarchy",
                "type": "value_error",
            }
        ]
        msg = _format_constraint_validation_error(mock_error)
        assert "Bounds must follow hierarchy" in msg

    def test_other_error_type(self):
        """Test other error types fall through to field: msg format."""
        try:
            ConstraintBounds(hard_min="not_a_number")
        except ValidationError as e:
            msg = _format_constraint_validation_error(e)
        assert "Invalid constraint configuration" in msg


# =============================================================================
# TESTS: _format_outlier_validation_error
# =============================================================================


class TestFormatOutlierValidationError:
    """Test _format_outlier_validation_error function."""

    def test_formats_error_message(self):
        """Test that a ValidationError is formatted into a user-friendly string."""
        try:
            OutlierOptionsConfig(
                outlier_method=OutlierMethod.IQR.value,
                outlier_multiplier=0.0,
                outlier_threshold=20,
            )
        except ValidationError as e:
            msg = _format_outlier_validation_error(e)
        assert "Invalid outlier configuration" in msg

    def test_includes_field_name(self):
        """Test that the field name appears in the formatted error."""
        try:
            OutlierOptionsConfig(
                outlier_method=OutlierMethod.IQR.value,
                outlier_multiplier=0.0,
                outlier_threshold=20,
            )
        except ValidationError as e:
            msg = _format_outlier_validation_error(e)
        assert "outlier_multiplier" in msg

    def test_value_error_number_not_ge_branch(self):
        """Test the value_error.number.not_ge branch via mocked error."""
        mock_error = MagicMock()
        mock_error.errors.return_value = [
            {
                "loc": ("outlier_multiplier",),
                "msg": "value must be greater than 0",
                "type": "value_error.number.not_ge",
            }
        ]
        msg = _format_outlier_validation_error(mock_error)
        assert "Invalid outlier configuration" in msg
        assert "greater than or equal" in msg

    def test_value_error_number_not_le_branch(self):
        """Test the value_error.number.not_le branch via mocked error."""
        mock_error = MagicMock()
        mock_error.errors.return_value = [
            {
                "loc": ("outlier_multiplier",),
                "msg": "value must be less than or equal to 10",
                "type": "value_error.number.not_le",
            }
        ]
        msg = _format_outlier_validation_error(mock_error)
        assert "Invalid outlier configuration" in msg
        assert "less than or equal" in msg


# =============================================================================
# TESTS: _ensure_column_formats
# =============================================================================


class TestEnsureColumnFormats:
    """Test _ensure_column_formats function."""

    def test_returns_polars_dataframe(self, outlier_column_config):
        result = _ensure_column_formats(outlier_column_config)
        assert isinstance(result, pl.DataFrame)

    def test_preserves_column_names(self, outlier_column_config):
        result = _ensure_column_formats(outlier_column_config)
        assert set(outlier_column_config.columns) == set(result.columns)

    def test_casts_types_correctly(self, outlier_column_config):
        result = _ensure_column_formats(outlier_column_config)
        assert result.schema["outlier_multiplier"] == pl.Float64
        assert result.schema["outlier_threshold"] == pl.Int64


# =============================================================================
# TESTS: _render_constraint_metrics
# =============================================================================


@pytest.fixture
def sample_violation_data():
    """Create sample constraint violation data."""
    return pl.DataFrame(
        {
            "survey_key": ["K001", "K002", "K003"],
            "column name": ["col1", "col1", "col2"],
            "violation reason": [
                "below hard minimum",
                "above soft maximum",
                "no violation",
            ],
        }
    )


class TestRenderConstraintMetrics:
    """Test _render_constraint_metrics function."""

    def test_calls_st_metric(self, sample_violation_data):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            _render_constraint_metrics(sample_violation_data)
        assert st_mock.metric.called or st_mock.columns.called


# =============================================================================
# TESTS: _render_outlier_metrics
# =============================================================================


@pytest.fixture
def sample_outlier_data():
    """Create sample outlier data."""
    return pl.DataFrame(
        {
            "survey_key": ["K001", "K002"],
            "column name": ["col1", "col1"],
            "outlier reason": ["Value is below lower bound 5.00", "no outlier"],
            "enumerator": ["E001", "E001"],
        }
    )


class TestRenderOutlierMetrics:
    """Test _render_outlier_metrics function."""

    def test_with_enumerator(self, sample_outlier_data, outlier_settings):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            _render_outlier_metrics(sample_outlier_data, outlier_settings)
        assert st_mock.metric.called or st_mock.columns.called

    def test_without_enumerator(self, sample_outlier_data):
        settings = OutlierSettings(
            survey_key="survey_key",
            survey_id="survey_id",
            survey_date=None,
            enumerator=None,
            team=None,
        )
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            _render_outlier_metrics(sample_outlier_data, settings)
        assert st_mock.columns.called


# =============================================================================
# TESTS: _render_constraint_violations_table
# =============================================================================


@pytest.fixture
def base_survey_data():
    """Create base survey data for rendering tests."""
    return pl.DataFrame(
        {
            "survey_key": ["K001", "K002"],
            "survey_id": ["S001", "S002"],
            "survey_date": ["2024-01-01", "2024-01-02"],
            "enumerator": ["E001", "E002"],
            "team": ["T1", "T2"],
        }
    )


class TestRenderConstraintViolationsTable:
    """Test _render_constraint_violations_table function."""

    def test_empty_data_shows_info(self, base_survey_data, outlier_settings):
        with patch("datasure.checks.outliers.st") as st_mock:
            _render_constraint_violations_table(
                base_survey_data,
                pl.DataFrame(),
                outlier_settings,
                "settings.json",
            )
        st_mock.info.assert_called_once()

    def test_non_empty_data_shows_dataframe(self, base_survey_data, outlier_settings):
        violation_data = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "column name": ["col1"],
                "violation reason": ["below soft minimum"],
            }
        )
        with (
            patch("datasure.checks.outliers.st") as st_mock,
            patch("datasure.checks.outliers.load_check_settings", return_value={}),
            patch("datasure.checks.outliers.save_check_settings"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.multiselect.return_value = []
            _render_constraint_violations_table(
                base_survey_data,
                violation_data,
                outlier_settings,
                "settings.json",
            )
        st_mock.dataframe.assert_called_once()

    def test_non_empty_with_extra_display_cols(
        self, base_survey_data, outlier_settings
    ):
        violation_data = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "violation reason": ["above hard maximum"],
            }
        )
        with (
            patch("datasure.checks.outliers.st") as st_mock,
            patch("datasure.checks.outliers.load_check_settings", return_value={}),
            patch("datasure.checks.outliers.save_check_settings"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.multiselect.return_value = []
            _render_constraint_violations_table(
                base_survey_data,
                violation_data,
                outlier_settings,
                "settings.json",
            )
        st_mock.dataframe.assert_called_once()


# =============================================================================
# TESTS: _render_outlier_table
# =============================================================================


class TestRenderOutlierTable:
    """Test _render_outlier_table function."""

    def test_empty_data_shows_info(self, base_survey_data, outlier_settings):
        with patch("datasure.checks.outliers.st") as st_mock:
            _render_outlier_table(
                base_survey_data,
                pl.DataFrame(),
                outlier_settings,
                "settings.json",
            )
        st_mock.info.assert_called_once()

    def test_non_empty_data_shows_dataframe(self, base_survey_data, outlier_settings):
        outliers_data = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "column name": ["col1"],
                "outlier reason": ["Value is above upper bound 50.00"],
            }
        )
        with (
            patch("datasure.checks.outliers.st") as st_mock,
            patch("datasure.checks.outliers.load_check_settings", return_value={}),
            patch("datasure.checks.outliers.save_check_settings"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.multiselect.return_value = []
            _render_outlier_table(
                base_survey_data,
                outliers_data,
                outlier_settings,
                "settings.json",
            )
        st_mock.dataframe.assert_called_once()


# =============================================================================
# TESTS: _render_outlier_column_inspection
# =============================================================================


class TestRenderOutlierColumnInspection:
    """Test _render_outlier_column_inspection function."""

    def test_empty_outlier_data_shows_info(self, base_survey_data, outlier_settings):
        with patch("datasure.checks.outliers.st") as st_mock:
            _render_outlier_column_inspection(
                base_survey_data, pl.DataFrame(), outlier_settings, "settings.json"
            )
        st_mock.info.assert_called_once()

    def test_no_selected_col_returns_early(self, base_survey_data, outlier_settings):
        outliers_data = pl.DataFrame(
            {"survey_key": ["K001"], "column name": ["survey_key"]}
        )
        with (
            patch("datasure.checks.outliers.st") as st_mock,
            patch("datasure.checks.outliers.load_check_settings", return_value={}),
            patch("datasure.checks.outliers.save_check_settings"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.selectbox.return_value = None
            _render_outlier_column_inspection(
                base_survey_data, outliers_data, outlier_settings, "settings.json"
            )
        st_mock.info.assert_called()

    def test_col_not_in_data_raises(self, base_survey_data, outlier_settings):
        outliers_data = pl.DataFrame(
            {"survey_key": ["K001"], "column name": ["nonexistent_col"]}
        )
        with (
            patch("datasure.checks.outliers.st") as st_mock,
            patch("datasure.checks.outliers.load_check_settings", return_value={}),
            patch("datasure.checks.outliers.save_check_settings"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.selectbox.return_value = "nonexistent_col"
            with pytest.raises(ValueError, match="not present in the data"):
                _render_outlier_column_inspection(
                    base_survey_data,
                    outliers_data,
                    outlier_settings,
                    "settings.json",
                )

    def test_normal_path_renders_chart_and_table(self, outlier_settings):
        data = pl.DataFrame(
            {
                "survey_key": ["K001", "K002"],
                "survey_id": ["S001", "S002"],
                "survey_date": ["2024-01-01", "2024-01-02"],
                "enumerator": ["E001", "E002"],
                "team": ["T1", "T2"],
                "numeric_col1": [1.0, 100.0],
            }
        )
        outliers_data = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "column name": ["numeric_col1"],
                "outlier reason": ["Value is above upper bound 50.00"],
            }
        )
        with (
            patch("datasure.checks.outliers.st") as st_mock,
            patch("datasure.checks.outliers.load_check_settings", return_value={}),
            patch("datasure.checks.outliers.save_check_settings"),
            patch("datasure.checks.outliers._create_descriptive_stats") as mock_desc,
            patch("datasure.checks.outliers._create_box_plot") as mock_box,
        ):
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.selectbox.return_value = "numeric_col1"
            st_mock.multiselect.return_value = []
            mock_desc.return_value = pl.DataFrame(
                {"statistic": ["count"], "value": ["2"]}
            )
            mock_box.return_value = MagicMock()
            _render_outlier_column_inspection(
                data, outliers_data, outlier_settings, "settings.json"
            )
        st_mock.dataframe.assert_called()


# =============================================================================
# TESTS: _create_search_type_info
# =============================================================================


class TestCreateSearchTypeInfo:
    """Test _create_search_type_info function."""

    def test_exact_search_type(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            _create_search_type_info(SearchType.EXACT.value)
        st_mock.info.assert_called_once()

    def test_startswith_search_type(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            _create_search_type_info(SearchType.STARTSWITH.value)
        st_mock.info.assert_called_once()

    def test_endswith_search_type(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            _create_search_type_info(SearchType.ENDSWITH.value)
        st_mock.info.assert_called_once()

    def test_contains_search_type(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            _create_search_type_info(SearchType.CONTAINS.value)
        st_mock.info.assert_called_once()

    def test_regex_search_type(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            _create_search_type_info(SearchType.REGEX.value)
        st_mock.info.assert_called_once()

    def test_unknown_type(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            _create_search_type_info("unknown_type")
        st_mock.info.assert_called_once()


# =============================================================================
# TESTS: _render_search_type_selection
# =============================================================================


class TestRenderSearchTypeSelection:
    """Test _render_search_type_selection function."""

    def test_exact_search_type(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.selectbox.return_value = SearchType.EXACT.value
            st_mock.multiselect.return_value = ["col1"]
            search_type, pattern, cols, lock = _render_search_type_selection(
                ["col1", "col2"]
            )
        assert search_type == SearchType.EXACT.value
        assert pattern is None
        assert cols == ["col1"]

    def test_pattern_search_type_with_pattern(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.selectbox.return_value = SearchType.STARTSWITH.value
            st_mock.text_input.return_value = "num"
            search_type, pattern, cols, lock = _render_search_type_selection(
                ["num_col1", "num_col2", "other"]
            )
        assert search_type == SearchType.STARTSWITH.value
        assert pattern == "num"
        assert "num_col1" in cols

    def test_pattern_search_type_no_pattern(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.selectbox.return_value = SearchType.CONTAINS.value
            st_mock.text_input.return_value = ""
            search_type, pattern, cols, lock = _render_search_type_selection(
                ["col1", "col2"]
            )
        assert cols == []
        assert lock is None


# =============================================================================
# TESTS: _render_column_grouping_options
# =============================================================================


class TestRenderColumnGroupingOptions:
    """Test _render_column_grouping_options function."""

    def test_basic_render(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.toggle.return_value = False
            group_cols, lock_cols = _render_column_grouping_options(
                ["col1", "col2"], SearchType.EXACT.value
            )
        assert isinstance(group_cols, bool)
        assert isinstance(lock_cols, bool)

    def test_returns_toggle_values(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.toggle.side_effect = [True, False]
            group_cols, lock_cols = _render_column_grouping_options(
                ["col1", "col2"], SearchType.STARTSWITH.value
            )
        assert group_cols is True
        assert lock_cols is False


# =============================================================================
# TESTS: _render_outlier_options
# =============================================================================


class TestRenderOutlierOptions:
    """Test _render_outlier_options function."""

    def test_outliers_enabled_returns_settings(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.toggle.return_value = True
            st_mock.selectbox.return_value = OutlierMethod.IQR.value
            st_mock.number_input.side_effect = [1.5, 20]
            enabled, settings, valid = _render_outlier_options()
        assert enabled is True
        assert settings is not None
        assert valid is True

    def test_outliers_enabled_sd_method(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.toggle.return_value = True
            st_mock.selectbox.return_value = OutlierMethod.SD.value
            st_mock.number_input.side_effect = [3.0, 30]
            enabled, settings, valid = _render_outlier_options()
        assert enabled is True
        assert valid is True

    def test_outliers_disabled_returns_none(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.toggle.return_value = False
            enabled, settings, valid = _render_outlier_options()
        assert enabled is False
        assert settings is None
        assert valid is True


# =============================================================================
# TESTS: _render_constraint_options
# =============================================================================


class TestRenderConstraintOptions:
    """Test _render_constraint_options function."""

    def test_valid_settings_returns_true(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.number_input.return_value = None
            settings, valid = _render_constraint_options()
        assert valid is True

    def test_invalid_settings_calls_error(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.number_input.side_effect = [50.0, 10.0, None, None]
            settings, valid = _render_constraint_options()
        assert valid is False
        st_mock.error.assert_called_once()


# =============================================================================
# TESTS: _render_outlier_settings_table
# =============================================================================


class TestRenderOutlierSettingsTable:
    """Test _render_outlier_settings_table function."""

    def test_renders_dataframe(self, outlier_column_config):
        with patch("datasure.checks.outliers.st") as st_mock:
            _render_outlier_settings_table(outlier_column_config)
        st_mock.dataframe.assert_called_once()


# =============================================================================
# TESTS: _render_outlier_column_actions
# =============================================================================


class TestRenderOutlierColumnActions:
    """Test _render_outlier_column_actions function."""

    def test_empty_settings_shows_info(self):
        with (
            patch("datasure.checks.outliers.st") as st_mock,
            patch(
                "datasure.checks.outliers.duckdb_get_table",
                return_value=pl.DataFrame(),
            ),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            _render_outlier_column_actions("proj1", "page1", ["col1"])
        assert st_mock.info.call_count >= 1

    def test_non_empty_settings_calls_render_table(self, outlier_column_config):
        with (
            patch("datasure.checks.outliers.st") as st_mock,
            patch(
                "datasure.checks.outliers.duckdb_get_table",
                return_value=outlier_column_config,
            ),
            patch(
                "datasure.checks.outliers._render_outlier_settings_table"
            ) as mock_render,
            patch("datasure.checks.outliers._delete_outlier_column"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            _render_outlier_column_actions("proj1", "page1", ["col1"])
        mock_render.assert_called_once()


# =============================================================================
# TESTS: _update_outlier_column_config
# =============================================================================


class TestUpdateOutlierColumnConfig:
    """Test _update_outlier_column_config function."""

    def test_empty_existing_config_saves_new(self):
        settings = OutlierOptionsConfig(
            outlier_method=OutlierMethod.IQR,
            outlier_multiplier=1.5,
            outlier_threshold=20,
        )
        bounds = ConstraintBounds(soft_min=0.0, soft_max=100.0)
        with (
            patch(
                "datasure.checks.outliers.duckdb_get_table",
                return_value=pl.DataFrame(),
            ),
            patch("datasure.checks.outliers.duckdb_save_table") as mock_save,
        ):
            _update_outlier_column_config(
                "proj1",
                "page1",
                "exact",
                None,
                ["col1"],
                False,
                False,
                True,
                settings,
                bounds,
            )
        mock_save.assert_called_once()

    def test_non_empty_existing_config_concatenates(self, outlier_column_config):
        settings = OutlierOptionsConfig(
            outlier_method=OutlierMethod.IQR,
            outlier_multiplier=1.5,
            outlier_threshold=20,
        )
        bounds = ConstraintBounds(soft_min=0.0, soft_max=100.0)
        with (
            patch(
                "datasure.checks.outliers.duckdb_get_table",
                return_value=outlier_column_config,
            ),
            patch("datasure.checks.outliers.duckdb_save_table") as mock_save,
        ):
            _update_outlier_column_config(
                "proj1",
                "page1",
                "exact",
                None,
                ["col2"],
                False,
                False,
                True,
                settings,
                bounds,
            )
        mock_save.assert_called_once()
        saved_df = mock_save.call_args[0][1]
        assert len(saved_df) == 2

    def test_outlier_settings_none(self):
        bounds = ConstraintBounds(soft_min=0.0, soft_max=100.0)
        with (
            patch(
                "datasure.checks.outliers.duckdb_get_table",
                return_value=pl.DataFrame(),
            ),
            patch("datasure.checks.outliers.duckdb_save_table") as mock_save,
        ):
            _update_outlier_column_config(
                "proj1",
                "page1",
                "exact",
                None,
                ["col1"],
                False,
                False,
                False,
                None,
                bounds,
            )
        mock_save.assert_called_once()


# =============================================================================
# TESTS: _delete_outlier_column
# =============================================================================


class TestDeleteOutlierColumn:
    """Test _delete_outlier_column function."""

    def test_empty_settings_shows_info(self):
        with patch("datasure.checks.outliers.st") as st_mock:
            _delete_outlier_column("proj1", "page1", pl.DataFrame())
        st_mock.info.assert_called_once()

    def test_non_empty_shows_selectbox_and_button(self, outlier_column_config):
        with patch("datasure.checks.outliers.st") as st_mock:
            st_mock.selectbox.return_value = "0 - exact - "
            st_mock.button.return_value = False
            _delete_outlier_column("proj1", "page1", outlier_column_config)
        st_mock.selectbox.assert_called_once()

    def test_delete_on_button_click(self, outlier_column_config):
        with (
            patch("datasure.checks.outliers.st") as st_mock,
            patch("datasure.checks.outliers.duckdb_save_table") as mock_save,
        ):
            st_mock.selectbox.return_value = "0 - exact - "
            st_mock.button.return_value = True
            _delete_outlier_column("proj1", "page1", outlier_column_config)
        mock_save.assert_called_once()


# =============================================================================
# TESTS: outliers_report_settings (via reimport)
# =============================================================================


class TestOutliersReportSettings:
    """Test outliers_report_settings function."""

    def test_returns_outlier_settings(self, outliers_mod):
        config = OutlierSettings(
            survey_key="survey_key",
            survey_id="survey_id",
            survey_date="survey_date",
            enumerator="enumerator",
            team="team",
        )
        with (
            patch(
                "datasure.checks.outliers.load_default_settings", return_value=config
            ),
            patch("datasure.checks.outliers.load_check_settings", return_value={}),
            patch("datasure.checks.outliers.save_check_settings"),
            patch("datasure.checks.outliers.trigger_save"),
        ):
            outliers_mod.st.selectbox.return_value = "survey_key"
            result = outliers_mod.outliers_report_settings(
                "settings.json",
                config,
                ["survey_key", "survey_id", "enumerator", "team"],
                ["survey_date"],
            )
        assert isinstance(result, outliers_mod.OutlierSettings)


# =============================================================================
# TESTS: _add_outlier_column (via reimport)
# =============================================================================


class TestAddOutlierColumn:
    """Test _add_outlier_column function."""

    def test_no_cols_selected_does_not_save(self, outliers_mod):
        """When no columns selected, skip grouping/options rendering."""
        mock_sel = MagicMock(return_value=(SearchType.EXACT.value, None, [], None))
        with patch.object(outliers_mod, "_render_search_type_selection", mock_sel):
            outliers_mod._add_outlier_column("proj1", "page1", ["col1", "col2"])
        mock_sel.assert_called_once()

    def test_with_cols_selected_renders_options(self, outliers_mod):
        """When columns are selected, all option panels are rendered."""
        settings = OutlierOptionsConfig(
            outlier_method=OutlierMethod.IQR,
            outlier_multiplier=1.5,
            outlier_threshold=20,
        )
        mock_sel = MagicMock(
            return_value=(SearchType.EXACT.value, None, ["col1"], None)
        )
        mock_grp = MagicMock(return_value=(False, False))
        mock_out = MagicMock(return_value=(True, settings, True))
        mock_con = MagicMock(return_value=(ConstraintBounds(), True))
        with (
            patch.object(outliers_mod, "_render_search_type_selection", mock_sel),
            patch.object(outliers_mod, "_render_column_grouping_options", mock_grp),
            patch.object(outliers_mod, "_render_outlier_options", mock_out),
            patch.object(outliers_mod, "_render_constraint_options", mock_con),
        ):
            outliers_mod.st.button.return_value = False
            outliers_mod._add_outlier_column("proj1", "page1", ["col1", "col2"])
        mock_grp.assert_called_once()
        mock_out.assert_called_once()
        mock_con.assert_called_once()


# =============================================================================
# TESTS: outliers_report (main function)
# =============================================================================


@pytest.fixture
def survey_columns_mock():
    """Create a mock ColumnByType for outliers_report tests."""
    from datasure.utils.dataframe_utils import ColumnByType

    return ColumnByType(
        all_columns=[
            "survey_key",
            "survey_id",
            "survey_date",
            "enumerator",
            "team",
            "col1",
        ],
        categorical_columns=["survey_key", "survey_id", "enumerator", "team"],
        datetime_columns=["survey_date"],
        numeric_columns=["col1"],
        boolean_columns=[],
    )


@pytest.fixture
def outlier_config_dict():
    """Create a default outlier config dict for outliers_report tests."""
    return {
        "survey_key": "survey_key",
        "survey_id": "survey_id",
        "survey_date": "survey_date",
        "enumerator": "enumerator",
        "team": "team",
    }


class TestOutliersReport:
    """Test outliers_report main function."""

    def test_empty_column_config_returns_early(
        self, base_survey_data, survey_columns_mock, outlier_config_dict
    ):
        settings = OutlierSettings(**outlier_config_dict)
        with (
            patch("datasure.checks.outliers.st") as st_mock,
            patch(
                "datasure.checks.outliers.outliers_report_settings",
                return_value=settings,
            ),
            patch("datasure.checks.outliers._render_outlier_column_actions"),
            patch(
                "datasure.checks.outliers.duckdb_get_table",
                return_value=pl.DataFrame(),
            ),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            outliers_report(
                "proj1",
                "page1",
                base_survey_data,
                "settings.json",
                outlier_config_dict,
                survey_columns_mock,
            )
        st_mock.title.assert_called()

    def test_with_constraint_violations(
        self,
        base_survey_data,
        survey_columns_mock,
        outlier_config_dict,
        outlier_column_config,
    ):
        settings = OutlierSettings(**outlier_config_dict)
        constraint_violations = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "column name": ["col1"],
                "violation reason": ["below soft minimum"],
            }
        )
        with (
            patch("datasure.checks.outliers.st") as st_mock,
            patch(
                "datasure.checks.outliers.outliers_report_settings",
                return_value=settings,
            ),
            patch("datasure.checks.outliers._render_outlier_column_actions"),
            patch(
                "datasure.checks.outliers.duckdb_get_table",
                return_value=outlier_column_config,
            ),
            patch("datasure.checks.outliers.duckdb_save_table"),
            patch(
                "datasure.checks.outliers.compute_constraint_violations",
                return_value=constraint_violations,
            ),
            patch(
                "datasure.checks.outliers.compute_outlier_output",
                return_value=pl.DataFrame(),
            ),
            patch("datasure.checks.outliers._render_constraint_metrics"),
            patch("datasure.checks.outliers._render_constraint_violations_table"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            outliers_report(
                "proj1",
                "page1",
                base_survey_data,
                "settings.json",
                outlier_config_dict,
                survey_columns_mock,
            )
        st_mock.info.assert_called()

    def test_with_outliers(
        self,
        base_survey_data,
        survey_columns_mock,
        outlier_config_dict,
        outlier_column_config,
    ):
        settings = OutlierSettings(**outlier_config_dict)
        outlier_data = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "column name": ["col1"],
                "outlier reason": ["Value is above upper bound 50.00"],
            }
        )
        with (
            patch("datasure.checks.outliers.st") as st_mock,
            patch(
                "datasure.checks.outliers.outliers_report_settings",
                return_value=settings,
            ),
            patch("datasure.checks.outliers._render_outlier_column_actions"),
            patch(
                "datasure.checks.outliers.duckdb_get_table",
                return_value=outlier_column_config,
            ),
            patch("datasure.checks.outliers.duckdb_save_table"),
            patch(
                "datasure.checks.outliers.compute_constraint_violations",
                return_value=pl.DataFrame(),
            ),
            patch(
                "datasure.checks.outliers.compute_outlier_output",
                return_value=outlier_data,
            ),
            patch("datasure.checks.outliers._render_outlier_metrics"),
            patch("datasure.checks.outliers._render_outlier_column_inspection"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            outliers_report(
                "proj1",
                "page1",
                base_survey_data,
                "settings.json",
                outlier_config_dict,
                survey_columns_mock,
            )
        st_mock.info.assert_called()
