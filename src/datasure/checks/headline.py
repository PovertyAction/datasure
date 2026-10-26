"""A check's headline: the numbers Summary's check health row shows for it.

Each check with a single triage number returns a ``CheckHeadline`` from its
headline function. Every number must match what the check itself reports.
Kept free of Streamlit and of the checks, so any check can import it.
"""

from dataclasses import dataclass
from enum import StrEnum

from pydantic import ValidationError


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
    """

    value: str
    detail: str = ""
    outstanding: float | None = None
    resolved: int | None = None
    informational: bool = False
    count: float | None = None

    @property
    def flagged(self) -> bool:
        """Whether the row has outstanding issues."""
        return (
            not self.informational
            and self.outstanding is not None
            and self.outstanding > 0
        )


class DeltaKind(StrEnum):
    """What a row's outstanding change measures, which sets how it reads."""

    # Issues among the submissions dated in the period: "▲ 3 new".
    NEW = "new"
    # A change in percentage points, as for Missing Values.
    POINTS = "points"
    # Submissions dated in the period, as for Progress.
    SUBMISSIONS = "submissions"
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
