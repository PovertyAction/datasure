"""Rules for new column names.

DataSure allows any column name that doesn't clash with an existing column
(see ``existing_name_error``). The Stata replication package can only use
names that follow Stata's rules (see ``stata_name_error``); the replication
generator checks names there, and mapping names to Stata-safe ones is
tracked in #449.

This module has no third-party imports so the replication generator can use
it without loading the app.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

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
