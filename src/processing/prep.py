import pandas as pd
import streamlit as st


def prep_load_log(index) -> pd.DataFrame:
    """Load existing log or return empty dataframe.

    PARAMS:
    -------
    return: pandas dataframe of logs
    """
    # load form details from last session
    try:
        file = pd.read_json(f"cache/pyDMS_prep_cache_{index}.json")
        logs = file.to_dict()
        return pd.DataFrame(logs)

    # if file not found, return empty dataframe
    except FileNotFoundError:
        return pd.DataFrame(columns=["action", "description"])


def prep_apply_action(
    action: str | None = None,
    description: str | None = None,
    index: int | None = None,
) -> None:
    """Update Log * Apply action in log to dataset.

    PARAMS:
    -------
    action: action to be logged
    description: description of action
    index: index for dataset and log

    return: None
    """
    if all([action, description]):
        # load existing logs
        logs = st.session_state[f"prep_log{index}"]

        # append new action
        new_log = pd.DataFrame(
            {"action": action, "description": description}, index=[0]
        )
        logs = pd.concat([logs, new_log], ignore_index=True)

        # save logs
        logs.to_json(f"cache/pyDMS_prep_cache_{index}.json")

        # update session state
        st.session_state[f"prep_log{index}"] = logs

    # loop through logs and apply actions to dataset
    for i in range(len(st.session_state[f"prep_log{index}"])):
        action = st.session_state[f"prep_log{index}"].iloc[i]["action"]
        description = st.session_state[f"prep_log{index}"].iloc[i]["description"]
