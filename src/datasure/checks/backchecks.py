import re
from contextlib import suppress
from enum import Enum
from typing import Any, Literal

import pandas as pd
import polars as pl
import streamlit as st
from pydantic import BaseModel, Field

from datasure.utils.dataframe_utils import ColumnByType
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

TAB_NAME: str = "backchecks"

# Weekday constants for productivity analysis
WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

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


##### Backchecks #####




# ==============================================================================
# PYDANTIC MODELS AND ENUMS
# ==============================================================================


class SearchType(str, Enum):
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
    backcheck_date: str | None = Field(None, description="Column containing backcheck date")
    enumerator: str | None = Field(None, description="Column containing enumerator")
    backchecker: str | None = Field(None, description="Column containing back checker")
    backcheck_target_percent: int = Field(10, description="Target percentage of backchecks")
    drop_duplicates_option: str = Field("drop", description="How to handle duplicate entries")
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

    case_option: str = Field("none", description="Case sensitivity option")
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



class OkRangeType(str, Enum):
    """OK range types for backchecks."""

    NUMBER = "number"
    PERCENTAGE = "percentage"



class BackcheckTestOptions(BaseModel):
    """Backcheck test settings for backchecks."""

    ttest: bool = Field(False, description="Perform t-test")
    prtest: bool = Field(False, description="Perform proportion test")
    signrank: bool = Field(False, description="Perform sign rank test")
    reliability: bool = Field(False, description="Calculate reliability metrics")


# ==============================================================================
# SETTINGS AND CONFIGURATION
# ==============================================================================


def load_default_backchecks_settings(
    settings_file: str, config: BackcheckSettings
) -> BackcheckSettings:
    """Load and merge saved settings with default configuration.

    Loads previously saved backcheck report settings from the settings file
    and merges them with the provided default configuration. Saved settings
    take precedence over defaults.

    Cached for 60 seconds to reduce file I/O operations.

    Parameters
    ----------
    settings_file : str
        Path to the settings file containing saved configurations.
    config : BackcheckSettings
        Default configuration to use as fallback for missing settings.

    Returns
    -------
    BackcheckSettings
        Merged settings combining saved and default configurations.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME)

    default_settings: dict = dict(config)
    default_settings.update(saved_settings)

    return BackcheckSettings(**default_settings)


# =============================================================================
# Column Search and Selection Utilities
# =============================================================================



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


# =============================================================================
# Backcheck Column Configuration Functions
# =============================================================================



def _get_ok_range_value(ok_range_type: OkRangeType) -> OkRangeValues:
    """Get the OK range value based on the selected type."""
    okr1, okr2 = st.columns(2)
    if ok_range_type == "number":
        okr_neg = okr1.number_input(
            "Negative Range Value", max_value=0.0, value=0.0, step=1.0, help="Enter the negative range value"
        )
        okr_pos = okr2.number_input(
            "Positive Range Value", min_value=0.0, value=0.0, step=1.0,  help="Enter the positive range value"
        )

    else:
        okr_neg = okr1.number_input(
            "Negative Range Value (%)",
            min_value=-100.0,
            max_value=0.0,
            value=0.0,
            step=1.0,
            help="Enter the negative range percentage",
        )
        okr_pos = okr2.number_input(
            "Positive Range Value (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            help="Enter the positive range percentage",
        )

    return OkRangeValues(ok_range_neg=okr_neg, ok_range_pos=okr_pos)





# ==============================================================================
# CORE COMPUTATION FUNCTIONS
# ==============================================================================


def compute_backcheck_analysis(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    backcheck_settings: BackcheckSettings,
    backcheck_column_settings: pl.DataFrame,
) -> pl.DataFrame:
    """Compute backcheck comparison analysis for configured columns.

    This function performs the backcheck comparison between survey and backcheck
    datasets based on the configured settings. It applies global settings from
    backcheck_settings and column-specific settings from backcheck_column_settings.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    backcheck_settings : BackcheckSettings
        Global settings for backcheck comparison.
    backcheck_column_settings : pl.DataFrame
        Column-specific settings including category, OK ranges, and test options.

    Returns
    -------
    pl.DataFrame
        Comparison results with columns:
        - survey_key: Survey identifier
        - survey_key__BCCL: Backcheck identifier
        - column_name: Name of compared column
        - survey_value: Value from survey
        - backcheck_value: Value from backcheck
        - match_status: 'match', 'mismatch', 'excluded', 'no_difference'
        - difference: Numeric difference (for numeric columns)
        - within_ok_range: Boolean indicating if within acceptable range
        - ttest_t_statistic: T-test t-statistic (if configured)
        - ttest_p_value: T-test p-value (if configured)
        - prtest_z_statistic: Proportion test z-statistic (if configured)
        - prtest_p_value: Proportion test p-value (if configured)
        - signrank_statistic: Wilcoxon signed-rank statistic (if configured)
        - signrank_p_value: Wilcoxon signed-rank p-value (if configured)
        - reliability_srv: Simple Response Variance (if configured)
        - reliability_ratio: Reliability ratio (if configured)
    """
    if backcheck_column_settings.is_empty():
        return pl.DataFrame()

    # Get survey key for merging
    survey_key = backcheck_settings.survey_key
    if not survey_key or survey_key not in survey_data.columns:
        return pl.DataFrame()

    survey_id = backcheck_settings.survey_id
    if not survey_id or survey_id not in survey_data.columns or survey_id not in backcheck_data.columns:
        return pl.DataFrame()

    # Handle duplicates according to settings
    drop_duplicates_option = backcheck_settings.drop_duplicates_option

    # Prepare survey data for merge
    survey_for_merge = survey_data.clone()
    if drop_duplicates_option == "first":
        survey_for_merge = survey_for_merge.unique(subset=[survey_id], keep="first")
    elif drop_duplicates_option == "last":
        survey_for_merge = survey_for_merge.unique(subset=[survey_id], keep="last")
    elif drop_duplicates_option == "drop":
        # Keep only non-duplicate rows
        duplicates = survey_for_merge.group_by(survey_id).len().filter(pl.col("len") > 1)[survey_id]
        survey_for_merge = survey_for_merge.filter(~pl.col(survey_id).is_in(duplicates))

    # Prepare backcheck data for merge
    backcheck_for_merge = backcheck_data.clone()
    if drop_duplicates_option == "first":
        backcheck_for_merge = backcheck_for_merge.unique(subset=[survey_id], keep="first")
    elif drop_duplicates_option == "last":
        backcheck_for_merge = backcheck_for_merge.unique(subset=[survey_id], keep="last")
    elif drop_duplicates_option == "drop":
        # Keep only non-duplicate rows
        duplicates = backcheck_for_merge.group_by(survey_id).len().filter(pl.col("len") > 1)[survey_id]
        backcheck_for_merge = backcheck_for_merge.filter(~pl.col(survey_id).is_in(duplicates))

    # Merge datasets on survey id. Inner join to keep only matched records and label
    # backcheck columns with suffix __BCCL
    merged_data = survey_for_merge.join(
        backcheck_for_merge,
        on=survey_id,
        how="inner",
        suffix="__BCCL",
    )

    if merged_data.is_empty():
        return pl.DataFrame()

    # Extract global settings
    no_diff_list = backcheck_settings.no_differences_list or []
    exclude_list = backcheck_settings.exclude_values_list or []
    case_option = backcheck_settings.case_option
    trim_spaces = backcheck_settings.trimspaces_option
    no_symbols = backcheck_settings.nosymbols_option

    results = []

    # Process each configured column
    for row in backcheck_column_settings.iter_rows(named=True):
        search_type = row["search_type"]
        pattern = row["pattern"]
        columns = row["column_name"]
        category = row["category"]
        ok_range_type = row.get("ok_range_type")
        ok_range_values = row.get("ok_range_values")
        ttest = row.get("ttest", False)
        prtest = row.get("prtest", False)
        signrank = row.get("signrank", False)
        reliability = row.get("reliability", False)

        # Expand columns if pattern-based search
        if search_type != SearchType.EXACT.value and pattern:
            survey_cols = [col for col in survey_data.columns if col != survey_key]
            columns = expand_col_names(survey_cols, pattern, search_type)

        # Process each column
        for col in columns:
            if col not in merged_data.columns:
                continue

            backcheck_col = f"{col}__BCCL"
            if backcheck_col not in merged_data.columns:
                continue

            # Compare values for this column
            col_results = _compare_column_values(
                merged_data,
                survey_key,
                col,
                backcheck_col,
                category,
                ok_range_type,
                ok_range_values,
                no_diff_list,
                exclude_list,
                case_option,
                trim_spaces,
                no_symbols,
            )

            # Add statistical tests if configured
            if ttest or prtest or signrank or reliability:
                test_results = _perform_statistical_tests(
                    merged_data,
                    col,
                    backcheck_col,
                    ttest,
                    prtest,
                    signrank,
                    reliability,
                )
                # Extract test results into separate columns
                col_results = col_results.with_columns([
                    pl.lit(test_results.get("ttest", {}).get("t_statistic")).alias("ttest_t_statistic"),
                    pl.lit(test_results.get("ttest", {}).get("p_value")).alias("ttest_p_value"),
                    pl.lit(test_results.get("prtest", {}).get("z_statistic")).alias("prtest_z_statistic"),
                    pl.lit(test_results.get("prtest", {}).get("p_value")).alias("prtest_p_value"),
                    pl.lit(test_results.get("signrank", {}).get("statistic")).alias("signrank_statistic"),
                    pl.lit(test_results.get("signrank", {}).get("p_value")).alias("signrank_p_value"),
                    pl.lit(test_results.get("reliability", {}).get("srv")).alias("reliability_srv"),
                    pl.lit(test_results.get("reliability", {}).get("reliability_ratio")).alias("reliability_ratio"),
                ])
            else:
                # Add null test result columns to maintain schema consistency
                col_results = col_results.with_columns([
                    pl.lit(None).alias("ttest_t_statistic"),
                    pl.lit(None).alias("ttest_p_value"),
                    pl.lit(None).alias("prtest_z_statistic"),
                    pl.lit(None).alias("prtest_p_value"),
                    pl.lit(None).alias("signrank_statistic"),
                    pl.lit(None).alias("signrank_p_value"),
                    pl.lit(None).alias("reliability_srv"),
                    pl.lit(None).alias("reliability_ratio"),
                ])

            results.append(col_results)

    # Combine all results
    if results:
        return pl.concat(results, how="vertical_relaxed")
    return pl.DataFrame()



def compute_backchecker_productivity(
    data: pl.DataFrame, date: str, group_by_cols: list[str], period: str, weekstartday: str
) -> pl.DataFrame:
    """Compute backchecker productivity over time.

    Analyzes backcheck submission counts by backchecker across time periods (daily,
    weekly, or monthly).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing backcheck data.
    date : str
        Date column name.
    group_by_cols : list[str]
        Columns to group by (e.g., [backchecker]).
    period : str
        Time period: "Daily", "Weekly", "Monthly", "Day", "Week", or "Month".
    weekstartday : str
        Start day of the week (e.g., "SUN", "MON") for weekly analysis.

    Returns
    -------
    pl.DataFrame
        Pivoted DataFrame with backcheckers as rows and time periods as columns.
    """
    prod_df = data.clone()

    # Normalize period values to handle both old and new formats
    period_normalized = period
    if period == "Day":
        period_normalized = "Daily"
    elif period == "Week":
        period_normalized = "Weekly"
    elif period == "Month":
        period_normalized = "Monthly"

    # Create time period column based on selection with user-friendly formatting
    if period_normalized == "Daily":
        # Format as "Jan 1, 2025"
        prod_df = prod_df.with_columns(
            pl.col(date).dt.strftime("%b %d, %Y").alias("TIME PERIOD")
        )
    elif period_normalized == "Weekly":
        # Calculate week start and end dates for user-friendly display
        offset = WEEKDAY_OFFSET_TO_NUMERIC.get(weekstartday, 1)

        # Calculate the week start date (beginning of the week containing this date)
        # weekday() returns 0=Monday, 6=Sunday
        prod_df = prod_df.with_columns([
            # Calculate days since the start of the week
            ((pl.col(date).dt.weekday() - offset + 7) % 7).alias("_days_since_week_start"),
        ])

        # Calculate week_start_date by subtracting days_since_week_start
        prod_df = prod_df.with_columns([
            (pl.col(date) - pl.duration(days=pl.col("_days_since_week_start"))).alias("_week_start"),
            (pl.col(date) - pl.duration(days=pl.col("_days_since_week_start")) + pl.duration(days=6)).alias("_week_end"),
        ])

        # Format as "Jan 1, 2025 to Jan 7, 2025"
        prod_df = prod_df.with_columns(
            (pl.col("_week_start").dt.strftime("%b %d, %Y") + " to " + pl.col("_week_end").dt.strftime("%b %d, %Y")).alias("TIME PERIOD")
        )
    elif period_normalized == "Monthly":
        # Format as "January 2025"
        prod_df = prod_df.with_columns(
            pl.col(date).dt.strftime("%B %Y").alias("TIME PERIOD")
        )

    # Count submissions per period and backchecker
    prod_df = prod_df.with_row_index(name="TOKEN KEY")
    prod_res = prod_df.group_by(["TIME PERIOD"] + group_by_cols, maintain_order=True).agg(
        pl.col("TOKEN KEY").count().alias("submissions")
    )

    # Pivot to wide format
    prod_res = prod_res.pivot(
        index=group_by_cols,
        on="TIME PERIOD",
        values="submissions",
    ).fill_null(0)

    return prod_res



def compute_enumerator_backchecker_stats(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    backcheck_analysis: pl.DataFrame,
    backcheck_settings: BackcheckSettings,
    staff_type: str = "enumerator",
) -> pl.DataFrame:
    """Compute error rate statistics for enumerators or backcheckers.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    backcheck_analysis : pl.DataFrame
        Results from compute_backcheck_analysis.
    backcheck_settings : BackcheckSettings
        Backcheck settings.
    staff_type : str
        Either "enumerator" or "backchecker".

    Returns
    -------
    pl.DataFrame
        Statistics DataFrame with error rates by category.
    """
    if backcheck_analysis.is_empty():
        return pl.DataFrame()

    survey_key = backcheck_settings.survey_key
    if not survey_key:
        return pl.DataFrame()

    survey_id = backcheck_settings.survey_id
    if not survey_id:
        return pl.DataFrame()

    # Get staff column name and join key
    if staff_type == "enumerator":
        staff_col = backcheck_settings.enumerator
        data_source = survey_data
        join_key = survey_key  # Enumerators join on survey_key
    else:  # backchecker
        staff_col = backcheck_settings.backchecker
        data_source = backcheck_data
        join_key = f"{survey_key}__BCCL"  # Backcheckers join on backcheck key

    if not staff_col or staff_col not in data_source.columns:
        return pl.DataFrame()

    # Check if join key exists in analysis
    if join_key not in backcheck_analysis.columns:
        return pl.DataFrame()

    # Get date columns
    survey_date = backcheck_settings.survey_date
    backcheck_date = backcheck_settings.backcheck_date

    # Join analysis with staff information
    # For backcheckers, join on the backcheck key; for enumerators, join on survey key
    # Remove duplicates from staff_info to avoid duplicate rows
    if staff_type == "enumerator":
        staff_info = data_source.select([survey_key, staff_col]).unique(subset=[survey_key])
        analysis_with_staff = backcheck_analysis.join(staff_info, on=survey_key, how="left")
    else:
        # For backcheckers, join backcheck_data with backcheck key
        staff_info = data_source.select([survey_key, staff_col]).unique(subset=[survey_key])
        # Rename survey_key to match backcheck key in analysis
        staff_info = staff_info.rename({survey_key: join_key})
        analysis_with_staff = backcheck_analysis.join(staff_info, on=join_key, how="left")

    # Add survey date from survey_data (regardless of staff type)
    if survey_date and survey_date in survey_data.columns:
        survey_dates = survey_data.select([survey_key, pl.col(survey_date).alias("survey_date_col")]).unique(subset=[survey_key])
        analysis_with_staff = analysis_with_staff.join(survey_dates, on=survey_key, how="left")

    # Add backcheck date from backcheck_data
    if backcheck_date and backcheck_date in backcheck_data.columns:
        bc_dates = backcheck_data.select([survey_key, pl.col(backcheck_date).alias("backcheck_date_col")]).unique(subset=[survey_key])
        analysis_with_staff = analysis_with_staff.join(bc_dates, on=survey_key, how="left")

    # Calculate statistics by staff and category
    stats_list = []

    # Filter out rows where staff column is null
    analysis_with_staff = analysis_with_staff.filter(pl.col(staff_col).is_not_null())

    if analysis_with_staff.is_empty():
        return pl.DataFrame()

    for staff_name in analysis_with_staff[staff_col].unique().drop_nulls():
        staff_data = analysis_with_staff.filter(pl.col(staff_col) == staff_name)

        # Initialize stats dict for this staff member
        staff_stats = {staff_col: staff_name}

        # Overall statistics (across all categories)
        staff_stats["Surveys"] = staff_data[survey_key].n_unique()
        staff_stats["Backchecks"] = staff_data[survey_key].n_unique()

        # Calculate average days between survey and backcheck (overall)
        if (survey_date and backcheck_date and
            "survey_date_col" in staff_data.columns and
            "backcheck_date_col" in staff_data.columns):
            with suppress(Exception):
                days_diff = (
                    staff_data
                    .with_columns([
                        (pl.col("backcheck_date_col") - pl.col("survey_date_col")).dt.total_days().alias("days_between")
                    ])
                    .select(pl.col("days_between").mean())
                    .item()
                )
                staff_stats["Avg Days"] = round(days_diff, 1) if days_diff is not None else 0
        else:
            staff_stats["Avg Days"] = 0

        # Initialize totals
        total_non_missing_survey = 0
        total_non_missing_backcheck = 0
        total_compared = 0
        total_mismatches = 0

        # Calculate statistics by category
        for category in [1, 2, 3]:
            cat_data = staff_data.filter(pl.col("category") == category)

            if cat_data.is_empty():
                # Fill with zeros if no data for this category
                staff_stats[f"Non-Missing Survey (Cat {category})"] = 0
                staff_stats[f"Non-Missing Backcheck (Cat {category})"] = 0
                staff_stats[f"Values Compared (Cat {category})"] = 0
                staff_stats[f"Mismatches (Cat {category})"] = 0
                staff_stats[f"Error Rate % (Cat {category})"] = 0.0
                continue

            # Non-missing values for this category
            n_non_missing_survey = cat_data.filter(
                ~pl.col("survey_value").is_null()
            ).height
            n_non_missing_backcheck = cat_data.filter(
                ~pl.col("backcheck_value").is_null()
            ).height

            # Mismatches for this category
            n_mismatches = cat_data.filter(
                pl.col("match_status") == "mismatch"
            ).height

            # Values compared for this category (excluding missing and excluded)
            n_cat_compared = cat_data.filter(
                ~pl.col("match_status").is_in(["missing", "excluded"])
            ).height

            # Error rate
            error_rate = (n_mismatches / n_cat_compared * 100) if n_cat_compared > 0 else 0

            # Store category-specific stats
            staff_stats[f"Non-Missing Survey (Cat {category})"] = n_non_missing_survey
            staff_stats[f"Non-Missing Backcheck (Cat {category})"] = n_non_missing_backcheck
            staff_stats[f"Values Compared (Cat {category})"] = n_cat_compared
            staff_stats[f"Mismatches (Cat {category})"] = n_mismatches
            staff_stats[f"Error Rate % (Cat {category})"] = round(error_rate, 2)

            # Accumulate totals
            total_non_missing_survey += n_non_missing_survey
            total_non_missing_backcheck += n_non_missing_backcheck
            total_compared += n_cat_compared
            total_mismatches += n_mismatches

        # Calculate and store totals
        staff_stats["Non-Missing Survey (Total)"] = total_non_missing_survey
        staff_stats["Non-Missing Backcheck (Total)"] = total_non_missing_backcheck
        staff_stats["Values Compared (Total)"] = total_compared
        staff_stats["Mismatches (Total)"] = total_mismatches
        total_error_rate = (total_mismatches / total_compared * 100) if total_compared > 0 else 0
        staff_stats["Error Rate % (Total)"] = round(total_error_rate, 2)

        stats_list.append(staff_stats)

    if not stats_list:
        return pl.DataFrame()

    return pl.DataFrame(stats_list)



def compute_column_stats(
    survey_data: pl.DataFrame,
    backcheck_analysis: pl.DataFrame,
) -> pl.DataFrame:
    """Compute statistics for each column in backcheck analysis.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset to get data types.
    backcheck_analysis : pl.DataFrame
        Results from compute_backcheck_analysis.

    Returns
    -------
    pl.DataFrame
        Statistics DataFrame with one row per column.
    """
    if backcheck_analysis.is_empty():
        return pl.DataFrame()

    # Group by column_name and category to compute statistics
    stats_list = []

    for col_name in backcheck_analysis["column_name"].unique().drop_nulls():
        col_data = backcheck_analysis.filter(pl.col("column_name") == col_name)

        # Get category (should be consistent for all rows of this column)
        category = col_data["category"][0]

        # Get data type from survey_data
        if col_name in survey_data.columns:
            dtype = str(survey_data.schema[col_name])
        else:
            dtype = "Unknown"

        # Total number of values (all rows for this column)
        n_values = col_data.height

        # Number of values compared (excluding missing and excluded)
        n_compared = col_data.filter(
            ~pl.col("match_status").is_in(["missing", "excluded"])
        ).height

        # Total mismatches
        n_mismatches = col_data.filter(
            pl.col("match_status") == "mismatch"
        ).height

        # Error rate
        error_rate = (n_mismatches / n_compared * 100) if n_compared > 0 else 0

        # Collect test results if available
        test_results_str = ""
        test_columns = [
            "ttest_t_statistic", "ttest_p_value",
            "prtest_z_statistic", "prtest_p_value",
            "signrank_statistic", "signrank_p_value",
            "reliability_srv", "reliability_ratio"
        ]

        # Check if any test columns exist and have non-null values
        available_tests = []
        for test_col in test_columns:
            if test_col in col_data.columns:
                # Get first non-null value (test results should be same for all rows)
                test_val = col_data[test_col].drop_nulls().head(1)
                if len(test_val) > 0:
                    val = test_val[0]
                    # Format the test result nicely
                    if "ttest" in test_col:
                        if "statistic" in test_col:
                            available_tests.append(f"T-test: t={val:.3f}")
                        elif "p_value" in test_col:
                            available_tests.append(f"p={val:.4f}")
                    elif "prtest" in test_col:
                        if "statistic" in test_col:
                            available_tests.append(f"Prop test: z={val:.3f}")
                        elif "p_value" in test_col:
                            available_tests.append(f"p={val:.4f}")
                    elif "signrank" in test_col:
                        if "statistic" in test_col:
                            available_tests.append(f"Sign-rank: W={val:.3f}")
                        elif "p_value" in test_col:
                            available_tests.append(f"p={val:.4f}")
                    elif "reliability_srv" in test_col:
                        available_tests.append(f"SRV={val:.4f}")
                    elif "reliability_ratio" in test_col:
                        available_tests.append(f"Reliability={val:.4f}")

        test_results_str = "; ".join(available_tests) if available_tests else "None"

        stats_list.append({
            "Column Name": col_name,
            "Category": category,
            "Data Type": dtype,
            "# of Values": n_values,
            "Values Compared": n_compared,
            "Mismatches": n_mismatches,
            "Error Rate (%)": round(error_rate, 2),
            "Test Results": test_results_str,
        })

    if not stats_list:
        return pl.DataFrame()

    return pl.DataFrame(stats_list)





# ==============================================================================
# COMPARISON AND ANALYSIS HELPERS
# ==============================================================================


def _compare_column_values(
    data: pl.DataFrame,
    survey_key: str,
    survey_col: str,
    backcheck_col: str,
    category: int,
    ok_range_type: str | None,
    ok_range_values: list[float] | None,
    no_diff_list: list[str],
    exclude_list: list[str],
    case_option: str | None,
    trim_spaces: bool,
    no_symbols: bool,
) -> pl.DataFrame:
    """Compare values between survey and backcheck for a single column.

    Parameters
    ----------
    data : pl.DataFrame
        Merged survey and backcheck data.
    survey_key : str
        Column name for survey identifier.
    survey_col : str
        Survey column name.
    backcheck_col : str
        Backcheck column name.
    category : int
        Backcheck category (1, 2, or 3).
    ok_range_type : str | None
        Type of OK range ('number' or 'percentage').
    ok_range_values : list[float] | None
        OK range values [negative, positive].
    no_diff_list : list[str]
        Values that won't be marked as differences.
    exclude_list : list[str]
        Values to exclude from comparison.
    case_option : str | None
        Case sensitivity option ('lowercase', 'uppercase', or None).
    trim_spaces : bool
        Whether to trim spaces before comparison.
    no_symbols : bool
        Whether to ignore symbols in comparison.

    Returns
    -------
    pl.DataFrame
        Comparison results for this column.
    """
    # Start with survey key, backcheck key, and column values
    # Backcheck key will have __BCCL suffix from the join
    backcheck_key = f"{survey_key}__BCCL"

    select_cols = [
        pl.col(survey_key),
        pl.lit(survey_col).alias("column_name"),
        pl.col(survey_col).alias("survey_value"),
        pl.col(backcheck_col).alias("backcheck_value"),
        pl.lit(category).alias("category"),
    ]

    # Include backcheck key if it exists in the data
    if backcheck_key in data.columns:
        select_cols.insert(1, pl.col(backcheck_key))

    result = data.select(select_cols)

    # Convert to string for comparison if needed
    survey_vals = result["survey_value"].cast(pl.Utf8)
    backcheck_vals = result["backcheck_value"].cast(pl.Utf8)

    # Apply string preprocessing if configured
    if case_option == "lowercase":
        survey_vals = survey_vals.str.to_lowercase()
        backcheck_vals = backcheck_vals.str.to_lowercase()
    elif case_option == "uppercase":
        survey_vals = survey_vals.str.to_uppercase()
        backcheck_vals = backcheck_vals.str.to_uppercase()

    if trim_spaces:
        survey_vals = survey_vals.str.strip_chars()
        backcheck_vals = backcheck_vals.str.strip_chars()

    if no_symbols:
        # Remove common symbols
        survey_vals = survey_vals.str.replace_all(r"[^\w\s]", "")
        backcheck_vals = backcheck_vals.str.replace_all(r"[^\w\s]", "")

    # Determine match status
    match_status = pl.when(
        survey_vals.is_in(exclude_list) | backcheck_vals.is_in(exclude_list)
    ).then(pl.lit("excluded")).when(
        survey_vals.is_in(no_diff_list) & backcheck_vals.is_in(no_diff_list)
    ).then(pl.lit("no_difference")).when(
        survey_vals.is_null() | backcheck_vals.is_null()
    ).then(pl.lit("missing")).when(
        survey_vals == backcheck_vals
    ).then(pl.lit("match")).otherwise(pl.lit("mismatch"))

    result = result.with_columns([match_status.alias("match_status")])

    # Calculate numeric difference and check OK range for numeric columns
    if data.schema[survey_col].is_numeric() and data.schema[backcheck_col.replace("__BCCL", "")].is_numeric():
        difference = (
            pl.col("survey_value").cast(pl.Float64) -
            pl.col("backcheck_value").cast(pl.Float64)
        )
        result = result.with_columns([difference.alias("difference")])

        # Check if within OK range
        if ok_range_type and ok_range_values and len(ok_range_values) >= 2:
            ok_range_neg = ok_range_values[0]
            ok_range_pos = ok_range_values[1]

            if ok_range_type == "percentage":
                # Calculate percentage difference
                pct_diff = (difference.abs() / pl.col("survey_value").cast(pl.Float64).abs()) * 100
                within_range = (pct_diff >= abs(ok_range_neg)) & (pct_diff <= ok_range_pos)
            else:
                # Absolute difference
                within_range = (difference >= ok_range_neg) & (difference <= ok_range_pos)

            result = result.with_columns([within_range.alias("within_ok_range")])
        else:
            result = result.with_columns([pl.lit(None).alias("within_ok_range")])
    else:
        result = result.with_columns([
            pl.lit(None).cast(pl.Float64).alias("difference"),
            pl.lit(None).alias("within_ok_range"),
        ])

    return result



def _perform_statistical_tests(
    data: pl.DataFrame,
    survey_col: str,
    backcheck_col: str,
    ttest: bool,
    prtest: bool,
    signrank: bool,
    reliability: bool,
) -> dict[str, Any]:
    """Perform statistical tests on survey and backcheck data.

    Parameters
    ----------
    data : pl.DataFrame
        Merged survey and backcheck data.
    survey_col : str
        Survey column name.
    backcheck_col : str
        Backcheck column name.
    ttest : bool
        Whether to perform t-test.
    prtest : bool
        Whether to perform proportion test.
    signrank : bool
        Whether to perform sign rank test.
    reliability : bool
        Whether to calculate reliability metrics.

    Returns
    -------
    dict[str, Any]
        Dictionary of test results.
    """
    test_results = {}

    # Convert to pandas for statistical tests
    df_pd = data.select([survey_col, backcheck_col]).to_pandas()
    survey_vals = df_pd[survey_col].dropna()
    backcheck_vals = df_pd[backcheck_col].dropna()

    if len(survey_vals) < 2 or len(backcheck_vals) < 2:
        return {"error": "Insufficient data for statistical tests"}

    # T-test for numeric data
    if ttest:
        with suppress(Exception):
            from scipy import stats
            t_stat, p_value = stats.ttest_rel(survey_vals, backcheck_vals)
            test_results["ttest"] = {
                "t_statistic": float(t_stat),
                "p_value": float(p_value),
            }

    # Proportion test for binary data
    if prtest:
        with suppress(Exception):
            from scipy import stats
            # Assume binary 0/1 or True/False
            prop_survey = survey_vals.mean()
            prop_backcheck = backcheck_vals.mean()
            n = len(survey_vals)
            z_stat = (prop_survey - prop_backcheck) / ((prop_survey * (1 - prop_survey) + prop_backcheck * (1 - prop_backcheck)) / n) ** 0.5
            p_value = 2 * (1 - stats.norm.cdf(abs(z_stat)))
            test_results["prtest"] = {
                "z_statistic": float(z_stat),
                "p_value": float(p_value),
            }

    # Wilcoxon signed-rank test
    if signrank:
        with suppress(Exception):
            from scipy import stats
            stat, p_value = stats.wilcoxon(survey_vals, backcheck_vals)
            test_results["signrank"] = {
                "statistic": float(stat),
                "p_value": float(p_value),
            }

    # Reliability metrics (Simple Response Variance and Reliability Ratio)
    if reliability:
        with suppress(Exception):
            differences = survey_vals - backcheck_vals
            srv = differences.var() / 2  # Simple Response Variance
            signal_var = survey_vals.var()
            reliability_ratio = 1 - (srv / signal_var) if signal_var > 0 else 0
            test_results["reliability"] = {
                "srv": float(srv),
                "reliability_ratio": float(reliability_ratio),
            }

    return test_results





# ==============================================================================
# COLUMN CONFIGURATION FUNCTIONS
# ==============================================================================


def _render_backchecks_column_actions(
    project_id: str, page_name_id: str, survey_data, backcheck_data, common_columns: list[str]
) -> None:
    """Render the backcheck column configuration UI.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    common_columns : list[str]
        List of columns common to both survey and backcheck data.
    """
    backcheck_settings = duckdb_get_table(
        project_id,
        f"backchecks_{page_name_id}",
        "logs",
    )

    os1, os2, _ = st.columns([0.4, 0.3, 0.3])
    with os1:
        st.button(
            "Add Backcheck Column",
            key="add_backcheck_column",
            help="Add a new backcheck column configuration.",
            width="stretch",
            type="primary",
            on_click=_add_backcheck_column,
            args=(
                project_id,
                page_name_id,
                survey_data,
                backcheck_data,
                common_columns,
            ),
        )
    with os2:
        _delete_backcheck_column(project_id, page_name_id, backcheck_settings)

    if backcheck_settings.is_empty():
        st.info(
            "Use the :material/add: button to add columns for backcheck comparison and the "
            ":material/delete: button to remove columns."
        )
    else:
        _render_backcheck_settings_table(backcheck_settings)


@st.dialog("Add Backcheck Column(s)", width="medium")



def _add_backcheck_column(
    project_id: str, page_name_id: str, survey_data: pl.DataFrame, backcheck_data: pl.DataFrame, common_columns: list[str]
) -> None:
    """Dialog to add a new backcheck column configuration.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    common_columns : list[str]
        List of columns common to both survey and backcheck data.
    """
    # Render search type selection
    search_type, pattern, backcheck_cols, _lock_cols_initial = (
        _render_search_type_selection(common_columns)
    )

    if backcheck_cols:
        # Render backcheck category
        backcheck_category = _render_backcheck_category_options()

        if backcheck_category:

            # Render OK range options
            # Check if columns are numeric in both datasets
            cols_numeric_in_survey = all(
                survey_data.schema[col].is_numeric()
                for col in backcheck_cols
                if col in survey_data.columns
            )

            cols_numeric_in_backcheck = all(
                backcheck_data.schema[col].is_numeric()
                for col in backcheck_cols
                if col in backcheck_data.columns
            )

            # Only show OK range options for numeric columns
            if cols_numeric_in_survey and cols_numeric_in_backcheck:
                ok_range_options: OkRangeOptions = _render_ok_range_options()
                backcheck_test_options: BackcheckTestOptions = _render_backcheck_test_options(backcheck_category)
            else:
                ok_range_options = OkRangeOptions(ok_range_type=None, ok_range_values=None)
                backcheck_test_options = BackcheckTestOptions(ttest=False, prtest=False, signrank=False, reliability=False)

            if st.button(
                "Add Backcheck Column Configuration",
                key="confirm_add_backcheck_column",
                type="primary",
                width="stretch",
                disabled=not backcheck_cols or not backcheck_category,
            ):
                _update_backcheck_column_config(
                    project_id,
                    page_name_id,
                    search_type,
                    pattern,
                    backcheck_cols,
                    backcheck_category,
                    ok_range_options,
                    backcheck_test_options,
                )

                st.success("Backcheck column configuration added successfully.")
                st.rerun()



def _update_backcheck_column_config(
    project_id: str,
    page_name_id: str,
    search_type: str,
    pattern: str | None,
    backcheck_cols: list[str],
    backcheck_category: int,
    ok_range_options: OkRangeOptions,
    backcheck_test_options: BackcheckTestOptions,
) -> None:
    """Update the backcheck column configuration in the database.

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
    backcheck_cols : list[str]
        Selected columns.
    category : int
        Backcheck category (1, 2, or 3).
    ok_range : str
        OK range value.
    comparison_condition : str
        Comparison condition.
    """
    # Get existing config
    existing_config = duckdb_get_table(
        project_id=project_id,
        alias=f"backchecks_{page_name_id}",
        db_name="logs",
    )

    # Prepare new configuration
    new_config = {
        "search_type": search_type,
        "pattern": pattern,
        "column_name": [backcheck_cols],
        "category": backcheck_category,
        "ok_range_type": ok_range_options.ok_range_type if ok_range_options else None,
        "ok_range_values": ok_range_options.ok_range_values if ok_range_options else None,
        "ttest": backcheck_test_options.ttest,
        "prtest": backcheck_test_options.prtest,
        "signrank": backcheck_test_options.signrank,
        "reliability": backcheck_test_options.reliability,
    }

    schema = {
        "search_type": pl.Utf8,
        "pattern": pl.Utf8,
        "column_name": pl.List(pl.Utf8),
        "category": pl.Int64,
        "ok_range_type": pl.Utf8,
        "ok_range_values": pl.List(pl.Float64),
        "ttest": pl.Boolean,
        "prtest": pl.Boolean,
        "signrank": pl.Boolean,
        "reliability": pl.Boolean,
    }

    # Append new configuration to existing polars DataFrame
    new_config_df = pl.DataFrame(new_config, schema=schema)
    if not existing_config.is_empty():
        updated_config = pl.concat([existing_config, new_config_df], how="vertical")
    else:
        updated_config = new_config_df

    # Save updated configuration back to the database
    duckdb_save_table(
        project_id,
        updated_config,
        f"backchecks_{page_name_id}",
        db_name="logs",
    )



def _delete_backcheck_column(
    project_id: str, page_name_id: str, backcheck_settings: pl.DataFrame
) -> None:
    """Render delete backcheck column button and handle deletion.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    backcheck_settings : pl.DataFrame
        Current backcheck settings.
    """
    with st.popover(
        label=":material/delete: Delete backcheck column",
        width="stretch",
    ):
        st.markdown("#### Remove backcheck columns")

        if backcheck_settings.is_empty():
            st.info("No backcheck columns have been added yet.")
        else:
            backcheck_settings_indexed = backcheck_settings.with_row_index().with_columns(
                (
                    pl.col("index").cast(pl.Utf8)
                    + " - "
                    + pl.col("search_type")
                    + " - "
                    + pl.col("pattern").fill_null("")
                ).alias("composite_index")
            )

            unique_index = (
                backcheck_settings_indexed["composite_index"]
                .unique(maintain_order=True)
                .to_list()
            )

            selected_index = st.selectbox(
                label="Select backcheck column to remove",
                options=unique_index,
                help="Select the backcheck column to remove from the list.",
            )

            if st.button(
                label="Confirm deletion",
                type="primary",
                width="stretch",
                key="confirm_delete_backcheck_column",
                help="Click to remove the selected backcheck column configuration.",
                disabled=not selected_index,
            ):
                updated_settings = backcheck_settings_indexed.filter(
                    pl.col("composite_index") != selected_index
                ).drop("composite_index", "index")

                duckdb_save_table(
                    project_id,
                    updated_settings,
                    f"backchecks_{page_name_id}",
                    "logs",
                )

                st.rerun()



def _render_backcheck_settings_table(backcheck_settings: pl.DataFrame) -> None:
    """Render the backcheck settings table in Streamlit.

    Parameters
    ----------
    backcheck_settings : pl.DataFrame
        Backcheck settings configuration.
    """
    with st.expander("Backcheck Column Settings", expanded=False):
        st.dataframe(
            backcheck_settings,
            width="stretch",
            hide_index=True,
            column_config={
                "search_type": st.column_config.Column("Search Type"),
                "pattern": st.column_config.Column("Pattern"),
                "column_name": st.column_config.Column("Column Name(s)"),
                "category": st.column_config.NumberColumn("Category"),
                "ok_range_type": st.column_config.Column("OK Range Type"),
                "ok_range_values": st.column_config.Column("OK Range Values"),
                "ttest": st.column_config.CheckboxColumn("t-test"),
                "prtest": st.column_config.CheckboxColumn("prtest"),
                "signrank": st.column_config.CheckboxColumn("Sign Rank Test"),
                "reliability": st.column_config.CheckboxColumn("Reliability Analysis"),
            },
        )





# ==============================================================================
# SETTINGS UI RENDER FUNCTIONS
# ==============================================================================


def backchecks_report_settings(
    project_id: str,
    settings_file: str,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    config: BackcheckSettings,
    survey_categorical_columns: list[str],
    survey_datetime_columns: list[str],
    backcheck_categorical_columns: list[str],
    backcheck_datetime_columns: list[str],
) -> BackcheckSettings:
    """Create and render the settings UI for backchecks report configuration.

    This function creates a comprehensive Streamlit UI for configuring
    backchecks report settings. It includes:
    - Survey identifiers (key and ID columns)
    - Survey date column selection
    - Enumerator and backchecker columns
    - Tracking options (backcheck goal and duplicate handling)

    Settings are automatically saved to the settings file when changed
    and loaded from previous sessions if available.

    Parameters
    ----------
    project_id : str
        Unique project identifier for database operations.
    settings_file : str
        Path to settings file for saving/loading configurations.
    survey_data : pd.DataFrame
        Survey dataset.
    backcheck_data : pd.DataFrame
        Backcheck dataset.
    config : BackcheckSettings
        Default configuration used as fallback values.
    categorical_columns : list[str]
        Available categorical columns for selection.
    datetime_columns : list[str]
        Available datetime columns for date selection.

    Returns
    -------
    BackcheckSettings
        User-configured settings from the UI.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for backcheck report")
        st.write("---")

        default_settings = load_default_backchecks_settings(settings_file, config)

        # Survey Identifiers
        with st.container(border=True):
            st.subheader("Survey Identifiers")
            si1, si2, _ = st.columns(3)

            with si1:
                default_survey_key = default_settings.survey_key
                default_survey_key_index = (
                    survey_categorical_columns.index(default_survey_key)
                    if default_survey_key and default_survey_key in survey_categorical_columns
                    else None
                )
                survey_key = st.selectbox(
                    "Survey Key (required)",
                    options=survey_categorical_columns,
                    key="survey_key_backchecks",
                    help="Select the column that contains the survey key",
                    index=default_survey_key_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_key"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_key": survey_key})

            with si2:
                default_survey_id = default_settings.survey_id
                default_survey_id_index = (
                    survey_categorical_columns.index(default_survey_id)
                    if default_survey_id and default_survey_id in survey_categorical_columns
                    else None
                )
                survey_id = st.selectbox(
                    "Survey ID (required)",
                    options=survey_categorical_columns,
                    help="Select the column that contains the survey ID",
                    key="survey_id_backchecks",
                    index=default_survey_id_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_id"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_id": survey_id})

        # Survey Date
        with st.container(border=True):
            st.subheader("Survey & BAckcheck Dates")

            sd1, sd2, _ = st.columns(3)

            with sd1:
                default_survey_date = default_settings.survey_date
                default_survey_date_index = (
                    survey_datetime_columns.index(default_survey_date)
                    if default_survey_date and default_survey_date in survey_datetime_columns
                    else None
                )

                survey_date = st.selectbox(
                    "Survey Date",
                    options=survey_datetime_columns,
                    help="Select the column that contains the survey date",
                    key="survey_date_backchecks",
                    index=default_survey_date_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_date"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"survey_date": survey_date}
                )
            with sd2:
                default_backcheck_date = default_settings.survey_date
                default_backcheck_date_index = (
                    backcheck_datetime_columns.index(default_backcheck_date)
                    if default_backcheck_date
                    and default_backcheck_date in backcheck_datetime_columns
                    else None
                )

                backcheck_date = st.selectbox(
                    "Backcheck Date",
                    options=backcheck_datetime_columns,
                    help="Select the column that contains the backcheck date",
                    key="backcheck_date_backchecks",
                    index=default_backcheck_date_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_backcheck_date"},
                )

        # Enumerator and Backchecker
        with st.container(border=True):
            st.subheader("Staff Identifiers")
            ec1, ec2, _ = st.columns(3)

            with ec1:
                default_enumerator = default_settings.enumerator
                default_enumerator_index = (
                    survey_categorical_columns.index(default_enumerator)
                    if default_enumerator and default_enumerator in survey_categorical_columns
                    else None
                )
                enumerator = st.selectbox(
                    "Enumerator",
                    options=survey_categorical_columns,
                    key="enumerator_backchecks",
                    help="Select the column that contains the enumerator ID",
                    index=default_enumerator_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_enumerator"},
                )
                save_check_settings(settings_file, TAB_NAME, {"enumerator": enumerator})

            with ec2:
                # Get backcheck columns for backchecker selection
                default_backchecker = default_settings.backchecker
                default_backchecker_index = (
                    backcheck_categorical_columns.index(default_backchecker)
                    if default_backchecker and default_backchecker in backcheck_categorical_columns
                    else None
                )
                backchecker = st.selectbox(
                    "Back Checker",
                    options=backcheck_categorical_columns,
                    key="backchecker_backchecks",
                    help="Select the column that contains the back checker ID",
                    index=default_backchecker_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_backchecker"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"backchecker": backchecker}
                )

        # Tracking Options
        with st.container(border=True):
            st.subheader("Tracking Options")

            to1, _, _ = st.columns(3)

            with to1:
                default_backcheck_goal = default_settings.backcheck_target_percent
                backcheck_goal = st.number_input(
                    "Target number of backchecks",
                    min_value=0,
                    help="Total number of backchecks expected",
                    key="backcheck_goal_backchecks",
                    value=default_backcheck_goal,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_backcheck_goal"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"backcheck_goal": backcheck_goal}
                )

        # Additional Options
        with st.container(border=True):
            st.subheader("Additional Options")

            with st.container(border=True):
                st.markdown("##### Duplicate Handling")
                st.write("How would you like to handle duplicates?")
                default_drop_duplicates = default_settings.drop_duplicates_option
                options_map = {"drop": ":material/remove_selection: Drop All Entries", "first": ":material/first_page: Keep First Entry", "last": ":material/last_page: Keep Last Entry"}
                drop_duplicates_option = st.pills(
                    "Select an option for handling duplicates",
                    options=list(options_map.keys()),
                    format_func=lambda x: options_map[x],
                    key="drop_duplicates_option_backchecks",
                    default=default_drop_duplicates,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_drop_duplicates_option"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"drop_duplicates_option": drop_duplicates_option}
                )

            with st.container(border=True):
                st.markdown("##### No differences Settings")
                st.write("Settings for entries values in backchecks that will not be marked as differences.")
                no_diff_values = _render_no_differences_settings(settings_file)

                if no_diff_values:
                    st.info("The following values will not be marked as differences:")
                    # save into a dataframe for better display
                    no_diff_df = pl.DataFrame({"Values": no_diff_values})
                    # configure column to be displayed as a list without index
                    dc1, _ = st.columns([1, 3])
                    dc1.dataframe(no_diff_df, hide_index=True, column_config={"Values": st.column_config.ListColumn("Values", help="Values that will not be marked as differences", width="content")})
                else:
                    st.warning("No values configured to be excluded from differences.")

            with st.container(border=True):
                st.markdown("##### Exclude Value Settings")
                st.write("Settings for entries values in backchecks that will be excluded from backcheck comparisons.")
                exclude_values = _render_exclude_values_settings(settings_file)
                if exclude_values:
                    st.info("The following values will be excluded from backcheck comparisons:")
                    # save into a dataframe for better display
                    exclude_df = pl.DataFrame({"Values": exclude_values})
                    # configure column to be displayed as a list without index
                    dr1, _ = st.columns([1, 3])
                    dr1.dataframe(exclude_df, hide_index=True, column_config={"Values": st.column_config.ListColumn("Values", help="Values that will be excluded from backcheck comparisons", width="content")})
                else:
                    st.warning("No values configured to be excluded from backcheck comparisons.")

            with st.container(border=True):
                st.markdown("##### String Comparison Settings")
                st.write("Settings for string comparison in backcheck comparisons.")
                string_comp_options: StrCompareOptions = _render_string_comparison_options(settings_file)

    return BackcheckSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        backcheck_date=backcheck_date,
        enumerator=enumerator,
        backchecker=backchecker,
        backcheck_goal=backcheck_goal,
        drop_duplicates=drop_duplicates_option,
        no_differences_list=no_diff_values,
        exclude_values_list=exclude_values,
        case_option=string_comp_options.case_option,
        trimspaces_option=string_comp_options.trimspaces_option,
        nosymbols_option=string_comp_options.nosymbols_option,
    )


# =============================================================================
# Backcheck Column Actions - UI Configuration
# =============================================================================



def _render_search_type_selection(
    common_columns: list[str],
) -> tuple[str, str | None, list[str], bool]:
    """Render search type selection UI for backcheck columns.

    Parameters
    ----------
    common_columns : list[str]
        List of columns common to both survey and backcheck data.

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

    if search_type == SearchType.EXACT.value:
        backcheck_cols_sel = st.multiselect(
            label="Select columns to configure for backcheck",
            options=common_columns,
            default=None,
            help="Select column or group of columns to configure for backcheck comparison.",
        )
        pattern, lock_cols = None, None
        return search_type, pattern, backcheck_cols_sel, lock_cols
    else:
        pattern = st.text_input(
            label="Enter pattern to match column names",
            placeholder="Enter pattern to match column names",
            help="Enter the pattern to match column names based on the "
            "selected search type.",
        )
        if pattern:
            backcheck_cols_patt = expand_col_names(
                common_columns, pattern, search_type=search_type
            )
        else:
            backcheck_cols_patt = []

        st.write(
            "**Columns Selected:** ",
            ", ".join(backcheck_cols_patt) if backcheck_cols_patt else "None",
        )
        return search_type, pattern, backcheck_cols_patt, None



def _render_backcheck_category_options() -> int:
    """Render backcheck category selection UI.

    Returns
    -------
    int
        Selected category (1, 2, or 3).
    """
    with st.container(border=True):
        st.markdown("##### Backcheck Category Selection")
        options_map = {1: ":material/looks_one: Category 1", 2: ":material/looks_two: Category 2", 3: ":material/looks_3: Category 3"}

        category = st.pills(
            "Select Backcheck Category",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            selection_mode="single",
            default=None,
            help="Select the backcheck category for the column(s).",
        )
    return category



def _render_ok_range_options() -> OkRangeOptions:
    """Render OK range options UI.

    Returns
    -------
    tuple[str, str]
        OK range type and OK range value.
    """
    with st.container(border=True):
        st.markdown("##### OK Range Selection")
        options_map = {"number": ":material/123: Value Range", "percentage": ":material/percent: Percentage Range"}
        ok_range_type = st.pills(
            "Select OK Range Type",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            selection_mode="single",
            default=None,
            help="Select the type of OK range condition for the column(s).",
            key="ok_range_type_backchecks_pills",
        )
        if ok_range_type:
            ok_range_value: OkRangeValues = _get_ok_range_value(OkRangeType(ok_range_type))
        else:
            ok_range_value = OkRangeValues(ok_range_neg=0.0, ok_range_pos=0.0)

    return OkRangeOptions(ok_range_type=ok_range_type, ok_range_value=ok_range_value)



def _render_backcheck_test_options(backcheck_category: int) -> BackcheckTestOptions:
    """Render backcheck test condition selection UI.

    Returns
    -------
    str
        Selected Back Check Test
    """
    with st.container(border=True):
        st.markdown("##### Statistical Test")
        with st.expander("Statisical Test Information", expanded=False):
            st.write(
                """
                Select the statistical test to apply for backcheck comparisons.

                - **ttest**: run paired two-sample mean-comparison tests for values in the back check and survey data.
                - **prtest**: run two-sample test of equality of proportions in the back check and survey data for dichotmous variables.
                - **signrank**: run Wilcoxon signed-rank tests for values in the back check and survey data.
                - **reliability**: calculate the simple response variance (SRV) and reliability ratio for type 2 and 3 variables.
                """
            )
        options_map = {
            "ttest": "t-test",
            "prtest": "prtest",
            "signrank": "sign rank test",
            "reliability": "reliability analysis",
        }

        # dont show reliability if category 1 is selected
        if backcheck_category == 1:
            options_map.pop("reliability")

        backcheck_test = st.pills(
            "Select Backcheck Statistical Test",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            selection_mode="multi",
            default="ttest",
            help="Select the statistical test to apply for backcheck comparisons.",
            key="backcheck_test_backchecks_pills",
        )

    return BackcheckTestOptions(ttest="ttest" in backcheck_test,
                         prtest="prtest" in backcheck_test,
                         signrank="signrank" in backcheck_test,
                         reliability="reliability" in backcheck_test)

@st.fragment



def _render_no_differences_settings(settings_file: str) -> list:
    """Render UI for managing values that won't be considered as discrepancies.

    This function allows users to add or remove values from a list. Values in this
    list will not be marked as differences during backcheck comparison, regardless
    of whether they appear in the survey or backcheck data.

    Parameters
    ----------
    settings_file : str
        Path to the settings file.
    tab_name : str
        Name of the tab/check (used as key in settings).
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME)
    updated_values = saved_settings.get("no_differences_values", [])
    ac_col, rc_col, _ = st.columns([0.4, 0.3, 0.3])
    with ac_col, st.popover("Add Value", type="primary", width="stretch"):
        new_value = st.text_input(
            "Enter value to exclude from differences",
            key="new_no_diff_value_input",
            help="Enter the value to be excluded from difference checks.",
        )
        # validate input and add to list
        if st.button(
            "Add Value",
            key="add_no_diff_value",
            help="Add the value to the no-differences list.",
            width="stretch",
            disabled=not new_value,
            type="primary",
            on_click=trigger_save,
            kwargs={"state_name": TAB_NAME + "_no_differences_values"},
        ):
            saved_settings = load_check_settings(settings_file, TAB_NAME)
            no_diff_values = saved_settings.get("no_differences_values", [])
            if no_diff_values:
                no_diff_values.append(new_value)
                updated_values = no_diff_values
            else:
                updated_values = [new_value]
            save_check_settings(
                settings_file,
                TAB_NAME,
                {"no_differences_values": updated_values},
            )
            st.rerun()

    with rc_col, st.popover("Remove Value", width="stretch"):
        saved_settings = load_check_settings(settings_file, TAB_NAME)
        no_diff_values = saved_settings.get("no_differences_values", [])
        if not no_diff_values:
            st.info("No values to remove.")
        value_to_remove = st.selectbox(
            "Select value to remove from no-differences list",
            options=no_diff_values,
            key="remove_no_diff_value_select",
            help="Select the value to remove from the no-differences list.",
            disabled=not no_diff_values,
        )
        if st.button(
            "Remove Value",
            key="remove_no_diff_value",
            help="Remove the selected value from the no-differences list.",
            width="stretch",
            type="primary",
            on_click=trigger_save,
            kwargs={"state_name": TAB_NAME + "_no_differences_value"},
        ):
            no_diff_values.remove(value_to_remove)
            updated_values = no_diff_values
            save_check_settings(
                settings_file,
                TAB_NAME,
                {"no_differences_values": updated_values},
            )
            st.rerun()

    return updated_values

@st.fragment



def _render_string_comparison_options(settings_file) -> StrCompareOptions:
    """Render string comparison options UI.

    Returns
    -------
    StrCompareOptions
        Selected string comparison options.
    """
    st.markdown("##### String Comparison Options")
    sok1, sok2, sok3 = st.columns(3)
    default_settings = load_check_settings(settings_file, TAB_NAME)
    default_case_setting = default_settings.get("string_case_option", None)
    options_map = {"lowercase": ":material/lowercase: lowercase", "uppercase": ":material/uppercase: UPPERCASE"}
    with sok1, st.container(border=True):
        string_case_option = st.pills(
            "Convert String Case Before Comparison",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            default=default_case_setting,
            key="string_case_option_backchecks_pills",
            help="Select how to handle case sensitivity in string comparisons.",
            selection_mode="single",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_string_case_option"},
        )
        save_check_settings(settings_file, TAB_NAME, {"string_case_option": string_case_option})

    with sok2, st.container(border=True):
        default_nosymbols_setting = default_settings.get("string_nosymbols_option", False)
        string_nosymbols_option = st.toggle(
            label="Ignore Symbols in String Comparison",
            value=default_nosymbols_setting,
            key="string_nosymbols_option_backchecks_toggle",
            help="Toggle to ignore symbols when comparing string values.",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_string_nosymbols_option"},
        )
        save_check_settings(settings_file, TAB_NAME, {"string_nosymbols_option": string_nosymbols_option})

    with sok3, st.container(border=True):
        default_trimspaces_setting = default_settings.get("string_trimspaces_option", False)
        string_trimspaces_option = st.toggle(
            label="Trim Spaces in String Comparison",
            value=default_trimspaces_setting,
            key="string_trimspaces_option_backchecks_toggle",
            help="Toggle to trim leading and trailing spaces when comparing string values.",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_string_trimspaces_option"},
        )
        save_check_settings(
            settings_file,
            TAB_NAME,
            {"string_trimspaces_option": string_trimspaces_option}
        )

    return StrCompareOptions(
        case_option=string_case_option,
        nosymbol_option=string_nosymbols_option,
        whitespace_option=string_trimspaces_option,
    )

@st.fragment



def _render_exclude_values_settings(
    settings_file: str
) -> list:
    """Render UI for managing values to exclude from backcheck comparison."""
    ac_col, rc_col, _ = st.columns([0.4, 0.3, 0.3])
    with ac_col, st.popover("Add Exclude Value", type="primary", width="stretch"):
        new_value = st.text_input(
            "Enter value to exclude from backcheck comparison",
            key="new_exclude_value_input",
            help="Enter the value to be excluded from backcheck comparison.",
        )
        # validate input and add to list
        saved_settings = load_check_settings(settings_file, TAB_NAME)
        exclude_values = saved_settings.get("exclude_values", [])
        updated_values = exclude_values
        if st.button(
            "Add Exclude Value",
            key="add_exclude_value",
            help="Add the value to the exclude list.",
            width="stretch",
            disabled=not new_value,
            type="primary",
            on_click=trigger_save,
            kwargs={"state_name": TAB_NAME + "_exclude_values"},
        ):
            saved_settings = load_check_settings(settings_file, TAB_NAME)
            exclude_values = saved_settings.get("exclude_values", [])
            if exclude_values:
                exclude_values.append(new_value)
                updated_values = exclude_values
            else:
                updated_values = [new_value]
            save_check_settings(
                settings_file,
                TAB_NAME,
                {"exclude_values": updated_values},
            )
            st.rerun()

    with rc_col, st.popover("Remove Exclude Value", width="stretch"):
        if not exclude_values:
            st.info("No values to remove.")
        value_to_remove = st.selectbox(
            "Select value to remove from exclude list",
            options=exclude_values,
            key="remove_exclude_value_select",
            help="Select the value to remove from the exclude list.",
            disabled=not exclude_values,
        )
        if st.button(
            "Remove Exclude Value",
            key="remove_exclude_value",
            help="Remove the selected value from the exclude list.",
            width="stretch",
            type="primary",
            on_click=trigger_save,
            kwargs={"state_name": TAB_NAME + "_exclude_values"},
        ):
            saved_settings = load_check_settings(settings_file, TAB_NAME)
            exclude_values = saved_settings.get("exclude_values", [])
            if value_to_remove in exclude_values:
                exclude_values.remove(value_to_remove)
                updated_values = exclude_values
                save_check_settings(
                    settings_file,
                    TAB_NAME,
                    {"exclude_values": updated_values},
                )
                st.rerun()

    return updated_values





# ==============================================================================
# RESULTS DISPLAY RENDER FUNCTIONS
# ==============================================================================


def _render_backcheck_summary(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    backcheck_analysis: pl.DataFrame,
    backcheck_settings: BackcheckSettings,
) -> None:
    """Render summary metrics for backcheck analysis.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    backcheck_analysis : pl.DataFrame
        Results from compute_backcheck_analysis.
    backcheck_settings : BackcheckSettings
        Backcheck settings including enumerator and backchecker columns.
    """
    # Calculate basic metrics
    n_survey_obs = len(survey_data)
    n_backcheck_obs = len(backcheck_data)

    # Calculate percentage of surveys with backcheck responses
    # Get unique survey keys that have backchecks
    survey_key = backcheck_settings.survey_key
    if survey_key and not backcheck_analysis.is_empty():
        unique_backchecked_surveys = backcheck_analysis[survey_key].n_unique()
        backcheck_coverage_pct = (unique_backchecked_surveys / n_survey_obs * 100) if n_survey_obs > 0 else 0
    else:
        backcheck_coverage_pct = 0

    # Count unique enumerators and back checkers
    enumerator_col = backcheck_settings.enumerator
    backchecker_col = backcheck_settings.backchecker

    if enumerator_col and enumerator_col in survey_data.columns:
        n_enumerators = survey_data[enumerator_col].n_unique()
    else:
        n_enumerators = 0

    if backchecker_col and backchecker_col in backcheck_data.columns:
        n_backcheckers = backcheck_data[backchecker_col].n_unique()
    else:
        n_backcheckers = 0

    # Display metrics in columns
    uc1, uc2, uc3, _ = st.columns(4)
    lc1, lc2, _, _ = st.columns(4)

    with uc1, st.container(border=True):
        st.metric("Survey Observations", f"{n_survey_obs:,}")

    with uc2, st.container(border=True):
        st.metric("Backcheck Observations", f"{n_backcheck_obs:,}")

    with uc3, st.container(border=True):

        st.metric(
            "Backcheck Coverage",
            f"{backcheck_coverage_pct:.1f}%",
        )

    with lc1, st.container(border=True):
        st.metric("Total Enumerators", f"{n_enumerators:,}" if n_enumerators > 0 else "N/A")

    with lc2, st.container(border=True):
        st.metric("Total Back Checkers", f"{n_backcheckers:,}" if n_backcheckers > 0 else "N/A")



def _render_backchecker_productivity(
    data: pl.DataFrame,
    date: str,
    backchecker: str,
    settings_file: str,
) -> None:
    """Display backchecker productivity table.

    Shows backcheck submission counts by backchecker over time with configurable
    time periods (daily, weekly, monthly).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing backcheck data.
    date : str
        Date column name.
    backchecker : str
        Backchecker column name.
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    if not (backchecker and date):
        st.info(
            "Backchecker productivity requires a date and backchecker column to be selected. "
            "Go to the :material/settings: settings section above to select them."
        )
        return

    _render_backchecker_productivity_table(
        data, date, backchecker, settings_file
    )


@st.fragment



def _render_backchecker_productivity_table(
    data: pl.DataFrame,
    date: str,
    backchecker: str,
    settings_file: str,
) -> None:
    """Display backchecker productivity table.

    Shows backcheck submission counts by backchecker over time with configurable
    time periods (daily, weekly, monthly).

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing backcheck data.
    date : str
        Date column name.
    backchecker : str
        Backchecker column name.
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    time_period = _render_time_period_selector_backchecks(settings_file)
    if time_period == "Week":
        weekstartday = _render_weekday_selector_backchecks(settings_file)
    else:
        weekstartday = "MON"  # Default value, not used for non-weekly periods

    group_by_cols = [backchecker]
    productivity_df = compute_backchecker_productivity(
        data, date, group_by_cols, time_period, weekstartday
    )

    column_config = {
        backchecker: st.column_config.TextColumn("Back Checker", pinned=True),
    }

    column_config.update({
        col: st.column_config.NumberColumn(col, format="%d") for col in productivity_df.columns
        if col not in group_by_cols
    })

    st.dataframe(productivity_df, hide_index=True, use_container_width=True, column_config=column_config)



def _render_time_period_selector_backchecks(
    settings_file: str,
) -> Literal["Day", "Week", "Month"]:
    """Render time period selector widget using pills interface for backchecks.

    Displays a pills widget allowing users to choose the time aggregation period
    for backchecker productivity analysis (Day, Week, or Month).

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading configurations.

    Returns
    -------
    Literal["Day", "Week", "Month"]
        Selected time period.
    """
    options_map = {"Day": ":material/event: Daily", "Week": ":material/date_range: Weekly", "Month": ":material/calendar_month: Monthly"}

    saved_settings = load_check_settings(settings_file, TAB_NAME) or {}
    default_time_period = saved_settings.get("time_period_backchecker_productivity", "Day")

    with st.container(horizontal_alignment="left"):
        time_period = st.pills(
                label="Time Period",
                options=options_map.keys(),
                format_func=lambda x: options_map[x],
                key="time_period_backchecker_productivity_key",
                default=default_time_period,
                help="Select time period for aggregating backchecker productivity",
                selection_mode="single",
                on_change=trigger_save,
                kwargs={"state_name": TAB_NAME + "_time_period_backchecker"},
            )
        save_check_settings(
                settings_file, TAB_NAME, {"time_period_backchecker_productivity": time_period}
            )

    return time_period or "Day"



def _render_weekday_selector_backchecks(
    settings_file: str,
) -> str:
    """Render weekday selector widget for backchecker productivity analysis.

    Displays a selectbox allowing users to choose the first day of the week
    for weekly productivity calculations.

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading configurations.

    Returns
    -------
    str
        Weekday offset code (e.g., "SUN", "MON") for calculations.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME) or {}
    default_weekstartday_sel = saved_settings.get("weekstartday_backchecker_productivity", "Monday")
    default_weekstartday_sel_index = WEEKDAY_NAMES.index(default_weekstartday_sel)

    cl1, _ = st.columns([1, 3])
    with cl1:
        weekstartday_sel = st.selectbox(
            label="Select the first day of the week",
            options=WEEKDAY_NAMES,
            index=default_weekstartday_sel_index,
            key="week_start_day_backchecker_productivity_key",
            help="Select the first day of the week",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_weekstartday_backchecker"},
        )
    save_check_settings(
        settings_file, TAB_NAME, {"weekstartday_backchecker_productivity": weekstartday_sel}
    )

    return WEEKDAY_OFFSET_MAP[weekstartday_sel]



def _render_enum_bcer_stats(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    backcheck_analysis: pl.DataFrame,
    backcheck_settings: BackcheckSettings,
    settings_file: str,
) -> None:
    """Render enumerator and backchecker error rate statistics.

    Displays statistics tables showing error rates by category for either
    enumerators or backcheckers, with a pills selector to switch between views.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    backcheck_analysis : pl.DataFrame
        Results from compute_backcheck_analysis.
    backcheck_settings : BackcheckSettings
        Backcheck settings.
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    if backcheck_analysis.is_empty():
        st.info("No backcheck analysis results available. Configure backcheck columns in the settings section above.")
        return

    # Check if required columns are configured
    enumerator_col = backcheck_settings.enumerator
    backchecker_col = backcheck_settings.backchecker

    if not enumerator_col and not backchecker_col:
        st.info(
            "Enumerator and backchecker columns are required. "
            "Go to the :material/settings: settings section above to configure them."
        )
        return

    _render_enum_bcer_stats_table(
        survey_data, backcheck_data, backcheck_analysis, backcheck_settings, settings_file
    )


@st.fragment



def _render_enum_bcer_stats_table(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    backcheck_analysis: pl.DataFrame,
    backcheck_settings: BackcheckSettings,
    settings_file: str,
) -> None:
    """Render enumerator and backchecker statistics table with pills selector.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    backcheck_analysis : pl.DataFrame
        Results from compute_backcheck_analysis.
    backcheck_settings : BackcheckSettings
        Backcheck settings.
    settings_file : str
        Path to settings file for saving/loading configurations.
    """
    # Determine available options
    enumerator_col = backcheck_settings.enumerator
    backchecker_col = backcheck_settings.backchecker

    options = ["Enumerator", "Backchecker"]

    # Pills selector
    saved_settings = load_check_settings(settings_file, TAB_NAME) or {}
    default_view = saved_settings.get("enum_bcer_stats_view", options[0])

    view_selection = st.pills(
        label="View Statistics",
        options=options,
        default=default_view,
        key="enum_bcer_stats_view_key",
        help="Select which statistics to view",
        selection_mode="single",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_enum_bcer_stats_view"},
    )
    save_check_settings(
        settings_file, TAB_NAME, {"enum_bcer_stats_view": view_selection}
    )

    # Compute and display statistics
    staff_type = "enumerator" if view_selection == "Enumerator" else "backchecker"
    stats_df = compute_enumerator_backchecker_stats(
        survey_data, backcheck_data, backcheck_analysis, backcheck_settings, staff_type
    )

    if stats_df.is_empty():
        st.info(f"No {view_selection.lower()} statistics available.")
        return

    # Get staff column name for display
    staff_col = enumerator_col if staff_type == "enumerator" else backchecker_col

    # Configure columns for wide format
    column_config = {
        staff_col: st.column_config.TextColumn(view_selection, pinned=True),
        "Surveys": st.column_config.NumberColumn("Surveys", format="%d"),
        "Backchecks": st.column_config.NumberColumn("Backchecks", format="%d"),
        "Avg Days": st.column_config.NumberColumn("Avg Days", format="%.1f"),
    }

    # Add category-specific columns
    for category in [1, 2, 3]:
        column_config[f"Non-Missing Survey (Cat {category})"] = st.column_config.NumberColumn(
            f"Survey Values (Cat {category})", format="%d"
        )
        column_config[f"Non-Missing Backcheck (Cat {category})"] = st.column_config.NumberColumn(
            f"Backcheck Values (Cat {category})", format="%d"
        )
        column_config[f"Values Compared (Cat {category})"] = st.column_config.NumberColumn(
            f"Compared (Cat {category})", format="%d"
        )
        column_config[f"Mismatches (Cat {category})"] = st.column_config.NumberColumn(
            f"Mismatches (Cat {category})", format="%d"
        )
        column_config[f"Error Rate % (Cat {category})"] = st.column_config.NumberColumn(
            f"Error % (Cat {category})", format="%.2f"
        )

    # Add total columns
    column_config["Non-Missing Survey (Total)"] = st.column_config.NumberColumn(
        "Survey Values (Total)", format="%d"
    )
    column_config["Non-Missing Backcheck (Total)"] = st.column_config.NumberColumn(
        "Backcheck Values (Total)", format="%d"
    )
    column_config["Values Compared (Total)"] = st.column_config.NumberColumn(
        "Compared (Total)", format="%d"
    )
    column_config["Mismatches (Total)"] = st.column_config.NumberColumn(
        "Mismatches (Total)", format="%d"
    )
    column_config["Error Rate % (Total)"] = st.column_config.NumberColumn(
        "Error % (Total)", format="%.2f"
    )

    st.dataframe(
        stats_df,
        hide_index=True,
        use_container_width=True,
        column_config=column_config
    )



def _render_column_stats(
    survey_data: pl.DataFrame,
    backcheck_analysis: pl.DataFrame,
) -> None:
    """Render column statistics for backcheck analysis.

    Displays a table showing statistics for each column configured
    for backcheck analysis.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_analysis : pl.DataFrame
        Results from compute_backcheck_analysis.
    """
    if backcheck_analysis.is_empty():
        st.info("No backcheck analysis results available. Configure backcheck columns in the settings section above.")
        return

    # Compute column statistics
    stats_df = compute_column_stats(survey_data, backcheck_analysis)

    if stats_df.is_empty():
        st.info("No column statistics available.")
        return

    # Configure columns
    column_config = {
        "Column Name": st.column_config.TextColumn("Column Name", pinned=True),
        "Category": st.column_config.NumberColumn("Category", format="%d"),
        "Data Type": st.column_config.TextColumn("Data Type"),
        "# of Values": st.column_config.NumberColumn("# of Values", format="%d"),
        "Values Compared": st.column_config.NumberColumn("Values Compared", format="%d"),
        "Mismatches": st.column_config.NumberColumn("Mismatches", format="%d"),
        "Error Rate (%)": st.column_config.NumberColumn("Error Rate (%)", format="%.2f"),
        "Test Results": st.column_config.TextColumn("Test Results", width="large"),
    }

    st.dataframe(
        stats_df,
        hide_index=True,
        use_container_width=True,
        column_config=column_config
    )

@st.fragment



def _render_backcheck_comparison_results(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    backcheck_analysis: pl.DataFrame,
    backcheck_settings: BackcheckSettings,
) -> None:
    """Render detailed backcheck comparison results with filtering options.

    Displays a table showing each individual comparison with options to filter
    by match status, select specific columns, and add additional data columns.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    backcheck_analysis : pl.DataFrame
        Results from compute_backcheck_analysis.
    backcheck_settings : BackcheckSettings
        Backcheck configuration settings.
    """
    if backcheck_analysis.is_empty():
        st.info("No backcheck comparison results available. Configure backcheck columns in the settings section above.")
        return

    survey_key = backcheck_settings.survey_key
    survey_id = backcheck_settings.survey_id
    backcheck_key = f"{survey_key}__BCCL"

    # Get available columns from backcheck_analysis
    available_columns = sorted(backcheck_analysis["column_name"].unique().drop_nulls().to_list())

    if not available_columns:
        st.info("No comparison results available.")
        return

    # Column filter
    selected_columns = st.multiselect(
        "Filter by Columns",
        options=available_columns,
        default=available_columns,
        help="Select which columns to show comparison results for"
    )

    # Additional columns selection in expander
    with st.expander("Show Additional Columns", expanded=False):
        col1, col2 = st.columns(2)

        # Get available additional columns (exclude keys and analysis columns)
        survey_additional_cols = [
            col for col in survey_data.columns
            if col not in [survey_key, survey_id, "column_name", "survey_value", "backcheck_value", "match_status", "category"]
            and col not in backcheck_analysis.columns
        ]

        backcheck_additional_cols = [
            col for col in backcheck_data.columns
            if col not in [survey_key, survey_id, "column_name", "survey_value", "backcheck_value", "match_status", "category"]
            and col not in backcheck_analysis.columns
        ]

        with col1:
            survey_extra_cols = st.multiselect(
                "Additional Survey Columns",
                options=sorted(survey_additional_cols),
                help="Select additional columns from survey data to display"
            )

        with col2:
            backcheck_extra_cols = st.multiselect(
                "Additional Backcheck Columns",
                options=sorted(backcheck_additional_cols),
                help="Select additional columns from backcheck data to display"
            )

    # Match status filter as pills - placed at top left
    match_filter = st.pills(
        "Filter by Match Status",
        options=["All Results", "Mismatches Only"],
        default="All Results",
        selection_mode="single"
    )

    # Apply filters
    filtered_data = backcheck_analysis.clone()

    # Filter by match status
    if match_filter == "Mismatches Only":
        filtered_data = filtered_data.filter(pl.col("match_status") == "mismatch")

    # Filter by selected columns
    if selected_columns:
        filtered_data = filtered_data.filter(pl.col("column_name").is_in(selected_columns))

    if filtered_data.is_empty():
        st.info("No results match the selected filters.")
        return

    # Add additional survey columns if requested
    if survey_extra_cols:
        # Prepare survey columns with unique names
        survey_cols_to_add = survey_data.select([survey_key] + survey_extra_cols).unique(subset=[survey_key])
        # Suffix survey columns to avoid conflicts
        rename_map = {col: f"{col} (Survey)" for col in survey_extra_cols}
        survey_cols_to_add = survey_cols_to_add.rename(rename_map)
        filtered_data = filtered_data.join(survey_cols_to_add, on=survey_key, how="left")

    # Add additional backcheck columns if requested
    if backcheck_extra_cols and backcheck_key in filtered_data.columns:
        # Prepare backcheck columns with unique names
        backcheck_cols_to_add = backcheck_data.select([survey_key] + backcheck_extra_cols).unique(subset=[survey_key])
        # Rename to match backcheck key and suffix column names
        backcheck_cols_to_add = backcheck_cols_to_add.rename({survey_key: backcheck_key})
        rename_map = {col: f"{col} (Backcheck)" for col in backcheck_extra_cols}
        backcheck_cols_to_add = backcheck_cols_to_add.rename(rename_map)
        filtered_data = filtered_data.join(backcheck_cols_to_add, on=backcheck_key, how="left")

    # Select only the specific columns to display
    display_columns = [
        "column_name",
        "survey_value",
        "backcheck_value",
        "match_status",
        "category"
    ]

    # Add survey_id if it exists in the data
    if survey_id and survey_id in filtered_data.columns:
        display_columns.insert(0, survey_id)

    # Add survey_key if it exists
    if survey_key in filtered_data.columns:
        display_columns.insert(1 if survey_id in display_columns else 0, survey_key)

    # Add backcheck_key if it exists
    if backcheck_key in filtered_data.columns:
        display_columns.insert(2 if survey_id in display_columns else 1, backcheck_key)

    # Add any additional columns requested
    for col in filtered_data.columns:
        if col not in display_columns and (col.endswith("(Survey)") or col.endswith("(Backcheck)")):
            display_columns.append(col)

    # Filter to only include columns that exist in the data
    display_columns = [col for col in display_columns if col in filtered_data.columns]

    # Select only the display columns and remove any completely empty rows
    filtered_data = filtered_data.select(display_columns)

    # Remove rows where both survey_value and backcheck_value are null
    filtered_data = filtered_data.filter(
        ~(pl.col("survey_value").is_null() & pl.col("backcheck_value").is_null())
    )

    if filtered_data.is_empty():
        st.info("No results match the selected filters.")
        return

    # Display record count
    st.caption(f"Showing {len(filtered_data):,} comparison records")

    # Configure columns for display
    column_config = {
        "column_name": st.column_config.TextColumn("Column Name"),
        "survey_value": st.column_config.TextColumn("Survey Value"),
        "backcheck_value": st.column_config.TextColumn("Backcheck Value"),
        "match_status": st.column_config.TextColumn("Match Status"),
        "category": st.column_config.NumberColumn("Category", format="%d"),
    }

    # Add survey_id to config if it exists (pinned)
    if survey_id and survey_id in filtered_data.columns:
        column_config[survey_id] = st.column_config.TextColumn(survey_id, pinned=True)

    # Add survey_key to config if it exists
    if survey_key in filtered_data.columns:
        column_config[survey_key] = st.column_config.TextColumn("Survey Key")

    # Add backcheck key to config if it exists
    if backcheck_key in filtered_data.columns:
        column_config[backcheck_key] = st.column_config.TextColumn("Backcheck Key")

    # Display the table
    st.dataframe(
        filtered_data,
        hide_index=True,
        use_container_width=True,
        column_config=column_config,
    )





# ==============================================================================
# MAIN ENTRY POINT
# ==============================================================================


def backchecks_report(
    project_id: str,
    page_name_id: str,
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    setting_file: str,
    config: dict,
    survey_columns: ColumnByType,
    backcheck_columns: ColumnByType,
) -> None:
    """
    Generate and display backchecks report.

    Parameters
    ----------
    project_id : str
        Project identifier.
    page_name_id : str
        Page name identifier.
    survey_data : pl.DataFrame
        Survey data.
    backcheck_data : pl.DataFrame
        Backcheck data.
    setting_file : str
        Path to the settings file.
    config : dict
        Configuration dictionary.
    """
    st.title("Backchecks Report")

    # Convert Polars DataFrames to Pandas for compatibility
    survey_data_pd = survey_data.to_pandas()
    backcheck_data_pd = backcheck_data.to_pandas()

    # Get column information for settings UI
    survey_categorical_columns = survey_columns.categorical_columns
    survey_datetime_columns = survey_columns.datetime_columns

    backcheck_categorical_columns = backcheck_columns.categorical_columns
    backcheck_datetime_columns = backcheck_columns.datetime_columns

    # Configure settings
    config_settings = BackcheckSettings(**config)
    backcheck_settings = backchecks_report_settings(
        project_id,
        setting_file,
        survey_data_pd,
        backcheck_data_pd,
        config_settings,
        survey_categorical_columns,
        survey_datetime_columns,
        backcheck_categorical_columns,
        backcheck_datetime_columns,
    )

    # Outlier columns configuration
    st.subheader("Backchecks Columns Configuration")
    common_columns = list(
        set(survey_categorical_columns).intersection(
            set(backcheck_categorical_columns)
        )
    )
    _render_backchecks_column_actions(project_id, page_name_id, survey_data, backcheck_data, common_columns)

    # Compute backcheck analysis
    backcheck_column_settings = duckdb_get_table(
        project_id,
        f"backchecks_{page_name_id}",
        "logs",
    )
    _backcheck_analysis = compute_backcheck_analysis(survey_data, backcheck_data, backcheck_settings, backcheck_column_settings)

    st.subheader("Backchecks Summary")
    _render_backcheck_summary(survey_data, backcheck_data, _backcheck_analysis, backcheck_settings)

    _render_backchecker_productivity(
        backcheck_data,
        backcheck_settings.backcheck_date,
        backcheck_settings.backchecker,
        setting_file,
    )

    st.subheader("Enumerator Backchecker Error Statistics")

    _render_enum_bcer_stats(
        survey_data,
        backcheck_data,
        _backcheck_analysis,
        backcheck_settings,
        setting_file
    )

    st.subheader("Column Statistics")
    _render_column_stats(survey_data, _backcheck_analysis)

    st.subheader("Comparison Results Details")
    _render_backcheck_comparison_results(
        survey_data,
        backcheck_data,
        _backcheck_analysis,
        backcheck_settings
    )

