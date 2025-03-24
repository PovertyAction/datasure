import pandas as pd
import plotly.express as px
import streamlit as st

##### Backchecks #####


def backchecks_report(survey_data, backcheck_data, page_num) -> None:
    """
    Create a backcheck report for a given survey and backcheck data.

    PARAMS:
    -------
    survey_data: pd.DataFrame
        Survey data to be used for backcheck report

    backcheck_data: pd.DataFrame
        Backcheck data to be used for backcheck report

    page_num: int
        Page number for the backcheck report

    Returns
    -------
    None

    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for backcheck report")

        survey_cols = survey_data.columns.tolist()

        # get list of columns in both surey and backcheck data
        common_cols = [
            col for col in survey_data.columns if col in backcheck_data.columns
        ]

        st.write("---")
        st.markdown("### Select columns to include in backcheck report")

        backcheck_cols = st.multiselect(
            "Select columns to include in back check report",
            options=common_cols,
            key="backcheck_cols",
            help="Select columns to include in back check report",
        )

        st.write("---")
        st.markdown("### Select other columns")

        meta_col, enum_col, agg_col = st.columns(spec=3, border=True)

        with meta_col:
            duration = st.selectbox(
                "Duration",
                options=survey_cols,
                help="Column containing survey duration",
                key="duration_backcheck",
                index=None,
            )
            date = st.selectbox(
                "Date",
                options=survey_cols,
                help="Column containing survey date",
                key="date_backcheck",
                index=None,
            )
            formversion = st.selectbox(
                "Form Version",
                options=survey_cols,
                help="Column containing survey form version",
                key="formversion_backcheck",
                index=None,
            )

        with enum_col:
            enumerator = st.selectbox(
                "Enumerator",
                options=survey_cols,
                help="Column containing survey enumerator",
                key="enumerator_backcheck",
                index=None,
            )
            team = st.selectbox(
                "Enumerator Team",
                options=survey_cols,
                help="Column containing survey team",
                key="team_backcheck",
                index=None,
            )
            backchecker = st.selectbox(
                "Back Checker",
                options=survey_cols,
                help="Column containing back check enumerator",
                key="backchecker_backcheck",
                index=None,
            )
            bc_team = st.selectbox(  # noqa: F841
                "Back Check Team",
                options=survey_cols,
                help="Column containing survey team",
                key="backcheck_team_backcheck",
                index=None,
            )

        with agg_col:
            survey_id = st.selectbox(
                "Survey ID",
                options=survey_cols,
                help="Column containing survey ID",
                key="surveyid_backcheck",
                index=None,
            )
            survey_key = st.selectbox(
                "Survey Key",
                options=survey_cols,
                help="Column containing survey key",
                key="surveykey_backcheck",
                index=None,
            )

            consent = st.selectbox(
                "Consent",
                options=survey_cols,
                help="Column containing survey consent",
                key="consent_backcheck",
                index=None,
            )

            if consent:
                consent_options = survey_data[consent].unique().tolist()
                consent_val = st.multiselect(  # noqa: F841
                    "Consent value(s)",
                    options=consent_options,
                    help="Value(s) indicating valid consent",
                    key="consent_val_backcheck",
                )

            outcome = st.selectbox(
                "Outcome",
                options=survey_cols,
                help="Column containing survey outcome",
                key="outcome_backcheck",
                index=None,
            )

            if outcome:
                outcome_options = survey_data[outcome].unique().tolist()
                outcome_val = st.multiselect(  # noqa: F841
                    "Outcome value(s)",
                    options=outcome_options,
                    help="Value(s) indicating completed survey",
                    key="outcome_val_backcheck",
                )

        st.write("---")
        st.markdown("### Tracking Options")

        # number of interviews expected
        backcheck_goal = st.number_input(
            "Target number of backchecks",
            min_value=0,
            help="Total number of backchecks expected",
            key="total_goal_backcheck",
        )
        # duplicates handling
        st.write("How would you like to handle duplicates?")
        drop_duplicates = st.toggle(
            label="Drop duplicates", value=True, key="drop_duplicates_backcheck"
        )
        st.write("")

        # define a save settings button
        save_settings = st.button("Save settings", key="save_settings_backcheck")  # noqa: F841

    # Check that required options have been selected. If not, display a info message
    if not all(
        [
            duration,
            date,
            formversion,
            enumerator,
            team,
            backchecker,
            survey_id,
            survey_key,
            consent,
            outcome,
        ]
    ):
        st.info("Please select all required options to generate the progress report")
        return

    if backcheck_data.empty:
        st.warning("No back check data available")

    else:
        if backcheck_cols:
            # drop duplicates
            if drop_duplicates:
                survey_data = survey_data.sort_values(
                    by=date, ascending=False
                ).drop_duplicates(subset=[survey_id], keep="first")
                backcheck_data = backcheck_data.sort_values(
                    by=date, ascending=False
                ).drop_duplicates(subset=[survey_id], keep="first")

            # merge survey and backcheck data
            survey_df_bc = survey_data[
                backcheck_cols + [survey_id, enumerator, consent, date]
            ].add_prefix("_svy_")
            # rename enumerator and survey_id columns removing prefix
            survey_df_bc.rename(columns={"_svy_" + survey_id: survey_id}, inplace=True)
            backcheck_df_bc = backcheck_data[
                backcheck_cols + [survey_id, backchecker, consent, date]
            ].add_prefix("_bc_")
            # rename enumerator and survey_id columns removing prefix
            backcheck_df_bc.rename(
                columns={"_bc_" + survey_id: survey_id}, inplace=True
            )

            merged_df = pd.merge(
                survey_df_bc, backcheck_df_bc, on=survey_id, how="inner"
            )

            # Find matching variable pairs (survey and backcheck variables)
            svy_vars = [col for col in merged_df.columns if col.startswith("_svy_")]  # noqa: F841
            back_vars = [col for col in merged_df.columns if col.startswith("_bc_")]  # noqa: F841

            # overview statistics
            st.subheader("Overview")
            min_backcheck_rate = st.number_input(
                "Enter a minimum percentage target of surveys backchecked by enumerator e.g. 10%",
                min_value=0,
                max_value=100,
                value=10,
                key="total_surveys_backcheck",
                help="This is the minimum percentage of surveys that have been backchecked by enumerator",
            )

            col1, col2, col3 = st.columns(3)
            col1.metric("Total number of backchecks", len(backcheck_df_bc))
            with col3:
                st.session_state.total_backcheck_error_rate = None
                if st.session_state.total_backcheck_error_rate is None:
                    st.warning("Backcheck column settings not configured")
                else:
                    st.metric(
                        "Total backcheck error rate",
                        f"{st.session_state.total_backcheck_error_rate:.0f}%",
                    )

            cl1, cl2, cl3 = st.columns(3)
            # define chart colors
            chart_colors = ["#35904A", "lightgrey"]
            with cl1:
                if backcheck_goal == 0:
                    st.warning("Please set a target for backchecks")
                else:
                    # Calculate percentage of backchecks completed
                    total_surveys = len(survey_df_bc)
                    total_backchecks = len(backcheck_df_bc)
                    # handle case when backchecks is > backchecks target
                    if backcheck_goal < total_backchecks:
                        backcheck_goal_update = total_backchecks
                    else:
                        backcheck_goal_update = backcheck_goal

                    # Create a donut chart

                    fig = px.pie(
                        names=["Backchecked", "Not backchecked"],
                        values=[
                            total_backchecks,
                            backcheck_goal_update - total_backchecks,
                        ],
                        hole=0.6,
                        title="% of surveys backchecked",
                    )
                    fig.update_layout(
                        width=400,
                        height=350,
                        showlegend=False,
                        title=dict(xanchor="left", y=0.9, yanchor="top"),
                    )
                    fig.update_traces(
                        textinfo="none",
                        marker=dict(colors=chart_colors),
                        direction="clockwise",
                    )

                    fig.add_annotation(
                        dict(
                            text=f"{(total_backchecks / backcheck_goal) * 100:.0f}%",
                            x=0.5,
                            y=0.5,
                            font_size=30,
                            font_weight="bold",
                            showarrow=False,
                        )
                    )

                    # Display the chart
                    st.plotly_chart(fig)

            with cl3:
                backcheck_sum_df = (
                    survey_df_bc.groupby("_svy_" + enumerator)
                    .size()
                    .reset_index(name="total_surveys")
                )
                backcheck_sum_df = backcheck_sum_df.merge(
                    merged_df.groupby("_svy_" + enumerator)
                    .size()
                    .reset_index(name="total_backchecks"),
                    left_on="_svy_" + enumerator,
                    right_on="_svy_" + enumerator,
                    how="outer",
                )
                backcheck_sum_df["backcheck_rate"] = (
                    backcheck_sum_df["total_backchecks"]
                    / backcheck_sum_df["total_surveys"]
                ) * 100
                bc_target_met_df = backcheck_sum_df[
                    backcheck_sum_df["backcheck_rate"] >= min_backcheck_rate
                ]

                num_enumerators_bc = bc_target_met_df["_svy_" + enumerator].nunique()
                total_enumerators = len(survey_df_bc["_svy_" + enumerator].unique())

                # Create a pie chart
                fig_enum = px.pie(
                    names=["Backchecked", "Not backchecked"],
                    values=[num_enumerators_bc, total_enumerators - num_enumerators_bc],
                    hole=0.6,
                    title="% of enumerators backchecked",
                )
                fig_enum.update_layout(
                    width=400,
                    height=350,
                    showlegend=False,
                    title=dict(xanchor="left", y=0.9, yanchor="top"),
                )
                fig_enum.update_traces(
                    textinfo="none",
                    marker=dict(colors=chart_colors),
                    direction="clockwise",
                )

                fig_enum.add_annotation(
                    dict(
                        text=f"{(num_enumerators_bc / total_enumerators) * 100:.0f}%",
                        x=0.5,
                        y=0.5,
                        font_size=30,
                        font_weight="bold",
                        showarrow=False,
                    )
                )

                # Display the pie chart
                st.plotly_chart(fig_enum)

            # Column types selection
            with st.expander("Backcheck columns settings", expanded=True):
                # Initialize session state for table data if not already present
                if "column_config_data" not in st.session_state:
                    st.session_state.column_config_data = pd.DataFrame(
                        columns=[
                            "column",
                            "category",
                            "ok range",
                            "comparison condition",
                        ]
                    )

                # Display the table and allow user interaction
                with st.popover("Add a backcheck column", icon=":material/add:"):
                    # st.markdown("### Add backcheck column type")
                    column_name = st.selectbox(
                        "column",
                        options=common_cols,
                        help="Select a column to configure",
                        key="column",
                    )
                    column_type = st.selectbox(
                        "category",
                        options=[1, 2, 3],
                        help="Select the backcheck category of the column",
                        key="category",
                    )
                    ok_range_type = st.selectbox(
                        "ok range",
                        options=[
                            "None",
                            "equals to",
                            "less than",
                            "greater than",
                            "between",
                        ],
                        help="Select the type of range condition",
                        key="ok range",
                    )

                    if ok_range_type == "between":
                        range_min = st.number_input(
                            "Minimum Value", help="Enter the minimum value"
                        )
                        range_max = st.number_input(
                            "Maximum Value", help="Enter the maximum value"
                        )
                        ok_range = f"between {range_min} and {range_max}"
                    elif ok_range_type == "None":
                        ok_range = ""
                    else:
                        single_value = st.number_input("Value", help="Enter the value")
                        ok_range = f"{ok_range_type} {single_value}"

                    compare_condition = st.selectbox(
                        label="comparison condition",
                        options=[
                            "None",
                            "Do not compare missing values or null values",
                            "Do not compare if the values contain:",
                            "Treat these values as the same:",
                        ],
                        help="Specify any additional conditions (e.g., do compare if values are missing)",
                        key="comparison condition",
                    )
                    if compare_condition == "Do not compare if the values contain:":
                        contains_condition = st.text_input(
                            "Enter the values separated by a comma",
                            help="Enter the values separated by a comma",
                        )
                        comparison_condition = (
                            f"{compare_condition} {contains_condition}"
                        )
                    elif compare_condition == "Treat these values as the same:":
                        same_condition = st.text_input(
                            "Enter the values separated by a comma",
                            help="Enter the values separated by a comma",
                        )
                        comparison_condition = f"{compare_condition} {same_condition}"
                    elif (
                        compare_condition
                        == "Do not compare missing values or null values"
                    ):
                        comparison_condition = "ignore_missing_values"
                    else:
                        comparison_condition = ""

                    if st.button("Add Column"):
                        new_row = {
                            "column": column_name,
                            "category": column_type,
                            "ok range": ok_range,
                            "comparison condition": comparison_condition,
                        }
                        st.session_state.column_config_data = pd.concat(
                            [
                                st.session_state.column_config_data,
                                pd.DataFrame([new_row]),
                            ],
                            ignore_index=True,
                        )
                # create an editable dataframe
                bc_column_config_df = st.data_editor(
                    st.session_state.column_config_data,
                    num_rows="dynamic",
                    use_container_width=True,
                )
                # drop any deleted rowss
                if len(st.session_state.column_config_data) > len(bc_column_config_df):
                    deleted_rows = st.session_state.column_config_data[
                        ~st.session_state.column_config_data.isin(
                            bc_column_config_df.to_dict(orient="list")
                        ).all(axis=1)
                    ]
                    if not deleted_rows.empty:
                        st.session_state.column_config_data = bc_column_config_df

            # Create a data category report
            def generate_column_summary(
                column_config_data, survey_data, backcheck_data, survey_id
            ):
                """
                Generate a summary for each column configuration.

                Parameters
                ----------
                column_config_data: pd.DataFrame
                    DataFrame containing column configuration with columns:
                    ["Column Name", "Column Type", "OK Range", "Conditions"]

                survey_data: pd.DataFrame
                    Survey data to be used for comparison.

                backcheck_data: pd.DataFrame
                    Backcheck data to be used for comparison.

                survey_id: str
                    Column name for the unique survey identifier.

                Returns
                -------
                pd.DataFrame
                    Summary DataFrame with columns:
                    ["Column", "Data Type", "Category", "# Surveys", "# Backchecks",
                     "# Compared", "# Different", "Error Rate"]
                """
                summary_data = []

                for _, row in column_config_data.iterrows():
                    column_name = row["column"]
                    column_type = row["category"]
                    ok_range = row["ok range"]
                    comparison_condition = row["comparison condition"]

                    # Prepare survey and backcheck data for the column
                    svy_col = f"_svy_{column_name}"
                    bc_col = f"_bc_{column_name}"

                    survey_col_data = (
                        survey_data[[survey_id, column_name]]
                        .add_prefix("_svy_")
                        .rename(columns={"_svy_" + survey_id: survey_id})
                    )
                    backcheck_col_data = (
                        backcheck_data[[survey_id, column_name]]
                        .add_prefix("_bc_")
                        .rename(columns={"_bc_" + survey_id: survey_id})
                    )

                    # Merge survey and backcheck data
                    merged_df = pd.merge(
                        survey_col_data, backcheck_col_data, on=survey_id, how="inner"
                    )

                    # Apply OK Range filtering
                    if ok_range:
                        if "between" in ok_range:
                            range_min, range_max = map(
                                float, ok_range.replace("between", "").split("and")
                            )
                            merged_df = merged_df[
                                (
                                    merged_df[svy_col]
                                    .astype(float)
                                    .between(range_min, range_max)
                                )
                                & (
                                    merged_df[bc_col]
                                    .astype(float)
                                    .between(range_min, range_max)
                                )
                            ]
                        elif "less than" in ok_range:
                            value = float(ok_range.replace("less than", "").strip())
                            merged_df = merged_df[
                                (merged_df[svy_col].astype(float) < value)
                                & (merged_df[bc_col].astype(float) < value)
                            ]
                        elif "greater than" in ok_range:
                            value = float(ok_range.replace("greater than", "").strip())
                            merged_df = merged_df[
                                (merged_df[svy_col].astype(float) > value)
                                & (merged_df[bc_col].astype(float) > value)
                            ]
                        elif "equals to" in ok_range:
                            value = ok_range.replace("equals to", "").strip()
                            merged_df = merged_df[
                                (merged_df[svy_col].astype(str) == value)
                                & (merged_df[bc_col].astype(str) == value)
                            ]

                    # Apply Conditions filtering
                    if comparison_condition:
                        if "Do not compare missing values" in comparison_condition:
                            merged_df = merged_df.dropna(subset=[svy_col, bc_col])
                        elif (
                            "Do not compare if the value contains:"
                            in comparison_condition
                        ):
                            exclude_values = (
                                comparison_condition.split(":")[1].strip().split(",")
                            )
                            merged_df = merged_df[
                                ~merged_df[svy_col].astype(str).isin(exclude_values)
                                & ~merged_df[bc_col].astype(str).isin(exclude_values)
                            ]
                        elif "Treat these values as the same:" in comparison_condition:
                            same_values = (
                                comparison_condition.split(":")[1].strip().split(",")
                            )
                            merged_df[svy_col] = merged_df[svy_col].replace(
                                same_values[1], same_values[0]
                            )
                            merged_df[bc_col] = merged_df[bc_col].replace(
                                same_values[1], same_values[0]
                            )

                    # Calculate metrics
                    data_types_dict = {
                        "float64": "Numeric",
                        "int64": "Numeric",
                        "object": "String",
                        "datetime64[ns]": "Date",
                    }
                    data_type = data_types_dict[survey_data[column_name].dtype.name]
                    total_surveys = len(survey_data)
                    total_backchecks = len(backcheck_data)
                    total_compared = len(merged_df)
                    total_different = (merged_df[svy_col] != merged_df[bc_col]).sum()
                    error_rate = (
                        (total_different / total_compared * 100)
                        if total_compared > 0
                        else 0
                    )

                    # Append to summary
                    summary_data.append(
                        {
                            "column": column_name,
                            "data type": data_type,
                            "category": column_type,
                            "# surveys": total_surveys,
                            "# backchecks": total_backchecks,
                            "# compared": total_compared,
                            "# different": total_different,
                            "error rate": f"{error_rate:.2f}%",
                        }
                    )

                # Convert to DataFrame and return
                return pd.DataFrame(summary_data)

            # generate the column summary
            column_category_summary = generate_column_summary(
                bc_column_config_df,
                survey_data,
                backcheck_data,
                survey_id,
            )

            st.dataframe(column_category_summary, use_container_width=True)

            # backcheck category columns
            if column_category_summary.empty:
                st.warning("No backcheck columns set")
            else:
                # backcheck category 1 error rate
                category_1_summary = column_category_summary[
                    column_category_summary["category"] == 1
                ]
                if category_1_summary.shape[0] > 0:
                    st.markdown("##### Backcheck category 1 error rates")
                    type1_1, type1_2, type1_3 = st.columns(3)
                    category_1_summary = column_category_summary[
                        column_category_summary["category"] == 1
                    ]
                    type1_1.metric(
                        "Number of category 1 columns",
                        len(category_1_summary["column"].unique()),
                    )
                    type1_2.metric(
                        "Number of category 1 values compared",
                        category_1_summary["# compared"].sum(),
                    )
                    type1_3.metric(
                        "% of category 1 error rate",
                        f"{((category_1_summary["# different"].sum()/category_1_summary["# compared"].sum())*100):.0f}%",
                    )
                    st.write("")

                # backcheck category 2 error rate
                category_2_summary = column_category_summary[
                    column_category_summary["category"] == 2
                ]
                if category_2_summary.shape[0] > 0:
                    st.markdown("##### Backcheck category 2 error rates")
                    type2_1, type2_2, type2_3 = st.columns(3)
                    category_2_summary = column_category_summary[
                        column_category_summary["category"] == 2
                    ]
                    type2_1.metric(
                        "Number of category 2 columns",
                        len(category_2_summary["column"].unique()),
                    )
                    type2_2.metric(
                        "Number of category 2 values compared",
                        category_2_summary["# compared"].sum(),
                    )
                    type2_3.metric(
                        "% of category 2 error rate",
                        f"{((category_2_summary["# different"].sum()/category_2_summary["# compared"].sum())*100):.0f}%",
                    )
                    st.write("")

                # backcheck category 3 error rate
                category_3_summary = column_category_summary[
                    column_category_summary["category"] == 3
                ]
                if category_3_summary.shape[0] > 0:
                    st.markdown("##### Backcheck category 3 error rates")
                    type3_1, type3_2, type3_3 = st.columns(3)
                    category_3_summary = column_category_summary[
                        column_category_summary["category"] == 3
                    ]
                    type3_1.metric(
                        "Number of category 3 columns",
                        len(category_3_summary["column"].unique()),
                    )
                    type3_2.metric(
                        "Number of category 3 values compared",
                        category_3_summary["# compared"].sum(),
                    )
                    type3_3.metric(
                        "% of category 3 error rate",
                        f"{((category_3_summary["# different"].sum()/category_3_summary["# compared"].sum())*100):.0f}%",
                    )
                st.write("")

                total_backcheck_error_rate = (
                    column_category_summary["# different"].sum()
                    / column_category_summary["# compared"].sum()
                ) * 100
                st.session_state.total_backcheck_error_rate = total_backcheck_error_rate

            # Create tabs for each selected variable

            tabs = st.tabs(
                [
                    "General Results",
                    "Enumerator Statistics",
                    "Backchecker Statistics",
                    *backcheck_cols,
                ]
            )
            var_summary = {}
            mismatches_dict = {}  # noqa: F841

            # First get the data types for each variable
            var_types = {}
            for var in backcheck_cols:
                svy_col = f"_svy_{var}"
                bc_col = f"_bc_{var}"  # noqa: F841
                # Check if all values can be converted to numeric
                try:
                    test_series = merged_df[svy_col].copy()
                    pd.to_numeric(test_series, errors="raise")
                    var_types[var] = "Numeric"
                except (ValueError, TypeError):
                    var_types[var] = "String"

            # First tab for "General Results"
            with tabs[0]:
                for var in backcheck_cols:
                    svy_col = f"_svy_{var}"
                    back_col = f"_bc_{var}"

                    enumid_var = f"_svy_{enumerator}"
                    enum_bcer_column = f"_bc_{backchecker}"

                    comparison_df = pd.DataFrame(
                        {
                            "Unique Identifier": merged_df[survey_id],
                            "Enumerator id": merged_df[enumid_var],
                            "Backchecker id": merged_df[enum_bcer_column]
                            if enum_bcer_column in merged_df.columns
                            else pd.Series([None] * len(merged_df)),
                            "Survey Value": merged_df[svy_col].astype(str),
                            "Backcheck Value": merged_df[back_col].astype(str),
                        }
                    )

                    comparison_df["Comparison"] = comparison_df.apply(
                        lambda x: "Match"
                        if str(x["Survey Value"]).strip()
                        == str(x["Backcheck Value"]).strip()
                        else "Mismatch",
                        axis=1,
                    )

                    mismatches_df = comparison_df[
                        comparison_df["Comparison"] == "Mismatch"
                    ]

                    var_summary[var] = {
                        "Variable Type": var_types[var],
                        "total_surveys": len(survey_df_bc),
                        "total_backchecks": len(backcheck_df_bc),
                        "compared": len(comparison_df),
                        "mismatches": len(mismatches_df),
                        "mismatch_percentage": (
                            len(mismatches_df) / len(comparison_df) * 100
                        )
                        if len(comparison_df) > 0
                        else 0,
                    }
                # Create the General results table from var_summary
                enumerator_stats = pd.DataFrame.from_dict(var_summary, orient="index")
                enumerator_stats = enumerator_stats.reset_index()
                enumerator_stats.columns = [
                    "Selected Variables",
                    "Variable Type",
                    "Total Surveys",
                    "Total Backchecks",
                    "# Compared",
                    "# Different",
                    "% Different",
                ]

                # Format the "% different" column
                enumerator_stats["% Different"] = (
                    enumerator_stats["% Different"].round(2)
                ).astype(str) + "%"

                # Display the general results table
                st.subheader("General Results")
                st.dataframe(enumerator_stats, use_container_width=True)

            # New tab for "Enumerator Statistics"
            with tabs[1]:
                st.subheader("Enumerator Statistics")

                # Calculate statistics per enumerator
                enumerator_detailed_stats = {}

                # First get total surveys per enumerator from existing_df
                total_surveys = survey_data[enumerator].value_counts().to_dict()

                # For each enumerator in the original dataset
                for enum_id in survey_data[enumerator].unique():
                    enumerator_detailed_stats[enum_id] = {
                        "total_surveys": total_surveys.get(enum_id, 0),
                        "total_backchecks": 0,
                        "total_compared": 0,
                        "total_different": 0,
                    }

                # Calculate backchecks and comparisons
                for var in backcheck_cols:
                    svy_col = f"_svy_{var}"
                    back_col = f"_bc_{var}"
                    enum_col = f"_svy_{enumerator}"

                    # Create comparison data for this variable
                    comparison = pd.DataFrame(
                        {
                            "enumerator_id": merged_df[enum_col],
                            "survey_value": merged_df[svy_col].astype(str),
                            "backcheck_value": merged_df[back_col].astype(str),
                        }
                    )

                    # Mark matches/mismatches
                    comparison["is_different"] = comparison.apply(
                        lambda x: str(x["survey_value"]).strip()
                        != str(x["backcheck_value"]).strip(),
                        axis=1,
                    )

                    # Group by enumerator and update statistics
                    for enum_id in comparison["enumerator_id"].unique():
                        if enum_id not in enumerator_detailed_stats:
                            # Handle case where enumerator is in
                            # backcheck but not in original data
                            enumerator_detailed_stats[enum_id] = {
                                "total_surveys": 0,
                                "total_backchecks": 0,
                                "total_compared": 0,
                                "total_different": 0,
                            }

                        enum_data = comparison[comparison["enumerator_id"] == enum_id]

                        # Only update backcheck count once per variable loop
                        if var == backcheck_cols[0]:  # First variable only
                            enumerator_detailed_stats[enum_id]["total_backchecks"] = (
                                len(enum_data)
                            )

                        enumerator_detailed_stats[enum_id]["total_compared"] += len(
                            enum_data
                        )
                        enumerator_detailed_stats[enum_id]["total_different"] += (
                            enum_data["is_different"].sum()
                        )

                # Create DataFrame from enumerator statistics
                enumerator_detailed_df = pd.DataFrame.from_dict(
                    enumerator_detailed_stats, orient="index"
                )
                enumerator_detailed_df = enumerator_detailed_df.reset_index()
                enumerator_detailed_df.columns = [
                    "Enumerator ID",
                    "Total Surveys",
                    "Total Backchecks",
                    "Total Values Compared",
                    "Total Different",
                ]

                # Calculate percentages
                enumerator_detailed_df["% Backchecked"] = (
                    enumerator_detailed_df["Total Backchecks"]
                    / enumerator_detailed_df["Total Surveys"]
                    * 100
                ).round(2)

                enumerator_detailed_df["% Different"] = (
                    enumerator_detailed_df["Total Different"]
                    / enumerator_detailed_df["Total Values Compared"]
                    * 100
                ).round(2)

                # Handle division by zero
                enumerator_detailed_df["% Backchecked"] = enumerator_detailed_df[
                    "% Backchecked"
                ].fillna(0)
                enumerator_detailed_df["% Different"] = enumerator_detailed_df[
                    "% Different"
                ].fillna(0)

                # Convert percentages to strings with % symbol
                enumerator_detailed_df["% Backchecked"] = (
                    enumerator_detailed_df["% Backchecked"].astype(str) + "%"
                )
                enumerator_detailed_df["% Different"] = (
                    enumerator_detailed_df["% Different"].astype(str) + "%"
                )

                # Create DataFrame from enumerator statistics
                enumerator_detailed_df = pd.DataFrame.from_dict(
                    enumerator_detailed_stats, orient="index"
                )
                enumerator_detailed_df = enumerator_detailed_df.reset_index()
                enumerator_detailed_df.columns = [
                    "Enumerator ID",
                    "Total Surveys",
                    "Total Backchecks",
                    "Total Values Compared",
                    "Total Different",
                ]

                # Calculate percentages
                enumerator_detailed_df["% Backchecked"] = (
                    enumerator_detailed_df["Total Backchecks"]
                    / enumerator_detailed_df["Total Surveys"]
                    * 100
                ).round(2)

                enumerator_detailed_df["% Different"] = (
                    enumerator_detailed_df["Total Different"]
                    / enumerator_detailed_df["Total Values Compared"]
                    * 100
                ).round(2)

                # Handle division by zero
                enumerator_detailed_df["% Backchecked"] = enumerator_detailed_df[
                    "% Backchecked"
                ].fillna(0)
                enumerator_detailed_df["% Different"] = enumerator_detailed_df[
                    "% Different"
                ].fillna(0)

                # Convert percentages to strings with % symbol
                enumerator_detailed_df["% Backchecked"] = (
                    enumerator_detailed_df["% Backchecked"].astype(str) + "%"
                )
                enumerator_detailed_df["% Different"] = (
                    enumerator_detailed_df["% Different"].astype(str) + "%"
                )

                # Reorder columns as requested
                column_order = [
                    "Enumerator ID",
                    "Total Surveys",
                    "Total Backchecks",
                    "% Backchecked",
                    "Total Values Compared",
                    "Total Different",
                    "% Different",
                ]

                enumerator_detailed_df = enumerator_detailed_df[column_order]

                # Selection filter by enumid
                selected_enumerators = st.multiselect(
                    "Filter enumerators:",
                    enumerator_detailed_df["Enumerator ID"].unique(),
                )

                if selected_enumerators:
                    filtered_enumerator_stats = enumerator_detailed_df[
                        enumerator_detailed_df["Enumerator ID"].isin(
                            selected_enumerators
                        )
                    ]
                else:
                    filtered_enumerator_stats = enumerator_detailed_df

                # Display the filtered enumerator statistics table
                st.dataframe(
                    filtered_enumerator_stats,
                    use_container_width=True,
                    column_config={
                        "Enumerator ID": st.column_config.Column(width="small"),
                        "Total Surveys": st.column_config.NumberColumn(
                            format="%d", width="small"
                        ),
                        "Total Backchecks": st.column_config.NumberColumn(
                            format="%d", width="small"
                        ),
                        "% Backchecked": st.column_config.Column(width="small"),
                        "Total Values Compared": st.column_config.NumberColumn(
                            format="%d", width="small"
                        ),
                        "Total Different": st.column_config.NumberColumn(
                            format="%d", width="small"
                        ),
                        "% Different": st.column_config.Column(width="small"),
                    },
                )

            # New tab for "Backchecker Statistics"
            with tabs[2]:
                # Initialize dictionary to store backchecker statistics
                backchecker_stats = {}

                # For each selected variable, calculate statistics per
                # backchecker
                for var in backcheck_cols:
                    svy_col = f"_svy_{var}"
                    back_col = f"_bc_{var}"

                # Create comparison data for this variable
                comparison = pd.DataFrame(
                    {
                        "backchecker_id": merged_df[enum_bcer_column],
                        "survey_value": merged_df[svy_col].astype(str),
                        "backcheck_value": merged_df[back_col].astype(str),
                    }
                )

                # Mark matches/mismatches
                comparison["is_different"] = comparison.apply(
                    lambda x: str(x["survey_value"]).strip()
                    != str(x["backcheck_value"]).strip(),
                    axis=1,
                )

                # Group by backchecker and calculate statistics
                for backchecker_id in comparison["backchecker_id"].unique():
                    if backchecker_id not in backchecker_stats:
                        backchecker_stats[backchecker_id] = {
                            "total_backchecks": len(
                                comparison[
                                    comparison["backchecker_id"] == backchecker_id
                                ]
                            ),
                            "total_compared": 0,
                            "total_different": 0,
                        }

                    backchecker_data = comparison[
                        comparison["backchecker_id"] == backchecker_id
                    ]
                    backchecker_stats[backchecker_id]["total_compared"] += len(
                        backchecker_data
                    )
                    backchecker_stats[backchecker_id]["total_different"] += (
                        backchecker_data["is_different"].sum()
                    )

                # Create DataFrame from backchecker statistics
                backchecker_df = pd.DataFrame.from_dict(
                    backchecker_stats, orient="index"
                )
                backchecker_df = backchecker_df.reset_index()
                backchecker_df.columns = [
                    "Backchecker ID",
                    "Total Backchecks",
                    "Total Values Compared",
                    "Total Different",
                ]

                # Calculate percentage different
                backchecker_df["% Different"] = (
                    backchecker_df["Total Different"]
                    / backchecker_df["Total Values Compared"]
                    * 100
                ).round(2).astype(str) + "%"

                st.subheader("Backchecker Statistics")
                selected_backcheckers = st.multiselect(
                    "Filter backcheckers:",
                    backchecker_df["Backchecker ID"].unique(),
                )

                if selected_backcheckers:
                    filtered_backchecker_stats = backchecker_df[
                        backchecker_df["Backchecker ID"].isin(selected_backcheckers)
                    ]
                else:
                    filtered_backchecker_stats = backchecker_df

                # Display the filtered backchecker statistics table
                st.dataframe(
                    filtered_backchecker_stats,
                    use_container_width=True,
                    column_config={
                        "Backchecker ID": st.column_config.Column(width="medium"),
                        "Total Backchecks": st.column_config.NumberColumn(
                            format="%d", width="medium"
                        ),
                        "Total Values Compared": st.column_config.NumberColumn(
                            format="%d", width="medium"
                        ),
                        "Total Different": st.column_config.NumberColumn(
                            format="%d", width="medium"
                        ),
                        "% Different": st.column_config.Column(width="medium"),
                    },
                )

            # Process the selected variables
            for tab, var in zip(tabs[3:], backcheck_cols, strict=False):
                with tab:
                    st.subheader(f"Mismatches for {var}")

                    svy_col = f"_svy_{var}"
                    back_col = f"_bc_{var}"
                    enumid_var = f"_svy_{enumerator}"
                    is_numeric = var_types[var] == "Numeric"

                    # Create base comparison dataframe
                    comparison_df = pd.DataFrame(
                        {
                            "Unique Identifier": merged_df[survey_id],
                            "Enumerator id": merged_df[enumid_var],
                            "Backchecker id": merged_df[enum_bcer_column]
                            if enum_bcer_column in merged_df.columns
                            else pd.Series([None] * len(merged_df)),
                            "Selected Variable": var,
                            "Survey Value": merged_df[svy_col].astype(str),
                            "Backcheck Value": merged_df[back_col].astype(str),
                        }
                    )

                    # Calculate difference for numeric variables
                    if is_numeric:
                        try:
                            # Create separate numeric columns for calculation
                            survey_numeric = pd.to_numeric(
                                merged_df[svy_col], errors="coerce"
                            )
                            backcheck_numeric = pd.to_numeric(
                                merged_df[back_col], errors="coerce"
                            )

                            # Add difference column
                            comparison_df["Difference"] = (
                                survey_numeric - backcheck_numeric
                            )

                            # Format difference to handle NaN values
                            comparison_df["Difference"] = comparison_df[
                                "Difference"
                            ].apply(lambda x: f"{x:.2f}" if pd.notnull(x) else "N/A")
                        except Exception as e:
                            st.warning(
                                f"Could not calculate differences for {var}. Error: {e!s}"
                            )
                    # Add comparison column
                    comparison_df["Comparison"] = comparison_df.apply(
                        lambda x: "Match"
                        if str(x["Survey Value"]).strip()
                        == str(x["Backcheck Value"]).strip()
                        else "Mismatch",
                        axis=1,
                    )

                    # Filter for mismatches only
                    mismatches_df = comparison_df[
                        comparison_df["Comparison"] == "Mismatch"
                    ]

                    # Allow the user to filter the mismatches by enumerator ID
                    selected_enumerators = st.multiselect(
                        f"Filter mismatches for {var} by enumerator:",
                        mismatches_df["Enumerator id"].unique(),
                    )
                    if selected_enumerators:
                        filtered_mismatches = mismatches_df[
                            mismatches_df["Enumerator id"].isin(selected_enumerators)
                        ]
                    else:
                        filtered_mismatches = mismatches_df

                    # Display the filtered mismatches
                    st.dataframe(filtered_mismatches, use_container_width=True)

        else:
            st.info(
                "There was no backcheck data frame found. Please upload the backcheck data first."
            )
