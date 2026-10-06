"""
Correction view for making data corrections based on identified issues.

This module provides an interactive interface for applying, tracking, and managing
data corrections across multiple datasets. Corrections are logged and can be
removed or modified as needed.
"""

from typing import Any

import polars as pl
import streamlit as st
from pydantic import BaseModel, Field

from datasure.processing.correction_log import (
    CORRECTIONS_PAGE_SOURCE,
    HARD_SEVERITY,
    Action,
    ensure_log_columns,
)
from datasure.processing.corrections import CorrectionProcessor
from datasure.utils.correction_form import (
    get_current_value,
    render_correction_form,
)
from datasure.utils.correction_form import (
    render_value_input_widget as render_shared_value_input_widget,
)
from datasure.utils.duckdb_utils import duckdb_get_table
from datasure.utils.navigations_utils import (
    add_demo_navigation,
    demo_sidebar_help,
    page_navigation,
)
from datasure.utils.onboarding_utils import ImportDemoInfo, demo_expander
from datasure.utils.reapply_utils import highlight_status, warn_reapply_failures
from datasure.utils.settings_utils import get_check_config_settings
from datasure.utils.ui_utils import (
    confirm_dialog,
    metric_row,
    page_header,
    row_styler,
    section_header,
    styled_dataframe,
)


class TabConfig(BaseModel):
    """Configuration for a correction tab."""

    page_name: str = Field(..., description="Name of the page/check")
    survey_data_name: str = Field(..., description="Name of the survey data alias")
    survey_key: str = Field(..., description="Name of the survey KEY column")
    survey_id: str | None = Field(
        None, description="Name of the survey ID column, if configured"
    )


def render_value_input_widget(
    column: str,
    col_dtype: pl.DataType,
    current_value: Any,
    tab_index: int,
) -> tuple[Any, str | None]:
    """
    Render the new-value input for a column on a Corrections page tab.

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
    return render_shared_value_input_widget(column, col_dtype, current_value, tab_index)


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
        survey_id=page_config.get("survey_id"),
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


def render_add_correction_form(
    correction_processor: CorrectionProcessor,
    key_col: str,
    alias: str,
    tab_index: int,
    survey_id_col: str | None = None,
) -> None:
    """
    Render the add correction step form.

    The page picks the KEY and shows its Survey ID; the shared correction
    form renders the action, new-value and reason inputs and the Apply
    button. Apply goes through `_handle_apply_correction`, so the page keeps
    offering any KEY, any column and every correction action.

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
    survey_id_col : str | None
        The name of the configured Survey ID column, if any. When set (and
        present in the data), the corresponding Survey ID is shown once a
        KEY is selected.
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

        survey_id_value = None
        if survey_id_col and survey_id_col in corrected_data.columns:
            survey_id_value = get_current_value(
                corrected_data, key_col, corr_key_val, survey_id_col
            )
            st.write(f"**Survey ID:** {survey_id_value}")

        # Steps 2-5: action, new value, reason and Apply
        render_correction_form(
            correction_processor=correction_processor,
            alias=alias,
            key_col=key_col,
            data=corrected_data,
            key_value=corr_key_val,
            key_namespace=tab_index,
            source=CORRECTIONS_PAGE_SOURCE,
            survey_id_value=survey_id_value,
            on_apply=lambda state: _handle_apply_correction(
                correction_processor=correction_processor,
                corrected_data=corrected_data,
                alias=alias,
                key_col=key_col,
                key_value=state.key_value,
                action=state.action,
                column=state.column,
                current_value=state.current_value,
                new_value=state.new_value,
                reason=state.reason,
                survey_id_value=survey_id_value,
            ),
        )


def _handle_apply_correction(
    correction_processor: CorrectionProcessor,
    corrected_data: pl.DataFrame,
    alias: str,
    key_col: str,
    key_value: str,
    action: Action,
    column: str | None,
    current_value: Any,
    new_value: Any,
    reason: str,
    survey_id_value: Any = None,
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
    action : Action
        The correction action type.
    column : str | None
        The column to modify (if applicable).
    current_value : Any
        The current value (if applicable).
    new_value : Any
        The new value (if applicable).
    reason : str
        The reason for correction.
    survey_id_value : Any
        The Survey ID value for this KEY, if a Survey ID column is
        configured, to record alongside the correction log entry.
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
            survey_id_value=survey_id_value,
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
    survey_id_col: str | None = None,
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
    survey_id_col : str | None
        The name of the configured Survey ID column, if any.
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
            survey_id_col=survey_id_col,
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
        if not correction_summaries:
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
            confirm_dialog(
                "Remove correction step",
                "This removes the selected correction step from the log and "
                "reapplies the remaining corrections. This cannot be undone.",
                confirm_label="Remove",
                on_confirm=lambda: _handle_remove_correction(
                    correction_processor, correction_summaries, alias, selected_action
                ),
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
    if selected_summary.get("check_type"):
        st.write(f"**Check type:** {selected_summary['check_type']}")
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
        failures = correction_processor.remove_correction_entry(alias, correction_index)

        st.success(f"Correction '{selected_action}' removed successfully!")
        warn_reapply_failures(
            failures, "Some remaining corrections could not be reapplied"
        )
        st.rerun()

    except Exception as e:
        st.error(f"Error removing correction: {e!s}")


def _build_correction_log_display(correction_log: pl.DataFrame) -> pl.DataFrame:
    """Prepare a correction log for display in the Correction Log table.

    Backfills columns missing from logs saved before they existed, orders
    columns so status/status_reason sit right after action, and relabels the
    "ID" column as "Survey ID" for display. "accept" rows carry the check
    whose flag was accepted in check_type and, for a hard constraint
    violation, severity "hard"; source names the page that made each entry
    and user names who made it (empty for entries logged before it was
    recorded).

    Parameters
    ----------
    correction_log : pl.DataFrame
        The raw correction log, as persisted.

    Returns
    -------
    pl.DataFrame
        The log with status columns present, in display column order, ready
        for display.
    """
    correction_log = ensure_log_columns(correction_log)

    display_columns = [
        "date",
        "user",
        "KEY",
        "ID",
        "action",
        "status",
        "status_reason",
        "check_type",
        "severity",
        "column",
        "current_value",
        "new_value",
        "reason",
        "source",
    ]
    # "ID" holds the Survey ID value recorded for the KEY, if one was
    # configured - rename it for display so the column reads clearly.
    return correction_log.select(display_columns).rename({"ID": "Survey ID"})


def highlight_hard_acceptance(row: Any) -> list[str]:
    """Style every cell of a hard-violation acceptance in the Correction Log.

    Used with a pandas ``Styler`` (``df.style.apply(highlight_hard_acceptance,
    axis=1)``). Accepting a value that breaks a hard constraint overrides a
    bound meant to be absolute, so those rows stand out for review.
    """
    action, severity = row.get("action"), row.get("severity")
    # Missing values may be pd.NA, which can't be used in a boolean test.
    is_hard_accept = (
        isinstance(action, str)
        and isinstance(severity, str)
        and action == Action.ACCEPT
        and severity == HARD_SEVERITY
    )
    style = "background-color: rgba(220, 53, 69, 0.15)" if is_hard_accept else ""
    return [style] * len(row)


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
            section_header("Correction Log")

            log_display = _build_correction_log_display(correction_log)
            styled_dataframe(
                row_styler(log_display, highlight_hard_acceptance).map(
                    highlight_status, subset=["status"]
                ),
                width="stretch",
            )


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
        section_header("Preview Corrected Data")
        st.divider()

        metric_row(
            [
                ("Rows", summary["rows"]),
                ("Columns", summary["columns"]),
                ("Missing Values", f"{summary['missing_percentage']}%"),
            ]
        )

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

    section_header(f"{config.page_name}")
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
        survey_id_col=config.survey_id,
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
    page_header(
        "Correct Data",
        "Make corrections to data based on issues identified in checks.",
    )

    demo_expander(
        "How to add correction steps",
        ImportDemoInfo.get_info_message("add_correction_step_info"),
        expanded=True,
    )


def render_page_navigation() -> None:
    """Render the page navigation controls."""
    replication_page = st.session_state.get("st_replication_page")
    page_navigation(
        prev={
            "page_name": st.session_state.get("st_output_page1", "output_view_1"),
            "label": "← Back: Output Page 1",
        },
        next={
            "page_name": replication_page,
            "label": "Export Replication Package →",
        }
        if replication_page
        else None,
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
    add_demo_navigation("correction_view", step=6)

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
