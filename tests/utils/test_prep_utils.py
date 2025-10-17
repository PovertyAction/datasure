import pytest  # noqa: F401

from datasure.utils.prep_utils import (
    PrepActionResult,
    PrepConfirmationMessages,
    PrepDescriptions,
)


class TestPrepActionResult:
    """Test cases for PrepActionResult dataclass."""

    def test_prep_action_result_initialization_with_defaults(self):
        """Test PrepActionResult initialization with default values."""
        result = PrepActionResult(action="test_action")

        assert result.action == "test_action"
        assert result.column_names is None
        assert result.affected_count is None
        assert result.remaining_count is None
        assert result.value is None
        assert result.method is None
        assert result.source_columns is None
        assert result.condition is None
        assert result.failed_count == 0
        assert result.additional_info is None

    def test_prep_action_result_initialization_with_all_fields(self):
        """Test PrepActionResult initialization with all fields specified."""
        result = PrepActionResult(
            action="transform column(s)",
            column_names=["col1", "col2"],
            affected_count=100,
            remaining_count=200,
            value=["old_val", "new_val"],
            method="replace",
            source_columns=["source_col"],
            condition="value > 10",
            failed_count=5,
            additional_info="Extra details",
        )

        assert result.action == "transform column(s)"
        assert result.column_names == ["col1", "col2"]
        assert result.affected_count == 100
        assert result.remaining_count == 200
        assert result.value == ["old_val", "new_val"]
        assert result.method == "replace"
        assert result.source_columns == ["source_col"]
        assert result.condition == "value > 10"
        assert result.failed_count == 5
        assert result.additional_info == "Extra details"

    def test_prep_action_result_with_different_data_types(self):
        """Test PrepActionResult with different data types for flexible fields."""
        # Test with string column names
        result1 = PrepActionResult(action="test", column_names="single_col")
        assert result1.column_names == "single_col"

        # Test with list column names
        result2 = PrepActionResult(action="test", column_names=["col1", "col2"])
        assert result2.column_names == ["col1", "col2"]

        # Test with string value
        result3 = PrepActionResult(action="test", value="string_value")
        assert result3.value == "string_value"

        # Test with list value
        result4 = PrepActionResult(action="test", value=[1, 2, 3])
        assert result4.value == [1, 2, 3]


class TestPrepDescriptions:
    """Test cases for PrepDescriptions class."""

    def test_prep_descriptions_initialization(self):
        """Test PrepDescriptions class initialization."""
        descriptions = PrepDescriptions()

        # Check that all class variables exist and are dictionaries
        assert isinstance(descriptions.MAIN_ACTIONS, dict)
        assert isinstance(descriptions.ADD_METHODS, dict)
        assert isinstance(descriptions.DEL_METHODS, dict)
        assert isinstance(descriptions.FUNC_CATEGORIES, dict)
        assert isinstance(descriptions.STRING_FUNCTIONS, dict)
        assert isinstance(descriptions.NUMERIC_FUNCTIONS, dict)
        assert isinstance(descriptions.DATETIME_FUNCTIONS, dict)
        assert isinstance(descriptions.ROW_CONDITIONS, dict)

    def test_main_actions_content(self):
        """Test MAIN_ACTIONS dictionary content."""
        descriptions = PrepDescriptions()
        expected_actions = [
            "transform column(s)",
            "add new column",
            "remove column(s)",
            "remove row(s)",
        ]

        for action in expected_actions:
            assert action in descriptions.MAIN_ACTIONS
            assert isinstance(descriptions.MAIN_ACTIONS[action], str)
            assert len(descriptions.MAIN_ACTIONS[action]) > 0

    def test_add_methods_content(self):
        """Test ADD_METHODS dictionary content."""
        descriptions = PrepDescriptions()
        expected_methods = [
            "constant",
            "sum",
            "mean",
            "median",
            "min",
            "max",
            "std",
            "var",
            "first",
            "last",
            "count",
            "nunique",
            "product",
            "diff",
            "quotient",
            "index",
            "uuid",
            "random",
        ]

        for method in expected_methods:
            assert method in descriptions.ADD_METHODS
            assert isinstance(descriptions.ADD_METHODS[method], str)

    def test_del_methods_content(self):
        """Test DEL_METHODS dictionary content."""
        descriptions = PrepDescriptions()
        expected_methods = ["by row index", "by condition"]

        for method in expected_methods:
            assert method in descriptions.DEL_METHODS
            assert isinstance(descriptions.DEL_METHODS[method], str)

    def test_func_categories_content(self):
        """Test FUNC_CATEGORIES dictionary content."""
        descriptions = PrepDescriptions()
        expected_categories = ["string", "numeric", "date"]

        for category in expected_categories:
            assert category in descriptions.FUNC_CATEGORIES
            assert isinstance(descriptions.FUNC_CATEGORIES[category], str)

    def test_string_functions_content(self):
        """Test STRING_FUNCTIONS dictionary content."""
        descriptions = PrepDescriptions()
        expected_functions = [
            "trim",
            "substring",
            "replace",
            "strip",
            "lower",
            "upper",
            "string to number",
            "string to date",
            "string to datetime",
            "extract pattern",
            "get dummies",
        ]

        for function in expected_functions:
            assert function in descriptions.STRING_FUNCTIONS
            assert isinstance(descriptions.STRING_FUNCTIONS[function], str)

    def test_numeric_functions_content(self):
        """Test NUMERIC_FUNCTIONS dictionary content."""
        descriptions = PrepDescriptions()
        expected_functions = [
            "add",
            "multiply",
            "subtract",
            "divide",
            "round",
            "floor",
            "ceil",
            "abs",
        ]

        for function in expected_functions:
            assert function in descriptions.NUMERIC_FUNCTIONS
            assert isinstance(descriptions.NUMERIC_FUNCTIONS[function], str)

    def test_datetime_functions_content(self):
        """Test DATETIME_FUNCTIONS dictionary content."""
        descriptions = PrepDescriptions()
        expected_functions = [
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
        ]

        for function in expected_functions:
            assert function in descriptions.DATETIME_FUNCTIONS
            assert isinstance(descriptions.DATETIME_FUNCTIONS[function], str)

    def test_row_conditions_content(self):
        """Test ROW_CONDITIONS dictionary content."""
        descriptions = PrepDescriptions()
        expected_conditions = [
            "value is missing",
            "value is not missing",
            "value is equal to",
            "value is not equal to",
            "value is greater than",
            "value is less than",
            "value is greater than or equal to",
            "value is less than or equal to",
            "value is between",
            "value is not between",
            "value is like",
            "value is not like",
        ]

        for condition in expected_conditions:
            assert condition in descriptions.ROW_CONDITIONS
            assert isinstance(descriptions.ROW_CONDITIONS[condition], str)

    def test_get_description_all_categories(self):
        """Test get_description method with all valid categories."""
        descriptions = PrepDescriptions()

        # Test all categories
        test_cases = [
            ("main_actions", "transform column(s)"),
            ("add_methods", "constant"),
            ("del_methods", "by row index"),
            ("func_categories", "string"),
            ("string", "trim"),
            ("numeric", "add"),
            ("datetime", "hour"),
            ("row_conditions", "value is missing"),
        ]

        for category, function in test_cases:
            result = descriptions.get_description(category, function)
            assert result is not None
            assert isinstance(result, str)
            assert len(result) > 0

    def test_get_description_case_insensitive(self):
        """Test get_description method is case insensitive for function names."""
        descriptions = PrepDescriptions()

        # Test with uppercase function name
        result_upper = descriptions.get_description("string", "TRIM")
        result_lower = descriptions.get_description("string", "trim")
        result_mixed = descriptions.get_description("string", "Trim")

        assert result_upper == result_lower == result_mixed
        assert result_upper is not None

    def test_get_description_invalid_category(self):
        """Test get_description method with invalid category."""
        descriptions = PrepDescriptions()

        result = descriptions.get_description("invalid_category", "some_function")
        assert result is None

    def test_get_description_invalid_function(self):
        """Test get_description method with invalid function name."""
        descriptions = PrepDescriptions()

        result = descriptions.get_description("string", "invalid_function")
        assert result is None

    def test_get_description_non_dict_category(self):
        """Test get_description with non-dict category value."""
        descriptions = PrepDescriptions()

        # This tests the isinstance check in get_description
        # We can't easily trigger this without modifying the class,
        # but we can test edge cases
        result = descriptions.get_description("string", "")
        assert result is None

    def test_get_all_descriptions_structure(self):
        """Test get_all_descriptions method returns expected structure."""
        descriptions = PrepDescriptions()

        all_descriptions = descriptions.get_all_descriptions()

        # Check return type
        assert isinstance(all_descriptions, dict)

        # Check expected keys
        expected_keys = [
            "main_actions",
            "add_methods",
            "del_methods",
            "func_categories",
            "string",
            "numeric",
            "datetime",
            "row_conditions",
        ]

        for key in expected_keys:
            assert key in all_descriptions
            assert isinstance(all_descriptions[key], dict)

    def test_get_all_descriptions_content_integrity(self):
        """Test that get_all_descriptions returns same content as class variables."""
        descriptions = PrepDescriptions()

        all_descriptions = descriptions.get_all_descriptions()

        # Verify content matches class variables
        assert all_descriptions["main_actions"] == descriptions.MAIN_ACTIONS
        assert all_descriptions["add_methods"] == descriptions.ADD_METHODS
        assert all_descriptions["del_methods"] == descriptions.DEL_METHODS
        assert all_descriptions["func_categories"] == descriptions.FUNC_CATEGORIES
        assert all_descriptions["string"] == descriptions.STRING_FUNCTIONS
        assert all_descriptions["numeric"] == descriptions.NUMERIC_FUNCTIONS
        assert all_descriptions["datetime"] == descriptions.DATETIME_FUNCTIONS
        assert all_descriptions["row_conditions"] == descriptions.ROW_CONDITIONS


class TestPrepConfirmationMessages:
    """Test cases for PrepConfirmationMessages class."""

    def test_format_column_names_single_string(self):
        """Test _format_column_names with single string."""
        result = PrepConfirmationMessages._format_column_names("column1")
        assert result == '"column1"'

    def test_format_column_names_empty_string(self):
        """Test _format_column_names with empty string."""
        result = PrepConfirmationMessages._format_column_names("")
        assert result == ""

    def test_format_column_names_none(self):
        """Test _format_column_names with None."""
        result = PrepConfirmationMessages._format_column_names(None)
        assert result == ""

    def test_format_column_names_empty_list(self):
        """Test _format_column_names with empty list."""
        result = PrepConfirmationMessages._format_column_names([])
        assert result == ""

    def test_format_column_names_single_item_list(self):
        """Test _format_column_names with single item list."""
        result = PrepConfirmationMessages._format_column_names(["column1"])
        assert result == '"column1"'

    def test_format_column_names_multiple_items_list(self):
        """Test _format_column_names with multiple items list."""
        result = PrepConfirmationMessages._format_column_names(["col1", "col2", "col3"])
        assert result == '"col1", "col2", "col3"'

    def test_format_column_names_many_items_list(self):
        """Test _format_column_names with many items list (>3)."""
        columns = ["col1", "col2", "col3", "col4", "col5"]
        result = PrepConfirmationMessages._format_column_names(columns)
        assert result == "5 columns"

    def test_pluralize_singular(self):
        """Test _pluralize method with count of 1."""
        result = PrepConfirmationMessages._pluralize(1, "row")
        assert result == "row"

    def test_pluralize_plural_default(self):
        """Test _pluralize method with count > 1 using default plural."""
        result = PrepConfirmationMessages._pluralize(5, "row")
        assert result == "rows"

    def test_pluralize_plural_custom(self):
        """Test _pluralize method with custom plural form."""
        result = PrepConfirmationMessages._pluralize(2, "child", "children")
        assert result == "children"

    def test_pluralize_zero(self):
        """Test _pluralize method with count of 0."""
        result = PrepConfirmationMessages._pluralize(0, "item")
        assert result == "items"

    def test_pluralize_none(self):
        """Test _pluralize method with None count."""
        result = PrepConfirmationMessages._pluralize(None, "item")
        assert result == "items"

    def test_transform_columns_message(self):
        """Test transform_columns message generation."""
        result = PrepActionResult(
            action="transform column(s)",
            source_columns=["column1"],
            affected_count=100,
            method="trim",
        )

        message = PrepConfirmationMessages.transform_columns(result)

        assert "✓ Column transformation applied" in message
        assert '"column1"' in message
        assert "trim" in message
        assert "100 rows affected" in message

    def test_transform_columns_message_no_method(self):
        """Test transform_columns message with no method."""
        result = PrepActionResult(
            action="transform column(s)",
            source_columns=["column1"],
            affected_count=50,
            method=None,
        )

        message = PrepConfirmationMessages.transform_columns(result)

        assert "unknown method" in message
        assert "50 rows affected" in message

    def test_add_new_column_message(self):
        """Test add_new_column message generation."""
        result = PrepActionResult(
            action="add new column",
            column_names="new_col",
            remaining_count=10,
            method="constant",
            source_columns=["source_col"],
        )

        message = PrepConfirmationMessages.add_new_column(result)

        assert "✓ New column" in message
        assert '"new_col"' in message
        assert "constant" in message
        assert "10 columns" in message

    def test_add_new_column_message_no_source(self):
        """Test add_new_column message with no source columns."""
        result = PrepActionResult(
            action="add new column",
            column_names="new_col",
            remaining_count=5,
            method="index",
            source_columns=None,
        )

        message = PrepConfirmationMessages.add_new_column(result)

        assert "specified parameters" in message

    def test_remove_columns_message(self):
        """Test remove_columns message generation."""
        result = PrepActionResult(
            action="remove column(s)",
            source_columns=["col1", "col2"],
            remaining_count=8,
        )

        message = PrepConfirmationMessages.remove_columns(result)

        assert "✓ 2 columns removed" in message
        assert '"col1", "col2"' in message
        assert "8 columns remaining" in message

    def test_remove_columns_message_single_column(self):
        """Test remove_columns message with single column."""
        result = PrepActionResult(
            action="remove column(s)", source_columns="single_col", remaining_count=5
        )

        message = PrepConfirmationMessages.remove_columns(result)

        assert "✓ 1 column removed" in message
        assert "5 columns remaining" in message

    def test_remove_rows_message(self):
        """Test remove_rows message generation."""
        result = PrepActionResult(
            action="remove row(s)",
            affected_count=25,
            remaining_count=75,
            method="by condition",
        )

        message = PrepConfirmationMessages.remove_rows(result)

        assert "✓ 25 rows removed" in message
        assert "by condition" in message
        assert "75 rows remaining" in message

    def test_remove_rows_message_no_method(self):
        """Test remove_rows message with no method."""
        result = PrepActionResult(
            action="remove row(s)", affected_count=10, remaining_count=90, method=None
        )

        message = PrepConfirmationMessages.remove_rows(result)

        assert "specified criteria" in message

    def test_add_column_constant_message(self):
        """Test add_column_constant message generation."""
        result = PrepActionResult(
            action="add new column",
            column_names="const_col",
            affected_count=100,
            value="default_value",
        )

        message = PrepConfirmationMessages.add_column_constant(result)

        assert "✓ Constant column added" in message
        assert '"const_col"' in message
        assert '"default_value"' in message
        assert "100 rows" in message

    def test_add_column_calculation_message(self):
        """Test add_column_calculation message generation."""
        result = PrepActionResult(
            action="add new column",
            column_names="calc_col",
            affected_count=50,
            method="sum",
            source_columns=["col1", "col2"],
        )

        message = PrepConfirmationMessages.add_column_calculation(result)

        assert "✓ Sum column added" in message
        assert '"calc_col"' in message
        assert "50 calculations" in message

    def test_add_column_calculation_no_method(self):
        """Test add_column_calculation with no method."""
        result = PrepActionResult(
            action="add new column",
            column_names="calc_col",
            affected_count=30,
            method=None,
            source_columns=["col1"],
        )

        message = PrepConfirmationMessages.add_column_calculation(result)

        assert "✓ Calculation column added" in message

    def test_add_column_index_message(self):
        """Test add_column_index message generation."""
        result = PrepActionResult(
            action="add new column", column_names="index_col", affected_count=200
        )

        message = PrepConfirmationMessages.add_column_index(result)

        assert "✓ Index column added" in message
        assert '"index_col"' in message
        assert "200 rows indexed" in message

    def test_add_column_uuid_message(self):
        """Test add_column_uuid message generation."""
        result = PrepActionResult(
            action="add new column", column_names="uuid_col", affected_count=150
        )

        message = PrepConfirmationMessages.add_column_uuid(result)

        assert "✓ UUID column added" in message
        assert '"uuid_col"' in message
        assert "150 unique IDs generated" in message

    def test_add_column_random_message(self):
        """Test add_column_random message generation."""
        result = PrepActionResult(
            action="add new column", column_names="random_col", affected_count=80
        )

        message = PrepConfirmationMessages.add_column_random(result)

        assert "✓ Random column added" in message
        assert '"random_col"' in message
        assert "80 random values generated" in message

    def test_string_function_basic_all_types(self):
        """Test string_function_basic for all basic string operations."""
        operations = ["trim", "lower", "upper", "strip"]

        for operation in operations:
            result = PrepActionResult(
                action=operation,
                column_names="text_col",
                affected_count=60,
                method=operation,
                value='"' if operation == "strip" else None,
            )

            message = PrepConfirmationMessages.string_function_basic(result)

            assert "✓" in message
            assert '"text_col"' in message
            assert "60 values updated" in message

    def test_string_function_basic_unknown_method(self):
        """Test string_function_basic with unknown method."""
        result = PrepActionResult(
            action="unknown_string_op",
            column_names="text_col",
            affected_count=30,
            method="unknown_string_op",
        )

        message = PrepConfirmationMessages.string_function_basic(result)

        assert "Unknown_string_op applied" in message

    def test_string_function_conversion_all_types(self):
        """Test string_function_conversion for all conversion types."""
        conversions = ["string to number", "string to date", "string to datetime"]

        for conversion in conversions:
            result = PrepActionResult(
                action=conversion,
                column_names="convert_col",
                affected_count=40,
                failed_count=5,
                method=conversion,
            )

            message = PrepConfirmationMessages.string_function_conversion(result)

            assert "✓" in message
            assert '"convert_col"' in message
            assert "40 values converted" in message
            assert "5 failed conversions" in message

    def test_string_function_conversion_no_failures(self):
        """Test string_function_conversion with no failures."""
        result = PrepActionResult(
            action="string to number",
            column_names="convert_col",
            affected_count=100,
            failed_count=0,
            method="string to number",
        )

        message = PrepConfirmationMessages.string_function_conversion(result)

        assert "100 values converted" in message
        assert "failed conversions" not in message

    def test_string_function_conversion_unknown_method(self):
        """Test string_function_conversion with unknown method."""
        result = PrepActionResult(
            action="unknown_conversion",
            column_names="convert_col",
            affected_count=20,
            method="unknown_conversion",
        )

        message = PrepConfirmationMessages.string_function_conversion(result)

        assert "unknown_conversion applied" in message

    def test_string_function_extract_message(self):
        """Test string_function_extract message generation."""
        result = PrepActionResult(
            action="extract pattern",
            column_names="text_col",
            affected_count=15,
            remaining_count=85,
            value="[0-9]+",
        )

        message = PrepConfirmationMessages.string_function_extract(result)

        assert "✓ Pattern extracted" in message
        assert "[0-9]+" in message
        assert '"text_col"' in message
        assert "15 matches found" in message
        assert "85 values updated" in message

    def test_string_function_extract_no_remaining_count(self):
        """Test string_function_extract with no remaining count."""
        result = PrepActionResult(
            action="extract pattern",
            column_names="text_col",
            affected_count=10,
            remaining_count=None,
            value="pattern",
        )

        message = PrepConfirmationMessages.string_function_extract(result)

        assert "10 matches found" in message

    def test_string_function_dummies_message(self):
        """Test string_function_dummies message generation."""
        result = PrepActionResult(
            action="get dummies",
            column_names="category_col",
            affected_count=5,
            additional_info="Categories: A, B, C, D, E",
        )

        message = PrepConfirmationMessages.string_function_dummies(result)

        assert "✓ Dummy columns created" in message
        assert '"category_col"' in message
        assert "5 binary columns" in message
        assert "Categories: A, B, C, D, E" in message

    def test_numeric_function_all_types(self):
        """Test numeric_function for all numeric operations."""
        operations = [
            ("add", "Addition applied. Added 5"),
            ("multiply", "Multiplication applied. Multiplied by 2"),
            ("subtract", "Subtraction applied. Subtracted 3"),
            ("divide", "Division applied. Divided by 4"),
            ("round", "Numbers rounded to 2 decimal places"),
            ("floor", "Numbers rounded down to nearest integer"),
            ("ceil", "Numbers rounded up to nearest integer"),
            ("abs", "Absolute values applied. Converted to positive values"),
        ]

        for operation, expected_text in operations:
            value = (
                5
                if operation == "add"
                else (
                    2
                    if operation == "multiply"
                    else (
                        3
                        if operation == "subtract"
                        else (
                            4
                            if operation == "divide"
                            else (2 if operation == "round" else None)
                        )
                    )
                )
            )
            result = PrepActionResult(
                action=operation,
                column_names="num_col",
                affected_count=50,
                method=operation,
                value=value,
            )

            message = PrepConfirmationMessages.numeric_function(result)

            assert "✓" in message
            assert expected_text.split(".")[0] in message
            assert '"num_col"' in message
            assert "50 calculations" in message

    def test_numeric_function_unknown_method(self):
        """Test numeric_function with unknown method."""
        result = PrepActionResult(
            action="unknown_numeric",
            column_names="num_col",
            affected_count=25,
            method="unknown_numeric",
        )

        message = PrepConfirmationMessages.numeric_function(result)

        assert "Unknown_numeric applied" in message

    def test_datetime_function_all_types(self):
        """Test datetime_function for all datetime extractions."""
        extractions = [
            ("second", "Seconds extracted. Now shows seconds (0-59)"),
            ("minute", "Minutes extracted. Now shows minutes (0-59)"),
            ("hour", "Hours extracted. Now shows hours (0-23)"),
            ("day of month", "Day of month extracted. Now shows day numbers (1-31)"),
            ("day of week", "Day of week extracted. Now shows weekday numbers"),
            ("day of year", "Day of year extracted. Now shows day numbers (1-365)"),
            ("date", "Date extracted. Now shows date only (without time)"),
            ("week of year", "Week of year extracted. Now shows week numbers (1-52)"),
            ("month of year", "Month extracted. Now shows month numbers (1-12)"),
            ("quarter of year", "Quarter extracted. Now shows quarters (1-4)"),
            ("year", "Year extracted. Now shows year values"),
        ]

        for extraction, expected_text in extractions:
            result = PrepActionResult(
                action=extraction,
                column_names="date_col",
                affected_count=100,
                method=extraction,
            )

            message = PrepConfirmationMessages.datetime_function(result)

            assert "✓" in message
            assert expected_text.split(".")[0] in message
            assert '"date_col"' in message
            assert "100 values extracted" in message

    def test_datetime_function_unknown_method(self):
        """Test datetime_function with unknown method."""
        result = PrepActionResult(
            action="unknown_datetime",
            column_names="date_col",
            affected_count=75,
            method="unknown_datetime",
        )

        message = PrepConfirmationMessages.datetime_function(result)

        assert "Unknown_datetime extracted" in message

    def test_delete_by_index_message(self):
        """Test delete_by_index message generation."""
        result = PrepActionResult(
            action="remove row(s)", remaining_count=95, additional_info="1, 3, 5"
        )

        message = PrepConfirmationMessages.delete_by_index(result)

        assert "✓ Rows deleted by index" in message
        assert "Removed rows 1, 3, 5" in message
        assert "95 rows remaining" in message

    def test_delete_by_condition_message(self):
        """Test delete_by_condition message generation."""
        result = PrepActionResult(
            action="remove row(s)",
            affected_count=15,
            remaining_count=85,
            condition="age > 65",
        )

        message = PrepConfirmationMessages.delete_by_condition(result)

        assert "✓ Rows deleted by condition" in message
        assert "Removed 15 rows" in message
        assert "where age > 65" in message
        assert "85 rows remaining" in message

    def test_generate_message_transform_columns(self):
        """Test generate_message method for transform columns action."""
        result = PrepActionResult(
            action="transform column(s)",
            source_columns=["test_col"],
            affected_count=10,
            method="trim",
        )

        message = PrepConfirmationMessages.transform_columns(result)

        assert "✓ Column transformation applied" in message
        assert "trim" in message

    def test_generate_message_add_column_constant(self):
        """Test generate_message method for add constant column."""
        result = PrepActionResult(
            action="add new column",
            column_names="new_col",
            affected_count=100,
            method="constant",
            value="test_value",
        )

        message = PrepConfirmationMessages.generate_message(result)

        assert "✓ Constant column added" in message
        assert "test_value" in message

    def test_generate_message_add_column_index(self):
        """Test generate_message method for add index column."""
        result = PrepActionResult(
            action="add new column",
            column_names="index_col",
            affected_count=50,
            method="index",
        )

        message = PrepConfirmationMessages.generate_message(result)

        assert "✓ Index column added" in message

    def test_generate_message_add_column_uuid(self):
        """Test generate_message method for add UUID column."""
        result = PrepActionResult(
            action="add new column",
            column_names="uuid_col",
            affected_count=75,
            method="uuid",
        )

        message = PrepConfirmationMessages.generate_message(result)

        assert "✓ UUID column added" in message

    def test_generate_message_add_column_random(self):
        """Test generate_message method for add random column."""
        result = PrepActionResult(
            action="add new column",
            column_names="random_col",
            affected_count=60,
            method="random",
        )

        message = PrepConfirmationMessages.generate_message(result)

        assert "✓ Random column added" in message

    def test_generate_message_add_column_calculation(self):
        """Test generate_message method for add calculation column."""
        result = PrepActionResult(
            action="add new column",
            column_names="calc_col",
            affected_count=40,
            method="sum",
            source_columns=["col1", "col2"],
        )

        message = PrepConfirmationMessages.generate_message(result)

        assert "✓ Sum column added" in message

    def test_generate_message_remove_columns(self):
        """Test generate_message method for remove columns."""
        result = PrepActionResult(
            action="remove column(s)",
            source_columns=["col1", "col2"],
            remaining_count=8,
        )

        message = PrepConfirmationMessages.generate_message(result)

        assert "✓ 2 columns removed" in message

    def test_generate_message_remove_rows_by_index(self):
        """Test generate_message method for remove rows by index."""
        result = PrepActionResult(
            action="remove row(s)",
            method="by row index",
            remaining_count=90,
            additional_info="1, 5, 10",
        )

        message = PrepConfirmationMessages.generate_message(result)

        assert "✓ Rows deleted by index" in message

    def test_generate_message_remove_rows_by_condition(self):
        """Test generate_message method for remove rows by condition."""
        result = PrepActionResult(
            action="remove row(s)",
            method="by condition",
            affected_count=20,
            remaining_count=80,
            condition="value > 100",
        )

        message = PrepConfirmationMessages.generate_message(result)

        assert "✓ Rows deleted by condition" in message

    def test_generate_message_string_functions(self):
        """Test generate_message method for all string functions."""
        string_actions = ["trim", "lower", "upper", "strip"]

        for action in string_actions:
            result = PrepActionResult(
                action=action, column_names="text_col", affected_count=30, method=action
            )

            message = PrepConfirmationMessages.generate_message(result)
            assert "✓" in message

    def test_generate_message_string_conversions(self):
        """Test generate_message method for string conversion functions."""
        conversions = ["string to number", "string to date", "string to datetime"]

        for conversion in conversions:
            result = PrepActionResult(
                action=conversion,
                column_names="convert_col",
                affected_count=25,
                method=conversion,
            )

            message = PrepConfirmationMessages.generate_message(result)
            assert "✓" in message

    def test_generate_message_extract_pattern(self):
        """Test generate_message method for extract pattern."""
        result = PrepActionResult(
            action="extract pattern",
            column_names="text_col",
            affected_count=15,
            remaining_count=85,
        )

        message = PrepConfirmationMessages.generate_message(result)

        assert "✓ Pattern extracted" in message

    def test_generate_message_get_dummies(self):
        """Test generate_message method for get dummies."""
        result = PrepActionResult(
            action="get dummies", column_names="category_col", affected_count=5
        )

        message = PrepConfirmationMessages.generate_message(result)

        assert "✓ Dummy columns created" in message

    def test_generate_message_numeric_functions(self):
        """Test generate_message method for all numeric functions."""
        numeric_actions = [
            "add",
            "multiply",
            "subtract",
            "divide",
            "round",
            "floor",
            "ceil",
            "abs",
        ]

        for action in numeric_actions:
            result = PrepActionResult(
                action=action, column_names="num_col", affected_count=45, method=action
            )

            message = PrepConfirmationMessages.generate_message(result)
            assert "✓" in message

    def test_generate_message_datetime_functions(self):
        """Test generate_message method for all datetime functions."""
        datetime_actions = [
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
        ]

        for action in datetime_actions:
            result = PrepActionResult(
                action=action,
                column_names="date_col",
                affected_count=100,
                method=action,
            )

            message = PrepConfirmationMessages.generate_message(result)
            assert "✓" in message

    def test_generate_message_fallback(self):
        """Test generate_message method fallback for unknown actions."""
        result = PrepActionResult(action="unknown_action", affected_count=10)

        message = PrepConfirmationMessages.generate_message(result)

        assert "✓ Unknown_action completed" in message
        assert "10 items processed" in message
