"""Integration smoke tests for build_replication_package."""

from __future__ import annotations

import zipfile
from io import BytesIO
from unittest.mock import patch

import polars as pl
import pytest
import yaml

from datasure.replication.package_builder import (
    _action_summary,
    _load_corrected,
    _load_correction_log,
    _load_dataset,
    _load_prep_log,
    _serialize_prep_args,
    _to_parquet_bytes,
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


class TestToParquetBytes:
    def test_columnless_dataframe_returns_empty_bytes(self):
        assert _to_parquet_bytes(pl.DataFrame()) == b""

    def test_empty_but_schema_dataframe_returns_valid_parquet(self):
        df = pl.DataFrame(schema={"key": pl.String, "age": pl.Int64})
        result = _to_parquet_bytes(df)
        assert result != b""
        read_back = pl.read_parquet(BytesIO(result))
        assert read_back.schema == df.schema
        assert read_back.height == 0

    def test_non_empty_dataframe_round_trips(self):
        df = pl.DataFrame({"key": ["k1", "k2"], "age": [25, 30]})
        result = _to_parquet_bytes(df)
        read_back = pl.read_parquet(BytesIO(result))
        assert read_back.equals(df)


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
        assert any("README.md" in n for n in names)

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

    def test_zip_contains_data_dict_yaml(self, zip_bytes):
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
            assert any("data-dict.yaml" in n for n in names)
            yaml_name = next(n for n in names if n.endswith("data-dict.yaml"))
            content = zf.read(yaml_name).decode()
        parsed = yaml.safe_load(content)
        assert parsed["$version"] == "0.1.0"

    def test_zip_contains_raw_parquet(self, zip_bytes):
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        assert any("_raw.parquet" in n for n in names)

    def test_zip_contains_python_scripts(self, zip_bytes):
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        for script in [
            "0_main.py",
            "3_prepare_data.py",
            "4_corrections.py",
        ]:
            assert any(script in n for n in names), f"{script} missing from zip"

    def test_zip_has_no_python_import_script(self, zip_bytes):
        # Unlike Stata, the Python pipeline reads the already-bundled,
        # correctly-typed raw Parquet directly — no import step needed.
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        assert not any("2_import_data.py" in n for n in names)

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


class TestBuildReplicationPackageNoRawData:
    """Regression test: a truly columnless raw table must not produce an
    invalid 0-byte "_raw.parquet" entry (see _to_parquet_bytes).
    """

    @pytest.fixture()
    def zip_bytes(self):
        def _duckdb_get(project_id, table, db_name):
            return pl.DataFrame()

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

    def test_is_valid_zip(self, zip_bytes):
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            assert zf.testzip() is None

    def test_no_raw_parquet_written(self, zip_bytes):
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            names = zf.namelist()
        assert not any("_raw.parquet" in n for n in names)
        assert any("_raw.csv" in n for n in names)


# ---------------------------------------------------------------------------
# PII export gate
# ---------------------------------------------------------------------------

_PII_RAW = pl.DataFrame(
    {
        "key": ["k1", "k2"],
        "enum_name": ["Kailash Khosla", "Arjun Patel"],
        "household_latitude": [26.08, 25.91],
        "age": [34, 51],
    }
)
_PII_FLAGS = pl.DataFrame(
    {
        "column": ["enum_name", "household_latitude", "age"],
        "source": ["fuzzy", "fuzzy", "name_match"],
        "entity_type": ["PERSON", None, None],
        "hit_rate": [1.0, 1.0, 1.0],
        "sample_matches": ["Kailash Khosla", "", ""],
        "decision": ["mask", "drop", "keep"],
        "mask_label": ["[PERSON]", "*****", "*****"],
        "scanned_at": ["2026-01-01T00:00:00"] * 3,
    }
)
_PII_CORR_LOG = pl.DataFrame(
    {
        "date": ["2026-01-01"],
        "KEY": ["k1"],
        "ID": [None],
        "action": ["modify value"],
        "column": ["enum_name"],
        "current_value": ["Kailash Khosla"],
        "new_value": ["K. Khosla"],
        "reason": ["typo"],
    }
)


def _pii_duckdb_get(project_id, table, db_name, **kwargs):
    name = str(table)
    if "pii_flags" in name:
        return _PII_FLAGS
    if "corr_log" in name:
        return _PII_CORR_LOG
    if "prep_log" in name:
        return pl.DataFrame()
    return _PII_RAW


def _build_pii_package(include_pii: bool) -> bytes:
    with (
        patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=_pii_duckdb_get,
        ),
        patch(
            "datasure.utils.duckdb_utils.duckdb_get_table",
            side_effect=_pii_duckdb_get,
        ),
    ):
        return build_replication_package(
            project_id="test-proj",
            project_name="Test Project",
            survey_name="Baseline Survey",
            alias="baseline",
            key_col="key",
            include_pii=include_pii,
        )


class TestBuildReplicationPackageDeidentified:
    @pytest.fixture()
    def zip_file(self):
        return zipfile.ZipFile(BytesIO(_build_pii_package(include_pii=False)))

    def _read(self, zip_file, suffix: str) -> str:
        name = next(n for n in zip_file.namelist() if n.endswith(suffix))
        return zip_file.read(name).decode()

    def test_masked_column_in_raw_csv(self, zip_file):
        raw_csv = self._read(zip_file, "_raw.csv")
        assert "Kailash" not in raw_csv
        assert "[PERSON]" in raw_csv

    def test_dropped_column_absent(self, zip_file):
        raw_csv = self._read(zip_file, "_raw.csv")
        assert "household_latitude" not in raw_csv

    def test_kept_column_intact(self, zip_file):
        raw_csv = self._read(zip_file, "_raw.csv")
        assert "age" in raw_csv
        assert "34" in raw_csv

    def test_correction_log_redacted(self, zip_file):
        corr = self._read(zip_file, "correction_log.csv")
        assert "Kailash" not in corr

    def test_codebook_samples_redacted(self, zip_file):
        codebook = self._read(zip_file, "codebook.csv")
        assert "Kailash" not in codebook

    def test_data_dict_annotated_and_redacted(self, zip_file):
        dd = self._read(zip_file, "data-dict.yaml")
        assert "Redacted (PII)" in dd
        assert "Kailash" not in dd

    def test_no_deidentify_script_or_flags_csv(self, zip_file):
        names = zip_file.namelist()
        assert not any("5_deidentify" in n for n in names)
        assert not any("pii_flags.csv" in n for n in names)

    def test_readme_states_deidentified(self, zip_file):
        readme = self._read(zip_file, "README.md")
        assert "exported de-identified" in readme
        assert "indirect identifiers" in readme
        assert "`enum_name`" in readme


class TestBuildReplicationPackageWithPii:
    @pytest.fixture()
    def zip_file(self):
        return zipfile.ZipFile(BytesIO(_build_pii_package(include_pii=True)))

    def _read(self, zip_file, suffix: str) -> str:
        name = next(n for n in zip_file.namelist() if n.endswith(suffix))
        return zip_file.read(name).decode()

    def test_data_left_untouched(self, zip_file):
        raw_csv = self._read(zip_file, "_raw.csv")
        assert "Kailash" in raw_csv
        assert "household_latitude" in raw_csv

    def test_deidentify_script_bundled_and_parses(self, zip_file):
        import ast

        script = self._read(zip_file, "5_deidentify_data.py")
        ast.parse(script)
        assert "('enum_name', 'mask', '[PERSON]')" in script
        assert "('household_latitude', 'drop', '*****')" in script

    def test_flags_audit_log_bundled(self, zip_file):
        flags_csv = self._read(zip_file, "pii_flags.csv")
        assert "enum_name" in flags_csv

    def test_readme_states_with_pii(self, zip_file):
        readme = self._read(zip_file, "README.md")
        assert "WITH personally identifiable" in readme
        assert "5_deidentify_data.py" in readme
