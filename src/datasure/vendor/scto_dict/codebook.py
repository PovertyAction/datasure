"""The xlsx outputs: the PI-facing codebook and the PII review workbook.

``<form>_codebook.xlsx`` has a Variables and a Summary stats sheet, built from the
outputs ``scto-build`` writes; it adds no submission values beyond the summary stats,
which give flagged PII columns counts only. ``scto-codebook`` writes
``<form>_summary_stats.csv`` too, from the same stats. ``<form>_pii_review.xlsx`` is the opposite:
the flagged columns' values, for the people cleaning the data.
"""

import datetime as dt
import json
from pathlib import Path

import pyarrow as pa
from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from datasure.vendor.scto_dict.pii import shows_values
from datasure.vendor.scto_dict.stats import COLUMNS as STATS_COLUMNS
from datasure.vendor.scto_dict.stats import write_form_stats
from datasure.vendor.scto_dict.survey import gates, plain_label, rule

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


REVIEW_COLUMNS = ["column", "label", "status", "basis", "hit_rows", "non_null"]


VALUE_COLUMNS = ["KEY", "column", "value"]
# A sheet's rows, the header included.
_EXCEL_ROWS = 1_048_576


def write_pii_review(table: pa.Table, vardict: dict, path: Path) -> Path:
    """Write every flagged column to ``path``: a Columns sheet and a Values sheet with
    one row per value (``KEY``, column, value), which filters by column in Excel.

    Text stays text, so IDs keep their leading zeros. Timestamps are UTC, written
    without the zone, which Excel does not store. More values than a sheet holds
    raise.
    """
    variables = vardict["variables"]
    flagged = [
        c for c in table.schema.names if not shows_values(variables[c]["pii"]["status"])
    ]
    columns = [
        [
            c,
            plain_label((variables[c]["survey"] or {}).get("question_text") or ""),
            variables[c]["pii"]["status"],
            ", ".join(variables[c]["pii"]["basis"]),
            variables[c]["pii"].get("presidio", {}).get("hit_rows", ""),
            variables[c]["non_null_count"],
        ]
        for c in flagged
    ]
    keys = table.column("KEY").to_pylist()
    values = [
        [key, c, v.replace(tzinfo=None) if isinstance(v, dt.datetime) else v]
        for c in flagged
        for key, v in zip(keys, table.column(c).to_pylist(), strict=True)
        if v is not None
    ]
    if len(values) >= _EXCEL_ROWS:
        raise ValueError(
            f"{path.name}: {len(values)} flagged values, more than a sheet's "
            f"{_EXCEL_ROWS - 1} rows; clear columns in [pii] whitelist and rebuild"
        )
    workbook = Workbook(write_only=True)
    _sheet(workbook, "Columns", REVIEW_COLUMNS, columns)
    _sheet(workbook, "Values", VALUE_COLUMNS, values)
    workbook.save(path)
    return path


def write_codebook(form_dir: Path, form_id: str, stats: list[dict]) -> Path:
    """Write ``<form>_codebook.xlsx`` next to the outputs from the form's stats rows."""
    form_dir = Path(form_dir)
    dictionary = json.loads(
        (form_dir / f"{form_id}_variable_dictionary.json").read_text(encoding="utf-8")
    )
    path = form_dir / f"{form_id}_codebook.xlsx"
    save_codebook(path, dictionary, stats)
    return path


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


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``scto-codebook``."""
    from dotenv import load_dotenv

    from datasure.vendor.scto_dict.cli import config_arg, env_sentinels

    cfg = config_arg(argv)
    load_dotenv()
    sentinels = env_sentinels()
    for form in cfg.forms:
        stats = write_form_stats(cfg.form_dir(form), form, sentinels)
        path = write_codebook(cfg.form_dir(form), form, stats)
        print(f"[codebook] {form} -> {path}")
