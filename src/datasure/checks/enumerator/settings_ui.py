"""Settings UI for the enumerator performance report."""

import polars as pl
import streamlit as st

from datasure.checks.enumerator.models import (
    TAB_NAME,
    ConsentOutcomeSettings,
    EnumeratorSettings,
)
from datasure.utils.duckdb_utils import duckdb_save_table
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

# =============================================================================
# Settings Management Functions
# =============================================================================


@st.cache_data(ttl=60)
def load_default_enumerator_settings(
    settings_file: str, config: EnumeratorSettings
) -> EnumeratorSettings:
    """Load and merge saved settings with default configuration.

    Loads previously saved duplicates report settings from the settings file
    and merges them with the provided default configuration. Saved settings
    take precedence over defaults.

    Cached for 60 seconds to reduce file I/O operations.

    Parameters
    ----------
    settings_file : str
        Path to the settings file containing saved configurations.
    config : DuplicatesSettings
        Default configuration to use as fallback for missing settings.

    Returns
    -------
    DuplicatesSettings
        Merged settings combining saved and default configurations.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME)

    default_settings: dict = dict(config)
    default_settings.update(saved_settings)

    return EnumeratorSettings(**default_settings)


@demo_output_onboarding(TAB_NAME)
def enumerator_report_settings(
    project_id: str,
    settings_file: str,
    data: pl.DataFrame,
    config: EnumeratorSettings,
    categorical_columns: list[str],
    datetime_columns: list[str],
) -> EnumeratorSettings:
    """Create and render the settings UI for duplicates report configuration.

    This function creates a comprehensive Streamlit UI for configuring
    duplicates report settings. It includes:
    - Survey identifiers (key and ID columns)
    - Survey date column selection
    - Enumerator ID column
    - Filtering conditions for targeted duplicate detection

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
    DuplicatesSettings
        User-configured settings from the UI.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for enumerator report")
        st.write("---")

        default_settings = load_default_enumerator_settings(settings_file, config)

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
                    key="survey_key_enumerator",
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
                    key="survey_id_enumerator",
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
                    key="survey_date_enumerator",
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
                    key="enumerator_enumerator",
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
                    key="team_enumerator",
                    help="Select the column that contains the team identifier",
                    index=default_team_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_team"},
                )
                save_check_settings(settings_file, TAB_NAME, {"team": team})

        with st.container(border=True):
            st.subheader("Survey Duration")
            dc1, dc2, _ = st.columns(3)
            with dc1:
                default_duration = default_settings.duration
                default_duration_index = (
                    categorical_columns.index(default_duration)
                    if default_duration and default_duration in categorical_columns
                    else None
                )
                duration = st.selectbox(
                    "Duration Column",
                    options=categorical_columns,
                    key="duration_enumerator",
                    help="Select the column that contains the survey duration in seconds",
                    index=default_duration_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_duration"},
                )
                save_check_settings(settings_file, TAB_NAME, {"duration": duration})

            with dc2:
                default_duration_unit = default_settings.duration_unit
                default_duration_unit_index = (
                    ["seconds", "minutes", "hours"].index(default_duration_unit)
                    if default_duration_unit in ["seconds", "minutes", "hours"]
                    else 0
                )
                duration_unit = st.selectbox(
                    "Duration Unit",
                    options=["seconds", "minutes", "hours"],
                    key="duration_unit_enumerator",
                    help="Select the unit for survey duration",
                    index=default_duration_unit_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_duration_unit"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"duration_unit": duration_unit}
                )

        with st.container(border=True):
            st.subheader("Form Version")
            fv1, _ = st.columns([1, 2])
            with fv1:
                default_formversion = default_settings.formversion
                default_formversion_index = (
                    categorical_columns.index(default_formversion)
                    if default_formversion
                    and default_formversion in categorical_columns
                    else None
                )
                formversion = st.selectbox(
                    "Form Version Column",
                    options=categorical_columns,
                    key="formversion_enumerator",
                    help="Select the column that contains the form version",
                    index=default_formversion_index,
                    on_change=trigger_save,
                    kwargs={"state_name": TAB_NAME + "_formversion"},
                )
                save_check_settings(
                    settings_file, TAB_NAME, {"formversion": formversion}
                )

        with st.container(border=True):
            st.subheader("Consent and Outcome Settings")
            st.info(
                "Configure consent and outcome columns along with their valid values."
            )

            _render_consent_outcome_settings(
                project_id, data, categorical_columns, settings_file
            )
            if st.session_state.get("st_apply_consent_outcome_enumerator"):
                st.success("Consent and outcome settings applied successfully.")
                st.session_state["st_apply_consent_outcome_enumerator"] = False

    return EnumeratorSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        enumerator=enumerator,
        team=team,
        formversion=formversion,
        duration=duration,
        duration_unit=duration_unit,
    )


@st.fragment
def _render_consent_outcome_settings(
    project_id: str, data: pl.DataFrame, categorical_columns: list, settings_file: str
) -> ConsentOutcomeSettings:
    """Render consent and outcome settings UI.

    Parameters
    ----------
    data : pl.DataFrame
        DataFrame containing survey data.
    settings_file : str
        Path to settings file for saving/loading configurations.

    Returns
    -------
    ConsentOutcomeSettings
        User-configured consent and outcome settings.
    """
    default_settings = load_check_settings(settings_file, TAB_NAME)

    with st.container(border=True):
        st.subheader("Consent Settings")
        co1, co2 = st.columns([0.3, 0.7])
        with co1:
            default_consent_col = default_settings.get("consent")
            default_consent_index = (
                categorical_columns.index(default_consent_col)
                if default_consent_col and default_consent_col in categorical_columns
                else 0
            )
            consent_col = st.selectbox(
                "Consent Column",
                options=categorical_columns,
                help="Select the column that contains consent status",
                key="consent_enumerator",
                index=default_consent_index,
                on_change=trigger_save,
                kwargs={"state_name": TAB_NAME + "_consent"},
            )
            save_check_settings(settings_file, TAB_NAME, {"consent": consent_col})

        with co2:
            default_consent_vals = default_settings.get("consent_vals", [])
            consent_val_options = data[consent_col].unique().to_list()
            consent_vals = st.multiselect(
                "Valid Consent Values",
                options=consent_val_options,
                default=default_consent_vals,
                help="Select values that indicate valid consent",
                key="consent_vals_enumerator",
                on_change=trigger_save,
                kwargs={"state_name": TAB_NAME + "_consent_vals"},
            )
            save_check_settings(settings_file, TAB_NAME, {"consent_vals": consent_vals})

    with st.container(border=True):
        st.subheader("Outcome Settings")
        oo1, oo2 = st.columns([0.3, 0.7])
        with oo1:
            default_outcome_col = default_settings.get("outcome")
            default_outcome_index = (
                categorical_columns.index(default_outcome_col)
                if default_outcome_col and default_outcome_col in categorical_columns
                else 0
            )
            outcome_col = st.selectbox(
                "Outcome Column",
                options=categorical_columns,
                help="Select the column that contains survey outcome status",
                key="outcome_enumerator",
                index=default_outcome_index,
                on_change=trigger_save,
                kwargs={"state_name": TAB_NAME + "_outcome"},
            )
            save_check_settings(settings_file, TAB_NAME, {"outcome": outcome_col})

        with oo2:
            default_outcome_vals = default_settings.get("outcome_vals", [])
            outcome_val_options = data[outcome_col].unique().to_list()
            outcome_vals = st.multiselect(
                "Completed Survey Values",
                options=outcome_val_options,
                default=default_outcome_vals,
                help="Select values that indicate completed surveys",
                key="outcome_vals_enumerator",
                on_change=trigger_save,
                kwargs={"state_name": TAB_NAME + "_outcome_vals"},
            )
            save_check_settings(settings_file, TAB_NAME, {"outcome_vals": outcome_vals})

        config_dict = {
            "consent": consent_col,
            "consent_vals": consent_vals,
            "outcome": outcome_col,
            "outcome_vals": outcome_vals,
        }
        config = ConsentOutcomeSettings(**config_dict)

    if st.button(
        "Apply Consent and Outcome Settings",
        key="apply_consent_outcome_enumerator",
        type="primary",
        width="stretch",
    ):
        _create_enum_data_on_settings(project_id, data, config)
        _trigger_success_message("st_apply_consent_outcome_enumerator")
        st.rerun()


def _trigger_success_message(button_key: str) -> None:
    """Trigger a success message after button click.

    Parameters
    ----------
    button_key : str
        Unique key of the button to associate the success message with.
    """
    st.session_state[f"{button_key}"] = True


def _create_enum_data_on_settings(
    project_id: str,
    data: pl.DataFrame,
    config: ConsentOutcomeSettings,
) -> None:
    """Create enumerator data based on consent and outcome settings.

    Parameters
    ----------
    project_id : str
        Unique project identifier for database operations.
    data : pl.DataFrame
        DataFrame containing survey data.
    conditions : ConsentOutcomeSettings
        Consent and outcome configuration settings.
    """
    # If consent and consent values are provided, create a dummy column indicating
    # valid consent else set to 1

    if config.consent and config.consent_vals:
        enum_data = data.with_columns(
            pl.col(config.consent)
            .is_in(config.consent_vals)
            .cast(pl.Int32)
            .alias("consent_granted_agg_col")
        )
    else:
        enum_data = data.with_columns(
            pl.lit(1).cast(pl.Int32).alias("consent_granted_agg_col")
        )

    if config.outcome and config.outcome_vals:
        enum_data = enum_data.with_columns(
            pl.col(config.outcome)
            .is_in(config.outcome_vals)
            .cast(pl.Int32)
            .alias("completed_survey_agg_col")
        )
    else:
        enum_data = enum_data.with_columns(
            pl.lit(1).cast(pl.Int32).alias("completed_survey_agg_col")
        )

    # save to database
    duckdb_save_table(
        project_id,
        enum_data,
        "enumerator_data_with_consent_outcome",
        "intermediate",
    )
