import hashlib
import json
import os
import re
from functools import lru_cache

import streamlit as st
from pydantic import BaseModel, Field, field_validator

from .duckdb_utils import duckdb_get_table


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


@st.cache_data
def save_check_settings(settings_file, check_name, check_settings) -> None:
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


# @st.cache_data
def load_check_settings(settings_file, check_name) -> tuple:
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
        return None
    with open(settings_file) as f:
        settings_dict = json.load(f)

    return settings_dict.get(check_name)


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
def get_check_config_settings(project_id: str, page_row_index: int) -> tuple:
    """Get the check configuration settings from DuckDB.

    Parameters
    ----------
    project_id (str): The ID of the project.
    page_row_index (int): The index of the row in the page.

    Returns
    -------
    tuple: The check configuration settings.
    """
    hfc_config_logs = duckdb_get_table(
        project_id=project_id, alias="check_config", db_name="logs"
    )

    page_name = hfc_config_logs.row(page_row_index)[0]
    survey_data_name = hfc_config_logs.row(page_row_index)[1]
    survey_key = hfc_config_logs.row(page_row_index)[2]
    survey_id = hfc_config_logs.row(page_row_index)[3]
    survey_date = hfc_config_logs.row(page_row_index)[4]
    enumerator = hfc_config_logs.row(page_row_index)[5]
    backcheck_data_name = hfc_config_logs.row(page_row_index)[6]
    tracking_data_name = hfc_config_logs.row(page_row_index)[7]

    return (
        page_name,
        survey_data_name,
        survey_key,
        survey_id,
        survey_date,
        enumerator,
        backcheck_data_name,
        tracking_data_name,
    )
