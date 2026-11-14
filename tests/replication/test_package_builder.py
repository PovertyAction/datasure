"""Integration smoke tests for build_replication_package."""

from __future__ import annotations

import zipfile
from io import BytesIO
from unittest.mock import patch

import polars as pl
import pytest
import yaml

from datasure.processing.correction_log import CORRECTION_LOG_SCHEMA
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

    def test_zip_leaves_out_personal_view_state(self, zip_bytes):
        """Saved filters and selections are not part of the data processing."""
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            for name in zf.namelist():
                assert "settings" not in name.lower()
                assert b"view_state" not in zf.read(name)

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

    @pytest.mark.parametrize(
        ("action", "prep_args"),
        [
            # Emitter raises on a bad value
            ("remove row(s)", '{"method": "by row index", "value": ["abc"]}'),
            # Emitter has no Stata translation and raises no error
            ("add new column", '{"column_names": "uid", "method": "uuid"}'),
        ],
    )
    def test_untranslatable_prep_step_warns_and_still_builds(self, action, prep_args):
        warnings: list[str] = []
        bad_log = pl.DataFrame(
            {
                "action": [action],
                "description": ["Bad step"],
                "prep_args": [prep_args],
                "action_index": [1],
            }
        )

        def _duckdb_get(project_id, table, db_name):
            if "prep_log" in table:
                return bad_log
            if "corr_log" in table:
                return _CORR_LOG
            return _mock_loader(project_id, table, db_name)

        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=_duckdb_get,
        ):
            zip_bytes = build_replication_package(
                project_id="p",
                project_name="P",
                survey_name="S",
                alias="s",
                key_col="key",
                on_warning=warnings.append,
            )
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            name = next(n for n in zf.namelist() if n.endswith("prepare_data.do"))
            prepare_do = zf.read(name).decode()
        assert "* NOTE: step 1 could not be translated" in prepare_do
        assert len(warnings) == 1


class TestPackageKeepsAcceptancesInAuditLog:
    def test_correction_log_csv_keeps_accept_rows(self):
        corr_log = pl.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02"],
                "KEY": ["k1", "k2"],
                "ID": [None, None],
                "action": ["accept", "modify value"],
                "column": ["age", "age"],
                "current_value": ["25", "30"],
                "new_value": [None, "31"],
                "reason": ["verified", "typo"],
                "source": ["outliers", "corrections_page"],
                "check_type": ["outliers", None],
                "user": ["ama", "kofi"],
            }
        )

        def _duckdb_get(project_id, table, db_name):
            if "prep_log" in table:
                return _PREP_LOG
            if "corr_log" in table:
                return corr_log
            return _mock_loader(project_id, table, db_name)

        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=_duckdb_get,
        ):
            zip_bytes = build_replication_package(
                project_id="p",
                project_name="P",
                survey_name="S",
                alias="s",
                key_col="key",
            )

        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            log_csv = zf.read("replication_p_s/4_output/3_logs/correction_log.csv")
            corrections_do = zf.read("replication_p_s/2_scripts/4_corrections.do")

        audit = pl.read_csv(BytesIO(log_csv))
        assert audit.select("KEY", "action", "check_type", "user").rows() == [
            ("k1", "accept", "outliers", "ama"),
            ("k2", "modify value", None, "kofi"),
        ]
        assert b'"k1"' not in corrections_do
        assert b'"k2"' in corrections_do

    def test_empty_correction_log_csv_has_full_header(self):
        def _duckdb_get(project_id, table, db_name):
            if "prep_log" in table:
                return _PREP_LOG
            return _mock_loader(project_id, table, db_name)

        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=_duckdb_get,
        ):
            zip_bytes = build_replication_package(
                project_id="p",
                project_name="P",
                survey_name="S",
                alias="s",
                key_col="key",
            )

        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            header = (
                zf.read("replication_p_s/4_output/3_logs/correction_log.csv")
                .decode()
                .strip()
            )
        assert header == (
            "date,KEY,ID,action,column,current_value,new_value,reason,"
            "status,status_reason,source,check_type,severity,user"
        )


class TestPackageCountsAndLegacyLogs:
    def _build(self, corr_log: pl.DataFrame) -> zipfile.ZipFile:
        def _duckdb_get(project_id, table, db_name):
            if "prep_log" in table:
                return _PREP_LOG
            if "corr_log" in table:
                return corr_log
            return _mock_loader(project_id, table, db_name)

        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=_duckdb_get,
        ):
            zip_bytes = build_replication_package(
                project_id="p",
                project_name="P",
                survey_name="S",
                alias="s",
                key_col="key",
            )
        return zipfile.ZipFile(BytesIO(zip_bytes))

    def test_readme_counts_exclude_acceptances(self):
        corr_log = pl.DataFrame(
            {
                "date": ["2026-01-01"] * 3,
                "KEY": ["k1", "k2", "k3"],
                "ID": [None] * 3,
                "action": ["accept", "accept", "remove row"],
                "column": ["age", "age", None],
                "current_value": ["25", "30", None],
                "new_value": [None] * 3,
                "reason": ["ok"] * 3,
            }
        )

        with self._build(corr_log) as zf:
            readme = zf.read("replication_p_s/README.md").decode()

        assert "Corrections applied          |       1 |" in readme
        assert "accept" not in readme

    def test_legacy_log_exports_with_backfilled_columns(self):
        with self._build(
            pl.DataFrame(
                {
                    "date": ["2026-01-01"],
                    "KEY": ["k1"],
                    "ID": [None],
                    "action": ["remove row"],
                    "column": [None],
                    "current_value": [None],
                    "new_value": [None],
                    "reason": ["dup"],
                }
            )
        ) as zf:
            audit = pl.read_csv(
                BytesIO(zf.read("replication_p_s/4_output/3_logs/correction_log.csv"))
            )

        assert audit["source"].to_list() == ["corrections_page"]
        assert audit["status"].to_list() == ["Successful"]
        assert "check_type" in audit.columns
        assert audit["user"].to_list() == [None]


class TestExcludeReviewerNames:
    _LOG_PATH = "replication_p_s/4_output/3_logs/correction_log.csv"

    @staticmethod
    def _corr_log() -> pl.DataFrame:
        return pl.DataFrame(
            {
                "date": ["2026-01-01", "2026-01-02"],
                "KEY": ["k1", "k2"],
                "ID": [None, None],
                "action": ["accept", "modify value"],
                "column": ["age", "age"],
                "current_value": ["25", "30"],
                "new_value": [None, "31"],
                "reason": ["verified", "typo"],
                "source": ["outliers", "corrections_page"],
                "check_type": ["outliers", None],
                "user": ["Ama Mensah", "kofi"],
            }
        )

    @staticmethod
    def _duckdb_get(corr_log: pl.DataFrame):
        def _get(project_id, table, db_name):
            if "prep_log" in table:
                return _PREP_LOG
            if "corr_log" in table:
                return corr_log
            return _mock_loader(project_id, table, db_name)

        return _get

    def _build(self, corr_log: pl.DataFrame, **kwargs) -> pl.DataFrame:
        with patch(
            "datasure.replication.package_builder.duckdb_get_table",
            side_effect=self._duckdb_get(corr_log),
        ):
            zip_bytes = build_replication_package(
                project_id="p",
                project_name="P",
                survey_name="S",
                alias="s",
                key_col="key",
                **kwargs,
            )
        with zipfile.ZipFile(BytesIO(zip_bytes)) as zf:
            return pl.read_csv(BytesIO(zf.read(self._LOG_PATH)), infer_schema_length=0)

    def test_names_kept_by_default(self):
        audit = self._build(self._corr_log())
        assert audit["user"].to_list() == ["Ama Mensah", "kofi"]

    def test_names_kept_when_option_off(self):
        audit = self._build(self._corr_log(), exclude_reviewer_names=False)
        assert audit["user"].to_list() == ["Ama Mensah", "kofi"]

    def test_names_blanked_when_option_on(self):
        audit = self._build(self._corr_log(), exclude_reviewer_names=True)
        assert audit["user"].to_list() == [None, None]

    def test_blanked_export_keeps_full_schema_and_other_columns(self):
        audit = self._build(self._corr_log(), exclude_reviewer_names=True)
        assert set(audit.columns) == set(CORRECTION_LOG_SCHEMA)
        assert audit.select("KEY", "action", "reason").rows() == [
            ("k1", "accept", "verified"),
            ("k2", "modify value", "typo"),
        ]

    def test_blanking_an_empty_log_keeps_full_header(self):
        audit = self._build(pl.DataFrame(), exclude_reviewer_names=True)
        assert audit.is_empty()
        assert audit.columns == list(CORRECTION_LOG_SCHEMA)

    def test_stored_log_not_modified(self):
        stored = self._corr_log()
        with (
            patch("datasure.utils.duckdb_utils.duckdb_save_table") as save,
            patch("datasure.utils.duckdb_utils.duckdb_remove_table") as remove,
            patch("datasure.utils.duckdb_utils.duckdb_delete_rows") as delete,
        ):
            self._build(stored, exclude_reviewer_names=True)
        assert stored["user"].to_list() == ["Ama Mensah", "kofi"]
        save.assert_not_called()
        remove.assert_not_called()
        delete.assert_not_called()


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
    if "prep_log" in name or name == "pii_salt" or "pii_code_map" in name:
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
        patch("datasure.utils.duckdb_utils.duckdb_save_table"),
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


class TestBuildReplicationPackagePseudonyms:
    """Hash and code decisions produce deterministic pseudonyms in exports."""

    _RAW = pl.DataFrame(
        {
            "key": ["k1", "k2", "k3"],
            "enum_name": ["Kailash Khosla", "Arjun Patel", "Kailash Khosla"],
            "village_name": ["Rampur", "Sitapur", "Rampur"],
        }
    )
    _FLAGS = pl.DataFrame(
        {
            "column": ["enum_name", "village_name"],
            "source": ["fuzzy"] * 2,
            "entity_type": ["PERSON", None],
            "hit_rate": [1.0] * 2,
            "sample_matches": [""] * 2,
            "decision": ["hash", "code"],
            "mask_label": ["[PERSON]", "*****"],
            "scanned_at": ["2026-01-01T00:00:00"] * 2,
        }
    )

    @pytest.fixture()
    def zip_file(self):
        state: dict = {}

        def _get(project_id, table, db_name, **kwargs):
            name = str(table)
            if "pii_flags" in name:
                return self._FLAGS
            if name == "pii_salt":
                return state.get("salt", pl.DataFrame())
            if "pii_code_map" in name:
                return state.get("codes", pl.DataFrame())
            if "prep_log" in name or "corr_log" in name:
                return pl.DataFrame()
            return self._RAW

        def _save(project_id, data, alias="", db_name="", **kwargs):
            if alias == "pii_salt":
                state["salt"] = data
            if "pii_code_map" in alias:
                state["codes"] = data

        with (
            patch(
                "datasure.replication.package_builder.duckdb_get_table",
                side_effect=_get,
            ),
            patch("datasure.utils.duckdb_utils.duckdb_get_table", side_effect=_get),
            patch("datasure.utils.duckdb_utils.duckdb_save_table", side_effect=_save),
        ):
            blob = build_replication_package(
                project_id="test-proj",
                project_name="Test Project",
                survey_name="Baseline Survey",
                alias="baseline",
                key_col="key",
                include_pii=False,
            )
        return zipfile.ZipFile(BytesIO(blob))

    def _read(self, zip_file, suffix: str) -> str:
        name = next(n for n in zip_file.namelist() if n.endswith(suffix))
        return zip_file.read(name).decode()

    def test_hash_tokens_deterministic_in_raw_csv(self, zip_file):
        raw_csv = self._read(zip_file, "_raw.csv")
        assert "Kailash" not in raw_csv
        person_tokens = [
            cell
            for line in raw_csv.splitlines()[1:]
            for cell in line.split(",")
            if cell.startswith("PERSON_")
        ]
        assert len(person_tokens) == 3
        # k1 and k3 share the same name → identical pseudonyms
        assert person_tokens[0] == person_tokens[2] != person_tokens[1]

    def test_code_tokens_in_raw_csv(self, zip_file):
        raw_csv = self._read(zip_file, "_raw.csv")
        assert "Rampur" not in raw_csv
        assert "VILLAGE_NAME_" in raw_csv

    def test_readme_lists_pseudonym_columns(self, zip_file):
        readme = self._read(zip_file, "README.md")
        assert "Hashed columns" in readme
        assert "Recoded columns" in readme
