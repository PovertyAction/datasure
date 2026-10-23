"""Rebuild ``questions.json`` from a compiled SurveyCTO XML.

Each entry is keyed by the field's XLSForm ``name`` (``variable_name``), so the file
joins back to the XLSForm row by row. Expressions are written in XLSForm ``${name}``
syntax; choices are the select's inline items, and a select's ``choice_list`` is its
own name. Each repeat gets a synthetic ``{repeat}_count`` entry before its fields.
"""

import html
import json
import re
from collections import defaultdict
from pathlib import Path

from datasure.vendor.scto_dict.xml_contract import (
    ENUMERATOR_COLUMNS,
    FormContract,
    Node,
    is_system_column,
)

# Metadata the export writes as a system column when the field has its reserved name
# (starttime, deviceid, ...); under any other name the field is a question.
_METADATA_TYPES = {"start", "end", "deviceid", "username", "simserial", "phonenumber"}
# The form's own meta fields, matched whole: a field named KEY_INF is a question.
_EXCLUDED_NAMES = {"instanceID", "instanceName"}

_INPUT_TYPES = {
    "string": "text",
    "int": "integer",
    "decimal": "decimal",
    "date": "date",
    "dateTime": "datetime",
    "time": "time",
    "geopoint": "geopoint",
    "geotrace": "geotrace",
    "geoshape": "geoshape",
}
_PRELOAD_TYPES = {
    ("timestamp", "start"): "start",
    ("timestamp", "end"): "end",
    ("date", "today"): "today",
    ("property", "deviceid"): "deviceid",
    ("property", "subscriberid"): "subscriberid",
    ("property", "simserial"): "simserial",
    ("property", "phonenumber"): "phonenumber",
    ("property", "username"): "username",
    ("property", "caseid"): "caseid",
}
_MEDIA_TYPES = {"image": "image", "audio": "audio", "video": "video"}
_REF_RE = re.compile(r"\$\{([^}]+)\}")
# An HTML tag: `<` then a letter or `/`, so `<5 and >10` is text.
_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")


def plain_text(text: str | None) -> str | None:
    """Return form text without its HTML: tags dropped, entities decoded, whitespace
    collapsed. ``${name}`` references stay.
    """
    if text is None:
        return None
    return " ".join(html.unescape(_TAG_RE.sub(" ", text)).split())


def _xlsform_type(node: Node) -> str:
    """Return the XLSForm base type a node was compiled from."""
    if node.field_type == "enumerator":
        return "enumerator"
    if node.original is not None:
        return node.original
    if node.control in ("select_one", "select_multiple"):
        return node.control
    if node.control == "input" and node.xml_type in _INPUT_TYPES:
        return _INPUT_TYPES[node.xml_type]
    if node.control == "upload" and node.xml_type == "binary":
        return _MEDIA_TYPES.get((node.mediatype or "").split("/")[0], "file")
    if node.control is None and node.preload is not None:
        key = (node.preload, node.preload_params)
        if key in _PRELOAD_TYPES:
            return _PRELOAD_TYPES[key]
    if node.control is None and node.calculate is not None:
        return "calculate"
    raise ValueError(
        f"node {node.path!r}: no XLSForm type for bind type={node.xml_type!r}, "
        f"control={node.control!r}, preload={node.preload!r}/{node.preload_params!r}"
    )


class _Refs:
    """Rewrite absolute instance paths in an expression to ``${name}``.

    SurveyCTO compiles ``${name}`` to `` /form/group/name `` with one space on each
    side; both spaces go with the path.
    """

    def __init__(self, contract: FormContract):
        self._names = {path: node.name for path, node in contract.nodes.items()}
        self._path_re = re.compile(
            rf" ?/{re.escape(contract.formid)}((?:/[\w.\-]+)+) ?"
        )

    def __call__(self, expr: str | None) -> str | None:
        if expr is None:
            return None
        return self._path_re.sub(self._sub, expr).strip()

    def _sub(self, match: re.Match) -> str:
        path = match.group(1).lstrip("/")
        if path not in self._names:
            raise ValueError(
                f"expression references {path!r}, which is not a form node"
            )
        return "${" + self._names[path] + "}"


def _references(*exprs: str | None) -> list[str] | None:
    refs = list(dict.fromkeys(r for e in exprs if e for r in _REF_RE.findall(e)))
    return refs or None


def _data_source(node: Node, refs: "_Refs") -> dict | None:
    """Return the dataset a field reads and how its rows match the submission.

    ``pulldata('roster', 'name', 'hhid', ${id})`` reads ``roster.name`` where
    ``roster.hhid`` = ``${id}``; a ``search()`` select keeps the dataset rows whose
    filter columns match.
    """
    source = node.data_source
    if source is None:
        return None
    if source["kind"] == "enumerator":
        return {
            "kind": "enumerator",
            "dataset": source["dataset"],
            "columns": list(ENUMERATOR_COLUMNS),
            "match": [],
        }
    if source["kind"] == "pulldata":
        return {
            "kind": "pulldata",
            "dataset": source["dataset"],
            "column": refs(source["value"]).strip("'\""),
            "match": [{"column": source["key"], "value": refs(source["match"])}],
        }
    return {
        "kind": "search",
        "dataset": source["dataset"],
        "mode": source["mode"],
        "match": [
            {"column": column, "value": refs(value)}
            for column, value in source["match"].items()
        ],
    }


def _excluded(name: str, qtype: str) -> bool:
    if qtype == "note":
        return True
    if qtype in _METADATA_TYPES:
        return is_system_column(name)
    return name in _EXCLUDED_NAMES


def build_questions(contract: FormContract) -> list[dict]:
    """Return the form's questions in form order."""
    refs = _Refs(contract)
    repeats = set(contract.repeat_groups)
    questions = []

    def group_context(node: Node) -> tuple[list[str], bool, list[dict], int]:
        """Return enclosing group relevances (outer first), whether any is "0", the
        same as gates with their group and repeat depth, and the node's repeat depth.

        A gate's ``repeat_depth`` is how many repeats enclose its group, the group
        included: ``index()`` in it is the index of that repeat.
        """
        relevances, gates, depth = [], [], 0
        for i in range(1, len(node.group_path) + 1):
            group = contract.nodes["/".join(node.group_path[:i])]
            depth += group.name in repeats
            if group.relevant is not None:
                relevance = refs(group.relevant)
                relevances.append(relevance)
                gates.append(
                    {"group": group.name, "relevance": relevance, "repeat_depth": depth}
                )
        return relevances, "0" in relevances, gates, depth

    def own_gate(relevance: str | None, depth: int) -> list[dict]:
        if relevance is None:
            return []
        return [{"group": None, "relevance": relevance, "repeat_depth": depth}]

    def label(node: Node) -> str:
        return plain_text(refs(node.label)) or ""

    # A repeat counted by an expression has a compiled `<repeat>_count` calculate
    # beside it; the repeat's count entry describes that field instead of repeating it.
    counted_by = {
        node.name: contract.nodes[path]
        for node in contract.nodes.values()
        if not node.is_leaf
        and node.name in repeats
        and (path := "/".join([*node.group_path, f"{node.name}_count"]))
        in contract.nodes
    }
    count_paths = {n.path for n in counted_by.values()}

    for node in contract.nodes.values():
        if not node.is_leaf and node.name in repeats:
            count = counted_by.get(node.name)
            group_relevances, parent_disabled, gates, depth = group_context(
                count or node
            )
            relevance = refs((count or node).relevant)
            calculation = refs(count.calculate if count else node.repeat_count)
            questions.append(
                {
                    "type": "repeat_count",
                    "choice_list": None,
                    "choices": None,
                    "choices_per_submission": False,
                    "choice_filter": None,
                    "variable_name": f"{node.name}_count",
                    "question_text": f"Number of iterations in '{label(node) or node.name}' repeat group",
                    "disabled": parent_disabled or relevance == "0",
                    "constraint": None,
                    "relevance": relevance,
                    "group_relevances": group_relevances,
                    "gates": gates + own_gate(relevance, depth),
                    "required": False,
                    "calculation": calculation,
                    "calculation_is_default": False,
                    "appearance": None,
                    "references": _references(relevance, calculation),
                    "group_path": node.group_path,
                    "publishable": count.publishable if count else False,
                    "choices_withheld": None,
                    "choice_columns": None,
                    "hint": None,
                    "constraint_message": None,
                    "data_source": None,
                    "repeat_group_name": node.name,
                }
            )
            continue
        if not node.is_leaf or node.path in count_paths:
            continue
        qtype = _xlsform_type(node)
        if _excluded(node.name, qtype):
            continue
        group_relevances, parent_disabled, gates, depth = group_context(node)
        relevance = refs(node.relevant)
        constraint = refs(node.constraint)
        calculation = refs(node.calculate)
        is_select = qtype in ("select_one", "select_multiple")
        questions.append(
            {
                "type": qtype,
                "choice_list": node.name if is_select else None,
                # A search() filtered by a field lists each choice once: its filter
                # values are the values the field takes in the submissions, so they
                # stay in <form>_search_choices.parquet.
                "choices": (
                    _unique(
                        {"value": c["value"], "label": plain_text(refs(c["label"]))}
                        | (
                            {"filter_columns": c["filter_columns"]}
                            if "filter_columns" in c
                            else {}
                        )
                        for c in node.choice_items
                    )
                    if is_select
                    else None
                ),
                # The form filters the list per submission (an itemset that reads
                # the form, a search() filtered by a field): a select_multiple has
                # binaries only for the codes someone picked.
                "choices_per_submission": node.choices_per_submission,
                # The itemset's filter, paths as ${name}; items: the list's length
                # before a static filter applies.
                "choice_filter": node.choice_filter
                and {
                    **node.choice_filter,
                    "expression": refs(node.choice_filter["expression"]),
                },
                "variable_name": node.name,
                "question_text": label(node)
                or (calculation if qtype == "calculate" else ""),
                "hint": plain_text(refs(node.hint)),
                "constraint_message": plain_text(refs(node.constraint_message)),
                "disabled": parent_disabled or relevance == "0",
                "constraint": constraint,
                "relevance": relevance,
                "group_relevances": group_relevances,
                "gates": gates + own_gate(relevance, depth),
                "required": node.required,
                "calculation": calculation,
                "calculation_is_default": node.calculation_is_default
                and qtype != "calculate"
                and not node.readonly
                and "invisible" not in (node.appearance or ""),
                "appearance": refs(node.appearance),
                "references": _references(relevance, constraint, calculation),
                "group_path": node.group_path,
                "publishable": node.publishable,
                "choices_withheld": node.choices_withheld,
                "choice_columns": node.choice_columns,
                "data_source": _data_source(node, refs),
            }
        )
    for order, question in enumerate(questions):
        question["question_order"] = order
    return questions


def _unique(choices) -> list[dict]:
    """Return ``choices`` without repeats, in order."""
    return list({json.dumps(c, sort_keys=True): c for c in choices}.values())


def search_choices(contract: FormContract) -> list[dict]:
    """Return every choice of the ``search()`` lists and the withheld lists, one row
    per choice and filter value.

    ``when`` holds a list's filter values, the values a field takes in the
    submissions, which ``questions.json`` leaves out; ``withheld`` says why
    ``questions.json`` refers to a list without listing it. Scripts read both from
    ``<form>.choices`` in the database. A list filtered by an expression has no
    choices known before a submission, so no rows.
    """
    refs = _Refs(contract)
    return [
        {
            "question": node.name,
            "value": c["value"],
            "label": plain_text(refs(c["label"])),
            "when": json.dumps(c["when"]) if "when" in c else None,
            "withheld": ", ".join(node.choices_withheld)
            if node.choices_withheld
            else None,
        }
        for node in contract.nodes.values()
        if node.choice_universe is not None
        for c in node.choice_universe
    ]


def write_sections(
    questions: list[dict], out_dir: Path, prefix: str = "section"
) -> dict[str, Path]:
    """Write one JSON slice per group level (``a``, ``a/b``, ...) plus ``ungrouped``.

    Returns the written path per section key; ``/`` in a key becomes ``_`` in the
    filename.
    """
    sections: dict[str, list[dict]] = defaultdict(list)
    for q in questions:
        path = q["group_path"]
        if not path:
            sections["ungrouped"].append(q)
        for i in range(1, len(path) + 1):
            sections["/".join(path[:i])].append(q)
    out_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    for key, section in sections.items():
        out = out_dir / f"{prefix}_{key.replace('/', '_').replace(' ', '_')}.json"
        out.write_text(
            json.dumps(section, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        written[key] = out
    return written
