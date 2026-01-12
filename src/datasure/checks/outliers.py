"""Outliers detection module for survey data quality checks.

This module provides comprehensive outlier detection functionality with:
- Multiple detection methods (IQR, Standard Deviation)
- Polars-based optimizations for performance
- Pydantic validation for data integrity
- Modular, testable architecture
"""

import re
from enum import Enum, IntEnum
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go  # type: ignore
import polars as pl
import streamlit as st
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from datasure.utils.dataframe_utils import ColumnByType
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

TAB_NAME: str = "outliers"


# =============================================================================
# Enums and Constants
# =============================================================================


class OutlierMethod(str, Enum):
    """Supported outlier detection methods."""

    IQR = "Interquartile Range (IQR)"
    SD = "Standard Deviation (SD)"


class SearchType(str, Enum):
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
    sd: float
    iqr: float
    lower_bound: float
    upper_bound: float

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


# =============================================================================
# Utility Functions
# =============================================================================


def _ensure_list(value: Any) -> list:
    """Ensure value is a list.

    Parameters
    ----------
    value : Any
        Value to convert.

    Returns
    -------
    list
        Value as a list.
    """
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return value
    return list(value)


def _build_include_cols(
    survey_key: str,
    survey_id: str | None,
    survey_date: str | None,
    enumerator: str | None,
    team: str | None,
) -> list[str]:
    """Build list of columns to include in output.

    Parameters
    ----------
    survey_key : str
        Survey key column.
    survey_id : str | None
        Survey ID column.
    survey_date : str | None
        Survey date column.
    enumerator : str | None
        Enumerator column.
    team : str | None
        Team column.

    Returns
    -------
    list[str]
        Deduplicated list of columns to include.
    """
    include_cols = []
    for col in [survey_key, survey_id, survey_date, enumerator, team]:
        if col and col not in include_cols:
            include_cols.append(col)
    return include_cols


def _sanitize_df_for_join(
    main_df: pl.DataFrame,
    join_df: pl.DataFrame,
    join_key: str,
) -> pl.DataFrame:
    """Sanitize join DataFrame to avoid column name conflicts.

    Parameters
    ----------
    main_df : pl.DataFrame
        Main DataFrame.
    join_df : pl.DataFrame
        DataFrame to join.
    join_key : str
        Column name to join on.

    Returns
    -------
    pl.DataFrame
        Sanitized join DataFrame.
    """
    main_cols = main_df.columns
    join_cols = join_df.columns

    sanitized_cols = [
        col for col in join_cols if col not in main_cols or col == join_key
    ]

    return join_df.select(sanitized_cols)


def _convert_series_to_numeric(series: pl.Series) -> pl.Series:
    """Convert a Polars Series to numeric type.

    Parameters
    ----------
    series : pl.Series
        Series to convert.

    Returns
    -------
    pl.Series
        Converted series.

    Raises
    ------
    ValueError
        If conversion fails.
    """
    if series.dtype in pl.NUMERIC_DTYPES:
        # Cast to Float64 for consistency in concatenation
        return series.cast(pl.Float64)

    try:
        if series.dtype == pl.Utf8:
            return series.str.to_decimal().cast(pl.Float64, strict=False)
        return series.cast(pl.Float64, strict=False)
    except Exception as e:
        raise ValueError(
            f"Could not convert Series to numeric: {e}, keeping as {series.dtype}"
        ) from e


def _convert_dataframe_column_to_numeric(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """Convert a DataFrame column to numeric type.

    Parameters
    ----------
    df : pl.DataFrame
        DataFrame containing the column.
    column : str
        Column name to convert.

    Returns
    -------
    pl.DataFrame
        DataFrame with converted column.

    Raises
    ------
    ValueError
        If conversion fails.
    """
    if df[column].dtype in pl.NUMERIC_DTYPES:
        # Cast to Float64 for consistency in concatenation
        return df.with_columns(pl.col(column).cast(pl.Float64).alias(column))

    try:
        if df[column].dtype == pl.Utf8:
            return df.with_columns(
                pl.col(column)
                .str.to_decimal()
                .cast(pl.Float64, strict=False)
                .alias(column)
            )
        return df.with_columns(
            pl.col(column).cast(pl.Float64, strict=False).alias(column)
        )
    except Exception as e:
        raise ValueError(
            f"Could not convert column '{column}' to numeric: {e}, keeping as {df[column].dtype}"
        ) from e


def safe_to_numeric(
    data: pl.DataFrame | pl.Series, column: str | None = None
) -> pl.DataFrame | pl.Series:
    """Safely convert columns to numeric, keeping original if conversion fails.

    Parameters
    ----------
    data : pl.DataFrame | pl.Series
        Data to convert.
    column : str | None
        Column name to convert (required for DataFrames).

    Returns
    -------
    pl.DataFrame | pl.Series
        Converted data.

    Raises
    ------
    ValueError
        If conversion fails or invalid inputs provided.
    TypeError
        If input is not a Polars DataFrame or Series.
    """
    if isinstance(data, pl.Series):
        return _convert_series_to_numeric(data)

    if isinstance(data, pl.DataFrame):
        if not column:
            raise ValueError("Column is required with dataframes")
        return _convert_dataframe_column_to_numeric(data, column)

    raise TypeError("Input data must be a Polars DataFrame or Series.")


# =============================================================================
# Settings and Configuration Functions
# =============================================================================


def load_default_settings(
    settings_file: str, config: OutlierSettings
) -> OutlierSettings:
    """Load the default settings for the outliers report.

    Parameters
    ----------
    settings_file : str
        The settings file to load.
    config : OutlierSettings
        Default configuration.

    Returns
    -------
    OutlierSettings
        Merged settings.
    """
    # Load saved settings
    saved_settings = load_check_settings(settings_file, TAB_NAME)

    default_settings: dict = dict(config)
    default_settings.update(saved_settings)

    # Merge with defaults
    return OutlierSettings(**default_settings)


@st.cache_data
def expand_col_names(
    col_names: list[str], pattern: str, search_type: str = "exact"
) -> list[str]:
    """Expand column names based on a pattern and search type.

    Parameters
    ----------
    col_names : list[str]
        List of column names to search in.
    pattern : str
        Pattern to match against column names.
    search_type : str, default="exact"
        Type of search to perform.

    Returns
    -------
    list[str]
        List of column names that match the pattern.

    Raises
    ------
    TypeError
        If input types are invalid.
    ValueError
        If search_type is not supported.
    """
    if not isinstance(col_names, list):
        raise TypeError("col_names must be a list of column names.")
    if not pattern:
        raise TypeError("pattern must be provided.")
    if not isinstance(pattern, str):
        raise TypeError("pattern must be a string.")

    search_funcs = {
        SearchType.EXACT.value: lambda col: col == pattern,
        SearchType.STARTSWITH.value: lambda col: col.startswith(pattern),
        SearchType.ENDSWITH.value: lambda col: col.endswith(pattern),
        SearchType.CONTAINS.value: lambda col: pattern in col,
        SearchType.REGEX.value: lambda col: re.match(pattern, col),
    }

    if search_type not in search_funcs:
        valid_types = ", ".join(search_funcs.keys())
        raise ValueError(
            f"Invalid search_type '{search_type}'. Choose from: {valid_types}."
        )

    return [col for col in col_names if search_funcs[search_type](col)]


def _should_expand_row(row: dict) -> bool:
    """Check if a configuration row should have its columns expanded.

    Parameters
    ----------
    row : dict
        Configuration row to check (from Polars iter_rows).

    Returns
    -------
    bool
        True if row should be expanded.
    """
    return row["search_type"] != SearchType.EXACT.value and not row.get("locked", False)


@st.cache_data(hash_funcs={pl.DataFrame: lambda x: None})
def _update_unlocked_cols(
    column_config: pl.DataFrame,
    col_names: list[str],
) -> pl.DataFrame:
    """Update column names for unlocked rows in column configuration.

    Parameters
    ----------
    column_config : pl.DataFrame
        Polars DataFrame containing outlier column configuration.
    col_names : list[str]
        List of available column names.

    Returns
    -------
    pl.DataFrame
        Updated column configuration with expanded column names.

    Raises
    ------
    ValueError
        If essential columns are missing or pattern is invalid.
    """
    required_columns = {"search_type", "pattern", "column_name", "locked"}
    missing_columns = required_columns - set(column_config.columns)
    if missing_columns:
        raise ValueError(
            f"Missing required columns in column_config: {', '.join(missing_columns)}"
        )

    updated_rows = []
    for row in column_config.iter_rows(named=True):
        if _should_expand_row(row):
            expanded_cols = expand_col_names(
                col_names=col_names,
                pattern=row["pattern"],
                search_type=row["search_type"],
            )
            row["outlier_cols"] = expanded_cols
        updated_rows.append(row)

    return pl.DataFrame(updated_rows)


def update_unlocked_cols(
    outlier_settings: pl.DataFrame, col_names: list[str]
) -> pl.DataFrame:
    """Update column names for unlocked rows in outlier settings.

    Public API wrapper for backward compatibility.

    Parameters
    ----------
    outlier_settings : pl.DataFrame
        Polars DataFrame containing outlier settings or column configuration.
    col_names : list[str]
        List of available column names.

    Returns
    -------
    pl.DataFrame
        Updated settings with expanded column names.

    Raises
    ------
    ValueError
        If essential columns are missing or pattern is invalid.
    """
    return _update_unlocked_cols(outlier_settings, col_names)


# =============================================================================
# Statistical Computation Functions (Polars-optimized)
# =============================================================================


def _compute_iqr_bounds(series: pl.Series, multiplier: float) -> OutlierBounds:
    """Compute IQR-based outlier bounds.

    Parameters
    ----------
    series : pl.Series
        Numeric series to compute bounds for.
    multiplier : float
        IQR multiplier (typically 1.5).

    Returns
    -------
    OutlierBounds
        Lower and upper bounds.
    """
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1
    lower_bound = q1 - (multiplier * iqr)
    upper_bound = q3 + (multiplier * iqr)
    return OutlierBounds(lower_bound=lower_bound, upper_bound=upper_bound)


def _compute_sd_bounds(series: pl.Series, multiplier: float) -> OutlierBounds:
    """Compute standard deviation-based outlier bounds.

    Parameters
    ----------
    series : pl.Series
        Numeric series to compute bounds for.
    multiplier : float
        SD multiplier (typically 3.0).

    Returns
    -------
    OutlierBounds
        Lower and upper bounds.
    """
    mean = series.mean()
    std = series.std()
    lower_bound = mean - (multiplier * std)
    upper_bound = mean + (multiplier * std)
    return OutlierBounds(lower_bound=lower_bound, upper_bound=upper_bound)


def compute_outlier_stats_polars(
    series: pl.Series,
    outlier_type: str | None,
    multiplier: float | None,
) -> OutlierStatistics:
    """Compute outlier statistics using Polars for better performance.

    Parameters
    ----------
    series : pl.Series
        The Series to compute statistics for.
    outlier_type : str | None
        The type of outlier detection method to use.
    multiplier : float | None
        The multiplier to use for outlier detection.

    Returns
    -------
    OutlierStatistics
        Pydantic model containing computed statistics.

    Raises
    ------
    ValueError
        If series is empty or parameters are invalid.
    """
    if series.len() == 0:
        raise ValueError("The Series is empty.")

    valid_types = [None, OutlierMethod.IQR.value, OutlierMethod.SD.value]
    if outlier_type not in valid_types:
        raise ValueError(
            f"Invalid outlier type. Use 'IQR' or 'SD', got: {outlier_type}"
        )

    if multiplier is not None and multiplier <= 0:
        raise ValueError("Multiplier must be a positive number.")

    # remove nulls for accurate stats
    series = series.drop_nulls()

    series = safe_to_numeric(series)

    # return empty stats if no non-null values
    if series.len() == 0:
        return OutlierStatistics(
            count=0,
            min_value=float("nan"),
            max_value=float("nan"),
            mean=float("nan"),
            median=float("nan"),
            sd=float("nan"),
            iqr=float("nan"),
            lower_bound=float("nan"),
            upper_bound=float("nan"),
        )

    # Compute basic statistics
    count = series.len() - series.null_count()
    min_value = series.min()
    max_value = series.max()
    mean = series.mean()
    median = series.median()
    sd = series.std()
    q1 = series.quantile(0.25)
    q3 = series.quantile(0.75)
    iqr = q3 - q1

    # Compute bounds based on method
    if outlier_type == OutlierMethod.SD.value:
        multiplier = multiplier or OutlierMultipliers.SD.value
        bounds = _compute_sd_bounds(series, multiplier)
    else:  # Default to IQR
        multiplier = multiplier or OutlierMultipliers.IQR.value
        bounds = _compute_iqr_bounds(series, multiplier)

    return OutlierStatistics(
        count=count,
        min_value=min_value,
        max_value=max_value,
        mean=mean,
        median=median,
        sd=sd,
        iqr=iqr,
        lower_bound=bounds.lower_bound,
        upper_bound=bounds.upper_bound,
    )


@st.cache_data(hash_funcs={pl.DataFrame: lambda df: str(df.schema)})
def stack_outlier_columns(df: pl.DataFrame, col_names: list[str]) -> pl.Series:
    """Stack specified columns of a DataFrame into a single Series.

    Parameters
    ----------
    df : pl.DataFrame
        The DataFrame containing the data.
    col_names : list[str]
        List of column names to stack.

    Returns
    -------
    pl.Series
        A Series containing the stacked values.

    Raises
    ------
    ValueError
        If DataFrame is empty or columns don't exist.
    """
    if df.is_empty():
        raise ValueError("The DataFrame is empty.")

    for col in col_names:
        if col not in df.columns:
            raise ValueError(f"Column '{col}' does not exist in the DataFrame.")

    # Check and convert columns to numeric if needed
    for col in col_names:
        dtype = df[col].dtype
        if dtype not in [
            pl.Int8,
            pl.Int16,
            pl.Int32,
            pl.Int64,
            pl.UInt8,
            pl.UInt16,
            pl.UInt32,
            pl.UInt64,
            pl.Float32,
            pl.Float64,
        ]:
            try:
                df = df.with_columns(pl.col(col).cast(pl.Float64))
            except Exception:
                raise ValueError(
                    f"Column '{col}' cannot be converted to numeric type."
                ) from None

    # Stack the columns - melt/unpivot in Polars
    stacked_values = (
        df.select(col_names)
        .unpivot()
        .get_column("value")
        .drop_nulls()  # Remove null values like pandas stack() does
    )

    return stacked_values


def _build_outlier_expression(
    col: str,
    lower_bound: float,
    upper_bound: float,
) -> pl.Expr:
    """Build Polars expression for outlier flagging.

    Parameters
    ----------
    col : str
        Column name.
    lower_bound : float
        Statistical lower bound.
    upper_bound : float
        Statistical upper bound.

    Returns
    -------
    pl.Expr
        Polars expression for outlier detection.
    """
    outlier_expr = (
        pl.when(pl.col(col) < lower_bound)
        .then(pl.lit(f"Value is below lower bound {lower_bound:.2f}"))
        .when(pl.col(col) > upper_bound)
        .then(pl.lit(f"Value is above upper bound {upper_bound:.2f}"))
    )

    return outlier_expr.otherwise(pl.lit("no outlier"))


def _add_statistics_columns(
    col_df: pl.DataFrame,
    outlier_stats: OutlierStatistics,
    outlier_method: str,
    outlier_multiplier: float,
    col_name: str,
) -> pl.DataFrame:
    """Add statistics columns to the outlier dataframe.

    Parameters
    ----------
    col_df : pl.DataFrame
        DataFrame to add columns to.
    outlier_stats : OutlierStatistics
        Computed statistics.
    outlier_method : str
        Detection method used.
    outlier_multiplier : float
        Multiplier used.
    col_name : str
        Name of the column being analyzed.

    Returns
    -------
    pl.DataFrame
        DataFrame with added statistics columns.
    """
    return col_df.with_columns(
        [
            pl.lit(outlier_stats.min_value, dtype=pl.Float64).alias("min_value"),
            pl.lit(outlier_stats.max_value, dtype=pl.Float64).alias("max_value"),
            pl.lit(outlier_stats.mean, dtype=pl.Float64).alias("mean"),
            pl.lit(outlier_stats.median, dtype=pl.Float64).alias("median"),
            pl.lit(outlier_stats.sd, dtype=pl.Float64).alias("std"),
            pl.lit(outlier_stats.iqr, dtype=pl.Float64).alias("iqr"),
            pl.lit(outlier_stats.lower_bound, dtype=pl.Float64).alias("lower_bound"),
            pl.lit(outlier_stats.upper_bound, dtype=pl.Float64).alias("upper_bound"),
            pl.lit(outlier_method).alias("outlier_method"),
            pl.lit(outlier_multiplier, dtype=pl.Float64).alias("outlier_multiplier"),
            pl.lit(col_name).alias("column name"),
        ]
    )


def _process_single_column_outliers(
    df_polars: pl.DataFrame,
    col: str,
    survey_key: str,
    outlier_stats: OutlierStatistics,
    outlier_method: str,
    outlier_multiplier: float,
    min_threshold: int,
    non_null_count: int,
) -> pl.DataFrame:
    """Process outliers for a single column using Polars.

    Parameters
    ----------
    df_polars : pl.DataFrame
        Polars DataFrame containing the data.
    col : str
        Column name to process.
    survey_key : str
        Survey key column name.
    outlier_stats : OutlierStatistics
        Pre-computed statistics.
    outlier_method : str
        Outlier detection method.
    outlier_multiplier : float
        Multiplier for detection.
    min_threshold : int
        Minimum sample size threshold.
    non_null_count : int
        Number of non-null values.

    Returns
    -------
    pl.DataFrame
        DataFrame with outlier information for the column.
    """
    # Select relevant columns
    col_df = df_polars.select([survey_key, col])
    col_df = safe_to_numeric(col_df, col)

    # Add outlier reason
    if non_null_count < min_threshold:
        col_df = col_df.with_columns(pl.lit("no outlier").alias("outlier reason"))
    else:
        # Vectorized outlier flagging
        outlier_expr = _build_outlier_expression(
            col,
            outlier_stats.lower_bound,
            outlier_stats.upper_bound,
        )
        col_df = col_df.with_columns(outlier_expr.alias("outlier reason"))

    # Add statistics columns
    col_df = _add_statistics_columns(
        col_df,
        outlier_stats,
        outlier_method,
        outlier_multiplier,
        col,
    )

    # Rename and reorder
    col_df = col_df.rename({col: "column value"})
    col_df = col_df.select(
        [
            survey_key,
            "column name",
            "column value",
            "min_value",
            "max_value",
            "mean",
            "median",
            "std",
            "iqr",
            "lower_bound",
            "upper_bound",
            "outlier reason",
            "outlier_method",
            "outlier_multiplier",
        ]
    )

    return col_df


# =============================================================================
# Outlier Detection - Main Logic
# =============================================================================


def compute_outlier_output(
    data: pl.DataFrame,
    outlier_settings: dict,
    column_config: pl.DataFrame,
) -> pl.DataFrame:
    """Detect outliers in DataFrame based on settings (Polars-optimized).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing the survey data.
    outlier_settings : dict
        Outlier settings configuration.
    column_config : pl.DataFrame
        DataFrame containing the outlier column configurations.

    Returns
    -------
    pl.DataFrame
        DataFrame containing the outlier summary.

    Raises
    ------
    ValueError
        If DataFrame is empty.
    """
    if data.is_empty():
        raise ValueError("The DataFrame is empty. Please provide a valid DataFrame.")

    # Build include columns list
    survey_key = outlier_settings.survey_key
    survey_id = outlier_settings.survey_id
    survey_date = outlier_settings.survey_date
    enumerator = outlier_settings.enumerator
    team = outlier_settings.team
    include_cols = _build_include_cols(
        survey_key, survey_id, survey_date, enumerator, team
    )

    # Select admin data
    admin_data_polars = data.select(include_cols)

    # Process outlier settings
    outlier_results_list = []
    for row in column_config.iter_rows(named=True):
        # Check if outlier detection is enabled
        outlier_enabled = row.get("outlier_enabled", False)
        if not outlier_enabled:
            continue

        # Extract settings with defaults
        outlier_cols = _ensure_list(row.get("column_name", []))
        grouped_cols = row.get("grouped_columns", False)
        outlier_method = row.get("outlier_method", OutlierMethod.IQR.value)
        threshold = row.get("outlier_threshold", OutlierThresholds.IQR.value)
        outlier_multiplier = row.get("outlier_multiplier", OutlierMultipliers.IQR.value)

        # Create subset
        outlier_df_polars = data.select([survey_key, *outlier_cols])

        # Compute statistics based on grouping
        if len(outlier_cols) == 1:
            non_null_count = (
                outlier_df_polars.height
                - outlier_df_polars[outlier_cols[0]].null_count()
            )
            outlier_stats = compute_outlier_stats_polars(
                outlier_df_polars[outlier_cols[0]],
                outlier_type=outlier_method,
                multiplier=outlier_multiplier,
            )
        elif grouped_cols:
            stacked_series = pl.concat([outlier_df_polars[col] for col in outlier_cols])
            non_null_count = stacked_series.len() - stacked_series.null_count()
            outlier_stats = compute_outlier_stats_polars(
                stacked_series,
                outlier_type=outlier_method,
                multiplier=outlier_multiplier,
            )

        # Process each column
        for col in outlier_cols:
            if not grouped_cols:
                non_null_count = (
                    outlier_df_polars.height - outlier_df_polars[col].null_count()
                )
                outlier_stats = compute_outlier_stats_polars(
                    outlier_df_polars[col],
                    outlier_type=outlier_method,
                    multiplier=outlier_multiplier,
                )

            col_result = _process_single_column_outliers(
                df_polars=outlier_df_polars,
                col=col,
                survey_key=survey_key,
                outlier_stats=outlier_stats,
                outlier_method=outlier_method,
                outlier_multiplier=outlier_multiplier,
                min_threshold=threshold,
                non_null_count=non_null_count,
            )

            outlier_results_list.append(col_result)

    # Concatenate and merge results
    if outlier_results_list:
        outlier_results_polars = pl.concat(outlier_results_list)

        if not admin_data_polars.is_empty():
            merged_results = admin_data_polars.join(
                outlier_results_polars,
                on=survey_key,
                how="left",
            )
        else:
            merged_results = outlier_results_polars

        return merged_results

    return pl.DataFrame()


# =============================================================================
# Constraint Violations - Main Logic
# =============================================================================


def compute_constraint_violations(
    data: pl.DataFrame,
    settings: OutlierSettings,
    column_config: pl.DataFrame,
) -> pl.DataFrame:
    """Compute constraint violations for outlier detection.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing the survey data.
    settings : OutlierSettings
        Outlier settings configuration.
    column_config : pl.DataFrame
        DataFrame containing the outlier column configurations.

    Returns
    -------
    pl.DataFrame
        DataFrame containing constraint violation information.
    """
    survey_key = settings.survey_key

    violation_results = pl.DataFrame()

    for row in column_config.iter_rows(named=True):
        outlier_cols = _ensure_list(row.get("column_name", []))
        hard_min = row.get("hard_min", None)
        soft_min = row.get("soft_min", None)
        soft_max = row.get("soft_max", None)
        hard_max = row.get("hard_max", None)

        # skip if no bounds are set
        if all(bound is None for bound in [hard_min, soft_min, soft_max, hard_max]):
            continue

        for col in outlier_cols:
            col_df = data.select([survey_key, col])

            violation_expr = (
                pl.when((hard_min is not None) & (pl.col(col) < hard_min))
                .then(pl.lit(f"Value is below hard minimum {hard_min}"))
                .when((soft_min is not None) & (pl.col(col) < soft_min))
                .then(pl.lit(f"Value is below soft minimum {soft_min}"))
                .when((soft_max is not None) & (pl.col(col) > soft_max))
                .then(pl.lit(f"Value is above soft maximum {soft_max}"))
                .when((hard_max is not None) & (pl.col(col) > hard_max))
                .then(pl.lit(f"Value is above hard maximum {hard_max}"))
            )

            col_df = safe_to_numeric(col_df, col)

            col_df = col_df.with_columns(
                violation_expr.otherwise(pl.lit("no violation")).alias(
                    "violation reason"
                )
            )

            # add hard and soft bounds columns
            for bound_name, bound_value in [
                ("hard_min", hard_min),
                ("soft_min", soft_min),
                ("soft_max", soft_max),
                ("hard_max", hard_max),
            ]:
                col_df = col_df.with_columns(pl.lit(bound_value).alias(bound_name))

            col_df = col_df.rename({col: "column value"})
            col_df = col_df.with_columns(pl.lit(col).alias("column name")).select(
                [
                    survey_key,
                    "column name",
                    "column value",
                    "hard_min",
                    "soft_min",
                    "soft_max",
                    "hard_max",
                    "violation reason",
                ]
            )

            violation_results = (
                violation_results.vstack(col_df)
                if not violation_results.is_empty()
                else col_df
            )

    return violation_results


# =============================================================================
# Metrics Computation - Analytics
# =============================================================================


def _compute_constraint_metrics(violation_data: pl.DataFrame) -> ConstraintMetrics:
    """Compute metrics related to constraint violations.

    Parameters
    ----------
    violation_data : pl.DataFrame
        DataFrame containing constraint violation data.

    Returns
    -------
    ConstraintMetrics
        Pydantic model containing computed metrics.
    """
    columns_checked = violation_data.select("column name").n_unique()
    total_violations = violation_data.filter(
        pl.col("violation reason") != "no violation"
    ).height

    hard_min_violations = violation_data.filter(
        pl.col("violation reason").str.contains("below hard minimum")
    ).height
    soft_min_violations = violation_data.filter(
        pl.col("violation reason").str.contains("below soft minimum")
    ).height
    soft_max_violations = violation_data.filter(
        pl.col("violation reason").str.contains("above soft maximum")
    ).height
    hard_max_violations = violation_data.filter(
        pl.col("violation reason").str.contains("above hard maximum")
    ).height

    return ConstraintMetrics(
        columns_checked=columns_checked,
        total_violations=total_violations,
        hard_min_violations=hard_min_violations,
        soft_min_violations=soft_min_violations,
        soft_max_violations=soft_max_violations,
        hard_max_violations=hard_max_violations,
    )


def _compute_outlier_metrics(
    outliers_data: pl.DataFrame,
    enumerator: str | None,
) -> OutlierMetrics:
    """Compute outlier metrics.

    Parameters
    ----------
    outliers_data : pl.DataFrame
        DataFrame containing outlier data.
    enumerator : str | None
        Enumerator column name.

    Returns
    -------
    OutlierMetrics
        Pydantic model containing computed metrics.
    """
    columns_checked = outliers_data.select("column name").n_unique()
    columns_with_outliers = (
        outliers_data.filter(pl.col("outlier reason") != "no outlier")
        .select("column name")
        .n_unique()
    )
    total_outliers = outliers_data.filter(
        pl.col("outlier reason") != "no outlier"
    ).height
    if enumerator:
        enumerators_with_outliers = (
            outliers_data.filter(pl.col("outlier reason") != "no outlier")
            .select(enumerator)
            .n_unique()
        )
    else:
        enumerators_with_outliers = 0

    return OutlierMetrics(
        columns_checked=columns_checked,
        columns_with_outliers=columns_with_outliers,
        total_outliers=total_outliers,
        enumerators_with_outliers=enumerators_with_outliers,
    )


def compute_column_outlier_summary(
    outlier_data: pl.DataFrame, survey_key: str
) -> pl.DataFrame:
    """Compute a summary of outliers for each column using Polars.

    Parameters
    ----------
    outlier_data : pl.DataFrame
        Polars DataFrame containing outlier data.
    survey_key : str
        Survey key column name.

    Returns
    -------
    pl.DataFrame
        Summary DataFrame with outlier counts per column.
    """
    if outlier_data.is_empty():
        return pl.DataFrame()

    # Remove duplicates
    outlier_summary = outlier_data.unique(subset=["column name", survey_key])

    # Count occurrences per column
    col_counts = outlier_summary.group_by("column name").agg(pl.count().alias("count"))

    # Join counts back
    outlier_summary = outlier_summary.join(col_counts, on="column name", how="left")

    # Flag outliers
    outlier_summary = outlier_summary.with_columns(
        pl.when(pl.col("outlier reason") != "no outlier")
        .then(pl.lit(1))
        .otherwise(pl.lit(0))
        .alias("flagged as outlier")
    )

    # Count outliers per column
    outlier_counts = outlier_summary.group_by("column name").agg(
        pl.col("flagged as outlier").sum().alias("outlier count")
    )

    # Merge outlier counts
    outlier_summary = outlier_summary.join(outlier_counts, on="column name", how="left")

    # Select and order columns
    outlier_summary = outlier_summary.select(
        [
            "column name",
            "count",
            "outlier count",
            "min_value",
            "max_value",
            "mean",
            "median",
            "std",
            "iqr",
            "lower_bound",
            "upper_bound",
        ]
    )

    return outlier_summary.unique(subset=["column name"])


def get_outlier_cols(outlier_settings: pd.DataFrame) -> list[str]:
    """Get list of outlier columns from settings DataFrame.

    Parameters
    ----------
    outlier_settings : pd.DataFrame
        DataFrame containing outlier settings.

    Returns
    -------
    list[str]
        List of column names to check for outliers.
    """
    cols = []
    for i in range(len(outlier_settings)):
        col = outlier_settings.iloc[i]["outlier_cols"]
        if isinstance(col, np.ndarray):
            cols.append(col[0])
        elif isinstance(col, list):
            cols.extend(col)

    return cols


# =============================================================================
# Visualization Functions
# =============================================================================


@st.cache_data
def _create_box_plot(data: pd.Series, title: str) -> go.Figure:
    """Create a box plot using plotly.

    Parameters
    ----------
    data : pd.Series
        Data series to plot.
    title : str
        Title for the plot.

    Returns
    -------
    go.Figure
        Plotly figure object.
    """
    return go.Figure(
        data=go.Box(
            y=data,
            boxpoints="outliers",
            marker_color="darkblue",
            line_color="black",
            fillcolor="lightblue",
            opacity=0.6,
            x0=title,
        )
    )


@st.cache_data
def _create_descriptive_stats(column_data: pl.DataFrame) -> pl.DataFrame:
    """Create descriptive statistics table.

    Parameters
    ----------
    column_data : pl.DataFrame
        Column data to analyze.

    Returns
    -------
    pl.DataFrame
        Descriptive statistics table.
    """
    table = column_data.describe()
    table.columns = ["statistic", "value"]
    # rename statistics
    stat_rename = {
        "count": "Number of Values",
        "null_count": "Number of Missing Values",
        "mean": "Mean",
        "std": "Standard Deviation",
        "min": "Minimum Value",
        "25%": "25th Percentile (Q1)",
        "50%": "Median (Q2)",
        "75%": "75th Percentile (Q3)",
        "max": "Maximum Value",
    }

    table = table.with_columns(
        pl.col("statistic").replace(stat_rename).alias("statistic")
    )

    return table


# =============================================================================
# Streamlit UI - Metrics Display
# =============================================================================


def _render_constraint_metrics(
    violation_data: pl.DataFrame,
) -> None:
    """Render constraint violation metrics using Streamlit.

    Parameters
    ----------
    violation_data : pl.DataFrame
        DataFrame containing constraint violation data.
    """
    metrics: ConstraintMetrics = _compute_constraint_metrics(violation_data)

    _, _, uc3, uc4 = st.columns(4)
    with uc3, st.container(border=True):
        st.metric(
            label="Number of columns checked",
            value=f"{metrics.columns_checked:,}",
            help="Number of columns checked for constraint violations",
        )
    with uc4, st.container(border=True):
        st.metric(
            label="Total Violations",
            value=f"{metrics.total_violations:,}",
            help="Total number of constraint violations detected",
        )

    lc1, lc2, lc3, lc4 = st.columns(4, border=True)
    lc1.metric(
        label="Hard Min Violations",
        value=f"{metrics.hard_min_violations:,}",
        help="Number of violations below hard minimum",
    )
    lc2.metric(
        label="Soft Min Violations",
        value=f"{metrics.soft_min_violations:,}",
        help="Number of violations below soft minimum",
    )
    lc3.metric(
        label="Soft Max Violations",
        value=f"{metrics.soft_max_violations:,}",
        help="Number of violations above soft maximum",
    )
    lc4.metric(
        label="Hard Max Violations",
        value=f"{metrics.hard_max_violations:,}",
        help="Number of violations above hard maximum",
    )


def _render_outlier_metrics(
    outliers_data: pl.DataFrame,
    settings: OutlierSettings,
) -> None:
    """Render outlier metrics using Streamlit.

    Parameters
    ----------
    outliers_data : pl.DataFrame
        DataFrame containing outlier data.
    settings : OutlierSettings
        Outlier settings configuration.
    """
    metrics: OutlierMetrics = _compute_outlier_metrics(
        outliers_data, settings.enumerator
    )

    uc1, uc2, uc3, uc4 = st.columns(4, border=True)
    uc1.metric(
        label="Number of columns checked",
        value=f"{metrics.columns_checked:,}",
        help="Number of columns checked for outliers",
    )
    uc2.metric(
        label="Columns with Outliers",
        value=f"{metrics.columns_with_outliers:,}",
        help="Number of columns that have outliers detected",
    )
    uc3.metric(
        label="Total Outliers",
        value=f"{metrics.total_outliers:,}",
        help="Total number of outliers detected",
    )
    if settings.enumerator:
        uc4.metric(
            label="Enumerators with Outliers",
            value=f"{metrics.enumerators_with_outliers:,}",
            help="Number of unique enumerators with outliers detected",
        )


# =============================================================================
# Streamlit UI - Table Display
# =============================================================================


def _render_constraint_violations_table(
    data: pl.DataFrame,
    violation_data: pl.DataFrame,
    settings: OutlierSettings,
    setting_file: str,
) -> None:
    """Render constraint violations table using Streamlit.

    Parameters
    ----------
    data : pl.DataFrame
        Original survey data.
    violation_data : pl.DataFrame
        DataFrame containing constraint violation data.
    settings : OutlierSettings
        Outlier settings configuration.
    setting_file : str
        Path to settings file.
    """
    if violation_data.is_empty():
        st.info("No constraint violations detected.")
        return

    all_columns = data.columns

    include_cols = _build_include_cols(
        survey_key=settings.survey_key,
        survey_id=settings.survey_id,
        survey_date=settings.survey_date,
        enumerator=settings.enumerator,
        team=settings.team,
    )

    display_options = [col for col in all_columns if col not in include_cols]

    with st.expander(":material/clarify: Show more columns in report", expanded=False):
        st.info(
            "Select additional columns to include in the constraint violations report."
        )

        # get saved settings
        saved_settings = load_check_settings(setting_file, TAB_NAME)
        cols = saved_settings.get("constraint_display_cols", [])
        default_constraint_display_cols = [
            col for col in cols if col in display_options
        ]

        constraint_display_cols = st.multiselect(
            label="Select columns to display",
            options=display_options,
            default=default_constraint_display_cols,
            key="constraint_violation_display_cols",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_constraint_display_cols"},
        )
        save_check_settings(
            setting_file, TAB_NAME, {"constraint_display_cols": constraint_display_cols}
        )

    if constraint_display_cols:
        include_cols.extend(constraint_display_cols)

    # select columns to display from data
    display_df = data.select(include_cols)
    # sanitize violation_data to avoid column name conflicts
    violation_df = _sanitize_df_for_join(
        main_df=display_df,
        join_df=violation_data,
        join_key=settings.survey_key,
    )

    display_df = display_df.join(
        violation_df,
        on=settings.survey_key,
        how="inner",
    )

    # show only rows with violations
    violations_df = display_df.filter(pl.col("violation reason") != "no violation")

    st.dataframe(violations_df)


def _render_outlier_table(
    data: pl.DataFrame,
    outliers_data: pl.DataFrame,
    settings: OutlierSettings,
    setting_file: str,
) -> None:
    """Render outlier data table using Streamlit.

    Parameters
    ----------
    data : pl.DataFrame
        Original survey data.
    outliers_data : pl.DataFrame
        DataFrame containing outlier data.
    settings : OutlierSettings
        Outlier settings configuration.
    setting_file : str
        Path to settings file.
    """
    if outliers_data.is_empty():
        st.info("No outliers detected in the selected columns.")
        return

    all_columns = data.columns

    include_cols = _build_include_cols(
        survey_key=settings.survey_key,
        survey_id=settings.survey_id,
        survey_date=settings.survey_date,
        enumerator=settings.enumerator,
        team=settings.team,
    )

    display_options = [col for col in all_columns if col not in include_cols]

    # get saved settings
    saved_settings = load_check_settings(setting_file, TAB_NAME)
    cols = saved_settings.get("outlier_display_cols", [])
    default_outlier_display_cols = [col for col in cols if col in display_options]

    with st.expander(":material/clarify: Show more columns in report", expanded=False):
        st.info("Select additional columns to include in the outlier report.")
        outlier_display_cols = st.multiselect(
            label="Select columns to display",
            default=default_outlier_display_cols,
            options=display_options,
            key="outlier_display_cols",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_outlier_display_cols"},
        )
        save_check_settings(
            setting_file, TAB_NAME, {"outlier_display_cols": outlier_display_cols}
        )

    if outlier_display_cols:
        include_cols.extend(outlier_display_cols)

    # select columns to display from data
    display_df = data.select(include_cols)
    outliers_df = _sanitize_df_for_join(display_df, outliers_data, settings.survey_key)
    display_df = display_df.join(
        outliers_df,
        on=settings.survey_key,
        how="inner",
    )

    # show only rows with outliers
    outlier_show_df = display_df.filter(pl.col("outlier reason") != "no outlier")

    st.dataframe(outlier_show_df)


def _render_outlier_column_inspection(
    data: pl.DataFrame,
    outliers_data: pl.DataFrame,
    settings: OutlierSettings,
    setting_file: str,
) -> None:
    """Inspect outlier columns in the DataFrame.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing the survey data.
    outliers_data : pl.DataFrame
        DataFrame containing outlier detection results.
    settings : OutlierSettings
        Outlier settings configuration.
    setting_file : str
        Path to settings file.
    """
    if outliers_data.is_empty():
        st.info(
            "No outlier columns selected. Please select outlier columns to inspect."
        )
        return

    all_columns = data.columns

    include_cols = _build_include_cols(
        survey_key=settings.survey_key,
        survey_id=settings.survey_id,
        survey_date=settings.survey_date,
        enumerator=settings.enumerator,
        team=settings.team,
    )

    # list of outlier columns checked
    columns_checked_list = (
        outliers_data.select("column name").unique().to_series().to_list()
    )

    ic1, _ = st.columns([0.2, 0.8])

    with ic1:
        # get saved settings
        saved_settings = load_check_settings(setting_file, TAB_NAME)
        default_selected_col = saved_settings.get("selected_col", None)
        default_selected_col_index = (
            columns_checked_list.index(default_selected_col)
            if default_selected_col and default_selected_col in columns_checked_list
            else None
        )
        selected_col = st.selectbox(
            label="Select outlier columns to inspect",
            options=columns_checked_list,
            index=default_selected_col_index,
            key="outlier_inspect_col",
            help="Select the outlier columns to inspect. "
            "You can only select one column at a time.",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_selected_col"},
        )
        save_check_settings(setting_file, TAB_NAME, {"selected_col": selected_col})

        if not selected_col:
            st.info("Select an outlier column to inspect.")
            return

        if selected_col not in data.columns:
            raise ValueError(
                f"Selected column '{selected_col}' is not present in the data. "
                "Please select a valid column."
            )
        else:
            include_cols.append(selected_col)

    # create a subset of the data
    column_data = data.select([selected_col])

    st.subheader(f"Details/Distribution for {selected_col} values")
    dc1, _, dc3 = st.columns([0.3, 0.1, 0.6])
    with dc1:
        desc_stats = _create_descriptive_stats(column_data)
        st.dataframe(desc_stats)

    with dc3:
        box_plot = _create_box_plot(
            data=column_data[selected_col].to_pandas(),
            title=selected_col,
        )
        st.plotly_chart(box_plot, width="stretch")

    with st.expander(":material/clarify: Show more columns in report", expanded=False):
        st.info(
            "Select additional columns to include in the outlier inspection report."
        )
        display_options = [
            col
            for col in all_columns
            if col not in include_cols and col != selected_col
        ]
        inspect_display_cols = st.multiselect(
            label="Select columns to display",
            options=display_options,
            default=None,
            help="Select the columns to display in the inspection table.",
            disabled=not selected_col,
        )

        if inspect_display_cols:
            include_cols.extend(inspect_display_cols)

    # select columns to display from data
    display_df = data.select(include_cols)
    outliers_df = _sanitize_df_for_join(display_df, outliers_data, settings.survey_key)
    display_df = display_df.join(
        outliers_df,
        on=settings.survey_key,
        how="inner",
    )

    st.dataframe(
        display_df,
        width="stretch",
        hide_index=False,
    )


# =============================================================================
# Streamlit UI - Settings Configuration
# =============================================================================


def _create_search_type_info(search_type_param: str) -> None:
    """Display info based on the selected search type.

    Parameters
    ----------
    search_type_param : str
        The search type to display info for.
    """
    info_messages = {
        SearchType.EXACT.value: "Select columns that match the exact name. "
        "You may select multiple columns.",
        SearchType.STARTSWITH.value: "Select columns that start with the specified pattern. "
        "You will have to enter the pattern in the input box below.",
        SearchType.ENDSWITH.value: "Select columns that end with the specified pattern. "
        "You will have to enter the pattern in the input box below.",
        SearchType.CONTAINS.value: "Select columns that contain the specified pattern. "
        "You will have to enter the pattern in the input box below.",
        SearchType.REGEX.value: "Select columns that match the specified regex pattern. "
        "You will have to enter the pattern in the input box below.",
    }

    st.info(info_messages.get(search_type_param, "Unknown search type."))


@demo_output_onboarding(TAB_NAME)
def outliers_report_settings(
    settings_file: str,
    config: OutlierSettings,
    categorical_columns: list[str],
    datetime_columns: list[str],
) -> OutlierSettings:
    """Create a settings UI for outliers report configuration.

    This function creates the comprehensive Streamlit UI for configuring
    outlier detection settings. Due to its complexity (UI rendering),
    it maintains a higher cognitive complexity but is well-structured.

    Parameters
    ----------
    settings_file : str
        Path to settings file.
    config : OutlierSettings
        Default configuration.
    categorical_columns : list[str]
        List of categorical columns.
    datetime_columns : list[str]
        List of datetime columns.

    Returns
    -------
    OutlierSettings
        User-configured settings.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for outliers report")
        st.write("---")

        # Load default settings
        default_settings = load_default_settings(settings_file, config)

        # Survey Identifiers
        with st.container(border=True):
            st.markdown("#### Survey Identifiers")
            si1, si2, _ = st.columns(3)

            with si1:
                default_survey_key = default_settings.survey_key
                default_survey_key_index = (
                    categorical_columns.index(default_survey_key)
                    if default_survey_key and default_survey_key in categorical_columns
                    else None
                )
                survey_key = st.selectbox(
                    "Survey Key",
                    options=categorical_columns,
                    key="survey_key_outliers",
                    help="Select the column that contains the survey key",
                    index=default_survey_key_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_key"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_key": survey_key})

            with si2:
                default_survey_id = default_settings.survey_id
                default_survey_id_index = (
                    categorical_columns.index(default_survey_id)
                    if default_survey_id and default_survey_id in categorical_columns
                    else None
                )
                survey_id = st.selectbox(
                    "Survey ID",
                    options=categorical_columns,
                    help="Select the column that contains the survey ID",
                    key="survey_id_outliers",
                    index=default_survey_id_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_id"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_id": survey_id})

        with st.container(border=True):
            st.markdown("#### Survey Date")

            sd1, _, _ = st.columns(3)

            with sd1:
                default_survey_date = default_settings.survey_date
                default_survey_date_index = (
                    datetime_columns.index(default_survey_date)
                    if default_survey_date and default_survey_date in datetime_columns
                    else None
                )

                survey_date = st.selectbox(
                    "Survey Date",
                    options=datetime_columns,
                    help="Select the column that contains the survey date",
                    key="survey_date_outliers",
                    index=default_survey_date_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_date"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"survey_date": survey_date}
                )

        with st.container(border=True):
            st.markdown("#### Enumerator & Team")
            ec1, ec2, _ = st.columns(3)
            with ec1:
                default_enumerator = default_settings.enumerator
                default_enumerator_index = (
                    categorical_columns.index(default_enumerator)
                    if default_enumerator and default_enumerator in categorical_columns
                    else None
                )
                enumerator = st.selectbox(
                    "Enumerator ID",
                    options=categorical_columns,
                    key="enumerator_outliers",
                    help="Select the column that contains the enumerator ID",
                    index=default_enumerator_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_enumerator"},
                )
                save_check_settings(settings_file, TAB_NAME, {"enumerator": enumerator})

            with ec2:
                default_team = default_settings.team
                default_team_index = (
                    categorical_columns.index(default_team)
                    if default_team and default_team in categorical_columns
                    else None
                )
                team = st.selectbox(
                    "Team ID",
                    options=categorical_columns,
                    key="team_outliers",
                    help="Select the column that contains the team ID",
                    index=default_team_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_team"},
                )
                save_check_settings(settings_file, TAB_NAME, {"team": team})

    return OutlierSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        enumerator=enumerator,
        team=team,
    )


# =============================================================================
# Streamlit UI - Column Configuration
# =============================================================================


def _render_search_type_selection(
    numeric_columns: list[str],
) -> tuple[str, str | None, list[str], bool]:
    """Render search type selection UI.

    Parameters
    ----------
    numeric_columns : list[str]
        List of numeric columns.

    Returns
    -------
    tuple[str, str | None, list[str], bool]
        Search type, pattern, selected columns, and lock_cols flag.
    """
    search_type_options = [e.value for e in SearchType]
    search_type = st.selectbox(
        label="Search type",
        options=search_type_options,
        index=0,
        help="Select the type of search to perform on the column names.",
    )

    _create_search_type_info(search_type)

    if search_type == SearchType.EXACT.value:
        outlier_cols_sel = st.multiselect(
            label="Select columns to check",
            options=numeric_columns,
            default=None,
            help="Select column or group of columns to check for outliers.",
        )
        pattern, lock_cols = None, None
        return search_type, pattern, outlier_cols_sel, lock_cols
    else:
        pattern = st.text_input(
            label="Enter pattern to match column names",
            placeholder="Enter pattern to match column names",
            help="Enter the pattern to match column names based on the "
            "selected search type.",
        )
        if pattern:
            outlier_cols_patt = expand_col_names(
                numeric_columns, pattern, search_type=search_type
            )
        else:
            outlier_cols_patt = []

        st.write(
            "**Columns Selected:** ",
            ", ".join(outlier_cols_patt) if outlier_cols_patt else "None",
        )
        return search_type, pattern, outlier_cols_patt, None


def _render_column_grouping_options(
    outlier_cols: list[str], search_type: str
) -> tuple[bool, bool]:
    """Render column grouping and locking options.

    Parameters
    ----------
    outlier_cols : list[str]
        Selected outlier columns.
    search_type : str
        Search type used.

    Returns
    -------
    tuple[bool, bool]
        Group columns flag and lock columns flag.
    """
    gc1, gc2 = st.columns([0.5, 0.5])
    with gc1:
        group_cols = st.toggle(
            label="Group columns",
            key="group_outlier_cols",
            help="Group selected columns together for outlier detection.",
            disabled=not outlier_cols or len(outlier_cols) < 2,
        )
    with gc2:
        lock_cols = st.toggle(
            label="Lock column selection",
            key="outlier_cols_lock",
            help="Lock the selected columns to prevent changes.",
            disabled=not outlier_cols
            or len(outlier_cols) < 2
            or search_type == SearchType.EXACT.value,
        )
    return group_cols, lock_cols


def _render_outlier_options() -> tuple[bool, dict | None, bool]:
    """Render outlier detection options UI.

    Returns
    -------
    tuple[bool, dict | None, bool]
        Enable outliers flag, outlier settings dict, and validation status.
    """
    with st.container(border=True):
        st.write("**Outlier Options:**")
        enable_outliers = st.toggle(
            "Enable Outlier Checks", key="enable_coutlier", value=True
        )
        if enable_outliers:
            oc1, oc2 = st.columns([0.5, 0.5])
            with oc1:
                outlier_method = st.selectbox(
                    label="Select outlier detection method",
                    options=[e.value for e in OutlierMethod],
                    index=0,
                    help="Select the method to use for outlier detection.",
                    key="outlier_method",
                )
            with oc2:
                default_multiplier = (
                    OutlierMultipliers.IQR.value
                    if outlier_method == OutlierMethod.IQR.value
                    else OutlierMultipliers.SD.value
                )
                outlier_multiplier = st.number_input(
                    label="Select multiplier for outlier detection",
                    min_value=0.1,
                    max_value=10.0,
                    value=default_multiplier,
                    step=0.1,
                    help="Select the multiplier to use for outlier detection.",
                    key="outlier_multiplier",
                )

            outlier_threshold_default = (
                OutlierThresholds.SD.value
                if outlier_method == OutlierMethod.SD.value
                else OutlierThresholds.IQR.value
            )
            outlier_threshold = st.number_input(
                label="Outlier threshold (%)",
                min_value=1,
                value=outlier_threshold_default,
                help="Set the minimum number values required to flag outliers in the column.",
                key="outlier_threshold",
            )

            outlier_settings, valid_outlier = _validate_outlier_settings(
                {
                    "outlier_method": outlier_method,
                    "outlier_multiplier": outlier_multiplier,
                    "outlier_threshold": outlier_threshold,
                }
            )
            return enable_outliers, outlier_settings, valid_outlier
        else:
            return False, None, True


def _render_constraint_options() -> tuple[dict, bool]:
    """Render constraint bounds options UI.

    Returns
    -------
    tuple[dict, bool]
        Constraint settings dict and validation status.
    """
    with st.container(border=True):
        st.write("**Constraint Options:**")

        hc1, hc2 = st.columns(2)
        with hc1:
            hard_min = st.number_input(
                label="(OPTIONAL) Hard minimum",
                help="(OPTIONAL) Hard minimum value for outlier detection.",
                value=None,
            )
        with hc2:
            hard_max = st.number_input(
                label="(OPTIONAL) Hard maximum",
                help="(OPTIONAL) Hard maximum value for outlier detection.",
                value=None,
            )

        sc1, sc2 = st.columns(2)
        with sc1:
            soft_min = st.number_input(
                label="(OPTIONAL) Soft minimum",
                help="(OPTIONAL) Soft minimum value for outlier detection.",
                value=None,
            )
        with sc2:
            soft_max = st.number_input(
                label="(OPTIONAL) Soft maximum",
                help="(OPTIONAL) Soft maximum value for outlier detection.",
                value=None,
            )

        return _validate_constraint_settings(
            {
                "hard_min": hard_min,
                "soft_min": soft_min,
                "soft_max": soft_max,
                "hard_max": hard_max,
            }
        )


def _render_outlier_column_actions(
    project_id: str, page_name_id: str, numeric_columns: list[str]
) -> None:
    """Render the outlier column configuration UI.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    numeric_columns : list[str]
        List of numeric columns.
    """
    outlier_settings = duckdb_get_table(
        project_id,
        f"outliers_{page_name_id}",
        "logs",
    )

    os1, os2, _ = st.columns([0.4, 0.3, 0.3])
    with os1:
        st.button(
            "Add Outlier/Constraint Column",
            key="add_outlier_column",
            help="Add a new outlier column configuration.",
            width="stretch",
            type="primary",
            on_click=_add_outlier_column,
            args=(
                project_id,
                page_name_id,
                numeric_columns,
            ),
        )
    with os2:
        _delete_outlier_column(project_id, page_name_id, outlier_settings)

    if outlier_settings.is_empty():
        st.info(
            "Use the :material/add: button to add columns to check for outliers and the "
            ":material/delete: button to remove columns."
        )
    else:
        _render_outlier_settings_table(outlier_settings)


@st.dialog("Add Outlier & Constraint Column(s)", width="medium")
def _add_outlier_column(
    project_id: str, page_name_id: str, numeric_columns: list[str]
) -> None:
    """Dialog to add a new outlier column configuration.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    numeric_columns : list[str]
        List of numeric columns.
    """
    # Render search type selection
    search_type, pattern, outlier_cols, lock_cols_initial = (
        _render_search_type_selection(numeric_columns)
    )

    if outlier_cols:
        # Render grouping options
        group_cols, lock_cols = _render_column_grouping_options(
            outlier_cols, search_type
        )
        if lock_cols_initial is not None:
            lock_cols = lock_cols_initial

        # Render outlier options
        enable_outliers, outlier_settings, valid_outlier = _render_outlier_options()

        # Render constraint options
        constraint_settings, valid_constraint = _render_constraint_options()

        button_disabled = (
            not outlier_cols
            or (enable_outliers and not valid_outlier)
            or not valid_constraint
        )
        if st.button(
            "Add Outlier & Constraint Configuration",
            key="confirm_add_outlier_column",
            type="primary",
            width="stretch",
            disabled=button_disabled,
        ):
            _update_outlier_column_config(
                project_id,
                page_name_id,
                search_type,
                pattern,
                outlier_cols,
                group_cols,
                lock_cols,
                enable_outliers,
                outlier_settings,
                constraint_settings,
            )

            st.success("Outlier & Constraint configuration added successfully.")
            st.rerun()


def _validate_constraint_settings(
    constraint_settings: dict,
) -> tuple[ConstraintBounds | None, bool]:
    """Validate constraint settings using Pydantic model.

    Parameters
    ----------
    constraint_settings : dict[str, Any]
        Dictionary containing constraint settings.

    Returns
    -------
    tuple[ConstraintBounds | None, bool]
        Validated constraint settings and validation status.
    """
    try:
        return ConstraintBounds(**constraint_settings), True
    except ValidationError as e:
        user_message = _format_constraint_validation_error(e)
        st.error(user_message)
        return None, False


def _validate_outlier_settings(
    outlier_settings: dict,
) -> tuple[OutlierOptionsConfig | None, bool]:
    """Validate outlier settings using Pydantic model.

    Parameters
    ----------
    outlier_settings : dict[str, Any]
        Dictionary containing outlier settings.

    Returns
    -------
    tuple[OutlierOptionsConfig | None, bool]
        Validated outlier settings and validation status.
    """
    try:
        return OutlierOptionsConfig(**outlier_settings), True
    except ValidationError as e:
        user_message = _format_outlier_validation_error(e)
        st.error(user_message)
        return None, False


def _format_constraint_validation_error(e: ValidationError) -> str:
    """Convert Pydantic ValidationError to user-friendly message.

    Parameters
    ----------
    e : ValidationError
        Pydantic validation error.

    Returns
    -------
    str
        User-friendly error message.
    """
    errors = []
    for error in e.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        msg = error["msg"]

        # Customize messages based on error type
        if error["type"] == "float_not_finite":
            errors.append(
                f"• {field}: Value must be a finite number (not NaN or infinity)"
            )
        elif error["type"] == "value_error":
            errors.append(f"• {msg}")  # Your custom validation messages
        else:
            errors.append(f"• {field}: {msg}")

    return "Invalid constraint configuration:\n" + "\n".join(errors)


def _format_outlier_validation_error(e: ValidationError) -> str:
    """Convert Pydantic ValidationError to user-friendly message.

    Parameters
    ----------
    e : ValidationError
        Pydantic validation error.

    Returns
    -------
    str
        User-friendly error message.
    """
    errors = []
    for error in e.errors():
        field = " -> ".join(str(loc) for loc in error["loc"])
        msg = error["msg"]

        # Customize messages based on error type
        if error["type"] == "value_error.number.not_ge":
            errors.append(
                f"• {field}: Value must be greater than or equal to the minimum allowed."
            )
        elif error["type"] == "value_error.number.not_le":
            errors.append(
                f"• {field}: Value must be less than or equal to the maximum allowed."
            )
        else:
            errors.append(f"• {field}: {msg}")

    return "Invalid outlier configuration:\n" + "\n".join(errors)


def _update_outlier_column_config(
    project_id: str,
    page_name_id: str,
    search_type: str,
    pattern: str | None,
    outlier_cols: list[str],
    group_cols: bool,
    lock_cols: bool,
    outlier_enabled: bool,
    outlier_settings: OutlierOptionsConfig | None,
    constraint_settings: ConstraintBounds | None,
) -> None:
    """Update the outlier column configuration in the database.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    search_type : str
        Search type used.
    pattern : str | None
        Pattern for column matching.
    outlier_cols : list[str]
        Selected columns.
    group_cols : bool
        Whether to group columns.
    lock_cols : bool
        Whether to lock column selection.
    outlier_enabled : bool
        Whether outlier detection is enabled.
    outlier_settings : OutlierOptionsConfig | None
        Outlier detection settings.
    constraint_settings : ConstraintBounds | None
        Constraint bounds settings.
    """
    # get existing config
    existing_config = duckdb_get_table(
        project_id=project_id,
        alias=f"outliers_{page_name_id}",
        db_name="logs",
    )

    # Prepare new configurations
    new_config = {
        "search_type": search_type,
        "pattern": pattern,
        "column_name": [outlier_cols],
        "grouped_columns": group_cols,
        "locked": lock_cols,
        "outlier_enabled": outlier_enabled,
        "outlier_method": outlier_settings.outlier_method if outlier_settings else None,
        "outlier_multiplier": outlier_settings.outlier_multiplier
        if outlier_settings
        else None,
        "outlier_threshold": outlier_settings.outlier_threshold
        if outlier_settings
        else None,
        "hard_min": constraint_settings.hard_min if constraint_settings else None,
        "soft_min": constraint_settings.soft_min if constraint_settings else None,
        "soft_max": constraint_settings.soft_max if constraint_settings else None,
        "hard_max": constraint_settings.hard_max if constraint_settings else None,
    }

    schema = {
        "search_type": pl.Utf8,
        "pattern": pl.Utf8,
        "column_name": pl.List(pl.Utf8),
        "grouped_columns": pl.Boolean,
        "locked": pl.Boolean,
        "outlier_enabled": pl.Boolean,
        "outlier_method": pl.Utf8,
        "outlier_multiplier": pl.Float64,
        "outlier_threshold": pl.Int64,
        "hard_min": pl.Float64,
        "soft_min": pl.Float64,
        "soft_max": pl.Float64,
        "hard_max": pl.Float64,
    }

    # Append new configurations to existing polars DataFrame
    new_config_df = pl.DataFrame(new_config, schema=schema)
    if not existing_config.is_empty():
        formatted_existing_config = _ensure_column_formats(existing_config)
        updated_config = pl.concat(
            [formatted_existing_config, new_config_df], how="vertical"
        )
    else:
        updated_config = new_config_df

    # Save updated configurations back to the database
    duckdb_save_table(
        project_id,
        updated_config,
        f"outliers_{page_name_id}",
        db_name="logs",
    )


def _ensure_column_formats(
    outlier_settings: pl.DataFrame,
) -> pl.DataFrame:
    """Ensure correct data types for outlier settings DataFrame.

    Parameters
    ----------
    outlier_settings : pl.DataFrame
        Outlier settings configuration.

    Returns
    -------
    pl.DataFrame
        DataFrame with ensured data types.
    """
    return outlier_settings.with_columns(
        [
            pl.col("search_type").cast(pl.Utf8),
            pl.col("pattern").cast(pl.Utf8),
            pl.col("column_name").cast(pl.List(pl.Utf8)),
            pl.col("grouped_columns").cast(pl.Boolean),
            pl.col("locked").cast(pl.Boolean),
            pl.col("outlier_enabled").cast(pl.Boolean),
            pl.col("outlier_method").cast(pl.Utf8),
            pl.col("outlier_multiplier").cast(pl.Float64),
            pl.col("outlier_threshold").cast(pl.Int64),
            pl.col("hard_min").cast(pl.Float64),
            pl.col("soft_min").cast(pl.Float64),
            pl.col("soft_max").cast(pl.Float64),
            pl.col("hard_max").cast(pl.Float64),
        ]
    )


def _render_outlier_settings_table(outlier_settings: pl.DataFrame) -> None:
    """Render the outlier settings table in Streamlit.

    Parameters
    ----------
    outlier_settings : pl.DataFrame
        Outlier settings configuration.
    """
    with st.expander("Outlier & Constraint Column Settings", expanded=False):
        st.dataframe(
            outlier_settings,
            width="stretch",
            hide_index=True,
            column_config={
                "search_type": st.column_config.Column("Search Type"),
                "pattern": st.column_config.Column("Pattern"),
                "column_name": st.column_config.Column("Column Name(s)"),
                "grouped_columns": st.column_config.CheckboxColumn("Grouped Columns"),
                "locked": st.column_config.CheckboxColumn("Locked"),
                "outlier_enabled": st.column_config.CheckboxColumn("Outlier Enabled"),
                "outlier_method": st.column_config.Column("Outlier Method"),
                "outlier_multiplier": st.column_config.NumberColumn(
                    "Outlier Multiplier"
                ),
                "outlier_threshold": st.column_config.NumberColumn("Outlier Threshold"),
                "hard_min": st.column_config.NumberColumn("Hard Min"),
                "soft_min": st.column_config.NumberColumn("Soft Min"),
                "soft_max": st.column_config.NumberColumn("Soft Max"),
                "hard_max": st.column_config.NumberColumn("Hard Max"),
            },
        )


def _delete_outlier_column(
    project_id: str, page_name_id: str, outliers_settings: pl.DataFrame
) -> None:
    """Render delete outlier column button and handle deletion.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    outliers_settings : pl.DataFrame
        Current outlier settings.
    """
    with (
        st.popover(
            label=":material/delete: Delete outlier column",
            width="stretch",
        ),
    ):
        st.markdown("#### Remove outlier columns")

        if outliers_settings.is_empty():
            st.info("No outlier columns have been added yet. ")
        else:
            outliers_settings = outliers_settings.with_row_index().with_columns(
                (
                    pl.col("index").cast(pl.Utf8)
                    + " - "
                    + pl.col("search_type")
                    + " - "
                    + pl.col("pattern").fill_null("")
                ).alias("composite_index")
            )

            unique_index = (
                outliers_settings["composite_index"]
                .unique(maintain_order=True)
                .to_list()
            )

            selected_index = st.selectbox(
                label="Select outlier column to remove",
                options=unique_index,
                help="Select the outlier column to remove from the list.",
            )

            if st.button(
                label="Confirm deletion",
                type="primary",
                width="stretch",
                help="Click to confirm deletion of the selected outlier column.",
                key="confirm_delete_outlier_column",
                disabled=not selected_index,
            ):
                updated_settings = outliers_settings.filter(
                    pl.col("composite_index") != selected_index
                ).drop("composite_index")

                duckdb_save_table(
                    project_id,
                    updated_settings,
                    f"outliers_{page_name_id}",
                    "logs",
                )

                st.rerun()


# =============================================================================
# Main Report Function
# =============================================================================


def outliers_report(
    project_id: str,
    page_name_id: str,
    data: pl.DataFrame,
    setting_file: str,
    config: dict,
    survey_columns: ColumnByType,
) -> None:
    """Create a comprehensive outliers report.

    Parameters
    ----------
    project_id : str
        The project identifier.
    page_name_id : str
        Page name identifier.
    data : pd.DataFrame
        DataFrame containing the survey data.
    setting_file : str
        Path to settings file.
    config : dict
        Configuration dictionary.
    """
    # get column info
    categorical_columns = survey_columns.categorical_columns
    datetime_columns = survey_columns.datetime_columns
    numeric_columns = survey_columns.numeric_columns

    st.title("Outliers and Constraints Report")

    # Load settings
    config_settings = OutlierSettings(**config)
    outliers_settings = outliers_report_settings(
        setting_file, config_settings, categorical_columns, datetime_columns
    )

    # Outlier columns configuration
    st.subheader("Outlier/Constraint Columns Configuration")
    _render_outlier_column_actions(project_id, page_name_id, numeric_columns)

    # get outlier column config
    outliers_column_config = duckdb_get_table(
        project_id,
        f"outliers_{page_name_id}",
        "logs",
    )

    if outliers_column_config.is_empty():
        return

    # update lock columns if needed
    outliers_column_config = _update_unlocked_cols(
        outliers_column_config,
        categorical_columns,
    )

    # save updated config
    duckdb_save_table(
        project_id,
        outliers_column_config,
        f"outliers_{page_name_id}",
        db_name="logs",
    )

    # Show constraint violations
    st.write("---")
    st.title("Constraint Violations")

    # compute constraint violations
    constraint_violations = compute_constraint_violations(
        data,
        outliers_settings,
        outliers_column_config,
    )

    if constraint_violations.is_empty():
        st.info("No constraint violations detected.")

    else:
        # show constraint metrics
        _render_constraint_metrics(constraint_violations)

        # show constraint violations table
        st.subheader("Constraint Violations Details")
        _render_constraint_violations_table(
            data,
            constraint_violations,
            outliers_settings,
            setting_file,
        )

    # show outliers metrics
    st.write("---")
    st.title("Outliers")

    # Compute outliers
    outlier_data = compute_outlier_output(
        data,
        outliers_settings,
        outliers_column_config,
    )

    if outlier_data.is_empty():
        st.info("No outliers detected.")

    else:
        # show outlier metrics
        _render_outlier_metrics(outlier_data, outliers_settings)

        # show outlier details table
        st.subheader("Outlier Details")
        _render_outlier_table(
            data,
            outlier_data,
            outliers_settings,
            setting_file,
        )

        # show outlier column inspection
        st.subheader("Inspect Columns")

        _render_outlier_column_inspection(
            data,
            outlier_data,
            outliers_settings,
            setting_file,
        )
