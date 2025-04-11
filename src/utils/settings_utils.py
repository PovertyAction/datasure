import json
import os

import streamlit as st


@st.cache_data
def save_check_settings(settings_file, check_name, check_settings) -> None:
    """Save the settings for a check to a dictionary.

    Parameters
    ----------
    settings_dict (dict): The JSON fole to which the settings will be added.
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

    settings_dict[check_name] = check_settings

    with open(settings_file, "w") as f:
        json.dump(settings_dict, f)


@st.cache_data
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
    with open(settings_file) as f:
        settings_dict = json.load(f)

    return settings_dict.get(check_name)
