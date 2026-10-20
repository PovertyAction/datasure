"""The check catalogue: every check shown on a check page.

Each entry gives a check's slug, label, icon, group and render function. The
check page builds its navigation from this catalogue, so adding an entry here
is the only change needed for a new check to appear.
"""

from collections.abc import Callable
from dataclasses import dataclass

from datasure.checks.backchecks.report_ui import (
    backchecks_report,
    overall_error_rate_percent,
)
from datasure.checks.context import CheckContext
from datasure.checks.descriptive import descriptive_report
from datasure.checks.duplicates import duplicates_report
from datasure.checks.enumerator.report_ui import enumerator_report
from datasure.checks.gpschecks.report_ui import gpschecks_report
from datasure.checks.missing import missing_report
from datasure.checks.outliers.report_ui import (
    flagged_outlier_percent,
    outliers_report,
)
from datasure.checks.progress import progress_report
from datasure.checks.summary import CheckRates, summary_report
from datasure.utils.dataframe_utils import TableState, get_df_columns, no_rows_message


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
    """

    slug: str
    label: str
    icon: str
    group: str
    render: Callable[[CheckContext], None]


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
    import streamlit as st

    data = ctx.data
    backcheck_state = data.backcheck_state
    if backcheck_state is TableState.HAS_ROWS:
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
    elif backcheck_state is TableState.NO_ROWS:
        st.info(no_rows_message(ctx.config.backcheck_data_name, "analyze"))
    else:
        st.info("No backcheck data available for analysis.")


CHECK_CATALOGUE: tuple[CheckEntry, ...] = (
    CheckEntry(
        "summary", "Summary", ":material/dashboard:", "Overview", _render_summary
    ),
    CheckEntry(
        "descriptive",
        "Descriptive Statistics",
        ":material/bar_chart:",
        "Exploration",
        _render_descriptive,
    ),
    CheckEntry(
        "progress",
        "Progress Tracking",
        ":material/trending_up:",
        "Overview",
        _render_progress,
    ),
    CheckEntry(
        "missing",
        "Missing Values",
        ":material/block:",
        "Data integrity",
        _render_missing,
    ),
    CheckEntry(
        "duplicates",
        "Duplicates",
        ":material/content_copy:",
        "Data integrity",
        _render_duplicates,
    ),
    CheckEntry(
        "outliers",
        "Outliers & Constraints",
        ":material/warning:",
        "Data integrity",
        _render_outliers,
    ),
    CheckEntry(
        "gps", "GPS Checks", ":material/location_on:", "Data integrity", _render_gps
    ),
    CheckEntry(
        "enumerator",
        "Enumerator Statistics",
        ":material/groups:",
        "Field team",
        _render_enumerator,
    ),
    CheckEntry(
        "backchecks",
        "Backcheck Analysis",
        ":material/fact_check:",
        "Field team",
        _render_backchecks,
    ),
)
