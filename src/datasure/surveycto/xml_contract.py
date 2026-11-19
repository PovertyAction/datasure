"""Parse a deployed SurveyCTO form XML into the form<->database column contract.

The compiled XForm is the authoritative statement of what gets stored in the
database. This module reads it into a node model that is the *structural spine*
of the variable dictionary:

- `<instance>` (the primary one, whose root `id` == the form_id) gives the node
  hierarchy. An element carrying `jr:template=""` is a **repeat group**; its
  fields are suffixed `_N` per instance in the wide export (nested repeats -> one
  index per level, outer->inner, e.g. `..._113_1`).
- Each `<bind nodeset=... type=...>` gives a node's type plus
  calculate/relevant/constraint/required/readonly. `calculate="pulldata(...)"`
  records preload provenance (which attached CSV fills the field).
- `<h:body>` controls distinguish `select1` (select_one) from `select`
  (select_multiple); a select_multiple expands to per-choice binaries in wide,
  carrying one extra trailing index = the choice code.
- A bind's `publishable` attribute marks fields SurveyCTO leaves unencrypted on
  encrypted forms.
- A select with a choice filter lists its choices through an `<itemset>` over a
  secondary instance (`instance('list')/root/item[filter]`). A filter on the items'
  own columns (`filter < 3`) is applied; one that reads the submission (`current()`,
  a field's path) keeps every item, since it is decided per submission.

The contract maps every wide-JSON column to its node and type; `questions.json`
is built from the same XML.

Pure stdlib (`xml.etree.ElementTree`).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from datasure.surveycto.xpath import UnsupportedExpression, compile_expression

_SELECT_CONTROL = {"select": "select_multiple", "select1": "select_one"}

# Wide columns that are SurveyCTO transport/metadata, not form nodes.
_SYS_EXACT = {
    "KEY",
    "SubmissionDate",
    "CompletionDate",
    "starttime",
    "endtime",
    "deviceid",
    "subscriberid",
    "simid",
    "devicephonenum",
    "username",
    "duration",
    "caseid",
    "formdef_version",
    "review_status",
    "review_comments",
    "review_corrections",
    "review_quality",
    "instanceID",
    "instanceName",
    "SubmitterID",
    "SubmitterName",
}
_SYS_PREFIX = ("meta-", "SET-OF-")


def _ln(tag) -> str:
    """Local-name of a possibly namespaced ElementTree tag."""
    return tag.split("}")[-1] if isinstance(tag, str) and "}" in tag else tag


def is_system_column(col: str) -> bool:
    """Return True if a wide column is SurveyCTO transport/metadata, not a form node."""
    return col in _SYS_EXACT or col.startswith(_SYS_PREFIX) or col.endswith("-Comment")


# Wide-column suffix grammar (see FormContract.map_column).
# Only a NEGATIVE number sanitises to a leading underscore, so `_66` is -66.
_NEG_TOKEN_RE = re.compile(r"_(\d+)")
# `1_1` -- all-integer tokens. On a non-select node this marks formdef index
# drift; on a select_multiple whose universe does not contain it, it marks an
# unknowable choice/index boundary, because a real numeric choice value
# sanitises to exactly ONE token.
_ALL_INT = re.compile(r"\d+(?:_\d+)*")
_COMPOSITE_INT = re.compile(r"\d+(?:_\d+)+")
_SANITISE_RE = re.compile(r"[^A-Za-z0-9_]")


def _coerce_choice_value(value: str):
    """Return a bare-integer choice value as an int, anything else unchanged.

    Both decode paths run through this, so a numeric code's type depends on the
    form, not on whether the choice CSV shipped.

    A LEADING ZERO stays a string: `01` and `1` are distinct choice codes in
    SurveyCTO, and int() would silently merge them.
    """
    if not re.fullmatch(r"-?\d+", value):
        return value
    digits = value.lstrip("-")
    if len(digits) > 1 and digits[0] == "0":
        return value
    return int(value)


def sanitize_choice_value(value: str) -> str:
    """Render a choice value the way SurveyCTO renders it into a wide column name.

    Every character outside `[A-Za-z0-9_]` becomes an underscore, which is why a
    sanitised token cannot be reversed without the form's own choice universe --
    `AB-12` and `AB_12` both arrive as `AB_12`. `FormContract._universe` keys a
    select's choices through this function to undo it.
    """
    return _SANITISE_RE.sub("_", value)


@dataclass
class Node:
    """One stored node in the compiled form (a field, or a bound group)."""

    path: str  # path below the form root, slash-joined
    name: str  # leaf token (last path segment)
    group_path: list[str]  # ancestor tokens (groups + repeats), outer->inner
    repeat_path: list[str]  # ancestor tokens that are repeats, outer->inner
    repeat_depth: int = 0
    is_leaf: bool = True  # False = value bound at a group node
    xml_type: str | None = None  # bind type (string/decimal/select/...)
    control: str | None = None  # body control: select_one/select_multiple/input/...
    is_select_multiple: bool = False
    calculate: str | None = None
    # The calculate is on the body control, not the bind: a default the user can
    # change when the field is shown and not read-only.
    calculation_is_default: bool = False
    relevant: str | None = None
    constraint: str | None = None
    required: bool = False
    readonly: bool = False
    publishable: bool = False  # SurveyCTO: unencrypted on encrypted forms
    preload: str | None = None  # jr:preload (system source, e.g. property)
    preload_params: str | None = None  # jr:preloadParams (e.g. username, deviceid)
    original: str | None = None  # SurveyCTO bind `original` (XLSForm type, e.g. "note")
    # SurveyCTO bind `fieldType`: "enumerator" picks a row of the form's enumerator
    # dataset and stores "name (id)".
    field_type: str | None = None
    # Body label text, from the default translation when the label is itext; each
    # <output value="..."/> is inlined as its expression.
    label: str | None = None
    mediatype: str | None = None  # <upload mediatype>, e.g. "image/*"
    appearance: str | None = None  # body control appearance
    # Bind appearance; SurveyCTO marks the fields it fills itself here, such as
    # "class=comments" or "class=textAudit;p=100".
    bind_appearance: str | None = None
    repeat_count: str | None = None  # <repeat jr:count>, on the repeat's node
    # Where the field's content/options come from, parsed from search()/pulldata():
    #   {kind:"search", dataset, mode, filter, match}
    #   | {kind:"pulldata", dataset, value, key, match}
    # A search() dataset named by a field whose calculate is not a literal is None,
    # with `dataset_field` set to that field's path.
    data_source: dict | None = None
    # The select's `<item>` pairs verbatim from the body. For a plain select these
    # are literal choices; for a `search()` select the value/label instead NAME the
    # CSV COLUMNS holding the real universe, and only the extras are literal (a
    # `-88` "Other" alongside a column reference). Needed to build the choice index
    # that de-sanitises a wide column's choice token back to its declared value.
    # For a `search()` select only the literal extras stay here; the item naming
    # the columns goes to `choice_columns`.
    choice_items: list[dict] = field(default_factory=list)
    # Why a `search()` select's dataset choices were left out, e.g. ["presidio:PERSON"].
    choices_withheld: list[str] | None = None
    # A `search()` select's value and label columns in its dataset, from the item
    # that names them: {"value": <value column>, "label": <label column>}.
    choice_columns: dict | None = None
    # The question's hint and constraint message, from the default translation.
    hint: str | None = None
    constraint_message: str | None = None
    # A `search()` select's choices as read from its dataset, also when they are left
    # out of the outputs: they decode column names and type the data. They go to
    # <form>_search_choices.parquet with their filter values, for the database.
    choice_universe: list[dict] | None = None
    # Binaries only for the codes someone picked: the list is filtered per submission
    # (an itemset filter or a search() filter on a field), or kept in its dataset.
    choices_per_submission: bool = False
    # The itemset's filter: {"expression", "per_submission", "items"}, the expression
    # as compiled and items the list's length before a static filter applies.
    # "unresolved": True marks a static filter the evaluator cannot run: every item
    # is kept, and the list is treated as filtered per submission.
    choice_filter: dict | None = None

    @property
    def all_choices(self) -> list[dict]:
        """Every choice the select can take, listed in the outputs or not."""
        return (
            self.choice_items if self.choice_universe is None else self.choice_universe
        )

    @property
    def choices_known(self) -> bool:
        """Whether `all_choices` is every code the select can take.

        A `search()` select takes its codes from a dataset; until they are read
        into `choice_universe`, only its literal extras are known.

        DataSure's import deliberately never reads those datasets: they often
        hold PII that must not reach DataSure by accident. So on import a
        `search()` select's choices stay unknown; see the surveycto-api skill.
        """
        searched = bool(self.data_source and self.data_source["kind"] == "search")
        return self.choice_universe is not None or not searched


_INTEGER_VALUE = re.compile(r"-?\d+")


def _split_search_items(items: list[dict]) -> tuple[list[dict], dict | None]:
    """Split a `search()` select's items into literal choices and its columns.

    As in ODK Collect, an item with an integer value is a static choice (an
    "Other" of -88); any other item names the dataset columns that hold the
    values and labels. Returns the literal items and the first such item.
    """
    literal = [i for i in items if _INTEGER_VALUE.fullmatch(str(i["value"] or ""))]
    columns = next((i for i in items if i not in literal), None)
    if columns is None:
        return literal, None
    return literal, {"value": columns["value"], "label": columns["label"]}


# search('dataset','mode','col','val'[,'col2','val2'...]) on a select's appearance.


# One piece of a call's argument text: a quoted literal (to the end of the text
# when it never closes), a paren, a comma, or a run of anything else.
_ARG_TOKEN = re.compile(r"""'[^']*'|"[^"]*"|['"].*|[(),]|[^'"(),]+""", re.DOTALL)


def _split_call_args(s: str | None, func_name: str) -> list[str] | None:
    """Top-level argument strings of the first ``func_name(...)`` call in ``s``,
    respecting nested parens and quoted literals. XPath has no backslash escape,
    so a literal closes on the next matching quote. Returns None when ``s`` has no
    such call and raises ``ValueError`` when the call never closes, since its dataset
    would otherwise go unread.
    """
    if not s:
        return None
    rx = re.compile(rf"(?<![\w-]){re.escape(func_name)}\s*\(", re.IGNORECASE)
    m = rx.search(s)
    if not m:
        return None
    depth = 1
    args: list[str] = []
    cur: list[str] = []
    for token in _ARG_TOKEN.finditer(s, m.end()):
        part = token.group()
        if part == "(":
            depth += 1
        elif part == ")":
            depth -= 1
            if depth == 0:
                args.append("".join(cur))
                return [a.strip() for a in args]
        elif part == "," and depth == 1:
            args.append("".join(cur))
            cur = []
            continue
        cur.append(part)
    raise ValueError(f"{func_name}( never closes in {s!r}")


def _unquote(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and s[0] in ("'", '"') and s[-1] == s[0]:
        return s[1:-1]
    return s


def _dataset_name(arg: str) -> str:
    """Return a dataset argument without quotes or ``.csv``.

    ``'roster.csv'`` -> ``roster``.
    """
    return _unquote(arg).removesuffix(".csv")


_STRING_LITERAL = re.compile(r"""^(?:string\(\s*)?(['"])([^'"]*)\1(?:\s*\))?$""")


def _parse_pulldata(calc: str | None) -> dict | None:
    """Parse ``pulldata('ds', 'col', 'key', expr)``.

    ``match`` is ``expr``, the value of ``key``.
    """
    args = _split_call_args(calc, "pulldata")
    if args is None:
        return None
    if len(args) < 3:
        raise ValueError(f"pulldata() needs a dataset, a column and a key: {calc!r}")
    return {
        "dataset": _dataset_name(args[0]),
        "value": args[1].strip(),
        "key": _unquote(args[2]),
        "match": args[3].strip() if len(args) > 3 else None,
    }


def _parse_search(appearance: str | None) -> dict | None:
    """Parse a select's `search(...)` appearance into a choice-source descriptor.

    `search('choices','matches','list_name','treatTarget')` ->
      {kind:"search", dataset:"choices", filter:{"list_name":"treatTarget"}} (+mode).
    A column whose value is a node-ref (not a quoted literal) maps to None
    (dynamic filter); the literal pairs resolve options from the CSV. ``match`` keeps
    every filter's value expression as written, node-refs included.
    """
    if not appearance or "search(" not in appearance:
        return None
    args = _split_call_args(appearance, "search")
    if not args:
        return None
    dataset = _dataset_name(args[0])
    rest = args[1:]
    mode = _unquote(rest[0]) if rest else None
    pairs = rest[1:]
    filt: dict[str, str | None] = {}
    match: dict[str, str | None] = {}
    for i in range(0, len(pairs) - 1, 2):
        col = _unquote(pairs[i])
        val_raw = pairs[i + 1].strip()
        # a quoted literal is a static filter value; an unquoted node-ref is
        # dynamic -> None
        filt[col] = _unquote(val_raw) if val_raw[:1] in ("'", '"') else None
        match[col] = val_raw
    if len(pairs) % 2 == 1:  # trailing col with a dynamic (node-ref) value
        filt[_unquote(pairs[-1])] = None
        match[_unquote(pairs[-1])] = None
    return {
        "kind": "search",
        "dataset": dataset,
        "mode": mode,
        "filter": filt,
        "match": match,
    }


def _parse_data_source(appearance: str | None, calc: str | None) -> dict | None:
    """Unify select-from-file (`search`) and preload (`pulldata`) provenance."""
    s = _parse_search(appearance)
    if s:
        return s
    pd = _parse_pulldata(calc)
    if pd:
        return {"kind": "pulldata", **pd}
    return None


def _split_suffix(toks: list[str], depth: int) -> tuple[int, str | None]:
    """Return how many trailing tokens are repeat indices, and the choice token.

    Trailing integer tokens are consumed as repeat indices, at most ``depth`` of
    them; what precedes them, joined by ``_``, is the (sanitised) choice token,
    or None when there is none.
    """
    n = 0
    while n < depth and n < len(toks) and toks[len(toks) - 1 - n].isdigit():
        n += 1
    # An EMPTY choice is impossible, so if the head vanished while the suffix
    # still carries more tokens than the node has depth, hand an index back: a
    # negative sentinel's own leading underscore produced that empty first token
    # (`x__77_2` is choice -77 at one index, not choice "" at iterations 77 and
    # 2). When len(toks) == depth there is no choice at all -- that is the
    # select_multiple's own parent column, which the export writes empty.
    while n > 0 and len(toks) > depth and not "_".join(toks[: len(toks) - n]):
        n -= 1
    token = "_".join(toks[: len(toks) - n])
    # A token made only of underscores is not a choice value: sanitisation maps a
    # real value's characters into the alphabet, so at least one alphanumeric
    # survives, so `x___` has no choice. A negative sentinel's `_66` keeps its
    # digits.
    return n, token if token.strip("_") else None


class FormContract:
    """The compiled-form node model + the wide-column -> node resolver."""

    def __init__(
        self,
        formid: str,
        formdef_version: str | None,
        nodes: dict[str, Node],
        encrypted: bool = False,
    ):
        """Store the node model and build the deterministic leaf-name resolver index."""
        self.formid = formid
        self.formdef_version = formdef_version
        self.nodes: dict[str, Node] = nodes
        # The form has a public key: submissions are encrypted, publishable
        # fields aside.
        self.encrypted = encrypted
        # (node path, its choice list) -> {sanitised token: (value, label) | None};
        # see `_universe`.
        self._universes: dict[tuple, dict] = {}
        # leaf token -> [paths], used to resolve a de-indexed wide base name. Sorted
        # paths decide which of two homonym nodes a column maps to.
        self._by_name: dict[str, list[str]] = {}
        for path in sorted(nodes):
            self._by_name.setdefault(nodes[path].name, []).append(path)

    @property
    def repeat_groups(self) -> list[str]:
        """Return the distinct repeat-group names in first-seen order."""
        seen: list[str] = []
        for n in self.nodes.values():
            for r in n.repeat_path:
                if r not in seen:
                    seen.append(r)
        return seen

    def _candidate_names(self, col: str):
        """Every node NAME `col` starts with on an `_` boundary, longest first."""
        toks = col.split("_")
        for k in range(len(toks), 0, -1):
            cand = "_".join(toks[:k])
            if cand in self._by_name:
                yield cand

    @staticmethod
    def _trailing_int_count(toks: list[str]) -> int:
        """How many trailing tokens of `toks` could be repeat-iteration indices."""
        n = 0
        while n < len(toks) and toks[len(toks) - 1 - n].isdigit():
            n += 1
        return n

    def _resolve_node(self, col: str):
        """Pick (name, node, suffix tokens) for a wide column, or None.

        Scores every (name prefix, node) pair, since name length alone picks
        impossible nodes:

        - A node named `x_1` two repeats deep cannot own the column `x_1`: its
          columns carry two trailing index tokens (`x_1_1_1`). Bare `x_1` is the
          choice-1 binary of a depth-0 select_multiple named `x`.
        - A token must be an integer to be an index: with a homonym leaf inside a
          repeat, `langs_ES` is the choice `ES` of the depth-0 `langs`, not the
          depth-1 `hh/langs` at iteration `ES`.

        So feasibility comes first: a node needs at least `repeat_depth` trailing
        INTEGER tokens available, or it cannot own the column. Among feasible
        candidates the preference mirrors the wide-column grammar -- the node's
        own column, then a select_multiple choice binary, then a string-keyed
        runtime column. An infeasible candidate is kept only as a last resort, so
        an under-indexed column still resolves (and gets flagged `ragged`) rather
        than falling out as unmapped.
        """
        best = None
        for name in self._candidate_names(col):
            rest = col[len(name) :]
            rest = rest[1:] if rest.startswith("_") else rest
            toks = rest.split("_") if rest else []
            avail = self._trailing_int_count(toks)
            for path in self._by_name[name]:
                node = self.nodes[path]
                # The longer name wins a tie, then the first path in sorted order.
                key = (self._fit(node, toks, avail), -len(name), path)
                if best is None or key < best[0]:
                    best = (key, name, node, toks)
        if best is None:
            return None
        return best[1], best[2], best[3]

    @staticmethod
    def _fit(node: Node, toks: list[str], avail: int) -> int:
        """Score how well ``node`` owns a column's suffix tokens; lower is better."""
        depth = node.repeat_depth
        if avail < depth:
            return 3  # cannot supply its own indices: under-indexed
        if len(toks) == depth:
            return 0  # the node's own column
        if node.is_select_multiple:
            return 1  # choice binary
        return 2  # string key, or formdef index drift

    def _universe(self, node: Node) -> dict:
        """Return ``node``'s choices by the token SurveyCTO writes into a column name.

        Read from ``node.all_choices`` when first asked for that list, so a
        ``search()`` select's choices count once they are read from its dataset. Two
        values that sanitise to one token map to ``None``: ambiguous.
        """
        key = (node.path, id(node.all_choices))
        if key not in self._universes:
            universe: dict = {}
            for item in node.all_choices:
                value = str(item["value"])
                token = sanitize_choice_value(value)
                if token in universe and (universe[token] or (value,))[0] != value:
                    universe[token] = None
                elif token not in universe:
                    universe[token] = (value, item.get("label"))
            self._universes[key] = universe
        return self._universes[key]

    def _decode_choice(self, node: Node, token: str):
        """Sanitised token -> (choice value, label|None, resolved-by-index).

        Prefers the select's own choices (`_universe`), the only thing that can undo
        sanitisation (`AB-12` and `AB_12` both render `AB_12`). Falls back to the
        one shape recoverable from the token alone: a dash->underscore negative
        sentinel (`_66` -> `-66`), since a leading underscore is impossible in a
        bare number. Anything else is carried verbatim.

        When two declared values sanitise to one token the index records it as
        ambiguous (a `None` entry), and this returns no value, since the token can
        itself be one of the colliding values.

        The third element says whether the index resolved it, so the caller can
        trust an index hit instead of second-guessing it as unknowable.

        Both paths finish through `_coerce_choice_value`.
        """
        universe = self._universe(node)
        if token in universe:
            hit = universe[token]
            if hit is None:  # known-ambiguous: two values sanitise to this token
                return None, None, True
            return _coerce_choice_value(hit[0]), hit[1], True
        m = _NEG_TOKEN_RE.fullmatch(token)
        if m:  # only a negative number sanitises to a leading underscore
            return _coerce_choice_value("-" + m.group(1)), None, False
        return _coerce_choice_value(token), None, False

    def _choice_of(self, node: Node, token: str | None):
        """Return (choice code, label, string key, ambiguous) for a column's token."""
        if token is None:
            return None, None, None, False
        if not node.is_select_multiple:
            # Per-study dynamic calculates: `<node>_<id>`, no choice.
            return None, None, token, False
        choice, label, from_index = self._decode_choice(node, token)
        if choice is None and from_index:
            # The index knows this token maps to two different declared values,
            # so which choice it is cannot be recovered.
            return None, None, None, True
        if not from_index and _COMPOSITE_INT.fullmatch(token):
            # An UNRESOLVED multi-token all-integer choice is not a choice: a real
            # numeric value sanitises to exactly ONE token. This is the same drift
            # as in `map_column` but on a select_multiple, where the choice/index
            # boundary is unknowable from the contract, so no code is given. Gated
            # on `not from_index`: a value like `1_2` in the select's choices is a
            # real choice.
            return None, None, None, True
        return choice, label, None, False

    def map_column(self, col: str) -> dict:
        """Resolve a wide column to its node + repeat iterations + choice code.

        Returns {kind, ...}. kind is one of: 'system', 'matched', 'unmapped'.
        For 'matched': node_path, name, repeat_iterations (list of (group, index)),
        choice_code (int|str|None), is_select_multiple, and optionally
        choice_label, string_key, ambiguous_choice, ragged.

        Anchors on the NODE first, then on its repeat depth: exactly `depth`
        trailing integer tokens are iteration indices, and whatever precedes them
        is the (sanitised) choice value, so a text choice (`langs_ES`) or one whose
        own digits look like suffixes keeps its code.
        """
        if is_system_column(col):
            return {"kind": "system"}

        picked = self._resolve_node(col)
        if picked is None:
            return {"kind": "unmapped", "base": col, "indices": []}
        _, node, toks = picked
        depth = node.repeat_depth
        n, token = _split_suffix(toks, depth)

        # A node with no choices cannot have a numeric head: a purely numeric
        # surplus is formdef drift (the column was written while the node sat in
        # one more repeat) and the surplus index is the INNER one, so the node's
        # own coordinates are the LEADING tokens. Reading the trailing `depth`
        # instead would shift every repeat group by one.
        drift = bool(
            token is not None
            and not node.is_select_multiple
            and _ALL_INT.fullmatch(token)
        )
        if drift:
            idx_toks, token = toks[: min(depth, len(toks))], None
        else:
            idx_toks = toks[len(toks) - n :]
        # Drift can leave fewer indices than repeat levels.
        iters = list(zip(node.repeat_path, [int(t) for t in idx_toks], strict=False))
        choice, label, string_key, ambiguous_choice = self._choice_of(node, token)

        result = {
            "kind": "matched",
            "node_path": node.path,
            "name": node.name,
            "repeat_iterations": iters,
            "choice_code": choice,
            "is_select_multiple": node.is_select_multiple,
        }
        if label is not None:
            result["choice_label"] = label
        if string_key is not None:
            result["string_key"] = string_key
        if ambiguous_choice:
            # Without it a select_multiple binary with choice_code None reads as the
            # parent column.
            result["ambiguous_choice"] = True
        # Ragged: the column CARRIED a different number of repeat indices than the
        # node's depth. SurveyCTO emits exactly one index per level, so a mismatch is
        # flagged rather than truncated (over-indexed) or under-assigned. Counted
        # from what the column supplied, not from what was consumed: the drift
        # branch above absorbs the surplus index, and counting consumed tokens would
        # report a tidy match for the shape the flag surfaces.
        if (len(toks) if drift else n) != depth:
            result["ragged"] = True
        return result


def _label_text(label) -> str:
    """Return a <label>'s text with each <output value="expr"/> inlined as ``expr``."""
    parts = [label.text or ""]
    for child in label:
        if _ln(child.tag) == "output":
            parts.append(child.get("value", ""))
        parts.append(child.tail or "")
    return "".join(parts).strip()


# The columns of a SurveyCTO enumerator dataset an enumerator field stores, as
# "name (id)".
ENUMERATOR_COLUMNS = ("name", "id")

_ITEXT_REF = re.compile(r"^jr:itext\('([^']+)'\)$")
_ITEMSET = re.compile(r"^instance\('([^']+)'\)/root/item(?:\[(.*)\])?$", re.DOTALL)
# A choice filter that reads the submission: current() or a path to a field.
_READS_FORM = re.compile(r"current\(\)|(?<![\w)\]])/[A-Za-z_]")
_QUOTED = re.compile(r"('[^']*'|\"[^\"]*\")")
# A name in a choice filter that is neither a function call nor a path step: an
# item's column.
_BARE_NAME = re.compile(r"(?<![\w$'{/-])([A-Za-z_][\w-]*)(?![\w-]|\s*\()")
_XPATH_WORDS = {"and", "or", "div", "mod"}


class _Item:
    """A secondary-instance item as an expression row: its columns by name."""

    def __init__(self, columns: dict[str, str]):
        self.columns = columns

    def ref(self, name: str):
        return self.columns.get(name) or None


def _itemset_choices(
    itemset, instances: dict, itext: dict[str, str]
) -> tuple[list[dict], dict | None]:
    """Return the choices an ``<itemset>`` lists, its filter applied when static, and
    the filter: ``{"expression", "per_submission", "items"}`` (per_submission: it
    reads the submission, so each one sees part of the list; items: how many the list
    holds before a static filter). A choice carries the values of the item columns
    the filter names, as ``filter_columns``.
    """
    nodeset = itemset.get("nodeset")
    match = _ITEMSET.match(nodeset)
    if match is None:
        raise ValueError(f"itemset {nodeset!r} is not instance('...')/root/item[...]")
    items = instances[match.group(1)]
    predicate = match.group(2)
    per_submission = bool(predicate and _READS_FORM.search(predicate))
    columns = {k for item in items for k in item}
    named = sorted(
        {n for p in _QUOTED.split(predicate or "")[::2] for n in _BARE_NAME.findall(p)}
        & columns
    )
    listed = len(items)
    unresolved = False
    if predicate and not per_submission:
        kept = _apply_static_filter(items, predicate)
        unresolved = kept is None
        items = items if kept is None else kept
    refs = {_ln(c.tag): c.get("ref") for c in itemset}
    label_id = re.fullmatch(r"jr:itext\((\w+)\)", refs["label"])
    choices = [
        {
            "label": itext[item[label_id.group(1)]]
            if label_id
            else item[refs["label"]],
            "value": item[refs["value"]],
        }
        | ({"filter_columns": {c: item.get(c, "") for c in named}} if named else {})
        for item in items
    ]
    if not predicate:
        return choices, None
    choice_filter = {
        "expression": predicate,
        "per_submission": per_submission,
        "items": listed,
    }
    if unresolved:
        choice_filter["unresolved"] = True
    return choices, choice_filter


def _apply_static_filter(items: list[dict], predicate: str) -> list[dict] | None:
    """Return the items a static itemset filter keeps.

    Returns None when the filter uses XPath the evaluator does not implement
    (``normalize-space(...)``): which items it keeps is then unknown, and the
    form must still import.
    """
    # Columns become ${column} refs, outside quoted literals. A column an item
    # lacks reads as empty, as a path to no node does on the device.
    parts = _QUOTED.split(predicate)
    bare = {n for p in parts[::2] for n in _BARE_NAME.findall(p)} - _XPATH_WORDS
    names = sorted({k for item in items for k in item} | bare, key=len, reverse=True)
    word = re.compile(r"(?<![\w$'{-])(" + "|".join(names) + r")(?![\w(-])")
    expr = "".join(p if i % 2 else word.sub(r"${\1}", p) for i, p in enumerate(parts))
    try:
        keep = compile_expression(expr)
    except UnsupportedExpression:
        return None
    return [item for item in items if keep(_Item(item))]


def _default_itext(model) -> dict[str, str]:
    """Return ``{text id: text}`` from the default translation, or {} without itext.

    The default is the translation marked ``default="true()"``, else the first one;
    media forms (``<value form="image">``) are skipped, so a text with only media is
    "": its label has no words.
    """
    translations = [e for e in model.iter() if _ln(e.tag) == "translation"]
    if not translations:
        return {}
    default = next(
        (t for t in translations if t.get("default") == _TRUE), translations[0]
    )
    texts = {}
    for text in default:
        value = next(
            (v for v in text if _ln(v.tag) == "value" and not v.get("form")), None
        )
        texts[text.get("id")] = "" if value is None else _label_text(value)
    return texts


# XForm attribute values that mean true, as in `required="true()"`.
_TRUE = "true()"
_TRUE_VALUES = (_TRUE, "true", "1")

# Body elements whose local name is the control a field uses.
_CONTROLS = ("select", "select1", "input", "upload", "trigger", "range")


def _is_true(value: str) -> bool:
    """Return whether a bind attribute such as ``required`` is set to true."""
    return str(value).strip() in _TRUE_VALUES


def _child(el, tag: str):
    """Return ``el``'s first child with local name ``tag``, or None."""
    return next((c for c in el if _ln(c.tag) == tag), None)


def _read_root(xml_path):
    """Return the XML's root element, from a path or from bytes."""
    import xml.etree.ElementTree as ET

    if isinstance(xml_path, bytes):
        return ET.fromstring(xml_path)
    return ET.parse(str(xml_path)).getroot()


def _secondary_instances(model) -> dict[str, list[dict]]:
    """Return the static secondary instances (choice lists behind an itemset).

    SurveyCTO compiles datasets and choice lists into ``<instance id="...">``
    blocks; each is read item by item, as ``{column: text}``.
    """
    return {
        inst.get("id"): [
            {_ln(c.tag): (c.text or "") for c in item}
            for item in inst.iter()
            if _ln(item.tag) == "item"
        ]
        for inst in model
        if _ln(inst.tag) == "instance" and inst.get("id")
    }


def _walk(
    el,
    ancestors: list[str],
    repeats: list[str],
    nodes: dict[str, dict],
    repeat_tokens: set[str],
) -> None:
    """Record ``el`` and its descendants with their group and repeat ancestry."""
    name = _ln(el.tag)
    is_rep = any(_ln(k) == "template" for k in el.attrib)
    if is_rep:
        repeat_tokens.add(name)
    anc = [*ancestors, name]
    rep = [*repeats, name] if is_rep else list(repeats)
    kids = [c for c in el if isinstance(c.tag, str)]
    nodes["/".join(anc)] = {
        "group_path": anc[:-1],
        "repeat_path": rep[:-1] if is_rep else list(rep),
        "is_leaf": not kids,
    }
    for c in kids:
        _walk(c, anc, rep, nodes, repeat_tokens)


def _instance_nodes(primary) -> tuple[dict[str, dict], set[str]]:
    """Walk the primary instance: every node by path, and the repeat names."""
    nodes: dict[str, dict] = {}
    repeat_tokens: set[str] = set()
    for c in primary:
        if isinstance(c.tag, str):
            _walk(c, [], [], nodes, repeat_tokens)
    return nodes, repeat_tokens


def _binds(root, prefix: str) -> dict[str, dict]:
    """Return each bind's attributes by its path under the form root.

    Binds are the authoritative typed-node set and may target group nodes too.
    """
    return {
        el.get("nodeset")[len(prefix) :]: {_ln(k): v for k, v in el.attrib.items()}
        for el in root.iter()
        if _ln(el.tag) == "bind" and (el.get("nodeset") or "").startswith(prefix)
    }


class _Texts:
    """Read labels, hints and messages in the form's default translation."""

    def __init__(self, itext: dict[str, str]):
        self.itext = itext

    def label(self, label) -> str:
        """Return a <label> or <hint>'s text, itself or the itext it names."""
        ref = label.get("ref")
        return self.itext[_ITEXT_REF.match(ref).group(1)] if ref else _label_text(label)

    def message(self, message: str | None) -> str | None:
        """Return a bind's message, itself or the text its ``jr:itext()`` names."""
        if message is None:
            return None
        ref = _ITEXT_REF.match(message)
        return self.itext[ref.group(1)] if ref else message


@dataclass
class _Body:
    """What the body's controls say about each field, by its path.

    The appearance carries ``search(...)`` for select-from-file fields, which is
    the deterministic choice source (dataset + filter): ``Node.data_source``.
    """

    controls: dict[str, str] = field(default_factory=dict)
    appearances: dict[str, str] = field(default_factory=dict)
    items: dict[str, list[dict]] = field(default_factory=dict)
    # Selects whose list is filtered per submission.
    filtered: set[str] = field(default_factory=set)
    # Select -> its itemset's filter.
    choice_filters: dict[str, dict] = field(default_factory=dict)
    labels: dict[str, str] = field(default_factory=dict)
    hints: dict[str, str] = field(default_factory=dict)
    mediatypes: dict[str, str] = field(default_factory=dict)
    counts: dict[str, str] = field(default_factory=dict)
    # SurveyCTO lets a body control carry the calculate: a field prefilled or hidden.
    calculates: dict[str, str] = field(default_factory=dict)

    def read(self, el, rel: str, instances: dict, texts: _Texts) -> None:
        """Record what one body element says about the field at ``rel``."""
        ctl = _ln(el.tag)
        if ctl in _CONTROLS:
            self.controls[rel] = ctl
        for tag, store in (("label", self.labels), ("hint", self.hints)):
            child = _child(el, tag)
            if child is not None:
                store[rel] = texts.label(child)
        for attr, store in (
            ("mediatype", self.mediatypes),
            ("calculate", self.calculates),
            ("appearance", self.appearances),
        ):
            if el.get(attr):
                store[rel] = el.get(attr)
        if ctl == "repeat":
            count = next((v for k, v in el.attrib.items() if _ln(k) == "count"), None)
            if count is not None:
                self.counts[rel] = count
        if ctl in ("select", "select1"):
            self._read_choices(el, rel, instances, texts)

    def _read_choices(self, el, rel: str, instances: dict, texts: _Texts) -> None:
        """Record a select's <item> choices, then those of its itemsets."""
        items = [
            {
                "label": next(
                    (texts.label(c) for c in it if _ln(c.tag) == "label"), None
                ),
                "value": next((c.text for c in it if _ln(c.tag) == "value"), None),
            }
            for it in el
            if _ln(it.tag) == "item"
        ]
        for itemset in (c for c in el if _ln(c.tag) == "itemset"):
            choices, choice_filter = _itemset_choices(itemset, instances, texts.itext)
            items += choices
            if choice_filter:
                self.choice_filters[rel] = choice_filter
                # A filter that cannot be run keeps every item, so like a
                # per-submission filter only the codes someone picked are known
                # to have been offered.
                if choice_filter["per_submission"] or choice_filter.get("unresolved"):
                    self.filtered.add(rel)
        self.items[rel] = items


def _read_body(root, prefix: str, instances: dict, texts: _Texts) -> _Body:
    """Read the body's controls: ref (full path) -> what they say about the field."""
    body = _Body()
    element = _child(root, "body")
    if element is None:
        return body
    for el in element.iter():
        ref = el.get("ref") or el.get("nodeset")
        if ref and ref.startswith(prefix):
            body.read(el, ref[len(prefix) :], instances, texts)
    return body


def _node(
    path: str,
    inst: dict,
    b: dict,
    body: _Body,
    texts: _Texts,
    repeat_tokens: set[str],
) -> Node:
    """Merge a path's instance node, bind and body control into a Node."""
    toks = path.split("/")
    rep = inst.get("repeat_path", [t for t in toks[:-1] if t in repeat_tokens])
    ctl = body.controls.get(path)
    ap = body.appearances.get(path)
    calculate = b.get("calculate") or body.calculates.get(path)
    source = _parse_data_source(ap, calculate)
    searched = bool(source and source["kind"] == "search")
    choice_items, choice_columns = body.items.get(path, []), None
    if searched:
        choice_items, choice_columns = _split_search_items(choice_items)
    return Node(
        path=path,
        name=toks[-1],
        group_path=inst.get("group_path", toks[:-1]),
        repeat_path=rep,
        repeat_depth=len(rep),
        is_leaf=inst.get("is_leaf", True),
        xml_type=b.get("type"),
        control=_SELECT_CONTROL.get(ctl, ctl),
        is_select_multiple=ctl == "select" or b.get("type") == "select",
        choice_items=choice_items,
        choice_columns=choice_columns,
        calculate=calculate,
        calculation_is_default=not b.get("calculate") and path in body.calculates,
        relevant=b.get("relevant"),
        constraint=b.get("constraint"),
        required=_is_true(b.get("required", "")),
        readonly=_is_true(b.get("readonly", "")),
        publishable=_is_true(b.get("publishable", "")),
        preload=b.get("preload"),
        preload_params=b.get("preloadParams"),
        data_source=source,
        # A search() select's dataset codes are unknown here, so its binaries
        # are only the codes someone picked.
        choices_per_submission=path in body.filtered or searched,
        choice_filter=body.choice_filters.get(path),
        original=b.get("original"),
        field_type=b.get("fieldType"),
        label=body.labels.get(path),
        hint=body.hints.get(path),
        constraint_message=texts.message(b.get("constraintMsg")),
        mediatype=body.mediatypes.get(path),
        appearance=ap,
        bind_appearance=b.get("appearance"),
        repeat_count=body.counts.get(path),
    )


def _resolve_named_datasets(nodes: dict[str, Node], prefix: str) -> None:
    """Resolve each search() dataset named through a field.

    A dataset named through a field (`search(${list_name})`) is that field's
    literal calculate, `string('roster')` or `'roster'`. Any other calculate
    (`concat(...)`, `if(...)`) picks the dataset per submission, so the
    dataset stays unknown (None) and `dataset_field` names the field. The
    form still imports: nothing downstream needs the dataset's name.
    """
    for node in nodes.values():
        source = node.data_source
        if not (source and source["dataset"].startswith(prefix)):
            continue
        field_path = source["dataset"][len(prefix) :]
        named_by = nodes.get(field_path)
        calculate = named_by.calculate if named_by else None
        literal = _STRING_LITERAL.match((calculate or "").strip())
        if literal:
            source["dataset"] = literal.group(2).removesuffix(".csv")
        else:
            source["dataset"] = None
            source["dataset_field"] = field_path


def parse_contract(xml_path) -> FormContract:
    """Parse a compiled XForm XML, as a path or as bytes, into a FormContract."""
    root = _read_root(xml_path)
    # The primary instance is the model's <instance> without an `id`; its first
    # element is the form root.
    (model,) = [e for e in root.iter() if _ln(e.tag) == "model"]
    (primary_instance,) = [
        e for e in model if _ln(e.tag) == "instance" and not e.get("id")
    ]
    primary = next(c for c in primary_instance if isinstance(c.tag, str))
    texts = _Texts(_default_itext(model))
    formid = primary.get("id") or _ln(primary.tag)
    prefix = f"/{formid}/"

    instance_nodes, repeat_tokens = _instance_nodes(primary)
    binds = _binds(root, prefix)
    body = _read_body(root, prefix, _secondary_instances(model), texts)

    # Instance document order is form order; binds without an instance node follow.
    paths = [*instance_nodes, *(p for p in binds if p not in instance_nodes)]
    nodes = {
        path: _node(
            path,
            instance_nodes.get(path, {}),
            binds.get(path, {}),
            body,
            texts,
            repeat_tokens,
        )
        for path in paths
    }
    _resolve_named_datasets(nodes, prefix)

    encrypted = any(
        _ln(el.tag) == "submission" and el.get("base64RsaPublicKey")
        for el in root.iter()
    )
    return FormContract(formid, primary.get("version"), nodes, encrypted=encrypted)
