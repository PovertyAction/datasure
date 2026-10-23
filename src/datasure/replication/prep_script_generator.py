"""Data-preparation script generator for Stata replication packages.

Translates the prep log (recorded in the Prepare Data section) into a
reproducible Stata do-file.

Each row in the prep log stores a ``prep_args`` JSON dict that matches the
``PrepActionResult`` dataclass.  The generator parses those dicts and emits
Stata statements that reproduce every recorded step.
"""

from __future__ import annotations

import ast
import json
from collections.abc import Callable
from typing import Any

import polars as pl

from datasure.replication.script_generators import _C, _LOG_CLOSE, _header

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
    _COND_EQ: "!=",
    _COND_NEQ: "==",
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


def _stata_to_string(col: str) -> list[str]:
    """Convert a column to text the way DataSure's ``to string`` does.

    The CSV import keeps every column as text, so a text column is fixed up
    as text rather than destrung, which would round large IDs through a
    double. A column of numbers drops a whole float's ".0" ("12.0" becomes
    "12"), and a column of CSV timestamps swaps the "T" for DataSure's
    space. SurveyCTO dates and datetimes are both datetimes in DataSure, so
    they get its full timestamp text. Missing values become "" instead of
    ".", and Stata's ".5" gets DataSure's leading zero. The code avoids "$",
    which a do-file would expand as a global macro.
    """
    return [
        f"capture confirm string variable {col}",
        "if !_rc {",
        f"    quietly count if !missing({col}) & missing(real({col}))",
        "    if r(N) == 0 {",
        (
            f"        quietly replace {col} = substr({col}, 1, strlen({col}) - 2) "
            f'if substr({col}, -2, 2) == ".0"'
        ),
        "    }",
        (
            f"    quietly count if !missing({col}) & "
            f'!ustrregexm({col}, "^[0-9]{{4}}-[0-9]{{2}}-[0-9]{{2}}T[0-9]")'
        ),
        "    if r(N) == 0 {",
        (
            f'        quietly replace {col} = substr({col}, 1, 10) + " " '
            f"+ substr({col}, 12, .) if !missing({col})"
        ),
        "    }",
        "}",
        f"capture confirm numeric variable {col}",
        "if !_rc {",
        "    tempvar s",
        f"    local fmt : format {col}",
        '    if strpos("`fmt\'", "%td") {',
        (
            f'        gen `s\' = string({col}, "%tdCCYY-NN-DD") '
            f'+ " 00:00:00.000000" if !missing({col})'
        ),
        "    }",
        '    else if strpos("`fmt\'", "%tc") {',
        (
            f'        gen `s\' = string({col}, "%tcCCYY-NN-DD_HH:MM:SS.sss") '
            f'+ "000" if !missing({col})'
        ),
        "    }",
        "    else {",
        f'        gen `s\' = string({col}, "%17.0g") if !missing({col})',
        '        replace `s\' = "0" + `s\' if substr(`s\', 1, 1) == "."',
        (
            "        replace `s' = \"-0\" + substr(`s', 2, .) "
            'if substr(`s\', 1, 2) == "-."'
        ),
        "    }",
        f"    order `s', after({col})",
        f"    drop {col}",
        f"    rename `s' {col}",
        "}",
    ]


def _stata_to_number(col: str) -> list[str]:
    """Convert a true/false column to 1/0 the way DataSure's ``to number`` does.

    The raw CSV holds booleans as "true"/"false" text. Any other value,
    including "", becomes missing. A numeric column is left as it is.
    """
    return [
        f"capture confirm string variable {col}",
        "if !_rc {",
        "    tempvar n",
        f'    gen byte `n\' = 1 if {col} == "true"',
        f'    replace `n\' = 0 if {col} == "false"',
        f"    order `n', after({col})",
        f"    drop {col}",
        f"    rename `n' {col}",
        "}",
    ]


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

    if method == "to string":
        return _stata_to_string(col)

    if method == "to number":
        return _stata_to_number(col)

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


# (min_cols, expr) — expr receives the source-column list.
_ADD_COL_EXPRS: dict[str, tuple[int, Callable[[list[str]], str]]] = {
    "index": (0, lambda _: "_n"),
    "random": (0, lambda _: "runiform()"),
    "sum": (1, lambda c: "+".join(c)),
    "mean": (1, lambda c: f"({' + '.join(c)}) / {len(c)}"),
    "min": (1, lambda c: f"min({', '.join(c)})"),
    "max": (1, lambda c: f"max({', '.join(c)})"),
    "first": (1, lambda c: c[0]),
    "last": (1, lambda c: c[-1]),
    "diff": (2, lambda c: f"{c[0]} - {c[1]}"),
    "quotient": (2, lambda c: f"{c[0]} / {c[1]}"),
}


# Characters Stata would read as macro syntax or a quote delimiter, even
# inside compound quotes.
_STATA_UNSAFE_CHARS = frozenset('`$"')


def _stata_str_literal(text: str) -> str:
    """Stata string expression that evaluates to exactly ``text``.

    Runs of unsafe characters become ``char()`` calls so a separator like
    ``"`v'"`` or ``"$raw"`` is not expanded as a macro.
    """
    parts: list[str] = []
    run = ""
    for ch in text:
        if ch in _STATA_UNSAFE_CHARS:
            if run:
                parts.append(f'"{run}"')
                run = ""
            parts.append(f"char({ord(ch)})")
        else:
            run += ch
    if run or not parts:
        parts.append(f'"{run}"')
    return " + ".join(parts)


def _stata_concat(new_col: str, src_cols: list[str], separator: str) -> list[str]:
    """Join string columns, skipping empty values like DataSure's concat.

    ``egen concat()`` would keep a separator for every empty value, so the
    columns are joined one at a time instead. Stata has no string missing
    value apart from "", so a value that was an empty string (not missing)
    in DataSure is skipped here too.
    """
    sep = _stata_str_literal(separator)
    return [
        f'gen {new_col} = ""',
        f"foreach v in {_col_list(src_cols)} {{",
        f"    replace {new_col} = {new_col} + "
        f'cond({new_col} == "" | `v\' == "", "", {sep}) + `v\'',
        "}",
    ]


def _stata_add_column(args: dict, _desc: str) -> list[str]:
    new_col = args.get("column_names") or ""
    method = (args.get("method") or "").lower()
    src_cols = _cols(args)
    values = _val_list(args)

    if method == "constant":
        raw = values[0] if values else (args.get("value") or "")
        return [f"gen {new_col} = {_fmt_val(raw)}"]

    if method == "concat" and len(src_cols) >= 2:
        return _stata_concat(new_col, src_cols, args.get("value") or "")

    if method == "uuid":
        return [f"{_C} NOTE: uuid column '{new_col}' — no direct Stata equivalent"]

    entry = _ADD_COL_EXPRS.get(method)
    if entry and len(src_cols) >= entry[0]:
        _, expr_fn = entry
        return [f"gen {new_col} = {expr_fn(src_cols)}"]

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


def _parse_prep_args(raw: object) -> dict:
    """Parse prep_args — may arrive as a JSON string, a dict, or a Polars struct."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            try:
                return ast.literal_eval(raw)  # type: ignore[return-value]
            except Exception:
                return {}
    return {}


def _emit_prep_step(i: int, row: dict) -> list[str]:
    """Return the Stata lines for one prep-log row."""
    action = str(row.get("action") or "")
    description = str(row.get("description") or "")
    args = _parse_prep_args(row.get("prep_args") or "{}")

    comment = [f"{_C} Step {i}: {description or action}"]
    emitter = _EMITTERS.get(action)
    body = (
        emitter(args, description)
        if emitter
        else [f"{_C} NOTE: unknown action '{action}'"]
    )
    return comment + body + [""]


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
        lines.extend(_emit_prep_step(i, row))

    lines.append(_LOG_CLOSE)
    return "\n".join(lines) + "\n"
