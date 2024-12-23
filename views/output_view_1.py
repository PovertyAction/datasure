import streamlit as st

from src.checks import (
    missing_report, 
    progress_report, 
    summary_report, 
    duplicates_report, 
    outliers_report, 
    enumerator_report,
    descriptive_report, 
    backchecks_report
)

# define page number
page_number = 1

st.title(st.session_state[f"config_page_{page_number}"])

summary, survey_progress, duplicates, missing, outliers, enum_stats, desc_stats, back_checks = st.tabs(
    (
        "Summary",
        "Survey Progress",
        "Duplicates",
        "Missing Data",
        "Outliers",
        "Enumerator Stats",
        "Descriptive Stats", 
        "Back Checks"
    )
)

alias_list = list(filter(None, st.session_state.alias_list))

# load data from

with summary:
    #summary_report(st.session_state[f"prepped_data{page_number}"])
    pass
with missing:
    #missing_report(st.session_state[f"prepped_data{page_number}"])
    pass
with survey_progress:
    #progress_report(st.session_state[f"prepped_data{page_number}"])
    pass
with duplicates:
    #duplicates_report(st.session_state[f"prepped_data{page_number}"])
    pass
with outliers:
    #outliers_report(st.session_state[f"prepped_data{page_number}"])
    pass
with enum_stats:
    #enumerator_report(st.session_state[f"prepped_data{page_number}"])
    pass

with desc_stats:
    #descriptive_report(st.session_state[f"prepped_data{page_number}"])
    pass

with back_checks:
    backchecks_report(st.session_state[f"prepped_data{page_number}"], st.session_state[f"prepped_data{page_number}"])