import pandas as pd
<<<<<<< HEAD
<<<<<<< HEAD
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
        total_goal = st.number_input(  # noqa: F841
            "Total goal",
            min_value=0,
            help="Total number of interviews expected",
            key="total_goal_backcheck",
        )

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
            # merge survey and backcheck data
            survey_df_bc = survey_data[
                backcheck_cols + [survey_id, enumerator]
            ].add_prefix("_svy_")
            # rename enumerator and survey_id columns removing prefix
            survey_df_bc.rename(columns={"_svy_" + survey_id: survey_id}, inplace=True)
            backcheck_df_bc = backcheck_data[
                backcheck_cols + [survey_id, backchecker]
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
=======

import seaborn as sns
import matplotlib.pyplot as plt

=======
>>>>>>> c8a436c (adding default values from config page)
import streamlit as st

##### Backchecks #####

def backchecks_report(survey_data, backcheck_data, page_num) -> None:
    
	with st.expander("settings", icon=":material/settings:"):
		st.markdown("## Configure settings for backcheck report")

		survey_cols = survey_data.columns.tolist()

		# get list of columns in both surey and backcheck data
		common_cols = [col for col in survey_data.columns if col in backcheck_data.columns]

		st.write("---")
		st.markdown("### Select columns to include in backcheck report")

		backcheck_cols = st.multiselect("Select columns to include in back check report", options = common_cols, key = "backcheck_cols", help = "Select columns to include in back check report")

		st.write("---")
		st.markdown("### Select other columns")

		meta_col, enum_col, agg_col = st.columns(spec = 3, border= True)

		with meta_col:
			duration = st.selectbox("Duration", options = survey_cols, help = "Column containing survey duration", key = "duration_backcheck", index=None)
			date = st.selectbox("Date", options = survey_cols, help = "Column containing survey date", key = "date_backcheck", index=None)
			formversion = st.selectbox("Form Version", options = survey_cols, help = "Column containing survey form version", key = "formversion_backcheck", index=None)

		with enum_col:
			enumerator = st.selectbox("Enumerator", options = survey_cols, help = "Column containing survey enumerator", key = "enumerator_backcheck", index=None)
			team = st.selectbox("Enumerator Team", options = survey_cols, help = "Column containing survey team", key = "team_backcheck", index=None)
			backchecker = st.selectbox("Back Checker", options = survey_cols, help = "Column containing back check enumerator", key = "backchecker_backcheck", index=None)
			team = st.selectbox("Back Check Team", options = survey_cols, help = "Column containing survey team", key = "backcheck_team_backcheck", index=None)
		
		with agg_col:
			
			survey_id = st.selectbox("Survey ID", options = survey_cols, help = "Column containing survey ID", key = "surveyid_backcheck", index=None)
			survey_key = st.selectbox("Survey Key", options = survey_cols, help = "Column containing survey key", key = "surveykey_backcheck", index=None)

			consent = st.selectbox("Consent", options = survey_cols, help = "Column containing survey consent", key = "consent_backcheck", index=None)

			if consent:
				consent_options = survey_data[consent].unique().tolist()
				consent_val = st.multiselect("Consent value(s)", options = consent_options, help = "Value(s) indicating valid consent", key="consent_val_backcheck")

			outcome = st.selectbox("Outcome", options = survey_cols, help = "Column containing survey outcome", key="outcome_backcheck", index=None)

			if outcome:
				outcome_options = survey_data[outcome].unique().tolist()
				outcome_val = st.multiselect("Outcome value(s)", options = outcome_options, help = "Value(s) indicating completed survey", key="outcome_val_backcheck")
		
		st.write("---")
		st.markdown("### Tracking Options")

		# number of interviews expected 
		total_goal = st.number_input("Total goal", min_value = 0, help = "Total number of interviews expected", key = "total_goal_backcheck")

		# define a save settings button
		save_settings = st.button("Save settings", key = "save_settings_backcheck")

	if backcheck_data.empty:
		st.warning("No back check data available")
		
	else:

		if backcheck_cols:
			# merge survey and backcheck data
			survey_df_bc = survey_data[backcheck_cols + [survey_id, enumerator]].add_prefix("_svy_")
			# rename enumerator and survey_id columns removing prefix
			survey_df_bc.rename(columns = {"_svy_" + survey_id: survey_id}, inplace = True)
			backcheck_df_bc = backcheck_data[backcheck_cols + [survey_id, backchecker]].add_prefix("_bc_")
			# rename enumerator and survey_id columns removing prefix
			backcheck_df_bc.rename(columns = {"_bc_" + survey_id: survey_id}, inplace = True)

			merged_df = pd.merge(survey_df_bc, backcheck_df_bc, on = survey_id, how = "inner")

			# Find matching variable pairs (survey and backcheck variables)
			svy_vars = [col for col in merged_df.columns if col.startswith("_svy_")]
			back_vars = [
				col for col in merged_df.columns if col.startswith("_bc_")
			]

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
			mismatches_dict = {}

			# First get the data types for each variable
			var_types = {}
			for var in backcheck_cols:
				svy_col = f"_svy_{var}"
				bc_col = f"_bc_{var}"
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
				enumerator_stats = pd.DataFrame.from_dict(
					var_summary, orient="index"
				)
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

						enum_data = comparison[
                            comparison["enumerator_id"] == enum_id
                        ]

						# Only update backcheck count once per variable loop
						if var == backcheck_cols[0]:  # First variable only
							enumerator_detailed_stats[enum_id][
								"total_backchecks"
							] = len(enum_data)

						enumerator_detailed_stats[enum_id][
							"total_compared"
						] += len(enum_data)
						enumerator_detailed_stats[enum_id][
							"total_different"
						] += enum_data["is_different"].sum()

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
				enumerator_detailed_df["% Backchecked"] = (
					enumerator_detailed_df["% Backchecked"].fillna(0)
				)
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
				enumerator_detailed_df["% Backchecked"] = (
					enumerator_detailed_df["% Backchecked"].fillna(0)
				)
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
									comparison["backchecker_id"]
									== backchecker_id
								]
							),
							"total_compared": 0,
							"total_different": 0,
						}

					backchecker_data = comparison[
						comparison["backchecker_id"] == backchecker_id
					]
					backchecker_stats[backchecker_id]["total_compared"] += (
						len(backchecker_data)
					)
					backchecker_stats[backchecker_id][
						"total_different"
					] += backchecker_data["is_different"].sum()

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
						backchecker_df["Backchecker ID"].isin(
							selected_backcheckers
						)
					]
				else:
					filtered_backchecker_stats = backchecker_df

				# Display the filtered backchecker statistics table
				st.dataframe(
					filtered_backchecker_stats,
					use_container_width=True,
					column_config={
						"Backchecker ID": st.column_config.Column(
							width="medium"
						),
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
							].apply(
								lambda x: f"{x:.2f}" if pd.notnull(x) else "N/A"
							)
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
							mismatches_df["Enumerator id"].isin(
								selected_enumerators
							)
						]
					else:
						filtered_mismatches = mismatches_df

					# Display the filtered mismatches
					st.dataframe(filtered_mismatches, use_container_width=True)


		else:
			st.info(
                    "There was no backcheck data frame found. Please upload the backcheck data first."
                )
			

	
>>>>>>> 1205bf5 (adding back check)
