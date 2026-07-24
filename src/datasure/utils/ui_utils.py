"""Shared UI helpers for consistent page structure across DataSure views.

These helpers centralize the repeated Streamlit patterns (page headers,
section headers, destructive-action confirmations, and metric rows) so every
view renders them identically. The module is intentionally UI-only: it holds
no data-access logic and is safe to import from any view.

Streamlit is imported inside each helper rather than at module level. Views
are page scripts whose tests swap ``sys.modules["streamlit"]`` for a mock at
import time; resolving the module per call ensures these helpers honor that
swap regardless of the order in which the module was first imported.
"""

from collections.abc import Callable, Sequence


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
