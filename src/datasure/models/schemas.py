"""Define Pydantic models for data validation and settings management in the Datasure
application.

These models ensure that user inputs and application settings adhere to expected formats
and constraints, facilitating
robust data processing and transformation operations.

"""

import datetime

import polars as pl
from pydantic import BaseModel, Field, field_validator

from datasure.models.enums import (
    DelimiterType,
    GPSFormatType,
    NumCondition,
    SearchType,
    StrCondition,
)


class DuplicatesColumnConfig(BaseModel):
    """Configuration for duplicate column checking.

    Attributes
    ----------
    search_type : SearchType
        Type of search pattern to use for matching columns.
    pattern : str | None
        Pattern string for column matching (required for non-exact searches).
    dup_cols : list[str]
        List of columns to check for duplicates.
    lock_cols : bool
        Whether to lock column selection to prevent dynamic updates.
    """

    search_type: SearchType
    pattern: str | None = None
    dup_cols: list[str] = Field(min_length=1)
    lock_cols: bool = False

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str | None, info) -> str | None:
        """Validate pattern is required for non-exact search types."""
        if info.data.get("search_type") != SearchType.EXACT and not v:
            raise ValueError("Pattern is required for non-exact search types")
        return v


class DuplicatesStats(BaseModel):
    """Statistics for duplicate analysis.

    Attributes
    ----------
    number_of_columns_checked : int
        Total number of columns analyzed for duplicates.
    total_duplicates : int
        Total count of duplicate entries across all checked columns.
    number_of_cols_with_duplicates : int
        Number of columns containing at least one duplicate.
    number_of_cols_without_duplicates : int
        Number of columns with no duplicates found.
    """

    number_of_columns_checked: int = Field(ge=0)
    total_duplicates: int = Field(ge=0)
    number_of_cols_with_duplicates: int = Field(ge=0)
    number_of_cols_without_duplicates: int = Field(ge=0)


class FilterCondition(BaseModel):
    """Validation model for data filtering conditions.

    Attributes
    ----------
    condition_col : str
        Column name to apply the condition filter on.
    condition_type : str
        Type of condition (from NumCondition or StrCondition enums).
    condition_value : int | float | str | list | tuple | datetime.date | None
        Value(s) to compare against in the condition.
    missing_as_duplicates : bool
        Whether to treat missing/null values as duplicates.
    """

    condition_col: str = Field(
        ..., min_length=1, description="Column to apply condition on"
    )
    condition_type: str = Field(..., description="Type of condition to apply")
    condition_value: int | float | str | list | tuple | datetime.date | None = Field(
        ..., description="Value(s) to compare against"
    )
    missing_as_duplicates: bool = Field(
        default=False, description="Whether to treat missing values as duplicates"
    )

    @field_validator("condition_value")
    @classmethod
    def validate_condition_value(cls, v, info):
        """Validate condition value matches the condition type requirements."""
        condition_type = info.data.get("condition_type")

        if condition_type in [NumCondition.IN_RANGE.value] and (
            not isinstance(v, list | tuple) or len(v) != 2
        ):
            raise ValueError(
                f"Condition type '{condition_type}' requires a tuple/list of 2 values"
            )

        if condition_type in [
            NumCondition.INCLUDES.value,
            StrCondition.INCLUDES.value,
        ] and not isinstance(v, list | tuple | set):
            raise ValueError(
                f"Condition type '{condition_type}' requires a list/tuple/set of values"
            )

        return v


class DuplicatesSettings(BaseModel):
    """Settings for duplicates report configuration.

    Attributes
    ----------
    filtered_data : pl.DataFrame | None
        Filtered dataset after applying conditions.
    survey_key : str | None
        Column name for survey key identifier.
    survey_id : str | None
        Column name for survey ID (required).
    survey_date : str | None
        Column name for survey date.
    enumerator : str | None
        Column name for enumerator ID.
    conditions : dict
        Dictionary of filtering conditions for duplicate detection.
    """

    filtered_data: pl.DataFrame | None = None
    survey_key: str | None = Field(None, description="Survey key column")
    survey_id: str | None = Field(..., min_length=1, description="Survey ID column")
    survey_date: str | None = Field(None, description="Survey date column")
    enumerator: str | None = Field(None, description="Enumerator ID column")
    conditions: dict = Field(
        default_factory=dict, description="Conditions for duplicates checks"
    )

    model_config = {
        "arbitrary_types_allowed": True,
    }


class DateDefaults(BaseModel):
    """Default date range configuration for date filters.

    Attributes
    ----------
    start_date : datetime.date
        Absolute minimum date allowed (January 1, 1970).
    end_date : datetime.date
        Absolute maximum date allowed (December 31, 2100).
    default_start_date : datetime.date
        Default start date for date inputs (30 days ago).
    default_end_date : datetime.date
        Default end date for date inputs (today).
    """

    start_date: datetime.date = Field(
        default=datetime.date(1970, 1, 1),
        description="Default start date (January 1, 1970)",
    )
    end_date: datetime.date = Field(
        default=datetime.date(2100, 12, 31),
        description="Default end date (December 31, 2100)",
    )

    default_start_date: datetime.date = Field(
        default=datetime.date.today() - datetime.timedelta(days=30),
        description="Default start date for date input (30 days ago)",
    )
    default_end_date: datetime.date = Field(
        default=datetime.date.today() + datetime.timedelta(days=30),
        description="Default end date for date input (today)",
    )


class GPSSettings(BaseModel):
    """GPS check settings model."""

    survey_key: str | None = Field(..., description="Survey key column")
    survey_id: str | None = Field(None, min_length=1, description="Survey ID column")
    survey_date: str | None = Field(None, description="Survey date column")
    enumerator: str | None = Field(None, description="Enumerator ID column")
    team: str | None = Field(None, description="Team identifier column")
    mapbox_custom_key: str | None = Field(None, description="Custom Mapbox API key")


class GPSColumnConfig(BaseModel):
    """Configuration for GPS column setup."""

    alias: str = Field(..., min_length=1, description="Alias for GPS configuration")
    format_type: GPSFormatType = Field(..., description="GPS data format type")
    delimiter: DelimiterType | None = Field(
        None, description="Delimiter for single column GPS data"
    )
    gps_column: str | None = Field(
        None, description="Column containing delimited GPS data"
    )
    latitude_column: str | None = Field(None, description="Latitude column name")
    longitude_column: str | None = Field(None, description="Longitude column name")
    altitude_column: str | None = Field(None, description="Altitude column name")
    accuracy_column: str | None = Field(None, description="Accuracy column name")

    @field_validator("delimiter")
    @classmethod
    def validate_delimiter(cls, v: DelimiterType | None, info) -> DelimiterType | None:
        """Validate delimiter is required for single column format."""
        if info.data.get("format_type") == GPSFormatType.SINGLE_COLUMN and not v:
            raise ValueError("Delimiter is required for single column format")
        return v

    @field_validator("gps_column")
    @classmethod
    def validate_gps_column(cls, v: str | None, info) -> str | None:
        """Validate gps_column is required for single column format."""
        if info.data.get("format_type") == GPSFormatType.SINGLE_COLUMN and not v:
            raise ValueError("GPS column is required for single column format")
        return v

    @field_validator("latitude_column", "longitude_column")
    @classmethod
    def validate_lat_lon_columns(cls, v: str | None, info) -> str | None:
        """Validate latitude and longitude are required for separate columns format."""
        field_name = info.field_name
        format_type = info.data.get("format_type")

        if format_type == GPSFormatType.SEPARATE_COLUMNS and not v:
            raise ValueError(
                f"{field_name.replace('_', ' ').title()} is required "
                "for separate columns format"
            )
        return v
