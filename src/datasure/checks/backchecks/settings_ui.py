"""Settings UI for the backchecks report."""

import pandas as pd
import polars as pl
import streamlit as st

from datasure.checks.backchecks.compute import load_default_backchecks_settings
from datasure.checks.backchecks.models import (
    TAB_NAME,
    BackcheckSettings,
    StrCompareOptions,
)
from datasure.utils.onboarding_utils import demo_output_onboarding
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)

# ==============================================================================
# SETTINGS UI RENDER FUNCTIONS
# ==============================================================================


def _get_default_index(default_value: str | None, options: list[str]) -> int | None:
    """Get index of default value in options list.

    Parameters
    ----------
    default_value : str | None
        Default value to find.
    options : list[str]
        List of available options.

    Returns
    -------
    int | None
        Index of default value, or None if not found.
    """
    if default_value and default_value in options:
        return options.index(default_value)
    return None


def _render_selectbox_with_save(
    label: str,
    options: list[str],
    key: str,
    settings_file: str,
    setting_key: str,
    default_value: str | None,
    help_text: str,
) -> str:
    """Render selectbox with automatic save functionality.

    Parameters
    ----------
    label : str
        Label for the selectbox.
    options : list[str]
        Available options.
    key : str
        Streamlit widget key.
    settings_file : str
        Path to settings file.
    setting_key : str
        Key for saving the setting.
    default_value : str | None
        Default value.
    help_text : str
        Help text for the selectbox.

    Returns
    -------
    str
        Selected value.
    """
    default_index = _get_default_index(default_value, options)
    selected_value = st.selectbox(
        label,
        options=options,
        key=key,
        help=help_text,
        index=default_index,
        on_change=trigger_save,
        kwargs={"state_name": TAB_NAME + f"_{setting_key}"},
    )
    save_check_settings(settings_file, TAB_NAME, {setting_key: selected_value})
    return selected_value


def _render_survey_identifiers(
    settings_file: str,
    default_settings: BackcheckSettings,
    survey_categorical_columns: list[str],
) -> tuple[str, str]:
    """Render survey identifiers section.

    Parameters
    ----------
    settings_file : str
        Path to settings file.
    default_settings : BackcheckSettings
        Default settings.
    survey_categorical_columns : list[str]
        Available categorical columns.

    Returns
    -------
    tuple[str, str]
        Survey key and survey ID.
    """
    with st.container(border=True):
        st.subheader("Survey Identifiers")
        si1, si2, _ = st.columns(3)

        with si1:
            survey_key = _render_selectbox_with_save(
                "Survey Key (required)",
                survey_categorical_columns,
                "survey_key_backchecks",
                settings_file,
                "survey_key",
                default_settings.survey_key,
                "Select the column that contains the survey key",
            )

        with si2:
            survey_id = _render_selectbox_with_save(
                "Survey ID (required)",
                survey_categorical_columns,
                "survey_id_backchecks",
                settings_file,
                "survey_id",
                default_settings.survey_id,
                "Select the column that contains the survey ID",
            )

    return survey_key, survey_id


def _render_date_columns(
    settings_file: str,
    default_settings: BackcheckSettings,
    survey_datetime_columns: list[str],
    backcheck_datetime_columns: list[str],
) -> tuple[str, str]:
    """Render date columns section.

    Parameters
    ----------
    settings_file : str
        Path to settings file.
    default_settings : BackcheckSettings
        Default settings.
    survey_datetime_columns : list[str]
        Available survey datetime columns.
    backcheck_datetime_columns : list[str]
        Available backcheck datetime columns.

    Returns
    -------
    tuple[str, str]
        Survey date and backcheck date.
    """
    with st.container(border=True):
        st.subheader("Survey & BAckcheck Dates")
        sd1, sd2, _ = st.columns(3)

        with sd1:
            survey_date = _render_selectbox_with_save(
                "Survey Date",
                survey_datetime_columns,
                "survey_date_backchecks",
                settings_file,
                "survey_date",
                default_settings.survey_date,
                "Select the column that contains the survey date",
            )

        with sd2:
            backcheck_date = _render_selectbox_with_save(
                "Backcheck Date",
                backcheck_datetime_columns,
                "backcheck_date_backchecks",
                settings_file,
                "backcheck_date",
                default_settings.survey_date,
                "Select the column that contains the backcheck date",
            )

    return survey_date, backcheck_date


def _render_staff_identifiers(
    settings_file: str,
    default_settings: BackcheckSettings,
    survey_categorical_columns: list[str],
    backcheck_categorical_columns: list[str],
) -> tuple[str, str]:
    """Render staff identifiers section.

    Parameters
    ----------
    settings_file : str
        Path to settings file.
    default_settings : BackcheckSettings
        Default settings.
    survey_categorical_columns : list[str]
        Available survey categorical columns.
    backcheck_categorical_columns : list[str]
        Available backcheck categorical columns.

    Returns
    -------
    tuple[str, str]
        Enumerator and backchecker.
    """
    with st.container(border=True):
        st.subheader("Staff Identifiers")
        ec1, ec2, _ = st.columns(3)

        with ec1:
            enumerator = _render_selectbox_with_save(
                "Enumerator",
                survey_categorical_columns,
                "enumerator_backchecks",
                settings_file,
                "enumerator",
                default_settings.enumerator,
                "Select the column that contains the enumerator ID",
            )

        with ec2:
            backchecker = _render_selectbox_with_save(
                "Back Checker",
                backcheck_categorical_columns,
                "backchecker_backchecks",
                settings_file,
                "backchecker",
                default_settings.backchecker,
                "Select the column that contains the back checker ID",
            )

    return enumerator, backchecker


def _render_tracking_options(
    settings_file: str, default_settings: BackcheckSettings
) -> int:
    """Render tracking options section.

    Parameters
    ----------
    settings_file : str
        Path to settings file.
    default_settings : BackcheckSettings
        Default settings.

    Returns
    -------
    int
        Backcheck goal.
    """
    with st.container(border=True):
        st.subheader("Tracking Options")
        to1, _, _ = st.columns(3)

        with to1:
            backcheck_goal = st.number_input(
                "Target number of backchecks",
                min_value=0,
                help="Total number of backchecks expected",
                key="backcheck_goal_backchecks",
                value=default_settings.backcheck_target_percent,
                on_change=trigger_save,
                kwargs={"state_name": TAB_NAME + "_backcheck_goal"},
            )
            save_check_settings(
                settings_file, TAB_NAME, {"backcheck_goal": backcheck_goal}
            )

    return backcheck_goal


def _render_duplicate_handling(
    settings_file: str, default_settings: BackcheckSettings
) -> str:
    """Render duplicate handling section.

    Parameters
    ----------
    settings_file : str
        Path to settings file.
    default_settings : BackcheckSettings
        Default settings.

    Returns
    -------
    str
        Drop duplicates option.
    """
    with st.container(border=True):
        st.markdown("##### Duplicate Handling")
        st.write("How would you like to handle duplicates?")
        options_map = {
            "drop": ":material/remove_selection: Drop All Entries",
            "first": ":material/first_page: Keep First Entry",
            "last": ":material/last_page: Keep Last Entry",
        }
        drop_duplicates_option = st.pills(
            "Select an option for handling duplicates",
            options=list(options_map.keys()),
            format_func=lambda x: options_map[x],
            key="drop_duplicates_option_backchecks",
            default=default_settings.drop_duplicates_option,
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_drop_duplicates_option"},
        )
        save_check_settings(
            settings_file,
            TAB_NAME,
            {"drop_duplicates_option": drop_duplicates_option},
        )

    return drop_duplicates_option


def _render_value_list_display(
    values: list[str], info_message: str, warning_message: str, help_text: str
) -> None:
    """Render a list of values in a dataframe display.

    Parameters
    ----------
    values : list[str]
        List of values to display.
    info_message : str
        Message to show when values exist.
    warning_message : str
        Message to show when no values configured.
    help_text : str
        Help text for the column.
    """
    if values:
        st.info(info_message)
        values_df = pl.DataFrame({"Values": values})
        dc1, _ = st.columns([1, 3])
        dc1.dataframe(
            values_df,
            hide_index=True,
            column_config={
                "Values": st.column_config.ListColumn(
                    "Values",
                    help=help_text,
                    width="content",
                )
            },
        )
    else:
        st.warning(warning_message)


def _render_additional_options(
    settings_file: str,
    config: BackcheckSettings,
) -> tuple[str, list[str], list[str], StrCompareOptions]:
    """Render additional options section.

    Parameters
    ----------
    settings_file : str
        Path to settings file.

    Returns
    -------
    tuple[str, list[str], list[str], StrCompareOptions]
        Drop duplicates option, no diff values, exclude values,
        and string comparison options.
    """
    with st.container(border=True):
        st.subheader("Additional Options")

        default_settings = load_default_backchecks_settings(settings_file, config)

        # Duplicate handling
        drop_duplicates_option = _render_duplicate_handling(
            settings_file, default_settings
        )

        # No differences settings
        with st.container(border=True):
            st.markdown("##### No differences Settings")
            st.write(
                "Settings for entries values in backchecks that will not be marked as differences."
            )
            no_diff_values = _render_no_differences_settings(settings_file)
            _render_value_list_display(
                no_diff_values,
                "The following values will not be marked as differences:",
                "No values configured to be excluded from differences.",
                "Values that will not be marked as differences",
            )

        # Exclude values settings
        with st.container(border=True):
            st.markdown("##### Exclude Value Settings")
            st.write(
                "Settings for entries values in backchecks that will be excluded from backcheck comparisons."
            )
            exclude_values = _render_exclude_values_settings(settings_file)
            _render_value_list_display(
                exclude_values,
                "The following values will be excluded from backcheck comparisons:",
                "No values configured to be excluded from backcheck comparisons.",
                "Values that will be excluded from backcheck comparisons",
            )

        # String comparison settings
        with st.container(border=True):
            st.markdown("##### String Comparison Settings")
            st.write("Settings for string comparison in backcheck comparisons.")
            string_comp_options = _render_string_comparison_options(settings_file)

    return drop_duplicates_option, no_diff_values, exclude_values, string_comp_options


@demo_output_onboarding(TAB_NAME)
def backchecks_report_settings(
    project_id: str,
    settings_file: str,
    survey_data: pd.DataFrame,
    backcheck_data: pd.DataFrame,
    config: BackcheckSettings,
    survey_categorical_columns: list[str],
    survey_datetime_columns: list[str],
    backcheck_categorical_columns: list[str],
    backcheck_datetime_columns: list[str],
) -> BackcheckSettings:
    """Create and render the settings UI for backchecks report configuration.

    This function creates a comprehensive Streamlit UI for configuring
    backchecks report settings. It includes:
    - Survey identifiers (key and ID columns)
    - Survey date column selection
    - Enumerator and backchecker columns
    - Tracking options (backcheck goal and duplicate handling)

    Settings are automatically saved to the settings file when changed
    and loaded from previous sessions if available.

    Parameters
    ----------
    project_id : str
        Unique project identifier for database operations.
    settings_file : str
        Path to settings file for saving/loading configurations.
    survey_data : pd.DataFrame
        Survey dataset.
    backcheck_data : pd.DataFrame
        Backcheck dataset.
    config : BackcheckSettings
        Default configuration used as fallback values.
    survey_categorical_columns : list[str]
        Available survey categorical columns for selection.
    survey_datetime_columns : list[str]
        Available survey datetime columns for date selection.
    backcheck_categorical_columns : list[str]
        Available backcheck categorical columns for selection.
    backcheck_datetime_columns : list[str]
        Available backcheck datetime columns for date selection.

    Returns
    -------
    BackcheckSettings
        User-configured settings from the UI.
    """
    with st.expander("settings", icon=":material/settings:"):
        st.markdown("## Configure settings for backcheck report")
        st.write("---")

        default_settings = load_default_backchecks_settings(settings_file, config)

        # Render all sections
        survey_key, survey_id = _render_survey_identifiers(
            settings_file, default_settings, survey_categorical_columns
        )

        survey_date, backcheck_date = _render_date_columns(
            settings_file,
            default_settings,
            survey_datetime_columns,
            backcheck_datetime_columns,
        )

        enumerator, backchecker = _render_staff_identifiers(
            settings_file,
            default_settings,
            survey_categorical_columns,
            backcheck_categorical_columns,
        )

        backcheck_goal = _render_tracking_options(settings_file, default_settings)

        (
            drop_duplicates_option,
            no_diff_values,
            exclude_values,
            string_comp_options,
        ) = _render_additional_options(settings_file, config)

    return BackcheckSettings(
        survey_key=survey_key,
        survey_id=survey_id,
        survey_date=survey_date,
        backcheck_date=backcheck_date,
        enumerator=enumerator,
        backchecker=backchecker,
        backcheck_goal=backcheck_goal,
        drop_duplicates=drop_duplicates_option,
        no_differences_list=no_diff_values,
        exclude_values_list=exclude_values,
        case_option=string_comp_options.case_option,
        trimspaces_option=string_comp_options.trimspaces_option,
        nosymbols_option=string_comp_options.nosymbols_option,
    )


def _render_value_list_editor(
    settings_file: str,
    setting_key: str,
    add_popover_label: str,
    add_text_label: str,
    add_text_key: str,
    add_text_help: str,
    add_button_label: str,
    add_button_key: str,
    add_button_help: str,
    add_state_name: str,
    remove_popover_label: str,
    remove_select_label: str,
    remove_select_key: str,
    remove_select_help: str,
    remove_button_label: str,
    remove_button_key: str,
    remove_button_help: str,
    remove_state_name: str,
    guard_remove_membership: bool,
) -> list:
    """Render add/remove popovers for editing a saved list of string values.

    Shared by `_render_no_differences_settings` and
    `_render_exclude_values_settings`, which both manage a simple add/remove
    editor for a list of string values persisted under a single settings key,
    differing only in labels, widget keys, and whether the remove action
    re-checks that the selected value is still present before removing it.

    Parameters
    ----------
    settings_file : str
        Path to the settings file.
    setting_key : str
        Key under which the list of values is saved.
    add_popover_label : str
        Label for the "add" popover.
    add_text_label : str
        Label for the text input used to enter a new value.
    add_text_key : str
        Streamlit widget key for the text input.
    add_text_help : str
        Help text for the text input.
    add_button_label : str
        Label for the "add" button.
    add_button_key : str
        Streamlit widget key for the "add" button.
    add_button_help : str
        Help text for the "add" button.
    add_state_name : str
        Suffix appended to TAB_NAME for the "add" button's trigger_save state.
    remove_popover_label : str
        Label for the "remove" popover.
    remove_select_label : str
        Label for the selectbox used to choose a value to remove.
    remove_select_key : str
        Streamlit widget key for the selectbox.
    remove_select_help : str
        Help text for the selectbox.
    remove_button_label : str
        Label for the "remove" button.
    remove_button_key : str
        Streamlit widget key for the "remove" button.
    remove_button_help : str
        Help text for the "remove" button.
    remove_state_name : str
        Suffix appended to TAB_NAME for the "remove" button's trigger_save state.
    guard_remove_membership : bool
        Whether to re-check that the selected value is still present in the
        saved list before removing it.

    Returns
    -------
    list
        Updated list of values.
    """
    saved_settings = load_check_settings(settings_file, TAB_NAME)
    updated_values = saved_settings.get(setting_key, [])

    ac_col, rc_col, _ = st.columns([0.4, 0.3, 0.3])
    with ac_col, st.popover(add_popover_label, type="primary", width="stretch"):
        new_value = st.text_input(add_text_label, key=add_text_key, help=add_text_help)
        # validate input and add to list
        if st.button(
            add_button_label,
            key=add_button_key,
            help=add_button_help,
            width="stretch",
            disabled=not new_value,
            type="primary",
            on_click=trigger_save,
            kwargs={"state_name": TAB_NAME + add_state_name},
        ):
            saved_settings = load_check_settings(settings_file, TAB_NAME)
            current_values = saved_settings.get(setting_key, [])
            if current_values:
                current_values.append(new_value)
                updated_values = current_values
            else:
                updated_values = [new_value]
            save_check_settings(settings_file, TAB_NAME, {setting_key: updated_values})
            st.rerun()

    with rc_col, st.popover(remove_popover_label, width="stretch"):
        saved_settings = load_check_settings(settings_file, TAB_NAME)
        current_values = saved_settings.get(setting_key, [])
        if not current_values:
            st.info("No values to remove.")
        value_to_remove = st.selectbox(
            remove_select_label,
            options=current_values,
            key=remove_select_key,
            help=remove_select_help,
            disabled=not current_values,
        )
        if st.button(
            remove_button_label,
            key=remove_button_key,
            help=remove_button_help,
            width="stretch",
            type="primary",
            on_click=trigger_save,
            kwargs={"state_name": TAB_NAME + remove_state_name},
        ):
            can_remove = (
                value_to_remove in current_values if guard_remove_membership else True
            )
            if can_remove:
                current_values.remove(value_to_remove)
                updated_values = current_values
                save_check_settings(
                    settings_file, TAB_NAME, {setting_key: updated_values}
                )
                st.rerun()

    return updated_values


@st.fragment
def _render_no_differences_settings(settings_file: str) -> list:
    """Render UI for managing values that won't be considered as discrepancies.

    This function allows users to add or remove values from a list. Values in this
    list will not be marked as differences during backcheck comparison, regardless
    of whether they appear in the survey or backcheck data.

    Parameters
    ----------
    settings_file : str
        Path to the settings file.
    tab_name : str
        Name of the tab/check (used as key in settings).
    """
    return _render_value_list_editor(
        settings_file,
        setting_key="no_differences_values",
        add_popover_label="Add Value",
        add_text_label="Enter value to exclude from differences",
        add_text_key="new_no_diff_value_input",
        add_text_help="Enter the value to be excluded from difference checks.",
        add_button_label="Add Value",
        add_button_key="add_no_diff_value",
        add_button_help="Add the value to the no-differences list.",
        add_state_name="_no_differences_values",
        remove_popover_label="Remove Value",
        remove_select_label="Select value to remove from no-differences list",
        remove_select_key="remove_no_diff_value_select",
        remove_select_help="Select the value to remove from the no-differences list.",
        remove_button_label="Remove Value",
        remove_button_key="remove_no_diff_value",
        remove_button_help="Remove the selected value from the no-differences list.",
        remove_state_name="_no_differences_value",
        guard_remove_membership=False,
    )


@st.fragment
def _render_string_comparison_options(settings_file) -> StrCompareOptions:
    """Render string comparison options UI.

    Returns
    -------
    StrCompareOptions
        Selected string comparison options.
    """
    st.markdown("##### String Comparison Options")
    sok1, sok2, sok3 = st.columns(3)
    default_settings = load_check_settings(settings_file, TAB_NAME)
    default_case_setting = default_settings.get("string_case_option", None)
    options_map = {
        "lowercase": ":material/lowercase: lowercase",
        "uppercase": ":material/uppercase: UPPERCASE",
    }
    with sok1, st.container(border=True):
        string_case_option = st.pills(
            "Convert String Case Before Comparison",
            options=options_map.keys(),
            format_func=lambda x: options_map[x],
            default=default_case_setting,
            key="string_case_option_backchecks_pills",
            help="Select how to handle case sensitivity in string comparisons.",
            selection_mode="single",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_string_case_option"},
        )
        save_check_settings(
            settings_file, TAB_NAME, {"string_case_option": string_case_option}
        )

    with sok2, st.container(border=True):
        default_nosymbols_setting = default_settings.get(
            "string_nosymbols_option", False
        )
        string_nosymbols_option = st.toggle(
            label="Ignore Symbols in String Comparison",
            value=default_nosymbols_setting,
            key="string_nosymbols_option_backchecks_toggle",
            help="Toggle to ignore symbols when comparing string values.",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_string_nosymbols_option"},
        )
        save_check_settings(
            settings_file,
            TAB_NAME,
            {"string_nosymbols_option": string_nosymbols_option},
        )

    with sok3, st.container(border=True):
        default_trimspaces_setting = default_settings.get(
            "string_trimspaces_option", False
        )
        string_trimspaces_option = st.toggle(
            label="Trim Spaces in String Comparison",
            value=default_trimspaces_setting,
            key="string_trimspaces_option_backchecks_toggle",
            help="Toggle to trim leading and trailing spaces when comparing string values.",
            on_change=trigger_save,
            kwargs={"state_name": TAB_NAME + "_string_trimspaces_option"},
        )
        save_check_settings(
            settings_file,
            TAB_NAME,
            {"string_trimspaces_option": string_trimspaces_option},
        )

    return StrCompareOptions(
        case_option=string_case_option,
        nosymbol_option=string_nosymbols_option,
        whitespace_option=string_trimspaces_option,
    )


@st.fragment
def _render_exclude_values_settings(settings_file: str) -> list:
    """Render UI for managing values to exclude from backcheck comparison."""
    return _render_value_list_editor(
        settings_file,
        setting_key="exclude_values",
        add_popover_label="Add Exclude Value",
        add_text_label="Enter value to exclude from backcheck comparison",
        add_text_key="new_exclude_value_input",
        add_text_help="Enter the value to be excluded from backcheck comparison.",
        add_button_label="Add Exclude Value",
        add_button_key="add_exclude_value",
        add_button_help="Add the value to the exclude list.",
        add_state_name="_exclude_values",
        remove_popover_label="Remove Exclude Value",
        remove_select_label="Select value to remove from exclude list",
        remove_select_key="remove_exclude_value_select",
        remove_select_help="Select the value to remove from the exclude list.",
        remove_button_label="Remove Exclude Value",
        remove_button_key="remove_exclude_value",
        remove_button_help="Remove the selected value from the exclude list.",
        remove_state_name="_exclude_values",
        guard_remove_membership=True,
    )
