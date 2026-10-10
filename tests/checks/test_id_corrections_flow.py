"""End-to-end: card saves through a real CorrectionProcessor, undo, comparison."""

from unittest.mock import patch

import polars as pl
import pytest

from datasure.checks.backchecks.compute import compute_backcheck_analysis
from datasure.checks.backchecks.models import BackcheckSettings
from datasure.checks.id_corrections import (
    SOURCE,
    Decision,
    RecordDecision,
    build_entries,
)
from datasure.checks.id_duplicates import find_duplicate_groups, find_unmatched_ids
from datasure.processing.corrections import CorrectionProcessor


@pytest.fixture
def store():
    """In-memory DuckDB stand-in; the processor's caches are reset."""
    tables: dict[tuple[str, str], pl.DataFrame] = {}

    def get(project_id, alias, db_name, type="pl"):
        return tables.get((db_name, alias), pl.DataFrame())

    def save(project_id, table_data, alias, db_name="raw"):
        tables[(db_name, alias)] = table_data

    def clear():
        for method in (
            "get_corrected_data",
            "get_correction_log",
            "get_data_summary",
            "get_correction_summary",
        ):
            getattr(CorrectionProcessor, method).clear()

    with (
        patch("datasure.processing.corrections.duckdb_get_table", get),
        patch("datasure.processing.corrections.duckdb_save_table", save),
        patch(
            "datasure.processing.corrections.duckdb_table_exists",
            lambda project_id, alias, db_name: (db_name, alias) in tables,
        ),
    ):
        clear()
        yield tables
        clear()


def _save_card(processor, alias, decisions, original_id):
    entries = build_entries(
        decisions, original_id=original_id, id_col="hhid", reason="Repeat visit: n"
    )
    processor.apply_corrections(alias, "KEY", entries, source=SOURCE)


def test_removing_one_entry_of_a_save_brings_the_card_back(store):
    store[("prep", "survey")] = pl.DataFrame(
        {"hhid": ["A", "A", "A"], "KEY": ["k1", "k2", "k3"]}
    )
    processor = CorrectionProcessor("p1")
    _save_card(
        processor,
        "survey",
        [
            RecordDecision("k1", Decision.KEEP),
            RecordDecision("k2", Decision.MODIFY_ID, "B"),
            RecordDecision("k3", Decision.DROP),
        ],
        "A",
    )
    corrected = processor.get_corrected_data("survey")
    assert find_duplicate_groups(corrected, "hhid", "KEY", None).is_empty()
    log = processor.get_correction_log("survey")
    assert log["source"].to_list() == [SOURCE, SOURCE]

    # Undo the drop on the Corrections page: k3 holds A again.
    processor.remove_correction_entry("survey", 1)

    groups = find_duplicate_groups(
        processor.get_corrected_data("survey"), "hhid", "KEY", None
    )
    assert groups["id"].to_list() == ["A"]
    assert groups["keys"].to_list() == [["k1", "k3"]]


def test_unmatched_backcheck_fixed_by_modify_id_joins_the_comparison(store):
    survey = pl.DataFrame({"hhid": ["A", "B"], "KEY": ["s1", "s2"], "age": [30, 40]})
    # The backcheck for B was entered with the mistyped ID "8".
    store[("raw", "bc")] = pl.DataFrame(
        {"hhid": ["A", "8"], "KEY": ["b1", "b2"], "age": [30, 41]}
    )
    processor = CorrectionProcessor("p1")
    backcheck = processor.get_corrected_data("bc")
    assert find_unmatched_ids(backcheck, survey, "hhid", "KEY", None)[
        "id"
    ].to_list() == ["8"]

    _save_card(processor, "bc", [RecordDecision("b2", Decision.MODIFY_ID, "B")], "8")

    backcheck = processor.get_corrected_data("bc")
    assert find_unmatched_ids(backcheck, survey, "hhid", "KEY", None).is_empty()
    columns = pl.DataFrame(
        {
            "search_type": ["exact"],
            "pattern": ["age"],
            "column_name": [["age"]],
            "category": [1],
            "ok_range_type": [None],
            "ok_range_values": [None],
            "ttest": [False],
            "prtest": [False],
            "signrank": [False],
            "reliability": [False],
        }
    )
    result = compute_backcheck_analysis(
        survey,
        backcheck,
        BackcheckSettings(survey_key="KEY", survey_id="hhid"),
        columns,
    )
    assert sorted(result["KEY"].unique().to_list()) == ["s1", "s2"]
