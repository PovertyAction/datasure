"""Tests for the SurveyCTO import do-file generator."""

from __future__ import annotations

import pytest

from datasure.replication.scto_import_generator import (
    _build_choices_map,
    _chunk_names,
    _clean_label,
    _emit_locals,
    _find_label_col,
    _is_numeric_str,
    _parse_form,
    generate_scto_import_script,
)

# ---------------------------------------------------------------------------
# _clean_label
# ---------------------------------------------------------------------------


class TestCleanLabel:
    def test_strips_simple_html_tags(self):
        assert _clean_label("<b>Bold text</b>") == "Bold text"

    def test_strips_span_with_attributes(self):
        assert _clean_label('<span style="color:red">Red</span>') == "Red"

    def test_strips_self_closing_tags(self):
        assert _clean_label("Line 1<br/>Line 2") == "Line 1Line 2"

    def test_escapes_dollar_sign(self):
        assert _clean_label("Enter ${name} here") == r"Enter \${name} here"

    def test_replaces_double_quotes_with_single(self):
        assert _clean_label('Say "hello"') == "Say 'hello'"

    def test_strips_html_then_escapes_dollar(self):
        result = _clean_label("<b>Enter ${var}</b>")
        assert "<b>" not in result
        assert r"\$" in result

    def test_empty_string(self):
        assert _clean_label("") == ""

    def test_plain_text_unchanged(self):
        assert _clean_label("Plain label") == "Plain label"

    def test_strips_leading_trailing_whitespace_after_html(self):
        result = _clean_label("  <b> text </b>  ")
        assert result == "text"

    def test_collapses_newlines_to_single_space(self):
        result = _clean_label("Line one\n\nLine two")
        assert result == "Line one Line two"

    def test_collapses_multiline_label_like_surveycto(self):
        label = "Nigeria ORS Zinc Project  \n \n COMMUNITY ENTRY FORM \n \n July 2024"
        result = _clean_label(label)
        assert result == "Nigeria ORS Zinc Project COMMUNITY ENTRY FORM July 2024"

    def test_newlines_after_html_removal_collapsed(self):
        result = _clean_label("Part one<br/>\n<br/>\nPart two")
        assert result == "Part one Part two"

    def test_tabs_collapsed(self):
        result = _clean_label("word\t\tanother")
        assert result == "word another"


# ---------------------------------------------------------------------------
# _find_label_col
# ---------------------------------------------------------------------------


class TestFindLabelCol:
    def test_prefers_english_label(self):
        assert _find_label_col(["type", "name", "label::English"]) == "label::English"

    def test_prefers_english_en_over_generic(self):
        assert (
            _find_label_col(["label::English (en)", "label"]) == "label::English (en)"
        )

    def test_falls_back_to_plain_label(self):
        assert _find_label_col(["type", "name", "label"]) == "label"

    def test_falls_back_to_any_label_prefix(self):
        assert _find_label_col(["type", "name", "label::French"]) == "label::French"

    def test_returns_empty_when_no_label_col(self):
        assert _find_label_col(["type", "name", "hint"]) == ""

    def test_empty_headers(self):
        assert _find_label_col([]) == ""


# ---------------------------------------------------------------------------
# _chunk_names
# ---------------------------------------------------------------------------


class TestChunkNames:
    def test_empty_list_returns_empty(self):
        assert _chunk_names([]) == []

    def test_single_name_one_chunk(self):
        assert _chunk_names(["var1"]) == [["var1"]]

    def test_names_fitting_in_one_chunk(self):
        names = ["a", "b", "c"]
        assert _chunk_names(names, max_len=10) == [["a", "b", "c"]]

    def test_names_split_across_chunks(self):
        # "longname" = 8 chars; with space separator total > 10 would split
        names = ["longname1", "longname2"]
        chunks = _chunk_names(names, max_len=10)
        assert len(chunks) == 2
        assert chunks[0] == ["longname1"]
        assert chunks[1] == ["longname2"]

    def test_all_names_in_one_chunk_exactly(self):
        # "ab cd" = 5 chars fits in max_len=5
        names = ["ab", "cd"]
        chunks = _chunk_names(names, max_len=5)
        assert chunks == [["ab", "cd"]]

    def test_many_names_chunked_correctly(self):
        names = [f"v{i}" for i in range(50)]
        chunks = _chunk_names(names, max_len=20)
        # Each chunk must fit within max_len
        for chunk in chunks:
            joined = " ".join(chunk)
            assert len(joined) <= 20
        # All names appear exactly once
        assert sorted(n for chunk in chunks for n in chunk) == sorted(names)


# ---------------------------------------------------------------------------
# _emit_locals
# ---------------------------------------------------------------------------


class TestEmitLocals:
    def test_empty_chunks_emits_empty_local(self):
        result = _emit_locals("note_fields", [])
        assert result == ['local note_fields1 ""']

    def test_single_chunk(self):
        result = _emit_locals("text_fields", [["var1", "var2"]])
        assert result == ['local text_fields1 "var1 var2"']

    def test_multiple_chunks_numbered(self):
        result = _emit_locals("date_fields", [["d1", "d2"], ["d3"]])
        assert result == [
            'local date_fields1 "d1 d2"',
            'local date_fields2 "d3"',
        ]


# ---------------------------------------------------------------------------
# _is_numeric_str
# ---------------------------------------------------------------------------


class TestIsNumericStr:
    def test_integer_string(self):
        assert _is_numeric_str("1") is True

    def test_float_string(self):
        assert _is_numeric_str("3.14") is True

    def test_negative(self):
        assert _is_numeric_str("-5") is True

    def test_plain_text(self):
        assert _is_numeric_str("abc") is False

    def test_empty_string(self):
        assert _is_numeric_str("") is False

    def test_none(self):
        assert _is_numeric_str(None) is False  # type: ignore[arg-type]

    def test_mixed(self):
        assert _is_numeric_str("1a") is False


# ---------------------------------------------------------------------------
# _build_choices_map
# ---------------------------------------------------------------------------


class TestBuildChoicesMap:
    def _make_choices(self):
        headers = ["list_name", "name", "label::English"]
        data = [
            ["yn", "1", "Yes"],
            ["yn", "0", "No"],
            ["region", "1", "North"],
            ["region", "2", "South"],
        ]
        return headers, data

    def test_builds_correct_map(self):
        hdr, data = self._make_choices()
        result = _build_choices_map(hdr, data)
        assert "yn" in result
        assert ("1", "Yes") in result["yn"]
        assert ("0", "No") in result["yn"]

    def test_multiple_lists(self):
        hdr, data = self._make_choices()
        result = _build_choices_map(hdr, data)
        assert "region" in result
        assert len(result["region"]) == 2

    def test_empty_headers(self):
        assert _build_choices_map([], []) == {}

    def test_missing_list_name_col(self):
        hdr = ["name", "label"]
        data = [["yes", "Yes"]]
        assert _build_choices_map(hdr, data) == {}

    def test_skips_rows_with_empty_list_name(self):
        hdr = ["list_name", "name", "label"]
        data = [["", "1", "One"], ["valid", "1", "One"]]
        result = _build_choices_map(hdr, data)
        assert "" not in result
        assert "valid" in result


# ---------------------------------------------------------------------------
# _parse_form
# ---------------------------------------------------------------------------


class TestParseForm:
    def test_empty_form_def(self):
        f_hdr, f_data, c_hdr, c_data = _parse_form({})
        assert f_hdr == []
        assert f_data == []
        assert c_hdr == []
        assert c_data == []

    def test_extracts_headers_and_data(self):
        form_def = {
            "fieldsRowsAndColumns": [
                ["type", "name", "label"],
                ["text", "q1", "Question 1"],
            ],
            "choicesRowsAndColumns": [
                ["list_name", "name", "label"],
                ["yn", "1", "Yes"],
            ],
        }
        f_hdr, f_data, c_hdr, c_data = _parse_form(form_def)
        assert f_hdr == ["type", "name", "label"]
        assert f_data == [["text", "q1", "Question 1"]]
        assert c_hdr == ["list_name", "name", "label"]
        assert c_data == [["yn", "1", "Yes"]]

    def test_only_header_row_gives_empty_data(self):
        form_def = {
            "fieldsRowsAndColumns": [["type", "name", "label"]],
            "choicesRowsAndColumns": [],
        }
        f_hdr, f_data, _, _ = _parse_form(form_def)
        assert f_hdr == ["type", "name", "label"]
        assert f_data == []


# ---------------------------------------------------------------------------
# generate_scto_import_script  (integration)
# ---------------------------------------------------------------------------

_SAMPLE_FORM_DEF = {
    "fieldsRowsAndColumns": [
        ["type", "name", "label::English", "disabled"],
        ["text", "respondent_name", "Respondent name", ""],
        ["integer", "age", "Age of respondent", ""],
        ["date", "dob", "Date of birth", ""],
        ["datetime", "interview_time", "Interview date/time", ""],
        ["select_one yn", "consent", "Do you consent?", ""],
        ["select_multiple region", "regions", "Regions covered", ""],
        ["note", "section_note", "Section A", ""],
        ["begin group", "grp1", "Group 1", ""],
        ["end group", "", "", ""],
        ["text", "skipped_field", "Disabled field", "yes"],
    ],
    "choicesRowsAndColumns": [
        ["list_name", "name", "label::English"],
        ["yn", "1", "Yes"],
        ["yn", "0", "No"],
        ["region", "north", "North"],
        ["region", "south", "South"],
    ],
}


class TestGenerateSCTOImportScript:
    @pytest.fixture()
    def script(self):
        return generate_scto_import_script(
            form_def=_SAMPLE_FORM_DEF,
            form_id="test_form_001",
            form_title="Test Survey",
            survey_name="test_survey",
            datasure_version="0.1.0",
        )

    def test_returns_string(self, script):
        assert isinstance(script, str)

    def test_contains_header_comment(self, script):
        assert "import_data.do" in script
        assert "Test Survey" in script
        assert "test_form_001" in script

    def test_contains_csv_and_dta_file_names(self, script):
        assert "test_survey_raw.csv" in script
        assert "test_survey_raw.dta" in script

    def test_contains_insheet_command(self, script):
        assert "insheet using" in script

    def test_drops_note_fields(self, script):
        assert "note_fields" in script
        assert "section_note" in script  # appears in the local declaration

    def test_note_fields_have_no_label_variable_statement(self, script):
        # note fields are absent from the data; no label variable statement should
        # be emitted for them
        assert "label variable section_note" not in script

    def test_text_fields_included(self, script):
        assert "text_fields" in script
        assert "respondent_name" in script

    def test_date_fields_included(self, script):
        assert "date_fields" in script
        assert "dob" in script

    def test_datetime_fields_included(self, script):
        assert "datetime_fields" in script
        assert "interview_time" in script

    def test_system_datetime_fields_included(self, script):
        assert "submissiondate" in script
        assert "starttime" in script
        assert "endtime" in script

    def test_skip_types_not_in_field_lists(self, script):
        # begin group / end group should not appear as field names
        assert "begin group" not in script
        assert "end group" not in script

    def test_disabled_fields_excluded(self, script):
        assert "skipped_field" not in script

    def test_label_variable_for_text_field(self, script):
        assert 'cap label variable respondent_name "Respondent name"' in script

    def test_label_variable_for_integer_field(self, script):
        assert 'cap label variable age "Age of respondent"' in script

    def test_numeric_value_labels_applied(self, script):
        # yn choices 1/0 are numeric → label define + cap label values
        assert "label define" in script
        assert "cap label values consent" in script

    def test_non_numeric_choices_no_value_labels(self, script):
        # region choices (north/south) are non-numeric → no value labels for regions
        assert "label values regions" not in script

    def test_key_consolidation_present(self, script):
        assert "replace key=instanceid" in script
        assert "drop instanceid" in script

    def test_save_command_present(self, script):
        assert 'save "`dtafile\'"' in script

    def test_overwrite_old_data_local(self, script):
        assert "local overwrite_old_data 0" in script

    def test_no_html_tags_in_output(self, script):
        import re

        assert not re.search(r"<[^>]+>", script)

    def test_empty_form_def_does_not_crash(self):
        result = generate_scto_import_script(
            form_def={},
            form_id="empty_form",
            form_title="Empty Form",
            survey_name="empty",
            datasure_version="0.1.0",
        )
        assert isinstance(result, str)
        assert "insheet using" in result

    def test_datasure_version_in_header(self, script):
        assert "DataSure 0.1.0" in script

    def test_script_ends_with_newline(self, script):
        assert script.endswith("\n")

    def test_html_labels_stripped(self):
        form_def = {
            "fieldsRowsAndColumns": [
                ["type", "name", "label::English", "disabled"],
                ["text", "q1", "<b>Bold</b> question", ""],
            ],
            "choicesRowsAndColumns": [],
        }
        script = generate_scto_import_script(
            form_def=form_def,
            form_id="f1",
            form_title="T",
            survey_name="s",
            datasure_version="0.0.1",
        )
        assert "<b>" not in script
        assert "Bold question" in script

    def test_dollar_sign_escaped_in_labels(self):
        form_def = {
            "fieldsRowsAndColumns": [
                ["type", "name", "label::English", "disabled"],
                ["text", "q1", "Enter ${name} here", ""],
            ],
            "choicesRowsAndColumns": [],
        }
        script = generate_scto_import_script(
            form_def=form_def,
            form_id="f1",
            form_title="T",
            survey_name="s",
            datasure_version="0.0.1",
        )
        assert r"\${name}" in script
