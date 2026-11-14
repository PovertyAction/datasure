"""Default session state for the open project and the page handles.

``app.py`` sets these before building the navigation, and Exit Demo sets
them again so the next project starts from the same state as a new session.
"""

from collections.abc import Callable
from typing import Any

# Session state key -> factory for its default value.
APP_SESSION_DEFAULTS: dict[str, Callable[[], Any]] = {
    "st_project_id": str,
    "st_import_data_page": lambda: None,
    "st_prep_data_page": lambda: None,
    "st_output_page1": lambda: None,
    "st_config_checks_page": lambda: None,
    "st_output_pages": list,
    "st_corr_page": lambda: None,
    "st_replication_page": lambda: None,
}


def init_app_session_state() -> None:
    """Set every key in ``APP_SESSION_DEFAULTS`` that is not set yet."""
    # Imported here, as in ui_utils, to honor the tests' sys.modules swap.
    import streamlit as st

    for key, default in APP_SESSION_DEFAULTS.items():
        if key not in st.session_state:
            setattr(st.session_state, key, default())
