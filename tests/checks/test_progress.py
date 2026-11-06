"""Tests for the progress module with comprehensive coverage."""

import datetime
import importlib
import json
import sys
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from pydantic import ValidationError

from datasure.checks import progress as progress_module
from datasure.checks.progress import (
    AttemptedInterviewsResult,
    ProgressSettings,
    TimePeriodConfig,
    _aggregate_attempts_by_survey_id,
    _compute_summary_stats,
    _display_chart_and_table,
    _display_metrics,
    _expand_attempt_dates,
    _get_unique_values,
    _prepare_display_columns,
    compute_attempted_interviews,
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


@pytest.fixture
def prog_bc():
    mock_st = _make_mock_st()
    original_st = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock_st
    import datasure.checks.progress as prog_module

    try:
        importlib.reload(prog_module)
        prog_module.load_check_settings = MagicMock(return_value={})
        prog_module.save_check_settings = MagicMock()
        prog_module.trigger_save = MagicMock()
        prog_module.demo_callout = MagicMock()
        prog_module.metric_row = MagicMock()
        prog_module.section_header = MagicMock()
        with patch(
            "datasure.utils.onboarding_utils.is_demo_project", return_value=False
        ):
            yield prog_module
    finally:
        if original_st is not None:
            sys.modules["streamlit"] = original_st
        else:
            sys.modules.pop("streamlit", None)
        importlib.reload(prog_module)


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

    def test_attempted_interviews_result_valid(self):
        """Test creating valid AttemptedInterviewsResult."""
        df = pl.DataFrame({"survey_id": ["ID1", "ID2"], "num_interviews": [1, 2]})
        result = AttemptedInterviewsResult(
            attempted_interviews=df,
            total_submitted=10,
            number_of_unique_ids=2,
            min_attempts=1,
            max_attempts=2,
        )
        assert result.total_submitted == 10
        assert result.number_of_unique_ids == 2


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

    def test_aggregate_attempts_by_survey_id(self):
        """Test _aggregate_attempts_by_survey_id helper."""
        import datetime

        data = pl.DataFrame(
            {
                "survey_id": ["ID1", "ID1", "ID2", "ID3"],
                "date": [
                    datetime.datetime(2024, 1, 1),
                    datetime.datetime(2024, 1, 2),
                    datetime.datetime(2024, 1, 3),
                    datetime.datetime(2024, 1, 4),
                ],
            }
        )

        result = _aggregate_attempts_by_survey_id(data, "survey_id", "date")

        assert isinstance(result, pl.DataFrame)
        assert "num_interviews" in result.columns
        assert "last_attempt_date" in result.columns
        assert "attempt_dates" in result.columns
        assert result.height == 3  # 3 unique survey IDs

    def test_expand_attempt_dates(self):
        """Test _expand_attempt_dates helper."""
        import datetime

        data = pl.DataFrame(
            {
                "survey_id": ["ID1", "ID2"],
                "num_interviews": [2, 3],
                "attempt_dates": [
                    [datetime.datetime(2024, 1, 1), datetime.datetime(2024, 1, 2)],
                    [
                        datetime.datetime(2024, 1, 3),
                        datetime.datetime(2024, 1, 4),
                        datetime.datetime(2024, 1, 5),
                    ],
                ],
            }
        )

        result = _expand_attempt_dates(data)

        assert isinstance(result, pl.DataFrame)
        assert "Attempt Date 1" in result.columns
        assert "Attempt Date 2" in result.columns
        assert "Attempt Date 3" in result.columns
        assert "attempt_dates" not in result.columns

    def test_prepare_display_columns_empty(self):
        """Test _prepare_display_columns with empty display_cols."""
        data = pl.DataFrame(
            {
                "survey_id": ["ID1", "ID2", "ID3"],
                "date": [1, 2, 3],
                "col1": ["A", "B", "C"],
            }
        )

        result = _prepare_display_columns(data, "survey_id", "date", [])

        assert isinstance(result, pl.DataFrame)
        assert "survey_id" in result.columns
        assert result.height == 3

    def test_prepare_display_columns_with_cols(self):
        """Test _prepare_display_columns with display columns."""
        data = pl.DataFrame(
            {
                "survey_id": ["ID1", "ID1", "ID2"],
                "date": [1, 2, 3],
                "enum": ["E1", None, "E2"],
                "team": [None, "T1", "T2"],
            }
        )

        result = _prepare_display_columns(data, "survey_id", "date", ["enum", "team"])

        assert isinstance(result, pl.DataFrame)
        assert "enum" in result.columns
        assert "team" in result.columns
        assert result.height == 2  # 2 unique survey IDs

    def test_compute_summary_stats(self):
        """Test _compute_summary_stats helper."""
        data = pl.DataFrame(
            {"survey_id": ["ID1", "ID2", "ID3"], "num_interviews": [1, 3, 2]}
        )

        num_unique, min_attempts, max_attempts = _compute_summary_stats(data)

        assert num_unique == 3
        assert min_attempts == 1
        assert max_attempts == 3


class TestComputeAttemptedInterviewsUpdated:
    """Test compute_attempted_interviews with new Polars/Pydantic API."""

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_attempted_interviews_basic(self):
        """Test compute_attempted_interviews basic functionality."""
        import datetime

        data = pl.DataFrame(
            {
                "survey_id": ["ID1", "ID1", "ID2", "ID3", "ID3", "ID3"],
                "date": [
                    datetime.datetime(2024, 1, 1),
                    datetime.datetime(2024, 1, 2),
                    datetime.datetime(2024, 1, 3),
                    datetime.datetime(2024, 1, 4),
                    datetime.datetime(2024, 1, 5),
                    datetime.datetime(2024, 1, 6),
                ],
            }
        )

        result = compute_attempted_interviews(data, "survey_id", "date", [])

        assert isinstance(result, AttemptedInterviewsResult)
        assert result.total_submitted == 6
        assert result.number_of_unique_ids == 3
        assert result.min_attempts == 1
        assert result.max_attempts == 3

    @patch("datasure.checks.progress.st.cache_data", lambda f: f)
    def test_compute_attempted_interviews_with_display_cols(self):
        """Test compute_attempted_interviews with display columns."""
        import datetime

        data = pl.DataFrame(
            {
                "survey_id": ["ID1", "ID1", "ID2"],
                "date": [
                    datetime.datetime(2024, 1, 1),
                    datetime.datetime(2024, 1, 2),
                    datetime.datetime(2024, 1, 3),
                ],
                "enumerator": ["E1", "E1", "E2"],
                "team": ["T1", "T1", "T2"],
            }
        )

        result = compute_attempted_interviews(
            data, "survey_id", "date", ["enumerator", "team"]
        )

        assert isinstance(result, AttemptedInterviewsResult)
        assert "enumerator" in result.attempted_interviews.columns
        assert "team" in result.attempted_interviews.columns

    @pytest.mark.parametrize("display_cols", [[], ["enumerator"]])
    def test_compute_attempted_interviews_zero_rows(self, display_cols):
        """Zero-row data gives an empty table and zero counts."""
        data = pl.DataFrame(
            schema={
                "survey_id": pl.String,
                "date": pl.Datetime,
                "enumerator": pl.String,
            }
        )

        result = compute_attempted_interviews(data, "survey_id", "date", display_cols)

        assert result.attempted_interviews.is_empty()
        assert result.total_submitted == 0
        assert result.number_of_unique_ids == 0
        assert result.min_attempts == 0
        assert result.max_attempts == 0


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

    def test_values_missing_from_the_column_are_dropped_from_the_file(
        self, real_saving
    ):
        mock_st, settings_file = real_saving
        saved = {"consent": "consent", "consent_vals": ["yes", "maybe"]}
        settings_file.write_text(json.dumps({"progress": saved}))

        self._render(mock_st, settings_file, "consent", ["yes"], saved)

        assert self._saved(settings_file)["consent_vals"] == ["yes"]

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
        patch("datasure.checks.progress.display_attempted_interviews") as follow_up,
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


def test_display_attempted_interviews_missing_id(prog_bc):
    """display_attempted_interviews shows info when survey_id is missing."""
    data = pl.DataFrame({"value": [1, 2, 3]})
    prog_bc.display_attempted_interviews(data, None, "date", "settings.json")
    prog_bc.st.info.assert_called()


def test_display_attempted_interviews_with_data(prog_bc):
    """display_attempted_interviews renders full report."""
    data = pl.DataFrame(
        {
            "survey_id": ["ID1", "ID2"],
            "date": pl.Series(
                [datetime.datetime(2024, 1, 1), datetime.datetime(2024, 1, 2)]
            ),
        }
    )
    mock_result = AttemptedInterviewsResult(
        attempted_interviews=pl.DataFrame(
            {
                "survey_id": ["ID1", "ID2"],
                "num_interviews": [1, 2],
                "last_attempt_date": [
                    datetime.date(2024, 1, 1),
                    datetime.date(2024, 1, 2),
                ],
                "Attempt Date 1": [
                    datetime.datetime(2024, 1, 1),
                    datetime.datetime(2024, 1, 2),
                ],
            }
        ),
        total_submitted=2,
        number_of_unique_ids=2,
        min_attempts=1,
        max_attempts=2,
    )
    prog_bc.compute_attempted_interviews = MagicMock(return_value=mock_result)
    prog_bc.st.multiselect.return_value = []

    prog_bc.display_attempted_interviews(data, "survey_id", "date", "settings.json")
    prog_bc.st.columns.assert_called()


def test_display_metrics_renders(patched_progress):
    """_display_metrics renders four metric columns."""
    result = AttemptedInterviewsResult(
        attempted_interviews=pl.DataFrame(
            {"survey_id": ["ID1"], "num_interviews": [1]}
        ),
        total_submitted=5,
        number_of_unique_ids=1,
        min_attempts=1,
        max_attempts=1,
    )
    _display_metrics(result)
    patched_progress.columns.assert_called()


def test_display_chart_and_table_renders(patched_progress):
    """_display_chart_and_table renders frequency chart and data table."""
    data = pl.DataFrame(
        {
            "survey_id": ["ID1", "ID2"],
            "num_interviews": [1, 2],
            "last_attempt_date": [
                datetime.date(2024, 1, 1),
                datetime.date(2024, 1, 2),
            ],
            "Attempt Date 1": [
                datetime.datetime(2024, 1, 1),
                datetime.datetime(2024, 1, 2),
            ],
            "Attempt Date 2": [None, datetime.datetime(2024, 1, 3)],
        }
    )
    _display_chart_and_table(data, "survey_id")
    patched_progress.plotly_chart.assert_called()
    patched_progress.dataframe.assert_called()


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
        # 15 remaining at 2 a day is 8 days.
        pace = compute_progress(self.DATA, _settings(survey_target=30), AS_OF).pace

        assert pace.per_day == 2.0
        assert pace.projected_finish == datetime.date(2026, 10, 22)

    def test_a_shorter_fieldwork_averages_over_its_own_days(self):
        data = _daily({"2026-10-12": 1, "2026-10-13": 2, "2026-10-14": 3})

        pace = compute_progress(data, _settings(survey_target=12), AS_OF).pace

        assert pace.per_day == 2.0
        assert pace.projected_finish == datetime.date(2026, 10, 17)

    def test_no_projection_with_fewer_than_3_days_of_data(self):
        data = _daily({"2026-10-13": 5, "2026-10-14": 5})

        pace = compute_progress(data, _settings(survey_target=30), AS_OF).pace

        assert pace.projected_finish is None

    def test_the_window_ends_at_the_last_submission_not_today(self):
        # Submissions stopped on 3 Oct: the pace is 1 a day over 1-3 Oct, and
        # the 27 remaining are projected from today.
        data = _daily({"2026-10-01": 1, "2026-10-02": 1, "2026-10-03": 1})

        pace = compute_progress(data, _settings(survey_target=30), AS_OF).pace

        assert pace.per_day == 1.0
        assert pace.projected_finish == datetime.date(2026, 11, 10)

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
        assert status.title == "Projected finish: Thu 22 Oct"
        assert "field end date" in status.message

    def test_on_track_counts_the_days_before_the_end_date(self):
        status = self._status(field_end_date=datetime.date(2026, 10, 23))

        assert (status.level, status.title) == ("success", "On track to finish on time")
        assert "1 day before the field end date (Fri 23 Oct)" in status.message

    def test_finishing_on_the_end_date_is_on_track(self):
        status = self._status(field_end_date=datetime.date(2026, 10, 22))

        assert status.level == "success"
        assert "on the field end date (Thu 22 Oct)" in status.message

    def test_behind_counts_the_days_after_and_the_pace_needed(self):
        # 15 remaining over the 7 days from today to 20 Oct: 2.1 a day.
        status = self._status(field_end_date=datetime.date(2026, 10, 20))

        assert (status.level, status.title) == ("warning", "Behind schedule")
        assert "2 days after the field end date (Tue 20 Oct)" in status.message
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

    def test_none_without_a_target(self):
        assert compute_progress(self.DATA, _settings(), AS_OF).target_path == []


class TestPageShape:
    def test_a_fixed_target_shows_overview_and_follow_up(self):
        result = compute_progress(SURVEY, _settings(survey_target=10), AS_OF)

        assert result.mode == "fixed"
        assert result.tabs == ["Overview", "Follow-up"]
        assert result.todos == []
