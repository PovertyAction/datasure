"""Integration smoke tests for build_replication_package."""

from __future__ import annotations

import zipfile
from io import BytesIO
from unittest.mock import patch

import polars as pl
import pytest

from datasure.replication.package_builder import (
    _action_summary,
    _load_corrected,
    _load_correction_log,
    _load_dataset,
    _load_prep_log,
    _serialize_prep_args,
    build_replication_package,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

_RAW = pl.DataFrame({"key": ["k1", "k2"], "age": ["25", "30"]})
_PREP_LOG = pl.DataFrame(
    schema={
        "action": pl.String,
        "description": pl.String,
        "prep_args": pl.String,
        "action_index": pl.Int64,
    }
)
_CORR_LOG = pl.DataFrame(
    schema={
        "date": pl.String,
        "KEY": pl.String,
        "ID": pl.String,
        "action": pl.String,
        "column": pl.String,
        "current_value": pl.String,
        "new_value": pl.String,
        "reason": pl.String,
    }
)


def _mock_loader(project_id, alias, db_name):
    tables = {
        "raw": _RAW,
        "prep": _RAW,
        "corrected": pl.DataFrame(),
    }
    return tables.get(db_name, pl.DataFrame())


# ---------------------------------------------------------------------------
# Loader helpers
# ---------------------------------------------------------------------------


class TestLoadDataset:
    def test_returns_dataframe_on_success(self):
        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            return_value=_RAW,
        ):
            df = _load_dataset("proj", "alias", "raw")
        assert df.height == 2

    def test_returns_empty_on_exception(self):
        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=RuntimeError("table not found"),
        ):
            df = _load_dataset("proj", "alias", "raw")
        assert df.is_empty()


class TestLoadCorrected:
    def test_returns_corrected_when_non_empty(self):
        corrected = pl.DataFrame({"key": ["k1"], "age": ["25"]})
        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            return_value=corrected,
        ):
            df, applied = _load_corrected("proj", "alias")
        assert applied is True
        assert df.height == 1

    def test_falls_back_to_prep_when_corrected_empty(self):
        prep = pl.DataFrame({"key": ["k1", "k2"], "age": ["25", "30"]})

        def _side_effect(project_id, alias, db_name):
            return pl.DataFrame() if db_name == "corrected" else prep

        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=_side_effect,
        ):
            df, applied = _load_corrected("proj", "alias")
        assert applied is False
        assert df.height == 2

    def test_duckdb_error_returns_empty(self):
        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=RuntimeError("db error"),
        ):
            df, applied = _load_corrected("proj", "alias")
        assert df.is_empty()
        assert applied is False


class TestLoadPrepLog:
    def test_returns_empty_on_exception(self):
        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=Exception("missing"),
        ):
            df = _load_prep_log("proj", "alias")
        assert df.is_empty()


class TestLoadCorrectionLog:
    def test_returns_empty_on_exception(self):
        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=Exception("missing"),
        ):
            df = _load_correction_log("proj", "alias")
        assert df.is_empty()


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestActionSummary:
    def test_empty_log_returns_empty_dict(self):
        assert _action_summary(pl.DataFrame()) == {}

    def test_counts_by_action(self):
        log = pl.DataFrame({"action": ["modify value", "modify value", "remove row"]})
        result = _action_summary(log)
        assert result["modify value"] == 2
        assert result["remove row"] == 1


class TestSerializePrepArgs:
    def test_none_returns_none(self):
        assert _serialize_prep_args(None) is None

    def test_dict_returns_json_string(self):
        result = _serialize_prep_args({"key": "val"})
        assert result == '{"key": "val"}'

    def test_non_serializable_falls_back_to_str(self):
        class Unserializable:
            def __repr__(self):
                return "Unserializable()"

        result = _serialize_prep_args(Unserializable())
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# build_replication_package smoke test
# ---------------------------------------------------------------------------


class TestBuildReplicationPackage:
    @pytest.fixture()
    def zip_bytes(self):
        def _loader(project_id, alias, db_name):
            return _mock_loader(project_id, alias, db_name)

        def _log_loader(project_id, table, db_name):
            return _PREP_LOG if "prep_log" in table else _CORR_LOG

        def _duckdb_get(project_id, table, db_name):
            if "prep_log" in table or "corr_log" in table:
                return _log_loader(project_id, table, db_name)
            return _mock_loader(project_id, table, db_name)

        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=_duckdb_get,
        ):
            return build_replication_package(
                project_id="test-proj",
                project_name="Test Project",
                survey_name="Baseline Survey",
                alias="baseline",
                key_col="key",
            )

    def test_returns_bytes(self, zip_bytes):
        assert isinstance(zip_bytes, bytes)
        assert len(zip_bytes) > 0

    def test_is_valid_zip(self, zip_bytes):
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            assert zf.testzip() is None

    def test_zip_contains_readme(self, zip_bytes):
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        assert any("0_README.txt" in n for n in names)

    def test_zip_contains_all_scripts(self, zip_bytes):
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        for script in [
            "0_main.do",
            "1_install_packages.do",
            "2_import_data.do",
            "3_prepare_data.do",
            "4_corrections.do",
        ]:
            assert any(script in n for n in names), f"{script} missing from zip"

    def test_zip_contains_raw_csv(self, zip_bytes):
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        assert any("_raw.csv" in n for n in names)

    def test_zip_contains_codebook(self, zip_bytes):
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        assert any("codebook.csv" in n for n in names)

    def test_zip_contains_audit_logs(self, zip_bytes):
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        assert any("correction_log.csv" in n for n in names)
        assert any("prep_log.csv" in n for n in names)

    def test_master_script_has_correct_pkg_path(self, zip_bytes):
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            main_do = zf.read(
                "replication_test_project_baseline_survey/2_scripts/0_main.do"
            ).decode()
        assert "replication_test_project_baseline_survey" in main_do

    def test_progress_callback_called(self):
        progress_messages = []

        def _duckdb_get(project_id, table, db_name):
            if "prep_log" in table or "corr_log" in table:
                return _PREP_LOG if "prep_log" in table else _CORR_LOG
            return _mock_loader(project_id, table, db_name)

        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=_duckdb_get,
        ):
            build_replication_package(
                project_id="p",
                project_name="P",
                survey_name="S",
                alias="s",
                key_col="key",
                on_progress=progress_messages.append,
            )
        assert len(progress_messages) > 0
