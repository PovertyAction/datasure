"""Tests for Python script generators (corrections, master)."""

from __future__ import annotations

import ast

import polars as pl
import pytest

from datasure.processing.pii import empty_flags
from datasure.replication.py_script_generators import (
    SCRIPT_EXT_PY,
    _emit_py,
    _py_lit,
    generate_corrections_script_py,
    generate_deidentify_script_py,
    generate_master_script_py,
)


def _pii_flags(rows: list[dict]) -> pl.DataFrame:
    base = {
        "column": "",
        "source": "name_match",
        "entity_type": None,
        "hit_rate": 1.0,
        "sample_matches": "",
        "decision": "undecided",
        "mask_label": "*****",
        "scanned_at": "2026-01-01T00:00:00",
    }
    return pl.DataFrame([{**base, **row} for row in rows], schema=empty_flags().schema)


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
# generate_deidentify_script_py
# ---------------------------------------------------------------------------


class TestGenerateDeidentifyScriptPy:
    def _script(self, flags):
        return generate_deidentify_script_py(
            flags, "Test Project", "Baseline Survey", "1.0.0"
        )

    def test_parses_as_valid_python(self):
        flags = _pii_flags(
            [{"column": "name", "decision": "mask", "mask_label": "[PERSON]"}]
        )
        ast.parse(self._script(flags))

    def test_decisions_embedded(self):
        flags = _pii_flags(
            [
                {"column": "name", "decision": "mask", "mask_label": "[PERSON]"},
                {"column": "latitude", "decision": "drop"},
            ]
        )
        script = self._script(flags)
        assert "('name', 'mask', '[PERSON]')" in script
        assert "('latitude', 'drop', '*****')" in script

    def test_undecided_treated_as_mask(self):
        flags = _pii_flags([{"column": "notes", "decision": "undecided"}])
        script = self._script(flags)
        assert "('notes', 'mask', '*****')" in script

    def test_kept_columns_excluded(self):
        flags = _pii_flags([{"column": "age", "decision": "keep"}])
        script = self._script(flags)
        assert "'age'" not in script

    def test_empty_flags_yields_empty_decisions(self):
        script = self._script(empty_flags())
        ast.parse(script)
        assert "DECISIONS = []" in script

    def test_targets_all_bundled_datasets(self):
        script = self._script(empty_flags())
        for name in (
            "baseline_survey_raw.parquet",
            "baseline_survey_prepped.parquet",
            "baseline_survey_corrected.parquet",
        ):
            assert name in script

    def test_prints_indirect_identifier_warning(self):
        script = self._script(empty_flags())
        assert "not anonymization" in script

    def test_hash_decision_embeds_salt_and_helper(self):
        flags = _pii_flags(
            [{"column": "name", "decision": "hash", "entity_type": "PERSON"}]
        )
        script = generate_deidentify_script_py(
            flags, "P", "Baseline Survey", "1.0.0", salt="secret-salt"
        )
        ast.parse(script)
        assert "SALT = 'secret-salt'" in script
        assert "def hash_token(" in script
        assert "('name', 'hash', 'PERSON')" in script

    def test_hash_without_salt_falls_back_to_mask(self):
        flags = _pii_flags(
            [
                {
                    "column": "name",
                    "decision": "hash",
                    "mask_label": "[PERSON]",
                }
            ]
        )
        script = generate_deidentify_script_py(flags, "P", "S", "1.0.0", salt=None)
        ast.parse(script)
        assert "('name', 'mask', '[PERSON]')" in script
        assert "SALT =" not in script

    def test_code_decision_embeds_prefix(self):
        flags = _pii_flags([{"column": "village_name", "decision": "code"}])
        script = self._script(flags)
        ast.parse(script)
        assert "('village_name', 'code', 'VILLAGE_NAME')" in script
        assert "code_maps" in script


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
        idx_prepare = steps_block.index("3_prepare_data.py")
        idx_corrections = steps_block.index("4_corrections.py")
        assert idx_prepare < idx_corrections

    def test_no_import_step(self, script):
        # The raw dataset is already bundled as a correctly-typed Parquet
        # file, so there's nothing for a Python import step to do.
        steps_block = script[script.index("STEPS = [") :]
        assert "2_import_data" not in steps_block

    def test_no_install_packages_step(self, script):
        assert "install_packages" not in script

    def test_steps_invoked_via_uv_run(self, script):
        # Each step must go through `uv run` (not the current interpreter)
        # so its own PEP 723 inline dependencies are honored.
        assert '["uv", "run", str(SCRIPTS_DIR / step)]' in script
        assert "sys.executable" not in script

    def test_does_not_import_unused_sys(self, script):
        assert "import sys" not in script
