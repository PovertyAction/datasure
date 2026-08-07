"""Pure data-computation functions for the enumerator performance module."""

from datetime import date as dt_date
from datetime import timedelta

import polars as pl
import streamlit as st

from datasure.checks import missing
from datasure.checks.enumerator.models import (
    WEEKDAY_OFFSET_TO_NUMERIC,
    EnumeratorOverviewMetrics,
)
from datasure.utils.duckdb_utils import load_missing_codes_from_db

# =============================================================================
# Overview Computation Functions
# =============================================================================


def compute_enumerator_overview(
    data: pl.DataFrame, date: str, enumerator: str, team: str | None
) -> EnumeratorOverviewMetrics:
    """Compute enumerator overview metrics.

    Calculates key metrics including total submissions, active enumerators,
    team counts, and submission statistics.

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name (optional).

    Returns
    -------
    EnumeratorOverviewMetrics
        Overview metrics for enumerators including counts and statistics.
    """
    if data.is_empty():
        raise ValueError(
            "Input data is empty. Cannot compute enumerator overview metrics."
        )
    data = data.sort([enumerator, date])

    all_submissions = data.height

    # Calculate daily submissions
    data = data.with_row_index(name="TOKEN KEY")
    daily_submissions_sum = data.group_by([date, enumerator]).agg(
        pl.col("TOKEN KEY").count().alias("count")
    )

    # Calculate active enumerators (past 7 days)
    from datetime import date as dt_date
    from datetime import timedelta

    active_date_cut_off = dt_date.today() - timedelta(weeks=1)

    daily_submissions_sum = daily_submissions_sum.with_columns(
        (pl.col(date).cast(pl.Date) > active_date_cut_off).alias("active")
    )

    num_active_enumerators = (
        daily_submissions_sum.filter(pl.col("active"))
        .select(pl.col(enumerator).n_unique())
        .item()
    )

    num_enumerators = data[enumerator].n_unique()
    num_teams = data[team].n_unique() if team else "n/a"
    min_submissions = int(daily_submissions_sum["count"].min())
    max_submissions = int(daily_submissions_sum["count"].max())
    avg_submissions = int(daily_submissions_sum["count"].mean())

    pct_active_enumerators = f"{(num_active_enumerators / num_enumerators) * 100:.0f}%"

    return EnumeratorOverviewMetrics(
        all_submissions=all_submissions,
        num_active_enumerators=num_active_enumerators,
        num_enumerators=num_enumerators,
        num_teams=num_teams,
        min_submissions=min_submissions,
        max_submissions=max_submissions,
        avg_submissions=avg_submissions,
        pct_active_enumerators=pct_active_enumerators,
    )


def compute_enumerator_missing_table(
    data: pl.DataFrame, missing_codes_config: pl.DataFrame, group_by_col: list[str]
) -> pl.DataFrame:
    """Compute missing data statistics per enumerator.

    Calculates missing data counts and percentages for each enumerator
    based on provided missing codes configuration.

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    missing_settings_file : str
        Path to missing codes configuration file.
    enumerator : str
        Enumerator column name.

    Returns
    -------
    pl.DataFrame
        DataFrame with missing data statistics per enumerator.
    """
    # define columns to exclude from missing data stats
    columns_to_exclude = ["consent_granted_agg_col", "completed_survey_agg_col"]

    data_for_missing = data.select(
        [col for col in data.columns if col not in columns_to_exclude]
    )

    # Metadata for missing data calculation
    enum_data_missing = data_for_missing.select(group_by_col)

    # If missing_codes_config is empty, calculate only null missingness
    if missing_codes_config.is_empty():
        # Calculate overall null missingness per enumerator
        columns_to_check = [
            col for col in data_for_missing.columns if col not in group_by_col
        ]

        # Count nulls per row and calculate percentage
        missing_summary = data_for_missing.with_columns(
            [
                pl.sum_horizontal(
                    [pl.col(col).is_null().cast(pl.Int32) for col in columns_to_check]
                ).alias("_null_count"),
                pl.lit(len(columns_to_check)).alias("_total_fields"),
            ]
        ).with_columns(
            (pl.col("_null_count") / pl.col("_total_fields") * 100).alias(
                "% Null values"
            )
        )

        # Group by enumerator and calculate mean missingness rate
        result_df = missing_summary.group_by(group_by_col, maintain_order=True).agg(
            pl.col("% Null values").mean()
        )

        return result_df

    # If missing_codes_config is provided, calculate missingness by category
    # Get missing code pairs from the config
    missing_code_pairs = missing._get_missing_code_pairs(missing_codes_config)

    # Compute missing data with paired encoding
    missing_data_encoded = missing._compute_missing_data_paired(
        data_for_missing, missing_codes_config
    )

    # Get columns to check (exclude enumerator column)
    columns_to_check = [
        col for col in missing_data_encoded.columns if col not in group_by_col
    ]
    total_fields = len(columns_to_check)

    # Calculate counts for each missing category per row
    agg_expressions = []

    # Add null values count (encoded as 1)
    agg_expressions.append(
        pl.sum_horizontal(
            [(pl.col(col) == 1).cast(pl.Int32) for col in columns_to_check]
        ).alias("_null_count")
    )

    # Add count for each special missing code category (starting from 2)
    for idx, label in enumerate(missing_code_pairs.keys(), start=2):
        agg_expressions.append(
            pl.sum_horizontal(
                [(pl.col(col) == idx).cast(pl.Int32) for col in columns_to_check]
            ).alias(f"_{label}_count")
        )

    # Add total missing count (any value > 0)
    agg_expressions.append(
        pl.sum_horizontal(
            [(pl.col(col) > 0).cast(pl.Int32) for col in columns_to_check]
        ).alias("_total_missing_count")
    )

    # Add total fields count
    agg_expressions.append(pl.lit(total_fields).alias("_total_fields"))

    # Apply the aggregations
    missing_counts = missing_data_encoded.select(
        [pl.col(group_by_col)] + agg_expressions
    )

    # Calculate percentages
    percentage_expressions = []

    # Null values percentage
    percentage_expressions.append(
        (pl.col("_null_count") / pl.col("_total_fields") * 100).alias("% Null values")
    )

    # Special missing code category percentages
    for label in missing_code_pairs:
        percentage_expressions.append(
            (pl.col(f"_{label}_count") / pl.col("_total_fields") * 100).alias(
                f"% {label}"
            )
        )

    # Total missing percentage
    percentage_expressions.append(
        (pl.col("_total_missing_count") / pl.col("_total_fields") * 100).alias(
            "% Total Missing"
        )
    )

    missing_with_percentages = missing_counts.with_columns(percentage_expressions)

    # Group by enumerator and calculate mean percentages
    final_agg_expressions = [pl.col("% Null values").mean()]

    for label in missing_code_pairs:
        final_agg_expressions.append(pl.col(f"% {label}").mean())

    final_agg_expressions.append(pl.col("% Total Missing").mean())

    # drop enumerator column from missing_with_percentages
    missing_with_percentages = missing_with_percentages.select(
        [col for col in missing_with_percentages.columns if col not in group_by_col]
    )
    # merge missing_with_percentages with enumerator column
    missing_with_percentages = pl.concat(
        [enum_data_missing, missing_with_percentages], how="horizontal"
    )

    result_df = missing_with_percentages.group_by(
        group_by_col, maintain_order=True
    ).agg(final_agg_expressions)

    return result_df


def compute_enumerator_summary(
    project_id: str,
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    formversion: str | None,
    duration: str | None,
) -> pl.DataFrame:
    """Compute comprehensive enumerator summary statistics.

    Calculates submission counts, date ranges, duration statistics,
    form version tracking, consent rates, outcome rates, and missing data
    patterns for each enumerator.

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    missing_settings_file : str
        Path to missing codes configuration file.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    formdef_version : str | None
        Form version column name (optional).
    duration : str | None
        Duration column name (optional).
    consent : str | None
        Consent column name (optional).
    consent_vals : list[str] | None
        List of values indicating valid consent (optional).
    outcome : str | None
        Outcome column name (optional).
    outcome_vals : list[str] | None
        List of values indicating completed surveys (optional).

    Returns
    -------
    pl.DataFrame
        Comprehensive summary DataFrame with enumerator statistics.
    """
    group_by_cols = [enumerator, team] if team else [enumerator]
    # Format date column
    df = data.with_columns(pl.col(date).dt.strftime("%b %d, %Y").alias(date))

    # Basic summary aggregations
    summary_df = df.group_by(group_by_cols, maintain_order=True).agg(
        [
            pl.col(date).min().alias("first submission"),
            pl.col(date).max().alias("last submission"),
            pl.col(date).count().alias("# submissions"),
            pl.col(date).n_unique().alias("# unique dates"),
        ]
    )

    # Calculate time-based submissions
    today = dt_date.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    today_str = today.strftime("%b %d, %Y")
    week_str = start_of_week.strftime("%b %d, %Y")
    month_str = start_of_month.strftime("%b %d, %Y")

    df = df.with_columns(
        [
            (pl.col(date) == today_str).alias("submitted_today"),
            (pl.col(date) >= week_str).alias("submitted_this_week"),
            (pl.col(date) >= month_str).alias("submitted_this_month"),
        ]
    )

    lagged_df = df.group_by(group_by_cols, maintain_order=True).agg(
        [
            pl.col("submitted_today").sum().alias("# submissions today"),
            pl.col("submitted_this_week").sum().alias("# submissions this week"),
            pl.col("submitted_this_month").sum().alias("# submissions this month"),
        ]
    )

    summary_df = summary_df.join(lagged_df, on=group_by_cols, how="left")

    # Add missing data statistics
    missing_settings_file = load_missing_codes_from_db(project_id)
    enumerator_missing_df = compute_enumerator_missing_table(
        data, missing_settings_file, group_by_cols
    )
    summary_df = summary_df.join(enumerator_missing_df, on=group_by_cols, how="left")

    # Add duration statistics if available
    if duration:
        duration_df = df.group_by(group_by_cols, maintain_order=True).agg(
            [
                pl.col(duration).min().alias("min duration"),
                pl.col(duration).mean().alias("mean duration"),
                pl.col(duration).median().alias("median duration"),
                pl.col(duration).max().alias("max duration"),
            ]
        )
        summary_df = summary_df.join(duration_df, on=group_by_cols, how="left")

    # Add form version statistics if available
    if formversion:
        # Get latest form version per date
        formdef_outdated = df.group_by(date, maintain_order=True).agg(
            pl.col(formversion).max().alias("latest daily form version")
        )

        df = df.join(formdef_outdated, on=date, how="left")
        df = df.with_columns(
            (pl.col(formversion) != pl.col("latest daily form version")).alias(
                "outdated_form_version"
            )
        )

        formdef_outdated_df = df.group_by(group_by_cols, maintain_order=True).agg(
            pl.col("outdated_form_version").sum().alias("# of outdated form versions")
        )

        formdef_df = df.group_by(group_by_cols, maintain_order=True).agg(
            [
                pl.col(formversion).n_unique().alias("# form versions"),
                pl.col(formversion).max().alias("latest form version"),
            ]
        )

        latest_enum_formversion = df.group_by(group_by_cols, maintain_order=True).agg(
            pl.col(formversion).max().alias("last form version")
        )

        summary_df = summary_df.join(formdef_df, on=group_by_cols, how="left")
        summary_df = summary_df.join(formdef_outdated_df, on=group_by_cols, how="left")
        summary_df = summary_df.join(
            latest_enum_formversion, on=group_by_cols, how="left"
        )

    # Add consent statistics if available
    if "consent_granted_agg_col" in df.columns:
        consent_df = df.group_by(group_by_cols, maintain_order=True).agg(
            pl.col("consent_granted_agg_col").mean().alias("% consent")
        )
        summary_df = summary_df.join(consent_df, on=group_by_cols, how="left")

    # Add outcome statistics if available
    if "completed_survey_agg_col" in df.columns:
        outcome_df = df.group_by(group_by_cols, maintain_order=True).agg(
            pl.col("completed_survey_agg_col").mean().alias("% completed survey")
        )
        summary_df = summary_df.join(outcome_df, on=group_by_cols, how="left")

    return summary_df


# =============================================================================
# Productivity Computation Functions
# =============================================================================


def compute_enumerator_productivity(
    data: pl.DataFrame,
    date: str,
    group_by_cols: list[str],
    period: str,
    weekstartday: str,
) -> pl.DataFrame:
    """Compute enumerator productivity over time.

    Analyzes submission counts by enumerator across time periods (daily,
    weekly, or monthly).

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    period : str
        Time period: "Daily", "Weekly", "Monthly", "Day", "Week", or "Month".
    weekstartday : str
        Start day of the week (e.g., "SUN", "MON") for weekly analysis.

    Returns
    -------
    pl.DataFrame
        Pivoted DataFrame with enumerators as rows and time periods as columns.
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

    # Count submissions per period and enumerator
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


# =============================================================================
# Statistics Computation Functions
# =============================================================================


@st.cache_data(ttl=300)
def compute_enumerator_statistics(
    data: pl.DataFrame,
    group_by_cols: list[str],
    statscols: list[str],
    stats: list[str],
) -> pl.DataFrame:
    """Compute enumerator statistics across specified columns.

    Calculates summary statistics (mean, median, std, etc.) for numeric
    columns grouped by enumerator (and optionally team).

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    group_by_cols : list[str]
        List of columns to group by (e.g., ["enumerator"] or ["enumerator", "team"]).
    statscols : list[str]
        List of columns to compute statistics on.
    stats : list[str]
        List of statistics to compute (e.g., ["mean", "median", "std"]).

    Returns
    -------
    pl.DataFrame
        DataFrame with enumerators (and teams) and computed statistics.
    """
    # Map stat names to Polars expressions
    stat_mapping = {
        "count": "count",
        "min": "min",
        "mean": "mean",
        "median": "median",
        "max": "max",
        "std": "std",
        "25th percentile": "quantile",
        "75th percentile": "quantile",
    }

    agg_exprs = []
    for col in statscols:
        for stat in stats:
            if stat == "25th percentile":
                agg_exprs.append(pl.col(col).quantile(0.25).alias(f"{col}_{stat}"))
            elif stat == "75th percentile":
                agg_exprs.append(pl.col(col).quantile(0.75).alias(f"{col}_{stat}"))
            else:
                method = stat_mapping.get(stat, stat)
                agg_exprs.append(getattr(pl.col(col), method)().alias(f"{col}_{stat}"))

    stats_res = data.group_by(group_by_cols, maintain_order=True).agg(agg_exprs)

    return stats_res


def compute_enumerator_statistics_overtime(
    data: pl.DataFrame,
    date: str,
    group_by_cols: list[str],
    statscol: str,
    stat: str,
    period: str,
    weekstartday: str,
) -> pl.DataFrame:
    """Compute enumerator statistics over time for a specific column.

    Analyzes how a specific statistic changes over time periods for each
    enumerator (and optionally team).

    Cached for 5 minutes to improve performance for repeated calls.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.
    group_by_cols : list[str]
        List of columns to group by (e.g., ["enumerator"] or ["enumerator", "team"]).
    statscol : str
        Column to compute statistics on.
    stat : str
        Statistic to compute (e.g., "mean", "median", "missing").
    period : str
        Time period: "Daily", "Weekly", "Monthly", "Day", "Week", or "Month".
    weekstartday : str
        Start day of the week for weekly analysis.

    Returns
    -------
    pl.DataFrame
        Pivoted DataFrame with enumerators (and teams) as rows and time
        periods as columns.
    """
    stats_overtime_df = data.select([date] + group_by_cols + [statscol]).clone()

    # Normalize period values to handle both old and new formats
    period_normalized = period
    if period == "Day":
        period_normalized = "Daily"
    elif period == "Week":
        period_normalized = "Weekly"
    elif period == "Month":
        period_normalized = "Monthly"

    # Create time period column with user-friendly formatting
    if period_normalized == "Daily":
        # Format as "Jan 1, 2025"
        stats_overtime_df = stats_overtime_df.with_columns(
            pl.col(date).dt.strftime("%b %d, %Y").alias("TIME PERIOD")
        )
    elif period_normalized == "Weekly":
        # Calculate week start and end dates for user-friendly display
        offset = WEEKDAY_OFFSET_TO_NUMERIC.get(weekstartday, 1)

        # Calculate the week start date (beginning of the week containing this date)
        # weekday() returns 0=Monday, 6=Sunday
        stats_overtime_df = stats_overtime_df.with_columns(
            [
                # Calculate days since the start of the week
                ((pl.col(date).dt.weekday() - offset + 7) % 7).alias(
                    "_days_since_week_start"
                ),
            ]
        )

        # Calculate week_start_date by subtracting days_since_week_start
        stats_overtime_df = stats_overtime_df.with_columns(
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
        stats_overtime_df = stats_overtime_df.with_columns(
            (
                pl.col("_week_start").dt.strftime("%b %d, %Y")
                + " to "
                + pl.col("_week_end").dt.strftime("%b %d, %Y")
            ).alias("TIME PERIOD")
        )
    elif period_normalized == "Monthly":
        # Format as "January 2025"
        stats_overtime_df = stats_overtime_df.with_columns(
            pl.col(date).dt.strftime("%B %Y").alias("TIME PERIOD")
        )

    # Calculate statistic
    if stat == "missing":
        stats_overtime_res = stats_overtime_df.group_by(
            ["TIME PERIOD"] + group_by_cols, maintain_order=True
        ).agg(pl.col(statscol).is_null().mean().alias("_STAT"))
    elif stat == "25th percentile":
        stats_overtime_res = stats_overtime_df.group_by(
            ["TIME PERIOD"] + group_by_cols, maintain_order=True
        ).agg(pl.col(statscol).quantile(0.25).alias("_STAT"))
    elif stat == "75th percentile":
        stats_overtime_res = stats_overtime_df.group_by(
            ["TIME PERIOD"] + group_by_cols, maintain_order=True
        ).agg(pl.col(statscol).quantile(0.75).alias("_STAT"))
    else:
        stats_overtime_res = stats_overtime_df.group_by(
            ["TIME PERIOD"] + group_by_cols, maintain_order=True
        ).agg(getattr(pl.col(statscol), stat)().alias("_STAT"))

    # Pivot to wide format
    stats_overtime_res = stats_overtime_res.pivot(
        index=group_by_cols, on="TIME PERIOD", values="_STAT"
    )

    return stats_overtime_res
