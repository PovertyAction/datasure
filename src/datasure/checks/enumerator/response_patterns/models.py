"""Pydantic models for the enumerator report's Response Patterns section."""

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field

# Key under the enumerator report's settings that holds this section's settings
SETTINGS_KEY: str = "response_patterns"

VariableType = Literal["integer", "continuous", "categorical"]
VARIABLE_TYPES: list[str] = ["integer", "continuous", "categorical"]
NUMERIC_TYPES: tuple[str, ...] = ("integer", "continuous")


class Sensitivity(StrEnum):
    """How readily a check flags an enumerator."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SensitivityLevel(BaseModel):
    """What a sensitivity level flags, and the evidence it needs.

    Attributes
    ----------
    label : str
        The level's name in the UI.
    ratio : float
        An enumerator is flagged when their share of answers ending in 0 or 5
        is at least this many times the rest of the team's.
    min_responses : int
        Fewest pooled responses an enumerator needs at this level, on top of
        the project's minimum. Smaller differences need more responses to tell
        apart from chance.
    """

    label: str
    ratio: float
    min_responses: int = 0


# Most sensitive first. A Moderate badge means the enumerator would be flagged
# one level more sensitive.
DIGIT_PREFERENCE_LEVELS: dict[Sensitivity, SensitivityLevel] = {
    Sensitivity.HIGH: SensitivityLevel(label="High", ratio=1.25, min_responses=100),
    Sensitivity.MEDIUM: SensitivityLevel(label="Medium", ratio=1.5),
    Sensitivity.LOW: SensitivityLevel(label="Low", ratio=2.0),
}
DEFAULT_SENSITIVITY: Sensitivity = Sensitivity.MEDIUM


class RangeCompressionLevel(BaseModel):
    """What a Range Compression sensitivity level flags.

    Attributes
    ----------
    label : str
        The level's name in the UI.
    max_sd_ratio : float
        An enumerator is flagged when, on any checked variable, their
        standard deviation is at most this many times the rest of the team's.
    """

    label: str
    max_sd_ratio: float


# Most sensitive first. A Moderate badge means the enumerator would be flagged
# one level more sensitive.
RANGE_COMPRESSION_LEVELS: dict[Sensitivity, RangeCompressionLevel] = {
    Sensitivity.HIGH: RangeCompressionLevel(label="High", max_sd_ratio=0.65),
    Sensitivity.MEDIUM: RangeCompressionLevel(label="Medium", max_sd_ratio=0.5),
    Sensitivity.LOW: RangeCompressionLevel(label="Low", max_sd_ratio=0.35),
}


class CategoricalLevel(BaseModel):
    """What a Categorical Response Patterns sensitivity level flags.

    Attributes
    ----------
    label : str
        The level's name in the UI.
    min_gap : float
        An enumerator is flagged when, on any checked question, their share
        of one answer option differs from the rest of the team's by at least
        this many percentage points.
    """

    label: str
    min_gap: float


# Most sensitive first. A Moderate badge means the enumerator would be flagged
# one level more sensitive.
CATEGORICAL_LEVELS: dict[Sensitivity, CategoricalLevel] = {
    Sensitivity.HIGH: CategoricalLevel(label="High", min_gap=15),
    Sensitivity.MEDIUM: CategoricalLevel(label="Medium", min_gap=25),
    Sensitivity.LOW: CategoricalLevel(label="Low", min_gap=35),
}


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
    digit_preference_sensitivity : Sensitivity
        How readily Digit Preference flags an enumerator, one of
        ``DIGIT_PREFERENCE_LEVELS``.
    range_compression_sensitivity : Sensitivity
        How readily Range Compression flags an enumerator, one of
        ``RANGE_COMPRESSION_LEVELS``.
    categorical_sensitivity : Sensitivity
        How readily Categorical Response Patterns flags an enumerator, one of
        ``CATEGORICAL_LEVELS``.
    """

    selected_variables: list[str] = Field(default_factory=list)
    type_overrides: dict[str, VariableType] = Field(default_factory=dict)
    min_sample: int = Field(15, ge=1)
    warn_sample: int = Field(30, ge=1)
    digit_preference_sensitivity: Sensitivity = DEFAULT_SENSITIVITY
    range_compression_sensitivity: Sensitivity = DEFAULT_SENSITIVITY
    categorical_sensitivity: Sensitivity = DEFAULT_SENSITIVITY


class SampleBand(StrEnum):
    """How many responses a result rests on, against the sample thresholds."""

    INSUFFICIENT = "insufficient"
    LOW = "low"
    OK = "ok"


class Badge(StrEnum):
    """Severity of an enumerator's result against the sensitivity level."""

    NA = "N/A"
    LOW = "Low"
    MODERATE = "Moderate"
    HIGH = "High"


class SkipReason(StrEnum):
    """Why a variable was left out of a check."""

    NOT_NUMERIC = "no answers are numbers"
    NO_RESPONSES = "no responses"
    NO_VARIATION = "no variation across the project"
    RANGE_UNDER_10 = "observed range under 10"
    BELOW_MINIMUM = "fewer responses than the minimum"
    TEAM_NO_VARIATION = "no variation in the rest of the team's responses"
    TEAM_NO_RESPONSES = "no responses from the rest of the team"


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
    enumerator except this one. ``ratio`` is ``enum_pct / team_pct``: how many
    times as often the enumerator's answers end in 0 or 5. It is None when the
    enumerator has too few responses or the team has no 0 or 5 endings.
    """

    enumerator: str
    interviews: int
    n_responses: int
    sample_band: SampleBand
    ratio: float | None
    badge: Badge
    enum_pct: float | None = None
    team_pct: float | None = None
    enum_digit_pct: list[float] = Field(default_factory=list)
    team_digit_pct: list[float] = Field(default_factory=list)
    skipped_variables: dict[str, SkipReason] = Field(default_factory=dict)


class DigitPreferenceResult(BaseModel):
    """Digit Preference results, enumerators sorted highest ratio first.

    ``min_responses`` is the fewest pooled responses an enumerator needs at
    this sensitivity: the project minimum or the level's, whichever is higher.
    """

    sensitivity: Sensitivity
    min_responses: int
    condition: CheckCondition | None = None
    variables: list[str] = Field(default_factory=list)
    skipped_variables: dict[str, SkipReason] = Field(default_factory=dict)
    enumerators: list[DigitPreferenceEnumerator] = Field(default_factory=list)


class RangeVariable(BaseModel):
    """One enumerator's Range Compression result on one variable.

    ``team`` always means the rest of the team. Means and SDs are taken
    after capping each side's values at its own 5th and 95th percentiles,
    so one extreme answer can't dominate them. ``sd_ratio`` is
    ``enum_sd / team_sd``, rounded to two decimals as shown. The histogram
    uses the uncapped values and shares ``bucket_edges`` between the two
    series; values beyond the team's 1st and 99th percentiles count in the
    end buckets. Each bucket includes its lower edge and excludes its upper
    one. ``whole_numbers`` is True when every answer is a whole number; the
    edges are then whole numbers too. Bucket shares are percentages.
    """

    variable: str
    n_responses: int
    sample_band: SampleBand
    enum_mean: float
    team_mean: float
    enum_sd: float
    team_sd: float
    sd_ratio: float
    bucket_edges: list[float]
    whole_numbers: bool = False
    enum_bucket_pct: list[float]
    team_bucket_pct: list[float]


class RangeCompressionEnumerator(BaseModel):
    """One enumerator's Range Compression result.

    ``variables`` are sorted lowest SD ratio first. The SD ratio and sample
    band are those of ``variables[0]``, the most compressed variable, so one
    problem question is never averaged away. ``flagged_variables`` name the
    variables whose SD ratio is at or below the sensitivity level's.
    """

    enumerator: str
    interviews: int
    sample_band: SampleBand
    sd_ratio: float | None
    badge: Badge
    variables: list[RangeVariable] = Field(default_factory=list)
    flagged_variables: list[str] = Field(default_factory=list)
    skipped_variables: dict[str, SkipReason] = Field(default_factory=dict)


class RangeCompressionResult(BaseModel):
    """Range Compression results, enumerators sorted lowest SD ratio first."""

    sensitivity: Sensitivity
    condition: CheckCondition | None = None
    variables: list[str] = Field(default_factory=list)
    skipped_variables: dict[str, SkipReason] = Field(default_factory=dict)
    enumerators: list[RangeCompressionEnumerator] = Field(default_factory=list)


class CategoricalOption(BaseModel):
    """One answer option's share for the enumerator and the rest of the team.

    Shares are percentages; an option one side never chose is 0% there.
    ``gap`` is the enumerator's share minus the team's, in percentage
    points. ``flagged`` options have a gap of at least the sensitivity
    level's either way.
    """

    option: str
    enum_pct: float
    team_pct: float
    gap: float
    flagged: bool


class CategoricalQuestion(BaseModel):
    """One enumerator's Categorical Response Patterns result on one question.

    ``options`` are in the order of their values. ``largest_gap`` is the
    largest absolute gap on any option, in percentage points, and
    ``scoring_option`` the option it is on, which may be one the enumerator
    chose less often than the team. ``dominant_option`` is the option the
    enumerator chose most often relative to the team, if any. ``flagged``
    questions have a largest gap of at least the sensitivity level's.
    """

    variable: str
    n_responses: int
    sample_band: SampleBand
    largest_gap: float
    scoring_option: str
    flagged: bool
    dominant_option: str | None = None
    options: list[CategoricalOption]


class CategoricalEnumerator(BaseModel):
    """One enumerator's Categorical Response Patterns result.

    ``questions`` are sorted largest gap first. The largest gap and sample
    band are those of ``questions[0]``, so one problem question is never
    averaged away.
    """

    enumerator: str
    interviews: int
    sample_band: SampleBand
    largest_gap: float | None
    badge: Badge
    questions: list[CategoricalQuestion] = Field(default_factory=list)
    skipped_variables: dict[str, SkipReason] = Field(default_factory=dict)


class CategoricalResult(BaseModel):
    """Categorical Response Patterns results, largest gap first."""

    sensitivity: Sensitivity
    condition: CheckCondition | None = None
    variables: list[str] = Field(default_factory=list)
    skipped_variables: dict[str, SkipReason] = Field(default_factory=dict)
    enumerators: list[CategoricalEnumerator] = Field(default_factory=list)


class ResponsePatternResults(BaseModel):
    """Everything the Response Patterns section shows."""

    condition: PageCondition | None = None
    min_sample: int
    warn_sample: int
    digit_preference: DigitPreferenceResult | None = None
    range_compression: RangeCompressionResult | None = None
    categorical: CategoricalResult | None = None
