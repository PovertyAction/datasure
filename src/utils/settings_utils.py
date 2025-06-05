import json
import os

import streamlit as st


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
