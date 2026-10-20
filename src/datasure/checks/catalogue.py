"""The check catalogue: every check shown on a check page.

Each entry gives a check's slug, short label, icon, group, render function and
status function, in display order. The check page builds its navigation from
this catalogue, so adding an entry here is the only change needed for a new
check to appear.
"""

from collections.abc import Callable
from dataclasses import dataclass

from datasure.checks.backchecks.report_ui import (
    backchecks_report,
    backchecks_status,
    overall_error_rate_percent,
)
from datasure.checks.context import CheckContext
from datasure.checks.descriptive import descriptive_report, descriptive_status
from datasure.checks.duplicates import duplicates_report, duplicates_status
from datasure.checks.enumerator.report_ui import enumerator_report, enumerator_status
from datasure.checks.gpschecks.report_ui import gpschecks_report, gpschecks_status
from datasure.checks.missing import missing_report, missing_status
from datasure.checks.outliers.report_ui import (
    flagged_outlier_percent,
    outliers_report,
    outliers_status,
)
from datasure.checks.progress import progress_report, progress_status
from datasure.checks.summary import CheckRates, summary_report, summary_status
from datasure.utils.dataframe_utils import TableState, get_df_columns
from datasure.utils.nav_ui import guarded_status
from datasure.utils.navigation import READY, NavItem, StatusResult

OVERVIEW = "Overview"
DATA_INTEGRITY = "Data integrity"
FIELD_TEAM = "Field team"
EXPLORATION = "Exploration"

# The check a page opens on when the URL and remembered selection give none.
DEFAULT_CHECK = "summary"


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
    """

    slug: str
    label: str
    icon: str
    group: str
    render: Callable[[CheckContext], None]
    status: Callable[[CheckContext], StatusResult] = lambda _ctx: READY
    setup: Callable[[CheckContext], None] | None = None


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
    # Summary shows rates from the Outliers and Backchecks checks. They are
    # computed here, so they only run when Summary is shown.
    check_rates = CheckRates(
        outliers_pct=flagged_outlier_percent(
            ctx.project_id,
            config.page_name_id,
            data.page_data,
            ctx.survey_columns,
            config.setting_file,
            _outliers_config(ctx),
            config.survey_data_name,
        ),
        backcheck_error_pct=(
            overall_error_rate_percent(
                ctx.project_id,
                config.page_name_id,
                data.page_data,
                data.backcheck_data,
                config.setting_file,
                _backcheck_config(ctx),
            )
            if data.backcheck_state is TableState.HAS_ROWS
            else None
        ),
    )
    summary_report(
        data.page_data,
        config.setting_file,
        {
            "survey_id": config.survey_id,
            "survey_date": config.survey_date,
            "survey_target": config.survey_target,
        },
        ctx.survey_columns,
        check_rates=check_rates,
    )


def _render_descriptive(ctx: CheckContext) -> None:
    descriptive_report(
        ctx.project_id,
        ctx.data.page_data,
        ctx.config.setting_file,
        ctx.survey_columns,
    )


def _render_progress(ctx: CheckContext) -> None:
    config = ctx.config
    progress_report(
        ctx.data.page_data,
        config.setting_file,
        {
            "survey_key": config.survey_key,
            "survey_id": config.survey_id,
            "enumerator": config.enumerator,
            "survey_date": config.survey_date,
            "survey_target": config.survey_target,
        },
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
        {
            "survey_key": config.survey_key,
            "survey_id": config.survey_id,
            "enumerator": config.enumerator,
            "team": config.team,
            "survey_date": config.survey_date,
            "backcheck_data_name": config.backcheck_data_name,
            "backcheck_date": config.backcheck_date,
            "backchecker": config.backchecker,
            "backchecker_team": config.backchecker_team,
        },
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
        {
            "survey_key": config.survey_key,
            "survey_id": config.survey_id,
            "survey_date": config.survey_date,
            "enumerator": config.enumerator,
            "team": config.team,
        },
        ctx.survey_columns,
        alias=config.survey_data_name,
    )


def _render_enumerator(ctx: CheckContext) -> None:
    config = ctx.config
    enumerator_report(
        ctx.project_id,
        ctx.data.page_data,
        config.setting_file,
        {
            "survey_key": config.survey_key,
            "survey_id": config.survey_id,
            "survey_date": config.survey_date,
            "enumerator": config.enumerator,
            "formversion": config.formversion,
            "duration": config.duration,
            "team": config.team,
        },
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


# Status adapters look the module-level status functions up on each call.
def _summary_status(ctx: CheckContext) -> StatusResult:
    return summary_status(ctx.data.page_data)


def _progress_status(ctx: CheckContext) -> StatusResult:
    return progress_status(ctx.data.page_data)


def _missing_status(ctx: CheckContext) -> StatusResult:
    return missing_status(ctx.data.page_data)


def _duplicates_status(ctx: CheckContext) -> StatusResult:
    return duplicates_status(
        ctx.config.setting_file, {"survey_id": ctx.config.survey_id}
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


def _descriptive_status(ctx: CheckContext) -> StatusResult:
    return descriptive_status(ctx.data.page_data)


CHECK_CATALOGUE: tuple[CheckEntry, ...] = (
    CheckEntry(
        "summary",
        "Summary",
        ":material/dashboard:",
        OVERVIEW,
        _render_summary,
        _summary_status,
    ),
    CheckEntry(
        "progress",
        "Progress",
        ":material/trending_up:",
        OVERVIEW,
        _render_progress,
        _progress_status,
    ),
    CheckEntry(
        "missing",
        "Missing Values",
        ":material/check_box_outline_blank:",
        DATA_INTEGRITY,
        _render_missing,
        _missing_status,
    ),
    CheckEntry(
        "duplicates",
        "Duplicates",
        ":material/content_copy:",
        DATA_INTEGRITY,
        _render_duplicates,
        _duplicates_status,
    ),
    CheckEntry(
        "outliers",
        "Outliers & Constraints",
        ":material/warning:",
        DATA_INTEGRITY,
        _render_outliers,
        _outliers_status,
    ),
    CheckEntry(
        "gps",
        "GPS Checks",
        ":material/location_on:",
        DATA_INTEGRITY,
        _render_gps,
        _gps_status,
    ),
    CheckEntry(
        "enumerator",
        "Enumerator Stats",
        ":material/groups:",
        FIELD_TEAM,
        _render_enumerator,
        _enumerator_status,
    ),
    CheckEntry(
        "backchecks",
        "Backchecks",
        ":material/fact_check:",
        FIELD_TEAM,
        _render_backchecks,
        _backchecks_status,
        setup=_setup_backchecks,
    ),
    CheckEntry(
        "descriptive",
        "Descriptive Stats",
        ":material/bar_chart:",
        EXPLORATION,
        _render_descriptive,
        _descriptive_status,
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
