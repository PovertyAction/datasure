import json
import os
import tempfile

import numpy as np
import pandas as pd
import pytest

from src.checks.missing import (
    compute_filtered_missing_columns,
    compute_missing_columns,
    compute_missing_compare,
    compute_missing_correlation,
    compute_missing_matrix,
    compute_missing_over_time,
    compute_missing_summary,
    get_null_list,
    load_missing_settings,
    save_missing_settings,
)


@pytest.fixture
def sample_settings_dict():
    """Fixture that returns a sample settings dictionary for missing values tests."""
    return {
        "Missing Labels": [
            "Don't Know",
            "Refuse to Answer",
            "Not Applicable",
        ],
        "Missing Codes": ["-999, .999", "-888, .888", "-777, .777"],
    }


@pytest.fixture
def sample_settings_df(sample_settings_dict):
    """Fixture that returns a sample settings DataFrame for missing values tests."""
    return pd.DataFrame(sample_settings_dict)


@pytest.fixture
def df_no_missing():
    """Fixture that returns a DataFrame with no missing values."""
    return pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})


@pytest.fixture
def df_some_missing():
    """Fixture that returns a DataFrame with some missing values."""
    return pd.DataFrame({"A": [1, np.nan, 3], "B": [np.nan, 5, 6]})


@pytest.fixture
def df_all_missing():
    """Fixture that returns a DataFrame where all values are missing."""
    return pd.DataFrame({"A": [np.nan, np.nan, np.nan], "B": [np.nan, np.nan, np.nan]})


def test_load_missing_settings_file_found(sample_settings_dict, sample_settings_df):
    """
    Test that loading missing settings
    from a found file returns the correct DataFrame.
    """
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp:
        json.dump(sample_settings_dict, tmp)
        tmp_path = tmp.name
    try:
        df = load_missing_settings(tmp_path)
        pd.testing.assert_frame_equal(df, sample_settings_df)
    finally:
        os.remove(tmp_path)


def test_load_missing_settings_file_not_found(sample_settings_df):
    """Test that loading missing settings
    from a non-existent file returns the default DataFrame.
    """
    df = load_missing_settings("non_existent_file.json")
    assert "Missing Labels" in df.columns
    assert "Missing Codes" in df.columns
    assert len(df) == 3
    assert df.isin(sample_settings_df).all().all()


def test_load_missing_settings_malformed_file():
    """Test that loading a malformed settings file
    returns a DataFrame with expected columns.
    """
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp:
        tmp.write("not a json")
        tmp_path = tmp.name
    try:
        df = load_missing_settings(tmp_path)
        assert "Missing Labels" in df.columns
        assert "Missing Codes" in df.columns
    finally:
        os.remove(tmp_path)


def test_save_and_load_missing_settings(sample_settings_df):
    """Test saving and loading missing settings
    to ensure data integrity.
    """
    with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        save_missing_settings(sample_settings_df, tmp_path)
        df_loaded = load_missing_settings(tmp_path)
        pd.testing.assert_frame_equal(df_loaded, sample_settings_df)
    finally:
        os.remove(tmp_path)


def test_compute_missing_summary(df_no_missing, df_some_missing, df_all_missing):
    """Test compute_missing_summary with DataFrames having
    no, some, and all missing values.
    """
    mv, all_mv, any_mv, no_mv = compute_missing_summary(df_no_missing)
    assert (mv == 0).all()
    assert (all_mv == 0).all()
    assert (any_mv == 0).all()
    assert (no_mv == 100).all()

    mv, all_mv, any_mv, no_mv = compute_missing_summary(df_some_missing)
    assert np.isclose(mv["A"], 1 / 3 * 100)
    assert np.isclose(mv["B"], 1 / 3 * 100)
    assert (all_mv == 0).all()
    assert (any_mv == 100).all()
    assert (no_mv == 0).all()

    mv, all_mv, any_mv, no_mv = compute_missing_summary(df_all_missing)
    assert (mv == 100).all()
    assert (all_mv == 100).all()
    assert (any_mv == 100).all()
    assert (no_mv == 0).all()


def test_compute_missing_columns():
    """Test compute_missing_columns with a
    DataFrame containing custom missing codes.
    """
    missing_codes = pd.DataFrame(
        {"Missing Labels": ["CustomMissing"], "Missing Codes": ["-999"]}
    )
    df = pd.DataFrame({"A": [1, -999, 3], "B": [np.nan, 2, 3]})
    mv_data = compute_missing_columns(df, missing_codes)
    assert "Null Values" in mv_data.columns
    assert "% Null Values" in mv_data.columns
    assert "CustomMissing" in mv_data.columns
    assert "% CustomMissing" in mv_data.columns
    assert mv_data.shape[0] == 2


def test_compute_filtered_missing_columns():
    """Test compute_filtered_missing_columns
    filters columns based on missing value threshold.
    """
    df = pd.DataFrame(
        {
            "Column": ["A", "B"],
            "Null Values": [1, 2],
            "% Null Values": [50, 100],
            "% CustomMissing": [0, 100],
        }
    )
    mv_data_filtered, perc_cols, vmin, vmax = compute_filtered_missing_columns(
        df, mv_threshold=60
    )
    assert mv_data_filtered.shape[0] == 1
    assert "% Null Values" in perc_cols
    assert "% CustomMissing" in perc_cols
    assert vmin == 100
    assert vmax == 100


def test_compute_filtered_missing_columns_all_match():
    """Test compute_filtered_missing_columns
    when all columns match the threshold.
    """
    df = pd.DataFrame(
        {
            "Column": ["A", "B"],
            "Null Values": [2, 2],
            "% Null Values": [100, 100],
            "% CustomMissing": [100, 100],
        }
    )
    mv_data_filtered, perc_cols, vmin, vmax = compute_filtered_missing_columns(
        df, mv_threshold=0
    )
    assert mv_data_filtered.shape[0] == 2
    assert vmin == 100
    assert vmax == 100


def test_compute_filtered_missing_columns_no_match():
    """Test compute_filtered_missing_columns
    when no columns match the threshold.
    """
    df = pd.DataFrame(
        {
            "Column": ["A", "B"],
            "Null Values": [0, 0],
            "% Null Values": [0, 0],
            "% CustomMissing": [0, 0],
        }
    )
    mv_data_filtered, perc_cols, vmin, vmax = compute_filtered_missing_columns(
        df, mv_threshold=50
    )
    assert mv_data_filtered.shape[0] == 0
    assert isinstance(perc_cols, list)


def test_compute_missing_over_time():
    """
    Test compute_missing_over_time
    with a DataFrame containing missing values over time.
    """
    dates = pd.date_range("2023-01-01", periods=3)
    df = pd.DataFrame({"date": dates, "A": [1, np.nan, 3], "B": [np.nan, 2, 3]})
    df["date"] = pd.to_datetime(df["date"])
    result = compute_missing_over_time(df, "date")
    assert "missingness_trend_date" in result.columns
    assert "missingness_rate" in result.columns
    assert len(result) == 3


def test_compute_missing_compare():
    """Test compute_missing_compare
    with a DataFrame containing missing values in groups.
    """
    df = pd.DataFrame({"group": ["x", "x", "y", "y"], "val": [1, np.nan, 2, np.nan]})
    group_by_data, vmin, vmax = compute_missing_compare(df, "group", "val")
    assert "values (count)" in group_by_data.columns
    assert "values (%)" in group_by_data.columns
    assert "val" in group_by_data.columns
    assert isinstance(vmin, float)
    assert isinstance(vmax, float)


def test_compute_missing_compare_no_missing():
    """Test compute_missing_compare
    when there are no missing values in the DataFrame.
    """
    df = pd.DataFrame({"group": ["x", "x", "y", "y"], "val": [1, 2, 3, 4]})
    group_by_data, vmin, vmax = compute_missing_compare(df, "group", "val")
    assert (group_by_data["val"] == 0).all()


def test_compute_missing_correlation():
    """Test compute_missing_correlation
    with multiple columns containing missing values.
    """
    df = pd.DataFrame(
        {
            "A": [1, np.nan, 3, np.nan],
            "B": [np.nan, 2, np.nan, 4],
            "C": [1, 2, 3, 4],
        }
    )
    null_cols = ["A", "B"]
    corr = compute_missing_correlation(df, null_cols)
    assert corr.shape == (2, 2)
    assert np.isnan(np.diag(corr)).all() or (corr.values.diagonal() == 1).all()


def test_compute_missing_correlation_single_col():
    """Test compute_missing_correlation
    with a single column containing missing values.
    """
    df = pd.DataFrame({"A": [1, np.nan, 3, np.nan]})
    null_cols = ["A"]
    corr = compute_missing_correlation(df, null_cols)
    assert corr.shape == (1, 1)


def test_get_null_list():
    """Test get_null_list
    returns correct columns with and without nulls.
    """
    df = pd.DataFrame(
        {
            "A": [1, 2, 3],
            "B": [np.nan, 2, 3],
            "C": [np.nan, np.nan, np.nan],
        }
    )
    all_cols = get_null_list(df, all_cols=True)
    assert set(all_cols) == set(df.columns)
    null_cols = get_null_list(df, all_cols=False)
    assert "B" in null_cols
    assert "C" not in null_cols
    assert "A" not in null_cols


def test_get_null_list_no_nulls():
    """Test get_null_list
    returns an empty list when there are no nulls in the DataFrame.
    """
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    null_cols = get_null_list(df, all_cols=False)
    assert null_cols == []


def test_get_null_list_all_null():
    """Test get_null_list
    returns an empty list when all columns contain only null values.
    """
    df = pd.DataFrame({"A": [np.nan, np.nan], "B": [np.nan, np.nan]})
    null_cols = get_null_list(df, all_cols=False)
    assert null_cols == []


def test_compute_missing_matrix():
    """Test compute_missing_matrix
    with a DataFrame containing missing values.
    """
    df = pd.DataFrame({"A": [1, np.nan, 3], "B": [np.nan, 2, 3]})
    matrix = compute_missing_matrix(df, sort_by_col=None)
    assert (matrix.values == np.array([[0, 1], [1, 0], [0, 0]])).any()
    assert matrix.shape == df.shape


def test_compute_missing_matrix_sorted():
    """Test compute_missing_matrix with sorting by a column."""
    df = pd.DataFrame({"A": [1, np.nan, 3], "B": [np.nan, 2, 3], "grp": [1, 2, 1]})
    matrix = compute_missing_matrix(df, sort_by_col="grp")
    assert matrix.shape == (3, 3)


# Additional tests


def test_missing_columns_with_multiple_missing_codes():
    """Test compute_missing_columns
    with multiple missing codes and labels.
    """
    missing_codes = pd.DataFrame(
        {
            "Missing Labels": ["CustomMissing", "OtherMissing"],
            "Missing Codes": ["-999", "-888"],
        }
    )
    df = pd.DataFrame({"A": [1, -999, -888], "B": [np.nan, -888, 3]})
    mv_data = compute_missing_columns(df, missing_codes)
    assert "CustomMissing" in mv_data.columns
    assert "OtherMissing" in mv_data.columns
    assert "% CustomMissing" in mv_data.columns
    assert "% OtherMissing" in mv_data.columns


def test_missing_summary_all_columns_missing():
    """Test compute_missing_summary when all columns are"""
    df = pd.DataFrame({"A": [np.nan, np.nan], "B": [np.nan, np.nan]})
    mv, all_mv, any_mv, no_mv = compute_missing_summary(df)
    assert (mv == 100).all()
    assert (all_mv == 100).all()
    assert (any_mv == 100).all()
    assert (no_mv == 0).all()


def test_missing_compare_with_nan_group():
    """
    Test compute_missing_compare
    when the group column contains NaN values.
    """
    df = pd.DataFrame({"group": ["x", np.nan, "y", "y"], "val": [1, np.nan, 2, np.nan]})
    group_by_data, vmin, vmax = compute_missing_compare(df, "group", "val")
    assert "values (count)" in group_by_data.columns
    assert "val" in group_by_data.columns


def test_missing_matrix_with_no_missing():
    """Test compute_missing_matrix
    when there are no missing values in the DataFrame.
    """
    df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    matrix = compute_missing_matrix(df, sort_by_col=None)
    assert (matrix.values == 0).all()
    assert matrix.shape == df.shape
