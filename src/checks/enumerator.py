import pandas as pd
import plotly.express as px
import streamlit as st

##### Enumerator Statistics #####


def enumerator_report(data, page_num) -> None:
    """Generate enumerator report.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing survey data.
    page_num : int

    Returns
    -------
    None
    """
    #### Temp Remove Later
    analyze_backcheck = False
    backcheck_data = None
    merged_df = None

    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for enumerator report")

        survey_cols = data.columns

        st.write("---")
        st.markdown("### Select columns to include in summary report")

        meta_col, enum_col, agg_col = st.columns(spec=3, border=True)

        with meta_col:
            duration = st.selectbox(
                "Duration",
                options=survey_cols,
                help="Column containing survey duration",
                key="duration_enumerator",
                index=None,
            )
            if duration:
                duration_in_minutes = st.toggle("Calculate duration in minutes")

            date = st.selectbox(
                "Date",
                options=survey_cols,
                help="Column containing survey date",
                key="date_enumerator",
                index=None,
            )
            formversion = st.selectbox(
                "Form Version",
                options=survey_cols,
                help="Column containing survey form version",
                key="formversion_enumerator",
                index=None,
            )

        with enum_col:
            by = st.selectbox(
                "Group by",
                options=survey_cols,
                help="Column to group summary report by",
                key="groupby_enumerator",
                index=None,
            )
            enumerator = st.selectbox(
                "Enumerator",
                options=survey_cols,
                help="Column containing survey enumerator",
                key="enumerator_enumerator",
                index=None,
            )
            team = st.selectbox(
                "Team",
                options=survey_cols,
                help="Column containing survey team",
                key="team_enumerator",
                index=None,
            )

        with agg_col:
            survey_id = st.selectbox(
                "Survey ID",
                options=survey_cols,
                help="Column containing survey ID",
                key="surveyid_enumerator",
                index=None,
            )
            survey_key = st.selectbox(
                "Survey Key",
                options=survey_cols,
                help="Column containing survey key",
                key="surveykey_enumerator",
                index=None,
            )

            consent = st.selectbox(
                "Consent",
                options=survey_cols,
                help="Column containing survey consent",
                key="consent_enumerator",
                index=None,
            )

            if consent:
                consent_options = data[consent].unique().tolist()
                consent_val = st.multiselect(
                    "Consent value(s)",
                    options=consent_options,
                    help="Value(s) indicating valid consent",
                    key="consent_val_enumerator",
                )

            outcome = st.selectbox(
                "Outcome",
                options=survey_cols,
                help="Column containing survey outcome",
                key="outcome_enumerator",
                index=None,
            )

            if outcome:
                outcome_options = data[outcome].unique().tolist()
                outcome_val = st.multiselect(  # noqa: F841
                    "Outcome value(s)",
                    options=outcome_options,
                    help="Value(s) indicating completed survey",
                    key="outcome_val_enumerator",
                )

        st.write("---")
        st.markdown("### Tracking Options")

        # number of interviews expected
        total_goal = st.number_input(  # noqa: F841
            "Total goal",
            min_value=0,
            help="Total number of interviews expected",
            key="total_goal_enumerator",
        )

        # define a save settings button
        save_settings = st.button("Save settings", key="save_settings_enumerator")  # noqa: F841

    # Check that required options have been selected. If not, display a info message
    if not all(
        [
            duration,
            date,
            formversion,
            by,
            enumerator,
            team,
            survey_id,
            survey_key,
            consent,
            outcome,
        ]
    ):
        st.info("Please select all required options to generate the enumerator report")
        return

    # quick overview metrics
    st.subheader("Overview")
    data[date] = pd.to_datetime(data[date])
    data = data.sort_values(by=[enumerator, date])
    data["submission_date_format"] = data[date].dt.strftime("%b %d, %Y")
    daily_submissions_sum = (
        data.groupby(["submission_date_format", enumerator])[survey_key]
        .count()
        .rename("count")
        .reset_index()
    )
    active_date_cut_off = pd.to_datetime("today").date() - pd.Timedelta(weeks=1)
    daily_submissions_sum["active"] = pd.to_datetime(
        data["submission_date_format"]
    ) > pd.to_datetime(active_date_cut_off)
    num_active_enumerators = daily_submissions_sum[daily_submissions_sum["active"]][
        enumerator
    ].unique()

    m1, m2, m3 = st.columns(3)
    num_enumerators = data[enumerator].nunique()
    num_teams = data[team].nunique() if team else "n/a"
    min_submissions = daily_submissions_sum["count"].min()
    max_submissions = daily_submissions_sum["count"].max()
    avg_submissions = int(daily_submissions_sum["count"].mean())

    pct_active_enumerators = (
        f"{(len(num_active_enumerators) / num_enumerators) * 100:.0f}%"
    )

    m1.metric("Total number of enumerators", num_enumerators)
    m2.metric("Total number of teams", num_teams)
    m3.metric("Active enumerators (past 1 week)", pct_active_enumerators)

    n1, n2, n3 = st.columns(3)
    n1.metric("Minimum number of submissions", min_submissions)
    n2.metric("Highest number of submissions", max_submissions)
    n3.metric("Average number of submissions", avg_submissions)

    # Enumerator summary table
    summary_df = (
        data.groupby(enumerator)
        .agg(
            first_submission=("submission_date_format", "first"),
            last_submission=("submission_date_format", "last"),
            total_submissions=(survey_key, "count"),
            total_days_worked=("submission_date_format", "nunique"),
        )
        .reset_index()
        .rename(
            columns={
                "first_submission": "first date",
                "last_submission": "last date",
                "total_submissions": "# of submissions",
                "total_days_worked": "# of days worked",
            }
        )
    )

    # Calculate number of submissions this month, week, and day
    today = pd.to_datetime("today").normalize()
    start_of_month = today.replace(day=1)
    start_of_week = today - pd.Timedelta(days=today.weekday())

    data["submission_date_format"] = pd.to_datetime(data["submission_date_format"])
    summary_df["# of submissions (today)"] = (
        data[data["submission_date_format"] == today.strftime("%b %d, %Y")]
        .groupby(enumerator)[survey_key]
        .count()
        .reindex(summary_df[enumerator])
        .fillna(0)
        .astype(int)
        .values
    )
    summary_df["# of submissions (this week)"] = (
        data[data["submission_date_format"] >= start_of_week]
        .groupby(enumerator)[survey_key]
        .count()
        .reindex(summary_df[enumerator])
        .fillna(0)
        .astype(int)
        .values
    )
    summary_df["# of submissions (this month)"] = (
        data[data["submission_date_format"] >= start_of_month]
        .groupby(enumerator)[survey_key]
        .count()
        .reindex(summary_df[enumerator])
        .fillna(0)
        .astype(int)
        .values
    )

    # convert duration to minutes if necessary
    if duration_in_minutes:
        data[duration] = data[duration].apply(lambda x: round(x / 60, 1))

    summary_df["minimum duration"] = (
        data.groupby(enumerator)[duration].min().reindex(summary_df[enumerator]).values
    )
    summary_df["median duration"] = (
        data.groupby(enumerator)[duration]
        .median()
        .reindex(summary_df[enumerator])
        .values
    )
    summary_df["mean duration"] = (
        data.groupby(enumerator)[duration].mean().reindex(summary_df[enumerator]).values
    )
    summary_df["maximum duration"] = (
        data.groupby(enumerator)[duration].max().reindex(summary_df[enumerator]).values
    )

    # Calculate percentage of missing values for each enumerator
    def calculate_missing_values(data, data_cols, index_cols):
        max_vals_count = data.shape[0] * len(data_cols)
        missing_values_df = data.pivot_table(
            index=index_cols, values=data_cols, aggfunc=lambda x: x.isna().sum()
        ).reset_index()
        missing_values_df["missing"] = missing_values_df.iloc[:, len(index_cols) :].sum(
            axis=1
        )
        missing_values_df["% missing"] = (
            missing_values_df["missing"] / max_vals_count * 100
        ).apply(lambda x: f"{x:.0f}%")
        return missing_values_df[index_cols + ["% missing"]]

    index_cols = ["enumerator"]
    data_cols = [x for x in data.columns if x != enumerator]
    missing_values_df = calculate_missing_values(data, data_cols, index_cols)

    # Merge missing values percentage with summary_df
    summary_df = summary_df.merge(missing_values_df, on=enumerator, how="left")
    st.dataframe(summary_df, hide_index=True)

    # Toggle for days, weeks, or months view
    st.markdown("##### Productivity")
    view_option = st.radio(
        "Select View:",
        ("Days", "Weeks", "Months"),
        index=0,
        key="view_option_enumerator",
        horizontal=True,
    )

    # Create a new column for the selected view option
    if view_option == "Days":
        data["view_period"] = data[date].dt.strftime("%d-%m-%Y")
        view_summary_df = (
            data.groupby([enumerator, "view_period"])
            .agg(total_submissions=(survey_key, "count"))
            .reset_index()
        )
    elif view_option == "Weeks":
        week_start_day_options = st.selectbox(
            label="Select the first day of the week",
            options=[
                "Monday",
                "Tuesday",
                "Wednesday",
                "Thursday",
                "Friday",
                "Saturday",
                "Sunday",
            ],
            index=0,
            key="project_week_start_day",
        )
        week_start_day = "W-" + str.upper(week_start_day_options[:3])
        week_start_end_dict = {
            "W-SUN": "W-SAT",
            "W-MON": "W-SUN",
            "W-TUE": "W-MON",
            "W-WED": "W-TUE",
            "W-THU": "W-WED",
            "W-FRI": "W-THU",
            "W-SAT": "W-FRI",
        }
        week_end_day = week_start_end_dict[week_start_day]

        data["view_period"] = pd.to_datetime(
            data[date].dt.strftime("%d-%m-%Y"), dayfirst=True
        )
        data["view_period"] = (
            data["view_period"].dt.to_period(week_end_day).dt.start_time
        )

        first_submission_date = min([d.date() for d in data["view_period"].unique()])
        last_submission_date = max([d.date() for d in data["view_period"].unique()])

        first_submission_week_date = (
            pd.to_datetime(first_submission_date)
            .to_period(week_end_day)
            .to_timestamp()
            .date()
        )
        last_submission_week_date = (
            pd.to_datetime(last_submission_date)
            .to_period(week_end_day)
            .to_timestamp()
            .date()
        )

        starting_week_dates = pd.date_range(
            start=first_submission_week_date,
            end=last_submission_week_date,
            freq=week_start_day,
        )

        starting_week_dates_dict = {}
        enum_list = [c for c in data[enumerator].unique()]
        for d in starting_week_dates:
            starting_week_dates_dict[d] = enum_list

        starting_week_dates_df = pd.DataFrame(
            starting_week_dates_dict.items(), columns=["view_period", enumerator]
        )
        enum_list_df = pd.DataFrame(starting_week_dates_df[enumerator].explode())
        starting_week_dates_df = pd.merge(
            enum_list_df,
            starting_week_dates_df["view_period"],
            left_index=True,
            right_index=True,
        )

        view_summary_df = (
            data.groupby([enumerator, "view_period"])
            .agg(total_submissions=(survey_key, "count"))
            .reset_index()
        )
        view_summary_df = pd.merge(
            starting_week_dates_df,
            view_summary_df,
            on=["enumerator", "view_period"],
            how="left",
        ).fillna(0)
        view_summary_df["view_period"] = pd.to_datetime(
            view_summary_df["view_period"]
        ).dt.strftime("%d-%m-%Y")

    else:
        data["view_period"] = data[date].dt.strftime("%b-%Y")
        view_summary_df = (
            data.groupby([enumerator, "view_period"])
            .agg(total_submissions=(survey_key, "count"))
            .reset_index()
        )

    # create a pivot table for the view summary
    view_summary_pivot = view_summary_df.pivot_table(
        index=enumerator,
        columns="view_period",
        values="total_submissions",
        fill_value=0,
    ).reset_index()
    view_summary_pivot.insert(
        1, "Total submissions", view_summary_pivot.sum(axis=1, numeric_only=True)
    )

    # Display view summary
    st.dataframe(view_summary_pivot, hide_index=True, use_container_width=True)

    # create enumerator statistics

    st.markdown("##### Statistics")
    s1, s2 = st.columns(2)
    with s1:
        selected_columns = st.multiselect(
            "Select columns:",
            options=data.select_dtypes("number").columns,
            default=duration,
            help="Select columns to include in statistics",
            key="selected_columns_enumerator",
        )
    with s2:
        statistics_options = st.multiselect(
            "Select statistics:",
            options=[
                "count",
                "min",
                "mean",
                "median",
                "max",
                "std",
                "25th percentile",
                "75th percentile",
            ],
            default=["count", "min", "mean", "max"],
            help="Select statistics to calculate",
            key="statistics_options_enumerator",
        )
    if selected_columns and statistics_options:
        try:
            stats_options_list = {
                "count": "count",
                "min": "min",
                "mean": "mean",
                "median": "median",
                "max": "max",
                "std": "std",
                "25th percentile": pd.NamedAgg(
                    column="25th percentile", aggfunc=lambda x: x.quantile(0.25)
                ),
                "75th percentile": pd.NamedAgg(
                    column="75th percentile", aggfunc=lambda x: x.quantile(0.75)
                ),
            }
            stat_func_list = [stats_options_list[col] for col in statistics_options]
            enum_statistics = (
                data[[enumerator] + selected_columns]
                .groupby(enumerator)
                .agg(stat_func_list)
                .reset_index()
            )

            # # clean multi-index columns
            enum_statistics = enum_statistics.rename(
                columns={enumerator: "", "": enumerator}
            )

            # display enumerator statistics
            st.dataframe(enum_statistics, hide_index=True, use_container_width=True)
        except Exception as e:
            st.write(e)
    else:
        st.info("Please select columns and statistics to display.")

    # Graph enumerator statistics

    # Radio button for calculations
    calculation_type = st.radio(
        "Select calculation type:",
        ("Graph with Overall Results", "Graph with Results per Date"),
    )

    # Date input for filtering if "Calculations per Date" is selected
    if calculation_type == "Graph with Results per Date":
        date_filter = st.date_input("Select date")
        filtered_df = data[data[date] == pd.to_datetime(date_filter)]
    else:
        filtered_df = data

    # Calculate average duration time per enumerator

    if filtered_df.shape[0] > 0:
        average_duration = (
            filtered_df.groupby(enumerator, observed=False)
            .agg(avg_duration=(duration, "mean"))
            .reset_index()
        )

        # Sort values by avg_duration
        average_duration = average_duration.sort_values(
            by="avg_duration", ascending=True
        )

        # Calculate overall average duration
        overall_avg_duration = average_duration["avg_duration"].mean()

        # Calculate standard deviation
        std_dev = average_duration["avg_duration"].std()

        # Calculate how many standard deviations away each average
        duration_units = "minutes" if duration_in_minutes else "seconds"

        # is from the overall average
        average_duration["std_dev_away"] = (
            average_duration["avg_duration"] - overall_avg_duration
        ) / std_dev

        # Create the plot with different colors for each bar
        fig = px.bar(
            average_duration,
            x=enumerator,
            y="avg_duration",
            title="Average Duration per Enumerator",
            labels={
                "avg_duration": "Average Duration (" + duration_units + ")",
                enumerator: "Enumerator ID",
            },
            color="std_dev_away",  # Color by how many std dev away from the mean
            color_continuous_scale=px.colors.sequential.Viridis[::-1],
        )

        fig.update_xaxes(tickangle=90, tickmode="auto")

        # Customize hover template
        fig.update_traces(
            hovertemplate="<b>Enumerator ID:</b> %{x}<br>"
            + "<b>Average Duration:</b> %{y} <br>"
            + f"<b>Overall Average:</b> {overall_avg_duration:.2f} <br>"
            + "<b>Standard Deviations Away:</b> %{customdata:.2f}",
            customdata=average_duration["std_dev_away"].values,
        )

        # Add overall average line
        fig.add_hline(y=overall_avg_duration, line_color="red", line_dash="dash")

        fig.update_layout(xaxis=dict(type="category"))

        # Show the figure
        st.plotly_chart(fig, theme="streamlit", use_container_width=True)
    else:
        st.warning("No data available for the selected criteria.")

    # with col2:
    # Add CSS for consistent width
    st.markdown(
        """
    <style>
        .stDataFrame {
            width: 100%;
        }
        .dataframe {
            width: 25%;
        }
    </style>
    """,
        unsafe_allow_html=True,
    )

    # Checkbox for calculations
    calculation_type = st.radio(
        "Select calculation type:",
        ("Calculations per Period", "Calculations per Date"),
    )

    # Date input for filtering
    if calculation_type == "Calculations per Date":
        date_filter = st.date_input("Select a date")
        data[date] = pd.to_datetime(data["date_only"])
        filtered_df = data[data[date] == pd.to_datetime(date_filter)]
    else:
        filtered_df = data

    if filtered_df.shape[0] > 0:
        # Summary calculation for consent data
        summary = (
            filtered_df.groupby(enumerator, observed=False)
            .agg(
                total_persons=(survey_id, "size"),
                consented_persons=(consent, lambda x: (x.isin(consent_val)).sum()),
            )
            .reset_index()
        )

        # Convert to numeric and calculate consent percentage
        summary["consented_persons"] = pd.to_numeric(
            summary["consented_persons"], errors="coerce"
        )
        summary["total_persons"] = pd.to_numeric(
            summary["total_persons"], errors="coerce"
        )
        summary["consent_percentage"] = (
            summary["consented_persons"] / summary["total_persons"]
        ) * 100

        # Rename columns for consent data
        summary.rename(
            columns={
                enumerate: "Enumerator ID",
                "total_persons": "Total Interviews",
                "consented_persons": "Consented Interviews",
                "consent_percentage": "Consent Percentage",
            },
            inplace=True,
        )

        # Backcheck analysis

        if analyze_backcheck:
            # Calculate statistics for original enumerators
            survey_counts = (
                data.groupby("enumid").size().reset_index(name="Total Surveys")
            )

            # Count how many times each enumerator's work was backchecked
            backcheck_counts = (
                merged_df.groupby("enumid")
                .size()
                .reset_index(name="Backchecked Interviews")
            )

            # Get comparable variables
            comparable_vars = []
            prefix_pairs = []
            svy_cols = [col for col in merged_df.columns if col.startswith("svy_")]

            for svy_col in svy_cols:
                base_var = svy_col[4:]
                back_col = f"back_{base_var}"
                if back_col in merged_df.columns:
                    comparable_vars.append(base_var)
                    prefix_pairs.append((svy_col, back_col))

            # Count mismatches for each enumerator
            def count_mismatches(group):
                """Count mismatches between survey and backcheck
                values for a given group.

                Args:
                        group (pd.DataFrame): DataFrame containing
                        survey and backcheck values.

                Returns
                -------
                        int: Number of mismatches.

                """
                mismatch_count = 0
                for svy_col, back_col in prefix_pairs:
                    svy_values = group[svy_col].astype(str)
                    back_values = group[back_col].astype(str)
                    svy_values = svy_values.replace("nan", "")
                    back_values = back_values.replace("nan", "")
                    mismatch_count += (svy_values != back_values).sum()
                return mismatch_count

            if len(comparable_vars) > 0:
                try:
                    # Calculate mismatches by enumerator
                    mismatch_counts = (
                        merged_df.groupby("enumid")
                        .apply(count_mismatches)
                        .reset_index(name="Total Mismatches")
                    )

                    # Calculate backcheck metrics
                    backcheck_data = survey_counts.merge(
                        backcheck_counts, on="enumid", how="left"
                    )

                    # Fill NaN values with 0 for enumerators with
                    # no backchecks
                    backcheck_data["Backchecked Interviews"] = (
                        backcheck_data["Backchecked Interviews"].fillna(0).astype(int)
                    )

                    # Calculate total surveys that can be compared
                    backcheck_data["Values Compared"] = (
                        backcheck_data["Backchecked Interviews"] * len(comparable_vars)
                    ).astype(int)

                    # Merge with mismatch counts
                    backcheck_data = backcheck_data.merge(
                        mismatch_counts, on="enumid", how="left"
                    )

                    # Fill NaN values for mismatches
                    backcheck_data["Total Mismatches"] = (
                        backcheck_data["Total Mismatches"].fillna(0).astype(int)
                    )

                    # Calculate percentages
                    backcheck_data["Backchecked Percentage"] = (
                        backcheck_data["Backchecked Interviews"]
                        / backcheck_data["Total Surveys"]
                        * 100
                    ).round(2)

                    backcheck_data["Mismatch Percentage"] = (
                        backcheck_data["Total Mismatches"]
                        / backcheck_data["Values Compared"]
                        * 100
                    ).round(2)

                    # Merge consent summary with backcheck data
                    combined_summary = summary.merge(
                        backcheck_data,
                        left_on="Enumerator ID",
                        right_on="enumid",
                        how="outer",
                    )

                    # Clean up the merged dataframe
                    combined_summary = combined_summary.drop(
                        ["enumid", "Total Surveys"], axis=1
                    )

                    # Format percentage columns
                    combined_summary["Consent Percentage"] = combined_summary[
                        "Consent Percentage"
                    ].round(2)
                    combined_summary["Backchecked Percentage"] = combined_summary[
                        "Backchecked Percentage"
                    ].round(2)
                    combined_summary["Mismatch Percentage"] = combined_summary[
                        "Mismatch Percentage"
                    ].round(2)

                    # Define the desired column order
                    column_order = [
                        "Enumerator ID",
                        "Total Interviews",
                        "Consented Interviews",
                        "Consent Percentage",
                        "Backchecked Interviews",
                        "Backchecked Percentage",
                        "Values Compared",
                        "Total Mismatches",
                        "Mismatch Percentage",
                    ]

                    # Reorder the columns in the combined_summary DataFrame
                    combined_summary = combined_summary[column_order]

                    # Display combined summary with the new column order
                    st.dataframe(
                        combined_summary,
                        hide_index=True,
                        use_container_width=True,
                        column_config={
                            "Enumerator ID": st.column_config.Column(width="small"),
                            "Total Interviews": st.column_config.NumberColumn(
                                format="%d", width="small"
                            ),
                            "Consented Interviews": st.column_config.NumberColumn(
                                format="%d", width="small"
                            ),
                            "Consent Percentage": st.column_config.NumberColumn(
                                format="%.2f%%", width="small"
                            ),
                            "Backchecked Interviews": st.column_config.NumberColumn(
                                format="%d", width="small"
                            ),
                            "Backchecked Percentage": st.column_config.NumberColumn(
                                format="%.2f%%", width="small"
                            ),
                            "Values Compared": st.column_config.NumberColumn(
                                format="%d", width="small"
                            ),
                            "Total Mismatches": st.column_config.NumberColumn(
                                format="%d", width="small"
                            ),
                            "Mismatch Percentage": st.column_config.NumberColumn(
                                format="%.2f%%", width="small"
                            ),
                        },
                    )

                    # Display number of comparable variables
                    st.write(
                        f"Note: For backchecks calculations there were found {len(comparable_vars)} comparable variables."
                    )

                except Exception as e:
                    st.error(f"Error calculating combined metrics: {e!s}")
            else:
                st.warning("No comparable variables found for backcheck analysis.")
        else:
            st.warning("No backcheck data available. Displaying only consent data.")
            st.dataframe(
                summary,
                hide_index=True,
                use_container_width=True,
                column_config={
                    "Enumerator ID": st.column_config.Column(width="small"),
                    "Total Interviews": st.column_config.NumberColumn(
                        format="%d", width="small"
                    ),
                    "Consent Percentage": st.column_config.NumberColumn(
                        format="%.2f%%", width="small"
                    ),
                },
            )
    else:
        st.warning("No data available for the selected criteria.")

    # enumerator statistics over time

    st.markdown("##### Enumerator Statistics Over Time")

    # Select enumerators to display
    selected_enumerators = st.multiselect(
        "Select enumerators:",
        options=data[enumerator].unique(),
        default=data[enumerator].unique(),
        help="Select enumerators to include in the graph",
        key="selected_enumerators",
    )

    # Filter data based on selected enumerators
    filtered_data = data[data[enumerator].isin(selected_enumerators)]
    filtered_data["submission_date_format"] = pd.to_datetime(
        filtered_data["submission_date_format"]
    ).dt.date

    # Select columns to display
    selected_column = st.selectbox(
        "Select columns:",
        options=filtered_data.columns,
        index=0,
        help="Select columns to include in the graph",
        key="selected_columns_graph",
    )

    # Select statistics to display
    statistics_option = st.selectbox(
        "Select a statistic:",
        options=["count", "mean", "median", "min", "max", "std", "missing"],
        help="Select statistics to calculate",
        key="statistics_options_graph",
    )

    # Calculate statistics
    if selected_column and statistics_option:
        # select specific columns
        filtered_data = filtered_data[
            [enumerator, "submission_date_format"] + [selected_column]
        ]

        if statistics_option == "missing":
            index_cols = [enumerator, "submission_date_format"]
            data_cols = [x for x in filtered_data.columns if x != enumerator]
            filtered_enum_statistics = calculate_missing_values(
                filtered_data, data_cols, index_cols
            )
            filtered_enum_statistics["% missing"] = filtered_enum_statistics[
                "% missing"
            ].apply(lambda x: int(x.replace("%", "")))
            selected_column = "% missing"
        else:
            filtered_enum_statistics = (
                filtered_data.groupby([enumerator, "submission_date_format"])
                .agg(statistics_option)
                .reset_index()
                .fillna(0)
            )
            filtered_enum_statistics.columns = [
                enumerator,
                "submission_date_format",
            ] + [selected_column]
        # Create line graph
        fig = px.line(
            filtered_enum_statistics,
            x="submission_date_format",
            y=selected_column,
            color=enumerator,
            labels={"value": "Value", "variable": "Statistic"},
            title="Enumerator Statistics Over Time",
        )

        # Update layout
        fig.update_layout(
            xaxis_title="",
            yaxis_title=selected_column,
            legend_title="Enumerator",
        )

        # Show the figure
        st.plotly_chart(fig, theme="streamlit", use_container_width=True)
    else:
        st.info("Please select columns and statistics to display.")
