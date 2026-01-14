import hashlib
import json
import os
import re
from functools import lru_cache
from pathlib import Path

import streamlit as st
from pydantic import BaseModel, Field, field_validator

from datasure.utils.config_utils import ConfigurationService

# Try to import toml for writing, use fallback if not available
try:
    import toml

    HAS_TOML = True
except ImportError:
    HAS_TOML = False
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib


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


def _write_toml_simple(data: dict, file_path: Path) -> None:
    """Write simple key-value pairs to TOML file.

    This is a fallback writer for when the toml library is not available.
    Only supports top-level string key-value pairs.

    Parameters
    ----------
    data : dict
        Dictionary of key-value pairs to write.
    file_path : Path
        Path to the TOML file.
    """
    with open(file_path, "w") as f:
        for key, value in data.items():
            # Escape quotes in value
            if isinstance(value, str):
                escaped_value = value.replace('"', '\\"')
                f.write(f'{key} = "{escaped_value}"\n')
            else:
                f.write(f"{key} = {value}\n")


def save_secrets(secret_name: str, secret_key: str) -> None:
    """Save a secret to the secrets.toml file.

    This function saves or updates a secret in the Streamlit secrets.toml file,
    making it accessible via st.secrets. The secrets file is located in the
    .streamlit directory.

    Parameters
    ----------
    secret_name : str
        The name/key of the secret to save.
    secret_key : str
        The value of the secret to save.

    Returns
    -------
    None

    Raises
    ------
    IOError
        If there's an error writing to the secrets file.

    Examples
    --------
    >>> save_secrets("mapbox_api_key", "pk.ey...")
    >>> # Now accessible via st.secrets["mapbox_api_key"]
    """
    if (
        "mapbox_custom_key" not in st.session_state
        or st.session_state["mapbox_custom_key"] is False
    ):
        return

    # Determine the secrets file path
    # Check if running in development (pyproject.toml exists) or production
    if Path("pyproject.toml").exists():
        # Development mode - use local .streamlit directory
        secrets_dir = Path(".streamlit")
    else:
        # Production mode - use Streamlit's default secrets location
        secrets_dir = Path.home() / ".streamlit"

    # Create .streamlit directory if it doesn't exist
    secrets_dir.mkdir(parents=True, exist_ok=True)

    secrets_file = secrets_dir / "secrets.toml"

    # Load existing secrets or create empty dict
    secrets_dict = {}
    if secrets_file.exists():
        if HAS_TOML:
            with open(secrets_file) as f:
                secrets_dict = toml.load(f)
        else:
            # Use tomllib for reading (Python 3.11+)
            with open(secrets_file, "rb") as f:
                secrets_dict = tomllib.load(f)

    # Update or add the secret
    secrets_dict[secret_name] = secret_key

    # Write back to secrets.toml
    if HAS_TOML:
        with open(secrets_file, "w") as f:
            toml.dump(secrets_dict, f)
    else:
        # Use simple fallback writer
        _write_toml_simple(secrets_dict, secrets_file)

    # Note: Streamlit will need to be restarted or the page reloaded
    # for st.secrets to pick up the new values
    st.rerun()
    st.session_state["mapbox_custom_key"] = False
