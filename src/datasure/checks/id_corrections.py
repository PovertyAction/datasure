"""Decisions that resolve the ID problems shown as cards on the Duplicates tab.

An ID belongs to one record. On a duplicate ID card the user decides, for each
record, to keep it, give it another ID or drop it; on an unmatched backcheck
card, to give it another ID or drop it. One save logs one correction per
changed record, all or nothing, with the same reason on every entry.

The functions here are pure; `id_duplicates_ui` renders the controls.
"""

import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Any

import polars as pl

from datasure.processing.correction_log import Action
from datasure.processing.corrections import CorrectionEntry

logger = logging.getLogger(__name__)

# Recorded as the `source` of every log entry a card save makes.
SOURCE = "duplicates"

REASONS = (
    "Repeat visit",
    "Wrong ID entered",
    "Duplicate submission",
    "Test or practice submission",
    "Other",
)


class Decision(StrEnum):
    """What to do with one record on a card."""

    KEEP = "Keep"
    MODIFY_ID = "Modify ID"
    DROP = "Drop"


DUPLICATE_DECISIONS = (Decision.KEEP, Decision.MODIFY_ID, Decision.DROP)
# An unmatched backcheck can't be kept as is: its ID matches no survey.
UNMATCHED_DECISIONS = (Decision.MODIFY_ID, Decision.DROP)


@dataclass(frozen=True)
class RecordDecision:
    """The decision for one record on a card.

    Attributes
    ----------
    key : Any
        The record's KEY, as stored in the data.
    decision : Decision
        What to do with the record.
    new_id : str | None
        For `Decision.MODIFY_ID`, the ID to give the record.
    """

    key: Any
    decision: Decision
    new_id: str | None = None


def _clean(new_id: str | None) -> str:
    return (new_id or "").strip()


def _id_text(id_col: str) -> pl.Expr:
    return pl.col(id_col).cast(pl.String)


def _fits(new_id: str, dtype: pl.DataType) -> bool:
    """Whether `new_id` can be stored in a column of `dtype` as it is.

    A value that doesn't fit would turn the whole ID column into text.
    """
    if dtype == pl.String:
        return True
    try:
        pl.Series([new_id]).cast(dtype, strict=True)
    except pl.exceptions.PolarsError:
        logger.debug("New ID %r does not fit %s", new_id, dtype, exc_info=True)
        return False
    return True


def _unresolved(decisions: Sequence[RecordDecision], original_id: str) -> list[str]:
    kept = sum(d.decision == Decision.KEEP for d in decisions)
    if kept <= 1:
        return []
    return [
        f"{kept} records still hold ID {original_id}. Keep at most one: modify "
        "or drop the others."
    ]


def _keys_holding(included: pl.DataFrame, id_col: str, key_col: str, new_id: str):
    return (
        included.filter(_id_text(id_col) == new_id)[key_col].cast(pl.String).to_list()
    )


def _new_id_problems(
    decisions: Sequence[RecordDecision],
    original_id: str,
    included: pl.DataFrame,
    id_col: str,
    key_col: str,
    survey_ids: Iterable[str] | None,
) -> list[str]:
    problems: list[str] = []
    survey_id_set = None if survey_ids is None else {str(i) for i in survey_ids}
    claimed: dict[str, Any] = {}
    for d in decisions:
        if d.decision != Decision.MODIFY_ID:
            continue
        new_id = _clean(d.new_id)
        if not new_id:
            problems.append(f"Enter a new ID for KEY {d.key}.")
            continue
        if new_id == original_id:
            problems.append(
                f"The new ID for KEY {d.key} is the same as its current ID."
            )
            continue
        if new_id in claimed:
            problems.append(
                f"KEY {claimed[new_id]} and KEY {d.key} have the same new ID {new_id}."
            )
            continue
        claimed[new_id] = d.key
        if not _fits(new_id, dtype := included.schema[id_col]):
            kind = "a number" if dtype.is_numeric() else f"a {dtype} value"
            problems.append(f"ID {new_id} is not {kind}, as {id_col} values are.")
        elif holders := _keys_holding(included, id_col, key_col, new_id):
            problems.append(f"ID {new_id} already belongs to KEY {', '.join(holders)}.")
        elif survey_id_set is not None and new_id not in survey_id_set:
            problems.append(f"ID {new_id} is not in the survey data.")
    return problems


def save_blockers(
    decisions: Sequence[RecordDecision],
    *,
    original_id: str,
    included: pl.DataFrame,
    id_col: str,
    key_col: str,
    reason: str | None,
    note: str | None,
    survey_ids: Iterable[str] | None = None,
) -> list[str]:
    """Return why a card can't be saved yet, or an empty list if it can.

    A card can be saved once at most one record keeps the ID, every new ID is
    valid, and a reason and a note are given. A new ID is valid when it is
    not empty, differs from the current ID and from the other new IDs in the
    save, and is not held by any of the `included` records (the records
    Records to Include keeps). For an unmatched backcheck, `survey_ids` lists
    the survey IDs, and the new ID must be one of them. IDs compare as text.

    Parameters
    ----------
    decisions : Sequence[RecordDecision]
        One decision per record on the card.
    original_id : str
        The ID the card's records hold, as text.
    included : pl.DataFrame
        The included records of the card's dataset.
    id_col, key_col : str
        The ID and KEY columns.
    reason : str | None
        The reason chosen for the save.
    note : str | None
        The note entered for the save.
    survey_ids : Iterable[str] | None
        For an unmatched backcheck card, the survey IDs a new ID must match.
    """
    blockers = _unresolved(decisions, original_id)
    blockers += _new_id_problems(
        decisions, original_id, included, id_col, key_col, survey_ids
    )
    if not reason:
        blockers.append("Choose a reason.")
    if not (note or "").strip():
        blockers.append("Enter a note.")
    return blockers


def all_dropped(decisions: Sequence[RecordDecision]) -> bool:
    """Whether every record on the card is dropped, removing the ID."""
    return bool(decisions) and all(d.decision == Decision.DROP for d in decisions)


def log_reason(reason: str, note: str) -> str:
    """Return the reason recorded in the log: the reason and the note."""
    return f"{reason}: {note.strip()}"


def build_entries(
    decisions: Sequence[RecordDecision],
    *,
    original_id: str,
    id_col: str,
    reason: str,
) -> list[CorrectionEntry]:
    """Return one log entry per changed record, in card order.

    Modify ID becomes "modify value" on `id_col`, and Drop becomes "remove
    row". Kept records need no entry. Every entry records `reason` and the
    original ID.
    """
    entries = []
    for d in decisions:
        if d.decision == Decision.MODIFY_ID:
            entries.append(
                CorrectionEntry(
                    key_value=d.key,
                    action=Action.MODIFY_VALUE,
                    reason=reason,
                    column=id_col,
                    current_value=original_id,
                    new_value=_clean(d.new_id),
                    survey_id_value=original_id,
                )
            )
        elif d.decision == Decision.DROP:
            entries.append(
                CorrectionEntry(
                    key_value=d.key,
                    action=Action.REMOVE_ROW,
                    reason=reason,
                    survey_id_value=original_id,
                )
            )
    return entries


def has_repeated_keys(records: pl.DataFrame, key_col: str) -> bool:
    """Whether two of `records` share a KEY.

    A correction applies to every row with its KEY, so the records on such a
    card can't be told apart.
    """
    return records[key_col].n_unique() < records.height
