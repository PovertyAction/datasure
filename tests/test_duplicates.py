"""Test the duplicates module."""

import unittest
from unittest.mock import patch

import pandas as pd

from src.checks.duplicates import (
    compute_duplicates_statistics,
    compute_id_duplicates,
    load_default_duplicates_settings,
)

# TODO: Make better docstrings for all test cases


class TestDuplicates(unittest.TestCase):  # noqa: D101
    def tearDown(self):
        """Clean up after each test method"""
        pass

    @patch("src.checks.duplicates.st")
    def test_compute_id_duplicates(self, mock_st):
        """Test the compute_id_duplicates function."""
        mock_st.session_state = {"resolved_duplicates": 5}

        # Test Case 1: No duplicates
        df = pd.DataFrame(
            {
                "caseID": [1, 2, 3, 4],
                "survey_key": ["a", "b", "c", "d"],
            }
        )
        result = compute_id_duplicates(df, "caseID", "survey_key", None)
        # Should be empty since there are no duplicates
        self.assertTrue(result.empty)

        # Test Case 2: Some duplicates
        df2 = pd.DataFrame(
            {
                "caseID": [1, 2, 2, 3, 4, 4, 4],
                "survey_key": ["a", "b", "b", "c", "d", "d", "d"],
            }
        )
        result2 = compute_id_duplicates(df2, "caseID", "survey_key", None)
        # Only rows with duplicated caseID should be present
        self.assertTrue((result2["caseID"].isin([2, 4])).all())
        # Check that id_dup_count is correct
        self.assertTrue((result2[result2["caseID"] == 2]["id_dup_count"] == 2).all())
        self.assertTrue((result2[result2["caseID"] == 4]["id_dup_count"] == 3).all())
        # Check that id_dup_percent is correct
        self.assertAlmostEqual(
            result2[result2["caseID"] == 2]["id_dup_percent"].iloc[0], 2 / 7 * 100
        )
        self.assertAlmostEqual(
            result2[result2["caseID"] == 4]["id_dup_percent"].iloc[0], 3 / 7 * 100
        )

        # Test Case 3: All IDs are duplicates (all the same)
        df3 = pd.DataFrame({"caseID": [1, 1, 1, 1], "survey_key": ["a", "b", "c", "d"]})
        result3 = compute_id_duplicates(df3, "caseID", "survey_key", None)
        self.assertEqual(result3["id_dup_count"].iloc[0], 4)
        self.assertTrue((result3["id_dup_count"] == 4).all())
        self.assertTrue((result3["id_dup_percent"] == 100.0).all())

        # Test Case 4: display_cols is None
        result4 = compute_id_duplicates(df2, "caseID", "survey_key", None)
        self.assertIn("caseID", result4.columns)
        self.assertIn("survey_key", result4.columns)
        self.assertIn("id_dup_count", result4.columns)
        self.assertIn("id_dup_percent", result4.columns)

    @patch("src.checks.duplicates.st")
    def test_compute_duplicates_statistics(self, mock_st):
        """Test the compute_duplicates_statistics function."""
        mock_st.session_state = {"resolved_duplicates": 5}
        # Case 1: No duplicates in any column
        df = pd.DataFrame(
            {
                "id": [1, 2, 3, 4],
                "col1": ["a", "b", "c", "d"],
                "col2": [10, 20, 30, 40],
            }
        )
        result = compute_duplicates_statistics(df, "id", "col1", ["col1", "col2"])
        self.assertEqual(result[0], 2)  # total_cols_checked
        self.assertEqual(result[1], 0)  # total_cols_with_dups
        self.assertEqual(result[2], 2)  # total_cols_no_dups
        self.assertEqual(result[3], 0)  # total_dups
        self.assertEqual(result[4], 0)  # total_id_dups
        self.assertEqual(result[5], 5)  # total_resolved_dups

        # Test Case 2: Duplicates in one column
        df2 = pd.DataFrame(
            {
                "id": [1, 2, 2, 3, 4, 4, 4],
                "col1": ["a", "b", "b", "c", "d", "d", "d"],
                "col2": [10, 20, 20, 30, 40, 40, 40],
            }
        )
        result2 = compute_duplicates_statistics(df2, "id", "col1", ["col1", "col2"])
        self.assertEqual(result2[0], 2)  # total_cols_checked
        self.assertEqual(result2[1], 2)  # total_cols_with_dups
        self.assertEqual(result2[2], 0)  # total_cols_no_dups
        self.assertEqual(result2[3], 10)
        self.assertEqual(result2[4], 5)
        self.assertEqual(result2[5], 5)

        # Test Case 3: All values are duplicates
        df3 = pd.DataFrame(
            {
                "id": [1, 1, 1, 1],
                "col1": ["x", "x", "x", "x"],
                "col2": [5, 5, 5, 5],
            }
        )
        result3 = compute_duplicates_statistics(df3, "id", "col1", ["col1", "col2"])
        self.assertEqual(result3[0], 2)
        self.assertEqual(result3[1], 2)
        self.assertEqual(result3[2], 0)
        # Each column: all 4 rows are duplicates, so for col1: 4, col2: 4, total_dups=8
        self.assertEqual(result3[3], 8)
        self.assertEqual(result3[4], 4)
        self.assertEqual(result3[5], 5)

        # Test Case 4: dup_cols is empty
        df4 = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "col1": ["a", "b", "c"],
            }
        )
        result4 = compute_duplicates_statistics(df4, "id", "col1", [])
        self.assertEqual(result4[0], 0)  # total_cols_checked
        self.assertEqual(result4[1], 0)  # total_cols_with_dups
        self.assertEqual(result4[2], 0)  # total_cols_no_dups
        self.assertEqual(result4[3], 0)  # total_dups
        self.assertEqual(result4[4], 0)  # total_id_dups
        self.assertEqual(result4[5], 5)

    @patch("src.checks.duplicates.st")
    def test_resolved_duplicates_from_session_state(self, mock_st):
        """
        Test the compute_duplicates_statistics function
        with resolved_duplicates from session_state.
        """
        # Simulate resolved_duplicates in session_state
        mock_st.session_state = {"resolved_duplicates": 42}
        df = pd.DataFrame(
            {
                "id": [1, 2, 2, 3, 4, 4, 4],
                "col1": ["a", "b", "b", "c", "d", "d", "d"],
                "col2": [10, 20, 20, 30, 40, 40, 40],
            }
        )
        result = compute_duplicates_statistics(df, "id", "col1", ["col1", "col2"])
        self.assertEqual(result[5], 5)

    @patch("src.checks.duplicates.st")
    def test_resolved_duplicates_default_zero(self, mock_st):
        """
        Test the compute_duplicates_statistics function
        with default resolved_duplicates.
        """
        # Simulate session_state without resolved_duplicates
        mock_st.session_state = {}
        df = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "col1": ["a", "b", "c"],
                "col2": [10, 20, 30],
            }
        )
        result = compute_duplicates_statistics(df, "id", "col1", ["col1", "col2"])
        self.assertEqual(result[5], 0)

    @patch("src.checks.duplicates.st")
    def test_empty_dataframe(self, mock_st):
        """
        Test the compute_duplicates_statistics function
        with an empty DataFrame.
        """
        mock_st.session_state = {}
        df = pd.DataFrame(columns=["id", "col1", "col2"])
        result = compute_duplicates_statistics(df, "id", "col1", ["col1", "col2"])
        self.assertEqual(result[0], 2)
        self.assertEqual(result[1], 0)
        self.assertEqual(result[2], 2)
        self.assertEqual(result[3], 0)
        self.assertEqual(result[4], 0)
        self.assertEqual(result[5], 0)

    @patch("src.checks.duplicates.st")
    def test_nonexistent_columns(self, mock_st):
        """
        Test the compute_duplicates_statistics function
        with non-existent columns.
        """
        mock_st.session_state = {}
        df = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "col1": ["a", "b", "c"],
            }
        )
        # dup_cols contains a column not in df
        with self.assertRaises(KeyError):
            compute_duplicates_statistics(df, "id", "col1", ["col1", "colX"])

    @patch("src.checks.duplicates.st")
    @patch("src.checks.duplicates.os.path.exists")
    @patch("src.checks.duplicates.load_check_settings")
    def test_load_default_duplicates_settings_file_exists(
        self, mock_load_check_settings, mock_exists, mock_st
    ):
        """
        Test the load_default_duplicates_settings function
        when settings file exists.
        """
        # Simulate settings file exists
        mock_exists.return_value = True
        # Simulate settings loaded from file
        mock_load_check_settings.return_value = {
            "survey_id": "enumid",
            "survey_key": "key",
            "date": "SubmissionDate",
            "dup_cols": ["enumid", "latitude", "longitude"],
            "display_cols": ["enumid", "latitude"],
        }
        # Simulate session_state config_pages (should not be used if file exists)
        mock_st.session_state = {
            "config_pages": {
                "Survey ID": ["sid1", "sid2"],
                "Survey KEY": ["skey1", "skey2"],
                "Survey Date": ["sdate1", "sdate2"],
            }
        }
        result = load_default_duplicates_settings("settings.json", 1)
        self.assertEqual(result[0], "enumid")
        self.assertEqual(result[1], "key")
        self.assertEqual(result[2], "SubmissionDate")
        self.assertEqual(result[3], ["enumid", "latitude", "longitude"])
        self.assertEqual(result[4], ["enumid", "latitude"])

    @patch("src.checks.duplicates.st")
    @patch("src.checks.duplicates.os.path.exists")
    @patch("src.checks.duplicates.load_check_settings")
    def test_load_default_duplicates_settings_file_missing(self, mock_exists, mock_st):
        """Test the load_default_duplicates_settings function
        when settings file is missing.
        """
        # Simulate settings file does not exist
        mock_exists.return_value = False
        # Simulate session_state config_pages
        mock_st.session_state = {
            "config_pages": {
                "Survey ID": ["sid1", "sid2"],
                "Survey KEY": ["skey1", "skey2"],
                "Survey Date": ["sdate1", "sdate2"],
            }
        }
        result = load_default_duplicates_settings("missing.json", 2)
        self.assertEqual(result[0], "sid2")
        self.assertEqual(result[1], "skey2")
        self.assertEqual(result[2], "sdate2")
        self.assertIsNone(result[3])
        self.assertIsNone(result[4])

    @patch("src.checks.duplicates.st")
    @patch("src.checks.duplicates.os.path.exists")
    @patch("src.checks.duplicates.load_check_settings")
    def test_load_default_duplicates_settings_file_exists_partial_settings(
        self, mock_load_check_settings, mock_exists, mock_st
    ):
        """
        Test the load_default_duplicates_settings function
        when settings file exists but is partial.
        """
        # Simulate settings file exists
        mock_exists.return_value = True
        # Simulate partial settings loaded from file
        mock_load_check_settings.return_value = {
            "survey_id": "enumid",
            # survey_key and date missing
        }
        # Simulate session_state config_pages
        mock_st.session_state = {
            "config_pages": {
                "Survey ID": ["sid1"],
                "Survey KEY": ["skey1"],
                "Survey Date": ["sdate1"],
            }
        }
        result = load_default_duplicates_settings("settings.json", 1)
        self.assertEqual(result[0], "enumid")
        self.assertEqual(result[1], "skey1")
        self.assertEqual(result[2], "sdate1")
        self.assertIsNone(result[3])
        self.assertIsNone(result[4])

    @patch("src.checks.duplicates.st")
    @patch("src.checks.duplicates.os.path.exists")
    @patch("src.checks.duplicates.load_check_settings")
    def test_load_default_duplicates_settings_missing_config_pages(
        self, mock_load_check_settings, mock_exists, mock_st
    ):
        """Test the load_default_duplicates_settings function
        when config_pages is missing.
        """
        # Simulate settings file does not exist
        mock_exists.return_value = False
        # Simulate session_state missing config_pages
        mock_st.session_state = {}
        # Should raise KeyError because config_pages is missing
        with self.assertRaises(KeyError):
            load_default_duplicates_settings("missing.json", 1)


if __name__ == "__main__":
    unittest.main()
