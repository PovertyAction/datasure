"""Tests for the check page: loading data, navigation and check states."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks import catalogue
from datasure.checks.catalogue import CheckEntry
from datasure.utils.dataframe_utils import TableState
from datasure.utils.duckdb_utils import duckdb_save_table
from datasure.utils.view_state import ViewState, save_selection
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


def _config(tmp_path: Path, **overrides) -> template.PageConfig:
    values = {
        "page_number": 1,
        "page_name": "HFCs",
        "page_name_id": "hfcs",
        "survey_data_name": ALIAS,
        "survey_key": "key",
        "survey_id": "key",
        "survey_date": None,
        "enumerator": None,
        "team": None,
        "formversion": None,
        "duration": None,
        "survey_target": None,
        "backcheck_data_name": "backcheck",
        "backcheck_date": None,
        "backchecker": None,
        "backchecker_team": None,
        "backcheck_target_percent": None,
        "tracking_data_name": None,
        "setting_file": tmp_path / "settings.json",
        "missing_setting_file": tmp_path / "missing.json",
    }
    values.update(overrides)
    return template.PageConfig(**values)


class CheckPage:
    """Renders the check page with Streamlit and every report mocked.

    Selection is driven the way a user drives it: through the mocked
    segmented control (groups) and pills (checks), whose on_change callbacks
    run before the next render, as in Streamlit.
    """

    def __init__(self, monkeypatch, tmp_path, url=None, **config):
        self.monkeypatch = monkeypatch
        self.st = MagicMock()
        self.st.session_state = {"st_config_checks_page": "config_page"}
        self.st.query_params = {} if url is None else {"check": url}
        self.config = _config(tmp_path, **config)
        self.reports = {name: MagicMock(name=name) for name in REPORTS}
        self.reports["flagged_outlier_percent"] = MagicMock(return_value=12.5)
        self.reports["overall_error_rate_percent"] = MagicMock(return_value=4.25)

    def render(self, data: template.CheckData) -> list[str]:
        """Render the page once; return the reports that ran."""
        for report in self.reports.values():
            report.reset_mock()
        self.st.reset_mock()
        with (
            self.monkeypatch.context() as m,
            patch.object(template, "st", self.st),
            patch.multiple(catalogue, **self.reports),
        ):
            m.setitem(sys.modules, "streamlit", self.st)
            template.render_checks(PROJECT_ID, self.config, data)
        return [name for name in REPORTS if self.reports[name].called]

    def _widget(self, name: str):
        return getattr(self.st, name).call_args

    def click(self, widget: str, value: str) -> None:
        """Choose a value in the segmented control or the pills."""
        call = self._widget(widget)
        self.st.session_state[call.kwargs["key"]] = value
        with self.monkeypatch.context() as m:
            m.setitem(sys.modules, "streamlit", self.st)
            call.kwargs["on_change"](*call.kwargs.get("args", ()))

    def options(self, widget: str) -> list[str]:
        return list(self._widget(widget).args[1])

    def label(self, slug: str) -> str:
        return self._widget("pills").kwargs["format_func"](slug)

    def messages(self, kind: str) -> str:
        return "\n".join(str(c.args[0]) for c in getattr(self.st, kind).call_args_list)


@pytest.fixture
def page(monkeypatch, tmp_path):
    def make(**kwargs) -> CheckPage:
        return CheckPage(monkeypatch, tmp_path, **kwargs)

    return make


SURVEY = template.CheckData(page_data=_rows(2), backcheck_data=_rows(1))


class TestSummaryCheckRates:
    """Summary gets the outlier % and backcheck error rate when it is shown."""

    def test_rates_are_passed_to_the_summary(self, page):
        check_page = page()

        check_page.render(SURVEY)

        mocks = check_page.reports
        mocks["flagged_outlier_percent"].assert_called_once()
        rates = mocks["summary_report"].call_args.kwargs["check_rates"]
        assert rates.outliers_pct == 12.5
        assert rates.backcheck_error_pct == 4.25

    @pytest.mark.parametrize("backcheck_rows", [None, 0])
    def test_no_error_rate_without_backcheck_rows(self, page, backcheck_rows):
        backcheck = None if backcheck_rows is None else _rows(backcheck_rows)
        data = template.CheckData(page_data=_rows(2), backcheck_data=backcheck)
        check_page = page()

        check_page.render(data)

        mocks = check_page.reports
        mocks["overall_error_rate_percent"].assert_not_called()
        rates = mocks["summary_report"].call_args.kwargs["check_rates"]
        assert rates.backcheck_error_pct is None

    def test_rates_are_not_computed_when_another_check_is_shown(self, page):
        check_page = page(url="missing")

        check_page.render(SURVEY)

        check_page.reports["flagged_outlier_percent"].assert_not_called()
        check_page.reports["overall_error_rate_percent"].assert_not_called()


class TestNavigation:
    def test_opens_on_summary_and_only_runs_summary(self, page):
        check_page = page()

        assert check_page.render(SURVEY) == ["summary_report"]
        assert check_page.st.query_params == {"check": "summary"}

    def test_groups_and_short_labels(self, page):
        check_page = page()
        check_page.render(SURVEY)

        assert check_page.options("segmented_control") == [
            "Overview",
            "Data integrity",
            "Field team",
            "Exploration",
        ]
        assert check_page.options("pills") == ["summary", "progress"]
        assert check_page.label("progress") == ":material/trending_up: Progress"

    def test_choosing_a_check_runs_only_that_report_and_updates_the_url(self, page):
        check_page = page()
        check_page.render(SURVEY)

        check_page.click("segmented_control", "Data integrity")
        # Switching group selects the first check in that group.
        assert check_page.render(SURVEY) == ["missing_report"]
        assert check_page.options("pills") == [
            "missing",
            "duplicates",
            "outliers",
            "gps",
        ]

        check_page.click("pills", "duplicates")
        assert check_page.render(SURVEY) == ["duplicates_report"]
        assert check_page.st.query_params == {"check": "duplicates"}

    def test_switching_back_to_a_group_selects_its_last_check(self, page):
        check_page = page(url="duplicates")
        check_page.render(SURVEY)

        check_page.click("segmented_control", "Overview")
        assert check_page.render(SURVEY) == ["summary_report"]
        check_page.click("segmented_control", "Data integrity")

        assert check_page.render(SURVEY) == ["duplicates_report"]

    @pytest.mark.parametrize(
        ("url", "report"),
        [
            ("descriptive", "descriptive_report"),
            ("enumerator", "enumerator_report"),
            ("debrief", "summary_report"),
            ("", "summary_report"),
        ],
    )
    def test_url_opens_a_valid_check_and_falls_back_to_summary(self, page, url, report):
        check_page = page(url=url)

        assert check_page.render(SURVEY) == [report]
        assert check_page.st.query_params["check"] == report.split("_")[0]


class TestNotReadyChecks:
    def test_not_applicable_check_shows_why_without_running(self, page):
        check_page = page(url="gps")

        assert check_page.render(SURVEY) == []
        assert "No GPS column found in this dataset." in check_page.messages("info")
        assert "not applicable" in check_page.label("gps")

    def test_not_set_up_check_shows_the_reason_and_its_settings(self, page):
        check_page = page(url="outliers")

        # The report draws the check's settings and stops before results.
        assert check_page.render(SURVEY) == ["outliers_report"]
        info = check_page.messages("info")
        assert "No outlier or constraint columns are set up yet." in info
        assert "Set it up below" in info
        assert "not set up" in check_page.label("outliers")

    def test_backchecks_without_a_dataset_links_to_configure_checks(self, page):
        check_page = page(url="backchecks", backcheck_data_name=None)

        assert check_page.render(template.CheckData(page_data=_rows(2))) == []
        assert "Configure Checks" in check_page.messages("info")
        check_page.st.page_link.assert_called_once()
        assert check_page.st.page_link.call_args.args[0] == "config_page"


class TestErrorIsolation:
    def test_a_check_that_raises_shows_an_error_and_is_marked(self, page):
        check_page = page(url="missing")
        check_page.reports["missing_report"].side_effect = ValueError("boom")

        check_page.render(SURVEY)

        assert "ValueError: boom" in check_page.messages("error")
        # The navigation is still drawn, with the check marked.
        assert "error" in check_page.label("missing")
        assert "error" not in check_page.label("duplicates")

    def test_the_rest_of_the_page_still_works(self, page):
        check_page = page(url="missing")
        check_page.reports["missing_report"].side_effect = ValueError("boom")
        check_page.render(SURVEY)

        check_page.click("pills", "duplicates")

        assert check_page.render(SURVEY) == ["duplicates_report"]
        assert check_page.messages("error") == ""

    def test_a_status_that_raises_marks_only_that_check(self, page, monkeypatch):
        monkeypatch.setattr(
            catalogue, "duplicates_status", MagicMock(side_effect=OSError("disk"))
        )
        check_page = page()

        assert check_page.render(SURVEY) == ["summary_report"]
        check_page.click("segmented_control", "Data integrity")
        check_page.render(SURVEY)

        assert "error" in check_page.label("duplicates")
        assert "error" not in check_page.label("missing")


class TestCatalogueDrivesTheChecks:
    """Adding a check to the catalogue is all it takes for it to appear."""

    def test_a_new_catalogue_check_is_reachable_and_renders(self, page, monkeypatch):
        rendered = []
        entries = (
            *catalogue.CHECK_CATALOGUE,
            CheckEntry(
                "debrief",
                "Debrief",
                ":material/forum:",
                "Field team",
                render=rendered.append,
            ),
        )
        monkeypatch.setattr(catalogue, "CHECK_CATALOGUE", entries)
        check_page = page(url="debrief")

        assert check_page.render(SURVEY) == []
        assert check_page.options("pills") == ["enumerator", "backchecks", "debrief"]
        ctx = rendered[0]
        assert ctx.project_id == PROJECT_ID
        assert ctx.config is check_page.config
        assert ctx.survey_columns.all_columns == ["key", "age"]


class TestSavedSelection:
    """The page returns to the last check in a new session; a URL wins."""

    def test_a_new_session_reopens_the_last_check(self, page):
        first = page()
        first.render(SURVEY)
        first.click("segmented_control", "Field team")
        first.render(SURVEY)

        new_session = page()

        assert new_session.render(SURVEY) == ["enumerator_report"]
        assert new_session.st.query_params == {"check": "enumerator"}

    def test_a_url_check_wins_over_the_saved_one(self, page):
        page(url="enumerator").render(SURVEY)

        assert page(url="duplicates").render(SURVEY) == ["duplicates_report"]

    def test_a_stale_saved_check_falls_back_to_summary(self, page):
        check_page = page()
        save_selection(check_page.config.setting_file, "removed_check")

        assert check_page.render(SURVEY) == ["summary_report"]


class TestResetFilters:
    def test_reset_clears_only_the_shown_checks_view_state(self, page):
        check_page = page(url="duplicates")
        settings = check_page.config.setting_file
        ViewState(settings, "duplicates").save("iddup_survey_sort", "KEY")
        ViewState(settings, "gps").save("gps_color_by", "team")
        check_page.st.session_state["iddup_survey_sort"] = "KEY"
        check_page.render(SURVEY)

        reset = next(
            call
            for call in check_page.st.button.call_args_list
            if call.args[0] == "Reset filters"
        )
        with patch.dict(sys.modules, {"streamlit": check_page.st}):
            reset.kwargs["on_click"](*reset.kwargs.get("args", ()))

        assert ViewState(settings, "duplicates").values() == {}
        assert "iddup_survey_sort" not in check_page.st.session_state
        assert ViewState(settings, "gps").values() == {"gps_color_by": "team"}
