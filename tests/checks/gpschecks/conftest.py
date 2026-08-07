"""Shared fixtures for the split gpschecks module test suite."""

import json
import os
import tempfile

import pandas as pd
import pytest


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests.
    """
    pass


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
