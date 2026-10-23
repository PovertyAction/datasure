"""A form's form-list entry and the datasets its XML references.

The contract itself is ``xml_contract.parse_contract``; ``Node.publishable`` carries the
SurveyCTO ``publishable`` bind attribute.
"""

import csv
import json
import xml.etree.ElementTree as ET
from collections import Counter
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

from datasure.vendor.scto_dict.xml_contract import FormContract, Node


class UnresolvedDataset(LookupError):
    """The XML references a dataset that is neither a server dataset nor a form file."""


@dataclass(frozen=True)
class FormEntry:
    """One form's ``/formList`` entry: its server datasets and attached files."""

    form_id: str
    version: str
    dataset_ids: set[str]
    filenames: set[str]
    # The enumerator dataset its enumerator fields pick from, if it has one.
    enumerators: str | None = None


@dataclass(frozen=True)
class DatasetSource:
    """Where a referenced dataset is pulled from: ``pull_dataset`` or ``pull_form_files``."""

    kind: str  # "server_dataset" | "form_file"
    ref: str  # dataset id | attached filename
    # False: the XML reads a server dataset the form does not attach on the server.
    attached: bool = True


def _ln(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def form_entry(form_list_xml: bytes, form_id: str) -> FormEntry:
    """Return ``form_id``'s entry from the ``/formList`` XML.

    SurveyCTO puts ``datasets`` and ``files`` in the entry as JSON text
    (``{"datasets": [{"id": ...}]}``, ``{"files": [{"filename": ...}]}``);
    ``datasets`` is empty when the form uses none. ``enumeratorsSupport`` names the
    enumerator dataset; the entry of a form without one omits it or leaves it empty.
    """
    for xform in ET.fromstring(form_list_xml).iter():
        if _ln(xform.tag) != "xform":
            continue
        fields = {_ln(c.tag): (c.text or "").strip() for c in xform}
        if fields["formID"] != form_id:
            continue
        datasets = (
            json.loads(fields["datasets"])["datasets"] if fields["datasets"] else []
        )
        files = json.loads(fields["files"])["files"]
        return FormEntry(
            form_id=form_id,
            version=fields["version"],
            dataset_ids={d["id"] for d in datasets},
            filenames={f["filename"] for f in files},
            enumerators=fields.get("enumeratorsSupport") or None,
        )
    raise KeyError(f"form {form_id!r} is not in the form list")


def attach_enumerators(contract: FormContract, entry: FormEntry) -> None:
    """Give each enumerator field the form's enumerator dataset as its data source.

    The XML marks the field (``fieldType="enumerator"``) but names no dataset; the
    form list does.
    """
    for node in contract.nodes.values():
        if node.field_type != "enumerator":
            continue
        if entry.enumerators is None:
            raise UnresolvedDataset(
                f"{node.path} is an enumerator field, but form {entry.form_id!r} "
                "has no enumerator dataset in the form list"
            )
        node.data_source = {"kind": "enumerator", "dataset": entry.enumerators}


@contextmanager
def naming_decode_errors(csv_path: Path):
    """Raise a dataset CSV that is not UTF-8 as a ValueError naming the file."""
    try:
        yield
    except UnicodeDecodeError as e:
        raise ValueError(f"{csv_path}: not UTF-8 (byte {e.start}: {e.reason})") from e


def checked_header(csv_path: Path, header: list[str] | None) -> list[str]:
    """Return a dataset CSV's header; raise when it is empty or names a column twice,
    since a row read by name then keeps only the last of them.
    """
    if not header:
        raise ValueError(f"{csv_path}: no header row")
    twice = sorted(c for c, n in Counter(header).items() if n > 1)
    if twice:
        raise ValueError(f"{csv_path}: columns named twice in the header: {twice}")
    return header


def dataset_header(csv_path: Path) -> list[str]:
    """Return a dataset CSV's columns, reading no row."""
    with (
        naming_decode_errors(csv_path),
        open(csv_path, encoding="utf-8-sig", newline="") as f,
    ):
        return checked_header(csv_path, next(csv.reader(f), None))


class DatasetTable:
    """A dataset CSV read once, with its rows indexed by column value on demand."""

    def __init__(self, csv_path: Path):
        """Read ``csv_path`` (UTF-8, with or without BOM)."""
        self.name = Path(csv_path).name
        with (
            naming_decode_errors(csv_path),
            open(csv_path, encoding="utf-8-sig", newline="") as f,
        ):
            reader = csv.DictReader(f)
            self.header = checked_header(csv_path, reader.fieldnames)
            self.rows = list(reader)
        self._index: dict[str, dict[str, list[int]]] = {}

    def where(self, column: str, values: list[str]) -> list[dict]:
        """Return the rows whose ``column`` equals one of ``values``, in file order."""
        if column not in self._index:
            index: dict[str, list[int]] = {}
            for position, row in enumerate(self.rows):
                index.setdefault(row[column], []).append(position)
            self._index[column] = index
        positions = sorted(p for v in values for p in self._index[column].get(v, []))
        return [self.rows[p] for p in positions]


class SubmissionValues:
    """The values a form's fields take in its submissions, read from the wide rows."""

    def __init__(self, contract: FormContract, rows: list[dict]):
        """Keep the rows; a field's columns are resolved when first asked for."""
        self.contract, self.rows = contract, rows
        self._columns: dict[str, list[str]] | None = None

    def of(self, expression: str | None) -> set[str] | None:
        """Return the values of the field ``expression`` names, or None when it is
        not a plain field reference (an expression, or nothing).
        """
        prefix = f"/{self.contract.formid}/"
        path = (expression or "").strip()
        if (
            not path.startswith(prefix)
            or path[len(prefix) :] not in self.contract.nodes
        ):
            return None
        if self._columns is None:
            self._columns = {}
            for name in dict.fromkeys(n for row in self.rows for n in row):
                mapped = self.contract.map_column(name)
                if mapped["kind"] == "matched":
                    self._columns.setdefault(mapped["node_path"], []).append(name)
        columns = self._columns.get(path[len(prefix) :], [])
        return {row[c] for row in self.rows for c in columns if row.get(c)}


def search_universe(
    node: Node, table: DatasetTable, fields: dict[str, set[str]] | None = None
) -> list[dict]:
    """Return a ``search()`` select's choices from its dataset.

    The select's one ``<item>`` whose value is a dataset column names the value and
    label columns; any other item is a literal choice, kept after the dataset's. With
    no such item the dataset adds nothing and the literals are the choices. The
    first column/text pair is searched with the mode (``matches``: equal,
    ``contains``: a substring); a second pair keeps the rows whose column equals its
    value, whatever the mode.

    A pair whose value is a field is decided per submission: ``fields`` gives, per
    such column, the values the field takes in the submissions. Its rows are the ones
    that match one of them, and each choice says which in ``when``
    (``{"list_name": "fruits"}``), so one value can be a choice of several lists.
    """
    named = [i for i in node.choice_items if i["value"] in table.header]
    if len(named) > 1:
        raise ValueError(f"{node.path}: several items name columns of {table.name}")
    literals = [i for i in node.choice_items if i not in named]
    if not named:
        return literals
    (columns,) = named
    source = node.data_source
    tests = {"matches": str.__eq__, "contains": str.__contains__}
    if source["filter"] and source["mode"] not in tests:
        raise ValueError(f"{node.path}: search() mode {source['mode']!r}")
    pairs = []  # (column, values to match, test, decided per submission)
    for i, (column, value) in enumerate(source["filter"].items()):
        test = tests[source["mode"]] if i == 0 else str.__eq__
        if value is None:
            if fields is None or column not in fields:
                raise ValueError(f"{node.path}: needs the values ${column} takes")
            pairs.append((column, sorted(fields[column]), test, True))
        else:
            pairs.append((column, [value], test, False))
    # An equality pair narrows the scan to the rows it can keep.
    exact = next(((c, vs) for c, vs, test, _ in pairs if test is str.__eq__), None)
    rows = table.where(*exact) if exact else table.rows
    choices: dict[tuple, dict] = {}
    for row in rows:
        when = {}
        for column, values, test, per_submission in pairs:
            hit = next((v for v in values if test(row[column], v)), None)
            if hit is None:
                break
            if per_submission:
                when[column] = hit
        else:
            value = row[columns["value"]]
            label = ", ".join(row[c] for c in label_columns(columns["label"]))
            choice = {"value": value, "label": label}
            choices.setdefault(
                (tuple(when.items()), value), choice | ({"when": when} if when else {})
            )
    return list(choices.values()) + literals


def label_columns(label: str) -> list[str]:
    """Return the dataset columns a search() choice's label names: one, or several
    separated by commas (``name,id``), which the tool joins with ", ".
    """
    return [c.strip() for c in label.split(",")]


def resolve_datasets(
    contract: FormContract, entry: FormEntry, server_ids: set[str]
) -> dict[str, DatasetSource]:
    """Map every dataset named in a ``pulldata()``/``search()`` to where it is pulled from.

    Names match case-insensitively: the XML may spell a dataset ``hhRoster`` while the
    server's id is ``hhroster``, and an attached file keeps its own case
    (``search('prices')`` reads ``Prices.csv``). A dataset the form attaches comes
    first, then an attached file, then any dataset in ``server_ids`` (``attached`` is
    False: the form reads it without attaching it).
    """
    names = {n.data_source["dataset"] for n in contract.nodes.values() if n.data_source}

    def match(name: str, candidates) -> list[str]:
        return [c for c in candidates if c.lower() == name.lower()]

    resolved = {}
    for name in sorted(names):
        attached = match(name, entry.dataset_ids)
        files = match(f"{name}.csv", entry.filenames)
        on_server = match(name, server_ids)
        if len(attached) == 1:
            resolved[name] = DatasetSource("server_dataset", attached[0])
        elif len(files) == 1:
            resolved[name] = DatasetSource("form_file", files[0])
        elif len(on_server) == 1:
            resolved[name] = DatasetSource("server_dataset", on_server[0], False)
        else:
            raise UnresolvedDataset(
                f"dataset {name!r} is referenced by form {entry.form_id!r} but is neither "
                f"a server dataset nor an attached file ({name}.csv)"
            )
    return resolved
