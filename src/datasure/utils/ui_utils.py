"""Shared UI helpers for consistent page structure across DataSure views.

These helpers centralize the repeated Streamlit patterns (page headers,
section headers, destructive-action confirmations, metric rows, and messages
that must survive a rerun) so every view renders them identically. The module
is intentionally UI-only: it holds no data-access logic and is safe to import
from any view.

Streamlit is imported inside each helper rather than at module level. Views
are page scripts whose tests swap ``sys.modules["streamlit"]`` for a mock at
import time; resolving the module per call ensures these helpers honor that
swap regardless of the order in which the module was first imported.
"""

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    import polars as pl
    from pandas.io.formats.style import Styler

NoticeLevel = Literal["success", "warning", "error", "toast"]

_QUEUED_NOTICES_KEY = "st_queued_notices"


@dataclass(frozen=True)
class Notice:
    """A message queued for the next run of a page."""

    level: NoticeLevel
    message: str


def page_header(title: str, subtitle: str | None = None, *, divider: bool = True):
    """Render a standard page header.

    Parameters
    ----------
    title : str
        The page title. Should match the sidebar navigation label so the
        in-page heading and the nav entry stay in sync.
    subtitle : str, optional
        A short descriptive line shown under the title as a caption. Use this
        for the one-sentence "what this page does" prose that previously lived
        in loose ``st.markdown`` calls.
    divider : bool, default True
        Whether to draw a horizontal rule under the header. Standardizes on
        ``st.divider()`` in place of the mixed ``st.write("---")`` usage.
    """
    import streamlit as st

    st.title(title)
    if subtitle:
        st.caption(subtitle)
    if divider:
        st.divider()


def section_header(text: str, icon: str | None = None):
    """Render a standard section subheader.

    Parameters
    ----------
    text : str
        The section label. Do not include a trailing colon; consistency is
        enforced here so callers cannot reintroduce the "Apply Changes:" vs
        "Change Log" mismatch.
    icon : str, optional
        A Material Symbols shortcode (e.g. ``":material/key:"``) rendered
        before the label.
    """
    import streamlit as st

    label = f"{icon} {text}" if icon else text
    st.subheader(label)


def metric_row(metrics: Sequence[tuple]):
    """Render a row of equal-width, bordered metrics.

    Using this helper keeps metric rows aligned across the Import, Prepare, and
    Correct pages, which previously used differing column ratios.

    Parameters
    ----------
    metrics : sequence of tuple
        Each tuple is ``(label, value)`` or ``(label, value, help_text)``.
    """
    import streamlit as st

    cols = st.columns(len(metrics), border=True)
    for col, metric in zip(cols, metrics, strict=True):
        label = metric[0]
        value = metric[1]
        help_text = metric[2] if len(metric) > 2 else None
        col.metric(label, value, help=help_text)


def confirm_dialog(
    title: str,
    body: str,
    *,
    on_confirm: Callable[[], None],
    confirm_label: str = "Confirm",
    cancel_label: str = "Cancel",
    danger: bool = True,
):
    """Open a modal dialog to confirm a destructive action.

    This is the single confirmation idiom for the whole app, replacing the
    ad hoc session-state flags, inline warnings, and confirm-inside-expander
    patterns that previously differed per view.

    Call this directly from a button handler, e.g.::

        if st.button("Delete project"):
            confirm_dialog(
                "Delete project",
                "This permanently deletes the project and all its data.",
                confirm_label="Delete",
                on_confirm=lambda: delete_project(project_id),
            )

    Parameters
    ----------
    title : str
        The dialog title.
    body : str
        The explanatory / warning text shown in the dialog body.
    on_confirm : callable
        Called with no arguments when the user confirms. If it does not itself
        navigate away (e.g. via ``st.switch_page``), the app reruns afterward
        to dismiss the dialog.
    confirm_label : str, default "Confirm"
        Label for the confirm button.
    cancel_label : str, default "Cancel"
        Label for the cancel button.
    danger : bool, default True
        When True, the body is shown as a warning callout; otherwise as plain
        text.
    """
    import streamlit as st

    @st.dialog(title)
    def _dialog():
        if danger:
            st.warning(body, icon=":material/warning:")
        else:
            st.write(body)

        confirm_col, cancel_col = st.columns(2)
        with confirm_col:
            if st.button(
                confirm_label,
                type="primary",
                width="stretch",
                key=f"_confirm_{title}",
            ):
                on_confirm()
                st.rerun()
        with cancel_col:
            if st.button(cancel_label, width="stretch", key=f"_cancel_{title}"):
                st.rerun()

    _dialog()


def queue_notice(scope: str, level: NoticeLevel, message: str) -> None:
    """Queue a message to show on the next run, after an ``st.rerun()``.

    A message rendered just before a rerun is cleared before the user sees
    it. Queue it instead, and call ``show_queued_notices`` with the same
    scope where it should appear.

    Parameters
    ----------
    scope : str
        Where the message belongs, e.g. ``"prep_survey"`` for one Prep tab.
    level : {"success", "warning", "error", "toast"}
        The Streamlit callout used to render the message, or "toast" for a
        transient ``st.toast``.
    message : str
        The message text (Markdown).
    """
    import streamlit as st

    queued = st.session_state.setdefault(_QUEUED_NOTICES_KEY, {})
    queued.setdefault(scope, []).append(Notice(level, message))


def show_queued_notices(scope: str) -> bool:
    """Render and clear the messages queued for a scope, in queue order.

    Returns True if any message was shown.
    """
    import streamlit as st

    queued = st.session_state.get(_QUEUED_NOTICES_KEY, {})
    notices = queued.pop(scope, [])
    for notice in notices:
        getattr(st, notice.level)(notice.message)
    return bool(notices)


# Serializes updates to pandas' process-wide Styler limit across sessions.
_STYLER_LIMIT_LOCK = threading.Lock()


def ensure_styler_limit(cells: int) -> None:
    """Raise pandas' ``styler.render.max_elements`` to at least `cells`.

    Streamlit refuses to render a Styler with more cells than this
    process-wide option, and every session shares it. The limit is only
    ever raised, never lowered or restored, so one session can't cut it
    below what another's render needs. Use this instead of
    ``pd.set_option("styler.render.max_elements", ...)``.
    """
    import pandas as pd

    with _STYLER_LIMIT_LOCK:
        if pd.get_option("styler.render.max_elements") < cells:
            pd.set_option("styler.render.max_elements", cells)


def styled_dataframe(styler: "Styler", **dataframe_kwargs: Any) -> Any:
    """Render a pandas ``Styler`` with ``st.dataframe``, whatever its size.

    Raises the Styler cell limit to fit the table first (see
    `ensure_styler_limit`). Returns what ``st.dataframe`` returns.
    """
    import streamlit as st

    ensure_styler_limit(styler.data.size)
    return st.dataframe(styler, **dataframe_kwargs)


def row_styler(df: "pl.DataFrame", row_style: Callable[[Any], list[str]]) -> "Styler":
    """Return a pandas ``Styler`` for `df` that styles each row with `row_style`.

    ``st.dataframe`` shows a Styler's formatted text, and pandas' defaults
    would change the values: integers with missing values become floats,
    floats are padded or rounded to six decimals, and missing values read
    "nan". Here nullable types are kept and each value is shown as its plain
    text ("None" if missing), so styling changes only the colours.

    `row_style` receives each row as a pandas Series; missing values are
    ``pd.NA``, which must not be used in a boolean test.
    """
    pandas_df = df.to_pandas(use_pyarrow_extension_array=True)
    return pandas_df.style.apply(row_style, axis=1).format(str, na_rep="None")
