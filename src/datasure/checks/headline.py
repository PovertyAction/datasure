"""A check's headline: the numbers Summary's check health row shows for it.

Each check with a single triage number returns a ``CheckHeadline`` from its
headline function. Every number must match what the check itself reports.
Kept free of Streamlit and of the checks, so any check can import it.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

import polars as pl
from pydantic import ValidationError

if TYPE_CHECKING:
    # Only named in annotations, so this module stays free of the checks.
    from datasure.checks.duplicates import DuplicatesBasis
    from datasure.checks.gpschecks.review import GPSOutlierSummary
    from datasure.checks.outliers.report_ui import OutliersBasis


@dataclass(frozen=True)
class CheckHeadline:
    """The numbers on a check's health row.

    Attributes
    ----------
    value : str
        The outstanding number as shown, such as "14", "12.5%" or "310 / 500".
    detail : str
        The line under the value, such as "duplicate IDs" or "of columns
        all missing (5 of 40)".
    outstanding : float | None
        The issues still to deal with; more than 0 flags the row. Usually a
        count, but for Missing Values the percentage of columns all missing
        (12.5 for 12.5%). None when the check has no issue count.
    resolved : int | None
        Issues resolved through corrections, acceptances or attributions;
        None for checks that resolve nothing.
    informational : bool
        The value describes the data rather than counting issues, as for
        Progress and Enumerator Stats, so the row is never flagged.
    count : float | None
        The number an informational value shows, such as the submissions or
        the active enumerators, which its change over the comparison period
        compares. None when the value has no such number.
    basis : DuplicatesBasis | GPSOutlierSummary | OutliersBasis | None
        What the check computed the numbers from, such as its flags, so its
        delta can reuse them instead of computing them again: Duplicates'
        ``DuplicatesBasis``, Outliers' ``OutliersBasis`` and GPS Checks'
        ``GPSOutlierSummary``; None for the other checks. Only valid for
        the data the headline was computed on; Summary keeps it out of the
        headline cache. Not compared, so headlines with equal numbers are
        equal.
    """

    value: str
    detail: str = ""
    outstanding: float | None = None
    resolved: int | None = None
    informational: bool = False
    count: float | None = None
    basis: "DuplicatesBasis | GPSOutlierSummary | OutliersBasis | None" = field(
        default=None, compare=False, repr=False
    )

    @property
    def flagged(self) -> bool:
        """Whether the row has outstanding issues."""
        return (
            not self.informational
            and self.outstanding is not None
            and self.outstanding > 0
        )


@dataclass(frozen=True)
class EnumeratorScope:
    """Whose issues a check counts for the Enumerator page.

    Attributes
    ----------
    enumerator : str
        The page's enumerator column.
    team_column : str | None
        The page's team column, if set.
    team : str | None
        The team the Enumerator page is narrowed to; None for all teams.
        Records outside it, or with no team, are left out of the counts. A
        check still finds its issues on all its records, so a duplicate ID
        shared with another team is still a duplicate.
    """

    enumerator: str
    team_column: str | None = None
    team: str | None = None

    @property
    def narrowed(self) -> bool:
        """Whether a team is chosen."""
        return self.team is not None and self.team_column is not None

    def keep(self, data: pl.DataFrame) -> pl.DataFrame:
        """Return the rows of `data` in the chosen team; all rows without one.

        With a team chosen but its column not in `data`, no row can be
        placed in the team, so none is kept.
        """
        if not self.narrowed:
            return data
        if self.team_column not in data.columns:
            return data.clear()
        return data.filter(pl.col(self.team_column).cast(pl.String) == self.team)


@dataclass(frozen=True)
class ByEnumerator:
    """A check's outstanding issues, split by the enumerator they belong to.

    For the Enumerator page's "Needs attention" list. ``counts`` plus
    ``unattributed`` is the check's own total, so the list can say how many
    issues it could not place.

    Attributes
    ----------
    counts : dict[str, int]
        Issues by enumerator, as text; enumerators with none are left out.
    unattributed : int
        Issues on records with no enumerator.
    """

    counts: dict[str, int] = field(default_factory=dict)
    unattributed: int = 0

    @property
    def total(self) -> int:
        """All the issues, placed or not."""
        return sum(self.counts.values()) + self.unattributed


class DeltaKind(StrEnum):
    """What a row's outstanding change measures, which sets how it reads."""

    # Issues among the submissions dated in the period: "▲ 3 new".
    NEW = "new"
    # A change in percentage points, as for Missing Values.
    POINTS = "points"
    # IDs first completed in the period, as for Progress.
    COMPLETIONS = "completions"
    # A change in active enumerators, as for Enumerator Stats.
    ACTIVE = "active"


@dataclass(frozen=True)
class CheckDelta:
    """How a check's health row changed over the comparison period.

    Attributes
    ----------
    outstanding : float | None
        The change in the outstanding number, read as `kind` says; None when
        it cannot be computed.
    resolved : int | None
        Resolutions logged in the period that are still in effect; None for
        checks that resolve nothing.
    kind : DeltaKind
        What `outstanding` measures.
    """

    outstanding: float | None = None
    resolved: int | None = None
    kind: DeltaKind = DeltaKind.NEW


def settings_no_longer_fit(check: str, cause: Exception) -> ValueError:
    """Return the error a headline raises when saved settings no longer fit.

    A headline that cannot compute its numbers raises rather than returning
    None, so Summary shows the check's row as an error with this reason
    instead of as having no issues.

    Parameters
    ----------
    check : str
        The check's label, such as "Outliers".
    cause : Exception
        Why the numbers could not be computed.
    """
    if isinstance(cause, ValidationError):
        reason = "; ".join(
            f"{'.'.join(map(str, error['loc']))}: {error['msg']}"
            for error in cause.errors()
        )
    else:
        reason = str(cause) or type(cause).__name__
    return ValueError(
        f"The saved {check} settings no longer fit the data ({reason}). "
        "Open the check to review them."
    )
