"""Pydantic models, enums, and constants for the outliers module."""

from enum import Enum, IntEnum, StrEnum

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
)

TAB_NAME: str = "outliers"


# =============================================================================
# Enums and Constants
# =============================================================================


class OutlierMethod(StrEnum):
    """Supported outlier detection methods."""

    IQR = "Interquartile Range (IQR)"
    SD = "Standard Deviation (SD)"


class SearchType(StrEnum):
    """Column search pattern types."""

    EXACT = "exact"
    STARTSWITH = "startswith"
    ENDSWITH = "endswith"
    CONTAINS = "contains"
    REGEX = "regex"


class OutlierThresholds(IntEnum):
    """Integer thresholds"""

    IQR = 20
    SD = 30


class OutlierMultipliers(float, Enum):
    """Float multipliers"""

    IQR = 1.5
    SD = 3.0


# =============================================================================
# Pydantic Models for Data Validation
# =============================================================================


class OutlierBounds(BaseModel):
    """Statistical bounds for outlier detection."""

    lower_bound: float
    upper_bound: float


class OutlierOptionsConfig(BaseModel):
    """Configuration for outlier options."""

    outlier_method: OutlierMethod = Field(
        ..., description="Outlier detection method to use."
    )
    outlier_multiplier: float = Field(
        ...,
        gt=0,
        le=10.0,
        description="Multiplier for outlier detection method.",
    )
    outlier_threshold: int = Field(
        ...,
        gt=0,
        description="Minimum number of non-null values required to flag outliers.",
    )


class ConstraintBounds(BaseModel):
    """User-defined constraint bounds for outlier detection.

    Bounds hierarchy: hard_min <= soft_min <= soft_max <= hard_max
    Values can be positive, negative, or zero. Infinity values are not allowed.
    """

    hard_min: int | float | None = Field(None, description="Absolute Minimum bound")
    soft_min: int | float | None = Field(None, description="Expected Minimum bound")
    soft_max: int | float | None = Field(None, description="Expected Maximum bound")
    hard_max: int | float | None = Field(None, description="Absolute Maximum bound")

    @model_validator(mode="after")
    def validate_bounds_hierarchy(self):
        """Validate the complete hierarchy of bounds."""
        bounds = [
            ("hard_min", self.hard_min),
            ("soft_min", self.soft_min),
            ("soft_max", self.soft_max),
            ("hard_max", self.hard_max),
        ]

        # Get only non-None values with their names
        defined_bounds = [(name, val) for name, val in bounds if val is not None]

        # Check that all defined bounds are in ascending order
        for i in range(len(defined_bounds) - 1):
            curr_name, curr_val = defined_bounds[i]
            next_name, next_val = defined_bounds[i + 1]
            if curr_val > next_val:
                raise ValueError(
                    f"{curr_name} ({curr_val}) must be <= {next_name} ({next_val}). "
                    f"Bounds must follow hierarchy: hard_min <= soft_min <= soft_max <= hard_max"
                )

        return self


class ConstraintMetrics(BaseModel):
    """Computed metrics for constraint violations."""

    columns_checked: int = Field(ge=0, description="Number of columns checked")
    total_violations: int = Field(
        ge=0, description="Total number of constraint violations"
    )
    hard_min_violations: int = Field(ge=0, description="Count of values below hard_min")
    soft_min_violations: int = Field(ge=0, description="Count of values below soft_min")
    soft_max_violations: int = Field(ge=0, description="Count of values above soft_max")
    hard_max_violations: int = Field(ge=0, description="Count of values above hard_max")


class OutlierMetrics(BaseModel):
    """Computed Metrics for Outlier Checks"""

    columns_checked: int = Field(ge=0, description="Number of columns checked")
    columns_with_outliers: int = Field(
        ge=0, description="Total number of columns with outlier values"
    )
    total_outliers: int = Field(ge=0, description="Total number of outliers flagged")
    enumerators_with_outliers: int = Field(
        ge=0, description="Total number of outliers flagged"
    )


class OutlierStatistics(BaseModel):
    """Complete statistical summary for outlier detection."""

    count: int = Field(ge=0, description="Number of non-null values")
    min_value: float
    max_value: float
    mean: float
    median: float
    sd: float | None
    iqr: float | None
    lower_bound: float | None
    upper_bound: float | None

    class Config:
        """Pydantic config."""

        populate_by_name = True


class OutlierColumnConfig(BaseModel):
    """Configuration for a single outlier column check."""

    search_type: SearchType
    pattern: str | None = None
    outlier_cols: list[str] = Field(min_length=1)
    lock_cols: bool = False
    grouped_cols: bool = False
    outlier_method: OutlierMethod = OutlierMethod.IQR
    outlier_multiplier: float = Field(gt=0, le=10.0)
    soft_min: float | None = None
    soft_max: float | None = None

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str | None, info) -> str | None:
        """Validate pattern is required for non-exact search types."""
        if info.data.get("search_type") != SearchType.EXACT and not v:
            raise ValueError("Pattern is required for non-exact search types")
        return v

    @field_validator("soft_max")
    @classmethod
    def validate_soft_bounds(cls, v: float | None, info) -> float | None:
        """Validate soft_max is greater than soft_min."""
        soft_min = info.data.get("soft_min")
        if v is not None and soft_min is not None and v <= soft_min:
            raise ValueError("soft_max must be greater than soft_min")
        return v


class OutlierSettings(BaseModel):
    """Main configuration for outlier report."""

    survey_key: str = Field(..., description="Column name for survey key", min_length=1)
    survey_id: str | None = Field(
        None, description="Column name for survey ID", min_length=1
    )
    survey_date: str | None = Field(
        None, description="Column name for survey date", min_length=1
    )
    enumerator: str | None = Field(
        None, description="Column name for enumerator ID", min_length=1
    )
    team: str | None = Field(None, description="Column name for team", min_length=1)
