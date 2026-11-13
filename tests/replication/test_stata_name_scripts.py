"""Do-files use the Stata names that ``stata_name_map`` gives columns (#449)."""

from __future__ import annotations

import polars as pl

from datasure.processing.column_names import stata_name_map
from datasure.replication.script_generators import (
    generate_corrections_script,
    generate_import_script,
)
from datasure.replication.scto_import_generator import generate_scto_import_script

_RAW_COLUMNS = ["KEY", "visit date", "2nd_visit", "âge", "in", "village"]
_NAME_MAP = stata_name_map(_RAW_COLUMNS)


def _lines(script: str) -> list[str]:
    return [line.strip() for line in script.splitlines()]


class TestImportScriptRenamesByPosition:
    """Columns Stata can't use are renamed once, by position, right after import."""

    def test_names_that_need_no_change_build_the_same_script(self):
        before = generate_import_script("P", "S", "1.0")
        after = generate_import_script(
            "P", "S", "1.0", columns=["KEY", "age"], name_map={}
        )
        assert after == before

    def test_mapped_columns_are_renamed_by_position_and_labelled(self):
        lines = _lines(
            generate_import_script(
                "P", "S", "1.0", columns=_RAW_COLUMNS, name_map=_NAME_MAP
            )
        )
        imported = next(i for i, ln in enumerate(lines) if "import delimited" in ln)
        unab = lines.index("unab ds_vars : _all")
        assert unab > imported
        rename = lines[unab + 1]
        assert rename == (
            "rename (`:word 2 of `ds_vars'' `:word 3 of `ds_vars'' "
            "`:word 4 of `ds_vars'' `:word 5 of `ds_vars'') "
            "(visit_date _2nd_visit age in_)"
        )
        assert lines[unab + 2 : unab + 6] == [
            'label variable visit_date "visit date"',
            'label variable _2nd_visit "2nd_visit"',
            'label variable age "âge"',
            'label variable in_ "in"',
        ]
        assert lines.index(next(ln for ln in lines if ln.startswith("save"))) > unab


_FORM = {
    "fieldsRowsAndColumns": [
        ["type", "name", "label::English", "disabled"],
        ["date", "visit date", "Date of visit", ""],
        ["text", "village", "Village", ""],
    ],
    "choicesRowsAndColumns": [],
}


class TestSurveyCTOImportScript:
    def _script(self, columns=None, name_map=None) -> str:
        return generate_scto_import_script(
            form_def=_FORM,
            form_id="f",
            form_title="T",
            survey_name="s",
            datasure_version="1.0",
            columns=columns or [],
            name_map=name_map or {},
        )

    def test_names_that_need_no_change_build_the_same_script(self):
        assert self._script(["KEY", "village"], {}) == generate_scto_import_script(
            form_def=_FORM,
            form_id="f",
            form_title="T",
            survey_name="s",
            datasure_version="1.0",
        )

    def test_mapped_columns_are_renamed_before_row_order_is_recorded(self):
        lines = _lines(self._script(_RAW_COLUMNS, _NAME_MAP))
        insheet = next(i for i, ln in enumerate(lines) if ln.startswith("insheet"))
        unab = lines.index("unab ds_vars : _all")
        assert insheet < unab < lines.index("gen long _ds_row = _n")
        assert "(visit_date _2nd_visit age in_)" in lines[unab + 1]

    def test_field_lists_and_labels_use_the_stata_name(self):
        script = self._script(_RAW_COLUMNS, _NAME_MAP)
        assert 'local date_fields1 "visit_date"' in script
        assert "label variable visit date" not in script
        assert 'cap note visit_date: "Date of visit"' in script
        # The DataSure name stays the variable label.
        assert "cap label variable visit_date" not in script
        assert 'label variable visit_date "visit date"' in script


class TestCorrectionsScriptUsesStataNames:
    def _log(self, column: str) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "action": ["modify value"],
                "KEY": ["k1"],
                "column": [column],
                "new_value": ["3"],
                "reason": [""],
            }
        )

    def test_mapped_column_and_key_use_their_stata_names(self):
        script = generate_corrections_script(
            self._log("visit date"),
            "key id",
            "P",
            "S",
            "1.0",
            name_map={"visit date": "visit_date", "key id": "key_id"},
        )
        assert 'replace visit_date = 3 if key_id == "k1"' in script

    def test_without_a_map_names_are_unchanged(self):
        script = generate_corrections_script(self._log("age"), "KEY", "P", "S", "1.0")
        assert 'replace age = 3 if KEY == "k1"' in script
