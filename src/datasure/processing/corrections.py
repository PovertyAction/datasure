import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import polars as pl
import streamlit as st

from datasure.processing.correction_log import (
    ACCEPT_CHECK_TYPES,
    CORRECTION_ACTIONS,
    CORRECTION_LOG_SCHEMA,
    CORRECTIONS_PAGE_SOURCE,
    Action,
    empty_correction_log,
    ensure_log_columns,
)
from datasure.utils.duckdb_utils import (
    duckdb_get_table,
    duckdb_save_table,
    duckdb_table_exists,
)
from datasure.utils.reapply_utils import ReapplyFailure


def _describe_correction_row(row: dict[str, Any]) -> str:
    """Build a human-readable description of a correction-log row.

    Parameters
    ----------
    row : dict[str, Any]
        A single row from the correction log

    Returns
    -------
    str
        Description such as "Modify {column} for key {key_value} to '{new_value}'"
    """
    action = row["action"]
    key_value = row["KEY"]
    column = row["column"]
    new_value = row["new_value"]

    if action == Action.MODIFY_VALUE:
        return f"Modify {column} for key {key_value} to '{new_value}'"
    if action == Action.REMOVE_VALUE:
        return f"Remove {column} value for key {key_value}"
    if action == Action.REMOVE_ROW:
        return f"Remove entire row for key {key_value}"
    if action == Action.ACCEPT:
        target = column if column is not None else "coordinates"
        return f"Accept {row['check_type']} flag on {target} for key {key_value}"
    return f"{action} for key {key_value}"


def _is_missing(value: Any) -> bool:
    """Whether a value is missing: None, or NaN as pandas reports nulls."""
    return value is None or (isinstance(value, float) and math.isnan(value))


def _encode_scalar(value: Any) -> str | None:
    return None if _is_missing(value) else str(value)


def _encode_log_value(value: Any) -> str | None:
    """Encode a value for the log's string-typed value columns.

    Missing values (None or NaN) are stored as null. GPS acceptances cover a
    latitude/longitude pair, passed as a mapping of column name to value and
    stored as JSON. Any other value is stored as a string.
    """
    if isinstance(value, dict):
        return json.dumps(
            {col: _encode_scalar(v) for col, v in value.items()}, sort_keys=True
        )
    return _encode_scalar(value)


def _values_match(actual: Any, recorded: str | None) -> bool:
    """Whether a data value equals a value recorded in the log as a string.

    Missing matches missing. Numbers compare numerically, so an integer cell
    holding 25 matches "25.0", which is how pandas reports an integer column
    that has nulls.
    """
    if _is_missing(actual) or recorded is None:
        return _is_missing(actual) and recorded is None
    if str(actual) == recorded:
        return True
    if isinstance(actual, int | float) and not isinstance(actual, bool):
        try:
            return float(actual) == float(recorded)
        except ValueError:
            return False
    return False


def _accepted_values(row: dict[str, Any]) -> dict[str, str | None]:
    """Return the column -> value snapshot an accept row was recorded against."""
    if row["column"] is not None:
        return {row["column"]: row["current_value"]}
    return json.loads(row["current_value"]) if row["current_value"] else {}


def _acceptance_mismatch(
    data: pl.DataFrame, key_col: str, key_value: Any, accepted: dict[str, str | None]
) -> str | None:
    """Explain why the data doesn't hold the accepted values, or None if it does.

    `accepted` maps each column to its value as encoded in the log. The log
    stores KEY as text, so the key column is compared as text. If the KEY
    appears on several rows, every row must hold the accepted values.
    """
    if key_col not in data.columns:
        return f"Key column '{key_col}' not found in data"
    records = data.filter(pl.col(key_col).cast(pl.String) == str(key_value))
    if records.is_empty():
        return f"Key value '{key_value}' not found in data"
    for column, value in accepted.items():
        if column not in records.columns:
            return f"Column '{column}' not found in data"
        if not all(_values_match(v, value) for v in records[column].to_list()):
            return (
                f"The value of '{column}' for key '{key_value}' has changed since "
                "it was flagged. Refresh the page and review it again."
            )
    return None


def _acceptance_is_active(
    data: pl.DataFrame, key_col: str, row: dict[str, Any]
) -> bool:
    """Whether the data still holds the values an acceptance recorded."""
    return (
        _acceptance_mismatch(data, key_col, row["KEY"], _accepted_values(row)) is None
    )


def _check_acceptance_against_data(
    data: pl.DataFrame,
    key_col: str,
    key_value: Any,
    column: str | None,
    current_value: Any,
) -> None:
    """Raise ValueError unless the data holds the value being accepted.

    The value is encoded exactly as the log will store it, so an acceptance
    that passes this check is active as soon as it is logged.
    """
    accepted = _accepted_values(
        {"column": column, "current_value": _encode_log_value(current_value)}
    )
    mismatch = _acceptance_mismatch(data, key_col, key_value, accepted)
    if mismatch:
        raise ValueError(mismatch)


def _validate_acceptance(
    check_type: str | None, column: str | None, current_value: Any
) -> None:
    """Raise ValueError if an acceptance's check type, column and value don't fit."""
    if check_type not in ACCEPT_CHECK_TYPES:
        raise ValueError(
            f"Unknown check type '{check_type}'; expected one of "
            f"{', '.join(ACCEPT_CHECK_TYPES)}"
        )
    if check_type == "gps":
        if (
            column is not None
            or not isinstance(current_value, dict)
            or len(current_value) != 2
        ):
            raise ValueError(
                "GPS acceptances take no column and a mapping of the "
                "latitude and longitude columns to their values"
            )
    elif not column:
        raise ValueError(f"A column is required to accept a {check_type} value")


def _build_log_row(
    key_value: str,
    current_id: Any | None,
    action: Action,
    column: str | None,
    current_value: Any | None,
    new_value: Any | None,
    reason: str,
    source: str,
    check_type: str | None,
    severity: str | None = None,
) -> dict[str, Any]:
    """Build one correction-log row.

    A freshly logged entry has just been applied successfully (the apply
    step raises before logging otherwise).
    """
    return {
        "date": datetime.now(),
        "KEY": str(key_value),
        "ID": str(current_id) if current_id is not None else None,
        "action": str(action),
        "column": str(column) if column is not None else None,
        "current_value": _encode_log_value(current_value),
        "new_value": _encode_log_value(new_value),
        "reason": str(reason),
        "status": "Successful",
        "status_reason": None,
        "source": str(source),
        "check_type": check_type,
        "severity": severity,
    }


@dataclass(frozen=True)
class CorrectionEntry:
    """One correction or acceptance, applied as part of `apply_corrections`.

    Attributes
    ----------
    key_value : str
        The KEY of the record
    action : Action
        The action to record; see `Action`
    reason : str
        Why the entry is made. Required.
    column : str | None
        The column affected. None for "remove row" and GPS acceptances.
    current_value : Any
        The value before the change, or the value being accepted. For GPS
        acceptances, a mapping of the latitude and longitude columns to their
        values.
    new_value : Any
        The new value, for "modify value"
    survey_id_value : Any
        The Survey ID value for this KEY, recorded in the log's ID column
    check_type : str | None
        For "accept", the check whose flag is accepted
    severity : str | None
        For "accept", how serious the accepted flag is: "hard" for a hard
        constraint violation, otherwise None
    """

    key_value: str
    action: Action
    reason: str
    column: str | None = None
    current_value: Any = None
    new_value: Any = None
    survey_id_value: Any = None
    check_type: str | None = None
    severity: str | None = None


# The cached methods below hash `self` by its project so that two projects
# sharing an alias never share cached data. The key is the class's qualified
# name because the class isn't defined yet when the decorators run.
_PROCESSOR_HASH_FUNCS = {
    "datasure.processing.corrections.CorrectionProcessor": lambda p: p.project_id
}


class CorrectionProcessor:
    """Handles all data correction operations and persistence."""

    def __init__(self, project_id: str) -> None:
        """Initialize the correction processor.

        Parameters
        ----------
        project_id : str
            The project identifier
        """
        self.project_id = project_id

    @st.cache_data(ttl=60, show_spinner=False, hash_funcs=_PROCESSOR_HASH_FUNCS)
    def get_corrected_data(self, alias: str) -> pl.DataFrame:
        """Get corrected data for a given alias.

        If no corrected data exists, initializes from prepped data.

        Parameters
        ----------
        alias : str
            The data alias/table name

        Returns
        -------
        pl.DataFrame
            The corrected data
        """
        corrected_data = duckdb_get_table(
            project_id=self.project_id,
            alias=alias,
            db_name="corrected",
        )

        if corrected_data.is_empty():
            # Initialize from prepped data
            prepped_data = duckdb_get_table(
                project_id=self.project_id,
                alias=alias,
                db_name="prep",
            )
            if not prepped_data.is_empty():
                self.save_corrected_data(alias, prepped_data)
                return prepped_data

        return corrected_data

    def save_corrected_data(self, alias: str, data: pl.DataFrame) -> None:
        """Save corrected data to storage.

        Parameters
        ----------
        alias : str
            The data alias/table name
        data : pl.DataFrame
            The data to save
        """
        duckdb_save_table(
            project_id=self.project_id,
            table_data=data,
            alias=alias,
            db_name="corrected",
        )
        # Clear cache after saving to ensure fresh data
        self.get_corrected_data.clear()
        self.get_data_summary.clear()

    @st.cache_data(ttl=30, show_spinner=False, hash_funcs=_PROCESSOR_HASH_FUNCS)
    def get_correction_log(self, alias: str) -> pl.DataFrame:
        """Get correction log for a given alias.

        Parameters
        ----------
        alias : str
            The data alias/table name

        Returns
        -------
        pl.DataFrame
            The correction log
        """
        return ensure_log_columns(
            duckdb_get_table(
                project_id=self.project_id,
                alias=f"corr_log_{alias}",
                db_name="logs",
            )
        )

    def add_correction_entry(
        self,
        alias: str,
        key_value: str,
        current_id: str | None,
        action: Action,
        column: str | None,
        current_value: Any | None,
        new_value: Any | None,
        reason: str,
        source: str = CORRECTIONS_PAGE_SOURCE,
        check_type: str | None = None,
    ) -> None:
        """Add a new correction entry to the log.

        Parameters
        ----------
        alias : str
            The data alias/table name
        key_value : str
            The key value being corrected
        current_id : str | None
            The Survey ID value for this KEY, if a Survey ID column is
            configured for the dataset
        action : Action
            The correction action
        column : str | None
            The column being modified
        current_value : Any | None
            The current value
        new_value : Any | None
            The new value
        reason : str
            The reason for correction
        source : str
            The page that produced the entry, e.g. "corrections_page" or a
            check page such as "outliers"
        check_type : str | None
            For "accept" entries, the check whose flag was accepted
        """
        self._append_log_rows(
            alias,
            [
                _build_log_row(
                    key_value=key_value,
                    current_id=current_id,
                    action=action,
                    column=column,
                    current_value=current_value,
                    new_value=new_value,
                    reason=reason,
                    source=source,
                    check_type=check_type,
                )
            ],
        )

    def _append_log_rows(self, alias: str, rows: list[dict[str, Any]]) -> None:
        """Append rows to the correction log in a single save.

        Parameters
        ----------
        alias : str
            The data alias/table name
        rows : list[dict[str, Any]]
            Log rows built by `_build_log_row`
        """
        current_log = self.get_correction_log(alias)
        new_rows = pl.DataFrame(rows, schema=CORRECTION_LOG_SCHEMA)

        if current_log.is_empty():
            updated_log = new_rows
        else:
            # Align column order and types with the new rows before concatenating
            aligned_current_log = current_log.select(
                pl.col(name).cast(dtype)
                for name, dtype in CORRECTION_LOG_SCHEMA.items()
            )
            updated_log = pl.concat([aligned_current_log, new_rows])

        duckdb_save_table(
            project_id=self.project_id,
            table_data=updated_log,
            alias=f"corr_log_{alias}",
            db_name="logs",
        )
        # Clear correction log cache so the new entries show immediately
        self.get_correction_log.clear()
        self.get_correction_summary.clear()

    def accept_value(
        self,
        alias: str,
        key_col: str,
        key_value: str,
        check_type: str,
        column: str | None,
        current_value: Any,
        reason: str,
        survey_id_value: Any | None = None,
        source: str | None = None,
    ) -> None:
        """Record that a flagged value was reviewed and is correct.

        The entry never changes the data. It stays active only while the
        data still holds `current_value` (see `get_active_acceptances`).

        Parameters
        ----------
        alias : str
            The data alias/table name
        key_col : str
            The key column name
        key_value : str
            The KEY of the accepted record
        check_type : str
            The check whose flag is accepted, one of `ACCEPT_CHECK_TYPES`
        column : str | None
            The accepted column. None for GPS, which accepts a coordinate pair.
        current_value : Any
            The value being accepted. For GPS, a mapping of the latitude and
            longitude column names to their values.
        reason : str
            Why the value is correct. Required.
        survey_id_value : Any | None
            The Survey ID value for this KEY, if a Survey ID column is
            configured, recorded in the log's ID column
        source : str | None
            The page that produced the entry. Defaults to `check_type`.

        Raises
        ------
        ValueError
            If the check type is unknown, the reason is blank, the column and
            value do not fit the check type, or the corrected data does not
            hold `current_value` for the KEY (for example, because the value
            changed after it was flagged).
        """
        _validate_acceptance(check_type, column, current_value)
        if not reason or not reason.strip():
            raise ValueError("A reason is required to accept a value")
        _check_acceptance_against_data(
            self.get_corrected_data(alias), key_col, key_value, column, current_value
        )

        self.add_correction_entry(
            alias=alias,
            key_value=key_value,
            current_id=survey_id_value,
            action=Action.ACCEPT,
            column=column,
            current_value=current_value,
            new_value=None,
            reason=reason,
            source=source or check_type,
            check_type=check_type,
        )

    def get_active_acceptances(
        self, alias: str, check_type: str, key_col: str
    ) -> pl.DataFrame:
        """Return the acceptances for a check that still apply to the data.

        An acceptance is active only while the corrected data still holds the
        value recorded when it was accepted. For GPS, both the latitude and
        the longitude must still match.

        Parameters
        ----------
        alias : str
            The data alias/table name
        check_type : str
            The check to return acceptances for
        key_col : str
            The Survey KEY column name

        Returns
        -------
        pl.DataFrame
            The active "accept" rows from the correction log, in log order
        """
        log = self.get_correction_log(alias)
        if log.width == 0:
            return empty_correction_log()

        acceptances = log.filter(
            (pl.col("action") == Action.ACCEPT) & (pl.col("check_type") == check_type)
        )
        if acceptances.is_empty():
            return acceptances

        data = self.get_corrected_data(alias)
        is_active = [
            _acceptance_is_active(data, key_col, row)
            for row in acceptances.iter_rows(named=True)
        ]
        return acceptances.filter(pl.Series(is_active, dtype=pl.Boolean))

    def get_active_corrections(self, alias: str, key_col: str) -> pl.DataFrame:
        """Return the value corrections whose result the data still holds.

        A "modify value" is active while the cell holds its new value, and a
        "remove value" while the cell is missing. A correction overwritten by
        a later one, or whose row was removed, is inactive.

        Parameters
        ----------
        alias : str
            The data alias/table name
        key_col : str
            The Survey KEY column name

        Returns
        -------
        pl.DataFrame
            The active "modify value" and "remove value" rows from the
            correction log, in log order
        """
        log = self.get_correction_log(alias)
        if log.width == 0:
            return empty_correction_log()

        corrections = log.filter(
            pl.col("action").is_in([Action.MODIFY_VALUE, Action.REMOVE_VALUE])
            & pl.col("column").is_not_null()
        )
        if corrections.is_empty():
            return corrections

        data = self.get_corrected_data(alias)
        is_active = [
            _acceptance_mismatch(
                data,
                key_col,
                row["KEY"],
                {
                    row["column"]: row["new_value"]
                    if row["action"] == Action.MODIFY_VALUE
                    else None
                },
            )
            is None
            for row in corrections.iter_rows(named=True)
        ]
        return corrections.filter(pl.Series(is_active, dtype=pl.Boolean))

    def apply_correction(
        self,
        alias: str,
        key_col: str,
        key_value: str,
        action: Action,
        column: str | None = None,
        current_value: Any | None = None,
        new_value: Any | None = None,
        reason: str | None = None,
        survey_id_value: Any | None = None,
    ) -> pl.DataFrame:
        """Apply a single correction to the data.

        Parameters
        ----------
        alias : str
            The data alias/table name
        key_col : str
            The key column name
        key_value : str
            The key value to correct
        action : Action
            The correction action; any of `CORRECTION_ACTIONS`
        column : str | None
            The column to modify
        current_value : Any | None
            The current value
        new_value : Any | None
            The new value
        reason : str | None
            The reason for correction
        survey_id_value : Any | None
            The Survey ID value for this KEY, if a Survey ID column is
            configured, recorded in the log's ID column

        Returns
        -------
        pl.DataFrame
            The corrected data
        """
        corrected_data = self._apply_action(
            self.get_corrected_data(alias),
            key_col,
            key_value,
            action,
            column,
            new_value,
        )

        self.save_corrected_data(alias, corrected_data)

        # Add to correction log if reason is provided
        if reason:
            self.add_correction_entry(
                alias=alias,
                key_value=key_value,
                current_id=survey_id_value,
                action=action,
                column=column,
                current_value=current_value,
                new_value=new_value,
                reason=reason,
            )

        return corrected_data

    def apply_corrections(
        self,
        alias: str,
        key_col: str,
        entries: Sequence[CorrectionEntry],
        source: str = CORRECTIONS_PAGE_SOURCE,
    ) -> pl.DataFrame:
        """Apply several corrections and acceptances as one all-or-nothing step.

        Entries are validated and applied in order against the result of the
        entries before them. If any entry is invalid, nothing is saved and
        nothing is logged.

        Parameters
        ----------
        alias : str
            The data alias/table name
        key_col : str
            The key column name
        entries : Sequence[CorrectionEntry]
            The corrections and acceptances to apply, in order
        source : str
            The page that produced the entries, recorded on every log row

        Returns
        -------
        pl.DataFrame
            The corrected data

        Raises
        ------
        ValueError
            If any entry is invalid; the message names the entry's problem.
            Storage errors are re-raised after the corrected data is restored.
        """
        original_data = self.get_corrected_data(alias)
        corrected_data = original_data
        for entry in entries:
            corrected_data = self._apply_entry(corrected_data, key_col, entry)

        log_rows = [
            _build_log_row(
                key_value=entry.key_value,
                current_id=entry.survey_id_value,
                action=entry.action,
                column=entry.column,
                current_value=entry.current_value,
                new_value=entry.new_value,
                reason=entry.reason,
                source=source,
                check_type=entry.check_type,
                severity=entry.severity,
            )
            for entry in entries
        ]

        self.save_corrected_data(alias, corrected_data)
        try:
            self._append_log_rows(alias, log_rows)
        except Exception:
            # Keep data and log in step: undo the data change, then re-raise.
            self.save_corrected_data(alias, original_data)
            raise
        return corrected_data

    def _apply_entry(
        self, data: pl.DataFrame, key_col: str, entry: CorrectionEntry
    ) -> pl.DataFrame:
        """Validate one `CorrectionEntry` against `data` and apply it.

        Raises
        ------
        ValueError
            If the entry is invalid for `data`.
        """
        if not entry.reason or not entry.reason.strip():
            raise ValueError(
                f"A reason is required for {entry.action} on {entry.key_value}"
            )

        if entry.action == Action.ACCEPT:
            _validate_acceptance(entry.check_type, entry.column, entry.current_value)
            _check_acceptance_against_data(
                data, key_col, entry.key_value, entry.column, entry.current_value
            )
            return data

        if entry.severity is not None:
            raise ValueError(
                f"Only acceptances record a severity, not {entry.action} "
                f"on {entry.key_value}"
            )

        if entry.action not in CORRECTION_ACTIONS:
            raise ValueError(f"Unknown correction action '{entry.action}'")

        is_valid, error_msg = self.validate_correction_input(
            data, key_col, entry.key_value, entry.action, entry.column, entry.new_value
        )
        if not is_valid:
            raise ValueError(error_msg)

        return self._apply_action(
            data, key_col, entry.key_value, entry.action, entry.column, entry.new_value
        )

    def _apply_action(
        self,
        data: pl.DataFrame,
        key_col: str,
        key_value: str,
        action: Action,
        column: str | None,
        new_value: Any | None,
    ) -> pl.DataFrame:
        """Apply one correction action to `data`; unknown actions leave it as is."""
        if action == Action.MODIFY_VALUE and column and new_value is not None:
            return self._apply_modify_value(data, key_col, key_value, column, new_value)
        if action == Action.REMOVE_VALUE and column:
            return self._apply_remove_value(data, key_col, key_value, column)
        if action == Action.REMOVE_ROW:
            return self._apply_remove_row(data, key_col, key_value)
        return data

    def _apply_modify_value(
        self,
        data: pl.DataFrame,
        key_col: str,
        key_value: str,
        column: str,
        new_value: Any,
    ) -> pl.DataFrame:
        """Apply modify value correction.

        Parameters
        ----------
        data : pl.DataFrame
            The data to modify
        key_col : str
            The key column name
        key_value : str
            The key value to match
        column : str
            The column to modify
        new_value : Any
            The new value

        Returns
        -------
        pl.DataFrame
            The modified data
        """
        if data[column].dtype == pl.String:
            return data.with_columns(
                pl.when(pl.col(key_col) == key_value)
                .then(pl.lit(str(new_value)))
                .otherwise(pl.col(column))
                .alias(column)
            )
        else:
            # Handle type conversion for non-string columns
            try:
                if isinstance(new_value, str):
                    typed_value = pl.lit(new_value).cast(data[column].dtype)
                else:
                    typed_value = pl.lit(new_value)

                return data.with_columns(
                    pl.when(pl.col(key_col) == key_value)
                    .then(typed_value)
                    .otherwise(pl.col(column))
                    .alias(column)
                )
            except Exception:
                # Fallback to string conversion if type casting fails
                return data.with_columns(
                    pl.when(pl.col(key_col) == key_value)
                    .then(pl.lit(str(new_value)))
                    .otherwise(pl.col(column))
                    .alias(column)
                )

    def _apply_remove_value(
        self,
        data: pl.DataFrame,
        key_col: str,
        key_value: str,
        column: str,
    ) -> pl.DataFrame:
        """Apply remove value correction.

        Parameters
        ----------
        data : pl.DataFrame
            The data to modify
        key_col : str
            The key column name
        key_value : str
            The key value to match
        column : str
            The column to modify

        Returns
        -------
        pl.DataFrame
            The modified data
        """
        return data.with_columns(
            pl.when(pl.col(key_col) == key_value)
            .then(None)
            .otherwise(pl.col(column))
            .alias(column)
        )

    def _apply_remove_row(
        self,
        data: pl.DataFrame,
        key_col: str,
        key_value: str,
    ) -> pl.DataFrame:
        """Apply remove row correction.

        Parameters
        ----------
        data : pl.DataFrame
            The data to modify
        key_col : str
            The key column name
        key_value : str
            The key value to match

        Returns
        -------
        pl.DataFrame
            The modified data
        """
        return data.filter(pl.col(key_col) != key_value)

    @st.cache_data(ttl=60, show_spinner=False, hash_funcs=_PROCESSOR_HASH_FUNCS)
    def get_data_summary(self, data: pl.DataFrame) -> dict[str, Any]:
        """Get summary statistics for the data.

        Parameters
        ----------
        data : pl.DataFrame
            The data to summarize

        Returns
        -------
        dict[str, Any]
            Summary statistics including row count, column count, and missing percentage
        """
        if data.is_empty():
            return {"rows": 0, "columns": 0, "missing_percentage": 0.0}

        rows, columns = data.shape

        # Calculate missing values percentage
        missing_count = data.select(pl.all().is_null().sum())
        total_missing = missing_count.select(
            pl.sum_horizontal(pl.all()).alias("total")
        )[0, "total"]

        missing_percentage = (
            round((total_missing / (rows * columns)) * 100, 2)
            if rows > 0 and columns > 0
            else 0.0
        )

        return {
            "rows": rows,
            "columns": columns,
            "missing_percentage": missing_percentage,
        }

    def validate_correction_input(
        self,
        data: pl.DataFrame,
        key_col: str,
        key_value: str,
        action: Action,
        column: str | None = None,
        new_value: Any | None = None,
    ) -> tuple[bool, str]:
        """Validate correction input parameters.

        Parameters
        ----------
        data : pl.DataFrame
            The data to validate against
        key_col : str
            The key column name
        key_value : str
            The key value
        action : Action
            The correction action
        column : str | None
            The column to modify
        new_value : Any | None
            The new value

        Returns
        -------
        tuple[bool, str]
            (is_valid, error_message)
        """
        if key_col not in data.columns:
            return False, f"Key column '{key_col}' not found in data"

        if key_value not in data[key_col].to_list():
            return False, f"Key value '{key_value}' not found in data"

        if action in (Action.MODIFY_VALUE, Action.REMOVE_VALUE):
            if not column:
                return False, "Column must be specified for modify/remove value actions"
            if column not in data.columns:
                return False, f"Column '{column}' not found in data"

        if action == Action.MODIFY_VALUE and new_value is None:
            return False, "New value must be provided for modify value action"

        return True, ""

    def remove_correction_entry(
        self,
        alias: str,
        correction_index: int,
    ) -> list[ReapplyFailure]:
        """Remove a correction entry from the log and reapply corrections.

        Parameters
        ----------
        alias : str
            The data alias/table name
        correction_index : int
            The index of the correction entry to remove

        Returns
        -------
        list[ReapplyFailure]
            Remaining corrections that failed to reapply after the removal.
        """
        correction_log = self.get_correction_log(alias)

        if correction_log.is_empty():
            raise ValueError("No corrections to remove")

        if correction_index < 0 or correction_index >= correction_log.height:
            raise ValueError(f"Invalid correction index: {correction_index}")

        # Remove the correction entry at the specified index
        if correction_index == 0 and correction_log.height == 1:
            # If removing the only entry, create an empty DataFrame with proper schema
            updated_log = empty_correction_log()
        else:
            # Build list of parts to concatenate
            parts = []
            if correction_index > 0:
                parts.append(correction_log[:correction_index])
            if correction_index < len(correction_log) - 1:
                parts.append(correction_log[correction_index + 1 :])

            # parts is never empty given the conditions above, but handle it
            updated_log = pl.concat(parts) if parts else empty_correction_log()

        # Save the updated log
        duckdb_save_table(
            project_id=self.project_id,
            table_data=updated_log,
            alias=f"corr_log_{alias}",
            db_name="logs",
        )
        # Clear correction log cache
        self.get_correction_log.clear()
        self.get_correction_summary.clear()

        # Reapply all remaining corrections
        return self._reapply_all_corrections(alias)

    def refresh_corrected_data(self, alias: str) -> list[ReapplyFailure]:
        """Rebuild corrected data from the current prep data.

        Used after an upstream refresh (e.g. re-importing raw data)
        invalidates the corrected table, so downstream pages stop serving
        cached results built on stale prep data.

        Parameters
        ----------
        alias : str
            The data alias/table name

        Returns
        -------
        list[ReapplyFailure]
            Corrections that failed to reapply against the refreshed data.
        """
        return self._reapply_all_corrections(alias)

    def refresh_existing_corrected_data(self, alias: str) -> list[ReapplyFailure]:
        """Rebuild corrected data from prep, if a corrected table already exists.

        Used after prep data changes (a re-import or a prep step being added
        or removed). Aliases that have never been corrected are left alone,
        so a corrected table is not created as a side effect.

        Parameters
        ----------
        alias : str
            The data alias/table name

        Returns
        -------
        list[ReapplyFailure]
            Corrections that failed to reapply against the new prep data.
            Empty when there is no corrected table.
        """
        if not duckdb_table_exists(self.project_id, alias=alias, db_name="corrected"):
            return []
        return self._reapply_all_corrections(alias)

    def _reapply_all_corrections(self, alias: str) -> list[ReapplyFailure]:
        """Reapply all corrections from the log to fresh data.

        Parameters
        ----------
        alias : str
            The data alias/table name

        Returns
        -------
        list[ReapplyFailure]
            Corrections that failed to reapply and were skipped, in log order.
        """
        fresh_data = duckdb_get_table(
            project_id=self.project_id,
            alias=alias,
            db_name="prep",
        )

        if fresh_data.width == 0:
            # Prep table doesn't exist yet, nothing to correct
            return []

        correction_log = self.get_correction_log(alias)

        corrected_data = fresh_data
        failures: list[ReapplyFailure] = []
        statuses: list[str] = []
        status_reasons: list[str | None] = []
        for row in correction_log.iter_rows(named=True):
            corrected_data, error = self._apply_correction_row(corrected_data, row)
            if error:
                statuses.append("Failed")
                status_reasons.append(error)
                failures.append(
                    ReapplyFailure(step=_describe_correction_row(row), reason=error)
                )
            else:
                statuses.append("Successful")
                status_reasons.append(None)

        refreshed_log = correction_log.with_columns(
            pl.Series("status", statuses, dtype=pl.String),
            pl.Series("status_reason", status_reasons, dtype=pl.String),
        )
        duckdb_save_table(
            project_id=self.project_id,
            table_data=refreshed_log,
            alias=f"corr_log_{alias}",
            db_name="logs",
        )
        self.get_correction_log.clear()
        self.get_correction_summary.clear()

        self.save_corrected_data(alias, corrected_data)
        return failures

    def _apply_correction_row(
        self, data: pl.DataFrame, row: dict[str, Any]
    ) -> tuple[pl.DataFrame, str | None]:
        """Apply one correction-log row to data.

        Returns `data` unchanged for "accept" rows, if the row's key can't be
        located, or if
        applying the correction fails (the underlying data may have changed
        since the correction was logged).

        Parameters
        ----------
        data : pl.DataFrame
            The data to apply the correction to
        row : dict[str, Any]
            A single row from the correction log

        Returns
        -------
        tuple[pl.DataFrame, str | None]
            The data (updated on success, unchanged on failure) and an error
            message describing why the correction was skipped, or None on
            success.
        """
        action = row["action"]
        if action == Action.ACCEPT:
            # Acceptances record a decision; they never change the data.
            return data, None

        key_value = row["KEY"]
        key_col = self._find_key_column(data, key_value)
        if not key_col:
            return data, f"Key '{key_value}' not found in current data"

        column = row["column"]
        recorded_value = row["current_value"]
        new_value = row["new_value"]

        if action in (Action.MODIFY_VALUE, Action.REMOVE_VALUE) and column:
            if column not in data.columns:
                return data, f"Column '{column}' no longer available in the data"

            mismatch = self._current_value_mismatch(
                data, key_col, key_value, column, recorded_value
            )
            if mismatch:
                return data, mismatch

        try:
            if action == Action.MODIFY_VALUE and column and new_value is not None:
                return (
                    self._apply_modify_value(
                        data, key_col, key_value, column, new_value
                    ),
                    None,
                )
            if action == Action.REMOVE_VALUE and column:
                return self._apply_remove_value(data, key_col, key_value, column), None
            if action == Action.REMOVE_ROW:
                return self._apply_remove_row(data, key_col, key_value), None
        except Exception as e:
            # Skip corrections that fail (data may have changed)
            return data, str(e)

        return data, None

    @staticmethod
    def _current_value_mismatch(
        data: pl.DataFrame,
        key_col: str,
        key_value: str,
        column: str,
        recorded_value: str | None,
    ) -> str | None:
        """Check whether `column`'s value at `key_value` still matches what
        was recorded when the correction was logged.

        Parameters
        ----------
        data : pl.DataFrame
            The data to check against
        key_col : str
            The key column name
        key_value : str
            The key value to match
        column : str
            The column the correction targets
        recorded_value : str | None
            The value recorded in the log at the time the correction was
            made, or None if no value was recorded

        Returns
        -------
        str | None
            A description of the mismatch, or None if the value still
            matches (or there is nothing recorded to compare against)
        """
        if recorded_value is None:
            return None

        actual_value = data.filter(pl.col(key_col) == key_value)[0, column]
        actual_str = None if actual_value is None else str(actual_value)

        if actual_str != recorded_value:
            return (
                f"Current value for '{column}' has changed since this correction "
                f"was recorded (expected '{recorded_value}', found '{actual_str}')"
            )
        return None

    @staticmethod
    def _find_key_column(data: pl.DataFrame, key_value: str) -> str | None:
        """Find the first column containing the given key value.

        Parameters
        ----------
        data : pl.DataFrame
            The data to search
        key_value : str
            The key value to look for

        Returns
        -------
        str | None
            The matching column name, or None if not found
        """
        for col in data.columns:
            try:
                if data[col].is_in([key_value]).any():
                    return col
            except Exception:
                continue
        return None

    @st.cache_data(ttl=30, show_spinner=False, hash_funcs=_PROCESSOR_HASH_FUNCS)
    def get_correction_summary(self, alias: str) -> list[dict[str, Any]]:
        """Get a summary of all correction entries for display.

        Parameters
        ----------
        alias : str
            The data alias/table name

        Returns
        -------
        list[dict[str, Any]]
            List of correction summaries with index, description, and details
        """
        correction_log = self.get_correction_log(alias)

        if correction_log.is_empty():
            return []

        summaries = []
        for index, row in enumerate(correction_log.iter_rows(named=True)):
            action = row["action"]
            key_value = row["KEY"]
            column = row["column"]
            new_value = row["new_value"]
            reason = row["reason"]
            date = row["date"]

            description = _describe_correction_row(row)

            summaries.append(
                {
                    "index": index,
                    "action_index": f"{index} - {action} - {description}",
                    "action": action,
                    "check_type": row["check_type"],
                    "severity": row["severity"],
                    "description": description,
                    "key_value": key_value,
                    "column": column,
                    "new_value": new_value,
                    "reason": reason,
                    "date": date,
                }
            )

        return summaries
