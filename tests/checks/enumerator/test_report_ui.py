"""Tests for datasure.checks.enumerator.report_ui."""

import importlib
import sys
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks.enumerator.report_ui import (
    _get_numeric_columns,
    _load_statistics_overtime_settings,
    _load_statistics_settings,
    _render_column_selector,
    _render_column_selector_single,
    _render_enumerator_overview_metrics,
    _render_enumerator_productivity,
    _render_enumerator_statistics,
    _render_enumerator_statistics_overtime,
    _render_period_selector_overtime,
    _render_statistic_selector,
    _render_statistics_selector,
    _render_time_period_selector,
    _render_weekday_selector,
    _render_weekday_selector_overtime,
)
from datasure.models.schemas import ColumnByType
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
        patch("datasure.checks.enumerator.report_ui.save_check_settings"),
        patch(
            "datasure.checks.enumerator.report_ui.load_check_settings", return_value={}
        ),
        patch("datasure.checks.enumerator.report_ui.trigger_save"),
        patch(
            "datasure.checks.enumerator.report_ui.duckdb_get_table",
            return_value=pl.DataFrame(),
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
        report_ui_module.duckdb_get_table = MagicMock(return_value=pl.DataFrame())
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


def test_render_enumerator_overview_no_date_enum(patched_enum):
    """_render_enumerator_overview_metrics shows info when date/enum is None."""
    _render_enumerator_overview_metrics(pl.DataFrame(), None, None, None)
    patched_enum.info.assert_called()


def test_render_enumerator_overview_with_data(patched_enum, sample_enumerator_data):
    """_render_enumerator_overview_metrics renders metrics with valid data."""
    _render_enumerator_overview_metrics(
        sample_enumerator_data, "submission_date", "enumerator", "team"
    )
    patched_enum.columns.assert_called()


def test_render_enumerator_overview_no_team(patched_enum, sample_enumerator_data):
    """_render_enumerator_overview_metrics renders without team column."""
    _render_enumerator_overview_metrics(
        sample_enumerator_data, "submission_date", "enumerator", None
    )
    patched_enum.columns.assert_called()


def test_render_time_period_selector_default(patched_enum):
    """_render_time_period_selector returns Day when pills returns None."""
    result = _render_time_period_selector("settings.json")
    assert result == "Day"
    patched_enum.pills.assert_called()


def test_render_time_period_selector_week(patched_enum):
    """_render_time_period_selector returns Week when pills returns Week."""
    patched_enum.pills.return_value = "Week"
    result = _render_time_period_selector("settings.json")
    assert result == "Week"


def test_render_weekday_selector(patched_enum):
    """_render_weekday_selector returns offset code for the selected weekday."""
    patched_enum.selectbox.return_value = "Monday"
    result = _render_weekday_selector("settings.json")
    assert result == "SUN"


def test_load_statistics_settings_default(patched_enum):
    """_load_statistics_settings returns default StatisticsSettings."""
    result = _load_statistics_settings("settings.json")
    assert result.stats == ["count", "mean"]


def test_render_column_selector(patched_enum):
    """_render_column_selector returns list from multiselect."""
    result = _render_column_selector(["age", "income"], None, "settings.json")
    assert isinstance(result, list)
    patched_enum.multiselect.assert_called()


def test_render_statistics_selector(patched_enum):
    """_render_statistics_selector returns list from multiselect."""
    result = _render_statistics_selector(["count", "mean"], "settings.json")
    assert isinstance(result, list)
    patched_enum.multiselect.assert_called()


def test_render_enumerator_statistics_no_enum(patched_enum):
    """_render_enumerator_statistics shows info when enumerator is None."""
    _render_enumerator_statistics(pl.DataFrame(), None, None, "settings.json")
    patched_enum.info.assert_called()


def test_load_statistics_overtime_settings_default(patched_enum):
    """_load_statistics_overtime_settings returns default settings."""
    result = _load_statistics_overtime_settings("settings.json")
    assert result.stat == "count"


def test_render_period_selector_overtime_default(patched_enum):
    """_render_period_selector_overtime returns Day when pills returns None."""
    result = _render_period_selector_overtime("settings.json")
    assert result == "Day"
    patched_enum.pills.assert_called()


def test_render_period_selector_overtime_week(patched_enum):
    """_render_period_selector_overtime returns Week when pills returns Week."""
    patched_enum.pills.return_value = "Week"
    result = _render_period_selector_overtime("settings.json", default_period="Week")
    assert result == "Week"


def test_render_weekday_selector_overtime(patched_enum):
    """_render_weekday_selector_overtime returns offset code."""
    patched_enum.selectbox.return_value = "Tuesday"
    result = _render_weekday_selector_overtime("Monday", "settings.json")
    assert result == "MON"


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


def test_render_enumerator_productivity_no_enum(patched_enum):
    """_render_enumerator_productivity shows info when enum/date is None."""
    _render_enumerator_productivity(pl.DataFrame(), None, None, None, "settings.json")
    patched_enum.info.assert_called()


def test_render_enumerator_statistics_overtime_no_enum(patched_enum):
    """_render_enumerator_statistics_overtime shows info when enum/date is None."""
    _render_enumerator_statistics_overtime(
        pl.DataFrame(), None, None, None, "settings.json"
    )
    patched_enum.info.assert_called()


def test_load_statistics_settings_fallback(patched_enum):
    """_load_statistics_settings returns defaults when saved settings invalid."""
    with patch(
        "datasure.checks.enumerator.report_ui.load_check_settings",
        return_value={"stats": ["not_a_real_stat"]},
    ):
        result = _load_statistics_settings("settings.json")
    assert result.stats == ["count", "mean"]


def test_load_statistics_overtime_settings_fallback(patched_enum):
    """_load_statistics_overtime_settings returns defaults when settings invalid."""
    with patch(
        "datasure.checks.enumerator.report_ui.load_check_settings",
        return_value={"period_overtime": "bad_period"},
    ):
        result = _load_statistics_overtime_settings("settings.json")
    assert result.stat == "count"


# ============================================
# ENUM_BC UI FRAGMENT TESTS
# ============================================


def test_render_enumerator_summary_table_no_date_enum(enum_bc):
    """_render_enumerator_summary_table shows info when date/enum is None."""
    enum_bc._render_enumerator_summary_table(
        "proj", pl.DataFrame(), None, None, None, None, None
    )
    enum_bc.st.info.assert_called()


def test_render_enumerator_summary_table_with_data(enum_bc, sample_enumerator_data):
    """_render_enumerator_summary_table renders table with valid data."""
    enum_bc._render_enumerator_summary_table(
        "proj",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        "formversion",
        "duration",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_summary_table_with_show_info(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_summary_table filters columns when show_info selected."""
    enum_bc.st.pills.return_value = ["submissions"]
    enum_bc._render_enumerator_summary_table(
        "proj",
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "formversion",
        "duration",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_productivity_table_day(enum_bc, sample_enumerator_data):
    """_render_enumerator_productivity_table renders with Day period."""
    enum_bc._render_enumerator_productivity_table(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "settings.json",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_productivity_table_week(enum_bc, sample_enumerator_data):
    """_render_enumerator_productivity_table renders weekday selector for Week."""
    enum_bc.st.pills.return_value = "Week"
    enum_bc.st.selectbox.return_value = "Monday"
    enum_bc._render_enumerator_productivity_table(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        "settings.json",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_statistics_table_no_enum(enum_bc):
    """_render_enumerator_statistics_table shows info when enum is None."""
    enum_bc._render_enumerator_statistics_table(pl.DataFrame(), None, None, "s.json")
    enum_bc.st.info.assert_called()


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


def test_render_enumerator_statistics_with_enum(enum_bc, sample_enumerator_data):
    """_render_enumerator_statistics calls the fragment table function."""
    enum_bc._render_enumerator_statistics(
        sample_enumerator_data, "enumerator", None, "settings.json"
    )
    enum_bc.st.info.assert_called()


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
    )
    enum_bc.st.info.assert_called()


def test_render_enumerator_statistics_overtime_table_with_col(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_statistics_overtime_table renders with valid col."""
    enum_bc.st.selectbox.side_effect = ["age", "count"]
    enum_bc._render_enumerator_statistics_overtime_table(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "settings.json",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_statistics_overtime_table_week_period(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_statistics_overtime_table handles Week period."""
    enum_bc.st.pills.return_value = "Week"
    enum_bc.st.selectbox.side_effect = ["age", "count", "Monday"]
    enum_bc._render_enumerator_statistics_overtime_table(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        "team",
        "settings.json",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_productivity_with_valid_params(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_productivity calls the table fragment when params valid."""
    enum_bc._render_enumerator_productivity(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "settings.json",
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_statistics_overtime_with_valid_params(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_statistics_overtime calls the table fragment."""
    enum_bc._render_enumerator_statistics_overtime(
        sample_enumerator_data,
        "submission_date",
        "enumerator",
        None,
        "settings.json",
    )
    enum_bc.st.info.assert_called()


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


def test_enumerator_report_with_data(enum_bc, sample_enumerator_data):
    """enumerator_report renders full report with valid data."""
    survey_cols = ColumnByType(
        categorical_columns=list(sample_enumerator_data.columns),
        datetime_columns=["submission_date"],
    )
    # `_render_consent_outcome_settings` lives in settings_ui (called internally by
    # enumerator_report_settings) rather than report_ui, so it must be patched on
    # the module that actually owns it for the stub to take effect.
    from datasure.checks.enumerator import settings_ui as settings_ui_module

    settings_ui_module._render_consent_outcome_settings = MagicMock()

    def _selectbox_side_effect(label, options=None, **kwargs):
        if options and "seconds" in options:
            return "seconds"
        return None

    enum_bc.st.selectbox.side_effect = _selectbox_side_effect
    enum_bc.enumerator_report(
        "proj_id",
        sample_enumerator_data,
        "settings.json",
        {"survey_id": "survey_id"},
        survey_cols,
    )
    enum_bc.st.title.assert_called()


def test_render_enumerator_statistics_table_with_cols_no_team(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_statistics_table uses else column config when no team."""
    enum_bc.st.multiselect.side_effect = [["age"], ["count"]]
    enum_bc._render_enumerator_statistics_table(
        sample_enumerator_data, "enumerator", None, "settings.json"
    )
    enum_bc.st.dataframe.assert_called()


def test_render_enumerator_statistics_overtime_table_early_return(
    enum_bc, sample_enumerator_data
):
    """_render_enumerator_statistics_overtime_table returns early when enum None."""
    enum_bc._render_enumerator_statistics_overtime_table(
        sample_enumerator_data, "submission_date", None, None, "settings.json"
    )
    enum_bc.st.dataframe.assert_not_called()
