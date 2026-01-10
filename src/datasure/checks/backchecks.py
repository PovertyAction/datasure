import re
from contextlib import suppress
from enum import Enum
from turtle import back
from typing import Any

import pandas as pd
import plotly.express as px
import polars as pl
import streamlit as st
from pydantic import BaseModel, Field

from datasure.utils import duckdb_get_table, duckdb_save_table
from datasure.utils.dataframe_utils import get_df_info
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

TAB_NAME: str = "backchecks"

IGNORE_MISSING_VALUES = "ignore_missing_values"
DO_NOT_COMPARE_VALUES = "Do not compare if the values contain:"
TREAT_VALUES_AS_SAME = "Treat these values as the same:"
NO_BACKCHECK_COLUMNS_SET = "Backcheck columns configuration required. Go to the :material/settings: settings section above and configure backcheck columns."


##### Backchecks #####


class SearchType(str, Enum):
    """Column search pattern types."""

    EXACT = "exact"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"
    CONTAINS = "contains"
    REGEX = "regex"


class BackcheckSettings(BaseModel):
    """Backcheck report settings model."""

    survey_key: str | None = Field(..., description="Column containing survey key")
    survey_id: str | None = Field(None, description="Column containing survey ID")
    survey_date: str | None = Field(None, description="Column containing survey date")
    backcheck_date: str | None = Field(None, description="Column containing backcheck date")
    enumerator: str | None = Field(None, description="Column containing enumerator")
    backchecker: str | None = Field(None, description="Column containing back checker")
    backcheck_target_percent: int = Field(10, description="Target percentage of backchecks")
    drop_duplicates_option: str = Field("drop", description="How to handle duplicate entries")
    no_differences_list: list[str] | None = Field(
        None,
        description="List of values that will not be marked as differences",
    )
    exclude_values_list: list[str] | None = Field(
        None,
        description="List of values to be excluded from backcheck comparisons",
    )
    nosymbols_option: bool = Field(
        False, description="Ignore symbols option for string comparison"
    )


class StrCompareOptions(BaseModel):
    """String comparison settings for backchecks."""

    case_option: str = Field("none", description="Case sensitivity option")
    trimspaces_option: bool = Field(False, description="Trim spaces option")
    nosymbols_option: bool = Field(False, description="Ignore symbols option")

class OkRangeValues(BaseModel):
    """OK range values settings for backchecks."""

    ok_range_neg: float | None = Field(le=0, description="Negative OK range value")
    ok_range_pos: float | None = Field(ge=0, description="Positive OK range value")

class OkRangeOptions(BaseModel):
    """OK range settings for backchecks."""

    ok_range_type: str | None = Field(None, description="Type of OK range")
    ok_range_values: OkRangeValues | None = Field(
        None, description="Values for OK range"
    )

class OkRangeType(str, Enum):
    """OK range types for backchecks."""

    NUMBER = "number"
    PERCENTAGE = "percentage"

class BackcheckTestOptions(BaseModel):
    """Backcheck test settings for backchecks."""

    ttest: bool = Field(False, description="Perform t-test")
    prtest: bool = Field(False, description="Perform proportion test")
    signrank: bool = Field(False, description="Perform sign rank test")
    reliability: bool = Field(False, description="Calculate reliability metrics")

@st.cache_data(ttl=60)
def load_default_backchecks_settings(
    settings_file: str, config: BackcheckSettings
) -> BackcheckSettings:
    """Load and merge saved settings with default configuration.

    Loads previously saved backcheck report settings from the settings file
    and merges them with the provided default configuration. Saved settings
    take precedence over defaults.

    Cached for 60 seconds to reduce file I/O operations.

    Parameters
    ----------
    settings_file : str
        Path to the settings file containing saved configurations.
    config : BackcheckSettings
        Default configuration to use as fallback for missing settings.

    Returns
    -------
    BackcheckSettings
        Merged settings combining saved and default configurations.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME)

    default_settings: dict = dict(config)
    default_settings.update(saved_settings)

    return BackcheckSettings(**default_settings)


# =============================================================================
# Column Search and Selection Utilities
# =============================================================================


def expand_col_names(
    col_names: list[str], pattern: str, search_type: str = "exact"
) -> list[str]:
    """Expand column names based on a pattern and search type.

    Parameters
    ----------
    col_names : list[str]
        List of column names to search in.
    pattern : str
        Pattern to match against column names.
    search_type : str, default="exact"
        Type of search to perform.

    Returns
    -------
    list[str]
        List of column names that match the pattern.

    Raises
    ------
    TypeError
        If input types are invalid.
    ValueError
        If search_type is not supported.
    """
    if not isinstance(col_names, list):
        raise TypeError("col_names must be a list of column names.")
    if not pattern:
        raise TypeError("pattern must be provided.")
    if not isinstance(pattern, str):
        raise TypeError("pattern must be a string.")

    search_funcs = {
        SearchType.EXACT.value: lambda col: col == pattern,
        SearchType.STARTSWITH.value: lambda col: col.startswith(pattern),
        SearchType.ENDSWITH.value: lambda col: col.endswith(pattern),
        SearchType.CONTAINS.value: lambda col: pattern in col,
        SearchType.REGEX.value: lambda col: re.match(pattern, col),
    }

    if search_type not in search_funcs:
        valid_types = ", ".join(search_funcs.keys())
        raise ValueError(
            f"Invalid search_type '{search_type}'. Choose from: {valid_types}."
        )

    return [col for col in col_names if search_funcs[search_type](col)]


# =============================================================================
# Backcheck Column Configuration Functions
# =============================================================================


def _get_ok_range_value(ok_range_type: OkRangeType) -> OkRangeValues:
    """Get the OK range value based on the selected type."""
    okr1, okr2 = st.columns(2)
    if ok_range_type == "number":
        okr_neg = okr1.number_input(
            "Negative Range Value", max_value=0.0, value=0.0, step=1.0, help="Enter the negative range value"
        )
        okr_pos = okr2.number_input(
            "Positive Range Value", min_value=0.0, value=0.0, step=1.0,  help="Enter the positive range value"
        )

    else:
        okr_neg = okr1.number_input(
            "Negative Range Value (%)",
            min_value=-100.0,
            max_value=0.0,
            value=0.0,
            step=1.0,
            help="Enter the negative range percentage",
        )
        okr_pos = okr2.number_input(
            "Positive Range Value (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            help="Enter the positive range percentage",
        )

    return OkRangeValues(ok_range_neg=okr_neg, ok_range_pos=okr_pos)


def _validate_backcheck_requirements(
    survey_key: str | None, survey_id: str | None, backcheck_data: pd.DataFrame
) -> bool:
    """Validate that required settings are configured for backcheck report.

    Parameters
    ----------
    survey_key : str | None
        Survey key column name.
    survey_id : str | None
        Survey ID column name.
    backcheck_data : pd.DataFrame
        Backcheck data.

    Returns
    -------
    bool
        True if requirements are met, False otherwise.
    """
    if not survey_key or not survey_id:
        st.info(
            "Please select Survey Key and Survey ID columns to generate the backcheck report."
        )
        return False

    if backcheck_data.empty:
        st.info("No back check data available")
        return False

    return True


def _get_merge_columns(base_cols: list[str], *optional_cols: str | None) -> list[str]:
    """Get unique columns for merging, avoiding duplicates."""
    cols = base_cols.copy()
    for col in optional_cols:
        if col and col not in cols:
            cols.append(col)
    return cols


def _prepare_merged_dataframes(
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    survey_id: str,
    enumerator: str | None,
    backchecker: str | None,
    date: str | None,
) -> pd.DataFrame:
    """Prepare and merge survey and backcheck dataframes."""
    # Get columns for merging
    survey_cols = _get_merge_columns([survey_id], enumerator, date)
    backcheck_cols = _get_merge_columns([survey_id], backchecker, date)

    # Create prefixed dataframes
    survey_df_bc = survey_data[survey_cols].add_prefix("_svy_")
    survey_df_bc.rename(columns={"_svy_" + survey_id: survey_id}, inplace=True)

    backcheck_df_bc = backcheck_data[backcheck_cols].add_prefix("_bc_")
    backcheck_df_bc.rename(columns={"_bc_" + survey_id: survey_id}, inplace=True)

    return pd.merge(survey_df_bc, backcheck_df_bc, on=survey_id, how="inner")


def _generate_backcheck_summaries(
    bc_column_config_df: pd.DataFrame,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    survey_id: str,
    enumerator: str | None,
    backchecker: str | None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate column summaries and comparison data.

    Parameters
    ----------
    bc_column_config_df : pd.DataFrame
        Column configuration dataframe.
    survey_data : pd.DataFrame
        Survey data.
    backcheck_data : pd.DataFrame
        Backcheck data.
    survey_id : str
        Survey ID column name.
    enumerator : str | None
        Enumerator column name.
    backchecker : str | None
        Backchecker column name.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        Column category summary and comparison dataframes.
    """
    if not bc_column_config_df.empty:
        column_category_summary, svy_bc_comparison_df = generate_column_summary(
            column_config_data=bc_column_config_df,
            survey_data=survey_data,
            backcheck_data=backcheck_data,
            survey_id=survey_id,
            enumerator=enumerator,
            backchecker=backchecker,
            summary_col=None,
        )

        # Calculate total backcheck error rate
        if column_category_summary.shape[0] > 0:
            total_backcheck_error_rate = (
                column_category_summary["# different"].sum()
                / column_category_summary["# compared"].sum()
            ) * 100
            st.session_state.total_backcheck_error_rate = total_backcheck_error_rate
        else:
            st.session_state.total_backcheck_error_rate = "n/a"
    else:
        column_category_summary = pd.DataFrame()
        svy_bc_comparison_df = pd.DataFrame()

    return column_category_summary, svy_bc_comparison_df


def display_overview_section(
    survey_df_bc: pd.DataFrame,
    backcheck_df_bc: pd.DataFrame,
    merged_df: pd.DataFrame,
    enumerator: str | None,
    backcheck_goal: int,
) -> tuple[int, int, int, int]:
    """Display the overview section with metrics and charts.

    Parameters
    ----------
    survey_df_bc : pd.DataFrame
        Survey data with prefixes.
    backcheck_df_bc : pd.DataFrame
        Backcheck data with prefixes.
    merged_df : pd.DataFrame
        Merged dataframe.
    enumerator : str | None
        Enumerator column name.
    backcheck_goal : int
        Target number of backchecks.

    Returns
    -------
    tuple[int, int, int, int]
        Overview metrics.
    """
    min_backcheck_rate = st.number_input(
        "Enter a minimum percentage target of surveys backchecked by enumerator e.g. 10%",
        min_value=0,
        max_value=100,
        value=10,
        key="total_surveys_backcheck",
        help="This is the minimum percentage of surveys that have been backchecked by enumerator",
    )

    # Compute and display overview metrics
    (
        total_backchecks,
        backcheck_goal_update,
        num_enumerators_bc,
        total_enumerators,
    ) = compute_backcheck_overview(
        survey_df_bc=survey_df_bc,
        backcheck_df_bc=backcheck_df_bc,
        merged_df=merged_df,
        enumerator=enumerator,
        backcheck_goal=backcheck_goal,
        min_backcheck_rate=min_backcheck_rate,
    )

    col1, _, col3 = st.columns(3)
    col1.metric("Total number of backchecks", total_backchecks)
    with col3:
        try:
            st.metric(
                "Total backcheck error rate",
                f"{st.session_state.total_backcheck_error_rate:.0f}%",
            )
        except (AttributeError, TypeError, ValueError):
            st.metric("Total backcheck error rate", "n/a")

    # Display overview charts
    display_overview_charts(
        total_backchecks, backcheck_goal_update, num_enumerators_bc, total_enumerators
    )

    return (
        total_backchecks,
        backcheck_goal_update,
        num_enumerators_bc,
        total_enumerators,
    )


@demo_output_onboarding(TAB_NAME)
def display_category_and_trends(
    bc_column_config_df: pd.DataFrame,
    column_category_summary: pd.DataFrame,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    survey_id: str,
    enumerator: str | None,
    backchecker: str | None,
    date: str | None,
) -> None:
    """Display category error rates and trends sections.

    Parameters
    ----------
    bc_column_config_df : pd.DataFrame
        Column configuration dataframe.
    column_category_summary : pd.DataFrame
        Column category summary data.
    survey_data : pd.DataFrame
        Survey data.
    backcheck_data : pd.DataFrame
        Backcheck data.
    survey_id : str
        Survey ID column name.
    enumerator : str | None
        Enumerator column name.
    backchecker : str | None
        Backchecker column name.
    date : str | None
        Date column name.
    """
    # Display category error rates
    if bc_column_config_df.empty:
        st.info(NO_BACKCHECK_COLUMNS_SET)
        st.write("")
    else:
        st.write("")
        display_category_error_rates(column_category_summary)

        # Error trends - only generate if date column is available
        if date:
            error_trends_category_summary, _ = generate_column_summary(
                column_config_data=bc_column_config_df,
                survey_data=survey_data,
                backcheck_data=backcheck_data,
                survey_id=survey_id,
                enumerator=enumerator,
                backchecker=backchecker,
                summary_col=date,
            )
        else:
            error_trends_category_summary = pd.DataFrame()

        display_error_trends(error_trends_category_summary, date)
        st.write("")


def _generate_staff_statistics(
    bc_column_config_df: pd.DataFrame,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    survey_id: str,
    enumerator: str | None,
    backchecker: str | None,
    summary_col: str,
    staff_type: str,
) -> pd.DataFrame:
    """Generate statistics for enumerators or backcheckers."""
    if bc_column_config_df.empty or not summary_col:
        return pd.DataFrame()

    stats_summary, _ = generate_column_summary(
        column_config_data=bc_column_config_df,
        survey_data=survey_data,
        backcheck_data=backcheck_data,
        survey_id=survey_id,
        enumerator=enumerator,
        backchecker=backchecker,
        summary_col=summary_col,
    )

    if stats_summary.empty or summary_col not in stats_summary.columns:
        return pd.DataFrame()

    # Aggregate statistics
    agg_dict = {
        "# surveys": "sum",
        "# backchecks": "sum",
        "# compared": "sum",
        "# different": "sum",
    }

    staff_stats = stats_summary.groupby([summary_col]).agg(agg_dict).reset_index()

    if staff_type == "enumerator":
        # Calculate percentage back checked and error rate for enumerators
        staff_stats["% back checked"] = (
            (staff_stats["# backchecks"] / staff_stats["# surveys"]) * 100
        ).round(2).astype(str) + "%"

        # Calculate error rate with division by zero protection
        mask = staff_stats["# compared"] > 0
        staff_stats["Error Rate"] = "0.00%"
        staff_stats.loc[mask, "Error Rate"] = (
            (staff_stats.loc[mask, "# different"] / staff_stats.loc[mask, "# compared"])
            * 100
        ).round(2).astype(str) + "%"

        # Rename columns for enumerator view
        rename_dict = {
            "# backchecks": "# back checked",
            "# compared": "# of values compared",
            "# different": "# of values different",
        }
        enum_cols = [col for col in staff_stats.columns if summary_col in col]
        if enum_cols:
            rename_dict[enum_cols[0]] = "Enumerator"

    else:  # backchecker
        # For backcheckers, calculate error rate differently
        mask = staff_stats["# compared"] > 0
        staff_stats["Error Rate"] = "0.00%"
        staff_stats.loc[mask, "Error Rate"] = (
            (staff_stats.loc[mask, "# different"] / staff_stats.loc[mask, "# compared"])
            * 100
        ).round(2).astype(str) + "%"

        # Find backchecker column and rename appropriately
        bcer_cols = [col for col in staff_stats.columns if summary_col in col]
        rename_dict = {
            "# backchecks": "# back checked",
            "# compared": "# values compared",
            "# different": "# different",
        }
        if bcer_cols:
            rename_dict[bcer_cols[0]] = "Back Checker"

    return staff_stats.rename(columns=rename_dict)


def _generate_enumerator_statistics(
    bc_column_config_df: pd.DataFrame,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    survey_id: str,
    enumerator: str | None,
    backchecker: str | None,
) -> pd.DataFrame:
    """Generate enumerator statistics."""
    return _generate_staff_statistics(
        bc_column_config_df,
        survey_data,
        backcheck_data,
        survey_id,
        enumerator,
        backchecker,
        enumerator,
        "enumerator",
    )


def _generate_backchecker_statistics(
    bc_column_config_df: pd.DataFrame,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    survey_id: str,
    enumerator: str | None,
    backchecker: str | None,
) -> pd.DataFrame:
    """Generate backchecker statistics."""
    stats = _generate_staff_statistics(
        bc_column_config_df,
        survey_data,
        backcheck_data,
        survey_id,
        enumerator,
        backchecker,
        backchecker,
        "backchecker",
    )

    if not stats.empty:
        # Select only required columns that exist
        required_cols = [
            "Back Checker",
            "# back checked",
            "# values compared",
            "# different",
            "Error Rate",
        ]
        existing_cols = [col for col in required_cols if col in stats.columns]
        return stats[existing_cols].copy()

    return pd.DataFrame()


def backchecks_report_settings(
    project_id: str,
    settings_file: str,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    config: BackcheckSettings,
    survey_categorical_columns: list[str],
    survey_datetime_columns: list[str],
    backcheck_categorical_columns: list[str],
    backcheck_datetime_columns: list[str],
) -> BackcheckSettings:
    """Create and render the settings UI for backchecks report configuration.

    This function creates a comprehensive Streamlit UI for configuring
    backchecks report settings. It includes:
    - Survey identifiers (key and ID columns)
    - Survey date column selection
    - Enumerator and backchecker columns
    - Tracking options (backcheck goal and duplicate handling)

    Settings are automatically saved to the settings file when changed
    and loaded from previous sessions if available.

    Parameters
    ----------
    project_id : str
        Unique project identifier for database operations.
    settings_file : str
        Path to settings file for saving/loading configurations.
    survey_data : pd.DataFrame
        Survey dataset.
    backcheck_data : pd.DataFrame
        Backcheck dataset.
    config : BackcheckSettings
        Default configuration used as fallback values.
    categorical_columns : list[str]
        Available categorical columns for selection.
    datetime_columns : list[str]
        Available datetime columns for date selection.

    Returns
    -------
    BackcheckSettings
        User-configured settings from the UI.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for backcheck report")
        st.write("---")

        default_settings = load_default_backchecks_settings(settings_file, config)

        # Survey Identifiers
        with st.container(border=True):
            st.subheader("Survey Identifiers")
            si1, si2, _ = st.columns(3)

            with si1:
                default_survey_key = default_settings.survey_key
                default_survey_key_index = (
                    survey_categorical_columns.index(default_survey_key)
                    if default_survey_key and default_survey_key in survey_categorical_columns
                    else None
                )
                survey_key = st.selectbox(
                    "Survey Key (required)",
                    options=survey_categorical_columns,
                    key="survey_key_backchecks",
                    help="Select the column that contains the survey key",
                    index=default_survey_key_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_key"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_key": survey_key})

            with si2:
                default_survey_id = default_settings.survey_id
                default_survey_id_index = (
                    survey_categorical_columns.index(default_survey_id)
                    if default_survey_id and default_survey_id in survey_categorical_columns
                    else None
                )
                survey_id = st.selectbox(
                    "Survey ID (required)",
                    options=survey_categorical_columns,
                    help="Select the column that contains the survey ID",
                    key="survey_id_backchecks",
                    index=default_survey_id_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_id"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_id": survey_id})

        # Survey Date
        with st.container(border=True):
            st.subheader("Survey & BAckcheck Dates")

            sd1, sd2, _ = st.columns(3)

            with sd1:
                default_survey_date = default_settings.survey_date
                default_survey_date_index = (
                    survey_datetime_columns.index(default_survey_date)
                    if default_survey_date and default_survey_date in survey_datetime_columns
                    else None
                )

                survey_date = st.selectbox(
                    "Survey Date",
                    options=survey_datetime_columns,
                    help="Select the column that contains the survey date",
                    key="survey_date_backchecks",
                    index=default_survey_date_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_date"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"survey_date": survey_date}
                )
            with sd2:
                default_backcheck_date = default_settings.survey_date
                default_backcheck_date_index = (
                    backcheck_datetime_columns.index(default_backcheck_date)
                    if default_backcheck_date
                    and default_backcheck_date in backcheck_datetime_columns
                    else None
                )

                backcheck_date = st.selectbox(
                    "Backcheck Date",
                    options=backcheck_datetime_columns,
                    help="Select the column that contains the backcheck date",
                    key="backcheck_date_backchecks",
                    index=default_backcheck_date_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_backcheck_date"},
                )

        # Enumerator and Backchecker
        with st.container(border=True):
            st.subheader("Staff Identifiers")
            ec1, ec2, _ = st.columns(3)

            with ec1:
                default_enumerator = default_settings.enumerator
                default_enumerator_index = (
                    survey_categorical_columns.index(default_enumerator)
                    if default_enumerator and default_enumerator in survey_categorical_columns
                    else None
                )
                enumerator = st.selectbox(
                    "Enumerator",
                    options=survey_categorical_columns,
                    key="enumerator_backchecks",
                    help="Select the column that contains the enumerator ID",
                    index=default_enumerator_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_enumerator"},
                )
                save_check_settings(settings_file, TAB_NAME, {"enumerator": enumerator})

            with ec2:
                # Get backcheck columns for backchecker selection
                default_backchecker = default_settings.backchecker
                default_backchecker_index = (
                    backcheck_categorical_columns.index(default_backchecker)
                    if default_backchecker and default_backchecker in backcheck_categorical_columns
                    else None
                )
                backchecker = st.selectbox(
                    "Back Checker",
                    options=backcheck_categorical_columns,
                    key="backchecker_backchecks",
                    help="Select the column that contains the back checker ID",
                    index=default_backchecker_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_backchecker"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"backchecker": backchecker}
                )

        # Tracking Options
        with st.container(border=True):
            st.subheader("Tracking Options")

            to1, _, _ = st.columns(3)

            with to1:
                default_backcheck_goal = default_settings.backcheck_target_percent
                backcheck_goal = st.number_input(
                    "Target number of backchecks",
                    min_value=0,
                    help="Total number of backchecks expected",
                    key="backcheck_goal_backchecks",
                    value=default_backcheck_goal,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_backcheck_goal"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"backcheck_goal": backcheck_goal}
                )

        # Additional Options
        with st.container(border=True):
            st.subheader("Additional Options")

            with st.container(border=True):
                st.markdown("##### Duplicate Handling")
                st.write("How would you like to handle duplicates?")
                default_drop_duplicates = default_settings.drop_duplicates_option
                options_map = {"drop": ":material/remove_selection: Drop All Entries", "first": ":material/first_page: Keep First Entry", "last": ":material/last_page: Keep Last Entry"}
                drop_duplicates_option = st.pills(
                    "Select an option for handling duplicates",
                    options=list(options_map.keys()),
                    format_func=lambda x: options_map[x],
                    key="drop_duplicates_option_backchecks",
                    default=default_drop_duplicates,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_drop_duplicates_option"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"drop_duplicates_option": drop_duplicates_option}
                )

            with st.container(border=True):
                st.markdown("##### No differences Settings")
                st.write("Settings for entries values in backchecks that will not be marked as differences.")
                no_diff_values = _render_no_differences_settings(settings_file)

                if no_diff_values:
                    st.info("The following values will not be marked as differences:")
                    # save into a dataframe for better display
                    no_diff_df = pl.DataFrame({"Values": no_diff_values})
                    # configure column to be displayed as a list without index
                    dc1, _ = st.columns([1, 3])
                    dc1.dataframe(no_diff_df, hide_index=True, column_config={"Values": st.column_config.ListColumn("Values", help="Values that will not be marked as differences", width="content")})
                else:
                    st.warning("No values configured to be excluded from differences.")

            with st.container(border=True):
                st.markdown("##### Exclude Value Settings")
                st.write("Settings for entries values in backchecks that will be excluded from backcheck comparisons.")
                exclude_values = _render_exclude_values_settings(settings_file)
                if exclude_values:
                    st.info("The following values will be excluded from backcheck comparisons:")
                    # save into a dataframe for better display
                    exclude_df = pl.DataFrame({"Values": exclude_values})
                    # configure column to be displayed as a list without index
                    dr1, _ = st.columns([1, 3])
                    dr1.dataframe(exclude_df, hide_index=True, column_config={"Values": st.column_config.ListColumn("Values", help="Values that will be excluded from backcheck comparisons", width="content")})
                else:
                    st.warning("No values configured to be excluded from backcheck comparisons.")

            with st.container(border=True):
                st.markdown("##### String Comparison Settings")
                st.write("Settings for string comparison in backcheck comparisons.")
                string_comp_options: StrCompareOptions = _render_string_comparison_options(settings_file)

    return BackcheckSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        backcheck_date=backcheck_date,
        enumerator=enumerator,
        backchecker=backchecker,
        backcheck_goal=backcheck_goal,
        drop_duplicates=drop_duplicates_option,
        no_differences_list=no_diff_values,
        exclude_values_list=exclude_values,
        case_option=string_comp_options.case_option,
        trimspaces_option=string_comp_options.trimspaces_option,
        nosymbols_option=string_comp_options.nosymbols_option,
    )


# =============================================================================
# Backcheck Column Actions - UI Configuration
# =============================================================================


def _render_search_type_selection(
    common_columns: list[str],
) -> tuple[str, str | None, list[str], bool]:
    """Render search type selection UI for backcheck columns.

    Parameters
    ----------
    common_columns : list[str]
        List of columns common to both survey and backcheck data.

    Returns
    -------
    tuple[str, str | None, list[str], bool]
        Search type, pattern, selected columns, and lock_cols flag.
    """
    search_type_options = [e.value for e in SearchType]
    search_type = st.selectbox(
        label="Search type",
        options=search_type_options,
        index=0,
        help="Select the type of search to perform on the column names.",
    )

    if search_type == SearchType.EXACT.value:
        backcheck_cols_sel = st.multiselect(
            label="Select columns to configure for backcheck",
            options=common_columns,
            default=None,
            help="Select column or group of columns to configure for backcheck comparison.",
        )
        pattern, lock_cols = None, None
        return search_type, pattern, backcheck_cols_sel, lock_cols
    else:
        pattern = st.text_input(
            label="Enter pattern to match column names",
            placeholder="Enter pattern to match column names",
            help="Enter the pattern to match column names based on the "
            "selected search type.",
        )
        if pattern:
            backcheck_cols_patt = expand_col_names(
                common_columns, pattern, search_type=search_type
            )
        else:
            backcheck_cols_patt = []

        st.write(
            "**Columns Selected:** ",
            ", ".join(backcheck_cols_patt) if backcheck_cols_patt else "None",
        )
        return search_type, pattern, backcheck_cols_patt, None


def _render_backcheck_category_options() -> int:
    """Render backcheck category selection UI.

    Returns
    -------
    int
        Selected category (1, 2, or 3).
    """
    with st.container(border=True):
        st.markdown("##### Backcheck Category Selection")
        options_map = {1: ":material/looks_one: Category 1", 2: ":material/looks_two: Category 2", 3: ":material/looks_3: Category 3"}

        category = st.pills(
            "Select Backcheck Category",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            selection_mode="single",
            default=None,
            help="Select the backcheck category for the column(s).",
        )
    return category


def _render_ok_range_options() -> OkRangeOptions:
    """Render OK range options UI.

    Returns
    -------
    tuple[str, str]
        OK range type and OK range value.
    """
    with st.container(border=True):
        st.markdown("##### OK Range Selection")
        options_map = {"number": ":material/123: Value Range", "percentage": ":material/percent: Percentage Range"}
        ok_range_type = st.pills(
            "Select OK Range Type",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            selection_mode="single",
            default=None,
            help="Select the type of OK range condition for the column(s).",
            key="ok_range_type_backchecks_pills",
        )
        if ok_range_type:
            ok_range_value: OkRangeValues = _get_ok_range_value(OkRangeType(ok_range_type))
        else:
            ok_range_value = OkRangeValues(ok_range_neg=0.0, ok_range_pos=0.0)

    return OkRangeOptions(ok_range_type=ok_range_type, ok_range_value=ok_range_value)

def _render_backcheck_test_options(backcheck_category: int) -> BackcheckTestOptions:
    """Render backcheck test condition selection UI.

    Returns
    -------
    str
        Selected Back Check Test
    """
    with st.container(border=True):
        st.markdown("##### Statistical Test")
        with st.expander("Statisical Test Information", expanded=False):
            st.write(
                """
                Select the statistical test to apply for backcheck comparisons.

                - **ttest**: run paired two-sample mean-comparison tests for values in the back check and survey data.
                - **prtest**: run two-sample test of equality of proportions in the back check and survey data for dichotmous variables.
                - **signrank**: run Wilcoxon signed-rank tests for values in the back check and survey data.
                - **reliability**: calculate the simple response variance (SRV) and reliability ratio for type 2 and 3 variables.
                """
            )
        options_map = {
            "ttest": "t-test",
            "prtest": "prtest",
            "signrank": "sign rank test",
            "reliability": "reliability analysis",
        }

        # dont show reliability if category 1 is selected
        if backcheck_category == 1:
            options_map.pop("reliability")

        backcheck_test = st.pills(
            "Select Backcheck Statistical Test",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            selection_mode="multi",
            default="ttest",
            help="Select the statistical test to apply for backcheck comparisons.",
            key="backcheck_test_backchecks_pills",
        )

    return BackcheckTestOptions(ttest="ttest" in backcheck_test,
                         prtest="prtest" in backcheck_test,
                         signrank="signrank" in backcheck_test,
                         reliability="reliability" in backcheck_test)

@st.fragment
def _render_no_differences_settings(settings_file: str) -> list:
    """Render UI for managing values that won't be considered as discrepancies.

    This function allows users to add or remove values from a list. Values in this
    list will not be marked as differences during backcheck comparison, regardless
    of whether they appear in the survey or backcheck data.

    Parameters
    ----------
    settings_file : str
        Path to the settings file.
    tab_name : str
        Name of the tab/check (used as key in settings).
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME)
    updated_values = saved_settings.get("no_differences_values", [])
    ac_col, rc_col, _ = st.columns([0.4, 0.3, 0.3])
    with ac_col, st.popover("Add Value", type="primary", width="stretch"):
        new_value = st.text_input(
            "Enter value to exclude from differences",
            key="new_no_diff_value_input",
            help="Enter the value to be excluded from difference checks.",
        )
        # validate input and add to list
        if st.button(
            "Add Value",
            key="add_no_diff_value",
            help="Add the value to the no-differences list.",
            width="stretch",
            disabled=not new_value,
            type="primary",
            on_click=trigger_save,
            kwargs={"state_name": TAB_NAME + "_no_differences_values"},
        ):
            saved_settings = load_check_settings(settings_file, TAB_NAME)
            no_diff_values = saved_settings.get("no_differences_values", [])
            if no_diff_values:
                no_diff_values.append(new_value)
                updated_values = no_diff_values
            else:
                updated_values = [new_value]
            save_check_settings(
                settings_file,
                TAB_NAME,
                {"no_differences_values": updated_values},
            )
            st.rerun()

    with rc_col, st.popover("Remove Value", width="stretch"):
        saved_settings = load_check_settings(settings_file, TAB_NAME)
        no_diff_values = saved_settings.get("no_differences_values", [])
        if not no_diff_values:
            st.info("No values to remove.")
        value_to_remove = st.selectbox(
            "Select value to remove from no-differences list",
            options=no_diff_values,
            key="remove_no_diff_value_select",
            help="Select the value to remove from the no-differences list.",
            disabled=not no_diff_values,
        )
        if st.button(
            "Remove Value",
            key="remove_no_diff_value",
            help="Remove the selected value from the no-differences list.",
            width="stretch",
            type="primary",
            on_click=trigger_save,
            kwargs={"state_name": TAB_NAME + "_no_differences_value"},
        ):
            no_diff_values.remove(value_to_remove)
            updated_values = no_diff_values
            save_check_settings(
                settings_file,
                TAB_NAME,
                {"no_differences_values": updated_values},
            )
            st.rerun()

    return updated_values

@st.fragment
def _render_string_comparison_options(settings_file) -> StrCompareOptions:
    """Render string comparison options UI.

    Returns
    -------
    StrCompareOptions
        Selected string comparison options.
    """
    st.markdown("##### String Comparison Options")
    sok1, sok2, sok3 = st.columns(3)
    default_settings = load_check_settings(settings_file, TAB_NAME)
    default_case_setting = default_settings.get("string_case_option", None)
    options_map = {"lowercase": ":material/lowercase: lowercase", "uppercase": ":material/uppercase: UPPERCASE"}
    with sok1, st.container(border=True):
        string_case_option = st.pills(
            "Convert String Case Before Comparison",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            default=default_case_setting,
            key="string_case_option_backchecks_pills",
            help="Select how to handle case sensitivity in string comparisons.",
            selection_mode="single",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_string_case_option"},
        )
        save_check_settings(settings_file, TAB_NAME, {"string_case_option": string_case_option})

    with sok2, st.container(border=True):
        default_nosymbols_setting = default_settings.get("string_nosymbols_option", False)
        string_nosymbols_option = st.toggle(
            label="Ignore Symbols in String Comparison",
            value=default_nosymbols_setting,
            key="string_nosymbols_option_backchecks_toggle",
            help="Toggle to ignore symbols when comparing string values.",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_string_nosymbols_option"},
        )
        save_check_settings(settings_file, TAB_NAME, {"string_nosymbols_option": string_nosymbols_option})

    with sok3, st.container(border=True):
        default_trimspaces_setting = default_settings.get("string_trimspaces_option", False)
        string_trimspaces_option = st.toggle(
            label="Trim Spaces in String Comparison",
            value=default_trimspaces_setting,
            key="string_trimspaces_option_backchecks_toggle",
            help="Toggle to trim leading and trailing spaces when comparing string values.",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_string_trimspaces_option"},
        )
        save_check_settings(
            settings_file,
            TAB_NAME,
            {"string_trimspaces_option": string_trimspaces_option}
        )

    return StrCompareOptions(
        case_option=string_case_option,
        nosymbol_option=string_nosymbols_option,
        whitespace_option=string_trimspaces_option,
    )

@st.fragment
def _render_exclude_values_settings(
    settings_file: str
) -> list:
    """Render UI for managing values to exclude from backcheck comparison."""
    ac_col, rc_col, _ = st.columns([0.4, 0.3, 0.3])
    with ac_col, st.popover("Add Exclude Value", type="primary", width="stretch"):
        new_value = st.text_input(
            "Enter value to exclude from backcheck comparison",
            key="new_exclude_value_input",
            help="Enter the value to be excluded from backcheck comparison.",
        )
        # validate input and add to list
        saved_settings = load_check_settings(settings_file, TAB_NAME)
        exclude_values = saved_settings.get("exclude_values", [])
        updated_values = exclude_values
        if st.button(
            "Add Exclude Value",
            key="add_exclude_value",
            help="Add the value to the exclude list.",
            width="stretch",
            disabled=not new_value,
            type="primary",
            on_click=trigger_save,
            kwargs={"state_name": TAB_NAME + "_exclude_values"},
        ):
            saved_settings = load_check_settings(settings_file, TAB_NAME)
            exclude_values = saved_settings.get("exclude_values", [])
            if exclude_values:
                exclude_values.append(new_value)
                updated_values = exclude_values
            else:
                updated_values = [new_value]
            save_check_settings(
                settings_file,
                TAB_NAME,
                {"exclude_values": updated_values},
            )
            st.rerun()

    with rc_col, st.popover("Remove Exclude Value", width="stretch"):
        if not exclude_values:
            st.info("No values to remove.")
        value_to_remove = st.selectbox(
            "Select value to remove from exclude list",
            options=exclude_values,
            key="remove_exclude_value_select",
            help="Select the value to remove from the exclude list.",
            disabled=not exclude_values,
        )
        if st.button(
            "Remove Exclude Value",
            key="remove_exclude_value",
            help="Remove the selected value from the exclude list.",
            width="stretch",
            type="primary",
            on_click=trigger_save,
            kwargs={"state_name": TAB_NAME + "_exclude_values"},
        ):
            saved_settings = load_check_settings(settings_file, TAB_NAME)
            exclude_values = saved_settings.get("exclude_values", [])
            if value_to_remove in exclude_values:
                exclude_values.remove(value_to_remove)
                updated_values = exclude_values
                save_check_settings(
                    settings_file,
                    TAB_NAME,
                    {"exclude_values": updated_values},
                )
                st.rerun()

    return updated_values

def _render_backchecks_column_actions(
    project_id: str, page_name_id: str, survey_data, backcheck_data, common_columns: list[str]
) -> None:
    """Render the backcheck column configuration UI.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    common_columns : list[str]
        List of columns common to both survey and backcheck data.
    """
    backcheck_settings = duckdb_get_table(
        project_id,
        f"backchecks_{page_name_id}",
        "logs",
    )

    os1, os2, _ = st.columns([0.4, 0.3, 0.3])
    with os1:
        st.button(
            "Add Backcheck Column",
            key="add_backcheck_column",
            help="Add a new backcheck column configuration.",
            width="stretch",
            type="primary",
            on_click=_add_backcheck_column,
            args=(
                project_id,
                page_name_id,
                survey_data,
                backcheck_data,
                common_columns,
            ),
        )
    with os2:
        _delete_backcheck_column(project_id, page_name_id, backcheck_settings)

    if backcheck_settings.is_empty():
        st.info(
            "Use the :material/add: button to add columns for backcheck comparison and the "
            ":material/delete: button to remove columns."
        )
    else:
        _render_backcheck_settings_table(backcheck_settings)


@st.dialog("Add Backcheck Column(s)", width="medium")
def _add_backcheck_column(
    project_id: str, page_name_id: str, survey_data: pl.DataFrame, backcheck_data: pl.DataFrame, common_columns: list[str]
) -> None:
    """Dialog to add a new backcheck column configuration.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    common_columns : list[str]
        List of columns common to both survey and backcheck data.
    """
    # Render search type selection
    search_type, pattern, backcheck_cols, _lock_cols_initial = (
        _render_search_type_selection(common_columns)
    )

    if backcheck_cols:
        # Render backcheck category
        backcheck_category = _render_backcheck_category_options()

        if backcheck_category:

            # Render OK range options
            # Check if columns are numeric in both datasets
            cols_numeric_in_survey = all(
                survey_data.schema[col].is_numeric()
                for col in backcheck_cols
                if col in survey_data.columns
            )

            cols_numeric_in_backcheck = all(
                backcheck_data.schema[col].is_numeric()
                for col in backcheck_cols
                if col in backcheck_data.columns
            )

            # Only show OK range options for numeric columns
            if cols_numeric_in_survey and cols_numeric_in_backcheck:
                ok_range_options: OkRangeOptions = _render_ok_range_options()
                backcheck_test_options: BackcheckTestOptions = _render_backcheck_test_options(backcheck_category)
            else:
                ok_range_options = OkRangeOptions(ok_range_type=None, ok_range_values=None)
                backcheck_test_options = BackcheckTestOptions(ttest=False, prtest=False, signrank=False, reliability=False)

            if st.button(
                "Add Backcheck Column Configuration",
                key="confirm_add_backcheck_column",
                type="primary",
                width="stretch",
                disabled=not backcheck_cols or not backcheck_category,
            ):
                _update_backcheck_column_config(
                    project_id,
                    page_name_id,
                    search_type,
                    pattern,
                    backcheck_cols,
                    backcheck_category,
                    ok_range_options,
                    backcheck_test_options,
                )

                st.success("Backcheck column configuration added successfully.")
                st.rerun()


def _update_backcheck_column_config(
    project_id: str,
    page_name_id: str,
    search_type: str,
    pattern: str | None,
    backcheck_cols: list[str],
    backcheck_category: int,
    ok_range_options: OkRangeOptions,
    backcheck_test_options: BackcheckTestOptions,
) -> None:
    """Update the backcheck column configuration in the database.

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
    backcheck_cols : list[str]
        Selected columns.
    category : int
        Backcheck category (1, 2, or 3).
    ok_range : str
        OK range value.
    comparison_condition : str
        Comparison condition.
    """
    # Get existing config
    existing_config = duckdb_get_table(
        project_id=project_id,
        alias=f"backchecks_{page_name_id}",
        db_name="logs",
    )

    # Prepare new configuration
    new_config = {
        "search_type": search_type,
        "pattern": pattern,
        "column_name": [backcheck_cols],
        "category": backcheck_category,
        "ok_range_type": ok_range_options.ok_range_type if ok_range_options else None,
        "ok_range_values": ok_range_options.ok_range_values if ok_range_options else None,
        "ttest": backcheck_test_options.ttest,
        "prtest": backcheck_test_options.prtest,
        "signrank": backcheck_test_options.signrank,
        "reliability": backcheck_test_options.reliability,
    }

    schema = {
        "search_type": pl.Utf8,
        "pattern": pl.Utf8,
        "column_name": pl.List(pl.Utf8),
        "category": pl.Int64,
        "ok_range_type": pl.Utf8,
        "ok_range_values": pl.List(pl.Float64),
        "ttest": pl.Boolean,
        "prtest": pl.Boolean,
        "signrank": pl.Boolean,
        "reliability": pl.Boolean,
    }

    # Append new configuration to existing polars DataFrame
    new_config_df = pl.DataFrame(new_config, schema=schema)
    if not existing_config.is_empty():
        updated_config = pl.concat([existing_config, new_config_df], how="vertical")
    else:
        updated_config = new_config_df

    # Save updated configuration back to the database
    duckdb_save_table(
        project_id,
        updated_config,
        f"backchecks_{page_name_id}",
        db_name="logs",
    )


def _render_backcheck_settings_table(backcheck_settings: pl.DataFrame) -> None:
    """Render the backcheck settings table in Streamlit.

    Parameters
    ----------
    backcheck_settings : pl.DataFrame
        Backcheck settings configuration.
    """
    with st.expander("Backcheck Column Settings", expanded=False):
        st.dataframe(
            backcheck_settings,
            width="stretch",
            hide_index=True,
            column_config={
                "search_type": st.column_config.Column("Search Type"),
                "pattern": st.column_config.Column("Pattern"),
                "column_name": st.column_config.Column("Column Name(s)"),
                "category": st.column_config.NumberColumn("Category"),
                "ok_range_type": st.column_config.Column("OK Range Type"),
                "ok_range_values": st.column_config.Column("OK Range Values"),
                "ttest": st.column_config.CheckboxColumn("t-test"),
                "prtest": st.column_config.CheckboxColumn("prtest"),
                "signrank": st.column_config.CheckboxColumn("Sign Rank Test"),
                "reliability": st.column_config.CheckboxColumn("Reliability Analysis"),
            },
        )


def _delete_backcheck_column(
    project_id: str, page_name_id: str, backcheck_settings: pl.DataFrame
) -> None:
    """Render delete backcheck column button and handle deletion.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    backcheck_settings : pl.DataFrame
        Current backcheck settings.
    """
    with st.popover(
        label=":material/delete: Delete backcheck column",
        width="stretch",
    ):
        st.markdown("#### Remove backcheck columns")

        if backcheck_settings.is_empty():
            st.info("No backcheck columns have been added yet.")
        else:
            backcheck_settings_indexed = backcheck_settings.with_row_index().with_columns(
                (
                    pl.col("index").cast(pl.Utf8)
                    + " - "
                    + pl.col("search_type")
                    + " - "
                    + pl.col("pattern").fill_null("")
                ).alias("composite_index")
            )

            unique_index = (
                backcheck_settings_indexed["composite_index"]
                .unique(maintain_order=True)
                .to_list()
            )

            selected_index = st.selectbox(
                label="Select backcheck column to remove",
                options=unique_index,
                help="Select the backcheck column to remove from the list.",
            )

            if st.button(
                label="Confirm deletion",
                type="primary",
                width="stretch",
                key="confirm_delete_backcheck_column",
                help="Click to remove the selected backcheck column configuration.",
                disabled=not selected_index,
            ):
                updated_settings = backcheck_settings_indexed.filter(
                    pl.col("composite_index") != selected_index
                ).drop("composite_index", "index")

                duckdb_save_table(
                    project_id,
                    updated_settings,
                    f"backchecks_{page_name_id}",
                    "logs",
                )

                st.rerun()


def process_duplicate_data(
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    survey_id: str,
    date: str,
    drop_duplicates: bool,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Process and handle duplicates in survey and backcheck data.

    Parameters
    ----------
    survey_data : pd.DataFrame
        Survey data.
    backcheck_data : pd.DataFrame
        Backcheck data.
    survey_id : str
        Survey ID column name.
    date : str
        Date column name.
    drop_duplicates : bool
        Whether to drop duplicates.

    Returns
    -------
    tuple[pd.DataFrame, pd.DataFrame]
        Processed survey and backcheck data.
    """
    if not drop_duplicates:
        return survey_data, backcheck_data

    # Check if required columns exist
    if survey_id not in survey_data.columns or date not in survey_data.columns:
        return survey_data, backcheck_data
    if survey_id not in backcheck_data.columns or date not in backcheck_data.columns:
        return survey_data, backcheck_data

    # Convert date columns to datetime if they aren't already
    for df in [survey_data, backcheck_data]:
        if not pd.api.types.is_datetime64_any_dtype(df[date]):
            with suppress(Exception):
                df[date] = pd.to_datetime(df[date])

    # Process duplicates - keep most recent entry per survey_id
    survey_processed = (
        survey_data.sort_values(by=date, ascending=False)
        .drop_duplicates(subset=[survey_id], keep="first")
        .copy()
    )
    backcheck_processed = (
        backcheck_data.sort_values(by=date, ascending=False)
        .drop_duplicates(subset=[survey_id], keep="first")
        .copy()
    )

    return survey_processed, backcheck_processed


@st.cache_data
def compute_backcheck_overview(
    survey_df_bc: pd.DataFrame,
    backcheck_df_bc: pd.DataFrame,
    merged_df: pd.DataFrame,
    enumerator: str | None,
    backcheck_goal: int,
    min_backcheck_rate: float,
) -> tuple:
    """Compute overview metrics for backcheck report.

    Parameters
    ----------
    survey_df_bc : pd.DataFrame
        Survey data with prefixes.
    backcheck_df_bc : pd.DataFrame
        Backcheck data with prefixes.
    merged_df : pd.DataFrame
        Merged survey and backcheck data.
    enumerator : str
        Enumerator column name.
    backcheck_goal : int
        Target number of backchecks.
    min_backcheck_rate : float
        Minimum backcheck rate percentage.

    Returns
    -------
    tuple
        Overview metrics.
    """
    total_backchecks = len(backcheck_df_bc)

    # Handle case when backchecks > target
    backcheck_goal_update = (
        max(backcheck_goal, total_backchecks)
        if backcheck_goal > 0
        else total_backchecks
    )
    # Calculate backcheck rate by enumerator
    if enumerator:
        backcheck_sum_df = (
            survey_df_bc.groupby("_svy_" + enumerator)
            .size()
            .reset_index(name="total_surveys")
        )

        backcheck_sum_df = backcheck_sum_df.merge(
            merged_df.groupby("_svy_" + enumerator)
            .size()
            .reset_index(name="total_backchecks"),
            left_on="_svy_" + enumerator,
            right_on="_svy_" + enumerator,
            how="outer",
        )

        backcheck_sum_df["backcheck_rate"] = (
            backcheck_sum_df["total_backchecks"] / backcheck_sum_df["total_surveys"]
        ) * 100

        bc_target_met_df = backcheck_sum_df[
            backcheck_sum_df["backcheck_rate"] >= min_backcheck_rate
        ]

        num_enumerators_bc = bc_target_met_df["_svy_" + enumerator].nunique()
        total_enumerators = len(survey_df_bc["_svy_" + enumerator].unique())

    else:
        num_enumerators_bc = 0
        total_enumerators = 0
    return (
        total_backchecks,
        backcheck_goal_update,
        num_enumerators_bc,
        total_enumerators,
    )


@st.cache_data
def generate_column_summary(
    column_config_data: pd.DataFrame,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    survey_id: str,
    enumerator: str | None,
    backchecker: str | None,
    summary_col: str | None,
) -> tuple:
    """Generate a summary for each column configuration.

    Parameters
    ----------
    column_config_data : pd.DataFrame
        DataFrame containing column configuration.
    survey_data : pd.DataFrame
        Survey data.
    backcheck_data : pd.DataFrame
        Backcheck data.
    survey_id : str
        Survey ID column name.
    enumerator : str
        Enumerator column name.
    backchecker : str
        Backchecker column name.
    summary_col : str, optional
        Column name to group results by.

    Returns
    -------
    tuple
        Summary DataFrame and merged results DataFrame.
    """
    # Update datasets with prefixes
    survey_data = survey_data.add_prefix("_svy_").rename(
        columns={"_svy_" + survey_id: survey_id}
    )
    backcheck_data = backcheck_data.add_prefix("_bc_").rename(
        columns={"_bc_" + survey_id: survey_id}
    )

    if enumerator:
        enumerator = "_svy_" + enumerator
    if backchecker:
        backchecker = "_bc_" + backchecker

    summary_data = []
    merged_results_df = pd.DataFrame()

    for _, row in column_config_data.iterrows():
        column_name = row["column"]
        column_type = row["category"]
        ok_range = row["ok_range"]
        comparison_condition = row["comparison_condition"]

        # Prepare survey and backcheck data
        svy_col = f"_svy_{column_name}"
        bc_col = f"_bc_{column_name}"

        # Create merged dataframe for this column
        merged_svy_bc_df = _create_merged_comparison_df(
            survey_data,
            backcheck_data,
            survey_id,
            enumerator,
            backchecker,
            svy_col,
            bc_col,
            summary_col,
        )

        # Apply comparison logic using vectorized operation where possible
        if merged_svy_bc_df.empty:
            merged_svy_bc_df["comparison_result"] = pd.Series(dtype=str)
        else:
            # For better performance, we could vectorize simple cases
            if not ok_range and not comparison_condition:
                # Simple string comparison - can be vectorized
                merged_svy_bc_df["comparison_result"] = (
                    merged_svy_bc_df[svy_col].astype(str).str.strip()
                    == merged_svy_bc_df[bc_col].astype(str).str.strip()
                ).map({True: "not_different", False: "different"})
            else:
                # Complex comparison - use apply
                merged_svy_bc_df["comparison_result"] = merged_svy_bc_df.apply(
                    lambda row,
                    s=svy_col,
                    b=bc_col,
                    r=ok_range,
                    c=comparison_condition: _compare_values(row, s, b, r, c),
                    axis=1,
                )

        merged_svy_bc_df["variable"] = svy_col.replace("_svy_", "")
        merged_svy_bc_df_clean = merged_svy_bc_df.copy()
        merged_svy_bc_df_clean = merged_svy_bc_df_clean.rename(
            columns={
                svy_col: "survey value",
                bc_col: "backcheck value",
            }
        )

        # Add to results
        merged_results_df = pd.concat(
            [merged_results_df, merged_svy_bc_df_clean], ignore_index=True
        )

        # Calculate summary statistics
        summary_stats = _calculate_column_summary_stats(
            merged_svy_bc_df,
            column_name,
            column_type,
            survey_data[svy_col],
            summary_col,
        )
        summary_data.extend(summary_stats)

    # Clean merged table results (only if DataFrame is not empty)
    if not merged_results_df.empty:
        merged_results_df = merged_results_df.rename(
            columns={
                enumerator: "Enumerator",
                backchecker: "Back Checker",
            }
        )
        enum_bc_cols = [survey_id]
        if enumerator:
            enum_bc_cols.append("Enumerator")
        if backchecker:
            enum_bc_cols.append("Back Checker")

        other_cols = [
            col for col in merged_results_df.columns if col not in enum_bc_cols
        ]
        merged_results_df = merged_results_df[enum_bc_cols + other_cols]

    return pd.DataFrame(summary_data), merged_results_df


def _create_merged_comparison_df(
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    survey_id: str,
    enumerator: str | None,
    backchecker: str | None,
    svy_col: str,
    bc_col: str,
    summary_col: str | None,
) -> pd.DataFrame:
    """Create merged dataframe for comparison."""
    # Determine columns to include
    if enumerator:
        svy_summary_cols = [survey_id, enumerator, svy_col]
    else:
        svy_summary_cols = [survey_id, svy_col]
    if backchecker:
        bc_summary_cols = [survey_id, backchecker, bc_col]
    else:
        bc_summary_cols = [survey_id, bc_col]

    if summary_col:
        if summary_col == backchecker:
            summary_cols = [
                c
                for c in backcheck_data.columns
                if backchecker in c and c not in bc_summary_cols
            ]
            bc_summary_cols.extend(
                [c for c in summary_cols if c not in bc_summary_cols]
            )

        else:
            summary_cols = [c for c in survey_data.columns if summary_col in c]
            svy_summary_cols.extend(summary_cols)

    # Remove duplicates while preserving order for consistency
    svy_summary_cols = list(dict.fromkeys(svy_summary_cols))
    bc_summary_cols = list(dict.fromkeys(bc_summary_cols))

    # Check if required columns exist before proceeding
    missing_survey_cols = [
        col for col in svy_summary_cols if col not in survey_data.columns
    ]
    missing_backcheck_cols = [
        col for col in bc_summary_cols if col not in backcheck_data.columns
    ]

    if missing_survey_cols or missing_backcheck_cols:
        # Return empty DataFrame if required columns are missing
        return pd.DataFrame()

    # Get data for columns
    survey_col_data = survey_data[svy_summary_cols]
    backcheck_col_data = backcheck_data[bc_summary_cols]

    # Merge datasets with error handling
    if survey_col_data.empty or backcheck_col_data.empty:
        return pd.DataFrame()

    try:
        merged_df = pd.merge(
            survey_col_data, backcheck_col_data, on=survey_id, how="inner"
        )
    except KeyError:
        # Handle case where survey_id column doesn't exist
        return pd.DataFrame()
    else:
        return merged_df


def _handle_missing_values(
    svy_val: Any, bc_val: Any, comparison_condition: str
) -> str | None:
    """Handle missing value comparison."""
    if (
        pd.isna(svy_val) or pd.isna(bc_val)
    ) and comparison_condition == IGNORE_MISSING_VALUES:
        return "not_compared"
    return None


def _handle_excluded_values(
    svy_val: Any, bc_val: Any, comparison_condition: str
) -> str | None:
    """Handle excluded value comparison."""
    if DO_NOT_COMPARE_VALUES in str(comparison_condition):
        with suppress(IndexError):
            exclude_values = comparison_condition.split(":")[1].strip().split(",")
            exclude_values = [val.strip() for val in exclude_values]
            if (
                str(svy_val).strip() in exclude_values
                or str(bc_val).strip() in exclude_values
            ):
                return "not_compared"
    return None


def _handle_same_values(
    svy_val: Any, bc_val: Any, comparison_condition: str
) -> str | None:
    """Handle values to be treated as same."""
    if TREAT_VALUES_AS_SAME in str(comparison_condition):
        with suppress(IndexError):
            same_values = comparison_condition.split(":")[1].strip().split(",")
            same_values = [val.strip() for val in same_values]
            svy_str = str(svy_val).strip()
            bc_str = str(bc_val).strip()
            if svy_str in same_values and bc_str in same_values:
                return "not_different"
    return None


def _compare_numeric_values(svy_val: Any, bc_val: Any, ok_range: str) -> str | None:
    """Compare numeric values within specified range."""
    try:
        svy_num = float(svy_val)
        bc_num = float(bc_val)
        diff = abs(svy_num - bc_num)

        if "%" in ok_range:
            percentage = float(ok_range.replace("%", ""))
            if svy_num != 0:
                allowed_diff = (percentage / 100) * abs(svy_num)
                return "not_different" if diff <= allowed_diff else "different"
        elif "[" in ok_range:
            range_vals = ok_range.strip("[]").split(",")
            if len(range_vals) == 2:
                min_val, max_val = (
                    float(range_vals[0].strip()),
                    float(range_vals[1].strip()),
                )
                return "not_different" if min_val <= diff <= max_val else "different"
        else:
            allowed_diff = float(ok_range)
            return "not_different" if diff <= allowed_diff else "different"
    except (ValueError, TypeError):
        # If numeric conversion fails, mark as not_compared
        return "not_compared"
    return None


def _compare_values(
    row: pd.Series, svy_col: str, bc_col: str, ok_range: str, comparison_condition: str
) -> str:
    """Compare values based on conditions and ranges."""
    svy_val = row[svy_col]
    bc_val = row[bc_col]

    # Check each comparison type in sequence
    result = _handle_missing_values(svy_val, bc_val, comparison_condition)
    if result:
        return result

    if comparison_condition:
        result = _handle_excluded_values(svy_val, bc_val, comparison_condition)
        if result:
            return result

        result = _handle_same_values(svy_val, bc_val, comparison_condition)
        if result:
            return result

    if ok_range:
        result = _compare_numeric_values(svy_val, bc_val, ok_range)
        if result:
            return result

    # Default string comparison
    return (
        "not_different" if str(svy_val).strip() == str(bc_val).strip() else "different"
    )


def _calculate_column_summary_stats(
    merged_df: pd.DataFrame,
    column_name: str,
    column_type: int,
    survey_col_data: pd.Series,
    summary_col: str | None,
) -> list[dict[str, Any]]:
    """Calculate summary statistics for a column.

    Parameters
    ----------
    merged_df : pd.DataFrame
        Merged comparison data.
    column_name : str
        Name of the column being analyzed.
    column_type : int
        Category type of the column.
    survey_col_data : pd.Series
        Survey column data for type detection.
    summary_col : str | None
        Column to group by, if any.

    Returns
    -------
    list[dict[str, Any]]
        List of summary statistics dictionaries.
    """
    # More comprehensive data type mapping
    data_types_dict = {
        "float64": "Numeric",
        "float32": "Numeric",
        "int64": "Numeric",
        "int32": "Numeric",
        "int16": "Numeric",
        "int8": "Numeric",
        "object": "String",
        "string": "String",
        "category": "String",
        "datetime64[ns]": "Date",
        "datetime64[ns, UTC]": "Date",
        "bool": "Boolean",
    }
    data_type = data_types_dict.get(str(survey_col_data.dtype), "String")

    summary_data = []

    if summary_col and not merged_df.empty:
        # Find matching summary column
        matching_cols = [col for col in merged_df.columns if summary_col in col]
        if matching_cols:
            summary_col_name = matching_cols[0]
            # Create a copy to avoid modifying original dataframe
            df_grouped = merged_df.rename(columns={summary_col_name: summary_col})

            # Group by summary column and compute stats
            for group_name, group_df in df_grouped.groupby(summary_col, dropna=False):
                stats = _compute_group_stats(
                    group_df, df_grouped, summary_col, group_name
                )
                summary_data.append(
                    {
                        "column": column_name,
                        "data type": data_type,
                        "category": column_type,
                        summary_col: group_name,
                        **stats,
                    }
                )

    if not summary_data:  # No grouping or no matching columns
        # Overall statistics
        stats = _compute_overall_stats(merged_df)
        summary_data.append(
            {
                "column": column_name,
                "data type": data_type,
                "category": column_type,
                **stats,
            }
        )

    return summary_data


def _compute_group_stats(
    group_df: pd.DataFrame, merged_df: pd.DataFrame, summary_col: str, group_name: Any
) -> dict[str, Any]:
    """Compute statistics for a specific group.

    Parameters
    ----------
    group_df : pd.DataFrame
        Group-specific data.
    merged_df : pd.DataFrame
        Full merged dataset.
    summary_col : str
        Column name for grouping.
    group_name : Any
        Value of the group.

    Returns
    -------
    dict[str, Any]
        Group statistics.
    """
    total_surveys = (merged_df[summary_col] == group_name).sum()
    total_backchecks = len(group_df)

    # Use vectorized operations for better performance
    comparison_mask = group_df["comparison_result"] != "not_compared"
    total_compared = comparison_mask.sum()
    total_different = (group_df["comparison_result"] == "different").sum()

    error_rate = (total_different / total_compared * 100) if total_compared > 0 else 0

    return {
        "# surveys": total_surveys,
        "# backchecks": total_backchecks,
        "# compared": total_compared,
        "# different": total_different,
        "error rate": f"{error_rate:.2f}%",
    }


def _compute_overall_stats(merged_df: pd.DataFrame) -> dict[str, Any]:
    """Compute overall statistics.

    Parameters
    ----------
    merged_df : pd.DataFrame
        Merged comparison data.

    Returns
    -------
    dict[str, Any]
        Overall statistics dictionary.
    """
    if merged_df.empty:
        return {
            "# surveys": 0,
            "# backchecks": 0,
            "# compared": 0,
            "# different": 0,
            "error rate": "0.00%",
        }

    # Use vectorized operations for better performance
    total_compared = (merged_df["comparison_result"] != "not_compared").sum()
    total_different = (merged_df["comparison_result"] == "different").sum()
    error_rate = (total_different / total_compared * 100) if total_compared > 0 else 0

    return {
        "# surveys": len(merged_df),
        "# backchecks": len(merged_df),
        "# compared": total_compared,
        "# different": total_different,
        "error rate": f"{error_rate:.2f}%",
    }


def display_category_error_rates(column_category_summary: pd.DataFrame) -> None:
    """Display error rates for each backcheck category.

    Parameters
    ----------
    column_category_summary : pd.DataFrame
        Summary data for all categories.
    """
    for category in [1, 2, 3]:
        category_summary = column_category_summary[
            column_category_summary["category"] == category
        ]
        if category_summary.shape[0] > 0:
            st.write(f"Backcheck category {category} error rates")
            col1, col2, col3 = st.columns(3)

            category_error_rate = (
                category_summary["# different"].sum()
                / category_summary["# compared"].sum()
            ) * 100

            col1.metric(
                f"Number of category {category} columns",
                len(category_summary["column"].unique()),
            )
            col2.metric(
                f"Number of category {category} values compared",
                category_summary["# compared"].sum(),
            )
            col3.metric(
                f"% of category {category} error rate",
                f"{category_error_rate:.0f}%",
            )
            st.write("")


def display_overview_charts(
    total_backchecks: int,
    backcheck_goal: int,
    num_enumerators_bc: int,
    total_enumerators: int,
) -> None:
    """Display overview charts for backcheck progress.

    Parameters
    ----------
    total_backchecks : int
        Total number of backchecks completed.
    backcheck_goal : int
        Target number of backchecks.
    num_enumerators_bc : int
        Number of enumerators who met backcheck target.
    total_enumerators : int
        Total number of enumerators.
    """
    cl1, _, cl3 = st.columns(3)
    chart_colors = ["#35904A", "lightgrey"]

    with cl1:
        if backcheck_goal == 0:
            st.warning("Please set a target for backchecks")
        else:
            # Create donut chart for backcheck progress
            fig = px.pie(
                names=["Backchecked", "Not backchecked"],
                values=[total_backchecks, backcheck_goal - total_backchecks],
                hole=0.6,
                title="% of surveys backchecked",
            )
            fig.update_layout(
                width=400,
                height=350,
                showlegend=False,
                title=dict(
                    xanchor="left",
                    y=0.9,
                    yanchor="top",
                    font=dict(weight="normal"),
                ),
            )
            fig.update_traces(
                textinfo="none",
                marker=dict(colors=chart_colors),
                direction="clockwise",
            )
            fig.add_annotation(
                dict(
                    text=f"{(total_backchecks / backcheck_goal) * 100:.0f}%",
                    x=0.5,
                    y=0.5,
                    font_size=30,
                    showarrow=False,
                )
            )
            st.plotly_chart(fig)

    with cl3:
        # Create pie chart for enumerator backcheck coverage
        if total_enumerators == 0:
            st.write("**% of enumerators backchecked**")
            st.info(
                "Percentage of enumerators backchecked requires an enumerator column. Go to :material/settings: settings above."
            )
        else:
            fig_enum = px.pie(
                names=["Backchecked", "Not backchecked"],
                values=[num_enumerators_bc, total_enumerators - num_enumerators_bc],
                hole=0.6,
                title="% of enumerators backchecked",
            )
            fig_enum.update_layout(
                width=400,
                height=350,
                showlegend=False,
                title=dict(
                    xanchor="left", y=0.9, yanchor="top", font=dict(weight="normal")
                ),
            )
            fig_enum.update_traces(
                textinfo="none",
                marker=dict(colors=chart_colors),
                direction="clockwise",
            )
            fig_enum.add_annotation(
                dict(
                    text=f"{(num_enumerators_bc / total_enumerators) * 100:.0f}%",
                    x=0.5,
                    y=0.5,
                    font_size=30,
                    showarrow=False,
                )
            )
            st.plotly_chart(fig_enum)


@demo_output_onboarding(TAB_NAME)
def display_error_trends(
    error_trends_summary: pd.DataFrame,
    date: str,
) -> None:
    """Display error trends over time.

    Parameters
    ----------
    error_trends_summary : pd.DataFrame
        Error trends data.
    date : str
        Date column name.
    """
    if error_trends_summary.empty:
        st.write("Error Trends")
        st.info(NO_BACKCHECK_COLUMNS_SET)
        return

    st.subheader("Error Trends")
    trend_cols = st.columns([2, 1])

    date_columns = [col for col in error_trends_summary if date in col]
    if not date_columns:
        st.info(
            "No matching date columns found in the data. Please check your date column name."
        )
        return

    date_col = date_columns[0]
    category_list = error_trends_summary["category"].unique().tolist()

    error_trends_summary[date_col] = pd.to_datetime(error_trends_summary[date_col])

    with trend_cols[0]:
        selected_categories = st.multiselect(
            "Select backcheck categories",
            options=category_list,
            default=category_list,
            key="trend_categories",
        )

    with trend_cols[1]:
        time_period_options = ["Daily"]
        if error_trends_summary[date_col].dt.to_period("W-SUN").nunique() > 1:
            time_period_options.append("Weekly")
        if error_trends_summary[date_col].dt.to_period("M").nunique() > 1:
            time_period_options.append("Monthly")

        time_period = st.selectbox(
            "Select time period",
            options=time_period_options,
            key="time_period",
        )

    if selected_categories:
        trends_df = error_trends_summary[
            error_trends_summary["category"].isin(selected_categories)
        ].copy()
        trends_df["date"] = pd.to_datetime(trends_df[date_col])

        # Filter based on time period
        if time_period == "Weekly":
            trends_df["date"] = trends_df["date"].dt.to_period("W-SUN").dt.start_time
        elif time_period == "Monthly":
            trends_df["date"] = trends_df["date"].dt.to_period("M").astype(str)
        else:
            trends_df["date"] = trends_df["date"].dt.date

        # Calculate error rates
        error_trends_df = (
            trends_df.groupby(["date", "category"])
            .aggregate({"# compared": "sum", "# different": "sum"})
            .reset_index()
        )
        error_trends_df["error_rate"] = (
            error_trends_df["# different"] / error_trends_df["# compared"]
        ) * 100
        error_trends_df["error_rate"] = error_trends_df["error_rate"].fillna(0).round(0)

        # Create line chart
        fig = px.line(
            error_trends_df,
            x="date",
            y="error_rate",
            color="category",
            title=f"{time_period} Error Rate Trends by Category",
            labels={
                "date": "Date",
                "error_rate": "Error Rate (%)",
                "category": "Category",
            },
        )
        fig.update_layout(
            xaxis_title="Date",
            yaxis_title="Error Rate (%)",
            hovermode="x unified",
        )
        st.plotly_chart(fig, width="stretch")


def _display_filtered_statistics(
    stats_df: pd.DataFrame,
    title: str,
    filter_column: str,
    filter_label: str,
    staff_type: str | None = None,
) -> None:
    """Display statistics table with filtering capability."""
    st.subheader(title)

    if stats_df.empty:
        st.info(NO_BACKCHECK_COLUMNS_SET)
        return

    if staff_type and staff_type not in stats_df.columns:
        st.info(
            f"{title} require a {staff_type.lower()} column. "
            "Go to :material/settings: settings above to select the appropriate column."
        )
        return

    # Filter functionality
    selected_items = st.multiselect(
        filter_label,
        stats_df[filter_column].unique() if filter_column in stats_df.columns else [],
    )

    if selected_items and filter_column in stats_df.columns:
        filtered_stats = stats_df[stats_df[filter_column].isin(selected_items)]
    else:
        filtered_stats = stats_df

    st.dataframe(filtered_stats, width="stretch", hide_index=True)


@demo_output_onboarding(TAB_NAME)
def display_statistics_tables(
    enumerator_statistics: pd.DataFrame,
    backchecker_statistics: pd.DataFrame,
    comparison_df: pd.DataFrame,
    enumerator: str | None,
    backchecker: str | None,
) -> None:
    """Display enumerator, backchecker, and comparison statistics."""
    # Enumerator Statistics
    _display_filtered_statistics(
        enumerator_statistics,
        "Enumerator Statistics",
        "Enumerator"
        if "Enumerator" in enumerator_statistics.columns
        else enumerator or "",
        "Filter enumerators:",
        "Enumerator",
    )

    # Backchecker Statistics
    _display_filtered_statistics(
        backchecker_statistics,
        "Backchecker Statistics",
        "Back Checker",
        "Filter back checkers:",
        "Back Checker",
    )
    st.write("")

    # Comparison Details
    _display_filtered_statistics(
        comparison_df,
        "Comparison Details",
        "variable",
        "Select variables to display:",
    )


@demo_output_onboarding(TAB_NAME)
def display_column_stats(column_stats: pd.DataFrame) -> None:
    """Display column statistics table.

    Parameters
    ----------
    column_stats : pd.DataFrame
        DataFrame containing column statistics.
    """
    if column_stats.empty:
        st.info(NO_BACKCHECK_COLUMNS_SET)
    else:
        st.dataframe(column_stats, width="stretch", hide_index=True)


@demo_output_onboarding(TAB_NAME)
def backchecks_report(
    project_id: str,
    page_name_id: str,
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    setting_file: str,
    config: dict,
) -> None:
    """
    Generate and display backchecks report.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    survey_data : pl.DataFrame
        Survey data.
    backcheck_data : pl.DataFrame
        Backcheck data.
    setting_file : str
        Path to the settings file.
    config : dict
        Configuration dictionary.
    """
    st.title("Backchecks Report")

    # Convert Polars DataFrames to Pandas for compatibility
    survey_data_pd = survey_data.to_pandas()
    backcheck_data_pd = backcheck_data.to_pandas()

    # Get column information for settings UI
    (
        _,
        survey_string_columns,
        survey_numeric_columns,
        survey_datetime_columns,
        _,
    ) = get_df_info(survey_data, cols_only=True)

    (
        _,
        backcheck_string_columns,
        backcheck_numeric_columns,
        backcheck_datetime_columns,
        _,
    ) = get_df_info(backcheck_data, cols_only=True)

    # Combine string and numeric columns for categorical options
    survey_categorical_columns = list(
        set(survey_string_columns + survey_numeric_columns)
    )
    backcheck_categorical_columns = list(
        set(backcheck_string_columns + backcheck_numeric_columns)
    )

    # Configure settings
    config_settings = BackcheckSettings(**config)
    _settings = backchecks_report_settings(
        project_id,
        setting_file,
        survey_data_pd,
        backcheck_data_pd,
        config_settings,
        survey_categorical_columns,
        survey_datetime_columns,
        backcheck_categorical_columns,
        backcheck_datetime_columns,
    )

    # Outlier columns configuration
    st.subheader("Backchecks Columns Configuration")
    common_columns = list(
        set(survey_categorical_columns).intersection(
            set(backcheck_categorical_columns)
        )
    )
    _render_backchecks_column_actions(project_id, page_name_id, survey_data, backcheck_data, common_columns)


