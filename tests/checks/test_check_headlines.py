"""Each triage check's headline: the number Summary shows on its health card.

A headline must match what the check itself reports, so these tests build the
same inputs the check uses (saved settings, logs tables) and assert the
number the check shows.
"""

import json
from datetime import date, timedelta
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks.backchecks.report_ui import backchecks_headline
from datasure.checks.duplicates import duplicates_headline
from datasure.checks.enumerator import report_ui as enumerator_ui
from datasure.checks.enumerator.report_ui import enumerator_headline
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
            "5 submitted interviews"
        )

    def test_share_of_the_target_from_the_page_config(self, setting_file):
        config = {**self.CONFIG, "survey_target": 20}

        assert progress_headline(SURVEY, setting_file, config) == (
            "25.00% of target (5 of 20)"
        )

    def test_a_target_saved_in_the_check_settings_wins(self, setting_file):
        _save_settings(setting_file, "progress", {"survey_target": 8})
        config = {**self.CONFIG, "survey_target": 20}

        assert progress_headline(SURVEY, setting_file, config) == (
            "62.50% of target (5 of 8)"
        )


class TestMissingHeadline:
    DATA = pl.DataFrame({"a": [1, None, 3, 4], "b": [-99, 2, 3, 4]})

    def test_mean_share_of_missing_values(self):
        # a is 25% missing, b has none: 12.5% on average, as the check shows.
        assert missing_headline(PROJECT_ID, self.DATA) == "12.50% of values missing"

    def test_missing_codes_count_as_missing(self):
        add_missing_code(PROJECT_ID, "Don't know", "-99")

        assert missing_headline(PROJECT_ID, self.DATA) == "25.00% of values missing"


class TestDuplicatesHeadline:
    CONFIG = {"survey_key": "key", "survey_id": "hhid"}  # noqa: RUF012

    def test_counts_duplicate_ids(self, setting_file):
        # h2 and h3 are each on two records.
        assert duplicates_headline(SURVEY, setting_file, self.CONFIG) == (
            "2 duplicate IDs"
        )

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
        assert duplicates_headline(SURVEY, setting_file, self.CONFIG) == (
            "1 duplicate ID"
        )

    def test_invalid_records_to_include_filter_raises(self, setting_file):
        # The check shows the filter error; the card must not show zero.
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
            duplicates_headline(SURVEY, setting_file, self.CONFIG)

    def test_uses_the_saved_survey_id(self, setting_file):
        _save_settings(setting_file, "duplicates", {"survey_id": "key"})

        assert duplicates_headline(SURVEY, setting_file, self.CONFIG) == (
            "0 duplicate IDs"
        )


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
        assert (
            self._headline(setting_file)
            == "1 outlier (20.0% of values), 1 constraint violation"
        )

    def test_accepted_flags_are_left_out(self, setting_file):
        from datasure.processing.correction_log import empty_correction_log

        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"outliers_{PAGE}", "logs")
        acceptances = pl.DataFrame(
            {
                "KEY": ["k4"],
                "action": ["accept"],
                "column": ["income"],
                "reason": ["checked"],
                "severity": [None],
            },
            schema_overrides={"severity": pl.String},
        )
        with patch(
            "datasure.checks.outliers.report_ui.CorrectionProcessor"
        ) as processor:
            processor.return_value.get_active_acceptances.return_value = acceptances
            processor.return_value.get_active_corrections.return_value = (
                empty_correction_log()
            )
            headline = self._headline(setting_file, alias="survey")

        assert headline == "0 outliers (0.0% of values), 0 constraint violations"

    def test_none_without_outlier_columns(self, setting_file):
        assert self._headline(setting_file) is None


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
            "2 of 3 enumerators active in the past 7 days"
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
        assert headline == f"{active} of {total} enumerators active in the past 7 days"


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

    def test_total_error_rate(self, setting_file):
        duckdb_save_table(PROJECT_ID, self.COLUMNS, f"backchecks_{PAGE}", "logs")

        # h2's age differs (31 vs 99): 1 of 3 values compared.
        assert self._headline(setting_file) == "33.33% error rate"

    def test_none_without_backcheck_columns(self, setting_file):
        assert self._headline(setting_file) is None
