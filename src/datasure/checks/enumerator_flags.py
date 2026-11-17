"""Other checks' outstanding issues by enumerator, for the Enumerator page.

Each function here takes the check page's context and the page's enumerator
column and returns the check's outstanding issues by enumerator
(`IssueCounts`), or an empty tuple when it has none to give. The check
catalogue names one per check (``CheckEntry.by_enumerator``), and the
Enumerator page lists them under "Needs attention".

Each starts from the check's headline, through Summary's cache
(`health.cached_headline`), so the issues are those the check and its
health row count, after corrections and acceptances, and opening the
Enumerator page after Summary computes nothing again. Backchecks has no
headline basis, so its numbers are cached on the page instead.
"""

from datasure.checks.backchecks.report_ui import backcheck_mismatches_by_enumerator
from datasure.checks.check_configs import (
    backcheck_config,
    duplicates_config,
    gps_config,
    outliers_config,
)
from datasure.checks.context import CheckContext
from datasure.checks.duplicates import (
    duplicate_records_by_enumerator,
    duplicates_headline,
)
from datasure.checks.enumerator.attention import CountRule, IssueCounts
from datasure.checks.gpschecks.report_ui import (
    gpschecks_headline,
    gpschecks_headline_view,
)
from datasure.checks.health import cached_headline, cached_on_page
from datasure.checks.outliers.report_ui import (
    outliers_by_enumerator,
    outliers_headline,
)


def duplicates(ctx: CheckContext, enumerator: str) -> tuple[IssueCounts, ...]:
    """Records holding an unresolved duplicate ID; any one is worth a look."""
    config = ctx.config
    headline = cached_headline(
        ctx,
        "duplicates",
        lambda c: duplicates_headline(
            c.project_id,
            c.data.page_data,
            c.config.setting_file,
            duplicates_config(c),
            alias=config.survey_data_name,
        ),
    )
    if headline is None or headline.basis is None:
        return ()
    counts = duplicate_records_by_enumerator(headline.basis, enumerator)
    return (
        IssueCounts(
            "Duplicates",
            "record with a duplicate ID",
            "records with a duplicate ID",
            counts,
        ),
    )


def outliers(ctx: CheckContext, enumerator: str) -> tuple[IssueCounts, ...]:
    """Outliers and constraint violations, flagged at a rate above the team's."""
    config = ctx.config
    headline = cached_headline(
        ctx,
        "outliers",
        lambda c: outliers_headline(
            c.project_id,
            config.page_name_id,
            c.data.page_data,
            c.survey_columns,
            config.setting_file,
            outliers_config(c),
            config.survey_data_name,
        ),
    )
    if headline is None or headline.basis is None:
        return ()
    found, broken = outliers_by_enumerator(
        headline.basis, ctx.data.page_data, enumerator
    )
    return (
        IssueCounts("Outliers", "outlier", "outliers", found, rule=CountRule.RELATIVE),
        IssueCounts(
            "Constraints",
            "constraint violation",
            "constraint violations",
            broken,
            rule=CountRule.RELATIVE,
        ),
    )


def _gps_view(ctx: CheckContext) -> object:
    return gpschecks_headline_view(ctx.project_id, ctx.config.page_name_id)


def gps(ctx: CheckContext, enumerator: str) -> tuple[IssueCounts, ...]:
    """GPS points flagged as outliers and not yet reviewed."""
    config = ctx.config
    headline = cached_headline(
        ctx,
        "gps",
        lambda c: gpschecks_headline(
            c.project_id,
            config.page_name_id,
            c.data.page_data,
            gps_config(c),
            alias=config.survey_data_name,
        ),
        view_key=_gps_view,
    )
    if headline is None or headline.basis is None:
        return ()
    return (
        IssueCounts(
            "GPS",
            "GPS point far from the others",
            "GPS points far from the others",
            headline.basis.unreviewed_by(enumerator),
        ),
    )


def backchecks(ctx: CheckContext, enumerator: str) -> tuple[IssueCounts, ...]:
    """Backcheck mismatches, at a rate per value compared above the team's."""
    config = ctx.config
    backcheck_data = ctx.data.backcheck_data_with_rows
    if backcheck_data is None:
        return ()
    result = cached_on_page(
        ctx,
        ("backchecks_by_enumerator", enumerator),
        lambda: backcheck_mismatches_by_enumerator(
            ctx.project_id,
            config.page_name_id,
            ctx.data.page_data,
            backcheck_data,
            config.setting_file,
            backcheck_config(ctx),
            enumerator,
        ),
    )
    if result is None:
        return ()
    return (
        IssueCounts(
            "Backchecks",
            "backcheck mismatch",
            "backcheck mismatches",
            result.mismatches,
            rule=CountRule.RELATIVE,
            denominators=result.compared,
            per="value compared",
        ),
    )
