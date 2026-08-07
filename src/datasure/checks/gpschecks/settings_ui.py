from __future__ import annotations

import streamlit as st

from datasure.checks.gpschecks.compute import load_default_gpschecks_settings
from datasure.checks.gpschecks.models import TAB_NAME
from datasure.models.schemas import GPSSettings
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import (
    save_check_settings,
    save_secrets,
    trigger_save,
)


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
    - Enumerator ID column

    Settings are automatically saved to the settings file when changed
    and loaded from previous sessions if available.

    Parameters
    ----------
    project_id : str
        Unique project identifier for database operations.
    settings_file : str
        Path to settings file for saving/loading configurations.
    data : pl.DataFrame
        Dataset to analyze for duplicates.
    config : DuplicatesSettings
        Default configuration used as fallback values.
    categorical_columns : list[str]
        Available categorical columns for selection (survey key, ID, enumerator).
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

        default_settings = load_default_gpschecks_settings(settings_file, config)

        # Survey Identifiers
        with st.container(border=True):
            st.subheader("Survey Identifiers")
            si1, si2, _ = st.columns(3)

            with si1:
                default_survey_key = default_settings.survey_key
                default_survey_key_index = (
                    categorical_columns.index(default_survey_key)
                    if default_survey_key and default_survey_key in categorical_columns
                    else None
                )
                survey_key = st.selectbox(
                    "Survey Key",
                    options=categorical_columns,
                    key="survey_key_gpschecks",
                    help="Select the column that contains the survey key",
                    index=default_survey_key_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_key"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_key": survey_key})

            with si2:
                default_survey_id = default_settings.survey_id
                default_survey_id_index = (
                    categorical_columns.index(default_survey_id)
                    if default_survey_id and default_survey_id in categorical_columns
                    else None
                )
                survey_id = st.selectbox(
                    "Survey ID",
                    options=categorical_columns,
                    help="Select the column that contains the survey ID",
                    key="survey_id_gpschecks",
                    index=default_survey_id_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_id"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_id": survey_id})

        with st.container(border=True):
            st.subheader("Survey Date")

            sd1, _, _ = st.columns(3)

            with sd1:
                default_survey_date = default_settings.survey_date
                default_survey_date_index = (
                    datetime_columns.index(default_survey_date)
                    if default_survey_date and default_survey_date in datetime_columns
                    else None
                )

                survey_date = st.selectbox(
                    "Survey Date",
                    options=datetime_columns,
                    help="Select the column that contains the survey date",
                    key="survey_date_gpschecks",
                    index=default_survey_date_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_date"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"survey_date": survey_date}
                )

        with st.container(border=True):
            st.subheader("Enumerator")
            ec1, ec2, _ = st.columns(3)
            with ec1:
                default_enumerator = default_settings.enumerator
                default_enumerator_index = (
                    categorical_columns.index(default_enumerator)
                    if default_enumerator and default_enumerator in categorical_columns
                    else None
                )
                enumerator = st.selectbox(
                    "Enumerator ID",
                    options=categorical_columns,
                    key="enumerator_gpschecks",
                    help="Select the column that contains the enumerator ID",
                    index=default_enumerator_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_enumerator"},
                )
                save_check_settings(settings_file, TAB_NAME, {"enumerator": enumerator})

            with ec2:
                default_team = default_settings.team
                default_team_index = (
                    categorical_columns.index(default_team)
                    if default_team and default_team in categorical_columns
                    else None
                )
                team = st.selectbox(
                    "Team",
                    options=categorical_columns,
                    key="team_gpschecks",
                    help="Select the column that contains the team identifier",
                    index=default_team_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_team"},
                )
                save_check_settings(settings_file, TAB_NAME, {"team": team})

        # Mapbox API Key Configuration
        with st.container(border=True):
            st.subheader("Mapbox API Token Configuration")
            st.caption("Configure your Mapbox API key for map visualizations. ")

            current_mapbox_token = st.secrets.get("mapbox_token", None)

            # Show text input if user wants to add own key
            mt1, mt2 = st.columns([0.7, 0.3])
            with mt1:
                mapbox_custom_token = st.text_input(
                    "Your Mapbox API Key",
                    value=current_mapbox_token,
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
                    save_secrets("mapbox_token", mapbox_custom_token)
                    st.success("Mapbox Token saved successfully.")

    return GPSSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        enumerator=enumerator,
        team=team,
        mapbox_custom_key=mapbox_custom_token,
    )
