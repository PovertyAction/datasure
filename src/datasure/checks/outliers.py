import os
import re

import pandas as pd
import plotly.graph_objects as go
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
    default_display_cols = default_settings.get("outlier_display_cols", None)
    default_min_threshold = default_settings.get("min_threshod", None)

    return (
        default_survey_id,
        default_enumerator,
        default_survey_key,
        default_display_cols,
        default_min_threshold,
    )

@st.cache_data
def expand_col_names(col_names, pattern, search_type='exact'):
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
    if not pattern and not isinstance(pattern, str):
        raise TypeError("pattern must be a string.")

    search_funcs = {
        'exact': lambda col: col == pattern,
        'startswith': lambda col: col.startswith(pattern),
        'endswith': lambda col: col.endswith(pattern),
        'contains': lambda col: pattern in col,
        'regex': lambda col: re.match(pattern, col)
    }

    # Check if the search_type is valid
    if search_type not in search_funcs:
        raise ValueError(f"Invalid search_type '{search_type}'. Choose from: {', '.join(search_funcs.keys())}.")

    return [col for col in col_names if search_funcs[search_type](col)]

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
    if not isinstance(outlier_multiplier, (int, float)): #noqa UP038
        raise TypeError("outlier_multiplier must be a number.")
    if soft_min is not None and not isinstance(soft_min, (int, float)): #noqa UP038
        raise TypeError("soft_min must be a number or None.")
    if soft_max is not None and not isinstance(soft_max, (int, float)): #noqa UP038
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
        table_data= logs,
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

        string_numeric_cols = [col for col in all_cols if col in string_columns or col in numeric_columns]

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
                if "survey_id_save" in st.session_state and st.session_state.survey_id_save:
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


        search_type_options = [
            "exact",
            "startswith",
            "endswith",
            "contains",
            "regex"
        ]

        with st.container(border=True):
            default_outlier_display_cols = [col for col in default_display_cols if col in all_cols] if default_display_cols else None
            # show display columns
            st.markdown("### Display columns")
            outlier_display_cols = st.multiselect(
                label="Select columns to display in the outliers report",
                options=all_cols,
                default=default_outlier_display_cols,
                help="Select columns to display in the outliers report eg. survey key, enumerator, survey ID, etc.",
                on_change=trigger_save,
                kwargs={"state_name", "outlier_disp_save"},
            )
            if "outlier_disp_save" in st.session_state and st.session_state.outlier_disp_save:
                save_check_settings(
                    settings_file=settings_file,
                    check_name="outliers",
                    check_settings={"outlier_display_cols": outlier_display_cols},
                )

            st.markdown("### Minimum Threshold")
            mt1, _ = st.columns([0.2, 0.8])
            with mt1:
                default_min_threshold_value = default_min_threshold if default_min_threshold else None
                min_threshold = st.number_input(label="Set general minimum threshold",
                                                min_value=20,
                                                max_value=50,
                                                value=default_min_threshold_value,
                                                step=1,
                                                help="Set the minimum threshold for outlier detection. " \
                                                "This is the minimum number of non-null values required to consider a column for outlier detection." \
                                                "The default value is 30 for standard deviation and 20 for Inter-Quartile Range.",
                                                key="min_threshold_key",
                                                on_change=trigger_save,
                                                kwargs={"state_name": "min_threshold_save"}
                                )
                if "min_threshold_save" in st.session_state and st.session_state.min_threshold_save:
                    save_check_settings(settings_file=settings_file,
                                        check_name="outliers",
                                        check_settings={"min_threshold": min_threshold}
                                        )
                    st.session_state.min_threshold_save = False

        # adding outlier columns and settings
        st.markdown("### Outlier columns")
        st.info("Use the :material/add: button to add columns to check for outliers and the "
        ":material/delete: button to remove columns.")

        oc1, oc2, _ = st.columns([0.4, 0.3, 0.3])
        with oc1, st.popover(
            label=":material/add: Add outlier column", use_container_width=True):
            search_type = st.selectbox(
                label="Search type",
                options=search_type_options,
                index=0,
                help="Select the type of search to perform on the column names.",
            )

            def search_type_info(search_type: str) -> None:
                """Display info based on the selected search type."""
                if search_type == "exact":
                    st.info("Select columns that match the exact name. You may select multiple columns.")
                elif search_type == "startswith":
                    st.info("Select columns that start with the specified pattern. You will have to enter the pattern in the input box below.")
                elif search_type == "endswith":
                    st.info("Select columns that end with the specified pattern. You will have to enter the pattern in the input box below.")
                elif search_type == "contains":
                    st.info("Select columns that contain the specified pattern. You will have to enter the pattern in the input box below.")
                elif search_type == "regex":
                    st.info("Select columns that match the specified regex pattern. You will have to enter the pattern in the input box below.")

            search_type_info(search_type=search_type)


            if search_type == "exact":
                outlier_cols_sel = st.multiselect(
                    label="Select columns to check for outliers",
                    options=numeric_columns,
                    default=None,
                    help="Select column or group of columns to check for outliers. " \
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

                st.write("**Columns Selected:**, ", ", ".join(outlier_cols_patt) if outlier_cols_patt else "None")

            outlier_cols = outlier_cols_sel if search_type == "exact" else outlier_cols_patt

            if outlier_cols:
                with st.container(border=True):
                    st.write("**Column Options:**")

                    gc1, gc2 = st.columns([0.5, 0.5])
                    with gc1:
                        grouped_cols = st.toggle(
                            label="Group columns",
                            key="outlier_cols_grouped",
                            help="Group selected columns together for outlier detection. " \
                            "If grouped, outliers will be detected across all selected columns as a single group.",
                            disabled=not outlier_cols or len(outlier_cols) < 2,
                        )
                    with gc2:
                        lock_cols = st.toggle(
                            label="Lock column selection",
                            key="outlier_cols_lock",
                            help="Lock the selected columns to prevent changes. " \
                            "If unlocked, column list may be updated when the data changes.",
                            disabled=not outlier_cols or len(outlier_cols) < 2 or search_type == "exact",
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
                                value=1.5 if outlier_method == "Interquartile Range (IQR)" else 3.0,
                                step=0.1,
                                help="Select the multiplier to use for outlier detection. " \
                                "For IQR method, this is the multiplier for the interquartile range. " \
                                "For SD method, this is the number of standard deviations from the mean.",
                                key="outlier_multiplier",
                            )

                        lc1, lc2 = st.columns([0.5, 0.5])
                        with lc1:
                            soft_min = st.number_input(
                                label="(OPTIONAL) Soft minimum",
                                help="(OPTIONAL) Soft minimum value for outlier detection. " \
                                "All values below this will be considered as outliers regardless of the method used.",
                                value=None,
                            )
                        with lc2:
                            soft_max = st.number_input(
                                label="(OPTIONAL) Soft maximum",
                                help="(OPTIONAL) Soft maximum value for outlier detection. " \
                                "All values above this will be considered as outliers regardless of the method used.",
                                value=None,
                            )
            else:
                st.warning("No columns selected. Please select columns to check for outliers.")
                outlier_cols, outlier_method, outlier_multiplier, grouped_cols, pattern, lock_cols, soft_min, soft_max = (
                    [], "", 0, False, None, False, 0, 0
                )


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

        with oc2, st.popover(label=":material/delete: Delete outlier column", use_container_width=True):
            st.markdown("### Remove outlier columns")

            logs = duckdb_get_table(
                project_id=project_id,
                alias=f"outliers_setting_logs_{label}",
                db_name="logs",
            ).to_pandas()

            if logs.empty:
                st.info("No outlier columns have been added yet. Please add outlier columns to remove them.")
            else:
                 # add new new column combine index, search_type and pattern
                logs["index"] = logs.index.astype(str) + " - " + logs["search_type"] + " - " + logs["pattern"].fillna("")

                # get unique values in index
                unique_index = logs["index"].unique().tolist()

                selected_index = st.selectbox(label="Select outlier column to remove",
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

        outlier_logs = duckdb_get_table(project_id=project_id, alias=f"outliers_setting_logs_{label}",
        db_name="logs",).to_pandas()

        if outlier_logs.empty:
            st.info("No outlier columns have been added yet. Please add outlier columns to see the settings.")

        else:
            st.dataframe(outlier_logs, use_container_width=True, hide_index=False,column_config={
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
            })
    return (
        outlier_display_cols,
        min_threshold,
        survey_id,
        survey_key,
        enumerator
    )

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
                df[col] = pd.to_numeric(df[col], errors='raise')
            except ValueError:
                raise ValueError(f"Column '{col}' cannot be converted to numeric type.")  # noqa: B904

    # Stack the specified columns into a single column
    stacked_values = df[col_names].stack()

    return stacked_values.reset_index(drop=True)

@st.cache_data
def compute_outlier_stats(series: pd.Series, outlier_type: str | None, multiplier: float | None) -> dict:
    """Compute outlier statistics for a given Series.
    Args:
        series (pd.Series): The Series to compute statistics for.
        outlier_type (str | None): The type of outlier detection method to use. Options 
        are "sd" for standard deviation or "iqr" for interquartile range.
        multiplier (float | None): The multiplier to use for outlier detection. If None, 
        defaults to 3 for standard deviation and 1.5 for IQR.

    Returns
    -------
        dict: A dictionary containing the computed statistics including mean, median, 
        standard deviation, lower bound, and upper bound.
    """
    if series.empty:
        raise ValueError("The Series is empty.")

    if outlier_type not in [None, "Interquartile Range (IQR)", "Standard Deviation (SD)"]:
        raise ValueError("Invalid outlier type. Use 'sd' or 'iqr'.")

    if multiplier is not None and multiplier <= 0:
        raise ValueError("Multiplier must be a positive number.")

    mean = series.mean()
    median = series.median()
    sd = series.std()

    if outlier_type in "Standard Deviation (SD)":
        if not multiplier:
            multiplier = 3.0 # default to 3 standard deviations
        lower_bound = mean - (multiplier * sd)
        upper_bound = mean + (multiplier * sd)
    elif outlier_type in [None, "Interquartile Range (IQR)"]: # default to IQR if not specified
        if not multiplier:
            multiplier = 1.5 # default to 1.5 IQR
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - (multiplier * iqr)
        upper_bound = q3 + (multiplier * iqr)

    return {
        "mean": mean,
        "median": median,
        "sd": sd,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound
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
    for col in (display_cols or []):
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
        outlier_df = df[[survey_key] + outlier_cols].copy(deep=True)

        if min_threshold is None:
            min_threshold = 20 if outlier_method == "Interquartile Range (IQR)" else 30

        if len(outlier_cols) == 1:
            # count the number of non-null values in the column
            non_null_count = outlier_df[outlier_cols[0]].count()

            # compute outlier stats for the single column
            outlier_stats = compute_outlier_stats(outlier_df[outlier_cols[0]],
                                                  outlier_type=outlier_method,
                                                  multiplier=outlier_multiplier)
        else:
            if grouped_cols:
                # stack cols
                stacked_series = stack_outlier_columns(
                    outlier_df, outlier_cols
                )
                # count the number of non-null values in the stacked series
                non_null_count = stacked_series.count()

                # compute outlier stats for the stacked series
                outlier_stats = compute_outlier_stats(
                    stacked_series,
                    outlier_type=outlier_method,
                    multiplier=outlier_multiplier,
                )
            else:
                non_null_count = None

        for col in outlier_cols:
            if not grouped_cols:
                non_null_count = outlier_df[col].count()

            if non_null_count < min_threshold:
                # skip columns with less than the minimum threshold of non-null values
                continue

            # compute outlier stats for each column if not grouped
            if not grouped_cols:
                outlier_stats = compute_outlier_stats(
                    outlier_df[col],
                    outlier_type=outlier_method,
                    multiplier=outlier_multiplier,
                )

            # add new column showing reason for flag
            def add_outlier_reason(value, soft_min, soft_max, outlier_stats):
                """Add a reason for outlier based on the value and
                outlier statistics.
                """
                if value < outlier_stats["lower_bound"]:
                    return f"Value is below lower bound {outlier_stats['lower_bound']:.2f}"
                elif value > outlier_stats["upper_bound"]:
                    return f"Value is above upper bound {outlier_stats['upper_bound']:.2f}"
                else:
                    if soft_min is not None and value < soft_min:
                        return f"Value is below soft minimum {soft_min:.2f}"
                    elif soft_max is not None and value > soft_max:
                        return f"Value is above soft maximum {soft_max:.2f}"
                    else:
                        return "no outlier" # return empty string if no reason

            # apply the function to the column to create a new column for outlier reason
            outlier_df["outlier reason"] = outlier_df[col].apply(
                lambda x, soft_min = soft_min, soft_max = soft_max, outlier_stats = outlier_stats: add_outlier_reason(
                    x, soft_min, soft_max, outlier_stats
                )
            )

            # count the number of outliers in the column
            outlier_count = outlier_df[outlier_df["outlier reason"] != "no outlier"].shape[0]

            if outlier_count > 0:

                # Filter out non-outliers
                outlier_df = outlier_df[outlier_df["outlier reason"] != "no outlier"].copy()

                # Assign variable name and rename value column
                outlier_df["variable"] = col
                outlier_df = outlier_df.rename(columns={col: "value"})

                # Prepare stats columns to add
                stats_map = {
                    "mean": outlier_stats.get("mean", None),
                    "std": outlier_stats.get("sd", None),
                    "lower_bound": outlier_stats.get("lower_bound", None),
                    "upper_bound": outlier_stats.get("upper_bound", None),
                    "outlier_method": outlier_method,
                    "outlier_multiplier": outlier_multiplier,
                    "soft_min": soft_min,
                    "soft_max": soft_max,
                }
                for k, v in stats_map.items():
                    outlier_df[k] = v

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

    return merged_results[merged_results["value"].notnull()]


def display_outlier_output(project_id: str,
                           label: str,
                           display_cols: list | None,
                           min_threshold: int,
                           survey_key: str,
                           survey_id: str, enumerator: str) -> None:
    """Display the outlier output in a Streamlit app.

    Args:
        project_id (str): Project ID for the DuckDB database.
        label (str): Label for the outlier settings.

    Returns
    -------
        None
    """
    # Get the outlier settings from the database
    outlier_settings = duckdb_get_table(
        project_id=project_id,
        alias=f"outliers_setting_logs_{label}",
        db_name="logs",
    ).to_pandas()

    data = duckdb_get_table(
        project_id=project_id,
        alias=f"outliers_data_{label}",
        db_name="data",
    ).to_pandas()

    outlier_data = compute_outlier_output(
        df=data,
        outlier_settings=outlier_settings,
        display_cols= display_cols,
        min_threshold=min_threshold,
        survey_key=survey_key,
        survey_id=survey_id,
        enumerator=enumerator,
    )

    if outlier_data.empty:
        st.info("No outliers detected in the selected columns.")
        return
    else:
        st.dataframe(outlier_data, use_container_width=True, hide_index=True,
            column_config={
                "variable": st.column_config.Column("Variable"),
                "value": st.column_config.NumberColumn(
                    "Value", format="%.2f", width="small"
                ),
                "mean": st.column_config.NumberColumn(
                    "Mean", format="%.2f", width="small"
                ),
                "std": st.column_config.NumberColumn(
                    "Standard Deviation", format="%.2f", width="small"
                ),
                "lower_bound": st.column_config.NumberColumn(
                    "Lower Bound", format="%.2f", width="small"
                ),
                "upper_bound": st.column_config.NumberColumn(
                    "Upper Bound", format="%.2f", width="small"
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


# plot outlier distribution
@st.cache_data
def plot_outlier_distributions(
    data, outliers_summary: pd.DataFrame, cols: list
) -> None:
    """Plot distribution of outliers for selected columns.

    Args:
        data: DataFrame containing the survey data
        outliers_summary: DataFrame containing the outlier summary
        cols: List of columns to plot distributions for

    Returns
    -------
        None
    """
    if outliers_summary.empty or data.empty or cols is None:
        return
    no_outlier_vars = []
    for var in cols:
        if var in outliers_summary["variable"].values:
            col1, col2 = st.columns([4, 1], vertical_alignment="center")
            with col1:
                fig = create_violin_plot(data[var], var)
                st.plotly_chart(fig, use_container_width=True)
            with col2:
                outlier_pct = (
                    len(outliers_summary[outliers_summary["variable"] == var])
                    / data[var].count()
                    * 100
                )
                st.metric(value=f"{outlier_pct:.2f}%", label="Share of outliers")
        else:
            no_outlier_vars.append(var)

    if no_outlier_vars:
        st.write(
            "No outliers detected for the following variables according to the selected method and threshold"
        )
        # Split the list into chunks of 3
        n = 3
        no_outliers_vars_list = [
            no_outlier_vars[i : i + n] for i in range(0, len(no_outlier_vars), n)
        ]
        no_outliers_df = pd.DataFrame(no_outliers_vars_list).fillna("")
        st.dataframe(
            no_outliers_df,
            hide_index=True,
            use_container_width=True,
        )


# Function to display outlier metrics
@st.cache_data
def display_outlier_metrics(
    outliers_summary: pd.DataFrame, outlier_cols: list | None, enumerator: str | None
) -> None:
    """Display metrics related to outliers in a summary format.
    Args:
    outliers_summary (pd.DataFrame): DataFrame containing outlier summary.
    outlier_cols (list): List of columns checked for outliers.
    enumerator (str): Column name for enumerator ID.
    """
    st.markdown("## Outliers Overview")
    if not outlier_cols:
        st.info(
            "Outlier columns are required to display metrics. Go to the :material/settings: settings section above to select columns."
        )
        return
    col1, col2, col3, col4 = st.columns(spec=4, border=True)

    cols_checked_outliers = len(outlier_cols)
    total_outliers = len(outliers_summary)
    at_least_one_outlier = (
        outliers_summary["variable"].nunique() if not outliers_summary.empty else 0
    )
    total_enumerators = (
        outliers_summary[enumerator].nunique()
        if enumerator and not outliers_summary.empty
        else 0
    )

    col1.metric(
        label="Variables checked",
        value=f"{cols_checked_outliers}",
        help="Columns checked for outlier values",
    )

    col2.metric(
        label="Outlier variables",
        value=f"{at_least_one_outlier}",
        help="Variables with at least one outlier",
    )

    col3.metric(
        label="Number of outliers",
        value=f"{total_outliers}",
        help="Total number of identified outliers",
    )

    if enumerator:
        col4.metric(
            label="Number of enumerators",
            value=f"{total_enumerators}",
            help="Number of enumerators with outliers flagged",
        )
    else:
        with col4:
            st.write("Number of enumerators")
            st.info(
                "Enumerator column is not selected. Go to the :material/settings: settings section above to select the enumerator column."
            )

    # Display the outliers summary table
    if not outliers_summary.empty:
        cmap = sns.light_palette("pink", as_cmap=True)

        num_cols = ["value", "mean", "std", "lower_bound", "upper_bound"]
        outliers_summary = outliers_summary.style.format(
            subset=num_cols, formatter="{:,.2f}"
        ).background_gradient(subset=num_cols, cmap=cmap)
        st.dataframe(outliers_summary, use_container_width=True, hide_index=True)

    else:
        st.success("No outliers detected in the selected variables.")


# Function to find the common prefix
def common_prefix(strs):
    """Find the longest common prefix string amongst an array
    of strings.

    Args:
        strs (list): List of strings.

    Returns
    -------
        str: The longest common prefix.

    """
    if not strs:
        return ""
    prefix = strs[0]
    for s in strs[1:]:
        while not s.startswith(prefix):
            prefix = prefix[:-1]
            if not prefix:
                return ""
    return prefix


# Function to calculate joint outlier distribution
@st.cache_data
def compute_joint_outlier_distribution(
    data, selected_cols, survey_id, outlier_method, iqr_value, sd_value
) -> pd.DataFrame:
    """
    Calculate the joint outlier distribution for a set of selected columns using the
    specified outlier detection method.

    Args:
        data (pd.DataFrame): Melted DataFrame containing the variables to analyze.
        selected_cols (list): List of selected variable columns.
        survey_id (str): Column name for survey ID.
        outlier_method (str): Outlier detection method ("Interquartile Range (IQR)" or
        "Standard Deviation (SD)").
        iqr_value (float): IQR multiplier for IQR method.
        sd_value (float): Number of standard deviations for SD method.

    Returns
    -------
        pd.DataFrame: DataFrame containing outlier joint outlier distribution.
    """
    series = data["new_var"].dropna()

    if outlier_method == "Interquartile Range (IQR)":
        Q1 = series.quantile(0.25)
        Q3 = series.quantile(0.75)
        IQR = Q3 - Q1
        lower_bound = Q1 - iqr_value * IQR
        upper_bound = Q3 + iqr_value * IQR
    else:
        mean = series.mean()
        std_dev = series.std()
        lower_bound = mean - sd_value * std_dev
        upper_bound = mean + sd_value * std_dev

    outliers = series[(series < lower_bound) | (series > upper_bound)]
    outliers_df = data[data["new_var"].isin(outliers)]

    table_data = outliers_df[[survey_id, "name_variable"]].copy()
    table_data["new_var"] = outliers_df["new_var"].round(2)
    table_data["mean"] = round(series.mean(), 2)
    table_data["lower_bound"] = round(lower_bound, 2)
    table_data["upper_bound"] = round(upper_bound, 2)

    return table_data, outliers_df


# display joint outlier distribution summary
@st.cache_data
def display_joint_outlier_summary(joint_outlier_summary):
    """Display the joint outlier distribution summary.
    Args:
        joint_outlier_summary (pd.DataFrame): DataFrame containing
        joint outlier summary.
    """
    st.subheader("Joint Outlier Distribution")
    st.dataframe(
        joint_outlier_summary,
        hide_index=True,
        use_container_width=True,
        column_config={
            "id": st.column_config.Column("ID", width="small"),
            "name_variable": st.column_config.Column("Variable Name"),
            "new_var": st.column_config.NumberColumn(
                "Value", format="%.2f", width="small"
            ),
            "mean": st.column_config.NumberColumn("Mean", format="%.2f", width="small"),
            "lower_bound": st.column_config.NumberColumn(
                "Lower Bound", format="%.2f", width="small"
            ),
            "upper_bound": st.column_config.NumberColumn(
                "Upper Bound", format="%.2f", width="small"
            ),
        },
    )


# calculate joint outliers metrics
@st.cache_data
def calculate_joint_outliers_percentage(
    outliers_df: pd.DataFrame, selected_cols: list
) -> tuple:
    """
    Calculate metrics for joint outliers.

    Args:
        outliers_df (pd.DataFrame): DataFrame containing outlier data.
        selected_cols (list): List of selected variable columns.

    Returns
    -------
        tuple: A tuple containing the number of outliers, total count,
        and percentage of outliers.
    """
    if outliers_df.empty:
        return "0.00%"

    outlier_count = len(outliers_df)
    total_count = len(outliers_df[selected_cols].dropna())
    outlier_percentage = (outlier_count / total_count) * 100 if total_count > 0 else 0.0
    formatted_outlier_percentage = f"{outlier_percentage:.2f}%"

    return formatted_outlier_percentage


# plot joint outliers distribution
def plot_joint_outliers_distribution(reshaped_joint_outliers_df, selected_cols):
    """Plot the joint outliers distribution for selected columns.
    Args:
        reshaped_joint_outliers_df (pd.DataFrame): Melted DataFrame
        containing the variables to analyze.
        selected_cols (list): List of selected variable columns.
    """
    # Get common prefix
    x_axis_label = common_prefix(selected_cols)

    fig = go.Figure(
        data=go.Violin(
            y=reshaped_joint_outliers_df["new_var"],
            box_visible=True,
            line_color="black",
            meanline_visible=True,
            fillcolor="forestgreen",
            opacity=0.6,
            x0=x_axis_label,
        )
    )

    st.plotly_chart(fig, theme="streamlit", use_container_width=True)


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

    label = current_pages_df.iloc[page_num-1]["page_name"]

    # outliers settings
    (
        display_cols,
        min_threshold,
        survey_id,
        survey_key,
        enumerator,
    ) = outliers_report_settings(project_id, data, setting_file, page_num, label)

    # display outlier output
    display_outlier_output(
        project_id=project_id,
        label=label,
        display_cols=display_cols,
        min_threshold=min_threshold,
        survey_key=survey_key,
        survey_id=survey_id,
        enumerator=enumerator,
    )
