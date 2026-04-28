"""SurveyCTO-specific Stata import do-file generator.

Generates an import do-file from a SurveyCTO form definition JSON that
mirrors the structure of SurveyCTO's own auto-generated import do-files:
field-type classification, date/datetime conversion, text coercion, and
per-variable labels, notes, and value labels for select fields.
"""

from __future__ import annotations

import re

from datasure.replication.script_generators import _C, _LOG_CLOSE

_HTML_TAG_RE = re.compile(r"<[^>]+>")

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LABEL_VAR_MAX = 80  # Stata label variable character limit
_LOCAL_CHUNK = 160  # Max chars per Stata field-list local

_NOTE_TYPES = {"note"}
_TEXT_TYPES = {"text", "barcode", "acknowledge", "calculate", "caseid", "hidden"}
_DATE_TYPES = {"date"}
_DATETIME_TYPES = {"datetime", "time", "start", "end"}
_SKIP_TYPES = {"begin group", "end group", "begin repeat", "end repeat"}
_SELECT_ONE = "select_one"
_SELECT_MULTI = "select_multiple"

# Always-datetime system fields added regardless of form definition
_SYSTEM_DATETIMES = ["submissiondate", "starttime", "endtime"]

# Maps each XLSForm base type to its classification bucket name.
_TYPE_BUCKET: dict[str, str] = (
    dict.fromkeys(_NOTE_TYPES, "note")
    | dict.fromkeys(_TEXT_TYPES, "text")
    | dict.fromkeys(_DATE_TYPES, "date")
    | dict.fromkeys(_DATETIME_TYPES, "datetime")
)

# ---------------------------------------------------------------------------
# String helpers
# ---------------------------------------------------------------------------


def _find_label_col(headers: list[str]) -> str:
    """Return the primary label column name from the survey/choices headers."""
    for candidate in ("label::English", "label::English (en)", "label"):
        if candidate in headers:
            return candidate
    for h in headers:
        if h.lower().startswith("label"):
            return h
    return ""


_WHITESPACE_RE = re.compile(r"\s+")


def _clean_label(text: str) -> str:
    """Strip HTML tags and escape text for a Stata double-quoted string."""
    text = _HTML_TAG_RE.sub("", text)
    text = _WHITESPACE_RE.sub(" ", text).strip()
    text = text.replace("$", r"\$")
    text = text.replace('"', "'")
    return text


def _truncate(text: str, max_len: int) -> str:
    return text[:max_len] if len(text) > max_len else text


def _is_numeric_str(s: object) -> bool:
    try:
        float(s)
    except (ValueError, TypeError):
        return False
    else:
        return True


# ---------------------------------------------------------------------------
# Form definition parsers
# ---------------------------------------------------------------------------


def _get_col(row: list, headers: list[str], col: str) -> str:
    """Return a cell value from a row, safely."""
    try:
        idx = headers.index(col)
    except ValueError:
        return ""
    return str(row[idx] or "").strip() if idx < len(row) else ""


def _parse_form(form_def: dict) -> tuple[list[str], list[list], list[str], list[list]]:
    fields_rows = form_def.get("fieldsRowsAndColumns", [])
    choices_rows = form_def.get("choicesRowsAndColumns", [])
    f_hdr = [str(h) for h in fields_rows[0]] if fields_rows else []
    f_data = [list(r) for r in fields_rows[1:]] if len(fields_rows) > 1 else []
    c_hdr = [str(h) for h in choices_rows[0]] if choices_rows else []
    c_data = [list(r) for r in choices_rows[1:]] if len(choices_rows) > 1 else []
    return f_hdr, f_data, c_hdr, c_data


def _parse_choice_row(
    row: list, li: int, ni: int, bi: int
) -> tuple[str, str, str] | None:
    """Return ``(list_name, value, label)`` from a choices row, or None if invalid."""
    if len(row) <= max(li, ni):
        return None
    lst = str(row[li] or "").strip()
    val = str(row[ni] or "").strip()
    if not lst or not val:
        return None
    lbl = str(row[bi] or "").strip() if bi >= 0 and len(row) > bi else ""
    return lst, val, lbl


def _build_choices_map(
    c_hdr: list[str], c_data: list[list]
) -> dict[str, list[tuple[str, str]]]:
    """Build ``{list_name: [(value, label), ...]}`` from the choices rows."""
    if not c_hdr or not c_data:
        return {}
    lbl_col = _find_label_col(c_hdr)
    try:
        li = c_hdr.index("list_name")
        ni = c_hdr.index("name")
    except ValueError:
        return {}
    bi = c_hdr.index(lbl_col) if lbl_col in c_hdr else -1
    result: dict[str, list[tuple[str, str]]] = {}
    for row in c_data:
        parsed = _parse_choice_row(row, li, ni, bi)
        if parsed:
            lst, val, lbl = parsed
            result.setdefault(lst, []).append((val, lbl))
    return result


# ---------------------------------------------------------------------------
# Field classification
# ---------------------------------------------------------------------------


def _parse_field_row(
    row: list, f_hdr: list[str], lbl_col: str
) -> tuple[str, str, str, str] | None:
    """Parse one survey row into ``(name, base_type, list_name, label)``.

    Returns None if the row should be skipped (disabled, empty, or a group/repeat).
    """
    name = _get_col(row, f_hdr, "name")
    raw_type = _get_col(row, f_hdr, "type")
    disabled = _get_col(row, f_hdr, "disabled").lower()

    if not name or not raw_type or disabled == "yes":
        return None

    parts = raw_type.split(None, 1)
    base = parts[0].lower()

    if not base or base in _SKIP_TYPES:
        return None

    list_name = parts[1] if len(parts) > 1 else ""
    label = _get_col(row, f_hdr, lbl_col) if lbl_col else ""
    return name, base, list_name, label


def _classify_fields(
    f_hdr: list[str],
    f_data: list[list],
    lbl_col: str,
) -> tuple[list[str], list[str], list[str], list[str], list[tuple[str, str, str, str]]]:
    """Classify form fields by type.

    Returns
    -------
    tuple
        ``(note_fields, text_fields, date_fields, datetime_fields, survey_fields)``
        where *survey_fields* is a list of ``(name, base_type, list_name, label)``
        tuples for every non-skip field.
    """
    buckets: dict[str, list[str]] = {"note": [], "text": [], "date": [], "datetime": []}
    survey_fields: list[tuple[str, str, str, str]] = []

    for row in f_data:
        parsed = _parse_field_row(row, f_hdr, lbl_col)
        if parsed is None:
            continue
        name, base, list_name, label = parsed
        bucket = _TYPE_BUCKET.get(base)
        if bucket:
            buckets[bucket].append(name)
        survey_fields.append((name, base, list_name, label))

    dt = buckets["datetime"]
    dt.extend(sf for sf in _SYSTEM_DATETIMES if sf not in dt)

    return buckets["note"], buckets["text"], buckets["date"], dt, survey_fields


# ---------------------------------------------------------------------------
# Stata field-list locals helpers
# ---------------------------------------------------------------------------


def _chunk_names(names: list[str], max_len: int = _LOCAL_CHUNK) -> list[list[str]]:
    """Split a list of variable names into chunks that fit inside a Stata local."""
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for name in names:
        add = len(name) + (1 if current else 0)
        if current and current_len + add > max_len:
            chunks.append(current)
            current = [name]
            current_len = len(name)
        else:
            current.append(name)
            current_len += add
    if current:
        chunks.append(current)
    return chunks


def _emit_locals(prefix: str, chunks: list[list[str]]) -> list[str]:
    """Emit Stata ``local`` declarations for a chunked list of field names."""
    if not chunks:
        return [f'local {prefix}1 ""']
    return [
        f'local {prefix}{i} "{" ".join(chunk)}"' for i, chunk in enumerate(chunks, 1)
    ]


# ---------------------------------------------------------------------------
# Stata section emitters
# ---------------------------------------------------------------------------


def _emit_preamble(
    form_title: str,
    form_id: str,
    csv_file: str,
    dta_file: str,
    datasure_version: str,
) -> list[str]:
    """Emit the script header, Stata initialization, log open, and file-path locals."""
    return [
        f"{_C} import_data.do",
        f"{_C}",
        f'{_C}    Imports and labels "{form_title}" (ID: {form_id}) data.',
        f"{_C}",
        f'{_C}    Inputs:  "${{raw}}/{csv_file}"',
        f'{_C}    Outputs: "${{raw}}/{dta_file}"',
        f"{_C}",
        f"{_C}    Generated by DataSure {datasure_version}",
        "",
        "* initialize Stata",
        "clear all",
        "set more off",
        "",
        'cap log using "$logdir/2_import_data.log", replace text',
        "",
        "* initialize workflow-specific parameters",
        "*    Set overwrite_old_data to 1 to allow un-approving submissions.",
        "local overwrite_old_data 0",
        "",
        "* initialize form-specific parameters",
        f'local csvfile "${{raw}}/{csv_file}"',
        f'local dtafile "${{raw}}/{dta_file}"',
        "",
    ]


def _emit_type_locals(
    note_chunks: list[list[str]],
    text_chunks: list[list[str]],
    date_chunks: list[list[str]],
    dt_chunks: list[list[str]],
) -> list[str]:
    """Emit Stata local declarations for all field-type lists."""
    lines: list[str] = []
    lines += _emit_locals("note_fields", note_chunks)
    lines += _emit_locals("text_fields", text_chunks)
    lines += _emit_locals("date_fields", date_chunks)
    lines += _emit_locals("datetime_fields", dt_chunks)
    lines.append("")
    return lines


def _emit_drop_note_fields() -> list[str]:
    """Emit the block that drops note fields (absent from API downloads)."""
    return [
        "\t* drop note fields if they exist (API downloads may omit them)",
        "\tforvalues i = 1/100 {",
        '\t\tif "`note_fields`i\'\'" ~= "" {',
        "\t\t\tforeach nfvar in `note_fields`i'' {",
        "\t\t\t\tcap drop `nfvar'",
        "\t\t\t}",
        "\t\t}",
        "\t}",
        "",
    ]


def _emit_format_date_fields() -> list[str]:
    """Emit the block that converts date/datetime columns to Stata date values."""
    return [
        "\t* format date and date/time fields",
        "\tlocal maxyr = year(today()) + 20",
        "\tforvalues i = 1/100 {",
        '\t\tif "`datetime_fields`i\'\'" ~= "" {',
        "\t\t\tforeach dtvarlist in `datetime_fields`i'' {",
        "\t\t\t\tcap unab dtvarlist : `dtvarlist'",
        "\t\t\t\tif _rc==0 {",
        "\t\t\t\t\tforeach dtvar in `dtvarlist' {",
        "\t\t\t\t\t\ttempvar tempdtvar",
        "\t\t\t\t\t\trename `dtvar' `tempdtvar'",
        "\t\t\t\t\t\tgen double `dtvar'=.",
        "\t\t\t\t\t\tcap replace `dtvar'=clock(`tempdtvar',\"MDYhms\",`maxyr')",
        "\t\t\t\t\t\t* automatically try without seconds, just in case",
        "\t\t\t\t\t\tcap replace `dtvar'=clock(`tempdtvar',\"MDYhm\",`maxyr') if `dtvar'==. & `tempdtvar'~=\"\"",
        "\t\t\t\t\t\tformat %tc `dtvar'",
        "\t\t\t\t\t\tdrop `tempdtvar'",
        "\t\t\t\t\t}",
        "\t\t\t\t}",
        "\t\t\t}",
        "\t\t}",
        '\t\tif "`date_fields`i\'\'" ~= "" {',
        "\t\t\tforeach dtvarlist in `date_fields`i'' {",
        "\t\t\t\tcap unab dtvarlist : `dtvarlist'",
        "\t\t\t\tif _rc==0 {",
        "\t\t\t\t\tforeach dtvar in `dtvarlist' {",
        "\t\t\t\t\t\ttempvar tempdtvar",
        "\t\t\t\t\t\trename `dtvar' `tempdtvar'",
        "\t\t\t\t\t\tgen double `dtvar'=.",
        "\t\t\t\t\t\tcap replace `dtvar'=date(`tempdtvar',\"MDY\",`maxyr')",
        "\t\t\t\t\t\tformat %td `dtvar'",
        "\t\t\t\t\t\tdrop `tempdtvar'",
        "\t\t\t\t\t}",
        "\t\t\t\t}",
        "\t\t\t}",
        "\t\t}",
        "\t}",
        "",
    ]


def _emit_coerce_text_fields() -> list[str]:
    """Emit the block that ensures text fields are always stored as strings."""
    return [
        '\t* ensure text fields are always imported as strings ("" for missing)',
        "\ttempvar ismissingvar",
        "\tquietly: gen `ismissingvar'=.",
        "\tforvalues i = 1/100 {",
        '\t\tif "`text_fields`i\'\'" ~= "" {',
        "\t\t\tforeach svarlist in `text_fields`i'' {",
        "\t\t\t\tcap unab svarlist : `svarlist'",
        "\t\t\t\tif _rc==0 {",
        "\t\t\t\t\tforeach stringvar in `svarlist' {",
        "\t\t\t\t\t\tquietly: replace `ismissingvar'=.",
        "\t\t\t\t\t\tquietly: cap replace `ismissingvar'=1 if `stringvar'==.",
        "\t\t\t\t\t\tcap tostring `stringvar', format(%100.0g) replace",
        "\t\t\t\t\t\tcap replace `stringvar'=\"\" if `ismissingvar'==1",
        "\t\t\t\t\t}",
        "\t\t\t\t}",
        "\t\t\t}",
        "\t\t}",
        "\t}",
        "\tquietly: drop `ismissingvar'",
        "",
    ]


def _emit_consolidate_key() -> list[str]:
    """Emit the block that consolidates instanceid into the key variable."""
    return [
        "\t* consolidate unique ID into key variable",
        '\treplace key=instanceid if key==""',
        "\tdrop instanceid",
        "",
    ]


def _emit_system_labels() -> list[str]:
    """Emit variable labels for standard SurveyCTO system fields."""
    return [
        "\t* label standard system variables",
        '\tlabel variable key "Unique submission ID"',
        '\tcap label variable submissiondate "Date/time submitted"',
        '\tcap label variable formdef_version "Form version used on device"',
        '\tcap label variable review_status "Review status"',
        '\tcap label variable review_comments "Comments made during review"',
        '\tcap label variable review_corrections "Corrections made during review"',
        "",
        "\t* label survey variables",
    ]


def _emit_survey_labels(
    survey_fields: list[tuple[str, str, str, str]],
    choices_map: dict[str, list[tuple[str, str]]],
) -> list[str]:
    """Emit per-variable labels, notes, and value labels for all survey fields."""
    lines: list[str] = []
    used_label_sets: set[str] = set()

    for name, base, list_name, label in survey_fields:
        if base in _NOTE_TYPES:
            continue

        esc = _clean_label(label)
        short = _truncate(esc, _LABEL_VAR_MAX)

        lines.append(f'\tcap label variable {name} "{short}"')
        if label:
            lines.append(f'\tcap note {name}: "{esc}"')

        if base in (_SELECT_ONE, _SELECT_MULTI) and list_name in choices_map:
            pairs = choices_map[list_name]
            numeric_pairs = [(v, lb) for v, lb in pairs if _is_numeric_str(v)]
            if numeric_pairs:
                lset = name if name not in used_label_sets else f"{name}_lbl"
                used_label_sets.add(lset)
                define_parts = " ".join(
                    f'{int(float(v))} "{_clean_label(lb)}"' for v, lb in numeric_pairs
                )
                lines.append(f"\tlabel define {lset} {define_parts}")
                lines.append(f"\tcap label values {name} {lset}")

        lines.append("")

    return lines


def _emit_append_and_save() -> list[str]:
    """Emit the block that appends existing data (if any) and saves to DTA format."""
    return [
        "\t* append old, previously-imported data (if any)",
        '\tcap confirm file "`dtafile\'"',
        "\tif _rc == 0 {",
        "\t\tgen new_data_row=1",
        '\t\tappend using "`dtafile\'"',
        "\t\tsort key",
        "\t\tby key: gen num_for_key = _N",
        "\t\tdrop if num_for_key > 1 & ((`overwrite_old_data' == 0 & new_data_row == 1) | (`overwrite_old_data' == 1 & new_data_row ~= 1))",
        "\t\tdrop num_for_key",
        "\t\tdrop new_data_row",
        "\t}",
        "",
        "\t* save data to Stata format",
        '\tsave "`dtafile\'", replace',
        "",
        "\t* show codebook and notes",
        "\tcodebook",
        "\tnotes list",
    ]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_scto_import_script(
    form_def: dict,
    form_id: str,
    form_title: str,
    survey_name: str,
    datasure_version: str,
) -> str:
    """Generate a Stata import do-file from a SurveyCTO form definition JSON.

    The generated script mirrors the structure of SurveyCTO's own auto-generated
    import do-files and is compatible with the ``$raw`` and ``$logdir`` globals
    set by ``0_main.do`` in the replication package.

    Parameters
    ----------
    form_def : dict
        Form definition returned by ``SurveyCTOAPIClient.download_form_definition``.
        Expected keys: ``fieldsRowsAndColumns``, ``choicesRowsAndColumns``.
    form_id : str
        The SurveyCTO form ID (used in the script header comment).
    form_title : str
        Human-readable form title (used in the script header comment).
    survey_name : str
        Survey name used for raw CSV and DTA file naming.
    datasure_version : str
        DataSure version string (used in the script header comment).

    Returns
    -------
    str
        Stata do-file content as a string.
    """
    safe_s = survey_name.lower().replace(" ", "_")
    csv_file = f"{safe_s}_raw.csv"
    dta_file = f"{safe_s}_raw.dta"

    f_hdr, f_data, c_hdr, c_data = _parse_form(form_def)
    choices_map = _build_choices_map(c_hdr, c_data)
    lbl_col = _find_label_col(f_hdr)

    note_fields, text_fields, date_fields, datetime_fields, survey_fields = (
        _classify_fields(f_hdr, f_data, lbl_col)
    )

    L: list[str] = []
    L += _emit_preamble(form_title, form_id, csv_file, dta_file, datasure_version)
    L += _emit_type_locals(
        _chunk_names(note_fields),
        _chunk_names(text_fields),
        _chunk_names(date_fields),
        _chunk_names(datetime_fields),
    )
    L += [
        'disp ""',
        'disp "Starting import of: `csvfile\'"',
        'disp ""',
        "",
        "* import data from primary .csv file",
        'insheet using "`csvfile\'", names clear',
        "",
        "* drop extra table-list columns",
        "cap drop reserved_name_for_field_*",
        "cap drop generated_table_list_lab*",
        "",
        "* continue only if there's at least one row of data to import",
        "if _N>0 {",
    ]
    L += _emit_drop_note_fields()
    L += _emit_format_date_fields()
    L += _emit_coerce_text_fields()
    L += _emit_consolidate_key()
    L += _emit_system_labels()
    L += _emit_survey_labels(survey_fields, choices_map)
    L += _emit_append_and_save()
    L += [
        "}",
        "",
        'disp ""',
        'disp "Finished import of: `csvfile\'"',
        'disp ""',
        "",
        _LOG_CLOSE,
    ]

    return "\n".join(L) + "\n"
