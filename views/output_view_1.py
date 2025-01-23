import streamlit as st

from src.checks import (
    backchecks_report,
    descriptive_report,
    duplicates_report,
    enumerator_report,
    missing_report,
    outliers_report,
    progress_report,
    summary_report,
)

# define page number
page_number = 1
page_data_index = page_number - 1

st.title(st.session_state[f"config_page_{page_number}"])

(
    summary,
    survey_progress,
    duplicates,
    missing,
    outliers,
    enum_stats,
    desc_stats,
    back_checks,
) = st.tabs(
    (
        "Summary",
        "Survey Progress",
        "Duplicates",
        "Missing Data",
        "Outliers",
        "Enumerator Stats",
        "Descriptive Stats",
        "Back Checks",
    )
)

alias_list = list(filter(None, st.session_state.alias_list))

# load data from

with summary:
    summary_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with missing:
    missing_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with survey_progress:
    progress_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with duplicates:
    duplicates_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with outliers:
    outliers_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with enum_stats:
    enumerator_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with desc_stats:
    descriptive_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with back_checks:
    backchecks_report(
        survey_data=st.session_state[f"prepped_data{page_data_index}"],
        backcheck_data=st.session_state[f"prepped_data{page_data_index}"],
        page_num=page_number,
    )
