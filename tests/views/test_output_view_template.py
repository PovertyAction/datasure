"""Tests for loading check-page data in the output view template."""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks import catalogue
from datasure.checks.catalogue import CheckEntry
from datasure.utils.dataframe_utils import TableState
from datasure.utils.duckdb_utils import duckdb_save_table
from datasure.views import output_view_template as template

PROJECT_ID = "zero_row_project"
ALIAS = "survey"


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
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


def _rows(n: int) -> pl.DataFrame:
    return pl.DataFrame({"key": [f"k{i}" for i in range(n)], "age": list(range(n))})


def _save(df: pl.DataFrame, db_name: str) -> None:
    duckdb_save_table(PROJECT_ID, df, ALIAS, db_name)


class TestLoadDataWithFallback:
    """A table that exists is used even when it has no rows."""

    def test_zero_row_prep_table_does_not_fall_back_to_raw(self):
        _save(_rows(3), "raw")
        _save(_rows(0), "prep")

        data = template.load_data_with_fallback(PROJECT_ID, ALIAS)

        assert data.height == 0
        assert data.columns == ["key", "age"]

    def test_zero_row_corrected_table_does_not_fall_back(self):
        _save(_rows(3), "raw")
        _save(_rows(2), "prep")
        _save(_rows(0), "corrected")

        data = template.load_data_with_fallback(PROJECT_ID, ALIAS)

        assert data.height == 0
        assert data.columns == ["key", "age"]

    def test_missing_tables_fall_back_to_raw(self):
        _save(_rows(3), "raw")

        data = template.load_data_with_fallback(PROJECT_ID, ALIAS)

        assert data.height == 3

    def test_no_table_anywhere_returns_frame_without_columns(self):
        data = template.load_data_with_fallback(PROJECT_ID, ALIAS)

        assert data.width == 0


class TestStopIfNoSurveyData:
    """Check pages say there is no data instead of running checks."""

    def test_zero_row_data_stops_with_message(self):
        with patch.object(template, "st") as mock_st:
            mock_st.stop.side_effect = StopIteration
            with pytest.raises(StopIteration):
                template.stop_if_no_survey_data(_rows(0), ALIAS)

        message = mock_st.info.call_args.args[0]
        assert "no rows" in message
        assert "Prepare Data" in message

    def test_missing_data_stops_with_message(self):
        with patch.object(template, "st") as mock_st:
            mock_st.stop.side_effect = StopIteration
            with pytest.raises(StopIteration):
                template.stop_if_no_survey_data(pl.DataFrame(), ALIAS)

        message = mock_st.info.call_args.args[0]
        assert "Import Data" in message

    def test_data_with_rows_continues(self):
        with patch.object(template, "st") as mock_st:
            template.stop_if_no_survey_data(_rows(1), ALIAS)

        mock_st.stop.assert_not_called()


class TestLoadCheckData:
    """Zero-row backcheck data is told apart from no backcheck data."""

    def _config(self, backcheck_data_name):
        return SimpleNamespace(
            survey_data_name=ALIAS, backcheck_data_name=backcheck_data_name
        )

    def test_zero_row_backcheck_has_no_rows(self):
        _save(_rows(2), "raw")
        duckdb_save_table(PROJECT_ID, _rows(0), "backcheck", "prep")

        data = template.load_check_data(PROJECT_ID, self._config("backcheck"))

        assert data.backcheck_state is TableState.NO_ROWS
        assert data.backcheck_data_with_rows is None

    def test_unimported_backcheck_is_missing(self):
        _save(_rows(2), "raw")

        data = template.load_check_data(PROJECT_ID, self._config("backcheck"))

        assert data.backcheck_state is TableState.MISSING
        assert data.backcheck_data_with_rows is None

    def test_unconfigured_backcheck_is_missing(self):
        _save(_rows(2), "raw")

        data = template.load_check_data(PROJECT_ID, self._config(None))

        assert data.backcheck_data is None
        assert data.backcheck_state is TableState.MISSING

    def test_backcheck_with_rows_is_loaded(self):
        _save(_rows(2), "raw")
        duckdb_save_table(PROJECT_ID, _rows(1), "backcheck", "raw")

        data = template.load_check_data(PROJECT_ID, self._config("backcheck"))

        assert data.backcheck_state is TableState.HAS_ROWS
        assert data.backcheck_data_with_rows.height == 1


class TestNoRowsMessage:
    """Check pages and the backcheck tab share one no-rows message."""

    def test_names_the_dataset_task_and_both_pages(self):
        message = template.no_rows_message("survey", "analyze")

        assert message.startswith("**survey** has no rows")
        assert "nothing to analyze" in message
        assert "Prepare Data" in message
        assert "Correct Data" in message


class TestSummaryCheckRates:
    """The Summary tab gets the outlier % and backcheck error rate."""

    REPORTS = (
        "summary_report",
        "descriptive_report",
        "progress_report",
        "missing_report",
        "duplicates_report",
        "outliers_report",
        "gpschecks_report",
        "enumerator_report",
        "backchecks_report",
    )

    def _config(self) -> template.PageConfig:
        return template.PageConfig(
            page_number=1,
            page_name="HFCs",
            page_name_id="hfcs",
            survey_data_name=ALIAS,
            survey_key="key",
            survey_id="key",
            survey_date=None,
            enumerator=None,
            team=None,
            formversion=None,
            duration=None,
            survey_target=None,
            backcheck_data_name="backcheck",
            backcheck_date=None,
            backchecker=None,
            backchecker_team=None,
            backcheck_target_percent=None,
            tracking_data_name=None,
            setting_file=Path("settings.json"),
            missing_setting_file=Path("missing.json"),
        )

    def _render(self, data: template.CheckData) -> dict[str, MagicMock]:
        mock_st = MagicMock()
        mock_st.tabs.return_value = [MagicMock() for _ in self.REPORTS]
        mocks = {name: MagicMock() for name in self.REPORTS}
        mocks["flagged_outlier_percent"] = MagicMock(return_value=12.5)
        mocks["overall_error_rate_percent"] = MagicMock(return_value=4.25)
        with (
            patch.object(template, "st", mock_st),
            patch.multiple(catalogue, **mocks),
        ):
            template.render_check_tabs(PROJECT_ID, self._config(), data)
        return mocks

    def test_rates_are_passed_to_the_summary(self):
        data = template.CheckData(page_data=_rows(2), backcheck_data=_rows(1))

        mocks = self._render(data)

        mocks["flagged_outlier_percent"].assert_called_once()
        rates = mocks["summary_report"].call_args.kwargs["check_rates"]
        assert rates.outliers_pct == 12.5
        assert rates.backcheck_error_pct == 4.25

    @pytest.mark.parametrize("backcheck_rows", [None, 0])
    def test_no_error_rate_without_backcheck_rows(self, backcheck_rows):
        backcheck = None if backcheck_rows is None else _rows(backcheck_rows)
        data = template.CheckData(page_data=_rows(2), backcheck_data=backcheck)

        mocks = self._render(data)

        mocks["overall_error_rate_percent"].assert_not_called()
        rates = mocks["summary_report"].call_args.kwargs["check_rates"]
        assert rates.backcheck_error_pct is None


class TestCatalogueDrivesTheChecks:
    """Adding a check to the catalogue is all it takes for it to appear."""

    def test_every_catalogue_check_gets_a_tab_and_renders(self):
        rendered = []

        def render(slug):
            return lambda ctx: rendered.append((slug, ctx))

        entries = (
            CheckEntry(
                "alpha", "Alpha", ":material/star:", "Overview", render("alpha")
            ),
            CheckEntry("beta", "Beta", ":material/star:", "Overview", render("beta")),
        )
        mock_st = MagicMock()
        mock_st.tabs.return_value = [MagicMock(), MagicMock()]
        data = template.CheckData(page_data=_rows(2))
        config = TestSummaryCheckRates()._config()

        with (
            patch.object(template, "st", mock_st),
            patch.object(catalogue, "CHECK_CATALOGUE", entries),
        ):
            template.render_check_tabs(PROJECT_ID, config, data)

        mock_st.tabs.assert_called_once_with(["Alpha", "Beta"])
        assert [slug for slug, _ in rendered] == ["alpha", "beta"]
        ctx = rendered[0][1]
        assert ctx.project_id == PROJECT_ID
        assert ctx.config is config
        assert ctx.data is data
        assert ctx.survey_columns.all_columns == ["key", "age"]
