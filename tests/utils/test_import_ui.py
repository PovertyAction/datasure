"""AppTest coverage of the import page's add, edit and remove dialogs."""

import polars as pl
import pytest
from streamlit.testing.v1 import AppTest

from datasure.connectors.local import FileConfig
from datasure.connectors.scto import FormConfig
from datasure.utils.duckdb_utils import (
    duckdb_get_table,
    duckdb_save_table,
    duckdb_table_exists,
)
from datasure.utils.import_log import save_local_dataset, save_surveycto_dataset

PROJECT = "proj"
SERVER = {
    "ipa-training": {
        "server": "ipa-training",
        "username": "me@example.org",
        "credential_type": "scto_login",
    }
}
FORMS = [("hh_main", "Household survey", False), ("hh_bc", "Back-check", False)]


@pytest.fixture(autouse=True)
def project_dirs(isolated_cache):
    for folder in ("settings", "data"):
        (isolated_cache / PROJECT / folder).mkdir(parents=True)


@pytest.fixture
def connected(monkeypatch):
    """One saved SurveyCTO server whose forms are FORMS, with no network."""
    from datasure.utils import import_ui

    monkeypatch.setattr(
        import_ui, "list_stored_credentials", lambda _p: {"credentials": SERVER}
    )
    monkeypatch.setattr(import_ui, "list_server_forms", lambda *_a: FORMS)


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "survey.csv"
    path.write_text("a,b\n1,2\n")
    return str(path)


def _add_app(project_id):
    import streamlit as st

    from datasure.utils.import_ui import open_add_dialog, show_open_dialog

    if st.button("Open"):
        open_add_dialog(project_id)
    else:
        show_open_dialog(project_id)


def _edit_app(project_id, alias):
    import streamlit as st

    from datasure.utils.import_log import dataset_entry
    from datasure.utils.import_ui import open_edit_dialog, show_open_dialog

    if st.button("Open"):
        open_edit_dialog(project_id, dataset_entry(project_id, alias))
    else:
        show_open_dialog(project_id)


def _remove_app(project_id, alias):
    import streamlit as st

    from datasure.utils.import_ui import open_remove_dialog

    # AppTest reruns the whole script, so keep the dialog open once opened.
    if st.button("Open") or st.session_state.get("removing"):
        st.session_state["removing"] = True
        open_remove_dialog(project_id, alias)


def _open(app, *args) -> AppTest:
    at = AppTest.from_function(app, args=(PROJECT, *args), default_timeout=30)
    at.run()
    _button(at, "Open").click().run()
    assert not at.exception, at.exception
    return at


def _button(at, label):
    matches = [b for b in at.get("button") if b.label == label]
    assert matches, f"no {label!r} button in {[b.label for b in at.get('button')]}"
    return matches[0]


def _click(at, label) -> AppTest:
    _button(at, label).click().run()
    assert not at.exception, at.exception
    return at


def _text_input(at, label):
    return next(t for t in at.get("text_input") if t.label == label)


def _selectbox(at, label):
    return next(s for s in at.get("selectbox") if s.label == label)


def _log() -> pl.DataFrame:
    return duckdb_get_table(PROJECT, "import_log", "logs")


def _step(at) -> str:
    return at.session_state["import_dataset_dialog"]["step"]


class TestAddDialog:
    def test_starts_at_source_and_next_is_disabled_until_a_source_is_chosen(self):
        at = _open(_add_app)

        assert _step(at) == "source"
        assert _button(at, "Next").disabled
        assert not any(b.label == "Back" for b in at.get("button"))

    def test_local_file_walks_source_connection_review_and_saves_on_confirm(
        self, csv_file
    ):
        at = _open(_add_app)
        at.get("radio")[0].set_value("local storage").run()
        _click(at, "Next")
        assert _step(at) == "connection"

        _text_input(at, "Alias").input("survey").run()
        _text_input(at, "File path").input(csv_file).run()
        assert any("File found" in s.value for s in at.get("success"))
        _click(at, "Next: review")

        assert _step(at) == "review"
        assert any(csv_file in m.value for m in at.get("markdown"))
        # Nothing is saved before Review is confirmed.
        assert _log().is_empty()

        _click(at, "Add dataset")
        row = _log().to_dicts()[0]
        assert (row["alias"], row["filename"]) == ("survey", csv_file)
        # Adding registers the dataset; it doesn't import it.
        assert not duckdb_table_exists(PROJECT, "survey", "raw")

    def test_missing_file_is_reported_and_blocks_next(self, tmp_path):
        at = _open(_add_app)
        at.get("radio")[0].set_value("local storage").run()
        _click(at, "Next")

        _text_input(at, "File path").input(str(tmp_path / "nope.csv")).run()

        assert any("no file" in e.value for e in at.get("error"))
        assert _button(at, "Next: review").disabled

    def test_unsupported_type_is_reported(self, tmp_path):
        path = tmp_path / "notes.txt"
        path.write_text("x")
        at = _open(_add_app)
        at.get("radio")[0].set_value("local storage").run()
        _click(at, "Next")

        _text_input(at, "File path").input(str(path)).run()

        assert any("aren't supported" in e.value for e in at.get("error"))

    def test_back_returns_to_the_previous_step_keeping_answers(self, csv_file):
        at = _open(_add_app)
        at.get("radio")[0].set_value("local storage").run()
        _click(at, "Next")
        _text_input(at, "Alias").input("survey").run()
        _text_input(at, "File path").input(csv_file).run()
        _click(at, "Next: review")

        _click(at, "Back")
        assert _step(at) == "connection"
        assert _text_input(at, "Alias").value == "survey"
        assert _text_input(at, "File path").value == csv_file

        _click(at, "Back")
        assert _step(at) == "source"
        assert at.get("radio")[0].value == "local storage"

    def test_back_before_review_keeps_unfinished_answers(self, tmp_path):
        missing = str(tmp_path / "not_there_yet.csv")
        at = _open(_add_app)
        at.get("radio")[0].set_value("local storage").run()
        _click(at, "Next")
        _text_input(at, "Alias").input("survey").run()
        # Not a usable path, so Next: review can't capture it.
        _text_input(at, "File path").input(missing).run()

        _click(at, "Back")
        _click(at, "Next")

        assert _step(at) == "connection"
        assert _text_input(at, "Alias").value == "survey"
        assert _text_input(at, "File path").value == missing

    def test_changes_after_returning_from_review_survive_back(self, csv_file):
        at = _open(_add_app)
        at.get("radio")[0].set_value("local storage").run()
        _click(at, "Next")
        _text_input(at, "Alias").input("survey").run()
        _text_input(at, "File path").input(csv_file).run()
        _click(at, "Next: review")
        _click(at, "Back")

        _text_input(at, "Alias").input("survey_r2").run()
        _click(at, "Back")
        _click(at, "Next")

        assert _text_input(at, "Alias").value == "survey_r2"

    def test_changing_source_after_back_still_starts_fresh(self, connected):
        at = _open(_add_app)
        at.get("radio")[0].set_value("local storage").run()
        _click(at, "Next")
        _text_input(at, "Alias").input("survey").run()
        _click(at, "Back")

        at.get("radio")[0].set_value("SurveyCTO").run()
        _click(at, "Next")

        assert at.session_state["import_dataset_dialog"]["values"] == {}

    def test_surveycto_back_keeps_the_form_and_its_settings(self, connected):
        at = _open(_add_app)
        at.get("radio")[0].set_value("SurveyCTO").run()
        _click(at, "Next")
        _selectbox(at, "Form").set_value("hh_bc").run()
        _text_input(at, "Alias").input("backcheck").run()
        _text_input(at, "Also save a copy to (optional)").input("C:/x.csv").run()

        _click(at, "Back")
        _click(at, "Next")

        assert _selectbox(at, "Form").value == "hh_bc"
        assert _text_input(at, "Alias").value == "backcheck"
        assert _text_input(at, "Also save a copy to (optional)").value == "C:/x.csv"

    def test_clashing_alias_is_refused_at_connection(self, csv_file):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))
        at = _open(_add_app)
        at.get("radio")[0].set_value("local storage").run()
        _click(at, "Next")
        _text_input(at, "Alias").input("Survey").run()
        _text_input(at, "File path").input(csv_file).run()

        _click(at, "Next: review")

        assert _step(at) == "connection"
        assert at.get("error")
        assert _log().height == 1

    def test_surveycto_form_is_registered_after_review(self, connected):
        at = _open(_add_app)
        at.get("radio")[0].set_value("SurveyCTO").run()
        _click(at, "Next")

        _selectbox(at, "Form").set_value("hh_main").run()
        assert _text_input(at, "Alias").value == "Household survey"
        _click(at, "Next: review")
        assert any("hh_main (Household survey)" in m.value for m in at.get("markdown"))
        assert _log().is_empty()

        _click(at, "Add dataset")
        row = _log().to_dicts()[0]
        assert (row["alias"], row["form_id"], row["server"]) == (
            "Household survey",
            "hh_main",
            "ipa-training",
        )

    def test_surveycto_without_a_connection_points_to_connections(self, monkeypatch):
        from datasure.utils import import_ui

        monkeypatch.setattr(
            import_ui, "list_stored_credentials", lambda _p: {"credentials": {}}
        )
        at = _open(_add_app)
        at.get("radio")[0].set_value("SurveyCTO").run()
        _click(at, "Next")

        assert any("Connections" in w.value for w in at.get("warning"))
        assert _button(at, "Next: review").disabled


class TestEditDialog:
    def test_local_edit_opens_filled_in_and_saves_the_new_path(
        self, csv_file, tmp_path
    ):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))
        at = _open(_edit_app, "survey")

        assert _step(at) == "connection"
        alias = _text_input(at, "Alias")
        assert (alias.value, alias.disabled) == ("survey", True)
        assert _text_input(at, "File path").value == csv_file

        other = tmp_path / "other.csv"
        other.write_text("a\n1\n")
        _text_input(at, "File path").input(str(other)).run()
        _click(at, "Next: review")
        _click(at, "Save changes")

        assert _log().to_dicts()[0]["filename"] == str(other)

    def test_surveycto_edit_opens_filled_in(self, connected):
        save_surveycto_dataset(
            PROJECT,
            FormConfig(
                alias="household",
                form_id="hh_bc",
                server="ipa-training",
                username="me@example.org",
                attachments=True,
            ),
        )
        at = _open(_edit_app, "household")

        assert _selectbox(at, "Server").value == "ipa-training"
        assert _selectbox(at, "Form").value == "hh_bc"
        assert _text_input(at, "Alias").value == "household"
        assert next(t for t in at.get("toggle") if t.label == "Download media").value

    def test_back_from_edit_shows_the_source_locked(self, csv_file):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))
        at = _open(_edit_app, "survey")

        _click(at, "Back")

        assert _step(at) == "source"
        assert at.get("radio")[0].disabled
        assert at.get("radio")[0].value == "local storage"


class TestRemoveDialog:
    def test_asks_first_and_says_what_is_deleted(self, csv_file):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))
        at = _open(_remove_app, "survey")

        body = " ".join(w.value for w in at.get("warning"))
        assert "survey" in body
        assert "imported, prepared and corrected data" in body
        assert _log().height == 1

    def test_confirm_removes_the_dataset_and_its_tables(self, csv_file):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))
        duckdb_save_table(PROJECT, pl.DataFrame({"a": [1]}), alias="survey")
        at = _open(_remove_app, "survey")

        _click(at, "Remove")

        assert _log().is_empty()
        assert not duckdb_table_exists(PROJECT, "survey", "raw")

    def test_cancel_keeps_the_dataset(self, csv_file):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))
        at = _open(_remove_app, "survey")

        _click(at, "Cancel")

        assert _log().height == 1


class _FakeLoginForm:
    def __init__(self, _project_id):
        pass

    def render_login_form(self):
        import streamlit as st

        st.button("Connect & Save Credentials")


def _remove_connection_app(project_id):
    # What confirming the Remove connection dialog runs.
    from datasure.utils.import_ui import _remove_connection

    details = {"server": "ipa-training", "credential_type": "scto_login"}
    _remove_connection(project_id, "ipa-training", details)


def _connections_app(project_id):
    from datasure.utils.import_ui import render_connections

    render_connections(project_id)


def _connections(monkeypatch, credentials, *, deleted=None, keyring=None):
    from datasure.utils import import_ui

    monkeypatch.setattr(
        import_ui, "list_stored_credentials", lambda _p: {"credentials": credentials}
    )
    monkeypatch.setattr(
        import_ui,
        "delete_stored_credentials",
        lambda **kwargs: (
            (deleted.append(kwargs), {"success": True})[1]
            if deleted is not None
            else {"success": True}
        ),
    )
    if keyring is not None:
        monkeypatch.setattr(import_ui, "test_keyring_availability", lambda: keyring)
    # The SurveyCTO sign-in form is tested in tests/connectors/test_scto.py.
    monkeypatch.setattr(import_ui, "SurveyCTOUI", _FakeLoginForm)
    at = AppTest.from_function(_connections_app, args=(PROJECT,), default_timeout=30)
    at.run()
    assert not at.exception, at.exception
    return at


class TestConnections:
    def test_open_with_guidance_when_nothing_is_connected(self, monkeypatch):
        at = _connections(monkeypatch, {})

        (expander,) = at.expander
        assert expander.label == "Connections · Nothing connected yet"
        assert expander.proto.expanded is True

    def test_collapsed_with_a_summary_once_a_server_is_connected(self, monkeypatch):
        at = _connections(monkeypatch, SERVER)

        (expander,) = at.expander
        assert expander.label == "Connections · 1 SurveyCTO server connected"
        assert expander.proto.expanded is False
        assert "SurveyCTO" not in expander.label.split("·")[0]

    def test_holds_add_remove_and_keyring_diagnostics(self, monkeypatch):
        at = _connections(monkeypatch, SERVER)

        labels = {b.label for b in at.get("button")}
        assert {"Remove connection", "Test keyring"} <= labels
        assert any("Connect" in label for label in labels)

    def test_remove_connection_asks_first(self, monkeypatch):
        deleted = []
        at = _connections(monkeypatch, SERVER, deleted=deleted)

        _selectbox(at, "Connection to remove").set_value("ipa-training").run()
        _click(at, "Remove connection")

        body = " ".join(w.value for w in at.get("warning"))
        assert "ipa-training" in body
        assert "keyring" in body
        assert deleted == []

    def test_confirmed_removal_deletes_the_saved_credentials(self, monkeypatch):
        deleted = []
        _connections(monkeypatch, SERVER, deleted=deleted)
        at = AppTest.from_function(_remove_connection_app, args=(PROJECT,))
        at.run()
        assert not at.exception, at.exception

        assert deleted == [
            {
                "project_id": PROJECT,
                "server": "ipa-training",
                "credential_type": "scto_login",
            }
        ]

    def test_keyring_problem_is_shown_with_tips(self, monkeypatch):
        at = _connections(
            monkeypatch, {}, keyring={"success": False, "error": "no backend"}
        )

        _click(at, "Test keyring")

        assert any("no backend" in e.value for e in at.get("error"))


def _rows_app(project_id):
    from datasure.utils.dataset_list import build_dataset_list
    from datasure.utils.duckdb_utils import duckdb_get_table
    from datasure.utils.import_ui import render_dataset_row

    log = duckdb_get_table(project_id, "import_log", "logs")
    for row in build_dataset_list(log, {}).rows:
        render_dataset_row(project_id, row, on_edit=print, on_remove=print)


class TestDatasetRow:
    @pytest.fixture
    def rows(self, csv_file):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))
        save_surveycto_dataset(
            PROJECT,
            FormConfig(alias="household", form_id="hh_main", server="ipa-training"),
        )
        at = AppTest.from_function(_rows_app, args=(PROJECT,), default_timeout=30)
        at.run()
        assert not at.exception, at.exception
        return at

    def _toggle(self, at, alias, label):
        return next(
            t
            for t in at.toggle
            if t.label == label and t.key.startswith(f"import_flag_{alias}_")
        )

    def test_media_is_disabled_with_a_reason_for_local_files(self, rows):
        media = self._toggle(rows, "survey", "Media")

        assert media.disabled
        assert "Local files" in media.help
        assert not self._toggle(rows, "household", "Media").disabled

    @pytest.mark.parametrize(
        ("label", "column"),
        [("Refresh", "refresh"), ("Load", "load"), ("Media", "attachments")],
    )
    def test_switches_write_to_the_import_log(self, rows, label, column):
        self._toggle(rows, "household", label).set_value(column == "attachments").run()

        log = _log().filter(pl.col("alias") == "household").to_dicts()[0]
        survey = _log().filter(pl.col("alias") == "survey").to_dicts()[0]
        assert log[column] is (column == "attachments")
        # The other dataset is untouched.
        assert survey["refresh"] is True
