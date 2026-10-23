"""Variable dictionary (one entry per parquet column) and variable graph (one per question).

The dictionary is ``{dataset, summary, variables}``; each variable links to its
question in ``questions.json`` by name and carries column statistics, the Arrow and
XML types, sentinel counts, and ``value_labels`` for coded columns (a select_one's
choices; for a select_multiple binary, ``1`` = its choice and ``0`` = not chosen). Sentinel codes are reported, never recoded: the
parquet keeps them as collected and the user decides how to treat them. The graph
links questions through calculations, relevance, group relevance, constraints and
shared repeats.
"""

import datetime as dt
import json
import re
from collections import Counter

import duckdb
import pyarrow as pa
import pyarrow.compute as pc

from datasure.vendor.scto_dict.cast import DROPPED
from datasure.vendor.scto_dict.survey import choice_labels
from datasure.vendor.scto_dict.xml_contract import FormContract
from datasure.vendor.scto_dict.xpath import UnsupportedExpression, compile_expression

_REF_RE = re.compile(r"\$\{([^}]+)\}")
_SURVEY_KEYS = (
    "question_text",
    "hint",
    "type",
    "choice_list",
    "choices",
    "choices_withheld",
    "choices_per_submission",
    "relevance",
    "group_relevances",
    "constraint",
    "constraint_message",
    "calculation",
    "references",
    "disabled",
)


def _json_value(value):
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


def _ordered(arrow_type: pa.DataType) -> bool:
    return (
        pa.types.is_integer(arrow_type)
        or pa.types.is_floating(arrow_type)
        or pa.types.is_temporal(arrow_type)
    )


def _sentinel_counts(
    column: pa.ChunkedArray, sentinels: dict, labels: dict[str, str]
) -> dict:
    """Count the sentinel codes in ``column``, each labelled by the question's own
    choice when it declares the code (``labels``), else by the study's table.
    """
    numbers = {c for c in sentinels if isinstance(c, int)}
    if pa.types.is_integer(column.type) or pa.types.is_floating(column.type):
        values = Counter(v for v in column.to_pylist() if v in numbers)
        found = {int(v): n for v, n in values.items()}
    elif pa.types.is_string(column.type):
        codes = {str(code): code for code in numbers}
        found = {
            codes[v]: n for v, n in Counter(column.to_pylist()).items() if v in codes
        }
    elif pa.types.is_date(column.type) or pa.types.is_timestamp(column.type):
        dates = {c for c in sentinels if isinstance(c, dt.date)}
        days = (
            v.date() if isinstance(v, dt.datetime) else v
            for v in column.to_pylist()
            if v is not None
        )
        found = dict(Counter(d for d in days if d in dates))
    else:
        return {}
    return {
        str(code): {
            "label": labels.get(str(code), sentinels[code]),
            "count": found[code],
        }
        for code in sorted(found, key=str)
    }


# A select compared with a code: selected(${x}, 'c'), ${x} = 'c', ${x} != 5.
_COMPARED = (
    re.compile(r"selected\(\s*\$\{([^}]+)\}\s*,\s*'([^']+)'\s*\)"),
    re.compile(r"\$\{([^}]+)\}\s*!?=\s*'([^']+)'"),
    re.compile(r"\$\{([^}]+)\}\s*!?=\s*(-?[0-9]+)(?![\w.])"),
)


def absent_codes(questions: list[dict], contract: FormContract) -> list[dict]:
    """Return each condition, of a question or of a group, that compares a select
    with a code its list lacks: a follow-up gated on it is never asked. A list read
    per submission or kept unread has no known codes and is not checked.
    """
    selects = {}
    for q in questions:
        if q["type"] not in ("select_one", "select_multiple"):
            continue
        node = contract.nodes["/".join([*q["group_path"], q["variable_name"]])]
        if node.data_source and node.choice_universe is None:
            continue
        selects[q["variable_name"]] = {str(c["value"]) for c in node.all_choices}
    conditions = {}
    for q in questions:
        for where in ("relevance", "constraint", "calculation"):
            conditions[q["variable_name"], where] = q[where]
        # A group's relevance, once, under the group's name.
        for gate in q["gates"]:
            if gate["group"] is not None:
                conditions[gate["group"], "group relevance"] = gate["relevance"]
    found = []
    for (name, where), condition in conditions.items():
        for pattern in _COMPARED:
            for select, code in pattern.findall(condition or ""):
                if select in selects and code not in selects[select]:
                    found.append(
                        {"name": name, "in": where, "select": select, "code": code}
                    )
    return found


class _Own:
    """The context of a constraint that reads only ``.``, the answer itself."""

    def __init__(self, value):
        self.value = value

    def ref(self, name: str):
        if name != ".":
            raise UnsupportedExpression(f"${{{name}}}")
        return self.value

    def index(self) -> int:
        raise UnsupportedExpression("index()")


def allowed_codes(constraint: str | None, sentinels: dict) -> list[int] | None:
    """Return the numeric sentinel codes a question's constraint accepts (every code
    without a constraint), or None when the constraint reads more than the answer.
    """
    codes = sorted(c for c in sentinels if isinstance(c, int))
    if not constraint:
        return codes
    try:
        fn = compile_expression(constraint)
        return [c for c in codes if bool(fn(_Own(c)))]
    except UnsupportedExpression:
        return None


def _kind(node) -> str:
    """Return what a column with no question is: a note, a group, a preload, or not
    in the current form (written under another version, say).
    """
    if node is None:
        return "not_in_form"
    if not node.is_leaf:
        return "group"
    if node.original == "note":
        return "note"
    if node.preload:
        return "preload"
    raise ValueError(f"{node.path}: a field with a column but no question")


def kept(table: pa.Table, exclude: str | None) -> pa.Table:
    """Return the rows of ``table`` that the SQL predicate ``exclude`` does not hold
    for (the config's ``[submissions] exclude``); every row without one.

    The predicate is evaluated as a column over every row of ``submissions``, so a
    window can say which rows a resubmission replaced:
    ``row_number() OVER (PARTITION BY id ORDER BY SubmissionDate DESC) > 1``.

    The predicate must make the query one statement. Its error names only the
    error's type, since DuckDB's message can quote a value it failed on.
    """
    if exclude is None:
        return table
    con = duckdb.connect()
    con.register("submissions", table)
    sql = (
        f"SELECT KEY FROM (SELECT KEY, ({exclude}) AS excluded FROM submissions) "
        "WHERE excluded IS NOT TRUE"
    )
    try:
        if len(con.extract_statements(sql)) != 1:
            raise ValueError(
                f"[submissions] exclude = {exclude!r}: not one condition; it closes "
                "the query it is put in"
            )
        keys = con.execute(sql).to_arrow_table()
    except duckdb.Error as e:
        raise ValueError(
            f"[submissions] exclude = {exclude!r}: {type(e).__name__}; run the "
            "condition in a script to see why"
        ) from None
    return table.filter(pc.is_in(table.column("KEY"), keys.column("KEY")))


def _add_picked(
    picked: dict,
    universes: dict,
    question: dict,
    node,
    meta: dict,
    column_name: str,
    column: pa.ChunkedArray,
    contract: FormContract,
) -> None:
    """Add the codes ``column`` holds for its withheld select to ``picked``."""
    name = question["variable_name"]
    codes = picked.setdefault(name, set())
    universes[name] = {str(c["value"]) for c in node.all_choices}
    if "choice_value" in meta:
        if pc.max(column).as_py() == 1:
            codes.add(meta["choice_value"])
    elif question["type"] == "select_multiple":
        code = contract.map_column(column_name)["choice_code"]
        if code is not None:
            # A binary for a code the list lacks, kept as text.
            if "1" in column.cast(pa.string()).to_pylist():
                codes.add(str(code))
        else:
            codes |= {c for v in column.drop_null().to_pylist() for c in v.split()}
    else:
        codes |= {str(v) for v in pc.unique(column.drop_null()).to_pylist()}


def build_dictionary(
    table: pa.Table,
    questions: list[dict],
    contract: FormContract,
    sentinels: dict[int, str],
    exclude: str | None = None,
) -> dict:
    """Return the variable dictionary for a cast table; counts leave out the rows
    ``exclude`` holds for.
    """
    by_name = {q["variable_name"]: q for q in questions}
    n_all = table.num_rows
    table = kept(table, exclude)
    n_rows = table.num_rows
    variables = {}
    # The codes the submissions picked in each withheld list, and the list's codes.
    picked: dict[str, set[str]] = {}
    universes: dict[str, set[str]] = {}
    for order, field in enumerate(table.schema):
        meta = {k.decode(): v.decode() for k, v in (field.metadata or {}).items()}
        column = table.column(field.name)
        non_null = n_rows - column.null_count
        entry = {
            "variable_order": order,
            "non_null_count": non_null,
            "missing_rate": round(column.null_count / n_rows, 4) if n_rows else 1.0,
            "is_all_missing": non_null == 0,
        }
        if _ordered(field.type) and non_null:
            bounds = pc.min_max(column)
            entry["data_min"] = _json_value(bounds["min"].as_py())
            entry["data_max"] = _json_value(bounds["max"].as_py())
        if pa.types.is_string(field.type) and non_null:
            # Many values at exactly the longest length can mean a limit cut them.
            lengths = pc.utf8_length(column)
            longest = pc.max(lengths).as_py()
            entry["max_length"] = longest
            entry["at_max_length"] = pc.sum(pc.equal(lengths, longest)).as_py()
        entry["parquet"] = {
            "arrow_type": str(field.type),
            "xml_type": meta.get("xml_type"),
        }
        if "cast_fallback" in meta:
            entry["parquet"]["cast_fallback"] = meta["cast_fallback"]

        system = meta.get("system") == "true"
        node = contract.nodes.get(meta.get("node_path"))
        # A system column can also be a form field (duration() exports as `duration`);
        # notes and unmapped columns have no question.
        question = by_name.get(field.name if system else node.name if node else None)
        if system:
            entry["system"] = True
        if question is None:
            entry.update(question=None, survey=None)
            if not system:
                entry["column_kind"] = _kind(node)
        else:
            entry["question"] = question["variable_name"]
            if not system:
                mapped = contract.map_column(field.name)
                if mapped["repeat_iterations"]:
                    entry["repeat_iteration"] = [
                        i for _, i in mapped["repeat_iterations"]
                    ]
                if mapped.get("ragged"):
                    # More or fewer repeat indices than the field's nesting: written
                    # under another form version.
                    entry["ragged"] = True
            if "choice_value" in meta:
                # A select_multiple binary stands for one choice: 1 chosen, 0 not.
                entry["choice_value"] = meta["choice_value"]
                # A withheld list is not in the outputs, nor its labels.
                label = (
                    "(label not listed)"
                    if question["choices_withheld"]
                    else choice_labels(question["choices"])[meta["choice_value"]]
                )
                entry["value_labels"] = [
                    {"value": "1", "label": label},
                    {"value": "0", "label": "not chosen"},
                ]
            elif question["type"] == "select_one" and not question["choices_withheld"]:
                entry["value_labels"] = [
                    {"value": value, "label": label}
                    for value, label in choice_labels(question["choices"]).items()
                ]
            entry["survey"] = {k: question[k] for k in _SURVEY_KEYS}
            entry["survey"]["original_variable_name"] = question["variable_name"]
            entry["survey"]["group_path"] = "/".join(question["group_path"])

        if (
            question
            and question["choices_withheld"]
            and node is not None
            and node.choice_universe is not None
            and non_null
        ):
            _add_picked(
                picked, universes, question, node, meta, field.name, column, contract
            )

        labels = (
            choice_labels(question["choices"])
            if question and question["choices"]
            else {}
        )
        found = _sentinel_counts(column, sentinels, labels)
        if found:
            entry["sentinels"] = found
        if question and question["type"] in ("integer", "decimal"):
            entry["sentinels_allowed"] = allowed_codes(
                question["constraint"], sentinels
            )
        variables[field.name] = entry

    return {
        "dataset": {
            "name": contract.formid,
            "form_version": contract.formdef_version,
            "n_observations": n_rows,
            "n_variables": table.num_columns,
            # [submissions] exclude: rows the project does not use, left out of counts.
            "exclude": exclude,
            "n_excluded": n_all - n_rows,
        },
        "summary": {
            "n_questions": len(questions),
            "n_system": sum(1 for v in variables.values() if v.get("system")),
            "n_all_missing": sum(1 for v in variables.values() if v["is_all_missing"]),
            "n_cast_fallback": sum(
                1 for v in variables.values() if "cast_fallback" in v["parquet"]
            ),
            # Columns whose repeat indices do not fit the form: another form version.
            "n_ragged": sum(1 for v in variables.values() if v.get("ragged")),
            # Columns with no question, by what they are.
            "columns_without_question": dict(
                Counter(
                    v["column_kind"] for v in variables.values() if "column_kind" in v
                )
            ),
            "conditions_on_absent_codes": absent_codes(questions, contract),
            # Per withheld list: how many codes the submissions picked, and those its
            # dataset no longer offers (pii.attach keeps only their count when their
            # columns' values are not shown).
            "withheld_choices": {
                name: {
                    "n_codes_picked": len(codes),
                    "n_codes_not_in_list": len(codes - universes[name]),
                    "codes_not_in_list": sorted(codes - universes[name]),
                }
                for name, codes in picked.items()
            },
            "n_empty_notes_and_groups_dropped": int(
                table.schema.metadata[DROPPED.encode()]
            ),
            "by_arrow_type": dict(
                Counter(v["parquet"]["arrow_type"] for v in variables.values())
            ),
            # No submission holds a value for these, so the export has no column. A
            # repeat_count entry describes the repeat, not a field of its own.
            "questions_without_columns": [
                q["variable_name"]
                for q in questions
                if q["type"] != "repeat_count"
                and q["variable_name"]
                not in {v["question"] for v in variables.values()}
            ],
        },
        "variables": variables,
    }


def build_graph(
    questions: list[dict], vardict: dict, reached: dict[str, int | None]
) -> dict:
    """Return the question graph as node-link JSON plus the repeat-group tree.

    A question no submission answered carries ``reached``: how many submissions its
    conditions hold for (``stats.reached``), None when they cannot be evaluated.
    """
    names = {q["variable_name"] for q in questions}
    repeats = {
        q["repeat_group_name"]: q for q in questions if q["type"] == "repeat_count"
    }
    columns: dict[str, list[str]] = {}
    for column, entry in vardict["variables"].items():
        if entry["question"] is not None:
            columns.setdefault(entry["question"], []).append(column)

    def repeat_chain(group_path: list[str]) -> list[str]:
        return [g for g in group_path if g in repeats]

    nodes, edges = [], []
    members: dict[str, list[str]] = {}
    for q in questions:
        name = q["variable_name"]
        chain = repeat_chain(q["group_path"])
        nodes.append(
            {
                "id": name,
                "type": q["type"],
                "group_path": "/".join(q["group_path"]),
                "repeat_depth": len(chain),
                "repeat_group": chain[-1] if chain else None,
                "columns": columns.get(name, []),
            }
            | ({"reached": reached[name]} if name in reached else {})
        )
        if chain:
            members.setdefault(chain[-1], []).append(name)
        sources = [
            ("calculates_from", [q["calculation"]]),
            ("gated_by", [q["relevance"]]),
            ("group_gated_by", q["group_relevances"]),
            ("constrained_by", [q["constraint"]]),
        ]
        for kind, exprs in sources:
            refs = dict.fromkeys(r for e in exprs if e for r in _REF_RE.findall(e))
            edges += [
                {"source": r, "target": name, "type": kind} for r in refs if r in names
            ]

    repeat_groups = {}
    for name, count_row in repeats.items():
        parents = repeat_chain(count_row["group_path"])
        repeat_groups[name] = {
            "parent": parents[-1] if parents else None,
            "depth": len(parents) + 1,
            "count": count_row["calculation"],
            "members": members.get(name, []),
        }
    return {
        "directed": True,
        "multigraph": True,
        "nodes": nodes,
        "edges": edges,
        "repeat_groups": repeat_groups,
    }


def write_json(data: dict, path, indent: int | None = 2) -> None:
    """Write ``data`` as UTF-8 JSON, indented unless ``indent`` is None."""
    path.write_text(
        json.dumps(data, indent=indent, ensure_ascii=False), encoding="utf-8"
    )
