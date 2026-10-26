"""The check catalogue: every check shown on a check page.

Each entry gives a check's slug, short label, icon, group, render function,
status function and optional headline and delta functions, in display order.
Delta functions live in `health_deltas`, so the catalogue only names them. The
check
page builds its navigation and Summary's check health rows from this
catalogue, so adding an entry here is the only change needed for a new check
to appear.
"""

from collections.abc import Callable, Hashable
from dataclasses import dataclass
from datetime import date
from functools import partial

from datasure.checks import health_deltas
from datasure.checks.backchecks.report_ui import (
    backchecks_headline,
    backchecks_report,
    backchecks_settings_section,
    backchecks_status,
)
from datasure.checks.check_configs import (
    backcheck_config,
    duplicates_config,
    enumerator_config,
    gps_config,
    outliers_config,
    progress_config,
)
from datasure.checks.context import CheckContext
from datasure.checks.descriptive import descriptive_report
from datasure.checks.duplicates import (
    duplicates_headline,
    duplicates_report,
    duplicates_status,
)
from datasure.checks.enumerator.report_ui import (
    enumerator_headline,
    enumerator_report,
    enumerator_status,
)
from datasure.checks.gpschecks.report_ui import (
    gpschecks_headline,
    gpschecks_headline_view,
    gpschecks_report,
    gpschecks_settings_section,
    gpschecks_status,
)
from datasure.checks.headline import CheckHeadline
from datasure.checks.health import (
    Delta,
    health_rows,
    render_comparison_period,
    render_health_header,
    render_health_rows,
    render_period_caption,
    status_only_headline,
)
from datasure.checks.health_deltas import comparison_window, latest_submission
from datasure.checks.health_period import DEFAULT_PERIOD, since_label
from datasure.checks.missing import missing_headline, missing_report
from datasure.checks.outliers.report_ui import (
    outliers_headline,
    outliers_report,
    outliers_settings_section,
    outliers_status,
)
from datasure.checks.progress import progress_headline, progress_report
from datasure.checks.summary import summary_report
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
    headline_view : Callable[[CheckContext], Hashable] | None
        The saved view values ``headline`` depends on, such as the GPS
        check's Auto-Clustering sliders. Summary's cached numbers are keyed
        on page data and settings without view state, so these are added to
        the check's key. None for headlines that ignore view state.
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
    headline_view: Callable[[CheckContext], Hashable] | None = None


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
    render_period_caption(since, latest_submission(ctx, window))
    rows = health_rows(
        ctx,
        [item for item in items if item.slug != "summary"],
        {entry.slug: entry.headline for entry in CHECK_CATALOGUE if entry.headline},
        deltas={entry.slug: entry.delta for entry in CHECK_CATALOGUE if entry.delta},
        window=window if window.has_dates else None,
        view_keys={
            entry.slug: entry.headline_view
            for entry in CHECK_CATALOGUE
            if entry.headline_view
        },
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


def _render_progress(ctx: CheckContext) -> None:
    progress_report(
        ctx.data.page_data,
        ctx.config.setting_file,
        progress_config(ctx),
        ctx.survey_columns,
    )


def _render_missing(ctx: CheckContext) -> None:
    missing_report(
        ctx.project_id,
        ctx.config.page_name_id,
        ctx.data.page_data,
        ctx.config.setting_file,
    )


def _render_duplicates(ctx: CheckContext) -> None:
    config = ctx.config
    duplicates_report(
        ctx.project_id,
        config.page_name_id,
        ctx.data.page_data,
        config.setting_file,
        duplicates_config(ctx),
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
        outliers_config(ctx),
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
        gps_config(ctx),
        ctx.survey_columns,
        alias=config.survey_data_name,
    )


def _render_enumerator(ctx: CheckContext) -> None:
    enumerator_report(
        ctx.project_id,
        ctx.data.page_data,
        ctx.config.setting_file,
        enumerator_config(ctx),
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
        backcheck_config(ctx),
        ctx.survey_columns,
        get_df_columns(data.backcheck_data),
    )


def _outliers_settings(ctx: CheckContext) -> None:
    outliers_settings_section(
        ctx.config.setting_file, outliers_config(ctx), ctx.survey_columns
    )


def _gps_settings(ctx: CheckContext) -> None:
    config = ctx.config
    gpschecks_settings_section(
        ctx.project_id,
        config.page_name_id,
        ctx.data.page_data,
        config.setting_file,
        gps_config(ctx),
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
        backcheck_config(ctx),
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
        ctx.data.page_data, ctx.config.setting_file, progress_config(ctx)
    )


def _missing_headline(ctx: CheckContext) -> CheckHeadline | None:
    return missing_headline(ctx.project_id, ctx.data.page_data)


def _duplicates_headline(ctx: CheckContext) -> CheckHeadline | None:
    config = ctx.config
    return duplicates_headline(
        ctx.project_id,
        ctx.data.page_data,
        config.setting_file,
        duplicates_config(ctx),
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
        outliers_config(ctx),
        config.survey_data_name,
    )


def _gps_headline(ctx: CheckContext) -> CheckHeadline | None:
    config = ctx.config
    return gpschecks_headline(
        ctx.project_id,
        config.page_name_id,
        ctx.data.page_data,
        gps_config(ctx),
        alias=config.survey_data_name,
    )


def _gps_headline_view(ctx: CheckContext) -> Hashable:
    return gpschecks_headline_view(ctx.project_id, ctx.config.page_name_id)


def _enumerator_headline(ctx: CheckContext) -> CheckHeadline | None:
    return enumerator_headline(
        ctx.project_id,
        ctx.data.page_data,
        ctx.config.setting_file,
        enumerator_config(ctx),
    )


def _backchecks_headline(ctx: CheckContext) -> CheckHeadline | None:
    # Only called when the status is ready, so the backcheck data has rows.
    return backchecks_headline(
        ctx.project_id,
        ctx.config.page_name_id,
        ctx.data.page_data,
        ctx.data.backcheck_data,
        ctx.config.setting_file,
        backcheck_config(ctx),
    )


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
        delta=health_deltas.progress,
    ),
    CheckEntry(
        "missing",
        "Missing Values",
        ":material/check_box_outline_blank:",
        DATA_INTEGRITY,
        _render_missing,
        _survey_rows_status,
        headline=_missing_headline,
        delta=health_deltas.missing,
    ),
    CheckEntry(
        "duplicates",
        "Duplicates",
        ":material/content_copy:",
        DATA_INTEGRITY,
        _render_duplicates,
        _duplicates_status,
        headline=_duplicates_headline,
        delta=health_deltas.duplicates,
    ),
    CheckEntry(
        "outliers",
        "Outliers & Constraints",
        ":material/warning:",
        DATA_INTEGRITY,
        _render_outliers,
        _outliers_status,
        headline=_outliers_headline,
        delta=health_deltas.outliers,
        settings=_outliers_settings,
    ),
    CheckEntry(
        "gps",
        "GPS Checks",
        ":material/location_on:",
        DATA_INTEGRITY,
        _render_gps,
        _gps_status,
        headline=_gps_headline,
        delta=health_deltas.gps,
        settings=_gps_settings,
        headline_view=_gps_headline_view,
    ),
    CheckEntry(
        "enumerator",
        "Enumerator Stats",
        ":material/groups:",
        FIELD_TEAM,
        _render_enumerator,
        _enumerator_status,
        headline=_enumerator_headline,
        delta=health_deltas.enumerator,
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
        delta=health_deltas.backchecks,
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
