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

# Get configuration data
hfc_config_logs = duckdb_get_table(
    project_id=project_id, alias="check_config", db_name="logs"
)
if hfc_config_logs.is_empty():
    st.info(
        "No checks configured. Please configure checks on the Configure Checks page."
    )
    st.stop()

# Get list of HFC pages from check config logs
hfc_pages = hfc_config_logs["page_name"].to_list()

if not hfc_pages:
    st.info(
        "No data available to prepare. Load a dataset from the import page to continue."
    )
    st.stop()


def render_correction_input_form(
    correction_processor: CorrectionProcessor,
    key_col: str,
    alias: str,
    tab_index: int,
) -> None:
    """Render input form for corrections.

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

    fc1, _ = st.columns([0.4, 0.6])
    with (
        fc1,
        st.popover(":material/add: Add correction step", width="stretch"),
    ):
        st.markdown("*Add new correction step*")
        
        # Get unique key values for selection
        key_options = corrected_data.select(key_col).unique(maintain_order=True).to_series().to_list()
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
                                        current_date = datetime.fromisoformat(current_value).date()
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
                            if new_value and col_dtype in [pl.Int64, pl.Int32, pl.Float64, pl.Float32]:
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
                reason and (
                    (corr_action == "modify value" and new_value) or
                    (corr_action == "remove value") or
                    (corr_action == "remove row")
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
                    is_valid, error_msg = correction_processor.validate_correction_input(
                        corrected_data, key_col, corr_key_val, corr_action, col_to_modify, new_value
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
                    st.error(f"Error applying correction: {str(e)}")


def render_correction_log(correction_processor: CorrectionProcessor, alias: str) -> None:
    """Render the correction log display.
    
    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance
    alias : str
        The data alias/table name
    """
    correction_log = correction_processor.get_correction_log(alias)
    
    with st.container(border=True):
        if correction_log.is_empty():
            st.info(
                "No corrections have been made yet. You can add corrections using the form above."
            )
        else:
            st.subheader("Correction Log")
            st.dataframe(
                data=correction_log,
                width="stretch",
            )


def render_data_summary(correction_processor: CorrectionProcessor, data: pl.DataFrame) -> None:
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


# Create tabs for each HFC page
corr_tabs = st.tabs(hfc_pages)

for tab_index, tab in enumerate(corr_tabs):
    with tab:
        # Get page configuration for current tab
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
        except Exception as e:
            st.error(f"Error loading configuration for tab {tab_index}: {str(e)}")
            continue

        st.subheader(f"{page_name}")
        st.write("Add corrections to the data based on issues identified in checks.")

        # Ensure corrected data exists (initialize from prepped data if needed)
        corrected_data = correction_processor.get_corrected_data(survey_data_name)
        
        if corrected_data.is_empty():
            st.warning(f"No data available for {survey_data_name}")
            continue

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
        )

        # Render data summary and preview
        render_data_summary(
            correction_processor=correction_processor,
            data=corrected_data,
        )

# Navigation
page_navigation(
    prev={
        "page_name": st.session_state.get("st_output_page1", "output_view_1"),
        "label": "← Back: Output Page 1",
    },
)
