"""Tests for datasure.checks.enumerator.attention: who needs attention, and why."""

from datetime import date, datetime, time, timedelta

import polars as pl
import pytest

from datasure.checks.enumerator.attention import (
    GPS_FLAG_POINTS,
    TIMES,
    AttentionRow,
    ColumnRoles,
    CountRule,
    IssueCounts,
    LeftOut,
    Reason,
    Severity,
    activity_reasons,
    attention_rows,
    attention_totals,
    count_reasons,
    counted_interviews,
    duration_minutes,
    duration_reasons,
    form_version_reasons,
    format_minutes,
    missing_column,
    missing_reasons,
    pattern_reasons,
    rate_reasons,
    row_label,
    shown_rows,
    submissions_by_enumerator,
    teams_by_enumerator,
    unattributed_notes,
)
from datasure.checks.enumerator.response_patterns.models import (
    Badge,
    CategoricalEnumerator,
    CategoricalOption,
    CategoricalQuestion,
    CategoricalResult,
    DigitPreferenceEnumerator,
    DigitPreferenceResult,
    PageCondition,
    RangeCompressionEnumerator,
    RangeCompressionResult,
    ResponsePatternResults,
    SampleBand,
    Sensitivity,
)

LATEST = date(2026, 11, 16)
ROLES = ColumnRoles("enum", "team", "day", "dur", "minutes", "version")


def _rows(enumerator: str, n: int, **values) -> dict[str, list]:
    """``n`` submissions by ``enumerator``, each with the given values."""
    return {"enum": [enumerator] * n, **{k: [v] * n for k, v in values.items()}}


def _frame(*parts: dict[str, list]) -> pl.DataFrame:
    return pl.concat([pl.DataFrame(part) for part in parts], how="diagonal_relaxed")


def _summary(rows: list[tuple]) -> pl.DataFrame:
    """A summary table with the columns the rules read."""
    return pl.DataFrame(
        rows,
        schema=["enum", "# submissions", "% Total Missing", "% consent"],
        orient="row",
    )


# --- Formatting --------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "unit", "minutes"),
    [
        (120, "seconds", 2),
        (3, "minutes", 3),
        (1.5, "hours", 90),
        (600, "default='seconds'", 10),
        (600, None, 10),
    ],
)
def test_duration_minutes_reads_unknown_units_as_seconds(value, unit, minutes):
    assert duration_minutes(value, unit) == minutes


@pytest.mark.parametrize(
    ("minutes", "text"),
    [(0.5, "30 s"), (19.4, "19 min"), (60, "1 h"), (80, "1 h 20 min")],
)
def test_format_minutes(minutes, text):
    assert format_minutes(minutes) == text


# --- Activity ----------------------------------------------------------------


def test_silent_enumerators_are_watched_from_the_latest_submission():
    data = pl.DataFrame(
        {
            "enum": ["a", "b", "c"],
            "day": [LATEST, LATEST - timedelta(days=2), LATEST - timedelta(days=5)],
        }
    )

    reasons = activity_reasons(data, ROLES)

    assert list(reasons) == ["c"]
    assert reasons["c"][0] == Reason(
        "Activity",
        "No submissions since Wed 11 Nov, 5 days before the latest submission "
        "(usually works daily)",
        Severity.WATCH,
    )


def test_a_weekly_worker_is_not_marked_after_a_quiet_week():
    """Silence counts against each enumerator's own pace."""
    weekly = [LATEST - timedelta(days=d) for d in (6, 13, 20, 27)]
    data = pl.DataFrame(
        {
            "enum": ["weekly"] * 4 + ["gone"] * 4 + ["daily"],
            "day": weekly
            + [LATEST - timedelta(days=d) for d in (22, 29, 36, 43)]
            + [LATEST],
        }
    )

    reasons = activity_reasons(data, ROLES)

    assert list(reasons) == ["gone"]
    assert reasons["gone"][0].finding.endswith("(usually works every 7 days)")


def test_activity_reads_datetimes_and_skips_text_dates():
    as_datetimes = pl.DataFrame(
        {"enum": ["a", "b"], "day": [datetime(2026, 11, 16, 9), datetime(2026, 11, 1)]}
    )
    as_text = as_datetimes.with_columns(pl.col("day").cast(pl.String))

    assert list(activity_reasons(as_datetimes, ROLES)) == ["b"]
    assert activity_reasons(as_text, ROLES) == {}


# --- Interview length --------------------------------------------------------


def test_short_interviews_are_flagged_against_the_team_median():
    data = _frame(
        _rows("fast", 6, dur=10.0),
        _rows("brisk", 6, dur=28.0),
        _rows("a", 6, dur=40.0),
        _rows("b", 6, dur=40.0),
        _rows("c", 6, dur=42.0),
    )

    reasons = duration_reasons(data, ROLES)

    assert reasons["fast"][0].severity is Severity.FLAG
    assert reasons["fast"][0].finding == (
        "Median 10 min against 40 min for the rest of the team"
    )
    assert reasons["brisk"][0].severity is Severity.WATCH
    assert set(reasons) == {"fast", "brisk"}


def test_short_interviews_compare_with_the_rest_of_the_team():
    """An enumerator with most of the interviews can't set their own benchmark."""
    data = _frame(_rows("fast", 20, dur=10.0), _rows("a", 6, dur=40.0))

    reasons = duration_reasons(data, ROLES)

    assert set(reasons) == {"fast"}
    assert reasons["fast"][0].severity is Severity.FLAG
    assert reasons["fast"][0].finding == (
        "Median 10 min against 40 min for the rest of the team"
    )


def test_a_lone_enumerator_has_no_team_to_compare_with():
    data = _frame(_rows("solo", 10, dur=10.0))

    assert duration_reasons(data, ROLES) == {}


def test_short_interviews_need_enough_submissions():
    data = _frame(_rows("new", 4, dur=5.0), _rows("a", 10, dur=40.0))

    assert duration_reasons(data, ROLES) == {}


def test_no_interview_length_without_a_duration_column():
    roles = ColumnRoles("enum", duration=None)
    assert duration_reasons(pl.DataFrame({"enum": ["a"]}), roles) == {}


def test_interviews_counted_are_the_consented_and_completed_ones():
    data = pl.DataFrame({"enum": ["a"] * 4, "ok": [1, 1, 0, 1], "done": [1, 0, 1, 1]})

    both, label = counted_interviews(
        data, ColumnRoles("enum", consent="ok", completed="done")
    )
    consent_only, consent_label = counted_interviews(
        data, ColumnRoles("enum", consent="ok")
    )
    unset, none = counted_interviews(data, ColumnRoles("enum"))

    assert (both.height, label) == (2, "completed interviews")
    assert (consent_only.height, consent_label) == (3, "consented interviews")
    assert (unset.height, none) == (4, None)


def test_interview_length_counts_only_completed_interviews():
    """Short refusals don't make an enumerator look rushed."""
    roles = ColumnRoles(
        "enum", duration="dur", duration_unit="minutes", completed="done"
    )
    data = _frame(
        _rows("refusals", 10, dur=2.0, done=0),
        _rows("refusals", 6, dur=38.0, done=1),
        _rows("fast", 6, dur=10.0, done=1),
        _rows("a", 6, dur=40.0, done=1),
        _rows("b", 6, dur=40.0, done=1),
    )

    reasons = duration_reasons(data, roles)

    assert set(reasons) == {"fast"}
    assert reasons["fast"][0].finding == (
        "Median 10 min over 6 completed interviews against 40 min for the rest "
        "of the team"
    )


def test_interview_length_needs_enough_completed_interviews():
    roles = ColumnRoles(
        "enum", duration="dur", duration_unit="minutes", completed="done"
    )
    data = _frame(
        _rows("fast", 4, dur=10.0, done=1),
        _rows("fast", 6, dur=10.0, done=0),
        _rows("a", 10, dur=40.0, done=1),
    )

    assert duration_reasons(data, roles) == {}


# --- Missing answers and rates -----------------------------------------------


def test_a_much_larger_share_of_missing_answers_is_flagged():
    summary = _summary(
        [
            ("a", 10, 3.0, 0.9),
            ("b", 10, 3.0, 0.9),
            ("c", 10, 4.0, 0.9),
            ("gaps", 10, 15.0, 0.9),
            ("some", 10, 9.0, 0.9),
            ("few", 3, 50.0, 0.9),
        ]
    )

    reasons = missing_reasons(summary, "enum")

    assert reasons["gaps"][0].severity is Severity.FLAG
    assert reasons["gaps"][0].finding == (
        "15% of answers missing against 3.5% for the rest of the team"
    )
    assert reasons["some"][0].severity is Severity.WATCH
    assert "few" not in reasons


def test_missing_answers_compare_with_the_rest_of_the_team():
    """In a small team, an enumerator's own share can't hide them."""
    summary = _summary([("a", 10, 2.0, 0.9), ("gaps", 10, 30.0, 0.9)])

    reasons = missing_reasons(summary, "enum")

    assert set(reasons) == {"gaps"}
    assert reasons["gaps"][0].finding == (
        "30% of answers missing against 2.0% for the rest of the team"
    )


def test_missing_answers_name_the_interviews_counted():
    summary = _summary([("a", 10, 2.0, 0.9), ("gaps", 10, 30.0, 0.9)])

    reasons = missing_reasons(summary, "enum", "completed interviews")

    assert reasons["gaps"][0].finding == (
        "30% of answers missing in completed interviews against 2.0% for the "
        "rest of the team"
    )


def test_missing_answers_fall_back_to_blanks_without_missing_codes():
    """Without missing codes the summary has only "% Null values"."""
    summary = _summary([("a", 10, 2.0, 0.9), ("gaps", 10, 30.0, 0.9)]).rename(
        {"% Total Missing": "% Null values"}
    )

    reasons = missing_reasons(summary, "enum")

    assert set(reasons) == {"gaps"}
    assert reasons["gaps"][0].severity is Severity.FLAG


def test_missing_column_prefers_the_total_with_missing_codes():
    assert missing_column(["% Null values", "% Total Missing"]) == "% Total Missing"
    assert missing_column(["% Null values"]) == "% Null values"
    assert missing_column(["# submissions"]) is None


def test_attention_rows_read_missing_answers_over_the_interviews_counted():
    """The narrowed table, not the summary, decides missing answers."""
    data = _frame(
        _rows("a", 6, done=1), _rows("b", 6, done=1), _rows("gaps", 6, done=1)
    )
    summary = _summary([("a", 6, 2.0, 0.9), ("b", 6, 2.0, 0.9), ("gaps", 6, 2.0, 0.9)])
    narrowed = _summary(
        [("a", 6, 2.0, 0.9), ("b", 6, 2.0, 0.9), ("gaps", 6, 30.0, 0.9)]
    )

    rows = attention_rows(
        data, ColumnRoles("enum", completed="done"), summary, missing=narrowed
    ).rows

    assert [row.enumerator for row in rows] == ["gaps"]
    assert "in completed interviews" in rows[0].reasons[0].finding


def test_low_consent_is_flagged_in_points_below_the_team():
    summary = _summary(
        [
            ("a", 10, 0.0, 0.95),
            ("b", 10, 0.0, 0.93),
            ("ok", 10, 0.0, 0.91),
            ("low", 10, 0.0, 0.71),
            ("lowish", 10, 0.0, 0.85),
        ]
    )

    reasons = rate_reasons(summary, "enum", "% consent", "Consent", "consent")

    assert reasons["low"][0] == Reason(
        "Consent",
        "71% consent against 92% for the rest of the team",
        Severity.FLAG,
    )
    assert "lowish" not in reasons


def test_rates_compare_with_the_rest_of_the_team():
    """In a small team, an enumerator's own rate can't hide them."""
    summary = _summary([("a", 10, 0.0, 0.95), ("low", 10, 0.0, 0.80)])

    reasons = rate_reasons(summary, "enum", "% consent", "Consent", "consent")

    assert set(reasons) == {"low"}
    assert reasons["low"][0].severity is Severity.FLAG


def test_rates_need_their_column():
    assert rate_reasons(pl.DataFrame(), "enum", "% consent", "Consent", "c") == {}
    assert missing_reasons(pl.DataFrame(), "enum") == {}


# --- Form version ------------------------------------------------------------


def test_old_versions_after_the_newest_came_out_are_flagged():
    data = pl.DataFrame(
        {
            "enum": ["a", "a", "b", "b", "c"],
            "version": [1, 2, 1, 1, 1],
            "day": [
                LATEST - timedelta(days=9),
                LATEST - timedelta(days=3),
                LATEST - timedelta(days=9),
                LATEST - timedelta(days=1),
                LATEST - timedelta(days=8),
            ],
        }
    )

    reasons = form_version_reasons(data, ROLES)

    assert list(reasons) == ["b"]
    assert reasons["b"][0].finding == (
        "1 submission on version 1 after 2 came out on Fri 13 Nov"
    )


def test_versions_stored_as_text_compare_as_numbers():
    """Version "10" is newer than "9", though "9" sorts after it as text."""
    data = pl.DataFrame(
        {
            "enum": ["a", "a", "b"],
            "version": ["9", "10", "9"],
            "day": [
                LATEST - timedelta(days=9),
                LATEST - timedelta(days=3),
                LATEST - timedelta(days=1),
            ],
        }
    )

    reasons = form_version_reasons(data, ROLES)

    assert list(reasons) == ["b"]
    assert reasons["b"][0].finding == (
        "1 submission on version 9 after 10 came out on Fri 13 Nov"
    )


def test_versions_that_are_not_numbers_compare_as_text():
    data = pl.DataFrame(
        {
            "enum": ["a", "b"],
            "version": ["v2", "v1"],
            "day": [LATEST - timedelta(days=3), LATEST - timedelta(days=1)],
        }
    )

    reasons = form_version_reasons(data, ROLES)

    assert list(reasons) == ["b"]


def test_submissions_before_the_update_on_its_day_are_not_flagged():
    """With times, only submissions after the newest version's first one count."""
    release_day = LATEST - timedelta(days=3)
    data = pl.DataFrame(
        {
            "enum": ["a", "b", "c"],
            "version": [2, 1, 1],
            "day": [
                datetime.combine(release_day, time(14)),
                datetime.combine(release_day, time(9)),
                datetime.combine(release_day, time(16)),
            ],
        }
    )

    reasons = form_version_reasons(data, ROLES)

    assert list(reasons) == ["c"]


def test_with_dates_only_the_release_day_itself_is_not_flagged():
    """Without times the order on the release day is unknown, so it is left out."""
    release_day = LATEST - timedelta(days=3)
    data = pl.DataFrame(
        {
            "enum": ["a", "b", "c"],
            "version": [2, 1, 1],
            "day": [release_day, release_day, release_day + timedelta(days=1)],
        }
    )

    reasons = form_version_reasons(data, ROLES)

    assert list(reasons) == ["c"]


def test_old_versions_within_a_day_of_the_update_are_watched():
    """Tablets take a while to update, so the first day is Watch, not Flagged."""
    release = datetime.combine(LATEST - timedelta(days=3), time(14))
    data = pl.DataFrame(
        {
            "enum": ["a", "late", "later", "later"],
            "version": [2, 1, 1, 1],
            "day": [
                release,
                release + timedelta(hours=23),
                release + timedelta(hours=2),
                release + timedelta(hours=25),
            ],
        }
    )

    reasons = form_version_reasons(data, ROLES)

    assert reasons["late"][0] == Reason(
        "Form version",
        "1 submission on version 1 after 2 came out on Fri 13 Nov, all within a "
        "day of it",
        Severity.WATCH,
    )
    assert reasons["later"][0].severity is Severity.FLAG
    assert reasons["later"][0].finding == (
        "2 submissions on version 1 after 2 came out on Fri 13 Nov"
    )


def test_with_dates_only_the_day_after_the_update_is_watched():
    release_day = LATEST - timedelta(days=3)
    data = pl.DataFrame(
        {
            "enum": ["a", "next", "after"],
            "version": [2, 1, 1],
            "day": [
                release_day,
                release_day + timedelta(days=1),
                release_day + timedelta(days=2),
            ],
        }
    )

    reasons = form_version_reasons(data, ROLES)

    assert reasons["next"][0].severity is Severity.WATCH
    assert reasons["after"][0].severity is Severity.FLAG


# --- Response patterns -------------------------------------------------------


def _patterns() -> ResponsePatternResults:
    question = CategoricalQuestion(
        variable="water_treat",
        n_responses=40,
        sample_band=SampleBand.OK,
        largest_gap=24.0,
        scoring_option="No",
        flagged=True,
        options=[
            CategoricalOption(
                option="No", enum_pct=60, team_pct=36, gap=24, flagged=True
            )
        ],
    )
    return ResponsePatternResults(
        min_sample=15,
        warn_sample=30,
        digit_preference=DigitPreferenceResult(
            sensitivity=Sensitivity.MEDIUM,
            min_responses=15,
            enumerators=[
                DigitPreferenceEnumerator(
                    enumerator="a",
                    interviews=20,
                    n_responses=200,
                    sample_band=SampleBand.OK,
                    ratio=2.1,
                    badge=Badge.HIGH,
                    enum_pct=40.0,
                    team_pct=19.0,
                ),
                DigitPreferenceEnumerator(
                    enumerator="b",
                    interviews=20,
                    n_responses=200,
                    sample_band=SampleBand.OK,
                    ratio=1.0,
                    badge=Badge.LOW,
                    enum_pct=19.0,
                    team_pct=19.0,
                ),
            ],
        ),
        range_compression=RangeCompressionResult(
            sensitivity=Sensitivity.MEDIUM,
            enumerators=[
                RangeCompressionEnumerator(
                    enumerator="b",
                    interviews=20,
                    sample_band=SampleBand.OK,
                    sd_ratio=0.5,
                    badge=Badge.MODERATE,
                    flagged_variables=["hh_income"],
                )
            ],
        ),
        categorical=CategoricalResult(
            sensitivity=Sensitivity.MEDIUM,
            enumerators=[
                CategoricalEnumerator(
                    enumerator="c",
                    interviews=20,
                    sample_band=SampleBand.OK,
                    largest_gap=24.0,
                    badge=Badge.HIGH,
                    questions=[question],
                )
            ],
        ),
    )


def test_high_badges_flag_and_moderate_badges_watch():
    reasons = pattern_reasons(_patterns())

    assert reasons["a"] == [
        Reason(
            "Digit preference",
            "40% of numeric answers end in 0 or 5 against 19% for the rest of the team",
            Severity.FLAG,
        )
    ]
    assert reasons["b"][0].check == "Range compression"
    assert reasons["b"][0].severity is Severity.WATCH
    assert "hh_income" in reasons["b"][0].finding
    assert reasons["c"][0].finding == (
        "Answers to water_treat differ from the team's by 24 points (option “No”)"
    )


def test_no_pattern_reasons_when_the_section_did_not_run():
    stopped = ResponsePatternResults(
        condition=PageCondition.NO_VARIABLES_SELECTED, min_sample=15, warn_sample=30
    )
    assert pattern_reasons(stopped) == {}
    assert pattern_reasons(None) == {}


def test_a_high_badge_on_a_low_sample_is_watched():
    results = _patterns()
    digit = results.digit_preference.enumerators[0]
    results.digit_preference.enumerators[0] = digit.model_copy(
        update={"sample_band": SampleBand.LOW}
    )

    reasons = pattern_reasons(results)

    assert reasons["a"][0].severity is Severity.WATCH
    assert reasons["a"][0].finding.endswith("(low sample)")
    assert reasons["c"][0].severity is Severity.FLAG


# --- Other checks' issues ----------------------------------------------------


def test_any_outstanding_issue_flags_under_the_any_rule():
    issues = IssueCounts(
        "Duplicates",
        "record with a duplicate ID",
        "records with a duplicate ID",
        {"a": 1, "b": 3, "gone": 2, "none": 0},
    )

    reasons = count_reasons(issues, {"a": 10, "b": 10, "none": 10})

    assert reasons == {
        "a": [Reason("Duplicates", "1 record with a duplicate ID", Severity.FLAG)],
        "b": [Reason("Duplicates", "3 records with a duplicate ID", Severity.FLAG)],
    }


def test_a_few_gps_points_are_watched_and_more_are_flagged():
    issues = IssueCounts(
        "GPS",
        "GPS point far from the others",
        "GPS points far from the others",
        {"one": 1, "two": 2, "three": GPS_FLAG_POINTS},
        flag_from=GPS_FLAG_POINTS,
    )

    reasons = count_reasons(issues, {"one": 10, "two": 10, "three": 10})

    assert reasons["one"][0].severity is Severity.WATCH
    assert reasons["two"][0].severity is Severity.WATCH
    assert reasons["three"][0] == Reason(
        "GPS", "3 GPS points far from the others", Severity.FLAG
    )


def test_the_relative_rule_compares_rates_with_the_team():
    issues = IssueCounts(
        "Outliers",
        "outlier",
        "outliers",
        {"high": 12, "raised": 8, "few": 2, "usual": 3},
        rule=CountRule.RELATIVE,
    )
    submissions = {"high": 20, "raised": 20, "few": 2, "usual": 20, "clean": 38}

    reasons = count_reasons(issues, submissions)

    # The team's rate is 25 outliers in 100 submissions.
    assert reasons["high"] == [
        Reason(
            "Outliers",
            f"12 outliers, 2.4{TIMES} the team's rate per submission",
            Severity.FLAG,
        )
    ]
    assert reasons["raised"][0].severity is Severity.WATCH
    assert set(reasons) == {"high", "raised"}


def test_the_relative_rule_can_use_its_own_denominators():
    issues = IssueCounts(
        "Backchecks",
        "backcheck mismatch",
        "backcheck mismatches",
        {"a": 6, "b": 1},
        rule=CountRule.RELATIVE,
        denominators={"a": 10, "b": 30},
        per="value compared",
    )

    reasons = count_reasons(issues, {"a": 100, "b": 100})

    assert reasons["a"][0].finding == (
        f"6 backcheck mismatches, 3.4{TIMES} the team's rate per value compared"
    )


def test_issues_with_no_enumerator_are_noted_per_check():
    counts = [
        IssueCounts("Duplicates", "record", "records", {"a": 2}, unattributed=3),
        IssueCounts("GPS", "point", "points", {"a": 1}, unattributed=1),
        IssueCounts("Outliers", "outlier", "outliers", {"a": 4}),
    ]

    assert unattributed_notes(counts) == [
        "Duplicates: 3 records have no enumerator, so no row above shows them.",
        "GPS: 1 point has no enumerator, so no row above shows it.",
    ]


# --- The list ----------------------------------------------------------------


def test_attention_rows_merge_reasons_and_put_most_flags_first():
    data = _frame(
        _rows("a", 6, team="North", day=LATEST, dur=10.0),
        _rows("b", 6, team="South", day=LATEST - timedelta(days=4), dur=40.0),
        _rows("c", 6, team="South", day=LATEST, dur=40.0),
        _rows("d", 6, team="South", day=LATEST, dur=41.0),
    )
    duplicates = IssueCounts("Duplicates", "record", "records", {"a": 2, "c": 1})

    attention = attention_rows(data, ROLES, pl.DataFrame(), None, [duplicates])
    rows = attention.rows

    assert attention.left_out == ()
    assert [row.enumerator for row in rows] == ["a", "c", "b"]
    assert rows[0].team == "North"
    assert [r.check for r in rows[0].reasons] == ["Duplicates", "Interview length"]
    assert [row_label(row) for row in rows] == ["2 flagged", "1 flagged", "1 watch"]


def _listed(name: str, flags: int, watches: int) -> AttentionRow:
    return AttentionRow(
        name,
        None,
        tuple(Reason(f"F{i}", "f", Severity.FLAG) for i in range(flags))
        + tuple(Reason(f"W{i}", "w", Severity.WATCH) for i in range(watches)),
    )


def test_totals_count_an_enumerator_with_both_severities_under_both():
    rows = [_listed("both", 2, 1), _listed("flag", 1, 0), _listed("watch", 0, 3)]

    totals = attention_totals(rows)

    assert (totals.flagged, totals.flags) == (2, 3)
    assert (totals.watched, totals.watches) == (2, 4)
    assert totals.listed == 3


def test_shown_rows_keep_only_the_severities_shown():
    rows = [_listed("both", 2, 1), _listed("flag", 1, 0), _listed("watch", 0, 3)]

    watch_only = shown_rows(rows, flagged=False)
    flagged_only = shown_rows(rows, watch=False)

    # Ordered by the Watch count once Flagged is hidden.
    assert [row.enumerator for row in watch_only] == ["watch", "both"]
    assert {r.severity for row in watch_only for r in row.reasons} == {Severity.WATCH}
    assert [row.enumerator for row in flagged_only] == ["both", "flag"]
    assert shown_rows(rows, flagged=False, watch=False) == []
    assert [row.enumerator for row in shown_rows(rows)] == ["both", "flag", "watch"]


def test_row_label_counts_each_severity_and_leaves_out_zeros():
    assert row_label(_listed("a", 2, 1)) == "2 flagged · 1 watch"
    assert row_label(_listed("b", 0, 3)) == "3 watch"
    assert row_label(_listed("c", 1, 0)) == "1 flagged"


def test_attention_rows_leave_out_enumerators_not_in_view():
    data = _frame(_rows("a", 6, day=LATEST), _rows("b", 6, day=LATEST))
    other = IssueCounts("GPS", "point", "points", {"elsewhere": 4, "a": 1})

    attention = attention_rows(data, ColumnRoles("enum"), pl.DataFrame(), None, [other])

    assert [row.enumerator for row in attention.rows] == ["a"]


def test_a_failing_rule_is_left_out_and_the_others_still_count(monkeypatch):
    data = _frame(
        _rows("a", 6, day=LATEST, dur=10.0),
        _rows("b", 6, day=LATEST, dur=40.0),
        _rows("c", 6, day=LATEST, dur=41.0),
    )
    duplicates = IssueCounts("Duplicates", "record", "records", {"b": 1})

    def broken(*_args):
        raise ValueError("bad dates")

    monkeypatch.setattr("datasure.checks.enumerator.attention.activity_reasons", broken)

    attention = attention_rows(data, ROLES, pl.DataFrame(), None, [duplicates])

    assert attention.left_out == (
        LeftOut(
            "Activity", "ValueError: bad dates", "Review this page's settings above."
        ),
    )
    assert {row.enumerator for row in attention.rows} == {"a", "b"}


def test_a_failing_check_names_where_to_review_it(monkeypatch):
    data = _frame(_rows("a", 6, day=LATEST))
    outliers = IssueCounts("Outliers", "outlier", "outliers", {"a": 9})

    def broken(*_args):
        raise KeyError("rate")

    monkeypatch.setattr("datasure.checks.enumerator.attention.count_reasons", broken)

    attention = attention_rows(data, ROLES, pl.DataFrame(), None, [outliers])

    (left_out,) = attention.left_out
    assert left_out.message == (
        "Outliers is left out of this list: its numbers could not be computed "
        "(KeyError: 'rate'). Open Outliers to review its settings."
    )


def test_counts_and_teams_by_enumerator_read_names_as_text():
    data = pl.DataFrame({"enum": [1, 1, 2], "team": ["x", "x", "y"]})

    assert submissions_by_enumerator(data, "enum") == {"1": 2, "2": 1}
    assert teams_by_enumerator(data, ColumnRoles("enum", "team")) == {
        "1": "x",
        "2": "y",
    }
