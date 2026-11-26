"""Per-variable PII signal: evidence for the people cleaning data, not enforcement.

Each column gets ``{"status", "basis"[, "presidio"]}``; the first matching rule wins:

0. ``contains_pii`` / ``reviewed``: the column or its question is on the user's
   blacklist; ``whitelisted`` / ``reviewed``: on the whitelist.
1. ``cleared_by_form``: the question is ``publishable``. With ``trust_publishable =
   false`` this rule is skipped and ``publishable`` is only noted in the basis.
2. ``contains_pii``: device metadata columns; whatever the name, a field that
   preloads device or user metadata (``username``, ``deviceid``, ...), an enumerator
   field, a calculate that calls ``enumerator-id()``, ``enumerator-name()`` or
   ``username()``; and a calculate whose formula reads such a field, a geo or
   attachment field or a blacklisted one, directly or through other calculates (basis
   ``lineage:<field>``). This rule holds under ``no_personal_data`` too, except for
   geo and attachment fields; the whitelist outranks it. Geo and attachment fields
   themselves are ``contains_pii`` by their type (rule 3's ``static``), which
   ``no_personal_data`` overrides.
3. ``whitelisted``: system columns; integer, decimal, date, datetime and time
   questions; selects with inline choices; calculates whose every reference is
   cleared or whitelisted and that do not ``pulldata()``.
4. ``may_contain_pii`` / ``no_hits``: everything else, scanned with Presidio on its
   distinct non-null values (evenly spaced above ``max_distinct``). Without
   an analyzer it is ``may_contain_pii`` / ``unscanned``. With
   ``no_personal_data`` the project declares it holds none: every column past the
   device and system columns is ``whitelisted`` / ``project``, and Presidio never runs.

Presidio, when given an analyzer, runs on submission values. Blocks hold entity
counts, the number of hit rows and up to five of their KEYs, never matched text.
"""

import re
from collections import Counter
from dataclasses import dataclass, field

import pyarrow as pa

from datasure.surveycto.survey import code_reasons

_DEVICE_COLUMNS = {
    "deviceid",
    "subscriberid",
    "simid",
    "simserial",
    "devicephonenum",
    "phonenumber",
    "username",
}
_CONTAINS_TYPES = {
    "geopoint",
    "geotrace",
    "geoshape",
    "image",
    "audio",
    "video",
    "file",
}
_TYPED_SAFE = {"integer", "decimal", "date", "datetime", "time"}
# Fields that capture who or which device collected the submission, whatever their name.
_METADATA_TYPES = {
    "deviceid",
    "subscriberid",
    "simserial",
    "phonenumber",
    "username",
    "enumerator",  # stores the enumerator's "name (id)"
}
_METADATA_CALLS = re.compile(r"(?<![\w-])(enumerator-id|enumerator-name|username)\(\)")
_SELECT_TYPES = {"select_one", "select_multiple"}
_REF = re.compile(r"\$\{([^}]+)\}")
_CALL = re.compile(r"([A-Za-z][\w-]*)\s*\(")
# Functions that make a value without reading the form or the device.
_GENERATED_CALLS = {"once", "uuid", "now", "today", "random", "concat", "if"}
# The statuses that clear a calculate reading the field (lineage), and those that hold
# or may hold PII.
SAFE = {"cleared_by_form", "whitelisted"}
FLAGGED = {"contains_pii", "may_contain_pii"}
# Enough KEYs to find examples; the review workbook has every flagged row.
_MAX_HIT_KEYS = 5
# A search() list longer than this stays in its dataset: a filter on a field can leave
# every row of a large dataset as a possible choice, copied into each column.


def shows_values(status: str) -> bool:
    """Return whether an output an agent reads may show a column's values (range,
    quartiles, frequencies, codes) for its pii ``status``: every status but a flagged
    one. Counts, null rates and ``KEY``s are shown for every column.
    """
    return status not in FLAGGED


@dataclass(frozen=True)
class PiiConfig:
    """``[pii]`` settings."""

    languages: dict[str, str] = field(
        default_factory=lambda: {"es": "es_core_news_lg", "en": "en_core_web_lg"}
    )
    entities: tuple[str, ...] = ("PERSON", "PHONE_NUMBER", "EMAIL_ADDRESS", "LOCATION")
    # Extra entity name -> regex, e.g. {"NATIONAL_ID": r"\b\d{8,10}\b"}.
    id_patterns: dict[str, str] = field(default_factory=dict)
    # Presidio scores bare phone numbers 0.4.
    score_threshold: float = 0.4
    max_distinct: int = 1000
    # Column or question names the user reviewed and cleared.
    whitelist: tuple[str, ...] = ()
    # Column or question names the user reviewed as personal data; above publishable.
    blacklist: tuple[str, ...] = ()
    # False: publishable clears nothing; the column goes through the other rules.
    trust_publishable: bool = True
    # True: the project holds no personal data (study metadata, say); every column
    # past the blacklist, publishable and device rules is whitelisted, unscanned.
    no_personal_data: bool = False

    def __post_init__(self):
        """Raise when a name is on both the whitelist and the blacklist."""
        both = set(self.whitelist) & set(self.blacklist)
        if both:
            raise ValueError(
                f"on both the whitelist and the blacklist: {', '.join(sorted(both))}"
            )


class _Rules:
    """Question-level rules, memoised so calculate lineage resolves once."""

    def __init__(
        self,
        questions: list[dict],
        whitelist: set[str],
        blacklist: set[str],
        trust_publishable: bool,
        no_personal_data: bool = False,
    ):
        self.by_name = {q["variable_name"]: q for q in questions}
        self.whitelist = whitelist
        self.blacklist = blacklist
        self.trust_publishable = trust_publishable
        # In a project declared to hold no personal data, geo and attachment fields are
        # whitelisted, so they carry nothing.
        self.personal_types = set() if no_personal_data else _CONTAINS_TYPES
        self._memo: dict[str, dict | None] = {}
        self._deciding: set[str] = set()
        self._carried: dict[str, str | None] = {}

    def static(self, name: str) -> dict | None:
        """Return the block when a rule decides it without the data, else None."""
        if name in self._deciding:
            return None  # a reference cycle resolves to "scan"
        if name not in self._memo:
            self._deciding.add(name)
            self._memo[name] = self._decide(self.by_name[name])
            self._deciding.discard(name)
        return self._memo[name]

    def _decide(self, q: dict) -> dict | None:
        qtype = q["type"]
        if q["variable_name"] in self.blacklist:
            return {"status": "contains_pii", "basis": ["reviewed"]}
        if q["variable_name"] in self.whitelist:
            return {"status": "whitelisted", "basis": ["reviewed"]}
        if q["publishable"] and self.trust_publishable:
            return {"status": "cleared_by_form", "basis": ["publishable"]}
        if basis := self.personal(q["variable_name"]):
            return {"status": "contains_pii", "basis": [basis]}
        if qtype in _CONTAINS_TYPES:
            return {"status": "contains_pii", "basis": [f"type:{qtype}"]}
        if qtype in _TYPED_SAFE:
            return {"status": "whitelisted", "basis": [f"type:{qtype}"]}
        if qtype in _SELECT_TYPES and "search(" not in (q["appearance"] or ""):
            return {"status": "whitelisted", "basis": ["choices:inline"]}
        if qtype == "calculate" and not self._pulldata(q):
            refs = q["references"]
            # Reading no field and calling only functions that generate a value, it
            # holds nothing anyone entered: once(uuid(5)), today().
            calls = set(_CALL.findall(q["calculation"] or ""))
            if not refs and calls <= _GENERATED_CALLS:
                return {"status": "whitelisted", "basis": ["generated"]}
            if refs and all(r in self.by_name and self._safe(r) for r in refs):
                return {"status": "whitelisted", "basis": [f"lineage:{','.join(refs)}"]}
        return None

    def personal(self, name: str | None) -> str | None:
        """Return why question ``name`` captures collection metadata, else None: its
        type, or a function its calculation calls. A calculate reading such a field
        is not cleared by lineage, so it is scanned like any other text.
        """
        q = self.by_name.get(name)
        if q is None:
            return None
        if q["type"] in _METADATA_TYPES:
            return f"metadata:{q['type']}"
        calls = _METADATA_CALLS.search(q["calculation"] or "")
        if calls:
            return f"calls:{calls.group(1)}()"
        return None

    def carried(self, name: str | None) -> str | None:
        """Return a field a calculate's formula reads, directly or through other
        calculates, that is blacklisted, collection metadata or of a type that holds
        personal data (a geopoint, an image, ...), else None: ``selected-at(${gps},
        0)`` holds the latitude. A whitelisted field carries nothing. A
        ``pulldata()`` holds its dataset column, not its key: it carries the column
        when that is blacklisted.
        """
        q = self.by_name.get(name)
        if q is None or q["type"] != "calculate":
            return None
        source = q["data_source"]
        if source and source["kind"] == "pulldata":
            column = f"{source['dataset']}.{source['column']}"
            return column if column in self.blacklist else None
        if name not in self._carried:
            self._carried[name] = None  # a reference cycle carries nothing
            for ref in dict.fromkeys(_REF.findall(q["calculation"] or "")):
                if ref in self.whitelist:
                    continue
                found = (
                    ref
                    if ref in self.blacklist
                    or self.personal(ref)
                    or self.by_name.get(ref, {}).get("type") in self.personal_types
                    else self.carried(ref)
                )
                if found:
                    self._carried[name] = found
                    break
        return self._carried[name]

    def _safe(self, name: str) -> bool:
        block = self.static(name)
        return block is not None and block["status"] in SAFE

    @staticmethod
    def _pulldata(q: dict) -> bool:
        return "pulldata(" in (q["calculation"] or "")

    def scan_basis(self, name: str | None) -> list[str]:
        if name is None:
            return ["no_question"]
        q = self.by_name[name]
        return [f"type:{q['type']}"] + (["pulldata"] if self._pulldata(q) else [])


def _entities(texts: list[str], config: PiiConfig, analyzer) -> list[set[str]]:
    """Return the entity types Presidio finds in each text.

    spaCy reads the texts in batches, several times faster than one call per text,
    and Presidio's recognizers then run on each text's parse.
    """
    wanted = [*config.entities, *config.id_patterns]
    found: list[set[str]] = [set() for _ in texts]
    for lang in config.languages:
        parsed = analyzer.nlp_engine.process_batch(texts, lang, batch_size=256)
        for hits, (text, artifacts) in zip(found, parsed, strict=True):
            hits.update(
                r.entity_type
                for r in analyzer.analyze(
                    text=text,
                    language=lang,
                    entities=wanted,
                    score_threshold=config.score_threshold,
                    nlp_artifacts=artifacts,
                )
            )
    return found


class _Scans:
    """Columns to scan, collected first so Presidio reads every distinct text once.

    Columns share many values ("0", "No", a date), so a form's columns are scanned
    together: ``add`` registers a column, ``run`` analyzes the union of their
    sampled distinct values, and ``block`` gives each column its result.
    """

    def __init__(self, config: PiiConfig):
        self.config = config
        self.columns: dict = {}
        self.found: dict[str, set[str]] = {}

    def add(self, name, column: pa.ChunkedArray, keys: list, basis: list[str]) -> None:
        values = [None if v is None else str(v) for v in column.to_pylist()]
        distinct = sorted({v for v in values if v is not None})
        if len(distinct) > self.config.max_distinct:
            # Evenly spaced over the sorted values: the same sample on every run.
            step = len(distinct) / self.config.max_distinct
            distinct = [
                distinct[int(i * step)] for i in range(self.config.max_distinct)
            ]
        self.columns[name] = (values, distinct, keys, basis)

    def run(self, analyzer) -> None:
        texts = sorted(
            {t for _, distinct, _, _ in self.columns.values() for t in distinct}
            - set(self.found)
        )
        if texts:
            self.found.update(
                zip(texts, _entities(texts, self.config, analyzer), strict=True)
            )

    def block(self, name) -> dict:
        values, distinct, keys, basis = self.columns[name]
        return _block(values, distinct, keys, basis, self.found)


def _block(
    values: list, distinct: list[str], keys: list, basis: list[str], entities: dict
) -> dict:
    found: dict[str, set[str]] = {}
    for value in distinct:
        for t in entities[value]:
            found.setdefault(t, set()).add(value)
    hits = set().union(*found.values()) if found else set()
    hit_keys = sorted({k for k, v in zip(keys, values, strict=True) if v in hits})
    return {
        "status": "may_contain_pii" if found else "no_hits",
        "basis": basis + [f"presidio:{t}" for t in sorted(found)],
        "presidio": {
            "entities": {t: len(found[t]) for t in sorted(found)},
            "distinct_scanned": len(distinct),
            "hit_rows": len(hit_keys),
            "hit_keys": hit_keys[:_MAX_HIT_KEYS],
        },
    }


def classify(
    table: pa.Table, vardict: dict, questions: list[dict], config: PiiConfig, analyzer
) -> dict[str, dict]:
    """Return the PII block for every column of ``table``.

    ``analyzer`` None runs the rules alone: a column they leave open is
    ``may_contain_pii`` with basis ``unscanned``, so its values stay hidden.
    """
    variables = vardict["variables"]
    question_names = {q["variable_name"] for q in questions}
    whitelist, blacklist = set(config.whitelist), set(config.blacklist)
    # The blacklist keeps its dataset columns (dataset.column): a pulldata() of one
    # carries it.
    rules = _Rules(
        questions,
        whitelist & question_names,
        blacklist,
        config.trust_publishable,
        config.no_personal_data,
    )
    keys = table.column("KEY").to_pylist()

    blocks = {}
    scans = _Scans(config)
    for column in table.schema.names:
        entry = variables[column]
        question = entry["question"]
        q = rules.by_name.get(question)
        if column in blacklist or question in rules.blacklist:
            block = {"status": "contains_pii", "basis": ["reviewed"]}
        elif column in whitelist or question in rules.whitelist:
            block = {"status": "whitelisted", "basis": ["reviewed"]}
        elif q is not None and q["publishable"] and config.trust_publishable:
            block = {"status": "cleared_by_form", "basis": ["publishable"]}
        elif column in _DEVICE_COLUMNS and entry.get("system"):
            block = {"status": "contains_pii", "basis": [f"device:{column}"]}
        elif basis := rules.personal(question):
            block = {"status": "contains_pii", "basis": [basis]}
        elif carried := rules.carried(question):
            block = {"status": "contains_pii", "basis": [f"lineage:{carried}"]}
        elif entry.get("system"):
            block = {"status": "whitelisted", "basis": ["system"]}
        elif config.no_personal_data:
            block = {"status": "whitelisted", "basis": ["project"]}
        else:
            block = rules.static(question) if question is not None else None
            if block is None:
                scans.add(
                    column, table.column(column), keys, rules.scan_basis(question)
                )
                continue
            if q is not None and q["publishable"]:
                block = {**block, "basis": [*block["basis"], "publishable"]}
        blocks[column] = block
    if analyzer is not None:
        scans.run(analyzer)
    for column, (_, _, _, basis) in scans.columns.items():
        # Without an analyzer, what the rules leave open stays flagged, unscanned.
        block = (
            scans.block(column)
            if analyzer is not None
            else {"status": "may_contain_pii", "basis": [*basis, "unscanned"]}
        )
        if (q := rules.by_name.get(variables[column]["question"])) and q["publishable"]:
            block = {**block, "basis": [*block["basis"], "publishable"]}
        blocks[column] = block
    return {column: blocks[column] for column in table.schema.names}


def attach(
    vardict: dict, blocks: dict[str, dict], questions: list[dict], codebook: list[dict]
) -> None:
    """Add each column's block to the dictionary and a status count to its summary.

    A column whose values are not shown (``shows_values``) loses its range
    (``data_min``, ``data_max``). The codes a withheld list lacks are only counted
    when its codes are not shown (``survey.code_reasons``): its list is withheld for
    what it holds, or a column of its select or its dataset's value column is flagged.
    """
    variables = vardict["variables"]
    for column, block in blocks.items():
        variables[column]["pii"] = block
        if not shows_values(block["status"]):
            for key in ("data_min", "data_max"):
                variables[column].pop(key, None)
    vardict["summary"]["pii"] = dict(Counter(b["status"] for b in blocks.values()))
    by_name = {q["variable_name"]: q for q in questions}
    for name, picked in vardict["summary"]["withheld_choices"].items():
        if code_reasons(by_name[name], variables, codebook):
            del picked["codes_not_in_list"]
