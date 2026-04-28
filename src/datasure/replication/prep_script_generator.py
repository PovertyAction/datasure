"""Data-preparation script generator for Stata replication packages.

Translates the prep log (recorded in the Prepare Data section) into a
reproducible Stata do-file.

Each row in the prep log stores a ``prep_args`` JSON dict that matches the
``PrepActionResult`` dataclass.  The generator parses those dicts and emits
Stata statements that reproduce every recorded step.
"""

from __future__ import annotations

import json
from typing import Any

import polars as pl

from datasure.replication.script_generators import _C, _header

# ---------------------------------------------------------------------------
# String constants mirroring enum values (avoids importing the full app stack)
# ---------------------------------------------------------------------------

_ACT_REMOVE_COL = "remove column(s)"
_ACT_REMOVE_ROW = "remove row(s)"
_ACT_TRANSFORM = "transform column(s)"
_ACT_ADD_COL = "add new column"

_METH_BY_INDEX = "by row index"

_COND_MISSING = "value is missing"
_COND_NOT_MISSING = "value is not missing"
_COND_EQ = "value is equal to"
_COND_NEQ = "value is not equal to"
_COND_GT = "value is greater than"
_COND_GTE = "value is greater than or equal to"
_COND_LT = "value is less than"
_COND_LTE = "value is less than or equal to"
_COND_BETWEEN = "value is between"
_COND_NOT_BETWEEN = "value is not between"
_COND_LIKE = "value is like"
_COND_NOT_LIKE = "value is not like"

# Comparison conditions map to the KEEP operator (opposite of the condition)
# e.g. "remove where col > val" → keep where col <= val
_KEEP_OP: dict[str, str] = {
    _COND_GT: "<=",
    _COND_GTE: "<",
    _COND_LT: ">=",
    _COND_LTE: ">",
    _COND_EQ: "==",
    _COND_NEQ: "!=",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _cols(args: dict) -> list[str]:
    src = args.get("source_columns") or []
    if isinstance(src, str):
        return [src]
    return list(src)


def _val(args: dict) -> Any:
    return args.get("value")


def _val_list(args: dict) -> list:
    v = _val(args)
    if v is None:
        return []
    return v if isinstance(v, list) else [v]


def _is_numeric_val(v: Any) -> bool:
    try:
        float(str(v))
    except (ValueError, TypeError):
        return False
    else:
        return True


def _fmt_val(v: Any) -> str:
    """Format a value for a Stata expression."""
    if _is_numeric_val(v):
        return str(v)
    return f'"{v}"'


def _col_list(cols: list[str]) -> str:
    """Space-separated column list for Stata."""
    return " ".join(cols)


# ---------------------------------------------------------------------------
# Stata emitters
# ---------------------------------------------------------------------------


def _stata_remove_columns(args: dict, _desc: str) -> list[str]:
    cols = _cols(args)
    return [f"drop {_col_list(cols)}"]


def _drop_by_index(values: list) -> list[str]:
    idx_vals = [str(int(v)) for v in values if str(v).strip() not in (",", "")]
    if not idx_vals:
        return [f"{_C} NOTE: no row indices provided for drop in"]
    if len(idx_vals) == 1:
        return [f"drop in {idx_vals[0]}"]
    conditions = " | ".join(f"_n == {v}" for v in idx_vals)
    return [f"drop if {conditions}"]


def _drop_by_condition(col: str, condition: str, values: list) -> list[str]:
    if condition == _COND_MISSING:
        return [f"drop if missing({col})"]
    if condition == _COND_NOT_MISSING:
        return [f"keep if missing({col})"]
    if condition in (_COND_LIKE, _COND_NOT_LIKE):
        pattern = values[0] if values else ""
        if condition == _COND_LIKE:
            return [f'drop if regexm({col}, "{pattern}")']
        return [f'keep if regexm({col}, "{pattern}")']
    if condition in (_COND_BETWEEN, _COND_NOT_BETWEEN) and len(values) >= 2:
        lo, hi = values[0], values[1]
        if condition == _COND_BETWEEN:
            return [f"drop if inrange({col}, {lo}, {hi})"]
        return [f"keep if inrange({col}, {lo}, {hi})"]
    op = _KEEP_OP.get(condition)
    if op and values:
        fv = _fmt_val(values[0] if isinstance(values, list) else values)
        return [f"keep if {col} {op} {fv}"]
    return [f"{_C} NOTE: condition '{condition}' could not be translated"]


def _stata_remove_rows(args: dict, _desc: str) -> list[str]:
    method = args.get("method", "")
    cols = _cols(args)
    condition = args.get("condition", "")
    values = _val_list(args)

    if method == _METH_BY_INDEX:
        return _drop_by_index(values)

    if not cols or not condition:
        return [f"{_C} NOTE: remove row step could not be translated"]

    return _drop_by_condition(cols[0], condition, values)


def _stata_transform_column(args: dict, _desc: str) -> list[str]:
    cols = _cols(args)
    method = (args.get("method") or "").lower()
    values = _val_list(args)
    col = cols[0] if cols else ""

    simple_stata: dict[str, str] = {
        "trim": f"replace {col} = strtrim({col})",
        "lowercase": f"replace {col} = lower({col})",
        "uppercase": f"replace {col} = upper({col})",
        "absolute value": f"replace {col} = abs({col})",
        "floor": f"replace {col} = floor({col})",
        "ceil": f"replace {col} = ceil({col})",
        "round": f"replace {col} = round({col})",
        "string to number": f"destring {col}, replace",
        "string to date": (f'gen {col}_date = date({col}, "DMY")  // adjust format'),
        "string to datetime": (
            f'gen {col}_dt = clock({col}, "DMYhms")  // adjust format'
        ),
        "day of month": f"gen {col}_day = day({col})",
        "day of week": f"gen {col}_dow = dow({col})",
        "day of year": f"gen {col}_doy = doy({col})",
        "week of year": f"gen {col}_week = week({col})",
        "month of year": f"gen {col}_month = month({col})",
        "year": f"gen {col}_year = year({col})",
        "quarter of year": f"gen {col}_quarter = quarter({col})",
        "hour": f"gen {col}_hour = hh({col})",
        "minute": f"gen {col}_minute = mm({col})",
        "second": f"gen {col}_second = ss({col})",
    }

    arith_ops: dict[str, str] = {
        "add": "+",
        "subtract": "-",
        "multiply": "*",
        "divide": "/",
    }

    if method in simple_stata:
        return [simple_stata[method]]

    if method in arith_ops and values:
        op = arith_ops[method]
        fv = _fmt_val(values[0])
        return [f"replace {col} = {col} {op} {fv}"]

    if method == "replace" and len(values) >= 2:
        old, new = values[0], values[1]
        return [f'replace {col} = subinstr({col}, "{old}", "{new}", .)']

    if method == "substring" and len(values) >= 2:
        start, end = int(values[0]) + 1, int(values[1])
        length = end - (start - 1)
        return [f"replace {col} = substr({col}, {start}, {length})"]

    if method == "extract pattern" and values:
        pattern = values[0]
        return [f'gen {col}_extract = regexs(0) if regexm({col}, "{pattern}")']

    if method == "get dummies":
        return [f"tabulate {col}, gen({col}_)  // creates dummy columns"]

    return [f"{_C} NOTE: transform '{method}' on '{col}' could not be translated"]


def _stata_add_column(args: dict, _desc: str) -> list[str]:
    new_col = args.get("column_names") or ""
    method = (args.get("method") or "").lower()
    src_cols = _cols(args)
    values = _val_list(args)

    if method == "constant":
        raw = values[0] if values else (args.get("value") or "")
        fv = _fmt_val(raw)
        return [f"gen {new_col} = {fv}"]

    if method == "index":
        return [f"gen {new_col} = _n"]

    if method == "uuid":
        return [f"{_C} NOTE: uuid column '{new_col}' — no direct Stata equivalent"]

    if method == "random":
        return [f"gen {new_col} = runiform()"]

    agg_stata: dict[str, str] = {
        "sum": "+".join(src_cols),
        "mean": f"({' + '.join(src_cols)}) / {len(src_cols)}",
        "min": f"min({', '.join(src_cols)})",
        "max": f"max({', '.join(src_cols)})",
    }

    if method in agg_stata and src_cols:
        return [f"gen {new_col} = {agg_stata[method]}"]

    if method == "first" and src_cols:
        return [f"gen {new_col} = {src_cols[0]}"]

    if method == "last" and src_cols:
        return [f"gen {new_col} = {src_cols[-1]}"]

    if method == "diff" and len(src_cols) >= 2:
        return [f"gen {new_col} = {src_cols[0]} - {src_cols[1]}"]

    if method == "quotient" and len(src_cols) >= 2:
        return [f"gen {new_col} = {src_cols[0]} / {src_cols[1]}"]

    return [f"{_C} NOTE: add column '{new_col}' ({method}) could not be translated"]


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_EMITTERS = {
    _ACT_REMOVE_COL: _stata_remove_columns,
    _ACT_REMOVE_ROW: _stata_remove_rows,
    _ACT_TRANSFORM: _stata_transform_column,
    _ACT_ADD_COL: _stata_add_column,
}

# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_prepare_data_script(
    prep_log: pl.DataFrame,
    project_name: str,
    survey_name: str,
    datasure_version: str,
) -> str:
    """Generate a Stata prepare_data do-file from the prep log.

    Parameters
    ----------
    prep_log : pl.DataFrame
        Prep log with columns: action, description, prep_args, action_index.
    project_name : str
        Human-readable project name.
    survey_name : str
        Human-readable survey name.
    datasure_version : str
        Version of DataSure.

    Returns
    -------
    str
        Stata script content as a string.
    """
    h = _header(
        "Data Preparation Script",
        project_name,
        survey_name,
        datasure_version,
    )

    if prep_log.is_empty():
        return (
            h
            + 'cap log using "$logdir/3_prepare_data.log", replace text\n'
            + f"{_C} No preparation steps recorded.\n"
            + "cap log close\n"
        )

    lines: list[str] = [
        h,
        'cap log using "$logdir/3_prepare_data.log", replace text',
        "",
    ]

    for i, row in enumerate(prep_log.iter_rows(named=True), start=1):
        action = str(row.get("action") or "")
        description = str(row.get("description") or "")
        raw_args = row.get("prep_args") or "{}"

        # Parse prep_args — may arrive as a JSON string, a dict, or a struct
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                try:
                    import ast

                    args = ast.literal_eval(raw_args)
                except Exception:
                    args = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}

        lines.append(f"{_C} Step {i}: {description or action}")

        emitter = _EMITTERS.get(action)
        if emitter:
            lines.extend(emitter(args, description))
        else:
            lines.append(f"{_C} NOTE: unknown action '{action}'")

        lines.append("")

    lines.append("cap log close")
    return "\n".join(lines)
