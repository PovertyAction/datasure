"""Report-rendering UI for the enumerator performance report."""

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date as dt_date
from typing import Literal

import polars as pl
import streamlit as st

from datasure.checks.enumerator.attention import (
    REVIEW_RESPONSE_PATTERNS,
    AttentionList,
    AttentionRow,
    ColumnRoles,
    LeftOut,
    OtherChecks,
    Severity,
    attention_rows,
    attention_totals,
    counted_interviews,
    format_minutes,
    missing_column,
    row_label,
    shown_rows,
    submissions_by_enumerator,
    unattributed_notes,
)
from datasure.checks.enumerator.compute import (
    COMPLETED_FLAG,
    CONSENT_FLAG,
    DISPLAY_DATE_FORMAT,
    add_consent_outcome_flags,
    compute_enumerator_missing_shares,
    compute_enumerator_productivity,
    compute_enumerator_statistics,
    compute_enumerator_statistics_overtime,
    compute_enumerator_summary,
    compute_latest_submission_date,
    compute_overview_figures,
    count_active_enumerators,
)
from datasure.checks.enumerator.models import (
    ALLOWED_STATISTICS,
    ALLOWED_STATISTICS_OVERTIME,
    TAB_NAME,
    WEEKDAY_NAMES,
    WEEKDAY_OFFSET_MAP,
    ConsentOutcomeSettings,
    EnumeratorSettings,
    StatisticsOvertimeSettings,
    StatisticsSettings,
)
from datasure.checks.enumerator.response_patterns.models import (
    ResponsePatternResults,
)
from datasure.checks.enumerator.response_patterns.report_ui import (
    cached_response_patterns,
    render_response_patterns,
)
from datasure.checks.enumerator.response_patterns.settings_ui import (
    load_response_pattern_settings,
)
from datasure.checks.enumerator.settings_ui import (
    enumerator_report_settings,
    load_default_enumerator_settings,
)
from datasure.checks.headline import CheckHeadline, EnumeratorScope
from datasure.utils.dataframe_utils import ColumnByType
from datasure.utils.duckdb_utils import load_missing_codes_from_db
from datasure.utils.navigation import READY, CheckStatus, StatusResult
from datasure.utils.navigations_utils import demo_callout
from datasure.utils.onboarding_utils import DemoColumn
from datasure.utils.settings_utils import load_check_settings
from datasure.utils.ui_utils import metric_row, section_header
from datasure.utils.view_state import (
    ViewState,
    bind_widget,
    reset_filters_beside,
    view_factory,
)

logger = logging.getLogger(__name__)

# Saved view state scope: the check's catalogue slug. The report's periods,
# columns and statistics are personal view state; older versions saved them in
# the check's settings and they move on first load. Both week start pickers
# saved under "weekstartday"; the statistics over time one was saved last.
VIEW_SCOPE = "enumerator"
check_view = view_factory(
    VIEW_SCOPE,
    legacy=(
        TAB_NAME,
        {
            "time_period_enumerator_productivity_key": "time_period",
            "selected_columns_enumerator": "statscols",
            "statistics_options_enumerator": "stats",
            "project_enumerator_statistics_overtime_period_pills": "period_overtime",
            "project_week_start_day_enumerator_overtime": "weekstartday",
            "enumerator_statistics_overtime_stat": "stat",
            "enumerator_statistics_overtime_column": "statscol",
        },
    ),
)

# The page's period, week start and team, which every section uses. Older
# versions had a period and week start in Productivity and in Statistics
# Over Time; `_adopt_shared_controls` moves them here, Productivity's first.
PERIOD_KEY = "period"
WEEK_START_KEY = "week_start"
TEAM_KEY = "team"
_LEGACY_PERIOD_KEYS = (
    "time_period_enumerator_productivity_key",
    "project_enumerator_statistics_overtime_period_pills",
)
_LEGACY_WEEK_START_KEYS = (
    "week_start_day_enumerator_productivity_key",
    "project_week_start_day_enumerator_overtime",
)
PERIODS = {"Day": "Daily", "Week": "Weekly", "Month": "Monthly"}
ALL_TEAMS = "All teams"
EN_DASH = "\N{EN DASH}"

# Enumerators listed under "Needs attention" before the rest fold away.
ATTENTION_SHOWN = 10
# The "Needs attention" toggles for each severity, saved as view state.
SHOW_FLAGGED_KEY = "attention_show_flagged"
SHOW_WATCH_KEY = "attention_show_watch"

# =============================================================================
# Display Functions - Overview
# =============================================================================


def _md(text: object) -> str:
    """Escape Markdown in a value shown in Markdown, such as a name."""
    return re.sub(r"([\\`*_\[\]<>|~$#])", r"\\\1", str(text))


def _render_overview(
    data: pl.DataFrame, settings: EnumeratorSettings, team: str | None = None
) -> None:
    """Show the four overview figures, each with what it is compared with.

    Active enumerators out of all, the past 7 days' submissions against the
    7 days before, the median submissions per enumerator with who has the
    fewest and the most, and the median interview length with its middle
    half (or the teams, without a duration column). ``team`` is the team
    the data is narrowed to, if any, which the active figure's help names.
    """
    active_help = "Enumerators with a submission dated in the 7 days up to today"
    if team is None:
        active_help += ", as on Summary's Enumerator Stats row"
    else:
        active_help += (
            f" in team {team}. Summary's Enumerator Stats row counts every team"
        )
    figures = compute_overview_figures(
        data,
        settings.survey_date,
        settings.enumerator,
        settings.team,
        settings.duration,
        settings.duration_unit,
    )
    fewest_name, fewest = figures.fewest
    most_name, most = figures.most
    row: list[tuple] = [
        (
            "Active in the past 7 days",
            f"{figures.num_active:,}",
            active_help,
            f"of {figures.num_enumerators:,} enumerators",
        ),
        (
            "Submissions in the past 7 days",
            f"{figures.submissions_past_week:,}",
            "Submissions dated in the 7 days up to today",
            f"{figures.submissions_week_before:,} in the 7 days before",
        ),
        (
            "Submissions per enumerator",
            f"{figures.median_per_enumerator:,.0f}",
            "The median of each enumerator's total submissions. Fewest: "
            f"{fewest_name} ({fewest:,}). Most: {most_name} ({most:,}).",
            f"Range {fewest:,} to {most:,}",
        ),
    ]
    if figures.duration_minutes is not None:
        low, median, high = figures.duration_minutes
        row.append(
            (
                "Interview length",
                format_minutes(median),
                "The median interview length over all submissions",
                f"Middle half {format_minutes(low)}{EN_DASH}{format_minutes(high)}",
            )
        )
    elif figures.num_teams is not None:
        row.append(("Teams", f"{figures.num_teams:,}", "Teams in the data"))
    else:
        row.append(("Submissions", f"{data.height:,}", "Submissions in the data"))
    metric_row(row)


def _render_data_line(data: pl.DataFrame, settings: EnumeratorSettings) -> None:
    """Say how recent the data is and what it covers."""
    parts = []
    if settings.survey_date:
        latest = compute_latest_submission_date(data, settings.survey_date)
        if latest is not None:
            parts.append(f"Data as of **{latest.strftime(DISPLAY_DATE_FORMAT)}**")
    covered = (
        f"{data.height:,} submissions from "
        f"{data[settings.enumerator].n_unique():,} enumerators"
    )
    if settings.team and settings.team in data.columns:
        covered += f" in {data[settings.team].n_unique():,} teams"
    parts.append(covered)
    st.caption(" · ".join(parts))


def _render_columns_in_use(
    settings: EnumeratorSettings, consent: ConsentOutcomeSettings
) -> None:
    """Say which columns the report uses and which are not set."""
    roles = (
        ("Enumerator", settings.enumerator),
        ("Date", settings.survey_date),
        ("Team", settings.team),
        ("Duration", settings.duration),
        ("Form version", settings.formversion),
        ("Consent", consent.consent if consent.consent_vals else None),
        ("Outcome", consent.outcome if consent.outcome_vals else None),
    )
    used = [f"{label.lower()} **{_md(column)}**" for label, column in roles if column]
    unset = [label.lower() for label, column in roles if not column]
    text = f"Using {', '.join(used)}." if used else "No columns selected yet."
    if unset:
        text += (
            f" Not set: {', '.join(unset)}. Set them in the :material/settings: "
            "settings above to add their numbers and flags."
        )
    st.caption(text)


@dataclass(frozen=True)
class PageControls:
    """The period, week start and team every section of the report uses."""

    period: Literal["Day", "Week", "Month"]
    weekstartday: str
    team: str | None


def _adopt_shared_controls(view: ViewState) -> None:
    """Move the period and week start each section once had to the page's.

    Productivity and Statistics Over Time each kept their own; the page
    now has one of each. Productivity's choice wins, as it came first on
    the page. The file is only written when something moves.
    """
    saved = view.values()
    for key, legacy_keys in (
        (PERIOD_KEY, _LEGACY_PERIOD_KEYS),
        (WEEK_START_KEY, _LEGACY_WEEK_START_KEYS),
    ):
        found = [saved[legacy] for legacy in legacy_keys if legacy in saved]
        if key not in saved and found:
            view.save(key, found[0])
        if found:
            view.forget(*legacy_keys)


def _render_page_controls(
    settings_file: str, data: pl.DataFrame, team: str | None
) -> PageControls:
    """Draw the page's period, week start and team; return the choices.

    Saved as view state, so they survive switching checks and new sessions.
    """
    view = check_view(settings_file)
    _adopt_shared_controls(view)
    with st.container(horizontal=True, vertical_alignment="bottom"):
        period = st.segmented_control(
            "Period",
            options=list(PERIODS),
            format_func=PERIODS.get,
            help="How the productivity and statistics over time tables group "
            "submissions",
            **view.bind(PERIOD_KEY, options=list(PERIODS), default="Week"),
        )
        period = period or "Week"
        week_start = "Monday"
        if period == "Week":
            week_start = st.selectbox(
                "Week starts on",
                options=WEEKDAY_NAMES,
                width=180,
                **view.bind(
                    WEEK_START_KEY,
                    options=WEEKDAY_NAMES,
                    index=WEEKDAY_NAMES.index("Monday"),
                ),
            )
        chosen_team = None
        if team and team in data.columns:
            teams = sorted(data[team].drop_nulls().cast(pl.String).unique().to_list())
            options = [ALL_TEAMS, *teams]
            chosen = st.selectbox(
                "Team",
                options=options,
                width=220,
                help="Show one team only. Its enumerators are then compared "
                "with the rest of that team.",
                **view.bind(TEAM_KEY, options=options, index=0),
            )
            chosen_team = None if chosen in (None, ALL_TEAMS) else chosen
    week_start_code = WEEKDAY_OFFSET_MAP.get(week_start, WEEKDAY_OFFSET_MAP["Monday"])
    return PageControls(period, week_start_code, chosen_team)


def _severity_badge(severity: Severity) -> str:
    color = "red" if severity is Severity.FLAG else "orange"
    return f":{color}-badge[{severity.value}]"


def _render_attention_row(row: AttentionRow, label: str) -> None:
    """Draw one enumerator's reasons in a bordered row."""
    with st.container(border=True):
        name_col, reasons_col = st.columns([1, 3], vertical_alignment="center")
        with name_col:
            st.markdown(f"**{_md(row.enumerator)}**")
            team = f"Team {_md(row.team)}" if row.team else ""
            st.caption(" · ".join(x for x in (team, label) if x))
        with reasons_col:
            st.markdown(
                "\n".join(
                    f"- {_severity_badge(reason.severity)} **{reason.check}**: "
                    f"{_md(reason.finding)}"
                    for reason in row.reasons
                )
            )


def _rules_in_use(
    settings: EnumeratorSettings,
    summary: pl.DataFrame,
    patterns: ResponsePatternResults | None,
    other: OtherChecks,
) -> list[str]:
    """Name what the list was built from, for the caption under it."""
    names = []
    if settings.survey_date:
        names.append("activity")
    if settings.duration:
        names.append("interview length")
    if missing_column(summary.columns):
        names.append("missing answers")
    if "% consent" in summary.columns:
        names.append("consent")
    if "% completed survey" in summary.columns:
        names.append("completion")
    if settings.formversion and settings.survey_date:
        names.append("form version")
    if patterns is not None and patterns.condition is None:
        names.append("response patterns")
    for issues in other.counts:
        if issues.check.lower() not in names:
            names.append(issues.check.lower())
    return names


def _plural(count: int, singular: str, plural: str) -> str:
    return f"{count:,} {singular if count == 1 else plural}"


def _render_attention_metrics(rows: list[AttentionRow], in_view: int) -> None:
    """Show how many enumerators have Flagged and Watch reasons, and how many."""
    totals = attention_totals(rows)
    metric_row(
        [
            (
                "Flagged enumerators",
                f"{totals.flagged:,}",
                "Enumerators with at least one Flagged reason, worth reviewing "
                "now. One who also has Watch reasons counts under both.",
                _plural(totals.flags, "flag", "flags"),
            ),
            (
                "Watch enumerators",
                f"{totals.watched:,}",
                "Enumerators with at least one Watch reason, worth keeping an "
                "eye on. One who also has Flagged reasons counts under both.",
                _plural(totals.watches, "watch reason", "watch reasons"),
            ),
            (
                "Enumerators listed",
                f"{totals.listed:,}",
                "Enumerators with any reason, each listed once",
                f"of {_plural(in_view, 'enumerator', 'enumerators')}",
            ),
        ]
    )


def _render_severity_toggles(setting_file: str) -> tuple[bool, bool]:
    """Draw the Show Flagged and Show Watch toggles; return their states.

    Saved as view state, like the page's team, and on by default.
    """
    view = check_view(setting_file)
    with st.container(horizontal=True):
        flagged = st.toggle(
            "Show Flagged",
            help="List the reasons worth reviewing now",
            **view.bind(SHOW_FLAGGED_KEY, value=True),
        )
        watch = st.toggle(
            "Show Watch",
            help="List the reasons worth keeping an eye on",
            **view.bind(SHOW_WATCH_KEY, value=True),
        )
    return bool(flagged), bool(watch)


def _render_needs_attention(
    attention: AttentionList,
    rules: list[str],
    other: OtherChecks,
    setting_file: str,
    in_view: int,
) -> None:
    """Draw the enumerators the checks single out, most flags first.

    Metrics count every reason; the toggles under them choose which
    severities the list shows. Each rule or check in ``attention.left_out``
    is named under the list with its reason, and left out of the "Checked"
    caption. ``in_view`` is the enumerators in the data shown.
    """
    rows = attention.rows
    section_header("Needs attention", icon=":material/flag:")
    demo_callout(
        """
        ##### Needs attention
        Each enumerator another check singles out, most flags first. A
        **Flagged** reason is worth reviewing now; **Watch** is worth keeping
        an eye on. Reasons compare the enumerator with the rest of the team,
        and come from this page (activity, interview length, missing answers,
        consent, form version, response patterns) and from Duplicates,
        Outliers, GPS and Backchecks when they are set up. Use **Show
        Flagged** and **Show Watch** to list only one kind.
        """
    )
    if not rows:
        st.success(
            "No enumerator stands out on the checks listed below.",
            icon=":material/check_circle:",
        )
    else:
        _render_attention_metrics(rows, in_view)
        show_flagged, show_watch = _render_severity_toggles(setting_file)
        shown = shown_rows(rows, flagged=show_flagged, watch=show_watch)
        if not (show_flagged or show_watch):
            st.info(
                "Turn on Show Flagged or Show Watch to see enumerators.",
                icon=":material/visibility_off:",
            )
        elif not shown:
            kind = "Flagged" if show_flagged else "Watch"
            st.info(f"No enumerator has a {kind} reason.", icon=":material/info:")
        for row in shown[:ATTENTION_SHOWN]:
            _render_attention_row(row, row_label(row))
        rest = shown[ATTENTION_SHOWN:]
        if rest:
            with st.expander(f"{len(rest):,} more"):
                for row in rest:
                    _render_attention_row(row, row_label(row))
    failed = {item.check.lower() for item in attention.left_out}
    checked = [rule for rule in rules if rule not in failed]
    if checked:
        st.caption(f"Checked: {', '.join(checked)}.")
    for note in unattributed_notes(other.counts):
        st.caption(note)
    for item in attention.left_out:
        st.error(item.message, icon=":material/error:")


def _list_patterns(
    data: pl.DataFrame,
    setting_file: str,
    enumerator: str,
    missing_codes: pl.DataFrame | None,
) -> tuple[ResponsePatternResults | None, tuple[LeftOut, ...]]:
    """Return Response Patterns' results for the list, or why there are none."""
    try:
        return cached_response_patterns(
            data,
            load_response_pattern_settings(setting_file),
            enumerator,
            missing_codes,
        ), ()
    # UI boundary: Response Patterns failing must not stop the list. The
    # error is shown under the "Needs attention" list by
    # _render_needs_attention (deferred display, see CONTRIBUTING "Error
    # Handling Conventions").
    except Exception as exc:
        logger.exception("Could not compute response patterns for the list")
        return None, (
            LeftOut.from_exception("Response patterns", exc, REVIEW_RESPONSE_PATTERNS),
        )


@st.fragment
def _render_enumerator_summary_table(
    summary_df: pl.DataFrame,
    enumerator: str,
    team: str | None,
    view: ViewState | None = None,
    today: dt_date | None = None,
) -> None:
    """Display the enumerator summary table.

    The summary information chosen is saved to ``view``.

    Parameters
    ----------
    summary_df : pl.DataFrame
        ``compute_enumerator_summary`` on the report's data.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).
    view : ViewState | None
        Where the chosen information is saved.
    today : date | None
        The day "today", "this week" and "this month" count from, for the
        caption. Defaults to the system clock.
    """
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
            help="Select which summary information to display in the table",
            selection_mode="multi",
            **bind_widget(
                view, "show_info_enumerator", options=list(options_map), multi=True
            ),
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
            # Rates from 0 to 1; "percent" shows 0.94 as 94%.
            "% consent": st.column_config.NumberColumn("% Consent", format="percent"),
            "% completed survey": st.column_config.NumberColumn(
                "% Completed", format="percent"
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

    today = today or dt_date.today()
    st.caption(
        "Today, this week and this month count from today's date "
        f"({today.strftime(DISPLAY_DATE_FORMAT)})."
    )


# =============================================================================
# Display Functions - Productivity
# =============================================================================


def _render_enumerator_productivity(
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    controls: PageControls,
) -> None:
    """Display submissions per enumerator in each period of the page's period.

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
    controls : PageControls
        The page's period and week start.
    """
    group_by_cols = [enumerator, team] if team else [enumerator]
    productivity_df = compute_enumerator_productivity(
        data, date, group_by_cols, controls.period, controls.weekstartday
    )

    column_config = {
        enumerator: st.column_config.TextColumn("Enumerator", pinned=True),
    }
    if team:
        column_config[team] = st.column_config.TextColumn("Team", pinned=True)
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


# =============================================================================
# Display Functions - Statistics
# =============================================================================


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
        if data[col].dtype.is_numeric() and col not in exclude_cols
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
        Path to the page settings file holding the view state.

    Returns
    -------
    list[str]
        Selected columns.
    """
    selected_cols = st.multiselect(
        label="Columns",
        options=numeric_cols,
        help="Select columns to include in statistics",
        **check_view(settings_file).bind(
            "selected_columns_enumerator",
            options=numeric_cols,
            multi=True,
            default=default_cols,
        ),
    )
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
        Path to the page settings file holding the view state.

    Returns
    -------
    list[str]
        Selected statistics.
    """
    selected_stats = st.multiselect(
        "Statistics",
        options=ALLOWED_STATISTICS,
        help="Select statistics to calculate",
        **check_view(settings_file).bind(
            "statistics_options_enumerator",
            options=ALLOWED_STATISTICS,
            multi=True,
            default=default_stats,
        ),
    )
    return selected_stats


@st.fragment
def _render_enumerator_statistics_table(
    data: pl.DataFrame,
    enumerator: str,
    team: str | None,
    settings_file: str,
    missing_codes: pl.DataFrame | None = None,
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
    missing_codes : pl.DataFrame | None
        The project's missing codes, counted as missing in the statistics.
    """
    # Widget defaults; the user's choices are saved view state
    settings = StatisticsSettings()

    # Build exclusion list for numeric columns
    exclude_cols = [enumerator, CONSENT_FLAG, COMPLETED_FLAG]
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
            missing_codes=missing_codes,
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
            "Select one or more columns to see their statistics.",
            icon=":material/info:",
        )


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
        Path to the page settings file holding the view state.

    Returns
    -------
    str
        Selected statistic.
    """
    stat = st.selectbox(
        label="Statistic",
        options=ALLOWED_STATISTICS_OVERTIME,
        help="Select statistic to calculate over time",
        **check_view(settings_file).bind(
            "enumerator_statistics_overtime_stat",
            options=ALLOWED_STATISTICS_OVERTIME,
            index=ALLOWED_STATISTICS_OVERTIME.index(default_stat),
        ),
    )
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
        Path to the page settings file holding the view state.

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
        label="Column",
        options=numeric_cols,
        help="Select column to include in statistics",
        **check_view(settings_file).bind(
            "enumerator_statistics_overtime_column",
            options=numeric_cols,
            index=default_col_index,
        ),
    )
    return statscol


@st.fragment
def _render_enumerator_statistics_overtime_table(
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    settings_file: str,
    controls: PageControls,
    missing_codes: pl.DataFrame | None = None,
) -> None:
    """Display one statistic of one column per enumerator, period by period.

    The periods are the page's (``controls``); the column and statistic are
    chosen here and saved as view state.

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
        Path to the page settings file holding the view state.
    controls : PageControls
        The page's period and week start.
    missing_codes : pl.DataFrame | None
        The project's missing codes, counted as missing in the statistics.
    """
    # Widget defaults; the user's choices are saved view state
    settings = StatisticsOvertimeSettings()

    # Build exclusion list for numeric columns
    exclude_cols = [enumerator, CONSENT_FLAG, COMPLETED_FLAG]
    if team:
        exclude_cols.append(team)

    numeric_cols = _get_numeric_columns(data, exclude_cols=exclude_cols)

    col1, col2 = st.columns(2)

    with col1:
        statscol = _render_column_selector_single(
            numeric_cols, settings.statscol, settings_file
        )

    with col2:
        stat = _render_statistic_selector(settings.stat, settings_file)

    # Compute and display statistics
    if statscol:
        group_by_cols = [enumerator, team] if team else [enumerator]
        stats_overtime_df = compute_enumerator_statistics_overtime(
            data=data,
            date=date,
            group_by_cols=group_by_cols,
            statscol=statscol,
            stat=stat,
            period=controls.period,
            weekstartday=controls.weekstartday,
            missing_codes=missing_codes,
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
            "Select a column to see its statistic over time.", icon=":material/info:"
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
    other_checks: Callable[[EnumeratorScope], OtherChecks] | None = None,
) -> None:
    """Draw the enumerator report, the enumerators needing attention first.

    In order: the settings and the columns in use; the page's period, week
    start and team; four overview figures; the enumerators that need
    attention and why; the summary table; productivity; column statistics;
    statistics over time; and response patterns.

    Parameters
    ----------
    project_id : str
        Unique project identifier for configuration lookup.
    data : pl.DataFrame
        Dataset containing survey data to analyze.
    setting_file : str
        Path to the page's settings file.
    config : dict
        The page configuration the check starts from.
    survey_columns : ColumnByType
        The survey data's columns by type.
    other_checks : Callable[[EnumeratorScope], OtherChecks] | None
        Returns, for the page's enumerator column and chosen team, the
        outstanding issues other checks on the page count by enumerator,
        which the "Needs attention" list adds. None leaves them out.
    """
    st.title("Enumerator Report")

    demo_callout(
        """
        This check tracks each enumerator's work and points to who needs a
        closer look.

        - **Needs attention** lists the enumerators other checks single out,
          with each reason in plain words.
        - The **Period** and **Team** controls apply to every section.
        - The summary, productivity and statistics tables below give the
          detail.

        **Start here**: Open the :material/settings: settings panel above to
        confirm your column selections and set the consent and outcome
        settings.
        """
    )

    if data.is_empty():
        st.info(
            "No data available for the enumerator report. "
            "Please upload data to proceed."
        )
        return

    with reset_filters_beside(check_view(setting_file)):
        settings = enumerator_report_settings(
            setting_file,
            data,
            EnumeratorSettings(**config),
            survey_columns.categorical_columns,
            survey_columns.datetime_columns,
        )
    _render_columns_in_use(settings, consent_outcome_settings(setting_file))

    enumerator, survey_date = settings.enumerator, settings.survey_date
    if not enumerator:
        st.info(
            "Select the enumerator column in the :material/settings: settings "
            "above to see this report.",
            icon=":material/info:",
        )
        return
    if not survey_date:
        st.info(
            "Select the survey date column in the :material/settings: settings "
            "above to see the overview, the summary, productivity and "
            "statistics over time.",
            icon=":material/info:",
        )

    controls = _render_page_controls(setting_file, data, settings.team)
    report_data = enumerator_report_data(data, setting_file)
    if controls.team is not None:
        report_data = report_data.filter(
            pl.col(settings.team).cast(pl.String) == controls.team
        )
    _render_data_line(report_data, settings)

    if survey_date:
        demo_callout(
            """
            ##### Overview
            Four figures, each with what it compares with: active enumerators
            out of all, the past 7 days' submissions against the 7 days
            before, submissions per enumerator with the fewest and the most,
            and the median interview length.
            """
        )
        _render_overview(report_data, settings, controls.team)

    # Missing codes such as -99 are missing, not values, in the statistics
    missing_codes = load_missing_codes_from_db(project_id)
    summary_df = (
        compute_enumerator_summary(
            project_id,
            report_data,
            survey_date,
            enumerator,
            settings.team,
            settings.formversion,
            settings.duration,
        )
        if survey_date
        else pl.DataFrame()
    )
    patterns, patterns_failed = _list_patterns(
        report_data, setting_file, enumerator, missing_codes
    )
    scope = EnumeratorScope(enumerator, settings.team, controls.team)
    other = other_checks(scope) if other_checks else OtherChecks()
    roles = ColumnRoles(
        enumerator,
        settings.team,
        survey_date,
        settings.duration,
        settings.duration_unit,
        settings.formversion,
        CONSENT_FLAG if CONSENT_FLAG in report_data.columns else None,
        COMPLETED_FLAG if COMPLETED_FLAG in report_data.columns else None,
    )
    counted, narrowed = counted_interviews(report_data, roles)
    attention = attention_rows(
        report_data,
        roles,
        summary_df,
        patterns,
        other.counts,
        compute_enumerator_missing_shares(
            counted, enumerator, settings.team, missing_codes
        )
        if narrowed and survey_date
        else None,
    )
    _render_needs_attention(
        replace(
            attention,
            left_out=(*other.errors, *patterns_failed, *attention.left_out),
        ),
        _rules_in_use(settings, summary_df, patterns, other),
        other,
        setting_file,
        len(submissions_by_enumerator(report_data, enumerator)),
    )

    if survey_date:
        st.divider()
        section_header("Enumerator summary", icon=":material/table_view:")
        demo_callout(
            """
            ##### Enumerator summary
            Use the pills above the table to choose what it shows:
            - **Submissions**: first and last submission dates, submission
              counts (total, today, this week, this month) and days worked.
            - **Missing Data**: the share of missing answers.
            - **Duration**: shortest, longest, mean and median interview.
            - **Form Version**: the form versions each enumerator used.
            - **Consent & Outcome**: consent and completed survey rates.
            """
        )
        _render_enumerator_summary_table(
            summary_df, enumerator, settings.team, check_view(setting_file)
        )

        st.divider()
        section_header("Productivity", icon=":material/calendar_month:")
        st.caption("Submissions per enumerator in each period.")
        _render_enumerator_productivity(
            report_data, survey_date, enumerator, settings.team, controls
        )

    st.divider()
    section_header("Column statistics", icon=":material/functions:")
    demo_callout(
        f"""
        ##### Column statistics
        Choose one or more numeric **Columns** and the **Statistics** to show
        for each enumerator (count, mean, median, min, max, std, 25th and 75th
        percentiles).

        ##### Instructions for Demo:
        Select **{DemoColumn.HOUSEHOLD_COUNT}** as the column and choose
        **count**, **mean**, **min** and **max** to check whether enumerators
        are recording consistent household sizes.
        """
    )
    _render_enumerator_statistics_table(
        report_data, enumerator, settings.team, setting_file, missing_codes
    )

    if survey_date:
        st.divider()
        section_header("Statistics over time", icon=":material/timeline:")
        demo_callout(
            f"""
            ##### Statistics over time
            A table of one statistic of one column for each enumerator,
            period by period, using the page's **Period**. Choose the
            **Column** and the **Statistic** (for example mean, count or
            missing).

            ##### Instructions for Demo:
            Select **{DemoColumn.HOUSEHOLD_COUNT}** as the column and **mean**
            as the statistic, then set the page's period to **Weekly** to see
            whether average household size varies by enumerator over time.
            """
        )
        _render_enumerator_statistics_overtime_table(
            report_data,
            survey_date,
            enumerator,
            settings.team,
            setting_file,
            controls,
            missing_codes,
        )

    render_response_patterns(report_data, setting_file, settings, missing_codes)

    demo_callout(
        "**Next**: :material/arrow_upward: Scroll up and select **Field team → Backchecks**."
    )


def enumerator_status(setting_file: str, config: dict) -> StatusResult:
    """Return the enumerator check's status for the check page navigation.

    The check is not set up without an enumerator column and a survey date
    column, saved in its settings or set on the Configure Checks page.
    """
    settings = {**config, **load_check_settings(setting_file, TAB_NAME)}
    missing = [
        label
        for key, label in (
            ("enumerator", "an enumerator column"),
            ("survey_date", "a survey date column"),
        )
        if not settings.get(key)
    ]
    if missing:
        return StatusResult(
            CheckStatus.NOT_SET_UP,
            f"Select {' and '.join(missing)} in the settings below.",
        )
    return READY


def consent_outcome_settings(setting_file: str) -> ConsentOutcomeSettings:
    """Return the consent and outcome settings saved in the page's settings file."""
    return ConsentOutcomeSettings(
        **{
            key: value
            for key, value in load_check_settings(setting_file, TAB_NAME).items()
            if key in ConsentOutcomeSettings.model_fields
        }
    )


def enumerator_report_data(data: pl.DataFrame, setting_file: str) -> pl.DataFrame:
    """Return the data the report uses, with the page's consent and outcome flags.

    The flags come from the consent and outcome settings saved in the page's
    settings file, so the report reflects them as soon as they change and
    after every data refresh.

    Parameters
    ----------
    data : pl.DataFrame
        The page's survey data.
    setting_file : str
        Path to the page's settings file.

    Returns
    -------
    pl.DataFrame
        ``data`` with the consent and completed-survey flags that are set up.
    """
    settings = consent_outcome_settings(setting_file)
    return add_consent_outcome_flags(
        data,
        settings.consent,
        tuple(settings.consent_vals or ()),
        settings.outcome,
        tuple(settings.outcome_vals or ()),
    )


def enumerator_headline(
    project_id: str,
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
    today: dt_date | None = None,
) -> CheckHeadline | None:
    """Return the enumerator headline for Summary's check health row.

    The active enumerators (past 7 days) out of all enumerators, counted by
    `count_active_enumerators` as the overview's "Active in the past 7 days"
    is, so the two agree with the Team filter on All teams. Informational:
    the check has no flagged-enumerator count, so the headline does not
    invent one.

    Parameters
    ----------
    project_id : str
        The project identifier.
    data : pl.DataFrame
        The survey data.
    setting_file : str
        Path to the page's settings file.
    config : dict
        The page configuration the check starts from.
    today : date | None
        The day "active in the past 7 days" counts back from, for the
        enumerators active as of the comparison period start. Defaults to
        the system clock.

    Returns
    -------
    CheckHeadline | None
        For example "4 / 12" active in the past 7 days, or None when the
        enumerator or survey date column is not set or there is no data.
    """
    settings = load_default_enumerator_settings(
        setting_file, EnumeratorSettings(**config)
    )
    if not (settings.enumerator and settings.survey_date) or data.is_empty():
        return None
    counted = count_active_enumerators(
        data, settings.survey_date, settings.enumerator, today
    )
    return CheckHeadline(
        f"{counted.active:,} / {counted.total:,}",
        "active in the past 7 days",
        informational=True,
        count=counted.active,
    )
