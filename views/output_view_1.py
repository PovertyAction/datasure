import streamlit as st

from src.checks import (
    backchecks_report,
    descriptive_report,
    duplicates_report,
    enumerator_report,
    gpschecks_report,
    missing_report,
    outliers_report,
    progress_report,
    summary_report,
)

# define page number
page_number = 1
page_data_index = page_number - 1

page_name = st.session_state.config_pages["Page Name"][page_data_index]
setting_file = f"cache/settings/pyDMS_hfc_settings_{page_name}.json"

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
    gps_checks,
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
        "GPS Checks",
    )
)

alias_list = list(filter(None, st.session_state.alias_list))

with summary:
    summary_report(
        data=st.session_state[f"prepped_data{page_data_index}"],
        setting_file=setting_file,
        page_num=page_number,
    )

with missing:
    missing_report(
        data=st.session_state[f"prepped_data{page_data_index}"],
        setting_file=setting_file,
        page_name=page_name,
    )

with survey_progress:
    progress_report(
        data=st.session_state[f"prepped_data{page_data_index}"],
        setting_file=setting_file,
        page_num=page_number,
    )

with duplicates:
    duplicates_report(
        data=st.session_state[f"prepped_data{page_data_index}"],
        setting_file=setting_file,
        page_num=page_number,
    )

with outliers:
    outliers_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with enum_stats:
    enumerator_report(
        data=st.session_state[f"prepped_data{page_data_index}"],
        setting_file=setting_file,
        page_num=page_number,
        page_name=page_name,
    )

with desc_stats:
    descriptive_report(
        data=st.session_state[f"prepped_data{page_data_index}"], page_num=page_number
    )

with back_checks:
    bc_data_name = st.session_state.config_pages["Back check data"][page_number - 1]
    if bc_data_name and bc_data_name in alias_list:
        page_bc_data_index = st.session_state.alias_list.index(bc_data_name)
        backcheck_data = st.session_state[f"prepped_data{page_bc_data_index}"]

        backchecks_report(
            survey_data=st.session_state[f"prepped_data{page_data_index}"],
            backcheck_data=backcheck_data,
            page_num=page_number,
        )

with gps_checks:
    gpschecks_report(
        data=st.session_state[f"prepped_data{page_data_index}"],
        setting_file=setting_file,
        page_num=page_number,
    )
