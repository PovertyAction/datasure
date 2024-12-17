import pandas as pd

import streamlit as st
from datetime import datetime

# define function to create summary report
def summary_report(data) -> None: 

	"""	
	Generates a summary report for the survey data

	Parameters
	----------

	data : pd.DataFrame
		The survey data

	Returns
	-------
	None

	"""

	with st.expander("settings", icon=":material/settings:"):
		st.markdown("## Configure settings for summary report")

		survey_cols = data.columns

		st.write("---")
		st.markdown("### Select columns to include in summary report")

		meta_col, enum_col, agg_col = st.columns(spec = 3, border= True)

		with meta_col:
			duration = st.selectbox("Duration", options = survey_cols, help = "Column containing survey duration")
			date = st.selectbox("Date", options = survey_cols, help = "Column containing survey date")
			formversion = st.selectbox("Form Version", options = survey_cols, help = "Column containing survey form version")

		with enum_col:
			by = st.selectbox("Group by", options = survey_cols, help = "Column to group summary report by by")
			enumerator = st.selectbox("Enumerator", options = survey_cols)
			team = st.selectbox("Team", options = survey_cols)
		
		with agg_col:
			
			survey_id = st.selectbox("Survey ID", options = survey_cols, help = "Column containing survey ID")

			consent = st.selectbox("Consent", options = survey_cols, help = "Column containing survey consent")

			if consent:
				consent_options = data[consent].unique().tolist()
				consent_val = st.multiselect("Consent value(s)", options = consent_options, help = "Value(s) indicating valid consent")

			outcome = st.selectbox("Outcome", options = survey_cols, help = "Column containing survey outcome")

			if outcome:
				outcome_options = data[outcome].unique().tolist()
				outcome_val = st.multiselect("Outcome value(s)", options = outcome_options, help = "Value(s) indicating completed survey")
		
		


		date_filter = st.slider(
			"Select date range", 
				min_value= datetime(2024, 1, 1), max_value = datetime(2024, 12, 31), 
				format = "YYYY-MM-DD", value = (datetime(2024, 1, 1), datetime(2024, 12, 31))
		)

		st.write("---")
		st.markdown("### Tracking Options")

		# number of interviews expected 
		total_goal = st.number_input("Total goal", min_value = 0, help = "Total number of interviews expected")

		# define a save settings button
		save_settings = st.button("Save settings")


	# Define flagged percentage of missing. For example, write 50 if there are more than 50% of missing and should be flagged as warning
	percentage_warning = 50

	### Value box 1 ###

	#### Remove later
	# convert SubmissionDate into datetime, formdef_version and duration into float
	data[date] = pd.to_datetime(data[date])
	data[formversion] = data[formversion].astype(float)
	data[duration] = data[duration].astype(float)
    
	# count the number of valid consent
	valid_interviews = data[consent].isin(consent_val).sum()

	# Calculate porcentage of finished interviews
	percentage_finished = (valid_interviews / total_goal) * 100

	# Format of percentage
	formatted_percentage_finished = f"{percentage_finished:.2f}%"

	### Value box 2 ###
    # Identify the date of the first interview
	earliest_date = data[date].min()

	# Todays date
	today = pd.Timestamp.now()
	
	# Calculate the number of days since the first interview/launch
	days_since_start = (today - earliest_date).days

    # Set the color
	color = "black"

	### Value box 3 ###
	# Percentage of missing ID's
	total_values = data[survey_id].size

	# Define ID variable
	missing_values = data[survey_id].isnull().sum()
	missing_percentage = (missing_values / total_values) * 100

	# Format the percentage
	formatted_missing_percentage = f"{missing_percentage:.2f}%"

	### Value box 4 ###
	# Group by date and count number of IDs
	count_by_date = data.groupby(date).size()

	# Calculate the average number of interviews per day
	average_interviews_per_day = count_by_date.mean()

	# Round number of interviews per day
	rounded_average_day = round(average_interviews_per_day, 2)

	 #### Create first row of value boxes ####
	# Define color codes
	color_completed = (
		"#FFA500" if percentage_finished <= percentage_warning else "#4CAF50"
	)
	color_missing = (
		"#FFA500" if missing_percentage > percentage_warning else "#4CAF50"
	)

	# Include Font Awesome
	st.markdown(
		'<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0-beta3/css/all.min.css">',
		unsafe_allow_html=True,
	)

	# Create columns for value boxes
	col1, col2, col3, col4 = st.columns(spec = 4, border = True)

	# Value box: Completed interviews
	with col1:
		
		st.markdown(
                    f"""
                <div style="display: flex; align-items: center; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
                    <i class="fas fa-bullseye" style="font-size: 70px; color: {color_completed}; margin-right: 10px;"></i>
                    <div style="flex-grow: 1;">
                        <h3 style="margin: 0; font-size: 25px; text-align: center;">Completed Interviews</h3>
                        <p style="font-size: 53px; color: {color_completed}; margin: 0; text-align: center;">{formatted_percentage_finished}</p>
                    </div>
                </div>
                """,
                    unsafe_allow_html=True,
                )

 	# Value box: Number of days since launch
	with col2:
		st.markdown(
			f"""
		<div style="display: flex; align-items: center; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
			<i class="fas fa-calendar-week" style="font-size: 70px; color: black; margin-right: 10px;"></i>
			<div style="flex-grow: 1;">
				<h3 style="margin: 0; font-size: 25px; text-align: center;">Number of Days since Launch</h3>
				<p style="font-size: 53px; color: black; margin: 0; text-align: center;">{days_since_start}</p>
			</div>
		</div>
		""",
			unsafe_allow_html=True,
		)

	# Value box: % of missing IDs
	with col3:
		st.markdown(
			f"""
		<div style="display: flex; align-items: center; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
			<i class="fas fa-percent" style="font-size: 70px; color: {color_missing}; margin-right: 10px;"></i>
			<div style="flex-grow: 1;">
				<h3 style="margin: 0; font-size: 25px; text-align: center;">Percentage of Missing IDs</h3>
				<p style="font-size: 53px; color: {color_missing}; margin: 0; text-align: center;">{formatted_missing_percentage}</p>
			</div>
		</div>
		""",
			unsafe_allow_html=True,
		)

	# Value box 4: Average Interviews per Day
	with col4:
		st.markdown(
			f"""
		<div style="display: flex; align-items: center; padding: 5px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
			<i class="fas fa-calendar-alt" style="font-size: 73px; color: black; margin-right: 10px;"></i>
			<div style="flex-grow: 1;">
				<h3 style="font-size: 28px; margin: 0; text-align: center;"> Average Interviews per Day</h3>
				<p style="font-size: 53px; color: black; margin: 0; text-align: center;">{rounded_average_day}</p>
			</div>
		</div>
		""",
			unsafe_allow_html=True,
		)


	 ### Value box 5 ###
	# Count number of enumerators
	unique_enumerators = data[enumerator].nunique()

	### Value box 6 ###
	# Count the number of interviews per interviewer
	interviews_per_interviewer = (
		data.groupby(enumerator, observed=False)
		.size()
		.reset_index(name="interviews_count")
	)

	# Calculate the average number of interviews per enumerator
	average_interviews_per_interviewer = interviews_per_interviewer[
		"interviews_count"
	].mean()

	# Round the number of interviews per enumerator
	rounded_average = round(average_interviews_per_interviewer, 2)

	### Value box 7 ###
	average_interviews_per_day_per_enumerator = (
		average_interviews_per_day / (unique_enumerators)
		if unique_enumerators > 0
		else 0
	)
	rounded_average_day_per_enumerator = round(
		average_interviews_per_day_per_enumerator, 2
	)

	### Value box 8 ###
	# Calculate interviews left
	interviews_left = total_goal - valid_interviews

	#### Create second row of value boxes
	# Create columns for the value boxes
	col5, col6, col7, col8 = st.columns(spec = 4, border = True)

	# Value box 5: Number of Enumerators
	with col5:
		st.markdown(
			f"""
		<div style="display: flex; align-items: center; padding: 21px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
			<i class="fas fa-user" style="font-size: 73px; color: black; margin-right: 10px;"></i>
			<div style="flex-grow: 1;">
				<h3 style="margin: 0; font-size: 23px; text-align: center;">Number of Enumerators</h3>
				<p style="font-size: 50px; color: black; margin: 0; text-align: center;">{unique_enumerators}</p>
			</div>
		</div>
		""",
			unsafe_allow_html=True,
		)

	# Value box 6: Average Interviews per Enumerator
	with col6:
		st.markdown(
			f"""
		<div style="display: flex; align-items: center; padding: 10px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
			<i class="fas fa-chart-line" style="font-size: 75px; color: black; margin-right: 10px;"></i>
			<div style="flex-grow: 1;">
				<h3 style="margin: 0; font-size: 25px; text-align: center;">Average Interviews per Enumerator</h3>
				<p style="font-size: 47px; color: black; margin: 0; text-align: center;">{rounded_average}</p>
			</div>
		</div>
		""",
			unsafe_allow_html=True,
		)

	# Value box 7: Avg interviews per day per enumerator
	with col7:
		st.markdown(
			f"""
		<div style="display: flex; align-items: center; justify-content: center; padding: 5px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
			<i class="fas fa-calendar-check" style="font-size: 75px; color: black; margin-right: 10px;"></i>
			<div style="flex-grow: 1; text-align: center;">
				<h3 style="margin: 0; font-size: 24px;">Average Interviews per Day per Enumerator</h3>
				<p style="font-size: 50px; color: black; margin: 0;">{rounded_average_day_per_enumerator}</p>
			</div>
		</div>
		""",
			unsafe_allow_html=True,
		)

	# Value box 8: Interviews Left
	with col8:
		st.markdown(
			f"""
		<div style="display: flex; align-items: center; justify-content: center; padding: 1px; border: 1px solid #e0e0e0; border-radius: 8px; background-color: #f9f9f9; text-align: center; width: 100%;">
			<i class="fas fa-pen-to-square" style="font-size: 70px; color: black; margin-right: 10px;"></i>
			<div style="flex-grow: 1; text-align: center;">
				<h3 style="margin: 0; font-size: 25px;">Number of Interviews Left to Reach Goal</h3>
				<p style="font-size: 50px; color: black; margin: 0;">{interviews_left}</p>
			</div>
		</div>
		""",
			unsafe_allow_html=True,
		)

	# Calculate todays date
	today = datetime.now().strftime(
		"%B %d, %Y"
	)  # Format: Month day, year (e.g., August 22, 2024)

	# Creat text
	last_updated_text = f"Last update: {today}"

	# Show text
	st.write(last_updated_text)