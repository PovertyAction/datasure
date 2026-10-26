"""The comparison period of Summary's check health rows."""

from datetime import date, datetime

import polars as pl
import pytest

from datasure.checks.health_period import (
    WEEKDAYS,
    ComparisonPeriod,
    dated_after,
    latest_date,
    on_or_before,
    period_start,
    since_label,
)

# A Monday.
MONDAY = date(2026, 10, 26)


class TestPeriodStart:
    """The period start is the date whose end the deltas compare with."""

    def test_day_compares_with_the_end_of_yesterday(self):
        assert period_start(ComparisonPeriod.DAY, MONDAY) == date(2026, 10, 25)

    def test_day_crosses_month_and_year_boundaries(self):
        assert period_start(ComparisonPeriod.DAY, date(2026, 3, 1)) == date(2026, 2, 28)
        assert period_start(ComparisonPeriod.DAY, date(2027, 1, 1)) == date(
            2026, 12, 31
        )

    def test_seven_days_compares_with_seven_days_ago(self):
        assert period_start(ComparisonPeriod.SEVEN_DAYS, MONDAY) == date(2026, 10, 19)

    def test_thirty_days_compares_with_thirty_days_ago(self):
        assert period_start(ComparisonPeriod.THIRTY_DAYS, MONDAY) == date(2026, 9, 26)

    def test_week_defaults_to_starting_on_sunday(self):
        # The week began on Sunday 25 Oct, so it compares with Saturday's end.
        assert period_start(ComparisonPeriod.WEEK, MONDAY) == date(2026, 10, 24)

    def test_week_starting_today_compares_with_yesterday(self):
        assert period_start(ComparisonPeriod.WEEK, MONDAY, "Monday") == date(
            2026, 10, 25
        )

    def test_week_start_is_selectable(self):
        # Wednesday 21 Oct began the week.
        assert period_start(ComparisonPeriod.WEEK, MONDAY, "Wednesday") == date(
            2026, 10, 20
        )
        # Tuesday 20 Oct began the week.
        assert period_start(ComparisonPeriod.WEEK, MONDAY, "Tuesday") == date(
            2026, 10, 19
        )

    def test_week_crosses_a_month_boundary(self):
        # Thursday 1 Oct 2026; the week began on Sunday 27 Sep.
        assert period_start(ComparisonPeriod.WEEK, date(2026, 10, 1)) == date(
            2026, 9, 26
        )

    def test_month_compares_with_the_end_of_last_month(self):
        assert period_start(ComparisonPeriod.MONTH, MONDAY) == date(2026, 9, 30)

    def test_month_on_the_first_compares_with_last_month(self):
        assert period_start(ComparisonPeriod.MONTH, date(2026, 10, 1)) == date(
            2026, 9, 30
        )

    def test_month_crosses_the_year_and_leap_day(self):
        assert period_start(ComparisonPeriod.MONTH, date(2027, 1, 15)) == date(
            2026, 12, 31
        )
        assert period_start(ComparisonPeriod.MONTH, date(2028, 3, 31)) == date(
            2028, 2, 29
        )

    def test_unknown_week_start_raises(self):
        with pytest.raises(ValueError, match="Funday"):
            period_start(ComparisonPeriod.WEEK, MONDAY, "Funday")

    def test_weekdays_start_on_sunday(self):
        assert WEEKDAYS[0] == "Sunday"
        assert len(WEEKDAYS) == 7


class TestSinceLabel:
    @pytest.mark.parametrize(
        ("period", "label"),
        [
            (ComparisonPeriod.DAY, "yesterday"),
            (ComparisonPeriod.SEVEN_DAYS, "7 days ago"),
            (ComparisonPeriod.WEEK, "Sunday"),
            (ComparisonPeriod.THIRTY_DAYS, "30 days ago"),
            (ComparisonPeriod.MONTH, "1 Oct"),
        ],
    )
    def test_label_names_where_the_period_starts(self, period, label):
        assert since_label(period, MONDAY) == label

    def test_week_label_names_the_week_start(self):
        assert since_label(ComparisonPeriod.WEEK, MONDAY, "Monday") == "Monday"


class TestDatedRows:
    """Splitting submissions at the period start."""

    @pytest.mark.parametrize(
        "dates",
        [
            [date(2026, 10, 24), date(2026, 10, 25), date(2026, 10, 26), None],
            ["2026-10-24", "2026-10-25", "2026-10-26", None],
            [
                datetime(2026, 10, 24, 9),
                datetime(2026, 10, 25, 23, 59),
                datetime(2026, 10, 26, 0, 1),
                None,
            ],
        ],
    )
    def test_before_keeps_rows_dated_on_or_before_and_undated(self, dates):
        data = pl.DataFrame({"key": ["a", "b", "c", "d"], "when": dates})

        before = on_or_before(data, "when", date(2026, 10, 25))

        assert before["key"].to_list() == ["a", "b", "d"]

    def test_in_period_is_the_rows_dated_after(self):
        data = pl.DataFrame(
            {"key": ["a", "b", "c"], "when": ["2026-10-25", "2026-10-26", None]}
        )

        in_period = data.filter(dated_after(data, "when", date(2026, 10, 25)))

        assert in_period["key"].to_list() == ["b"]

    def test_latest_date(self):
        data = pl.DataFrame(
            {"when": [datetime(2026, 10, 20, 8), None, datetime(2026, 10, 22, 7)]}
        )

        assert latest_date(data, "when") == date(2026, 10, 22)

    def test_latest_date_without_dates_is_none(self):
        data = pl.DataFrame({"when": [None, None]}, schema={"when": pl.Date})

        assert latest_date(data, "when") is None
        assert latest_date(data, "other") is None
