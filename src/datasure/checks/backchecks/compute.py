"""Pure data-computation functions for the backchecks module."""

import re
from contextlib import suppress
from typing import Any

import polars as pl
from scipy import stats

from datasure.checks.backchecks.models import (
    TAB_NAME,
    WEEKDAY_OFFSET_TO_NUMERIC,
    BackcheckSettings,
    SearchType,
)
from datasure.utils.settings_utils import load_check_settings

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


# ==============================================================================
# CORE COMPUTATION FUNCTIONS
# ==============================================================================


def _validate_backcheck_inputs(
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    backcheck_settings: BackcheckSettings,
    backcheck_column_settings: pl.DataFrame,
) -> tuple[str, str] | None:
    """Validate backcheck analysis inputs and extract required keys.

    Parameters
    ----------
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    backcheck_settings : BackcheckSettings
        Global settings for backcheck comparison.
    backcheck_column_settings : pl.DataFrame
        Column-specific settings.

    Returns
    -------
    tuple[str, str] | None
        Tuple of (survey_key, survey_id) if valid, None otherwise.
    """
    if backcheck_column_settings.is_empty():
        return None

    survey_key = backcheck_settings.survey_key
    if not survey_key or survey_key not in survey_data.columns:
        return None

    survey_id = backcheck_settings.survey_id
    if (
        not survey_id
        or survey_id not in survey_data.columns
        or survey_id not in backcheck_data.columns
    ):
        return None

    return survey_key, survey_id


def _prepare_data_for_merge(
    data: pl.DataFrame, survey_id: str, drop_duplicates_option: str
) -> pl.DataFrame:
    """Prepare dataset for merge by handling duplicates according to settings.

    Parameters
    ----------
    data : pl.DataFrame
        Dataset to prepare.
    survey_id : str
        Column name to use for duplicate detection.
    drop_duplicates_option : str
        How to handle duplicates: 'first', 'last', 'drop', or 'none'.

    Returns
    -------
    pl.DataFrame
        Prepared dataset with duplicates handled.
    """
    prepared_data = data.clone()

    if drop_duplicates_option == "first":
        return prepared_data.unique(subset=[survey_id], keep="first")

    if drop_duplicates_option == "last":
        return prepared_data.unique(subset=[survey_id], keep="last")

    if drop_duplicates_option == "drop":
        # Keep only non-duplicate rows
        duplicates = (
            prepared_data.group_by(survey_id).len().filter(pl.col("len") > 1)[survey_id]
        )
        return prepared_data.filter(~pl.col(survey_id).is_in(duplicates))

    return prepared_data


def _add_statistical_test_columns(
    col_results: pl.DataFrame, test_results: dict[str, dict[str, Any]] | None
) -> pl.DataFrame:
    """Add statistical test result columns to comparison results.

    Parameters
    ----------
    col_results : pl.DataFrame
        Column comparison results.
    test_results : dict[str, dict[str, Any]] | None
        Statistical test results, or None if no tests configured.

    Returns
    -------
    pl.DataFrame
        Results with test columns added.
    """
    if test_results:
        return col_results.with_columns(
            [
                pl.lit(test_results.get("ttest", {}).get("t_statistic")).alias(
                    "ttest_t_statistic"
                ),
                pl.lit(test_results.get("ttest", {}).get("p_value")).alias(
                    "ttest_p_value"
                ),
                pl.lit(test_results.get("prtest", {}).get("z_statistic")).alias(
                    "prtest_z_statistic"
                ),
                pl.lit(test_results.get("prtest", {}).get("p_value")).alias(
                    "prtest_p_value"
                ),
                pl.lit(test_results.get("signrank", {}).get("statistic")).alias(
                    "signrank_statistic"
                ),
                pl.lit(test_results.get("signrank", {}).get("p_value")).alias(
                    "signrank_p_value"
                ),
                pl.lit(
                    test_results.get("skipped_tests", {}).get("signrank"),
                    dtype=pl.Utf8,
                ).alias("signrank_skipped"),
                pl.lit(test_results.get("reliability", {}).get("srv")).alias(
                    "reliability_srv"
                ),
                pl.lit(
                    test_results.get("reliability", {}).get("reliability_ratio")
                ).alias("reliability_ratio"),
            ]
        )

    # Add null test result columns to maintain schema consistency
    return col_results.with_columns(
        [
            pl.lit(None).alias("ttest_t_statistic"),
            pl.lit(None).alias("ttest_p_value"),
            pl.lit(None).alias("prtest_z_statistic"),
            pl.lit(None).alias("prtest_p_value"),
            pl.lit(None).alias("signrank_statistic"),
            pl.lit(None).alias("signrank_p_value"),
            pl.lit(None, dtype=pl.Utf8).alias("signrank_skipped"),
            pl.lit(None).alias("reliability_srv"),
            pl.lit(None).alias("reliability_ratio"),
        ]
    )


def _process_backcheck_column(
    merged_data: pl.DataFrame,
    survey_key: str,
    col: str,
    category: str,
    ok_range_type: str | None,
    ok_range_values: list | None,
    no_diff_list: list,
    exclude_list: list,
    case_option: str,
    trim_spaces: bool,
    no_symbols: bool,
    ttest: bool,
    prtest: bool,
    signrank: bool,
    reliability: bool,
) -> pl.DataFrame | None:
    """Process comparison for a single column.

    Parameters
    ----------
    merged_data : pl.DataFrame
        Merged survey and backcheck data.
    survey_key : str
        Survey identifier column name.
    col : str
        Column name to process.
    category : str
        Column category (numeric/text).
    ok_range_type : str | None
        Type of OK range.
    ok_range_values : list | None
        OK range values.
    no_diff_list : list
        List of values to treat as no difference.
    exclude_list : list
        List of values to exclude.
    case_option : str
        Case sensitivity option.
    trim_spaces : bool
        Whether to trim spaces.
    no_symbols : bool
        Whether to remove symbols.
    ttest : bool
        Whether to run t-test.
    prtest : bool
        Whether to run proportion test.
    signrank : bool
        Whether to run signed-rank test.
    reliability : bool
        Whether to calculate reliability metrics.

    Returns
    -------
    pl.DataFrame | None
        Comparison results for the column, or None if column not found.
    """
    if col not in merged_data.columns:
        return None

    backcheck_col = f"{col}__BCCL"
    if backcheck_col not in merged_data.columns:
        return None

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
    test_results = None
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

    return _add_statistical_test_columns(col_results, test_results)


def _expand_columns_if_needed(
    search_type: str,
    pattern: str | None,
    columns: list[str],
    survey_data: pl.DataFrame,
    survey_key: str,
) -> list[str]:
    """Expand column list if pattern-based search is configured.

    Parameters
    ----------
    search_type : str
        Type of search (exact, startswith, endswith, contains, regex).
    pattern : str | None
        Pattern to match.
    columns : list[str]
        Original column list.
    survey_data : pl.DataFrame
        Survey data to get column names from.
    survey_key : str
        Survey key column to exclude.

    Returns
    -------
    list[str]
        Expanded column list.
    """
    if search_type != SearchType.EXACT.value and pattern:
        survey_cols = [col for col in survey_data.columns if col != survey_key]
        return expand_col_names(survey_cols, pattern, search_type)
    return columns


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
    # Validate inputs
    validation_result = _validate_backcheck_inputs(
        survey_data, backcheck_data, backcheck_settings, backcheck_column_settings
    )
    if validation_result is None:
        return pl.DataFrame()

    survey_key, survey_id = validation_result

    # Prepare datasets for merge
    drop_duplicates_option = backcheck_settings.drop_duplicates_option
    survey_for_merge = _prepare_data_for_merge(
        survey_data, survey_id, drop_duplicates_option
    )
    backcheck_for_merge = _prepare_data_for_merge(
        backcheck_data, survey_id, drop_duplicates_option
    )

    # Merge datasets on survey id
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
        # Extract row settings
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
        columns = _expand_columns_if_needed(
            search_type, pattern, columns, survey_data, survey_key
        )

        # Process each column
        for col in columns:
            col_results = _process_backcheck_column(
                merged_data,
                survey_key,
                col,
                category,
                ok_range_type,
                ok_range_values,
                no_diff_list,
                exclude_list,
                case_option,
                trim_spaces,
                no_symbols,
                ttest,
                prtest,
                signrank,
                reliability,
            )

            if col_results is not None:
                results.append(col_results)

    # Combine all results
    if results:
        return pl.concat(results, how="vertical_relaxed")
    return pl.DataFrame()


def compute_backchecker_productivity(
    data: pl.DataFrame,
    date: str,
    group_by_cols: list[str],
    period: str,
    weekstartday: str,
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
        prod_df = prod_df.with_columns(
            [
                # Calculate days since the start of the week
                ((pl.col(date).dt.weekday() - offset + 7) % 7).alias(
                    "_days_since_week_start"
                ),
            ]
        )

        # Calculate week_start_date by subtracting days_since_week_start
        prod_df = prod_df.with_columns(
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

        # Format as "Jan 1, 2025 to Jan 7, 2025"
        prod_df = prod_df.with_columns(
            (
                pl.col("_week_start").dt.strftime("%b %d, %Y")
                + " to "
                + pl.col("_week_end").dt.strftime("%b %d, %Y")
            ).alias("TIME PERIOD")
        )
    elif period_normalized == "Monthly":
        # Format as "January 2025"
        prod_df = prod_df.with_columns(
            pl.col(date).dt.strftime("%B %Y").alias("TIME PERIOD")
        )

    # Count submissions per period and backchecker
    prod_df = prod_df.with_row_index(name="TOKEN KEY")
    prod_res = prod_df.group_by(
        ["TIME PERIOD"] + group_by_cols, maintain_order=True
    ).agg(pl.col("TOKEN KEY").count().alias("submissions"))

    # Pivot to wide format
    prod_res = prod_res.pivot(
        index=group_by_cols,
        on="TIME PERIOD",
        values="submissions",
    ).fill_null(0)

    return prod_res


def _get_staff_configuration(
    staff_type: str,
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    backcheck_settings: BackcheckSettings,
    survey_key: str,
) -> tuple[str, pl.DataFrame, str] | None:
    """Get staff column configuration based on staff type.

    Parameters
    ----------
    staff_type : str
        Either "enumerator" or "backchecker".
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    backcheck_settings : BackcheckSettings
        Backcheck settings.
    survey_key : str
        Survey key column name.

    Returns
    -------
    tuple[str, pl.DataFrame, str] | None
        Tuple of (staff_col, data_source, join_key) if valid, None otherwise.
    """
    if staff_type == "enumerator":
        staff_col = backcheck_settings.enumerator
        data_source = survey_data
        join_key = survey_key
    else:  # backchecker
        staff_col = backcheck_settings.backchecker
        data_source = backcheck_data
        join_key = f"{survey_key}__BCCL"

    if not staff_col or staff_col not in data_source.columns:
        return None

    return staff_col, data_source, join_key


def _join_staff_information(
    backcheck_analysis: pl.DataFrame,
    data_source: pl.DataFrame,
    staff_col: str,
    survey_key: str,
    join_key: str,
    staff_type: str,
) -> pl.DataFrame:
    """Join backcheck analysis with staff information.

    Parameters
    ----------
    backcheck_analysis : pl.DataFrame
        Backcheck analysis results.
    data_source : pl.DataFrame
        Source dataset (survey or backcheck).
    staff_col : str
        Staff column name.
    survey_key : str
        Survey key column name.
    join_key : str
        Key to join on.
    staff_type : str
        Either "enumerator" or "backchecker".

    Returns
    -------
    pl.DataFrame
        Analysis joined with staff information.
    """
    staff_info = data_source.select([survey_key, staff_col]).unique(subset=[survey_key])

    if staff_type == "enumerator":
        return backcheck_analysis.join(staff_info, on=survey_key, how="left")

    # For backcheckers, rename survey_key to match backcheck key
    staff_info = staff_info.rename({survey_key: join_key})
    return backcheck_analysis.join(staff_info, on=join_key, how="left")


def _add_date_columns(
    analysis_with_staff: pl.DataFrame,
    survey_data: pl.DataFrame,
    backcheck_data: pl.DataFrame,
    survey_key: str,
    survey_date: str | None,
    backcheck_date: str | None,
) -> pl.DataFrame:
    """Add survey and backcheck date columns to analysis.

    Parameters
    ----------
    analysis_with_staff : pl.DataFrame
        Analysis with staff information.
    survey_data : pl.DataFrame
        Survey dataset.
    backcheck_data : pl.DataFrame
        Backcheck dataset.
    survey_key : str
        Survey key column name.
    survey_date : str | None
        Survey date column name.
    backcheck_date : str | None
        Backcheck date column name.

    Returns
    -------
    pl.DataFrame
        Analysis with date columns added.
    """
    result = analysis_with_staff

    # Add survey date
    if survey_date and survey_date in survey_data.columns:
        survey_dates = survey_data.select(
            [survey_key, pl.col(survey_date).alias("survey_date_col")]
        ).unique(subset=[survey_key])
        result = result.join(survey_dates, on=survey_key, how="left")

    # Add backcheck date
    if backcheck_date and backcheck_date in backcheck_data.columns:
        bc_dates = backcheck_data.select(
            [survey_key, pl.col(backcheck_date).alias("backcheck_date_col")]
        ).unique(subset=[survey_key])
        result = result.join(bc_dates, on=survey_key, how="left")

    return result


def _calculate_average_days(
    staff_data: pl.DataFrame,
    survey_date: str | None,
    backcheck_date: str | None,
) -> float:
    """Calculate average days between survey and backcheck.

    Parameters
    ----------
    staff_data : pl.DataFrame
        Staff-specific data.
    survey_date : str | None
        Survey date column name.
    backcheck_date : str | None
        Backcheck date column name.

    Returns
    -------
    float
        Average days between survey and backcheck.
    """
    if not (
        survey_date
        and backcheck_date
        and "survey_date_col" in staff_data.columns
        and "backcheck_date_col" in staff_data.columns
    ):
        return 0.0

    with suppress(Exception):
        days_diff = (
            staff_data.with_columns(
                [
                    (pl.col("backcheck_date_col") - pl.col("survey_date_col"))
                    .dt.total_days()
                    .alias("days_between")
                ]
            )
            .select(pl.col("days_between").mean())
            .item()
        )
        return round(days_diff, 1) if days_diff is not None else 0.0

    return 0.0


def _calculate_category_statistics(
    cat_data: pl.DataFrame, category: int
) -> dict[str, int | float]:
    """Calculate statistics for a single category.

    Parameters
    ----------
    cat_data : pl.DataFrame
        Category-specific data.
    category : int
        Category number (1, 2, or 3).

    Returns
    -------
    dict[str, int | float]
        Statistics dictionary for the category.
    """
    if cat_data.is_empty():
        return {
            f"Non-Missing Survey (Cat {category})": 0,
            f"Non-Missing Backcheck (Cat {category})": 0,
            f"Values Compared (Cat {category})": 0,
            f"Mismatches (Cat {category})": 0,
            f"Error Rate % (Cat {category})": 0.0,
        }

    # Count non-missing values
    n_non_missing_survey = cat_data.filter(~pl.col("survey_value").is_null()).height
    n_non_missing_backcheck = cat_data.filter(
        ~pl.col("backcheck_value").is_null()
    ).height

    # Count mismatches
    n_mismatches = cat_data.filter(pl.col("match_status") == "mismatch").height

    # Count values compared (excluding missing and excluded)
    n_cat_compared = cat_data.filter(
        ~pl.col("match_status").is_in(["missing", "excluded"])
    ).height

    # Calculate error rate
    error_rate = (n_mismatches / n_cat_compared * 100) if n_cat_compared > 0 else 0.0

    return {
        f"Non-Missing Survey (Cat {category})": n_non_missing_survey,
        f"Non-Missing Backcheck (Cat {category})": n_non_missing_backcheck,
        f"Values Compared (Cat {category})": n_cat_compared,
        f"Mismatches (Cat {category})": n_mismatches,
        f"Error Rate % (Cat {category})": round(error_rate, 2),
    }


def _calculate_staff_statistics(
    staff_data: pl.DataFrame,
    staff_col: str,
    staff_name: str,
    survey_key: str,
    survey_date: str | None,
    backcheck_date: str | None,
) -> dict[str, Any]:
    """Calculate all statistics for a single staff member.

    Parameters
    ----------
    staff_data : pl.DataFrame
        Data for a single staff member.
    staff_col : str
        Staff column name.
    staff_name : str
        Staff member name.
    survey_key : str
        Survey key column name.
    survey_date : str | None
        Survey date column name.
    backcheck_date : str | None
        Backcheck date column name.

    Returns
    -------
    dict[str, Any]
        Complete statistics dictionary for the staff member.
    """
    # Initialize stats dict
    staff_stats = {
        staff_col: staff_name,
        "Surveys": staff_data[survey_key].n_unique(),
        "Backchecks": staff_data[survey_key].n_unique(),
        "Avg Days": _calculate_average_days(staff_data, survey_date, backcheck_date),
    }

    # Initialize totals
    total_non_missing_survey = 0
    total_non_missing_backcheck = 0
    total_compared = 0
    total_mismatches = 0

    # Calculate statistics for each category
    for category in [1, 2, 3]:
        cat_data = staff_data.filter(pl.col("category") == category)
        cat_stats = _calculate_category_statistics(cat_data, category)

        # Add category stats to staff_stats
        staff_stats.update(cat_stats)

        # Accumulate totals
        total_non_missing_survey += cat_stats[f"Non-Missing Survey (Cat {category})"]
        total_non_missing_backcheck += cat_stats[
            f"Non-Missing Backcheck (Cat {category})"
        ]
        total_compared += cat_stats[f"Values Compared (Cat {category})"]
        total_mismatches += cat_stats[f"Mismatches (Cat {category})"]

    # Calculate and store totals
    total_error_rate = (
        (total_mismatches / total_compared * 100) if total_compared > 0 else 0.0
    )

    staff_stats.update(
        {
            "Non-Missing Survey (Total)": total_non_missing_survey,
            "Non-Missing Backcheck (Total)": total_non_missing_backcheck,
            "Values Compared (Total)": total_compared,
            "Mismatches (Total)": total_mismatches,
            "Error Rate % (Total)": round(total_error_rate, 2),
        }
    )

    return staff_stats


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
    # Validate inputs
    if backcheck_analysis.is_empty():
        return pl.DataFrame()

    survey_key = backcheck_settings.survey_key
    if not survey_key:
        return pl.DataFrame()

    survey_id = backcheck_settings.survey_id
    if not survey_id:
        return pl.DataFrame()

    # Get staff configuration
    staff_config = _get_staff_configuration(
        staff_type, survey_data, backcheck_data, backcheck_settings, survey_key
    )
    if staff_config is None:
        return pl.DataFrame()

    staff_col, data_source, join_key = staff_config

    # Check if join key exists in analysis
    if join_key not in backcheck_analysis.columns:
        return pl.DataFrame()

    # Join analysis with staff information
    analysis_with_staff = _join_staff_information(
        backcheck_analysis, data_source, staff_col, survey_key, join_key, staff_type
    )

    # Add date columns
    analysis_with_staff = _add_date_columns(
        analysis_with_staff,
        survey_data,
        backcheck_data,
        survey_key,
        backcheck_settings.survey_date,
        backcheck_settings.backcheck_date,
    )

    # Filter out rows where staff column is null
    analysis_with_staff = analysis_with_staff.filter(pl.col(staff_col).is_not_null())

    if analysis_with_staff.is_empty():
        return pl.DataFrame()

    # Calculate statistics for each staff member
    stats_list = []
    for staff_name in analysis_with_staff[staff_col].unique().drop_nulls():
        staff_data = analysis_with_staff.filter(pl.col(staff_col) == staff_name)
        staff_stats = _calculate_staff_statistics(
            staff_data,
            staff_col,
            staff_name,
            survey_key,
            backcheck_settings.survey_date,
            backcheck_settings.backcheck_date,
        )
        stats_list.append(staff_stats)

    if not stats_list:
        return pl.DataFrame()

    return pl.DataFrame(stats_list)


def _get_column_data_type(col_name: str, survey_data: pl.DataFrame) -> str:
    """Get data type for a column from survey data.

    Parameters
    ----------
    col_name : str
        Column name.
    survey_data : pl.DataFrame
        Survey dataset.

    Returns
    -------
    str
        Data type as string, or "Unknown" if column not found.
    """
    if col_name in survey_data.columns:
        return str(survey_data.schema[col_name])
    return "Unknown"


def _get_test_value(col_data: pl.DataFrame, test_col: str) -> float | None:
    """Extract first non-null test value from column data.

    Parameters
    ----------
    col_data : pl.DataFrame
        Column-specific data.
    test_col : str
        Test column name.

    Returns
    -------
    float | None
        First non-null value, or None if no values found.
    """
    if test_col not in col_data.columns:
        return None

    test_val = col_data[test_col].drop_nulls().head(1)
    return test_val[0] if len(test_val) > 0 else None


def _format_test_result(test_col: str, val: float | str) -> str | None:
    """Format a single test result value.

    Parameters
    ----------
    test_col : str
        Test column name.
    val : float
        Test value.

    Returns
    -------
    str | None
        Formatted test result string, or None if not applicable.
    """
    # T-test results
    if "ttest" in test_col:
        if "statistic" in test_col:
            return f"T-test: t={val:.3f}"
        if "p_value" in test_col:
            return f"p={val:.4f}"

    # Proportion test results
    if "prtest" in test_col:
        if "statistic" in test_col:
            return f"Prop test: z={val:.3f}"
        if "p_value" in test_col:
            return f"p={val:.4f}"

    # Sign-rank test results
    if "signrank" in test_col:
        if test_col == "signrank_skipped":
            return f"Sign-rank: skipped ({val})"
        if "statistic" in test_col:
            return f"Sign-rank: W={val:.3f}"
        if "p_value" in test_col:
            return f"p={val:.4f}"

    # Reliability metrics
    if "reliability_srv" in test_col:
        return f"SRV={val:.4f}"
    if "reliability_ratio" in test_col:
        return f"Reliability={val:.4f}"

    return None


def _collect_test_results(col_data: pl.DataFrame) -> str:
    """Collect and format all test results for a column.

    Parameters
    ----------
    col_data : pl.DataFrame
        Column-specific data with test results.

    Returns
    -------
    str
        Formatted test results string, or "None" if no tests available.
    """
    test_columns = [
        "ttest_t_statistic",
        "ttest_p_value",
        "prtest_z_statistic",
        "prtest_p_value",
        "signrank_statistic",
        "signrank_p_value",
        "signrank_skipped",
        "reliability_srv",
        "reliability_ratio",
    ]

    available_tests = []
    for test_col in test_columns:
        val = _get_test_value(col_data, test_col)
        if val is not None:
            formatted = _format_test_result(test_col, val)
            if formatted:
                available_tests.append(formatted)

    return "; ".join(available_tests) if available_tests else "None"


def _calculate_column_statistics(
    col_data: pl.DataFrame,
) -> tuple[int, int, int, float]:
    """Calculate basic statistics for a column.

    Parameters
    ----------
    col_data : pl.DataFrame
        Column-specific data.

    Returns
    -------
    tuple[int, int, int, float]
        Tuple of (n_values, n_compared, n_mismatches, error_rate).
    """
    # Total number of values
    n_values = col_data.height

    # Number of values compared (excluding missing and excluded)
    n_compared = col_data.filter(
        ~pl.col("match_status").is_in(["missing", "excluded"])
    ).height

    # Total mismatches
    n_mismatches = col_data.filter(pl.col("match_status") == "mismatch").height

    # Error rate
    error_rate = (n_mismatches / n_compared * 100) if n_compared > 0 else 0.0

    return n_values, n_compared, n_mismatches, error_rate


def _build_column_stats_dict(
    col_name: str,
    category: int,
    dtype: str,
    n_values: int,
    n_compared: int,
    n_mismatches: int,
    error_rate: float,
    test_results_str: str,
) -> dict[str, Any]:
    """Build statistics dictionary for a column.

    Parameters
    ----------
    col_name : str
        Column name.
    category : int
        Category number.
    dtype : str
        Data type.
    n_values : int
        Total number of values.
    n_compared : int
        Number of values compared.
    n_mismatches : int
        Number of mismatches.
    error_rate : float
        Error rate percentage.
    test_results_str : str
        Formatted test results string.

    Returns
    -------
    dict[str, Any]
        Statistics dictionary.
    """
    return {
        "Column Name": col_name,
        "Category": category,
        "Data Type": dtype,
        "# of Values": n_values,
        "Values Compared": n_compared,
        "Mismatches": n_mismatches,
        "Error Rate (%)": round(error_rate, 2),
        "Test Results": test_results_str,
    }


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

    stats_list = []

    for col_name in backcheck_analysis["column_name"].unique().drop_nulls():
        col_data = backcheck_analysis.filter(pl.col("column_name") == col_name)

        # Get column metadata
        category = col_data["category"][0]
        dtype = _get_column_data_type(col_name, survey_data)

        # Calculate statistics
        n_values, n_compared, n_mismatches, error_rate = _calculate_column_statistics(
            col_data
        )

        # Collect test results
        test_results_str = _collect_test_results(col_data)

        # Build and append statistics dictionary
        stats_dict = _build_column_stats_dict(
            col_name,
            category,
            dtype,
            n_values,
            n_compared,
            n_mismatches,
            error_rate,
            test_results_str,
        )
        stats_list.append(stats_dict)

    if not stats_list:
        return pl.DataFrame()

    return pl.DataFrame(stats_list)


# ==============================================================================
# COMPARISON AND ANALYSIS HELPERS
# ==============================================================================


def _build_select_columns(
    survey_key: str,
    survey_col: str,
    backcheck_col: str,
    category: int,
    data: pl.DataFrame,
) -> list:
    """Build list of columns to select for comparison.

    Parameters
    ----------
    survey_key : str
        Column name for survey identifier.
    survey_col : str
        Survey column name.
    backcheck_col : str
        Backcheck column name.
    category : int
        Backcheck category.
    data : pl.DataFrame
        Merged data.

    Returns
    -------
    list
        List of polars expressions to select.
    """
    select_cols = [
        pl.col(survey_key),
        pl.lit(survey_col).alias("column_name"),
        pl.col(survey_col).alias("survey_value"),
        pl.col(backcheck_col).alias("backcheck_value"),
        pl.lit(category).alias("category"),
    ]

    # Include backcheck key if it exists in the data
    backcheck_key = f"{survey_key}__BCCL"
    if backcheck_key in data.columns:
        select_cols.insert(1, pl.col(backcheck_key))

    return select_cols


def _preprocess_string_values(
    survey_vals: pl.Series,
    backcheck_vals: pl.Series,
    case_option: str | None,
    trim_spaces: bool,
    no_symbols: bool,
) -> tuple[pl.Series, pl.Series]:
    """Apply string preprocessing to survey and backcheck values.

    Parameters
    ----------
    survey_vals : pl.Series
        Survey values as strings.
    backcheck_vals : pl.Series
        Backcheck values as strings.
    case_option : str | None
        Case sensitivity option ('lowercase', 'uppercase', or None).
    trim_spaces : bool
        Whether to trim spaces.
    no_symbols : bool
        Whether to remove symbols.

    Returns
    -------
    tuple[pl.Series, pl.Series]
        Preprocessed survey and backcheck values.
    """
    # Apply case conversion
    if case_option == "lowercase":
        survey_vals = survey_vals.str.to_lowercase()
        backcheck_vals = backcheck_vals.str.to_lowercase()
    elif case_option == "uppercase":
        survey_vals = survey_vals.str.to_uppercase()
        backcheck_vals = backcheck_vals.str.to_uppercase()

    # Trim spaces
    if trim_spaces:
        survey_vals = survey_vals.str.strip_chars()
        backcheck_vals = backcheck_vals.str.strip_chars()

    # Remove symbols
    if no_symbols:
        survey_vals = survey_vals.str.replace_all(r"[^\w\s]", "")
        backcheck_vals = backcheck_vals.str.replace_all(r"[^\w\s]", "")

    return survey_vals, backcheck_vals


def _determine_match_status(
    survey_vals: pl.Series,
    backcheck_vals: pl.Series,
    no_diff_list: list[str],
    exclude_list: list[str],
) -> pl.Expr:
    """Determine match status for each value pair.

    Parameters
    ----------
    survey_vals : pl.Series
        Preprocessed survey values.
    backcheck_vals : pl.Series
        Preprocessed backcheck values.
    no_diff_list : list[str]
        Values that won't be marked as differences.
    exclude_list : list[str]
        Values to exclude from comparison.

    Returns
    -------
    pl.Expr
        Polars expression for match status.
    """
    return (
        pl.when(survey_vals.is_in(exclude_list) | backcheck_vals.is_in(exclude_list))
        .then(pl.lit("excluded"))
        .when(survey_vals.is_in(no_diff_list) & backcheck_vals.is_in(no_diff_list))
        .then(pl.lit("no_difference"))
        .when(survey_vals.is_null() | backcheck_vals.is_null())
        .then(pl.lit("missing"))
        .when(survey_vals == backcheck_vals)
        .then(pl.lit("match"))
        .otherwise(pl.lit("mismatch"))
    )


def _are_columns_numeric(
    data: pl.DataFrame, survey_col: str, backcheck_col: str
) -> bool:
    """Check if both survey and backcheck columns are numeric.

    Parameters
    ----------
    data : pl.DataFrame
        Merged data.
    survey_col : str
        Survey column name.
    backcheck_col : str
        Backcheck column name.

    Returns
    -------
    bool
        True if both columns are numeric.
    """
    # Remove __BCCL suffix from backcheck column for schema lookup
    backcheck_col_original = backcheck_col.replace("__BCCL", "")
    return (
        data.schema[survey_col].is_numeric()
        and data.schema[backcheck_col_original].is_numeric()
    )


def _calculate_within_ok_range(
    difference: pl.Expr,
    ok_range_type: str,
    ok_range_values: list[float],
) -> pl.Expr:
    """Calculate whether difference is within OK range.

    Parameters
    ----------
    difference : pl.Expr
        Polars expression for difference.
    ok_range_type : str
        Type of OK range ('number' or 'percentage').
    ok_range_values : list[float]
        OK range values [negative, positive].

    Returns
    -------
    pl.Expr
        Polars expression for within_ok_range boolean.
    """
    ok_range_neg = ok_range_values[0]
    ok_range_pos = ok_range_values[1]

    if ok_range_type == "percentage":
        # Calculate percentage difference
        pct_diff = (
            difference.abs() / pl.col("survey_value").cast(pl.Float64).abs()
        ) * 100
        return (pct_diff >= abs(ok_range_neg)) & (pct_diff <= ok_range_pos)

    # Absolute difference
    return (difference >= ok_range_neg) & (difference <= ok_range_pos)


def _add_numeric_columns(
    result: pl.DataFrame,
    data: pl.DataFrame,
    survey_col: str,
    backcheck_col: str,
    ok_range_type: str | None,
    ok_range_values: list[float] | None,
) -> pl.DataFrame:
    """Add numeric difference and OK range columns.

    Parameters
    ----------
    result : pl.DataFrame
        Result dataframe.
    data : pl.DataFrame
        Original merged data.
    survey_col : str
        Survey column name.
    backcheck_col : str
        Backcheck column name.
    ok_range_type : str | None
        Type of OK range.
    ok_range_values : list[float] | None
        OK range values.

    Returns
    -------
    pl.DataFrame
        Result with numeric columns added.
    """
    if not _are_columns_numeric(data, survey_col, backcheck_col):
        # Add null columns for non-numeric data
        return result.with_columns(
            [
                pl.lit(None).cast(pl.Float64).alias("difference"),
                pl.lit(None).alias("within_ok_range"),
            ]
        )

    # Calculate numeric difference
    difference = pl.col("survey_value").cast(pl.Float64) - pl.col(
        "backcheck_value"
    ).cast(pl.Float64)
    result = result.with_columns([difference.alias("difference")])

    # Check if within OK range
    if ok_range_type and ok_range_values and len(ok_range_values) >= 2:
        within_range = _calculate_within_ok_range(
            difference, ok_range_type, ok_range_values
        )
        return result.with_columns([within_range.alias("within_ok_range")])

    # No OK range configured
    return result.with_columns([pl.lit(None).alias("within_ok_range")])


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
    # Build and select columns
    select_cols = _build_select_columns(
        survey_key, survey_col, backcheck_col, category, data
    )
    result = data.select(select_cols)

    # Convert to string and preprocess
    survey_vals = result["survey_value"].cast(pl.Utf8)
    backcheck_vals = result["backcheck_value"].cast(pl.Utf8)
    survey_vals, backcheck_vals = _preprocess_string_values(
        survey_vals, backcheck_vals, case_option, trim_spaces, no_symbols
    )

    # Determine match status
    match_status = _determine_match_status(
        survey_vals, backcheck_vals, no_diff_list, exclude_list
    )
    result = result.with_columns([match_status.alias("match_status")])

    # Add numeric columns if applicable
    result = _add_numeric_columns(
        result, data, survey_col, backcheck_col, ok_range_type, ok_range_values
    )

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
            t_stat, p_value = stats.ttest_rel(survey_vals, backcheck_vals)
            test_results["ttest"] = {
                "t_statistic": float(t_stat),
                "p_value": float(p_value),
            }

    # Proportion test for binary data
    if prtest:
        with suppress(Exception):
            # Assume binary 0/1 or True/False
            prop_survey = survey_vals.mean()
            prop_backcheck = backcheck_vals.mean()
            n = len(survey_vals)
            pooled_var = (
                prop_survey * (1 - prop_survey) + prop_backcheck * (1 - prop_backcheck)
            ) / n
            if pooled_var > 0:
                z_stat = (prop_survey - prop_backcheck) / pooled_var**0.5
                p_value = 2 * (1 - stats.norm.cdf(abs(z_stat)))
                test_results["prtest"] = {
                    "z_statistic": float(z_stat),
                    "p_value": float(p_value),
                }

    # Wilcoxon signed-rank test
    if signrank:
        with suppress(Exception):
            diffs = survey_vals - backcheck_vals
            if diffs.std() > 0:
                stat, p_value = stats.wilcoxon(survey_vals, backcheck_vals)
                test_results["signrank"] = {
                    "statistic": float(stat),
                    "p_value": float(p_value),
                }
            else:
                test_results.setdefault("skipped_tests", {})["signrank"] = (
                    "zero variance in differences"
                )

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
