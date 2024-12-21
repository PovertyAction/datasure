import streamlit as st
<<<<<<< HEAD


# define function to create duplicates report
def duplicates_report(data, page_num) -> None:  # noqa: D417, RUF100
=======
import pandas as pd


# define function to create duplicates report
def duplicates_report(data) -> None:  # noqa: D417, RUF100

>>>>>>> fbd01f5 (adding duplicates check file)
    """
    Generate a report on duplicate data in the dataset. The report includes a
    summary of duplicate data, a table showing the number of duplicate rows, and
    an option to inspect duplicate rows.

    Parameters
    ----------
        data (pd.DataFrame): The dataset to generate the duplicate data
                report for.
<<<<<<< HEAD

    Returns
    -------
        None

    """
=======
        
    Returns 
    -------
    
        None

    """

>>>>>>> fbd01f5 (adding duplicates check file)
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for survey duplicates report")

        survey_cols = data.columns

        st.write("---")
        st.markdown("### Select columns to check for duplicates")
        dup_cols = st.multiselect("Columns", options=survey_cols, key="dup_cols")

<<<<<<< HEAD
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
=======
        st.markdown("### Select survey ID column")
        survey_id = st.selectbox("Survey ID", options=survey_cols, key="survey_id_duplicates", index=None)

        st.markdown("### Select survey key column")
        survey_key = st.selectbox("Survey Key", options=survey_cols, key="survey_key_duplicates", index=None)

        st.markdown("### Select date column")
        date = st.selectbox("Date", options=survey_cols, key="date_duplicates", index=None)

        st.write("---")
        st.markdown("### Report options")
        
        st.markdown("### Select additional columns to display in the report")

        display_cols = st.multiselect("Columns", options=survey_cols, key="display_cols")
>>>>>>> fbd01f5 (adding duplicates check file)

        # add button for saving settings
        st.write("---")
        st.write("Save settings")
<<<<<<< HEAD
        save_settings = st.button("Save settings", key="save_settings_duplicates")  # noqa: F841

    # ---- Show report --- #
    # Check that required options have been selected. If not, display a info message
    if not all([survey_id, survey_key, date, display_cols]):
        st.info("Please select all required options to generate the progress report")
        return

=======
        save_settings = st.button("Save settings", key="save_settings_duplicates")

    
>>>>>>> fbd01f5 (adding duplicates check file)
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

    # Count duplicates by ID
<<<<<<< HEAD
    data["num_dups"] = data.groupby(dup_cols)[survey_key].transform("count")

    # Filter rows with duplicates and without missing
    dups_data = data[data["num_dups"] > 1]
=======
    data['num_dups'] = data.groupby(dup_cols)[survey_key].transform('count')
   
    # Filter rows with duplicates and without missing
    dups_data = data[data['num_dups'] > 1]
>>>>>>> fbd01f5 (adding duplicates check file)

    if dups_data.empty:
        st.write("No duplicates")
    else:
        # Sort by num_dups in descending order
        dups_data = dups_data.sort_values("num_dups", ascending=[False])

        # Include the selected column in the result
        if dup_cols == survey_id:
            result = dups_data[[survey_id, "num_dups", date, survey_key]]
        else:
            result = dups_data[[survey_id] + dup_cols + ["num_dups", date, survey_key]]

        # Display using st.dataframe with configurations for better display
        st.dataframe(
            result,
            hide_index=True,
<<<<<<< HEAD
            use_container_width=True,
            column_config={
                "num_dups": st.column_config.Column(label="# of duplicates")
            },
        )
=======
            use_container_width=True, 
            column_config={
                'num_dups':st.column_config.Column(
                    label="# of duplicates"
                )
            }
        )

>>>>>>> fbd01f5 (adding duplicates check file)
