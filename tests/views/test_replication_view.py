"""Tests for replication_view.py."""

import importlib
import sys
from contextlib import ExitStack, suppress
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.utils.scto_api import SurveyCTOAPIError

# ---------------------------------------------------------------------------
# Module-level mock setup — must happen before replication_view is imported
# so that module-level Streamlit calls don't fail during test collection.
# ---------------------------------------------------------------------------

_st = sys.modules["streamlit"]
_orig_stop = _st.stop
_orig_columns = _st.columns

_st.stop = MagicMock()
_st.session_state["st_project_id"] = "test_project"


# columns must return the correct number of items to support unpacking (e.g.
# `page_name_col, _ = st.columns(2)`). Use side_effect so call-count matches arg.
def _columns_factory(n, *_a, **_kw):
    return [MagicMock() for _ in range(n if isinstance(n, int) else len(n))]


_st.columns = MagicMock(side_effect=_columns_factory)

_import_configs_df = pl.DataFrame(
    {
        "page_name": ["Household HFCs"],
        "survey_data_name": ["hh_survey"],
        "backcheck_data_name": [""],
        "survey_key": ["SubmissionDate"],
        "survey_id": ["hh_form"],
        "survey_date": ["date"],
        "enumerator": ["enum_col"],
    }
)

with (
    patch("datasure.utils.config_utils.ConfigurationService") as _mock_cs_cls,
    patch("datasure.utils.navigations_utils.demo_sidebar_help"),
    patch("datasure.utils.navigations_utils.add_demo_navigation"),
    patch("datasure.utils.navigations_utils.demo_callout"),
):
    _mock_cs_cls.return_value.get_all_configurations.return_value = _import_configs_df
    from datasure.views.replication_view import (
        _fetch_scto_assets,
        _get_import_log_row,
        _on_progress,
        _package_tree,
        _render_config_details,
        _render_package_preview,
        _resolve_page_config,
        _zip_filename,
    )

# Module reference for reload-based tests — safe to import now that the module
# is already cached in sys.modules from the import block above.
import datasure.views.replication_view as _rv_mod  # noqa: E402

# Restore mutated mock attributes so they don't leak into other test files.
_st.session_state["st_project_id"] = None
_st.stop = _orig_stop
_st.columns = _orig_columns


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_configs_df(**overrides) -> pl.DataFrame:
    data = {
        "page_name": ["My Page"],
        "survey_data_name": ["my_survey"],
        "backcheck_data_name": [""],
        "survey_key": ["key_col"],
        "survey_id": ["form_id"],
        "survey_date": ["date_col"],
        "enumerator": ["enum"],
    }
    data.update(overrides)
    return pl.DataFrame(data)


@pytest.fixture(autouse=True)
def _reset_mocks():
    """Reset frequently-used mock call counts before and after each test."""
    for attr in ("write", "expander", "code", "dataframe", "info", "warning", "error"):
        getattr(_st, attr).reset_mock()
    yield
    for attr in ("write", "expander", "code", "dataframe", "info", "warning", "error"):
        getattr(_st, attr).reset_mock()


# ---------------------------------------------------------------------------
# _zip_filename
# ---------------------------------------------------------------------------


class TestZipFilename:
    def test_spaces_replaced_with_underscores(self):
        assert (
            _zip_filename("My Project", "My Page")
            == "replication_my_project_my_page.zip"
        )

    def test_already_lowercase_no_spaces(self):
        assert _zip_filename("project", "page") == "replication_project_page.zip"

    def test_mixed_case_multiword(self):
        result = _zip_filename("ORS Zinc Trial", "Household HFCs")
        assert result == "replication_ors_zinc_trial_household_hfcs.zip"


# ---------------------------------------------------------------------------
# _package_tree
# ---------------------------------------------------------------------------


class TestPackageTree:
    def test_is_scto_includes_questionnaire_line(self):
        tree = _package_tree("proj", "page", is_scto=True)
        assert "page_questionnaire.xlsx" in tree

    def test_not_scto_uses_generic_surveys_line(self):
        tree = _package_tree("proj", "page", is_scto=False)
        assert "1_surveys/" in tree
        assert "questionnaire.xlsx" not in tree

    def test_tree_starts_with_replication_prefix(self):
        tree = _package_tree("my_proj", "my_page", is_scto=False)
        assert tree.startswith("replication_my_proj_my_page/")

    def test_tree_contains_expected_directories(self):
        tree = _package_tree("p", "s", is_scto=False)
        for d in ["1_docs/", "2_scripts/", "3_data/", "4_output/"]:
            assert d in tree

    def test_tree_contains_stata_scripts(self):
        tree = _package_tree("p", "s", is_scto=False)
        for script in ["0_main.do", "1_install_packages.do", "2_import_data.do"]:
            assert script in tree

    def test_raw_data_file_uses_safe_page_name(self):
        tree = _package_tree("proj", "hh_survey", is_scto=False)
        assert "hh_survey_raw.csv" in tree


# ---------------------------------------------------------------------------
# _resolve_page_config
# ---------------------------------------------------------------------------


class TestResolvePageConfig:
    def test_empty_configs_returns_none(self):
        configs = pl.DataFrame(
            {"page_name": [], "survey_data_name": [], "survey_key": []}
        )
        assert _resolve_page_config(configs, "Any Page") is None

    def test_page_not_found_returns_none(self):
        configs = _make_configs_df()
        assert _resolve_page_config(configs, "Nonexistent Page") is None

    def test_page_found_returns_alias_and_key(self):
        configs = _make_configs_df()
        result = _resolve_page_config(configs, "My Page")
        assert result == ("my_survey", "key_col")

    def test_page_found_with_null_values_returns_empty_strings(self):
        configs = pl.DataFrame(
            {
                "page_name": ["Empty Page"],
                "survey_data_name": pl.Series([None], dtype=pl.Utf8),
                "survey_key": pl.Series([None], dtype=pl.Utf8),
            }
        )
        result = _resolve_page_config(configs, "Empty Page")
        assert result == ("", "")


# ---------------------------------------------------------------------------
# _get_import_log_row
# ---------------------------------------------------------------------------


class TestGetImportLogRow:
    def test_exception_returns_none(self):
        with patch(
            "datasure.views.replication_view.duckdb_get_table",
            side_effect=Exception("DB error"),
        ):
            result = _get_import_log_row("proj", "alias")
        assert result is None

    def test_empty_filter_returns_none(self):
        mock_df = MagicMock()
        mock_df.filter.return_value.is_empty.return_value = True
        with patch(
            "datasure.views.replication_view.duckdb_get_table", return_value=mock_df
        ):
            result = _get_import_log_row("proj", "alias")
        assert result is None

    def test_row_found_returns_dict(self):
        expected = {"alias": "hh_survey", "source": "SurveyCTO"}
        mock_df = MagicMock()
        mock_df.filter.return_value.is_empty.return_value = False
        mock_df.filter.return_value.row.return_value = expected
        with patch(
            "datasure.views.replication_view.duckdb_get_table", return_value=mock_df
        ):
            result = _get_import_log_row("proj", "hh_survey")
        assert result == expected


# ---------------------------------------------------------------------------
# _fetch_scto_assets
# ---------------------------------------------------------------------------


class TestFetchSctoAssets:
    def _row(self, **overrides):
        defaults = {
            "source": "SurveyCTO",
            "server": "myserver",
            "username": "user@test.com",
            "form_id": "hh_form",
        }
        defaults.update(overrides)
        return defaults

    def _good_cred(self):
        return {
            "success": True,
            "credentials": {"password": "secret", "username": "user"},
        }

    def test_no_import_log_row_returns_empty(self):
        with patch(
            "datasure.views.replication_view._get_import_log_row", return_value=None
        ):
            result = _fetch_scto_assets("proj", "alias")
        assert result == (None, None, "", "")

    def test_non_scto_source_returns_empty(self):
        row = self._row(source="CSV")
        with patch(
            "datasure.views.replication_view._get_import_log_row", return_value=row
        ):
            result = _fetch_scto_assets("proj", "alias")
        assert result == (None, None, "", "")

    def test_missing_server_returns_error(self):
        row = self._row(server="")
        with patch(
            "datasure.views.replication_view._get_import_log_row", return_value=row
        ):
            xlsx, _, _fid, error = _fetch_scto_assets("proj", "alias")
        assert xlsx is None
        assert "missing" in error.lower()

    def test_missing_form_id_returns_error(self):
        row = self._row(form_id="")
        with patch(
            "datasure.views.replication_view._get_import_log_row", return_value=row
        ):
            xlsx, _, _fid, error = _fetch_scto_assets("proj", "alias")
        assert xlsx is None
        assert error

    def test_credential_failure_returns_error(self):
        row = self._row()
        with (
            patch(
                "datasure.views.replication_view._get_import_log_row", return_value=row
            ),
            patch(
                "datasure.views.replication_view.retrieve_scto_credentials",
                return_value={"success": False, "error": "keyring unavailable"},
            ),
        ):
            xlsx, _fd, _fid, error = _fetch_scto_assets("proj", "alias")
        assert xlsx is None
        assert "keyring unavailable" in error

    def test_missing_password_returns_error(self):
        row = self._row()
        with (
            patch(
                "datasure.views.replication_view._get_import_log_row", return_value=row
            ),
            patch(
                "datasure.views.replication_view.retrieve_scto_credentials",
                return_value={"success": True, "credentials": {"password": ""}},
            ),
        ):
            xlsx, _fd, _fid, error = _fetch_scto_assets("proj", "alias")
        assert xlsx is None
        assert "Password not found" in error

    def test_scto_api_error_returns_error(self):
        row = self._row()
        mock_client = MagicMock()
        mock_client.download_form_xlsx.side_effect = SurveyCTOAPIError("timeout")
        with (
            patch(
                "datasure.views.replication_view._get_import_log_row", return_value=row
            ),
            patch(
                "datasure.views.replication_view.retrieve_scto_credentials",
                return_value=self._good_cred(),
            ),
            patch("datasure.views.replication_view.SurveyCTOAPIConfig"),
            patch(
                "datasure.views.replication_view.SurveyCTOAPIClient",
                return_value=mock_client,
            ),
        ):
            xlsx, _fd, _fid, error = _fetch_scto_assets("proj", "alias")
        assert xlsx is None
        assert "timeout" in error

    def test_unexpected_exception_returns_error(self):
        row = self._row()
        mock_client = MagicMock()
        mock_client.download_form_xlsx.side_effect = RuntimeError("unexpected")
        with (
            patch(
                "datasure.views.replication_view._get_import_log_row", return_value=row
            ),
            patch(
                "datasure.views.replication_view.retrieve_scto_credentials",
                return_value=self._good_cred(),
            ),
            patch("datasure.views.replication_view.SurveyCTOAPIConfig"),
            patch(
                "datasure.views.replication_view.SurveyCTOAPIClient",
                return_value=mock_client,
            ),
        ):
            xlsx, _fd, _fid, error = _fetch_scto_assets("proj", "alias")
        assert xlsx is None
        assert "unexpected" in error.lower()

    def test_success_returns_all_assets(self):
        row = self._row()
        mock_client = MagicMock()
        mock_xlsx = b"xlsx_bytes"
        mock_form_def = {"fields": []}
        mock_client.download_form_xlsx.return_value = (mock_xlsx, mock_form_def)
        with (
            patch(
                "datasure.views.replication_view._get_import_log_row", return_value=row
            ),
            patch(
                "datasure.views.replication_view.retrieve_scto_credentials",
                return_value=self._good_cred(),
            ),
            patch("datasure.views.replication_view.SurveyCTOAPIConfig"),
            patch(
                "datasure.views.replication_view.SurveyCTOAPIClient",
                return_value=mock_client,
            ),
        ):
            xlsx, form_def, form_id, error = _fetch_scto_assets("proj", "alias")
        assert xlsx == mock_xlsx
        assert form_def == mock_form_def
        assert form_id == "hh_form"
        assert error == ""


# ---------------------------------------------------------------------------
# _on_progress
# ---------------------------------------------------------------------------


class TestOnProgress:
    def test_calls_st_write_with_checkmark_prefix(self):
        _on_progress("Processing data")
        _st.write.assert_called_once()
        arg = _st.write.call_args[0][0]
        assert "Processing data" in arg
        assert ":white_check_mark:" in arg


# ---------------------------------------------------------------------------
# _render_config_details
# ---------------------------------------------------------------------------


class TestRenderConfigDetails:
    def test_calls_expander_and_dataframe(self):
        configs = _make_configs_df()
        _render_config_details(configs)
        _st.expander.assert_called_once()
        _st.dataframe.assert_called_once()

    def test_expander_label_mentions_details(self):
        configs = _make_configs_df()
        _render_config_details(configs)
        label = _st.expander.call_args[0][0]
        assert "details" in label.lower() or "page" in label.lower()

    def test_dataframe_receives_selected_columns(self):
        configs = _make_configs_df()
        _render_config_details(configs)
        passed_df = _st.dataframe.call_args[0][0]
        assert isinstance(passed_df, pl.DataFrame)
        assert "survey_data_name" in passed_df.columns


# ---------------------------------------------------------------------------
# _render_package_preview
# ---------------------------------------------------------------------------


class TestRenderPackagePreview:
    def test_calls_expander_and_code(self):
        _render_package_preview("project", "page", is_scto=False)
        _st.expander.assert_called_once()
        _st.code.assert_called_once()

    def test_code_block_contains_project_and_page(self):
        _render_package_preview("myproj", "mypage", is_scto=True)
        code_arg = _st.code.call_args[0][0]
        assert "myproj" in code_arg
        assert "mypage" in code_arg

    def test_is_scto_true_includes_questionnaire(self):
        _render_package_preview("proj", "page", is_scto=True)
        code_arg = _st.code.call_args[0][0]
        assert "questionnaire.xlsx" in code_arg

    def test_is_scto_false_omits_questionnaire(self):
        _render_package_preview("proj", "page", is_scto=False)
        code_arg = _st.code.call_args[0][0]
        assert "questionnaire.xlsx" not in code_arg


# ---------------------------------------------------------------------------
# Module-level page code branches (covered via importlib.reload)
# ---------------------------------------------------------------------------


def _base_reload_patches(configs=None, extra_patches=()):
    """Return an ExitStack with all patches needed to reload replication_view."""
    if configs is None:
        configs = _import_configs_df
    mock_cs = MagicMock()
    mock_cs.return_value.get_all_configurations.return_value = configs
    stack = ExitStack()
    stack.enter_context(
        patch("datasure.utils.config_utils.ConfigurationService", mock_cs)
    )
    stack.enter_context(patch("datasure.utils.navigations_utils.demo_sidebar_help"))
    stack.enter_context(patch("datasure.utils.navigations_utils.add_demo_navigation"))
    stack.enter_context(patch("datasure.utils.navigations_utils.demo_callout"))
    stack.enter_context(
        patch(
            "datasure.utils.cache_utils.get_cache_path",
            return_value=Path("/nonexistent"),
        )
    )
    stack.enter_context(
        patch(
            "datasure.utils.duckdb_utils.duckdb_get_table",
            side_effect=Exception("no db"),
        )
    )
    stack.enter_context(
        patch(
            "datasure.replication.package_builder.build_replication_package",
            return_value=b"zip",
        )
    )
    for p in extra_patches:
        stack.enter_context(p)
    return stack


class TestModuleLevelCodeCoverage:
    """Cover module-level page execution branches via importlib.reload."""

    @pytest.fixture(autouse=True)
    def _restore_module(self):
        """After each test, reload to a clean baseline so later tests are unaffected."""
        yield
        _st.stop.side_effect = None
        _st.session_state["st_project_id"] = "test_project"
        _st.selectbox = MagicMock(return_value=None)
        _st.button = MagicMock(return_value=False)
        orig_cd = _st.cache_data
        orig_cols = _st.columns
        _st.cache_data = lambda ttl=None, **kw: (lambda f: f)
        _st.columns = MagicMock(side_effect=_columns_factory)
        try:
            with _base_reload_patches():
                importlib.reload(_rv_mod)
        finally:
            _st.cache_data = orig_cd
            _st.columns = orig_cols
            _st.session_state["st_project_id"] = None

    def _reload(
        self,
        project_id="test_project",
        configs=None,
        selectbox_val=None,
        button_val=False,
        stop_raises=False,
    ):
        _st.session_state["st_project_id"] = project_id
        _st.selectbox = MagicMock(return_value=selectbox_val)
        _st.button = MagicMock(return_value=button_val)
        if stop_raises:
            _st.stop.side_effect = StopIteration
        orig_cd = _st.cache_data
        orig_cols = _st.columns
        _st.cache_data = lambda ttl=None, **kw: (lambda f: f)
        _st.columns = MagicMock(side_effect=_columns_factory)
        try:
            with _base_reload_patches(configs=configs), suppress(StopIteration):
                importlib.reload(_rv_mod)
        finally:
            _st.cache_data = orig_cd
            _st.columns = orig_cols
            _st.stop.side_effect = None

    def test_page_selected_covers_selector_config_and_preview(self):
        """Reload with a selected page covers session-state cleanup (324-326),
        config details (329-337), and package preview (419-421).
        """
        self._reload(selectbox_val="Household HFCs", button_val=False)

    def test_build_button_covers_build_and_download_sections(self):
        """Reload with button=True covers build block (353-377) and download
        section (384-406) including the PII confirmation branch.
        """
        self._reload(selectbox_val="Household HFCs", button_val=True)

    def test_no_project_id_covers_first_guard(self):
        """Empty project_id covers st.info + st.stop guard (249-250)."""
        self._reload(project_id="", stop_raises=True)

    def test_empty_configs_covers_second_guard(self):
        """Empty configs DataFrame covers the no-configs guard (255-259)."""
        empty = pl.DataFrame(
            {
                "page_name": pl.Series([], dtype=pl.Utf8),
                "survey_data_name": pl.Series([], dtype=pl.Utf8),
                "backcheck_data_name": pl.Series([], dtype=pl.Utf8),
                "survey_key": pl.Series([], dtype=pl.Utf8),
                "survey_id": pl.Series([], dtype=pl.Utf8),
                "survey_date": pl.Series([], dtype=pl.Utf8),
                "enumerator": pl.Series([], dtype=pl.Utf8),
            }
        )
        self._reload(configs=empty, stop_raises=True)
