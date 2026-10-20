"""
Output view template for data quality checks reporting.

This module provides a reusable template for displaying data quality check reports
across multiple output pages. Each page can be configured independently with different
datasets and checks.
"""

import re

import polars as pl
import streamlit as st

from datasure.checks import catalogue
from datasure.checks.context import CheckContext, CheckData, PageConfig
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.config_utils import CheckConfiguration
from datasure.utils.dataframe_utils import (
    TableState,
    get_df_columns,
    get_table_state,
    no_rows_message,
)
from datasure.utils.duckdb_utils import (
    duckdb_get_table,
    duckdb_table_exists,
)
from datasure.utils.nav_ui import draw_nav, render_selected, resolve_selection
from datasure.utils.navigations_utils import (
    add_demo_navigation,
    demo_sidebar_help,
)
from datasure.utils.settings_utils import (
    get_check_config_settings,
)
from datasure.utils.ui_utils import page_header
from datasure.utils.view_state import (
    ViewState,
    reset_filters_button,
    save_selection,
    saved_selection,
)

__all__ = ["CheckData", "PageConfig", "no_rows_message"]

# URL query parameter holding the selected check, e.g. ?check=duplicates.
CHECK_PARAM = "check"


def check_nav_key(page_name_id: str) -> str:
    """Return the session state key prefix for a check page's navigation."""
    return f"check_nav_{page_name_id}"


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
) -> pl.DataFrame:
    """
    Load data with cascading fallback through multiple databases.

    Attempts to load data from databases in the specified order, returning the
    first table that exists. A table with no rows counts as found: a prep step
    or correction that dropped every record must not fall back to older data.

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
    pl.DataFrame
        The loaded data, or a DataFrame with no columns if none found.
    """
    for db_name in db_names:
        if duckdb_table_exists(project_id=project_id, alias=data_name, db_name=db_name):
            return duckdb_get_table(
                project_id=project_id,
                alias=data_name,
                db_name=db_name,
            )

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

    return CheckData(page_data=page_data, backcheck_data=backcheck_data)


def stop_if_no_survey_data(page_data: pl.DataFrame, data_name: str) -> None:
    """
    Stop the page with a message when the survey data is missing or has no rows.

    Parameters
    ----------
    page_data : pl.DataFrame
        The survey data loaded for the page.
    data_name : str
        The alias of the survey data, shown in the message.

    Raises
    ------
    SystemExit
        If the data is missing or has no rows (via st.stop()).
    """
    state = get_table_state(page_data)
    if state is TableState.HAS_ROWS:
        return

    if state is TableState.MISSING:
        st.info(
            f"No data found for **{data_name}**. Import it on the Import Data page."
        )
    else:
        st.info(no_rows_message(data_name, "check"))
    st.stop()


def render_checks(project_id: str, config: PageConfig, data: CheckData) -> None:
    """
    Render the check navigation and the selected check.

    Groups and checks come from the check catalogue. Only the selected
    check's report runs. The selection follows the ``check`` URL query
    parameter, then the check last opened on this page, then Summary.

    Parameters
    ----------
    project_id : str
        The project identifier.
    config : PageConfig
        Page configuration data.
    data : CheckData
        Loaded data for checks.
    """
    ctx = CheckContext(
        project_id=project_id,
        config=config,
        data=data,
        survey_columns=get_df_columns(data.page_data),
    )
    nav_key = check_nav_key(config.page_name_id)

    # The navigation sits above the check but is drawn after it, so a check
    # that fails while rendering is already marked in it.
    nav_slot = st.container()
    state = resolve_selection(
        catalogue.nav_items(ctx),
        key=nav_key,
        param=CHECK_PARAM,
        default=catalogue.DEFAULT_CHECK,
        saved=saved_selection(config.setting_file),
    )
    save_selection(config.setting_file, state.selected)
    reset_filters_button(ViewState(config.setting_file, state.selected), key=nav_key)
    entry = catalogue.get_check(state.selected)
    render_selected(
        nav_key,
        state.selected_item,
        render=lambda: entry.render(ctx),
        setup=None if entry.setup is None else lambda: entry.setup(ctx),
    )
    with nav_slot:
        draw_nav(state, key=nav_key, param=CHECK_PARAM, label="Check")


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
    page_header(
        page_title,
        "Review the results of the data quality checks configured for this page.",
    )

    # Load page configuration
    config = load_page_config(project_id, page_number)

    # Load data for checks
    data = load_check_data(project_id, config)
    stop_if_no_survey_data(data.page_data, config.survey_data_name)

    # Render the check navigation and the selected check
    render_checks(project_id, config, data)


# Execute main function when run as a Streamlit page
if __name__ == "__main__":
    main()
