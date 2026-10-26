"""A check's headline: the numbers Summary's check health row shows for it.

Each check with a single triage number returns a ``CheckHeadline`` from its
headline function. Every number must match what the check itself reports.
Kept free of Streamlit and of the checks, so any check can import it.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class CheckHeadline:
    """The numbers on a check's health row.

    Attributes
    ----------
    value : str
        The outstanding number as shown, such as "14", "12.5%" or "310 / 500".
    detail : str
        The line under the value, such as "duplicate IDs" or "5 of 40
        columns".
    outstanding : float | None
        The issues still to deal with; more than 0 flags the row. None when
        the check has no issue count.
    resolved : int | None
        Issues resolved through corrections, acceptances or attributions;
        None for checks that resolve nothing.
    informational : bool
        The value describes the data rather than counting issues, as for
        Progress and Enumerator Stats, so the row is never flagged.
    """

    value: str
    detail: str = ""
    outstanding: float | None = None
    resolved: int | None = None
    informational: bool = False

    @property
    def flagged(self) -> bool:
        """Whether the row has outstanding issues."""
        return (
            not self.informational
            and self.outstanding is not None
            and self.outstanding > 0
        )
