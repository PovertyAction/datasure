"""Descriptive statistics module for survey data quality checks.

This module provides comprehensive descriptive statistics functionality with:
- Per-column summary statistics (count, mean, median, std, min, max, Q1, Q3,
  skewness, kurtosis, outliers)
- Histogram distributions with adjustable bin count
- Box plot statistics (Q1, median, Q3, whiskers, outlier count)
- Value counts (frequency table with % share)
- Missing data rates with traffic-light colour coding
- Pearson correlation matrix across numeric columns
- GroupBy filter bar for slicing all views by a categorical variable
- Sidebar column selector with type badges
"""

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import polars as pl
import streamlit as st

from datasure.utils.dataframe_utils import ColumnByType

TAB_NAME: str = "descriptive_stats"

# Colour constants
_MISSING_GREEN = "#2ca02c"
_MISSING_AMBER = "#ff7f0e"
_MISSING_RED = "#d62728"
_CORR_COLORSCALE = [
    [0.0, "#d62728"],
    [0.5, "#ffffff"],
    [1.0, "#1f77b4"],
]


# =============================================================================
# Computation functions (pure, no Streamlit)
# =============================================================================


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
        median, std, min, max, q1, q3, skewness, kurtosis, outliers.
    """
    if not numeric_cols or df.is_empty():
        return pd.DataFrame()

    n_total = len(df)
    rows = []
    for col in numeric_cols:
        s = df[col].cast(pl.Float64, strict=False).drop_nulls()
        n_missing = df[col].null_count()
        n_valid = len(s)

        if n_valid == 0:
            rows.append(
                {
                    "column": col,
                    "count": 0,
                    "missing": n_missing,
                    "missing_pct": round(n_missing / n_total * 100, 1)
                    if n_total > 0
                    else 0.0,
                    "mean": None,
                    "median": None,
                    "std": None,
                    "min": None,
                    "max": None,
                    "q1": None,
                    "q3": None,
                    "skewness": None,
                    "kurtosis": None,
                    "outliers": 0,
                }
            )
            continue

        q1 = float(s.quantile(0.25, interpolation="midpoint") or 0.0)
        q3 = float(s.quantile(0.75, interpolation="midpoint") or 0.0)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outlier_count = int(((s < lower) | (s > upper)).sum())

        skew_val = s.skew() if n_valid >= 3 else None
        kurt_val = s.kurtosis() if n_valid >= 4 else None

        rows.append(
            {
                "column": col,
                "count": n_valid,
                "missing": n_missing,
                "missing_pct": round(n_missing / n_total * 100, 1)
                if n_total > 0
                else 0.0,
                "mean": round(float(s.mean() or 0.0), 4),
                "median": round(float(s.median() or 0.0), 4),
                "std": round(float(s.std() or 0.0), 4),
                "min": float(s.min() or 0.0),
                "max": float(s.max() or 0.0),
                "q1": round(q1, 4),
                "q3": round(q3, 4),
                "skewness": round(skew_val, 4) if skew_val is not None else None,
                "kurtosis": round(kurt_val, 4) if kurt_val is not None else None,
                "outliers": outlier_count,
            }
        )

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


def compute_box_plot_stats(df: pl.DataFrame, numeric_cols: list[str]) -> pd.DataFrame:
    """Compute box plot statistics (Q1, median, Q3, whiskers, outliers).

    Parameters
    ----------
    df : pl.DataFrame
        Input data.
    numeric_cols : list[str]
        Numeric column names to analyse.

    Returns
    -------
    pd.DataFrame
        One row per column with: column, q1, median, q3,
        whisker_low, whisker_high, outlier_count.
    """
    if not numeric_cols or df.is_empty():
        return pd.DataFrame()

    rows = []
    for col in numeric_cols:
        s = df[col].cast(pl.Float64, strict=False).drop_nulls()
        n_valid = len(s)

        if n_valid == 0:
            rows.append(
                {
                    "column": col,
                    "q1": None,
                    "median": None,
                    "q3": None,
                    "whisker_low": None,
                    "whisker_high": None,
                    "outlier_count": 0,
                }
            )
            continue

        q1 = float(s.quantile(0.25, interpolation="midpoint") or 0.0)
        q3 = float(s.quantile(0.75, interpolation="midpoint") or 0.0)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        in_range = s.filter((s >= lower) & (s <= upper))
        whisker_low = float(in_range.min() or lower)
        whisker_high = float(in_range.max() or upper)
        outlier_count = int(((s < lower) | (s > upper)).sum())

        rows.append(
            {
                "column": col,
                "q1": round(q1, 4),
                "median": round(float(s.median() or 0.0), 4),
                "q3": round(q3, 4),
                "whisker_low": round(whisker_low, 4),
                "whisker_high": round(whisker_high, 4),
                "outlier_count": outlier_count,
            }
        )

    return pd.DataFrame(rows)


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


def compute_missing_rate(df: pl.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Compute per-column missing rate.

    Parameters
    ----------
    df : pl.DataFrame
        Input data.
    columns : list[str]
        Column names to analyse.

    Returns
    -------
    pd.DataFrame
        Columns: column, missing_count, missing_pct, status
        (status: "OK" <5%, "Warning" 5-20%, "Critical" >20%).
    """
    if not columns or df.is_empty():
        return pd.DataFrame()

    n_total = len(df)
    rows = []
    for col in columns:
        n_missing = df[col].null_count()
        pct = round(n_missing / n_total * 100, 2) if n_total > 0 else 0.0
        if pct < 5:
            status = "OK"
        elif pct <= 20:
            status = "Warning"
        else:
            status = "Critical"
        rows.append(
            {
                "column": col,
                "missing_count": n_missing,
                "missing_pct": pct,
                "status": status,
            }
        )

    return pd.DataFrame(rows)


def compute_correlation_matrix(
    df: pl.DataFrame, numeric_cols: list[str]
) -> pd.DataFrame:
    """Compute Pearson correlation matrix across numeric columns.

    Parameters
    ----------
    df : pl.DataFrame
        Input data.
    numeric_cols : list[str]
        Numeric column names to include.

    Returns
    -------
    pd.DataFrame
        Correlation matrix (rows and columns are the numeric column names).
    """
    if len(numeric_cols) < 2 or df.is_empty():
        return pd.DataFrame()

    return (
        df.select(numeric_cols)
        .cast({col: pl.Float64 for col in numeric_cols}, strict=False)
        .to_pandas()
        .corr()
    )


# =============================================================================
# Internal rendering helpers
# =============================================================================


def _missing_colour(pct: float) -> str:
    """Return traffic-light colour for a missing percentage."""
    if pct < 5:
        return _MISSING_GREEN
    if pct <= 20:
        return _MISSING_AMBER
    return _MISSING_RED


def _render_groupby_filter(
    df: pl.DataFrame, categorical_cols: list[str]
) -> pl.DataFrame:
    """Render the GroupBy filter bar and return the filtered DataFrame.

    Parameters
    ----------
    df : pl.DataFrame
        Full dataset.
    categorical_cols : list[str]
        Categorical column names available for grouping.

    Returns
    -------
    pl.DataFrame
        Filtered (or original) DataFrame.
    """
    if not categorical_cols:
        return df

    col1, col2, col3 = st.columns([3, 3, 1])

    with col1:
        group_col = st.selectbox(
            "Filter by column",
            options=["(none)"] + categorical_cols,
            key="desc_groupby_col",
            label_visibility="collapsed",
        )

    filtered_df = df
    if group_col and group_col != "(none)":
        unique_vals = df[group_col].drop_nulls().unique().sort().to_list()
        with col2:
            group_val = st.selectbox(
                "Filter value",
                options=unique_vals,
                key="desc_groupby_val",
                label_visibility="collapsed",
            )
        with col3:
            if st.button("Clear", key="desc_groupby_clear"):
                st.session_state.desc_groupby_col = "(none)"
                st.rerun()

        filtered_df = df.filter(pl.col(group_col) == group_val)

    return filtered_df


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


def _render_column_selector(
    df: pl.DataFrame, columns: ColumnByType
) -> tuple[list[str], list[str]]:
    """Render the inline column selector with descriptive type labels.

    Parameters
    ----------
    df : pl.DataFrame
        Dataset (used to determine available columns).
    columns : ColumnByType
        Column type information.

    Returns
    -------
    tuple[list[str], list[str]]
        (selected_numeric_cols, selected_all_cols)
    """
    all_cols = [c for c in df.columns if c in columns.all_columns]
    num_cols = set(columns.numeric_columns)

    if "desc_editor_version" not in st.session_state:
        st.session_state.desc_editor_version = 0
    if "desc_select_mode" not in st.session_state:
        st.session_state.desc_select_mode = "all"

    def _on_type_change() -> None:
        st.session_state.desc_editor_version += 1

    with st.expander("Column Selector", expanded=True):
        btn1, btn2, btn3 = st.columns(3)

        if btn1.button("Clear All", key="desc_clr_all"):
            st.session_state.desc_editor_version += 1
            st.session_state.desc_select_mode = "none"
            st.rerun()
        if btn2.button("Select All", key="desc_sel_all"):
            st.session_state.desc_editor_version += 1
            st.session_state.desc_select_mode = "all"
            st.rerun()
        if btn3.button("Select by Type", key="desc_sel_by_type"):
            st.session_state.desc_editor_version += 1
            st.session_state.desc_select_mode = "by_type"
            st.rerun()

        selected_types: list[str] = []
        if st.session_state.desc_select_mode == "by_type":
            available_types = sorted(
                {_get_column_type_label(col, columns) for col in all_cols}
            )
            selected_types = st.multiselect(
                "Select types to include",
                options=available_types,
                key="desc_type_multiselect",
                on_change=_on_type_change,
            )

        mode = st.session_state.desc_select_mode
        selected_types_set = set(selected_types)

        col_df = pd.DataFrame(
            [
                {
                    "Column": col,
                    "Type": _get_column_type_label(col, columns),
                    "Include": (
                        True
                        if mode == "all"
                        else (
                            _get_column_type_label(col, columns) in selected_types_set
                            if mode == "by_type"
                            else False
                        )
                    ),
                }
                for col in all_cols
            ]
        )

        edited = st.data_editor(
            col_df,
            column_config={
                "Column": st.column_config.TextColumn("Column", disabled=True),
                "Type": st.column_config.TextColumn("Type", disabled=True),
                "Include": st.column_config.CheckboxColumn("Include", width="small"),
            },
            hide_index=True,
            use_container_width=True,
            key=f"desc_col_editor_{st.session_state.desc_editor_version}",
        )

    selected = edited[edited["Include"]]["Column"].tolist()
    selected_num = [c for c in selected if c in num_cols]
    return selected_num, selected


def _render_summary_stats_tab(df: pl.DataFrame, numeric_cols: list[str]) -> None:
    """Render the Summary Stats tab."""
    if not numeric_cols:
        st.info("No numeric columns selected.")
        return

    stats = compute_summary_stats(df, numeric_cols)
    if stats.empty:
        st.info("No data to display.")
        return

    view = st.radio(
        "View",
        ["Table", "Chart"],
        horizontal=True,
        key="desc_summary_view",
    )

    if view == "Table":
        st.dataframe(stats, use_container_width=True, hide_index=True)
    else:
        col_to_plot = st.selectbox("Column", numeric_cols, key="desc_summary_chart_col")
        hist_data = compute_histogram_data(df, col_to_plot, n_bins=20)
        if hist_data.empty:
            st.info("No data to plot.")
            return
        fig = px.bar(
            hist_data,
            x="bin_start",
            y="count",
            labels={"bin_start": col_to_plot, "count": "Count"},
            title=f"Distribution of {col_to_plot}",
        )
        row = stats[stats["column"] == col_to_plot]
        if not row.empty:
            mean_val = row["mean"].iloc[0]
            median_val = row["median"].iloc[0]
            if mean_val is not None:
                fig.add_vline(
                    x=mean_val,
                    line_dash="dash",
                    line_color="red",
                    annotation_text="mean",
                )
            if median_val is not None:
                fig.add_vline(
                    x=median_val,
                    line_dash="dot",
                    line_color="blue",
                    annotation_text="median",
                )
        st.plotly_chart(fig, use_container_width=True)


def _render_histogram_tab(df: pl.DataFrame, numeric_cols: list[str]) -> None:
    """Render the Histogram tab."""
    if not numeric_cols:
        st.info("No numeric columns selected.")
        return

    col_to_plot = st.selectbox("Column", numeric_cols, key="desc_hist_col")
    n_bins = st.slider(
        "Bins", min_value=5, max_value=100, value=20, key="desc_hist_bins"
    )

    hist_data = compute_histogram_data(df, col_to_plot, n_bins=n_bins)
    if hist_data.empty:
        st.info("No data to plot.")
        return

    fig = px.bar(
        hist_data,
        x="bin_start",
        y="count",
        labels={"bin_start": col_to_plot, "count": "Count"},
        title=f"Distribution of {col_to_plot}",
    )

    s = df[col_to_plot].cast(pl.Float64, strict=False).drop_nulls()
    if len(s) > 0:
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
        skew_val = s.skew() if len(s) >= 3 else None
        kurt_val = s.kurtosis() if len(s) >= 4 else None
        readout = []
        if skew_val is not None:
            readout.append(f"Skewness: **{skew_val:.3f}**")
        if kurt_val is not None:
            readout.append(f"Kurtosis: **{kurt_val:.3f}**")
        if readout:
            st.caption("  ·  ".join(readout))

    st.plotly_chart(fig, use_container_width=True)


def _render_box_plot_tab(df: pl.DataFrame, numeric_cols: list[str]) -> None:
    """Render the Box Plot tab."""
    if not numeric_cols:
        st.info("No numeric columns selected.")
        return

    stats = compute_box_plot_stats(df, numeric_cols)
    if stats.empty:
        st.info("No data to display.")
        return

    view = st.radio("View", ["Table", "Chart"], horizontal=True, key="desc_box_view")

    if view == "Table":
        st.dataframe(stats, use_container_width=True, hide_index=True)
    else:
        pandas_df = (
            df.select(numeric_cols)
            .cast({c: pl.Float64 for c in numeric_cols}, strict=False)
            .to_pandas()
        )

        fig = go.Figure()
        for col in numeric_cols:
            col_vals = pandas_df[col].dropna().tolist()
            if col_vals:
                fig.add_trace(go.Box(y=col_vals, name=col, boxpoints="outliers"))

        fig.update_layout(title="Box Plots", showlegend=False)
        st.plotly_chart(fig, use_container_width=True)


def _render_value_counts_tab(df: pl.DataFrame, all_selected_cols: list[str]) -> None:
    """Render the Value Counts tab."""
    if not all_selected_cols:
        st.info("No columns selected.")
        return

    col_to_analyse = st.selectbox("Column", all_selected_cols, key="desc_vc_col")
    top_n = st.slider("Top N categories", 5, 50, 20, key="desc_vc_topn")

    vc = compute_value_counts(df, col_to_analyse, top_n=top_n)
    if vc.empty:
        st.info("No data to display.")
        return

    view = st.radio("View", ["Table", "Chart"], horizontal=True, key="desc_vc_view")

    if view == "Table":
        st.dataframe(vc, use_container_width=True, hide_index=True)
    else:
        fig = px.bar(
            vc,
            x="value",
            y="count",
            text="pct",
            labels={"value": col_to_analyse, "count": "Count", "pct": "%"},
            title=f"Value counts: {col_to_analyse}",
        )
        fig.update_traces(texttemplate="%{text}%", textposition="outside")
        st.plotly_chart(fig, use_container_width=True)


def _render_missing_data_tab(df: pl.DataFrame, all_selected_cols: list[str]) -> None:
    """Render the Missing Data tab."""
    if not all_selected_cols:
        st.info("No columns selected.")
        return

    missing = compute_missing_rate(df, all_selected_cols)
    if missing.empty:
        st.info("No data to display.")
        return

    view = st.radio("View", ["Table", "Chart"], horizontal=True, key="desc_miss_view")

    if view == "Table":
        st.dataframe(missing, use_container_width=True, hide_index=True)
    else:
        colours = [_missing_colour(p) for p in missing["missing_pct"]]
        fig = go.Figure(
            go.Bar(
                x=missing["column"],
                y=missing["missing_pct"],
                marker_color=colours,
                text=[f"{p}%" for p in missing["missing_pct"]],
                textposition="outside",
            )
        )
        fig.add_hline(
            y=5, line_dash="dash", line_color=_MISSING_GREEN, annotation_text="5%"
        )
        fig.add_hline(
            y=20, line_dash="dash", line_color=_MISSING_AMBER, annotation_text="20%"
        )
        fig.update_layout(
            title="Missing data rate per column",
            yaxis_title="Missing %",
            xaxis_title="Column",
        )
        st.plotly_chart(fig, use_container_width=True)


def _render_correlation_tab(df: pl.DataFrame, numeric_cols: list[str]) -> None:
    """Render the Correlation Matrix tab."""
    if len(numeric_cols) < 2:
        st.info("Select at least 2 numeric columns to compute a correlation matrix.")
        return

    corr = compute_correlation_matrix(df, numeric_cols)
    if corr.empty:
        st.info("No data to display.")
        return

    view = st.radio("View", ["Table", "Chart"], horizontal=True, key="desc_corr_view")

    if view == "Table":
        st.dataframe(corr.round(3), use_container_width=True)
    else:
        fig = px.imshow(
            corr,
            color_continuous_scale=_CORR_COLORSCALE,
            zmin=-1,
            zmax=1,
            text_auto=".2f",
            title="Pearson Correlation Matrix",
        )
        fig.update_layout(coloraxis_colorbar_title="r")
        st.plotly_chart(fig, use_container_width=True)


# =============================================================================
# Public report entry point
# =============================================================================


def descriptive_report(df: pl.DataFrame | pd.DataFrame, columns: ColumnByType) -> None:
    """Render the full descriptive statistics page.

    Includes a GroupBy filter bar, inline column selector, and six stacked
    sections: Summary Stats, Histogram, Box Plot, Value Counts, Missing Data,
    and Correlation Matrix.

    Parameters
    ----------
    df : pl.DataFrame | pd.DataFrame
        Survey dataset to analyse. Pandas DataFrames are converted automatically.
    columns : ColumnByType
        Column type metadata for the dataset.
    """
    if isinstance(df, pd.DataFrame):
        df = pl.from_pandas(df)

    if df.is_empty():
        st.warning("The selected dataset is empty.")
        return

    n_total = len(df)

    # GroupBy filter bar
    st.markdown("**Filter**")
    filtered_df = _render_groupby_filter(df, columns.categorical_columns)

    n_filtered = len(filtered_df)
    if n_filtered != n_total:
        st.caption(f"{n_filtered:,} records (filtered from {n_total:,})")
    else:
        st.caption(f"{n_total:,} records")

    if filtered_df.is_empty():
        st.warning("No records match the selected filter.")
        return

    st.divider()

    # Inline column selector
    selected_num_cols, selected_all_cols = _render_column_selector(filtered_df, columns)

    if not selected_all_cols:
        st.info("No columns selected. Use the column selector above to select columns.")
        return

    st.divider()

    # Stacked sections
    st.subheader("Summary Stats")
    _render_summary_stats_tab(filtered_df, selected_num_cols)

    st.divider()

    st.subheader("Histogram")
    _render_histogram_tab(filtered_df, selected_num_cols)

    st.divider()

    st.subheader("Value Counts")
    _render_value_counts_tab(filtered_df, selected_all_cols)
