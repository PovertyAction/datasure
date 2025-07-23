import json
import sys
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Get the project root directory
project_root = Path(__file__).parent.parent

# Add the project root to Python path
sys.path.insert(0, str(project_root))


@pytest.fixture
def settings_file(tmp_path):
    """Create temporary settings file with standard configuration."""
    settings = {
        "enumerator": {
            "date": "submission_date",
            "enumerator": "enumerator",
            "team": "team",
            "duration": "duration",
            "consent": "consent",
            "consent_vals": ["Yes", "No"],
            "outcome": "outcome",
            "outcome_vals": ["Complete", "Refused"],
        }
    }

    # Create cache directory structure
    cache_dir = project_root / "cache"
    test_project_dir = cache_dir / "test_survey_project_1001"
    settings_dir = test_project_dir / "settings"

    # Create directories if they don't exist
    settings_dir.mkdir(parents=True, exist_ok=True)

    # Write settings file
    file_path = settings_dir / "settings.json"
    file_path.write_text(json.dumps(settings))
    return str(file_path)


@pytest.fixture
def sample_dataframe():
    """Create a sample dataframe for testing."""
    today = date.today()
    recent_date1 = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    recent_date2 = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    return pd.DataFrame(
        {
            "id": range(1, 6),
            "enumid": ["E001", "E002", "E001", "E003", "E002"],
            "latitude": [6.6018, 6.6015, 6.6022, 6.6025, 6.6019],
            "longitude": [-0.1870, -0.1865, -0.1868, -0.1872, -0.1867],
            "gps_accuracy": [4.5, 3.8, 4.2, 3.9, 4.1],
            "submission_date": [
                recent_date1,
                recent_date1,
                recent_date2,
                recent_date2,
                recent_date1,
            ],
            "team": ["T1", "T1", "T2", "T2", "T1"],
            "duration": [10, 15, 20, 25, 30],
            "consent": ["Yes", "Yes", "No", "Yes", "Yes"],
            "outcome": ["Complete", "Complete", "Refused", "Complete", "Complete"],
            "value1": [1, None, 3, 4, 5],
            "value2": [10, 20, None, 40, 50],
        }
    )


@pytest.fixture
def mock_streamlit_session():
    """Mock Streamlit session state for testing."""
    mock_config_pages = {
        "Survey Date": ["submission_date"],
        "Survey ID": ["survey_id"],
        "Enumerator": ["enumerator"],
        "st_project_id": ["test_survey_project_1001"],
        "data_loading": True,
        "data_processing": True,
        "gps_checks": True,
        "backchecks": True,
    }

    with patch("streamlit.session_state") as mock_session_state:
        mock_session_state.__getitem__.side_effect = lambda key: {
            "config_pages": mock_config_pages
        }[key]
        yield mock_session_state


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
def date_format_data():
    """Create datasets with different date formats for testing."""
    return {
        "iso_dates": pd.DataFrame(
            {
                "submission_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "enumerator": ["E1", "E1", "E2"],
                "team": ["T1", "T1", "T2"],
            }
        ),
        "datetime_obj": pd.DataFrame(
            {
                "submission_date": pd.date_range(start="2024-01-01", periods=3),
                "enumerator": ["E1", "E1", "E2"],
                "team": ["T1", "T1", "T2"],
            }
        ),
        "uk_format": pd.DataFrame(
            {
                "submission_date": ["01/01/2024", "02/01/2024", "03/01/2024"],
                "enumerator": ["E1", "E1", "E2"],
                "team": ["T1", "T1", "T2"],
            }
        ),
        "month_name": pd.DataFrame(
            {
                "submission_date": ["Jan 01, 2024", "Jan 02, 2024", "Jan 03, 2024"],
                "enumerator": ["E1", "E1", "E2"],
                "team": ["T1", "T1", "T2"],
            }
        ),
    }


@pytest.fixture
def missing_data():
    """Create dataset with various missing value patterns for testing."""
    return pd.DataFrame(
        {
            "submission_date": ["2024-01-01"] * 5,
            "enumerator": ["E1", "E1", "E2", "E2", "E2"],
            "team": ["T1", ".888", "T2", "-999", "T2"],
            "duration": [10, None, 20, -777, 30],
            "value1": [1, None, -999, 4, 0.888],
            "value2": [-777, 2, None, -999, 5],
        }
    )


@pytest.fixture
def productivity_data():
    """Create dataset for testing productivity metrics."""
    return pd.DataFrame(
        {
            "submission_date": pd.date_range("2024-01-01", periods=10),
            "enumerator": ["E1", "E1", "E2", "E2", "E1", "E2", "E1", "E2", "E1", "E2"],
            "team": ["T1", "T1", "T2", "T2", "T1", "T2", "T1", "T2", "T1", "T2"],
            "duration": range(10, 20),
            "errors": [0, 1, 0, 2, 1, 0, 1, 0, 2, 1],
        }
    )


@pytest.fixture
def missing_settings_file(tmp_path):
    """Create temporary settings file for missing data configuration."""
    settings = {
        "Missing Labels": ["Don't Know", "Refuse to Answer", "Not Applicable"],
        "Missing Codes": ["-999, .999", "-888, .888", "-777, .777"],
    }
    file_path = tmp_path / "missing_settings.json"
    file_path.write_text(json.dumps(settings))
    return str(file_path)


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


@pytest.fixture
def sample_date_data_10000():
    """Create a test dataset of 1000 observations for summary computation."""
    # Set random seeds for reproducibility
    seed = 42
    size = 100  # Reduced from 10000 for faster test execution

    # Generate datetime range
    start_date = pd.Timestamp.now() - pd.Timedelta(days=40)
    end_date = pd.Timestamp.now()

    # Generate random datetimes
    dates = pd.date_range(start=start_date, end=end_date, freq="h").to_list()
    dates = (
        pd.Series(dates)
        .sample(size, random_state=seed, replace=True)
        .dt.tz_localize(None)
    )

    # Create enumerator data
    enum_ids = list(range(1, 11))  # 10 enumerators
    enum_names = [
        "John Smith",
        "Mary Johnson",
        "David Williams",
        "Patricia Brown",
        "Robert Jones",
        "Linda Davis",
        "Michael Miller",
        "Sarah Wilson",
        "James Taylor",
        "Jennifer Anderson",
    ]

    # Create the dataset
    data = {
        "SubmissionDate": dates,
        "enum_id": [
            pd.Series(enum_ids).sample(1, random_state=seed).values[0]
            for _ in range(size)
        ],
    }

    df = pd.DataFrame(data)

    # Add enum_name based on enum_id
    df["enum_name"] = df["enum_id"].map(dict(zip(enum_ids, enum_names, strict=False)))

    return df


@pytest.fixture(autouse=True)
def cleanup_test_cache():
    """Clean up test cache directory after tests."""
    yield
    # Clean up after the test is done
    cache_dir = project_root / "cache"
    test_project_dir = cache_dir / "test_survey_project_1001"
    if test_project_dir.exists():
        import shutil

        shutil.rmtree(test_project_dir)


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Mock database functions to avoid needing actual database files during tests."""
    import polars as pl
    import streamlit as st

    def mock_duckdb_get_table(project_id, alias, db_name):
        """Mock duckdb_get_table to return a proper DataFrame with test data."""
        if alias == "check_config":
            # Return a DataFrame with the expected structure for check_config table
            return pl.DataFrame(
                {
                    "page_name": ["enumerator"],
                    "survey_data_name": ["test_survey"],
                    "form_title": ["Test Form"],
                    "survey_id": ["survey_id"],
                    "survey_date": ["submission_date"],
                    "enumerator_id": ["enumerator"],
                    "consent_col": ["consent"],
                    "outcome_col": ["outcome"],
                }
            )
        else:
            # Return empty DataFrame for other aliases
            return pl.DataFrame()

    def mock_config(*args, **kwargs):
        # Return mock values in the expected order:
        # formdef_version, project_name, form_title, survey_id,
        # survey_date, enumerator_id, consent_col, outcome_col
        return (
            "v1",  # formdef_version
            "Test Project",  # project_name
            "Test Form",  # form_title
            "survey_id",  # survey_id
            "submission_date",  # survey_date
            "enumerator",  # enumerator_id
            "consent",  # consent_col
            "outcome",  # outcome_col
        )

    # Clear streamlit cache to ensure our mocks are applied
    st.cache_data.clear()

    # Mock the duckdb_get_table function in all the places it might be imported
    monkeypatch.setattr(
        "datasure.utils.duckdb_utils.duckdb_get_table", mock_duckdb_get_table
    )
    monkeypatch.setattr("datasure.utils.duckdb_get_table", mock_duckdb_get_table)
    monkeypatch.setattr(
        "datasure.utils.settings_utils.duckdb_get_table", mock_duckdb_get_table
    )

    # Also directly patch the function used in settings_utils
    monkeypatch.setattr(
        "datasure.utils.settings_utils.get_check_config_settings", mock_config
    )
