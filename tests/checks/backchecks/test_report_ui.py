"""Tests for datasure.checks.backchecks.report_ui."""

import importlib
import sys
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks.backchecks.models import (
    BackcheckSettings,
    BackcheckTestOptions,
    OkRangeOptions,
    OkRangeValues,
)
from datasure.checks.backchecks.report_ui import (
    _add_extra_backcheck_columns,
    _add_extra_survey_columns,
    _apply_backcheck_filters,
    _build_column_config,
    _build_display_columns,
    _delete_backcheck_column,
    _get_available_additional_columns,
    _get_ok_range_value,
    _prepare_display_data,
    _render_additional_columns_selector,
    _render_backcheck_category_options,
    _render_backcheck_comparison_results,
    _render_backcheck_settings_table,
    _render_backcheck_summary,
    _render_backcheck_test_options,
    _render_backchecker_productivity,
    _render_backchecks_column_actions,
    _render_column_stats,
    _render_enum_bcer_stats,
    _render_ok_range_options,
    _render_search_type_selection,
    _render_time_period_selector_backchecks,
    _render_weekday_selector_backchecks,
    _update_backcheck_column_config,
)
from tests.checks.backchecks.conftest import make_mock_st

# ============================================
# PATCHED_BC FIXTURE (patch st in report_ui for non-fragment UI tests)
# ============================================


@pytest.fixture
def patched_bc():
    """Patch report_ui module's st and utility deps for non-fragment UI tests."""
    mock_st = make_mock_st()
    with (
        patch("datasure.checks.backchecks.report_ui.st", mock_st),
        patch("datasure.checks.backchecks.report_ui.save_check_settings"),
        patch(
            "datasure.checks.backchecks.report_ui.load_check_settings", return_value={}
        ),
        patch("datasure.checks.backchecks.report_ui.trigger_save"),
        patch(
            "datasure.checks.backchecks.report_ui.duckdb_get_table",
            return_value=pl.DataFrame(),
        ),
        patch("datasure.checks.backchecks.report_ui.duckdb_save_table"),
    ):
        yield mock_st


# ============================================
# BC FIXTURE (reload compute/settings_ui/report_ui with mocked streamlit)
# ============================================


@pytest.fixture
def bc():
    """Reload backchecks submodules with mocked Streamlit to strip fragments."""
    mock_st = make_mock_st()
    original_st = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock_st

    import datasure.checks.backchecks.compute as compute_module
    import datasure.checks.backchecks.report_ui as report_ui_module
    import datasure.checks.backchecks.settings_ui as settings_ui_module

    try:
        # Reload in dependency order so decorators pick up the mocked st and
        # cross-module references (report_ui imports from settings_ui) stay wired.
        importlib.reload(compute_module)
        importlib.reload(settings_ui_module)
        importlib.reload(report_ui_module)

        settings_ui_module.load_check_settings = MagicMock(return_value={})
        settings_ui_module.save_check_settings = MagicMock()
        settings_ui_module.trigger_save = MagicMock()

        report_ui_module.load_check_settings = MagicMock(return_value={})
        report_ui_module.save_check_settings = MagicMock()
        report_ui_module.trigger_save = MagicMock()
        report_ui_module.duckdb_get_table = MagicMock(return_value=pl.DataFrame())
        report_ui_module.duckdb_save_table = MagicMock()
        report_ui_module.demo_callout = MagicMock()
        report_ui_module.show_demo_next_action = MagicMock()

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
# REPORT UI TESTS
# ============================================


def test_get_available_additional_columns():
    """Test _get_available_additional_columns."""
    data = pl.DataFrame(
        {
            "survey_id": ["A", "B"],
            "survey_id__BCCL": ["A", "B"],
            "age__SRV": [25, 30],
            "age__BCCL": [25, 30],
            "income__SRV": [50000, 60000],
        }
    )
    backcheck_analysis = pl.DataFrame(
        {
            "survey_id": ["A", "B"],
            "column_name": ["age", "income"],
        }
    )

    result = _get_available_additional_columns(
        data,
        "survey_id",
        "survey_id",
        backcheck_analysis,
    )

    assert isinstance(result, list) or result is None


def test_apply_backcheck_filters_all():
    """Test _apply_backcheck_filters with 'All' filter."""
    backcheck_analysis = pl.DataFrame(
        {
            "column_name": ["age", "income", "gender"],
            "match_status": ["match", "mismatch", "match"],
        }
    )

    result = _apply_backcheck_filters(
        backcheck_analysis,
        "All",
        ["age", "income"],
    )

    assert len(result) == 2
    assert set(result["column_name"].to_list()) == {"age", "income"}


def test_apply_backcheck_filters_mismatches():
    """Test _apply_backcheck_filters with 'Mismatches Only' filter."""
    backcheck_analysis = pl.DataFrame(
        {
            "column_name": ["age", "income", "gender"],
            "match_status": ["match", "mismatch", "match"],
        }
    )

    result = _apply_backcheck_filters(
        backcheck_analysis,
        "Mismatches Only",
        [],
    )

    assert len(result) == 1
    assert result["column_name"][0] == "income"


def test_build_display_columns():
    """Test _build_display_columns."""
    filtered_data = pl.DataFrame(
        {
            "survey_id": ["A", "B"],
            "survey_id__BCCL": ["A", "B"],
            "column_name": ["age", "income"],
            "age__SRV": [25, 30],
            "age__BCCL": [25, 31],
        }
    )

    result = _build_display_columns(
        filtered_data,
        "survey_id",
        "survey_id",
        "survey_id__BCCL",
    )

    assert isinstance(result, list)
    assert len(result) > 0


def test_build_column_config():
    """Test _build_column_config."""
    filtered_data = pl.DataFrame(
        {
            "survey_id": ["A", "B"],
            "survey_id__BCCL": ["A", "B"],
            "column_name": ["age", "income"],
        }
    )

    result = _build_column_config(
        "survey_id",
        "survey_id",
        "survey_id__BCCL",
        filtered_data,
    )

    assert isinstance(result, dict)
    assert "survey_id" in result or len(result) > 0


def test_add_extra_survey_columns_empty_list():
    filtered = pl.DataFrame({"key": [1], "col_a": ["x"]})
    survey = pl.DataFrame({"key": [1], "extra": ["y"]})
    result = _add_extra_survey_columns(filtered, survey, "key", [])
    assert result.columns == filtered.columns


def test_add_extra_survey_columns_with_cols():
    filtered = pl.DataFrame({"key": [1, 2]})
    survey = pl.DataFrame({"key": [1, 2], "extra": ["a", "b"]})
    result = _add_extra_survey_columns(filtered, survey, "key", ["extra"])
    assert "extra (Survey)" in result.columns


def test_add_extra_backcheck_columns_empty_list():
    filtered = pl.DataFrame({"key": [1]})
    bc_data = pl.DataFrame({"key": [1], "extra": ["x"]})
    result = _add_extra_backcheck_columns(filtered, bc_data, "key", "key__BCCL", [])
    assert result.columns == filtered.columns


def test_add_extra_backcheck_columns_no_backcheck_key():
    """Returns unchanged data when backcheck_key not present in filtered_data."""
    filtered = pl.DataFrame({"key": [1]})
    bc_data = pl.DataFrame({"key": [1], "extra": ["x"]})
    result = _add_extra_backcheck_columns(filtered, bc_data, "key", "bc_key", ["extra"])
    assert result.columns == filtered.columns


def test_add_extra_backcheck_columns_with_cols():
    filtered = pl.DataFrame({"key": [1], "bc_key": [10]})
    bc_data = pl.DataFrame({"key": [1], "extra": ["x"]})
    result = _add_extra_backcheck_columns(filtered, bc_data, "key", "bc_key", ["extra"])
    assert "extra (Backcheck)" in result.columns


def test_build_display_columns_basic():
    filtered = pl.DataFrame(
        {
            "column_name": ["age"],
            "survey_value": ["25"],
            "backcheck_value": ["25"],
            "match_status": ["match"],
            "category": [1],
        }
    )
    result = _build_display_columns(filtered, "key", None, "key__BCCL")
    assert "column_name" in result
    assert "survey_value" in result


def test_build_display_columns_with_all_ids():
    filtered = pl.DataFrame(
        {
            "key": [1],
            "bc_key": [10],
            "sid": ["a"],
            "column_name": ["age"],
            "survey_value": ["25"],
            "backcheck_value": ["25"],
            "match_status": ["match"],
            "category": [1],
        }
    )
    result = _build_display_columns(filtered, "key", "sid", "bc_key")
    assert "sid" in result
    assert "key" in result
    assert "bc_key" in result


def test_build_display_columns_with_extra_cols():
    """Extra Survey/Backcheck columns are appended to display list."""
    filtered = pl.DataFrame(
        {
            "column_name": ["age"],
            "survey_value": ["25"],
            "backcheck_value": ["25"],
            "match_status": ["match"],
            "category": [1],
            "extra (Survey)": ["val"],
            "other (Backcheck)": ["val2"],
        }
    )
    result = _build_display_columns(filtered, "key", None, "bc_key")
    assert "extra (Survey)" in result
    assert "other (Backcheck)" in result


def test_prepare_display_data_filters_null_rows():
    """Rows where both survey_value and backcheck_value are null are removed."""
    filtered = pl.DataFrame(
        {
            "column_name": ["age", "name", "city"],
            "survey_value": ["25", None, "NYC"],
            "backcheck_value": ["25", None, "LA"],
            "match_status": ["match", "match", "mismatch"],
            "category": [1, 1, 1],
        }
    )
    cols = [
        "column_name",
        "survey_value",
        "backcheck_value",
        "match_status",
        "category",
    ]
    result = _prepare_display_data(filtered, cols)
    assert result.height == 2


def test_build_column_config_with_all_keys():
    filtered = pl.DataFrame({"key": [1], "bc_key": [10], "sid": ["a"]})
    result = _build_column_config("key", "sid", "bc_key", filtered)
    assert "key" in result
    assert "bc_key" in result
    assert "sid" in result


def test_build_column_config_missing_keys():
    """Config doesn't include keys not present in filtered_data."""
    filtered = pl.DataFrame({"other_col": [1]})
    result = _build_column_config("key", "sid", "bc_key", filtered)
    assert "column_name" in result
    assert "key" not in result


def test_get_ok_range_value_number_type(patched_bc):
    """_get_ok_range_value returns OkRangeValues for number type."""
    result = _get_ok_range_value("number")
    assert isinstance(result, OkRangeValues)
    assert result.ok_range_neg <= 0
    assert result.ok_range_pos >= 0


def test_get_ok_range_value_percentage_type(patched_bc):
    """_get_ok_range_value returns OkRangeValues for percentage type."""
    result = _get_ok_range_value("percentage")
    assert isinstance(result, OkRangeValues)
    assert result.ok_range_neg <= 0
    assert result.ok_range_pos >= 0


def test_render_backcheck_settings_table(patched_bc):
    """_render_backcheck_settings_table calls st.expander and st.dataframe."""
    df = pl.DataFrame(
        {
            "search_type": ["exact"],
            "pattern": [None],
            "column_name": [["age"]],
            "category": [1],
            "ok_range_type": [None],
            "ok_range_values": [None],
            "ttest": [False],
            "prtest": [False],
            "signrank": [False],
            "reliability": [False],
        }
    )
    _render_backcheck_settings_table(df)
    patched_bc.expander.assert_called()


def test_render_search_type_selection_exact(patched_bc):
    """_render_search_type_selection returns exact path when exact is selected."""
    patched_bc.selectbox.return_value = "exact"
    patched_bc.multiselect.return_value = ["age", "income"]
    result = _render_search_type_selection(["age", "income", "gender"])
    assert result[0] == "exact"
    assert result[1] is None
    assert "age" in result[2]


def test_render_search_type_selection_pattern(patched_bc):
    """_render_search_type_selection returns pattern path with non-exact type."""
    patched_bc.selectbox.return_value = "contains"
    patched_bc.text_input.return_value = "age"
    result = _render_search_type_selection(["age_survey", "income", "age_bc"])
    assert result[0] == "contains"
    assert result[1] == "age"


def test_render_search_type_selection_pattern_empty(patched_bc):
    """_render_search_type_selection with non-exact type and empty pattern."""
    patched_bc.selectbox.return_value = "contains"
    patched_bc.text_input.return_value = ""
    result = _render_search_type_selection(["age"])
    assert result[2] == []


def test_render_backcheck_category_options(patched_bc):
    """_render_backcheck_category_options returns pills selection."""
    patched_bc.pills.return_value = 2
    result = _render_backcheck_category_options()
    assert result == 2


def test_render_ok_range_options_with_range(patched_bc):
    """_render_ok_range_options returns OkRangeOptions when a range type is selected."""
    patched_bc.pills.return_value = "number"
    patched_bc.number_input.return_value = 5.0
    result = _render_ok_range_options()
    assert result.ok_range_type == "number"


def test_render_ok_range_options_none(patched_bc):
    """_render_ok_range_options returns OkRangeOptions when no type selected."""
    patched_bc.pills.return_value = None
    result = _render_ok_range_options()
    assert result.ok_range_type is None


def test_render_backcheck_test_options_category1(patched_bc):
    """_render_backcheck_test_options removes reliability for category 1."""
    patched_bc.pills.return_value = ["ttest"]
    result = _render_backcheck_test_options(1)
    assert isinstance(result, BackcheckTestOptions)
    assert result.ttest is True


def test_render_backcheck_test_options_category2(patched_bc):
    """_render_backcheck_test_options includes reliability for category 2+."""
    patched_bc.pills.return_value = ["ttest", "reliability"]
    result = _render_backcheck_test_options(2)
    assert result.ttest is True
    assert result.reliability is True


def test_render_backcheck_summary(patched_bc):
    """_render_backcheck_summary renders metrics without errors."""
    survey_data = pl.DataFrame({"key": [1, 2], "enum": ["a", "b"]})
    backcheck_data = pl.DataFrame({"key": [1], "bcer": ["c"]})
    analysis = pl.DataFrame(
        {
            "key": [1],
            "column_name": ["age"],
            "survey_value": ["25"],
            "backcheck_value": ["26"],
            "match_status": ["mismatch"],
            "category": [1],
        }
    )
    settings = BackcheckSettings(
        survey_key="key", enumerator="enum", backchecker="bcer"
    )
    _render_backcheck_summary(survey_data, backcheck_data, analysis, settings)
    patched_bc.metric.assert_called()


def test_render_time_period_selector_backchecks(patched_bc):
    """_render_time_period_selector_backchecks returns selected time period."""
    patched_bc.pills.return_value = "Week"
    result = _render_time_period_selector_backchecks("settings.json")
    assert result == "Week"


def test_render_time_period_selector_backchecks_none(patched_bc):
    """_render_time_period_selector_backchecks returns 'Day' when pills returns None."""
    patched_bc.pills.return_value = None
    result = _render_time_period_selector_backchecks("settings.json")
    assert result == "Day"


def test_render_weekday_selector_backchecks(patched_bc):
    """_render_weekday_selector_backchecks returns WEEKDAY_OFFSET_MAP value."""
    patched_bc.selectbox.return_value = "Monday"
    result = _render_weekday_selector_backchecks("settings.json")
    assert result == "SUN"


def test_render_enum_bcer_stats_empty_analysis(patched_bc):
    """_render_enum_bcer_stats shows info for empty analysis."""
    _render_enum_bcer_stats(
        pl.DataFrame(),
        pl.DataFrame(),
        pl.DataFrame(),
        BackcheckSettings(survey_key=None),
        "settings.json",
    )
    patched_bc.info.assert_called()


def test_render_enum_bcer_stats_no_staff(patched_bc):
    """_render_enum_bcer_stats shows info when no enumerator/backchecker configured."""
    analysis = pl.DataFrame({"key": [1]})
    settings = BackcheckSettings(survey_key=None, enumerator=None, backchecker=None)
    _render_enum_bcer_stats(
        pl.DataFrame({"key": [1]}),
        pl.DataFrame({"key": [1]}),
        analysis,
        settings,
        "settings.json",
    )
    patched_bc.info.assert_called()


def test_render_enum_bcer_stats_with_data(patched_bc):
    """_render_enum_bcer_stats calls fragment when data and config are present."""
    analysis = pl.DataFrame({"key": [1]})
    settings = BackcheckSettings(
        survey_key=None, enumerator="enumerator", backchecker="backchecker"
    )
    with patch("datasure.checks.backchecks.report_ui._render_enum_bcer_stats_table"):
        _render_enum_bcer_stats(
            pl.DataFrame({"key": [1]}),
            pl.DataFrame({"key": [1]}),
            analysis,
            settings,
            "settings.json",
        )


def test_render_column_statistics_empty_analysis(patched_bc):
    """_render_column_statistics shows info message for empty analysis."""
    _render_column_stats(pl.DataFrame({"key": [1]}), pl.DataFrame())
    patched_bc.info.assert_called()


def test_render_column_statistics_with_data(patched_bc):
    """_render_column_statistics renders dataframe when data available."""
    survey_data = pl.DataFrame({"key": [1, 2], "age": [25, 30]})
    analysis = pl.DataFrame(
        {
            "key": [1, 2],
            "column_name": ["age", "age"],
            "survey_value": ["25", "30"],
            "backcheck_value": ["25", "31"],
            "match_status": ["match", "mismatch"],
            "category": [1, 1],
        }
    )
    _render_column_stats(survey_data, analysis)
    patched_bc.dataframe.assert_called()


def test_render_additional_columns_selector(patched_bc):
    """_render_additional_columns_selector returns (survey_cols, backcheck_cols)."""
    survey_data = pl.DataFrame({"key": [1], "extra_a": ["x"]})
    backcheck_data = pl.DataFrame({"key": [1], "extra_b": ["y"]})
    analysis = pl.DataFrame({"key": [1]})

    with patch(
        "datasure.checks.backchecks.report_ui._get_available_additional_columns",
        return_value=["extra_a"],
    ):
        result = _render_additional_columns_selector(
            survey_data, backcheck_data, "key", "sid", analysis
        )

    assert isinstance(result, tuple)
    assert len(result) == 2


def test_render_backcheck_comparison_results_empty(patched_bc):
    """_render_backcheck_comparison_results shows info for empty analysis."""
    _render_backcheck_comparison_results(
        pl.DataFrame(),
        pl.DataFrame(),
        pl.DataFrame(),
        BackcheckSettings(survey_key="key", survey_id=None),
    )
    patched_bc.info.assert_called()


def test_render_backcheck_comparison_results_no_columns(patched_bc):
    """_render_backcheck_comparison_results shows info when no columns available."""
    analysis = pl.DataFrame(
        {
            "key": [1],
            "column_name": pl.Series([None], dtype=pl.Utf8),
            "survey_value": ["25"],
            "backcheck_value": ["26"],
            "match_status": ["mismatch"],
            "category": [1],
        }
    )
    _render_backcheck_comparison_results(
        pl.DataFrame({"key": [1]}),
        pl.DataFrame({"key": [1]}),
        analysis,
        BackcheckSettings(survey_key="key", survey_id=None),
    )
    patched_bc.info.assert_called()


def test_render_backcheck_comparison_results_with_data(patched_bc):
    """_render_backcheck_comparison_results renders full results table."""
    analysis = pl.DataFrame(
        {
            "key": [1, 1],
            "column_name": ["age", "income"],
            "survey_value": ["25", "5000"],
            "backcheck_value": ["26", "5000"],
            "match_status": ["mismatch", "match"],
            "category": [1, 1],
        }
    )
    survey_data = pl.DataFrame(
        {"key": [1], "sid": ["a"], "age": [25], "income": [5000]}
    )
    backcheck_data = pl.DataFrame({"key": [1], "age": [26], "income": [5000]})
    settings = BackcheckSettings(survey_key="key", survey_id="sid")

    with patch(
        "datasure.checks.backchecks.report_ui._render_additional_columns_selector",
        return_value=([], []),
    ):
        _render_backcheck_comparison_results(
            survey_data, backcheck_data, analysis, settings
        )

    patched_bc.dataframe.assert_called()


def test_render_backchecks_column_actions_empty(patched_bc):
    """_render_backchecks_column_actions shows info when no columns configured."""
    _render_backchecks_column_actions(
        "proj_id",
        "page_id",
        pl.DataFrame({"key": [1]}),
        pl.DataFrame({"key": [1]}),
        ["key"],
    )
    patched_bc.info.assert_called()


def test_delete_backcheck_column_empty(patched_bc):
    """_delete_backcheck_column shows info message when no columns configured."""
    _delete_backcheck_column("proj_id", "page_id", pl.DataFrame())
    patched_bc.info.assert_called()


def test_update_backcheck_column_config(patched_bc):
    """_update_backcheck_column_config saves new column config to database."""
    ok_opts = OkRangeOptions()
    test_opts = BackcheckTestOptions()
    _update_backcheck_column_config(
        "proj_id", "page_id", "exact", None, ["age"], 1, ok_opts, test_opts
    )


def test_get_available_additional_columns_fragment(bc):
    """_get_available_additional_columns returns sorted list of non-excluded cols."""
    data = pl.DataFrame({"key": [1], "sid": ["a"], "extra_col": ["x"], "other": ["y"]})
    analysis = pl.DataFrame({"key": [1]})

    result = bc._get_available_additional_columns(data, "key", "sid", analysis)

    assert "extra_col" in result
    assert "other" in result
    assert "key" not in result
    assert "sid" not in result


def test_render_additional_columns_selector_fragment(bc):
    """_render_additional_columns_selector returns two lists via reload context."""
    survey_data = pl.DataFrame({"key": [1], "extra_a": ["x"]})
    backcheck_data = pl.DataFrame({"key": [1], "extra_b": ["y"]})
    analysis = pl.DataFrame({"key": [1]})

    result = bc._render_additional_columns_selector(
        survey_data, backcheck_data, "key", "sid", analysis
    )

    assert isinstance(result, tuple)
    assert len(result) == 2


def test_render_backchecker_productivity_table_fragment(bc):
    """_render_backchecker_productivity_table runs via reload context."""
    data = pl.DataFrame(
        {
            "date": pl.Series(["2024-01-15", "2024-01-20"]).str.to_date(),
            "backchecker": ["alice", "alice"],
        }
    )
    bc.st.pills.return_value = "Day"
    bc.st.selectbox.return_value = "Monday"
    bc._render_backchecker_productivity_table(
        data, "date", "backchecker", "settings.json"
    )


def test_render_enum_bcer_stats_table_fragment(bc):
    """_render_enum_bcer_stats_table runs without error in reload context."""
    survey_data = pl.DataFrame(
        {
            "key": [1, 2],
            "sid": ["a", "b"],
            "enumerator": ["alice", "bob"],
        }
    )
    backcheck_data = pl.DataFrame(
        {
            "key": [1, 2],
            "backchecker": ["charlie", "charlie"],
        }
    )
    analysis = pl.DataFrame(
        {
            "key": [1, 2],
            "column_name": ["age", "age"],
            "survey_value": ["25", "30"],
            "backcheck_value": ["25", "31"],
            "match_status": ["match", "mismatch"],
            "category": [1, 1],
        }
    )
    settings = bc.BackcheckSettings(
        survey_key="key",
        survey_id="sid",
        enumerator="enumerator",
        backchecker="backchecker",
    )
    bc.st.pills.return_value = "Enumerator"
    bc._render_enum_bcer_stats_table(
        survey_data, backcheck_data, analysis, settings, "settings.json"
    )


def test_render_backcheck_comparison_results_fragment(bc):
    """_render_backcheck_comparison_results works in reload context."""
    analysis = pl.DataFrame(
        {
            "key": [1],
            "column_name": ["age"],
            "survey_value": ["25"],
            "backcheck_value": ["26"],
            "match_status": ["mismatch"],
            "category": [1],
        }
    )
    survey_data = pl.DataFrame({"key": [1], "age": [25]})
    backcheck_data = pl.DataFrame({"key": [1], "age": [26]})
    settings = bc.BackcheckSettings(survey_key="key", survey_id="sid")

    bc.st.multiselect.return_value = []
    bc.st.pills.return_value = "All Results"
    bc._render_backcheck_comparison_results(
        survey_data, backcheck_data, analysis, settings
    )


def test_render_backcheck_summary_no_key_no_enum_no_bcer(patched_bc):
    """_render_backcheck_summary hits else branches when key/enum/bcer are None."""
    survey_data = pl.DataFrame({"col1": [1, 2]})
    backcheck_data = pl.DataFrame({"col1": [1]})
    analysis = pl.DataFrame()
    settings = BackcheckSettings(survey_key=None, enumerator=None, backchecker=None)
    _render_backcheck_summary(survey_data, backcheck_data, analysis, settings)
    patched_bc.metric.assert_called()


def test_render_backchecker_productivity_empty_date(patched_bc):
    """_render_backchecker_productivity shows info when date is empty."""
    _render_backchecker_productivity(pl.DataFrame(), "", "bcer", "settings.json")
    patched_bc.info.assert_called()


def test_render_backchecker_productivity_valid_params(patched_bc):
    """_render_backchecker_productivity calls table fragment when params are valid."""
    with patch(
        "datasure.checks.backchecks.report_ui._render_backchecker_productivity_table"
    ):
        _render_backchecker_productivity(
            pl.DataFrame(), "date", "bcer", "settings.json"
        )


def test_render_column_stats_empty_column_names(patched_bc):
    """_render_column_stats shows info when analysis has only null column names."""
    analysis = pl.DataFrame({"column_name": pl.Series([None], dtype=pl.Utf8)})
    _render_column_stats(pl.DataFrame(), analysis)
    patched_bc.info.assert_called()


def test_render_enum_bcer_stats_table_empty_stats_bc(bc):
    """_render_enum_bcer_stats_table shows info when compute returns empty stats."""
    analysis = pl.DataFrame({"key": [1]})
    settings = bc.BackcheckSettings(
        survey_key="key", survey_id=None, enumerator="enumerator"
    )
    bc.st.pills.return_value = "Enumerator"
    bc._render_enum_bcer_stats_table(
        pl.DataFrame({"key": [1]}),
        pl.DataFrame({"key": [1]}),
        analysis,
        settings,
        "settings.json",
    )
    bc.st.info.assert_called()


def test_render_backcheck_comparison_results_filtered_empty(patched_bc):
    """_render_backcheck_comparison_results shows info when filter yields empty."""
    analysis = pl.DataFrame(
        {
            "key": [1],
            "column_name": ["age"],
            "survey_value": ["25"],
            "backcheck_value": ["25"],
            "match_status": ["match"],
            "category": [1],
        }
    )
    patched_bc.pills.return_value = "Mismatches Only"
    with patch(
        "datasure.checks.backchecks.report_ui._render_additional_columns_selector",
        return_value=([], []),
    ):
        _render_backcheck_comparison_results(
            pl.DataFrame({"key": [1]}),
            pl.DataFrame({"key": [1]}),
            analysis,
            BackcheckSettings(survey_key="key", survey_id="sid"),
        )
    patched_bc.info.assert_called()


def test_render_backchecks_column_actions_non_empty(patched_bc):
    """_render_backchecks_column_actions calls settings table for non-empty config."""
    settings_df = pl.DataFrame(
        {
            "search_type": pl.Series(["exact"], dtype=pl.Utf8),
            "pattern": pl.Series(["age"], dtype=pl.Utf8),
            "column_name": pl.Series([["age"]], dtype=pl.List(pl.Utf8)),
            "category": pl.Series([1], dtype=pl.Int64),
            "ok_range_type": pl.Series([None], dtype=pl.Utf8),
            "ok_range_values": pl.Series([None], dtype=pl.List(pl.Float64)),
            "ttest": pl.Series([False], dtype=pl.Boolean),
            "prtest": pl.Series([False], dtype=pl.Boolean),
            "signrank": pl.Series([False], dtype=pl.Boolean),
            "reliability": pl.Series([False], dtype=pl.Boolean),
        }
    )
    with patch(
        "datasure.checks.backchecks.report_ui.duckdb_get_table",
        return_value=settings_df,
    ):
        _render_backchecks_column_actions(
            "proj_id",
            "page_id",
            pl.DataFrame({"key": [1]}),
            pl.DataFrame({"key": [1]}),
            ["key"],
        )
    patched_bc.dataframe.assert_called()


def test_update_backcheck_column_config_concat_existing(patched_bc):
    """_update_backcheck_column_config concatenates new config with existing."""
    existing = pl.DataFrame(
        {
            "search_type": pl.Series(["exact"], dtype=pl.Utf8),
            "pattern": pl.Series([None], dtype=pl.Utf8),
            "column_name": pl.Series([["age"]], dtype=pl.List(pl.Utf8)),
            "category": pl.Series([1], dtype=pl.Int64),
            "ok_range_type": pl.Series([None], dtype=pl.Utf8),
            "ok_range_values": pl.Series([None], dtype=pl.List(pl.Float64)),
            "ttest": pl.Series([False], dtype=pl.Boolean),
            "prtest": pl.Series([False], dtype=pl.Boolean),
            "signrank": pl.Series([False], dtype=pl.Boolean),
            "reliability": pl.Series([False], dtype=pl.Boolean),
        }
    )
    with patch(
        "datasure.checks.backchecks.report_ui.duckdb_get_table", return_value=existing
    ):
        _update_backcheck_column_config(
            "proj_id",
            "page_id",
            "exact",
            None,
            ["income"],
            2,
            OkRangeOptions(),
            BackcheckTestOptions(),
        )


def test_render_backchecker_productivity_table_week_bc(bc):
    """_render_backchecker_productivity_table renders weekday selector for Week."""
    data = pl.DataFrame(
        {
            "date": pl.Series(["2024-01-15", "2024-01-20"]).str.to_date(),
            "backchecker": ["alice", "alice"],
        }
    )
    bc.st.pills.return_value = "Week"
    bc.st.selectbox.return_value = "Monday"
    bc._render_backchecker_productivity_table(
        data, "date", "backchecker", "settings.json"
    )


def test_render_backcheck_comparison_results_empty_display(patched_bc):
    """_render_backcheck_comparison_results shows info when display is empty."""
    analysis = pl.DataFrame(
        {
            "key": [1],
            "column_name": ["age"],
            "survey_value": pl.Series([None], dtype=pl.Utf8),
            "backcheck_value": pl.Series([None], dtype=pl.Utf8),
            "match_status": ["match"],
            "category": [1],
        }
    )
    with patch(
        "datasure.checks.backchecks.report_ui._render_additional_columns_selector",
        return_value=([], []),
    ):
        _render_backcheck_comparison_results(
            pl.DataFrame({"key": [1]}),
            pl.DataFrame({"key": [1]}),
            analysis,
            BackcheckSettings(survey_key="key", survey_id="sid"),
        )
    patched_bc.info.assert_called()
