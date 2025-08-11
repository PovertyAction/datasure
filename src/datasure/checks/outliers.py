import os
import re

import numpy as np
import pandas as pd
import plotly.graph_objects as go  # type: ignore
import seaborn as sns
import streamlit as st

from datasure.utils import (
    duckdb_get_table,
    duckdb_save_table,
    get_check_config_settings,
    get_df_info,
    load_check_settings,
    save_check_settings,
    trigger_save,
)


def load_default_settings(project_id: str, settings_file: str, page_num: int) -> tuple:
    """
    Load the default settings for the summary report.

    Parameters
    ----------
    setting_file : str
            The settings file to load.

    page_num : int
            The page number of the report.

    Returns
    -------
    tuple
            A tuple containing the default settings for the summary report.

    """
    # Get config page defaults
    _, _, config_survey_key, config_survey_id, _, config_enumerator, _, _ = (
        get_check_config_settings(
            project_id=project_id,
            page_row_index=page_num - 1,
        )
    )
    # load default settings in the following order:
    # - if settings file exists, load settings from file
    # - if settings file does not exist, load default settings from config
    if settings_file and os.path.exists(settings_file):
        default_settings = load_check_settings(settings_file, "outliers") or {}
    else:
        default_settings = {}

    default_survey_id = default_settings.get("survey_id", config_survey_id)
    default_enumerator = default_settings.get("enumerator", config_enumerator)
    default_survey_key = default_settings.get("survey_key", config_survey_key)
    default_display_cols = default_settings.get("outlier_display_cols")
    default_min_threshold = default_settings.get("min_threshold")

    return (
        default_survey_id,
        default_enumerator,
        default_survey_key,
        default_display_cols,
        default_min_threshold,
    )


@st.cache_data
def expand_col_names(col_names, pattern, search_type="exact"):
    """
    Expand column names based on a pattern and search type.
    Args:
        col_names (list): List of column names to search in.
        pattern (str): Pattern to match against column names.
        search_type (str): Type of search to perform. Options are:
            - 'exact': Match exactly
            - 'startswith': Match if column name starts with the pattern
            - 'endswith': Match if column name ends with the pattern
            - 'contains': Match if column name contains the pattern
            - 'regex': Use regex to match column names
    Returns:
        list: List of column names that match the pattern based on the search type.
    """
    # Validate input parameters
    if not isinstance(col_names, list):
        raise TypeError("col_names must be a list of column names.")
    if not pattern:
        raise TypeError("pattern must be provided.")
    if pattern and not isinstance(pattern, str):
        raise TypeError("pattern must be a string.")

    search_funcs = {
        "exact": lambda col: col == pattern,
        "startswith": lambda col: col.startswith(pattern),
        "endswith": lambda col: col.endswith(pattern),
        "contains": lambda col: pattern in col,
        "regex": lambda col: re.match(pattern, col),
    }

    # Check if the search_type is valid
    if search_type not in search_funcs:
        raise ValueError(
            f"Invalid search_type '{search_type}'. Choose from: {', '.join(search_funcs.keys())}."
        )

    return [col for col in col_names if search_funcs[search_type](col)]


@st.cache_data
def update_unlocked_cols(
    outlier_settings: pd.DataFrame, col_names: list
) -> pd.DataFrame:
    """Update column names for unlocked rows in outlier settings"""
    # validate that essential columns are present
    essential_cols = ["outlier_cols", "lock_cols"]
    for col in essential_cols:
        if col not in outlier_settings.columns:
            raise ValueError(
                f"Essential column '{col}' is missing from outlier settings."
            )

    # count the number of unlocked rows. ie, search_type is not "exact" and
    # lock_cols is False
    outlier_settings["to_expand"] = outlier_settings.apply(
        lambda row: row["search_type"] != "exact" and not row["lock_cols"], axis=1
    )
    unlocked_rows_count = outlier_settings["to_expand"].sum()

    if unlocked_rows_count == 0:
        return outlier_settings  # No unlocked rows to update
    else:  # update unlocked rows
        # loop through each row and update the outlier_cols
        for index, row in outlier_settings.iterrows():
            search_type = row["search_type"]
            if search_type != "exact" and not row["lock_cols"]:
                pattern = row["pattern"]
                if pattern is None or pattern.strip() == "":
                    raise ValueError(
                        f"Missing pattern for row {index}. Please provide a valid pattern."
                    )

                new_col_names = expand_col_names(col_names, pattern, search_type)
                # update the outlier_cols with new col_names
                outlier_settings.at[index, "outlier_cols"] = new_col_names

    return outlier_settings


@st.cache_data
def update_outlier_settings(
    project_id: str,
    label: str,
    search_type: str,
    outlier_cols: list,
    outlier_method: str,
    outlier_multiplier: float,
    grouped_cols: bool | None,
    pattern: str | None,
    lock_cols: bool | None,
    soft_min: float | None,
    soft_max: float | None,
) -> None:
    """
    Update the outlier settings based on user input.
    Args:
        search_type (str): Type of search to perform on the column names.
        pattern (str): Pattern to match against column names.
        outlier_cols (list): List of columns to check for outliers.
        lock_cols (bool): Whether to lock the selected columns.
        outlier_method (str): Outlier detection method.
        outlier_multiplier (float): Multiplier for outlier detection.
        soft_min (float | None): Soft minimum value for outlier detection.
        soft_max (float | None): Soft maximum value for outlier detection.
        settings_file (str): Path to the settings file.
    """
    # validate input parameters
    if not isinstance(outlier_cols, list):
        raise TypeError("outlier_cols must be a list of column names.")
    if not isinstance(search_type, str):
        raise TypeError("search_type must be a string.")
    if pattern is not None and not isinstance(pattern, str):
        raise TypeError("pattern must be a string.")
    if not isinstance(outlier_method, str):
        raise TypeError("outlier_method must be a string.")
    if not isinstance(outlier_multiplier, (int, float)):  # noqa UP038
        raise TypeError("outlier_multiplier must be a number.")
    if soft_min is not None and not isinstance(soft_min, (int, float)):  # noqa UP038
        raise TypeError("soft_min must be a number or None.")
    if soft_max is not None and not isinstance(soft_max, (int, float)):  # noqa UP038
        raise TypeError("soft_max must be a number or None.")
    if lock_cols is not None and not isinstance(lock_cols, bool):
        raise TypeError("lock_cols must be a boolean or None.")
    if grouped_cols is not None and not isinstance(grouped_cols, bool):
        raise TypeError("grouped_cols must be a boolean or None.")

    # get current settings data
    logs = duckdb_get_table(
        project_id=project_id,
        alias=f"outliers_setting_logs_{label}",
        db_name="logs",
    ).to_pandas()

    # append new settings to the logs
    new_settings = {
        "search_type": search_type,
        "pattern": pattern,
        "outlier_cols": outlier_cols,
        "lock_cols": lock_cols,
        "grouped_cols": grouped_cols,
        "outlier_method": outlier_method,
        "outlier_multiplier": outlier_multiplier,
        "soft_min": soft_min,
        "soft_max": soft_max,
    }

    if not logs.empty:
        # if logs already exist, append new settings
        logs = pd.concat([logs, pd.DataFrame([new_settings])], ignore_index=True)
        # check if there are duplicate settings and drop one
        logs = logs.drop_duplicates(
            subset=["outlier_cols"],
            keep="last",
        )

    else:
        # if logs do not exist, create new logs with the new settings
        logs = pd.DataFrame([new_settings])

    # save the updated settings to the database
    duckdb_save_table(
        project_id=project_id,
        table_data=logs,
        alias=f"outliers_setting_logs_{label}",
        db_name="logs",
    )


# outliers check settings
def outliers_report_settings(
    project_id: str, data: pd.DataFrame, settings_file: str, page_num: int, label: str
) -> tuple:
    """
    Function to create a report on survey duplicates
    Args:
        data: DataFrame
    Returns:

    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for outliers report")

        st.write("---")

        all_cols, string_columns, numeric_columns, _, _ = get_df_info(
            data, cols_only=True
        )

        string_numeric_cols = [
            col for col in all_cols if col in string_columns or col in numeric_columns
        ]

        # load default settings
        (
            default_survey_id,
            default_enumerator,
            default_survey_key,
            default_display_cols,
            default_min_threshold,
        ) = load_default_settings(project_id, settings_file, page_num)

        with st.container(border=True):
            st.markdown("### Admin columns")
            ac1, ac2, ac3 = st.columns(3)
            with ac1:
                default_survey_id_index = (
                    string_numeric_cols.index(default_survey_id)
                    if default_survey_id and default_survey_id in string_numeric_cols
                    else None
                )
                survey_id = st.selectbox(
                    "Survey ID",
                    options=string_numeric_cols,
                    help="Select the column that contains the survey ID",
                    key="survey_id_outliers",
                    index=default_survey_id_index,
                    on_change=trigger_save,
                    kwargs={"state_name": "survey_id_save"},
                )
                if (
                    "survey_id_save" in st.session_state
                    and st.session_state.survey_id_save
                ):
                    save_check_settings(
                        settings_file=settings_file,
                        check_name="outliers",
                        check_settings={"survey_id": survey_id},
                    )
                    st.session_state.survey_id_save = False

            with ac2:
                default_survey_key_index = (
                    string_numeric_cols.index(default_survey_key)
                    if default_survey_key and default_survey_key in string_numeric_cols
                    else None
                )
                survey_key = st.selectbox(
                    "Survey Key",
                    options=string_numeric_cols,
                    key="survey_key_outliers",
                    help="Select the column that contains the survey key",
                    index=default_survey_key_index,
                    on_change=trigger_save,
                    kwargs={"state_name": "survey_key_save"},
                )
                if (
                    "survey_key_save" in st.session_state
                    and st.session_state.survey_key_save
                ):
                    save_check_settings(
                        settings_file=settings_file,
                        check_name="outliers",
                        check_settings={"survey_key": survey_key},
                    )
                    st.session_state.survey_key_save = False

            with ac3:
                default_enumerator_index = (
                    string_numeric_cols.index(default_enumerator)
                    if default_enumerator and default_enumerator in string_numeric_cols
                    else None
                )
                enumerator = st.selectbox(
                    "Enumerator ID",
                    options=string_numeric_cols,
                    key="enumerator_outliers",
                    help="Select the column that contains the enumerator ID",
                    index=default_enumerator_index,
                    on_change=trigger_save,
                    kwargs={"state_name": "enumerator_save"},
                )
                if (
                    "enumerator_save" in st.session_state
                    and st.session_state.enumerator_save
                ):
                    save_check_settings(
                        settings_file=settings_file,
                        check_name="outliers",
                        check_settings={"enumerator": enumerator},
                    )
                    st.session_state.enumerator_save = False

        search_type_options = ["exact", "startswith", "endswith", "contains", "regex"]

        with st.container(border=True):
            default_outlier_display_cols = (
                [col for col in default_display_cols if col in all_cols]
                if default_display_cols
                else None
            )
            # show display columns
            st.markdown("### Display columns")
            outlier_display_cols = st.multiselect(
                label="Select columns to display in the outliers report",
                options=all_cols,
                default=default_outlier_display_cols,
                help="Select columns to display in the outliers report eg. survey key, enumerator, survey ID, etc.",
                on_change=trigger_save,
                kwargs={"state_name": "outlier_display_cols_save"},
            )

            if (
                "outlier_display_cols_save" in st.session_state
                and st.session_state.outlier_display_cols_save
            ):
                save_check_settings(
                    settings_file=settings_file,
                    check_name="outliers",
                    check_settings={"outlier_display_cols": outlier_display_cols},
                )
                st.session_state.outlier_disp_save = False

            st.markdown("### Minimum Threshold")
            mt1, _ = st.columns([0.2, 0.8])
            with mt1:
                default_min_threshold_value = (
                    default_min_threshold if default_min_threshold else None
                )
                min_threshold = st.number_input(
                    label="Set general minimum threshold",
                    min_value=20,
                    max_value=50,
                    value=default_min_threshold_value,
                    step=1,
                    help="Set the minimum threshold for outlier detection. "
                    "This is the minimum number of non-null values required to consider a column for outlier detection."
                    "The default value is 30 for standard deviation and 20 for Inter-Quartile Range.",
                    key="min_threshold_key",
                    on_change=trigger_save,
                    kwargs={"state_name": "min_threshold_save"},
                )
                if (
                    "min_threshold_save" in st.session_state
                    and st.session_state.min_threshold_save
                ):
                    save_check_settings(
                        settings_file=settings_file,
                        check_name="outliers",
                        check_settings={"min_threshold": min_threshold},
                    )
                    st.session_state.min_threshold_save = False

        # adding outlier columns and settings
        st.markdown("### Outlier columns")
        st.info(
            "Use the :material/add: button to add columns to check for outliers and the "
            ":material/delete: button to remove columns."
        )

        oc1, oc2, _ = st.columns([0.4, 0.3, 0.3])
        with (
            oc1,
            st.popover(
                label=":material/add: Add outlier column", use_container_width=True
            ),
        ):
            search_type = st.selectbox(
                label="Search type",
                options=search_type_options,
                index=0,
                help="Select the type of search to perform on the column names.",
            )

            def search_type_info(search_type: str) -> None:
                """Display info based on the selected search type."""
                if search_type == "exact":
                    st.info(
                        "Select columns that match the exact name. You may select multiple columns."
                    )
                elif search_type == "startswith":
                    st.info(
                        "Select columns that start with the specified pattern. You will have to enter the pattern in the input box below."
                    )
                elif search_type == "endswith":
                    st.info(
                        "Select columns that end with the specified pattern. You will have to enter the pattern in the input box below."
                    )
                elif search_type == "contains":
                    st.info(
                        "Select columns that contain the specified pattern. You will have to enter the pattern in the input box below."
                    )
                elif search_type == "regex":
                    st.info(
                        "Select columns that match the specified regex pattern. You will have to enter the pattern in the input box below."
                    )

            search_type_info(search_type=search_type)

            if search_type == "exact":
                outlier_cols_sel = st.multiselect(
                    label="Select columns to check for outliers",
                    options=numeric_columns,
                    default=None,
                    help="Select column or group of columns to check for outliers. "
                    "Only numeric columns are available for outlier detection.",
                )

                # set other options to None
                pattern, lock_cols = None, None
            else:
                pattern = st.text_input(
                    label="Enter pattern to match column names",
                    placeholder="Enter pattern to match column names",
                    help="Enter the pattern to match column names based on the selected search type.",
                )
                if pattern:
                    outlier_cols_patt = expand_col_names(
                        numeric_columns, pattern, search_type=search_type
                    )
                else:
                    outlier_cols_patt = []

                st.write(
                    "**Columns Selected:**, ",
                    ", ".join(outlier_cols_patt) if outlier_cols_patt else "None",
                )

            outlier_cols = (
                outlier_cols_sel if search_type == "exact" else outlier_cols_patt
            )

            if outlier_cols:
                with st.container(border=True):
                    st.write("**Column Options:**")

                    gc1, gc2 = st.columns([0.5, 0.5])
                    with gc1:
                        grouped_cols = st.toggle(
                            label="Group columns",
                            key="outlier_cols_grouped",
                            help="Group selected columns together for outlier detection. "
                            "If grouped, outliers will be detected across all selected columns as a single group.",
                            disabled=not outlier_cols or len(outlier_cols) < 2,
                        )
                    with gc2:
                        lock_cols = st.toggle(
                            label="Lock column selection",
                            key="outlier_cols_lock",
                            help="Lock the selected columns to prevent changes. "
                            "If unlocked, column list may be updated when the data changes.",
                            disabled=not outlier_cols
                            or len(outlier_cols) < 2
                            or search_type == "exact",
                        )

                    with st.container(border=True):
                        st.write("**Outlier Options:**")
                        uc1, uc2 = st.columns([0.5, 0.5])

                        with uc1:
                            outlier_method = st.selectbox(
                                label="Select outlier detection method",
                                options=[
                                    "Interquartile Range (IQR)",
                                    "Standard Deviation (SD)",
                                ],
                                index=0,
                                help="Select the method to use for outlier detection.",
                                key="outlier_method",
                            )
                        with uc2:
                            outlier_multiplier = st.number_input(
                                label="Select multiplier for outlier detection",
                                min_value=0.0,
                                max_value=3.0,
                                value=1.5
                                if outlier_method == "Interquartile Range (IQR)"
                                else 3.0,
                                step=0.1,
                                help="Select the multiplier to use for outlier detection. "
                                "For IQR method, this is the multiplier for the interquartile range. "
                                "For SD method, this is the number of standard deviations from the mean.",
                                key="outlier_multiplier",
                            )

                        lc1, lc2 = st.columns([0.5, 0.5])
                        with lc1:
                            soft_min = st.number_input(
                                label="(OPTIONAL) Soft minimum",
                                help="(OPTIONAL) Soft minimum value for outlier detection. "
                                "All values below this will be considered as outliers regardless of the method used.",
                                value=None,
                            )
                        with lc2:
                            soft_max = st.number_input(
                                label="(OPTIONAL) Soft maximum",
                                help="(OPTIONAL) Soft maximum value for outlier detection. "
                                "All values above this will be considered as outliers regardless of the method used.",
                                value=None,
                            )
            else:
                st.warning(
                    "No columns selected. Please select columns to check for outliers."
                )
                (
                    outlier_cols,
                    outlier_method,
                    outlier_multiplier,
                    grouped_cols,
                    pattern,
                    lock_cols,
                    soft_min,
                    soft_max,
                ) = ([], "", 0, False, None, False, 0, 0)

            st.button(
                label="Add outlier column",
                type="primary",
                use_container_width=True,
                on_click=update_outlier_settings,
                kwargs={
                    "project_id": project_id,
                    "label": label,
                    "search_type": search_type,
                    "outlier_cols": outlier_cols,
                    "outlier_method": outlier_method,
                    "outlier_multiplier": outlier_multiplier,
                    "grouped_cols": grouped_cols,
                    "pattern": pattern,
                    "lock_cols": lock_cols,
                    "soft_min": soft_min,
                    "soft_max": soft_max,
                },
                disabled=not outlier_cols,
            )

        with (
            oc2,
            st.popover(
                label=":material/delete: Delete outlier column",
                use_container_width=True,
            ),
        ):
            st.markdown("### Remove outlier columns")

            logs = duckdb_get_table(
                project_id=project_id,
                alias=f"outliers_setting_logs_{label}",
                db_name="logs",
            ).to_pandas()

            if logs.empty:
                st.info(
                    "No outlier columns have been added yet. Please add outlier columns to remove them."
                )
            else:
                # add new new column combine index, search_type and pattern
                logs["index"] = (
                    logs.index.astype(str)
                    + " - "
                    + logs["search_type"]
                    + " - "
                    + logs["pattern"].fillna("")
                )

                # get unique values in index
                unique_index = logs["index"].unique().tolist()

                selected_index = st.selectbox(
                    label="Select outlier column to remove",
                    options=unique_index,
                    help="Select the outlier column to remove from the list of added outlier columns.",
                )

                if selected_index:
                    # confirm deletion
                    confirm_delete = st.button(
                        label="Confirm deletion",
                        type="primary",
                        use_container_width=True,
                    )
                    if confirm_delete:
                        # remove the selected index from the logs
                        logs = logs[logs["index"] != selected_index]

                        # remove index column
                        logs = logs.drop(columns=["index"])

                        # save the updated logs to the database
                        duckdb_save_table(
                            project_id=project_id,
                            table_data=logs,
                            alias=f"outliers_setting_logs_{label}",
                            db_name="logs",
                        )

        outlier_logs = duckdb_get_table(
            project_id=project_id,
            alias=f"outliers_setting_logs_{label}",
            db_name="logs",
        ).to_pandas()

        if outlier_logs.empty:
            st.info(
                "No outlier columns have been added yet. Please add outlier columns to see the settings."
            )

        else:
            st.dataframe(
                outlier_logs,
                use_container_width=True,
                hide_index=False,
                column_config={
                    "search_type": st.column_config.Column("Search Type"),
                    "pattern": st.column_config.Column("Pattern"),
                    "outlier_cols": st.column_config.Column("Outlier Columns"),
                    "lock_cols": st.column_config.Column("Lock Columns"),
                    "grouped_cols": st.column_config.Column("Grouped Columns"),
                    "outlier_method": st.column_config.Column("Outlier Method"),
                    "outlier_multiplier": st.column_config.NumberColumn(
                        "Outlier Multiplier", format="%.2f"
                    ),
                    "soft_min": st.column_config.NumberColumn(
                        "Soft Min", format="%.2f", width="small"
                    ),
                    "soft_max": st.column_config.NumberColumn(
                        "Soft Max", format="%.2f", width="small"
                    ),
                },
            )
    return (outlier_display_cols, min_threshold, survey_id, survey_key, enumerator)


@st.cache_data
def stack_outlier_columns(df: pd.DataFrame, col_names: list) -> pd.Series:
    """Stack specified columns of a DataFrame into a single Series.
    Args:
        df (pd.DataFrame): The DataFrame containing the data.
        col_names (list): List of column names to stack.

    Returns
    -------
        pd.Series: A Series containing the stacked values of the specified columns.
    """
    # check if dataset is empty
    if df.empty:
        raise ValueError("The DataFrame is empty.")

    # validate that all column names exist in the dataframe
    for col in col_names:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' does not exist in the DataFrame.")
    # for each column, check if it is numeric, if not, check if it can
    # be converted to numeric, else raise an error
    for col in col_names:
        if not pd.api.types.is_numeric_dtype(df[col]):
            try:
                df[col] = pd.to_numeric(df[col], errors="raise")
            except ValueError:
                raise ValueError(f"Column '{col}' cannot be converted to numeric type.")  # noqa: B904

    # Stack the specified columns into a single column
    stacked_values = df[col_names].stack()

    return stacked_values.reset_index(drop=True)


@st.cache_data
def compute_outlier_stats(
    series: pd.Series, outlier_type: str | None, multiplier: float | None
) -> dict:
    """Compute outlier statistics for a given Series.
    Args:
        series (pd.Series): The Series to compute statistics for.
        outlier_type (str | None): The type of outlier detection method to use.
        Options are "sd" for standard deviation or "iqr" for interquartile range.
        multiplier (float | None): The multiplier to use for outlier detection. If None,
        defaults to 3 for standard deviation and 1.5 for IQR.

    Returns
    -------
        dict: A dictionary containing the computed statistics including mean, median,
        standard deviation, lower bound, and upper bound.
    """
    if series.empty:
        raise ValueError("The Series is empty.")

    if outlier_type not in [
        None,
        "Interquartile Range (IQR)",
        "Standard Deviation (SD)",
    ]:
        raise ValueError("Invalid outlier type. Use 'sd' or 'iqr'.")

    if multiplier is not None and multiplier <= 0:
        raise ValueError("Multiplier must be a positive number.")

    count = series.count()
    min_value = series.min()
    max_value = series.max()
    mean = series.mean()
    median = series.median()
    sd = series.std()
    iqr = series.quantile(0.75) - series.quantile(0.25)

    if outlier_type in "Standard Deviation (SD)":
        if not multiplier:
            multiplier = 3.0  # default to 3 standard deviations
        lower_bound = mean - (multiplier * sd)
        upper_bound = mean + (multiplier * sd)
    elif outlier_type in [
        None,
        "Interquartile Range (IQR)",
    ]:  # default to IQR if not specified
        if not multiplier:
            multiplier = 1.5  # default to 1.5 IQR
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - (multiplier * iqr)
        upper_bound = q3 + (multiplier * iqr)

    return {
        "count": count,
        "min_value": min_value,
        "max_value": max_value,
        "mean": mean,
        "median": median,
        "sd": sd,
        "iqr": iqr,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
    }


# Function to detect outliers
@st.cache_data
def compute_outlier_output(
    df: pd.DataFrame,
    outlier_settings: pd.DataFrame,
    display_cols: list,
    min_threshold: float | None,
    survey_key: str,
    survey_id: str | None,
    enumerator: str | None,
) -> pd.DataFrame:
    """Detect outliers in the DataFrame based on the specified settings.

    Args:
        df (pd.DataFrame): DataFrame containing the survey data.
        outlier_settings (pd.DataFrame): DataFrame containing the outlier settings.
        survey_key (str): Column name for survey key.
        survey_id (str | None): Column name for survey ID.
        enumerator (str | None): Column name for enumerator ID.

    Returns
    -------
        pd.DataFrame: DataFrame containing the outlier summary.
    """
    # check that the DataFrame is not empty
    if df.empty:
        raise ValueError("The DataFrame is empty. Please provide a valid DataFrame.")

    # get a list of columns to include in the output
    # Build a list of columns to include in the output, avoiding duplicates
    # and None values
    include_cols = []
    for col in display_cols or []:
        if col and col not in include_cols:
            include_cols.append(col)
    for col in [survey_key, survey_id, enumerator]:
        if col and col not in include_cols:
            include_cols.append(col)

    # create an empty DataFrame to store the outlier results
    outlier_results = pd.DataFrame()

    # create admin_data DataFrame to store survey metadata
    admin_data = df[include_cols].copy(deep=True)

    # Iterate through each row in the outlier settings DataFrame
    for _, row in outlier_settings.iterrows():
        # Extract outlier settings with defaults for robustness
        outlier_cols = row.get("outlier_cols", [])
        grouped_cols = row.get("grouped_cols", False)
        outlier_method = row.get("outlier_method", "Interquartile Range (IQR)")
        outlier_multiplier = row.get("outlier_multiplier", 1.5)
        soft_min = row.get("soft_min", None)
        soft_max = row.get("soft_max", None)

        # Ensure outlier_cols is a list
        if isinstance(outlier_cols, str):
            outlier_cols = [outlier_cols]
        elif not isinstance(outlier_cols, list):
            outlier_cols = list(outlier_cols)

        # create a subset of the dataset containing
        outlier_df_all = df[[survey_key] + outlier_cols].copy(deep=True)

        if min_threshold is None:
            min_threshold = 20 if outlier_method == "Interquartile Range (IQR)" else 30

        if len(outlier_cols) == 1:
            # count the number of non-null values in the column
            non_null_count = outlier_df_all[outlier_cols[0]].count()

            # compute outlier stats for the single column
            outlier_stats = compute_outlier_stats(
                outlier_df_all[outlier_cols[0]],
                outlier_type=outlier_method,
                multiplier=outlier_multiplier,
            )
        elif grouped_cols is True:  # compute group outlier stats
            # stack cols
            stacked_series = stack_outlier_columns(outlier_df_all, outlier_cols)
            # count the number of non-null values in the stacked series
            non_null_count = stacked_series.count()

            # compute outlier stats for the stacked series
            outlier_stats = compute_outlier_stats(
                stacked_series,
                outlier_type=outlier_method,
                multiplier=outlier_multiplier,
            )

        for col in outlier_cols:
            if grouped_cols is not True:
                non_null_count = outlier_df_all[col].count()

                outlier_stats = compute_outlier_stats(
                    outlier_df_all[col],
                    outlier_type=outlier_method,
                    multiplier=outlier_multiplier,
                )

            outlier_df = outlier_df_all[[survey_key, col]].copy(deep=True)

            # add new column showing reason for flag
            def add_outlier_reason(value, soft_min, soft_max, outlier_stats):
                """Add a reason for outlier based on the value and
                outlier statistics.
                """
                if value < outlier_stats["lower_bound"]:
                    return (
                        f"Value is below lower bound {outlier_stats['lower_bound']:.2f}"
                    )
                elif value > outlier_stats["upper_bound"]:
                    return (
                        f"Value is above upper bound {outlier_stats['upper_bound']:.2f}"
                    )
                else:
                    if soft_min is not None and value < soft_min:
                        return f"Value is below soft minimum {soft_min:.2f}"
                    elif soft_max is not None and value > soft_max:
                        return f"Value is above soft maximum {soft_max:.2f}"
                    else:
                        return "no outlier"  # return empty string if no reason

            if non_null_count < min_threshold:
                outlier_df["outlier reason"] = "no outlier"
            else:
                # apply the function to the column to create a new column for
                # outlier reason
                outlier_df["outlier reason"] = outlier_df[col].apply(
                    lambda x,
                    soft_min=soft_min,
                    soft_max=soft_max,
                    outlier_stats=outlier_stats: add_outlier_reason(
                        x, soft_min, soft_max, outlier_stats
                    )
                )

            # Prepare stats columns to add
            stats_map = {
                "min_value": outlier_stats.get("min_value", None),
                "max_value": outlier_stats.get("max_value", None),
                "mean": outlier_stats.get("mean", None),
                "median": outlier_stats.get("median", None),
                "std": outlier_stats.get("sd", None),
                "iqr": outlier_stats.get("iqr", None),
                "lower_bound": outlier_stats.get("lower_bound", None),
                "upper_bound": outlier_stats.get("upper_bound", None),
                "outlier_method": outlier_method,
                "outlier_multiplier": outlier_multiplier,
                "soft_min": soft_min,
                "soft_max": soft_max,
            }

            for k, v in stats_map.items():
                outlier_df[k] = v

            # Assign variable name and rename value column
            outlier_df["column name"] = col
            outlier_df = outlier_df.rename(columns={col: "column value"})

            # reorder columns to ensure consistent output
            outlier_df = outlier_df[
                [
                    survey_key,
                    "column name",
                    "column value",
                    "min_value",
                    "max_value",
                    "mean",
                    "median",
                    "std",
                    "iqr",
                    "lower_bound",
                    "upper_bound",
                    "outlier reason",
                    "outlier_method",
                    "outlier_multiplier",
                    "soft_min",
                    "soft_max",
                ]
            ]

            # append to the outlier results DataFrame
            outlier_results = pd.concat(
                [outlier_results, outlier_df],
                ignore_index=True,
            )

        # merge admin_data with outlier_df in (1:m) relationship
        merged_results = pd.merge(
            admin_data,
            outlier_results,
            how="left",
            on=survey_key,
        )

    return merged_results


def display_outlier_output(outlier_data: pd.DataFrame) -> None:
    """Display the outlier output in a Streamlit app."""
    # Get the outlier settings from the database

    st.write("---")
    st.title("Outliers")

    outlier_data_disp = outlier_data[outlier_data["outlier reason"] != "no outlier"]

    if outlier_data_disp.empty:
        st.info("No outliers detected in the selected columns.")
        return

    st.dataframe(
        outlier_data_disp,
        use_container_width=True,
        hide_index=True,
        column_config={
            "column name": st.column_config.Column("Column Name"),
            "column value": st.column_config.Column(
                "Column Value",
                help="The value of the column that is flagged as an outlier.",
            ),
            "min_value": st.column_config.NumberColumn(
                "Min Value",
                format="%.2f",
            ),
            "max_value": st.column_config.NumberColumn(
                "Max Value",
                format="%.2f",
            ),
            "mean": st.column_config.NumberColumn(
                "Mean",
                format="%.4f",
            ),
            "std": st.column_config.NumberColumn(
                "SD",
                format="%.4f",
            ),
            "median": st.column_config.NumberColumn(
                "Median",
                format="%.4f",
            ),
            "iqr": st.column_config.NumberColumn(
                "IQR",
                format="%.2f",
            ),
            "outlier reason": st.column_config.Column(
                "Outlier Reason",
                help="Reason for flagging the value as an outlier. "
                "This includes whether the value is below the lower bound, above the upper bound, "
                "or below/above the soft minimum/maximum.",
            ),
            "outlier_method": st.column_config.Column(
                "Outlier Method",
                help="Method used for outlier detection. "
                "This can be either Interquartile Range (IQR) or Standard Deviation (SD)",
            ),
            "soft_min": st.column_config.NumberColumn(
                "Soft Min",
            ),
            "soft_max": st.column_config.NumberColumn(
                "Soft Max",
            ),
            "outlier_multiplier": st.column_config.NumberColumn(
                "Outlier Multiplier",
            ),
            "lower_bound": st.column_config.NumberColumn(
                "Lower Bound", format="%.2f", width="small"
            ),
            "upper_bound": st.column_config.NumberColumn(
                "Upper Bound", format="%.2f", width="small"
            ),
        },
    )


def compute_column_outlier_summary(
    outlier_data: pd.DataFrame, survey_key
) -> pd.DataFrame:
    """Compute a summary of outliers for each column in the DataFrame."""
    # validate that outlier_data is not empty
    if outlier_data.empty:
        return pd.DataFrame()

    # drop duplicates based on column name and survey key
    outlier_summary = outlier_data.drop_duplicates(subset=["column name", survey_key])

    col_counts = outlier_summary["column name"].value_counts().reset_index()
    outlier_summary = outlier_summary.merge(
        col_counts,
        on="column name",
        how="left",
    )

    # count number of outliers per column
    outlier_summary["flagged as outlier"] = outlier_summary.apply(
        lambda row: 1 if row["outlier reason"] != "no outlier" else 0, axis=1
    )

    outlier_counts = (
        outlier_summary.groupby("column name")["flagged as outlier"].sum().reset_index()
    )
    outlier_counts.columns = ["column name", "outlier count"]

    # merge outlier counts with the summary
    outlier_summary = outlier_summary.merge(
        outlier_counts,
        on="column name",
        how="left",
    )

    # keep only relevant columns
    outlier_summary = outlier_summary[
        [
            "column name",
            "count",
            "outlier count",
            "min_value",
            "max_value",
            "mean",
            "median",
            "std",
            "iqr",
            "lower_bound",
            "upper_bound",
        ]
    ]

    # reorder columns
    outlier_summary = outlier_summary[
        [
            "column name",
            "count",
            "outlier count",
            "min_value",
            "max_value",
            "mean",
            "median",
            "std",
            "iqr",
            "lower_bound",
            "upper_bound",
        ]
    ]

    # remove duplicates by column name and keep the first occurrence
    outlier_summary = outlier_summary.drop_duplicates(subset=["column name"])

    return outlier_summary


def display_outlier_column_summary(outlier_summary: pd.DataFrame) -> None:
    """Display the outlier summary in a Streamlit app."""
    st.write("---")
    st.title("Outlier Column Summary")

    if outlier_summary.empty:
        raise ValueError(
            "No outlier summary data available. Please check the outlier settings and data."
        )

    cmap = sns.light_palette("pink", as_cmap=True)

    outlier_summary = outlier_summary.style.background_gradient(
        subset=["outlier count"], cmap=cmap
    )

    st.dataframe(
        outlier_summary,
        use_container_width=True,
        hide_index=True,
        column_config={
            "column name": st.column_config.Column("Column Name"),
            "count": st.column_config.NumberColumn("# of Values", format="%.0f"),
            "outlier count": st.column_config.NumberColumn(
                "# of Outliers",
                format="%.0f",
            ),
            "min_value": st.column_config.NumberColumn("Minimum Value", format="%.0f"),
            "max_value": st.column_config.NumberColumn("Maximum Value", format="%.0f"),
            "mean": st.column_config.NumberColumn(
                "Mean",
                format="%.2f",
            ),
            "median": st.column_config.NumberColumn(
                "Median",
                format="%.2f",
            ),
            "iqr": st.column_config.NumberColumn(
                "Interquartile Range",
                format="%.2f",
            ),
            "std": st.column_config.NumberColumn(
                "Standard Deviation",
                format="%.2f",
            ),
            "lower_bound": st.column_config.NumberColumn(
                "Lower Bound",
                format="%.2f",
            ),
            "upper_bound": st.column_config.NumberColumn(
                "Upper Bound",
                format="%.2f",
            ),
        },
    )


# function to create outlier distribution
@st.cache_data
def create_violin_plot(data: pd.Series, title: str) -> go.Figure:
    """Create a violin plot using plotly.

    Args:
        data (pd.Series): Data series to plot
        title (str): Title for the plot

    Returns
    -------
        go.Figure: Plotly figure object containing the violin plot
    """
    return go.Figure(
        data=go.Violin(
            y=data,
            box_visible=True,
            line_color="black",
            meanline_visible=True,
            fillcolor="darkgreen",
            opacity=0.6,
            x0=title,
        )
    )


@st.cache_data
def plot_col_distribution(data: pd.DataFrame, col_name: str) -> go.Figure:
    """Plot the distribution of a specific column in the data."""
    # Check if the column exists in the DataFrame
    if col_name not in data.columns:
        raise ValueError(f"Column '{col_name}' does not exist in the DataFrame.")

    # Check if the column is numeric
    if not pd.api.types.is_numeric_dtype(data[col_name]):
        raise ValueError(
            f"Column '{col_name}' is not numeric. Cannot plot distribution."
        )

    # create a histogram of the column
    fig = go.Figure(
        data=go.Histogram(
            x=data[col_name],
            nbinsx=30,  # Adjust the number of bins as needed
            marker_color="orange",
            opacity=0.7,
        )
    )
    fig.update_layout(
        title=f"Distribution of {col_name}",
        xaxis_title=col_name,
        yaxis_title="Frequency",
        template="plotly_white",
    )
    return fig


def get_outlier_cols(outlier_settings: pd.DataFrame) -> list:
    """Get a list of outlier columns from the outlier settings DataFrame."""
    # Count the number of columns checked for outliers
    cols = []
    for i in range(len(outlier_settings)):
        col = outlier_settings.iloc[i]["outlier_cols"]
        if isinstance(col, np.ndarray):
            cols.append(col[0])
        elif isinstance(col, list):
            cols.extend(col)

    return cols


# Function to display outlier metrics
@st.cache_data
def display_outlier_metrics(
    outliers_data: pd.DataFrame,
    outlier_cols: list,
    survey_key: str,
    survey_id: str | None,
    enumerator: str | None,
) -> None:
    """Display metrics related to outliers in a summary format.
    Args:
    outliers_summary (pd.DataFrame): DataFrame containing outlier summary.
    outlier_cols (list): List of columns checked for outliers.
    enumerator (str): Column name for enumerator ID.
    """
    st.title("Outlier Summary")

    # Count the number of columns checked for outliers
    outlier_cols_count = len(outlier_cols)

    # number of outliers flagged
    total_outliers = outliers_data[
        outliers_data["outlier reason"] != "no outlier"
    ].shape[0]

    # columns flagged with at least one outlier
    at_least_one_outlier = (
        outliers_data["column name"].nunique() if not outliers_data.empty else 0
    )

    # number of enumerators with outliers flagged
    total_enumerators = (
        outliers_data[outliers_data["outlier reason"] != "no outlier"][
            enumerator
        ].nunique()
        if enumerator and not outliers_data.empty
        else 0
    )

    col1, col2, col3, col4 = st.columns(spec=4, border=True)

    col1.metric(
        label="Variables checked",
        value=f"{outlier_cols_count:,}",
        help="Columns checked for outlier values",
    )

    col2.metric(
        label="Outlier variables",
        value=f"{at_least_one_outlier:,}",
        help="Variables with at least one outlier",
    )

    col3.metric(
        label="Number of outliers",
        value=f"{total_outliers:,}",
        help="Total number of identified outliers",
    )

    if enumerator:
        col4.metric(
            label="Number of enumerators with outliers",
            value=f"{total_enumerators:,}",
            help="Number of enumerators with outliers flagged",
        )
    else:
        with col4:
            st.write("Number of enumerators")
            st.info(
                "Enumerator column is not selected. Go to the :material/settings: settings section above to select the enumerator column."
            )


def inspect_outliers_columns(
    data: pd.DataFrame,
    outlier_data: pd.DataFrame,
    col_summary: pd.DataFrame,
    outlier_cols: list,
    display_cols: list | None,
    survey_key: str,
    survey_id: str,
    enumerator: str,
) -> None:
    """Inspect outlier columns in the DataFrame.

    Args:
        data (pd.DataFrame): DataFrame containing the survey data.
        outlier_data (list): List of outlier columns to inspect.

    Returns
    -------
        None
    """
    st.title("Inspect Columns")
    if outlier_data.empty:
        st.info(
            "No outlier columns selected. Please select outlier columns to inspect."
        )
        return

    include_cols = []
    # add global display columns to include_cols
    if display_cols:
        include_cols.extend(display_cols)
    for col in [survey_key, survey_id, enumerator]:
        if col and col not in include_cols:
            include_cols.append(col)

    ic1, ic2 = st.columns([0.2, 0.8])

    with ic1:
        # create a multiselect widget to select outlier columns
        selected_col = st.selectbox(
            label="Select outlier columns to inspect",
            options=outlier_cols,
            help="Select the outlier columns to inspect. "
            "You can only select one column at a time.",
        )

        # check if the selected column is in the outlier data
        if selected_col not in data.columns:
            raise ValueError(
                f"Selected column '{selected_col}' is not present in the data. "
                "Please select a valid column."
            )

    with ic2:
        inspect_display_cols = st.multiselect(
            label="Select columns to display",
            options=data.columns.tolist(),
            default=[selected_col],
            help="Select the columns to display in the inspection table. "
            "You can select multiple columns to display alongside the outlier column.",
            disabled=not selected_col,
        )

        if inspect_display_cols:
            include_cols.extend(inspect_display_cols)

    if selected_col:
        # check if the selected column is in the outlier data
        if selected_col not in outlier_data["column name"].unique():
            st.warning(
                f"Column '{selected_col}' is not an outlier column. Please select a valid outlier column."
            )
            return

        # filter the outlier data for the selected column
        include_cols.append(selected_col)
        include_cols = list(set(include_cols))

    # merge with outlier data to get the outlier reason
    col_outlier_details = data[include_cols].copy(deep=True)
    col_outlier_details = col_outlier_details.merge(
        outlier_data[[survey_key, "outlier reason"]],
        left_on=survey_key,
        right_on=survey_key,
        how="left",
    )

    # reorder columns
    disp_cols = [
        col for col in include_cols if col not in [survey_key, "outlier reason"]
    ]
    col_outlier_details = col_outlier_details[
        [survey_key, "outlier reason"] + disp_cols
    ]

    # display column metrics
    # return row in col_summary as dict where column name matches selected column
    col_summary_row = col_summary[col_summary["column name"] == selected_col]
    if col_summary_row.empty:
        raise ValueError(
            f"No summary data found for column '{selected_col}'. "
            "Please check the outlier settings and data."
        )
    col_summary_row = col_summary_row.iloc[0].to_dict()

    mu1, mu2, mu3, mu4, mu5 = st.columns(5, border=True)
    ml1, ml2, ml3, ml4, ml5 = st.columns(5, border=True)

    col_summary_row_count = col_summary_row["count"]
    mu1.metric(
        label="# of Values",
        value=f"{col_summary_row_count:,}",
        help="Total number of values in the column.",
    )
    col_summary_row_outlier_count = col_summary_row["outlier count"]
    mu2.metric(
        label="# of Outliers",
        value=f"{col_summary_row_outlier_count:,}",
        help="Total number of outliers in the column.",
    )
    col_summary_row_min_value = col_summary_row["min_value"]
    mu3.metric(
        label="Minimum Value",
        value=f"{col_summary_row_min_value:,.2f}",
        help="Minimum value in the column.",
    )
    col_summary_row_max_value = col_summary_row["max_value"]
    mu4.metric(
        label="Maximum Value",
        value=f"{col_summary_row_max_value:,.2f}",
        help="Maximum value in the column.",
    )
    col_summary_row_mean = col_summary_row["mean"]
    mu5.metric(
        label="Mean",
        value=f"{col_summary_row_mean:,.4f}",
        help="Mean value in the column.",
    )
    col_summary_row_median = col_summary_row["median"]
    ml1.metric(
        label="Median",
        value=f"{col_summary_row_median:,.2f}",
        help="Median value in the column.",
    )
    col_summary_row_std = col_summary_row["std"]
    ml2.metric(
        label="Standard Deviation",
        value=f"{col_summary_row_std:,.4f}",
        help="Standard deviation of the values in the column.",
    )
    col_summary_row_iqr = col_summary_row["iqr"]
    ml3.metric(
        label="Interquartile Range",
        value=f"{col_summary_row_iqr:,.2f}",
        help="Interquartile range of the values in the column.",
    )
    col_summary_row_lower_bound = col_summary_row["lower_bound"]
    ml4.metric(
        label="Lower Bound",
        value=f"{col_summary_row_lower_bound:,.2f}",
        help="Lower bound for outlier detection in the column.",
    )
    col_summary_row_upper_bound = col_summary_row["upper_bound"]
    ml5.metric(
        label="Upper Bound",
        value=f"{col_summary_row_upper_bound:,.2f}",
        help="Upper bound for outlier detection in the column.",
    )
    st.write("---")

    dc1, dc2 = st.columns(2)
    with dc1:
        st.subheader(f"Distribution of {selected_col} values")
        # plot outlier distribution
        fig = plot_col_distribution(
            data=col_outlier_details[[selected_col]], col_name=selected_col
        )
        st.plotly_chart(fig, use_container_width=True)

    with dc2:
        st.subheader(f"Violin plot of {selected_col} values")
        # create violin plot
        violin_fig = create_violin_plot(
            data=col_outlier_details[selected_col],
            title=selected_col,
        )
        st.plotly_chart(violin_fig, use_container_width=True)

    st.dataframe(
        col_outlier_details,
        use_container_width=True,
        hide_index=False,
    )


# define function to create outliers report
def outliers_report(
    project_id: str, data: pd.DataFrame, setting_file: str, page_num: int
) -> None:
    """
    Function to create a report on survey duplicates
    Args:
        data: DataFrame
    Returns:

    """
    current_pages_df = duckdb_get_table(
        project_id=project_id, alias="check_config", db_name="logs"
    ).to_pandas()

    label = current_pages_df.iloc[page_num - 1]["page_name"]

    # outliers settings
    (
        display_cols,
        min_threshold,
        survey_id,
        survey_key,
        enumerator,
    ) = outliers_report_settings(project_id, data, setting_file, page_num, label)

    outlier_settings = duckdb_get_table(
        project_id=project_id,
        alias=f"outliers_setting_logs_{label}",
        db_name="logs",
    ).to_pandas()

    if outlier_settings.empty:
        st.warning(
            "No outlier settings found. Please add outlier columns in the settings section."
        )
        return

    # update unlocked columns in outlier settings
    _, _, numeric_cols, _, _ = get_df_info(data, cols_only=True)  # get numeric columns
    outlier_settings = update_unlocked_cols(
        outlier_settings=outlier_settings,
        col_names=numeric_cols,
    )

    # save updated outlier settings
    duckdb_save_table(
        project_id=project_id,
        table_data=outlier_settings,
        alias=f"outliers_setting_logs_{label}",
        db_name="logs",
    )

    # compute outlier output
    outlier_data = compute_outlier_output(
        df=data,
        outlier_settings=outlier_settings,
        display_cols=display_cols,
        min_threshold=min_threshold,
        survey_key=survey_key,
        survey_id=survey_id,
        enumerator=enumerator,
    )

    outlier_cols = get_outlier_cols(outlier_settings)

    # display outlier metrics
    display_outlier_metrics(
        outliers_data=outlier_data,
        outlier_cols=outlier_cols,
        survey_key=survey_key,
        survey_id=survey_id,
        enumerator=enumerator,
    )

    # compute outlier summary
    outlier_summary = compute_column_outlier_summary(
        outlier_data=outlier_data, survey_key=survey_key
    )

    # display outlier summary
    display_outlier_column_summary(outlier_summary)

    # display outlier output
    display_outlier_output(outlier_data)

    # inspect outlier columns
    inspect_outliers_columns(
        data=data,
        outlier_data=outlier_data,
        col_summary=outlier_summary,
        outlier_cols=outlier_cols,
        display_cols=display_cols,
        survey_key=survey_key,
        survey_id=survey_id,
        enumerator=enumerator,
    )
