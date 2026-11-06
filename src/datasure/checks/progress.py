"""Progress check: completions against the target.

All counting lives in `compute_progress`, a pure function that returns a
`ProgressResult`; the page and the summary headline only draw from it. The
page has a settings expander at the top, then a header, then two sections:
Overview (to-do cards and the completions chart) and Follow-up (who needs
another visit, and how many tries a completion takes).
"""

import math
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Literal

import plotly.graph_objects as go
import polars as pl
import streamlit as st
from pydantic import BaseModel, Field, ValidationError, field_validator

from datasure.checks.check_configs import progress_config
from datasure.checks.context import CheckContext
from datasure.checks.headline import CheckHeadline, settings_no_longer_fit
from datasure.checks.health_period import date_expr
from datasure.checks.progress_tracking import (
    ProgressMode,
    Respondent,
    TrackingIssue,
    TrackingReference,
    TrackingSettings,
    UnitLevel,
    assign_units,
    detect_mode,
    normalize_keys,
    read_tracking,
    respondents,
    unit_levels,
    untracked_unit_count,
)
from datasure.checks.progress_tracking_ui import (
    display_by_unit,
    display_issues,
    display_respondents,
)
from datasure.utils.dataframe_utils import ColumnByType
from datasure.utils.navigations_utils import demo_callout
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)
from datasure.utils.ui_utils import metric_row, section_header
from datasure.utils.view_state import reset_filters_beside, view_factory

TAB_NAME = "progress"
Period = Literal["Day", "Week", "Month"]
SECTIONS_BY_MODE: dict[str, list[str]] = {
    "fixed": ["Overview", "Follow-up"],
    "tracking file": ["Overview", "Follow-up", "By unit"],
    "master list": ["Overview", "Follow-up", "By unit", "Respondents"],
}
# Where a to-do card's link takes the reader, by section
SECTION_ANCHORS = {
    "Follow-up": "follow-up",
    "By unit": "by-unit",
    "Respondents": "respondents",
}
# The header's attention pill jumps here, to the to-do cards
OVERVIEW_ANCHOR = "overview"
# Keys older versions saved the targets under, mapped to the
# ProgressSettings fields they belong to
LEGACY_TARGET_KEYS = {
    "target": "survey_target",
    "target_per_period": "target_submissions_per_period",
}

# Saved view state scope: the check's catalogue slug. The chart
# view, the time period and the follow-up queue filters are personal view
# state. Older versions saved the time period and the removed attempted
# interviews table's extra columns in the check's settings; they move on
# first load, so exports leave them out. The other progress settings
# (columns, targets, field end date and completion condition) are
# configuration.
VIEW_SCOPE = "progress"
check_view = view_factory(
    VIEW_SCOPE,
    legacy=(
        TAB_NAME,
        {
            "time_period_progress_overtime": "time_period",
            "attempted_interviews_display_cols": "display_cols",
        },
    ),
)


# =============================================================================
# Pydantic Models for Data Validation
# =============================================================================


class ProgressSettings(TrackingSettings):
    """Settings for progress report configuration."""

    survey_key: str | None = Field(None, description="Survey key column")
    survey_id: str | None = Field(..., min_length=1, description="Survey ID column")
    survey_date: str | None = Field(None, description="Survey date column")
    survey_target: int | None = Field(
        None, ge=0, description="Target number of completed IDs"
    )
    # Named for the key it is saved under, but it counts completions
    target_submissions_per_period: int | None = Field(
        None, ge=0, description="Target number of completions per time period"
    )
    consent: str | None = Field(None, description="Consent column")
    consent_vals: list[Any] | None = Field(
        None, description="Consent values that count towards completion"
    )
    outcome: str | None = Field(None, description="Outcome column")
    outcome_vals: list[Any] | None = Field(
        None, description="Outcome values that count towards completion"
    )
    field_end_date: date | None = Field(
        None, description="The day fieldwork should finish"
    )
    # From the page config only: not a Progress setting, so saved values of
    # the old Enumerator setting are ignored (see load_default_settings)
    enumerator: str | None = Field(
        None, description="Enumerator column, for the follow-up queue"
    )

    @property
    def has_condition(self) -> bool:
        """Whether a completion condition is set."""
        return bool(
            (self.consent and self.consent_vals) or (self.outcome and self.outcome_vals)
        )

    def condition(self) -> pl.Expr:
        """Return whether a row meets the completion condition.

        Every row does when no condition is set.
        """
        condition = pl.lit(True)
        for column, values in (
            (self.consent, self.consent_vals),
            (self.outcome, self.outcome_vals),
        ):
            if column and values:
                # nulls_equal: a selected null value matches null rows
                condition &= (
                    pl.col(column).is_in(values, nulls_equal=True).fill_null(False)
                )
        return condition

    @field_validator("survey_target", "target_submissions_per_period")
    @classmethod
    def validate_target(cls, v: int | None) -> int | None:
        """Validate target is positive if provided."""
        if v is not None and v < 0:
            raise ValueError("Target must be a positive number")
        return v


@dataclass(frozen=True)
class TrackingSource:
    """The page's tracking dataset, as the Progress page receives it.

    Attributes
    ----------
    name : str | None
        Its alias in the page config; None when the page has none.
    data : pl.DataFrame | None
        Its rows; None when not set, not imported yet or empty.
    """

    name: str | None = None
    data: pl.DataFrame | None = None


class ProgressCounts(BaseModel):
    """The counts the header and the summary headline show."""

    submissions: int = Field(ge=0, description="Every row")
    unique: int = Field(ge=0, description="Distinct IDs")
    completed: int = Field(
        ge=0, description="Distinct IDs with a row meeting the completion condition"
    )
    target: int | None = Field(None, ge=0, description="Target number of IDs")
    remaining: int | None = Field(
        None, ge=0, description="Completions still needed to reach the target"
    )
    percentage: float | None = Field(
        None, ge=0, description="Completed as a percentage of the target"
    )


class SeriesPoint(BaseModel):
    """One period of the over-time series."""

    start: date = Field(description="The first day of the period")
    completed: int = Field(ge=0, description="IDs first completed in the period")
    cumulative: int = Field(ge=0, description="IDs completed by the period's end")
    partial: bool = Field(description="Whether the period is still under way")


class CurrentPeriod(BaseModel):
    """Completions in the period under way, against the per-period target."""

    period: Period = Field(description="Day, Week or Month")
    start: date = Field(description="The first day of the period")
    completed: int = Field(ge=0, description="IDs first completed in the period")
    target: int = Field(gt=0, description="Target completions per period")


class Pace(BaseModel):
    """How fast completions come in, and what finishing on time needs."""

    per_day: float | None = Field(
        None,
        ge=0,
        description="Mean completions per day over the 7 days up to the last "
        "submission; None with fewer than 3 days of data",
    )
    projected_finish: date | None = Field(
        None, description="When the target is reached at that pace"
    )
    days_left: int | None = Field(
        None, ge=0, description="Days to the field end date, counting today"
    )
    need_per_day: float | None = Field(
        None, ge=0, description="Completions per day needed to finish on time"
    )


class ProgressStatus(BaseModel):
    """The header's one-sentence answer to "will fieldwork finish on time?"."""

    level: Literal["success", "warning", "info"] = Field(
        description="How the status box is drawn: green, amber or neutral"
    )
    title: str = Field(description="The status in a few words")
    message: str = Field(description="One or two sentences of Markdown")


class TodoItem(BaseModel):
    """A to-do card on Overview: something to act on, linking to its section."""

    label: str = Field(description="What needs action")
    count: int = Field(gt=0, description="How many need it")
    section: str = Field(description="The section with the detail")


class Attempt(BaseModel):
    """One submission of an ID, in a follow-up queue row's history."""

    number: int = Field(gt=0, description="1 for the ID's first attempt")
    day: date | None = Field(None, description="The attempt's date")
    outcome: str = Field(description="The outcome column's value")
    enumerator: str | None = Field(None, description="Who made the attempt")


class QueueRow(BaseModel):
    """An ID attempted but never completed, in the follow-up queue."""

    id: str = Field(description="The survey ID")
    attempts: int = Field(gt=0, description="Submissions of the ID")
    last_outcome: str = Field(
        description="The last attempt's outcome, or 'not complete' without an "
        "outcome column"
    )
    last_date: date | None = Field(None, description="The last attempt's date")
    days_since: int | None = Field(
        None, ge=0, description="Days from the last attempt to today"
    )
    last_enumerator: str | None = Field(None, description="Who made the last attempt")
    history: list[Attempt] = Field(description="Every attempt, first to last")


class FollowUpMetrics(BaseModel):
    """The Follow-up section's metrics.

    The repeat-ID metrics always hold; the others need a completion
    condition and are None without one.
    """

    repeat_ids: int = Field(ge=0, description="IDs submitted more than once")
    avg_attempts: float | None = Field(
        None, ge=0, description="Submissions per ID; None without IDs"
    )
    max_attempts: int = Field(ge=0, description="The most submissions of one ID")
    need_follow_up: int | None = Field(
        None, ge=0, description="IDs attempted but never completed"
    )
    first_try_rate: float | None = Field(
        None,
        ge=0,
        le=100,
        description="Completions at attempt 1, as a percentage of completions",
    )
    avg_attempts_per_completion: float | None = Field(
        None, ge=1, description="The mean attempt number completions came at"
    )
    open_3_plus: int | None = Field(
        None, ge=0, description="Open IDs with 3 or more attempts"
    )


class AttemptBucket(BaseModel):
    """One bar group of the attempts-to-outcome chart."""

    attempt: str = Field(description='The attempt number: "1", "2", "3" or "4+"')
    completed: int = Field(ge=0, description="IDs completed at this attempt")
    open: int = Field(
        ge=0, description="Open IDs with exactly this many attempts (4+: or more)"
    )
    submitted: int = Field(ge=0, description="IDs submitted this many times")


class ProgressResult(BaseModel):
    """Everything the Progress page draws, from `compute_progress`."""

    mode: ProgressMode = Field("fixed", description="Where the target comes from")
    sections: list[str] = Field(description="The sections the page shows, in order")
    counts: ProgressCounts
    target_path: list[tuple[date, float]] = Field(
        default_factory=list,
        description="The cumulative target line: from 0 to the target by the "
        "field end date, else flat at the target; empty without a target",
    )
    todos: list[TodoItem] = Field(
        default_factory=list, description="To-do cards, only those above zero"
    )
    pace: Pace = Field(default_factory=Pace)
    status: ProgressStatus | None = Field(
        None, description="Whether fieldwork will finish on time; None without a target"
    )
    current_period: CurrentPeriod | None = Field(
        None, description="None without a per-period target or a date column"
    )
    series: list[SeriesPoint] = Field(
        default_factory=list,
        description="Completions per period up to today; empty without dates",
    )
    follow_up: FollowUpMetrics = Field(
        default_factory=lambda: FollowUpMetrics(repeat_ids=0, max_attempts=0),
        description="The Follow-up section's metrics",
    )
    attempts_to_outcome: list[AttemptBucket] = Field(
        default_factory=list,
        description="Completed and open IDs at attempts 1, 2, 3 and 4+",
    )
    follow_up_queue: list[QueueRow] = Field(
        default_factory=list,
        description="Open IDs, most attempts first, then longest since the last "
        "attempt; empty without a completion condition",
    )
    issues: list[TrackingIssue] = Field(
        default_factory=list,
        description="Errors and warnings about the tracking dataset",
    )
    unit_levels: list[UnitLevel] = Field(
        default_factory=list,
        description="The By unit table at each level, units first; empty in "
        "fixed mode or when an error stops the tracking dataset being used",
    )
    untracked_units: int = Field(
        0, ge=0, description="Survey units the tracking file has no target for"
    )
    respondents: list[Respondent] = Field(
        default_factory=list,
        description="Master-list respondents and unexpected IDs; empty outside "
        "master-list mode",
    )


def _progress_rows(data: pl.DataFrame, settings: ProgressSettings) -> pl.DataFrame:
    """Return each row's ID, date and whether it meets the completion condition.

    Without an ID column each row is its own ID. Without a date column, or
    one the data no longer has, every date is null: the counts stand, but
    there is no series or pace.
    """
    id_expr = (
        pl.col(settings.survey_id) if settings.survey_id else pl.int_range(pl.len())
    )
    date_col = settings.survey_date
    day = (
        date_expr(date_col, data.schema[date_col])
        if date_col in data.columns
        else pl.lit(None, dtype=pl.Date)
    )
    return data.select(
        id_expr.alias("id"),
        day.alias("date"),
        settings.condition().alias("qualifies"),
    )


NOT_COMPLETE = "not complete"
MISSING_OUTCOME = "missing"


def _attempts(
    data: pl.DataFrame, rows: pl.DataFrame, settings: ProgressSettings
) -> pl.DataFrame:
    """Return every attempt of every ID, numbered from 1 in date order.

    Attempts on the same day keep their order in the data; undated attempts
    come last. Rows without an ID are left out. Without an outcome column,
    an attempt's outcome is "not complete" unless it meets the completion
    condition.
    """

    def text(column: str | None) -> pl.Series:
        if column and column in data.columns:
            return data[column].cast(pl.String)
        return pl.Series(values=[None] * data.height, dtype=pl.String)

    if settings.outcome and settings.outcome in data.columns:
        outcome = text(settings.outcome).fill_null(MISSING_OUTCOME)
    else:
        outcome = rows["qualifies"].replace_strict(
            {True: "complete", False: NOT_COMPLETE}, return_dtype=pl.String
        )
    return (
        rows.with_columns(
            outcome.alias("outcome"), text(settings.enumerator).alias("enumerator")
        )
        .with_row_index("row")
        .filter(pl.col("id").is_not_null())
        .with_columns(pl.col("id").cast(pl.String))
        .sort(["id", "date", "row"], nulls_last=True)
        .with_columns(pl.int_range(1, pl.len() + 1).over("id").alias("number"))
    )


def _per_id(attempts: pl.DataFrame) -> pl.DataFrame:
    """Sum up each ID's attempts: how many, when it completed and the last one."""
    return attempts.group_by("id").agg(
        pl.len().alias("attempts"),
        pl.col("number").filter(pl.col("qualifies")).min().alias("completed_at"),
        pl.col("date").last().alias("last_date"),
        pl.col("outcome").last().alias("last_outcome"),
        pl.col("enumerator").last().alias("last_enumerator"),
        pl.struct(
            pl.col("number"),
            pl.col("date").alias("day"),
            pl.col("outcome"),
            pl.col("enumerator"),
        ).alias("history"),
    )


FOLLOW_UP_AFTER = 3
ATTEMPT_BUCKETS = ["1", "2", "3", "4+"]
OPEN_AFTER_3_LABEL = "Respondents open after 3+ attempts"


def _follow_up_metrics(
    per_id: pl.DataFrame, settings: ProgressSettings
) -> FollowUpMetrics:
    """Count the repeat IDs and, with a completion condition, the follow-ups."""
    attempts = per_id["attempts"]
    repeat = FollowUpMetrics(
        repeat_ids=attempts.filter(attempts > 1).len(),
        avg_attempts=attempts.mean(),
        max_attempts=attempts.max() or 0,
    )
    if not settings.has_condition:
        return repeat
    completed_at = per_id["completed_at"].drop_nulls()
    open_attempts = per_id.filter(pl.col("completed_at").is_null())["attempts"]
    return repeat.model_copy(
        update={
            "need_follow_up": open_attempts.len(),
            "first_try_rate": (
                (completed_at == 1).sum() / completed_at.len() * 100
                if completed_at.len()
                else None
            ),
            "avg_attempts_per_completion": completed_at.mean(),
            "open_3_plus": (open_attempts >= FOLLOW_UP_AFTER).sum(),
        }
    )


def _attempts_to_outcome(
    per_id: pl.DataFrame, settings: ProgressSettings
) -> list[AttemptBucket]:
    """Count IDs completed at, open after and submitted at attempts 1, 2, 3, 4+.

    Without a completion condition no ID is completed or open; only the
    submissions per ID are counted.
    """
    top = len(ATTEMPT_BUCKETS)

    def bucket(column: str) -> pl.Expr:
        return pl.col(column).clip(upper_bound=top).cast(pl.Int64)

    has_condition = settings.has_condition
    counts = per_id.select(
        pl.when(has_condition).then(bucket("completed_at")).alias("completed"),
        pl.when(pl.col("completed_at").is_null() & has_condition)
        .then(bucket("attempts"))
        .alias("open"),
        bucket("attempts").alias("submitted"),
    )
    return [
        AttemptBucket(
            attempt=label,
            **{
                column: (counts[column] == number).sum()
                for column in ("completed", "open", "submitted")
            },
        )
        for number, label in enumerate(ATTEMPT_BUCKETS, start=1)
    ]


BEHIND_LABEL = "Units below 50% of target"
UNTRACKED_LABEL = "Untracked units"
UNEXPECTED_LABEL = "Unexpected IDs"


def _todos(result: "ProgressResult") -> list[TodoItem]:
    """List the to-do cards whose count is above zero."""
    finest = result.unit_levels[0].rows if result.unit_levels else []
    counts = [
        (
            UNEXPECTED_LABEL,
            sum(r.status == "Unexpected" for r in result.respondents),
            "Respondents",
        ),
        (BEHIND_LABEL, sum(r.status == "behind" for r in finest), "By unit"),
        (UNTRACKED_LABEL, result.untracked_units, "By unit"),
        (OPEN_AFTER_3_LABEL, result.follow_up.open_3_plus or 0, "Follow-up"),
    ]
    return [
        TodoItem(label=label, count=count, section=section)
        for label, count, section in counts
        if count
    ]


def _follow_up_queue(
    per_id: pl.DataFrame, settings: ProgressSettings, as_of: date
) -> list[QueueRow]:
    """List the open IDs, most attempts first, then longest since the last one."""
    if not settings.has_condition:
        return []
    open_ids = per_id.filter(pl.col("completed_at").is_null()).sort(
        ["attempts", "last_date", "id"],
        descending=[True, False, False],
        nulls_last=True,
    )
    return [
        QueueRow(
            **row,
            days_since=(
                max((as_of - row["last_date"]).days, 0) if row["last_date"] else None
            ),
        )
        for row in open_ids.drop("completed_at").iter_rows(named=True)
    ]


PERIOD_EVERY = {"Day": "1d", "Week": "1w", "Month": "1mo"}


def period_start(day: date, period: Period) -> date:
    """Return the first day of the period containing `day`.

    Weeks start on Monday.
    """
    return pl.select(pl.lit(day).dt.truncate(PERIOD_EVERY[period])).item()


def _first_completions(rows: pl.DataFrame) -> pl.DataFrame:
    """Return the date each ID first met the completion condition, if dated."""
    return (
        rows.filter(pl.col("qualifies") & pl.col("id").is_not_null())
        .group_by("id")
        .agg(pl.col("date").min())
        .drop_nulls("date")
    )


def _series(
    rows: pl.DataFrame, firsts: pl.DataFrame, as_of: date, period: Period
) -> list[SeriesPoint]:
    """Count first completions per period, from the first one to the last submission.

    Periods with no completions between them count 0; periods after the
    last submission, such as the ones since data collection stopped, are
    left out. Submissions dated after today are ignored, so the series never
    runs past the current period. `firsts` holds no dates after today.
    """
    dates = rows["date"]
    last_submission = dates.filter(dates <= as_of).max()
    if firsts.is_empty() or last_submission is None:
        return []
    every = PERIOD_EVERY[period]
    counts = (
        firsts.select(pl.col("date").dt.truncate(every).alias("start"))
        .group_by("start")
        .agg(pl.len().alias("completed"))
    )
    current = period_start(as_of, period)
    last = period_start(last_submission, period)
    starts = pl.date_range(counts["start"].min(), last, every, eager=True)
    filled = (
        pl.DataFrame({"start": starts})
        .join(counts, on="start", how="left")
        .with_columns(pl.col("completed").fill_null(0))
        .with_columns(pl.col("completed").cum_sum().alias("cumulative"))
    )
    return [
        SeriesPoint(**row, partial=row["start"] == current)
        for row in filled.iter_rows(named=True)
    ]


def _current_period(
    firsts: pl.DataFrame, settings: ProgressSettings, as_of: date, period: Period
) -> CurrentPeriod | None:
    """Count the first completions in the period containing today."""
    target = settings.target_submissions_per_period
    if not target or not settings.survey_date:
        return None
    start = period_start(as_of, period)
    in_period = pl.col("date").dt.truncate(PERIOD_EVERY[period]) == start
    return CurrentPeriod(
        period=period,
        start=start,
        completed=firsts.filter(in_period).height,
        target=target,
    )


PACE_WINDOW_DAYS = 7
MIN_PACE_DAYS = 3


def _pace(
    rows: pl.DataFrame,
    firsts: pl.DataFrame,
    settings: ProgressSettings,
    remaining: int | None,
    as_of: date,
) -> Pace:
    """Work out the pace, the projected finish and the completions needed per day.

    The pace is the mean completions per day over the 7 days up to the last
    submission, or over the days since the first submission when fieldwork
    is shorter, so a pause in the data does not drop it to 0. It is left out
    with fewer than 3 days of submissions. The projected finish counts today
    as a day of fieldwork, as the days left do.
    """
    days_left = need_per_day = None
    if settings.field_end_date:
        days_left = max((settings.field_end_date - as_of).days + 1, 0)
        if remaining and days_left:
            need_per_day = remaining / days_left

    dated = rows["date"].drop_nulls()
    days = dated.filter(dated <= as_of)
    if days.n_unique() < MIN_PACE_DAYS:
        return Pace(days_left=days_left, need_per_day=need_per_day)
    last = days.max()
    window_start = max(last - timedelta(days=PACE_WINDOW_DAYS - 1), days.min())
    in_window = firsts.filter(pl.col("date").is_between(window_start, last)).height
    per_day = in_window / ((last - window_start).days + 1)

    projected_finish = None
    if remaining and per_day:
        days_needed = math.ceil(remaining / per_day)
        projected_finish = as_of + timedelta(days=days_needed - 1)
    return Pace(
        per_day=per_day,
        projected_finish=projected_finish,
        days_left=days_left,
        need_per_day=need_per_day,
    )


def short_date(day: date, as_of: date) -> str:
    """Format a date as "Mon 16 Nov", adding the year when it isn't as_of's."""
    text = f"{day:%a} {day.day} {day:%b}"
    return text if day.year == as_of.year else f"{text} {day.year}"


def per_day_text(rate: float) -> str:
    """Format a daily rate, with two decimals below 1 so a slow pace isn't 0.0."""
    return f"{rate:,.{1 if rate >= 1 else 2}f}"


def _days(n: int) -> str:
    return f"{n:,} day" if n == 1 else f"{n:,} days"


def _status(
    counts: ProgressCounts, pace: Pace, end: date | None, as_of: date
) -> ProgressStatus | None:
    """Say in a sentence whether fieldwork will finish by the field end date.

    None without a target: the header asks for one instead.
    """
    if not counts.target:
        return None
    if not counts.remaining:
        return ProgressStatus(
            level="success",
            title="Target reached",
            message=f"All **{counts.target:,}** completions are in.",
        )
    need = (
        f" Finishing by {short_date(end, as_of)} needs "
        f"**{per_day_text(pace.need_per_day)} a day**."
        if pace.need_per_day is not None
        else ""
    )
    finish = pace.projected_finish
    at_pace = (
        f"At **{per_day_text(pace.per_day)} completions a day**, the target is "
        f"reached on **{short_date(finish, as_of)}**"
        if finish is not None
        else ""
    )
    if end is not None and pace.days_left == 0:
        return ProgressStatus(
            level="warning",
            title="Field end date passed",
            message=f"The field end date ({short_date(end, as_of)}) has passed "
            f"with **{counts.remaining:,}** completions to go."
            + (f" {at_pace}." if at_pace else ""),
        )
    if pace.per_day is None:
        return ProgressStatus(
            level="info",
            title="Not enough data for a projected finish",
            message="A projected finish needs at least 3 days of submissions." + need,
        )
    if finish is None:
        return ProgressStatus(
            level="warning",
            title="No completions in the last 7 days",
            message="Nothing was completed in the 7 days up to the last "
            "submission, so there is no projected finish." + need,
        )
    if end is None:
        return ProgressStatus(
            level="info",
            title=f"Projected finish: {short_date(finish, as_of)}",
            message=f"{at_pace}. Set a field end date in the :material/settings: "
            "settings section above to see whether this is on time.",
        )
    gap = (end - finish).days
    end_text = f"the field end date ({short_date(end, as_of)})"
    if gap >= 0:
        when = f"on {end_text}" if gap == 0 else f"{_days(gap)} before {end_text}"
        return ProgressStatus(
            level="success",
            title="On track to finish on time",
            message=f"{at_pace}, {when}.",
        )
    return ProgressStatus(
        level="warning",
        title="Behind schedule",
        message=f"{at_pace}, {_days(-gap)} after {end_text}.{need}",
    )


def _target_path(
    series: list[SeriesPoint], target: int | None, end: date | None
) -> list[tuple[date, float]]:
    """Return the cumulative target line from the first period.

    It rises from 0 to the target by the field end date. Without an end date,
    or with one no later than the first period, it stays flat at the target.
    """
    if not target or not series:
        return []
    first = series[0].start
    if end and end > first:
        return [(first, 0), (end, target)]
    return [(first, target), (series[-1].start, target)]


def filter_queue(
    queue: list[QueueRow], outcomes: list[str], min_attempts: int
) -> list[QueueRow]:
    """Keep rows with `min_attempts` or more and one of `outcomes` (any if empty)."""
    return [
        row
        for row in queue
        if row.attempts >= min_attempts
        and (not outcomes or row.last_outcome in outcomes)
    ]


QUEUE_COLUMNS = {
    "id": ("ID", pl.String),
    "attempts": ("Attempts", pl.Int64),
    "last_outcome": ("Last outcome", pl.String),
    "last_date": ("Last attempt", pl.Date),
    "days_since": ("Days since", pl.Int64),
    "last_enumerator": ("Last enumerator", pl.String),
}


def queue_frame(queue: list[QueueRow]) -> pl.DataFrame:
    """Return the queue as a table, one row per open ID, for display and export."""
    return pl.DataFrame(
        [[getattr(row, field) for field in QUEUE_COLUMNS] for row in queue],
        schema={label: dtype for label, dtype in QUEUE_COLUMNS.values()},
        orient="row",
    )


def compute_progress(
    data: pl.DataFrame,
    settings: ProgressSettings,
    as_of: date,
    period: Period = "Day",
    tracking: pl.DataFrame | None = None,
) -> ProgressResult:
    """Count progress towards the target as of a date.

    Parameters
    ----------
    data : pl.DataFrame
        The survey data.
    settings : ProgressSettings
        The progress settings: columns, targets and completion condition.
    as_of : date
        Today: the date the current period, the pace and the days left to
        the field end date are worked out from.
    period : {"Day", "Week", "Month"}
        The period of the over-time series and of the current-period count.
    tracking : pl.DataFrame | None
        The tracking dataset: a tracking file or a master list. None for a
        fixed target.

    Returns
    -------
    ProgressResult
        The counts, series and pace the page draws.
    """
    TimePeriodConfig(time_period=period)
    mode = detect_mode(tracking is not None, settings)
    rows, reference = _rows_and_reference(data, settings, tracking)
    counts = _counts(rows, _target(settings, reference))
    # A completion dated after today, such as one from a device with a wrong
    # clock, counts in Completed but not in the chart, period or pace
    firsts = _first_completions(rows).filter(pl.col("date") <= as_of)

    series = _series(rows, firsts, as_of, period)
    pace = _pace(rows, firsts, settings, counts.remaining, as_of)
    result = ProgressResult(
        mode=mode,
        sections=SECTIONS_BY_MODE[mode],
        counts=counts,
        pace=pace,
        status=_status(counts, pace, settings.field_end_date, as_of),
        current_period=_current_period(firsts, settings, as_of, period),
        series=series,
        target_path=_target_path(series, counts.target, settings.field_end_date),
        issues=reference.issues if reference else [],
    )
    tagged = None
    if reference is not None and reference.usable:
        tagged = assign_units(rows, data, reference, settings)
        result = result.model_copy(
            update={
                "unit_levels": unit_levels(tagged, reference),
                "untracked_units": untracked_unit_count(tagged, reference),
            }
        )
    # Without an ID column each row is its own ID, which the headline counts
    # accept but which would make every follow-up number up
    if not settings.survey_id:
        return result.model_copy(update={"todos": _todos(result)})
    per_id = _per_id(_attempts(data, rows, settings))
    result = result.model_copy(
        update={
            "follow_up": _follow_up_metrics(per_id, settings),
            "attempts_to_outcome": _attempts_to_outcome(per_id, settings),
            "follow_up_queue": _follow_up_queue(per_id, settings, as_of),
        }
    )
    if tagged is not None and reference.ids is not None:
        result = result.model_copy(
            update={
                "respondents": respondents(per_id, reference, settings.tracking_display)
            }
        )
    return result.model_copy(update={"todos": _todos(result)})


def _rows_and_reference(
    data: pl.DataFrame, settings: ProgressSettings, tracking: pl.DataFrame | None
) -> tuple[pl.DataFrame, TrackingReference | None]:
    """Return the progress rows and the checked tracking dataset, if any.

    With a usable master list, the survey IDs are normalized the way the
    master list's are, so every count matches IDs the same way.
    """
    rows = _progress_rows(data, settings)
    if tracking is None:
        return rows, None
    reference = read_tracking(tracking, settings, settings.survey_id, data.columns)
    if reference.usable and reference.ids is not None:
        rows = rows.with_columns(
            normalize_keys(rows["id"], settings.strip_leading_zeros).alias("id")
        )
    return rows, reference


def _target(
    settings: ProgressSettings, reference: TrackingReference | None
) -> int | None:
    """The fixed target, or the tracking dataset's total in the file modes."""
    if reference is None:
        return settings.survey_target or None
    return reference.target or None


def _counts(rows: pl.DataFrame, target: int | None) -> ProgressCounts:
    """Count submissions, unique and completed IDs against the target."""
    completed = rows.filter(pl.col("qualifies"))["id"].drop_nulls().n_unique()
    return ProgressCounts(
        submissions=rows.height,
        unique=rows["id"].drop_nulls().n_unique(),
        completed=completed,
        target=target,
        remaining=max(target - completed, 0) if target else None,
        percentage=completed / target * 100 if target else None,
    )


def compute_counts(
    data: pl.DataFrame,
    settings: ProgressSettings,
    tracking: pl.DataFrame | None = None,
) -> ProgressCounts:
    """Count progress without the series and pace, for Summary's Progress row.

    The same counts `compute_progress` returns. Leaving out the series keeps
    Summary quick when a mis-keyed date stretches it over decades.
    """
    rows, reference = _rows_and_reference(data, settings, tracking)
    return _counts(rows, _target(settings, reference))


class TimePeriodConfig(BaseModel):
    """Configuration for time period aggregation."""

    time_period: Literal["Day", "Week", "Month"] = Field(
        description="Time period for aggregating progress data"
    )

    @field_validator("time_period")
    @classmethod
    def validate_time_period(cls, v: str) -> str:
        """Validate that time period is one of the allowed values."""
        valid_periods = {"Day", "Week", "Month"}
        if v not in valid_periods:
            raise ValueError(
                f"Invalid time period '{v}'. Must be one of: {', '.join(valid_periods)}"
            )
        return v


# =============================================================================
# Settings and Configuration Functions
# =============================================================================


def load_default_settings(
    settings_file: str, config: ProgressSettings
) -> ProgressSettings:
    """Load and merge saved settings with default configuration.

    Loads previously saved progress report settings from the settings file
    and merges them with the provided default configuration. Saved settings
    take precedence over defaults.

    Not cached: the check page rebuilds a check's widgets from these
    settings whenever the check is opened, so they must be current.

    Parameters
    ----------
    settings_file : str
        Path to the settings file containing saved progress configurations.
    config : ProgressSettings
        Default configuration to use as fallback for missing settings.

    Returns
    -------
    ProgressSettings
        Merged settings combining saved and default configurations.
    """
    # Load saved settings
    saved_settings = load_check_settings(settings_file, TAB_NAME)
    # The old Enumerator setting is no longer a Progress setting: the
    # follow-up queue uses the page config's enumerator column
    saved_settings.pop("enumerator", None)

    # Targets used to be saved under other keys, where they never took
    # effect. Load them only when the page config has no target of its own,
    # which may have been set after them.
    for old_key, key in LEGACY_TARGET_KEYS.items():
        old_value = saved_settings.pop(old_key, None)
        if old_value is not None and getattr(config, key) is None:
            saved_settings.setdefault(key, old_value)

    default_settings: dict = dict(config)
    default_settings.update(saved_settings)

    # Merge with defaults
    return ProgressSettings(**default_settings)


def _setting_selectbox(
    settings_file: str,
    setting: str,
    label: str,
    options: list[str],
    default: str | None,
    help_text: str,
    *,
    optional: bool = False,
) -> str | None:
    """Render a column picker for one progress setting and save the choice.

    An optional picker starts with a "None" choice, so a column chosen by
    mistake can be cleared: Streamlit's selectbox has no clear button.
    """
    choices: list[str | None] = [None, *options] if optional else list(options)
    selected = st.selectbox(
        label,
        options=choices,
        format_func=lambda column: "None" if column is None else str(column),
        help=help_text,
        key=f"{setting}_progress",
        index=choices.index(default) if default in options else None,
        on_change=trigger_save,
        kwargs={"state_name": f"{TAB_NAME}_{setting}"},
    )
    save_check_settings(settings_file, TAB_NAME, {setting: selected})
    return selected


@st.cache_data
def _get_unique_values(data: pl.DataFrame, column: str) -> list[Any]:
    """Get unique values from a Polars DataFrame column (cached for performance).

    Parameters
    ----------
    data : pl.DataFrame
        Dataset
    column : str
        Column name

    Returns
    -------
    list[Any]
        List of unique values, in the order they first appear
    """
    return data[column].unique(maintain_order=True).to_list()


def _render_condition_part(
    data: pl.DataFrame,
    settings_file: str,
    setting: str,
    label: str,
    columns: list[str],
    default_column: str | None,
    default_values: list[Any] | None,
    values_help: str,
) -> tuple[str | None, list[Any] | None]:
    """Render one part of the completion condition: a column and its values.

    The saved values always match the ones the page applies, so Summary's
    Progress row counts the same condition. When the column changes, the
    saved values the new column has are saved again. With the same column,
    saved values missing from the current data stay selected and saved.

    Parameters
    ----------
    data : pl.DataFrame
        Survey data, for the column's values.
    settings_file : str
        Path to settings file for saving configurations.
    setting : str
        The column's setting, ``consent`` or ``outcome``; its values are
        saved under ``<setting>_vals``.
    label : str
        The column picker's label.
    columns : list[str]
        The columns offered: categorical only, since the chosen values are
        saved as JSON and dates can't be.
    default_column : str | None
        The saved column.
    default_values : list[Any] | None
        The saved values.
    values_help : str
        Help text for the values picker.

    Returns
    -------
    tuple[str | None, list[Any] | None]
        Selected column and values.
    """
    column = _setting_selectbox(
        settings_file,
        setting,
        label,
        columns,
        default_column,
        f"Leave empty to set no {setting} condition.",
    )
    if not column:
        return None, None

    value_options = _get_unique_values(data, column)
    saved = list(default_values or [])
    values_key = f"{setting}_vals_progress"
    save_flag = f"{TAB_NAME}_{setting}_vals"
    if column == default_column:
        # Keep saved values the current data lacks: a refresh with no
        # "complete" rows must not drop "complete" from the condition
        value_options = value_options + [
            value for value in saved if value not in value_options
        ]
        defaults = saved
    else:
        # The picker still holds the old column's values: start from the
        # saved values the new column has, and save them
        defaults = [value for value in saved if value in value_options]
        st.session_state.pop(values_key, None)
        st.session_state[save_flag] = True
    values = st.multiselect(
        label=f"{label} values",
        options=value_options,
        help=values_help,
        key=values_key,
        default=defaults or None,
        on_change=trigger_save,
        kwargs={"state_name": save_flag},
    )
    save_check_settings(settings_file, TAB_NAME, {f"{setting}_vals": values})
    return column, values


@demo_output_onboarding(TAB_NAME)
def progress_report_settings(
    data: pl.DataFrame,
    settings_file: str,
    config: ProgressSettings,
    categorical_columns: list[str],
    datetime_columns: list[str],
    tracking: TrackingSource | None = None,
) -> ProgressSettings:
    """Render the settings expander at the top of the page; return the settings.

    The expander holds the survey columns, the target source, the targets,
    the field end date and the completion condition. Each setting is saved
    to the settings file when the user changes it, and loads back on the
    next visit.

    Parameters
    ----------
    data : pl.DataFrame
        Survey data, for the completion condition's values.
    settings_file : str
        Path to settings file for saving/loading configurations.
    config : ProgressSettings
        Default configuration used as fallback values.
    categorical_columns : list[str]
        Available categorical columns for selection (survey key and ID).
    datetime_columns : list[str]
        Available datetime columns for date selection.
    tracking : TrackingSource | None
        The page's tracking dataset; None when the page config has none.

    Returns
    -------
    ProgressSettings
        User-configured settings from the UI.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for progress report")
        st.divider()
        return _settings_sections(
            data,
            settings_file,
            config,
            categorical_columns,
            datetime_columns,
            tracking,
        )


def _settings_sections(
    data: pl.DataFrame,
    settings_file: str,
    config: ProgressSettings,
    categorical_columns: list[str],
    datetime_columns: list[str],
    tracking: TrackingSource | None = None,
) -> ProgressSettings:
    """Render the settings sections; see `progress_report_settings`."""
    tracking = tracking or TrackingSource()
    default_settings = load_default_settings(settings_file, config)

    with st.container(border=True):
        section_header("Survey columns", icon=":material/table_chart:")
        sc1, sc2, sc3 = st.columns(3)
        with sc1:
            survey_key = _setting_selectbox(
                settings_file,
                "survey_key",
                "Survey Key",
                categorical_columns,
                default_settings.survey_key,
                "Select the column that contains the survey key",
            )
        with sc2:
            survey_id = _setting_selectbox(
                settings_file,
                "survey_id",
                "Survey ID",
                categorical_columns,
                default_settings.survey_id,
                "Select the column that contains the survey ID. Unique and "
                "Completed count distinct IDs.",
            )
        with sc3:
            survey_date = _setting_selectbox(
                settings_file,
                "survey_date",
                "Survey Date",
                datetime_columns,
                default_settings.survey_date,
                "Select the column that contains the survey date. The chart, "
                "the current period and the projected finish need it.",
            )

    tracking_settings = _tracking_settings_section(
        settings_file, default_settings, tracking, categorical_columns
    )

    with st.container(border=True):
        section_header("Targets", icon=":material/flag:")
        tc1, tc2, tc3 = st.columns(3)
        default_target_per_period = default_settings.target_submissions_per_period
        with tc1:
            if tracking.data is None:
                target = st.number_input(
                    label="Total Expected Interviews",
                    min_value=0,
                    value=default_settings.survey_target,
                    help="Total number of completed interviews expected",
                    key="total_goal_progress",
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_target"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_target": target})
            else:
                # The tracking dataset sets the target. The saved fixed
                # target is kept, for when the tracking dataset is removed.
                target = default_settings.survey_target
                file_total = read_tracking(
                    tracking.data, tracking_settings, survey_id, data.columns
                ).target
                st.number_input(
                    label="Total Expected Interviews",
                    min_value=0,
                    value=file_total,
                    disabled=True,
                    help="Set by the tracking dataset: the sum of the unit "
                    "targets. To set a fixed target, remove the tracking "
                    "dataset in the page configuration.",
                    key="total_goal_progress_tracking",
                )
        with tc2:
            target_per_period = st.number_input(
                label="Target Completions Per Period",
                min_value=0,
                value=default_target_per_period if default_target_per_period else 0,
                help="Target number of completions per day, week or month, "
                "following the period chosen on Overview. 0 sets no target.",
                key="target_per_period_progress",
                on_change=trigger_save,
                kwargs={"state_name": TAB_NAME + "_target_submissions_per_period"},
            )
            save_check_settings(
                settings_file,
                TAB_NAME,
                {"target_submissions_per_period": target_per_period},
            )
        with tc3:
            field_end_date = st.date_input(
                label="Field End Date",
                value=default_settings.field_end_date,
                help="The day fieldwork should finish. Overview then shows the "
                "completions needed per day to finish on time.",
                key="field_end_date_progress",
                on_change=trigger_save,
                kwargs={"state_name": TAB_NAME + "_field_end_date"},
            )
            save_check_settings(
                settings_file,
                TAB_NAME,
                {
                    "field_end_date": field_end_date.isoformat()
                    if field_end_date
                    else None
                },
            )

    with st.container(border=True):
        section_header("Completion condition", icon=":material/task_alt:")
        st.caption(
            "An ID is completed when at least one of its submissions has one of "
            "the consent values and one of the outcome values. With no "
            "condition, every ID counts as completed."
        )
        cc1, cc2 = st.columns(2)
        with cc1:
            consent, consent_vals = _render_condition_part(
                data,
                settings_file,
                "consent",
                "Consent column",
                categorical_columns,
                default_settings.consent,
                default_settings.consent_vals,
                "Values that mean the respondent consented",
            )
        with cc2:
            outcome, outcome_vals = _render_condition_part(
                data,
                settings_file,
                "outcome",
                "Outcome column",
                categorical_columns,
                default_settings.outcome,
                default_settings.outcome_vals,
                "Values that mean the interview was completed",
            )

    return ProgressSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        survey_target=target,
        target_submissions_per_period=target_per_period or None,
        consent=consent,
        consent_vals=consent_vals,
        outcome=outcome,
        outcome_vals=outcome_vals,
        field_end_date=field_end_date,
        enumerator=default_settings.enumerator,
        **tracking_settings.model_dump(),
    )


def _setting_multiselect(
    settings_file: str,
    setting: str,
    label: str,
    options: list[str],
    default: list[str],
    help_text: str,
) -> list[str]:
    """Render a multi-column picker for one progress setting and save the choice."""
    selected = st.multiselect(
        label,
        options=options,
        default=[column for column in default if column in options] or None,
        help=help_text,
        key=f"{setting}_progress",
        on_change=trigger_save,
        kwargs={"state_name": f"{TAB_NAME}_{setting}"},
    )
    save_check_settings(settings_file, TAB_NAME, {setting: selected})
    return selected


def _saved_tracking(saved: ProgressSettings) -> TrackingSettings:
    return TrackingSettings(
        **saved.model_dump(include=set(TrackingSettings.model_fields))
    )


def _tracking_settings_section(
    settings_file: str,
    saved: ProgressSettings,
    tracking: TrackingSource,
    categorical_columns: list[str],
) -> TrackingSettings:
    """Render the target source settings; return the tracking settings.

    Without a tracking dataset this only says how to add one. The mode
    follows from the target column: chosen for a tracking file, empty for a
    master list.
    """
    with st.container(border=True):
        section_header("Target source", icon=":material/table_view:")
        if not tracking.name:
            st.caption(
                "The target is a fixed number. To set targets per unit from a "
                "tracking file, or per respondent from a master list, add a "
                "**Tracking Dataset** in the page configuration. That turns "
                "on the **By unit** section, and **Respondents** for a master "
                "list."
            )
            return _saved_tracking(saved)
        if tracking.data is None:
            st.warning(
                f"The tracking dataset **{tracking.name}** has no rows or is "
                "not imported yet. Import it on the Import Data page. Until "
                "then the target is the fixed number.",
                icon=":material/warning:",
            )
            return _saved_tracking(saved)
        columns = tracking.data.columns
        st.caption(
            f"Targets come from **{tracking.name}**. Choose a target column for "
            "a tracking file (one row per unit), or choose None for a "
            "master list (one row per expected respondent)."
        )
        c1, c2, c3 = st.columns(3)
        with c1:
            target_column = _setting_selectbox(
                settings_file,
                "tracking_target",
                "Target column",
                columns,
                saved.tracking_target,
                "Each unit's target. Choose None for a master list.",
                optional=True,
            )
        with c2:
            unit = _setting_selectbox(
                settings_file,
                "tracking_unit",
                "Unit column (tracking dataset)",
                columns,
                saved.tracking_unit,
                "The unit each row belongs to, such as a village. Optional for "
                "a master list.",
                optional=True,
            )
        survey_unit, tracking_id = saved.survey_unit, saved.tracking_id
        display = saved.tracking_display
        with c3:
            if target_column:
                survey_unit = _setting_selectbox(
                    settings_file,
                    "survey_unit",
                    "Unit column (survey)",
                    categorical_columns,
                    saved.survey_unit,
                    "The survey column holding the same units",
                    optional=True,
                )
            else:
                tracking_id = _setting_selectbox(
                    settings_file,
                    "tracking_id",
                    "ID column (master list)",
                    columns,
                    saved.tracking_id,
                    "Matched to the Survey ID column above",
                )
        used = {target_column, unit, tracking_id}
        parents = _setting_multiselect(
            settings_file,
            "tracking_parents",
            "Parent columns, finest first",
            [column for column in columns if column not in used],
            saved.tracking_parents,
            "Higher levels the units roll up to, such as district then region. "
            "A parent's target is the sum of its units' targets.",
        )
        if not target_column:
            display = _setting_multiselect(
                settings_file,
                "tracking_display",
                "Extra columns for respondent lists",
                [column for column in columns if column != tracking_id],
                saved.tracking_display,
                "Master-list columns shown and exported with each respondent "
                "list, such as a landmark",
            )
        strip = st.toggle(
            "Ignore leading zeros in IDs and units",
            value=saved.strip_leading_zeros,
            help="Match 0123 to 123. IDs and units are always matched as text "
            "with spaces trimmed, and case matters.",
            key="strip_leading_zeros_progress",
            on_change=trigger_save,
            kwargs={"state_name": f"{TAB_NAME}_strip_leading_zeros"},
        )
        save_check_settings(settings_file, TAB_NAME, {"strip_leading_zeros": strip})
    return TrackingSettings(
        tracking_target=target_column,
        tracking_unit=unit,
        survey_unit=survey_unit,
        tracking_id=tracking_id,
        tracking_parents=parents,
        strip_leading_zeros=strip,
        tracking_display=display,
    )


# =============================================================================
# Header - above both sections
# =============================================================================

PERIOD_LABELS = {"Day": "Today", "Week": "This week", "Month": "This month"}


def describe_condition(settings: ProgressSettings) -> str:
    """Describe the completion condition, such as "consent in [yes]"."""
    parts = [
        f"{column} in {values}"
        for column, values in (
            (settings.consent, settings.consent_vals),
            (settings.outcome, settings.outcome_vals),
        )
        if column and values
    ]
    return " and ".join(parts) if parts else "none (every ID counts)"


def describe_target(result: ProgressResult, tracking_name: str | None) -> str:
    """Name the target's source and size for the header strip."""
    target = result.counts.target
    if result.mode == "fixed":
        return f"fixed number, {target:,}" if target else "fixed number, not set"
    if not result.unit_levels:
        return f"{result.mode} **{tracking_name}**, not usable yet"
    if not target:
        return f"{result.mode} **{tracking_name}**, every target is 0"
    if result.mode == "tracking file":
        units = sum(r.target is not None for r in result.unit_levels[0].rows)
        return f"tracking file **{tracking_name}**, {target:,} across {units:,} units"
    return f"master list **{tracking_name}**, {target:,} respondents"


def attention_text(result: ProgressResult) -> str | None:
    """The header's pill linking to the to-do cards; None when there are none."""
    count = len(result.todos)
    if not count:
        return None
    things = "thing needs" if count == 1 else "things need"
    return (
        f"[:orange-badge[:material/warning: {count} {things} attention]]"
        f"(#{OVERVIEW_ANCHOR})"
    )


@demo_output_onboarding(TAB_NAME)
def display_progress_header(
    result: ProgressResult,
    settings: ProgressSettings,
    tracking_name: str | None = None,
) -> None:
    """Draw the header at the top of the Progress page.

    Parameters
    ----------
    result : ProgressResult
        The computed progress.
    settings : ProgressSettings
        The settings the progress was computed with.
    tracking_name : str | None
        The tracking dataset's alias, named in the target-source strip.
    """
    display_issues(result.issues)
    counts = result.counts
    st.caption(
        f"**Target:** {describe_target(result, tracking_name)} · "
        f"**Completion condition:** {describe_condition(settings)}"
    )
    pill = attention_text(result)
    if pill:
        st.markdown(pill)
    completed_help = (
        "Distinct IDs with a submission that meets the completion condition"
    )
    metrics = [
        ("Submissions", f"{counts.submissions:,}", "Every submission"),
        ("Unique", f"{counts.unique:,}", "Distinct IDs"),
    ]
    if counts.percentage is None:
        st.info(
            "Target number of interviews is not set. Set it in the "
            ":material/settings: settings section above."
            if result.mode == "fixed"
            else "There is no target until the tracking dataset can be used. "
            "Finish the target source in the :material/settings: settings "
            "section above."
        )
        metrics.append(("Completed", f"{counts.completed:,}", completed_help))
    else:
        _display_headline(result)

    current = result.current_period
    if current is not None:
        metrics.append(
            (
                PERIOD_LABELS[current.period],
                f"{current.completed:,} / {current.target:,}",
                "IDs first completed in the current period, against the "
                "per-period target",
            )
        )
    pace = result.pace
    metrics.append(
        (
            "Pace",
            "—" if pace.per_day is None else f"{per_day_text(pace.per_day)}/day",
            "Mean completions per day over the 7 days up to the last submission; "
            "needs at least 3 days of submissions",
        )
    )
    if pace.days_left is not None:
        metrics.append(
            (
                "Days left",
                f"{pace.days_left:,}",
                f"Days to the field end date ({settings.field_end_date:%d %b %Y}), "
                "counting today",
            )
        )
    metric_row(metrics)


STATUS_ICONS = {
    "success": ":material/check_circle:",
    "warning": ":material/warning:",
    "info": ":material/info:",
}


def progress_fraction(percentage: float) -> float:
    """Return the percentage as the 0-1 fraction `st.progress` accepts.

    Completions can pass the target, and `st.progress` raises on a value
    above 1, so the bar stops full at 100%; the text keeps the real figure.
    """
    return min(max(percentage / 100, 0.0), 1.0)


def _display_headline(result: ProgressResult) -> None:
    """Draw the percentage and counts above a progress bar, with the status beside."""
    counts = result.counts
    headline, status_col = st.columns([2, 3], vertical_alignment="center")
    to_go = f"{counts.remaining:,} to go" if counts.remaining else "target reached"
    with headline:
        st.markdown(
            f"### {counts.percentage:.1f}% complete\n"
            f"**{counts.completed:,}** of {counts.target:,} completed · {to_go}"
        )
        st.progress(progress_fraction(counts.percentage))
    status = result.status
    if status is not None:
        draw = getattr(status_col, status.level)
        draw(f"**{status.title}**  \n{status.message}", icon=STATUS_ICONS[status.level])


# =============================================================================
# Overview - completions against the target
# =============================================================================

CHART_VIEWS = ["Cumulative", "Per period"]
MET_COLOR = "#2ECC71"
MISSED_COLOR = "#f87171"
LINE_COLOR = "#4D5E90"
TARGET_COLOR = "#E67E22"
TRANSPARENT = "rgba(0,0,0,0)"


def render_time_period_selector(settings_file: str) -> Period:
    """Render the Day/Week/Month pills and return the chosen period.

    The choice is saved view state, and sets both the chart's periods and the
    header's current-period count.

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading the selected time period.

    Returns
    -------
    Literal["Day", "Week", "Month"]
        Selected time period for aggregation.
    """
    options_map = {
        "Day": ":material/event: Daily",
        "Week": ":material/date_range: Weekly",
        "Month": ":material/calendar_month: Monthly",
    }
    return st.pills(
        label="Time Period",
        options=options_map.keys(),
        format_func=lambda x: options_map[x],
        help="Select time period for aggregating progress data",
        selection_mode="single",
        required=True,
        **check_view(settings_file).bind(
            PERIOD_KEY, options=PERIODS, default=PERIODS[0]
        ),
    )


PERIODS: list[Period] = ["Day", "Week", "Month"]
PERIOD_KEY = "time_period_progress_overtime"


FOLLOW_UP_ANCHOR = SECTION_ANCHORS["Follow-up"]


def follow_up_title(result: ProgressResult) -> str:
    """Return the Follow-up title; it has a count badge when the queue has rows."""
    queued = len(result.follow_up_queue)
    return f"Follow-up :orange-badge[{queued:,}]" if queued else "Follow-up"


def render_chart_controls(settings_file: str) -> tuple[str, Period]:
    """Render the chart view toggle and the period pills; return both choices."""
    with st.container(horizontal=True):
        chart_view = st.segmented_control(
            "Chart",
            options=CHART_VIEWS,
            required=True,
            help="Cumulative completions against the target path, or "
            "completions per period against the per-period target",
            **check_view(settings_file).bind(
                "progress_chart_view", options=CHART_VIEWS, default=CHART_VIEWS[0]
            ),
        )
        period = render_time_period_selector(settings_file)
    return chart_view, period


def _add_target_line(fig: go.Figure, path: list[tuple[date, float]]) -> None:
    """Draw the cumulative target line on the Overview chart.

    With one period and no end date, the path's two points are the same and
    a line between them draws nothing, so the target spans the chart instead.
    """
    if not path:
        return
    line = {"color": TARGET_COLOR, "width": 2, "dash": "dash"}
    if path[0][0] == path[-1][0]:
        fig.add_hline(y=path[0][1], line=line, annotation_text="Target")
        return
    fig.add_trace(
        go.Scatter(
            x=[day for day, _ in path],
            y=[value for _, value in path],
            mode="lines",
            name="Target",
            line=line,
        )
    )


def progress_figure(
    result: ProgressResult, chart_view: str, target_per_period: int | None
) -> go.Figure:
    """Build the Overview chart from the computed progress.

    The current period is drawn as unfinished: a dotted line to its point on
    the cumulative chart, or a faded bar on the per-period chart.
    """
    points = result.series
    starts = [point.start for point in points]
    finished = [point for point in points if not point.partial]
    fig = go.Figure()
    if chart_view == "Cumulative":
        fig.add_trace(
            go.Scatter(
                x=[point.start for point in finished],
                y=[point.cumulative for point in finished],
                mode="lines+markers",
                name="Completed",
                line={"color": LINE_COLOR, "width": 2},
            )
        )
        if points[-1].partial:
            tail = points[-2:]
            fig.add_trace(
                go.Scatter(
                    x=[point.start for point in tail],
                    y=[point.cumulative for point in tail],
                    mode="lines+markers",
                    name="So far (unfinished)",
                    line={"color": LINE_COLOR, "width": 2, "dash": "dot"},
                )
            )
        _add_target_line(fig, result.target_path)
        y_title = "Completed (cumulative)"
    else:
        completed = [point.completed for point in points]
        colors = [
            LINE_COLOR
            if not target_per_period
            else MET_COLOR
            if point.completed >= target_per_period
            else MISSED_COLOR
            for point in points
        ]
        fig.add_trace(
            go.Bar(
                x=starts,
                y=completed,
                name="Completed",
                marker={
                    "color": colors,
                    "opacity": [0.4 if point.partial else 1.0 for point in points],
                },
                customdata=[
                    " (unfinished)" if point.partial else "" for point in points
                ],
                hovertemplate="<b>%{x}</b>%{customdata}<br>Completed: %{y}"
                "<extra></extra>",
            )
        )
        if target_per_period:
            fig.add_trace(
                go.Scatter(
                    x=[starts[0], starts[-1]],
                    y=[target_per_period, target_per_period],
                    mode="lines",
                    name=f"Target: {target_per_period:,}",
                    line={"color": TARGET_COLOR, "width": 2, "dash": "dash"},
                )
            )
        y_title = "Completed"

    fig.update_layout(
        plot_bgcolor=TRANSPARENT,
        paper_bgcolor=TRANSPARENT,
        height=400,
        margin={"t": 30, "b": 50, "l": 50, "r": 30},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        xaxis={"showgrid": False},
        yaxis={"title_text": y_title, "showgrid": False, "rangemode": "tozero"},
    )
    return fig


@demo_output_onboarding(TAB_NAME)
def display_overview(
    result: ProgressResult, settings: ProgressSettings, chart_view: str
) -> None:
    """Draw the Overview section's to-do cards and completions chart.

    Parameters
    ----------
    result : ProgressResult
        The computed progress.
    settings : ProgressSettings
        The settings the progress was computed with.
    chart_view : str
        "Cumulative" or "Per period".
    """
    for todo in result.todos:
        with st.container(border=True):
            st.markdown(
                f":material/warning: **{todo.label}**: {todo.count:,} · "
                f"[See {todo.section} :material/arrow_downward:]"
                f"(#{SECTION_ANCHORS[todo.section]})"
            )

    if not result.series:
        st.info(
            "The chart needs a date column and at least one dated completion. "
            "To choose the date column, go to the :material/settings: "
            "settings section above."
        )
    else:
        st.plotly_chart(
            progress_figure(result, chart_view, settings.target_submissions_per_period),
            theme=None,
            width="stretch",
        )


# =============================================================================
# Follow-up - who needs another visit, and how many tries a completion takes
# =============================================================================


def attempts_figure(buckets: list[AttemptBucket], has_condition: bool) -> go.Figure:
    """Build the attempts-to-outcome chart.

    With a completion condition: for each attempt number, the IDs completed
    at that attempt and those still open after that many. Without one: the
    IDs submitted that many times.
    """
    labels = [bucket.attempt for bucket in buckets]
    fig = go.Figure()
    if has_condition:
        for name, values, color in (
            ("Completed at this attempt", [b.completed for b in buckets], MET_COLOR),
            ("Still open after this many", [b.open for b in buckets], MISSED_COLOR),
        ):
            fig.add_trace(go.Bar(x=labels, y=values, name=name, marker_color=color))
        y_title = "IDs"
    else:
        fig.add_trace(
            go.Bar(
                x=labels,
                y=[b.submitted for b in buckets],
                name="IDs",
                marker_color=LINE_COLOR,
            )
        )
        y_title = "IDs submitted this many times"
    fig.update_layout(
        barmode="group",
        plot_bgcolor=TRANSPARENT,
        paper_bgcolor=TRANSPARENT,
        height=350,
        margin={"t": 30, "b": 50, "l": 50, "r": 30},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
        },
        xaxis={"title_text": "Attempt", "type": "category", "showgrid": False},
        yaxis={"title_text": y_title, "showgrid": False, "rangemode": "tozero"},
    )
    return fig


def _rate(value: float | None, suffix: str = "") -> str:
    return "—" if value is None else f"{value:,.1f}{suffix}"


def _display_follow_up_metrics(metrics: FollowUpMetrics) -> None:
    if metrics.need_follow_up is None:
        metric_row(
            [
                (
                    "Repeat IDs",
                    f"{metrics.repeat_ids:,}",
                    "IDs submitted more than once",
                ),
                (
                    "Submissions per ID",
                    _rate(metrics.avg_attempts),
                    "Mean submissions of each ID",
                ),
                ("Most submissions", f"{metrics.max_attempts:,}", "Of any one ID"),
            ]
        )
        return
    metric_row(
        [
            (
                "Need follow-up",
                f"{metrics.need_follow_up:,}",
                "IDs attempted but never completed",
            ),
            (
                "Done on 1st try",
                _rate(metrics.first_try_rate, "%"),
                "Completions at the first attempt, as a share of all completions",
            ),
            (
                "Avg attempts per completion",
                _rate(metrics.avg_attempts_per_completion),
                "The mean attempt number completions came at",
            ),
            (
                "3+ attempts, still open",
                f"{metrics.open_3_plus:,}",
                "IDs still open after 3 or more attempts",
            ),
        ]
    )


QUEUE_OUTCOME_KEY = "follow_up_outcomes"
QUEUE_MIN_ATTEMPTS_KEY = "follow_up_min_attempts"


def _display_queue(queue: list[QueueRow], settings_file: str) -> None:
    """Draw the follow-up queue: filters, export, table and attempt history."""
    section_header("Follow-up queue", icon=":material/assignment_return:")
    if not queue:
        st.success("No IDs need a follow-up visit.", icon=":material/check_circle:")
        return
    view = check_view(settings_file)
    outcomes = sorted({row.last_outcome for row in queue})
    fc1, fc2, fc3 = st.columns([0.5, 0.25, 0.25], vertical_alignment="bottom")
    with fc1:
        chosen = st.multiselect(
            "Last outcome",
            options=outcomes,
            placeholder="Any outcome",
            **view.bind(QUEUE_OUTCOME_KEY, options=outcomes, multi=True, default=None),
        )
    with fc2:
        min_attempts = st.number_input(
            "Minimum attempts",
            min_value=1,
            step=1,
            **view.bind(QUEUE_MIN_ATTEMPTS_KEY, value=1),
        )
    shown = filter_queue(queue, chosen or [], int(min_attempts or 1))
    table = queue_frame(shown)
    with fc3:
        st.download_button(
            "Download queue (CSV)",
            data=table.write_csv().encode("utf-8"),
            file_name="follow_up_queue.csv",
            mime="text/csv",
            icon=":material/download:",
            width="stretch",
            help="The IDs in the queue below, with the filters applied.",
        )
    if not shown:
        st.info("No IDs match the filters.")
        return
    st.caption(
        f"{len(shown):,} of {len(queue):,} IDs. Select a row to see its attempts."
    )
    selection = st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        on_select="rerun",
        selection_mode="single-row",
        # A new key per filter, so a selected row can't point at another ID
        key=f"follow_up_queue_{chosen}_{min_attempts}",
        column_config={"ID": st.column_config.Column(pinned=True)},
    )
    rows = selection.selection.rows if selection else []
    if rows and rows[0] < len(shown):
        row = shown[rows[0]]
        st.markdown(f"**Attempts for {row.id}**")
        st.dataframe(
            pl.DataFrame(
                [[a.number, a.day, a.outcome, a.enumerator] for a in row.history],
                schema={
                    "Attempt": pl.Int64,
                    "Date": pl.Date,
                    "Outcome": pl.String,
                    "Enumerator": pl.String,
                },
                orient="row",
            ),
            hide_index=True,
            width="stretch",
        )


@demo_output_onboarding(TAB_NAME)
def display_follow_up(
    result: ProgressResult, settings: ProgressSettings, settings_file: str
) -> None:
    """Draw the Follow-up section: metrics, attempts-to-outcome chart and queue.

    Without a completion condition there is no queue: the section shows the
    repeat-ID metrics and chart, and says how to turn the queue on.

    Parameters
    ----------
    result : ProgressResult
        The computed progress.
    settings : ProgressSettings
        The settings the progress was computed with.
    settings_file : str
        The page's settings file, for the queue filters' view state.
    """
    if not settings.survey_id:
        st.info(
            "Follow-up needs the survey ID column. To choose it, go to the "
            ":material/settings: settings section above."
        )
        return
    _display_follow_up_metrics(result.follow_up)
    if not settings.has_condition:
        st.info(
            "Set a completion condition in the :material/settings: settings "
            "section above to see who needs a follow-up visit and how many "
            "tries a completion takes."
        )
    st.plotly_chart(
        attempts_figure(result.attempts_to_outcome, settings.has_condition),
        theme=None,
        width="stretch",
    )
    if settings.has_condition:
        _display_queue(result.follow_up_queue, settings_file)

    demo_callout(
        "**Next**: :material/arrow_upward: Scroll up and select **Data integrity → Missing Values**."
    )


# =============================================================================
# Main Report Function
# =============================================================================


def stale_condition_columns(saved: ProgressSettings, columns: list[str]) -> list[str]:
    """Return the saved consent and outcome columns the pickers no longer offer.

    A prep step can drop or rename a column. Its picker then starts empty
    without saving, so the page counts without that part of the condition
    while Summary still reads the missing column. The page warns instead.
    """
    return [
        column
        for column in (saved.consent, saved.outcome)
        if column and column not in columns
    ]


@demo_output_onboarding(TAB_NAME)
def progress_report(
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
    survey_columns: ColumnByType,
    tracking: TrackingSource | None = None,
) -> None:
    """Display the Progress page: settings, header, then the sections.

    The settings expander sits at the top, as on Summary, with "Reset
    filters" beside it. `compute_progress` then counts the progress once and
    the header and the sections draw from its result: Overview and
    Follow-up, then By unit with a tracking dataset and Respondents with a
    master list.

    Parameters
    ----------
    data : pl.DataFrame
        Survey data to analyze and display.
    setting_file : str
        Path to settings file for configuration persistence.
    config : dict
        Default configuration dictionary to initialize ProgressSettings.
    survey_columns : ColumnByType
        Column names categorized by data type.
    tracking : TrackingSource | None
        The page's tracking dataset; None when the page config has none.
    """
    tracking = tracking or TrackingSource()
    st.title("Progress Tracking")
    saved_view = check_view(setting_file)
    with reset_filters_beside(saved_view):
        settings = progress_report_settings(
            data,
            setting_file,
            ProgressSettings(**config),
            survey_columns.categorical_columns,
            survey_columns.datetime_columns,
            tracking,
        )

    saved = load_default_settings(setting_file, ProgressSettings(**config))
    for column in stale_condition_columns(saved, survey_columns.categorical_columns):
        st.warning(
            f"The saved completion condition uses **{column}**, which is no "
            "longer in the data. This page counts without it, so Summary's "
            "Progress row won't match. Pick another column in the "
            ":material/settings: settings section above.",
            icon=":material/warning:",
        )

    # The header sits above the chart controls but needs the period they hold
    header = st.container()
    section_header("Overview", icon=":material/insights:", anchor=OVERVIEW_ANCHOR)
    chart_view, period = render_chart_controls(setting_file)

    result = compute_progress(
        data, settings, date.today(), period, tracking=tracking.data
    )

    with header:
        display_progress_header(result, settings, tracking.name)
    display_overview(result, settings, chart_view)

    st.divider()
    section_header(
        follow_up_title(result),
        icon=":material/assignment_return:",
        anchor=FOLLOW_UP_ANCHOR,
    )
    display_follow_up(result, settings, setting_file)

    if "By unit" in result.sections:
        st.divider()
        section_header(
            "By unit",
            icon=":material/holiday_village:",
            anchor=SECTION_ANCHORS["By unit"],
        )
        display_by_unit(result.unit_levels, saved_view)
    if "Respondents" in result.sections:
        st.divider()
        section_header(
            "Respondents",
            icon=":material/groups:",
            anchor=SECTION_ANCHORS["Respondents"],
        )
        display_respondents(
            result.respondents, result.unit_levels, settings.tracking_display
        )


class ProgressResolution(BaseModel):
    """Progress as other pages read it, through `resolve_progress`."""

    mode: ProgressMode = Field(description="Where the target comes from")
    target: int | None = Field(None, ge=0, description="None when not set")
    achieved: int = Field(
        ge=0, description="Completed IDs; every ID without a completion condition"
    )
    basis: Literal["completed interviews", "unique IDs"] = Field(
        description="What `achieved` counts"
    )
    unit_levels: list[UnitLevel] = Field(
        default_factory=list,
        description="Unit and parent targets and counts, as on By unit",
    )


def resolve_progress(ctx: CheckContext) -> ProgressResolution:
    """Return the target and the count against it, as the Progress check has them.

    The contract for other pages, such as Project Overview: the target from
    the fixed setting or the tracking dataset, the Completed count (Unique
    when no completion condition is set) and the unit and parent targets.
    A tracking dataset with no rows, or not yet imported, counts as none.

    Parameters
    ----------
    ctx : CheckContext
        The check page's configuration and data.
    """
    data = ctx.data.page_data
    tracking = ctx.data.tracking_data_with_rows
    settings = load_default_settings(
        ctx.config.setting_file, ProgressSettings(**progress_config(ctx))
    )
    rows, reference = _rows_and_reference(data, settings, tracking)
    counts = _counts(rows, _target(settings, reference))
    levels = []
    if reference is not None and reference.usable:
        levels = unit_levels(assign_units(rows, data, reference, settings), reference)
    return ProgressResolution(
        mode=detect_mode(tracking is not None, settings),
        target=counts.target,
        achieved=counts.completed,
        basis="completed interviews" if settings.has_condition else "unique IDs",
        unit_levels=levels,
    )


def progress_headline(
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
    tracking: pl.DataFrame | None = None,
) -> CheckHeadline:
    """Return the progress headline for Summary's check health row.

    The completed IDs out of the target, with the share of the target as the
    Progress header shows it, or only the completed IDs when no target is
    set. Informational: progress is never an issue to resolve.

    Parameters
    ----------
    data : pl.DataFrame
        The survey data.
    setting_file : str
        Path to the page's settings file.
    config : dict
        The page configuration the check starts from.
    tracking : pl.DataFrame | None
        The tracking dataset, when it has rows; its total is the target.
    """
    try:
        settings = load_default_settings(setting_file, ProgressSettings(**config))
        counts = compute_counts(data, settings, tracking)
    except (pl.exceptions.PolarsError, ValidationError) as exc:
        raise settings_no_longer_fit("Progress", exc) from exc
    if counts.target is None:
        return CheckHeadline(
            f"{counts.completed:,}",
            "completed",
            informational=True,
            count=counts.completed,
        )
    return CheckHeadline(
        f"{counts.completed:,} / {counts.target:,}",
        f"{counts.percentage:.2f}% of target",
        informational=True,
        count=counts.completed,
    )
