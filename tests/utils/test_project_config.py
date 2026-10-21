"""Tests for project configuration export/import (issue #251)."""

import json
import logging
from datetime import date, datetime
from unittest.mock import Mock, patch

import polars as pl
import pytest
from polars.testing import assert_frame_equal

from datasure.models.schemas import (
    ImportSourceEntry,
    ProjectConfigBundle,
    ProjectPageBundle,
)
from datasure.utils.config_utils import ConfigurationService
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.project_config import (
    BUNDLE_VERSION,
    _render_config_summary,
    _stored_username_for_server,
    apply_project_config,
    bundle_version_warning,
    export_project_config,
    missing_credentials,
    missing_local_files,
    parse_project_config,
)
from datasure.utils.reapply_utils import ReapplyFailure

PROJECT_ID = "test_survey_project_1001"


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the conftest autouse fixture: these tests mock duckdb per-test."""


# === BUNDLE PARSE / ROUND TRIP === #


class TestBundleRoundTrip:
    """Test ProjectConfigBundle serialization and parsing."""

    def test_round_trip(self):
        """A bundle survives a dump-to-JSON, parse-back cycle unchanged."""
        bundle = ProjectConfigBundle(
            exported_from_project="ACME Endline 2026",
            exported_at="2026-08-28T10:15:00",
            datasets=[
                ImportSourceEntry(alias="household", source="SurveyCTO", server="acme")
            ],
            prep_steps={"household": [{"action": "remove row(s)"}]},
            pages=[ProjectPageBundle(config={"page_name": "Household HFC"})],
            corrections={"household": [{"KEY": "1", "action": "modify value"}]},
        )

        raw = bundle.model_dump_json()
        parsed = parse_project_config(raw)

        assert parsed == bundle

    def test_parse_rejects_invalid_json(self):
        """Malformed JSON raises rather than silently producing an empty bundle."""
        with pytest.raises(json.JSONDecodeError):
            parse_project_config("not json")

    def test_parse_defaults_missing_optional_fields(self):
        """A minimal bundle (no datasets/prep/pages/corrections) still parses."""
        bundle = parse_project_config(
            json.dumps(
                {
                    "exported_from_project": "Minimal Project",
                    "exported_at": "2026-08-28T10:15:00",
                }
            )
        )
        assert bundle.datasets == []
        assert bundle.prep_steps == {}
        assert bundle.pages == []
        assert bundle.corrections == {}


# === EXPORT === #


class TestExportProjectConfig:
    """Test export_project_config."""

    @patch("datasure.utils.project_config.get_cache_path")
    @patch("datasure.utils.project_config.ConfigurationService")
    @patch("datasure.utils.project_config.duckdb_get_table")
    def test_export_assembles_all_layers(
        self, mock_get_table, mock_config_service_cls, mock_get_cache_path, tmp_path
    ):
        """Export pulls import sources, prep steps, corrections, and pages together."""

        def fake_get_table(project_id, alias, db_name):
            if alias == "import_log":
                return pl.DataFrame(
                    {
                        "alias": ["household"],
                        "source": ["SurveyCTO"],
                        "server": ["acme"],
                        "form_id": ["hh_v3"],
                        "username": ["k@example.com"],
                        "filename": [None],
                        "sheet_name": [None],
                        "attachments": [True],
                    }
                )
            if alias == "prep_log_household":
                return pl.DataFrame(
                    {"prep_args": [json.dumps({"action": "transform column(s)"})]}
                )
            if alias == "corr_log_household":
                return pl.DataFrame(
                    {
                        "date": [None],
                        "KEY": ["1"],
                        "action": ["modify value"],
                        "column": ["age"],
                        "current_value": ["10"],
                        "new_value": ["20"],
                        "reason": ["typo"],
                    }
                )
            return pl.DataFrame()

        mock_get_table.side_effect = fake_get_table

        mock_service = Mock()
        mock_service.get_all_configurations.return_value = pl.DataFrame(
            {"page_name": ["Household HFC"], "survey_data_name": ["household"]}
        )
        mock_config_service_cls.return_value = mock_service
        mock_get_cache_path.return_value = tmp_path

        bundle = export_project_config(PROJECT_ID, "ACME Endline 2026")

        assert bundle.exported_from_project == "ACME Endline 2026"
        assert [d.alias for d in bundle.datasets] == ["household"]
        assert bundle.datasets[0].server == "acme"
        assert bundle.prep_steps["household"] == [{"action": "transform column(s)"}]
        assert bundle.corrections["household"][0]["KEY"] == "1"
        assert bundle.pages[0].config["page_name"] == "Household HFC"

    @patch("datasure.utils.project_config.get_cache_path")
    @patch("datasure.utils.project_config.ConfigurationService")
    @patch("datasure.utils.project_config.duckdb_get_table")
    def test_export_reads_settings_json_files(
        self, mock_get_table, mock_config_service_cls, mock_get_cache_path, tmp_path
    ):
        """Export attaches each page's on-disk settings JSON to its bundle entry."""
        mock_get_table.return_value = pl.DataFrame()

        mock_service = Mock()
        mock_service.get_all_configurations.return_value = pl.DataFrame(
            {"page_name": ["Household HFC"], "survey_data_name": ["household"]}
        )
        mock_config_service_cls.return_value = mock_service
        mock_get_cache_path.return_value = tmp_path

        (tmp_path / "page_household_hfc_settings.json").write_text(
            json.dumps({"missing": {"threshold": 5}})
        )

        bundle = export_project_config(PROJECT_ID, "ACME Endline 2026")

        assert bundle.pages[0].settings == {"missing": {"threshold": 5}}
        assert bundle.pages[0].missing_settings == {}

    @patch("datasure.utils.project_config.get_cache_path")
    @patch("datasure.utils.project_config.ConfigurationService")
    @patch("datasure.utils.project_config.duckdb_get_table")
    def test_export_leaves_out_personal_view_state(
        self, mock_get_table, mock_config_service_cls, mock_get_cache_path, tmp_path
    ):
        """Saved filters and the last selected check are not shared."""
        mock_get_table.return_value = pl.DataFrame()
        mock_config_service_cls.return_value.get_all_configurations.return_value = (
            pl.DataFrame(
                {"page_name": ["Household HFC"], "survey_data_name": ["household"]}
            )
        )
        mock_get_cache_path.return_value = tmp_path
        (tmp_path / "page_household_hfc_settings.json").write_text(
            json.dumps(
                {
                    "missing": {"threshold": 5},
                    "view_state": {"selected": "gps", "scopes": {"gps": {"a": 1}}},
                }
            )
        )

        bundle = export_project_config(PROJECT_ID, "ACME Endline 2026")

        assert bundle.pages[0].settings == {"missing": {"threshold": 5}}
        assert "view_state" not in bundle.model_dump_json()


# === RESOLUTION HELPERS === #


class TestResolutionHelpers:
    """Test missing_credentials / missing_local_files / _stored_username_for_server."""

    @patch("datasure.utils.project_config.list_stored_credentials")
    def test_missing_credentials_excludes_stored_servers(self, mock_list_creds):
        """A server with a stored credential is not reported as missing."""
        mock_list_creds.return_value = {
            "credentials": {"scto_login - acme - a@x.com": {"server": "acme"}}
        }
        bundle = ProjectConfigBundle(
            exported_from_project="p",
            exported_at="t",
            datasets=[
                ImportSourceEntry(alias="household", source="SurveyCTO", server="acme"),
                ImportSourceEntry(alias="tracking", source="SurveyCTO", server="other"),
            ],
        )

        assert missing_credentials(PROJECT_ID, bundle) == ["other"]

    def test_missing_local_files_returns_only_local_storage_entries(self):
        """SurveyCTO datasets are not included; local-storage ones are."""
        bundle = ProjectConfigBundle(
            exported_from_project="p",
            exported_at="t",
            datasets=[
                ImportSourceEntry(alias="household", source="SurveyCTO", server="acme"),
                ImportSourceEntry(alias="tracking", source="local storage"),
            ],
        )

        result = missing_local_files(bundle)

        assert [d.alias for d in result] == ["tracking"]

    @patch("datasure.utils.project_config.list_stored_credentials")
    def test_stored_username_for_server_found(self, mock_list_creds):
        """Returns the username stored for a matching server."""
        mock_list_creds.return_value = {
            "credentials": {"k": {"server": "acme", "username": "k@x.com"}}
        }
        assert _stored_username_for_server(PROJECT_ID, "acme") == "k@x.com"

    @patch("datasure.utils.project_config.list_stored_credentials")
    def test_stored_username_for_server_not_found(self, mock_list_creds):
        """Returns None when no credential is stored for that server."""
        mock_list_creds.return_value = {"credentials": {}}
        assert _stored_username_for_server(PROJECT_ID, "acme") is None


# === APPLY === #


class TestApplyProjectConfig:
    """Test apply_project_config."""

    def _config_service_mock(self, page_exists=False):
        service = Mock()
        service.page_name_exists.return_value = page_exists
        return service

    @patch("datasure.utils.project_config.CorrectionProcessor")
    @patch("datasure.utils.project_config.ConfigurationService")
    @patch("datasure.utils.project_config.prep_apply_action")
    @patch("datasure.utils.project_config.load_local_data")
    @patch("datasure.utils.project_config.duckdb_save_table")
    @patch("datasure.utils.project_config.duckdb_get_table")
    def test_local_dataset_full_pipeline_succeeds(
        self,
        mock_get_table,
        mock_save_table,
        mock_load_local,
        mock_prep_apply,
        mock_config_service_cls,
        mock_correction_cls,
        tmp_path,
    ):
        """A local dataset with a valid path flows through the whole pipeline."""
        mock_get_table.return_value = pl.DataFrame()
        mock_prep_apply.return_value = []
        mock_config_service_cls.return_value = self._config_service_mock(
            page_exists=False
        )
        mock_correction_cls.return_value.refresh_corrected_data.return_value = []

        data_file = tmp_path / "household.csv"
        data_file.write_text("id,age\n1,30\n")

        bundle = ProjectConfigBundle(
            exported_from_project="p",
            exported_at="t",
            datasets=[ImportSourceEntry(alias="household", source="local storage")],
            prep_steps={"household": [{"action": "transform column(s)"}]},
            pages=[
                ProjectPageBundle(
                    config={
                        "page_name": "Household HFC",
                        "survey_data_name": "household",
                    }
                )
            ],
            corrections={"household": [{"KEY": "1", "action": "modify value"}]},
        )

        result = apply_project_config(
            PROJECT_ID, bundle, local_file_paths={"household": str(data_file)}
        )

        assert result.datasets_imported == ["household"]
        assert result.datasets_skipped == []
        mock_load_local.assert_called_once()
        mock_prep_apply.assert_called_once_with(PROJECT_ID, "household")
        assert result.pages_created == ["Household HFC"]
        mock_correction_cls.return_value.refresh_corrected_data.assert_called_once_with(
            "household"
        )
        mock_correction_cls.return_value.refresh_existing_corrected_data.assert_not_called()

    @patch("datasure.utils.project_config.CorrectionProcessor")
    @patch("datasure.utils.project_config.ConfigurationService")
    @patch("datasure.utils.project_config.prep_apply_action")
    @patch("datasure.utils.project_config.load_local_data")
    @patch("datasure.utils.project_config.duckdb_save_table")
    @patch("datasure.utils.project_config.duckdb_get_table")
    def test_prep_steps_without_corrections_rebuild_existing_corrected_data(
        self,
        mock_get_table,
        mock_save_table,
        mock_load_local,
        mock_prep_apply,
        mock_config_service_cls,
        mock_correction_cls,
        tmp_path,
    ):
        """Re-seeded prep steps refresh a corrected table the bundle doesn't seed."""
        mock_get_table.return_value = pl.DataFrame()
        mock_prep_apply.return_value = []
        mock_config_service_cls.return_value = self._config_service_mock()
        failure = ReapplyFailure("modify value", "Column not found")
        processor = mock_correction_cls.return_value
        processor.refresh_existing_corrected_data.return_value = [failure]

        data_file = tmp_path / "household.csv"
        data_file.write_text("id,age\n1,30\n")

        bundle = ProjectConfigBundle(
            exported_from_project="p",
            exported_at="t",
            datasets=[ImportSourceEntry(alias="household", source="local storage")],
            prep_steps={"household": [{"action": "transform column(s)"}]},
        )

        result = apply_project_config(
            PROJECT_ID, bundle, local_file_paths={"household": str(data_file)}
        )

        processor.refresh_existing_corrected_data.assert_called_once_with("household")
        processor.refresh_corrected_data.assert_not_called()
        assert result.correction_failures == [failure]

    @patch("datasure.utils.project_config.ConfigurationService")
    @patch("datasure.utils.project_config.duckdb_get_table")
    def test_local_dataset_without_path_is_skipped(
        self, mock_get_table, mock_config_service_cls
    ):
        """A local-storage dataset with no resolved path is skipped, not fatal."""
        mock_get_table.return_value = pl.DataFrame()
        mock_config_service_cls.return_value = self._config_service_mock()

        bundle = ProjectConfigBundle(
            exported_from_project="p",
            exported_at="t",
            datasets=[ImportSourceEntry(alias="tracking", source="local storage")],
        )

        result = apply_project_config(PROJECT_ID, bundle, local_file_paths={})

        assert result.datasets_imported == []
        assert result.datasets_skipped == [
            ReapplyFailure("tracking", "No file path was provided")
        ]

    @patch("datasure.utils.project_config.list_stored_credentials")
    @patch("datasure.utils.project_config.ConfigurationService")
    @patch("datasure.utils.project_config.duckdb_get_table")
    def test_surveycto_dataset_without_credentials_is_skipped(
        self, mock_get_table, mock_config_service_cls, mock_list_creds
    ):
        """A SurveyCTO dataset with no stored credentials is skipped, not fatal."""
        mock_get_table.return_value = pl.DataFrame()
        mock_config_service_cls.return_value = self._config_service_mock()
        mock_list_creds.return_value = {"credentials": {}}

        bundle = ProjectConfigBundle(
            exported_from_project="p",
            exported_at="t",
            datasets=[
                ImportSourceEntry(
                    alias="household", source="SurveyCTO", server="acme", form_id="hh"
                )
            ],
        )

        result = apply_project_config(PROJECT_ID, bundle, local_file_paths={})

        assert result.datasets_imported == []
        assert len(result.datasets_skipped) == 1
        assert result.datasets_skipped[0].step == "household"

    @patch("datasure.utils.project_config.ConfigurationService")
    @patch("datasure.utils.project_config.duckdb_get_table")
    @patch("datasure.utils.project_config.duckdb_save_table")
    @patch("datasure.utils.project_config.load_local_data")
    def test_page_referencing_unimported_dataset_is_skipped(
        self, mock_load_local, mock_save_table, mock_get_table, mock_config_service_cls
    ):
        """A page whose survey dataset failed to import is skipped, not created."""
        mock_get_table.return_value = pl.DataFrame()
        mock_config_service_cls.return_value = self._config_service_mock()

        bundle = ProjectConfigBundle(
            exported_from_project="p",
            exported_at="t",
            datasets=[ImportSourceEntry(alias="household", source="local storage")],
            pages=[
                ProjectPageBundle(
                    config={
                        "page_name": "Household HFC",
                        "survey_data_name": "household",
                    }
                )
            ],
        )

        # No path resolved for "household" -> import is skipped -> page must be too
        result = apply_project_config(PROJECT_ID, bundle, local_file_paths={})

        assert result.pages_created == []
        assert result.pages_skipped == [
            ReapplyFailure("Household HFC", "Dataset 'household' was not imported")
        ]

    @patch("datasure.utils.project_config.ConfigurationService")
    @patch("datasure.utils.project_config.duckdb_get_table")
    def test_page_with_existing_name_is_skipped(
        self, mock_get_table, mock_config_service_cls
    ):
        """A page whose name already exists locally is skipped, not overwritten."""
        mock_get_table.return_value = pl.DataFrame()
        mock_config_service_cls.return_value = self._config_service_mock(
            page_exists=True
        )

        bundle = ProjectConfigBundle(
            exported_from_project="p",
            exported_at="t",
            pages=[
                ProjectPageBundle(
                    config={
                        "page_name": "Household HFC",
                        "survey_data_name": "household",
                    }
                )
            ],
        )

        result = apply_project_config(PROJECT_ID, bundle, local_file_paths={})

        assert result.pages_created == []
        assert result.pages_skipped[0].reason == "A page with this name already exists"

    @patch("datasure.utils.project_config.get_cache_path")
    @patch("datasure.utils.project_config.CorrectionProcessor")
    @patch("datasure.utils.project_config.ConfigurationService")
    @patch("datasure.utils.project_config.load_local_data")
    @patch("datasure.utils.project_config.duckdb_save_table")
    @patch("datasure.utils.project_config.duckdb_get_table")
    def test_applied_settings_keep_local_view_state_and_drop_incoming(
        self,
        mock_get_table,
        mock_save_table,
        mock_load_local,
        mock_config_service_cls,
        mock_correction_cls,
        mock_get_cache_path,
        tmp_path,
    ):
        """Applying a configuration (template) never carries view state."""
        mock_get_table.return_value = pl.DataFrame()
        mock_config_service_cls.return_value = self._config_service_mock()
        mock_get_cache_path.return_value = tmp_path
        settings_file = tmp_path / "page_household_hfc_settings.json"
        settings_file.write_text(json.dumps({"view_state": {"selected": "duplicates"}}))
        data_file = tmp_path / "household.csv"
        data_file.write_text("id,age\n1,30\n")
        bundle = ProjectConfigBundle(
            exported_from_project="p",
            exported_at="t",
            datasets=[ImportSourceEntry(alias="household", source="local storage")],
            pages=[
                ProjectPageBundle(
                    config={
                        "page_name": "Household HFC",
                        "survey_data_name": "household",
                    },
                    settings={
                        "missing": {"threshold": 5},
                        "view_state": {"selected": "gps"},
                    },
                )
            ],
        )

        apply_project_config(
            PROJECT_ID, bundle, local_file_paths={"household": str(data_file)}
        )

        assert json.loads(settings_file.read_text()) == {
            "missing": {"threshold": 5},
            "view_state": {"selected": "duplicates"},
        }


# === CHECK TABLES AND MISSING CODES (issue #354) === #

SRC_PROJECT = "src00001"
DST_PROJECT = "dst00001"
PAGE_NAME = "Household HFC"
PAGE_ID = "household_hfc"

# One table per registered check prefix, using the dtypes each check saves.
CHECK_TABLES = {
    "duplicates": pl.DataFrame(
        {
            "search_type": ["exact", "pattern"],
            "pattern": [None, "hh_*"],
            "column_name": [["hhid"], ["hh_a", "hh_b"]],
            "locked": [True, False],
        },
        schema={
            "search_type": pl.Utf8,
            "pattern": pl.Utf8,
            "column_name": pl.List(pl.Utf8),
            "locked": pl.Boolean,
        },
    ),
    "outliers": pl.DataFrame(
        {
            "search_type": ["exact"],
            "pattern": [None],
            "column_name": [["age"]],
            "grouped_columns": [False],
            "locked": [False],
            "outlier_enabled": [True],
            "outlier_method": ["iqr"],
            "outlier_multiplier": [1.5],
            "outlier_threshold": [None],
            "hard_min": [0.0],
            "soft_min": [None],
            "soft_max": [None],
            "hard_max": [120.0],
        },
        schema={
            "search_type": pl.Utf8,
            "pattern": pl.Utf8,
            "column_name": pl.List(pl.Utf8),
            "grouped_columns": pl.Boolean,
            "locked": pl.Boolean,
            "outlier_enabled": pl.Boolean,
            "outlier_method": pl.Utf8,
            "outlier_multiplier": pl.Float64,
            "outlier_threshold": pl.Int64,
            "hard_min": pl.Float64,
            "soft_min": pl.Float64,
            "soft_max": pl.Float64,
            "hard_max": pl.Float64,
        },
    ),
    "gps_columns": pl.DataFrame(
        {
            "alias": ["home"],
            "format_type": ["single"],
            "delimiter": [" "],
            "gps_column": ["gps"],
            "latitude_column": [None],
            "longitude_column": [None],
            "altitude_column": [None],
            "accuracy_column": [None],
        },
        schema={
            c: pl.Utf8
            for c in (
                "alias",
                "format_type",
                "delimiter",
                "gps_column",
                "latitude_column",
                "longitude_column",
                "altitude_column",
                "accuracy_column",
            )
        },
    ),
    "backchecks": pl.DataFrame(
        {
            "search_type": ["exact"],
            "pattern": [None],
            "column_name": [["age", "sex"]],
            "category": [1],
            "ok_range_type": ["absolute"],
            "ok_range_values": [[-2, 2]],
            "ttest": [True],
            "prtest": [False],
            "signrank": [False],
            "reliability": [True],
        },
        schema={
            "search_type": pl.Utf8,
            "pattern": pl.Utf8,
            "column_name": pl.List(pl.Utf8),
            "category": pl.Int64,
            "ok_range_type": pl.Utf8,
            "ok_range_values": pl.List(pl.Float64),
            "ttest": pl.Boolean,
            "prtest": pl.Boolean,
            "signrank": pl.Boolean,
            "reliability": pl.Boolean,
        },
    ),
    "descriptive_columns": pl.DataFrame(
        {
            "Selected": [True, False],
            "column": ["age", "sex"],
            "type": ["numeric", "categorical"],
        }
    ),
    "bc_attribution": pl.DataFrame(
        {
            "survey_key": ["k1"],
            "backcheck_key": ["b1"],
            "column_name": ["age"],
            "survey_value": ["30"],
            "backcheck_value": ["31"],
            "source": ["enumerator"],
            "note": [None],
            "user": ["reviewer"],
            "date": [datetime(2026, 8, 28, 10, 15, 0, 123456)],
        },
        schema={
            "survey_key": pl.String,
            "backcheck_key": pl.String,
            "column_name": pl.String,
            "survey_value": pl.String,
            "backcheck_value": pl.String,
            "source": pl.String,
            "note": pl.String,
            "user": pl.String,
            "date": pl.Datetime("us"),
        },
    ),
}


@pytest.fixture
def real_duckdb(tmp_path):
    """Point every DuckDB database and settings file at a temporary cache."""

    def fake_cache_path(*parts):
        path = tmp_path.joinpath(*map(str, parts))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    with (
        patch("datasure.utils.duckdb_utils.get_cache_path", fake_cache_path),
        patch("datasure.utils.project_config.get_cache_path", fake_cache_path),
    ):
        yield tmp_path


def _page_config_service(page_exists=False):
    service = Mock()
    service.get_all_configurations.return_value = pl.DataFrame(
        {
            "page_name": [PAGE_NAME],
            "survey_data_name": ["household"],
            "survey_key": ["KEY"],
        }
    )
    service.page_name_exists.return_value = page_exists
    return service


def _seed_source_project():
    duckdb_save_table(
        SRC_PROJECT,
        pl.DataFrame(
            {
                "alias": ["household"],
                "source": ["local storage"],
                "filename": ["household.csv"],
            }
        ),
        "import_log",
        "logs",
    )
    for prefix, df in CHECK_TABLES.items():
        duckdb_save_table(SRC_PROJECT, df, f"{prefix}_{PAGE_ID}", "logs")
    duckdb_save_table(
        SRC_PROJECT,
        pl.DataFrame({"label": ["Don't know", "Refused"], "codes": ["-99", "-88"]}),
        f"missing_codes_{SRC_PROJECT}",
        "logs",
    )


def _seed_corrections():
    duckdb_save_table(
        SRC_PROJECT,
        pl.DataFrame(
            {
                "date": [datetime(2026, 8, 28, 9, 0, 0)],
                "KEY": ["1"],
                "action": ["modify value"],
                "column": ["age"],
                "current_value": ["30"],
                "new_value": ["31"],
                "reason": ["typo"],
            }
        ),
        "corr_log_household",
        "logs",
    )


@patch("datasure.utils.project_config.CorrectionProcessor")
@patch("datasure.utils.project_config.load_local_data")
@patch("datasure.utils.project_config.ConfigurationService")
class TestCheckTablesAndMissingCodes:
    """Check tables and missing codes travel with the bundle."""

    @pytest.fixture(autouse=True)
    def _data_file(self, real_duckdb):
        data_file = real_duckdb / "household.csv"
        data_file.write_text("KEY,age\n1,30\n")
        self.local_paths = {"household": str(data_file)}

    def _export_and_parse(self, **export_kwargs):
        bundle = export_project_config(SRC_PROJECT, "Source", **export_kwargs)
        return parse_project_config(bundle.model_dump_json())

    def test_round_trip_preserves_check_tables_and_missing_codes(
        self, mock_service_cls, mock_load_local, mock_correction_cls
    ):
        """Every registered table and the missing codes arrive with their dtypes."""
        mock_service_cls.return_value = _page_config_service()
        _seed_source_project()

        bundle = self._export_and_parse()
        result = apply_project_config(
            DST_PROJECT, bundle, local_file_paths=self.local_paths
        )

        assert result.pages_created == [PAGE_NAME]
        for prefix, expected in CHECK_TABLES.items():
            actual = duckdb_get_table(DST_PROJECT, f"{prefix}_{PAGE_ID}", "logs")
            assert_frame_equal(actual, expected)
        assert_frame_equal(
            duckdb_get_table(DST_PROJECT, f"missing_codes_{DST_PROJECT}", "logs"),
            pl.DataFrame({"label": ["Don't know", "Refused"], "codes": ["-99", "-88"]}),
        )

    def test_update_merges_missing_codes_with_bundle_winning_on_label(
        self, mock_service_cls, mock_load_local, mock_correction_cls
    ):
        """Existing labels are kept; a label in the bundle replaces the local one."""
        mock_service_cls.return_value = _page_config_service()
        _seed_source_project()
        duckdb_save_table(
            DST_PROJECT,
            pl.DataFrame({"label": ["Refused", "N/A"], "codes": ["-77", "-66"]}),
            f"missing_codes_{DST_PROJECT}",
            "logs",
        )

        apply_project_config(DST_PROJECT, self._export_and_parse(), self.local_paths)

        merged = duckdb_get_table(DST_PROJECT, f"missing_codes_{DST_PROJECT}", "logs")
        assert sorted(merged.rows()) == [
            ("Don't know", "-99"),
            ("N/A", "-66"),
            ("Refused", "-88"),
        ]

    def test_page_with_existing_name_writes_no_check_tables(
        self, mock_service_cls, mock_load_local, mock_correction_cls
    ):
        """An existing page keeps its own check tables untouched."""
        mock_service_cls.return_value = _page_config_service()
        _seed_source_project()
        bundle = self._export_and_parse()
        mock_service_cls.return_value = _page_config_service(page_exists=True)

        apply_project_config(DST_PROJECT, bundle, self.local_paths)

        for prefix in CHECK_TABLES:
            assert duckdb_get_table(
                DST_PROJECT, f"{prefix}_{PAGE_ID}", "logs"
            ).is_empty()

    def test_page_with_unimported_dataset_writes_no_check_tables(
        self, mock_service_cls, mock_load_local, mock_correction_cls
    ):
        """A page skipped because its dataset wasn't imported writes no tables."""
        mock_service_cls.return_value = _page_config_service()
        _seed_source_project()

        result = apply_project_config(
            DST_PROJECT, self._export_and_parse(), local_file_paths={}
        )

        assert result.pages_created == []
        for prefix in CHECK_TABLES:
            assert duckdb_get_table(
                DST_PROJECT, f"{prefix}_{PAGE_ID}", "logs"
            ).is_empty()

    def test_export_includes_record_level_decisions_by_default(
        self, mock_service_cls, mock_load_local, mock_correction_cls
    ):
        """By default corrections and backcheck attribution travel too."""
        mock_service_cls.return_value = _page_config_service()
        _seed_source_project()
        _seed_corrections()

        bundle = self._export_and_parse()
        result = apply_project_config(DST_PROJECT, bundle, self.local_paths)

        assert bundle.corrections["household"][0]["KEY"] == "1"
        assert "bc_attribution" in bundle.pages[0].check_tables
        assert result.pages_created == [PAGE_NAME]
        assert_frame_equal(
            duckdb_get_table(DST_PROJECT, f"bc_attribution_{PAGE_ID}", "logs"),
            CHECK_TABLES["bc_attribution"],
        )

    def test_export_without_record_level_decisions_imports_cleanly(
        self, mock_service_cls, mock_load_local, mock_correction_cls
    ):
        """Unticked: no corrections or attribution, and the bundle still applies."""
        mock_service_cls.return_value = _page_config_service()
        _seed_source_project()
        _seed_corrections()

        bundle = self._export_and_parse(include_record_level=False)
        result = apply_project_config(DST_PROJECT, bundle, self.local_paths)

        assert bundle.corrections == {}
        assert "bc_attribution" not in bundle.pages[0].check_tables
        assert "duplicates" in bundle.pages[0].check_tables
        assert result.pages_created == [PAGE_NAME]
        assert result.correction_failures == []
        assert duckdb_get_table(
            DST_PROJECT, f"bc_attribution_{PAGE_ID}", "logs"
        ).is_empty()
        assert duckdb_get_table(DST_PROJECT, "corr_log_household", "logs").is_empty()
        assert_frame_equal(
            duckdb_get_table(DST_PROJECT, f"duplicates_{PAGE_ID}", "logs"),
            CHECK_TABLES["duplicates"],
        )

    def test_export_no_longer_includes_missing_settings(
        self, mock_service_cls, mock_load_local, mock_correction_cls, real_duckdb
    ):
        """The retired per-page missing settings file is not exported."""
        mock_service_cls.return_value = _page_config_service()
        _seed_source_project()
        settings_dir = real_duckdb / SRC_PROJECT / "settings"
        (settings_dir / f"page_{PAGE_ID}_missing_settings.json").write_text(
            json.dumps({"threshold": 5})
        )

        bundle = self._export_and_parse()

        assert bundle.pages[0].missing_settings == {}
        assert bundle.bundle_version == BUNDLE_VERSION

    def test_apply_ignores_bundled_missing_settings(
        self, mock_service_cls, mock_load_local, mock_correction_cls, real_duckdb
    ):
        """An old bundle's missing settings are parsed but never written."""
        mock_service_cls.return_value = _page_config_service()
        bundle = ProjectConfigBundle(
            exported_from_project="Old",
            exported_at="t",
            datasets=[ImportSourceEntry(alias="household", source="local storage")],
            pages=[
                ProjectPageBundle(
                    config={"page_name": PAGE_NAME, "survey_data_name": "household"},
                    missing_settings={"threshold": 5},
                )
            ],
        )

        result = apply_project_config(DST_PROJECT, bundle, self.local_paths)

        assert result.pages_created == [PAGE_NAME]
        settings_dir = real_duckdb / DST_PROJECT / "settings"
        assert not (settings_dir / f"page_{PAGE_ID}_missing_settings.json").exists()

    def test_round_trip_preserves_date_columns(
        self, mock_service_cls, mock_load_local, mock_correction_cls
    ):
        """A pl.Date column in a check table arrives as pl.Date, not a string."""
        mock_service_cls.return_value = _page_config_service()
        _seed_source_project()
        with_date = pl.DataFrame(
            {"survey_key": ["k1", "k2"], "date": [date(2026, 8, 28), None]},
            schema={"survey_key": pl.String, "date": pl.Date},
        )
        duckdb_save_table(SRC_PROJECT, with_date, f"bc_attribution_{PAGE_ID}", "logs")

        apply_project_config(DST_PROJECT, self._export_and_parse(), self.local_paths)

        assert_frame_equal(
            duckdb_get_table(DST_PROJECT, f"bc_attribution_{PAGE_ID}", "logs"),
            with_date,
        )

    def test_unbuildable_dtype_falls_back_to_string_and_is_logged(
        self, mock_service_cls, mock_load_local, mock_correction_cls, caplog
    ):
        """A dtype that can't be rebuilt from its name is logged, then read as text."""
        mock_service_cls.return_value = _page_config_service()
        bundle = ProjectConfigBundle(
            exported_from_project="Edited",
            exported_at="t",
            datasets=[ImportSourceEntry(alias="household", source="local storage")],
            pages=[
                ProjectPageBundle(
                    config={"page_name": PAGE_NAME, "survey_data_name": "household"},
                    check_tables={"duplicates": [{"search_type": "exact"}]},
                    check_table_schemas={"duplicates": {"search_type": "Array"}},
                )
            ],
        )

        with caplog.at_level(logging.WARNING, logger="datasure.utils.project_config"):
            apply_project_config(DST_PROJECT, bundle, self.local_paths)

        assert "Array" in caplog.text
        assert_frame_equal(
            duckdb_get_table(DST_PROJECT, f"duplicates_{PAGE_ID}", "logs"),
            pl.DataFrame({"search_type": ["exact"]}, schema={"search_type": pl.String}),
        )


class TestBundleVersionWarning:
    """Bundles from before check tables and missing codes are flagged."""

    def test_old_bundle_parses_and_is_warned_about(self):
        """A bundle with no bundle_version parses and produces a warning."""
        bundle = parse_project_config(
            json.dumps(
                {
                    "datasure_config_version": 1,
                    "exported_from_project": "Old Project",
                    "exported_at": "2026-01-01T00:00:00",
                    "pages": [
                        {
                            "config": {"page_name": "HFC"},
                            "missing_settings": {"threshold": 5},
                        }
                    ],
                }
            )
        )

        assert bundle.missing_codes == []
        assert bundle.pages[0].check_tables == {}
        assert bundle.pages[0].missing_settings == {"threshold": 5}
        warning = bundle_version_warning(bundle)
        assert warning is not None
        assert "check tables" in warning
        assert "missing codes" in warning

    def test_current_bundle_has_no_warning(self):
        """A bundle written by this version is not flagged."""
        bundle = ProjectConfigBundle(
            bundle_version=BUNDLE_VERSION,
            exported_from_project="p",
            exported_at="t",
        )
        assert bundle_version_warning(bundle) is None


class TestConfigSummary:
    """The import summary checklist lists check tables and missing codes."""

    @patch("streamlit.markdown")
    def test_summary_lists_check_tables_and_missing_codes(self, mock_markdown):
        """Counts of check tables and missing codes appear in the checklist."""
        bundle = ProjectConfigBundle(
            bundle_version=BUNDLE_VERSION,
            exported_from_project="p",
            exported_at="t",
            pages=[
                ProjectPageBundle(
                    config={"page_name": "HFC"},
                    check_tables={"duplicates": [{"a": 1}], "outliers": [{"a": 1}]},
                )
            ],
            missing_codes=[{"label": "Refused", "codes": "-88"}],
        )

        _render_config_summary(bundle)

        lines = " ".join(c.args[0] for c in mock_markdown.call_args_list)
        assert "2 check tables" in lines
        assert "1 missing code" in lines


class TestAddConfigurationRerun:
    """Regression test for the rerun=False bulk-import path."""

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.duckdb_save_table")
    @patch.object(ConfigurationService, "_add_page_file")
    def test_rerun_false_does_not_call_st_rerun(
        self, mock_add_page_file, mock_save_table, mock_st
    ):
        """add_configuration(rerun=False) must not call st.rerun()."""
        from datasure.models.schemas import CheckConfiguration

        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=pl.DataFrame())

        service.add_configuration(
            CheckConfiguration(
                page_name="New Page", survey_data_name="survey_1", survey_key="key"
            ),
            rerun=False,
        )

        mock_st.rerun.assert_not_called()
