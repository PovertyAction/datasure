"""Data-preparation script generators for replication packages.

Translates the prep log (recorded in the Prepare Data section) into
reproducible Stata, R, or Python scripts.

Each row in the prep log stores a ``prep_args`` JSON dict that matches the
``PrepActionResult`` dataclass.  The generators parse those dicts and emit
language-specific statements that reproduce every recorded step.
"""

from __future__ import annotations

import json
from typing import Any

import polars as pl

from datasure.processing.replication.script_generators import _COMMENT, _header

# ---------------------------------------------------------------------------
# String constants mirroring enum values (avoids importing the full app stack)
# ---------------------------------------------------------------------------

_ACT_REMOVE_COL = "remove column(s)"
_ACT_REMOVE_ROW = "remove row(s)"
_ACT_TRANSFORM = "transform column(s)"
_ACT_ADD_COL = "add new column"

_METH_BY_INDEX = "by row index"
_METH_BY_COND = "by condition"

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


def _first_val(args: dict) -> Any:
    v = _val(args)
    if isinstance(v, list) and v:
        return v[0]
    return v


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


def _fmt_val_py(v: Any) -> str:
    """Format a value for Python source code."""
    if _is_numeric_val(v):
        return str(v)
    return repr(str(v))


def _fmt_val_r(v: Any) -> str:
    if _is_numeric_val(v):
        return str(v)
    return f'"{v}"'


def _fmt_val_stata(v: Any) -> str:
    if _is_numeric_val(v):
        return str(v)
    return f'"{v}"'


def _col_list_py(cols: list[str]) -> str:
    return "[" + ", ".join(repr(c) for c in cols) + "]"


def _col_list_r(cols: list[str]) -> str:
    return "c(" + ", ".join(f'"{c}"' for c in cols) + ")"


def _col_list_stata(cols: list[str]) -> str:
    return " ".join(cols)


# ---------------------------------------------------------------------------
# Python emitters
# ---------------------------------------------------------------------------

_IND = "    "  # 4-space indent inside function body


def _py_remove_columns(args: dict, _desc: str) -> list[str]:
    cols = _cols(args)
    return [f"{_IND}df = df.drop(columns={_col_list_py(cols)})"]


def _py_remove_rows(args: dict, _desc: str) -> list[str]:
    method = args.get("method", "")
    cols = _cols(args)
    condition = args.get("condition", "")
    values = _val_list(args)

    if method == _METH_BY_INDEX:
        idx_vals = [int(v) for v in values if str(v).strip() not in (",", "")]
        return [f"{_IND}df = df.drop(index={idx_vals}).reset_index(drop=True)"]

    if not cols or not condition:
        return [f"{_IND}# NOTE: remove row step could not be translated"]

    col = cols[0]

    if condition == _COND_MISSING:
        return [f"{_IND}df = df.dropna(subset={_col_list_py(cols)})"]

    if condition == _COND_NOT_MISSING:
        return [f"{_IND}df = df[df[{col!r}].isna()]"]

    if condition in (_COND_LIKE, _COND_NOT_LIKE):
        pattern = values[0] if values else ""
        negate = "" if condition == _COND_LIKE else "~"
        return [
            f"{_IND}df = df[{negate}df[{col!r}]"
            f".str.contains({pattern!r}, regex=True, na=False)]"
        ]

    if condition in (_COND_BETWEEN, _COND_NOT_BETWEEN) and len(values) >= 2:
        lo, hi = values[0], values[1]
        if condition == _COND_BETWEEN:
            return [f"{_IND}df = df[(df[{col!r}] < {lo}) | (df[{col!r}] > {hi})]"]
        return [f"{_IND}df = df[(df[{col!r}] >= {lo}) & (df[{col!r}] <= {hi})]"]

    op = _KEEP_OP.get(condition)
    if op and values:
        fv = _fmt_val_py(values[0] if isinstance(values, list) else values)
        if op in ("==", "!="):
            all_exprs = " | ".join(f"df[{c!r}] {op} {fv}" for c in cols)
            return [f"{_IND}df = df[{all_exprs}]"]
        all_exprs = " | ".join(f"df[{c!r}] {op} {fv}" for c in cols)
        return [f"{_IND}df = df[{all_exprs}]"]

    return [f"{_IND}# NOTE: condition '{condition}' could not be translated"]


def _py_transform_column(args: dict, _desc: str) -> list[str]:
    cols = _cols(args)
    method = (args.get("method") or "").lower()
    values = _val_list(args)
    col = cols[0] if cols else ""

    simple_ops: dict[str, str] = {
        "trim": f"df[{col!r}].str.strip()",
        "lowercase": f"df[{col!r}].str.lower()",
        "uppercase": f"df[{col!r}].str.upper()",
        "absolute value": f"df[{col!r}].abs()",
        "floor": f"df[{col!r}].apply(import_floor)",
        "ceil": f"df[{col!r}].apply(import_ceil)",
        "round": f"df[{col!r}].round(0)",
        "string to number": (f"pd.to_numeric(df[{col!r}], errors='coerce')"),
        "string to date": f"pd.to_datetime(df[{col!r}], errors='coerce')",
        "string to datetime": (f"pd.to_datetime(df[{col!r}], errors='coerce')"),
        "day of month": f"pd.to_datetime(df[{col!r}]).dt.day",
        "day of week": f"pd.to_datetime(df[{col!r}]).dt.dayofweek",
        "day of year": f"pd.to_datetime(df[{col!r}]).dt.dayofyear",
        "date": f"pd.to_datetime(df[{col!r}]).dt.date",
        "week of year": f"pd.to_datetime(df[{col!r}]).dt.isocalendar().week",
        "month of year": f"pd.to_datetime(df[{col!r}]).dt.month",
        "year": f"pd.to_datetime(df[{col!r}]).dt.year",
        "quarter of year": f"pd.to_datetime(df[{col!r}]).dt.quarter",
        "hour": f"pd.to_datetime(df[{col!r}]).dt.hour",
        "minute": f"pd.to_datetime(df[{col!r}]).dt.minute",
        "second": f"pd.to_datetime(df[{col!r}]).dt.second",
    }

    arith_ops: dict[str, str] = {
        "add": "+",
        "subtract": "-",
        "multiply": "*",
        "divide": "/",
    }

    if method in simple_ops:
        expr = simple_ops[method]
        # floor/ceil need math import — swap the placeholder
        if method in ("floor", "ceil"):
            import_line = f"{_IND}import math"
            fn = "math.floor" if method == "floor" else "math.ceil"
            expr = expr.replace("import_floor", fn).replace("import_ceil", fn)
            return [
                import_line,
                f"{_IND}df[{col!r}] = df[{col!r}].apply({fn})",
            ]
        return [f"{_IND}df[{col!r}] = {expr}"]

    if method in arith_ops and values:
        op = arith_ops[method]
        fv = _fmt_val_py(values[0])
        return [f"{_IND}df[{col!r}] = df[{col!r}] {op} {fv}"]

    if method == "replace" and len(values) >= 2:
        old, new = values[0], values[1]
        return [
            f"{_IND}df[{col!r}] = df[{col!r}]"
            f".str.replace({old!r}, {new!r}, regex=False)"
        ]

    if method == "substring" and len(values) >= 2:
        start, end = int(values[0]), int(values[1])
        return [f"{_IND}df[{col!r}] = df[{col!r}].str[{start}:{end}]"]

    if method == "extract pattern" and values:
        return [
            f"{_IND}df[{col!r}] = df[{col!r}].str.extract(r{values[0]!r}, expand=False)"
        ]

    if method == "get dummies":
        return [f"{_IND}df = pd.get_dummies(df, columns=[{col!r}])"]

    return [f"{_IND}# NOTE: transform '{method}' on '{col}' could not be translated"]


def _py_add_column(args: dict, _desc: str) -> list[str]:
    new_col = args.get("column_names") or ""
    method = (args.get("method") or "").lower()
    src_cols = _cols(args)
    values = _val_list(args)

    if method == "constant":
        raw = values[0] if values else (args.get("value") or "")
        fv = _fmt_val_py(raw)
        return [f"{_IND}df[{new_col!r}] = {fv}"]

    if method == "index":
        return [f"{_IND}df[{new_col!r}] = range(len(df))"]

    if method == "uuid":
        return [
            f"{_IND}import hashlib",
            f"{_IND}df[{new_col!r}] = [",
            f"{_IND}    hashlib.sha256(str(i).encode()).hexdigest()",
            f"{_IND}    for i in range(len(df))",
            f"{_IND}]",
        ]

    if method == "random":
        return [
            f"{_IND}import random",
            f"{_IND}df[{new_col!r}] = [random.random() for _ in range(len(df))]",
        ]

    aggregations: dict[str, str] = {
        "sum": "sum",
        "mean": "mean",
        "median": "median",
        "min": "min",
        "max": "max",
        "std": "std",
        "var": "var",
        "count": "count",
        "nunique": "nunique",
        "product": "prod",
    }

    if method in aggregations and src_cols:
        fn = aggregations[method]
        return [f"{_IND}df[{new_col!r}] = df[{_col_list_py(src_cols)}].{fn}(axis=1)"]

    if method == "first" and src_cols:
        return [f"{_IND}df[{new_col!r}] = df[{src_cols[0]!r}]"]

    if method == "last" and src_cols:
        return [f"{_IND}df[{new_col!r}] = df[{src_cols[-1]!r}]"]

    if method == "diff" and len(src_cols) >= 2:
        return [f"{_IND}df[{new_col!r}] = df[{src_cols[0]!r}] - df[{src_cols[1]!r}]"]

    if method == "quotient" and len(src_cols) >= 2:
        return [f"{_IND}df[{new_col!r}] = df[{src_cols[0]!r}] / df[{src_cols[1]!r}]"]

    return [f"{_IND}# NOTE: add column '{new_col}' ({method}) could not be translated"]


# ---------------------------------------------------------------------------
# Stata emitters
# ---------------------------------------------------------------------------


def _stata_remove_columns(args: dict, _desc: str) -> list[str]:
    cols = _cols(args)
    return [f"drop {_col_list_stata(cols)}"]


def _stata_remove_rows(args: dict, _desc: str) -> list[str]:
    method = args.get("method", "")
    cols = _cols(args)
    condition = args.get("condition", "")
    values = _val_list(args)

    if method == _METH_BY_INDEX:
        idx_vals = [str(int(v)) for v in values if str(v).strip() not in (",", "")]
        return [f"drop in {','.join(idx_vals)}"]

    if not cols or not condition:
        return ["* NOTE: remove row step could not be translated"]

    col = cols[0]

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
        fv = _fmt_val_stata(values[0] if isinstance(values, list) else values)
        return [f"keep if {col} {op} {fv}"]

    return [f"* NOTE: condition '{condition}' could not be translated"]


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
        "string to date": f'gen {col}_date = date({col}, "DMY")  // adjust format',
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
        fv = _fmt_val_stata(values[0])
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

    return [f"* NOTE: transform '{method}' on '{col}' could not be translated"]


def _stata_add_column(args: dict, _desc: str) -> list[str]:
    new_col = args.get("column_names") or ""
    method = (args.get("method") or "").lower()
    src_cols = _cols(args)
    values = _val_list(args)

    if method == "constant":
        raw = values[0] if values else (args.get("value") or "")
        fv = _fmt_val_stata(raw)
        return [f"gen {new_col} = {fv}"]

    if method == "index":
        return [f"gen {new_col} = _n"]

    if method == "uuid":
        return [f"* NOTE: uuid column '{new_col}' — no direct Stata equivalent"]

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

    return [f"* NOTE: add column '{new_col}' ({method}) could not be translated"]


# ---------------------------------------------------------------------------
# R emitters
# ---------------------------------------------------------------------------


def _r_remove_columns(args: dict, _desc: str) -> list[str]:
    cols = _cols(args)
    col_str = _col_list_r(cols)
    return [f"  df <- df[, !names(df) %in% {col_str}]"]


def _r_remove_rows(args: dict, _desc: str) -> list[str]:
    method = args.get("method", "")
    cols = _cols(args)
    condition = args.get("condition", "")
    values = _val_list(args)

    if method == _METH_BY_INDEX:
        idx_vals = [
            str(int(v) + 1)  # R is 1-indexed
            for v in values
            if str(v).strip() not in (",", "")
        ]
        return [f"  df <- df[-c({', '.join(idx_vals)}), ]"]

    if not cols or not condition:
        return ["  # NOTE: remove row step could not be translated"]

    col = cols[0]

    if condition == _COND_MISSING:
        return [f"  df <- df[!is.na(df${col}), ]"]

    if condition == _COND_NOT_MISSING:
        return [f"  df <- df[is.na(df${col}), ]"]

    if condition in (_COND_LIKE, _COND_NOT_LIKE):
        pattern = values[0] if values else ""
        if condition == _COND_LIKE:
            return [f'  df <- df[!grepl("{pattern}", df${col}), ]']
        return [f'  df <- df[grepl("{pattern}", df${col}), ]']

    if condition in (_COND_BETWEEN, _COND_NOT_BETWEEN) and len(values) >= 2:
        lo, hi = values[0], values[1]
        if condition == _COND_BETWEEN:
            return [f"  df <- df[df${col} < {lo} | df${col} > {hi}, ]"]
        return [f"  df <- df[df${col} >= {lo} & df${col} <= {hi}, ]"]

    op = _KEEP_OP.get(condition)
    if op and values:
        fv = _fmt_val_r(values[0] if isinstance(values, list) else values)
        return [f"  df <- df[df${col} {op} {fv}, ]"]

    return [f"  # NOTE: condition '{condition}' could not be translated"]


def _r_transform_column(args: dict, _desc: str) -> list[str]:
    cols = _cols(args)
    method = (args.get("method") or "").lower()
    values = _val_list(args)
    col = cols[0] if cols else ""

    simple_r: dict[str, str] = {
        "trim": f"  df${col} <- trimws(df${col})",
        "lowercase": f"  df${col} <- tolower(df${col})",
        "uppercase": f"  df${col} <- toupper(df${col})",
        "absolute value": f"  df${col} <- abs(df${col})",
        "floor": f"  df${col} <- floor(df${col})",
        "ceil": f"  df${col} <- ceiling(df${col})",
        "round": f"  df${col} <- round(df${col}, 0)",
        "string to number": f"  df${col} <- as.numeric(df${col})",
        "string to date": f"  df${col} <- as.Date(df${col})  # adjust format",
        "string to datetime": (f"  df${col} <- as.POSIXct(df${col})  # adjust format"),
        "day of month": (f"  df${col} <- as.integer(format(as.Date(df${col}), '%d'))"),
        "day of week": (f"  df${col} <- as.integer(format(as.Date(df${col}), '%u'))"),
        "day of year": (f"  df${col} <- as.integer(format(as.Date(df${col}), '%j'))"),
        "week of year": (f"  df${col} <- as.integer(format(as.Date(df${col}), '%V'))"),
        "month of year": (f"  df${col} <- as.integer(format(as.Date(df${col}), '%m'))"),
        "year": (f"  df${col} <- as.integer(format(as.Date(df${col}), '%Y'))"),
        "quarter of year": (f"  library(lubridate)\n  df${col} <- quarter(df${col})"),
        "hour": f"  df${col} <- as.integer(format(as.POSIXct(df${col}), '%H'))",
        "minute": (f"  df${col} <- as.integer(format(as.POSIXct(df${col}), '%M'))"),
        "second": (f"  df${col} <- as.integer(format(as.POSIXct(df${col}), '%S'))"),
    }

    arith_ops: dict[str, str] = {
        "add": "+",
        "subtract": "-",
        "multiply": "*",
        "divide": "/",
    }

    if method in simple_r:
        return [simple_r[method]]

    if method in arith_ops and values:
        op = arith_ops[method]
        fv = _fmt_val_r(values[0])
        return [f"  df${col} <- df${col} {op} {fv}"]

    if method == "replace" and len(values) >= 2:
        old, new = values[0], values[1]
        return [f"  df${col} <- gsub({old!r}, {new!r}, df${col}, fixed = TRUE)"]

    if method == "substring" and len(values) >= 2:
        start, end = int(values[0]) + 1, int(values[1])  # R is 1-indexed
        length = end - (start - 1)
        return [f"  df${col} <- substr(df${col}, {start}, {start + length - 1})"]

    if method == "extract pattern" and values:
        pattern = values[0]
        return [f'  df${col} <- regmatches(df${col}, regexpr("{pattern}", df${col}))']

    if method == "get dummies":
        return [
            "  library(fastDummies)",
            f"  df <- dummy_cols(df, select_columns = {col!r},"
            "  remove_first_dummy = FALSE)",
        ]

    return [f"  # NOTE: transform '{method}' on '{col}' could not be translated"]


def _r_add_column(args: dict, _desc: str) -> list[str]:
    new_col = args.get("column_names") or ""
    method = (args.get("method") or "").lower()
    src_cols = _cols(args)
    values = _val_list(args)

    if method == "constant":
        raw = values[0] if values else (args.get("value") or "")
        fv = _fmt_val_r(raw)
        return [f"  df${new_col} <- {fv}"]

    if method == "index":
        return [f"  df${new_col} <- seq_len(nrow(df))"]

    if method == "uuid":
        return [
            "  library(uuid)",
            f"  df${new_col} <- replicate(nrow(df), UUIDgenerate())",
        ]

    if method == "random":
        return [f"  df${new_col} <- runif(nrow(df))"]

    agg_r: dict[str, str] = {
        "sum": "rowSums",
        "mean": "rowMeans",
        "min": "apply(df[, cols], 1, min)",
        "max": "apply(df[, cols], 1, max)",
        "std": "apply(df[, cols], 1, sd)",
        "var": "apply(df[, cols], 1, var)",
        "median": "apply(df[, cols], 1, median)",
        "product": "apply(df[, cols], 1, prod)",
    }

    if method in ("sum", "mean") and src_cols:
        fn = agg_r[method]
        return [f"  df${new_col} <- {fn}(df[, {_col_list_r(src_cols)}])"]

    if method in ("min", "max", "std", "var", "median", "product") and src_cols:
        fn_str = (
            agg_r[method]
            .replace("df[, cols]", f"df[, {_col_list_r(src_cols)}]")
            .replace("apply(", "apply(")
        )
        return [f"  df${new_col} <- {fn_str}"]

    if method in ("count", "nunique") and src_cols:
        fn = "length" if method == "count" else "length(unique"
        close = "" if method == "count" else ")"
        return [
            f"  df${new_col} <- apply("
            f"df[, {_col_list_r(src_cols)}], 1,"
            f" function(x) {fn}(na.omit(x)){close})"
        ]

    if method == "first" and src_cols:
        return [f"  df${new_col} <- df${src_cols[0]}"]

    if method == "last" and src_cols:
        return [f"  df${new_col} <- df${src_cols[-1]}"]

    if method == "diff" and len(src_cols) >= 2:
        return [f"  df${new_col} <- df${src_cols[0]} - df${src_cols[1]}"]

    if method == "quotient" and len(src_cols) >= 2:
        return [f"  df${new_col} <- df${src_cols[0]} / df${src_cols[1]}"]

    return [f"  # NOTE: add column '{new_col}' ({method}) could not be translated"]


# ---------------------------------------------------------------------------
# Dispatch tables
# ---------------------------------------------------------------------------

_PY_EMITTERS = {
    _ACT_REMOVE_COL: _py_remove_columns,
    _ACT_REMOVE_ROW: _py_remove_rows,
    _ACT_TRANSFORM: _py_transform_column,
    _ACT_ADD_COL: _py_add_column,
}

_STATA_EMITTERS = {
    _ACT_REMOVE_COL: _stata_remove_columns,
    _ACT_REMOVE_ROW: _stata_remove_rows,
    _ACT_TRANSFORM: _stata_transform_column,
    _ACT_ADD_COL: _stata_add_column,
}

_R_EMITTERS = {
    _ACT_REMOVE_COL: _r_remove_columns,
    _ACT_REMOVE_ROW: _r_remove_rows,
    _ACT_TRANSFORM: _r_transform_column,
    _ACT_ADD_COL: _r_add_column,
}

_LANG_EMITTERS = {"python": _PY_EMITTERS, "stata": _STATA_EMITTERS, "r": _R_EMITTERS}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_prepare_data_script(
    lang: str,
    prep_log: pl.DataFrame,
    project_name: str,
    survey_name: str,
    datasure_version: str,
) -> str:
    """Generate a prepare_data script from the prep log.

    Parameters
    ----------
    lang : str
        Target language: 'stata', 'r', or 'python'.
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
        Script content as a string.
    """
    h = _header(
        lang,
        "Data Preparation Script",
        project_name,
        survey_name,
        datasure_version,
    )
    c = _COMMENT[lang]
    emitters = _LANG_EMITTERS.get(lang, _PY_EMITTERS)

    if prep_log.is_empty():
        return h + f"{c} No preparation steps recorded.\n"

    lines: list[str] = [h]

    if lang == "python":
        lines += [
            "import pandas as pd",
            "",
            "",
            "def prepare_data(df: 'pd.DataFrame') -> 'pd.DataFrame':",
            '    """Apply all recorded preparation steps."""',
            "    df = df.copy()",
            "",
        ]
    elif lang == "r":
        lines += [
            "library(readr)",
            "",
            "prepare_data <- function(df) {",
            "",
        ]

    for i, row in enumerate(prep_log.iter_rows(named=True), start=1):
        action = str(row.get("action") or "")
        description = str(row.get("description") or "")
        raw_args = row.get("prep_args") or "{}"

        # Parse prep_args JSON
        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args)
            except json.JSONDecodeError:
                # Fallback for Python-literal encoded strings
                try:
                    import ast

                    args = ast.literal_eval(raw_args)
                except Exception:
                    args = {}
        elif isinstance(raw_args, dict):
            args = raw_args
        else:
            args = {}

        # Comment line
        comment_line = f"{c} Step {i}: {description or action}"
        if lang in ("python", "r"):
            indent_c = "    " if lang == "python" else "  "
            comment_line = f"{indent_c}{c} Step {i}: {description or action}"

        lines.append(comment_line)

        emitter = emitters.get(action)
        if emitter:
            lines.extend(emitter(args, description))
        else:
            fallback = (
                f"{_IND}# NOTE: unknown action '{action}'"
                if lang == "python"
                else f"  # NOTE: unknown action '{action}'"
                if lang == "r"
                else f"* NOTE: unknown action '{action}'"
            )
            lines.append(fallback)

        lines.append("")

    if lang == "python":
        lines += ["    return df", ""]
    elif lang == "r":
        lines += ["  return(df)", "}", ""]

    return "\n".join(lines)
