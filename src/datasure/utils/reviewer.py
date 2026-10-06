"""The reviewer identity recorded on every correction-log entry.

The reviewer defaults to the OS login. A "Reviewer name" set in the app
overrides it and is remembered across sessions in the user settings file.
The setting holds a display name only, never credentials.
"""

import getpass
import json
import logging
from pathlib import Path

import streamlit as st

from datasure.utils.cache_utils import get_cache_path

logger = logging.getLogger(__name__)

_REVIEWER_NAME_KEY = "reviewer_name"


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
    except Exception:  # getpass raises OSError, or KeyError on some platforms
        return ""


def get_reviewer_override() -> str:
    """Return the saved "Reviewer name", or "" if none is set."""
    name = _load_user_settings().get(_REVIEWER_NAME_KEY)
    return name.strip() if isinstance(name, str) else ""


def get_reviewer_name() -> str:
    """Return who is making corrections: the saved name, else the OS login."""
    return get_reviewer_override() or _os_login()


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
    set_reviewer_name(st.session_state.get("reviewer_name_input", ""))


def render_reviewer_setting() -> None:
    """Render the "Reviewer name" setting, saved as soon as it changes."""
    with st.popover(
        f":material/person: Reviewer: {get_reviewer_name() or 'unknown'}",
        width="stretch",
    ):
        st.text_input(
            "Reviewer name",
            value=get_reviewer_override(),
            key="reviewer_name_input",
            placeholder=_os_login(),
            help=(
                "Recorded as the user on every correction and acceptance you "
                "make. Leave blank to use your computer login."
            ),
            on_change=_save_reviewer_name_input,
        )
