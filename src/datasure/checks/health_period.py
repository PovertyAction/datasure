"""The comparison period of Summary's check health rows, and as-of helpers.

Each row's deltas compare the check now with the check recomputed on the
submissions dated on or before the period start: the date whose end the
period starts from, such as yesterday for the Day period. Kept free of
Streamlit and of the checks, so any check can import it.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum

import polars as pl


class ComparisonPeriod(StrEnum):
    """What the check health deltas compare with; the value is its label."""

    DAY = "Day"
    SEVEN_DAYS = "7 days"
    WEEK = "Week"
    THIRTY_DAYS = "30 days"
    MONTH = "Month"


DEFAULT_PERIOD = ComparisonPeriod.DAY


class Weekday(StrEnum):
    """The first day of the week for the Week period; the value is its label."""

    SUNDAY = "Sunday"
    MONDAY = "Monday"
    TUESDAY = "Tuesday"
    WEDNESDAY = "Wednesday"
    THURSDAY = "Thursday"
    FRIDAY = "Friday"
    SATURDAY = "Saturday"


# Week start choices for the Week period, in the order offered.
WEEKDAYS = tuple(day.value for day in Weekday)
DEFAULT_WEEK_START = Weekday.SUNDAY

_ROLLING_DAYS = {
    ComparisonPeriod.DAY: 1,
    ComparisonPeriod.SEVEN_DAYS: 7,
    ComparisonPeriod.THIRTY_DAYS: 30,
}


def _week_began(today: date, week_start: Weekday) -> date:
    """Return the first day of the week holding `today`."""
    try:
        # date.weekday() counts from Monday as 0.
        first = (list(Weekday).index(Weekday(week_start)) - 1) % 7
    except ValueError:
        raise ValueError(
            f"Unknown week start '{week_start}'; expected one of {', '.join(WEEKDAYS)}"
        ) from None
    return today - timedelta(days=(today.weekday() - first) % 7)


def period_start(
    period: ComparisonPeriod, today: date, week_start: Weekday = DEFAULT_WEEK_START
) -> date:
    """Return the date whose end the period's deltas compare with.

    Submissions dated on or before it are "before"; the rest are in the
    period.

    Parameters
    ----------
    period : ComparisonPeriod
        The comparison period.
    today : date
        Today, from the computer clock in the app.
    week_start : Weekday
        The first day of the week for ``ComparisonPeriod.WEEK``.

    Returns
    -------
    date
        Day: yesterday. 7 days and 30 days: that many days ago. Week: the day
        before the week began. Month: the last day of last month.

    Raises
    ------
    ValueError
        If `week_start` is not a `Weekday`.
    """
    if period in _ROLLING_DAYS:
        return today - timedelta(days=_ROLLING_DAYS[period])
    if period is ComparisonPeriod.WEEK:
        return _week_began(today, week_start) - timedelta(days=1)
    return today.replace(day=1) - timedelta(days=1)


def since_label(
    period: ComparisonPeriod, today: date, week_start: Weekday = DEFAULT_WEEK_START
) -> str:
    """Return where the period starts, to follow "since", as in "since yesterday"."""
    if period is ComparisonPeriod.DAY:
        return "yesterday"
    if period in _ROLLING_DAYS:
        return f"{_ROLLING_DAYS[period]} days ago"
    if period is ComparisonPeriod.WEEK:
        return Weekday(week_start).value
    first = today.replace(day=1)
    return f"{first.day} {first:%b}"


@dataclass(frozen=True)
class DeltaWindow:
    """What a check needs to compute its change over the comparison period.

    Attributes
    ----------
    as_of : date
        The period start (see `period_start`): the check "before" is the
        check on the submissions dated on or before it.
    survey_date : str | None
        Summary's date column: Summary's saved date setting, else the page's
        survey date. None when neither is set.
    backcheck_date : str | None
        The backcheck date column, for the Backchecks row.
    """

    as_of: date
    survey_date: str | None = None
    backcheck_date: str | None = None

    @property
    def has_dates(self) -> bool:
        """Whether any row can have a delta."""
        return bool(self.survey_date or self.backcheck_date)


# --- Dated submissions ---------------------------------------------------- #


def date_expr(column: str, dtype: pl.DataType) -> pl.Expr:
    """Return `column` as a Date expression, null where it is not a date.

    Text is read as an ISO date, ignoring any time after it; datetimes keep
    their calendar day.
    """
    if dtype == pl.String:
        return pl.col(column).str.slice(0, 10).str.to_date("%Y-%m-%d", strict=False)
    if isinstance(dtype, pl.Datetime):
        return pl.col(column).dt.date()
    return pl.col(column).cast(pl.Date, strict=False)


def dated_after(data: pl.DataFrame, column: str, as_of: date) -> pl.Expr:
    """Return whether each row of `data` is dated after `as_of`: in the period.

    Rows without a date are not in the period.
    """
    return date_expr(column, data.schema[column]).fill_null(as_of) > as_of


def on_or_before(data: pl.DataFrame, column: str, as_of: date) -> pl.DataFrame:
    """Return the rows of `data` not dated after `as_of`: the check as of then.

    Rows without a date are kept, so they never count as new in the period.
    """
    return data.filter(~dated_after(data, column, as_of))


def logged_after(log: pl.DataFrame, as_of: date, column: str = "date") -> pl.Expr:
    """Return whether each log entry was made after `as_of`: in the period.

    For the correction and attribution logs, whose `date` is when the entry
    was made. A log without the column has no entries in the period.
    """
    if column not in log.columns:
        return pl.repeat(False, log.height)
    return dated_after(log, column, as_of)


def latest_date(data: pl.DataFrame, column: str) -> date | None:
    """Return the latest date in `column`, or None without one."""
    if column not in data.columns:
        return None
    return data.select(date_expr(column, data.schema[column]).max()).item()
