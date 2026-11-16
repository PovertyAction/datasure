"""Tests for finding where check configs and corrections use columns."""

import json
from unittest.mock import patch

import polars as pl
import pytest

from datasure.utils.column_references import (
    ColumnReference,
    find_column_references,
    format_references,
)
from datasure.utils.duckdb_utils import duckdb_save_table

PROJECT = "proj"


@pytest.fixture
def cache(tmp_path):
    """Point DuckDB databases and settings files at a temporary project."""

    def fake_cache_path(*parts):
        path = tmp_path.joinpath(*map(str, parts))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    with (
        patch("datasure.utils.duckdb_utils.get_cache_path", fake_cache_path),
        patch("datasure.utils.column_references.get_cache_path", fake_cache_path),
    ):
        yield tmp_path


def _save(df: pl.DataFrame, table: str) -> None:
    duckdb_save_table(PROJECT, df, table, "logs")


def _config(**fields) -> None:
    row = {
        "page_name": "Main Checks",
        "survey_data_name": "survey",
        "backcheck_data_name": None,
        "survey_key": "KEY",
        "survey_id": None,
        "enumerator": None,
        "backchecker": None,
    } | fields
    _save(pl.DataFrame([row]), "check_config")


def _find(*columns: str, alias: str = "survey") -> list[ColumnReference]:
    return find_column_references(PROJECT, alias, columns)


class TestFindColumnReferences:
    def test_empty_project_has_no_references(self, cache):
        assert _find("hhid") == []

    def test_page_config_fields_on_the_dataset(self, cache):
        _config(survey_id="hhid", enumerator="enum")

        assert _find("hhid", "age") == [
            ColumnReference("hhid", "Check page 'Main Checks'", "survey ID")
        ]

    def test_pages_on_another_dataset_are_ignored(self, cache):
        _config(survey_data_name="other", survey_id="hhid")

        assert _find("hhid") == []

    def test_backcheck_fields_count_for_the_backcheck_dataset(self, cache):
        _config(backcheck_data_name="bc", backchecker="bcer", survey_id="hhid")

        assert _find("bcer", "hhid", alias="bc") == [
            ColumnReference("bcer", "Check page 'Main Checks'", "backchecker"),
            ColumnReference("hhid", "Check page 'Main Checks'", "survey ID"),
        ]

    def test_check_tables_of_the_page(self, cache):
        _config()
        _save(
            pl.DataFrame({"column_name": [["hhid", "phone"]], "pattern": [None]}),
            "duplicates_main_checks",
        )
        _save(
            pl.DataFrame(
                {"gps_column": [None], "latitude_column": ["lat"], "alias": ["gps"]}
            ),
            "gps_columns_main_checks",
        )
        _save(
            pl.DataFrame({"column": ["age", "income"], "Selected": [True, False]}),
            "descriptive_columns_main_checks",
        )

        assert _find("phone", "lat", "age", "income") == [
            ColumnReference("phone", "Check page 'Main Checks'", "Duplicates check"),
            ColumnReference(
                "lat", "Check page 'Main Checks'", "GPS check (latitude column)"
            ),
            ColumnReference("age", "Check page 'Main Checks'", "Descriptive stats"),
        ]

    def test_check_settings_ignore_view_state(self, cache):
        _config()
        settings = {
            "progress": {"survey_date": "starttime"},
            "view_state": {"progress": {"survey_date": "age"}},
        }
        path = cache / PROJECT / "settings" / "page_main_checks_settings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(settings))

        assert _find("starttime", "age") == [
            ColumnReference(
                "starttime",
                "Check page 'Main Checks'",
                "Progress settings: survey date",
            )
        ]

    def test_correction_log_entries_are_counted(self, cache):
        _save(
            pl.DataFrame(
                {
                    "action": ["modify value", "remove value", "accept", "remove row"],
                    "column": ["age", "age", "income", None],
                    "KEY": ["k1", "k2", "k3", "k4"],
                }
            ),
            "corr_log_survey",
        )

        assert _find("age", "hhid") == [
            ColumnReference("age", "Correction log", "2 entries")
        ]

    def test_gps_acceptances_count_their_coordinate_columns(self, cache):
        _save(
            pl.DataFrame(
                {
                    "action": ["accept"],
                    "column": [None],
                    "check_type": ["gps"],
                    "current_value": [json.dumps({"lat": "1.0", "lon": "2.0"})],
                    "KEY": ["k1"],
                }
            ),
            "corr_log_survey",
        )

        assert _find("lat") == [ColumnReference("lat", "Correction log", "1 entry")]

    def test_unused_columns_have_no_references(self, cache):
        _config(survey_id="hhid")

        assert _find("age") == []


class TestFormatReferences:
    def test_lists_each_reference_under_its_column(self):
        text = format_references(
            [
                ColumnReference("hhid", "Check page 'Main'", "survey ID"),
                ColumnReference("hhid", "Correction log", "1 entry"),
            ]
        )

        assert (
            text
            == "- **hhid**: Check page 'Main' (survey ID); Correction log (1 entry)"
        )
