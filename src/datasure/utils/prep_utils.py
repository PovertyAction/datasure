from dataclasses import dataclass
from typing import ClassVar

from datasure.models.enums import (
    PrepActions,
    PrepFunctions,
    PrepMethods,
    PrepOperations,
    PrepRowConditions,
)


@dataclass
class PrepActionResult:
    """Data class to hold the result of a prep action for message formatting."""

    action: str
    column_names: str | list[str] | None = None
    affected_count: int | None = None
    remaining_count: int | None = None
    value: str | list | None = None
    method: str | None = None
    source_columns: str | list[str] | None = None
    condition: str | None = None
    failed_count: int | None = 0
    additional_info: str | None = None


class PrepDescriptions:
    """Class containing user-friendly descriptions for all data prep functions."""

    # Main Actions
    MAIN_ACTIONS: ClassVar[dict[str, str]] = {
        PrepActions.transform_column.value: "Apply functions to modify existing column values while keeping the same column structure",
        PrepActions.add_column.value: "Create a new column using various calculation methods or data sources",
        PrepActions.remove_column.value: "Delete selected columns from your dataset to reduce size or remove unnecessary data",
        PrepActions.remove_row.value: "Delete specific rows based on index position or conditional criteria",
        PrepActions.redact_column.value: "Mask all values in selected columns with a redaction label (e.g. [PERSON]) to remove PII",
    }

    # Add Column Methods
    ADD_METHODS: ClassVar[dict[str, str]] = {
        PrepFunctions.constant.value: "Add a column with the same value in every row",
        PrepFunctions.sum.value: "Add a column containing the sum of values from selected columns",
        PrepFunctions.mean.value: "Add a column containing the average of values from selected columns",
        PrepFunctions.median.value: "Add a column containing the middle value from selected columns",
        PrepFunctions.min.value: "Add a column containing the smallest value from selected columns",
        PrepFunctions.max.value: "Add a column containing the largest value from selected columns",
        PrepFunctions.std.value: "Add a column containing the standard deviation of values from selected columns",
        PrepFunctions.var.value: "Add a column containing the variance of values from selected columns",
        PrepFunctions.first.value: "Add a column containing the first value from selected columns",
        PrepFunctions.last.value: "Add a column containing the last value from selected columns",
        PrepFunctions.count.value: "Add a column containing the count of non-null values from selected columns",
        PrepFunctions.nunique.value: "Add a column containing the count of unique values from selected columns",
        PrepFunctions.product.value: "Add a column containing the product (multiplication) of values from selected columns",
        PrepFunctions.diff.value: "Add a column containing the difference between two selected columns",
        PrepFunctions.quotient.value: "Add a column containing the division result between two selected columns",
        PrepFunctions.index.value: "Add a column containing row index numbers or custom indexing",
        PrepFunctions.uuid.value: "Add a column containing unique identifiers for each row",
        PrepFunctions.random.value: "Add a column containing randomly generated values",
    }

    # Row Deletion Methods
    DEL_METHODS: ClassVar[dict[str, str]] = {
        PrepMethods.row_index.value: "Remove rows using their position numbers (e.g., rows 1, 5, 10)",
        PrepMethods.condition.value: "Remove rows that meet specified criteria (e.g., where age > 65)",
    }

    # Function Categories
    FUNC_CATEGORIES: ClassVar[dict[str, str]] = {
        "string": "Apply text manipulation functions to clean and format text data",
        "numeric": "Apply mathematical operations to calculate and transform numerical values",
        "date": "Extract specific components from date and time values",
    }

    # String Functions
    STRING_FUNCTIONS: ClassVar[dict[str, str]] = {
        PrepOperations.trim.value: "Remove extra spaces from the beginning and end of text values",
        PrepOperations.substring.value: "Extract a portion of text from a specific position (e.g., first 5 characters)",
        PrepOperations.replace.value: "Find and replace specific text patterns with new values",
        PrepOperations.strip.value: "Remove specified characters from the beginning and end of text values",
        PrepOperations.lower.value: "Convert all text characters to lowercase",
        PrepOperations.upper.value: "Convert all text characters to uppercase",
        PrepOperations.string_to_number.value: "Convert text values to numerical format for calculations",
        PrepOperations.string_to_date.value: "Convert text values to date format for date operations",
        PrepOperations.string_to_datetime.value: "Convert text values to date and time format",
        PrepOperations.extract_pattern.value: "Find and extract specific text patterns using regular expressions",
        PrepOperations.get_dummies.value: "Convert categorical text values into separate binary columns (0/1)",
    }

    # Numeric Functions
    NUMERIC_FUNCTIONS: ClassVar[dict[str, str]] = {
        PrepOperations.add.value: "Add a constant value or another column to the selected column",
        PrepOperations.multiply.value: "Multiply values by a constant number or another column",
        PrepOperations.subtract.value: "Subtract a constant value or another column from the selected column",
        PrepOperations.divide.value: "Divide values by a constant number or another column",
        PrepOperations.round.value: "Round decimal numbers to a specified number of places",
        PrepOperations.floor.value: "Round numbers down to the nearest integer",
        PrepOperations.ceil.value: "Round numbers up to the nearest integer",
        PrepOperations.abs.value: "Convert negative numbers to positive (absolute value)",
    }

    # DateTime Functions
    DATETIME_FUNCTIONS: ClassVar[dict[str, str]] = {
        PrepOperations.second.value: "Extract the seconds component from datetime values (0-59)",
        PrepOperations.minute.value: "Extract the minutes component from datetime values (0-59)",
        PrepOperations.hour.value: "Extract the hour component from datetime values (0-23)",
        PrepOperations.day_of_month.value: "Extract the day number from dates (1-31)",
        PrepOperations.day_of_week.value: "Extract the weekday from dates (Monday=1, Sunday=7)",
        PrepOperations.day_of_year.value: "Extract the day number within the year (1-365)",
        PrepOperations.date.value: "Extract only the date portion from datetime values",
        PrepOperations.week_of_year.value: "Extract the week number within the year (1-52)",
        PrepOperations.month_of_year.value: "Extract the month number from dates (1-12)",
        PrepOperations.quarter_of_year.value: "Extract the quarter from dates (Q1, Q2, Q3, Q4)",
        PrepOperations.year.value: "Extract the year component from dates",
    }

    # Row Condition Filters
    ROW_CONDITIONS: ClassVar[dict[str, str]] = {
        PrepRowConditions.missing.value: "Select rows where the specified column has no value (null/empty)",
        PrepRowConditions.not_missing.value: "Select rows where the specified column contains any value",
        PrepRowConditions.equal_to.value: "Select rows where the column value exactly matches a specified value",
        PrepRowConditions.not_equal_to.value: "Select rows where the column value differs from a specified value",
        PrepRowConditions.greater_than.value: "Select rows where the column value exceeds a specified number",
        PrepRowConditions.less_than.value: "Select rows where the column value is below a specified number",
        PrepRowConditions.greater_than_or_equal_to.value: "Select rows where the column value meets or exceeds a specified number",
        PrepRowConditions.less_than_or_equal_to.value: "Select rows where the column value is at or below a specified number",
        PrepRowConditions.between.value: "Select rows where the column value falls within a specified range",
        PrepRowConditions.not_between.value: "Select rows where the column value falls outside a specified range",
        PrepRowConditions.like.value: "Select rows where the column value contains or matches a text pattern",
        PrepRowConditions.not_like.value: "Select rows where the column value does not contain or match a text pattern",
    }

    @classmethod
    def get_description(cls, category: str, function: str) -> str | None:
        """
        Get description for a specific function in a category.

        Args
        ----
        category : str
            The category of the function (e.g., 'string', 'numeric',
            'main_actions')
        function : str
            The specific function name

        Returns
        -------
        str or None
            Description string or None if not found
        """
        category_map = {
            "main_actions": cls.MAIN_ACTIONS,
            "add_methods": cls.ADD_METHODS,
            "del_methods": cls.DEL_METHODS,
            "func_categories": cls.FUNC_CATEGORIES,
            "string": cls.STRING_FUNCTIONS,
            "numeric": cls.NUMERIC_FUNCTIONS,
            "datetime": cls.DATETIME_FUNCTIONS,
            "row_conditions": cls.ROW_CONDITIONS,
        }

        category_dict = category_map.get(category, {})
        if not isinstance(category_dict, dict):
            return None
        return category_dict.get(function.lower())

    @classmethod
    def get_all_descriptions(cls) -> dict[str, dict[str, str]]:
        """
        Get all descriptions organized by category.

        Returns
        -------
        dict[str, dict[str, str]]
            All descriptions organized by category.
        """
        return {
            "main_actions": cls.MAIN_ACTIONS,
            "add_methods": cls.ADD_METHODS,
            "del_methods": cls.DEL_METHODS,
            "func_categories": cls.FUNC_CATEGORIES,
            "string": cls.STRING_FUNCTIONS,
            "numeric": cls.NUMERIC_FUNCTIONS,
            "datetime": cls.DATETIME_FUNCTIONS,
            "row_conditions": cls.ROW_CONDITIONS,
        }


class PrepConfirmationMessages:
    """Class for generating confirmation messages after prep actions are completed."""

    @staticmethod
    def _format_column_names(column_names: str | list[str] | None) -> str:
        """Format column name(s) for display in messages."""
        if column_names is None:
            return ""

        if isinstance(column_names, list):
            if len(column_names) == 0:
                return ""
            elif len(column_names) == 1:
                return f'"{column_names[0]}"'
            elif len(column_names) <= 3:
                return ", ".join([f'"{name}"' for name in column_names])
            else:
                return f"{len(column_names)} columns"
        return f'"{column_names}"' if column_names else ""

    @staticmethod
    def _pluralize(count: int | None, singular: str, plural: str | None = None) -> str:
        """Return singular or plural form based on count."""
        if count is None:
            count = 0
        if plural is None:
            plural = f"{singular}s"
        return singular if count == 1 else plural

    # Main Actions
    @classmethod
    def transform_columns(cls, result: PrepActionResult) -> str:
        """Generate message for column transformation."""
        column_display = cls._format_column_names(result.source_columns)
        row_text = cls._pluralize(result.affected_count, "row")
        method = result.method or "unknown method"
        affected_count = result.affected_count or 0
        return (
            f"✓ Column transformation applied. {column_display} updated using "
            f"{method}. {affected_count} {row_text} affected."
        )

    @classmethod
    def add_new_column(cls, result: PrepActionResult) -> str:
        """Generate message for adding new column."""
        source_display = (
            cls._format_column_names(result.source_columns)
            if result.source_columns
            else "specified parameters"
        )
        column_text = cls._pluralize(result.remaining_count, "column")
        return (
            f"✓ New column {cls._format_column_names(result.column_names)} added. "
            f"Created using {result.method} from {source_display}. "
            f"Your dataset now has {result.remaining_count} {column_text}."
        )

    @classmethod
    def remove_columns(cls, result: PrepActionResult) -> str:
        """Generate message for removing columns."""
        column_count = (
            len(result.source_columns) if isinstance(result.source_columns, list) else 1
        )
        column_text = cls._pluralize(column_count, "column")
        remaining_text = cls._pluralize(result.remaining_count, "column")
        column_display = cls._format_column_names(result.source_columns)
        return (
            f"✓ {column_count} {column_text} removed. {column_display} deleted from "
            f"your dataset. {result.remaining_count} {remaining_text} remaining."
        )

    @classmethod
    def redact_columns(cls, result: PrepActionResult) -> str:
        """Generate message for redacting columns."""
        column_count = (
            len(result.source_columns) if isinstance(result.source_columns, list) else 1
        )
        column_text = cls._pluralize(column_count, "column")
        column_display = cls._format_column_names(result.source_columns)
        method = (result.method or "mask").lower()
        how = {
            "hash": "replaced with salted hash pseudonyms",
            "code": "replaced with category codes",
        }.get(method, "masked with a redaction label")
        return (
            f"✓ {column_count} {column_text} redacted. All values in "
            f"{column_display} were {how}."
        )

    @classmethod
    def remove_rows(cls, result: PrepActionResult) -> str:
        """Generate message for removing rows."""
        row_text = cls._pluralize(result.affected_count, "row")
        remaining_text = cls._pluralize(result.remaining_count, "row")
        method_text = result.method if result.method else "specified criteria"
        return (
            f"✓ {result.affected_count} {row_text} removed. Deleted rows {method_text}. "
            f"{result.remaining_count} {remaining_text} remaining in your dataset."
        )

    # Add Column Methods
    @classmethod
    def add_column_constant(cls, result: PrepActionResult) -> str:
        """Generate message for adding constant column."""
        row_text = cls._pluralize(result.affected_count, "row")
        return (
            f"✓ Constant column added. {cls._format_column_names(result.column_names)} "
            f'created with value "{result.value}" for all {result.affected_count} {row_text}.'
        )

    @classmethod
    def add_column_calculation(cls, result: PrepActionResult) -> str:
        """Generate message for calculation-based column additions (sum, mean, etc.)."""
        source_display = cls._format_column_names(result.source_columns)
        calculation_text = cls._pluralize(result.affected_count, "calculation")
        method_name = result.method.capitalize() if result.method else "Calculation"
        return (
            f"✓ {method_name} column added. {cls._format_column_names(result.column_names)} "
            f"created from {source_display}. {result.affected_count} {calculation_text} completed."
        )

    @classmethod
    def add_column_index(cls, result: PrepActionResult) -> str:
        """Generate message for adding index column."""
        row_text = cls._pluralize(result.affected_count, "row")
        return (
            f"✓ Index column added. {cls._format_column_names(result.column_names)} "
            f"created with row index numbers. {result.affected_count} {row_text} indexed."
        )

    @classmethod
    def add_column_uuid(cls, result: PrepActionResult) -> str:
        """Generate message for adding UUID column."""
        return (
            f"✓ UUID column added. {cls._format_column_names(result.column_names)} "
            f"created with unique identifiers. {result.affected_count} unique IDs generated."
        )

    @classmethod
    def add_column_random(cls, result: PrepActionResult) -> str:
        """Generate message for adding random column."""
        return (
            f"✓ Random column added. {cls._format_column_names(result.column_names)} "
            f"created with random values. {result.affected_count} random values generated."
        )

    # String Functions
    @classmethod
    def string_function_basic(cls, result: PrepActionResult) -> str:
        """Generate message for basic string functions (trim, lower, upper, etc.)."""
        action_names = {
            "trim": "Text trimmed. Removed extra spaces",
            "lower": "Text converted to lowercase",
            "upper": "Text converted to uppercase",
            "strip": f'Characters stripped. Removed "{result.value}"',
        }
        action_text = action_names.get(
            result.method, f"{result.method.capitalize()} applied"
        )
        value_text = cls._pluralize(result.affected_count, "value")
        return (
            f"✓ {action_text} from {cls._format_column_names(result.column_names)}. "
            f"{result.affected_count} {value_text} updated."
        )

    @classmethod
    def string_function_conversion(cls, result: PrepActionResult) -> str:
        """Generate message for string conversion functions."""
        conversion_names = {
            "string to number": "Text converted to numbers. Now numeric format",
            "string to date": "Text converted to dates. Now date format",
            "string to datetime": "Text converted to datetime. Now datetime format",
        }
        action_text = conversion_names.get(result.method, f"{result.method} applied")
        value_text = cls._pluralize(result.affected_count, "value")
        failed_text = (
            f", {result.failed_count} failed conversions"
            if result.failed_count > 0
            else ""
        )
        return (
            f"✓ {action_text}. {cls._format_column_names(result.column_names)} updated. "
            f"{result.affected_count} {value_text} converted{failed_text}."
        )

    @classmethod
    def string_function_extract(cls, result: PrepActionResult) -> str:
        """Generate message for pattern extraction."""
        match_text = cls._pluralize(result.affected_count, "match", "matches")
        value_text = (
            cls._pluralize(result.remaining_count, "value")
            if result.remaining_count
            else ""
        )
        return (
            f"✓ Pattern extracted. Found {result.value} in {cls._format_column_names(result.column_names)}. "
            f"{result.affected_count} {match_text} found, {result.remaining_count} {value_text} updated."
        )

    @classmethod
    def string_function_dummies(cls, result: PrepActionResult) -> str:
        """Generate message for get dummies operation."""
        column_text = cls._pluralize(result.affected_count, "column")
        return (
            f"✓ Dummy columns created. {cls._format_column_names(result.column_names)} "
            f"converted to {result.affected_count} binary {column_text}. {result.additional_info}"
        )

    # Numeric Functions
    @classmethod
    def numeric_function(cls, result: PrepActionResult) -> str:
        """Generate message for numeric functions."""
        action_names = {
            "add": f"Addition applied. Added {result.value}",
            "multiply": f"Multiplication applied. Multiplied by {result.value}",
            "subtract": f"Subtraction applied. Subtracted {result.value}",
            "divide": f"Division applied. Divided by {result.value}",
            "round": f"Numbers rounded to {result.value} decimal places",
            "floor": "Numbers rounded down to nearest integer",
            "ceil": "Numbers rounded up to nearest integer",
            "abs": "Absolute values applied. Converted to positive values",
        }
        action_text = action_names.get(
            result.method, f"{result.method.capitalize()} applied"
        )
        calculation_text = cls._pluralize(result.affected_count, "calculation")
        return (
            f"✓ {action_text} to {cls._format_column_names(result.column_names)}. "
            f"{result.affected_count} {calculation_text} completed."
        )

    # DateTime Functions
    @classmethod
    def datetime_function(cls, result: PrepActionResult) -> str:
        """Generate message for datetime extraction functions."""
        extraction_names = {
            PrepOperations.second.value: "Seconds extracted. Now shows seconds (0-59)",
            PrepOperations.minute.value: "Minutes extracted. Now shows minutes (0-59)",
            PrepOperations.hour.value: "Hours extracted. Now shows hours (0-23)",
            PrepOperations.day_of_month.value: "Day of month extracted. Now shows day numbers (1-31)",
            PrepOperations.day_of_week.value: "Day of week extracted. Now shows weekday numbers",
            PrepOperations.day_of_year.value: "Day of year extracted. Now shows day numbers (1-365)",
            PrepOperations.date.value: "Date extracted. Now shows date only (without time)",
            PrepOperations.week_of_year.value: "Week of year extracted. Now shows week numbers (1-52)",
            PrepOperations.month_of_year.value: "Month extracted. Now shows month numbers (1-12)",
            PrepOperations.quarter_of_year.value: "Quarter extracted. Now shows quarters (1-4)",
            PrepOperations.year.value: "Year extracted. Now shows year values",
        }

        action_text = extraction_names.get(
            result.method, f"{result.method.capitalize()} extracted"
        )
        value_text = cls._pluralize(result.affected_count, "value")
        return (
            f"✓ {action_text}. {cls._format_column_names(result.column_names)} updated. "
            f"{result.affected_count} {value_text} extracted."
        )

    # Row Deletion Methods
    @classmethod
    def delete_by_index(cls, result: PrepActionResult) -> str:
        """Generate message for deleting rows by index."""
        row_text = cls._pluralize(result.remaining_count, "row")
        return (
            f"✓ Rows deleted by index. Removed rows {result.additional_info}. "
            f"{result.remaining_count} {row_text} remaining in your dataset."
        )

    @classmethod
    def delete_by_condition(cls, result: PrepActionResult) -> str:
        """Generate message for deleting rows by condition."""
        deleted_text = cls._pluralize(result.affected_count, "row")
        remaining_text = cls._pluralize(result.remaining_count, "row")
        return (
            f"✓ Rows deleted by condition. Removed {result.affected_count} {deleted_text} "
            f"where {result.condition}. {result.remaining_count} {remaining_text} remaining."
        )

    # Add column method dispatch
    _ADD_COLUMN_HANDLERS: ClassVar[dict] = {
        PrepFunctions.constant.value: "add_column_constant",
        PrepFunctions.index.value: "add_column_index",
        PrepFunctions.uuid.value: "add_column_uuid",
        PrepFunctions.random.value: "add_column_random",
    }

    # Action-to-handler dispatch for transform functions
    _ACTION_HANDLERS: ClassVar[dict] = {
        # String basic
        PrepOperations.trim.value: "string_function_basic",
        PrepOperations.lower.value: "string_function_basic",
        PrepOperations.upper.value: "string_function_basic",
        PrepOperations.strip.value: "string_function_basic",
        # String conversion
        PrepOperations.string_to_number.value: "string_function_conversion",
        PrepOperations.string_to_date.value: "string_function_conversion",
        PrepOperations.string_to_datetime.value: "string_function_conversion",
        PrepOperations.extract_pattern.value: "string_function_extract",
        PrepOperations.get_dummies.value: "string_function_dummies",
        # Numeric
        PrepOperations.add.value: "numeric_function",
        PrepOperations.multiply.value: "numeric_function",
        PrepOperations.subtract.value: "numeric_function",
        PrepOperations.divide.value: "numeric_function",
        PrepOperations.round.value: "numeric_function",
        PrepOperations.floor.value: "numeric_function",
        PrepOperations.ceil.value: "numeric_function",
        PrepOperations.abs.value: "numeric_function",
        # DateTime
        PrepOperations.second.value: "datetime_function",
        PrepOperations.minute.value: "datetime_function",
        PrepOperations.hour.value: "datetime_function",
        PrepOperations.day_of_month.value: "datetime_function",
        PrepOperations.day_of_week.value: "datetime_function",
        PrepOperations.day_of_year.value: "datetime_function",
        PrepOperations.date.value: "datetime_function",
        PrepOperations.week_of_year.value: "datetime_function",
        PrepOperations.month_of_year.value: "datetime_function",
        PrepOperations.quarter_of_year.value: "datetime_function",
        PrepOperations.year.value: "datetime_function",
    }

    @classmethod
    def _resolve_add_column(cls, result: PrepActionResult) -> str:
        """Resolve the handler for add column actions based on method."""
        method = result.method.lower() if result.method else ""
        handler_name = cls._ADD_COLUMN_HANDLERS.get(method, "add_column_calculation")
        return getattr(cls, handler_name)(result)

    @classmethod
    def _resolve_remove_row(cls, result: PrepActionResult) -> str:
        """Resolve the handler for remove row actions based on method."""
        method = result.method.lower() if result.method else ""
        if method == PrepMethods.row_index.value:
            return cls.delete_by_index(result)
        return cls.delete_by_condition(result)

    # Main action dispatch
    _MAIN_ACTION_HANDLERS: ClassVar[dict] = {
        PrepActions.transform_column.value: "transform_column",
        PrepActions.add_column.value: "_resolve_add_column",
        PrepActions.remove_column.value: "remove_columns",
        PrepActions.remove_row.value: "_resolve_remove_row",
        PrepActions.redact_column.value: "redact_columns",
    }

    @classmethod
    def generate_message(cls, result: PrepActionResult) -> str:
        """
        Generate appropriate confirmation message based on action and method.

        Args
        ----
        result : PrepActionResult
            PrepActionResult containing action details

        Returns
        -------
        str
            Formatted confirmation message string
        """
        action = result.action.lower()

        # Check main actions first
        main_handler = cls._MAIN_ACTION_HANDLERS.get(action)
        if main_handler:
            return getattr(cls, main_handler)(result)

        # Check transform function actions
        func_handler = cls._ACTION_HANDLERS.get(action)
        if func_handler:
            return getattr(cls, func_handler)(result)

        # Generic fallback
        return (
            f"✓ {action.capitalize()} completed. "
            f"{result.affected_count} items processed."
        )
