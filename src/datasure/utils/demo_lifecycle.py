"""Restart and exit the demo project.

Restart deletes everything under ``cache/demoproject/`` (data, logs,
corrections, page settings and check configs) and loads the demo data again.
Exit Demo clears the demo's session state so the next project opens clean.
"""

import gc
import logging
import shutil

import streamlit as st

from datasure.checks.health import clear_headline_cache
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.onboarding_utils import (
    DEMO_PROJECT_ID,
    create_demo_project,
    load_demo_data,
    set_onboarding_step,
)

logger = logging.getLogger(__name__)

RESTART_DEMO_MESSAGE = (
    "Restarting deletes everything in the demo project: imported and "
    "prepared data, data preparation steps, corrections, check pages and "
    "their settings. The demo data is then loaded again and the demo starts "
    "from the beginning. This cannot be undone."
)

# Session state keys set while a project is open, removed when the demo ends.
_PROJECT_SESSION_KEYS = (
    "onboarding_step",
    "_sidebar_confirm_restart",
    "st_raw_dataset_list",
    "st_prep_dataset_list",
)

# Page handles app.py builds for the open project, with app.py's defaults.
_PAGE_HANDLE_DEFAULTS = {
    "st_output_pages": list,
    "st_output_page1": lambda: None,
    "st_corr_page": lambda: None,
    "st_replication_page": lambda: None,
}


def _clear_demo_session_state() -> None:
    """Remove the demo's session state, keeping app-wide page handles."""
    state = st.session_state
    for key in _PROJECT_SESSION_KEYS:
        state.pop(key, None)
    # Navigation and view-state keys include the project ID.
    for key in [k for k in state if DEMO_PROJECT_ID in str(k)]:
        state.pop(key, None)
    for key, default in _PAGE_HANDLE_DEFAULTS.items():
        state[key] = default()


def _delete_demo_cache() -> None:
    """Delete ``cache/demoproject/`` and every cached result computed from it.

    Raises
    ------
    OSError
        If the folder cannot be deleted, for example because another DataSure
        window still has one of its DuckDB files open.
    """
    # Cached results would show the old demo's corrections and checks.
    st.cache_data.clear()
    clear_headline_cache()
    # Release any DuckDB connection still waiting to be garbage collected,
    # which on Windows keeps its file locked.
    gc.collect()
    project_path = get_cache_path(DEMO_PROJECT_ID)
    if project_path.exists():
        shutil.rmtree(project_path)


def reset_demo_project() -> bool:
    """Delete the demo project and rebuild it from the demo data.

    Shared by every Restart action. Clears the demo's session state, deletes
    everything under ``cache/demoproject/``, registers the demo project again,
    loads the demo data and makes the demo the active project at step 2.

    Returns
    -------
    bool
        True if the demo was rebuilt, False if the folder could not be
        deleted or the demo data could not be loaded.
    """
    _clear_demo_session_state()
    try:
        _delete_demo_cache()
    except OSError:
        logger.exception("Could not delete the demo project folder")
        return False

    project_id = create_demo_project()
    st.session_state.st_project_id = project_id
    set_onboarding_step(1)
    if not load_demo_data():
        return False
    set_onboarding_step(2)
    return True


def exit_demo() -> None:
    """Leave the demo and clear its session state.

    Other projects' session state is kept. The caller navigates away.
    """
    _clear_demo_session_state()
    st.session_state.st_project_id = ""
