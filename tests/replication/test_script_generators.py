"""Tests for Stata script generators (corrections, master, import)."""

from __future__ import annotations

import polars as pl
import pytest

from datasure.replication.script_generators import (
    SCRIPT_EXT,
    _emit_stata,
    _escape,
    _header,
    _is_numeric,
    generate_corrections_script,
    generate_import_script,
    generate_master_script,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------


def test_script_ext():
    assert SCRIPT_EXT == "do"


# ---------------------------------------------------------------------------
# _escape
# ---------------------------------------------------------------------------


class TestEscape:
    def test_no_quotes(self):
        assert _escape("hello") == "hello"

    def test_single_double_quote(self):
        assert _escape('say "hi"') == 'say ""hi""'

    def test_empty_string(self):
        assert _escape("") == ""


# ---------------------------------------------------------------------------
# _is_numeric
# ---------------------------------------------------------------------------


class TestIsNumeric:
    def test_integer(self):
        assert _is_numeric("42") is True

    def test_float(self):
        assert _is_numeric("3.14") is True

    def test_negative(self):
        assert _is_numeric("-1") is True

    def test_alpha(self):
        assert _is_numeric("abc") is False

    def test_empty(self):
        assert _is_numeric("") is False

    def test_none(self):
        assert _is_numeric(None) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# _header
# ---------------------------------------------------------------------------


class TestHeader:
    def test_contains_title(self):
        h = _header("My Title", "Proj", "Survey", "1.0.0")
        assert "My Title" in h

    def test_contains_project(self):
        h = _header("T", "My Project", "S", "1.0.0")
        assert "My Project" in h

    def test_contains_survey(self):
        h = _header("T", "P", "My Survey", "1.0.0")
        assert "My Survey" in h

    def test_contains_datasure_version(self):
        h = _header("T", "P", "S", "0.9.9")
        assert "DataSure 0.9.9" in h

    def test_starts_with_stata_comment(self):
        h = _header("T", "P", "S", "1.0")
        assert h.startswith("*")


# ---------------------------------------------------------------------------
# _emit_stata
# ---------------------------------------------------------------------------


class TestEmitStata:
    def test_modify_numeric_value(self):
        lines = _emit_stata("modify value", "KEY", "k001", "age", "25", "typo")
        assert any("replace age = 25" in line for line in lines)
        assert any('KEY == "k001"' in line for line in lines)

    def test_modify_string_value(self):
        lines = _emit_stata("modify value", "KEY", "k001", "name", "Alice", "fix")
        assert any('replace name = "Alice"' in line for line in lines)

    def test_modify_value_with_quoted_string_in_value(self):
        lines = _emit_stata("modify value", "KEY", "k1", "note", 'say "hi"', "fix")
        # Value should be escaped
        assert any('""hi""' in line for line in lines)

    def test_remove_value(self):
        lines = _emit_stata("remove value", "KEY", "k002", "score", None, "")
        assert any("replace score = ." in line for line in lines)

    def test_remove_row(self):
        lines = _emit_stata("remove row", "KEY", "k003", None, None, "duplicate")
        assert any("drop if KEY" in line for line in lines)

    def test_unknown_action_returns_empty(self):
        lines = _emit_stata("unknown action", "KEY", "k004", "col", "val", "")
        assert lines == []

    def test_comment_includes_reason(self):
        lines = _emit_stata("remove row", "KEY", "k005", None, None, "test reason")
        assert any("test reason" in line for line in lines)

    def test_key_with_double_quote_escaped(self):
        lines = _emit_stata("remove row", "KEY", 'k"x', None, None, "")
        assert any('""x"' in line or '""' in line for line in lines)


# ---------------------------------------------------------------------------
# generate_corrections_script
# ---------------------------------------------------------------------------


class TestGenerateCorrectionsScript:
    def test_empty_log_returns_no_corrections_message(self):
        log = pl.DataFrame(schema={"action": pl.String, "KEY": pl.String})
        script = generate_corrections_script(log, "key", "Proj", "Survey", "1.0")
        assert "No corrections recorded" in script

    def test_empty_log_has_header(self):
        log = pl.DataFrame(schema={"action": pl.String, "KEY": pl.String})
        script = generate_corrections_script(log, "key", "Proj", "Survey", "1.0")
        assert "Corrections Script" in script

    def test_modify_value_row(self):
        log = pl.DataFrame(
            {
                "action": ["modify value"],
                "KEY": ["k001"],
                "column": ["age"],
                "new_value": ["30"],
                "reason": ["typo"],
                "ID": ["1"],
                "date": ["2024-01-01"],
                "current_value": ["25"],
            }
        )
        script = generate_corrections_script(log, "KEY", "P", "S", "0.1")
        assert "replace age = 30" in script
        assert 'KEY == "k001"' in script

    def test_remove_row_action(self):
        log = pl.DataFrame(
            {
                "action": ["remove row"],
                "KEY": ["k002"],
                "column": [None],
                "new_value": [None],
                "reason": ["duplicate"],
                "ID": ["2"],
                "date": ["2024-01-01"],
                "current_value": [None],
            }
        )
        script = generate_corrections_script(log, "KEY", "P", "S", "0.1")
        assert "drop if KEY" in script

    def test_returns_string(self):
        log = pl.DataFrame(schema={"action": pl.String, "KEY": pl.String})
        result = generate_corrections_script(log, "key", "P", "S", "1.0")
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# generate_master_script
# ---------------------------------------------------------------------------


class TestGenerateMasterScript:
    @pytest.fixture()
    def script(self):
        return generate_master_script("My Project", "My Survey", "1.0.0")

    def test_returns_string(self, script):
        assert isinstance(script, str)

    def test_ends_with_newline(self, script):
        assert script.endswith("\n")

    def test_contains_global_root(self, script):
        assert "global root" in script

    def test_contains_import_step(self, script):
        assert "import_data.do" in script

    def test_contains_prepare_step(self, script):
        assert "prepare_data.do" in script

    def test_contains_corrections_step(self, script):
        assert "corrections.do" in script

    def test_contains_ipacodebook(self, script):
        assert "ipacodebook" in script

    def test_safe_project_name_used(self, script):
        assert "my_project" in script

    def test_safe_survey_name_used(self, script):
        assert "my_survey" in script

    def test_header_present(self, script):
        assert "Master Replication Script" in script


# ---------------------------------------------------------------------------
# generate_import_script
# ---------------------------------------------------------------------------


class TestGenerateImportScript:
    @pytest.fixture()
    def script(self):
        return generate_import_script("My Project", "My Survey", "1.0.0")

    def test_returns_string(self, script):
        assert isinstance(script, str)

    def test_ends_with_newline(self, script):
        assert script.endswith("\n")

    def test_contains_import_delimited(self, script):
        assert "import delimited" in script

    def test_contains_safe_survey_csv(self, script):
        assert "my_survey_raw.csv" in script

    def test_contains_safe_survey_dta(self, script):
        assert "my_survey_raw.dta" in script

    def test_contains_save_command(self, script):
        assert "save" in script

    def test_header_present(self, script):
        assert "Import Script" in script
