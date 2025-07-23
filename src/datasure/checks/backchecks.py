import pandas as pd
import plotly.express as px
import streamlit as st

from datasure.utils import get_check_config_settings

##### Backchecks #####


def backchecks_report(project_id: str, survey_data, backcheck_data, page_num) -> None:
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

        survey_cols = survey_data.columns
        backcheck_cols_list = backcheck_data.columns

        # get list of columns in both surey and backcheck data
        common_cols = [col for col in survey_data.columns if col in backcheck_cols_list]

        meta_col, enum_col, agg_col = st.columns(spec=3, border=True)

        # Get config page defaults
        (
            _,
            _,
            config_survey_key,
            config_survey_id,
            config_survey_date,
            config_enumerator,
            _,
            _,
        ) = get_check_config_settings(
            project_id=project_id,
            page_row_index=page_num - 1,
        )

        with meta_col:
            duration = st.selectbox(
                "Duration",
                options=survey_cols,
                help="Column containing survey duration",
                key="duration_backcheck",
                index=None,
            )
            default_date = config_survey_date
            default_date_index = survey_cols.get_loc(default_date)
            date = st.selectbox(
                "Date",
                options=survey_cols,
                help="Column containing survey date",
                key="date_backcheck",
                index=default_date_index,
            )
            formversion = st.selectbox(
                "Form Version",
                options=survey_cols,
                help="Column containing survey form version",
                key="formversion_backcheck",
                index=None,
            )

        with enum_col:
            default_enumerator = config_enumerator
            default_enumerator_index = survey_cols.get_loc(default_enumerator)

            enumerator = st.selectbox(
                "Enumerator",
                options=survey_cols,
                help="Column containing survey enumerator",
                key="enumerator_backcheck",
                index=default_enumerator_index,
            )
            team = st.selectbox(  # noqa: F841
                "Enumerator Team",
                options=survey_cols,
                help="Column containing survey team",
                key="team_backcheck",
                index=None,
            )
            backchecker = st.selectbox(
                "Back Checker",
                options=backcheck_cols_list,
                help="Column containing back check enumerator",
                key="backchecker_backcheck",
                index=None,
            )
            bc_team = st.selectbox(  # noqa: F841
                "Back Check Team",
                options=backcheck_cols_list,
                help="Column containing survey team",
                key="backcheck_team_backcheck",
                index=None,
            )

        with agg_col:
            default_survey_id = config_survey_id
            default_survey_id_index = survey_cols.get_loc(default_survey_id)
            survey_id = st.selectbox(
                "Survey ID",
                options=survey_cols,
                help="Column containing survey ID",
                key="surveyid_backcheck",
                index=default_survey_id_index,
            )
            default_survey_key = config_survey_key
            default_survey_key_index = survey_cols.get_loc(default_survey_key)
            survey_key = st.selectbox(
                "Survey Key",
                options=survey_cols,
                help="Column containing survey key",
                key="surveykey_backcheck",
                index=default_survey_key_index,
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
        # drop duplicates
        if drop_duplicates:
            survey_data = survey_data.sort_values(
                by=date, ascending=False
            ).drop_duplicates(subset=[survey_id], keep="first")
            backcheck_data = backcheck_data.sort_values(
                by=date, ascending=False
            ).drop_duplicates(subset=[survey_id], keep="first")

        # merge survey and backcheck data
        survey_df_bc = survey_data[[survey_id, enumerator, consent, date]].add_prefix(
            "_svy_"
        )
        # rename enumerator and survey_id columns removing prefix
        survey_df_bc.rename(columns={"_svy_" + survey_id: survey_id}, inplace=True)
        backcheck_df_bc = backcheck_data[
            [survey_id, backchecker, consent, date]
        ].add_prefix("_bc_")
        # rename enumerator and survey_id columns removing prefix
        backcheck_df_bc.rename(columns={"_bc_" + survey_id: survey_id}, inplace=True)

        merged_df = pd.merge(survey_df_bc, backcheck_df_bc, on=survey_id, how="inner")

        # Find matching variable pairs (survey and backcheck variables)
        svy_vars = [col for col in merged_df.columns if col.startswith("_svy_")]  # noqa: F841
        back_vars = [col for col in merged_df.columns if col.startswith("_bc_")]  # noqa: F841

        # Column category selection
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
            with st.popover(
                "Add a backcheck column",
                icon=":material/add:",
                use_container_width=True,
            ):
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
                        "absolute value",
                        "range",
                        "percentage",
                    ],
                    help="Select the type of range condition",
                    key="ok range",
                )
                if ok_range_type == "absolute value":
                    absolute_ok_range = st.number_input(
                        label="Absolute Value",
                        min_value=0,
                        help="Enter the absolute value",
                    )
                    ok_range = f"{absolute_ok_range}"
                elif ok_range_type == "percentage":
                    ok_range_percentage = st.number_input(
                        "Percentage", min_value=0, help="Enter a percentage value"
                    )
                    ok_range = f"{ok_range_percentage}%"
                elif ok_range_type == "range":
                    range_min = st.number_input(
                        "Minimum Value",
                        max_value=0,
                        help="Enter the minimum value (less than zero)",
                    )
                    range_max = st.number_input(
                        "Maximum Value",
                        min_value=0,
                        help="Enter the maximum value (greater than zero)",
                    )
                    ok_range = f"[{range_min} , {range_max}]"
                else:
                    ok_range = ""

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
                    comparison_condition = f"{compare_condition} {contains_condition}"
                elif compare_condition == "Treat these values as the same:":
                    same_condition = st.text_input(
                        "Enter the values separated by a comma",
                        help="Enter the values separated by a comma",
                    )
                    comparison_condition = f"{compare_condition} {same_condition}"
                elif (
                    compare_condition == "Do not compare missing values or null values"
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
            column_config_data,
            survey_data,
            backcheck_data,
            survey_id,
            enumerator,
            backchecker,
            summary_col=None,
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

            summary_col: str, optional
                Column name to group results by. If None, returns ungrouped summary.

            Returns
            -------
            pd.DataFrame
                Summary DataFrame with columns:
                ["Column", "Data Type", "Category", "# Surveys", "# Backchecks",
                    "# Compared", "# Different", "Error Rate"]
            """
            # update datasets
            survey_data = survey_data.add_prefix("_svy_").rename(
                columns={"_svy_" + survey_id: survey_id}
            )
            backcheck_data = backcheck_data.add_prefix("_bc_").rename(
                columns={"_bc_" + survey_id: survey_id}
            )
            enumerator = "_svy_" + enumerator
            backchecker = "_bc_" + backchecker
            svy_col = None
            bc_col = None

            # summary column logic
            if summary_col:
                # backchecker case
                if summary_col == "backchecker":
                    summary_col = [
                        c for c in backcheck_data.columns if backchecker in c
                    ]
                    svy_summary_cols = [survey_id, enumerator, svy_col]
                    bc_summary_cols = [survey_id, backchecker, bc_col] + summary_col

                else:
                    summary_col = [c for c in survey_data.columns if summary_col in c]
                    svy_summary_cols = [survey_id, enumerator, svy_col] + summary_col
                    bc_summary_cols = [survey_id, backchecker, bc_col]
            else:
                svy_summary_cols = [survey_id, enumerator, svy_col]
                bc_summary_cols = [survey_id, backchecker, bc_col]

            summary_data = []

            # define merged results dataframe
            merged_results_df = pd.DataFrame()

            for _, row in column_config_data.iterrows():
                column_name = row["column"]
                column_type = row["category"]
                ok_range = row["ok range"]
                comparison_condition = row["comparison condition"]
                # Prepare survey and backcheck data
                svy_col = f"_svy_{column_name}"
                bc_col = f"_bc_{column_name}"

                # update summary columns
                svy_summary_cols_n = svy_summary_cols.copy()
                bc_summary_cols_n = bc_summary_cols.copy()
                svy_summary_cols_n[2] = svy_col
                bc_summary_cols_n[2] = bc_col

                # remove any duplicates
                svy_summary_cols_n = list(set(svy_summary_cols_n))
                bc_summary_cols_n = list(set(bc_summary_cols_n))

                survey_col_data = survey_data[svy_summary_cols_n]
                backcheck_col_data = backcheck_data[bc_summary_cols_n]

                # # Merge survey and backcheck data
                merged_svy_bc_df = pd.merge(
                    survey_col_data, backcheck_col_data, on=survey_id, how="inner"
                )

                merged_svy_bc_df["variable"] = svy_col.replace("_svy_", "")

                # Add comparison result column based on conditions
                merged_svy_bc_df["comparison result"] = "not compared"  # default value

                # Helper function to compare values based on conditions
                def compare_values(
                    row, svy_col, bc_col, ok_range, comparison_condition
                ):
                    if comparison_condition:
                        # Handle missing values first
                        if comparison_condition == "ignore_missing_values":
                            if pd.isna(row[svy_col]) or pd.isna(row[bc_col]):
                                return "not compared"

                        # Handle values to exclude from comparison
                        elif "Do not compare if the values contain:" in str(
                            comparison_condition
                        ):
                            exclude_values = (
                                comparison_condition.split(":")[1].strip().split(",")
                            )
                            if (
                                str(row[svy_col]) in exclude_values
                                or str(row[bc_col]) in exclude_values
                            ):
                                return "not compared"

                        # Handle values to treat as same
                        elif "Treat these values as the same:" in str(
                            comparison_condition
                        ):
                            same_values = (
                                comparison_condition.split(":")[1].strip().split(",")
                            )
                            svy_val = str(row[svy_col])
                            bc_val = str(row[bc_col])
                            if svy_val in same_values and bc_val in same_values:
                                return "not different"

                    # Handle OK ranges
                    if ok_range:
                        try:
                            svy_val = float(row[svy_col])
                            bc_val = float(row[bc_col])
                            diff = abs(svy_val - bc_val)

                            if "%" in ok_range:  # Percentage range
                                allowed_diff = (
                                    float(ok_range.replace("%", "")) / 100 * svy_val
                                )
                                if diff <= allowed_diff:
                                    return "not different"
                            elif "[" in ok_range:  # Between range
                                min_val, max_val = map(
                                    float, ok_range.strip("[]").split(",")
                                )
                                if min_val <= diff <= max_val:
                                    return "not different"
                            else:  # Absolute value
                                allowed_diff = float(ok_range)
                                if diff <= allowed_diff:
                                    return "not different"

                            return "different"  # noqa: TRY300
                        except (ValueError, TypeError):
                            return "not compared"
                    # Default comparison
                    return (
                        "not different"
                        if str(row[svy_col]).strip() == str(row[bc_col]).strip()
                        else "different"
                    )

                # Apply comparison function to each row
                merged_svy_bc_df["comparison result"] = merged_svy_bc_df.apply(
                    lambda row: compare_values(
                        row,
                        svy_col,  # noqa: B023
                        bc_col,  # noqa: B023
                        ok_range,  # noqa: B023
                        comparison_condition,  # noqa: B023
                    ),
                    axis=1,
                )
                merged_svy_bc_df = merged_svy_bc_df.rename(
                    columns={svy_col: "survey value", bc_col: "back check value"}
                )

                # Add summary column if provided
                if summary_col:
                    selected_merged_df_cols = [
                        survey_id,
                        summary_col[0],
                        enumerator,
                        backchecker,
                        "variable",
                        "survey value",
                        "back check value",
                        "comparison result",
                    ]
                    selected_merged_df_cols = list(set(selected_merged_df_cols))
                else:
                    selected_merged_df_cols = [
                        survey_id,
                        enumerator,
                        backchecker,
                        "variable",
                        "survey value",
                        "back check value",
                        "comparison result",
                    ]

                merged_svy_bc_df = merged_svy_bc_df[selected_merged_df_cols].copy()
                merged_results_df = pd.concat(
                    [merged_results_df, merged_svy_bc_df], ignore_index=True
                )

                # Calculate metrics
                data_types_dict = {
                    "float64": "Numeric",
                    "int64": "Numeric",
                    "object": "String",
                    "datetime64[ns]": "Date",
                }
                data_type = data_types_dict[survey_data[svy_col].dtype.name]

                if summary_col:
                    # Group by summary column
                    groupby_obj = merged_svy_bc_df.groupby(summary_col)
                    for group_name, group_df in groupby_obj:
                        total_surveys = len(
                            merged_svy_bc_df[
                                merged_svy_bc_df[summary_col] == group_name
                            ]
                        )
                        total_backchecks = len(
                            merged_svy_bc_df[
                                merged_svy_bc_df[survey_id].isin(group_df[survey_id])
                            ]
                        )
                        total_compared = len(
                            group_df[group_df["comparison result"] != "not compared"]
                        )
                        total_different = len(
                            group_df[group_df["comparison result"] == "different"]
                        )
                        error_rate = (
                            (total_different / total_compared * 100)
                            if total_compared > 0
                            else 0
                        )

                        summary_data.append(
                            {
                                "column": column_name,
                                "data type": data_type,
                                "category": column_type,
                                summary_col[0]: group_name[0],
                                "# surveys": total_surveys,
                                "# backchecks": total_backchecks,
                                "# compared": total_compared,
                                "# different": total_different,
                                "error rate": f"{error_rate:.2f}%",
                            }
                        )
                else:
                    # Calculate overall metrics
                    total_surveys = len(survey_data)
                    total_backchecks = len(backcheck_data)
                    total_compared = merged_svy_bc_df[
                        merged_svy_bc_df["comparison result"] != "not compared"
                    ].shape[0]
                    total_different = merged_svy_bc_df[
                        merged_svy_bc_df["comparison result"] == "different"
                    ].shape[0]
                    error_rate = (
                        (total_different / total_compared * 100)
                        if total_compared > 0
                        else 0
                    )

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
            # clean merged table results
            merged_results_df = merged_results_df.rename(
                columns={enumerator: "Enumerator", backchecker: "Back Checker"}
            )

            return pd.DataFrame(summary_data), merged_results_df

        # generate the column summary without group value
        column_category_summary, svy_bc_comparison_df = generate_column_summary(
            column_config_data=bc_column_config_df,
            survey_data=survey_data,
            backcheck_data=backcheck_data,
            survey_id=survey_id,
            enumerator=enumerator,
            backchecker=backchecker,
            summary_col=None,
        )

        # Calculate total backcheck error rate
        if column_category_summary.shape[0] > 0:
            total_backcheck_error_rate = (
                column_category_summary["# different"].sum()
                / column_category_summary["# compared"].sum()
            ) * 100
            st.session_state.total_backcheck_error_rate = total_backcheck_error_rate

        else:
            st.session_state.total_backcheck_error_rate = "n/a"

        # Overview Statistics
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
            try:
                st.metric(
                    "Total backcheck error rate",
                    f"{st.session_state.total_backcheck_error_rate:.0f}%",
                )
            except (AttributeError, TypeError, ValueError):
                st.metric("Total backcheck error rate", "n/a")

        cl1, cl2, cl3 = st.columns(3)
        # define chart colors
        chart_colors = ["#35904A", "lightgrey"]
        with cl1:
            if backcheck_goal == 0:
                st.warning("Please set a target for backchecks")
            else:
                # Calculate percentage of backchecks completed
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
                    title=dict(
                        xanchor="left",
                        y=0.9,
                        yanchor="top",
                        font=dict(weight="normal"),
                    ),
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
                backcheck_sum_df["total_backchecks"] / backcheck_sum_df["total_surveys"]
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
                title=dict(
                    xanchor="left", y=0.9, yanchor="top", font=dict(weight="normal")
                ),
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
                    showarrow=False,
                )
            )

            # Display the pie chart
            st.plotly_chart(fig_enum)

        # backcheck category columns
        if column_category_summary.empty:
            st.write("Backcheck category summary")
            st.warning("No backcheck columns set")
            st.write("")
        else:
            st.write("")
            # backcheck category 1 error rate
            category_1_summary = column_category_summary[
                column_category_summary["category"] == 1
            ]
            if category_1_summary.shape[0] > 0:
                st.write("Backcheck category 1 error rates")
                type1_1, type1_2, type1_3 = st.columns(3)
                category_1_summary = column_category_summary[
                    column_category_summary["category"] == 1
                ]
                category_1_error_rate = (
                    category_1_summary["# different"].sum()
                    / category_1_summary["# compared"].sum()
                ) * 100
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
                    f"{category_1_error_rate:.0f}%",
                )
                st.write("")

            # backcheck category 2 error rate
            category_2_summary = column_category_summary[
                column_category_summary["category"] == 2
            ]
            if category_2_summary.shape[0] > 0:
                st.write("Backcheck category 2 error rates")
                type2_1, type2_2, type2_3 = st.columns(3)
                category_2_summary = column_category_summary[
                    column_category_summary["category"] == 2
                ]
                category_2_error_rate = (
                    category_2_summary["# different"].sum()
                    / category_2_summary["# compared"].sum()
                ) * 100
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
                    f"{category_2_error_rate:.0f}%",
                )
                st.write("")

            # backcheck category 3 error rate
            category_3_summary = column_category_summary[
                column_category_summary["category"] == 3
            ]
            if category_3_summary.shape[0] > 0:
                st.write("Backcheck category 3 error rates")
                type3_1, type3_2, type3_3 = st.columns(3)
                category_3_summary = column_category_summary[
                    column_category_summary["category"] == 3
                ]
                category_3_error_rate = (
                    category_3_summary["# different"].sum()
                    / category_3_summary["# compared"].sum()
                ) * 100
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
                    f"{category_3_error_rate:.0f}%",
                )
            st.write("")

        # error trends
        error_trends_category_summary, _ = generate_column_summary(
            column_config_data=bc_column_config_df,
            survey_data=survey_data,
            backcheck_data=backcheck_data,
            survey_id=survey_id,
            enumerator=enumerator,
            backchecker=backchecker,
            summary_col=date,
        )

        if error_trends_category_summary.empty:
            st.write("Error Trends")
            st.warning("No backcheck columns set")
            st.write("")
        else:
            st.subheader("Error Trends")
            trend_cols = st.columns([2, 1])

            # get the list of categories
            category_list = error_trends_category_summary["category"].unique().tolist()
            date_col = [  # noqa: RUF015
                col for col in error_trends_category_summary if date in col
            ][0]

            error_trends_category_summary[date_col] = pd.to_datetime(
                error_trends_category_summary[date_col]
            )

            with trend_cols[0]:
                selected_categories = st.multiselect(
                    "Select backcheck categories",
                    options=category_list,
                    default=category_list,
                    key="trend_categories",
                )

            with trend_cols[1]:
                # create weekly and monthly options based on submission date
                time_period_options = ["Daily"]
                if (
                    error_trends_category_summary[date_col]
                    .dt.to_period("W-SUN")
                    .nunique()
                    > 1
                ):
                    time_period_options.append("Weekly")
                if (
                    error_trends_category_summary[date_col].dt.to_period("M").nunique()
                    > 1
                ):
                    time_period_options.append("Monthly")

                # Select time period
                time_period = st.selectbox(
                    "Select time period",
                    options=time_period_options,
                    key="time_period",
                )

            if selected_categories:
                # Create trends dataframe
                trends_df = error_trends_category_summary[
                    error_trends_category_summary["category"].isin(selected_categories)
                ].copy()
                trends_df["date"] = pd.to_datetime(trends_df["_svy_" + date])

                # filter based on selected time period
                if time_period == "Weekly":
                    trends_df["date"] = (
                        trends_df["date"].dt.to_period("W-SUN").dt.start_time
                    )
                elif time_period == "Monthly":
                    trends_df["date"] = trends_df["date"].dt.to_period("M").astype(str)
                else:  # Daily
                    trends_df["date"] = trends_df["date"].dt.date

                # Calculate error rates for each category and date
                error_trends_df = (
                    trends_df.groupby(["date", "category"])
                    .aggregate({"# compared": "sum", "# different": "sum"})
                    .reset_index()
                )
                error_trends_df["error_rate"] = (
                    error_trends_df["# different"] / error_trends_df["# compared"]
                ) * 100
                error_trends_df["error_rate"] = (
                    error_trends_df["error_rate"].fillna(0).round(0)
                )

                # Create line chart
                fig = px.line(
                    error_trends_df,
                    x="date",
                    y="error_rate",
                    color="category",
                    title=f"{time_period} Error Rate Trends by Category",
                    labels={
                        "date": "Date",
                        "error_rate": "Error Rate (%)",
                        "category": "Category",
                    },
                )

                fig.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Error Rate (%)",
                    hovermode="x unified",
                )

                st.plotly_chart(fig, use_container_width=True)

            st.write("")

        # column statistics
        if column_category_summary.empty:
            st.write("Column Statistics")
            st.warning("No backcheck columns set")
        else:
            st.subheader("Column Statistics")
            st.dataframe(
                column_category_summary, use_container_width=True, hide_index=True
            )
        st.write("")

        # enumerator statistics
        enumerator_category_summary, _var_sum_df = generate_column_summary(
            column_config_data=bc_column_config_df,
            survey_data=survey_data,
            backcheck_data=backcheck_data,
            survey_id=survey_id,
            enumerator=enumerator,
            backchecker=backchecker,
            summary_col=enumerator,
        )
        if column_category_summary.empty:
            st.write("Enumerator Statistics")
            st.warning("No backcheck columns set")
        else:
            st.subheader("Enumerator Statistics")

            enumerator_statistics = (
                enumerator_category_summary.groupby(["_svy_" + enumerator])
                .agg(
                    {
                        "# surveys": "sum",
                        "# backchecks": "sum",
                        "# compared": "sum",
                        "# different": "sum",
                    }
                )
                .reset_index()
            )
            enumerator_statistics["% back checked"] = enumerator_statistics.apply(
                lambda x: f"{(x['# backchecks'] / x['# surveys']) * 100:.2f}%", axis=1
            )
            enumerator_statistics["Error Rate"] = enumerator_statistics.apply(
                lambda x: f"{(x['# different'] / x['# compared']) * 100:.2f}%", axis=1
            )

            enumerator_statistics = enumerator_statistics.rename(
                columns={
                    "_svy_" + enumerator: "Enumerator",
                    "# backchecks": "# back checked",
                    "# compared": "# of values compared",
                    "# different": "# of values different",
                }
            )
            er_stats_cols = [
                "Enumerator",
                "# surveys",
                "# back checked",
                "% back checked",
                "# of values compared",
                "# of values different",
                "Error Rate",
            ]
            enumerator_statistics = enumerator_statistics[er_stats_cols].copy()

            # filter by enumerator
            selected_enum_list = st.multiselect(
                "Filter enumerators:",
                enumerator_statistics["Enumerator"].unique(),
            )

            if selected_enum_list:
                filtered_enumerator_statistics = enumerator_statistics[
                    enumerator_statistics["Enumerator"].isin(selected_enum_list)
                ]
            else:
                filtered_enumerator_statistics = enumerator_statistics

            st.dataframe(
                filtered_enumerator_statistics,
                use_container_width=True,
                hide_index=True,
            )
        st.write("")

        # backchecker statistics
        if column_category_summary.empty:
            st.write("Backchecker Statistics")
            st.warning("No backcheck columns set")
        else:
            st.subheader("Backchecker Statistics")
            backchecker_statistics, _ = generate_column_summary(
                column_config_data=bc_column_config_df,
                survey_data=survey_data,
                backcheck_data=backcheck_data,
                survey_id=survey_id,
                enumerator=enumerator,
                backchecker=backchecker,
                summary_col="backchecker",
            )
            bcer_col = [  # noqa: RUF015
                col for col in backchecker_statistics.columns if backchecker in col
            ][0]

            backchecker_statistics = backchecker_statistics.rename(
                columns={
                    bcer_col: "Back Checker",
                    "# backchecks": "# back checked",
                    "# compared": "# values compared",
                    "error rate": "Error Rate",
                }
            )
            backchecker_statistics = backchecker_statistics[
                [
                    "Back Checker",
                    "# back checked",
                    "# values compared",
                    "# different",
                    "Error Rate",
                ]
            ].copy()
            # filter by enumerator
            selected_bcer_list = st.multiselect(
                "Filter back checkers:",
                backchecker_statistics["Back Checker"].unique(),
            )

            if selected_bcer_list:
                filtered_backchecker_statistics = backchecker_statistics[
                    backchecker_statistics["Back Checker"].isin(selected_bcer_list)
                ]
            else:
                filtered_backchecker_statistics = backchecker_statistics

            st.dataframe(
                filtered_backchecker_statistics,
                use_container_width=True,
                hide_index=True,
            )
        st.write("")

        if column_category_summary.empty:
            st.write("Comparison Details")
            st.warning("No backcheck columns set")
        else:
            st.subheader("Comparison Details")
            # filter by variable
            selected_var_list = st.multiselect(
                "Select variables to display:",
                svy_bc_comparison_df["variable"].unique(),
            )

            if selected_var_list:
                filtered_comparison_df = svy_bc_comparison_df[
                    svy_bc_comparison_df["variable"].isin(selected_var_list)
                ]
            else:
                filtered_comparison_df = svy_bc_comparison_df

            st.dataframe(
                filtered_comparison_df, use_container_width=True, hide_index=True
            )
        st.write("")
