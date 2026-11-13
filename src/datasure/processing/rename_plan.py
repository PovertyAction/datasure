"""Resolve a column rename into old → new pairs, and find what blocks it.

The Prep rename step and the rename form's live preview both call
``plan_rename``, so what the preview shows is what the step does.

Renames apply all at once: collisions are judged against the final set of
names, so swaps (``a→b, b→a``) and chains are allowed. Names are compared
ignoring case, because DuckDB, which stores the prepared data, treats ``Age``
and ``age`` as one name.

This module has no third-party imports so the replication generator can use
it without loading the app.
"""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ByName:
    """Rename the listed columns: ``pairs`` holds (old, new) names."""

    pairs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class Wildcard:
    """Rename columns matching ``old`` to ``new``, Stata style.

    ``*`` matches any run of characters, including none, and ``?`` exactly
    one. ``old`` must match the whole name. The wildcards in ``new`` are
    filled in order with what the wildcards in ``old`` matched. When a name
    could match in more than one way, earlier wildcards take as much as they
    can (``*_*`` splits ``a_b_c`` into ``a_b`` and ``c``).
    """

    old: str
    new: str


@dataclass(frozen=True)
class ChangeCase:
    """Lowercase or uppercase the names of columns matching ``filter``.

    ``case`` is ``"lower"`` or ``"upper"``. ``filter`` is a wildcard pattern
    as in ``Wildcard``; empty means every column.
    """

    case: str
    filter: str = "*"


@dataclass(frozen=True)
class RegexRename:
    """Rename columns whose whole name matches the Python regex ``pattern``.

    ``replacement`` can use back-references to the pattern's groups, such as
    a backslash followed by the group number.
    """

    pattern: str
    replacement: str


RenameSpec = ByName | Wildcard | ChangeCase | RegexRename

CASES = ("lower", "upper")

_WILDCARDS = "*?"
_UNSUPPORTED_WILDCARDS = "#="

# How a rename step is logged. These mirror PrepMethods (kept as strings so
# the replication generator needn't import the app's enums). A by-name step's
# ``value`` holds its requested [old, new] pairs; a by-pattern step's holds
# [mode, first input, second input].
METHOD_BY_NAME = "by name"
METHOD_BY_PATTERN = "by pattern"
MODE_WILDCARD = "wildcard"
MODE_CASE = "change case"
MODE_REGEX = "regex"
PATTERN_MODES = (MODE_WILDCARD, MODE_CASE, MODE_REGEX)


def spec_to_args(spec: RenameSpec) -> tuple[str, list]:
    """Return the (method, value) a rename step is logged with."""
    if isinstance(spec, ByName):
        return METHOD_BY_NAME, [[old, new] for old, new in spec.pairs]
    if isinstance(spec, Wildcard):
        return METHOD_BY_PATTERN, [MODE_WILDCARD, spec.old, spec.new]
    if isinstance(spec, ChangeCase):
        return METHOD_BY_PATTERN, [MODE_CASE, spec.case, spec.filter]
    return METHOD_BY_PATTERN, [MODE_REGEX, spec.pattern, spec.replacement]


def spec_from_args(method: str | None, value: object) -> RenameSpec:
    """Rebuild the spec a rename step was logged with.

    Raises
    ------
    ValueError
        If ``method`` and ``value`` don't describe a rename.
    """
    is_list = isinstance(value, list)
    if (
        method == METHOD_BY_NAME
        and is_list
        and all(isinstance(p, list | tuple) and len(p) == 2 for p in value)
    ):
        return ByName(tuple((str(old), str(new)) for old, new in value))
    if method == METHOD_BY_PATTERN and is_list and len(value) == 3:
        mode, first, second = (str(v) if v is not None else "" for v in value)
        if mode == MODE_WILDCARD:
            return Wildcard(first, second)
        if mode == MODE_CASE:
            return ChangeCase(first, second or "*")
        if mode == MODE_REGEX:
            return RegexRename(first, second)
    raise ValueError(f"Unknown rename: method {method!r}, inputs {value!r}.")


def describe_pattern(spec: RenameSpec) -> str:
    """Describe a pattern spec in words, for the log and the Stata comment.

    A by-name spec has no pattern and gives an empty string.
    """
    if isinstance(spec, Wildcard):
        return f'matching "{spec.old}" to "{spec.new}"'
    if isinstance(spec, ChangeCase):
        return f'matching "{spec.filter or "*"}" to {spec.case}case'
    if isinstance(spec, RegexRename):
        return f'matching regex "{spec.pattern}" to "{spec.replacement}"'
    return ""


@dataclass(frozen=True)
class RenamePlan:
    """What a rename spec does to a set of columns.

    Attributes
    ----------
    pairs
        The resolved (old, new) pairs, in column order. A name that would
        not change is left out.
    collisions
        New names that clash with a column that isn't renamed away, or with
        another new name in the plan.
    invalid
        New names DataSure can't use (an empty name).
    missing
        For a by-name spec, the old names that aren't columns.
    matched
        For a pattern spec, every column the pattern fits, including those
        whose name wouldn't change.
    problems
        Why each pair can't be applied, keyed by its old name, for flagging
        rows in the preview.
    error
        Why the spec itself can't be used (for example, a regex that won't
        compile), or None.
    """

    pairs: tuple[tuple[str, str], ...] = ()
    collisions: tuple[str, ...] = ()
    invalid: tuple[str, ...] = ()
    missing: tuple[str, ...] = ()
    matched: tuple[str, ...] = ()
    problems: dict[str, str] = field(default_factory=dict)
    error: str | None = None

    @property
    def old_names(self) -> list[str]:
        """The old name of each pair, in column order."""
        return [old for old, _ in self.pairs]

    @property
    def new_names(self) -> list[str]:
        """The new name of each pair, in column order."""
        return [new for _, new in self.pairs]

    @property
    def can_apply(self) -> bool:
        """True when the plan renames something and nothing blocks it."""
        return bool(self.pairs) and not (self.collisions or self.invalid or self.error)


def plan_rename(columns: Sequence[str], spec: RenameSpec) -> RenamePlan:
    """Return the plan for renaming ``columns`` as ``spec`` says."""
    columns = list(columns)
    if isinstance(spec, ByName):
        return _plan_by_name(columns, spec)
    if isinstance(spec, Wildcard):
        error = _wildcard_error(spec)
        rename = None if error else _wildcard_renamer(spec)
    elif isinstance(spec, ChangeCase):
        error = None if spec.case in CASES else "Choose lower or upper case."
        rename = None if error else _case_renamer(spec)
    else:
        error, rename = _regex_renamer(spec)
    if error or rename is None:
        return RenamePlan(error=error)
    return _plan_pattern(columns, rename)


def _plan_by_name(columns: list[str], spec: ByName) -> RenamePlan:
    """Resolve listed pairs; old names that aren't columns are missing."""
    repeated = [old for old, n in Counter(o for o, _ in spec.pairs).items() if n > 1]
    if repeated:
        return RenamePlan(error=f"'{repeated[0]}' is listed more than once.")
    requested = dict(spec.pairs)
    pairs = tuple(
        (old, requested[old])
        for old in columns
        if old in requested and requested[old] != old
    )
    missing = tuple(old for old in requested if old not in columns)
    return _check_pairs(columns, pairs, missing=missing)


# A pattern renamer returns a column's new name, or None if it doesn't match.
_Renamer = Callable[[str], "str | None"]


def _plan_pattern(columns: list[str], rename: _Renamer) -> RenamePlan:
    """Resolve a pattern rename by applying ``rename`` to every column."""
    matched: list[str] = []
    pairs: list[tuple[str, str]] = []
    for column in columns:
        try:
            new = rename(column)
        except _SpecError as e:
            return RenamePlan(error=str(e))
        if new is None:
            continue
        matched.append(column)
        if new != column:
            pairs.append((column, new))
    return _check_pairs(columns, tuple(pairs), matched=tuple(matched))


def _wildcard_renamer(spec: Wildcard) -> _Renamer:
    matcher = wildcard_regex(spec.old)

    def rename(column: str) -> str | None:
        match = matcher.fullmatch(column)
        return _fill_wildcards(spec.new, match.groups()) if match else None

    return rename


def _case_renamer(spec: ChangeCase) -> _Renamer:
    matcher = wildcard_regex(spec.filter or "*")

    def rename(column: str) -> str | None:
        if not matcher.fullmatch(column):
            return None
        return column.lower() if spec.case == "lower" else column.upper()

    return rename


def _regex_renamer(spec: RegexRename) -> tuple[str | None, _Renamer | None]:
    """Return (error, renamer) for a regex spec; one of them is None."""
    if not spec.pattern:
        return "Enter a regex.", None
    try:
        matcher = re.compile(spec.pattern)
    except re.error as e:
        return f"The regex can't be used: {e}.", None

    def rename(column: str) -> str | None:
        match = matcher.fullmatch(column)
        if not match:
            return None
        try:
            return match.expand(spec.replacement)
        except (re.error, IndexError) as e:
            raise _SpecError(f"The replacement can't be used: {e}.") from e

    return None, rename


class _SpecError(Exception):
    """A spec that can only be found unusable while applying it to a name."""


def _wildcard_error(spec: Wildcard) -> str | None:
    """Return why a wildcard spec can't be used, or None."""
    if not spec.old:
        return "Enter the old pattern."
    if not spec.new:
        return "Enter the new pattern."
    if any(c in _UNSUPPORTED_WILDCARDS for c in spec.old + spec.new):
        return "Stata's # and = wildcards aren't supported. Use * or ?, or a regex."
    old_count = sum(spec.old.count(c) for c in _WILDCARDS)
    new_count = sum(spec.new.count(c) for c in _WILDCARDS)
    if old_count != new_count:
        return (
            "The old and new patterns need the same number of wildcards "
            f"(the old pattern has {old_count}, the new pattern has {new_count})."
        )
    return None


def wildcard_regex(pattern: str) -> re.Pattern[str]:
    """Compile a ``*``/``?`` wildcard pattern, one group per wildcard.

    Match it with ``fullmatch``: the pattern must fit the whole name.
    """
    parts = []
    for char in pattern:
        if char == "*":
            parts.append("(.*)")
        elif char == "?":
            parts.append("(.)")
        else:
            parts.append(re.escape(char))
    return re.compile("".join(parts), re.DOTALL)


def _fill_wildcards(pattern: str, values: Sequence[str]) -> str:
    """Replace each wildcard in ``pattern``, in order, with the next value."""
    filled = iter(values)
    return "".join(next(filled) if c in _WILDCARDS else c for c in pattern)


def _check_pairs(
    columns: list[str],
    pairs: tuple[tuple[str, str], ...],
    *,
    missing: tuple[str, ...] = (),
    matched: tuple[str, ...] = (),
) -> RenamePlan:
    """Find the collisions and invalid names among resolved ``pairs``."""
    renamed = dict(pairs)
    final_names = [renamed.get(column, column) for column in columns]
    counts = Counter(name.lower() for name in final_names)

    collisions: list[str] = []
    invalid: list[str] = []
    problems: dict[str, str] = {}
    for old, new in pairs:
        if not new.strip():
            invalid.append(new)
            problems[old] = "Enter a new name."
        elif counts[new.lower()] > 1:
            collisions.append(new)
            problems[old] = _collision_reason(old, new, columns, renamed)

    return RenamePlan(
        pairs=pairs,
        collisions=tuple(collisions),
        invalid=tuple(invalid),
        missing=missing,
        matched=matched,
        problems=problems,
    )


def _collision_reason(
    old: str, new: str, columns: list[str], renamed: dict[str, str]
) -> str:
    """Explain what ``new`` clashes with in the final set of names."""
    for other_old, other_new in renamed.items():
        if other_old != old and other_new.lower() == new.lower():
            return f"'{other_old}' is also renamed to '{other_new}'."
    for column in columns:
        if column not in renamed and column.lower() == new.lower():
            return f"'{column}' is already a column and isn't renamed."
    return f"'{new}' is used more than once."
