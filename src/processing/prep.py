import re

import numpy as np
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

        if action == "remove column(s)":
            prep_remove_columns(index, description)
        elif "remove row(s)" in description:
            prep_remove_rows(index, description)
        elif action == "transform column(s)":
            prep_transform_columns(index, description)


# function to remove columns from dataset
def prep_remove_columns(index: int, description: str):
    """Remove columns from dataset.

    PARAMS:
    -------
    index: index for dataset and log
    action: action to be logged
    description: description of action

    return: None
    """
    # get column names from description
    columns = description.replace("remove column(s) ", "")
    columns = eval(columns)

    # drop columns from dataset
    st.session_state[f"prepped_data{index}"].drop(columns=columns, axis=1, inplace=True)


# function to remove rows
def prep_remove_rows(index: int, description: str):
    """Remove rows from dataset.

    PARAMS:
    -------
    index: index for dataset and log
    action: action to be logged
    description: description of action

    return: None
    """
    # get row indexes from description
    if "remove row(s) by index" in description:
        rows = description.replace("remove row(s) by index", "")
        rows = eval(rows)

        # drop rows from dataset
        st.session_state[f"prepped_data{index}"].drop(index=rows, inplace=True)

    if "remove row(s) by condition" in description:
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
            )

            values_use = eval(values)
            cols = eval(cols)[0]
            if condition == "value is equal to":
                st.session_state[f"prepped_data{index}"].query(
                    f"{cols} not in {values_use}", inplace=True
                )
            else:
                st.session_state[f"prepped_data{index}"].query(
                    f"{cols} in {values_use}", inplace=True
                )
        elif condition in [
            "value is greater than",
            "value is greater than or equal to",
            "value is less than",
            "" "value is less than or equal to",
        ]:
            value = (
                re.search(r"with value.+", description)
                .group(0)
                .replace("with value ", "")
                .replace("'", "")
            )
            value = int(value)
            cols = eval(cols)[0]
            if condition == "value is greater than":
                st.session_state[f"prepped_data{index}"] = st.session_state[
                    f"prepped_data{index}"
                ].query(f"{cols} <= {value}")
            elif condition == "value is greater than or equal to":
                st.session_state[f"prepped_data{index}"] = st.session_state[
                    f"prepped_data{index}"
                ].query(f"{cols} < {value}")
            elif condition == "value is less than":
                st.session_state[f"prepped_data{index}"] = st.session_state[
                    f"prepped_data{index}"
                ].query(f"{cols} >= {value}")
            elif condition == "value is less than or equal to":
                st.session_state[f"prepped_data{index}"] = st.session_state[
                    f"prepped_data{index}"
                ].query(f"{cols} > {value}")
        elif condition in ["value is between", "value is not between"]:
            values = (
                re.search(r"with values.+", description)
                .group(0)
                .replace("with values ", "")
                .replace("'", "")
            )
            values = values.split(" and ")
            values_use = []
            for value in values:
                if value.isdigit():
                    values_use.append(int(value))
                else:
                    values_use.append(value)

            cols = eval(cols)[0]
            if condition == "value is between":
                st.session_state[f"prepped_data{index}"] = st.session_state[
                    f"prepped_data{index}"
                ].query(f"{cols} < {values_use[0]} or {cols} > {values_use[1]}")
            else:
                st.session_state[f"prepped_data{index}"] = st.session_state[
                    f"prepped_data{index}"
                ].query(f"{cols} >= {values_use[0]} and {cols} <= {values_use[1]}")
        elif condition in ["value is like", "value is not like"]:
            value = (
                re.search(r"with pattern.+", description)
                .group(0)
                .replace("with pattern ", "")
                .replace("'", "")
            )
            cols = eval(cols)[0]
            if condition == "value is like":
                st.session_state[f"prepped_data{index}"] = st.session_state[
                    f"prepped_data{index}"
                ].query(f"not {cols}.str.contains('{value}')", engine="python")
            else:
                st.session_state[f"prepped_data{index}"] = st.session_state[
                    f"prepped_data{index}"
                ].query(f"{cols}.str.contains('{value}')", engine="python")


# function to transform columns
def prep_transform_columns(index: int, description: str):
    """Transform columns in dataset.

    PARAMS:
    -------
    index: index for dataset and log
    action: action to be logged
    description: description of action

    return: None
    """
    # get columns names from description
    columns, func = (
        re.search(r"\'.+\'", description).group(0).replace("'", "").split(" to ")
    )

    # apply transformation to columns
    if func == "day":
        # convert to day
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].dt.day
    elif func == "week":
        # convert to week
        st.session_state[f"prepped_data{index}"][columns] = (
            st.session_state[f"prepped_data{index}"][columns].dt.isocalendar().week
        )
    elif func == "month":
        # convert to month
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].dt.month
    elif func == "year":
        # convert to year
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].dt.year
    elif func == "quarter":
        # convert to quarter
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].dt.quarter
    elif func == "hour":
        # convert to hour
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].dt.hour
    elif func == "minute":
        # convert to minute
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].dt.minute
    elif func == "second":
        # convert to second
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].dt.second
    elif func == "floor":
        # floor the value
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].apply(np.floor)
    elif func == "ceil":
        # ceil the value
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].apply(np.ceil)
    elif func == "round":
        # round the value
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].apply(np.round)
    elif func == "abs":
        # absolute value
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].apply(np.abs)
    elif func in ["add", "subtract", "multiply", "divide"]:
        # get number of values for operation
        value_operation = float(
            re.search(r"[0-9]+\.{0,1}[0-9]*$", description).group(0)
        )
        if func == "add":
            # add value to column
            st.session_state[f"prepped_data{index}"][columns] = (
                st.session_state[f"prepped_data{index}"][columns] + value_operation
            )
        elif func == "subtract":
            # subtract value from column
            st.session_state[f"prepped_data{index}"][columns] = (
                st.session_state[f"prepped_data{index}"][columns] - value_operation
            )
        elif func == "multiply":
            # multiply value to column
            st.session_state[f"prepped_data{index}"][columns] = (
                st.session_state[f"prepped_data{index}"][columns] * value_operation
            )
        elif func == "divide":
            # divide value from column
            st.session_state[f"prepped_data{index}"][columns] = (
                st.session_state[f"prepped_data{index}"][columns] / value_operation
            )
    elif func == "trim":
        # trim the column
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].str.strip()
    elif func == "lower":
        # convert to lower case
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].str.lower()
    elif func == "upper":
        # convert to upper case
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].str.upper()
    elif func == "string to number":
        # convert string to number
        st.session_state[f"prepped_data{index}"][columns] = pd.to_numeric(
            st.session_state[f"prepped_data{index}"][columns], errors="coerce"
        )
    elif func in ["string to date", "string to datetime"]:
        # convert string to date
        st.session_state[f"prepped_data{index}"][columns] = pd.to_datetime(
            st.session_state[f"prepped_data{index}"][columns], errors="coerce"
        )
    elif func == "get dummies":
        # get dummies
        st.session_state[f"prepped_data{index}"] = pd.get_dummies(
            st.session_state[f"prepped_data{index}"], columns=[columns]
        )
    elif "replace" in func:
        old_txt, new_text = func.replace("replace by replacing ", "").split(" with ")
        # replace all occurrence of old_txt with new_text
        st.session_state[f"prepped_data{index}"][columns] = st.session_state[
            f"prepped_data{index}"
        ][columns].str.replace(old_txt, new_text)
