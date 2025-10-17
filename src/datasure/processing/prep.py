"""Data preparation module for DataSure.

This module provides robust data preparation functionality using Polars for
high-performance DataFrame operations. It supports column removal, row filtering,
transformations, and new column creation with comprehensive error handling.
"""

import ast
import hashlib
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any

import polars as pl
import streamlit as st

from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.prep_utils import (
    PrepActionResult,
    PrepConfirmationMessages,
)

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
    prep_args: PrepActionResult

    @classmethod
    def from_args(cls, prep_args: PrepActionResult) -> "PrepAction":
        """Create PrepAction from string representations."""
        action = prep_args.action
        try:
            action_type = ActionType(action)
        except ValueError as e:
            raise ValidationError(f"Unknown action type: {action}") from e

        return cls(action_type=action_type, prep_args=prep_args)


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

    def execute(
        self, data: pl.DataFrame, prep_args: PrepActionResult
    ) -> tuple[pl.DataFrame, PrepActionResult]:
        """Remove columns specified in description."""
        try:
            # Extract column names from description
            columns = prep_args.source_columns
            self._validate_columns_exist(data, columns)

            # drop columns
            results = data.drop(columns)

            updated_prep_args = {
                "action": "remove column(s)",
                "column_names": None,
                "affected_count": len(columns),
                "remaining_count": data.width,
                "value": None,
                "method": None,
                "source_columns": columns,
                "condition": prep_args.condition,
                "failed_count": 0,
                "additional_info": None,
            }

            # Remove columns using Polars
            return results, PrepActionResult(**updated_prep_args)

        except Exception as e:
            if isinstance(e, ValidationError | OperationError):
                raise
            raise OperationError(f"Failed to remove columns: {e}") from e


class RemoveRowsOperation(PrepOperation):
    """Remove rows based on various conditions."""

    def execute(
        self, data: pl.DataFrame, prep_args: PrepActionResult
    ) -> tuple[pl.DataFrame, PrepActionResult]:
        """Remove rows based on condition specified in description."""
        try:
            method = prep_args.method
            value = prep_args.value
            condition = prep_args.condition
            source_columns = prep_args.source_columns or []

            if method == "by row index":
                results = self._remove_by_index(data, value)
            elif method == "by condition":
                results = self._remove_by_condition(
                    data, condition, source_columns, value
                )
            else:
                raise ValidationError(f"Unknown removal method: {method}")  # noqa: TRY301

            updated_prep_args = {
                "action": "remove row(s)",
                "column_names": None,
                "affected_count": data.height - results.height,
                "remaining_count": results.height,
                "value": value,
                "method": method,
                "source_columns": source_columns,
                "condition": condition,
                "failed_count": 0,
                "additional_info": None,
            }

            return results, PrepActionResult(**updated_prep_args)

        except Exception as e:
            if isinstance(e, ValidationError | OperationError):
                raise
            raise OperationError(f"Failed to remove rows: {e}") from e

    def _remove_by_index(self, data: pl.DataFrame, index_values: list) -> pl.DataFrame:
        """Remove rows by index positions."""
        rows_to_drop = []
        for item in index_values:
            if item in [",", None]:
                continue
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
        self, data: pl.DataFrame, condition: str, columns: list[str], value: Any
    ) -> pl.DataFrame:
        """Remove rows based on conditions."""
        # Parse columns
        self._validate_columns_exist(data, columns)

        if condition == "value is missing":
            return data.filter(~pl.any_horizontal(pl.col(columns).is_null()))

        elif condition == "value is not missing":
            return data.filter(pl.any_horizontal(pl.col(columns).is_null()))

        elif condition in ["value is equal to", "value is not equal to"]:
            return self._filter_by_equality(data, condition, columns, value)

        elif condition in [
            "value is greater than",
            "value is greater than or equal to",
            "value is less than",
            "value is less than or equal to",
        ]:
            return self._filter_by_comparison(data, condition, columns, value)

        elif condition in ["value is between", "value is not between"]:
            return self._filter_by_range(data, condition, columns, value)

        elif condition in ["value is like", "value is not like"]:
            return self._filter_by_pattern(data, condition, columns, value)

        else:
            raise ValidationError(f"Unknown condition: {condition}")

    def _filter_by_equality(
        self, data: pl.DataFrame, condition: str, columns: list[str], value: Any
    ) -> pl.DataFrame:
        """Filter by equality conditions."""
        if condition == "value is equal to":
            # Keep rows where value is NOT in the list (remove matching rows)
            return data.filter(~pl.col(columns).is_in(value))
        else:
            # Keep rows where value IS in the list (remove non-matching rows)
            return data.filter(pl.col(columns).is_in(value))

    def _filter_by_comparison(
        self, data: pl.DataFrame, condition: str, columns: list[str], value: Any
    ) -> pl.DataFrame:
        """Filter by comparison conditions."""
        # Inverse logic - we keep rows that don't match the removal condition
        value_use = (
            float(value[0])
            if isinstance(value[0], str) and "." in value
            else int(value[0])
        )
        if condition == "value is greater than":
            return data.filter(pl.col(columns) <= value_use)
        elif condition == "value is greater than or equal to":
            return data.filter(pl.col(columns) < value_use)
        elif condition == "value is less than":
            return data.filter(pl.col(columns) >= value_use)
        elif condition == "value is less than or equal to":
            return data.filter(pl.col(columns) > value_use)

        return data

    def _filter_by_range(
        self, data: pl.DataFrame, condition: str, columns: list[str], value: Any
    ) -> pl.DataFrame:
        """Filter by range conditions."""
        if len(value) != MAX_RANGE_VALUES:
            raise ValidationError(
                f"Expected {MAX_RANGE_VALUES} values for range, got: {value}"
            )

        if condition == "value is between":
            # Keep rows outside the range
            return data.filter(
                (pl.col(columns) < value[0]) | (pl.col(columns) > value[1])
            )
        else:
            # Keep rows inside the range
            return data.filter(
                (pl.col(columns) >= value[0]) & (pl.col(columns) <= value[1])
            )

    def _filter_by_pattern(
        self, data: pl.DataFrame, condition: str, columns: list[str], value: str
    ) -> pl.DataFrame:
        """Filter by pattern matching."""
        if condition == "value is like":
            # Keep rows that don't match the pattern
            filter_expr = pl.all_horizontal(
                [~pl.col(col).str.contains(value) for col in columns]
            )
            return data.filter(filter_expr)
        elif condition == "value is not like":
            # Keep rows that match the pattern
            filter_expr = pl.any_horizontal(
                [pl.col(col).str.contains(value) for col in columns]
            )
            return data.filter(filter_expr)
        else:
            raise ValidationError(f"Unknown pattern condition: {condition}")


class TransformColumnsOperation(PrepOperation):
    """Transform column values using various operations."""

    def execute(
        self, data: pl.DataFrame, prep_args: PrepActionResult
    ) -> tuple[pl.DataFrame, PrepActionResult]:
        """Transform columns based on description."""
        try:
            source_columns, func_name = prep_args.source_columns, prep_args.method
            self._validate_columns_exist(data, source_columns)
            value = prep_args.value or []
            result_data = self._apply_transformation(
                data, source_columns[0], func_name, value
            )

            # count the number of non-missing values in the transformed columns
            null_count = result_data.select(
                pl.col(source_columns[0]).null_count()
            ).item()
            affected_count = data.height - null_count
            prep_args = {
                "action": "transform column(s)",
                "column_names": None,
                "affected_count": affected_count,
                "remaining_count": None,
                "value": prep_args.value,
                "method": prep_args.method,
                "source_columns": source_columns,
                "condition": None,
                "failed_count": 0,
                "additional_info": None,
            }

            return result_data, PrepActionResult(**prep_args)

        except Exception as e:
            if isinstance(e, ValidationError | OperationError):
                raise
            raise OperationError(f"Failed to transform columns: {e}") from e

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
        self,
        data: pl.DataFrame,
        column_name: str,
        func_name: str,
        value: list[Any],
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
            return self._apply_arithmetic(data, column_name, func_name, value)

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
            return self._apply_substring(data, column_name, value)

        # Pattern extraction
        if func_name.startswith("extract pattern"):
            return self._apply_pattern_extract(data, column_name, func_name)

        raise ValidationError(f"Unknown transformation function: {func_name}")

    def _apply_arithmetic(
        self,
        data: pl.DataFrame,
        column_name: str,
        operation: str,
        value: list[int | float],
    ) -> pl.DataFrame:
        """Apply arithmetic operations."""
        ops = {
            "add": lambda col, val: col + val,
            "subtract": lambda col, val: col - val,
            "multiply": lambda col, val: col * val,
            "divide": lambda col, val: col / val,
        }

        return data.with_columns(
            ops[operation](pl.col(column_name), value[0]).alias(column_name)
        )

    def _apply_string_replace(
        self,
        data: pl.DataFrame,
        column_name: str,
        value: list[str],
    ) -> pl.DataFrame:
        """Apply string replacement."""
        if len(value) != 2:
            raise ValidationError(
                "Invalid replace format. Expected 'replace by replacing X with Y'"
            )

        old_text, new_text = value
        return data.with_columns(
            pl.col(column_name).str.replace(old_text, new_text).alias(column_name)
        )

    def _apply_substring(
        self,
        data: pl.DataFrame,
        column_name: str,
        value: list[int],
    ) -> pl.DataFrame:
        """Apply substring extraction."""
        if not value or len(value) != 2:
            raise ValidationError("Invalid description format. Expected 'from X to Y'.")

        start, end = value

        return data.with_columns(
            pl.col(column_name).str.slice(start, end - start).alias(column_name)
        )

    def _apply_pattern_extract(
        self,
        data: pl.DataFrame,
        column_name: str,
        value: list[str],
    ) -> pl.DataFrame:
        """Apply pattern extraction."""
        pattern_text = value[0]
        # validate pattern text
        try:
            re.compile(pattern_text)
        except re.error as e:
            raise ValidationError(f"Invalid regex pattern: {pattern_text}") from e
        return data.with_columns(
            pl.col(column_name).str.extract(pattern_text).alias(column_name)
        )


class AddNewColumnOperation(PrepOperation):
    """Add new columns with computed values."""

    def execute(self, data: pl.DataFrame, prep_args: PrepActionResult) -> pl.DataFrame:
        """Add new column based on description."""
        try:
            new_col_name, value_spec = prep_args.column_names, prep_args.value
            method = prep_args.method
            source_columns = prep_args.source_columns or [""]

            if method == "constant":
                results = self._add_constant_column(data, new_col_name, value_spec)
            elif method in ["index", "uuid", "random"]:
                results = self._add_special_column(data, method, new_col_name)
            else:
                results = self._add_computed_column(
                    data, new_col_name, method, source_columns
                )

            updated_prep_args = {
                "action": "add new column",
                "column_names": new_col_name,
                "affected_count": 1,
                "remaining_count": results.width,
                "value": value_spec,
                "method": method,
                "source_columns": source_columns,
                "condition": None,
                "failed_count": 0,
                "additional_info": None,
            }

            return results, PrepActionResult(**updated_prep_args)

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
        self,
        data: pl.DataFrame,
        method: str,
        col_name: str,
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
            "product": lambda cols: pl.fold(
                acc=pl.lit(1), function=lambda acc, x: acc * x, exprs=cols
            ),
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
    ) -> tuple[pl.DataFrame, PrepActionResult]:
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
                result_data, _ = self.execute_single_action(result_data, action)
            except Exception as e:
                raise OperationError(f"Failed to execute action '{action}': {e}") from e

        return result_data


def prep_apply_action(
    project_id: str,
    alias: str,
    prep_args: PrepActionResult | None = None,
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
    processor = PrepProcessor()
    # Load existing preparation log
    prep_log_df = duckdb_get_table(
        project_id,
        f"prep_log_{alias}",
        db_name="logs",
    )

    # run current action if prep_args is provided, else re-apply all actions from log
    if not prep_args:
        # Get raw data if re-applying all actions
        raw_data = duckdb_get_table(
            project_id,
            alias,
            db_name="raw",
        )

        if prep_log_df.is_empty():
            return None  # No actions to re-apply

        # Convert to list of actions
        existing_actions = []
        for row in prep_log_df.iter_rows(named=True):
            args = row["prep_args"]
            # check if args is a string (from JSON) and convert to dict
            if isinstance(args, str):
                args = ast.literal_eval(args)
            prep_action = PrepActionResult(**args)
            existing_actions.append(PrepAction.from_args(prep_action))

        # apply all existing actions to current prepared data
        result_data = processor.execute_all_actions(raw_data, existing_actions)
        # save new prep data
        duckdb_save_table(
            project_id,
            result_data,
            alias,
            db_name="prep",
        )
    else:
        # Get current prepared data
        prep_data = duckdb_get_table(
            project_id,
            alias,
            db_name="prep",
        )

        # Apply only the new action
        new_action = PrepAction.from_args(prep_args)
        result_data, updated_prep_args = processor.execute_single_action(
            prep_data, new_action
        )
        # Add new action if provided
        action = updated_prep_args.action
        if action == "remove column(s)":
            description = PrepConfirmationMessages.remove_columns(updated_prep_args)
        elif action == "remove row(s)":
            description = PrepConfirmationMessages.remove_rows(updated_prep_args)
        elif action == "transform column(s)":
            description = PrepConfirmationMessages.transform_columns(updated_prep_args)
        elif action == "add new column":
            description = PrepConfirmationMessages.add_new_column(updated_prep_args)

        action_index_val = f"{prep_log_df.height} - {action} - {description}"

        # Update log with new action
        new_row = pl.DataFrame(
            {
                "action": [action],
                "description": [description],
                "prep_args": [updated_prep_args],
                "action_index": [action_index_val],
            }
        )

        if prep_log_df.is_empty():
            updated_log = new_row
        else:
            # Convert struct columns to JSON strings for concatenation
            prep_log_json = prep_log_df.with_columns(
                pl.col("prep_args").map_elements(
                    lambda x: str(x) if x is not None else None, return_dtype=pl.String
                )
            )
            new_row_json = new_row.with_columns(
                pl.col("prep_args").map_elements(
                    lambda x: str(x) if x is not None else None, return_dtype=pl.String
                )
            )
            updated_log = pl.concat([prep_log_json, new_row_json])

        duckdb_save_table(
            project_id,
            updated_log,
            f"prep_log_{alias}",
            db_name="logs",
        )

        # Save updated prepared data
        duckdb_save_table(
            project_id,
            result_data,
            alias,
            db_name="prep",
        )
