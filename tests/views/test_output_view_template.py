"""Tests for the check page: loading data, navigation and check states."""

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks import catalogue
from datasure.checks.catalogue import CheckEntry
from datasure.checks.headline import CheckHeadline
from datasure.utils import nav_ui
from datasure.utils.dataframe_utils import TableState
from datasure.utils.duckdb_utils import duckdb_save_table
from datasure.utils.navigation import READY
from datasure.utils.view_state import remembered, save_selection
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

# Settings sections shown alone under a not-applicable check's empty state.
SETTINGS_SECTIONS = (
    "outliers_settings_section",
    "gpschecks_settings_section",
    "backchecks_settings_section",
)

# Headlines the mocked checks report on their Summary check health rows.
HEADLINES = {
    "progress_headline": CheckHeadline("2", "submitted interviews", informational=True),
    "missing_headline": CheckHeadline(
        "0.00%", "of columns all missing (0 of 2)", outstanding=0
    ),
    "duplicates_headline": CheckHeadline(
        "0", "duplicate IDs", outstanding=0, resolved=6
    ),
    "outliers_headline": CheckHeadline(
        "1", "1 outlier, 0 constraint violations", outstanding=1, resolved=0
    ),
    "enumerator_headline": CheckHeadline(
        "1 / 1", "active in the past 7 days", informational=True
    ),
    "backchecks_headline": CheckHeadline(
        "3", "4.25% error rate", outstanding=3, resolved=2
    ),
    "gpschecks_headline": CheckHeadline(
        "2", "GPS outliers (20.00% of 10 points)", outstanding=2, resolved=1
    ),
    "gpschecks_headline_view": "[]",
}


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
        # Columns draw through st itself, so calls stay in drawing order.
        self.st.columns.side_effect = lambda spec, **_: (
            [self.st] * (spec if isinstance(spec, int) else len(spec))
        )
        self.tmp_path = tmp_path
        self.config = _config(tmp_path, **config)
        self.reports = {name: MagicMock(name=name) for name in REPORTS}
        self.headlines = {
            name: MagicMock(name=name, return_value=value)
            for name, value in HEADLINES.items()
        }
        self.settings = {name: MagicMock(name=name) for name in SETTINGS_SECTIONS}

    def render(self, data: template.CheckData) -> list[str]:
        """Render the page once; return the reports that ran."""
        for report in (*self.reports.values(), *self.settings.values()):
            report.reset_mock()
        self.st.reset_mock()
        with (
            self.monkeypatch.context() as m,
            patch.object(template, "st", self.st),
            patch.object(template, "get_cache_path", self.cache_path),
            patch.multiple(
                catalogue, **self.reports, **self.headlines, **self.settings
            ),
        ):
            m.setitem(sys.modules, "streamlit", self.st)
            template.render_checks(PROJECT_ID, self.config, data)
        return [name for name in REPORTS if self.reports[name].called]

    def cache_path(self, *parts) -> Path:
        return self.tmp_path.joinpath(*map(str, parts))

    @property
    def project_view_file(self) -> Path:
        return self.cache_path(PROJECT_ID, "settings", nav_ui.PROJECT_VIEW_FILE)

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

    def rows(self) -> dict[str, list[str]]:
        """The Summary check health rows: each row's texts by its check label.

        A row starts with its label, the markdown drawn just before its
        status pill; the pill, value, detail and resolved count follow, up to
        the next row's label. Group and column headings (bold captions) are
        left out.
        """
        calls = [
            (c[0], str(c.args[0]))
            for c in self.st.method_calls
            if c[0] in {"markdown", "caption", "badge"} and c.args
        ]
        rows: dict[str, list[str]] = {}
        current = None
        for (name, text), (next_name, _) in zip(
            calls, [*calls[1:], ("", "")], strict=True
        ):
            if name == "markdown" and next_name == "badge":
                current = text.strip("*")
                rows[current] = []
            elif current is not None and not (
                name == "caption" and text.startswith("**")
            ):
                rows[current].append(text)
        return rows

    def pills(self) -> list[tuple[str, str, str]]:
        """Each row's status pill (colour, icon, label), in row order."""
        return [
            (c.kwargs["color"], c.kwargs["icon"], c.args[0])
            for c in self.st.badge.call_args_list
        ]

    def row_buttons(self) -> dict[str, str]:
        """The health row buttons: label by check slug."""
        return {
            c.kwargs["args"][0]: c.args[0]
            for c in self.st.button.call_args_list
            if c.kwargs.get("key", "").startswith("health_row_")
        }

    def click_row(self, slug: str) -> None:
        """Click a health row's button."""
        call = next(
            c
            for c in self.st.button.call_args_list
            if c.kwargs.get("key") == f"health_row_{slug}"
        )
        with self.monkeypatch.context() as m:
            m.setitem(sys.modules, "streamlit", self.st)
            call.kwargs["on_click"](*call.kwargs["args"])


@pytest.fixture
def page(monkeypatch, tmp_path):
    def make(**kwargs) -> CheckPage:
        return CheckPage(monkeypatch, tmp_path, **kwargs)

    return make


SURVEY = template.CheckData(page_data=_rows(2), backcheck_data=_rows(1))


class TestSummaryHealthRows:
    """Summary shows a check health row per check, with a button to open it."""

    GROUPS = ("Overview", "Data integrity", "Field team", "Exploration")

    @pytest.fixture(autouse=True)
    def _fresh_headlines(self):
        from datasure.checks.health import clear_headline_cache

        clear_headline_cache()
        yield
        clear_headline_cache()

    def test_a_row_for_every_check_except_summary(self, page):
        check_page = page()

        check_page.render(SURVEY)

        assert list(check_page.rows()) == [
            entry.label
            for entry in catalogue.CHECK_CATALOGUE
            if entry.slug != "summary"
        ]

    def test_rows_are_grouped_under_the_navigation_groups(self, page):
        check_page = page()

        check_page.render(SURVEY)

        headings = {f"**{group}**" for group in self.GROUPS}
        shown = [
            str(c.args[0])
            for c in check_page.st.caption.call_args_list
            if str(c.args[0]) in headings
        ]
        assert shown == [f"**{group}**" for group in self.GROUPS]

    def test_ready_rows_show_their_numbers(self, page):
        check_page = page()

        check_page.render(SURVEY)

        rows = check_page.rows()
        assert rows["Duplicates"] == ["No issues", "**0**", "duplicate IDs", "6"]
        assert rows["Backchecks"] == ["Flagged", "**3**", "4.25% error rate", "2"]
        assert rows["Progress"] == [
            "No issues",
            "**2**",
            "submitted interviews",
            "—",
        ]
        assert check_page.row_buttons()["duplicates"] == "Open →"

    def test_status_pills_have_a_colour_icon_and_label(self, page):
        check_page = page()

        check_page.render(SURVEY)

        pills = dict(zip(check_page.rows(), check_page.pills(), strict=True))
        assert pills["Backchecks"] == ("orange", ":material/warning:", "Flagged")
        assert pills["Duplicates"] == (
            "green",
            ":material/check_circle:",
            "No issues",
        )
        assert pills["GPS Checks"] == (
            "gray",
            ":material/do_not_disturb_on:",
            "Not applicable",
        )
        assert pills["Outliers & Constraints"] == (
            "gray",
            ":material/build:",
            "Not set up",
        )

    def test_a_ready_gps_check_shows_its_outliers(self, page):
        check_page = page()

        with patch.object(catalogue, "gpschecks_status", return_value=READY):
            check_page.render(SURVEY)

        assert check_page.rows()["GPS Checks"] == [
            "Flagged",
            "**2**",
            "GPS outliers (20.00% of 10 points)",
            "1",
        ]
        check_page.headlines["gpschecks_headline"].assert_called_once_with(
            PROJECT_ID,
            "hfcs",
            SURVEY.page_data,
            {
                "survey_key": "key",
                "survey_id": "key",
                "survey_date": None,
                "enumerator": None,
                "team": None,
            },
            alias=ALIAS,
        )
        check_page.headlines["gpschecks_headline_view"].assert_called_with(
            PROJECT_ID, "hfcs"
        )

    def test_descriptive_stats_shows_status_only(self, page):
        check_page = page()

        check_page.render(SURVEY)

        assert check_page.rows()["Descriptive Stats"] == [
            "No issues",
            "**—**",
            "Status only",
            "—",
        ]

    def test_not_ready_rows_show_their_status_and_reason(self, page):
        check_page = page()

        check_page.render(SURVEY)

        rows, buttons = check_page.rows(), check_page.row_buttons()
        assert "No GPS column found in this dataset." in rows["GPS Checks"]
        assert "gps" not in buttons
        assert any(
            "No outlier or constraint columns" in text
            for text in rows["Outliers & Constraints"]
        )
        assert buttons["outliers"] == "Set up →"
        # Not-ready checks do not compute a headline.
        check_page.headlines["outliers_headline"].assert_not_called()

    def test_a_number_that_fails_shows_a_red_row_and_the_others_render(self, page):
        check_page = page()
        check_page.headlines["duplicates_headline"].side_effect = ValueError("boom")

        check_page.render(SURVEY)

        rows = check_page.rows()
        pills = dict(zip(rows, check_page.pills(), strict=True))
        assert pills["Duplicates"] == ("red", ":material/error:", "Error")
        assert any("ValueError: boom" in text for text in rows["Duplicates"])
        assert pills["Backchecks"][2] == "Flagged"
        assert rows["Backchecks"][1] == "**3**"

    @pytest.mark.parametrize(
        ("slug", "report"),
        [("duplicates", "duplicates_report"), ("outliers", "outliers_report")],
    )
    def test_row_buttons_select_the_check(self, page, slug, report):
        check_page = page()
        check_page.render(SURVEY)

        check_page.click_row(slug)

        assert check_page.render(SURVEY) == [report]
        assert check_page.st.query_params == {"check": slug}

    def test_headlines_are_cached_between_runs(self, page):
        check_page = page()

        check_page.render(SURVEY)
        check_page.render(SURVEY)

        check_page.headlines["duplicates_headline"].assert_called_once()

    def test_headlines_are_not_computed_when_another_check_is_shown(self, page):
        check_page = page(url="missing")

        check_page.render(SURVEY)

        for headline in check_page.headlines.values():
            headline.assert_not_called()


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
    def test_not_applicable_check_shows_why_then_its_settings(self, page):
        check_page = page(url="gps")

        assert check_page.render(SURVEY) == []
        assert "No GPS column found in this dataset." in check_page.messages("info")
        assert "not applicable" in check_page.label("gps")
        # The settings stay reachable, e.g. to configure GPS columns the
        # name heuristic missed.
        check_page.settings["gpschecks_settings_section"].assert_called_once()

    def test_backchecks_with_no_rows_shows_why_then_its_settings(self, page):
        check_page = page(url="backchecks")
        no_rows = template.CheckData(page_data=_rows(2), backcheck_data=_rows(0))

        assert check_page.render(no_rows) == []
        assert "does not apply" in check_page.messages("info")
        check_page.settings["backchecks_settings_section"].assert_called_once()

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
        info = check_page.messages("info")
        assert "Configure Checks" in info
        # Its fix is on another page, linked below, not settings below.
        assert "Set it up below" not in info
        assert "linked below" in info
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


class TestLastViewedCheckPage:
    def test_rendering_a_check_page_records_it_for_corrections(self, page):
        check_page = page(page_name_id="household_survey")

        check_page.render(SURVEY)

        # Saved to a project-level file, so it survives a new session.
        assert (
            remembered(check_page.project_view_file, nav_ui.LAST_CHECK_PAGE)
            == "household_survey"
        )

    def test_the_record_is_only_written_when_it_changes(self, page):
        check_page = page(page_name_id="household_survey")
        check_page.render(SURVEY)
        written = check_page.project_view_file.stat().st_mtime_ns

        with patch("datasure.utils.view_state.write_settings") as write:
            check_page.render(SURVEY)

        write.assert_not_called()
        assert check_page.project_view_file.stat().st_mtime_ns == written
