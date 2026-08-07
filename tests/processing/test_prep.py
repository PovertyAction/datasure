"""Comprehensive tests for the prep module."""

import json
from unittest.mock import patch

import polars as pl
import pytest

from datasure.models.enums import (
    PrepActions,
)
from datasure.processing.prep import (
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
    _append_to_prep_log,
    _apply_single_action,
    _convert_prep_args_to_string,
    _create_log_entry,
    _generate_action_description,
    _parse_prep_log_to_actions,
    _reapply_all_actions,
    prep_apply_action,
)
from datasure.utils.prep_utils import PrepActionResult


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests.
    """
    pass


# === EXCEPTION TESTS === #


class TestPrepExceptions:
    """Test custom exception classes."""

    def test_prep_error_base_exception(self):
        """Test that PrepError is a base exception with correct message."""
        error = PrepError("Base error")
        assert str(error) == "Base error"
        assert isinstance(error, Exception)

    def test_validation_error_inheritance(self):
        """Test that ValidationError inherits from PrepError."""
        error = ValidationError("Validation failed")
        assert isinstance(error, PrepError)

    def test_operation_error_inheritance(self):
        """Test that OperationError inherits from PrepError."""
        error = OperationError("Operation failed")
        assert isinstance(error, PrepError)


# === PREP ACTION TESTS === #


class TestPrepAction:
    """Test PrepAction dataclass."""

    def test_from_args_valid(self):
        """Test that from_args creates a PrepAction with correct action type."""
        prep_args = PrepActionResult(action="remove column(s)")
        action = PrepAction.from_args(prep_args)
        assert action.action_type == PrepActions.remove_column
        assert action.prep_args == prep_args

    def test_from_args_all_types(self):
        """Test that from_args maps all action strings to correct enum types."""
        cases = [
            ("remove column(s)", PrepActions.remove_column),
            ("remove row(s)", PrepActions.remove_row),
            ("transform column(s)", PrepActions.transform_column),
            ("add new column", PrepActions.add_column),
        ]
        for action_str, expected in cases:
            action = PrepAction.from_args(PrepActionResult(action=action_str))
            assert action.action_type == expected

    def test_from_args_invalid(self):
        """Test that from_args raises ValidationError for unknown action types."""
        with pytest.raises(ValidationError, match="Unknown action type"):
            PrepAction.from_args(PrepActionResult(action="invalid"))


# === DESCRIPTION PARSER TESTS === #


class TestDescriptionParser:
    """Test DescriptionParser static methods."""

    def test_parse_column_list_valid(self):
        """Test that parse_column_list extracts columns from bracket notation."""
        result = DescriptionParser.parse_column_list("Remove [col1, col2, col3]")
        assert result == ["col1", "col2", "col3"]

    def test_parse_column_list_quoted(self):
        """Test that parse_column_list strips quotes from column names."""
        result = DescriptionParser.parse_column_list("Remove ['col1', 'col2']")
        assert result == ["col1", "col2"]

    def test_parse_column_list_no_brackets(self):
        """Test that parse_column_list raises ValidationError without brackets."""
        with pytest.raises(ValidationError, match="No column specification"):
            DescriptionParser.parse_column_list("no brackets here")

    def test_parse_column_list_empty(self):
        """Test that parse_column_list raises ValidationError for empty brackets."""
        with pytest.raises(ValidationError, match="No column specification"):
            DescriptionParser.parse_column_list("Remove []")

    def test_parse_quoted_content(self):
        """Test that parse_quoted_content extracts single-quoted strings."""
        result = DescriptionParser.parse_quoted_content("replace 'old' with 'new'")
        assert result == ["old", "new"]

    def test_parse_quoted_content_no_quotes(self):
        """Test that parse_quoted_content raises ValidationError without quotes."""
        with pytest.raises(ValidationError, match="No quoted content"):
            DescriptionParser.parse_quoted_content("no quotes here")

    def test_parse_numeric_value_integer(self):
        """Test that parse_numeric_value extracts an integer value."""
        result = DescriptionParser.parse_numeric_value("add 42")
        assert result == 42
        assert isinstance(result, int)

    def test_parse_numeric_value_float(self):
        """Test that parse_numeric_value extracts a float value."""
        result = DescriptionParser.parse_numeric_value("multiply 3.14")
        assert result == 3.14
        assert isinstance(result, float)

    def test_parse_numeric_value_none(self):
        """Test parse_numeric_value raises error with no number."""
        with pytest.raises(ValidationError, match="No numeric value"):
            DescriptionParser.parse_numeric_value("no number")

    def test_parse_value_list_mixed(self):
        """Test that parse_value_list handles mixed int, float, and string values."""
        result = DescriptionParser.parse_value_list("values [1, 2.5, hello]")
        assert result == [1, 2.5, "hello"]

    def test_parse_value_list_no_brackets(self):
        """Test that parse_value_list raises ValidationError without brackets."""
        with pytest.raises(ValidationError, match="No value list"):
            DescriptionParser.parse_value_list("no brackets")


# === REMOVE COLUMNS OPERATION TESTS === #


class TestRemoveColumnsOperation:
    """Test RemoveColumnsOperation."""

    def test_remove_single_column(self):
        """Test Remove single column."""
        op = RemoveColumnsOperation()
        data = pl.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
        prep_args = PrepActionResult(action="remove column(s)", source_columns=["b"])
        result, args = op.execute(data, prep_args)
        assert "b" not in result.columns
        assert result.shape == (2, 2)
        assert args.affected_count == 1

    def test_remove_multiple_columns(self):
        """Test Remove multiple columns."""
        op = RemoveColumnsOperation()
        data = pl.DataFrame({"a": [1], "b": [2], "c": [3], "d": [4]})
        prep_args = PrepActionResult(
            action="remove column(s)", source_columns=["b", "d"]
        )
        result, args = op.execute(data, prep_args)
        assert set(result.columns) == {"a", "c"}
        assert args.affected_count == 2

    def test_remove_nonexistent_column(self):
        """Test Remove nonexistent column."""
        op = RemoveColumnsOperation()
        data = pl.DataFrame({"a": [1]})
        prep_args = PrepActionResult(
            action="remove column(s)", source_columns=["nonexistent"]
        )
        with pytest.raises(OperationError, match="Columns not found"):
            op.execute(data, prep_args)

    def test_remove_columns_partial_missing(self):
        """Removing 4 columns where 2 no longer exist removes the other 2."""
        op = RemoveColumnsOperation()
        data = pl.DataFrame({"a": [1], "b": [2], "c": [3], "d": [4]})
        prep_args = PrepActionResult(
            action="remove column(s)",
            source_columns=["a", "c", "missing1", "missing2"],
        )
        result, args = op.execute(data, prep_args)
        assert set(result.columns) == {"b", "d"}
        assert args.affected_count == 2
        assert args.failed_count == 2
        assert args.source_columns == ["a", "c"]
        assert "missing1" in args.additional_info
        assert "missing2" in args.additional_info

    def test_validate_columns_exist_valid(self):
        """Test Validate columns exist valid."""
        op = RemoveColumnsOperation()
        data = pl.DataFrame({"a": [1], "b": [2]})
        op._validate_columns_exist(data, ["a", "b"])

    def test_validate_columns_exist_invalid(self):
        """Test Validate columns exist invalid."""
        op = RemoveColumnsOperation()
        data = pl.DataFrame({"a": [1]})
        with pytest.raises(OperationError, match="Columns not found"):
            op._validate_columns_exist(data, ["a", "missing"])


# === REMOVE ROWS OPERATION TESTS === #


class TestRemoveRowsOperation:
    """Test RemoveRowsOperation."""

    def test_remove_by_index_single(self):
        """Test Remove by index single."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [10, 20, 30, 40, 50]})
        prep_args = PrepActionResult(
            action="remove row(s)", method="by row index", value=["1", "3"]
        )
        result, args = op.execute(data, prep_args)
        assert result.shape[0] == 3
        assert args.affected_count == 2

    def test_remove_by_index_range(self):
        """Test Remove by index range."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": list(range(10))})
        prep_args = PrepActionResult(
            action="remove row(s)", method="by row index", value=["2:4"]
        )
        result, _ = op.execute(data, prep_args)
        assert result.shape[0] == 7

    def test_remove_by_index_skip_comma_and_none(self):
        """Test Remove by index skip comma and none."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [1, 2, 3, 4, 5]})
        prep_args = PrepActionResult(
            action="remove row(s)", method="by row index", value=["0", ",", None, "2"]
        )
        result, _ = op.execute(data, prep_args)
        assert result.shape[0] == 3

    def test_remove_by_unknown_method(self):
        """Test Remove by unknown method."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [1, 2]})
        prep_args = PrepActionResult(
            action="remove row(s)", method="unknown_method", value=None
        )
        with pytest.raises(ValidationError, match="Unknown removal method"):
            op.execute(data, prep_args)

    def test_remove_by_condition_missing(self):
        """Test Remove by condition missing."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [1, None, 3, None, 5]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is missing",
        )
        result, _ = op.execute(data, prep_args)
        assert result.shape[0] == 3

    def test_remove_by_condition_not_missing(self):
        """Test Remove by condition not missing."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [1, None, 3, None, 5]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is not missing",
        )
        result, _ = op.execute(data, prep_args)
        assert result.shape[0] == 2

    def test_remove_by_condition_equal_to(self):
        """Test Remove by condition equal to."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [1, 2, 3, 2, 5]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is equal to",
            value=[2],
        )
        result, _ = op.execute(data, prep_args)
        # equal_to keeps matching rows (removes non-matching)
        assert result.shape[0] == 2

    def test_remove_by_condition_not_equal_to(self):
        """Test Remove by condition not equal to."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [1, 2, 3, 2, 5]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is not equal to",
            value=[2],
        )
        result, _ = op.execute(data, prep_args)
        # not_equal_to removes matching rows
        assert result.shape[0] == 3

    def test_remove_by_condition_greater_than(self):
        """Test Remove by condition greater than."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [10, 20, 30, 40, 50]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is greater than",
            value=[30],
        )
        result, _ = op.execute(data, prep_args)
        assert all(v <= 30 for v in result["a"].to_list())

    def test_remove_by_condition_greater_than_or_equal_to(self):
        """Test Remove by condition greater than or equal to."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [10, 20, 30, 40, 50]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is greater than or equal to",
            value=[30],
        )
        result, _ = op.execute(data, prep_args)
        assert all(v < 30 for v in result["a"].to_list())

    def test_remove_by_condition_less_than(self):
        """Test Remove by condition less than."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [10, 20, 30, 40, 50]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is less than",
            value=[30],
        )
        result, _ = op.execute(data, prep_args)
        assert all(v >= 30 for v in result["a"].to_list())

    def test_remove_by_condition_less_than_or_equal_to(self):
        """Test Remove by condition less than or equal to."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [10, 20, 30, 40, 50]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is less than or equal to",
            value=[30],
        )
        result, _ = op.execute(data, prep_args)
        assert all(v > 30 for v in result["a"].to_list())

    def test_remove_by_condition_between(self):
        """Test Remove by condition between."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [10, 20, 30, 40, 50]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is between",
            value=[20, 40],
        )
        result, _ = op.execute(data, prep_args)
        # "between" keeps rows OUTSIDE the range (removes rows inside)
        values = result["a"].to_list()
        assert all(v < 20 or v > 40 for v in values)

    def test_remove_by_condition_not_between(self):
        """Test Remove by condition not between."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [10, 20, 30, 40, 50]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is not between",
            value=[20, 40],
        )
        result, _ = op.execute(data, prep_args)
        values = result["a"].to_list()
        assert all(20 <= v <= 40 for v in values)

    def test_remove_by_condition_between_bad_values(self):
        """Test Remove by condition between bad values."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [1, 2, 3]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is between",
            value=[1, 2, 3],
        )
        with pytest.raises(ValidationError, match="Expected 2 values"):
            op.execute(data, prep_args)

    def test_remove_by_condition_like(self):
        """Test Remove by condition like."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": ["hello", "world", "help", "test"]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is like",
            value="hel",
        )
        result, _ = op.execute(data, prep_args)
        # "like" removes matching rows (keeps non-matching)
        values = result["a"].to_list()
        assert "hello" not in values
        assert "help" not in values

    def test_remove_by_condition_not_like(self):
        """Test Remove by condition not like."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": ["hello", "world", "help", "test"]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is not like",
            value="hel",
        )
        result, _ = op.execute(data, prep_args)
        # "not like" keeps matching rows
        values = result["a"].to_list()
        assert "hello" in values
        assert "help" in values

    def test_remove_by_condition_unknown(self):
        """Test Remove by condition unknown."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [1, 2, 3]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="unknown condition",
        )
        with pytest.raises(ValidationError, match="Unknown condition"):
            op.execute(data, prep_args)

    def test_remove_by_condition_missing_column(self):
        """Test Remove by condition missing column."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [1, 2]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["nonexistent"],
            condition="value is missing",
        )
        with pytest.raises(OperationError):
            op.execute(data, prep_args)

    def test_filter_by_comparison_single_value(self):
        """Test comparison with single value (not a list)."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [10, 20, 30]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is greater than",
            value=20,
        )
        result, _ = op.execute(data, prep_args)
        assert all(v <= 20 for v in result["a"].to_list())

    def test_filter_by_equality_with_list(self):
        """Test equality filter with list of values."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [1, 2, 3, 4, 5]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is equal to",
            value=[2, 4],
        )
        result, _ = op.execute(data, prep_args)
        assert sorted(result["a"].to_list()) == [2, 4]

    def test_filter_by_range_single_value(self):
        """Test range filter with single value (not a list) - uses [val, val]."""
        op = RemoveRowsOperation()
        data = pl.DataFrame({"a": [10, 20, 30]})
        prep_args = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            source_columns=["a"],
            condition="value is between",
            value=20,
        )
        result, _ = op.execute(data, prep_args)
        # between with single value becomes [20, 20], keeps outside
        values = result["a"].to_list()
        assert all(v < 20 or v > 20 for v in values)


# === TRANSFORM COLUMNS OPERATION TESTS === #


class TestTransformColumnsOperation:
    """Test TransformColumnsOperation."""

    # --- String operations ---

    def test_trim(self):
        """Test Trim."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"text": ["  hello  ", "  world  "]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["text"], method="trim"
        )
        result, _ = op.execute(data, prep_args)
        assert result["text"].to_list() == ["hello", "world"]

    def test_lowercase(self):
        """Test Lowercase."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"text": ["HELLO", "WORLD"]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["text"], method="lowercase"
        )
        result, _ = op.execute(data, prep_args)
        assert result["text"].to_list() == ["hello", "world"]

    def test_uppercase(self):
        """Test Uppercase."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"text": ["hello", "world"]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["text"], method="uppercase"
        )
        result, _ = op.execute(data, prep_args)
        assert result["text"].to_list() == ["HELLO", "WORLD"]

    def test_string_to_number(self):
        """Test String to number."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"text": ["1", "2", "3"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["text"],
            method="string to number",
        )
        result, _ = op.execute(data, prep_args)
        assert result["text"].to_list() == [1.0, 2.0, 3.0]
        assert result["text"].dtype == pl.Float64

    # --- Math operations ---

    def test_floor(self):
        """Test Floor."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"num": [1.7, 2.3, 3.9]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["num"], method="floor"
        )
        result, _ = op.execute(data, prep_args)
        assert result["num"].to_list() == [1.0, 2.0, 3.0]

    def test_ceil(self):
        """Test Ceil."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"num": [1.1, 2.5, 3.9]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["num"], method="ceil"
        )
        result, _ = op.execute(data, prep_args)
        assert result["num"].to_list() == [2.0, 3.0, 4.0]

    def test_round(self):
        """Test Round."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"num": [1.5, 2.3, 3.7]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["num"], method="round"
        )
        result, _ = op.execute(data, prep_args)
        assert result["num"].to_list() == [2.0, 2.0, 4.0]

    def test_abs(self):
        """Test Abs."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"num": [-1, 2, -3]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["num"],
            method="absolute value",
        )
        result, _ = op.execute(data, prep_args)
        assert result["num"].to_list() == [1, 2, 3]

    # --- Arithmetic operations ---

    def test_add(self):
        """Test Add."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"num": [1, 2, 3]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["num"],
            method="add",
            value=[10],
        )
        result, _ = op.execute(data, prep_args)
        assert result["num"].to_list() == [11, 12, 13]

    def test_subtract(self):
        """Test Subtract."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"num": [10, 20, 30]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["num"],
            method="subtract",
            value=[5],
        )
        result, _ = op.execute(data, prep_args)
        assert result["num"].to_list() == [5, 15, 25]

    def test_multiply(self):
        """Test Multiply."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"num": [1, 2, 3]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["num"],
            method="multiply",
            value=[3],
        )
        result, _ = op.execute(data, prep_args)
        assert result["num"].to_list() == [3, 6, 9]

    def test_divide(self):
        """Test Divide."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"num": [10, 20, 30]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["num"],
            method="divide",
            value=[10],
        )
        result, _ = op.execute(data, prep_args)
        assert result["num"].to_list() == [1.0, 2.0, 3.0]

    # --- DateTime operations ---

    def test_datetime_year(self):
        """Test Datetime year."""
        op = TransformColumnsOperation()
        dates = pl.date_range(
            start=pl.date(2023, 1, 1),
            end=pl.date(2023, 1, 3),
            interval="1d",
            eager=True,
        )
        data = pl.DataFrame({"d": dates})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["d"], method="year"
        )
        result, _ = op.execute(data, prep_args)
        assert all(y == 2023 for y in result["d"].to_list())

    def test_datetime_month(self):
        """Test Datetime month."""
        op = TransformColumnsOperation()
        dates = pl.date_range(
            start=pl.date(2023, 3, 1),
            end=pl.date(2023, 3, 3),
            interval="1d",
            eager=True,
        )
        data = pl.DataFrame({"d": dates})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["d"], method="month of year"
        )
        result, _ = op.execute(data, prep_args)
        assert all(m == 3 for m in result["d"].to_list())

    def test_datetime_day_of_month(self):
        """Test Datetime day of month."""
        op = TransformColumnsOperation()
        dates = pl.date_range(
            start=pl.date(2023, 1, 15),
            end=pl.date(2023, 1, 17),
            interval="1d",
            eager=True,
        )
        data = pl.DataFrame({"d": dates})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["d"], method="day of month"
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].to_list() == [15, 16, 17]

    def test_datetime_day_of_week(self):
        """Test Datetime day of week."""
        from datetime import date

        op = TransformColumnsOperation()
        data = pl.DataFrame({"d": [date(2023, 1, 2)]})  # Monday
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["d"], method="day of week"
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].to_list()[0] == 1  # Monday = 1

    def test_datetime_day_of_year(self):
        """Test Datetime day of year."""
        from datetime import date

        op = TransformColumnsOperation()
        data = pl.DataFrame({"d": [date(2023, 2, 1)]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["d"], method="day of year"
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].to_list()[0] == 32

    def test_datetime_week_of_year(self):
        """Test Datetime week of year."""
        from datetime import date

        op = TransformColumnsOperation()
        data = pl.DataFrame({"d": [date(2023, 1, 15)]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["d"], method="week of year"
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].to_list()[0] > 0

    def test_datetime_quarter(self):
        """Test Datetime quarter."""
        from datetime import date

        op = TransformColumnsOperation()
        data = pl.DataFrame({"d": [date(2023, 4, 1)]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["d"],
            method="quarter of year",
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].to_list()[0] == 2

    def test_datetime_date_extraction(self):
        """Test Datetime date extraction."""
        from datetime import date, datetime

        op = TransformColumnsOperation()
        data = pl.DataFrame({"d": [datetime(2023, 1, 15, 10, 30, 0)]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["d"], method="date"
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].to_list()[0] == date(2023, 1, 15)

    def test_datetime_hour(self):
        """Test Datetime hour."""
        op = TransformColumnsOperation()
        from datetime import datetime

        data = pl.DataFrame({"d": [datetime(2023, 1, 1, 14, 30, 45)]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["d"], method="hour"
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].to_list()[0] == 14

    def test_datetime_minute(self):
        """Test Datetime minute."""
        op = TransformColumnsOperation()
        from datetime import datetime

        data = pl.DataFrame({"d": [datetime(2023, 1, 1, 14, 30, 45)]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["d"], method="minute"
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].to_list()[0] == 30

    def test_datetime_second(self):
        """Test Datetime second."""
        op = TransformColumnsOperation()
        from datetime import datetime

        data = pl.DataFrame({"d": [datetime(2023, 1, 1, 14, 30, 45)]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["d"], method="second"
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].to_list()[0] == 45

    # --- String to datetime ---

    def test_string_to_date_iso(self):
        """Test String to date iso."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"d": ["2023-01-15", "2023-02-20"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["d"],
            method="string to date",
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].dtype == pl.Datetime

    def test_string_to_datetime_slash_format(self):
        """Test String to datetime slash format."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"d": ["01/15/2023 10:30:00", "02/20/2023 14:00:00"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["d"],
            method="string to datetime",
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].dtype == pl.Datetime

    def test_string_to_datetime_slash_format_no_seconds(self):
        """A timestamp with no seconds (e.g. spreadsheet exports) still parses."""
        from datetime import datetime

        op = TransformColumnsOperation()
        data = pl.DataFrame({"d": ["3/15/2026 17:28", "4/1/2026 9:05"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["d"],
            method="string to datetime",
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].dtype == pl.Datetime
        assert result["d"].to_list()[0] == datetime(2026, 3, 15, 17, 28)

    def test_string_to_datetime_iso_format_no_seconds(self):
        """ISO-shaped timestamps with no seconds also parse."""
        from datetime import datetime

        op = TransformColumnsOperation()
        data = pl.DataFrame({"d": ["2026-03-15 17:28", "2026-04-01 09:05"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["d"],
            method="string to datetime",
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].dtype == pl.Datetime
        assert result["d"].to_list()[0] == datetime(2026, 3, 15, 17, 28)

    def test_string_to_datetime_stata_format_no_seconds(self):
        """Stata-shaped timestamps with no seconds also parse."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"d": ["18aug2025 19:49", "20sep2025 10:00"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["d"],
            method="string to datetime",
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].dtype == pl.Datetime

    def test_string_to_datetime_stata_format(self):
        """Test String to datetime stata format."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"d": ["18aug2025 19:49:00", "20sep2025 10:00:00"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["d"],
            method="string to datetime",
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].dtype == pl.Datetime

    def test_string_to_datetime_unsupported_format(self):
        """Test String to datetime unsupported format."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"d": ["not-a-date", "also-not-a-date"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["d"],
            method="string to datetime",
        )
        with pytest.raises(ValidationError, match="Failed to parse datetime"):
            op.execute(data, prep_args)

    # --- Get dummies ---

    def test_get_dummies(self):
        """Test Get dummies."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"cat": ["a", "b", "a", "c"]})
        prep_args = PrepActionResult(
            action="transform column(s)", source_columns=["cat"], method="get dummies"
        )
        result, _ = op.execute(data, prep_args)
        assert "cat" not in result.columns
        assert result.width > 1

    # --- String replace ---

    def test_string_replace(self):
        """Test String replace."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"text": ["hello world", "hello there"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["text"],
            method="replace by replacing",
            value=["hello", "hi"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["text"].to_list() == ["hi world", "hi there"]

    def test_string_replace_bad_value(self):
        """Test String replace bad value."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"text": ["hello"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["text"],
            method="replace by replacing",
            value=["only_one"],
        )
        with pytest.raises(ValidationError, match="Invalid replace format"):
            op.execute(data, prep_args)

    # --- Substring ---

    def test_substring(self):
        """Test Substring."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"text": ["abcdef", "ghijkl"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["text"],
            method="substring",
            value=[1, 4],
        )
        result, _ = op.execute(data, prep_args)
        assert result["text"].to_list() == ["bcd", "hij"]

    def test_substring_bad_value(self):
        """Test Substring bad value."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"text": ["abc"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["text"],
            method="substring",
            value=[1],
        )
        with pytest.raises(ValidationError, match="Invalid description format"):
            op.execute(data, prep_args)

    def test_substring_empty_value(self):
        """Test Substring empty value."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"text": ["abc"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["text"],
            method="substring",
            value=[],
        )
        with pytest.raises(ValidationError, match="Invalid description format"):
            op.execute(data, prep_args)

    # --- Pattern extract ---

    def test_pattern_extract(self):
        """Test Pattern extract."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"text": ["abc123", "def456"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["text"],
            method="extract pattern",
            value=[r"(\d+)"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["text"].to_list() == ["123", "456"]

    def test_pattern_extract_invalid_regex(self):
        """Test Pattern extract invalid regex."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"text": ["abc"]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["text"],
            method="extract pattern",
            value=["[invalid"],
        )
        with pytest.raises(ValidationError, match="Invalid regex pattern"):
            op.execute(data, prep_args)

    # --- Unknown transformation ---

    def test_unknown_transformation(self):
        """Test Unknown transformation."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"a": [1, 2]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["a"],
            method="unknown_func",
        )
        with pytest.raises(ValidationError, match="Unknown transformation function"):
            op.execute(data, prep_args)

    # --- Column validation ---

    def test_transform_missing_column(self):
        """Test Transform missing column."""
        op = TransformColumnsOperation()
        data = pl.DataFrame({"a": [1, 2]})
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["nonexistent"],
            method="trim",
        )
        with pytest.raises(OperationError):
            op.execute(data, prep_args)


# === ADD NEW COLUMN OPERATION TESTS === #


class TestAddNewColumnOperation:
    """Test AddNewColumnOperation."""

    def test_add_constant_string(self):
        """Test Add constant string."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1, 2, 3]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="new",
            method="constant",
            value="hello",
        )
        result, _args = op.execute(data, prep_args)
        assert "new" in result.columns
        assert all(v == "hello" for v in result["new"].to_list())

    def test_add_constant_integer(self):
        """Test Add constant integer."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1, 2, 3]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="new",
            method="constant",
            value="42",
        )
        result, _ = op.execute(data, prep_args)
        assert all(v == 42 for v in result["new"].to_list())

    def test_add_constant_float(self):
        """Test Add constant float."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1, 2, 3]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="new",
            method="constant",
            value="3.14",
        )
        result, _ = op.execute(data, prep_args)
        assert all(abs(v - 3.14) < 0.001 for v in result["new"].to_list())

    def test_add_index_column(self):
        """Test Add index column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": ["x", "y", "z"]})
        prep_args = PrepActionResult(
            action="add new column", column_names="idx", method="index"
        )
        result, _ = op.execute(data, prep_args)
        assert result["idx"].to_list() == [0, 1, 2]

    @patch("datasure.processing.prep.st")
    def test_add_uuid_column(self, mock_st):
        """Test Add uuid column."""
        mock_st.session_state.st_project_id = "test123"
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1, 2, 3]})
        prep_args = PrepActionResult(
            action="add new column", column_names="uid", method="uuid"
        )
        result, _ = op.execute(data, prep_args)
        assert "uid" in result.columns
        uids = result["uid"].to_list()
        assert len(set(uids)) == 3  # All unique

    def test_add_random_column(self):
        """Test Add random column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1, 2, 3]})
        prep_args = PrepActionResult(
            action="add new column", column_names="rand", method="random"
        )
        result, _ = op.execute(data, prep_args)
        assert "rand" in result.columns
        assert all(0 <= v <= 1 for v in result["rand"].to_list())

    # --- Computed columns ---

    def test_add_sum_column(self):
        """Test Add sum column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="total",
            method="sum",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["total"].to_list() == [5, 7, 9]

    def test_add_mean_column(self):
        """Test Add mean column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [10.0, 20.0], "b": [30.0, 40.0]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="avg",
            method="mean",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["avg"].to_list() == [20.0, 30.0]

    def test_add_max_column(self):
        """Test Add max column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1, 5, 3], "b": [4, 2, 6]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="mx",
            method="max",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["mx"].to_list() == [4, 5, 6]

    def test_add_min_column(self):
        """Test Add min column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1, 5, 3], "b": [4, 2, 6]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="mn",
            method="min",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["mn"].to_list() == [1, 2, 3]

    def test_add_median_column(self):
        """Test Add median column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0], "c": [5.0, 6.0]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="med",
            method="median",
            source_columns=["a", "b", "c"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["med"].to_list() == [3.0, 4.0]

    def test_add_std_column(self):
        """Test Add std column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="sd",
            method="std",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["sd"].to_list()[0] is not None

    def test_add_var_column(self):
        """Test Add var column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="v",
            method="var",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert "v" in result.columns

    def test_add_first_column(self):
        """Test Add first column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="f",
            method="first",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["f"].to_list() == [1.0, 2.0]

    def test_add_last_column(self):
        """Test Add last column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1.0, 2.0], "b": [3.0, 4.0]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="l",
            method="last",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["l"].to_list() == [3.0, 4.0]

    def test_add_count_column(self):
        """Test Add count column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1.0, None], "b": [3.0, 4.0]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="cnt",
            method="count",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["cnt"].to_list() == [2, 2]

    def test_add_nunique_column(self):
        """Test Add nunique column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1.0, 1.0], "b": [1.0, 2.0]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="nu",
            method="nunique",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert "nu" in result.columns

    def test_add_product_column(self):
        """Test Add product column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [2, 3], "b": [4, 5]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="prod",
            method="product",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["prod"].to_list() == [8, 15]

    def test_add_quotient_column(self):
        """Test Add quotient column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [10.0, 20.0], "b": [2.0, 5.0]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="q",
            method="quotient",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["q"].to_list() == [5.0, 4.0]

    def test_add_diff_column(self):
        """Test Add diff column."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [10, 20], "b": [3, 8]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="d",
            method="diff",
            source_columns=["a", "b"],
        )
        result, _ = op.execute(data, prep_args)
        assert result["d"].to_list() == [7, 12]

    def test_quotient_requires_two_columns(self):
        """Test Quotient requires two columns."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1], "b": [2], "c": [3]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="q",
            method="quotient",
            source_columns=["a", "b", "c"],
        )
        with pytest.raises(ValidationError, match="exactly two columns"):
            op.execute(data, prep_args)

    def test_unknown_aggregation_function(self):
        """Test Unknown aggregation function."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1, 2]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="x",
            method="unknown_func",
            source_columns=["a"],
        )
        with pytest.raises(ValidationError, match="Unknown aggregation function"):
            op.execute(data, prep_args)

    def test_computed_column_missing_source(self):
        """Test Computed column missing source."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1, 2]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="x",
            method="sum",
            source_columns=["nonexistent"],
        )
        with pytest.raises(OperationError):
            op.execute(data, prep_args)

    def test_computed_with_string_source_columns(self):
        """Test that string source_columns are parsed correctly."""
        op = AddNewColumnOperation()
        data = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        prep_args = PrepActionResult(
            action="add new column",
            column_names="total",
            method="sum",
            source_columns="a, b",
        )
        result, _ = op.execute(data, prep_args)
        assert result["total"].to_list() == [4, 6]


# === PREP PROCESSOR TESTS === #


class TestPrepProcessor:
    """Test PrepProcessor."""

    def test_init(self):
        """Test Init."""
        processor = PrepProcessor()
        assert PrepActions.remove_column in processor.operation_handlers
        assert PrepActions.remove_row in processor.operation_handlers
        assert PrepActions.transform_column in processor.operation_handlers
        assert PrepActions.add_column in processor.operation_handlers

    def test_execute_single_action(self):
        """Test Execute single action."""
        processor = PrepProcessor()
        data = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        action = PrepAction.from_args(
            PrepActionResult(action="remove column(s)", source_columns=["b"])
        )
        result, _ = processor.execute_single_action(data, action)
        assert "b" not in result.columns

    def test_execute_single_action_invalid_type(self):
        """Test Execute single action invalid type."""
        processor = PrepProcessor()
        data = pl.DataFrame({"a": [1]})
        action = PrepAction(action_type=None, prep_args=PrepActionResult(action="x"))
        with pytest.raises(ValidationError, match="No handler for action type"):
            processor.execute_single_action(data, action)

    def test_execute_all_actions_success(self):
        """Test Execute all actions success."""
        processor = PrepProcessor()
        data = pl.DataFrame({"a": [1, 2], "b": [3, 4], "c": [5, 6]})
        actions = [
            PrepAction.from_args(
                PrepActionResult(action="remove column(s)", source_columns=["c"])
            ),
            PrepAction.from_args(
                PrepActionResult(
                    action="add new column",
                    column_names="new",
                    method="constant",
                    value="x",
                )
            ),
        ]
        result, outcomes = processor.execute_all_actions(data, actions)
        assert "c" not in result.columns
        assert "new" in result.columns
        assert [o.status for o in outcomes] == ["Successful", "Successful"]

    def test_execute_all_actions_empty(self):
        """Test Execute all actions empty."""
        processor = PrepProcessor()
        data = pl.DataFrame({"a": [1, 2]})
        result, outcomes = processor.execute_all_actions(data, [])
        assert result.equals(data)
        assert outcomes == []

    def test_execute_all_actions_failure(self):
        """Test Execute all actions failure."""
        processor = PrepProcessor()
        data = pl.DataFrame({"a": [1]})
        actions = [
            PrepAction.from_args(
                PrepActionResult(
                    action="remove column(s)", source_columns=["nonexistent"]
                )
            )
        ]
        # A failing action is skipped (not raised) and reported as a failure
        result, outcomes = processor.execute_all_actions(data, actions)
        assert result.equals(data)
        assert len(outcomes) == 1
        assert outcomes[0].status == "Failed"
        assert "Columns not found" in outcomes[0].error

    def test_execute_all_actions_partial_failure_continues(self):
        """A failing action is skipped but later actions still apply."""
        processor = PrepProcessor()
        data = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        actions = [
            PrepAction.from_args(
                PrepActionResult(
                    action="remove column(s)", source_columns=["nonexistent"]
                )
            ),
            PrepAction.from_args(
                PrepActionResult(action="remove column(s)", source_columns=["b"])
            ),
        ]
        result, outcomes = processor.execute_all_actions(data, actions)
        assert "b" not in result.columns
        assert "a" in result.columns
        assert [o.status for o in outcomes] == ["Failed", "Successful"]
        assert "Columns not found" in outcomes[0].error

    def test_execute_all_actions_partial_column_removal(self):
        """Removing 4 columns where 2 no longer exist removes the other 2."""
        processor = PrepProcessor()
        data = pl.DataFrame({"a": [1], "b": [2], "c": [3], "d": [4]})
        actions = [
            PrepAction.from_args(
                PrepActionResult(
                    action="remove column(s)",
                    source_columns=["a", "b", "missing1", "missing2"],
                )
            )
        ]
        result, outcomes = processor.execute_all_actions(data, actions)
        assert set(result.columns) == {"c", "d"}
        assert outcomes[0].status == "Successful"
        assert outcomes[0].prep_args.affected_count == 2
        assert outcomes[0].prep_args.failed_count == 2
        assert outcomes[0].prep_args.source_columns == ["a", "b"]


# === LOG MANAGEMENT TESTS === #


class TestLogManagement:
    """Test private log management functions."""

    def test_parse_prep_log_to_actions_dict(self):
        """Test parsing JSON-serialized prep_args (current production format)."""
        log = pl.DataFrame(
            {
                "prep_args": [
                    json.dumps(
                        {
                            "action": "remove column(s)",
                            "source_columns": ["col1"],
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
        actions = _parse_prep_log_to_actions(log)
        assert len(actions) == 1
        assert actions[0].action_type == PrepActions.remove_column

    def test_parse_prep_log_to_actions_legacy_repr(self):
        """Test parsing Python-repr-serialized prep_args (legacy fallback format)."""
        log = pl.DataFrame(
            {
                "prep_args": [
                    str(
                        {
                            "action": "remove column(s)",
                            "source_columns": ["col1"],
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
        actions = _parse_prep_log_to_actions(log)
        assert len(actions) == 1
        assert actions[0].action_type == PrepActions.remove_column

    def test_generate_action_description_remove_columns(self):
        """Test Generate action description remove columns."""
        prep_args = PrepActionResult(
            action="remove column(s)",
            source_columns=["col1"],
            affected_count=1,
            remaining_count=5,
        )
        desc = _generate_action_description(prep_args)
        assert "removed" in desc.lower() or "column" in desc.lower()

    def test_generate_action_description_remove_rows(self):
        """Test Generate action description remove rows."""
        prep_args = PrepActionResult(
            action="remove row(s)",
            affected_count=2,
            remaining_count=8,
            method="by condition",
        )
        desc = _generate_action_description(prep_args)
        assert len(desc) > 0

    def test_generate_action_description_transform(self):
        """Test Generate action description transform."""
        prep_args = PrepActionResult(
            action="transform column(s)",
            source_columns=["col1"],
            method="trim",
            affected_count=10,
        )
        desc = _generate_action_description(prep_args)
        assert len(desc) > 0

    def test_generate_action_description_add_column(self):
        """Test Generate action description add column."""
        prep_args = PrepActionResult(
            action="add new column",
            column_names="new_col",
            method="constant",
            value="test",
            remaining_count=5,
            source_columns=["src"],
        )
        desc = _generate_action_description(prep_args)
        assert len(desc) > 0

    def test_generate_action_description_unknown(self):
        """Test Generate action description unknown."""
        prep_args = PrepActionResult(action="unknown_action")
        desc = _generate_action_description(prep_args)
        assert desc == ""

    def test_convert_prep_args_to_string_already_string(self):
        """Test Convert prep args to string already string."""
        df = pl.DataFrame({"prep_args": ["already a string"]})
        result = _convert_prep_args_to_string(df)
        assert result["prep_args"].dtype == pl.String

    def test_create_log_entry(self):
        """Test Create log entry."""
        prep_args = PrepActionResult(action="remove column(s)", source_columns=["col1"])
        entry = _create_log_entry("remove column(s)", "Removed col1", prep_args, 0)
        assert entry.shape[0] == 1
        assert "action" in entry.columns
        assert "description" in entry.columns
        assert "prep_args" in entry.columns
        assert "action_index" in entry.columns
        assert entry["action_index"][0] == "0 - remove column(s) - Removed col1"

    def test_append_to_prep_log_empty(self):
        """Test Append to prep log empty."""
        existing = pl.DataFrame(
            {
                "action": [],
                "description": [],
                "prep_args": [],
                "action_index": [],
            }
        )
        new_entry = _create_log_entry(
            "remove column(s)",
            "test",
            PrepActionResult(action="remove column(s)"),
            0,
        )
        result = _append_to_prep_log(existing, new_entry)
        assert result.shape[0] == 1

    def test_append_to_prep_log_nonempty(self):
        """Test Append to prep log nonempty."""
        existing = _create_log_entry(
            "remove column(s)",
            "first",
            PrepActionResult(action="remove column(s)"),
            0,
        )
        new_entry = _create_log_entry(
            "add new column",
            "second",
            PrepActionResult(action="add new column"),
            1,
        )
        # Convert existing to string format to match typical state
        existing_str = _convert_prep_args_to_string(existing)
        result = _append_to_prep_log(existing_str, new_entry)
        assert result.shape[0] == 2

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_reapply_all_actions_empty_log(self, mock_save, mock_get):
        """Test Reapply all actions empty log."""
        raw_data = pl.DataFrame({"a": [1, 2, 3]})
        mock_get.return_value = raw_data
        empty_log = pl.DataFrame(
            {
                "action": [],
                "description": [],
                "prep_args": [],
                "action_index": [],
            }
        )
        processor = PrepProcessor()
        _reapply_all_actions("proj", "alias", empty_log, processor)
        mock_save.assert_called_once()
        # Should save raw_data as prep data
        saved_data = mock_save.call_args[0][1]
        assert saved_data.equals(raw_data)

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_reapply_all_actions_with_log(self, mock_save, mock_get):
        """Test Reapply all actions with log."""
        raw_data = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        mock_get.return_value = raw_data
        log = pl.DataFrame(
            {
                "prep_args": [
                    str(
                        {
                            "action": "remove column(s)",
                            "source_columns": ["b"],
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
        processor = PrepProcessor()
        failures = _reapply_all_actions("proj", "alias", log, processor)
        # Saves both the reapplied data and the refreshed log
        assert mock_save.call_count == 2
        saved_data = mock_save.call_args_list[0][0][1]
        assert "b" not in saved_data.columns
        assert failures == []

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_reapply_all_actions_partial_failure(self, mock_save, mock_get):
        """A step referencing a column dropped upstream is skipped, not raised.

        The rest of the log (a step on a still-present column) still applies,
        and the save reflects that partial result plus the reported failure.
        """
        raw_data = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        mock_get.return_value = raw_data
        log = pl.DataFrame(
            {
                "prep_args": [
                    str(
                        {
                            "action": "remove column(s)",
                            "source_columns": ["missing_column"],
                            "column_names": None,
                            "affected_count": None,
                            "remaining_count": None,
                            "value": None,
                            "method": None,
                            "condition": None,
                            "failed_count": None,
                            "additional_info": None,
                        }
                    ),
                    str(
                        {
                            "action": "remove column(s)",
                            "source_columns": ["b"],
                            "column_names": None,
                            "affected_count": None,
                            "remaining_count": None,
                            "value": None,
                            "method": None,
                            "condition": None,
                            "failed_count": None,
                            "additional_info": None,
                        }
                    ),
                ]
            }
        )
        processor = PrepProcessor()
        failures = _reapply_all_actions("proj", "alias", log, processor)

        saved_data = mock_save.call_args_list[0][0][1]
        assert "b" not in saved_data.columns
        assert "a" in saved_data.columns
        assert len(failures) == 1
        assert "Columns not found" in failures[0].reason

        # The refreshed log records the failed step's status and description
        saved_log = mock_save.call_args_list[1][0][1]
        assert saved_log["status"].to_list() == ["Failed", "Successful"]
        assert "Failed to reapply" in saved_log["description"][0]

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_apply_single_action(self, mock_save, mock_get):
        """Test Apply single action."""
        prep_data = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        mock_get.return_value = prep_data
        empty_log = pl.DataFrame(
            {
                "action": [],
                "description": [],
                "prep_args": [],
                "action_index": [],
            }
        )
        processor = PrepProcessor()
        prep_args = PrepActionResult(action="remove column(s)", source_columns=["b"])
        _apply_single_action("proj", "alias", prep_args, empty_log, processor)
        assert mock_save.call_count == 2  # log and data


# === PUBLIC API TESTS === #


class TestPrepApplyAction:
    """Test prep_apply_action public function."""

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_apply_new_action(self, mock_save, mock_get):
        """Test Apply new action."""
        empty_log = pl.DataFrame(
            {
                "action": [],
                "description": [],
                "prep_args": [],
                "action_index": [],
            }
        )
        mock_data = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        mock_get.side_effect = [empty_log, mock_data]
        prep_args = PrepActionResult(action="remove column(s)", source_columns=["b"])
        prep_apply_action("proj", "alias", prep_args)
        assert mock_get.call_count == 2
        assert mock_save.call_count == 2

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_reapply_all(self, mock_save, mock_get):
        """Test Reapply all."""
        log = pl.DataFrame(
            {
                "prep_args": [
                    str(
                        {
                            "action": "remove column(s)",
                            "source_columns": ["b"],
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
        raw_data = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        mock_get.side_effect = [log, raw_data]
        failures = prep_apply_action("proj", "alias", prep_args=None)
        assert mock_get.call_count == 2
        mock_save.assert_called()
        assert failures == []

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_reapply_all_reports_partial_failure(self, mock_save, mock_get):
        """A failing step during reapply-all is reported, not raised."""
        log = pl.DataFrame(
            {
                "prep_args": [
                    str(
                        {
                            "action": "remove column(s)",
                            "source_columns": ["missing_column"],
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
        raw_data = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        mock_get.side_effect = [log, raw_data]
        failures = prep_apply_action("proj", "alias", prep_args=None)
        assert mock_save.called  # data still saved, unmodified
        assert len(failures) == 1
        assert "Columns not found" in failures[0].reason

    @patch("datasure.processing.prep.duckdb_get_table")
    @patch("datasure.processing.prep.duckdb_save_table")
    def test_reapply_empty_log(self, mock_save, mock_get):
        """Test Reapply empty log."""
        empty_log = pl.DataFrame({"prep_args": []})
        raw_data = pl.DataFrame({"a": [1, 2]})
        mock_get.side_effect = [empty_log, raw_data]
        prep_apply_action("proj", "alias", prep_args=None)
        mock_save.assert_called_once()


# === INTEGRATION TESTS === #


class TestIntegration:
    """Integration tests combining multiple components."""

    def test_full_workflow_remove_and_add(self):
        """Test Full workflow remove and add."""
        data = pl.DataFrame(
            {"keep": [1, 2, 3], "remove": [4, 5, 6], "also_keep": [7, 8, 9]}
        )
        processor = PrepProcessor()

        # Remove a column
        action1 = PrepAction.from_args(
            PrepActionResult(action="remove column(s)", source_columns=["remove"])
        )
        result, _ = processor.execute_single_action(data, action1)
        assert "remove" not in result.columns

        # Add a new column
        action2 = PrepAction.from_args(
            PrepActionResult(
                action="add new column",
                column_names="new",
                method="constant",
                value="v",
            )
        )
        result, _ = processor.execute_single_action(result, action2)
        assert "new" in result.columns
        assert result.shape[1] == 3

    def test_full_workflow_transform_and_filter(self):
        """Test Full workflow transform and filter."""
        data = pl.DataFrame({"nums": [1, 2, 3, 4, 5]})
        processor = PrepProcessor()

        # Transform: add 10
        action1 = PrepAction.from_args(
            PrepActionResult(
                action="transform column(s)",
                source_columns=["nums"],
                method="add",
                value=[10],
            )
        )
        result, _ = processor.execute_single_action(data, action1)
        assert result["nums"].to_list() == [11, 12, 13, 14, 15]

        # Remove rows where nums > 13
        action2 = PrepAction.from_args(
            PrepActionResult(
                action="remove row(s)",
                method="by condition",
                source_columns=["nums"],
                condition="value is greater than",
                value=[13],
            )
        )
        result, _ = processor.execute_single_action(result, action2)
        assert all(v <= 13 for v in result["nums"].to_list())

    def test_error_propagation(self):
        """Test Error propagation."""
        processor = PrepProcessor()
        data = pl.DataFrame({"a": [1, 2]})
        action = PrepAction.from_args(
            PrepActionResult(action="remove column(s)", source_columns=["nonexistent"])
        )
        with pytest.raises(OperationError):
            processor.execute_single_action(data, action)

    def test_validation_chain(self):
        """Test Validation chain."""
        with pytest.raises(ValidationError):
            PrepAction.from_args(PrepActionResult(action="invalid_action"))
