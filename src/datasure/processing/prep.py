import ast
import hashlib
import operator
import re

import numpy as np
import pandas as pd
import streamlit as st

from datasure.utils import duckdb_get_table, duckdb_save_table


def prep_apply_action(
    project_id: str,
    alias: str,
    action: str | None = None,
    description: str | None = None,
) -> None:
    """Update Log * Apply action in log to dataset.

    PARAMS:
    -------
    action: action to be logged
    description: description of action
    index: index for dataset and log

    return: None
    """
    # load existing logs
    prep_log = duckdb_get_table(
        project_id,
        f"prep_log_{alias}",
        db_name="logs",
    ).to_pandas()

    # loop through logs and apply actions to dataset
    action_handlers = {
        "remove column(s)": prep_remove_columns,
        "remove row(s)": prep_remove_rows,
        "transform column(s)": prep_transform_columns,
        "add new column": prep_add_new_column,
    }

    if all([action, description]):
        # append new action, update log with new action and get
        # current prepped dataset
        new_log = pd.DataFrame(
            {"action": action, "description": description}, index=[0]
        )
        prep_log = pd.concat([prep_log, new_log], ignore_index=True)

        duckdb_save_table(
            project_id,
            prep_log,
            f"prep_log_{alias}",
            db_name="logs",
        )

        prep_data = duckdb_get_table(
            project_id,
            alias,
            db_name="prep",
        ).to_pandas()

        prep_data = action_handlers[action](prep_data, description)
    else:
        # if no action or description is provided, just get the current
        # get the raw dataset as prepped dataset. In this case, we will
        # re-apply all actions
        prep_data = duckdb_get_table(
            project_id,
            alias,
            db_name="raw",
        ).to_pandas()

        # Apply each action based on the prep_log
        for row in prep_log.itertuples():
            action = row.action
            description = row.description

            if action in action_handlers:
                prep_data = action_handlers[action](prep_data, description)
            else:
                raise ValueError(f"Unsupported action: {action}")

    # save prepped dataset
    duckdb_save_table(
        project_id,
        prep_data,
        alias,
        db_name="prep",
    )


# function to remove columns from dataset
def prep_remove_columns(prep_data: pd.DataFrame, description: str) -> pd.DataFrame:
    """Remove columns from dataset.

    PARAMS:
    -------
    prep_data: DataFrame to remove columns from
    description: description of action

    return:
    -------
    pd.DataFrame: DataFrame with columns removed
    """
    # get column names from description
    columns = description.replace("remove column(s) ", "")
    try:
        columns = ast.literal_eval(columns)
    except (ValueError, SyntaxError):
        st.error(f"Invalid column specification: {columns}")
        return prep_data

    # drop columns from dataset
    return prep_data.drop(columns=columns, axis=1)


# function to remove rows
def prep_remove_rows(prep_data: pd.DataFrame, description: str) -> pd.DataFrame:
    """Remove rows from dataset.

    PARAMS:
    -------
    prep_data: DataFrame to remove rows from
    description: description of action

    return:
    -------
    pd.DataFrame: DataFrame with rows removed
    """
    # get row indexes from description
    if "remove row(s) by index" in description:
        rows = description.replace("remove row(s) by index", "")

        rows_drop = []
        try:
            rows_list = ast.literal_eval(rows)
        except (ValueError, SyntaxError):
            st.error(f"Invalid row specification: {rows}")
            return prep_data
        for row in rows_list:
            if ":" in row:
                start, end = row.split(":")
                rows_drop.extend(list(range(int(start), int(end) + 1)))
            else:
                rows_drop.append(int(row))

        # drop rows from dataset
        return prep_data.drop(index=rows_drop)

    if "remove row(s) by condition" in description:
        condition = re.search(r"'[a-z ]+'", description).group(0).replace("'", "")
        cols = re.search(r"\[.*?\]", description).group(0)

        if condition == "value is missing":
            # drop rows from dataset if any value in cols is missing
            try:
                cols_list = ast.literal_eval(cols)
            except (ValueError, SyntaxError):
                st.error(f"Invalid column specification: {cols}")
                return prep_data
            prep_data.dropna(subset=cols_list, inplace=True)
            return prep_data
        elif condition == "value is not missing":
            try:
                cols_list = ast.literal_eval(cols)
            except (ValueError, SyntaxError):
                st.error(f"Invalid column specification: {cols}")
                return prep_data
            drop_index = prep_data.dropna(subset=cols_list)
            if drop_index is not None:
                drop_index = list(drop_index.index)
                return prep_data.drop(index=drop_index, inplace=True)
            else:
                return prep_data
        elif condition in ["value is equal to", "value is not equal to"]:
            values = (
                re.search(r"with value.+", description)
                .group(0)
                .replace("with value ", "")
            )

            # check if column type is datetime
            try:
                cols_list = ast.literal_eval(cols)
                first_col = cols_list[0]
            except (ValueError, SyntaxError, IndexError):
                st.error(f"Invalid column specification: {cols}")
                return prep_data
            if prep_data[first_col].dtypes == "datetime64[ns]":
                try:
                    values_use = list(ast.literal_eval(values.replace("Timestamp", "")))
                except (ValueError, SyntaxError):
                    st.error(f"Invalid values specification: {values}")
                    return prep_data
            else:
                try:
                    values_use = ast.literal_eval(values)
                except (ValueError, SyntaxError):
                    st.error(f"Invalid values specification: {values}")
                    return prep_data
            if condition == "value is equal to":
                return prep_data.query(f"{first_col} not in {values_use}")
            else:
                return prep_data.query(f"{first_col} in {values_use}")
        elif condition in [
            "value is greater than",
            "value is greater than or equal to",
            "value is less than",
            "value is less than or equal to",
        ]:
            value = (
                re.search(r"with value.+", description)
                .group(0)
                .replace("with value ", "")
                .replace("'", "")
            )

            # check if value is a Timestamp
            if "Timestamp" in value:
                value = (
                    value.replace("[", "@pd.")
                    .replace("]", "")
                    .replace("(", "('")
                    .replace(")", "')")
                )
            else:
                try:
                    value_list = ast.literal_eval(value)
                    value = value_list[0]
                except (ValueError, SyntaxError, IndexError):
                    st.error(f"Invalid value specification: {value}")
                    return prep_data
            try:
                cols_list = ast.literal_eval(cols)
                cols = cols_list[0]
            except (ValueError, SyntaxError, IndexError):
                st.error(f"Invalid column specification: {cols}")
                return prep_data

            drop_logic = {
                "value is greater than": "<=",
                "value is greater than or equal to": "<",
                "value is less than": ">=",
                "value is less than or equal to": ">",
            }

            if condition in drop_logic:
                return prep_data.query(f"{cols} {drop_logic[condition]} {value}")

        elif condition in ["value is between", "value is not between"]:
            values = (
                re.search(r"with values.+", description)
                .group(0)
                .replace("with values ", "")
                .replace("'", "")
            )
            try:
                cols_list = ast.literal_eval(cols)
                cols = cols_list[0]
            except (ValueError, SyntaxError, IndexError):
                st.error(f"Invalid column specification: {cols}")
                return prep_data
            values = values.split(" and ")
            values_use = []
            for value in values:
                # check if column type is datetime
                if prep_data[cols].dtypes == "datetime64[ns]":
                    value = "@pd.Timestamp('" + value + "')"
                if value.isdigit():
                    values_use.append(int(value))
                else:
                    values_use.append(value)

            if condition == "value is between":
                return prep_data.query(
                    f"{cols} < {values_use[0]} or {cols} > {values_use[1]}"
                )
            else:
                return prep_data.query(
                    f"{cols} >= {values_use[0]} and {cols} <= {values_use[1]}"
                )
        elif condition in ["value is like", "value is not like"]:
            value = (
                re.search(r"with pattern.+", description)
                .group(0)
                .replace("with pattern ", "")
                .replace("'", "")
            )
            try:
                cols_list = ast.literal_eval(cols)
                cols = cols_list[0]
            except (ValueError, SyntaxError, IndexError):
                st.error(f"Invalid column specification: {cols}")
                return prep_data
            if condition == "value is like":
                return prep_data.query(
                    f"not {cols}.str.contains('{value}')", engine="python"
                )
            else:
                return prep_data.query(
                    f"{cols}.str.contains('{value}')", engine="python"
                )


# function to transform columns
def prep_transform_columns(prep_data: pd.DataFrame, description: str):
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
        re.search(r"\'.+\'", description)
        .group(0)
        .replace("'", "")
        .split(" to ", maxsplit=1)
    )

    datetime_extractors = {
        "day of month": lambda s: s.dt.day,
        "day of week": lambda s: s.dt.dayofweek,
        "day of year": lambda s: s.dt.dayofyear,
        "date": lambda s: s.dt.date,
        "week of year": lambda s: s.dt.isocalendar().week,
        "month of year": lambda s: s.dt.month,
        "year": lambda s: s.dt.year,
        "quarter of year": lambda s: s.dt.quarter,
        "hour": lambda s: s.dt.hour,
        "minute": lambda s: s.dt.minute,
        "second": lambda s: s.dt.second,
    }

    math_operations = {
        "floor": np.floor,
        "ceil": np.ceil,
        "round": np.round,
        "abs": np.abs,
    }

    arithmetic_ops = {
        "add": operator.add,
        "subtract": operator.sub,
        "multiply": operator.mul,
        "divide": operator.truediv,
    }

    string_ops = {
        "trim": lambda s: s.str.strip(),
        "lower": lambda s: s.str.lower(),
        "upper": lambda s: s.str.upper(),
        "string to number": lambda s: pd.to_numeric(s, errors="coerce"),
        "string to date": lambda s: pd.to_datetime(s, errors="coerce"),
        "string to datetime": lambda s: pd.to_datetime(s, errors="coerce"),
    }

    if func in datetime_extractors:
        prep_data[columns] = datetime_extractors[func](prep_data[columns])
    elif func in math_operations:
        prep_data[columns] = prep_data[columns].apply(math_operations[func])
    elif func in arithmetic_ops:
        # Extract the numeric value from the description
        value_operation = float(
            re.search(r"\s\d{1,10}(?:\.\d{1,10})?$", description).group(0).strip()
        )
        prep_data[columns] = arithmetic_ops[func](prep_data[columns], value_operation)
    elif func in string_ops:
        prep_data[columns] = string_ops[func](prep_data[columns])
    elif func == "get dummies":
        return pd.get_dummies(prep_data, columns=[columns])
    elif func.startswith("replace by replacing "):
        try:
            old_txt, new_text = func.replace("replace by replacing ", "").split(
                " with "
            )
            prep_data[columns] = prep_data[columns].str.replace(
                old_txt, new_text, regex=False
            )
        except ValueError:
            raise ValueError(
                "Invalid replace format. Expected 'replace by replacing X with Y'"
            ) from None
    elif func == "substring":
        try:
            start, end = (
                re.search(r"from \d+ to \d+", description)
                .group(0)
                .replace("from ", "")
                .split(" to ")
            )
            prep_data[columns] = prep_data[columns].str[int(start) : int(end)]
        except Exception:
            raise ValueError(
                "Invalid description format. Expected 'from X to Y'."
            ) from None
    elif func.startswith("extract pattern by extracting pattern "):
        pattern_str = func.replace("extract pattern by extracting pattern ", "")
        pattern = re.compile(rf"({pattern_str})")
        prep_data[columns] = prep_data[columns].str.extract(pattern)
    else:
        st.error(f"Unknown transformation function: {func}")
        return prep_data

    return prep_data


# functions for adding new columns
def prep_add_new_column(prep_data: pd.DataFrame, description: str) -> pd.DataFrame:
    """Transform columns in dataset.

    PARAMS:
    -------
    prep_data: DataFrame to add new column to
    description: description of action

    return:
    -------
    pd.DataFrame with new column added
    """
    # get columns names from description
    new_col, value = (
        re.search(r"\'.+\'", description).group(0).replace("'", "").split(" with ")
    )

    if "constant value" in value:
        value = value.replace("constant value ", "")
        prep_data[new_col] = value
    elif value in ["index", "uuid", "random"]:
        # handle special cases for index, uuid, and random
        if value == "index":
            # create an index column
            prep_data[new_col] = prep_data.index
        elif value == "uuid":
            # get session state project ID
            project_id = st.session_state.st_project_id
            # create a UUID column
            prep_data[new_col] = prep_data.index.to_series().apply(
                lambda i: hashlib.sha256(f"{project_id}_{i}".encode()).hexdigest()
            )
        elif value == "random":
            # create a random column
            prep_data[new_col] = np.random.rand(len(prep_data))
    else:
        # get function from value
        func = re.search(r"with [a-z]+", description).group(0).replace("with ", "")
        # get list of columns from description
        columns = re.search(r"\[.+\]", description).group(0)
        try:
            columns_list = ast.literal_eval(columns)
        except (ValueError, SyntaxError):
            st.error(f"Invalid column specification: {columns}")
            return prep_data

        agg_funcs = {
            "sum": "sum",
            "product": "product",
            "mean": "mean",
            "median": "median",
            "mode": "mode",
            "max": "max",
            "min": "min",
            "count": "count",
            "std": "std",
            "nunique": "nunique",
        }
        if func in agg_funcs:
            method = getattr(prep_data[columns_list], agg_funcs[func])
            prep_data[new_col] = method(axis=1)
        elif func in ["quotient", "diff", "index", "uuid", "random"]:
            # we need to handle quotient and diff separately
            if len(columns_list) != 2:
                st.error("Quotient and diff require exactly two columns.")
                return prep_data
            if func == "quotient":
                # calculate quotient of two columns
                prep_data[new_col] = (
                    prep_data[columns_list[0]] / prep_data[columns_list[1]]
                )
            elif func == "diff":
                # calculate difference of two columns
                prep_data[new_col] = (
                    prep_data[columns_list[0]] - prep_data[columns_list[1]]
                )
    return prep_data
