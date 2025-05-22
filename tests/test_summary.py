"""Tests for the summary module."""

import datetime
import unittest

import numpy as np
import pandas as pd

from src.checks import (
    compute_summary_progress,
    compute_summary_progress_by_col,
    compute_summary_submissions,
)


def create_summary_test_data():
    """Create a test dataset of 1000 observations for summary computation."""
    # Set random seeds for reproducibility
    seed = 42
    size = 1000

    # Generate datetime range
    start_date = pd.Timestamp("2025-04-01")
    end_date = pd.Timestamp("2025-05-15")

    # Generate random datetimes
    dates = pd.date_range(start=start_date, end=end_date, freq="h").to_list()
    dates = pd.Series(dates).sample(size, random_state=seed).dt.tz_localize(None)

    # Create enumerator data
    enum_ids = list(range(1, 11))  # 10 enumerators
    enum_names = [
        "John Smith",
        "Mary Johnson",
        "David Williams",
        "Patricia Brown",
        "Robert Jones",
        "Linda Davis",
        "Michael Miller",
        "Sarah Wilson",
        "James Taylor",
        "Jennifer Anderson",
    ]

    # Create the dataset
    data = {
        "SubmissionDate": dates,
        "enum_id": [
            pd.Series(enum_ids).sample(1, random_state=seed).values[0]
            for _ in range(size)
        ],
    }

    df = pd.DataFrame(data)

    # Add enum_name based on enum_id
    df["enum_name"] = df["enum_id"].map(dict(zip(enum_ids, enum_names, strict=False)))

    return df


class TestSummary(unittest.TestCase):  # noqa: D101
    def tearDown(self):
        """Clean up after each test method"""
        pass

    def test_compute_summary_submissions(self):
        """Test the compute_summary_submissions function"""
        # Load test data
        self.test_data = create_summary_test_data()

        # Compute summary
        (
            first_submission_date,
            last_submission_date,
            submissions_today,
            submissions_this_week,
            submissions_this_month,
            submissions_total,
            submissions_today_delta,
            submissions_this_week_delta,
            submissions_this_month_delta,
            submissions_by_date,
        ) = compute_summary_submissions(
            data=self.test_data,
            date="SubmissionDate",
        )

        # test 1: Returns a tuple of 10 elements
        self.assertEqual(
            len(
                (
                    first_submission_date,
                    last_submission_date,
                    submissions_today,
                    submissions_this_week,
                    submissions_this_month,
                    submissions_total,
                    submissions_today_delta,
                    submissions_this_week_delta,
                    submissions_this_month_delta,
                    submissions_by_date,
                )
            ),
            10,
        )

        # test 2: Check the type of each element in the tuple
        self.assertIsInstance(first_submission_date, datetime.date)
        self.assertIsInstance(last_submission_date, datetime.date)
        self.assertIsInstance(submissions_today, int)
        self.assertIsInstance(submissions_this_week, int)
        self.assertIsInstance(submissions_this_month, int)
        self.assertIsInstance(submissions_total, (int, np.int64))
        self.assertIsInstance(submissions_today_delta, (int))
        self.assertIsInstance(submissions_this_week_delta, (int, float))
        self.assertIsInstance(submissions_this_month_delta, (int, float))
        self.assertIsInstance(submissions_by_date, pd.DataFrame)

        # test 3: check the values of the tuple
        self.test_data = self.test_data["SubmissionDate"].dt.date
        self.assertEqual(
            first_submission_date,
            self.test_data.min(),
        )
        self.assertEqual(
            last_submission_date,
            self.test_data.max(),
        )
        self.assertEqual(
            submissions_today,
            self.test_data[self.test_data == datetime.date.today()].count(),
        )
        submissions_this_week_test = self.test_data[
            (self.test_data >= datetime.date.today() - datetime.timedelta(days=7))
            & (self.test_data <= datetime.date.today())
        ].count()
        self.assertEqual(
            submissions_this_week,
            submissions_this_week_test,
        )
        submissions_this_month_test = self.test_data[
            (self.test_data >= datetime.date.today() - datetime.timedelta(days=30))
            & (self.test_data <= datetime.date.today())
        ].count()
        self.assertEqual(
            submissions_this_month,
            submissions_this_month_test,
        )
        self.assertEqual(
            submissions_total,
            self.test_data.count(),
        )

        yesterdays_submissions = self.test_data[
            (self.test_data >= datetime.date.today() - datetime.timedelta(days=1))
            & (self.test_data <= datetime.date.today())
        ].count()
        self.assertEqual(
            submissions_today_delta,
            submissions_today - yesterdays_submissions,
        )
        lastweek_start_date = (
            pd.Timestamp.now().normalize() - pd.DateOffset(weeks=2)
        ).date()
        lastweek_end_date = (
            pd.Timestamp.now().normalize() - pd.DateOffset(weeks=1)
        ).date()
        submissions_last_week_test = self.test_data[
            (self.test_data >= lastweek_start_date)
            & (self.test_data < lastweek_end_date)
        ].count()
        self.assertEqual(
            submissions_this_week_delta,
            (
                (submissions_this_week_test - submissions_last_week_test)
                / submissions_last_week_test
            )
            * 100
            if submissions_last_week_test != 0
            else 0,
        )

        lastmonth_start_date = (
            pd.Timestamp.now().normalize() - pd.DateOffset(months=2)
        ).date()
        lastmonth_end_date = (
            pd.Timestamp.now().normalize() - pd.DateOffset(months=1)
        ).date()
        submissions_last_month_test = self.test_data[
            (self.test_data >= lastmonth_start_date)
            & (self.test_data < lastmonth_end_date)
        ].count()
        self.assertEqual(
            submissions_this_month_delta,
            (
                (submissions_this_month_test - submissions_last_month_test)
                / submissions_last_month_test
            )
            * 100
            if submissions_last_month_test != 0
            else 0,
        )

    # test 4: test with empty data
    def test_compute_summary_submissions_with_empty_data(self):
        """Test the compute_summary_submissions function with empty data"""
        empty_data = pd.DataFrame(
            {
                "SubmissionDate": [],
                "enum_id": [],
                "enum_name": [],
            }
        )
        (
            first_submission_date,
            last_submission_date,
            submissions_today,
            submissions_this_week,
            submissions_this_month,
            submissions_total,
            submissions_today_delta,
            submissions_this_week_delta,
            submissions_this_month_delta,
            submissions_by_date,
        ) = compute_summary_submissions(
            data=empty_data,
            date="SubmissionDate",
        )

        self.assertEqual(
            first_submission_date,
            None,
        )
        self.assertEqual(
            last_submission_date,
            None,
        )
        self.assertEqual(
            submissions_today,
            0,
        )
        self.assertEqual(
            submissions_this_week,
            0,
        )
        self.assertEqual(
            submissions_this_month,
            0,
        )
        self.assertEqual(
            submissions_total,
            0,
        )
        self.assertEqual(
            submissions_today_delta,
            0,
        )
        self.assertEqual(
            submissions_this_week_delta,
            0,
        )
        self.assertEqual(
            submissions_this_month_delta,
            0,
        )
        assert submissions_by_date.empty

    # test 5: test with non-empty data with missing date values
    def test_compute_summary_submissions_with_missing_dates(self):
        """Test the compute_summary_submissions function with missing date values"""
        # Load test data
        self.test_data = create_summary_test_data()

        # Introduce missing dates
        self.test_data.loc[
            self.test_data.sample(frac=0.1, random_state=42).index, "SubmissionDate"
        ] = pd.NaT

        # Compute summary
        (
            first_submission_date,
            last_submission_date,
            _,
            _,
            _,
            _,
            _,
            _,
            _,
            _,
        ) = compute_summary_submissions(
            data=self.test_data,
            date="SubmissionDate",
        )

        # Check that the function handles missing dates correctly
        self.assertIsInstance(first_submission_date, datetime.date)
        self.assertIsInstance(last_submission_date, datetime.date)

    def test_compute_summary_progress(self):
        """Test the compute_summary_progress function"""
        # load test data
        self.test_data = create_summary_test_data()

        (
            progress,
            average_submission_per_day,
            average_submission_per_week,
            average_submission_per_month,
        ) = compute_summary_progress(
            data=self.test_data,
            date="SubmissionDate",
            target=1000,
        )

        # test 1: Returns a tuple of 4 elements
        self.assertEqual(
            len(
                (
                    progress,
                    average_submission_per_day,
                    average_submission_per_week,
                    average_submission_per_month,
                )
            ),
            4,
        )

        # test 2: Check the type of each element in the tuple
        self.assertIsInstance(progress, (float, int))
        self.assertIsInstance(average_submission_per_day, (float, int))
        self.assertIsInstance(average_submission_per_week, (float, int))
        self.assertIsInstance(average_submission_per_month, (float, int))

        # test 3: check the values of the tuple
        self.assertEqual(
            progress,
            len(self.test_data) / 1000 * 100,
        )
        # create day column, calculate average submission per day and check the value
        self.test_data["day"] = (
            self.test_data["SubmissionDate"].dt.to_period("D").dt.to_timestamp()
        )
        average_submission_per_day_test = self.test_data.groupby("day").size().mean()
        self.assertEqual(
            average_submission_per_day,
            average_submission_per_day_test,
        )
        # create week column, calculate average submission per week and check the value
        self.test_data["week"] = (
            self.test_data["SubmissionDate"].dt.to_period("W").dt.to_timestamp()
        )
        average_submission_per_week_test = self.test_data.groupby("week").size().mean()
        self.assertEqual(
            average_submission_per_week,
            average_submission_per_week_test,
        )
        # create month column, calculate average submission per month and check the
        # value
        self.test_data["month"] = (
            self.test_data["SubmissionDate"].dt.to_period("M").dt.to_timestamp()
        )
        average_submission_per_month_test = (
            self.test_data.groupby("month").size().mean()
        )
        self.assertEqual(
            average_submission_per_month,
            average_submission_per_month_test,
        )

    # test 4: test with empty data
    def test_compute_summary_progress_with_empty_data(self):
        """Test the compute_summary_progress function with empty data"""
        empty_data = pd.DataFrame(
            {
                "SubmissionDate": [],
                "enum_id": [],
                "enum_name": [],
            }
        )
        (
            progress,
            average_submission_per_day,
            average_submission_per_week,
            average_submission_per_month,
        ) = compute_summary_progress(
            data=empty_data,
            date="SubmissionDate",
            target=1000,
        )

        self.assertEqual(
            progress,
            0,
        )
        self.assertEqual(
            average_submission_per_day,
            0,
        )
        self.assertEqual(
            average_submission_per_week,
            0,
        )
        self.assertEqual(
            average_submission_per_month,
            0,
        )

    # test 5: test with non-empty data with missing date values
    def test_compute_summary_progress_with_missing_dates(self):
        """Test the compute_summary_progress function with missing date values"""
        # Load test data
        self.test_data = create_summary_test_data()

        # Introduce missing dates
        self.test_data.loc[
            self.test_data.sample(frac=0.1, random_state=42).index, "SubmissionDate"
        ] = pd.NaT

        # Compute summary
        (
            progress,
            average_submission_per_day,
            average_submission_per_week,
            average_submission_per_month,
        ) = compute_summary_progress(
            data=self.test_data,
            date="SubmissionDate",
            target=1000,
        )

        # Check that the function handles missing dates correctly
        self.assertIsInstance(progress, (float, int))
        self.assertIsInstance(average_submission_per_day, (float, int))
        self.assertIsInstance(average_submission_per_week, (float, int))
        self.assertIsInstance(average_submission_per_month, (float, int))

    def test_compute_summary_progress_with_invalid_target(self):
        """Test the compute_summary_progress function with invalid target"""
        # Load test data
        self.test_data = create_summary_test_data()

        # Compute summary with invalid target
        with self.assertRaises(ValueError):
            compute_summary_progress(
                data=self.test_data,
                date="SubmissionDate",
                target=-1000,
            )
        # test with non-integer target
        with self.assertRaises(ValueError):
            compute_summary_progress(
                data=self.test_data,
                date="SubmissionDate",
                target=1000.5,
            )

        # test target of 0 and 2000
        progress_0, _, _, _ = compute_summary_progress(
            data=self.test_data,
            date="SubmissionDate",
            target=0,
        )
        self.assertEqual(
            progress_0,
            0,
        )
        progress_2000, _, _, _ = compute_summary_progress(
            data=self.test_data,
            date="SubmissionDate",
            target=2000,
        )
        self.assertEqual(
            progress_2000,
            len(self.test_data) / 2000 * 100,
        )

    def test_compute_summary_progress_by_col(self):
        """Test the compute_summary_progress_by_col function"""
        # Load test data
        self.test_data = create_summary_test_data()
        # add district column with 5 random districts
        districts = [
            "District A",
            "District B",
            "District C",
            "District D",
            "District E",
        ]
        self.test_data["district"] = [
            pd.Series(districts).sample(1, random_state=42).values[0]
            for _ in range(len(self.test_data))
        ]

        # Compute summary
        progress_data, vmin_val, vmax_val, format_cols = (
            compute_summary_progress_by_col(
                data=self.test_data,
                date="SubmissionDate",
                progress_by_col="district",
                progress_time_period="Auto",
            )
        )

        # test 1: Returns tuple of 4 elements
        self.assertEqual(
            len(
                (
                    progress_data,
                    vmin_val,
                    vmax_val,
                    format_cols,
                )
            ),
            4,
        )
        # test 2: Check the type of each element in the tuple
        self.assertIsInstance(progress_data, pd.DataFrame)
        self.assertIsInstance(vmin_val, (int, np.int64, float))
        self.assertIsInstance(vmax_val, (int, np.int64, float))
        self.assertIsInstance(format_cols, list)


if __name__ == "__main__":
    unittest.main()
