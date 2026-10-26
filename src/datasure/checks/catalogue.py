"""The check catalogue: every check shown on a check page.

Each entry gives a check's slug, short label, icon, group, render function,
status function and optional headline function, in display order. The check
page builds its navigation and Summary's check health rows from this
catalogue, so adding an entry here is the only change needed for a new check
to appear.
"""

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import date
from functools import partial

import polars as pl
from pydantic import ValidationError

from datasure.checks.backchecks.compute import load_default_backchecks_settings
from datasure.checks.backchecks.coverage import settings_from_page_config
from datasure.checks.backchecks.report_ui import (
    backchecks_delta,
    backchecks_headline,
    backchecks_report,
    backchecks_settings_section,
    backchecks_status,
)
from datasure.checks.context import CheckContext, CheckData
from datasure.checks.descriptive import descriptive_report
from datasure.checks.duplicates import (
    duplicates_headline,
    duplicates_report,
    duplicates_resolved_since,
    duplicates_status,
)
from datasure.checks.enumerator.report_ui import (
    enumerator_headline,
    enumerator_report,
    enumerator_status,
)
from datasure.checks.gpschecks.report_ui import (
    gpschecks_report,
    gpschecks_settings_section,
    gpschecks_status,
)
from datasure.checks.headline import CheckDelta, CheckHeadline, DeltaKind
from datasure.checks.health import (
    Delta,
    health_rows,
    render_comparison_period,
    render_health_header,
    render_health_rows,
    render_period_caption,
    status_only_headline,
)
from datasure.checks.health_period import (
    DEFAULT_PERIOD,
    DEFAULT_WEEK_START,
    ComparisonPeriod,
    DeltaWindow,
    latest_date,
    on_or_before,
    period_start,
    since_label,
)
from datasure.checks.missing import missing_headline, missing_report
from datasure.checks.outliers.report_ui import (
    outliers_delta,
    outliers_headline,
    outliers_report,
    outliers_settings_section,
    outliers_status,
)
from datasure.checks.progress import progress_headline, progress_report
from datasure.checks.summary import SummarySettings, summary_defaults, summary_report
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.dataframe_utils import get_df_columns
from datasure.utils.nav_ui import (
    PROJECT_VIEW_FILE,
    SET_UP_BELOW,
    guarded_status,
    project_nav_key,
    render_errors,
    select_nav_item,
)
from datasure.utils.navigation import (
    READY,
    NavItem,
    StatusResult,
    rows_status,
    with_errors,
)
from datasure.utils.navigations_utils import demo_callout
from datasure.utils.onboarding_utils import demo_output_onboarding

logger = logging.getLogger(__name__)

OVERVIEW = "Overview"
DATA_INTEGRITY = "Data integrity"
FIELD_TEAM = "Field team"
EXPLORATION = "Exploration"

# The check a page opens on when the URL and remembered selection give none.
DEFAULT_CHECK = "summary"

# URL query parameter holding the selected check, e.g. ?check=duplicates.
CHECK_PARAM = "check"


def check_nav_key(project_id: str, page_name_id: str) -> str:
    """Return the session state key prefix for a check page's navigation."""
    return project_nav_key(f"check_nav_{page_name_id}", project_id)


@dataclass(frozen=True)
class CheckEntry:
    """One check in the catalogue.

    Attributes
    ----------
    slug : str
        Stable identifier, used in the ``check`` URL query parameter.
    label : str
        Short label shown in the navigation.
    icon : str
        Material icon shortcode.
    group : str
        The navigation group the check belongs to.
    render : Callable[[CheckContext], None]
        Draws the check's report.
    status : Callable[[CheckContext], StatusResult]
        Cheap status from configuration and data shape only; never computes
        results. Default: always ready.
    setup : Callable[[CheckContext], None] | None
        Draws what the user needs to set the check up when it is not set up.
        Default: ``render``, for reports that start with their settings.
    headline : Callable[[CheckContext], CheckHeadline | None] | None
        The numbers Summary's check health row shows for the check when it
        is ready: the outstanding value and its detail, and the resolved
        count. Every number must match what the check reports. None for
        checks with no numbers, whose row shows their status only.
    settings : Callable[[CheckContext], None] | None
        Draws the check's settings section alone, under the empty state when
        the check is not applicable, so its settings stay reachable. None for
        checks that cannot be not applicable or have no settings section.
    setup_hint : str
        Ends the not-set-up message; it must say where the setup happens.
    delta : Delta | None
        The row's change over Summary's comparison period, from the context,
        the headline now and the window (see `health_rows`). None for checks
        whose row shows no change.
    """

    slug: str
    label: str
    icon: str
    group: str
    render: Callable[[CheckContext], None]
    status: Callable[[CheckContext], StatusResult] = lambda _ctx: READY
    setup: Callable[[CheckContext], None] | None = None
    headline: Callable[[CheckContext], CheckHeadline | None] | None = None
    settings: Callable[[CheckContext], None] | None = None
    setup_hint: str = SET_UP_BELOW
    delta: Delta | None = None


def _outliers_config(ctx: CheckContext) -> dict:
    config = ctx.config
    return {
        "survey_key": config.survey_key,
        "survey_id": config.survey_id,
        "enumerator": config.enumerator,
        "team": config.team,
        "survey_date": config.survey_date,
    }


def _backcheck_config(ctx: CheckContext) -> dict:
    config = ctx.config
    return {
        "survey_key": config.survey_key,
        "survey_id": config.survey_id,
        "survey_date": config.survey_date,
        "backcheck_date": config.backcheck_date,
        "enumerator": config.enumerator,
        "backchecker": config.backchecker,
        "backchecker_team": config.backchecker_team,
        "backcheck_target_percent": config.backcheck_target_percent,
        "survey_target": config.survey_target,
    }


def _render_summary(ctx: CheckContext) -> None:
    config, data = ctx.config, ctx.data
    summary_report(
        data.page_data,
        config.setting_file,
        {
            "survey_date": config.survey_date,
            "survey_target": config.survey_target,
        },
        ctx.survey_columns,
    )
    summary_check_health(ctx)


def _latest_submission(ctx: CheckContext, window: DeltaWindow) -> date | None:
    """The latest survey submission date, else the latest backcheck date."""
    if window.survey_date:
        return latest_date(ctx.data.page_data, window.survey_date)
    if window.backcheck_date and ctx.data.backcheck_data is not None:
        return latest_date(ctx.data.backcheck_data, window.backcheck_date)
    return None


@demo_output_onboarding("summary")
def summary_check_health(ctx: CheckContext) -> None:
    """Draw a check health row for every check but Summary, under its sections.

    Replaces Summary's former Data Quality section: each row's numbers come
    from its check, with that check's settings and corrections. Above the
    rows, the Comparison period box sets what their changes compare with;
    without any date column it is replaced by a caption saying how to get
    changes.
    """
    nav_key = check_nav_key(ctx.project_id, ctx.config.page_name_id)
    items = with_errors(nav_items(ctx), render_errors(nav_key))
    render_health_header()
    # Today is the computer clock's date.
    today = date.today()
    window = comparison_window(ctx, DEFAULT_PERIOD, today)
    since = None
    if window.has_dates:
        period, week_start = render_comparison_period(
            get_cache_path(ctx.project_id, "settings", PROJECT_VIEW_FILE),
            ctx.project_id,
        )
        window = comparison_window(ctx, period, today, week_start)
        since = since_label(period, today, week_start)
    render_period_caption(since, _latest_submission(ctx, window))
    rows = health_rows(
        ctx,
        [item for item in items if item.slug != "summary"],
        {entry.slug: entry.headline for entry in CHECK_CATALOGUE if entry.headline},
        deltas={entry.slug: entry.delta for entry in CHECK_CATALOGUE if entry.delta},
        window=window if window.has_dates else None,
    )
    render_health_rows(
        rows, on_select=partial(select_nav_item, nav_key, CHECK_PARAM), since=since
    )
    demo_callout(
        "**Next**: :material/arrow_upward: Scroll up and select **Overview → Progress**."
    )


def _render_descriptive(ctx: CheckContext) -> None:
    descriptive_report(
        ctx.project_id,
        ctx.config.page_name_id,
        ctx.data.page_data,
        ctx.config.setting_file,
        ctx.survey_columns,
    )


def _progress_config(ctx: CheckContext) -> dict:
    config = ctx.config
    return {
        "survey_key": config.survey_key,
        "survey_id": config.survey_id,
        "enumerator": config.enumerator,
        "survey_date": config.survey_date,
        "survey_target": config.survey_target,
    }


def _render_progress(ctx: CheckContext) -> None:
    progress_report(
        ctx.data.page_data,
        ctx.config.setting_file,
        _progress_config(ctx),
        ctx.survey_columns,
    )


def _render_missing(ctx: CheckContext) -> None:
    missing_report(
        ctx.project_id,
        ctx.config.page_name_id,
        ctx.data.page_data,
        ctx.config.setting_file,
    )


def _duplicates_config(ctx: CheckContext) -> dict:
    config = ctx.config
    return {
        "survey_key": config.survey_key,
        "survey_id": config.survey_id,
        "enumerator": config.enumerator,
        "team": config.team,
        "survey_date": config.survey_date,
        "backcheck_data_name": config.backcheck_data_name,
        "backcheck_date": config.backcheck_date,
        "backchecker": config.backchecker,
        "backchecker_team": config.backchecker_team,
    }


def _render_duplicates(ctx: CheckContext) -> None:
    config = ctx.config
    duplicates_report(
        ctx.project_id,
        config.page_name_id,
        ctx.data.page_data,
        config.setting_file,
        _duplicates_config(ctx),
        ctx.survey_columns,
        ctx.data.backcheck_data_with_rows,
        alias=config.survey_data_name,
    )


def _render_outliers(ctx: CheckContext) -> None:
    outliers_report(
        ctx.project_id,
        ctx.config.page_name_id,
        ctx.data.page_data,
        ctx.config.setting_file,
        _outliers_config(ctx),
        ctx.survey_columns,
        alias=ctx.config.survey_data_name,
    )


def _render_gps(ctx: CheckContext) -> None:
    config = ctx.config
    gpschecks_report(
        ctx.project_id,
        config.page_name_id,
        ctx.data.page_data,
        config.setting_file,
        _gps_config(ctx),
        ctx.survey_columns,
        alias=config.survey_data_name,
    )


def _enumerator_config(ctx: CheckContext) -> dict:
    config = ctx.config
    return {
        "survey_key": config.survey_key,
        "survey_id": config.survey_id,
        "survey_date": config.survey_date,
        "enumerator": config.enumerator,
        "formversion": config.formversion,
        "duration": config.duration,
        "team": config.team,
    }


def _render_enumerator(ctx: CheckContext) -> None:
    enumerator_report(
        ctx.project_id,
        ctx.data.page_data,
        ctx.config.setting_file,
        _enumerator_config(ctx),
        ctx.survey_columns,
    )


def _render_backchecks(ctx: CheckContext) -> None:
    # Only called when the status is ready, so the backcheck data has rows.
    data = ctx.data
    backchecks_report(
        ctx.project_id,
        ctx.config.page_name_id,
        data.page_data,
        data.backcheck_data,
        ctx.config.setting_file,
        _backcheck_config(ctx),
        ctx.survey_columns,
        get_df_columns(data.backcheck_data),
    )


def _outliers_settings(ctx: CheckContext) -> None:
    outliers_settings_section(
        ctx.config.setting_file, _outliers_config(ctx), ctx.survey_columns
    )


def _gps_config(ctx: CheckContext) -> dict:
    config = ctx.config
    return {
        "survey_key": config.survey_key,
        "survey_id": config.survey_id,
        "survey_date": config.survey_date,
        "enumerator": config.enumerator,
        "team": config.team,
    }


def _gps_settings(ctx: CheckContext) -> None:
    config = ctx.config
    gpschecks_settings_section(
        ctx.project_id,
        config.page_name_id,
        ctx.data.page_data,
        config.setting_file,
        _gps_config(ctx),
        ctx.survey_columns,
    )


def _backchecks_settings(ctx: CheckContext) -> None:
    # Not applicable means the backcheck data was loaded but has no rows; its
    # columns still fill the settings.
    data = ctx.data
    if data.backcheck_data is None:
        return
    backchecks_settings_section(
        ctx.project_id,
        data.page_data,
        data.backcheck_data,
        ctx.config.setting_file,
        _backcheck_config(ctx),
        ctx.survey_columns,
        get_df_columns(data.backcheck_data),
    )


def _setup_backchecks(ctx: CheckContext) -> None:
    import streamlit as st

    # The backcheck dataset is chosen on Configure Checks and imported on
    # Import Data, so link to the page that fixes it.
    if ctx.config.backcheck_data_name:
        page, label = st.session_state.get("st_import_data_page"), "Import Data"
    else:
        page = st.session_state.get("st_config_checks_page")
        label = "Configure Checks"
    if page is not None:
        st.page_link(page, label=f"Open {label}", icon=":material/arrow_forward:")


def _survey_rows_status(ctx: CheckContext) -> StatusResult:
    """Status of Summary, Progress, Missing Values and Descriptive Stats.

    They work on any survey data with rows, so they share this one status.
    """
    return rows_status(ctx.data.page_data.height)


# Status adapters look the module-level status functions up on each call.


def _duplicates_status(ctx: CheckContext) -> StatusResult:
    return duplicates_status(
        ctx.config.setting_file,
        {"survey_id": ctx.config.survey_id},
        ctx.data.page_data.columns,
    )


def _outliers_status(ctx: CheckContext) -> StatusResult:
    return outliers_status(ctx.project_id, ctx.config.page_name_id, ctx.survey_columns)


def _gps_status(ctx: CheckContext) -> StatusResult:
    return gpschecks_status(ctx.project_id, ctx.config.page_name_id, ctx.data.page_data)


def _enumerator_status(ctx: CheckContext) -> StatusResult:
    config = ctx.config
    return enumerator_status(
        config.setting_file,
        {"enumerator": config.enumerator, "survey_date": config.survey_date},
    )


def _backchecks_status(ctx: CheckContext) -> StatusResult:
    return backchecks_status(ctx.config.backcheck_data_name, ctx.data.backcheck_data)


# Headline adapters also look the module-level functions up on each call.
def _progress_headline(ctx: CheckContext) -> CheckHeadline | None:
    return progress_headline(
        ctx.data.page_data, ctx.config.setting_file, _progress_config(ctx)
    )


def _missing_headline(ctx: CheckContext) -> CheckHeadline | None:
    return missing_headline(ctx.project_id, ctx.data.page_data)


def _duplicates_headline(ctx: CheckContext) -> CheckHeadline | None:
    config = ctx.config
    return duplicates_headline(
        ctx.project_id,
        ctx.data.page_data,
        config.setting_file,
        _duplicates_config(ctx),
        alias=config.survey_data_name,
    )


def _outliers_headline(ctx: CheckContext) -> CheckHeadline | None:
    config = ctx.config
    return outliers_headline(
        ctx.project_id,
        config.page_name_id,
        ctx.data.page_data,
        ctx.survey_columns,
        config.setting_file,
        _outliers_config(ctx),
        config.survey_data_name,
    )


def _enumerator_headline(ctx: CheckContext) -> CheckHeadline | None:
    return enumerator_headline(
        ctx.project_id,
        ctx.data.page_data,
        ctx.config.setting_file,
        _enumerator_config(ctx),
    )


def _backchecks_headline(ctx: CheckContext) -> CheckHeadline | None:
    # Only called when the status is ready, so the backcheck data has rows.
    return backchecks_headline(
        ctx.project_id,
        ctx.config.page_name_id,
        ctx.data.page_data,
        ctx.data.backcheck_data,
        ctx.config.setting_file,
        _backcheck_config(ctx),
    )


def _column_in(column: str | None, data: pl.DataFrame | None) -> str | None:
    return column if column and data is not None and column in data.columns else None


def comparison_window(
    ctx: CheckContext,
    period: ComparisonPeriod,
    today: date,
    week_start: str = DEFAULT_WEEK_START,
) -> DeltaWindow:
    """Return the comparison window of a page's health rows.

    Rows compare by Summary's date column: Summary's saved date setting,
    else the page's survey date. The Backchecks row compares by the
    backcheck date column. A column that is not in its data counts as not
    set, so its rows show no change.

    Parameters
    ----------
    ctx : CheckContext
        The check page's context.
    period : ComparisonPeriod
        The comparison period.
    today : date
        Today, from the computer clock.
    week_start : str
        The first day of the week, for the Week period.
    """
    config = ctx.config
    survey_date, _ = summary_defaults(
        str(config.setting_file), SummarySettings(survey_date=config.survey_date)
    )
    backcheck_date = None
    if ctx.data.backcheck_data is not None:
        try:
            backcheck_date = load_default_backchecks_settings(
                str(config.setting_file),
                settings_from_page_config(_backcheck_config(ctx)),
            ).backcheck_date
        except ValidationError:
            # The Backchecks row shows the settings error; it has no change.
            logger.warning("Could not load the backcheck settings", exc_info=True)
    return DeltaWindow(
        as_of=period_start(period, today, week_start),
        survey_date=_column_in(survey_date, ctx.data.page_data),
        backcheck_date=_column_in(backcheck_date, ctx.data.backcheck_data),
    )


# --- Delta adapters --------------------------------------------------------
# Each takes the context, the check's headline now and the comparison window,
# and returns the row's change over the period, or None without a date
# column. A new check gets a delta by adding an adapter here.


def _before(ctx: CheckContext, window: DeltaWindow) -> CheckContext | None:
    """Return the context on the submissions dated on or before the period start.

    None when Summary's date column is not set or not in the data.
    """
    column, data = window.survey_date, ctx.data.page_data
    if not column or column not in data.columns:
        return None
    return replace(
        ctx,
        data=CheckData(
            on_or_before(data, column, window.as_of), ctx.data.backcheck_data
        ),
    )


def _progress_delta(
    ctx: CheckContext, now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    before = _before(ctx, window)
    if before is None or now.count is None:
        return None
    then = _progress_headline(before)
    return CheckDelta(now.count - (then.count or 0), kind=DeltaKind.SUBMISSIONS)


def _missing_delta(
    ctx: CheckContext, now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    before = _before(ctx, window)
    # With no submissions before the period there is no share to compare.
    if before is None or before.data.page_data.is_empty() or now.outstanding is None:
        return None
    then = _missing_headline(before)
    return CheckDelta(now.outstanding - (then.outstanding or 0), kind=DeltaKind.POINTS)


def _new_issues(now: CheckHeadline, then: CheckHeadline | None) -> float | None:
    """The issues among the submissions in the period: now less the as-of count.

    The as-of count is on fewer submissions of the same corrected data, so it
    is never larger; it is floored at 0 all the same.
    """
    if now.outstanding is None:
        return None
    before = then.outstanding if then is not None else None
    return max(now.outstanding - (before or 0), 0)


def _duplicates_delta(
    ctx: CheckContext, now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    before = _before(ctx, window)
    if before is None:
        return None
    config = ctx.config
    # No alias: the as-of resolved count is not needed, so it is skipped.
    then = duplicates_headline(
        ctx.project_id,
        before.data.page_data,
        config.setting_file,
        _duplicates_config(ctx),
    )
    return CheckDelta(
        _new_issues(now, then),
        resolved=duplicates_resolved_since(
            ctx.project_id,
            ctx.data.page_data,
            config.setting_file,
            _duplicates_config(ctx),
            config.survey_data_name,
            window.as_of,
        ),
    )


def _outliers_delta(
    ctx: CheckContext, _now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    if _before(ctx, window) is None:
        return None
    config = ctx.config
    return outliers_delta(
        ctx.project_id,
        config.page_name_id,
        ctx.data.page_data,
        ctx.survey_columns,
        config.setting_file,
        _outliers_config(ctx),
        config.survey_data_name,
        window.survey_date,
        window.as_of,
    )


def _backchecks_delta(
    ctx: CheckContext, _now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    # The Backchecks row uses the backcheck date column, never the survey's.
    if not window.backcheck_date or ctx.data.backcheck_data is None:
        return None
    return backchecks_delta(
        ctx.project_id,
        ctx.config.page_name_id,
        ctx.data.page_data,
        ctx.data.backcheck_data,
        ctx.config.setting_file,
        _backcheck_config(ctx),
        window.backcheck_date,
        window.as_of,
    )


def _enumerator_delta(
    ctx: CheckContext, now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    before = _before(ctx, window)
    if before is None or now.count is None:
        return None
    # Active in the 7 days up to the period start, on what was submitted then.
    then = enumerator_headline(
        ctx.project_id,
        before.data.page_data,
        ctx.config.setting_file,
        _enumerator_config(ctx),
        today=window.as_of,
    )
    active = then.count if then is not None and then.count is not None else 0
    return CheckDelta(now.count - active, kind=DeltaKind.ACTIVE)


CHECK_CATALOGUE: tuple[CheckEntry, ...] = (
    CheckEntry(
        "summary",
        "Summary",
        ":material/dashboard:",
        OVERVIEW,
        _render_summary,
        _survey_rows_status,
    ),
    CheckEntry(
        "progress",
        "Progress",
        ":material/trending_up:",
        OVERVIEW,
        _render_progress,
        _survey_rows_status,
        headline=_progress_headline,
        delta=_progress_delta,
    ),
    CheckEntry(
        "missing",
        "Missing Values",
        ":material/check_box_outline_blank:",
        DATA_INTEGRITY,
        _render_missing,
        _survey_rows_status,
        headline=_missing_headline,
        delta=_missing_delta,
    ),
    CheckEntry(
        "duplicates",
        "Duplicates",
        ":material/content_copy:",
        DATA_INTEGRITY,
        _render_duplicates,
        _duplicates_status,
        headline=_duplicates_headline,
        delta=_duplicates_delta,
    ),
    CheckEntry(
        "outliers",
        "Outliers & Constraints",
        ":material/warning:",
        DATA_INTEGRITY,
        _render_outliers,
        _outliers_status,
        headline=_outliers_headline,
        delta=_outliers_delta,
        settings=_outliers_settings,
    ),
    CheckEntry(
        "gps",
        "GPS Checks",
        ":material/location_on:",
        DATA_INTEGRITY,
        _render_gps,
        _gps_status,
        settings=_gps_settings,
    ),
    CheckEntry(
        "enumerator",
        "Enumerator Stats",
        ":material/groups:",
        FIELD_TEAM,
        _render_enumerator,
        _enumerator_status,
        headline=_enumerator_headline,
        delta=_enumerator_delta,
    ),
    CheckEntry(
        "backchecks",
        "Backchecks",
        ":material/fact_check:",
        FIELD_TEAM,
        _render_backchecks,
        _backchecks_status,
        setup=_setup_backchecks,
        headline=_backchecks_headline,
        delta=_backchecks_delta,
        settings=_backchecks_settings,
        # The backcheck dataset is chosen and imported on other pages.
        setup_hint="Fix it on the page linked below.",
    ),
    CheckEntry(
        "descriptive",
        "Descriptive Stats",
        ":material/bar_chart:",
        EXPLORATION,
        _render_descriptive,
        _survey_rows_status,
        headline=status_only_headline,
    ),
)


def get_check(slug: str) -> CheckEntry:
    """Return the catalogue entry with the given slug.

    Raises
    ------
    KeyError
        If no check has the slug.
    """
    for entry in CHECK_CATALOGUE:
        if entry.slug == slug:
            return entry
    raise KeyError(slug)


def nav_items(ctx: CheckContext) -> tuple[NavItem, ...]:
    """Return a navigation item, with its status, for every catalogue check.

    A status function that raises gives that check the error status.
    """
    items = []
    for entry in CHECK_CATALOGUE:
        status, reason = guarded_status(entry.slug, lambda e=entry: e.status(ctx))
        items.append(
            NavItem(entry.slug, entry.label, entry.icon, entry.group, status, reason)
        )
    return tuple(items)
