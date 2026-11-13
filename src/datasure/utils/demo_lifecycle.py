"""Restart and exit the demo project.

Restart deletes everything under ``cache/demoproject/`` (data, logs,
corrections, page settings and check configs) and loads the demo data again.
Exit Demo clears the demo's session state so the next project opens clean.
"""

import gc
import logging
import re
import shutil

import streamlit as st

from datasure.checks.health import clear_headline_cache
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.onboarding_utils import (
    DEMO_PROJECT_ID,
    create_demo_project,
    load_demo_data,
    set_onboarding_step,
    unregister_demo_project,
)
from datasure.utils.reviewer import _REVIEWER_NAME_WIDGET_KEY
from datasure.utils.session_defaults import init_app_session_state
from datasure.utils.ui_utils import _QUEUED_NOTICES_KEY

logger = logging.getLogger(__name__)

RESTART_DEMO_MESSAGE = (
    "Restarting deletes everything in the demo project: imported and "
    "prepared data, data preparation steps, corrections, check pages and "
    "their settings. The demo data is then loaded again and the demo starts "
    "from the beginning. This cannot be undone."
)

DEMO_RESET_FAILED_MESSAGE = (
    "Failed to reset the demo. Close any other DataSure windows and try again."
)

# `queue_notice` scope of the Start page demo row's messages. A failed reset
# leaves the demo, so both Restart actions show their error there.
DEMO_NOTICE_SCOPE = "start_demo"

# Session state that is not the demo's: the page handles app.py builds on
# every run (callers still switch page with them), the reviewer name and
# messages queued for the next run. Every other key is cleared, so state a
# view adds later is cleared too without being listed here.
_APP_WIDE_KEYS = frozenset(
    {
        "st_start_page",
        "st_import_data_page",
        "st_prep_data_page",
        "st_config_checks_page",
        _REVIEWER_NAME_WIDGET_KEY,
        _QUEUED_NOTICES_KEY,
    }
)

# A key ``project_nav_key`` built for another project, which is kept:
# "<name>__<project id>[__<suffix>]", where the ID is 8 hex characters
# (``start_view.get_project_id``). A demo page name can also hold 8 hex
# characters (e.g. "HFC - 20251026"), so demo keys are checked for first.
_OTHER_PROJECT_KEY = re.compile(r"__[0-9a-f]{8}(?:__|$)")
_DEMO_KEY_PART = f"__{DEMO_PROJECT_ID}"


def _is_other_project_key(key: str) -> bool:
    """Return True if ``key`` is another project's navigation key."""
    return _DEMO_KEY_PART not in key and bool(_OTHER_PROJECT_KEY.search(key))


def _clear_demo_session_state() -> None:
    """Clear the demo's session state back to a new session's defaults.

    App-wide keys and other projects' navigation keys are kept.
    """
    state = st.session_state
    for key in list(state):
        if key in _APP_WIDE_KEYS or _is_other_project_key(str(key)):
            continue
        state.pop(key, None)
    init_app_session_state()


def _clear_cached_results() -> None:
    """Clear every ``st.cache_data`` result and the check headline cache.

    This clears the whole app's cache, not only the demo's: ``st.cache_data``
    can be cleared per function or all at once but not per project, and the
    demo's results are spread over many cached functions. Other projects'
    results are recomputed the next time they are needed.
    """
    st.cache_data.clear()
    clear_headline_cache()


def _delete_demo_folder() -> None:
    """Delete ``cache/demoproject/``.

    Raises
    ------
    OSError
        If the folder cannot be deleted, for example because another DataSure
        window still has one of its DuckDB files open.
    """
    # Release any DuckDB connection still waiting to be garbage collected,
    # which on Windows keeps its file locked.
    gc.collect()
    project_path = get_cache_path(DEMO_PROJECT_ID)
    if project_path.exists():
        shutil.rmtree(project_path)


def _abandon_demo() -> None:
    """Leave a demo that could not be rebuilt and stop offering Resume.

    The folder may be partly deleted or loaded, so the demo is removed from
    ``projects.json`` and the Start page offers only Start Demo.
    """
    unregister_demo_project()
    exit_demo()


def reset_demo_project() -> bool:
    """Delete the demo project and rebuild it from the demo data.

    Shared by every Restart action. Clears the demo's session state and the
    app's cached results, deletes everything under ``cache/demoproject/``,
    registers the demo project again,
    loads the demo data and makes the demo the active project at step 2.

    On failure the demo is unregistered and left, so the caller shows the
    error on the Start page (``DEMO_NOTICE_SCOPE``).

    Returns
    -------
    bool
        True if the demo was rebuilt, False if the folder could not be
        deleted or the demo data could not be loaded.
    """
    _clear_demo_session_state()
    # Cached results would show the old demo's corrections and checks.
    _clear_cached_results()
    try:
        _delete_demo_folder()
    except OSError:
        logger.exception("Could not delete the demo project folder")
        _abandon_demo()
        return False

    project_id = create_demo_project()
    st.session_state.st_project_id = project_id
    set_onboarding_step(1)
    if not load_demo_data():
        _abandon_demo()
        return False
    set_onboarding_step(2)
    return True


def exit_demo() -> None:
    """Leave the demo and clear its session state.

    Other projects' session state is kept. The caller navigates away.
    """
    _clear_demo_session_state()
    st.session_state.st_project_id = ""
