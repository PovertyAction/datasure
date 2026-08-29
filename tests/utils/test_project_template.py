"""Tests for project template export/import (issue #251)."""

import json
from unittest.mock import Mock, patch

import polars as pl
import pytest

from datasure.models.schemas import (
    ImportSourceEntry,
    ProjectPageBundle,
    ProjectTemplateBundle,
)
from datasure.utils.config_utils import ConfigurationService
from datasure.utils.project_template import (
    _stored_username_for_server,
    apply_project_template,
    export_project_template,
    missing_credentials,
    missing_local_files,
    parse_project_template,
)
from datasure.utils.reapply_utils import ReapplyFailure

PROJECT_ID = "test_survey_project_1001"


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the conftest autouse fixture: these tests mock duckdb per-test."""


# === BUNDLE PARSE / ROUND TRIP === #


class TestBundleRoundTrip:
    """Test ProjectTemplateBundle serialization and parsing."""

    def test_round_trip(self):
        """A bundle survives a dump-to-JSON, parse-back cycle unchanged."""
        bundle = ProjectTemplateBundle(
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
        parsed = parse_project_template(raw)

        assert parsed == bundle

    def test_parse_rejects_invalid_json(self):
        """Malformed JSON raises rather than silently producing an empty bundle."""
        with pytest.raises(json.JSONDecodeError):
            parse_project_template("not json")

    def test_parse_defaults_missing_optional_fields(self):
        """A minimal bundle (no datasets/prep/pages/corrections) still parses."""
        bundle = parse_project_template(
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


class TestExportProjectTemplate:
    """Test export_project_template."""

    @patch("datasure.utils.project_template.get_cache_path")
    @patch("datasure.utils.project_template.ConfigurationService")
    @patch("datasure.utils.project_template.duckdb_get_table")
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

        bundle = export_project_template(PROJECT_ID, "ACME Endline 2026")

        assert bundle.exported_from_project == "ACME Endline 2026"
        assert [d.alias for d in bundle.datasets] == ["household"]
        assert bundle.datasets[0].server == "acme"
        assert bundle.prep_steps["household"] == [{"action": "transform column(s)"}]
        assert bundle.corrections["household"][0]["KEY"] == "1"
        assert bundle.pages[0].config["page_name"] == "Household HFC"

    @patch("datasure.utils.project_template.get_cache_path")
    @patch("datasure.utils.project_template.ConfigurationService")
    @patch("datasure.utils.project_template.duckdb_get_table")
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

        bundle = export_project_template(PROJECT_ID, "ACME Endline 2026")

        assert bundle.pages[0].settings == {"missing": {"threshold": 5}}
        assert bundle.pages[0].missing_settings == {}


# === RESOLUTION HELPERS === #


class TestResolutionHelpers:
    """Test missing_credentials / missing_local_files / _stored_username_for_server."""

    @patch("datasure.utils.project_template.list_stored_credentials")
    def test_missing_credentials_excludes_stored_servers(self, mock_list_creds):
        """A server with a stored credential is not reported as missing."""
        mock_list_creds.return_value = {
            "credentials": {"scto_login - acme - a@x.com": {"server": "acme"}}
        }
        bundle = ProjectTemplateBundle(
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
        bundle = ProjectTemplateBundle(
            exported_from_project="p",
            exported_at="t",
            datasets=[
                ImportSourceEntry(alias="household", source="SurveyCTO", server="acme"),
                ImportSourceEntry(alias="tracking", source="local storage"),
            ],
        )

        result = missing_local_files(bundle)

        assert [d.alias for d in result] == ["tracking"]

    @patch("datasure.utils.project_template.list_stored_credentials")
    def test_stored_username_for_server_found(self, mock_list_creds):
        """Returns the username stored for a matching server."""
        mock_list_creds.return_value = {
            "credentials": {"k": {"server": "acme", "username": "k@x.com"}}
        }
        assert _stored_username_for_server(PROJECT_ID, "acme") == "k@x.com"

    @patch("datasure.utils.project_template.list_stored_credentials")
    def test_stored_username_for_server_not_found(self, mock_list_creds):
        """Returns None when no credential is stored for that server."""
        mock_list_creds.return_value = {"credentials": {}}
        assert _stored_username_for_server(PROJECT_ID, "acme") is None


# === APPLY === #


class TestApplyProjectTemplate:
    """Test apply_project_template."""

    def _config_service_mock(self, page_exists=False):
        service = Mock()
        service.page_name_exists.return_value = page_exists
        return service

    @patch("datasure.utils.project_template.CorrectionProcessor")
    @patch("datasure.utils.project_template.ConfigurationService")
    @patch("datasure.utils.project_template.prep_apply_action")
    @patch("datasure.utils.project_template.load_local_data")
    @patch("datasure.utils.project_template.duckdb_save_table")
    @patch("datasure.utils.project_template.duckdb_get_table")
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

        bundle = ProjectTemplateBundle(
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

        result = apply_project_template(
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

    @patch("datasure.utils.project_template.ConfigurationService")
    @patch("datasure.utils.project_template.duckdb_get_table")
    def test_local_dataset_without_path_is_skipped(
        self, mock_get_table, mock_config_service_cls
    ):
        """A local-storage dataset with no resolved path is skipped, not fatal."""
        mock_get_table.return_value = pl.DataFrame()
        mock_config_service_cls.return_value = self._config_service_mock()

        bundle = ProjectTemplateBundle(
            exported_from_project="p",
            exported_at="t",
            datasets=[ImportSourceEntry(alias="tracking", source="local storage")],
        )

        result = apply_project_template(PROJECT_ID, bundle, local_file_paths={})

        assert result.datasets_imported == []
        assert result.datasets_skipped == [
            ReapplyFailure("tracking", "No file path was provided")
        ]

    @patch("datasure.utils.project_template.list_stored_credentials")
    @patch("datasure.utils.project_template.ConfigurationService")
    @patch("datasure.utils.project_template.duckdb_get_table")
    def test_surveycto_dataset_without_credentials_is_skipped(
        self, mock_get_table, mock_config_service_cls, mock_list_creds
    ):
        """A SurveyCTO dataset with no stored credentials is skipped, not fatal."""
        mock_get_table.return_value = pl.DataFrame()
        mock_config_service_cls.return_value = self._config_service_mock()
        mock_list_creds.return_value = {"credentials": {}}

        bundle = ProjectTemplateBundle(
            exported_from_project="p",
            exported_at="t",
            datasets=[
                ImportSourceEntry(
                    alias="household", source="SurveyCTO", server="acme", form_id="hh"
                )
            ],
        )

        result = apply_project_template(PROJECT_ID, bundle, local_file_paths={})

        assert result.datasets_imported == []
        assert len(result.datasets_skipped) == 1
        assert result.datasets_skipped[0].step == "household"

    @patch("datasure.utils.project_template.ConfigurationService")
    @patch("datasure.utils.project_template.duckdb_get_table")
    @patch("datasure.utils.project_template.duckdb_save_table")
    @patch("datasure.utils.project_template.load_local_data")
    def test_page_referencing_unimported_dataset_is_skipped(
        self, mock_load_local, mock_save_table, mock_get_table, mock_config_service_cls
    ):
        """A page whose survey dataset failed to import is skipped, not created."""
        mock_get_table.return_value = pl.DataFrame()
        mock_config_service_cls.return_value = self._config_service_mock()

        bundle = ProjectTemplateBundle(
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
        result = apply_project_template(PROJECT_ID, bundle, local_file_paths={})

        assert result.pages_created == []
        assert result.pages_skipped == [
            ReapplyFailure("Household HFC", "Dataset 'household' was not imported")
        ]

    @patch("datasure.utils.project_template.ConfigurationService")
    @patch("datasure.utils.project_template.duckdb_get_table")
    def test_page_with_existing_name_is_skipped(
        self, mock_get_table, mock_config_service_cls
    ):
        """A page whose name already exists locally is skipped, not overwritten."""
        mock_get_table.return_value = pl.DataFrame()
        mock_config_service_cls.return_value = self._config_service_mock(
            page_exists=True
        )

        bundle = ProjectTemplateBundle(
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

        result = apply_project_template(PROJECT_ID, bundle, local_file_paths={})

        assert result.pages_created == []
        assert result.pages_skipped[0].reason == "A page with this name already exists"


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
