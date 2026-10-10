"""Tests for the decisions that resolve ID problems on the duplicate cards."""

import polars as pl
import pytest

from datasure.checks.id_corrections import (
    Decision,
    RecordDecision,
    all_dropped,
    build_entries,
    has_repeated_keys,
    log_reason,
    save_blockers,
)
from datasure.processing.correction_log import Action


@pytest.fixture
def included():
    """Included survey records: KEYs k1 and k2 share ID A."""
    return pl.DataFrame(
        {
            "hhid": ["A", "A", "B", "C"],
            "KEY": ["k1", "k2", "k3", "k4"],
        }
    )


def _blockers(decisions, included, *, reason="Repeat visit", note="checked", **kw):
    return save_blockers(
        decisions,
        original_id="A",
        included=included,
        id_col="hhid",
        key_col="KEY",
        reason=reason,
        note=note,
        **kw,
    )


class TestResolutionRule:
    def test_two_kept_records_block_the_save(self, included):
        decisions = [
            RecordDecision("k1", Decision.KEEP),
            RecordDecision("k2", Decision.KEEP),
        ]
        blockers = _blockers(decisions, included)
        assert blockers == [
            "2 records still hold ID A. Keep at most one: modify or drop the others."
        ]

    def test_one_kept_record_resolves_the_group(self, included):
        decisions = [
            RecordDecision("k1", Decision.KEEP),
            RecordDecision("k2", Decision.DROP),
        ]
        assert _blockers(decisions, included) == []

    def test_no_kept_record_resolves_the_group(self, included):
        decisions = [
            RecordDecision("k1", Decision.MODIFY_ID, "D"),
            RecordDecision("k2", Decision.DROP),
        ]
        assert _blockers(decisions, included) == []

    def test_reason_and_note_are_required(self, included):
        decisions = [
            RecordDecision("k1", Decision.KEEP),
            RecordDecision("k2", Decision.DROP),
        ]
        assert _blockers(decisions, included, reason=None, note="  ") == [
            "Choose a reason.",
            "Enter a note.",
        ]


class TestModifyIdValidation:
    def _modify(self, new_id):
        return [
            RecordDecision("k1", Decision.KEEP),
            RecordDecision("k2", Decision.MODIFY_ID, new_id),
        ]

    @pytest.mark.parametrize("new_id", [None, "", "   "])
    def test_empty_id_is_blocked(self, included, new_id):
        assert _blockers(self._modify(new_id), included) == [
            "Enter a new ID for KEY k2."
        ]

    def test_unchanged_id_is_blocked(self, included):
        assert _blockers(self._modify(" A "), included) == [
            "The new ID for KEY k2 is the same as its current ID."
        ]

    def test_same_new_id_twice_is_blocked(self, included):
        decisions = [
            RecordDecision("k1", Decision.MODIFY_ID, "D"),
            RecordDecision("k2", Decision.MODIFY_ID, "D"),
        ]
        assert _blockers(decisions, included) == [
            "KEY k1 and KEY k2 have the same new ID D."
        ]

    def test_existing_included_id_is_blocked_and_names_its_key(self, included):
        assert _blockers(self._modify("C"), included) == [
            "ID C already belongs to KEY k4."
        ]

    def test_existing_id_is_matched_as_text(self):
        included = pl.DataFrame({"hhid": [1, 1, 7], "KEY": ["k1", "k2", "k9"]})
        decisions = [
            RecordDecision("k1", Decision.KEEP),
            RecordDecision("k2", Decision.MODIFY_ID, "7"),
        ]
        blockers = save_blockers(
            decisions,
            original_id="1",
            included=included,
            id_col="hhid",
            key_col="KEY",
            reason="Wrong ID entered",
            note="n",
        )
        assert blockers == ["ID 7 already belongs to KEY k9."]

    def test_new_unused_id_is_allowed(self, included):
        assert _blockers(self._modify("Z"), included) == []

    def test_unmatched_id_must_be_a_survey_id(self, included):
        decisions = [RecordDecision("b1", Decision.MODIFY_ID, "Q")]
        blockers = _blockers(decisions, included, survey_ids=["A", "B", "Z"])
        assert blockers == ["ID Q is not in the survey data."]

        decisions = [RecordDecision("b1", Decision.MODIFY_ID, "Z")]
        assert _blockers(decisions, included, survey_ids=["A", "B", "Z"]) == []


class TestAllDropped:
    def test_all_dropped(self):
        assert all_dropped([RecordDecision("k1", Decision.DROP)] * 2)

    def test_not_all_dropped(self):
        assert not all_dropped(
            [RecordDecision("k1", Decision.DROP), RecordDecision("k2", Decision.KEEP)]
        )

    def test_no_decisions(self):
        assert not all_dropped([])


class TestBuildEntries:
    def test_one_entry_per_changed_record(self):
        decisions = [
            RecordDecision("k1", Decision.KEEP),
            RecordDecision("k2", Decision.MODIFY_ID, " D "),
            RecordDecision("k3", Decision.DROP),
        ]
        entries = build_entries(
            decisions, original_id="A", id_col="hhid", reason="Repeat visit: checked"
        )

        assert len(entries) == 2
        modify, drop = entries
        assert modify.key_value == "k2"
        assert modify.action == Action.MODIFY_VALUE
        assert modify.column == "hhid"
        assert modify.current_value == "A"
        assert modify.new_value == "D"
        assert modify.survey_id_value == "A"
        assert modify.reason == "Repeat visit: checked"

        assert drop.key_value == "k3"
        assert drop.action == Action.REMOVE_ROW
        assert drop.column is None
        assert drop.survey_id_value == "A"
        assert drop.reason == "Repeat visit: checked"

    def test_log_reason_joins_reason_and_note(self):
        assert log_reason("Repeat visit", "  2nd attempt  ") == (
            "Repeat visit: 2nd attempt"
        )


class TestRepeatedKeys:
    def test_repeated_keys(self):
        records = pl.DataFrame({"KEY": ["k1", "k1"], "hhid": ["A", "A"]})
        assert has_repeated_keys(records, "KEY")

    def test_distinct_keys(self):
        records = pl.DataFrame({"KEY": ["k1", "k2"], "hhid": ["A", "A"]})
        assert not has_repeated_keys(records, "KEY")


class TestNewIdType:
    def test_new_id_must_fit_a_numeric_id_column(self):
        included = pl.DataFrame({"hhid": [1, 1, 7], "KEY": ["k1", "k2", "k9"]})
        decisions = [
            RecordDecision("k1", Decision.KEEP),
            RecordDecision("k2", Decision.MODIFY_ID, "A12"),
        ]
        blockers = save_blockers(
            decisions,
            original_id="1",
            included=included,
            id_col="hhid",
            key_col="KEY",
            reason="Wrong ID entered",
            note="n",
        )
        assert blockers == ["ID A12 is not a number, as hhid values are."]

    def test_numeric_new_id_fits(self):
        included = pl.DataFrame({"hhid": [1, 1], "KEY": ["k1", "k2"]})
        decisions = [
            RecordDecision("k1", Decision.KEEP),
            RecordDecision("k2", Decision.MODIFY_ID, "12"),
        ]
        blockers = save_blockers(
            decisions,
            original_id="1",
            included=included,
            id_col="hhid",
            key_col="KEY",
            reason="Wrong ID entered",
            note="n",
        )
        assert blockers == []
