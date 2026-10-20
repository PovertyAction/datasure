"""Tests for loading check-page data in the output view template."""

from types import SimpleNamespace
from unittest.mock import patch

import polars as pl
import pytest

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
