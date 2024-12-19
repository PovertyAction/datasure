import pandas as pd

import seaborn as sns
import matplotlib.pyplot as plt

import streamlit as st
from datetime import datetime


##### Survey Progress #####

def progress_report(data) -> None:
    
	with st.expander("settings", icon=":material/settings:"):
		st.markdown("## Configure settings for progress report")

		survey_cols = data.columns

		st.write("---")
		st.markdown("### Select columns to include in summary report")

		meta_col, enum_col, agg_col = st.columns(spec = 3, border= True)

		with meta_col:
			duration = st.selectbox("Duration", options = survey_cols, help = "Column containing survey duration", key = "duration_progress")
			date = st.selectbox("Date", options = survey_cols, help = "Column containing survey date", key = "date_progress")
			formversion = st.selectbox("Form Version", options = survey_cols, help = "Column containing survey form version", key = "formversion_progress")

		with enum_col:
			by = st.selectbox("Group by", options = survey_cols, help = "Column to group summary report by by", key = "groupby_progress")
			enumerator = st.selectbox("Enumerator", options = survey_cols, help = "Column containing survey enumerator", key = "enumerator_progress")
			team = st.selectbox("Team", options = survey_cols, help = "Column containing survey team", key = "team_progress")
		
		with agg_col:
			
			survey_id = st.selectbox("Survey ID", options = survey_cols, help = "Column containing survey ID", key = "surveyid_progress")
			survey_key = st.selectbox("Survey Key", options = survey_cols, help = "Column containing survey key", key = "surveykey_progress")

			consent = st.selectbox("Consent", options = survey_cols, help = "Column containing survey consent", key = "consent_progress")

			if consent:
				consent_options = data[consent].unique().tolist()
				consent_val = st.multiselect("Consent value(s)", options = consent_options, help = "Value(s) indicating valid consent")

			outcome = st.selectbox("Outcome", options = survey_cols, help = "Column containing survey outcome")

			if outcome:
				outcome_options = data[outcome].unique().tolist()
				outcome_val = st.multiselect("Outcome value(s)", options = outcome_options, help = "Value(s) indicating completed survey")
		
		st.write("---")
		st.markdown("### Tracking Options")

		# number of interviews expected 
		total_goal = st.number_input("Total goal", min_value = 0, help = "Total number of interviews expected", key = "total_goal_progress")

		# define a save settings button
		save_settings = st.button("Save settings", key = "save_settings_progress")

	col1, col2, col3 = st.columns(3)

	with col1:
		# Add CSS to ensure table width matches selectbox
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

		consent_col = st.selectbox(
			"Select your consent variable",
			options=data.columns,
			index=data.columns.get_loc(consent),
		)

		summary = data.groupby(consent_col)[survey_id].nunique().reset_index()
		summary.columns = ["Consent Status", "Unique ID Count"]

		st.table(summary)

		# Modify consent variable - Define values of consent/no consent
		mapping = {1: "Consent", 0: "No Consent"}
		data[consent] = data[consent].map(mapping)

		# Group by 'id' and count unique values of "key"
		unique_counts = df.groupby(survey_id)[survey_key].nunique().reset_index()
		unique_counts.columns = [survey_id, "unique_key_count"]

		# Count unique ids from the new df
		count_unique_ids = unique_counts["id"].nunique()