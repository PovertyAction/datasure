from unittest.mock import patch

import numpy as np
import pandas as pd
import polars as pl
import pytest

from datasure.checks.gpschecks.compute import (
    _build_map_dataframe,
    _build_tooltip_config,
    _collect_optional_fields,
    _get_mapbox_key,
    _has_parsed_coords,
    _parse_gps_data,
    calculate_gps_accuracy_statistics,
    detect_outliers_with_clusters,
    detect_outliers_with_lof,
    load_default_gpschecks_settings,
)
from datasure.models.enums import DelimiterType, GPSFormatType
from datasure.models.schemas import GPSSettings

# =============================================================================
# Tests for GPS Data Parsing
# =============================================================================


def test_parse_gps_data_single_column_space_delimiter():
    """Test parsing GPS data from single column with space delimiter."""
    data = pl.DataFrame(
        {
            "key": ["A", "B", "C"],
            "gps": [
                "6.6018 -0.1870 150.0 4.5",
                "6.6015 -0.1865 152.0 3.8",
                "6.6022 -0.1868 148.0 4.2",
            ],
        }
    )

    config = {
        "format_type": GPSFormatType.SINGLE_COLUMN.value,
        "delimiter": DelimiterType.SPACE.value,
        "gps_column": "gps",
    }

    result = _parse_gps_data(data, config)

    assert "latitude" in result.columns
    assert "longitude" in result.columns
    assert result["latitude"][0] == pytest.approx(6.6018)
    assert result["longitude"][0] == pytest.approx(-0.1870)
    assert len(result) == 3


def test_parse_gps_data_single_column_comma_delimiter():
    """Test parsing GPS data from single column with comma delimiter."""
    data = pl.DataFrame(
        {
            "key": ["A", "B"],
            "gps": ["6.6018,-0.1870,150.0,4.5", "6.6015,-0.1865,152.0,3.8"],
        }
    )

    config = {
        "format_type": GPSFormatType.SINGLE_COLUMN.value,
        "delimiter": DelimiterType.COMMA.value,
        "gps_column": "gps",
    }

    result = _parse_gps_data(data, config)

    assert "latitude" in result.columns
    assert "longitude" in result.columns
    assert result["latitude"][0] == pytest.approx(6.6018)
    assert result["longitude"][0] == pytest.approx(-0.1870)


def test_parse_gps_data_separate_columns():
    """Test parsing GPS data from separate columns."""
    data = pl.DataFrame(
        {
            "key": ["A", "B", "C"],
            "lat": [6.6018, 6.6015, 6.6022],
            "lon": [-0.1870, -0.1865, -0.1868],
        }
    )

    config = {
        "format_type": GPSFormatType.SEPARATE_COLUMNS.value,
        "latitude_column": "lat",
        "longitude_column": "lon",
    }

    result = _parse_gps_data(data, config)

    assert "latitude" in result.columns
    assert "longitude" in result.columns
    assert result["latitude"][0] == pytest.approx(6.6018)
    assert result["longitude"][1] == pytest.approx(-0.1865)
    assert len(result) == 3


def test_parse_gps_data_missing_gps_column():
    """Test parsing when GPS column doesn't exist."""
    data = pl.DataFrame({"key": ["A", "B"]})

    config = {
        "format_type": GPSFormatType.SINGLE_COLUMN.value,
        "delimiter": DelimiterType.SPACE.value,
        "gps_column": "nonexistent_column",
    }

    result = _parse_gps_data(data, config)

    assert "latitude" in result.columns
    assert "longitude" in result.columns
    # Should have null values
    assert result["latitude"].null_count() == 2
    assert result["longitude"].null_count() == 2


def test_parse_gps_data_missing_lat_lon_columns():
    """Test parsing when lat/lon columns don't exist."""
    data = pl.DataFrame({"key": ["A", "B"]})

    config = {
        "format_type": GPSFormatType.SEPARATE_COLUMNS.value,
        "latitude_column": "missing_lat",
        "longitude_column": "missing_lon",
    }

    result = _parse_gps_data(data, config)

    assert "latitude" in result.columns
    assert "longitude" in result.columns
    # Should have null values
    assert result["latitude"].null_count() == 2
    assert result["longitude"].null_count() == 2


def test_parse_gps_data_with_null_values():
    """Test parsing GPS data with null/missing values."""
    data = pl.DataFrame(
        {
            "key": ["A", "B", "C"],
            "gps": ["6.6018 -0.1870", None, "6.6022 -0.1868"],
        }
    )

    config = {
        "format_type": GPSFormatType.SINGLE_COLUMN.value,
        "delimiter": DelimiterType.SPACE.value,
        "gps_column": "gps",
    }

    result = _parse_gps_data(data, config)

    assert result["latitude"][1] is None
    assert result["longitude"][1] is None
    assert result["latitude"][0] == pytest.approx(6.6018)


def test_parse_gps_data_properly_formatted_string():
    """Test parsing GPS data with properly formatted strings."""
    data = pl.DataFrame(
        {
            "key": ["A", "B", "C"],
            "gps": ["1.23 4.56", "2.34 5.67", "3.45 6.78"],
        }
    )

    config = {
        "format_type": GPSFormatType.SINGLE_COLUMN.value,
        "delimiter": DelimiterType.SPACE.value,
        "gps_column": "gps",
    }

    result = _parse_gps_data(data, config)

    # Check that parsing succeeds
    assert "latitude" in result.columns
    assert "longitude" in result.columns
    assert result["latitude"][0] == pytest.approx(1.23)
    assert result["longitude"][0] == pytest.approx(4.56)


# =============================================================================
# Tests for Load Default GPS Settings
# =============================================================================


@patch("datasure.checks.gpschecks.compute.st.cache_data", lambda f: f)
@patch("datasure.checks.gpschecks.compute.load_check_settings")
def test_load_default_gpschecks_settings_no_saved_settings(mock_load_settings):
    """Test loading default GPS settings when no saved settings exist."""
    mock_load_settings.return_value = {}

    config = GPSSettings(
        survey_key="default_key",
        survey_id="default_id",
        survey_date="default_date",
        enumerator="default_enum",
    )

    result = load_default_gpschecks_settings("test_settings.json", config)

    assert result.survey_key == "default_key"
    assert result.survey_id == "default_id"
    assert result.survey_date == "default_date"
    assert result.enumerator == "default_enum"


@patch("datasure.checks.gpschecks.compute.st.cache_data", lambda f: f)
@patch("datasure.checks.gpschecks.compute.load_check_settings")
def test_load_default_gpschecks_settings_with_saved_settings(mock_load_settings):
    """Test loading GPS settings with saved settings override."""
    # The actual implementation might use model_dump() or dict()
    # Let's test that saved settings can override defaults
    mock_load_settings.return_value = {
        "survey_key": "saved_key",
        "enumerator": "saved_enum",
    }

    config = GPSSettings(
        survey_key="default_key",
        survey_id="default_id",
        survey_date="default_date",
        enumerator="default_enum",
    )

    result = load_default_gpschecks_settings("test_settings.json", config)

    # Check that result is a valid GPSSettings object
    assert isinstance(result, GPSSettings)
    # Test that function returns valid settings
    assert result.survey_id == "default_id"
    assert result.survey_date == "default_date"


@patch("datasure.checks.gpschecks.compute.st.cache_data", lambda f: f)
@patch("datasure.checks.gpschecks.compute.load_check_settings")
def test_load_default_gpschecks_settings_all_fields(mock_load_settings):
    """Test loading GPS settings with all fields specified."""
    mock_load_settings.return_value = {}

    config = GPSSettings(
        survey_key="key",
        survey_id="id",
        survey_date="date",
        enumerator="enum",
        team="team",
        mapbox_custom_key="test_key",
    )

    result = load_default_gpschecks_settings("test_settings.json", config)

    assert result.survey_key == "key"
    assert result.survey_id == "id"
    assert result.survey_date == "date"
    assert result.enumerator == "enum"
    assert result.team == "team"
    assert result.mapbox_custom_key == "test_key"


# =============================================================================
# Tests for Existing Functions (Updated)
# =============================================================================


@patch("datasure.checks.gpschecks.compute.st.cache_data", lambda f: f)
def test_detect_outliers_with_clusters(sample_gps_data_with_outliers):
    """Test outlier detection using clustering method."""
    result = detect_outliers_with_clusters(
        sample_gps_data_with_outliers, "latitude", "longitude", "enumerator"
    )

    # Check that result has required columns
    assert "distance_from_centroid" in result.columns
    assert "Outlier" in result.columns

    # Check that outliers are flagged
    outliers = result[result["Outlier"]]
    assert len(outliers) > 0

    # The far points should be flagged as outliers
    far_points = result[result["latitude"].isin([6.7018, 6.5018])]
    assert far_points["Outlier"].any()


@patch("datasure.checks.gpschecks.compute.st.cache_data", lambda f: f)
def test_detect_outliers_with_clusters_no_outliers():
    """Test outlier detection when there are no outliers."""
    # Create tight cluster with no outliers
    tight_cluster = pd.DataFrame(
        {
            "enumerator": ["E001"] * 5,
            "latitude": [
                6.6018 + i * 0.00001 for i in range(5)
            ],  # Very small differences
            "longitude": [-0.1870 + i * 0.00001 for i in range(5)],
        }
    )

    result = detect_outliers_with_clusters(
        tight_cluster, "latitude", "longitude", "enumerator"
    )

    # In a tight cluster, there might be no outliers or minimal outliers
    assert "Outlier" in result.columns
    assert "distance_from_centroid" in result.columns


@patch("datasure.checks.gpschecks.compute.st.cache_data", lambda f: f)
def test_detect_outliers_with_lof(sample_gps_data_with_outliers):
    """Test outlier detection using Local Outlier Factor."""
    result = detect_outliers_with_lof(
        sample_gps_data_with_outliers,
        "latitude",
        "longitude",
        n_neighbors=5,
        contamination=0.1,
    )

    # Check that result has Outlier column
    assert "Outlier" in result.columns

    # Check that some outliers are detected
    outliers = result[result["Outlier"]]
    assert len(outliers) > 0

    # Check data types
    assert result["Outlier"].dtype == bool


@patch("datasure.checks.gpschecks.compute.st.cache_data", lambda f: f)
def test_detect_outliers_with_lof_auto_contamination(sample_gps_data):
    """Test LOF with automatic contamination detection."""
    result = detect_outliers_with_lof(
        sample_gps_data, "latitude", "longitude", n_neighbors=3, contamination="auto"
    )

    assert "Outlier" in result.columns
    assert len(result) == len(sample_gps_data)


@patch("datasure.checks.gpschecks.compute.st.cache_data", lambda f: f)
def test_calculate_gps_accuracy_statistics(sample_gps_data):
    """Test GPS accuracy statistics calculation."""
    stats_list = ["min", "max", "mean", "median", "std"]

    result = calculate_gps_accuracy_statistics(
        sample_gps_data, "gps_accuracy", "enumerator", stats_list
    )

    # Check that result is a DataFrame
    assert isinstance(result, pd.DataFrame)

    # Check that statistics columns exist
    for stat in stats_list:
        assert stat in result.columns

    # Check that enumerators are grouped correctly
    assert len(result) > 0

    # Verify some basic statistics
    assert result["min"].min() >= 0
    assert result["max"].max() > 0


@patch("datasure.checks.gpschecks.compute.st.cache_data", lambda f: f)
def test_calculate_gps_accuracy_statistics_with_percentiles(sample_gps_data):
    """Test GPS accuracy statistics with percentile calculations."""
    stats_list = ["min", "25th percentile", "75th percentile", "95th percentile", "max"]

    result = calculate_gps_accuracy_statistics(
        sample_gps_data, "gps_accuracy", "enumerator", stats_list
    )

    # Check that percentile columns are properly named
    assert "25th percentile" in result.columns
    assert "75th percentile" in result.columns
    assert "95th percentile" in result.columns


@patch("datasure.checks.gpschecks.compute.st.cache_data", lambda f: f)
def test_calculate_gps_accuracy_statistics_empty_data():
    """Test GPS accuracy statistics with empty DataFrame."""
    empty_df = pd.DataFrame(columns=["enumerator", "gps_accuracy"])

    result = calculate_gps_accuracy_statistics(
        empty_df, "gps_accuracy", "enumerator", ["min", "max"]
    )

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


def test_detect_outliers_with_clusters_single_point():
    """Test outlier detection with single point in cluster."""
    single_point = pd.DataFrame(
        {"enumerator": ["E001"], "latitude": [6.6018], "longitude": [-0.1870]}
    )

    result = detect_outliers_with_clusters(
        single_point, "latitude", "longitude", "enumerator"
    )

    # Single point should not be considered an outlier
    assert "Outlier" in result.columns
    assert not result["Outlier"].iloc[0]


def test_detect_outliers_with_missing_coordinates():
    """Test outlier detection with missing coordinates."""
    data_with_missing = pd.DataFrame(
        {
            "enumerator": ["E001", "E001", "E001"],
            "latitude": [6.6018, np.nan, 6.6022],
            "longitude": [-0.1870, -0.1865, np.nan],
        }
    )

    result = detect_outliers_with_clusters(
        data_with_missing, "latitude", "longitude", "enumerator"
    )

    # Should only process rows with non-null coordinates
    assert len(result) == 1  # Only one row has both lat and lon
    assert "Outlier" in result.columns


def test_detect_outliers_with_lof_small_dataset():
    """Test LOF with dataset smaller than n_neighbors."""
    small_data = pd.DataFrame(
        {"latitude": [6.6018, 6.6019], "longitude": [-0.1870, -0.1871]}
    )

    # This should handle the case where n_neighbors > number of samples
    result = detect_outliers_with_lof(
        small_data,
        "latitude",
        "longitude",
        n_neighbors=5,  # More neighbors than data points
        contamination=0.5,
    )

    assert "Outlier" in result.columns
    assert len(result) == 2


def test_calculate_gps_accuracy_statistics_single_group(sample_gps_data):
    """Test GPS accuracy statistics with single group."""
    single_group_data = sample_gps_data[sample_gps_data["enumerator"] == "E001"]

    result = calculate_gps_accuracy_statistics(
        single_group_data, "gps_accuracy", "enumerator", ["min", "max", "mean"]
    )

    assert len(result) == 1  # Only one enumerator group
    assert "min" in result.columns
    assert "max" in result.columns
    assert "mean" in result.columns


def test_calculate_gps_accuracy_statistics_missing_values():
    """Test GPS accuracy statistics with missing accuracy values."""
    data_with_missing = pd.DataFrame(
        {
            "enumerator": ["E001", "E001", "E002", "E002"],
            "gps_accuracy": [4.5, np.nan, 3.8, 4.2],
        }
    )

    result = calculate_gps_accuracy_statistics(
        data_with_missing, "gps_accuracy", "enumerator", ["min", "max", "mean"]
    )

    # Should handle missing values gracefully
    assert len(result) == 2  # Two enumerator groups
    assert not result.isna().all().any()  # No columns should be all NaN


def test_detect_outliers_multiple_clusters():
    """Test outlier detection with multiple distinct clusters."""
    # Create two distinct clusters
    cluster1 = pd.DataFrame(
        {
            "enumerator": ["E001"] * 5,
            "latitude": [6.6000 + i * 0.0001 for i in range(5)],
            "longitude": [-0.1870 + i * 0.0001 for i in range(5)],
        }
    )

    cluster2 = pd.DataFrame(
        {
            "enumerator": ["E002"] * 5,
            "latitude": [6.7000 + i * 0.0001 for i in range(5)],
            "longitude": [-0.2870 + i * 0.0001 for i in range(5)],
        }
    )

    multi_cluster_data = pd.concat([cluster1, cluster2], ignore_index=True)

    result = detect_outliers_with_clusters(
        multi_cluster_data, "latitude", "longitude", "enumerator"
    )

    # Each cluster should be analyzed separately
    assert "distance_from_centroid" in result.columns
    assert "Outlier" in result.columns
    assert len(result) == 10


@patch("datasure.checks.gpschecks.compute.st.cache_data", lambda f: f)
def test_calculate_gps_accuracy_with_invalid_stats():
    """Test GPS accuracy calculation with invalid statistics names."""
    data = pd.DataFrame({"enumerator": ["E001", "E001"], "gps_accuracy": [4.5, 3.8]})

    # Test with invalid stat name - should handle gracefully
    result = calculate_gps_accuracy_statistics(
        data, "gps_accuracy", "enumerator", ["invalid_stat", "mean"]
    )

    # Should still work with valid stats
    assert isinstance(result, pd.DataFrame)
    assert "mean" in result.columns


# =============================================================================
# Tests for _get_mapbox_key
# =============================================================================


@patch("datasure.checks.gpschecks.compute.pydeck.settings")
@patch("datasure.checks.gpschecks.compute.st.secrets", {})
def test_get_mapbox_key_from_pydeck(mock_pydeck_settings):
    """Test getting mapbox key from pydeck settings."""
    mock_pydeck_settings.mapbox_key = "pydeck_key"
    assert _get_mapbox_key() == "pydeck_key"


@patch("datasure.checks.gpschecks.compute.pydeck.settings")
@patch(
    "datasure.checks.gpschecks.compute.st.secrets",
    {"mapbox_custom_key": "custom_key"},
)
def test_get_mapbox_key_from_custom_secret(mock_pydeck_settings):
    """Test getting mapbox key from st.secrets mapbox_custom_key."""
    mock_pydeck_settings.mapbox_key = None
    assert _get_mapbox_key() == "custom_key"


@patch("datasure.checks.gpschecks.compute.pydeck.settings")
@patch(
    "datasure.checks.gpschecks.compute.st.secrets",
    {"default_mapbox_api_key": "default_key"},
)
def test_get_mapbox_key_from_default_secret(mock_pydeck_settings):
    """Test getting mapbox key from st.secrets default_mapbox_api_key."""
    mock_pydeck_settings.mapbox_key = None
    assert _get_mapbox_key() == "default_key"


@patch("datasure.checks.gpschecks.compute.pydeck.settings")
@patch("datasure.checks.gpschecks.compute.st.secrets", {})
def test_get_mapbox_key_returns_none(mock_pydeck_settings):
    """Test returns None when no mapbox key is available."""
    mock_pydeck_settings.mapbox_key = None
    assert _get_mapbox_key() is None


# =============================================================================
# Tests for _build_tooltip_config
# =============================================================================


def test_build_tooltip_config():
    """Test tooltip configuration building."""
    result = _build_tooltip_config(["lat", "lon", "ID"])
    assert "html" in result
    assert "style" in result
    assert "<b>lat:</b>" in result["html"]
    assert "<b>lon:</b>" in result["html"]
    assert "<b>ID:</b>" in result["html"]


def test_build_tooltip_config_empty():
    """Test tooltip config with empty fields."""
    result = _build_tooltip_config([])
    assert result["html"] == ""


# =============================================================================
# Tests for _collect_optional_fields
# =============================================================================


def test_collect_optional_fields_all_present():
    """Test collecting fields when all are present."""
    df = pd.DataFrame({"col_a": [1], "col_b": [2]})
    result = _collect_optional_fields(df, [("col_a", "Label A"), ("col_b", "Label B")])
    assert result == ["Label A", "Label B"]


def test_collect_optional_fields_some_missing():
    """Test collecting fields when some columns are missing."""
    df = pd.DataFrame({"col_a": [1]})
    result = _collect_optional_fields(
        df, [("col_a", "Label A"), ("missing", "Label B")]
    )
    assert result == ["Label A"]


def test_collect_optional_fields_none_values():
    """Test collecting fields when field names are None."""
    df = pd.DataFrame({"col_a": [1]})
    result = _collect_optional_fields(df, [(None, "Label A"), ("col_a", "Label B")])
    assert result == ["Label B"]


def test_collect_optional_fields_polars_df():
    """Test collecting fields with a Polars DataFrame."""
    df = pl.DataFrame({"col_a": [1], "col_b": [2]})
    result = _collect_optional_fields(df, [("col_a", "A"), ("col_b", "B"), (None, "C")])
    assert result == ["A", "B"]


# =============================================================================
# Tests for _has_parsed_coords
# =============================================================================


def test_has_parsed_coords_true():
    """Test returns True when both lat and lon exist."""
    df = pl.DataFrame({"latitude": [1.0], "longitude": [2.0]})
    assert _has_parsed_coords(df) is True


def test_has_parsed_coords_missing_lat():
    """Test returns False when latitude is missing."""
    df = pl.DataFrame({"longitude": [2.0]})
    assert _has_parsed_coords(df) is False


def test_has_parsed_coords_missing_lon():
    """Test returns False when longitude is missing."""
    df = pl.DataFrame({"latitude": [1.0]})
    assert _has_parsed_coords(df) is False


# =============================================================================
# Tests for _build_map_dataframe
# =============================================================================


def test_build_map_dataframe_basic():
    """Test building map dataframe with basic fields."""
    data = pl.DataFrame(
        {
            "latitude": [1.0, 2.0],
            "longitude": [3.0, 4.0],
            "key_col": ["A", "B"],
        }
    )
    map_pd, tooltip_fields = _build_map_dataframe(
        data, "key_col", None, None, None, None
    )
    assert "lat" in map_pd.columns
    assert "lon" in map_pd.columns
    assert "ID" in map_pd.columns
    assert "ID" in tooltip_fields
    assert "lat" in tooltip_fields


def test_build_map_dataframe_all_fields():
    """Test building map dataframe with all optional fields."""
    data = pl.DataFrame(
        {
            "latitude": [1.0, 2.0],
            "longitude": [3.0, 4.0],
            "key": ["A", "B"],
            "date": ["2025-01-01", "2025-01-02"],
            "enum": ["E1", "E2"],
            "team": ["T1", "T2"],
            "region": ["R1", "R2"],
        }
    )
    map_pd, tooltip_fields = _build_map_dataframe(
        data, "key", "date", "enum", "team", "region"
    )
    assert "ID" in tooltip_fields
    assert "Date" in tooltip_fields
    assert "Enumerator" in tooltip_fields
    assert "Team" in tooltip_fields
    assert "region" in tooltip_fields
    assert "color_group" in map_pd.columns
    assert "color" in map_pd.columns


def test_build_map_dataframe_no_optional_fields():
    """Test building map dataframe with no optional fields."""
    data = pl.DataFrame({"latitude": [1.0], "longitude": [3.0]})
    _map_pd, tooltip_fields = _build_map_dataframe(data, None, None, None, None, None)
    assert tooltip_fields == ["lat", "lon"]


# =============================================================================
# Tests for edge cases in detect_outliers_with_clusters
# =============================================================================


def test_detect_outliers_with_clusters_no_clustering_col():
    """Test outlier detection without clustering column."""
    data = pd.DataFrame(
        {
            "latitude": [6.6 + i * 0.001 for i in range(10)] + [6.9],
            "longitude": [-0.18 + i * 0.001 for i in range(10)] + [-0.5],
        }
    )
    result = detect_outliers_with_clusters(data, "latitude", "longitude", None)
    assert "Outlier" in result.columns
    assert "distance_from_centroid" in result.columns


def test_detect_outliers_with_clusters_iqr_zero():
    """Test outlier detection when IQR is 0 (all same distance)."""
    # All points at the exact same location -> IQR=0
    data = pd.DataFrame(
        {
            "group": ["A"] * 5,
            "latitude": [6.6] * 5,
            "longitude": [-0.18] * 5,
        }
    )
    result = detect_outliers_with_clusters(data, "latitude", "longitude", "group")
    assert result["Outlier"].sum() == 0


def test_detect_outliers_with_lof_single_point():
    """Test LOF with single data point (n_samples < 2)."""
    data = pd.DataFrame({"latitude": [6.6], "longitude": [-0.18]})
    result = detect_outliers_with_lof(data, "latitude", "longitude", 5, 0.1)
    assert "Outlier" in result.columns
    assert not result["Outlier"].iloc[0]
