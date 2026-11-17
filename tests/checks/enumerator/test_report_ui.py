"""Tests for datasure.checks.enumerator.report_ui."""

import importlib
import json
import sys
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks.enumerator.attention import (
    AttentionRow,
    OtherChecks,
    Reason,
    Severity,
)
from datasure.checks.enumerator.models import ConsentOutcomeSettings
from datasure.checks.enumerator.report_ui import (
    ATTENTION_SHOWN,
    PageControls,
    _adopt_shared_controls,
    _get_numeric_columns,
    _md,
    _render_attention_row,
    _render_column_selector,
    _render_column_selector_single,
    _render_columns_in_use,
    _render_enumerator_productivity,
    _render_needs_attention,
    _render_overview,
    _render_page_controls,
    _render_statistic_selector,
    _render_statistics_selector,
    enumerator_report_data,
)
from datasure.models.schemas import ColumnByType
from datasure.utils.view_state import ViewState
from tests.checks.enumerator.conftest import make_mock_st

# ============================================
# PATCHED_ENUM FIXTURE (patch st in report_ui for non-fragment UI functions)
# ============================================


@pytest.fixture
def patched_enum():
    """Patch st in report_ui module for non-fragment UI function tests."""
    mock_st = make_mock_st()
    with (
        patch("datasure.checks.enumerator.report_ui.st", mock_st),
        patch(
            "datasure.checks.enumerator.report_ui.load_check_settings", return_value={}
        ),
        patch("datasure.checks.enumerator.report_ui.demo_callout"),
        patch("datasure.utils.onboarding_utils.is_demo_project", return_value=False),
    ):
        yield mock_st


# ============================================
# ENUM_BC FIXTURE (reload compute/settings_ui/report_ui with mocked streamlit)
# ============================================


@pytest.fixture
def enum_bc():
    """Reload enumerator submodules with mocked Streamlit to strip fragments."""
    mock_st = make_mock_st()
    original_st = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock_st

    import datasure.checks.enumerator.compute as compute_module
    import datasure.checks.enumerator.report_ui as report_ui_module
    import datasure.checks.enumerator.settings_ui as settings_ui_module

    try:
        # Reload in dependency order so decorators pick up the mocked st and
        # cross-module references (report_ui imports from settings_ui) stay wired.
        importlib.reload(compute_module)
        importlib.reload(settings_ui_module)
        importlib.reload(report_ui_module)

        compute_module.load_missing_codes_from_db = MagicMock(
            return_value=pl.DataFrame()
        )

        settings_ui_module.load_check_settings = MagicMock(return_value={})
        settings_ui_module.save_check_settings = MagicMock()
        settings_ui_module.trigger_save = MagicMock()
        settings_ui_module.duckdb_save_table = MagicMock()

        report_ui_module.load_check_settings = MagicMock(return_value={})
        report_ui_module.save_check_settings = MagicMock()
        report_ui_module.trigger_save = MagicMock()
        report_ui_module.load_missing_codes_from_db = MagicMock(
            return_value=pl.DataFrame()
        )
        report_ui_module.demo_callout = MagicMock()

        with patch(
            "datasure.utils.onboarding_utils.is_demo_project", return_value=False
        ):
            yield report_ui_module
    finally:
        if original_st is not None:
            sys.modules["streamlit"] = original_st
        else:
            sys.modules.pop("streamlit", None)
        importlib.reload(compute_module)
        importlib.reload(settings_ui_module)
        importlib.reload(report_ui_module)


# ============================================
# HELPER FUNCTIONS TESTS
# ============================================


def test_get_numeric_columns():
    """Test _get_numeric_columns helper function."""
    data = pl.DataFrame(
        {
            "age": [25, 30, 35],
            "income": [50000, 60000, 55000],
            "name": ["Alice", "Bob", "Charlie"],
            "is_active": [True, False, True],
        }
    )

    result = _get_numeric_columns(data)
    assert "age" in result
    assert "income" in result
    assert "name" not in result
    assert "is_active" not in result


def test_get_numeric_columns_with_exclude():
    """Test _get_numeric_columns with exclude list."""
    data = pl.DataFrame(
        {
            "age": [25, 30, 35],
            "income": [50000, 60000, 55000],
            "duration": [3600, 4200, 3800],
        }
    )

    result = _get_numeric_columns(data, exclude_cols=["duration"])
    assert "age" in result
    assert "income" in result
    assert "duration" not in result


def test_get_numeric_columns_empty_dataframe():
    """Test _get_numeric_columns with empty DataFrame."""
    data = pl.DataFrame()
    result = _get_numeric_columns(data)
    assert result == []


def test_get_numeric_columns_no_numeric():
    """Test _get_numeric_columns with no numeric columns."""
    data = pl.DataFrame(
        {
            "name": ["Alice", "Bob"],
            "city": ["NYC", "LA"],
        }
    )
    result = _get_numeric_columns(data)
    assert result == []


# ============================================
# PATCHED_ENUM UI FUNCTION TESTS
# ============================================

WEEK = PageControls("Week", "SUN", None)
DAY = PageControls("Day", "SUN", None)


def _drawn_columns(mock_st):
    return [col for result in mock_st._made_columns for col in result]


@pytest.fixture
def tracked_columns(patched_enum):
    """Keep the columns the mock makes, so tests can read their metrics."""
    factory = patched_enum.columns.side_effect
    patched_enum._made_columns = []

    def track(*args, **kwargs):
        made = factory(*args, **kwargs)
        patched_enum._made_columns.append(made)
        return made

    patched_enum.columns.side_effect = track
    return patched_enum


def test_render_overview_shows_four_figures_with_comparisons(
    tracked_columns, sample_enumerator_data, sample_enumerator_settings
):
    """The overview has four figures; the last is interview length in minutes."""
    with patch.dict(sys.modules, {"streamlit": tracked_columns}):
        _render_overview(sample_enumerator_data, sample_enumerator_settings)

    metrics = [
        m for col in _drawn_columns(tracked_columns) for m in col.metric.mock_calls
    ]
    labels = [m.args[0] for m in metrics]
    assert labels == [
        "Active in the past 7 days",
        "Submissions in the past 7 days",
        "Submissions per enumerator",
        "Interview length",
    ]
    assert metrics[3].args[1] == "1 h 4 min"
    assert metrics[2].kwargs["delta"] == "Range 1 to 3"
    assert "Fewest: E3 (1). Most: E1 (3)." in metrics[2].kwargs["help"]


def test_render_overview_without_duration_shows_teams(
    tracked_columns, sample_enumerator_data, sample_enumerator_settings
):
    """Without a duration column the fourth figure counts the teams."""
    settings = sample_enumerator_settings.model_copy(update={"duration": None})
    with patch.dict(sys.modules, {"streamlit": tracked_columns}):
        _render_overview(sample_enumerator_data, settings)

    labels = [
        m.args[0]
        for col in _drawn_columns(tracked_columns)
        for m in col.metric.mock_calls
    ]
    assert labels[-1] == "Teams"


def test_columns_in_use_names_set_and_unset_columns(
    patched_enum, sample_enumerator_settings
):
    """The caption names the columns in use and the ones still to set."""
    _render_columns_in_use(sample_enumerator_settings, ConsentOutcomeSettings())

    text = patched_enum.caption.call_args.args[0]
    assert "enumerator **enumerator**" in text
    assert "Not set: consent, outcome." in text


def test_markdown_in_names_is_escaped():
    """Names shown in Markdown cannot turn into formatting."""
    assert _md("a*b_[c]") == r"a\*b\_\[c\]"


def test_render_column_selector(patched_enum):
    """_render_column_selector returns list from multiselect."""
    result = _render_column_selector(["age", "income"], None, "settings.json")
    assert isinstance(result, list)
    patched_enum.multiselect.assert_called()
    assert patched_enum.multiselect.call_args.kwargs["label"] == "Columns"


def test_render_statistics_selector(patched_enum):
    """_render_statistics_selector returns list from multiselect."""
    result = _render_statistics_selector(["count", "mean"], "settings.json")
    assert isinstance(result, list)
    patched_enum.multiselect.assert_called()


def test_render_statistic_selector(patched_enum):
    """_render_statistic_selector returns the selectbox value."""
    patched_enum.selectbox.return_value = "mean"
    result = _render_statistic_selector("count", "settings.json")
    assert result == "mean"


def test_render_column_selector_single_default_none(patched_enum):
    """_render_column_selector_single returns None when selectbox returns None."""
    result = _render_column_selector_single(["age", "income"], None, "settings.json")
    assert result is None
    patched_enum.selectbox.assert_called()


def test_render_column_selector_single_with_value(patched_enum):
    """_render_column_selector_single returns the selectbox value."""
    patched_enum.selectbox.return_value = "age"
    result = _render_column_selector_single(["age", "income"], "age", "settings.json")
    assert result == "age"


def test_render_enumerator_productivity_uses_the_page_period(
    patched_enum, sample_enumerator_data
):
    """Productivity groups by the page's period, with no controls of its own."""
    with patch(
        "datasure.checks.enumerator.report_ui.compute_enumerator_productivity",
        return_value=pl.DataFrame({"enumerator": ["E1"]}),
    ) as compute:
        _render_enumerator_productivity(
            sample_enumerator_data, "submission_date", "enumerator", None, WEEK
        )

    assert compute.call_args.args[3:] == ("Week", "SUN")
    patched_enum.pills.assert_not_called()
    patched_enum.dataframe.assert_called()


# ============================================
# PAGE CONTROLS AND SAVED VIEW STATE
# ============================================


@pytest.fixture
def fake_session(monkeypatch):
    """A fresh Streamlit session for widgets bound to saved view state."""
    fake_st = SimpleNamespace(session_state={})
    monkeypatch.setitem(sys.modules, "streamlit", fake_st)
    return fake_st.session_state


def test_page_controls_default_to_weekly_and_all_teams(
    patched_enum, sample_enumerator_data
):
    """Without saved choices the page groups by week, from Monday, all teams."""
    controls = _render_page_controls("settings.json", sample_enumerator_data, "team")

    assert controls == PageControls("Week", "SUN", None)
    team_box = patched_enum.selectbox.call_args_list[-1]
    assert team_box.args[0] == "Team"
    assert team_box.kwargs["options"] == ["All teams", "T1", "T2"]


def test_page_controls_return_the_chosen_team_and_period(
    patched_enum, sample_enumerator_data
):
    """A chosen team and period come back for every section to use."""
    patched_enum.segmented_control.return_value = "Month"
    patched_enum.selectbox.return_value = "T2"

    controls = _render_page_controls("settings.json", sample_enumerator_data, "team")

    assert controls == PageControls("Month", "SUN", "T2")


def test_page_controls_without_team_column_draw_no_team_filter(
    patched_enum, sample_enumerator_data
):
    """With no team column there is nothing to filter by."""
    patched_enum.segmented_control.return_value = "Day"

    controls = _render_page_controls("settings.json", sample_enumerator_data, None)

    assert controls.team is None
    patched_enum.selectbox.assert_not_called()


def test_sections_periods_saved_by_older_versions_become_the_page_period(tmp_path):
    """Productivity's saved period and week start become the page's; both go."""
    settings_file = tmp_path / "page_hfcs_settings.json"
    view = ViewState(settings_file, "enumerator")
    view.save("time_period_enumerator_productivity_key", "Month")
    view.save("project_enumerator_statistics_overtime_period_pills", "Day")
    view.save("project_week_start_day_enumerator_overtime", "Sunday")
    view.save("statistics_options_enumerator", ["median"])

    _adopt_shared_controls(view)

    assert view.values() == {
        "period": "Month",
        "week_start": "Sunday",
        "statistics_options_enumerator": ["median"],
    }


def test_a_saved_page_period_wins_over_older_section_periods(tmp_path):
    """Once the page has its own period, older section choices are dropped."""
    settings_file = tmp_path / "page_hfcs_settings.json"
    view = ViewState(settings_file, "enumerator")
    view.save("period", "Day")
    view.save("time_period_enumerator_productivity_key", "Month")

    _adopt_shared_controls(view)

    assert view.values() == {"period": "Day"}


def test_report_choices_come_back_from_view_state(patched_enum, fake_session, tmp_path):
    """Saved statistics choices are restored in a new session."""
    settings_file = tmp_path / "page_hfcs_settings.json"
    view = ViewState(settings_file, "enumerator")
    view.save("statistics_options_enumerator", ["median", "not_a_stat"])
    view.save("enumerator_statistics_overtime_stat", "max")

    _render_statistics_selector(["count", "mean"], str(settings_file))
    _render_statistic_selector("count", str(settings_file))

    assert fake_session["statistics_options_enumerator"] == ["median"]
    assert fake_session["enumerator_statistics_overtime_stat"] == "max"


def test_report_choices_saved_by_older_versions_move_to_view_state(
    patched_enum, fake_session, tmp_path
):
    """Old saves load as before but leave the exported check settings."""
    settings_file = tmp_path / "page_hfcs_settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "enumerators": {
                    "enumerator": "enum",
                    "statscol": "age",
                    "period_overtime": "Month",
                }
            }
        )
    )

    _render_column_selector_single(["age", "income"], None, str(settings_file))

    assert fake_session["enumerator_statistics_overtime_column"] == "age"
    assert json.loads(settings_file.read_text())["enumerators"] == {
        "enumerator": "enum"
    }
    assert ViewState(settings_file, "enumerator").values() == {
        "enumerator_statistics_overtime_column": "age",
        "project_enumerator_statistics_overtime_period_pills": "Month",
    }


# ============================================
# NEEDS ATTENTION
# ============================================


def _row(name, *severities, team="T1"):
    return AttentionRow(
        name,
        team,
        tuple(Reason("Check", f"finding {i}", s) for i, s in enumerate(severities)),
    )


def test_needs_attention_with_no_rows_says_so(patched_enum):
    """An empty list is a success, with what was checked under it."""
    _render_needs_attention([], ["activity", "duplicates"], OtherChecks())

    patched_enum.success.assert_called_once()
    assert patched_enum.caption.call_args.args[0] == "Checked: activity, duplicates."


def test_needs_attention_lists_rows_and_folds_the_rest(patched_enum):
    """The first rows show; the rest fold into an expander."""
    rows = [_row(f"E{i}", Severity.FLAG) for i in range(ATTENTION_SHOWN + 2)]

    _render_needs_attention(rows, ["activity"], OtherChecks())

    patched_enum.expander.assert_called_once_with("2 more")
    first = patched_enum.caption.call_args_list[0].args[0]
    assert first.startswith("12 flagged and 0 to watch")


def test_needs_attention_shows_each_check_left_out_as_an_error(patched_enum):
    """A check whose numbers failed is named with its reason."""
    other = OtherChecks(errors=(("Outliers", "ValueError: bad settings"),))

    _render_needs_attention([], [], other)

    message = patched_enum.error.call_args.args[0]
    assert message.startswith("Outliers is left out of this list")
    assert "ValueError: bad settings" in message


def test_attention_row_shows_badges_and_escaped_findings(patched_enum):
    """Each reason shows its severity badge, its check and its finding."""
    row = AttentionRow(
        "E*1",
        "T1",
        (
            Reason("Duplicates", "2 records with a duplicate ID", Severity.FLAG),
            Reason("Activity", "No submissions since Mon", Severity.WATCH),
        ),
    )

    _render_attention_row(row, "1 flag")

    markdown = [c.args[0] for c in patched_enum.markdown.call_args_list]
    assert markdown[0] == r"**E\*1**"
    assert markdown[1] == (
        "- :red-badge[Flagged] **Duplicates**: 2 records with a duplicate ID\n"
        "- :orange-badge[Watch] **Activity**: No submissions since Mon"
    )


# ============================================
# ENUM_BC UI FRAGMENT TESTS
# ============================================


def test_render_enumerator_summary_table_with_data(enum_bc, sample_enumerator_data):
    """_render_enumerator_summary_table renders the summary it is given."""
    summary = enum_bc.compute_enumerator_summary(
        "proj",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        "formversion",
        "duration",
    )
    enum_bc._render_enumerator_summary_table(summary, "enumerator", "team")
    enum_bc.st.dataframe.assert_called()


def test_summary_table_shows_consent_and_completion_as_percentages(
    enum_bc, sample_enumerator_data
):
    """Consent and completion are 0 to 1 rates, so they show as percentages."""
    summary = enum_bc.compute_enumerator_summary(
        "proj",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        None,
        None,
    )
    enum_bc._render_enumerator_summary_table(summary, "enumerator", None)

    config = enum_bc.st.dataframe.call_args.kwargs["column_config"]
    enum_bc.st.column_config.NumberColumn.assert_any_call("% Consent", format="percent")
    assert "% consent" in config


def test_render_enumerator_summary_table_with_show_info(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_summary_table filters columns when show_info selected."""
    enum_bc.st.pills.return_value = ["submissions"]
    summary = enum_bc.compute_enumerator_summary(
        "proj",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "formversion",
        "duration",
    )
    enum_bc._render_enumerator_summary_table(summary, "enumerator", None)
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_statistics_table_no_cols(enum_bc, sample_enumerator_data):
    """_render_enumerator_statistics_table shows info when no cols selected."""
    enum_bc._render_enumerator_statistics_table(
        sample_enumerator_data, "enumerator", None, "settings.json"
    )
    enum_bc.st.info.assert_called()


def test_render_enumerator_statistics_table_with_cols(enum_bc, sample_enumerator_data):
    """_render_enumerator_statistics_table renders table when cols selected."""
    enum_bc.st.multiselect.side_effect = [["age"], ["count", "mean"]]
    enum_bc._render_enumerator_statistics_table(
        sample_enumerator_data, "enumerator", "team", "settings.json"
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_statistics_overtime_table_no_statscol(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_statistics_overtime_table shows info when statscol None."""
    enum_bc._render_enumerator_statistics_overtime_table(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "settings.json",
        enum_bc.PageControls("Week", "SUN", None),
    )
    enum_bc.st.info.assert_called()


def test_render_enumerator_statistics_overtime_table_uses_the_page_period(
    enum_bc, sample_enumerator_data
):
    """Statistics over time groups by the page's period and week start."""
    enum_bc.st.selectbox.side_effect = ["age", "count"]
    with patch.object(
        enum_bc,
        "compute_enumerator_statistics_overtime",
        return_value=pl.DataFrame({"enumerator": ["E1"]}),
    ) as compute:
        enum_bc._render_enumerator_statistics_overtime_table(
            sample_enumerator_data,
            "submission_date",
            "enumerator",
            "team",
            "settings.json",
            enum_bc.PageControls("Month", "MON", None),
        )

    assert compute.call_args.kwargs["period"] == "Month"
    assert compute.call_args.kwargs["weekstartday"] == "MON"
    enum_bc.st.pills.assert_not_called()
    enum_bc.st.dataframe.assert_called()


def test_enumerator_report_empty_data(enum_bc):
    """enumerator_report shows info and returns early when data is empty."""
    survey_cols = ColumnByType(
        categorical_columns=["survey_id", "enumerator"],
        datetime_columns=["submission_date"],
    )
    enum_bc.enumerator_report(
        "proj_id",
        pl.DataFrame(),
        "settings.json",
        {"survey_id": "survey_id"},
        survey_cols,
    )
    enum_bc.st.info.assert_called()


@pytest.fixture
def full_report(enum_bc):
    """The report module with Response Patterns stubbed out."""
    enum_bc.render_response_patterns = MagicMock()
    enum_bc.cached_response_patterns = MagicMock(return_value=None)
    # The reloaded compute module's cache decorator is a mock; skip the flags.
    enum_bc.enumerator_report_data = MagicMock(side_effect=lambda data, _file: data)
    return enum_bc


def test_enumerator_report_without_enumerator_asks_for_it_once(
    enum_bc, sample_enumerator_data, sample_enumerator_settings
):
    """Without an enumerator column, one message asks for it and nothing else draws."""
    enum_bc.enumerator_report_settings = MagicMock(
        return_value=sample_enumerator_settings.model_copy(update={"enumerator": None})
    )
    enum_bc.enumerator_report(
        "proj_id",
        sample_enumerator_data,
        "settings.json",
        {"survey_id": "survey_id"},
        ColumnByType(),
    )

    enum_bc.st.info.assert_called_once()
    assert "enumerator column" in enum_bc.st.info.call_args.args[0]
    enum_bc.st.dataframe.assert_not_called()


def test_enumerator_report_with_data(
    full_report, sample_enumerator_data, sample_enumerator_settings
):
    """enumerator_report draws every section and asks the other checks once."""
    enum_bc = full_report
    enum_bc.enumerator_report_settings = MagicMock(
        return_value=sample_enumerator_settings
    )
    other_checks = MagicMock(return_value=OtherChecks())

    enum_bc.enumerator_report(
        "proj_id",
        sample_enumerator_data,
        "settings.json",
        {"survey_id": "survey_id"},
        ColumnByType(),
        other_checks=other_checks,
    )

    other_checks.assert_called_once_with("enumerator")
    headers = [c.args[0] for c in enum_bc.st.subheader.call_args_list]
    assert headers[:5] == [
        ":material/flag: Needs attention",
        ":material/table_view: Enumerator summary",
        ":material/calendar_month: Productivity",
        ":material/functions: Column statistics",
        ":material/timeline: Statistics over time",
    ]


def test_enumerator_report_narrows_every_section_to_the_chosen_team(
    full_report, sample_enumerator_data, sample_enumerator_settings
):
    """Choosing a team narrows the data each section gets."""
    enum_bc = full_report
    enum_bc.enumerator_report_settings = MagicMock(
        return_value=sample_enumerator_settings
    )
    enum_bc.st.selectbox.side_effect = lambda label, **kwargs: (
        "T2" if label == "Team" else None
    )
    with patch.object(enum_bc, "_render_enumerator_productivity") as productivity:
        enum_bc.enumerator_report(
            "proj_id",
            sample_enumerator_data,
            "settings.json",
            {"survey_id": "survey_id"},
            ColumnByType(),
        )

    data = productivity.call_args.args[0]
    assert set(data["team"].to_list()) == {"T2"}


# ============================================
# REPORT DATA: consent and outcome flags from the page's saved settings
# ============================================


def _page_settings(tmp_path, name: str, consent_outcome: dict | None = None) -> str:
    """Write a page settings file with the given consent/outcome settings."""
    path = tmp_path / f"page_{name}_settings.json"
    path.write_text(json.dumps({"enumerators": consent_outcome or {}}))
    return str(path)


CONSENT_DATA = pl.DataFrame(
    {
        "enumerator": ["E1", "E1", "E2", "E2"],
        "consent": ["yes", "no", "yes", "yes"],
        "outcome": ["done", "done", "partial", "done"],
    }
)
CONSENT_YES_DONE = {
    "consent": "consent",
    "consent_vals": ["yes"],
    "outcome": "outcome",
    "outcome_vals": ["done"],
}


class TestEnumeratorReportData:
    """The report flags consent and completion from the page's saved settings."""

    def test_flags_consent_and_completion_from_saved_settings(self, tmp_path):
        settings = _page_settings(tmp_path, "a", CONSENT_YES_DONE)

        report_data = enumerator_report_data(CONSENT_DATA, settings)

        assert report_data["consent_granted_agg_col"].to_list() == [1, 0, 1, 1]
        assert report_data["completed_survey_agg_col"].to_list() == [1, 1, 0, 1]

    def test_without_consent_or_outcome_settings_adds_no_flags(self, tmp_path):
        settings = _page_settings(tmp_path, "a")

        report_data = enumerator_report_data(CONSENT_DATA, settings)

        assert report_data.columns == CONSENT_DATA.columns

    def test_column_without_values_adds_no_flag(self, tmp_path):
        settings = _page_settings(
            tmp_path, "a", {"consent": "consent", "consent_vals": []}
        )

        report_data = enumerator_report_data(CONSENT_DATA, settings)

        assert "consent_granted_agg_col" not in report_data.columns

    def test_column_missing_from_the_data_adds_no_flag(self, tmp_path):
        settings = _page_settings(tmp_path, "a", CONSENT_YES_DONE)

        report_data = enumerator_report_data(CONSENT_DATA.drop("outcome"), settings)

        assert "consent_granted_agg_col" in report_data.columns
        assert "completed_survey_agg_col" not in report_data.columns

    def test_reflects_settings_changed_since_the_last_report(self, tmp_path):
        settings = _page_settings(tmp_path, "a", CONSENT_YES_DONE)
        enumerator_report_data(CONSENT_DATA, settings)

        _page_settings(tmp_path, "a", {**CONSENT_YES_DONE, "consent_vals": ["no"]})
        report_data = enumerator_report_data(CONSENT_DATA, settings)

        assert report_data["consent_granted_agg_col"].to_list() == [0, 1, 0, 0]

    def test_reflects_refreshed_data(self, tmp_path):
        settings = _page_settings(tmp_path, "a", CONSENT_YES_DONE)
        enumerator_report_data(CONSENT_DATA, settings)

        refreshed = pl.concat(
            [
                CONSENT_DATA,
                pl.DataFrame(
                    {"enumerator": ["E3"], "consent": ["no"], "outcome": ["done"]}
                ),
            ]
        )
        report_data = enumerator_report_data(refreshed, settings)

        assert report_data["consent_granted_agg_col"].to_list() == [1, 0, 1, 1, 0]

    def test_pages_with_different_settings_report_independently(self, tmp_path):
        page_a = _page_settings(tmp_path, "a", CONSENT_YES_DONE)
        page_b = _page_settings(
            tmp_path, "b", {**CONSENT_YES_DONE, "consent_vals": ["no"]}
        )

        data_a = enumerator_report_data(CONSENT_DATA, page_a)
        data_b = enumerator_report_data(CONSENT_DATA, page_b)

        assert data_a["consent_granted_agg_col"].to_list() == [1, 0, 1, 1]
        assert data_b["consent_granted_agg_col"].to_list() == [0, 1, 0, 0]
