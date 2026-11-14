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
from dataclasses import dataclass, field
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


# Auto-Clustering (LOF) settings: the sliders' ranges and defaults. The check
# and Summary's check health row both read the saved values through
# `lof_neighbors` and `lof_contamination`, so they detect the same outliers.
LOF_MIN_POINTS = 6
LOF_MIN_NEIGHBORS = 5
LOF_MAX_NEIGHBORS = 50
LOF_DEFAULT_NEIGHBORS = 20
LOF_MIN_CONTAMINATION = 0.01
LOF_MAX_CONTAMINATION = 0.5
LOF_DEFAULT_CONTAMINATION = 0.1


def lof_max_neighbors(n_samples: int) -> int:
    """Return the most neighbors LOF can use for `n_samples` points."""
    return min(LOF_MAX_NEIGHBORS, n_samples - 1)


def lof_neighbors(saved: Any, n_samples: int) -> int:
    """Return the saved number of neighbors, or the default if it doesn't fit.

    A saved value outside the slider's range for `n_samples` points, such as
    one saved when the data had more points, falls back to the default.
    """
    maximum = lof_max_neighbors(n_samples)
    if (
        isinstance(saved, int)
        and not isinstance(saved, bool)
        and LOF_MIN_NEIGHBORS <= saved <= maximum
    ):
        return saved
    return min(LOF_DEFAULT_NEIGHBORS, maximum)


def lof_contamination(saved: Any) -> float:
    """Return the saved expected outlier proportion, or the default."""
    if (
        isinstance(saved, int | float)
        and not isinstance(saved, bool)
        and LOF_MIN_CONTAMINATION <= saved <= LOF_MAX_CONTAMINATION
    ):
        return float(saved)
    return LOF_DEFAULT_CONTAMINATION


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
    column, which corrections can't write to, or that uses one column for
    both, where the longitude would overwrite the latitude.
    """
    if gps_config.get("format_type") != GPSFormatType.SEPARATE_COLUMNS.value:
        return None
    latitude = gps_config.get("latitude_column")
    longitude = gps_config.get("longitude_column")
    if not latitude or not longitude or latitude == longitude:
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


def _is_reviewed(outliers: pd.DataFrame, *, marked: bool) -> pd.Series:
    # Without `marked`, a REVIEW_STATUS_COL is a source column, such as a
    # Survey KEY with that name, not the output of `mark_gps_reviewed`.
    if not marked or REVIEW_STATUS_COL not in outliers.columns:
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


def count_unreviewed_outliers(outliers: pd.DataFrame, *, marked: bool) -> int:
    """Return the number of outliers not accepted as valid.

    `marked` says whether `outliers` comes from `mark_gps_reviewed`;
    otherwise no outlier counts as accepted.
    """
    return int((_is_outlier(outliers) & ~_is_reviewed(outliers, marked=marked)).sum())


@dataclass(frozen=True)
class GPSReviewLog:
    """The correction log entries that review the outliers of one configuration.

    Attributes
    ----------
    acceptances : pl.DataFrame
        The active GPS acceptances, from
        `CorrectionProcessor.get_active_acceptances`.
    corrections : pl.DataFrame
        The GPS corrections still in effect (see `gps_corrections`).
    columns : CoordinateColumns | None
        The configuration's coordinate columns; None if it stores both in one
        column, so no acceptance applies to it.
    history : pl.DataFrame
        Every GPS acceptance and correction in the log, including those no
        longer in effect (see `gps_review_history`), to date when each point
        was first resolved.
    """

    acceptances: pl.DataFrame
    corrections: pl.DataFrame
    columns: CoordinateColumns | None
    history: pl.DataFrame = field(default_factory=pl.DataFrame)


@dataclass(frozen=True)
class GPSOutlierSummary:
    """The GPS outliers of one configuration with their review status.

    Attributes
    ----------
    outliers : pd.DataFrame
        The detection output, marked by `mark_gps_reviewed` when `marked`.
    marked : bool
        Whether the outliers could be reviewed (see `summarize_gps_outliers`).
    outstanding : int
        Outliers not accepted as valid: the check's "Outliers Detected".
    resolved : int | None
        Points accepted or corrected from the check and not flagged as
        outstanding now; None when the outliers could not be reviewed.
    resolutions : pl.DataFrame
        KEY (as text) and the date of its first GPS acceptance or
        correction, one row per resolved point. An entry no longer in effect
        still counts, so a point resolved again later keeps its first date.
    """

    outliers: pd.DataFrame
    marked: bool
    outstanding: int
    resolved: int | None
    resolutions: pl.DataFrame

    def unreviewed(self) -> pd.DataFrame:
        """Return the outstanding outliers, with every column of the data."""
        flagged = _is_outlier(self.outliers) & ~_is_reviewed(
            self.outliers, marked=self.marked
        )
        return self.outliers[flagged]


_RESOLUTIONS_SCHEMA = {"KEY": pl.String, "date": pl.Datetime("us")}


def gps_corrections(
    log: pl.DataFrame,
    active_corrections: pl.DataFrame,
    columns: CoordinateColumns | None,
) -> pl.DataFrame:
    """Return the GPS check's corrections still in effect for a configuration.

    Parameters
    ----------
    log : pl.DataFrame
        The whole correction log, for removed observations: a successful
        "remove row" from the GPS check stays in effect until it is undone.
    active_corrections : pl.DataFrame
        From `CorrectionProcessor.get_active_corrections`: value corrections
        the data still holds. Only the GPS check's corrections of `columns`
        are kept.
    columns : CoordinateColumns | None
        The configuration's coordinate columns; None keeps removed rows only.

    Returns
    -------
    pl.DataFrame
        Rows of the log, removed observations first.
    """
    frames = []
    if {"action", "source", "status"} <= set(log.columns):
        frames.append(
            log.filter(
                (pl.col("action") == Action.REMOVE_ROW.value)
                & (pl.col("source") == GPS_CHECK_TYPE)
                & (pl.col("status") == "Successful")
            )
        )
    if columns is not None and {"source", "column"} <= set(active_corrections.columns):
        frames.append(
            active_corrections.filter(
                (pl.col("source") == GPS_CHECK_TYPE)
                & pl.col("column").is_in(list(columns.as_tuple()))
            )
        )
    if not frames:
        return log.clear()
    return pl.concat(frames, how="diagonal_relaxed")


def gps_review_history(log: pl.DataFrame) -> pl.DataFrame:
    """Return every GPS acceptance and successful GPS correction in the log.

    Unlike `GPSReviewLog.acceptances` and `.corrections`, entries no longer in
    effect are kept: they still show when a point was first resolved.
    """
    if not {"action", "check_type", "source", "status"} <= set(log.columns):
        return log.clear()
    return log.filter(
        ((pl.col("action") == Action.ACCEPT) & (pl.col("check_type") == GPS_CHECK_TYPE))
        | (
            pl.col("action").is_in(
                [Action.MODIFY_VALUE, Action.REMOVE_VALUE, Action.REMOVE_ROW]
            )
            & (pl.col("source") == GPS_CHECK_TYPE)
            & (pl.col("status") == "Successful")
        )
    )


def summarize_gps_outliers(
    outliers: pd.DataFrame, survey_key: str, *, review: GPSReviewLog | None
) -> GPSOutlierSummary:
    """Mark accepted outliers and count what is outstanding and resolved.

    The GPS check's "Outliers Detected" metric and Summary's check health
    row both come from this function, so their numbers match.

    Parameters
    ----------
    outliers : pd.DataFrame
        Output of `detect_outliers_with_lof` or `detect_outliers_with_clusters`.
    survey_key : str
        The Survey KEY column in `outliers`.
    review : GPSReviewLog | None
        The log entries reviewing these outliers, or None when they can't be
        reviewed (no dataset alias, or a KEY column with a review column's
        name); then every outlier is outstanding and nothing is resolved.

    Returns
    -------
    GPSOutlierSummary
        A point is resolved when it is an accepted outlier, or when a GPS
        correction of it is still in effect and it is not an outstanding
        outlier now. Each point counts once.
    """
    if review is None:
        return GPSOutlierSummary(
            outliers,
            marked=False,
            outstanding=count_unreviewed_outliers(outliers, marked=False),
            resolved=None,
            resolutions=pl.DataFrame(schema=_RESOLUTIONS_SCHEMA),
        )
    accepted = (
        {}
        if review.columns is None
        else accepted_gps_keys(review.acceptances, review.columns)
    )
    marked = mark_gps_reviewed(outliers, accepted, survey_key)
    is_outlier = _is_outlier(marked)
    is_accepted = _is_reviewed(marked, marked=True)

    def keys(rows: pd.Series) -> set[str]:
        return {str(_native(key)) for key in marked.loc[rows, survey_key]}

    outstanding = keys(is_outlier & ~is_accepted)
    corrected = (
        set(review.corrections["KEY"].cast(pl.String).to_list())
        if "KEY" in review.corrections.columns
        else set()
    )
    resolved = keys(is_accepted) | (corrected - outstanding)
    entries = [
        frame.select(pl.col("KEY").cast(pl.String), pl.col("date"))
        for frame in (review.acceptances, review.corrections, review.history)
        if {"KEY", "date"} <= set(frame.columns) and not frame.is_empty()
    ]
    resolutions = (
        pl.concat(entries, how="vertical_relaxed")
        .filter(pl.col("KEY").is_in(sorted(resolved)))
        .group_by("KEY")
        .agg(pl.col("date").min())
        .sort("KEY")
        if entries
        else pl.DataFrame(schema=_RESOLUTIONS_SCHEMA)
    )
    return GPSOutlierSummary(
        marked,
        marked=True,
        outstanding=count_unreviewed_outliers(marked, marked=True),
        resolved=len(resolved),
        resolutions=resolutions,
    )


def outlier_status(
    outliers: pd.DataFrame, outlier_col: str = OUTLIER_COL, *, marked: bool
) -> pd.Series:
    """Label each point Accepted, Outlier or Normal, for the map.

    `marked` says whether `outliers` comes from `mark_gps_reviewed`;
    otherwise no point is Accepted.
    """
    reviewed = _is_reviewed(outliers, marked=marked)
    is_outlier = _is_outlier(outliers, outlier_col)
    return pd.Series(
        [
            ACCEPTED_STATUS if r else OUTLIER_STATUS if o else NORMAL_STATUS
            for r, o in zip(reviewed, is_outlier, strict=True)
        ],
        index=outliers.index,
        dtype=object,
    )


def outliers_table(
    outliers: pd.DataFrame, *, marked: bool, show_reviewed: bool
) -> pd.DataFrame:
    """Return the outliers to show in the table, indexed by row position.

    If `outliers` comes from `mark_gps_reviewed` (`marked`), accepted
    outliers and the review columns are hidden unless `show_reviewed`. The
    index is reset so a clicked row position maps to a row of the result.
    """
    table = outliers[_is_outlier(outliers)]
    if marked and not show_reviewed:
        table = table[~_is_reviewed(table, marked=True)].drop(
            columns=list(REVIEW_COLUMNS)
        )
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
