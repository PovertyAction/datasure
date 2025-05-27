import json
import os
import tempfile
import unittest

import numpy as np
import pandas as pd

from src.checks import missing


class TestMissing(unittest.TestCase):
    """Unit tests for validating the core functionality of the Missing Data Page."""

    def setUp(self):
        """Set up test data and configurations."""
        self.sample_settings_dict = {
            "Missing Labels": [
                "Don't Know",
                "Refuse to Answer",
                "Not Applicable",
            ],
            "Missing Codes": ["-999, .999", "-888, .888", "-777, .777"],
        }
        self.sample_settings_df = pd.DataFrame(self.sample_settings_dict)
        self.df_no_missing = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
        self.df_some_missing = pd.DataFrame({"A": [1, np.nan, 3], "B": [np.nan, 5, 6]})
        self.df_all_missing = pd.DataFrame(
            {"A": [np.nan, np.nan, np.nan], "B": [np.nan, np.nan, np.nan]}
        )

    def test_load_missing_settings_file_found(self):
        """Test loading missing settings when the file exists."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp:
            json.dump(self.sample_settings_dict, tmp)
            tmp_path = tmp.name
        try:
            df = missing.load_missing_settings(tmp_path)
            pd.testing.assert_frame_equal(df, self.sample_settings_df)
        finally:
            os.remove(tmp_path)

    def test_load_missing_settings_file_not_found(self):
        """Test loading missing settings when the file does not exist."""
        df = missing.load_missing_settings("non_existent_file.json")
        self.assertIn("Missing Labels", df.columns)
        self.assertIn("Missing Codes", df.columns)
        self.assertEqual(len(df), 3)
        self.assertTrue(df.isin(self.sample_settings_df).all().all())

    def test_load_missing_settings_malformed_file(self):
        """Test loading missing settings from a malformed JSON file."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp:
            tmp.write("not a json")
            tmp_path = tmp.name
        try:
            df = missing.load_missing_settings(tmp_path)
            self.assertIn("Missing Labels", df.columns)
            self.assertIn("Missing Codes", df.columns)
        finally:
            os.remove(tmp_path)

    def test_save_and_load_missing_settings(self):
        """Test saving and loading missing settings."""
        with tempfile.NamedTemporaryFile(mode="w+", delete=False) as tmp:
            tmp_path = tmp.name
        try:
            missing.save_missing_settings(self.sample_settings_df, tmp_path)
            df_loaded = missing.load_missing_settings(tmp_path)
            pd.testing.assert_frame_equal(df_loaded, self.sample_settings_df)
        finally:
            os.remove(tmp_path)

    def test_compute_missing_summary(self):
        """Test the compute_missing_summary function."""
        mv, all_mv, any_mv, no_mv = missing.compute_missing_summary(self.df_no_missing)
        self.assertTrue((mv == 0).all())
        self.assertTrue((all_mv == 0).all())
        self.assertTrue((any_mv == 0).all())
        self.assertTrue((no_mv == 100).all())
        mv, all_mv, any_mv, no_mv = missing.compute_missing_summary(
            self.df_some_missing
        )
        self.assertAlmostEqual(mv["A"], 1 / 3 * 100)
        self.assertAlmostEqual(mv["B"], 1 / 3 * 100)
        self.assertTrue((all_mv == 0).all())
        self.assertTrue((any_mv == 100).all())
        self.assertTrue((no_mv == 0).all())
        mv, all_mv, any_mv, no_mv = missing.compute_missing_summary(self.df_all_missing)
        self.assertTrue((mv == 100).all())
        self.assertTrue((all_mv == 100).all())
        self.assertTrue((any_mv == 100).all())
        self.assertTrue((no_mv == 0).all())

    def test_compute_missing_columns(self):
        """Test the compute_missing_columns function."""
        missing_codes = pd.DataFrame(
            {"Missing Labels": ["CustomMissing"], "Missing Codes": ["-999"]}
        )
        df = pd.DataFrame({"A": [1, -999, 3], "B": [np.nan, 2, 3]})
        mv_data = missing.compute_missing_columns(df, missing_codes)
        self.assertIn("Null Values", mv_data.columns)
        self.assertIn("% Null Values", mv_data.columns)
        self.assertIn("CustomMissing", mv_data.columns)
        self.assertIn("% CustomMissing", mv_data.columns)
        self.assertEqual(mv_data.shape[0], 2)

    def test_compute_filtered_missing_columns(self):
        """Test the compute_filtered_missing_columns function."""
        df = pd.DataFrame(
            {
                "Column": ["A", "B"],
                "Null Values": [1, 2],
                "% Null Values": [50, 100],
                "% CustomMissing": [0, 100],
            }
        )
        mv_data_filtered, perc_cols, vmin, vmax = (
            missing.compute_filtered_missing_columns(df, mv_threshold=60)
        )
        self.assertEqual(mv_data_filtered.shape[0], 1)
        self.assertIn("% Null Values", perc_cols)
        self.assertIn("% CustomMissing", perc_cols)
        self.assertEqual(vmin, 100)
        self.assertEqual(vmax, 100)

    def test_compute_filtered_missing_columns_all_match(self):
        """Test the compute_filtered_missing_columns function with all matches."""
        df = pd.DataFrame(
            {
                "Column": ["A", "B"],
                "Null Values": [2, 2],
                "% Null Values": [100, 100],
                "% CustomMissing": [100, 100],
            }
        )
        mv_data_filtered, perc_cols, vmin, vmax = (
            missing.compute_filtered_missing_columns(df, mv_threshold=0)
        )
        self.assertEqual(mv_data_filtered.shape[0], 2)
        self.assertEqual(vmin, 100)
        self.assertEqual(vmax, 100)

    def test_compute_filtered_missing_columns_no_match(self):
        """Test the compute_filtered_missing_columns function with no matches."""
        df = pd.DataFrame(
            {
                "Column": ["A", "B"],
                "Null Values": [0, 0],
                "% Null Values": [0, 0],
                "% CustomMissing": [0, 0],
            }
        )
        mv_data_filtered, perc_cols, vmin, vmax = (
            missing.compute_filtered_missing_columns(df, mv_threshold=50)
        )
        self.assertEqual(mv_data_filtered.shape[0], 0)
        self.assertTrue(isinstance(perc_cols, list))

    def test_compute_missing_over_time(self):
        """Test the compute_missing_over_time function."""
        dates = pd.date_range("2023-01-01", periods=3)
        df = pd.DataFrame({"date": dates, "A": [1, np.nan, 3], "B": [np.nan, 2, 3]})
        df["date"] = pd.to_datetime(df["date"])
        result = missing.compute_missing_over_time(df, "date")
        self.assertIn("missingness_trend_date", result.columns)
        self.assertIn("missingness_rate", result.columns)
        self.assertEqual(len(result), 3)

    def test_compute_missing_compare(self):
        """Test the compute_missing_compare function."""
        df = pd.DataFrame(
            {"group": ["x", "x", "y", "y"], "val": [1, np.nan, 2, np.nan]}
        )
        group_by_data, vmin, vmax = missing.compute_missing_compare(df, "group", "val")
        self.assertIn("values (count)", group_by_data.columns)
        self.assertIn("values (%)", group_by_data.columns)
        self.assertIn("val", group_by_data.columns)
        self.assertTrue(isinstance(vmin, float))
        self.assertTrue(isinstance(vmax, float))

    def test_compute_missing_compare_no_missing(self):
        """Test the compute_missing_compare function with no missing values."""
        df = pd.DataFrame({"group": ["x", "x", "y", "y"], "val": [1, 2, 3, 4]})
        group_by_data, vmin, vmax = missing.compute_missing_compare(df, "group", "val")
        self.assertTrue((group_by_data["val"] == 0).all())

    def test_compute_missing_correlation(self):
        """Test the compute_missing_correlation function."""
        df = pd.DataFrame(
            {
                "A": [1, np.nan, 3, np.nan],
                "B": [np.nan, 2, np.nan, 4],
                "C": [1, 2, 3, 4],
            }
        )
        null_cols = ["A", "B"]
        corr = missing.compute_missing_correlation(df, null_cols)
        self.assertEqual(corr.shape, (2, 2))
        self.assertTrue(
            np.isnan(np.diag(corr)).all() or (corr.values.diagonal() == 1).all()
        )

    def test_compute_missing_correlation_single_col(self):
        """Test the compute_missing_correlation function with a single column."""
        df = pd.DataFrame({"A": [1, np.nan, 3, np.nan]})
        null_cols = ["A"]
        corr = missing.compute_missing_correlation(df, null_cols)
        self.assertEqual(corr.shape, (1, 1))

    def test_get_null_list(self):
        """Test the get_null_list function."""
        df = pd.DataFrame(
            {
                "A": [1, 2, 3],
                "B": [np.nan, 2, 3],
                "C": [np.nan, np.nan, np.nan],
            }
        )
        all_cols = missing.get_null_list(df, all_cols=True)
        self.assertEqual(set(all_cols), set(df.columns))
        null_cols = missing.get_null_list(df, all_cols=False)
        self.assertIn("B", null_cols)
        self.assertNotIn("C", null_cols)
        self.assertNotIn("A", null_cols)

    def test_get_null_list_no_nulls(self):
        """Test the get_null_list function with no nulls."""
        df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
        null_cols = missing.get_null_list(df, all_cols=False)
        self.assertEqual(null_cols, [])

    def test_get_null_list_all_null(self):
        """Test the get_null_list function with all nulls."""
        df = pd.DataFrame({"A": [np.nan, np.nan], "B": [np.nan, np.nan]})
        null_cols = missing.get_null_list(df, all_cols=False)
        self.assertEqual(null_cols, [])

    def test_compute_missing_matrix(self):
        """Test the compute_missing_matrix function."""
        df = pd.DataFrame({"A": [1, np.nan, 3], "B": [np.nan, 2, 3]})
        matrix = missing.compute_missing_matrix(df, sort_by_col=None)
        self.assertTrue((matrix.values == np.array([[0, 1], [1, 0], [0, 0]])).any())
        self.assertEqual(matrix.shape, df.shape)

    def test_compute_missing_matrix_sorted(self):
        """Test the compute_missing_matrix function with sorting."""
        df = pd.DataFrame({"A": [1, np.nan, 3], "B": [np.nan, 2, 3], "grp": [1, 2, 1]})
        matrix = missing.compute_missing_matrix(df, sort_by_col="grp")
        self.assertEqual(matrix.shape, (3, 3))


if __name__ == "__main__":
    unittest.main()
