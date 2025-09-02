"""Data preparation module for DataSure.

This module provides robust data preparation functionality using Polars for
high-performance DataFrame operations. It supports column removal, row filtering,
transformations, and new column creation with comprehensive error handling.
"""

import hashlib
import logging
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

import polars as pl
import streamlit as st

from datasure.utils import duckdb_get_table, duckdb_save_table

# Constants for validation
MAX_RANGE_VALUES = 2
MIN_PARTS_REQUIRED = 2


class PrepError(Exception):
    """Base exception for data preparation errors."""

    pass


class ValidationError(PrepError):
    """Raised when input validation fails."""

    pass


class OperationError(PrepError):
    """Raised when data operation fails."""

    pass


class ActionType(Enum):
    """Supported preparation action types."""

    REMOVE_COLUMNS = "remove column(s)"
    REMOVE_ROWS = "remove row(s)"
    TRANSFORM_COLUMNS = "transform column(s)"
    ADD_NEW_COLUMN = "add new column"


@dataclass
class PrepAction:
    """Represents a data preparation action."""

    action_type: ActionType
    description: str
    prep_args: str = ""

    @classmethod
    def from_strings(cls, action: str, description: str, prep_args: str) -> "PrepAction":
        """Create PrepAction from string representations."""
        try:
            action_type = ActionType(action)
        except ValueError as e:
            raise ValidationError(f"Unknown action type: {action}") from e

        return cls(action_type=action_type, description=description, prep_args=prep_args)


class DescriptionParser:
    """Parses operation descriptions into structured parameters."""

    @staticmethod
    def parse_column_list(text: str) -> list[str]:
        """Parse column list from description text."""
        # Extract content between square brackets
        match = re.search(r"\[([^\]]+)\]", text)
        if not match:
            raise ValidationError(f"No column specification found in: {text}")

        column_text = match.group(1)
        # Handle both quoted and unquoted column names
        columns = []
        for item in column_text.split(","):
            item = item.strip().strip("'\"")
            if item:
                columns.append(item)

        if not columns:
            raise ValidationError(f"Empty column specification in: {text}")

        return columns

    @staticmethod
    def parse_quoted_content(text: str) -> list:
        """Extract content between single quotes."""
        matches = re.findall(r"'([^']+)'", text)
        if not matches:
            raise ValidationError(f"No quoted content found in: {text}")
        return matches

    @staticmethod
    def parse_numeric_value(text: str) -> int | float:
        """Extract numeric value from text."""
        # Look for integer or float pattern
        match = re.search(r"(\d+\.?\d*)", text)
        if not match:
            raise ValidationError(f"No numeric value found in: {text}")

        value_str = match.group(1)
        return float(value_str) if "." in value_str else int(value_str)

    @staticmethod
    def parse_value_list(text: str) -> list[Any]:
        """Parse a list of values from text."""
        # Extract content between brackets
        match = re.search(r"\[([^\]]+)\]", text)
        if not match:
            raise ValidationError(f"No value list found in: {text}")

        values_text = match.group(1)
        values = []
        for item in values_text.split(","):
            item = item.strip().strip("'\"")
            if item.isdigit():
                values.append(int(item))
            elif item.replace(".", "", 1).isdigit():
                values.append(float(item))
            else:
                values.append(item)

        return values


class PrepOperation(ABC):
    """Base class for data preparation operations."""

    @abstractmethod
    def execute(self, data: pl.DataFrame, description: str) -> pl.DataFrame:
        """Execute the operation on the given data."""
        pass

    def _validate_columns_exist(self, data: pl.DataFrame, columns: list[str]) -> None:
        """Validate that specified columns exist in the DataFrame."""
        missing_columns = [col for col in columns if col not in data.columns]
        if missing_columns:
            raise OperationError(f"Columns not found: {missing_columns}")


class RemoveColumnsOperation(PrepOperation):
    """Remove specified columns from DataFrame."""

    def execute(self, data: pl.DataFrame, description: str) -> pl.DataFrame:
        """Remove columns specified in description."""
        try:
            # Extract column names from description
            columns_text = description.replace("remove column(s) ", "", 1)
            columns = DescriptionParser.parse_column_list(columns_text)

            self._validate_columns_exist(data, columns)

            # Remove columns using Polars
            return data.drop(columns)

        except Exception as e:
            if isinstance(e, ValidationError | OperationError):
                raise
            raise OperationError(f"Failed to remove columns: {e}") from e


class RemoveRowsOperation(PrepOperation):
    """Remove rows based on various conditions."""

    def execute(self, data: pl.DataFrame, description: str) -> pl.DataFrame:
        """Remove rows based on condition specified in description."""
        try:

            def _raise_unknown_removal_type():
                raise ValidationError(f"Unknown row removal type: {description}")  # noqa: TRY301

            if "remove row(s) by index" in description:
                return self._remove_by_index(data, description)
            elif "remove row(s) by condition" in description:
                return self._remove_by_condition(data, description)
            else:
                _raise_unknown_removal_type()

        except Exception as e:
            if isinstance(e, ValidationError | OperationError):
                raise
            raise OperationError(f"Failed to remove rows: {e}") from e

    def _remove_by_index(self, data: pl.DataFrame, description: str) -> pl.DataFrame:
        """Remove rows by index positions."""
        index_text = description.replace("remove row(s) by index", "", 1).strip()
        index_values = DescriptionParser.parse_value_list(index_text)

        rows_to_drop = []
        for item in index_values:
            if isinstance(item, str) and ":" in item:
                # Handle range like "1:3"
                start, end = item.split(":")
                rows_to_drop.extend(range(int(start), int(end) + 1))
            else:
                rows_to_drop.append(int(item))

        # Create row number column for filtering
        data_with_idx = data.with_row_count("__row_idx__")
        filtered_data = data_with_idx.filter(~pl.col("__row_idx__").is_in(rows_to_drop))
        return filtered_data.drop("__row_idx__")

    def _remove_by_condition(
        self, data: pl.DataFrame, description: str
    ) -> pl.DataFrame:
        """Remove rows based on conditions."""
        # Parse condition type
        condition_match = re.search(r"'([^']+)'", description)
        if not condition_match:
            raise ValidationError(f"No condition found in: {description}")

        condition = condition_match.group(1)

        # Parse columns
        columns = DescriptionParser.parse_column_list(description)
        self._validate_columns_exist(data, columns)

        if condition == "value is missing":
            return data.filter(~pl.any_horizontal(pl.col(columns).is_null()))

        elif condition == "value is not missing":
            return data.filter(pl.any_horizontal(pl.col(columns).is_null()))

        elif condition in ["value is equal to", "value is not equal to"]:
            return self._filter_by_equality(data, description, condition, columns)

        elif condition in [
            "value is greater than",
            "value is greater than or equal to",
            "value is less than",
            "value is less than or equal to",
        ]:
            return self._filter_by_comparison(data, description, condition, columns)

        elif condition in ["value is between", "value is not between"]:
            return self._filter_by_range(data, description, condition, columns)

        elif condition in ["value is like", "value is not like"]:
            return self._filter_by_pattern(data, description, condition, columns)

        else:
            raise ValidationError(f"Unknown condition: {condition}")

    def _filter_by_equality(
        self, data: pl.DataFrame, description: str, condition: str, columns: list[str]
    ) -> pl.DataFrame:
        """Filter by equality conditions."""
        # Extract values
        value_match = re.search(r"with value\s+(.+)", description)
        if not value_match:
            raise ValidationError(f"No values found in: {description}")

        values = DescriptionParser.parse_value_list(value_match.group(1))
        col_name = columns[0]

        if condition == "value is equal to":
            # Keep rows where value is NOT in the list (remove matching rows)
            return data.filter(~pl.col(col_name).is_in(values))
        else:
            # Keep rows where value IS in the list (remove non-matching rows)
            return data.filter(pl.col(col_name).is_in(values))

    def _filter_by_comparison(
        self, data: pl.DataFrame, description: str, condition: str, columns: list[str]
    ) -> pl.DataFrame:
        """Filter by comparison conditions."""
        value_match = re.search(r"with value\s+(.+)", description)
        if not value_match:
            raise ValidationError(f"No value found in: {description}")

        value_text = value_match.group(1).strip("'\"[]")
        value = DescriptionParser.parse_numeric_value(value_text)
        col_name = columns[0]

        # Inverse logic - we keep rows that don't match the removal condition
        if condition == "value is greater than":
            return data.filter(pl.col(col_name) <= value)
        elif condition == "value is greater than or equal to":
            return data.filter(pl.col(col_name) < value)
        elif condition == "value is less than":
            return data.filter(pl.col(col_name) >= value)
        elif condition == "value is less than or equal to":
            return data.filter(pl.col(col_name) > value)

        return data

    def _filter_by_range(
        self, data: pl.DataFrame, description: str, condition: str, columns: list[str]
    ) -> pl.DataFrame:
        """Filter by range conditions."""
        value_match = re.search(r"with values\s+(.+)", description)
        if not value_match:
            raise ValidationError(f"No values found in: {description}")

        values_text = value_match.group(1).replace("'", "").replace('"', "")
        values = values_text.split(" and ")

        if len(values) != MAX_RANGE_VALUES:
            raise ValidationError(
                f"Expected {MAX_RANGE_VALUES} values for range, got: {values}"
            )

        val1 = DescriptionParser.parse_numeric_value(values[0])
        val2 = DescriptionParser.parse_numeric_value(values[1])
        col_name = columns[0]

        if condition == "value is between":
            # Keep rows outside the range
            return data.filter((pl.col(col_name) < val1) | (pl.col(col_name) > val2))
        else:
            # Keep rows inside the range
            return data.filter((pl.col(col_name) >= val1) & (pl.col(col_name) <= val2))

    def _filter_by_pattern(
        self, data: pl.DataFrame, description: str, condition: str, columns: list[str]
    ) -> pl.DataFrame:
        """Filter by pattern matching."""
        pattern_match = re.search(r"with pattern\s+(.+)", description)
        if not pattern_match:
            raise ValidationError(f"No pattern found in: {description}")

        pattern = pattern_match.group(1).strip("'\"")
        col_name = columns[0]

        if condition == "value is like":
            # Keep rows that don't match the pattern
            return data.filter(~pl.col(col_name).str.contains(pattern))
        else:
            # Keep rows that match the pattern
            return data.filter(pl.col(col_name).str.contains(pattern))


class TransformColumnsOperation(PrepOperation):
    """Transform column values using various operations."""

    def execute(self, data: pl.DataFrame, description: str) -> pl.DataFrame:
        """Transform columns based on description."""
        try:
            column_name, func_name = self._parse_transformation_params(description)
            self._validate_columns_exist(data, [column_name])
            return self._apply_transformation(data, column_name, func_name, description)

        except Exception as e:
            if isinstance(e, ValidationError | OperationError):
                raise
            raise OperationError(f"Failed to transform columns: {e}") from e

    def _parse_transformation_params(self, description: str) -> tuple[str, str]:
        """Parse transformation parameters from description."""
        quoted_content = DescriptionParser.parse_quoted_content(description)

        if len(quoted_content) < MIN_PARTS_REQUIRED:
            raise ValidationError(f"Invalid transformation format: {quoted_content}")

        if len(quoted_content) > MIN_PARTS_REQUIRED:
            column_name, func_name, *_ = quoted_content
        else:
            column_name, func_name = quoted_content

        return column_name, func_name

    @staticmethod
    def _parse_flexible_datetime(col_name: str) -> pl.Expr:
        """Try multiple datetime formats and return the first successful one"""
        formats_to_try = [
            "%d%b%Y %H:%M:%S",  # 18aug2025 19:49:00
            "%d-%b-%Y %H:%M:%S",  # 18-aug-2025 19:49:00
            "%Y-%m-%d %H:%M:%S",  # 2025-08-18 19:49:00
            "%m/%d/%Y %H:%M:%S",  # 08/18/2025 19:49:00
            "%d/%m/%Y %H:%M:%S",  # 18/08/2025 19:49:00
            "%Y-%m-%d",  # 2025-08-18
            "%m/%d/%Y",  # 08/18/2025
            "%d-%m-%Y",  # 18-08-2025
        ]

        for fmt in formats_to_try:
            try:
                return pl.col(col_name).str.to_datetime(format=fmt, strict=False)
            except Exception:
                continue

        # If all formats fail, all missing values
        return pl.lit(None).cast(pl.Datetime)

    def _apply_transformation(
        self, data: pl.DataFrame, column_name: str, func_name: str, description: str
    ) -> pl.DataFrame:
        """Apply specific transformation to column."""
        # DateTime extractions
        datetime_ops = {
            "day of month": lambda col: col.dt.day(),
            "day of week": lambda col: col.dt.weekday(),
            "day of year": lambda col: col.dt.ordinal_day(),
            "date": lambda col: col.dt.date(),
            "week of year": lambda col: col.dt.week(),
            "month of year": lambda col: col.dt.month(),
            "year": lambda col: col.dt.year(),
            "quarter of year": lambda col: col.dt.quarter(),
            "hour": lambda col: col.dt.hour(),
            "minute": lambda col: col.dt.minute(),
            "second": lambda col: col.dt.second(),
        }

        if func_name in datetime_ops:
            return data.with_columns(
                datetime_ops[func_name](pl.col(column_name)).alias(column_name)
            )

        # Math operations
        math_ops = {
            "floor": lambda col: col.floor(),
            "ceil": lambda col: col.ceil(),
            "round": lambda col: col.round(0),
            "abs": lambda col: col.abs(),
        }

        if func_name in math_ops:
            return data.with_columns(
                math_ops[func_name](pl.col(column_name)).alias(column_name)
            )

        # Arithmetic operations
        if func_name in ["add", "subtract", "multiply", "divide"]:
            return self._apply_arithmetic(data, column_name, func_name, description)

        # String operations
        string_ops = {
            "trim": lambda col: col.str.strip_chars(),
            "lower": lambda col: col.str.to_lowercase(),
            "upper": lambda col: col.str.to_uppercase(),
            "string to number": lambda col: col.str.to_numeric(strict=False),
        }

        if func_name in string_ops:
            return data.with_columns(
                string_ops[func_name](pl.col(column_name)).alias(column_name)
            )

        # String to datetime
        if func_name in ["string to date", "string to datetime"]:
            return data.with_columns(
                self._parse_flexible_datetime(column_name).alias(column_name)
            )

        # Get dummies (one-hot encoding)
        if func_name == "get dummies":
            return data.to_dummies(columns=[column_name])

        # String replacement
        if func_name.startswith("replace by replacing"):
            return self._apply_string_replace(data, column_name, func_name)

        # Substring extraction
        if func_name == "substring":
            return self._apply_substring(data, column_name, description)

        # Pattern extraction
        if func_name.startswith("extract pattern"):
            return self._apply_pattern_extract(data, column_name, func_name)

        raise ValidationError(f"Unknown transformation function: {func_name}")

    def _apply_arithmetic(
        self, data: pl.DataFrame, column_name: str, operation: str, description: str
    ) -> pl.DataFrame:
        """Apply arithmetic operations."""
        value = DescriptionParser.parse_numeric_value(description)

        ops = {
            "add": lambda col, val: col + val,
            "subtract": lambda col, val: col - val,
            "multiply": lambda col, val: col * val,
            "divide": lambda col, val: col / val,
        }

        return data.with_columns(
            ops[operation](pl.col(column_name), value).alias(column_name)
        )

    def _apply_string_replace(
        self, data: pl.DataFrame, column_name: str, func_name: str
    ) -> pl.DataFrame:
        """Apply string replacement."""
        replace_text = func_name.replace("replace by replacing ", "")
        parts = replace_text.split(" with ", 1)

        if len(parts) != 2:
            raise ValidationError(
                "Invalid replace format. Expected 'replace by replacing X with Y'"
            )

        old_text, new_text = parts
        return data.with_columns(
            pl.col(column_name).str.replace(old_text, new_text).alias(column_name)
        )

    def _apply_substring(
        self, data: pl.DataFrame, column_name: str, description: str
    ) -> pl.DataFrame:
        """Apply substring extraction."""
        range_match = re.findall(r"(\d+) to (\d+)", description)
        if not range_match:
            raise ValidationError("Invalid description format. Expected 'from X to Y'.")

        start = int(range_match[0][0])
        end = int(range_match[0][1])

        return data.with_columns(
            pl.col(column_name).str.slice(start, end - start).alias(column_name)
        )

    def _apply_pattern_extract(
        self, data: pl.DataFrame, column_name: str, func_name: str
    ) -> pl.DataFrame:
        """Apply pattern extraction."""
        pattern_text = func_name.replace("extract pattern by extracting pattern ", "")

        return data.with_columns(
            pl.col(column_name).str.extract(pattern_text).alias(column_name)
        )


class AddNewColumnOperation(PrepOperation):
    """Add new columns with computed values."""

    def execute(self, data: pl.DataFrame, prep_args: dict) -> pl.DataFrame:
        """Add new column based on description."""
        try:
            new_col_name, value_spec = prep_args.get("column_names"), prep_args.get("value")
            method = prep_args.get("method")
            source_columns = prep_args.get("source_columns", [])

            if method == "constant":
                return self._add_constant_column(data, new_col_name, value_spec)
            elif method in ["index", "uuid", "random"]:
                return self._add_special_column(data, method, new_col_name, value_spec,)
            else:
                return self._add_computed_column(data, new_col_name, method, source_columns)

        except Exception as e:
            if isinstance(e, ValidationError | OperationError):
                raise
            raise OperationError(f"Failed to add new column: {e}") from e

    def _add_constant_column(
        self, data: pl.DataFrame, col_name: str, value_spec: str
    ) -> pl.DataFrame:
        """Add column with constant value."""
        # check if value_spec can be converted to int or float
        try:
            value = float(value_spec) if "." in value_spec else int(value_spec)
        except ValueError:
            value = value_spec
        return data.with_columns(pl.lit(value).alias(col_name))

    def _add_special_column(
        self, data: pl.DataFrame, method: str, col_name: str, value_spec: str
    ) -> pl.DataFrame:
        """Add special columns like index, uuid, or random."""
        if method == "index":
            return data.with_row_count(col_name)

        elif method == "uuid":
            # Generate UUID-like hash based on project ID and row index
            project_id = st.session_state.st_project_id

            return (
                data.with_row_count("__temp_idx__")
                .with_columns(
                    pl.col("__temp_idx__")
                    .map_elements(
                        lambda idx: hashlib.sha256(
                            f"{project_id}_{idx}".encode()
                        ).hexdigest(),
                        return_dtype=pl.Utf8,
                    )
                    .alias(col_name)
                )
                .drop("__temp_idx__")
            )

        elif method == "random":
            import random

            n_rows = data.height
            random_values = [random.random() for _ in range(n_rows)]
            return data.with_columns(pl.Series(random_values).alias(col_name))

        return data

    def _add_computed_column(
        self, data: pl.DataFrame, col_name: str, method: str, source_columns: str
    ) -> pl.DataFrame:
        """Add column with computed values from other columns."""
        func_name = method.lower()
        if isinstance(source_columns, str):
            columns = [col.strip().strip("'\"") for col in source_columns.split(",")]
        elif isinstance(source_columns, list):
            columns = source_columns

        self._validate_columns_exist(data, columns)

        # Aggregation functions
        agg_funcs = {
            "sum": lambda cols: pl.sum_horizontal(cols),
            "mean": lambda cols: pl.mean_horizontal(cols),
            "median": lambda cols: pl.concat_list(cols).list.median(),
            "max": lambda cols: pl.max_horizontal(cols),
            "min": lambda cols: pl.min_horizontal(cols),
            "std": lambda cols: pl.concat_list(cols).list.std(),
            "var": lambda cols: pl.concat_list(cols).list.var(),
            "first": lambda cols: pl.concat_list(cols).list.first(),
            "last": lambda cols: pl.concat_list(cols).list.last(),
            "count": lambda cols: pl.concat_list(cols).list.len(),
            "nunique": lambda cols: pl.concat_list(cols).list.unique().list.len(),
            "product": lambda cols: pl.fold(acc=pl.lit(1), function=lambda acc, x: acc * x, exprs=cols),
        }

        if func_name in agg_funcs:
            return data.with_columns(agg_funcs[func_name](columns).alias(col_name))

        # Binary operations
        if func_name in ["quotient", "diff"]:
            if len(columns) != 2:
                raise ValidationError("Quotient and diff require exactly two columns.")

            if func_name == "quotient":
                return data.with_columns(
                    (pl.col(columns[0]) / pl.col(columns[1])).alias(col_name)
                )
            else:  # diff
                return data.with_columns(
                    (pl.col(columns[0]) - pl.col(columns[1])).alias(col_name)
                )

        raise ValidationError(f"Unknown aggregation function: {func_name}")


class PrepProcessor:
    """Main processor for data preparation operations."""

    def __init__(self):
        """Initialize processor with operation handlers."""
        self.operation_handlers = {
            ActionType.REMOVE_COLUMNS: RemoveColumnsOperation(),
            ActionType.REMOVE_ROWS: RemoveRowsOperation(),
            ActionType.TRANSFORM_COLUMNS: TransformColumnsOperation(),
            ActionType.ADD_NEW_COLUMN: AddNewColumnOperation(),
        }

    def execute_single_action(
        self, data: pl.DataFrame, action: PrepAction
    ) -> pl.DataFrame:
        """Execute a single preparation action."""
        handler = self.operation_handlers.get(action.action_type)
        if not handler:
            raise ValidationError(f"No handler for action type: {action.action_type}")

        return handler.execute(data, action.prep_args)

    def execute_all_actions(
        self, data: pl.DataFrame, actions: list[PrepAction]
    ) -> pl.DataFrame:
        """Execute a sequence of preparation actions."""
        result_data = data

        for action in actions:
            try:
                result_data = self.execute_single_action(result_data, action)
            except Exception as e:
                raise OperationError(
                    f"Failed to execute action '{action.description}': {e}"
                ) from e

        return result_data


def prep_apply_action(
    project_id: str,
    alias: str,
    action: str | None = None,
    description: str | None = None,
) -> None:
    """Apply data preparation action to dataset.

    Args:
        project_id: Project identifier
        alias: Dataset alias
        action: Action type to apply
        description: Action description

    Raises
    ------
        ValidationError: If action/description validation fails
        OperationError: If data operation fails
    """
    try:
        processor = PrepProcessor()

        # Load existing preparation log
        prep_log_df = duckdb_get_table(
            project_id,
            f"prep_log_{alias}",
            db_name="logs",
        )

        # Convert to list of actions
        existing_actions = []
        for row in prep_log_df.iter_rows(named=True):
            existing_actions.append(
                PrepAction.from_strings(row["action"], row["description"], row["prep_args"])
            )

        # Add new action if provided
        if action and description:
            new_action = PrepAction.from_strings(action, description)
            existing_actions.append(new_action)
            action_index_val = f"{len(existing_actions) - 1} - {action} - {description}"

            # Update log with new action
            new_row = pl.DataFrame(
                {
                    "action": [action],
                    "description": [description],
                    "action_index": [action_index_val],
                }
            )

            if prep_log_df.is_empty():
                updated_log = new_row
            else:
                updated_log = prep_log_df.vstack(new_row)

            duckdb_save_table(
                project_id,
                updated_log,
                f"prep_log_{alias}",
                db_name="logs",
            )

            # Get current prepared data
            prep_data = duckdb_get_table(
                project_id,
                alias,
                db_name="prep",
            )

            # Apply only the new action
            result_data = processor.execute_single_action(prep_data, new_action)
        else:
            # Re-apply all actions from raw data
            raw_data = duckdb_get_table(
                project_id,
                alias,
                db_name="raw",
            )

            # Apply all actions
            result_data = processor.execute_all_actions(raw_data, existing_actions)

        # Save prepared dataset
        duckdb_save_table(
            project_id,
            result_data,
            alias,
            db_name="prep",
        )

    except Exception as e:
        if isinstance(e, ValidationError | OperationError):
            # Show user-friendly error in Streamlit
            st.error(f"Data preparation failed: {e}")
            raise
        else:
            # Log unexpected errors and show generic message
            logging.error("Unexpected error in prep_apply_action: %s", e, exc_info=True)
            st.error("An unexpected error occurred during data preparation.")
            raise OperationError(f"Unexpected error in prep_apply_action: {e}") from e


# Legacy function aliases for backward compatibility
def prep_remove_columns(prep_data, description: str):
    """Legacy wrapper for column removal."""
    operation = RemoveColumnsOperation()
    # Convert pandas to polars if needed
    if hasattr(prep_data, "to_pandas"):
        # It's already a Polars DataFrame
        polars_data = prep_data
    else:
        # Convert pandas to polars
        polars_data = pl.from_pandas(prep_data)

    return operation.execute(polars_data, description)


def prep_remove_rows(prep_data, description: str):
    """Legacy wrapper for row removal."""
    operation = RemoveRowsOperation()
    if hasattr(prep_data, "to_pandas"):
        polars_data = prep_data
    else:
        polars_data = pl.from_pandas(prep_data)

    return operation.execute(polars_data, description)


def prep_transform_columns(prep_data, description: str):
    """Legacy wrapper for column transformation."""
    operation = TransformColumnsOperation()
    if hasattr(prep_data, "to_pandas"):
        polars_data = prep_data
    else:
        polars_data = pl.from_pandas(prep_data)

    return operation.execute(polars_data, description)


def prep_add_new_column(prep_data, description: str):
    """Legacy wrapper for adding new columns."""
    operation = AddNewColumnOperation()
    if hasattr(prep_data, "to_pandas"):
        polars_data = prep_data
    else:
        polars_data = pl.from_pandas(prep_data)

    return operation.execute(polars_data, description)
