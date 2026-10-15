"""Tests for the records the backcheck comparison uses, and its ID problems."""

import json

import polars as pl
import pytest

from datasure.checks.backchecks.scope import (
    IdProblemCounts,
    comparison_scope,
    id_problem_counts,
    id_problem_warning,
    scope_captions,
)


@pytest.fixture
def survey():
    return pl.DataFrame(
        {
            "hhid": ["A", "B", "B", "C", "D"],
            "KEY": ["s1", "s2", "s3", "s4", "s5"],
            "status": ["Complete", "Complete", "Failed", "Complete", "Failed"],
        }
    )


@pytest.fixture
def backcheck():
    return pl.DataFrame(
        {
            "hhid": ["A", "A", "C", "X"],
            "KEY": ["b1", "b2", "b3", "b4"],
            "bc_status": ["Done", "Done", "Done", "Done"],
        }
    )


def _settings_file(tmp_path, duplicates: dict) -> str:
    path = tmp_path / "page_settings.json"
    path.write_text(json.dumps({"duplicates": duplicates}))
    return str(path)


SURVEY_FILTER = {
    "condition_col": "status",
    "condition_type": "Value is equal",
    "condition_value": "Complete",
}


class TestComparisonScope:
    def test_no_filters_keep_every_record(self, tmp_path, survey, backcheck):
        scope = comparison_scope(survey, backcheck, _settings_file(tmp_path, {}))

        assert scope.survey.data.equals(survey)
        assert scope.backcheck.data.equals(backcheck)
        assert scope_captions(scope) == []

    def test_survey_filter_leaves_out_records(self, tmp_path, survey, backcheck):
        settings_file = _settings_file(tmp_path, SURVEY_FILTER)

        scope = comparison_scope(survey, backcheck, settings_file)

        assert scope.survey.data["KEY"].to_list() == ["s1", "s2", "s4"]
        assert scope.backcheck.data.equals(backcheck)
        assert scope_captions(scope) == [
            "Comparing 3 of 5 surveys (Records to Include: status == Complete)"
        ]

    def test_backcheck_filter_uses_its_own_prefix(self, tmp_path, survey, backcheck):
        settings_file = _settings_file(
            tmp_path,
            {
                "backcheck_condition_col": "KEY",
                "backcheck_condition_type": "Value does not include",
                "backcheck_condition_value": ["b2"],
            },
        )

        scope = comparison_scope(survey, backcheck, settings_file)

        assert scope.survey.data.equals(survey)
        assert scope.backcheck.data["KEY"].to_list() == ["b1", "b3", "b4"]
        assert scope_captions(scope) == [
            "Comparing 3 of 4 backchecks (Records to Include: KEY not in b2)"
        ]

    def test_counts_use_thousands_separators(self, tmp_path):
        survey = pl.DataFrame({"hhid": list(range(1310)), "n": list(range(1310))})
        settings_file = _settings_file(
            tmp_path,
            {
                "condition_col": "n",
                "condition_type": "Value is less than",
                "condition_value": 1240,
            },
        )

        scope = comparison_scope(survey, survey.head(0), settings_file)

        assert scope_captions(scope) == [
            "Comparing 1,240 of 1,310 surveys (Records to Include: n < 1240)"
        ]

    def test_invalid_filter_keeps_no_records(self, tmp_path, survey, backcheck):
        settings_file = _settings_file(
            tmp_path,
            {
                "condition_col": "missing_col",
                "condition_type": "Value is equal",
                "condition_value": "x",
            },
        )

        scope = comparison_scope(survey, backcheck, settings_file)

        assert scope.survey.data.is_empty()
        assert scope.survey.error


class TestIdProblems:
    def test_counts_duplicates_among_included_records(
        self, tmp_path, survey, backcheck
    ):
        scope = comparison_scope(survey, backcheck, _settings_file(tmp_path, {}))

        counts = id_problem_counts(scope, survey, "hhid")

        # Survey: B twice. Backcheck: A twice. Unmatched backcheck: X.
        assert counts == IdProblemCounts(
            duplicate_survey_ids=1, duplicate_backcheck_ids=1, unmatched_ids=1
        )

    def test_left_out_records_are_not_duplicates(self, tmp_path, survey, backcheck):
        """s3 is a failed visit left out by the filter, so B is not duplicated."""
        settings_file = _settings_file(tmp_path, SURVEY_FILTER)
        scope = comparison_scope(survey, backcheck, settings_file)

        counts = id_problem_counts(scope, survey, "hhid")

        assert counts.duplicate_survey_ids == 0

    def test_unmatched_ids_match_every_survey_record(self, tmp_path, survey):
        """As on the Duplicates tab, a left-out survey still matches its ID."""
        backcheck = pl.DataFrame({"hhid": ["D"], "KEY": ["b1"]})
        settings_file = _settings_file(tmp_path, SURVEY_FILTER)
        scope = comparison_scope(survey, backcheck, settings_file)

        assert id_problem_counts(scope, survey, "hhid").unmatched_ids == 0

    def test_missing_id_column_counts_nothing(self, tmp_path, survey, backcheck):
        scope = comparison_scope(survey, backcheck, _settings_file(tmp_path, {}))

        assert id_problem_counts(scope, survey, None) == IdProblemCounts(0, 0, 0)

    def test_warning_lists_the_counts(self):
        warning = id_problem_warning(IdProblemCounts(2, 1, 3))

        assert warning == (
            "2 duplicate survey IDs, 1 duplicate backcheck ID and 3 unmatched "
            "backcheck IDs are left out of the comparison. Resolve them on the "
            "Duplicates tab to include them."
        )

    def test_no_warning_without_problems(self):
        assert id_problem_warning(IdProblemCounts(0, 0, 0)) is None
