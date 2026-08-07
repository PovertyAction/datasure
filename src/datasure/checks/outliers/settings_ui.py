"""Settings UI for the outliers report."""

import streamlit as st

from datasure.checks.outliers.compute import load_default_settings
from datasure.checks.outliers.models import TAB_NAME, OutlierSettings
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import save_check_settings, trigger_save


@demo_output_onboarding(TAB_NAME)
def outliers_report_settings(
    settings_file: str,
    config: OutlierSettings,
    categorical_columns: list[str],
    datetime_columns: list[str],
) -> OutlierSettings:
    """Create a settings UI for outliers report configuration.

    This function creates the comprehensive Streamlit UI for configuring
    outlier detection settings. Due to its complexity (UI rendering),
    it maintains a higher cognitive complexity but is well-structured.

    Parameters
    ----------
    settings_file : str
        Path to settings file.
    config : OutlierSettings
        Default configuration.
    categorical_columns : list[str]
        List of categorical columns.
    datetime_columns : list[str]
        List of datetime columns.

    Returns
    -------
    OutlierSettings
        User-configured settings.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for outliers report")
        st.write("---")

        # Load default settings
        default_settings = load_default_settings(settings_file, config)

        # Survey Identifiers
        with st.container(border=True):
            st.markdown("#### Survey Identifiers")
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
                    key="survey_key_outliers",
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
                    key="survey_id_outliers",
                    index=default_survey_id_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_id"},
                )
                save_check_settings(settings_file, TAB_NAME, {"survey_id": survey_id})

        with st.container(border=True):
            st.markdown("#### Survey Date")

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
                    key="survey_date_outliers",
                    index=default_survey_date_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_survey_date"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"survey_date": survey_date}
                )

        with st.container(border=True):
            st.markdown("#### Enumerator & Team")
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
                    key="enumerator_outliers",
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
                    "Team ID",
                    options=categorical_columns,
                    key="team_outliers",
                    help="Select the column that contains the team ID",
                    index=default_team_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_team"},
                )
                save_check_settings(settings_file, TAB_NAME, {"team": team})

    return OutlierSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        enumerator=enumerator,
        team=team,
    )
