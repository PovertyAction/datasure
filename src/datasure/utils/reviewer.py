"""The reviewer identity recorded on every correction-log entry.

The reviewer defaults to the OS login. A "Reviewer name" set in the app
overrides it and is remembered across sessions in the user settings file.
A host can name the reviewer with the ``DATASURE_REVIEWER`` environment
variable, which wins over both and can't be changed in the app.
The setting holds a display name only, never credentials.
"""

import getpass
import json
import logging
import os
from pathlib import Path

import streamlit as st

from datasure.utils.cache_utils import get_cache_path

logger = logging.getLogger(__name__)

# Set by a host that already knows who the user is, such as a deployment
# with its own sign-in. It wins over the saved name and the OS login, and the
# app shows it without an input, so a correction can't be recorded under
# another name.
REVIEWER_ENV_VAR = "DATASURE_REVIEWER"

_REVIEWER_NAME_KEY = "reviewer_name"
_REVIEWER_NAME_WIDGET_KEY = "reviewer_name_input"


def _user_settings_path() -> Path:
    return get_cache_path("user_settings.json")


def _load_user_settings() -> dict:
    path = _user_settings_path()
    if not path.exists():
        return {}
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        logger.warning("Could not read user settings from %s", path)
        return {}
    return settings if isinstance(settings, dict) else {}


def _os_login() -> str:
    try:
        return getpass.getuser()
    # With no login environment variable set, getpass falls back to the
    # password database: KeyError when the uid has no entry, ImportError on
    # Windows before Python 3.13 (no pwd module), OSError from 3.13.
    except (OSError, KeyError, ImportError):
        logger.warning("Could not look up the OS login", exc_info=True)
        return ""


def get_reviewer_override() -> str:
    """Return the saved "Reviewer name", or "" if none is set."""
    name = _load_user_settings().get(_REVIEWER_NAME_KEY)
    return name.strip() if isinstance(name, str) else ""


def _host_reviewer() -> str:
    return os.environ.get(REVIEWER_ENV_VAR, "").strip()


def get_reviewer_name() -> str:
    """Return who is making corrections.

    The host's name (``REVIEWER_ENV_VAR``) if set, else the saved name, else
    the OS login.
    """
    return _host_reviewer() or get_reviewer_override() or _os_login()


def set_reviewer_name(name: str) -> None:
    """Save the "Reviewer name" override. A blank name clears it."""
    settings = _load_user_settings()
    name = name.strip()
    if name:
        settings[_REVIEWER_NAME_KEY] = name
    else:
        settings.pop(_REVIEWER_NAME_KEY, None)
    path = _user_settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(settings, indent=2), encoding="utf-8")


def _save_reviewer_name_input() -> None:
    try:
        set_reviewer_name(st.session_state.get(_REVIEWER_NAME_WIDGET_KEY, ""))
    except OSError:
        logger.exception("Could not save the reviewer name")
        st.error("Could not save the reviewer name. Check the cache folder.")


def render_reviewer_setting() -> None:
    """Render the "Reviewer name" setting, saved as soon as it changes.

    When the host names the reviewer, the name is shown and can't be edited.
    """
    host_reviewer = _host_reviewer()
    if host_reviewer:
        st.caption(f":material/person: Reviewer: {host_reviewer}")
        return
    with st.popover(
        f":material/person: Reviewer: {get_reviewer_name() or 'unknown'}",
        width="stretch",
    ):
        st.text_input(
            "Reviewer name",
            value=get_reviewer_override(),
            key=_REVIEWER_NAME_WIDGET_KEY,
            placeholder=_os_login(),
            help=(
                "Recorded as the user on every correction and acceptance you "
                "make. Leave blank to use your computer login."
            ),
            on_change=_save_reviewer_name_input,
        )
