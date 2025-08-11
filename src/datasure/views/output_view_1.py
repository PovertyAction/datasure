import re

import streamlit as st
from utils import duckdb_get_table, get_cache_path, get_check_config_settings

from datasure.checks import (
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


def get_page_number() -> int | None:
    """
    Get the page number from filename.
    The filename should be in the format 'output_view_X.py' where X is the page number.

    Parameters
    ----------
        None
    Returns:
        int: The Page Number.
    """
    match = re.search(r"_view_(\d+)\.py$", __file__)
    if match:
        return int(match.group(1))
    return None


# Get Page Number from filename
page_number = get_page_number()
page_data_index = page_number - 1

# define project ID
project_id = st.session_state.st_project_id

st.title(f"DQA Report {page_number}")

if not project_id:
    st.info(
        "Select a project from the Start page and import data. You can also create a new project from the Start page."
    )
    st.stop()

# if no configured checks, stop
check_log = duckdb_get_table(
    project_id=project_id, alias="check_config", db_name="logs"
)

if check_log.is_empty():
    st.info(
        "No checks configured. Please configure checks on the Configure Checks page."
    )
    st.stop()

# get page config information
(
    page_name,
    survey_data_name,
    survey_key,
    survey_id,
    survey_date,
    enumerator,
    backcheck_data_name,
    tracking_data_name,
) = get_check_config_settings(
    project_id=project_id,
    page_row_index=page_data_index,
)

# get_page_name_id from page name
page_name_id = page_name.lower().replace(" ", "_").replace("-", "_")

# set setting file path
cache_settings_base = get_cache_path(project_id, "settings")

# define setting file
setting_file = cache_settings_base / f"page_{page_name_id}_settings.json"
missing_setting_file = (
    cache_settings_base / f"page_{page_name_id}_missing_settings.json"
)

# load corrected data for page
page_data = duckdb_get_table(
    project_id,
    survey_data_name,
    db_name="corrected",
    type="pd",
)
# if corrected data is empty, load prep data
if page_data.empty:
    page_data = duckdb_get_table(
        project_id,
        survey_data_name,
        db_name="prep",
        type="pd",
    )
    # if prep data is empty, load raw data
    if page_data.empty:
        page_data = duckdb_get_table(
            project_id,
            survey_data_name,
            db_name="raw",
            type="pd",
        )

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


with summary:
    summary_report(
        project_id,
        page_data,
        setting_file,
        page_number,
    )

with missing:
    missing_report(
        project_id,
        page_data,
        setting_file,
        page_name,
    )

with survey_progress:
    progress_report(
        project_id,
        page_data,
        setting_file,
        page_number,
    )

with duplicates:
    duplicates_report(
        project_id,
        page_data,
        setting_file,
        page_number,
    )

with outliers:
    outliers_report(
        project_id,
        page_data,
        setting_file,
        page_number,
    )

with enum_stats:
    enumerator_report(
        project_id,
        page_data,
        setting_file,
        missing_setting_file,
        page_number,
    )

with desc_stats:
    descriptive_report(
        page_data,
        setting_file,
        page_number,
    )

with back_checks:
    if backcheck_data_name:
        # load backcheck data
        backcheck_data = duckdb_get_table(
            project_id,
            backcheck_data_name,
            db_name="corrected",
            type="pd",
        )

        # if corrected backcheck data is empty, load prep data
        if backcheck_data.empty:
            backcheck_data = duckdb_get_table(
                project_id, backcheck_data_name, db_name="prep", type="pd"
            )

        # if prep backcheck data is empty, load raw data
        if backcheck_data.empty:
            backcheck_data = duckdb_get_table(
                project_id,
                backcheck_data_name,
                db_name="raw",
                type="pd",
            )

        backchecks_report(
            project_id,
            page_data,
            backcheck_data,
            setting_file,
            page_number,
        )

with gps_checks:
    gpschecks_report(
        project_id,
        page_data,
        setting_file,
        page_number,
    )
