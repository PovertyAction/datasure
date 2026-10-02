"""Review of outlier and constraint flags against the correction log.

A flag is reviewed when the correction log holds an active acceptance for
its KEY and column under the same check type (see
`CorrectionProcessor.get_active_acceptances`). Reviewed flags are hidden from
the tables unless the user asks to see them, and are left out of the flag
counts. Outlier and constraint acceptances are independent: accepting an
outlier does not review a constraint violation on the same cell.

A cell whose current value comes from a correction (see
`CorrectionProcessor.get_active_corrections`) is marked corrected. Corrected
values are shown with the reviewed ones, but a corrected value that is still
flagged stays visible and counted: it still needs attention.

Kept free of Streamlit so the logic can be tested without a running app.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl

from datasure.processing.correction_log import HARD_SEVERITY, Action

REVIEW_STATUS_COL = "review status"
REVIEW_REASON_COL = "review reason"
REVIEWED_BADGE = "Reviewed"
CORRECTED_BADGE = "Corrected"


@dataclass(frozen=True)
class FlagCheck:
    """How one check reports its flags in the computed results."""

    check_type: str
    reason_col: str
    no_flag: str


OUTLIERS = FlagCheck("outliers", "outlier reason", "no outlier")
CONSTRAINTS = FlagCheck("constraints", "violation reason", "no violation")

# Flag columns of the computed results that the review logic reads.
COLUMN_NAME_COL = "column name"
# Added to the constraint table by `_render_constraint_violations_table`.
VIOLATION_TYPE_COL = "violation type"

# Violation types (see `_render_constraint_violations_table`) of hard bounds.
_HARD_VIOLATION_TYPES = ("Hard Min", "Hard Max")


@dataclass(frozen=True)
class FlagSelection:
    """The flag behind a selected table row, used to prefill the form."""

    key_value: Any
    column: str
    check_type: str
    flagged: bool
    reviewed: bool
    hard: bool


def _is_flagged(check: FlagCheck) -> pl.Expr:
    return pl.col(check.reason_col).is_not_null() & (
        pl.col(check.reason_col) != check.no_flag
    )


def _latest_entry_by_cell(log_rows: pl.DataFrame, prefix: str) -> pl.DataFrame:
    """Return the latest log reason and severity per KEY and column, for a join.

    The log stores KEY as text, so keys are compared as text. Logs without
    a severity column have a null severity.
    """
    severity = (
        pl.col("severity").cast(pl.String)
        if "severity" in log_rows.columns
        else pl.lit(None, dtype=pl.String)
    )
    return log_rows.select(
        pl.col("KEY").cast(pl.String).alias("_review_key"),
        pl.col("column").cast(pl.String).alias("_review_column"),
        pl.col("reason").cast(pl.String).alias(f"_{prefix}_reason"),
        severity.alias(f"_{prefix}_severity"),
    ).unique(subset=["_review_key", "_review_column"], keep="last")


def _is_hard_violation(check: FlagCheck) -> pl.Expr:
    """Whether a row's flag is a hard constraint violation.

    Matches the reasons written by `compute_constraint_violations`.
    """
    return (
        pl.col(check.reason_col)
        .fill_null("")
        .str.contains("below hard minimum|above hard maximum")
    )


def mark_reviewed(
    flags: pl.DataFrame,
    acceptances: pl.DataFrame,
    survey_key: str,
    check: FlagCheck,
    corrections: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Add review status and reason columns to computed flags.

    Parameters
    ----------
    flags : pl.DataFrame
        Output of `compute_outlier_output` or `compute_constraint_violations`:
        one row per KEY and column name.
    acceptances : pl.DataFrame
        The active acceptances for `check`, as returned by
        `CorrectionProcessor.get_active_acceptances`.
    survey_key : str
        The Survey KEY column in `flags`.
    check : FlagCheck
        The check that produced `flags`.
    corrections : pl.DataFrame | None
        The active value corrections, as returned by
        `CorrectionProcessor.get_active_corrections`.

    Returns
    -------
    pl.DataFrame
        `flags` in the same order, plus `REVIEW_STATUS_COL` and
        `REVIEW_REASON_COL`: `REVIEWED_BADGE` and the acceptance reason for
        an accepted flag (only flagged rows can be accepted),
        `CORRECTED_BADGE` and the correction reason for a corrected cell,
        otherwise null. An acceptance takes precedence over a correction.
    """
    if flags.is_empty():
        return flags

    if corrections is None:
        corrections = acceptances.clear()

    keyed = flags.with_columns(
        pl.col(survey_key).cast(pl.String).alias("_review_key"),
        pl.col(COLUMN_NAME_COL).cast(pl.String).alias("_review_column"),
    )
    for prefix, log_rows in (("accept", acceptances), ("correct", corrections)):
        keyed = keyed.join(
            _latest_entry_by_cell(log_rows, prefix),
            on=["_review_key", "_review_column"],
            how="left",
            maintain_order="left",
        )

    # An acceptance covers a hard violation only if it was confirmed as one:
    # a value accepted as a soft violation can become hard when bounds are
    # tightened, and must then be confirmed again.
    accepted = (
        _is_flagged(check)
        & pl.col("_accept_reason").is_not_null()
        & (
            ~_is_hard_violation(check)
            | (pl.col("_accept_severity").fill_null("") == HARD_SEVERITY)
        )
    )
    corrected = pl.col("_correct_reason").is_not_null()
    return keyed.with_columns(
        pl.when(accepted)
        .then(pl.lit(REVIEWED_BADGE))
        .when(corrected)
        .then(pl.lit(CORRECTED_BADGE))
        .alias(REVIEW_STATUS_COL),
        pl.when(accepted)
        .then(pl.col("_accept_reason"))
        .when(corrected)
        .then(pl.col("_correct_reason"))
        .alias(REVIEW_REASON_COL),
    ).drop(
        "_review_key",
        "_review_column",
        "_accept_reason",
        "_accept_severity",
        "_correct_reason",
        "_correct_severity",
    )


def _is_reviewed() -> pl.Expr:
    """Whether a row is an accepted flag (not merely a corrected value)."""
    return pl.col(REVIEW_STATUS_COL).fill_null("") == REVIEWED_BADGE


def clear_reviewed_flags(flags: pl.DataFrame, check: FlagCheck) -> pl.DataFrame:
    """Return `flags` with reviewed flags reported as unflagged, for metrics.

    Rows are kept, so the number of columns checked is unchanged.
    """
    if REVIEW_STATUS_COL not in flags.columns:
        return flags
    return flags.with_columns(
        pl.when(_is_reviewed())
        .then(pl.lit(check.no_flag))
        .otherwise(pl.col(check.reason_col))
        .alias(check.reason_col)
    )


_REVIEWED_ROW_STYLE = "background-color: rgba(25, 135, 84, 0.15)"


def highlight_reviewed_row(row: Any) -> list[str]:
    """Style every cell of an accepted or corrected row green in a table.

    Used with a pandas ``Styler`` (``df.style.apply(highlight_reviewed_row,
    axis=1)``) when "Show reviewed" is on.
    """
    status = row.get(REVIEW_STATUS_COL)
    # Missing values may be pd.NA, which can't be used in a boolean test.
    is_reviewed = isinstance(status, str) and status in (
        REVIEWED_BADGE,
        CORRECTED_BADGE,
    )
    return [_REVIEWED_ROW_STYLE if is_reviewed else ""] * len(row)


def flagged_only(flags: pl.DataFrame, check: FlagCheck) -> pl.DataFrame:
    """Return the rows of `flags` that `check` flagged."""
    if check.reason_col not in flags.columns:
        return flags
    return flags.filter(_is_flagged(check))


def visible_flags(flags: pl.DataFrame, *, show_reviewed: bool) -> pl.DataFrame:
    """Return the rows and columns of `flags` to show in a results table.

    Reviewed flags and the review columns are hidden unless `show_reviewed`.
    """
    if REVIEW_STATUS_COL not in flags.columns:
        return flags
    if show_reviewed:
        return flags
    return flags.filter(~_is_reviewed()).drop(REVIEW_STATUS_COL, REVIEW_REASON_COL)


@dataclass(frozen=True)
class TableFilters:
    """The toggles above a results table.

    Attributes
    ----------
    flagged_only : bool
        Show only flagged values.
    show_reviewed : bool
        Also show accepted flags, with the review columns.
    reviewed_only : bool
        Show only accepted and corrected rows, whatever the other toggles.
    """

    flagged_only: bool = True
    show_reviewed: bool = False
    reviewed_only: bool = False


def filter_table(
    flags: pl.DataFrame, filters: TableFilters, check: FlagCheck
) -> pl.DataFrame:
    """Return the rows and columns of marked `flags` that `filters` show."""
    if filters.reviewed_only:
        # A value corrected into range is unflagged, so flagged-only and
        # show-reviewed are ignored here.
        if REVIEW_STATUS_COL not in flags.columns:
            return flags.clear()
        return flags.filter(pl.col(REVIEW_STATUS_COL).is_not_null())

    flags = visible_flags(flags, show_reviewed=filters.show_reviewed)
    if filters.flagged_only:
        flags = flagged_only(flags, check)
    return flags


SURVEY_COL_SUFFIX = " (survey)"


def join_survey_columns(
    survey: pl.DataFrame,
    flags: pl.DataFrame,
    survey_key: str,
    check: FlagCheck,
    *,
    reserved: Sequence[str] = (),
) -> pl.DataFrame:
    """Join survey display columns onto `flags` for a results table.

    The flag columns stay authoritative: a survey column named like one of
    them, or like a `reserved` column added afterwards, is renamed with
    `SURVEY_COL_SUFFIX`. Otherwise a survey field called "column name"
    would become the correction target.

    The result is sorted by KEY, column name and flag reason, so a row
    position reported by a Review click resolves to the same flag on the
    rerun it triggers whatever order the join returns.
    """
    taken = set(flags.columns) | set(reserved) | set(survey.columns)
    renames = {}
    for col in survey.columns:
        if col == survey_key or (col not in flags.columns and col not in reserved):
            continue
        new_name = f"{col}{SURVEY_COL_SUFFIX}"
        while new_name in taken:
            new_name = f"{new_name}{SURVEY_COL_SUFFIX}"
        renames[col] = new_name
        taken.add(new_name)

    joined = survey.rename(renames).join(flags, on=survey_key, how="inner")
    sort_cols = [
        col
        for col in (survey_key, COLUMN_NAME_COL, check.reason_col)
        if col in joined.columns
    ]
    return joined.sort(sort_cols, nulls_last=True, maintain_order=True)


def select_flag(
    table: pl.DataFrame,
    rows: list[int],
    survey_key: str,
    check: FlagCheck,
) -> FlagSelection | None:
    """Return the flag behind the selected row of a results table.

    Parameters
    ----------
    table : pl.DataFrame
        The table as displayed.
    rows : list[int]
        Selected row positions, as reported by `st.dataframe` selection.
    survey_key : str
        The Survey KEY column in `table`.
    check : FlagCheck
        The check the table shows.

    Returns
    -------
    FlagSelection | None
        The selection, or None if no row is selected or the position no
        longer exists in `table`.
    """
    if not rows or not 0 <= rows[0] < table.height:
        return None

    row = table.row(rows[0], named=True)
    flagged = check.reason_col in table.columns and bool(
        table.slice(rows[0], 1).select(_is_flagged(check)).item()
    )
    return FlagSelection(
        key_value=row[survey_key],
        column=row[COLUMN_NAME_COL],
        check_type=check.check_type,
        flagged=flagged,
        reviewed=row.get(REVIEW_STATUS_COL) == REVIEWED_BADGE,
        hard=row.get(VIOLATION_TYPE_COL) in _HARD_VIOLATION_TYPES,
    )


def allowed_actions(selection: FlagSelection) -> list[Action]:
    """Return the actions the correction form offers for `selection`.

    A value can be accepted only while it is flagged and not yet reviewed.
    Rows are removed from the Corrections page, not from a check page.
    """
    actions = [Action.MODIFY_VALUE, Action.REMOVE_VALUE]
    if selection.flagged and not selection.reviewed:
        actions.append(Action.ACCEPT)
    return actions


def needs_hard_confirmation(selection: FlagSelection, action: Action) -> bool:
    """Whether applying `action` needs the hard-violation confirmation step."""
    return action == Action.ACCEPT and selection.hard
