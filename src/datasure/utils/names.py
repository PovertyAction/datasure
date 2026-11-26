"""The one name rule for dataset aliases and check page names.

People type these names freely, and each one becomes a storage ID: a DuckDB
table name for an alias, settings file and check table names for a page.
Every part of the app turns a name into its ID with ``name_id`` and checks
new names with ``name_problem`` and ``name_clash``, so two entries can never
share storage and no name can break a file path.
"""

import re
from collections.abc import Callable, Iterable

from pydantic import ValidationError, ValidationInfo

NAME_MAX_LENGTH = 20

ALLOWED_NAME_CHARACTERS = "letters, digits, spaces, underscores (_) and hyphens (-)"

# Validation context for names already saved in a project. Names created
# before the rule may break it; they load unchanged instead of failing.
STORED_NAME = {"stored_name": True}

# Help text for alias and page name inputs.
NAME_RULE_HELP = (
    f"Start with a letter; use only {ALLOWED_NAME_CHARACTERS}. "
    f"Max {NAME_MAX_LENGTH} characters."
)

_NAME_PATTERN = re.compile(r"[A-Za-z][A-Za-z0-9 _-]*")
_DISALLOWED = re.compile(r"[^A-Za-z0-9 _-]")


def name_problem(name: str, label: str = "Name") -> str | None:
    """Return why ``name`` can't be used as an alias or page name.

    Returns ``None`` when the name is allowed. ``label`` starts the message
    ("Alias", "Page name"). Callers trim surrounding spaces before checking.
    """
    if not name or not name.strip():
        return f"{label} cannot be empty"
    if len(name) > NAME_MAX_LENGTH:
        return f"{label} must be at most {NAME_MAX_LENGTH} characters"
    if not _NAME_PATTERN.fullmatch(name):
        return (
            f"{label} must start with a letter and contain only "
            f"{ALLOWED_NAME_CHARACTERS}"
        )
    return None


def validate_name(value: str, info: ValidationInfo, label: str) -> str:
    """Pydantic field validator body for an alias or page name.

    Trims spaces and enforces the name rule, unless the model is validated
    with the ``STORED_NAME`` context. A stored name is returned exactly as
    saved, because its table and settings IDs were built from it.
    """
    if not value or not value.strip():
        raise ValueError(f"{label} cannot be empty")
    if (info.context or {}).get("stored_name"):
        return value
    value = value.strip()
    problem = name_problem(value, label)
    if problem:
        raise ValueError(problem)
    return value


def validation_message(error: ValidationError) -> str:
    """Return a model's validation errors as plain sentences for users.

    Drops Pydantic's ``Value error,`` prefix so a rejected name reads as the
    rule, for example "Alias must start with a letter ...".
    """
    return "; ".join(
        detail["msg"].removeprefix("Value error, ") for detail in error.errors()
    )


def name_id(name: str) -> str:
    """Return the storage ID of a page or dataset name.

    Lower case, with spaces and hyphens as underscores. Used for table names,
    settings file names and the Corrections ``page`` URL value. Existing
    projects already store IDs in this form, so it must not change.
    """
    return name.lower().replace(" ", "_").replace("-", "_")


def name_clash(
    name: str,
    existing: Iterable[str],
    *,
    kind: str,
    own: str | None = None,
    id_of: Callable[[str], str] = name_id,
) -> str | None:
    """Return a message if ``name`` shares its ID with an existing entry.

    ``kind`` names the entry type in the message ("alias", "page name").
    ``own`` is the entry's current name when renaming it, so a rename that
    keeps its own ID (such as a change of case) is allowed. ``id_of`` maps a
    name to the ID it is stored under.
    """
    new_id = id_of(name)
    own_id = id_of(own) if own is not None else None
    for other in existing:
        if other is None or id_of(other) != new_id or new_id == own_id:
            continue
        return (
            f"'{name}' is too similar to existing {kind} '{other}'. "
            "Please choose a different name."
        )
    return None


def suggest_name(text: str) -> str:
    """Turn free text, such as a form title, into an allowed name.

    Disallowed characters become underscores and the result is cut to the
    length limit. Returns an empty string when no allowed name results, for
    example when the text starts with a digit.
    """
    suggestion = _DISALLOWED.sub("_", text.strip())[:NAME_MAX_LENGTH].rstrip()
    return suggestion if name_problem(suggestion) is None else ""
