"""Tests for the summary module."""

import datetime

import numpy as np
import pandas as pd
import pytest

from datasure.checks import (
    compute_summary_progress,
    compute_summary_progress_by_col,
    compute_summary_submissions,
)

### TEST: compute_summary_submissions


# test 1: Test structure of returned value from compute_summary_submissions
def test_compute_summary_submissions_structure(sample_date_data_10000):
    """Test the compute_summary_submissions function"""
    # Load test data
    test_data_10000 = sample_date_data_10000
    test_data_1000 = test_data_10000.sample(n=1000, random_state=42)
    test_data_10 = test_data_10000.sample(n=10, random_state=42)
    test_data_0 = test_data_10000.sample(n=0, random_state=42)

    ### test for 0, 10, 1000, and 10000 observations
    # Compute summary for 0 observations
    summary_0 = compute_summary_submissions(test_data_0, "SubmissionDate")
    assert isinstance(summary_0, tuple), (
        "0 ROWS: Returned value for compute_summary_submissions should be a tuple"
    )
    assert len(summary_0) == 10, (
        "0 ROWS: Returned value for compute_summary_submissions should have 10 elements"
    )

    # Compute summary for 10 observations
    summary_10 = compute_summary_submissions(test_data_10, "SubmissionDate")
    assert isinstance(summary_10, tuple), (
        "10 ROWS: Returned value for compute_summary_submissions should be a tuple"
    )
    assert len(summary_10) == 10, (
        "10 ROWS: Returned value for compute_summary_submissions should have 10 elements"
    )

    # Compute summary for 1000 observations
    summary_1000 = compute_summary_submissions(test_data_1000, "SubmissionDate")
    assert isinstance(summary_1000, tuple), (
        "1000 ROWS: Returned value for compute_summary_submissions should be a tuple"
    )
    assert len(summary_1000) == 10, (
        "1000 ROWS: Returned value for compute_summary_submissions should have 10 elements"
    )

    # Compute summary for 10000 observations
    summary_10000 = compute_summary_submissions(test_data_10000, "SubmissionDate")
    assert isinstance(summary_10000, tuple), (
        "10000 ROWS: Returned value for compute_summary_submissions should be a tuple"
    )
    assert len(summary_10000) == 10, (
        "10000 ROWS: Returned value for compute_summary_submissions should have 10 elements"
    )


# Test 2: type of returned values
@pytest.mark.parametrize(
    "name, index, type",
    [
        ("first_date", 0, datetime.date),
        ("last_date", 1, datetime.date),
        ("submissions_today", 2, int),
        ("submissions_this_week", 3, int),
        ("submissions_this_month", 4, int),
        ("submissions_total", 5, (int, np.int64)),
        ("submissions_today_delta", 6, (int, float)),
        ("submissions_this_week_delta", 7, (int, float)),
        ("submissions_this_month_delta", 8, (int, float)),
        ("submissions_by_date", 9, pd.DataFrame),
    ],
)
def test_compute_summary_submissions_type(sample_date_data_10000, name, index, type):
    """Test the compute_summary_submissions function for specific values."""
    # Load test data
    test_data = sample_date_data_10000

    # Compute summary
    summary = compute_summary_submissions(test_data, "SubmissionDate")

    # Check if the value is of the expected type
    assert isinstance(summary[index], type), (
        f"Value at index {name} should be of type {type.__name__}"
    )


def test_compute_submissions_with_missing_dates(sample_date_data_10000):
    """Test the compute_summary_submissions function when dataset has some
    missing dates.
    """
    # Randomly sample 10000 observations
    test_data = sample_date_data_10000.sample(n=10000, random_state=42)
    # Introduce some missing dates
    test_data.loc[
        test_data.sample(frac=0.1, random_state=42).index, "SubmissionDate"
    ] = pd.NaT

    # Compute summary
    summary = compute_summary_submissions(test_data, "SubmissionDate")

    # Check basic structure
    assert isinstance(summary, tuple)
    assert len(summary) == 10


# test 3: values of return values with empty input dataset
@pytest.mark.parametrize(
    "name, index, result",
    [
        ("first_date", 0, None),
        ("last_date", 1, None),
        ("submissions_today", 2, 0),
        ("submissions_this_week", 3, 0),
        ("submissions_this_month", 4, 0),
        ("submissions_total", 5, 0),
        ("submissions_today_delta", 6, 0),
        ("submissions_this_week_delta", 7, 0),
        ("submissions_this_month_delta", 8, 0),
        ("submissions_by_date", 9, pd.DataFrame.empty),
    ],
)
def test_compute_submissions_values_0(name, index, result):
    """Test the compute_summary_submissions function for specific values with
    empty input.
    """
    # Compute summary
    test_data_empty = pd.DataFrame(columns=["SubmissionDate", "enum_id"])
    summary = compute_summary_submissions(test_data_empty, "SubmissionDate")

    # Check if the value is of the expected type
    if index == 9:
        # For submissions_by_date, we expect an empty DataFrame
        assert summary[index].empty, (
            f"Value at index {name} should be an empty DataFrame"
        )
    else:
        assert summary[index] == result, f"Value at index {name} should be {result}"


@pytest.mark.parametrize("size", [10, 1000, 10000])
# test 5: values of return values with 10
def test_compute_submissions_values_10(sample_date_data_10000, size):
    """Test the compute_summary_submissions function for specific values with 10
    observations.
    """
    # randomly sample based on size
    test_data = sample_date_data_10000.sample(n=size, random_state=42)

    # Compute summary
    summary = compute_summary_submissions(test_data, "SubmissionDate")

    # Check if the values are as expected
    test_data["SubmissionDate"] = test_data["SubmissionDate"].dt.date
    assert summary[0] == test_data["SubmissionDate"].min()
    assert summary[1] == test_data["SubmissionDate"].max()
    test_submissions_today = test_data[
        test_data["SubmissionDate"] == datetime.date.today()
    ]["SubmissionDate"].count()
    assert summary[2] == test_submissions_today
    test_submissions_this_week = test_data[
        (
            test_data["SubmissionDate"]
            >= datetime.date.today() - datetime.timedelta(days=7)
        )
        & (test_data["SubmissionDate"] <= datetime.date.today())
    ]["SubmissionDate"].count()
    assert summary[3] == test_submissions_this_week
    test_submissions_this_month = test_data[
        (
            test_data["SubmissionDate"]
            >= (pd.Timestamp.now().normalize() - pd.DateOffset(months=1)).date()
        )
        & (test_data["SubmissionDate"] <= datetime.date.today())
    ]["SubmissionDate"].count()
    assert summary[4] == test_submissions_this_month
    assert summary[5] == len(test_data)
    test_submissions_yesterday = test_data[
        test_data["SubmissionDate"]
        == (datetime.date.today() - datetime.timedelta(days=1))
    ]["SubmissionDate"].count()
    test_submissions_today_delta = (
        (test_submissions_today - test_submissions_yesterday)
        / test_submissions_yesterday
        if test_submissions_yesterday > 0
        else 0
    )
    assert summary[6] == test_submissions_today_delta * 100
    lastweek_start_date = (
        pd.Timestamp.now().normalize() - pd.DateOffset(weeks=2)
    ).date()
    lastweek_end_date = (pd.Timestamp.now().normalize() - pd.DateOffset(weeks=1)).date()
    test_submissions_last_week = test_data[
        (test_data["SubmissionDate"] >= lastweek_start_date)
        & (test_data["SubmissionDate"] < lastweek_end_date)
    ]["SubmissionDate"].count()
    test_submissions_this_week_delta = (
        (test_submissions_this_week - test_submissions_last_week)
        / test_submissions_last_week
        if test_submissions_last_week > 0
        else 0
    )
    assert summary[7] == test_submissions_this_week_delta * 100
    lastmonth_start_date = (
        pd.Timestamp.now().normalize() - pd.DateOffset(months=2)
    ).date()
    lastmonth_end_date = (
        pd.Timestamp.now().normalize() - pd.DateOffset(months=1)
    ).date()
    test_submissions_last_month = test_data[
        (test_data["SubmissionDate"] >= lastmonth_start_date)
        & (test_data["SubmissionDate"] < lastmonth_end_date)
    ]["SubmissionDate"].count()
    test_submissions_this_month_delta = (
        (test_submissions_this_month - test_submissions_last_month)
        / test_submissions_last_month
        if test_submissions_last_month > 0
        else 0
    )
    assert summary[8] == test_submissions_this_month_delta * 100
    assert isinstance(summary[9], pd.DataFrame), (
        "submissions_by_date should be a DataFrame"
    )
    assert not summary[9].empty, "submissions_by_date should not be empty"


### TEST: compute_summary_progress


# test 1: Test structure of returned value from compute_summary_progress
@pytest.mark.parametrize("target", [None, 0, 10, 9999, 10000, 10001])
def test_compute_summary_progress_structure(sample_date_data_10000, target):
    """Test the compute_summary_progress function"""
    # Randomly sample based on size
    test_data = sample_date_data_10000

    summary_progress = compute_summary_progress(
        data=test_data,
        date="SubmissionDate",
        target=target,
    )

    # Check if the returned value is a tuple
    assert isinstance(summary_progress, tuple)

    # Check if return value us a tuple of 4 elements
    assert len(summary_progress) == 4

    # check if elements of the tuple are of expected types (ie int, float)
    assert isinstance(summary_progress[0], int | float)
    assert isinstance(summary_progress[1], int | float)
    assert isinstance(summary_progress[2], int | float)
    assert isinstance(summary_progress[3], int | float)


# test 2: Test values of returned value from compute_summary_progress
@pytest.mark.parametrize("target", [0, 10, 9999, 10000, 10001])
def test_compute_summary_progress_values(sample_date_data_10000, target):
    """Test the compute_summary_progress function for specific values."""
    # Randomly sample based on size
    test_data = sample_date_data_10000

    summary_progress = compute_summary_progress(
        data=test_data,
        date="SubmissionDate",
        target=target,
    )

    # check progress
    test_progress = len(test_data) / target * 100 if target > 0 else 0
    assert summary_progress[0] == test_progress

    # check average submissions per day
    test_data["day"] = test_data["SubmissionDate"].dt.date
    test_avg_submissions_per_day = (
        test_data["day"].value_counts().mean() if not test_data["day"].empty else 0
    )
    assert summary_progress[1] == test_avg_submissions_per_day

    # check average submissions per week
    test_data["week"] = test_data["SubmissionDate"].dt.to_period("W").dt.to_timestamp()
    test_avg_submissions_per_week = (
        test_data["week"].value_counts().mean() if not test_data["week"].empty else 0
    )
    assert summary_progress[2] == test_avg_submissions_per_week

    # check average submissions per month
    test_data["month"] = test_data["SubmissionDate"].dt.to_period("M").dt.to_timestamp()
    test_avg_submissions_per_month = (
        test_data["month"].value_counts().mean() if not test_data["month"].empty else 0
    )
    assert summary_progress[3] == test_avg_submissions_per_month


# test 3: Test values of returned value from compute_summary_progress with empty input
@pytest.mark.parametrize("target", [0, 10001])
def test_compute_summary_progress_values_empty(target):
    """Test the compute_summary_progress function for specific values with
    empty input.
    """
    # Create an empty DataFrame
    test_data_empty = pd.DataFrame(columns=["SubmissionDate", "enum_id"])

    summary_progress = compute_summary_progress(
        data=test_data_empty,
        date="SubmissionDate",
        target=target,
    )

    # Check if the values are as expected
    assert summary_progress[0] == 0
    assert summary_progress[1] == 0
    assert summary_progress[2] == 0
    assert summary_progress[3] == 0


# test 4: Test values of returned value from compute_summary_progress with
# invalid target
@pytest.mark.parametrize("target", [-1, -100, "A"])
def test_compute_summary_progress_invalid_target(sample_date_data_10000, target):
    """Test the compute_summary_progress function for specific values with
    invalid target.
    """
    # Randomly sample based on size
    test_data = sample_date_data_10000

    with pytest.raises(ValueError):
        compute_summary_progress(
            data=test_data,
            date="SubmissionDate",
            target=target,
        )


### TEST: compute_summary_progress_by_col
# test 1: Test structure of returned value from compute_summary_progress_by_col
def test_compute_summary_progress_by_col(sample_date_data_10000):
    """Test the compute_summary_progress_by_col function"""
    # Randomly sample based on size
    test_data = sample_date_data_10000

    # add district column to the test data
    test_data["district"] = (
        pd.Series(["District A", "District B", "District C", "District D"])
        .sample(n=len(test_data), replace=True, random_state=42)
        .values
    )

    summary_progress_by_col = compute_summary_progress_by_col(
        data=test_data,
        date="SubmissionDate",
        progress_by_col="district",
        progress_time_period="Auto",
    )

    # check that the returned value is a tuple of 4 elements
    assert isinstance(summary_progress_by_col, tuple)
    assert len(summary_progress_by_col) == 4

    # Check if the returned value is a DataFrame
    assert isinstance(summary_progress_by_col[0], pd.DataFrame)
    assert isinstance(summary_progress_by_col[1], int | np.int64 | float | np.float64)
    assert isinstance(summary_progress_by_col[2], int | np.int64 | float | np.float64)
    assert isinstance(summary_progress_by_col[3], list)


# test 2: Test values of returned value from compute_summary_progress_by_col
@pytest.mark.parametrize("time_period", ["daily", "weekly", "monthly"])
def test_compute_summary_progress_by_col_values(sample_date_data_10000, time_period):
    """Test the compute_summary_progress_by_col function for specific values."""
    # Randomly sample based on size
    test_data = sample_date_data_10000

    # add district column to the test data
    test_data["district"] = (
        pd.Series(["District A", "District B", "District C", "District D"])
        .sample(n=len(test_data), replace=True, random_state=42)
        .values
    )

    summary_progress_by_col = compute_summary_progress_by_col(
        data=test_data,
        date="SubmissionDate",
        progress_by_col="district",
        progress_time_period=time_period,
    )

    # check that the number of rows in progress_by_col DataFrame is equal to
    # the number of unique values in the progress_by_col column
    assert len(summary_progress_by_col[0]) == test_data["district"].nunique()
