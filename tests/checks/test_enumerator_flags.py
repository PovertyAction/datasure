"""Other checks' outstanding issues by enumerator, for the Enumerator page.

Reached through `catalogue.enumerator_other_checks`, as the Enumerator page
reaches them, on real DuckDB files. Each check's numbers by enumerator must
add up to what the check itself counts.
"""

import json
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks import health
from datasure.checks.catalogue import (
    CHECK_CATALOGUE,
    enumerator_other_checks,
    get_check,
)
from datasure.checks.context import CheckContext, CheckData, PageConfig
from datasure.checks.enumerator.attention import CountRule, IssueCounts, LeftOut
from datasure.checks.headline import EnumeratorScope
from datasure.checks.id_duplicates import find_duplicate_groups
from datasure.processing.correction_log import CORRECTION_LOG_SCHEMA
from datasure.utils.dataframe_utils import get_df_columns
from datasure.utils.duckdb_utils import duckdb_save_table
from datasure.utils.navigation import CheckStatus, StatusResult

PROJECT_ID = "enumflags01"
PAGE = "hfcs"
ALL_TEAMS = EnumeratorScope("enum")
TEAM_1 = EnumeratorScope("enum", "team", "T1")
TEAM_2 = EnumeratorScope("enum", "team", "T2")


@pytest.fixture(autouse=True)
def mock_database_functions():
    """Override the autouse fixture from conftest to use real DuckDB files."""


@pytest.fixture(autouse=True)
def cache_dir(tmp_path):
    """Point every DuckDB database and settings file at a temporary directory."""

    def fake_cache_path(*parts):
        path = tmp_path.joinpath(*map(str, parts))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    with (
        patch("datasure.utils.duckdb_utils.get_cache_path", fake_cache_path),
        patch("datasure.utils.settings_utils.get_cache_path", fake_cache_path),
    ):
        health.clear_headline_cache()
        yield tmp_path
        health.clear_headline_cache()


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
        "survey_date": None,
        "enumerator": "enum",
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


def _by_check(
    ctx: CheckContext, scope: EnumeratorScope = ALL_TEAMS
) -> dict[str, IssueCounts]:
    other = enumerator_other_checks(ctx, scope)
    assert other.errors == ()
    return {issues.check: issues for issues in other.counts}


class TestDuplicates:
    # h3 is held by k3 (e1) and k4 (e2).
    SURVEY = pl.DataFrame(
        {
            "key": ["k1", "k2", "k3", "k4", "k5"],
            "hhid": ["h1", "h2", "h3", "h3", "h4"],
            "enum": ["e1", "e2", "e1", "e2", "e3"],
        }
    )

    def test_records_holding_a_duplicate_id_count_for_their_enumerator(self, tmp_path):
        duckdb_save_table(PROJECT_ID, self.SURVEY, "survey", "prep")

        issues = _by_check(_ctx(_config(tmp_path), self.SURVEY))["Duplicates"]

        assert issues.counts == {"e1": 1, "e2": 1}
        assert issues.rule is CountRule.ANY

    def test_records_add_up_to_the_checks_records_involved(self, tmp_path):
        # h3 is held by three records, one of them with no enumerator.
        survey = pl.DataFrame(
            {
                "key": ["k1", "k2", "k3", "k4", "k5", "k6"],
                "hhid": ["h1", "h2", "h3", "h3", "h3", "h4"],
                "enum": ["e1", "e2", "e1", "e2", None, "e3"],
            }
        )
        duckdb_save_table(PROJECT_ID, survey, "survey", "prep")
        ctx = _ctx(_config(tmp_path), survey)

        headline = get_check("duplicates").headline(ctx)
        issues = _by_check(ctx)["Duplicates"]

        # The headline counts IDs; the list counts the records holding them,
        # which the Duplicates tab shows as "Records involved".
        records_involved = int(
            find_duplicate_groups(survey, "hhid", None, None)["n_records"].sum()
        )
        assert headline.outstanding == 1
        assert issues.counts == {"e1": 1, "e2": 1}
        assert issues.unattributed == 1
        assert sum(issues.counts.values()) + issues.unattributed == records_involved

    def test_a_chosen_team_counts_only_its_records(self, tmp_path):
        # h1 is held by k1 (e1, T1) and k2 (e1, T2); h2 by k3 and k4 in T1.
        survey = pl.DataFrame(
            {
                "key": ["k1", "k2", "k3", "k4", "k5"],
                "hhid": ["h1", "h1", "h2", "h2", "h3"],
                "enum": ["e1", "e1", "e2", "e3", "e1"],
                "team": ["T1", "T2", "T1", "T1", "T1"],
            }
        )
        duckdb_save_table(PROJECT_ID, survey, "survey", "prep")
        ctx = _ctx(_config(tmp_path, team="team"), survey)

        everyone = _by_check(ctx)["Duplicates"]
        team_1 = _by_check(ctx, TEAM_1)["Duplicates"]

        assert everyone.counts == {"e1": 2, "e2": 1, "e3": 1}
        # k2 is in T2, but h1 is still a duplicate, so k1 still counts.
        assert team_1.counts == {"e1": 1, "e2": 1, "e3": 1}

    def test_a_check_that_is_not_set_up_is_left_out(self, tmp_path):
        ctx = _ctx(_config(tmp_path, survey_id=None), self.SURVEY)

        assert "Duplicates" not in _by_check(ctx)

    def test_a_check_whose_numbers_fail_is_named_with_the_reason(self, tmp_path):
        duckdb_save_table(PROJECT_ID, self.SURVEY, "survey", "prep")
        ctx = _ctx(_config(tmp_path), self.SURVEY)

        with patch(
            "datasure.checks.enumerator_flags.duplicate_records_by_enumerator",
            side_effect=ValueError("bad filter"),
        ):
            other = enumerator_other_checks(ctx, ALL_TEAMS)

        assert other.errors == (
            LeftOut(
                "Duplicates",
                "ValueError: bad filter",
                "Open Duplicates to review its settings.",
            ),
        )

    def test_a_check_whose_status_fails_is_named_with_the_reason(self, tmp_path):
        ctx = _ctx(_config(tmp_path), self.SURVEY)

        with patch(
            "datasure.checks.catalogue.guarded_status",
            return_value=StatusResult(CheckStatus.ERROR, "OSError: locked"),
        ):
            other = enumerator_other_checks(ctx, ALL_TEAMS)

        assert [item.check for item in other.errors] == [
            entry.label for entry in CHECK_CATALOGUE if entry.by_enumerator is not None
        ]
        assert other.errors[0].reason == "OSError: locked"
        assert other.counts == ()


class TestOutliers:
    # k4's 100 is an IQR outlier and above the soft maximum.
    DATA = pl.DataFrame(
        {
            "key": ["k1", "k2", "k3", "k4", "k5"],
            "hhid": ["h1", "h2", "h3", "h4", "h5"],
            "income": [1.0, 2.0, 3.0, 100.0, 5.0],
            "enum": ["e1", "e1", "e2", "e2", "e1"],
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

    def _by_check(
        self, tmp_path, log_entries: list[dict], scope: EnumeratorScope = ALL_TEAMS
    ):
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"outliers_{PAGE}", "logs")
        log = pl.DataFrame(
            [{"status": "Successful", **entry} for entry in log_entries],
            schema=CORRECTION_LOG_SCHEMA,
        )
        processor = "datasure.processing.corrections.CorrectionProcessor"
        with (
            patch(f"{processor}.get_correction_log", lambda _self, _alias: log),
            patch(f"{processor}.get_corrected_data", lambda _self, _a: self.DATA),
            patch(f"{processor}.get_uncorrected_data", lambda _self, _a: self.DATA),
        ):
            return _by_check(_ctx(_config(tmp_path), self.DATA), scope)

    def test_flags_count_for_the_enumerator_of_their_submission(self, tmp_path):
        found = self._by_check(tmp_path, [])

        assert found["Outliers"].counts == {"e2": 1}
        assert found["Constraints"].counts == {"e2": 1}
        assert found["Outliers"].rule is CountRule.RELATIVE

    def test_flags_with_no_enumerator_are_unattributed(self, tmp_path):
        self.DATA = self.DATA.with_columns(
            pl.when(pl.col("key") == "k4")
            .then(None)
            .otherwise(pl.col("enum"))
            .alias("enum")
        )

        found = self._by_check(tmp_path, [])

        for check in ("Outliers", "Constraints"):
            assert found[check].counts == {}
            assert found[check].unattributed == 1

    def test_a_chosen_team_counts_only_its_flags(self, tmp_path):
        # k4, the flagged submission, is the only one in T2.
        self.DATA = self.DATA.with_columns(
            team=pl.when(pl.col("key") == "k4")
            .then(pl.lit("T2"))
            .otherwise(pl.lit("T1"))
        )

        team_1 = self._by_check(tmp_path, [], TEAM_1)
        team_2 = self._by_check(tmp_path, [], TEAM_2)

        for check in ("Outliers", "Constraints"):
            assert (team_1[check].counts, team_1[check].unattributed) == ({}, 0)
            assert (team_2[check].counts, team_2[check].unattributed) == ({"e2": 1}, 0)

    def test_accepted_flags_no_longer_count(self, tmp_path):
        accepted = [
            {
                "date": datetime(2026, 10, 26, 8),
                "KEY": "k4",
                "action": "accept",
                "column": "income",
                "current_value": "100.0",
                "reason": "checked",
                "check_type": check_type,
            }
            for check_type in ("outliers", "constraints")
        ]

        found = self._by_check(tmp_path, accepted)

        assert found["Outliers"].counts == {}
        assert found["Constraints"].counts == {}


class TestGPS:
    # Ten points close together and two far away: with the default LOF
    # settings k09 and k10 are the outliers.
    DATA = pl.DataFrame(
        {
            "key": [f"k{i:02d}" for i in range(1, 13)],
            "hhid": [f"h{i:02d}" for i in range(1, 13)],
            "lat": [6.60 + 0.001 * (i % 4) for i in range(10)] + [7.5, 5.5],
            "lon": [-0.18 + 0.001 * (i // 4) for i in range(10)] + [-1.5, 1.2],
            "enum": ["e1"] * 8 + ["e2", "e3", "e1", "e1"],
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

    def test_unreviewed_outliers_count_for_their_enumerator(self, tmp_path):
        duckdb_save_table(PROJECT_ID, self.GPS_COLUMNS, f"gps_columns_{PAGE}", "logs")
        processor = MagicMock()
        processor.get_active_acceptances.return_value = pl.DataFrame()
        processor.get_correction_log.return_value = pl.DataFrame()
        processor.get_active_corrections.return_value = pl.DataFrame()
        ctx = _ctx(_config(tmp_path), self.DATA)

        with patch(
            "datasure.checks.gpschecks.report_ui.CorrectionProcessor",
            return_value=processor,
        ):
            headline = get_check("gps").headline(ctx)
            issues = _by_check(ctx)["GPS"]

        assert issues.counts == {"e2": 1, "e3": 1}
        assert issues.unattributed == 0
        assert sum(issues.counts.values()) == headline.outstanding

    def test_points_with_no_enumerator_are_unattributed(self, tmp_path):
        duckdb_save_table(PROJECT_ID, self.GPS_COLUMNS, f"gps_columns_{PAGE}", "logs")
        processor = MagicMock()
        processor.get_active_acceptances.return_value = pl.DataFrame()
        processor.get_correction_log.return_value = pl.DataFrame()
        processor.get_active_corrections.return_value = pl.DataFrame()
        data = self.DATA.with_columns(
            pl.when(pl.col("key") == "k10")
            .then(None)
            .otherwise(pl.col("enum"))
            .alias("enum")
        )
        ctx = _ctx(_config(tmp_path), data)

        with patch(
            "datasure.checks.gpschecks.report_ui.CorrectionProcessor",
            return_value=processor,
        ):
            headline = get_check("gps").headline(ctx)
            issues = _by_check(ctx)["GPS"]

        assert issues.counts == {"e2": 1}
        assert issues.unattributed == 1
        assert sum(issues.counts.values()) + issues.unattributed == (
            headline.outstanding
        )

    def test_a_chosen_team_counts_only_its_points(self, tmp_path):
        duckdb_save_table(PROJECT_ID, self.GPS_COLUMNS, f"gps_columns_{PAGE}", "logs")
        processor = MagicMock()
        processor.get_active_acceptances.return_value = pl.DataFrame()
        processor.get_correction_log.return_value = pl.DataFrame()
        processor.get_active_corrections.return_value = pl.DataFrame()
        # k10 (e3) is the only submission in T2.
        data = self.DATA.with_columns(
            team=pl.when(pl.col("key") == "k10")
            .then(pl.lit("T2"))
            .otherwise(pl.lit("T1"))
        )
        ctx = _ctx(_config(tmp_path, team="team"), data)

        with patch(
            "datasure.checks.gpschecks.report_ui.CorrectionProcessor",
            return_value=processor,
        ):
            team_1 = _by_check(ctx, TEAM_1)["GPS"]
            team_2 = _by_check(ctx, TEAM_2)["GPS"]

        assert (team_1.counts, team_1.unattributed) == ({"e2": 1}, 0)
        assert (team_2.counts, team_2.unattributed) == ({"e3": 1}, 0)


class TestBackchecks:
    SURVEY = pl.DataFrame(
        {
            "key": ["k1", "k2", "k3"],
            "hhid": ["h1", "h2", "h3"],
            "age": [30, 31, 33],
            "enum": ["e1", "e2", "e2"],
        }
    )
    # b2's age differs from k2's.
    BACKCHECK = pl.DataFrame(
        {"key": ["b1", "b2", "b3"], "hhid": ["h1", "h2", "h3"], "age": [30, 99, 33]}
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

    def _ctx(self, tmp_path):
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"backchecks_{PAGE}", "logs")
        config = _config(
            tmp_path, backcheck_data_name="bc", backcheck_target_percent=10
        )
        return _ctx(config, self.SURVEY, self.BACKCHECK)

    def test_mismatches_count_against_values_compared_by_enumerator(self, tmp_path):
        issues = _by_check(self._ctx(tmp_path))["Backchecks"]

        assert issues.counts == {"e1": 0, "e2": 1}
        assert issues.denominators == {"e1": 1, "e2": 2}
        assert issues.per == "value compared"
        assert issues.unattributed == 0

    def test_mismatches_with_no_enumerator_are_unattributed(self, tmp_path):
        self.SURVEY = self.SURVEY.with_columns(
            pl.when(pl.col("key") == "k2")
            .then(None)
            .otherwise(pl.col("enum"))
            .alias("enum")
        )

        issues = _by_check(self._ctx(tmp_path))["Backchecks"]

        assert issues.counts == {"e1": 0, "e2": 0}
        assert issues.unattributed == 1

    def test_a_chosen_team_counts_only_its_comparisons(self, tmp_path):
        # k2, with the mismatch, is the only submission in T2.
        self.SURVEY = self.SURVEY.with_columns(
            team=pl.when(pl.col("key") == "k2")
            .then(pl.lit("T2"))
            .otherwise(pl.lit("T1"))
        )

        issues = _by_check(self._ctx(tmp_path), TEAM_1)["Backchecks"]

        assert issues.counts == {"e1": 0, "e2": 0}
        assert issues.denominators == {"e1": 1, "e2": 1}
        assert issues.unattributed == 0

    def test_no_backcheck_data_gives_nothing(self, tmp_path):
        ctx = _ctx(_config(tmp_path), self.SURVEY)

        assert "Backchecks" not in _by_check(ctx)


def test_counts_are_cached_on_the_page(tmp_path):
    """Opening the page again computes nothing again."""
    data = TestDuplicates.SURVEY
    duckdb_save_table(PROJECT_ID, data, "survey", "prep")
    ctx = _ctx(_config(tmp_path), data)
    # The first call creates the logs database, which the page fingerprint
    # stamps; on a real project it already exists.
    enumerator_other_checks(ctx, ALL_TEAMS)
    enumerator_other_checks(ctx, ALL_TEAMS)
    with patch(
        "datasure.checks.enumerator_flags.duplicate_records_by_enumerator"
    ) as counted:
        enumerator_other_checks(ctx, ALL_TEAMS)

    counted.assert_not_called()


def test_cached_headline_shares_summarys_cache_and_keeps_the_basis(tmp_path):
    data = TestDuplicates.SURVEY
    duckdb_save_table(PROJECT_ID, data, "survey", "prep")
    ctx = _ctx(_config(tmp_path), data)
    headline = MagicMock(side_effect=get_check("duplicates").headline)

    first = health.cached_headline(ctx, "duplicates", headline)
    again = health.cached_headline(ctx, "duplicates", headline)

    assert headline.call_count == 1
    assert first.basis is not None
    assert again.basis is first.basis
    assert json.dumps(first.value) == json.dumps(again.value)
