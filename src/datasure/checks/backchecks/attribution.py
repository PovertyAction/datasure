"""Attribution of backcheck mismatches to an error source.

Reviewers record whether a mismatch came from the enumerator, the
backchecker or the respondent. Attribution never changes the survey or
backcheck data, the mismatch counts or the regular error rate: it only feeds
the adjusted error rate.

Attributions are kept in an append-only table in the `logs` db. The latest
entry for each survey KEY, backcheck KEY and column wins, and applies only
while the survey and backcheck values still equal the ones attributed.

Kept free of Streamlit so the logic can be tested without a running app.
"""

from datetime import datetime
from enum import StrEnum

import polars as pl

from datasure.checks.backchecks.models import merged_backcheck_name
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table


class ErrorSource(StrEnum):
    """Who caused a backcheck mismatch. Values are stored in the log."""

    ENUMERATOR = "Enumerator"
    BACKCHECKER = "Backchecker"
    RESPONDENT = "Respondent"
    UNATTRIBUTED = "Unattributed"


# Sources that excuse a mismatch from someone's adjusted rate need a reason.
_NOTE_REQUIRED_SOURCES = (ErrorSource.BACKCHECKER, ErrorSource.RESPONDENT)

# Mismatches attributed to these sources are left out of each staff type's
# adjusted error rate.
_EXCUSED_SOURCES: dict[str, tuple[ErrorSource, ...]] = {
    "enumerator": (ErrorSource.BACKCHECKER, ErrorSource.RESPONDENT),
    "backchecker": (ErrorSource.ENUMERATOR, ErrorSource.RESPONDENT),
}

# Added to the comparison results by `mark_error_sources`: the error source
# of each mismatch, null for other rows.
ERROR_SOURCE_COL = "error_source"

MISMATCH = "mismatch"

# Schema of a persisted attribution log, in column order. Keys and values
# are stored as text, so they are compared as text.
ATTRIBUTION_LOG_SCHEMA: dict[str, pl.DataType] = {
    "survey_key": pl.String,
    "backcheck_key": pl.String,
    "column_name": pl.String,
    "survey_value": pl.String,
    "backcheck_value": pl.String,
    "source": pl.String,
    "note": pl.String,
    # Who attributed: the reviewer name set in the app, else the OS login.
    "user": pl.String,
    "date": pl.Datetime("us"),
}

_CELL = ["survey_key", "backcheck_key", "column_name"]


def attribution_table(page_name_id: str) -> str:
    """Return the name of a page's attribution log table in the `logs` db."""
    return f"bc_attribution_{page_name_id}"


def note_required(source: ErrorSource) -> bool:
    """Whether attributing a mismatch to `source` needs a note."""
    return source in _NOTE_REQUIRED_SOURCES


def backcheck_key_col(data: pl.DataFrame, survey_key: str) -> str:
    """Return the backcheck KEY column of the comparison results.

    The merge only adds `{survey_key}__BCCL` when `survey_key` is not the
    merge ID; otherwise the survey and backcheck share `survey_key`.
    """
    backcheck_key = merged_backcheck_name(survey_key)
    return backcheck_key if backcheck_key in data.columns else survey_key


def _cell_values(data: pl.DataFrame, survey_key: str) -> list[pl.Expr]:
    """Select the keys, column and values of comparison results as log text."""
    return [
        pl.col(survey_key).cast(pl.String).alias("survey_key"),
        pl.col(backcheck_key_col(data, survey_key))
        .cast(pl.String)
        .alias("backcheck_key"),
        pl.col("column_name").cast(pl.String),
        pl.col("survey_value").cast(pl.String),
        pl.col("backcheck_value").cast(pl.String),
    ]


def is_mismatch() -> pl.Expr:
    """Whether a row of comparison results is a mismatch."""
    return pl.col("match_status") == MISMATCH


def rows_to_review(
    table: pl.DataFrame, clicked_row: int, selected_rows: list[int]
) -> pl.DataFrame:
    """Return the mismatch rows of `table` that a Review click covers.

    Clicking Review on a selected row covers every selected row; on any
    other row, just that row. Only mismatches can be attributed, so other
    rows are dropped. Positions no longer in `table` are ignored.
    """
    rows = selected_rows if clicked_row in selected_rows else [clicked_row]
    rows = [row for row in rows if 0 <= row < table.height]
    if not rows:
        return table.clear()
    return table[rows].filter(is_mismatch())


def build_attribution_entries(
    rows: pl.DataFrame,
    survey_key: str,
    source: ErrorSource,
    note: str | None,
    user: str,
    date: datetime,
) -> pl.DataFrame:
    """Return the attribution log entries for attributing `rows` to `source`.

    Parameters
    ----------
    rows : pl.DataFrame
        Comparison results to attribute, each a mismatch.
    survey_key : str
        The Survey KEY column in `rows`.
    source : ErrorSource
        The error source to record.
    note : str | None
        The reviewer's note; required for Backchecker and Respondent.
    user : str
        Who made the attribution.
    date : datetime
        When the attribution was made.

    Raises
    ------
    ValueError
        If there are no rows, a row is not a mismatch, or a required note is
        blank.
    """
    if rows.is_empty():
        raise ValueError("No mismatches to attribute")
    if not rows.select(is_mismatch().all()).item():
        raise ValueError("Only a mismatch can be attributed to an error source")
    note = (note or "").strip() or None
    if note_required(source) and note is None:
        raise ValueError(f"A note is required to attribute a mismatch to {source}")

    return rows.select(
        *_cell_values(rows, survey_key),
        pl.lit(str(source), dtype=pl.String).alias("source"),
        pl.lit(note, dtype=pl.String).alias("note"),
        pl.lit(user, dtype=pl.String).alias("user"),
        pl.lit(date, dtype=ATTRIBUTION_LOG_SCHEMA["date"]).alias("date"),
    )


def mark_error_sources(
    analysis: pl.DataFrame, log: pl.DataFrame, survey_key: str
) -> pl.DataFrame:
    """Add `ERROR_SOURCE_COL` to comparison results.

    Each mismatch gets the source of its latest attribution, if the survey
    and backcheck values still equal the attributed ones, else
    Unattributed. Other rows get null, whatever the log holds.

    Parameters
    ----------
    analysis : pl.DataFrame
        Output of `compute_backcheck_analysis`.
    log : pl.DataFrame
        The attribution log, in the order entries were made.
    survey_key : str
        The Survey KEY column in `analysis`.

    Returns
    -------
    pl.DataFrame
        `analysis` in the same order, plus `ERROR_SOURCE_COL`.
    """
    if analysis.is_empty():
        return analysis

    latest = log.select(
        *(pl.col(col).cast(pl.String) for col in _CELL),
        pl.col("survey_value").cast(pl.String).alias("_survey_value"),
        pl.col("backcheck_value").cast(pl.String).alias("_backcheck_value"),
        pl.col("source").cast(pl.String).alias("_source"),
    ).unique(subset=_CELL, keep="last", maintain_order=True)

    # Match in a frame of our own columns, so they can't clash with a
    # survey KEY of the same name.
    cells = analysis.select(
        *_cell_values(analysis, survey_key),
        pl.col("match_status"),
    ).join(latest, on=_CELL, how="left", maintain_order="left")

    still_applies = pl.col("survey_value").eq_missing(pl.col("_survey_value")) & pl.col(
        "backcheck_value"
    ).eq_missing(pl.col("_backcheck_value"))
    source = cells.select(
        pl.when(~is_mismatch())
        .then(pl.lit(None, dtype=pl.String))
        .when(pl.col("_source").is_not_null() & still_applies)
        .then(pl.col("_source"))
        .otherwise(pl.lit(str(ErrorSource.UNATTRIBUTED)))
        .alias(ERROR_SOURCE_COL)
    )
    return analysis.with_columns(source.get_columns())


def _mismatch_sources(rows: pl.DataFrame) -> pl.Series:
    """Return the error source of each mismatch in `rows`."""
    mismatches = rows.filter(is_mismatch()) if "match_status" in rows.columns else rows
    if ERROR_SOURCE_COL not in mismatches.columns:
        return pl.Series([str(ErrorSource.UNATTRIBUTED)] * mismatches.height)
    return mismatches.get_column(ERROR_SOURCE_COL).fill_null(
        str(ErrorSource.UNATTRIBUTED)
    )


def count_error_sources(rows: pl.DataFrame) -> dict[ErrorSource, int]:
    """Count the mismatches in `rows` by error source.

    Without `ERROR_SOURCE_COL`, every mismatch is Unattributed.
    """
    if rows.is_empty():
        return dict.fromkeys(ErrorSource, 0)
    sources = _mismatch_sources(rows).to_list()
    return {source: sources.count(str(source)) for source in ErrorSource}


def excused_mismatches(rows: pl.DataFrame, staff_type: str) -> int:
    """Count the mismatches left out of `staff_type`'s adjusted error rate."""
    if staff_type not in _EXCUSED_SOURCES:
        raise ValueError(
            f"Unknown staff type '{staff_type}'; expected one of "
            f"{', '.join(_EXCUSED_SOURCES)}"
        )
    counts = count_error_sources(rows)
    return sum(counts[source] for source in _EXCUSED_SOURCES[staff_type])


def adjusted_error_rate(
    mismatches: int, compared: int, rows: pl.DataFrame, staff_type: str
) -> float:
    """Return `staff_type`'s adjusted error rate, in percent.

    The denominator is the values compared, as for the regular rate.
    Enumerators: (mismatches - Backchecker - Respondent) / compared.
    Backcheckers: (mismatches - Enumerator - Respondent) / compared.
    Unattributed mismatches always count.
    """
    excused = excused_mismatches(rows, staff_type)
    if compared <= 0:
        return 0.0
    return round((mismatches - excused) / compared * 100, 2)


def attributed_share(analysis: pl.DataFrame) -> float | None:
    """Return the % of mismatches attributed to a source, None if none."""
    if analysis.is_empty() or "match_status" not in analysis.columns:
        return None
    counts = count_error_sources(analysis)
    total = sum(counts.values())
    if total == 0:
        return None
    return (total - counts[ErrorSource.UNATTRIBUTED]) / total * 100


def load_attribution_log(project_id: str, page_name_id: str) -> pl.DataFrame:
    """Return a page's attribution log, in the order entries were made."""
    log = duckdb_get_table(project_id, attribution_table(page_name_id), "logs")
    if log.width == 0:
        return pl.DataFrame(schema=ATTRIBUTION_LOG_SCHEMA)
    return log.select(
        pl.col(col).cast(dtype) for col, dtype in ATTRIBUTION_LOG_SCHEMA.items()
    )


def save_attributions(
    project_id: str, page_name_id: str, entries: pl.DataFrame
) -> None:
    """Append `entries` to a page's attribution log. Earlier entries are kept."""
    log = pl.concat(
        [load_attribution_log(project_id, page_name_id), entries], how="vertical"
    )
    duckdb_save_table(project_id, log, attribution_table(page_name_id), "logs")


def attribution_history(log: pl.DataFrame) -> pl.DataFrame:
    """Return the attribution log newest first, for display."""
    return (
        log.with_row_index("_order")
        .sort(["date", "_order"], descending=True, nulls_last=True)
        .drop("_order")
    )
