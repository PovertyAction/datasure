"""Tests for the Response Patterns compute entry point (seam A)."""

import polars as pl
import pytest

from datasure.checks.enumerator.response_patterns.compute import (
    compute_response_patterns,
    infer_variable_types,
)
from datasure.checks.enumerator.response_patterns.models import (
    ResponsePatternSettings,
)

ENUM = "enum"


def _values(n: int, round_count: int, start: int = 11) -> list[int]:
    """Return ``n`` values, the first ``round_count`` ending in 0 or 5.

    The rest end in 1-4 or 6-9, and the values span more than 10.
    """
    rounded = [10 + 5 * i for i in range(round_count)]
    others = [v for v in range(start, start + 200) if v % 5 != 0]
    return rounded + others[: n - round_count]


def _frame(values_by_enum: dict[str, list], column: str = "x") -> pl.DataFrame:
    """Build one row per value, tagged with its enumerator."""
    enums, values = [], []
    for name, vals in values_by_enum.items():
        enums.extend([name] * len(vals))
        values.extend(vals)
    return pl.DataFrame({ENUM: enums, column: values})


def _settings(**kwargs) -> ResponsePatternSettings:
    return ResponsePatternSettings(**{"selected_variables": ["x"], **kwargs})


def _digit(results, name: str):
    return next(e for e in results.digit_preference.enumerators if e.enumerator == name)


class TestDigitPreferenceScore:
    def test_twice_the_team_share_scores_100_and_half_scores_0(self):
        data = _frame({"A": _values(40, 16), "B": _values(40, 8)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _digit(results, "A").score == pytest.approx(100)
        assert _digit(results, "A").enum_pct == pytest.approx(40)
        assert _digit(results, "A").team_pct == pytest.approx(20)
        assert _digit(results, "B").score == pytest.approx(0)

    def test_one_and_a_half_times_the_team_share_scores_50(self):
        data = _frame({"A": _values(40, 12), "B": _values(40, 8)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _digit(results, "A").score == pytest.approx(50)

    def test_zero_team_share_scores_100_if_enumerator_rounds_at_all(self):
        data = _frame({"A": _values(40, 1), "B": _values(40, 0), "C": _values(40, 0)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _digit(results, "A").score == pytest.approx(100)
        # B's rest of team (A and C) has some rounding; B has none
        assert _digit(results, "B").score == pytest.approx(0)

    def test_zero_team_share_scores_0_if_enumerator_never_rounds(self):
        data = _frame({"A": _values(40, 0), "B": _values(40, 0)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _digit(results, "A").score == pytest.approx(0)

    def test_baseline_leaves_out_the_enumerator_being_scored(self):
        # A rounds 80%, B and C 20%. A's rest of team is B and C (20%); B's
        # is A and C (50%). A project-wide baseline would be 40% for both.
        data = _frame({"A": _values(40, 32), "B": _values(40, 8), "C": _values(40, 8)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _digit(results, "A").team_pct == pytest.approx(20)
        assert _digit(results, "B").team_pct == pytest.approx(50)

    def test_terminal_digit_uses_the_integer_part(self):
        # 10.9 ends in 0, 14.5 ends in 4, -25.2 floors to -26 and ends in 6
        data = _frame({"A": [10.9, 14.5, -25.2] * 10, "B": _values(30, 6)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _digit(results, "A")
        assert a.enum_digit_pct[0] == pytest.approx(100 / 3)
        assert a.enum_digit_pct[4] == pytest.approx(100 / 3)
        assert a.enum_digit_pct[6] == pytest.approx(100 / 3)
        assert len(a.team_digit_pct) == 10

    def test_responses_are_pooled_across_variables(self):
        data = pl.DataFrame(
            {
                ENUM: ["A"] * 20 + ["B"] * 20,
                "x": _values(20, 10) + _values(20, 2),
                "y": _values(20, 0) + _values(20, 2),
            }
        )
        settings = _settings(selected_variables=["x", "y"])

        results = compute_response_patterns(data, settings, ENUM, None)

        a = _digit(results, "A")
        assert a.n_responses == 40
        assert a.enum_pct == pytest.approx(25)
        assert a.team_pct == pytest.approx(10)


class TestMissingCodes:
    def test_missing_codes_are_excluded_before_scoring(self):
        # -995 ends in 5; once masked, A's responses are its 40 real values
        data = _frame({"A": _values(40, 0) + [-995] * 20, "B": _values(40, 8)})
        codes = pl.DataFrame({"label": ["Refused"], "codes": ["-995"]})

        results = compute_response_patterns(data, _settings(), ENUM, codes)

        a = _digit(results, "A")
        assert a.n_responses == 40
        assert a.enum_pct == pytest.approx(0)
        assert a.interviews == 60


class TestSampleBands:
    @pytest.mark.parametrize(
        ("n", "band"),
        [(14, "insufficient"), (15, "low"), (29, "low"), (30, "ok")],
    )
    def test_pooled_count_sets_the_band(self, n, band):
        data = _frame({"A": _values(n, 2), "B": _values(40, 8)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _digit(results, "A").sample_band == band

    def test_insufficient_enumerator_has_no_score_and_na_badge(self):
        data = _frame({"A": _values(10, 10), "B": _values(40, 8)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _digit(results, "A")
        assert a.score is None
        assert a.badge == "N/A"

    def test_thresholds_are_configurable(self):
        data = _frame({"A": _values(10, 2), "B": _values(40, 8)})
        settings = _settings(min_sample=5, warn_sample=8)

        results = compute_response_patterns(data, settings, ENUM, None)

        assert _digit(results, "A").sample_band == "ok"


class TestBadgesAndOrder:
    @pytest.mark.parametrize(
        ("threshold", "badge"),
        [(35, "High"), (50, "High"), (65, "Moderate"), (80, "Low")],
    )
    def test_badge_boundaries(self, threshold, badge):
        data = _frame({"A": _values(40, 12), "B": _values(40, 8)})  # score 50
        settings = _settings(digit_preference_threshold=threshold)

        results = compute_response_patterns(data, settings, ENUM, None)

        assert _digit(results, "A").badge == badge

    def test_sorted_highest_score_first_with_na_last(self):
        data = _frame(
            {
                "few": _values(5, 5),
                "mid": _values(40, 12),
                "top": _values(40, 20),
                "base": _values(40, 8),
            }
        )

        results = compute_response_patterns(data, _settings(), ENUM, None)

        names = [e.enumerator for e in results.digit_preference.enumerators]
        assert names[0] == "top"
        assert names[-1] == "few"
        scores = [e.score for e in results.digit_preference.enumerators[:-1]]
        assert scores == sorted(scores, reverse=True)


class TestVariableSkips:
    def test_range_under_10_is_skipped_with_a_reason(self):
        data = pl.DataFrame(
            {
                ENUM: ["A"] * 40 + ["B"] * 40,
                "x": _values(40, 8) + _values(40, 8),
                "kids": list(range(9)) * 8 + [0] * 8,
            }
        )
        settings = _settings(selected_variables=["x", "kids"])

        results = compute_response_patterns(data, settings, ENUM, None)

        dp = results.digit_preference
        assert dp.variables == ["x"]
        assert dp.skipped_variables == {"kids": "observed range under 10"}
        assert _digit(results, "A").n_responses == 40

    def test_no_variation_is_skipped_with_a_reason(self):
        data = pl.DataFrame(
            {
                ENUM: ["A"] * 40 + ["B"] * 40,
                "x": _values(40, 8) + _values(40, 8),
                "same": [100] * 80,
            }
        )
        settings = _settings(selected_variables=["x", "same"])

        results = compute_response_patterns(data, settings, ENUM, None)

        assert results.digit_preference.skipped_variables == {
            "same": "no variation across the project"
        }


class TestConditions:
    def test_no_variables_selected(self):
        data = _frame({"A": _values(40, 8), "B": _values(40, 8)})

        results = compute_response_patterns(data, ResponsePatternSettings(), ENUM, None)

        assert results.condition == "no_variables_selected"
        assert results.digit_preference is None

    def test_selected_variables_missing_from_the_data_count_as_none(self):
        data = _frame({"A": _values(40, 8), "B": _values(40, 8)})
        settings = _settings(selected_variables=["gone", ENUM])

        results = compute_response_patterns(data, settings, ENUM, None)

        assert results.condition == "no_variables_selected"

    def test_single_enumerator(self):
        data = _frame({"A": _values(40, 8)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert results.condition == "single_enumerator"

    def test_no_applicable_variables(self):
        data = pl.DataFrame({ENUM: ["A"] * 20 + ["B"] * 20, "x": ["yes", "no"] * 20})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert results.condition is None
        assert results.digit_preference.condition == "no_applicable_variables"

    def test_numeric_override_on_a_text_column_is_skipped(self):
        data = pl.DataFrame({ENUM: ["A"] * 20 + ["B"] * 20, "x": ["yes", "no"] * 20})
        settings = _settings(type_overrides={"x": "integer"})

        results = compute_response_patterns(data, settings, ENUM, None)

        dp = results.digit_preference
        assert dp.condition == "no_eligible_variables"
        assert dp.skipped_variables == {"x": "not a numeric column"}

    def test_categorical_override_removes_a_numeric_variable(self):
        data = _frame({"A": _values(40, 8), "B": _values(40, 8)})
        settings = _settings(type_overrides={"x": "categorical"})

        results = compute_response_patterns(data, settings, ENUM, None)

        assert results.digit_preference.condition == "no_applicable_variables"

    def test_everyone_below_the_minimum(self):
        data = _frame({"A": _values(10, 2, start=31), "B": _values(10, 2, start=31)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert results.digit_preference.condition == "all_below_minimum"


class TestThresholdLevels:
    @pytest.mark.parametrize(("saved", "level"), [(70, 65), (10, 20), (90, 80)])
    def test_saved_threshold_snaps_to_the_nearest_level(self, saved, level):
        settings = ResponsePatternSettings(digit_preference_threshold=saved)

        assert settings.digit_preference_threshold == level


class TestInferVariableTypes:
    def test_whole_floats_are_integer_and_fractions_continuous(self):
        data = pl.DataFrame(
            {
                "id": ["a", "b"],
                ENUM: ["A", "B"],
                "count": [1, 2],
                "whole": [1.0, None],
                "money": [1.5, 2.0],
                "choice": ["yes", "no"],
                "flag": [True, False],
            }
        )

        types = infer_variable_types(data, exclude=["id", ENUM])

        assert types == {
            "count": "integer",
            "whole": "integer",
            "money": "continuous",
            "choice": "categorical",
        }
