"""Tests for the Python/Polars prep script generator."""

from __future__ import annotations

import ast
import json

import polars as pl

from datasure.replication.py_prep_script_generator import (
    _py_add_column,
    _py_redact_columns,
    _py_remove_columns,
    _py_remove_rows,
    _py_transform_column,
    generate_prepare_data_script_py,
)

# ---------------------------------------------------------------------------
# _py_remove_columns
# ---------------------------------------------------------------------------


class TestPyRemoveColumns:
    def test_drops_listed_columns(self):
        lines = _py_remove_columns({"source_columns": ["a", "b"]}, "")
        assert lines == ["df = df.drop(['a', 'b'])"]


# ---------------------------------------------------------------------------
# _py_redact_columns
# ---------------------------------------------------------------------------


class TestPyRedactColumns:
    def test_single_column(self):
        lines = _py_redact_columns(
            {"source_columns": ["name"], "value": ["[PERSON]"]}, ""
        )
        assert len(lines) == 1
        assert "pl.when(pl.col('name').is_not_null())" in lines[0]
        assert "pl.lit('[PERSON]')" in lines[0]

    def test_single_string_label_applies_to_all(self):
        lines = _py_redact_columns({"source_columns": ["a", "b"], "value": "*"}, "")
        assert len(lines) == 2
        assert all("pl.lit('*')" in line for line in lines)

    def test_generated_code_parses(self):
        lines = _py_redact_columns(
            {"source_columns": ["name"], "value": ["[PERSON]"]}, ""
        )
        ast.parse("\n".join(lines))


# ---------------------------------------------------------------------------
# _py_remove_rows
# ---------------------------------------------------------------------------


class TestPyRemoveRowsByIndex:
    def test_single_index(self):
        lines = _py_remove_rows({"method": "by row index", "value": [2]}, "")
        joined = "\n".join(lines)
        assert "with_row_index" in joined
        assert "[2]" in joined

    def test_range_syntax(self):
        lines = _py_remove_rows({"method": "by row index", "value": ["1:3"]}, "")
        joined = "\n".join(lines)
        assert "[1, 2, 3]" in joined

    def test_no_values_returns_note(self):
        lines = _py_remove_rows({"method": "by row index", "value": []}, "")
        assert lines == ["# NOTE: no row indices provided for drop"]


class TestPyRemoveRowsByCondition:
    def _rows(self, condition, value, cols=None):
        return _py_remove_rows(
            {
                "method": "by condition",
                "condition": condition,
                "source_columns": cols or ["age"],
                "value": value,
            },
            "",
        )

    def test_missing(self):
        lines = self._rows("value is missing", None)
        assert "is_null()" in lines[0]
        assert lines[0].startswith("df = df.filter(~")

    def test_not_missing(self):
        lines = self._rows("value is not missing", None)
        assert "is_null()" in lines[0]
        assert not lines[0].startswith("df = df.filter(~")

    def test_equal_to(self):
        lines = self._rows("value is equal to", [65])
        assert "is_in([65])" in lines[0]
        assert not lines[0].startswith("df = df.filter(~(")

    def test_not_equal_to(self):
        lines = self._rows("value is not equal to", [65])
        assert lines[0].startswith("df = df.filter(~(")

    def test_greater_than(self):
        lines = self._rows("value is greater than", [65])
        assert "<= 65.0" in lines[0]

    def test_less_than_or_equal_to(self):
        lines = self._rows("value is less than or equal to", [65])
        assert "> 65.0" in lines[0]

    def test_between(self):
        lines = self._rows("value is between", [10, 20])
        assert "< 10" in lines[0]
        assert "> 20" in lines[0]

    def test_not_between(self):
        lines = self._rows("value is not between", [10, 20])
        assert ">= 10" in lines[0]
        assert "<= 20" in lines[0]

    def test_like(self):
        lines = self._rows("value is like", ["foo"], cols=["name"])
        assert "all_horizontal" in lines[0]
        assert "'foo'" in lines[0]

    def test_not_like(self):
        lines = self._rows("value is not like", ["foo"], cols=["name"])
        assert "any_horizontal" in lines[0]

    def test_unknown_condition(self):
        lines = self._rows("value is unknowable", [1])
        assert "could not be translated" in lines[0]

    def test_missing_cols_or_condition_returns_note(self):
        lines = _py_remove_rows({"method": "by condition"}, "")
        assert "could not be translated" in lines[0]


# ---------------------------------------------------------------------------
# _py_transform_column
# ---------------------------------------------------------------------------


class TestPyTransformColumn:
    def test_trim(self):
        lines = _py_transform_column({"source_columns": ["name"], "method": "trim"}, "")
        assert "str.strip_chars()" in lines[0]
        assert "alias('name')" in lines[0]

    def test_uppercase(self):
        lines = _py_transform_column(
            {"source_columns": ["name"], "method": "uppercase"}, ""
        )
        assert "str.to_uppercase()" in lines[0]

    def test_floor(self):
        lines = _py_transform_column({"source_columns": ["x"], "method": "floor"}, "")
        assert "floor()" in lines[0]

    def test_day_of_month(self):
        lines = _py_transform_column(
            {"source_columns": ["dob"], "method": "day of month"}, ""
        )
        assert "dt.day()" in lines[0]

    def test_string_to_number(self):
        lines = _py_transform_column(
            {"source_columns": ["x"], "method": "string to number"}, ""
        )
        assert "cast(pl.Float64, strict=False)" in lines[0]

    def test_add_arithmetic(self):
        lines = _py_transform_column(
            {"source_columns": ["x"], "method": "add", "value": [5]}, ""
        )
        assert "+ 5" in lines[0]

    def test_string_to_date_uses_helper(self):
        lines = _py_transform_column(
            {"source_columns": ["dob"], "method": "string to date"}, ""
        )
        assert "_parse_flexible_datetime(df, 'dob')" in lines[0]

    def test_get_dummies(self):
        lines = _py_transform_column(
            {"source_columns": ["cat"], "method": "get dummies"}, ""
        )
        assert lines == ["df = df.to_dummies(columns=['cat'])"]

    def test_substring(self):
        lines = _py_transform_column(
            {"source_columns": ["x"], "method": "substring", "value": [0, 3]}, ""
        )
        assert "str.slice(0, 3)" in lines[0]

    def test_unknown_method_returns_note(self):
        lines = _py_transform_column(
            {"source_columns": ["x"], "method": "teleport"}, ""
        )
        assert "could not be translated" in lines[0]


# ---------------------------------------------------------------------------
# _py_add_column
# ---------------------------------------------------------------------------


class TestPyAddColumn:
    def test_constant_numeric(self):
        lines = _py_add_column(
            {"column_names": "flag", "method": "constant", "value": ["1"]}, ""
        )
        assert lines == ["df = df.with_columns(pl.lit(1).alias('flag'))"]

    def test_constant_string(self):
        lines = _py_add_column(
            {"column_names": "note", "method": "constant", "value": ["hi"]}, ""
        )
        assert "pl.lit('hi')" in lines[0]

    def test_index(self):
        lines = _py_add_column({"column_names": "idx", "method": "index"}, "")
        assert lines == ["df = df.with_row_index('idx')"]

    def test_sum(self):
        lines = _py_add_column(
            {
                "column_names": "total",
                "method": "sum",
                "source_columns": ["a", "b"],
            },
            "",
        )
        joined = "\n".join(lines)
        assert "pl.sum_horizontal(['a', 'b'])" in joined

    def test_diff(self):
        lines = _py_add_column(
            {
                "column_names": "delta",
                "method": "diff",
                "source_columns": ["a", "b"],
            },
            "",
        )
        joined = "\n".join(lines)
        assert "pl.col('a') - pl.col('b')" in joined

    def test_uuid_seeded_on_survey_name(self):
        lines = _py_add_column(
            {"column_names": "uid", "method": "uuid"}, "", seed="Baseline Survey"
        )
        joined = "\n".join(lines)
        assert "'Baseline Survey'" in joined
        assert "hashlib" in joined

    def test_random(self):
        lines = _py_add_column({"column_names": "r", "method": "random"}, "")
        joined = "\n".join(lines)
        assert "random.random()" in joined

    def test_unknown_method_returns_note(self):
        lines = _py_add_column(
            {"column_names": "x", "method": "levitate", "source_columns": ["a"]}, ""
        )
        assert "could not be translated" in lines[0]


# ---------------------------------------------------------------------------
# generate_prepare_data_script_py
# ---------------------------------------------------------------------------


class TestGeneratePrepareDataScriptPy:
    def test_empty_log_returns_valid_script(self):
        script = generate_prepare_data_script_py(pl.DataFrame(), "P", "S", "1.0.0")
        ast.parse(script)
        assert "No preparation steps recorded" in script

    def test_full_log_parses_and_contains_steps(self):
        prep_log = pl.DataFrame(
            {
                "action": [
                    "remove column(s)",
                    "remove row(s)",
                    "transform column(s)",
                    "add new column",
                    "transform column(s)",
                ],
                "description": [
                    "drop junk",
                    "drop old",
                    "trim name",
                    "add total",
                    "one-hot cat",
                ],
                "prep_args": [
                    json.dumps({"source_columns": ["junk"]}),
                    json.dumps(
                        {
                            "method": "by condition",
                            "condition": "value is greater than",
                            "source_columns": ["age"],
                            "value": [65],
                        }
                    ),
                    json.dumps({"source_columns": ["name"], "method": "trim"}),
                    json.dumps(
                        {
                            "column_names": "total",
                            "method": "sum",
                            "source_columns": ["a", "b"],
                        }
                    ),
                    json.dumps({"source_columns": ["cat"], "method": "get dummies"}),
                ],
                "action_index": [0, 1, 2, 3, 4],
            }
        )
        script = generate_prepare_data_script_py(prep_log, "P", "S", "1.0.0")
        ast.parse(script)
        assert "df = df.drop(['junk'])" in script
        assert "to_dummies(columns=['cat'])" in script

    def test_datetime_helper_only_included_when_needed(self):
        no_date_log = pl.DataFrame(
            {
                "action": ["transform column(s)"],
                "description": ["trim"],
                "prep_args": [
                    json.dumps({"source_columns": ["name"], "method": "trim"})
                ],
                "action_index": [0],
            }
        )
        script = generate_prepare_data_script_py(no_date_log, "P", "S", "1.0.0")
        assert "_parse_flexible_datetime" not in script

        date_log = pl.DataFrame(
            {
                "action": ["transform column(s)"],
                "description": ["parse date"],
                "prep_args": [
                    json.dumps({"source_columns": ["dob"], "method": "string to date"})
                ],
                "action_index": [0],
            }
        )
        script_with_date = generate_prepare_data_script_py(date_log, "P", "S", "1.0.0")
        ast.parse(script_with_date)
        assert "def _parse_flexible_datetime(" in script_with_date

    def test_unknown_action_emits_note(self):
        prep_log = pl.DataFrame(
            {
                "action": ["levitate row(s)"],
                "description": ["???"],
                "prep_args": [json.dumps({})],
                "action_index": [0],
            }
        )
        script = generate_prepare_data_script_py(prep_log, "P", "S", "1.0.0")
        ast.parse(script)
        assert "NOTE: unknown action" in script
