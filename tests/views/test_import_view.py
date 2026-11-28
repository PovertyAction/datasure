"""Tests for import_view.py - actual imports with proper mocking."""

import importlib
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.connectors.scto import FormConfig, FormDefinitionNotSavedError
from datasure.utils.reapply_utils import ReapplyFailure

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
_st.tabs = MagicMock(return_value=[MagicMock(), MagicMock()])


class _Rerun(BaseException):
    """Raised by the mocked ``st.rerun()``: the real one ends the run."""


_LOAD_RUNNING_KEY = "st_import_running"
_LOAD_OUTCOME_KEY = "import_load_outcome"


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
        _p("datasure.connectors.local.import_local_file", return_value=3),
        _p("datasure.connectors.scto.SurveyCTOClient"),
        _p("datasure.utils.duckdb_utils.duckdb_row_counts", return_value={}),
        _p("datasure.utils.duckdb_utils.duckdb_get_aliases", return_value=[]),
        _p("datasure.utils.duckdb_utils.duckdb_get_table", return_value=pl.DataFrame()),
        _p("datasure.utils.duckdb_utils.duckdb_get_imported_datasets", return_value=[]),
        _p("datasure.utils.duckdb_utils.duckdb_table_exists", return_value=False),
        # The corrections module is not reloaded, so it keeps its own binding.
        _p("datasure.processing.corrections.duckdb_table_exists", return_value=False),
        _p("datasure.utils.import_log.get_load_info", return_value={}),
        _p("datasure.utils.import_log.record_load"),
        # Connections, rows and dialogs are covered by AppTest in
        # tests/utils/test_import_ui.py; here they only need to be called.
        _p("datasure.utils.import_ui.render_connections"),
        _p("datasure.utils.import_ui.render_dataset_row"),
        _p("datasure.utils.import_ui.project_name", return_value="Test project"),
        _p("datasure.utils.import_ui.open_add_dialog"),
        _p("datasure.utils.import_ui.open_edit_dialog"),
        _p("datasure.utils.import_ui.open_remove_dialog"),
        _p("datasure.utils.import_log.dataset_entry"),
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
    overrides=None,
    button_labels=(),
    selectbox_map=None,
    project_id="test_project",
    loading=False,
):
    """Reload import_view with baseline patches plus per-test overrides.

    `button_labels` is the set of `st.button()` labels that should return
    True (every other label returns False); `selectbox_map` maps a
    `st.selectbox()` label to the value it should return (unlisted labels
    return None). Because import_view imports its collaborators by name
    (`from x import y`), the mocks these patches install can be read back
    off the reloaded module inside the `with` block, e.g.
    `import_view.open_add_dialog`. Assertions must happen inside the
    block: on exit, the module is reloaded back to its default bindings, so
    anything read afterwards would see fresh, uncalled mocks.

    With `loading`, the page runs as if Load data was just clicked: the load
    runs under the lock and ends in ``st.rerun()``, which here raises
    `_Rerun` and is swallowed, so the ``with`` body is skipped. Read the
    outcome from session state, or from mocks passed in `overrides`, after
    the block.
    """
    selectbox_map = selectbox_map or {}
    _st.session_state["st_project_id"] = project_id
    orig_button = _st.button
    orig_selectbox = _st.selectbox
    orig_columns = _st.columns
    orig_popover = _st.popover
    orig_container = _st.container
    orig_status = _st.status
    orig_tabs = _st.tabs
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
    _st.tabs = MagicMock(return_value=[MagicMock(), MagicMock()])

    orig_rerun = _st.rerun
    _st.rerun = MagicMock(side_effect=_Rerun)
    _st.session_state[_LOAD_RUNNING_KEY] = loading
    _st.session_state.pop(_LOAD_OUTCOME_KEY, None)

    patches = _module_patches(overrides)
    for p in patches:
        p.start()
    try:
        try:
            importlib.reload(import_view)
        except _Rerun:
            if not loading:
                raise
            reran = True
        else:
            reran = False
        if reran:
            yield None
        else:
            if loading:
                pytest.fail("a locked load must end in st.rerun()")
            yield import_view
    finally:
        _st.rerun = orig_rerun
        _st.session_state[_LOAD_RUNNING_KEY] = False
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
        _st.tabs = orig_tabs


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


# import_view imports utils/import_ui and utils/import_log. Imported here,
# they bind this file's mock streamlit (import_ui's @st.dialog runs at import)
# and the patched DuckDB helpers. Drop them so the AppTest and DuckDB tests in
# tests/utils import them again with the real ones.
_PAGE_HELPERS = ("datasure.utils.import_ui", "datasure.utils.import_log")


def _forget_page_helpers():
    for name in _PAGE_HELPERS:
        sys.modules.pop(name, None)


_forget_page_helpers()


@pytest.fixture(autouse=True)
def _forget_mock_bound_helpers():
    """Drop the helpers after each test, as reloading import_view re-imports them."""
    yield
    _forget_page_helpers()


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

    def test_empty_log_loads_nothing(self):
        with (
            patch.object(
                import_view,
                "_get_filtered_import_log",
                return_value=pl.DataFrame(),
            ),
            patch.object(import_view, "_process_import_log") as mock_process,
        ):
            outcome = import_view.load_raw_datasets("test_project")

        assert outcome == ([], [])
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
    """Loading every dataset marked Load, with one status line each."""

    def _results(self, *aliases, failed=()):
        from datasure.utils.dataset_list import LoadResult

        return [
            (
                LoadResult(
                    alias=a,
                    source="local storage",
                    refreshed=True,
                    error="boom" if a in failed else None,
                    rows=None if a in failed else 3,
                ),
                [],
            )
            for a in aliases
        ]

    def test_processes_each_row_and_returns_their_results(self):
        log = _import_log_df([{"alias": "a"}, {"alias": "b"}])
        with patch.object(
            import_view,
            "_process_single_import",
            side_effect=self._results("a", "b"),
        ) as mock_single:
            results, _failures = import_view._process_import_log("test_project", log)

        processed = [call.args[1]["alias"] for call in mock_single.call_args_list]
        assert processed == ["a", "b"]
        assert [r.alias for r in results] == ["a", "b"]

    def test_status_ends_complete_when_every_dataset_loaded(self):
        log = _import_log_df([{"alias": "a"}, {"alias": "b"}])
        _st.status.reset_mock()
        with patch.object(
            import_view,
            "_process_single_import",
            side_effect=self._results("a", "b"),
        ):
            import_view._process_import_log("test_project", log)

        status = _st.status.return_value.__enter__.return_value
        final = status.update.call_args.kwargs
        assert final == {
            "label": "Loaded 2 datasets",
            "state": "complete",
            "expanded": False,
        }

    def test_status_ends_in_error_and_stays_open_when_one_failed(self):
        log = _import_log_df([{"alias": "a"}, {"alias": "b"}])
        _st.status.reset_mock()
        with patch.object(
            import_view,
            "_process_single_import",
            side_effect=self._results("a", "b", failed={"b"}),
        ):
            import_view._process_import_log("test_project", log)

        status = _st.status.return_value.__enter__.return_value
        final = status.update.call_args.kwargs
        assert final == {
            "label": "Loaded 1 of 2 datasets · 1 failed",
            "state": "error",
            "expanded": True,
        }


class TestProcessSingleImport:
    """One dataset's load: the refresh gate, failures and its result."""

    def test_refresh_true_loads_dataset(self):
        row = {"refresh": True, "alias": "survey", "source": "local storage"}
        with (
            patch.object(
                import_view, "_load_dataset_by_source", return_value=3
            ) as mock_load,
            patch.object(
                import_view, "_refresh_downstream_data", return_value=[]
            ) as mock_refresh,
            patch.object(import_view, "_add_to_session_state") as mock_add,
            patch.object(import_view, "duckdb_row_counts", return_value={"survey": 3}),
        ):
            result, failures = import_view._process_single_import("test_project", row)

        mock_load.assert_called_once_with("test_project", row)
        mock_refresh.assert_called_once_with("test_project", "survey")
        mock_add.assert_called_once_with("survey")
        assert (result.ok, result.refreshed, result.rows) == (True, True, 3)
        assert failures == []

    def test_refresh_false_skips_load_but_registers(self):
        row = {"refresh": False, "alias": "survey", "source": "local storage"}
        with (
            patch.object(import_view, "_load_dataset_by_source") as mock_load,
            patch.object(import_view, "_refresh_downstream_data") as mock_refresh,
            patch.object(import_view, "_add_to_session_state") as mock_add,
        ):
            result, _ = import_view._process_single_import("test_project", row)

        mock_load.assert_not_called()
        mock_refresh.assert_not_called()
        mock_add.assert_called_once_with("survey")
        assert result.refreshed is False

    def test_a_failed_load_is_reported_not_raised_and_skips_reapplying(self):
        row = {"refresh": True, "alias": "survey", "source": "SurveyCTO"}
        with (
            patch.object(
                import_view,
                "_load_dataset_by_source",
                side_effect=ConnectionError("couldn't sign in"),
            ),
            patch.object(import_view, "_refresh_downstream_data") as mock_refresh,
            patch.object(import_view, "_record_load") as mock_record,
            patch.object(import_view, "_add_to_session_state"),
        ):
            result, failures = import_view._process_single_import("test_project", row)

        assert result.ok is False
        assert result.error == "couldn't sign in"
        mock_refresh.assert_not_called()
        mock_record.assert_not_called()
        assert failures == []

    def test_a_definition_not_saved_still_rebuilds_and_is_flagged(self):
        row = {"refresh": True, "alias": "survey", "source": "SurveyCTO"}
        with (
            patch.object(
                import_view,
                "_load_dataset_by_source",
                side_effect=FormDefinitionNotSavedError("definition not saved", 7),
            ),
            patch.object(
                import_view, "_refresh_downstream_data", return_value=[]
            ) as mock_refresh,
            patch.object(import_view, "_record_load") as mock_record,
            patch.object(import_view, "_add_to_session_state"),
            patch.object(import_view, "duckdb_row_counts", return_value={"survey": 9}),
        ):
            result, _ = import_view._process_single_import("test_project", row)

        # Raw holds the new data, so it counts as loaded and downstream follows.
        assert result.ok is True
        assert (result.rows, result.new_rows) == (9, 7)
        assert result.problems == ("definition not saved",)
        mock_record.assert_called_once_with("test_project", "survey")
        mock_refresh.assert_called_once_with("test_project", "survey")

    @pytest.mark.parametrize("failing", ["_record_load", "_refresh_downstream_data"])
    def test_a_failure_after_the_raw_import_is_flagged_not_raised(self, failing):
        row = {"refresh": True, "alias": "survey", "source": "local storage"}
        with (
            patch.object(import_view, "_load_dataset_by_source", return_value=3),
            patch.object(import_view, "_record_load"),
            patch.object(import_view, "_refresh_downstream_data", return_value=[]),
            patch.object(import_view, failing, side_effect=OSError("disk full")),
            patch.object(import_view, "_add_to_session_state"),
            patch.object(import_view, "duckdb_row_counts", return_value={"survey": 3}),
        ):
            result, failures = import_view._process_single_import("test_project", row)

        assert result.ok is True
        assert result.problems == ("prep and corrections not rebuilt: disk full",)
        assert failures == []

    def test_an_unreadable_row_count_is_left_blank(self):
        row = {"refresh": False, "alias": "survey", "source": "local storage"}
        with (
            patch.object(import_view, "_add_to_session_state"),
            patch.object(
                import_view, "duckdb_row_counts", side_effect=OSError("locked")
            ),
        ):
            result, _ = import_view._process_single_import("test_project", row)

        assert result.rows is None

    def test_surveycto_result_counts_new_rows(self):
        row = {"refresh": True, "alias": "survey", "source": "SurveyCTO"}
        with (
            patch.object(import_view, "_load_dataset_by_source", return_value=38),
            patch.object(import_view, "_refresh_downstream_data", return_value=[]),
            patch.object(import_view, "_add_to_session_state"),
            patch.object(
                import_view, "duckdb_row_counts", return_value={"survey": 1284}
            ),
        ):
            result, _ = import_view._process_single_import("test_project", row)

        assert (result.rows, result.new_rows) == (1284, 38)

    def test_reports_each_stage(self):
        row = {"refresh": True, "alias": "survey", "source": "SurveyCTO"}
        stages = []
        with (
            patch.object(import_view, "_load_dataset_by_source", return_value=1),
            patch.object(import_view, "_refresh_downstream_data", return_value=[]),
            patch.object(import_view, "_add_to_session_state"),
        ):
            import_view._process_single_import("test_project", row, stages.append)

        assert stages == [
            "downloading from SurveyCTO",
            "reapplying prep and corrections",
        ]

    def test_demo_rows_are_not_refreshed(self):
        row = {"refresh": True, "alias": "demo_survey", "source": "Demo Data"}
        with (
            patch.object(import_view, "_load_dataset_by_source") as mock_load,
            patch.object(import_view, "_add_to_session_state"),
        ):
            result, _ = import_view._process_single_import("test_project", row)

        mock_load.assert_not_called()
        assert result.refreshed is False


class TestRefreshDownstreamData:
    """Test that a raw refresh rebuilds prep/corrected data when present."""

    def test_rebuilds_prep_and_replays_corrections_when_prep_exists(self):
        with (
            patch.object(import_view, "duckdb_table_exists", return_value=True),
            patch.object(import_view, "prep_apply_action") as mock_prep_apply,
            patch.object(import_view, "CorrectionProcessor") as mock_processor_cls,
        ):
            import_view._refresh_downstream_data("test_project", "survey")

        mock_prep_apply.assert_called_once_with("test_project", "survey")
        mock_processor_cls.assert_called_once_with("test_project")
        processor = mock_processor_cls.return_value
        processor.refresh_existing_corrected_data.assert_called_once_with("survey")

    def test_skips_prep_rebuild_when_prep_does_not_exist(self):
        with (
            patch.object(import_view, "duckdb_table_exists", return_value=False),
            patch.object(import_view, "prep_apply_action") as mock_prep_apply,
            patch.object(import_view, "CorrectionProcessor") as mock_processor_cls,
        ):
            import_view._refresh_downstream_data("test_project", "survey")

        mock_prep_apply.assert_not_called()
        processor = mock_processor_cls.return_value
        processor.refresh_existing_corrected_data.assert_called_once_with("survey")

    def test_returns_prep_and_correction_failures(self):
        prep_failure = ReapplyFailure("drop age", "column missing")
        correction_failure = ReapplyFailure("modify name", "column missing")
        with (
            patch.object(import_view, "duckdb_table_exists", return_value=True),
            patch.object(import_view, "prep_apply_action", return_value=[prep_failure]),
            patch.object(import_view, "CorrectionProcessor") as mock_processor_cls,
        ):
            processor = mock_processor_cls.return_value
            processor.refresh_existing_corrected_data.return_value = [
                correction_failure
            ]
            failures = import_view._refresh_downstream_data("test_project", "survey")

        assert failures == [prep_failure, correction_failure]


class TestLoadDatasetBySource:
    """Test source dispatch."""

    def test_local_storage_dispatch(self):
        row = {"source": "local storage"}
        local, scto = MagicMock(return_value=3), MagicMock()
        loaders = {"local storage": local, "SurveyCTO": scto}
        with patch.dict(import_view._LOADERS, loaders):
            assert import_view._load_dataset_by_source("test_project", row) == 3

        local.assert_called_once_with("test_project", row)
        scto.assert_not_called()

    def test_surveycto_dispatch(self):
        row = {"source": "SurveyCTO"}
        local, scto = MagicMock(), MagicMock(return_value=38)
        loaders = {"local storage": local, "SurveyCTO": scto}
        with patch.dict(import_view._LOADERS, loaders):
            assert import_view._load_dataset_by_source("test_project", row) == 38

        scto.assert_called_once_with("test_project", row)
        local.assert_not_called()

    def test_unknown_source_is_noop(self):
        assert (
            import_view._load_dataset_by_source("test_project", {"source": "ftp"})
            is None
        )


class TestLoadFromSurveycto:
    """Test SurveyCTO download invocation."""

    def test_imports_with_form_config_and_returns_new_rows(self):
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
        with patch.object(import_view, "SurveyCTOClient") as mock_client:
            mock_client.return_value.import_data.return_value = 38
            new_rows = import_view._load_from_surveycto("test_project", row)

        assert new_rows == 38
        mock_client.assert_called_once_with("test_project")
        (config,) = mock_client.return_value.import_data.call_args.args
        assert isinstance(config, FormConfig)
        assert config.form_id == "form_1"


class TestLoadFromLocalStorage:
    """Test local-storage load dispatch."""

    def test_loads_with_expected_args(self):
        row = {
            "alias": "svy",
            "filename": "C:/data/survey.csv",
            "sheet_name": "Sheet1",
        }
        with patch.object(
            import_view, "import_local_file", return_value=3
        ) as mock_load:
            assert import_view._load_from_local_storage("test_project", row) == 3

        mock_load.assert_called_once_with(
            project_id="test_project",
            alias="svy",
            filename="C:/data/survey.csv",
            sheet_name="Sheet1",
        )

    def test_blank_sheet_name_becomes_none(self):
        row = {"alias": "svy", "filename": "C:/data/survey.csv", "sheet_name": ""}
        with patch.object(import_view, "import_local_file") as mock_load:
            import_view._load_from_local_storage("test_project", row)

        assert mock_load.call_args.kwargs["sheet_name"] is None


class TestPercentMissing:
    """Test the Missing Data percentage on the import preview."""

    def test_counts_null_cells(self):
        data = pl.DataFrame({"a": [1, None], "b": [None, None]})

        assert import_view._percent_missing(data) == 75.0

    def test_no_nulls_is_zero(self):
        assert import_view._percent_missing(pl.DataFrame({"a": [1, 2]})) == 0.0

    def test_no_rows_is_zero_not_division_error(self):
        data = pl.DataFrame(schema={"a": pl.Int64, "b": pl.String})

        assert import_view._percent_missing(data) == 0.0

    def test_no_columns_is_zero(self):
        assert import_view._percent_missing(pl.DataFrame()) == 0.0


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


class TestPageActions:
    """The header button and each row's menu open the right dialog."""

    def test_add_dataset_button_opens_the_add_dialog(self):
        with _reloaded_with(button_labels={"Add dataset"}) as iv:
            iv.open_add_dialog.assert_called_once_with("test_project")

    def test_edit_opens_the_dialog_with_the_import_log_row(self):
        entry = {"alias": "survey", "source": "local storage"}
        with _reloaded_with(
            overrides={
                "datasure.utils.import_log.dataset_entry": {"return_value": entry}
            }
        ) as iv:
            iv._edit_dataset("survey")

            iv.dataset_entry.assert_called_once_with("test_project", "survey")
            iv.open_edit_dialog.assert_called_once_with("test_project", entry)

    def test_remove_asks_through_the_remove_dialog(self):
        with _reloaded_with() as iv:
            iv._remove_dataset("survey")

            iv.open_remove_dialog.assert_called_once()
            assert iv.open_remove_dialog.call_args.args == ("test_project", "survey")


class TestDatasetList:
    """The page renders one row per dataset, or guidance when there are none."""

    def test_empty_project_shows_guidance_instead_of_rows(self):
        _st.info.reset_mock()
        with _reloaded_with() as iv:
            iv.render_dataset_row.assert_not_called()
            assert "no datasets yet" in str(_st.info.call_args_list)

    def test_each_dataset_gets_a_row(self):
        log = _import_log_df([{"alias": "a"}, {"alias": "b"}])
        with _reloaded_with(
            overrides={
                "datasure.utils.duckdb_utils.duckdb_get_table": {"return_value": log}
            }
        ) as iv:
            rendered = [c.args[1].alias for c in iv.render_dataset_row.call_args_list]
            assert rendered == ["a", "b"]

    def test_connections_are_always_rendered(self):
        with _reloaded_with() as iv:
            iv.render_connections.assert_called_once_with("test_project")


def _load_result(alias, error=None):
    from datasure.utils.dataset_list import LoadResult

    return LoadResult(
        alias=alias,
        source="local storage",
        refreshed=True,
        error=error,
        rows=None if error else 3,
    )


class TestLoadLock:
    """Load data keeps the app on this page until the load ends."""

    def test_load_data_button_only_locks_the_page(self):
        _st.session_state[_LOAD_RUNNING_KEY] = False
        import_view._start_load()
        assert _st.session_state[_LOAD_RUNNING_KEY] is True
        _st.session_state[_LOAD_RUNNING_KEY] = False

    def test_locked_run_renders_only_the_load(self):
        log = _import_log_df()
        connections, rows, nav, sidebar_help = (MagicMock() for _ in range(4))
        with _reloaded_with(
            overrides={
                "datasure.utils.duckdb_utils.duckdb_get_table": {"return_value": log},
                "datasure.utils.import_ui.render_connections": {"new": connections},
                "datasure.utils.import_ui.render_dataset_row": {"new": rows},
                "datasure.utils.navigations_utils.page_navigation": {"new": nav},
                "datasure.utils.navigations_utils.demo_sidebar_help": {
                    "new": sidebar_help
                },
            },
            loading=True,
        ):
            pass

        for rendered in (connections, rows, nav, sidebar_help):
            rendered.assert_not_called()
        outcome = _st.session_state.pop(_LOAD_OUTCOME_KEY)
        assert [r.alias for r in outcome.results] == ["survey"]
        assert _st.session_state[_LOAD_RUNNING_KEY] is False

    def _locked_load(self, **load_kwargs):
        """Run _run_locked_load with load_raw_datasets mocked; return the outcome."""
        _st.session_state[_LOAD_RUNNING_KEY] = True
        with (
            patch.object(import_view, "load_raw_datasets", **load_kwargs),
            patch.object(import_view, "duckdb_get_imported_datasets"),
            patch.object(import_view.st, "rerun", side_effect=_Rerun),
            pytest.raises(_Rerun),
        ):
            import_view._run_locked_load("test_project")
        assert _st.session_state[_LOAD_RUNNING_KEY] is False
        return _st.session_state.pop(_LOAD_OUTCOME_KEY)

    def test_unlocks_after_a_successful_load(self):
        outcome = self._locked_load(return_value=([_load_result("a")], []))
        assert outcome.error is None
        assert [r.alias for r in outcome.results] == ["a"]

    def test_unlocks_after_a_partial_failure(self):
        results = [_load_result("a"), _load_result("b", error="boom")]
        outcome = self._locked_load(return_value=(results, []))
        assert [r.ok for r in outcome.results] == [True, False]

    def test_unlocks_and_reports_an_unexpected_error(self):
        outcome = self._locked_load(side_effect=RuntimeError("disk full"))
        assert outcome.error == "disk full"
        assert outcome.results == []

    def test_unlocks_when_the_run_is_interrupted(self):
        """A rerun started elsewhere (e.g. the URL) still releases the lock."""
        _st.session_state[_LOAD_RUNNING_KEY] = True
        with (
            patch.object(import_view, "load_raw_datasets", side_effect=_Rerun),
            pytest.raises(_Rerun),
        ):
            import_view._run_locked_load("test_project")
        assert _st.session_state[_LOAD_RUNNING_KEY] is False


class TestShowLoadOutcome:
    """The outcome of the last load shows once the full page is back."""

    def _show(self, outcome):
        _st.session_state[_LOAD_OUTCOME_KEY] = outcome
        _st.error.reset_mock()
        _st.success.reset_mock()
        with patch.object(import_view, "warn_reapply_failures") as warn:
            import_view._show_load_outcome()
        assert _LOAD_OUTCOME_KEY not in _st.session_state
        return warn

    def test_nothing_to_show(self):
        _st.session_state.pop(_LOAD_OUTCOME_KEY, None)
        _st.success.reset_mock()
        import_view._show_load_outcome()
        _st.success.assert_not_called()

    def test_all_loaded_shows_success(self):
        warn = self._show(import_view._LoadOutcome(results=[_load_result("a")]))
        _st.success.assert_called_once()
        warn.assert_called_once()

    def test_a_failure_shows_no_success(self):
        result = _load_result("a", error="boom")
        self._show(import_view._LoadOutcome(results=[result]))
        _st.success.assert_not_called()

    def test_unexpected_error_is_shown(self):
        self._show(import_view._LoadOutcome(error="disk full"))
        assert "disk full" in str(_st.error.call_args)

    def test_no_datasets_marked_load_is_an_error(self):
        self._show(import_view._LoadOutcome())
        assert "No import configurations" in str(_st.error.call_args)


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
            selectbox_map={"Dataset": "survey"},
            project_id=import_view.DEMO_PROJECT_ID,
            loading=True,
        ):
            pass
        # Demo datasets are folded into the raw dataset list on first
        # load, alongside the alias the (mocked) import just loaded.
        raw_list = _st.session_state.st_raw_dataset_list
        assert "demo_survey" in raw_list
        assert "demo_backcheck" in raw_list
        assert "survey" in raw_list
        # Load data -> preview options are stashed for the Prep page.
        assert _st.session_state.st_prep_dataset_list == ["survey"]

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
            selectbox_map={"Dataset": "survey"},
            loading=True,
        ):
            pass
        assert _st.session_state.st_prep_dataset_list == ["survey"]

    def test_preview_renders_the_imported_data(self):
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
            selectbox_map={"Dataset": "survey"},
        ):
            assert _st.dataframe.called


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
