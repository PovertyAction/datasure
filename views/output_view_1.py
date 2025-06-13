import polars as pl
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
from src.processing import correction_apply_action

# define project ID
project_id = st.session_state.st_project_id


# define page number
page_number = 1
page_data_index = page_number - 1

# define setting file
setting_file = f"cache/{project_id}/settings/checks_{page_data_index}.json"

page_name = st.session_state.config_pages["Page Name"][page_data_index]
key_col = st.session_state.config_pages["Survey KEY"][page_data_index]
correction_apply_action(
    data_index=page_data_index,
    key_col=key_col,
    page_name=page_name,
    project_id=project_id,
)

if isinstance(st.session_state[f"corrected_data{page_data_index}"], pl.DataFrame):
    page_data = st.session_state[f"corrected_data{page_data_index}"].to_pandas()
else:
    page_data = st.session_state[f"corrected_data{page_data_index}"]

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
        data=page_data,
        setting_file=setting_file,
        page_num=page_number,
    )

with missing:
    missing_report(
        project_id=project_id,
        data=page_data,
        setting_file=setting_file,
        page_name=page_name,
    )

with survey_progress:
    progress_report(
        data=page_data,
        setting_file=setting_file,
        page_num=page_number,
    )

with duplicates:
    duplicates_report(
        data=page_data,
        setting_file=setting_file,
        page_num=page_number,
    )

with outliers:
    outliers_report(
        data=page_data,
        setting_file=setting_file,
        page_num=page_number,
    )

with enum_stats:
    enumerator_report(
        project_id=project_id,
        data=page_data,
        setting_file=setting_file,
        page_num=page_number,
        page_name=page_name,
    )

with desc_stats:
    descriptive_report(
        data=page_data,
        setting_file=setting_file,
        page_num=page_number,
    )

with back_checks:
    bc_data_name = st.session_state.config_pages["Back check data"][page_number - 1]
    if bc_data_name and bc_data_name in alias_list:
        page_bc_data_index = st.session_state.alias_list.index(bc_data_name)
        backcheck_data = st.session_state[f"prepped_data{page_bc_data_index}"]

        backchecks_report(
            survey_data=page_data,
            backcheck_data=backcheck_data,
            page_num=page_number,
        )

with gps_checks:
    gpschecks_report(
        data=page_data,
        setting_file=setting_file,
        page_num=page_number,
    )
