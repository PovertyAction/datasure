"""Tests for saved view state (``utils/view_state.py``)."""

import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from datasure.utils.view_state import (
    ViewState,
    bind_widget,
    forget_remembered,
    remember,
    remembered,
    reset_filters_beside,
    save_selection,
    saved_selection,
    without_view_state,
)


@pytest.fixture
def settings_file(tmp_path):
    path = tmp_path / "page_hfcs_settings.json"
    path.write_text(json.dumps({"duplicates": {"survey_id": "hhid"}}))
    return path


def _file(path) -> dict:
    return json.loads(path.read_text())


class TestScopeValues:
    def test_saved_values_load_back_in_a_new_view(self, settings_file):
        ViewState(settings_file, "duplicates").save("sort", "ID")

        assert ViewState(settings_file, "duplicates").values() == {"sort": "ID"}

    def test_saving_keeps_the_check_settings(self, settings_file):
        ViewState(settings_file, "duplicates").save("sort", "ID")

        assert _file(settings_file)["duplicates"] == {"survey_id": "hhid"}

    def test_works_without_a_settings_file(self, tmp_path):
        view = ViewState(tmp_path / "settings" / "prep_view_settings.json", "survey")

        assert view.values() == {}
        view.save("filter", ["a"])
        assert view.values() == {"filter": ["a"]}


class TestSelection:
    def test_selection_round_trips_and_keeps_scopes(self, settings_file):
        ViewState(settings_file, "gps").save("color_by", "team")

        save_selection(settings_file, "gps")

        assert saved_selection(settings_file) == "gps"
        assert ViewState(settings_file, "gps").values() == {"color_by": "team"}

    def test_no_saved_selection(self, tmp_path):
        assert saved_selection(tmp_path / "missing.json") is None


class TestRemembered:
    def test_a_remembered_value_round_trips_and_can_be_forgotten(self, tmp_path):
        path = tmp_path / "project_view_settings.json"

        remember(path, "last_check_page", "hfcs")
        assert remembered(path, "last_check_page") == "hfcs"

        forget_remembered(path, "last_check_page")
        assert remembered(path, "last_check_page") is None

    def test_the_file_is_only_written_when_the_value_changes(self, settings_file):
        remember(settings_file, "last_check_page", "hfcs")
        written = settings_file.stat().st_mtime_ns
        settings_file.chmod(0o444)
        try:
            # Read-only: a write here would raise.
            remember(settings_file, "last_check_page", "hfcs")
            forget_remembered(settings_file, "other")
        finally:
            settings_file.chmod(0o644)

        assert settings_file.stat().st_mtime_ns == written


class TestAdoptLegacy:
    """View values an older version saved with check settings move over."""

    def test_legacy_values_move_into_the_scope(self, settings_file):
        settings_file.write_text(
            json.dumps({"duplicates": {"survey_id": "hhid", "old_sort": "ID"}})
        )

        ViewState(settings_file, "duplicates").adopt_legacy(
            "duplicates", {"sort_widget": "old_sort"}
        )

        assert ViewState(settings_file, "duplicates").values() == {"sort_widget": "ID"}
        assert _file(settings_file)["duplicates"] == {"survey_id": "hhid"}

    def test_a_value_already_in_the_scope_wins(self, settings_file):
        view = ViewState(settings_file, "duplicates")
        view.save("sort_widget", "KEY")
        settings = _file(settings_file)
        settings["duplicates"]["old_sort"] = "ID"
        settings_file.write_text(json.dumps(settings))

        view.adopt_legacy("duplicates", {"sort_widget": "old_sort"})

        assert view.values() == {"sort_widget": "KEY"}
        assert "old_sort" not in _file(settings_file)["duplicates"]

    def test_nothing_to_move_leaves_the_file_alone(self, settings_file):
        before = settings_file.read_text()

        ViewState(settings_file, "duplicates").adopt_legacy(
            "duplicates", {"sort_widget": "old_sort"}
        )

        assert settings_file.read_text() == before


class TestWithoutViewState:
    def test_drops_only_the_view_state_section(self, settings_file):
        save_selection(settings_file, "gps")

        assert without_view_state(_file(settings_file)) == {
            "duplicates": {"survey_id": "hhid"}
        }


class TestReset:
    def test_reset_clears_only_its_own_scope(self, settings_file):
        ViewState(settings_file, "duplicates").save("sort", "ID")
        ViewState(settings_file, "gps").save("color_by", "team")

        cleared = ViewState(settings_file, "duplicates").reset()

        assert cleared == ["sort"]
        assert ViewState(settings_file, "duplicates").values() == {}
        assert ViewState(settings_file, "gps").values() == {"color_by": "team"}
        # Check settings are not view state and stay.
        assert _file(settings_file)["duplicates"] == {"survey_id": "hhid"}


class TestResetFiltersBeside:
    @pytest.fixture
    def st(self, monkeypatch):
        st = MagicMock(session_state={})
        monkeypatch.setitem(sys.modules, "streamlit", st)
        return st

    def test_the_action_follows_the_block_in_one_row(self, settings_file, st):
        with reset_filters_beside(ViewState(settings_file, "duplicates")):
            st.expander("settings")

        st.container.assert_called_once_with(horizontal=True, vertical_alignment="top")
        names = [name for name, *_ in st.mock_calls if name in ("expander", "button")]
        assert names == ["expander", "button"]
        assert st.button.call_args.args == ("Reset filters",)

    def test_the_action_clears_only_its_own_scope(self, settings_file, st):
        ViewState(settings_file, "duplicates").save("iddup_survey_sort", "KEY")
        ViewState(settings_file, "gps").save("gps_color_by", "team")
        st.session_state["iddup_survey_sort"] = "KEY"

        with reset_filters_beside(ViewState(settings_file, "duplicates")):
            pass
        st.button.call_args.kwargs["on_click"]()

        assert ViewState(settings_file, "duplicates").values() == {}
        assert "iddup_survey_sort" not in st.session_state
        assert ViewState(settings_file, "gps").values() == {"gps_color_by": "team"}

    def test_keys_differ_between_check_pages(self, tmp_path, st):
        for page in ("page_a", "page_b"):
            with reset_filters_beside(ViewState(tmp_path / f"{page}.json", "gps")):
                pass

        keys = [call.kwargs["key"] for call in st.button.call_args_list]
        assert len(set(keys)) == 2


@pytest.fixture
def fake_st(monkeypatch):
    """A stand-in for Streamlit holding only session state."""
    st = SimpleNamespace(session_state={})
    monkeypatch.setitem(sys.modules, "streamlit", st)
    return st


def _change(st, widget: dict, value) -> None:
    """Change a bound widget the way Streamlit does: state, then on_change."""
    st.session_state[widget["key"]] = value
    widget["on_change"]()


class TestBind:
    def test_a_changed_value_is_restored_in_a_new_session(self, settings_file, fake_st):
        view = ViewState(settings_file, "gps")
        widget = view.bind("gps_color_by", options=["team", "enumerator"])
        _change(fake_st, widget, "enumerator")

        fake_st.session_state.clear()  # new session
        ViewState(settings_file, "gps").bind(
            "gps_color_by", options=["team", "enumerator"]
        )

        assert fake_st.session_state["gps_color_by"] == "enumerator"

    def test_a_value_set_in_this_session_is_not_overwritten(
        self, settings_file, fake_st
    ):
        view = ViewState(settings_file, "gps")
        view.save("gps_color_by", "team")
        fake_st.session_state["gps_color_by"] = "enumerator"

        view.bind("gps_color_by", options=["team", "enumerator"])

        assert fake_st.session_state["gps_color_by"] == "enumerator"

    def test_nothing_saved_leaves_the_widget_default(self, settings_file, fake_st):
        widget = ViewState(settings_file, "gps").bind("gps_color_by")

        assert widget["key"] == "gps_color_by"
        assert "gps_color_by" not in fake_st.session_state

    def test_a_stale_value_falls_back_to_default_and_is_removed(
        self, settings_file, fake_st
    ):
        view = ViewState(settings_file, "enumerator")
        view.save("enum_select", "Removed Enumerator")

        view.bind("enum_select", options=["Ama", "Kofi"])

        assert "enum_select" not in fake_st.session_state
        assert view.values() == {}

    def test_a_multiselect_keeps_the_values_that_still_exist(
        self, settings_file, fake_st
    ):
        view = ViewState(settings_file, "backchecks")
        view.save("bc_filter_cols", ["age", "removed_col", "income"])

        view.bind("bc_filter_cols", options=["income", "age"], multi=True)

        assert fake_st.session_state["bc_filter_cols"] == ["age", "income"]
        assert view.values() == {"bc_filter_cols": ["age", "income"]}

    def test_the_widget_default_is_only_used_without_a_state_value(
        self, settings_file, fake_st
    ):
        view = ViewState(settings_file, "gps")

        assert view.bind("gps_color_by", index=1)["index"] == 1

        view.save("gps_color_by", "team")
        assert "index" not in view.bind("gps_color_by", index=1)

    def test_bind_without_a_view_only_keys_the_widget(self, fake_st):
        assert bind_widget(None, "gps_color_by", options=["a"], index=0) == {
            "key": "gps_color_by",
            "index": 0,
        }

    def test_clearing_a_value_removes_it(self, settings_file, fake_st):
        view = ViewState(settings_file, "gps")
        view.save("gps_config", "gps_1")

        _change(fake_st, view.bind("gps_config"), None)

        assert view.values() == {}

    def test_the_widgets_own_on_change_still_runs(self, settings_file, fake_st):
        calls = []
        view = ViewState(settings_file, "duplicates")
        widget = view.bind("iddup_survey_sort", on_change=calls.append, args=("x",))

        _change(fake_st, widget, "KEY")

        assert calls == ["x"]
        assert view.values() == {"iddup_survey_sort": "KEY"}

    def test_reset_widgets_clears_saved_and_session_values(
        self, settings_file, fake_st
    ):
        view = ViewState(settings_file, "gps")
        _change(fake_st, view.bind("gps_color_by"), "team")
        fake_st.session_state["gps_page"] = 3  # not view state

        view.reset_widgets()

        assert "gps_color_by" not in fake_st.session_state
        assert fake_st.session_state["gps_page"] == 3
        assert view.values() == {}


def _search_app(show: bool) -> None:
    import streamlit as st

    from datasure.utils.view_state import show_session_value

    if show:
        show_session_value("iddup_survey_search")
    st.text_input("Search by ID or KEY", key="iddup_survey_search")


class TestShowSessionValue:
    """A value left in session state is sent to the browser to display.

    Switching checks quickly can interrupt the run that clears a widget's
    value; the value still filters the output, so the redrawn widget must
    show it rather than its empty default.
    """

    @pytest.mark.parametrize("show", [False, True])
    def test_the_widget_displays_the_value_in_use(self, show):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_function(_search_app, args=(show,)).run()
        # The value an interrupted run left behind.
        at.session_state["iddup_survey_search"] = "GJ021"
        at.run()

        box = at.text_input(key="iddup_survey_search")
        assert box.value == "GJ021"  # what filters the output
        displayed = box.proto.value if box.proto.set_value else ""
        assert (displayed == "GJ021") is show

    def test_a_widget_without_a_value_is_left_alone(self, fake_st):
        from datasure.utils.view_state import show_session_value

        show_session_value("iddup_survey_search")

        assert "iddup_survey_search" not in fake_st.session_state


def _kept_search_app(settings_file: str) -> None:
    import streamlit as st

    from datasure.utils.view_state import ViewState

    if st.session_state.get("show_duplicates", True):
        st.text_input(
            "Search by ID or KEY",
            **ViewState(settings_file, "duplicates").keep("iddup_survey_search"),
        )


class TestKeep:
    """A search box keeps its value when you switch checks and come back."""

    def _search(self, settings_file, value):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_function(_kept_search_app, args=(str(settings_file),))
        at.run()
        at.text_input(key="iddup_survey_search").input(value).run()
        return at

    def _switch_away_and_back(self, at):
        at.session_state["show_duplicates"] = False
        at.run()
        assert "iddup_survey_search" not in at.session_state  # Streamlit forgot
        at.session_state["show_duplicates"] = True
        return at.run()

    def test_the_search_survives_switching_checks(self, settings_file):
        at = self._switch_away_and_back(self._search(settings_file, "GJ021"))

        box = at.text_input(key="iddup_survey_search")
        assert box.value == "GJ021"
        assert box.proto.set_value and box.proto.value == "GJ021"  # displayed

    def test_a_cleared_search_stays_cleared(self, settings_file):
        at = self._search(settings_file, "GJ021")
        at.text_input(key="iddup_survey_search").input("").run()

        at = self._switch_away_and_back(at)

        assert at.text_input(key="iddup_survey_search").value == ""

    def test_the_search_is_not_saved_to_disk(self, settings_file):
        self._search(settings_file, "GJ021")

        assert ViewState(settings_file, "duplicates").values() == {}

    def test_another_check_page_does_not_inherit_it(self, tmp_path, fake_st):
        first = ViewState(tmp_path / "page_a.json", "duplicates")
        second = ViewState(tmp_path / "page_b.json", "duplicates")
        widget = first.keep("iddup_survey_search")
        fake_st.session_state["iddup_survey_search"] = "GJ021"
        widget["on_change"]()
        del fake_st.session_state["iddup_survey_search"]  # switched away

        second.keep("iddup_survey_search")

        assert "iddup_survey_search" not in fake_st.session_state

    def test_the_widgets_own_on_change_still_runs(self, settings_file, fake_st):
        calls = []
        widget = ViewState(settings_file, "duplicates").keep(
            "iddup_survey_search", on_change=calls.append, args=("page",)
        )
        fake_st.session_state["iddup_survey_search"] = "GJ021"

        widget["on_change"]()

        assert calls == ["page"]
