"""Tests for the correction log vocabulary."""

import polars as pl

from datasure.processing.correction_log import CORRECTION_ACTIONS, Action


class TestAction:
    """The Action enum must match the strings stored in existing logs."""

    def test_values_match_stored_strings(self):
        assert Action.MODIFY_VALUE == "modify value"
        assert Action.REMOVE_VALUE == "remove value"
        assert Action.REMOVE_ROW == "remove row"
        assert Action.ACCEPT == "accept"

    def test_stored_strings_round_trip(self):
        for value in ("modify value", "remove value", "remove row", "accept"):
            assert Action(value) == value

    def test_str_is_the_stored_value(self):
        assert str(Action.REMOVE_ROW) == "remove row"
        assert f"{Action.MODIFY_VALUE}" == "modify value"

    def test_correction_actions_are_the_data_changing_actions(self):
        assert CORRECTION_ACTIONS == (
            Action.MODIFY_VALUE,
            Action.REMOVE_VALUE,
            Action.REMOVE_ROW,
        )
        assert Action.ACCEPT not in CORRECTION_ACTIONS

    def test_filters_a_persisted_log(self):
        log = pl.DataFrame({"action": ["accept", "modify value", "remove row"]})
        assert log.filter(pl.col("action") != Action.ACCEPT).height == 2
