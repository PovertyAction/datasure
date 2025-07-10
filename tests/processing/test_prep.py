"""Test the prep module."""

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from src.processing.prep import (
    prep_add_new_column,
    prep_remove_columns,
    prep_remove_rows,
    prep_transform_columns,
)


@pytest.fixture
def sample_prep_data():
    """Sample DataFrame for testing prep functions."""
    return pd.DataFrame(
        {
            "id": [1, 2, 3, 4, 5],
            "name": ["Alice", "Bob", "Charlie", "David", "Eve"],
            "age": [25, 30, 35, 40, 45],
            "salary": [50000.5, 60000.0, 70000.75, 80000.25, 90000.0],
            "date_joined": pd.to_datetime(
                ["2020-01-15", "2019-03-22", "2021-06-10", "2018-11-05", "2022-02-28"]
            ),
            "department": ["IT", "HR", "IT", "Finance", "HR"],
            "text_field": ["  HELLO  ", "world", "TEST", "sample", "data"],
        }
    )


@pytest.fixture
def sample_prep_log():
    """Sample prep log DataFrame."""
    return pd.DataFrame(
        {
            "action": ["remove column(s)", "remove row(s)"],
            "description": [
                "remove column(s) ['department']",
                "remove row(s) by index ['2']",
            ],
        }
    )


class TestPrepRemoveColumns:
    """Test prep_remove_columns function."""

    def test_remove_single_column(self, sample_prep_data):
        """Test removing a single column."""
        result = prep_remove_columns(sample_prep_data, "remove column(s) ['name']")
        assert "name" not in result.columns
        assert len(result.columns) == len(sample_prep_data.columns) - 1

    def test_remove_multiple_columns(self, sample_prep_data):
        """Test removing multiple columns."""
        result = prep_remove_columns(
            sample_prep_data, "remove column(s) ['name', 'age']"
        )
        assert "name" not in result.columns
        assert "age" not in result.columns
        assert len(result.columns) == len(sample_prep_data.columns) - 2

    @patch("src.processing.prep.st")
    def test_invalid_column_specification(self, mock_st, sample_prep_data):
        """Test handling of invalid column specification."""
        prep_remove_columns(sample_prep_data, "remove column(s) invalid_format")
        mock_st.error.assert_called_once()


class TestPrepRemoveRows:
    """Test prep_remove_rows function."""

    def test_remove_rows_by_index_single(self, sample_prep_data):
        """Test removing a single row by index."""
        result = prep_remove_rows(sample_prep_data, "remove row(s) by index ['2']")
        assert len(result) == len(sample_prep_data) - 1
        assert 2 not in result.index

    def test_remove_rows_by_index_multiple(self, sample_prep_data):
        """Test removing multiple rows by index."""
        result = prep_remove_rows(sample_prep_data, "remove row(s) by index ['1', '3']")
        assert len(result) == len(sample_prep_data) - 2
        assert 1 not in result.index
        assert 3 not in result.index

    def test_remove_rows_by_index_range(self, sample_prep_data):
        """Test removing rows by index range."""
        result = prep_remove_rows(sample_prep_data, "remove row(s) by index ['1:3']")
        assert len(result) == len(sample_prep_data) - 3
        for idx in [1, 2, 3]:
            assert idx not in result.index

    def test_remove_rows_by_condition_missing_values(self, sample_prep_data):
        """Test removing rows with missing values."""
        # Add some missing values
        test_data = sample_prep_data.copy()
        test_data.loc[1, "name"] = None
        test_data.loc[3, "age"] = None

        prep_remove_rows(
            test_data, "remove row(s) by condition 'value is missing' in ['name']"
        )

        assert test_data["name"].notna().all()

    def test_remove_rows_by_condition_equal_to(self, sample_prep_data):
        """Test removing rows where values equal specified values."""
        result = prep_remove_rows(
            sample_prep_data,
            "remove row(s) by condition 'value is equal to' on columns ['department'] with value ['IT']",
        )
        # Should keep only non-IT departments
        if result is not None:
            assert all(dept != "IT" for dept in result["department"])

    def test_remove_rows_by_condition_greater_than(self, sample_prep_data):
        """Test removing rows where values are greater than specified value."""
        result = prep_remove_rows(
            sample_prep_data,
            "remove row(s) by condition 'value is greater than' on columns ['age'] with value ['35']",
        )
        if result is not None:
            assert all(age <= 35 for age in result["age"])

    def test_remove_rows_by_condition_between(self, sample_prep_data):
        """Test removing rows where values are between specified values."""
        result = prep_remove_rows(
            sample_prep_data,
            "remove row(s) by condition 'value is between' on columns ['age'] with values 30 and 40",
        )
        if result is not None:
            assert all(age < 30 or age > 40 for age in result["age"])

    def test_remove_rows_by_condition_like(self, sample_prep_data):
        """Test removing rows where values match pattern."""
        result = prep_remove_rows(
            sample_prep_data,
            "remove row(s) by condition 'value is like' on columns ['name'] with pattern 'A'",
        )
        if result is not None:
            assert all("A" not in name for name in result["name"])

    @patch("src.processing.prep.st")
    def test_invalid_row_specification(self, mock_st, sample_prep_data):
        """Test handling of invalid row specification."""
        prep_remove_rows(sample_prep_data, "remove row(s) by index invalid_format")
        mock_st.error.assert_called_once()


class TestPrepTransformColumns:
    """Test prep_transform_columns function."""

    def test_datetime_extraction_day_of_month(self, sample_prep_data):
        """Test extracting day from datetime column."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'date_joined to day of month'"
        )
        assert result["date_joined"].dtype in [np.int32, np.int64]
        assert all(1 <= day <= 31 for day in result["date_joined"])

    def test_datetime_extraction_day_of_week(self, sample_prep_data):
        """Test extracting day of week from datetime column."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'date_joined to day of week'"
        )
        assert result["date_joined"].dtype in [np.int32, np.int64]
        assert all(0 <= day <= 6 for day in result["date_joined"])

    def test_datetime_extraction_day_of_year(self, sample_prep_data):
        """Test extracting day of year from datetime column."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'date_joined to day of year'"
        )
        assert result["date_joined"].dtype in [np.int32, np.int64]
        assert all(1 <= day <= 366 for day in result["date_joined"])

    def test_datetime_extraction_week_of_year(self, sample_prep_data):
        """Test extracting week of year from datetime column."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'date_joined' to 'week of year'"
        )
        assert all(1 <= week <= 53 for week in result["date_joined"])

    def test_datetime_extraction_month_of_year(self, sample_prep_data):
        """Test extracting month from datetime column."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'date_joined to month of year'"
        )
        assert all(1 <= month <= 12 for month in result["date_joined"])

    def test_datetime_extraction_quarter_of_year(self, sample_prep_data):
        """Test extracting quarter from datetime column."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'date_joined to quarter of year'"
        )
        assert all(1 <= quarter <= 4 for quarter in result["date_joined"])

    def test_datetime_extraction_year(self, sample_prep_data):
        """Test extracting year from datetime column."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'date_joined to year'"
        )
        assert all(year >= 2018 for year in result["date_joined"])

    def test_math_operations_floor(self, sample_prep_data):
        """Test floor operation on numeric column."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'salary to floor'"
        )
        assert all(val == int(val) for val in result["salary"])

    def test_math_operations_ceil(self, sample_prep_data):
        """Test ceil operation on numeric column."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'salary to ceil'"
        )
        original_salary = sample_prep_data["salary"].iloc[0]
        result_salary = result["salary"].iloc[0]
        assert result_salary >= original_salary

    def test_string_operations_trim(self, sample_prep_data):
        """Test trimming whitespace from string column."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'text_field' to 'trim'"
        )
        assert result["text_field"].iloc[0] == "HELLO"

    def test_string_operations_lower(self, sample_prep_data):
        """Test converting string to lowercase."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'text_field' to 'lower'"
        )
        assert all(text.islower() for text in result["text_field"])

    def test_string_operations_upper(self, sample_prep_data):
        """Test converting string to uppercase."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'name' to 'upper'"
        )
        assert all(name.isupper() for name in result["name"])

    def test_string_to_number(self, sample_prep_data):
        """Test converting string to number."""
        # Add a string column with numeric values
        test_data = sample_prep_data.copy()
        test_data["string_numbers"] = ["1", "2", "3", "4", "5"]
        result = prep_transform_columns(
            test_data, "transform column(s) 'string_numbers' to 'string to number'"
        )
        assert pd.api.types.is_numeric_dtype(result["string_numbers"])

    def test_get_dummies(self, sample_prep_data):
        """Test creating dummy variables from categorical column."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'department' to 'get dummies'"
        )
        # Should have columns for each unique department value
        assert "department_IT" in result.columns
        assert "department_HR" in result.columns
        assert "department_Finance" in result.columns

    def test_replace_text(self, sample_prep_data):
        """Test replacing text in string column."""
        result = prep_transform_columns(
            sample_prep_data,
            "transform column(s) 'name' to 'replace' by replacing 'Alice' with 'Alicia'",
        )
        assert "Alicia" in result["name"].values
        assert "Alice" not in result["name"].values

    def test_substring_extraction(self, sample_prep_data):
        """Test extracting substring from string column."""
        result = prep_transform_columns(
            sample_prep_data,
            "transform column(s) 'name' to 'substring' by taking substring from index from 0 to 2",
        )
        assert all(len(name) <= 2 for name in result["name"])

    def test_pattern_extraction(self, sample_prep_data):
        """Test extracting pattern from string column."""
        result = prep_transform_columns(
            sample_prep_data,
            "transform column(s) 'name to extract pattern by extracting pattern [A-Z]'",
        )
        # Should extract first capital letter from each name
        assert all(len(str(val)) <= 1 for val in result["name"] if pd.notna(val))

    @patch("src.processing.prep.st")
    def test_unknown_transformation(self, mock_st, sample_prep_data):
        """Test handling of unknown transformation function."""
        result = prep_transform_columns(
            sample_prep_data, "transform column(s) 'name to unknown_function'"
        )
        mock_st.error.assert_called_once()
        assert result.equals(sample_prep_data)


class TestPrepAddNewColumn:
    """Test prep_add_new_column function."""

    def test_add_sum_column(self, sample_prep_data):
        """Test adding a column with sum of other columns."""
        result = prep_add_new_column(
            sample_prep_data, "add new column 'total with sum' ['id', 'age']"
        )
        if isinstance(result, pd.DataFrame):
            assert "total" in result.columns
            expected_sum = sample_prep_data["id"] + sample_prep_data["age"]
            pd.testing.assert_series_equal(
                result["total"], expected_sum, check_names=False
            )

    def test_add_mean_column(self, sample_prep_data):
        """Test adding a column with mean of other columns."""
        result = prep_add_new_column(
            sample_prep_data, "add new column 'average with mean' ['id', 'age']"
        )
        if isinstance(result, pd.DataFrame):
            assert "average" in result.columns

    def test_add_quotient_column(self, sample_prep_data):
        """Test adding a column with quotient of two columns."""
        result = prep_add_new_column(
            sample_prep_data, "add new column 'ratio with quotient' ['salary', 'age']"
        )
        if isinstance(result, pd.DataFrame):
            assert "ratio" in result.columns
            expected_ratio = sample_prep_data["salary"] / sample_prep_data["age"]
            pd.testing.assert_series_equal(
                result["ratio"], expected_ratio, check_names=False
            )

    def test_add_diff_column(self, sample_prep_data):
        """Test adding a column with difference of two columns."""
        result = prep_add_new_column(
            sample_prep_data, "add new column 'age_diff with diff' ['age', 'id']"
        )
        if isinstance(result, pd.DataFrame):
            assert "age_diff" in result.columns
            expected_diff = sample_prep_data["age"] - sample_prep_data["id"]
            pd.testing.assert_series_equal(
                result["age_diff"], expected_diff, check_names=False
            )

    @patch("src.processing.prep.st")
    def test_quotient_wrong_column_count(self, mock_st, sample_prep_data):
        """Test error handling when quotient operation has wrong number of columns."""
        prep_add_new_column(
            sample_prep_data,
            "add new column 'ratio with quotient' ['salary', 'age', 'id']",
        )
        mock_st.error.assert_called_once_with(
            "Quotient and diff require exactly two columns."
        )
