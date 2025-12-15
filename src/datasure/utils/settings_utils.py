import hashlib
import json
import os
import re
from functools import lru_cache

import streamlit as st
from pydantic import BaseModel, Field, field_validator

from datasure.utils.config_utils import ConfigurationService


class ProjectID(BaseModel):
    """Model for project ID with validation."""

    project_id: str = Field(..., min_length=8, max_length=8)

    @field_validator("project_id")
    def validate_project_id(cls, v):
        """Validate project ID format."""
        if not re.fullmatch(r"^[a-z0-9]{8}$", v):
            raise ValueError(
                "Project ID must be alphanumeric only and exactly 8 characters long"
            )
        return v


def save_check_settings(
    settings_file: str, check_name: str, check_settings: dict
) -> None:
    """Save the settings for a check to a dictionary.

    Parameters
    ----------
    settings_dict (dict): The JSON file to which the settings will be added.
    check_name (str): The name of the check.
        The name of the check for which the settings will be saved.
    check_settings (dict): The settings for the check.
        The settings to save for the check.

    Returns
    -------
    None

    """
    dict_key = check_settings.keys().__iter__().__next__()  # get the first key
    state_name = check_name + "_" + dict_key
    if state_name not in st.session_state or not st.session_state[state_name]:
        return

    if not os.path.exists(settings_file):
        with open(settings_file, "w") as f:
            json.dump({}, f)

    with open(settings_file) as f:
        settings_dict = json.load(f)

    if check_name in settings_dict:
        settings_dict[check_name].update(check_settings)
    else:
        settings_dict[check_name] = check_settings

    # save the dictionary to the file
    with open(settings_file, "w") as f:
        json.dump(settings_dict, f)

    st.session_state[state_name] = False


def load_check_settings(settings_file, check_name) -> dict:
    """Load the settings for a check from a dictionary.

    Parameters
    ----------
    settings_dict (dict): The JSON file from which the settings will be loaded.
    check_name (str): The name of the check.
        The name of the check for which the settings will be loaded.

    Returns
    -------
    tuple: The settings for the check.

    """
    # check if the file exists
    if not os.path.exists(settings_file):
        return {}
    with open(settings_file) as f:
        settings_dict = json.load(f)

    return settings_dict.get(check_name, {})


def trigger_save(state_name: str):
    """Return a session state of True when triggered by the user."""
    st.session_state[state_name] = True


# --- Get shortened ID for text --- #
@lru_cache
def get_hash_id(name: str, length=6) -> str:
    """Generate a unique ID (maybe) for project.
    This ID will be used as project IDs (6 digits) and dataset IDs 8 digits
    """
    hash_val = hashlib.sha256(name.encode()).hexdigest()
    return hash_val[:length]


# --- Get Check Config Settings from DuckDB --- #
def get_check_config_settings(project_id: str, page_row_index: int) -> dict:
    """Get the check configuration settings from DuckDB.

    Parameters
    ----------
    project_id (str): The ID of the project.
    page_row_index (int): The index of the row in the page.

    Returns
    -------
    tuple: The check configuration settings.
    """
    hfc_config_logs = ConfigurationService(project_id).get_page_configuration(
        page_row_index
    )

    return hfc_config_logs if hfc_config_logs else {}
