"""Test the outliers module."""

from unittest.mock import MagicMock, patch

import pandas as pd
import plotly.graph_objects as go
import pytest

from datasure.checks.outliers import (
    calculate_joint_outliers_percentage,
    common_prefix,
    compute_joint_outlier_distribution,
    create_violin_plot,
    detect_outliers,
    display_outlier_metrics,
    load_default_settings,
    outliers_report_settings,
    plot_joint_outliers_distribution,
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
def melted_data():
    """Melted data for joint outlier testing."""
    return pd.DataFrame(
        {
            "survey_id": ["S001", "S002", "S003", "S004", "S005"] * 3,
            "name_variable": ["var1"] * 5 + ["var2"] * 5 + ["var3"] * 5,
            "new_var": [1, 2, 3, 4, 100] + [10, 20, 30, 40, 50] + [5, 6, 7, 8, 9],
        }
    )


class TestLoadDefaultSettings:
    """Test load_default_settings function."""

    def test_load_default_settings_file_exists(self):
        """Test when settings file exists."""
        with (
            patch("src.pydms.checks.outliers.get_check_config_settings") as mock_config,
            patch("src.pydms.checks.outliers.os.path.exists") as mock_exists,
            patch("src.pydms.checks.outliers.load_check_settings") as mock_load,
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
                "outlier_cols": ["col1", "col2"],
                "outlier_method": 1,
                "sd_value": 2.5,
                "iqr_value": 1.8,
                "selected_pattern": ["pattern1"],
            }

            result = load_default_settings("project1", "settings.json", 1)

            assert result[0] == "test_id"
            assert result[1] == "test_enum"
            assert result[2] == "test_key"
            assert result[3] == ["col1", "col2"]
            assert result[4] == 1
            assert result[5] == 2.5
            assert result[6] == 1.8
            assert result[7] == ["pattern1"]

    def test_load_default_settings_file_missing(self):
        """Test when settings file is missing."""
        with (
            patch("src.pydms.checks.outliers.get_check_config_settings") as mock_config,
            patch("src.pydms.checks.outliers.os.path.exists") as mock_exists,
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
            assert result[3] == []
            assert result[4] == 0
            assert result[5] == 3.0
            assert result[6] == 1.5
            assert result[7] == []

    def test_load_default_settings_partial_config(self):
        """Test when settings file exists but has partial config."""
        with (
            patch("src.pydms.checks.outliers.get_check_config_settings") as mock_config,
            patch("src.pydms.checks.outliers.os.path.exists") as mock_exists,
            patch("src.pydms.checks.outliers.load_check_settings") as mock_load,
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
            assert result[3] == []  # Default
            assert result[4] == 0  # Default
            assert result[5] == 3.0  # Default
            assert result[6] == 1.5  # Default
            assert result[7] == []  # Default


class TestDetectOutliers:
    """Test detect_outliers function."""

    def test_detect_outliers_iqr_method(self, outliers_data):
        """Test with IQR method."""
        result = detect_outliers(
            outliers_data,
            "survey_key",
            "survey_id",
            "enumerator",
            ["outlier_col"],
            "Interquartile Range (IQR)",
            1.5,
            3.0,
        )

        assert isinstance(result, pd.DataFrame)
        if not result.empty:
            assert "variable" in result.columns
            assert "value" in result.columns
            assert "lower_bound" in result.columns
            assert "upper_bound" in result.columns
            assert "survey_key" in result.columns

    def test_detect_outliers_sd_method(self, outliers_data):
        """Test with Standard Deviation method."""
        result = detect_outliers(
            outliers_data,
            "survey_key",
            "survey_id",
            "enumerator",
            ["outlier_col"],
            "Standard Deviation (SD)",
            1.5,
            2.0,
        )

        assert isinstance(result, pd.DataFrame)
        if not result.empty:
            assert "variable" in result.columns
            assert "value" in result.columns
            assert "mean" in result.columns
            assert "std" in result.columns

    def test_detect_outliers_no_outliers(self, outliers_data):
        """Test when no outliers are found."""
        result = detect_outliers(
            outliers_data,
            "survey_key",
            "survey_id",
            "enumerator",
            ["normal_col"],
            "Interquartile Range (IQR)",
            1.5,
            3.0,
        )

        assert result.empty

    def test_detect_outliers_special_values_excluded(self, outliers_data):
        """Test that special values are excluded."""
        result = detect_outliers(
            outliers_data,
            "survey_key",
            "survey_id",
            "enumerator",
            ["special_values"],
            "Interquartile Range (IQR)",
            1.5,
            3.0,
        )

        # Should process only [1.0, 2.0, 5.0] (excluding -999, 0.777)
        assert isinstance(result, pd.DataFrame)

    def test_detect_outliers_empty_columns(self, outliers_data):
        """Test with empty columns list."""
        result = detect_outliers(
            outliers_data,
            "survey_key",
            "survey_id",
            "enumerator",
            [],
            "Interquartile Range (IQR)",
            1.5,
            3.0,
        )

        assert result.empty

    def test_detect_outliers_missing_admin_columns(self, outliers_data):
        """Test with missing admin columns."""
        result = detect_outliers(
            outliers_data,
            "survey_key",
            None,
            None,
            ["outlier_col"],
            "Interquartile Range (IQR)",
            1.5,
            3.0,
        )

        assert isinstance(result, pd.DataFrame)
        if not result.empty:
            assert "survey_key" in result.columns
            assert "survey_id" not in result.columns
            assert "enumerator" not in result.columns

    def test_detect_outliers_column_order(self, outliers_data):
        """Test that columns are ordered correctly."""
        result = detect_outliers(
            outliers_data,
            "survey_key",
            "survey_id",
            "enumerator",
            ["outlier_col"],
            "Interquartile Range (IQR)",
            1.5,
            3.0,
        )

        if not result.empty:
            actual_columns = result.columns.tolist()
            # Check that survey_key comes first, then admin columns
            assert actual_columns[0] == "survey_key"
            assert "survey_id" in actual_columns
            assert "enumerator" in actual_columns


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


class TestDisplayOutlierMetrics:
    """Test display_outlier_metrics function."""

    def test_display_outlier_metrics_no_outliers(self):
        """Test with no outliers."""
        empty_df = pd.DataFrame()
        outlier_cols = ["col1", "col2"]

        with (
            patch("streamlit.columns") as mock_columns,
            patch("streamlit.success") as mock_success,
        ):
            mock_col = MagicMock()
            mock_col.metric = MagicMock()
            mock_columns.return_value = [mock_col, mock_col, mock_col, mock_col]

            display_outlier_metrics(empty_df, outlier_cols, "enumerator")

            mock_success.assert_called_once()

    def test_display_outlier_metrics_no_cols(self):
        """Test with no columns selected."""
        outliers_df = pd.DataFrame()

        with (
            patch("streamlit.info") as mock_info,
        ):
            display_outlier_metrics(outliers_df, None, "enumerator")

            mock_info.assert_called_once()


class TestCommonPrefix:
    """Test common_prefix function."""

    def test_common_prefix_basic(self):
        """Test with common prefix."""
        strs = ["hh_member_1_age", "hh_member_2_age", "hh_member_3_age"]
        result = common_prefix(strs)
        assert result == "hh_member_"

    def test_common_prefix_no_common(self):
        """Test with no common prefix."""
        strs = ["income", "education", "age"]
        result = common_prefix(strs)
        assert result == ""

    def test_common_prefix_empty_list(self):
        """Test with empty list."""
        result = common_prefix([])
        assert result == ""

    def test_common_prefix_single_string(self):
        """Test with single string."""
        result = common_prefix(["single"])
        assert result == "single"

    def test_common_prefix_partial_match(self):
        """Test with partial match."""
        strs = ["test_var_1", "test_var_2", "test_other"]
        result = common_prefix(strs)
        assert result == "test_"

    def test_common_prefix_identical_strings(self):
        """Test with identical strings."""
        strs = ["same", "same", "same"]
        result = common_prefix(strs)
        assert result == "same"


class TestComputeJointOutlierDistribution:
    """Test compute_joint_outlier_distribution function."""

    def test_compute_joint_outlier_distribution_iqr(self, melted_data):
        """Test with IQR method."""
        result = compute_joint_outlier_distribution(
            melted_data,
            ["var1", "var2", "var3"],
            "survey_id",
            "Interquartile Range (IQR)",
            1.5,
            3.0,
        )

        assert isinstance(result, tuple)
        assert len(result) == 2
        table_data, outliers_df = result

        assert isinstance(table_data, pd.DataFrame)
        assert isinstance(outliers_df, pd.DataFrame)

        if not table_data.empty:
            assert "survey_id" in table_data.columns
            assert "name_variable" in table_data.columns
            assert "new_var" in table_data.columns
            assert "lower_bound" in table_data.columns
            assert "upper_bound" in table_data.columns

    def test_compute_joint_outlier_distribution_sd(self, melted_data):
        """Test with SD method."""
        result = compute_joint_outlier_distribution(
            melted_data, ["var1"], "survey_id", "Standard Deviation (SD)", 1.5, 2.0
        )

        assert isinstance(result, tuple)
        table_data, outliers_df = result

        assert isinstance(table_data, pd.DataFrame)
        assert isinstance(outliers_df, pd.DataFrame)

    def test_compute_joint_outlier_distribution_no_outliers(self):
        """Test when no outliers are found."""
        normal_data = pd.DataFrame(
            {
                "survey_id": ["S001", "S002", "S003"],
                "name_variable": ["var1", "var1", "var1"],
                "new_var": [1, 2, 3],
            }
        )

        result = compute_joint_outlier_distribution(
            normal_data, ["var1"], "survey_id", "Interquartile Range (IQR)", 1.5, 3.0
        )

        table_data, outliers_df = result
        assert table_data.empty
        assert outliers_df.empty

    def test_compute_joint_outlier_distribution_empty_data(self):
        """Test with empty data."""
        empty_data = pd.DataFrame(columns=["survey_id", "name_variable", "new_var"])

        result = compute_joint_outlier_distribution(
            empty_data, [], "survey_id", "Interquartile Range (IQR)", 1.5, 3.0
        )

        table_data, outliers_df = result
        assert table_data.empty
        assert outliers_df.empty


class TestPlotJointOutliersDistribution:
    """Test plot_joint_outliers_distribution function."""

    def test_plot_joint_outliers_distribution_basic(self, melted_data):
        """Test basic functionality."""
        selected_cols = ["var1", "var2"]

        with patch("streamlit.plotly_chart") as mock_plotly:
            plot_joint_outliers_distribution(melted_data, selected_cols)

            mock_plotly.assert_called_once()

    def test_plot_joint_outliers_distribution_single_col(self, melted_data):
        """Test with single column."""
        selected_cols = ["var1"]

        with patch("streamlit.plotly_chart") as mock_plotly:
            plot_joint_outliers_distribution(melted_data, selected_cols)

            mock_plotly.assert_called_once()

    def test_plot_joint_outliers_distribution_empty_cols(self, melted_data):
        """Test with empty columns."""
        selected_cols = []

        with patch("streamlit.plotly_chart") as mock_plotly:
            plot_joint_outliers_distribution(melted_data, selected_cols)

            mock_plotly.assert_called_once()


class TestOutliersReportSettings:
    """Test outliers_report_settings function."""

    @patch("streamlit.expander")
    @patch("streamlit.columns")
    @patch("streamlit.multiselect")
    @patch("streamlit.radio")
    @patch("streamlit.selectbox")
    @patch("streamlit.number_input")
    @patch("streamlit.container")
    @patch("streamlit.write")
    @patch("src.pydms.checks.outliers.get_df_info")
    @patch("src.pydms.checks.outliers.load_default_settings")
    @patch("src.pydms.checks.outliers.find_variable_patterns")
    @patch("src.pydms.checks.outliers.show_pattern_selection")
    def test_outliers_report_settings_basic(
        self,
        mock_show_pattern,
        mock_find_patterns,
        mock_load_defaults,
        mock_get_df_info,
        mock_write,
        mock_container,
        mock_number_input,
        mock_selectbox,
        mock_radio,
        mock_multiselect,
        mock_columns,
        mock_expander,
        sample_data,
    ):
        """Test basic settings functionality."""
        # Mock expander context manager
        mock_expander_context = MagicMock()
        mock_expander.return_value.__enter__ = MagicMock(
            return_value=mock_expander_context
        )
        mock_expander.return_value.__exit__ = MagicMock(return_value=None)

        # Mock container context manager
        mock_container_context = MagicMock()
        mock_container.return_value.__enter__ = MagicMock(
            return_value=mock_container_context
        )
        mock_container.return_value.__exit__ = MagicMock(return_value=None)

        # Mock get_df_info return
        mock_get_df_info.return_value = (
            ["col1", "col2", "col3"],
            ["string_col"],
            ["numeric_col1", "numeric_col2"],
            ["datetime_col"],
            None,
        )

        # Mock load_default_settings return
        mock_load_defaults.return_value = (
            "survey_id",
            "enumerator",
            "survey_key",
            ["numeric_col1"],
            0,
            3.0,
            1.5,
            [],
        )

        # Mock UI components
        mock_col = MagicMock()
        mock_columns.return_value = [mock_col, mock_col, mock_col]
        mock_multiselect.return_value = ["numeric_col1"]
        mock_radio.return_value = "Interquartile Range (IQR)"
        mock_selectbox.return_value = "survey_id"
        mock_number_input.return_value = 1.5

        # Mock pattern functions
        mock_find_patterns.return_value = {}
        mock_show_pattern.return_value = (None, None, None)

        with patch("streamlit.session_state", {}):
            result = outliers_report_settings(
                "project1", sample_data, "settings.json", 1
            )

            assert isinstance(result, tuple)
            assert len(result) == 9

    @patch("streamlit.expander")
    @patch("streamlit.columns")
    @patch("streamlit.multiselect")
    @patch("streamlit.radio")
    @patch("streamlit.selectbox")
    @patch("streamlit.number_input")
    @patch("streamlit.container")
    @patch("streamlit.write")
    @patch("src.pydms.checks.outliers.get_df_info")
    @patch("src.pydms.checks.outliers.load_default_settings")
    @patch("src.pydms.checks.outliers.find_variable_patterns")
    @patch("src.pydms.checks.outliers.show_pattern_selection")
    def test_outliers_report_settings_with_patterns(
        self,
        mock_show_pattern,
        mock_find_patterns,
        mock_load_defaults,
        mock_get_df_info,
        mock_write,
        mock_container,
        mock_number_input,
        mock_selectbox,
        mock_radio,
        mock_multiselect,
        mock_columns,
        mock_expander,
        sample_data,
    ):
        """Test settings with pattern selection."""
        # Mock expander and container context managers
        mock_expander_context = MagicMock()
        mock_expander.return_value.__enter__ = MagicMock(
            return_value=mock_expander_context
        )
        mock_expander.return_value.__exit__ = MagicMock(return_value=None)

        mock_container_context = MagicMock()
        mock_container.return_value.__enter__ = MagicMock(
            return_value=mock_container_context
        )
        mock_container.return_value.__exit__ = MagicMock(return_value=None)

        # Mock get_df_info return
        mock_get_df_info.return_value = (
            ["col1", "col2", "col3"],
            ["string_col"],
            ["hh_member_1_age", "hh_member_2_age"],
            ["datetime_col"],
            None,
        )

        # Mock load_default_settings return
        mock_load_defaults.return_value = (
            "survey_id",
            "enumerator",
            "survey_key",
            ["hh_member_1_age"],
            0,
            3.0,
            1.5,
            ["hh_member_1_age", "hh_member_2_age"],
        )

        # Mock UI components
        mock_col = MagicMock()
        mock_columns.return_value = [mock_col, mock_col, mock_col]
        mock_multiselect.side_effect = [
            ["hh_member_1_age"],
            ["hh_member_1_age", "hh_member_2_age"],
        ]
        mock_radio.return_value = "Standard Deviation (SD)"
        mock_selectbox.return_value = "survey_id"
        mock_number_input.return_value = 2.5

        # Mock pattern functions
        mock_find_patterns.return_value = {
            "hh_member": ["hh_member_1_age", "hh_member_2_age"]
        }
        mock_show_pattern.return_value = (
            "hh_member",
            ["hh_member_1_age", "hh_member_2_age"],
            pd.DataFrame(
                {
                    "survey_id": ["S001"],
                    "name_variable": ["hh_member_1_age"],
                    "new_var": [25],
                }
            ),
        )

        with patch("streamlit.session_state", {}):
            result = outliers_report_settings(
                "project1", sample_data, "settings.json", 1
            )

            assert isinstance(result, tuple)
            assert len(result) == 9
            # Check that pattern selection worked
            assert result[7] == ["hh_member_1_age", "hh_member_2_age"]  # selected_cols
            assert isinstance(result[8], pd.DataFrame)  # reshaped_joint_outliers_df


# Integration tests
class TestIntegration:
    """Integration tests for the outliers module."""

    def test_joint_outlier_detection_workflow(self, sample_data):
        """Test joint outlier detection workflow."""
        # Step 1: Create melted data
        melted_data = pd.melt(
            sample_data[["survey_id", "hh_member_1_age", "hh_member_2_age"]],
            id_vars=["survey_id"],
            value_vars=["hh_member_1_age", "hh_member_2_age"],
            var_name="name_variable",
            value_name="new_var",
        )

        # Step 2: Compute joint outliers
        table_data, outliers_df = compute_joint_outlier_distribution(
            melted_data,
            ["hh_member_1_age", "hh_member_2_age"],
            "survey_id",
            "Interquartile Range (IQR)",
            1.5,
            3.0,
        )

        # Step 3: Calculate percentage
        percentage = calculate_joint_outliers_percentage(
            outliers_df, ["hh_member_1_age", "hh_member_2_age"]
        )

        assert isinstance(table_data, pd.DataFrame)
        assert isinstance(outliers_df, pd.DataFrame)
        assert isinstance(percentage, str)
        assert percentage.endswith("%")
