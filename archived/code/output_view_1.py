<<<<<<< HEAD
<<<<<<< HEAD
from datetime import datetime

import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st

st.title(st.session_state.config_page_1)

summary, survey_progress, duplicates, missing, outliers, enum_stats = st.tabs(
    (
        "Summary",
        "Survey Progress",
        "Duplicates",
        "Missing Data",
        "Outliers",
        "Enumerator Stats",
    )
)

alias_list = list(filter(None, st.session_state.alias_list))
new_page_data = st.session_state["prepped_data1"]

# load data from

with summary, st.expander("settings", icon=":material/settings:"):
    st.markdown("## Configure settings for summary report")

    survey_cols = st.session_state[f"prepped_data{1}"].columns

    st.write("---")
    st.markdown("### Select columns to include in summary report")

    formversion_col, enumerator_col, date_col = st.columns(3)
    formversion_col.selectbox("Form Version", options=survey_cols)
    enumerator_col.selectbox("Enumerator", options=survey_cols)
    date_col.selectbox("Date", options=survey_cols)
    by_col, consent_col, duration_col = st.columns(3)
    by_col.selectbox("Group by", options=survey_cols)
    consent_col.selectbox("Consent", options=survey_cols)
    duration_col.selectbox("Duration", options="Duration")

    st.write("---")
    st.markdown("### Summary report options")

    enum_filter_col, team_filter_col, location_filter_col = st.columns(3)
    enum_filter_col.multiselect("Enumerator", options=survey_cols)
    team_filter_col.multiselect("Team", options=survey_cols)
    location_filter_col.multiselect("Location", options=survey_cols)

    date_filter = st.slider(
        "Select date range",
        min_value=datetime(2024, 1, 1),
        max_value=datetime(2024, 12, 31),
        format="YYYY-MM-DD",
        value=(datetime(2024, 1, 1), datetime(2024, 12, 31)),
    )


with missing:
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for missing data report")

        survey_cols = st.session_state["prepped_data1"].columns

        st.write("---")
        st.markdown("### Select columns to include in missing data report")

        miss_cols = st.multiselect("Columns", options=survey_cols)
=======
import streamlit as st
import pandas as pd
=======
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)
from datetime import datetime

import matplotlib.pyplot as plt
import seaborn as sns
import streamlit as st

st.title(st.session_state.config_page_1)

summary, survey_progress, duplicates, missing, outliers, enum_stats = st.tabs(
    (
        "Summary",
        "Survey Progress",
        "Duplicates",
        "Missing Data",
        "Outliers",
        "Enumerator Stats",
    )
)

alias_list = list(filter(None, st.session_state.alias_list))
new_page_data = st.session_state["prepped_data1"]

# load data from

with summary, st.expander("settings", icon=":material/settings:"):
    st.markdown("## Configure settings for summary report")

    survey_cols = st.session_state[f"prepped_data{1}"].columns

    st.write("---")
    st.markdown("### Select columns to include in summary report")

    formversion_col, enumerator_col, date_col = st.columns(3)
    formversion_col.selectbox("Form Version", options=survey_cols)
    enumerator_col.selectbox("Enumerator", options=survey_cols)
    date_col.selectbox("Date", options=survey_cols)
    by_col, consent_col, duration_col = st.columns(3)
    by_col.selectbox("Group by", options=survey_cols)
    consent_col.selectbox("Consent", options=survey_cols)
    duration_col.selectbox("Duration", options="Duration")

    st.write("---")
    st.markdown("### Summary report options")

    enum_filter_col, team_filter_col, location_filter_col = st.columns(3)
    enum_filter_col.multiselect("Enumerator", options=survey_cols)
    team_filter_col.multiselect("Team", options=survey_cols)
    location_filter_col.multiselect("Location", options=survey_cols)

    date_filter = st.slider(
        "Select date range",
        min_value=datetime(2024, 1, 1),
        max_value=datetime(2024, 12, 31),
        format="YYYY-MM-DD",
        value=(datetime(2024, 1, 1), datetime(2024, 12, 31)),
    )


with missing:  # noqa: SIM117
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for missing data report")

        survey_cols = st.session_state["prepped_data1"].columns

        st.write("---")
        st.markdown("### Select columns to include in missing data report")
<<<<<<< HEAD
        
        miss_cols = st.multiselect("Columns", options = survey_cols)
>>>>>>> ad3f479 (added summary report)
=======

        miss_cols = st.multiselect("Columns", options=survey_cols)
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)

        st.write("---")
        st.markdown("### Report filter options")
        miss_filter_options = ["All", "Top N", "Bottom N", "Greater than", "Less than"]
<<<<<<< HEAD
<<<<<<< HEAD
        miss_filter = st.selectbox("Filter by", options=miss_filter_options)
        if miss_filter and miss_filter != "All":
            if miss_filter == "Top N" or miss_filter == "Bottom N":
                miss_filter_val = st.number_input(
                    "Number of columns", min_value=1, value=5
                )
            else:
                miss_filter_val = st.number_input(
                    "Percentage", min_value=0, max_value=100, value=10
                )
=======
        miss_filter = st.selectbox("Filter by", options = miss_filter_options)
        if miss_filter and miss_filter is not "All":
=======
        miss_filter = st.selectbox("Filter by", options=miss_filter_options)
        if miss_filter and miss_filter != "All":
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)
            if miss_filter == "Top N" or miss_filter == "Bottom N":
                miss_filter_val = st.number_input(
                    "Number of columns", min_value=1, value=5
                )
            else:
<<<<<<< HEAD
                miss_filter_val = st.number_input("Percentage", min_value = 0, max_value = 100, value = 10)
        
>>>>>>> ad3f479 (added summary report)
=======
                miss_filter_val = st.number_input(
                    "Percentage", min_value=0, max_value=100, value=10
                )
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)

    st.markdown("## Missing data")

    with st.container():
<<<<<<< HEAD
<<<<<<< HEAD
        st.markdown("### Summary")

        (
            col_metric,
            row_metric,
            miss_metric,
            no_miss_metric,
            some_miss_metric,
            all_miss_metric,
        ) = st.columns(6)
        # show number of columns
        col_metric.metric(
            label="Columns",
            value=len(st.session_state["prepped_data1"].columns),
            border=True,
        )
        # show number of rows
        row_metric.metric(
            label="Rows", value=len(st.session_state["prepped_data1"]), border=True
        )
        # show percentage of missing values
        miss_metric_val = st.session_state["prepped_data1"].isnull().sum().sum() / (
            len(st.session_state["prepped_data1"].columns)
            * len(st.session_state["prepped_data1"])
        )
        miss_metric.metric(
            label="Missing", value=round(miss_metric_val * 100, 2), border=True
        )
        # show number of columns with no missing values
        no_miss_metric_val = len(st.session_state["prepped_data1"].columns) - len(
            st.session_state["prepped_data1"].columns[
                st.session_state["prepped_data1"].isnull().sum() > 0
            ]
        )
        no_miss_metric.metric(label="No missing", value=no_miss_metric_val, border=True)
        # show number of columns with some missing values
        some_miss_metric_val = len(
            st.session_state["prepped_data1"].columns[
                st.session_state["prepped_data1"].isnull().sum() > 0
            ]
        )
        some_miss_metric.metric(
            label="Some missing", value=some_miss_metric_val, border=True
        )
        # show number of columns with all missing values
        all_miss_metric_val = len(
            st.session_state["prepped_data1"].columns[
                st.session_state["prepped_data1"].isnull().sum()
                == len(st.session_state["prepped_data1"])
            ]
        )
        all_miss_metric.metric(
            label="All missing", value=all_miss_metric_val, border=True
        )

    miss_table, miss_inspect = st.columns((0.3, 0.7))

    with miss_table:  # noqa: SIM117
        with st.container(border=True):
            st.markdown("### Missing data by column")

            # for each column, show the percentage of missing values
            missing_data = st.session_state["prepped_data1"].isnull().sum() / len(
                st.session_state["prepped_data1"]
            )
            # sort data from highest to lowest
            missing_data = missing_data.sort_values(ascending=False)
            # rename columns as columns and missing values
            missing_data = missing_data.rename_axis("columns").reset_index(
                name="% missing"
            )
            st.data_editor(
                missing_data,
                hide_index=True,
                column_config={
                    "% missing": st.column_config.ProgressColumn(
                        label="% missing",
                        help="Percentage of missing values in the column",
                        min_value=0,
                        max_value=1.0,
                    ),
                },
            )

    with miss_inspect:  # noqa: SIM117
        with st.container(border=True):
            st.markdown("### Inspect variables with missing data")

            inspect_cols = st.multiselect(
                "Select columns to inspect",
                options=st.session_state["prepped_data1"].columns,
            )
=======
        
=======
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)
        st.markdown("### Summary")

        (
            col_metric,
            row_metric,
            miss_metric,
            no_miss_metric,
            some_miss_metric,
            all_miss_metric,
        ) = st.columns(6)
        # show number of columns
        col_metric.metric(
            label="Columns",
            value=len(st.session_state["prepped_data1"].columns),
            border=True,
        )
        # show number of rows
        row_metric.metric(
            label="Rows", value=len(st.session_state["prepped_data1"]), border=True
        )
        # show percentage of missing values
        miss_metric_val = st.session_state["prepped_data1"].isnull().sum().sum() / (
            len(st.session_state["prepped_data1"].columns)
            * len(st.session_state["prepped_data1"])
        )
        miss_metric.metric(
            label="Missing", value=round(miss_metric_val * 100, 2), border=True
        )
        # show number of columns with no missing values
        no_miss_metric_val = len(st.session_state["prepped_data1"].columns) - len(
            st.session_state["prepped_data1"].columns[
                st.session_state["prepped_data1"].isnull().sum() > 0
            ]
        )
        no_miss_metric.metric(label="No missing", value=no_miss_metric_val, border=True)
        # show number of columns with some missing values
        some_miss_metric_val = len(
            st.session_state["prepped_data1"].columns[
                st.session_state["prepped_data1"].isnull().sum() > 0
            ]
        )
        some_miss_metric.metric(
            label="Some missing", value=some_miss_metric_val, border=True
        )
        # show number of columns with all missing values
        all_miss_metric_val = len(
            st.session_state["prepped_data1"].columns[
                st.session_state["prepped_data1"].isnull().sum()
                == len(st.session_state["prepped_data1"])
            ]
        )
        all_miss_metric.metric(
            label="All missing", value=all_miss_metric_val, border=True
        )

    miss_table, miss_inspect = st.columns((0.3, 0.7))

    with miss_table:  # noqa: SIM117
        with st.container(border=True):
            st.markdown("### Missing data by column")

            # for each column, show the percentage of missing values
            missing_data = st.session_state["prepped_data1"].isnull().sum() / len(
                st.session_state["prepped_data1"]
            )
            # sort data from highest to lowest
            missing_data = missing_data.sort_values(ascending=False)
            # rename columns as columns and missing values
            missing_data = missing_data.rename_axis("columns").reset_index(
                name="% missing"
            )
            st.data_editor(
                missing_data,
                hide_index=True,
                column_config={
                    "% missing": st.column_config.ProgressColumn(
                        label="% missing",
                        help="Percentage of missing values in the column",
                        min_value=0,
                        max_value=1.0,
                    ),
                },
            )

    with miss_inspect:  # noqa: SIM117
        with st.container(border=True):
            st.markdown("### Inspect variables with missing data")

<<<<<<< HEAD
            inspect_cols = st.multiselect("Select columns to inspect", options = st.session_state['prepped_data1'].columns)
>>>>>>> ad3f479 (added summary report)
=======
            inspect_cols = st.multiselect(
                "Select columns to inspect",
                options=st.session_state["prepped_data1"].columns,
            )
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)

            st.write("---")

            if inspect_cols:
<<<<<<< HEAD
<<<<<<< HEAD
=======
                
>>>>>>> ad3f479 (added summary report)
=======
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)
                # count the number columns selected
                num_cols = len(inspect_cols)

                st.write(f"Inspecting {num_cols} columns")

                inspect_vars_mc1, inspect_vars_mc2, inspect_vars_mc3 = st.columns(3)

<<<<<<< HEAD
<<<<<<< HEAD
                inspect_vars_mc1.metric(
                    label=r"\# of columns", value=num_cols, border=True
                )
                # total number of missing values
                inspect_vars_mc2.metric(
                    label=r"\# of missing values",
                    value=st.session_state["prepped_data1"][inspect_cols]
                    .isnull()
                    .sum()
                    .sum(),
                    border=True,
                )
                # percentage of missing values
                inspect_vars_miss_perc = (
                    st.session_state["prepped_data1"][inspect_cols].isnull().sum().sum()
                    / (len(st.session_state["prepped_data1"]) * num_cols)
                ) * 100
                inspect_vars_mc3.metric(
                    label="% of missing values",
                    value=f"{round(inspect_vars_miss_perc, 2)}%",
                    border=True,
                )

                if num_cols == 1:
                    st.write("---")
                    st.markdown(f"### Missing data correlation for {inspect_cols}")

                    # create a table showing the correlation between missing
                    # values of selected column and all other columns, sort
                    # data from highest to lowest
                    missing_data_corr = (
                        st.session_state["prepped_data1"]
                        .isnull()
                        .corr()[inspect_cols[0]]
                        .sort_values(ascending=False)
                    )

                    st.data_editor(
                        missing_data_corr,
                        hide_index=False,
                        column_config={
                            inspect_cols[0]: st.column_config.ProgressColumn(
                                label=inspect_cols[0],
                                help="Correlation between missing values in selected column and other columns",
                                min_value=-1,
                                max_value=1.0,
                            ),
                        },
                    )

                elif num_cols > 1:
                    st.write("---")
                    st.markdown("### Missing data correlation for selected columns")

                    # create a table showing the correlation between missing
                    # values of selected columns and all other columns,
                    # sort data from highest to lowest
                    missing_data_corr = (
                        st.session_state["prepped_data1"][inspect_cols].isnull().corr()
                    )
                    missing_heatmap = plt.figure(figsize=(6, 4))
                    sns.heatmap(data=missing_data_corr, cmap="rocket", annot=True)

                    st.pyplot(missing_heatmap)
=======
                inspect_vars_mc1.metric(label = "\# of columns", value = num_cols, border = True)
=======
                inspect_vars_mc1.metric(
                    label=r"\# of columns", value=num_cols, border=True
                )
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)
                # total number of missing values
                inspect_vars_mc2.metric(
                    label=r"\# of missing values",
                    value=st.session_state["prepped_data1"][inspect_cols]
                    .isnull()
                    .sum()
                    .sum(),
                    border=True,
                )
                # percentage of missing values
                inspect_vars_miss_perc = (
                    st.session_state["prepped_data1"][inspect_cols].isnull().sum().sum()
                    / (len(st.session_state["prepped_data1"]) * num_cols)
                ) * 100
                inspect_vars_mc3.metric(
                    label="% of missing values",
                    value=f"{round(inspect_vars_miss_perc, 2)}%",
                    border=True,
                )

                if num_cols == 1:
                    st.write("---")
                    st.markdown(f"### Missing data correlation for {inspect_cols}")

                    # create a table showing the correlation between missing values of selected column and all other columns, sort data from highest to lowest
                    missing_data_corr = (
                        st.session_state["prepped_data1"]
                        .isnull()
                        .corr()[inspect_cols[0]]
                        .sort_values(ascending=False)
                    )

                    st.data_editor(
                        missing_data_corr,
                        hide_index=False,
                        column_config={
                            inspect_cols[0]: st.column_config.ProgressColumn(
                                label=inspect_cols[0],
                                help="Correlation between missing values in selected column and other columns",
                                min_value=-1,
                                max_value=1.0,
                            ),
                        },
                    )

                elif num_cols > 1:
                    st.write("---")
                    st.markdown("### Missing data correlation for selected columns")

                    # create a table showing the correlation between missing values of selected columns and all other columns, sort data from highest to lowest
                    missing_data_corr = (
                        st.session_state["prepped_data1"][inspect_cols].isnull().corr()
                    )
                    missing_heatmap = plt.figure(figsize=(6, 4))
                    sns.heatmap(data=missing_data_corr, cmap="rocket", annot=True)

                    st.pyplot(missing_heatmap)
<<<<<<< HEAD


                    


           
  
   
    
>>>>>>> ad3f479 (added summary report)
=======
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)
