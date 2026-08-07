"""Tests for datasure.checks.backchecks.settings_ui."""

import importlib
import sys
from unittest.mock import MagicMock, patch

import pytest

from datasure.checks.backchecks.models import BackcheckSettings, StrCompareOptions
from datasure.checks.backchecks.settings_ui import (
    _get_default_index,
    _render_additional_options,
    _render_date_columns,
    _render_duplicate_handling,
    _render_selectbox_with_save,
    _render_staff_identifiers,
    _render_survey_identifiers,
    _render_tracking_options,
    _render_value_list_display,
)
from tests.checks.backchecks.conftest import make_mock_st

# ============================================
# PATCHED_BC FIXTURE (patch st in settings_ui for non-fragment UI tests)
# ============================================


@pytest.fixture
def patched_bc():
    """Patch settings_ui module's st and utility deps for non-fragment UI tests."""
    mock_st = make_mock_st()
    with (
        patch("datasure.checks.backchecks.settings_ui.st", mock_st),
        patch("datasure.checks.backchecks.settings_ui.save_check_settings"),
        patch(
            "datasure.checks.backchecks.settings_ui.load_check_settings",
            return_value={},
        ),
        patch("datasure.checks.backchecks.settings_ui.trigger_save"),
    ):
        yield mock_st


# ============================================
# BC FIXTURE (reload compute/settings_ui with mocked streamlit)
# ============================================


@pytest.fixture
def bc():
    """Reload settings_ui (and compute) with mocked Streamlit to strip fragments."""
    mock_st = make_mock_st()
    original_st = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock_st

    import datasure.checks.backchecks.compute as compute_module
    import datasure.checks.backchecks.settings_ui as settings_ui_module

    try:
        # Reload in dependency order so decorators pick up the mocked st.
        importlib.reload(compute_module)
        importlib.reload(settings_ui_module)

        settings_ui_module.load_check_settings = MagicMock(return_value={})
        settings_ui_module.save_check_settings = MagicMock()
        settings_ui_module.trigger_save = MagicMock()

        yield settings_ui_module
    finally:
        if original_st is not None:
            sys.modules["streamlit"] = original_st
        else:
            sys.modules.pop("streamlit", None)
        importlib.reload(compute_module)
        importlib.reload(settings_ui_module)


# ============================================
# SETTINGS UI TESTS
# ============================================


def test_get_default_index_valid():
    """Test _get_default_index with valid default value."""
    options = ["option1", "option2", "option3"]

    result = _get_default_index("option2", options)

    assert result == 1


def test_get_default_index_invalid():
    """Test _get_default_index with invalid default value."""
    options = ["option1", "option2", "option3"]

    result = _get_default_index("option4", options)

    assert result is None


def test_get_default_index_none():
    """Test _get_default_index with None default value."""
    options = ["option1", "option2", "option3"]

    result = _get_default_index(None, options)

    assert result is None


def test_render_selectbox_with_save(patched_bc):
    """_render_selectbox_with_save calls st.selectbox and returns selection."""
    patched_bc.selectbox.return_value = "col_a"
    result = _render_selectbox_with_save(
        "Label", ["col_a", "col_b"], "key", "settings.json", "setting_key", None, "help"
    )
    assert result == "col_a"


def test_render_survey_identifiers(patched_bc):
    """_render_survey_identifiers returns (survey_key, survey_id) tuple."""
    patched_bc.selectbox.return_value = "key_col"
    result = _render_survey_identifiers(
        "settings.json", BackcheckSettings(survey_key=None), ["key_col", "id_col"]
    )
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_render_date_columns(patched_bc):
    """_render_date_columns returns (survey_date, backcheck_date) tuple."""
    patched_bc.selectbox.return_value = "date_col"
    result = _render_date_columns(
        "settings.json",
        BackcheckSettings(survey_key=None),
        ["date_col"],
        ["bc_date_col"],
    )
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_render_staff_identifiers(patched_bc):
    """_render_staff_identifiers returns (enumerator, backchecker) tuple."""
    patched_bc.selectbox.return_value = "enum_col"
    result = _render_staff_identifiers(
        "settings.json",
        BackcheckSettings(survey_key=None),
        ["enum_col"],
        ["bc_enum_col"],
    )
    assert isinstance(result, tuple)
    assert len(result) == 2


def test_render_tracking_options(patched_bc):
    """_render_tracking_options returns a numeric backcheck_goal."""
    patched_bc.number_input.return_value = 50
    result = _render_tracking_options(
        "settings.json", BackcheckSettings(survey_key=None)
    )
    assert result == 50


def test_render_duplicate_handling(patched_bc):
    """_render_duplicate_handling returns selected option string."""
    patched_bc.pills.return_value = "drop"
    result = _render_duplicate_handling(
        "settings.json", BackcheckSettings(survey_key=None)
    )
    assert result == "drop"


def test_render_value_list_display_with_values(patched_bc):
    """_render_value_list_display shows info when values exist."""
    _render_value_list_display(["val1", "val2"], "Has values", "No values", "help")
    patched_bc.info.assert_called_once()


def test_render_value_list_display_empty(patched_bc):
    """_render_value_list_display shows warning when list is empty."""
    _render_value_list_display([], "Has values", "No values configured", "help")
    patched_bc.warning.assert_called_once()


def test_render_additional_options(patched_bc):
    """_render_additional_options returns 4-tuple of settings."""
    with (
        patch(
            "datasure.checks.backchecks.settings_ui._render_no_differences_settings",
            return_value=[],
        ),
        patch(
            "datasure.checks.backchecks.settings_ui._render_exclude_values_settings",
            return_value=[],
        ),
        patch(
            "datasure.checks.backchecks.settings_ui._render_string_comparison_options",
            return_value=StrCompareOptions(),
        ),
        patch(
            "datasure.checks.backchecks.settings_ui.load_default_backchecks_settings",
            return_value=BackcheckSettings(survey_key=None),
        ),
    ):
        result = _render_additional_options(
            "settings.json", BackcheckSettings(survey_key=None)
        )

    assert isinstance(result, tuple)
    assert len(result) == 4


def test_render_no_differences_settings_fragment(bc):
    """_render_no_differences_settings runs without error and returns a list."""
    result = bc._render_no_differences_settings("settings.json")
    assert isinstance(result, list)


def test_render_string_comparison_options_fragment(bc):
    """_render_string_comparison_options returns a StrCompareOptions object."""
    result = bc._render_string_comparison_options("settings.json")
    assert hasattr(result, "case_option")
    assert hasattr(result, "trimspaces_option")


def test_render_exclude_values_settings_fragment(bc):
    """_render_exclude_values_settings runs without error and returns a list."""
    result = bc._render_exclude_values_settings("settings.json")
    assert isinstance(result, list)
