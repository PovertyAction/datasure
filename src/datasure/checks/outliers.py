"""Outliers detection module for survey data quality checks.

This module provides comprehensive outlier detection functionality with:
- Multiple detection methods (IQR, Standard Deviation)
- Polars-based optimizations for performance
- Pydantic validation for data integrity
- Modular, testable architecture
"""

import os
import re
from enum import Enum, IntEnum
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go  # type: ignore
import polars as pl
import seaborn as sns
import streamlit as st
from pydantic import (
    BaseModel,
    Field,
    ValidationError,
    field_validator,
    model_validator,
)

from datasure.utils import (
    duckdb_get_table,
    duckdb_save_table,
    get_check_config_settings,
    get_df_info,
    load_check_settings,
    save_check_settings,
    trigger_save,
)
from datasure.utils.onboarding_utils import demo_output_onboarding

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

    @model_validator(mode='after')
    def validate_bounds_hierarchy(self):
        """Validate the complete hierarchy of bounds."""
        bounds = [
            ('hard_min', self.hard_min),
            ('soft_min', self.soft_min),
            ('soft_max', self.soft_max),
            ('hard_max', self.hard_max)
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

class OutlierStatistics(BaseModel):
    """Complete statistical summary for outlier detection."""

    count: int = Field(ge=0, description="Number of non-null values")
    min_value: float
    max_value: float
    mean: float
    median: float
    sd: float = Field(ge=0, alias="std")
    iqr: float = Field(ge=0)
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
    survey_id: str | None = Field(None, description="Column name for survey ID", min_length=1)
    survey_date: str | None = Field(None, description="Column name for survey date", min_length=1)
    enumerator: str | None = Field(None, description="Column name for enumerator ID", min_length=1)
    team: str | None = Field(None, description="Column name for team", min_length=1)

# =============================================================================
# Settings and Configuration Functions
# =============================================================================

def load_default_settings(
    settings_file: str, config: OutlierSettings
) -> OutlierSettings:
    """Load the default settings for the outliers report.

    Parameters
    ----------
    project_id : str
        The project identifier.
    settings_file : str
        The settings file to load.
    page_num : int
        The page number of the report.

    Returns
    -------
    tuple
        A tuple containing (survey_id, enumerator, survey_key,
        display_cols, min_threshold).
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


def _should_expand_row(row: pd.Series) -> bool:
    """Check if a settings row should have its columns expanded.

    Parameters
    ----------
    row : pd.Series
        Settings row to check.

    Returns
    -------
    bool
        True if row should be expanded.
    """
    return row["search_type"] != SearchType.EXACT.value and not row["lock_cols"]


@st.cache_data
def update_unlocked_cols(
    outlier_settings: pd.DataFrame, col_names: list[str]
) -> pd.DataFrame:
    """Update column names for unlocked rows in outlier settings.

    Parameters
    ----------
    outlier_settings : pd.DataFrame
        DataFrame containing outlier settings.
    col_names : list[str]
        List of available column names.

    Returns
    -------
    pd.DataFrame
        Updated outlier settings with expanded column names.

    Raises
    ------
    ValueError
        If essential columns are missing or pattern is invalid.
    """
    essential_cols = ["outlier_cols", "lock_cols"]
    for col in essential_cols:
        if col not in outlier_settings.columns:
            raise ValueError(
                f"Essential column '{col}' is missing from outlier settings."
            )

    # Identify rows to expand
    outlier_settings["to_expand"] = outlier_settings.apply(_should_expand_row, axis=1)

    if outlier_settings["to_expand"].sum() == 0:
        return outlier_settings

    # Update unlocked rows
    for index, row in outlier_settings.iterrows():
        if row["to_expand"]:
            pattern = row["pattern"]
            if not pattern or not pattern.strip():
                raise ValueError(
                    f"Missing pattern for row {index}. Please provide a valid pattern."
                )

            new_col_names = expand_col_names(col_names, pattern, row["search_type"])
            outlier_settings.at[index, "outlier_cols"] = new_col_names

    return outlier_settings


def _validate_outlier_settings_input(
    outlier_cols: list[str],
    search_type: str,
    pattern: str | None,
    outlier_method: str,
    outlier_multiplier: float,
    soft_min: float | None,
    soft_max: float | None,
    lock_cols: bool | None,
    grouped_cols: bool | None,
) -> None:
    """Validate outlier settings input parameters.

    Parameters
    ----------
    All parameters to validate.

    Raises
    ------
    TypeError
        If input types are invalid.
    """
    if not isinstance(outlier_cols, list):
        raise TypeError("outlier_cols must be a list of column names.")
    if not isinstance(search_type, str):
        raise TypeError("search_type must be a string.")
    if pattern is not None and not isinstance(pattern, str):
        raise TypeError("pattern must be a string.")
    if not isinstance(outlier_method, str):
        raise TypeError("outlier_method must be a string.")
    if not isinstance(outlier_multiplier, (int, float)):  # noqa: UP038
        raise TypeError("outlier_multiplier must be a number.")
    if soft_min is not None and not isinstance(soft_min, (int, float)):  # noqa: UP038
        raise TypeError("soft_min must be a number or None.")
    if soft_max is not None and not isinstance(soft_max, (int, float)):  # noqa: UP038
        raise TypeError("soft_max must be a number or None.")
    if lock_cols is not None and not isinstance(lock_cols, bool):
        raise TypeError("lock_cols must be a boolean or None.")
    if grouped_cols is not None and not isinstance(grouped_cols, bool):
        raise TypeError("grouped_cols must be a boolean or None.")


@st.cache_data
def update_outlier_settings(
    project_id: str,
    label: str,
    search_type: str,
    outlier_cols: list[str],
    outlier_method: str,
    outlier_multiplier: float,
    grouped_cols: bool | None,
    pattern: str | None,
    lock_cols: bool | None,
    soft_min: float | None,
    soft_max: float | None,
) -> None:
    """Update the outlier settings based on user input.

    Parameters
    ----------
    project_id : str
        The project identifier.
    label : str
        Label for the settings.
    search_type : str
        Type of search to perform on the column names.
    outlier_cols : list[str]
        List of columns to check for outliers.
    outlier_method : str
        Outlier detection method.
    outlier_multiplier : float
        Multiplier for outlier detection.
    grouped_cols : bool | None
        Whether to group columns together.
    pattern : str | None
        Pattern to match against column names.
    lock_cols : bool | None
        Whether to lock the selected columns.
    soft_min : float | None
        Soft minimum value for outlier detection.
    soft_max : float | None
        Soft maximum value for outlier detection.

    Raises
    ------
    TypeError
        If input types are invalid.
    """
    # Validate inputs
    _validate_outlier_settings_input(
        outlier_cols,
        search_type,
        pattern,
        outlier_method,
        outlier_multiplier,
        soft_min,
        soft_max,
        lock_cols,
        grouped_cols,
    )

    # Get current settings
    logs = duckdb_get_table(
        project_id=project_id,
        alias=f"outliers_setting_logs_{label}",
        db_name="logs",
    ).to_pandas()

    # Create new settings entry
    new_settings = {
        "search_type": search_type,
        "pattern": pattern,
        "outlier_cols": outlier_cols,
        "lock_cols": lock_cols,
        "grouped_cols": grouped_cols,
        "outlier_method": outlier_method,
        "outlier_multiplier": outlier_multiplier,
        "soft_min": soft_min,
        "soft_max": soft_max,
    }

    if not logs.empty:
        logs = pd.concat([logs, pd.DataFrame([new_settings])], ignore_index=True)
        logs = logs.drop_duplicates(subset=["outlier_cols"], keep="last")
    else:
        logs = pd.DataFrame([new_settings])

    # Save updated settings
    duckdb_save_table(
        project_id=project_id,
        table_data=logs,
        alias=f"outliers_setting_logs_{label}",
        db_name="logs",
    )


# =============================================================================
# Core Statistics Computation (Polars-optimized)
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
        std=sd,
        iqr=iqr,
        lower_bound=bounds.lower_bound,
        upper_bound=bounds.upper_bound,
    )


def _build_outlier_expression(
    col: str,
    lower_bound: float,
    upper_bound: float,
    soft_min: float | None,
    soft_max: float | None,
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
    soft_min : float | None
        User-defined soft minimum.
    soft_max : float | None
        User-defined soft maximum.

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

    if soft_min is not None:
        outlier_expr = outlier_expr.when(pl.col(col) < soft_min).then(
            pl.lit(f"Value is below soft minimum {soft_min:.2f}")
        )
    if soft_max is not None:
        outlier_expr = outlier_expr.when(pl.col(col) > soft_max).then(
            pl.lit(f"Value is above soft maximum {soft_max:.2f}")
        )

    return outlier_expr.otherwise(pl.lit("no outlier"))


def _add_statistics_columns(
    col_df: pl.DataFrame,
    outlier_stats: OutlierStatistics,
    outlier_method: str,
    outlier_multiplier: float,
    soft_min: float | None,
    soft_max: float | None,
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
    soft_min : float | None
        Soft minimum threshold.
    soft_max : float | None
        Soft maximum threshold.
    col_name : str
        Name of the column being analyzed.

    Returns
    -------
    pl.DataFrame
        DataFrame with added statistics columns.
    """
    return col_df.with_columns(
        [
            pl.lit(outlier_stats.min_value).alias("min_value"),
            pl.lit(outlier_stats.max_value).alias("max_value"),
            pl.lit(outlier_stats.mean).alias("mean"),
            pl.lit(outlier_stats.median).alias("median"),
            pl.lit(outlier_stats.sd).alias("std"),
            pl.lit(outlier_stats.iqr).alias("iqr"),
            pl.lit(outlier_stats.lower_bound).alias("lower_bound"),
            pl.lit(outlier_stats.upper_bound).alias("upper_bound"),
            pl.lit(outlier_method).alias("outlier_method"),
            pl.lit(outlier_multiplier).alias("outlier_multiplier"),
            pl.lit(soft_min).alias("soft_min"),
            pl.lit(soft_max).alias("soft_max"),
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
    soft_min: float | None,
    soft_max: float | None,
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
    soft_min : float | None
        Soft minimum threshold.
    soft_max : float | None
        Soft maximum threshold.
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

    # Add outlier reason
    if non_null_count < min_threshold:
        col_df = col_df.with_columns(pl.lit("no outlier").alias("outlier reason"))
    else:
        # Vectorized outlier flagging
        outlier_expr = _build_outlier_expression(
            col,
            outlier_stats.lower_bound,
            outlier_stats.upper_bound,
            soft_min,
            soft_max,
        )
        col_df = col_df.with_columns(outlier_expr.alias("outlier reason"))

    # Add statistics columns
    col_df = _add_statistics_columns(
        col_df,
        outlier_stats,
        outlier_method,
        outlier_multiplier,
        soft_min,
        soft_max,
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
            "soft_min",
            "soft_max",
        ]
    )

    return col_df


def _get_default_threshold(outlier_method: str) -> int:
    """Get default threshold based on outlier method.

    Parameters
    ----------
    outlier_method : str
        The outlier detection method.

    Returns
    -------
    int
        Default threshold value.
    """
    return (
        OutlierThresholds.IQR.value
        if outlier_method == OutlierMethod.IQR.value
        else OutlierThresholds.SD.value
    )


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
    display_cols : list[str]
        User-selected display columns.
    survey_key : str
        Survey key column.
    survey_id : str | None
        Survey ID column.
    enumerator : str | None
        Enumerator column.

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


def compute_outlier_output(
    data: pl.DataFrame,
    outlier_settings: pl.DataFrame,
    config: OutlierSettings,
) -> pd.DataFrame:
    """Detect outliers in DataFrame based on settings (Polars-optimized).

    Parameters
    ----------
    df : pd.DataFrame
        DataFrame containing the survey data.
    outlier_settings : pd.DataFrame
        DataFrame containing the outlier settings.
    display_cols : list[str]
        Columns to display in output.
    min_threshold : float | None
        Minimum sample size for outlier detection.
    survey_key : str
        Column name for survey key.
    survey_id : str | None
        Column name for survey ID.
    enumerator : str | None
        Column name for enumerator ID.

    Returns
    -------
    pd.DataFrame
        DataFrame containing the outlier summary.

    Raises
    ------
    ValueError
        If DataFrame is empty.
    """
    if data.empty:
        raise ValueError("The DataFrame is empty. Please provide a valid DataFrame.")

    # Build include columns list
    survey_key = config.survey_key
    survey_id = config.survey_id
    survey_date = config.survey_date
    enumerator = config.enumerator
    team = config.team
    include_cols = _build_include_cols(survey_key, survey_id,
                                        survey_date,
                                        enumerator,
                                        team)

    # Convert to Polars
    admin_data_polars = data.select(include_cols)

    # Process outlier settings
    outlier_results_list = []

    for _, row in outlier_settings.iterrows():
        # Extract settings with defaults
        outlier_cols = _ensure_list(row.get("outlier_cols", []))
        grouped_cols = row.get("group_cols", False)
        outlier_method = row.get("outlier_method", OutlierMethod.IQR.value)
        threshold = row.get("outlier_threshold", OutlierThresholds.IQR.value)
        outlier_multiplier = row.get("outlier_multiplier", OutlierMultipliers.IQR.value)
        hard_min = row.get("hard_min", None)
        soft_min = row.get("soft_min", None)
        soft_max = row.get("soft_max", None)
        hard_max = row.get("hard_max", None)

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
                soft_min=soft_min,
                soft_max=soft_max,
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

        return merged_results.to_pandas()

    return pd.DataFrame()


# =============================================================================
# Legacy Pandas Functions (for backward compatibility)
# =============================================================================


@st.cache_data
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
        if dtype not in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, 
                         pl.UInt8, pl.UInt16, pl.UInt32, pl.UInt64,
                         pl.Float32, pl.Float64]:
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


@st.cache_data
def compute_outlier_stats(
    series: pd.Series, outlier_type: str | None, multiplier: float | None
) -> dict[str, Any]:
    """Compute outlier statistics for a Series (legacy Pandas version).

    Parameters
    ----------
    series : pd.Series
        The Series to compute statistics for.
    outlier_type : str | None
        The type of outlier detection method.
    multiplier : float | None
        The multiplier to use.

    Returns
    -------
    dict[str, Any]
        Dictionary containing computed statistics.

    Raises
    ------
    ValueError
        If series is empty or parameters are invalid.
    """
    if series.empty:
        raise ValueError("The Series is empty.")

    valid_types = [None, OutlierMethod.IQR.value, OutlierMethod.SD.value]
    if outlier_type not in valid_types:
        raise ValueError("Invalid outlier type. Use 'IQR' or 'SD'.")

    if multiplier is not None and multiplier <= 0:
        raise ValueError("Multiplier must be a positive number.")

    count = series.count()
    min_value = series.min()
    max_value = series.max()
    mean = series.mean()
    median = series.median()
    sd = series.std()
    iqr = series.quantile(0.75) - series.quantile(0.25)

    if outlier_type == OutlierMethod.SD.value:
        multiplier = multiplier or OutlierMultipliers.SD.value
        lower_bound = mean - (multiplier * sd)
        upper_bound = mean + (multiplier * sd)
    else:
        multiplier = multiplier or OutlierMultipliers.IQR.value
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lower_bound = q1 - (multiplier * iqr)
        upper_bound = q3 + (multiplier * iqr)

    return {
        "count": count,
        "min_value": min_value,
        "max_value": max_value,
        "mean": mean,
        "median": median,
        "sd": sd,
        "iqr": iqr,
        "lower_bound": lower_bound,
        "upper_bound": upper_bound,
    }


# =============================================================================
# Summary and Display Helper Functions
# =============================================================================


def compute_column_outlier_summary(
    outlier_data: pd.DataFrame, survey_key: str
) -> pd.DataFrame:
    """Compute a summary of outliers for each column.

    Parameters
    ----------
    outlier_data : pd.DataFrame
        DataFrame containing outlier data.
    survey_key : str
        Survey key column name.

    Returns
    -------
    pd.DataFrame
        Summary DataFrame with outlier counts per column.
    """
    if outlier_data.empty:
        return pd.DataFrame()

    outlier_summary = outlier_data.drop_duplicates(subset=["column name", survey_key])

    col_counts = outlier_summary["column name"].value_counts().reset_index()
    outlier_summary = outlier_summary.merge(col_counts, on="column name", how="left")

    outlier_summary["flagged as outlier"] = outlier_summary.apply(
        lambda row: 1 if row["outlier reason"] != "no outlier" else 0, axis=1
    )

    outlier_counts = (
        outlier_summary.groupby("column name")["flagged as outlier"].sum().reset_index()
    )
    outlier_counts.columns = ["column name", "outlier count"]

    outlier_summary = outlier_summary.merge(
        outlier_counts, on="column name", how="left"
    )

    outlier_summary = outlier_summary[
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
    ]

    return outlier_summary.drop_duplicates(subset=["column name"])


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


@st.cache_data
def display_outlier_metrics(
    outliers_data: pd.DataFrame,
    outlier_cols: list[str],
    survey_key: str,
    survey_id: str | None,
    enumerator: str | None,
) -> None:
    """Display metrics related to outliers in a summary format.

    Parameters
    ----------
    outliers_data : pd.DataFrame
        DataFrame containing outlier data.
    outlier_cols : list[str]
        List of columns checked for outliers.
    survey_key : str
        Survey key column name.
    survey_id : str | None
        Survey ID column name.
    enumerator : str | None
        Enumerator column name.
    """
    st.title("Outlier Summary")

    outlier_cols_count = len(outlier_cols)
    total_outliers = outliers_data[
        outliers_data["outlier reason"] != "no outlier"
    ].shape[0]
    at_least_one_outlier = (
        outliers_data["column name"].nunique() if not outliers_data.empty else 0
    )
    total_enumerators = (
        outliers_data[outliers_data["outlier reason"] != "no outlier"][
            enumerator
        ].nunique()
        if enumerator and not outliers_data.empty
        else 0
    )

    col1, col2, col3, col4 = st.columns(spec=4, border=True)

    col1.metric(
        label="Variables checked",
        value=f"{outlier_cols_count:,}",
        help="Columns checked for outlier values",
    )

    col2.metric(
        label="Outlier variables",
        value=f"{at_least_one_outlier:,}",
        help="Variables with at least one outlier",
    )

    col3.metric(
        label="Number of outliers",
        value=f"{total_outliers:,}",
        help="Total number of identified outliers",
    )

    if enumerator:
        col4.metric(
            label="Number of enumerators with outliers",
            value=f"{total_enumerators:,}",
            help="Number of enumerators with outliers flagged",
        )
    else:
        with col4:
            st.write("Number of enumerators")
            st.info(
                "Enumerator column is not selected. Go to the :material/settings: "
                "settings section above to select the enumerator column."
            )


# =============================================================================
# Visualization Functions
# =============================================================================


@st.cache_data
def create_violin_plot(data: pd.Series, title: str) -> go.Figure:
    """Create a violin plot using plotly.

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
        data=go.Violin(
            y=data,
            box_visible=True,
            line_color="black",
            meanline_visible=True,
            fillcolor="darkgreen",
            opacity=0.6,
            x0=title,
        )
    )


@st.cache_data
def plot_col_distribution(data: pd.DataFrame, col_name: str) -> go.Figure:
    """Plot the distribution of a specific column.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing the data.
    col_name : str
        Name of the column to plot.

    Returns
    -------
    go.Figure
        Plotly figure object with histogram.

    Raises
    ------
    ValueError
        If column doesn't exist or isn't numeric.
    """
    if col_name not in data.columns:
        raise ValueError(f"Column '{col_name}' does not exist in the DataFrame.")

    if not pd.api.types.is_numeric_dtype(data[col_name]):
        raise ValueError(
            f"Column '{col_name}' is not numeric. Cannot plot distribution."
        )

    fig = go.Figure(
        data=go.Histogram(
            x=data[col_name],
            nbinsx=30,
            marker_color="orange",
            opacity=0.7,
        )
    )
    fig.update_layout(
        title=f"Distribution of {col_name}",
        xaxis_title=col_name,
        yaxis_title="Frequency",
        template="plotly_white",
    )
    return fig


# =============================================================================
# Streamlit Display Functions
# =============================================================================


@demo_output_onboarding(TAB_NAME)
def display_outlier_output(outlier_data: pd.DataFrame) -> None:
    """Display the outlier output in a Streamlit app.

    Parameters
    ----------
    outlier_data : pd.DataFrame
        DataFrame containing outlier detection results.
    """
    outlier_data_disp = outlier_data[outlier_data["outlier reason"] != "no outlier"]

    if outlier_data_disp.empty:
        st.info("No outliers detected in the selected columns.")
        return

    st.dataframe(
        outlier_data_disp,
        width="stretch",
        hide_index=True,
        column_config={
            "column name": st.column_config.Column("Column Name"),
            "column value": st.column_config.Column(
                "Column Value",
                help="The value of the column that is flagged as an outlier.",
            ),
            "min_value": st.column_config.NumberColumn("Min Value", format="%.2f"),
            "max_value": st.column_config.NumberColumn("Max Value", format="%.2f"),
            "mean": st.column_config.NumberColumn("Mean", format="%.4f"),
            "std": st.column_config.NumberColumn("SD", format="%.4f"),
            "median": st.column_config.NumberColumn("Median", format="%.4f"),
            "iqr": st.column_config.NumberColumn("IQR", format="%.2f"),
            "outlier reason": st.column_config.Column(
                "Outlier Reason",
                help="Reason for flagging the value as an outlier.",
            ),
            "outlier_method": st.column_config.Column(
                "Outlier Method",
                help="Method used for outlier detection (IQR or SD).",
            ),
            "soft_min": st.column_config.NumberColumn("Soft Min"),
            "soft_max": st.column_config.NumberColumn("Soft Max"),
            "outlier_multiplier": st.column_config.NumberColumn("Outlier Multiplier"),
            "lower_bound": st.column_config.NumberColumn(
                "Lower Bound", format="%.2f", width="small"
            ),
            "upper_bound": st.column_config.NumberColumn(
                "Upper Bound", format="%.2f", width="small"
            ),
        },
    )


@demo_output_onboarding(TAB_NAME)
def display_outlier_column_summary(outlier_summary: pd.DataFrame) -> None:
    """Display the outlier summary in a Streamlit app.

    Parameters
    ----------
    outlier_summary : pd.DataFrame
        DataFrame containing outlier summary statistics.

    Raises
    ------
    ValueError
        If summary data is empty.
    """
    if outlier_summary.empty:
        raise ValueError(
            "No outlier summary data available. Please check the outlier "
            "settings and data."
        )

    cmap = sns.light_palette("pink", as_cmap=True)
    styler_limit = outlier_summary.shape[0] * outlier_summary.shape[1]
    pd.set_option("styler.render.max_elements", styler_limit)
    outlier_summary = outlier_summary.style.background_gradient(
        subset=["outlier count"], cmap=cmap
    )

    st.dataframe(
        outlier_summary,
        width="stretch",
        hide_index=True,
        column_config={
            "column name": st.column_config.Column("Column Name"),
            "count": st.column_config.NumberColumn("# of Values", format="%.0f"),
            "outlier count": st.column_config.NumberColumn(
                "# of Outliers", format="%.0f"
            ),
            "min_value": st.column_config.NumberColumn("Minimum Value", format="%.0f"),
            "max_value": st.column_config.NumberColumn("Maximum Value", format="%.0f"),
            "mean": st.column_config.NumberColumn("Mean", format="%.2f"),
            "median": st.column_config.NumberColumn("Median", format="%.2f"),
            "iqr": st.column_config.NumberColumn("Interquartile Range", format="%.2f"),
            "std": st.column_config.NumberColumn("Standard Deviation", format="%.2f"),
            "lower_bound": st.column_config.NumberColumn("Lower Bound", format="%.2f"),
            "upper_bound": st.column_config.NumberColumn("Upper Bound", format="%.2f"),
        },
    )


def _display_column_metrics(col_summary_row: dict[str, Any]) -> None:
    """Display metrics for a single column.

    Parameters
    ----------
    col_summary_row : dict[str, Any]
        Dictionary containing column summary statistics.
    """
    mu1, mu2, mu3, mu4, mu5 = st.columns(5, border=True)
    ml1, ml2, ml3, ml4, ml5 = st.columns(5, border=True)

    mu1.metric(
        label="# of Values",
        value=f"{col_summary_row['count']:,}",
        help="Total number of values in the column.",
    )
    mu2.metric(
        label="# of Outliers",
        value=f"{col_summary_row['outlier count']:,}",
        help="Total number of outliers in the column.",
    )
    mu3.metric(
        label="Minimum Value",
        value=f"{col_summary_row['min_value']:,.2f}",
        help="Minimum value in the column.",
    )
    mu4.metric(
        label="Maximum Value",
        value=f"{col_summary_row['max_value']:,.2f}",
        help="Maximum value in the column.",
    )
    mu5.metric(
        label="Mean",
        value=f"{col_summary_row['mean']:,.4f}",
        help="Mean value in the column.",
    )
    ml1.metric(
        label="Median",
        value=f"{col_summary_row['median']:,.2f}",
        help="Median value in the column.",
    )
    ml2.metric(
        label="Standard Deviation",
        value=f"{col_summary_row['std']:,.4f}",
        help="Standard deviation of the values in the column.",
    )
    ml3.metric(
        label="Interquartile Range",
        value=f"{col_summary_row['iqr']:,.2f}",
        help="Interquartile range of the values in the column.",
    )
    ml4.metric(
        label="Lower Bound",
        value=f"{col_summary_row['lower_bound']:,.2f}",
        help="Lower bound for outlier detection in the column.",
    )
    ml5.metric(
        label="Upper Bound",
        value=f"{col_summary_row['upper_bound']:,.2f}",
        help="Upper bound for outlier detection in the column.",
    )


@demo_output_onboarding(TAB_NAME)
def inspect_outliers_columns(
    data: pd.DataFrame,
    outlier_data: pd.DataFrame,
    col_summary: pd.DataFrame,
    outlier_cols: list[str],
    display_cols: list[str] | None,
    survey_key: str,
    survey_id: str,
    enumerator: str,
) -> None:
    """Inspect outlier columns in the DataFrame.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame containing the survey data.
    outlier_data : pd.DataFrame
        DataFrame containing outlier detection results.
    col_summary : pd.DataFrame
        DataFrame containing column summary statistics.
    outlier_cols : list[str]
        List of outlier columns to inspect.
    display_cols : list[str] | None
        Columns to display.
    survey_key : str
        Survey key column name.
    survey_id : str
        Survey ID column name.
    enumerator : str
        Enumerator column name.
    """
    if outlier_data.empty:
        st.info(
            "No outlier columns selected. Please select outlier columns to inspect."
        )
        return

    include_cols = []
    if display_cols:
        include_cols.extend(display_cols)
    for col in [survey_key, survey_id, enumerator]:
        if col and col not in include_cols:
            include_cols.append(col)

    ic1, ic2 = st.columns([0.2, 0.8])

    with ic1:
        selected_col = st.selectbox(
            label="Select outlier columns to inspect",
            options=outlier_cols,
            help="Select the outlier columns to inspect. "
            "You can only select one column at a time.",
        )

        if selected_col not in data.columns:
            raise ValueError(
                f"Selected column '{selected_col}' is not present in the data. "
                "Please select a valid column."
            )

    with ic2:
        inspect_display_cols = st.multiselect(
            label="Select columns to display",
            options=data.columns.tolist(),
            default=[selected_col],
            help="Select the columns to display in the inspection table.",
            disabled=not selected_col,
        )

        if inspect_display_cols:
            include_cols.extend(inspect_display_cols)

    if selected_col:
        if selected_col not in outlier_data["column name"].unique():
            st.warning(
                f"Column '{selected_col}' is not an outlier column. "
                "Please select a valid outlier column."
            )
            return

        include_cols.append(selected_col)
        include_cols = list(set(include_cols))

    # Merge with outlier data
    col_outlier_details = data[include_cols].copy()
    col_outlier_details = col_outlier_details.merge(
        outlier_data[[survey_key, "outlier reason"]],
        left_on=survey_key,
        right_on=survey_key,
        how="left",
    )

    # Reorder columns
    disp_cols = [
        col for col in include_cols if col not in [survey_key, "outlier reason"]
    ]
    col_outlier_details = col_outlier_details[
        [survey_key, "outlier reason", *disp_cols]
    ]

    # Display column metrics
    col_summary_row = col_summary[col_summary["column name"] == selected_col]
    if col_summary_row.empty:
        raise ValueError(
            f"No summary data found for column '{selected_col}'. "
            "Please check the outlier settings and data."
        )
    col_summary_row = col_summary_row.iloc[0].to_dict()

    _display_column_metrics(col_summary_row)
    st.write("---")

    dc1, dc2 = st.columns(2)
    with dc1:
        st.subheader(f"Distribution of {selected_col} values")
        fig = plot_col_distribution(
            data=col_outlier_details[[selected_col]], col_name=selected_col
        )
        st.plotly_chart(fig, width="stretch")

    with dc2:
        st.subheader(f"Violin plot of {selected_col} values")
        violin_fig = create_violin_plot(
            data=col_outlier_details[selected_col],
            title=selected_col,
        )
        st.plotly_chart(violin_fig, width="stretch")

    st.dataframe(
        col_outlier_details,
        width="stretch",
        hide_index=False,
    )


# =============================================================================
# Settings UI Functions
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
    settings_file: str, config: OutlierSettings, categorical_columns: list[str], datetime_columns: list[str]
) -> OutlierSettings:
    """Create a settings UI for outliers report configuration.

    This function creates the comprehensive Streamlit UI for configuring
    outlier detection settings. Due to its complexity (UI rendering),
    it maintains a higher cognitive complexity but is well-structured.

    Parameters
    ----------
    project_id : str
        The project identifier.
    data : pd.DataFrame
        DataFrame containing the survey data.
    settings_file : str
        Path to settings file.
    page_num : int
        Page number for configuration.
    label : str
        Label for the settings.

    Returns
    -------
    tuple
        Configuration values (display_cols, min_threshold, survey_id,
        survey_key, enumerator).
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
                    if default_survey_date
                    and default_survey_date in categorical_columns
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
                save_check_settings(
                    settings_file, TAB_NAME, {"enumerator": enumerator}
                )

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


def _render_outlier_column_actions(project_id: str, page_name_id: str, numeric_columns: list[str]) -> None:
    """Render the outlier column configuration UI."""
    outlier_settings = duckdb_get_table(
        project_id,
        f"outliers_{page_name_id}",
        "logs",
    )

    os1, os2, _ = st.columns([0.4, 0.3, 0.3])
    with os1:
        st.button("Add Outlier/Constraint Column",
                  key="add_outlier_column",
                  help="Add a new outlier column configuration.",
                  width="stretch",
                  type="primary",
                  on_click=_add_outlier_column,
                  args=(project_id, page_name_id, numeric_columns,))
    with os2:
        _delete_outlier_column(project_id, page_name_id, outlier_settings)

    if outlier_settings.is_empty():
        st.info(
            "Use the :material/add: button to add columns to check for outliers and the "
            ":material/delete: button to remove columns."
        )
    else:
        _render_outlier_settings_table(outlier_settings)


@st.dialog("Add Outlier & Constraint Column(s)", width="medium", on_dismiss="rerun")
def _add_outlier_column(project_id: str, page_name_id: str, numeric_columns: list[str]) -> None:
    """Dialog to add a new outlier column configuration."""
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

    outlier_cols = (
        outlier_cols_sel
        if search_type == SearchType.EXACT.value
        else outlier_cols_patt
    )

    if outlier_cols:
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

        with st.container(border=True):
            st.write("**Outlier Options:**")
            enable_outliers = st.toggle("Enable Outlier Checks", key="enable_coutlier", value=True)
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

                outlier_threshold_default = OutlierThresholds.SD.value if outlier_method == OutlierMethod.SD.value else OutlierThresholds.IQR.value
                outlier_threshold = st.number_input(
                    label="Outlier threshold (%)",
                    min_value=1,
                    value=outlier_threshold_default,
                    help="Set the minimum number values required to flag outliers in the column.",
                    key="outlier_threshold",
                )

                outlier_settings, valid_outlier = _validate_outlier_settings({
                    "outlier_method": outlier_method,
                    "outlier_multiplier": outlier_multiplier,
                    "outlier_threshold": outlier_threshold,
                })
            else:
                outlier_settings, valid_outlier = None, True

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

            constraint_settings, valid_constraint = _validate_constraint_settings({
                "hard_min": hard_min,
                "soft_min": soft_min,
                "soft_max": soft_max,
                "hard_max": hard_max,
            })

        button_disabled = not outlier_cols or (enable_outliers and not valid_outlier) or not valid_constraint
        if st.button("Add Outlier & Constraint Configuration",
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

def _validate_constraint_settings(
    constraint_settings: dict
) -> tuple[ConstraintBounds | None, bool]:
    """Validate constraint settings using Pydantic model.

    Parameters
    ----------
    constraint_settings : dict[str, Any]
        Dictionary containing constraint settings.

    Returns
    -------
    ConstraintBounds
        Validated constraint settings.

    Raises
    ------
    ValidationError
        If validation fails.
    """
    try:
        return ConstraintBounds(
            **constraint_settings
        ), True
    except ValidationError as e:
        user_message = _format_constraint_validation_error(e)
        st.error(user_message)
        return None, False

def _validate_outlier_settings(
    outlier_settings: dict
) -> tuple[OutlierOptionsConfig | None, bool]:
    """Validate outlier settings using Pydantic model.

    Parameters
    ----------
    outlier_settings : dict[str, Any]
        Dictionary containing outlier settings.

    Returns
    -------
    OutlierOptionsConfig
        Validated outlier settings.

    Raises
    ------
    ValidationError
        If validation fails.
    """
    try:
        return OutlierOptionsConfig(
            **outlier_settings
        ), True
    except ValidationError as e:
        user_message = _format_outlier_validation_error(e)
        st.error(user_message)
        return None, False

def _format_constraint_validation_error(e: ValidationError) -> str:
    """Convert Pydantic ValidationError to user-friendly message."""
    errors = []
    for error in e.errors():
        field = " -> ".join(str(loc) for loc in error['loc'])
        msg = error['msg']

        # Customize messages based on error type
        if error['type'] == 'float_not_finite':
            errors.append(f"• {field}: Value must be a finite number (not NaN or infinity)")
        elif error['type'] == 'value_error':
            errors.append(f"• {msg}")  # Your custom validation messages
        else:
            errors.append(f"• {field}: {msg}")

    return "Invalid constraint configuration:\n" + "\n".join(errors)

def _format_outlier_validation_error(e: ValidationError) -> str:
    """Convert Pydantic ValidationError to user-friendly message."""
    errors = []
    for error in e.errors():
        field = " -> ".join(str(loc) for loc in error['loc'])
        msg = error['msg']

        # Customize messages based on error type
        if error['type'] == 'value_error.number.not_ge':
            errors.append(f"• {field}: Value must be greater than or equal to the minimum allowed.")
        elif error['type'] == 'value_error.number.not_le':
            errors.append(f"• {field}: Value must be less than or equal to the maximum allowed.")
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
    """Update the outlier column configuration in the database."""
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
        "column_name": outlier_cols,
        "grouped_columns": group_cols,
        "locked": lock_cols,
        "outlier_enabled": outlier_enabled,
        "outlier_method": outlier_settings.outlier_method if outlier_settings else None,
        "outlier_multiplier": outlier_settings.outlier_multiplier if outlier_settings else None,
        "outlier_threshold": outlier_settings.outlier_threshold if outlier_settings else None,
        "hard_min": constraint_settings.hard_min if constraint_settings else None,
        "soft_min": constraint_settings.soft_min if constraint_settings else None,
        "soft_max": constraint_settings.soft_max if constraint_settings else None,
        "hard_max": constraint_settings.hard_max if constraint_settings else None,
    }
    # Append new configurations to existing polars DataFrame
    new_config_df = pl.DataFrame(new_config)
    if not existing_config.is_empty():
        updated_config = pl.concat([existing_config, new_config_df], how="vertical")
    else:
        updated_config = new_config_df

    # Save updated configurations back to the database
    duckdb_save_table(
        project_id,
        updated_config,
        f"outliers_{page_name_id}",
        db_name="logs",
    )

def _render_outlier_settings_table(outlier_settings: pl.DataFrame) -> None:
    """Render the outlier settings table in Streamlit."""
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
                "outlier_multiplier": st.column_config.NumberColumn("Outlier Multiplier"),
                "outlier_threshold": st.column_config.NumberColumn("Outlier Threshold"),
                "hard_min": st.column_config.NumberColumn("Hard Min"),
                "soft_min": st.column_config.NumberColumn("Soft Min"),
                "soft_max": st.column_config.NumberColumn("Soft Max"),
                "hard_max": st.column_config.NumberColumn("Hard Max"),
            },
        )

def _delete_outlier_column(project_id: str, page_name_id: str, outliers_settings: pl.DataFrame) -> None:
    """Render delete outlier column button and handle deletion."""
    with (st.popover(
            label=":material/delete: Delete outlier column",
            width="stretch",
            ),
        ):
            st.markdown("#### Remove outlier columns")

            if outliers_settings.is_empty():
                st.info(
                    "No outlier columns have been added yet. "
                )
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

                unique_index = outliers_settings["composite_index"].unique(maintain_order=True).to_list()

                selected_index = st.selectbox(
                    label="Select outlier column to remove",
                    options=unique_index,
                    help="Select the outlier column to remove from the list.",
                )

                if selected_index:
                    confirm_delete = st.button(
                        label="Confirm deletion",
                        type="primary",
                        width="stretch",
                    )
                    if confirm_delete:
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
    project_id: str, page_name_id: str, data: pd.DataFrame, setting_file: str, config: dict
) -> None:
    """Create a comprehensive outliers report.

    Parameters
    ----------
    project_id : str
        The project identifier.
    data : pd.DataFrame
        DataFrame containing the survey data.
    setting_file : str
        Path to settings file.
    page_num : int
        Page number for configuration.
    """
    # get column info
    _, string_columns, numeric_columns, datetime_columns, _ = get_df_info(
            data, cols_only=True
        )

    string_numeric_cols = list(set(string_columns + numeric_columns))

    # Load settings
    config_settings = OutlierSettings(**config)
    outliers_settings = outliers_report_settings(
        setting_file, config_settings, string_numeric_cols, datetime_columns
    )

    # Outlier columns configuration
    st.markdown("### Outlier/Constraint Columns Configuration")
    _render_outlier_column_actions(project_id, page_name_id, string_numeric_cols)

    # Compute outliers
    outlier_data = compute_outlier_output(
        data,
        outliers_settings,
        config_settings
    )
