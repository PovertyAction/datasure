"""Answers the survey-expert MCP tools from one form's built outputs.

Reads ``<form>_questions.json``, ``<form>_variable_dictionary.json`` and
``<form>_variable_graph.json``; every answer is plain text. Nothing here reads the
parquet: a column's values (its range, a withheld list's codes) come from the
dictionary and are shown only for a column that is not flagged ``contains_pii`` or
``may_contain_pii``.

Standard library only, so the file also ships in the survey-expert skill as
``search_survey.py`` and runs where the package is not installed::

    python search_survey.py --dir <out_dir>/<form_id> var <name>
"""

import difflib
import json
import math
import re
from collections import Counter
from pathlib import Path

# As pii.FLAGGED: this module imports only the standard library (the skill ships it).
_FLAGGED = {"contains_pii", "may_contain_pii"}
# Longer lists are summarised, with an argument that lists them in full.
_LISTED = 20
_TOKEN_RE = re.compile(r"\w+")
# An HTML tag: `<` then a letter or `/`, so `<5 and >10` is text.
_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")
_REF_RE = re.compile(r"\$\{([^}]+)\}")


def _shows_values(status: str) -> bool:
    """Return whether a column's values may be shown, as ``pii.shows_values``."""
    return status not in _FLAGGED


def plain_label(text: str) -> str:
    """Return ``text`` without HTML tags, whitespace collapsed."""
    return " ".join(_TAG_RE.sub(" ", text).split())


def choice_labels(choices: list[dict]) -> dict[str, str]:
    """Return each choice value's label; a value that several lists of a ``search()``
    select label differently gets their labels joined with `` | ``.
    """
    labels: dict[str, list[str]] = {}
    for c in choices:
        found = labels.setdefault(c["value"], [])
        if c["label"] not in found:
            found.append(c["label"])
    return {value: " | ".join(found) for value, found in labels.items()}


def _filter_fields(q: dict) -> list[str]:
    """Return the fields (``${name}``) whose values in a submission filter a
    ``search()`` select's list.
    """
    source = q["data_source"]
    if not source or source["kind"] != "search":
        return []
    return [m["value"] for m in source["match"] if m["value"].startswith("${")]


def gates(q: dict) -> list[str]:
    """Return what must hold for ``q`` to be asked: its groups' relevances, then its own."""
    return [*q["group_relevances"], *([q["relevance"]] if q["relevance"] else [])]


def gates_by_group(q: dict) -> str:
    """Return ``q``'s conditions joined with ``and``, each group's tagged with it."""
    parts = [
        g["relevance"] + (f"  [group {g['group']}]" if g["group"] else "")
        for g in q["gates"]
    ]
    return rule(parts) if len(parts) != 1 else parts[0]


def rule(conditions: list[str]) -> str:
    """Join conditions with ``and``, each in parentheses when there are several."""
    if len(conditions) == 1:
        return conditions[0]
    return " and ".join(f"({c})" for c in conditions)


def _tokens(text: str) -> list[str]:
    """Return the words of ``text`` (any script, accents kept), lowercased."""
    return _TOKEN_RE.findall(plain_label(text).lower())


_REPEAT_COUNT_TEXT = re.compile(r"Number of iterations in '(.*)' repeat group")


def _label(q: dict) -> str:
    """Return the words a question is searched by besides its name: its label, the
    repeat's label for a repeat count, nothing for a calculate's formula.
    """
    if q["type"] == "repeat_count":
        return _REPEAT_COUNT_TEXT.fullmatch(q["question_text"]).group(1)
    if q["question_text"] == q["calculation"]:
        return ""
    return q["question_text"]


def _name_tokens(name: str) -> list[str]:
    """Return a field name's parts and the name itself, lowercased: ``plotArea``
    gives ``plot``, ``area`` and ``plotarea``.
    """
    spaced = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", name)
    return [*_tokens(spaced.replace("_", " ").replace(".", " ")), name.lower()]


def _short(text: str, limit: int = 100) -> str:
    text = plain_label(text)
    return text if len(text) <= limit else text[: limit - 3] + "..."


_KINDS = {
    "note": "a note",
    "group": "a group's own column",
    "preload": "a preload (device or form metadata)",
    "not_in_form": "no field of the current form, written under another version",
}


def _kinds_text(summary: dict) -> str:
    kinds = summary["columns_without_question"]
    text = ", ".join(f"{n} {_KINDS[k]}" for k, n in kinds.items()) or "none"
    dropped = summary["n_empty_notes_and_groups_dropped"]
    return text + (
        f"; {dropped} note and group columns empty in every row dropped"
        if dropped
        else ""
    )


def _absent_text(found: list[dict]) -> str:
    text = f"conditions comparing a select with a code it lacks: {len(found)}"
    shown = "; ".join(
        f"{f['name']} ({f['in']}): {f['select']} has no {f['code']}"
        for f in found[:_LISTED]
    )
    more = f"; ... {len(found) - _LISTED} more" if len(found) > _LISTED else ""
    return text + (f" ({shown}{more})" if found else "")


def _withheld(q: dict, form: str) -> str:
    text = f"choices not listed ({', '.join(q['choices_withheld'])}); "
    if "search(" not in (q["appearance"] or ""):
        return text + f"they are in {form}.choices"
    text += f"they are in the dataset of `{q['appearance']}`"
    columns = q["choice_columns"]
    if columns:
        text += (
            f", value column `{columns['value']}`, label column `{columns['label']}`"
        )
    return text


def code_reasons(q: dict, variables: dict, dataset_columns: list[dict]) -> list[str]:
    """Return why select ``q``'s codes stay out of what an agent reads, empty when
    they are shown: its list is withheld for what it holds (reviewed, a Presidio
    hit), or a column that holds them, the select's own or its dataset's value
    column, has values that are not shown.
    """
    name = q["variable_name"]
    reasons = [
        f"the list is withheld ({r})"
        for r in q["choices_withheld"] or []
        if r == "reviewed" or r.startswith("presidio:")
    ]
    flagged = sorted(
        {
            v["pii"]["status"]
            for v in variables.values()
            if v["question"] == name and not _shows_values(v["pii"]["status"])
        }
    )
    if flagged:
        reasons.append(f"{name} is {', '.join(flagged)}")
    if q["data_source"] and q["choice_columns"]:
        value = q["choice_columns"]["value"]
        reasons += [
            f"{value} is {c['pii']['status']}"
            for c in dataset_columns
            if c["dataset"] == q["data_source"]["dataset"]
            and c["column"] == value
            and not _shows_values(c["pii"]["status"])
        ]
    return reasons


def coded_names(
    q: dict, variables: dict, dataset_columns: list[dict]
) -> dict[str, str]:
    """Return the name each column of select ``q`` is shown by when its name would
    show a code that is not shown, else nothing.

    A withheld select_multiple's binaries are named by its codes, so the columns of
    its n-th code are shown as ``<q>_<n>`` plus their instance suffix
    (``members_<2>_1``). The data keeps every column under its own name.
    """
    name = q["variable_name"]
    if (
        q["type"] != "select_multiple"
        or not q["choices_withheld"]
        or not code_reasons(q, variables, dataset_columns)
    ):
        return {}
    shown: dict[str, str] = {}
    codes: dict[str, int] = {}
    for column, v in variables.items():
        if v["question"] != name:
            continue
        suffix = (
            ""
            if v.get("ragged")
            else "".join(f"_{i}" for i in v.get("repeat_iteration", []))
        )
        n = codes.setdefault(column.removesuffix(suffix), len(codes) + 1)
        shown[column] = f"{name}_<{n}>{suffix}"
    return shown


def _source_line(source: dict) -> str:
    match = " and ".join(
        f"{source['dataset']}.{m['column']} = {m['value']}" for m in source["match"]
    )
    if source["kind"] == "enumerator":
        return (
            f"enumerator: picks a row of {source['dataset']} and stores its name and "
            'id as "name (id)"'
        )
    if source["kind"] == "pulldata":
        return f"pulldata: {source['dataset']}.{source['column']} where {match}"
    return f"search: choices from {source['dataset']}" + (
        f" where {match}" if match else ""
    )


_PII_LINE = (
    "-- Every view holds every column; dictionary.pii_status says which may hold "
    "personal data: use them in scripts, print only their counts and KEYs."
)


def render_structure(
    project: str, objects: list[dict], all_columns: bool = False, listed: int = _LISTED
) -> str:
    """Render ``<project>_db.json`` as commented SQL: grain, key, joins and columns.

    An object with more than ``listed`` columns lists that many unless
    ``all_columns``. A column named by a code that is not shown is shown by its
    ``shown_as`` (``coded_names``).
    """
    lines = [
        f"-- {project}.duckdb: every table and view, what one row is, its key and joins.",
        _PII_LINE,
    ]
    for o in objects:
        lines += ["", f"-- {o['kind']} {o['name']}: {o['grain']}"]
        lines.append(f"--   key: {', '.join(o['key'])}")
        lines += [f"--   join: {j}" for j in o["joins"]]
        columns = [f"{c.get('shown_as', c['name'])} {c['type']}" for c in o["columns"]]
        if len(columns) > listed and not all_columns:
            lines.append(
                f"--   columns ({len(columns)}): "
                + "".join(f"{c}, " for c in columns[:listed])
                + f"... get_structure_db('{_schema(o['name'])}', "
                f"'{o['name'].split('.', 1)[-1]}') lists all"
            )
        else:
            lines.append(f"--   columns ({len(columns)}): " + ", ".join(columns))
        if any("shown_as" in c for c in o["columns"]):
            lines.append(
                "--   <q>_<n>: a column named by the n-th code of the withheld list of "
                "select <q>, whose codes are not shown; dictionary.column_name has its "
                "name"
            )
    return "\n".join(lines)


def _schema(name: str) -> str:
    return name.split(".", 1)[0] if "." in name else "main"


def render_structure_summary(project: str, objects: list[dict]) -> str:
    """Summarise ``<project>_db.json``: the project tables in full, a line per dataset
    and per form schema.
    """
    schemas: dict[str, list[dict]] = {}
    for o in objects:
        schemas.setdefault(_schema(o["name"]), []).append(o)
    lines = [
        f"-- {project}.duckdb: {len(objects)} tables and views in {len(schemas)} "
        "schemas. get_structure_db(<schema>) maps one schema in full.",
        _PII_LINE,
    ]
    main = render_structure(project, schemas.pop("main"))
    lines += ["", "-- schema main: the project, from flow.json"]
    lines += main.splitlines()[2:]
    datasets = schemas.pop("dataset", [])
    lines += ["", f"-- schema dataset: {len(datasets)} datasets"]
    lines += [f"--   {o['name'].split('.', 1)[1]}: {o['grain']}" for o in datasets]
    for schema, members in schemas.items():
        width = next(
            len(o["columns"]) for o in members if o["name"].endswith(".submissions")
        )
        repeats = [o for o in members if o["kind"] == "view" and len(o["key"]) > 1]
        tables = [o for o in members if o["kind"] == "table"]
        deepest = max((len(o["key"]) - 1 for o in repeats), default=0)
        lines += [
            "",
            f"-- schema {schema}: submissions ({width} columns); repeat tables: "
            f"{len(repeats)}, nested up to {deepest} deep; description tables: "
            f"{len(tables)}",
        ]
    return "\n".join(lines)


def render_structure_schema(project: str, objects: list[dict], schema: str) -> str:
    """Render one schema of ``<project>_db.json`` in full.

    For a form, add the datasets it joins and its rows of the project's ``joins``.
    """
    names = {o["name"] for o in objects}
    if schema not in {_schema(n) for n in names}:
        raise ValueError(
            f"no schema {schema!r}; schemas: {sorted({_schema(n) for n in names})}"
        )
    picked = [o for o in objects if _schema(o["name"]) == schema]
    if schema not in ("main", "dataset"):
        # The datasets the form joins, with this form's joins only. A join line
        # quotes its names, as SQL does.
        quoted = '"' + schema.replace('"', '""') + '".'
        prefix = f"= {quoted}"
        for o in objects:
            mine = [j for j in o["joins"] if prefix in j]
            if _schema(o["name"]) != "dataset" or not mine:
                continue
            others = len(o["joins"]) - len(mine)
            if others:
                table = o["name"].split(".", 1)[1]
                mine.append(
                    f"... {others} more of other forms: "
                    f"get_structure_db('dataset', '{table}')"
                )
            picked.append({**o, "joins": mine})
        joins = next(o for o in objects if o["name"] == "joins")
        mine = [j for j in joins["joins"] if quoted in j]
        if mine:
            picked.append({**joins, "joins": mine})
    # A schema can hold dozens of tables: a table's columns are counted, listed by
    # get_structure_db(schema, table).
    return render_structure(project, picked, listed=0)


def _places(item: dict) -> str:
    forms = "; ".join(f"{f} ({', '.join(t)})" for f, t in item["forms"].items())
    return f"in {forms or 'no form'}; datasets: {', '.join(item['datasets']) or '-'}"


def render_project(flow: dict) -> str:
    """Render what the project is about: the user's description, entities and keys.

    The description and entities come from the config's ``[project]`` and
    ``[entities.*]``; the candidate keys from the outputs.
    """
    project = flow["project"]
    lines = [
        "About: "
        + (
            project["description"]
            or "not described yet. Ask the user what the project is about; a "
            "pre-analysis plan, replication paper or protocol helps. It goes in the "
            "config's [project] description."
        ),
        "",
    ]
    if project["entities"]:
        lines.append("Entities (named by the user):")
        for e in project["entities"]:
            parent = f"; part of {e['parent']}" if e["parent"] else ""
            key = ", ".join(e["key"])
            lines.append(f"  {e['name']} ({key}): {e['description']}{parent}")
            lines.append(f"    {_places(e)}")
    else:
        lines.append(
            "Entities: none named yet. Each goes in the config as [entities.<name>] "
            "with its key (one column, or a list of the columns that identify it "
            "together), a description and an optional parent."
        )
    named = {c for e in project["entities"] for c in e["key"]}
    candidates = [k for k in flow["keys"] if k["column"] not in named]
    if candidates:
        lines += ["", "Candidate keys (from the outputs, most widely carried first):"]
        for k in candidates:
            what = []
            if k["key_of"]:
                what.append(f"key of {', '.join(k['key_of'])}")
            if k["matched_by"]:
                what.append(f"matched by {k['matched_by']} reads")
            lines.append(f"  {k['column']}: {'; '.join(what)}; {_places(k)}")
    return "\n".join(lines)


def upstream_lines(flow: dict, form: str, name: str) -> list[str]:
    """Return where the dataset columns that ``form``'s field ``name`` reads come from."""
    datasets = {d["id"]: d for d in flow["datasets"]}
    lines = []
    for read in flow["reads"]:
        if read["form"] != form:
            continue
        d = datasets[read["dataset"]]
        for f in read["fields"]:
            if _leaf(f["field"]) != name:
                continue
            if not d["published_by"]:
                what = "an attached file" if d["kind"] == "form_file" else "external"
                lines.append(
                    f"Comes from: {d['id']} ({what}: no project form fills it"
                    f"{_closest(d)})"
                )
                continue
            if f["computed"]:
                lines.append(
                    f"Comes from: {d['id']}, the column named by {f['computed']}"
                )
            for column in f["columns"]:
                if column in f["missing"]:
                    lines.append(f"Comes from: {d['id']}.{column} (no such column)")
                if column in d["legacy_columns"]:
                    lines.append(
                        f"Comes from: {d['id']}.{column} (no field of "
                        f"{d['published_by']}'s current version)"
                    )
                if column not in d["publish_map"]:
                    continue
                origin = d["origins"][column]
                source = f" from {', '.join(origin['from'])}" if origin["from"] else ""
                lines.append(
                    f"Comes from: {d['id']}.{column} <- {d['published_by']}."
                    f"{d['publish_map'][column]} ({origin['kind']}{source})"
                )
    return lines


def _leaf(path: str) -> str:
    return path.rsplit("/", 1)[-1]


def _field_lines(d: dict, readers: dict[str, list[str]]) -> list[str]:
    """Return a dataset's columns one line per field that publishes them (by stem
    for the columns no field explains), with the fields that read them.
    """
    groups: dict[str, list[str]] = {}
    for column in d["columns"]:
        field = d["publish_map"].get(column)
        groups.setdefault(field or _STEM.sub("", column), []).append(column)
    lines = [
        f"  {len(d['columns'])} columns in {len(groups)} fields; "
        f"get_flow('{d['id']}', columns=True) lists each:"
    ]
    for key, cols in groups.items():
        first = cols[0]
        what = first if len(cols) == 1 else f"{first} ... {cols[-1]} ({len(cols)})"
        field = d["publish_map"].get(first)
        line = f"  {what}"
        if field:
            origin = d["origins"][first]
            line += f"  <- {d['published_by']}.{field} ({origin['kind']}"
            line += f" from {', '.join(origin['from'])})" if origin["from"] else ")"
        elif first in d["legacy_columns"]:
            line += f"  (no field of {d['published_by']}'s current version)"
        read = list(dict.fromkeys(r for c in cols for r in readers.get(c, [])))
        if read:
            line += f"  -> {_capped(read)}"
        lines.append(line)
    lines += [
        f"  {column}  no such column; read by {', '.join(fields)}"
        for column, fields in readers.items()
        if column not in d["columns"]
    ]
    return lines


def _closest(d: dict) -> str:
    """Return the form covering most of an external dataset's columns, if any."""
    c = d["closest"]
    if not c:
        return ""
    return (
        f"; {c['columns']} of its {len(d['columns'])} columns are fields of "
        f"{c['form']}: set [datasets.{d['id']}] published_by if it publishes it"
    )


def _legacy(d: dict) -> str:
    n = len(d["legacy_columns"])
    return f"; {n} columns no field of its current version" if n else ""


_ORIGINS = ("entered", "calculated", "carried", "metadata")


def _origin_text(d: dict) -> str:
    """Return a published dataset's column origins: ``4 entered, 7 carried from x``."""
    counts = d["origin_counts"]
    carried_from = sorted({x for o in d["origins"].values() for x in o["from"]})
    return ", ".join(
        f"{counts[k]} {k}"
        + (f" from {', '.join(carried_from)}" if k == "carried" else "")
        for k in _ORIGINS
        if k in counts
    )


def _tone(d: dict) -> str:
    """Return how a dataset is filled: entered, carried, mixed or external."""
    if not d["published_by"]:
        return "external"
    counts = d["origin_counts"]
    if not counts.get("carried"):
        return "entered"
    return "mixed" if counts.get("entered") or counts.get("calculated") else "carried"


def _mermaid_id(prefix: str, name: str) -> str:
    return prefix + re.sub(r"\W", "_", name)


def _mermaid_text(text: str) -> str:
    return text.replace('"', "#quot;")


def render_mermaid(flow: dict) -> str:
    """Render ``flow.json`` as a Mermaid flowchart: forms, datasets, publishes, reads.

    A dataset's colour says how it is filled: green when its columns come from the
    publishing form's answers (entered or calculated from them), orange when they are
    carried from another dataset, yellow when both, grey when no project form fills it.
    """
    lines = ["flowchart LR"]
    for f in flow["forms"]:
        fid = _mermaid_id("f_", f["form_id"])
        lines.append(f'  {fid}["{_mermaid_text(f["form_id"])}<br/>stage {f["stage"]}"]')
        lines.append(f"  class {fid} form")
    for d in flow["datasets"]:
        did = _mermaid_id("d_", d["id"])
        label = f"{d['id']}<br/>{d['rows']} rows"
        if d["published_by"]:
            label += f"<br/>{_origin_text(d)}"
        lines.append(f'  {did}[("{_mermaid_text(label)}")]')
        lines.append(f"  class {did} {_tone(d)}")
        if d["published_by"]:
            lines.append(
                f"  {_mermaid_id('f_', d['published_by'])} -->|publishes| {did}"
            )
    for r in flow["reads"]:
        arrow = "-->" if r["attached"] else "-.->"
        label = f"{len(r['fields'])} fields" + (
            "" if r["attached"] else ", not attached"
        )
        lines.append(
            f"  {_mermaid_id('d_', r['dataset'])} {arrow}|{label}| "
            f"{_mermaid_id('f_', r['form'])}"
        )
    lines += [
        "  classDef form fill:#e3f2fd,stroke:#1565c0",
        "  classDef entered fill:#c8e6c9,stroke:#2e7d32",
        "  classDef carried fill:#ffe0b2,stroke:#ef6c00",
        "  classDef mixed fill:#fff59d,stroke:#f9a825",
        "  classDef external fill:#eeeeee,stroke:#757575",
    ]
    return "\n".join(lines)


def _role(read: dict, column: str) -> str:
    """Return how a field uses a dataset column: the value it stores, the key or filter
    it matches rows on, or a label it only shows.
    """
    if column in read["match"]:
        return f"{read['via']} {'key' if read['via'] == 'pulldata' else 'filter'}"
    if read["via"] == "search" and column != read["value"]:
        return "search label"
    return f"{read['via']} value"


def render_flow(flow: dict, dataset: str | None = None, columns: bool = False) -> str:
    """Render ``flow.json``: forms by stage, then each dataset's publisher and readers.

    With ``dataset``, list its columns instead: the field each one is published from
    and the fields that read it. Past ``_LISTED`` columns, the columns of one field
    (a repeat's ``score_1`` ... ``score_9``) share a line; ``columns`` lists each.
    """
    datasets = {d["id"]: d for d in flow["datasets"]}
    if dataset is not None:
        d = datasets[dataset]
        lines = [
            f"{d['id']} ({d['title']}): {d['rows']} rows, key {d['key'] or '-'}, "
            f"published by {d['published_by'] or 'no project form (external)'}"
            f"{_legacy(d) if d['published_by'] else _closest(d)}"
        ]
        readers: dict[str, list[str]] = {}
        for r in flow["reads"]:
            if r["dataset"] != dataset:
                continue
            for f in r["fields"]:
                for column in f["columns"]:
                    readers.setdefault(column, []).append(
                        f"{r['form']}.{_leaf(f['field'])} ({_role(f, column)})"
                    )
        if not columns and len(d["columns"]) > _LISTED:
            return "\n".join(lines + _field_lines(d, readers))
        for column in d["columns"]:
            source = d["publish_map"].get(column)
            line = f"  {column}"
            if source:
                origin = d["origins"][column]
                line += f"  <- {d['published_by']}.{source} ({origin['kind']}"
                line += f" from {', '.join(origin['from'])})" if origin["from"] else ")"
            elif column in d["legacy_columns"]:
                line += f"  (no field of {d['published_by']}'s current version)"
            if column in readers:
                line += f"  -> {', '.join(readers[column]) if columns else _capped(readers[column])}"
            lines.append(line)
        lines += [
            f"  {column}  no such column; read by {', '.join(fields)}"
            for column, fields in readers.items()
            if column not in d["columns"]
        ]
        return "\n".join(lines)

    lines = []
    for stage in sorted({f["stage"] for f in flow["forms"]}):
        lines.append(f"Stage {stage}:")
        for f in flow["forms"]:
            if f["stage"] != stage:
                continue
            line = f"  {f['form_id']}"
            if f["reads_from"]:
                line += f"  (reads datasets published by {', '.join(f['reads_from'])})"
            lines.append(line)
            if f["publishes"]:
                lines.append(f"    publishes: {', '.join(f['publishes'])}")
    lines += ["", "Datasets:"]
    for d in flow["datasets"]:
        source = (
            f"published by {d['published_by']} ({_origin_text(d)}){_legacy(d)}"
            if d["published_by"]
            else ("attached file" if d["kind"] == "form_file" else "external")
            + _closest(d)
        )
        readers = ", ".join(d["read_by"]) or "no project form"
        lines.append(
            f"  {d['id']}: {d['rows']} rows, key {d['key'] or '-'}; {source}; "
            f"read by {readers}"
        )
    unattached = [r for r in flow["reads"] if not r["attached"]]
    if unattached:
        lines += ["", "Read without being attached to the form on the server:"]
        lines += [
            f"  {r['form']} reads {r['dataset']} ("
            + ", ".join(_leaf(f["field"]) for f in r["fields"])
            + ")"
            for r in unattached
        ]
    return "\n".join(lines)


class SurveyStore:
    """One form's questions, dictionary and graph."""

    def __init__(self, form_dir: Path, form_id: str):
        """Load the three JSON outputs from ``form_dir``."""

        def load(suffix: str):
            path = Path(form_dir) / f"{form_id}_{suffix}.json"
            return json.loads(path.read_text(encoding="utf-8"))

        self.form_id = form_id
        self.form_dir = Path(form_dir)
        self.questions = {q["variable_name"]: q for q in load("questions")}
        dictionary = load("variable_dictionary")
        self.dataset, self.summary = dictionary["dataset"], dictionary["summary"]
        self.variables = dictionary["variables"]
        self.graph = load("variable_graph")
        self.columns = {n["id"]: n["columns"] for n in self.graph["nodes"]}
        # Questions no submission answered: how many submissions reach them.
        self.reached = {
            n["id"]: n["reached"] for n in self.graph["nodes"] if "reached" in n
        }
        self.repeat_of = {n["id"]: n["repeat_group"] for n in self.graph["nodes"]}
        self.dataset_columns = load("dataset_codebook")
        self.review_file = f"{form_id}_pii_review.xlsx"
        self.project = self.form_dir.parent.name
        self.flow = json.loads(
            (self.form_dir.parent / "flow.json").read_text(encoding="utf-8")
        )

    def read(self, dataset: str, path: str) -> tuple[dict, dict]:
        """Return the ``flow.json`` dataset this form names ``dataset`` and the read of
        it by field ``path``.
        """
        datasets = {d["id"]: d for d in self.flow["datasets"]}
        for r in self.flow["reads"]:
            if r["form"] == self.form_id and r["name_in_form"] == dataset:
                for f in r["fields"]:
                    if f["field"] == path:
                        return datasets[r["dataset"]], f
        raise KeyError(f"{self.form_id}: {path} does not read {dataset}")

    # -- lookups -------------------------------------------------------------------

    def _column_line(self, name: str, shown: str | None = None) -> str:
        """Return a column's line, the column named ``shown`` when given."""
        v = self.variables[name]
        parts = [
            f"  {shown or name}  {v['parquet']['arrow_type']}  "
            f"missing {v['missing_rate']:.1%}"
        ]
        if "choice_value" in v:
            parts.append(
                ", ".join(f"{c['value']} = {c['label']}" for c in v["value_labels"])
            )
        if "data_min" in v and _shows_values(v["pii"]["status"]):
            parts.append(f"range {v['data_min']}..{v['data_max']}")
        if "max_length" in v:
            parts.append(
                f"longest {v['max_length']} chars ({v['at_max_length']} values that long)"
            )
        if "sentinels" in v:
            codes = ", ".join(
                f"{c} {s['label']} x{s['count']}" for c, s in v["sentinels"].items()
            )
            parts.append(f"sentinels {codes}")
        if "cast_fallback" in v["parquet"]:
            parts.append(f"kept as text: {v['parquet']['cast_fallback']}")
        if v.get("ragged"):
            parts.append("ragged: another form version's layout")
        pii = v["pii"]
        parts.append(f"pii: {pii['status']} ({', '.join(pii['basis'])})")
        return "  ".join(parts)

    def _columns_summary(
        self, name: str, columns: list[str], shown: dict[str, str]
    ) -> str:
        entries = [self.variables[c] for c in columns]
        instances = {tuple(v.get("repeat_iteration", [])) for v in entries}
        choices = {v["choice_value"] for v in entries if "choice_value" in v}
        rates = [v["missing_rate"] for v in entries]
        first, last = (shown.get(c, c) for c in (columns[0], columns[-1]))
        parts = [f"Columns: {len(columns)}, {first} ... {last}"]
        # Slots, not instances: score_3 is the third instance of every submission.
        if instances != {()}:
            parts.append(f"{len(instances)} repeat slots")
        if choices:
            parts.append(f"{len(choices)} codes with a column")
        ragged = sum(1 for v in entries if v.get("ragged"))
        if ragged:
            parts.append(f"{ragged} from another form version (ragged)")
        parts += [
            f"missing rate {min(rates)}-{max(rates)}",
            f"pii {dict(Counter(v['pii']['status'] for v in entries))}",
        ]
        return "; ".join(parts) + (
            f". lookup_variable('{name}', columns=True) lists each."
        )

    def _render_question(
        self, q: dict, all_columns: bool = False, listed: int | None = None
    ) -> str:
        lines = [f"{q['variable_name']} ({q['type']})"]
        # An unlabelled calculate's text is its formula, shown as Calculation below.
        if q["question_text"] and q["question_text"] != q["calculation"]:
            lines.append(f"Text: {q['question_text']}")
        if q["hint"]:
            lines.append(f"Hint: {q['hint']}")
        if q["group_path"]:
            lines.append(f"Group: {'/'.join(q['group_path'])}")
        # A search() appearance is shown as the data source.
        if q["appearance"] and "search(" not in q["appearance"]:
            lines.append(f"Appearance: {q['appearance']}")
        calculation = (
            "Default (computed; the user can change it)"
            if q["calculation_is_default"]
            else "Calculation"
        )
        for label, key in (
            ("Relevance", "relevance"),
            ("Constraint", "constraint"),
            ("Constraint message", "constraint_message"),
            (calculation, "calculation"),
        ):
            if q[key]:
                lines.append(f"{label}: {q[key]}")
        for gate in q["gates"]:
            if gate["group"]:
                lines.append(f"Group relevance ({gate['group']}): {gate['relevance']}")
        if q["choices_withheld"]:
            lines.append(_withheld(q, self.form_id))
        elif q["choices"] and _filter_fields(q):
            lines.append(
                f"Choices: {len(q['choices'])}, from the dataset rows the submissions "
                f"reach; {self._lists_text(q)}; get_choice_list lists them"
            )
        elif q["choices"]:
            lines.append(_choices_line(q))
        if q["choice_filter"]:
            lines.append(_filter_line(q))
        if q["choices_per_submission"] and q["type"] == "select_multiple":
            lines.append(
                "Binaries: only for the codes someone picked (the form filters the "
                "list per submission, or the list stays in its dataset)."
            )
        lines += self._qualifies_lines(q["variable_name"])
        first = (self.columns.get(q["variable_name"]) or [None])[0]
        if first and "sentinels_allowed" in self.variables[first]:
            allowed = self.variables[first]["sentinels_allowed"]
            lines.append(
                "Non-response codes its constraint accepts: "
                + (
                    "not read (the constraint reads other fields)"
                    if allowed is None
                    else ", ".join(map(str, allowed)) or "none"
                )
            )
        if q["data_source"]:
            lines.append(f"Data source: {_source_line(q['data_source'])}")
            lines += upstream_lines(self.flow, self.form_id, q["variable_name"])
        if q["publishable"]:
            lines.append("Publishable: yes")
        columns = self.columns.get(q["variable_name"], [])
        shown = coded_names(q, self.variables, self.dataset_columns)
        if len(columns) > (_LISTED if listed is None else listed) and not all_columns:
            lines.append(self._columns_summary(q["variable_name"], columns, shown))
        else:
            lines.append(
                "Columns:" if columns else "Columns: none in the data" + self._reach(q)
            )
            lines += [self._column_line(c, shown.get(c)) for c in columns]
        if shown:
            lines.append(
                f"Column names: {len(shown)} are named by the codes of its withheld "
                f"list, shown as {q['variable_name']}_<n> for the n-th code; the data "
                "keeps their names."
            )
        if any(self.variables[c]["pii"]["status"] in _FLAGGED for c in columns):
            lines.append(
                "PII: use flagged columns in scripts like any other, but print only "
                f"their counts and KEYs; the team checks the flags in {self.review_file}."
            )
        return "\n".join(lines)

    def lookup_variable(
        self, name: str, columns: bool = False, listed: int | None = None
    ) -> str:
        """Describe a question, or the column ``name`` and its question.

        A question with more than ``listed`` columns (default 20: a repeat, a long
        choice list) gets a summary of them; ``columns`` lists each.
        """
        if name in self.questions:
            return self._render_question(self.questions[name], columns, listed)
        if name in self.variables:
            question = self.variables[name]["question"]
            if question is not None:
                return self._render_question(self.questions[question], columns, listed)
            v = self.variables[name]
            what = _KINDS[v["column_kind"]] if "column_kind" in v else "a system column"
            return (
                f"{name} (column without a question: {what})\n{self._column_line(name)}"
            )
        coded = {
            c
            for q in self.questions.values()
            for c in coded_names(q, self.variables, self.dataset_columns)
        }
        close = difflib.get_close_matches(
            name,
            [
                n
                for n in dict.fromkeys([*self.questions, *self.variables])
                if n not in coded
            ],
            n=5,
        )
        hint = f" Close matches: {', '.join(close)}." if close else ""
        return f"No variable or question named {name!r}.{hint}"

    def lookup_variables(self, names: list[str], columns: bool = False) -> str:
        """Describe several variables; with more than one, a question's columns are
        summarised unless ``columns``.
        """
        listed = None if len(names) == 1 else 1
        return "\n\n".join(self.lookup_variable(n, columns, listed) for n in names)

    def search_matches(self, query: str) -> tuple[dict, dict]:
        """Return, per query word, the questions whose name or label hold it and
        those whose hint or listed choice labels do (and not the first).
        """
        docs = {
            n: set(_name_tokens(n)) | set(_tokens(_label(q)))
            for n, q in self.questions.items()
        }
        hints = {
            n: set(_tokens(q["hint"] or ""))
            | {t for c in q["choices"] or [] for t in _tokens(c["label"])}
            for n, q in self.questions.items()
        }

        def holding(w: str, texts: dict[str, set[str]]) -> set[str]:
            # A word of four letters or more also matches the words it starts
            # ("child" finds "children").
            return {
                n
                for n, toks in texts.items()
                if w in toks or (len(w) >= 4 and any(t.startswith(w) for t in toks))
            }

        matched = {w: holding(w, docs) for w in _query_words(query)}
        hinted = {w: holding(w, hints) - matched[w] for w in matched}
        return matched, hinted

    def search_scored(
        self, query: str, idf: dict[str, float] | None = None
    ) -> tuple[list[tuple[tuple[float, bool, float], str]], set[str]]:
        """Rank questions by the query words their name, label, hint or listed
        choice labels hold, each word weighed by its IDF (a rare word outranks a
        common one) and a hint or choice label counting half; then questions someone
        answers above calculates and repeat counts, then the number of words held. A
        question named exactly ``query`` comes first. Also return the query words no
        question holds. ``idf`` is the words' IDF over several forms; by default,
        over this one.
        """
        matched, hinted = self.search_matches(query)
        if idf is None:
            idf = _idf(matched, [(matched, hinted, len(self.questions))])
        # Each word counts once per question, so long texts do not win on common words.
        scores = {}
        for n in self.questions:
            weights = {
                w: 1.0 if n in matched[w] else 0.5 if n in hinted[w] else 0.0
                for w in idf
            }
            scores[n] = (
                sum(idf[w] * weight for w, weight in weights.items()),
                self.questions[n]["type"] not in ("calculate", "repeat_count"),
                sum(weights.values()),
            )
        if query.strip() in scores:
            scores[query.strip()] = (math.inf, True, math.inf)
        ranked = sorted(
            ((s, n) for n, s in scores.items() if s[0] > 0),
            key=lambda x: (-x[0][0], -x[0][1], -x[0][2], x[1]),
        )
        return ranked, {w for w in matched if not matched[w] | hinted[w]}

    def search_line(self, name: str) -> str:
        """Return a search hit: the question's name, type and short text, and its
        columns' PII status when any is flagged.
        """
        q = self.questions[name]
        flagged = sorted(
            {
                self.variables[c]["pii"]["status"]
                for c in self.columns.get(name, [])
                if self.variables[c]["pii"]["status"] in _FLAGGED
            }
        )
        tag = f"  [{', '.join(flagged)}]" if flagged else ""
        return f"{name} ({q['type']}): {_short(q['question_text'])}{tag}"

    def search_questions(self, query: str, max_results: int = 20) -> str:
        """Rank the form's questions by the words of ``query`` in their name or text."""
        ranked, unmatched = self.search_scored(query)
        if not ranked:
            return f"No question of {self.form_id} matches {query!r}."
        return "\n".join(
            _unmatched_lines(unmatched)
            + [self.search_line(n) for _, n in ranked[:max_results]]
        )

    def get_group(self, group: str) -> str:
        """List a group's questions in form order, with their type and condition."""
        members = [q for q in self.questions.values() if group in q["group_path"]]
        if not members:
            groups = sorted(
                {g for q in self.questions.values() for g in q["group_path"]}
            )
            close = difflib.get_close_matches(group, groups, n=5)
            return f"No group named {group!r}." + (
                f" Close: {', '.join(close)}" if close else ""
            )
        lines = [f"{group}: {len(members)} questions"]
        own = next(
            (g for q in members for g in q["gates"] if g["group"] == group), None
        )
        if own:
            lines[0] += f", asked if {own['relevance']}"
        # The groups it sits in gate it too, outermost first.
        path = members[0]["group_path"]
        outer = path[: path.index(group)]
        lines += [
            f"  inside {g['group']}, asked if {g['relevance']}"
            for g in members[0]["gates"]
            if g["group"] in outer
        ]
        shown: set[str] = set()
        for q in members:
            inner = q["group_path"][q["group_path"].index(group) + 1 :]
            # Each subgroup's condition once, where its questions start.
            for g in q["gates"]:
                if g["group"] in inner and g["group"] not in shown:
                    shown.add(g["group"])
                    lines.append(f"  -- {g['group']}: if {g['relevance']}")
            where = f" [{'/'.join(inner)}]" if inner else ""
            when = f"  if {q['relevance']}" if q["relevance"] else ""
            lines.append(f"  {q['variable_name']} ({q['type']}){where}{when}")
        return "\n".join(lines)

    def _reach(self, q: dict) -> str:
        """Return whether a question no submission answered was reached."""
        name = q["variable_name"]
        if name not in self.reached:
            return ""
        n = self.reached[name]
        # With no submissions counted, nothing is reached, gated or not.
        if self.dataset["n_observations"] == 0:
            return "; no submissions to reach it"
        if n is None:
            return "; whether it was reached is not evaluated (its conditions)"
        if n == 0:
            return "; never reached: its conditions held for no submission"
        return (
            f"; reached in {n} of {self.dataset['n_observations']} submissions, "
            "never answered"
        )

    def get_choice_list(self, name: str) -> str:
        """List a select question's choices."""
        q = self.questions.get(name)
        if q is None:
            return self.lookup_variable(name)
        if q["choices_withheld"]:
            return "\n".join(self._withheld_lines(q))
        if q["type"] not in ("select_one", "select_multiple"):
            return f"{name} ({q['type']}) is not a select question."
        lines = [f"{name} ({q['type']}):"]
        if q["choice_filter"]:
            lines.append(f"  {_filter_line(q)}")
        if _filter_fields(q):
            lines.append(f"  {self._lists_text(q)}")
        lines += [
            f"  {c['value']} = {c['label']}"
            + (
                f"  [{_columns_text(c['filter_columns'])}]"
                if "filter_columns" in c
                else ""
            )
            for c in q["choices"]
        ]
        return "\n".join(lines)

    def _lists_text(self, q: dict) -> str:
        """Return where a ``search()`` list filtered by fields keeps each choice's
        list: its filter values are the fields' values in the submissions.
        """
        return (
            f"one list per value of {', '.join(_filter_fields(q))} in the "
            f"submissions; each choice's filter values: SELECT value, label, "
            f"filter_values FROM {self.form_id}.choices WHERE question = "
            f"'{q['variable_name']}'"
        )

    def _qualifies_lines(self, name: str) -> list[str]:
        """Return the questions whose conditions or text read ``name``: an answer that
        means little without this one.
        """
        ref = "${" + name + "}"
        gated = [
            o
            for o, q in self.questions.items()
            if o != name and any(ref in g["relevance"] for g in q["gates"])
        ]
        worded = [
            o
            for o, q in self.questions.items()
            if o != name and ref in (q["question_text"] or "")
        ]
        lines = []
        if gated:
            lines.append(f"Asks or skips: {_capped(gated)}")
        if worded:
            lines.append(f"Named in the text of: {_capped(worded)}")
        return lines

    def _dataset_lines(self, source: dict, columns: dict, path: str) -> list[str]:
        """Return where a withheld ``search()`` list's dataset is and how a script
        decodes its codes.
        """
        d, _ = self.read(source["dataset"], path)
        value, label = columns["value"], columns["label"]
        status = {
            c["column"]: c["pii"]["status"]
            for c in self.dataset_columns
            if c["dataset"] == source["dataset"]
        }
        where = " AND ".join(
            f"{m['column']} = <the submission's {m['value']}>"
            if m["value"].startswith("${")
            else f"{m['column']} = {m['value']}"
            for m in source["match"]
        )
        # A label can name several columns, the value column among them: name,id.
        labels = [c.strip() for c in label.split(",")]
        selected = ", ".join([value, *(c for c in labels if c != value)])
        return [
            f"  The rest: in {self.project}.duckdb dataset.{d['id']}; value column "
            f"{value} ({status[value]}), label "
            + ("columns " if len(labels) > 1 else "column ")
            + ", ".join(f"{c} ({status[c]})" for c in labels),
            f'  A script decodes them: SELECT {selected} FROM dataset."{d["id"]}"'
            + (f" WHERE {where}" if where else ""),
        ]

    def _withheld_lines(self, q: dict) -> list[str]:
        """Return why a list is left out, the form's own choices, where a script reads
        the rest and how, and the codes the submissions picked.
        """
        name = q["variable_name"]
        lines = [f"{name} ({q['type']}): {_withheld(q, self.form_id)}"]
        if q["choices"]:
            lines.append(
                "  The form's own choices: "
                + "; ".join(f"{c['value']} = {c['label']}" for c in q["choices"])
            )
        source, columns = q["data_source"], q["choice_columns"]
        if source and not columns:
            return lines
        # An inline list withheld by the blacklist is only in <form>.choices.
        if source:
            lines += self._dataset_lines(source, columns, _path(q))
        # A list filtered by an expression has no choices known before a submission.
        if not any(r.startswith("filtered by ") for r in q["choices_withheld"]):
            lines.append(
                f"  Every choice, with its filter values: SELECT value, label, filter_values "
                f"FROM {self.form_id}.choices WHERE question = '{name}'"
            )
        picked = self.summary["withheld_choices"].get(name)
        if picked is None:
            lines.append("  In the data: no submission picked a code")
            return lines
        n, missing = picked["n_codes_picked"], picked["n_codes_not_in_list"]
        line = f"  In the data: {n} code{'s' if n > 1 else ''} picked"
        hidden = code_reasons(q, self.variables, self.dataset_columns)
        if not missing:
            line += ", all in the list"
        elif "codes_not_in_list" in picked and not hidden:
            codes = ", ".join(picked["codes_not_in_list"])
            line += f"; {missing} not in the list: {codes}"
        else:
            line += (
                f"; {missing} not in the list (codes not shown: {'; '.join(hidden)})"
            )
        return [*lines, line]

    def get_gate_chain(self, name: str, depth: int = 3) -> str:
        """Show the conditions that must hold for ``name`` to be asked, and their gates."""
        if name not in self.questions:
            return self.lookup_variable(name)
        lines: list[str] = []
        seen: set[str] = set()

        def walk(var: str, level: int) -> None:
            q = self.questions[var]
            pad = "  " * level
            conditions = gates(q)
            lines.append(f"{pad}{var}: {gates_by_group(q) or 'always asked'}")
            seen.add(var)
            if level >= depth:
                return
            for ref in dict.fromkeys(r for g in conditions for r in _REF_RE.findall(g)):
                if ref in self.questions and ref not in seen:
                    walk(ref, level + 1)

        walk(name, 0)
        return "\n".join(lines)

    def get_variable_neighborhood(self, name: str, depth: int = 1) -> str:
        """List graph edges within ``depth`` hops of ``name``."""
        if name not in self.columns:
            return self.lookup_variable(name)
        reached, frontier = {name}, {name}
        for _ in range(depth):
            # A group's gate reaches every question in the group: it is followed from
            # a question to its gate, not from the gate to the group's questions.
            frontier = {
                other
                for e in self.graph["edges"]
                for node, other, way in (
                    (e["source"], e["target"], "out"),
                    (e["target"], e["source"], "in"),
                )
                if node in frontier
                and other not in reached
                and not (e["type"] == "group_gated_by" and way == "out")
            }
            reached |= frontier
        gated: dict[tuple[str, str], int] = {}
        for e in self.graph["edges"]:
            if e["type"] == "group_gated_by" and e["source"] in reached:
                key = (e["source"], self._gated_group(e))
                gated[key] = gated.get(key, 0) + 1
        edges = sorted(
            {
                f"{e['source']} -> {e['target']} ({e['type']})"
                for e in self.graph["edges"]
                if e["type"] != "group_gated_by"
                and e["source"] in reached
                and e["target"] in reached
            }
            | {
                f"{source} gates group {group} ({n} questions)"
                for (source, group), n in gated.items()
            }
        )
        lines = []
        repeat = self.repeat_of.get(name)
        if repeat:
            members = self.graph["repeat_groups"][repeat]["members"]
            lines.append(
                f"{name} is in repeat {repeat} with {len(members)} questions "
                f"(get_repeat_structure('{repeat}') lists them)."
            )
        if len(edges) > 200:
            lines += edges[:200]
            lines.append(
                f"... {len(edges) - 200} more links; lower depth to see fewer."
            )
        else:
            lines += edges or [f"{name} has no calculation, gate or constraint links."]
        return "\n".join(lines)

    def _gated_group(self, edge: dict) -> str:
        """Return the group whose condition makes ``edge``'s source gate its target."""
        for g in self.questions[edge["target"]]["gates"]:
            if g["group"] and edge["source"] in _REF_RE.findall(g["relevance"]):
                return g["group"]
        raise ValueError(f"{edge}: no group condition of the target reads the source")

    def get_repeat_structure(self, repeat: str | None = None) -> str:
        """Show the repeat groups, their nesting, counts and first members; with
        ``repeat``, that repeat's members in full.
        """
        groups = self.graph["repeat_groups"]
        if not groups:
            return "The form has no repeat groups."
        if repeat is not None and repeat not in groups:
            raise ValueError(f"no repeat {repeat!r}; repeats: {list(groups)}")
        lines = []
        for name, g in groups.items():
            if repeat not in (None, name):
                continue
            count = g["count"] or "none: as many instances as were filled in"
            members = g["members"]
            shown = members if repeat or len(members) <= _LISTED else members[:_LISTED]
            more = len(members) - len(shown)
            lines += [
                f"{name} (depth {g['depth']}, parent {g['parent'] or '-'}, count: {count})",
                f"  members ({len(members)}): {', '.join(shown)}"
                + (
                    f", ... {more} more; get_repeat_structure('{name}')" if more else ""
                ),
            ]
            if repeat is not None:
                lines += self._instance_lines(g)
        return "\n".join(lines)

    def _instance_lines(self, g: dict) -> list[str]:
        """Return what sets a repeat's instances: the fields its count reads and the
        member calculates that read ``index()``, as the form writes them.
        """
        lines = []
        for ref in dict.fromkeys(_REF_RE.findall(g["count"] or "")):
            q = self.questions.get(ref)
            if q is None:
                continue
            what = (
                f"= {_short(q['calculation'], 160)}"
                if q["calculation"]
                else f"({q['type']}) {_short(q['question_text'])}"
            )
            lines.append(f"  count reads {ref} {what}")
        indexed = [
            self.questions[m]
            for m in g["members"]
            if m in self.questions
            and "index()" in (self.questions[m]["calculation"] or "")
        ]
        for default, what in (
            (False, "calculates that read index()"),
            (True, "defaults that read index(); the user can change them"),
        ):
            set_by = [q for q in indexed if q["calculation_is_default"] == default]
            if set_by:
                lines.append(f"  set per instance ({what}):")
                lines += [
                    f"    {q['variable_name']} = {_short(q['calculation'], 160)}"
                    for q in set_by
                ]
        return lines

    def _table_of(self, value: str | None) -> str:
        """Return the table a ``${field}`` lives in: submissions or its repeat view."""
        match = _REF_RE.fullmatch(value or "")
        if match is None:
            return "a literal or expression"
        return self.repeat_of.get(match.group(1)) or "submissions"

    def get_datasets(self, dataset: str | None = None, columns: bool = False) -> str:
        """Describe each dataset the form reads and how its rows join to the form.

        A join column's values past ``_LISTED`` and a dataset's columns past
        ``_LISTED`` are summarised; ``dataset`` gives one dataset's joins in full and
        ``columns`` lists each column.
        """
        by_dataset: dict[str, list[dict]] = {}
        for column in self.dataset_columns:
            by_dataset.setdefault(column["dataset"], []).append(column)
        if not by_dataset:
            return "The form reads no datasets."
        if dataset is not None and dataset not in by_dataset:
            raise ValueError(f"the form reads no {dataset!r}: {list(by_dataset)}")
        id_of, read_of = {}, {}
        for r in self.flow["reads"]:
            if r["form"] == self.form_id:
                id_of[r["name_in_form"]] = r["dataset"]
                for f in r["fields"]:
                    read_of[r["name_in_form"], f["field"]] = f
        blocks = []
        for name, cols in by_dataset.items():
            if dataset not in (None, name):
                continue
            lines = self._dataset_head(name, cols, id_of[name])
            lines += self._join_lines(name, cols, read_of, full=dataset is not None)
            lines += self._dataset_column_lines(name, cols, columns)
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def _dataset_head(self, name: str, cols: list[dict], dataset_id: str) -> list[str]:
        statuses = dict(Counter(c["pii"]["status"] for c in cols))
        view = f"dataset.{dataset_id}"
        return [
            f"{name}: {cols[0]['rows']} rows, {len(cols)} columns, pii {statuses}",
            f"  In {self.project}.duckdb: {view} (every column, plus row).",
        ]

    def _join_lines(
        self, name: str, cols: list[dict], read_of: dict, full: bool
    ) -> list[str]:
        """Return how the dataset's rows join to the form: per match column, its
        uniqueness once, then each value matched and the fields that match it.
        """
        joins: dict[str | None, dict[str | None, list[str]]] = {}
        for q in self.questions.values():
            source = q["data_source"]
            if not source or source["dataset"] != name:
                continue
            read = read_of[name, _path(q)]
            if source["kind"] == "enumerator":
                field = "${" + q["variable_name"] + "}"
                joins.setdefault("id", {}).setdefault(field, []).append(
                    f'{q["variable_name"]} stores "name (id)", the id in parentheses'
                )
                continue
            if source["kind"] == "search":
                what = f"{q['variable_name']} (choices)"
            elif read["computed"]:
                what = f"{q['variable_name']} <- the column named by {source['column']}"
            else:
                what = f"{q['variable_name']} <- {source['column']}"
                if source["column"] in read["missing"]:
                    what += " (no such column)"
            for m in source["match"] or [{"column": None, "value": None}]:
                joins.setdefault(m["column"], {}).setdefault(m["value"], []).append(
                    what
                )
        by_name = {c["column"]: c for c in cols}
        lines = [
            "  Joins to the form (dataset column = form value: fields; `<- column` "
            "reads it, `(choices)` takes its choices from the matching rows):"
        ]
        for column, values in joins.items():
            if column is None:
                lines.append(f"    (no filter): {'; '.join(values[None])}")
                continue
            if column not in by_name:
                lines.append(f"    {name}.{column}: no such column in {name}")
            else:
                unique = (
                    _not_unique(by_name[column]) or "unique: one dataset row per match"
                )
                lines.append(f"    {name}.{column} ({unique}) =")
            items = list(values.items())
            shown = items if full else items[:_LISTED]
            lines += [
                f"      {value}"
                + (f" (in {self._table_of(value)})" if _REF_RE.fullmatch(value) else "")
                + f": {_capped(uses)}"
                for value, uses in shown
            ]
            if len(shown) < len(items):
                lines.append(
                    f"      ... {len(items) - len(shown)} more values; "
                    f"get_datasets('{self.form_id}', '{name}') lists each"
                )
        return lines

    def _dataset_column_lines(
        self, name: str, cols: list[dict], every: bool
    ) -> list[str]:
        """Return the dataset's columns, one line each, or past ``_LISTED`` one line
        per stem (``score`` for ``score_1`` ... ``score_9``).
        """
        n_rows = cols[0]["rows"]
        if every or len(cols) <= _LISTED:
            return ["  Columns:"] + [
                f"    {c['column']}  non-null {c['non_null']}/{n_rows}, "
                f"distinct {c['distinct']}, longest {c['max_length']} chars "
                f"({c['at_max_length']} values that long)  pii: {c['pii']['status']}"
                + (f"  read by {_capped(c['read_by'])}" if c["read_by"] else "")
                for c in cols
            ]
        stems: dict[str, list[dict]] = {}
        for c in cols:
            stems.setdefault(_STEM.sub("", c["column"]), []).append(c)
        lines = [
            f"  Columns ({len(cols)} in {len(stems)} stems; "
            f"get_datasets('{self.form_id}', '{name}', columns=True) lists each):"
        ]
        for stem, group in list(stems.items())[:_LISTED]:
            readers = list(dict.fromkeys(r for c in group for r in c["read_by"]))
            statuses = dict(Counter(c["pii"]["status"] for c in group))
            what = (
                group[0]["column"]
                if len(group) == 1
                else f"{stem}: {len(group)} columns, {group[0]['column']} ... "
                f"{group[-1]['column']}"
            )
            lines.append(
                f"    {what}  non-null {min(c['non_null'] for c in group)}-"
                f"{max(c['non_null'] for c in group)}/{n_rows}  pii {statuses}"
                + (f"  read by {_capped(readers)}" if readers else "")
            )
        if len(stems) > _LISTED:
            lines.append(f"    ... {len(stems) - _LISTED} more stems")
        return lines

    def get_structure_db(
        self, schema: str | None = None, table: str | None = None
    ) -> str:
        """Map ``<project>.duckdb``: a summary, one schema, or one table with every
        column.
        """
        path = self.form_dir.parent / f"{self.project}_db.json"
        objects = json.loads(path.read_text(encoding="utf-8"))
        if schema is None:
            return render_structure_summary(self.project, objects)
        if table is None:
            return render_structure_schema(self.project, objects, schema)
        name = table if schema == "main" else f"{schema}.{table}"
        picked = [o for o in objects if o["name"] == name]
        if not picked:
            raise ValueError(f"no table {name!r} in {self.project}.duckdb")
        return render_structure(self.project, picked, all_columns=True)

    def get_project(self) -> str:
        """Render what the project is about: description, entities, candidate keys."""
        return render_project(self.flow)

    def get_flow(self, dataset: str | None = None, columns: bool = False) -> str:
        """Render the project's ``flow.json``, or one dataset's columns with ``dataset``."""
        return render_flow(self.flow, dataset, columns)

    def get_survey_info(self) -> str:
        """Summarise the form and its outputs."""
        d, s = self.dataset, self.summary
        top_groups = sorted(
            {q["group_path"][0] for q in self.questions.values() if q["group_path"]}
        )
        absent = s["questions_without_columns"]
        return "\n".join(
            [
                f"{d['name']} (version {d['form_version']}): submissions: {d['n_observations']}, "
                f"columns: {d['n_variables']}, questions: {s['n_questions']}",
                f"pii: {s['pii']}",
                *(
                    [
                        f"left out of every count and stat: {d['n_excluded']} "
                        f"submissions where {d['exclude']} ([submissions] exclude); "
                        "the parquet keeps them"
                    ]
                    if d["exclude"]
                    else []
                ),
                f"columns kept as text: {s['n_cast_fallback']}; all missing: {s['n_all_missing']}; "
                f"from another form version (ragged): {s['n_ragged']}",
                f"columns without a question: {_kinds_text(s)}",
                _absent_text(s["conditions_on_absent_codes"]),
                f"top-level groups: {', '.join(top_groups) or '-'}",
                f"questions with no column, since no submission holds a value: "
                f"{len(absent)}" + (f" ({', '.join(absent)})" if absent else ""),
                f"PII review file: {self.review_file}",
            ]
        )


def _unmatched_lines(words: set[str]) -> list[str]:
    """Return a line naming the query words no question holds, when there are any."""
    if not words:
        return []
    return [f"No question holds: {', '.join(sorted(words))}; ranked on the rest."]


def _query_words(query: str) -> set[str]:
    """Return the query's words; one-letter words ("p" of "p-value") only when alone."""
    words = set(_tokens(query))
    return {w for w in words if len(w) > 1} or words


def _idf(words, forms: list[tuple[dict, dict, int]]) -> dict[str, float]:
    """Return each word's IDF over ``forms`` (each: the questions holding each word
    in text, in hints, and the number of questions). A word in more than half the
    questions ("de", "the") only counts when no other word is rarer.
    """
    n = sum(size for _, _, size in forms)
    held = {w: sum(len(m[w] | h[w]) for m, h, _ in forms) for w in words}
    terms = [w for w in words if held[w] <= n / 2] or list(words)
    return {w: math.log(n / held[w]) + 1 for w in terms if held[w]}


def search_forms(stores: dict, query: str, max_results: int = 20) -> str:
    """Search every form's questions, best first; a word's IDF is over every form,
    so scores compare across them.
    """
    matches = [
        (*store.search_matches(query), len(store.questions))
        for store in stores.values()
    ]
    idf = _idf(_query_words(query), matches)
    scored = {form: store.search_scored(query, idf) for form, store in stores.items()}
    ranked = sorted(
        (
            (score, form, name)
            for form, (hits, _) in scored.items()
            for score, name in hits
        ),
        key=lambda x: (-x[0][0], -x[0][1], -x[0][2], x[1], x[2]),
    )[:max_results]
    if not ranked:
        return f"No question of {', '.join(stores)} matches {query!r}."
    unmatched = set.intersection(*(words for _, words in scored.values()))
    return "\n".join(
        _unmatched_lines(unmatched)
        + [f"{form}.{stores[form].search_line(name)}" for _, form, name in ranked]
    )


# A wide column's instance suffixes: score_2_1 -> score.
_STEM = re.compile(r"(_[0-9]+)+$")
# The literal start of a column named per row: concat('score_', index()).
_CONCAT_PREFIX = re.compile(r"concat\(\s*'([^']+)'\s*,")


def _capped(names: list[str]) -> str:
    """Return ``names`` joined, the first ``_LISTED`` and a count of the rest."""
    more = len(names) - _LISTED
    return ", ".join(names[:_LISTED]) + (f", ... {more} more" if more > 0 else "")


def _path(q: dict) -> str:
    return "/".join([*q["group_path"], q["variable_name"]])


def trace_lineage(stores: dict, form: str, name: str) -> str:
    """Trace where ``form``'s field ``name`` gets its value, back to the questions
    someone answered.

    One line per hop, indented by depth: a calculate to the fields it reads; a
    ``pulldata()`` to the dataset column and the field another form publishes it
    from (a column named per row, ``concat('score_', index())``, to the one field
    that publishes every ``score_<n>``); a ``search()`` select to the dataset columns its choices come from. A hop
    that goes no further says why (an external dataset, a column the dataset lacks).
    """
    lines: list[str] = []
    seen: set[tuple[str, str]] = set()
    lists: dict[tuple, str] = {}

    def column(d: dict, col: str, depth: int) -> None:
        pad = "  " * depth
        if not d["published_by"]:
            what = "an attached file" if d["kind"] == "form_file" else "external"
            lines.append(f"{pad}{d['id']}.{col}: {what}, no project form fills it")
        elif col in d["publish_map"]:
            field = _leaf(d["publish_map"][col])
            lines.append(f"{pad}{d['id']}.{col}: published by {d['published_by']}")
            walk(d["published_by"], field, depth + 1)
        elif col in d["legacy_columns"]:
            lines.append(
                f"{pad}{d['id']}.{col}: no field of {d['published_by']}'s current "
                "version"
            )
        else:
            lines.append(f"{pad}{d['id']}.{col}: no such column")

    def computed(d: dict, expression: str, depth: int) -> None:
        # concat('score_', index()) names score_1, score_2, ...: when one field
        # publishes every column of that stem, the hop continues to it.
        pad = "  " * depth
        prefix = _CONCAT_PREFIX.match(expression)
        stem = prefix.group(1).rstrip("_") if prefix else None
        named = sorted(
            (
                c
                for c in d["publish_map"]
                if stem and c.startswith(prefix.group(1)) and _STEM.sub("", c) == stem
            ),
            key=lambda c: [int(n) for n in c[len(stem) + 1 :].split("_")],
        )
        fields = {_leaf(d["publish_map"][c]) for c in named}
        if len(fields) != 1:
            lines.append(f"{pad}{d['id']}: the column is named per row")
            return
        lines.append(
            f"{pad}{d['id']}.{named[0]} ... {named[-1]} ({len(named)} columns, named "
            f"per row): published by {d['published_by']}"
        )
        walk(d["published_by"], fields.pop(), depth + 1)

    def walk(form: str, name: str, depth: int) -> None:
        pad = "  " * depth
        if (form, name) in seen:
            lines.append(f"{pad}{form}.{name}: traced above")
            return
        seen.add((form, name))
        store = stores[form]
        q = store.questions.get(name)
        if q is None:
            lines.append(f"{pad}{form}.{name}: no question of {form}")
            return
        source, calculation = q["data_source"], q["calculation"]
        refs = list(dict.fromkeys(_REF_RE.findall(calculation or "")))
        if source and source["kind"] == "pulldata":
            match = " and ".join(
                f"{m['column']} = {m['value']}" for m in source["match"]
            )
            keys = {
                c["column"]: c
                for c in store.dataset_columns
                if c["dataset"] == source["dataset"]
            }
            warnings = [
                f"{m['column']} {_not_unique(keys[m['column']])}"
                for m in source["match"]
                if m["column"] in keys and _not_unique(keys[m["column"]])
            ]
            lines.append(
                f"{pad}{form}.{name} <- pulldata {source['dataset']}.{source['column']}"
                f" where {match}" + (f" ({'; '.join(warnings)})" if warnings else "")
            )
            d, read = store.read(source["dataset"], _path(q))
            if read["computed"]:
                computed(d, read["computed"], depth + 1)
            else:
                column(d, source["column"], depth + 1)
            keys = {r for m in source["match"] for r in _REF_RE.findall(m["value"])}
            refs = [r for r in refs if r not in keys]
        elif calculation:
            lines.append(
                f"{pad}{form}.{name} = {calculation}"
                + (
                    f" (a default of this {q['type']}; the user can change it)"
                    if q["calculation_is_default"]
                    else ""
                )
            )
        else:
            withheld = q["choices_withheld"] and not source
            lines.append(
                f"{pad}{form}.{name} ({q['type']}): {_short(q['question_text'])}"
                + (_choices_text(q) if withheld else "")
            )
            if q["choices"] and not source and not withheld:
                # Selects sharing a list print it once.
                listed = tuple((c["value"], c["label"]) for c in q["choices"])
                if listed in lists:
                    lines.append(f"{pad}  choices as {lists[listed]} above")
                else:
                    lists[listed] = f"{form}.{name}"
                    lines.append(f"{pad}  {_choices_line(q)}")
        if source and source["kind"] == "enumerator":
            d, _ = store.read(source["dataset"], _path(q))
            line = f'{pad}  picks a row of {d["id"]}; stores its name and id as "name (id)"'
            if not d["published_by"]:
                line += " (external, no project form fills it)"
            lines.append(line)
        if source and source["kind"] == "search":
            d, read = store.read(source["dataset"], _path(q))
            where = " and ".join(
                f"{m['column']} = {m['value']}" for m in source["match"]
            )
            # The select stores its value column; the label columns are only shown.
            labels = [c for c in read["choices"] if c != read["value"]]
            line = (
                f"{pad}  choices: rows of {d['id']}"
                + (f" where {where}" if where else "")
                + (f"; stores {read['value']}" if read["value"] else "")
                + (f", shows {', '.join(labels)}" if labels else "")
            )
            if not d["published_by"]:
                what = "an attached file" if d["kind"] == "form_file" else "external"
                lines.append(f"{line} ({what}, no project form fills it)")
            else:
                lines.append(line)
                if read["value"]:
                    column(d, read["value"], depth + 2)
        for ref in refs:
            walk(form, ref, depth + 1)

    walk(form, name, 0)
    return "\n".join(lines)


def _not_unique(column: dict) -> str | None:
    """Return why a dataset column does not identify one row, or None when it does."""
    if column["distinct"] == column["non_null"] == column["rows"]:
        return None
    return f"not unique: {column['distinct']} distinct in {column['non_null']} rows"


def _columns_text(columns: dict[str, str]) -> str:
    return ", ".join(f"{k} = {v}" for k, v in columns.items())


def _filter_line(q: dict) -> str:
    """Return a select's choice filter: applied to the list when static, or which
    choices each submission sees when it reads the form.
    """
    f = q["choice_filter"]
    if f["per_submission"]:
        how = "per submission: each sees the choices it passes"
    elif q["choices_withheld"]:
        how = f"applied to its {f['items']} choices"
    else:
        how = f"applied: {len(q['choices'])} of {f['items']} choices pass"
    return f"Choice filter: {f['expression']} ({how})"


def _choices_line(q: dict) -> str:
    """Return a select's choices; past ``_LISTED``, the first ones, or the label
    pattern when every label is the same text around its value.
    """
    choices = q["choices"]
    if len(choices) <= _LISTED:
        return "Choices: " + "; ".join(f"{c['value']} = {c['label']}" for c in choices)
    rest = f"; get_choice_list('{q['variable_name']}') lists each"
    patterns = {c["label"].replace(c["value"], "<n>") for c in choices}
    if len(patterns) == 1 and "<n>" in (pattern := patterns.pop()):
        return (
            f"Choices: {len(choices)}, {choices[0]['value']} ... "
            f"{choices[-1]['value']}, each labelled {pattern} (<n>: its value){rest}"
        )
    return (
        "Choices: "
        + "; ".join(f"{c['value']} = {c['label']}" for c in choices[:_LISTED])
        + f"; ... {len(choices) - _LISTED} more{rest}"
    )


def _choices_text(q: dict) -> str:
    if q["choices_withheld"]:
        return f"; choices not listed ({', '.join(q['choices_withheld'])})"
    if not q["choices"]:
        return ""
    labels = list(choice_labels(q["choices"]).items())
    shown = ", ".join(f"{v} = {plain_label(lab)}" for v, lab in labels[:_LISTED])
    more = f", ... {len(labels) - _LISTED} more" if len(labels) > _LISTED else ""
    return f"; choices {shown}{more}"


def project_stores(config: Path) -> dict[str, SurveyStore]:
    """Open every form of the project ``config`` names."""
    import tomllib

    data = tomllib.loads(config.read_text(encoding="utf-8"))
    return {
        f: SurveyStore(config.parent / data["out_dir"] / f, f) for f in data["forms"]
    }


def _open(
    config: Path | None, directory: Path, form: str | None, project: bool = False
) -> SurveyStore:
    """Open a form's outputs named by a config file, or the one form in ``directory``.

    A config with several forms needs ``form``, except for a ``project`` command,
    which reads the project's files through any form.
    """
    if config is not None:
        import tomllib

        data = tomllib.loads(config.read_text(encoding="utf-8"))
        forms = data["forms"]
        if form is None and project:
            form = forms[0]
        if form is None:
            if len(forms) > 1:
                raise ValueError(f"the config has several forms; pass --form: {forms}")
            (form,) = forms
        if form not in forms:
            raise ValueError(f"{form!r} is not in the config's forms: {forms}")
        return SurveyStore(config.parent / data["out_dir"] / form, form)
    found = sorted(directory.glob("*_questions.json"))
    if len(found) != 1:
        raise FileNotFoundError(
            f"expected one <form>_questions.json in {directory}, found {len(found)}"
        )
    return SurveyStore(directory, found[0].name.removesuffix("_questions.json"))


def main(argv: list[str] | None = None, store: SurveyStore | None = None) -> None:
    """Entry point for ``scto-survey`` and ``search_survey.py``: the MCP tools as commands."""
    import argparse

    parser = argparse.ArgumentParser(prog="scto-survey")
    parser.add_argument(
        "--config", type=Path, help="config.toml naming the forms and out_dir"
    )
    parser.add_argument("--form", help="which form, when the config has several")
    parser.add_argument(
        "--dir",
        type=Path,
        default=Path("."),
        help="a form's output folder (default: here)",
    )
    commands = parser.add_subparsers(dest="command", required=True)
    var = commands.add_parser("var", help="describe questions or columns")
    var.add_argument("names", nargs="+")
    var.add_argument("--columns", action="store_true", help="list every column")
    commands.add_parser("group", help="a group's questions in order").add_argument(
        "group"
    )
    search = commands.add_parser(
        "search", help="find questions by name or text (every form without --form)"
    )
    search.add_argument("query", nargs="+")
    search.add_argument("--max", type=int, default=20)
    commands.add_parser("choices", help="a select's choices").add_argument("name")
    commands.add_parser("gates", help="the relevance chain").add_argument("name")
    hood = commands.add_parser("neighborhood", help="related questions")
    hood.add_argument("name")
    hood.add_argument("--depth", type=int, default=1)
    commands.add_parser("repeats", help="repeat-group structure").add_argument(
        "repeat", nargs="?", help="one repeat's members in full"
    )
    commands.add_parser("info", help="form summary")
    datasets = commands.add_parser(
        "datasets", help="datasets the form reads and their joins"
    )
    datasets.add_argument("dataset", nargs="?", help="one dataset's joins in full")
    datasets.add_argument("--columns", action="store_true", help="list every column")
    db = commands.add_parser("db", help="map of <project>.duckdb: tables, keys, joins")
    db.add_argument(
        "schema", nargs="?", help="one schema in full (a form, dataset, main)"
    )
    db.add_argument("table", nargs="?", help="one table of the schema, every column")
    commands.add_parser("project", help="what the project is about: entities, keys")
    flow = commands.add_parser("flow", help="how the project's forms chain")
    flow.add_argument("dataset", nargs="?", help="one dataset's columns, end to end")
    flow.add_argument("--columns", action="store_true", help="list every column")
    commands.add_parser(
        "lineage", help="where a field's value comes from, across forms (--config)"
    ).add_argument("name")
    args = parser.parse_args(argv)

    if args.command == "lineage":
        if args.config is None or args.form is None:
            raise ValueError("lineage reads every form: pass --config and --form")
        print(trace_lineage(project_stores(args.config), args.form, args.name))
        return
    if (
        store is None
        and args.command == "search"
        and args.form is None
        and args.config is not None
    ):
        stores = project_stores(args.config)
        print(search_forms(stores, " ".join(args.query), args.max))
        return
    if store is None:
        store = _open(
            args.config, args.dir, args.form, args.command in ("project", "flow", "db")
        )
    answer = {
        "var": lambda: store.lookup_variables(args.names, args.columns),
        "search": lambda: store.search_questions(" ".join(args.query), args.max),
        "group": lambda: store.get_group(args.group),
        "choices": lambda: store.get_choice_list(args.name),
        "gates": lambda: store.get_gate_chain(args.name),
        "neighborhood": lambda: store.get_variable_neighborhood(args.name, args.depth),
        "repeats": lambda: store.get_repeat_structure(args.repeat),
        "info": store.get_survey_info,
        "datasets": lambda: store.get_datasets(args.dataset, args.columns),
        "db": lambda: store.get_structure_db(args.schema, args.table),
        "flow": lambda: store.get_flow(args.dataset, args.columns),
        "project": store.get_project,
    }[args.command]()
    print(answer)


if __name__ == "__main__":
    main()
