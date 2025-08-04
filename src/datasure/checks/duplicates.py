import os

import pandas as pd
import streamlit as st

from datasure.utils import (
    get_check_config_settings,
    get_df_info,
    load_check_settings,
    save_check_settings,
    trigger_save,
)


# @st.cache_data
def load_default_duplicates_settings(
    project_id: str, setting_file: str, page_num: int
) -> tuple:
    """
    Load default settings for duplicates report from a settings file.

    Parameters
    ----------
        settings_file (str): The path to the settings file.

    Returns
    -------
        dict: A dictionary containing the default settings for duplicates report.
    """
    # Get config page defaults
    _, _, config_survey_key, config_survey_id, config_survey_date, _, _, _ = (
        get_check_config_settings(
            project_id=project_id,
            page_row_index=page_num - 1,
        )
    )
    # load default settings in the following order:
    # - if settings file exists, load settings from file
    # - if settings file does not exist, load default settings from config

    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(setting_file, "duplicates") or {}
    else:
        default_settings = {}

    default_survey_id = default_settings.get("survey_id", config_survey_id)
    default_survey_key = default_settings.get("survey_key", config_survey_key)
    default_date = default_settings.get("date", config_survey_date)
    default_dup_cols = default_settings.get("dup_cols")
    default_display_cols = default_settings.get("display_cols")

    return (
        default_survey_id,
        default_survey_key,
        default_date,
        default_dup_cols,
        default_display_cols,
    )


def duplicates_settings(
    project_id: str, data: pd.DataFrame, settings_file: str, page_num: int
) -> tuple:
    """
    Get the settings for duplicates report

    Parameters
    ----------
        data (pd.DataFrame): The dataset to generate the duplicate data report for.
        settings_file (str): The path to the settings file.
        page_num (int): The page number of the current report.

    Returns
    -------
            tuple: A tuple containing the survey ID, survey key, date, and columns to
            check for duplicates.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for survey duplicates report")

        st.write("---")

        id_col, key_col, date_col = st.columns(3)

        survey_id, survey_key, date, dup_cols, display_cols = (
            load_default_duplicates_settings(project_id, settings_file, page_num)
        )

        all_cols, string_columns, numeric_columns, datetime_columns, _ = get_df_info(
            data, cols_only=True
        )

        id_key_cols = numeric_columns + string_columns

        with id_col:
            survey_id_index = (
                id_key_cols.index(survey_id)
                if survey_id and survey_id in id_key_cols
                else None
            )
            survey_id = st.selectbox(
                label="Survey ID",
                options=id_key_cols,
                key="survey_id_duplicates_key",
                index=survey_id_index,
            )

        with key_col:
            survey_key_index = (
                id_key_cols.index(survey_key)
                if survey_key and survey_key in id_key_cols
                else None
            )
            survey_key = st.selectbox(
                label="Survey Key",
                options=id_key_cols,
                key="survey_key_duplicates_key",
                index=survey_key_index,
                on_change=trigger_save,
                kwargs={"state_name": "duplicates_key_save"},
            )
            if (
                "duplicates_key_save" in st.session_state
            ) and st.session_state.duplicates_key_save:
                save_check_settings(
                    settings_file=settings_file,
                    check_name="duplicates",
                    check_settings={"survey_key": survey_key},
                )
                st.session_state["duplicates_key_save"] = False

        with date_col:
            date_index = (
                datetime_columns.index(date)
                if date and date in datetime_columns
                else None
            )
            date = st.selectbox(
                label="Date",
                options=datetime_columns,
                key="date_duplicates_key",
                index=date_index,
                on_change=trigger_save,
                kwargs={"state_name": "duplicates_date_save"},
            )

        default_dup_cols = (
            [col for col in dup_cols if col in all_cols] if dup_cols else None
        )

        dup_cols = st.multiselect(
            label="Columns",
            options=all_cols,
            key="dup_cols_key",
            default=default_dup_cols,
            on_change=trigger_save,
            kwargs={"state_name": "dup_cols_save"},
        )
        if ("dup_cols_save" in st.session_state) and st.session_state.dup_cols_save:
            save_check_settings(
                settings_file=settings_file,
                check_name="duplicates",
                check_settings={"dup_cols": dup_cols},
            )
            st.session_state["dup_cols_save"] = False

    return survey_id, survey_key, date, dup_cols, display_cols


@st.cache_data
def compute_duplicates_statistics(
    data: pd.DataFrame, survey_id: str | None, dup_cols: list
) -> tuple:
    """
    Compute statistics for duplicates in the dataset.

    Parameters
    ----------
        data (pd.DataFrame): The dataset to compute duplicates statistics for.
        survey_id (str): The survey ID column name.
        survey_key (str): The survey key column name.
        dup_cols (list): The columns to check for duplicates.

    Returns
    -------
        tuple: A tuple containing the total number of columns checked, the number of
        columns with duplicates, the number of columns without duplicates, total number
            of duplicates
        total number of ID duplicates and total number of duplicates resolved.
        id_duplicates_data (pd.DataFrame): A DataFrame containing the duplicate entries
          for the survey ID.
        all_duplicates_data (pd.DataFrame): A DataFrame containing the duplicate entries
          for the selected columns.
    """
    total_cols_checked = len(dup_cols)
    cols_with_dups = [x for x in dup_cols if data[x].duplicated().any()]
    total_cols_with_dups = len(cols_with_dups)
    total_cols_no_dups = total_cols_checked - total_cols_with_dups
    if survey_id:
        id_dups_data = data[data.duplicated(subset=[survey_id], keep=False)]
        total_id_dups = len(id_dups_data)
    else:
        id_dups_data, total_id_dups = pd.DataFrame(), 0

    total_resolved_dups = st.session_state.get("resolved_duplicates", 0)
    total_dups = 0
    for col in dup_cols:
        if data[col].duplicated().any():
            col_dups_data = data[data.duplicated(subset=[col], keep=False)]
            total_dups += len(col_dups_data)

    return (
        total_cols_checked,
        total_cols_with_dups,
        total_cols_no_dups,
        total_dups,
        total_id_dups,
        total_resolved_dups,
    )


def display_duplicates_statistics(
    data: pd.DataFrame, survey_id: str, dup_cols: list
) -> None:
    """
    Display an overview of duplicates statistics in the dataset.

    Parameters
    ----------
        data (pd.DataFrame): The dataset to display duplicates statistics for.
        survey_id (str): The survey ID column name.
        survey_key (str): The survey key column name.
        dup_cols (list): The columns to check for duplicates.

    Returns
    -------
        None
    """
    st.markdown("## Duplicates Statistics Overview")
    if not (any([survey_id, dup_cols])):
        st.info(
            "Duplicates statistics requires a survey ID column or at least one column to check for duplicates. Go to :material/settings: settings to select a survey ID column and columns to check for duplicates."
        )
        return
    (
        total_cols_checked,
        total_cols_with_dups,
        total_cols_no_dups,
        total_dups,
        total_id_dups,
        total_resolved_dups,
    ) = compute_duplicates_statistics(data=data, survey_id=survey_id, dup_cols=dup_cols)
    _, gc2 = st.columns(2)
    with gc2:
        tc3, tc4 = st.columns(2, border=True)
        tc3.metric(
            label="Total Duplicates",
            value=total_dups,
            help="Total number of duplicates in the dataset",
        )
        tc4.metric(
            label="Resolved Duplicates",
            value=total_resolved_dups,
            help="Total number of duplicates resolved",
        )

    bc1, bc2, bc3, bc4 = st.columns(4, border=True)
    bc1.metric(
        label="Columns Checked",
        value=total_cols_checked,
        help="Total number of columns checked for duplicates",
    )
    bc2.metric(
        label="Columns With No Duplicates",
        value=total_cols_no_dups,
        help="Total number of columns with no duplicates",
    )
    bc3.metric(
        label="Columns With Duplicates",
        value=total_cols_with_dups,
        help="Total number of columns with duplicates",
    )
    bc4.metric(
        label="Survey ID Duplicates",
        value=total_id_dups,
        help="Total number of duplicates in the survey ID column",
    )


@st.cache_data
def compute_id_duplicates(
    data: pd.DataFrame,
    survey_id: str,
    survey_date: str | None,
    survey_key: str,
    display_cols: list | None,
) -> pd.DataFrame:
    """
    Compute duplicates for the survey ID column.

    Parameters
    ----------
        data (pd.DataFrame): The dataset to compute duplicates for.
        survey_id (str): The

    Returns
    -------
        pd.DataFrame: A DataFrame containing the duplicate entries for the survey ID.
    """
    id_dups_data = data.copy(deep=True)
    id_dups_data = id_dups_data[id_dups_data.duplicated(subset=[survey_id], keep=False)]
    id_dups_data["id_dup_count"] = id_dups_data.groupby(survey_id)[survey_id].transform(
        "count"
    )
    id_dups_data["id_dup_percent"] = (id_dups_data["id_dup_count"] / len(data)) * 100

    # default survey date to None if not provided
    survey_date = [] if survey_date is None else [survey_date]

    if display_cols:
        if survey_date:
            display_cols = survey_date + display_cols

        # remove any duplicate columns from display_cols
        display_cols = list(set(display_cols))
        id_dups_data.merge(
            data[[survey_key] + display_cols],
            on=survey_key,
            how="left",
        )
        id_dups_data = id_dups_data[
            [survey_id, survey_key, survey_date, "id_dup_count", "id_dup_percent"]
            + display_cols
            if survey_date
            else [survey_id, survey_key, "id_dup_count", "id_dup_percent"]
            + display_cols
        ]
    else:
        id_dups_data = (
            id_dups_data[
                [
                    survey_id,
                    survey_key,
                    survey_date[0],
                    "id_dup_count",
                    "id_dup_percent",
                ]
            ]
            if survey_date
            else id_dups_data[[survey_id, survey_key, "id_dup_count", "id_dup_percent"]]
        )
    return id_dups_data.sort_values(
        [survey_id, "id_dup_count"], ascending=[False, True]
    )


def display_id_duplicates(
    data: pd.DataFrame,
    survey_id: str | None,
    survey_date: str | None,
    survey_key: str,
    setting_file: str,
) -> None:
    """
    Display duplicates for the survey ID column.

    Parameters
    ----------
        data (pd.DataFrame): The dataset to compute duplicates for.
        survey_id (str): survey ID column name.
        survey_key (str): survey key column name.

    Returns
    -------
        None

    """
    if not survey_id:
        st.markdown("## Duplicate Entries Survey ID")
        st.info(
            "Duplicate entries for survey ID requires a survey ID column to be selected. Go to :material/settings: settings to select a survey ID column."
        )
        return
    # Load settings from file if it exists
    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(setting_file, "duplicates") or {}
    else:
        default_settings = {}
    display_cols = default_settings.get("id_display_cols")
    display_col_options = [
        col for col in data.columns if col not in [survey_id, survey_key, survey_date]
    ]
    display_cols = st.multiselect(
        label="Select columns to display in the report",
        options=display_col_options,
        default=display_cols,
        key="display_id_cols_duplicates",
        on_change=trigger_save,
        kwargs={"state_name": "display_id_cols_duplicates_save"},
    )
    if (
        "display_id_cols_duplicates_save" in st.session_state
    ) and st.session_state.display_id_cols_duplicates_save:
        save_check_settings(
            settings_file=setting_file,
            check_name="duplicates",
            check_settings={"id_display_cols": display_cols},
        )
        st.session_state["display_id_cols_duplicates_save"] = False

    id_dups_data = compute_id_duplicates(
        data=data,
        survey_id=survey_id,
        survey_date=survey_date,
        survey_key=survey_key,
        display_cols=display_cols,
    )

    if id_dups_data.empty:
        st.write(f"No duplicates found for {survey_id}")
    else:
        st.dataframe(
            id_dups_data,
            hide_index=True,
            use_container_width=True,
            column_config={
                "id_dup_count": st.column_config.Column(
                    label=f"# of {survey_id} duplicates"
                ),
                "id_dup_percent": st.column_config.NumberColumn(
                    label="% of total records", format="%.2f%%"
                ),
            },
        )


@st.cache_data
def compute_column_duplicates(
    data: pd.DataFrame,
    survey_id: str,
    survey_key: str,
    survey_date: str,
    dup_col: list,
    display_cols,
) -> pd.DataFrame:
    """
    Compute duplicates for the selected columns.

    Parameters
    ----------
        data (pd.DataFrame): The dataset to compute duplicates for.
        survey_id (str): The survey ID column name.
        survey_key (str): The survey key column name.
        dup_col (list): The columns to check for duplicates.
        display_cols (list): The columns to display in the report.

    Returns
    -------
        pd.DataFrame: A DataFrame containing the duplicate entries for the selected
        columns.
    """
    var_dups_data = data[data.duplicated(subset=[dup_col], keep=False)]
    var_dups_data[f"{dup_col}_dup_count"] = var_dups_data.groupby(dup_col)[
        dup_col
    ].transform("count")
    var_dups_data[f"{dup_col}_dup_percent"] = (
        var_dups_data[f"{dup_col}_dup_count"] / len(data)
    ) * 100

    # get a list of vars that exist
    existing_vars = [
        col for col in ["survey_id", "survey_date"] if col in globals() and col
    ]

    # Add user-selected display columns (if any). Join to duplicates data
    # using survey_key
    if display_cols:
        var_dups_data.merge(
            data[[survey_key] + display_cols],
            on=survey_key,
            how="left",
        )
        var_dups_data = var_dups_data[
            existing_vars
            + [
                dup_col,
                f"{dup_col}_dup_count",
                f"{dup_col}_dup_percent",
            ]
            + display_cols
        ]
    else:
        var_dups_data = var_dups_data[
            existing_vars
            + [
                dup_col,
                f"{dup_col}_dup_count",
                f"{dup_col}_dup_percent",
            ]
        ]
    return var_dups_data.sort_values(
        [f"{dup_col}_dup_count", dup_col], ascending=[False, True]
    )


def display_column_duplicates(
    data: pd.DataFrame,
    survey_id: str | None,
    survey_key: str,
    survey_date: str | None,
    dup_cols: str | None,
    setting_file: str,
) -> None:
    """
    Display duplicates for the selected columns.

    Parameters
    ----------
        data (pd.DataFrame): The dataset to compute duplicates for.
        survey_id (str): survey ID column name.
        survey_key (str): survey key column name.
        dup_col (list): The columns to check for duplicates.

    Returns
    -------
        None

    """
    st.markdown("## Duplicate Entries for columns")
    if not dup_cols:
        st.info(
            "Duplicate entries for columns requires at least one column to be selected. Go to :material/settings: settings to select columns to check for duplicates."
        )
        return

    # load settings from file if it exists
    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(setting_file, "duplicates") or {}
    else:
        default_settings = {}
    dup_col = default_settings.get("dup_col")
    dup_col_index = dup_cols.index(dup_col) if dup_col and dup_col in dup_cols else 0
    display_cols = default_settings.get(f"{dup_col}/display_cols") if dup_col else None
    # make a list of columns with at least one duplicate
    dup_cols_with_dups = [col for col in dup_cols if data[col].duplicated().any()]
    dup_cols_without_dups = [col for col in dup_cols if col not in dup_cols_with_dups]
    if len(dup_cols_with_dups) == 0:
        st.info(
            body="No columns with duplicates found. Please select a column to check for duplicates.",
            icon=":material/info:",
        )
        return
    elif len(dup_cols_without_dups) > 0:
        st.info(
            body=f"The following {dup_cols_without_dups} columns have no duplicates.",
            icon=":material/info:",
        )
    dup_col = st.selectbox(
        label="Select column to check for duplicates",
        options=dup_cols_with_dups,
        key="dup_col_duplicates",
        index=dup_col_index,
        on_change=trigger_save,
        kwargs={"state_name": "dup_col_duplicates_save"},
    )
    if (
        "dup_col_duplicates_save" in st.session_state
    ) and st.session_state.dup_col_duplicates_save:
        save_check_settings(
            settings_file=setting_file,
            check_name="duplicates",
            check_settings={"dup_col": dup_col},
        )
        st.session_state["dup_col_duplicates_save"] = False

    display_cols_options = [
        col
        for col in data.columns
        if col not in [survey_id, survey_key, survey_date, dup_col]
    ]
    display_cols = st.multiselect(
        label="Select columns to display in the report",
        options=display_cols_options,
        default=display_cols,
        key="display_cols_duplicates",
        on_change=trigger_save,
        kwargs={"state_name": "display_cols_duplicates_save"},
    )
    if (
        "display_cols_duplicates_save" in st.session_state
    ) and st.session_state.display_cols_duplicates_save:
        save_check_settings(
            settings_file=setting_file,
            check_name="duplicates",
            check_settings={f"{dup_col}/display_cols": display_cols},
        )
        st.session_state["display_cols_duplicates_save"] = False

    if dup_col:
        col_dups_data = compute_column_duplicates(
            data=data,
            survey_id=survey_id,
            survey_key=survey_key,
            survey_date=survey_date,
            dup_col=dup_col,
            display_cols=display_cols,
        )

        if col_dups_data.empty:
            st.write(f"No duplicates found for {dup_col}")
        else:
            st.dataframe(
                col_dups_data,
                hide_index=True,
                use_container_width=True,
                column_config={
                    f"{dup_col}_dup_count": st.column_config.Column(
                        label="# duplicates"
                    ),
                    f"{dup_col}_dup_percent": st.column_config.NumberColumn(
                        label="% duplicates", format="%.2f%%"
                    ),
                },
            )
    else:
        st.info(
            body="Please select a column to check for duplicates",
            icon=":material/info:",
        )


# define function to create duplicates report
def duplicates_report(
    project_id: str, data: pd.DataFrame, setting_file: str, page_num: int
) -> None:  # noqa: D417, RUF100
    """
    Generate a report on duplicate data in the dataset. The report includes a
    summary of duplicate data, a table showing the number of duplicate rows, and
    an option to inspect duplicate rows.


    Parameters
    ----------
        data (pd.DataFrame): The dataset to generate the duplicate data
                report for.


    Returns
    -------
        None


    """
    survey_id, survey_key, date, dup_cols, _ = duplicates_settings(
        project_id, data, setting_file, page_num
    )

    # ---- Show report --- #

    display_duplicates_statistics(
        data=data,
        survey_id=survey_id,
        dup_cols=dup_cols,
    )

    st.write("---")
    display_id_duplicates(
        data=data,
        survey_id=survey_id,
        survey_date=date,
        survey_key=survey_key,
        setting_file=setting_file,
    )

    st.write("---")
    display_column_duplicates(
        data=data,
        survey_id=survey_id,
        survey_key=survey_key,
        survey_date=date,
        dup_cols=dup_cols,
        setting_file=setting_file,
    )
