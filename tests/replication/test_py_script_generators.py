"""Tests for Python script generators (corrections, master, import)."""

from __future__ import annotations

import ast

import polars as pl
import pytest

from datasure.replication.py_script_generators import (
    SCRIPT_EXT_PY,
    _emit_py,
    _py_lit,
    generate_corrections_script_py,
    generate_import_script_py,
    generate_master_script_py,
)


def test_script_ext():
    assert SCRIPT_EXT_PY == "py"


# ---------------------------------------------------------------------------
# _py_lit
# ---------------------------------------------------------------------------


class TestPyLit:
    def test_none_returns_none_literal(self):
        assert _py_lit(None) == "None"

    def test_integer_string(self):
        assert _py_lit("42") == "42"

    def test_float_string(self):
        assert _py_lit("3.14") == "3.14"

    def test_non_numeric_string_is_quoted(self):
        assert _py_lit("hello") == "'hello'"

    def test_negative_integer_string(self):
        assert _py_lit("-5") == "-5"


# ---------------------------------------------------------------------------
# _emit_py
# ---------------------------------------------------------------------------


class TestEmitPy:
    def test_modify_value(self):
        lines = _emit_py("modify value", "key", "k1", "age", "26", "typo")
        joined = "\n".join(lines)
        assert "pl.when(pl.col('key') == 'k1')" in joined
        assert "pl.lit(26)" in joined
        assert "alias('age')" in joined

    def test_remove_value(self):
        lines = _emit_py("remove value", "key", "k1", "age", None, "bad data")
        joined = "\n".join(lines)
        assert ".then(None)" in joined

    def test_remove_row(self):
        lines = _emit_py("remove row", "key", "k1", None, None, "duplicate")
        joined = "\n".join(lines)
        assert "df = df.filter(pl.col('key') != 'k1')" in joined

    def test_unknown_action_returns_empty(self):
        assert _emit_py("unknown action", "key", "k1", None, None, "") == []

    def test_modify_value_without_new_value_returns_empty(self):
        assert _emit_py("modify value", "key", "k1", "age", None, "") == []


# ---------------------------------------------------------------------------
# generate_import_script_py
# ---------------------------------------------------------------------------


class TestGenerateImportScriptPy:
    @pytest.fixture()
    def script(self):
        return generate_import_script_py("Test Project", "Baseline Survey", "1.0.0")

    def test_returns_string(self, script):
        assert isinstance(script, str)

    def test_parses_as_valid_python(self, script):
        ast.parse(script)

    def test_has_pep723_header(self, script):
        assert "# /// script" in script
        assert "dependencies = [" in script
        assert '"polars"' in script

    def test_uses_safe_survey_filename(self, script):
        assert "baseline_survey_raw.csv" in script
        assert "baseline_survey_raw.parquet" in script

    def test_preserves_schema_inference(self, script):
        # Must NOT force all-string columns — downstream prep/correction
        # steps assume the real numeric/date dtypes DataSure infers on import.
        assert "infer_schema_length=0" not in script
        assert "infer_schema_length=10000" in script


# ---------------------------------------------------------------------------
# generate_corrections_script_py
# ---------------------------------------------------------------------------


class TestGenerateCorrectionsScriptPy:
    def test_no_key_col_is_noop(self):
        script = generate_corrections_script_py(pl.DataFrame(), "", "P", "S", "1.0.0")
        ast.parse(script)
        assert "no-op" in script

    def test_empty_log_returns_valid_script(self):
        script = generate_corrections_script_py(
            pl.DataFrame(), "key", "P", "S", "1.0.0"
        )
        ast.parse(script)
        assert "No corrections recorded" in script

    def test_corrections_translated(self):
        log = pl.DataFrame(
            {
                "action": ["modify value", "remove row"],
                "KEY": ["k1", "k2"],
                "column": ["age", None],
                "new_value": ["26", None],
                "reason": ["typo", "duplicate"],
            }
        )
        script = generate_corrections_script_py(log, "key", "P", "S", "1.0.0")
        ast.parse(script)
        assert "pl.when(pl.col('key') == 'k1')" in script
        assert "df = df.filter(pl.col('key') != 'k2')" in script

    def test_writes_corrected_parquet(self):
        script = generate_corrections_script_py(
            pl.DataFrame(), "key", "P", "S", "1.0.0"
        )
        assert "_corrected.parquet" in script


# ---------------------------------------------------------------------------
# generate_master_script_py
# ---------------------------------------------------------------------------


class TestGenerateMasterScriptPy:
    @pytest.fixture()
    def script(self):
        return generate_master_script_py("Test Project", "Baseline Survey", "1.0.0")

    def test_returns_string(self, script):
        assert isinstance(script, str)

    def test_parses_as_valid_python(self, script):
        ast.parse(script)

    def test_runs_steps_in_order(self, script):
        steps_block = script[script.index("STEPS = [") :]
        idx_import = steps_block.index("2_import_data.py")
        idx_prepare = steps_block.index("3_prepare_data.py")
        idx_corrections = steps_block.index("4_corrections.py")
        assert idx_import < idx_prepare < idx_corrections

    def test_no_install_packages_step(self, script):
        assert "install_packages" not in script
