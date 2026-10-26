"""Each check's headline: the numbers Summary shows on its check health row.

A headline must match what the check itself reports, so these tests build the
same inputs the check uses (saved settings, logs tables) and assert the
number the check shows.
"""

import json
from datetime import date, datetime, timedelta
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks.backchecks.attribution import (
    ATTRIBUTION_LOG_SCHEMA,
    save_attributions,
)
from datasure.checks.backchecks.report_ui import backchecks_headline
from datasure.checks.duplicates import duplicates_headline
from datasure.checks.enumerator import report_ui as enumerator_ui
from datasure.checks.enumerator.report_ui import enumerator_headline
from datasure.checks.headline import CheckHeadline
from datasure.checks.missing import missing_headline
from datasure.checks.outliers.report_ui import outliers_headline
from datasure.checks.progress import progress_headline
from datasure.utils.dataframe_utils import get_df_columns
from datasure.utils.duckdb_utils import add_missing_code, duckdb_save_table

PROJECT_ID = "headline01"
PAGE = "hfcs"


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


@pytest.fixture
def setting_file(tmp_path):
    path = tmp_path / "settings.json"
    path.write_text("{}")
    return str(path)


def _save_settings(setting_file: str, check: str, values: dict) -> None:
    with open(setting_file, encoding="utf-8") as f:
        settings = json.load(f)
    settings.setdefault(check, {}).update(values)
    with open(setting_file, "w", encoding="utf-8") as f:
        json.dump(settings, f)


SURVEY = pl.DataFrame(
    {
        "key": ["k1", "k2", "k3", "k4", "k5"],
        "hhid": ["h1", "h2", "h2", "h3", "h3"],
        "age": [30, 31, 32, 33, 34],
    }
)


class TestProgressHeadline:
    CONFIG = {"survey_key": "key", "survey_id": "hhid"}  # noqa: RUF012

    def test_submissions_without_a_target(self, setting_file):
        assert progress_headline(SURVEY, setting_file, self.CONFIG) == (
            CheckHeadline("5", "submitted interviews", informational=True, count=5)
        )

    def test_submitted_out_of_the_target_from_the_page_config(self, setting_file):
        config = {**self.CONFIG, "survey_target": 20}

        assert progress_headline(SURVEY, setting_file, config) == (
            CheckHeadline("5 / 20", "25.00% of target", informational=True, count=5)
        )

    def test_a_target_saved_in_the_check_settings_wins(self, setting_file):
        _save_settings(setting_file, "progress", {"survey_target": 8})
        config = {**self.CONFIG, "survey_target": 20}

        headline = progress_headline(SURVEY, setting_file, config)

        assert (headline.value, headline.detail) == ("5 / 8", "62.50% of target")


class TestMissingHeadline:
    DATA = pl.DataFrame(
        {
            "a": [1, None, 3, 4],
            "b": [-99, 2, 3, 4],
            "c": [None, None, None, None],
            "d": [-99, -99, None, -99],
        }
    )

    def test_share_of_columns_all_missing(self):
        # Only c is all missing: 1 of 4 columns, the check's "% columns all
        # missing".
        assert missing_headline(PROJECT_ID, self.DATA) == CheckHeadline(
            "25.00%", "of columns all missing (1 of 4)", outstanding=25.0
        )

    def test_missing_codes_count_as_missing(self):
        add_missing_code(PROJECT_ID, "Don't know", "-99")

        # d is now all missing too.
        headline = missing_headline(PROJECT_ID, self.DATA)

        assert (headline.value, headline.detail) == (
            "50.00%",
            "of columns all missing (2 of 4)",
        )

    def test_no_columns_all_missing_is_not_outstanding(self):
        headline = missing_headline(PROJECT_ID, self.DATA.select("a", "b"))

        assert headline.outstanding == 0
        assert not headline.flagged


class TestDuplicatesHeadline:
    CONFIG = {"survey_key": "key", "survey_id": "hhid"}  # noqa: RUF012

    def test_counts_duplicate_ids(self, setting_file):
        # h2 and h3 are each on two records.
        headline = duplicates_headline(
            PROJECT_ID, SURVEY, setting_file, self.CONFIG, alias="survey"
        )

        assert headline == CheckHeadline(
            "2", "duplicate IDs", outstanding=2, resolved=0
        )

    def test_resolved_is_unknown_without_an_alias(self, setting_file):
        # Without the uncorrected data, resolved can't be computed: the row
        # shows "—", not 0.
        headline = duplicates_headline(PROJECT_ID, SURVEY, setting_file, self.CONFIG)

        assert (headline.outstanding, headline.resolved) == (2, None)

    def test_resolved_ids_are_the_duplicates_corrections_removed(self, setting_file):
        # Before corrections h1 and h4 were also duplicated; the survey data
        # is the corrected data, as on the check, which shows "Resolved: 2".
        uncorrected = pl.concat(
            [
                SURVEY,
                pl.DataFrame(
                    {"key": ["k6", "k7"], "hhid": ["h1", "h4"], "age": [35, 36]}
                ),
                pl.DataFrame({"key": ["k8"], "hhid": ["h4"], "age": [37]}),
            ]
        )
        duckdb_save_table(PROJECT_ID, uncorrected, "survey", "prep")

        headline = duplicates_headline(
            PROJECT_ID, SURVEY, setting_file, self.CONFIG, alias="survey"
        )

        assert (headline.outstanding, headline.resolved) == (2, 2)

    def test_uses_the_saved_records_to_include_filter(self, setting_file):
        _save_settings(
            setting_file,
            "duplicates",
            {
                "condition_col": "age",
                "condition_type": "Value is greater than",
                "condition_value": 31,
            },
        )

        # Only k3 (h2), k4 (h3) and k5 (h3) are checked.
        headline = duplicates_headline(PROJECT_ID, SURVEY, setting_file, self.CONFIG)
        assert (headline.value, headline.detail) == ("1", "duplicate ID")

    def test_invalid_records_to_include_filter_raises(self, setting_file):
        # The check shows the filter error; the row must not show zero.
        _save_settings(
            setting_file,
            "duplicates",
            {
                "condition_col": "removed_col",
                "condition_type": "Value is greater than",
                "condition_value": 31,
            },
        )

        with pytest.raises(ValueError, match="Records to Include"):
            duplicates_headline(PROJECT_ID, SURVEY, setting_file, self.CONFIG)

    def test_uses_the_saved_survey_id(self, setting_file):
        _save_settings(setting_file, "duplicates", {"survey_id": "key"})

        headline = duplicates_headline(PROJECT_ID, SURVEY, setting_file, self.CONFIG)
        assert (headline.value, headline.outstanding) == ("0", 0)


class TestOutliersHeadline:
    CONFIG = {"survey_key": "key", "survey_id": "hhid"}  # noqa: RUF012
    DATA = pl.DataFrame(
        {
            "key": ["k1", "k2", "k3", "k4", "k5"],
            "hhid": ["h1", "h2", "h3", "h4", "h5"],
            "income": [1.0, 2.0, 3.0, 100.0, 5.0],
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

    def _headline(self, setting_file, alias=None):
        return outliers_headline(
            PROJECT_ID,
            PAGE,
            self.DATA,
            get_df_columns(self.DATA),
            setting_file,
            self.CONFIG,
            alias,
        )

    def test_totals_outliers_and_constraint_violations(self, setting_file):
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"outliers_{PAGE}", "logs")

        # 100 is an IQR outlier and above the soft maximum of 50.
        assert self._headline(setting_file) == CheckHeadline(
            "2",
            "1 outlier (20.0% of values), 1 constraint violation",
            outstanding=2,
            resolved=0,
        )

    def _reviewed_headline(
        self, setting_file, acceptances, corrections, uncorrected=None
    ):
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"outliers_{PAGE}", "logs")
        with patch(
            "datasure.checks.outliers.report_ui.CorrectionProcessor"
        ) as processor:
            processor.return_value.get_active_acceptances.return_value = acceptances
            processor.return_value.get_active_corrections.return_value = corrections
            processor.return_value.get_uncorrected_data.return_value = (
                self.DATA if uncorrected is None else uncorrected
            )
            return self._headline(setting_file, alias="survey")

    @staticmethod
    def _log(action: str, key: str) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "KEY": [key],
                "action": [action],
                "column": ["income"],
                "reason": ["checked"],
                "severity": [None],
            },
            schema_overrides={"severity": pl.String},
        )

    def test_accepted_flags_are_resolved_not_outstanding(self, setting_file):
        from datasure.processing.correction_log import empty_correction_log

        headline = self._reviewed_headline(
            setting_file, self._log("accept", "k4"), empty_correction_log()
        )

        # The outlier and the constraint violation on k4 were both accepted.
        assert headline == CheckHeadline(
            "0",
            "0 outliers (0.0% of values), 0 constraint violations",
            outstanding=0,
            resolved=2,
        )

    def test_a_corrected_flag_no_longer_flagged_is_resolved_once(self, setting_file):
        from datasure.processing.correction_log import empty_correction_log

        # k5's income was 500, an outlier and above the soft maximum, before
        # it was corrected to 5.
        uncorrected = self.DATA.with_columns(
            pl.when(pl.col("key") == "k5")
            .then(500.0)
            .otherwise(pl.col("income"))
            .alias("income")
        )
        headline = self._reviewed_headline(
            setting_file, empty_correction_log(), self._log("modify", "k5"), uncorrected
        )

        assert (headline.outstanding, headline.resolved) == (2, 1)

    def test_a_corrected_value_that_was_never_flagged_is_not_resolved(
        self, setting_file
    ):
        from datasure.processing.correction_log import empty_correction_log

        # k2's income was corrected, but no check ever flagged it.
        headline = self._reviewed_headline(
            setting_file, empty_correction_log(), self._log("modify", "k2")
        )

        assert (headline.outstanding, headline.resolved) == (2, 0)

    def test_a_corrected_value_still_flagged_stays_outstanding(self, setting_file):
        from datasure.processing.correction_log import empty_correction_log

        headline = self._reviewed_headline(
            setting_file, empty_correction_log(), self._log("modify", "k4")
        )

        assert (headline.outstanding, headline.resolved) == (2, 0)

    def test_none_without_outlier_columns(self, setting_file):
        assert self._headline(setting_file) is None

    def test_saved_settings_that_no_longer_fit_raise_with_the_reason(
        self, setting_file
    ):
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"outliers_{PAGE}", "logs")
        _save_settings(setting_file, "outliers", {"survey_key": ""})

        # Summary shows the reason on a red row instead of "No issues".
        with pytest.raises(ValueError, match="saved Outliers settings"):
            self._headline(setting_file)


class TestEnumeratorHeadline:
    CONFIG = {  # noqa: RUF012
        "survey_key": "key",
        "survey_id": "key",
        "enumerator": "enum",
        "survey_date": "date",
    }

    @staticmethod
    def _data(enumerators: list[str], days_ago: list[int]) -> pl.DataFrame:
        today = date.today()
        return pl.DataFrame(
            {
                "key": [f"k{i}" for i in range(len(enumerators))],
                "enum": enumerators,
                "date": [today - timedelta(days=d) for d in days_ago],
            }
        )

    def test_active_enumerators_in_the_past_7_days(self, setting_file):
        data = self._data(["e1", "e1", "e2", "e3"], [1, 20, 2, 30])

        assert enumerator_headline(PROJECT_ID, data, setting_file, self.CONFIG) == (
            CheckHeadline(
                "2 / 3", "active in the past 7 days", informational=True, count=2
            )
        )

    @staticmethod
    def _report_overview(data: pl.DataFrame, setting_file: str, config: dict):
        """Run the Enumerator report; return its overview metrics by label.

        Streamlit and the sections after the overview are mocked; the
        settings panel returns the page configuration as its settings.
        """
        metrics: dict[str, str] = {}

        def column(*_args, **_kwargs):
            col = MagicMock()
            col.metric.side_effect = lambda label, value, **_: metrics.update(
                {label: value}
            )
            return col

        st = MagicMock()
        st.columns.side_effect = lambda spec, **_: [
            column() for _ in range(spec if isinstance(spec, int) else len(spec))
        ]
        with patch.multiple(
            enumerator_ui,
            st=st,
            demo_callout=MagicMock(),
            enumerator_report_settings=MagicMock(
                return_value=enumerator_ui.EnumeratorSettings(**config)
            ),
            _render_enumerator_summary_table=MagicMock(),
            _render_enumerator_productivity=MagicMock(),
            _render_enumerator_statistics=MagicMock(),
            _render_enumerator_statistics_overtime=MagicMock(),
        ):
            enumerator_ui.enumerator_report(
                PROJECT_ID, data, setting_file, config, get_df_columns(data)
            )
        return metrics

    def test_matches_the_enumerator_report_overview(self, setting_file):
        data = self._data(["e1", "e1", "e2", "e3", "e4"], [1, 20, 2, 30, 3])

        headline = enumerator_headline(PROJECT_ID, data, setting_file, self.CONFIG)
        shown = self._report_overview(data, setting_file, self.CONFIG)

        active = shown[r"\# of Active enumerators (past 7 days)"]
        total = shown[r"\# of enumerators"]
        assert headline.value == f"{active} / {total}"


class TestBackchecksHeadline:
    CONFIG = {  # noqa: RUF012
        "survey_key": "key",
        "survey_id": "hhid",
        "survey_date": None,
        "backcheck_date": None,
        "enumerator": None,
        "backchecker": None,
        "backcheck_target_percent": 10,
        "survey_target": 0,
    }
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
    SURVEY = SURVEY.unique("hhid", keep="first", maintain_order=True)

    def _headline(self, setting_file):
        return backchecks_headline(
            PROJECT_ID, PAGE, self.SURVEY, self.BACKCHECK, setting_file, self.CONFIG
        )

    def test_unattributed_mismatches_with_the_total_error_rate(self, setting_file):
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"backchecks_{PAGE}", "logs")

        # h2's age differs (31 vs 99): 1 of 3 values compared, as the check's
        # "Error Rate (Total)" shows.
        assert self._headline(setting_file) == CheckHeadline(
            "1", "33.33% error rate", outstanding=1, resolved=0
        )

    def _attribute(self, survey_value: str) -> None:
        save_attributions(
            PROJECT_ID,
            PAGE,
            pl.DataFrame(
                {
                    "survey_key": ["k2"],
                    "backcheck_key": ["b2"],
                    "column_name": ["age"],
                    "survey_value": [survey_value],
                    "backcheck_value": ["99"],
                    "source": ["Respondent"],
                    "note": ["Misheard"],
                    "user": ["tester"],
                    "date": [datetime(2026, 10, 1)],
                },
                schema=ATTRIBUTION_LOG_SCHEMA,
            ),
        )

    def test_attributed_mismatches_are_resolved(self, setting_file):
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"backchecks_{PAGE}", "logs")
        self._attribute("31")

        headline = self._headline(setting_file)

        # The error rate still counts the mismatch, as on the check.
        assert headline == CheckHeadline(
            "0", "33.33% error rate", outstanding=0, resolved=1
        )

    def test_an_attribution_whose_values_changed_no_longer_applies(self, setting_file):
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"backchecks_{PAGE}", "logs")
        self._attribute("32")

        headline = self._headline(setting_file)

        assert (headline.outstanding, headline.resolved) == (1, 0)

    def test_none_without_backcheck_columns(self, setting_file):
        assert self._headline(setting_file) is None

    def test_none_when_no_values_were_compared(self, setting_file):
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"backchecks_{PAGE}", "logs")
        backcheck = self.BACKCHECK.with_columns(pl.lit(None, pl.Int64).alias("age"))

        headline = backchecks_headline(
            PROJECT_ID, PAGE, self.SURVEY, backcheck, setting_file, self.CONFIG
        )

        assert headline is None

    def test_saved_settings_that_no_longer_fit_raise_with_the_reason(
        self, setting_file
    ):
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"backchecks_{PAGE}", "logs")
        _save_settings(setting_file, "backchecks", {"no_differences_values": 5})

        # Summary shows the reason on a red row instead of "No issues".
        with pytest.raises(ValueError, match="saved Backchecks settings"):
            self._headline(setting_file)
