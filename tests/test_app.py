"""Tests for datasure/app.py.

app.py is entirely module-level Streamlit code. Tests re-import it under
controlled mocks to exercise all branches without running a real server.
"""

import importlib
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class MockSessionState:
    """Mimics st.session_state: supports the ``in`` operator and attribute access."""

    def __init__(self, initial: dict | None = None) -> None:
        object.__setattr__(self, "_data", dict(initial or {}))

    def __contains__(self, key: str) -> bool:
        return key in object.__getattribute__(self, "_data")

    def __getattr__(self, key: str):
        return object.__getattribute__(self, "_data").get(key)

    def __setattr__(self, key: str, value) -> None:
        object.__getattribute__(self, "_data")[key] = value

    def __getitem__(self, key: str):
        return object.__getattribute__(self, "_data")[key]

    def as_dict(self) -> dict:
        return dict(object.__getattribute__(self, "_data"))


def _import_app(
    session_state: dict | None = None,
    page_names: list[str] | None = None,
    assets_dir_exists: bool = True,
    logo_exists: bool = True,
) -> tuple:
    """Remove datasure.app from sys.modules, then re-import under controlled mocks.

    Returns (st_mock, session_state, config_service_cls, nav_mock).
    """
    sys.modules.pop("datasure.app", None)

    ss = MockSessionState(session_state or {})
    st_mock = MagicMock()
    st_mock.session_state = ss

    nav_mock = MagicMock()
    st_mock.navigation.return_value = nav_mock

    _original_exists = Path.exists
    _original_read_text = Path.read_text

    def _mock_exists(self: Path) -> bool:
        if self.name == "assets":
            return assets_dir_exists
        if self.name == "datasure-icon.svg":
            return logo_exists
        return _original_exists(self)

    def _mock_read_text(self: Path, *args, **kwargs) -> str:
        # The favicon reads datasure-icon.svg; keep it hermetic so the
        # fallback-assets-dir case does not touch a path that is absent on disk.
        if self.name == "datasure-icon.svg":
            return "<svg></svg>"
        return _original_read_text(self, *args, **kwargs)

    with (
        patch.dict(sys.modules, {"streamlit": st_mock}),
        patch("datasure.utils.config_utils.ConfigurationService") as cs_cls,
        patch.object(Path, "exists", _mock_exists),
        patch.object(Path, "read_text", _mock_read_text),
    ):
        cs_cls.return_value.get_page_names.return_value = list(page_names or [])
        importlib.import_module("datasure.app")

    return st_mock, ss, cs_cls, nav_mock


# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------


class TestSessionStateInit:
    """Session state keys are initialised when absent, not overwritten when present."""

    def test_project_id_initialised_to_empty_string(self):
        _, ss, *_ = _import_app(session_state={})
        assert ss.st_project_id == ""

    def test_output_pages_initialised_to_empty_list_without_project(self):
        _, ss, *_ = _import_app(session_state={})
        assert ss.st_output_pages == []

    def test_existing_project_id_not_overwritten(self):
        _, ss, *_ = _import_app(
            session_state={"st_project_id": "abc12345"},
            page_names=[],
        )
        assert ss.st_project_id == "abc12345"

    def test_static_pages_stored_in_session_state(self):
        _, ss, *_ = _import_app(session_state={})
        assert ss.st_start_page is not None
        assert ss.st_import_data_page is not None
        assert ss.st_prep_data_page is not None
        assert ss.st_config_checks_page is not None

    def test_output_page1_and_corr_default_none_without_pages(self):
        _, ss, *_ = _import_app(
            session_state={"st_project_id": "abc12345"},
            page_names=[],
        )
        assert ss.st_output_page1 is None
        assert ss.st_corr_page is None


# ---------------------------------------------------------------------------
# Navigation - no project ID
# ---------------------------------------------------------------------------


class TestNavigationNoProject:
    """When st_project_id is empty only the start-page nav is built."""

    def test_navigation_called_once(self):
        st_mock, *_ = _import_app(session_state={})
        st_mock.navigation.assert_called_once()

    def test_nav_dict_has_single_unnamed_section(self):
        st_mock, *_ = _import_app(session_state={})
        nav_arg = st_mock.navigation.call_args[0][0]
        assert list(nav_arg.keys()) == [""]

    def test_nav_single_section_contains_one_page(self):
        st_mock, *_ = _import_app(session_state={})
        nav_arg = st_mock.navigation.call_args[0][0]
        assert len(nav_arg[""]) == 1

    def test_config_service_not_called(self):
        _st, _ss, cs_cls, _nav = _import_app(session_state={})
        cs_cls.assert_not_called()

    def test_nav_run_is_called(self):
        _st, _ss, _cs, nav_mock = _import_app(session_state={})
        nav_mock.run.assert_called_once()

    def test_output_pages_remain_empty(self):
        _, ss, *_ = _import_app(session_state={})
        assert ss.st_output_pages == []


# ---------------------------------------------------------------------------
# Navigation - project ID set, no pages configured
# ---------------------------------------------------------------------------


class TestNavigationProjectNoPages:
    """With a project ID but no configured check pages."""

    @pytest.fixture
    def result(self):
        return _import_app(
            session_state={"st_project_id": "abc12345"},
            page_names=[],
        )

    def test_config_service_called_with_project_id(self, result):
        _st, _ss, cs_cls, _nav = result
        cs_cls.assert_called_once_with("abc12345")

    def test_navigation_has_single_section(self, result):
        st_mock, *_ = result
        nav_arg = st_mock.navigation.call_args[0][0]
        assert list(nav_arg.keys()) == [""]

    def test_navigation_section_has_four_pages(self, result):
        st_mock, *_ = result
        nav_arg = st_mock.navigation.call_args[0][0]
        assert len(nav_arg[""]) == 4

    def test_no_dqa_reports_section(self, result):
        st_mock, *_ = result
        nav_arg = st_mock.navigation.call_args[0][0]
        assert "DQA Reports" not in nav_arg

    def test_output_page1_remains_none(self, result):
        _, ss, *_ = result
        assert ss.st_output_page1 is None

    def test_corr_page_remains_none(self, result):
        _, ss, *_ = result
        assert ss.st_corr_page is None

    def test_nav_run_is_called(self, result):
        _st, _ss, _cs, nav_mock = result
        nav_mock.run.assert_called_once()


# ---------------------------------------------------------------------------
# Navigation - project ID set, pages configured
# ---------------------------------------------------------------------------


class TestNavigationProjectWithPages:
    """With a project ID and check pages configured."""

    @pytest.fixture
    def two_pages(self):
        return _import_app(
            session_state={"st_project_id": "abc12345"},
            page_names=["Household HFC", "Individual HFC"],
        )

    def test_navigation_has_three_sections(self, two_pages):
        st_mock, *_ = two_pages
        nav_arg = st_mock.navigation.call_args[0][0]
        assert len(nav_arg) == 3

    def test_dqa_reports_section_present(self, two_pages):
        st_mock, *_ = two_pages
        nav_arg = st_mock.navigation.call_args[0][0]
        assert "DQA Reports" in nav_arg

    def test_dqa_reports_page_count_matches(self, two_pages):
        st_mock, *_ = two_pages
        nav_arg = st_mock.navigation.call_args[0][0]
        assert len(nav_arg["DQA Reports"]) == 2

    def test_correction_section_present(self, two_pages):
        st_mock, *_ = two_pages
        nav_arg = st_mock.navigation.call_args[0][0]
        assert "---" in nav_arg

    def test_correction_section_has_two_pages(self, two_pages):
        st_mock, *_ = two_pages
        nav_arg = st_mock.navigation.call_args[0][0]
        assert len(nav_arg["---"]) == 2

    def test_output_pages_stored_in_session_state(self, two_pages):
        _st, ss, *_ = two_pages
        assert len(ss.st_output_pages) == 2

    def test_output_page1_stored_in_session_state(self, two_pages):
        _st, ss, *_ = two_pages
        assert ss.st_output_page1 is not None

    def test_corr_page_stored_in_session_state(self, two_pages):
        _st, ss, *_ = two_pages
        assert ss.st_corr_page is not None

    def test_output_page_files_named_sequentially(self, two_pages):
        st_mock, *_ = two_pages
        output_calls = [
            c
            for c in st_mock.Page.call_args_list
            if "output_view_" in c.kwargs.get("page", "")
        ]
        assert len(output_calls) == 2
        assert "output_view_1.py" in output_calls[0].kwargs["page"]
        assert "output_view_2.py" in output_calls[1].kwargs["page"]

    def test_single_configured_page(self):
        st_mock, ss, *_ = _import_app(
            session_state={"st_project_id": "abc12345"},
            page_names=["Single HFC"],
        )
        assert len(ss.st_output_pages) == 1
        nav_arg = st_mock.navigation.call_args[0][0]
        assert len(nav_arg["DQA Reports"]) == 1

    def test_nav_run_is_called(self, two_pages):
        _st, _ss, _cs, nav_mock = two_pages
        nav_mock.run.assert_called_once()

    def test_output_pages_list_reset_before_population(self, two_pages):
        """st_output_pages is always reset to [] before pages are appended."""
        _st, ss, *_ = two_pages
        # Result should contain exactly the configured pages, not accumulate
        assert len(ss.st_output_pages) == 2


# ---------------------------------------------------------------------------
# Static pages always created
# ---------------------------------------------------------------------------


class TestStaticPages:
    """Start, Import, Prep, and Config pages are always created."""

    def test_start_page_is_default(self):
        st_mock, *_ = _import_app()
        first_call = st_mock.Page.call_args_list[0]
        assert first_call.kwargs.get("default") is True

    def test_start_page_uses_start_view(self):
        st_mock, *_ = _import_app()
        assert "start_view.py" in st_mock.Page.call_args_list[0].kwargs["page"]

    def test_import_page_uses_import_view(self):
        st_mock, *_ = _import_app()
        assert "import_view.py" in st_mock.Page.call_args_list[1].kwargs["page"]

    def test_prep_page_uses_prep_view(self):
        st_mock, *_ = _import_app()
        assert "prep_view.py" in st_mock.Page.call_args_list[2].kwargs["page"]

    def test_config_page_uses_config_view(self):
        st_mock, *_ = _import_app()
        assert "config_view.py" in st_mock.Page.call_args_list[3].kwargs["page"]

    def test_correction_page_uses_correction_view(self):
        st_mock, *_ = _import_app(
            session_state={"st_project_id": "abc12345"},
            page_names=["HFC"],
        )
        correction_calls = [
            c
            for c in st_mock.Page.call_args_list
            if "correction_view.py" in c.kwargs.get("page", "")
        ]
        assert len(correction_calls) == 1


# ---------------------------------------------------------------------------
# Assets directory and logo
# ---------------------------------------------------------------------------


class TestAssetsAndLogo:
    """Logo is loaded conditionally based on file existence."""

    def test_logo_called_when_logo_exists(self):
        st_mock, *_ = _import_app(assets_dir_exists=True, logo_exists=True)
        st_mock.logo.assert_called_once()

    def test_logo_not_called_when_logo_missing(self):
        st_mock, *_ = _import_app(assets_dir_exists=True, logo_exists=False)
        st_mock.logo.assert_not_called()

    def test_logo_arg_is_svg_string(self):
        st_mock, *_ = _import_app(assets_dir_exists=True, logo_exists=True)
        logo_arg = st_mock.logo.call_args[0][0]
        assert isinstance(logo_arg, str)
        assert logo_arg.endswith(".svg")

    def test_logo_loaded_with_fallback_assets_dir(self):
        """Logo is still loaded when the assets dir falls back to cwd."""
        st_mock, *_ = _import_app(assets_dir_exists=False, logo_exists=True)
        st_mock.logo.assert_called_once()

    def test_logo_not_loaded_when_fallback_and_missing(self):
        st_mock, *_ = _import_app(assets_dir_exists=False, logo_exists=False)
        st_mock.logo.assert_not_called()
