from unittest.mock import MagicMock, patch

from datasure.checks.gpschecks.settings_ui import gpschecks_report_settings
from datasure.models.schemas import GPSSettings
from datasure.utils.secure_credentials import SecureCredentialError

# =============================================================================
# Tests for gpschecks_report_settings
# =============================================================================


@patch("datasure.checks.gpschecks.settings_ui.retrieve_mapbox_token", return_value=None)
@patch("datasure.checks.gpschecks.settings_ui.store_mapbox_token")
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
    mock_store_token,
    mock_retrieve_token,
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


@patch("datasure.checks.gpschecks.settings_ui.retrieve_mapbox_token", return_value=None)
@patch("datasure.checks.gpschecks.settings_ui.store_mapbox_token")
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
    mock_store_token,
    mock_retrieve_token,
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
    mock_store_token.assert_called_once_with("new_token")


MODULE = "datasure.checks.gpschecks.settings_ui"


def _render_mapbox(
    keyring_token=None, secrets=None, typed="", clicked=False, store_error=None
):
    """Render the settings with the Mapbox text box holding `typed`."""
    st_mock = MagicMock()
    st_mock.secrets = secrets or {}
    st_mock.columns.side_effect = lambda spec, **kw: [
        MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))
    ]
    st_mock.selectbox.return_value = "key"
    st_mock.text_input.return_value = typed
    st_mock.button.return_value = clicked
    with (
        patch(f"{MODULE}.st", st_mock),
        patch(
            f"{MODULE}.load_default_gpschecks_settings",
            return_value=GPSSettings(survey_key="key"),
        ),
        patch(f"{MODULE}.save_check_settings"),
        patch(f"{MODULE}.retrieve_mapbox_token", return_value=keyring_token),
        patch(f"{MODULE}.store_mapbox_token", side_effect=store_error) as store,
    ):
        result = gpschecks_report_settings(
            "settings.json", GPSSettings(survey_key="key"), ["key"], []
        )
    return result, st_mock, store


class TestMapboxTokenPersistence:
    def test_the_saved_token_prefills_the_box(self):
        _, st_mock, _ = _render_mapbox(keyring_token="pk.saved", typed="pk.saved")
        assert st_mock.text_input.call_args.kwargs["value"] == "pk.saved"

    def test_the_saved_token_is_used_when_the_box_is_empty(self):
        result, _, _ = _render_mapbox(keyring_token="pk.saved", typed="")
        assert result.mapbox_custom_key == "pk.saved"

    def test_a_token_in_secrets_toml_is_still_read(self):
        result, st_mock, _ = _render_mapbox(secrets={"mapbox_token": "pk.toml"})
        assert st_mock.text_input.call_args.kwargs["value"] == "pk.toml"
        assert result.mapbox_custom_key == "pk.toml"

    def test_the_keyring_token_wins_over_secrets_toml(self):
        result, _, _ = _render_mapbox(
            keyring_token="pk.saved", secrets={"mapbox_token": "pk.toml"}
        )
        assert result.mapbox_custom_key == "pk.saved"

    def test_save_stores_the_typed_token_in_the_keyring(self):
        result, st_mock, store = _render_mapbox(typed="pk.new", clicked=True)
        store.assert_called_once_with("pk.new")
        st_mock.success.assert_called_once()
        assert result.mapbox_custom_key == "pk.new"

    def test_a_failed_save_shows_an_error(self):
        error = SecureCredentialError("no keyring backend")
        _, st_mock, _ = _render_mapbox(typed="pk.new", clicked=True, store_error=error)
        st_mock.error.assert_called_once()
        assert "no keyring backend" in st_mock.error.call_args.args[0]
        st_mock.success.assert_not_called()

    def test_nothing_is_stored_without_a_click(self):
        _, _, store = _render_mapbox(typed="pk.new", clicked=False)
        store.assert_not_called()
