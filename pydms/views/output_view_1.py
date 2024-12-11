import streamlit as st
import pandas as pd
from datetime import datetime

st.title(st.session_state.config_page_1)

summary, survey_progress, duplicates, missing, outliers, enum_stats = \
    st.tabs(("Summary", "Survey Progress", "Duplicates", "Missing Data", "Outliers", "Enumerator Stats"))

alias_list = list(filter(None, st.session_state.alias_list))
new_page_data = st.session_state[f'prepped_data{1}']

# load data from 

with summary:
    
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for summary report")

        survey_cols = st.session_state[f'prepped_data{1}'].columns

        st.write("---")
        st.markdown("### Select columns to include in summary report")
        
        formversion_col, enumerator_col, date_col = st.columns(3)
        formversion_col.selectbox("Form Version", options = survey_cols)
        enumerator_col.selectbox("Enumerator", options = survey_cols)
        date_col.selectbox("Date", options = survey_cols)
        by_col, consent_col, duration_col = st.columns(3)
        by_col.selectbox("Group by", options = survey_cols)
        consent_col.selectbox("Consent", options = survey_cols)
        duration_col.selectbox("Duration", options = "Duration")

        st.write("---")
        st.markdown("### Summary report options")

        enum_filter_col, team_filter_col, location_filter_col = st.columns(3)
        enum_filter_col.multiselect("Enumerator", options = survey_cols)
        team_filter_col.multiselect("Team", options = survey_cols)
        location_filter_col.multiselect("Location", options = survey_cols)

        date_filter = st.slider(
            "Select date range", 
                min_value= datetime(2024, 1, 1), max_value = datetime(2024, 12, 31), 
                format = "YYYY-MM-DD", value = (datetime(2024, 1, 1), datetime(2024, 12, 31))
        )





