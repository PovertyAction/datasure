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
from dataclasses import dataclass, field

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
    no code changes meaning. A `search()` select whose dataset codes are unknown
    stays text, since its literal extras alone say nothing about them.
    """
    if not node.choices_known:
        return pa.string()
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


@dataclass
class _Picks:
    """The choice binaries the columns name, per select_multiple and repeat instance."""

    # select_multiple path -> the repeat instances its binaries appear in.
    instances: dict[str, set[tuple[int, ...]]] = field(default_factory=dict)
    # (select_multiple path, repeat instance) -> the codes picked there.
    chosen: dict[tuple[str, tuple[int, ...]], set[str]] = field(default_factory=dict)
    codes: dict[str, set[str]] = field(default_factory=dict)

    def add(self, node: Node, iterations: tuple[int, ...], code: str) -> bool:
        """Record a picked code; return False when the form's choices lack it.

        A search() select's dataset codes are not in the form: any code goes.
        """
        self.instances.setdefault(node.path, set()).add(iterations)
        self.chosen.setdefault((node.path, iterations), set()).add(code)
        if node.path not in self.codes:
            self.codes[node.path] = {str(c["value"]) for c in node.all_choices}
        return not node.choices_known or code in self.codes[node.path]


def _system_type(name: str) -> pa.DataType:
    """Return a system column's Arrow type."""
    if name in _SYSTEM_TIMESTAMPS:
        return _TIMESTAMP
    if name in _SYSTEM_INTS:
        return pa.int64()
    return pa.string()


def _columns(
    names: list[str],
    contract: FormContract,
    raw_instances: set[tuple[str, tuple[int, ...]]] = frozenset(),
) -> list[_Column]:
    """Resolve every column, adding the binaries of choices nobody picked.

    ``raw_instances`` are the (select path, repeat instance) of select_multiples
    exported raw: each gets its binaries even when nobody picked a choice there,
    so an unanswered question shows as missing instead of disappearing.
    """
    order = {path: i for i, path in enumerate(contract.nodes)}
    columns: dict[str, _Column] = {}
    picks = _Picks()
    for path, iterations in raw_instances:
        picks.instances.setdefault(path, set()).add(iterations)
    for position, name in enumerate(names):
        column = _column(name, position, contract, order, picks)
        if column is not None:
            columns[name] = column

    for path, instances in picks.instances.items():
        node = contract.nodes[path]
        for iterations in instances if node.repeat_path else {()}:
            chosen = picks.chosen.get((path, iterations), set())
            for column in _binary_columns(contract, node, iterations, chosen, order):
                columns[column.name] = column
    return sorted(columns.values(), key=lambda c: c.sort_key)


def _column(
    name: str,
    position: int,
    contract: FormContract,
    order: dict[str, int],
    picks: _Picks,
) -> _Column | None:
    """Resolve one column, or record a choice binary in ``picks`` and return None.

    A recorded binary's column is built with its siblings in `_binary_columns`.
    """
    if is_system_column(name):
        rank = -1 if name == "KEY" else position
        return _Column(name, _system_type(name), {"system": "true"}, (0, rank))
    m = contract.map_column(name)
    if m["kind"] != "matched":
        return _text(name, "maps to no form field", {}, (2, position))
    node = contract.nodes[m["node_path"]]
    iterations = tuple(i for _, i in m["repeat_iterations"])
    key = (1, order[node.path], iterations, 0)
    if not node.is_leaf:
        return _text(name, f"maps to group {node.path!r}", {}, key, structural=True)
    if m.get("ambiguous_choice"):
        reason = "a choice binary whose choice is ambiguous"
        return _text(name, reason, _node_metadata(node), key)
    if node.is_select_multiple and m["choice_code"] is not None:
        if picks.add(node, iterations, str(m["choice_code"])):
            return None
        return _text(
            name,
            "a choice code not among the form's choices",
            _node_metadata(node),
            (*key[:3], len(node.all_choices)),
            binary_group=(node.path, iterations),
        )
    return _answer_column(name, node, key)


def _answer_column(name: str, node: Node, key: tuple) -> _Column:
    """Return the column of a field's own answer, typed by its bind."""
    if node.xml_type not in _XML_TYPES:
        reason = f"no Arrow type for xml_type {node.xml_type!r}"
        return _text(name, reason, _node_metadata(node), key)
    # A select_one control can sit on a `select1` or a `string` bind.
    is_select_one = node.xml_type == "select1" or node.control == "select_one"
    arrow_type = _select_one_type(node) if is_select_one else _XML_TYPES[node.xml_type]
    return _Column(
        name,
        arrow_type,
        _node_metadata(node),
        key,
        structural=node.original == "note",
    )


def _binary_columns(
    contract: FormContract,
    node: Node,
    iterations: tuple[int, ...],
    chosen: set[str],
    order: dict[str, int],
) -> list[_Column]:
    """Return a select_multiple's choice binaries in one repeat instance."""
    values = [str(item["value"]) for item in node.all_choices]
    if not node.choices_known:
        # The dataset's codes someone picked, ahead of the literal extras.
        values = [*sorted(chosen - set(values), key=_code_order), *values]
    columns = []
    for index, value in enumerate(values):
        if node.choices_per_submission and value not in chosen:
            continue
        name = _binary_name(node, value, iterations)
        m = contract.map_column(name)
        if m["kind"] != "matched" or m["node_path"] != node.path:
            raise RuntimeError(
                f"choice binary {name!r} does not map back to {node.path!r}"
            )
        columns.append(
            _Column(
                name,
                pa.int8(),
                {**_node_metadata(node), "choice_value": value},
                (1, order[node.path], iterations, index),
                binary_group=(node.path, iterations),
            )
        )
    return columns


def _code_order(code: str) -> tuple:
    """Sort integer codes by value, ahead of text codes.

    The code itself breaks ties (``1`` and ``01``), so the order never depends on
    set iteration.
    """
    try:
        return (0, int(code), code)
    except ValueError:
        return (1, 0, code)


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


def _raw_multiples(
    names, contract: FormContract
) -> dict[str, tuple[Node, tuple[int, ...]]]:
    """Return the columns holding a select_multiple's raw answer, with its instance."""
    raw: dict[str, tuple[Node, tuple[int, ...]]] = {}
    for name in names:
        if is_system_column(name):
            continue
        m = contract.map_column(name)
        if (
            m["kind"] != "matched"
            or m["choice_code"] is not None
            or m.get("ragged")
            # A choice binary whose choice cannot be recovered: not a raw answer.
            or m.get("ambiguous_choice")
        ):
            continue
        node = contract.nodes[m["node_path"]]
        if node.is_select_multiple and node.is_leaf:
            raw[name] = (node, tuple(i for _, i in m["repeat_iterations"]))
    return raw


def _split_raw_multiples(
    rows: list[dict], contract: FormContract
) -> tuple[list[dict], set[tuple[str, tuple[int, ...]]]]:
    """Return ``rows`` with each select_multiple exported raw (one column, the codes
    separated by spaces) rewritten as its per-choice binaries, as the export writes
    the others, and the (select path, repeat instance) of every raw column split.
    The contract resolves each column, since a select's own name can end in
    ``_<digits>`` like a repeat instance.

    A raw column blank in every row, of a select whose choices are only known
    when picked (a per-submission filter or a `search()` dataset), is kept as is:
    with nothing picked there are no binaries to replace it, and dropping it would
    hide an unanswered question.
    """
    names = dict.fromkeys(name for row in rows for name in row)
    raw = {
        name: (node, iterations)
        for name, (node, iterations) in _raw_multiples(names, contract).items()
        if not (
            node.choices_per_submission
            and all(not str(row.get(name) or "").strip() for row in rows)
        )
    }
    seen = {(node.path, iterations) for node, iterations in raw.values()}
    if not raw:
        return rows, seen
    split = []
    for row in rows:
        row = dict(row)
        for name, (node, iterations) in raw.items():
            for code in row.pop(name, "").split():
                row[_binary_name(node, code, iterations)] = "1"
        split.append(row)
    return split, seen


def cast_wide(rows: list[dict], contract: FormContract) -> pa.Table:
    """Return the submissions as a typed table: system columns, then form order."""
    rows, raw_instances = _split_raw_multiples(rows, contract)
    names = list(dict.fromkeys(name for row in rows for name in row))
    if not rows:
        names = list(SUBMISSION_COLUMNS)
    columns = _columns(names, contract, raw_instances)
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
