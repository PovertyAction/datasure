"""Tests for datasure.checks.outliers.review."""

import pandas as pd
import polars as pl
import pytest

from datasure.checks.outliers.review import (
    CONSTRAINTS,
    OUTLIERS,
    REVIEW_REASON_COL,
    REVIEW_STATUS_COL,
    REVIEWED_BADGE,
    FlagSelection,
    allowed_actions,
    clear_reviewed_flags,
    flagged_only,
    highlight_reviewed_row,
    mark_reviewed,
    needs_hard_confirmation,
    select_flag,
    visible_flags,
)
from datasure.processing.correction_log import Action, empty_correction_log


def _acceptances(rows: list[dict]) -> pl.DataFrame:
    """Build accept rows shaped like `get_active_acceptances` output."""
    base = empty_correction_log()
    if not rows:
        return base
    return pl.DataFrame(
        [
            {
                "KEY": r["KEY"],
                "action": "accept",
                "column": r["column"],
                "current_value": r.get("current_value"),
                "reason": r.get("reason", "checked"),
                "check_type": r.get("check_type", "outliers"),
            }
            for r in rows
        ]
    ).select(
        pl.col(c).cast(pl.String)
        for c in ["KEY", "action", "column", "current_value", "reason", "check_type"]
    )


@pytest.fixture
def outlier_flags() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "survey_key": ["K1", "K2", "K3", "K1"],
            "column name": ["age", "age", "age", "income"],
            "column value": [99.0, 30.0, 120.0, 5000.0],
            "outlier reason": [
                "Value is above upper bound 80.00",
                "no outlier",
                "Value is above upper bound 80.00",
                "Value is above upper bound 900.00",
            ],
        }
    )


class TestMarkReviewed:
    def test_flags_matching_an_acceptance_are_reviewed_with_its_reason(
        self, outlier_flags
    ):
        acceptances = _acceptances(
            [{"KEY": "K1", "column": "age", "reason": "verified by phone"}]
        )

        result = mark_reviewed(outlier_flags, acceptances, "survey_key", OUTLIERS)

        assert result[REVIEW_STATUS_COL].to_list() == [
            REVIEWED_BADGE,
            None,
            None,
            None,
        ]
        assert result[REVIEW_REASON_COL].to_list() == [
            "verified by phone",
            None,
            None,
            None,
        ]

    def test_acceptance_on_another_column_of_the_same_key_does_not_match(
        self, outlier_flags
    ):
        acceptances = _acceptances([{"KEY": "K1", "column": "income"}])

        result = mark_reviewed(outlier_flags, acceptances, "survey_key", OUTLIERS)

        assert result[REVIEW_STATUS_COL].to_list() == [
            None,
            None,
            None,
            REVIEWED_BADGE,
        ]

    def test_unflagged_rows_are_never_reviewed(self, outlier_flags):
        acceptances = _acceptances([{"KEY": "K2", "column": "age"}])

        result = mark_reviewed(outlier_flags, acceptances, "survey_key", OUTLIERS)

        assert result[REVIEW_STATUS_COL].null_count() == result.height

    def test_keeps_row_order_and_columns(self, outlier_flags):
        acceptances = _acceptances([{"KEY": "K3", "column": "age"}])

        result = mark_reviewed(outlier_flags, acceptances, "survey_key", OUTLIERS)

        assert result.columns == [
            *outlier_flags.columns,
            REVIEW_STATUS_COL,
            REVIEW_REASON_COL,
        ]
        assert result.drop(REVIEW_STATUS_COL, REVIEW_REASON_COL).equals(outlier_flags)

    def test_matches_non_string_keys_as_text(self):
        flags = pl.DataFrame(
            {
                "survey_key": [1, 2],
                "column name": ["age", "age"],
                "violation reason": ["Value is above hard maximum 100", "no violation"],
            }
        )
        acceptances = _acceptances(
            [{"KEY": "1", "column": "age", "check_type": "constraints"}]
        )

        result = mark_reviewed(flags, acceptances, "survey_key", CONSTRAINTS)

        assert result[REVIEW_STATUS_COL].to_list() == [REVIEWED_BADGE, None]

    def test_repeated_acceptances_use_the_latest_reason(self, outlier_flags):
        acceptances = _acceptances(
            [
                {"KEY": "K1", "column": "age", "reason": "first"},
                {"KEY": "K1", "column": "age", "reason": "second"},
            ]
        )

        result = mark_reviewed(outlier_flags, acceptances, "survey_key", OUTLIERS)

        assert result.height == outlier_flags.height
        assert result[REVIEW_REASON_COL][0] == "second"

    def test_no_acceptances_marks_nothing(self, outlier_flags):
        result = mark_reviewed(
            outlier_flags, empty_correction_log(), "survey_key", OUTLIERS
        )

        assert result[REVIEW_STATUS_COL].null_count() == result.height

    def test_empty_flags_are_returned_unchanged(self):
        result = mark_reviewed(pl.DataFrame(), _acceptances([]), "survey_key", OUTLIERS)

        assert result.is_empty()


class TestClearReviewedFlags:
    def test_reviewed_flags_no_longer_count_as_flags(self, outlier_flags):
        marked = mark_reviewed(
            outlier_flags,
            _acceptances([{"KEY": "K1", "column": "age"}]),
            "survey_key",
            OUTLIERS,
        )

        result = clear_reviewed_flags(marked, OUTLIERS)

        assert result["outlier reason"].to_list() == [
            "no outlier",
            "no outlier",
            "Value is above upper bound 80.00",
            "Value is above upper bound 900.00",
        ]

    def test_keeps_rows_so_checked_columns_are_still_counted(self, outlier_flags):
        acceptances = _acceptances(
            [{"KEY": "K1", "column": "income"}, {"KEY": "K1", "column": "age"}]
        )
        marked = mark_reviewed(outlier_flags, acceptances, "survey_key", OUTLIERS)

        result = clear_reviewed_flags(marked, OUTLIERS)

        assert result.height == outlier_flags.height
        assert set(result["column name"]) == {"age", "income"}

    def test_data_without_review_columns_is_unchanged(self, outlier_flags):
        assert clear_reviewed_flags(outlier_flags, OUTLIERS).equals(outlier_flags)


class TestHighlightReviewedRow:
    def test_reviewed_rows_are_green_in_every_cell(self):
        row = pd.Series({"KEY": "K1", REVIEW_STATUS_COL: REVIEWED_BADGE})

        styles = highlight_reviewed_row(row)

        assert len(styles) == len(row)
        assert all("background-color" in style for style in styles)
        assert all("25, 135, 84" in style for style in styles)

    @pytest.mark.parametrize("status", [None, float("nan")])
    def test_other_rows_are_plain(self, status):
        row = pd.Series({"KEY": "K2", REVIEW_STATUS_COL: status})

        assert highlight_reviewed_row(row) == ["", ""]


class TestFlaggedOnly:
    def test_keeps_only_flagged_rows(self, outlier_flags):
        result = flagged_only(outlier_flags, OUTLIERS)

        assert result["survey_key"].to_list() == ["K1", "K3", "K1"]
        assert "no outlier" not in result["outlier reason"].to_list()

    def test_uses_the_check_sentinel(self):
        flags = pl.DataFrame(
            {
                "survey_key": ["K1", "K2"],
                "column name": ["age", "age"],
                "violation reason": ["Value is above hard maximum 100", "no violation"],
            }
        )

        assert flagged_only(flags, CONSTRAINTS)["survey_key"].to_list() == ["K1"]

    def test_data_without_the_reason_column_is_unchanged(self):
        flags = pl.DataFrame({"survey_key": ["K1"]})

        assert flagged_only(flags, OUTLIERS).equals(flags)


class TestVisibleFlags:
    @pytest.fixture
    def marked(self, outlier_flags):
        return mark_reviewed(
            outlier_flags,
            _acceptances([{"KEY": "K1", "column": "age", "reason": "ok"}]),
            "survey_key",
            OUTLIERS,
        )

    def test_hides_reviewed_flags_and_review_columns(self, marked):
        result = visible_flags(marked, show_reviewed=False)

        assert result.height == 3
        assert REVIEW_STATUS_COL not in result.columns
        assert REVIEW_REASON_COL not in result.columns

    def test_show_reviewed_keeps_them_with_badge_and_reason(self, marked):
        result = visible_flags(marked, show_reviewed=True)

        assert result.height == 4
        assert result.row(0, named=True)[REVIEW_STATUS_COL] == REVIEWED_BADGE
        assert result.row(0, named=True)[REVIEW_REASON_COL] == "ok"

    def test_data_without_review_columns_is_unchanged(self, outlier_flags):
        assert visible_flags(outlier_flags, show_reviewed=False).equals(outlier_flags)


@pytest.fixture
def constraint_table() -> pl.DataFrame:
    """A constraint table as displayed: flagged rows plus the violation type."""
    return pl.DataFrame(
        {
            "survey_key": ["K1", "K2"],
            "survey_id": ["S1", "S2"],
            "column name": ["age", "age"],
            "column value": [150.0, 70.0],
            "violation reason": [
                "Value is above hard maximum 100",
                "Value is above soft maximum 65",
            ],
            "violation type": ["Hard Max", "Soft Max"],
        }
    )


class TestSelectFlag:
    def test_prefills_key_and_column_from_the_selected_row(self, constraint_table):
        selection = select_flag(constraint_table, [1], "survey_key", CONSTRAINTS)

        assert selection == FlagSelection(
            key_value="K2",
            column="age",
            check_type="constraints",
            flagged=True,
            reviewed=False,
            hard=False,
        )

    def test_hard_violations_are_marked_hard(self, constraint_table):
        selection = select_flag(constraint_table, [0], "survey_key", CONSTRAINTS)

        assert selection.hard is True

    def test_outliers_are_never_hard(self, outlier_flags):
        selection = select_flag(outlier_flags, [0], "survey_key", OUTLIERS)

        assert selection.check_type == "outliers"
        assert selection.flagged is True
        assert selection.hard is False

    def test_unflagged_rows_are_reported_as_unflagged(self, outlier_flags):
        selection = select_flag(outlier_flags, [1], "survey_key", OUTLIERS)

        assert selection.flagged is False

    def test_reviewed_rows_are_reported_as_reviewed(self, outlier_flags):
        table = visible_flags(
            mark_reviewed(
                outlier_flags,
                _acceptances([{"KEY": "K1", "column": "age"}]),
                "survey_key",
                OUTLIERS,
            ),
            show_reviewed=True,
        )

        selection = select_flag(table, [0], "survey_key", OUTLIERS)

        assert selection.reviewed is True

    def test_keeps_the_key_value_as_stored_in_the_data(self):
        table = pl.DataFrame(
            {
                "survey_key": [7],
                "column name": ["age"],
                "outlier reason": ["Value is above upper bound 80.00"],
            }
        )

        assert select_flag(table, [0], "survey_key", OUTLIERS).key_value == 7

    @pytest.mark.parametrize("rows", [[], [5], [-1]])
    def test_no_or_stale_selection_returns_none(self, constraint_table, rows):
        assert select_flag(constraint_table, rows, "survey_key", CONSTRAINTS) is None


class TestAllowedActions:
    def _selection(self, **overrides) -> FlagSelection:
        values = {
            "key_value": "K1",
            "column": "age",
            "check_type": "outliers",
            "flagged": True,
            "reviewed": False,
            "hard": False,
        }
        return FlagSelection(**(values | overrides))

    def test_flagged_value_can_be_modified_removed_or_accepted(self):
        assert allowed_actions(self._selection()) == [
            Action.MODIFY_VALUE,
            Action.REMOVE_VALUE,
            Action.ACCEPT,
        ]

    def test_unflagged_value_cannot_be_accepted(self):
        assert Action.ACCEPT not in allowed_actions(self._selection(flagged=False))

    def test_reviewed_value_cannot_be_accepted_again(self):
        assert Action.ACCEPT not in allowed_actions(self._selection(reviewed=True))

    def test_rows_are_never_removed_from_a_check_page(self):
        assert Action.REMOVE_ROW not in allowed_actions(self._selection())

    def test_only_accepting_a_hard_violation_needs_confirmation(self):
        hard = self._selection(check_type="constraints", hard=True)
        soft = self._selection(check_type="constraints", hard=False)

        assert needs_hard_confirmation(hard, Action.ACCEPT) is True
        assert needs_hard_confirmation(hard, Action.MODIFY_VALUE) is False
        assert needs_hard_confirmation(soft, Action.ACCEPT) is False
