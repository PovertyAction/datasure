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
			duration = st.selectbox("Duration", options = survey_cols, help = "Column containing survey duration", key = "duration_progress", index=None)
			date = st.selectbox("Date", options = survey_cols, help = "Column containing survey date", key = "date_progress", index=None)
			formversion = st.selectbox("Form Version", options = survey_cols, help = "Column containing survey form version", key = "formversion_progress", index=None)

		with enum_col:
			by = st.selectbox("Group by", options = survey_cols, help = "Column to group summary report by by", key = "groupby_progress", index=None)
			enumerator = st.selectbox("Enumerator", options = survey_cols, help = "Column containing survey enumerator", key = "enumerator_progress", index=None)
			team = st.selectbox("Team", options = survey_cols, help = "Column containing survey team", key = "team_progress", index=None)
		
		with agg_col:
			
			survey_id = st.selectbox("Survey ID", options = survey_cols, help = "Column containing survey ID", key = "surveyid_progress", index=None)
			survey_key = st.selectbox("Survey Key", options = survey_cols, help = "Column containing survey key", key = "surveykey_progress", index=None)

			consent = st.selectbox("Consent", options = survey_cols, help = "Column containing survey consent", key = "consent_progress", index=None)

			if consent:
				consent_options = data[consent].unique().tolist()
				consent_val = st.multiselect("Consent value(s)", options = consent_options, help = "Value(s) indicating valid consent", key="consent_val_progress")

			outcome = st.selectbox("Outcome", options = survey_cols, help = "Column containing survey outcome", key="outcome_progress", index=None)

			if outcome:
				outcome_options = data[outcome].unique().tolist()
				outcome_val = st.multiselect("Outcome value(s)", options = outcome_options, help = "Value(s) indicating completed survey", key="outcome_val_progress")
		
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

		summary = data.groupby(consent)[survey_id].nunique().reset_index()
		summary.columns = ["Consent Status", "Unique ID Count"]

		st.table(summary)

		# Modify consent variable - Define values of consent/no consent
		mapping = {1: "Consent", 0: "No Consent"}
		data[consent] = data[consent].map(mapping)

		# Group by 'id' and count unique values of "key"
		unique_counts = data.groupby(survey_id)[survey_key].nunique().reset_index()
		unique_counts.columns = [survey_id, "unique_key_count"]

		# Count unique ids from the new df
		count_unique_ids = unique_counts[survey_id].nunique()