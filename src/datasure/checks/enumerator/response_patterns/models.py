"""Pydantic models for the enumerator report's Response Patterns section."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# Key under the enumerator report's settings that holds this section's settings
SETTINGS_KEY: str = "response_patterns"

VariableType = Literal["integer", "continuous", "categorical"]
VARIABLE_TYPES: list[str] = ["integer", "continuous", "categorical"]
NUMERIC_TYPES: tuple[str, ...] = ("integer", "continuous")

# Moderate badges start this many points below the flag threshold
MODERATE_MARGIN: int = 15


class ResponsePatternSettings(BaseModel):
    """Settings for the Response Patterns section, saved per project.

    Attributes
    ----------
    selected_variables : list[str]
        Variables the checks run on. None are selected by default.
    type_overrides : dict[str, VariableType]
        Types the user set in place of the inferred ones.
    min_sample : int
        Enumerators with fewer responses than this get no result.
    warn_sample : int
        Results with fewer responses than this carry a low-sample warning.
    digit_preference_threshold : int
        Digit Preference score at or above which an enumerator is flagged.
    """

    selected_variables: list[str] = Field(default_factory=list)
    type_overrides: dict[str, VariableType] = Field(default_factory=dict)
    min_sample: int = Field(15, ge=1)
    warn_sample: int = Field(30, ge=1)
    digit_preference_threshold: int = Field(50, ge=0, le=100)


class SampleBand(StrEnum):
    """How many responses a result rests on, against the sample thresholds."""

    INSUFFICIENT = "insufficient"
    LOW = "low"
    OK = "ok"


class Badge(StrEnum):
    """Severity of an enumerator's score against the flag threshold."""

    NA = "N/A"
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"


class SkipReason(StrEnum):
    """Why a variable was left out of a check."""

    NOT_NUMERIC = "not a numeric column"
    NO_RESPONSES = "no responses"
    NO_VARIATION = "no variation across the project"
    RANGE_UNDER_10 = "observed range under 10"
    BELOW_MINIMUM = "fewer responses than the minimum"


class PageCondition(StrEnum):
    """Conditions that stop every check in the section from running."""

    NO_VARIABLES_SELECTED = "no_variables_selected"
    SINGLE_ENUMERATOR = "single_enumerator"


class CheckCondition(StrEnum):
    """Conditions that stop one check from listing enumerators."""

    NO_APPLICABLE_VARIABLES = "no_applicable_variables"
    NO_ELIGIBLE_VARIABLES = "no_eligible_variables"
    ALL_BELOW_MINIMUM = "all_below_minimum"


class DigitPreferenceEnumerator(BaseModel):
    """One enumerator's Digit Preference result.

    Shares are percentages. ``team`` always means the rest of the team: every
    enumerator except this one.
    """

    enumerator: str
    interviews: int
    n_responses: int
    sample_band: SampleBand
    score: float | None
    badge: Badge
    enum_pct: float | None = None
    team_pct: float | None = None
    enum_digit_pct: list[float] = Field(default_factory=list)
    team_digit_pct: list[float] = Field(default_factory=list)
    skipped_variables: dict[str, SkipReason] = Field(default_factory=dict)


class DigitPreferenceResult(BaseModel):
    """Digit Preference results, enumerators sorted highest score first."""

    threshold: int
    condition: CheckCondition | None = None
    variables: list[str] = Field(default_factory=list)
    skipped_variables: dict[str, SkipReason] = Field(default_factory=dict)
    enumerators: list[DigitPreferenceEnumerator] = Field(default_factory=list)


class ResponsePatternResults(BaseModel):
    """Everything the Response Patterns section shows."""

    condition: PageCondition | None = None
    min_sample: int
    warn_sample: int
    digit_preference: DigitPreferenceResult | None = None
