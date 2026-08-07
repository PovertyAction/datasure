from unittest.mock import MagicMock, patch

from datasure.checks.gpschecks.settings_ui import gpschecks_report_settings
from datasure.models.schemas import GPSSettings

# =============================================================================
# Tests for gpschecks_report_settings
# =============================================================================


@patch("datasure.checks.gpschecks.settings_ui.save_secrets")
@patch("datasure.checks.gpschecks.settings_ui.save_check_settings")
@patch("datasure.checks.gpschecks.settings_ui.load_default_gpschecks_settings")
@patch("datasure.checks.gpschecks.settings_ui.st.secrets", {})
@patch("datasure.checks.gpschecks.settings_ui.st.button")
@patch("datasure.checks.gpschecks.settings_ui.st.text_input")
@patch("datasure.checks.gpschecks.settings_ui.st.selectbox")
@patch("datasure.checks.gpschecks.settings_ui.st.columns")
@patch("datasure.checks.gpschecks.settings_ui.st.container")
@patch("datasure.checks.gpschecks.settings_ui.st.expander")
@patch("datasure.checks.gpschecks.settings_ui.st.write")
@patch("datasure.checks.gpschecks.settings_ui.st.subheader")
@patch("datasure.checks.gpschecks.settings_ui.st.markdown")
@patch("datasure.checks.gpschecks.settings_ui.st.caption")
def test_gpschecks_report_settings_ui(
    mock_caption,
    mock_markdown,
    mock_subheader,
    mock_write,
    mock_expander,
    mock_container,
    mock_columns,
    mock_selectbox,
    mock_text_input,
    mock_button,
    mock_load,
    mock_save,
    mock_save_secrets,
):
    """Test GPS report settings UI rendering."""
    mock_load.return_value = GPSSettings(
        survey_key="key",
        survey_id="id",
        survey_date="date",
        enumerator="enum",
        team="team",
    )

    expander_ctx = MagicMock()
    expander_ctx.__enter__ = lambda s: s
    expander_ctx.__exit__ = MagicMock(return_value=False)
    mock_expander.return_value = expander_ctx

    container_ctx = MagicMock()
    container_ctx.__enter__ = lambda s: s
    container_ctx.__exit__ = MagicMock(return_value=False)
    mock_container.return_value = container_ctx

    col_mock = MagicMock()
    col_mock.__enter__ = lambda s: s
    col_mock.__exit__ = MagicMock(return_value=False)

    def columns_side_effect(arg, **kwargs):
        if isinstance(arg, list):
            return [col_mock] * len(arg)
        return [col_mock] * arg

    mock_columns.side_effect = columns_side_effect

    mock_selectbox.return_value = "key"
    mock_text_input.return_value = ""
    mock_button.return_value = False

    config = GPSSettings(survey_key="key")
    result = gpschecks_report_settings(
        "settings.json", config, ["key", "id", "enum"], ["date"]
    )
    assert isinstance(result, GPSSettings)


# =============================================================================
# Tests for mapbox token in report settings
# =============================================================================


@patch("datasure.checks.gpschecks.settings_ui.save_secrets")
@patch("datasure.checks.gpschecks.settings_ui.save_check_settings")
@patch("datasure.checks.gpschecks.settings_ui.load_default_gpschecks_settings")
@patch(
    "datasure.checks.gpschecks.settings_ui.st.secrets",
    {"mapbox_token": "existing_token"},
)
@patch("datasure.checks.gpschecks.settings_ui.st.button")
@patch("datasure.checks.gpschecks.settings_ui.st.text_input")
@patch("datasure.checks.gpschecks.settings_ui.st.selectbox")
@patch("datasure.checks.gpschecks.settings_ui.st.columns")
@patch("datasure.checks.gpschecks.settings_ui.st.container")
@patch("datasure.checks.gpschecks.settings_ui.st.expander")
@patch("datasure.checks.gpschecks.settings_ui.st.write")
@patch("datasure.checks.gpschecks.settings_ui.st.subheader")
@patch("datasure.checks.gpschecks.settings_ui.st.markdown")
@patch("datasure.checks.gpschecks.settings_ui.st.caption")
def test_gpschecks_report_settings_with_mapbox_token(
    mock_caption,
    mock_markdown,
    mock_subheader,
    mock_write,
    mock_expander,
    mock_container,
    mock_columns,
    mock_selectbox,
    mock_text_input,
    mock_button,
    mock_load,
    mock_save,
    mock_save_secrets,
):
    """Test GPS settings UI with existing mapbox token."""
    mock_load.return_value = GPSSettings(survey_key="key")

    expander_ctx = MagicMock()
    expander_ctx.__enter__ = lambda s: s
    expander_ctx.__exit__ = MagicMock(return_value=False)
    mock_expander.return_value = expander_ctx

    container_ctx = MagicMock()
    container_ctx.__enter__ = lambda s: s
    container_ctx.__exit__ = MagicMock(return_value=False)
    mock_container.return_value = container_ctx

    col_mock = MagicMock()
    col_mock.__enter__ = lambda s: s
    col_mock.__exit__ = MagicMock(return_value=False)

    def columns_side_effect(arg, **kwargs):
        if isinstance(arg, list):
            return [col_mock] * len(arg)
        return [col_mock] * arg

    mock_columns.side_effect = columns_side_effect

    mock_selectbox.return_value = "key"
    mock_text_input.return_value = "new_token"
    mock_button.return_value = True  # save button clicked

    config = GPSSettings(survey_key="key")
    result = gpschecks_report_settings("settings.json", config, ["key"], ["date"])
    assert isinstance(result, GPSSettings)
    mock_save_secrets.assert_called_once()
