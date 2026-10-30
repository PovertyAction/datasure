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
        kept = ["age", "how_long", "relation", "plate_count", "accuracy_score"]
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


class TestRangeCompressionScore:
    @pytest.mark.parametrize(("factor", "score"), [(1.0, 0), (0.5, 50), (0.0, 100)])
    def test_compression_score_falls_with_the_sd_ratio(self, factor, score):
        data = _frame({"A": _scaled(BASE, factor), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _range(results, "A")
        assert a.score == pytest.approx(score)
        assert a.signal == "compression"
        (var,) = a.variables
        assert var.sd_ratio == pytest.approx(factor)
        assert var.compression_score == pytest.approx(score)
        assert var.shift_score == pytest.approx(0)

    def test_wider_spread_than_the_team_scores_0(self):
        data = _frame({"A": _scaled(BASE, 2.0), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _range(results, "A").score == pytest.approx(0)

    @pytest.mark.parametrize(
        ("team_sds", "score"), [(0, 0), (50 / 33, 50), (100 / 33, 100), (5, 100)]
    )
    def test_shift_score_rises_33_points_per_team_sd(self, team_sds, score):
        data = _frame({"A": _scaled(BASE, 1.0, shift=team_sds * BASE_SD), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _range(results, "A")
        assert a.score == pytest.approx(score)
        (var,) = a.variables
        assert var.shift_score == pytest.approx(score)
        assert var.compression_score == pytest.approx(0)
        assert var.enum_mean - var.team_mean == pytest.approx(team_sds * BASE_SD)

    def test_shift_below_the_team_scores_the_same_as_above(self):
        data = _frame({"A": _scaled(BASE, 1.0, shift=-50 / 33 * BASE_SD), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _range(results, "A").score == pytest.approx(50)
        assert _range(results, "A").signal == "shift"

    def test_both_signals_fire_and_the_higher_sets_the_score(self):
        # Half the spread (compression 50) and 2 team SDs up (shift 66)
        data = _frame({"A": _scaled(BASE, 0.5, shift=2 * BASE_SD), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _range(results, "A")
        assert a.score == pytest.approx(66)
        assert a.signal == "shift"
        assert a.badge == "High"
        assert a.compression_variables == ["x"]
        assert a.shift_variables == ["x"]

    def test_only_signals_reaching_the_threshold_are_listed(self):
        data = _frame({"A": _scaled(BASE, 0.4, shift=1 * BASE_SD), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _range(results, "A")
        assert a.signal == "compression"
        assert a.compression_variables == ["x"]
        assert a.shift_variables == []

    def test_baseline_leaves_out_the_enumerator_being_scored(self):
        # A answers 100 higher than B and C. A's rest of team is B and C
        # (mean 49.5); a project-wide mean would be 82.8. B's rest of team is
        # A and C, two equal blocks centred on 99.5.
        data = _frame({"A": _scaled(BASE, 1.0, shift=100), "B": BASE, "C": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (var,) = _range(results, "A").variables
        assert var.team_mean == pytest.approx(49.5)
        assert _range(results, "B").variables[0].team_mean == pytest.approx(99.5)

    def test_enumerator_score_is_the_highest_variable_score(self):
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
        assert a.score == pytest.approx(70)
        assert [v.variable for v in a.variables] == ["y", "x"]
        assert a.variables[1].score == pytest.approx(20)


class TestRangeCompressionTrimming:
    def test_one_extreme_value_does_not_flag_the_rest_of_the_team(self):
        # C recorded one 4,400 among answers of 30-69. Untrimmed, it sits in
        # A's and B's rest of team, so both would score 100 for compression,
        # and C would score 100 for shift.
        data = _frame({"A": BASE, "B": BASE, "C": BASE[:-1] + [4400.0]})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        for name in ("A", "B", "C"):
            assert _range(results, name).score < 15, name

    def test_extreme_values_are_capped_at_the_5th_and_95th_percentiles(self):
        # 0-99 capped at its 4.95 and 94.05 percentiles: the mean stays 49.5
        team = [float(v) for v in range(100)]
        data = _frame({"A": team, "B": team[:-1] + [10_000.0]})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (var,) = _range(results, "A").variables
        assert var.enum_mean == pytest.approx(49.5)
        assert var.team_mean < 51

    def test_enumerator_entirely_above_the_team_is_flagged_for_shift(self):
        # Every one of A's answers is above the team's 95th percentile, with
        # the same spread. Each side is capped at its own percentiles, so A's
        # spread is kept and A is not mistaken for compression.
        data = _frame({"A": _scaled(BASE, 1.0, shift=100), "B": BASE})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _range(results, "A")
        assert a.signal == "shift"
        assert a.variables[0].sd_ratio == pytest.approx(1)
        assert a.compression_variables == []


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
        assert a.score == pytest.approx(50)
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

        assert _range(results, "A").score == pytest.approx(50)

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
        assert a.score is None
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
        assert var.score == pytest.approx(0)

    def test_no_applicable_variables(self):
        data = pl.DataFrame({ENUM: ["A"] * 20 + ["B"] * 20, "x": ["yes", "no"] * 20})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert results.range_compression.condition == "no_applicable_variables"


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


class TestRangeCompressionThreshold:
    @pytest.mark.parametrize(
        ("threshold", "badge"), [(50, "High"), (65, "Moderate"), (80, "Low")]
    )
    def test_badge_follows_its_own_threshold(self, threshold, badge):
        data = _frame({"A": _scaled(BASE, 0.5), "B": BASE})
        settings = _settings(range_compression_threshold=threshold)

        results = compute_response_patterns(data, settings, ENUM, None)

        assert _range(results, "A").badge == badge
        assert results.range_compression.threshold == threshold

    def test_saved_threshold_snaps_to_the_nearest_level(self):
        settings = ResponsePatternSettings(range_compression_threshold=90)

        assert settings.range_compression_threshold == 80


# =============================================================================
# Categorical Response Patterns
# =============================================================================


def _choices(counts: dict[str, int]) -> list[str]:
    """Return each option repeated its count times."""
    return [option for option, n in counts.items() for _ in range(n)]


def _categorical(results, name: str):
    return next(e for e in results.categorical.enumerators if e.enumerator == name)


class TestCategoricalScore:
    @pytest.mark.parametrize(
        ("enum_yes", "gap", "score"),
        [(20, 0, 0), (30, 25, 50), (40, 50, 100), (36, 40, 80)],
    )
    def test_score_is_twice_the_largest_gap(self, enum_yes, gap, score):
        # The rest of the team answers yes half the time; A's yes share of
        # 50%, 75% and 100% is a gap of 0, 25 and 50 points
        data = _frame(
            {
                "A": _choices({"yes": enum_yes, "no": 40 - enum_yes}),
                "B": _choices({"yes": 20, "no": 20}),
            }
        )

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _categorical(results, "A")
        assert a.score == pytest.approx(score)
        (question,) = a.questions
        assert question.score == pytest.approx(score)
        assert question.largest_gap == pytest.approx(gap)

    def test_gap_beyond_50_points_is_capped_at_100(self):
        data = _frame({"A": _choices({"yes": 40}), "B": _choices({"yes": 8, "no": 32})})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _categorical(results, "A").score == pytest.approx(100)

    def test_baseline_leaves_out_the_enumerator_being_scored(self):
        # A always says yes; B and C split evenly. A's rest of team says yes
        # 50% of the time (gap 50, score 100). B's rest of team is A and C,
        # 75% yes (gap 25, score 50). A project-wide 66.7% would give 67 and
        # 33.
        data = _frame(
            {
                "A": _choices({"yes": 40}),
                "B": _choices({"yes": 20, "no": 20}),
                "C": _choices({"yes": 20, "no": 20}),
            }
        )

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert _categorical(results, "A").score == pytest.approx(100)
        assert _categorical(results, "B").score == pytest.approx(50)
        yes = _categorical(results, "B").questions[0].options[1]
        assert (yes.option, yes.team_pct) == ("yes", pytest.approx(75))

    def test_enumerator_score_is_the_highest_question_score(self):
        data = pl.DataFrame(
            {
                ENUM: ["A"] * 40 + ["B"] * 40,
                "x": _choices({"yes": 24, "no": 16}) + _choices({"yes": 20, "no": 20}),
                "y": _choices({"yes": 32, "no": 8}) + _choices({"yes": 20, "no": 20}),
            }
        )
        settings = _settings(selected_variables=["x", "y"])

        results = compute_response_patterns(data, settings, ENUM, None)

        a = _categorical(results, "A")
        assert a.score == pytest.approx(60)
        assert [q.variable for q in a.questions] == ["y", "x"]
        assert [q.score for q in a.questions] == [pytest.approx(60), pytest.approx(20)]


class TestCategoricalOptions:
    def test_options_only_one_side_chose_count_as_0_on_the_other(self):
        # A never says "maybe"; only A says "dk"
        data = _frame(
            {
                "A": _choices({"yes": 20, "dk": 20}),
                "B": _choices({"yes": 20, "maybe": 20}),
            }
        )

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (question,) = _categorical(results, "A").questions
        shares = {o.option: (o.enum_pct, o.team_pct) for o in question.options}
        assert shares == {
            "dk": (pytest.approx(50), 0),
            "maybe": (0, pytest.approx(50)),
            "yes": (pytest.approx(50), pytest.approx(50)),
        }
        assert question.score == pytest.approx(100)

    def test_options_at_half_the_threshold_are_flagged_either_way(self):
        # Gaps: yes +25, no -15, dk -10. At threshold 50 the cut-off is 25.
        data = _frame(
            {
                "A": _choices({"yes": 30, "no": 6, "dk": 4}),
                "B": _choices({"yes": 20, "no": 12, "dk": 8}),
            }
        )

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (question,) = _categorical(results, "A").questions
        assert {o.option: o.flagged for o in question.options} == {
            "dk": False,
            "no": False,
            "yes": True,
        }
        assert question.flagged
        assert question.dominant_option == "yes"
        assert {o.option: o.gap for o in question.options} == {
            "dk": pytest.approx(-10),
            "no": pytest.approx(-15),
            "yes": pytest.approx(25),
        }

    def test_under_used_option_is_flagged_below_the_threshold_too(self):
        # Gaps: no -15 and yes +15. At threshold 20 the cut-off is 10.
        data = _frame(
            {
                "A": _choices({"yes": 26, "no": 14}),
                "B": _choices({"yes": 20, "no": 20}),
            }
        )
        settings = _settings(categorical_threshold=20)

        results = compute_response_patterns(data, settings, ENUM, None)

        (question,) = _categorical(results, "A").questions
        assert all(o.flagged for o in question.options)

    def test_scoring_option_can_be_one_the_enumerator_avoids(self):
        # Team a/b/c 60/20/20, A 0/50/50: never choosing a (-60) sets the
        # score; b is the first of the over-chosen options (+30)
        data = _frame(
            {
                "A": _choices({"b": 20, "c": 20}),
                "B": _choices({"a": 24, "b": 8, "c": 8}),
            }
        )

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (question,) = _categorical(results, "A").questions
        assert question.score == pytest.approx(100)
        assert question.scoring_option == "a"
        assert question.dominant_option == "b"

    def test_consistent_question_is_not_flagged_and_has_no_dominant_option(self):
        data = _frame(
            {
                "A": _choices({"yes": 20, "no": 20}),
                "B": _choices({"yes": 20, "no": 20}),
            }
        )

        results = compute_response_patterns(data, _settings(), ENUM, None)

        (question,) = _categorical(results, "A").questions
        assert not question.flagged
        assert question.dominant_option is None
        assert not any(o.flagged for o in question.options)

    def test_numeric_codes_are_options_in_value_order(self):
        data = _frame({"A": [1, 2, 10] * 14, "B": [2, 10, 1] * 14})
        settings = _settings(type_overrides={"x": "categorical"})

        results = compute_response_patterns(data, settings, ENUM, None)

        (question,) = _categorical(results, "A").questions
        assert [o.option for o in question.options] == ["1", "2", "10"]
        assert results.digit_preference.condition == "no_applicable_variables"


class TestCategoricalSkipsAndConditions:
    def test_no_applicable_variables_when_none_are_categorical(self):
        data = _frame({"A": _values(40, 8), "B": _values(40, 8)})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert results.categorical.condition == "no_applicable_variables"

    def test_one_answer_across_the_project_is_skipped(self):
        data = pl.DataFrame(
            {
                ENUM: ["A"] * 40 + ["B"] * 40,
                "x": _choices({"yes": 20, "no": 20}) * 2,
                "same": ["yes"] * 80,
            }
        )
        settings = _settings(selected_variables=["x", "same"])

        results = compute_response_patterns(data, settings, ENUM, None)

        cat = results.categorical
        assert cat.variables == ["x"]
        assert cat.skipped_variables == {"same": "no variation across the project"}

    def test_question_below_the_minimum_is_skipped_for_that_enumerator(self):
        data = pl.DataFrame(
            {
                ENUM: ["A"] * 40 + ["B"] * 40,
                "x": _choices({"yes": 30, "no": 10}) + _choices({"yes": 20, "no": 20}),
                "y": ["yes"] * 10 + [None] * 30 + _choices({"yes": 20, "no": 20}),
            }
        )
        settings = _settings(selected_variables=["x", "y"])

        results = compute_response_patterns(data, settings, ENUM, None)

        a = _categorical(results, "A")
        assert a.skipped_variables == {"y": "fewer responses than the minimum"}
        assert [q.variable for q in a.questions] == ["x"]

    def test_rest_of_team_without_answers_skips_the_question(self):
        data = pl.DataFrame(
            {
                ENUM: ["A"] * 40 + ["B"] * 40,
                "x": _choices({"yes": 20, "no": 20}) + [None] * 40,
            }
        )

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _categorical(results, "A")
        assert a.score is None
        assert a.skipped_variables == {"x": "no responses from the rest of the team"}

    def test_enumerator_below_the_minimum_everywhere_is_na_and_last(self):
        data = _frame(
            {
                "A": _choices({"yes": 10}),
                "B": _choices({"yes": 20, "no": 20}),
                "C": _choices({"yes": 20, "no": 20}),
            }
        )

        results = compute_response_patterns(data, _settings(), ENUM, None)

        a = _categorical(results, "A")
        assert (a.score, a.badge, a.sample_band) == (None, "N/A", "insufficient")
        assert results.categorical.enumerators[-1].enumerator == "A"

    def test_everyone_below_the_minimum(self):
        data = _frame({"A": _choices({"yes": 5, "no": 5}), "B": ["no"] * 10})

        results = compute_response_patterns(data, _settings(), ENUM, None)

        assert results.categorical.condition == "all_below_minimum"

    def test_missing_codes_are_excluded_before_scoring(self):
        data = _frame(
            {
                "A": _choices({"yes": 20, "no": 20, "-99": 30}),
                "B": _choices({"yes": 20, "no": 20}),
            }
        )
        codes = pl.DataFrame({"label": ["Refused"], "codes": ["-99"]})

        results = compute_response_patterns(data, _settings(), ENUM, codes)

        (question,) = _categorical(results, "A").questions
        assert question.n_responses == 40
        assert question.score == pytest.approx(0)


class TestCategoricalThreshold:
    @pytest.mark.parametrize(
        ("threshold", "badge"), [(50, "High"), (65, "Moderate"), (80, "Low")]
    )
    def test_badge_follows_its_own_threshold(self, threshold, badge):
        data = _frame(
            {
                "A": _choices({"yes": 30, "no": 10}),
                "B": _choices({"yes": 20, "no": 20}),
            }
        )  # gap 25, score 50
        settings = _settings(categorical_threshold=threshold)

        results = compute_response_patterns(data, settings, ENUM, None)

        assert _categorical(results, "A").badge == badge
        assert results.categorical.threshold == threshold

    def test_saved_threshold_snaps_to_the_nearest_level(self):
        settings = ResponsePatternSettings(categorical_threshold=10)

        assert settings.categorical_threshold == 20
