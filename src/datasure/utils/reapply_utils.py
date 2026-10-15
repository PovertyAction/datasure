"""Shared helpers for reporting partial failures during bulk reapply.

Both the prep log (processing/prep.py) and correction log
(processing/corrections.py) can be reapplied in bulk against refreshed
upstream data - e.g. after a re-import changes the underlying columns. A
single incompatible step should not abort the whole sequence, but it also
should not be silently dropped. This module gives both paths a common type
for reporting what was skipped and why, and a single Streamlit helper for
surfacing it at the UI boundary.
"""

from dataclasses import dataclass


@dataclass
class ReapplyFailure:
    """A single step or correction skipped during a bulk reapply."""

    step: str
    reason: str


def highlight_status(value: object) -> str:
    """Style a log status cell: green text for Successful, red for Failed.

    Used with a pandas ``Styler`` (``df.style.map(highlight_status,
    subset=["status"])``) on the prep and correction Change Log tables.
    """
    if not isinstance(value, str):
        # Missing (None or pd.NA, which can't be used in a boolean test).
        return ""
    if value == "Failed":
        return "color: #dc3545; font-weight: 600"
    if value == "Successful":
        return "color: #198754; font-weight: 600"
    return ""


def warn_reapply_failures(failures: list[ReapplyFailure], context: str) -> None:
    """Render one warning summarizing steps skipped during a bulk reapply.

    Parameters
    ----------
    failures : list[ReapplyFailure]
        Steps/corrections skipped during the reapply, in the order they were
        encountered. No-op when empty.
    context : str
        Short lead-in describing what was being reapplied, e.g. "Some
        preparation steps could not be reapplied".
    """
    if not failures:
        return

    import streamlit as st

    st.warning(format_reapply_failures(failures, context))


def format_reapply_failures(failures: list[ReapplyFailure], context: str) -> str:
    """Summarize skipped steps as Markdown: a lead-in, then one bullet each.

    Parameters
    ----------
    failures : list[ReapplyFailure]
        Steps/corrections skipped during the reapply, in order.
    context : str
        Short lead-in describing what was being reapplied.
    """
    lines = "\n".join(f"- {f.step}: {f.reason}" for f in failures)
    return f"{context} ({len(failures)} skipped):\n{lines}"
