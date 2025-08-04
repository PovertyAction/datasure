import os
from contextlib import suppress
from typing import Any

import pandas as pd
import plotly.express as px
import streamlit as st

from datasure.utils import (
    get_check_config_settings,
    load_check_settings,
    save_check_settings,
    trigger_save,
)

IGNORE_MISSING_VALUES = "ignore_missing_values"
DO_NOT_COMPARE_VALUES = "Do not compare if the values contain:"
TREAT_VALUES_AS_SAME = "Treat these values as the same:"
NO_BACKCHECK_COLUMNS_SET = "Backcheck columns configuration required. Go to the :material/settings: settings section above and configure backcheck columns."


##### Backchecks #####


@st.cache_data
def load_default_backcheck_settings(
    project_id: str, setting_file: str | None, page_num: int
) -> tuple:
    """Load default settings for backcheck report.

    Parameters
    ----------
    project_id : str
        Project ID.
    setting_file : str
        Path to the settings file.
    page_num : int
        Page number for the report.

    Returns
    -------
    tuple
        Default settings for backcheck report.
    """
    # Get config page defaults
    (
        _,
        _,
        config_survey_key,
        config_survey_id,
        config_survey_date,
        config_enumerator,
        _,
        _,
    ) = get_check_config_settings(
        project_id=project_id,
        page_row_index=page_num - 1,
    )

    if setting_file and os.path.exists(setting_file):
        with suppress(Exception):
            default_settings = (
                load_check_settings(settings_file=setting_file, check_name="backchecks")
                or {}
            )
        if "default_settings" not in locals():
            default_settings = {}
    else:
        default_settings = {}

    return (
        default_settings.get("date", config_survey_date),
        default_settings.get("enumerator", config_enumerator),
        default_settings.get("backchecker"),
        default_settings.get("survey_id", config_survey_id),
        default_settings.get("survey_key", config_survey_key),
        default_settings.get("backcheck_goal", 0),
        default_settings.get("drop_duplicates", True),
    )


def _create_selectbox_with_save(
    label: str,
    options: list,
    help_text: str,
    key: str,
    default_value: str | None,
    setting_file: str,
    setting_key: str,
    session_state_key: str,
) -> str:
    """Create a selectbox with automatic save functionality.

    Consolidates the common pattern of selectbox creation with settings persistence.
    """
    default_index = None
    if default_value and default_value in options:
        with suppress(ValueError):
            default_index = options.index(default_value)

    selected = st.selectbox(
        label,
        options=options,
        help=help_text,
        key=key,
        index=default_index,
        on_change=trigger_save,
        kwargs={"state_name": session_state_key},
    )

    if st.session_state.get(session_state_key):
        with suppress(Exception):
            save_check_settings(
                settings_file=setting_file,
                check_name="backchecks",
                check_settings={setting_key: selected},
            )
        st.session_state[session_state_key] = False

    return selected


def _handle_meta_settings(
    survey_cols: pd.Index, date: str | None, setting_file: str
) -> str:
    """Handle metadata column settings."""
    return _create_selectbox_with_save(
        label="Date",
        options=survey_cols.tolist(),
        help_text="Column containing survey date",
        key="date_backcheck",
        default_value=date,
        setting_file=setting_file,
        setting_key="date",
        session_state_key="backcheck_date",
    )


def _handle_enum_settings(
    survey_cols: pd.Index,
    backcheck_cols_list: pd.Index,
    enumerator: str | None,
    backchecker: str | None,
    setting_file: str,
) -> tuple[str, str]:
    """Handle enumerator column settings."""
    enumerator = _create_selectbox_with_save(
        label="Enumerator",
        options=survey_cols.tolist(),
        help_text="Column containing survey enumerator",
        key="enumerator_backcheck",
        default_value=enumerator,
        setting_file=setting_file,
        setting_key="enumerator",
        session_state_key="backcheck_enumerator",
    )

    backchecker = _create_selectbox_with_save(
        label="Back Checker",
        options=backcheck_cols_list.tolist(),
        help_text="Column containing back check enumerator",
        key="backchecker_backcheck",
        default_value=backchecker,
        setting_file=setting_file,
        setting_key="backchecker",
        session_state_key="backcheck_backchecker",
    )

    return enumerator, backchecker


def _handle_agg_settings(
    survey_cols: pd.Index,
    survey_id: str | None,
    survey_key: str | None,
    setting_file: str,
) -> tuple[str, str]:
    """Handle aggregation column settings."""
    survey_id = _create_selectbox_with_save(
        label="Survey ID (required)",
        options=survey_cols.tolist(),
        help_text="Column containing survey ID",
        key="surveyid_backcheck",
        default_value=survey_id,
        setting_file=setting_file,
        setting_key="survey_id",
        session_state_key="backcheck_survey_id",
    )

    survey_key = _create_selectbox_with_save(
        label="Survey Key (required)",
        options=survey_cols.tolist(),
        help_text="Column containing survey key",
        key="surveykey_backcheck",
        default_value=survey_key,
        setting_file=setting_file,
        setting_key="survey_key",
        session_state_key="backcheck_survey_key",
    )

    return survey_id, survey_key


def _handle_tracking_options(
    setting_file: str,
    backcheck_goal: int,
    drop_duplicates: bool,
    date: str | None,
    survey_id: str | None,
) -> tuple[int, bool]:
    """Handle tracking options settings.

    Parameters
    ----------
    setting_file : str
        Path to settings file.
    backcheck_goal : int
        Current backcheck goal value.
    drop_duplicates : bool
        Current drop duplicates setting.
    date : str | None
        Date column selection.
    survey_id : str | None
        Survey ID column selection.

    Returns
    -------
    tuple[int, bool]
        Selected backcheck goal and drop duplicates setting.
    """
    backcheck_goal = st.number_input(
        "Target number of backchecks",
        min_value=0,
        help="Total number of backchecks expected",
        key="total_goal_backcheck",
        value=backcheck_goal,
        on_change=trigger_save,
        kwargs={"state_name": "backcheck_goal"},
    )
    if "backcheck_goal" in st.session_state and st.session_state.backcheck_goal:
        with suppress(Exception):
            save_check_settings(
                settings_file=setting_file,
                check_name="backchecks",
                check_settings={"backcheck_goal": backcheck_goal},
            )
        st.session_state.backcheck_goal = False

    st.write("How would you like to handle duplicates?")
    drop_duplicates = st.toggle(
        label="Drop duplicates",
        value=drop_duplicates,
        key="drop_duplicates_backcheck",
        on_change=trigger_save,
        kwargs={"state_name": "backcheck_drop_duplicates"},
    )
    if drop_duplicates and (not date or not survey_id):
        st.info(
            "Please select date and survey id columns to drop duplicates correctly."
        )

    if (
        "backcheck_drop_duplicates" in st.session_state
        and st.session_state.backcheck_drop_duplicates
    ):
        with suppress(Exception):
            save_check_settings(
                settings_file=setting_file,
                check_name="backchecks",
                check_settings={"drop_duplicates": drop_duplicates},
            )
        st.session_state.backcheck_drop_duplicates = False
    return backcheck_goal, drop_duplicates


def _get_ok_range_value(ok_range_type: str) -> str:
    """Get the OK range value based on the selected type."""
    if ok_range_type == "absolute value":
        absolute_ok_range = st.number_input(
            label="Absolute Value", min_value=0, help="Enter the absolute value"
        )
        return f"{absolute_ok_range}"
    elif ok_range_type == "percentage":
        ok_range_percentage = st.number_input(
            "Percentage", min_value=0, help="Enter a percentage value"
        )
        return f"{ok_range_percentage}%"
    elif ok_range_type == "range":
        range_min = st.number_input(
            "Minimum Value",
            max_value=0,
            help="Enter the minimum value (less than zero)",
        )
        range_max = st.number_input(
            "Maximum Value",
            min_value=0,
            help="Enter the maximum value (greater than zero)",
        )
        return f"[{range_min} , {range_max}]"
    return ""


def _get_comparison_condition(compare_condition: str) -> str:
    """Get the comparison condition based on the selected option."""
    if compare_condition == "Do not compare if the values contain:":
        contains_condition = st.text_input(
            "Enter values not to compare separated by a comma",
            help="Values not to compare if they contain these values",
        )
        return f"{compare_condition}: {contains_condition}"
    elif compare_condition == "Treat these values as the same:":
        same_condition = st.text_input(
            "Enter values separated by a comma",
            help="Enter values separated by a comma",
        )
        return f"{compare_condition}: {same_condition}"
    elif compare_condition == "Do not compare missing values or null values":
        return "ignore_missing_values"
    return ""


def _handle_column_configuration(common_cols: list[str]) -> pd.DataFrame:
    """Handle backcheck column configuration settings."""
    st.write("---")
    st.markdown("#### Backcheck Columns Configuration")

    # Initialize session state for table data if not already present
    if "column_config_data" not in st.session_state:
        st.session_state.column_config_data = pd.DataFrame(
            columns=["column", "category", "ok_range", "comparison_condition"]
        )

    # Display the table and allow user interaction
    with st.popover(
        "Add a backcheck column", icon=":material/add:", use_container_width=True
    ):
        column_name = st.selectbox(
            "column",
            options=common_cols,
            help="Select a column to configure",
            key="column",
        )
        column_type = st.selectbox(
            "category",
            options=[1, 2, 3],
            help="Select the backcheck category of the column",
            key="category",
        )
        ok_range_type = st.selectbox(
            "ok_range",
            options=["None", "absolute value", "range", "percentage"],
            help="Select the type of range condition",
            key="ok_range",
        )
        ok_range = _get_ok_range_value(ok_range_type)

        compare_condition = st.selectbox(
            label="comparison_condition",
            options=[
                "None",
                "Do not compare missing values or null values",
                "Do not compare if the values contain:",
                "Treat these values as the same:",
            ],
            help="Specify any additional conditions",
            key="comparison_condition",
        )
        comparison_condition = _get_comparison_condition(compare_condition)

        if st.button("Add Column"):
            new_row = {
                "column": column_name,
                "category": column_type,
                "ok_range": ok_range,
                "comparison_condition": comparison_condition,
            }
            st.session_state.column_config_data = pd.concat(
                [st.session_state.column_config_data, pd.DataFrame([new_row])],
                ignore_index=True,
            )

    # Create an editable dataframe
    return st.data_editor(
        st.session_state.column_config_data,
        num_rows="dynamic",
        use_container_width=True,
    )


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


def _display_overview_section(
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
    st.subheader("Overview")
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


def _display_category_and_trends(
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
        st.write("Backcheck category summary")
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


def backcheck_report_settings(
    project_id: str,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    setting_file: str,
    page_num: int,
) -> tuple:
    """Load settings for backcheck report.

    Parameters
    ----------
    project_id : str
        Project ID.
    survey_data : pd.DataFrame
        Survey data.
    backcheck_data : pd.DataFrame
        Backcheck data.
    setting_file : str
        Path to the settings file.
    page_num : int
        Page number for the report.

    Returns
    -------
    tuple
        Settings for backcheck report.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for backcheck report")

        survey_cols = survey_data.columns
        backcheck_cols_list = backcheck_data.columns
        # Use set intersection for better performance
        common_cols = list(set(survey_data.columns) & set(backcheck_cols_list))

        settings = load_default_backcheck_settings(project_id, setting_file, page_num)
        (
            date,
            enumerator,
            backchecker,
            survey_id,
            survey_key,
            backcheck_goal,
            drop_duplicates,
        ) = settings

        agg_col, enum_col, meta_col = st.columns(spec=3, border=True)

        with meta_col:
            date = _handle_meta_settings(survey_cols, date, setting_file)

        with enum_col:
            enumerator, backchecker = _handle_enum_settings(
                survey_cols, backcheck_cols_list, enumerator, backchecker, setting_file
            )

        with agg_col:
            survey_id, survey_key = _handle_agg_settings(
                survey_cols, survey_id, survey_key, setting_file
            )

        st.write("---")
        st.markdown("#### Tracking Options")
        backcheck_goal, drop_duplicates = _handle_tracking_options(
            setting_file, backcheck_goal, drop_duplicates, date, survey_id
        )

        # Add column configuration section
        bc_column_config_df = _handle_column_configuration(common_cols)

        st.write("")

    return (
        date,
        enumerator,
        backchecker,
        survey_id,
        survey_key,
        backcheck_goal,
        drop_duplicates,
        common_cols,
        bc_column_config_df,
    )


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
        st.plotly_chart(fig, use_container_width=True)


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

    st.dataframe(filtered_stats, use_container_width=True, hide_index=True)


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


def backchecks_report(
    project_id: str,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    setting_file: str,
    page_num: int,
) -> None:
    """Create a backcheck report for a given survey and backcheck data.

    This function orchestrates the entire backcheck report generation process
    by coordinating settings, data processing, analysis, and display.

    Parameters
    ----------
    project_id : str
        Project ID for the backcheck report.
    survey_data : pd.DataFrame
        Survey data to be used for backcheck report.
    backcheck_data : pd.DataFrame
        Backcheck data to be used for backcheck report.
    setting_file : str
        Path to the settings file.
    page_num : int
        Page number for the backcheck report.
    """
    # Get settings and configuration
    (
        date,
        enumerator,
        backchecker,
        survey_id,
        survey_key,
        backcheck_goal,
        drop_duplicates,
        common_cols,
        bc_column_config_df,
    ) = backcheck_report_settings(
        project_id, survey_data, backcheck_data, setting_file, page_num
    )

    # Validate requirements
    if not _validate_backcheck_requirements(survey_key, survey_id, backcheck_data):
        return

    # Process duplicates if requested
    if drop_duplicates and survey_id and date:
        survey_data, backcheck_data = process_duplicate_data(
            survey_data, backcheck_data, survey_id, date, drop_duplicates
        )

    # Prepare merged dataframes
    merged_df = _prepare_merged_dataframes(
        survey_data, backcheck_data, survey_id, enumerator, backchecker, date
    )

    # Get the individual survey and backcheck dataframes for overview calculations
    survey_cols_for_merge = _get_merge_columns([survey_id], enumerator, date)
    survey_df_bc = survey_data[survey_cols_for_merge].add_prefix("_svy_")
    survey_df_bc.rename(columns={"_svy_" + survey_id: survey_id}, inplace=True)

    backcheck_cols_for_merge = _get_merge_columns([survey_id], backchecker, date)
    backcheck_df_bc = backcheck_data[backcheck_cols_for_merge].add_prefix("_bc_")
    backcheck_df_bc.rename(columns={"_bc_" + survey_id: survey_id}, inplace=True)

    # Generate column summaries and comparison data
    column_category_summary, svy_bc_comparison_df = _generate_backcheck_summaries(
        bc_column_config_df,
        survey_data,
        backcheck_data,
        survey_id,
        enumerator,
        backchecker,
    )

    # Display overview section
    _display_overview_section(
        survey_df_bc, backcheck_df_bc, merged_df, enumerator, backcheck_goal
    )

    # Display category error rates and trends
    _display_category_and_trends(
        bc_column_config_df,
        column_category_summary,
        survey_data,
        backcheck_data,
        survey_id,
        enumerator,
        backchecker,
        date,
    )

    # Display column statistics
    if bc_column_config_df.empty:
        st.write("Column Statistics")
        st.info(NO_BACKCHECK_COLUMNS_SET)
    else:
        st.subheader("Column Statistics")
        st.dataframe(column_category_summary, use_container_width=True, hide_index=True)

    st.write("")

    # Generate and display statistics
    enumerator_statistics = _generate_enumerator_statistics(
        bc_column_config_df,
        survey_data,
        backcheck_data,
        survey_id,
        enumerator,
        backchecker,
    )

    backchecker_statistics = _generate_backchecker_statistics(
        bc_column_config_df,
        survey_data,
        backcheck_data,
        survey_id,
        enumerator,
        backchecker,
    )

    # Display statistics tables
    display_statistics_tables(
        enumerator_statistics=enumerator_statistics,
        backchecker_statistics=backchecker_statistics,
        comparison_df=svy_bc_comparison_df,
        enumerator=enumerator,
        backchecker=backchecker,
    )

    st.write("")
