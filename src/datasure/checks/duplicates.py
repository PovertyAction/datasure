"""Duplicates detection module for survey data quality checks.

This module provides comprehensive duplicate detection functionality with:
- Survey ID duplicate detection with statistics and metrics
- Column-level duplicate analysis with configurable patterns
- Flexible filtering conditions for targeted duplicate detection
- Duplicate statistics and reporting
- Configurable duplicate checking with pattern matching
- Modular, testable architecture with Pydantic validation
"""

import datetime
import logging
import re
from dataclasses import dataclass

import polars as pl
import streamlit as st

from datasure.checks.backchecks.models import TAB_NAME as BACKCHECKS_TAB_NAME
from datasure.checks.id_duplicates_ui import (
    BACKCHECK_DATA,
    IdView,
    count_duplicate_ids,
    render_dataset_switcher,
    render_id_duplicates,
)
from datasure.models.enums import (
    NumCondition,
    SearchType,
    StrCondition,
)
from datasure.models.schemas import (
    DateDefaults,
    DuplicatesSettings,
    DuplicatesStats,
    FilterCondition,
)
from datasure.utils.dataframe_utils import ColumnByType
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.navigations_utils import demo_callout
from datasure.utils.onboarding_utils import demo_output_onboarding, is_demo_project
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

logger = logging.getLogger(__name__)

TAB_NAME = "duplicates"
BACKCHECK_PREFIX = "backcheck_"

# =============================================================================
# Settings Management Functions
# =============================================================================


@st.cache_data(ttl=60)
def load_default_duplicates_settings(
    settings_file: str, config: DuplicatesSettings
) -> DuplicatesSettings:
    """Load and merge saved settings with default configuration.

    Loads previously saved duplicates report settings from the settings file
    and merges them with the provided default configuration. Saved settings
    take precedence over defaults.

    Cached for 60 seconds to reduce file I/O operations.

    Parameters
    ----------
    settings_file : str
        Path to the settings file containing saved configurations.
    config : DuplicatesSettings
        Default configuration to use as fallback for missing settings.

    Returns
    -------
    DuplicatesSettings
        Merged settings combining saved and default configurations.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME)

    default_settings: dict = dict(config)
    default_settings.update(saved_settings)

    return DuplicatesSettings(**default_settings)


@demo_output_onboarding(TAB_NAME)
def duplicates_report_settings(
    project_id: str,
    settings_file: str,
    data: pl.DataFrame,
    config: DuplicatesSettings,
    categorical_columns: list[str],
    datetime_columns: list[str],
    backcheck_data: pl.DataFrame | None = None,
) -> DuplicatesSettings:
    """Create and render the settings UI for duplicates report configuration.

    This function creates a comprehensive Streamlit UI for configuring
    duplicates report settings. It includes:
    - Survey identifiers (key and ID columns)
    - Survey date column selection
    - Enumerator ID column
    - Filtering conditions for targeted duplicate detection

    Settings are automatically saved to the settings file when changed
    and loaded from previous sessions if available.

    Parameters
    ----------
    project_id : str
        Unique project identifier for database operations.
    settings_file : str
        Path to settings file for saving/loading configurations.
    data : pl.DataFrame
        Dataset to analyze for duplicates.
    config : DuplicatesSettings
        Default configuration used as fallback values.
    categorical_columns : list[str]
        Available categorical columns for selection (survey key, ID, enumerator).
    datetime_columns : list[str]
        Available datetime columns for date selection.
    backcheck_data : pl.DataFrame | None, default=None
        The page's backcheck data. When given, a separate Records to Include
        filter is shown for it.

    Returns
    -------
    DuplicatesSettings
        User-configured settings from the UI.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for duplicates report")
        st.write("---")

        default_settings = load_default_duplicates_settings(settings_file, config)

        # Survey Identifiers
        with st.container(border=True):
            st.subheader("Survey Identifiers")
            si1, si2, _ = st.columns(3)

            with si1:
                default_survey_key = default_settings.survey_key
                default_survey_key_index = (
                    categorical_columns.index(default_survey_key)
                    if default_survey_key and default_survey_key in categorical_columns
                    else None
                )
                survey_key = st.selectbox(
                    "Survey Key",
                    options=categorical_columns,
                    key="survey_key_duplicates",
                    help="Select the column that contains the survey key",
                    index=default_survey_key_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_key"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_key": survey_key})

            with si2:
                default_survey_id = default_settings.survey_id
                default_survey_id_index = (
                    categorical_columns.index(default_survey_id)
                    if default_survey_id and default_survey_id in categorical_columns
                    else None
                )
                survey_id = st.selectbox(
                    "Survey ID",
                    options=categorical_columns,
                    help="Select the column that contains the survey ID",
                    key="survey_id_duplicates",
                    index=default_survey_id_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_id"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_id": survey_id})

        with st.container(border=True):
            st.subheader("Survey Date")

            sd1, _, _ = st.columns(3)

            with sd1:
                default_survey_date = default_settings.survey_date
                default_survey_date_index = (
                    datetime_columns.index(default_survey_date)
                    if default_survey_date and default_survey_date in datetime_columns
                    else None
                )

                survey_date = st.selectbox(
                    "Survey Date",
                    options=datetime_columns,
                    help="Select the column that contains the survey date",
                    key="survey_date_duplicates",
                    index=default_survey_date_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_date"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"survey_date": survey_date}
                )

        with st.container(border=True):
            st.subheader("Enumerator")
            ec1, _, _ = st.columns(3)
            with ec1:
                default_enumerator = default_settings.enumerator
                default_enumerator_index = (
                    categorical_columns.index(default_enumerator)
                    if default_enumerator and default_enumerator in categorical_columns
                    else None
                )
                enumerator = st.selectbox(
                    "Enumerator ID",
                    options=categorical_columns,
                    key="enumerator_duplicates",
                    help="Select the column that contains the enumerator ID",
                    index=default_enumerator_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_enumerator"},
                )
                save_check_settings(settings_file, TAB_NAME, {"enumerator": enumerator})

        with st.container(border=True):
            st.subheader("Missing Values")
            st.caption(
                "Controls how duplicates are matched, not which records are checked."
            )
            missing_as_duplicates = _render_missing_as_duplicates_toggle(settings_file)

        with st.container(border=True):
            st.subheader("Records to Include")
            st.info(
                "By default, the duplicates check runs on every record. Use the "
                "filter below to check duplicates only within a subset — for "
                "example, only households with `consent == Yes` or "
                "`interview_status == Complete`. Records that don't match the "
                "condition are excluded from the duplicates analysis entirely."
            )

            conditions = _render_duplicates_condition_options(
                data, settings_file, missing_as_duplicates
            )

        backcheck_conditions: dict = {}
        if backcheck_data is not None:
            with st.container(border=True):
                st.subheader("Backcheck Records to Include")
                st.info(
                    "Check backcheck IDs only within a subset of the backcheck "
                    "data, for example to leave out a backchecker's failed "
                    "first visit. This filter is separate from the survey "
                    "filter above."
                )
                backcheck_conditions = _render_duplicates_condition_options(
                    backcheck_data,
                    settings_file,
                    missing_as_duplicates,
                    prefix=BACKCHECK_PREFIX,
                )

    return DuplicatesSettings(
        filtered_data=None,
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        enumerator=enumerator,
        team=default_settings.team,
        conditions=conditions,
        backcheck_conditions=backcheck_conditions,
    )


# =============================================================================
# Column Selection and Pattern Matching Functions
# =============================================================================


@st.cache_data(ttl=300)
def expand_col_names(
    all_columns: list[str], pattern: str, search_type: str = SearchType.EXACT.value
) -> list[str]:
    """Expand column names based on search pattern.

    Supports multiple search types for flexible column matching:
    - exact: Match column name exactly
    - startswith: Match columns starting with pattern
    - endswith: Match columns ending with pattern
    - contains: Match columns containing pattern anywhere
    - regex: Match columns using regular expression

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    all_columns : list[str]
        List of all available column names.
    pattern : str
        Pattern string to match against column names.
    search_type : str, default=SearchType.EXACT.value
        Type of search to perform.

    Returns
    -------
    list[str]
        List of column names matching the search criteria.

    Examples
    --------
    >>> columns = ["income_farm", "income_wage", "expense_total"]
    >>> expand_col_names(columns, "income_", "startswith")
    ['income_farm', 'income_wage']
    """
    if search_type == SearchType.EXACT.value:
        return [col for col in all_columns if col == pattern]
    elif search_type == SearchType.STARTSWITH.value:
        return [col for col in all_columns if col.startswith(pattern)]
    elif search_type == SearchType.ENDSWITH.value:
        return [col for col in all_columns if col.endswith(pattern)]
    elif search_type == SearchType.CONTAINS.value:
        return [col for col in all_columns if pattern in col]
    elif search_type == SearchType.REGEX.value:
        try:
            regex = re.compile(pattern)
            return [col for col in all_columns if regex.search(col)]
        except re.error:
            st.error(f"Invalid regex pattern: {pattern}")
            return []
    return []


def _create_search_type_info(search_type: str) -> None:
    """Display informational message about the selected search type.

    Parameters
    ----------
    search_type : str
        The selected search type from SearchType enum.
    """
    info_messages = {
        SearchType.EXACT.value: "Select columns directly from the dropdown.",
        SearchType.STARTSWITH.value: "Enter a pattern that column names start with (e.g., 'income_' matches 'income_farm', 'income_wage').",
        SearchType.ENDSWITH.value: "Enter a pattern that column names end with (e.g., '_total' matches 'income_total', 'expense_total').",
        SearchType.CONTAINS.value: "Enter a pattern that appears anywhere in column names (e.g., 'age' matches 'age_hh', 'average_age').",
        SearchType.REGEX.value: "Enter a regular expression pattern (e.g., '^q[0-9]+$' matches 'q1', 'q2', etc.).",
    }

    if search_type in info_messages:
        st.info(info_messages[search_type])


# =============================================================================
# Duplicates Column Configuration UI Functions
# =============================================================================


def _render_duplicates_column_actions(
    project_id: str, page_name_id: str, all_columns: list[str]
) -> None:
    """Render the duplicates column configuration UI.

    Displays buttons for adding and deleting duplicate column configurations,
    and shows the current settings table.

    Parameters
    ----------
    project_id : str
        Project identifier for database operations.
    page_name_id : str
        Page name identifier for storing configurations.
    all_columns : list[str]
        List of all columns available for duplicate checking.
    """
    duplicates_settings = duckdb_get_table(
        project_id,
        f"duplicates_{page_name_id}",
        "logs",
    )

    os1, os2, _ = st.columns([0.4, 0.3, 0.3])
    with os1:
        st.button(
            "Add Duplicates Column(s)",
            key="add_duplicates_column",
            help="Add columns to check for duplicates.",
            width="stretch",
            type="primary",
            on_click=_add_duplicates_column,
            args=(
                project_id,
                page_name_id,
                all_columns,
            ),
        )
    with os2:
        _delete_duplicates_column(project_id, page_name_id, duplicates_settings)

    if duplicates_settings.is_empty():
        st.info(
            "Use the :material/add: button to add columns to check for duplicates and the "
            ":material/delete: button to remove columns."
        )
    else:
        _render_duplicates_settings_table(duplicates_settings)


@st.dialog("Add Duplicates Column(s)", width="medium")
def _add_duplicates_column(
    project_id: str, page_name_id: str, all_columns: list[str]
) -> None:
    """Dialog to add a new duplicates column configuration.

    Parameters
    ----------
    project_id : str
        Project identifier for database operations.
    page_name_id : str
        Page name identifier for storing configurations.
    all_columns : list[str]
        List of all columns available for duplicate checking.
    """
    search_type, pattern, dup_cols, lock_cols_initial = _render_search_type_selection(
        all_columns
    )

    if dup_cols:
        lock_cols = _render_column_locking_options(
            dup_cols, search_type, lock_cols_initial
        )

        button_disabled = not dup_cols
        if st.button(
            "Add Duplicates Configuration",
            key="confirm_add_duplicates_column",
            type="primary",
            width="stretch",
            disabled=button_disabled,
        ):
            _update_duplicates_column_config(
                project_id,
                page_name_id,
                search_type,
                pattern,
                dup_cols,
                lock_cols,
            )

            st.success("Duplicates configuration added successfully.")
            st.rerun()


def _render_search_type_selection(
    all_columns: list[str],
) -> tuple[str, str | None, list[str], bool | None]:
    """Render search type selection UI.

    Parameters
    ----------
    all_columns : list[str]
        List of all available columns.

    Returns
    -------
    tuple[str, str | None, list[str], bool | None]
        Tuple containing:
        - search_type: Selected search type
        - pattern: Pattern string (None for exact search)
        - selected_columns: List of matched columns
        - lock_cols: Initial lock state (None for exact search)
    """
    search_type_options = [e.value for e in SearchType]
    search_type = st.selectbox(
        label="Search type",
        options=search_type_options,
        index=0,
        help="Select the type of search to perform on the column names.",
    )

    _create_search_type_info(search_type)

    if search_type == SearchType.EXACT.value:
        dup_cols_sel = st.multiselect(
            label="Select columns to check for duplicates",
            options=all_columns,
            default=None,
            help="Select columns to check for duplicate values.",
        )
        pattern, lock_cols = None, None
        return search_type, pattern, dup_cols_sel, lock_cols
    else:
        pattern = st.text_input(
            label="Enter pattern to match column names",
            placeholder="Enter pattern to match column names",
            help="Enter the pattern to match column names based on the "
            "selected search type.",
        )
        if pattern:
            dup_cols_patt = expand_col_names(
                all_columns, pattern, search_type=search_type
            )
        else:
            dup_cols_patt = []

        st.write(
            "**Columns Selected:** ",
            ", ".join(dup_cols_patt) if dup_cols_patt else "None",
        )
        return search_type, pattern, dup_cols_patt, None


def _render_column_locking_options(
    dup_cols: list[str], search_type: str, lock_cols_initial: bool | None
) -> bool:
    """Render column locking option.

    Allows users to lock column selections to prevent dynamic updates
    when pattern matches change.

    Parameters
    ----------
    dup_cols : list[str]
        Selected duplicate columns.
    search_type : str
        Search type used for column selection.
    lock_cols_initial : bool | None
        Initial lock_cols value.

    Returns
    -------
    bool
        Lock columns flag.
    """
    if lock_cols_initial is not None:
        return lock_cols_initial

    lock_cols = st.toggle(
        label="Lock column selection",
        key="duplicates_cols_lock",
        help="Lock the selected columns to prevent changes when pattern matches change.",
        disabled=not dup_cols
        or len(dup_cols) < 2
        or search_type == SearchType.EXACT.value,
    )
    return lock_cols


@st.fragment
def _render_datetime_condition_input(
    condition_type: str,
    default_condition_value,
    prefix: str = "",
):
    """Render date input widget for datetime condition values.

    Parameters
    ----------
    condition_type : str
        The selected condition type.
    default_condition_value
        Saved default value to restore.
    prefix : str, default=""
        Prefix for the filter's widget keys and saved settings.

    Returns
    -------
    tuple
        (condition_value, condition_value_dict) where dict has serialized value.
    """
    min_date = DateDefaults().start_date
    max_date = DateDefaults().end_date

    date_range = (
        (DateDefaults().default_start_date, DateDefaults().default_end_date)
        if condition_type in [NumCondition.IN_RANGE.value]
        else DateDefaults().default_start_date
    )

    default_condition_value = _validate_duplicates_condition_date_value(
        default_condition_value, date_range
    )

    condition_value = st.date_input(
        value=default_condition_value,
        min_value=min_date,
        max_value=max_date,
        label="Condition Value",
        key=f"duplicates_{prefix}condition_date_value_key",
        help="Select the date value to filter the condition column.",
        on_change=trigger_save,
        kwargs={"state_name": f"{TAB_NAME}_{prefix}condition_value"},
    )
    condition_value_dict = {
        f"{prefix}condition_value": _serialize_condition_value_for_json(condition_value)
    }
    return condition_value, condition_value_dict


def _render_numeric_condition_input(
    condition_type: str,
    default_condition_value,
    condition_values: list,
    prefix: str = "",
):
    """Render input widget for numeric condition values.

    Parameters
    ----------
    condition_type : str
        The selected condition type.
    default_condition_value
        Saved default value to restore.
    condition_values : list
        Unique values in the condition column.
    prefix : str, default=""
        Prefix for the filter's widget keys and saved settings.

    Returns
    -------
    The selected condition value.
    """
    state_name = f"{TAB_NAME}_{prefix}condition_value"
    if not default_condition_value:
        default_condition_value = (
            min(condition_values),
            max(condition_values),
        )

    if condition_type == NumCondition.IN_RANGE.value:
        return st.slider(
            label="Condition Value Range",
            min_value=min(condition_values),
            max_value=max(condition_values),
            value=default_condition_value,
            key=f"duplicates_{prefix}condition_numeric_range_value_key",
            help="Select the numeric range to filter the condition column.",
            on_change=trigger_save,
            kwargs={"state_name": state_name},
        )

    if condition_type in [NumCondition.INCLUDES.value, NumCondition.EXCLUDES.value]:
        if not isinstance(default_condition_value, list):
            default_condition_value = [default_condition_value]
        return st.multiselect(
            label="Condition Values",
            options=condition_values,
            key=f"duplicates_{prefix}condition_numeric_multivalue_key",
            help="Select the numeric values to filter the condition column.",
            on_change=trigger_save,
            kwargs={"state_name": state_name},
        )

    if isinstance(default_condition_value, list):
        default_condition_value = default_condition_value[0]
    else:
        default_condition_value = None

    return st.number_input(
        label="Condition Value",
        value=default_condition_value,
        key=f"duplicates_{prefix}condition_numeric_value_key",
        help="Enter the numeric value to filter the condition column.",
        on_change=trigger_save,
        kwargs={"state_name": state_name},
    )


def _render_string_condition_input(
    condition_type: str,
    saved_settings: dict,
    condition_values: list,
    prefix: str = "",
):
    """Render input widget for string condition values.

    Parameters
    ----------
    condition_type : str
        The selected condition type.
    saved_settings : dict
        Saved settings dictionary.
    condition_values : list
        Unique values in the condition column.
    prefix : str, default=""
        Prefix for the filter's widget keys and saved settings.

    Returns
    -------
    The selected condition value.
    """
    state_name = f"{TAB_NAME}_{prefix}condition_value"
    default_condition_value = saved_settings.get(f"{prefix}condition_value", [])
    if default_condition_value and not isinstance(default_condition_value, list):
        default_condition_value = [default_condition_value]

    if condition_type in [StrCondition.INCLUDES.value, StrCondition.EXCLUDES.value]:
        return st.multiselect(
            label="Condition Values",
            options=condition_values,
            default=default_condition_value,
            key=f"duplicates_{prefix}condition_string_multivalue",
            help="Select the string values to filter the condition column.",
            on_change=trigger_save,
            kwargs={"state_name": state_name},
        )

    return st.text_input(
        label="Condition Value",
        value=default_condition_value
        if isinstance(default_condition_value, str)
        else None,
        key=f"duplicates_{prefix}condition_string_value_key",
        help="Enter the string value to filter the condition column.",
        on_change=trigger_save,
        kwargs={"state_name": state_name},
    )


def _render_condition_value_input(
    data: pl.DataFrame,
    condition_col: str,
    condition_type: str,
    saved_settings: dict,
    condition_values: list,
    prefix: str = "",
) -> tuple:
    """Render the appropriate condition value input based on column dtype.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset to analyze.
    condition_col : str
        Selected condition column name.
    condition_type : str
        The selected condition type.
    saved_settings : dict
        Saved settings dictionary.
    condition_values : list
        Unique values in the condition column.
    prefix : str, default=""
        Prefix for the filter's widget keys and saved settings.

    Returns
    -------
    tuple
        (condition_value, condition_value_dict) for saving settings.
    """
    default_condition_value = saved_settings.get(f"{prefix}condition_value")
    col_dtype = data[condition_col].dtype

    if col_dtype in pl.DATETIME_DTYPES:
        return _render_datetime_condition_input(
            condition_type, default_condition_value, prefix
        )

    if col_dtype in pl.NUMERIC_DTYPES:
        condition_value = _render_numeric_condition_input(
            condition_type, default_condition_value, condition_values, prefix
        )
        return condition_value, {}

    condition_value = _render_string_condition_input(
        condition_type, saved_settings, condition_values, prefix
    )
    return condition_value, {}


def _render_missing_as_duplicates_toggle(settings_file: str) -> bool:
    """Render the toggle controlling missing-value handling for duplicate matching.

    Parameters
    ----------
    settings_file : str
        Path to settings file for persisting configurations.

    Returns
    -------
    bool
        Whether missing values should be treated as duplicates.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME)

    default_missing_as_duplicates = saved_settings.get("missing_as_duplicates", False)
    missing_as_duplicates = st.toggle(
        label="Consider missing values as duplicates",
        value=default_missing_as_duplicates,
        key="duplicates_missing_as_duplicates_key",
        help=(
            "If enabled, two records with a missing value in the same column "
            "count as a duplicate pair. If disabled, missing values are never "
            "matched as duplicates."
        ),
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_missing_as_duplicates"},
    )
    save_check_settings(
        settings_file, TAB_NAME, {"missing_as_duplicates": missing_as_duplicates}
    )
    return missing_as_duplicates


def _render_duplicates_condition_options(
    data: pl.DataFrame,
    settings_file: str,
    missing_as_duplicates: bool,
    prefix: str = "",
) -> dict:
    """Render a Records to Include filter and return its conditions.

    The filter is saved in the page's settings file under keys starting with
    `prefix`, so each page, and the survey and backcheck data on a page, keep
    their own filter. Apply it with `apply_records_to_include`.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset the filter applies to.
    settings_file : str
        Path to settings file for persisting configurations.
    missing_as_duplicates : bool
        Whether missing values should be treated as duplicates, as configured
        by `_render_missing_as_duplicates_toggle`.
    prefix : str, default=""
        Prefix for the filter's widget keys and saved settings; ``""`` for
        the survey data.

    Returns
    -------
    dict
        Dictionary containing condition configuration with keys:
        - condition_col: Column to filter on
        - condition_type: Type of condition
        - condition_value: Value(s) for comparison
        - missing_as_duplicates: Whether to include nulls
        Empty when no condition column is chosen.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME)

    st.caption("Only records matching this condition will be checked for duplicates.")

    co1, co2, co3 = st.columns([0.3, 0.3, 0.4])
    all_columns = data.columns
    with co1:
        saved_condition_col = saved_settings.get(f"{prefix}condition_col")
        condition_col = st.selectbox(
            label="Condition Column",
            options=all_columns,
            index=(
                all_columns.index(saved_condition_col)
                if saved_condition_col in all_columns
                else None
            ),
            key=f"duplicates_{prefix}condition_col_key",
            help=(
                "Column used to decide which records are included, e.g. a "
                "consent or interview-status column."
            ),
            on_change=trigger_save,
            kwargs={"state_name": f"{TAB_NAME}_{prefix}condition_col"},
        )

        save_check_settings(
            settings_file, TAB_NAME, {f"{prefix}condition_col": condition_col}
        )

    if not condition_col:
        st.caption("No filter applied — all records will be checked for duplicates.")
        return {}

    with co2:
        NUMERIC_DTYPES = pl.NUMERIC_DTYPES | pl.DATETIME_DTYPES
        col_is_numeric = data[condition_col].dtype in NUMERIC_DTYPES
        condition_type = NumCondition if col_is_numeric else StrCondition
        condition_type_options = [e.value for e in condition_type]

        default_condition_type = saved_settings.get(f"{prefix}condition_type", None)
        default_condition_type_index = (
            condition_type_options.index(default_condition_type)
            if default_condition_type
            and default_condition_type in condition_type_options
            else 0
        )
        condition_type = st.selectbox(
            label="Condition Type",
            index=default_condition_type_index,
            options=condition_type_options,
            key=f"duplicates_{prefix}condition_type_key",
            help=(
                "How to compare the column's values against your condition "
                "value (equals, contains, greater than, etc.)."
            ),
            on_change=trigger_save,
            kwargs={"state_name": f"{TAB_NAME}_{prefix}condition_type"},
        )
        save_check_settings(
            settings_file, TAB_NAME, {f"{prefix}condition_type": condition_type}
        )

    condition_values = data.select(pl.col(condition_col).unique()).to_series().to_list()

    with co3:
        condition_value, condition_value_dict = _render_condition_value_input(
            data,
            condition_col,
            condition_type,
            saved_settings,
            condition_values,
            prefix,
        )

        if not condition_value_dict:
            condition_value_dict = {
                f"{prefix}condition_value": _serialize_condition_value_for_json(
                    condition_value
                )
            }
        save_check_settings(settings_file, TAB_NAME, condition_value_dict)

    conditions = {
        "condition_col": condition_col,
        "condition_type": condition_type,
        "condition_value": condition_value,
        "missing_as_duplicates": missing_as_duplicates,
    }
    if not has_active_filter(conditions):
        st.caption("Choose a condition value to apply the filter.")
    return conditions


# =============================================================================
# Data Filtering Helper Functions
# =============================================================================


def _validate_duplicates_condition_date_value(
    value: str | list[str] | None,
    default_value: datetime.date | tuple[datetime.date, datetime.date],
) -> datetime.date | tuple[datetime.date, datetime.date]:
    """Validate and convert date values from saved settings.

    Converts date strings from saved settings to datetime.date objects.
    Handles both single dates and date ranges.

    Parameters
    ----------
    value : str | list[str] | None
        The input date value(s) to validate (ISO format strings).
    default_value : datetime.date | tuple[datetime.date, datetime.date]
        The default date value(s) to use if input is invalid.

    Returns
    -------
    datetime.date | tuple[datetime.date, datetime.date]
        Validated date value(s) or default if validation fails.
    """
    if not value:
        return default_value

    try:
        if isinstance(value, list) and len(value) == 2:
            start_date = datetime.date.fromisoformat(value[0])
            end_date = datetime.date.fromisoformat(value[1])
            return (start_date, end_date)
        else:
            return datetime.date.fromisoformat(value)
    except Exception:
        return default_value


def _serialize_condition_value_for_json(
    value: datetime.date | tuple | list | int | float | str,
) -> str | list | int | float:
    """Convert date values to JSON-serializable strings.

    Parameters
    ----------
    value : datetime.date | tuple | list | int | float | str
        The value to serialize.

    Returns
    -------
    str | list | int | float
        JSON-serializable value.
    """
    if isinstance(value, datetime.date) and not isinstance(value, datetime.datetime):
        return str(value)
    elif isinstance(value, tuple | list):
        return [_serialize_condition_value_for_json(v) for v in value]
    else:
        return value


def _is_date_not_datetime(value) -> bool:
    """Check if a value is a date but not a datetime."""
    return isinstance(value, datetime.date) and not isinstance(value, datetime.datetime)


def _has_date_values(values: list | tuple) -> bool:
    """Check if any element in a list/tuple is a date (not datetime)."""
    return any(_is_date_not_datetime(v) for v in values)


def _cast_col_for_date_comparison(
    col: pl.Expr,
    condition_type: str,
    value: int | float | list | tuple | datetime.date,
) -> pl.Expr:
    """Cast column to Date if the value contains date objects.

    Parameters
    ----------
    col : pl.Expr
        Polars column expression.
    condition_type : str
        Type of numeric condition from NumCondition enum.
    value : int | float | list | tuple | datetime.date
        Value(s) to compare against.

    Returns
    -------
    pl.Expr
        Column expression, cast to Date if needed.
    """
    if _is_date_not_datetime(value):
        return col.cast(pl.Date)

    if not isinstance(value, list | tuple):
        return col

    needs_cast = condition_type == NumCondition.INCLUDES.value or (
        condition_type == NumCondition.IN_RANGE.value and len(value) == 2
    )
    if needs_cast and _has_date_values(value):
        return col.cast(pl.Date)

    return col


def _apply_numeric_condition(
    col: pl.Expr,
    condition_type: str,
    value: int | float | list | tuple | datetime.date,
) -> pl.Expr:
    """Apply numeric condition to a Polars column expression.

    Supports various numeric comparison operators including equality,
    inequality, ranges, and membership tests. Handles datetime columns
    by casting to date when comparing with date values.

    Parameters
    ----------
    col : pl.Expr
        Polars column expression to filter.
    condition_type : str
        Type of numeric condition from NumCondition enum.
    value : int | float | list | tuple | datetime.date
        Value(s) to compare against.

    Returns
    -------
    pl.Expr
        Filtered column expression.

    Notes
    -----
    When comparing a datetime column with a date value, the column is
    automatically cast to date type to ensure all datetime values within
    that date match the condition.
    """
    col = _cast_col_for_date_comparison(col, condition_type, value)

    if value is None:
        if condition_type == NumCondition.EQUALS.value:
            return col.is_null()
        if condition_type == NumCondition.NOT_EQUALS.value:
            return col.is_not_null()

    dispatch = {
        NumCondition.EQUALS.value: lambda c, v: c == v,
        NumCondition.NOT_EQUALS.value: lambda c, v: c != v,
        NumCondition.GREATER_THAN.value: lambda c, v: c > v,
        NumCondition.GREATER_THAN_OR_EQUAL.value: lambda c, v: c >= v,
        NumCondition.LESS_THAN.value: lambda c, v: c < v,
        NumCondition.LESS_THAN_OR_EQUAL.value: lambda c, v: c <= v,
        NumCondition.INCLUDES.value: lambda c, v: c.is_in(v),
        NumCondition.EXCLUDES.value: lambda c, v: ~c.is_in(v),
        NumCondition.IN_RANGE.value: lambda c, v: (c >= v[0]) & (c <= v[1]),
    }

    handler = dispatch.get(condition_type)
    if handler is None:
        raise ValueError(f"Unsupported numeric condition type: {condition_type}")

    return handler(col, value)


def _apply_string_condition(
    col: pl.Expr, condition_type: str, value: str | list
) -> pl.Expr:
    """Apply string condition to a Polars column expression.

    Supports various string operations including equality, containment,
    prefix/suffix matching, and membership tests.

    Parameters
    ----------
    col : pl.Expr
        Polars column expression to filter.
    condition_type : str
        Type of string condition from StrCondition enum.
    value : str | list
        Value(s) to compare against.

    Returns
    -------
    pl.Expr
        Filtered column expression.
    """
    if condition_type == StrCondition.EQUALS.value:
        return col == value
    elif condition_type == StrCondition.NOT_EQUALS.value:
        return col != value
    elif condition_type == StrCondition.STARTWITH.value:
        return col.str.starts_with(value)
    elif condition_type == StrCondition.ENDWITH.value:
        return col.str.ends_with(value)
    elif condition_type == StrCondition.CONTAINS.value:
        return col.str.contains(value)
    elif condition_type == StrCondition.INCLUDES.value:
        return col.is_in(value)
    elif condition_type == StrCondition.EXCLUDES.value:
        return ~col.is_in(value)
    else:
        raise ValueError(f"Unsupported string condition type: {condition_type}")


def _build_filter_expression(
    validated_condition: FilterCondition, col_expr: pl.Expr
) -> pl.Expr:
    """Build the appropriate filter expression based on condition type.

    Constructs a complete filter expression including null value handling
    based on the missing_as_duplicates flag.

    Parameters
    ----------
    validated_condition : FilterCondition
        Validated condition configuration.
    col_expr : pl.Expr
        Column expression to filter.

    Returns
    -------
    pl.Expr
        Complete filter expression including null handling.
    """
    condition_type = validated_condition.condition_type
    condition_value = validated_condition.condition_value

    numeric_conditions = [e.value for e in NumCondition]
    string_conditions = [e.value for e in StrCondition]

    if condition_type in numeric_conditions:
        filter_expr = _apply_numeric_condition(
            col_expr, condition_type, condition_value
        )
    elif condition_type in string_conditions:
        filter_expr = _apply_string_condition(col_expr, condition_type, condition_value)
    else:
        raise ValueError(f"Unknown condition type: {condition_type}")

    if validated_condition.missing_as_duplicates:
        filter_expr = col_expr.is_null() | filter_expr

    return filter_expr


def _coerce_datetime_value(
    condition_value: str | list,
) -> datetime.date | list:
    """Coerce string condition value(s) to date objects.

    Parameters
    ----------
    condition_value : str | list
        Raw condition value to coerce.

    Returns
    -------
    datetime.date | list
        Coerced value(s); non-string values are returned unchanged.

    Raises
    ------
    ValueError
        If a string value is not an ISO-format date.
    """
    try:
        if isinstance(condition_value, str):
            return datetime.date.fromisoformat(condition_value)
        if isinstance(condition_value, list):
            return [
                datetime.date.fromisoformat(v) if isinstance(v, str) else v
                for v in condition_value
            ]
    except (ValueError, TypeError) as e:
        raise ValueError(f"Cannot convert filter value to date: {e}") from e
    return condition_value


def _coerce_numeric_value(
    condition_value: str | list,
    col_dtype: pl.DataType,
) -> int | float | list:
    """Coerce string condition value(s) to numeric types.

    Parameters
    ----------
    condition_value : str | list
        Raw condition value to coerce.
    col_dtype : pl.DataType
        The Polars data type of the target column.

    Returns
    -------
    int | float | list
        Coerced value(s); non-string values are returned unchanged.

    Raises
    ------
    ValueError
        If a string value cannot be converted to the column's numeric type.
    """
    cast_fn = int if col_dtype in pl.INTEGER_DTYPES else float

    try:
        if isinstance(condition_value, str):
            return cast_fn(condition_value)
        if isinstance(condition_value, list):
            return [cast_fn(v) if isinstance(v, str) else v for v in condition_value]
    except (ValueError, TypeError) as e:
        raise ValueError(f"Cannot convert filter value to numeric: {e}") from e
    return condition_value


def _coerce_condition_value(conditions: dict, data: pl.DataFrame) -> None:
    """Coerce the condition value to match the column's dtype in-place.

    Parameters
    ----------
    conditions : dict
        Conditions dict (mutated in-place).
    data : pl.DataFrame
        Dataset used to determine column dtype.
    """
    condition_col = conditions["condition_col"]
    condition_value = conditions.get("condition_value")
    if not condition_value or condition_col not in data.columns:
        return

    col_dtype = data[condition_col].dtype

    if col_dtype in pl.DATETIME_DTYPES:
        conditions["condition_value"] = _coerce_datetime_value(condition_value)
    elif col_dtype in pl.NUMERIC_DTYPES:
        conditions["condition_value"] = _coerce_numeric_value(
            condition_value, col_dtype
        )


def _has_valid_filter_conditions(conditions: dict) -> bool:
    """Check whether conditions contain enough info to build a filter."""
    return bool(conditions.get("condition_col") and conditions.get("condition_type"))


def has_active_filter(conditions: dict | None) -> bool:
    """Return whether a Records to Include filter is set and has a value.

    A filter whose value has not been chosen yet (``None``, ``""`` or an empty
    list) is not applied, so every record is checked.
    """
    if not conditions or not _has_valid_filter_conditions(conditions):
        return False
    return conditions.get("condition_value") not in (None, "", [], ())


def apply_records_to_include(
    data: pl.DataFrame, conditions: dict | None
) -> pl.DataFrame:
    """Return the records the Records to Include filter keeps.

    Returns `data` unchanged when no filter is active (see
    `has_active_filter`). A filter that matches no records returns an empty
    DataFrame, so no records are checked. `conditions` is not changed.

    Parameters
    ----------
    data : pl.DataFrame
        The dataset to filter.
    conditions : dict | None
        Conditions for filtering with keys:
        - condition_col: Column name to filter on
        - condition_type: Type of condition (from NumCondition or StrCondition)
        - condition_value: Value(s) to compare against
        - missing_as_duplicates: Whether to include null values

    Raises
    ------
    ValueError
        If conditions are invalid or condition type is not supported.
    """
    if not has_active_filter(conditions):
        return data

    conditions = dict(conditions)
    try:
        _coerce_condition_value(conditions, data)
    except Exception as e:
        raise ValueError(f"Error applying filter: {e}") from e

    try:
        validated_condition = FilterCondition(**conditions)
    except Exception as e:
        raise ValueError(f"Invalid conditions: {e}") from e

    try:
        col_expr = pl.col(validated_condition.condition_col)
        filter_expr = _build_filter_expression(validated_condition, col_expr)
        return data.filter(filter_expr)
    except Exception as e:
        raise ValueError(f"Error applying filter: {e}") from e


# =============================================================================
# Duplicates Column Configuration Management
# =============================================================================


def _update_duplicates_column_config(
    project_id: str,
    page_name_id: str,
    search_type: str,
    pattern: str | None,
    dup_cols: list[str],
    lock_cols: bool,
) -> None:
    """Update the duplicates column configuration in the database.

    Appends new configuration to existing settings or creates new
    configuration if none exists.

    Parameters
    ----------
    project_id : str
        Project identifier for database operations.
    page_name_id : str
        Page name identifier for storing configurations.
    search_type : str
        Search type used for column matching.
    pattern : str | None
        Pattern for column matching (None for exact search).
    dup_cols : list[str]
        Selected columns to check for duplicates.
    lock_cols : bool
        Whether to lock column selection.
    """
    existing_config = duckdb_get_table(
        project_id=project_id,
        alias=f"duplicates_{page_name_id}",
        db_name="logs",
    )

    new_config = {
        "search_type": search_type,
        "pattern": pattern,
        "column_name": [dup_cols],
        "locked": lock_cols,
    }

    schema = {
        "search_type": pl.Utf8,
        "pattern": pl.Utf8,
        "column_name": pl.List(pl.Utf8),
        "locked": pl.Boolean,
    }

    new_config_df = pl.DataFrame(new_config, schema=schema)
    if not existing_config.is_empty():
        formatted_existing_config = _ensure_duplicates_column_formats(existing_config)
        updated_config = pl.concat(
            [formatted_existing_config, new_config_df], how="vertical"
        )
    else:
        updated_config = new_config_df

    duckdb_save_table(
        project_id,
        updated_config,
        f"duplicates_{page_name_id}",
        db_name="logs",
    )


def _ensure_duplicates_column_formats(
    duplicates_settings: pl.DataFrame,
) -> pl.DataFrame:
    """Ensure correct data types for duplicates settings DataFrame.

    Parameters
    ----------
    duplicates_settings : pl.DataFrame
        Duplicates settings configuration.

    Returns
    -------
    pl.DataFrame
        DataFrame with ensured data types.
    """
    return duplicates_settings.with_columns(
        [
            pl.col("search_type").cast(pl.Utf8),
            pl.col("pattern").cast(pl.Utf8),
            pl.col("column_name").cast(pl.List(pl.Utf8)),
            pl.col("locked").cast(pl.Boolean),
        ]
    )


def _render_duplicates_settings_table(duplicates_settings: pl.DataFrame) -> None:
    """Render the duplicates settings table in Streamlit.

    Displays current duplicate column configurations in an expandable table.

    Parameters
    ----------
    duplicates_settings : pl.DataFrame
        Duplicates settings configuration to display.
    """
    with st.expander("Duplicates Column Settings", expanded=False):
        st.dataframe(
            duplicates_settings,
            width="stretch",
            hide_index=True,
            column_config={
                "search_type": st.column_config.Column("Search Type"),
                "pattern": st.column_config.Column("Pattern"),
                "column_name": st.column_config.Column("Column Name(s)"),
                "locked": st.column_config.CheckboxColumn("Locked"),
            },
        )


def _delete_duplicates_column(
    project_id: str, page_name_id: str, duplicates_settings: pl.DataFrame
) -> None:
    """Render delete duplicates column button and handle deletion.

    Provides a popover UI for selecting and deleting duplicate column
    configurations.

    Parameters
    ----------
    project_id : str
        Project identifier for database operations.
    page_name_id : str
        Page name identifier for storing configurations.
    duplicates_settings : pl.DataFrame
        Current duplicates settings.
    """
    with st.popover(
        label=":material/delete: Delete duplicates column",
        width="stretch",
    ):
        st.markdown("#### Remove duplicates columns")

        if duplicates_settings.is_empty():
            st.info("No duplicates columns have been added yet.")
        else:
            duplicates_settings_indexed = (
                duplicates_settings.with_row_index().with_columns(
                    (
                        pl.col("index").cast(pl.Utf8)
                        + " - "
                        + pl.col("search_type")
                        + " - "
                        + pl.col("pattern").fill_null("")
                    ).alias("composite_index")
                )
            )

            unique_index = (
                duplicates_settings_indexed["composite_index"]
                .unique(maintain_order=True)
                .to_list()
            )

            selected_index = st.selectbox(
                label="Select duplicates column to remove",
                options=unique_index,
                help="Select the duplicates column to remove from the list.",
            )

            if selected_index:
                confirm_delete = st.button(
                    label="Confirm deletion",
                    type="primary",
                    width="stretch",
                )
                if confirm_delete:
                    updated_settings = duplicates_settings_indexed.filter(
                        pl.col("composite_index") != selected_index
                    ).drop("composite_index")

                    duckdb_save_table(
                        project_id,
                        updated_settings,
                        f"duplicates_{page_name_id}",
                        "logs",
                    )

                    st.rerun()


def _update_unlocked_duplicates_cols(
    duplicates_config: pl.DataFrame,
    all_columns: list[str],
) -> pl.DataFrame:
    """Update unlocked columns based on current available columns.

    Re-evaluates pattern matches for unlocked configurations to ensure
    they reflect current column availability.

    Parameters
    ----------
    duplicates_config : pl.DataFrame
        Current duplicates configuration.
    all_columns : list[str]
        List of all available columns in the dataset.

    Returns
    -------
    pl.DataFrame
        Updated duplicates configuration with refreshed column matches.
    """
    if duplicates_config.is_empty():
        return duplicates_config

    updated_rows = []
    for row in duplicates_config.iter_rows(named=True):
        if not row["locked"]:
            search_type = row["search_type"]
            pattern = row["pattern"]

            if pattern and search_type != SearchType.EXACT.value:
                new_cols = expand_col_names(all_columns, pattern, search_type)
                row["column_name"] = new_cols

        updated_rows.append(row)

    return pl.DataFrame(updated_rows)


# =============================================================================
# Other Column Duplicates Display Functions
# =============================================================================


def _render_other_duplicates_metrics(
    data: pl.DataFrame,
    duplicates_settings: DuplicatesSettings,
    dup_cols: list | None = None,
) -> None:
    """Render metrics for other column duplicates.

    Displays summary statistics for duplicate detection across
    configured columns.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset to analyze.
    duplicates_settings : DuplicatesSettings
        Duplicates settings configuration.
    dup_cols : list | None, default=None
        List of columns to check for duplicates.
    """
    if data.is_empty():
        return

    if not dup_cols or len(dup_cols) == 0:
        st.info("No columns configured for duplicate checking.")
        return

    duplicates_stats: DuplicatesStats = compute_duplicates_statistics(
        data, duplicates_settings, dup_cols
    )

    gc1, gc2, gc3, gc4 = st.columns(4)
    with gc1, st.container(border=True):
        st.metric(
            label="Columns Checked",
            value=duplicates_stats.number_of_columns_checked,
            help="Total number of columns checked for duplicates.",
        )

    with gc2, st.container(border=True):
        st.metric(
            label="Total Duplicates",
            value=duplicates_stats.total_duplicates,
            help="Total number of duplicate entries found across all checked columns.",
        )

    with gc3, st.container(border=True):
        st.metric(
            label="Columns with Duplicates",
            value=duplicates_stats.number_of_cols_with_duplicates,
            help="Number of columns that have at least one duplicate entry.",
        )

    with gc4, st.container(border=True):
        st.metric(
            label="Columns without Duplicates",
            value=duplicates_stats.number_of_cols_without_duplicates,
            help="Number of columns that have no duplicate entries.",
        )


def _render_other_duplicates_table(
    data: pl.DataFrame,
    dup_cols: list,
    duplicates_settings: DuplicatesSettings,
    settings_file: str,
) -> None:
    """Display other column duplicates table with configurable columns.

    Shows detailed duplicate analysis for selected non-ID columns with
    options to include additional context columns.

    Parameters
    ----------
    data : pl.DataFrame
        The full dataset.
    dup_cols : list
        The columns being checked for duplicates.
    duplicates_settings : DuplicatesSettings
        Duplicates settings configuration.
    settings_file : str
        Path to the settings file.
    """
    cc1, _ = st.columns([0.3, 0.7])
    with cc1:
        col_checked = st.selectbox(
            label="Select column to check for duplicates",
            options=dup_cols,
            key="other_dup_col_selectbox",
        )

    col_dups_data = compute_column_duplicates(
        data=data,
        survey_id=duplicates_settings.survey_id,
        survey_date=duplicates_settings.survey_date,
        dup_col=col_checked,
    )

    with st.expander(":material/clarify: Show more columns in report", expanded=False):
        saved_settings = load_check_settings(settings_file, TAB_NAME)
        default_var_table_display_cols = saved_settings.get(
            f"{col_checked}_display_cols", []
        )
        display_options = [
            col
            for col in data.columns
            if col
            not in [
                duplicates_settings.survey_id,
                duplicates_settings.survey_key,
                duplicates_settings.survey_date,
                col_checked,
            ]
        ]
        var_table_display_cols = st.multiselect(
            label="Select additional columns to display",
            options=display_options,
            help="Select additional columns to include in the duplicates report.",
            default=default_var_table_display_cols,
            key="other_duplicates_table_display_cols_key",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + f"_{col_checked}_display_cols"},
        )

        save_check_settings(
            settings_file,
            TAB_NAME,
            {f"{col_checked}_display_cols": var_table_display_cols},
        )

        if var_table_display_cols:
            join_keys = []
            if (
                duplicates_settings.survey_id
                and duplicates_settings.survey_id in data.columns
                and duplicates_settings.survey_id in col_dups_data.columns
            ):
                join_keys.append(duplicates_settings.survey_id)
            if (
                duplicates_settings.survey_key
                and duplicates_settings.survey_key in data.columns
                and duplicates_settings.survey_key in col_dups_data.columns
            ):
                join_keys.append(duplicates_settings.survey_key)

            if join_keys:
                select_cols = join_keys + [
                    col for col in var_table_display_cols if col in data.columns
                ]

                col_dups_data = col_dups_data.join(
                    data.select(select_cols),
                    on=join_keys,
                    how="left",
                ).unique()
            else:
                st.warning(
                    "Cannot join additional columns: required join keys not found in data."
                )

    if col_dups_data.is_empty():
        st.info(f"No duplicates found for the column '{col_checked}'.")
        return

    st.dataframe(
        col_dups_data,
        width="stretch",
        hide_index=True,
        column_config={
            f"{col_checked}_dup_count": st.column_config.Column(
                label=f"# of {col_checked} duplicates"
            ),
            f"{col_checked}_dup_percent": st.column_config.NumberColumn(
                label="% of total records", format="%.2f%%"
            ),
        },
    )


# =============================================================================
# Duplicates Computation Functions
# =============================================================================


@st.cache_data(ttl=300)
def compute_duplicates_statistics(
    data: pl.DataFrame,
    duplicates_settings: DuplicatesSettings,
    dup_cols: list,
) -> DuplicatesStats:
    """Compute comprehensive statistics for duplicate detection.

    Analyzes specified columns for duplicates and returns summary statistics
    including counts of columns with/without duplicates and total duplicate entries.

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        The dataset to compute statistics for.
    duplicates_settings : DuplicatesSettings
        Duplicates settings configuration containing survey identifiers.
    dup_cols : list
        The columns to check for duplicates.

    Returns
    -------
    DuplicatesStats
        Statistics about duplicates including counts and percentages.

    Raises
    ------
    ValueError
        If neither survey_id nor survey_key is provided in settings.
    """
    survey_id = duplicates_settings.survey_id
    survey_key = duplicates_settings.survey_key

    if not survey_id and not survey_key:
        raise ValueError("Either survey_id or survey_key must be provided.")

    if not dup_cols:
        return DuplicatesStats(
            number_of_columns_checked=0,
            total_duplicates=0,
            number_of_cols_with_duplicates=0,
            number_of_cols_without_duplicates=0,
        )

    number_of_cols_with_duplicates = 0
    number_of_cols_without_duplicates = 0

    dup_cols_checked = [col for col in dup_cols if col not in [survey_id, survey_key]]
    number_of_cols_checked = len(dup_cols_checked)

    if number_of_cols_checked == 0:
        return DuplicatesStats(
            number_of_columns_checked=0,
            total_duplicates=0,
            number_of_cols_with_duplicates=0,
            number_of_cols_without_duplicates=0,
        )

    total_duplicates = 0
    for dup_col in dup_cols_checked:
        col_dups_data = data.filter(pl.col(dup_col).is_duplicated())
        total_duplicates += col_dups_data.height
        if col_dups_data.height > 0:
            number_of_cols_with_duplicates += 1
        else:
            number_of_cols_without_duplicates += 1

    return DuplicatesStats(
        number_of_columns_checked=int(number_of_cols_checked),
        total_duplicates=int(total_duplicates),
        number_of_cols_with_duplicates=int(number_of_cols_with_duplicates),
        number_of_cols_without_duplicates=int(number_of_cols_without_duplicates),
    )


@st.cache_data(ttl=300)
def compute_id_duplicates(
    data: pl.DataFrame,
    survey_id: str,
    survey_date: str | None,
    survey_key: str,
) -> pl.DataFrame:
    """Compute duplicates for the survey ID column.

    Identifies duplicate survey IDs and calculates statistics including
    duplicate counts and percentages.

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        The dataset to compute duplicates for.
    survey_id : str
        The survey ID column name.
    survey_date : str | None
        The survey date column name (optional).
    survey_key : str
        The survey key column name.

    Returns
    -------
    pl.DataFrame
        DataFrame containing duplicate entries with columns:
        - survey_id: Survey ID values
        - survey_key: Survey key values
        - survey_date: Survey date values (if provided)
        - id_dup_count: Number of times each ID appears
        - id_dup_percent: Percentage of total records
    """
    id_dups_data = data.filter(pl.col(survey_id).is_duplicated())

    id_dups_data = id_dups_data.with_columns(
        [pl.col(survey_id).count().over(survey_id).alias("id_dup_count")]
    )

    total_records = data.height
    id_dups_data = id_dups_data.with_columns(
        [(pl.col("id_dup_count") / total_records * 100).alias("id_dup_percent")]
    )

    context_cols = [
        col
        for col in (survey_key, survey_date)
        if col and col in data.columns and col != survey_id
    ]
    id_dups_data = id_dups_data.select(
        [survey_id, *context_cols, "id_dup_count", "id_dup_percent"]
    )

    return id_dups_data.sort([survey_id, "id_dup_count"], descending=[True, False])


@st.cache_data(ttl=300)
def compute_column_duplicates(
    data: pl.DataFrame,
    survey_id: str,
    survey_date: str,
    dup_col: str,
) -> pl.DataFrame:
    """Compute duplicates for a specific column.

    Identifies duplicate values in the specified column and calculates
    statistics including duplicate counts and percentages.

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        The dataset to compute duplicates for.
    survey_id : str
        The survey ID column name for context.
    survey_date : str
        The survey date column name for context.
    dup_col : str
        The column to check for duplicates.

    Returns
    -------
    pl.DataFrame
        DataFrame containing duplicate entries with columns:
        - survey_id: Survey ID (if exists in data)
        - survey_date: Survey date (if exists in data)
        - dup_col: The duplicate column values
        - {dup_col}_dup_count: Count of duplicates
        - {dup_col}_dup_percent: Percentage of total records
    """
    var_dups_data = data.filter(pl.col(dup_col).is_duplicated())

    var_dups_data = var_dups_data.with_columns(
        [pl.col(dup_col).count().over(dup_col).alias(f"{dup_col}_dup_count")]
    )

    total_records = data.height
    var_dups_data = var_dups_data.with_columns(
        [
            (pl.col(f"{dup_col}_dup_count") / total_records * 100).alias(
                f"{dup_col}_dup_percent"
            )
        ]
    )

    base_cols = [dup_col, f"{dup_col}_dup_count", f"{dup_col}_dup_percent"]

    existing_vars = []
    if survey_id and survey_id in data.columns:
        existing_vars.append(survey_id)
    if survey_date and survey_date in data.columns:
        existing_vars.append(survey_date)

    cols_to_select = existing_vars + base_cols

    var_dups_data = var_dups_data.select(cols_to_select)

    return var_dups_data.sort(
        [f"{dup_col}_dup_count", dup_col], descending=[True, False]
    )


# =============================================================================
# ID Duplicates Views
# =============================================================================


@dataclass(frozen=True)
class _FilteredRecords:
    """The records a Records to Include filter keeps, and any problem with it.

    Attributes
    ----------
    data : pl.DataFrame
        The records to check. Empty when the filter is invalid.
    label : str
        ``"survey"`` or ``"backcheck"``, for messages.
    error : str | None
        Why the filter could not be applied, if it could not.
    matches_nothing : bool
        Whether an active filter matches no records.
    """

    data: pl.DataFrame
    label: str
    error: str | None = None
    matches_nothing: bool = False


def _records_to_include(
    data: pl.DataFrame, conditions: dict, label: str
) -> _FilteredRecords:
    """Apply a Records to Include filter without showing anything.

    An invalid filter, like a filter that matches nothing, leaves no records
    to check. Show its problems with `_render_filter_messages`.
    """
    try:
        filtered = apply_records_to_include(data, conditions)
    except ValueError as e:
        logger.warning("Records to Include filter for %s data failed: %s", label, e)
        return _FilteredRecords(data.clear(), label, error=str(e))

    return _FilteredRecords(
        filtered,
        label,
        matches_nothing=has_active_filter(conditions) and filtered.is_empty(),
    )


def _render_filter_messages(records: _FilteredRecords) -> None:
    """Show an error for an invalid filter or a warning for an empty one."""
    label = records.label
    if records.error:
        st.error(
            f"The {label} Records to Include filter could not be applied: "
            f"{records.error}"
        )
    elif records.matches_nothing:
        st.warning(
            f"The {label} Records to Include filter matches no records, so no "
            f"{label} records are checked. Change the filter in "
            ":material/settings: settings.",
            icon=":material/filter_alt_off:",
        )


def _backcheck_view(
    backcheck_data: pl.DataFrame,
    survey_data: pl.DataFrame,
    duplicates_settings: DuplicatesSettings,
    config: dict,
    setting_file: str,
) -> tuple[IdView, _FilteredRecords]:
    """Build the backcheck view from the page's backcheck settings.

    The ID and KEY columns are the ones set on the Backcheck Analysis tab,
    falling back to the survey's. Unmatched IDs are matched against every
    survey record, not only the survey's Records to Include. Also returns the
    filtered backcheck records, for their filter messages.
    """
    saved = load_check_settings(setting_file, BACKCHECKS_TAB_NAME)
    records = _records_to_include(
        backcheck_data, duplicates_settings.backcheck_conditions, "backcheck"
    )
    view = IdView(
        name="backcheck",
        data=records.data,
        id_col=saved.get("survey_id") or duplicates_settings.survey_id,
        key_col=saved.get("survey_key") or duplicates_settings.survey_key,
        date_col=saved.get("backcheck_date") or config.get("backcheck_date"),
        staff_col=saved.get("backchecker") or config.get("backchecker"),
        team_col=config.get("backchecker_team"),
        display_cols_setting="backcheck_id_table_display_cols",
        survey_data=survey_data,
    )
    return view, records


# =============================================================================
# Main Duplicates Report Function
# =============================================================================


def duplicates_report(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
    survey_columns: ColumnByType,
    backcheck_data: pl.DataFrame | None = None,
) -> None:
    """Generate a comprehensive duplicates report.

    Creates a complete duplicates analysis report including:
    - ID duplicate detection and statistics
    - Column-level duplicate analysis
    - Configurable filtering and column selection
    - Interactive tables and metrics

    Parameters
    ----------
    project_id : str
        Unique project identifier for database operations.
    page_name_id : str
        Page name identifier for storing configurations.
    data : pl.DataFrame
        The dataset to analyze for duplicates.
    setting_file : str
        Path to settings file for persisting configurations.
    config : dict
        Configuration dictionary for duplicates settings. The backcheck keys
        ``backcheck_data_name``, ``backcheck_date``, ``backchecker`` and
        ``backchecker_team`` set up the backcheck view.
    survey_columns : ColumnByType
        The survey data's columns by type.
    backcheck_data : pl.DataFrame | None, default=None
        The page's backcheck data, if any.
    """
    categorical_columns = survey_columns.categorical_columns
    datetime_columns = survey_columns.datetime_columns

    st.title("Duplicates Report")

    if is_demo_project():
        demo_callout(
            "This tab identifies duplicate records in your survey data. It has two sections:\n\n"
            "- **ID Duplicates**: Records sharing the same Survey ID (e.g., two submissions "
            "with the same household ID).\n"
            "- **Other Duplicates**: Duplicates in any additional columns you configure.\n\n"
            "Start by reviewing the :material/settings: **settings** panel — your columns are "
            "pre-filled from your check configuration."
        )

    config_settings = DuplicatesSettings(**config)
    duplicates_settings = duplicates_report_settings(
        project_id,
        setting_file,
        data,
        config_settings,
        categorical_columns,
        datetime_columns,
        backcheck_data,
    )

    # ---- ID Duplicates --- #
    st.divider()
    st.title("ID Duplicates")

    if is_demo_project():
        demo_callout(
            "This section shows one card for each **hhid** (household ID) shared "
            "by more than one survey record. Each card compares the records side "
            "by side and highlights the fields that differ. "
            "Use **Compare all fields** on a card to see every column, and "
            "expand **:material/clarify: Show more columns in report** to add "
            "context columns such as **enum_name** or **state** to every card."
        )

    # Build both views first: the switcher shows each one's duplicate count.
    survey_records = _records_to_include(data, duplicates_settings.conditions, "survey")
    survey_view = IdView(
        name="survey",
        data=survey_records.data,
        id_col=duplicates_settings.survey_id,
        key_col=duplicates_settings.survey_key,
        date_col=duplicates_settings.survey_date,
        staff_col=duplicates_settings.enumerator,
        team_col=duplicates_settings.team,
        display_cols_setting="id_table_display_cols",
    )
    backcheck = None
    if config.get("backcheck_data_name") and backcheck_data is not None:
        backcheck = _backcheck_view(
            backcheck_data, data, duplicates_settings, config, setting_file
        )

    dataset = render_dataset_switcher(
        count_duplicate_ids(survey_view),
        None if backcheck is None else count_duplicate_ids(backcheck[0]),
    )
    if dataset == BACKCHECK_DATA and backcheck is not None:
        backcheck_view, backcheck_records = backcheck
        _render_filter_messages(backcheck_records)
        render_id_duplicates(backcheck_view, setting_file)
        return

    _render_filter_messages(survey_records)
    data = survey_records.data
    if not duplicates_settings.survey_id:
        st.info("Survey ID column is not configured for duplicates check.")
    else:
        render_id_duplicates(survey_view, setting_file)

    # Duplicates column configuration
    st.divider()
    st.title("Other Duplicates")

    if is_demo_project():
        demo_callout(
            "Use **Add Duplicates Column(s)** to check any column for duplicate values — "
            "for example, a phone number or unique ID number. "
            "The demo dataset has no additional columns that should be duplicate-free beyond "
            "the household ID, so you can skip adding columns here."
        )

    all_columns = data.columns
    # if survey id exist, remove it + key from the list of columns to check
    # for duplicates, else only remove the key if exist. This is to
    # avoid confusion as the survey id
    if duplicates_settings.survey_id and duplicates_settings.survey_id in all_columns:
        all_columns = [
            col
            for col in all_columns
            if col != duplicates_settings.survey_id
            and col != duplicates_settings.survey_key
        ]
    elif duplicates_settings.survey_key in all_columns:
        all_columns = [
            col for col in all_columns if col != duplicates_settings.survey_key
        ]
    _render_duplicates_column_actions(project_id, page_name_id, all_columns)

    duplicates_column_config = duckdb_get_table(
        project_id,
        f"duplicates_{page_name_id}",
        "logs",
    )

    if duplicates_column_config.is_empty():
        return

    duplicates_column_config = _update_unlocked_duplicates_cols(
        duplicates_column_config,
        all_columns,
    )

    duckdb_save_table(
        project_id,
        duplicates_column_config,
        f"duplicates_{page_name_id}",
        db_name="logs",
    )

    all_dup_cols = []
    for row in duplicates_column_config.iter_rows(named=True):
        all_dup_cols.extend(row["column_name"])

    all_dup_cols = list(set(all_dup_cols))

    _render_other_duplicates_metrics(
        data,
        config_settings,
        all_dup_cols,
    )

    _render_other_duplicates_table(
        data, all_dup_cols, duplicates_settings, setting_file
    )

    demo_callout(
        "**Next**: :material/arrow_upward: Scroll up and select the **Outliers & Constraints** tab."
    )
