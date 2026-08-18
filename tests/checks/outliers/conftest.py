"""Shared fixtures for the split outliers module test suite."""

from unittest.mock import MagicMock

import pandas as pd
import polars as pl
import pytest

from datasure.checks.outliers.models import OutlierSettings

# ============================================================================
# MOCK STREAMLIT HELPERS
# ============================================================================


def _columns_side_effect(*args, **kwargs):
    """Return a list of MagicMocks whose length matches the columns argument."""
    n = args[0] if args else 1
    count = len(n) if isinstance(n, list | tuple) else int(n)
    return [MagicMock() for _ in range(count)]


def _make_st_mock():
    """Create a MagicMock for streamlit with sensible defaults.

    Configures ``columns`` (matches the requested column count),
    ``cache_data`` (identity passthrough, with or without kwargs), and
    ``dialog`` (identity passthrough) so modules decorated with
    ``@st.cache_data``/``@st.dialog`` can be reloaded against this mock
    without their decorated behavior changing.
    """
    st_mock = MagicMock()
    st_mock.columns.side_effect = _columns_side_effect

    def _mock_cache_data(func=None, **kwargs):
        if callable(func):
            return func
        return lambda f: f

    st_mock.cache_data = _mock_cache_data
    st_mock.dialog = lambda *args, **kwargs: lambda f: f
    return st_mock


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests.
    """
    pass


@pytest.fixture
def sample_polars_df():
    """Create a sample Polars DataFrame for testing."""
    from datetime import date

    return pl.DataFrame(
        {
            "survey_key": ["K001", "K002", "K003", "K004", "K005"],
            "survey_id": ["S001", "S002", "S003", "S004", "S005"],
            "enumerator": ["E001", "E002", "E001", "E003", "E002"],
            "team": ["T1", "T2", "T1", "T3", "T2"],
            "survey_date": [date(2024, 1, i) for i in range(1, 6)],
            "numeric_col1": [1.0, 2.0, 3.0, 100.0, 5.0],  # outlier: 100.0
            "numeric_col2": [10.0, 20.0, 30.0, 40.0, 500.0],  # outlier: 500.0
            "string_col": ["A", "B", "C", "D", "E"],
        }
    )


@pytest.fixture
def sample_pandas_df():
    """Create a sample pandas DataFrame for testing."""
    return pd.DataFrame(
        {
            "survey_key": ["K001", "K002", "K003", "K004", "K005"],
            "survey_id": ["S001", "S002", "S003", "S004", "S005"],
            "enumerator": ["E001", "E002", "E001", "E003", "E002"],
            "numeric_col1": [1.0, 2.0, 3.0, 100.0, 5.0],
            "numeric_col2": [10.0, 20.0, 30.0, 40.0, 500.0],
        }
    )


@pytest.fixture
def outlier_column_config():
    """Create sample outlier column configuration."""
    return pl.DataFrame(
        {
            "search_type": ["exact"],
            "pattern": [None],
            "column_name": [["numeric_col1"]],
            "grouped_columns": [False],
            "locked": [False],
            "outlier_enabled": [True],
            "outlier_method": ["Interquartile Range (IQR)"],
            "outlier_multiplier": [1.5],
            "outlier_threshold": [3],
            "hard_min": [None],
            "soft_min": [0.0],
            "soft_max": [50.0],
            "hard_max": [None],
        }
    )


@pytest.fixture
def outlier_settings():
    """Create sample outlier settings."""
    return OutlierSettings(
        survey_key="survey_key",
        survey_id="survey_id",
        survey_date="survey_date",
        enumerator="enumerator",
        team="team",
    )
