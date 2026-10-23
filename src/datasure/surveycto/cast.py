"""Cast all-string wide JSON rows into a typed Arrow table through the contract.

Empty strings and absent keys are null. A select_multiple comes as per-choice
binaries present only when chosen (one the export leaves as a single column of
codes is split into them): within one field (and one repeat instance), an
unchosen binary is 0 when any sibling was chosen, else null; every choice gets
its column, except where the form filters the list per submission: there only
the choices someone picked at that instance do, since an unoffered choice is not
unchosen. A column that cannot be typed (a value that does not parse, a column
the form does not define) is kept as text, with the reason in its
``cast_fallback`` field metadata; the reason never quotes a value. A form with
no submissions yet has the columns every submission carries
(``SUBMISSION_COLUMNS``). A note's or a group's column empty in every row is
dropped (the export writes field-list groups once per repeat instance), and the
table's metadata counts them.
"""

import datetime as dt
import json
import re
from dataclasses import dataclass

import pyarrow as pa

from datasure.surveycto.xml_contract import (
    FormContract,
    Node,
    is_system_column,
    sanitize_choice_value,
)

_TIMESTAMP = pa.timestamp("ms", tz="UTC")
# Table metadata: how many note and group columns, empty in every row, were dropped.
DROPPED = "empty_notes_and_groups_dropped"
_SYSTEM_TIMESTAMPS = {"SubmissionDate", "CompletionDate", "starttime", "endtime"}
_SYSTEM_INTS = {"duration"}
# The columns the server writes on every submission, whatever the form: a form with
# no submissions yet has these alone.
SUBMISSION_COLUMNS = ("KEY", "SubmissionDate", "formdef_version")

_XML_TYPES = {
    "int": pa.int64(),
    "decimal": pa.float64(),
    "date": pa.date32(),
    "dateTime": _TIMESTAMP,
    "string": pa.string(),
    "select1": pa.string(),  # integer-coded selects become int64 (_select_one_type)
    "select": pa.string(),
    "binary": pa.string(),  # attachment URL
    # Text by nature: coordinates separated by spaces and ";", a time with its offset.
    "geopoint": pa.string(),
    "geotrace": pa.string(),
    "geoshape": pa.string(),
    "time": pa.string(),
}


@dataclass
class _Column:
    name: str
    arrow_type: pa.DataType
    metadata: dict[str, str]
    sort_key: tuple
    binary_group: tuple | None = (
        None  # (node path, repeat iterations) of a choice binary
    )
    # A note's or a group's column, which holds no answer: dropped when empty.
    structural: bool = False


def _parse_timestamp(value: str) -> dt.datetime:
    # The REST API returns UTC, e.g. "Mar 7, 2025 4:06:12 PM".
    return dt.datetime.strptime(value, "%b %d, %Y %I:%M:%S %p").replace(tzinfo=dt.UTC)


def _parse_date(value: str) -> dt.date:
    return dt.datetime.strptime(value, "%b %d, %Y").date()


def _parse_binary(value: str) -> int:
    if value != "1":
        raise ValueError("a chosen select_multiple binary is '1'")
    return 1


# The numbers the server writes: ASCII digits, an optional minus, and for a decimal
# a fraction and the exponent Java writes for large and small values ("1.0E-4"). The
# rest of what int() and float() accept ("1_0", "nan", " 3 ") is text.
_INT = re.compile(r"-?[0-9]+")
_DECIMAL = re.compile(r"-?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][-+]?[0-9]+)?")


def _parse_int(value: str) -> int:
    if not _INT.fullmatch(value):
        raise ValueError("not an integer")
    return int(value)


def _parse_decimal(value: str) -> float:
    if not _DECIMAL.fullmatch(value):
        raise ValueError("not a decimal")
    return float(value)


_PARSERS = {
    pa.int64(): _parse_int,
    pa.float64(): _parse_decimal,
    pa.date32(): _parse_date,
    _TIMESTAMP: _parse_timestamp,
    pa.string(): str,
    pa.int8(): _parse_binary,
}


_INTEGER_CODE = re.compile(r"-?(0|[1-9][0-9]*)")


def _select_one_type(node: Node) -> pa.DataType:
    """Return int64 when every choice code is a plain integer, else string.

    A code with a leading zero ("01") or letters ("yes") keeps the column as text, so
    no code changes meaning.
    """
    codes = [str(c["value"]) for c in node.all_choices]
    if codes and all(_INTEGER_CODE.fullmatch(code) for code in codes):
        return pa.int64()
    return pa.string()


def _node_metadata(node: Node) -> dict[str, str]:
    return {
        "xml_type": node.xml_type or "",
        "node_path": node.path,
        "repeat_path": json.dumps(node.repeat_path),
    }


def _text(
    name: str, reason: str, metadata: dict[str, str], sort_key: tuple, **kw
) -> _Column:
    return _Column(
        name, pa.string(), {**metadata, "cast_fallback": reason}, sort_key, **kw
    )


def _binary_name(node: Node, code: str, iterations: tuple[int, ...]) -> str:
    suffix = "".join(f"_{i}" for i in iterations)
    return f"{node.name}_{sanitize_choice_value(code)}{suffix}"


def _columns(names: list[str], contract: FormContract) -> list[_Column]:
    """Resolve every column, adding the binaries of choices nobody picked."""
    order = {path: i for i, path in enumerate(contract.nodes)}
    columns: dict[str, _Column] = {}
    multi_instances: dict[str, set[tuple[int, ...]]] = {}
    picked: dict[tuple[str, tuple[int, ...]], set[str]] = {}
    codes_of: dict[str, set[str]] = {}
    for position, name in enumerate(names):
        if is_system_column(name):
            arrow_type = (
                _TIMESTAMP
                if name in _SYSTEM_TIMESTAMPS
                else pa.int64()
                if name in _SYSTEM_INTS
                else pa.string()
            )
            rank = -1 if name == "KEY" else position
            columns[name] = _Column(name, arrow_type, {"system": "true"}, (0, rank))
            continue
        m = contract.map_column(name)
        if m["kind"] != "matched":
            columns[name] = _text(name, "maps to no form field", {}, (2, position))
            continue
        node = contract.nodes[m["node_path"]]
        iterations = tuple(i for _, i in m["repeat_iterations"])
        key = (1, order[node.path], iterations, 0)
        if not node.is_leaf:
            columns[name] = _text(
                name, f"maps to group {node.path!r}", {}, key, structural=True
            )
            continue
        if node.is_select_multiple and m["choice_code"] is not None:
            multi_instances.setdefault(node.path, set()).add(iterations)
            picked.setdefault((node.path, iterations), set()).add(str(m["choice_code"]))
            if node.path not in codes_of:
                codes_of[node.path] = {str(c["value"]) for c in node.all_choices}
            codes = codes_of[node.path]
            if str(m["choice_code"]) not in codes:
                columns[name] = _text(
                    name,
                    "a choice code not among the form's choices",
                    _node_metadata(node),
                    (*key[:3], len(node.all_choices)),
                    binary_group=(node.path, iterations),
                )
            continue
        if node.xml_type not in _XML_TYPES:
            columns[name] = _text(
                name,
                f"no Arrow type for xml_type {node.xml_type!r}",
                _node_metadata(node),
                key,
            )
            continue
        arrow_type = (
            _select_one_type(node)
            if node.xml_type == "select1"
            else _XML_TYPES[node.xml_type]
        )
        columns[name] = _Column(
            name,
            arrow_type,
            _node_metadata(node),
            key,
            structural=node.original == "note",
        )

    for path, instances in multi_instances.items():
        node = contract.nodes[path]
        if not node.repeat_path:
            instances = {()}
        for iterations in instances:
            for index, item in enumerate(node.all_choices):
                if (
                    node.choices_per_submission
                    and str(item["value"]) not in picked[path, iterations]
                ):
                    continue
                name = _binary_name(node, item["value"], iterations)
                m = contract.map_column(name)
                if m["kind"] != "matched" or m["node_path"] != path:
                    raise RuntimeError(
                        f"choice binary {name!r} does not map back to {path!r}"
                    )
                columns[name] = _Column(
                    name,
                    pa.int8(),
                    {**_node_metadata(node), "choice_value": str(item["value"])},
                    (1, order[path], iterations, index),
                    binary_group=(path, iterations),
                )
    return sorted(columns.values(), key=lambda c: c.sort_key)


def _cast(
    column: _Column, raw: list[str], answered: list[bool]
) -> tuple[pa.Array, _Column]:
    """Return the typed array, or the text array and its fallback column."""
    parse = _PARSERS[column.arrow_type]
    binary = column.arrow_type == pa.int8()
    values, failed = [], 0
    for value, was_answered in zip(raw, answered, strict=True):
        if value == "":
            values.append(0 if was_answered and binary else None)
            continue
        try:
            values.append(parse(value))
        except ValueError:
            failed += 1
    if not failed:
        return pa.array(values, type=column.arrow_type), column
    reason = f"{failed} of {sum(v != '' for v in raw)} values do not parse as {column.arrow_type}"
    text = _text(column.name, reason, column.metadata, column.sort_key)
    return pa.array([v or None for v in raw], type=pa.string()), text


def _split_raw_multiples(rows: list[dict], contract: FormContract) -> list[dict]:
    """Return ``rows`` with each select_multiple exported raw (one column, the codes
    separated by spaces) rewritten as its per-choice binaries, as the export writes
    the others. The contract resolves each column, since a select's own name can end
    in ``_<digits>`` like a repeat instance.
    """
    raw: dict[str, tuple[Node, tuple[int, ...]]] = {}
    for name in dict.fromkeys(name for row in rows for name in row):
        if is_system_column(name):
            continue
        m = contract.map_column(name)
        if m["kind"] != "matched" or m["choice_code"] is not None or m.get("ragged"):
            continue
        node = contract.nodes[m["node_path"]]
        if node.is_select_multiple and node.is_leaf:
            raw[name] = (node, tuple(i for _, i in m["repeat_iterations"]))
    if not raw:
        return rows
    split = []
    for row in rows:
        row = dict(row)
        for name, (node, iterations) in raw.items():
            for code in row.pop(name, "").split():
                row[_binary_name(node, code, iterations)] = "1"
        split.append(row)
    return split


def cast_wide(rows: list[dict], contract: FormContract) -> pa.Table:
    """Return the submissions as a typed table: system columns, then form order."""
    rows = _split_raw_multiples(rows, contract)
    names = list(dict.fromkeys(name for row in rows for name in row))
    if not rows:
        names = list(SUBMISSION_COLUMNS)
    columns = _columns(names, contract)
    groups: dict[tuple, list[str]] = {}
    for c in columns:
        if c.binary_group is not None:
            groups.setdefault(c.binary_group, []).append(c.name)

    # Per binary group: whether each row answered the select_multiple.
    answered_by_group = {
        group: [any(row.get(s, "") != "" for s in siblings) for row in rows]
        for group, siblings in groups.items()
    }
    unanswered = [False] * len(rows)
    arrays, fields = [], []
    dropped = 0
    for c in columns:
        raw = [row.get(c.name, "") for row in rows]
        answered = answered_by_group.get(c.binary_group, unanswered)
        array, c = _cast(c, raw, answered)
        if c.structural and array.null_count == len(array):
            dropped += 1
            continue
        arrays.append(array)
        fields.append(pa.field(c.name, c.arrow_type, metadata=c.metadata))
    schema = pa.schema(fields, metadata={DROPPED: str(dropped)})
    return pa.Table.from_arrays(arrays, schema=schema)
