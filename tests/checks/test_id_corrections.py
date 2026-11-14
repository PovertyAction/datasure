"""Tests for the decisions that resolve ID problems on the duplicate cards."""

import polars as pl
import pytest

from datasure.checks.id_corrections import (
    Decision,
    RecordDecision,
    all_dropped,
    build_entries,
    has_untargetable_keys,
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

    def test_existing_id_on_a_record_with_no_key_is_blocked(self):
        # A missing KEY outside the card must not crash the message.
        included = pl.DataFrame({"hhid": ["A", "A", "C"], "KEY": ["k1", "k2", None]})
        assert _blockers(self._modify("C"), included) == [
            "ID C already belongs to a record with no KEY."
        ]

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


class TestUntargetableKeys:
    def test_repeated_keys(self):
        records = pl.DataFrame({"KEY": ["k1", "k1"], "hhid": ["A", "A"]})
        assert has_untargetable_keys(records, records, "KEY")

    def test_distinct_keys(self):
        records = pl.DataFrame({"KEY": ["k1", "k2"], "hhid": ["A", "A"]})
        assert not has_untargetable_keys(records, records, "KEY")

    def test_missing_key(self):
        records = pl.DataFrame({"KEY": ["k1", None], "hhid": ["A", "A"]})
        assert has_untargetable_keys(records, records, "KEY")

    def test_key_also_on_a_record_outside_the_card(self):
        records = pl.DataFrame({"KEY": ["k1", "k2"], "hhid": ["A", "A"]})
        all_data = pl.DataFrame({"KEY": ["k1", "k2", "k1"], "hhid": ["A", "A", "Z"]})
        assert has_untargetable_keys(records, all_data, "KEY")

    def test_keys_unique_in_the_whole_dataset(self):
        records = pl.DataFrame({"KEY": ["k1", "k2"], "hhid": ["A", "A"]})
        all_data = pl.DataFrame({"KEY": ["k1", "k2", "k3"], "hhid": ["A", "A", "Z"]})
        assert not has_untargetable_keys(records, all_data, "KEY")


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


class TestNumericNewId:
    """A numeric ID column stores `01` as `1`, so new IDs compare that way."""

    @pytest.fixture
    def numeric(self):
        return pl.DataFrame({"hhid": [1, 1, 7], "KEY": ["k1", "k2", "k9"]})

    def _blockers(self, numeric, *new_ids, **kw):
        decisions = [RecordDecision("k1", Decision.KEEP)] + [
            RecordDecision(f"k{i}", Decision.MODIFY_ID, new_id)
            for i, new_id in enumerate(new_ids, start=2)
        ]
        return save_blockers(
            decisions,
            original_id="1",
            included=numeric,
            id_col="hhid",
            key_col="KEY",
            reason="Wrong ID entered",
            note="n",
            **kw,
        )

    def test_leading_zero_is_the_current_id(self, numeric):
        assert self._blockers(numeric, "01") == [
            "The new ID for KEY k2 is the same as its current ID."
        ]

    def test_leading_zero_matches_an_existing_id(self, numeric):
        assert self._blockers(numeric, "007") == ["ID 7 already belongs to KEY k9."]

    def test_two_spellings_of_one_new_id_clash(self, numeric):
        assert self._blockers(numeric, "12", "012") == [
            "KEY k2 and KEY k3 have the same new ID 12."
        ]

    def test_leading_zero_matches_a_survey_id(self, numeric):
        assert self._blockers(numeric, "012", survey_ids=["12"]) == []
