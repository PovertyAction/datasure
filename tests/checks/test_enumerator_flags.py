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
from datasure.checks.catalogue import enumerator_other_checks, get_check
from datasure.checks.context import CheckContext, CheckData, PageConfig
from datasure.checks.enumerator.attention import CountRule, IssueCounts
from datasure.processing.correction_log import CORRECTION_LOG_SCHEMA
from datasure.utils.dataframe_utils import get_df_columns
from datasure.utils.duckdb_utils import duckdb_save_table

PROJECT_ID = "enumflags01"
PAGE = "hfcs"


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


def _by_check(ctx: CheckContext) -> dict[str, IssueCounts]:
    other = enumerator_other_checks(ctx, "enum")
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
            other = enumerator_other_checks(ctx, "enum")

        assert other.errors == (("Duplicates", "ValueError: bad filter"),)


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

    def _by_check(self, tmp_path, log_entries: list[dict]):
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
            return _by_check(_ctx(_config(tmp_path), self.DATA))

    def test_flags_count_for_the_enumerator_of_their_submission(self, tmp_path):
        found = self._by_check(tmp_path, [])

        assert found["Outliers"].counts == {"e2": 1}
        assert found["Constraints"].counts == {"e2": 1}
        assert found["Outliers"].rule is CountRule.RELATIVE

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
        assert sum(issues.counts.values()) == headline.outstanding


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
    enumerator_other_checks(ctx, "enum")
    enumerator_other_checks(ctx, "enum")
    with patch(
        "datasure.checks.enumerator_flags.duplicate_records_by_enumerator"
    ) as counted:
        enumerator_other_checks(ctx, "enum")

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
