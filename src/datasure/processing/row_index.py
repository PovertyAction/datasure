"""Row-index values for the "remove row(s) by row index" prep step.

The prep engine and the Stata replication generator both read these values, so
they are parsed here, in one place, to keep the two in step.

A value is a row position counting from 0, a negative position counting back
from the end (``-1`` is the last row), or an inclusive range ``a:b`` whose ends
follow the same rules. Prep logs saved by earlier versions may hold ``","``,
``""`` or ``None`` entries; these are skipped.

This module has no third-party imports so the replication generator can use it
without loading the app.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


@dataclass(frozen=True)
class RowSpan:
    """An inclusive span of row positions, 0-based, either end may be negative."""

    start: int
    end: int

    @property
    def is_single(self) -> bool:
        """Whether the span names one row."""
        return self.start == self.end


def _parse_int(text: str, original: object) -> int:
    try:
        return int(text)
    except ValueError:
        raise ValueError(f"'{original}' is not a valid row index") from None


def _parse_item(item: object) -> list[RowSpan]:
    # A bool is an int in Python; it falls through to the text path and fails
    if isinstance(item, int) and not isinstance(item, bool):
        return [RowSpan(item, item)]
    if isinstance(item, float) and item.is_integer():
        return [RowSpan(int(item), int(item))]

    spans: list[RowSpan] = []
    for raw_part in str(item).split(","):
        part = raw_part.strip()
        if not part:
            continue
        if ":" in part:
            bounds = part.split(":")
            if len(bounds) != 2:
                raise ValueError(f"'{part}' is not a valid row index range")
            start = _parse_int(bounds[0].strip(), part)
            end = _parse_int(bounds[1].strip(), part)
            spans.append(RowSpan(start, end))
        else:
            index = _parse_int(part, part)
            spans.append(RowSpan(index, index))
    return spans


def parse_row_indices(values: object) -> list[RowSpan]:
    """Parse stored row-index values into spans, in the order given.

    Raises
    ------
    ValueError
        If a value is not an integer, a negative integer, or an ``a:b`` range.
    """
    if values is None:
        return []
    items: Iterable[object] = values if isinstance(values, (list, tuple)) else [values]
    spans: list[RowSpan] = []
    for item in items:
        if item is None:
            continue
        spans.extend(_parse_item(item))
    return spans


def resolve_row_positions(spans: Iterable[RowSpan], n_rows: int) -> set[int]:
    """Return the 0-based positions the spans select in a table of ``n_rows``.

    Negative ends count back from ``n_rows``. Positions outside the table are
    ignored, and a span whose start falls after its end selects nothing.
    """
    positions: set[int] = set()
    for span in spans:
        start = span.start + n_rows if span.start < 0 else span.start
        end = span.end + n_rows if span.end < 0 else span.end
        positions.update(range(max(start, 0), min(end, n_rows - 1) + 1))
    return positions
