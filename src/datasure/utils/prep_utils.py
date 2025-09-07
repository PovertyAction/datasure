from dataclasses import dataclass
from typing import ClassVar


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
        "transform column(s)": "Apply functions to modify existing column values while keeping the same column structure",
        "add new column": "Create a new column using various calculation methods or data sources",
        "remove column(s)": "Delete selected columns from your dataset to reduce size or remove unnecessary data",
        "remove row(s)": "Delete specific rows based on index position or conditional criteria",
    }

    # Add Column Methods
    ADD_METHODS: ClassVar[dict[str, str]] = {
        "constant": "Add a column with the same value in every row",
        "sum": "Add a column containing the sum of values from selected columns",
        "mean": "Add a column containing the average of values from selected columns",
        "median": "Add a column containing the middle value from selected columns",
        "min": "Add a column containing the smallest value from selected columns",
        "max": "Add a column containing the largest value from selected columns",
        "std": "Add a column containing the standard deviation of values from selected columns",
        "var": "Add a column containing the variance of values from selected columns",
        "first": "Add a column containing the first value from selected columns",
        "last": "Add a column containing the last value from selected columns",
        "count": "Add a column containing the count of non-null values from selected columns",
        "nunique": "Add a column containing the count of unique values from selected columns",
        "product": "Add a column containing the product (multiplication) of values from selected columns",
        "diff": "Add a column containing the difference between two selected columns",
        "quotient": "Add a column containing the division result between two selected columns",
        "index": "Add a column containing row index numbers or custom indexing",
        "uuid": "Add a column containing unique identifiers for each row",
        "random": "Add a column containing randomly generated values",
    }

    # Row Deletion Methods
    DEL_METHODS: ClassVar[dict[str, str]] = {
        "by row index": "Remove rows using their position numbers (e.g., rows 1, 5, 10)",
        "by condition": "Remove rows that meet specified criteria (e.g., where age > 65)",
    }

    # Function Categories
    FUNC_CATEGORIES: ClassVar[dict[str, str]] = {
        "string": "Apply text manipulation functions to clean and format text data",
        "numeric": "Apply mathematical operations to calculate and transform numerical values",
        "date": "Extract specific components from date and time values",
    }

    # String Functions
    STRING_FUNCTIONS: ClassVar[dict[str, str]] = {
        "trim": "Remove extra spaces from the beginning and end of text values",
        "substring": "Extract a portion of text from a specific position (e.g., first 5 characters)",
        "replace": "Find and replace specific text patterns with new values",
        "strip": "Remove specified characters from the beginning and end of text values",
        "lower": "Convert all text characters to lowercase",
        "upper": "Convert all text characters to uppercase",
        "string to number": "Convert text values to numerical format for calculations",
        "string to date": "Convert text values to date format for date operations",
        "string to datetime": "Convert text values to date and time format",
        "extract pattern": "Find and extract specific text patterns using regular expressions",
        "get dummies": "Convert categorical text values into separate binary columns (0/1)",
    }

    # Numeric Functions
    NUMERIC_FUNCTIONS: ClassVar[dict[str, str]] = {
        "add": "Add a constant value or another column to the selected column",
        "multiply": "Multiply values by a constant number or another column",
        "subtract": "Subtract a constant value or another column from the selected column",
        "divide": "Divide values by a constant number or another column",
        "round": "Round decimal numbers to a specified number of places",
        "floor": "Round numbers down to the nearest integer",
        "ceil": "Round numbers up to the nearest integer",
        "abs": "Convert negative numbers to positive (absolute value)",
    }

    # DateTime Functions
    DATETIME_FUNCTIONS: ClassVar[dict[str, str]] = {
        "second": "Extract the seconds component from datetime values (0-59)",
        "minute": "Extract the minutes component from datetime values (0-59)",
        "hour": "Extract the hour component from datetime values (0-23)",
        "day of month": "Extract the day number from dates (1-31)",
        "day of week": "Extract the weekday from dates (Monday=1, Sunday=7)",
        "day of year": "Extract the day number within the year (1-365)",
        "date": "Extract only the date portion from datetime values",
        "week of year": "Extract the week number within the year (1-52)",
        "month of year": "Extract the month number from dates (1-12)",
        "quarter of year": "Extract the quarter from dates (Q1, Q2, Q3, Q4)",
        "year": "Extract the year component from dates",
    }

    # Row Condition Filters
    ROW_CONDITIONS: ClassVar[dict[str, str]] = {
        "value is missing": "Select rows where the specified column has no value (null/empty)",
        "value is not missing": "Select rows where the specified column contains any value",
        "value is equal to": "Select rows where the column value exactly matches a specified value",
        "value is not equal to": "Select rows where the column value differs from a specified value",
        "value is greater than": "Select rows where the column value exceeds a specified number",
        "value is less than": "Select rows where the column value is below a specified number",
        "value is greater than or equal to": "Select rows where the column value meets or exceeds a specified number",
        "value is less than or equal to": "Select rows where the column value is at or below a specified number",
        "value is between": "Select rows where the column value falls within a specified range",
        "value is not between": "Select rows where the column value falls outside a specified range",
        "value is like": "Select rows where the column value contains or matches a text pattern",
        "value is not like": "Select rows where the column value does not contain or match a text pattern",
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
            "second": "Seconds extracted. Now shows seconds (0-59)",
            "minute": "Minutes extracted. Now shows minutes (0-59)",
            "hour": "Hours extracted. Now shows hours (0-23)",
            "day of month": "Day of month extracted. Now shows day numbers (1-31)",
            "day of week": "Day of week extracted. Now shows weekday numbers",
            "day of year": "Day of year extracted. Now shows day numbers (1-365)",
            "date": "Date extracted. Now shows date only (without time)",
            "week of year": "Week of year extracted. Now shows week numbers (1-52)",
            "month of year": "Month extracted. Now shows month numbers (1-12)",
            "quarter of year": "Quarter extracted. Now shows quarters (1-4)",
            "year": "Year extracted. Now shows year values",
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
        method = result.method.lower() if result.method else ""

        # Main actions
        if action == "transform column(s)":
            return cls.transform_column(result)
        elif action == "add new column":
            if method == "constant":
                return cls.add_column_constant(result)
            elif method in ["index"]:
                return cls.add_column_index(result)
            elif method == "uuid":
                return cls.add_column_uuid(result)
            elif method == "random":
                return cls.add_column_random(result)
            else:
                return cls.add_column_calculation(result)
        elif action == "remove column(s)":
            return cls.remove_columns(result)
        elif action == "remove row(s)":
            if method == "by row index":
                return cls.delete_by_index(result)
            else:
                return cls.delete_by_condition(result)

        # String functions
        elif action in ["trim", "lower", "upper", "strip"]:
            return cls.string_function_basic(result)
        elif action in ["string to number", "string to date", "string to datetime"]:
            return cls.string_function_conversion(result)
        elif action == "extract pattern":
            return cls.string_function_extract(result)
        elif action == "get dummies":
            return cls.string_function_dummies(result)

        # Numeric functions
        elif action in [
            "add",
            "multiply",
            "subtract",
            "divide",
            "round",
            "floor",
            "ceil",
            "abs",
        ]:
            return cls.numeric_function(result)

        # DateTime functions
        elif action in [
            "second",
            "minute",
            "hour",
            "day of month",
            "day of week",
            "day of year",
            "date",
            "week of year",
            "month of year",
            "quarter of year",
            "year",
        ]:
            return cls.datetime_function(result)

        # Generic fallback
        else:
            return (
                f"✓ {action.capitalize()} completed. "
                f"{result.affected_count} items processed."
            )
