"""Tests for prep_view.py - actual imports with proper mocking."""

import sys
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.models.enums import (
    DEL_ROW_COND_MAX_1,
    DEL_ROW_COND_NUM_ONLY,
    DEL_ROW_COND_STR_ONLY,
    PrepActions,
    PrepFunctions,
    PrepMethods,
    PrepRowConditions,
)

# --- Module import setup ---
# prep_view.py has module-level Streamlit guards and UI code.
# We need to set up mocks so the module can import without real DB or UI.
_st = sys.modules["streamlit"]
_orig_stop = _st.stop

# Let module load past the guards
_st.session_state["st_project_id"] = "test_project"
_st.stop = MagicMock()

# Make st.columns return context-manager-compatible mocks
_mock_col = MagicMock()
_mock_col.__enter__ = MagicMock(return_value=_mock_col)
_mock_col.__exit__ = MagicMock(return_value=False)
_st.columns = MagicMock(return_value=[_mock_col, _mock_col, _mock_col])

# Patch duckdb and navigation utilities so module-level UI code doesn't fail
with (
    patch("datasure.utils.duckdb_utils.duckdb_get_aliases", return_value=[]),
    patch("datasure.utils.navigations_utils.page_navigation"),
    patch("datasure.utils.navigations_utils.add_demo_navigation"),
    patch("datasure.utils.navigations_utils.demo_sidebar_help"),
    patch("datasure.utils.navigations_utils.demo_callout"),
    patch("datasure.utils.navigations_utils.show_demo_next_action"),
    patch("datasure.utils.onboarding_utils.is_demo_project", return_value=False),
    patch("datasure.utils.onboarding_utils.demo_expander"),
):
    from datasure.views.prep_view import (
        PrepStepHandler,
        PrepViewConfig,
        RemoveRowsInputs,
        TransformInputs,
        _build_remove_rows_result,
        _build_remove_rows_value,
        _build_transform_result,
        _build_transform_value,
        _get_column_options_for_condition,
        _get_unique_values_from_columns,
        _has_none_values,
        _is_add_column_incomplete,
        _is_prep_form_incomplete,
        _is_remove_row_incomplete,
        _is_transform_column_incomplete,
        _render_datetime_function_inputs,
        _render_equality_value_inputs,
        _render_numeric_function_inputs,
        _render_pattern_value_inputs,
        _render_range_value_inputs,
        _render_string_function_inputs,
        _render_substring_inputs,
        _validate_column_types_for_range,
        prep_add_step,
        prep_remove_step,
    )

# Restore original stop behavior
_st.session_state["st_project_id"] = None
_st.stop = _orig_stop


# === DATA CLASS TESTS === #


class TestTransformInputs:
    """Test TransformInputs initialization."""

    def test_default_init(self):
        inputs = TransformInputs()
        assert inputs.func is None
        assert inputs.old_val is None
        assert inputs.new_val is None
        assert inputs.pattern is None
        assert inputs.start is None
        assert inputs.end is None
        assert inputs.numeric_val is None

    def test_set_values(self):
        inputs = TransformInputs()
        inputs.func = "replace"
        inputs.old_val = "old"
        inputs.new_val = "new"
        assert inputs.func == "replace"
        assert inputs.old_val == "old"
        assert inputs.new_val == "new"


class TestRemoveRowsInputs:
    """Test RemoveRowsInputs initialization."""

    def test_default_init(self):
        inputs = RemoveRowsInputs()
        assert inputs.method is None
        assert inputs.condition is None
        assert inputs.selected_columns == []
        assert inputs.indexes_to_remove == []
        assert inputs.equality_values == []
        assert inputs.min_value is None
        assert inputs.max_value is None
        assert inputs.pattern_value is None


class TestPrepViewConfig:
    """Test PrepViewConfig class."""

    def test_init_creates_tuples(self):
        cfg = PrepViewConfig()
        assert isinstance(cfg.DP_ACTIONS, tuple)
        assert isinstance(cfg.DP_ADD_METHODS, tuple)
        assert isinstance(cfg.DP_DEL_METHODS, tuple)
        assert isinstance(cfg.DP_FUNCS, tuple)
        assert isinstance(cfg.DP_STR_FUNCS, tuple)
        assert isinstance(cfg.DP_NUM_FUNCS, tuple)
        assert isinstance(cfg.DP_DATETIME_FUNCS, tuple)
        assert isinstance(cfg.DP_ROW_CONDITIONS, tuple)

    def test_actions_content(self):
        cfg = PrepViewConfig()
        assert PrepActions.add_column.value in cfg.DP_ACTIONS
        assert PrepActions.transform_column.value in cfg.DP_ACTIONS
        assert PrepActions.remove_column.value in cfg.DP_ACTIONS
        assert PrepActions.remove_row.value in cfg.DP_ACTIONS

    def test_add_methods_content(self):
        cfg = PrepViewConfig()
        assert PrepFunctions.constant.value in cfg.DP_ADD_METHODS
        assert PrepFunctions.sum.value in cfg.DP_ADD_METHODS
        assert PrepFunctions.index.value in cfg.DP_ADD_METHODS

    def test_del_methods_content(self):
        cfg = PrepViewConfig()
        assert PrepMethods.row_index.value in cfg.DP_DEL_METHODS
        assert PrepMethods.condition.value in cfg.DP_DEL_METHODS

    def test_descriptions_attribute(self):
        cfg = PrepViewConfig()
        assert cfg.descriptions is not None
        assert len(cfg.DP_STR_FUNCS) > 0
        assert len(cfg.DP_NUM_FUNCS) > 0
        assert len(cfg.DP_DATETIME_FUNCS) > 0
        assert len(cfg.DP_ROW_CONDITIONS) > 0


# === VALIDATION FUNCTION TESTS === #


class TestHasNoneValues:
    """Test _has_none_values helper."""

    def test_none_input(self):
        assert _has_none_values(None) is True

    def test_empty_list(self):
        assert _has_none_values([]) is True

    def test_list_with_none(self):
        assert _has_none_values([1, None, 3]) is True

    def test_list_without_none(self):
        assert _has_none_values([1, 2, 3]) is False

    def test_single_none(self):
        assert _has_none_values([None]) is True

    def test_single_value(self):
        assert _has_none_values(["a"]) is False


class TestIsAddColumnIncomplete:
    """Test _is_add_column_incomplete."""

    def test_no_column_name(self):
        assert _is_add_column_incomplete({"column_names": None}) is True
        assert _is_add_column_incomplete({"column_names": ""}) is True

    def test_constant_method_complete(self):
        args = {
            "column_names": "new_col",
            "method": PrepFunctions.constant.value,
        }
        assert _is_add_column_incomplete(args) is False

    def test_col_func_with_values_no_source(self):
        args = {
            "column_names": "new_col",
            "method": PrepFunctions.sum.value,
            "source_columns": [],
        }
        assert _is_add_column_incomplete(args) is True

    def test_col_func_with_values_has_source(self):
        args = {
            "column_names": "new_col",
            "method": PrepFunctions.sum.value,
            "source_columns": ["col1", "col2"],
        }
        assert _is_add_column_incomplete(args) is False

    def test_quotient_needs_exactly_2_columns(self):
        args = {
            "column_names": "new_col",
            "method": PrepFunctions.quotient.value,
            "source_columns": ["col1"],
        }
        assert _is_add_column_incomplete(args) is True

    def test_quotient_with_2_columns_complete(self):
        args = {
            "column_names": "new_col",
            "method": PrepFunctions.quotient.value,
            "source_columns": ["col1", "col2"],
        }
        assert _is_add_column_incomplete(args) is False

    def test_quotient_with_3_columns_incomplete(self):
        args = {
            "column_names": "new_col",
            "method": PrepFunctions.quotient.value,
            "source_columns": ["c1", "c2", "c3"],
        }
        assert _is_add_column_incomplete(args) is True

    def test_no_values_method_complete(self):
        args = {
            "column_names": "new_col",
            "method": PrepFunctions.index.value,
        }
        assert _is_add_column_incomplete(args) is False

    def test_missing_column_names_key(self):
        assert _is_add_column_incomplete({}) is True


class TestIsTransformColumnIncomplete:
    """Test _is_transform_column_incomplete."""

    def test_no_source_columns(self):
        assert _is_transform_column_incomplete({"source_columns": []}) is True

    def test_no_method(self):
        args = {"source_columns": ["col1"], "method": None}
        assert _is_transform_column_incomplete(args) is True

    def test_no_value_required_complete(self):
        args = {"source_columns": ["col1"], "method": "trim", "value": []}
        assert _is_transform_column_incomplete(args) is False

    def test_value_required_all_present(self):
        args = {
            "source_columns": ["col1"],
            "method": "replace",
            "value": ["old", "new"],
        }
        assert _is_transform_column_incomplete(args) is False

    def test_value_required_has_none(self):
        args = {
            "source_columns": ["col1"],
            "method": "replace",
            "value": ["old", None],
        }
        assert _is_transform_column_incomplete(args) is True

    def test_value_required_has_empty_string(self):
        args = {
            "source_columns": ["col1"],
            "method": "replace",
            "value": ["old", ""],
        }
        assert _is_transform_column_incomplete(args) is True

    def test_none_value_means_complete(self):
        """When value is None (not required), form is complete."""
        args = {"source_columns": ["col1"], "method": "trim", "value": None}
        assert _is_transform_column_incomplete(args) is False

    def test_missing_source_columns_key(self):
        assert _is_transform_column_incomplete({"method": "trim"}) is True


class TestIsRemoveRowIncomplete:
    """Test _is_remove_row_incomplete."""

    def test_row_index_no_value(self):
        args = {"method": PrepMethods.row_index.value, "value": None}
        assert _is_remove_row_incomplete(args) is True

    def test_row_index_with_value(self):
        args = {"method": PrepMethods.row_index.value, "value": ["1", "2"]}
        assert _is_remove_row_incomplete(args) is False

    def test_unknown_method(self):
        args = {"method": "unknown"}
        assert _is_remove_row_incomplete(args) is True

    def test_condition_equal_to_with_value(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.equal_to.value,
            "value": "some_val",
        }
        assert _is_remove_row_incomplete(args) is False

    def test_condition_equal_to_no_value(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.equal_to.value,
            "value": None,
        }
        assert _is_remove_row_incomplete(args) is True

    def test_condition_not_equal_to_with_value(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.not_equal_to.value,
            "value": "some_val",
        }
        assert _is_remove_row_incomplete(args) is False

    def test_condition_not_equal_to_no_value(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.not_equal_to.value,
            "value": None,
        }
        assert _is_remove_row_incomplete(args) is True

    def test_condition_greater_than_with_value(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.greater_than.value,
            "value": 10,
        }
        assert _is_remove_row_incomplete(args) is False

    def test_condition_less_than_no_value(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.less_than.value,
            "value": None,
        }
        assert _is_remove_row_incomplete(args) is True

    def test_condition_between_with_values(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.between.value,
            "value": [1, 10],
        }
        assert _is_remove_row_incomplete(args) is False

    def test_condition_between_with_none_values(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.between.value,
            "value": [None, 10],
        }
        assert _is_remove_row_incomplete(args) is True

    def test_condition_not_between_with_values(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.not_between.value,
            "value": [5, 20],
        }
        assert _is_remove_row_incomplete(args) is False

    def test_condition_like_with_value(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.like.value,
            "value": "pattern",
        }
        assert _is_remove_row_incomplete(args) is False

    def test_condition_like_no_value(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.like.value,
            "value": None,
        }
        assert _is_remove_row_incomplete(args) is True

    def test_condition_not_like_with_value(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.not_like.value,
            "value": "pat",
        }
        assert _is_remove_row_incomplete(args) is False

    def test_condition_not_like_no_value(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.not_like.value,
            "value": None,
        }
        assert _is_remove_row_incomplete(args) is True

    def test_condition_missing_no_value_needed(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.missing.value,
            "value": None,
        }
        assert _is_remove_row_incomplete(args) is False

    def test_condition_not_missing_no_value_needed(self):
        args = {
            "method": PrepMethods.condition.value,
            "condition": PrepRowConditions.not_missing.value,
            "value": None,
        }
        assert _is_remove_row_incomplete(args) is False

    def test_row_index_with_empty_value(self):
        args = {"method": PrepMethods.row_index.value, "value": []}
        assert _is_remove_row_incomplete(args) is True


class TestIsPrepFormIncomplete:
    """Test _is_prep_form_incomplete dispatcher."""

    def test_add_column_dispatch(self):
        args = {"column_names": "col", "method": PrepFunctions.constant.value}
        result = _is_prep_form_incomplete(PrepActions.add_column.value, args)
        assert result is False

    def test_transform_column_dispatch(self):
        args = {"source_columns": ["col1"], "method": "trim", "value": []}
        result = _is_prep_form_incomplete(PrepActions.transform_column.value, args)
        assert result is False

    def test_remove_column_dispatch_with_columns(self):
        args = {"source_columns": ["col1"]}
        result = _is_prep_form_incomplete(PrepActions.remove_column.value, args)
        assert result is False

    def test_remove_column_dispatch_no_columns(self):
        args = {"source_columns": []}
        result = _is_prep_form_incomplete(PrepActions.remove_column.value, args)
        assert result is True

    def test_remove_row_dispatch(self):
        args = {"method": PrepMethods.row_index.value, "value": ["1"]}
        result = _is_prep_form_incomplete(PrepActions.remove_row.value, args)
        assert result is False

    def test_unknown_action(self):
        result = _is_prep_form_incomplete("unknown_action", {})
        assert result is False

    def test_add_column_incomplete(self):
        args = {"column_names": None}
        result = _is_prep_form_incomplete(PrepActions.add_column.value, args)
        assert result is True

    def test_transform_column_incomplete(self):
        args = {"source_columns": [], "method": None}
        result = _is_prep_form_incomplete(PrepActions.transform_column.value, args)
        assert result is True


# === BUILDER FUNCTION TESTS === #


class TestBuildTransformValue:
    """Test _build_transform_value."""

    def test_no_func(self):
        inputs = TransformInputs()
        assert _build_transform_value(inputs) == []

    def test_replace(self):
        inputs = TransformInputs()
        inputs.func = "replace"
        inputs.old_val = "old"
        inputs.new_val = "new"
        assert _build_transform_value(inputs) == ["old", "new"]

    def test_extract_pattern(self):
        inputs = TransformInputs()
        inputs.func = "extract pattern"
        inputs.pattern = r"\d+"
        assert _build_transform_value(inputs) == [r"\d+"]

    def test_substring(self):
        inputs = TransformInputs()
        inputs.func = "substring"
        inputs.start = 0
        inputs.end = 5
        assert _build_transform_value(inputs) == [0, 5]

    def test_add(self):
        inputs = TransformInputs()
        inputs.func = "add"
        inputs.numeric_val = 10.0
        assert _build_transform_value(inputs) == [10.0]

    def test_multiply(self):
        inputs = TransformInputs()
        inputs.func = "multiply"
        inputs.numeric_val = 2.5
        assert _build_transform_value(inputs) == [2.5]

    def test_subtract(self):
        inputs = TransformInputs()
        inputs.func = "subtract"
        inputs.numeric_val = 3
        assert _build_transform_value(inputs) == [3]

    def test_divide(self):
        inputs = TransformInputs()
        inputs.func = "divide"
        inputs.numeric_val = 4
        assert _build_transform_value(inputs) == [4]

    def test_func_without_values(self):
        inputs = TransformInputs()
        inputs.func = "trim"
        assert _build_transform_value(inputs) == []

    def test_lower(self):
        inputs = TransformInputs()
        inputs.func = "lowercase"
        assert _build_transform_value(inputs) == []


class TestBuildTransformResult:
    """Test _build_transform_result."""

    def test_with_column_and_func(self):
        inputs = TransformInputs()
        inputs.func = "trim"
        result = _build_transform_result("col1", inputs)
        assert result["action"] == PrepActions.transform_column.value
        assert result["source_columns"] == ["col1"]
        assert result["method"] == "trim"
        assert result["value"] == []
        assert result["column_names"] is None
        assert result["affected_count"] == 0
        assert result["condition"] is None
        assert result["failed_count"] == 0
        assert result["additional_info"] is None
        assert result["remaining_count"] is None

    def test_with_no_column(self):
        inputs = TransformInputs()
        inputs.func = "trim"
        result = _build_transform_result(None, inputs)
        assert result["source_columns"] == []

    def test_with_replace_values(self):
        inputs = TransformInputs()
        inputs.func = "replace"
        inputs.old_val = "a"
        inputs.new_val = "b"
        result = _build_transform_result("col1", inputs)
        assert result["value"] == ["a", "b"]
        assert result["method"] == "replace"

    def test_with_numeric_func(self):
        inputs = TransformInputs()
        inputs.func = "add"
        inputs.numeric_val = 5.0
        result = _build_transform_result("score", inputs)
        assert result["value"] == [5.0]
        assert result["source_columns"] == ["score"]


# === COLUMN OPTION TESTS === #


class TestGetColumnOptionsForCondition:
    """Test _get_column_options_for_condition."""

    def setup_method(self):
        self.all_cols = ["a", "b", "c", "d"]
        self.num_cols = ["a", "b"]
        self.date_cols = ["c"]
        self.str_cols = ["d"]

    def test_numeric_condition_returns_num_and_date(self):
        for cond in DEL_ROW_COND_NUM_ONLY:
            cols, _ = _get_column_options_for_condition(
                cond, self.all_cols, self.num_cols, self.date_cols, self.str_cols
            )
            assert cols == ["a", "b", "c"]

    def test_string_condition_returns_string_cols(self):
        for cond in DEL_ROW_COND_STR_ONLY:
            cols, _ = _get_column_options_for_condition(
                cond,
                self.all_cols,
                self.num_cols,
                self.date_cols,
                self.str_cols,
            )
            assert cols == ["d"]

    def test_other_condition_returns_all_cols(self):
        cols, _ = _get_column_options_for_condition(
            PrepRowConditions.missing.value,
            self.all_cols,
            self.num_cols,
            self.date_cols,
            self.str_cols,
        )
        assert cols == self.all_cols

    def test_max_1_condition(self):
        for cond in DEL_ROW_COND_MAX_1:
            _, max_sel = _get_column_options_for_condition(
                cond,
                self.all_cols,
                self.num_cols,
                self.date_cols,
                self.str_cols,
            )
            assert max_sel == 1

    def test_non_max1_condition_allows_all(self):
        _, max_sel = _get_column_options_for_condition(
            PrepRowConditions.missing.value,
            self.all_cols,
            self.num_cols,
            self.date_cols,
            self.str_cols,
        )
        assert max_sel == len(self.all_cols)

    def test_equal_to_returns_max_1(self):
        _, max_sel = _get_column_options_for_condition(
            PrepRowConditions.equal_to.value,
            self.all_cols,
            self.num_cols,
            self.date_cols,
            self.str_cols,
        )
        assert max_sel == 1

    def test_between_returns_num_and_date(self):
        cols, _ = _get_column_options_for_condition(
            PrepRowConditions.between.value,
            self.all_cols,
            self.num_cols,
            self.date_cols,
            self.str_cols,
        )
        assert cols == ["a", "b", "c"]


# === POLARS DATAFRAME FUNCTION TESTS === #


class TestValidateColumnTypesForRange:
    """Test _validate_column_types_for_range."""

    def test_empty_columns(self):
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        valid, types = _validate_column_types_for_range(df, [])
        assert valid is False
        assert types == set()

    def test_same_type_valid(self):
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        valid, types = _validate_column_types_for_range(df, ["a", "b"])
        assert valid is True
        assert len(types) == 1

    def test_different_types_invalid(self):
        df = pl.DataFrame({"a": [1, 2], "b": ["x", "y"]})
        valid, types = _validate_column_types_for_range(df, ["a", "b"])
        assert valid is False
        assert len(types) == 2

    def test_single_column_valid(self):
        df = pl.DataFrame({"a": [1, 2]})
        valid, types = _validate_column_types_for_range(df, ["a"])
        assert valid is True
        assert len(types) == 1


class TestGetUniqueValuesFromColumns:
    """Test _get_unique_values_from_columns."""

    def test_single_column(self):
        df = pl.DataFrame({"a": [3, 1, 2, 1]})
        result = _get_unique_values_from_columns(df, ["a"])
        assert result == [1, 2, 3]

    def test_multiple_columns(self):
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        result = _get_unique_values_from_columns(df, ["a", "b"])
        assert result == [1, 2, 3, 4]

    def test_empty_columns_list(self):
        df = pl.DataFrame({"a": [1, 2]})
        result = _get_unique_values_from_columns(df, [])
        assert result == []

    def test_duplicates_across_columns(self):
        df = pl.DataFrame({"a": [1, 2], "b": [2, 3]})
        result = _get_unique_values_from_columns(df, ["a", "b"])
        assert result == [1, 2, 2, 3]


# === REMOVE ROWS BUILDER TESTS === #


class TestBuildRemoveRowsValue:
    """Test _build_remove_rows_value."""

    def test_row_index_with_indexes(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.row_index.value
        inputs.indexes_to_remove = ["1", "3", "5"]
        assert _build_remove_rows_value(inputs) == ["1", "3", "5"]

    def test_row_index_no_indexes(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.row_index.value
        assert _build_remove_rows_value(inputs) is None

    def test_not_condition_method(self):
        inputs = RemoveRowsInputs()
        inputs.method = "unknown"
        assert _build_remove_rows_value(inputs) is None

    def test_condition_no_columns(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = PrepRowConditions.equal_to.value
        assert _build_remove_rows_value(inputs) is None

    def test_condition_equal_to(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = PrepRowConditions.equal_to.value
        inputs.selected_columns = ["col1"]
        inputs.equality_values = "test_val"
        assert _build_remove_rows_value(inputs) == "test_val"

    def test_condition_not_equal_to(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = PrepRowConditions.not_equal_to.value
        inputs.selected_columns = ["col1"]
        inputs.equality_values = "test_val"
        assert _build_remove_rows_value(inputs) == "test_val"

    def test_condition_between(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = PrepRowConditions.between.value
        inputs.selected_columns = ["col1"]
        inputs.min_value = 1
        inputs.max_value = 10
        assert _build_remove_rows_value(inputs) == [1, 10]

    def test_condition_not_between(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = PrepRowConditions.not_between.value
        inputs.selected_columns = ["col1"]
        inputs.min_value = 5
        inputs.max_value = 20
        assert _build_remove_rows_value(inputs) == [5, 20]

    def test_condition_like(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = PrepRowConditions.like.value
        inputs.selected_columns = ["col1"]
        inputs.pattern_value = "pattern.*"
        assert _build_remove_rows_value(inputs) == "pattern.*"

    def test_condition_not_like(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = PrepRowConditions.not_like.value
        inputs.selected_columns = ["col1"]
        inputs.pattern_value = "pat"
        assert _build_remove_rows_value(inputs) == "pat"

    def test_condition_missing_returns_none(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = PrepRowConditions.missing.value
        inputs.selected_columns = ["col1"]
        assert _build_remove_rows_value(inputs) is None

    def test_condition_not_missing_returns_none(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = PrepRowConditions.not_missing.value
        inputs.selected_columns = ["col1"]
        assert _build_remove_rows_value(inputs) is None

    def test_condition_no_condition_set(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = None
        assert _build_remove_rows_value(inputs) is None


class TestBuildRemoveRowsResult:
    """Test _build_remove_rows_result."""

    def test_row_index_result(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.row_index.value
        inputs.indexes_to_remove = ["1", "2"]
        result = _build_remove_rows_result(inputs)
        assert result["action"] == PrepActions.remove_row.value
        assert result["value"] == ["1", "2"]
        assert result["source_columns"] == []
        assert result["condition"] is None
        assert result["failed_count"] is None
        assert result["additional_info"] is None

    def test_condition_result(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = PrepRowConditions.equal_to.value
        inputs.selected_columns = ["col1"]
        inputs.equality_values = "val"
        result = _build_remove_rows_result(inputs)
        assert result["action"] == PrepActions.remove_row.value
        assert result["source_columns"] == ["col1"]
        assert result["condition"] == PrepRowConditions.equal_to.value
        assert result["value"] == "val"
        assert result["method"] == PrepMethods.condition.value

    def test_no_method(self):
        inputs = RemoveRowsInputs()
        result = _build_remove_rows_result(inputs)
        assert result["source_columns"] == []
        assert result["condition"] is None
        assert result["value"] is None

    def test_condition_no_selected_columns(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = PrepRowConditions.missing.value
        result = _build_remove_rows_result(inputs)
        assert result["source_columns"] == []

    def test_condition_with_no_condition_value(self):
        inputs = RemoveRowsInputs()
        inputs.method = PrepMethods.condition.value
        inputs.condition = None
        inputs.selected_columns = ["col1"]
        result = _build_remove_rows_result(inputs)
        assert result["condition"] is None


# === RENDER FUNCTION TESTS (with st mocking) === #


class TestRenderStringFunctionInputs:
    """Test _render_string_function_inputs with mocked streamlit."""

    def test_basic_function_no_extra_inputs(self):
        _st.selectbox = MagicMock(return_value="trim")
        inputs = TransformInputs()
        result = _render_string_function_inputs(0, inputs)
        assert result.func == "trim"

    def test_replace_function(self):
        _st.selectbox = MagicMock(return_value="replace")
        _st.text_input = MagicMock(side_effect=["old_val", "new_val"])
        inputs = TransformInputs()
        result = _render_string_function_inputs(0, inputs)
        assert result.func == "replace"
        assert result.old_val == "old_val"
        assert result.new_val == "new_val"

    def test_substring_function(self):
        _st.selectbox = MagicMock(return_value="substring")
        mock_col = MagicMock()
        _st.columns = MagicMock(return_value=[mock_col, mock_col])
        _st.number_input = MagicMock(side_effect=[0, 5])
        inputs = TransformInputs()
        result = _render_string_function_inputs(0, inputs)
        assert result.func == "substring"

    def test_extract_pattern_function(self):
        _st.selectbox = MagicMock(return_value="extract pattern")
        _st.text_input = MagicMock(return_value=r"\d+")
        inputs = TransformInputs()
        result = _render_string_function_inputs(0, inputs)
        assert result.func == "extract pattern"
        assert result.pattern == r"\d+"

    def test_uppercase_function(self):
        _st.selectbox = MagicMock(return_value="uppercase")
        inputs = TransformInputs()
        result = _render_string_function_inputs(0, inputs)
        assert result.func == "uppercase"

    def test_lowercase_function(self):
        _st.selectbox = MagicMock(return_value="lowercase")
        inputs = TransformInputs()
        result = _render_string_function_inputs(0, inputs)
        assert result.func == "lowercase"


class TestRenderSubstringInputs:
    """Test _render_substring_inputs."""

    def test_valid_range(self):
        mock_col = MagicMock()
        _st.columns = MagicMock(return_value=[mock_col, mock_col])
        _st.number_input = MagicMock(side_effect=[0, 5])
        inputs = TransformInputs()
        _render_substring_inputs(0, inputs)
        assert inputs.start == 0
        assert inputs.end == 5

    def test_start_greater_than_end_shows_error(self):
        mock_col = MagicMock()
        _st.columns = MagicMock(return_value=[mock_col, mock_col])
        _st.number_input = MagicMock(side_effect=[5, 2])
        _st.error = MagicMock()
        inputs = TransformInputs()
        _render_substring_inputs(0, inputs)
        _st.error.assert_called_once()

    def test_start_equals_end_shows_error(self):
        mock_col = MagicMock()
        _st.columns = MagicMock(return_value=[mock_col, mock_col])
        _st.number_input = MagicMock(side_effect=[3, 3])
        _st.error = MagicMock()
        inputs = TransformInputs()
        _render_substring_inputs(0, inputs)
        _st.error.assert_called_once()

    def test_none_values_no_error(self):
        mock_col = MagicMock()
        _st.columns = MagicMock(return_value=[mock_col, mock_col])
        _st.number_input = MagicMock(side_effect=[None, None])
        _st.error = MagicMock()
        inputs = TransformInputs()
        _render_substring_inputs(0, inputs)
        _st.error.assert_not_called()

    def test_start_none_end_has_value(self):
        mock_col = MagicMock()
        _st.columns = MagicMock(return_value=[mock_col, mock_col])
        _st.number_input = MagicMock(side_effect=[None, 5])
        _st.error = MagicMock()
        inputs = TransformInputs()
        _render_substring_inputs(0, inputs)
        _st.error.assert_not_called()


class TestRenderNumericFunctionInputs:
    """Test _render_numeric_function_inputs."""

    def test_add_op(self):
        _st.selectbox = MagicMock(return_value="add")
        _st.number_input = MagicMock(return_value=10.0)
        inputs = TransformInputs()
        result = _render_numeric_function_inputs(0, inputs)
        assert result.func == "add"
        assert result.numeric_val == 10.0

    def test_multiply_op(self):
        _st.selectbox = MagicMock(return_value="multiply")
        _st.number_input = MagicMock(return_value=2.0)
        inputs = TransformInputs()
        result = _render_numeric_function_inputs(0, inputs)
        assert result.func == "multiply"
        assert result.numeric_val == 2.0

    def test_subtract_op(self):
        _st.selectbox = MagicMock(return_value="subtract")
        _st.number_input = MagicMock(return_value=3.0)
        inputs = TransformInputs()
        result = _render_numeric_function_inputs(0, inputs)
        assert result.func == "subtract"
        assert result.numeric_val == 3.0

    def test_divide_op(self):
        _st.selectbox = MagicMock(return_value="divide")
        _st.number_input = MagicMock(return_value=4.0)
        inputs = TransformInputs()
        result = _render_numeric_function_inputs(0, inputs)
        assert result.func == "divide"
        assert result.numeric_val == 4.0

    def test_non_arithmetic_op(self):
        _st.selectbox = MagicMock(return_value="round")
        inputs = TransformInputs()
        result = _render_numeric_function_inputs(0, inputs)
        assert result.func == "round"
        assert result.numeric_val is None

    def test_floor_op(self):
        _st.selectbox = MagicMock(return_value="floor")
        inputs = TransformInputs()
        result = _render_numeric_function_inputs(0, inputs)
        assert result.func == "floor"
        assert result.numeric_val is None


class TestRenderDatetimeFunctionInputs:
    """Test _render_datetime_function_inputs."""

    def test_returns_inputs_with_func(self):
        _st.selectbox = MagicMock(return_value="hour")
        inputs = TransformInputs()
        result = _render_datetime_function_inputs(0, inputs)
        assert result.func == "hour"

    def test_minute_func(self):
        _st.selectbox = MagicMock(return_value="minute")
        inputs = TransformInputs()
        result = _render_datetime_function_inputs(0, inputs)
        assert result.func == "minute"


# === RENDER EQUALITY/RANGE/PATTERN VALUE INPUT TESTS === #


class TestRenderEqualityValueInputs:
    """Test _render_equality_value_inputs."""

    def test_renders_selectbox_with_unique_vals(self):
        df = pl.DataFrame({"name": ["Alice", "Bob", "Alice"]})
        inputs = RemoveRowsInputs()
        inputs.selected_columns = ["name"]
        _st.selectbox = MagicMock(return_value="Alice")
        _render_equality_value_inputs(df, inputs, 0)
        assert inputs.equality_values == "Alice"
        _st.selectbox.assert_called_once()

    def test_numeric_column(self):
        df = pl.DataFrame({"age": [25, 30, 35]})
        inputs = RemoveRowsInputs()
        inputs.selected_columns = ["age"]
        _st.selectbox = MagicMock(return_value=30)
        _render_equality_value_inputs(df, inputs, 0)
        assert inputs.equality_values == 30


class TestRenderRangeValueInputs:
    """Test _render_range_value_inputs."""

    def test_valid_same_type_columns(self):
        df = pl.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        inputs = RemoveRowsInputs()
        inputs.selected_columns = ["a", "b"]
        _st.selectbox = MagicMock(side_effect=[1, 6])
        _st.error = MagicMock()
        _render_range_value_inputs(df, inputs, 0)
        assert inputs.min_value == 1
        assert inputs.max_value == 6
        _st.error.assert_not_called()

    def test_invalid_mixed_types_shows_error(self):
        df = pl.DataFrame({"a": [1, 2], "b": [1.5, 2.5]})
        inputs = RemoveRowsInputs()
        inputs.selected_columns = ["a", "b"]
        _st.selectbox = MagicMock(side_effect=[1, 2.5])
        _st.error = MagicMock()
        _render_range_value_inputs(df, inputs, 0)
        _st.error.assert_called_once()

    def test_empty_columns(self):
        df = pl.DataFrame({"a": [1, 2]})
        inputs = RemoveRowsInputs()
        inputs.selected_columns = []
        _st.selectbox = MagicMock(side_effect=[None, None])
        _st.error = MagicMock()
        _render_range_value_inputs(df, inputs, 0)
        # empty columns => not valid, but no col_types => no error shown
        _st.error.assert_not_called()


class TestRenderPatternValueInputs:
    """Test _render_pattern_value_inputs."""

    def test_sets_pattern_value(self):
        inputs = RemoveRowsInputs()
        _st.text_input = MagicMock(return_value="Al.*")
        _render_pattern_value_inputs(inputs, 0)
        assert inputs.pattern_value == "Al.*"

    def test_empty_pattern(self):
        inputs = RemoveRowsInputs()
        _st.text_input = MagicMock(return_value="")
        _render_pattern_value_inputs(inputs, 0)
        assert inputs.pattern_value == ""


# === PREP STEP HANDLER TESTS === #


@pytest.fixture()
def sample_polars_df():
    """Create a sample polars DataFrame for testing."""
    return pl.DataFrame(
        {
            "name": ["Alice", "Bob", "Charlie"],
            "age": [25, 30, 35],
            "score": [90.5, 85.0, 92.3],
            "date": pl.Series(
                ["2024-01-01", "2024-02-01", "2024-03-01"]
            ).str.to_datetime(),
        }
    )


class TestPrepStepHandler:
    """Test PrepStepHandler methods."""

    def test_init(self, sample_polars_df):
        handler = PrepStepHandler(sample_polars_df, step_index=0)
        assert handler.prep_data is sample_polars_df
        assert handler.step_index == 0
        assert "name" in handler.all_cols
        assert "age" in handler.num_cols
        assert "name" in handler.string_cols

    def test_init_column_categories(self, sample_polars_df):
        handler = PrepStepHandler(sample_polars_df, step_index=0)
        assert "score" in handler.num_cols
        assert "date" in handler.date_cols

    def test_add_column_handler_no_input(self, sample_polars_df):
        _st.text_input = MagicMock(return_value="")
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.add_column_handler()
        assert result is None

    def test_add_column_handler_constant(self, sample_polars_df):
        _st.text_input = MagicMock(side_effect=["new_col", "constant_val"])
        _st.selectbox = MagicMock(return_value=PrepFunctions.constant.value)
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.add_column_handler()
        assert result is not None
        assert result["action"] == PrepActions.add_column.value
        assert result["column_names"] == "new_col"
        assert result["value"] == "constant_val"
        assert result["method"] == PrepFunctions.constant.value
        assert result["remaining_count"] == sample_polars_df.shape[1] + 1
        assert result["condition"] is None
        assert result["failed_count"] is None
        assert result["additional_info"] is None

    def test_add_column_handler_sum(self, sample_polars_df):
        _st.text_input = MagicMock(return_value="sum_col")
        _st.selectbox = MagicMock(return_value=PrepFunctions.sum.value)
        _st.multiselect = MagicMock(return_value=["age", "score"])
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.add_column_handler()
        assert result is not None
        assert result["method"] == PrepFunctions.sum.value
        assert result["source_columns"] == ["age", "score"]
        assert result["value"] is None

    def test_add_column_handler_quotient_max_2(self, sample_polars_df):
        _st.text_input = MagicMock(return_value="q_col")
        _st.selectbox = MagicMock(return_value=PrepFunctions.quotient.value)
        _st.multiselect = MagicMock(return_value=["age", "score"])
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.add_column_handler()
        assert result is not None
        call_kwargs = _st.multiselect.call_args[1]
        assert call_kwargs["max_selections"] == 2

    def test_add_column_handler_diff_max_2(self, sample_polars_df):
        _st.text_input = MagicMock(return_value="diff_col")
        _st.selectbox = MagicMock(return_value=PrepFunctions.diff.value)
        _st.multiselect = MagicMock(return_value=["age", "score"])
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.add_column_handler()
        assert result is not None
        call_kwargs = _st.multiselect.call_args[1]
        assert call_kwargs["max_selections"] == 2

    def test_add_column_handler_no_values_method(self, sample_polars_df):
        _st.text_input = MagicMock(return_value="idx_col")
        _st.selectbox = MagicMock(return_value=PrepFunctions.index.value)
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.add_column_handler()
        assert result is not None
        assert result["method"] == PrepFunctions.index.value
        assert result["value"] is None
        assert result["source_columns"] == []

    def test_add_column_handler_mean(self, sample_polars_df):
        _st.text_input = MagicMock(return_value="mean_col")
        _st.selectbox = MagicMock(return_value=PrepFunctions.mean.value)
        _st.multiselect = MagicMock(return_value=["age", "score"])
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.add_column_handler()
        assert result is not None
        assert result["method"] == PrepFunctions.mean.value
        call_kwargs = _st.multiselect.call_args[1]
        assert call_kwargs["max_selections"] == len(handler.num_cols)

    def test_transform_column_handler_no_selection(self, sample_polars_df):
        _st.selectbox = MagicMock(return_value=None)
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.transform_column_handler()
        assert result is None

    def test_transform_column_handler_string_col(self, sample_polars_df):
        _st.selectbox = MagicMock(side_effect=["name", "trim"])
        _st.info = MagicMock()
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.transform_column_handler()
        assert result is not None
        assert result["source_columns"] == ["name"]
        assert result["method"] == "trim"

    def test_transform_column_handler_numeric_col(self, sample_polars_df):
        _st.selectbox = MagicMock(side_effect=["age", "add"])
        _st.info = MagicMock()
        _st.number_input = MagicMock(return_value=5.0)
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.transform_column_handler()
        assert result is not None
        assert result["source_columns"] == ["age"]

    def test_transform_column_handler_datetime_col(self, sample_polars_df):
        _st.selectbox = MagicMock(side_effect=["date", "hour"])
        _st.info = MagicMock()
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.transform_column_handler()
        assert result is not None
        assert result["source_columns"] == ["date"]
        assert result["method"] == "hour"

    def test_render_transform_inputs_unknown_type(self, sample_polars_df):
        handler = PrepStepHandler(sample_polars_df, 0)
        inputs = TransformInputs()
        result = handler._render_transform_inputs_by_type(pl.Boolean, inputs)
        assert result.func is None

    def test_render_transform_inputs_float_col(self, sample_polars_df):
        _st.selectbox = MagicMock(side_effect=["score", "round"])
        _st.info = MagicMock()
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.transform_column_handler()
        assert result is not None
        assert result["source_columns"] == ["score"]

    def test_remove_column_handler_with_selection(self, sample_polars_df):
        _st.multiselect = MagicMock(return_value=["name", "age"])
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.remove_column_handler()
        assert result["action"] == PrepActions.remove_column.value
        assert result["affected_count"] == 2
        assert result["remaining_count"] == sample_polars_df.shape[1] - 2
        assert result["source_columns"] == ["name", "age"]
        assert result["column_names"] is None
        assert result["value"] is None
        assert result["method"] is None
        assert result["condition"] is None

    def test_remove_column_handler_no_selection(self, sample_polars_df):
        _st.multiselect = MagicMock(return_value=[])
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.remove_column_handler()
        assert result["affected_count"] == 0
        assert result["remaining_count"] == sample_polars_df.shape[1]
        assert result["source_columns"] == []

    def test_remove_rows_handler_by_index(self, sample_polars_df):
        _st.selectbox = MagicMock(return_value=PrepMethods.row_index.value)
        _st.text_input = MagicMock(return_value="1, 2, 3")
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.remove_rows_handler()
        assert result["method"] == PrepMethods.row_index.value
        assert result["value"] == ["1", "2", "3"]

    def test_remove_rows_handler_by_index_empty(self, sample_polars_df):
        _st.selectbox = MagicMock(return_value=PrepMethods.row_index.value)
        _st.text_input = MagicMock(return_value="")
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.remove_rows_handler()
        assert result["method"] == PrepMethods.row_index.value

    def test_remove_rows_handler_by_condition(self, sample_polars_df):
        _st.selectbox = MagicMock(
            side_effect=[
                PrepMethods.condition.value,
                PrepRowConditions.equal_to.value,
                "Alice",
            ]
        )
        _st.multiselect = MagicMock(return_value=["name"])
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.remove_rows_handler()
        assert result["method"] == PrepMethods.condition.value

    def test_remove_rows_handler_condition_no_condition(self, sample_polars_df):
        _st.selectbox = MagicMock(side_effect=[PrepMethods.condition.value, None])
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.remove_rows_handler()
        assert result["condition"] is None

    def test_remove_rows_handler_condition_no_columns(self, sample_polars_df):
        _st.selectbox = MagicMock(
            side_effect=[
                PrepMethods.condition.value,
                PrepRowConditions.missing.value,
            ]
        )
        _st.multiselect = MagicMock(return_value=[])
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.remove_rows_handler()
        assert result["source_columns"] == []

    def test_remove_rows_handler_condition_between(self, sample_polars_df):
        _st.selectbox = MagicMock(
            side_effect=[
                PrepMethods.condition.value,
                PrepRowConditions.between.value,
                25,
                35,
            ]
        )
        _st.multiselect = MagicMock(return_value=["age"])
        _st.error = MagicMock()
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.remove_rows_handler()
        assert result["method"] == PrepMethods.condition.value

    def test_remove_rows_handler_condition_like(self, sample_polars_df):
        _st.selectbox = MagicMock(
            side_effect=[
                PrepMethods.condition.value,
                PrepRowConditions.like.value,
            ]
        )
        _st.multiselect = MagicMock(return_value=["name"])
        _st.text_input = MagicMock(return_value="Al.*")
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.remove_rows_handler()
        assert result["method"] == PrepMethods.condition.value

    def test_remove_rows_handler_condition_not_like(self, sample_polars_df):
        _st.selectbox = MagicMock(
            side_effect=[
                PrepMethods.condition.value,
                PrepRowConditions.not_like.value,
            ]
        )
        _st.multiselect = MagicMock(return_value=["name"])
        _st.text_input = MagicMock(return_value="Bob")
        handler = PrepStepHandler(sample_polars_df, 0)
        result = handler.remove_rows_handler()
        assert result["method"] == PrepMethods.condition.value

    def test_render_condition_value_inputs_equality(self, sample_polars_df):
        handler = PrepStepHandler(sample_polars_df, 0)
        inputs = RemoveRowsInputs()
        inputs.condition = PrepRowConditions.equal_to.value
        inputs.selected_columns = ["name"]
        _st.selectbox = MagicMock(return_value="Alice")
        handler._render_condition_value_inputs(inputs)
        assert inputs.equality_values == "Alice"

    def test_render_condition_value_inputs_not_equal(self, sample_polars_df):
        handler = PrepStepHandler(sample_polars_df, 0)
        inputs = RemoveRowsInputs()
        inputs.condition = PrepRowConditions.not_equal_to.value
        inputs.selected_columns = ["name"]
        _st.selectbox = MagicMock(return_value="Bob")
        handler._render_condition_value_inputs(inputs)
        assert inputs.equality_values == "Bob"

    def test_render_condition_value_inputs_between(self, sample_polars_df):
        handler = PrepStepHandler(sample_polars_df, 0)
        inputs = RemoveRowsInputs()
        inputs.condition = PrepRowConditions.between.value
        inputs.selected_columns = ["age"]
        _st.selectbox = MagicMock(side_effect=[25, 35])
        _st.error = MagicMock()
        handler._render_condition_value_inputs(inputs)
        assert inputs.min_value == 25
        assert inputs.max_value == 35

    def test_render_condition_value_inputs_like(self, sample_polars_df):
        handler = PrepStepHandler(sample_polars_df, 0)
        inputs = RemoveRowsInputs()
        inputs.condition = PrepRowConditions.like.value
        inputs.selected_columns = ["name"]
        _st.text_input = MagicMock(return_value="Al.*")
        handler._render_condition_value_inputs(inputs)
        assert inputs.pattern_value == "Al.*"

    def test_render_condition_value_inputs_not_like(self, sample_polars_df):
        handler = PrepStepHandler(sample_polars_df, 0)
        inputs = RemoveRowsInputs()
        inputs.condition = PrepRowConditions.not_like.value
        inputs.selected_columns = ["name"]
        _st.text_input = MagicMock(return_value="Bob")
        handler._render_condition_value_inputs(inputs)
        assert inputs.pattern_value == "Bob"

    def test_render_condition_value_inputs_between_mixed_types(self):
        df = pl.DataFrame({"a": [1, 2], "b": [1.5, 2.5]})
        handler = PrepStepHandler(df, 0)
        inputs = RemoveRowsInputs()
        inputs.condition = PrepRowConditions.between.value
        inputs.selected_columns = ["a", "b"]
        _st.selectbox = MagicMock(side_effect=[1, 2])
        _st.error = MagicMock()
        handler._render_condition_value_inputs(inputs)
        _st.error.assert_called_once()

    def test_render_condition_value_inputs_missing(self, sample_polars_df):
        """Condition like 'missing' should not render any value inputs."""
        handler = PrepStepHandler(sample_polars_df, 0)
        inputs = RemoveRowsInputs()
        inputs.condition = PrepRowConditions.missing.value
        inputs.selected_columns = ["name"]
        _st.selectbox = MagicMock()
        _st.text_input = MagicMock()
        handler._render_condition_value_inputs(inputs)
        # For missing condition, none of the value render methods should be called
        _st.selectbox.assert_not_called()
        _st.text_input.assert_not_called()

    def test_render_row_index_inputs_with_text(self, sample_polars_df):
        handler = PrepStepHandler(sample_polars_df, 0)
        inputs = RemoveRowsInputs()
        _st.text_input = MagicMock(return_value="1, 2, 3")
        handler._render_row_index_inputs(inputs)
        assert inputs.indexes_to_remove == ["1", "2", "3"]

    def test_render_row_index_inputs_empty(self, sample_polars_df):
        handler = PrepStepHandler(sample_polars_df, 0)
        inputs = RemoveRowsInputs()
        _st.text_input = MagicMock(return_value="")
        handler._render_row_index_inputs(inputs)
        assert inputs.indexes_to_remove == []

    def test_render_row_index_inputs_with_range(self, sample_polars_df):
        handler = PrepStepHandler(sample_polars_df, 0)
        inputs = RemoveRowsInputs()
        _st.text_input = MagicMock(return_value="5:-2")
        handler._render_row_index_inputs(inputs)
        assert inputs.indexes_to_remove == ["5:-2"]

    def test_render_condition_inputs_with_condition_and_columns(self, sample_polars_df):
        handler = PrepStepHandler(sample_polars_df, 0)
        inputs = RemoveRowsInputs()
        _st.selectbox = MagicMock(
            side_effect=[PrepRowConditions.equal_to.value, "Alice"]
        )
        _st.multiselect = MagicMock(return_value=["name"])
        handler._render_condition_inputs(inputs)
        assert inputs.condition == PrepRowConditions.equal_to.value
        assert inputs.selected_columns == ["name"]


# === PREP ADD/REMOVE STEP TESTS === #


class TestPrepAddStep:
    """Test prep_add_step function."""

    def test_no_action_selected(self, sample_polars_df):
        """When no action is selected, should show warning."""
        mock_popover = MagicMock()
        mock_popover.__enter__ = MagicMock(return_value=None)
        mock_popover.__exit__ = MagicMock(return_value=False)
        _st.popover = MagicMock(return_value=mock_popover)
        _st.selectbox = MagicMock(return_value=None)
        _st.info = MagicMock()
        _st.warning = MagicMock()

        prep_add_step(sample_polars_df, step_index=0)
        _st.warning.assert_called()

    def test_add_column_action_no_input(self, sample_polars_df):
        """When add column selected but no column name entered."""
        mock_popover = MagicMock()
        mock_popover.__enter__ = MagicMock(return_value=None)
        mock_popover.__exit__ = MagicMock(return_value=False)
        _st.popover = MagicMock(return_value=mock_popover)
        _st.selectbox = MagicMock(return_value=PrepActions.add_column.value)
        _st.text_input = MagicMock(return_value="")
        _st.info = MagicMock()
        _st.warning = MagicMock()

        prep_add_step(sample_polars_df, step_index=0)
        _st.warning.assert_called()

    def test_remove_column_action(self, sample_polars_df):
        """When remove column selected and columns chosen."""
        mock_popover = MagicMock()
        mock_popover.__enter__ = MagicMock(return_value=None)
        mock_popover.__exit__ = MagicMock(return_value=False)
        _st.popover = MagicMock(return_value=mock_popover)
        _st.selectbox = MagicMock(return_value=PrepActions.remove_column.value)
        _st.multiselect = MagicMock(return_value=["name"])
        _st.info = MagicMock()
        _st.button = MagicMock(return_value=False)

        prep_add_step(sample_polars_df, step_index=0)
        _st.button.assert_called_once()

    def test_transform_column_action(self, sample_polars_df):
        """When transform column selected."""
        mock_popover = MagicMock()
        mock_popover.__enter__ = MagicMock(return_value=None)
        mock_popover.__exit__ = MagicMock(return_value=False)
        _st.popover = MagicMock(return_value=mock_popover)
        _st.selectbox = MagicMock(
            side_effect=[PrepActions.transform_column.value, "name", "trim"]
        )
        _st.info = MagicMock()
        _st.button = MagicMock(return_value=False)

        prep_add_step(sample_polars_df, step_index=0)

    def test_remove_row_action(self, sample_polars_df):
        """When remove row selected."""
        mock_popover = MagicMock()
        mock_popover.__enter__ = MagicMock(return_value=None)
        mock_popover.__exit__ = MagicMock(return_value=False)
        _st.popover = MagicMock(return_value=mock_popover)
        _st.selectbox = MagicMock(
            side_effect=[
                PrepActions.remove_row.value,
                PrepMethods.row_index.value,
            ]
        )
        _st.text_input = MagicMock(return_value="1, 2")
        _st.info = MagicMock()
        _st.button = MagicMock(return_value=False)

        prep_add_step(sample_polars_df, step_index=0)

    @patch("datasure.views.prep_view.prep_apply_action")
    def test_add_button_clicked(self, mock_prep_apply, sample_polars_df):
        """When Add button is clicked with valid data."""
        import datasure.views.prep_view as pv

        # Set module-level variables needed by prep_add_step
        pv.project_id = "test_project"
        pv.label = "test_label"

        mock_popover = MagicMock()
        mock_popover.__enter__ = MagicMock(return_value=None)
        mock_popover.__exit__ = MagicMock(return_value=False)
        _st.popover = MagicMock(return_value=mock_popover)
        _st.selectbox = MagicMock(return_value=PrepActions.remove_column.value)
        _st.multiselect = MagicMock(return_value=["name"])
        _st.info = MagicMock()
        _st.button = MagicMock(return_value=True)
        _st.success = MagicMock()
        _st.rerun = MagicMock()

        prep_add_step(sample_polars_df, step_index=0)
        mock_prep_apply.assert_called_once()
        _st.success.assert_called_once()
        _st.rerun.assert_called_once()


class TestModuleLevelPageLayout:
    """Test the module-level page layout code by reloading the module."""

    def test_page_layout_with_aliases(self):
        """Reload prep_view with aliases to cover the tab rendering code."""
        import importlib

        import datasure.views.prep_view as pv_mod

        # Set up session state
        _st.session_state["st_project_id"] = "test_project"
        _st.session_state["st_import_data_page"] = "import_page"
        _st.session_state["st_config_checks_page"] = "config_page"
        _st.stop = MagicMock()

        # Create sample data for the tab rendering
        sample_df = pl.DataFrame(
            {
                "name": ["Alice", "Bob"],
                "age": [25, 30],
            }
        )
        # Create a non-empty prep log
        prep_log_df = pl.DataFrame(
            {"action": ["add column"], "description": ["Added col1"]}
        )

        # Mock tab context manager
        mock_tab = MagicMock()
        mock_tab.__enter__ = MagicMock(return_value=mock_tab)
        mock_tab.__exit__ = MagicMock(return_value=False)
        _st.tabs = MagicMock(return_value=[mock_tab])

        # Mock columns with context manager support
        mock_col = MagicMock()
        mock_col.__enter__ = MagicMock(return_value=mock_col)
        mock_col.__exit__ = MagicMock(return_value=False)
        _st.columns = MagicMock(return_value=[mock_col, mock_col, mock_col])

        # Mock container context manager
        mock_container = MagicMock()
        mock_container.__enter__ = MagicMock(return_value=mock_container)
        mock_container.__exit__ = MagicMock(return_value=False)
        _st.container = MagicMock(return_value=mock_container)

        # Mock popover context manager
        mock_popover = MagicMock()
        mock_popover.__enter__ = MagicMock(return_value=mock_popover)
        mock_popover.__exit__ = MagicMock(return_value=False)
        _st.popover = MagicMock(return_value=mock_popover)

        # Mock UI widgets to prevent execution of action handlers
        _st.button = MagicMock(return_value=False)
        _st.selectbox = MagicMock(return_value=None)
        _st.multiselect = MagicMock(return_value=[])

        with (
            patch(
                "datasure.utils.duckdb_utils.duckdb_get_aliases",
                return_value=["test_data"],
            ),
            patch(
                "datasure.utils.duckdb_utils.duckdb_get_table",
                side_effect=[
                    prep_log_df,  # prep_log for tab
                    sample_df,  # prep_data for tab
                    prep_log_df,  # prep_log re-fetch in change log
                    prep_log_df,  # prep_log in prep_remove_step
                ],
            ),
            patch("datasure.utils.duckdb_utils.duckdb_save_table"),
            patch("datasure.utils.navigations_utils.page_navigation"),
            patch("datasure.utils.navigations_utils.add_demo_navigation"),
            patch("datasure.utils.navigations_utils.demo_sidebar_help"),
            patch("datasure.utils.navigations_utils.demo_callout"),
            patch("datasure.utils.navigations_utils.show_demo_next_action"),
            patch(
                "datasure.utils.onboarding_utils.is_demo_project",
                return_value=False,
            ),
            patch("datasure.utils.onboarding_utils.demo_expander"),
            patch("datasure.processing.prep.prep_apply_action"),
        ):
            importlib.reload(pv_mod)

        # Restore session state
        _st.session_state["st_project_id"] = None
        _st.stop = _orig_stop

    def test_page_layout_with_failed_status_in_log(self):
        """Change Log renders a status column and styles a Failed row."""
        import importlib

        _st.session_state["st_project_id"] = "test_project"
        _st.session_state["st_import_data_page"] = "import_page"
        _st.session_state["st_config_checks_page"] = "config_page"
        _st.stop = MagicMock()

        sample_df = pl.DataFrame({"name": ["Alice", "Bob"], "age": [25, 30]})
        # A log with one failed and one successful step (mixed status column)
        prep_log_df = pl.DataFrame(
            {
                "action": ["remove column(s)", "add column"],
                "description": [
                    "✗ Failed to reapply: Columns not found: ['missing']",
                    "✓ 1 column added.",
                ],
                "status": ["Failed", "Successful"],
            }
        )

        mock_tab = MagicMock()
        mock_tab.__enter__ = MagicMock(return_value=mock_tab)
        mock_tab.__exit__ = MagicMock(return_value=False)
        _st.tabs = MagicMock(return_value=[mock_tab])

        mock_col = MagicMock()
        mock_col.__enter__ = MagicMock(return_value=mock_col)
        mock_col.__exit__ = MagicMock(return_value=False)
        _st.columns = MagicMock(return_value=[mock_col, mock_col, mock_col])

        mock_container = MagicMock()
        mock_container.__enter__ = MagicMock(return_value=mock_container)
        mock_container.__exit__ = MagicMock(return_value=False)
        _st.container = MagicMock(return_value=mock_container)

        mock_popover = MagicMock()
        mock_popover.__enter__ = MagicMock(return_value=mock_popover)
        mock_popover.__exit__ = MagicMock(return_value=False)
        _st.popover = MagicMock(return_value=mock_popover)

        _st.button = MagicMock(return_value=False)
        _st.selectbox = MagicMock(return_value=None)
        _st.multiselect = MagicMock(return_value=[])
        _st.dataframe = MagicMock()

        with (
            patch(
                "datasure.utils.duckdb_utils.duckdb_get_aliases",
                return_value=["test_data"],
            ),
            patch(
                "datasure.utils.duckdb_utils.duckdb_get_table",
                side_effect=[
                    prep_log_df,
                    sample_df,
                    prep_log_df,
                    prep_log_df,
                ],
            ),
            patch("datasure.utils.duckdb_utils.duckdb_save_table"),
            patch("datasure.utils.navigations_utils.page_navigation"),
            patch("datasure.utils.navigations_utils.add_demo_navigation"),
            patch("datasure.utils.navigations_utils.demo_sidebar_help"),
            patch("datasure.utils.navigations_utils.demo_callout"),
            patch("datasure.utils.navigations_utils.show_demo_next_action"),
            patch(
                "datasure.utils.onboarding_utils.is_demo_project",
                return_value=False,
            ),
            patch("datasure.utils.onboarding_utils.demo_expander"),
            patch("datasure.processing.prep.prep_apply_action"),
        ):
            importlib.reload(pv_mod)

        # The Change Log table (first st.dataframe call) is a styled pandas
        # DataFrame with the status column positioned right after action
        rendered = _st.dataframe.call_args_list[0][0][0]
        assert list(rendered.data.columns) == ["action", "status", "description"]

        _st.session_state["st_project_id"] = None
        _st.stop = _orig_stop

    def test_page_layout_with_empty_prep_data(self):
        """Test when prep_data and prep_log are both empty (falls back to raw)."""
        import importlib

        import datasure.views.prep_view as pv_mod

        _st.session_state["st_project_id"] = "test_project"
        _st.session_state["st_import_data_page"] = "import_page"
        _st.session_state["st_config_checks_page"] = "config_page"
        _st.stop = MagicMock()

        # Empty dataframes (triggers the raw data fallback)
        empty_df = pl.DataFrame({"name": pl.Series([], dtype=pl.String)})
        raw_df = pl.DataFrame({"name": ["Alice"], "age": [25]})
        empty_log = pl.DataFrame(
            {
                "action": pl.Series([], dtype=pl.String),
                "description": pl.Series([], dtype=pl.String),
            }
        )

        mock_tab = MagicMock()
        mock_tab.__enter__ = MagicMock(return_value=mock_tab)
        mock_tab.__exit__ = MagicMock(return_value=False)
        _st.tabs = MagicMock(return_value=[mock_tab])

        mock_col = MagicMock()
        mock_col.__enter__ = MagicMock(return_value=mock_col)
        mock_col.__exit__ = MagicMock(return_value=False)
        _st.columns = MagicMock(return_value=[mock_col, mock_col, mock_col])

        mock_container = MagicMock()
        mock_container.__enter__ = MagicMock(return_value=mock_container)
        mock_container.__exit__ = MagicMock(return_value=False)
        _st.container = MagicMock(return_value=mock_container)

        mock_popover = MagicMock()
        mock_popover.__enter__ = MagicMock(return_value=mock_popover)
        mock_popover.__exit__ = MagicMock(return_value=False)
        _st.popover = MagicMock(return_value=mock_popover)

        # Mock UI widgets to prevent execution of action handlers
        _st.button = MagicMock(return_value=False)
        _st.selectbox = MagicMock(return_value=None)
        _st.multiselect = MagicMock(return_value=[])

        with (
            patch(
                "datasure.utils.duckdb_utils.duckdb_get_aliases",
                return_value=["test_data"],
            ),
            patch(
                "datasure.utils.duckdb_utils.duckdb_get_table",
                side_effect=[
                    empty_log,  # prep_log
                    empty_df,  # prep_data (empty)
                    raw_df,  # raw data fallback
                    empty_log,  # prep_log in prep_remove_step
                    empty_log,  # prep_log re-fetch in change log
                ],
            ),
            patch("datasure.utils.duckdb_utils.duckdb_save_table") as mock_save,
            patch("datasure.utils.navigations_utils.page_navigation"),
            patch("datasure.utils.navigations_utils.add_demo_navigation"),
            patch("datasure.utils.navigations_utils.demo_sidebar_help"),
            patch("datasure.utils.navigations_utils.demo_callout"),
            patch("datasure.utils.navigations_utils.show_demo_next_action"),
            patch(
                "datasure.utils.onboarding_utils.is_demo_project",
                return_value=False,
            ),
            patch("datasure.utils.onboarding_utils.demo_expander"),
            patch("datasure.processing.prep.prep_apply_action"),
        ):
            importlib.reload(pv_mod)
            # Verify that raw data was saved as prep data
            mock_save.assert_called()

        _st.session_state["st_project_id"] = None
        _st.stop = _orig_stop

    def test_page_layout_no_project_id(self):
        """Test page guard when no project_id is set."""
        import importlib

        import datasure.views.prep_view as pv_mod

        _st.session_state["st_project_id"] = None
        _st.stop = MagicMock()
        _st.info = MagicMock()

        with (
            patch(
                "datasure.utils.duckdb_utils.duckdb_get_aliases",
                return_value=[],
            ),
            patch("datasure.utils.navigations_utils.page_navigation"),
            patch("datasure.utils.navigations_utils.add_demo_navigation"),
            patch("datasure.utils.navigations_utils.demo_sidebar_help"),
            patch("datasure.utils.navigations_utils.demo_callout"),
            patch("datasure.utils.navigations_utils.show_demo_next_action"),
            patch(
                "datasure.utils.onboarding_utils.is_demo_project",
                return_value=False,
            ),
            patch("datasure.utils.onboarding_utils.demo_expander"),
        ):
            importlib.reload(pv_mod)

        _st.session_state["st_project_id"] = None
        _st.stop = _orig_stop


class TestPrepRemoveStep:
    """Test prep_remove_step function."""

    @patch("datasure.views.prep_view.duckdb_get_table")
    def test_empty_prep_log(self, mock_get_table):
        """When prep log is empty."""
        import datasure.views.prep_view as pv

        pv.project_id = "test_project"
        pv.label = "test_label"
        pv.i = 0

        mock_popover = MagicMock()
        mock_popover.__enter__ = MagicMock(return_value=None)
        mock_popover.__exit__ = MagicMock(return_value=False)
        _st.popover = MagicMock(return_value=mock_popover)

        import pandas as pd

        mock_get_table.return_value = pl.DataFrame({"action": [], "description": []})
        # to_pandas() is called on the result
        mock_get_table.return_value = MagicMock()
        mock_get_table.return_value.to_pandas.return_value = pd.DataFrame(
            {"action": [], "description": []}
        )
        _st.info = MagicMock()

        prep_remove_step()
        _st.info.assert_called()

    @patch("datasure.views.prep_view.duckdb_get_table")
    def test_with_prep_log_no_selection(self, mock_get_table):
        """When prep log has entries but no action selected."""
        import pandas as pd

        import datasure.views.prep_view as pv

        pv.project_id = "test_project"
        pv.label = "test_label"
        pv.i = 0

        mock_popover = MagicMock()
        mock_popover.__enter__ = MagicMock(return_value=None)
        mock_popover.__exit__ = MagicMock(return_value=False)
        _st.popover = MagicMock(return_value=mock_popover)

        mock_get_table.return_value = MagicMock()
        mock_get_table.return_value.to_pandas.return_value = pd.DataFrame(
            {
                "action": ["remove column(s)"],
                "description": ["Removed col1"],
            }
        )
        _st.selectbox = MagicMock(return_value=None)
        _st.button = MagicMock(return_value=False)

        prep_remove_step()
        # With entries present, the action selector is rendered.
        _st.selectbox.assert_called()

    @patch("datasure.views.prep_view.prep_apply_action")
    @patch("datasure.views.prep_view.duckdb_save_table")
    @patch("datasure.views.prep_view.duckdb_get_table")
    def test_remove_confirm(self, mock_get_table, mock_save_table, mock_prep_apply):
        """When remove button clicked with valid selection."""
        import pandas as pd

        import datasure.views.prep_view as pv

        pv.project_id = "test_project"
        pv.label = "test_label"
        pv.i = 0

        mock_popover = MagicMock()
        mock_popover.__enter__ = MagicMock(return_value=None)
        mock_popover.__exit__ = MagicMock(return_value=False)
        _st.popover = MagicMock(return_value=mock_popover)

        log_df = pd.DataFrame(
            {
                "action": ["remove column(s)", "add new column"],
                "description": ["Removed col1", "Added col2"],
            }
        )
        mock_get_table.return_value = MagicMock()
        mock_get_table.return_value.to_pandas.return_value = log_df

        action_index_val = "0 - remove column(s) - Removed col1"
        _st.warning = MagicMock()
        _st.selectbox = MagicMock(return_value=action_index_val)
        # Clicking "Remove" opens confirm_dialog; the dialog's "Remove" button
        # then runs the removal. Return True for both, False for "Cancel".
        _st.button = MagicMock(
            side_effect=lambda label=None, *a, **k: label != "Cancel"
        )
        # Make @st.dialog a no-op decorator so the dialog body runs, and give
        # confirm_dialog its two columns.
        _st.dialog = MagicMock(side_effect=lambda *a, **k: lambda fn: fn)
        _st.columns = MagicMock(return_value=[MagicMock(), MagicMock()])
        _st.success = MagicMock()
        _st.rerun = MagicMock()

        prep_remove_step()
        mock_save_table.assert_called_once()
        mock_prep_apply.assert_called_once()
        _st.success.assert_called_once()
        _st.rerun.assert_called_once()
