"""Tests for import_view.py - actual imports with proper mocking."""

import importlib
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.connectors.scto import FormConfig

# --- Module import setup ---
# import_view.py is a Streamlit page script: it has module-level UI code and
# guards. Mirror the test_prep_view.py pattern: configure the shared
# streamlit mock so the module can import, and patch data/navigation
# utilities at their source so the module binds mocks instead of real
# implementations.
_st = sys.modules["streamlit"]
_orig_stop = _st.stop


def _make_columns(spec, **_kwargs):
    """Return one context-manager mock per requested column."""
    n = spec if isinstance(spec, int) else len(spec)
    return [MagicMock() for _ in range(n)]


# Let module load past the project guard, and make layout primitives
# context-manager capable (plain Mock cannot be used in a `with` block).
# The layout overrides intentionally stay in place for the whole test
# module: TestRemoveImportFlow reloads import_view and needs them active.
_st.session_state["st_project_id"] = "test_project"
_st.stop = MagicMock()
_st.columns = MagicMock(side_effect=_make_columns)
_st.popover = MagicMock()
_st.container = MagicMock()
_st.status = MagicMock()


def _module_patches(overrides: dict | None = None):
    """Patches required for import_view's module-level code to execute.

    `overrides` maps a patch target below to a replacement kwargs dict (e.g.
    ``{"datasure.utils.onboarding_utils.is_demo_project": {"return_value": True}}``),
    letting tests reuse this baseline while changing just what they need
    instead of repeating the whole patch list.
    """
    overrides = overrides or {}

    def _p(target, **kwargs):
        kwargs.update(overrides.get(target, {}))
        return patch(target, **kwargs)

    return (
        # The "Add Credentials" popover renders the SurveyCTO login form at
        # import; the real form calls st.image on scto's own streamlit binding
        # (which may be the real module if scto was imported by another test
        # package first). Patch the UI class so module import stays in bare mode.
        _p("datasure.connectors.scto.SurveyCTOUI"),
        _p("datasure.connectors.local.load_local_data"),
        _p("datasure.connectors.local.render_local_file_form"),
        _p("datasure.utils.duckdb_utils.duckdb_get_aliases", return_value=[]),
        _p("datasure.utils.duckdb_utils.duckdb_get_table", return_value=pl.DataFrame()),
        _p("datasure.utils.duckdb_utils.duckdb_get_imported_datasets", return_value=[]),
        _p("datasure.utils.duckdb_utils.duckdb_table_exists", return_value=False),
        _p(
            "datasure.utils.secure_credentials.list_stored_credentials",
            return_value={"credentials": {}},
        ),
        _p("datasure.utils.secure_credentials.delete_stored_credentials"),
        _p(
            "datasure.utils.secure_credentials.test_keyring_availability",
            return_value={"success": True, "backend": "mock-backend"},
        ),
        patch("datasure.utils.navigations_utils.page_navigation"),
        patch("datasure.utils.navigations_utils.add_demo_navigation"),
        patch("datasure.utils.navigations_utils.demo_sidebar_help"),
        patch("datasure.utils.navigations_utils.demo_callout"),
        patch("datasure.utils.navigations_utils.show_demo_next_action"),
        _p("datasure.utils.onboarding_utils.is_demo_project", return_value=False),
    )


def _reload_cleanly():
    """Reload import_view under the default baseline patches.

    Used to restore the module to known-good bindings after a test reloads
    it under one-off patches/widget mocks, so later tests aren't affected.
    """
    patches = _module_patches()
    for p in patches:
        p.start()
    try:
        importlib.reload(import_view)
    finally:
        for p in patches:
            p.stop()


@contextmanager
def _reloaded_with(
    overrides=None, button_labels=(), selectbox_map=None, project_id="test_project"
):
    """Reload import_view with baseline patches plus per-test overrides.

    `button_labels` is the set of `st.button()` labels that should return
    True (every other label returns False); `selectbox_map` maps a
    `st.selectbox()` label to the value it should return (unlisted labels
    return None). Because import_view imports its collaborators by name
    (`from x import y`), the mocks these patches install can be read back
    off the reloaded module inside the `with` block, e.g.
    `import_view.render_local_file_form`. Assertions must happen inside the
    block: on exit, the module is reloaded back to its default bindings, so
    anything read afterwards would see fresh, uncalled mocks.
    """
    selectbox_map = selectbox_map or {}
    _st.session_state["st_project_id"] = project_id
    orig_button = _st.button
    orig_selectbox = _st.selectbox
    orig_columns = _st.columns
    orig_popover = _st.popover
    orig_container = _st.container
    orig_status = _st.status
    _st.button = MagicMock(
        side_effect=lambda label=None, *a, **k: label in button_labels
    )
    _st.selectbox = MagicMock(
        side_effect=lambda label=None, *a, **k: selectbox_map.get(label)
    )
    # Other view test modules share this same mocked streamlit module and
    # may leave `columns`/`popover`/`container`/`status` bound to their own
    # (incompatible) mocks after collection, so re-pin them here rather than
    # relying on the module-level defaults set at the top of this file.
    _st.columns = MagicMock(side_effect=_make_columns)
    _st.popover = MagicMock()
    _st.container = MagicMock()
    _st.status = MagicMock()

    patches = _module_patches(overrides)
    for p in patches:
        p.start()
    try:
        importlib.reload(import_view)
        yield import_view
    finally:
        for p in patches:
            p.stop()
        # Restore button/selectbox *before* the cleanup reload so it takes a
        # truly default pass (this test's button_labels/selectbox_map would
        # otherwise route the cleanup reload into these branches too, against
        # the baseline's empty DataFrames). Keep the re-pinned columns/popover/
        # container/status through the cleanup reload though, since the
        # baseline patches don't restore column counts either.
        _st.button = orig_button
        _st.selectbox = orig_selectbox
        _st.session_state["st_project_id"] = "test_project"
        _reload_cleanly()
        _st.session_state["st_project_id"] = None
        _st.columns = orig_columns
        _st.popover = orig_popover
        _st.container = orig_container
        _st.status = orig_status


_patches = _module_patches()
for _p in _patches:
    _p.start()
try:
    # Single import form: module-qualified access also guarantees tests
    # resolve the current bindings after TestRemoveImportFlow reloads
    import datasure.views.import_view as import_view
finally:
    for _p in _patches:
        _p.stop()

# Restore guard state
_st.session_state["st_project_id"] = None
_st.stop = _orig_stop


def _import_log_df(rows: list[dict] | None = None) -> pl.DataFrame:
    """Build an import_log DataFrame with the full column set."""
    base = {
        "refresh": True,
        "load": True,
        "alias": "survey",
        "filename": "C:/data/survey.csv",
        "sheet_name": "",
        "source": "local storage",
        "server": "",
        "username": "",
        "form_id": "",
        "private_key": "",
        "save_to": "",
        "attachments": False,
    }
    rows = rows if rows is not None else [base]
    return pl.DataFrame([{**base, **row} for row in rows])


class TestNoProjectSelected:
    """Test the top-level guard when no project is selected.

    Unlike other module-level tests, this one needs `st.stop()` to actually
    halt the script (the shared mock stubs it to a no-op so the rest of the
    module can execute for every other test), so it swaps in the
    StopIteration-raising version conftest.py normally installs.
    """

    def test_shows_guidance_and_stops(self):
        _st.session_state["st_project_id"] = ""
        orig_stop = _st.stop
        _st.info.reset_mock()
        _st.stop = MagicMock(side_effect=StopIteration)

        patches = _module_patches()
        for p in patches:
            p.start()
        try:
            with pytest.raises(StopIteration):
                importlib.reload(import_view)
            assert _st.info.called
        finally:
            for p in patches:
                p.stop()
            _st.stop = orig_stop
            _st.session_state["st_project_id"] = "test_project"
            _reload_cleanly()
            _st.session_state["st_project_id"] = None


class TestCreateFormConfig:
    """Test _create_form_config row-to-FormConfig conversion."""

    def _row(self, **overrides):
        row = {
            "alias": "svy",
            "form_id": "form_1",
            "server": "myserver",
            "username": "user@example.com",
            "private_key": "",
            "save_to": "",
            "attachments": True,
            "refresh": True,
        }
        row.update(overrides)
        return row

    def test_basic_config(self):
        config = import_view._create_form_config(self._row())

        assert isinstance(config, FormConfig)
        assert config.alias == "svy"
        assert config.form_id == "form_1"
        assert config.server == "myserver"
        assert config.username == "user@example.com"
        assert config.attachments is True
        assert config.refresh is True

    def test_empty_strings_become_none(self):
        config = import_view._create_form_config(
            self._row(username="", private_key="", save_to="")
        )

        assert config.username is None
        assert config.private_key is None
        assert config.save_to is None

    def test_populated_optional_fields_preserved(self):
        config = import_view._create_form_config(
            self._row(private_key="C:/keys/key.pem", save_to="survey_data")
        )

        assert config.private_key == "C:/keys/key.pem"
        assert config.save_to == "survey_data"


class TestGetFilteredImportLog:
    """Test _get_filtered_import_log load-flag filtering."""

    def test_filters_unloaded_rows(self):
        log = _import_log_df(
            [
                {"alias": "a", "load": True},
                {"alias": "b", "load": False},
                {"alias": "c", "load": True},
            ]
        )
        with patch.object(import_view, "duckdb_get_table", return_value=log):
            result = import_view._get_filtered_import_log("test_project")

        assert result["alias"].to_list() == ["a", "c"]

    def test_reads_import_log_from_logs_db(self):
        with patch.object(
            import_view, "duckdb_get_table", return_value=_import_log_df()
        ) as mock_get:
            import_view._get_filtered_import_log("test_project")

        mock_get.assert_called_once_with(
            project_id="test_project", alias="import_log", db_name="logs"
        )


class TestLoadRawDatasets:
    """Test the load_raw_datasets orchestration."""

    def test_empty_log_shows_error(self):
        with (
            patch.object(
                import_view,
                "_get_filtered_import_log",
                return_value=pl.DataFrame(),
            ),
            patch.object(import_view, "_process_import_log") as mock_process,
        ):
            import_view.load_raw_datasets("test_project")

        _st.error.assert_called()
        mock_process.assert_not_called()

    def test_nonempty_log_is_processed(self):
        log = _import_log_df()
        with (
            patch.object(import_view, "_get_filtered_import_log", return_value=log),
            patch.object(import_view, "_process_import_log") as mock_process,
        ):
            import_view.load_raw_datasets("test_project")

        mock_process.assert_called_once_with("test_project", log)


class TestProcessImportLog:
    """Test per-row processing with status updates."""

    def test_processes_each_row(self):
        log = _import_log_df([{"alias": "a"}, {"alias": "b"}])
        with patch.object(import_view, "_process_single_import") as mock_single:
            import_view._process_import_log("test_project", log)

        assert mock_single.call_count == 2
        processed_aliases = [
            call.args[1]["alias"] for call in mock_single.call_args_list
        ]
        assert processed_aliases == ["a", "b"]


class TestProcessSingleImport:
    """Test the refresh gate and session-state registration."""

    def test_refresh_true_loads_dataset(self):
        row = {"refresh": True, "alias": "survey", "source": "local storage"}
        with (
            patch.object(import_view, "_load_dataset_by_source") as mock_load,
            patch.object(import_view, "_refresh_downstream_data") as mock_refresh,
            patch.object(import_view, "_add_to_session_state") as mock_add,
        ):
            import_view._process_single_import("test_project", row)

        mock_load.assert_called_once_with("test_project", row)
        mock_refresh.assert_called_once_with("test_project", "survey")
        mock_add.assert_called_once_with("survey")

    def test_refresh_false_skips_load_but_registers(self):
        row = {"refresh": False, "alias": "survey", "source": "local storage"}
        with (
            patch.object(import_view, "_load_dataset_by_source") as mock_load,
            patch.object(import_view, "_refresh_downstream_data") as mock_refresh,
            patch.object(import_view, "_add_to_session_state") as mock_add,
        ):
            import_view._process_single_import("test_project", row)

        mock_load.assert_not_called()
        mock_refresh.assert_not_called()
        mock_add.assert_called_once_with("survey")


class TestRefreshDownstreamData:
    """Test that a raw refresh rebuilds prep/corrected data when present."""

    def test_rebuilds_prep_and_corrected_when_both_exist(self):
        with (
            patch.object(
                import_view, "duckdb_table_exists", return_value=True
            ) as mock_exists,
            patch.object(import_view, "prep_apply_action") as mock_prep_apply,
            patch.object(import_view, "CorrectionProcessor") as mock_processor_cls,
        ):
            import_view._refresh_downstream_data("test_project", "survey")

        assert mock_exists.call_count == 2
        mock_prep_apply.assert_called_once_with("test_project", "survey")
        mock_processor_cls.assert_called_once_with("test_project")
        mock_processor_cls.return_value.refresh_corrected_data.assert_called_once_with(
            "survey"
        )

    def test_skips_when_neither_prep_nor_corrected_exist(self):
        with (
            patch.object(import_view, "duckdb_table_exists", return_value=False),
            patch.object(import_view, "prep_apply_action") as mock_prep_apply,
            patch.object(import_view, "CorrectionProcessor") as mock_processor_cls,
        ):
            import_view._refresh_downstream_data("test_project", "survey")

        mock_prep_apply.assert_not_called()
        mock_processor_cls.assert_not_called()


class TestLoadDatasetBySource:
    """Test source dispatch."""

    def test_local_storage_dispatch(self):
        row = {"source": "local storage"}
        with (
            patch.object(import_view, "_load_from_local_storage") as mock_local,
            patch.object(import_view, "_load_from_surveycto") as mock_scto,
        ):
            import_view._load_dataset_by_source("test_project", row)

        mock_local.assert_called_once_with("test_project", row)
        mock_scto.assert_not_called()

    def test_surveycto_dispatch(self):
        row = {"source": "SurveyCTO"}
        with (
            patch.object(import_view, "_load_from_local_storage") as mock_local,
            patch.object(import_view, "_load_from_surveycto") as mock_scto,
        ):
            import_view._load_dataset_by_source("test_project", row)

        mock_scto.assert_called_once_with("test_project", row)
        mock_local.assert_not_called()

    def test_unknown_source_is_noop(self):
        row = {"source": "ftp"}
        with (
            patch.object(import_view, "_load_from_local_storage") as mock_local,
            patch.object(import_view, "_load_from_surveycto") as mock_scto,
        ):
            import_view._load_dataset_by_source("test_project", row)

        mock_local.assert_not_called()
        mock_scto.assert_not_called()


class TestLoadFromSurveycto:
    """Test SurveyCTO download invocation."""

    def test_downloads_with_form_config(self):
        row = {
            "alias": "svy",
            "form_id": "form_1",
            "server": "myserver",
            "username": "user@example.com",
            "private_key": "",
            "save_to": "",
            "attachments": False,
            "refresh": True,
        }
        with patch.object(import_view, "download_forms") as mock_download:
            import_view._load_from_surveycto("test_project", row)

        mock_download.assert_called_once()
        kwargs = mock_download.call_args.kwargs
        assert kwargs["project_id"] == "test_project"
        configs = kwargs["form_configs"]
        assert len(configs) == 1
        assert isinstance(configs[0], FormConfig)
        assert configs[0].form_id == "form_1"


class TestLoadFromLocalStorage:
    """Test local-storage load dispatch."""

    def test_loads_with_expected_args(self):
        row = {
            "alias": "svy",
            "filename": "C:/data/survey.csv",
            "sheet_name": "Sheet1",
        }
        with patch.object(import_view, "load_local_data") as mock_load:
            import_view._load_from_local_storage("test_project", row)

        mock_load.assert_called_once_with(
            project_id="test_project",
            alias="svy",
            filename="C:/data/survey.csv",
            sheet_name="Sheet1",
        )

    def test_blank_sheet_name_becomes_none(self):
        row = {"alias": "svy", "filename": "C:/data/survey.csv", "sheet_name": ""}
        with patch.object(import_view, "load_local_data") as mock_load:
            import_view._load_from_local_storage("test_project", row)

        assert mock_load.call_args.kwargs["sheet_name"] is None


class TestAddToSessionState:
    """Test session-state dataset registration."""

    def test_new_alias_appended(self):
        _st.session_state.st_raw_dataset_list = []

        import_view._add_to_session_state("survey")

        assert _st.session_state.st_raw_dataset_list == ["survey"]

    def test_existing_alias_not_duplicated(self):
        _st.session_state.st_raw_dataset_list = ["survey"]

        import_view._add_to_session_state("survey")

        assert _st.session_state.st_raw_dataset_list == ["survey"]

    def test_new_alias_in_demo_project_shows_callout(self):
        _st.session_state.st_raw_dataset_list = []

        with (
            patch.object(import_view, "is_demo_project", return_value=True),
            patch.object(import_view, "demo_callout") as mock_callout,
        ):
            import_view._add_to_session_state("demo_survey")

        assert _st.session_state.st_raw_dataset_list == ["demo_survey"]
        mock_callout.assert_called_once()


class TestUpdateImportLog:
    """Test the import-log data editor save flow."""

    def test_saves_edited_log_when_refresh_triggered(self):
        log = _import_log_df()
        edited = log.with_columns(pl.lit(False).alias("refresh"))
        _st.session_state["refresh_import_log"] = True

        with (
            patch.object(_st, "data_editor", return_value=edited),
            patch.object(import_view, "duckdb_save_table") as mock_save,
        ):
            import_view.update_import_log(log)

        mock_save.assert_called_once()
        kwargs = mock_save.call_args.kwargs
        assert kwargs["alias"] == "import_log"
        assert kwargs["db_name"] == "logs"
        assert kwargs["table_data"].equals(edited)
        # The trigger flag is reset after saving
        assert _st.session_state["refresh_import_log"] is False

    def test_no_save_without_refresh_trigger(self):
        log = _import_log_df()
        with (
            patch.object(_st, "data_editor", return_value=log),
            patch.object(import_view, "duckdb_save_table") as mock_save,
        ):
            import_view.update_import_log(log)

        mock_save.assert_not_called()


class TestRemoveImportFlow:
    """Test the module-level remove-import-configuration flow.

    The flow is top-level Streamlit code, so it is exercised by reloading
    the module with the Remove Data button returning True. The row-removal
    helper is patched under both its old (duckdb_row_filter) and new
    (duckdb_delete_rows) names with create=True so this test passes on
    either side of the PR #179 rename.
    """

    def _run_remove_flow(self, table_exists_side_effect):
        """Reload the module through the Remove Data -> confirm cascade.

        Returns the (mock_remove, mock_exists, mock_row_filter,
        mock_delete_rows) mocks so callers can assert on the cascade.
        """
        _st.session_state["st_project_id"] = "test_project"
        orig_button = _st.button
        orig_selectbox = _st.selectbox
        orig_stop = _st.stop
        orig_dialog = _st.dialog
        orig_columns = _st.columns

        _st.stop = MagicMock()
        # The removal is guarded by confirm_dialog: clicking "Remove Data"
        # opens the modal, whose "Remove" button runs the cascade. Return True
        # for both so the whole flow executes in one reload pass.
        _st.button = MagicMock(
            side_effect=lambda label=None, *a, **k: label in ("Remove Data", "Remove")
        )
        _st.selectbox = MagicMock(
            side_effect=lambda label=None, *a, **k: (
                "stale_data" if label == "Select Data to Remove" else None
            )
        )
        # Make @st.dialog(title) a no-op decorator so the dialog body runs, and
        # return one column per requested slot (confirm_dialog needs 2, the
        # action row needs 3) regardless of leaked state from other view tests.
        _st.dialog = MagicMock(side_effect=lambda *a, **k: lambda fn: fn)
        _st.columns = MagicMock(side_effect=_make_columns)

        try:
            with (
                patch("datasure.connectors.scto.SurveyCTOUI"),
                patch(
                    "datasure.utils.duckdb_utils.duckdb_get_aliases",
                    return_value=["stale_data"],
                ),
                patch(
                    "datasure.utils.duckdb_utils.duckdb_get_table",
                    return_value=pl.DataFrame(),
                ),
                patch(
                    "datasure.utils.duckdb_utils.duckdb_get_imported_datasets",
                    return_value=[],
                ),
                patch("datasure.utils.duckdb_utils.duckdb_remove_table") as mock_remove,
                patch(
                    "datasure.utils.duckdb_utils.duckdb_table_exists",
                    side_effect=table_exists_side_effect,
                ) as mock_exists,
                patch(
                    "datasure.utils.duckdb_utils.duckdb_row_filter",
                    create=True,
                ) as mock_row_filter,
                patch(
                    "datasure.utils.duckdb_utils.duckdb_delete_rows",
                    create=True,
                ) as mock_delete_rows,
                patch(
                    "datasure.utils.secure_credentials.list_stored_credentials",
                    return_value={"credentials": {}},
                ),
                patch("datasure.utils.navigations_utils.page_navigation"),
                patch("datasure.utils.navigations_utils.add_demo_navigation"),
                patch("datasure.utils.navigations_utils.demo_sidebar_help"),
                patch("datasure.utils.navigations_utils.demo_callout"),
                patch("datasure.utils.navigations_utils.show_demo_next_action"),
                patch(
                    "datasure.utils.onboarding_utils.is_demo_project",
                    return_value=False,
                ),
            ):
                importlib.reload(import_view)

            return mock_remove, mock_exists, mock_row_filter, mock_delete_rows
        finally:
            # Restore button/selectbox/dialog *before* the cleanup reload so
            # it takes a truly default pass (this test's mocks would
            # otherwise route the cleanup reload into the same remove-data
            # cascade, against the baseline's unpatched duckdb functions).
            # Columns stays pinned through cleanup since the baseline
            # patches don't restore column counts either.
            _st.button = orig_button
            _st.selectbox = orig_selectbox
            _st.dialog = orig_dialog

            _st.session_state["st_project_id"] = "test_project"
            _reload_cleanly()
            _st.session_state["st_project_id"] = None
            _st.columns = orig_columns
            _st.stop = orig_stop

    def test_remove_data_cascades_table_removal(self):
        mock_remove, mock_exists, mock_row_filter, mock_delete_rows = (
            self._run_remove_flow([True, False])
        )

        # The import_log row for the alias is removed (either helper)
        assert mock_row_filter.called or mock_delete_rows.called

        # The raw table is removed, plus the prep table (exists=True);
        # the corrected table does not exist so it is left alone
        removed = [
            (call.kwargs.get("alias"), call.kwargs.get("db_name"))
            for call in mock_remove.call_args_list
        ]
        assert ("stale_data", "raw") in removed
        assert ("stale_data", "prep") in removed
        assert ("stale_data", "corrected") not in removed
        assert mock_exists.call_count == 2

    def test_remove_data_also_removes_corrected_when_present(self):
        mock_remove, mock_exists, _, _ = self._run_remove_flow([True, True])

        removed = [
            (call.kwargs.get("alias"), call.kwargs.get("db_name"))
            for call in mock_remove.call_args_list
        ]
        assert ("stale_data", "raw") in removed
        assert ("stale_data", "prep") in removed
        assert ("stale_data", "corrected") in removed
        assert mock_exists.call_count == 2

    def test_remove_data_skips_prep_and_corrected_when_absent(self):
        mock_remove, mock_exists, _, _ = self._run_remove_flow([False, False])

        removed = [
            (call.kwargs.get("alias"), call.kwargs.get("db_name"))
            for call in mock_remove.call_args_list
        ]
        assert ("stale_data", "raw") in removed
        assert ("stale_data", "prep") not in removed
        assert ("stale_data", "corrected") not in removed
        assert mock_exists.call_count == 2


_SAVED_CREDENTIALS_OVERRIDE = {
    "return_value": {
        "credentials": {"Test Cred": {"server": "srv", "type": "surveycto"}}
    }
}


class TestCredentialsSection:
    """Test the Manage Credentials section: delete and keyring diagnostics."""

    def test_delete_credentials_button(self):
        with _reloaded_with(
            overrides={
                "datasure.utils.secure_credentials.list_stored_credentials": (
                    _SAVED_CREDENTIALS_OVERRIDE
                ),
            },
            button_labels={"Delete Credentials"},
            selectbox_map={"Select Crendetials to Deleted": "Test Cred"},
        ) as iv:
            iv.delete_stored_credentials.assert_called_once()

    def test_keyring_diagnostics_success(self):
        _st.success.reset_mock()
        with _reloaded_with(
            overrides={
                "datasure.utils.secure_credentials.test_keyring_availability": {
                    "return_value": {
                        "success": True,
                        "backend": "Windows",
                        "message": "Keyring backend is functional.",
                    }
                },
            },
            button_labels={"Test Keyring Availability"},
        ):
            assert _st.success.called

    def test_keyring_diagnostics_failure(self):
        _st.error.reset_mock()
        with _reloaded_with(
            overrides={
                "datasure.utils.secure_credentials.test_keyring_availability": {
                    "return_value": {"success": False, "error": "no backend"}
                },
            },
            button_labels={"Test Keyring Availability"},
        ):
            assert _st.error.called


class TestImportConfigurationFlow:
    """Test the Add/Edit Import Configuration popovers."""

    def test_add_local_storage_form(self):
        with _reloaded_with(
            overrides={
                "datasure.utils.duckdb_utils.duckdb_get_aliases": {
                    "return_value": ["survey"]
                },
            },
            selectbox_map={"Import Type": "local storage"},
        ) as iv:
            iv.render_local_file_form.assert_called_once_with("test_project")

    def test_add_surveycto_form(self):
        with _reloaded_with(selectbox_map={"Import Type": "SurveyCTO"}) as iv:
            iv.SurveyCTOUI.return_value.render_form_config.assert_called_once_with()

    def test_edit_local_storage_form(self):
        log = _import_log_df([{"alias": "survey", "source": "local storage"}])
        with _reloaded_with(
            overrides={
                "datasure.utils.duckdb_utils.duckdb_get_aliases": {
                    "return_value": ["survey"]
                },
                "datasure.utils.duckdb_utils.duckdb_get_table": {"return_value": log},
            },
            selectbox_map={"Select Data to Edit": "survey"},
        ) as iv:
            iv.render_local_file_form.assert_called_once_with(
                "test_project", edit_mode=True, defaults=log.to_dicts()[0]
            )

    def test_edit_surveycto_form(self):
        log = _import_log_df([{"alias": "survey", "source": "SurveyCTO"}])
        with _reloaded_with(
            overrides={
                "datasure.utils.duckdb_utils.duckdb_get_aliases": {
                    "return_value": ["survey"]
                },
                "datasure.utils.duckdb_utils.duckdb_get_table": {"return_value": log},
            },
            selectbox_map={"Select Data to Edit": "survey"},
        ) as iv:
            iv.SurveyCTOUI.return_value.render_form_config.assert_called_once_with(
                edit_mode=True, defaults=log.to_dicts()[0]
            )

    def test_edit_invalid_source_shows_error(self):
        log = _import_log_df([{"alias": "survey", "source": "unknown"}])
        _st.error.reset_mock()
        with _reloaded_with(
            overrides={
                "datasure.utils.duckdb_utils.duckdb_get_aliases": {
                    "return_value": ["survey"]
                },
                "datasure.utils.duckdb_utils.duckdb_get_table": {"return_value": log},
            },
            selectbox_map={"Select Data to Edit": "survey"},
        ):
            assert _st.error.called


def _fake_get_table_for(
    log: pl.DataFrame, preview_df: pl.DataFrame, preview_alias: str
):
    """Build a duckdb_get_table side_effect dispatching by alias."""

    def _fake_get_table(*args, alias=None, **kwargs):
        if alias == "import_log":
            return log
        if alias == preview_alias:
            return preview_df
        return pl.DataFrame()

    return _fake_get_table


class TestLoadAndPreviewFlow:
    """Test the main load-data / preview-data module-level flow."""

    def test_full_flow_in_demo_project(self):
        log = _import_log_df()  # alias="survey", refresh=True, load=True
        preview_df = pl.DataFrame({"a": [1, 2, None], "b": [4, None, 6]})
        _st.dataframe.reset_mock()

        with _reloaded_with(
            overrides={
                "datasure.utils.duckdb_utils.duckdb_get_table": {
                    "side_effect": _fake_get_table_for(log, preview_df, "survey")
                },
                "datasure.utils.duckdb_utils.duckdb_get_aliases": {
                    "return_value": ["existing_alias"]
                },
                "datasure.utils.duckdb_utils.duckdb_get_imported_datasets": {
                    "return_value": ["survey"]
                },
                "datasure.utils.onboarding_utils.is_demo_project": {
                    "return_value": True
                },
            },
            button_labels={"Load Data"},
            selectbox_map={"Select Dataset": "survey"},
            project_id=import_view.DEMO_PROJECT_ID,
        ):
            # Demo datasets are folded into the raw dataset list on first
            # load, alongside the alias the (mocked) import just loaded.
            raw_list = _st.session_state.st_raw_dataset_list
            assert "demo_survey" in raw_list
            assert "demo_backcheck" in raw_list
            assert "survey" in raw_list
            # Load Data -> preview options are stashed for the Prep page.
            assert _st.session_state.st_prep_dataset_list == ["survey"]
            # The preview section rendered metrics from the fetched raw data.
            assert _st.dataframe.called

    def test_full_flow_in_non_demo_project(self):
        """Same flow outside the demo project, to cover the non-demo branches
        of the preview section (no guidance callout, no next-action button).
        """
        log = _import_log_df()
        preview_df = pl.DataFrame({"a": [1, 2, None], "b": [4, None, 6]})
        _st.dataframe.reset_mock()

        with _reloaded_with(
            overrides={
                "datasure.utils.duckdb_utils.duckdb_get_table": {
                    "side_effect": _fake_get_table_for(log, preview_df, "survey")
                },
                "datasure.utils.duckdb_utils.duckdb_get_imported_datasets": {
                    "return_value": ["survey"]
                },
            },
            button_labels={"Load Data"},
            selectbox_map={"Select Dataset": "survey"},
        ):
            assert _st.session_state.st_prep_dataset_list == ["survey"]
            assert _st.dataframe.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
