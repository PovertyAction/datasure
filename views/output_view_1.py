import streamlit as st
from src.checks import missing_report, progress_report, summary_report, duplicates_report, outliers_report

# define page number
page_number = 1

st.title(st.session_state[f"config_page_{page_number}"])

summary, survey_progress, duplicates, missing, outliers, enum_stats = st.tabs(
    (
        "Summary",
        "Survey Progress",
        "Duplicates",
        "Missing Data",
        "Outliers",
        "Enumerator Stats",
    )
)

alias_list = list(filter(None, st.session_state.alias_list))

# load data from

with summary:
    summary_report(st.session_state[f"prepped_data{page_number}"])

with missing:
    missing_report(st.session_state[f"prepped_data{page_number}"])

with survey_progress:
    progress_report(st.session_state[f"prepped_data{page_number}"])

with duplicates:
    duplicates_report(st.session_state[f"prepped_data{page_number}"])

with outliers:
    outliers_report(st.session_state[f"prepped_data{page_number}"])
