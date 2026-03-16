"""Test descriptive statistics computation functions."""

import numpy as np
import pandas as pd
import polars as pl
import pytest

from datasure.checks.descriptive import (
    compute_box_plot_stats,
    compute_correlation_matrix,
    compute_histogram_data,
    compute_missing_rate,
    compute_summary_stats,
    compute_value_counts,
)
from datasure.utils.dataframe_utils import get_df_columns

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def sample_df() -> pl.DataFrame:
    """Numeric and categorical survey data with known properties."""
    return pl.DataFrame(
        {
            "age": [25, 30, 35, 40, 45, 50, 55, 200, None, 30],
            "income": [
                1000.0,
                2000.0,
                3000.0,
                4000.0,
                5000.0,
                None,
                None,
                6000.0,
                7000.0,
                2000.0,
            ],
            "region": [
                "North",
                "South",
                "North",
                "East",
                "South",
                "North",
                "East",
                "West",
                None,
                "North",
            ],
            "gender": ["M", "F", "M", "F", "M", None, "F", "M", "F", "M"],
        }
    )


@pytest.fixture
def empty_df() -> pl.DataFrame:
    """Empty DataFrame for edge case testing."""
    return pl.DataFrame()


@pytest.fixture
def all_null_df() -> pl.DataFrame:
    """DataFrame with a single all-null column."""
    return pl.DataFrame({"x": pl.Series([None, None, None], dtype=pl.Float64)})


# =============================================================================
# compute_summary_stats
# =============================================================================


class TestComputeSummaryStats:
    """Tests for compute_summary_stats."""

    def test_returns_dataframe(self, sample_df):
        result = compute_summary_stats(sample_df, ["age", "income"])
        assert isinstance(result, pd.DataFrame)

    def test_columns_present(self, sample_df):
        result = compute_summary_stats(sample_df, ["age"])
        expected_cols = {
            "column",
            "count",
            "missing",
            "missing_pct",
            "mean",
            "median",
            "std",
            "min",
            "max",
            "q1",
            "q3",
            "skewness",
            "kurtosis",
            "outliers",
        }
        assert expected_cols.issubset(set(result.columns))

    def test_one_row_per_column(self, sample_df):
        result = compute_summary_stats(sample_df, ["age", "income"])
        assert len(result) == 2

    def test_missing_count_correct(self, sample_df):
        result = compute_summary_stats(sample_df, ["age"])
        row = result[result["column"] == "age"].iloc[0]
        assert row["missing"] == 1

    def test_missing_pct_correct(self, sample_df):
        result = compute_summary_stats(sample_df, ["income"])
        row = result[result["column"] == "income"].iloc[0]
        assert row["missing_pct"] == pytest.approx(20.0)

    def test_outlier_detected(self, sample_df):
        # age=200 is a clear outlier
        result = compute_summary_stats(sample_df, ["age"])
        row = result[result["column"] == "age"].iloc[0]
        assert row["outliers"] >= 1

    def test_empty_df_returns_empty(self, empty_df):
        result = compute_summary_stats(empty_df, ["age"])
        assert result.empty

    def test_empty_col_list_returns_empty(self, sample_df):
        result = compute_summary_stats(sample_df, [])
        assert result.empty

    def test_all_null_column(self, all_null_df):
        result = compute_summary_stats(all_null_df, ["x"])
        assert len(result) == 1
        assert result.iloc[0]["count"] == 0
        assert result.iloc[0]["mean"] is None

    def test_min_max_correct(self):
        df = pl.DataFrame({"v": [1.0, 2.0, 3.0, 4.0, 5.0]})
        result = compute_summary_stats(df, ["v"])
        row = result.iloc[0]
        assert row["min"] == pytest.approx(1.0)
        assert row["max"] == pytest.approx(5.0)


# =============================================================================
# compute_histogram_data
# =============================================================================


class TestComputeHistogramData:
    """Tests for compute_histogram_data."""

    def test_returns_dataframe(self, sample_df):
        result = compute_histogram_data(sample_df, "age")
        assert isinstance(result, pd.DataFrame)

    def test_columns_present(self, sample_df):
        result = compute_histogram_data(sample_df, "age")
        assert set(result.columns) == {"bin_start", "bin_end", "count"}

    def test_bin_count_matches_n_bins(self, sample_df):
        result = compute_histogram_data(sample_df, "age", n_bins=10)
        assert len(result) == 10

    def test_total_count_matches_non_null(self, sample_df):
        result = compute_histogram_data(sample_df, "age", n_bins=5)
        non_null = sample_df["age"].drop_nulls().__len__()
        assert result["count"].sum() == non_null

    def test_empty_df_returns_empty(self, empty_df):
        result = compute_histogram_data(empty_df, "age")
        assert result.empty

    def test_missing_column_returns_empty(self, sample_df):
        result = compute_histogram_data(sample_df, "nonexistent")
        assert result.empty

    def test_all_null_column_returns_empty(self, all_null_df):
        result = compute_histogram_data(all_null_df, "x")
        assert result.empty


# =============================================================================
# compute_box_plot_stats
# =============================================================================


class TestComputeBoxPlotStats:
    """Tests for compute_box_plot_stats."""

    def test_returns_dataframe(self, sample_df):
        result = compute_box_plot_stats(sample_df, ["age", "income"])
        assert isinstance(result, pd.DataFrame)

    def test_one_row_per_column(self, sample_df):
        result = compute_box_plot_stats(sample_df, ["age", "income"])
        assert len(result) == 2

    def test_columns_present(self, sample_df):
        result = compute_box_plot_stats(sample_df, ["age"])
        expected = {
            "column",
            "q1",
            "median",
            "q3",
            "whisker_low",
            "whisker_high",
            "outlier_count",
        }
        assert expected.issubset(set(result.columns))

    def test_q1_le_median_le_q3(self):
        df = pl.DataFrame({"v": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]})
        result = compute_box_plot_stats(df, ["v"])
        row = result.iloc[0]
        assert row["q1"] <= row["median"] <= row["q3"]

    def test_outlier_detected(self, sample_df):
        result = compute_box_plot_stats(sample_df, ["age"])
        row = result[result["column"] == "age"].iloc[0]
        assert row["outlier_count"] >= 1

    def test_empty_df_returns_empty(self, empty_df):
        result = compute_box_plot_stats(empty_df, ["age"])
        assert result.empty

    def test_empty_col_list_returns_empty(self, sample_df):
        result = compute_box_plot_stats(sample_df, [])
        assert result.empty


# =============================================================================
# compute_value_counts
# =============================================================================


class TestComputeValueCounts:
    """Tests for compute_value_counts."""

    def test_returns_dataframe(self, sample_df):
        result = compute_value_counts(sample_df, "region")
        assert isinstance(result, pd.DataFrame)

    def test_columns_present(self, sample_df):
        result = compute_value_counts(sample_df, "region")
        assert set(result.columns) == {"value", "count", "pct"}

    def test_sorted_descending(self, sample_df):
        result = compute_value_counts(sample_df, "region")
        counts = result["count"].tolist()
        assert counts == sorted(counts, reverse=True)

    def test_pct_at_most_100(self, sample_df):
        # pct denominator is total rows; top_n subset may not reach 100%
        result = compute_value_counts(sample_df, "region", top_n=100)
        assert result["pct"].sum() <= 100.0

    def test_top_n_respected(self, sample_df):
        result = compute_value_counts(sample_df, "region", top_n=2)
        assert len(result) <= 2

    def test_empty_df_returns_empty(self, empty_df):
        result = compute_value_counts(empty_df, "region")
        assert result.empty

    def test_missing_column_returns_empty(self, sample_df):
        result = compute_value_counts(sample_df, "nonexistent")
        assert result.empty


# =============================================================================
# compute_missing_rate
# =============================================================================


class TestComputeMissingRate:
    """Tests for compute_missing_rate."""

    def test_returns_dataframe(self, sample_df):
        result = compute_missing_rate(sample_df, ["age", "income", "region"])
        assert isinstance(result, pd.DataFrame)

    def test_columns_present(self, sample_df):
        result = compute_missing_rate(sample_df, ["age"])
        assert set(result.columns) == {
            "column",
            "missing_count",
            "missing_pct",
            "status",
        }

    def test_one_row_per_column(self, sample_df):
        result = compute_missing_rate(sample_df, ["age", "income"])
        assert len(result) == 2

    def test_missing_count_correct(self, sample_df):
        result = compute_missing_rate(sample_df, ["age"])
        row = result[result["column"] == "age"].iloc[0]
        assert row["missing_count"] == 1

    def test_status_warning_at_10pct(self):
        # 1/10 = 10% missing -> Warning
        df = pl.DataFrame({"v": [1, 2, 3, 4, 5, 6, 7, 8, 9, None]})
        result = compute_missing_rate(df, ["v"])
        assert result.iloc[0]["status"] == "Warning"

    def test_status_ok_no_missing(self):
        df = pl.DataFrame({"v": [1, 2, 3, 4, 5]})
        result = compute_missing_rate(df, ["v"])
        assert result.iloc[0]["status"] == "OK"

    def test_status_critical_above_20pct(self):
        df = pl.DataFrame({"v": [1, None, None, None, None, None, 2, 3, 4, 5]})
        result = compute_missing_rate(df, ["v"])
        assert result.iloc[0]["status"] == "Critical"

    def test_empty_df_returns_empty(self, empty_df):
        result = compute_missing_rate(empty_df, ["age"])
        assert result.empty

    def test_empty_col_list_returns_empty(self, sample_df):
        result = compute_missing_rate(sample_df, [])
        assert result.empty


# =============================================================================
# compute_correlation_matrix
# =============================================================================


class TestComputeCorrelationMatrix:
    """Tests for compute_correlation_matrix."""

    def test_returns_dataframe(self, sample_df):
        result = compute_correlation_matrix(sample_df, ["age", "income"])
        assert isinstance(result, pd.DataFrame)

    def test_square_matrix(self, sample_df):
        cols = ["age", "income"]
        result = compute_correlation_matrix(sample_df, cols)
        assert result.shape == (len(cols), len(cols))

    def test_diagonal_is_one(self):
        df = pl.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]})
        result = compute_correlation_matrix(df, ["a", "b"])
        assert result.loc["a", "a"] == pytest.approx(1.0)
        assert result.loc["b", "b"] == pytest.approx(1.0)

    def test_perfectly_correlated(self):
        df = pl.DataFrame({"a": [1.0, 2.0, 3.0, 4.0], "b": [2.0, 4.0, 6.0, 8.0]})
        result = compute_correlation_matrix(df, ["a", "b"])
        assert result.loc["a", "b"] == pytest.approx(1.0)

    def test_too_few_columns_returns_empty(self, sample_df):
        result = compute_correlation_matrix(sample_df, ["age"])
        assert result.empty

    def test_empty_df_returns_empty(self, empty_df):
        result = compute_correlation_matrix(empty_df, ["age", "income"])
        assert result.empty

    def test_values_between_minus1_and_1(self, sample_df):
        result = compute_correlation_matrix(sample_df, ["age", "income"])
        for val in result.values.flatten():
            if not np.isnan(val):
                assert -1.0 <= val <= 1.0


# =============================================================================
# descriptive_report - pandas input compatibility
# =============================================================================


class TestDescriptiveReportInputCompat:
    """Verify compute functions work with pandas input from output_view_template."""

    def test_accepts_pandas_dataframe(self, sample_df):
        """Computation functions work correctly after pandas-to-polars conversion."""
        pandas_df = sample_df.to_pandas()
        columns = get_df_columns(pandas_df)
        result = compute_summary_stats(
            pl.from_pandas(pandas_df), columns.numeric_columns
        )
        assert not result.empty

    def test_pandas_and_polars_summary_stats_equivalent(self, sample_df):
        """Summary stats from polars and from converted pandas input match."""
        pandas_df = sample_df.to_pandas()
        result_polars = compute_summary_stats(sample_df, ["age"])
        result_pandas = compute_summary_stats(pl.from_pandas(pandas_df), ["age"])
        assert result_polars["mean"].iloc[0] == pytest.approx(
            result_pandas["mean"].iloc[0], rel=1e-6
        )
