"""Each check's change over the comparison period, on fixed dated data.

The deltas are reached through the catalogue entries Summary uses. The check
"before" is the check on the submissions dated on or before the period start
(25 Oct 2026 here); resolutions count when logged after it and still in
effect.
"""

import json
from dataclasses import replace
from datetime import date, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks.backchecks.attribution import (
    ATTRIBUTION_LOG_SCHEMA,
    save_attributions,
)
from datasure.checks.catalogue import get_check, summary_check_health
from datasure.checks.context import CheckContext, CheckData, PageConfig
from datasure.checks.headline import CheckDelta, CheckHeadline, DeltaKind
from datasure.checks.health_deltas import comparison_window
from datasure.checks.health_period import ComparisonPeriod, DeltaWindow, Weekday
from datasure.processing.correction_log import CORRECTION_LOG_SCHEMA
from datasure.utils.dataframe_utils import get_df_columns
from datasure.utils.duckdb_utils import duckdb_save_table

PROJECT_ID = "delta01"
PAGE = "hfcs"
AS_OF = date(2026, 10, 25)
WINDOW = DeltaWindow(as_of=AS_OF, survey_date="when")


@pytest.fixture(autouse=True)
def mock_database_functions():
    """Override the autouse fixture from conftest to use real DuckDB files."""


@pytest.fixture(autouse=True)
def cache_dir(tmp_path):
    """Point every DuckDB database at a temporary cache directory."""

    def fake_cache_path(*parts):
        path = tmp_path.joinpath(*map(str, parts))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    with patch("datasure.utils.duckdb_utils.get_cache_path", fake_cache_path):
        yield tmp_path


def _config(tmp_path: Path, **overrides) -> PageConfig:
    settings = tmp_path / "settings.json"
    if not settings.exists():
        settings.write_text("{}")
    values = {
        "page_number": 1,
        "page_name": "HFCs",
        "page_name_id": PAGE,
        "survey_data_name": "survey",
        "survey_key": "key",
        "survey_id": "hhid",
        "survey_date": "when",
        "enumerator": None,
        "team": None,
        "formversion": None,
        "duration": None,
        "survey_target": None,
        "backcheck_data_name": None,
        "backcheck_date": None,
        "backchecker": None,
        "backchecker_team": None,
        "backcheck_target_percent": None,
        "tracking_data_name": None,
        "setting_file": settings,
        "missing_setting_file": tmp_path / "missing.json",
    }
    return PageConfig(**{**values, **overrides})


def _ctx(config: PageConfig, data: pl.DataFrame, backcheck=None) -> CheckContext:
    return CheckContext(
        PROJECT_ID, config, CheckData(data, backcheck), get_df_columns(data)
    )


def _save_settings(setting_file: Path, check: str, values: dict) -> None:
    settings = json.loads(setting_file.read_text())
    settings.setdefault(check, {}).update(values)
    setting_file.write_text(json.dumps(settings))


def _delta(slug: str, ctx: CheckContext, window: DeltaWindow = WINDOW):
    """The check's delta from its headline, as Summary computes it.

    A delta that reuses the headline's basis must equal the delta computed
    without it, so this checks both.
    """
    entry = get_check(slug)
    headline = entry.headline(ctx)
    delta = entry.delta(ctx, headline, window)
    if headline is not None and headline.basis is not None:
        assert entry.delta(ctx, replace(headline, basis=None), window) == delta
    return delta


# k4 is dated in the period; k5 has no date, so it is never new.
SURVEY = pl.DataFrame(
    {
        "key": ["k1", "k2", "k3", "k4", "k5"],
        "hhid": ["h1", "h2", "h3", "h3", "h4"],
        "when": ["2026-10-24", "2026-10-24", "2026-10-25", "2026-10-26", None],
    }
)


class TestProgressDelta:
    def test_new_submissions_are_the_ones_dated_in_the_period(self, tmp_path):
        ctx = _ctx(_config(tmp_path), SURVEY)

        assert _delta("progress", ctx) == CheckDelta(
            outstanding=1, kind=DeltaKind.SUBMISSIONS
        )

    def test_no_delta_without_a_date_column(self, tmp_path):
        ctx = _ctx(_config(tmp_path, survey_date=None), SURVEY)

        assert _delta("progress", ctx, DeltaWindow(as_of=AS_OF)) is None

    def test_no_delta_when_the_date_column_is_not_in_the_data(self, tmp_path):
        ctx = _ctx(_config(tmp_path), SURVEY.drop("when"))

        assert _delta("progress", ctx) is None

    def test_no_delta_when_the_earlier_check_has_no_headline(self, tmp_path):
        ctx = _ctx(_config(tmp_path), SURVEY)
        earlier = "datasure.checks.health_deltas.progress_headline"

        with patch(earlier, return_value=None):
            assert _delta("progress", ctx) is None


class TestMissingDelta:
    def test_change_in_percentage_points(self, tmp_path):
        # Before k4, x was never answered: 1 of 4 columns all missing.
        data = SURVEY.with_columns(pl.Series("x", [None, None, None, 5, None]))
        ctx = _ctx(_config(tmp_path), data)

        assert _delta("missing", ctx) == CheckDelta(
            outstanding=-25.0, kind=DeltaKind.POINTS
        )

    def test_no_delta_without_submissions_before_the_period(self, tmp_path):
        data = SURVEY.filter(pl.col("key") == "k4")
        ctx = _ctx(_config(tmp_path), data)

        assert _delta("missing", ctx) is None

    def test_no_delta_when_the_earlier_check_has_no_number(self, tmp_path):
        ctx = _ctx(_config(tmp_path), SURVEY)
        earlier = "datasure.checks.health_deltas.missing_headline"

        with patch(earlier, return_value=CheckHeadline("—")):
            assert _delta("missing", ctx) is None
        with patch(earlier, return_value=None):
            assert _delta("missing", ctx) is None


def _save_correction_log(entries: list[dict]) -> None:
    """Save the survey's correction log; an entry missing from it was undone."""
    log = pl.DataFrame(
        [{"status": "Successful", **entry} for entry in entries],
        schema=CORRECTION_LOG_SCHEMA,
    )
    duckdb_save_table(PROJECT_ID, log, "corr_log_survey", "logs")


class TestDuplicatesDelta:
    # Before corrections h1 and h2 were duplicated as well: k6 and k7 were
    # removed.
    UNCORRECTED = pl.concat(
        [
            SURVEY,
            pl.DataFrame(
                {"key": ["k6", "k7"], "hhid": ["h1", "h2"], "when": [None, None]},
                schema=SURVEY.schema,
            ),
        ]
    )

    def _ctx(self, tmp_path, data=SURVEY):
        duckdb_save_table(PROJECT_ID, self.UNCORRECTED, "survey", "prep")
        return _ctx(_config(tmp_path), data)

    @staticmethod
    def _removed(key: str, hhid: str, when: datetime) -> dict:
        return {"date": when, "KEY": key, "ID": hhid, "action": "remove row"}

    def test_new_duplicates_and_resolutions_logged_in_the_period(self, tmp_path):
        ctx = self._ctx(tmp_path)
        _save_correction_log(
            [
                self._removed("k6", "h1", datetime(2026, 10, 26, 9)),
                self._removed("k7", "h2", datetime(2026, 10, 20, 9)),
            ]
        )

        # h3 is duplicated by k4, dated in the period; h1 was resolved in it.
        assert _delta("duplicates", ctx) == CheckDelta(outstanding=1, resolved=1)

    def test_new_duplicates_are_ids_on_submissions_dated_in_the_period(self, tmp_path):
        # h3 was already duplicated by k3 and k8 before the period, and k4
        # joins it in the period, so it is new although the count did not
        # change. h5 is duplicated only by submissions before the period.
        before = pl.DataFrame(
            {
                "key": ["k8", "k9", "k10"],
                "hhid": ["h3", "h5", "h5"],
                "when": ["2026-10-24", "2026-10-20", "2026-10-21"],
            }
        )
        ctx = self._ctx(tmp_path, pl.concat([SURVEY, before]))
        _save_correction_log([])

        assert _delta("duplicates", ctx).outstanding == 1

    def test_an_unrelated_entry_in_the_period_does_not_resolve_an_id(self, tmp_path):
        # h1 and h2 were resolved before the period; k2, which holds h2, then
        # had another column corrected.
        ctx = self._ctx(tmp_path)
        _save_correction_log(
            [
                self._removed("k6", "h1", datetime(2026, 10, 20, 9)),
                self._removed("k7", "h2", datetime(2026, 10, 20, 9)),
                {
                    "date": datetime(2026, 10, 26, 9),
                    "KEY": "k2",
                    "ID": "h2",
                    "action": "modify value",
                    "column": "when",
                    "current_value": "2026-10-23",
                    "new_value": "2026-10-24",
                },
            ]
        )

        assert _delta("duplicates", ctx).resolved == 0

    def test_changing_the_id_resolves_it_when_logged_in_the_period(self, tmp_path):
        ctx = self._ctx(tmp_path)
        _save_correction_log(
            [
                self._removed("k6", "h1", datetime(2026, 10, 20, 9)),
                {
                    "date": datetime(2026, 10, 26, 9),
                    "KEY": "k7",
                    "ID": "h2",
                    "action": "modify value",
                    "column": "hhid",
                    "current_value": "h2",
                    "new_value": "h9",
                },
            ]
        )

        assert _delta("duplicates", ctx).resolved == 1

    def test_an_undone_correction_drops_out_of_resolved(self, tmp_path):
        # Undoing k6's removal deletes its log entry and brings k6 back.
        data = pl.concat([SURVEY, self.UNCORRECTED.filter(pl.col("key") == "k6")])
        ctx = self._ctx(tmp_path, data)
        _save_correction_log([self._removed("k7", "h2", datetime(2026, 10, 20, 9))])

        assert _delta("duplicates", ctx) == CheckDelta(outstanding=1, resolved=0)


class TestOutliersDelta:
    # k4's 100 is an IQR outlier and above the soft maximum; k4 is dated in
    # the period.
    DATA = pl.DataFrame(
        {
            "key": ["k1", "k2", "k3", "k4", "k5"],
            "hhid": ["h1", "h2", "h3", "h4", "h5"],
            "income": [1.0, 2.0, 3.0, 100.0, 5.0],
            "when": ["2026-10-20"] * 3 + ["2026-10-26", "2026-10-21"],
        }
    )
    COLUMNS = pl.DataFrame(
        {
            "search_type": ["exact"],
            "pattern": [None],
            "column_name": [["income"]],
            "grouped_columns": [False],
            "locked": [False],
            "outlier_enabled": [True],
            "outlier_method": ["Interquartile Range (IQR)"],
            "outlier_multiplier": [1.5],
            "outlier_threshold": [3],
            "hard_min": [None],
            "soft_min": [0.0],
            "soft_max": [50.0],
            "hard_max": [None],
        }
    )

    def _delta(self, tmp_path, log_entries: list[dict], data=None):
        """The delta with the correction log `log_entries`, on the real processor.

        `data` is the corrected data, by default the uncorrected `DATA`.
        """
        data = self.DATA if data is None else data
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"outliers_{PAGE}", "logs")
        log = pl.DataFrame(
            [{"status": "Successful", **entry} for entry in log_entries],
            schema=CORRECTION_LOG_SCHEMA,
        )
        processor = "datasure.processing.corrections.CorrectionProcessor"
        with (
            patch(f"{processor}.get_correction_log", lambda _self, _alias: log),
            patch(f"{processor}.get_corrected_data", lambda _self, _a: data),
            patch(f"{processor}.get_uncorrected_data", lambda _self, _a: self.DATA),
        ):
            return _delta("outliers", _ctx(_config(tmp_path), data))

    @staticmethod
    def _accepted(when: datetime, value: str = "100.0") -> list[dict]:
        """Accept k4's outlier and its constraint violation at `when`."""
        return [
            {
                "date": when,
                "KEY": "k4",
                "action": "accept",
                "column": "income",
                "current_value": value,
                "reason": "checked",
                "check_type": check_type,
            }
            for check_type in ("outliers", "constraints")
        ]

    def test_new_flags_are_those_on_submissions_dated_in_the_period(self, tmp_path):
        assert self._delta(tmp_path, []) == CheckDelta(outstanding=2, resolved=0)

    def test_acceptances_logged_in_the_period_are_resolved(self, tmp_path):
        delta = self._delta(tmp_path, self._accepted(datetime(2026, 10, 26, 8)))

        assert delta == CheckDelta(outstanding=0, resolved=2)

    def test_acceptances_logged_before_the_period_are_not(self, tmp_path):
        delta = self._delta(tmp_path, self._accepted(datetime(2026, 10, 25, 23)))

        assert delta == CheckDelta(outstanding=0, resolved=0)

    def test_an_acceptance_that_no_longer_applies_drops_out(self, tmp_path):
        # k4 was accepted at 90, but the data now holds 100.
        delta = self._delta(
            tmp_path, self._accepted(datetime(2026, 10, 26, 8), value="90")
        )

        assert delta == CheckDelta(outstanding=2, resolved=0)

    def test_a_correction_logged_in_the_period_is_resolved_until_undone(self, tmp_path):
        corrected = self.DATA.with_columns(
            pl.when(pl.col("key") == "k4")
            .then(4.0)
            .otherwise(pl.col("income"))
            .alias("income")
        )
        correction = {
            "date": datetime(2026, 10, 26, 8),
            "KEY": "k4",
            "action": "modify value",
            "column": "income",
            "current_value": "100.0",
            "new_value": "4.0",
            "reason": "typo",
            "source": "outliers",
        }

        # k4's value was flagged by both checks; the corrected cell counts once.
        assert self._delta(tmp_path, [correction], corrected) == CheckDelta(
            outstanding=0, resolved=1
        )
        # Undoing it deletes the entry and puts the value back.
        assert self._delta(tmp_path, []) == CheckDelta(outstanding=2, resolved=0)

    def test_a_key_column_not_in_the_data_is_a_settings_error(self, tmp_path):
        # As for the headline: the row shows why, not a missing column error.
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"outliers_{PAGE}", "logs")
        ctx = _ctx(_config(tmp_path), self.DATA.rename({"key": "id"}))

        with pytest.raises(ValueError, match="Outliers settings no longer fit"):
            get_check("outliers").delta(ctx, CheckHeadline("2"), WINDOW)


class TestGPSDelta:
    # Ten points close together and two far away: with the default LOF
    # settings k09 and k10 are the outliers. k09 is dated in the period.
    DATA = pl.DataFrame(
        {
            "key": [f"k{i:02d}" for i in range(1, 13)],
            "hhid": [f"h{i:02d}" for i in range(1, 13)],
            "lat": [6.60 + 0.001 * (i % 4) for i in range(10)] + [7.5, 5.5],
            "lon": [-0.18 + 0.001 * (i // 4) for i in range(10)] + [-1.5, 1.2],
            "when": ["2026-10-20"] * 8 + ["2026-10-26", "2026-10-24"] + [None] * 2,
        }
    )
    GPS_COLUMNS = pl.DataFrame(
        {
            "alias": ["home"],
            "format_type": ["Separate Columns"],
            "delimiter": [None],
            "gps_column": [None],
            "latitude_column": ["lat"],
            "longitude_column": ["lon"],
            "altitude_column": [None],
            "accuracy_column": [None],
        },
        schema_overrides={
            "delimiter": pl.String,
            "gps_column": pl.String,
            "altitude_column": pl.String,
            "accuracy_column": pl.String,
        },
    )

    @pytest.fixture(autouse=True)
    def page_settings(self, cache_dir):
        """The GPS check reads its view state from the page settings file."""

        def fake_cache_path(*parts):
            path = cache_dir.joinpath(*map(str, parts))
            path.parent.mkdir(parents=True, exist_ok=True)
            return path

        with patch("datasure.utils.settings_utils.get_cache_path", fake_cache_path):
            yield

    def _acceptance(self, key: str, when: datetime) -> pl.DataFrame:
        row = self.DATA.filter(pl.col("key") == key).row(0, named=True)
        return pl.DataFrame(
            {
                "date": [when],
                "KEY": [key],
                "action": ["accept"],
                "column": [None],
                "current_value": [json.dumps({"lat": row["lat"], "lon": row["lon"]})],
                "reason": ["market"],
            },
            schema_overrides={"column": pl.String},
        )

    def _delta(self, tmp_path, acceptances: pl.DataFrame | None = None):
        duckdb_save_table(PROJECT_ID, self.GPS_COLUMNS, f"gps_columns_{PAGE}", "logs")
        processor = MagicMock()
        processor.get_active_acceptances.return_value = (
            pl.DataFrame() if acceptances is None else acceptances
        )
        processor.get_correction_log.return_value = pl.DataFrame()
        processor.get_active_corrections.return_value = pl.DataFrame()
        with patch(
            "datasure.checks.gpschecks.report_ui.CorrectionProcessor",
            return_value=processor,
        ):
            return _delta("gps", _ctx(_config(tmp_path), self.DATA))

    def test_new_outliers_are_those_on_submissions_dated_in_the_period(self, tmp_path):
        assert self._delta(tmp_path) == CheckDelta(outstanding=1, resolved=0)

    def test_acceptances_logged_in_the_period_are_resolved(self, tmp_path):
        delta = self._delta(
            tmp_path, self._acceptance("k09", datetime(2026, 10, 26, 8))
        )

        assert delta == CheckDelta(outstanding=0, resolved=1)

    def test_acceptances_logged_before_the_period_are_not(self, tmp_path):
        delta = self._delta(
            tmp_path, self._acceptance("k10", datetime(2026, 10, 25, 23))
        )

        assert delta == CheckDelta(outstanding=1, resolved=0)

    def _corrected_delta(self, tmp_path, log_entries: list[dict]):
        """The delta on the real processor, the logged KEYs removed."""
        duckdb_save_table(PROJECT_ID, self.GPS_COLUMNS, f"gps_columns_{PAGE}", "logs")
        log = pl.DataFrame(
            [{"status": "Successful", **entry} for entry in log_entries],
            schema=CORRECTION_LOG_SCHEMA,
        )
        removed = sorted(entry["KEY"] for entry in log_entries)
        data = self.DATA.filter(~pl.col("key").is_in(removed))
        processor = "datasure.processing.corrections.CorrectionProcessor"
        with (
            patch(f"{processor}.get_correction_log", lambda _self, _alias: log),
            patch(f"{processor}.get_corrected_data", lambda _self, _a: data),
        ):
            return _delta("gps", _ctx(_config(tmp_path), data))

    def test_a_correction_logged_in_the_period_is_resolved_until_undone(self, tmp_path):
        removal = {
            "date": datetime(2026, 10, 26, 8),
            "KEY": "k09",
            "action": "remove row",
            "reason": "duplicate visit",
            "source": "gps",
        }

        assert self._corrected_delta(tmp_path, [removal]).resolved == 1
        # Undoing it deletes the entry and brings k09 back as an outlier.
        assert self._corrected_delta(tmp_path, []) == CheckDelta(
            outstanding=1, resolved=0
        )

    def test_no_delta_without_a_date_column(self, tmp_path):
        duckdb_save_table(PROJECT_ID, self.GPS_COLUMNS, f"gps_columns_{PAGE}", "logs")
        ctx = _ctx(_config(tmp_path, survey_date=None), self.DATA)

        assert _delta("gps", ctx, DeltaWindow(as_of=AS_OF)) is None


class TestBackchecksDelta:
    SURVEY = pl.DataFrame(
        {
            "key": ["k1", "k2", "k3"],
            "hhid": ["h1", "h2", "h3"],
            "age": [30, 31, 33],
            "when": ["2026-10-20"] * 3,
        }
    )
    # b2's age differs from k2's, and b2 was backchecked in the period.
    BACKCHECK = pl.DataFrame(
        {
            "key": ["b1", "b2", "b3"],
            "hhid": ["h1", "h2", "h3"],
            "age": [30, 99, 33],
            "bcdate": ["2026-10-24", "2026-10-26", "2026-10-24"],
        }
    )
    COLUMNS = pl.DataFrame(
        {
            "search_type": ["exact"],
            "pattern": ["age"],
            "column_name": [["age"]],
            "category": [1],
            "ok_range_type": [None],
            "ok_range_values": [None],
            "ttest": [False],
            "prtest": [False],
            "signrank": [False],
            "reliability": [False],
        },
        schema_overrides={
            "ok_range_type": pl.String,
            "ok_range_values": pl.List(pl.Float64),
        },
    )
    WINDOW = DeltaWindow(as_of=AS_OF, survey_date="when", backcheck_date="bcdate")

    def _delta(self, tmp_path, window=WINDOW):
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"backchecks_{PAGE}", "logs")
        config = _config(tmp_path, backcheck_date="bcdate", backcheck_target_percent=10)
        return _delta("backchecks", _ctx(config, self.SURVEY, self.BACKCHECK), window)

    @staticmethod
    def _attribute(source: str, when: datetime) -> None:
        save_attributions(
            PROJECT_ID,
            PAGE,
            pl.DataFrame(
                {
                    "survey_key": ["k2"],
                    "backcheck_key": ["b2"],
                    "column_name": ["age"],
                    "survey_value": ["31"],
                    "backcheck_value": ["99"],
                    "source": [source],
                    "note": ["Misheard"],
                    "user": ["tester"],
                    "date": [when],
                },
                schema=ATTRIBUTION_LOG_SCHEMA,
            ),
        )

    def test_new_mismatches_are_on_backchecks_dated_in_the_period(self, tmp_path):
        assert self._delta(tmp_path) == CheckDelta(outstanding=1, resolved=0)

    def test_attributions_logged_in_the_period_are_resolved(self, tmp_path):
        self._attribute("Respondent", datetime(2026, 10, 26, 9))

        assert self._delta(tmp_path) == CheckDelta(outstanding=0, resolved=1)

    def test_attributions_logged_before_the_period_are_not(self, tmp_path):
        self._attribute("Respondent", datetime(2026, 10, 25, 9))

        assert self._delta(tmp_path) == CheckDelta(outstanding=0, resolved=0)

    def test_the_latest_attribution_wins(self, tmp_path):
        self._attribute("Respondent", datetime(2026, 10, 26, 9))
        self._attribute("Unattributed", datetime(2026, 10, 26, 10))

        assert self._delta(tmp_path) == CheckDelta(outstanding=1, resolved=0)

    def test_no_delta_without_a_backcheck_date_column(self, tmp_path):
        # The survey date column does not stand in for the backcheck date.
        window = DeltaWindow(as_of=AS_OF, survey_date="when")

        assert self._delta(tmp_path, window) is None


class TestComparisonWindow:
    """Which date columns the rows compare by."""

    TODAY = date(2026, 10, 26)

    def _window(self, ctx):
        return comparison_window(ctx, ComparisonPeriod.DAY, self.TODAY)

    def test_the_period_start_comes_from_the_period(self, tmp_path):
        ctx = _ctx(_config(tmp_path), SURVEY)

        window = comparison_window(
            ctx, ComparisonPeriod.WEEK, self.TODAY, week_start=Weekday.MONDAY
        )

        assert window.as_of == date(2026, 10, 25)

    def test_the_page_survey_date_by_default(self, tmp_path):
        window = self._window(_ctx(_config(tmp_path), SURVEY))

        assert (window.survey_date, window.has_dates) == ("when", True)

    def test_summary_date_setting_wins(self, tmp_path):
        config = _config(tmp_path)
        _save_settings(config.setting_file, "summary", {"date": "other"})
        data = SURVEY.with_columns(pl.col("when").alias("other"))

        assert self._window(_ctx(config, data)).survey_date == "other"

    def test_no_date_column_at_all(self, tmp_path):
        window = self._window(_ctx(_config(tmp_path, survey_date=None), SURVEY))

        assert window.survey_date is None
        assert not window.has_dates

    def test_a_date_column_missing_from_the_data_is_no_date(self, tmp_path):
        window = self._window(_ctx(_config(tmp_path), SURVEY.drop("when")))

        assert not window.has_dates

    def test_backchecks_use_the_backcheck_date_setting(self, tmp_path):
        config = _config(tmp_path, backcheck_date="when")
        _save_settings(config.setting_file, "backchecks", {"backcheck_date": "bc"})
        backcheck = pl.DataFrame({"key": ["b1"], "hhid": ["h1"], "bc": ["2026-10-26"]})

        window = self._window(_ctx(config, SURVEY, backcheck))

        assert window.backcheck_date == "bc"

    def test_no_backcheck_date_without_backcheck_data(self, tmp_path):
        config = _config(tmp_path, backcheck_date="when")

        assert self._window(_ctx(config, SURVEY)).backcheck_date is None


class TestEnumeratorDelta:
    @staticmethod
    def _ctx(tmp_path, days_ago: list[int]) -> CheckContext:
        today = date.today()
        data = pl.DataFrame(
            {
                "key": [f"k{i}" for i in range(len(days_ago))],
                "hhid": [f"h{i}" for i in range(len(days_ago))],
                "enum": [f"e{i}" for i in range(len(days_ago))],
                "when": [today - timedelta(days=d) for d in days_ago],
            }
        )
        return _ctx(_config(tmp_path, enumerator="enum"), data)

    WINDOW = DeltaWindow(as_of=date.today() - timedelta(days=1), survey_date="when")

    def test_change_in_active_enumerators(self, tmp_path):
        # e0 is active now and as of yesterday, e1 in neither, and e2 only
        # submitted today.
        ctx = self._ctx(tmp_path, [3, 8, 0])

        assert _delta("enumerator", ctx, self.WINDOW) == CheckDelta(
            outstanding=1, kind=DeltaKind.ACTIVE
        )

    def test_an_enumerator_no_longer_active_lowers_the_count(self, tmp_path):
        # e0's last submission was 7 days ago: active as of yesterday only.
        ctx = self._ctx(tmp_path, [7])

        assert _delta("enumerator", ctx, self.WINDOW) == CheckDelta(
            outstanding=-1, kind=DeltaKind.ACTIVE
        )


class TestSummaryCheckHealth:
    """What Summary draws above and in the rows, with and without dates."""

    @staticmethod
    def _draw(ctx) -> dict[str, MagicMock]:
        drawn = {
            name: MagicMock()
            for name in (
                "render_health_header",
                "render_period_caption",
                "render_health_rows",
                "demo_callout",
            )
        }
        drawn["render_comparison_period"] = MagicMock(
            return_value=(ComparisonPeriod.SEVEN_DAYS, "Sunday")
        )
        catalogue = "datasure.checks.catalogue"
        with (
            patch.multiple(catalogue, **drawn, render_errors=lambda _key: {}),
            patch(f"{catalogue}.get_cache_path", lambda *parts: Path(*parts)),
        ):
            summary_check_health(ctx)
        return drawn

    @staticmethod
    def _rows(drawn) -> dict:
        rows = drawn["render_health_rows"].call_args.args[0]
        return {row.item.slug: row for row in rows}

    def test_with_a_date_column_rows_show_changes_since_the_period(self, tmp_path):
        drawn = self._draw(_ctx(_config(tmp_path), SURVEY))

        drawn["render_comparison_period"].assert_called_once()
        assert drawn["render_health_rows"].call_args.kwargs["since"] == "7 days ago"
        # The latest submission is 26 Oct, from Summary's date column.
        drawn["render_period_caption"].assert_called_once_with(
            "7 days ago", date(2026, 10, 26)
        )
        assert self._rows(drawn)["progress"].delta is not None

    def test_without_a_date_column_the_box_and_changes_are_hidden(self, tmp_path):
        drawn = self._draw(_ctx(_config(tmp_path, survey_date=None), SURVEY))

        drawn["render_comparison_period"].assert_not_called()
        drawn["render_period_caption"].assert_called_once_with(None, None)
        assert drawn["render_health_rows"].call_args.kwargs["since"] is None
        rows = self._rows(drawn)
        assert all(row.delta is None for row in rows.values())
        # Resolved totals still show.
        assert rows["duplicates"].headline.resolved is not None
