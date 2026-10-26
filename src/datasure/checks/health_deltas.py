"""Each check's change over Summary's comparison period, for its health row.

`comparison_window` decides what the rows compare with: the period start and
the date columns. Each delta function here takes the check page's context,
the check's headline now and that window, and returns the row's
`CheckDelta`, or None when the row shows no change. The check catalogue
names one per check (``CheckEntry.delta``); a new check gets a change by
adding a function here.

Most checks are recomputed on the submissions dated on or before the period
start and compared with now. Outliers, GPS Checks and Duplicates count their
current issues on the submissions dated in the period, and Backchecks
compares by the backcheck date (see each check's own delta function).
"""

import logging
from dataclasses import replace
from datetime import date

from pydantic import ValidationError

from datasure.checks.backchecks.compute import load_default_backchecks_settings
from datasure.checks.backchecks.coverage import settings_from_page_config
from datasure.checks.backchecks.report_ui import backchecks_delta
from datasure.checks.check_configs import (
    backcheck_config,
    duplicates_config,
    enumerator_config,
    gps_config,
    outliers_config,
    progress_config,
)
from datasure.checks.context import CheckContext, CheckData
from datasure.checks.duplicates import duplicates_delta
from datasure.checks.enumerator.report_ui import enumerator_headline
from datasure.checks.gpschecks.report_ui import gpschecks_delta
from datasure.checks.headline import CheckDelta, CheckHeadline, DeltaKind
from datasure.checks.health_period import (
    DEFAULT_WEEK_START,
    ComparisonPeriod,
    DeltaWindow,
    Weekday,
    latest_date,
    on_or_before,
    period_start,
)
from datasure.checks.missing import missing_headline
from datasure.checks.outliers.report_ui import outliers_delta
from datasure.checks.progress import progress_headline
from datasure.checks.summary import SummarySettings, summary_defaults

logger = logging.getLogger(__name__)


def _column_in(column: str | None, data) -> str | None:
    return column if column and data is not None and column in data.columns else None


def comparison_window(
    ctx: CheckContext,
    period: ComparisonPeriod,
    today: date,
    week_start: Weekday = DEFAULT_WEEK_START,
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
    week_start : Weekday
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
                settings_from_page_config(backcheck_config(ctx)),
            ).backcheck_date
        except ValidationError:
            # The Backchecks row shows the settings error; it has no change.
            logger.warning("Could not load the backcheck settings", exc_info=True)
    return DeltaWindow(
        as_of=period_start(period, today, week_start),
        survey_date=_column_in(survey_date, ctx.data.page_data),
        backcheck_date=_column_in(backcheck_date, ctx.data.backcheck_data),
    )


def latest_submission(ctx: CheckContext, window: DeltaWindow) -> date | None:
    """Return the latest survey submission date, else the latest backcheck date."""
    if window.survey_date:
        return latest_date(ctx.data.page_data, window.survey_date)
    if window.backcheck_date and ctx.data.backcheck_data is not None:
        return latest_date(ctx.data.backcheck_data, window.backcheck_date)
    return None


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


def progress(
    ctx: CheckContext, now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    """The submissions dated in the period."""
    before = _before(ctx, window)
    if before is None or now.count is None:
        return None
    then = progress_headline(
        before.data.page_data, ctx.config.setting_file, progress_config(ctx)
    )
    if then is None:
        return None
    return CheckDelta(now.count - (then.count or 0), kind=DeltaKind.SUBMISSIONS)


def missing(
    ctx: CheckContext, now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    """The change in the share of columns all missing, in percentage points."""
    before = _before(ctx, window)
    # With no submissions before the period there is no share to compare.
    if before is None or before.data.page_data.is_empty() or now.outstanding is None:
        return None
    then = missing_headline(ctx.project_id, before.data.page_data)
    if then is None or then.outstanding is None:
        return None
    return CheckDelta(now.outstanding - then.outstanding, kind=DeltaKind.POINTS)


def duplicates(
    ctx: CheckContext, now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    """The duplicate IDs on submissions in the period, and those resolved in it."""
    config = ctx.config
    return duplicates_delta(
        ctx.project_id,
        ctx.data.page_data,
        config.setting_file,
        duplicates_config(ctx),
        config.survey_data_name,
        window,
        basis=now.basis,
    )


def outliers(
    ctx: CheckContext, now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    """The flags on submissions in the period, and those resolved in it."""
    if _before(ctx, window) is None:
        return None
    config = ctx.config
    return outliers_delta(
        ctx.project_id,
        config.page_name_id,
        ctx.data.page_data,
        ctx.survey_columns,
        config.setting_file,
        outliers_config(ctx),
        config.survey_data_name,
        window,
        basis=now.basis,
    )


def gps(
    ctx: CheckContext, now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    """The GPS outliers on submissions in the period, and those resolved in it."""
    if _before(ctx, window) is None:
        return None
    config = ctx.config
    return gpschecks_delta(
        ctx.project_id,
        config.page_name_id,
        ctx.data.page_data,
        gps_config(ctx),
        config.survey_data_name,
        window,
        basis=now.basis,
    )


def backchecks(
    ctx: CheckContext, _now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    """The mismatches on backchecks dated in the period, and those attributed."""
    # The Backchecks row uses the backcheck date column, never the survey's.
    if not window.backcheck_date or ctx.data.backcheck_data is None:
        return None
    return backchecks_delta(
        ctx.project_id,
        ctx.config.page_name_id,
        ctx.data.page_data,
        ctx.data.backcheck_data,
        ctx.config.setting_file,
        backcheck_config(ctx),
        window,
    )


def enumerator(
    ctx: CheckContext, now: CheckHeadline, window: DeltaWindow
) -> CheckDelta | None:
    """The change in enumerators active in the past 7 days."""
    before = _before(ctx, window)
    if before is None or now.count is None:
        return None
    # Active in the 7 days up to the period start, on what was submitted then.
    then = enumerator_headline(
        ctx.project_id,
        before.data.page_data,
        ctx.config.setting_file,
        enumerator_config(ctx),
        today=window.as_of,
    )
    active = then.count if then is not None and then.count is not None else 0
    return CheckDelta(now.count - active, kind=DeltaKind.ACTIVE)
