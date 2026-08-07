"""Data preparation module for DataSure.

This module provides robust data preparation functionality using Polars for
high-performance DataFrame operations. It supports column removal, row filtering,
transformations, and new column creation with comprehensive error handling.
"""

import ast
import hashlib
import json
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import polars as pl
import streamlit as st

from datasure.models.enums import (
    PrepActions,
    PrepFunctions,
    PrepMethods,
    PrepOperations,
    PrepRowConditions,
)
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.prep_utils import (
    PrepActionResult,
    PrepConfirmationMessages,
)
from datasure.utils.reapply_utils import ReapplyFailure

# === EXCEPTIONS === #


class PrepError(Exception):
    """Base exception for data preparation errors."""

    pass


class ValidationError(PrepError):
    """Raised when input validation fails."""

    pass


class OperationError(PrepError):
    """Raised when data operation fails."""

    pass


# === DATA MODELS === #


@dataclass
class PrepReapplyOutcome:
    """Result of (re)applying one logged prep action during a bulk reapply."""

    prep_args: PrepActionResult
    status: str  # "Successful" or "Failed"
    error: str | None = None


@dataclass
class PrepAction:
    """Represents a data preparation action."""

    action_type: PrepActions
    prep_args: PrepActionResult

    @classmethod
    def from_args(cls, prep_args: PrepActionResult) -> "PrepAction":
        """Create PrepAction from string representations."""
        action = prep_args.action
        try:
            action_type = PrepActions(action)
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


# === OPERATIONS === #


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
        """Remove columns specified in description.

        Columns that no longer exist (e.g. dropped by a later re-import) are
        skipped rather than failing the whole step, as long as at least one
        requested column is still present - so a step that removed 4 columns
        still removes the 2 that remain instead of removing none.
        """
        try:
            columns = prep_args.source_columns or []
            existing_columns = [c for c in columns if c in data.columns]
            missing_columns = [c for c in columns if c not in data.columns]

            if not existing_columns:
                raise OperationError(f"Columns not found: {missing_columns}")  # noqa: TRY301

            # Remove columns using Polars
            results = data.drop(existing_columns)

            updated_prep_args = {
                "action": PrepActions.remove_column.value,
                "column_names": None,
                "affected_count": len(existing_columns),
                "remaining_count": results.width,
                "value": None,
                "method": None,
                "source_columns": existing_columns,
                "condition": prep_args.condition,
                "failed_count": len(missing_columns),
                "additional_info": (
                    f"Columns not found and skipped: {missing_columns}"
                    if missing_columns
                    else None
                ),
            }

            return results, PrepActionResult(**updated_prep_args)

        except (ValidationError, OperationError):
            raise
        except Exception as e:
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

            if method == PrepMethods.row_index.value:
                results = self._remove_by_index(data, value)
            elif method == PrepMethods.condition.value:
                results = self._remove_by_condition(
                    data, condition, source_columns, value
                )
            else:
                raise ValidationError(f"Unknown removal method: {method}")  # noqa: TRY301

            updated_prep_args = {
                "action": PrepActions.remove_row.value,
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

        except (ValidationError, OperationError):
            raise
        except Exception as e:
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

        if condition == PrepRowConditions.missing.value:
            return data.filter(~pl.any_horizontal(pl.col(columns).is_null()))

        elif condition == PrepRowConditions.not_missing.value:
            return data.filter(pl.any_horizontal(pl.col(columns).is_null()))

        elif condition in [
            PrepRowConditions.equal_to.value,
            PrepRowConditions.not_equal_to.value,
        ]:
            return self._filter_by_equality(data, condition, columns, value)

        elif condition in [
            PrepRowConditions.greater_than.value,
            PrepRowConditions.greater_than_or_equal_to.value,
            PrepRowConditions.less_than.value,
            PrepRowConditions.less_than_or_equal_to.value,
        ]:
            return self._filter_by_comparison(data, condition, columns, value)

        elif condition in [
            PrepRowConditions.between.value,
            PrepRowConditions.not_between.value,
        ]:
            return self._filter_by_range(data, condition, columns, value)

        elif condition in [
            PrepRowConditions.like.value,
            PrepRowConditions.not_like.value,
        ]:
            return self._filter_by_pattern(data, condition, columns, value)

        else:
            raise ValidationError(f"Unknown condition: {condition}")

    def _filter_by_equality(
        self, data: pl.DataFrame, condition: str, columns: list[str], value: Any
    ) -> pl.DataFrame:
        """Filter by equality conditions."""
        # Ensure value is a list for is_in() to treat as literal values
        value_list = value if isinstance(value, list) else [value]

        filter_expr = pl.any_horizontal(
            [pl.col(col).is_in(value_list) for col in columns]
        )

        if condition == PrepRowConditions.not_equal_to.value:
            # "Remove rows where value is not equal to X" - keep only the
            # matching rows, i.e. drop everything the filter doesn't match.
            return data.filter(filter_expr)
        else:
            # "Remove rows where value is equal to X" - keep everything
            # that doesn't match.
            return data.filter(~filter_expr)

    def _filter_by_comparison(
        self, data: pl.DataFrame, condition: str, columns: list[str], value: Any
    ) -> pl.DataFrame:
        """Filter by comparison conditions."""
        # Handle both single values and lists
        raw_value = value[0] if isinstance(value, list) else value
        value_use = float(raw_value)

        # Build filter expression for each column
        if condition == PrepRowConditions.greater_than.value:
            filter_expr = pl.any_horizontal(
                [pl.col(col) <= value_use for col in columns]
            )
        elif condition == PrepRowConditions.greater_than_or_equal_to.value:
            filter_expr = pl.any_horizontal(
                [pl.col(col) < value_use for col in columns]
            )
        elif condition == PrepRowConditions.less_than.value:
            filter_expr = pl.any_horizontal(
                [pl.col(col) >= value_use for col in columns]
            )
        elif condition == PrepRowConditions.less_than_or_equal_to.value:
            filter_expr = pl.any_horizontal(
                [pl.col(col) > value_use for col in columns]
            )
        else:
            return data

        return data.filter(filter_expr)

    def _filter_by_range(
        self, data: pl.DataFrame, condition: str, columns: list[str], value: Any
    ) -> pl.DataFrame:
        """Filter by range conditions."""
        # Handle both single values and lists for value
        value_list = value if isinstance(value, list) else [value, value]
        if len(value_list) != 2:
            raise ValidationError(f"Expected 2 values for range, got: {value_list}")

        if condition == "value is between":
            # Keep rows outside the range
            filter_expr = pl.any_horizontal(
                [
                    (pl.col(col) < value_list[0]) | (pl.col(col) > value_list[1])
                    for col in columns
                ]
            )
        else:
            # Keep rows inside the range
            filter_expr = pl.any_horizontal(
                [
                    (pl.col(col) >= value_list[0]) & (pl.col(col) <= value_list[1])
                    for col in columns
                ]
            )

        return data.filter(filter_expr)

    def _filter_by_pattern(
        self, data: pl.DataFrame, condition: str, columns: list[str], value: str
    ) -> pl.DataFrame:
        """Filter by pattern matching."""
        if condition == PrepRowConditions.like.value:
            # Keep rows that don't match the pattern
            filter_expr = pl.all_horizontal(
                [~pl.col(col).str.contains(value) for col in columns]
            )
            return data.filter(filter_expr)
        elif condition == PrepRowConditions.not_like.value:
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
            if source_columns[0] in result_data.columns:
                null_count = result_data.select(
                    pl.col(source_columns[0]).null_count()
                ).item()
                affected_count = data.height - null_count
            else:
                # Column was removed (e.g., get_dummies), all rows affected
                affected_count = data.height
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

        except (ValidationError, OperationError):
            raise
        except Exception as e:
            raise OperationError(f"Failed to transform columns: {e}") from e

    @staticmethod
    def _parse_flexible_datetime(data: pl.DataFrame, col_name: str) -> pl.Expr:
        """Try multiple datetime formats and return the first successful one"""
        formats_to_try = [
            {
                "format": "%d%b%Y %H:%M:%S",
                "validator": r"^\d{1,2}[a-zA-Z]{3}\d{4} \d{2}:\d{2}:\d{2}$",
                "example": "18aug2025 19:49:00",
            },
            {
                "format": "%d%b%Y %H:%M",
                "validator": r"^\d{1,2}[a-zA-Z]{3}\d{4} \d{1,2}:\d{2}$",
                "example": "18aug2025 19:49",
            },
            {
                "format": "%d-%b-%Y %H:%M:%S",
                "validator": r"^\d{1,2}-[a-zA-Z]{3}-\d{4} \d{2}:\d{2}:\d{2}$",
                "example": "18-aug-2025 19:49:00",
            },
            {
                "format": "%d-%b-%Y %H:%M",
                "validator": r"^\d{1,2}-[a-zA-Z]{3}-\d{4} \d{1,2}:\d{2}$",
                "example": "18-aug-2025 19:49",
            },
            {
                "format": "%Y-%m-%d %H:%M:%S",
                "validator": r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$",
                "example": "2025-08-18 19:49:00",
            },
            {
                "format": "%Y-%m-%d %H:%M",
                "validator": r"^\d{4}-\d{2}-\d{2} \d{1,2}:\d{2}$",
                "example": "2025-08-18 19:49",
            },
            {
                "format": "%m/%d/%Y %H:%M:%S",
                "validator": r"^\d{1,2}/\d{1,2}/\d{4} \d{2}:\d{2}:\d{2}$",
                "example": "08/18/2025 19:49:00",
            },
            {
                "format": "%m/%d/%Y %H:%M",
                "validator": r"^\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}$",
                "example": "3/15/2026 17:28",
            },
            {
                "format": "%d/%m/%Y %H:%M:%S",
                "validator": r"^\d{1,2}/\d{1,2}/\d{4} \d{2}:\d{2}:\d{2}$",
                "example": "18/08/2025 19:49:00",
            },
            {
                "format": "%d/%m/%Y %H:%M",
                "validator": r"^\d{1,2}/\d{1,2}/\d{4} \d{1,2}:\d{2}$",
                "example": "18/08/2025 19:49",
            },
            {
                "format": "%Y-%m-%d",
                "validator": r"^\d{4}-\d{2}-\d{2}$",
                "example": "2025-08-18",
            },
            {
                "format": "%m/%d/%Y",
                "validator": r"^\d{1,2}/\d{1,2}/\d{4}$",
                "example": "08/18/2025",
            },
            {
                "format": "%d-%m-%Y",
                "validator": r"^\d{1,2}-\d{1,2}-\d{4}$",
                "example": "18-08-2025",
            },
        ]

        for fmt in formats_to_try:
            # check that all non-missing values match the format using regex
            validator = fmt["validator"]
            validate_col = (
                data.filter(pl.col(col_name).is_not_null())
                .select(
                    pl.col(col_name).str.contains(f"^{validator.strip('^$')}$").all()
                )
                .item()
            )
            if not validate_col:
                continue
            else:
                return pl.col(col_name).str.to_datetime(
                    format=fmt["format"], strict=False
                )

        # If all formats fail, all missing values, return Exception
        supported_formats = ", ".join([f["example"] for f in formats_to_try])
        raise ValidationError(
            f"Failed to parse datetime for column '{col_name}'. Ensure values match supported formats like: {supported_formats}"
        )

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
            PrepOperations.day_of_month.value: lambda col: col.dt.day(),
            PrepOperations.day_of_week.value: lambda col: col.dt.weekday(),
            PrepOperations.day_of_year.value: lambda col: col.dt.ordinal_day(),
            PrepOperations.date.value: lambda col: col.dt.date(),
            PrepOperations.week_of_year.value: lambda col: col.dt.week(),
            PrepOperations.month_of_year.value: lambda col: col.dt.month(),
            PrepOperations.year.value: lambda col: col.dt.year(),
            PrepOperations.quarter_of_year.value: lambda col: col.dt.quarter(),
            PrepOperations.hour.value: lambda col: col.dt.hour(),
            PrepOperations.minute.value: lambda col: col.dt.minute(),
            PrepOperations.second.value: lambda col: col.dt.second(),
        }

        if func_name in datetime_ops:
            return data.with_columns(
                datetime_ops[func_name](pl.col(column_name)).alias(column_name)
            )

        # Math operations
        math_ops = {
            PrepOperations.floor.value: lambda col: col.floor(),
            PrepOperations.ceil.value: lambda col: col.ceil(),
            PrepOperations.round.value: lambda col: col.round(0),
            PrepOperations.abs.value: lambda col: col.abs(),
        }

        if func_name in math_ops:
            return data.with_columns(
                math_ops[func_name](pl.col(column_name)).alias(column_name)
            )

        # Arithmetic operations
        if func_name in [
            PrepOperations.add.value,
            PrepOperations.subtract.value,
            PrepOperations.multiply.value,
            PrepOperations.divide.value,
        ]:
            return self._apply_arithmetic(data, column_name, func_name, value)

        # String operations
        string_ops = {
            PrepOperations.trim.value: lambda col: col.str.strip_chars(),
            PrepOperations.lower.value: lambda col: col.str.to_lowercase(),
            PrepOperations.upper.value: lambda col: col.str.to_uppercase(),
            PrepOperations.string_to_number.value: lambda col: col.cast(
                pl.Float64, strict=False
            ),
        }

        if func_name in string_ops:
            return data.with_columns(
                string_ops[func_name](pl.col(column_name)).alias(column_name)
            )

        # String to datetime
        if func_name in ["string to date", "string to datetime"]:
            return data.with_columns(
                self._parse_flexible_datetime(data, column_name).alias(column_name)
            )

        # Get dummies (one-hot encoding)
        if func_name == "get dummies":
            return data.to_dummies(columns=[column_name])

        # String replacement
        if func_name.startswith("replace by replacing"):
            return self._apply_string_replace(data, column_name, value)

        # Substring extraction
        if func_name == "substring":
            return self._apply_substring(data, column_name, value)

        # Pattern extraction
        if func_name.startswith("extract pattern"):
            return self._apply_pattern_extract(data, column_name, value)

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
            PrepOperations.add.value: lambda col, val: col + val,
            PrepOperations.subtract.value: lambda col, val: col - val,
            PrepOperations.multiply.value: lambda col, val: col * val,
            PrepOperations.divide.value: lambda col, val: col / val,
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

            if method == PrepFunctions.constant.value:
                results = self._add_constant_column(data, new_col_name, value_spec)
            elif method in [
                PrepFunctions.index.value,
                PrepFunctions.uuid.value,
                PrepFunctions.random.value,
            ]:
                results = self._add_special_column(data, method, new_col_name)
            else:
                results = self._add_computed_column(
                    data, new_col_name, method, source_columns
                )

            updated_prep_args = {
                "action": PrepActions.add_column.value,
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

        except (ValidationError, OperationError):
            raise
        except Exception as e:
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
            PrepFunctions.sum.value: lambda cols: pl.sum_horizontal(cols),
            PrepFunctions.mean.value: lambda cols: pl.mean_horizontal(cols),
            PrepFunctions.median.value: lambda cols: pl.concat_list(cols).list.median(),
            PrepFunctions.max.value: lambda cols: pl.max_horizontal(cols),
            PrepFunctions.min.value: lambda cols: pl.min_horizontal(cols),
            PrepFunctions.std.value: lambda cols: pl.concat_list(cols).list.std(),
            PrepFunctions.var.value: lambda cols: pl.concat_list(cols).list.var(),
            PrepFunctions.first.value: lambda cols: pl.concat_list(cols).list.first(),
            PrepFunctions.last.value: lambda cols: pl.concat_list(cols).list.last(),
            PrepFunctions.count.value: lambda cols: (
                pl.concat_list(cols).list.drop_nulls().list.len()
            ),
            PrepFunctions.nunique.value: lambda cols: (
                pl.concat_list(cols).list.unique().list.len()
            ),
            PrepFunctions.product.value: lambda cols: pl.fold(
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


# === PROCESSOR === #


class PrepProcessor:
    """Main processor for data preparation operations."""

    def __init__(self):
        """Initialize processor with operation handlers."""
        self.operation_handlers = {
            PrepActions.remove_column: RemoveColumnsOperation(),
            PrepActions.remove_row: RemoveRowsOperation(),
            PrepActions.transform_column: TransformColumnsOperation(),
            PrepActions.add_column: AddNewColumnOperation(),
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
    ) -> tuple[pl.DataFrame, list[PrepReapplyOutcome]]:
        """Execute a sequence of preparation actions.

        An action that fails is skipped - the data is left as it was before
        that action - so a single step made incompatible by upstream changes
        (e.g. a re-import that renames/drops a column an earlier step relied
        on) does not abort the rest of the sequence.

        Returns
        -------
            Tuple of the resulting data and one outcome per action, in order,
            reflecting what actually happened this time (a step that used to
            remove 4 columns but now only finds 2 is reported as removing 2,
            not as a failure).
        """
        result_data = data
        outcomes: list[PrepReapplyOutcome] = []

        for action in actions:
            try:
                result_data, updated_args = self.execute_single_action(
                    result_data, action
                )
                outcomes.append(
                    PrepReapplyOutcome(prep_args=updated_args, status="Successful")
                )
            except (ValidationError, OperationError) as e:
                outcomes.append(
                    PrepReapplyOutcome(
                        prep_args=action.prep_args, status="Failed", error=str(e)
                    )
                )
            except Exception as e:
                outcomes.append(
                    PrepReapplyOutcome(
                        prep_args=action.prep_args, status="Failed", error=str(e)
                    )
                )

        return result_data, outcomes


# === LOG MANAGEMENT (PRIVATE) === #


def _parse_prep_log_to_actions(prep_log_df: pl.DataFrame) -> list[PrepAction]:
    """Convert a preparation log DataFrame to a list of PrepAction objects.

    Args:
        prep_log_df: DataFrame containing prep_args column with action data

    Returns
    -------
        List of PrepAction objects ready for execution
    """
    actions = []
    for row in prep_log_df.iter_rows(named=True):
        args = row["prep_args"]
        if isinstance(args, str):
            try:
                args = json.loads(args)
            except ValueError:
                args = ast.literal_eval(args)
        prep_action = PrepActionResult(**args)
        actions.append(PrepAction.from_args(prep_action))
    return actions


def _generate_action_description(prep_args: PrepActionResult) -> str:
    """Generate human-readable description for a prep action.

    Args:
        prep_args: The preparation action result containing action details

    Returns
    -------
        Formatted description string
    """
    action_description_map = {
        PrepActions.remove_column.value: PrepConfirmationMessages.remove_columns,
        PrepActions.remove_row.value: PrepConfirmationMessages.remove_rows,
        PrepActions.transform_column.value: PrepConfirmationMessages.transform_columns,
        PrepActions.add_column.value: PrepConfirmationMessages.add_new_column,
    }
    description_func = action_description_map.get(prep_args.action)
    if description_func:
        return description_func(prep_args)
    return ""


def _convert_prep_args_to_string(df: pl.DataFrame) -> pl.DataFrame:
    """Convert prep_args column from struct to string for concatenation.

    Args:
        df: DataFrame with prep_args column

    Returns
    -------
        DataFrame with prep_args converted to string
    """
    if df.schema["prep_args"] == pl.String:
        return df
    return df.with_columns(pl.col("prep_args").struct.json_encode())


def _create_log_entry(
    action: str,
    description: str,
    prep_args: PrepActionResult,
    log_index: int,
    status: str = "Successful",
) -> pl.DataFrame:
    """Create a new log entry DataFrame for a prep action.

    Args:
        action: The action type string
        description: Human-readable description
        prep_args: The preparation action result
        log_index: Current log size (for action_index)
        status: "Successful" or "Failed" - the outcome of the most recent
            (re)application of this step

    Returns
    -------
        Single-row DataFrame with the log entry
    """
    action_index_val = f"{log_index} - {action} - {description}"
    return pl.DataFrame(
        {
            "action": [action],
            "description": [description],
            "prep_args": [prep_args],
            "action_index": [action_index_val],
            "status": [status],
        }
    )


def _ensure_status_column(df: pl.DataFrame) -> pl.DataFrame:
    """Backfill a "status" column for logs persisted before it was added."""
    if df.is_empty() or "status" in df.columns:
        return df
    return df.with_columns(pl.lit("Successful").alias("status"))


def _build_log_from_outcomes(
    existing_actions: list[PrepAction], outcomes: list[PrepReapplyOutcome]
) -> pl.DataFrame:
    """Rebuild the persisted prep log after a reapply.

    Each step's original request (`prep_args`) is kept as-is, so a column
    that reappears in a later re-import is still requested for removal.
    Only the display description and status are refreshed to reflect what
    actually happened this time.

    Args:
        existing_actions: The logged actions, as originally requested
        outcomes: The result of (re)applying each action, in the same order

    Returns
    -------
        A fresh prep log DataFrame reflecting the latest reapply
    """
    entries = []
    for index, (action, outcome) in enumerate(
        zip(existing_actions, outcomes, strict=True)
    ):
        if outcome.status == "Failed":
            description = f"✗ Failed to reapply: {outcome.error}"
        else:
            description = _generate_action_description(outcome.prep_args)

        entries.append(
            _create_log_entry(
                action.prep_args.action,
                description,
                action.prep_args,
                index,
                outcome.status,
            )
        )

    return pl.concat([_convert_prep_args_to_string(e) for e in entries])


def _append_to_prep_log(
    existing_log: pl.DataFrame, new_entry: pl.DataFrame
) -> pl.DataFrame:
    """Append a new entry to the preparation log.

    Args:
        existing_log: Current log DataFrame (may be empty)
        new_entry: New log entry to append

    Returns
    -------
        Updated log DataFrame
    """
    if existing_log.is_empty():
        return new_entry
    existing_log_str = _ensure_status_column(_convert_prep_args_to_string(existing_log))
    new_entry_str = _convert_prep_args_to_string(new_entry)
    return pl.concat([existing_log_str, new_entry_str])


def _reapply_all_actions(
    project_id: str,
    alias: str,
    prep_log_df: pl.DataFrame,
    processor: PrepProcessor,
) -> list[ReapplyFailure]:
    """Re-apply all actions from the log to the raw data.

    Args:
        project_id: Project identifier
        alias: Dataset alias
        prep_log_df: DataFrame containing the preparation log
        processor: PrepProcessor instance for executing actions

    Returns
    -------
        List of actions that were skipped because they failed to reapply.
    """
    raw_data = duckdb_get_table(project_id, alias, db_name="raw")

    if prep_log_df.is_empty():
        duckdb_save_table(project_id, raw_data, alias, db_name="prep")
        return []

    existing_actions = _parse_prep_log_to_actions(prep_log_df)
    result_data, outcomes = processor.execute_all_actions(raw_data, existing_actions)
    duckdb_save_table(project_id, result_data, alias, db_name="prep")

    refreshed_log = _build_log_from_outcomes(existing_actions, outcomes)
    duckdb_save_table(project_id, refreshed_log, f"prep_log_{alias}", db_name="logs")

    return [
        ReapplyFailure(
            step=_generate_action_description(outcome.prep_args), reason=outcome.error
        )
        for outcome in outcomes
        if outcome.status == "Failed"
    ]


def _apply_single_action(
    project_id: str,
    alias: str,
    prep_args: PrepActionResult,
    prep_log_df: pl.DataFrame,
    processor: PrepProcessor,
) -> None:
    """Apply a single new action and update the log.

    Args:
        project_id: Project identifier
        alias: Dataset alias
        prep_args: The preparation action to apply
        prep_log_df: Current preparation log DataFrame
        processor: PrepProcessor instance for executing actions
    """
    prep_data = duckdb_get_table(project_id, alias, db_name="prep")

    new_action = PrepAction.from_args(prep_args)
    result_data, updated_prep_args = processor.execute_single_action(
        prep_data, new_action
    )

    action = updated_prep_args.action
    description = _generate_action_description(updated_prep_args)

    new_entry = _create_log_entry(
        action, description, updated_prep_args, prep_log_df.height
    )
    updated_log = _append_to_prep_log(prep_log_df, new_entry)

    duckdb_save_table(project_id, updated_log, f"prep_log_{alias}", db_name="logs")
    duckdb_save_table(project_id, result_data, alias, db_name="prep")


# === PUBLIC API === #


def prep_apply_action(
    project_id: str,
    alias: str,
    prep_args: PrepActionResult | None = None,
) -> list[ReapplyFailure]:
    """Apply data preparation action to dataset.

    When prep_args is provided, applies the single new action to the current
    prepared data and updates the log. When prep_args is None, re-applies all
    actions from the log to the raw data.

    Args:
        project_id: Project identifier
        alias: Dataset alias
        prep_args: Optional action to apply. If None, re-applies all logged actions.

    Returns
    -------
        List of actions skipped while re-applying the full log. Always empty
        when applying a single new action (prep_args is not None).

    Raises
    ------
        ValidationError: If action/description validation fails (only when
            applying a single new action)
        OperationError: If data operation fails (only when applying a single
            new action)
    """
    processor = PrepProcessor()
    prep_log_df = duckdb_get_table(project_id, f"prep_log_{alias}", db_name="logs")

    if prep_args is None:
        return _reapply_all_actions(project_id, alias, prep_log_df, processor)

    _apply_single_action(project_id, alias, prep_args, prep_log_df, processor)
    return []
