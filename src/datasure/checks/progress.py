"""Progress check: completions against the target.

All counting lives in `compute_progress`, a pure function that returns a
`ProgressResult`; the page and the summary headline only draw from it. The
page has a settings expander at the top, then a header shown on every tab
above the Overview (the completions chart) and Follow-up (attempted
interviews) tabs.
"""

import math
from datetime import date, timedelta
from typing import Any, Literal

import plotly.graph_objects as go
import polars as pl
import seaborn as sns
import streamlit as st
from pydantic import BaseModel, Field, ValidationError, field_validator

from datasure.checks.headline import CheckHeadline, settings_no_longer_fit
from datasure.checks.health_period import date_expr
from datasure.utils.dataframe_utils import ColumnByType
from datasure.utils.navigations_utils import demo_callout
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)
from datasure.utils.ui_utils import ensure_styler_limit, metric_row, section_header
from datasure.utils.view_state import reset_filters_beside, view_factory

TAB_NAME = "progress"
Period = Literal["Day", "Week", "Month"]
# Only a fixed target for now; the tracking file and master list come later
ProgressMode = Literal["fixed"]
TABS_BY_MODE: dict[str, list[str]] = {"fixed": ["Overview", "Follow-up"]}
# Keys older versions saved the targets under, mapped to the
# ProgressSettings fields they belong to
LEGACY_TARGET_KEYS = {
    "target": "survey_target",
    "target_per_period": "target_submissions_per_period",
}

# Saved view state scope: the check's catalogue slug. The open tab, the chart
# view, the time period and the extra attempted-interview columns are personal
# view state; older versions saved the last two in the check's settings and
# they move on first load. The other progress settings (columns, targets,
# field end date and completion condition) are configuration.
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

# Allow styling large dataframes (the limit is shared and only raised)
ensure_styler_limit(1_000_000)


# =============================================================================
# Pydantic Models for Data Validation
# =============================================================================


class ProgressSettings(BaseModel):
    """Settings for progress report configuration."""

    survey_key: str = Field(None, description="Survey key column")
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
                condition &= pl.col(column).is_in(values).fill_null(False)
        return condition

    @field_validator("survey_target", "target_submissions_per_period")
    @classmethod
    def validate_target(cls, v: int | None) -> int | None:
        """Validate target is positive if provided."""
        if v is not None and v < 0:
            raise ValueError("Target must be a positive number")
        return v


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
    """A to-do card on Overview: something to act on, linking to its tab."""

    label: str = Field(description="What needs action")
    count: int = Field(gt=0, description="How many need it")
    tab: str = Field(description="The tab with the detail")


class ProgressResult(BaseModel):
    """Everything the Progress page draws, from `compute_progress`."""

    mode: ProgressMode = Field("fixed", description="Where the target comes from")
    tabs: list[str] = Field(description="The tabs the page shows, in order")
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
    with fewer than 3 days of submissions. The projected finish counts on
    from today.
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
        projected_finish = as_of + timedelta(days=math.ceil(remaining / per_day))
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
    """Return the cumulative target line from the first period."""
    if not target or not series:
        return []
    first = series[0].start
    if end:
        return [(first, 0), (end, target)]
    return [(first, target), (series[-1].start, target)]


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
        The tracking dataset. Not used yet: only the fixed target is.

    Returns
    -------
    ProgressResult
        The counts, series and pace the page draws.
    """
    TimePeriodConfig(time_period=period)
    rows = _progress_rows(data, settings)
    counts = _counts(rows, settings)
    # A completion dated after today, such as one from a device with a wrong
    # clock, counts in Completed but not in the chart, period or pace
    firsts = _first_completions(rows).filter(pl.col("date") <= as_of)

    series = _series(rows, firsts, as_of, period)
    pace = _pace(rows, firsts, settings, counts.remaining, as_of)
    return ProgressResult(
        mode="fixed",
        tabs=TABS_BY_MODE["fixed"],
        counts=counts,
        pace=pace,
        status=_status(counts, pace, settings.field_end_date, as_of),
        current_period=_current_period(firsts, settings, as_of, period),
        series=series,
        target_path=_target_path(series, counts.target, settings.field_end_date),
    )


def _counts(rows: pl.DataFrame, settings: ProgressSettings) -> ProgressCounts:
    """Count submissions, unique and completed IDs against the target."""
    completed = rows.filter(pl.col("qualifies"))["id"].drop_nulls().n_unique()
    target = settings.survey_target or None
    return ProgressCounts(
        submissions=rows.height,
        unique=rows["id"].drop_nulls().n_unique(),
        completed=completed,
        target=target,
        remaining=max(target - completed, 0) if target else None,
        percentage=completed / target * 100 if target else None,
    )


def compute_counts(data: pl.DataFrame, settings: ProgressSettings) -> ProgressCounts:
    """Count progress without the series and pace, for Summary's Progress row.

    The same counts `compute_progress` returns. Leaving out the series keeps
    Summary quick when a mis-keyed date stretches it over decades.
    """
    return _counts(_progress_rows(data, settings), settings)


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


class AttemptedInterviewsResult(BaseModel):
    """Result model for attempted interviews computation."""

    attempted_interviews: Any = Field(
        description="DataFrame with attempted interviews data"
    )
    total_submitted: int = Field(ge=0, description="Total number of submissions")
    number_of_unique_ids: int = Field(ge=0, description="Number of unique survey IDs")
    min_attempts: int = Field(ge=0, description="Minimum number of attempts")
    max_attempts: int = Field(ge=0, description="Maximum number of attempts")

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


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
) -> str | None:
    """Render a column picker for one progress setting and save the choice."""
    selected = st.selectbox(
        label,
        options=options,
        help=help_text,
        key=f"{setting}_progress",
        index=options.index(default) if default in options else None,
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

    The saved values always match the ones the page applies. When the column
    changes, or saved values are no longer in the column, the kept values
    are saved again, so Summary's Progress row counts the same condition.

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
    defaults = [value for value in saved if value in value_options]
    values_key = f"{setting}_vals_progress"
    save_flag = f"{TAB_NAME}_{setting}_vals"
    if column != default_column:
        # The picker still holds the old column's values: start from the
        # saved values the new column has
        st.session_state.pop(values_key, None)
    if column != default_column or defaults != saved:
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
) -> ProgressSettings:
    """Render the settings expander at the top of the page; return the settings.

    The expander holds the survey columns, the targets, the field end date
    and the completion condition. Each setting is saved to the settings file
    when the user changes it, and loads back on the next visit.

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

    Returns
    -------
    ProgressSettings
        User-configured settings from the UI.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for progress report")
        st.divider()
        return _settings_sections(
            data, settings_file, config, categorical_columns, datetime_columns
        )


def _settings_sections(
    data: pl.DataFrame,
    settings_file: str,
    config: ProgressSettings,
    categorical_columns: list[str],
    datetime_columns: list[str],
) -> ProgressSettings:
    """Render the settings sections; see `progress_report_settings`."""
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

    with st.container(border=True):
        section_header("Targets", icon=":material/flag:")
        tc1, tc2, tc3 = st.columns(3)
        default_target_per_period = default_settings.target_submissions_per_period
        with tc1:
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
    )


# =============================================================================
# Header - shown on every tab
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


@demo_output_onboarding(TAB_NAME)
def display_progress_header(result: ProgressResult, settings: ProgressSettings) -> None:
    """Draw the header shown on every tab of the Progress page.

    Parameters
    ----------
    result : ProgressResult
        The computed progress.
    settings : ProgressSettings
        The settings the progress was computed with.
    """
    counts = result.counts
    target_text = f"{counts.target:,}" if counts.target else "not set"
    st.caption(
        f"**Target:** fixed number, {target_text} · "
        f"**Completion condition:** {describe_condition(settings)}"
    )
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
            "time_period_progress_overtime",
            options=list(options_map),
            default="Day",
        ),
    )


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
        if result.target_path:
            fig.add_trace(
                go.Scatter(
                    x=[day for day, _ in result.target_path],
                    y=[value for _, value in result.target_path],
                    mode="lines",
                    name="Target",
                    line={"color": TARGET_COLOR, "width": 2, "dash": "dash"},
                )
            )
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
    """Draw the Overview tab's to-do cards and completions chart.

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
        st.warning(f"**{todo.count:,}** {todo.label}: see the {todo.tab} tab.")

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
# Attempted Interviews - Computation and Display
# =============================================================================


def _aggregate_attempts_by_survey_id(
    data: pl.DataFrame, survey_id: str, date: str
) -> pl.DataFrame:
    """Aggregate interview attempts by survey ID.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset
    survey_id : str
        Column name for survey ID
    date : str
        Column name for date

    Returns
    -------
    pl.DataFrame
        Aggregated attempts with num_interviews, last_attempt_date, and attempt_dates
    """
    return (
        data.group_by(survey_id)
        .agg(
            [
                pl.len().alias("num_interviews"),
                pl.col(date).max().alias("last_attempt_date"),
                pl.col(date).alias("attempt_dates"),
            ]
        )
        .sort(survey_id)
    )


def _expand_attempt_dates(attempts_df: pl.DataFrame) -> pl.DataFrame:
    """Expand attempt dates list into separate columns.

    Parameters
    ----------
    attempts_df : pl.DataFrame
        DataFrame with attempt_dates column containing lists

    Returns
    -------
    pl.DataFrame
        DataFrame with expanded attempt date columns
    """
    # Get the maximum number of attempts to determine how many columns we need
    # No survey IDs (zero-row data) means no attempt date columns.
    max_attempts = (
        attempts_df.select(pl.col("attempt_dates").list.len().max()).item() or 0
    )

    # Explode attempt dates into separate columns
    # Use list.get with default=None to handle lists shorter than max_attempts
    for i in range(max_attempts):
        attempts_df = attempts_df.with_columns(
            pl.col("attempt_dates")
            .list.get(i, null_on_oob=True)
            .alias(f"Attempt Date {i + 1}")
        )

    return attempts_df.drop("attempt_dates")


def _prepare_display_columns(
    data: pl.DataFrame, survey_id: str, date: str, display_cols: list[str]
) -> pl.DataFrame:
    """Prepare display columns with forward and backward fill.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset
    survey_id : str
        Column name for survey ID
    date : str
        Column name for date
    display_cols : list[str]
        List of columns to display

    Returns
    -------
    pl.DataFrame
        DataFrame with filled display columns, one row per survey ID
    """
    if not display_cols:
        return pl.DataFrame({survey_id: data[survey_id].unique()})

    # Sort and select relevant columns
    cols_to_select = [survey_id, date] + display_cols
    sorted_data = data.select(cols_to_select).sort([survey_id, date])

    # Forward fill and backward fill within each group
    filled_data = sorted_data.with_columns(
        [
            pl.col(col).forward_fill().backward_fill().over(survey_id)
            for col in display_cols
        ]
    )

    # Keep only one row per survey ID (the first one after sorting)
    return filled_data.unique(subset=[survey_id], keep="first")


def _compute_summary_stats(attempts_df: pl.DataFrame) -> tuple[int, int, int]:
    """Compute summary statistics for attempted interviews.

    Parameters
    ----------
    attempts_df : pl.DataFrame
        DataFrame with attempted interviews data

    Returns
    -------
    tuple
        (number_of_unique_ids, min_attempts, max_attempts)
    """
    num_unique = attempts_df.height
    if num_unique == 0:
        return 0, 0, 0
    min_attempts = attempts_df["num_interviews"].min()
    max_attempts = attempts_df["num_interviews"].max()

    return num_unique, min_attempts, max_attempts


@st.cache_data
def compute_attempted_interviews(
    data: pl.DataFrame, survey_id: str, date: str, display_cols: list[str]
) -> AttemptedInterviewsResult:
    """Compute attempted interviews statistics.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset
    survey_id : str
        Column name for survey ID
    date : str
        Column name for date
    display_cols : list[str]
        List of columns to display

    Returns
    -------
    AttemptedInterviewsResult
        Pydantic model containing attempted interviews data and summary statistics
    """
    total_submitted = data.height

    # Step 1: Aggregate attempts by survey ID
    attempted_interviews = _aggregate_attempts_by_survey_id(data, survey_id, date)

    # Step 2: Expand attempt dates into separate columns
    attempted_interviews = _expand_attempt_dates(attempted_interviews)

    # Step 3: Prepare display columns if any
    if display_cols:
        display_data = _prepare_display_columns(data, survey_id, date, display_cols)

        # Merge display columns with attempted interviews
        attempted_interviews = attempted_interviews.join(
            display_data.drop([date]), on=survey_id, how="left"
        )

        # Reorder columns: survey_id, num_interviews, last_attempt_date,
        # display_cols, attempt dates
        attempt_date_cols = [
            col
            for col in attempted_interviews.columns
            if col.startswith("Attempt Date")
        ]
        ordered_cols = (
            [survey_id, "num_interviews", "last_attempt_date"]
            + display_cols
            + attempt_date_cols
        )
        attempted_interviews = attempted_interviews.select(ordered_cols)

    # Step 4: Calculate summary statistics
    num_unique, min_attempts, max_attempts = _compute_summary_stats(
        attempted_interviews
    )

    return AttemptedInterviewsResult(
        attempted_interviews=attempted_interviews,
        total_submitted=total_submitted,
        number_of_unique_ids=num_unique,
        min_attempts=min_attempts,
        max_attempts=max_attempts,
    )


@demo_output_onboarding(TAB_NAME)
@st.fragment
def display_attempted_interviews(
    data: pl.DataFrame, survey_id: str | None, date: str | None, setting_file: str
) -> None:
    """Display attempted interviews report.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset
    survey_id : str | None
        Column name for survey ID
    date : str | None
        Column name for date
    setting_file : str
        Path to settings file
    """
    if not (all([survey_id, date])):
        st.info(
            "Attempted interviews report requires survey ID and date columns to be selected. "
            "To add these columns, go to the :material/settings: settings section above."
        )
        return

    with st.expander(":material/clarify: Show more columns in report", expanded=False):
        st.info(
            "Select additional columns to include in the table displaying attempted interviews. "
        )
        display_cols = st.multiselect(
            label="Additional columns",
            label_visibility="collapsed",
            options=data.columns,
            help="Columns to display in the attempted interviews report",
            **check_view(setting_file).bind(
                "attempted_interviews_display_cols",
                options=data.columns,
                multi=True,
                default=None,
            ),
        )

    # Compute attempted interviews using Polars
    result = compute_attempted_interviews(
        data=data,
        survey_id=survey_id,
        date=date,
        display_cols=display_cols,
    )

    # Display metrics
    _display_metrics(result)

    # Display chart and table
    _display_chart_and_table(result.attempted_interviews, survey_id)

    demo_callout(
        "**Next**: :material/arrow_upward: Scroll up and select **Data integrity → Missing Values**."
    )


def _display_metrics(result: AttemptedInterviewsResult) -> None:
    """Display summary metrics for attempted interviews.

    Parameters
    ----------
    result : AttemptedInterviewsResult
        Result containing attempted interviews data and statistics
    """
    cm1, cm2, cm3, cm4 = st.columns(4, border=True)
    total_submissions_formatted = f"{result.total_submitted:,}"
    cm1.metric(label="Total Submitted Interviews", value=total_submissions_formatted)
    number_of_unique_ids_formatted = f"{result.number_of_unique_ids:,}"
    cm2.metric(label="Number of Unique IDs", value=number_of_unique_ids_formatted)
    min_attempts_formatted = f"{result.min_attempts:,}"
    cm3.metric(label="Min Attempts", value=min_attempts_formatted)
    max_attempts_formatted = f"{result.max_attempts:,}"
    cm4.metric(label="Max Attempts", value=max_attempts_formatted)


def _display_chart_and_table(
    attempted_interviews: pl.DataFrame, survey_id: str
) -> None:
    """Display frequency chart and detailed table.

    Parameters
    ----------
    attempted_interviews : pl.DataFrame
        DataFrame with attempted interviews data
    survey_id : str
        Column name for survey ID
    """
    ai1, ai2 = st.columns([0.4, 0.6])

    with ai1:
        # Aggregate attempted interviews into frequency counts
        attempted_frequency = (
            attempted_interviews.group_by("num_interviews")
            .agg(pl.len().alias("frequency"))
            .sort("num_interviews")
        )

        # Calculate total and percentage
        total_surveys = attempted_frequency["frequency"].sum()
        attempted_frequency = attempted_frequency.with_columns(
            (pl.col("frequency") / total_surveys * 100).alias("percentage")
        )

        # Convert to list for plotting
        num_interviews_list = attempted_frequency["num_interviews"].to_list()
        percentage_list = attempted_frequency["percentage"].to_list()
        frequency_list = attempted_frequency["frequency"].to_list()

        # Convert attempts to strings for categorical axis
        num_interviews_str = [str(int(x)) for x in num_interviews_list]

        # Create custom hover text
        hover_text = [
            f"<b>{attempts} Attempts</b><br>Percentage: {pct:.1f}%<br>Frequency: {freq}"
            for attempts, pct, freq in zip(
                num_interviews_list, percentage_list, frequency_list, strict=False
            )
        ]

        # Create figure using go.Bar for better control
        fig = go.Figure()

        fig.add_trace(
            go.Bar(
                x=percentage_list,
                y=num_interviews_str,
                orientation="h",
                marker_color="#f87171",
                hovertemplate="%{customdata}<extra></extra>",
                customdata=hover_text,
            )
        )

        fig.update_layout(
            title="Attempted Interviews Distribution",
            title_x=0.5,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=400,
            margin={"t": 50, "b": 50, "l": 50, "r": 50},
            hovermode="closest",
            xaxis={
                "title": "Percentage (%)",
                "showgrid": False,
                "gridcolor": "lightgrey",
            },
            yaxis={
                "title": "Number of Attempts",
                "type": "category",
                "showgrid": False,
                "gridcolor": "lightgrey",
                "autorange": "reversed",
            },
        )
        st.plotly_chart(fig, width="stretch")

    with ai2:
        # Convert to pandas for styling (Streamlit doesn't support Polars styling yet)
        attempts_pd = attempted_interviews.to_pandas()
        # Make sure the Styler limit fits this DataFrame
        ensure_styler_limit(attempts_pd.size + 1)

        cmap = sns.light_palette("pink", as_cmap=True)
        vmin = attempts_pd["num_interviews"].min()
        vmax = attempts_pd["num_interviews"].max()

        st.dataframe(
            data=attempts_pd.style.background_gradient(
                subset=["num_interviews"],
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
            ),
            width="stretch",
            column_config={
                survey_id: st.column_config.Column(pinned=True),
                "num_interviews": st.column_config.Column(
                    pinned=True, label="Number of Interviews"
                ),
                "last_attempt_date": st.column_config.DateColumn(
                    pinned=True, label="Last Attempt Date"
                ),
            },
            hide_index=True,
        )


# =============================================================================
# Main Report Function
# =============================================================================


@demo_output_onboarding(TAB_NAME)
def progress_report(
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
    survey_columns: ColumnByType,
) -> None:
    """Display the Progress page: settings, then a header above Overview and Follow-up.

    The settings expander sits at the top, as on Summary, with "Reset
    filters" beside it. `compute_progress` then counts the progress once and
    the header (shown on every tab) and the tabs draw from its result.

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
    """
    st.title("Progress Tracking")
    saved_view = check_view(setting_file)
    with reset_filters_beside(saved_view):
        settings = progress_report_settings(
            data,
            setting_file,
            ProgressSettings(**config),
            survey_columns.categorical_columns,
            survey_columns.datetime_columns,
        )

    header = st.container()
    # Only the fixed target for now, so the tabs are always the same
    tab_names = TABS_BY_MODE["fixed"]
    overview, follow_up = st.tabs(
        tab_names,
        **saved_view.bind("progress_tab", options=tab_names, default=tab_names[0]),
    )

    with overview:
        chart_view, period = render_chart_controls(setting_file)

    result = compute_progress(data, settings, date.today(), period)

    with header:
        display_progress_header(result, settings)
    with overview:
        display_overview(result, settings, chart_view)
    with follow_up:
        display_attempted_interviews(
            data, settings.survey_id, settings.survey_date, setting_file
        )


def progress_headline(
    data: pl.DataFrame, setting_file: str, config: dict
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
    """
    try:
        settings = load_default_settings(setting_file, ProgressSettings(**config))
        counts = compute_counts(data, settings)
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
