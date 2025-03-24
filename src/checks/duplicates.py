import streamlit as st


# define function to create duplicates report
def duplicates_report(data, page_num) -> None:  # noqa: D417, RUF100
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
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for survey duplicates report")

        survey_cols = data.columns

        st.write("---")
        st.markdown("### Select columns to check for duplicates")
        dup_cols = st.multiselect("Columns", options=survey_cols, key="dup_cols")

        id_col, key_col, date_col = st.columns(3)

        with id_col:
            # get survey id column name from dataset & get index
            default_survey_id = st.session_state["config_pages"]["Survey ID"][
                page_num - 1
            ]
            default_survey_id_index = survey_cols.get_loc(default_survey_id)

            st.markdown("### Select survey ID column")
            survey_id = st.selectbox(
                "Survey ID",
                options=survey_cols,
                key="survey_id_duplicates",
                index=default_survey_id_index,
            )

        with key_col:
            # get survey key column name from dataset & get index
            default_survey_key = st.session_state["config_pages"]["Survey KEY"][
                page_num - 1
            ]
            default_survey_key_index = survey_cols.get_loc(default_survey_key)

            st.markdown("### Select survey key column")
            survey_key = st.selectbox(
                "Survey Key",
                options=survey_cols,
                key="survey_key_duplicates",
                index=default_survey_key_index,
            )

        with date_col:
            # get date column name from dataset & get index
            default_date = st.session_state["config_pages"]["Survey Date"][page_num - 1]
            default_date_index = survey_cols.get_loc(default_date)

            st.markdown("### Select date column")
            date = st.selectbox(
                "Date",
                options=survey_cols,
                key="date_duplicates",
                index=default_date_index,
            )

        st.write("---")
        st.markdown("### Report options")

        st.markdown("### Select additional columns to display in the report")

        display_cols = st.multiselect(
            "Columns", options=survey_cols, key="display_cols"
        )

        # add button for saving settings
        st.write("---")
        st.write("Save settings")
        save_settings = st.button("Save settings", key="save_settings_duplicates")  # noqa: F841

    # ---- Show report --- #
    # Check that required options have been selected. If not, display a info message
    if not all([survey_id, survey_key, date, display_cols]):
        st.info("Please select all required options to generate the progress report")
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

    # Calculate statistics for selected columns
    data["num_dups"] = data.groupby(dup_cols)[survey_key].transform("count")
    dups_data = data[data["num_dups"] > 1]

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
    total_duplicates = len(dups_data)
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

            # Add user-selected display columns
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
