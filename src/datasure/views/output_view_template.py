"""
Output view template for data quality checks reporting.

This module provides a reusable template for displaying data quality check reports
across multiple output pages. Each page can be configured independently with different
datasets and checks.
"""

import re
from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import polars as pl
import streamlit as st

from datasure.checks.backchecks import backchecks_report
from datasure.checks.duplicates import duplicates_report
from datasure.checks.enumerator import enumerator_report
from datasure.checks.gpschecks import gpschecks_report
from datasure.checks.missing import missing_report
from datasure.checks.outliers import outliers_report
from datasure.checks.progress import progress_report
from datasure.checks.summary import summary_report
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.config_utils import CheckConfiguration
from datasure.utils.dataframe_utils import get_df_columns
from datasure.utils.duckdb_utils import (
    duckdb_get_table,
)
from datasure.utils.navigations_utils import (
    add_demo_navigation,
    demo_sidebar_help,
)
from datasure.utils.settings_utils import (
    get_check_config_settings,
)


@dataclass
class PageConfig:
    """Configuration data for an output page."""

    page_number: int
    page_name: str
    page_name_id: str
    survey_data_name: str
    survey_key: str
    survey_id: str | None
    survey_date: str | None
    enumerator: str | None
    team: str | None
    formversion: str | None
    duration: str | None
    survey_target: int | None
    backcheck_data_name: str | None
    backcheck_date: str | None
    backchecker: str | None
    backchecker_team: str | None
    backcheck_target_percent: int | None
    tracking_data_name: str | None
    setting_file: Path
    missing_setting_file: Path


@dataclass
class CheckData:
    """Data required for running checks."""

    page_data: pd.DataFrame
    backcheck_data: pd.DataFrame | None = None


def extract_page_number(file_path: str) -> int | None:
    """
    Extract page number from filename.

    Expected format: 'output_view_X.py' where X is the page number.

    Parameters
    ----------
    file_path : str
        The file path to extract the page number from.

    Returns
    -------
    int | None
        The page number if found, None otherwise.
    """
    match = re.search(r"_view_(\d+)\.py$", file_path)
    return int(match.group(1)) if match else None


def load_data_with_fallback(
    project_id: str,
    data_name: str,
    db_names: tuple[str, ...] = ("corrected", "prep", "raw"),
) -> pd.DataFrame:
    """
    Load data with cascading fallback through multiple databases.

    Attempts to load data from databases in the specified order, returning the
    first non-empty dataset found.

    Parameters
    ----------
    project_id : str
        The project identifier.
    data_name : str
        The name/alias of the data table to load.
    db_names : tuple[str, ...]
        Database names to try in order (default: corrected -> prep -> raw).

    Returns
    -------
    pd.DataFrame
        The loaded data, or an empty DataFrame if none found.
    """
    for db_name in db_names:
        data = duckdb_get_table(
            project_id=project_id,
            alias=data_name,
            db_name=db_name,
        )
        if not data.is_empty():
            return data

    # Return empty DataFrame if all attempts fail
    return pl.DataFrame()


def get_page_title(page_number: int, check_log: pl.DataFrame) -> str:
    """
    Generate the page title based on configuration.

    Parameters
    ----------
    project_id : str
        The project identifier.
    page_number : int
        The page number for this output view.
    check_log : pl.DataFrame
        The check configuration log.

    Returns
    -------
    str
        The formatted page title.
    """
    if check_log.is_empty():
        return f"Data Quality Checks - page {page_number}"

    page_data_index = page_number - 1
    page_name = check_log[page_data_index, "page_name"]
    return f"Data Quality Checks - {page_name}"


def load_page_config(project_id: str, page_number: int) -> PageConfig:
    """
    Load all configuration data for a specific output page.

    Parameters
    ----------
    project_id : str
        The project identifier.
    page_number : int
        The page number to load configuration for.

    Returns
    -------
    PageConfig
        Complete configuration data for the page.

    Raises
    ------
    ValueError
        If the page configuration cannot be loaded.
    """
    page_data_index = page_number - 1

    # Get configuration from check_config table
    check_config_info: dict = get_check_config_settings(
        project_id=project_id,
        page_row_index=page_data_index,
    )

    check_config = CheckConfiguration(**check_config_info)

    # Validate configuration
    page_name = check_config.page_name

    # Generate page name ID for file naming
    page_name_id = page_name.lower().replace(" ", "_").replace("-", "_")

    # Set up setting file paths
    cache_settings_base = get_cache_path(project_id, "settings")
    setting_file = cache_settings_base / f"page_{page_name_id}_settings.json"
    missing_setting_file = (
        cache_settings_base / f"page_{page_name_id}_missing_settings.json"
    )

    return PageConfig(
        page_number=page_number,
        page_name=page_name,
        page_name_id=page_name_id,
        survey_data_name=check_config.survey_data_name,
        survey_key=check_config.survey_key,
        survey_id=check_config.survey_id,
        survey_date=check_config.survey_date,
        enumerator=check_config.enumerator,
        team=check_config.team,
        formversion=check_config.formversion,
        duration=check_config.duration,
        survey_target=check_config.survey_target,
        backcheck_data_name=check_config.backcheck_data_name,
        backcheck_date=check_config.backcheck_date,
        backchecker=check_config.backchecker,
        backchecker_team=check_config.backchecker_team,
        backcheck_target_percent=check_config.backcheck_target_percent,
        tracking_data_name=check_config.tracking_data_name,
        setting_file=setting_file,
        missing_setting_file=missing_setting_file,
    )


def load_check_data(project_id: str, config: PageConfig) -> CheckData:
    """
    Load all data required for running checks.

    Parameters
    ----------
    project_id : str
        The project identifier.
    config : PageConfig
        Page configuration containing data source information.

    Returns
    -------
    CheckData
        Loaded data for running checks.
    """
    # Load main survey data
    page_data = load_data_with_fallback(project_id, config.survey_data_name)

    # Load backcheck data if configured
    backcheck_data = None
    if config.backcheck_data_name:
        backcheck_data = load_data_with_fallback(project_id, config.backcheck_data_name)
        if backcheck_data.is_empty():
            backcheck_data = None

    return CheckData(page_data=page_data, backcheck_data=backcheck_data)


def render_check_tabs(project_id: str, config: PageConfig, data: CheckData) -> None:
    """
    Render all data quality check tabs.

    Parameters
    ----------
    project_id : str
        The project identifier.
    config : PageConfig
        Page configuration data.
    data : CheckData
        Loaded data for checks.
    """
    # Create tabs
    (
        summary,
        progress,
        missing,
        duplicates,
        outliers,
        gps_checks,
        enumerator_stats,
        backcheck_analysis,
    ) = st.tabs(
        (
            "Summary",
            "Progress Tracking",
            "Missing Values",
            "Duplicates",
            "Outliers & Constraints",
            "GPS Checks",
            "Enumerator Statistics",
            "Backcheck Analysis",
        )
    )

    # get columns by type
    survey_columns = get_df_columns(data.page_data)

    # Render each tab
    with summary:
        summary_config: dict = {
            "survey_id": config.survey_id,
            "survey_date": config.survey_date,
            "survey_target": config.survey_target,
        }
        summary_report(
            data.page_data, config.setting_file, summary_config, survey_columns
        )

    with progress:
        progress_config: dict = {
            "survey_key": config.survey_key,
            "survey_id": config.survey_id,
            "enumerator": config.enumerator,
            "survey_date": config.survey_date,
            "survey_target": config.survey_target,
        }
        progress_report(
            data.page_data,
            config.setting_file,
            progress_config,
            survey_columns,
        )

    with missing:
        missing_report(
            project_id,
            config.page_name_id,
            data.page_data,
            config.setting_file,
        )

    with duplicates:
        duplicates_config: dict = {
            "survey_key": config.survey_key,
            "survey_id": config.survey_id,
            "enumerator": config.enumerator,
            "team": config.team,
            "survey_date": config.survey_date,
        }
        duplicates_report(
            project_id,
            config.page_name_id,
            data.page_data,
            config.setting_file,
            duplicates_config,
            survey_columns,
        )

    with outliers:
        outliers_config: dict = {
            "survey_key": config.survey_key,
            "survey_id": config.survey_id,
            "enumerator": config.enumerator,
            "team": config.team,
            "survey_date": config.survey_date,
        }
        outliers_report(
            project_id,
            config.page_name_id,
            data.page_data,
            config.setting_file,
            outliers_config,
            survey_columns,
        )

    with gps_checks:
        gpschecks_config: dict = {
            "survey_key": config.survey_key,
            "survey_id": config.survey_id,
            "survey_date": config.survey_date,
            "enumerator": config.enumerator,
            "team": config.team,
        }
        gpschecks_report(
            project_id,
            config.page_name_id,
            data.page_data,
            config.setting_file,
            gpschecks_config,
            survey_columns,
        )

    with enumerator_stats:
        enumerator_stats_config: dict = {
            "survey_key": config.survey_key,
            "survey_id": config.survey_id,
            "survey_date": config.survey_date,
            "enumerator": config.enumerator,
            "formversion": config.formversion,
            "duration": config.duration,
            "team": config.team,
        }
        enumerator_report(
            project_id,
            data.page_data,
            config.setting_file,
            enumerator_stats_config,
            survey_columns,
        )

    with backcheck_analysis:
        if data.backcheck_data is not None:
            backcheck_columns = get_df_columns(data.backcheck_data)
            backcheck_config: dict = {
                "survey_key": config.survey_key,
                "survey_id": config.survey_id,
                "survey_date": config.survey_date,
                "backcheck_date": config.backcheck_date,
                "enumerator": config.enumerator,
                "backchecker": config.backchecker,
                "backchecker_team": config.backchecker_team,
                "backcheck_target_percent": config.backcheck_target_percent,
            }
            backchecks_report(
                project_id,
                config.page_name_id,
                data.page_data,
                data.backcheck_data,
                config.setting_file,
                backcheck_config,
                survey_columns,
                backcheck_columns,
            )
        else:
            st.info("No backcheck data available for analysis.")


def validate_prerequisites(project_id: str | None) -> pl.DataFrame:
    """
    Validate that all prerequisites are met before rendering the page.

    Parameters
    ----------
    project_id : str | None
        The project identifier.

    Returns
    -------
    pl.DataFrame
        The check configuration log.

    Raises
    ------
    SystemExit
        If prerequisites are not met (via st.stop()).
    """
    if not project_id:
        st.info(
            "Select a project from the Start page and import data. "
            "You can also create a new project from the Start page."
        )
        st.stop()

    # Load check configuration
    check_log = duckdb_get_table(
        project_id=project_id, alias="check_config", db_name="logs"
    )

    if check_log.is_empty():
        st.info(
            "No checks configured. Please configure checks on the "
            "Configure Checks page."
        )
        st.stop()

    return check_log


def main() -> None:
    """
    Main entry point for the output view template.

    This function orchestrates the entire page rendering process, including:
    - Setting up navigation and demo helpers
    - Extracting page number from filename
    - Validating prerequisites
    - Loading configuration and data
    - Rendering the UI
    """
    # Set up demo navigation and help
    demo_sidebar_help()
    add_demo_navigation("output_view_1", step=5)

    # Extract page number from filename
    page_number = extract_page_number(__file__)
    if page_number is None:
        st.error("Could not determine page number from filename.")
        st.stop()

    # Get project ID from session state
    project_id = st.session_state["st_project_id"]

    # Validate prerequisites and get check log
    check_log = validate_prerequisites(project_id)

    # Set page title
    page_title = get_page_title(page_number, check_log)
    st.title(page_title)

    # Load page configuration
    config = load_page_config(project_id, page_number)

    # Load data for checks
    data = load_check_data(project_id, config)

    # Render check tabs
    render_check_tabs(project_id, config, data)


# Execute main function when run as a Streamlit page
if __name__ == "__main__":
    main()
