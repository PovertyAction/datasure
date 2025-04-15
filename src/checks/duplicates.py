import os

import pandas as pd
import streamlit as st

from src.utils import load_check_settings, save_check_settings


def load_default_duplicates_settings(setting_file: str, page_num: int) -> tuple:
    """
    Load default settings for duplicates report from a settings file.

    Parameters
    ----------
        settings_file (str): The path to the settings file.

    Returns
    -------
        dict: A dictionary containing the default settings for duplicates report.
    """
    # load default settings in the following order:
    # - if settings file exists, load settings from file
    # - if settings file does not exist, load default settings from config

    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(setting_file, "duplicates")
        if default_settings:
            default_survey_id = default_settings.get("survey_id")
            default_survey_key = default_settings.get("survey_key")
            default_date = default_settings.get("date")
            default_dup_cols = default_settings.get("dup_cols")
            default_display_cols = default_settings.get("display_cols")
        else:
            default_survey_id = st.session_state["config_pages"]["Survey ID"][
                page_num - 1
            ]
            default_survey_key = st.session_state["config_pages"]["Survey KEY"][
                page_num - 1
            ]
            default_date = st.session_state["config_pages"]["Survey Date"][page_num - 1]
            default_dup_cols = None
            default_display_cols = None

    else:
        default_survey_id = st.session_state["config_pages"]["Survey ID"][page_num - 1]
        default_survey_key = st.session_state["config_pages"]["Survey KEY"][
            page_num - 1
        ]
        default_date = st.session_state["config_pages"]["Survey Date"][page_num - 1]
        default_dup_cols = None
        default_display_cols = None

    return (
        default_survey_id,
        default_survey_key,
        default_date,
        default_dup_cols,
        default_display_cols,
    )


def duplicates_settings(data: pd.DataFrame, settings_file: str, page_num: int) -> tuple:
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

        survey_cols = data.columns.to_list()

        st.write("---")

        id_col, key_col, date_col = st.columns(3)

        survey_id, survey_key, date, dup_cols, display_cols = (
            load_default_duplicates_settings(
                setting_file=settings_file, page_num=page_num
            )
        )

        with id_col:
            survey_id_index = survey_cols.index(survey_id) if survey_id else 0
            st.markdown("### Select survey ID column")
            survey_id = st.selectbox(
                label="Survey ID",
                options=survey_cols,
                key="survey_id_duplicates_key",
                index=survey_id_index,
            )

        with key_col:
            survey_key_index = survey_cols.index(survey_key) if survey_key else None
            st.markdown("### Select survey key column")
            survey_key = st.selectbox(
                label="Survey Key",
                options=survey_cols,
                key="survey_key_duplicates_key",
                index=survey_key_index,
            )

        with date_col:
            st.markdown("### Select date column")
            date_index = survey_cols.index(date) if date else None
            date = st.selectbox(
                label="Date",
                options=survey_cols,
                key="date_duplicates_key",
                index=date_index,
            )

        st.markdown("### Select columns to check for duplicates")
        dup_cols = st.multiselect(
            label="Columns",
            options=survey_cols,
            key="dup_cols_key",
            default=dup_cols,
        )

        st.write("---")
        st.markdown("### Report options")

        st.markdown("### Select additional columns to display in the report")
        display_cols = st.multiselect(
            label="Columns",
            options=survey_cols,
            key="display_cols_key",
            default=display_cols,
        )

        # add button for saving settings
        st.write("---")
        st.write("Save settings")
        st.button(
            label="Save settings",
            key="save_settings_duplicates",
            on_click=save_check_settings,
            args=(
                settings_file,
                "duplicates",
                {
                    "survey_id": survey_id,
                    "survey_key": survey_key,
                    "date": date,
                    "dup_cols": dup_cols,
                    "display_cols": display_cols,
                },
            ),
        )

    return survey_id, survey_key, date, dup_cols, display_cols


# define function to create duplicates report
def duplicates_report(data: pd.DataFrame, setting_file: str, page_num: int) -> None:  # noqa: D417, RUF100
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
    survey_id, survey_key, date, dup_cols, display_cols = duplicates_settings(
        data, settings_file=setting_file, page_num=page_num
    )

    # ---- Show report --- #
    # Check that required options have been selected. If not, display a info message
    # Modified to always allow survey_id, survey_key, and date to be processed
    if not all([survey_id, survey_key, date]):
        st.info(
            body="Please select all required options to generate the progress report",
            icon=":material/info:",
        )
        return

    # Add CSS for consistent width
    st.markdown(
        """
        <style>
            .stDataFrame {
                width: 100%;
            }
            .dataframe {
                width: 100%;
            }
        </style>
    """,
        unsafe_allow_html=True,
    )

    # ---- Duplicates Statistics Overview Section ---- #
    st.markdown("## Duplicates Statistics Overview")

    # Calculate statistics for ID duplicates
    id_dups_data = data[data.duplicated(subset=[survey_id], keep=False)]

    # Calculate statistics for selected columns (only if dup_cols is not empty)
    total_duplicates = 0
    dups_data = pd.DataFrame()
    if dup_cols:
        data["num_dups"] = data.groupby(dup_cols)[survey_key].transform("count")
        dups_data = data[data["num_dups"] > 1]
        total_duplicates = len(dups_data)

    # Determine duplicates for each selected column
    columns_with_dups = []
    columns_no_dups = []

    for col in dup_cols:
        # Check if column has duplicates
        if data[col].duplicated().any():
            columns_with_dups.append(col)
        else:
            columns_no_dups.append(col)

    total_columns_checked = len(dup_cols)
    total_columns_no_dups = len(columns_no_dups)
    total_columns_with_dups = len(columns_with_dups)
    id_duplicates = len(id_dups_data)

    # Calculate total records for percentage calculations
    total_records = len(data)

    resolved_duplicates = 0
    if "resolved_duplicates" in st.session_state:
        resolved_duplicates = st.session_state["resolved_duplicates"]

    # Display metric cards in a row
    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        st.metric(label="Columns Checked", value=total_columns_checked)

    with col2:
        st.metric(label="Columns With No Duplicates", value=total_columns_no_dups)

    with col3:
        st.metric(label="Columns With Duplicates", value=total_columns_with_dups)

    with col4:
        st.metric(label="Total Duplicates", value=total_duplicates)

    with col5:
        st.metric(label=f"{survey_id} Duplicates", value=id_duplicates)

    with col6:
        st.metric(label="Duplicates Resolved", value=resolved_duplicates)

    # Add a separator
    st.markdown("---")

    # Create tabs for ID duplicates and selected variables duplicates
    tab1, tab2 = st.tabs(["Survey ID Duplicates", "Selected Variables Duplicates"])

    # Tab for ID duplicates
    with tab1:
        st.markdown(f"## Duplicate Entries for {survey_id}")

        if id_dups_data.empty:
            st.write(f"No duplicates found for {survey_id}")
        else:
            # Count duplicates by ID
            id_dups_data["id_dup_count"] = id_dups_data.groupby(survey_id)[
                survey_key
            ].transform("count")

            # Calculate percentage of total records
            id_dups_data["id_dup_percent"] = (
                id_dups_data["id_dup_count"] / total_records
            ) * 100

            # Sort by count in descending order
            id_dups_data = id_dups_data.sort_values(
                ["id_dup_count", survey_id], ascending=[False, True]
            )

            # Create a list of columns to display
            # Start with mandatory columns
            id_display_columns = [survey_id, date, survey_key]

            # Add user-selected display columns (if any)
            for col in display_cols:
                if col not in id_display_columns and col in id_dups_data.columns:
                    id_display_columns.append(col)

            # Insert the duplicate count and percentage
            if "id_dup_count" not in id_display_columns:
                id_display_columns.insert(1, "id_dup_count")
            if "id_dup_percent" not in id_display_columns:
                id_display_columns.insert(2, "id_dup_percent")

            # Filter to ensure all columns exist in the dataframe
            existing_columns = [
                col for col in id_display_columns if col in id_dups_data.columns
            ]

            st.dataframe(
                id_dups_data[existing_columns],
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

    # Tab for selected variables duplicates
    with tab2:
        st.markdown("## Duplicate Entries for Selected Variables")

        # Only allow selection if dup_cols is not empty
        if dup_cols:
            # Create dropdown for variable selection
            selected_var = st.selectbox(
                "Select variable to display duplicates for:",
                options=dup_cols,
                key="selected_var_duplicates",
            )

            # Display duplicates for the selected variable
            if selected_var:
                # Check if the selected variable has duplicates
                if selected_var in columns_with_dups:
                    # Filter by this specific column
                    var_dups_data = data[
                        data.duplicated(subset=[selected_var], keep=False)
                    ]

                    # Count duplicates by this column
                    var_dups_data[f"{selected_var}_dup_count"] = var_dups_data.groupby(
                        selected_var
                    )[survey_key].transform("count")

                    # Calculate percentage of total records
                    var_dups_data[f"{selected_var}_dup_percent"] = (
                        var_dups_data[f"{selected_var}_dup_count"] / total_records
                    ) * 100

                    # Sort by count in descending order
                    var_dups_data = var_dups_data.sort_values(
                        [f"{selected_var}_dup_count", selected_var],
                        ascending=[False, True],
                    )

                    # Create list of columns to display
                    # Start with the current variable and mandatory columns
                    var_display_columns = [survey_id, selected_var, date, survey_key]

                    # Add user-selected display columns
                    for display_col in display_cols:
                        if (
                            display_col not in var_display_columns
                            and display_col in var_dups_data.columns
                        ):
                            var_display_columns.append(display_col)

                    # Insert the duplicate count and percentage
                    var_display_columns.insert(2, f"{selected_var}_dup_count")
                    var_display_columns.insert(3, f"{selected_var}_dup_percent")

                    # Filter to ensure all columns exist in the dataframe
                    existing_columns = [
                        c for c in var_display_columns if c in var_dups_data.columns
                    ]

                    st.dataframe(
                        var_dups_data[existing_columns],
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            f"{selected_var}_dup_count": st.column_config.Column(
                                label=f"# of {selected_var} duplicates"
                            ),
                            f"{selected_var}_dup_percent": st.column_config.NumberColumn(
                                label="% of total records", format="%.2f%%"
                            ),
                        },
                    )
                else:
                    st.warning(f"No duplicates found for {selected_var}")
        else:
            st.info("Please select columns to check for duplicates in the settings.")
