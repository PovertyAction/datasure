"""
Correction view for making data corrections based on identified issues.

This module provides an interactive interface for applying, tracking, and managing
data corrections across multiple datasets. Corrections are logged and can be
removed or modified as needed.
"""

from datetime import datetime
from typing import Any

import polars as pl
import streamlit as st
from pydantic import BaseModel, Field

from datasure.processing.corrections import CorrectionProcessor
from datasure.utils.duckdb_utils import duckdb_get_table
from datasure.utils.navigations_utils import demo_sidebar_help, page_navigation
from datasure.utils.onboarding_utils import ImportDemoInfo, demo_expander
from datasure.utils.settings_utils import get_check_config_settings

# DEFINE CONSTANTS FOR CORRECTION
CORRECTION_ACTIONS = ("modify value", "remove value", "remove row")


class TabConfig(BaseModel):
    """Configuration for a correction tab."""

    page_name: str = Field(..., description="Name of the page/check")
    survey_data_name: str = Field(..., description="Name of the survey data alias")
    survey_key: str = Field(..., description="Name of the survey KEY column")


class CorrectionFormState(BaseModel):
    """State management for correction form inputs."""

    key_value: str = Field(..., description="The selected key value for correction")
    action: str = Field(..., description="The correction action type")
    column: str | None = Field(None, description="The column to modify (if applicable)")
    current_value: Any | None = Field(
        None, description="The current value (if applicable)"
    )
    new_value: Any | None = Field(None, description="The new value (if applicable)")
    validation_error: str | None = Field(
        None, description="Validation error message (if any)"
    )


def load_hfc_config(project_id: str) -> tuple[pl.DataFrame, list[str]]:
    """
    Load HFC configuration data and extract page list.

    Parameters
    ----------
    project_id : str
        The project identifier.

    Returns
    -------
    tuple[pl.DataFrame, list[str]]
        A tuple containing the HFC configuration logs and list of page names.

    """
    hfc_config_logs = duckdb_get_table(
        project_id=project_id, alias="check_config", db_name="logs"
    )
    if hfc_config_logs.is_empty():
        return hfc_config_logs, []
    return hfc_config_logs, hfc_config_logs["page_name"].to_list()


def get_key_options(data: pl.DataFrame, key_col: str) -> list:
    """
    Extract unique key values from data for correction selection.

    Parameters
    ----------
    data : pl.DataFrame
        The dataset containing the key column.
    key_col : str
        The name of the key column.

    Returns
    -------
    list
        List of unique key values.
    """
    return data.select(key_col).unique(maintain_order=True).to_series().to_list()


def get_current_value(
    data: pl.DataFrame, key_col: str, key_value: str, column: str
) -> Any:
    """
    Retrieve the current value for a specific key and column.

    Parameters
    ----------
    data : pl.DataFrame
        The dataset to query.
    key_col : str
        The name of the key column.
    key_value : str
        The key value to filter by.
    column : str
        The column to retrieve the value from.

    Returns
    -------
    Any
        The current value, or None if not found.
    """
    try:
        return data.filter(pl.col(key_col) == key_value).select(column)[0, 0]
    except Exception:
        return None


def parse_date_value(value: Any) -> datetime.date:
    """
    Parse a datetime value to a date object.

    Parameters
    ----------
    value : Any
        The value to parse (can be string or datetime).

    Returns
    -------
    datetime.date | None
        Parsed date or None if parsing fails.
    """
    if not value:
        return None

    try:
        if isinstance(value, str):
            return datetime.fromisoformat(value).date()
        return value.date()
    except Exception:
        return None


def validate_numeric_input(value: str, dtype: pl.DataType) -> tuple[bool, str | None]:
    """
    Validate numeric input based on column data type.

    Parameters
    ----------
    value : str
        The input value to validate.
    dtype : pl.DataType
        The expected data type.

    Returns
    -------
    tuple[bool, str | None]
        A tuple of (is_valid, error_message).
    """
    if dtype in [pl.Int64, pl.Int32, pl.Float64, pl.Float32]:
        try:
            float(value)
            return True, None  # noqa: TRY300
        except ValueError:
            return False, "New value must be a number."
    return True, None


def should_enable_apply_button(action: str, reason: str, new_value: Any = None) -> bool:
    """
    Determine if the apply button should be enabled.

    Parameters
    ----------
    action : str
        The correction action type.
    reason : str
        The reason for correction.
    new_value : Any, optional
        The new value (required for modify action).

    Returns
    -------
    bool
        True if apply button should be enabled.
    """
    if not reason:
        return False

    if action == "modify value":
        return bool(new_value)
    return action in ["remove value", "remove row"]


def load_tab_config(project_id: str, tab_index: int) -> TabConfig | None:
    """
    Load configuration for a specific correction tab.

    Parameters
    ----------
    project_id : str
        The project identifier.
    tab_index : int
        The index of the tab to load configuration for.

    Returns
    -------
    TabConfig | None
        Tab configuration or None if loading fails.
    """
    page_config = get_check_config_settings(
        project_id=project_id,
        page_row_index=tab_index,
    )

    return TabConfig(
        page_name=page_config.get("page_name"),
        survey_data_name=page_config.get("survey_data_name"),
        survey_key=page_config.get("survey_key"),
    )


def validate_prerequisites(project_id: str | None) -> tuple[pl.DataFrame, list[str]]:
    """
    Validate that all prerequisites are met before rendering the page.

    Parameters
    ----------
    project_id : str | None
        The project identifier.

    Returns
    -------
    tuple[pl.DataFrame, list[str]]
        HFC configuration logs and page list.

    Raises
    ------
    SystemExit
        If prerequisites are not met (via st.stop()).
    """
    if not project_id:
        st.info(
            "Select a project from the Start page and import data. "
            "You can also create a new project from the Start page."
        )
        st.stop()

    hfc_config_logs, hfc_pages = load_hfc_config(project_id)

    if hfc_config_logs.is_empty():
        st.info(
            "No checks configured. Please configure checks on the Configure Checks page."
        )
        st.stop()

    if not hfc_pages:
        st.info(
            "No data available to prepare. Load a dataset from the import page to continue."
        )
        st.stop()

    return hfc_config_logs, hfc_pages


def render_value_input_widget(
    column: str,
    col_dtype: pl.DataType,
    current_value: Any,
    tab_index: int,
) -> tuple[Any, str | None]:
    """
    Render appropriate input widget based on column data type.

    Parameters
    ----------
    column : str
        The column name being modified.
    col_dtype : pl.DataType
        The column data type.
    current_value : Any
        The current value in the column.
    tab_index : int
        The tab index for unique widget keys.

    Returns
    -------
    tuple[Any, str | None]
        A tuple of (new_value, error_message).
    """
    if col_dtype == pl.Datetime:
        current_date = parse_date_value(current_value)
        new_value = st.date_input(
            label="New Value",
            key=f"correction_new_value_{tab_index}",
            value=current_date,
            help="Select a date for the new value.",
        )
        return new_value, None

    # Text input for other types
    new_value = st.text_input(
        label="New Value",
        key=f"correction_new_value_{tab_index}",
        placeholder="Enter new value",
    )

    if new_value:
        is_valid, error_msg = validate_numeric_input(new_value, col_dtype)
        if not is_valid:
            return None, error_msg

    return new_value, None


def _render_column_selector(
    corrected_data: pl.DataFrame,
    key_col: str,
    key_value: str,
    tab_index: int,
) -> tuple[str | None, Any]:
    """
    Render column selector and display current value.

    Parameters
    ----------
    corrected_data : pl.DataFrame
        The corrected dataset.
    key_col : str
        The key column name.
    key_value : str
        The selected key value.
    tab_index : int
        The tab index for unique widget keys.

    Returns
    -------
    tuple[str | None, Any]
        Column name and current value.
    """
    column = st.selectbox(
        label="Select Column to Modify",
        options=corrected_data.columns,
        key=f"correction_col_to_modify_{tab_index}",
    )

    if not column:
        return None, None

    current_value = get_current_value(corrected_data, key_col, key_value, column)

    st.text_input(
        label="Current Value",
        value=str(current_value) if current_value is not None else "",
        key=f"correction_current_value_{tab_index}",
        disabled=True,
    )

    return column, current_value


def _render_modify_value_action(
    corrected_data: pl.DataFrame,
    key_col: str,
    key_value: str,
    tab_index: int,
) -> CorrectionFormState:
    """
    Render UI elements for 'modify value' action.

    Parameters
    ----------
    corrected_data : pl.DataFrame
        The corrected dataset.
    key_col : str
        The key column name.
    key_value : str
        The selected key value.
    tab_index : int
        The tab index for unique widget keys.

    Returns
    -------
    CorrectionFormState
        Form state with column, values, and validation errors.
    """
    column, current_value = _render_column_selector(
        corrected_data, key_col, key_value, tab_index
    )

    if not column:
        return CorrectionFormState(
            key_value=key_value, action="modify value", column=None
        )

    col_dtype = corrected_data.schema[column]
    new_value, validation_error = render_value_input_widget(
        column, col_dtype, current_value, tab_index
    )

    if validation_error:
        st.error(validation_error)

    return CorrectionFormState(
        key_value=key_value,
        action="modify value",
        column=column,
        current_value=current_value,
        new_value=new_value,
        validation_error=validation_error,
    )


def _render_remove_value_action(
    corrected_data: pl.DataFrame,
    key_col: str,
    key_value: str,
    tab_index: int,
) -> CorrectionFormState:
    """
    Render UI elements for 'remove value' action.

    Parameters
    ----------
    corrected_data : pl.DataFrame
        The corrected dataset.
    key_col : str
        The key column name.
    key_value : str
        The selected key value.
    tab_index : int
        The tab index for unique widget keys.

    Returns
    -------
    CorrectionFormState
        Form state with column and current value.
    """
    column, current_value = _render_column_selector(
        corrected_data, key_col, key_value, tab_index
    )

    return CorrectionFormState(
        key_value=key_value,
        action="remove value",
        column=column,
        current_value=current_value,
    )


def _render_remove_row_action(key_value: str) -> CorrectionFormState:
    """
    Render UI elements for 'remove row' action.

    Parameters
    ----------
    key_value : str
        The selected key value.

    Returns
    -------
    CorrectionFormState
        Form state for row removal.
    """
    st.warning("This will remove the row with the selected key value from the dataset.")

    return CorrectionFormState(key_value=key_value, action="remove row")


def render_add_correction_form(
    correction_processor: CorrectionProcessor,
    key_col: str,
    alias: str,
    tab_index: int,
) -> None:
    """
    Render the add correction step form.

    This function orchestrates the correction form UI, delegating action-specific
    rendering to helper functions to maintain low cognitive complexity.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    key_col : str
        The name of the Survey KEY column in the DataFrame.
    alias : str
        The data alias/table name.
    tab_index : int
        The tab index for unique widget keys.
    """
    corrected_data = correction_processor.get_corrected_data(alias)

    if corrected_data.is_empty():
        st.warning("No data available for correction.")
        return

    with st.popover(":material/add: Add correction step", width="stretch"):
        st.markdown("*Add new correction step*")

        # Step 1: Select key
        key_options = get_key_options(corrected_data, key_col)
        corr_key_val = st.selectbox(
            label="Select KEY",
            options=key_options,
            key=f"correction_key_value_{tab_index}",
        )

        if not corr_key_val:
            return

        # Step 2: Select action
        corr_action = st.selectbox(
            label="Select Action",
            options=CORRECTION_ACTIONS,
            key=f"correction_action_{tab_index}",
        )

        # Step 3: Render action-specific UI and collect form state
        form_state = _render_action_ui(
            corr_action, corrected_data, key_col, corr_key_val, tab_index
        )

        # Step 4: Collect reason
        reason = st.text_input(
            label="Reason for Correction",
            key=f"correction_reason_{tab_index}",
            placeholder="Enter reason for correction",
        )

        # Step 5: Render apply button
        _render_apply_button(
            correction_processor=correction_processor,
            corrected_data=corrected_data,
            alias=alias,
            key_col=key_col,
            form_state=form_state,
            reason=reason,
            tab_index=tab_index,
        )


def _render_action_ui(
    action: str,
    corrected_data: pl.DataFrame,
    key_col: str,
    key_value: str,
    tab_index: int,
) -> CorrectionFormState:
    """
    Render UI elements based on selected action type.

    Parameters
    ----------
    action : str
        The correction action type.
    corrected_data : pl.DataFrame
        The corrected dataset.
    key_col : str
        The key column name.
    key_value : str
        The selected key value.
    tab_index : int
        The tab index for unique widget keys.

    Returns
    -------
    CorrectionFormState
        Form state containing collected values.
    """
    if action == "modify value":
        return _render_modify_value_action(
            corrected_data, key_col, key_value, tab_index
        )

    if action == "remove value":
        return _render_remove_value_action(
            corrected_data, key_col, key_value, tab_index
        )

    # action == "remove row"
    return _render_remove_row_action(key_value)


def _render_apply_button(
    correction_processor: CorrectionProcessor,
    corrected_data: pl.DataFrame,
    alias: str,
    key_col: str,
    form_state: CorrectionFormState,
    reason: str,
    tab_index: int,
) -> None:
    """
    Render apply button and handle correction application.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    corrected_data : pl.DataFrame
        The corrected dataset.
    alias : str
        The data alias/table name.
    key_col : str
        The key column name.
    form_state : CorrectionFormState
        Current form state.
    reason : str
        Reason for correction.
    tab_index : int
        The tab index for unique widget keys.
    """
    apply_enabled = should_enable_apply_button(
        form_state.action, reason, form_state.new_value
    )

    has_validation_error = bool(form_state.validation_error)

    if st.button(
        label="Apply",
        key=f"correction_apply_{tab_index}",
        width="stretch",
        disabled=not apply_enabled or has_validation_error,
        type="primary",
    ):
        _handle_apply_correction(
            correction_processor=correction_processor,
            corrected_data=corrected_data,
            alias=alias,
            key_col=key_col,
            key_value=form_state.key_value,
            action=form_state.action,
            column=form_state.column,
            current_value=form_state.current_value,
            new_value=form_state.new_value,
            reason=reason,
        )


def _handle_apply_correction(
    correction_processor: CorrectionProcessor,
    corrected_data: pl.DataFrame,
    alias: str,
    key_col: str,
    key_value: str,
    action: str,
    column: str | None,
    current_value: Any,
    new_value: Any,
    reason: str,
) -> None:
    """
    Handle the application of a correction with validation.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    corrected_data : pl.DataFrame
        The current corrected data.
    alias : str
        The data alias/table name.
    key_col : str
        The name of the Survey KEY column.
    key_value : str
        The key value to correct.
    action : str
        The correction action type.
    column : str | None
        The column to modify (if applicable).
    current_value : Any
        The current value (if applicable).
    new_value : Any
        The new value (if applicable).
    reason : str
        The reason for correction.
    """
    try:
        # Validate input
        is_valid, error_msg = correction_processor.validate_correction_input(
            corrected_data,
            key_col,
            key_value,
            action,
            column,
            new_value,
        )

        if not is_valid:
            st.error(f"Validation error: {error_msg}")
            return

        # Apply the correction
        correction_processor.apply_correction(
            alias=alias,
            key_col=key_col,
            key_value=key_value,
            action=action,
            column=column,
            current_value=current_value,
            new_value=new_value,
            reason=reason,
        )

        st.success("Correction applied successfully!")
        st.rerun()

    except Exception as e:
        st.error(f"Error applying correction: {e!s}")


def render_correction_input_form(
    correction_processor: CorrectionProcessor,
    key_col: str,
    alias: str,
    tab_index: int,
) -> None:
    """
    Render input form for corrections with add and remove functionality.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    key_col : str
        The name of the Survey KEY column in the DataFrame.
    alias : str
        The data alias/table name.
    tab_index : int
        The tab index for unique widget keys.
    """
    corrected_data = correction_processor.get_corrected_data(alias)

    if corrected_data.is_empty():
        st.warning("No data available for correction.")
        return

    fc1, fc2, _ = st.columns([0.4, 0.3, 0.3])

    with fc1:
        render_add_correction_form(
            correction_processor=correction_processor,
            key_col=key_col,
            alias=alias,
            tab_index=tab_index,
        )

    with fc2:
        render_remove_correction_form(
            correction_processor=correction_processor,
            alias=alias,
            tab_index=tab_index,
        )


@st.fragment
def render_remove_correction_form(
    correction_processor: CorrectionProcessor,
    alias: str,
    tab_index: int,
) -> None:
    """
    Render the remove correction step form.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    alias : str
        The data alias/table name.
    tab_index : int
        The tab index for unique widget keys.
    """
    correction_summaries = correction_processor.get_correction_summary(alias)

    with st.popover(":material/delete: Remove correction step", width="stretch"):
        if correction_summaries:
            st.warning(
                "This will remove a correction step from the log and reapply "
                "remaining corrections."
            )
        else:
            st.info("No correction steps available to remove.")

        # Create selectbox with action descriptions
        action_options = [summary["action_index"] for summary in correction_summaries]
        selected_action = st.selectbox(
            label="Select Correction to Remove",
            options=action_options,
            key=f"remove_correction_{tab_index}",
            index=None,
            help="Select the correction you want to remove from the log",
            disabled=not correction_summaries,
        )

        # Show details of selected correction
        if selected_action:
            _display_correction_details(correction_summaries, selected_action)

        # Confirm removal button
        if st.button(
            label="Remove",
            key=f"confirm_remove_correction_{tab_index}",
            width="stretch",
            type="primary",
            help="Remove the selected correction step from the log",
            disabled=not selected_action,
        ):
            _handle_remove_correction(
                correction_processor, correction_summaries, alias, selected_action
            )


def _display_correction_details(
    correction_summaries: list[dict], selected_action: str
) -> None:
    """
    Display details of the selected correction.

    Parameters
    ----------
    correction_summaries : list[dict]
        List of correction summaries.
    selected_action : str
        The selected action index.
    """
    selected_summary = next(
        s for s in correction_summaries if s["action_index"] == selected_action
    )
    st.write(f"**Action:** {selected_summary['action']}")
    st.write(f"**Key:** {selected_summary['key_value']}")
    if selected_summary["column"]:
        st.write(f"**Column:** {selected_summary['column']}")
    if selected_summary["new_value"]:
        st.write(f"**New Value:** {selected_summary['new_value']}")
    st.write(f"**Reason:** {selected_summary['reason']}")


def _handle_remove_correction(
    correction_processor: CorrectionProcessor,
    correction_summaries: list[dict],
    alias: str,
    selected_action: str,
) -> None:
    """
    Handle the removal of a correction entry.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    correction_summaries : list[dict]
        List of correction summaries.
    alias : str
        The data alias/table name.
    selected_action : str
        The selected action index to remove.
    """
    try:
        # Find the index of the selected correction
        correction_index = next(
            s["index"]
            for s in correction_summaries
            if s["action_index"] == selected_action
        )

        # Remove the correction
        correction_processor.remove_correction_entry(alias, correction_index)

        st.success(f"Correction '{selected_action}' removed successfully!")
        st.rerun()

    except Exception as e:
        st.error(f"Error removing correction: {e!s}")


@st.fragment
def render_correction_log(
    correction_processor: CorrectionProcessor, alias: str, tab_index: int
) -> None:
    """
    Render the correction log display.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    alias : str
        The data alias/table name.
    tab_index : int
        The tab index for unique widget keys.
    """
    correction_log = correction_processor.get_correction_log(alias)

    with st.container(border=True):
        if correction_log.is_empty():
            st.info(
                "No corrections have been made yet. You can add corrections "
                "using the form above."
            )
        else:
            with st.container(border=True):
                st.subheader("Correction Log")
                st.dataframe(data=correction_log, width="stretch")


@st.fragment
def render_data_summary(
    correction_processor: CorrectionProcessor, data: pl.DataFrame
) -> None:
    """
    Render data summary metrics and preview.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    data : pl.DataFrame
        The data to summarize.
    """
    summary = correction_processor.get_data_summary(data)

    with st.container(border=True):
        st.subheader("Preview Corrected Data")
        st.write("---")

        mc1, mc2, mc3 = st.columns((0.3, 0.3, 0.4))

        mc1.metric(label="Rows", value=summary["rows"])
        mc2.metric(label="Columns", value=summary["columns"])
        mc3.metric(label="Missing Values", value=f"{summary['missing_percentage']}%")

        st.dataframe(data=data, width="stretch")


@st.fragment
def render_correction_tab(
    correction_processor: CorrectionProcessor, project_id: str, tab_index: int
) -> None:
    """
    Render a single correction tab with all components.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    project_id : str
        The project identifier.
    tab_index : int
        The index of the tab being rendered.
    """
    config: TabConfig = load_tab_config(project_id, tab_index)

    if not config:
        st.error(f"Error loading configuration for tab {tab_index}")
        return

    st.subheader(f"{config.page_name}")
    st.write("Add corrections to the data based on issues identified in checks.")

    # Ensure corrected data exists
    corrected_data = correction_processor.get_corrected_data(config.survey_data_name)

    if corrected_data.is_empty():
        st.warning(f"No data available for {config.survey_data_name}")
        return

    # Render components
    render_correction_input_form(
        correction_processor=correction_processor,
        key_col=config.survey_key,
        alias=config.survey_data_name,
        tab_index=tab_index,
    )

    render_correction_log(
        correction_processor=correction_processor,
        alias=config.survey_data_name,
        tab_index=tab_index,
    )

    render_data_summary(
        correction_processor=correction_processor,
        data=corrected_data,
    )


def render_page_header() -> None:
    """Render the page header and demo information."""
    st.title("Correct Data")
    st.markdown(
        "Make necessary corrections to data based on issues identified in checks."
    )

    demo_expander(
        "How to add correction steps",
        ImportDemoInfo.get_info_message("add_correction_step_info"),
        expanded=True,
    )


def render_page_navigation() -> None:
    """Render the page navigation controls."""
    page_navigation(
        prev={
            "page_name": st.session_state.get("st_output_page1", "output_view_1"),
            "label": "← Back: Output Page 1",
        },
    )


def main() -> None:
    """
    Main entry point for the correction view.

    This function orchestrates the entire page rendering process, including:
    - Setting up navigation and demo helpers
    - Validating prerequisites
    - Creating correction processor
    - Rendering correction tabs
    """
    # Set up demo navigation
    demo_sidebar_help()

    # Render page header
    render_page_header()

    # Get project ID from session state
    project_id: str = st.session_state["st_project_id"]

    # Validate prerequisites
    _, hfc_pages = validate_prerequisites(project_id)

    # Initialize correction processor
    correction_processor = CorrectionProcessor(project_id)

    # Create tabs for each HFC page
    corr_tabs = st.tabs(hfc_pages)

    for tab_index, tab in enumerate(corr_tabs):
        with tab:
            render_correction_tab(correction_processor, project_id, tab_index)

    # Render navigation
    render_page_navigation()


# Execute main function when run as a Streamlit page
if __name__ == "__main__":
    main()
