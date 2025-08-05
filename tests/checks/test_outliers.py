"""Test the outliers module."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import plotly.graph_objects as go  # type: ignore
import pytest  # type: ignore
import streamlit as st  # noqa: F401

from datasure.checks.outliers import (
    compute_column_outlier_summary,
    compute_outlier_output,
    compute_outlier_stats,
    create_violin_plot,
    display_outlier_column_summary,
    display_outlier_metrics,
    display_outlier_output,
    expand_col_names,
    get_outlier_cols,
    inspect_outliers_columns,
    load_default_settings,
    outliers_report,
    outliers_report_settings,  # noqa: F401
    plot_col_distribution,
    stack_outlier_columns,
    update_outlier_settings,
    update_unlocked_cols,
)


@pytest.fixture
def sample_data():
    """Sample data for testing."""
    return pd.DataFrame(
        {
            "survey_id": ["S001", "S002", "S003", "S004", "S005"],
            "enumerator": ["E001", "E002", "E001", "E003", "E002"],
            "survey_key": ["K001", "K002", "K003", "K004", "K005"],
            "numeric_col1": [1.0, 2.0, 3.0, 100.0, 5.0],  # outlier: 100.0
            "numeric_col2": [10.0, 20.0, 30.0, 40.0, 500.0],  # outlier: 500.0
            "string_col": ["A", "B", "C", "D", "E"],
            "datetime_col": pd.date_range("2023-01-01", periods=5),
            "mixed_col": [1, "text", 3.0, 4, 5],
            "hh_member_1_age": [25, 30, 35, 40, 45],
            "hh_member_2_age": [20, 25, 30, 35, 40],
            "hh_member_3_age": [15, 20, 25, 30, 35],
        }
    )


@pytest.fixture
def outlier_settings_data():
    """Sample outlier settings data for testing."""
    return pd.DataFrame(
        {
            "search_type": ["exact", "startswith", "contains"],
            "pattern": [None, "hh_", "age"],
            "outlier_cols": [
                ["numeric_col1"],
                ["hh_member_1_age", "hh_member_2_age"],
                ["hh_member_1_age"],
            ],
            "lock_cols": [True, False, False],
            "grouped_cols": [False, True, False],
            "outlier_method": [
                "Interquartile Range (IQR)",
                "Standard Deviation (SD)",
                "Interquartile Range (IQR)",
            ],
            "outlier_multiplier": [1.5, 3.0, 1.5],
            "soft_min": [None, None, 10.0],
            "soft_max": [None, None, 50.0],
        }
    )


@pytest.fixture
def outliers_data():
    """Data specifically designed for outlier testing."""
    return pd.DataFrame(
        {
            "survey_key": ["K001", "K002", "K003", "K004", "K005"],
            "survey_id": ["S001", "S002", "S003", "S004", "S005"],
            "enumerator": ["E001", "E002", "E001", "E003", "E002"],
            "normal_col": [1.0, 2.0, 3.0, 4.0, 5.0],  # No outliers
            "outlier_col": [1.0, 2.0, 3.0, 4.0, 1000.0],  # Clear outlier
            "special_values": [1.0, 2.0, -999, 0.777, 5.0],  # Special values
        }
    )


@pytest.fixture
def large_dataset():
    """Create a larger dataset for threshold testing."""
    np.random.seed(42)
    size = 100
    return pd.DataFrame(
        {
            "survey_key": [f"K{i:03d}" for i in range(size)],
            "survey_id": [f"S{i:03d}" for i in range(size)],
            "enumerator": [f"E{i % 10:03d}" for i in range(size)],
            "normal_values": np.random.normal(50, 10, size),
            "outlier_values": np.concatenate(
                [np.random.normal(50, 10, size - 5), [200, 300, 400, 500, 600]]
            ),
        }
    )


@pytest.fixture
def empty_dataframe():
    """Empty DataFrame for edge case testing."""
    return pd.DataFrame()


@pytest.fixture
def numeric_series():
    """Numeric series for statistical calculations."""
    return pd.Series([1, 2, 3, 4, 5, 100])  # Contains one clear outlier


class TestLoadDefaultSettings:
    """Test load_default_settings function."""

    def test_load_default_settings_file_exists(self):
        """Test when settings file exists."""
        with (
            patch("datasure.checks.outliers.get_check_config_settings") as mock_config,
            patch("datasure.checks.outliers.os.path.exists") as mock_exists,
            patch("datasure.checks.outliers.load_check_settings") as mock_load,
        ):
            mock_config.return_value = (
                None,
                None,
                "key1",
                "id1",
                None,
                "enum1",
                None,
                None,
            )
            mock_exists.return_value = True
            mock_load.return_value = {
                "survey_id": "test_id",
                "enumerator": "test_enum",
                "survey_key": "test_key",
                "outlier_display_cols": ["col1", "col2"],
                "min_threshold": 25,
            }

            result = load_default_settings("project1", "settings.json", 1)

            assert result[0] == "test_id"
            assert result[1] == "test_enum"
            assert result[2] == "test_key"
            assert result[3] == ["col1", "col2"]
            assert result[4] == 25

    def test_load_default_settings_file_missing(self):
        """Test when settings file is missing."""
        with (
            patch("datasure.checks.outliers.get_check_config_settings") as mock_config,
            patch("datasure.checks.outliers.os.path.exists") as mock_exists,
        ):
            mock_config.return_value = (
                None,
                None,
                "key1",
                "id1",
                None,
                "enum1",
                None,
                None,
            )
            mock_exists.return_value = False

            result = load_default_settings("project1", "settings.json", 1)

            assert result[0] == "id1"
            assert result[1] == "enum1"
            assert result[2] == "key1"
            assert result[3] is None
            assert result[4] is None

    def test_load_default_settings_partial_config(self):
        """Test when settings file exists but has partial config."""
        with (
            patch("datasure.checks.outliers.get_check_config_settings") as mock_config,
            patch("datasure.checks.outliers.os.path.exists") as mock_exists,
            patch("datasure.checks.outliers.load_check_settings") as mock_load,
        ):
            mock_config.return_value = (
                None,
                None,
                "key1",
                "id1",
                None,
                "enum1",
                None,
                None,
            )
            mock_exists.return_value = True
            mock_load.return_value = {
                "survey_id": "test_id",
                # Missing other keys
            }

            result = load_default_settings("project1", "settings.json", 1)

            assert result[0] == "test_id"
            assert result[1] == "enum1"  # Falls back to config
            assert result[2] == "key1"  # Falls back to config
            assert result[3] is None  # Default
            assert result[4] is None  # Default


class TestExpandColNames:
    """Test expand_col_names function."""

    def test_expand_col_names_exact(self):
        """Test exact matching."""
        col_names = ["age", "income", "education"]
        result = expand_col_names(col_names, "age", "exact")
        assert result == ["age"]

    def test_expand_col_names_startswith(self):
        """Test startswith matching."""
        col_names = ["hh_member_1_age", "hh_member_2_age", "other_col"]
        result = expand_col_names(col_names, "hh_member", "startswith")
        assert result == ["hh_member_1_age", "hh_member_2_age"]

    def test_expand_col_names_endswith(self):
        """Test endswith matching."""
        col_names = ["hh_member_1_age", "hh_member_2_age", "other_col"]
        result = expand_col_names(col_names, "_age", "endswith")
        assert result == ["hh_member_1_age", "hh_member_2_age"]

    def test_expand_col_names_contains(self):
        """Test contains matching."""
        col_names = ["hh_member_1_age", "hh_member_2_age", "other_age"]
        result = expand_col_names(col_names, "member", "contains")
        assert result == ["hh_member_1_age", "hh_member_2_age"]

    def test_expand_col_names_regex(self):
        """Test regex matching."""
        col_names = ["var_1", "var_2", "other_col"]
        result = expand_col_names(col_names, r"var_\d+", "regex")
        assert result == ["var_1", "var_2"]

    def test_expand_col_names_invalid_input(self):
        """Test with invalid input."""
        with pytest.raises(TypeError):
            expand_col_names("not_a_list", "pattern", "exact")

        with pytest.raises(TypeError):
            expand_col_names(["col1"], None, "exact")

        with pytest.raises(ValueError):
            expand_col_names(["col1"], "pattern", "invalid_type")

    def test_expand_col_names_empty_pattern_string(self):
        """Test with empty pattern string."""
        col_names = ["col1", "col2"]
        with pytest.raises(TypeError):
            expand_col_names(col_names, "", "exact")


class TestUpdateUnlockedCols:
    """Test update_unlocked_cols function."""

    def test_update_unlocked_cols_basic(self, outlier_settings_data):
        """Test basic functionality."""
        col_names = [
            "hh_member_1_age",
            "hh_member_2_age",
            "hh_member_3_age",
            "numeric_col1",
        ]
        result = update_unlocked_cols(outlier_settings_data, col_names)

        assert isinstance(result, pd.DataFrame)
        assert "outlier_cols" in result.columns
        assert "lock_cols" in result.columns

    def test_update_unlocked_cols_missing_columns(self):
        """Test with missing essential columns."""
        df = pd.DataFrame({"other_col": [1, 2, 3]})
        col_names = ["col1", "col2"]

        with pytest.raises(
            ValueError, match="Essential column 'outlier_cols' is missing"
        ):
            update_unlocked_cols(df, col_names)

    def test_update_unlocked_cols_no_unlocked_rows(self):
        """Test when all rows are locked or exact."""
        df = pd.DataFrame(
            {
                "search_type": ["exact", "exact"],
                "pattern": [None, None],
                "outlier_cols": [["col1"], ["col2"]],
                "lock_cols": [True, True],
            }
        )
        col_names = ["col1", "col2"]

        result = update_unlocked_cols(df, col_names)
        assert result.equals(df)

    def test_update_unlocked_cols_missing_pattern(self):
        """Test with missing pattern for unlocked row."""
        df = pd.DataFrame(
            {
                "search_type": "startswith",
                "pattern": None,
                "outlier_cols": ["col1"],
                "lock_cols": False,
            }
        )
        col_names = ["col1", "col2"]

        with pytest.raises(ValueError):
            update_unlocked_cols(df, col_names)


class TestUpdateOutlierSettings:
    """Test update_outlier_settings function."""

    @patch("datasure.checks.outliers.duckdb_get_table")
    @patch("datasure.checks.outliers.duckdb_save_table")
    def test_update_outlier_settings_basic(self, mock_save, mock_get):
        """Test basic functionality."""
        mock_get.return_value.to_pandas.return_value = pd.DataFrame()

        update_outlier_settings(
            project_id="test_project",
            label="test_label",
            search_type="exact",
            outlier_cols=["col1"],
            outlier_method="Interquartile Range (IQR)",
            outlier_multiplier=1.5,
            grouped_cols=False,
            pattern=None,
            lock_cols=None,
            soft_min=None,
            soft_max=None,
        )

        mock_get.assert_called_once()
        mock_save.assert_called_once()

    def test_update_outlier_settings_invalid_inputs(self):
        """Test with invalid input types."""
        with pytest.raises(TypeError, match="outlier_cols must be a list"):
            update_outlier_settings(
                project_id="test",
                label="test",
                search_type="exact",
                outlier_cols="not_a_list",
                outlier_method="IQR",
                outlier_multiplier=1.5,
                grouped_cols=False,
                pattern=None,
                lock_cols=None,
                soft_min=None,
                soft_max=None,
            )

        with pytest.raises(TypeError, match="search_type must be a string"):
            update_outlier_settings(
                project_id="test",
                label="test",
                search_type=123,
                outlier_cols=["col1"],
                outlier_method="IQR",
                outlier_multiplier=1.5,
                grouped_cols=False,
                pattern=None,
                lock_cols=None,
                soft_min=None,
                soft_max=None,
            )

    @patch("datasure.checks.outliers.duckdb_get_table")
    @patch("datasure.checks.outliers.duckdb_save_table")
    def test_update_outlier_settings_with_existing_logs(self, mock_save, mock_get):
        """Test when existing logs are present."""
        existing_logs = pd.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "outlier_cols": [["old_col"]],
                "lock_cols": [False],
                "grouped_cols": [False],
                "outlier_method": ["IQR"],
                "outlier_multiplier": [1.5],
                "soft_min": [None],
                "soft_max": [None],
            }
        )
        mock_get.return_value.to_pandas.return_value = existing_logs

        update_outlier_settings(
            project_id="test_project",
            label="test_label",
            search_type="exact",
            outlier_cols=["col1"],
            outlier_method="Standard Deviation (SD)",
            outlier_multiplier=2.0,
            grouped_cols=True,
            pattern=None,
            lock_cols=True,
            soft_min=10.0,
            soft_max=100.0,
        )

        mock_get.assert_called_once()
        mock_save.assert_called_once()


class TestStackOutlierColumns:
    """Test stack_outlier_columns function."""

    def test_stack_outlier_columns_basic(self, sample_data):
        """Test basic functionality."""
        col_names = ["numeric_col1", "numeric_col2"]
        result = stack_outlier_columns(sample_data, col_names)

        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_data) * len(col_names)

    def test_stack_outlier_columns_empty_dataframe(self, empty_dataframe):
        """Test with empty DataFrame."""
        col_names = ["col1", "col2"]

        with pytest.raises(ValueError, match="The DataFrame is empty"):
            stack_outlier_columns(empty_dataframe, col_names)

    def test_stack_outlier_columns_missing_column(self, sample_data):
        """Test with missing column."""
        col_names = ["nonexistent_col"]

        with pytest.raises(ValueError, match="Column 'nonexistent_col' does not exist"):
            stack_outlier_columns(sample_data, col_names)

    def test_stack_outlier_columns_non_numeric(self, sample_data):
        """Test with non-numeric column that can't be converted."""
        col_names = ["string_col"]

        with pytest.raises(
            ValueError, match="Column 'string_col' cannot be converted to numeric type"
        ):
            stack_outlier_columns(sample_data, col_names)

    def test_stack_outlier_columns_single_column(self, sample_data):
        """Test with single column."""
        col_names = ["numeric_col1"]
        result = stack_outlier_columns(sample_data, col_names)

        assert isinstance(result, pd.Series)
        assert len(result) == len(sample_data)


class TestComputeOutlierStats:
    """Test compute_outlier_stats function."""

    def test_compute_outlier_stats_iqr_method(self, numeric_series):
        """Test with IQR method."""
        result = compute_outlier_stats(numeric_series, "Interquartile Range (IQR)", 1.5)

        assert isinstance(result, dict)
        expected_keys = [
            "count",
            "min_value",
            "max_value",
            "mean",
            "median",
            "sd",
            "iqr",
            "lower_bound",
            "upper_bound",
        ]
        for key in expected_keys:
            assert key in result

        assert result["count"] == 6
        assert result["min_value"] == 1
        assert result["max_value"] == 100

    def test_compute_outlier_stats_sd_method(self, numeric_series):
        """Test with Standard Deviation method."""
        result = compute_outlier_stats(numeric_series, "Standard Deviation (SD)", 2.0)

        assert isinstance(result, dict)
        expected_keys = [
            "count",
            "min_value",
            "max_value",
            "mean",
            "median",
            "sd",
            "iqr",
            "lower_bound",
            "upper_bound",
        ]
        for key in expected_keys:
            assert key in result

    def test_compute_outlier_stats_empty_series(self):
        """Test with empty series."""
        empty_series = pd.Series([])

        with pytest.raises(ValueError, match="The Series is empty"):
            compute_outlier_stats(empty_series, "Interquartile Range (IQR)", 1.5)

    def test_compute_outlier_stats_invalid_method(self, numeric_series):
        """Test with invalid outlier method."""
        with pytest.raises(ValueError, match="Invalid outlier type"):
            compute_outlier_stats(numeric_series, "Invalid Method", 1.5)

    def test_compute_outlier_stats_invalid_multiplier(self, numeric_series):
        """Test with invalid multiplier."""
        with pytest.raises(ValueError, match="Multiplier must be a positive number"):
            compute_outlier_stats(numeric_series, "Interquartile Range (IQR)", -1.5)

    def test_compute_outlier_stats_default_multipliers(self, numeric_series):
        """Test with default multipliers."""
        # Test IQR with None multiplier (should default to 1.5)
        result_iqr = compute_outlier_stats(
            numeric_series, "Interquartile Range (IQR)", None
        )
        assert "lower_bound" in result_iqr
        assert "upper_bound" in result_iqr

        # Test SD with None multiplier (should default to 3.0)
        result_sd = compute_outlier_stats(
            numeric_series, "Standard Deviation (SD)", None
        )
        assert "lower_bound" in result_sd
        assert "upper_bound" in result_sd


class TestComputeOutlierOutput:
    """Test compute_outlier_output function."""

    def test_compute_outlier_output_basic(self, sample_data, outlier_settings_data):
        """Test basic functionality."""
        result = compute_outlier_output(
            df=sample_data,
            outlier_settings=outlier_settings_data.iloc[:1],  # Use only first row
            display_cols=["enumerator"],
            min_threshold=5,
            survey_key="survey_key",
            survey_id="survey_id",
            enumerator="enumerator",
        )

        assert isinstance(result, pd.DataFrame)
        expected_columns = [
            "survey_key",
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
            "soft_min",
            "soft_max",
        ]
        for col in expected_columns:
            assert col in result.columns

    def test_compute_outlier_output_empty_dataframe(
        self, empty_dataframe, outlier_settings_data
    ):
        """Test with empty DataFrame."""
        with pytest.raises(ValueError, match="The DataFrame is empty"):
            compute_outlier_output(
                df=empty_dataframe,
                outlier_settings=outlier_settings_data,
                display_cols=[],
                min_threshold=5,
                survey_key="survey_key",
                survey_id="survey_id",
                enumerator="enumerator",
            )

    def test_compute_outlier_output_large_dataset(self, large_dataset):
        """Test with larger dataset and threshold logic."""
        outlier_settings = pd.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "outlier_cols": [["outlier_values"]],
                "lock_cols": [False],
                "grouped_cols": [False],
                "outlier_method": ["Interquartile Range (IQR)"],
                "outlier_multiplier": [1.5],
                "soft_min": [None],
                "soft_max": [None],
            }
        )

        result = compute_outlier_output(
            df=large_dataset,
            outlier_settings=outlier_settings,
            display_cols=["enumerator"],
            min_threshold=30,  # Set threshold below dataset size
            survey_key="survey_key",
            survey_id="survey_id",
            enumerator="enumerator",
        )

        assert isinstance(result, pd.DataFrame)
        assert "outlier reason" in result.columns

        # Should have some outliers flagged
        outliers = result[result["outlier reason"] != "no outlier"]
        assert len(outliers) > 0


class TestCreateViolinPlot:
    """Test create_violin_plot function."""

    def test_create_violin_plot_basic(self):
        """Test basic violin plot creation."""
        data = pd.Series([1, 2, 3, 4, 5, 100])
        title = "Test Variable"

        result = create_violin_plot(data, title)

        assert isinstance(result, go.Figure)
        assert len(result.data) == 1
        assert result.data[0].x0 == title

    def test_create_violin_plot_empty_data(self):
        """Test with empty data."""
        data = pd.Series([])
        title = "Empty Variable"

        result = create_violin_plot(data, title)

        assert isinstance(result, go.Figure)

    def test_create_violin_plot_single_value(self):
        """Test with single value."""
        data = pd.Series([42])
        title = "Single Value"

        result = create_violin_plot(data, title)

        assert isinstance(result, go.Figure)
        assert result.data[0].x0 == title


class TestPlotColDistribution:
    """Test plot_col_distribution function."""

    def test_plot_col_distribution_basic(self, sample_data):
        """Test basic functionality."""
        result = plot_col_distribution(sample_data, "numeric_col1")

        assert isinstance(result, go.Figure)
        assert len(result.data) == 1
        assert result.data[0].type == "histogram"

    def test_plot_col_distribution_missing_column(self, sample_data):
        """Test with missing column."""
        with pytest.raises(ValueError, match="Column 'nonexistent' does not exist"):
            plot_col_distribution(sample_data, "nonexistent")

    def test_plot_col_distribution_non_numeric(self, sample_data):
        """Test with non-numeric column."""
        with pytest.raises(ValueError, match="Column 'string_col' is not numeric"):
            plot_col_distribution(sample_data, "string_col")


class TestGetOutlierCols:
    """Test get_outlier_cols function."""

    def test_get_outlier_cols_basic(self, outlier_settings_data):
        """Test basic functionality."""
        result = get_outlier_cols(outlier_settings_data)

        assert isinstance(result, list)
        assert len(result) > 0

    def test_get_outlier_cols_with_arrays(self):
        """Test with numpy arrays in outlier_cols."""
        df = pd.DataFrame({"outlier_cols": [np.array(["col1"]), ["col2", "col3"]]})

        result = get_outlier_cols(df)
        assert "col1" in result
        assert "col2" in result
        assert "col3" in result


class TestComputeColumnOutlierSummary:
    """Test compute_column_outlier_summary function."""

    def test_compute_column_outlier_summary_basic(self):
        """Test basic functionality."""
        outlier_data = pd.DataFrame(
            {
                "survey_key": ["K001", "K002", "K003", "K001", "K002"],
                "column name": ["col1", "col1", "col1", "col2", "col2"],
                "outlier reason": [
                    "outlier",
                    "no outlier",
                    "outlier",
                    "outlier",
                    "no outlier",
                ],
                "min_value": [1, 1, 1, 5, 5],
                "max_value": [100, 100, 100, 200, 200],
                "mean": [50, 50, 50, 100, 100],
                "median": [45, 45, 45, 95, 95],
                "std": [25, 25, 25, 50, 50],
                "iqr": [30, 30, 30, 60, 60],
                "lower_bound": [10, 10, 10, 20, 20],
                "upper_bound": [90, 90, 90, 180, 180],
            }
        )

        result = compute_column_outlier_summary(outlier_data, "survey_key")

        assert isinstance(result, pd.DataFrame)
        assert "column name" in result.columns
        assert "outlier count" in result.columns
        assert len(result) == 2  # Two unique columns

    def test_compute_column_outlier_summary_empty(self, empty_dataframe):
        """Test with empty DataFrame."""
        result = compute_column_outlier_summary(empty_dataframe, "survey_key")
        assert result.empty


class TestDisplayFunctions:
    """Test display functions (mocked Streamlit calls)."""

    @patch("streamlit.dataframe")
    @patch("streamlit.info")
    def test_display_outlier_output_no_outliers(self, mock_info, mock_dataframe):
        """Test display when no outliers exist."""
        outlier_data = pd.DataFrame({"outlier reason": ["no outlier", "no outlier"]})

        display_outlier_output(outlier_data)
        mock_info.assert_called_once()
        mock_dataframe.assert_not_called()

    @patch("streamlit.dataframe")
    @patch("streamlit.info")
    def test_display_outlier_output_with_outliers(self, mock_info, mock_dataframe):
        """Test display when outliers exist."""
        outlier_data = pd.DataFrame(
            {
                "outlier reason": ["outlier", "no outlier"],
                "column name": ["col1", "col2"],
                "column value": [100, 50],
            }
        )

        display_outlier_output(outlier_data)
        mock_info.assert_not_called()
        mock_dataframe.assert_called_once()

    @patch("streamlit.dataframe")
    @patch("streamlit.title")
    def test_display_outlier_column_summary_basic(self, mock_title, mock_dataframe):
        """Test display column summary."""
        summary_data = pd.DataFrame(
            {
                "column name": ["col1"],
                "count": [10],
                "outlier count": [2],
            }
        )

        display_outlier_column_summary(summary_data)
        mock_title.assert_called_once()
        mock_dataframe.assert_called_once()

    @patch("streamlit.title")
    def test_display_outlier_column_summary_empty(self, mock_title):
        """Test display column summary with empty data."""
        with pytest.raises(ValueError, match="No outlier summary data available"):
            display_outlier_column_summary(pd.DataFrame())

    @patch("streamlit.columns")
    @patch("streamlit.title")
    def test_display_outlier_metrics_basic(self, mock_title, mock_columns):
        """Test display outlier metrics."""
        mock_col = MagicMock()
        mock_col.metric = MagicMock()
        mock_columns.return_value = [mock_col, mock_col, mock_col, mock_col]

        outliers_data = pd.DataFrame(
            {
                "outlier reason": ["outlier", "no outlier"],
                "column name": ["col1", "col2"],
                "enumerator": ["E1", "E2"],
            }
        )

        display_outlier_metrics(
            outliers_data, ["col1", "col2"], "survey_key", "survey_id", "enumerator"
        )
        mock_title.assert_called_once()
        mock_columns.assert_called_once()


class TestInspectOutliersColumns:
    """Test inspect_outliers_columns function."""

    @patch("streamlit.title")
    @patch("streamlit.info")
    def test_inspect_outliers_columns_empty_data(self, mock_info, mock_title):
        """Test with empty outlier data."""
        inspect_outliers_columns(
            data=pd.DataFrame(),
            outlier_data=pd.DataFrame(),
            col_summary=pd.DataFrame(),
            outlier_cols=[],
            display_cols=[],
            survey_key="survey_key",
            survey_id="survey_id",
            enumerator="enumerator",
        )

        mock_title.assert_called_once()
        mock_info.assert_called_once()


# Integration tests
class TestIntegration:
    """Integration tests for the outliers module."""

    def test_outlier_detection_workflow(self, sample_data, outlier_settings_data):
        """Test complete outlier detection workflow."""
        # Step 1: Compute outlier output
        outlier_data = compute_outlier_output(
            df=sample_data,
            outlier_settings=outlier_settings_data.iloc[:1],  # Use first row only
            display_cols=["enumerator"],
            min_threshold=5,
            survey_key="survey_key",
            survey_id="survey_id",
            enumerator="enumerator",
        )

        # Step 2: Compute column summary
        summary = compute_column_outlier_summary(outlier_data, "survey_key")

        # Step 3: Get outlier columns
        outlier_cols = get_outlier_cols(outlier_settings_data.iloc[:1])

        assert isinstance(outlier_data, pd.DataFrame)
        assert isinstance(summary, pd.DataFrame)
        assert isinstance(outlier_cols, list)
        assert len(outlier_cols) > 0

    def test_stack_and_compute_workflow(self, sample_data):
        """Test stacking columns and computing statistics."""
        # Stack columns
        stacked = stack_outlier_columns(sample_data, ["numeric_col1", "numeric_col2"])

        # Compute stats on stacked series
        stats = compute_outlier_stats(stacked, "Interquartile Range (IQR)", 1.5)

        assert isinstance(stacked, pd.Series)
        assert isinstance(stats, dict)
        assert len(stacked) == len(sample_data) * 2
        assert "lower_bound" in stats
        assert "upper_bound" in stats


class TestOutliersReport:
    """Test outliers_report function (integration test)."""

    @patch("datasure.checks.outliers.duckdb_get_table")
    @patch("datasure.checks.outliers.duckdb_save_table")
    @patch("datasure.checks.outliers.outliers_report_settings")
    @patch("datasure.checks.outliers.get_df_info")
    @patch("datasure.checks.outliers.display_outlier_metrics")
    @patch("datasure.checks.outliers.display_outlier_column_summary")
    @patch("datasure.checks.outliers.display_outlier_output")
    @patch("datasure.checks.outliers.inspect_outliers_columns")
    @patch("streamlit.warning")
    def test_outliers_report_no_settings(
        self,
        mock_warning,
        mock_inspect,
        mock_display_output,
        mock_display_summary,
        mock_display_metrics,
        mock_get_df_info,
        mock_settings,
        mock_save,
        mock_get,
    ):
        """Test outliers report when no settings are found."""
        # Mock empty settings
        mock_get.side_effect = [
            MagicMock(
                to_pandas=MagicMock(return_value=pd.DataFrame({"page_name": ["test"]}))
            ),
            MagicMock(
                to_pandas=MagicMock(return_value=pd.DataFrame())
            ),  # Empty outlier settings
        ]

        mock_settings.return_value = (
            ["col1"],
            30,
            "survey_id",
            "survey_key",
            "enumerator",
        )

        outliers_report(
            "test_project", pd.DataFrame({"col1": [1, 2, 3]}), "settings.json", 1
        )

        mock_warning.assert_called_once_with(
            "No outlier settings found. Please add outlier columns in the settings section."
        )

    @patch("datasure.checks.outliers.duckdb_get_table")
    @patch("datasure.checks.outliers.duckdb_save_table")
    @patch("datasure.checks.outliers.outliers_report_settings")
    @patch("datasure.checks.outliers.get_df_info")
    @patch("datasure.checks.outliers.update_unlocked_cols")
    @patch("datasure.checks.outliers.compute_outlier_output")
    @patch("datasure.checks.outliers.get_outlier_cols")
    @patch("datasure.checks.outliers.display_outlier_metrics")
    @patch("datasure.checks.outliers.compute_column_outlier_summary")
    @patch("datasure.checks.outliers.display_outlier_column_summary")
    @patch("datasure.checks.outliers.display_outlier_output")
    @patch("datasure.checks.outliers.inspect_outliers_columns")
    def test_outliers_report_with_settings(
        self,
        mock_inspect,
        mock_display_output,
        mock_display_summary,
        mock_compute_summary,
        mock_display_metrics,
        mock_get_cols,
        mock_compute_output,
        mock_update_cols,
        mock_get_df_info,
        mock_settings,
        mock_save,
        mock_get,
        sample_data,
        outlier_settings_data,
    ):
        """Test outliers report with valid settings."""
        # Mock database calls
        mock_get.side_effect = [
            MagicMock(
                to_pandas=MagicMock(return_value=pd.DataFrame({"page_name": ["test"]}))
            ),
            MagicMock(to_pandas=MagicMock(return_value=outlier_settings_data)),
        ]

        # Mock function returns
        mock_settings.return_value = (
            ["col1"],
            30,
            "survey_id",
            "survey_key",
            "enumerator",
        )
        mock_get_df_info.return_value = (
            [],
            [],
            ["numeric_col1", "numeric_col2"],
            [],
            [],
        )
        mock_update_cols.return_value = outlier_settings_data
        mock_compute_output.return_value = pd.DataFrame(
            {"column name": ["col1"], "outlier reason": ["outlier"]}
        )
        mock_get_cols.return_value = ["col1"]
        mock_compute_summary.return_value = pd.DataFrame(
            {"column name": ["col1"], "outlier count": [1]}
        )

        outliers_report("test_project", sample_data, "settings.json", 1)

        # Verify all major functions were called
        mock_settings.assert_called_once()
        mock_get_df_info.assert_called_once()
        mock_update_cols.assert_called_once()
        mock_compute_output.assert_called_once()
        mock_display_metrics.assert_called_once()
        mock_display_summary.assert_called_once()
        mock_display_output.assert_called_once()
        mock_inspect.assert_called_once()
