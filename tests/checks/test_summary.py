"""Tests for the summary module."""

import datetime

import numpy as np
import pandas as pd
import pytest

from src.checks import (
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
    assert isinstance(
        summary_0, tuple
    ), "0 ROWS: Returned value for compute_summary_submissions should be a tuple"
    assert (
        len(summary_0) == 10
    ), "0 ROWS: Returned value for compute_summary_submissions should have 10 elements"

    # Compute summary for 10 observations
    summary_10 = compute_summary_submissions(test_data_10, "SubmissionDate")
    assert isinstance(
        summary_10, tuple
    ), "10 ROWS: Returned value for compute_summary_submissions should be a tuple"
    assert (
        len(summary_10) == 10
    ), "10 ROWS: Returned value for compute_summary_submissions should have 10 elements"

    # Compute summary for 1000 observations
    summary_1000 = compute_summary_submissions(test_data_1000, "SubmissionDate")
    assert isinstance(
        summary_1000, tuple
    ), "1000 ROWS: Returned value for compute_summary_submissions should be a tuple"
    assert (
        len(summary_1000) == 10
    ), "1000 ROWS: Returned value for compute_summary_submissions should have 10 elements"

    # Compute summary for 10000 observations
    summary_10000 = compute_summary_submissions(test_data_10000, "SubmissionDate")
    assert isinstance(
        summary_10000, tuple
    ), "10000 ROWS: Returned value for compute_summary_submissions should be a tuple"
    assert (
        len(summary_10000) == 10
    ), "10000 ROWS: Returned value for compute_summary_submissions should have 10 elements"


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
    assert isinstance(
        summary[index], type
    ), f"Value at index {name} should be of type {type.__name__}"


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
def test_compute_submissions_with_missing_dates(
    sample_date_data_10000, name, index, type
):
    """Test the compute_summary_submissions function for specific values when dataset
    has some missing dates.
    """
    # Randomly sample 10000 observations
    test_data = sample_date_data_10000.sample(n=10000, random_state=42)
    # Introduce some missing dates
    test_data.loc[
        test_data.sample(frac=0.1, random_state=42).index, "SubmissionDate"
    ] = pd.NaT

    # Compute summary
    summary = compute_summary_submissions(test_data, "SubmissionDate")

    # Check if the value is of the expected type
    assert isinstance(
        summary[index], type
    ), f"Value at index {name} should be of type {type.__name__}"


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
        assert summary[
            index
        ].empty, f"Value at index {name} should be an empty DataFrame"
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
            >= datetime.date.today() - datetime.timedelta(days=30)
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
    assert isinstance(
        summary[9], pd.DataFrame
    ), "submissions_by_date should be a DataFrame"
    assert not summary[9].empty, "submissions_by_date should not be empty"
