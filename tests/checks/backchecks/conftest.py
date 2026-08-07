"""Shared fixtures for the split backchecks module test suite."""

import json
from datetime import date
from unittest.mock import MagicMock

import polars as pl
import pytest

from datasure.checks.backchecks.models import BackcheckSettings

# ============================================
# MOCK STREAMLIT HELPERS
# ============================================


def make_mock_st():
    """Create a MagicMock configured for Streamlit UI testing."""

    def make_col():
        col = MagicMock()
        col.number_input.return_value = 0.0
        col.selectbox.return_value = None
        col.text_input.return_value = ""
        return col

    def mock_columns(n_or_spec):
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
    mock_st.columns = mock_columns
    mock_st.selectbox.return_value = None
    mock_st.multiselect.return_value = []
    mock_st.pills.return_value = None
    mock_st.button.return_value = False
    mock_st.toggle.return_value = False
    mock_st.number_input.return_value = 0
    mock_st.text_input.return_value = ""
    return mock_st


# ============================================
# FIXTURES FOR BACKCHECK-SPECIFIC DATA
# ============================================


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest to disable database
    mocking for these tests.
    """
    # These tests don't use database functions, so we don't need to mock them
    pass


@pytest.fixture
def sample_backcheck_settings():
    """Create sample BackcheckSettings for testing."""
    return BackcheckSettings(
        survey_key="survey_id",
        survey_id="survey_id",
        survey_date="submission_date",
        backcheck_date="backcheck_date",
        enumerator="enumerator",
        backchecker="backchecker",
        backcheck_target_percent=10,
        drop_duplicates_option="drop",
        no_differences_list=["refuse", "dk"],
        exclude_values_list=["na", "skip"],
        case_option="lowercase",
        trimspaces_option=True,
        nosymbols_option=False,
    )


@pytest.fixture
def sample_survey_data_pl():
    """Create sample survey data as Polars DataFrame."""
    return pl.DataFrame(
        {
            "survey_id": ["S001", "S002", "S003", "S004", "S005"],
            "submission_date": [
                date(2024, 1, 1),
                date(2024, 1, 2),
                date(2024, 1, 3),
                date(2024, 1, 4),
                date(2024, 1, 5),
            ],
            "enumerator": ["E1", "E1", "E2", "E2", "E3"],
            "age": [25, 30, 35, 28, 32],
            "income": [50000, 60000, 55000, 52000, 58000],
            "gender": ["M", "F", "M", "F", "M"],
            "education": [
                "High School",
                "College",
                "High School",
                "College",
                "Graduate",
            ],
        }
    )


@pytest.fixture
def sample_backcheck_data_pl():
    """Create sample backcheck data as Polars DataFrame."""
    return pl.DataFrame(
        {
            "survey_id": ["S001", "S002", "S003"],
            "backcheck_date": [
                date(2024, 1, 5),
                date(2024, 1, 6),
                date(2024, 1, 7),
            ],
            "backchecker": ["B1", "B1", "B2"],
            "age": [25, 31, 35],  # One mismatch (S002)
            "income": [50000, 60000, 56000],  # One mismatch (S003)
            "gender": ["M", "F", "M"],
            "education": ["High School", "College", "High School"],
        }
    )


@pytest.fixture
def sample_backcheck_column_settings_pl():
    """Create sample column settings as Polars DataFrame."""
    return pl.DataFrame(
        {
            "search_type": ["exact", "exact", "exact"],
            "pattern": ["age", "income", "gender"],
            "column_name": [["age"], ["income"], ["gender"]],
            "category": [1, 2, 3],
            "ok_range_type": ["number", "percentage", None],
            "ok_range_values": [[-2.0, 2.0], [-10.0, 10.0], None],
            "ttest": [False, False, False],
            "prtest": [False, False, False],
            "signrank": [False, False, False],
            "reliability": [False, False, False],
        }
    )


@pytest.fixture
def backcheck_settings_file(tmp_path):
    """Create a temporary backcheck settings file."""
    settings = {
        "backchecks": {
            "survey_key": "survey_id",
            "survey_id": "survey_id",
            "survey_date": "submission_date",
            "backcheck_date": "backcheck_date",
            "enumerator": "enumerator",
            "backchecker": "backchecker",
            "backcheck_target_percent": 10,
            "drop_duplicates_option": "drop",
        }
    }
    file_path = tmp_path / "backcheck_settings.json"
    file_path.write_text(json.dumps(settings))
    return str(file_path)
