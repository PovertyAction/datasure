"""Descriptive statistics module for survey data quality checks.

This module provides comprehensive descriptive statistics functionality with:
- Per-column summary statistics (count, mean, median, std, min, max, Q1, Q3,
  skewness, kurtosis, outliers)
- Histogram distributions with adjustable bin count
- Value counts (frequency table with % share)
- GroupBy filter bar for slicing all views by a categorical variable
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import streamlit as st

from datasure.models.schemas import ColumnByType
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

TAB_NAME: str = "descriptive_stats"

# Colour constants
_ORANGE_HEX = "#f26529"

# =============================================================================
# Computation functions (pure, no Streamlit)
# =============================================================================


def _missing_pct(n_missing: int, n_total: int) -> float:
    """Return missing percentage rounded to 1 decimal place."""
    return round(n_missing / n_total * 100, 1) if n_total > 0 else 0.0


def _empty_col_stats(col: str, n_missing: int, n_total: int) -> dict:
    """Return a stats row for a column with no valid (non-null) values."""
    return {
        "column": col,
        "count": 0,
        "missing": n_missing,
        "missing_pct": _missing_pct(n_missing, n_total),
        "mean": None,
        "median": None,
        "std": None,
        "min": None,
        "max": None,
        "q1": None,
        "q3": None,
        "skewness": None,
        "kurtosis": None,
    }


def _col_stats(col: str, s: pl.Series, n_missing: int, n_total: int) -> dict:
    """Return a stats row for a column with sufficient valid values."""
    n_valid = len(s)
    q1 = float(s.quantile(0.25, interpolation="midpoint") or 0.0)
    q3 = float(s.quantile(0.75, interpolation="midpoint") or 0.0)
    skew_val = s.skew() if n_valid >= 3 else None
    kurt_val = s.kurtosis() if n_valid >= 4 else None
    return {
        "column": col,
        "count": n_valid,
        "missing": n_missing,
        "missing_pct": _missing_pct(n_missing, n_total),
        "mean": round(float(s.mean() or 0.0), 4),
        "median": round(float(s.median() or 0.0), 4),
        "std": round(float(s.std() or 0.0), 4),
        "min": float(s.min() or 0.0),
        "max": float(s.max() or 0.0),
        "q1": round(q1, 4),
        "q3": round(q3, 4),
        "skewness": round(skew_val, 4) if skew_val is not None else None,
        "kurtosis": round(kurt_val, 4) if kurt_val is not None else None,
    }


def compute_summary_stats(df: pl.DataFrame, numeric_cols: list[str]) -> pd.DataFrame:
    """Compute per-column summary statistics for numeric columns.

    Parameters
    ----------
    df : pl.DataFrame
        Input data.
    numeric_cols : list[str]
        Numeric column names to analyse.

    Returns
    -------
    pd.DataFrame
        One row per column with: column, count, missing, missing_pct, mean,
        median, std, min, max, q1, q3, skewness, kurtosis.
    """
    if not numeric_cols or df.is_empty():
        return pd.DataFrame()

    n_total = len(df)
    rows = []
    for col in numeric_cols:
        s = df[col].cast(pl.Float64, strict=False).drop_nulls()
        n_missing = df[col].null_count()
        if len(s) == 0:
            rows.append(_empty_col_stats(col, n_missing, n_total))
        else:
            rows.append(_col_stats(col, s, n_missing, n_total))

    return pd.DataFrame(rows)


def compute_histogram_data(
    df: pl.DataFrame, column: str, n_bins: int = 20
) -> pd.DataFrame:
    """Compute histogram bin counts for a numeric column.

    Parameters
    ----------
    df : pl.DataFrame
        Input data.
    column : str
        Column to compute histogram for.
    n_bins : int
        Number of histogram bins.

    Returns
    -------
    pd.DataFrame
        Columns: bin_start, bin_end, count.
    """
    if df.is_empty() or column not in df.columns:
        return pd.DataFrame()

    values = df[column].cast(pl.Float64, strict=False).drop_nulls().to_numpy()
    if len(values) == 0:
        return pd.DataFrame()

    counts, bin_edges = np.histogram(values, bins=n_bins)
    return pd.DataFrame(
        {
            "bin_start": bin_edges[:-1],
            "bin_end": bin_edges[1:],
            "count": counts,
        }
    )


def compute_value_counts(
    df: pl.DataFrame, column: str, top_n: int = 20
) -> pd.DataFrame:
    """Compute value frequency table with percentage share.

    Parameters
    ----------
    df : pl.DataFrame
        Input data.
    column : str
        Column to compute value counts for.
    top_n : int
        Maximum number of categories to return.

    Returns
    -------
    pd.DataFrame
        Columns: value, count, pct.
    """
    if df.is_empty() or column not in df.columns:
        return pd.DataFrame()

    n_total = len(df)
    vc = (
        df.group_by(column)
        .agg(pl.len().alias("count"))
        .sort("count", descending=True)
        .head(top_n)
    )

    result = vc.with_columns(
        (pl.col("count") / n_total * 100).round(1).alias("pct")
    ).rename({column: "value"})

    return result.to_pandas()


# create column selection dataframe with type labels
def _create_new_column_selection_df(
    df: pl.DataFrame, columns: ColumnByType
) -> pl.DataFrame:
    """Create a DataFrame for the column selector with descriptive type labels."""
    all_cols = df.columns
    selected = [False] * len(all_cols)
    col_types = []
    for col in all_cols:
        if col in columns.datetime_columns:
            col_types.append("datetime")
        elif col in columns.numeric_columns:
            col_types.append("numeric")
        elif col in columns.categorical_columns:
            col_types.append("categorical")
        elif col in columns.string_columns:
            col_types.append("string")
        else:
            col_types.append("other")

    return pl.DataFrame({"Selected": selected, "column": all_cols, "type": col_types})


def _modify_column_selection_df(
    column_selection_df: pl.DataFrame, current_cols: set[str]
) -> pl.DataFrame:
    """Modify the column selection DataFrame to match the current dataset columns."""
    existing_cols = set(column_selection_df["column"])
    cols_to_add = current_cols - existing_cols
    cols_to_remove = existing_cols - current_cols

    # Remove columns that no longer exist
    if cols_to_remove:
        column_selection_df = column_selection_df.filter(
            ~pl.col("column").is_in(list(cols_to_remove))
        )

    # Add new columns that are not in the existing DataFrame
    for col in cols_to_add:
        column_selection_df = column_selection_df.concat(
            pl.DataFrame(
                {
                    "Selected": [False],
                    "column": [col],
                    "type": [_get_column_type_label(col, existing_cols)],
                }
            ),
            allow_duplicates=False,
        )

    return column_selection_df


def get_column_selection_df(
    project_id: str, df: pl.DataFrame, columns: ColumnByType
) -> pl.DataFrame:
    """Retrieve the column selection DataFrame from duckdb or create a new one."""
    try:
        column_selection_df = duckdb_get_table(
            project_id,
            "selected_columns_df",
            "intermediate",
        )
        current_cols = set(df.columns)
        if not set(column_selection_df["column"]).issubset(current_cols):
            return _modify_column_selection_df(column_selection_df, current_cols)
    except Exception:
        # If the table doesn't exist or columns mismatch, create a new one
        return _create_new_column_selection_df(df, columns)
    else:
        return column_selection_df


# =============================================================================
# Internal rendering helpers
# =============================================================================


def _get_column_type_label(col: str, columns: ColumnByType) -> str:
    """Return a descriptive type label for a column."""
    if col in columns.datetime_columns:
        return "datetime"
    if col in columns.numeric_columns:
        return "numeric"
    if col in columns.categorical_columns:
        return "categorical"
    if col in columns.string_columns:
        return "string"
    return "other"


@st.fragment
def _render_column_selector(
    project_id: str,
    df: pl.DataFrame,
    columns: ColumnByType,
    column_selection_df: pl.DataFrame,
) -> ColumnByType:
    """Render the inline column selector with descriptive type labels.

    Parameters
    ----------
    df : pl.DataFrame
        Dataset (used to determine available columns).
    columns : ColumnByType
        Column type information.

    Returns
    -------
    ColumnByType
        Selected columns by type.
    """
    options_map = {
        "clear_all": ":material/clear_all: Clear All",
        "select_all": ":material/select_all: Select All",
        "select_by_type": ":material/category: Select by Type",
    }

    type_options_map = {
        "numeric": ":material/123: Numeric",
        "categorical": ":material/ad_group: Categorical",
        "datetime": ":material/event: Datetime",
        "string": ":material/abc: String",
    }

    with st.expander(
        "Expand to Select Columns for Descriptive Analysis", expanded=True
    ):
        select_mode = st.pills(
            "Select Columns to Include in Analysis",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            key="desc_select_mode_pills",
            help="Quick selection options for columns",
        )

        if select_mode == "select_by_type":
            select_mode_type = st.pills(
                "Select Types",
                options=type_options_map.keys(),
                format_func=lambda x: type_options_map[x],
                key="desc_select_mode_type_pills",
                help="Select column types to include",
                selection_mode="multi",
            )
        else:
            select_mode_type = []

        quick_select_df = column_selection_df.clone()
        if select_mode == "select_all":
            quick_select_df = quick_select_df.with_columns(
                pl.lit(True).alias("Selected")
            )
        elif select_mode == "clear_all":
            quick_select_df = quick_select_df.with_columns(pl.lit(0).alias("Selected"))
        elif select_mode == "select_by_type" and select_mode_type:
            quick_select_df = quick_select_df.with_columns(
                pl.when(pl.col("type").is_in(select_mode_type))
                .then(True)
                .otherwise(pl.col("Selected"))
                .alias("Selected")
            )

        selected_columns_df = st.data_editor(
            quick_select_df,
            column_config={
                "Selected": st.column_config.CheckboxColumn(
                    "Include in analysis",
                    help="Check to include this column in the descriptive analysis",
                ),
                "column": st.column_config.TextColumn(
                    "Column name", help="Name of the column in the dataset"
                ),
                "type": st.column_config.TextColumn(
                    "Inferred type",
                    help="Inferred type of the column (numeric, categorical, datetime, string, other)",
                ),
            },
            hide_index=True,
            key="desc_column_selector",
        )

        if st.button(
            "Apply Selection",
            key="desc_apply_selection",
            type="primary",
            width="stretch",
        ):
            duckdb_save_table(
                project_id,
                selected_columns_df,
                "selected_columns_df",
                "intermediate",
            )
            st.rerun()

    selected_numeric_cols = selected_columns_df.filter(
        pl.col("Selected").cast(pl.Boolean) & (pl.col("type") == "numeric")
    )["column"].to_list()

    selected_all_cols = selected_columns_df.filter(pl.col("Selected").cast(pl.Boolean))[
        "column"
    ].to_list()

    return ColumnByType(
        all_columns=selected_all_cols,
        numeric_columns=selected_numeric_cols,
    )


def _render_summary_stats(df: pl.DataFrame, numeric_cols: list[str]) -> None:
    """Render the Summary Stats tab."""
    if not numeric_cols:
        st.info("No numeric columns selected.")
        return

    stats = compute_summary_stats(df, numeric_cols)
    if stats.empty:
        st.info("No data to display.")
        return

    st.dataframe(
        stats,
        width="stretch",
        hide_index=True,
        column_config={
            "column": st.column_config.TextColumn("Column", pinned=True),
            "count": st.column_config.NumberColumn("Count"),
            "missing": st.column_config.NumberColumn("Missing"),
            "missing_pct": st.column_config.ProgressColumn(
                "Missing %",
                help="Percentage of total, shown as a progress bar",
                format="%0.1f%%",
                min_value=0,
                max_value=100,
                width="medium",
            ),
            "mean": st.column_config.NumberColumn("Mean", format="%0.2f"),
            "median": st.column_config.NumberColumn("Median", format="%0.2f"),
            "std": st.column_config.NumberColumn("Std Dev", format="%0.2f"),
            "min": st.column_config.NumberColumn("Min", format="%0.2f"),
            "max": st.column_config.NumberColumn("Max", format="%0.2f"),
            "q1": st.column_config.NumberColumn("Q1", format="%0.2f"),
            "q3": st.column_config.NumberColumn("Q3", format="%0.2f"),
            "skewness": st.column_config.NumberColumn("Skewness", format="%0.2f"),
            "kurtosis": st.column_config.NumberColumn("Kurtosis", format="%0.2f"),
        },
    )


def _add_distribution_vlines(fig: go.Figure, s: pl.Series) -> None:
    """Add mean and median vertical lines to a histogram figure."""
    mean_val = s.mean()
    median_val = s.median()
    if mean_val is not None:
        fig.add_vline(
            x=float(mean_val),
            line_dash="dash",
            line_color="red",
            annotation_text=f"mean={mean_val:.2f}",
        )
    if median_val is not None:
        fig.add_vline(
            x=float(median_val),
            line_dash="dot",
            line_color="blue",
            annotation_text=f"median={median_val:.2f}",
        )


def _build_shape_caption(s: pl.Series) -> str:
    """Return a skewness/kurtosis caption string, or empty string if unavailable."""
    n = len(s)
    skew_val = s.skew() if n >= 3 else None
    kurt_val = s.kurtosis() if n >= 4 else None
    parts = []
    if skew_val is not None:
        parts.append(f"Skewness: **{skew_val:.3f}**")
    if kurt_val is not None:
        parts.append(f"Kurtosis: **{kurt_val:.3f}**")
    return "  ·  ".join(parts)


@st.fragment
def _render_histogram(
    df: pl.DataFrame, numeric_cols: list[str], setting_file: str
) -> None:
    """Render the Histogram section."""
    if not numeric_cols:
        st.info("No numeric columns selected.")
        return

    col_sel, _, bins_sel = st.columns([3, 1, 2])

    saved_settings = load_check_settings(setting_file, TAB_NAME) or {}
    default_col_to_plot = saved_settings.get("col_to_plot", None)

    default_col_to_plot_index = (
        numeric_cols.index(default_col_to_plot)
        if default_col_to_plot in numeric_cols
        else 0
    )

    col_to_plot = col_sel.selectbox(
        "Column",
        numeric_cols,
        index=default_col_to_plot_index,
        key="desc_hist_col",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_col_to_plot"},
    )
    save_check_settings(setting_file, TAB_NAME, {"col_to_plot": col_to_plot})

    default_n_bins = saved_settings.get("n_bins", 20)

    n_bins = bins_sel.slider(
        "Bins",
        min_value=5,
        max_value=100,
        value=default_n_bins,
        key="desc_hist_bins",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_n_bins"},
    )
    save_check_settings(setting_file, TAB_NAME, {"n_bins": n_bins})

    hist_data = compute_histogram_data(df, col_to_plot, n_bins=n_bins)
    if hist_data.empty:
        st.info("No data to plot.")
        return

    fig = px.bar(
        hist_data,
        x="bin_start",
        y="count",
        labels={"bin_start": col_to_plot, "count": "Count"},
        color_discrete_sequence=[_ORANGE_HEX],
        title=f"Distribution of {col_to_plot}",
    )

    s = df[col_to_plot].cast(pl.Float64, strict=False).drop_nulls()
    if len(s) > 0:
        _add_distribution_vlines(fig, s)
        caption = _build_shape_caption(s)
        if caption:
            st.caption(caption)

    st.plotly_chart(fig, width="stretch")


@st.fragment
def _render_value_counts(
    df: pl.DataFrame, all_selected_cols: list[str], setting_file: str
) -> None:
    """Render the Value Counts tab."""
    if not all_selected_cols:
        st.info("No columns selected.")
        return

    col_sel, _, topn_sel = st.columns([3, 1, 2])

    saved_settings = load_check_settings(setting_file, TAB_NAME) or {}
    default_col_to_analyse = saved_settings.get("col_to_analyse", None)
    default_col_to_analyse_index = (
        all_selected_cols.index(default_col_to_analyse)
        if default_col_to_analyse in all_selected_cols
        else 0
    )

    col_to_analyse = col_sel.selectbox(
        "Column",
        all_selected_cols,
        index=default_col_to_analyse_index,
        key="desc_vc_col",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_col_to_analyse"},
    )
    save_check_settings(setting_file, TAB_NAME, {"col_to_analyse": col_to_analyse})

    default_top_n = saved_settings.get("top_n", 20)

    top_n = topn_sel.slider(
        "Top N categories",
        5,
        50,
        value=default_top_n,
        key="desc_vc_topn",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_top_n"},
    )
    save_check_settings(setting_file, TAB_NAME, {"top_n": top_n})

    vc = compute_value_counts(df, col_to_analyse, top_n=top_n)
    if vc.empty:
        st.info("No data to display.")
        return

    options_map = {
        "table": ":material/table_chart: Table View",
        "chart": ":material/bar_chart: Chart View",
    }

    default_view = saved_settings.get("view", "table")

    view = st.pills(
        "Select view",
        default=default_view,
        options=options_map.keys(),
        format_func=lambda x: options_map[x],
        key="desc_vc_view_pills",
        help="Toggle between table and chart view for value counts",
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + "_view"},
    )
    save_check_settings(setting_file, TAB_NAME, {"view": view})

    if view == "table":
        st.dataframe(
            vc,
            width="stretch",
            hide_index=True,
            column_config={
                "value": st.column_config.TextColumn("Value"),
                "count": st.column_config.NumberColumn("Count"),
                "pct": st.column_config.ProgressColumn(
                    "Percentage",
                    help="Percentage of total, shown as a progress bar",
                    format="%0.1f%%",
                    min_value=0,
                    max_value=100,
                ),
            },
        )
    else:
        default_agg_option = saved_settings.get("agg_option", "count")
        agg_options_map = {
            "count": ":material/123: Count",
            "pct": ":material/percent: Percentage",
        }

        agg_options = st.pills(
            "Aggregate by",
            options=agg_options_map.keys(),
            format_func=lambda x: agg_options_map[x],
            key="desc_vc_agg_pills",
            help="Choose whether to size bars by count or percentage",
            default=default_agg_option,
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_agg_option"},
        )
        save_check_settings(setting_file, TAB_NAME, {"agg_option": agg_options})

        # Create the figure
        fig = go.Figure()

        # Add bar plot for interviews per time period with conditional coloring
        count_hovertemplate = "<b>%{x}</b><br>Count: %{y}<br>"
        pct_hovertemplate = "<b>%{x}</b><br>Percentage: %{y}%<br>"
        fig.add_trace(
            go.Bar(
                x=vc["value"],
                y=vc[agg_options],
                name="",
                marker_color=_ORANGE_HEX,
                hovertemplate=count_hovertemplate
                if agg_options == "count"
                else pct_hovertemplate,
            )
        )

        # Update layout with transparent background
        fig.update_layout(
            title=f"Value counts for {col_to_analyse}",
            title_x=0,
            plot_bgcolor="rgba(0,0,0,0)",
            paper_bgcolor="rgba(0,0,0,0)",
            height=400,
            margin={"t": 50, "b": 50, "l": 50, "r": 50},
            legend={
                "orientation": "h",
                "yanchor": "bottom",
                "y": 1.02,
                "xanchor": "right",
                "x": 1,
            },
            xaxis={
                "title": col_to_analyse,
                "showgrid": False,
                "gridcolor": "lightgrey",
                "tickangle": -45,
                "type": "category",
            },
            yaxis={
                "title_text": "Values" if agg_options == "count" else "Percentage",
                "showgrid": False,
                "gridcolor": "lightgrey",
                "zeroline": False,
            },
        )

        st.plotly_chart(fig, theme=None, width="stretch")


# =============================================================================
# Public report entry point
# =============================================================================


def descriptive_report(
    project_id: str,
    data: pl.DataFrame,
    setting_file: str,
    survey_columns: ColumnByType,
) -> None:
    """Render the full descriptive statistics page.

    Includes inline column selector, and six stacked
    sections: Summary Stats, Histogram, Box Plot, Value Counts, Missing Data,
    and Correlation Matrix.

    Parameters
    ----------
    df : pl.DataFrame | pd.DataFrame
        Survey dataset to analyse. Pandas DataFrames are converted automatically.
    columns : ColumnByType
        Column type metadata for the dataset.
    """
    st.title("Descriptive Statistics")

    # check if DataFrame is empty before proceeding with any computations or rendering
    if data.is_empty():
        st.warning("The selected dataset is empty.")
        return

    column_selection_df = get_column_selection_df(project_id, data, survey_columns)

    # Inline column selector
    selected_columns = _render_column_selector(
        project_id, data, survey_columns, column_selection_df
    )

    if not selected_columns.all_columns:
        st.info("No columns selected. Use the column selector above to select columns.")
        return

    st.write("---")

    # Stacked sections
    st.subheader("Summary Stats")
    _render_summary_stats(data, selected_columns.numeric_columns)

    st.write("---")
    st.subheader("Histogram")
    _render_histogram(data, selected_columns.numeric_columns, setting_file)

    st.write("---")
    st.subheader("Value Counts")
    _render_value_counts(data, selected_columns.all_columns, setting_file)
