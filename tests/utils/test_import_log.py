"""Tests for import-log persistence behind the import page, on real DuckDB files."""

from datetime import datetime

import polars as pl
import pytest

from datasure.connectors.local import FileConfig
from datasure.connectors.scto import FormConfig
from datasure.utils.dataset_list import LoadInfo
from datasure.utils.duckdb_utils import (
    duckdb_get_table,
    duckdb_save_table,
    duckdb_table_exists,
    load_form_definition,
    save_form_definition,
)
from datasure.utils.import_log import (
    DatasetExistsError,
    get_load_info,
    record_load,
    remove_dataset,
    save_local_dataset,
    save_surveycto_dataset,
    set_dataset_flag,
)

PROJECT = "proj"


@pytest.fixture(autouse=True)
def project_dirs(isolated_cache):
    """Create the project's folders, as creating a project does."""
    for folder in ("settings", "data"):
        (isolated_cache / PROJECT / folder).mkdir(parents=True)


def _log() -> pl.DataFrame:
    return duckdb_get_table(PROJECT, "import_log", "logs")


def _row(alias: str) -> dict:
    return _log().filter(pl.col("alias") == alias).to_dicts()[0]


@pytest.fixture
def csv_file(tmp_path):
    path = tmp_path / "survey.csv"
    path.write_text("a,b\n1,2\n")
    return str(path)


def _form(alias="household", **overrides) -> FormConfig:
    return FormConfig.model_validate(
        {
            "alias": alias,
            "form_id": "hh_main",
            "server": "ipa-training",
            "username": "me@example.org",
            "private_key": None,
            "save_to": None,
            "attachments": False,
            **overrides,
        }
    )


class TestSaveLocalDataset:
    def test_adding_registers_the_file_marked_refresh_and_load(self, csv_file):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))

        row = _row("survey")
        assert row["source"] == "local storage"
        assert row["filename"] == csv_file
        assert (row["refresh"], row["load"], row["attachments"]) == (
            True,
            True,
            False,
        )

    def test_adding_does_not_import_the_data(self, csv_file):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))

        assert not duckdb_table_exists(PROJECT, "survey", "raw")

    def test_adding_a_clashing_alias_is_refused(self, csv_file):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))

        with pytest.raises(DatasetExistsError):
            save_local_dataset(PROJECT, FileConfig(alias="Survey", filename=csv_file))
        assert _log().height == 1

    def test_editing_updates_path_and_sheet_and_keeps_switches(
        self, csv_file, tmp_path
    ):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))
        set_dataset_flag(PROJECT, "survey", "refresh", False)
        other = tmp_path / "other.csv"
        other.write_text("a\n1\n")

        save_local_dataset(
            PROJECT, FileConfig(alias="survey", filename=str(other)), edit=True
        )

        row = _row("survey")
        assert row["filename"] == str(other)
        assert row["refresh"] is False
        assert _log().height == 1


class TestSaveSurveyctoDataset:
    def test_adding_registers_the_form(self):
        save_surveycto_dataset(PROJECT, _form(attachments=True))

        row = _row("household")
        assert row["source"] == "SurveyCTO"
        assert (row["form_id"], row["server"], row["username"]) == (
            "hh_main",
            "ipa-training",
            "me@example.org",
        )
        assert row["attachments"] is True
        assert (row["refresh"], row["load"]) == (True, True)

    def test_adding_after_a_local_file_keeps_both(self, csv_file):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))
        save_surveycto_dataset(PROJECT, _form())

        assert sorted(_log()["alias"].to_list()) == ["household", "survey"]

    def test_adding_a_clashing_alias_is_refused(self):
        save_surveycto_dataset(PROJECT, _form())

        with pytest.raises(DatasetExistsError):
            save_surveycto_dataset(PROJECT, _form(alias="Household"))

    def test_editing_updates_the_row(self):
        save_surveycto_dataset(PROJECT, _form())

        save_surveycto_dataset(
            PROJECT, _form(form_id="hh_v2", save_to="C:/out.csv"), edit=True
        )

        row = _row("household")
        assert row["form_id"] == "hh_v2"
        assert row["save_to"] == "C:/out.csv"
        assert _log().height == 1


class TestSetDatasetFlag:
    @pytest.mark.parametrize("column", ["refresh", "load", "attachments"])
    def test_switch_updates_only_that_dataset(self, column):
        save_surveycto_dataset(PROJECT, _form(alias="one"))
        save_surveycto_dataset(PROJECT, _form(alias="two"))
        before = _row("two")[column]

        set_dataset_flag(PROJECT, "one", column, not _row("one")[column])

        assert _row("one")[column] is not before
        assert _row("two")[column] is before

    def test_other_columns_are_refused(self):
        save_surveycto_dataset(PROJECT, _form())

        with pytest.raises(ValueError, match="alias"):
            set_dataset_flag(PROJECT, "household", "alias", True)


class TestRemoveDataset:
    def _imported(self, csv_file):
        save_local_dataset(PROJECT, FileConfig(alias="survey", filename=csv_file))
        save_surveycto_dataset(PROJECT, _form(alias="keep"))
        data = pl.DataFrame({"a": [1]})
        for db in ("raw", "prep", "corrected"):
            duckdb_save_table(PROJECT, data, alias="survey", db_name=db)
        save_form_definition(PROJECT, "survey", "f", "1", b"<x/>", b"")
        record_load(PROJECT, "survey")

    def test_removes_the_row_tables_form_definition_and_load_record(self, csv_file):
        self._imported(csv_file)

        remove_dataset(PROJECT, "survey")

        assert _log()["alias"].to_list() == ["keep"]
        for db in ("raw", "prep", "corrected"):
            assert not duckdb_table_exists(PROJECT, "survey", db)
        assert load_form_definition(PROJECT, "survey") is None
        assert get_load_info(PROJECT, ["survey"]) == {}

    def test_dataset_never_loaded_is_removed(self):
        save_surveycto_dataset(PROJECT, _form())

        remove_dataset(PROJECT, "household")

        assert _log().is_empty()


class TestLoadInfo:
    def test_never_loaded_dataset_has_no_info(self):
        assert get_load_info(PROJECT, ["survey"]) == {}

    def test_recorded_load_gives_time_and_rows(self):
        duckdb_save_table(PROJECT, pl.DataFrame({"a": [1, 2, 3]}), alias="survey")
        before = datetime.now().replace(microsecond=0)

        record_load(PROJECT, "survey")

        info = get_load_info(PROJECT, ["survey"])["survey"]
        assert info.rows == 3
        assert info.loaded_at >= before

    def test_table_imported_before_load_times_has_rows_only(self):
        duckdb_save_table(PROJECT, pl.DataFrame({"a": [1, 2]}), alias="survey")

        assert get_load_info(PROJECT, ["survey"]) == {"survey": LoadInfo(None, 2)}

    def test_reloading_keeps_one_record_with_the_latest_time(self):
        duckdb_save_table(PROJECT, pl.DataFrame({"a": [1]}), alias="survey")
        record_load(PROJECT, "survey")
        first = get_load_info(PROJECT, ["survey"])["survey"].loaded_at

        record_load(PROJECT, "survey")

        assert get_load_info(PROJECT, ["survey"])["survey"].loaded_at >= first
