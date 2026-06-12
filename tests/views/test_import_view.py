"""Tests for import_view.py - actual imports with proper mocking."""

import importlib
import sys
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


def _module_patches():
    """Patches required for import_view's module-level code to execute."""
    return (
        patch(
            "datasure.utils.duckdb_utils.duckdb_get_aliases",
            return_value=[],
        ),
        patch(
            "datasure.utils.duckdb_utils.duckdb_get_table",
            return_value=pl.DataFrame(),
        ),
        patch(
            "datasure.utils.duckdb_utils.duckdb_get_imported_datasets",
            return_value=[],
        ),
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
    )


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
            patch.object(import_view, "_add_to_session_state") as mock_add,
        ):
            import_view._process_single_import("test_project", row)

        mock_load.assert_called_once_with("test_project", row)
        mock_add.assert_called_once_with("survey")

    def test_refresh_false_skips_load_but_registers(self):
        row = {"refresh": False, "alias": "survey", "source": "local storage"}
        with (
            patch.object(import_view, "_load_dataset_by_source") as mock_load,
            patch.object(import_view, "_add_to_session_state") as mock_add,
        ):
            import_view._process_single_import("test_project", row)

        mock_load.assert_not_called()
        mock_add.assert_called_once_with("survey")


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

    def test_remove_data_cascades_table_removal(self):
        _st.session_state["st_project_id"] = "test_project"
        orig_button = _st.button
        orig_selectbox = _st.selectbox
        orig_stop = _st.stop

        _st.stop = MagicMock()
        _st.button = MagicMock(
            side_effect=lambda label=None, *a, **k: label == "Remove Data"
        )
        _st.selectbox = MagicMock(
            side_effect=lambda label=None, *a, **k: (
                "stale_data" if label == "Select Data to Remove" else None
            )
        )

        try:
            with (
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
                    side_effect=[True, False],
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
        finally:
            _st.button = orig_button
            _st.selectbox = orig_selectbox

            # Re-import cleanly so later tests see a module bound to
            # default mocks rather than this test's patched state
            _st.session_state["st_project_id"] = "test_project"
            reload_patches = _module_patches()
            for p in reload_patches:
                p.start()
            try:
                importlib.reload(import_view)
            finally:
                for p in reload_patches:
                    p.stop()
            _st.session_state["st_project_id"] = None
            _st.stop = orig_stop


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
