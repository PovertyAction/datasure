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


class TestDigitPreferenceRatio:
    def test_ratio_is_the_enumerator_share_over_the_team_share(self):
        data = _frame({"A": _values(40, 16), "B": _values(40, 8)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _digit(results, "A").ratio == pytest.approx(2)
        assert _digit(results, "A").enum_pct == pytest.approx(40)
        assert _digit(results, "A").team_pct == pytest.approx(20)
        assert _digit(results, "B").ratio == pytest.approx(0.5)

    def test_ratio_is_rounded_to_two_decimals_as_shown(self):
        # 13 of 40 against 9 of 40 is 1.444...
        data = _frame({"A": _values(40, 13), "B": _values(40, 9)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _digit(results, "A").ratio == 1.44

    def test_zero_team_share_has_no_ratio(self):
        data = _frame({"A": _values(40, 1), "B": _values(40, 0), "C": _values(40, 0)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _digit(results, "A").ratio is None
        assert _digit(results, "A").badge == "N/A"
        # B's rest of team (A and C) has some rounding; B has none
        assert _digit(results, "B").ratio == pytest.approx(0)

    def test_baseline_leaves_out_the_enumerator_being_checked(self):
        # A rounds 80%, B and C 20%. A's rest of team is B and C (20%); B's
        # is A and C (50%). A project-wide baseline would be 40% for both.
        data = _frame({"A": _values(40, 32), "B": _values(40, 8), "C": _values(40, 8)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _digit(results, "A").team_pct == pytest.approx(20)
        assert _digit(results, "B").team_pct == pytest.approx(50)

    def test_terminal_digit_uses_the_integer_part(self):
        # 10.9 ends in 0, 14.5 ends in 4, -26.8 truncates to -26 and ends in 6
        data = _frame({"A": [10.9, 14.5, -26.8] * 10, "B": _values(30, 6)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _digit(results, "A")
        assert a.enum_digit_pct[0] == pytest.approx(100 / 3)
        assert a.enum_digit_pct[4] == pytest.approx(100 / 3)
        assert a.enum_digit_pct[6] == pytest.approx(100 / 3)
        assert len(a.team_digit_pct) == 10

    def test_negative_values_take_the_digit_toward_zero(self):
        # -10.5 ends in 0 and -25.5 in 5, as 10.5 and 25.5 do
        data = _frame({"A": [-10.5, -25.5, 13.0] * 10, "B": _values(30, 6)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _digit(results, "A")
        assert a.enum_digit_pct[0] == pytest.approx(100 / 3)
        assert a.enum_digit_pct[5] == pytest.approx(100 / 3)
        assert a.enum_digit_pct[3] == pytest.approx(100 / 3)

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

    def test_insufficient_enumerator_has_no_ratio_and_na_badge(self):
        data = _frame({"A": _values(10, 10), "B": _values(40, 8)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _digit(results, "A")
        assert a.ratio is None
        assert a.badge == "N/A"

    def test_thresholds_are_configurable(self):
        data = _frame({"A": _values(10, 2), "B": _values(40, 8)})
        settings = _settings(min_sample=5, warn_sample=8)

        results = compute_response_patterns(data, settings, ENUM, None)

        assert _digit(results, "A").sample_band == "ok"

    def test_high_sensitivity_needs_100_responses(self):
        data = _frame({"A": _values(99, 30), "B": _values(100, 20)})
        settings = _settings(digit_preference_sensitivity="high")

        results = compute_response_patterns(data, settings, ENUM, None)

        dp = results.digit_preference
        assert dp.min_responses == 100
        assert _digit(results, "A").sample_band == "insufficient"
        assert _digit(results, "A").ratio is None
        assert _digit(results, "B").sample_band == "ok"

    def test_project_minimum_above_the_level_minimum_wins(self):
        data = _frame({"A": _values(40, 8), "B": _values(40, 8)})
        settings = _settings(digit_preference_sensitivity="high", min_sample=150)

        results = compute_response_patterns(data, settings, ENUM, None)

        assert results.digit_preference.min_responses == 150

    def test_medium_and_low_use_the_project_minimum(self):
        data = _frame({"A": _values(40, 8), "B": _values(40, 8)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert results.digit_preference.min_responses == 15


class TestBadgesAndOrder:
    @pytest.mark.parametrize(
        ("round_count", "sensitivity", "badge"),
        [
            (12, "medium", "High"),  # 1.5x reaches Medium
            (12, "low", "Moderate"),  # 1.5x reaches Medium, not Low
            (9, "medium", "Low"),  # 1.13x is under High and Medium
            (16, "low", "High"),  # 2x reaches Low
        ],
    )
    def test_badge_boundaries(self, round_count, sensitivity, badge):
        # The team ends 8 of 40 answers in 0 or 5
        data = _frame({"A": _values(40, round_count), "B": _values(40, 8)})
        settings = _settings(digit_preference_sensitivity=sensitivity)

        results = compute_response_patterns(data, settings, ENUM, None)

        assert _digit(results, "A").badge == badge

    def test_moderate_at_medium_needs_the_responses_high_needs(self):
        # 1.25x reaches High's ratio; High also needs 100 responses
        data = _frame({"A": _values(100, 25), "B": _values(100, 20)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _digit(results, "A").ratio == pytest.approx(1.25)
        assert _digit(results, "A").badge == "Moderate"

    def test_too_few_responses_for_high_is_not_moderate(self):
        # 1.25x on 40 responses: High would show N/A, so Medium shows Low
        data = _frame({"A": _values(40, 10), "B": _values(40, 8)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _digit(results, "A").ratio == pytest.approx(1.25)
        assert _digit(results, "A").badge == "Low"

    def test_most_sensitive_level_has_no_moderate_band(self):
        # 1.2x the team, just under High's 1.25x
        data = _frame({"A": _values(100, 24), "B": _values(100, 20)})
        settings = _settings(digit_preference_sensitivity="high")

        results = compute_response_patterns(data, settings, ENUM, None)

        assert _digit(results, "A").ratio == pytest.approx(1.2)
        assert _digit(results, "A").badge == "Low"

    def test_sorted_highest_ratio_first_with_na_last(self):
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
        ratios = [e.ratio for e in results.digit_preference.enumerators[:-1]]
        assert ratios == sorted(ratios, reverse=True)


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

    def test_numeric_override_on_text_without_numbers_is_skipped(self):
        data = pl.DataFrame({ENUM: ["A"] * 20 + ["B"] * 20, "x": ["yes", "no"] * 20})
        settings = _settings(type_overrides={"x": "integer"})

        results = compute_response_patterns(data, settings, ENUM, None)

        dp = results.digit_preference
        assert dp.condition == "no_eligible_variables"
        assert dp.skipped_variables == {"x": "no answers are numbers"}

    def test_numeric_override_on_text_numbers_is_checked(self):
        # Numbers stored as text; answers that aren't numbers count as missing
        values = [str(v) for v in _values(40, 16)] + [" 15 ", "n/a"]
        data = _frame({"A": values, "B": [str(v) for v in _values(40, 8)]})
        settings = _settings(type_overrides={"x": "integer"})

        results = compute_response_patterns(data, settings, ENUM, None)

        a = _digit(results, "A")
        assert results.digit_preference.skipped_variables == {}
        assert a.n_responses == 41
        assert a.ratio == pytest.approx(17 / 41 / 0.2, abs=0.01)

    def test_categorical_override_removes_a_numeric_variable(self):
        data = _frame({"A": _values(40, 8), "B": _values(40, 8)})
        settings = _settings(type_overrides={"x": "categorical"})

        results = compute_response_patterns(data, settings, ENUM, None)

        assert results.digit_preference.condition == "no_applicable_variables"

    def test_everyone_below_the_minimum(self):
        data = _frame({"A": _values(10, 2, start=31), "B": _values(10, 2, start=31)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert results.digit_preference.condition == "all_below_minimum"


class TestSensitivity:
    def test_defaults_to_medium(self):
        assert ResponsePatternSettings().digit_preference_sensitivity == "medium"

    def test_old_score_threshold_setting_is_ignored(self):
        settings = ResponsePatternSettings(digit_preference_threshold=80)

        assert settings.digit_preference_sensitivity == "medium"


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

    def test_gps_looking_columns_are_left_out(self):
        gps = [
            "household_latitude",
            "household_longitude",
            "hh_gps-Latitude",
            "hh_gps-Altitude",
            "hh_gps-Accuracy",
            "home-Accuracy",
            "geopoint_home",
            "lat",
            "plot_lng",
            "GPS_lon",
        ]
        kept = [
            "age",
            "how_long",
            "relation",
            "plate_count",
            "accuracy_score",
            # GPS-measured answers, not coordinates
            "plot_area_gps",
            "gps_area_ha",
        ]
        data = pl.DataFrame({col: [1.5, 2.5] for col in gps + kept})

        types = infer_variable_types(data)

        assert list(types) == kept


# =============================================================================
# Range Compression
# =============================================================================

# 40 values with a mean of 49.5 and a sample SD of about 11.7
BASE = [float(v) for v in range(30, 70)]


def _scaled(values: list[float], factor: float, shift: float = 0.0) -> list[float]:
    """Return ``values`` spread ``factor`` times as widely and moved by ``shift``."""
    mean = sum(values) / len(values)
    return [mean + (v - mean) * factor + shift for v in values]


def _sd(values: list[float]) -> float:
    mean = sum(values) / len(values)
    return (sum((v - mean) ** 2 for v in values) / (len(values) - 1)) ** 0.5


def _capped(values: list[float]) -> list[float]:
    """Cap values at their 5th and 95th percentiles (linear interpolation)."""
    ordered = sorted(values)

    def percentile(q: float) -> float:
        pos = q * (len(ordered) - 1)
        below = int(pos)
        above = min(below + 1, len(ordered) - 1)
        return ordered[below] + (ordered[above] - ordered[below]) * (pos - below)

    low, high = percentile(0.05), percentile(0.95)
    return [min(max(v, low), high) for v in values]


# The team SD scoring uses for BASE: after capping its extreme values
BASE_SD = _sd(_capped(BASE))


def _range(results, name: str):
    return next(
        e for e in results.range_compression.enumerators if e.enumerator == name
    )


class TestRangeCompressionSdRatio:
    @pytest.mark.parametrize("factor", [1.0, 0.5, 0.0, 2.0])
    def test_sd_ratio_is_the_enumerator_sd_over_the_team_sd(self, factor):
        data = _frame({"A": _scaled(BASE, factor), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _range(results, "A")
        assert a.sd_ratio == pytest.approx(factor)
        (var,) = a.variables
        assert var.sd_ratio == pytest.approx(factor)
        assert var.enum_sd == pytest.approx(factor * BASE_SD)
        assert var.team_sd == pytest.approx(BASE_SD)

    def test_sd_ratio_is_rounded_to_two_decimals_as_shown(self):
        data = _frame({"A": _scaled(BASE, 0.4444), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _range(results, "A").sd_ratio == 0.44

    @pytest.mark.parametrize(
        ("factor", "badge"), [(0.5, "High"), (0.6, "Moderate"), (0.7, "Low")]
    )
    def test_medium_flags_at_half_the_team_spread(self, factor, badge):
        data = _frame({"A": _scaled(BASE, factor), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _range(results, "A")
        assert a.badge == badge
        assert a.flagged_variables == (["x"] if badge == "High" else [])

    def test_a_shifted_mean_with_the_same_spread_is_not_flagged(self):
        data = _frame({"A": _scaled(BASE, 1.0, shift=3 * BASE_SD), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _range(results, "A")
        assert a.sd_ratio == pytest.approx(1)
        assert a.badge == "Low"
        (var,) = a.variables
        assert var.enum_mean - var.team_mean == pytest.approx(3 * BASE_SD)

    def test_baseline_leaves_out_the_enumerator_being_scored(self):
        # A answers 100 higher than B and C. A's rest of team is B and C
        # (mean 49.5); a project-wide mean would be 82.8. B's rest of team is
        # A and C, two equal blocks centred on 99.5.
        data = _frame({"A": _scaled(BASE, 1.0, shift=100), "B": BASE, "C": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (var,) = _range(results, "A").variables
        assert var.team_mean == pytest.approx(49.5)
        assert _range(results, "B").variables[0].team_mean == pytest.approx(99.5)

    def test_enumerator_sd_ratio_is_the_lowest_variable_ratio(self):
        data = pl.DataFrame(
            {
                ENUM: ["A"] * 40 + ["B"] * 40,
                "x": _scaled(BASE, 0.8) + BASE,
                "y": _scaled(BASE, 0.3) + BASE,
            }
        )
        settings = _settings(selected_variables=["x", "y"])

        results = compute_response_patterns(data, settings, ENUM, None)

        a = _range(results, "A")
        assert a.sd_ratio == pytest.approx(0.3)
        assert [v.variable for v in a.variables] == ["y", "x"]
        assert a.variables[1].sd_ratio == pytest.approx(0.8)
        assert a.flagged_variables == ["y"]

    def test_enumerators_are_sorted_lowest_sd_ratio_first(self):
        data = _frame({"A": _scaled(BASE, 0.9), "B": _scaled(BASE, 0.3), "C": BASE[:5]})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        names = [e.enumerator for e in results.range_compression.enumerators]
        assert names == ["B", "A", "C"]


class TestRangeCompressionTrimming:
    def test_one_extreme_value_does_not_flag_the_rest_of_the_team(self):
        # C recorded one 4,400 among answers of 30-69. Untrimmed, it sits in
        # A's and B's rest of team, so both would have an SD ratio near 0.
        data = _frame({"A": BASE, "B": BASE, "C": BASE[:-1] + [4400.0]})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        for name in ("A", "B", "C"):
            assert _range(results, name).sd_ratio > 0.85, name

    def test_extreme_values_are_capped_at_the_5th_and_95th_percentiles(self):
        # 0-99 capped at its 4.95 and 94.05 percentiles: the mean stays 49.5
        team = [float(v) for v in range(100)]
        data = _frame({"A": team, "B": team[:-1] + [10_000.0]})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (var,) = _range(results, "A").variables
        assert var.enum_mean == pytest.approx(49.5)
        assert var.team_mean < 51

    def test_enumerator_entirely_above_the_team_keeps_their_spread(self):
        # Every one of A's answers is above the team's 95th percentile, with
        # the same spread. Each side is capped at its own percentiles, so A's
        # spread is kept and A is not mistaken for compression.
        data = _frame({"A": _scaled(BASE, 1.0, shift=100), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _range(results, "A")
        assert a.sd_ratio == pytest.approx(1)
        assert a.flagged_variables == []


class TestRangeCompressionSkips:
    def test_team_sd_of_zero_skips_the_variable_with_no_variation(self):
        # The rest of the team always answers 50, so A's comparison has no SD
        data = pl.DataFrame(
            {
                ENUM: ["A"] * 40 + ["B"] * 40,
                "x": BASE + [50.0] * 40,
                "y": _scaled(BASE, 0.5) + BASE,
            }
        )
        settings = _settings(selected_variables=["x", "y"])

        results = compute_response_patterns(data, settings, ENUM, None)

        a = _range(results, "A")
        assert a.skipped_variables == {
            "x": "no variation in the rest of the team's responses"
        }
        assert [v.variable for v in a.variables] == ["y"]
        assert a.sd_ratio == pytest.approx(0.5)
        # B's rest of team (A) does vary, so B is scored on x
        assert "x" in [v.variable for v in _range(results, "B").variables]

    def test_no_variation_across_the_project_is_skipped_for_everyone(self):
        data = pl.DataFrame(
            {ENUM: ["A"] * 40 + ["B"] * 40, "x": BASE + BASE, "same": [7] * 80}
        )
        settings = _settings(selected_variables=["x", "same"])

        results = compute_response_patterns(data, settings, ENUM, None)

        rc = results.range_compression
        assert rc.variables == ["x"]
        assert rc.skipped_variables == {"same": "no variation across the project"}

    def test_narrow_range_is_still_checked(self):
        # Digit Preference skips ranges under 10; Range Compression does not
        kids = [float(v % 6) for v in range(40)]
        data = _frame({"A": _scaled(kids, 0.5), "B": kids})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _range(results, "A").sd_ratio == pytest.approx(0.5)

    def test_variable_below_the_minimum_is_skipped_for_that_enumerator(self):
        data = pl.DataFrame(
            {
                ENUM: ["A"] * 40 + ["B"] * 40,
                "x": _scaled(BASE, 0.5) + BASE,
                "y": BASE[:10] + [None] * 30 + BASE,
            }
        )
        settings = _settings(selected_variables=["x", "y"])

        results = compute_response_patterns(data, settings, ENUM, None)

        a = _range(results, "A")
        assert a.skipped_variables == {"y": "fewer responses than the minimum"}
        assert a.sample_band == "ok"

    def test_enumerator_below_the_minimum_everywhere_is_na(self):
        data = _frame({"A": BASE[:10], "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _range(results, "A")
        assert a.sd_ratio is None
        assert a.badge == "N/A"
        assert a.sample_band == "insufficient"
        assert results.range_compression.enumerators[-1].enumerator == "A"

    def test_sample_band_is_that_of_the_scoring_variable(self):
        data = _frame({"A": _scaled(BASE[:20], 0.5), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _range(results, "A").sample_band == "low"

    def test_everyone_below_the_minimum(self):
        data = _frame({"A": BASE[:10], "B": BASE[10:20]})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert results.range_compression.condition == "all_below_minimum"

    def test_missing_codes_are_excluded_before_scoring(self):
        data = _frame({"A": BASE + [-999.0] * 10, "B": BASE})
        codes = pl.DataFrame({"label": ["Don't know"], "codes": ["-999"]})

        results = compute_response_patterns(data, _settings(), ENUM, codes)

        (var,) = _range(results, "A").variables
        assert var.n_responses == 40
        assert var.sd_ratio == pytest.approx(1)

    def test_no_applicable_variables(self):
        data = pl.DataFrame({ENUM: ["A"] * 20 + ["B"] * 20, "x": ["yes", "no"] * 20})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert results.range_compression.condition == "no_applicable_variables"

    def test_numeric_override_on_text_numbers_is_checked(self):
        # Numbers stored as text are scored, as Digit Preference scores them
        data = _frame(
            {
                "A": [str(v) for v in _scaled(BASE, 0.5)] + ["n/a"],
                "B": [str(v) for v in BASE],
            }
        )
        settings = _settings(type_overrides={"x": "continuous"})

        results = compute_response_patterns(data, settings, ENUM, None)

        assert results.range_compression.skipped_variables == {}
        (var,) = _range(results, "A").variables
        assert var.n_responses == 40
        assert var.sd_ratio == pytest.approx(0.5)

    def test_numeric_override_on_text_without_numbers_is_skipped(self):
        data = pl.DataFrame({ENUM: ["A"] * 20 + ["B"] * 20, "x": ["yes", "no"] * 20})
        settings = _settings(type_overrides={"x": "integer"})

        results = compute_response_patterns(data, settings, ENUM, None)

        rc = results.range_compression
        assert rc.condition == "no_eligible_variables"
        assert rc.skipped_variables == {"x": "no answers are numbers"}


class TestRangeCompressionHistogram:
    def test_buckets_span_the_teams_1st_to_99th_percentile(self):
        team = [float(v) for v in range(101)]  # 1st percentile 1, 99th 99
        data = _frame({"A": _scaled(team, 0.5), "B": team})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (var,) = _range(results, "A").variables
        assert len(var.bucket_edges) == 11
        assert var.bucket_edges[0] == pytest.approx(1)
        assert var.bucket_edges[-1] == pytest.approx(99)
        assert var.bucket_edges[1] - var.bucket_edges[0] == pytest.approx(9.8)

    def test_both_series_share_the_buckets_and_sum_to_100(self):
        team = [float(v) for v in range(101)]
        data = _frame({"A": _scaled(team, 0.5), "B": team})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (var,) = _range(results, "A").variables
        assert len(var.enum_bucket_pct) == len(var.team_bucket_pct) == 10
        assert sum(var.enum_bucket_pct) == pytest.approx(100)
        # Values beyond the percentiles count in the end buckets
        assert sum(var.team_bucket_pct) == pytest.approx(100)
        assert var.team_bucket_pct[0] == pytest.approx(11 / 101 * 100)
        # A's values all sit in the middle half of the team's range
        assert var.enum_bucket_pct[0] == 0
        assert var.enum_bucket_pct[-1] == 0

    def test_fractional_answers_are_not_whole_numbers(self):
        team = [float(v) for v in range(101)]
        data = _frame({"A": _scaled(team, 0.5), "B": team})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (var,) = _range(results, "A").variables
        assert var.whole_numbers is False

    def test_whole_number_buckets_have_whole_number_edges(self):
        team = [float(v) for v in range(101)]  # 1st percentile 1, 99th 99
        data = _frame({"A": [float(v) for v in range(25, 76)], "B": team})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (var,) = _range(results, "A").variables
        assert var.whole_numbers is True
        # 99 values (1 to 99) in buckets of 10: 1-10, 11-20, ..., 91-100
        assert var.bucket_edges == [1 + 10 * i for i in range(11)]
        # 0 counts in the first bucket and 91 to 100 in the last
        assert var.team_bucket_pct[0] == pytest.approx(11 / 101 * 100)
        assert var.team_bucket_pct[-1] == pytest.approx(10 / 101 * 100)

    def test_whole_number_edges_widen_fractional_percentiles(self):
        # 1st percentile 0.1 and 99th 9.9 widen to 0 and 10: 11 values
        team = [float(v) for v in range(11)] * 3
        data = _frame({"A": [4.0, 5.0, 6.0] * 10, "B": team})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (var,) = _range(results, "A").variables
        assert var.bucket_edges == [0, 2, 4, 6, 8, 10, 12]
        assert var.enum_bucket_pct == pytest.approx([0, 0, 200 / 3, 100 / 3, 0, 0])

    def test_a_short_whole_number_scale_gets_one_bucket_per_value(self):
        team = [1.0, 2.0, 3.0, 4.0, 5.0] * 8
        data = _frame({"A": [2.0, 3.0, 4.0] * 10, "B": team})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (var,) = _range(results, "A").variables
        assert var.bucket_edges == [1, 2, 3, 4, 5, 6]
        assert var.team_bucket_pct == pytest.approx([20.0] * 5)
        assert var.enum_bucket_pct == pytest.approx([0, 100 / 3, 100 / 3, 100 / 3, 0])


class TestRangeCompressionSensitivity:
    @pytest.mark.parametrize(
        ("sensitivity", "badge"),
        [("high", "High"), ("medium", "Moderate"), ("low", "Low")],
    )
    def test_badge_follows_its_own_sensitivity(self, sensitivity, badge):
        # SD ratio 0.6: within High's 0.65 but above Medium's 0.5
        data = _frame({"A": _scaled(BASE, 0.6), "B": BASE})
        settings = _settings(range_compression_sensitivity=sensitivity)

        results = compute_response_patterns(data, settings, ENUM, None)

        assert _range(results, "A").badge == badge
        assert results.range_compression.sensitivity == sensitivity

    def test_most_sensitive_level_has_no_moderate_band(self):
        data = _frame({"A": _scaled(BASE, 0.7), "B": BASE})
        settings = _settings(range_compression_sensitivity="high")

        results = compute_response_patterns(data, settings, ENUM, None)

        assert _range(results, "A").badge == "Low"

    def test_sensitivity_is_independent_of_digit_preference(self):
        settings = ResponsePatternSettings(
            digit_preference_sensitivity="low", range_compression_sensitivity="high"
        )

        assert settings.digit_preference_sensitivity == "low"
        assert settings.range_compression_sensitivity == "high"
