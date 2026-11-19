"""Rebuild a SurveyCTO design-shaped form definition from the compiled form XML.

SurveyCTO's design endpoint (``/forms/{id}/design/``) returns the form's
XLSForm as JSON, but refuses some forms with HTTP 430 until they are
"optimized", which the console offers no way to do. The compiled XML is
always available, so this module rebuilds the same shape from it:
``fieldsRowsAndColumns`` and ``choicesRowsAndColumns``, each a header row
followed by data rows, plus ``title``.

The result is a faithful questionnaire for reading and for the replication
package's import script, not the original spreadsheet: anything the XML
does not keep (translations other than the default, the original choice list
names, comments in the spreadsheet) is not there. ``rebuilt_from_xml`` marks
it so callers can say so.
"""

import re
import xml.etree.ElementTree as ET

from datasure.surveycto.xml_contract import FormContract, Node, parse_contract

FIELD_COLUMNS = [
    "type",
    "name",
    "label",
    "hint",
    "required",
    "relevance",
    "constraint",
    "constraint message",
    "calculation",
    "appearance",
    "repeat_count",
]
CHOICE_COLUMNS = ["list_name", "name", "label"]
_COLUMN_KEYS = {column.replace(" ", "_"): column for column in FIELD_COLUMNS}

# XForm bind types -> XLSForm types, for fields with no more specific type.
_XML_TYPES = {
    "string": "text",
    "int": "integer",
    "decimal": "decimal",
    "date": "date",
    "dateTime": "datetime",
    "time": "time",
    "geopoint": "geopoint",
    "geotrace": "geotrace",
    "geoshape": "geoshape",
    "barcode": "barcode",
}

# Upload mediatype prefix -> XLSForm type; any other upload is a file.
_UPLOAD_TYPES = {"image/": "image", "audio/": "audio", "video/": "video"}

# Bind appearance class -> XLSForm type, for media SurveyCTO fills itself.
_BINARY_CLASSES = {
    "comments": "comments",
    "textAudit": "text audit",
    "audioAudit": "audio audit",
}

# jr:preload="timestamp" params -> XLSForm metadata types.
_TIMESTAMP_TYPES = {"start": "start", "end": "end"}

# The form's own bookkeeping group, never part of the XLSForm.
_META = "meta"


def design_from_xml(xml: bytes) -> dict:
    """Return a design-shaped form definition rebuilt from the compiled XML.

    Parameters
    ----------
    xml : bytes
        The compiled form XML, as ``SurveyCTOAPIClient.download_form_xml``
        returns it.

    Returns
    -------
    dict
        ``title``, ``fieldsRowsAndColumns``, ``choicesRowsAndColumns`` and
        ``rebuilt_from_xml`` (always True).
    """
    contract = parse_contract(xml)
    survey, choices = _rows(contract)
    return {
        "title": _title(xml) or contract.formid,
        "fieldsRowsAndColumns": [FIELD_COLUMNS, *survey],
        "choicesRowsAndColumns": [CHOICE_COLUMNS, *choices],
        "rebuilt_from_xml": True,
    }


def _title(xml: bytes) -> str | None:
    """Return the form's <h:title>, or None."""
    for el in ET.fromstring(xml).iter():
        if el.tag.rsplit("}", 1)[-1] == "title" and el.text and el.text.strip():
            return el.text.strip()
    return None


def _rows(contract: FormContract) -> tuple[list[list[str]], list[list[str]]]:
    """Return the survey rows and choice rows, in form order."""
    references = _references(contract.formid)
    repeats = {token for node in contract.nodes.values() for token in node.repeat_path}
    survey: list[list[str]] = []
    choices: list[list[str]] = []
    open_groups: list[tuple[str, str]] = []  # (path, "group" | "repeat")

    def close_until(parent: str) -> None:
        while open_groups and not _is_within(parent, open_groups[-1][0]):
            path, kind = open_groups.pop()
            survey.append(_row(f"end {kind}", path.rsplit("/", 1)[-1]))

    for path, node in contract.nodes.items():
        if path.split("/")[0] == _META:
            continue
        close_until("/".join(node.group_path))
        if not node.is_leaf:
            kind = "repeat" if node.name in repeats else "group"
            survey.append(
                _row(
                    f"begin {kind}",
                    node.name,
                    label=node.label,
                    relevance=references(node.relevant),
                    appearance=node.appearance,
                    repeat_count=references(node.repeat_count),
                )
            )
            open_groups.append((path, kind))
            continue
        list_name = node.name if node.control else ""
        survey.append(
            _row(
                _field_type(node, list_name),
                node.name,
                label=node.label,
                hint=node.hint,
                required="yes" if node.required else "",
                relevance=references(node.relevant),
                constraint=references(node.constraint),
                constraint_message=node.constraint_message,
                calculation=references(node.calculate),
                appearance=node.appearance,
            )
        )
        choices.extend(_choice_rows(node, list_name))
    close_until("")
    return survey, choices


def _choice_rows(node: Node, list_name: str) -> list[list[str]]:
    """Return a select's choice rows; none for a field that is not a select.

    A `search()` select's list is the row naming its dataset columns, then any
    literal extras. A select prefilled by `pulldata()` keeps its plain list.
    """
    if not list_name:
        return []
    items = node.choice_items
    if node.choice_columns:
        items = [node.choice_columns, *items]
    return [
        [list_name, str(item["value"]), str(item.get("label") or "")] for item in items
    ]


def _is_within(path: str, group: str) -> bool:
    """Return whether *path* is *group* or inside it."""
    return path == group or path.startswith(group + "/")


def _row(field_type: str, name: str, **values: str | None) -> list[str]:
    """Return one survey row in FIELD_COLUMNS order.

    Keyword names are the column names with spaces as underscores.
    """
    cells = {"type": field_type, "name": name}
    cells |= {_COLUMN_KEYS[key]: value for key, value in values.items()}
    return [str(cells.get(column) or "").strip() for column in FIELD_COLUMNS]


def _field_type(node: Node, list_name: str) -> str:
    """Return the XLSForm type of a leaf node."""
    if node.control in ("select_one", "select_multiple"):
        return f"{node.control} {list_name}"
    if node.original:
        return node.original
    if node.preload == "timestamp":
        return _TIMESTAMP_TYPES.get(node.preload_params or "", "datetime")
    if node.preload == "property" and node.preload_params:
        return node.preload_params
    if node.xml_type == "binary":
        return _binary_type(node)
    if node.calculate and node.control is None:
        return "calculate"
    return _XML_TYPES.get(node.xml_type or "", "text")


def _binary_type(node: Node) -> str:
    """Return the XLSForm type of a media field."""
    if node.mediatype:
        return next(
            (
                kind
                for prefix, kind in _UPLOAD_TYPES.items()
                if node.mediatype.startswith(prefix)
            ),
            "file",
        )
    match = re.search(r"class=(\w+)", node.bind_appearance or "")
    return _BINARY_CLASSES.get(match.group(1), "file") if match else "file"


# A quoted XPath string literal; the split keeps it as its own part.
_QUOTED = re.compile(r"""('[^']*'|"[^"]*")""")


def _references(formid: str):
    """Return a function that writes absolute paths as ${field} references.

    Text inside a quoted string literal is a value, not a path, and is left as
    written: ``concat('/f/a', /f/a)`` becomes ``concat('/f/a', ${a})``.
    """
    absolute = re.compile(rf"\s*/{re.escape(formid)}/(?:[\w-]+/)*([\w-]+)\s*")

    def rewrite(expression: str | None) -> str | None:
        if expression is None:
            return None
        # re.split with a group puts the quoted literals at the odd indexes.
        parts = _QUOTED.split(expression)
        return "".join(
            part if i % 2 else absolute.sub(lambda m: f" ${{{m.group(1)}}} ", part)
            for i, part in enumerate(parts)
        ).strip()

    return rewrite
