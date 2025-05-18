"""Tests for the summary module."""

import datetime
import unittest

import pandas as pd

from src.checks import compute_summary_submissions


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
        self.assertIsInstance(submissions_total, int)
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


if __name__ == "__main__":
    unittest.main()
