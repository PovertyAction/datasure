"""Tests for the reviewer identity recorded in the correction log."""

import json

import pytest

from datasure.utils import reviewer
from datasure.utils.reviewer import get_reviewer_name, set_reviewer_name


@pytest.fixture(autouse=True)
def user_settings_file(tmp_path, monkeypatch):
    """Point the user settings file at a temporary path."""
    path = tmp_path / "user_settings.json"
    monkeypatch.setattr(reviewer, "_user_settings_path", lambda: path)
    monkeypatch.setattr(reviewer.getpass, "getuser", lambda: "os_login")
    return path


class TestGetReviewerName:
    def test_defaults_to_the_os_login(self):
        assert get_reviewer_name() == "os_login"

    def test_override_takes_precedence_over_the_os_login(self):
        set_reviewer_name("Ama Mensah")
        assert get_reviewer_name() == "Ama Mensah"

    def test_override_persists_in_the_user_settings_file(self, user_settings_file):
        set_reviewer_name("Ama Mensah")
        assert json.loads(user_settings_file.read_text())["reviewer_name"] == (
            "Ama Mensah"
        )

    def test_override_is_stripped(self):
        set_reviewer_name("  Ama Mensah  ")
        assert get_reviewer_name() == "Ama Mensah"

    def test_clearing_the_override_falls_back_to_the_os_login(self):
        set_reviewer_name("Ama Mensah")
        set_reviewer_name("   ")
        assert get_reviewer_name() == "os_login"

    def test_keeps_other_user_settings(self, user_settings_file):
        user_settings_file.write_text(json.dumps({"other": 1}))
        set_reviewer_name("Ama Mensah")
        assert json.loads(user_settings_file.read_text())["other"] == 1

    def test_unreadable_settings_file_falls_back_to_the_os_login(
        self, user_settings_file
    ):
        user_settings_file.write_text("not json")
        assert get_reviewer_name() == "os_login"

    def test_os_login_lookup_failure_gives_an_empty_name(self, monkeypatch):
        def fail():
            raise OSError("no login")

        monkeypatch.setattr(reviewer.getpass, "getuser", fail)
        assert get_reviewer_name() == ""


def _reviewer_setting_app():
    from datasure.utils.reviewer import render_reviewer_setting

    render_reviewer_setting()


class TestRenderReviewerSetting:
    def test_entering_a_name_saves_the_override(self):
        from streamlit.testing.v1 import AppTest

        at = AppTest.from_function(_reviewer_setting_app).run()
        at.text_input(key="reviewer_name_input").input("Ama Mensah").run()

        assert not at.exception
        assert get_reviewer_name() == "Ama Mensah"
        assert at.text_input(key="reviewer_name_input").value == "Ama Mensah"
