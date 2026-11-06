"""Tests for the progress module with comprehensive coverage."""

import datetime
import json
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from pydantic import ValidationError

from datasure.checks import progress as progress_module
from datasure.checks.progress import (
    ProgressSettings,
    TimePeriodConfig,
    _get_unique_values,
    compute_counts,
    compute_progress,
    display_overview,
    display_progress_header,
    load_default_settings,
    progress_fraction,
    progress_report,
    progress_report_settings,
    short_date,
)
from datasure.utils.dataframe_utils import ColumnByType


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests.
    """
    pass


# ==============================================================================
# UI Test Helpers and Fixtures
# ==============================================================================


def _make_mock_st():
    """Create a mock Streamlit module for progress UI tests."""

    def make_col():
        col = MagicMock()
        col.selectbox.return_value = None
        col.number_input.return_value = 0
        col.multiselect.return_value = []
        return col

    def _col_factory(*args, **kwargs):
        n_or_spec = args[0] if args else kwargs.get("spec", kwargs.get("n_or_spec", 2))
        if isinstance(n_or_spec, int):
            n = n_or_spec
        elif isinstance(n_or_spec, list | tuple):
            n = len(n_or_spec)
        else:
            n = 2
        return tuple(make_col() for _ in range(n))

    mock_st = MagicMock()
    mock_st.fragment = lambda func: func
    mock_st.columns.side_effect = _col_factory
    mock_st.selectbox.return_value = None
    mock_st.multiselect.return_value = []
    mock_st.number_input.return_value = 0
    mock_st.date_input.return_value = None
    mock_st.pills.return_value = "Day"
    mock_st.segmented_control.return_value = "Cumulative"
    mock_st.tabs.side_effect = lambda names, **kwargs: [MagicMock() for _ in names]
    mock_st.button.return_value = False
    mock_st.session_state = {}
    return mock_st


@pytest.fixture
def patched_progress():
    mock_st = _make_mock_st()
    with (
        patch("datasure.checks.progress.st", mock_st),
        patch("datasure.utils.onboarding_utils.is_demo_project", return_value=False),
        patch("datasure.checks.progress.load_check_settings", return_value={}),
        patch("datasure.checks.progress.save_check_settings"),
        patch("datasure.checks.progress.trigger_save"),
        patch("datasure.checks.progress.demo_callout"),
        patch("datasure.checks.progress.metric_row"),
        patch("datasure.checks.progress.section_header"),
    ):
        yield mock_st


# ==============================================================================
# New Tests for Pydantic Models and Helper Functions
# ==============================================================================


class TestPydanticModels:
    """Test Pydantic models for data validation."""

    def test_progress_settings_valid(self):
        """Test creating valid ProgressSettings."""
        settings = ProgressSettings(
            survey_key="key_col",
            survey_id="id_col",
            survey_date="date_col",
            survey_target=1000,
            target_submissions_per_period=50,
        )
        assert settings.survey_key == "key_col"
        assert settings.survey_id == "id_col"
        assert settings.survey_target == 1000

    def test_progress_settings_negative_target(self):
        """Test ProgressSettings rejects negative targets."""
        with pytest.raises(ValidationError):
            ProgressSettings(survey_key="key", survey_id="id", survey_target=-10)

    def test_time_period_config_valid(self):
        """Test creating valid TimePeriodConfig."""
        for period in ["Day", "Week", "Month"]:
            config = TimePeriodConfig(time_period=period)
            assert config.time_period == period

    def test_time_period_config_invalid(self):
        """Test TimePeriodConfig rejects invalid periods."""
        with pytest.raises(ValidationError):
            TimePeriodConfig(time_period="Year")


class TestHelperFunctions:
    """Test helper functions."""

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_get_unique_values(self):
        """Test _get_unique_values helper."""
        data = pl.DataFrame({"col1": ["A", "B", "A", "C", "B"]})
        unique_vals = _get_unique_values(data, "col1")

        assert isinstance(unique_vals, list)
        assert set(unique_vals) == {"A", "B", "C"}
        assert len(unique_vals) == 3


# ==============================================================================
# New UI Coverage Tests
# ==============================================================================


def test_load_default_settings_basic(patched_progress):
    """load_default_settings merges saved and default config."""
    config = ProgressSettings(survey_id="id_col")
    with patch(
        "datasure.checks.progress.load_check_settings",
        return_value={"survey_id": "id_col", "survey_key": "key_col"},
    ):
        result = load_default_settings("settings.json", config)
    assert isinstance(result, ProgressSettings)


def test_progress_report_settings_renders(patched_progress):
    """The settings expander renders and returns ProgressSettings."""
    data = pl.DataFrame({"survey_id": ["h1"], "consent": ["yes"]})
    patched_progress.selectbox.return_value = "survey_id"
    with patch(
        "datasure.checks.progress.load_default_settings",
        return_value=ProgressSettings(survey_id=None),
    ):
        result = progress_report_settings(
            data, "settings.json", ProgressSettings(survey_id=None), ["survey_id"], []
        )
    assert isinstance(result, ProgressSettings)
    patched_progress.expander.assert_called_once()
    patched_progress.date_input.assert_called()


def test_condition_pickers_offer_only_categorical_columns(patched_progress):
    """A date column's values can't be saved as JSON, so none is offered."""
    data = pl.DataFrame(
        {
            "hhid": ["h1"],
            "consent": ["yes"],
            "when": [datetime.date(2026, 10, 12)],
        }
    )
    categorical = ["hhid", "consent"]
    patched_progress.selectbox.return_value = "hhid"
    patched_progress.multiselect.return_value = []

    with patch(
        "datasure.checks.progress.load_default_settings",
        return_value=ProgressSettings(survey_id=None),
    ):
        progress_module._settings_sections(
            data,
            "settings.json",
            ProgressSettings(survey_id=None),
            categorical,
            ["when"],
        )

    pickers = {
        c.kwargs["key"]: c.kwargs["options"]
        for c in patched_progress.selectbox.call_args_list
    }
    assert pickers["consent_progress"] == categorical
    assert pickers["outcome_progress"] == categorical


class TestConditionValuesSaved:
    """The saved condition values match the ones the page applies."""

    def _render(self, mock_st, settings_file, column, picked, saved):
        """Render the consent picker with the column and values chosen."""
        mock_st.selectbox.return_value = column
        mock_st.multiselect.return_value = picked
        return progress_module._render_condition_part(
            SURVEY,
            str(settings_file),
            "consent",
            "Consent column",
            ["hhid", "consent", "outcome"],
            saved["consent"],
            saved["consent_vals"],
            "help",
        )

    @pytest.fixture
    def real_saving(self, patched_progress, tmp_path):
        """Save to a real settings file, sharing session state with the page."""
        from datasure.utils import settings_utils

        settings_file = tmp_path / "settings.json"
        with (
            patch.object(
                settings_utils.st, "session_state", patched_progress.session_state
            ),
            patch(
                "datasure.checks.progress.save_check_settings",
                settings_utils.save_check_settings,
            ),
        ):
            yield patched_progress, settings_file

    def _saved(self, settings_file):
        return json.loads(settings_file.read_text())["progress"]

    def test_changing_the_column_saves_the_values_kept_for_it(self, real_saving):
        mock_st, settings_file = real_saving
        saved = {"consent": "consent", "consent_vals": ["yes"]}
        settings_file.write_text(json.dumps({"progress": saved}))
        mock_st.session_state["consent_vals_progress"] = ["yes"]
        # The user picks the outcome column, which has no "yes"
        mock_st.session_state["progress_consent"] = True

        self._render(mock_st, settings_file, "outcome", [], saved)

        assert self._saved(settings_file) == {"consent": "outcome", "consent_vals": []}
        assert "consent_vals_progress" not in mock_st.session_state
        assert mock_st.multiselect.call_args.kwargs["default"] is None

    def test_values_missing_from_the_data_stay_selected_and_saved(self, real_saving):
        # A refresh with no "maybe" rows must not drop "maybe" from the
        # condition: with no values left, every ID would count as completed.
        mock_st, settings_file = real_saving
        saved = {"consent": "consent", "consent_vals": ["yes", "maybe"]}
        settings_file.write_text(json.dumps({"progress": saved}))

        self._render(mock_st, settings_file, "consent", ["yes", "maybe"], saved)

        picker = mock_st.multiselect.call_args.kwargs
        assert picker["options"] == ["yes", "no", "maybe"]
        assert picker["default"] == ["yes", "maybe"]
        assert self._saved(settings_file) == saved

    def test_unchanged_values_are_not_saved_again(self, real_saving):
        mock_st, settings_file = real_saving
        saved = {"consent": "consent", "consent_vals": ["yes"]}
        settings_file.write_text(json.dumps({"progress": saved}))
        before = settings_file.stat().st_mtime_ns

        self._render(mock_st, settings_file, "consent", ["yes"], saved)

        assert settings_file.stat().st_mtime_ns == before
        assert "consent_vals_progress" not in mock_st.session_state


@pytest.mark.parametrize("survey_target", [None, 10])
def test_display_progress_header_renders(patched_progress, survey_target):
    """The header renders with and without a target."""
    settings = _settings(survey_target=survey_target, target_submissions_per_period=2)
    result = compute_progress(
        _daily({"2026-10-12": 2, "2026-10-13": 2, "2026-10-14": 2}), settings, AS_OF
    )

    display_progress_header(result, settings)

    progress_module.metric_row.assert_called_once()
    labels = [m[0] for m in progress_module.metric_row.call_args.args[0]]
    if survey_target is None:
        # No headline: Completed moves into the strip
        assert "Completed" in labels
        patched_progress.progress.assert_not_called()
    else:
        assert "Completed" not in labels
        assert "Pace" in labels


def test_display_progress_header_draws_the_status(patched_progress):
    """The status box uses the status level, beside the progress bar."""
    settings = _settings(survey_target=30, field_end_date=datetime.date(2026, 10, 20))
    result = compute_progress(TestPace.DATA, settings, AS_OF)
    headline, status_col = MagicMock(), MagicMock()
    patched_progress.columns.side_effect = [(headline, status_col)]

    display_progress_header(result, settings)

    patched_progress.progress.assert_called_once_with(0.5)
    status_col.warning.assert_called_once()
    assert "Behind schedule" in status_col.warning.call_args.args[0]
    labels = [m[0] for m in progress_module.metric_row.call_args.args[0]]
    assert labels[-1] == "Days left"


@pytest.mark.parametrize("chart_view", ["Cumulative", "Per period"])
def test_display_overview_draws_the_chart(patched_progress, chart_view):
    settings = _settings(
        survey_target=30,
        target_submissions_per_period=2,
        field_end_date=datetime.date(2026, 10, 31),
    )
    result = compute_progress(SURVEY, settings, AS_OF)

    display_overview(result, settings, chart_view)

    patched_progress.plotly_chart.assert_called_once()


def test_display_overview_without_dates_explains_the_chart(patched_progress):
    settings = _settings(survey_date=None)

    display_overview(compute_progress(SURVEY, settings, AS_OF), settings, "Cumulative")

    patched_progress.info.assert_called()
    patched_progress.plotly_chart.assert_not_called()


def test_progress_report_renders_settings_header_and_tabs(patched_progress, tmp_path):
    """The page draws the settings, then Overview and Follow-up tabs."""
    survey_cols = ColumnByType(categorical_columns=["hhid"], datetime_columns=["when"])
    with (
        patch(
            "datasure.checks.progress.progress_report_settings",
            return_value=_settings(survey_target=10),
        ) as settings,
        patch("datasure.checks.progress.display_progress_header") as header,
        patch("datasure.checks.progress.display_overview") as overview,
        patch("datasure.checks.progress.display_follow_up") as follow_up,
    ):
        progress_report(
            SURVEY, str(tmp_path / "settings.json"), {"survey_id": "hhid"}, survey_cols
        )

    names = patched_progress.tabs.call_args.args[0]
    assert names == ["Overview", "Follow-up"]
    settings.assert_called_once()
    assert patched_progress.tabs.call_args.kwargs["key"] == "progress_tab"
    header.assert_called_once()
    overview.assert_called_once()
    follow_up.assert_called_once()


def test_stale_condition_columns_lists_saved_columns_no_longer_offered():
    saved = _settings(consent="consent", outcome="gone")

    assert progress_module.stale_condition_columns(saved, ["hhid", "consent"]) == [
        "gone"
    ]
    assert progress_module.stale_condition_columns(_settings(), ["hhid"]) == []


def test_progress_report_warns_about_a_saved_column_no_longer_in_the_data(
    patched_progress, tmp_path
):
    """A prep step removed the outcome column: the page says so."""
    settings_file = tmp_path / "settings.json"
    survey_cols = ColumnByType(categorical_columns=["hhid"], datetime_columns=["when"])
    with (
        patch(
            "datasure.checks.progress.load_check_settings",
            return_value={"outcome": "old_outcome", "outcome_vals": ["complete"]},
        ),
        patch(
            "datasure.checks.progress.progress_report_settings",
            return_value=_settings(survey_target=10),
        ),
        patch("datasure.checks.progress.display_progress_header"),
        patch("datasure.checks.progress.display_overview"),
        patch("datasure.checks.progress.display_follow_up"),
    ):
        progress_report(SURVEY, str(settings_file), {"survey_id": "hhid"}, survey_cols)

    patched_progress.warning.assert_called_once()
    assert "**old_outcome**" in patched_progress.warning.call_args.args[0]


# ==============================================================================
# Saved targets load back (#407)
# ==============================================================================


class TestSavedTargetsLoadBack:
    """Targets saved on the Progress page load back on the next visit."""

    CONFIG = ProgressSettings(
        survey_key="key", survey_id="survey_id", survey_target=100
    )

    @staticmethod
    def _edit_targets(settings_file, target, target_per_period):
        """Render the settings with the user entering both targets.

        Each edited widget fires its on_change callback, which flags its
        value for saving, the way Streamlit does on a real edit.
        """
        session_state = {}
        entered = {
            "total_goal_progress": target,
            "target_per_period_progress": target_per_period,
        }

        def number_input(*args, **kwargs):
            session_state[kwargs["kwargs"]["state_name"]] = True
            return entered[kwargs["key"]]

        mock_st = _make_mock_st()
        mock_st.number_input.side_effect = number_input
        mock_st.selectbox.side_effect = lambda *args, **kwargs: kwargs["options"][0]
        mock_st.session_state = session_state
        mock_settings_st = MagicMock()
        mock_settings_st.session_state = session_state
        with (
            patch("datasure.checks.progress.st", mock_st),
            patch("datasure.utils.settings_utils.st", mock_settings_st),
            patch(
                "datasure.utils.onboarding_utils.is_demo_project", return_value=False
            ),
            patch("datasure.checks.progress.demo_callout"),
        ):
            progress_report_settings(
                pl.DataFrame({"survey_id": ["h1"]}),
                str(settings_file),
                TestSavedTargetsLoadBack.CONFIG,
                ["survey_id"],
                ["date"],
            )

    def test_targets_entered_on_the_page_load_back(self, tmp_path):
        settings_file = tmp_path / "page_settings.json"

        self._edit_targets(settings_file, target=250, target_per_period=12)
        loaded = load_default_settings(str(settings_file), self.CONFIG)

        assert loaded.survey_target == 250
        assert loaded.target_submissions_per_period == 12

    def test_targets_saved_under_the_old_keys_still_load(self, tmp_path):
        settings_file = tmp_path / "page_settings.json"
        settings_file.write_text(
            json.dumps({"progress": {"target": 250, "target_per_period": 12}})
        )
        config = self.CONFIG.model_copy(update={"survey_target": None})

        loaded = load_default_settings(str(settings_file), config)

        assert loaded.survey_target == 250
        assert loaded.target_submissions_per_period == 12

    def test_page_config_target_beats_a_target_saved_under_the_old_key(self, tmp_path):
        # The old key never took effect, so the page config's target may be
        # the newer one: users were told to set it there instead
        settings_file = tmp_path / "page_settings.json"
        settings_file.write_text(
            json.dumps({"progress": {"target": 250, "target_per_period": 12}})
        )

        loaded = load_default_settings(str(settings_file), self.CONFIG)

        assert loaded.survey_target == 100
        assert loaded.target_submissions_per_period == 12

    def test_page_config_target_is_used_when_no_target_is_saved(self, tmp_path):
        settings_file = tmp_path / "page_settings.json"
        settings_file.write_text(json.dumps({"progress": {"enumerator": "enum"}}))

        loaded = load_default_settings(str(settings_file), self.CONFIG)

        assert loaded.survey_target == 100
        assert loaded.target_submissions_per_period is None


# ==============================================================================
# compute_progress (#408)
# ==============================================================================

AS_OF = datetime.date(2026, 10, 14)  # a Wednesday


def _survey(rows: list[tuple]) -> pl.DataFrame:
    """Survey rows of (id, date, consent, outcome); dates are ISO text."""
    return pl.DataFrame(
        rows,
        schema={
            "hhid": pl.String,
            "when": pl.String,
            "consent": pl.String,
            "outcome": pl.String,
        },
        orient="row",
    )


def _settings(**overrides) -> ProgressSettings:
    values = {"survey_id": "hhid", "survey_date": "when", **overrides}
    return ProgressSettings(**values)


CONDITION = {
    "consent": "consent",
    "consent_vals": ["yes"],
    "outcome": "outcome",
    "outcome_vals": ["complete"],
}

# h1 is submitted twice, h2 refused, h3 completed on its second try.
SURVEY = _survey(
    [
        ("h1", "2026-10-12", "yes", "complete"),
        ("h1", "2026-10-13", "yes", "complete"),
        ("h2", "2026-10-12", "no", "refused"),
        ("h3", "2026-10-12", "yes", "partial"),
        ("h3", "2026-10-14", "yes", "complete"),
    ]
)


class TestComputeProgressCounts:
    def test_without_a_condition_completed_is_unique(self):
        result = compute_progress(SURVEY, _settings(survey_target=10), AS_OF)

        counts = result.counts
        assert (counts.submissions, counts.unique, counts.completed) == (5, 3, 3)
        assert counts.remaining == 7
        assert counts.percentage == 30.0

    def test_completed_counts_ids_with_a_row_meeting_the_condition(self):
        # h1 counts once despite two qualifying rows; h2 never qualifies;
        # h3 qualifies on its second row.
        result = compute_progress(
            SURVEY, _settings(survey_target=4, **CONDITION), AS_OF
        )

        counts = result.counts
        assert (counts.submissions, counts.unique, counts.completed) == (5, 3, 2)
        assert counts.remaining == 2
        assert counts.percentage == 50.0

    def test_both_consent_and_outcome_must_hold(self):
        data = _survey(
            [
                ("h1", "2026-10-12", "no", "complete"),
                ("h2", "2026-10-12", "yes", "refused"),
                ("h3", "2026-10-12", "yes", "complete"),
            ]
        )

        result = compute_progress(data, _settings(**CONDITION), AS_OF)

        assert result.counts.completed == 1

    def test_a_consent_column_alone_is_a_condition(self):
        settings = _settings(consent="consent", consent_vals=["yes"])

        assert compute_progress(SURVEY, settings, AS_OF).counts.completed == 2

    def test_a_selected_null_value_matches_null_rows(self):
        data = _survey(
            [
                ("h1", "2026-10-12", "yes", None),
                ("h2", "2026-10-12", "yes", "refused"),
            ]
        )
        settings = _settings(outcome="outcome", outcome_vals=[None])

        assert compute_progress(data, settings, AS_OF).counts.completed == 1

    def test_an_unselected_null_value_does_not_match(self):
        data = _survey([("h1", "2026-10-12", "yes", None)])
        settings = _settings(outcome="outcome", outcome_vals=["complete"])

        assert compute_progress(data, settings, AS_OF).counts.completed == 0

    def test_a_column_without_values_sets_no_condition(self):
        settings = _settings(consent="consent", consent_vals=[])

        assert compute_progress(SURVEY, settings, AS_OF).counts.completed == 3

    def test_no_target_leaves_remaining_and_percentage_unset(self):
        counts = compute_progress(SURVEY, _settings(), AS_OF).counts

        assert (counts.target, counts.remaining, counts.percentage) == (
            None,
            None,
            None,
        )

    def test_remaining_stops_at_zero_past_the_target(self):
        counts = compute_progress(SURVEY, _settings(survey_target=2), AS_OF).counts

        assert counts.remaining == 0
        assert counts.percentage == 150.0


def _points(series) -> list[tuple]:
    return [(p.start, p.completed, p.cumulative, p.partial) for p in series]


class TestComputeProgressSeries:
    def test_each_id_counts_in_the_day_of_its_first_qualifying_row(self):
        # h1 first qualifies on the 12th, h3 only on the 14th (today).
        result = compute_progress(SURVEY, _settings(**CONDITION), AS_OF)

        assert _points(result.series) == [
            (datetime.date(2026, 10, 12), 1, 1, False),
            (datetime.date(2026, 10, 13), 0, 1, False),
            (datetime.date(2026, 10, 14), 1, 2, True),
        ]

    def test_ends_at_the_last_submission_not_today(self):
        # Submissions stopped on the 12th; today, the 14th, is not drawn.
        data = _survey([("h1", "2026-10-11", "yes", "complete")])
        data = pl.concat([data, _survey([("h2", "2026-10-12", "no", "refused")])])

        result = compute_progress(data, _settings(**CONDITION), AS_OF)

        assert _points(result.series) == [
            (datetime.date(2026, 10, 11), 1, 1, False),
            (datetime.date(2026, 10, 12), 0, 1, False),
        ]

    def test_ends_at_the_month_of_the_last_submission(self):
        # The last submission is in September, so October is not drawn.
        data = _survey(
            [
                ("h1", "2026-08-20", "yes", "complete"),
                ("h2", "2026-09-03", "yes", "complete"),
            ]
        )

        result = compute_progress(data, _settings(), AS_OF, period="Month")

        assert _points(result.series) == [
            (datetime.date(2026, 8, 1), 1, 1, False),
            (datetime.date(2026, 9, 1), 1, 2, False),
        ]

    def test_days_without_completions_between_submissions_count_zero(self):
        data = _survey(
            [
                ("h1", "2026-10-11", "yes", "complete"),
                ("h2", "2026-10-13", "yes", "complete"),
            ]
        )

        result = compute_progress(data, _settings(), AS_OF)

        assert _points(result.series) == [
            (datetime.date(2026, 10, 11), 1, 1, False),
            (datetime.date(2026, 10, 12), 0, 1, False),
            (datetime.date(2026, 10, 13), 1, 2, False),
        ]

    def test_weeks_start_on_monday(self):
        data = _survey(
            [
                ("h1", "2026-10-04", "yes", "complete"),  # a Sunday
                ("h2", "2026-10-05", "yes", "complete"),
                ("h3", "2026-10-14", "yes", "complete"),
            ]
        )

        result = compute_progress(data, _settings(), AS_OF, period="Week")

        assert _points(result.series) == [
            (datetime.date(2026, 9, 28), 1, 1, False),
            (datetime.date(2026, 10, 5), 1, 2, False),
            (datetime.date(2026, 10, 12), 1, 3, True),
        ]

    def test_months(self):
        data = _survey(
            [
                ("h1", "2026-09-30", "yes", "complete"),
                ("h2", "2026-10-01", "yes", "complete"),
            ]
        )

        result = compute_progress(data, _settings(), AS_OF, period="Month")

        assert _points(result.series) == [
            (datetime.date(2026, 9, 1), 1, 1, False),
            (datetime.date(2026, 10, 1), 1, 2, True),
        ]

    def test_undated_rows_count_but_are_not_drawn(self):
        data = _survey(
            [("h1", "2026-10-14", "yes", "complete"), ("h2", None, "yes", "complete")]
        )

        result = compute_progress(data, _settings(), AS_OF)

        assert result.counts.completed == 2
        assert _points(result.series) == [(datetime.date(2026, 10, 14), 1, 1, True)]

    def test_no_series_without_a_date_column(self):
        result = compute_progress(SURVEY, _settings(survey_date=None), AS_OF)

        assert result.series == []


class TestCurrentPeriod:
    # One completion on the 5th (last week), two this week, one today.
    DATA = _survey(
        [
            ("h1", "2026-10-05", "yes", "complete"),
            ("h2", "2026-10-12", "yes", "complete"),
            ("h3", "2026-10-14", "yes", "complete"),
        ]
    )

    @pytest.mark.parametrize(
        ("period", "start", "completed"),
        [
            ("Day", datetime.date(2026, 10, 14), 1),
            ("Week", datetime.date(2026, 10, 12), 2),
            ("Month", datetime.date(2026, 10, 1), 3),
        ],
    )
    def test_follows_the_selected_period(self, period, start, completed):
        settings = _settings(target_submissions_per_period=5)

        current = compute_progress(self.DATA, settings, AS_OF, period).current_period

        assert (current.period, current.start) == (period, start)
        assert (current.completed, current.target) == (completed, 5)

    def test_a_period_without_completions_counts_zero(self):
        settings = _settings(target_submissions_per_period=5)
        later = datetime.date(2026, 10, 20)

        current = compute_progress(self.DATA, settings, later).current_period

        assert current.completed == 0

    def test_hidden_without_a_per_period_target(self):
        assert compute_progress(self.DATA, _settings(), AS_OF).current_period is None

    def test_hidden_without_a_date_column(self):
        settings = _settings(survey_date=None, target_submissions_per_period=5)

        assert compute_progress(self.DATA, settings, AS_OF).current_period is None


def _daily(days: dict[str, int]) -> pl.DataFrame:
    """Completed IDs per ISO date, each with its own ID."""
    rows = [
        (f"{day}-{n}", day, "yes", "complete")
        for day, count in days.items()
        for n in range(count)
    ]
    return _survey(rows)


class TestPace:
    # One completion on 1 Oct, then 2 a day over the 7 days to today: 15
    # completed, a pace of 2 a day.
    DATA = _daily(
        {"2026-10-01": 1, **{f"2026-10-{day:02d}": 2 for day in range(8, 15)}}
    )

    def test_projected_finish_uses_the_mean_of_the_last_7_days(self):
        # 15 remaining at 2 a day is 8 days, today the first of them.
        pace = compute_progress(self.DATA, _settings(survey_target=30), AS_OF).pace

        assert pace.per_day == 2.0
        assert pace.projected_finish == datetime.date(2026, 10, 21)

    def test_a_shorter_fieldwork_averages_over_its_own_days(self):
        data = _daily({"2026-10-12": 1, "2026-10-13": 2, "2026-10-14": 3})

        pace = compute_progress(data, _settings(survey_target=12), AS_OF).pace

        assert pace.per_day == 2.0
        assert pace.projected_finish == datetime.date(2026, 10, 16)

    def test_no_projection_with_fewer_than_3_days_of_data(self):
        data = _daily({"2026-10-13": 5, "2026-10-14": 5})

        pace = compute_progress(data, _settings(survey_target=30), AS_OF).pace

        assert pace.projected_finish is None

    def test_the_window_ends_at_the_last_submission_not_today(self):
        # Submissions stopped on 3 Oct: the pace is 1 a day over 1-3 Oct, and
        # the 27 remaining are projected from today, counting today.
        data = _daily({"2026-10-01": 1, "2026-10-02": 1, "2026-10-03": 1})

        pace = compute_progress(data, _settings(survey_target=30), AS_OF).pace

        assert pace.per_day == 1.0
        assert pace.projected_finish == datetime.date(2026, 11, 9)

    def test_no_projection_without_completions_in_the_last_7_days(self):
        # Completions stop on 3 Oct, but submissions go on to today.
        completions = _daily({"2026-10-01": 1, "2026-10-02": 1, "2026-10-03": 1})
        refusals = _survey(
            [(f"r{day}", f"2026-10-{day}", "no", "refused") for day in (12, 13, 14)]
        )
        data = pl.concat([completions, refusals])
        settings = _settings(survey_target=30, **CONDITION)

        pace = compute_progress(data, settings, AS_OF).pace

        assert pace.per_day == 0
        assert pace.projected_finish is None

    def test_no_projection_once_the_target_is_reached(self):
        pace = compute_progress(self.DATA, _settings(survey_target=15), AS_OF).pace

        assert pace.projected_finish is None

    def test_no_projection_without_a_target(self):
        assert (
            compute_progress(self.DATA, _settings(), AS_OF).pace.projected_finish
            is None
        )

    def test_need_per_day_is_remaining_over_the_days_left(self):
        # 15 remaining over the 10 days from today to 23 Oct.
        settings = _settings(
            survey_target=30, field_end_date=datetime.date(2026, 10, 23)
        )

        pace = compute_progress(self.DATA, settings, AS_OF).pace

        assert pace.days_left == 10
        assert pace.need_per_day == 1.5

    def test_no_need_per_day_once_the_target_is_reached(self):
        settings = _settings(
            survey_target=15, field_end_date=datetime.date(2026, 10, 23)
        )

        assert compute_progress(self.DATA, settings, AS_OF).pace.need_per_day is None

    def test_no_need_per_day_without_an_end_date(self):
        pace = compute_progress(self.DATA, _settings(survey_target=30), AS_OF).pace

        assert pace.need_per_day is None

    def test_no_need_per_day_after_the_end_date(self):
        settings = _settings(
            survey_target=30, field_end_date=datetime.date(2026, 10, 13)
        )

        pace = compute_progress(self.DATA, settings, AS_OF).pace

        assert pace.days_left == 0
        assert pace.need_per_day is None


class TestFutureDates:
    """A submission dated after today, such as from a device with a wrong clock."""

    # Two completions this week up to today, one later this week (Friday)
    # and one dated 2099
    DATA = _daily({"2026-10-12": 1, "2026-10-14": 1, "2026-10-16": 1, "2099-01-01": 1})

    def _result(self, **overrides):
        settings = _settings(**{"target_submissions_per_period": 5, **overrides})
        return compute_progress(self.DATA, settings, AS_OF, "Week")

    def test_counts_as_completed(self):
        assert self._result().counts.completed == 4

    def test_the_series_ends_at_the_current_period(self):
        series = self._result().series

        assert [p.start for p in series] == [datetime.date(2026, 10, 12)]
        assert series[-1].partial
        assert series[-1].completed == 2

    def test_left_out_of_the_current_period(self):
        assert self._result().current_period.completed == 2

    def test_only_future_dates_give_no_series(self):
        data = _daily({"2099-01-01": 2})

        result = compute_progress(data, _settings(), AS_OF)

        assert result.series == []
        assert result.counts.completed == 2


def test_compute_counts_matches_compute_progress():
    settings = _settings(survey_target=10, **CONDITION)

    assert compute_counts(SURVEY, settings) == (
        compute_progress(SURVEY, settings, AS_OF).counts
    )


def test_progress_headline_does_not_build_the_series(tmp_path):
    """Summary needs only the counts, so a stretched series can't slow it."""
    with patch("datasure.checks.progress._series") as series:
        headline = progress_module.progress_headline(
            SURVEY,
            str(tmp_path / "settings.json"),
            {"survey_key": "hhid", "survey_id": "hhid", "survey_date": "when"},
        )

    series.assert_not_called()
    assert headline.count == 3


class TestStatus:
    """The header's on-time status, with TestPace's 2 completions a day."""

    DATA = TestPace.DATA

    def _status(self, **overrides):
        settings = _settings(**{"survey_target": 30, **overrides})
        return compute_progress(self.DATA, settings, AS_OF).status

    def test_none_without_a_target(self):
        assert compute_progress(self.DATA, _settings(), AS_OF).status is None

    def test_target_reached(self):
        status = self._status(survey_target=15)

        assert (status.level, status.title) == ("success", "Target reached")

    def test_without_an_end_date_shows_the_projected_finish(self):
        status = self._status()

        assert status.level == "info"
        assert status.title == "Projected finish: Wed 21 Oct"
        assert "field end date" in status.message

    def test_on_track_counts_the_days_before_the_end_date(self):
        status = self._status(field_end_date=datetime.date(2026, 10, 22))

        assert (status.level, status.title) == ("success", "On track to finish on time")
        assert "1 day before the field end date (Thu 22 Oct)" in status.message

    def test_finishing_on_the_end_date_is_on_track(self):
        status = self._status(field_end_date=datetime.date(2026, 10, 21))

        assert status.level == "success"
        assert "on the field end date (Wed 21 Oct)" in status.message

    def test_exactly_the_pace_needed_is_on_track(self):
        # 14 remaining over the 7 days from today to 20 Oct needs 2 a day,
        # the pace: the days left and the projection both count today.
        status = self._status(
            survey_target=29, field_end_date=datetime.date(2026, 10, 20)
        )

        assert (status.level, status.title) == ("success", "On track to finish on time")
        assert "on the field end date (Tue 20 Oct)" in status.message

    def test_behind_counts_the_days_after_and_the_pace_needed(self):
        # 15 remaining over the 7 days from today to 20 Oct: 2.1 a day.
        status = self._status(field_end_date=datetime.date(2026, 10, 20))

        assert (status.level, status.title) == ("warning", "Behind schedule")
        assert "1 day after the field end date (Tue 20 Oct)" in status.message
        assert "**2.1 a day**" in status.message

    def test_field_end_date_passed(self):
        status = self._status(field_end_date=datetime.date(2026, 10, 13))

        assert (status.level, status.title) == ("warning", "Field end date passed")
        assert "**15** completions to go" in status.message

    def test_too_little_data(self):
        data = _daily({"2026-10-13": 5, "2026-10-14": 5})

        status = compute_progress(data, _settings(survey_target=30), AS_OF).status

        assert status.level == "info"
        assert status.title == "Not enough data for a projected finish"

    def test_no_recent_completions(self):
        completions = _daily({"2026-10-01": 1, "2026-10-02": 1, "2026-10-03": 1})
        refusals = _survey(
            [(f"r{day}", f"2026-10-{day}", "no", "refused") for day in (12, 13, 14)]
        )
        settings = _settings(survey_target=30, **CONDITION)

        status = compute_progress(
            pl.concat([completions, refusals]), settings, AS_OF
        ).status

        assert (status.level, status.title) == (
            "warning",
            "No completions in the last 7 days",
        )


@pytest.mark.parametrize(
    ("percentage", "fraction"), [(0, 0.0), (45.5, 0.455), (100, 1.0), (180, 1.0)]
)
def test_progress_fraction_stays_within_what_st_progress_accepts(percentage, fraction):
    assert progress_fraction(percentage) == pytest.approx(fraction)


def test_display_progress_header_past_the_target(patched_progress):
    """More completions than the target: the bar stops full, the text says so."""
    settings = _settings(survey_target=10)
    result = compute_progress(TestPace.DATA, settings, AS_OF)  # 15 completed

    display_progress_header(result, settings)

    patched_progress.progress.assert_called_once_with(1.0)
    text = patched_progress.markdown.call_args.args[0]
    assert "150.0% complete" in text
    assert "target reached" in text


def test_short_date_adds_the_year_only_when_it_differs():
    assert short_date(datetime.date(2026, 11, 16), AS_OF) == "Mon 16 Nov"
    assert short_date(datetime.date(2027, 1, 4), AS_OF) == "Mon 4 Jan 2027"


class TestTargetPath:
    DATA = _daily({"2026-10-12": 1, "2026-10-14": 1})

    def test_runs_from_zero_to_the_target_by_the_field_end_date(self):
        settings = _settings(
            survey_target=30, field_end_date=datetime.date(2026, 10, 31)
        )

        path = compute_progress(self.DATA, settings, AS_OF).target_path

        assert path == [
            (datetime.date(2026, 10, 12), 0),
            (datetime.date(2026, 10, 31), 30),
        ]

    def test_is_flat_without_an_end_date(self):
        path = compute_progress(
            self.DATA, _settings(survey_target=30), AS_OF
        ).target_path

        assert path == [
            (datetime.date(2026, 10, 12), 30),
            (datetime.date(2026, 10, 14), 30),
        ]

    def test_is_flat_when_the_end_date_is_before_the_first_period(self):
        # Fieldwork started late: the line must not run back to the end date.
        settings = _settings(
            survey_target=30, field_end_date=datetime.date(2026, 10, 10)
        )

        path = compute_progress(self.DATA, settings, AS_OF).target_path

        assert path == [
            (datetime.date(2026, 10, 12), 30),
            (datetime.date(2026, 10, 14), 30),
        ]

    def test_none_without_a_target(self):
        assert compute_progress(self.DATA, _settings(), AS_OF).target_path == []


class TestTargetLine:
    def test_one_period_without_an_end_date_spans_the_chart(self):
        # Both target points share the first day: a line between them would
        # draw nothing.
        data = _daily({"2026-10-14": 2})
        result = compute_progress(data, _settings(survey_target=30), AS_OF)

        fig = progress_module.progress_figure(result, "Cumulative", None)

        assert [trace.name for trace in fig.data] == [
            "Completed",
            "So far (unfinished)",
        ]
        assert [shape.y0 for shape in fig.layout.shapes] == [30]

    def test_several_periods_draw_a_target_trace(self):
        data = _daily({"2026-10-12": 1, "2026-10-14": 1})
        result = compute_progress(data, _settings(survey_target=30), AS_OF)

        fig = progress_module.progress_figure(result, "Cumulative", None)

        assert "Target" in [trace.name for trace in fig.data]
        assert fig.layout.shapes == ()


class TestPageShape:
    def test_a_fixed_target_shows_overview_and_follow_up(self):
        result = compute_progress(SURVEY, _settings(survey_target=10), AS_OF)

        assert result.mode == "fixed"
        assert result.tabs == ["Overview", "Follow-up"]
        assert result.todos == []


# ==============================================================================
# Follow-up (#409)
# ==============================================================================


def _attempts(rows: list[tuple]) -> pl.DataFrame:
    """Survey rows of (id, date, consent, outcome, enumerator)."""
    return pl.DataFrame(
        rows,
        schema={
            "hhid": pl.String,
            "when": pl.String,
            "consent": pl.String,
            "outcome": pl.String,
            "enum": pl.String,
        },
        orient="row",
    )


# h1 done on its 1st try; h2 done on its 3rd; h3 open after 3 tries;
# h4 open after 1 try (a longer time ago than h5); h5 open after 1 try.
ATTEMPTS = _attempts(
    [
        ("h1", "2026-10-01", "yes", "complete", "ann"),
        ("h2", "2026-10-01", "yes", "not home", "ann"),
        ("h2", "2026-10-03", "yes", "not home", "bo"),
        ("h2", "2026-10-05", "yes", "complete", "bo"),
        ("h3", "2026-10-02", "yes", "not home", "ann"),
        ("h3", "2026-10-06", "no", "refused", "bo"),
        ("h3", "2026-10-04", "yes", "partial", "cy"),
        ("h4", "2026-10-07", "yes", "partial", "cy"),
        ("h5", "2026-10-10", "yes", "not home", "ann"),
    ]
)


def _follow_up(data=ATTEMPTS, **overrides):
    settings = _settings(enumerator="enum", **{**CONDITION, **overrides})
    return compute_progress(data, settings, AS_OF)


class TestFollowUpQueue:
    def test_lists_open_ids_by_attempts_then_days_since_the_last(self):
        queue = _follow_up().follow_up_queue

        assert [
            (
                row.id,
                row.attempts,
                row.last_outcome,
                row.last_date,
                row.days_since,
                row.last_enumerator,
            )
            for row in queue
        ] == [
            ("h3", 3, "refused", datetime.date(2026, 10, 6), 8, "bo"),
            ("h4", 1, "partial", datetime.date(2026, 10, 7), 7, "cy"),
            ("h5", 1, "not home", datetime.date(2026, 10, 10), 4, "ann"),
        ]

    def test_each_row_carries_its_attempts_in_date_order(self):
        h3 = _follow_up().follow_up_queue[0]

        assert [(a.number, a.day, a.outcome, a.enumerator) for a in h3.history] == [
            (1, datetime.date(2026, 10, 2), "not home", "ann"),
            (2, datetime.date(2026, 10, 4), "partial", "cy"),
            (3, datetime.date(2026, 10, 6), "refused", "bo"),
        ]

    def test_without_an_outcome_column_the_last_outcome_is_not_complete(self):
        data = _attempts(
            [
                ("h1", "2026-10-01", "yes", "complete", None),
                ("h2", "2026-10-01", "no", "refused", None),
                ("h2", "2026-10-02", "no", "refused", None),
            ]
        )

        queue = _follow_up(data, outcome=None, outcome_vals=None).follow_up_queue

        assert [(row.id, row.last_outcome) for row in queue] == [("h2", "not complete")]
        assert [a.outcome for a in queue[0].history] == ["not complete"] * 2

    def test_without_a_completion_condition_there_is_no_queue(self):
        settings = _settings(enumerator="enum")

        assert compute_progress(ATTEMPTS, settings, AS_OF).follow_up_queue == []

    def test_a_missing_outcome_reads_as_missing(self):
        data = _attempts([("h1", "2026-10-01", "yes", None, None)])

        (row,) = _follow_up(data).follow_up_queue

        assert (row.last_outcome, row.last_enumerator) == ("missing", None)


class TestFollowUpMetrics:
    def test_with_a_completion_condition(self):
        metrics = _follow_up().follow_up

        # Completions: h1 at attempt 1, h2 at 3. Open: h3 (3 tries), h4, h5.
        assert metrics.need_follow_up == 3
        assert metrics.first_try_rate == 50.0
        assert metrics.avg_attempts_per_completion == 2.0
        assert metrics.open_3_plus == 1

    def test_repeat_id_metrics_hold_with_or_without_a_condition(self):
        for settings in (_settings(), _settings(**CONDITION)):
            metrics = compute_progress(ATTEMPTS, settings, AS_OF).follow_up

            # h2 and h3 were each submitted 3 times; 9 submissions, 5 IDs
            assert (metrics.repeat_ids, metrics.avg_attempts, metrics.max_attempts) == (
                2,
                1.8,
                3,
            )

    def test_without_a_condition_the_follow_up_metrics_are_unset(self):
        metrics = compute_progress(ATTEMPTS, _settings(), AS_OF).follow_up

        assert (
            metrics.need_follow_up,
            metrics.first_try_rate,
            metrics.avg_attempts_per_completion,
            metrics.open_3_plus,
        ) == (None, None, None, None)

    def test_no_completions_leave_the_rates_unset(self):
        data = _attempts([("h1", "2026-10-01", "no", "refused", None)])

        metrics = _follow_up(data).follow_up

        assert (metrics.need_follow_up, metrics.first_try_rate) == (1, None)
        assert metrics.avg_attempts_per_completion is None

    def test_no_data_counts_nothing(self):
        metrics = _follow_up(ATTEMPTS.clear()).follow_up

        assert (metrics.repeat_ids, metrics.avg_attempts, metrics.max_attempts) == (
            0,
            None,
            0,
        )


class TestAttemptsToOutcome:
    def test_completed_and_still_open_at_each_attempt_number(self):
        buckets = _follow_up().attempts_to_outcome

        assert [(b.attempt, b.completed, b.open, b.submitted) for b in buckets] == [
            ("1", 1, 2, 3),
            ("2", 0, 0, 0),
            ("3", 1, 1, 2),
            ("4+", 0, 0, 0),
        ]

    def test_four_or_more_attempts_share_the_last_bucket(self):
        data = _attempts(
            [("h1", f"2026-10-0{day}", "no", "refused", None) for day in range(1, 6)]
        )

        last = _follow_up(data).attempts_to_outcome[-1]

        assert (last.attempt, last.open, last.submitted) == ("4+", 1, 1)


class TestFollowUpTodo:
    def test_open_after_three_attempts_links_to_follow_up(self):
        todos = _follow_up().todos

        assert [(t.label, t.count, t.tab) for t in todos] == [
            ("Respondents open after 3+ attempts", 1, "Follow-up")
        ]

    def test_no_card_when_none_are_open_after_three_attempts(self):
        data = ATTEMPTS.filter(pl.col("hhid") != "h3")

        assert _follow_up(data).todos == []


class TestQueueFilterAndExport:
    def test_filters_by_last_outcome_and_minimum_attempts(self):
        queue = _follow_up().follow_up_queue

        ids = progress_module.filter_queue
        assert [r.id for r in ids(queue, ["partial", "not home"], 1)] == ["h4", "h5"]
        assert [r.id for r in ids(queue, [], 2)] == ["h3"]

    def test_export_has_one_row_per_open_id_in_queue_order(self):
        frame = progress_module.queue_frame(_follow_up().follow_up_queue)

        assert frame.columns == [
            "ID",
            "Attempts",
            "Last outcome",
            "Last attempt",
            "Days since",
            "Last enumerator",
        ]
        assert frame.row(0) == (
            "h3",
            3,
            "refused",
            datetime.date(2026, 10, 6),
            8,
            "bo",
        )
        assert frame.height == 3

    def test_an_empty_queue_exports_the_columns(self):
        assert progress_module.queue_frame([]).columns[0] == "ID"


def test_the_enumerator_comes_from_the_page_config_not_old_saved_settings():
    with patch(
        "datasure.checks.progress.load_check_settings",
        return_value={"enumerator": "old_enum"},
    ):
        settings = load_default_settings("settings.json", _settings(enumerator="enum"))

    assert settings.enumerator == "enum"


# ==============================================================================
# Follow-up UI (#409): smoke tests only, no counting is asserted here
# ==============================================================================


def _labels():
    return [m[0] for m in progress_module.metric_row.call_args.args[0]]


def test_display_follow_up_with_a_condition_draws_the_queue(patched_progress, tmp_path):
    settings = _settings(enumerator="enum", **CONDITION)
    result = compute_progress(ATTEMPTS, settings, AS_OF)
    selected = MagicMock()
    selected.selection.rows = [0]
    patched_progress.dataframe.return_value = selected

    progress_module.display_follow_up(result, settings, str(tmp_path / "s.json"))

    assert _labels() == [
        "Need follow-up",
        "Done on 1st try",
        "Avg attempts per completion",
        "3+ attempts, still open",
    ]
    patched_progress.plotly_chart.assert_called_once()
    patched_progress.download_button.assert_called_once()
    # The queue, then the selected row's attempt history
    assert patched_progress.dataframe.call_count == 2
    history = patched_progress.dataframe.call_args_list[1].args[0]
    assert history["Attempt"].to_list() == [1, 2, 3]


def test_display_follow_up_without_a_condition_hides_the_queue(
    patched_progress, tmp_path
):
    settings = _settings()
    result = compute_progress(ATTEMPTS, settings, AS_OF)

    progress_module.display_follow_up(result, settings, str(tmp_path / "s.json"))

    assert _labels() == ["Repeat IDs", "Submissions per ID", "Most submissions"]
    assert "completion condition" in patched_progress.info.call_args.args[0]
    patched_progress.plotly_chart.assert_called_once()
    patched_progress.dataframe.assert_not_called()


def test_display_follow_up_without_an_id_column_explains(patched_progress, tmp_path):
    settings = _settings(survey_id=None)

    progress_module.display_follow_up(
        compute_progress(ATTEMPTS, settings, AS_OF), settings, str(tmp_path / "s.json")
    )

    patched_progress.info.assert_called_once()
    patched_progress.plotly_chart.assert_not_called()


def test_a_todo_card_opens_its_tab(patched_progress):
    settings = _settings(**CONDITION)
    result = compute_progress(ATTEMPTS, settings, AS_OF)

    display_overview(result, settings, "Cumulative")

    button = patched_progress.button.call_args
    assert button.kwargs["on_click"] is progress_module.open_tab
    button.kwargs["on_click"](*button.kwargs["args"])
    assert patched_progress.session_state["progress_tab"] == "Follow-up"


class TestTabBadge:
    def test_follow_up_has_a_badge_only_when_its_queue_has_rows(self):
        with_queue = compute_progress(ATTEMPTS, _settings(**CONDITION), AS_OF)
        without = compute_progress(ATTEMPTS, _settings(), AS_OF)

        assert progress_module.tab_labels(with_queue) == [
            "Overview",
            "Follow-up :orange-badge[3]",
        ]
        assert progress_module.tab_labels(without) == ["Overview", "Follow-up"]

    def test_the_open_tab_follows_its_label_as_the_badge_changes(
        self, patched_progress, tmp_path
    ):
        view = progress_module.check_view(str(tmp_path / "s.json"))
        view.save("progress_tab", "Follow-up :orange-badge[3]")
        patched_progress.session_state["progress_tab"] = "Follow-up"
        labels = ["Overview", "Follow-up :orange-badge[2]"]

        progress_module.settle_tab(view, labels)

        assert patched_progress.session_state["progress_tab"] == labels[1]
        assert view.values()["progress_tab"] == labels[1]


def test_progress_report_puts_the_badge_on_the_follow_up_tab(
    patched_progress, tmp_path
):
    survey_cols = ColumnByType(categorical_columns=["hhid"], datetime_columns=["when"])
    with (
        patch(
            "datasure.checks.progress.progress_report_settings",
            return_value=_settings(**CONDITION),
        ),
        patch("datasure.checks.progress.display_progress_header"),
        patch("datasure.checks.progress.display_overview"),
        patch("datasure.checks.progress.display_follow_up") as follow_up,
    ):
        progress_report(
            ATTEMPTS, str(tmp_path / "s.json"), {"survey_id": "hhid"}, survey_cols
        )

    names = patched_progress.tabs.call_args.args[0]
    assert names == ["Overview", "Follow-up :orange-badge[3]"]
    follow_up.assert_called_once()


def test_without_a_condition_no_bucket_counts_completed_or_open():
    buckets = compute_progress(ATTEMPTS, _settings(), AS_OF).attempts_to_outcome

    assert {(b.completed, b.open) for b in buckets} == {(0, 0)}


def test_the_last_date_outcome_and_enumerator_come_from_the_same_attempt():
    data = _attempts(
        [
            ("h1", "2026-10-01", "yes", "not home", "ann"),
            ("h1", None, "yes", "partial", "bo"),
        ]
    )

    (row,) = _follow_up(data).follow_up_queue

    assert (row.last_outcome, row.last_enumerator, row.last_date) == (
        "partial",
        "bo",
        None,
    )
