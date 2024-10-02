import streamlit as st
import numpy as np
import pandas as pd
from datetime import datetime

st.write("""


# pyDMS - Data Management System

Data Management system for research data


""")

# Import survey data 

survey = pd.read_csv("C:/Users/IBaako/Documents/learning/streamlit/pyDMS/data/household_survey.csv")


# Prepare Data

# submissiondate, starttime, endtime
datecols = {'submissiondate':'subdate', 'starttime':'startdate', 'endtime':'enddate'}
for col in datecols:
    survey[col] = survey[col].apply(lambda x: datetime.strptime(x, '%d%b%Y %H:%M:%S'))
    survey[datecols[col]] = survey[col].dt.date


st.write("""


## Check 1: Form Versions

Check for surveys that were completed with older form versions

""")

# get a subset of the dataset 
formv_data = survey[['formdef_version', 'startdate', 'a_enum_id', 'a_enum_name']]

# create a dataset of the latest form available for each day
check_version = formv_data.groupby('startdate').agg(formdef_version_max = ('formdef_version', np.max))

# merge the grouped dataset back into the formv_data
formv_data = formv_data.merge(check_version, on='startdate')

# flag outdated submissions
formv_data['outdated'] = formv_data['formdef_version'] < formv_data['formdef_version_max']
formv_data['sub'] = 1

# Aggregate statistics by formdef_vers



outdated_stats = formv_data.groupby('formdef_version').agg(
                                        submissions = ('sub', np.sum),
                                        outdated = ('outdated', np.sum),
                                        firstdate = ('startdate', np.min),
                                        lastdate = ('startdate', np.max)
                                    )

# Show version information
st.write("""
	Information about form versions
	""")

outdated_stats

st.write("""
	All surveys that were completed with outdated form version
	""")

# Show all observations with outdated form versions
formv_data[['startdate', 'a_enum_id', 'a_enum_name', 'formdef_version']][formv_data['outdated'] == True]