"""Duplicates detection module for survey data quality checks.

This module provides comprehensive duplicate detection functionality with:
- Survey ID duplicate detection
- Column-level duplicate analysis
- Duplicate statistics and reporting
- Configurable duplicate checking
- Modular, testable architecture
"""

import datetime
import os
import re
from enum import Enum

import polars as pl
import streamlit as st
from pydantic import BaseModel, Field, field_validator

from datasure.utils import (
    get_df_info,
    load_check_settings,
    save_check_settings,
    trigger_save,
)
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.onboarding_utils import demo_output_onboarding

TAB_NAME = "duplicates"


# =============================================================================
# Enums and Constants
# =============================================================================


class SearchType(str, Enum):
    """Column search pattern types."""

    EXACT = "exact"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"
    CONTAINS = "contains"
    REGEX = "regex"


class NumCondition(str, Enum):
    """Condition types for duplicates checks for numeric columns."""

    EQUALS = "Value is equal"
    NOT_EQUALS = "Value is not equal"
    GREATER_THAN = "Value is greater than"
    GREATER_THAN_OR_EQUAL = "Value is greater than or equal to"
    LESS_THAN = "Value is less than"
    LESS_THAN_OR_EQUAL = "Value is less than or equal to"
    INCLUDES = "Values includes"
    EXCLUDES = "Value does not include"
    IN_RANGE = "Value is in range"

class StrCondition(str, Enum):
    """Condition types for duplicates checks for string columns."""

    EQUALS = "Value is equal"
    NOT_EQUALS = "Value is not equal"
    STARTWITH = "Value starts with"
    ENDWITH = "Value ends with"
    CONTAINS = "Value contains"
    INCLUDES = "Values includes"
    EXCLUDES = "Value does not include"

# =============================================================================
# Pydantic Models for Data Validation
# =============================================================================


class DuplicatesColumnConfig(BaseModel):
    """Configuration for a single duplicates column check."""

    search_type: SearchType
    pattern: str | None = None
    dup_cols: list[str] = Field(min_length=1)
    lock_cols: bool = False

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str | None, info) -> str | None:
        """Validate pattern is required for non-exact search types."""
        if info.data.get("search_type") != SearchType.EXACT and not v:
            raise ValueError("Pattern is required for non-exact search types")
        return v


class FilterCondition(BaseModel):
    """Validation model for filter conditions."""

    condition_col: str = Field(..., min_length=1, description="Column to apply condition on")
    condition_type: str = Field(..., description="Type of condition to apply")
    condition_value: int | float | str | list | tuple | datetime.date | None = Field(
        ..., description="Value(s) to compare against"
    )
    missing_as_duplicates: bool = Field(
        default=False, description="Whether to treat missing values as duplicates"
    )

    @field_validator("condition_value")
    @classmethod
    def validate_condition_value(cls, v, info):
        """Validate condition value based on condition type."""
        condition_type = info.data.get("condition_type")

        if condition_type in [NumCondition.IN_RANGE.value] and (
            not isinstance(v, list | tuple) or len(v) != 2
        ):
            raise ValueError(
                f"Condition type '{condition_type}' requires a tuple/list of 2 values"
            )

        if condition_type in [
            NumCondition.INCLUDES.value,
            StrCondition.INCLUDES.value,
        ] and not isinstance(v, list | tuple | set):
            raise ValueError(
                f"Condition type '{condition_type}' requires a list/tuple/set of values"
            )

        return v


class DuplicatesSettings(BaseModel):
    """Settings for progress report configuration."""

    filtered_data: pl.DataFrame | None = None
    survey_key: str = Field(None, description="Survey key column")
    survey_id: str | None = Field(..., min_length=1, description="Survey ID column")
    survey_date: str | None = Field(None, description="Survey date column")
    enumerator: str | None = Field(None, description="Enumerator ID column")
    conditions: dict = Field(default_factory=dict, description="Conditions for duplicates checks")

    # set arbitrary types allowed for polars DataFrame
    model_config = {
        "arbitrary_types_allowed": True,
    }

class DateDefaults(BaseModel):
        """Default date range model."""

        start_date: datetime.date = Field(
            default=datetime.date(1970, 1, 1),
            description="Default start date (January 1, 1970)",
        )
        end_date: datetime.date = Field(
            default=datetime.date(2100, 12, 31),
            description="Default end date (December 31, 2100)",
        )

        default_start_date: datetime.date = Field(
            default=datetime.date.today() - datetime.timedelta(days=30),
            description="Default start date for date input (30 days ago)",
        )
        default_end_date: datetime.date = Field(
            default=datetime.date.today() + datetime.timedelta(days=30),
            description="Default end date for date input (today)",
        )

# =============================================================================
# Settings Load and Save Functions
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
        Path to the settings file containing saved progress configurations.
    config : ProgressSettings
        Default configuration to use as fallback for missing settings.

    Returns
    -------
    DuplicatesSettings
        Merged settings combining saved and default configurations.
    """
    # Load saved settings
    saved_settings = load_check_settings(settings_file, TAB_NAME)

    default_settings: dict = dict(config)
    default_settings.update(saved_settings)

    # Merge with defaults
    return DuplicatesSettings(**default_settings)


def duplicates_report_settings(
    settings_file: str,
    data: pl.DataFrame,
    config: DuplicatesSettings,
    categorical_columns: list[str],
    datetime_columns: list[str],
) -> DuplicatesSettings:
    """Create and render the settings UI for progress report configuration.

    This function creates a comprehensive Streamlit UI for configuring
    progress report settings. It includes:
    - Survey identifiers (key and ID columns)
    - Survey date column selection
    - Enumerator ID column

    Settings are automatically saved to the settings file when changed
    and loaded from previous sessions if available.

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading configurations.
    config : ProgressSettings
        Default configuration used as fallback values.
    categorical_columns : list[str]
        Available categorical columns for selection (survey key, ID, enumerator).
    datetime_columns : list[str]
        Available datetime columns for date selection.

    Returns
    -------
    DuplicatesSettings
        User-configured settings from the UI.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for duplicates report")
        st.write("---")

        # Load default settings
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
            st.subheader("Duplicates Conditions")
            st.info(
                "Configure filters for duplicates checks. These settings help exclude irrelevant records from the duplicates analysis."
            )

            conditions = _render_duplicates_condition_options(data, settings_file)
            filtered_data = _filter_data_on_conditions(data, conditions)

    return DuplicatesSettings(
        filtered_data=filtered_data,
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        enumerator=enumerator,
        conditions=conditions,
    )


# =============================================================================
# Column Selection and Expansion Functions
# =============================================================================


def expand_col_names(
    all_columns: list[str], pattern: str, search_type: str = SearchType.EXACT.value
) -> list[str]:
    """Expand column names based on search pattern.

    Parameters
    ----------
    all_columns : list[str]
        List of all available columns.
    pattern : str
        Pattern to match against column names.
    search_type : str
        Type of search to perform (exact, startswith, endswith, contains, regex).

    Returns
    -------
    list[str]
        List of matching column names.
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
        The selected search type.
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

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
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
        Project identifier.
    page_name_id : str
        Page name identifier.
    all_columns : list[str]
        List of all columns available for duplicate checking.
    """
    # Render search type selection
    search_type, pattern, dup_cols, lock_cols_initial = (
        _render_search_type_selection(all_columns)
    )

    if dup_cols:
        # Render locking options (no grouping for duplicates)
        lock_cols = _render_column_locking_options(dup_cols, search_type, lock_cols_initial)

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
        List of all columns.

    Returns
    -------
    tuple[str, str | None, list[str], bool | None]
        Search type, pattern, selected columns, and lock_cols flag.
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
    """Render column locking option (no grouping for duplicates).

    Parameters
    ----------
    dup_cols : list[str]
        Selected duplicate columns.
    search_type : str
        Search type used.
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
def _render_duplicates_condition_options(data: pl.DataFrame, settings_file: str) -> dict:
    """Render duplicates condition options

    Allow users to set conditions for duplicates checks.
    """
    # get defaults
    saved_settings = load_check_settings(settings_file, TAB_NAME)

    default_missing_as_duplicates = saved_settings.get("missing_as_duplicates", False)
    missing_as_duplicates = st.toggle(
        label="Consider missing values as duplicates",
        value=default_missing_as_duplicates,
        key="duplicates_missing_as_duplicates",
        help="If enabled, missing values will be treated as duplicates during the check.",
    )

    co1, co2, co3 = st.columns([0.3, 0.3, 0.4])
    all_columns = data.columns
    with co1:
        default_condition_col = saved_settings.get("condition_col", None)
        condition_col = st.selectbox(
            label="Condition Column",
            options=all_columns,
            key="duplicates_condition_col",
            help="Select the column to apply the condition on.",
        )

    if condition_col:

        with co2:
            # check column data type to determine condition types
            NUMERIC_DTYPES = pl.NUMERIC_DTYPES | pl.DATETIME_DTYPES
            col_is_numeric = data[condition_col].dtype in NUMERIC_DTYPES
            ConditionType = NumCondition if col_is_numeric else StrCondition
            condition_type_options = [e.value for e in ConditionType]

            default_condition_type = saved_settings.get("condition_type", None)
            condition_type = st.selectbox(
                label="Condition Type",
                options=condition_type_options,
                key="duplicates_condition_type",
                help="Select the type of condition to apply.",
            )

        # column values for the selected condition column
        condition_values = (
            data.select(pl.col(condition_col).unique()).to_series().to_list()
        )

        with co3:

            default_condition_value = saved_settings.get("condition_value", None)

            # check if value is a date/time type for proper input
            is_datetime = data[condition_col].dtype in pl.DATETIME_DTYPES
            is_numeric = data[condition_col].dtype in pl.NUMERIC_DTYPES
            if is_datetime:
                min_date = DateDefaults().start_date
                max_date = DateDefaults().end_date

                # create the date input with default range
                date_range = (DateDefaults().default_start_date, DateDefaults().default_end_date) if condition_type in [NumCondition.IN_RANGE.value] else DateDefaults().default_start_date

                  # get default date range from saved settings
                default_condition_value = _validate_duplicates_condition_date_value(
                    default_condition_col, date_range
                )

                condition_value = st.date_input(
                    value=default_condition_value,
                    min_value=min_date,
                    max_value=max_date,
                    label="Condition Value",
                    key="duplicates_condition_date_value",
                    help="Select the date value to filter the condition column.",
                )

            elif is_numeric:

                if not default_condition_value:
                    default_condition_value = (min(condition_values), max(condition_values))

                if condition_type == NumCondition.IN_RANGE.value:
                    condition_value = st.slider(
                        label="Condition Value Range",
                        min_value=min(condition_values),
                        max_value=max(condition_values),
                        value=default_condition_value,
                        key="duplicates_condition_numeric_range_value",
                        help="Select the numeric range to filter the condition column.",
                    )
                elif condition_type in [NumCondition.INCLUDES.value, NumCondition.EXCLUDES.value]:
                    if default_condition_value and not isinstance(default_condition_value, list):
                        default_condition_value = [default_condition_value]
                    condition_value = st.multiselect(
                        label="Condition Values",
                        options=condition_values,
                        key="duplicates_condition_numeric_multivalue",
                        help="Select the numeric values to filter the condition column.",
                    )
                else:
                    if default_condition_value and isinstance(default_condition_value, list):
                        default_condition_value = default_condition_value[0]
                    condition_value = st.number_input(
                        label="Condition Value",
                        value=None,
                        key="duplicates_condition_numeric_value",
                        help="Enter the numeric value to filter the condition column.",
                    )

            else:

                default_condition_value = saved_settings.get("condition_value", [])
                if default_condition_value and not isinstance(default_condition_value, list):
                    default_condition_value = [default_condition_value]


                if condition_type in [StrCondition.INCLUDES.value, StrCondition.EXCLUDES.value]:
                    condition_value = st.multiselect(
                        label="Condition Values",
                        options=default_condition_value,
                        key="duplicates_condition_string_multivalue",
                        help="Select the string values to filter the condition column.",
                    )

                else:
                    condition_value = st.selectbox(
                        label="Condition Value",
                        options=default_condition_value,
                        key="duplicates_condition_value",
                        help="Select the value to filter the condition column.",
                    )

    return {
        "missing_as_duplicates": missing_as_duplicates,
        "condition_type": condition_type if condition_col else None,
        "condition_col": condition_col,
        "condition_value": condition_value if condition_col else {},
    }


# =============================================================================
# Filter Helper Functions
# =============================================================================


def _validate_duplicates_condition_date_value(
    value: datetime.date | list[datetime.date] | None,
    default_value: datetime.date | tuple[datetime.date, datetime.date],
) -> datetime.date | tuple[datetime.date, datetime.date]:
    """Validate and return appropriate date value for condition.

    Parameters
    ----------
    value : datetime.date | list[datetime.date] | None
        The input date value(s) to validate.
    default_value : datetime.date | tuple[datetime.date, datetime.date]
        The default date value(s) to use if input is invalid.

    Returns
    -------
    datetime.date | tuple[datetime.date, datetime.date]
        Validated date value(s).
    """
    if isinstance(value, datetime.date):
        return value
    elif isinstance(value, list) and all(isinstance(d, datetime.date) for d in value):  # noqa: SIM102
        if len(value) == 2:
            return (value[0], value[1])
    return default_value

def _apply_numeric_condition(
    col: pl.Expr, condition_type: str, value: int | float | list | tuple
) -> pl.Expr:
    """Apply numeric condition to a column expression.

    Parameters
    ----------
    col : pl.Expr
        Polars column expression.
    condition_type : str
        Type of numeric condition.
    value : int | float | list | tuple
        Value(s) to compare against.

    Returns
    -------
    pl.Expr
        Filtered column expression.
    """
    if condition_type == NumCondition.EQUALS.value:
        return col == value
    elif condition_type == NumCondition.NOT_EQUALS.value:
        return col != value
    elif condition_type == NumCondition.GREATER_THAN.value:
        return col > value
    elif condition_type == NumCondition.GREATER_THAN_OR_EQUAL.value:
        return col >= value
    elif condition_type == NumCondition.LESS_THAN.value:
        return col < value
    elif condition_type == NumCondition.LESS_THAN_OR_EQUAL.value:
        return col <= value
    elif condition_type == NumCondition.INCLUDES.value:
        return col.is_in(value)
    elif condition_type == NumCondition.EXCLUDES.value:
        return ~col.is_in(value)
    elif condition_type == NumCondition.IN_RANGE.value:
        min_val, max_val = value[0], value[1]
        return (col >= min_val) & (col <= max_val)
    else:
        raise ValueError(f"Unsupported numeric condition type: {condition_type}")


def _apply_string_condition(
    col: pl.Expr, condition_type: str, value: str | list
) -> pl.Expr:
    """Apply string condition to a column expression.

    Parameters
    ----------
    col : pl.Expr
        Polars column expression.
    condition_type : str
        Type of string condition.
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

    # Determine if this is a numeric or string condition
    numeric_conditions = [e.value for e in NumCondition]
    string_conditions = [e.value for e in StrCondition]

    if condition_type in numeric_conditions:
        filter_expr = _apply_numeric_condition(col_expr, condition_type, condition_value)
    elif condition_type in string_conditions:
        filter_expr = _apply_string_condition(col_expr, condition_type, condition_value)
    else:
        raise ValueError(f"Unknown condition type: {condition_type}")

    # Handle missing values based on missing_as_duplicates flag
    if validated_condition.missing_as_duplicates:
        filter_expr = col_expr.is_null() | filter_expr

    return filter_expr


def _filter_data_on_conditions(
    data: pl.DataFrame, conditions: dict
) -> pl.DataFrame:
    """Filter data based on duplicates conditions.

    This function validates the conditions using Pydantic, then applies
    the appropriate filter based on the condition type. Supports both
    numeric and string condition types with comprehensive operators.

    Parameters
    ----------
    data : pl.DataFrame
        The dataset to filter.
    conditions : dict
        Conditions for filtering with keys:
        - condition_col: Column name to filter on
        - condition_type: Type of condition (from NumCondition or StrCondition)
        - condition_value: Value(s) to compare against
        - missing_as_duplicates: Whether to include null values

    Returns
    -------
    pl.DataFrame
        Filtered dataset.

    Raises
    ------
    ValueError
        If conditions are invalid or condition type is not supported.
    """
    if not conditions:
        return data

    # Check if required keys exist
    condition_col = conditions.get("condition_col")
    if not condition_col or not conditions.get("condition_type"):
        return data

    # Validate conditions using Pydantic
    try:
        validated_condition = FilterCondition(**conditions)
    except Exception as e:
        st.error(f"Invalid filter condition: {e}")
        return data

    # Build and apply filter expression
    try:
        col_expr = pl.col(validated_condition.condition_col)
        filter_expr = _build_filter_expression(validated_condition, col_expr)
        return data.filter(filter_expr)
    except Exception as e:
        st.error(f"Error applying filter: {e}")
        return data


def _update_duplicates_column_config(
    project_id: str,
    page_name_id: str,
    search_type: str,
    pattern: str | None,
    dup_cols: list[str],
    lock_cols: bool,
) -> None:
    """Update the duplicates column configuration in the database.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    search_type : str
        Search type used.
    pattern : str | None
        Pattern for column matching.
    dup_cols : list[str]
        Selected columns.
    lock_cols : bool
        Whether to lock column selection.
    """
    # get existing config
    existing_config = duckdb_get_table(
        project_id=project_id,
        alias=f"duplicates_{page_name_id}",
        db_name="logs",
    )

    # Prepare new configurations
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

    # Append new configurations to existing polars DataFrame
    new_config_df = pl.DataFrame(new_config, schema=schema)
    if not existing_config.is_empty():
        formatted_existing_config = _ensure_duplicates_column_formats(existing_config)
        updated_config = pl.concat([formatted_existing_config, new_config_df], how="vertical")
    else:
        updated_config = new_config_df

    # Save updated configurations back to the database
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

    Parameters
    ----------
    duplicates_settings : pl.DataFrame
        Duplicates settings configuration.
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

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    duplicates_settings : pl.DataFrame
        Current duplicates settings.
    """
    with (
        st.popover(
            label=":material/delete: Delete duplicates column",
            width="stretch",
        ),
    ):
        st.markdown("#### Remove duplicates columns")

        if duplicates_settings.is_empty():
            st.info("No duplicates columns have been added yet. ")
        else:
            duplicates_settings_indexed = duplicates_settings.with_row_index().with_columns(
                (
                    pl.col("index").cast(pl.Utf8)
                    + " - "
                    + pl.col("search_type")
                    + " - "
                    + pl.col("pattern").fill_null("")
                ).alias("composite_index")
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

    Parameters
    ----------
    duplicates_config : pl.DataFrame
        Current duplicates configuration.
    all_columns : list[str]
        List of all available columns.

    Returns
    -------
    pl.DataFrame
        Updated duplicates configuration.
    """
    if duplicates_config.is_empty():
        return duplicates_config

    updated_rows = []
    for row in duplicates_config.iter_rows(named=True):
        if not row["locked"]:
            # Re-expand columns based on pattern and search type
            search_type = row["search_type"]
            pattern = row["pattern"]

            if pattern and search_type != SearchType.EXACT.value:
                new_cols = expand_col_names(all_columns, pattern, search_type)
                row["column_name"] = new_cols

        updated_rows.append(row)

    return pl.DataFrame(updated_rows)


# =============================================================================
# Duplicates Statistics and Display Functions
# =============================================================================


@st.cache_data
def compute_duplicates_statistics(
    data: pl.DataFrame, survey_id: str | None, dup_cols: list
) -> tuple:
    """
    Compute statistics for duplicates in the dataset.

    Parameters
    ----------
        data (pl.DataFrame): The dataset to compute duplicates statistics for.
        survey_id (str): The survey ID column name.
        survey_key (str): The survey key column name.
        dup_cols (list): The columns to check for duplicates.

    Returns
    -------
        tuple: A tuple containing the total number of columns checked, the number of
        columns with duplicates, the number of columns without duplicates, total number
            of duplicates
        total number of ID duplicates and total number of duplicates resolved.
        id_duplicates_data (pl.DataFrame): A DataFrame containing the duplicate entries
          for the survey ID.
        all_duplicates_data (pl.DataFrame): A DataFrame containing the duplicate entries
          for the selected columns.
    """
    total_cols_checked = len(dup_cols)
    # Check which columns have duplicates
    cols_with_dups = [
        col for col in dup_cols
        if data.select(pl.col(col)).is_duplicated().any()
    ]
    total_cols_with_dups = len(cols_with_dups)
    total_cols_no_dups = total_cols_checked - total_cols_with_dups

    if survey_id:
        # Find duplicates in survey_id column
        id_dups_data = data.filter(
            pl.col(survey_id).is_duplicated()
        )
        total_id_dups = id_dups_data.height
    else:
        id_dups_data, total_id_dups = pl.DataFrame(), 0

    total_resolved_dups = st.session_state.get("resolved_duplicates", 0)
    total_dups = 0
    for col in dup_cols:
        # Check if column has duplicates
        if data.select(pl.col(col)).is_duplicated().any():
            col_dups_data = data.filter(pl.col(col).is_duplicated())
            total_dups += col_dups_data.height

    return (
        total_cols_checked,
        total_cols_with_dups,
        total_cols_no_dups,
        total_dups,
        total_id_dups,
        total_resolved_dups,
    )


@demo_output_onboarding(TAB_NAME)
def display_duplicates_statistics(
    data: pl.DataFrame, survey_id: str, dup_cols: list
) -> None:
    """
    Display an overview of duplicates statistics in the dataset.

    Parameters
    ----------
        data (pl.DataFrame): The dataset to display duplicates statistics for.
        survey_id (str): The survey ID column name.
        survey_key (str): The survey key column name.
        dup_cols (list): The columns to check for duplicates.

    Returns
    -------
        None
    """
    if not (any([survey_id, dup_cols])):
        st.info(
            "Duplicates statistics requires a survey ID column or at least one column to check for duplicates. Go to :material/settings: settings to select a survey ID column and columns to check for duplicates."
        )
        return
    (
        total_cols_checked,
        total_cols_with_dups,
        total_cols_no_dups,
        total_dups,
        total_id_dups,
        total_resolved_dups,
    ) = compute_duplicates_statistics(data=data, survey_id=survey_id, dup_cols=dup_cols)
    _, gc2 = st.columns(2)
    with gc2:
        tc3, tc4 = st.columns(2, border=True)
        tc3.metric(
            label="Total Duplicates",
            value=total_dups,
            help="Total number of duplicates in the dataset",
        )
        tc4.metric(
            label="Resolved Duplicates",
            value=total_resolved_dups,
            help="Total number of duplicates resolved",
        )

    bc1, bc2, bc3, bc4 = st.columns(4, border=True)
    bc1.metric(
        label="Columns Checked",
        value=total_cols_checked,
        help="Total number of columns checked for duplicates",
    )
    bc2.metric(
        label="Columns With No Duplicates",
        value=total_cols_no_dups,
        help="Total number of columns with no duplicates",
    )
    bc3.metric(
        label="Columns With Duplicates",
        value=total_cols_with_dups,
        help="Total number of columns with duplicates",
    )
    bc4.metric(
        label="Survey ID Duplicates",
        value=total_id_dups,
        help="Total number of duplicates in the survey ID column",
    )


@st.cache_data
def compute_id_duplicates(
    data: pl.DataFrame,
    survey_id: str,
    survey_date: str | None,
    survey_key: str,
    display_cols: list | None,
) -> pl.DataFrame:
    """
    Compute duplicates for the survey ID column.

    Parameters
    ----------
        data (pl.DataFrame): The dataset to compute duplicates for.
        survey_id (str): The survey ID column name.

    Returns
    -------
        pl.DataFrame: A DataFrame containing the duplicate entries for the survey ID.
    """
    # Filter for duplicate survey IDs
    id_dups_data = data.filter(pl.col(survey_id).is_duplicated())

    # Count duplicates per survey_id using over() for window function
    id_dups_data = id_dups_data.with_columns([
        pl.col(survey_id).count().over(survey_id).alias("id_dup_count")
    ])

    # Calculate percentage
    total_records = data.height
    id_dups_data = id_dups_data.with_columns([
        (pl.col("id_dup_count") / total_records * 100).alias("id_dup_percent")
    ])

    # Handle survey_date
    survey_date_list = [] if survey_date is None else [survey_date]

    # Select columns to display
    if display_cols:
        if survey_date_list:
            display_cols = survey_date_list + display_cols

        # Remove any duplicate columns from display_cols
        display_cols = list(set(display_cols))

        # Merge with additional display columns if needed
        if survey_date_list:
            id_dups_data = id_dups_data.select([
                survey_id, survey_key, survey_date, "id_dup_count", "id_dup_percent"
            ] + display_cols)
        else:
            id_dups_data = id_dups_data.select([
                survey_id, survey_key, "id_dup_count", "id_dup_percent"
            ] + display_cols)
    else:
        if survey_date_list:
            id_dups_data = id_dups_data.select([
                survey_id,
                survey_key,
                survey_date,
                "id_dup_count",
                "id_dup_percent",
            ])
        else:
            id_dups_data = id_dups_data.select([
                survey_id, survey_key, "id_dup_count", "id_dup_percent"
            ])

    return id_dups_data.sort([survey_id, "id_dup_count"], descending=[True, False])


@demo_output_onboarding(TAB_NAME)
def display_id_duplicates(
    data: pl.DataFrame,
    survey_id: str | None,
    survey_date: str | None,
    survey_key: str,
    setting_file: str,
) -> None:
    """
    Display duplicates for the survey ID column.

    Parameters
    ----------
        data (pl.DataFrame): The dataset to compute duplicates for.
        survey_id (str): survey ID column name.
        survey_key (str): survey key column name.

    Returns
    -------
        None

    """
    if not survey_id:
        st.info(
            "Duplicate entries for survey ID requires a survey ID column to be selected. Go to :material/settings: settings to select a survey ID column."
        )
        return
    # Load settings from file if it exists
    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(setting_file, "duplicates") or {}
    else:
        default_settings = {}
    display_cols = default_settings.get("id_display_cols")
    display_col_options = [
        col for col in data.columns if col not in [survey_id, survey_key, survey_date]
    ]
    display_cols = st.multiselect(
        label="Select columns to display in the report",
        options=display_col_options,
        default=display_cols,
        key="display_id_cols_duplicates",
        on_change=trigger_save,
        kwargs={"state_name": "display_id_cols_duplicates_save"},
    )
    if (
        "display_id_cols_duplicates_save" in st.session_state
    ) and st.session_state.display_id_cols_duplicates_save:
        save_check_settings(
            settings_file=setting_file,
            check_name="duplicates",
            check_settings={"id_display_cols": display_cols},
        )
        st.session_state["display_id_cols_duplicates_save"] = False

    id_dups_data = compute_id_duplicates(
        data=data,
        survey_id=survey_id,
        survey_date=survey_date,
        survey_key=survey_key,
        display_cols=display_cols,
    )

    if id_dups_data.height == 0:
        st.write(f"No duplicates found for {survey_id}")
    else:
        # Convert to pandas for Streamlit display
        st.dataframe(
            id_dups_data.to_pandas(),
            hide_index=True,
            width="stretch",
            column_config={
                "id_dup_count": st.column_config.Column(
                    label=f"# of {survey_id} duplicates"
                ),
                "id_dup_percent": st.column_config.NumberColumn(
                    label="% of total records", format="%.2f%%"
                ),
            },
        )


@st.cache_data
def compute_column_duplicates(
    data: pl.DataFrame,
    survey_id: str,
    survey_key: str,
    survey_date: str,
    dup_col: str,
    display_cols: list | None,
) -> pl.DataFrame:
    """
    Compute duplicates for the selected columns.

    Parameters
    ----------
        data (pl.DataFrame): The dataset to compute duplicates for.
        survey_id (str): The survey ID column name.
        survey_key (str): The survey key column name.
        dup_col (str): The column to check for duplicates.
        display_cols (list): The columns to display in the report.

    Returns
    -------
        pl.DataFrame: A DataFrame containing the duplicate entries for the selected
        columns.
    """
    # Filter for duplicate values in the specified column
    var_dups_data = data.filter(pl.col(dup_col).is_duplicated())

    # Count duplicates per value using over() for window function
    var_dups_data = var_dups_data.with_columns([
        pl.col(dup_col).count().over(dup_col).alias(f"{dup_col}_dup_count")
    ])

    # Calculate percentage
    total_records = data.height
    var_dups_data = var_dups_data.with_columns([
        (pl.col(f"{dup_col}_dup_count") / total_records * 100).alias(f"{dup_col}_dup_percent")
    ])

    # Build list of columns to select
    base_cols = [dup_col, f"{dup_col}_dup_count", f"{dup_col}_dup_percent"]

    # Add survey_id and survey_date if they exist in the data
    existing_vars = []
    if survey_id and survey_id in data.columns:
        existing_vars.append(survey_id)
    if survey_date and survey_date in data.columns:
        existing_vars.append(survey_date)

    # Build final column list
    if display_cols:
        cols_to_select = existing_vars + base_cols + display_cols
    else:
        cols_to_select = existing_vars + base_cols

    var_dups_data = var_dups_data.select(cols_to_select)

    return var_dups_data.sort([f"{dup_col}_dup_count", dup_col], descending=[True, False])


@demo_output_onboarding(TAB_NAME)
def display_column_duplicates(
    data: pl.DataFrame,
    survey_id: str | None,
    survey_key: str,
    survey_date: str | None,
    dup_cols: list | None,
    setting_file: str,
) -> None:
    """
    Display duplicates for the selected columns.

    Parameters
    ----------
        data (pl.DataFrame): The dataset to compute duplicates for.
        survey_id (str): survey ID column name.
        survey_key (str): survey key column name.
        dup_cols (list): The columns to check for duplicates.

    Returns
    -------
        None

    """
    if not dup_cols:
        st.info(
            "Duplicate entries for columns requires at least one column to be selected. Go to :material/settings: settings to select columns to check for duplicates."
        )
        return

    # load settings from file if it exists
    if setting_file and os.path.exists(setting_file):
        default_settings = load_check_settings(setting_file, "duplicates") or {}
    else:
        default_settings = {}
    dup_col = default_settings.get("dup_col")
    dup_col_index = dup_cols.index(dup_col) if dup_col and dup_col in dup_cols else 0
    display_cols = default_settings.get(f"{dup_col}/display_cols") if dup_col else None
    # make a list of columns with at least one duplicate
    dup_cols_with_dups = [
        col for col in dup_cols
        if data.select(pl.col(col)).is_duplicated().any()
    ]
    dup_cols_without_dups = [col for col in dup_cols if col not in dup_cols_with_dups]
    if len(dup_cols_with_dups) == 0:
        st.info(
            body="No columns with duplicates found. Please select a column to check for duplicates.",
            icon=":material/info:",
        )
        return
    elif len(dup_cols_without_dups) > 0:
        st.info(
            body=f"The following {dup_cols_without_dups} columns have no duplicates.",
            icon=":material/info:",
        )
    dup_col = st.selectbox(
        label="Select column to check for duplicates",
        options=dup_cols_with_dups,
        key="dup_col_duplicates",
        index=dup_col_index,
        on_change=trigger_save,
        kwargs={"state_name": "dup_col_duplicates_save"},
    )
    if (
        "dup_col_duplicates_save" in st.session_state
    ) and st.session_state.dup_col_duplicates_save:
        save_check_settings(
            settings_file=setting_file,
            check_name="duplicates",
            check_settings={"dup_col": dup_col},
        )
        st.session_state["dup_col_duplicates_save"] = False

    display_cols_options = [
        col
        for col in data.columns
        if col not in [survey_id, survey_key, survey_date, dup_col]
    ]
    display_cols = st.multiselect(
        label="Select columns to display in the report",
        options=display_cols_options,
        default=display_cols,
        key="display_cols_duplicates",
        on_change=trigger_save,
        kwargs={"state_name": "display_cols_duplicates_save"},
    )
    if (
        "display_cols_duplicates_save" in st.session_state
    ) and st.session_state.display_cols_duplicates_save:
        save_check_settings(
            settings_file=setting_file,
            check_name="duplicates",
            check_settings={f"{dup_col}/display_cols": display_cols},
        )
        st.session_state["display_cols_duplicates_save"] = False

    if dup_col:
        col_dups_data = compute_column_duplicates(
            data=data,
            survey_id=survey_id,
            survey_key=survey_key,
            survey_date=survey_date,
            dup_col=dup_col,
            display_cols=display_cols,
        )

        if col_dups_data.height == 0:
            st.write(f"No duplicates found for {dup_col}")
        else:
            # Convert to pandas for Streamlit display
            st.dataframe(
                col_dups_data.to_pandas(),
                hide_index=True,
                width="stretch",
                column_config={
                    f"{dup_col}_dup_count": st.column_config.Column(
                        label="# duplicates"
                    ),
                    f"{dup_col}_dup_percent": st.column_config.NumberColumn(
                        label="% duplicates", format="%.2f%%"
                    ),
                },
            )
    else:
        st.info(
            body="Please select a column to check for duplicates",
            icon=":material/info:",
        )


# define function to create duplicates report
def duplicates_report(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
) -> None:
    """
    Generate a report on duplicate data in the dataset. The report includes a
    summary of duplicate data, a table showing the number of duplicate rows, and
    an option to inspect duplicate rows.


    Parameters
    ----------
        data (pl.DataFrame): The dataset to generate the duplicate data
                report for.


    Returns
    -------
        None


    """
    # get column info
    _, string_columns, numeric_columns, datetime_columns, _ = get_df_info(
        data, cols_only=True
    )

    string_numeric_cols = list(set(string_columns + numeric_columns))

    st.title("Duplicates Report")

    config_settings = DuplicatesSettings(**config)
    duplicates_settings = duplicates_report_settings(
        setting_file, data, config_settings, string_numeric_cols, datetime_columns
    )

    # Duplicates column configuration
    st.write("---")
    st.title("Duplicates Column Configuration")
    # Get all columns for duplicate checking (strings and numerics)
    all_columns = data.columns
    _render_duplicates_column_actions(project_id, page_name_id, all_columns)

    # Get duplicates column config
    duplicates_column_config = duckdb_get_table(
        project_id,
        f"duplicates_{page_name_id}",
        "logs",
    )

    if duplicates_column_config.is_empty():
        return

    # Update unlocked columns if needed
    duplicates_column_config = _update_unlocked_duplicates_cols(
        duplicates_column_config,
        all_columns,
    )

    # Save updated config
    duckdb_save_table(
        project_id,
        duplicates_column_config,
        f"duplicates_{page_name_id}",
        db_name="logs",
    )

    # Extract all duplicate columns from config
    all_dup_cols = []
    for row in duplicates_column_config.iter_rows(named=True):
        all_dup_cols.extend(row["column_name"])

    # Remove duplicates and sort
    all_dup_cols = sorted(list(set(all_dup_cols)))

    # ---- Show report --- #
    st.write("---")
    st.markdown("## Duplicates Statistics Overview")
    display_duplicates_statistics(
        data=data,
        survey_id=duplicates_settings.survey_id,
        dup_cols=all_dup_cols,
    )

    st.write("---")
    st.markdown("## Duplicate Entries Survey ID")
    display_id_duplicates(
        data=data,
        survey_id=duplicates_settings.survey_id,
        survey_date=duplicates_settings.survey_date,
        survey_key=duplicates_settings.survey_key,
        setting_file=setting_file,
    )

    st.write("---")
    st.markdown("## Duplicate Entries for columns")
    display_column_duplicates(
        data=data,
        survey_id=duplicates_settings.survey_id,
        survey_key=duplicates_settings.survey_key,
        survey_date=duplicates_settings.survey_date,
        dup_cols=all_dup_cols,
        setting_file=setting_file,
    )
