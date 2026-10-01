"""Review of outlier and constraint flags against accepted values.

A flag is reviewed when the correction log holds an active acceptance for
its KEY and column under the same check type (see
`CorrectionProcessor.get_active_acceptances`). Reviewed flags are hidden from
the tables unless the user asks to see them, and are left out of the flag
counts. Outlier and constraint acceptances are independent: accepting an
outlier does not review a constraint violation on the same cell.

Kept free of Streamlit so the logic can be tested without a running app.
"""

from dataclasses import dataclass
from typing import Any

import polars as pl

from datasure.processing.correction_log import Action

REVIEW_STATUS_COL = "review status"
REVIEW_REASON_COL = "review reason"
REVIEWED_BADGE = "Reviewed"


@dataclass(frozen=True)
class FlagCheck:
    """How one check reports its flags in the computed results."""

    check_type: str
    reason_col: str
    no_flag: str


OUTLIERS = FlagCheck("outliers", "outlier reason", "no outlier")
CONSTRAINTS = FlagCheck("constraints", "violation reason", "no violation")

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


def mark_reviewed(
    flags: pl.DataFrame,
    acceptances: pl.DataFrame,
    survey_key: str,
    check: FlagCheck,
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

    Returns
    -------
    pl.DataFrame
        `flags` in the same order, plus `REVIEW_STATUS_COL` (the reviewed
        badge, or null) and `REVIEW_REASON_COL` (the acceptance reason, or
        null). Only flagged rows can be reviewed.
    """
    if flags.is_empty():
        return flags

    # The log stores KEY as text; the latest acceptance's reason wins.
    accepted = acceptances.select(
        pl.col("KEY").cast(pl.String).alias("_review_key"),
        pl.col("column").cast(pl.String).alias("_review_column"),
        pl.lit(REVIEWED_BADGE).alias(REVIEW_STATUS_COL),
        pl.col("reason").cast(pl.String).alias(REVIEW_REASON_COL),
    ).unique(subset=["_review_key", "_review_column"], keep="last")

    marked = (
        flags.with_columns(
            pl.col(survey_key).cast(pl.String).alias("_review_key"),
            pl.col("column name").cast(pl.String).alias("_review_column"),
        )
        .join(
            accepted,
            on=["_review_key", "_review_column"],
            how="left",
            maintain_order="left",
        )
        .drop("_review_key", "_review_column")
    )

    flagged = _is_flagged(check)
    return marked.with_columns(
        pl.when(flagged).then(pl.col(REVIEW_STATUS_COL)).alias(REVIEW_STATUS_COL),
        pl.when(flagged).then(pl.col(REVIEW_REASON_COL)).alias(REVIEW_REASON_COL),
    )


def _is_reviewed() -> pl.Expr:
    return pl.col(REVIEW_STATUS_COL).is_not_null()


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
    """Style every cell of a reviewed flag green in a results table.

    Used with a pandas ``Styler`` (``df.style.apply(highlight_reviewed_row,
    axis=1)``) when "Show reviewed" is on.
    """
    status = row.get(REVIEW_STATUS_COL)
    style = _REVIEWED_ROW_STYLE if status == REVIEWED_BADGE else ""
    return [style] * len(row)


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
        column=row["column name"],
        check_type=check.check_type,
        flagged=flagged,
        reviewed=row.get(REVIEW_STATUS_COL) is not None,
        hard=row.get("violation type") in _HARD_VIOLATION_TYPES,
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
