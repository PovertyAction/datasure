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

# Save the original streamlit module so we can restore it for non-view tests.
# Replacing sys.modules["streamlit"] globally would break @st.cache_data,
# @st.fragment, and other decorators in non-view source files.
_original_streamlit = sys.modules.get("streamlit")

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

# Inject mock into sys.modules at module level for collection-time availability.
# This is needed so that view modules (e.g. prep_view.py) can be imported
# during test collection without requiring a running Streamlit runtime.
sys.modules["streamlit"] = _st_mock


@pytest.fixture(autouse=True)
def _use_mock_streamlit():
    """Swap in mock streamlit for each view test, restore after.

    Also resets session_state to MockSessionState to prevent corruption
    from tests that replace session_state with a plain dict.
    """
    # Install the mock for this view test
    sys.modules["streamlit"] = _st_mock

    # Reset session state
    _st_mock.session_state = MockSessionState(
        {
            "st_project_id": None,
            "st_prep_data_page": None,
            "st_output_page1": None,
            "current_page": None,
        }
    )

    yield _st_mock

    # Restore real streamlit after the view test
    if _original_streamlit is not None:
        sys.modules["streamlit"] = _original_streamlit
