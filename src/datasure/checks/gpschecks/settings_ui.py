from __future__ import annotations

import streamlit as st

from datasure.checks.gpschecks.compute import load_default_gpschecks_settings
from datasure.checks.gpschecks.models import TAB_NAME
from datasure.models.schemas import GPSSettings
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.secure_credentials import (
    SecureCredentialError,
    retrieve_mapbox_token,
    store_mapbox_token,
)
from datasure.utils.settings_utils import save_check_settings, trigger_save


#  gps check settings
@demo_output_onboarding(TAB_NAME)
def gpschecks_report_settings(
    settings_file: str,
    config: GPSSettings,
    categorical_columns: list[str],
    datetime_columns: list[str],
) -> GPSSettings:
    """Create and render the settings UI for gpschecks report configuration.

    This function creates a comprehensive Streamlit UI for configuring
    gpschecks report settings. It includes:
    - Survey identifiers (key and ID columns)
    - Survey date column selection
    - Enumerator ID and team columns
    - The Mapbox API token

    Settings are automatically saved to the settings file when changed
    and loaded from previous sessions if available.

    Parameters
    ----------
    settings_file : str
        Path to settings file for saving/loading configurations.
    config : GPSSettings
        Default configuration used as fallback values.
    categorical_columns : list[str]
        Available categorical columns for selection (survey key, ID,
        enumerator, team).
    datetime_columns : list[str]
        Available datetime columns for date selection.

    Returns
    -------
    GPSSettings
        User-configured settings from the UI.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for GPS CHecks report")
        st.write("---")

        defaults = load_default_gpschecks_settings(settings_file, config)

        def select(
            setting: str, label: str, options: list[str], help_text: str
        ) -> str | None:
            return _column_select(
                settings_file, setting, label, options, defaults, help_text
            )

        # Survey Identifiers
        with st.container(border=True):
            st.subheader("Survey Identifiers")
            si1, si2, _ = st.columns(3)
            with si1:
                survey_key = select(
                    "survey_key",
                    "Survey Key",
                    categorical_columns,
                    "Select the column that contains the survey key",
                )
            with si2:
                survey_id = select(
                    "survey_id",
                    "Survey ID",
                    categorical_columns,
                    "Select the column that contains the survey ID",
                )

        with st.container(border=True):
            st.subheader("Survey Date")
            sd1, _, _ = st.columns(3)
            with sd1:
                survey_date = select(
                    "survey_date",
                    "Survey Date",
                    datetime_columns,
                    "Select the column that contains the survey date",
                )

        with st.container(border=True):
            st.subheader("Enumerator")
            ec1, ec2, _ = st.columns(3)
            with ec1:
                enumerator = select(
                    "enumerator",
                    "Enumerator ID",
                    categorical_columns,
                    "Select the column that contains the enumerator ID",
                )
            with ec2:
                team = select(
                    "team",
                    "Team",
                    categorical_columns,
                    "Select the column that contains the team identifier",
                )

        mapbox_token = _render_mapbox_token_settings()

    return GPSSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        enumerator=enumerator,
        team=team,
        mapbox_custom_key=mapbox_token,
    )


def _column_select(
    settings_file: str,
    setting: str,
    label: str,
    options: list[str],
    defaults: GPSSettings,
    help_text: str,
) -> str | None:
    """Render a column selectbox for `setting` and save the choice.

    The saved value preselects the box if it is still one of `options`.
    """
    default = getattr(defaults, setting)
    selected = st.selectbox(
        label,
        options=options,
        key=f"{setting}_gpschecks",
        help=help_text,
        index=options.index(default) if default in options else None,
        on_change=trigger_save,
        kwargs={"state_name": f"{TAB_NAME}_{setting}"},
    )
    save_check_settings(settings_file, TAB_NAME, {setting: selected})
    return selected


def _render_mapbox_token_settings() -> str | None:
    """Render the Mapbox token input and save button.

    Returns
    -------
    str | None
        The token to use: the one entered, or the saved one if the box is
        empty.
    """
    with st.container(border=True):
        st.subheader("Mapbox API Token Configuration")
        st.caption("Configure your Mapbox API key for map visualizations. ")

        # Saved tokens live in the system keyring. A token set by hand in
        # secrets.toml is still read, for setups made before that.
        saved_mapbox_token = retrieve_mapbox_token() or st.secrets.get(
            "mapbox_token", None
        )

        mt1, mt2 = st.columns([0.7, 0.3])
        with mt1:
            mapbox_custom_token = st.text_input(
                "Your Mapbox API Key",
                value=saved_mapbox_token,
                type="password",
                key="mapbox_custom_token_gpschecks",
                help="Enter your Mapbox API key. Get one free at https://account.mapbox.com/",
            )
        with mt2:
            st.write("")
            if st.button(
                "Save Mapbox Token",
                key="save_mapbox_token_gpschecks",
                type="primary",
                width="stretch",
                disabled=not mapbox_custom_token,
            ):
                _save_mapbox_token(mapbox_custom_token)

    # An emptied box falls back to the saved token.
    return (mapbox_custom_token or "").strip() or saved_mapbox_token


def _save_mapbox_token(token: str) -> None:
    """Store the token in the keyring and report the outcome."""
    try:
        store_mapbox_token(token)
    except SecureCredentialError as e:
        # UI boundary: report a keyring failure, keep the page.
        st.error(f"Mapbox token not saved: {e}")
    else:
        st.success("Mapbox Token saved successfully.")
