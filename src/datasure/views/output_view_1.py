import streamlit as st

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
from datasure.utils import duckdb_get_table, get_cache_path, get_check_config_settings

# define page number
page_number = 1
page_data_index = page_number - 1

# define project ID
project_id = st.session_state.st_project_id

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
