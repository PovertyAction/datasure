"""Comprehensive tests for the prep module."""

from unittest.mock import patch

import polars as pl
import pytest

from datasure.processing.prep import (
    ActionType,
    AddNewColumnOperation,
    DescriptionParser,
    OperationError,
    PrepAction,
    PrepError,
    PrepProcessor,
    RemoveColumnsOperation,
    RemoveRowsOperation,
    TransformColumnsOperation,
    ValidationError,
    prep_apply_action,
)
from datasure.utils.prep_utils import PrepActionResult


class TestPrepExceptions:
    """Test custom exception classes."""

    def test_prep_error_base_exception(self):
        """Test PrepError base exception."""
        error = PrepError("Base error")
        assert str(error) == "Base error"
        assert isinstance(error, Exception)

    def test_validation_error_inheritance(self):
        """Test ValidationError inherits from PrepError."""
        error = ValidationError("Validation failed")
        assert str(error) == "Validation failed"
        assert isinstance(error, PrepError)
        assert isinstance(error, Exception)

    def test_operation_error_inheritance(self):
        """Test OperationError inherits from PrepError."""
        error = OperationError("Operation failed")
        assert str(error) == "Operation failed"
        assert isinstance(error, PrepError)
        assert isinstance(error, Exception)


class TestActionType:
    """Test ActionType enum."""

    def test_action_type_values(self):
        """Test ActionType enum values."""
        assert ActionType.REMOVE_COLUMNS.value == "remove column(s)"
        assert ActionType.REMOVE_ROWS.value == "remove row(s)"
        assert ActionType.TRANSFORM_COLUMNS.value == "transform column(s)"
        assert ActionType.ADD_NEW_COLUMN.value == "add new column"

    def test_action_type_membership(self):
        """Test ActionType enum membership."""
        assert ActionType.REMOVE_COLUMNS in ActionType
        assert ActionType.REMOVE_ROWS in ActionType
        assert ActionType.TRANSFORM_COLUMNS in ActionType
        assert ActionType.ADD_NEW_COLUMN in ActionType

    def test_action_type_from_string(self):
        """Test creating ActionType from string value."""
        assert ActionType("remove column(s)") == ActionType.REMOVE_COLUMNS
        assert ActionType("remove row(s)") == ActionType.REMOVE_ROWS
        assert ActionType("transform column(s)") == ActionType.TRANSFORM_COLUMNS
        assert ActionType("add new column") == ActionType.ADD_NEW_COLUMN

    def test_action_type_invalid_string(self):
        """Test invalid string raises ValueError."""
        with pytest.raises(ValueError):
            ActionType("invalid action")


class TestPrepAction:
    """Test PrepAction dataclass."""

    def test_prep_action_initialization(self):
        """Test PrepAction initialization."""
        prep_args = PrepActionResult(action="remove column(s)")
        prep_action = PrepAction(
            action_type=ActionType.REMOVE_COLUMNS, prep_args=prep_args
        )

        assert prep_action.action_type == ActionType.REMOVE_COLUMNS
        assert prep_action.prep_args == prep_args

    def test_prep_action_from_args_valid(self):
        """Test PrepAction.from_args with valid action."""
        prep_args = PrepActionResult(action="remove column(s)")
        prep_action = PrepAction.from_args(prep_args)

        assert prep_action.action_type == ActionType.REMOVE_COLUMNS
        assert prep_action.prep_args == prep_args

    def test_prep_action_from_args_invalid(self):
        """Test PrepAction.from_args with invalid action."""
        prep_args = PrepActionResult(action="invalid action")

        with pytest.raises(ValidationError) as exc_info:
            PrepAction.from_args(prep_args)

        assert "Unknown action type: invalid action" in str(exc_info.value)

    def test_prep_action_from_args_all_types(self):
        """Test PrepAction.from_args with all valid action types."""
        test_actions = [
            ("remove column(s)", ActionType.REMOVE_COLUMNS),
            ("remove row(s)", ActionType.REMOVE_ROWS),
            ("transform column(s)", ActionType.TRANSFORM_COLUMNS),
            ("add new column", ActionType.ADD_NEW_COLUMN),
        ]

        for action_str, expected_type in test_actions:
            prep_args = PrepActionResult(action=action_str)
            prep_action = PrepAction.from_args(prep_args)
            assert prep_action.action_type == expected_type


class TestDescriptionParser:
    """Test DescriptionParser class."""

    def test_description_parser_initialization(self):
        """Test DescriptionParser initialization."""
        parser = DescriptionParser()
        assert parser is not None


class TestRemoveColumnsOperation:
    """Test RemoveColumnsOperation class."""

    def test_remove_columns_operation_valid(self):
        """Test removing columns with valid input."""
        operation = RemoveColumnsOperation()
        data = pl.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6], "col3": [7, 8, 9]})

        prep_args = PrepActionResult(action="remove column(s)", source_columns=["col2"])

        result_data, result_args = operation.execute(data, prep_args)

        # Check result data
        assert "col2" not in result_data.columns
        assert "col1" in result_data.columns
        assert "col3" in result_data.columns
        assert result_data.shape == (3, 2)

        # Check result args
        assert result_args.action == "remove column(s)"
        assert result_args.affected_count == 1
        assert result_args.source_columns == ["col2"]

    def test_remove_columns_operation_multiple(self):
        """Test removing multiple columns."""
        operation = RemoveColumnsOperation()
        data = pl.DataFrame(
            {
                "col1": [1, 2, 3],
                "col2": [4, 5, 6],
                "col3": [7, 8, 9],
                "col4": [10, 11, 12],
            }
        )

        prep_args = PrepActionResult(
            action="remove column(s)", source_columns=["col2", "col4"]
        )

        result_data, result_args = operation.execute(data, prep_args)

        assert "col2" not in result_data.columns
        assert "col4" not in result_data.columns
        assert result_data.shape == (3, 2)
        assert result_args.affected_count == 2

    def test_remove_columns_operation_missing_column(self):
        """Test removing non-existent column."""
        operation = RemoveColumnsOperation()
        data = pl.DataFrame({"col1": [1, 2, 3]})

        prep_args = PrepActionResult(
            action="remove column(s)", source_columns=["nonexistent"]
        )

        with pytest.raises(OperationError) as exc_info:
            operation.execute(data, prep_args)

        assert "Columns not found: ['nonexistent']" in str(exc_info.value)

    def test_validate_columns_exist_valid(self):
        """Test column validation with existing columns."""
        operation = RemoveColumnsOperation()
        data = pl.DataFrame({"col1": [1, 2], "col2": [3, 4]})

        # Should not raise exception
        operation._validate_columns_exist(data, ["col1", "col2"])

    def test_validate_columns_exist_invalid(self):
        """Test column validation with missing columns."""
        operation = RemoveColumnsOperation()
        data = pl.DataFrame({"col1": [1, 2]})

        with pytest.raises(OperationError) as exc_info:
            operation._validate_columns_exist(data, ["col1", "missing"])

        assert "Columns not found: ['missing']" in str(exc_info.value)


class TestRemoveRowsOperation:
    """Test RemoveRowsOperation class."""

    def test_remove_rows_by_index(self):
        """Test removing rows by index."""
        operation = RemoveRowsOperation()
        data = pl.DataFrame(
            {"col1": [1, 2, 3, 4, 5], "col2": ["a", "b", "c", "d", "e"]}
        )

        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by row index",
            value="1,3",  # Remove rows at index 1 and 3
        )

        result_data, result_args = operation.execute(data, prep_args)

        # Should have 3 rows remaining (removed indices 1 and 3)
        assert result_data.shape[0] == 3
        assert result_args.remaining_count == 3

    def test_remove_rows_by_condition(self):
        """Test removing rows by condition."""
        operation = RemoveRowsOperation()
        data = pl.DataFrame(
            {"age": [25, 30, 35, 40, 45], "name": ["A", "B", "C", "D", "E"]}
        )

        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["age"],
            condition="value is greater than",
            value=[35],
        )

        result_data, result_args = operation.execute(data, prep_args)

        # Should remove rows where age > 35 (2 rows)
        assert result_data.shape[0] == 3
        assert all(age <= 35 for age in result_data["age"].to_list())


class TestTransformColumnsOperation:
    """Test TransformColumnsOperation class."""

    def test_transform_columns_string_function(self):
        """Test transforming columns with string functions."""
        operation = TransformColumnsOperation()
        data = pl.DataFrame({"text": ["  hello  ", "  WORLD  ", "  Test  "]})

        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["text"], method="trim"
        )

        result_data, result_args = operation.execute(data, prep_args)

        # Check that whitespace was trimmed
        trimmed_values = result_data["text"].to_list()
        assert "hello" in trimmed_values
        assert "WORLD" in trimmed_values
        assert "Test" in trimmed_values

    def test_transform_columns_numeric_function(self):
        """Test transforming columns with numeric functions."""
        operation = TransformColumnsOperation()
        data = pl.DataFrame({"numbers": [1, 2, 3, 4, 5]})

        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["numbers"],
            method="add",
            value=[10],
        )

        result_data, result_args = operation.execute(data, prep_args)

        # Check that 10 was added to all values
        result_values = result_data["numbers"].to_list()
        expected_values = [11, 12, 13, 14, 15]
        assert result_values == expected_values

    def test_transform_columns_datetime_function(self):
        """Test transforming columns with datetime functions."""
        operation = TransformColumnsOperation()
        dates = pl.date_range(
            start=pl.date(2023, 1, 1),
            end=pl.date(2023, 1, 5),
            interval="1d",
            eager=True,
        )
        data = pl.DataFrame({"date_col": dates})

        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["date_col"], method="year"
        )

        result_data, result_args = operation.execute(data, prep_args)

        # Check that years were extracted
        years = result_data["date_col"].to_list()
        assert all(year == 2023 for year in years)


class TestAddNewColumnOperation:
    """Test AddNewColumnOperation class."""

    def test_add_new_column_constant(self):
        """Test adding a new column with constant value."""
        operation = AddNewColumnOperation()
        data = pl.DataFrame({"existing": [1, 2, 3]})

        prep_args = PrepActionResult(
            action="add new column",
            column_names="new_col",
            method="constant",
            value="test_value",
        )

        result_data, result_args = operation.execute(data, prep_args)

        assert "new_col" in result_data.columns
        assert result_data.shape[1] == 2
        assert all(val == "test_value" for val in result_data["new_col"].to_list())

    def test_add_new_column_calculation(self):
        """Test adding a new column with calculation."""
        operation = AddNewColumnOperation()
        data = pl.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6]})

        prep_args = PrepActionResult(
            action="add new column",
            column_names="sum_col",
            method="sum",
            source_columns=["col1", "col2"],
        )

        result_data, result_args = operation.execute(data, prep_args)

        assert "sum_col" in result_data.columns
        result_values = result_data["sum_col"].to_list()
        expected_values = [5, 7, 9]  # [1+4, 2+5, 3+6]
        assert result_values == expected_values

    def test_add_new_column_index(self):
        """Test adding index column."""
        operation = AddNewColumnOperation()
        data = pl.DataFrame({"existing": ["a", "b", "c"]})

        prep_args = PrepActionResult(
            action="add new column", column_names="index_col", method="index"
        )

        result_data, result_args = operation.execute(data, prep_args)

        assert "index_col" in result_data.columns
        index_values = result_data["index_col"].to_list()
        assert index_values == [0, 1, 2]


class TestPrepProcessor:
    """Test PrepProcessor class."""

    def test_prep_processor_initialization(self):
        """Test PrepProcessor initialization."""
        processor = PrepProcessor()

        assert ActionType.REMOVE_COLUMNS in processor.operation_handlers
        assert ActionType.REMOVE_ROWS in processor.operation_handlers
        assert ActionType.TRANSFORM_COLUMNS in processor.operation_handlers
        assert ActionType.ADD_NEW_COLUMN in processor.operation_handlers

    def test_execute_single_action_valid(self):
        """Test executing a single valid action."""
        processor = PrepProcessor()
        data = pl.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6]})

        prep_args = PrepActionResult(action="remove column(s)", source_columns=["col2"])
        action = PrepAction.from_args(prep_args)

        result_data, result_args = processor.execute_single_action(data, action)

        assert "col2" not in result_data.columns
        assert result_data.shape == (3, 1)

    def test_execute_single_action_invalid_type(self):
        """Test executing action with invalid type."""
        processor = PrepProcessor()
        data = pl.DataFrame({"col1": [1, 2, 3]})

        # Create action with invalid type manually
        action = PrepAction(
            action_type=None,  # Invalid type
            prep_args=PrepActionResult(action="invalid"),
        )

        with pytest.raises(ValidationError) as exc_info:
            processor.execute_single_action(data, action)

        assert "No handler for action type: None" in str(exc_info.value)

    def test_execute_all_actions_success(self):
        """Test executing multiple actions successfully."""
        processor = PrepProcessor()
        data = pl.DataFrame(
            {"col1": [1, 2, 3, 4], "col2": [5, 6, 7, 8], "col3": [9, 10, 11, 12]}
        )

        # Create multiple actions
        actions = [
            PrepAction.from_args(
                PrepActionResult(action="remove column(s)", source_columns=["col3"])
            ),
            PrepAction.from_args(
                PrepActionResult(
                    action="add new column",
                    column_names="new_col",
                    method="constant",
                    value="test",
                )
            ),
        ]

        result_data = processor.execute_all_actions(data, actions)

        # Check final result
        assert "col3" not in result_data.columns
        assert "new_col" in result_data.columns
        assert result_data.shape[1] == 3  # col1, col2, new_col

    def test_execute_all_actions_failure(self):
        """Test executing actions with failure."""
        processor = PrepProcessor()
        data = pl.DataFrame({"col1": [1, 2, 3]})

        # Create action that will fail
        actions = [
            PrepAction.from_args(
                PrepActionResult(
                    action="remove column(s)",
                    source_columns=["nonexistent"],  # This will cause failure
                )
            )
        ]

        with pytest.raises(OperationError) as exc_info:
            processor.execute_all_actions(data, actions)

        assert "Failed to execute action" in str(exc_info.value)

    def test_execute_all_actions_empty_list(self):
        """Test executing with empty action list."""
        processor = PrepProcessor()
        data = pl.DataFrame({"col1": [1, 2, 3]})

        result_data = processor.execute_all_actions(data, [])

        # Should return original data unchanged
        assert result_data.equals(data)


class TestPrepApplyAction:
    """Test prep_apply_action function."""

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    @patch("streamlit.success")
    def test_prep_apply_action_new_action(self, mock_success, mock_save, mock_get):
        """Test applying a new action."""
        # Mock data
        mock_log = pl.DataFrame({"prep_args": []})
        mock_data = pl.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6]})

        mock_get.side_effect = [
            mock_log,
            mock_data,
        ]  # First call gets log, second gets prepared data

        prep_args = PrepActionResult(action="remove column(s)", source_columns=["col2"])

        prep_apply_action("test_project", "test_alias", prep_args)

        # Verify database operations were called
        assert mock_get.call_count == 2
        mock_save.assert_called()

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_prep_apply_action_reapply_all(self, mock_save, mock_get):
        """Test re-applying all actions from log."""
        # Mock log with existing actions
        mock_log = pl.DataFrame(
            {
                "prep_args": [
                    str(
                        {
                            "action": "remove column(s)",
                            "source_columns": ["col3"],
                            "column_names": None,
                            "affected_count": None,
                            "remaining_count": None,
                            "value": None,
                            "method": None,
                            "condition": None,
                            "failed_count": None,
                            "additional_info": None,
                        }
                    )
                ]
            }
        )
        mock_raw_data = pl.DataFrame(
            {"col1": [1, 2, 3], "col2": [4, 5, 6], "col3": [7, 8, 9]}
        )

        mock_get.side_effect = [mock_log, mock_raw_data]

        # Call without prep_args to trigger re-apply
        prep_apply_action("test_project", "test_alias", prep_args=None)

        # Should have called get_table twice (log and raw data)
        assert mock_get.call_count == 2
        mock_save.assert_called()

    @patch("datasure.processing.prep.duckdb_get_table")
    def test_prep_apply_action_empty_log_reapply(self, mock_get):
        """Test re-applying with empty log."""
        # Mock empty log
        mock_log = pl.DataFrame({"prep_args": []})
        mock_get.return_value = mock_log

        # Should return None for empty log
        result = prep_apply_action("test_project", "test_alias", prep_args=None)
        assert result is None

    @patch("datasure.processing.prep.duckdb_get_table")
    def test_prep_apply_action_ast_literal_eval(self, mock_get):
        """Test handling of string prep_args that need ast.literal_eval."""
        # Mock log with string representation of prep_args
        prep_args_str = str(
            {
                "action": "remove column(s)",
                "source_columns": ["col2"],
                "column_names": None,
                "affected_count": None,
                "remaining_count": None,
                "value": None,
                "method": None,
                "condition": None,
                "failed_count": None,
                "additional_info": None,
            }
        )

        mock_log = pl.DataFrame({"prep_args": [prep_args_str]})
        mock_raw_data = pl.DataFrame({"col1": [1, 2, 3], "col2": [4, 5, 6]})

        mock_get.side_effect = [mock_log, mock_raw_data]

        # Should successfully parse string prep_args
        with patch("datasure.processing.prep.duckdb_save_table"):
            prep_apply_action("test_project", "test_alias", prep_args=None)

        # Should complete without error


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_workflow_remove_columns(self):
        """Test complete workflow for removing columns."""
        # Create test data
        data = pl.DataFrame(
            {"keep_me": [1, 2, 3], "remove_me": [4, 5, 6], "also_keep": [7, 8, 9]}
        )

        # Create action
        prep_args = PrepActionResult(
            action="remove column(s)", source_columns=["remove_me"]
        )
        action = PrepAction.from_args(prep_args)

        # Execute with processor
        processor = PrepProcessor()
        result_data, result_args = processor.execute_single_action(data, action)

        # Verify results
        assert "remove_me" not in result_data.columns
        assert "keep_me" in result_data.columns
        assert "also_keep" in result_data.columns
        assert result_data.shape == (3, 2)

    def test_full_workflow_multiple_operations(self):
        """Test workflow with multiple operations."""
        data = pl.DataFrame(
            {
                "col1": [1, 2, 3, 4, 5],
                "col2": [10, 20, 30, 40, 50],
                "col3": ["a", "b", "c", "d", "e"],
            }
        )

        processor = PrepProcessor()

        # Step 1: Add constant column
        action1 = PrepAction.from_args(
            PrepActionResult(
                action="add new column",
                column_names="constant_col",
                method="constant",
                value="test",
            )
        )

        result_data, _ = processor.execute_single_action(data, action1)
        assert "constant_col" in result_data.columns

        # Step 2: Remove original column
        action2 = PrepAction.from_args(
            PrepActionResult(action="remove column(s)", source_columns=["col3"])
        )

        result_data, _ = processor.execute_single_action(result_data, action2)
        assert "col3" not in result_data.columns
        assert result_data.shape[1] == 3  # col1, col2, constant_col

    def test_error_propagation(self):
        """Test that errors are properly propagated through the system."""
        processor = PrepProcessor()
        data = pl.DataFrame({"col1": [1, 2, 3]})

        # Create action that will fail
        action = PrepAction.from_args(
            PrepActionResult(
                action="remove column(s)", source_columns=["nonexistent_column"]
            )
        )

        with pytest.raises(OperationError):
            processor.execute_single_action(data, action)

    def test_validation_chain(self):
        """Test validation error chain from PrepAction to operations."""
        # Test invalid action type
        with pytest.raises(ValidationError):
            PrepAction.from_args(PrepActionResult(action="invalid_action"))
