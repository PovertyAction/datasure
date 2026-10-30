"""Pydantic models for the enumerator report's Response Patterns section."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator

# Key under the enumerator report's settings that holds this section's settings
SETTINGS_KEY: str = "response_patterns"

VariableType = Literal["integer", "continuous", "categorical"]
VARIABLE_TYPES: list[str] = ["integer", "continuous", "categorical"]
NUMERIC_TYPES: tuple[str, ...] = ("integer", "continuous")

# Moderate badges start this many points below the flag threshold
MODERATE_MARGIN: int = 15

# Fixed flag-threshold levels, most sensitive first: score -> label. Levels
# are MODERATE_MARGIN apart, so a Moderate badge means the enumerator would be
# flagged one level more sensitive.
THRESHOLD_LEVELS: dict[int, str] = {
    20: "Very high",
    35: "High",
    50: "Medium",
    65: "Low",
    80: "Very low",
}
DEFAULT_THRESHOLD: int = 50


def nearest_threshold_level(threshold: int) -> int:
    """Return the fixed threshold level closest to ``threshold``."""
    return min(THRESHOLD_LEVELS, key=lambda level: (abs(level - threshold), level))


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
        Digit Preference score at or above which an enumerator is flagged,
        one of ``THRESHOLD_LEVELS``.
    range_compression_threshold : int
        Range Compression score at or above which an enumerator is flagged,
        one of ``THRESHOLD_LEVELS``.
    """

    selected_variables: list[str] = Field(default_factory=list)
    type_overrides: dict[str, VariableType] = Field(default_factory=dict)
    min_sample: int = Field(15, ge=1)
    warn_sample: int = Field(30, ge=1)
    digit_preference_threshold: int = Field(DEFAULT_THRESHOLD, ge=0, le=100)
    range_compression_threshold: int = Field(DEFAULT_THRESHOLD, ge=0, le=100)

    @field_validator("digit_preference_threshold", "range_compression_threshold")
    @classmethod
    def snap_to_level(cls, v: int) -> int:
        """Move a threshold saved off the fixed levels to the nearest level."""
        return nearest_threshold_level(v)


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
    TEAM_NO_VARIATION = "no variation in the rest of the team's responses"


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


class RangeSignal(StrEnum):
    """Which Range Compression signal set a score."""

    COMPRESSION = "compression"
    SHIFT = "shift"


class RangeVariable(BaseModel):
    """One enumerator's Range Compression result on one variable.

    ``team`` always means the rest of the team. The histogram shares
    ``bucket_edges`` between the two series; values beyond the team's 1st
    and 99th percentiles count in the end buckets. Bucket shares are
    percentages.
    """

    variable: str
    n_responses: int
    sample_band: SampleBand
    score: float
    signal: RangeSignal
    compression_score: float
    shift_score: float
    enum_mean: float
    team_mean: float
    enum_sd: float
    team_sd: float
    sd_ratio: float
    bucket_edges: list[float]
    enum_bucket_pct: list[float]
    team_bucket_pct: list[float]


class RangeCompressionEnumerator(BaseModel):
    """One enumerator's Range Compression result.

    The score, signal and sample band are those of ``variables[0]``, the
    highest-scoring variable. ``compression_variables`` and
    ``shift_variables`` name the variables whose score for that signal
    reaches the flag threshold.
    """

    enumerator: str
    interviews: int
    sample_band: SampleBand
    score: float | None
    badge: Badge
    signal: RangeSignal | None = None
    variables: list[RangeVariable] = Field(default_factory=list)
    compression_variables: list[str] = Field(default_factory=list)
    shift_variables: list[str] = Field(default_factory=list)
    skipped_variables: dict[str, SkipReason] = Field(default_factory=dict)


class RangeCompressionResult(BaseModel):
    """Range Compression results, enumerators sorted highest score first."""

    threshold: int
    condition: CheckCondition | None = None
    variables: list[str] = Field(default_factory=list)
    skipped_variables: dict[str, SkipReason] = Field(default_factory=dict)
    enumerators: list[RangeCompressionEnumerator] = Field(default_factory=list)


class ResponsePatternResults(BaseModel):
    """Everything the Response Patterns section shows."""

    condition: PageCondition | None = None
    min_sample: int
    warn_sample: int
    digit_preference: DigitPreferenceResult | None = None
    range_compression: RangeCompressionResult | None = None
