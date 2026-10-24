"""Question helpers the dictionary, stats and PII rules share.

Choice labels, a question's gates (its groups' relevances, then its own) and
the rule they compose, and plain-text labels.
"""

import re

# As pii.FLAGGED: this module imports only the standard library (the skill ships it).
_FLAGGED = {"contains_pii", "may_contain_pii"}
# Longer lists are summarised, with an argument that lists them in full.
# An HTML tag: `<` then a letter or `/`, so `<5 and >10` is text.
_TAG_RE = re.compile(r"</?[A-Za-z][^<>]*>")


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


def gates(q: dict) -> list[str]:
    """Return what must hold for ``q`` to be asked: group relevances, then its own."""
    return [*q["group_relevances"], *([q["relevance"]] if q["relevance"] else [])]


def rule(conditions: list[str]) -> str:
    """Join conditions with ``and``, each in parentheses when there are several."""
    if len(conditions) == 1:
        return conditions[0]
    return " and ".join(f"({c})" for c in conditions)


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


# A wide column's instance suffixes: score_2_1 -> score.
# The literal start of a column named per row: concat('score_', index()).
