"""Shared fixtures for the split enumerator module test suite."""

import json
from datetime import date, timedelta
from unittest.mock import MagicMock

import polars as pl
import pytest

from datasure.checks.enumerator.models import EnumeratorSettings

# ============================================
# MOCK STREAMLIT HELPERS
# ============================================


def make_mock_st():
    """Create a mock Streamlit module for testing UI render functions."""

    def make_col():
        col = MagicMock()
        col.number_input.return_value = 0.0
        col.selectbox.return_value = None
        col.text_input.return_value = ""
        col.multiselect.return_value = []
        return col

    def _col_factory(n_or_spec, **kwargs):
        if isinstance(n_or_spec, int):
            n = n_or_spec
        elif isinstance(n_or_spec, list | tuple):
            n = len(n_or_spec)
        else:
            n = 2
        return tuple(make_col() for _ in range(n))

    mock_st = MagicMock()
    mock_st.fragment = lambda func: func
    mock_st.dialog = lambda *args, **kwargs: lambda func: func
    mock_st.columns.side_effect = _col_factory
    mock_st.selectbox.return_value = None
    mock_st.multiselect.return_value = []
    mock_st.pills.return_value = None
    mock_st.button.return_value = False
    mock_st.toggle.return_value = False
    mock_st.number_input.return_value = 0
    mock_st.text_input.return_value = ""
    mock_st.session_state = {}
    return mock_st


# ============================================
# FIXTURES FOR ENUMERATOR-SPECIFIC DATA
# ============================================


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests.
    """
    pass


@pytest.fixture
def sample_enumerator_data():
    """Create sample enumerator data as Polars DataFrame."""
    today = date.today()
    return pl.DataFrame(
        {
            "survey_id": ["S001", "S002", "S003", "S004", "S005", "S006"],
            "submission_date": [
                today - timedelta(days=1),
                today - timedelta(days=2),
                today - timedelta(days=3),
                today - timedelta(days=1),
                today - timedelta(days=8),
                today,
            ],
            "enumerator": ["E1", "E1", "E2", "E2", "E3", "E1"],
            "team": ["T1", "T1", "T1", "T2", "T2", "T1"],
            "duration": [3600, 4200, 3800, 4000, 3900, 3700],
            "formversion": ["v1", "v1", "v2", "v2", "v1", "v2"],
            "age": [25, 30, 35, 28, 32, 27],
            "income": [50000, 60000, 55000, 52000, 58000, 51000],
            "consent_granted_agg_col": [1, 1, 1, 0, 1, 1],
            "completed_survey_agg_col": [1, 1, 1, 1, 0, 1],
        }
    )


@pytest.fixture
def sample_enumerator_settings():
    """Create sample EnumeratorSettings for testing."""
    return EnumeratorSettings(
        survey_key="survey_id",
        survey_id="survey_id",
        survey_date="submission_date",
        enumerator="enumerator",
        formversion="formversion",
        duration="duration",
        duration_unit="seconds",
        team="team",
    )


@pytest.fixture
def sample_missing_codes_config():
    """Create sample missing codes configuration."""
    return pl.DataFrame(
        {
            "label": ["Refused", "Don't know"],
            "codes": ["-99", "-88"],
        }
    )


@pytest.fixture
def enumerator_settings_file(tmp_path):
    """Create a temporary enumerator settings file."""
    settings = {
        "enumerators": {
            "survey_key": "survey_id",
            "survey_id": "survey_id",
            "survey_date": "submission_date",
            "enumerator": "enumerator",
            "team": "team",
        }
    }
    file_path = tmp_path / "enumerator_settings.json"
    file_path.write_text(json.dumps(settings))
    return str(file_path)
