"""Report-rendering UI for the enumerator performance report."""

from typing import Literal

import polars as pl
import streamlit as st

from datasure.checks.enumerator.compute import (
    compute_enumerator_overview,
    compute_enumerator_productivity,
    compute_enumerator_statistics,
    compute_enumerator_statistics_overtime,
    compute_enumerator_summary,
)
from datasure.checks.enumerator.models import (
    ALLOWED_STATISTICS,
    ALLOWED_STATISTICS_OVERTIME,
    TAB_NAME,
    WEEKDAY_NAMES,
    WEEKDAY_OFFSET_MAP,
    EnumeratorOverviewMetrics,
    EnumeratorSettings,
    StatisticsOvertimeSettings,
    StatisticsSettings,
)
from datasure.checks.enumerator.settings_ui import enumerator_report_settings
from datasure.utils.dataframe_utils import ColumnByType
from datasure.utils.duckdb_utils import duckdb_get_table
from datasure.utils.navigations_utils import demo_callout
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

# =============================================================================
# Display Functions - Overview
# =============================================================================


def _render_enumerator_overview_metrics(
    data: pl.DataFrame, date: str, enumerator: str, team: str | None
) -> None:
    """Display enumerator overview metrics.

    Shows key metrics including total submissions, active enumerators,
    team counts, and submission statistics in a grid layout.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).
    """
    if not (enumerator and date):
        st.info(
            "Enumerator overview requires a date and enumerator column to be selected. "
            "Go to the :material/settings: settings section above to select them."
        )
        return

    metrics: EnumeratorOverviewMetrics = compute_enumerator_overview(
        data, date, enumerator, team
    )

    tc1, tc2, tc3, tc4 = st.columns(4, border=True)
    num_enumerators_formatted = (
        f"{metrics.num_enumerators:,}"
        if isinstance(metrics.num_enumerators, int)
        else metrics.num_enumerators
    )
    tc1.metric(
        r"\# of enumerators",
        num_enumerators_formatted,
        help="Total unique enumerators in the dataset",
    )
    num_teams_formatted = (
        f"{metrics.num_teams:,}"
        if isinstance(metrics.num_teams, int)
        else metrics.num_teams
    )
    tc2.metric(
        r"\# of teams", num_teams_formatted, help="Total unique teams in the dataset"
    )
    num_active_enumerators_formatted = f"{metrics.num_active_enumerators:,}"
    tc3.metric(
        r"\# of Active enumerators (past 7 days)",
        num_active_enumerators_formatted,
        help="Number of enumerators with submissions in the past 7 days",
    )
    pct_active_enumerators_formatted = f"{metrics.pct_active_enumerators}"
    tc4.metric(
        "% of active enumerator (past 7 days)",
        pct_active_enumerators_formatted,
        help="Percentage of enumerators active in the past 7 days",
    )

    bc1, bc2, bc3, bc4 = st.columns(4, border=True)
    min_submissions_formatted = f"{metrics.min_submissions:,}"
    bc1.metric(
        "Fewest enumerator submissions",
        min_submissions_formatted,
        help="Minimum number of submissions by any enumerator",
    )
    max_submissions_formatted = f"{metrics.max_submissions:,}"
    bc2.metric(
        "Highest enumerator submissions",
        max_submissions_formatted,
        help="Maximum number of submissions by any enumerator",
    )
    avg_submissions_formatted = f"{metrics.avg_submissions:,}"
    bc3.metric(
        "Average enumerator submissions",
        avg_submissions_formatted,
        help="Average number of submissions per enumerator",
    )
    all_submissions_formatted = f"{metrics.all_submissions:,}"
    bc4.metric(
        "Total survey submissions",
        all_submissions_formatted,
        help="Total number of survey submissions in the dataset",
    )


@st.fragment
def _render_enumerator_summary_table(
    project_id: str,
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    formversion: str | None,
    duration: str | None,
) -> None:
    """Display enumerator summary table.

    Shows comprehensive enumerator statistics including submission counts,
    duration, missing data, consent rates, and outcome rates with styled
    formatting.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    missing_settings_file : str
        Path to missing codes configuration file.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    formdef_version : str | None
        Form version column name (optional).
    duration : str | None
        Duration column name (optional).
    consent : str | None
        Consent column name (optional).
    consent_vals : list[str] | None
        Valid consent values (optional).
    outcome : str | None
        Outcome column name (optional).
    outcome_vals : list[str] | None
        Completed survey values (optional).
    """
    if not (enumerator and date):
        st.info(
            "Enumerator summary requires a date and enumerator column to be selected. "
            "Go to the :material/settings: settings section above to select them."
        )
        return

    summary_df = compute_enumerator_summary(
        project_id,
        data,
        date,
        enumerator,
        team,
        formversion,
        duration,
    )

    options_map = {
        "submissions": ":material/arrow_upload_progress: Submissions",
        "missing": ":material/incomplete_circle: Missing Data",
        "duration": ":material/timer: Duration",
        "formversion": ":material/difference: Form Version",
        "consent_outcome": ":material/check_circle: Consent & Outcome",
    }
    with st.container(horizontal_alignment="left"):
        show_info = st.pills(
            "Select Summary Information to Display",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            key="show_info_enumerator",
            help="Select which summary information to display in the table",
            selection_mode="multi",
        )

    # Define column groups
    column_groups = {
        "submissions": [
            "first submission",
            "last submission",
            "# submissions",
            "# unique dates",
            "# submissions today",
            "# submissions this week",
            "# submissions this month",
        ],
        "missing": [
            col
            for col in summary_df.columns
            if "%" in col
            and (
                "Null" in col
                or "Missing" in col
                or any(
                    keyword in col
                    for keyword in ["Don't Know", "Refuse", "Not Applicable"]
                )
            )
        ],
        "duration": [
            "min duration",
            "mean duration",
            "median duration",
            "max duration",
        ],
        "formversion": [
            "# form versions",
            "latest form version",
            "last form version",
            "# of outdated form versions",
        ],
        "consent_outcome": [
            "% consent",
            "% completed survey",
        ],
    }

    # Always include enumerator and # submissions
    columns_to_show = (
        [enumerator, team, "# submissions"] if team else [enumerator, "# submissions"]
    )

    # Filter columns based on selection
    if show_info:
        # Add columns from selected categories
        for category in show_info:
            columns_to_show.extend(
                [
                    col
                    for col in column_groups[category]
                    if col in summary_df.columns and col not in columns_to_show
                ]
            )

        # Filter the dataframe
        filtered_df = summary_df.select(columns_to_show)
    else:
        # Show all columns if nothing is selected
        filtered_df = summary_df

    # Display using Streamlit's native dataframe display
    # create column config for enumerator and team conditionally
    # Build column configuration dynamically
    column_config = {
        enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
    }

    # Add team column if available
    if team:
        column_config[team] = st.column_config.TextColumn("Team", pinned=True)

    # Add remaining columns
    column_config.update(
        {
            "# submissions": st.column_config.NumberColumn(
                "# of Submissions", format="%d", pinned=True
            ),
            "# unique dates": st.column_config.NumberColumn("# of Days", format="%d"),
            "# submissions today": st.column_config.NumberColumn(
                "# submitted Today", format="%d"
            ),
            "# submissions this week": st.column_config.NumberColumn(
                "# submitted This Week", format="%d"
            ),
            "# submissions this month": st.column_config.NumberColumn(
                "# submitted This Month", format="%d"
            ),
            "% Null values": st.column_config.NumberColumn(
                "% Null Values", format="%.2f%%"
            ),
            "% Total Missing": st.column_config.NumberColumn(
                "% Total Missing", format="%.2f%%"
            ),
            "% consent": st.column_config.NumberColumn("% Consent", format="%.2f%%"),
            "% completed survey": st.column_config.NumberColumn(
                "% Completed", format="%.2f%%"
            ),
            "min duration": st.column_config.NumberColumn(
                "Min Duration (s)", format="%.2f"
            ),
            "mean duration": st.column_config.NumberColumn(
                "Mean Duration (s)", format="%.2f"
            ),
            "median duration": st.column_config.NumberColumn(
                "Median Duration (s)", format="%.2f"
            ),
            "max duration": st.column_config.NumberColumn(
                "Max Duration (s)", format="%.2f"
            ),
        }
    )

    st.dataframe(
        filtered_df,
        hide_index=True,
        width="stretch",
        column_config=column_config,
    )


# =============================================================================
# Display Functions - Productivity
# =============================================================================


def _render_enumerator_productivity(
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    settings_file: str,
) -> None:
    """Display enumerator productivity table.

    Shows submission counts by enumerator over time with configurable
    time periods (daily, weekly, monthly).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    if not (enumerator and date):
        st.info(
            "Enumerator productivity requires a date and enumerator column to be selected. "
            "Go to the :material/settings: settings section above to select them."
        )
        return

    _render_enumerator_productivity_table(data, date, enumerator, team, settings_file)


@st.fragment
def _render_enumerator_productivity_table(
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    settings_file: str,
) -> None:
    """Display enumerator productivity table.
    Shows submission counts by enumerator over time with configurable
    time periods (daily, weekly, monthly).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    time_period = _render_time_period_selector(settings_file, tab_name=TAB_NAME)
    if time_period == "Week":
        weekstartday = _render_weekday_selector(settings_file, tab_name=TAB_NAME)
    else:
        weekstartday = "MON"  # Default value, not used for non-weekly periods

    group_by_cols = [enumerator, team] if team else [enumerator]
    productivity_df = compute_enumerator_productivity(
        data, date, group_by_cols, time_period, weekstartday
    )

    if team:
        # Build column configuration dynamically
        column_config = {
            enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
            team: st.column_config.TextColumn("Team", pinned=True),
        }
    else:
        column_config = {
            enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
        }

    column_config.update(
        {
            col: st.column_config.NumberColumn(col, format="%d")
            for col in productivity_df.columns
            if col not in group_by_cols
        }
    )

    st.dataframe(
        productivity_df, hide_index=True, width="stretch", column_config=column_config
    )


def _render_time_period_selector(
    settings_file: str,
    tab_name: str = TAB_NAME,
) -> Literal["Day", "Week", "Month"]:
    """Render time period selector widget using pills interface.

    Displays a pills widget allowing users to choose the time aggregation period
    for productivity analysis (Day, Week, or Month).

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading configurations.
    tab_name : str
        Name of the tab for settings storage (default: TAB_NAME).

    Returns
    -------
    Literal["Day", "Week", "Month"]
        Selected time period.
    """
    options_map = {
        "Day": ":material/event: Daily",
        "Week": ":material/date_range: Weekly",
        "Month": ":material/calendar_month: Monthly",
    }

    saved_settings = load_check_settings(settings_file, tab_name) or {}
    default_time_period = saved_settings.get(
        "time_period_enumerator_productivity", "Day"
    )

    with st.container(horizontal_alignment="left"):
        time_period = st.pills(
            label="Time Period",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            key="time_period_enumerator_productivity_key",
            default=default_time_period,
            help="Select time period for aggregating productivity",
            selection_mode="single",
            on_change=trigger_save,
            kwargs={"state_name": tab_name + "_time_period"},
        )
        save_check_settings(settings_file, tab_name, {"time_period": time_period})

    return time_period or "Day"


def _render_weekday_selector(
    settings_file: str,
    tab_name: str = TAB_NAME,
) -> str:
    """Render weekday selector widget for productivity analysis.

    Displays a selectbox allowing users to choose the first day of the week
    for weekly productivity calculations.

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading configurations.
    tab_name : str
        Name of the tab for settings storage (default: TAB_NAME).

    Returns
    -------
    str
        Weekday offset code (e.g., "SUN", "MON") for calculations.
    """
    saved_settings = load_check_settings(settings_file, tab_name) or {}
    default_weekstartday_sel = saved_settings.get(
        "weekstartday_enumerator_productivity", "Monday"
    )
    default_weekstartday_sel_index = WEEKDAY_NAMES.index(default_weekstartday_sel)

    cl1, _ = st.columns([1, 3])
    with cl1:
        weekstartday_sel = st.selectbox(
            label="Select the first day of the week",
            options=WEEKDAY_NAMES,
            index=default_weekstartday_sel_index,
            key="week_start_day_enumerator_productivity_key",
            help="Select the first day of the week",
            on_change=trigger_save,
            kwargs={"state_name": tab_name + "_weekstartday"},
        )
    save_check_settings(settings_file, tab_name, {"weekstartday": weekstartday_sel})

    return WEEKDAY_OFFSET_MAP[weekstartday_sel]


# =============================================================================
# Display Functions - Statistics
# =============================================================================


def _load_statistics_settings(settings_file: str) -> StatisticsSettings:
    """Load and validate statistics settings from file.

    Parameters
    ----------
    settings_file : str
        Path to settings file.

    Returns
    -------
    StatisticsSettings
        Validated statistics settings.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME) or {}
    try:
        return StatisticsSettings(**saved_settings)
    except ValueError:
        # Return default settings if validation fails
        return StatisticsSettings()


def _get_numeric_columns(
    data: pl.DataFrame, exclude_cols: list[str] | None = None
) -> list[str]:
    """Extract numeric column names from DataFrame.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame to extract columns from.
    exclude_cols : list[str] | None
        Columns to exclude from the result.

    Returns
    -------
    list[str]
        List of numeric column names.
    """
    exclude_cols = exclude_cols or []
    return [
        col
        for col in data.columns
        if data[col].dtype in pl.NUMERIC_DTYPES and col not in exclude_cols
    ]


def _render_column_selector(
    numeric_cols: list[str],
    default_cols: list[str] | None,
    settings_file: str,
) -> list[str]:
    """Render column selection widget.

    Parameters
    ----------
    numeric_cols : list[str]
        Available numeric columns.
    default_cols : list[str] | None
        Default selected columns.
    settings_file : str
        Path to settings file.

    Returns
    -------
    list[str]
        Selected columns.
    """
    selected_cols = st.multiselect(
        label="Select columns:",
        options=numeric_cols,
        default=default_cols,
        help="Select columns to include in statistics",
        key="selected_columns_enumerator",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_statscols"},
    )
    save_check_settings(settings_file, TAB_NAME, {"statscols": selected_cols})
    return selected_cols


def _render_statistics_selector(
    default_stats: list[str],
    settings_file: str,
) -> list[str]:
    """Render statistics selection widget.

    Parameters
    ----------
    default_stats : list[str]
        Default selected statistics.
    settings_file : str
        Path to settings file.

    Returns
    -------
    list[str]
        Selected statistics.
    """
    selected_stats = st.multiselect(
        "Select statistics:",
        options=ALLOWED_STATISTICS,
        default=default_stats,
        help="Select statistics to calculate",
        key="statistics_options_enumerator",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_stats"},
    )
    save_check_settings(settings_file, TAB_NAME, {"stats": selected_stats})
    return selected_stats


@st.fragment
def _render_enumerator_statistics_table(
    data: pl.DataFrame,
    enumerator: str,
    team: str | None,
    settings_file: str,
) -> None:
    """Display enumerator statistics table with team support.

    Shows configurable summary statistics for selected numeric columns
    grouped by enumerator (and optionally team).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    # Validate inputs
    if not enumerator:
        st.info(
            "Enumerator statistics requires an enumerator column to be selected. "
            "Go to the :material/settings: settings section above to select it."
        )
        return

    # Load and validate settings using Pydantic
    settings = _load_statistics_settings(settings_file)

    # Build exclusion list for numeric columns
    exclude_cols = [enumerator, "consent_granted_agg_col", "completed_survey_agg_col"]
    if team:
        exclude_cols.append(team)

    numeric_cols = _get_numeric_columns(data, exclude_cols=exclude_cols)

    # Render UI in two columns
    col1, col2 = st.columns(2)

    with col1:
        statscols = _render_column_selector(
            numeric_cols, settings.statscols, settings_file
        )

    with col2:
        stats = _render_statistics_selector(settings.stats, settings_file)

    # Compute and display statistics
    if statscols:
        group_by_cols = [enumerator, team] if team else [enumerator]
        stats_df = compute_enumerator_statistics(
            data=data,
            group_by_cols=group_by_cols,
            statscols=statscols,
            stats=stats,
        )

        # Build column configuration dynamically with pinning
        if team:
            column_config = {
                enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
                team: st.column_config.TextColumn("Team", pinned=True),
            }
        else:
            column_config = {
                enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
            }

        st.dataframe(
            stats_df, hide_index=True, width="stretch", column_config=column_config
        )
    else:
        st.info(
            "No columns selected for statistics calculation.", icon=":material/info:"
        )


def _render_enumerator_statistics(
    data: pl.DataFrame,
    enumerator: str,
    team: str | None,
    settings_file: str,
) -> None:
    """Display enumerator statistics table with team support.

    Shows configurable summary statistics for selected numeric columns
    grouped by enumerator (and optionally team).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    # Validate inputs
    if not enumerator:
        st.info(
            "Enumerator statistics requires an enumerator column to be selected. "
            "Go to the :material/settings: settings section above to select it."
        )
        return

    _render_enumerator_statistics_table(
        data=data, enumerator=enumerator, team=team, settings_file=settings_file
    )


def _load_statistics_overtime_settings(
    settings_file: str,
) -> StatisticsOvertimeSettings:
    """Load and validate statistics overtime settings from file.

    Parameters
    ----------
    settings_file : str
        Path to settings file.

    Returns
    -------
    StatisticsOvertimeSettings
        Validated statistics overtime settings.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME) or {}
    try:
        return StatisticsOvertimeSettings(**saved_settings)
    except ValueError:
        # Return default settings if validation fails
        return StatisticsOvertimeSettings()


def _render_period_selector_overtime(
    settings_file: str,
    default_period: str = "Week",
) -> str:
    """Render time period selection widget.

    Parameters
    ----------
    default_period : str
        Default selected period.
    settings_file : str
        Path to settings file.

    Returns
    -------
    str
        Selected time period.
    """
    options_map = {
        "Day": ":material/event: Daily",
        "Week": ":material/date_range: Weekly",
        "Month": ":material/calendar_month: Monthly",
    }
    period = st.pills(
        label="Select Time Period:",
        options=options_map.keys(),
        format_func=lambda x: options_map[x],
        default=default_period,
        key="project_enumerator_statistics_overtime_period_pills",
        help="Select time period for aggregating statistics",
        selection_mode="single",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_period_overtime"},
    )
    save_check_settings(settings_file, TAB_NAME, {"period_overtime": period})
    return period or "Day"


def _render_weekday_selector_overtime(
    default_weekday: str,
    settings_file: str,
) -> str:
    """Render weekday selection widget (for weekly period).

    Parameters
    ----------
    default_weekday : str
        Default selected weekday.
    settings_file : str
        Path to settings file.

    Returns
    -------
    str
        Selected weekday offset code (e.g., "SUN", "MON").
    """
    default_weekday_index = WEEKDAY_NAMES.index(default_weekday)

    weekday_sel = st.selectbox(
        label="Select the first day of the week",
        options=WEEKDAY_NAMES,
        index=default_weekday_index,
        help="Select the first day of the week",
        key="project_week_start_day_enumerator_overtime",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_weekstartday_overtime"},
    )
    save_check_settings(settings_file, TAB_NAME, {"weekstartday": weekday_sel})

    return WEEKDAY_OFFSET_MAP[weekday_sel]


def _render_statistic_selector(
    default_stat: str,
    settings_file: str,
) -> str:
    """Render statistic selection widget.

    Parameters
    ----------
    default_stat : str
        Default selected statistic.
    settings_file : str
        Path to settings file.

    Returns
    -------
    str
        Selected statistic.
    """
    default_stat_index = ALLOWED_STATISTICS_OVERTIME.index(default_stat)

    stat = st.selectbox(
        label="Select statistic:",
        options=ALLOWED_STATISTICS_OVERTIME,
        index=default_stat_index,
        help="Select statistic to calculate over time",
        key="enumerator_statistics_overtime_stat",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_stat_overtime"},
    )
    save_check_settings(settings_file, TAB_NAME, {"stat": stat})
    return stat


def _render_column_selector_single(
    numeric_cols: list[str],
    default_col: str | None,
    settings_file: str,
) -> str | None:
    """Render single column selection widget.

    Parameters
    ----------
    numeric_cols : list[str]
        Available numeric columns.
    default_col : str | None
        Default selected column.
    settings_file : str
        Path to settings file.

    Returns
    -------
    str | None
        Selected column.
    """
    default_col_index = (
        numeric_cols.index(default_col)
        if default_col and default_col in numeric_cols
        else None
    )

    statscol = st.selectbox(
        label="Select column:",
        options=numeric_cols,
        index=default_col_index,
        help="Select column to include in statistics",
        key="enumerator_statistics_overtime_column",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_statscol_overtime"},
    )
    save_check_settings(settings_file, TAB_NAME, {"statscol": statscol})
    return statscol


@st.fragment
def _render_enumerator_statistics_overtime_table(
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    settings_file: str,
) -> None:
    """Display enumerator statistics over time table with team support.

    Shows how a specific statistic changes over time periods for each
    enumerator (and optionally team) with configurable time periods and statistics.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    # Validate inputs
    if not (enumerator and date):
        return

    # Load and validate settings using Pydantic
    settings = _load_statistics_overtime_settings(settings_file)

    # Build exclusion list for numeric columns
    exclude_cols = [enumerator, "consent_granted_agg_col", "completed_survey_agg_col"]
    if team:
        exclude_cols.append(team)

    numeric_cols = _get_numeric_columns(data, exclude_cols=exclude_cols)

    # Render UI in three columns
    col1, col2, col3 = st.columns([0.3, 0.2, 0.5])

    with col1:
        statscol = _render_column_selector_single(
            numeric_cols, settings.statscol, settings_file
        )

    with col2:
        stat = _render_statistic_selector(settings.stat, settings_file)

    with col3:
        period = _render_period_selector_overtime(
            settings_file, settings.period_overtime
        )
        # Conditionally render weekday selector for weekly period
        weekstartday = "SAT"  # Default
        if period == "Week":
            weekstartday = _render_weekday_selector_overtime(
                settings.weekstartday, settings_file
            )

    # Compute and display statistics
    if statscol:
        group_by_cols = [enumerator, team] if team else [enumerator]
        stats_overtime_df = compute_enumerator_statistics_overtime(
            data=data,
            date=date,
            group_by_cols=group_by_cols,
            statscol=statscol,
            stat=stat,
            period=period,
            weekstartday=weekstartday,
        )

        # Build column configuration dynamically with pinning
        if team:
            column_config = {
                enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
                team: st.column_config.TextColumn("Team", pinned=True),
            }
        else:
            column_config = {
                enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
            }

        st.dataframe(
            stats_overtime_df,
            hide_index=True,
            width="stretch",
            column_config=column_config,
        )
    else:
        st.info(
            "No column selected for statistics calculation.", icon=":material/info:"
        )


def _render_enumerator_statistics_overtime(
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    settings_file: str,
) -> None:
    """Display enumerator statistics over time table with team support.

    Shows how a specific statistic changes over time periods for each
    enumerator (and optionally team) with configurable time periods and statistics.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    # Validate inputs
    if not (enumerator and date):
        st.info(
            "Enumerator statistics over time requires a date and enumerator column to be selected. "
            "Go to the :material/settings: settings section above to select them."
        )
        return

    _render_enumerator_statistics_overtime_table(
        data=data,
        date=date,
        enumerator=enumerator,
        team=team,
        settings_file=settings_file,
    )


# =============================================================================
# Main Enumerator Report Function
# =============================================================================


def enumerator_report(
    project_id: str,
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
    survey_columns: ColumnByType,
) -> None:
    """Generate a comprehensive enumerator performance report.

    Creates a complete enumerator analysis report including:
    - Overview metrics and statistics
    - Comprehensive enumerator summary table
    - Productivity tracking over time
    - Statistical analysis across enumerators
    - Time-series analysis of performance

    Parameters
    ----------
    project_id : str
        Unique project identifier for configuration lookup.
    data : pl.DataFrame
        Dataset containing survey data to analyze.
    settings_file : str
        Path to settings file for persisting configurations.
    missing_settings_file : str
        Path to missing codes configuration file.
    page_num : int
        Page number for configuration defaults (1-indexed).
    """
    categorical_columns = survey_columns.categorical_columns
    datetime_columns = survey_columns.datetime_columns

    st.title("Enumerator Report")

    demo_callout(
        """
        This tab tracks enumerator performance across your survey dataset.

        It has four sections:
        - **Enumerator Overview**: 8 summary metrics at the top.
        - **Enumerator Summary**: Tabular breakdown by enumerator with pill-based view switching.
        - **Enumerator Productivity**: Submission counts per enumerator over time.
        - **Column Statistics by Enumerator**: Per-column statistics broken down by enumerator.
        - **Enumerator Statistics Over Time**: Time-series chart of a selected statistic.

        **Start here**: Open the :material/settings: settings panel above to confirm your column
        selections and apply consent and outcome settings.
        """
    )

    if data.is_empty():
        st.info(
            "No data available for the enumerator report. "
            "Please upload data to proceed."
        )
        return

    config_settings = EnumeratorSettings(**config)

    enumerator_settings = enumerator_report_settings(
        project_id,
        setting_file,
        data,
        config_settings,
        categorical_columns,
        datetime_columns,
    )

    # get data for enumerator report
    data_enum_report = duckdb_get_table(
        project_id,
        "enumerator_data_with_consent_outcome",
        "intermediate",
    )

    if data_enum_report.is_empty():
        data_enum_report = data

    demo_callout(
        """
        ##### Enumerator Overview
        Eight metrics appear here in two rows of four:
        - Row 1: Total enumerators, Total teams, Active enumerators (past 7 days),
          % active enumerators.
        - Row 2: Fewest submissions, Highest submissions, Average submissions,
          Total submissions.
        """
    )

    _render_enumerator_overview_metrics(
        data_enum_report,
        enumerator_settings.survey_date,
        enumerator_settings.enumerator,
        enumerator_settings.team,
    )

    st.write("---")
    st.subheader("Enumerator Summary")

    demo_callout(
        """
        ##### Enumerator Summary
        Use the pills above the table to switch between views. Each pill shows a different
        set of columns:
        - **Submissions**: First/last submission dates, submission counts (total, today,
          this week, this month), unique active days.
        - **Missing Data**: Percentage of missing values per enumerator.
        - **Duration**: Min, max, mean, and median interview duration.
        - **Form Version**: Form versions used by each enumerator.
        - **Consent & Outcome**: Consent rate and completed survey rate per enumerator.

        You can select multiple pills to see combined columns side by side.
        """
    )

    _render_enumerator_summary_table(
        project_id,
        data_enum_report,
        enumerator_settings.survey_date,
        enumerator_settings.enumerator,
        enumerator_settings.team,
        enumerator_settings.formversion,
        enumerator_settings.duration,
    )

    st.write("---")
    st.subheader("Enumerator Productivity")

    demo_callout(
        """
        ##### Enumerator Productivity
        This section shows submission counts per enumerator over time as a table.
        Use the **Daily / Weekly / Monthly** pills to change the time period granularity.
        """
    )

    _render_enumerator_productivity(
        data_enum_report,
        enumerator_settings.survey_date,
        enumerator_settings.enumerator,
        enumerator_settings.team,
        setting_file,
    )

    st.write("---")
    st.subheader("Column Statistics by Enumerator")

    demo_callout(
        """
        ##### Column Statistics by Enumerator
        Use the **column multiselect** to choose one or more numeric columns to analyse,
        then use the **statistics multiselect** to choose which statistics to display
        (count, mean, median, min, max, std, 25th percentile, 75th percentile).

        ##### Instructions for Demo:
        Select **household_size** as the column and choose **count**, **mean**, **min**,
        and **max** to check whether enumerators are recording consistent household sizes.
        """
    )

    _render_enumerator_statistics(
        data_enum_report,
        enumerator_settings.enumerator,
        enumerator_settings.team,
        setting_file,
    )

    st.write("---")
    st.subheader("Enumerator Statistics Over Time")

    demo_callout(
        """
        ##### Enumerator Statistics Over Time
        This section renders a line chart showing how a selected statistic for a chosen
        column changes over time, broken down per enumerator. Use the **column selectbox**
        to pick the variable, the **statistic selectbox** to choose the metric
        (e.g., mean, count, missing), and the **Daily / Weekly / Monthly** pills to set
        the time granularity.

        ##### Instructions for Demo:
        Select **household_size** as the column and **mean** as the statistic, then switch
        to **Weekly** to see whether average household size varies by enumerator over time.
        """
    )

    _render_enumerator_statistics_overtime(
        data_enum_report,
        enumerator_settings.survey_date,
        enumerator_settings.enumerator,
        enumerator_settings.team,
        setting_file,
    )

    demo_callout(
        "**Next**: :material/arrow_upward: Scroll up and select the **Backcheck Analysis** tab."
    )
