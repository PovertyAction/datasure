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
            date = st.selectbox(
                "Date",
                options=survey_cols,
                help="Column containing survey date",
                key="date_enumerator",
                index=None,
            )
            formversion = st.selectbox(  # noqa: F841
                "Form Version",
                options=survey_cols,
                help="Column containing survey form version",
                key="formversion_enumerator",
                index=None,
            )

        with enum_col:
            by = st.selectbox(  # noqa: F841
                "Group by",
                options=survey_cols,
                help="Column to group summary report by by",
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
            team = st.selectbox(  # noqa: F841
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
                consent_val = st.multiselect(  # noqa: F841
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

    col1, col2 = st.columns(2)

    with col1:
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
                    "avg_duration": "Average Duration (minutes)",
                    enumerator: "Enumerator ID",
                },
                color="std_dev_away",  # Color by how many std dev away from the mean
                color_continuous_scale=px.colors.sequential.Viridis[::-1],
            )

            fig.update_xaxes(tickangle=90, tickmode="auto")

            # Customize hover template
            fig.update_traces(
                hovertemplate="<b>Enumerator ID:</b> %{x}<br>"
                + "<b>Average Duration:</b> %{y} minutes<br>"
                + f"<b>Overall Average:</b> {overall_avg_duration:.2f} minutes<br>"
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

    with col2:
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
                    consented_persons=(consent, lambda x: (x == 1).sum()),
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
                            backcheck_data["Backchecked Interviews"]
                            .fillna(0)
                            .astype(int)
                        )

                        # Calculate total surveys that can be compared
                        backcheck_data["Values Compared"] = (
                            backcheck_data["Backchecked Interviews"]
                            * len(comparable_vars)
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

    col3 = st.columns(1)[0]

    with col3:
        enum_stats_df = data[[date, enumerator, survey_key, duration]].copy()

        # Rename columns for consistency
        enum_stats_df[date] = pd.to_datetime(enum_stats_df[date])

        # Ensure enumid is of type string
        enum_stats_df[enumerator] = enum_stats_df[enumerator].astype(str)

        # Calculate average duration time per enumerator
        average_duration = (
            enum_stats_df.groupby(enumerator, observed=False)
            .agg(avg_duration=(duration, "mean"))
            .reset_index()
        )

        # Calculate overall average duration
        current_avg_duration = average_duration["avg_duration"].mean()

        # Compute cumulative count of surveys by enumerator and date
        enum_stats_df = (
            enum_stats_df.groupby([date, enumerator])
            .agg({survey_key: "nunique", duration: "mean"})
            .reset_index()
        )
        enum_stats_df = enum_stats_df.sort_values(
            [enumerator, date], ascending=[False, True]
        )
        enum_stats_df["cumsum_surveys"] = enum_stats_df.groupby([enumerator])[
            survey_key
        ].cumsum()
        enum_stats_df = enum_stats_df.sort_values(date, ascending=True)

        # Calculate the min and max of the duration variable
        y_min = enum_stats_df[duration].min()
        y_max = enum_stats_df[duration].max()

        # Create cross join of dates and enumerators
        dates = pd.DataFrame({date: enum_stats_df[date].unique()}).sort_values(
            date, ascending=True
        )
        enums = pd.DataFrame(
            {enumerator: enum_stats_df[enumerator].unique()}
        ).sort_values(enumerator, ascending=True)
        crossjoin = dates.merge(enums, how="cross")

        # Merge the cross join with the original data
        merged = crossjoin.merge(
            enum_stats_df, how="left", on=[date, enumerator]
        ).sort_values([enumerator, date], ascending=[False, True])
        merged.update(merged.groupby([enumerator]).ffill())

        # Fill remaining NaN values with 0
        merged = merged.fillna(0)

        # Ensure all columns are of the correct type
        merged["cumsum_surveys"] = merged["cumsum_surveys"].astype(float)
        merged[duration] = merged[duration].astype(float)

        # Calculate the min and max of the cumulative count
        x_min = enum_stats_df["cumsum_surveys"].min()
        x_max = enum_stats_df["cumsum_surveys"].max()

        # Create a new format for the date
        merged["display_date"] = pd.to_datetime(merged[date]).dt.strftime("%m/%d")

        # Create scatter plot
        fig = px.scatter(
            merged,
            x="cumsum_surveys",
            y=duration,
            animation_frame="display_date",
            color=enumerator,
            animation_group=enumerator,
            size="cumsum_surveys",
            hover_name=enumerator,
            range_x=[x_min, x_max],
            range_y=[y_min, y_max],
            width=1300,
            height=600,
        )

        # Update layout to set axis titles and hide legend
        fig.update_layout(
            xaxis_title="Cumulative Surveys",
            yaxis_title="Average Duration (minutes)",
            showlegend=False,
            sliders=[
                {
                    "currentvalue": {
                        "font": {"size": 8},
                        "prefix": "Date: ",
                        "xanchor": "right",
                        "offset": 10,
                    },
                    "pad": {"t": 40},
                    "len": 0.9,
                    "x": 0.1,
                    "y": 0,
                }
            ],
        )

        # Add a dashed line for the overall average duration
        fig.add_shape(
            type="line",
            x0=0,
            y0=current_avg_duration,
            x1=30,
            y1=current_avg_duration,
            line=dict(color="red", width=2, dash="dash"),
            name="Overall Average",
        )

        # Add notes to the shape
        fig.add_annotation(
            x=x_max,
            y=current_avg_duration,
            text=f"Overall Average: {current_avg_duration:.2f}",
            showarrow=False,
            font=dict(color="red"),
        )

        st.plotly_chart(fig, theme="streamlit", use_container_width=True)
