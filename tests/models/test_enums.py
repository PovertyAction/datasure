"""Tests for datasure.models.enums module.

This module tests all enum classes, their members, values, and the
module-level constant tuples derived from enum values.
"""

import pytest

from datasure.models.enums import (
    COL_FUNC_WITH_VALUES,
    COL_METHODS_WITHOUT_VALUES,
    DEL_COND_USE_VALS,
    DEL_ROW_COND_MAX_1,
    DEL_ROW_COND_NUM_ONLY,
    DEL_ROW_COND_SAME_TYPE,
    DEL_ROW_COND_STR_ONLY,
    NumCondition,
    PrepActions,
    PrepFunctions,
    PrepMethods,
    PrepOperations,
    PrepRowConditions,
    SearchType,
    StrCondition,
)

# ============================================
# PrepActions Tests
# ============================================


class TestPrepActions:
    """Tests for the PrepActions enum."""

    def test_member_count(self):
        """Verify PrepActions has exactly 4 members."""
        assert len(PrepActions) == 4

    def test_add_column_value(self):
        """Verify add_column has the expected string value."""
        assert PrepActions.add_column.value == "add new column"

    def test_transform_column_value(self):
        """Verify transform_column has the expected string value."""
        assert PrepActions.transform_column.value == "transform column(s)"

    def test_remove_column_value(self):
        """Verify remove_column has the expected string value."""
        assert PrepActions.remove_column.value == "remove column(s)"

    def test_remove_row_value(self):
        """Verify remove_row has the expected string value."""
        assert PrepActions.remove_row.value == "remove row(s)"

    def test_access_by_name(self):
        """Verify enum members can be accessed by name."""
        assert PrepActions["add_column"] is PrepActions.add_column

    def test_access_by_value(self):
        """Verify enum members can be accessed by value."""
        assert PrepActions("add new column") is PrepActions.add_column

    def test_invalid_value_raises(self):
        """Verify accessing a non-existent value raises ValueError."""
        with pytest.raises(ValueError, match="is not a valid"):
            PrepActions("nonexistent")


# ============================================
# PrepMethods Tests
# ============================================


class TestPrepMethods:
    """Tests for the PrepMethods enum."""

    def test_member_count(self):
        """Verify PrepMethods has exactly 2 members."""
        assert len(PrepMethods) == 2

    def test_row_index_value(self):
        """Verify row_index has the expected string value."""
        assert PrepMethods.row_index.value == "by row index"

    def test_condition_value(self):
        """Verify condition has the expected string value."""
        assert PrepMethods.condition.value == "by condition"


# ============================================
# PrepFunctions Tests
# ============================================


class TestPrepFunctions:
    """Tests for the PrepFunctions enum."""

    def test_member_count(self):
        """Verify PrepFunctions has exactly 19 members."""
        assert len(PrepFunctions) == 19

    @pytest.mark.parametrize(
        ("member_name", "expected_value"),
        [
            ("sum", "sum"),
            ("diff", "diff"),
            ("mean", "mean"),
            ("median", "median"),
            ("mode", "mode"),
            ("min", "min"),
            ("max", "max"),
            ("std", "std"),
            ("var", "var"),
            ("first", "first"),
            ("last", "last"),
            ("count", "count"),
            ("nunique", "nunique"),
            ("product", "product"),
            ("quotient", "quotient"),
            ("index", "index"),
            ("uuid", "uuid"),
            ("random", "random"),
            ("constant", "constant"),
        ],
    )
    def test_member_values(self, member_name, expected_value):
        """Verify each PrepFunctions member has its expected value."""
        assert PrepFunctions[member_name].value == expected_value

    def test_access_by_value(self):
        """Verify enum members can be looked up by value."""
        assert PrepFunctions("sum") is PrepFunctions.sum


# ============================================
# PrepOperations Tests
# ============================================


class TestPrepOperations:
    """Tests for the PrepOperations enum."""

    def test_member_count(self):
        """Verify PrepOperations has exactly 30 members."""
        assert len(PrepOperations) == 30

    @pytest.mark.parametrize(
        ("member_name", "expected_value"),
        [
            ("day_of_month", "day of month"),
            ("day_of_week", "day of week"),
            ("day_of_year", "day of year"),
            ("date", "date"),
            ("week_of_year", "week of year"),
            ("month_of_year", "month of year"),
            ("year", "year"),
            ("quarter_of_year", "quarter of year"),
            ("hour", "hour"),
            ("minute", "minute"),
            ("second", "second"),
            ("floor", "floor"),
            ("ceil", "ceil"),
            ("round", "round"),
            ("abs", "absolute value"),
            ("trim", "trim"),
            ("substring", "substring"),
            ("replace", "replace"),
            ("strip", "strip"),
            ("lower", "lowercase"),
            ("upper", "uppercase"),
            ("string_to_number", "string to number"),
            ("string_to_date", "string to date"),
            ("string_to_datetime", "string to datetime"),
            ("extract_pattern", "extract pattern"),
            ("get_dummies", "get dummies"),
            ("add", "add"),
            ("subtract", "subtract"),
            ("multiply", "multiply"),
            ("divide", "divide"),
        ],
    )
    def test_member_values(self, member_name, expected_value):
        """Verify each PrepOperations member has its expected value."""
        assert PrepOperations[member_name].value == expected_value


# ============================================
# PrepRowConditions Tests
# ============================================


class TestPrepRowConditions:
    """Tests for the PrepRowConditions enum."""

    def test_member_count(self):
        """Verify PrepRowConditions has exactly 12 members."""
        assert len(PrepRowConditions) == 12

    @pytest.mark.parametrize(
        ("member_name", "expected_value"),
        [
            ("missing", "value is missing"),
            ("not_missing", "value is not missing"),
            ("equal_to", "value is equal to"),
            ("not_equal_to", "value is not equal to"),
            ("greater_than", "value is greater than"),
            ("less_than", "value is less than"),
            ("greater_than_or_equal_to", "value is greater than or equal to"),
            ("less_than_or_equal_to", "value is less than or equal to"),
            ("between", "value is between"),
            ("not_between", "value is not between"),
            ("like", "value is like"),
            ("not_like", "value is not like"),
        ],
    )
    def test_member_values(self, member_name, expected_value):
        """Verify each PrepRowConditions member has its expected value."""
        assert PrepRowConditions[member_name].value == expected_value


# ============================================
# SearchType Tests
# ============================================


class TestSearchType:
    """Tests for the SearchType enum."""

    def test_member_count(self):
        """Verify SearchType has exactly 5 members."""
        assert len(SearchType) == 5

    @pytest.mark.parametrize(
        ("member", "expected_value"),
        [
            (SearchType.EXACT, "exact"),
            (SearchType.STARTSWITH, "startswith"),
            (SearchType.ENDSWITH, "endswith"),
            (SearchType.CONTAINS, "contains"),
            (SearchType.REGEX, "regex"),
        ],
    )
    def test_member_values(self, member, expected_value):
        """Verify each SearchType member has its expected value."""
        assert member.value == expected_value

    def test_access_by_value(self):
        """Verify SearchType members can be looked up by value."""
        assert SearchType("exact") is SearchType.EXACT


# ============================================
# NumCondition Tests
# ============================================


class TestNumCondition:
    """Tests for the NumCondition enum."""

    def test_member_count(self):
        """Verify NumCondition has exactly 9 members."""
        assert len(NumCondition) == 9

    @pytest.mark.parametrize(
        ("member", "expected_value"),
        [
            (NumCondition.EQUALS, "Value is equal"),
            (NumCondition.NOT_EQUALS, "Value is not equal"),
            (NumCondition.GREATER_THAN, "Value is greater than"),
            (NumCondition.GREATER_THAN_OR_EQUAL, "Value is greater than or equal to"),
            (NumCondition.LESS_THAN, "Value is less than"),
            (NumCondition.LESS_THAN_OR_EQUAL, "Value is less than or equal to"),
            (NumCondition.INCLUDES, "Values includes"),
            (NumCondition.EXCLUDES, "Value does not include"),
            (NumCondition.IN_RANGE, "Value is in range"),
        ],
    )
    def test_member_values(self, member, expected_value):
        """Verify each NumCondition member has its expected value."""
        assert member.value == expected_value


# ============================================
# StrCondition Tests
# ============================================


class TestStrCondition:
    """Tests for the StrCondition enum."""

    def test_member_count(self):
        """Verify StrCondition has exactly 7 members."""
        assert len(StrCondition) == 7

    @pytest.mark.parametrize(
        ("member", "expected_value"),
        [
            (StrCondition.EQUALS, "Value is equal"),
            (StrCondition.NOT_EQUALS, "Value is not equal"),
            (StrCondition.STARTWITH, "Value starts with"),
            (StrCondition.ENDWITH, "Value ends with"),
            (StrCondition.CONTAINS, "Value contains"),
            (StrCondition.INCLUDES, "Values includes"),
            (StrCondition.EXCLUDES, "Value does not include"),
        ],
    )
    def test_member_values(self, member, expected_value):
        """Verify each StrCondition member has its expected value."""
        assert member.value == expected_value


# ============================================
# Module-level Constant Tuple Tests
# ============================================


class TestColFuncWithValues:
    """Tests for the COL_FUNC_WITH_VALUES constant tuple."""

    def test_is_tuple(self):
        """Verify COL_FUNC_WITH_VALUES is a tuple."""
        assert isinstance(COL_FUNC_WITH_VALUES, tuple)

    def test_length(self):
        """Verify COL_FUNC_WITH_VALUES contains 15 items."""
        assert len(COL_FUNC_WITH_VALUES) == 15

    def test_contains_expected_values(self):
        """Verify COL_FUNC_WITH_VALUES includes all aggregate function values."""
        expected = {
            "sum",
            "diff",
            "mean",
            "median",
            "mode",
            "min",
            "max",
            "std",
            "var",
            "first",
            "last",
            "count",
            "nunique",
            "product",
            "quotient",
        }
        assert set(COL_FUNC_WITH_VALUES) == expected

    def test_excludes_special_methods(self):
        """Verify COL_FUNC_WITH_VALUES excludes index, uuid, random, constant."""
        for val in ("index", "uuid", "random", "constant"):
            assert val not in COL_FUNC_WITH_VALUES


class TestColMethodsWithoutValues:
    """Tests for the COL_METHODS_WITHOUT_VALUES constant tuple."""

    def test_is_tuple(self):
        """Verify COL_METHODS_WITHOUT_VALUES is a tuple."""
        assert isinstance(COL_METHODS_WITHOUT_VALUES, tuple)

    def test_length(self):
        """Verify COL_METHODS_WITHOUT_VALUES contains 3 items."""
        assert len(COL_METHODS_WITHOUT_VALUES) == 3

    def test_contents(self):
        """Verify COL_METHODS_WITHOUT_VALUES contains index, uuid, random."""
        assert set(COL_METHODS_WITHOUT_VALUES) == {"index", "uuid", "random"}


class TestDelRowCondMax1:
    """Tests for the DEL_ROW_COND_MAX_1 constant tuple."""

    def test_is_tuple(self):
        """Verify DEL_ROW_COND_MAX_1 is a tuple."""
        assert isinstance(DEL_ROW_COND_MAX_1, tuple)

    def test_length(self):
        """Verify DEL_ROW_COND_MAX_1 contains 6 items."""
        assert len(DEL_ROW_COND_MAX_1) == 6

    def test_contents(self):
        """Verify DEL_ROW_COND_MAX_1 contains the expected condition values."""
        expected = {
            "value is equal to",
            "value is not equal to",
            "value is greater than",
            "value is less than",
            "value is greater than or equal to",
            "value is less than or equal to",
        }
        assert set(DEL_ROW_COND_MAX_1) == expected


class TestDelRowCondNumOnly:
    """Tests for the DEL_ROW_COND_NUM_ONLY constant tuple."""

    def test_is_tuple(self):
        """Verify DEL_ROW_COND_NUM_ONLY is a tuple."""
        assert isinstance(DEL_ROW_COND_NUM_ONLY, tuple)

    def test_length(self):
        """Verify DEL_ROW_COND_NUM_ONLY contains 6 items."""
        assert len(DEL_ROW_COND_NUM_ONLY) == 6

    def test_contains_numeric_conditions(self):
        """Verify DEL_ROW_COND_NUM_ONLY includes between and not_between."""
        assert PrepRowConditions.between.value in DEL_ROW_COND_NUM_ONLY
        assert PrepRowConditions.not_between.value in DEL_ROW_COND_NUM_ONLY

    def test_excludes_string_conditions(self):
        """Verify DEL_ROW_COND_NUM_ONLY excludes like and not_like."""
        assert PrepRowConditions.like.value not in DEL_ROW_COND_NUM_ONLY
        assert PrepRowConditions.not_like.value not in DEL_ROW_COND_NUM_ONLY


class TestDelRowCondStrOnly:
    """Tests for the DEL_ROW_COND_STR_ONLY constant tuple."""

    def test_is_tuple(self):
        """Verify DEL_ROW_COND_STR_ONLY is a tuple."""
        assert isinstance(DEL_ROW_COND_STR_ONLY, tuple)

    def test_length(self):
        """Verify DEL_ROW_COND_STR_ONLY contains 2 items."""
        assert len(DEL_ROW_COND_STR_ONLY) == 2

    def test_contents(self):
        """Verify DEL_ROW_COND_STR_ONLY contains like and not_like values."""
        assert set(DEL_ROW_COND_STR_ONLY) == {
            "value is like",
            "value is not like",
        }


class TestDelCondUseVals:
    """Tests for the DEL_COND_USE_VALS constant tuple."""

    def test_is_tuple(self):
        """Verify DEL_COND_USE_VALS is a tuple."""
        assert isinstance(DEL_COND_USE_VALS, tuple)

    def test_length(self):
        """Verify DEL_COND_USE_VALS contains 6 items."""
        assert len(DEL_COND_USE_VALS) == 6

    def test_subset_of_max_1(self):
        """Verify DEL_COND_USE_VALS matches DEL_ROW_COND_MAX_1."""
        assert set(DEL_COND_USE_VALS) == set(DEL_ROW_COND_MAX_1)


class TestDelRowCondSameType:
    """Tests for the DEL_ROW_COND_SAME_TYPE constant tuple."""

    def test_is_tuple(self):
        """Verify DEL_ROW_COND_SAME_TYPE is a tuple."""
        assert isinstance(DEL_ROW_COND_SAME_TYPE, tuple)

    def test_length(self):
        """Verify DEL_ROW_COND_SAME_TYPE contains 2 items."""
        assert len(DEL_ROW_COND_SAME_TYPE) == 2

    def test_contents(self):
        """Verify DEL_ROW_COND_SAME_TYPE contains between and not_between."""
        assert set(DEL_ROW_COND_SAME_TYPE) == {
            "value is between",
            "value is not between",
        }


# ============================================
# Cross-constant Consistency Tests
# ============================================


class TestConstantConsistency:
    """Tests for consistency between constant tuples."""

    def test_no_overlap_num_only_and_str_only(self):
        """Verify numeric-only and string-only conditions do not overlap."""
        assert not set(DEL_ROW_COND_NUM_ONLY) & set(DEL_ROW_COND_STR_ONLY)

    def test_same_type_is_subset_of_num_only(self):
        """Verify same-type conditions are a subset of numeric-only conditions."""
        assert set(DEL_ROW_COND_SAME_TYPE).issubset(set(DEL_ROW_COND_NUM_ONLY))

    def test_all_constant_values_come_from_enums(self):
        """Verify all constant tuple values originate from their respective enums."""
        all_prep_func_values = {m.value for m in PrepFunctions}
        for val in COL_FUNC_WITH_VALUES:
            assert val in all_prep_func_values
        for val in COL_METHODS_WITHOUT_VALUES:
            assert val in all_prep_func_values

        all_row_cond_values = {m.value for m in PrepRowConditions}
        for val in DEL_ROW_COND_MAX_1:
            assert val in all_row_cond_values
        for val in DEL_ROW_COND_NUM_ONLY:
            assert val in all_row_cond_values
        for val in DEL_ROW_COND_STR_ONLY:
            assert val in all_row_cond_values
        for val in DEL_COND_USE_VALS:
            assert val in all_row_cond_values
        for val in DEL_ROW_COND_SAME_TYPE:
            assert val in all_row_cond_values

    def test_col_func_and_methods_are_disjoint(self):
        """Verify COL_FUNC_WITH_VALUES and COL_METHODS_WITHOUT_VALUES are disjoint."""
        assert not set(COL_FUNC_WITH_VALUES) & set(COL_METHODS_WITHOUT_VALUES)

    def test_col_func_and_methods_cover_all_except_constant(self):
        """Verify COL_FUNC_WITH_VALUES + COL_METHODS_WITHOUT_VALUES cover all
        PrepFunctions except 'constant'.
        """
        combined = set(COL_FUNC_WITH_VALUES) | set(COL_METHODS_WITHOUT_VALUES)
        all_values = {m.value for m in PrepFunctions}
        assert all_values - combined == {"constant"}
