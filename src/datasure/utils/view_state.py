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
templates (``without_view_state``), along with the view values older versions
saved with check settings that have not moved into view state yet.
Pagination, search boxes and dialog inputs are never bound, so they start
fresh in a new session; search boxes use ``ViewState.keep`` to survive
switching checks within a session.
"""

import json
import logging
from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Literal

logger = logging.getLogger(__name__)

VIEW_STATE_KEY = "view_state"

# Settings keys older versions saved view values under, by check settings
# section. Opening a check moves them into view state (``adopt_legacy``);
# until then ``without_view_state`` leaves them out as well. ``view_factory``
# checks each check's legacy keys against this table.
LEGACY_VIEW_KEYS: dict[str, frozenset[str]] = {
    "backchecks": frozenset(
        {
            "time_period_backchecker_productivity",
            "weekstartday_backchecker_productivity",
            "enum_bcer_stats_view",
        }
    ),
    "descriptive_stats": frozenset(
        {"col_to_plot", "n_bins", "col_to_analyse", "top_n", "view", "agg_option"}
    ),
    "enumerators": frozenset(
        {
            "time_period",
            "statscols",
            "stats",
            "period_overtime",
            "weekstartday",
            "stat",
            "statscol",
        }
    ),
    "missing": frozenset(
        {
            "mv_threshold",
            "select_date_col",
            "group_by_col",
            "compare_col",
            "all_cols",
            "null_cols_sel",
        }
    ),
    "outliers": frozenset({"selected_col", "constraint_display_cols"}),
    "progress": frozenset({"time_period", "display_cols"}),
    "summary": frozenset({"progress_by_col", "progress_time_period"}),
}
# Duplicates saved each table's extra columns as "<table>_display_cols".
_LEGACY_VIEW_SUFFIXES = {"duplicates": "_display_cols"}


def _is_legacy_view_key(section: str, key: str) -> bool:
    suffix = _LEGACY_VIEW_SUFFIXES.get(section)
    return key in LEGACY_VIEW_KEYS.get(section, ()) or (
        suffix is not None and key.endswith(suffix)
    )


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

    View values an older version saved with check settings
    (``LEGACY_VIEW_KEYS``) are left out too, so a project exported before
    each check was opened does not carry them.

    Used wherever settings leave the user's machine or arrive from another
    project: configuration exports and applied configurations (templates).
    """
    return {
        section: (
            {
                key: value
                for key, value in values.items()
                if not _is_legacy_view_key(section, key)
            }
            if isinstance(values, dict)
            else values
        )
        for section, values in settings.items()
        if section != VIEW_STATE_KEY
    }


def remembered(settings_file: str | Path, name: str) -> str | None:
    """Return a value remembered under ``name`` in the view state, if any."""
    value = _view_state(read_settings(settings_file)).get(name)
    return value if isinstance(value, str) else None


def remember(settings_file: str | Path, name: str, value: str) -> None:
    """Remember a value under ``name``; the file is only written on change."""
    settings = read_settings(settings_file)
    view_state = settings.setdefault(VIEW_STATE_KEY, {})
    if view_state.get(name) == value:
        return
    view_state[name] = value
    write_settings(settings_file, settings)


def forget_remembered(settings_file: str | Path, name: str) -> None:
    """Forget the value remembered under ``name``, if there is one."""
    settings = read_settings(settings_file)
    view_state = _view_state(settings)
    if name not in view_state:
        return
    del view_state[name]
    write_settings(settings_file, settings)


def saved_selection(settings_file: str | Path) -> str | None:
    """Return the last selected item (check, dataset or page), if any."""
    return remembered(settings_file, "selected")


def save_selection(settings_file: str | Path, slug: str) -> None:
    """Remember the selected item; the file is only written when it changes.

    Validation is the resolver's job: a stale saved slug is ignored there.
    """
    remember(settings_file, "selected", slug)


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

    def adopt_legacy(self, section: str, keys: Mapping[str, str]) -> None:
        """Move view values an older version saved with check settings.

        Older versions saved some filters and selections under the check's
        own settings section. Each legacy value found there moves into this
        scope (unless the scope already has one) and is removed from the
        section, so it loads as before but is now personal view state: left
        out of exports and cleared by "Reset filters". The file is only
        written when something moves.

        Parameters
        ----------
        section : str
            The check's settings section, such as ``"missing"``.
        keys : Mapping[str, str]
            Legacy settings key by widget key.
        """
        settings = read_settings(self.settings_file)
        legacy = settings.get(section)
        if not isinstance(legacy, dict) or not any(
            legacy_key in legacy for legacy_key in keys.values()
        ):
            return
        view_state = settings.get(VIEW_STATE_KEY)
        if not isinstance(view_state, dict):
            view_state = settings[VIEW_STATE_KEY] = {}
        saved = view_state.setdefault("scopes", {}).setdefault(self.scope, {})
        for widget_key, legacy_key in keys.items():
            if legacy_key not in legacy:
                continue
            value = legacy.pop(legacy_key)
            if value is not None:
                saved.setdefault(widget_key, value)
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
        kept. A saved or session value that is no longer in ``options`` falls
        back to the widget default and is removed; for a multiselect
        (``multi=True``) only the values that still exist are kept.

        Bind only filter, selection and sort widgets. Pagination, search
        boxes and dialog inputs must start fresh in a new session, so never
        bind them; keep search boxes for the session with ``keep``.

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

        if key in st.session_state:
            # None is a cleared widget, which the widget's default must not
            # replace.
            current = st.session_state[key]
            if current is not None:
                value = self._restore(key, current, options, multi)
                if value is None:
                    self.forget(key)
                    del st.session_state[key]
                elif value != current:
                    st.session_state[key] = value
        show_session_value(key)
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

    def keep(
        self,
        key: str,
        *,
        on_change: Callable[..., None] | None = None,
        args: tuple = (),
    ) -> dict[str, Any]:
        """Keep a widget's value for this session only, without saving it.

        For search boxes: the search survives switching to another check and
        back, but a new session starts with an empty box. The value is kept
        per page and scope, so another check page does not inherit it.
        Spread the result into the widget call, like ``bind``.

        Parameters
        ----------
        key : str
            The widget key.
        on_change : Callable | None
            The widget's own callback, run after keeping the value.
        args : tuple
            Arguments for ``on_change``.

        Returns
        -------
        dict
            ``key`` and ``on_change`` keyword arguments for the widget.
        """
        import streamlit as st

        kept = f"_kept__{self.settings_file}__{self.scope}__{key}"
        if key not in st.session_state and kept in st.session_state:
            st.session_state[key] = st.session_state[kept]
        show_session_value(key)

        def _keep() -> None:
            st.session_state[kept] = st.session_state.get(key)
            if on_change is not None:
                on_change(*args)

        return {"key": key, "on_change": _keep}

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


def show_session_value(key: str) -> None:
    """Make a widget display the value session state still holds for it.

    Switching to another check and straight back can interrupt the run that
    would have cleared the widget's value, so the value survives in session
    state and still filters the output. The redrawn widget would show its
    default, because Streamlit only sends a value to the browser when code
    sets it. Setting it again here, before the widget is drawn, shows it.
    """
    import streamlit as st

    if key in st.session_state:
        value = st.session_state[key]
        st.session_state[key] = value


def view_factory(
    scope: str, legacy: tuple[str, Mapping[str, str]] | None = None
) -> Callable[[str | Path], ViewState]:
    """Return a function that opens ``scope``'s view state in a settings file.

    Each check module builds its own once, from its catalogue slug::

        check_view = view_factory(VIEW_SCOPE)
        st.selectbox("Sort by", options, **check_view(settings_file).bind(...))

    Parameters
    ----------
    scope : str
        The check's catalogue slug.
    legacy : tuple[str, Mapping[str, str]] | None
        For a check whose view values an older version saved with its
        settings: the settings section and the legacy key by widget key.
        Opening the view moves any found there (``ViewState.adopt_legacy``).
    """
    if legacy is not None:
        section, keys = legacy
        unlisted = [
            key for key in keys.values() if not _is_legacy_view_key(section, key)
        ]
        if unlisted:
            raise ValueError(
                f"Add {unlisted} to LEGACY_VIEW_KEYS[{section!r}] so exports "
                "leave them out."
            )

    def open_view(settings_file: str | Path) -> ViewState:
        view = ViewState(settings_file, scope)
        if legacy is not None:
            view.adopt_legacy(*legacy)
        return view

    return open_view


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


@contextmanager
def reset_filters_beside(
    view: ViewState, *, vertical_alignment: Literal["top", "center"] = "top"
) -> Iterator[None]:
    """Draw the block's elements with a "Reset filters" action beside them.

    Wrap a check's settings section (or its title, when it has none) so the
    action sits on the same row::

        with reset_filters_beside(check_view(setting_file)):
            settings = progress_report_settings(...)

    Parameters
    ----------
    view : ViewState
        The scope the action clears.
    vertical_alignment : {"top", "center"}
        Use "top" beside an expander, so the action stays level with its
        header when it opens, and "center" beside a title.

    In the demo, the block's "Learn More" guidance draws above the row.
    """
    import streamlit as st

    from datasure.utils.onboarding_utils import demo_guidance_above

    with (
        demo_guidance_above(),
        st.container(horizontal=True, vertical_alignment=vertical_alignment),
    ):
        yield
        reset_filters_button(view, key=view.settings_file.stem)
