"""Pydantic models and constants for the enumerator performance module."""

from pydantic import BaseModel, Field, field_validator, model_validator

TAB_NAME: str = "enumerators"


# =============================================================================
# Pydantic Models for Data Validation
# =============================================================================


class EnumeratorSettings(BaseModel):
    """Settings for enumerator report configuration.

    Attributes
    ----------
    date : str | None
        Column name containing survey submission date.
    survey_id : str | None
        Column name containing survey ID.
    enumerator : str | None
        Column name containing enumerator identifier (required).
    formdef_version : str | None
        Column name containing form version.
    duration : str | None
        Column name containing survey duration in seconds.
    team : str | None
        Column name containing team identifier.
    consent : str | None
        Column name containing consent status.
    consent_vals : list[str] | None
        List of values indicating valid consent.
    outcome : str | None
        Column name containing survey outcome status.
    outcome_vals : list[str] | None
        List of values indicating completed surveys.
    """

    survey_key: str | None = Field(None, description="Survey key column")
    survey_id: str | None = Field(..., min_length=1, description="Survey ID column")
    survey_date: str | None = Field(None, description="Survey date column")
    enumerator: str | None = Field(None, description="Enumerator ID column")
    formversion: str | None = Field(None, description="Form version column")
    duration: str | None = Field(None, description="Duration column")
    duration_unit: str = Field("default='seconds'", description="Duration unit")
    team: str | None = Field(None, description="Team identifier column")

    @model_validator(mode="after")
    def drop_team_same_as_enumerator(self) -> "EnumeratorSettings":
        """Ignore a team column that is the enumerator column.

        Grouping by the same column twice fails, and such a team adds nothing.
        """
        if self.team and self.team == self.enumerator:
            self.team = None
        return self


class ConsentOutcomeSettings(BaseModel):
    """Settings for consent and outcome configuration.

    Attributes
    ----------
    consent : str | None
        Column name containing consent status.
    consent_vals : list[str] | None
        List of values indicating valid consent.
    outcome : str | None
        Column name containing survey outcome status.
    outcome_vals : list[str] | None
        List of values indicating completed surveys.
    """

    consent: str | None = Field(None, description="Consent status column")
    consent_vals: list[str] | None = Field(None, description="Valid consent values")
    outcome: str | None = Field(None, description="Outcome status column")
    outcome_vals: list[str] | None = Field(None, description="Completed survey values")


class ProductivitySettings(BaseModel):
    """Settings for productivity analysis configuration.

    Attributes
    ----------
    view_option : str
        Time period for analysis: Daily, Weekly, or Monthly.
    weekstartday : str
        First day of the week for weekly analysis.
    """

    view_option: str = Field(default="Daily", description="Time period view")
    weekstartday: str = Field(default="Monday", description="Week start day")

    @field_validator("view_option")
    @classmethod
    def validate_view_option(cls, v: str) -> str:
        """Validate view option is one of the allowed values."""
        allowed = ["Daily", "Weekly", "Monthly"]
        if v not in allowed:
            raise ValueError(f"view_option must be one of {allowed}")
        return v

    @field_validator("weekstartday")
    @classmethod
    def validate_weekstartday(cls, v: str) -> str:
        """Validate weekstartday is one of the allowed values."""
        allowed = [
            "Monday",
            "Tuesday",
            "Wednesday",
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
        ]
        if v not in allowed:
            raise ValueError(f"weekstartday must be one of {allowed}")
        return v


# Constants for statistics options
ALLOWED_STATISTICS = [
    "count",
    "min",
    "mean",
    "median",
    "max",
    "std",
    "25th percentile",
    "75th percentile",
]
ALLOWED_STATISTICS_OVERTIME = ALLOWED_STATISTICS + ["missing"]
ALLOWED_TIME_PERIODS = ["Daily", "Weekly", "Monthly"]
WEEKDAY_NAMES = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

# Maps weekday names to offset codes used in computation
WEEKDAY_OFFSET_MAP = {
    "Monday": "SUN",
    "Tuesday": "MON",
    "Wednesday": "TUE",
    "Thursday": "WED",
    "Friday": "THU",
    "Saturday": "FRI",
    "Sunday": "SAT",
}

# Maps offset codes to numeric values for week calculations
WEEKDAY_OFFSET_TO_NUMERIC = {
    "SUN": 0,
    "MON": 1,
    "TUE": 2,
    "WED": 3,
    "THU": 4,
    "FRI": 5,
    "SAT": 6,
}


class StatisticsSettings(BaseModel):
    """Settings for statistics analysis configuration.

    Attributes
    ----------
    statscols : list[str] | None
        Columns to compute statistics on.
    stats : list[str]
        Statistics to compute (count, mean, median, etc.).
    """

    statscols: list[str] | None = Field(None, description="Columns for statistics")
    stats: list[str] = Field(
        default=["count", "mean"], description="Statistics to compute"
    )

    @field_validator("stats")
    @classmethod
    def validate_stats(cls, v: list[str]) -> list[str]:
        """Validate that statistics are from allowed list."""
        for stat in v:
            if stat not in ALLOWED_STATISTICS:
                raise ValueError(
                    f"Invalid statistic: {stat}. Must be one of {ALLOWED_STATISTICS}"
                )
        return v


class StatisticsOvertimeSettings(BaseModel):
    """Settings for statistics over time analysis configuration.

    Attributes
    ----------
    period : str
        Time period for analysis (Daily, Weekly, Monthly).
    weekstartday : str
        First day of the week for weekly analysis.
    stat : str
        Statistic to compute over time.
    statscol : str | None
        Column to compute statistics on.
    """

    period_overtime: str = Field(default="Week", description="Time period for analysis")
    weekstartday: str = Field(default="Monday", description="Week start day")
    stat: str = Field(default="count", description="Statistic to compute")
    statscol: str | None = Field(None, description="Column for statistics")

    @field_validator("period_overtime")
    @classmethod
    def validate_period(cls, v: str) -> str:
        """Validate period is from allowed list."""
        if v not in ALLOWED_TIME_PERIODS:
            raise ValueError(
                f"Invalid period: {v}. Must be one of {ALLOWED_TIME_PERIODS}"
            )
        return v

    @field_validator("weekstartday")
    @classmethod
    def validate_weekstartday(cls, v: str) -> str:
        """Validate weekstartday is from allowed list."""
        if v not in WEEKDAY_NAMES:
            raise ValueError(
                f"Invalid weekstartday: {v}. Must be one of {WEEKDAY_NAMES}"
            )
        return v

    @field_validator("stat")
    @classmethod
    def validate_stat(cls, v: str) -> str:
        """Validate stat is from allowed list."""
        if v not in ALLOWED_STATISTICS_OVERTIME:
            raise ValueError(
                f"Invalid statistic: {v}. Must be one of {ALLOWED_STATISTICS_OVERTIME}"
            )
        return v


class ActiveEnumerators(BaseModel):
    """Enumerators active in the past 7 days, out of all.

    Attributes
    ----------
    active : int
        Enumerators with a submission dated in the 7 days up to today.
    total : int
        Enumerators in the data.
    """

    active: int = Field(ge=0)
    total: int = Field(ge=0)


class OverviewFigures(BaseModel):
    """The four figures at the top of the enumerator report.

    Attributes
    ----------
    num_enumerators : int
        Enumerators in the data.
    num_active : int
        Enumerators with a submission in the past 7 days, counted from today.
    num_teams : int | None
        Teams in the data; None without a team column.
    submissions_past_week : int
        Submissions dated in the past 7 days, counted from today.
    submissions_week_before : int
        Submissions dated in the 7 days before that.
    median_per_enumerator : float
        The median of each enumerator's total submissions.
    fewest, most : tuple[str, int]
        The enumerator with the fewest and the most submissions, and the
        count.
    duration_minutes : tuple[float, float, float] | None
        The interview length's lower quartile, median and upper quartile,
        in minutes; None without a duration column.
    """

    num_enumerators: int = Field(ge=0)
    num_active: int = Field(ge=0)
    num_teams: int | None = None
    submissions_past_week: int = Field(ge=0)
    submissions_week_before: int = Field(ge=0)
    median_per_enumerator: float = Field(ge=0)
    fewest: tuple[str, int]
    most: tuple[str, int]
    duration_minutes: tuple[float, float, float] | None = None
