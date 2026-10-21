"""Streamlit side of the shared navigation (see ``utils/navigation.py``).

A page uses it in four steps:

1. ``resolve_selection`` reads the URL query parameter and the remembered
   selection and decides what is selected, before anything is drawn.
2. ``render_selected`` draws the selected item: a standard empty state when
   it is not ready, and its content through ``run_guarded``, which turns an
   exception into an error state instead of stopping the page.
3. ``draw_nav`` draws the controls: a segmented control for the groups and
   pills for the selected group's items, or one row of pills for a flat list.
   Draw it into a container created above the content, after the content, so
   an item that failed while rendering is already marked.
4. ``select_nav_item`` changes the selection from code, for example from a
   button's ``on_click``. The controls use it too.

All state lives in ``st.session_state`` under keys built from the page's
``key``. Opening another project keeps session state, so build ``key`` with
``project_nav_key``. Streamlit is imported inside each function, as in
``ui_utils``.
"""

import logging
import traceback
from collections.abc import Callable, Sequence

from datasure.utils.navigation import (
    CheckStatus,
    NavItem,
    NavState,
    StatusResult,
    group_selection,
    nav_label,
    resolve_nav,
    with_errors,
)

logger = logging.getLogger(__name__)

# Project-level view state file (under the project's settings folder) and
# the name it records the page_name_id of the check page last viewed under,
# so Corrections opens on the check page the user was reviewing, also in a
# new session.
PROJECT_VIEW_FILE = "project_view_settings.json"
LAST_CHECK_PAGE = "last_check_page"


def project_nav_key(name: str, project_id: str) -> str:
    """Return a page's navigation key for one project.

    Opening another project keeps session state, so a key without the
    project would carry one project's selection and errors into another.
    """
    return f"{name}__{project_id}"


def _selected_key(key: str) -> str:
    return f"{key}__selected"


def _group_key(key: str) -> str:
    return f"{key}__group"


def _item_key(key: str) -> str:
    return f"{key}__item"


def _last_by_group_key(key: str) -> str:
    return f"{key}__last_by_group"


def _errors_key(key: str) -> str:
    return f"{key}__errors"


def render_errors(key: str) -> dict[str, str]:
    """Return the items that raised the last time they rendered, with why."""
    import streamlit as st

    return st.session_state.setdefault(_errors_key(key), {})


def select_nav_item(key: str, param: str, slug: str) -> None:
    """Select an item and show it in the URL.

    Safe to call from a widget callback; the next run opens the item.

    Parameters
    ----------
    key : str
        The page's navigation key.
    param : str
        The page's URL query parameter.
    slug : str
        The item to select. An unknown slug falls back to the default on the
        next run.
    """
    import streamlit as st

    st.session_state[_selected_key(key)] = slug
    st.query_params[param] = slug


def resolve_selection(
    items: Sequence[NavItem],
    *,
    key: str,
    param: str,
    default: str | None = None,
    saved: str | None = None,
) -> NavState:
    """Decide which item is selected on this run.

    Precedence: a valid URL value, then the selection remembered in this
    session (or ``saved`` when there is none), then ``default``. The URL is
    updated to show the selected item.

    Parameters
    ----------
    items : Sequence[NavItem]
        Every item with its status, in display order.
    key : str
        The page's navigation key; must be unique to the page.
    param : str
        The page's URL query parameter, such as ``check``.
    default : str | None
        The item to select when nothing else is valid.
    saved : str | None
        A selection saved between sessions.

    Returns
    -------
    NavState
        The selection and the items.
    """
    import streamlit as st

    url = st.query_params.get(param)
    remembered = st.session_state.get(_selected_key(key))
    # A remembered selection the items no longer offer gives way to the saved
    # one, rather than to the default.
    slugs = {item.slug for item in items}
    state = resolve_nav(
        items,
        url=url,
        saved=remembered if remembered in slugs else saved,
        default=default,
    )
    st.session_state[_selected_key(key)] = state.selected
    if state.group:
        st.session_state.setdefault(_last_by_group_key(key), {})[state.group] = (
            state.selected
        )
    if url != state.selected:
        st.query_params[param] = state.selected
    return state


def _on_group_change(key: str, param: str, items: Sequence[NavItem]) -> None:
    import streamlit as st

    group = st.session_state.get(_group_key(key))
    if group:
        remembered = st.session_state.get(_last_by_group_key(key))
        select_nav_item(key, param, group_selection(items, group, remembered))


def _on_item_change(key: str, param: str) -> None:
    import streamlit as st

    slug = st.session_state.get(_item_key(key))
    if slug:
        select_nav_item(key, param, slug)


def draw_nav(state: NavState, *, key: str, param: str, label: str) -> None:
    """Draw the navigation controls for a resolved selection.

    Grouped items get a full-width segmented control for the group, a
    divider, and pills for the group's items; a flat list gets one row of
    pills. Items that are not
    ready, or that raised when they last rendered, are muted with a text and
    icon marker.

    Parameters
    ----------
    state : NavState
        The selection from ``resolve_selection``.
    key : str
        The page's navigation key.
    param : str
        The page's URL query parameter.
    label : str
        What an item is, such as "Check" or "Dataset"; used as the
        (hidden) widget label.
    """
    import streamlit as st

    items = with_errors(state.items, render_errors(key))
    by_slug = {item.slug: item for item in items}

    if state.groups:
        # The controls show the resolved selection, whatever set it.
        st.session_state[_group_key(key)] = state.group
        st.segmented_control(
            f"{label} group",
            state.groups,
            key=_group_key(key),
            required=True,
            label_visibility="collapsed",
            on_change=_on_group_change,
            args=(key, param, items),
            width="stretch",
        )
        # Separates the groups from the selected group's items below.
        st.divider()
        options = [item.slug for item in items if item.group == state.group]
    else:
        options = [item.slug for item in items]

    st.session_state[_item_key(key)] = state.selected
    st.pills(
        label,
        options,
        key=_item_key(key),
        required=True,
        format_func=lambda slug: nav_label(by_slug[slug]),
        label_visibility="collapsed",
        on_change=_on_item_change,
        args=(key, param),
        wrap=True,
    )


def guarded_status(slug: str, status: Callable[[], StatusResult]) -> StatusResult:
    """Compute an item's status; an exception becomes the error status.

    The navigation shows the error and the item's page explains it, so one
    failing status does not stop the page.
    """
    try:
        return status()
    # UI boundary: one item's status must not stop the page. The error is
    # shown by render_empty_state and the navigation marker (deferred display,
    # see CONTRIBUTING "Error Handling Conventions").
    except Exception as exc:
        logger.exception("Could not compute the status of %r", slug)
        return StatusResult(CheckStatus.ERROR, f"{type(exc).__name__}: {exc}")


# What a not-set-up item's empty state tells the user to do by default.
SET_UP_BELOW = "Set it up below."


def render_empty_state(item: NavItem, setup_hint: str = SET_UP_BELOW) -> None:
    """Explain why an item that is not ready shows no results.

    ``setup_hint`` ends a not-set-up message; it must say truthfully where
    the setup happens.
    """
    import streamlit as st

    if item.status is CheckStatus.NOT_SET_UP:
        st.info(
            f"**{item.label}** is not set up. {item.reason} {setup_hint}",
            icon=":material/build:",
        )
    elif item.status is CheckStatus.NOT_APPLICABLE:
        st.info(
            f"**{item.label}** does not apply to this data. {item.reason}",
            icon=":material/do_not_disturb_on:",
        )
    elif item.status is CheckStatus.ERROR:
        st.error(
            f"**{item.label}** could not check whether it is ready. {item.reason}",
            icon=":material/error:",
        )


def run_guarded(key: str, item: NavItem, render: Callable[[], None]) -> bool:
    """Run an item's render function, turning an exception into an error state.

    The error is remembered so the navigation marks the item until it renders
    without one. Streamlit's ``st.stop()`` and ``st.rerun()`` are not
    ``Exception`` subclasses, so they pass through.

    Returns
    -------
    bool
        True when the item rendered without an exception.
    """
    import streamlit as st

    errors = render_errors(key)
    try:
        render()
    except Exception as exc:  # UI boundary: one failing item must not stop the page
        logger.exception("%s failed to render", item.label)
        errors[item.slug] = f"{type(exc).__name__}: {exc}"
        st.error(
            f"**{item.label}** failed: {type(exc).__name__}: {exc}. The rest of "
            "the page still works. If this keeps happening, report it with the "
            "details below.",
            icon=":material/error:",
        )
        with st.expander("Error details"):
            st.code(traceback.format_exc(), language="text")
        return False
    errors.pop(item.slug, None)
    return True


def render_selected(
    key: str,
    item: NavItem,
    render: Callable[[], None],
    setup: Callable[[], None] | None = None,
    settings: Callable[[], None] | None = None,
    setup_hint: str = SET_UP_BELOW,
) -> None:
    """Draw the selected item according to its status.

    - ready: ``render``.
    - not set up: the empty state ending with ``setup_hint``, then ``setup``
      (default: ``render``, for items whose content starts with their
      settings).
    - not applicable: the empty state, then ``settings`` when the item has a
      settings section, so it stays reachable.
    - error (its status raised): the error, then ``render`` anyway.

    ``render``, ``setup`` and ``settings`` run through ``run_guarded``.
    """
    if item.status is CheckStatus.READY:
        run_guarded(key, item, render)
        return
    render_empty_state(item, setup_hint)
    if item.status is CheckStatus.NOT_SET_UP:
        run_guarded(key, item, setup or render)
    elif item.status is CheckStatus.NOT_APPLICABLE:
        if settings is not None:
            run_guarded(key, item, settings)
    elif item.status is CheckStatus.ERROR:
        run_guarded(key, item, render)
