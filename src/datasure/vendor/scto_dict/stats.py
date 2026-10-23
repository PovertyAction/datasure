"""Summary statistics per column that follow skip logic and leave sentinel codes out.

A row counts toward a column only where the question was asked: every enclosing
group relevance and the question's own relevance evaluate true on that row (and
repeat instance), and the instance is within the repeat count (``jr:count``, or the
highest instance present when the repeat has none). Sentinel codes (-99, ...) stay coded in the data; here they are
counted apart and excluded from every statistic. Columns flagged ``contains_pii`` or
``may_contain_pii`` get counts only, never values. One CSV row per parquet column.
"""

import csv
import datetime as dt
import json
import statistics
from pathlib import Path

import pyarrow.parquet as pq

from datasure.vendor.scto_dict.dictionary import kept
from datasure.vendor.scto_dict.pii import shows_values
from datasure.vendor.scto_dict.survey import choice_labels, gates, rule
from datasure.vendor.scto_dict.xpath import (
    UnsupportedExpression,
    compile_expression,
    reads_self,
    to_number,
)

COLUMNS = [
    "variable",
    "question",
    "type",
    "required",
    "pii_status",
    "relevance",
    "eligibility_evaluated",
    "eligibility_note",
    "rows",
    "eligible",
    "skipped_by_logic",
    "answered",
    "sentinel",
    "sentinel_detail",
    "missing_when_eligible",
    "answered_when_skipped",
    "n_valid",
    "mean",
    "sd",
    "min",
    "p25",
    "median",
    "p75",
    "max",
    "selected",
    "selected_share",
    "n_distinct",
    "frequencies",
]
RAGGED_NOTE = "layout from another form version; not evaluated"
# Each column's type when the CSV is read back: min, median and max hold a number or
# a date, so text.
SQL_TYPES = {
    **dict.fromkeys(COLUMNS, "VARCHAR"),
    "eligibility_evaluated": "BOOLEAN",
    "required": "BOOLEAN",
    **dict.fromkeys(
        (
            "rows",
            "eligible",
            "skipped_by_logic",
            "answered",
            "sentinel",
            "missing_when_eligible",
            "answered_when_skipped",
            "n_valid",
            "selected",
            "n_distinct",
        ),
        "BIGINT",
    ),
    **dict.fromkeys(("mean", "sd", "p25", "p75", "selected_share"), "DOUBLE"),
}


def _plain(value):
    """Return a value the expression evaluator reads: dates as ISO text."""
    if isinstance(value, (dt.date, dt.datetime)):
        return value.isoformat()
    return value


class _Data:
    """Column values plus the lookups relevance needs: question -> column per instance."""

    def __init__(self, table, questions: dict, variables: dict):
        self.values = {
            name: [_plain(v) for v in col] for name, col in table.to_pydict().items()
        }
        self.questions = questions
        # repeat name -> its synthetic `<repeat>_count` question
        self.count_questions = {
            q["repeat_group_name"]: q
            for q in questions.values()
            if q["type"] == "repeat_count"
        }
        self.repeats = set(self.count_questions)
        self.chains = {
            name: [g for g in q["group_path"] if g in self.repeats]
            for name, q in questions.items()
        }
        # Results shared by every column a gate or repeat count applies to; see
        # `_gate` and `_within`.
        self.gates: dict[tuple, list] = {}
        self.limits: dict[tuple, list] = {}
        self.columns: dict[tuple, str] = {}
        # (repeat, parent instances) -> {instance: columns}, for repeats without a count
        self.instance_columns: dict[tuple, dict[int, list[str]]] = {}
        self.binaries: dict[tuple, list[tuple[str, str]]] = {}
        for column, entry in variables.items():
            # A ragged column (another form version's layout) would take the place
            # of the real column of the same instance.
            if entry["question"] is None or entry.get("ragged"):
                continue
            key = (entry["question"], tuple(entry.get("repeat_iteration", [])))
            if "choice_value" in entry:
                self.binaries.setdefault(key, []).append(
                    (entry["choice_value"], column)
                )
            else:
                self.columns[key] = column
            iterations = key[1]
            if iterations:
                repeat = self.repeat_chain(entry["question"])[-1]
                slot = self.instance_columns.setdefault((repeat, iterations[:-1]), {})
                slot.setdefault(iterations[-1], []).append(column)

    def highest_instance(self, repeat: str, parent: tuple[int, ...], row: int) -> int:
        """Return the highest instance of ``repeat`` with any value on ``row``."""
        present = [
            instance
            for instance, columns in self.instance_columns.get(
                (repeat, parent), {}
            ).items()
            if any(self.values[c][row] is not None for c in columns)
        ]
        return max(present, default=0)

    def repeat_chain(self, question: str) -> list[str]:
        return self.chains[question]

    def value(self, question: str, iterations: tuple[int, ...], row: int):
        """Return ``question``'s value on ``row`` in the given repeat instance."""
        key = (question, iterations)
        if key in self.binaries:
            chosen = [
                code for code, col in self.binaries[key] if self.values[col][row] == 1
            ]
            answered = any(
                self.values[col][row] is not None for _, col in self.binaries[key]
            )
            return " ".join(chosen) if answered else None
        column = self.columns.get(key)
        return None if column is None else self.values[column][row]


class _Row:
    """The evaluation context of one column on one row."""

    def __init__(self, data: _Data, question: str, iterations: tuple, row: int, own):
        self.data, self.question, self.iterations, self.row, self.own = (
            data,
            question,
            iterations,
            row,
            own,
        )

    def ref(self, name: str):
        if name == ".":
            return self.own
        if name not in self.data.questions:
            raise UnsupportedExpression(f"${{{name}}} is not a question in the data")
        chain = self.data.repeat_chain(name)
        if len(chain) > len(self.iterations):
            raise UnsupportedExpression(
                f"${{{name}}} sits in a repeat inside the group whose condition reads it"
            )
        if chain != self.data.repeat_chain(self.question)[: len(chain)]:
            raise UnsupportedExpression(
                f"${{{name}}} sits in a repeat that does not enclose {self.question}"
            )
        return self.data.value(name, self.iterations[: len(chain)], self.row)

    def index(self) -> int:
        if not self.iterations:
            raise UnsupportedExpression("index() outside a repeat")
        return self.iterations[-1]


def _gate(data: _Data, gate: str, question: str, iterations: tuple, own: list):
    """Return row -> whether ``gate`` holds for ``question`` in this repeat instance.

    A gate that does not read ``.`` gives the same answer for every question in the
    same repeats and instance (a group's relevance, a select_multiple's binaries), so
    each row is evaluated once and shared.
    """
    fn = compile_expression(gate)
    if reads_self(gate):
        return lambda r: bool(fn(_Row(data, question, iterations, r, own[r])))
    key = (gate, tuple(data.repeat_chain(question)[: len(iterations)]), iterations)
    memo = data.gates.setdefault(key, [None] * len(own))

    def holds(r: int) -> bool:
        if memo[r] is None:
            memo[r] = bool(fn(_Row(data, question, iterations, r, None)))
        return memo[r]

    return holds


def _within(data: _Data, repeat: str, parent: tuple, n_rows: int) -> list:
    """Return the instances of ``repeat`` under ``parent`` on each row."""
    key = (repeat, parent)
    if key not in data.limits:
        count_q = data.count_questions[repeat]
        if count_q["calculation"] is None:
            limits = [data.highest_instance(repeat, parent, r) for r in range(n_rows)]
        else:
            count = compile_expression(count_q["calculation"])
            # An empty or invalid count gives no instances, as on the device.
            limits = [
                to_number(count(_Row(data, count_q["variable_name"], parent, r, None)))
                for r in range(n_rows)
            ]
        data.limits[key] = limits
    return data.limits[key]


def _eligibility(
    data: _Data,
    q: dict | None,
    column: str | None,
    iterations: tuple,
    n_rows: int,
    ragged: bool = False,
):
    """Return (per-row eligibility, composed rule, evaluated, note)."""
    if q is None:
        return [True] * n_rows, "", True, ""
    conditions = gates(q)
    composed = rule(conditions)
    if ragged:
        # Its repeat indices do not fit the form's nesting, so the conditions
        # cannot be read at the right level.
        return [True] * n_rows, composed, False, RAGGED_NOTE
    if q["disabled"]:
        return [False] * n_rows, composed, True, "disabled"
    # A question with no column has no value of its own: `.` reads as empty.
    own = data.values[column] if column else [None] * n_rows
    try:
        # Each gate at its own repeat level: index() in a group's condition is the
        # index of that group's repeat, not the question's innermost one.
        tests = [
            _gate(
                data,
                g["relevance"],
                q["variable_name"],
                iterations[: g["repeat_depth"]],
                own,
            )
            for g in q["gates"]
        ]
        eligible = [all(t(r) for t in tests) for r in range(n_rows)]
        # A repeat instance exists only up to the repeat count, at every level.
        for level, repeat in enumerate(data.repeat_chain(q["variable_name"])):
            instance, parent = iterations[level], iterations[:level]
            limits = _within(data, repeat, parent, n_rows)
            eligible = [
                e and instance <= c for e, c in zip(eligible, limits, strict=True)
            ]
    except UnsupportedExpression as e:
        return [True] * n_rows, composed, False, f"{e}; counted over all rows"
    return eligible, composed, True, ""


def reached(table, questions: list[dict], vardict: dict) -> dict[str, int | None]:
    """Return how many submissions reach each question no submission answered: its
    conditions hold, in some instance of its repeats. None when they cannot be
    evaluated. The rows are the ones the dictionary counts ([submissions] exclude).
    """
    variables = vardict["variables"]
    table = kept(table, vardict["dataset"]["exclude"])
    data = _Data(table, {q["variable_name"]: q for q in questions}, variables)
    n_rows = table.num_rows
    answered = {v["question"] for v in variables.values()}
    found: dict[str, int | None] = {}
    for q in questions:
        name = q["variable_name"]
        if q["type"] == "repeat_count" or name in answered:
            continue
        try:
            # Every instance its repeats can have on some row, level by level.
            instances: list[tuple] = [()]
            for repeat in data.repeat_chain(name):
                instances = [
                    (*parent, i)
                    for parent in instances
                    for i in range(
                        1,
                        int(
                            max(
                                (
                                    c
                                    for c in _within(data, repeat, parent, n_rows)
                                    if c == c
                                ),
                                default=0,
                            )
                        )
                        + 1,
                    )
                ]
            rows = [False] * n_rows
            for iterations in instances:
                eligible, _, evaluated, _ = _eligibility(
                    data, q, None, iterations, n_rows
                )
                if not evaluated:
                    raise UnsupportedExpression(name)
                rows = [a or b for a, b in zip(rows, eligible, strict=True)]
            found[name] = sum(rows)
        except UnsupportedExpression:
            found[name] = None
    return found


def _fmt(x: float) -> float:
    return round(x, 4)


def summary_stats(
    form_dir: Path, form_id: str, sentinels: dict[int, str]
) -> list[dict]:
    """Return one stats row per parquet column, in column order."""
    form_dir = Path(form_dir)
    questions = json.loads(
        (form_dir / f"{form_id}_questions.json").read_text(encoding="utf-8")
    )
    dictionary = json.loads(
        (form_dir / f"{form_id}_variable_dictionary.json").read_text(encoding="utf-8")
    )
    return stats_rows(
        pq.read_table(form_dir / f"{form_id}.parquet"), questions, dictionary, sentinels
    )


def stats_rows(
    table, questions: list[dict], dictionary: dict, sentinels: dict[int, str]
) -> list[dict]:
    """Return one stats row per column of ``table``, in the dictionary's order.

    ``questions`` and ``dictionary`` are what ``build_questions`` and
    ``build_dictionary`` return, with the PII blocks attached.
    """
    questions = {q["variable_name"]: q for q in questions}
    variables = dictionary["variables"]
    # The rows the build counted: [submissions] exclude leaves some out.
    table = kept(table, dictionary["dataset"]["exclude"])
    data = _Data(table, questions, variables)
    n_rows = table.num_rows
    # Numeric codes as numbers and as text; date codes as ISO text, as dates are read.
    sentinel_codes = {
        **{c: m for c, m in sentinels.items() if isinstance(c, int)},
        **{str(c): m for c, m in sentinels.items()},
    }

    rows = []
    for column, entry in variables.items():
        q = questions.get(entry["question"]) if entry["question"] else None
        iterations = tuple(entry.get("repeat_iteration", []))
        ragged = bool(entry.get("ragged"))
        eligible, rule, evaluated, note = _eligibility(
            data, q, column, iterations, n_rows, ragged
        )
        values = data.values[column]
        is_binary = "choice_value" in entry
        # A timestamp is read as ISO text; a date sentinel matches its day.
        day = entry["parquet"]["arrow_type"].startswith("timestamp")
        labels = choice_labels(q["choices"]) if q and q["choices"] else {}
        sentinel_hits: dict = {}
        valid = []
        answered = missing = outside = 0
        for v, ok in zip(values, eligible, strict=True):
            if v is None:
                missing += ok
                continue
            if not ok:
                outside += 1
                continue
            code = v[:10] if day else v
            if not is_binary and not isinstance(v, bool) and code in sentinel_codes:
                sentinel_hits[code] = sentinel_hits.get(code, 0) + 1
                continue
            answered += 1
            valid.append(v)

        pii = entry["pii"]["status"]
        out = dict.fromkeys(COLUMNS, "")
        out.update(
            variable=column,
            question=entry["question"] or "",
            type=q["type"] if q else ("system" if entry.get("system") else ""),
            # missing_when_eligible on a required question is a gap the form forbids.
            required=q["required"] if q else "",
            pii_status=pii,
            relevance=rule,
            eligibility_evaluated=evaluated,
            eligibility_note=note,
            rows=n_rows,
            eligible=sum(eligible),
            skipped_by_logic=n_rows - sum(eligible),
            answered=answered,
            sentinel=sum(sentinel_hits.values()),
            sentinel_detail="; ".join(
                f"{c} {labels.get(str(c), sentinel_codes[c])}: {n}"
                for c, n in sorted(sentinel_hits.items(), key=str)
            ),
            # A column with no question (a note, a group, a field from another form
            # version) has no rule saying when it should hold a value, and a ragged
            # one no rule that can be read.
            missing_when_eligible=(
                missing if (q or entry.get("system")) and not ragged else ""
            ),
            answered_when_skipped="" if ragged else outside,
            n_valid=len(valid),
        )
        if shows_values(pii) and valid:
            out.update(_describe(valid, entry, q, is_binary))
        rows.append(out)
    return rows


def _describe(valid: list, entry: dict, q: dict | None, is_binary: bool) -> dict:
    """Value-level statistics for a column that may be read."""
    arrow_type = entry["parquet"]["arrow_type"]
    if is_binary:
        selected = sum(1 for v in valid if v == 1)
        return {"selected": selected, "selected_share": _fmt(selected / len(valid))}
    # A select_one gets frequencies whether its codes are stored as text or integers.
    if q is not None and q["type"] == "select_one":
        # A withheld list has no labels here, only the codes found.
        labels = {} if q["choices_withheld"] else choice_labels(q["choices"])
        counts = {code: 0 for code in labels}
        for v in valid:
            counts[str(v)] = counts.get(str(v), 0) + 1
        return {
            "frequencies": "; ".join(
                f"{code} {labels.get(code, '(not listed)' if q['choices_withheld'] else '(not a choice)')}: "
                f"{n} ({n / len(valid):.1%})"
                for code, n in counts.items()
            )
        }
    if arrow_type in ("int64", "double"):
        cuts = (
            statistics.quantiles(valid, n=4, method="inclusive")
            if len(valid) > 1
            else valid * 3
        )
        return {
            "mean": _fmt(statistics.fmean(valid)),
            "sd": _fmt(statistics.stdev(valid)) if len(valid) > 1 else "",
            "min": min(valid),
            "p25": _fmt(cuts[0]),
            "median": _fmt(cuts[1]),
            "p75": _fmt(cuts[2]),
            "max": max(valid),
        }
    if arrow_type.startswith(("date32", "timestamp")):
        ordered = sorted(valid)
        return {
            "min": ordered[0],
            "median": ordered[len(ordered) // 2],
            "max": ordered[-1],
        }
    return {"n_distinct": len(set(valid))}


def write_csv(rows: list[dict], path: Path) -> Path:
    """Write the stats rows as CSV (UTF-8 with BOM, so Excel reads accents)."""
    path = Path(path)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    return path


def write_form_stats(
    form_dir: Path, form_id: str, sentinels: dict[int, str]
) -> list[dict]:
    """Write ``<form>_summary_stats.csv`` and report it; return the rows."""
    rows = summary_stats(form_dir, form_id, sentinels)
    path = write_csv(rows, Path(form_dir) / f"{form_id}_summary_stats.csv")
    unevaluated = sum(1 for r in rows if not r["eligibility_evaluated"])
    flagged = sum(1 for r in rows if r["answered_when_skipped"])
    print(
        f"[stats] {form_id}: {len(rows)} columns, {unevaluated} with relevance not "
        f"evaluated, {flagged} answered where skip logic says skipped -> {path}"
    )
    return rows


def main(argv: list[str] | None = None) -> None:
    """Entry point for ``scto-stats``: write ``<form>_summary_stats.csv`` from built outputs."""
    from dotenv import load_dotenv

    from datasure.vendor.scto_dict.cli import config_arg, env_sentinels

    cfg = config_arg(argv)
    load_dotenv()
    sentinels = env_sentinels()
    for form in cfg.forms:
        write_form_stats(cfg.form_dir(form), form, sentinels)
