import re

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

    st.session_state[f"prepped_data{index}"] = st.session_state[
        f"raw_data_prep{index}"
    ].copy()

    # loop through logs and apply actions to dataset
    for i in range(len(st.session_state[f"prep_log{index}"])):
        action = st.session_state[f"prep_log{index}"].iloc[i]["action"]
        description = st.session_state[f"prep_log{index}"].iloc[i]["description"]

        if action == "delete column(s)":
            prep_delete_columns(index, description)

        elif "delete row(s)" in description:
            prep_delete_rows(index, description)


# function to delete columns from dataset
def prep_delete_columns(index: int, description: str):
    """Delete columns from dataset.

    PARAMS:
    -------
    index: index for dataset and log
    action: action to be logged
    description: description of action

    return: None
    """
    # get column names from description
    columns = description.replace("delete column(s) ", "")
    columns = eval(columns)

    # drop columns from dataset
    st.session_state[f"prepped_data{index}"].drop(columns=columns, axis=1, inplace=True)


# function to delete rows
def prep_delete_rows(index: int, description: str):
    """Delete rows from dataset.

    PARAMS:
    -------
    index: index for dataset and log
    action: action to be logged
    description: description of action

    return: None
    """
    # get row indexes from description
    if "delete row(s) by index" in description:
        rows = description.replace("delete row(s) by index", "")
        rows = eval(rows)

        # drop rows from dataset
        st.session_state[f"prepped_data{index}"].drop(index=rows, inplace=True)

    if "delete row(s) by condition" in description:
        condition = re.search(r"'[a-z ]+'", description).group(0).replace("'", "")
        cols = re.search(r"\[.*?\]", description).group(0)

        if condition == "value is missing":
            # drop rows from dataset if any value in cols is missing
            st.session_state[f"prepped_data{index}"].dropna(
                subset=eval(cols), inplace=True
            )
        elif condition == "value is not missing":
            drop_index = st.session_state[f"prepped_data{index}"].dropna(
                subset=eval(cols)
            )
            if drop_index is not None:
                drop_index = list(drop_index.index)
                st.session_state[f"prepped_data{index}"].drop(
                    index=drop_index, inplace=True
                )
        elif condition in ["value is equal to", "value is not equal to"]:
            values = (
                re.search(r"with value.+", description)
                .group(0)
                .replace("with value ", "")
                .replace("'", "")
            )
            values = values.split(",")
            values_use = []
            for value in values:
                if value.isdigit():
                    values_use.append(int(value))
                else:
                    values_use.append(value)

            cols = eval(cols)[0]
            if condition == "value is equal to":
                st.session_state[f"prepped_data{index}"].query(
                    f"{cols} not in {values_use}", inplace=True
                )
            else:
                st.session_state[f"prepped_data{index}"].query(
                    f"{cols} in {values_use}", inplace=True
                )
