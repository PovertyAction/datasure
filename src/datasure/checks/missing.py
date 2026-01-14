"""Missing data detection module for survey data quality checks.

This module provides comprehensive missing data analysis functionality with:
- Configurable missing value types (Don't Know, Refuse, etc.)
- Pydantic validation for data integrity
- Modular, testable architecture
- DuckDB storage for missing code configurations
"""

from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import polars as pl
import seaborn as sns
import streamlit as st
from pydantic import BaseModel, Field, field_validator

from datasure.utils.duckdb_utils import (
    add_missing_code,
    duckdb_save_table,
    load_missing_codes_from_db,
)
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

TAB_NAME = "missing"


# =============================================================================
# Pydantic Models for Data Validation
# =============================================================================


class MissingCode(BaseModel):
    """Configuration for a single missing code type."""

    label: str = Field(
        ..., min_length=1, description="Label for the missing value type"
    )
    codes: list[str] = Field(..., min_length=1, description="List of missing codes")

    @field_validator("codes", mode="before")
    @classmethod
    def parse_codes(cls, value: Any) -> list[str]:
        """Parse codes from comma-separated string or list."""
        if isinstance(value, str):
            return [code.strip() for code in value.split(",") if code.strip()]
        if isinstance(value, list):
            return [str(code).strip() for code in value if str(code).strip()]
        msg = f"codes must be a string or list, got {type(value)}"
        raise ValueError(msg)

    def codes_as_string(self) -> str:
        """Return codes as comma-separated string."""
        return ", ".join(self.codes)


class MissingSummaryStats(BaseModel):
    """Summary statistics for missing data."""

    mean_missing_pct: float = Field(
        ge=0, le=100, description="Mean percentage of missing values"
    )
    all_missing_pct: float = Field(
        ge=0, le=100, description="Percentage of columns with all missing"
    )
    any_missing_pct: float = Field(
        ge=0, le=100, description="Percentage of columns with any missing"
    )
    no_missing_pct: float = Field(
        ge=0, le=100, description="Percentage of columns with no missing"
    )


# =============================================================================
# Helper Functions
# =============================================================================


def _create_binary_missing_indicator(missing_data: pl.DataFrame) -> pl.DataFrame:
    """Create binary missing indicator (0 = not missing, 1 = missing).

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1+ = missing.

    Returns
    -------
    pl.DataFrame
        Binary indicator DataFrame (0 or 1).
    """
    return missing_data.select(
        [(pl.col(col) > 0).cast(pl.Int8).alias(col) for col in missing_data.columns]
    )


def _safe_percentage(numerator: int | float, denominator: int | float) -> float:
    """Safely calculate percentage avoiding division by zero.

    Parameters
    ----------
    numerator : int | float
        The numerator value.
    denominator : int | float
        The denominator value.

    Returns
    -------
    float
        The percentage, or 0.0 if denominator is zero.
    """
    return (numerator / denominator * 100) if denominator > 0 else 0.0


# =============================================================================
# Core Computation Functions
# =============================================================================


def _try_convert_code_to_column_type(
    code: str, col_dtype: pl.DataType, col_name: str
) -> tuple[Any, bool]:
    """Try to convert a missing code to match the column's data type.

    Parameters
    ----------
    code : str
        The missing code to convert.
    col_dtype : pl.DataType
        The Polars data type of the column.
    col_name : str
        The name of the column (for logging/debugging).

    Returns
    -------
    tuple[Any, bool]
        A tuple of (converted_value, success). If conversion fails,
        returns (None, False).
    """
    # Handle numeric types
    if col_dtype in (
        pl.Int8,
        pl.Int16,
        pl.Int32,
        pl.Int64,
        pl.UInt8,
        pl.UInt16,
        pl.UInt32,
        pl.UInt64,
    ):
        try:
            # Try to convert to integer
            converted = int(float(code))  # Handle cases like "-999.0"
            return converted, True  # noqa: TRY300
        except (ValueError, TypeError):
            return None, False

    if col_dtype in (pl.Float32, pl.Float64):
        try:
            # Try to convert to float
            converted = float(code)
            return converted, True  # noqa: TRY300
        except (ValueError, TypeError):
            return None, False

    # Handle string types - always successful
    if col_dtype in (pl.Utf8, pl.Categorical, pl.String):
        return str(code), True

    # Handle boolean types
    if col_dtype == pl.Boolean:
        lower_code = str(code).lower()
        if lower_code in ("true", "1", "yes"):
            return True, True
        if lower_code in ("false", "0", "no"):
            return False, True
        return None, False

    # For other types (including temporal types), return failure
    return None, False


def _compute_missing_data_paired(
    data: pl.DataFrame, missing_codes_df: pl.DataFrame
) -> pl.DataFrame:
    """Compute missing data DataFrame with missing codes applied (paired by label).

    Parameters
    ----------
    data : pl.DataFrame
        The dataset to analyze.
    missing_codes_df : pl.DataFrame
        The missing codes configuration.

    Returns
    -------
    pl.DataFrame
        DataFrame with:
        - 0 for non-missing values
        - 1 for NULL values
        - 2+ for special missing codes based on their position in missing_code_pairs
    """
    missing_code_pairs = _get_missing_code_pairs(missing_codes_df)
    expressions = []

    for col in data.columns:
        col_dtype = data[col].dtype

        # Start by marking everything as 0 (non-missing)
        result = pl.lit(0)

        # Replace NULL values with 1
        result = pl.when(pl.col(col).is_null()).then(pl.lit(1)).otherwise(result)

        # Skip special missing code checks for temporal types (date, datetime, time)
        if col_dtype in (pl.Date, pl.Datetime, pl.Time, pl.Duration):
            expressions.append(result.alias(col))
            continue

        # Replace special missing codes with position-based numbers (starting from 2)
        for idx, (_, codes) in enumerate(missing_code_pairs.items(), start=2):
            for code in codes:
                # Try to convert the code to match the column's type
                converted_code, conversion_success = _try_convert_code_to_column_type(
                    code, col_dtype, col
                )

                # Skip this code if conversion failed
                if not conversion_success:
                    continue

                try:
                    # Perform comparison with converted value
                    condition = pl.col(col) == converted_code
                    result = pl.when(condition).then(pl.lit(idx)).otherwise(result)
                except Exception:
                    # If comparison still fails, skip this code
                    continue

        expressions.append(result.alias(col))

    return data.select(expressions)


def _get_all_missing_codes(missing_codes_df: pl.DataFrame) -> list[str]:
    """Get all missing codes from the missing codes DataFrame.

    Parameters
    ----------
    missing_codes_df : pl.DataFrame
        The missing codes configuration.

    Returns
    -------
    list[str]
        List of all missing codes.
    """
    all_codes = []
    if not missing_codes_df.is_empty():
        for row in missing_codes_df.iter_rows(named=True):
            mc = row["codes"].split(",")
            all_codes.extend([code.strip() for code in mc if code.strip()])
    return all_codes


def _get_missing_code_pairs(missing_codes_df: pl.DataFrame) -> dict[str, list[str]]:
    """Get missing code label to codes mapping.

    Parameters
    ----------
    missing_codes_df : pl.DataFrame
        The missing codes configuration.

    Returns
    -------
    dict[str, list[str]]
        Mapping of missing code labels to their codes.
    """
    code_map = {}
    if not missing_codes_df.is_empty():
        for row in missing_codes_df.iter_rows(named=True):
            label = row["label"]
            codes = [code.strip() for code in row["codes"].split(",") if code.strip()]
            code_map[label] = codes
    return code_map


@st.cache_data
def compute_missing_summary(missing_data: pl.DataFrame) -> MissingSummaryStats:
    """Compute the summary of missing data in the dataset.

    Uses vectorized Polars operations for efficient computation.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1+ = missing.

    Returns
    -------
    MissingSummaryStats
        Summary statistics for missing data.
    """
    if missing_data.is_empty() or len(missing_data.columns) == 0:
        return MissingSummaryStats(
            mean_missing_pct=0.0,
            all_missing_pct=0.0,
            any_missing_pct=0.0,
            no_missing_pct=100.0,
        )

    n_rows = missing_data.height
    n_cols = len(missing_data.columns)

    # Vectorized computation: create binary missing indicator for all columns at once
    missing_indicators = missing_data.select(
        [(pl.col(col) > 0).alias(col) for col in missing_data.columns]
    )

    # Calculate statistics using aggregations
    col_stats = missing_indicators.select(
        [
            pl.sum_horizontal(pl.all()).alias("total_missing_per_row"),
            *[
                pl.col(col).sum().alias(f"missing_count_{col}")
                for col in missing_indicators.columns
            ],
        ]
    )

    # Extract missing counts per column
    missing_counts = [
        col_stats[f"missing_count_{col}"][0] for col in missing_indicators.columns
    ]

    # Calculate percentages
    missing_pcts = [(count / n_rows) * 100 for count in missing_counts]
    mean_missing = sum(missing_pcts) / n_cols

    # Count columns by missingness pattern
    all_missing_count = sum(1 for count in missing_counts if count == n_rows)
    any_missing_count = sum(1 for count in missing_counts if count > 0)
    no_missing_count = n_cols - any_missing_count

    return MissingSummaryStats(
        mean_missing_pct=mean_missing,
        all_missing_pct=(all_missing_count / n_cols) * 100,
        any_missing_pct=(any_missing_count / n_cols) * 100,
        no_missing_pct=(no_missing_count / n_cols) * 100,
    )


def compute_missing_columns(
    missing_data: pl.DataFrame, missing_codes_df: pl.DataFrame
) -> pd.DataFrame:
    """Compute the summary of missing values in each column.

    Uses vectorized Polars operations for efficient computation.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1 = NULL, 2+ = special codes.
    missing_codes_df : pl.DataFrame
        The missing codes configuration with label and codes columns.

    Returns
    -------
    pd.DataFrame
        The summary of missing values in each column with counts and percentages.
    """
    n_rows = missing_data.height
    missing_code_pairs = _get_missing_code_pairs(missing_codes_df)

    # Build aggregation expressions for all columns at once
    agg_expressions = []

    for col in missing_data.columns:
        # NULL count (value == 1)
        agg_expressions.append((pl.col(col) == 1).sum().alias(f"{col}_null"))

        # Count each special missing code type
        for idx, (label, _) in enumerate(missing_code_pairs.items(), start=2):
            agg_expressions.append((pl.col(col) == idx).sum().alias(f"{col}_{label}"))

        # Total missing count (value > 0)
        agg_expressions.append((pl.col(col) > 0).sum().alias(f"{col}_total"))

    # Execute aggregation in single pass
    stats = missing_data.select(agg_expressions)

    # Build result rows
    rows = []
    for col in missing_data.columns:
        null_count = stats[f"{col}_null"][0]
        null_pct = (null_count / n_rows) * 100

        row = {
            "Column": col,
            "Null Values": null_count,
            "% Null Values": null_pct,
        }

        # Add special code counts
        for label in missing_code_pairs:
            count = stats[f"{col}_{label}"][0]
            pct = (count / n_rows) * 100
            row[label] = count
            row[f"% {label}"] = pct

        # Add total
        total_count = stats[f"{col}_total"][0]
        total_pct = (total_count / n_rows) * 100
        row["Total Missing"] = total_count
        row["% Total Missing"] = total_pct

        rows.append(row)

    # Convert to pandas for display (only at the end)
    result_df = pd.DataFrame(rows)

    # Reorder columns
    base_cols = ["Column", "Total Missing", "% Total Missing"]
    other_cols = [col for col in result_df.columns if col not in base_cols]

    return result_df[base_cols + other_cols]


@st.cache_data
def compute_filtered_missing_columns(
    data: pd.DataFrame, mv_threshold: int
) -> tuple[pd.DataFrame, list[str], float, float]:
    """Compute filtered datasets and statistics based on threshold.

    Parameters
    ----------
    data : pd.DataFrame
        DataFrame with missing value statistics.
    mv_threshold : int
        Minimum threshold for filtering (0-100).

    Returns
    -------
    tuple
        (filtered_data, percentage_columns, min_value, max_value)
    """
    mv_data_filtered = data[data["% Total Missing"] >= mv_threshold]
    perc_cols = [col for col in data.columns if "%" in col]

    if not mv_data_filtered.empty:
        vmin_val = float(mv_data_filtered[perc_cols].min().min())
        vmax_val = float(mv_data_filtered[perc_cols].max().max())
    else:
        vmin_val = 0.0
        vmax_val = 100.0

    return mv_data_filtered, perc_cols, vmin_val, vmax_val


@st.cache_data
def compute_missing_over_time(
    missing_data: pl.DataFrame, data: pl.DataFrame, select_date_col: str
) -> pd.DataFrame:
    """Compute the missingness over time based on the selected date column.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1+ = missing.
    data : pl.DataFrame
        The original dataset (needed for date column).
    select_date_col : str
        The date column to group by.

    Returns
    -------
    pd.DataFrame
        DataFrame with missingness statistics over time.
    """
    # Extract date from the original data and convert to date only (no time)
    date_series = data[select_date_col].dt.date()

    # Add the date column to missing_data for grouping
    missing_with_date = missing_data.with_columns(
        date_series.alias("missingness_trend_date")
    )

    # Get all columns except the date column
    stat_cols = [col for col in missing_data.columns]
    n_cols = len(stat_cols)

    # Group by date and calculate total missing values (values > 0)
    missingness_by_date = missing_with_date.group_by("missingness_trend_date").agg(
        [
            # Count total data points per date (rows * columns)
            (pl.count() * n_cols).alias("total_data_points"),
            # Count total missing values (sum of all values > 0 across all columns)
            pl.sum_horizontal([(pl.col(col) > 0).sum() for col in stat_cols]).alias(
                "total_missing"
            ),
        ]
    )

    # Calculate missingness rate
    missingness_by_date = missingness_by_date.with_columns(
        ((pl.col("total_missing") / pl.col("total_data_points")) * 100).alias(
            "missingness_rate"
        )
    )

    # Sort by date and convert to pandas for plotting
    result = (
        missingness_by_date.sort("missingness_trend_date")
        .select(["missingness_trend_date", "missingness_rate"])
        .to_pandas()
    )

    return result


@st.cache_data
def compute_missing_compare(
    missing_data: pl.DataFrame,
    data: pl.DataFrame,
    group_by_col: str,
    compare_cols: list[str],
) -> tuple[pd.DataFrame, float, float]:
    """Compute the missingness comparison between groups.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1+ = missing.
    data : pl.DataFrame
        The original dataset (needed for grouping column values).
    group_by_col : str
        The column to group the data by.
    compare_cols : list[str]
        The columns to compare the missingness.

    Returns
    -------
    tuple
        (group_by_data DataFrame, minimum value, maximum value)
    """
    # Get value counts for the grouping column from original data
    group_counts = data.group_by(group_by_col).agg(pl.count().alias("values (count)"))
    total_rows = data.height

    # Calculate percentage
    group_counts = group_counts.with_columns(
        ((pl.col("values (count)") / total_rows) * 100).alias("values (%)")
    )

    if compare_cols:
        # For each comparison column, calculate % missing by group
        for col in compare_cols:
            # Add the grouping column to missing_data for grouping
            missing_with_group = missing_data.select(col).with_columns(
                data.select(group_by_col)
            )

            # Calculate % missing (values > 0) for each group
            col_missing_pct = missing_with_group.group_by(group_by_col).agg(
                [((pl.col(col) > 0).sum() / pl.count() * 100).alias(col)]
            )

            # Merge into group_counts
            group_counts = group_counts.join(
                col_missing_pct, on=group_by_col, how="left"
            )

        # Convert to pandas for display
        group_by_data = group_counts.to_pandas().set_index(group_by_col)

        vmin_val = float(group_by_data[compare_cols].min().min())
        vmax_val = float(group_by_data[compare_cols].max().max())
    else:
        # Convert to pandas for display
        group_by_data = group_counts.to_pandas().set_index(group_by_col)
        vmin_val = 0.0
        vmax_val = 100.0

    return group_by_data, vmin_val, vmax_val


@st.cache_data
def compute_missing_correlation(
    missing_data: pl.DataFrame, null_cols: list[str]
) -> pd.DataFrame:
    """Compute the correlation of missing data in the dataset.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1+ = missing.
    null_cols : list[str]
        The columns to calculate nullity correlation for.

    Returns
    -------
    pd.DataFrame
        The correlation of missing data in the dataset.
    """
    # Create binary missing indicator and select relevant columns
    missing_indicators = _create_binary_missing_indicator(
        missing_data.select(null_cols)
    )

    # Convert to pandas for correlation calculation (pandas has optimized corr())
    nullity_corr = missing_indicators.to_pandas().corr()

    # Keep only lower triangle (excluding diagonal)
    mask = np.tril(np.ones(nullity_corr.shape), k=-1).astype(bool)

    return nullity_corr.where(mask)


@st.cache_data
def get_null_list(missing_data: pl.DataFrame, all_cols: bool) -> list[str]:
    """Get list of columns depending on trigger for all columns.

    Uses vectorized Polars operations for efficient computation.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1+ = missing.
    all_cols : bool
        If True, return all columns. If False, return only columns
        with partial missingness.

    Returns
    -------
    list[str]
        List of column names.
    """
    if all_cols:
        return missing_data.columns

    # Vectorized check for partial missingness
    # Aggregate to find columns with both missing (>0) and non-missing (==0) values
    col_checks = missing_data.select(
        [
            pl.struct(
                [
                    (pl.col(col) > 0).any().alias("has_missing"),
                    (pl.col(col) == 0).any().alias("has_non_missing"),
                ]
            ).alias(col)
            for col in missing_data.columns
        ]
    )

    # Extract columns with partial missingness
    partial_missing_cols = [
        col
        for col in missing_data.columns
        if col_checks[col][0]["has_missing"] and col_checks[col][0]["has_non_missing"]
    ]

    return partial_missing_cols


@st.cache_data
def compute_missing_matrix(missing_data: pl.DataFrame) -> pd.DataFrame:
    """Compute the missingness matrix for the dataset.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1+ = missing.

    Returns
    -------
    pd.DataFrame
        The missingness matrix for the dataset (binary: 0 or 1), sorted by index.
    """
    # Create binary missing indicator and convert to pandas for visualization
    return _create_binary_missing_indicator(missing_data).to_pandas()


# =============================================================================
# UI Components - Missing Codes Management
# =============================================================================


def render_missing_codes_table(project_id: str) -> None:
    """Render the missing codes table with add/modify/delete controls.

    Parameters
    ----------
    project_id : str
        The project identifier.

    Returns
    -------
    pd.DataFrame
        DataFrame representation of missing codes.
    """
    missing_codes = load_missing_codes_from_db(project_id)
    table_name = f"missing_codes_{project_id}"

    # Create three popover buttons in a row
    col1, col2, col3 = st.columns([0.35, 0.35, 0.3])

    # Add button
    with col1, st.popover(":material/add: Add", width="stretch"):
        st.markdown("#### Add Missing Code")
        st.info(
            "Define a new missing code type. Eg., Don't Know, Refuse to Answer.",
            icon=":material/info:",
        )
        new_label = st.text_input("Label", key="add_label", help="E.g., Don't Know")
        new_codes = st.text_input(
            "Codes (comma-separated)", key="add_codes", help="E.g., -999, .999"
        )

        if st.button(
            "Add",
            key="add_submit",
            width="stretch",
            disabled=not new_label or not new_codes,
        ):
            add_missing_code(project_id, new_label, new_codes)
            st.success(f"Added '{new_label}'")
            st.rerun()

    # Modify button
    with col2, st.popover(":material/edit: Modify", width="stretch"):
        st.markdown("#### Modify Missing Code")
        st.info(
            "Select and modify an existing missing code type.", icon=":material/info:"
        )
        if not missing_codes.is_empty():
            options = missing_codes["label"].to_list()
            selected_label = st.selectbox(
                "Select code to modify", options=options, key="modify_select"
            )

            if selected_label:
                # get existing codes
                existing_codes = missing_codes.filter(
                    pl.col("label") == selected_label
                ).select("codes")[0, 0]

                modified_codes = st.text_input(
                    "Codes (comma-separated)",
                    value=existing_codes,
                    key="modify_codes",
                    help="E.g., -999, .999",
                )

            if st.button(
                "Modify",
                key="modify_submit",
                width="stretch",
                disabled=not selected_label or not modified_codes,
            ):
                # replace current code with new code, based on label
                updated_missing_code = missing_codes.with_columns(
                    pl.when(pl.col("label") == selected_label)
                    .then(pl.lit(modified_codes))
                    .otherwise(pl.col("codes"))
                    .alias("codes")
                )
                duckdb_save_table(project_id, updated_missing_code, table_name, "logs")
                st.success(f"Modified '{selected_label}'")
                st.rerun()
        else:
            st.info("No missing codes to modify")

    # Delete button
    with col3, st.popover(":material/delete: Delete", width="stretch"):
        st.markdown("#### Delete Missing Code")
        if not missing_codes.is_empty():
            options = missing_codes["label"].to_list()
            selected_label = st.selectbox(
                "Select code to delete",
                options=options,
                key="delete_select",
                index=None,
            )

            if selected_label:
                updated_missing_code = missing_codes.filter(
                    pl.col("label") != selected_label
                )

                if st.button(
                    "Confirm Delete",
                    key="delete_submit",
                    type="primary",
                    width="stretch",
                ):
                    duckdb_save_table(
                        project_id, updated_missing_code, table_name, "logs"
                    )
                    st.success(f"Deleted '{selected_label}'")
                    st.rerun()
        else:
            st.info("No missing codes to delete")

    # Display table in expander
    with st.expander("View Missing Codes Configuration", expanded=True):
        if not missing_codes.is_empty():
            show_df = missing_codes.select(
                pl.col("label").alias("Missing Label"),
                pl.col("codes").alias("Missing Codes"),
            )
            st.dataframe(
                show_df,
                width="stretch",
                hide_index=True,
                column_config={"Missing Codes": st.column_config.ListColumn()},
            )
        else:
            st.info("No missing codes configured. Use the Add button to create one.")


# =============================================================================
# UI Components - Report Sections
# =============================================================================


@demo_output_onboarding(TAB_NAME)
def missing_summary(missing_data: pl.DataFrame) -> None:
    """Generate a summary of missing data in the dataset.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1+ = missing.
    """
    summary_stats = compute_missing_summary(missing_data=missing_data)

    mc1, mc2, mc3, mc4 = st.columns(4)
    mc1.metric(
        label="Percentage of missing values",
        value=f"{summary_stats.mean_missing_pct:.2f}%",
        border=True,
        help="Mean percentage of missing values across all columns",
    )

    mc2.metric(
        label="% columns all missing",
        value=f"{summary_stats.all_missing_pct:.2f}%",
        border=True,
        help="Percentage of columns with all values missing",
    )

    mc3.metric(
        label="% columns any missing",
        value=f"{summary_stats.any_missing_pct:.2f}%",
        border=True,
        help="Percentage of columns with at least one missing value",
    )

    mc4.metric(
        label="% columns no missing",
        value=f"{summary_stats.no_missing_pct:.2f}%",
        border=True,
        help="Percentage of columns with no missing values",
    )


@demo_output_onboarding(TAB_NAME)
def missing_columns(
    missing_data: pl.DataFrame, missing_codes_df: pl.DataFrame, setting_file: str
) -> None:
    """Generate a table showing the percentage of missing values in each column.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1 = NULL, 2+ = special codes.
    missing_codes_df : pl.DataFrame
        The missing codes configuration with label and codes columns.
    setting_file : str
        Path to settings file.
    """
    _, _, _, slider_col = st.columns(4)

    default_settings = (
        load_check_settings(settings_file=setting_file, check_name="missing") or {}
    )
    mv_threshold = default_settings.get("mv_threshold", 0)

    with slider_col:
        mv_threshold = st.slider(
            label="Filter by % missing:",
            help="Filter columns by minimum percentage of missing values",
            min_value=0,
            max_value=100,
            value=mv_threshold,
            key="mv_threshold",
            on_change=trigger_save,
            kwargs={"state_name": "mv_threshold_save"},
        )
        if st.session_state.get("mv_threshold_save"):
            save_check_settings(
                settings_file=setting_file,
                check_name="missing",
                check_settings={"mv_threshold": mv_threshold},
            )
            st.session_state["mv_threshold_save"] = False

    mv_data = compute_missing_columns(
        missing_data=missing_data, missing_codes_df=missing_codes_df
    )
    mv_data_filtered, perc_cols, vmin_val, vmax_val = compute_filtered_missing_columns(
        data=mv_data, mv_threshold=mv_threshold
    )

    if not mv_data_filtered.empty:
        cmap = sns.light_palette("pink", as_cmap=True)
        styler_limit = mv_data_filtered.shape[0] * mv_data_filtered.shape[1]
        pd.set_option("styler.render.max_elements", styler_limit)

        st.dataframe(
            mv_data_filtered.style.format(
                subset=perc_cols, precision=2
            ).background_gradient(
                subset=perc_cols, cmap=cmap, axis=1, vmin=vmin_val, vmax=vmax_val
            ),
            width="stretch",
            hide_index=True,
            column_config={
                "Column": st.column_config.Column(pinned=True),
                "Total Missing": st.column_config.Column(pinned=True),
                "% Total Missing": st.column_config.Column(pinned=True),
            },
        )
    else:
        st.info("No columns meet the threshold criteria")


@demo_output_onboarding(TAB_NAME)
def missing_over_time(
    missing_data: pl.DataFrame, data: pl.DataFrame, setting_file: str
) -> None:
    """Generate a report on missing data over time.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1+ = missing.
    data : pl.DataFrame
        The original dataset (needed for date column).
    setting_file : str
        Path to settings file.
    """
    # Get datetime columns from Polars DataFrame
    date_cols = [
        col for col in data.columns if data[col].dtype in (pl.Date, pl.Datetime)
    ]

    if not date_cols:
        st.info("No datetime columns available for time series analysis")
        return

    default_settings = (
        load_check_settings(settings_file=setting_file, check_name="missing") or {}
    )
    select_date_col = default_settings.get("select_date_col")

    dc1, _ = st.columns([0.3, 0.7])
    with dc1:
        select_date_col_index = (
            date_cols.index(select_date_col)
            if select_date_col and select_date_col in date_cols
            else 0
        )

        select_date_col = st.selectbox(
            "Select date column",
            options=date_cols,
            index=select_date_col_index,
            key="select_date_col",
            help="Select the date column to compute missingness over time",
            on_change=trigger_save,
            kwargs={"state_name": "select_date_col_save"},
        )
        if st.session_state.get("select_date_col_save"):
            save_check_settings(
                settings_file=setting_file,
                check_name="missing",
                check_settings={"select_date_col": select_date_col},
            )
            st.session_state["select_date_col_save"] = False

    missingness_over_time = compute_missing_over_time(
        missing_data=missing_data, data=data, select_date_col=select_date_col
    )

    fig = px.area(
        missingness_over_time,
        x="missingness_trend_date",
        y="missingness_rate",
        title="Missingness over time",
        labels={
            "missingness_trend_date": select_date_col,
            "missingness_rate": "Missingness rate (%)",
        },
        color_discrete_sequence=["#e8848b"],
    )
    fig.update_layout(width=1000, height=500, yaxis_range=[0, 100])
    st.plotly_chart(fig, width="stretch")


@demo_output_onboarding(TAB_NAME)
def missing_compare(
    missing_data: pl.DataFrame, data: pl.DataFrame, setting_file: str
) -> None:
    """Generate a report comparing missing data between groups.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1+ = missing.
    data : pl.DataFrame
        The original dataset (needed for grouping column values).
    setting_file : str
        Path to settings file.
    """
    mc_1, mc_2 = st.columns([0.3, 0.7])

    with mc_1:
        # Get categorical/string columns from Polars DataFrame
        allowed_cols = [
            col
            for col in data.columns
            if data[col].dtype in (pl.Utf8, pl.Categorical, pl.String)
        ]

        if not allowed_cols:
            st.warning("No categorical columns available for grouping")
            return

        default_settings = (
            load_check_settings(settings_file=setting_file, check_name="missing") or {}
        )
        group_by_col = default_settings.get("group_by_col")
        group_by_col_index = (
            allowed_cols.index(group_by_col)
            if group_by_col and group_by_col in allowed_cols
            else 0
        )

        group_by_col = st.selectbox(
            label="Group by column",
            options=allowed_cols,
            index=group_by_col_index,
            key="group_by_col",
            on_change=trigger_save,
            kwargs={"state_name": "group_by_col_save"},
        )
        if st.session_state.get("group_by_col_save"):
            save_check_settings(
                settings_file=setting_file,
                check_name="missing",
                check_settings={"group_by_col": group_by_col},
            )
            st.session_state["group_by_col_save"] = False

        allowed_cols = [col for col in data.columns if col != group_by_col]

    with mc_2:
        compare_col = default_settings.get("compare_col", [])
        compare_col = st.multiselect(
            label="Compare columns",
            options=allowed_cols,
            default=compare_col if isinstance(compare_col, list) else [],
            key="compare_col",
            on_change=trigger_save,
            kwargs={"state_name": "compare_col_save"},
        )
        if st.session_state.get("compare_col_save"):
            save_check_settings(
                settings_file=setting_file,
                check_name="missing",
                check_settings={"compare_col": compare_col},
            )
            st.session_state["compare_col_save"] = False

    if not group_by_col:
        st.warning("Please select a column to group by")
        return

    group_by_data, vmin_val, vmax_val = compute_missing_compare(
        missing_data=missing_data,
        data=data,
        group_by_col=group_by_col,
        compare_cols=compare_col,
    )

    if not compare_col:
        st.dataframe(group_by_data, width="stretch")
    else:
        cmap = sns.light_palette("pink", as_cmap=True)
        styler_limit = group_by_data.shape[0] * group_by_data.shape[1]
        pd.set_option("styler.render.max_elements", styler_limit)

        st.dataframe(
            group_by_data.style.format(subset=compare_col, precision=2)
            .format(subset=["values (count)"], thousands=",")
            .format(subset=["values (%)"], precision=2)
            .background_gradient(
                subset=compare_col, cmap=cmap, axis=1, vmin=vmin_val, vmax=vmax_val
            ),
            width="stretch",
            column_config={
                "values (count)": st.column_config.Column(pinned=True),
                "values (%)": st.column_config.Column(pinned=True),
            },
        )


@demo_output_onboarding(TAB_NAME)
def missing_correlation(
    missing_data: pl.DataFrame, color_map: list, setting_file: str
) -> None:
    """Generate a report on missing data correlation.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1+ = missing.
    color_map : list
        The color map to use for the heatmap.
    setting_file : str
        Path to settings file.
    """
    mc1, mc2 = st.columns([0.1, 0.9])

    with mc1:
        default_settings = (
            load_check_settings(settings_file=setting_file, check_name="missing") or {}
        )
        all_cols = default_settings.get("all_cols", False)

        all_cols = st.toggle(
            label="All columns",
            value=all_cols,
            help="Include all columns (default: only columns with partial missingness)",
            key="all_cols",
            on_change=trigger_save,
            kwargs={"state_name": "all_cols_save"},
        )
        if st.session_state.get("all_cols_save"):
            save_check_settings(
                settings_file=setting_file,
                check_name="missing",
                check_settings={"all_cols": all_cols},
            )
            st.session_state["all_cols_save"] = False

        col_options = get_null_list(missing_data=missing_data, all_cols=all_cols)

    with mc2:
        null_cols_sel = default_settings.get("null_cols_sel", [])
        null_cols_sel = st.multiselect(
            label="Select columns for correlation",
            options=col_options,
            default=null_cols_sel if isinstance(null_cols_sel, list) else [],
            key="null_cols_sel",
            on_change=trigger_save,
            kwargs={"state_name": "null_cols_sel_save"},
        )
        if st.session_state.get("null_cols_sel_save"):
            save_check_settings(
                settings_file=setting_file,
                check_name="missing",
                check_settings={"null_cols_sel": null_cols_sel},
            )
            st.session_state["null_cols_sel_save"] = False

    if null_cols_sel and len(null_cols_sel) > 1:
        nullity_corr = compute_missing_correlation(
            missing_data=missing_data, null_cols=null_cols_sel
        )

        fig = px.imshow(nullity_corr, color_continuous_scale=color_map)
        fig.update_layout(width=1000, height=1000)
        st.plotly_chart(fig, width="stretch")
    else:
        st.warning("Select at least two columns to calculate correlation")


@demo_output_onboarding(TAB_NAME)
def missing_matrix(missing_data: pl.DataFrame, color_map: list) -> None:
    """Generate a report on missing data matrix.

    Parameters
    ----------
    missing_data : pl.DataFrame
        The missing data DataFrame where 0 = non-missing, 1+ = missing.
    color_map : list
        The color map to use for the heatmap.
    """
    nullity_matrix = compute_missing_matrix(missing_data=missing_data)

    fig = px.imshow(nullity_matrix, color_continuous_scale=color_map)
    fig.layout.coloraxis.showscale = False
    fig.update_layout(width=1000, height=1000)
    st.plotly_chart(fig, width="stretch")


# =============================================================================
# Main Report Function
# =============================================================================


@demo_output_onboarding(TAB_NAME)
def missing_report(
    project_id: str, page_name: str, data: pl.DataFrame, setting_file: str
) -> None:
    """Generate a report on missing data in the dataset.

    Parameters
    ----------
    project_id : str
        The project identifier.
    data : pd.DataFrame
        The dataset to analyze.
    setting_file : str
        Path to settings file.
    page_name : str
        Page name identifier.
    """
    sns_colormap = [
        [0.0, "#3f7f93"],
        [0.1, "#6397a7"],
        [0.2, "#88b1bd"],
        [0.3, "#acc9d2"],
        [0.4, "#d1e2e7"],
        [0.5, "#f2f2f2"],
        [0.6, "#f6cdd0"],
        [0.7, "#efa8ad"],
        [0.8, "#e8848b"],
        [0.9, "#e15e68"],
        [1.0, "#da3b46"],
    ]

    st.title("Missing data")

    # Missing codes configuration
    render_missing_codes_table(project_id)

    # create missing data and summary table
    missing_codes_df = load_missing_codes_from_db(project_id)
    missing_data = _compute_missing_data_paired(data, missing_codes_df)

    # Summary section
    missing_summary(missing_data)

    st.write("---")
    st.subheader("Missingness by column")
    missing_columns(
        missing_data=missing_data,
        missing_codes_df=missing_codes_df,
        setting_file=setting_file,
    )

    st.write("---")
    st.subheader("Compare missing data within groups")
    missing_compare(missing_data=missing_data, data=data, setting_file=setting_file)

    st.write("---")
    st.subheader("Missingness over time")
    missing_over_time(missing_data=missing_data, data=data, setting_file=setting_file)

    st.write("---")
    st.subheader("Nullity correlation")
    missing_correlation(
        missing_data=missing_data, color_map=sns_colormap, setting_file=setting_file
    )

    st.write("---")
    st.subheader("Nullity matrix")
    missing_matrix(missing_data=missing_data, color_map=sns_colormap)
