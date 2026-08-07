from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import polars as pl

from datasure.checks.gpschecks.report_ui import (
    _add_gps_column,
    _apply_category_filter,
    _calculate_comparison_distances,
    _delete_gps_column,
    _display_comparison_summary,
    _load_and_parse_gps_data,
    _load_comparison_aliases,
    _merge_parsed_gps_data,
    _render_comparison_details_table,
    _render_comparison_map,
    _render_comparison_selectors,
    _render_gps_column_actions,
    _render_gps_comparison_checks,
    _render_gps_coordinates,
    _render_gps_outliers_checks,
    _render_gps_settings_table,
    _render_outliers_data_table,
    _render_scatterplot_map,
    _run_cluster_detection,
    _run_lof_detection,
    _update_gps_column_config,
    gpschecks_report,
    plot_clusters_on_map,
    plot_gps_coordinates,
)
from datasure.models.enums import DelimiterType, GPSFormatType, GPSOutlierMethod
from datasure.models.schemas import GPSColumnConfig, GPSSettings
from datasure.utils.dataframe_utils import ColumnByType

# =============================================================================
# Tests for GPS Column Configuration Update
# =============================================================================


@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
@patch("datasure.checks.gpschecks.compute.duckdb_save_table")
def test_update_gps_column_config_new_config(mock_save, mock_get):
    """Test updating GPS column config with new configuration."""
    # Mock empty existing config
    mock_get.return_value = pl.DataFrame()

    config = GPSColumnConfig(
        alias="test_gps",
        format_type=GPSFormatType.SINGLE_COLUMN,
        delimiter=DelimiterType.SPACE,
        gps_column="gps_coords",
    )

    _update_gps_column_config("test_project", "test_page", config)

    # Verify save was called
    mock_save.assert_called_once()
    saved_df = mock_save.call_args[0][1]

    # Verify saved data
    assert len(saved_df) == 1
    assert saved_df["alias"][0] == "test_gps"
    assert saved_df["format_type"][0] == GPSFormatType.SINGLE_COLUMN.value
    assert saved_df["delimiter"][0] == DelimiterType.SPACE.value
    assert saved_df["gps_column"][0] == "gps_coords"


@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
@patch("datasure.checks.gpschecks.compute.duckdb_save_table")
def test_update_gps_column_config_append_to_existing(mock_save, mock_get):
    """Test appending new GPS config to existing configurations."""
    # Mock existing config with proper schema (all strings, not nulls)
    schema = {
        "alias": pl.Utf8,
        "format_type": pl.Utf8,
        "delimiter": pl.Utf8,
        "gps_column": pl.Utf8,
        "latitude_column": pl.Utf8,
        "longitude_column": pl.Utf8,
        "altitude_column": pl.Utf8,
        "accuracy_column": pl.Utf8,
    }
    existing_config = pl.DataFrame(
        {
            "alias": ["existing_gps"],
            "format_type": [GPSFormatType.SINGLE_COLUMN.value],
            "delimiter": [DelimiterType.COMMA.value],
            "gps_column": ["old_gps"],
            "latitude_column": [None],
            "longitude_column": [None],
            "altitude_column": [None],
            "accuracy_column": [None],
        },
        schema=schema,
    )
    mock_get.return_value = existing_config

    new_config = GPSColumnConfig(
        alias="new_gps",
        format_type=GPSFormatType.SEPARATE_COLUMNS,
        latitude_column="lat",
        longitude_column="lon",
    )

    _update_gps_column_config("test_project", "test_page", new_config)

    # Verify save was called
    mock_save.assert_called_once()
    saved_df = mock_save.call_args[0][1]

    # Should have 2 configurations now
    assert len(saved_df) == 2
    assert "existing_gps" in saved_df["alias"].to_list()
    assert "new_gps" in saved_df["alias"].to_list()


@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
@patch("datasure.checks.gpschecks.compute.duckdb_save_table")
def test_update_gps_column_config_separate_columns(mock_save, mock_get):
    """Test updating GPS config with separate columns format."""
    mock_get.return_value = pl.DataFrame()

    config = GPSColumnConfig(
        alias="sep_gps",
        format_type=GPSFormatType.SEPARATE_COLUMNS,
        latitude_column="latitude",
        longitude_column="longitude",
        altitude_column="altitude",
        accuracy_column="accuracy",
    )

    _update_gps_column_config("test_project", "test_page", config)

    saved_df = mock_save.call_args[0][1]

    assert saved_df["alias"][0] == "sep_gps"
    assert saved_df["format_type"][0] == GPSFormatType.SEPARATE_COLUMNS.value
    assert saved_df["latitude_column"][0] == "latitude"
    assert saved_df["longitude_column"][0] == "longitude"
    assert saved_df["altitude_column"][0] == "altitude"
    assert saved_df["accuracy_column"][0] == "accuracy"
    assert saved_df["delimiter"][0] is None  # No delimiter for separate columns


# =============================================================================
# Tests for plot_gps_coordinates / plot_clusters_on_map
# =============================================================================


@patch("datasure.checks.gpschecks.compute.pydeck.settings")
@patch("datasure.checks.gpschecks.report_ui.st.pydeck_chart")
def test_plot_gps_coordinates(mock_pydeck_chart, mock_pydeck_settings, sample_gps_data):
    """Test GPS coordinates plotting function."""
    # Mock the mapbox_key attribute
    mock_pydeck_settings.mapbox_key = "test_mapbox_key"

    plot_gps_coordinates(
        sample_gps_data,
        "enumerator",
        "submissiondate",
        "survey_id",
        "latitude",
        "longitude",
        "enumerator",
    )

    # Verify that pydeck chart was called
    mock_pydeck_chart.assert_called_once()

    # Get the call arguments
    call_args = mock_pydeck_chart.call_args
    deck_obj = call_args[0][0]

    # Verify deck object properties
    assert hasattr(deck_obj, "layers")
    assert len(deck_obj.layers) == 1

    # Verify layer properties
    layer = deck_obj.layers[0]
    assert layer.type == "ScatterplotLayer"


@patch("datasure.checks.gpschecks.compute.pydeck.settings")
@patch("datasure.checks.gpschecks.report_ui.st.pydeck_chart")
def test_plot_gps_coordinates_with_missing_data(
    mock_pydeck_chart, mock_pydeck_settings
):
    """Test GPS coordinates plotting with missing coordinates."""
    # Mock the mapbox_key attribute
    mock_pydeck_settings.mapbox_key = "test_mapbox_key"

    data_with_missing = pd.DataFrame(
        {
            "enumerator": ["E001", "E002", "E003"],
            "submissiondate": pd.date_range("2025-01-01", periods=3),
            "survey_id": ["ID001", "ID002", "ID003"],
            "latitude": [6.6018, np.nan, 6.6022],
            "longitude": [-0.1870, -0.1865, np.nan],
        }
    )

    plot_gps_coordinates(
        data_with_missing,
        "enumerator",
        "submissiondate",
        "survey_id",
        "latitude",
        "longitude",
        "enumerator",
    )

    # Should still call pydeck chart (missing rows are dropped)
    mock_pydeck_chart.assert_called_once()


@patch("datasure.checks.gpschecks.compute.pydeck.settings")
@patch("datasure.checks.gpschecks.report_ui.st.pydeck_chart")
def test_plot_clusters_on_map(
    mock_pydeck_chart, mock_pydeck_settings, sample_gps_data_with_outliers
):
    """Test plotting clusters on map with outlier highlighting."""
    # Mock the mapbox_key attribute
    mock_pydeck_settings.mapbox_key = "test_mapbox_key"

    # Add outlier column
    sample_gps_data_with_outliers["Outlier"] = False
    sample_gps_data_with_outliers.loc[10:, "Outlier"] = True  # Mark last 2 as outliers

    plot_clusters_on_map(
        sample_gps_data_with_outliers,
        "latitude",
        "longitude",
        "enumerator",
        "submissiondate",
        "survey_id",
        "enumerator",
        "Outlier",
    )

    # Verify that pydeck chart was called
    mock_pydeck_chart.assert_called_once()

    # Get the call arguments
    call_args = mock_pydeck_chart.call_args
    deck_obj = call_args[0][0]

    # Verify deck object properties
    assert hasattr(deck_obj, "layers")
    assert len(deck_obj.layers) == 1


@patch("datasure.checks.gpschecks.compute.pydeck.settings")
@patch("datasure.checks.gpschecks.report_ui.st.pydeck_chart")
def test_plot_clusters_on_map_all_normal_points(
    mock_pydeck_chart, mock_pydeck_settings, sample_gps_data
):
    """Test plotting clusters when all points are normal (no outliers)."""
    # Mock the mapbox_key attribute
    mock_pydeck_settings.mapbox_key = "test_mapbox_key"

    sample_gps_data["Outlier"] = False  # All points are normal

    plot_clusters_on_map(
        sample_gps_data,
        "latitude",
        "longitude",
        "enumerator",
        "submissiondate",
        "survey_id",
        "enumerator",
        "Outlier",
    )

    mock_pydeck_chart.assert_called_once()


@patch("datasure.checks.gpschecks.compute.pydeck.settings")
@patch("datasure.checks.gpschecks.report_ui.st.pydeck_chart")
def test_plot_gps_coordinates_many_unique_values(
    mock_pydeck_chart, mock_pydeck_settings
):
    """Test GPS plotting with many unique values for color coding."""
    # Mock the mapbox_key attribute
    mock_pydeck_settings.mapbox_key = "test_mapbox_key"

    # Create data with more than 10 unique enumerators
    many_enum_data = pd.DataFrame(
        {
            "enumerator": [f"E{i:03d}" for i in range(15)],
            "submissiondate": pd.date_range("2025-01-01", periods=15),
            "survey_id": [f"ID{i:03d}" for i in range(15)],
            "latitude": [6.6018 + i * 0.001 for i in range(15)],
            "longitude": [-0.1870 + i * 0.001 for i in range(15)],
        }
    )

    plot_gps_coordinates(
        many_enum_data,
        "enumerator",
        "submissiondate",
        "survey_id",
        "latitude",
        "longitude",
        "enumerator",
    )

    # Should handle > 10 colors by using matplotlib colormap
    mock_pydeck_chart.assert_called_once()


# =============================================================================
# Tests for _apply_category_filter
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.multiselect")
def test_apply_category_filter_with_filter(mock_multiselect):
    """Test category filter with selected values."""
    data = pl.DataFrame({"group": ["A", "B", "C", "A"], "val": [1, 2, 3, 4]})
    mock_multiselect.return_value = ["A"]
    result = _apply_category_filter(data, "group")
    assert len(result) == 2
    assert result["group"].to_list() == ["A", "A"]


@patch("datasure.checks.gpschecks.report_ui.st.multiselect")
def test_apply_category_filter_empty_selection(mock_multiselect):
    """Test category filter with empty selection returns original."""
    data = pl.DataFrame({"group": ["A", "B"], "val": [1, 2]})
    mock_multiselect.return_value = []
    result = _apply_category_filter(data, "group")
    assert len(result) == 2


def test_apply_category_filter_no_filter():
    """Test category filter with None returns original data."""
    data = pl.DataFrame({"group": ["A", "B"], "val": [1, 2]})
    result = _apply_category_filter(data, None)
    assert len(result) == 2


# =============================================================================
# Tests for _merge_parsed_gps_data
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.error")
def test_merge_parsed_gps_data_no_survey_key(mock_error):
    """Test merge fails when survey_key is None."""
    df1 = pl.DataFrame({"latitude": [1.0], "longitude": [2.0]})
    df2 = pl.DataFrame({"latitude": [1.1], "longitude": [2.1]})
    result = _merge_parsed_gps_data(df1, df2, None)
    assert result is None
    mock_error.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui.st.error")
def test_merge_parsed_gps_data_missing_key_column(mock_error):
    """Test merge fails when survey_key not in columns."""
    df1 = pl.DataFrame({"latitude": [1.0], "longitude": [2.0]})
    df2 = pl.DataFrame({"latitude": [1.1], "longitude": [2.1]})
    result = _merge_parsed_gps_data(df1, df2, "missing_key")
    assert result is None


def test_merge_parsed_gps_data_success():
    """Test successful merge of two GPS datasets."""
    df1 = pl.DataFrame(
        {
            "key": ["A", "B"],
            "latitude": [1.0, 2.0],
            "longitude": [3.0, 4.0],
        }
    )
    df2 = pl.DataFrame(
        {
            "key": ["A", "B"],
            "latitude": [1.1, 2.1],
            "longitude": [3.1, 4.1],
        }
    )
    result = _merge_parsed_gps_data(df1, df2, "key")
    assert result is not None
    assert "lat_1" in result.columns
    assert "lon_1" in result.columns
    assert "lat_2" in result.columns
    assert "lon_2" in result.columns
    assert len(result) == 2


@patch("datasure.checks.gpschecks.report_ui.st.warning")
def test_merge_parsed_gps_data_no_matches(mock_warning):
    """Test merge with no matching keys."""
    df1 = pl.DataFrame({"key": ["A"], "latitude": [1.0], "longitude": [3.0]})
    df2 = pl.DataFrame({"key": ["B"], "latitude": [1.1], "longitude": [3.1]})
    result = _merge_parsed_gps_data(df1, df2, "key")
    assert result is None
    mock_warning.assert_called_once()


# =============================================================================
# Tests for _calculate_comparison_distances
# =============================================================================


def test_calculate_comparison_distances_success():
    """Test successful distance calculation."""
    data = pl.DataFrame(
        {
            "lat_1": [6.6018, 6.6020],
            "lon_1": [-0.1870, -0.1865],
            "lat_2": [6.6019, 6.6021],
            "lon_2": [-0.1871, -0.1866],
        }
    )
    result = _calculate_comparison_distances(data)
    assert result is not None
    assert "distance_meters" in result.columns
    assert len(result) == 2
    assert (result["distance_meters"] > 0).all()


@patch("datasure.checks.gpschecks.report_ui.st.warning")
def test_calculate_comparison_distances_empty(mock_warning):
    """Test distance calc with no valid coordinates."""
    data = pl.DataFrame(
        {
            "lat_1": [None],
            "lon_1": [None],
            "lat_2": [None],
            "lon_2": [None],
        },
        schema={
            "lat_1": pl.Float64,
            "lon_1": pl.Float64,
            "lat_2": pl.Float64,
            "lon_2": pl.Float64,
        },
    )
    result = _calculate_comparison_distances(data)
    assert result is None


# =============================================================================
# Tests for _display_comparison_summary
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.success")
@patch("datasure.checks.gpschecks.report_ui.st.metric")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
def test_display_comparison_summary_no_flagged(mock_cols, mock_metric, mock_success):
    """Test comparison summary with no flagged points."""
    mock_cols.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
    df = pd.DataFrame(
        {
            "distance_meters": [10.0, 20.0, 30.0],
            "exceeds_threshold": [False, False, False],
        }
    )
    _display_comparison_summary(df, 100)
    mock_success.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui.st.warning")
@patch("datasure.checks.gpschecks.report_ui.st.metric")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
def test_display_comparison_summary_with_flagged(mock_cols, mock_metric, mock_warning):
    """Test comparison summary with flagged points."""
    mock_cols.return_value = [MagicMock(), MagicMock(), MagicMock(), MagicMock()]
    df = pd.DataFrame(
        {
            "distance_meters": [10.0, 200.0, 300.0],
            "exceeds_threshold": [False, True, True],
        }
    )
    _display_comparison_summary(df, 100)
    mock_warning.assert_called_once()


# =============================================================================
# Tests for _load_and_parse_gps_data
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
@patch("datasure.checks.gpschecks.report_ui.st.info")
def test_load_and_parse_gps_data_no_settings(mock_info, mock_get_table, mock_selectbox):
    """Test loading GPS data when no settings exist."""
    mock_get_table.return_value = pl.DataFrame()
    data = pl.DataFrame({"gps": ["1.0 2.0"]})
    result = _load_and_parse_gps_data("proj", "page", data)
    assert result == (None, None, None)
    mock_info.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
def test_load_and_parse_gps_data_no_alias_selected(mock_get_table, mock_selectbox):
    """Test loading GPS data when no alias is selected."""
    schema = {
        "alias": pl.Utf8,
        "format_type": pl.Utf8,
        "delimiter": pl.Utf8,
        "gps_column": pl.Utf8,
        "latitude_column": pl.Utf8,
        "longitude_column": pl.Utf8,
        "altitude_column": pl.Utf8,
        "accuracy_column": pl.Utf8,
    }
    settings = pl.DataFrame(
        {
            "alias": ["gps1"],
            "format_type": ["Separate Columns"],
            "delimiter": [None],
            "gps_column": [None],
            "latitude_column": ["lat"],
            "longitude_column": ["lon"],
            "altitude_column": [None],
            "accuracy_column": [None],
        },
        schema=schema,
    )
    mock_get_table.return_value = settings
    mock_selectbox.return_value = None

    data = pl.DataFrame({"lat": [1.0], "lon": [2.0]})
    gps_settings, alias, parsed = _load_and_parse_gps_data("proj", "page", data)
    assert gps_settings is not None
    assert alias is None
    assert parsed is None


@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
def test_load_and_parse_gps_data_success(mock_get_table, mock_selectbox):
    """Test successful GPS data loading and parsing."""
    schema = {
        "alias": pl.Utf8,
        "format_type": pl.Utf8,
        "delimiter": pl.Utf8,
        "gps_column": pl.Utf8,
        "latitude_column": pl.Utf8,
        "longitude_column": pl.Utf8,
        "altitude_column": pl.Utf8,
        "accuracy_column": pl.Utf8,
    }
    settings = pl.DataFrame(
        {
            "alias": ["gps1"],
            "format_type": ["Separate Columns"],
            "delimiter": [None],
            "gps_column": [None],
            "latitude_column": ["lat"],
            "longitude_column": ["lon"],
            "altitude_column": [None],
            "accuracy_column": [None],
        },
        schema=schema,
    )
    mock_get_table.return_value = settings
    mock_selectbox.return_value = "gps1"

    data = pl.DataFrame({"lat": [1.0, 2.0], "lon": [3.0, 4.0]})
    _gps_settings, alias, parsed = _load_and_parse_gps_data("proj", "page", data)
    assert alias == "gps1"
    assert parsed is not None
    assert len(parsed) == 2


@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
@patch("datasure.checks.gpschecks.report_ui.st.warning")
def test_load_and_parse_gps_data_all_null_coords(
    mock_warning, mock_get_table, mock_selectbox
):
    """Test GPS data loading when all coords are null."""
    schema = {
        "alias": pl.Utf8,
        "format_type": pl.Utf8,
        "delimiter": pl.Utf8,
        "gps_column": pl.Utf8,
        "latitude_column": pl.Utf8,
        "longitude_column": pl.Utf8,
        "altitude_column": pl.Utf8,
        "accuracy_column": pl.Utf8,
    }
    settings = pl.DataFrame(
        {
            "alias": ["gps1"],
            "format_type": ["Separate Columns"],
            "delimiter": [None],
            "gps_column": [None],
            "latitude_column": ["lat"],
            "longitude_column": ["lon"],
            "altitude_column": [None],
            "accuracy_column": [None],
        },
        schema=schema,
    )
    mock_get_table.return_value = settings
    mock_selectbox.return_value = "gps1"

    data = pl.DataFrame(
        {"lat": [None, None], "lon": [None, None]},
        schema={"lat": pl.Float64, "lon": pl.Float64},
    )
    _, _, parsed = _load_and_parse_gps_data("proj", "page", data)
    assert parsed is None


@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
@patch("datasure.checks.gpschecks.report_ui.st.error")
def test_load_and_parse_gps_data_parse_error(
    mock_error, mock_get_table, mock_selectbox
):
    """Test GPS data loading when parsing raises an exception."""
    schema = {
        "alias": pl.Utf8,
        "format_type": pl.Utf8,
        "delimiter": pl.Utf8,
        "gps_column": pl.Utf8,
        "latitude_column": pl.Utf8,
        "longitude_column": pl.Utf8,
        "altitude_column": pl.Utf8,
        "accuracy_column": pl.Utf8,
    }
    settings = pl.DataFrame(
        {
            "alias": ["gps1"],
            "format_type": ["INVALID_FORMAT"],
            "delimiter": [None],
            "gps_column": [None],
            "latitude_column": [None],
            "longitude_column": [None],
            "altitude_column": [None],
            "accuracy_column": [None],
        },
        schema=schema,
    )
    mock_get_table.return_value = settings
    mock_selectbox.return_value = "gps1"

    data = pl.DataFrame({"a": [1]})
    _, _, parsed = _load_and_parse_gps_data("proj", "page", data)
    assert parsed is None


# =============================================================================
# Tests for _run_lof_detection and _run_cluster_detection
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.warning")
def test_run_lof_detection_too_few_points(mock_warning):
    """Test LOF detection with too few points."""
    df_pd = pd.DataFrame({"latitude": [1.0, 2.0], "longitude": [3.0, 4.0]})
    result = _run_lof_detection(df_pd, 2, MagicMock())
    assert result is None
    mock_warning.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui.detect_outliers_with_lof")
@patch("datasure.checks.gpschecks.report_ui.st.slider")
@patch("datasure.checks.gpschecks.report_ui.st.warning")
def test_run_lof_detection_small_dataset(mock_warning, mock_slider, mock_detect):
    """Test LOF detection with small but valid dataset."""
    mock_slider.side_effect = [10, 0.1]
    mock_detect.return_value = pd.DataFrame(
        {
            "latitude": [1.0] * 10,
            "longitude": [2.0] * 10,
            "Outlier": [False] * 10,
        }
    )
    col_mock = MagicMock()
    result = _run_lof_detection(
        pd.DataFrame({"latitude": [1.0] * 10, "longitude": [2.0] * 10}),
        10,
        col_mock,
    )
    assert result is not None
    mock_warning.assert_called_once()  # <20 points warning


@patch("datasure.checks.gpschecks.report_ui.detect_outliers_with_clusters")
@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.report_ui.st.info")
def test_run_cluster_detection_no_col(mock_info, mock_selectbox, mock_detect):
    """Test cluster detection with no column selected."""
    mock_selectbox.return_value = None
    col_mock = MagicMock()
    result, col = _run_cluster_detection(pd.DataFrame(), ["col1"], col_mock)
    assert result is None
    assert col is None
    mock_info.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui.detect_outliers_with_clusters")
@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
def test_run_cluster_detection_success(mock_selectbox, mock_detect):
    """Test successful cluster detection."""
    mock_selectbox.return_value = "group"
    expected = pd.DataFrame(
        {"Outlier": [False, True], "distance_from_centroid": [0, 100]}
    )
    mock_detect.return_value = expected
    col_mock = MagicMock()

    result, col = _run_cluster_detection(pd.DataFrame(), ["group", "other"], col_mock)
    assert result is not None
    assert col == "group"


# =============================================================================
# Tests for _render_outliers_data_table
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.download_button")
@patch("datasure.checks.gpschecks.report_ui.st.dataframe")
@patch("datasure.checks.gpschecks.report_ui.st.expander")
def test_render_outliers_data_table_with_outliers(mock_expander, mock_df, mock_dl):
    """Test rendering outliers data table."""
    mock_expander.return_value.__enter__ = lambda s: s
    mock_expander.return_value.__exit__ = MagicMock(return_value=False)
    outlier_df = pd.DataFrame(
        {
            "survey_key": ["A", "B", "C"],
            "latitude": [1.0, 2.0, 3.0],
            "longitude": [4.0, 5.0, 6.0],
            "Outlier": [True, False, True],
        }
    )
    _render_outliers_data_table(
        outlier_df, "gps1", "survey_key", None, None, "Auto", None
    )
    mock_df.assert_called_once()
    mock_dl.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui.st.success")
@patch("datasure.checks.gpschecks.report_ui.st.expander")
def test_render_outliers_data_table_no_outliers(mock_expander, mock_success):
    """Test rendering when no outliers detected."""
    mock_expander.return_value.__enter__ = lambda s: s
    mock_expander.return_value.__exit__ = MagicMock(return_value=False)
    outlier_df = pd.DataFrame(
        {
            "latitude": [1.0, 2.0],
            "longitude": [3.0, 4.0],
            "Outlier": [False, False],
        }
    )
    _render_outliers_data_table(outlier_df, "gps1", None, None, None, "Auto", None)
    mock_success.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui.st.download_button")
@patch("datasure.checks.gpschecks.report_ui.st.dataframe")
@patch("datasure.checks.gpschecks.report_ui.st.expander")
def test_render_outliers_data_table_cluster_method(mock_expander, mock_df, mock_dl):
    """Test rendering outliers with cluster method."""
    mock_expander.return_value.__enter__ = lambda s: s
    mock_expander.return_value.__exit__ = MagicMock(return_value=False)
    outlier_df = pd.DataFrame(
        {
            "survey_key": ["A"],
            "latitude": [1.0],
            "longitude": [4.0],
            "group": ["G1"],
            "distance_from_centroid": [50.0],
            "Outlier": [True],
        }
    )
    _render_outliers_data_table(
        outlier_df,
        "gps1",
        "survey_key",
        None,
        None,
        "Cluster by Column",
        "group",
    )
    mock_df.assert_called_once()


# =============================================================================
# Tests for _render_gps_settings_table
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.dataframe")
@patch("datasure.checks.gpschecks.report_ui.st.expander")
def test_render_gps_settings_table(mock_expander, mock_df):
    """Test rendering GPS settings table."""
    mock_expander.return_value.__enter__ = lambda s: s
    mock_expander.return_value.__exit__ = MagicMock(return_value=False)
    gps_settings = pl.DataFrame(
        {
            "alias": ["gps1"],
            "format_type": ["Separate Columns"],
        }
    )
    _render_gps_settings_table(gps_settings)
    mock_df.assert_called_once()


# =============================================================================
# Tests for _render_comparison_map and _render_comparison_details_table
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui._render_scatterplot_map")
@patch("datasure.checks.gpschecks.report_ui.st.subheader")
def test_render_comparison_map(mock_subheader, mock_render):
    """Test rendering comparison map."""
    df = pd.DataFrame(
        {
            "lat_1": [1.0],
            "lon_1": [2.0],
            "survey_key": ["A"],
            "distance_meters": [50.0],
            "exceeds_threshold": [False],
        }
    )
    _render_comparison_map(df, "survey_key", None, None)
    mock_render.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui.st.download_button")
@patch("datasure.checks.gpschecks.report_ui.st.dataframe")
@patch("datasure.checks.gpschecks.report_ui.st.expander")
def test_render_comparison_details_table(mock_expander, mock_df, mock_dl):
    """Test rendering comparison details table."""
    mock_expander.return_value.__enter__ = lambda s: s
    mock_expander.return_value.__exit__ = MagicMock(return_value=False)
    df = pd.DataFrame(
        {
            "survey_key": ["A"],
            "lat_1": [1.0],
            "lon_1": [2.0],
            "lat_2": [1.1],
            "lon_2": [2.1],
            "distance_meters": [50.0],
            "exceeds_threshold": [False],
        }
    )
    _render_comparison_details_table(df, "config1", "config2", "survey_key", None, None)
    mock_df.assert_called_once()
    mock_dl.assert_called_once()


# =============================================================================
# Tests for _render_gps_coordinates
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui._render_scatterplot_map")
@patch("datasure.checks.gpschecks.report_ui._build_map_dataframe")
@patch("datasure.checks.gpschecks.report_ui._apply_category_filter")
@patch("datasure.checks.gpschecks.report_ui.get_df_columns")
@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.report_ui._load_and_parse_gps_data")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
@patch("datasure.checks.gpschecks.report_ui.st.subheader")
@patch("datasure.checks.gpschecks.report_ui.st.caption")
def test_render_gps_coordinates_success(
    mock_caption,
    mock_subheader,
    mock_cols,
    mock_load,
    mock_selectbox,
    mock_get_cols,
    mock_filter,
    mock_build_map,
    mock_render_map,
):
    """Test rendering GPS coordinates visualization."""
    col_mock = MagicMock()
    mock_cols.return_value = [col_mock, col_mock, col_mock]

    parsed = pl.DataFrame({"latitude": [1.0], "longitude": [2.0], "key": ["A"]})
    mock_load.return_value = (pl.DataFrame(), "gps1", parsed)

    mock_get_cols.return_value = ColumnByType(categorical_columns=["key"])
    mock_selectbox.return_value = None
    mock_filter.return_value = parsed

    map_pd = pd.DataFrame({"lat": [1.0], "lon": [2.0]})
    mock_build_map.return_value = (map_pd, ["lat", "lon"])

    _render_gps_coordinates.__wrapped__("proj", "page", parsed, "key", None, None, None)
    mock_render_map.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui._load_and_parse_gps_data")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
@patch("datasure.checks.gpschecks.report_ui.st.subheader")
def test_render_gps_coordinates_no_data(mock_subheader, mock_cols, mock_load):
    """Test rendering GPS coordinates when no data is available."""
    col_mock = MagicMock()
    mock_cols.return_value = [col_mock, col_mock, col_mock]
    mock_load.return_value = (None, None, None)

    _render_gps_coordinates.__wrapped__(
        "proj", "page", pl.DataFrame(), "key", None, None, None
    )


# =============================================================================
# Tests for _render_gps_outliers_checks
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui._load_and_parse_gps_data")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
@patch("datasure.checks.gpschecks.report_ui.st.subheader")
def test_render_gps_outliers_no_data(mock_subheader, mock_cols, mock_load):
    """Test outlier rendering when no data."""
    col_mock = MagicMock()
    mock_cols.return_value = [col_mock, col_mock, col_mock]
    mock_load.return_value = (None, None, None)

    _render_gps_outliers_checks.__wrapped__(
        "proj", "page", pl.DataFrame(), "key", None, None
    )


@patch("datasure.checks.gpschecks.report_ui._render_outliers_data_table")
@patch("datasure.checks.gpschecks.report_ui.plot_clusters_on_map")
@patch("datasure.checks.gpschecks.report_ui.st.metric")
@patch("datasure.checks.gpschecks.report_ui._run_lof_detection")
@patch("datasure.checks.gpschecks.report_ui.get_df_columns")
@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.report_ui._load_and_parse_gps_data")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
@patch("datasure.checks.gpschecks.report_ui.st.subheader")
def test_render_gps_outliers_lof_success(
    mock_subheader,
    mock_cols,
    mock_load,
    mock_selectbox,
    mock_get_cols,
    mock_run_lof,
    mock_metric,
    mock_plot,
    mock_table,
):
    """Test outlier rendering with LOF method."""
    col_mock = MagicMock()
    mock_cols.return_value = [col_mock, col_mock, col_mock]

    parsed = pl.DataFrame({"latitude": [1.0, 2.0], "longitude": [3.0, 4.0]})
    mock_load.return_value = (pl.DataFrame(), "gps1", parsed)
    mock_get_cols.return_value = ColumnByType(categorical_columns=["grp"])
    mock_selectbox.return_value = GPSOutlierMethod.auto_lof.value

    outlier_df = pd.DataFrame(
        {
            "latitude": [1.0, 2.0],
            "longitude": [3.0, 4.0],
            "Outlier": [False, True],
        }
    )
    mock_run_lof.return_value = outlier_df

    _render_gps_outliers_checks.__wrapped__("proj", "page", parsed, "key", None, None)
    mock_plot.assert_called_once()
    mock_table.assert_called_once()


# =============================================================================
# Tests for _render_gps_comparison_checks and helpers
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui._load_comparison_aliases")
@patch("datasure.checks.gpschecks.report_ui.st.caption")
@patch("datasure.checks.gpschecks.report_ui.st.subheader")
def test_render_gps_comparison_no_aliases(mock_sub, mock_cap, mock_aliases):
    """Test comparison check when no aliases."""
    mock_aliases.return_value = None
    _render_gps_comparison_checks("proj", "page", pl.DataFrame(), "key", None, None)


@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
@patch("datasure.checks.gpschecks.report_ui.st.info")
def test_load_comparison_aliases_empty(mock_info, mock_get):
    """Test loading aliases when none exist."""
    mock_get.return_value = pl.DataFrame()
    result = _load_comparison_aliases.__wrapped__("proj", "page")
    assert result is None
    mock_info.assert_called_once()


@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
@patch("datasure.checks.gpschecks.report_ui.st.warning")
def test_load_comparison_aliases_only_one(mock_warning, mock_get):
    """Test loading aliases when only one exists."""
    mock_get.return_value = pl.DataFrame({"alias": ["gps1"]})
    result = _load_comparison_aliases.__wrapped__("proj", "page")
    assert result is None
    mock_warning.assert_called_once()


@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
def test_load_comparison_aliases_success(mock_get):
    """Test loading aliases when enough exist."""
    mock_get.return_value = pl.DataFrame({"alias": ["gps1", "gps2"]})
    result = _load_comparison_aliases.__wrapped__("proj", "page")
    assert result == ["gps1", "gps2"]


# =============================================================================
# Tests for _render_gps_column_actions
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui._render_gps_settings_table")
@patch("datasure.checks.gpschecks.report_ui._delete_gps_column")
@patch("datasure.checks.gpschecks.report_ui.st.button")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
def test_render_gps_column_actions_with_settings(
    mock_get, mock_cols, mock_btn, mock_del, mock_table
):
    """Test rendering GPS column actions with existing settings."""
    gps_df = pl.DataFrame({"alias": ["gps1"], "format_type": ["Separate Columns"]})
    mock_get.return_value = gps_df
    col_mock = MagicMock()
    mock_cols.return_value = [col_mock, col_mock, col_mock]

    _render_gps_column_actions("proj", "page", ["col1"])
    mock_table.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui.st.info")
@patch("datasure.checks.gpschecks.report_ui._delete_gps_column")
@patch("datasure.checks.gpschecks.report_ui.st.button")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
def test_render_gps_column_actions_empty(
    mock_get, mock_cols, mock_btn, mock_del, mock_info
):
    """Test rendering GPS column actions when empty."""
    mock_get.return_value = pl.DataFrame()
    col_mock = MagicMock()
    mock_cols.return_value = [col_mock, col_mock, col_mock]

    _render_gps_column_actions("proj", "page", ["col1"])
    mock_info.assert_called_once()


# =============================================================================
# Tests for _render_comparison_selectors
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.number_input")
@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
def test_render_comparison_selectors_success(mock_cols, mock_selectbox, mock_number):
    """Test rendering comparison selectors."""
    col_mock = MagicMock()
    mock_cols.return_value = [col_mock, col_mock, col_mock]
    mock_selectbox.side_effect = ["gps1", "gps2"]
    mock_number.return_value = 100

    result = _render_comparison_selectors(["gps1", "gps2", "gps3"])
    assert result == ("gps1", "gps2", 100)


@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
def test_render_comparison_selectors_no_selection(mock_cols, mock_selectbox):
    """Test comparison selectors when no config selected."""
    col_mock = MagicMock()
    mock_cols.return_value = [col_mock, col_mock, col_mock]
    mock_selectbox.side_effect = [None, None]

    result = _render_comparison_selectors(["gps1", "gps2"])
    assert result is None


# =============================================================================
# Tests for gpschecks_report
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui._render_gps_comparison_checks")
@patch("datasure.checks.gpschecks.report_ui._render_gps_outliers_checks")
@patch("datasure.checks.gpschecks.report_ui._render_gps_coordinates")
@patch("datasure.checks.gpschecks.report_ui._render_gps_column_actions")
@patch("datasure.checks.gpschecks.report_ui.gpschecks_report_settings")
@patch("datasure.checks.gpschecks.report_ui.pydeck.settings")
@patch("datasure.checks.gpschecks.report_ui.st.info")
@patch("datasure.checks.gpschecks.report_ui.st.title")
def test_gpschecks_report_empty_data(
    mock_title,
    mock_info,
    mock_pydeck,
    mock_settings_fn,
    mock_actions,
    mock_coords,
    mock_outliers,
    mock_comparison,
):
    """Test report with empty data."""
    data = pl.DataFrame()
    survey_columns = ColumnByType(
        categorical_columns=["col1"],
        datetime_columns=["date"],
    )
    config = {"survey_key": "key"}

    gpschecks_report("proj", "page", data, "settings.json", config, survey_columns)
    mock_info.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui._render_gps_comparison_checks")
@patch("datasure.checks.gpschecks.report_ui._render_gps_outliers_checks")
@patch("datasure.checks.gpschecks.report_ui._render_gps_coordinates")
@patch("datasure.checks.gpschecks.report_ui._render_gps_column_actions")
@patch("datasure.checks.gpschecks.report_ui.gpschecks_report_settings")
@patch("datasure.checks.gpschecks.report_ui.pydeck.settings")
@patch("datasure.checks.gpschecks.report_ui.st.warning")
@patch("datasure.checks.gpschecks.report_ui.st.write")
@patch("datasure.checks.gpschecks.report_ui.st.subheader")
@patch("datasure.checks.gpschecks.report_ui.st.title")
def test_gpschecks_report_no_mapbox(
    mock_title,
    mock_subheader,
    mock_write,
    mock_warning,
    mock_pydeck,
    mock_settings_fn,
    mock_actions,
    mock_coords,
    mock_outliers,
    mock_comparison,
):
    """Test report when no mapbox token."""
    settings = GPSSettings(
        survey_key="key",
        mapbox_custom_key=None,
    )
    mock_settings_fn.return_value = settings

    data = pl.DataFrame({"col1": ["a"], "date": ["2025-01-01"]})
    survey_columns = ColumnByType(
        categorical_columns=["col1"],
        datetime_columns=["date"],
    )
    config = {"survey_key": "key"}

    gpschecks_report("proj", "page", data, "settings.json", config, survey_columns)
    mock_warning.assert_called()
    mock_coords.assert_not_called()


@patch("datasure.checks.gpschecks.report_ui._render_gps_comparison_checks")
@patch("datasure.checks.gpschecks.report_ui._render_gps_outliers_checks")
@patch("datasure.checks.gpschecks.report_ui._render_gps_coordinates")
@patch("datasure.checks.gpschecks.report_ui._render_gps_column_actions")
@patch("datasure.checks.gpschecks.report_ui.gpschecks_report_settings")
@patch("datasure.checks.gpschecks.report_ui.pydeck.settings")
@patch("datasure.checks.gpschecks.report_ui.st.write")
@patch("datasure.checks.gpschecks.report_ui.st.subheader")
@patch("datasure.checks.gpschecks.report_ui.st.title")
def test_gpschecks_report_full_flow(
    mock_title,
    mock_subheader,
    mock_write,
    mock_pydeck,
    mock_settings_fn,
    mock_actions,
    mock_coords,
    mock_outliers,
    mock_comparison,
):
    """Test report full flow with mapbox token."""
    settings = GPSSettings(
        survey_key="key",
        survey_date="date",
        enumerator="enum",
        team="team",
        mapbox_custom_key="token123",
    )
    mock_settings_fn.return_value = settings

    data = pl.DataFrame({"col1": ["a"], "date": ["2025-01-01"]})
    survey_columns = ColumnByType(
        categorical_columns=["col1"],
        datetime_columns=["date"],
    )
    config = {"survey_key": "key"}

    gpschecks_report("proj", "page", data, "settings.json", config, survey_columns)
    mock_coords.assert_called_once()
    mock_outliers.assert_called_once()
    mock_comparison.assert_called_once()


# =============================================================================
# Tests for _render_scatterplot_map
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui._get_mapbox_key")
@patch("datasure.checks.gpschecks.report_ui.st.pydeck_chart")
def test_render_scatterplot_map(mock_pydeck, mock_key):
    """Test rendering scatterplot map."""
    mock_key.return_value = "test_key"
    map_pd = pd.DataFrame({"lat": [1.0, 2.0], "lon": [3.0, 4.0]})
    _render_scatterplot_map(map_pd, ["lat", "lon"])
    mock_pydeck.assert_called_once()


# =============================================================================
# Tests for plot_gps_coordinates without color_col
# =============================================================================


@patch("datasure.checks.gpschecks.compute.pydeck.settings")
@patch("datasure.checks.gpschecks.report_ui.st.pydeck_chart")
def test_plot_gps_coordinates_no_color(mock_pydeck_chart, mock_pydeck_settings):
    """Test GPS plotting without color column."""
    mock_pydeck_settings.mapbox_key = "test"
    data = pd.DataFrame(
        {
            "latitude": [1.0, 2.0],
            "longitude": [3.0, 4.0],
            "survey_id": ["A", "B"],
        }
    )
    plot_gps_coordinates(data, None, None, "survey_id", "latitude", "longitude", None)
    mock_pydeck_chart.assert_called_once()


# =============================================================================
# Tests for plot_clusters_on_map with/without clustering col
# =============================================================================


@patch("datasure.checks.gpschecks.compute.pydeck.settings")
@patch("datasure.checks.gpschecks.report_ui.st.pydeck_chart")
def test_plot_clusters_on_map_no_clustering_col(
    mock_pydeck_chart, mock_pydeck_settings
):
    """Test cluster map without clustering column."""
    mock_pydeck_settings.mapbox_key = "test"
    data = pd.DataFrame(
        {
            "latitude": [1.0],
            "longitude": [2.0],
            "Outlier": [False],
        }
    )
    plot_clusters_on_map(
        data, "latitude", "longitude", None, None, None, None, "Outlier"
    )
    mock_pydeck_chart.assert_called_once()


# =============================================================================
# Tests for _delete_gps_column
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.info")
@patch("datasure.checks.gpschecks.report_ui.st.markdown")
@patch("datasure.checks.gpschecks.report_ui.st.popover")
def test_delete_gps_column_empty(mock_popover, mock_markdown, mock_info):
    """Test delete GPS column with no configurations."""
    mock_popover.return_value.__enter__ = lambda s: s
    mock_popover.return_value.__exit__ = MagicMock(return_value=False)

    _delete_gps_column("proj", "page", pl.DataFrame())
    mock_info.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui.st.button")
@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.report_ui.st.markdown")
@patch("datasure.checks.gpschecks.report_ui.st.popover")
def test_delete_gps_column_with_settings(
    mock_popover, mock_markdown, mock_selectbox, mock_button
):
    """Test delete GPS column UI with existing settings."""
    mock_popover.return_value.__enter__ = lambda s: s
    mock_popover.return_value.__exit__ = MagicMock(return_value=False)
    mock_selectbox.return_value = "0 - gps1 (Separate Columns)"
    mock_button.return_value = False

    gps_settings = pl.DataFrame(
        {"alias": ["gps1"], "format_type": ["Separate Columns"]}
    )

    _delete_gps_column("proj", "page", gps_settings)
    mock_selectbox.assert_called_once()


# =============================================================================
# Tests for _add_gps_column dialog
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.rerun")
@patch("datasure.checks.gpschecks.report_ui.st.success")
@patch("datasure.checks.gpschecks.report_ui._update_gps_column_config")
@patch("datasure.checks.gpschecks.report_ui.st.button")
@patch("datasure.checks.gpschecks.report_ui.st.text_input")
@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.report_ui.st.info")
@patch("datasure.checks.gpschecks.report_ui.st.markdown")
def test_add_gps_column_single_column_valid(
    mock_md,
    mock_info,
    mock_selectbox,
    mock_text_input,
    mock_button,
    mock_update,
    mock_success,
    mock_rerun,
):
    """Test adding GPS config with single column format."""
    mock_selectbox.side_effect = [
        GPSFormatType.SINGLE_COLUMN.value,  # format_type
        DelimiterType.SPACE.value,  # delimiter
        "gps_col",  # gps_column
    ]
    mock_text_input.return_value = "my_gps"
    mock_button.return_value = True

    _add_gps_column.__wrapped__("proj", "page", ["gps_col", "other"])
    mock_update.assert_called_once()
    mock_success.assert_called_once()


@patch("datasure.checks.gpschecks.report_ui.st.button")
@patch("datasure.checks.gpschecks.report_ui.st.text_input")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.report_ui.st.info")
@patch("datasure.checks.gpschecks.report_ui.st.markdown")
def test_add_gps_column_separate_columns_valid(
    mock_md, mock_info, mock_selectbox, mock_columns, mock_text_input, mock_button
):
    """Test adding GPS config with separate columns format."""
    col_mock = MagicMock()
    col_mock.__enter__ = lambda s: s
    col_mock.__exit__ = MagicMock(return_value=False)
    mock_columns.return_value = [col_mock, col_mock]

    mock_selectbox.side_effect = [
        GPSFormatType.SEPARATE_COLUMNS.value,  # format
        "lat_col",  # latitude
        "lon_col",  # longitude
        None,  # altitude
        None,  # accuracy
    ]
    mock_text_input.return_value = "my_gps"
    mock_button.return_value = False

    _add_gps_column.__wrapped__("proj", "page", ["lat_col", "lon_col"])


@patch("datasure.checks.gpschecks.report_ui.st.button")
@patch("datasure.checks.gpschecks.report_ui.st.text_input")
@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.report_ui.st.info")
@patch("datasure.checks.gpschecks.report_ui.st.markdown")
def test_add_gps_column_validation_error(
    mock_md, mock_info, mock_selectbox, mock_text_input, mock_button
):
    """Test adding GPS config with validation error."""
    mock_selectbox.side_effect = [
        GPSFormatType.SINGLE_COLUMN.value,  # format
        DelimiterType.SPACE.value,  # delimiter
        None,  # gps_column - None triggers validation error
    ]
    mock_text_input.return_value = ""  # empty alias
    mock_button.return_value = False

    # Should not raise - validation errors are caught
    _add_gps_column.__wrapped__("proj", "page", ["col1"])


# =============================================================================
# Tests for _delete_gps_column confirm deletion
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.rerun")
@patch("datasure.checks.gpschecks.compute.duckdb_save_table")
@patch("datasure.checks.gpschecks.report_ui.st.button")
@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.report_ui.st.markdown")
@patch("datasure.checks.gpschecks.report_ui.st.popover")
def test_delete_gps_column_confirm(
    mock_popover, mock_markdown, mock_selectbox, mock_button, mock_save, mock_rerun
):
    """Test confirming GPS column deletion."""
    mock_popover.return_value.__enter__ = lambda s: s
    mock_popover.return_value.__exit__ = MagicMock(return_value=False)
    mock_selectbox.return_value = "0 - gps1 (Separate Columns)"
    mock_button.return_value = True

    gps_settings = pl.DataFrame(
        {"alias": ["gps1"], "format_type": ["Separate Columns"]}
    )

    _delete_gps_column("proj", "page", gps_settings)
    mock_save.assert_called_once()
    mock_rerun.assert_called_once()


# =============================================================================
# Tests for _render_gps_comparison_checks full flow
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui._render_comparison_details_table")
@patch("datasure.checks.gpschecks.report_ui._render_comparison_map")
@patch("datasure.checks.gpschecks.report_ui._display_comparison_summary")
@patch("datasure.checks.gpschecks.report_ui._calculate_comparison_distances")
@patch("datasure.checks.gpschecks.report_ui._merge_parsed_gps_data")
@patch("datasure.checks.gpschecks.report_ui._parse_gps_data")
@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
@patch("datasure.checks.gpschecks.report_ui._render_comparison_selectors")
@patch("datasure.checks.gpschecks.report_ui._load_comparison_aliases")
@patch("datasure.checks.gpschecks.report_ui.st.caption")
@patch("datasure.checks.gpschecks.report_ui.st.subheader")
def test_render_gps_comparison_full_flow(
    mock_sub,
    mock_cap,
    mock_aliases,
    mock_selectors,
    mock_get_table,
    mock_parse,
    mock_merge,
    mock_distances,
    mock_summary,
    mock_map,
    mock_details,
):
    """Test comparison checks full flow."""
    mock_aliases.return_value = ["gps1", "gps2"]
    mock_selectors.return_value = ("gps1", "gps2", 100)

    settings_df = pl.DataFrame(
        {
            "alias": ["gps1", "gps2"],
            "format_type": ["Separate Columns"] * 2,
            "delimiter": [None, None],
            "gps_column": [None, None],
            "latitude_column": ["lat1", "lat2"],
            "longitude_column": ["lon1", "lon2"],
            "altitude_column": [None, None],
            "accuracy_column": [None, None],
        }
    )
    mock_get_table.return_value = settings_df

    parsed1 = pl.DataFrame({"latitude": [1.0], "longitude": [2.0], "key": ["A"]})
    parsed2 = pl.DataFrame({"latitude": [1.1], "longitude": [2.1], "key": ["A"]})
    mock_parse.side_effect = [parsed1, parsed2]

    merged = pl.DataFrame(
        {
            "key": ["A"],
            "lat_1": [1.0],
            "lon_1": [2.0],
            "lat_2": [1.1],
            "lon_2": [2.1],
        }
    )
    mock_merge.return_value = merged

    comp_df = pd.DataFrame(
        {
            "key": ["A"],
            "lat_1": [1.0],
            "lon_1": [2.0],
            "lat_2": [1.1],
            "lon_2": [2.1],
            "distance_meters": [50.0],
        }
    )
    mock_distances.return_value = comp_df

    data = pl.DataFrame({"lat1": [1.0], "lon1": [2.0], "lat2": [1.1], "lon2": [2.1]})

    _render_gps_comparison_checks("proj", "page", data, "key", None, None)
    mock_summary.assert_called_once()
    mock_map.assert_called_once()
    mock_details.assert_called_once()


# =============================================================================
# Tests for _render_gps_coordinates empty filter
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.warning")
@patch("datasure.checks.gpschecks.report_ui._apply_category_filter")
@patch("datasure.checks.gpschecks.report_ui.get_df_columns")
@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.report_ui._load_and_parse_gps_data")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
@patch("datasure.checks.gpschecks.report_ui.st.subheader")
def test_render_gps_coordinates_empty_filter(
    mock_subheader,
    mock_cols,
    mock_load,
    mock_selectbox,
    mock_get_cols,
    mock_filter,
    mock_warning,
):
    """Test GPS coordinates with empty filtered data."""
    col_mock = MagicMock()
    mock_cols.return_value = [col_mock, col_mock, col_mock]

    parsed = pl.DataFrame({"latitude": [1.0], "longitude": [2.0], "key": ["A"]})
    mock_load.return_value = (pl.DataFrame(), "gps1", parsed)
    mock_get_cols.return_value = ColumnByType(categorical_columns=["key"])
    mock_selectbox.return_value = None
    mock_filter.return_value = pl.DataFrame()

    _render_gps_coordinates.__wrapped__("proj", "page", parsed, "key", None, None, None)
    mock_warning.assert_called_once()


# =============================================================================
# Tests for _render_gps_outliers cluster method
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui._render_outliers_data_table")
@patch("datasure.checks.gpschecks.report_ui.plot_clusters_on_map")
@patch("datasure.checks.gpschecks.report_ui.st.metric")
@patch("datasure.checks.gpschecks.report_ui._run_cluster_detection")
@patch("datasure.checks.gpschecks.report_ui.get_df_columns")
@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.report_ui._load_and_parse_gps_data")
@patch("datasure.checks.gpschecks.report_ui.st.columns")
@patch("datasure.checks.gpschecks.report_ui.st.subheader")
def test_render_gps_outliers_cluster_success(
    mock_subheader,
    mock_cols,
    mock_load,
    mock_selectbox,
    mock_get_cols,
    mock_run_cluster,
    mock_metric,
    mock_plot,
    mock_table,
):
    """Test outlier rendering with cluster method."""
    col_mock = MagicMock()
    mock_cols.return_value = [col_mock, col_mock, col_mock]

    parsed = pl.DataFrame({"latitude": [1.0, 2.0], "longitude": [3.0, 4.0]})
    mock_load.return_value = (pl.DataFrame(), "gps1", parsed)
    mock_get_cols.return_value = ColumnByType(categorical_columns=["grp"])
    mock_selectbox.return_value = GPSOutlierMethod.columns.value

    outlier_df = pd.DataFrame(
        {
            "latitude": [1.0, 2.0],
            "longitude": [3.0, 4.0],
            "Outlier": [False, True],
        }
    )
    mock_run_cluster.return_value = (outlier_df, "grp")

    _render_gps_outliers_checks.__wrapped__("proj", "page", parsed, "key", None, None)
    mock_plot.assert_called_once()
    mock_table.assert_called_once()


# =============================================================================
# Tests for _load_and_parse_gps_data alias_select_key branch
# =============================================================================


@patch("datasure.checks.gpschecks.report_ui.st.selectbox")
@patch("datasure.checks.gpschecks.compute.duckdb_get_table")
def test_load_and_parse_gps_data_with_alias_key(mock_get_table, mock_selectbox):
    """Test GPS data loading with custom alias select key."""
    schema = {
        "alias": pl.Utf8,
        "format_type": pl.Utf8,
        "delimiter": pl.Utf8,
        "gps_column": pl.Utf8,
        "latitude_column": pl.Utf8,
        "longitude_column": pl.Utf8,
        "altitude_column": pl.Utf8,
        "accuracy_column": pl.Utf8,
    }
    settings = pl.DataFrame(
        {
            "alias": ["gps1"],
            "format_type": ["Separate Columns"],
            "delimiter": [None],
            "gps_column": [None],
            "latitude_column": ["lat"],
            "longitude_column": ["lon"],
            "altitude_column": [None],
            "accuracy_column": [None],
        },
        schema=schema,
    )
    mock_get_table.return_value = settings
    mock_selectbox.return_value = "gps1"

    data = pl.DataFrame({"lat": [1.0], "lon": [2.0]})
    _, alias, _parsed = _load_and_parse_gps_data(
        "proj", "page", data, alias_select_key="custom_key"
    )
    assert alias == "gps1"
    # Verify selectbox was called with the key
    call_kwargs = mock_selectbox.call_args
    assert call_kwargs[1].get("key") == "custom_key"
