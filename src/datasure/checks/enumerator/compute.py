"""Pure data-computation functions for the enumerator performance module."""

from datetime import date as dt_date
from datetime import timedelta

import polars as pl
import streamlit as st

from datasure.checks import missing
from datasure.checks.enumerator.attention import duration_minutes
from datasure.checks.enumerator.models import (
    WEEKDAY_OFFSET_TO_NUMERIC,
    ActiveEnumerators,
    OverviewFigures,
)
from datasure.utils.duckdb_utils import load_missing_codes_from_db

# =============================================================================
# Consent and Outcome Flags
# =============================================================================

CONSENT_FLAG = "consent_granted_agg_col"
COMPLETED_FLAG = "completed_survey_agg_col"


@st.cache_data(ttl=300)
def add_consent_outcome_flags(
    data: pl.DataFrame,
    consent: str | None,
    consent_vals: tuple | None,
    outcome: str | None,
    outcome_vals: tuple | None,
) -> pl.DataFrame:
    """Add 0/1 consent and completed-survey flag columns to the data.

    A flag is 1 where the column's value is one of the given values. A flag
    is added only when its column is in the data and values are given, so
    the Enumerator Summary leaves out a rate that is not set up.

    Cached on the data and the settings, so a change to either recomputes.

    Parameters
    ----------
    data : pl.DataFrame
        Survey data.
    consent, outcome : str | None
        Consent and outcome columns.
    consent_vals, outcome_vals : tuple | None
        Values meaning consent was given and the survey was completed.

    Returns
    -------
    pl.DataFrame
        ``data`` with ``consent_granted_agg_col`` and
        ``completed_survey_agg_col`` where set up.
    """
    flags = [
        pl.col(column).is_in(list(values)).cast(pl.Int32).alias(flag)
        for column, values, flag in (
            (consent, consent_vals, CONSENT_FLAG),
            (outcome, outcome_vals, COMPLETED_FLAG),
        )
        if column and values and column in data.columns
    ]
    return data.with_columns(flags) if flags else data


# =============================================================================
# Shared Time-Period Helpers
# =============================================================================

# Display format for single dates, e.g. "Jan 01, 2025".
DISPLAY_DATE_FORMAT = "%b %d, %Y"

_LEGACY_PERIOD_ALIASES = {"Day": "Daily", "Week": "Weekly", "Month": "Monthly"}


def _add_time_period_column(
    df: pl.DataFrame, date: str, period: str, weekstartday: str
) -> pl.DataFrame:
    """Add a user-friendly "TIME PERIOD" column for the selected granularity.

    Shared by compute_enumerator_productivity and
    compute_enumerator_statistics_overtime, which both bucket submissions
    into daily/weekly/monthly periods the same way before aggregating.

    Parameters
    ----------
    df : pl.DataFrame
        DataFrame containing the date column to bucket.
    date : str
        Date column name.
    period : str
        Time period: "Daily", "Weekly", "Monthly", "Day", "Week", or "Month".
    weekstartday : str
        Start day of the week (e.g., "SUN", "MON") for weekly analysis.

    Returns
    -------
    pl.DataFrame
        `df` with a "TIME PERIOD" column added (unchanged if `period` is
        not recognized).
    """
    period_normalized = _LEGACY_PERIOD_ALIASES.get(period, period)

    if period_normalized == "Daily":
        # Format as "Jan 1, 2025"
        return df.with_columns(
            pl.col(date).dt.strftime(DISPLAY_DATE_FORMAT).alias("TIME PERIOD")
        )

    if period_normalized == "Weekly":
        # Calculate week start and end dates for user-friendly display
        offset = WEEKDAY_OFFSET_TO_NUMERIC.get(weekstartday, 1)

        # Calculate the week start date (beginning of the week containing this date)
        # weekday() returns 0=Monday, 6=Sunday
        df = df.with_columns(
            [
                # Calculate days since the start of the week
                ((pl.col(date).dt.weekday() - offset + 7) % 7).alias(
                    "_days_since_week_start"
                ),
            ]
        )

        # Calculate week_start_date by subtracting days_since_week_start
        df = df.with_columns(
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
        return df.with_columns(
            (
                pl.col("_week_start").dt.strftime(DISPLAY_DATE_FORMAT)
                + " to "
                + pl.col("_week_end").dt.strftime(DISPLAY_DATE_FORMAT)
            ).alias("TIME PERIOD")
        )

    if period_normalized == "Monthly":
        # Format as "January 2025"
        return df.with_columns(pl.col(date).dt.strftime("%B %Y").alias("TIME PERIOD"))

    return df


# =============================================================================
# Overview Computation Functions
# =============================================================================


def _past_week(today: dt_date) -> pl.Expr:
    """True for a ``day`` dated in the 7 days up to and including `today`."""
    return pl.col("day").is_between(today - timedelta(days=6), today)


def _enumerator_days(data: pl.DataFrame, date: str, enumerator: str) -> pl.DataFrame:
    """Return each submission's enumerator, as text, and its local day."""
    return data.select(
        pl.col(enumerator).cast(pl.String).alias("enumerator"),
        pl.col(date).dt.date().alias("day"),
    )


def count_active_enumerators(
    data: pl.DataFrame, date: str, enumerator: str, today: dt_date | None = None
) -> ActiveEnumerators:
    """Count the enumerators active in the past 7 days, out of all.

    Active: a submission dated in the 7 days up to and including `today`;
    later dates do not count. Rows with no enumerator are left out of both
    counts. Datetimes count on their local day, as the summary table does.
    The overview's "Active in the past 7 days" and Summary's Enumerator Stats
    health row both use this, so they agree on the same data.

    Parameters
    ----------
    data : pl.DataFrame
        Survey data.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    today : date | None
        The day the past 7 days count back from. Defaults to the system clock.
    """
    if today is None:
        today = dt_date.today()
    named = _enumerator_days(data, date, enumerator).drop_nulls("enumerator")
    return ActiveEnumerators(
        active=named.filter(_past_week(today))["enumerator"].n_unique(),
        total=named["enumerator"].n_unique(),
    )


def compute_overview_figures(
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None = None,
    duration: str | None = None,
    duration_unit: str | None = None,
    today: dt_date | None = None,
) -> OverviewFigures:
    """Compute the four figures at the top of the enumerator report.

    Each figure carries what it is compared with: active enumerators out of
    all, the past 7 days' submissions against the 7 days before, the median
    submissions per enumerator with who has the fewest and the most, and the
    median interview length with its middle half.

    Parameters
    ----------
    data : pl.DataFrame
        Survey data with at least one row.
    date : str
        Date column name.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name, for the team count.
    duration : str | None
        Duration column name, for the interview length.
    duration_unit : str | None
        The duration's unit: "seconds", "minutes" or "hours"; anything else
        is read as seconds.
    today : date | None
        The day the past 7 days count back from. Defaults to the system clock.

    Raises
    ------
    ValueError
        If ``data`` is empty.
    """
    if data.is_empty():
        raise ValueError("Input data is empty. Cannot compute the overview figures.")
    if today is None:
        today = dt_date.today()
    days = _enumerator_days(data, date, enumerator)
    week_before = _past_week(today - timedelta(days=7))
    active = count_active_enumerators(data, date, enumerator, today)

    totals = (
        days.drop_nulls("enumerator")
        .group_by("enumerator")
        .len()
        .sort(["len", "enumerator"])
    )
    fewest = totals.row(0)
    most = totals.sort(["len", "enumerator"], descending=[True, False]).row(0)

    length_minutes = None
    if duration and duration in data.columns:
        lengths = data[duration].cast(pl.Float64, strict=False).drop_nulls()
        if not lengths.is_empty():
            length_minutes = tuple(
                duration_minutes(
                    float(lengths.quantile(q, interpolation="linear")), duration_unit
                )
                for q in (0.25, 0.5, 0.75)
            )

    return OverviewFigures(
        num_enumerators=active.total,
        num_active=active.active,
        num_teams=data[team].n_unique() if team and team in data.columns else None,
        submissions_past_week=days.filter(_past_week(today)).height,
        submissions_week_before=days.filter(week_before).height,
        median_per_enumerator=float(totals["len"].median()),
        fewest=(fewest[0], int(fewest[1])),
        most=(most[0], int(most[1])),
        duration_minutes=length_minutes,
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
    columns_to_exclude = [CONSENT_FLAG, COMPLETED_FLAG]

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


def compute_enumerator_missing_shares(
    data: pl.DataFrame,
    enumerator: str,
    team: str | None,
    missing_codes_config: pl.DataFrame,
) -> pl.DataFrame:
    """Return each enumerator's submissions and missing-answer share.

    The "# submissions" and "% Total Missing" columns the summary table has,
    computed the same way over ``data``, so Needs attention can compare
    missing answers over only some interviews, such as completed ones.

    Parameters
    ----------
    data : pl.DataFrame
        The interviews to count.
    enumerator : str
        Enumerator column name.
    team : str | None
        Team column name, grouped by as in the summary table.
    missing_codes_config : pl.DataFrame
        The project's missing codes.

    Returns
    -------
    pl.DataFrame
        One row per enumerator (and team); empty when ``data`` is.
    """
    if data.is_empty():
        return pl.DataFrame()
    group_by_cols = [enumerator, team] if team else [enumerator]
    counts = data.group_by(group_by_cols, maintain_order=True).agg(
        pl.len().alias("# submissions")
    )
    shares = compute_enumerator_missing_table(data, missing_codes_config, group_by_cols)
    return counts.join(shares, on=group_by_cols, how="left")


def compute_enumerator_summary(
    project_id: str,
    data: pl.DataFrame,
    date: str,
    enumerator: str,
    team: str | None,
    formversion: str | None,
    duration: str | None,
    today: dt_date | None = None,
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
    today : date | None
        Reference date for the today/this week/this month counts. Defaults
        to the system clock.

    Returns
    -------
    pl.DataFrame
        Comprehensive summary DataFrame with enumerator statistics.
    """
    group_by_cols = [enumerator, team] if team else [enumerator]
    # Compare as dates (cut to the local day); format as text only for display.
    df = data.with_columns(pl.col(date).dt.date())

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
    if today is None:
        today = dt_date.today()
    start_of_week = today - timedelta(days=today.weekday())
    start_of_month = today.replace(day=1)

    df = df.with_columns(
        [
            (pl.col(date) == today).alias("submitted_today"),
            (pl.col(date) >= start_of_week).alias("submitted_this_week"),
            (pl.col(date) >= start_of_month).alias("submitted_this_month"),
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
    if CONSENT_FLAG in df.columns:
        consent_df = df.group_by(group_by_cols, maintain_order=True).agg(
            pl.col(CONSENT_FLAG).mean().alias("% consent")
        )
        summary_df = summary_df.join(consent_df, on=group_by_cols, how="left")

    # Add outcome statistics if available
    if COMPLETED_FLAG in df.columns:
        outcome_df = df.group_by(group_by_cols, maintain_order=True).agg(
            pl.col(COMPLETED_FLAG).mean().alias("% completed survey")
        )
        summary_df = summary_df.join(outcome_df, on=group_by_cols, how="left")

    return summary_df.with_columns(
        pl.col("first submission", "last submission").dt.strftime(DISPLAY_DATE_FORMAT)
    )


def compute_latest_submission_date(data: pl.DataFrame, date: str) -> dt_date | None:
    """Return the latest submission date, or None if there are no submissions.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    date : str
        Date column name.

    Returns
    -------
    date | None
        Latest submission date, cut to the local day as in
        compute_enumerator_summary.
    """
    return data[date].dt.date().max()


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
    prod_df = _add_time_period_column(prod_df, date, period, weekstartday)

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
    missing_codes: pl.DataFrame | None = None,
) -> pl.DataFrame:
    """Compute enumerator statistics across specified columns.

    Calculates summary statistics (mean, median, std, etc.) for numeric
    columns grouped by enumerator (and optionally team).

    Cached for 5 minutes to improve performance for repeated calls. The
    missing codes are an argument so that editing them changes the cache key.

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
    missing_codes : pl.DataFrame | None
        The project's missing codes. Values matching them count as missing.

    Returns
    -------
    pl.DataFrame
        DataFrame with enumerators (and teams) and computed statistics.
    """
    if missing_codes is not None:
        data = missing.mask_missing_codes(data, statscols, missing_codes)

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
    missing_codes: pl.DataFrame | None = None,
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
    missing_codes : pl.DataFrame | None
        The project's missing codes. Values matching them count as missing.

    Returns
    -------
    pl.DataFrame
        Pivoted DataFrame with enumerators (and teams) as rows and time
        periods as columns.
    """
    stats_overtime_df = data.select([date] + group_by_cols + [statscol]).clone()
    if missing_codes is not None:
        stats_overtime_df = missing.mask_missing_codes(
            stats_overtime_df, [statscol], missing_codes
        )
    stats_overtime_df = _add_time_period_column(
        stats_overtime_df, date, period, weekstartday
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
