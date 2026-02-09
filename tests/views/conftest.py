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


# === Module-level streamlit mock setup ===
# This MUST happen at module level (not in a fixture) so that it's available
# during test collection when test modules with module-level imports are loaded.

_st_mock = MagicMock()

_st_mock.session_state = MockSessionState(
    {
        "st_project_id": None,
        "st_prep_data_page": None,
        "st_output_page1": None,
        "current_page": None,
    }
)

# Mock common streamlit functions
_st_mock.stop = Mock(side_effect=StopIteration)
_st_mock.info = Mock()
_st_mock.warning = Mock()
_st_mock.error = Mock()
_st_mock.success = Mock()
_st_mock.title = Mock()
_st_mock.markdown = Mock()
_st_mock.subheader = Mock()
_st_mock.write = Mock()
_st_mock.columns = Mock(return_value=[Mock(), Mock(), Mock()])
_st_mock.button = Mock(return_value=False)
_st_mock.text_input = Mock(return_value="")
_st_mock.selectbox = Mock(return_value=None)
_st_mock.multiselect = Mock(return_value=[])
_st_mock.container = Mock()
_st_mock.popover = Mock()
_st_mock.dataframe = Mock()
_st_mock.number_input = Mock(return_value=None)
_st_mock.tabs = Mock(return_value=[Mock()])

# Inject mock into sys.modules at module level for collection-time availability
sys.modules["streamlit"] = _st_mock


@pytest.fixture(scope="session", autouse=True)
def mock_streamlit_for_views():
    """Provide the streamlit mock to tests (already set up at module level)."""
    yield _st_mock
