import json
import os
import tempfile
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from datasure.checks.gpschecks import (
    calculate_gps_accuracy_statistics,
    detect_outliers_with_clusters,
    detect_outliers_with_lof,
    load_default_settings,
    plot_clusters_on_map,
    plot_gps_coordinates,
)


@pytest.fixture
def sample_gps_data():
    """Create sample GPS data for testing."""
    return pd.DataFrame(
        {
            "survey_key": ["KEY001", "KEY002", "KEY003", "KEY004", "KEY005"],
            "survey_id": ["ID001", "ID002", "ID003", "ID004", "ID005"],
            "enumerator": ["E001", "E001", "E002", "E002", "E003"],
            "submissiondate": pd.date_range("2025-01-01", periods=5),
            "latitude": [6.6018, 6.6015, 6.6022, 6.6025, 6.6019],
            "longitude": [-0.1870, -0.1865, -0.1868, -0.1872, -0.1867],
            "gps_accuracy": [4.5, 3.8, 4.2, 3.9, 4.1],
            "altitude": [150.0, 152.0, 148.0, 151.0, 149.0],
        }
    )


@pytest.fixture
def sample_gps_data_with_outliers():
    """Create sample GPS data with known outliers for testing."""
    # Normal cluster points
    normal_data = pd.DataFrame(
        {
            "survey_key": [f"KEY{i:03d}" for i in range(1, 11)],
            "survey_id": [f"ID{i:03d}" for i in range(1, 11)],
            "enumerator": ["E001"] * 10,
            "submissiondate": pd.date_range("2025-01-01", periods=10),
            "latitude": [6.6018 + i * 0.0001 for i in range(10)],
            "longitude": [-0.1870 + i * 0.0001 for i in range(10)],
            "gps_accuracy": [4.0 + i * 0.1 for i in range(10)],
        }
    )

    # Outlier points (far from cluster)
    outlier_data = pd.DataFrame(
        {
            "survey_key": ["KEY_OUT1", "KEY_OUT2"],
            "survey_id": ["ID_OUT1", "ID_OUT2"],
            "enumerator": ["E001", "E001"],
            "submissiondate": pd.date_range("2025-01-11", periods=2),
            "latitude": [6.7018, 6.5018],  # Significantly different locations
            "longitude": [-0.2870, -0.0870],
            "gps_accuracy": [4.0, 4.0],
        }
    )

    return pd.concat([normal_data, outlier_data], ignore_index=True)


@pytest.fixture
def sample_gps_string_data():
    """Create sample GPS data with GPS coordinates as string for testing parsing."""
    return pd.DataFrame(
        {
            "survey_key": ["KEY001", "KEY002", "KEY003", "KEY004"],
            "survey_id": ["ID001", "ID002", "ID003", "ID004"],
            "enumerator": ["E001", "E001", "E002", "E002"],
            "submissiondate": pd.date_range("2025-01-01", periods=4),
            "gps": [
                "6.6018,-0.1870,4.5,150.0",  # lat,lon,accuracy,altitude
                "6.6015,-0.1865,3.8,152.0",
                "6.6022,-0.1868",  # lat,lon only
                "6.6025\t-0.1872\t3.9",  # tab-separated
            ],
        }
    )


@pytest.fixture
def mock_settings_file():
    """Create a temporary settings file for testing."""
    settings_data = {
        "gpscheck": {
            "date": "submissiondate",
            "enumerator": "enumerator",
            "survey_key": "survey_key",
            "survey_id": "survey_id",
            "gps_column_exists": True,
            "lat_lon_columns_exist": True,
            "gps_lat_col": "latitude",
            "gps_lon_col": "longitude",
            "gps_accuracy": "gps_accuracy",
            "gps_column": None,
        }
    }

    with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".json") as tmp:
        json.dump(settings_data, tmp)
        tmp_path = tmp.name

    yield tmp_path

    # Cleanup
    os.unlink(tmp_path)


@pytest.fixture
def mock_session_state_gps():
    """Create mock session state for GPS checks."""
    return {
        "config_pages": {
            "Survey Date": ["submissiondate", "date", "submission_date"],
            "Enumerator": ["enumerator", "enum_id", "interviewer"],
            "Survey ID": ["survey_id", "id", "unique_id"],
            "Survey KEY": ["survey_key", "key", "unique_key"],
        }
    }


@patch("datasure.checks.gpschecks.st.cache_data", lambda f: f)
@patch("datasure.checks.gpschecks.get_check_config_settings")
def test_load_default_settings_no_file(mock_config_settings):
    """Test loading default settings when no settings file exists."""
    # Mock the config settings function to return expected values
    mock_config_settings.return_value = (
        None,
        None,
        "survey_key",
        "survey_id",
        "submissiondate",
        "enumerator",
        None,
        None,
        None,
        None,
        None,
        None,
    )

    result = load_default_settings("test_project", None, 1)

    assert len(result) == 10
    assert result[0] == "submissiondate"
    assert result[1] == "enumerator"
    assert result[2] == "survey_id"
    assert result[3] == "survey_key"
    assert result[4] is False  # gps_column_exists
    assert result[5] is False  # lat_lon_exist


@patch("datasure.checks.gpschecks.st.cache_data", lambda f: f)
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


@patch("datasure.checks.gpschecks.st.cache_data", lambda f: f)
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


@patch("datasure.checks.gpschecks.st.cache_data", lambda f: f)
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


@patch("datasure.checks.gpschecks.st.cache_data", lambda f: f)
def test_detect_outliers_with_lof_auto_contamination(sample_gps_data):
    """Test LOF with automatic contamination detection."""
    result = detect_outliers_with_lof(
        sample_gps_data, "latitude", "longitude", n_neighbors=3, contamination="auto"
    )

    assert "Outlier" in result.columns
    assert len(result) == len(sample_gps_data)


@patch("datasure.checks.gpschecks.st.cache_data", lambda f: f)
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


@patch("datasure.checks.gpschecks.st.cache_data", lambda f: f)
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


@patch("datasure.checks.gpschecks.st.cache_data", lambda f: f)
def test_calculate_gps_accuracy_statistics_empty_data():
    """Test GPS accuracy statistics with empty DataFrame."""
    empty_df = pd.DataFrame(columns=["enumerator", "gps_accuracy"])

    result = calculate_gps_accuracy_statistics(
        empty_df, "gps_accuracy", "enumerator", ["min", "max"]
    )

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


@patch("datasure.checks.gpschecks.st.pydeck_chart")
def test_plot_gps_coordinates(mock_pydeck_chart, sample_gps_data):
    """Test GPS coordinates plotting function."""
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


@patch("datasure.checks.gpschecks.st.pydeck_chart")
def test_plot_gps_coordinates_with_missing_data(mock_pydeck_chart):
    """Test GPS coordinates plotting with missing coordinates."""
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


@patch("datasure.checks.gpschecks.st.pydeck_chart")
def test_plot_clusters_on_map(mock_pydeck_chart, sample_gps_data_with_outliers):
    """Test plotting clusters on map with outlier highlighting."""
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


@patch("datasure.checks.gpschecks.st.pydeck_chart")
def test_plot_clusters_on_map_all_normal_points(mock_pydeck_chart, sample_gps_data):
    """Test plotting clusters when all points are normal (no outliers)."""
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


@patch("datasure.checks.gpschecks.st.pydeck_chart")
def test_plot_gps_coordinates_many_unique_values(mock_pydeck_chart):
    """Test GPS plotting with many unique values for color coding."""
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


@patch("datasure.checks.gpschecks.st.cache_data", lambda f: f)
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
