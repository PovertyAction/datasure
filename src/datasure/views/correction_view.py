import polars as pl
import streamlit as st

from datasure.processing.corrections import CorrectionProcessor
from datasure.utils import duckdb_get_table, get_check_config_settings
from datasure.utils.navigations import page_navigation

# DEFINE CONSTANTS FOR CORRECTION
CORRECTION_ACTIONS = ("modify value", "remove value", "remove row")

st.title("Correct Data")
st.markdown("Make necessary corrections to data based on issues identified in checks.")

# Initialize project ID from session state
project_id: str = st.session_state.get("st_project_id", "")

if not project_id:
    st.info(
        "Select a project from the Start page and import data. You can also create a new project from the Start page."
    )
    st.stop()

# Initialize correction processor
correction_processor = CorrectionProcessor(project_id)


# Cache configuration data loading
@st.cache_data(ttl=120, show_spinner=False)
def get_hfc_config(project_id: str) -> tuple[pl.DataFrame, list[str]]:
    """Get HFC configuration data and page list."""
    hfc_config_logs = duckdb_get_table(
        project_id=project_id, alias="check_config", db_name="logs"
    )
    if hfc_config_logs.is_empty():
        return hfc_config_logs, []
    return hfc_config_logs, hfc_config_logs["page_name"].to_list()


hfc_config_logs, hfc_pages = get_hfc_config(project_id)

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


@st.fragment
def render_add_correction_form(
    correction_processor: CorrectionProcessor,
    key_col: str,
    alias: str,
    tab_index: int,
) -> None:
    """Render the add correction step form.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance
    key_col : str
        The name of the Survey KEY column in the DataFrame
    alias : str
        The data alias/table name
    tab_index : int
        The tab index for unique widget keys
    """
    # Get corrected data
    corrected_data = correction_processor.get_corrected_data(alias)

    if corrected_data.is_empty():
        st.warning("No data available for correction.")
        return

    with st.popover(":material/add: Add correction step", width="stretch"):
        st.markdown("*Add new correction step*")

        # Cache key options for better performance
        @st.cache_data(ttl=60, show_spinner=False)
        def get_key_options(data: pl.DataFrame, key_col: str) -> list:
            return (
                data.select(key_col).unique(maintain_order=True).to_series().to_list()
            )

        key_options = get_key_options(corrected_data, key_col)
        corr_key_val = st.selectbox(
            label="Select KEY",
            options=key_options,
            key=f"correction_key_value_{tab_index}",
        )

        if corr_key_val:
            corr_action = st.selectbox(
                label="Select Action",
                options=CORRECTION_ACTIONS,
                key=f"correction_action_{tab_index}",
            )

            col_to_modify = None
            current_value = None
            new_value = None

            if corr_action in ["modify value", "remove value"]:
                col_to_modify = st.selectbox(
                    label="Select Column to Modify",
                    options=corrected_data.columns,
                    key=f"correction_col_to_modify_{tab_index}",
                )

                if col_to_modify:
                    # Get current value
                    try:
                        current_value = corrected_data.filter(
                            pl.col(key_col) == corr_key_val
                        ).select(col_to_modify)[0, 0]
                    except Exception:
                        current_value = None

                    st.text_input(
                        label="Current Value",
                        value=str(current_value) if current_value is not None else "",
                        key=f"correction_current_value_{tab_index}",
                        disabled=True,
                    )

                    if corr_action == "modify value":
                        # Handle different input types based on column type
                        col_dtype = corrected_data.schema[col_to_modify]

                        if col_dtype == pl.Datetime:
                            if current_value:
                                try:
                                    from datetime import datetime

                                    if isinstance(current_value, str):
                                        current_date = datetime.fromisoformat(
                                            current_value
                                        ).date()
                                    else:
                                        current_date = current_value.date()
                                except Exception:
                                    current_date = None
                            else:
                                current_date = None

                            new_value = st.date_input(
                                label="New Value",
                                key=f"correction_new_value_{tab_index}",
                                value=current_date,
                                help="Select a date for the new value.",
                            )
                        else:
                            new_value = st.text_input(
                                label="New Value",
                                key=f"correction_new_value_{tab_index}",
                                placeholder="Enter new value",
                            )

                            # Validate numeric input
                            if new_value and col_dtype in [
                                pl.Int64,
                                pl.Int32,
                                pl.Float64,
                                pl.Float32,
                            ]:
                                try:
                                    float(new_value)
                                except ValueError:
                                    st.error("New value must be a number.")
                                    new_value = None

            elif corr_action == "remove row":
                st.warning(
                    "This will remove the row with the selected key value from the dataset."
                )

            reason = st.text_input(
                label="Reason for Correction",
                key=f"correction_reason_{tab_index}",
                placeholder="Enter reason for correction",
            )

            # Determine if apply button should be enabled
            apply_button_enabled = bool(
                reason
                and (
                    (corr_action == "modify value" and new_value)
                    or (corr_action == "remove value")
                    or (corr_action == "remove row")
                )
            )

            apply_correction_btn = st.button(
                label="Apply",
                key=f"correction_apply_{tab_index}",
                width="stretch",
                disabled=not apply_button_enabled,
                type="primary",
            )

            if apply_correction_btn:
                try:
                    # Validate input before applying
                    is_valid, error_msg = (
                        correction_processor.validate_correction_input(
                            corrected_data,
                            key_col,
                            corr_key_val,
                            corr_action,
                            col_to_modify,
                            new_value,
                        )
                    )

                    if not is_valid:
                        st.error(f"Validation error: {error_msg}")
                        return

                    # Apply the correction
                    correction_processor.apply_correction(
                        alias=alias,
                        key_col=key_col,
                        key_value=corr_key_val,
                        action=corr_action,
                        column=col_to_modify,
                        current_value=current_value,
                        new_value=new_value,
                        reason=reason,
                    )

                    st.success("Correction applied successfully!")
                    st.rerun()  # Refresh the page to show updated data

                except Exception as e:
                    st.error(f"Error applying correction: {e!s}")


def render_correction_input_form(
    correction_processor: CorrectionProcessor,
    key_col: str,
    alias: str,
    tab_index: int,
) -> None:
    """Render input form for corrections with add and remove functionality.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance
    key_col : str
        The name of the Survey KEY column in the DataFrame
    alias : str
        The data alias/table name
    tab_index : int
        The tab index for unique widget keys

    Returns
    -------
    None
    """
    # Get corrected data
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
    """Render the remove correction step form.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance
    alias : str
        The data alias/table name
    tab_index : int
        The tab index for unique widget keys
    """
    correction_summaries = correction_processor.get_correction_summary(alias)

    if not correction_summaries:
        st.info("No corrections to remove.")
        return

    with st.popover(":material/delete: Remove correction step", width="stretch"):
        st.warning(
            "This will remove a correction step from the log and reapply remaining corrections."
        )

        # Create selectbox with action descriptions
        action_options = [summary["action_index"] for summary in correction_summaries]
        selected_action = st.selectbox(
            label="Select Correction to Remove",
            options=action_options,
            key=f"remove_correction_{tab_index}",
            index=None,
            help="Select the correction you want to remove from the log",
        )

        # Show details of selected correction
        if selected_action:
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

        # Confirm removal button
        remove_button = st.button(
            label="Remove",
            key=f"confirm_remove_correction_{tab_index}",
            width="stretch",
            type="primary",
            help="Remove the selected correction step from the log",
            disabled=not selected_action,
        )

        if remove_button and selected_action:
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
                st.rerun()  # Refresh the page to show updated data

            except Exception as e:
                st.error(f"Error removing correction: {e!s}")


@st.fragment
def render_correction_log(
    correction_processor: CorrectionProcessor, alias: str, tab_index: int
) -> None:
    """Render the correction log display with remove functionality.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance
    alias : str
        The data alias/table name
    tab_index : int
        The tab index for unique widget keys
    """
    correction_log = correction_processor.get_correction_log(alias)

    with st.container(border=True):
        if correction_log.is_empty():
            st.info(
                "No corrections have been made yet. You can add corrections using the form above."
            )
        else:
            with st.container(border=True):
                st.subheader("Correction Log")

                # Display the correction log
                st.dataframe(
                    data=correction_log,
                    width="stretch",
                )


@st.fragment
def render_data_summary(
    correction_processor: CorrectionProcessor, data: pl.DataFrame
) -> None:
    """Render data summary metrics.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance
    data : pl.DataFrame
        The data to summarize
    """
    summary = correction_processor.get_data_summary(data)

    with st.container(border=True):
        st.subheader("Preview Corrected Data")
        st.write("---")

        mc1, mc2, mc3 = st.columns((0.3, 0.3, 0.4))

        mc1.metric(label="Rows", value=summary["rows"])
        mc2.metric(label="Columns", value=summary["columns"])
        mc3.metric(label="Missing Values", value=f"{summary['missing_percentage']}%")

        # Display data
        st.dataframe(
            data=data,
            width="stretch",
        )


# Cache tab configuration data
@st.cache_data(ttl=120, show_spinner=False)
def get_tab_config(project_id: str, tab_index: int) -> tuple[str, str, str]:
    """Get tab configuration data for rendering."""
    try:
        (
            page_name,
            survey_data_name,
            survey_key,
            survey_id,
            survey_date,
            enumerator,
            backcheck_data_name,
            tracking_data_name,
        ) = get_check_config_settings(
            project_id=project_id,
            page_row_index=tab_index,
        )
        return page_name, survey_data_name, survey_key  # noqa: TRY300
    except Exception:
        return "", "", ""


@st.fragment
def render_correction_tab(
    correction_processor: CorrectionProcessor, project_id: str, tab_index: int
) -> None:
    """Render a single correction tab."""
    page_name, survey_data_name, survey_key = get_tab_config(project_id, tab_index)

    if not page_name:
        st.error(f"Error loading configuration for tab {tab_index}")
        return

    st.subheader(f"{page_name}")
    st.write("Add corrections to the data based on issues identified in checks.")

    # Ensure corrected data exists (initialize from prepped data if needed)
    corrected_data = correction_processor.get_corrected_data(survey_data_name)

    if corrected_data.is_empty():
        st.warning(f"No data available for {survey_data_name}")
        return

    # Render correction input form
    render_correction_input_form(
        correction_processor=correction_processor,
        key_col=survey_key,
        alias=survey_data_name,
        tab_index=tab_index,
    )

    # Render correction log
    render_correction_log(
        correction_processor=correction_processor,
        alias=survey_data_name,
        tab_index=tab_index,
    )

    # Render data summary and preview
    render_data_summary(
        correction_processor=correction_processor,
        data=corrected_data,
    )


# Create tabs for each HFC page
corr_tabs = st.tabs(hfc_pages)

for tab_index, tab in enumerate(corr_tabs):
    with tab:
        render_correction_tab(correction_processor, project_id, tab_index)

# Navigation
page_navigation(
    prev={
        "page_name": st.session_state.get("st_output_page1", "output_view_1"),
        "label": "← Back: Output Page 1",
    },
)
