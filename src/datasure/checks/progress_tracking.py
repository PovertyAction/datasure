"""The Progress check's targets from a tracking dataset.

A page's tracking dataset gives the target in one of two ways. A tracking
file has one row per unit (a village, say) with that unit's target. A master
list has one row per expected respondent; a unit's target is its count of
rows. Which one is worked out from the settings and never stored:

| Tracking dataset | Target column chosen | Mode          |
| ---------------- | -------------------- | ------------- |
| none             | -                    | fixed         |
| set              | yes                  | tracking file |
| set              | no                   | master list   |

Everything here is pure: `compute_progress` calls it and the page draws the
result. Problems with the tracking dataset come back as `TrackingIssue`s and
are shown on the page; nothing is dropped silently.
"""

from datetime import date
from typing import Literal

import polars as pl
from pydantic import BaseModel, Field

ProgressMode = Literal["fixed", "tracking file", "master list"]


class TrackingSettings(BaseModel):
    """The progress settings that only apply with a tracking dataset."""

    tracking_target: str | None = Field(
        None, description="Target column in the tracking file; none for a master list"
    )
    tracking_unit: str | None = Field(
        None, description="Unit column in the tracking dataset"
    )
    survey_unit: str | None = Field(
        None, description="Unit column in the survey (tracking file only)"
    )
    tracking_id: str | None = Field(
        None, description="ID column in the master list, matched to the survey ID"
    )
    tracking_parents: list[str] = Field(
        default_factory=list,
        description="Parent columns in the tracking dataset, finest to coarsest",
    )
    strip_leading_zeros: bool = Field(
        False, description="Whether IDs and units match without leading zeros"
    )
    tracking_display: list[str] = Field(
        default_factory=list,
        description="Master-list columns shown with each respondent list",
    )


def detect_mode(has_tracking: bool, settings: TrackingSettings) -> ProgressMode:
    """Work out where the target comes from (see the module docstring)."""
    if not has_tracking:
        return "fixed"
    return "tracking file" if settings.tracking_target else "master list"


def normalize_keys(keys: pl.Series, strip_leading_zeros: bool) -> pl.Series:
    """Return IDs or units as the text they are matched on.

    Keys are cast to text and trimmed of spaces; blank text is missing. With
    `strip_leading_zeros`, "0123" becomes "123" (and "000" becomes "0").
    There is no case folding. Whole-number floats, as a spreadsheet import
    can make of an integer ID, are matched as integers: 12.0 as "12".
    """
    if keys.dtype.is_float():
        whole = keys.drop_nulls()
        if whole.is_finite().all() and (whole == whole.floor()).all():
            keys = keys.cast(pl.Int64)
    text = keys.cast(pl.String).str.strip_chars()
    if strip_leading_zeros:
        stripped = text.str.strip_chars_start("0")
        text = pl.select(
            pl.when((stripped == "") & (text != ""))
            .then(pl.lit("0"))
            .otherwise(stripped)
        ).to_series()
    return pl.select(pl.when(text != "").then(text)).to_series().alias(keys.name)


UNTRACKED = "Untracked"
BLANK = "(blank)"
ALL_UNITS = "All"
BEHIND_BELOW = 50.0
UnitStatus = Literal["behind", "on track", "over target", "untracked"]


class TrackingIssue(BaseModel):
    """A problem with the tracking dataset, shown on the page."""

    level: Literal["error", "warning"] = Field(
        description="An error stops the dataset being used; a warning does not"
    )
    message: str = Field(description="What is wrong and what was done about it")
    values: list[str] = Field(
        default_factory=list, description="The units or IDs it concerns"
    )


class UnitRow(BaseModel):
    """One unit, or the Untracked group, in the By unit table."""

    unit: str = Field(description="The unit, or 'Untracked'")
    target: int | None = Field(None, ge=0, description="None for Untracked")
    submissions: int = Field(ge=0, description="Rows in the unit")
    unique: int = Field(ge=0, description="Distinct IDs in the unit")
    completed: int = Field(ge=0, description="Distinct IDs completed in the unit")
    percentage: float | None = Field(None, ge=0, description="Completed of target")
    remaining: int | None = Field(None, ge=0, description="Completions still needed")
    status: UnitStatus = Field(
        description="Behind below 50%, over target above 100%, else on track"
    )


class UnitLevel(BaseModel):
    """The By unit table at one level: the units, or one parent column."""

    column: str = Field(description="The level's column in the tracking dataset")
    rows: list[UnitRow] = Field(
        description="Tracked units by name, then the Untracked group if any"
    )


class TrackingReference:
    """The tracking dataset, checked and keyed for matching.

    Attributes
    ----------
    issues : list[TrackingIssue]
        Errors and warnings found while reading it.
    units : pl.DataFrame | None
        One row per unit: ``unit``, ``target`` and ``p0``, ``p1``... for the
        parent columns. None when an error stops the dataset being used.
    ids : pl.DataFrame | None
        A master list's respondents: ``id``, ``unit`` and ``d0``, ``d1``...
        for the display columns, as text. None for a tracking file.
    levels : list[tuple[str, str]]
        Each level's key in ``units`` and its column name, unit first.
    """

    def __init__(
        self,
        issues: list[TrackingIssue],
        units: pl.DataFrame | None = None,
        ids: pl.DataFrame | None = None,
        levels: list[tuple[str, str]] | None = None,
    ) -> None:
        self.issues = issues
        self.units = units
        self.ids = ids
        self.levels = levels or []

    @property
    def usable(self) -> bool:
        """Whether the dataset can be used: read without an error."""
        return self.units is not None

    @property
    def target(self) -> int | None:
        """The total target, the sum of the units'; None when not usable."""
        if self.units is None:
            return None
        return int(self.units["target"].sum())


def _error(message: str, values: list[str] | None = None) -> TrackingIssue:
    return TrackingIssue(level="error", message=message, values=values or [])


def _setup_errors(
    required: dict[str, str | None],
    tracking_columns: list[str],
    survey_columns: dict[str, str | None],
    data_columns: list[str],
) -> list[TrackingIssue]:
    """Report settings not chosen and chosen columns the data no longer has."""
    errors = [
        _error(f"Choose the {label} in the progress settings.")
        for label, column in {**required, **survey_columns}.items()
        if not column
    ]
    gone = [c for c in required.values() if c and c not in tracking_columns]
    if gone:
        errors.append(_error("The tracking dataset has no column named:", gone))
    gone = [c for c in survey_columns.values() if c and c not in data_columns]
    if gone:
        errors.append(_error("The survey data has no column named:", gone))
    return errors


def _drop_missing_keys(
    frame: pl.DataFrame, key: str, what: str
) -> tuple[pl.DataFrame, list[TrackingIssue]]:
    """Drop rows without a key, with a warning giving how many."""
    missing = frame[key].null_count()
    if not missing:
        return frame, []
    rows, were = ("row has", "was") if missing == 1 else ("rows have", "were")
    warning = TrackingIssue(
        level="warning",
        message=f"{missing:,} tracking dataset {rows} no {what} and {were} left out.",
    )
    return frame.drop_nulls(key), [warning]


def _repeated(frame: pl.DataFrame, key: str, what: str) -> list[TrackingIssue]:
    """A blocking error listing keys that appear more than once."""
    repeated = frame.filter(pl.col(key).is_duplicated())[key].unique().sort()
    if repeated.is_empty():
        return []
    return [
        _error(
            f"Each {what} must appear once in the tracking dataset. These "
            "appear more than once:",
            repeated.to_list(),
        )
    ]


def _targets(
    values: pl.Series, units: pl.Series
) -> tuple[pl.Series, list[TrackingIssue]]:
    """Read the targets: missing, non-numeric or negative ones count as 0.

    Infinite targets count as non-numeric. Fractional targets are rounded
    down, with a warning of their own.
    """
    numbers = values.cast(pl.String).str.strip_chars().cast(pl.Float64, strict=False)
    bad = (~numbers.is_finite() | (numbers < 0)).fill_null(True)
    whole = numbers.floor()
    fractional = (~bad & (numbers != whole)).fill_null(False)
    targets = pl.select(
        pl.when(bad).then(0).otherwise(whole.cast(pl.Int64, strict=False))
    ).to_series()
    warnings = []
    if bad.any():
        warnings.append(
            TrackingIssue(
                level="warning",
                message="These units have a missing, non-numeric or negative "
                "target, so their target counts as 0:",
                values=units.filter(bad).sort().to_list(),
            )
        )
    if fractional.any():
        warnings.append(
            TrackingIssue(
                level="warning",
                message="These units have a fractional target, rounded down:",
                values=units.filter(fractional).sort().to_list(),
            )
        )
    return targets.alias("target"), warnings


def _parent_columns(tracking: pl.DataFrame, parents: list[str]) -> list[pl.Series]:
    return [
        tracking[column].cast(pl.String).fill_null(BLANK).alias(f"p{i}")
        for i, column in enumerate(parents)
    ]


def _levels(unit: str | None, parents: list[str]) -> list[tuple[str, str]]:
    return [("unit", unit or "Unit")] + [(f"p{i}", c) for i, c in enumerate(parents)]


def read_tracking(
    tracking: pl.DataFrame,
    settings: TrackingSettings,
    survey_id: str | None,
    data_columns: list[str],
) -> TrackingReference:
    """Check the tracking dataset and key it by unit and, for a master list, ID.

    Parameters
    ----------
    tracking : pl.DataFrame
        The tracking file or master list.
    settings : TrackingSettings
        The tracking settings; the mode follows from them.
    survey_id : str | None
        The survey's ID column, matched to a master list's ID column.
    data_columns : list[str]
        The survey data's columns, to check the survey's chosen columns.

    Returns
    -------
    TrackingReference
        Not usable when the settings are incomplete, a column is gone or a
        unit or ID is repeated.
    """
    if settings.tracking_target:
        return _read_tracking_file(tracking, settings, data_columns)
    return _read_master_list(tracking, settings, survey_id, data_columns)


def _read_tracking_file(
    tracking: pl.DataFrame, settings: TrackingSettings, data_columns: list[str]
) -> TrackingReference:
    errors = _setup_errors(
        {
            "unit column in the tracking file": settings.tracking_unit,
            "target column": settings.tracking_target,
        }
        | {f"parent column {c}": c for c in settings.tracking_parents},
        tracking.columns,
        {"unit column in the survey": settings.survey_unit},
        data_columns,
    )
    if errors:
        return TrackingReference(errors)
    strip = settings.strip_leading_zeros
    frame = pl.DataFrame(
        [
            normalize_keys(tracking[settings.tracking_unit], strip).alias("unit"),
            tracking[settings.tracking_target].alias("target"),
            *_parent_columns(tracking, settings.tracking_parents),
        ]
    )
    frame, issues = _drop_missing_keys(frame, "unit", "unit")
    repeated = _repeated(frame, "unit", "unit")
    if repeated:
        return TrackingReference(issues + repeated)
    targets, warnings = _targets(frame["target"], frame["unit"])
    return TrackingReference(
        issues + warnings,
        units=frame.with_columns(targets).sort("unit"),
        levels=_levels(settings.tracking_unit, settings.tracking_parents),
    )


def _read_master_list(
    tracking: pl.DataFrame,
    settings: TrackingSettings,
    survey_id: str | None,
    data_columns: list[str],
) -> TrackingReference:
    optional = [settings.tracking_unit, *settings.tracking_parents]
    errors = _setup_errors(
        {"ID column in the master list": settings.tracking_id}
        | {f"column {c}": c for c in optional + settings.tracking_display if c},
        tracking.columns,
        {"survey ID column": survey_id},
        data_columns,
    )
    if errors:
        return TrackingReference(errors)
    strip = settings.strip_leading_zeros
    # A respondent with no unit is still expected: counted in a "(blank)"
    # unit, with a warning
    unit = (
        normalize_keys(tracking[settings.tracking_unit], strip)
        if settings.tracking_unit
        else pl.Series(values=[ALL_UNITS] * tracking.height, dtype=pl.String)
    )
    frame = pl.DataFrame(
        [
            normalize_keys(tracking[settings.tracking_id], strip).alias("id"),
            unit.alias("unit"),
            *_parent_columns(tracking, settings.tracking_parents),
            *(
                tracking[c].cast(pl.String).alias(f"d{i}")
                for i, c in enumerate(settings.tracking_display)
            ),
        ]
    )
    frame, issues = _drop_missing_keys(frame, "id", "ID")
    repeated = _repeated(frame, "id", "ID")
    if repeated:
        return TrackingReference(issues + repeated)
    no_unit = frame["unit"].null_count()
    if no_unit:
        issues.append(
            TrackingIssue(
                level="warning",
                message=f"{no_unit:,} master list "
                f"{'row has' if no_unit == 1 else 'rows have'} no unit; they "
                f"are counted in a {BLANK} unit.",
            )
        )
        frame = frame.with_columns(pl.col("unit").fill_null(BLANK))
    parents = [f"p{i}" for i in range(len(settings.tracking_parents))]
    units = (
        frame.group_by("unit", maintain_order=True)
        .agg(
            pl.len().cast(pl.Int64).alias("target"),
            *(pl.first(p) for p in parents),
            pl.any_horizontal(
                *(pl.col(p).n_unique() > 1 for p in parents), pl.lit(False)
            ).alias("conflict"),
        )
        .sort("unit")
    )
    conflicts = units.filter(pl.col("conflict"))["unit"]
    if not conflicts.is_empty():
        issues.append(
            TrackingIssue(
                level="warning",
                message="These units have more than one value in a parent "
                "column; each is placed under its first value:",
                values=conflicts.to_list(),
            )
        )
    units = units.drop("conflict")
    return TrackingReference(
        issues,
        units=units,
        ids=frame.drop(parents),
        levels=_levels(settings.tracking_unit, settings.tracking_parents),
    )


def assign_units(
    rows: pl.DataFrame,
    data: pl.DataFrame,
    reference: TrackingReference,
    settings: TrackingSettings,
) -> pl.DataFrame:
    """Add each row's unit and whether that unit is tracked.

    A tracking file's units come from the survey's unit column; a master
    list's come from the master list, through the ID (the IDs in `rows` are
    already normalized), so the survey needs no unit column. A unit is
    tracked when the tracking dataset gives it a target above 0. Other rows,
    and a master list's unexpected IDs, are untracked.
    """
    if reference.ids is not None:
        unit = rows.join(
            reference.ids.select("id", "unit"),
            on="id",
            how="left",
            maintain_order="left",
        )["unit"]
    else:
        unit = normalize_keys(data[settings.survey_unit], settings.strip_leading_zeros)
    tracked = reference.units.filter(pl.col("target") > 0)["unit"]
    return rows.with_columns(
        unit.alias("unit"),
        unit.is_in(tracked.implode()).fill_null(False).alias("tracked"),
    )


def _status(completed: int, target: int) -> UnitStatus:
    if completed > target:
        return "over target"
    return "behind" if completed / target * 100 < BEHIND_BELOW else "on track"


def _group_counts(rows: pl.DataFrame, key: str | None) -> pl.DataFrame:
    """Count submissions, distinct IDs and distinct completed IDs per key."""
    aggs = (
        pl.len().alias("submissions"),
        pl.col("id").drop_nulls().n_unique().alias("unique"),
        pl.col("id")
        .filter(pl.col("qualifies"))
        .drop_nulls()
        .n_unique()
        .alias("completed"),
    )
    if key is None:
        return rows.select(*aggs)
    return rows.group_by(key).agg(*aggs)


def unit_levels(rows: pl.DataFrame, reference: TrackingReference) -> list[UnitLevel]:
    """Count each level's units against their targets, with the Untracked group.

    `rows` are the survey rows from `assign_units`. Parents sum their
    children's targets and counts. Units with a target of 0 are left out of
    every level: their rows are in the Untracked group.
    """
    units = reference.units.filter(pl.col("target") > 0)
    tracked = rows.filter(pl.col("tracked"))
    untracked = rows.filter(~pl.col("tracked"))
    levels = []
    for key, column in reference.levels:
        tagged = (
            tracked
            if key == "unit"
            else tracked.join(units.select("unit", key), on="unit", how="left")
        )
        table = (
            units.group_by(key)
            .agg(pl.col("target").sum())
            .join(_group_counts(tagged, key), on=key, how="left")
            .with_columns(pl.col("submissions", "unique", "completed").fill_null(0))
            .sort(key)
        )
        level_rows = [
            UnitRow(
                unit=row[key],
                target=row["target"],
                submissions=row["submissions"],
                unique=row["unique"],
                completed=row["completed"],
                percentage=row["completed"] / row["target"] * 100,
                remaining=max(row["target"] - row["completed"], 0),
                status=_status(row["completed"], row["target"]),
            )
            for row in table.iter_rows(named=True)
        ]
        if untracked.height:
            level_rows.append(
                UnitRow(
                    unit=UNTRACKED,
                    status="untracked",
                    **_group_counts(untracked, None).row(0, named=True),
                )
            )
        levels.append(UnitLevel(column=column, rows=level_rows))
    return levels


def untracked_unit_count(rows: pl.DataFrame, reference: TrackingReference) -> int:
    """Count the survey's units that are not tracked, for a tracking file.

    A master list has no untracked units of its own: its untracked rows are
    unexpected IDs, which have their own count.
    """
    if reference.ids is not None:
        return 0
    # Rows with a blank unit are in the Untracked group but name no unit
    return rows.filter(~pl.col("tracked"))["unit"].drop_nulls().n_unique()


RespondentStatus = Literal[
    "Completed", "Attempted not completed", "Pending", "Unexpected"
]
ATTEMPTED: RespondentStatus = "Attempted not completed"
VISIT_STATUSES = ("Pending", ATTEMPTED)


class Respondent(BaseModel):
    """A master-list respondent, or a survey ID not on the master list."""

    id: str = Field(description="The ID, normalized for matching")
    status: RespondentStatus = Field(
        description="Completed: has a qualifying row. Attempted not completed: "
        "has rows, none qualifying. Pending: has no rows. Unexpected: not on "
        "the master list"
    )
    unit: str | None = Field(None, description="None for an unexpected ID")
    attempts: int = Field(0, ge=0, description="Submissions of the ID")
    last_date: date | None = Field(None, description="The last submission's date")
    extra: dict[str, str | None] = Field(
        default_factory=dict, description="The chosen master-list columns, as text"
    )


def respondents(
    per_id: pl.DataFrame, reference: TrackingReference, display: list[str]
) -> list[Respondent]:
    """Give every master-list respondent and unexpected ID its status.

    Parameters
    ----------
    per_id : pl.DataFrame
        One row per survey ID: ``id``, ``attempts``, ``completed_at`` (null
        when never completed) and ``last_date``.
    reference : TrackingReference
        A usable master list.
    display : list[str]
        The master-list columns to carry, in the order of ``d0``, ``d1``...

    Returns
    -------
    list[Respondent]
        The master list's respondents by unit and ID, then the unexpected
        IDs by ID.
    """
    shown = [f"d{i}" for i in range(len(display))]
    listed = (
        reference.ids.join(per_id, on="id", how="left")
        .with_columns(
            pl.when(pl.col("completed_at").is_not_null())
            .then(pl.lit("Completed"))
            .when(pl.col("attempts").is_not_null())
            .then(pl.lit(ATTEMPTED))
            .otherwise(pl.lit("Pending"))
            .alias("status"),
            pl.col("attempts").fill_null(0),
        )
        .sort("unit", "id")
    )
    unexpected = per_id.join(reference.ids, on="id", how="anti").sort("id")
    return [
        Respondent(
            id=row["id"],
            status=row["status"],
            unit=row["unit"],
            attempts=row["attempts"],
            last_date=row["last_date"],
            extra={name: row[key] for name, key in zip(display, shown, strict=True)},
        )
        for row in listed.iter_rows(named=True)
    ] + [
        Respondent(
            id=row["id"],
            status="Unexpected",
            attempts=row["attempts"],
            last_date=row["last_date"],
        )
        for row in unexpected.iter_rows(named=True)
    ]
