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


def _render_column_select(
    label: str,
    field_key: str,
    options: list[str],
    help_text: str,
    default_settings: EnumeratorSettings,
    settings_file: str,
) -> str | None:
    """Render a settings selectbox bound to an EnumeratorSettings field.

    Every single-column picker in the settings UI (survey key, survey ID,
    survey date, enumerator, team, duration, form version) shares this same
    default-index-lookup + selectbox + save_check_settings shape.

    Parameters
    ----------
    label : str
        Widget label shown above the selectbox.
    field_key : str
        Name of the EnumeratorSettings field this selectbox configures; also
        used to derive the widget key and the saved settings key.
    options : list[str]
        Columns to offer as selectbox options.
    help_text : str
        Tooltip text for the selectbox.
    default_settings : EnumeratorSettings
        Previously saved settings, used to preselect a default option.
    settings_file : str
        Path to settings file for saving the selected value.

    Returns
    -------
    str | None
        The selected column name.
    """
    default_value = getattr(default_settings, field_key)
    default_index = (
        options.index(default_value)
        if default_value and default_value in options
        else None
    )
    selected = st.selectbox(
        label,
        options=options,
        key=f"{field_key}_enumerator",
        help=help_text,
        index=default_index,
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + f"_{field_key}"},
    )
    save_check_settings(settings_file, TAB_NAME, {field_key: selected})
    return selected


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
                survey_key = _render_column_select(
                    "Survey Key",
                    "survey_key",
                    categorical_columns,
                    "Select the column that contains the survey key",
                    default_settings,
                    settings_file,
                )

            with si2:
                survey_id = _render_column_select(
                    "Survey ID",
                    "survey_id",
                    categorical_columns,
                    "Select the column that contains the survey ID",
                    default_settings,
                    settings_file,
                )

        with st.container(border=True):
            st.subheader("Survey Date")

            sd1, _, _ = st.columns(3)

            with sd1:
                survey_date = _render_column_select(
                    "Survey Date",
                    "survey_date",
                    datetime_columns,
                    "Select the column that contains the survey date",
                    default_settings,
                    settings_file,
                )

        with st.container(border=True):
            st.subheader("Enumerator")
            ec1, ec2, _ = st.columns(3)
            with ec1:
                enumerator = _render_column_select(
                    "Enumerator ID",
                    "enumerator",
                    categorical_columns,
                    "Select the column that contains the enumerator ID",
                    default_settings,
                    settings_file,
                )

            with ec2:
                team = _render_column_select(
                    "Team",
                    "team",
                    categorical_columns,
                    "Select the column that contains the team identifier",
                    default_settings,
                    settings_file,
                )

        with st.container(border=True):
            st.subheader("Survey Duration")
            dc1, dc2, _ = st.columns(3)
            with dc1:
                duration = _render_column_select(
                    "Duration Column",
                    "duration",
                    categorical_columns,
                    "Select the column that contains the survey duration in seconds",
                    default_settings,
                    settings_file,
                )

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
                formversion = _render_column_select(
                    "Form Version Column",
                    "formversion",
                    categorical_columns,
                    "Select the column that contains the form version",
                    default_settings,
                    settings_file,
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


def _render_category_settings(
    column_label: str,
    field_key: str,
    column_help: str,
    values_label: str,
    values_help: str,
    categorical_columns: list,
    default_settings: dict,
    data: pl.DataFrame,
    settings_file: str,
) -> tuple[str | None, list[str]]:
    """Render a column selector + valid-values multiselect pair.

    The consent and outcome settings sections share this same
    column-then-values-multiselect layout, differing only in labels,
    help text, and which EnumeratorSettings field they populate.

    Parameters
    ----------
    column_label : str
        Widget label for the column selectbox.
    field_key : str
        Base settings key (e.g. "consent" or "outcome"); the values
        multiselect is saved under f"{field_key}_vals".
    column_help : str
        Tooltip text for the column selectbox.
    values_label : str
        Widget label for the values multiselect.
    values_help : str
        Tooltip text for the values multiselect.
    categorical_columns : list
        Columns to offer as selectbox options.
    default_settings : dict
        Previously saved settings, used to preselect defaults.
    data : pl.DataFrame
        DataFrame containing survey data, used to derive value options.
    settings_file : str
        Path to settings file for saving/loading configurations.

    Returns
    -------
    tuple[str | None, list[str]]
        The selected column name and selected valid values.
    """
    col1, col2 = st.columns([0.3, 0.7])
    with col1:
        default_col = default_settings.get(field_key)
        default_index = (
            categorical_columns.index(default_col)
            if default_col and default_col in categorical_columns
            else 0
        )
        selected_col = st.selectbox(
            column_label,
            options=categorical_columns,
            help=column_help,
            key=f"{field_key}_enumerator",
            index=default_index,
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + f"_{field_key}"},
        )
        save_check_settings(settings_file, TAB_NAME, {field_key: selected_col})

    with col2:
        vals_key = f"{field_key}_vals"
        default_vals = default_settings.get(vals_key, [])
        val_options = data[selected_col].unique().to_list()
        selected_vals = st.multiselect(
            values_label,
            options=val_options,
            default=default_vals,
            help=values_help,
            key=f"{vals_key}_enumerator",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + f"_{vals_key}"},
        )
        save_check_settings(settings_file, TAB_NAME, {vals_key: selected_vals})

    return selected_col, selected_vals


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
        consent_col, consent_vals = _render_category_settings(
            "Consent Column",
            "consent",
            "Select the column that contains consent status",
            "Valid Consent Values",
            "Select values that indicate valid consent",
            categorical_columns,
            default_settings,
            data,
            settings_file,
        )

    with st.container(border=True):
        st.subheader("Outcome Settings")
        outcome_col, outcome_vals = _render_category_settings(
            "Outcome Column",
            "outcome",
            "Select the column that contains survey outcome status",
            "Completed Survey Values",
            "Select values that indicate completed surveys",
            categorical_columns,
            default_settings,
            data,
            settings_file,
        )

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
