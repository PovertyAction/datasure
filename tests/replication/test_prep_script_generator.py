"""Tests for the Stata prep script generator."""

from __future__ import annotations

import polars as pl

from datasure.replication.prep_script_generator import (
    _col_list,
    _cols,
    _fmt_val,
    _is_numeric_val,
    _stata_add_column,
    _stata_redact_columns,
    _stata_remove_columns,
    _stata_remove_rows,
    _stata_transform_column,
    _val,
    _val_list,
    generate_prepare_data_script,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class TestCols:
    def test_list_source_columns(self):
        assert _cols({"source_columns": ["a", "b"]}) == ["a", "b"]

    def test_string_source_columns(self):
        assert _cols({"source_columns": "x"}) == ["x"]

    def test_missing_key_returns_empty(self):
        assert _cols({}) == []

    def test_none_returns_empty(self):
        assert _cols({"source_columns": None}) == []


class TestVal:
    def test_returns_value(self):
        assert _val({"value": 42}) == 42

    def test_missing_returns_none(self):
        assert _val({}) is None


class TestValList:
    def test_list_value(self):
        assert _val_list({"value": [1, 2]}) == [1, 2]

    def test_scalar_wrapped_in_list(self):
        assert _val_list({"value": 5}) == [5]

    def test_none_returns_empty(self):
        assert _val_list({}) == []

    def test_explicit_none_returns_empty(self):
        assert _val_list({"value": None}) == []


class TestIsNumericVal:
    def test_integer_string(self):
        assert _is_numeric_val("1") is True

    def test_float_string(self):
        assert _is_numeric_val("3.14") is True

    def test_int(self):
        assert _is_numeric_val(5) is True

    def test_alpha_string(self):
        assert _is_numeric_val("abc") is False


class TestFmtVal:
    def test_numeric_string_unquoted(self):
        assert _fmt_val("42") == "42"

    def test_text_string_quoted(self):
        assert _fmt_val("hello") == '"hello"'

    def test_numeric_int(self):
        assert _fmt_val(10) == "10"


class TestColList:
    def test_single_col(self):
        assert _col_list(["age"]) == "age"

    def test_multiple_cols(self):
        assert _col_list(["a", "b", "c"]) == "a b c"

    def test_empty(self):
        assert _col_list([]) == ""


# ---------------------------------------------------------------------------
# Stata emitters
# ---------------------------------------------------------------------------


class TestStataRemoveColumns:
    def test_single_column(self):
        lines = _stata_remove_columns({"source_columns": ["age"]}, "")
        assert lines == ["drop age"]

    def test_multiple_columns(self):
        lines = _stata_remove_columns({"source_columns": ["a", "b"]}, "")
        assert lines == ["drop a b"]


class TestStataRedactColumns:
    def test_single_column(self):
        lines = _stata_redact_columns(
            {"source_columns": ["name"], "value": ["[PERSON]"]}, ""
        )
        assert lines == [
            "tostring name, replace force",
            'replace name = "[PERSON]" if name != ""',
        ]

    def test_single_string_label_applies_to_all(self):
        lines = _stata_redact_columns(
            {"source_columns": ["a", "b"], "value": "*****"}, ""
        )
        assert 'replace a = "*****" if a != ""' in lines
        assert 'replace b = "*****" if b != ""' in lines

    def test_mismatched_labels_fall_back_to_default(self):
        lines = _stata_redact_columns(
            {"source_columns": ["a", "b"], "value": ["only-one"]}, ""
        )
        assert 'replace a = "*****" if a != ""' in lines

    def test_hash_method_emits_note(self):
        lines = _stata_redact_columns(
            {"source_columns": ["name"], "value": ["PERSON"], "method": "hash"}, ""
        )
        assert all(line.startswith("*") for line in lines)
        assert "cannot be reproduced" in lines[0]

    def test_code_method_emits_note(self):
        lines = _stata_redact_columns(
            {"source_columns": ["village"], "method": "code"}, ""
        )
        assert all(line.startswith("*") for line in lines)


class TestStataRemoveRows:
    def test_by_index_single(self):
        lines = _stata_remove_rows({"method": "by row index", "value": [5]}, "")
        assert lines == ["drop in 5"]

    def test_by_index_multiple(self):
        lines = _stata_remove_rows({"method": "by row index", "value": [1, 3]}, "")
        assert lines == ["drop if _n == 1 | _n == 3"]

    def test_missing_condition(self):
        lines = _stata_remove_rows(
            {"source_columns": ["col"], "condition": "value is missing"}, ""
        )
        assert lines == ["drop if missing(col)"]

    def test_not_missing_condition(self):
        lines = _stata_remove_rows(
            {"source_columns": ["col"], "condition": "value is not missing"}, ""
        )
        assert lines == ["keep if missing(col)"]

    def test_like_condition(self):
        lines = _stata_remove_rows(
            {
                "source_columns": ["name"],
                "condition": "value is like",
                "value": ["^test"],
            },
            "",
        )
        assert 'regexm(name, "^test")' in lines[0]

    def test_not_like_condition(self):
        lines = _stata_remove_rows(
            {
                "source_columns": ["name"],
                "condition": "value is not like",
                "value": ["^test"],
            },
            "",
        )
        assert "keep if" in lines[0]

    def test_between_condition(self):
        lines = _stata_remove_rows(
            {
                "source_columns": ["age"],
                "condition": "value is between",
                "value": [18, 65],
            },
            "",
        )
        assert "inrange(age, 18, 65)" in lines[0]

    def test_not_between_condition(self):
        lines = _stata_remove_rows(
            {
                "source_columns": ["age"],
                "condition": "value is not between",
                "value": [18, 65],
            },
            "",
        )
        assert "keep if inrange" in lines[0]

    def test_greater_than_condition(self):
        lines = _stata_remove_rows(
            {
                "source_columns": ["score"],
                "condition": "value is greater than",
                "value": [100],
            },
            "",
        )
        assert "keep if score <= 100" in lines[0]

    def test_equal_condition(self):
        lines = _stata_remove_rows(
            {
                "source_columns": ["status"],
                "condition": "value is equal to",
                "value": ["active"],
            },
            "",
        )
        assert "keep if status !=" in lines[0]

    def test_no_cols_no_condition_returns_note(self):
        lines = _stata_remove_rows({}, "")
        assert "NOTE" in lines[0]

    def test_unknown_condition_returns_note(self):
        lines = _stata_remove_rows(
            {"source_columns": ["col"], "condition": "something weird"}, ""
        )
        assert "NOTE" in lines[0]


class TestStataTransformColumn:
    def test_trim(self):
        lines = _stata_transform_column(
            {"source_columns": ["name"], "method": "trim"}, ""
        )
        assert "strtrim" in lines[0]

    def test_lowercase(self):
        lines = _stata_transform_column(
            {"source_columns": ["col"], "method": "lowercase"}, ""
        )
        assert "lower(" in lines[0]

    def test_uppercase(self):
        lines = _stata_transform_column(
            {"source_columns": ["col"], "method": "uppercase"}, ""
        )
        assert "upper(" in lines[0]

    def test_absolute_value(self):
        lines = _stata_transform_column(
            {"source_columns": ["col"], "method": "absolute value"}, ""
        )
        assert "abs(" in lines[0]

    def test_add_arithmetic(self):
        lines = _stata_transform_column(
            {"source_columns": ["col"], "method": "add", "value": [5]}, ""
        )
        assert "col + 5" in lines[0]

    def test_subtract_arithmetic(self):
        lines = _stata_transform_column(
            {"source_columns": ["col"], "method": "subtract", "value": [2]}, ""
        )
        assert "col - 2" in lines[0]

    def test_replace_method(self):
        lines = _stata_transform_column(
            {"source_columns": ["col"], "method": "replace", "value": ["old", "new"]},
            "",
        )
        assert "subinstr" in lines[0]

    def test_substring_method(self):
        lines = _stata_transform_column(
            {"source_columns": ["col"], "method": "substring", "value": [0, 5]}, ""
        )
        assert "substr" in lines[0]

    def test_extract_pattern(self):
        lines = _stata_transform_column(
            {
                "source_columns": ["col"],
                "method": "extract pattern",
                "value": ["[0-9]+"],
            },
            "",
        )
        assert "regexm" in lines[0]

    def test_get_dummies(self):
        lines = _stata_transform_column(
            {"source_columns": ["cat"], "method": "get dummies"}, ""
        )
        assert "tabulate" in lines[0]

    def test_unknown_method_returns_note(self):
        lines = _stata_transform_column(
            {"source_columns": ["col"], "method": "unknown_method"}, ""
        )
        assert "NOTE" in lines[0]

    def test_string_to_number(self):
        lines = _stata_transform_column(
            {"source_columns": ["col"], "method": "string to number"}, ""
        )
        assert "destring" in lines[0]

    def test_floor(self):
        lines = _stata_transform_column(
            {"source_columns": ["col"], "method": "floor"}, ""
        )
        assert "floor(" in lines[0]

    def test_year(self):
        lines = _stata_transform_column(
            {"source_columns": ["dob"], "method": "year"}, ""
        )
        assert "year(" in lines[0]


class TestStataAddColumn:
    def test_constant_numeric(self):
        lines = _stata_add_column(
            {"column_names": "new_col", "method": "constant", "value": [5]}, ""
        )
        assert "gen new_col = 5" in lines[0]

    def test_constant_string(self):
        lines = _stata_add_column(
            {"column_names": "new_col", "method": "constant", "value": ["hello"]}, ""
        )
        assert 'gen new_col = "hello"' in lines[0]

    def test_index(self):
        lines = _stata_add_column({"column_names": "idx", "method": "index"}, "")
        assert "gen idx = _n" in lines[0]

    def test_uuid_note(self):
        lines = _stata_add_column({"column_names": "uid", "method": "uuid"}, "")
        assert "NOTE" in lines[0]

    def test_random(self):
        lines = _stata_add_column({"column_names": "rnd", "method": "random"}, "")
        assert "runiform()" in lines[0]

    def test_sum_aggregation(self):
        lines = _stata_add_column(
            {"column_names": "total", "method": "sum", "source_columns": ["a", "b"]},
            "",
        )
        assert "gen total = a+b" in lines[0]

    def test_mean_aggregation(self):
        lines = _stata_add_column(
            {"column_names": "avg", "method": "mean", "source_columns": ["a", "b"]},
            "",
        )
        assert "gen avg = " in lines[0]
        assert "+ b)" in lines[0]

    def test_first(self):
        lines = _stata_add_column(
            {
                "column_names": "first_col",
                "method": "first",
                "source_columns": ["a", "b"],
            },
            "",
        )
        assert "gen first_col = a" in lines[0]

    def test_last(self):
        lines = _stata_add_column(
            {
                "column_names": "last_col",
                "method": "last",
                "source_columns": ["a", "b"],
            },
            "",
        )
        assert "gen last_col = b" in lines[0]

    def test_diff(self):
        lines = _stata_add_column(
            {"column_names": "d", "method": "diff", "source_columns": ["a", "b"]}, ""
        )
        assert "gen d = a - b" in lines[0]

    def test_quotient(self):
        lines = _stata_add_column(
            {"column_names": "q", "method": "quotient", "source_columns": ["a", "b"]},
            "",
        )
        assert "gen q = a / b" in lines[0]

    def test_unknown_method_returns_note(self):
        lines = _stata_add_column({"column_names": "nc", "method": "unknown"}, "")
        assert "NOTE" in lines[0]

    def test_min_aggregation(self):
        lines = _stata_add_column(
            {"column_names": "mn", "method": "min", "source_columns": ["a", "b"]},
            "",
        )
        assert "min(a, b)" in lines[0]

    def test_max_aggregation(self):
        lines = _stata_add_column(
            {"column_names": "mx", "method": "max", "source_columns": ["a", "b"]},
            "",
        )
        assert "max(a, b)" in lines[0]


# ---------------------------------------------------------------------------
# generate_prepare_data_script
# ---------------------------------------------------------------------------


class TestGeneratePrepareDataScript:
    def test_empty_log_returns_no_steps_message(self):
        log = pl.DataFrame(
            schema={
                "action": pl.String,
                "description": pl.String,
                "prep_args": pl.String,
                "action_index": pl.Int64,
            }
        )
        result = generate_prepare_data_script(log, "Proj", "Survey", "1.0")
        assert "No preparation steps recorded" in result

    def test_empty_log_has_header(self):
        log = pl.DataFrame(
            schema={
                "action": pl.String,
                "description": pl.String,
                "prep_args": pl.String,
                "action_index": pl.Int64,
            }
        )
        result = generate_prepare_data_script(log, "Proj", "Survey", "1.0")
        assert "Data Preparation Script" in result

    def test_remove_column_step(self):
        log = pl.DataFrame(
            {
                "action": ["remove column(s)"],
                "description": ["Drop age column"],
                "prep_args": ['{"source_columns": ["age"]}'],
                "action_index": [1],
            }
        )
        result = generate_prepare_data_script(log, "P", "S", "0.1")
        assert "drop age" in result

    def test_unknown_action_returns_note(self):
        log = pl.DataFrame(
            {
                "action": ["mystery action"],
                "description": ["Some step"],
                "prep_args": ["{}"],
                "action_index": [1],
            }
        )
        result = generate_prepare_data_script(log, "P", "S", "0.1")
        assert "unknown action" in result

    def test_dict_prep_args(self):
        log = pl.DataFrame(
            {
                "action": ["remove column(s)"],
                "description": ["Drop col"],
                "prep_args": ['{"source_columns": ["x"]}'],
                "action_index": [1],
            }
        )
        result = generate_prepare_data_script(log, "P", "S", "0.1")
        assert "drop x" in result

    def test_invalid_json_falls_back_to_empty_args(self):
        log = pl.DataFrame(
            {
                "action": ["remove column(s)"],
                "description": ["Drop col"],
                "prep_args": ["NOT_VALID_JSON"],
                "action_index": [1],
            }
        )
        # Should not crash — just emit a note since cols list will be empty
        result = generate_prepare_data_script(log, "P", "S", "0.1")
        assert isinstance(result, str)

    def test_step_comment_included(self):
        log = pl.DataFrame(
            {
                "action": ["remove column(s)"],
                "description": ["Removes old column"],
                "prep_args": ['{"source_columns": ["old"]}'],
                "action_index": [1],
            }
        )
        result = generate_prepare_data_script(log, "P", "S", "0.1")
        assert "Removes old column" in result

    def test_returns_string(self):
        log = pl.DataFrame(
            schema={
                "action": pl.String,
                "description": pl.String,
                "prep_args": pl.String,
                "action_index": pl.Int64,
            }
        )
        assert isinstance(generate_prepare_data_script(log, "P", "S", "1.0"), str)
