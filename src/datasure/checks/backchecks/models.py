"""Pydantic models, enums, and constants for the backchecks module."""

from enum import StrEnum

from pydantic import BaseModel, Field

TAB_NAME: str = "backchecks"

# Weekday constants for productivity analysis
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


# ==============================================================================
# PYDANTIC MODELS AND ENUMS
# ==============================================================================


class SearchType(StrEnum):
    """Column search pattern types."""

    EXACT = "exact"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"
    CONTAINS = "contains"
    REGEX = "regex"


class BackcheckSettings(BaseModel):
    """Backcheck report settings model."""

    survey_key: str | None = Field(..., description="Column containing survey key")
    survey_id: str | None = Field(None, description="Column containing survey ID")
    survey_date: str | None = Field(None, description="Column containing survey date")
    backcheck_date: str | None = Field(
        None, description="Column containing backcheck date"
    )
    enumerator: str | None = Field(None, description="Column containing enumerator")
    backchecker: str | None = Field(None, description="Column containing back checker")
    backcheck_target_percent: int = Field(
        10, description="Target percentage of backchecks"
    )
    drop_duplicates_option: str = Field(
        "drop", description="How to handle duplicate entries"
    )
    no_differences_list: list[str] | None = Field(
        None,
        description="List of values that will not be marked as differences",
    )
    exclude_values_list: list[str] | None = Field(
        None,
        description="List of values to be excluded from backcheck comparisons",
    )
    case_option: str | None = Field(
        None, description="Case sensitivity option for string comparison"
    )
    trimspaces_option: bool = Field(
        False, description="Trim spaces option for string comparison"
    )
    nosymbols_option: bool = Field(
        False, description="Ignore symbols option for string comparison"
    )


class StrCompareOptions(BaseModel):
    """String comparison settings for backchecks."""

    case_option: str | None = Field(None, description="Case sensitivity option")
    trimspaces_option: bool = Field(False, description="Trim spaces option")
    nosymbols_option: bool = Field(False, description="Ignore symbols option")


class OkRangeValues(BaseModel):
    """OK range values settings for backchecks."""

    ok_range_neg: float | None = Field(le=0, description="Negative OK range value")
    ok_range_pos: float | None = Field(ge=0, description="Positive OK range value")


class OkRangeOptions(BaseModel):
    """OK range settings for backchecks."""

    ok_range_type: str | None = Field(None, description="Type of OK range")
    ok_range_values: OkRangeValues | None = Field(
        None, description="Values for OK range"
    )


class OkRangeType(StrEnum):
    """OK range types for backchecks."""

    NUMBER = "number"
    PERCENTAGE = "percentage"


class BackcheckTestOptions(BaseModel):
    """Backcheck test settings for backchecks."""

    ttest: bool = Field(False, description="Perform t-test")
    prtest: bool = Field(False, description="Perform proportion test")
    signrank: bool = Field(False, description="Perform sign rank test")
    reliability: bool = Field(False, description="Calculate reliability metrics")
