"""Tests for datasure.checks.outliers.settings_ui."""

import importlib
import sys
from unittest.mock import patch

import pytest

from datasure.checks.outliers.models import OutlierSettings
from tests.checks.outliers.conftest import _make_st_mock

# ============================================================================
# SETTINGS_UI_MOD FIXTURE (reload compute/settings_ui with mocked streamlit)
# ============================================================================


@pytest.fixture
def settings_ui_mod():
    """Reload compute/settings_ui with mocked Streamlit and onboarding decorator."""
    mock_st = _make_st_mock()
    original_st = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock_st

    import datasure.checks.outliers.compute as compute_module
    import datasure.checks.outliers.settings_ui as settings_ui_module

    try:
        with patch(
            "datasure.utils.onboarding_utils.demo_output_onboarding",
            lambda tab: lambda f: f,
        ):
            importlib.reload(compute_module)
            importlib.reload(settings_ui_module)
        yield settings_ui_module
    finally:
        if original_st is not None:
            sys.modules["streamlit"] = original_st
        else:
            sys.modules.pop("streamlit", None)
        importlib.reload(compute_module)
        importlib.reload(settings_ui_module)


# ============================================================================
# TESTS: outliers_report_settings (via reimport)
# ============================================================================


class TestOutliersReportSettings:
    """Test outliers_report_settings function."""

    def test_returns_outlier_settings(self, settings_ui_mod):
        config = OutlierSettings(
            survey_key="survey_key",
            survey_id="survey_id",
            survey_date="survey_date",
            enumerator="enumerator",
            team="team",
        )
        with (
            patch(
                "datasure.checks.outliers.settings_ui.load_default_settings",
                return_value=config,
            ),
            patch("datasure.checks.outliers.settings_ui.save_check_settings"),
            patch("datasure.checks.outliers.settings_ui.trigger_save"),
        ):
            settings_ui_mod.st.selectbox.return_value = "survey_key"
            result = settings_ui_mod.outliers_report_settings(
                "settings.json",
                config,
                ["survey_key", "survey_id", "enumerator", "team"],
                ["survey_date"],
            )
        assert isinstance(result, settings_ui_mod.OutlierSettings)
