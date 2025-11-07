"""Pytest configuration for view tests."""

import sys
from unittest.mock import MagicMock, Mock

import pytest


class MockSessionState(dict):
    """Mock session state that supports both dict and attribute access."""

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError:
            # Return None for missing attributes instead of raising
            return None

    def __setattr__(self, name, value):
        self[name] = value


@pytest.fixture(scope="session", autouse=True)
def mock_streamlit_for_views():
    """Mock streamlit module for all view tests to prevent module-level
    execution issues.
    """
    # Create a comprehensive mock for streamlit
    st_mock = MagicMock()

    # Mock session_state as a dict-like object that supports attribute access
    st_mock.session_state = MockSessionState(
        {
            "st_project_id": None,
            "st_prep_data_page": None,
            "st_output_page1": None,
            "current_page": None,
        }
    )

    # Mock common streamlit functions
    st_mock.stop = Mock(
        side_effect=StopIteration
    )  # Use StopIteration instead of generic Exception
    st_mock.info = Mock()
    st_mock.warning = Mock()
    st_mock.error = Mock()
    st_mock.success = Mock()
    st_mock.title = Mock()
    st_mock.markdown = Mock()
    st_mock.subheader = Mock()
    st_mock.write = Mock()
    st_mock.columns = Mock(return_value=[Mock(), Mock(), Mock()])
    st_mock.button = Mock(return_value=False)
    st_mock.text_input = Mock(return_value="")
    st_mock.selectbox = Mock(return_value=None)
    st_mock.container = Mock()
    st_mock.popover = Mock()
    st_mock.dataframe = Mock()

    # Inject mock into sys.modules before any view imports
    sys.modules["streamlit"] = st_mock

    yield st_mock

    # Cleanup not necessary as it's session-scoped
