"""SurveyCTO-specific Stata import do-file generator.

Generates an import do-file from a SurveyCTO form definition JSON that
mirrors the structure of SurveyCTO's own auto-generated import do-files:
field-type classification, date/datetime conversion, text coercion, and
per-variable labels, notes, and value labels for select fields.
"""

from __future__ import annotations

import re

from datasure.processing.replication.script_generators import _C

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

# ---------------------------------------------------------------------------
# Helpers
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


def _clean_label(text: str) -> str:
    """Strip HTML tags and escape text for a Stata double-quoted string."""
    # Remove HTML tags (SurveyCTO embeds <b>, <br/>, <span ...>, etc.)
    text = _HTML_TAG_RE.sub("", text).strip()
    # Escape $ to prevent Stata macro expansion (SurveyCTO uses ${var} syntax)
    text = text.replace("$", r"\$")
    # Replace embedded double-quotes with single quotes
    text = text.replace('"', "'")
    return text


def _truncate(text: str, max_len: int) -> str:
    return text[:max_len] if len(text) > max_len else text


def _chunk_names(names: list[str], max_len: int = _LOCAL_CHUNK) -> list[list[str]]:
    """Split a list of variable names into chunks that fit inside a Stata local."""
    chunks: list[list[str]] = []
    current: list[str] = []
    current_len = 0
    for name in names:
        add = len(name) + (1 if current else 0)  # +1 for space separator
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


def _is_numeric_str(s: str) -> bool:
    try:
        float(s)
    except (ValueError, TypeError):
        return False
    else:
        return True


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


def _build_choices_map(
    c_hdr: list[str], c_data: list[list]
) -> dict[str, list[tuple[str, str]]]:
    """Build ``{list_name: [(value, label), ...]}`` from the choices rows."""
    result: dict[str, list[tuple[str, str]]] = {}
    if not c_hdr or not c_data:
        return result
    lbl_col = _find_label_col(c_hdr)
    try:
        li = c_hdr.index("list_name")
        ni = c_hdr.index("name")
    except ValueError:
        return result
    bi = c_hdr.index(lbl_col) if lbl_col in c_hdr else -1
    for row in c_data:
        if len(row) <= max(li, ni):
            continue
        lst = str(row[li] or "").strip()
        val = str(row[ni] or "").strip()
        lbl = str(row[bi] or "").strip() if bi >= 0 and len(row) > bi else ""
        if lst and val:
            result.setdefault(lst, []).append((val, lbl))
    return result


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
    import do-files and is compatible with the ``$raw`` / ``$output`` globals
    set by ``master.do`` in the replication package.

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

    # ── Classify fields by type ───────────────────────────────────────────────
    note_fields: list[str] = []
    text_fields: list[str] = []
    date_fields: list[str] = []
    datetime_fields: list[str] = []
    # (name, base_type, list_name, label_text)
    survey_fields: list[tuple[str, str, str, str]] = []

    for row in f_data:
        name = _get_col(row, f_hdr, "name")
        raw_type = _get_col(row, f_hdr, "type")
        label = _get_col(row, f_hdr, lbl_col) if lbl_col else ""
        disabled = _get_col(row, f_hdr, "disabled").lower()

        if not name or not raw_type or disabled == "yes":
            continue

        parts = raw_type.split(None, 1)
        base = parts[0].lower()
        list_name = parts[1] if len(parts) > 1 else ""

        if not base or base in _SKIP_TYPES:
            continue

        if base in _NOTE_TYPES:
            note_fields.append(name)
        elif base in _TEXT_TYPES:
            text_fields.append(name)
        elif base in _DATE_TYPES:
            date_fields.append(name)
        elif base in _DATETIME_TYPES:
            datetime_fields.append(name)
        # GPS, image, audio, video, integer, decimal: no special classification;
        # Stata handles numeric fields automatically on CSV import.

        survey_fields.append((name, base, list_name, label))

    # Ensure standard system datetime fields are always included
    for sf in _SYSTEM_DATETIMES:
        if sf not in datetime_fields:
            datetime_fields.append(sf)

    # ── Chunk field lists into Stata locals ───────────────────────────────────
    note_chunks = _chunk_names(note_fields)
    text_chunks = _chunk_names(text_fields)
    date_chunks = _chunk_names(date_fields)
    dt_chunks = _chunk_names(datetime_fields)

    L: list[str] = []

    # ── File header ───────────────────────────────────────────────────────────
    L += [
        f"{_C} import_data.do",
        f"{_C}",
        f'{_C}    Imports and labels "{form_title}" (ID: {form_id}) data.',
        f"{_C}",
        f'{_C}    Inputs:  "${{raw}}/{csv_file}"',
        f'{_C}    Outputs: "${{output}}/{dta_file}"',
        f"{_C}",
        f"{_C}    Generated by DataSure {datasure_version}",
        "",
        "* initialize Stata",
        "clear all",
        "set more off",
        "",
        "* initialize workflow-specific parameters",
        "*    Set overwrite_old_data to 1 to allow un-approving submissions.",
        "local overwrite_old_data 0",
        "",
        "* initialize form-specific parameters",
        f'local csvfile "${{raw}}/{csv_file}"',
        f'local dtafile "${{output}}/{dta_file}"',
        "",
    ]

    # ── Field-type locals ─────────────────────────────────────────────────────
    L += _emit_locals("note_fields", note_chunks)
    L += _emit_locals("text_fields", text_chunks)
    L += _emit_locals("date_fields", date_chunks)
    L += _emit_locals("datetime_fields", dt_chunks)
    L += [""]

    # ── Import CSV ────────────────────────────────────────────────────────────
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

    # ── Drop note fields ──────────────────────────────────────────────────────
    L += [
        "\t* drop note fields (since they don't contain any real data)",
        "\tforvalues i = 1/100 {",
        '\t\tif "`note_fields`i\'\'" ~= "" {',
        "\t\t\tdrop `note_fields`i''",
        "\t\t}",
        "\t}",
        "",
    ]

    # ── Format date/datetime fields ───────────────────────────────────────────
    L += [
        "\t* format date and date/time fields",
        "\tforvalues i = 1/100 {",
        '\t\tif "`datetime_fields`i\'\'" ~= "" {',
        "\t\t\tforeach dtvarlist in `datetime_fields`i'' {",
        "\t\t\t\tcap unab dtvarlist : `dtvarlist'",
        "\t\t\t\tif _rc==0 {",
        "\t\t\t\t\tforeach dtvar in `dtvarlist' {",
        "\t\t\t\t\t\ttempvar tempdtvar",
        "\t\t\t\t\t\trename `dtvar' `tempdtvar'",
        "\t\t\t\t\t\tgen double `dtvar'=.",
        "\t\t\t\t\t\tcap replace `dtvar'=clock(`tempdtvar',\"MDYhms\",2025)",
        "\t\t\t\t\t\t* automatically try without seconds, just in case",
        "\t\t\t\t\t\tcap replace `dtvar'=clock(`tempdtvar',\"MDYhm\",2025) if `dtvar'==. & `tempdtvar'~=\"\"",
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
        "\t\t\t\t\t\tcap replace `dtvar'=date(`tempdtvar',\"MDY\",2025)",
        "\t\t\t\t\t\tformat %td `dtvar'",
        "\t\t\t\t\t\tdrop `tempdtvar'",
        "\t\t\t\t\t}",
        "\t\t\t\t}",
        "\t\t\t}",
        "\t\t}",
        "\t}",
        "",
    ]

    # ── Ensure text fields are strings ────────────────────────────────────────
    L += [
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

    # ── Consolidate key ───────────────────────────────────────────────────────
    L += [
        "\t* consolidate unique ID into key variable",
        '\treplace key=instanceid if key==""',
        "\tdrop instanceid",
        "",
    ]

    # ── Standard system variable labels ───────────────────────────────────────
    L += [
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

    # ── Per-variable labels, notes, and value labels ──────────────────────────
    used_label_sets: set[str] = set()

    for name, base, list_name, label in survey_fields:
        esc = _clean_label(label)
        short = _truncate(esc, _LABEL_VAR_MAX)

        L.append(f'\tlabel variable {name} "{short}"')
        if label:
            L.append(f'\tnote {name}: "{esc}"')

        # Value labels for select_one / select_multiple with numeric choice values
        if base in (_SELECT_ONE, _SELECT_MULTI) and list_name in choices_map:
            pairs = choices_map[list_name]
            numeric_pairs = [(v, lb) for v, lb in pairs if _is_numeric_str(v)]
            if numeric_pairs:
                lset = name if name not in used_label_sets else f"{name}_lbl"
                used_label_sets.add(lset)
                define_parts = " ".join(
                    f'{int(float(v))} "{_clean_label(lb)}"' for v, lb in numeric_pairs
                )
                L.append(f"\tlabel define {lset} {define_parts}")
                L.append(f"\tlabel values {name} {lset}")

        L.append("")

    # ── Append old data and save ──────────────────────────────────────────────
    L += [
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
        "}",
        "",
        'disp ""',
        'disp "Finished import of: `csvfile\'"',
        'disp ""',
    ]

    return "\n".join(L) + "\n"
