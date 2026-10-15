"""Schema and vocabulary of the correction log (`corr_log_{alias}`).

Kept free of Streamlit so the replication package can read logs with the
same schema and backfill rules as `CorrectionProcessor`.
"""

from enum import StrEnum

import polars as pl

CORRECTIONS_PAGE_SOURCE = "corrections_page"


class Action(StrEnum):
    """An action recorded in the correction log's `action` column.

    Values are stored in persisted logs and matched on replay and by the
    replication script, so changing one requires migrating existing logs.
    """

    MODIFY_VALUE = "modify value"
    REMOVE_VALUE = "remove value"
    REMOVE_ROW = "remove row"
    # Records that a flagged value was reviewed and is correct. It never
    # changes the data; check pages use it to stop flagging the value.
    ACCEPT = "accept"


# Actions that change the data when a correction is applied or replayed.
CORRECTION_ACTIONS: tuple[Action, ...] = (
    Action.MODIFY_VALUE,
    Action.REMOVE_VALUE,
    Action.REMOVE_ROW,
)

# Backchecks is deliberately absent: backcheck results measure data quality,
# so a mismatch can't be accepted away. The Backchecks page attributes
# mismatches to an error source instead (see checks/backchecks/attribution.py).
# Duplicates is absent too: an ID belongs to one record, so each duplicate ID
# is resolved on its card (see checks/id_corrections.py), not accepted.
ACCEPT_CHECK_TYPES = ("outliers", "constraints", "gps")

# `severity` of an acceptance that overrides a hard constraint bound.
HARD_SEVERITY = "hard"

# Full schema of a persisted correction log (`corr_log_{alias}`), in column order.
CORRECTION_LOG_SCHEMA: dict[str, pl.DataType] = {
    "date": pl.Datetime("us"),
    "KEY": pl.String,
    "ID": pl.String,
    "action": pl.String,
    "column": pl.String,
    "current_value": pl.String,
    "new_value": pl.String,
    "reason": pl.String,
    "status": pl.String,
    "status_reason": pl.String,
    "source": pl.String,
    "check_type": pl.String,
    # For "accept", how serious the accepted flag is: "hard" for a hard
    # constraint violation, null otherwise.
    "severity": pl.String,
    # Who made the entry: the reviewer name set in the app, else the OS login.
    "user": pl.String,
}

# Values given to columns that were added to the log after some logs were
# already persisted. Every legacy entry came from the Corrections page and
# was applied successfully when it was logged. Who made it was not recorded.
_LOG_BACKFILL_DEFAULTS: dict[str, str | None] = {
    "status": "Successful",
    "status_reason": None,
    "source": CORRECTIONS_PAGE_SOURCE,
    "check_type": None,
    "severity": None,
    "user": None,
}


def ensure_log_columns(df: pl.DataFrame) -> pl.DataFrame:
    """Backfill columns missing from logs persisted before those columns existed."""
    if df.width == 0:
        return df
    for column, default in _LOG_BACKFILL_DEFAULTS.items():
        if column not in df.columns:
            df = df.with_columns(
                pl.lit(default, dtype=CORRECTION_LOG_SCHEMA[column]).alias(column)
            )
    return df


def empty_correction_log() -> pl.DataFrame:
    """Return a correction log with no entries and the full schema."""
    return pl.DataFrame(schema=CORRECTION_LOG_SCHEMA)
