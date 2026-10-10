"""The records the backcheck comparison and coverage use.

The Backchecks page checks the same records as the Duplicates tab: the survey
and backcheck Records to Include filters saved there apply here too. Records
whose survey ID is duplicated among the included records are then left out of
the comparison (`compute.exclude_duplicate_ids`) until they are resolved on
the duplicate cards. This module applies the filters and counts the ID
problems that keep records out, for the page to report.
"""

from dataclasses import dataclass

import polars as pl

from datasure.checks.duplicates import (
    BACKCHECK_PREFIX,
    FilteredRecords,
    describe_records_to_include,
    filter_records_to_include,
    saved_records_to_include,
)
from datasure.checks.id_duplicates import find_duplicate_groups, find_unmatched_ids


@dataclass(frozen=True)
class ComparisonScope:
    """The survey and backcheck records the comparison uses.

    Attributes
    ----------
    survey, backcheck : FilteredRecords
        The records each Records to Include filter keeps.
    survey_total, backcheck_total : int
        The number of records before filtering.
    survey_filter, backcheck_filter : str | None
        Descriptions of the active filters, or None when a filter is not set.
    """

    survey: FilteredRecords
    backcheck: FilteredRecords
    survey_total: int
    backcheck_total: int
    survey_filter: str | None
    backcheck_filter: str | None


def comparison_scope(
    survey_data: pl.DataFrame, backcheck_data: pl.DataFrame, setting_file: str
) -> ComparisonScope:
    """Apply the page's saved Records to Include filters to both datasets.

    An invalid filter keeps no records; its error is on the returned
    `FilteredRecords`.
    """
    survey_conditions = saved_records_to_include(setting_file)
    backcheck_conditions = saved_records_to_include(setting_file, BACKCHECK_PREFIX)
    return ComparisonScope(
        survey=filter_records_to_include(survey_data, survey_conditions, "survey"),
        backcheck=filter_records_to_include(
            backcheck_data, backcheck_conditions, "backcheck"
        ),
        survey_total=survey_data.height,
        backcheck_total=backcheck_data.height,
        survey_filter=describe_records_to_include(survey_conditions),
        backcheck_filter=describe_records_to_include(backcheck_conditions),
    )


def scope_captions(scope: ComparisonScope) -> list[str]:
    """Return one line per active filter, e.g. "Comparing 1,240 of 1,310 surveys"."""
    lines = []
    for noun, records, total, description in (
        ("surveys", scope.survey, scope.survey_total, scope.survey_filter),
        ("backchecks", scope.backcheck, scope.backcheck_total, scope.backcheck_filter),
    ):
        if description:
            lines.append(
                f"Comparing {records.data.height:,} of {total:,} {noun} "
                f"(Records to Include: {description})"
            )
    return lines


@dataclass(frozen=True)
class IdProblemCounts:
    """ID problems that keep included records out of the comparison."""

    duplicate_survey_ids: int
    duplicate_backcheck_ids: int
    unmatched_ids: int


def _duplicate_ids(data: pl.DataFrame, id_col: str) -> int:
    if id_col not in data.columns:
        return 0
    return find_duplicate_groups(data, id_col, None, None).height


def id_problem_counts(
    scope: ComparisonScope, survey_data: pl.DataFrame, id_col: str | None
) -> IdProblemCounts:
    """Count the duplicate and unmatched IDs among the included records.

    As on the Duplicates tab, a backcheck is unmatched when its ID is on no
    survey record at all, included or not. Counts are 0 when the ID column
    is not configured.
    """
    if not id_col:
        return IdProblemCounts(0, 0, 0)
    backcheck = scope.backcheck.data
    unmatched = 0
    if id_col in backcheck.columns:
        unmatched = find_unmatched_ids(
            backcheck, survey_data, id_col, None, None
        ).height
    return IdProblemCounts(
        duplicate_survey_ids=_duplicate_ids(scope.survey.data, id_col),
        duplicate_backcheck_ids=_duplicate_ids(backcheck, id_col),
        unmatched_ids=unmatched,
    )


def _count_text(n: int, noun: str) -> str:
    return f"{n} {noun}" + ("" if n == 1 else "s")


def id_problem_warning(counts: IdProblemCounts) -> str | None:
    """Describe the ID problems left out of the comparison, or None if none."""
    parts = [
        _count_text(n, noun)
        for n, noun in (
            (counts.duplicate_survey_ids, "duplicate survey ID"),
            (counts.duplicate_backcheck_ids, "duplicate backcheck ID"),
            (counts.unmatched_ids, "unmatched backcheck ID"),
        )
        if n
    ]
    if not parts:
        return None
    listed = parts[0] if len(parts) == 1 else f"{', '.join(parts[:-1])} and {parts[-1]}"
    total = (
        counts.duplicate_survey_ids
        + counts.duplicate_backcheck_ids
        + counts.unmatched_ids
    )
    verb = "is" if total == 1 else "are"
    pronoun = "it" if total == 1 else "them"
    return (
        f"{listed} {verb} left out of the comparison. Resolve {pronoun} on the "
        f"Duplicates tab to include {pronoun}."
    )
