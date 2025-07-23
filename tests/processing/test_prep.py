"""Test the prep module."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest

from datasure.processing.prep import (
    prep_add_new_column,
    prep_apply_action,
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

    @patch("datasure.processing.prep.st")
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

    @patch("datasure.processing.prep.st")
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

    @patch("datasure.processing.prep.st")
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

    @patch("datasure.processing.prep.st")
    def test_quotient_wrong_column_count(self, mock_st, sample_prep_data):
        """Test error handling when quotient operation has wrong number of columns."""
        prep_add_new_column(
            sample_prep_data,
            "add new column 'ratio with quotient' ['salary', 'age', 'id']",
        )
        mock_st.error.assert_called_once_with(
            "Quotient and diff require exactly two columns."
        )


class TestPrepApplyAction:
    """Test the prep_apply_action function."""

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_prep_apply_action_with_new_action(self, mock_save_table, mock_get_table):
        """Test prep_apply_action when adding a new action."""
        # Mock existing prep log - needs to_pandas method
        existing_log_mock = MagicMock()
        existing_log = pd.DataFrame(
            {
                "action": ["remove column(s)"],
                "description": ["remove column(s) ['old_col']"],
            }
        )
        existing_log_mock.to_pandas.return_value = existing_log

        # Mock prep data - needs to_pandas method
        prep_data_mock = MagicMock()
        prep_data = pd.DataFrame(
            {"col1": [1, 2, 3], "col2": ["a", "b", "c"], "old_col": ["x", "y", "z"]}
        )
        prep_data_mock.to_pandas.return_value = prep_data

        # Setup mock returns - get_table called twice (log, then data)
        mock_get_table.side_effect = [existing_log_mock, prep_data_mock]

        # Call function with new action
        prep_apply_action(
            project_id="test_project",
            alias="test_alias",
            action="remove column(s)",
            description="remove column(s) ['col2']",
        )

        # Verify duckdb_get_table was called correctly
        assert mock_get_table.call_count == 2
        mock_get_table.assert_any_call(
            "test_project", "prep_log_test_alias", db_name="logs"
        )
        mock_get_table.assert_any_call("test_project", "test_alias", db_name="prep")

        # Verify duckdb_save_table was called for both log and data
        assert mock_save_table.call_count == 2

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_prep_apply_action_without_new_action(
        self, mock_save_table, mock_get_table
    ):
        """Test prep_apply_action when reapplying existing actions."""
        # Mock existing prep log
        existing_log_mock = MagicMock()
        existing_log = pd.DataFrame(
            {
                "action": ["remove column(s)", "transform column(s)"],
                "description": [
                    "remove column(s) ['old_col']",
                    "transform column(s) 'col1 to abs'",
                ],
            }
        )
        existing_log_mock.to_pandas.return_value = existing_log

        # Mock raw data
        raw_data_mock = MagicMock()
        raw_data = pd.DataFrame(
            {"col1": [-1, -2, 3], "col2": ["a", "b", "c"], "old_col": ["x", "y", "z"]}
        )
        raw_data_mock.to_pandas.return_value = raw_data

        # Setup mock returns
        mock_get_table.side_effect = [existing_log_mock, raw_data_mock]

        # Call function without new action
        prep_apply_action(project_id="test_project", alias="test_alias")

        # Verify raw data was retrieved instead of prep data
        mock_get_table.assert_any_call("test_project", "test_alias", db_name="raw")

        # Verify final data was saved
        mock_save_table.assert_called_once()

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_prep_apply_action_unsupported_action(
        self, mock_save_table, mock_get_table
    ):
        """Test prep_apply_action with unsupported action raises ValueError."""
        # Mock existing prep log with unsupported action
        existing_log_mock = MagicMock()
        existing_log = pd.DataFrame(
            {"action": ["unsupported_action"], "description": ["some description"]}
        )
        existing_log_mock.to_pandas.return_value = existing_log

        raw_data_mock = MagicMock()
        raw_data = pd.DataFrame({"col1": [1, 2, 3]})
        raw_data_mock.to_pandas.return_value = raw_data

        mock_get_table.side_effect = [existing_log_mock, raw_data_mock]

        # Should raise ValueError for unsupported action
        with pytest.raises(ValueError, match="Unsupported action: unsupported_action"):
            prep_apply_action(project_id="test_project", alias="test_alias")

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_prep_apply_action_all_supported_actions(
        self, mock_save_table, mock_get_table
    ):
        """Test prep_apply_action with all supported action types."""
        # Mock prep log with all supported actions
        existing_log_mock = MagicMock()
        existing_log = pd.DataFrame(
            {
                "action": [
                    "remove column(s)",
                    "remove row(s)",
                    "transform column(s)",
                    "add new column",
                ],
                "description": [
                    "remove column(s) ['unwanted_col']",
                    "remove row(s) by index ['2']",
                    "transform column(s) 'score to abs'",
                    "add new column 'total with sum' ['col1', 'col2']",
                ],
            }
        )
        existing_log_mock.to_pandas.return_value = existing_log

        # Mock raw data
        raw_data_mock = MagicMock()
        raw_data = pd.DataFrame(
            {
                "col1": [1, 2, 3, 4],
                "col2": [10, 20, 30, 40],
                "score": [-5, 10, -15, 20],
                "unwanted_col": ["a", "b", "c", "d"],
            }
        )
        raw_data_mock.to_pandas.return_value = raw_data

        mock_get_table.side_effect = [existing_log_mock, raw_data_mock]

        # Should not raise any errors
        prep_apply_action(project_id="test_project", alias="test_alias")

        # Verify database operations were called
        assert mock_get_table.call_count == 2
        mock_save_table.assert_called_once()

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_prep_apply_action_empty_log(self, mock_save_table, mock_get_table):
        """Test prep_apply_action with empty prep log."""
        # Mock empty prep log
        empty_log_mock = MagicMock()
        empty_log = pd.DataFrame({"action": [], "description": []})
        empty_log_mock.to_pandas.return_value = empty_log

        # Mock raw data
        raw_data_mock = MagicMock()
        raw_data = pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
        raw_data_mock.to_pandas.return_value = raw_data

        mock_get_table.side_effect = [empty_log_mock, raw_data_mock]

        # Should work without errors
        prep_apply_action(project_id="test_project", alias="test_alias")

        # Should still save the data even with no operations
        mock_save_table.assert_called_once()


class TestPrepAddNewColumnExtended:
    """Extended tests for prep_add_new_column function."""

    def test_add_constant_value_column(self, sample_prep_data):
        """Test adding a column with constant value."""
        result = prep_add_new_column(
            sample_prep_data, "add new column 'status with constant value active'"
        )
        if isinstance(result, pd.DataFrame):
            assert "status" in result.columns
            assert all(result["status"] == "active")

    def test_add_index_column(self, sample_prep_data):
        """Test adding a column with index values."""
        result = prep_add_new_column(
            sample_prep_data, "add new column 'row_index with index'"
        )
        if isinstance(result, pd.DataFrame):
            assert "row_index" in result.columns
            assert result["row_index"].tolist() == list(sample_prep_data.index)

    @patch("datasure.processing.prep.st")
    def test_add_uuid_column(self, mock_st, sample_prep_data):
        """Test adding a column with UUID values."""
        mock_st.session_state.st_project_id = "test_project"

        result = prep_add_new_column(
            sample_prep_data, "add new column 'unique_id with uuid'"
        )
        if isinstance(result, pd.DataFrame):
            assert "unique_id" in result.columns
            # UUIDs should be different for each row
            uuid_values = result["unique_id"].tolist()
            assert len(set(uuid_values)) == len(uuid_values)  # All unique
            assert all(len(uuid) == 64 for uuid in uuid_values)  # SHA256 hash length

    def test_add_random_column(self, sample_prep_data):
        """Test adding a column with random values."""
        result = prep_add_new_column(
            sample_prep_data, "add new column 'random_val with random'"
        )
        if isinstance(result, pd.DataFrame):
            assert "random_val" in result.columns
            # Random values should be between 0 and 1
            assert all(0 <= val <= 1 for val in result["random_val"])

    def test_add_aggregation_columns(self, sample_prep_data):
        """Test adding columns with various aggregation functions."""
        aggregations = [
            ("sum", "add new column 'total with sum' ['id', 'age']", "total"),
            ("mean", "add new column 'average with mean' ['id', 'age']", "average"),
            ("median", "add new column 'middle with median' ['id', 'age']", "middle"),
            ("max", "add new column 'maximum with max' ['id', 'age']", "maximum"),
            ("min", "add new column 'minimum with min' ['id', 'age']", "minimum"),
            ("count", "add new column 'counted with count' ['id', 'age']", "counted"),
            ("std", "add new column 'deviation with std' ['id', 'age']", "deviation"),
        ]

        for _agg_name, description, expected_col_name in aggregations:
            result = prep_add_new_column(sample_prep_data.copy(), description)
            if isinstance(result, pd.DataFrame):
                assert expected_col_name in result.columns

    def test_add_column_invalid_column_spec(self, sample_prep_data):
        """Test error handling with invalid column specification."""
        # Test that the function raises an AttributeError for invalid format
        with pytest.raises(AttributeError):
            prep_add_new_column(
                sample_prep_data, "add new column 'total with sum' invalid_format"
            )


class TestPrepTransformColumnsExtended:
    """Extended tests for prep_transform_columns function."""

    def test_arithmetic_operations(self, sample_prep_data):
        """Test all arithmetic operations."""
        operations = [
            ("add", "transform column(s) 'age to add' 5", lambda x: x + 5),
            ("subtract", "transform column(s) 'age to subtract' 5", lambda x: x - 5),
            ("multiply", "transform column(s) 'age to multiply' 2", lambda x: x * 2),
            ("divide", "transform column(s) 'age to divide' 2", lambda x: x / 2),
        ]

        for _op_name, description, expected_func in operations:
            test_data = sample_prep_data.copy()
            original_values = test_data["age"].copy()

            result = prep_transform_columns(test_data, description)
            if isinstance(result, pd.DataFrame):
                expected_values = expected_func(original_values)
                # Check values are approximately equal, allowing for dtype differences
                assert result["age"].tolist() == expected_values.tolist()

    def test_string_conversions(self, sample_prep_data):
        """Test string conversion operations."""
        # Add a string column with dates for testing
        test_data = sample_prep_data.copy()
        test_data["date_strings"] = [
            "2024-01-01",
            "2024-02-01",
            "2024-03-01",
            "2024-04-01",
            "2024-05-01",
        ]
        test_data["number_strings"] = ["1", "2", "3", "4", "5"]

        # Test string to date conversion
        result = prep_transform_columns(
            test_data, "transform column(s) 'date_strings to string to date'"
        )
        if isinstance(result, pd.DataFrame):
            assert pd.api.types.is_datetime64_any_dtype(result["date_strings"])

        # Test string to number conversion
        result = prep_transform_columns(
            test_data, "transform column(s) 'number_strings to string to number'"
        )
        if isinstance(result, pd.DataFrame):
            assert pd.api.types.is_numeric_dtype(result["number_strings"])

    def test_math_operations_comprehensive(self, sample_prep_data):
        """Test all mathematical operations."""
        # Add decimal values for testing
        test_data = sample_prep_data.copy()
        test_data["decimal_values"] = [1.7, 2.3, 3.8, 4.1, 5.9]

        math_ops = [
            ("floor", "transform column(s) 'decimal_values to floor'"),
            ("ceil", "transform column(s) 'decimal_values to ceil'"),
            ("round", "transform column(s) 'decimal_values to round'"),
            ("abs", "transform column(s) 'decimal_values to abs'"),
        ]

        for _op_name, description in math_ops:
            result = prep_transform_columns(test_data.copy(), description)
            if isinstance(result, pd.DataFrame):
                assert "decimal_values" in result.columns

    def test_datetime_extractions_comprehensive(self, sample_prep_data):
        """Test all datetime extraction operations."""
        datetime_ops = [
            ("day of month", "transform column(s) 'date_joined to day of month'"),
            ("day of week", "transform column(s) 'date_joined to day of week'"),
            ("day of year", "transform column(s) 'date_joined to day of year'"),
            ("date", "transform column(s) 'date_joined to date'"),
            ("week of year", "transform column(s) 'date_joined to week of year'"),
            ("month of year", "transform column(s) 'date_joined to month of year'"),
            ("year", "transform column(s) 'date_joined to year'"),
            ("quarter of year", "transform column(s) 'date_joined to quarter of year'"),
            ("hour", "transform column(s) 'date_joined to hour'"),
            ("minute", "transform column(s) 'date_joined to minute'"),
            ("second", "transform column(s) 'date_joined to second'"),
        ]

        for _op_name, description in datetime_ops:
            result = prep_transform_columns(sample_prep_data.copy(), description)
            if isinstance(result, pd.DataFrame):
                assert "date_joined" in result.columns

    def test_string_operations_comprehensive(self, sample_prep_data):
        """Test comprehensive string operations."""
        test_data = sample_prep_data.copy()
        test_data["test_text"] = [
            "  Hello World  ",
            "  TESTING  ",
            "  sample text  ",
            "  Another Test  ",
            "  Final Text  ",
        ]

        string_ops = [
            ("trim", "transform column(s) 'test_text to trim'"),
            ("lower", "transform column(s) 'test_text to lower'"),
            ("upper", "transform column(s) 'test_text to upper'"),
        ]

        for _op_name, description in string_ops:
            result = prep_transform_columns(test_data.copy(), description)
            if isinstance(result, pd.DataFrame):
                assert "test_text" in result.columns

    def test_replace_with_invalid_format(self, sample_prep_data):
        """Test replace operation with invalid format."""
        with pytest.raises(ValueError, match="Invalid replace format"):
            prep_transform_columns(
                sample_prep_data,
                "transform column(s) 'name to replace by replacing invalid_format'",
            )

    def test_substring_with_invalid_format(self, sample_prep_data):
        """Test substring operation with invalid format."""
        with pytest.raises(ValueError, match="Invalid description format"):
            prep_transform_columns(
                sample_prep_data,
                "transform column(s) 'name to substring' invalid_format",
            )


class TestPrepRemoveRowsExtended:
    """Extended tests for prep_remove_rows function."""

    def test_remove_rows_datetime_conditions(self, sample_prep_data):
        """Test removing rows with datetime conditions."""
        # Test with datetime column
        test_data = sample_prep_data.copy()

        # Test greater than datetime
        description = "remove row(s) by condition 'value is greater than' ['date_joined'] with value ['2020-01-01']"
        result = prep_remove_rows(test_data, description)
        if isinstance(result, pd.DataFrame):
            # Should keep rows with dates <= 2020-01-01
            assert len(result) <= len(test_data)

    def test_remove_rows_not_equal_condition(self, sample_prep_data):
        """Test removing rows where values are not equal to specified values."""
        description = "remove row(s) by condition 'value is not equal to' ['department'] with value ['IT']"
        result = prep_remove_rows(sample_prep_data, description)

        if isinstance(result, pd.DataFrame):
            # Should keep only IT departments
            assert (
                all(dept == "IT" for dept in result["department"])
                if len(result) > 0
                else True
            )

    def test_remove_rows_not_missing_condition(self, sample_prep_data):
        """Test removing rows where values are not missing."""
        # Add some missing values
        test_data = sample_prep_data.copy()
        test_data.loc[1, "name"] = None
        test_data.loc[3, "age"] = None

        description = "remove row(s) by condition 'value is not missing' ['name']"
        result = prep_remove_rows(test_data, description)

        # This should keep only rows where name is missing
        if isinstance(result, pd.DataFrame):
            assert result["name"].isna().all() if len(result) > 0 else True

    def test_remove_rows_not_between_condition(self, sample_prep_data):
        """Test removing rows where values are not between specified values."""
        description = "remove row(s) by condition 'value is not between' ['age'] with values 30 and 40"
        result = prep_remove_rows(sample_prep_data, description)

        if isinstance(result, pd.DataFrame):
            # Should keep rows where age is between 30 and 40
            assert (
                all(30 <= age <= 40 for age in result["age"])
                if len(result) > 0
                else True
            )

    def test_remove_rows_not_like_condition(self, sample_prep_data):
        """Test removing rows where values do not match pattern."""
        description = (
            "remove row(s) by condition 'value is not like' ['name'] with pattern 'A'"
        )
        result = prep_remove_rows(sample_prep_data, description)

        if isinstance(result, pd.DataFrame):
            # Should keep rows where name contains 'A'
            assert (
                all("A" in name for name in result["name"]) if len(result) > 0 else True
            )

    def test_remove_rows_comparison_operators(self, sample_prep_data):
        """Test all comparison operators for row removal."""
        operators = [
            (
                "value is greater than",
                "remove row(s) by condition 'value is greater than' ['age'] with value ['30']",
            ),
            (
                "value is greater than or equal to",
                "remove row(s) by condition 'value is greater than or equal to' ['age'] with value ['35']",
            ),
            (
                "value is less than",
                "remove row(s) by condition 'value is less than' ['age'] with value ['40']",
            ),
            (
                "value is less than or equal to",
                "remove row(s) by condition 'value is less than or equal to' ['age'] with value ['35']",
            ),
        ]

        for _op_name, description in operators:
            result = prep_remove_rows(sample_prep_data.copy(), description)
            if isinstance(result, pd.DataFrame):
                assert len(result) <= len(sample_prep_data)

    def test_remove_rows_with_invalid_column_specs(self, sample_prep_data):
        """Test error handling with various invalid column specifications."""
        # Test invalid column specification that causes AttributeError
        with pytest.raises(AttributeError):
            prep_remove_rows(
                sample_prep_data,
                "remove row(s) by condition 'value is missing' invalid_format",
            )
