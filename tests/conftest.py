from unittest.mock import MagicMock

import pandas as pd
import pytest


@pytest.fixture
def sample_dataframe():
    """Create a sample dataframe for testing."""
    return pd.DataFrame(
        {
            "id": range(1, 6),
            "enumid": ["E001", "E002", "E001", "E003", "E002"],
            "latitude": [6.6018, 6.6015, 6.6022, 6.6025, 6.6019],
            "longitude": [-0.1870, -0.1865, -0.1868, -0.1872, -0.1867],
            "gps_accuracy": [4.5, 3.8, 4.2, 3.9, 4.1],
            "submissiondate": pd.date_range("2025-01-01", periods=5),
        }
    )


@pytest.fixture
def mock_streamlit():
    """Create a mock for streamlit functions."""
    mock_st = MagicMock()
    return mock_st


@pytest.fixture
def sample_gps_data():
    """Create a sample GPS dataset with known outliers."""
    # Normal points in a cluster
    normal_points = pd.DataFrame(
        {
            "latitude": [6.6018 + i * 0.0001 for i in range(10)],
            "longitude": [-0.1870 + i * 0.0001 for i in range(10)],
            "enumid": ["E001"] * 10,
            "gps_accuracy": [4.0] * 10,
            "submissiondate": pd.date_range("2025-01-01", periods=10),
        }
    )

    # Add outlier points
    outliers = pd.DataFrame(
        {
            "latitude": [6.7018, 6.5018],  # Significantly different locations
            "longitude": [-0.2870, -0.0870],
            "enumid": ["E001"] * 2,
            "gps_accuracy": [4.0] * 2,
            "submissiondate": pd.date_range("2025-01-11", periods=2),
        }
    )

    return pd.concat([normal_points, outliers], ignore_index=True)


@pytest.fixture
def mock_session_state():
    """Create a mock for streamlit session state."""

    class MockSessionState(dict):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            # Default configuration
            self["config_pages"] = {
                "data_loading": True,
                "data_processing": True,
                "gps_checks": True,
                "backchecks": True,
            }
            # Common state keys
            self["uploaded_file"] = None
            self["processed_data"] = None
            self["gps_results"] = None
            self["backcheck_results"] = None
            self["errors"] = []
            self["warnings"] = []

        def __getattr__(self, key):
            if key not in self:
                return None
            return self[key]

        def __setattr__(self, key, value):
            self[key] = value

    return MockSessionState()


@pytest.fixture
def mock_st(mock_session_state):
    """Create a comprehensive mock for streamlit with session state."""
    mock = MagicMock()
    mock.session_state = mock_session_state
    mock.write = MagicMock()
    mock.error = MagicMock()
    mock.warning = MagicMock()
    mock.success = MagicMock()
    mock.markdown = MagicMock()
    mock.dataframe = MagicMock()
    mock.file_uploader = MagicMock(return_value=None)
    mock.button = MagicMock(return_value=False)
    mock.selectbox = MagicMock(return_value=None)
    mock.checkbox = MagicMock(return_value=False)
    mock.number_input = MagicMock(return_value=0)
    mock.text_input = MagicMock(return_value="")
    return mock


@pytest.fixture
def sample_form_data():
    """Create sample form metadata for testing."""
    return {
        "title": "Test Survey Form",
        "version": "2025.1.1",
        "fields": [
            {"name": "survey_id", "type": "text"},
            {"name": "enumerator", "type": "select_one"},
            {"name": "gps", "type": "geopoint"},
            {"name": "consent", "type": "select_one"},
            {"name": "age", "type": "integer"},
            {"name": "income", "type": "decimal"},
            {"name": "education", "type": "select_one"},
        ],
    }
