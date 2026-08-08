"""Tests for start_view.py - actual imports with proper mocking."""

import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from datasure.utils.onboarding_utils import DEMO_PROJECT_ID

# --- Module import setup ---
# Unlike most view pages, start_view.py has no project guard: it renders its
# whole page unconditionally at import time. Layout primitives must be
# context-manager capable, and st.tabs must return enough entries for the
# "Learn more" section's 5 workflow tabs, before the module can be imported.
_st = sys.modules["streamlit"]


def _make_columns(spec, **_kwargs):
    """Return one context-manager mock per requested column."""
    n = spec if isinstance(spec, int) else len(spec)
    return [MagicMock() for _ in range(n)]


_st.columns = MagicMock(side_effect=_make_columns)
_st.container = MagicMock()
_st.tabs = MagicMock(return_value=[MagicMock() for _ in range(5)])

# st.selectbox defaults to returning None (conftest default), so none of the
# "DataSure Demo" / "Create New Project" / existing-project branches run
# during import - only get_project_names()/_get_last_used_project_name() are
# exercised, both of which read the project registry via get_cache_path.
# Patch it to a throwaway temp dir so import never touches the real cache.
_fake_import_cache_dir = Path(tempfile.mkdtemp(prefix="datasure_start_view_import_"))

with patch(
    "datasure.utils.cache_utils.get_cache_path",
    side_effect=lambda *parts: _fake_import_cache_dir.joinpath(*parts),
):
    import datasure.views.start_view as start_view


@pytest.fixture(autouse=True)
def _isolated_cache(tmp_path, monkeypatch):
    """Point start_view's get_cache_path at a fresh temp dir for each test."""
    monkeypatch.setattr(
        start_view, "get_cache_path", lambda *parts: tmp_path.joinpath(*parts)
    )


# === PURE VALIDATION FUNCTION TESTS === #


class TestValidateProjectId:
    """Test _validate_project_id."""

    def test_valid_id(self):
        assert start_view._validate_project_id("abcd1234") is True

    def test_too_short(self):
        assert start_view._validate_project_id("abc123") is False

    def test_non_alnum(self):
        assert start_view._validate_project_id("abcd-234") is False


class TestGetProjectId:
    """Test get_project_id."""

    def test_deterministic(self):
        assert start_view.get_project_id("My Project") == start_view.get_project_id(
            "My Project"
        )

    def test_different_names_different_ids(self):
        assert start_view.get_project_id("Project A") != start_view.get_project_id(
            "Project B"
        )

    def test_length_and_format(self):
        project_id = start_view.get_project_id("Any Project Name")
        assert len(project_id) == 8
        assert start_view._validate_project_id(project_id)


class TestValidProjectName:
    """Test valid_project_name."""

    def test_empty_name(self, monkeypatch):
        mock_error = MagicMock()
        monkeypatch.setattr(_st, "error", mock_error)
        assert start_view.valid_project_name("") is False
        mock_error.assert_called_once()

    def test_too_short(self, monkeypatch):
        monkeypatch.setattr(_st, "error", MagicMock())
        assert start_view.valid_project_name("ab") is False

    def test_invalid_characters(self, monkeypatch):
        monkeypatch.setattr(_st, "error", MagicMock())
        assert start_view.valid_project_name("bad!name") is False

    def test_valid_name(self, monkeypatch):
        mock_error = MagicMock()
        monkeypatch.setattr(_st, "error", mock_error)
        assert start_view.valid_project_name("My Project-1") is True
        mock_error.assert_not_called()


class TestNowStr:
    """Test _now_str."""

    def test_matches_expected_format(self):
        # Raises ValueError if the format doesn't match.
        datetime.strptime(start_view._now_str(), "%Y-%m-%d %H:%M:%S")


# === PROJECT REGISTRY PERSISTENCE TESTS === #


class TestSaveProjects:
    """Test _save_projects."""

    def test_writes_json(self, tmp_path):
        start_view._save_projects({"abcd1234": {"name": "X"}})
        written = json.loads((tmp_path / "projects.json").read_text())
        assert written == {"abcd1234": {"name": "X"}}


class TestLoadProjects:
    """Test load_projects."""

    def test_no_file_returns_empty_dict(self):
        assert start_view.load_projects() == {}

    def test_reads_existing_file(self, tmp_path):
        (tmp_path / "projects.json").write_text(
            json.dumps({"abcd1234": {"name": "Test"}})
        )
        assert start_view.load_projects() == {"abcd1234": {"name": "Test"}}


class TestSaveProject:
    """Test save_project."""

    def test_invalid_id_raises(self):
        with pytest.raises(ValueError, match="Invalid project ID"):
            start_view.save_project("My Project", "bad-id")

    def test_creates_directories_and_metadata(self, tmp_path):
        start_view.save_project("My Project", "abcd1234")
        project_path = tmp_path / "abcd1234"
        assert (project_path / "data").is_dir()
        assert (project_path / "settings").is_dir()
        info = json.loads((project_path / "settings" / "project_info.json").read_text())
        assert "created_at" in info

    def test_registers_project(self, tmp_path):
        start_view.save_project("My Project", "abcd1234")
        projects = json.loads((tmp_path / "projects.json").read_text())
        assert projects["abcd1234"]["name"] == "My Project"
        assert "created_at" in projects["abcd1234"]
        assert "last_used" in projects["abcd1234"]

    def test_existing_project_preserves_created_at(self, tmp_path):
        start_view.save_project("My Project", "abcd1234")
        first = json.loads((tmp_path / "projects.json").read_text())["abcd1234"]

        start_view.save_project("My Project", "abcd1234")
        second = json.loads((tmp_path / "projects.json").read_text())["abcd1234"]

        assert second["created_at"] == first["created_at"]

    def test_project_dir_without_info_file_recreates_it(self, tmp_path):
        project_path = tmp_path / "abcd1234"
        (project_path / "settings").mkdir(parents=True)
        (project_path / "data").mkdir()

        start_view.save_project("My Project", "abcd1234")

        assert (project_path / "settings" / "project_info.json").exists()


class TestDeleteProject:
    """Test delete_project."""

    def test_delete_existing_project(self, tmp_path, monkeypatch):
        start_view.save_project("My Project", "abcd1234")
        mock_success = MagicMock()
        monkeypatch.setattr(_st, "success", mock_success)

        start_view.delete_project("abcd1234")

        assert "abcd1234" not in start_view.load_projects()
        assert not (tmp_path / "abcd1234").exists()
        mock_success.assert_called_once()

    def test_delete_nonexistent_project_shows_error(self, monkeypatch):
        mock_error = MagicMock()
        monkeypatch.setattr(_st, "error", mock_error)

        start_view.delete_project("abcd1234")

        mock_error.assert_called_once()

    def test_delete_invalid_id_shows_error(self, monkeypatch):
        mock_error = MagicMock()
        monkeypatch.setattr(_st, "error", mock_error)

        start_view.delete_project("bad-id")

        mock_error.assert_called_once()


class TestGetProjectNames:
    """Test get_project_names."""

    def test_no_projects_file(self):
        assert start_view.get_project_names() == [
            "DataSure Demo",
            "Create New Project",
        ]

    def test_sorts_by_last_used_most_recent_first(self, tmp_path):
        (tmp_path / "projects.json").write_text(
            json.dumps(
                {
                    "id1": {"name": "Older", "last_used": "2024-01-01 00:00:00"},
                    "id2": {"name": "Newer", "last_used": "2024-06-01 00:00:00"},
                }
            )
        )
        assert start_view.get_project_names() == [
            "DataSure Demo",
            "Newer",
            "Older",
            "Create New Project",
        ]

    def test_excludes_demo_projects(self, tmp_path):
        (tmp_path / "projects.json").write_text(
            json.dumps(
                {
                    "demoid": {
                        "name": "Demo Copy",
                        "is_demo": True,
                        "last_used": "2024-01-01 00:00:00",
                    },
                    "id1": {
                        "name": "Real Project",
                        "last_used": "2024-02-01 00:00:00",
                    },
                }
            )
        )
        names = start_view.get_project_names()
        assert "Demo Copy" not in names
        assert "Real Project" in names


class TestGetLastUsedProjectName:
    """Test _get_last_used_project_name."""

    def test_no_projects_file(self):
        assert start_view._get_last_used_project_name() is None

    def test_returns_most_recently_used(self, tmp_path):
        (tmp_path / "projects.json").write_text(
            json.dumps(
                {
                    "id1": {"name": "Older", "last_used": "2024-01-01 00:00:00"},
                    "id2": {"name": "Newer", "last_used": "2024-06-01 00:00:00"},
                }
            )
        )
        assert start_view._get_last_used_project_name() == "Newer"

    def test_ignores_demo_and_never_used_projects(self, tmp_path):
        (tmp_path / "projects.json").write_text(
            json.dumps(
                {
                    "demoid": {
                        "name": "Demo",
                        "is_demo": True,
                        "last_used": "2024-06-01 00:00:00",
                    },
                    "id1": {"name": "NoLastUsed"},
                }
            )
        )
        assert start_view._get_last_used_project_name() is None


# === PROJECT ACTIVATION / NAVIGATION TESTS === #


class TestActivateProject:
    """Test _activate_project."""

    def test_sets_state_syncs_and_switches_page(self, monkeypatch):
        monkeypatch.setitem(_st.session_state, "st_project_id", None)
        monkeypatch.setitem(_st.session_state, "st_import_data_page", "import_page")
        mock_switch_page = MagicMock()
        monkeypatch.setattr(_st, "switch_page", mock_switch_page)

        with patch("datasure.views.start_view.ConfigurationService") as mock_cs:
            start_view._activate_project("abcd1234")

        assert _st.session_state["st_project_id"] == "abcd1234"
        mock_cs.assert_called_once_with("abcd1234")
        mock_cs.return_value.sync_output_view_files.assert_called_once()
        mock_switch_page.assert_called_once_with("import_page")


class TestCreateAndLoadProject:
    """Test _create_and_load_project."""

    def test_saves_project_then_activates_it(self, tmp_path):
        with patch("datasure.views.start_view._activate_project") as mock_activate:
            start_view._create_and_load_project("My Project", "abcd1234")

        assert "abcd1234" in start_view.load_projects()
        mock_activate.assert_called_once_with("abcd1234")


class TestDeleteProjectAndReset:
    """Test _delete_project_and_reset."""

    def test_deletes_project_and_clears_session_state(self, tmp_path, monkeypatch):
        start_view.save_project("My Project", "abcd1234")
        monkeypatch.setitem(_st.session_state, "st_project_id", "abcd1234")

        start_view._delete_project_and_reset("abcd1234")

        assert start_view.load_projects() == {}
        assert _st.session_state["st_project_id"] == ""


# === HANDLER FUNCTION TESTS (with mocked Streamlit widgets) === #


class TestHandleCreateNewProject:
    """Test _handle_create_new_project."""

    def test_asks_for_confirmation_before_creating(self, monkeypatch):
        monkeypatch.setattr(_st, "text_input", MagicMock(return_value="My New Project"))
        monkeypatch.setattr(_st, "button", MagicMock(return_value=True))

        with patch("datasure.views.start_view.confirm_dialog") as mock_confirm:
            start_view._handle_create_new_project()

        mock_confirm.assert_called_once()
        args, kwargs = mock_confirm.call_args
        assert kwargs["confirm_label"] == "Create & Load New Project"
        assert "My New Project" in args[1]

    def test_confirming_creates_and_activates_the_project(self, tmp_path, monkeypatch):
        monkeypatch.setattr(_st, "text_input", MagicMock(return_value="My New Project"))
        monkeypatch.setattr(_st, "button", MagicMock(return_value=True))

        with patch("datasure.views.start_view.confirm_dialog") as mock_confirm:
            start_view._handle_create_new_project()
        on_confirm = mock_confirm.call_args.kwargs["on_confirm"]

        with patch("datasure.views.start_view._activate_project") as mock_activate:
            on_confirm()

        project_id = start_view.get_project_id("My New Project")
        assert project_id in start_view.load_projects()
        mock_activate.assert_called_once_with(project_id)

    def test_duplicate_name_shows_error_and_stops(self, tmp_path, monkeypatch):
        existing_id = start_view.get_project_id("Existing")
        start_view.save_project("Existing", existing_id)
        monkeypatch.setattr(_st, "text_input", MagicMock(return_value="Existing"))
        monkeypatch.setattr(_st, "button", MagicMock(return_value=True))
        mock_error = MagicMock()
        monkeypatch.setattr(_st, "error", mock_error)
        monkeypatch.setattr(_st, "stop", MagicMock(side_effect=StopIteration))

        with (
            patch("datasure.views.start_view.confirm_dialog") as mock_confirm,
            pytest.raises(StopIteration),
        ):
            start_view._handle_create_new_project()

        mock_error.assert_called_once()
        mock_confirm.assert_not_called()

    def test_no_button_click_does_nothing(self, monkeypatch):
        monkeypatch.setattr(_st, "text_input", MagicMock(return_value=""))
        monkeypatch.setattr(_st, "button", MagicMock(return_value=False))

        with patch("datasure.views.start_view.confirm_dialog") as mock_confirm:
            start_view._handle_create_new_project()

        mock_confirm.assert_not_called()


class TestHandleExistingProjectSelection:
    """Test _handle_existing_project_selection."""

    def test_loading_activates_the_project(self, tmp_path, monkeypatch):
        project_id = start_view.get_project_id("My Project")
        start_view.save_project("My Project", project_id)
        monkeypatch.setattr(_st, "button", MagicMock(return_value=True))
        monkeypatch.setattr(_st, "write", MagicMock())

        with (
            patch("datasure.views.start_view._activate_project") as mock_activate,
            patch("datasure.views.start_view._show_delete_project_option"),
        ):
            start_view._handle_existing_project_selection("My Project")

        mock_activate.assert_called_once_with(project_id)

    def test_no_click_does_not_activate(self, tmp_path, monkeypatch):
        project_id = start_view.get_project_id("My Project")
        start_view.save_project("My Project", project_id)
        monkeypatch.setattr(_st, "button", MagicMock(return_value=False))

        with patch("datasure.views.start_view._activate_project") as mock_activate:
            start_view._handle_existing_project_selection("My Project")

        mock_activate.assert_not_called()

    def test_demo_project_skips_delete_option(self, monkeypatch):
        monkeypatch.setattr(_st, "button", MagicMock(return_value=False))

        with (
            patch(
                "datasure.views.start_view.get_project_id",
                return_value=DEMO_PROJECT_ID,
            ),
            patch(
                "datasure.views.start_view._show_delete_project_option"
            ) as mock_show_delete,
        ):
            start_view._handle_existing_project_selection("DataSure Demo")

        mock_show_delete.assert_not_called()

    def test_non_demo_project_shows_delete_option(self, tmp_path, monkeypatch):
        start_view.save_project("My Project", start_view.get_project_id("My Project"))
        monkeypatch.setattr(_st, "button", MagicMock(return_value=False))

        with patch(
            "datasure.views.start_view._show_delete_project_option"
        ) as mock_show_delete:
            start_view._handle_existing_project_selection("My Project")

        mock_show_delete.assert_called_once()


class TestShowDeleteProjectOption:
    """Test _show_delete_project_option."""

    def test_click_opens_confirm_dialog(self, monkeypatch):
        monkeypatch.setattr(_st, "button", MagicMock(return_value=True))

        with patch("datasure.views.start_view.confirm_dialog") as mock_confirm:
            start_view._show_delete_project_option("My Project", "abcd1234", {})

        mock_confirm.assert_called_once()
        assert mock_confirm.call_args.kwargs["confirm_label"] == "Delete project"

    def test_no_click_does_nothing(self, monkeypatch):
        monkeypatch.setattr(_st, "button", MagicMock(return_value=False))

        with patch("datasure.views.start_view.confirm_dialog") as mock_confirm:
            start_view._show_delete_project_option("My Project", "abcd1234", {})

        mock_confirm.assert_not_called()


class TestLaunchFreshDemo:
    """Test _launch_fresh_demo."""

    def test_success_path_activates_demo_and_advances_onboarding(self, monkeypatch):
        monkeypatch.setitem(_st.session_state, "st_project_id", None)
        mock_switch_page = MagicMock()
        monkeypatch.setattr(_st, "switch_page", mock_switch_page)

        with (
            patch(
                "datasure.views.start_view.create_demo_project",
                return_value="demoid",
            ),
            patch("datasure.views.start_view.load_demo_data", return_value=True),
            patch("datasure.views.start_view.set_onboarding_step") as mock_step,
        ):
            start_view._launch_fresh_demo()

        assert _st.session_state["st_project_id"] == "demoid"
        mock_switch_page.assert_called_once()
        mock_step.assert_any_call(1)
        mock_step.assert_any_call(2)

    def test_failure_path_shows_error(self, monkeypatch):
        mock_error = MagicMock()
        monkeypatch.setattr(_st, "error", mock_error)
        mock_switch_page = MagicMock()
        monkeypatch.setattr(_st, "switch_page", mock_switch_page)

        with (
            patch(
                "datasure.views.start_view.create_demo_project",
                return_value="demoid",
            ),
            patch("datasure.views.start_view.load_demo_data", return_value=False),
            patch("datasure.views.start_view.set_onboarding_step"),
        ):
            start_view._launch_fresh_demo()

        mock_error.assert_called_once()
        mock_switch_page.assert_not_called()


class TestHandleDemoProject:
    """Test _handle_demo_project."""

    def test_resume_demo_activates_it_when_it_exists(self, monkeypatch):
        monkeypatch.setattr(
            _st,
            "button",
            MagicMock(side_effect=lambda label=None, *a, **k: label == "Resume Demo"),
        )

        with (
            patch("datasure.views.start_view.show_demo_intro"),
            patch(
                "datasure.views.start_view.load_projects",
                return_value={DEMO_PROJECT_ID: {}},
            ),
            patch("datasure.views.start_view._activate_project") as mock_activate,
        ):
            start_view._handle_demo_project()

        mock_activate.assert_called_once_with(DEMO_PROJECT_ID)

    def test_restart_demo_opens_confirm_dialog(self, monkeypatch):
        monkeypatch.setattr(
            _st,
            "button",
            MagicMock(side_effect=lambda label=None, *a, **k: label == "Restart Demo"),
        )

        with (
            patch("datasure.views.start_view.show_demo_intro"),
            patch(
                "datasure.views.start_view.load_projects",
                return_value={DEMO_PROJECT_ID: {}},
            ),
            patch("datasure.views.start_view.confirm_dialog") as mock_confirm,
        ):
            start_view._handle_demo_project()

        mock_confirm.assert_called_once()

    def test_start_demo_when_no_demo_exists(self, monkeypatch):
        monkeypatch.setattr(_st, "button", MagicMock(return_value=True))

        with (
            patch("datasure.views.start_view.show_demo_intro"),
            patch("datasure.views.start_view.load_projects", return_value={}),
            patch("datasure.views.start_view._launch_fresh_demo") as mock_launch,
        ):
            start_view._handle_demo_project()

        mock_launch.assert_called_once()
