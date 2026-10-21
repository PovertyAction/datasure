"""Tests for the Streamlit side of the shared navigation."""

from datasure.utils.nav_ui import project_nav_key


def _nav_app():
    import streamlit as st

    from datasure.utils.nav_ui import project_nav_key, resolve_selection
    from datasure.utils.navigation import NavItem

    # Opening another project goes to another page, which clears the URL.
    st.query_params.clear()
    project = st.session_state["_project"]
    slugs = st.session_state["_slugs"]
    state = resolve_selection(
        [NavItem(slug, slug, ":material/table:") for slug in slugs],
        key=project_nav_key("prep_nav", project),
        param="dataset",
        saved=st.session_state.get("_saved"),
    )
    st.write(f"SELECTED={state.selected}")


def _selected(at) -> str:
    return next(m.value for m in at.markdown if m.value.startswith("SELECTED="))


def _run(at, project, slugs, saved=None):
    at.session_state["_project"] = project
    at.session_state["_slugs"] = slugs
    at.session_state["_saved"] = saved
    return at.run()


class TestProjectNavKey:
    def test_differs_by_project(self):
        assert project_nav_key("prep_nav", "aaa") != project_nav_key("prep_nav", "bbb")


class TestResolveSelectionAcrossProjects:
    def test_another_project_opens_on_its_own_saved_selection(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_function(_nav_app)
        _run(at, "aaa", ["survey", "backcheck"], saved="backcheck")
        assert _selected(at) == "SELECTED=backcheck"

        _run(at, "bbb", ["survey", "backcheck"], saved="survey")

        assert not at.exception
        assert _selected(at) == "SELECTED=survey"

    def test_a_remembered_selection_no_longer_offered_gives_way_to_saved(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_function(_nav_app)
        _run(at, "aaa", ["survey", "backcheck", "listing"], saved="listing")
        assert _selected(at) == "SELECTED=listing"

        _run(at, "aaa", ["survey", "backcheck"], saved="backcheck")

        assert _selected(at) == "SELECTED=backcheck"
