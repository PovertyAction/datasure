"""Python/Polars script generator for replication packages.

Translates the prep log (recorded in the Prepare Data section) into a
reproducible, standalone Polars script. Unlike the Stata translation in
``prep_script_generator.py`` (which approximates some operations because
Stata has no direct equivalent), this generator mirrors the real semantics
implemented in ``datasure.processing.prep`` as closely as possible — e.g.
transforms overwrite the source column in place, row-removal conditions
support multiple source columns, ``get dummies`` and ``uuid`` translate
directly instead of falling back to a "could not be translated" note.
"""

from __future__ import annotations

import polars as pl

from datasure.replication.prep_script_generator import (
    _ACT_ADD_COL,
    _ACT_REDACT_COL,
    _ACT_REMOVE_COL,
    _ACT_REMOVE_ROW,
    _ACT_TRANSFORM,
    _COND_BETWEEN,
    _COND_EQ,
    _COND_GT,
    _COND_GTE,
    _COND_LIKE,
    _COND_LT,
    _COND_LTE,
    _COND_MISSING,
    _COND_NEQ,
    _COND_NOT_BETWEEN,
    _COND_NOT_LIKE,
    _COND_NOT_MISSING,
    _METH_BY_INDEX,
    _cols,
    _parse_prep_args,
    _val_list,
)
from datasure.replication.py_script_generators import _py_header, _safe_survey

# ---------------------------------------------------------------------------
# Embedded helper for "string to date"/"string to datetime" transforms.
# Mirrors TransformColumnsOperation._parse_flexible_datetime in prep.py.
# Only included in the generated script when actually needed.
# ---------------------------------------------------------------------------

_DATETIME_HELPER_SRC = r'''
def _parse_flexible_datetime(frame: pl.DataFrame, col_name: str) -> pl.Expr:
    """Try multiple datetime formats and return the first that matches."""
    formats_to_try = [
        {"format": "%d%b%Y %H:%M:%S", "validator": r"^\d{1,2}[a-zA-Z]{3}\d{4} \d{2}:\d{2}:\d{2}$"},
        {"format": "%d-%b-%Y %H:%M:%S", "validator": r"^\d{1,2}-[a-zA-Z]{3}-\d{4} \d{2}:\d{2}:\d{2}$"},
        {"format": "%Y-%m-%d %H:%M:%S", "validator": r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$"},
        {"format": "%m/%d/%Y %H:%M:%S", "validator": r"^\d{1,2}/\d{1,2}/\d{4} \d{2}:\d{2}:\d{2}$"},
        {"format": "%d/%m/%Y %H:%M:%S", "validator": r"^\d{1,2}/\d{1,2}/\d{4} \d{2}:\d{2}:\d{2}$"},
        {"format": "%Y-%m-%d", "validator": r"^\d{4}-\d{2}-\d{2}$"},
        {"format": "%m/%d/%Y", "validator": r"^\d{1,2}/\d{1,2}/\d{4}$"},
        {"format": "%d-%m-%Y", "validator": r"^\d{1,2}-\d{1,2}-\d{4}$"},
    ]
    for fmt in formats_to_try:
        validator = fmt["validator"]
        ok = (
            frame.filter(pl.col(col_name).is_not_null())
            .select(pl.col(col_name).str.contains(f"^{validator.strip('^$')}$").all())
            .item()
        )
        if ok:
            return pl.col(col_name).str.to_datetime(format=fmt["format"], strict=False)
    raise ValueError(f"Failed to parse datetime for column '{col_name}'.")
'''

# ---------------------------------------------------------------------------
# Row-removal condition translation (mirrors RemoveRowsOperation._filter_by_*)
# ---------------------------------------------------------------------------


def _drop_by_index_py(values: list) -> list[str]:
    row_indices: list[int] = []
    for item in values:
        if item in (",", None):
            continue
        text = str(item)
        if ":" in text:
            start, end = text.split(":")
            row_indices.extend(range(int(start), int(end) + 1))
        else:
            row_indices.append(int(item))

    if not row_indices:
        return ["# NOTE: no row indices provided for drop"]

    return [
        'df = df.with_row_index("__row_idx__")',
        f'df = df.filter(~pl.col("__row_idx__").is_in({row_indices!r})).drop("__row_idx__")',
    ]


def _drop_by_condition_py(cols: list[str], condition: str, values: list) -> list[str]:
    cols_src = repr(cols)

    if condition == _COND_MISSING:
        return [f"df = df.filter(~pl.any_horizontal(pl.col({cols_src}).is_null()))"]
    if condition == _COND_NOT_MISSING:
        return [f"df = df.filter(pl.any_horizontal(pl.col({cols_src}).is_null()))"]

    if condition in (_COND_EQ, _COND_NEQ):
        value_list = values if isinstance(values, list) else [values]
        expr = (
            f"pl.any_horizontal([pl.col(c).is_in({value_list!r}) for c in {cols_src}])"
        )
        return [
            f"df = df.filter({'~(' + expr + ')' if condition == _COND_NEQ else expr})"
        ]

    if condition in (_COND_GT, _COND_GTE, _COND_LT, _COND_LTE):
        if not values:
            return ["# NOTE: comparison condition is missing a value"]
        raw_value = values[0] if isinstance(values, list) else values
        op = {_COND_GT: "<=", _COND_GTE: "<", _COND_LT: ">=", _COND_LTE: ">"}[condition]
        value_use = float(raw_value)
        return [
            "df = df.filter(pl.any_horizontal("
            f"[pl.col(c) {op} {value_use!r} for c in {cols_src}]))"
        ]

    if condition in (_COND_BETWEEN, _COND_NOT_BETWEEN):
        value_list = values if isinstance(values, list) else [values, values]
        if len(value_list) != 2:
            return ["# NOTE: between condition requires exactly two values"]
        lo, hi = value_list
        if condition == _COND_BETWEEN:
            expr = (
                "pl.any_horizontal([(pl.col(c) < "
                f"{lo!r}) | (pl.col(c) > {hi!r}) for c in {cols_src}])"
            )
        else:
            expr = (
                "pl.any_horizontal([(pl.col(c) >= "
                f"{lo!r}) & (pl.col(c) <= {hi!r}) for c in {cols_src}])"
            )
        return [f"df = df.filter({expr})"]

    if condition in (_COND_LIKE, _COND_NOT_LIKE):
        pattern = values[0] if values else ""
        if condition == _COND_LIKE:
            expr = (
                f"pl.all_horizontal([~pl.col(c).str.contains({pattern!r}) "
                f"for c in {cols_src}])"
            )
        else:
            expr = (
                f"pl.any_horizontal([pl.col(c).str.contains({pattern!r}) "
                f"for c in {cols_src}])"
            )
        return [f"df = df.filter({expr})"]

    return [f"# NOTE: condition {condition!r} could not be translated"]


def _py_remove_columns(args: dict, _desc: str) -> list[str]:
    cols = _cols(args)
    return [f"df = df.drop({cols!r})"]


def _py_redact_columns(args: dict, _desc: str) -> list[str]:
    """Mask every value in the given columns with its redaction label."""
    cols = _cols(args)
    method = (args.get("method") or "mask").lower()

    if method in ("hash", "code"):
        # The project salt / code maps live only in DataSure's local cache
        # and are never exported, so this step cannot be re-derived here.
        # De-identified exports already carry the tokens in the bundled raw
        # dataset (the transformation is inherited on replay); with-PII
        # exports include 5_deidentify_data.py for consistent pseudonyms.
        return [
            f"# NOTE: {method!r} redaction of {cols!r} was applied in DataSure",
            "# and cannot be reproduced here; exported datasets already carry",
            "# the pseudonym tokens.",
        ]

    labels = args.get("value") or []
    if isinstance(labels, str):
        labels = [labels] * len(cols)
    if len(labels) != len(cols):
        labels = ["*****"] * len(cols)

    lines: list[str] = []
    for col, label in zip(cols, labels, strict=True):
        lines.append(
            f"df = df.with_columns(pl.when(pl.col({col!r}).is_not_null())"
            f".then(pl.lit({label!r}))"
            f".otherwise(pl.lit(None, dtype=pl.String)).alias({col!r}))"
        )
    return lines


def _py_remove_rows(args: dict, _desc: str) -> list[str]:
    method = args.get("method", "")
    cols = _cols(args)
    condition = args.get("condition", "")
    values = _val_list(args)

    if method == _METH_BY_INDEX:
        return _drop_by_index_py(values)

    if not cols or not condition:
        return ["# NOTE: remove row step could not be translated"]

    return _drop_by_condition_py(cols, condition, values)


# ---------------------------------------------------------------------------
# Transform-column translation (mirrors TransformColumnsOperation)
# ---------------------------------------------------------------------------

_DATETIME_EXTRACT_PY = {
    "day of month": "dt.day()",
    "day of week": "dt.weekday()",
    "day of year": "dt.ordinal_day()",
    "date": "dt.date()",
    "week of year": "dt.week()",
    "month of year": "dt.month()",
    "year": "dt.year()",
    "quarter of year": "dt.quarter()",
    "hour": "dt.hour()",
    "minute": "dt.minute()",
    "second": "dt.second()",
}

_MATH_OPS_PY = {
    "floor": "floor()",
    "ceil": "ceil()",
    "round": "round(0)",
    "absolute value": "abs()",
}

_STRING_OPS_PY = {
    "trim": "str.strip_chars()",
    "lowercase": "str.to_lowercase()",
    "uppercase": "str.to_uppercase()",
}

_ARITH_OPS_PY = {"add": "+", "subtract": "-", "multiply": "*", "divide": "/"}


def _uses_datetime_helper(method: str) -> bool:
    return method in ("string to date", "string to datetime")


def _py_transform_column(args: dict, _desc: str) -> list[str]:
    cols = _cols(args)
    method = (args.get("method") or "").lower()
    values = _val_list(args)
    col = cols[0] if cols else ""
    col_src = repr(col)

    if method in _DATETIME_EXTRACT_PY:
        return [
            f"df = df.with_columns(pl.col({col_src})"
            f".{_DATETIME_EXTRACT_PY[method]}.alias({col_src}))"
        ]

    if method in _MATH_OPS_PY:
        return [
            f"df = df.with_columns(pl.col({col_src})"
            f".{_MATH_OPS_PY[method]}.alias({col_src}))"
        ]

    if method in _STRING_OPS_PY:
        return [
            f"df = df.with_columns(pl.col({col_src})"
            f".{_STRING_OPS_PY[method]}.alias({col_src}))"
        ]

    if method == "string to number":
        return [
            f"df = df.with_columns(pl.col({col_src})"
            f".cast(pl.Float64, strict=False).alias({col_src}))"
        ]

    if method in _ARITH_OPS_PY and values:
        op = _ARITH_OPS_PY[method]
        return [
            f"df = df.with_columns((pl.col({col_src}) {op} {values[0]!r})"
            f".alias({col_src}))"
        ]

    if _uses_datetime_helper(method):
        return [
            f"df = df.with_columns(_parse_flexible_datetime(df, {col_src}).alias({col_src}))"
        ]

    if method == "get dummies":
        return [f"df = df.to_dummies(columns=[{col_src}])"]

    if method.startswith("replace by replacing") and len(values) >= 2:
        old, new = values[0], values[1]
        return [
            f"df = df.with_columns(pl.col({col_src})"
            f".str.replace({old!r}, {new!r}).alias({col_src}))"
        ]

    if method == "substring" and len(values) >= 2:
        start, end = int(values[0]), int(values[1])
        return [
            f"df = df.with_columns(pl.col({col_src})"
            f".str.slice({start}, {end - start}).alias({col_src}))"
        ]

    if method.startswith("extract pattern") and values:
        pattern = values[0]
        return [
            f"df = df.with_columns(pl.col({col_src})"
            f".str.extract({pattern!r}).alias({col_src}))"
        ]

    return [f"# NOTE: transform {method!r} on {col!r} could not be translated"]


# ---------------------------------------------------------------------------
# Add-column translation (mirrors AddNewColumnOperation)
# ---------------------------------------------------------------------------

_AGG_FUNCS_PY = {
    "sum": lambda c: f"pl.sum_horizontal({c!r})",
    "mean": lambda c: f"pl.mean_horizontal({c!r})",
    "median": lambda c: f"pl.concat_list({c!r}).list.median()",
    "max": lambda c: f"pl.max_horizontal({c!r})",
    "min": lambda c: f"pl.min_horizontal({c!r})",
    "std": lambda c: f"pl.concat_list({c!r}).list.std()",
    "var": lambda c: f"pl.concat_list({c!r}).list.var()",
    "first": lambda c: f"pl.concat_list({c!r}).list.first()",
    "last": lambda c: f"pl.concat_list({c!r}).list.last()",
    "count": lambda c: f"pl.concat_list({c!r}).list.len()",
    "nunique": lambda c: f"pl.concat_list({c!r}).list.unique().list.len()",
    "product": lambda c: (
        f"pl.fold(acc=pl.lit(1), function=lambda acc, x: acc * x, exprs={c!r})"
    ),
}


def _py_add_constant_column(new_col_src: str, values: list, args: dict) -> list[str]:
    raw = values[0] if values else (args.get("value") or "")
    if isinstance(raw, str):
        try:
            lit_val: object = float(raw) if "." in raw else int(raw)
        except ValueError:
            lit_val = raw
    else:
        lit_val = raw
    return [f"df = df.with_columns(pl.lit({lit_val!r}).alias({new_col_src}))"]


def _py_add_special_column(method: str, new_col_src: str, seed: str) -> list[str]:
    if method == "index":
        return [f"df = df.with_row_index({new_col_src})"]

    if method == "random":
        return [
            "import random",
            "df = df.with_columns(",
            "    pl.Series([random.random() for _ in range(df.height)])",
            f"    .alias({new_col_src})",
            ")",
        ]

    if method == "uuid":
        return [
            "import hashlib",
            'df = df.with_row_index("__idx__")',
            "df = df.with_columns(",
            '    pl.col("__idx__")',
            "    .map_elements(",
            "        lambda idx: hashlib.sha256("
            f"({seed!r} + '_' + str(idx)).encode()"
            ").hexdigest(),",
            "        return_dtype=pl.Utf8,",
            "    )",
            f"    .alias({new_col_src})",
            ")",
            'df = df.drop("__idx__")',
            "# NOTE: uuid values are seeded on the survey name (DataSure's",
            "# internal project id isn't available outside the app), so exact",
            "# hash values will differ from the in-app output.",
        ]

    return [f"# NOTE: add column method {method!r} could not be translated"]


def _py_add_column(args: dict, _desc: str, seed: str = "") -> list[str]:
    new_col = args.get("column_names") or ""
    method = (args.get("method") or "").lower()
    src_cols = _cols(args)
    values = _val_list(args)
    new_col_src = repr(new_col)

    if method == "constant":
        return _py_add_constant_column(new_col_src, values, args)

    if method in ("index", "uuid", "random"):
        return _py_add_special_column(method, new_col_src, seed)

    if method in _AGG_FUNCS_PY and src_cols:
        expr = _AGG_FUNCS_PY[method](src_cols)
        return [f"df = df.with_columns(({expr}).alias({new_col_src}))"]

    if method in ("quotient", "diff") and len(src_cols) == 2:
        op = "/" if method == "quotient" else "-"
        return [
            f"df = df.with_columns((pl.col({src_cols[0]!r}) {op} "
            f"pl.col({src_cols[1]!r})).alias({new_col_src}))"
        ]

    return [f"# NOTE: add column {new_col!r} ({method!r}) could not be translated"]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_prepare_data_script_py(
    prep_log: pl.DataFrame,
    project_name: str,
    survey_name: str,
    datasure_version: str,
) -> str:
    """Generate a Python prepare_data script from the prep log.

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
        Python script content as a string.
    """
    header = _py_header(
        "Data Preparation Script (Python)",
        project_name,
        survey_name,
        datasure_version,
        ["polars"],
    )
    safe_survey = _safe_survey(survey_name)

    preamble = [
        header,
        "from pathlib import Path",
        "",
        "import polars as pl",
        "",
        "PKG_ROOT = Path(__file__).resolve().parents[1]",
        f'RAW = PKG_ROOT / "3_data" / "1_raw" / "{safe_survey}_raw.parquet"',
        f'OUT = PKG_ROOT / "3_data" / "2_intermediate" / "{safe_survey}_prepped.parquet"',
        "",
    ]

    if prep_log.is_empty():
        lines = [
            *preamble,
            "df = pl.read_parquet(RAW)",
            "# No preparation steps recorded.",
            "df.write_parquet(OUT)",
            'print(f"Wrote {OUT} — {df.height:,} rows")',
        ]
        return "\n".join(lines) + "\n"

    steps = []
    needs_datetime_helper = False
    for i, row in enumerate(prep_log.iter_rows(named=True), start=1):
        action = str(row.get("action") or "")
        description = str(row.get("description") or "")
        args = _parse_prep_args(row.get("prep_args") or "{}")
        if action == _ACT_TRANSFORM and _uses_datetime_helper(
            (args.get("method") or "").lower()
        ):
            needs_datetime_helper = True
        steps.append((i, action, description, args))

    lines = list(preamble)
    if needs_datetime_helper:
        lines.append(_DATETIME_HELPER_SRC)

    lines += ["df = pl.read_parquet(RAW)", ""]

    for i, action, description, args in steps:
        lines.append(f"# Step {i}: {description or action}")
        if action == _ACT_REMOVE_COL:
            lines += _py_remove_columns(args, description)
        elif action == _ACT_REMOVE_ROW:
            lines += _py_remove_rows(args, description)
        elif action == _ACT_TRANSFORM:
            lines += _py_transform_column(args, description)
        elif action == _ACT_ADD_COL:
            lines += _py_add_column(args, description, seed=survey_name)
        elif action == _ACT_REDACT_COL:
            lines += _py_redact_columns(args, description)
        else:
            lines.append(f"# NOTE: unknown action {action!r}")
        lines.append("")

    lines += ["df.write_parquet(OUT)", 'print(f"Wrote {OUT} — {df.height:,} rows")']
    return "\n".join(lines) + "\n"
