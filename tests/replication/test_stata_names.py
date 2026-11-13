"""Stata names the replication package uses, and the edits saved for them."""

from __future__ import annotations

import json
from unittest.mock import patch

import polars as pl
import pytest

from datasure.replication.stata_names import (
    load_stata_name_edits,
    package_name_map,
    save_stata_name_edits,
    updated_stata_name_edits,
)


def _prep_log(*steps: dict) -> pl.DataFrame:
    return pl.DataFrame(
        {
            "action": [s["action"] for s in steps],
            "description": [""] * len(steps),
            "prep_args": [json.dumps(s) for s in steps],
            "action_index": list(range(1, len(steps) + 1)),
        }
    )


class TestPackageNameMap:
    def test_covers_imported_columns_and_names_prep_steps_create(self):
        log = _prep_log(
            {
                "action": "add new column",
                "method": "copy of column",
                "source_columns": ["visit date"],
                "column_names": "visit date copy",
            }
        )
        mapping = package_name_map(["KEY", "visit date"], log)
        assert mapping == {
            "visit date": "visit_date",
            "visit date copy": "visit_date_copy",
        }

    def test_imported_columns_claim_names_before_prep_steps(self):
        log = _prep_log(
            {
                "action": "rename column(s)",
                "source_columns": ["a"],
                "column_names": ["x-y"],
            }
        )
        mapping = package_name_map(["x y", "a"], log)
        assert mapping == {"x y": "x_y", "x-y": "x_y_2"}

    def test_saved_edits_are_used(self):
        mapping = package_name_map(["in"], pl.DataFrame(), edits={"in": "inside"})
        assert mapping == {"in": "inside"}

    def test_all_valid_names_map_nothing(self):
        assert package_name_map(["KEY", "age"], pl.DataFrame()) == {}


class TestStoredEdits:
    @pytest.fixture(autouse=True)
    def _logs_db(self, tmp_path):
        with patch(
            "datasure.utils.duckdb_utils.database_path",
            return_value=tmp_path / "logs.duckdb",
        ):
            yield

    def test_no_saved_edits_is_empty(self):
        assert load_stata_name_edits("p", "survey") == {}

    def test_edits_round_trip(self):
        save_stata_name_edits("p", "survey", {"visit date": "vdate", "in": "inside"})
        assert load_stata_name_edits("p", "survey") == {
            "visit date": "vdate",
            "in": "inside",
        }

    def test_saving_replaces_earlier_edits_and_can_clear_them(self):
        save_stata_name_edits("p", "survey", {"visit date": "vdate"})
        save_stata_name_edits("p", "survey", {"in": "inside"})
        assert load_stata_name_edits("p", "survey") == {"in": "inside"}
        save_stata_name_edits("p", "survey", {})
        assert load_stata_name_edits("p", "survey") == {}

    def test_edits_are_kept_per_dataset(self):
        save_stata_name_edits("p", "survey", {"in": "inside"})
        assert load_stata_name_edits("p", "backcheck") == {}


_PROPOSALS = {"visit date": "visit_date", "visit-date": "visit_date_2"}


class TestUpdatedEdits:
    """Which names typed into the Replication page's table are kept as edits."""

    def test_untouched_table_has_no_edits(self):
        assert updated_stata_name_edits(_PROPOSALS, _PROPOSALS, _PROPOSALS, {}) == {}

    def test_a_changed_name_is_an_edit_and_is_trimmed(self):
        typed = {**_PROPOSALS, "visit date": " vdate "}
        edits = updated_stata_name_edits(typed, _PROPOSALS, _PROPOSALS, {})
        assert edits == {"visit date": "vdate"}

    def test_a_proposal_moved_by_an_edit_is_not_an_edit(self):
        saved = {"visit-date": "visit_date"}
        shown = {"visit date": "visit_date_2", "visit-date": "visit_date"}
        edits = updated_stata_name_edits(shown, shown, _PROPOSALS, saved)
        assert edits == saved

    def test_typing_the_proposal_back_undoes_an_edit(self):
        saved = {"visit date": "vdate"}
        shown = {"visit date": "vdate", "visit-date": "visit_date_2"}
        typed = {**shown, "visit date": "visit_date"}
        assert updated_stata_name_edits(typed, shown, _PROPOSALS, saved) == {}
