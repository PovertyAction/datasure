"""Correcting and accepting GPS outliers against the correction log.

A GPS outlier is corrected or accepted per KEY. Correcting the coordinates
writes one log entry per coordinate column (latitude and longitude) with a
shared reason, applied together or not at all by
`CorrectionProcessor.apply_corrections`. An acceptance is a single
(gps, KEY, no column) log entry that records both coordinates, and lapses
when either of them changes (see `CorrectionProcessor.get_active_acceptances`).

Accepted outliers are hidden from the outliers table unless the user asks to
see them, are left out of the outlier count, and are drawn in their own
color on the map.

Corrections need the configured latitude and longitude columns, so a GPS
configuration that stores both in one delimited column can only remove the
observation.

Kept free of Streamlit so the logic can be tested without a running app.
"""

import json
import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import pandas as pd
import polars as pl

from datasure.checks.outliers.review import (
    REVIEW_COLUMNS,
    REVIEW_REASON_COL,
    REVIEW_STATUS_COL,
    REVIEWED_BADGE,
)
from datasure.models.enums import GPSFormatType
from datasure.processing.correction_log import Action
from datasure.processing.corrections import CorrectionEntry

# Check type of GPS acceptances, and the source of every GPS log entry.
GPS_CHECK_TYPE = "gps"

# Outlier flag column added by the detection functions in `compute`.
OUTLIER_COL = "Outlier"

# Map labels of a point's outlier status.
OUTLIER_STATUS = "Outlier"
NORMAL_STATUS = "Normal"
ACCEPTED_STATUS = "Accepted"


class GPSAction(StrEnum):
    """The actions offered for a GPS outlier."""

    MODIFY_COORDINATES = "modify coordinates"
    REMOVE_COORDINATES = "remove coordinates"
    REMOVE_OBSERVATION = "remove observation"
    ACCEPT = "accept"


@dataclass(frozen=True)
class CoordinateColumns:
    """The configured latitude and longitude columns of a GPS configuration."""

    latitude: str
    longitude: str

    def as_tuple(self) -> tuple[str, str]:
        """Return (latitude, longitude)."""
        return (self.latitude, self.longitude)


@dataclass(frozen=True)
class GPSSelection:
    """The outlier behind a clicked table row, used to prefill the form."""

    key_value: Any
    reviewed: bool


def coordinate_columns(gps_config: dict[str, Any]) -> CoordinateColumns | None:
    """Return the latitude and longitude columns of a GPS configuration.

    None for a configuration that stores the coordinates in one delimited
    column, which corrections can't write to.
    """
    if gps_config.get("format_type") != GPSFormatType.SEPARATE_COLUMNS.value:
        return None
    latitude = gps_config.get("latitude_column")
    longitude = gps_config.get("longitude_column")
    if not latitude or not longitude:
        return None
    return CoordinateColumns(latitude=latitude, longitude=longitude)


def allowed_gps_actions(
    columns: CoordinateColumns | None, *, reviewed: bool
) -> list[GPSAction]:
    """Return the actions the form offers for an outlier.

    An outlier can be accepted only while it is not yet accepted. Without
    coordinate columns, only the observation can be removed.
    """
    if columns is None:
        return [GPSAction.REMOVE_OBSERVATION]
    actions = [
        GPSAction.MODIFY_COORDINATES,
        GPSAction.REMOVE_COORDINATES,
        GPSAction.REMOVE_OBSERVATION,
    ]
    if not reviewed:
        actions.append(GPSAction.ACCEPT)
    return actions


def _parse_coordinate(value: str, name: str, bound: int) -> str | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return f"{name} must be a number"
    if math.isnan(number):
        return f"{name} must be a number"
    if not -bound <= number <= bound:
        return f"{name} must be between -{bound} and {bound}"
    return None


def validate_coordinates(latitude: str, longitude: str) -> str | None:
    """Return why a new coordinate pair is invalid, or None if it is valid."""
    return _parse_coordinate(latitude, "Latitude", 90) or _parse_coordinate(
        longitude, "Longitude", 180
    )


def build_gps_entries(
    action: GPSAction,
    key_value: Any,
    reason: str,
    *,
    columns: CoordinateColumns | None,
    current: dict[str, Any],
    new_latitude: str | None = None,
    new_longitude: str | None = None,
    survey_id_value: Any = None,
) -> list[CorrectionEntry]:
    """Return the log entries that carry out `action` on one KEY.

    Parameters
    ----------
    action : GPSAction
        The action chosen in the form.
    key_value : Any
        The KEY of the outlier.
    reason : str
        The reason, shared by every entry.
    columns : CoordinateColumns | None
        The configured coordinate columns. Required unless `action` is
        "remove observation".
    current : dict[str, Any]
        The current value of each coordinate column for the KEY.
    new_latitude, new_longitude : str | None
        The new coordinates, for "modify coordinates".
    survey_id_value : Any
        The Survey ID value for the KEY, recorded with each entry.

    Returns
    -------
    list[CorrectionEntry]
        The entries, to apply together with `apply_corrections`.

    Raises
    ------
    ValueError
        If `action` needs coordinate columns and `columns` is None.
    """
    if action == GPSAction.REMOVE_OBSERVATION:
        return [
            CorrectionEntry(
                key_value=key_value,
                action=Action.REMOVE_ROW,
                reason=reason,
                survey_id_value=survey_id_value,
            )
        ]

    if columns is None:
        raise ValueError(
            f"'{action}' needs the GPS configuration's latitude and longitude columns"
        )

    if action == GPSAction.ACCEPT:
        return [
            CorrectionEntry(
                key_value=key_value,
                action=Action.ACCEPT,
                reason=reason,
                current_value={col: current.get(col) for col in columns.as_tuple()},
                survey_id_value=survey_id_value,
                check_type=GPS_CHECK_TYPE,
            )
        ]

    if action == GPSAction.MODIFY_COORDINATES:
        new_values = {columns.latitude: new_latitude, columns.longitude: new_longitude}
        return [
            CorrectionEntry(
                key_value=key_value,
                action=Action.MODIFY_VALUE,
                reason=reason,
                column=col,
                current_value=current.get(col),
                new_value=new_values[col],
                survey_id_value=survey_id_value,
            )
            for col in columns.as_tuple()
        ]

    if action == GPSAction.REMOVE_COORDINATES:
        return [
            CorrectionEntry(
                key_value=key_value,
                action=Action.REMOVE_VALUE,
                reason=reason,
                column=col,
                current_value=current.get(col),
                survey_id_value=survey_id_value,
            )
            for col in columns.as_tuple()
        ]

    # Never fall back to a destructive action for an unrecognized value.
    raise ValueError(f"Unsupported GPS action: {action!r}")


def accepted_gps_keys(
    acceptances: pl.DataFrame, columns: CoordinateColumns
) -> dict[str, str]:
    """Map each KEY with an acceptance for `columns` to its latest reason.

    Parameters
    ----------
    acceptances : pl.DataFrame
        The active GPS acceptances, as returned by
        `CorrectionProcessor.get_active_acceptances`.
    columns : CoordinateColumns
        The coordinate columns of the GPS configuration shown. Acceptances
        recorded for another configuration's columns are ignored.

    Returns
    -------
    dict[str, str]
        KEY (as text, as the log stores it) to acceptance reason.
    """
    if acceptances.is_empty() or "current_value" not in acceptances.columns:
        return {}

    wanted = set(columns.as_tuple())
    accepted: dict[str, str] = {}
    for row in acceptances.iter_rows(named=True):
        if row.get("column") is not None or not row["current_value"]:
            continue
        if set(json.loads(row["current_value"])) == wanted:
            # Later rows overwrite earlier ones: the log is in entry order.
            accepted[str(row["KEY"])] = row["reason"]
    return accepted


def _native(value: Any) -> Any:
    """Return a KEY from the detection output as polars and the log hold it.

    Numpy scalars become Python values. An integer KEY column with nulls
    comes back from `to_pandas` as floats, so an integral float becomes an
    int again: the log stores KEY 1 as "1", not "1.0".
    """
    value = value.item() if hasattr(value, "item") else value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


def _is_outlier(outliers: pd.DataFrame, outlier_col: str = OUTLIER_COL) -> pd.Series:
    return outliers[outlier_col].fillna(False).astype(bool)


def _is_reviewed(outliers: pd.DataFrame) -> pd.Series:
    if REVIEW_STATUS_COL not in outliers.columns:
        return pd.Series(False, index=outliers.index)
    return outliers[REVIEW_STATUS_COL] == REVIEWED_BADGE


def mark_gps_reviewed(
    outliers: pd.DataFrame, accepted: dict[str, str], survey_key: str
) -> pd.DataFrame:
    """Add review status and reason columns to detection output.

    Parameters
    ----------
    outliers : pd.DataFrame
        Output of `detect_outliers_with_lof` or `detect_outliers_with_clusters`.
    accepted : dict[str, str]
        KEY to acceptance reason, from `accepted_gps_keys`.
    survey_key : str
        The Survey KEY column in `outliers`.

    Returns
    -------
    pd.DataFrame
        A copy of `outliers` with `REVIEW_STATUS_COL` and `REVIEW_REASON_COL`:
        `REVIEWED_BADGE` and the reason for an accepted outlier, otherwise
        None. Only outliers can be reviewed.

    Raises
    ------
    ValueError
        If `survey_key` is one of `REVIEW_COLUMNS`, which would overwrite it.
    """
    if survey_key in REVIEW_COLUMNS:
        raise ValueError(
            f"The Survey KEY column '{survey_key}' has the name of a review column"
        )
    reasons = outliers[survey_key].map(lambda key: accepted.get(str(_native(key))))
    reviewed = _is_outlier(outliers) & reasons.notna()

    marked = outliers.copy()
    marked[REVIEW_STATUS_COL] = pd.Series(
        [REVIEWED_BADGE if r else None for r in reviewed],
        index=outliers.index,
        dtype=object,
    )
    marked[REVIEW_REASON_COL] = pd.Series(
        [reason if r else None for r, reason in zip(reviewed, reasons, strict=True)],
        index=outliers.index,
        dtype=object,
    )
    return marked


def count_unreviewed_outliers(outliers: pd.DataFrame) -> int:
    """Return the number of outliers not accepted as valid."""
    return int((_is_outlier(outliers) & ~_is_reviewed(outliers)).sum())


def outlier_status(outliers: pd.DataFrame, outlier_col: str = OUTLIER_COL) -> pd.Series:
    """Label each point Accepted, Outlier or Normal, for the map."""
    reviewed = _is_reviewed(outliers)
    is_outlier = _is_outlier(outliers, outlier_col)
    return pd.Series(
        [
            ACCEPTED_STATUS if r else OUTLIER_STATUS if o else NORMAL_STATUS
            for r, o in zip(reviewed, is_outlier, strict=True)
        ],
        index=outliers.index,
        dtype=object,
    )


def outliers_table(outliers: pd.DataFrame, *, show_reviewed: bool) -> pd.DataFrame:
    """Return the outliers to show in the table, indexed by row position.

    Accepted outliers and the review columns are hidden unless
    `show_reviewed`. The index is reset so a clicked row position maps to a
    row of the result.
    """
    table = outliers[_is_outlier(outliers)]
    if REVIEW_STATUS_COL in table.columns and not show_reviewed:
        table = table[~_is_reviewed(table)].drop(columns=list(REVIEW_COLUMNS))
    return table.reset_index(drop=True)


def select_gps_outlier(
    table: pd.DataFrame, rows: Sequence[int], survey_key: str
) -> GPSSelection | None:
    """Return the outlier behind a clicked row of `outliers_table`.

    None if no row is clicked or the position no longer exists in `table`.
    """
    if not rows or not 0 <= rows[0] < len(table):
        return None
    row = table.iloc[rows[0]]
    return GPSSelection(
        key_value=_native(row[survey_key]),
        reviewed=row.get(REVIEW_STATUS_COL) == REVIEWED_BADGE,
    )
