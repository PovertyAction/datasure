"""Test the duplicates module."""

import unittest

import pandas as pd

from src.checks.duplicates import (
    compute_duplicates_statistics,
    compute_id_duplicates,
)


class TestDuplicates(unittest.TestCase):  # noqa: D101
    def tearDown(self):
        """Clean up after each test method"""
        pass

    # @patch("src.checks.duplicates.load_check_settings")
    # def test_load_default_duplicates_settings(mock_exists, mock_load_check_settings):
    #     """
    #     Test that load_default_duplicates_settings
    #     loads and returns the expected default configuration.
    #     """
    #     # Confirm it loads the expected default configuration structure.
    #     # Validate key components of the settings
    #     # Ensure it handles missing settings files properly.

    #     # firstttry using a non-existing path

    #     # the result must have the key config_pages
    #     # the result should also have inside config_pages the keys
    #     # Survey KEY, Survey ID,
    #  Survey Date, check that these keys
    #  when not present is handled gracefully

    #     # the result may or may not have the keys dup_cols and display_cols

    #     result = load_default_duplicates_settings("non_existing_path", 1)
    #     print(result)
    #     mock_load_check_settings.return_value = {
    #         "survey_id": "enumid",
    #         "survey_key": "key",
    #         "date": "SubmissionDate",
    #         "dup_cols": ["enumid", "latitude", "longitude"],
    #         "display_cols": ["enumid", "latitude"],
    #     }

    #     result = load_default_duplicates_settings("settings.json", 1)
    #     assert result[0] == "enumid"
    #     assert result[1] == "key"
    #     assert result[2] == "SubmissionDate"
    #     assert result[3] == ["enumid", "latitude", "longitude"]
    #     assert result[4] == ["enumid", "latitude"]
    def test_compute_id_duplicates(self):
        """Test the compute_id_duplicates function."""
        # Test Case 1: No duplicates
        df = pd.DataFrame(
            {
                "caseID": [1, 2, 3, 4],
                "survey_key": ["a", "b", "c", "d"],
            }
        )
        result = compute_id_duplicates(df, "caseID", "survey_key")
        # Should be empty since there are no duplicates
        self.assertTrue(result.empty)

        # Case 2: Some duplicates
        df2 = pd.DataFrame(
            {
                "caseID": [1, 2, 2, 3, 4, 4, 4],
                "survey_key": ["a", "b", "b", "c", "d", "d", "d"],
            }
        )
        result2 = compute_id_duplicates(df2, "caseID", "survey_key")
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
        result3 = compute_id_duplicates(df3, "caseID", "survey_key")
        self.assertEqual(result3["id_dup_count"].iloc[0], 4)
        self.assertTrue((result3["id_dup_count"] == 4).all())
        self.assertTrue((result3["id_dup_percent"] == 100.0).all())

        # Test Case 4: display_cols is None
        result4 = compute_id_duplicates(df2, "caseID", "survey_key", None)
        self.assertIn("caseID", result4.columns)
        self.assertIn("survey_key", result4.columns)
        self.assertIn("id_dup_count", result4.columns)
        self.assertIn("id_dup_percent", result4.columns)

    def test_compute_duplicates_statistics(self):
        """Test the compute_duplicates_statistics function."""
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

    # def test_compute_duplicates_statistics():

    #     # Test the overall summary statistics generated by this function
    #     # Validate output type and accuracy.
    #     pass

    # def test_compute_column_duplicates():
    #     # compute_column_duplicates()

    #     # Test for duplication across specific user-defined columns
    #     # Use datasets with:
    #     # Partial duplicates
    #     # No duplicates
    #     # All duplicates
    #     # Missing values in columns
    #     pass

    # def test_compute_id_duplicates():

    #     # Provide test datasets with:
    #     # Known duplicate values in a unique identifier field.
    #     # Edge Case: No duplicates.
    #     # Edge case: all IDs are duplicates.
    #     # Validate that the function identifies exact
    #     #  row matches correctly and outputs all duplicates
    #     pass


if __name__ == "__main__":
    unittest.main()
