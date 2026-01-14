"""Summary report module for survey data analytics.

This module provides comprehensive summary functionality with:
- Submission tracking and metrics
- Progress monitoring against targets
- Data quality assessment
- Polars-based optimizations for performance
- Pydantic validation for data integrity
"""

from datetime import date as Date
from datetime import datetime, timedelta
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import plotly.express as px
import polars as pl
import seaborn as sns
import streamlit as st
from dateutil.relativedelta import relativedelta
from pydantic import BaseModel, Field, field_validator

from datasure.utils.chart_utils import donut_chart2
from datasure.utils.dataframe_utils import ColumnByType
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

TAB_NAME: str = "summary"


# =============================================================================
# Pydantic Models for Data Validation
# =============================================================================


class SummarySettings(BaseModel):
    """Settings configuration for the summary report with validation."""

    survey_id: str | None = None
    survey_date: str | None = None
    survey_target: int | None = Field(None, ge=0)

    @field_validator("survey_target")
    @classmethod
    def validate_target(cls, v: int | None) -> int | None:
        """Validate that target is non-negative if provided.

        Parameters
        ----------
        v : int | None
            Target value to validate.

        Returns
        -------
        int | None
            Validated target value.

        Raises
        ------
        ValueError
            If target is negative.
        """
        if v is not None and v < 0:
            raise ValueError("Target submissions must be non-negative")
        return v


class SubmissionMetrics(BaseModel):
    """Metrics for submission analysis with validation."""

    first_submission_date: Date | None = None
    last_submission_date: Date | None = None
    today_count: int = Field(ge=0)
    this_week_count: int = Field(ge=0)
    this_month_count: int = Field(ge=0)
    total_count: int = Field(ge=0)
    today_delta_pct: float = 0.0
    this_week_delta_pct: float = 0.0
    this_month_delta_pct: float = 0.0
    submissions_by_date: pd.DataFrame = Field(default_factory=pd.DataFrame)

    class Config:
        """Pydantic config."""

        arbitrary_types_allowed = True


class ProgressMetrics(BaseModel):
    """Metrics for progress tracking with validation."""

    progress_pct: float = Field(ge=0.0)
    avg_per_day: float = Field(ge=0.0)
    avg_per_week: float = Field(ge=0.0)
    avg_per_month: float = Field(ge=0.0)


class DataSummaryMetrics(BaseModel):
    """Metrics for data summary with validation."""

    string_columns_count: int = Field(ge=0)
    numeric_columns_count: int = Field(ge=0)
    date_columns_count: int = Field(ge=0)
    total_columns_count: int = Field(ge=0)

    @field_validator("total_columns_count")
    @classmethod
    def validate_total(cls, v: int, info: Any) -> int:
        """Validate that total equals sum of type counts.

        Parameters
        ----------
        v : int
            Total count value.
        info : Any
            Pydantic validation info.

        Returns
        -------
        int
            Validated total count.

        Raises
        ------
        ValueError
            If total doesn't match sum of individual counts.
        """
        if hasattr(info, "data"):
            expected = (
                info.data.get("string_columns_count", 0)
                + info.data.get("numeric_columns_count", 0)
                + info.data.get("date_columns_count", 0)
            )
            if v != expected:
                raise ValueError(
                    "Total columns count must equal sum of string, numeric, and date columns counts"
                )
        return v


class DataQualityMetrics(BaseModel):
    """Metrics for data quality assessment with validation."""

    duplicates_pct: float | None = Field(None, ge=0.0, le=100.0)
    outliers_pct: float = Field(ge=0.0, le=100.0)
    missing_pct: float = Field(ge=0.0, le=100.0)
    backcheck_error_pct: float = Field(ge=0.0, le=100.0)


# =============================================================================
# Date Range Calculation Helpers
# =============================================================================


class DateRangeCalculator:
    """Helper class for calculating date ranges for time-based filtering."""

    @staticmethod
    def get_today() -> Date:
        """Get today's date.

        Returns
        -------
        Date
            Today's date.
        """
        return datetime.now().date()

    @staticmethod
    def get_yesterday() -> Date:
        """Get yesterday's date.

        Returns
        -------
        Date
            Yesterday's date.
        """
        return (datetime.now() - timedelta(days=1)).date()

    @staticmethod
    def get_week_start(weeks_ago: int = 0) -> Date:
        """Get the start date for a week.

        Parameters
        ----------
        weeks_ago : int, default=0
            Number of weeks to go back from today (0 = current week).

        Returns
        -------
        Date
            Start date of the specified week.
        """
        return (datetime.now() - timedelta(weeks=weeks_ago + 1)).date()

    @staticmethod
    def get_month_start(months_ago: int = 0) -> Date:
        """Get the start date for a month.

        Parameters
        ----------
        months_ago : int, default=0
            Number of months to go back from today (0 = current month).

        Returns
        -------
        Date
            Start date of the specified month.
        """
        today = datetime.now()
        target_month = today - relativedelta(months=months_ago + 1)
        return target_month.date()


# =============================================================================
# Utility Functions - Data Conversion
# =============================================================================


def _pandas_to_polars(df: pd.DataFrame) -> pl.DataFrame:
    """Convert pandas DataFrame to Polars DataFrame.

    Parameters
    ----------
    df : pd.DataFrame
        Input pandas dataframe.

    Returns
    -------
    pl.DataFrame
        Converted Polars dataframe.
    """
    return pl.from_pandas(df)


def _polars_to_pandas(df: pl.DataFrame) -> pd.DataFrame:
    """Convert Polars DataFrame to pandas DataFrame.

    Parameters
    ----------
    df : pl.DataFrame
        Input Polars dataframe.

    Returns
    -------
    pd.DataFrame
        Converted pandas dataframe.
    """
    return df.to_pandas()


# Public API wrappers for backward compatibility
pandas_to_polars = _pandas_to_polars
polars_to_pandas = _polars_to_pandas


# =============================================================================
# Data Validation and Preparation Functions
# =============================================================================


def _validate_and_convert_date_column(
    data: pl.DataFrame, date_column: str
) -> pl.DataFrame:
    """Validate and convert a column to date format.

    Parameters
    ----------
    data : pl.DataFrame
        Input dataframe.
    date_column : str
        Name of the date column to validate and convert.

    Returns
    -------
    pl.DataFrame
        Dataframe with only the date column, converted to date type.

    Raises
    ------
    ValueError
        If the column cannot be converted to date.
    """
    try:
        # Check if column exists
        if date_column not in data.columns:
            raise ValueError(f"Column {date_column} not found in dataframe")  # noqa: TRY301

        # Try to cast to date type, selecting only the date column
        df = data.select(
            pl.col(date_column).cast(pl.Date, strict=False).alias(date_column)
        )
        return df  # noqa: TRY300
    except Exception as e:
        raise ValueError(
            f"Column {date_column} cannot be converted to date: {e}"
        ) from e


def _prepare_date_data(
    data: pl.DataFrame, date_column: str
) -> tuple[pl.DataFrame, int]:
    """Prepare date data by converting to date and handling missing values.

    Parameters
    ----------
    data : pl.DataFrame
        Input dataframe.
    date_column : str
        Name of the date column.

    Returns
    -------
    tuple[pl.DataFrame, int]
        Tuple of (processed dataframe, missing date count).
    """
    # Convert to date if needed
    df = _validate_and_convert_date_column(data, date_column)

    # Count missing values
    missing_count = df.select(pl.col(date_column).is_null().sum()).item()

    # Drop missing values
    df = df.filter(pl.col(date_column).is_not_null())

    return df, missing_count


# Public API wrappers for backward compatibility
validate_and_convert_date_column = _validate_and_convert_date_column
prepare_date_data = _prepare_date_data


# =============================================================================
# Submission Metrics - Computation Functions
# =============================================================================


def _calculate_submission_count(
    df: pl.DataFrame,
    date_column: str,
    start_date: Date | None,
    end_date: Date | None = None,
) -> int:
    """Calculate submission count within a date range.

    Parameters
    ----------
    df : pl.DataFrame
        Dataframe with date column.
    date_column : str
        Name of the date column.
    start_date : Date | None
        Start date for filtering (inclusive).
    end_date : Date | None, default=None
        End date for filtering (exclusive). If None, no upper bound.

    Returns
    -------
    int
        Count of submissions in the date range.
    """
    if start_date is None:
        return 0

    if end_date is None:
        filtered = df.filter(pl.col(date_column) >= start_date)
    else:
        filtered = df.filter(
            (pl.col(date_column) >= start_date) & (pl.col(date_column) < end_date)
        )

    return filtered.height


def _calculate_percentage_change(current: int, previous: int) -> float:
    """Calculate percentage change between two values.

    Parameters
    ----------
    current : int
        Current value.
    previous : int
        Previous value.

    Returns
    -------
    float
        Percentage change.
    """
    if previous == 0:
        return 0.0
    return ((current - previous) / previous) * 100


def _create_empty_submission_metrics(total_count: int = 0) -> SubmissionMetrics:
    """Create empty submission metrics for edge cases.

    Parameters
    ----------
    total_count : int, default=0
        Total submission count (for cases with missing dates).

    Returns
    -------
    SubmissionMetrics
        Empty metrics structure.
    """
    return SubmissionMetrics(
        first_submission_date=None,
        last_submission_date=None,
        today_count=0,
        this_week_count=0,
        this_month_count=0,
        total_count=total_count,
        today_delta_pct=0.0,
        this_week_delta_pct=0.0,
        this_month_delta_pct=0.0,
        submissions_by_date=pd.DataFrame(),
    )


# Public API wrappers
calculate_submission_count = _calculate_submission_count
calculate_percentage_change = _calculate_percentage_change


def calculate_submission_metrics(
    data: pl.DataFrame, date_column: str
) -> SubmissionMetrics:
    """Calculate comprehensive submission metrics using Polars.

    Parameters
    ----------
    data : pl.DataFrame
        The survey data.
    date_column : str
        The date column in the survey data.

    Returns
    -------
    SubmissionMetrics
        Structured metrics for submissions.
    """
    # Handle empty data
    if data.height == 0:
        return _create_empty_submission_metrics()

    # Prepare and validate date data
    df, missing_count = _prepare_date_data(data, date_column)

    # Handle case where all dates are missing
    if df.height == 0:
        return _create_empty_submission_metrics(total_count=missing_count)

    # Calculate date boundaries
    first_date = df.select(pl.col(date_column).min()).item()
    last_date = df.select(pl.col(date_column).max()).item()

    # Get date ranges
    today = DateRangeCalculator.get_today()
    yesterday = DateRangeCalculator.get_yesterday()
    this_week_start = DateRangeCalculator.get_week_start(weeks_ago=0)
    last_week_start = DateRangeCalculator.get_week_start(weeks_ago=1)
    this_month_start = DateRangeCalculator.get_month_start(months_ago=0)
    last_month_start = DateRangeCalculator.get_month_start(months_ago=1)

    # Calculate current period counts
    today_count = df.filter(pl.col(date_column) == today).height
    this_week_count = _calculate_submission_count(df, date_column, this_week_start)
    this_month_count = _calculate_submission_count(df, date_column, this_month_start)

    # Calculate previous period counts for deltas
    yesterday_count = df.filter(pl.col(date_column) == yesterday).height
    last_week_count = _calculate_submission_count(
        df, date_column, last_week_start, this_week_start
    )
    last_month_count = _calculate_submission_count(
        df, date_column, last_month_start, this_month_start
    )

    # Calculate percentage changes
    today_delta = _calculate_percentage_change(today_count, yesterday_count)
    this_week_delta = _calculate_percentage_change(this_week_count, last_week_count)
    this_month_delta = _calculate_percentage_change(this_month_count, last_month_count)

    # Calculate submissions by date
    submissions_by_date_pl = (
        df.group_by(date_column).agg(pl.len().alias("submissions")).sort(date_column)
    )

    # Convert to pandas for compatibility with Plotly
    submissions_by_date = _polars_to_pandas(submissions_by_date_pl)

    return SubmissionMetrics(
        first_submission_date=first_date,
        last_submission_date=last_date,
        today_count=today_count,
        this_week_count=this_week_count,
        this_month_count=this_month_count,
        total_count=data.height,
        today_delta_pct=today_delta,
        this_week_delta_pct=this_week_delta,
        this_month_delta_pct=this_month_delta,
        submissions_by_date=submissions_by_date,
    )


@st.cache_data
def compute_summary_submissions(data: pl.DataFrame, date: str) -> tuple:
    """Compute submission metrics for the summary report.

    This function is maintained for backward compatibility with existing tests.

    Parameters
    ----------
    data : pd.DataFrame
        The survey data (pandas).
    date : str
        The date column in the survey data.

    Returns
    -------
    tuple
        A tuple containing:
        - first_submission_date: Date | None
        - last_submission_date: Date | None
        - submissions_today: int
        - submissions_this_week: int
        - submissions_this_month: int
        - submissions_total: int
        - submissions_today_delta: float
        - submissions_this_week_delta: float
        - submissions_this_month_delta: float
        - submissions_by_date: pd.DataFrame
    """
    # Convert to Polars for computation
    metrics = calculate_submission_metrics(data, date)

    return (
        metrics.first_submission_date,
        metrics.last_submission_date,
        metrics.today_count,
        metrics.this_week_count,
        metrics.this_month_count,
        metrics.total_count,
        metrics.today_delta_pct,
        metrics.this_week_delta_pct,
        metrics.this_month_delta_pct,
        metrics.submissions_by_date,
    )


# =============================================================================
# Progress Metrics - Computation Functions
# =============================================================================


def _create_empty_progress_metrics() -> ProgressMetrics:
    """Create empty progress metrics for edge cases.

    Returns
    -------
    ProgressMetrics
        Empty metrics structure.
    """
    return ProgressMetrics(
        progress_pct=0.0,
        avg_per_day=0.0,
        avg_per_week=0.0,
        avg_per_month=0.0,
    )


def calculate_progress_metrics(
    data: pl.DataFrame, date_column: str, target: int | None = None
) -> ProgressMetrics:
    """Calculate progress metrics for survey submissions using Polars.

    Parameters
    ----------
    data : pl.DataFrame
        The survey data.
    date_column : str
        The date column in the survey data.
    target : int | None, default=None
        The target number of submissions.

    Returns
    -------
    ProgressMetrics
        Structured progress metrics.

    Raises
    ------
    ValueError
        If target is not a positive integer.
    """
    # Validate target
    if target is not None and (not isinstance(target, int) or target < 0):
        raise ValueError("Target must be a positive integer")

    # Handle empty data
    if data.height == 0:
        return _create_empty_progress_metrics()

    # Prepare and validate date data
    df, _ = _prepare_date_data(data, date_column)

    # Handle case where all dates are missing
    if df.height == 0:
        return _create_empty_progress_metrics()

    # Calculate progress percentage
    progress_pct = (df.height / target * 100) if target else 0.0

    # Calculate average submissions per day
    daily_counts = df.group_by(date_column).agg(pl.len().alias("count"))
    avg_per_day = daily_counts.select(pl.col("count").mean()).item()

    # Calculate average submissions per week
    weekly_data = df.select(pl.col(date_column).dt.truncate("1w").alias("week"))
    weekly_counts = weekly_data.group_by("week").agg(pl.len().alias("count"))
    avg_per_week = weekly_counts.select(pl.col("count").mean()).item()

    # Calculate average submissions per month
    monthly_data = df.select(pl.col(date_column).dt.truncate("1mo").alias("month"))
    monthly_counts = monthly_data.group_by("month").agg(pl.len().alias("count"))
    avg_per_month = monthly_counts.select(pl.col("count").mean()).item()

    return ProgressMetrics(
        progress_pct=progress_pct,
        avg_per_day=avg_per_day,
        avg_per_week=avg_per_week,
        avg_per_month=avg_per_month,
    )


@st.cache_data
def compute_summary_progress(
    data: pl.DataFrame, date: str, target: int | None = None
) -> tuple:
    """Compute progress metrics for the summary report.

    This function is maintained for backward compatibility with existing tests.

    Parameters
    ----------
    data : pd.DataFrame
        The survey data (pandas).
    date : str
        The date column in the survey data.
    target : int | None, default=None
        The target number of submissions.

    Returns
    -------
    tuple
        A tuple containing:
        - progress: float
        - average_submission_per_day: float
        - average_submission_per_week: float
        - average_submission_per_month: float

    Raises
    ------
    ValueError
        If target is not a positive integer.
    """
    metrics = calculate_progress_metrics(data, date, target)
    return (
        metrics.progress_pct,
        metrics.avg_per_day,
        metrics.avg_per_week,
        metrics.avg_per_month,
    )


# =============================================================================
# Progress by Column - Computation Functions
# =============================================================================


def _determine_auto_time_period(total_submissions: int) -> str:
    """Determine the best time period based on submission count.

    Parameters
    ----------
    total_submissions : int
        Total number of submissions.

    Returns
    -------
    str
        Time period ('Daily', 'Weekly', or 'Monthly').
    """
    if total_submissions < 20:
        return "Daily"
    elif total_submissions < 140:
        return "Weekly"
    else:
        return "Monthly"


# Public API wrapper
determine_auto_time_period = _determine_auto_time_period


@st.cache_data
def compute_summary_progress_by_col(
    data: pl.DataFrame,
    date: str,
    progress_by_col: str,
    progress_time_period: str,
) -> tuple:
    """Compute progress metrics grouped by a column.

    This function is maintained for backward compatibility with existing tests.

    Parameters
    ----------
    data : pd.DataFrame
        The survey data (pandas).
    date : str
        The date column in the survey data.
    progress_by_col : str
        The column to compute progress by.
    progress_time_period : str
        The time period to compute progress by ('Auto', 'Daily', 'Weekly', 'Monthly').

    Returns
    -------
    tuple
        A tuple containing:
        - progress_data: pd.DataFrame (pivoted progress data)
        - vmin_val: float (minimum value for heatmap)
        - vmax_val: float (maximum value for heatmap)
        - format_cols: list (columns for formatting)
    """
    # Handle empty data
    if data.is_empty():
        return pd.DataFrame(), 0, 0, []

    # Determine time period
    if progress_time_period == "Auto":
        time_period = _determine_auto_time_period(data.height)
    else:
        time_period = progress_time_period

    # Select relevant columns
    progress_data = data.select([date, progress_by_col])

    # Validate and convert date column
    try:
        progress_data = progress_data.with_columns(
            pl.col(date).cast(pl.Date, strict=False).alias(date)
        )
    except Exception as e:
        raise ValueError(f"Column {date} is not a datetime column: {e}") from e

    # Create time period aggregation with user-friendly formatting
    if time_period == "Daily":
        # Format as "Feb 05, 2026"
        progress_data = progress_data.with_columns(
            pl.col(date).dt.strftime("%b %d, %Y").alias("time period")
        )
    elif time_period == "Weekly":
        # Calculate week start and end dates for user-friendly display
        # Default week starts on Monday (offset 1)
        offset = 1

        # Calculate the week start date (beginning of the week containing this date)
        # weekday() returns 0=Monday, 6=Sunday
        progress_data = progress_data.with_columns(
            [
                # Calculate days since the start of the week
                ((pl.col(date).dt.weekday() - offset + 7) % 7).alias(
                    "_days_since_week_start"
                ),
            ]
        )

        # Calculate week_start_date by subtracting days_since_week_start
        progress_data = progress_data.with_columns(
            [
                (
                    pl.col(date) - pl.duration(days=pl.col("_days_since_week_start"))
                ).alias("_week_start"),
                (
                    pl.col(date)
                    - pl.duration(days=pl.col("_days_since_week_start"))
                    + pl.duration(days=6)
                ).alias("_week_end"),
            ]
        )

        # Format as "Feb 02, 2025 to Feb 08, 2025"
        progress_data = progress_data.with_columns(
            (
                pl.col("_week_start").dt.strftime("%b %d, %Y")
                + " to "
                + pl.col("_week_end").dt.strftime("%b %d, %Y")
            ).alias("time period")
        )
    else:  # Monthly
        # Format as "February 2025"
        progress_data = progress_data.with_columns(
            pl.col(date).dt.strftime("%B %Y").alias("time period")
        )

    # Aggregate by time period and progress column
    progress_data = progress_data.group_by(["time period", progress_by_col]).agg(
        pl.len().alias("count")
    )

    # Pivot the data
    # Convert to pandas for pivoting (Polars pivot is still evolving)
    progress_pd = _polars_to_pandas(progress_data)
    progress_pd = progress_pd.pivot(
        index=progress_by_col, columns="time period", values="count"
    ).fillna(0)

    # Calculate heatmap range
    if not progress_pd.empty:
        vmin_val = progress_pd.min().min()
        vmax_val = progress_pd.max().max()
        format_cols = progress_pd.columns
    else:
        vmin_val = 0
        vmax_val = 0
        format_cols = []

    return progress_pd, vmin_val, vmax_val, format_cols


# =============================================================================
# Data Summary - Computation Functions
# =============================================================================


def calculate_data_summary_metrics(data: pl.DataFrame) -> DataSummaryMetrics:
    """Calculate data summary metrics using Polars.

    Parameters
    ----------
    data : pl.DataFrame
        The survey data.

    Returns
    -------
    DataSummaryMetrics
        Structured data summary metrics.
    """
    # Count columns by type
    string_cols = 0
    numeric_cols = 0
    date_cols = 0

    for dtype in data.dtypes:
        if dtype in [pl.Utf8, pl.Categorical]:
            string_cols += 1
        elif dtype in [pl.Int8, pl.Int16, pl.Int32, pl.Int64, pl.Float32, pl.Float64]:
            numeric_cols += 1
        elif dtype in [pl.Date, pl.Datetime]:
            date_cols += 1

    return DataSummaryMetrics(
        string_columns_count=string_cols,
        numeric_columns_count=numeric_cols,
        date_columns_count=date_cols,
        total_columns_count=len(data.columns),
    )


@st.cache_data
def compute_summary_data_summary(data: pl.DataFrame) -> tuple:
    """Compute data summary metrics.

    This function is maintained for backward compatibility.

    Parameters
    ----------
    data : pd.DataFrame
        The survey data (pandas).

    Returns
    -------
    tuple
        A tuple containing column counts by type.
    """
    metrics = calculate_data_summary_metrics(data)
    return (
        metrics.string_columns_count,
        metrics.numeric_columns_count,
        metrics.date_columns_count,
        metrics.total_columns_count,
    )


# =============================================================================
# Data Quality - Computation Functions
# =============================================================================


def calculate_data_quality_metrics(
    data: pl.DataFrame, survey_id: str | None
) -> DataQualityMetrics:
    """Calculate data quality metrics using Polars.

    Parameters
    ----------
    data : pl.DataFrame
        The survey data.
    survey_id : str | None
        The survey ID column in the survey data.

    Returns
    -------
    DataQualityMetrics
        Structured data quality metrics.
    """
    # Calculate duplicates percentage
    if survey_id and survey_id in data.columns:
        total_rows = data.height
        unique_rows = data.select(pl.col(survey_id)).unique().height
        duplicates_pct = (
            ((total_rows - unique_rows) / total_rows * 100) if total_rows > 0 else 0.0
        )
    else:
        duplicates_pct = None

    # Calculate missing percentage
    if data.height > 0:
        null_counts = data.null_count()
        total_cells = data.height * len(data.columns)
        missing_pct = (
            (null_counts.sum_horizontal().item() / total_cells * 100)
            if total_cells > 0
            else 0.0
        )
    else:
        missing_pct = 0.0

    # Placeholder values for future implementation
    outliers_pct = 0.0
    backcheck_error_pct = 0.0

    return DataQualityMetrics(
        duplicates_pct=duplicates_pct,
        outliers_pct=outliers_pct,
        missing_pct=missing_pct,
        backcheck_error_pct=backcheck_error_pct,
    )


@st.cache_data
def compute_summary_data_quality(data: pl.DataFrame, survey_id: str | None) -> tuple:
    """Compute data quality metrics.

    This function is maintained for backward compatibility.

    Parameters
    ----------
    data : pd.DataFrame
        The survey data (pandas).
    survey_id : str | None
        The survey ID column in the survey data.

    Returns
    -------
    tuple
        A tuple containing data quality metrics.
    """
    metrics = calculate_data_quality_metrics(data, survey_id)
    return (
        metrics.duplicates_pct,
        metrics.outliers_pct,
        metrics.missing_pct,
        metrics.backcheck_error_pct,
    )


# =============================================================================
# Streamlit UI - Settings Configuration
# =============================================================================


@demo_output_onboarding(TAB_NAME)
def summary_settings(
    data: pl.DataFrame,
    setting_file: str,
    config: SummarySettings,
    survey_columns: ColumnByType,
) -> tuple:
    """Render settings UI and return selected settings.

    Parameters
    ----------
    data : pd.DataFrame
        The survey data (pandas).
    setting_file : str
        Path to the settings file.
    config : SummarySettings
        Configuration settings.

    Returns
    -------
    tuple
        A tuple containing (date_column, target, survey_id_column).
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for summary report")
        st.write("---")

        # Load defaults
        default_survey_id, default_date, default_target = (
            config.survey_id,
            config.survey_date,
            config.survey_target,
        )

        # Get column information
        datetime_columns = survey_columns.datetime_columns
        categorical_columns = survey_columns.categorical_columns

        st.markdown("#### Survey Identifiers")
        with st.container(border=True):
            si1, _, _ = st.columns(spec=3)
            # Survey ID selection
            with si1:
                id_col_options = categorical_columns
                default_survey_id_index = (
                    id_col_options.index(default_survey_id)
                    if default_survey_id and default_survey_id in id_col_options
                    else None
                )

                survey_id = st.selectbox(
                    label="Survey ID",
                    options=id_col_options,
                    help="Column containing survey ID",
                    index=default_survey_id_index,
                    key="survey_id_summary",
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_id"},
                )
                save_check_settings(setting_file, TAB_NAME, {"survey_id": survey_id})

        st.markdown("#### Survey Date")
        with st.container(border=True):
            dc1, _, _ = st.columns(spec=3)
            # Date selection
            with dc1:
                default_date_index = (
                    datetime_columns.index(default_date)
                    if default_date and default_date in datetime_columns
                    else None
                )
                date = st.selectbox(
                    label="Survey Date",
                    options=datetime_columns,
                    help="Column containing survey date",
                    index=default_date_index,
                    key="date_summary",
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_date"},
                )
                save_check_settings(setting_file, TAB_NAME, {"date": date})

        st.markdown("#### Submission Target")
        with st.container(border=True):
            tc1, _, _ = st.columns(spec=3)
            # Target selection
            with tc1:
                target = st.number_input(
                    label="Total Expected Interviews",
                    min_value=0,
                    value=default_target,
                    help="Total number of interviews expected",
                    key="total_goal_summary",
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_target"},
                )
                save_check_settings(setting_file, TAB_NAME, {"target": target})

    return date, target, survey_id or None


# =============================================================================
# Streamlit UI - Report Sections
# =============================================================================


@demo_output_onboarding(TAB_NAME)
def summary_submissions(data: pl.DataFrame, date: str | None = None) -> None:
    """Render submission details report.

    Parameters
    ----------
    data : pd.DataFrame
        The survey data (pandas).
    date : str | None, default=None
        The date column in the survey data.
    """
    if not date:
        st.info(
            "Submission details report requires a date column to be selected. "
            "Go to the :material/settings: settings section above."
        )
        return

    metrics = calculate_submission_metrics(data, date)

    # Display date range
    dc1, _, _, dc2 = st.columns(spec=4)
    dc1.metric(
        label="First Submission",
        value=str(metrics.first_submission_date),
        help="Date of the first submission",
    )
    dc2.metric(
        label="Last Submission",
        value=str(metrics.last_submission_date),
        help="Date of the last submission",
    )

    # Display metrics
    mc1, mc2, mc3, mc4 = st.columns(spec=4, border=True)

    mc1.metric(
        label="Today",
        value=f"{metrics.today_count:,}",
        delta=f"{metrics.today_delta_pct:.2f}%",
        help="Number of submissions today. Delta is the percentage change from yesterday.",
    )
    mc2.metric(
        label="This week",
        value=f"{metrics.this_week_count:,}",
        delta=f"{metrics.this_week_delta_pct:.2f}%",
        help="Number of submissions this week. Delta is the percentage change from last week.",
    )
    mc3.metric(
        label="This month",
        value=f"{metrics.this_month_count:,}",
        delta=f"{metrics.this_month_delta_pct:.2f}%",
        help="Number of submissions this month. Delta is the percentage change from last month",
    )
    mc4.metric(
        label="Total",
        value=f"{metrics.total_count:,}",
        help="Total number of submissions",
    )

    # Display chart
    fig = px.area(
        metrics.submissions_by_date,
        x=date,
        y="submissions",
        title="Submissions by date",
        color_discrete_sequence=["#e8848b"],
    )
    fig.update_layout(width=1000, height=500)
    fig.update_yaxes(tick0=0)
    st.plotly_chart(fig, width="stretch")


@demo_output_onboarding(TAB_NAME)
def summary_progress(
    data: pl.DataFrame,
    date: str,
    setting_file: str,
    target: int | None = None,
) -> None:
    """Render progress report.

    Parameters
    ----------
    data : pd.DataFrame
        The survey data (pandas).
    date : str
        The date column in the survey data.
    setting_file : str
        Path to the settings file.
    target : int | None, default=None
        The target number of submissions.
    """
    if not date:
        st.info(
            "Progress section requires a date column to be selected. "
            "Go to the :material/settings: settings section above."
        )
        return

    metrics = calculate_progress_metrics(data, date, target)

    # Display metrics
    mc1, mc2, mc3, mc4 = st.columns(spec=4, border=True)

    with mc1:
        st.write("Submission progress")
        if not target:
            st.info("Target not set. Progress cannot be computed.")
        else:
            sp1, sp2 = st.columns([0.80, 0.20])
            progress_val = min(metrics.progress_pct, 100)
            sp1.progress(value=int(progress_val))
            sp2.write(f"{metrics.progress_pct:.2f}%")

    mc2.metric(
        label="Average submissions per day",
        value=f"{metrics.avg_per_day:,.2f}",
        help="Average number of submissions per day",
    )
    mc3.metric(
        label="Average submissions per week",
        value=f"{metrics.avg_per_week:,.2f}",
        help="Average number of submissions per week",
    )
    mc4.metric(
        label="Average submissions per month",
        value=f"{metrics.avg_per_month:,.2f}",
        help="Average number of submissions per month",
    )

    # Progress by column
    _render_progress_by_column(data, date, setting_file)


@st.fragment
def _render_progress_by_column(
    data: pl.DataFrame, date: str, setting_file: str
) -> None:
    """Render progress by column section.

    Parameters
    ----------
    data : pd.DataFrame
        The survey data (pandas).
    date : str
        The date column.
    setting_file : str
        Path to the settings file.
    """
    # Load default settings
    default_settings = load_check_settings(setting_file, "summary") or {}

    # Progress by column selection
    pc1, _ = st.columns([0.3, 0.7])
    with pc1:
        progress_by_col = default_settings.get("progress_by_col", None)
        progress_options = [col for col in data.columns if col != date]
        progress_col_index = (
            progress_options.index(progress_by_col)
            if progress_by_col and progress_by_col in progress_options
            else None
        )
        progress_by_col = st.selectbox(
            label="Progress by",
            options=progress_options,
            index=progress_col_index,
            key="progress_by_col_key",
            help="Select a column to compute progress by",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_progress_by_col"},
        )
        save_check_settings(
            setting_file, TAB_NAME, {"progress_by_col": progress_by_col}
        )

    if not progress_by_col:
        return

    # Time period selection
    with st.container(horizontal_alignment="right"):
        progress_time_period = default_settings.get("progress_time_period", "Auto")
        progress_time_period = st.pills(
            label="Progress time period",
            options=["Auto", "Daily", "Weekly", "Monthly"],
            default=progress_time_period,
            help="Select a time period to compute progress by",
            key="summary_progress_time_period_pill",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_progress_time_period"},
        )

        if progress_time_period:
            save_check_settings(
                setting_file,
                TAB_NAME,
                {"progress_time_period": progress_time_period},
            )

    # Compute and display progress data
    progress_data, vmin_val, vmax_val, format_cols = compute_summary_progress_by_col(
        data=data,
        date=date,
        progress_by_col=progress_by_col,
        progress_time_period=progress_time_period,
    )

    # Display heatmap
    cmap = sns.light_palette("pink", as_cmap=True)
    styler_limit = progress_data.shape[0] * progress_data.shape[1]
    pd.set_option("styler.render.max_elements", styler_limit)
    st.dataframe(
        progress_data.style.format(subset=format_cols, precision=0).background_gradient(
            subset=format_cols, cmap=cmap, axis=1, vmin=vmin_val, vmax=vmax_val
        ),
        width="stretch",
    )


@demo_output_onboarding(TAB_NAME)
def summary_data_summary(data: pl.DataFrame) -> None:
    """Render data summary section.

    Parameters
    ----------
    data : pd.DataFrame
        The survey data (pandas).
    """
    metrics = calculate_data_summary_metrics(data)

    ds1, ds2, ds3, ds4 = st.columns(spec=4, border=True)
    ds1.metric(
        label="String Columns",
        value=f"{metrics.string_columns_count:,}",
        help="Number of string columns",
    )
    ds2.metric(
        label="Numeric Columns",
        value=f"{metrics.numeric_columns_count:,}",
        help="Number of numeric columns",
    )
    ds3.metric(
        label="Date Columns",
        value=f"{metrics.date_columns_count:,}",
        help="Number of date columns",
    )
    ds4.metric(
        label="Total Columns",
        value=f"{metrics.total_columns_count:,}",
        help="Total number of columns",
    )


@demo_output_onboarding(TAB_NAME)
def summary_data_quality(data: pl.DataFrame, survey_id: str | None) -> None:
    """Render data quality section.

    Parameters
    ----------
    data : pd.DataFrame
        The survey data (pandas).
    survey_id : str | None
        The survey ID column.
    """
    metrics = calculate_data_quality_metrics(data, survey_id)

    # Create donut charts
    if metrics.duplicates_pct is not None:
        perc_duplicates_chart = donut_chart2(actual_value=metrics.duplicates_pct)
        plt.close(perc_duplicates_chart)

    perc_outliers_chart = donut_chart2(actual_value=metrics.outliers_pct)
    plt.close(perc_outliers_chart)

    perc_missing_chart = donut_chart2(actual_value=metrics.missing_pct)
    plt.close(perc_missing_chart)

    perc_back_check_error_rate_chart = donut_chart2(
        actual_value=metrics.backcheck_error_pct
    )

    # Display charts
    dq1, dq2, dq3, dq4 = st.columns(spec=4, border=True)

    with dq1:
        if metrics.duplicates_pct is not None:
            st.markdown(f"**% of duplicates values on {survey_id}**")
            st.pyplot(perc_duplicates_chart)
        else:
            st.markdown("**% of duplicates values ID Column**")
            st.info(
                "Percentage of duplicate values requires a survey ID column to be selected. "
                "Go to the :material/settings: settings section above."
            )

    with dq2:
        st.markdown("**% of values flagged as outliers**")
        st.pyplot(perc_outliers_chart)

    with dq3:
        st.markdown("**% of missing values in survey dataset**")
        st.pyplot(perc_missing_chart)

    with dq4:
        st.markdown("**Back check error rate**")
        st.pyplot(perc_back_check_error_rate_chart)


# =============================================================================
# Main Report Function
# =============================================================================


@demo_output_onboarding(TAB_NAME)
def summary_report(
    data: pl.DataFrame, setting_file: str, config: dict, survey_columns: ColumnByType
) -> None:
    """Generate comprehensive summary report.

    Parameters
    ----------
    data : pl.DataFrame
        The survey data (polars).
    setting_file : str
        Path to the settings file.
    config : dict
        Configuration dictionary.
    """
    # Get settings
    config_settings = SummarySettings(**config)
    survey_date, survey_target, survey_id = summary_settings(
        data, setting_file, config_settings, survey_columns
    )

    # Render sections
    st.write("---")
    st.markdown("## Data Summary")
    summary_data_summary(data=data)

    st.markdown("## Submission details")
    summary_submissions(data=data, date=survey_date)

    st.write("---")
    st.markdown("## Progress")
    summary_progress(
        data=data, date=survey_date, target=survey_target, setting_file=setting_file
    )

    st.write("---")
    st.markdown("## Data Quality")
    summary_data_quality(data=data, survey_id=survey_id)
