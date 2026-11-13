"""Rules for new column names.

DataSure allows any column name that doesn't clash with an existing column
(see ``existing_name_error``). The Stata replication package can only use
names that follow Stata's rules (see ``stata_name_error``), so when the
package is built every other name is mapped to a Stata-safe one
(``stata_name_map``).

This module has no third-party imports so the replication generator can use
it without loading the app.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable, Mapping

STATA_NAME_MAX_LENGTH = 32

# ASCII only: ``\w`` would also accept non-ASCII letters, which Stata rejects.
_STATA_NAME_CHARS = re.compile(r"[A-Za-z0-9_]*")

# Names Stata reserves, from the Stata User's Guide, [U] 11.3 Naming
# conventions. Stata is case-sensitive, so only exact matches are reserved.
STATA_RESERVED_NAMES = frozenset(
    {
        "alias",
        "_all",
        "_b",
        "byte",
        "_coef",
        "_cons",
        "double",
        "float",
        "if",
        "in",
        "int",
        "long",
        "_n",
        "_N",
        "_pi",
        "_pred",
        "_r_b",
        "_r_ci",
        "_r_cri",
        "_r_crlb",
        "_r_crub",
        "_r_df",
        "_r_lb",
        "_r_p",
        "_r_se",
        "_r_ub",
        "_r_z",
        "_r_z_abs",
        "_rc",
        "_se",
        "_skip",
        "strL",
        "using",
        "with",
    }
)

# The reserved ``str#`` string types: str1, str80, ...
_STATA_STR_TYPE = re.compile(r"str[0-9]+")


def existing_name_error(name: str, columns: Iterable[str]) -> str | None:
    """Return why ``name`` clashes with one of ``columns``, or None if it doesn't.

    The comparison ignores case: DuckDB, which stores the prepared data,
    treats ``Age`` and ``age`` as one name and would quietly rename the
    second to ``Age_1``.
    """
    columns = list(columns)
    if name in columns:
        return f"Column '{name}' already exists."
    for column in columns:
        if column.lower() == name.lower():
            return (
                f"Column '{name}' already exists as '{column}'. Names that "
                "differ only in upper or lower case can't both be used."
            )
    return None


def stata_name_error(name: str) -> str | None:
    """Return why ``name`` can't be a Stata variable name, or None if it can.

    A valid name has at most 32 characters, starts with a letter or ``_``,
    uses only ASCII letters, digits and ``_``, and isn't one of the names
    Stata reserves.
    """
    if not name:
        return "Enter a column name."
    if len(name) > STATA_NAME_MAX_LENGTH:
        return (
            f"'{name}' has {len(name)} characters. Stata names can have at most "
            f"{STATA_NAME_MAX_LENGTH} characters."
        )
    if not _STATA_NAME_CHARS.fullmatch(name):
        return (
            f"'{name}' can use only letters, digits and _ (no spaces, "
            "punctuation or accented letters)."
        )
    if name[0].isdigit():
        return f"'{name}' must start with a letter or _."
    if name in STATA_RESERVED_NAMES or _STATA_STR_TYPE.fullmatch(name):
        return f"'{name}' is reserved by Stata. Choose another name."
    return None


_NOT_STATA_CHAR = re.compile(r"[^A-Za-z0-9_]")


def _is_reserved(name: str) -> bool:
    return name in STATA_RESERVED_NAMES or bool(_STATA_STR_TYPE.fullmatch(name))


def _propose_stata_name(name: str) -> str:
    """Stata-safe form of ``name``, before making it unique."""
    # Accented letters become their plain letter: "âge" -> "age".
    ascii_name = "".join(
        ch
        for ch in unicodedata.normalize("NFKD", name)
        if not unicodedata.combining(ch)
    )
    proposal = _NOT_STATA_CHAR.sub("_", ascii_name) or "var"
    if proposal[0].isdigit():
        proposal = "_" + proposal
    proposal = proposal[:STATA_NAME_MAX_LENGTH]
    if _is_reserved(proposal):
        proposal = proposal[: STATA_NAME_MAX_LENGTH - 1] + "_"
    return proposal


def _unique(proposal: str, taken: set[str]) -> str:
    """``proposal``, or ``proposal_2``, ``_3`` ... cut to fit, if it is taken."""
    candidate, n = proposal, 1
    while candidate in taken:
        n += 1
        suffix = f"_{n}"
        candidate = proposal[: STATA_NAME_MAX_LENGTH - len(suffix)] + suffix
    return candidate


def stata_name_edit_errors(
    names: Iterable[str], edits: Mapping[str, str]
) -> dict[str, str]:
    """Return why each edited Stata name can't be used, keyed by DataSure name.

    ``edits`` maps DataSure names to the Stata names people typed. An edit
    must follow Stata's rules, must not be a name the package already uses
    unchanged, and must not be used by another edit. Edits for names that
    need no mapping are ignored, as ``stata_name_map`` ignores them.
    """
    names = list(dict.fromkeys(names))
    kept = {name for name in names if stata_name_error(name) is None}
    edited = {name: edits[name] for name in names if name not in kept and name in edits}
    errors: dict[str, str] = {}
    for name, new in edited.items():
        rule_error = stata_name_error(new)
        if rule_error:
            errors[name] = rule_error
        elif new in kept:
            errors[name] = f"'{new}' is already the name of another column."
        elif sum(other == new for other in edited.values()) > 1:
            errors[name] = f"'{new}' is used for more than one column."
    return errors


def stata_name_map(
    names: Iterable[str], edits: Mapping[str, str] | None = None
) -> dict[str, str]:
    """Map each name Stata can't use to a unique Stata-safe name.

    ``names`` is every column name the package uses, in order: the imported
    columns, then the names prep steps create. Names Stata can already use
    are never changed and are left out of the result, and no mapped name
    takes one of them. The rules: characters outside ``[A-Za-z0-9_]``
    become ``_`` (accented letters become their plain letter), a leading
    digit gets ``_`` in front, a reserved name gets ``_`` after, names are
    cut to 32 characters, and a name already taken gets ``_2``, ``_3`` ...

    ``edits`` holds names people chose instead of the proposals. Edits
    without an error from ``stata_name_edit_errors`` are used and claim
    their names first; the rest fall back to the proposal.
    """
    names = list(dict.fromkeys(names))
    edits = dict(edits or {})
    kept = {name for name in names if stata_name_error(name) is None}
    errors = stata_name_edit_errors(names, edits)
    mapping: dict[str, str] = {
        name: edits[name]
        for name in names
        if name not in kept and name in edits and name not in errors
    }
    taken = kept | set(mapping.values())
    for name in names:
        if name in kept or name in mapping:
            continue
        mapping[name] = _unique(_propose_stata_name(name), taken)
        taken.add(mapping[name])
    return {name: mapping[name] for name in names if name in mapping}
