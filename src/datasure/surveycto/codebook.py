"""The data dictionary workbook: Instructions, Variables, Choices, Summary stats.

``save_codebook`` writes it from ``build_dictionary``'s output, with the PII
blocks attached, and ``stats_rows``'s rows. It adds no submission values beyond
the summary stats, which give flagged PII columns counts only.

The Variables sheet's ``choices`` column names each select's list in the
Choices sheet. The compiled XML does not keep the XLSForm list names, so each
list is named after its question.
"""

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from datasure.surveycto.stats import COLUMNS as STATS_COLUMNS
from datasure.surveycto.survey import choice_labels, gates, plain_label, rule

# Variables sheet columns and what each holds, for the Instructions sheet.
VARIABLE_DESCRIPTIONS = {
    "variable": "Column name in the raw data, as SurveyCTO exports it",
    "stata_name": (
        "Name of the column in the package's Stata scripts and final data. "
        "Differs from variable only when Stata can't use that name"
    ),
    "question": (
        "Form field the column comes from. Differs from variable for repeat "
        "instances (_1, _2) and select_multiple choice columns"
    ),
    "label": "Question text, in the form's default language",
    "hint": "Hint shown under the question",
    "type": (
        "XLSForm type (select_one, integer, calculate...). system: added by "
        "SurveyCTO. Blank: not in the current form version, or added in "
        "Prepare Data"
    ),
    "group": "Groups and repeats the field sits in, outermost first",
    "relevance": (
        "Condition, including its groups', for the question to be asked. Blank: "
        "always asked. Summary stats count only rows where it holds"
    ),
    "calculation": "Formula of a calculate field",
    "choices": "Choice list in the Choices sheet, for select questions",
    "value_labels": (
        "Codes and their labels. For a select_multiple choice column, 1 = chosen "
        "and 0 = not chosen"
    ),
    "arrow_type": "Storage type in the raw data",
    "non_null": "Rows with a value in the raw data, over all rows",
    "missing_rate": "Share of all raw rows with no value, asked or not",
    "sentinels": (
        "The project's missing codes found in the column, with their label and count"
    ),
    "final_missing_rate": (
        "Share of rows with no value in the final data, after Prepare Data and "
        "corrections. Blank: the column was dropped"
    ),
    "final_unique": "Distinct values in the final data, missing counted once",
    "pii_status": (
        "PII flag from the form's rules: contains_pii, may_contain_pii (values "
        "not checked), cleared_by_form (publishable) or whitelisted (numbers, "
        "dates, inline choices, system columns). Values of contains_pii and "
        "may_contain_pii columns are never shown in this workbook"
    ),
    "pii_basis": (
        "Why: publishable, type:<type>, device:<column>, lineage:<fields> (a "
        "calculate reading them), choices:inline, system, unscanned..."
    ),
}
VARIABLE_COLUMNS = [
    "variable",
    "stata_name",
    "question",
    "label",
    "hint",
    "type",
    "group",
    "relevance",
    "calculation",
    "choices",
    "value_labels",
    "arrow_type",
    "non_null",
    "missing_rate",
    "sentinels",
    "final_missing_rate",
    "final_unique",
    "pii_status",
    "pii_basis",
]
_WRAPPED = {
    "label",
    "hint",
    "relevance",
    "calculation",
    "value_labels",
    "frequencies",
    "sentinel_detail",
    "description",
}
CHOICE_COLUMNS = ["list_name", "value", "label"]
INSTRUCTION_COLUMNS = ["sheet", "column", "description"]
_SHEET_DESCRIPTIONS = [
    [
        "Variables",
        "",
        "One row per column of the raw data, then any column added in Prepare Data",
    ],
    [
        "Choices",
        "",
        "Each choice list's codes and labels. A list is named after its "
        "question: SurveyCTO's compiled form does not keep XLSForm list names",
    ],
    [
        "Summary stats",
        "",
        "Counts and frequencies over the rows where each question "
        "was asked. Columns flagged as PII show counts only",
    ],
]
_PERCENT = {"missing_rate", "final_missing_rate", "selected_share"}
# One style object each: openpyxl hashes every cell's style into the workbook.
_HEADER_FONT = Font(bold=True)
_HEADER_FILL = PatternFill("solid", fgColor="DDE5F0")
_WRAP = Alignment(wrap_text=True, vertical="top")


def _choice_list(survey: dict) -> str:
    """Return the name of a select's list in the Choices sheet, or ``""``.

    A withheld list is not in the outputs, so it is not named either.
    """
    if survey.get("choices") and not survey.get("choices_withheld"):
        return survey.get("choice_list") or ""
    return ""


def _choice_rows(variables: dict) -> list[list]:
    """Return each listed choice once per list, in form order."""
    rows = []
    seen = set()
    for v in variables.values():
        survey = v["survey"] or {}
        list_name = _choice_list(survey)
        if not list_name or list_name in seen:
            continue
        seen.add(list_name)
        rows.extend(
            [list_name, value, label]
            for value, label in choice_labels(survey["choices"]).items()
        )
    return rows


def _variable_row(name: str, v: dict) -> dict:
    survey = v["survey"] or {}
    return {
        "variable": name,
        "question": v["question"] or "",
        "label": plain_label(survey.get("question_text") or ""),
        "hint": plain_label(survey.get("hint") or ""),
        "type": survey.get("type") or ("system" if v.get("system") else ""),
        "group": survey.get("group_path", ""),
        "relevance": rule(gates(survey)) if survey else "",
        "calculation": survey.get("calculation") or "",
        "choices": _choice_list(survey),
        "value_labels": "; ".join(
            f"{c['value']} = {c['label']}" for c in v.get("value_labels", [])
        ),
        "arrow_type": v["parquet"]["arrow_type"],
        "non_null": v["non_null_count"],
        "missing_rate": v["missing_rate"],
        "sentinels": "; ".join(
            f"{code} {s['label']}: {s['count']}"
            for code, s in v.get("sentinels", {}).items()
        ),
        "pii_status": v["pii"]["status"],
        "pii_basis": ", ".join(v["pii"]["basis"]),
    }


def _variable_rows(variables: dict, final: dict[str, dict]) -> list[list]:
    """Return a row per raw column, then one per column only the final data has.

    ``final`` maps a column name to its ``stata_name``, ``final_missing_rate``
    and ``final_unique`` in the final dataset; a column it lacks was dropped.
    """
    rows = [
        _variable_row(name, v) | final.get(name, {}) for name, v in variables.items()
    ]
    rows += [
        {"variable": name} | f for name, f in final.items() if name not in variables
    ]
    return [[row.get(c, "") for c in VARIABLE_COLUMNS] for row in rows]


def _sheet(workbook: Workbook, title: str, header: list[str], rows: list[list]) -> None:
    """Add a sheet to a write-only workbook: bold frozen header with a filter, each
    column as wide as its longest value (up to 60), long text wrapped, shares as %.
    """
    rows = [[None if value == "" else value for value in row] for row in rows]
    ws = workbook.create_sheet(title)
    for index, name in enumerate(header):
        longest = max(
            [len(name), *(len(str(r[index])) for r in rows if r[index] is not None)]
        )
        ws.column_dimensions[get_column_letter(index + 1)].width = min(longest + 2, 60)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(header))}{len(rows) + 1}"
    cells = []
    for name in header:
        cell = WriteOnlyCell(ws, name)
        cell.font, cell.fill = _HEADER_FONT, _HEADER_FILL
        cells.append(cell)
    ws.append(cells)
    styled = [name in _WRAPPED or name in _PERCENT for name in header]
    for row in rows:
        ws.append(
            [
                _cell(ws, name, value) if style else value
                for name, value, style in zip(header, row, styled, strict=True)
            ]
        )


def _cell(ws, name: str, value) -> WriteOnlyCell:
    cell = WriteOnlyCell(ws, value)
    if name in _WRAPPED:
        cell.alignment = _WRAP
    if name in _PERCENT and isinstance(value, (int, float)):
        cell.number_format = "0.0%"
    return cell


# A sheet's rows, the header included.


def _instruction_rows() -> list[list]:
    return [
        *_SHEET_DESCRIPTIONS,
        *(["Variables", c, VARIABLE_DESCRIPTIONS[c]] for c in VARIABLE_COLUMNS),
    ]


def save_codebook(
    dest, dictionary: dict, stats: list[dict], final: dict[str, dict] | None = None
) -> None:
    """Save the codebook workbook to ``dest``, a path or a binary file object.

    ``dictionary`` is ``build_dictionary``'s output with the PII blocks attached;
    ``stats`` is ``stats_rows``'s. ``final`` adds each column's Stata name and
    final-data counts to the Variables sheet (see ``_variable_rows``).
    """
    workbook = Workbook(write_only=True)
    _sheet(workbook, "Instructions", INSTRUCTION_COLUMNS, _instruction_rows())
    _sheet(
        workbook,
        "Variables",
        VARIABLE_COLUMNS,
        _variable_rows(dictionary["variables"], final or {}),
    )
    _sheet(workbook, "Choices", CHOICE_COLUMNS, _choice_rows(dictionary["variables"]))
    _sheet(
        workbook,
        "Summary stats",
        STATS_COLUMNS,
        [[row[c] for c in STATS_COLUMNS] for row in stats],
    )
    workbook.save(dest)
