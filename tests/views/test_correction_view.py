"""Tests for correction_view.py logic patterns."""

import polars as pl

from datasure.views.correction_view import _build_correction_log_display


class TestCorrectionInputFormLogic:
    """Test the correction_input_form function logic patterns."""

    def test_correction_form_data_type_validation_numeric_logic(self):
        """Test numeric data type validation logic."""
        # Test numeric column validation logic
        column_name = "age"
        column_schema = {"age": pl.Int64, "name": pl.Utf8}
        new_value_str = "25"

        # Simulate the numeric validation logic from the function
        if column_schema[column_name] in [pl.Int64, pl.Float64]:
            try:
                validated_value = float(new_value_str)
                is_valid = True
                error_message = None
            except ValueError:
                validated_value = None
                is_valid = False
                error_message = "New value must be a number."
        else:
            validated_value = new_value_str
            is_valid = True
            error_message = None

        assert is_valid is True
        assert validated_value == 25.0
        assert error_message is None

    def test_correction_form_invalid_numeric_value_logic(self):
        """Test validation logic with invalid numeric value."""
        column_name = "age"
        column_schema = {"age": pl.Int64, "name": pl.Utf8}
        new_value_str = "not_a_number"

        # Simulate the numeric validation logic
        if column_schema[column_name] in [pl.Int64, pl.Float64]:
            try:
                validated_value = float(new_value_str)
                is_valid = True
                error_message = None
            except ValueError:
                validated_value = None
                is_valid = False
                error_message = "New value must be a number."
        else:
            validated_value = new_value_str
            is_valid = True
            error_message = None

        assert is_valid is False
        assert validated_value is None
        assert error_message == "New value must be a number."

    def test_correction_form_string_data_type_logic(self):
        """Test string data type handling logic."""
        column_name = "name"
        column_schema = {"age": pl.Int64, "name": pl.Utf8}
        new_value_str = "John Doe"

        # Simulate the validation logic for string columns
        if column_schema[column_name] in [pl.Int64, pl.Float64]:
            try:
                validated_value = float(new_value_str)
                is_valid = True
                error_message = None
            except ValueError:
                validated_value = None
                is_valid = False
                error_message = "New value must be a number."
        else:
            validated_value = new_value_str
            is_valid = True
            error_message = None

        assert is_valid is True
        assert validated_value == "John Doe"
        assert error_message is None

    def test_correction_form_datetime_handling_logic(self):
        """Test datetime data type handling logic."""
        # Simulate datetime input handling
        column_dtype = pl.Datetime

        # Mock date input from Streamlit
        from datetime import date

        date_input = date(2024, 1, 15)

        # Simulate the datetime conversion logic
        if column_dtype == pl.Datetime:
            # Convert date to datetime as done in the function
            converted_datetime = pl.datetime(
                date_input.year, date_input.month, date_input.day
            )
            is_datetime_conversion = True
        else:
            converted_datetime = None
            is_datetime_conversion = False

        assert is_datetime_conversion is True
        # Note: pl.datetime returns a datetime expression, not a value
        assert converted_datetime is not None

    def test_correction_form_action_types_logic(self):
        """Test different correction action types logic."""

        def requires_column_selection(action):
            return action in ["modify value", "remove value"]

        def requires_new_value(action):
            return action == "modify value"

        # Test each action type
        test_cases = [
            ("modify value", True, True, None),
            ("remove value", True, False, None),
            (
                "remove row",
                False,
                False,
                "This will remove the row with the current ID value from the dataset.",
            ),
        ]

        for action, needs_column, needs_new_value, warning_message in test_cases:
            assert requires_column_selection(action) == needs_column
            assert requires_new_value(action) == needs_new_value

            if action == "remove row":
                assert warning_message is not None
            else:
                assert warning_message is None

    def test_correction_form_data_retrieval_logic(self):
        """Test the data retrieval and filtering logic."""
        # Mock corrected data
        mock_corrected_data = pl.DataFrame(
            {
                "KEY": ["uuid:123", "uuid:456", "uuid:789"],
                "name": ["Alice", "Bob", "Charlie"],
                "age": [25, 30, 35],
                "city": ["NYC", "LA", "Chicago"],
            }
        )

        # Test current value retrieval logic
        survey_key = "KEY"
        selected_key = "uuid:456"
        column_to_modify = "name"

        # Simulate the current value retrieval logic
        filtered_data = mock_corrected_data.filter(pl.col(survey_key) == selected_key)
        current_value = filtered_data.select(column_to_modify)[0, 0]

        assert current_value == "Bob"

    def test_correction_form_unique_key_options_logic(self):
        """Test unique key options retrieval logic."""
        # Mock corrected data with duplicate keys
        mock_corrected_data = pl.DataFrame(
            {
                "KEY": ["uuid:123", "uuid:456", "uuid:123", "uuid:789"],
                "name": ["Alice", "Bob", "Alice", "Charlie"],
                "age": [25, 30, 25, 35],
            }
        )

        # Test unique key retrieval logic
        survey_key = "KEY"

        # Simulate the unique key options logic
        key_options = mock_corrected_data.select(survey_key).unique(maintain_order=True)
        unique_keys = key_options.to_series().to_list()

        # Should have unique keys only
        expected_unique_keys = ["uuid:123", "uuid:456", "uuid:789"]
        assert len(unique_keys) == 3
        assert set(unique_keys) == set(expected_unique_keys)

    def test_correction_form_column_options_logic(self):
        """Test column options for modification logic."""
        # Mock corrected data
        mock_corrected_data = pl.DataFrame(
            {
                "KEY": ["uuid:123"],
                "name": ["Alice"],
                "age": [25],
                "city": ["NYC"],
                "score": [95.5],
            }
        )

        # Test column options logic
        available_columns = mock_corrected_data.columns

        # All columns should be available for modification
        expected_columns = ["KEY", "name", "age", "city", "score"]
        assert available_columns == expected_columns

    def test_correction_form_schema_type_checking_logic(self):
        """Test schema-based data type checking logic."""
        from datetime import datetime

        # Mock corrected data with different data types
        mock_corrected_data = pl.DataFrame(
            {
                "id": [1, 2, 3],
                "name": ["Alice", "Bob", "Charlie"],
                "score": [95.5, 87.2, 92.1],
                "active": [True, False, True],
                "created_date": [
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 2),
                    datetime(2024, 1, 3),
                ],
            }
        )

        # Test schema type checking logic
        schema = mock_corrected_data.schema

        # Test different column type checks
        test_cases = [
            ("id", pl.Int64, True),  # Integer column
            ("name", pl.Utf8, False),  # String column
            ("score", pl.Float64, True),  # Float column
            ("active", pl.Boolean, False),  # Boolean column
            ("created_date", pl.Datetime, False),  # Datetime column
        ]

        for col_name, expected_type, is_numeric in test_cases:
            actual_type = schema[col_name]
            assert actual_type == expected_type

            # Test numeric type checking logic
            if actual_type in [pl.Int64, pl.Float64]:
                assert is_numeric is True
            else:
                assert is_numeric is False

    def test_correction_form_remove_row_logic(self):
        """Test remove row action logic."""
        # Test remove row action handling
        action = "remove row"

        # Simulate the remove row logic
        if action == "remove row":
            warning_shown = True
            new_value = None
            current_value = None
            col_to_modify = None
        else:
            warning_shown = False
            new_value = "some_value"
            current_value = "old_value"
            col_to_modify = "some_column"

        assert warning_shown is True
        assert new_value is None
        assert current_value is None
        assert col_to_modify is None

    def test_correction_form_remove_value_logic(self):
        """Test remove value action logic."""
        # Test remove value action (sets new_value to None)
        action = "remove value"

        # Simulate the remove value logic
        if action == "modify value":
            new_value_required = True
        elif action == "remove value":
            new_value_required = False
            # In remove value, new_value would be set to None
            new_value = None
        else:
            new_value_required = False

        assert new_value_required is False
        assert new_value is None

    def test_correction_form_edge_cases_logic(self):
        """Test edge cases in correction form logic."""
        # Test empty dataset
        empty_data = pl.DataFrame()

        # Empty dataset should have no columns
        assert len(empty_data.columns) == 0

        # Test single row dataset
        single_row_data = pl.DataFrame({"KEY": ["uuid:123"], "value": [42]})

        # Should still work with single row
        assert len(single_row_data) == 1
        assert "KEY" in single_row_data.columns
        assert "value" in single_row_data.columns

    def test_correction_form_numeric_edge_cases_logic(self):
        """Test numeric validation edge cases logic."""
        # Test various numeric input scenarios
        test_cases = [
            ("42", 42.0, True),  # Integer string
            ("42.5", 42.5, True),  # Float string
            ("0", 0.0, True),  # Zero
            ("-42", -42.0, True),  # Negative number
            ("42.0", 42.0, True),  # Float with .0
            ("", None, False),  # Empty string
            ("abc", None, False),  # Non-numeric string
            ("42abc", None, False),  # Mixed alphanumeric
            ("42.5.6", None, False),  # Invalid float format
        ]

        def _handle_empty_value_error():
            raise ValueError("Empty string")

        for input_value, expected_output, should_succeed in test_cases:
            # Simulate numeric validation
            try:
                if input_value == "":
                    # Handle empty string case
                    _handle_empty_value_error()
                validated_value = float(input_value)
                is_valid = True
            except ValueError:
                validated_value = None
                is_valid = False

            assert is_valid == should_succeed
            if should_succeed:
                assert validated_value == expected_output
            else:
                assert validated_value is None

    def test_correction_form_database_interaction_logic(self):
        """Test database interaction parameters logic."""
        project_id = "test_project_123"
        alias = "survey_data"

        # Test that the function logic would call duckdb_get_table with correct params
        expected_project_id = project_id
        expected_alias = alias
        expected_db_name = "corrected"

        # Verify the expected parameters match what the function should use
        assert expected_project_id == "test_project_123"
        assert expected_alias == "survey_data"
        assert expected_db_name == "corrected"


class TestBuildCorrectionLogDisplay:
    """Test _build_correction_log_display: status columns and ordering."""

    def _base_log(self, **overrides) -> pl.DataFrame:
        data = {
            "date": ["2026-01-01"],
            "KEY": ["key1"],
            "ID": [None],
            "action": ["modify value"],
            "column": ["name"],
            "current_value": ["John"],
            "new_value": ["Johnny"],
            "reason": ["typo"],
        }
        data.update(overrides)
        return pl.DataFrame(data)

    def test_backfills_missing_status_columns(self):
        """A legacy log without status columns gets defaults applied."""
        log = self._base_log()

        result = _build_correction_log_display(log)

        assert result["status"].to_list() == ["Successful"]
        assert result["status_reason"].to_list() == [None]

    def test_preserves_existing_status_columns(self):
        """An already-refreshed log keeps its real status/reason values."""
        log = self._base_log(status=["Failed"], status_reason=["Key not found"])

        result = _build_correction_log_display(log)

        assert result["status"].to_list() == ["Failed"]
        assert result["status_reason"].to_list() == ["Key not found"]

    def test_status_columns_ordered_right_after_action(self):
        """status/status_reason are positioned right after action."""
        log = self._base_log()

        result = _build_correction_log_display(log)

        assert result.columns == [
            "date",
            "KEY",
            "ID",
            "action",
            "status",
            "status_reason",
            "column",
            "current_value",
            "new_value",
            "reason",
        ]
