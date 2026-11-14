"""Tests for descriptive statistics computation functions."""

import importlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pandas as pd
import plotly.graph_objects as go
import polars as pl
import pytest

from datasure.checks.descriptive import (
    _add_distribution_vlines,
    _build_shape_caption,
    _col_stats,
    _create_new_column_selection_df,
    _empty_col_stats,
    _get_column_type_label,
    _missing_pct,
    compute_histogram_data,
    compute_summary_stats,
    compute_value_counts,
    get_column_selection_df,
    save_column_selection,
)
from datasure.models.schemas import ColumnByType
from datasure.utils.dataframe_utils import get_df_columns
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.view_state import ViewState

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


@pytest.fixture
def sample_columns(sample_df) -> ColumnByType:
    """ColumnByType derived from sample_df."""
    return get_df_columns(sample_df)


@pytest.fixture
def mixed_type_df() -> pl.DataFrame:
    """DataFrame with datetime, numeric, categorical, string, and other columns."""
    return pl.DataFrame(
        {
            "num_col": [1.0, 2.0, 3.0],
            "cat_col": ["a", "b", "c"],
            "date_col": pl.Series(
                ["2021-01-01", "2021-01-02", "2021-01-03"]
            ).str.to_date(),
            "str_col": ["x", "y", "z"],
            "bool_col": [True, False, True],
        }
    )


@pytest.fixture
def mixed_columns() -> ColumnByType:
    """ColumnByType matching mixed_type_df."""
    return ColumnByType(
        all_columns=["num_col", "cat_col", "date_col", "str_col", "bool_col"],
        datetime_columns=["date_col"],
        numeric_columns=["num_col"],
        categorical_columns=["cat_col"],
        string_columns=["str_col"],
    )


@pytest.fixture
def fake_session(monkeypatch):
    """A fresh Streamlit session for widgets bound to saved view state."""
    fake_st = SimpleNamespace(session_state={})
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    return fake_st.session_state


@pytest.fixture
def settings_file(tmp_path):
    return tmp_path / "page_hfcs_settings.json"


@pytest.fixture(scope="module")
def descriptive_mod():
    """Reimport descriptive module with mocked streamlit.

    Makes @st.fragment a passthrough decorator so rendering functions
    can be called directly in tests.
    """
    orig_desc = sys.modules.pop("datasure.checks.descriptive", None)
    orig_st = sys.modules.get("streamlit")

    st_mock = MagicMock()
    st_mock.fragment = lambda f: f
    st_mock.column_config = MagicMock()
    # data_editor returns its first positional argument (the DataFrame)
    st_mock.data_editor.side_effect = lambda *a, **kw: a[0]
    st_mock.button.return_value = False
    st_mock.pills.return_value = None

    sys.modules["streamlit"] = st_mock
    try:
        mod = importlib.import_module("datasure.checks.descriptive")
        sys.modules.pop("datasure.checks.descriptive", None)
    finally:
        if orig_st is not None:
            sys.modules["streamlit"] = orig_st
        else:
            sys.modules.pop("streamlit", None)
        if orig_desc is not None:
            sys.modules["datasure.checks.descriptive"] = orig_desc

    return mod


# =============================================================================
# _missing_pct
# =============================================================================


class TestMissingPct:
    """Tests for _missing_pct helper."""

    def test_basic_percentage(self):
        assert _missing_pct(1, 10) == pytest.approx(10.0)

    def test_zero_missing(self):
        assert _missing_pct(0, 10) == pytest.approx(0.0)

    def test_all_missing(self):
        assert _missing_pct(5, 5) == pytest.approx(100.0)

    def test_zero_total_returns_zero(self):
        assert _missing_pct(0, 0) == pytest.approx(0.0)

    def test_rounds_to_one_decimal(self):
        # 1/3 ≈ 33.333... → 33.3
        assert _missing_pct(1, 3) == pytest.approx(33.3)


# =============================================================================
# _empty_col_stats
# =============================================================================


class TestEmptyColStats:
    """Tests for _empty_col_stats helper."""

    def test_returns_dict(self):
        result = _empty_col_stats("x", 3, 10)
        assert isinstance(result, dict)

    def test_column_name(self):
        result = _empty_col_stats("age", 2, 10)
        assert result["column"] == "age"

    def test_count_is_zero(self):
        result = _empty_col_stats("x", 3, 10)
        assert result["count"] == 0

    def test_missing_count(self):
        result = _empty_col_stats("x", 3, 10)
        assert result["missing"] == 3

    def test_missing_pct(self):
        result = _empty_col_stats("x", 2, 10)
        assert result["missing_pct"] == pytest.approx(20.0)

    def test_stats_are_none(self):
        result = _empty_col_stats("x", 0, 5)
        for key in (
            "mean",
            "median",
            "std",
            "min",
            "max",
            "q1",
            "q3",
            "skewness",
            "kurtosis",
        ):
            assert result[key] is None

    def test_zero_total_missing_pct(self):
        result = _empty_col_stats("x", 0, 0)
        assert result["missing_pct"] == pytest.approx(0.0)


# =============================================================================
# _col_stats
# =============================================================================


class TestColStats:
    """Tests for _col_stats helper."""

    @pytest.fixture
    def simple_series(self) -> pl.Series:
        return pl.Series([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])

    def test_returns_dict(self, simple_series):
        result = _col_stats("v", simple_series, 0, 8)
        assert isinstance(result, dict)

    def test_column_name(self, simple_series):
        result = _col_stats("v", simple_series, 0, 8)
        assert result["column"] == "v"

    def test_count_matches_series_length(self, simple_series):
        result = _col_stats("v", simple_series, 0, 8)
        assert result["count"] == len(simple_series)

    def test_min_max(self, simple_series):
        result = _col_stats("v", simple_series, 0, 8)
        assert result["min"] == pytest.approx(1.0)
        assert result["max"] == pytest.approx(8.0)

    def test_q1_le_median_le_q3(self, simple_series):
        result = _col_stats("v", simple_series, 0, 8)
        assert result["q1"] <= result["median"] <= result["q3"]

    def test_skewness_none_for_two_values(self):
        s = pl.Series([1.0, 2.0])
        result = _col_stats("v", s, 0, 2)
        assert result["skewness"] is None

    def test_kurtosis_none_for_three_values(self):
        s = pl.Series([1.0, 2.0, 3.0])
        result = _col_stats("v", s, 0, 3)
        assert result["kurtosis"] is None

    def test_skewness_present_with_three_values(self):
        s = pl.Series([1.0, 2.0, 3.0])
        result = _col_stats("v", s, 0, 3)
        assert result["skewness"] is not None

    def test_skewness_present_with_enough_values(self, simple_series):
        result = _col_stats("v", simple_series, 0, 8)
        assert result["skewness"] is not None

    def test_kurtosis_present_with_enough_values(self, simple_series):
        result = _col_stats("v", simple_series, 0, 8)
        assert result["kurtosis"] is not None

    def test_missing_pct_calculated(self, simple_series):
        result = _col_stats("v", simple_series, 2, 10)
        assert result["missing_pct"] == pytest.approx(20.0)

    def test_rounded_to_four_decimals(self, simple_series):
        result = _col_stats("v", simple_series, 0, 8)
        # mean of 1..8 = 4.5, exactly representable
        assert result["mean"] == pytest.approx(4.5)


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
        }
        assert expected_cols.issubset(set(result.columns))

    def test_no_outliers_column(self, sample_df):
        result = compute_summary_stats(sample_df, ["age"])
        assert "outliers" not in result.columns

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

    def test_missing_codes_are_not_values(
        self, land_area_data, land_area_missing_codes
    ):
        """Issue #379: -99 and -88 count as missing, not in the mean or minimum."""
        result = compute_summary_stats(
            land_area_data, ["land_area"], missing_codes=land_area_missing_codes
        )
        row = result.iloc[0]
        assert row["count"] == 9
        assert row["missing"] == 3
        assert row["mean"] == pytest.approx(10.5)
        assert row["min"] == pytest.approx(2.0)


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

    def test_default_n_bins_is_20(self, sample_df):
        result = compute_histogram_data(sample_df, "age")
        assert len(result) == 20

    def test_missing_codes_are_not_binned(
        self, land_area_data, land_area_missing_codes
    ):
        """Issue #379: the histogram starts at 2, not at the -99 code."""
        result = compute_histogram_data(
            land_area_data, "land_area", missing_codes=land_area_missing_codes
        )
        assert result["count"].sum() == 9
        assert result["bin_start"].min() == pytest.approx(2.0)


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

    def test_pct_sums_close_to_100_all_rows(self, sample_df):
        result = compute_value_counts(sample_df, "region", top_n=100)
        # with nulls included, pct sum should be <= 100
        assert result["pct"].sum() <= 100.0 + 1e-6

    def test_numeric_column_value_counts(self, sample_df):
        result = compute_value_counts(sample_df, "age")
        assert isinstance(result, pd.DataFrame)
        assert not result.empty


# =============================================================================
# _build_shape_caption
# =============================================================================


class TestBuildShapeCaption:
    """Tests for _build_shape_caption helper."""

    def test_empty_series_returns_empty_string(self):
        s = pl.Series([], dtype=pl.Float64)
        assert _build_shape_caption(s) == ""

    def test_too_few_values_returns_empty_string(self):
        s = pl.Series([1.0, 2.0])
        assert _build_shape_caption(s) == ""

    def test_three_values_has_skewness_only(self):
        s = pl.Series([1.0, 2.0, 3.0])
        caption = _build_shape_caption(s)
        assert "Skewness" in caption
        assert "Kurtosis" not in caption

    def test_four_plus_values_has_both(self):
        s = pl.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        caption = _build_shape_caption(s)
        assert "Skewness" in caption
        assert "Kurtosis" in caption

    def test_values_separated_by_dot(self):
        s = pl.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        caption = _build_shape_caption(s)
        assert "·" in caption

    def test_one_value_returns_empty_string(self):
        s = pl.Series([5.0])
        assert _build_shape_caption(s) == ""


# =============================================================================
# _get_column_type_label
# =============================================================================


class TestGetColumnTypeLabel:
    """Tests for _get_column_type_label helper."""

    @pytest.fixture
    def columns(self) -> ColumnByType:
        return ColumnByType(
            all_columns=["date_col", "num_col", "cat_col", "str_col"],
            datetime_columns=["date_col"],
            numeric_columns=["num_col"],
            categorical_columns=["cat_col"],
            string_columns=["str_col"],
        )

    def test_datetime_label(self, columns):
        assert _get_column_type_label("date_col", columns) == "datetime"

    def test_numeric_label(self, columns):
        assert _get_column_type_label("num_col", columns) == "numeric"

    def test_categorical_label(self, columns):
        assert _get_column_type_label("cat_col", columns) == "categorical"

    def test_string_label(self, columns):
        assert _get_column_type_label("str_col", columns) == "string"

    def test_unknown_column_returns_other(self, columns):
        assert _get_column_type_label("unknown_col", columns) == "other"

    def test_datetime_takes_priority_over_numeric(self):
        """A column in both datetime and numeric lists → datetime wins."""
        cols = ColumnByType(
            all_columns=["col"],
            datetime_columns=["col"],
            numeric_columns=["col"],
        )
        assert _get_column_type_label("col", cols) == "datetime"


# =============================================================================
# _create_new_column_selection_df
# =============================================================================


class TestCreateNewColumnSelectionDf:
    """Tests for _create_new_column_selection_df helper."""

    def test_returns_polars_dataframe(self, sample_df, sample_columns):
        result = _create_new_column_selection_df(sample_df, sample_columns)
        assert isinstance(result, pl.DataFrame)

    def test_has_required_columns(self, sample_df, sample_columns):
        result = _create_new_column_selection_df(sample_df, sample_columns)
        assert set(result.columns) == {"Selected", "column", "type"}

    def test_one_row_per_dataframe_column(self, sample_df, sample_columns):
        result = _create_new_column_selection_df(sample_df, sample_columns)
        assert len(result) == len(sample_df.columns)

    def test_all_selected_false_by_default(self, sample_df, sample_columns):
        result = _create_new_column_selection_df(sample_df, sample_columns)
        assert result["Selected"].to_list() == [False] * len(sample_df.columns)

    def test_type_labels_are_valid(self, sample_df, sample_columns):
        result = _create_new_column_selection_df(sample_df, sample_columns)
        valid_types = {"numeric", "categorical", "datetime", "string", "other"}
        assert set(result["type"].to_list()).issubset(valid_types)

    def test_column_names_match_dataframe(self, sample_df, sample_columns):
        result = _create_new_column_selection_df(sample_df, sample_columns)
        assert result["column"].to_list() == sample_df.columns

    def test_datetime_type_label(self, mixed_type_df, mixed_columns):
        result = _create_new_column_selection_df(mixed_type_df, mixed_columns)
        row = result.filter(pl.col("column") == "date_col")
        assert row["type"][0] == "datetime"

    def test_string_type_label(self, mixed_type_df, mixed_columns):
        result = _create_new_column_selection_df(mixed_type_df, mixed_columns)
        row = result.filter(pl.col("column") == "str_col")
        assert row["type"][0] == "string"

    def test_other_type_label(self, mixed_type_df, mixed_columns):
        result = _create_new_column_selection_df(mixed_type_df, mixed_columns)
        row = result.filter(pl.col("column") == "bool_col")
        assert row["type"][0] == "other"

    def test_numeric_type_label(self, mixed_type_df, mixed_columns):
        result = _create_new_column_selection_df(mixed_type_df, mixed_columns)
        row = result.filter(pl.col("column") == "num_col")
        assert row["type"][0] == "numeric"

    def test_categorical_type_label(self, mixed_type_df, mixed_columns):
        result = _create_new_column_selection_df(mixed_type_df, mixed_columns)
        row = result.filter(pl.col("column") == "cat_col")
        assert row["type"][0] == "categorical"


# =============================================================================
# Column selection: saved per page in the logs database
# =============================================================================

PROJECT_ID = "descproj01"


@pytest.fixture
def cache_dir(tmp_path):
    """Point every DuckDB database at a temporary cache directory."""

    def fake_cache_path(*parts):
        path = tmp_path.joinpath(*map(str, parts))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    with patch("datasure.utils.duckdb_utils.get_cache_path", fake_cache_path):
        yield tmp_path


def _selected(selection: pl.DataFrame) -> set[str]:
    return set(selection.filter(pl.col("Selected").cast(pl.Boolean))["column"])


def _with_selected(selection: pl.DataFrame, columns: set[str]) -> pl.DataFrame:
    return selection.with_columns(
        pl.col("column").is_in(list(columns)).alias("Selected")
    )


@pytest.mark.usefixtures("cache_dir")
class TestColumnSelectionPerPage:
    """The descriptive column selection is saved per page."""

    def test_new_page_starts_with_nothing_selected(self, sample_df, sample_columns):
        selection = get_column_selection_df(
            PROJECT_ID, "page_a", sample_df, sample_columns
        )

        assert selection["column"].to_list() == sample_df.columns
        assert _selected(selection) == set()

    def test_saved_selection_is_returned_for_the_page(self, sample_df, sample_columns):
        selection = get_column_selection_df(
            PROJECT_ID, "page_a", sample_df, sample_columns
        )
        save_column_selection(
            PROJECT_ID, "page_a", _with_selected(selection, {"age", "region"})
        )

        reloaded = get_column_selection_df(
            PROJECT_ID, "page_a", sample_df, sample_columns
        )

        assert _selected(reloaded) == {"age", "region"}

    def test_two_pages_keep_independent_selections(self, sample_df, sample_columns):
        base = get_column_selection_df(PROJECT_ID, "page_a", sample_df, sample_columns)
        save_column_selection(PROJECT_ID, "page_a", _with_selected(base, {"age"}))
        save_column_selection(PROJECT_ID, "page_b", _with_selected(base, {"gender"}))

        page_a = get_column_selection_df(
            PROJECT_ID, "page_a", sample_df, sample_columns
        )
        page_b = get_column_selection_df(
            PROJECT_ID, "page_b", sample_df, sample_columns
        )

        assert _selected(page_a) == {"age"}
        assert _selected(page_b) == {"gender"}


@pytest.mark.usefixtures("cache_dir")
class TestColumnSelectionMigration:
    """Projects saved before per-page selections seed each page once."""

    LEGACY = pl.DataFrame(
        {
            "Selected": [True, True, False, True],
            "column": ["age", "region", "income", "other_page_col"],
            "type": ["numeric", "categorical", "numeric", "numeric"],
        }
    )

    def _save_legacy(self, selection: pl.DataFrame | None = None) -> None:
        duckdb_save_table(
            PROJECT_ID,
            self.LEGACY if selection is None else selection,
            "selected_columns_df",
            "intermediate",
        )

    def test_page_without_a_selection_carries_over_the_legacy_selection(
        self, sample_df, sample_columns
    ):
        self._save_legacy()

        selection = get_column_selection_df(
            PROJECT_ID, "page_a", sample_df, sample_columns
        )

        assert selection["column"].to_list() == sample_df.columns
        assert _selected(selection) == {"age", "region"}

    def test_each_page_keeps_only_its_own_columns(self, sample_columns, sample_df):
        self._save_legacy()
        other_data = pl.DataFrame({"other_page_col": [1, 2], "gender": ["M", "F"]})

        page_a = get_column_selection_df(
            PROJECT_ID, "page_a", sample_df, sample_columns
        )
        page_b = get_column_selection_df(
            PROJECT_ID, "page_b", other_data, get_df_columns(other_data)
        )

        assert _selected(page_a) == {"age", "region"}
        assert _selected(page_b) == {"other_page_col"}

    def test_seeded_selection_is_saved_for_the_page(self, sample_df, sample_columns):
        self._save_legacy()
        get_column_selection_df(PROJECT_ID, "page_a", sample_df, sample_columns)
        # The legacy table changing later does not reseed the page.
        self._save_legacy(self.LEGACY.with_columns(pl.lit(False).alias("Selected")))

        selection = get_column_selection_df(
            PROJECT_ID, "page_a", sample_df, sample_columns
        )

        assert _selected(selection) == {"age", "region"}

    def test_page_with_its_own_selection_ignores_the_legacy_selection(
        self, sample_df, sample_columns
    ):
        self._save_legacy()
        cleared = _create_new_column_selection_df(sample_df, sample_columns)
        save_column_selection(PROJECT_ID, "page_a", cleared)

        selection = get_column_selection_df(
            PROJECT_ID, "page_a", sample_df, sample_columns
        )

        assert _selected(selection) == set()

    def test_legacy_table_is_left_in_place(self, sample_df, sample_columns):
        self._save_legacy()

        get_column_selection_df(PROJECT_ID, "page_a", sample_df, sample_columns)

        assert duckdb_get_table(
            PROJECT_ID, "selected_columns_df", "intermediate"
        ).equals(self.LEGACY)


# =============================================================================
# _add_distribution_vlines
# =============================================================================


class TestAddDistributionVlines:
    """Tests for _add_distribution_vlines helper."""

    def test_adds_two_shapes_for_valid_series(self):
        fig = go.Figure()
        s = pl.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        _add_distribution_vlines(fig, s)
        assert len(fig.layout.shapes) == 2

    def test_no_shapes_for_empty_series(self):
        fig = go.Figure()
        s = pl.Series([], dtype=pl.Float64)
        _add_distribution_vlines(fig, s)
        assert len(fig.layout.shapes) == 0

    def test_mean_annotation_present(self):
        fig = go.Figure()
        s = pl.Series([2.0, 4.0, 6.0])
        _add_distribution_vlines(fig, s)
        texts = [a.text for a in fig.layout.annotations if a.text]
        assert any("mean" in t for t in texts)

    def test_median_annotation_present(self):
        fig = go.Figure()
        s = pl.Series([2.0, 4.0, 6.0])
        _add_distribution_vlines(fig, s)
        texts = [a.text for a in fig.layout.annotations if a.text]
        assert any("median" in t for t in texts)

    def test_single_value_adds_shapes(self):
        fig = go.Figure()
        s = pl.Series([3.0])
        _add_distribution_vlines(fig, s)
        # mean and median both equal 3.0, so two shapes added
        assert len(fig.layout.shapes) == 2


# =============================================================================
# pandas input compatibility
# =============================================================================


class TestDescriptiveReportInputCompat:
    """Verify compute functions work with pandas input from output_view_template."""

    def test_accepts_pandas_dataframe(self, sample_df):
        pandas_df = sample_df.to_pandas()
        columns = get_df_columns(pandas_df)
        result = compute_summary_stats(
            pl.from_pandas(pandas_df), columns.numeric_columns
        )
        assert not result.empty

    def test_pandas_and_polars_summary_stats_equivalent(self, sample_df):
        pandas_df = sample_df.to_pandas()
        result_polars = compute_summary_stats(sample_df, ["age"])
        result_pandas = compute_summary_stats(pl.from_pandas(pandas_df), ["age"])
        assert result_polars["mean"].iloc[0] == pytest.approx(
            result_pandas["mean"].iloc[0], rel=1e-6
        )


# =============================================================================
# Rendering functions - require mocked streamlit (descriptive_mod fixture)
# =============================================================================


class TestRenderSummaryStats:
    """Tests for _render_summary_stats via mocked streamlit module."""

    def test_no_numeric_cols_calls_info(self, descriptive_mod, sample_df):
        mod = descriptive_mod
        mod.st.reset_mock()
        mod._render_summary_stats(sample_df, [])
        mod.st.info.assert_called_once()

    def test_valid_cols_calls_dataframe(self, descriptive_mod, sample_df):
        mod = descriptive_mod
        mod.st.reset_mock()
        mod._render_summary_stats(sample_df, ["age", "income"])
        mod.st.dataframe.assert_called_once()

    def test_empty_stats_calls_info(self, descriptive_mod, sample_df):
        """When compute_summary_stats returns empty, st.info is called."""
        mod = descriptive_mod
        mod.st.reset_mock()
        with patch.object(mod, "compute_summary_stats", return_value=pd.DataFrame()):
            mod._render_summary_stats(sample_df, ["age"])
        mod.st.info.assert_called_once()


class TestRenderColumnSelector:
    """Tests for _render_column_selector via mocked streamlit module."""

    @pytest.fixture
    def sel_df(self, sample_df, sample_columns) -> pl.DataFrame:
        return _create_new_column_selection_df(sample_df, sample_columns)

    def test_returns_column_by_type(
        self, descriptive_mod, sample_df, sample_columns, sel_df
    ):
        mod = descriptive_mod
        mod.st.reset_mock()
        mod.st.pills.return_value = None
        mod.st.button.return_value = False
        result = mod._render_column_selector("proj1", "page1", sel_df)
        assert isinstance(result, mod.ColumnByType)

    def test_select_all_marks_all_selected(
        self, descriptive_mod, sample_df, sample_columns, sel_df
    ):
        mod = descriptive_mod
        mod.st.reset_mock()
        # First pills call → "select_all", second pills call (type selector) → []
        mod.st.pills.side_effect = ["select_all", []]
        mod.st.button.return_value = False
        # Capture what data_editor receives
        received = {}

        def capture_editor(df, **kw):
            received["df"] = df
            return df

        mod.st.data_editor.side_effect = capture_editor
        mod._render_column_selector("proj1", "page1", sel_df)
        assert received["df"]["Selected"].to_list() == [True] * len(sample_df.columns)

    def test_clear_all_marks_none_selected(
        self, descriptive_mod, sample_df, sample_columns, sel_df
    ):
        mod = descriptive_mod
        mod.st.reset_mock()
        mod.st.pills.side_effect = ["clear_all", []]
        mod.st.button.return_value = False
        received = {}

        def capture_editor(df, **kw):
            received["df"] = df
            # Streamlit CheckboxColumn always returns Boolean; cast to match
            return df.with_columns(pl.col("Selected").cast(pl.Boolean))

        mod.st.data_editor.side_effect = capture_editor
        mod._render_column_selector("proj1", "page1", sel_df)
        # all Selected should be False
        assert all(not v for v in received["df"]["Selected"].to_list())

    def test_select_by_type_filters_correctly(
        self, descriptive_mod, sample_df, sample_columns, sel_df
    ):
        mod = descriptive_mod
        mod.st.reset_mock()
        mod.st.pills.side_effect = ["select_by_type", ["numeric"]]
        mod.st.button.return_value = False
        received = {}

        def capture_editor(df, **kw):
            received["df"] = df
            return df

        mod.st.data_editor.side_effect = capture_editor
        mod._render_column_selector("proj1", "page1", sel_df)
        # Only numeric columns should be selected
        for row in received["df"].iter_rows(named=True):
            if row["type"] == "numeric":
                assert row["Selected"] is True
            else:
                assert row["Selected"] is False or row["Selected"] == 0

    def test_select_by_type_no_types_leaves_unchanged(
        self, descriptive_mod, sample_df, sample_columns, sel_df
    ):
        """select_by_type with empty type list → no columns changed."""
        mod = descriptive_mod
        mod.st.reset_mock()
        mod.st.pills.side_effect = ["select_by_type", []]
        mod.st.button.return_value = False
        received = {}

        def capture_editor(df, **kw):
            received["df"] = df
            return df

        mod.st.data_editor.side_effect = capture_editor
        mod._render_column_selector("proj1", "page1", sel_df)
        # No columns should be selected since no types were chosen
        assert all(not v for v in received["df"]["Selected"].to_list())

    def test_apply_button_saves_the_page_selection(
        self, descriptive_mod, sample_df, sample_columns, sel_df
    ):
        mod = descriptive_mod
        mod.st.reset_mock()
        mod.st.pills.side_effect = None  # clear any leftover side_effect
        mod.st.pills.return_value = None
        mod.st.button.return_value = True  # Apply clicked
        mod.st.data_editor.side_effect = lambda *a, **kw: a[0]
        with patch.object(mod, "save_column_selection") as mock_save:
            mod._render_column_selector("proj1", "page1", sel_df)
            mock_save.assert_called_once()
        project_id, page_name_id, saved = mock_save.call_args.args
        assert (project_id, page_name_id) == ("proj1", "page1")
        assert saved.equals(sel_df)


@pytest.mark.usefixtures("fake_session")
class TestRenderHistogram:
    """Tests for _render_histogram via mocked streamlit module."""

    def test_no_numeric_cols_calls_info(self, descriptive_mod, sample_df):
        mod = descriptive_mod
        mod.st.reset_mock()
        mod._render_histogram(sample_df, [], "settings.json")
        mod.st.info.assert_called_once()

    def test_valid_cols_calls_plotly_chart(self, descriptive_mod, sample_df):
        mod = descriptive_mod
        mod.st.reset_mock()
        col_mock, mid_mock, bins_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "age"
        bins_mock.slider.return_value = 10
        mod.st.columns.return_value = [col_mock, mid_mock, bins_mock]
        mod._render_histogram(sample_df, ["age", "income"], "settings.json")
        mod.st.plotly_chart.assert_called_once()

    def test_saved_view_state_restores_the_choices(
        self, descriptive_mod, sample_df, settings_file, fake_session
    ):
        """Saved column and bins come back in a new session."""
        mod = descriptive_mod
        mod.st.reset_mock()
        col_mock, mid_mock, bins_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "income"
        bins_mock.slider.return_value = 15
        mod.st.columns.return_value = [col_mock, mid_mock, bins_mock]
        view = ViewState(settings_file, "descriptive")
        view.save("desc_hist_col", "income")
        view.save("desc_hist_bins", 15)

        mod._render_histogram(sample_df, ["age", "income"], str(settings_file))

        assert fake_session["desc_hist_col"] == "income"
        assert fake_session["desc_hist_bins"] == 15
        assert "index" not in col_mock.selectbox.call_args.kwargs

    def test_choices_saved_by_older_versions_move_to_view_state(
        self, descriptive_mod, sample_df, settings_file, fake_session
    ):
        """Old saves load as before but leave the check's exported settings."""
        mod = descriptive_mod
        mod.st.reset_mock()
        col_mock, mid_mock, bins_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "income"
        bins_mock.slider.return_value = 15
        mod.st.columns.return_value = [col_mock, mid_mock, bins_mock]
        settings_file.write_text(
            json.dumps({"descriptive_stats": {"col_to_plot": "income", "n_bins": 15}})
        )

        mod._render_histogram(sample_df, ["age", "income"], str(settings_file))

        assert fake_session["desc_hist_col"] == "income"
        assert json.loads(settings_file.read_text())["descriptive_stats"] == {}

    def test_all_null_column_calls_info(self, descriptive_mod, all_null_df):
        mod = descriptive_mod
        mod.st.reset_mock()
        col_mock, mid_mock, bins_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "x"
        bins_mock.slider.return_value = 10
        mod.st.columns.return_value = [col_mock, mid_mock, bins_mock]
        null_df = pl.DataFrame({"x": pl.Series([None, None], dtype=pl.Float64)})
        mod._render_histogram(null_df, ["x"], "settings.json")
        mod.st.info.assert_called()

    def test_caption_shown_for_large_series(self, descriptive_mod, sample_df):
        mod = descriptive_mod
        mod.st.reset_mock()
        col_mock, mid_mock, bins_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "age"
        bins_mock.slider.return_value = 10
        mod.st.columns.return_value = [col_mock, mid_mock, bins_mock]
        mod._render_histogram(sample_df, ["age"], "settings.json")
        mod.st.caption.assert_called_once()

    def test_no_vlines_when_series_empty_after_histogram(self, descriptive_mod):
        """Histogram data non-empty but series is all-null → skip vlines/caption."""
        mod = descriptive_mod
        mod.st.reset_mock()
        col_mock, mid_mock, bins_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "age"
        bins_mock.slider.return_value = 10
        mod.st.columns.return_value = [col_mock, mid_mock, bins_mock]
        fake_hist = pd.DataFrame({"bin_start": [0.0], "bin_end": [1.0], "count": [1]})
        null_df = pl.DataFrame({"age": pl.Series([None, None], dtype=pl.Float64)})
        with (
            patch.object(mod, "compute_histogram_data", return_value=fake_hist),
        ):
            mod._render_histogram(null_df, ["age"], "settings.json")
        # chart rendered even without vlines
        mod.st.plotly_chart.assert_called_once()
        mod.st.caption.assert_not_called()

    def test_no_caption_for_two_value_series(self, descriptive_mod):
        """Series with exactly 2 values: histogram shown but no caption (n < 3)."""
        mod = descriptive_mod
        mod.st.reset_mock()
        col_mock, mid_mock, bins_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "num"
        bins_mock.slider.return_value = 5
        mod.st.columns.return_value = [col_mock, mid_mock, bins_mock]
        two_val_df = pl.DataFrame({"num": [1.0, 2.0, None, None, None]})
        mod._render_histogram(two_val_df, ["num"], "settings.json")
        mod.st.caption.assert_not_called()

    def test_saved_col_not_in_list_defaults_to_index_0(
        self, descriptive_mod, sample_df, settings_file
    ):
        """A saved column that is gone falls back to the first and is removed."""
        mod = descriptive_mod
        mod.st.reset_mock()
        col_mock, mid_mock, bins_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "age"
        bins_mock.slider.return_value = 20
        mod.st.columns.return_value = [col_mock, mid_mock, bins_mock]
        ViewState(settings_file, "descriptive").save("desc_hist_col", "removed")

        mod._render_histogram(sample_df, ["age", "income"], str(settings_file))

        assert col_mock.selectbox.call_args.kwargs.get("index") == 0
        assert ViewState(settings_file, "descriptive").values() == {}


@pytest.mark.usefixtures("fake_session")
class TestRenderValueCounts:
    """Tests for _render_value_counts via mocked streamlit module."""

    def test_no_columns_calls_info(self, descriptive_mod, sample_df):
        mod = descriptive_mod
        mod.st.reset_mock()
        mod._render_value_counts(sample_df, [], "settings.json")
        mod.st.info.assert_called_once()

    def test_table_view_calls_dataframe(self, descriptive_mod, sample_df):
        mod = descriptive_mod
        mod.st.reset_mock()
        mod.st.pills.side_effect = None
        col_mock, mid_mock, topn_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "region"
        topn_mock.slider.return_value = 10
        mod.st.columns.return_value = [col_mock, mid_mock, topn_mock]
        mod.st.pills.return_value = "table"
        mod._render_value_counts(sample_df, ["region", "gender"], "settings.json")
        mod.st.dataframe.assert_called_once()

    def test_chart_view_count_agg_calls_plotly_chart(self, descriptive_mod, sample_df):
        """Chart view with 'count' aggregation renders a plotly chart."""
        mod = descriptive_mod
        mod.st.reset_mock()
        mod.st.pills.side_effect = None
        col_mock, mid_mock, topn_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "region"
        topn_mock.slider.return_value = 10
        mod.st.columns.return_value = [col_mock, mid_mock, topn_mock]
        # First pills = view selector → "chart", second pills = agg → "count"
        mod.st.pills.side_effect = ["chart", "count"]
        mod._render_value_counts(sample_df, ["region", "gender"], "settings.json")
        mod.st.plotly_chart.assert_called_once()

    def test_chart_view_pct_agg_calls_plotly_chart(self, descriptive_mod, sample_df):
        """Chart view with 'pct' aggregation renders a plotly chart."""
        mod = descriptive_mod
        mod.st.reset_mock()
        col_mock, mid_mock, topn_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "region"
        topn_mock.slider.return_value = 10
        mod.st.columns.return_value = [col_mock, mid_mock, topn_mock]
        # First pills = "chart", second pills = "pct"
        mod.st.pills.side_effect = ["chart", "pct"]
        mod._render_value_counts(sample_df, ["region", "gender"], "settings.json")
        mod.st.plotly_chart.assert_called_once()

    def test_empty_value_counts_calls_info(self, descriptive_mod, sample_df):
        mod = descriptive_mod
        mod.st.reset_mock()
        col_mock, mid_mock, topn_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "region"
        topn_mock.slider.return_value = 10
        mod.st.columns.return_value = [col_mock, mid_mock, topn_mock]
        with (
            patch.object(mod, "compute_value_counts", return_value=pd.DataFrame()),
        ):
            mod._render_value_counts(sample_df, ["region"], "settings.json")
        mod.st.info.assert_called()

    def test_saved_view_state_restores_the_choices(
        self, descriptive_mod, sample_df, settings_file, fake_session
    ):
        mod = descriptive_mod
        mod.st.reset_mock()
        mod.st.pills.side_effect = None
        col_mock, mid_mock, topn_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "gender"
        topn_mock.slider.return_value = 30
        mod.st.columns.return_value = [col_mock, mid_mock, topn_mock]
        mod.st.pills.return_value = "table"
        view = ViewState(settings_file, "descriptive")
        view.save("desc_vc_col", "gender")
        view.save("desc_vc_topn", 30)
        view.save("desc_vc_view_pills", "chart")

        mod._render_value_counts(sample_df, ["region", "gender"], str(settings_file))

        assert fake_session["desc_vc_col"] == "gender"
        assert fake_session["desc_vc_topn"] == 30
        assert fake_session["desc_vc_view_pills"] == "chart"

    def test_saved_col_not_in_list_defaults_to_index_0(
        self, descriptive_mod, sample_df, settings_file
    ):
        """Saved col_to_analyse not in list → index defaults to 0."""
        mod = descriptive_mod
        mod.st.reset_mock()
        mod.st.pills.side_effect = None
        col_mock, mid_mock, topn_mock = MagicMock(), MagicMock(), MagicMock()
        col_mock.selectbox.return_value = "region"
        topn_mock.slider.return_value = 20
        mod.st.columns.return_value = [col_mock, mid_mock, topn_mock]
        mod.st.pills.return_value = "table"
        ViewState(settings_file, "descriptive").save("desc_vc_col", "removed")

        mod._render_value_counts(sample_df, ["region", "gender"], str(settings_file))

        assert col_mock.selectbox.call_args.kwargs.get("index") == 0
        assert ViewState(settings_file, "descriptive").values() == {}


class TestDescriptiveReport:
    """Tests for the public descriptive_report entry point."""

    @pytest.fixture
    def sel_df(self, sample_df, sample_columns) -> pl.DataFrame:
        df = _create_new_column_selection_df(sample_df, sample_columns)
        # Pre-select numeric columns
        return df.with_columns(
            pl.when(pl.col("type") == "numeric")
            .then(True)
            .otherwise(False)
            .alias("Selected")
        )

    def test_empty_data_calls_warning(self, descriptive_mod):
        mod = descriptive_mod
        mod.st.reset_mock()
        empty = pl.DataFrame()
        cols = ColumnByType(all_columns=[])
        mod.descriptive_report("proj1", "page1", empty, "settings.json", cols)
        mod.st.warning.assert_called_once()

    def test_no_columns_selected_calls_info(
        self, descriptive_mod, sample_df, sample_columns
    ):
        mod = descriptive_mod
        mod.st.reset_mock()
        # Column selector returns no selected columns
        empty_cols = mod.ColumnByType(all_columns=[], numeric_columns=[])
        with (
            patch.object(
                mod,
                "get_column_selection_df",
                return_value=pl.DataFrame(
                    {
                        "Selected": [False, False, False, False],
                        "column": sample_df.columns,
                        "type": ["numeric", "numeric", "categorical", "categorical"],
                    }
                ),
            ),
            patch.object(mod, "_render_column_selector", return_value=empty_cols),
        ):
            mod.descriptive_report(
                "proj1", "page1", sample_df, "settings.json", sample_columns
            )
        mod.st.info.assert_called()

    def test_full_report_rendered_with_selections(
        self, descriptive_mod, sample_df, sample_columns, sel_df
    ):
        mod = descriptive_mod
        mod.st.reset_mock()
        selected_cols = mod.ColumnByType(
            all_columns=["age", "income"],
            numeric_columns=["age", "income"],
        )
        with (
            patch.object(mod, "get_column_selection_df", return_value=sel_df),
            patch.object(mod, "_render_column_selector", return_value=selected_cols),
            patch.object(
                mod, "load_missing_codes_from_db", return_value=pl.DataFrame()
            ),
            patch.object(mod, "_render_summary_stats"),
            patch.object(mod, "_render_histogram"),
            patch.object(mod, "_render_value_counts"),
        ):
            mod.descriptive_report(
                "proj1", "page1", sample_df, "settings.json", sample_columns
            )
        mod.st.title.assert_called_once()
        mod.st.subheader.assert_called()
