"""Column-name rules for prep steps that create or rename columns.

Prep steps are replayed in DataSure and translated into ``prepare_data.do``
for the replication package, so every new column name must also be a valid
Stata variable name. The Prep page and the prep engine both check names here.

This module has no third-party imports so the replication generator and the
form helpers can use it without loading the app.
"""

from __future__ import annotations

import re

STATA_NAME_MAX_LENGTH = 32

# ASCII only: ``\w`` would also accept non-ASCII letters, which Stata rejects.
_STATA_NAME_CHARS = re.compile(r"[A-Za-z0-9_]*")


def stata_name_error(name: str) -> str | None:
    """Return why ``name`` can't be a Stata variable name, or None if it can.

    A valid name has at most 32 characters, starts with a letter or ``_``,
    and uses only ASCII letters, digits and ``_``.
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
    return None
