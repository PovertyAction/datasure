"""The data dictionary workbook: a Variables and a Summary stats sheet.

``save_codebook`` writes it from ``build_dictionary``'s output, with the PII
blocks attached, and ``stats_rows``'s rows. It adds no submission values beyond
the summary stats, which give flagged PII columns counts only.
"""

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from datasure.surveycto.stats import COLUMNS as STATS_COLUMNS
from datasure.surveycto.survey import gates, plain_label, rule

VARIABLE_COLUMNS = [
    "variable",
    "question",
    "label",
    "hint",
    "type",
    "group",
    "relevance",
    "value_labels",
    "arrow_type",
    "non_null",
    "missing_rate",
    "sentinels",
    "pii_status",
    "pii_basis",
]
_WRAPPED = {
    "label",
    "hint",
    "relevance",
    "value_labels",
    "frequencies",
    "sentinel_detail",
}
_PERCENT = {"missing_rate", "selected_share"}
# One style object each: openpyxl hashes every cell's style into the workbook.
_HEADER_FONT = Font(bold=True)
_HEADER_FILL = PatternFill("solid", fgColor="DDE5F0")
_WRAP = Alignment(wrap_text=True, vertical="top")


def _variable_rows(variables: dict) -> list[list]:
    rows = []
    for name, v in variables.items():
        survey = v["survey"] or {}
        relevance = rule(gates(survey)) if survey else ""
        rows.append(
            [
                name,
                v["question"] or "",
                plain_label(survey.get("question_text") or ""),
                plain_label(survey.get("hint") or ""),
                survey.get("type") or ("system" if v.get("system") else ""),
                survey.get("group_path", ""),
                relevance,
                "; ".join(
                    f"{c['value']} = {c['label']}" for c in v.get("value_labels", [])
                ),
                v["parquet"]["arrow_type"],
                v["non_null_count"],
                v["missing_rate"],
                "; ".join(
                    f"{code} {s['label']}: {s['count']}"
                    for code, s in v.get("sentinels", {}).items()
                ),
                v["pii"]["status"],
                ", ".join(v["pii"]["basis"]),
            ]
        )
    return rows


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


def save_codebook(dest, dictionary: dict, stats: list[dict]) -> None:
    """Save the codebook workbook to ``dest``, a path or a binary file object.

    ``dictionary`` is ``build_dictionary``'s output with the PII blocks attached;
    ``stats`` is ``stats_rows``'s.
    """
    workbook = Workbook(write_only=True)
    _sheet(
        workbook, "Variables", VARIABLE_COLUMNS, _variable_rows(dictionary["variables"])
    )
    _sheet(
        workbook,
        "Summary stats",
        STATS_COLUMNS,
        [[row[c] for c in STATS_COLUMNS] for row in stats],
    )
    workbook.save(dest)
