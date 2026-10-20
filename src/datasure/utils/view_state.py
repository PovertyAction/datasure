"""Saved view state: personal view settings remembered between sessions.

Only the selected check (or dataset, or page) renders, and Streamlit forgets
the values of widgets that are not drawn. View state keeps the last selection
and each scope's filter, selection and sort widget values in a ``view_state``
section of a settings JSON file, so they survive switching and new sessions::

    {
        "duplicates": {...},  # check settings, untouched
        "view_state": {
            "selected": "duplicates",  # last selected item
            "scopes": {"duplicates": {"iddup_survey_sort": "ID"}},
        },
    }

A scope is one check (its catalogue slug) or one Prepare Data / Corrections
item. Any settings file works, so other pages can keep their own.

View state is personal: it is left out of project configuration exports and
templates (``without_view_state``). Pagination, search boxes and dialog
inputs are never bound, so they start fresh.
"""

import json
import logging
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

VIEW_STATE_KEY = "view_state"


def read_settings(settings_file: str | Path) -> dict:
    """Read a settings JSON file; a missing file reads as ``{}``.

    The one reader for page settings files outside Streamlit code (view
    state and project configuration export/apply).
    """
    path = Path(settings_file)
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def write_settings(settings_file: str | Path, settings: dict) -> None:
    """Write a settings JSON file, creating its folder if needed."""
    path = Path(settings_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(settings, f)


def _view_state(settings: dict) -> dict:
    view_state = settings.get(VIEW_STATE_KEY)
    return view_state if isinstance(view_state, dict) else {}


def without_view_state(settings: dict) -> dict:
    """Return settings without the personal ``view_state`` section.

    Used wherever settings leave the user's machine or arrive from another
    project: configuration exports and applied configurations (templates).
    """
    return {key: value for key, value in settings.items() if key != VIEW_STATE_KEY}


def saved_selection(settings_file: str | Path) -> str | None:
    """Return the last selected item (check, dataset or page), if any."""
    selected = _view_state(read_settings(settings_file)).get("selected")
    return selected if isinstance(selected, str) else None


def save_selection(settings_file: str | Path, slug: str) -> None:
    """Remember the selected item; the file is only written when it changes.

    Validation is the resolver's job: a stale saved slug is ignored there.
    """
    settings = read_settings(settings_file)
    view_state = settings.setdefault(VIEW_STATE_KEY, {})
    if view_state.get("selected") == slug:
        return
    view_state["selected"] = slug
    write_settings(settings_file, settings)


class ViewState:
    """The saved widget values of one scope in a settings file.

    Parameters
    ----------
    settings_file : str | Path
        The JSON file holding the ``view_state`` section; created on first
        save.
    scope : str
        The check slug, dataset or page the values belong to.
    """

    def __init__(self, settings_file: str | Path, scope: str) -> None:
        self.settings_file = Path(settings_file)
        self.scope = scope

    def values(self) -> dict[str, Any]:
        """Return the scope's saved values, keyed by widget key."""
        scopes = _view_state(read_settings(self.settings_file)).get("scopes", {})
        return dict(scopes.get(self.scope, {}))

    def save(self, key: str, value: Any) -> None:
        """Save one widget value; other settings in the file are kept."""
        settings = read_settings(self.settings_file)
        view_state = settings.setdefault(VIEW_STATE_KEY, {})
        view_state.setdefault("scopes", {}).setdefault(self.scope, {})[key] = value
        write_settings(self.settings_file, settings)

    def forget(self, *keys: str) -> None:
        """Remove saved values, for example ones that no longer match the data."""
        settings = read_settings(self.settings_file)
        saved = _view_state(settings).get("scopes", {}).get(self.scope)
        if not saved or not any(key in saved for key in keys):
            return
        for key in keys:
            saved.pop(key, None)
        write_settings(self.settings_file, settings)

    def reset(self) -> list[str]:
        """Clear every saved value of this scope, and only this scope.

        Returns
        -------
        list[str]
            The widget keys that had saved values.
        """
        keys = list(self.values())
        if keys:
            self.forget(*keys)
        return keys

    # --- Streamlit side; Streamlit is imported inside each method. --- #

    def _restore(
        self, key: str, saved: Any, options: Sequence | None, multi: bool
    ) -> Any:
        """Return the saved value still valid for ``options``, or None."""
        if options is None:
            return saved
        allowed = list(options)
        if not multi:
            return saved if saved in allowed else None
        if not isinstance(saved, list):
            return None
        kept = [value for value in saved if value in allowed]
        if saved and not kept:
            return None
        if kept != saved:
            self.save(key, kept)
        return kept

    def bind(
        self,
        key: str,
        *,
        options: Sequence | None = None,
        multi: bool = False,
        on_change: Callable[..., None] | None = None,
        args: tuple = (),
        **initial: Any,
    ) -> dict[str, Any]:
        """Restore a widget's saved value and save it when the user changes it.

        Spread the result into the widget call. Pass the widget's own
        ``index``/``default``/``value`` through ``initial`` rather than to the
        widget, so it is only used when session state holds no value::

            widget = view.bind("color_by", options=cols, index=1)
            st.selectbox("Color by", cols, **widget)

        A value already in session state (set earlier in this session) is
        kept. A saved value that is no longer in ``options`` falls back to the
        widget default and is removed; for a multiselect (``multi=True``) only
        the values that still exist are kept.

        Bind only filter, selection and sort widgets. Pagination, search
        boxes and dialog inputs must start fresh, so never bind them.

        Parameters
        ----------
        key : str
            The widget key.
        options : Sequence | None
            The widget's current options, to drop stale values. None accepts
            any saved value (toggles, numbers).
        multi : bool
            Whether the value is a list of options.
        on_change : Callable | None
            The widget's own callback, run after saving.
        args : tuple
            Arguments for ``on_change``.
        **initial
            The widget's default argument, such as ``index=1``. Left out when
            session state already holds the value, which avoids Streamlit's
            warning about a widget with both a default and a state value.

        Returns
        -------
        dict
            ``key``, ``on_change`` and, when used, ``initial`` keyword
            arguments for the widget.
        """
        import streamlit as st

        saved_values = self.values()
        if key not in st.session_state and key in saved_values:
            value = self._restore(key, saved_values[key], options, multi)
            if value is None:
                self.forget(key)
            else:
                st.session_state[key] = value

        def _save() -> None:
            self._save_widget(key)
            if on_change is not None:
                on_change(*args)

        kwargs = {} if key in st.session_state else dict(initial)
        return {**kwargs, "key": key, "on_change": _save}

    def _save_widget(self, key: str) -> None:
        import streamlit as st

        value = st.session_state.get(key)
        if value is None:
            self.forget(key)
            return
        if isinstance(value, tuple):
            value = list(value)
        try:
            json.dumps(value)
        except TypeError:
            logger.warning("View state %r: %r cannot be saved", key, value)
            return
        self.save(key, value)

    def reset_widgets(self) -> None:
        """Clear this scope's saved values and their widgets in this session.

        Call it from a button's ``on_click`` so the widgets are drawn with
        their defaults on the next run.
        """
        import streamlit as st

        for key in self.reset():
            st.session_state.pop(key, None)


def bind_widget(view: ViewState | None, key: str, **kwargs: Any) -> dict[str, Any]:
    """Bind a widget to ``view``, or only key it when there is no view.

    For helpers that are also used outside a page with a settings file.
    Takes the same keyword arguments as ``ViewState.bind``.
    """
    if view is None:
        kwargs.pop("options", None)
        kwargs.pop("multi", None)
        return {"key": key, **kwargs}
    return view.bind(key, **kwargs)


def reset_filters_button(view: ViewState, *, key: str) -> None:
    """Draw a small "Reset filters" action that clears one scope's view state.

    Parameters
    ----------
    view : ViewState
        The scope to clear.
    key : str
        A widget key prefix unique to the page.
    """
    import streamlit as st

    st.button(
        "Reset filters",
        key=f"{key}__reset_{view.scope}",
        type="tertiary",
        icon=":material/restart_alt:",
        help="Clear the filters, selections and sort order remembered here.",
        on_click=view.reset_widgets,
    )
