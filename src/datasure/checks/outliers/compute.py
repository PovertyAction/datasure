"""Pure data-computation functions for the outliers module."""

import re
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go  # type: ignore
import polars as pl
import streamlit as st

from datasure.checks.outliers.models import (
    TAB_NAME,
    ConstraintMetrics,
    OutlierBounds,
    OutlierMethod,
    OutlierMetrics,
    OutlierMultipliers,
    OutlierSettings,
    OutlierStatistics,
    OutlierThresholds,
    SearchType,
)
from datasure.utils.dataframe_utils import safe_to_numeric
from datasure.utils.settings_utils import load_check_settings

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


def _compute_column_stats(
    df_polars: pl.DataFrame,
    outlier_cols: list[str],
    grouped_cols: bool,
    outlier_method: str,
    outlier_multiplier: float,
) -> tuple[OutlierStatistics, int]:
    """Compute outlier statistics for grouped columns.

    Parameters
    ----------
    df_polars : pl.DataFrame
        DataFrame containing the data (with survey_key and outlier columns).
    outlier_cols : list[str]
        List of columns to analyze.
    grouped_cols : bool
        Whether columns should be analyzed together.
    outlier_method : str
        Outlier detection method (IQR or SD).
    outlier_multiplier : float
        Multiplier for bounds calculation.

    Returns
    -------
    tuple[OutlierStatistics, int]
        Computed statistics and non-null count.
    """
    if len(outlier_cols) == 1 or grouped_cols:
        if len(outlier_cols) == 1:
            series = df_polars[outlier_cols[0]]
        else:
            series = pl.concat([df_polars[col] for col in outlier_cols])

        non_null_count = series.len() - series.null_count()
        stats = compute_outlier_stats_polars(
            series,
            outlier_type=outlier_method,
            multiplier=outlier_multiplier,
        )
        return stats, non_null_count

    # For non-grouped multiple columns, return None to signal per-column computation
    return None, 0


def _compute_single_column_stats(
    df_polars: pl.DataFrame,
    col: str,
    outlier_method: str,
    outlier_multiplier: float,
) -> tuple[OutlierStatistics, int]:
    """Compute outlier statistics for a single column.

    Parameters
    ----------
    df_polars : pl.DataFrame
        DataFrame containing the data.
    col : str
        Column name to analyze.
    outlier_method : str
        Outlier detection method.
    outlier_multiplier : float
        Multiplier for bounds calculation.

    Returns
    -------
    tuple[OutlierStatistics, int]
        Computed statistics and non-null count.
    """
    non_null_count = df_polars.height - df_polars[col].null_count()
    stats = compute_outlier_stats_polars(
        df_polars[col],
        outlier_type=outlier_method,
        multiplier=outlier_multiplier,
    )
    return stats, non_null_count


def _merge_outlier_results(
    outlier_results_list: list[pl.DataFrame],
    admin_data_polars: pl.DataFrame,
    survey_key: str,
) -> pl.DataFrame:
    """Merge outlier results with admin data.

    Parameters
    ----------
    outlier_results_list : list[pl.DataFrame]
        List of outlier result DataFrames.
    admin_data_polars : pl.DataFrame
        Admin data DataFrame.
    survey_key : str
        Survey key column name.

    Returns
    -------
    pl.DataFrame
        Merged results or empty DataFrame if no results.
    """
    if not outlier_results_list:
        return pl.DataFrame()

    outlier_results_polars = pl.concat(outlier_results_list)

    if admin_data_polars.is_empty():
        return outlier_results_polars

    return admin_data_polars.join(
        outlier_results_polars,
        on=survey_key,
        how="left",
    )


def _process_outlier_configs(
    data: pl.DataFrame,
    column_config: pl.DataFrame,
    survey_key: str,
) -> list[pl.DataFrame]:
    """Process all outlier configurations and return results.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing the survey data.
    column_config : pl.DataFrame
        DataFrame containing the outlier column configurations.
    survey_key : str
        Survey key column name.

    Returns
    -------
    list[pl.DataFrame]
        List of outlier result DataFrames.
    """
    outlier_results_list = []

    for row in column_config.iter_rows(named=True):
        if not row.get("outlier_enabled", False):
            continue

        results = _process_single_config(data, row, survey_key)
        outlier_results_list.extend(results)

    return outlier_results_list


def _process_single_config(
    data: pl.DataFrame,
    row: dict,
    survey_key: str,
) -> list[pl.DataFrame]:
    """Process a single outlier configuration row.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing the survey data.
    row : dict
        Configuration row from column_config.
    survey_key : str
        Survey key column name.

    Returns
    -------
    list[pl.DataFrame]
        List of outlier results for this configuration.
    """
    # Extract settings with defaults
    outlier_cols = _ensure_list(row.get("column_name", []))
    grouped_cols = row.get("grouped_columns", False)
    outlier_method = row.get("outlier_method", OutlierMethod.IQR.value)
    threshold = row.get("outlier_threshold", OutlierThresholds.IQR.value)
    outlier_multiplier = row.get("outlier_multiplier", OutlierMultipliers.IQR.value)

    # Create subset
    outlier_df_polars = data.select([survey_key, *outlier_cols])

    # Compute shared stats for single column or grouped columns
    shared_stats, shared_count = _compute_column_stats(
        outlier_df_polars,
        outlier_cols,
        grouped_cols,
        outlier_method,
        outlier_multiplier,
    )

    # Process each column
    results = []
    for col in outlier_cols:
        if shared_stats is not None:
            outlier_stats, non_null_count = shared_stats, shared_count
        else:
            outlier_stats, non_null_count = _compute_single_column_stats(
                outlier_df_polars, col, outlier_method, outlier_multiplier
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
        results.append(col_result)

    return results


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
    include_cols = _build_include_cols(
        survey_key,
        outlier_settings.survey_id,
        outlier_settings.survey_date,
        outlier_settings.enumerator,
        outlier_settings.team,
    )
    admin_data_polars = data.select(include_cols)

    # Process outlier settings
    outlier_results_list = _process_outlier_configs(data, column_config, survey_key)

    return _merge_outlier_results(outlier_results_list, admin_data_polars, survey_key)


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
