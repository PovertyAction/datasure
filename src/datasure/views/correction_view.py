import polars as pl
import streamlit as st

from datasure.processing import (
    correction_apply_action,
)
from datasure.utils import (
    duckdb_get_table,
    duckdb_save_table,
    get_check_config_settings,
)

# DEFINE CONSTANTS FOR CORRECTION'

CORRECTION_ACTIONS = ("modify value", "remove value", "remove row")

st.title("Correct Data")
st.markdown("Make necessary corrections to data based on issues identified in checks.")

project_id: str = st.session_state.st_project_id

if not project_id:
    st.info(
        "Select a project from the Start page and import data. You can also create a new project from the Start page."
    )
    st.stop()

hfc_config_logs = duckdb_get_table(
    project_id=project_id, alias="check_config", db_name="logs"
)
if hfc_config_logs.is_empty():
    st.info(
        "No checks configured. Please configure checks on the Configure Checks page."
    )
    st.stop()

# get list of HFC pages from check config logs
hfc_pages = hfc_config_logs["page_name"].to_list()

# -- DATA CORERCTIONS PAGE --#
# Creates page for data preprocessing


# show/hide data prep page

show_corr_page_info = False
if not hfc_pages:
    st.info(
        "No data available to prepare. Load a dataset from the import page to continue."
    )
    st.stop()


def correction_input_form(
    project_id: str,
    key_col: str,
    alias: str,
) -> None:
    """Define input form for corrections

    Parameters
    ----------
        id_col (str): The name of the Survey ID column in the DataFrame.
        key_col (str): The name of the Survey KEY column in the DataFrame.

    Returns
    -------
        None
    """
    # get corrected data keys
    corrected_data = duckdb_get_table(
        project_id=project_id,
        alias=alias,
        db_name="corrected",
    )
    fc1, _ = st.columns([0.4, 0.6])
    with (
        fc1,
        st.popover(":material/add: Add ID correction step", use_container_width=True),
    ):
        st.markdown("*Add new ID correction step*")
        key_options = corrected_data.select(survey_key).unique(maintain_order=True)
        corr_key_val = st.selectbox(
            label="Select KEY",
            options=key_options,
            key=f"ID_correction_key_value_{i}",
        )
        if corr_key_val:
            corr_action = st.selectbox(
                label="Select Action",
                options=CORRECTION_ACTIONS,
                key=f"ID_correction_action_{i}",
            )

            if corr_action == "modify value" or corr_action == "remove value":
                col_to_modify = st.selectbox(
                    label="Select Column to Modify",
                    options=corrected_data.columns,
                    key=f"ID_correction_col_to_modify_{i}",
                )

                # display current value
                current_value = corrected_data.filter(
                    pl.col(survey_key) == corr_key_val
                ).select(col_to_modify)[0, 0]

                st.text_input(
                    label="Current Value",
                    value=current_value,
                    key=f"ID_correction_current_value_{i}",
                    disabled=True,
                )
                if corr_action == "modify value":
                    # if column is a date column, we use date or datetime input
                    if corrected_data.dtypes == pl.datetime:
                        new_value = st.date_input(
                            label="New Value",
                            key=f"ID_correction_new_value_{i}",
                            value=current_value,
                            help="Select a date for the new value.",
                        )
                        # convert date to datetime
                        new_value = pl.datetime(
                            new_value.year, new_value.month, new_value.day
                        )
                    # else we use text input
                    else:
                        new_value = st.text_input(
                            label="New Value",
                            key=f"ID_correction_new_value_{i}",
                            placeholder="Enter new value",
                        )
                        # validate new value
                        # if col_to_modify is a numeric column, we check if the
                        # new value is
                        # a number
                        if corrected_data.schema[col_to_modify] in [
                            "int",
                            "float",
                        ]:
                            try:
                                new_value = float(new_value)
                            except ValueError:
                                st.error("New value must be a number.")
                                new_value = None
                else:
                    new_value = None
                    current_value = None
            elif corr_action == "remove row":
                st.warning(
                    "This will remove the row with the current ID value from the dataset."
                )
                new_value, current_value, col_to_modify = None, None, None
            reason = st.text_input(
                label="Reason for Correction",
                key=f"ID_correction_reason_{i}",
                placeholder="Enter reason for correction",
            )
            apply_button_enabled = bool(
                (corr_action == "modify value" and new_value and reason)
                or bool(corr_action == "remove row" and reason)
                or bool(corr_action == "remove value" and reason)
            )
            apply_id_correction_btn = st.button(
                label="Apply",
                key=f"ID_correction_apply_{i}",
                use_container_width=True,
                disabled=not apply_button_enabled,
            )

            if apply_id_correction_btn:
                correction_apply_action(
                    action=corr_action,
                    key_col=key_col,
                    key_value=corr_key_val,
                    current_value=current_value,
                    col_to_modify=col_to_modify,
                    new_value=new_value,
                    reason=reason,
                )
                st.success("ID correction applied successfully!")

                # update the corrections log
                new_log_entry = {
                    "date": pl.datetime.now(),
                    "KEY": corr_key_val,
                    "ID": current_value,
                    "action": corr_action,
                    "column": col_to_modify,
                    "current value": current_value,
                    "new value": new_value,
                    "reason": reason,
                }

                # get current corrections log
                current_log = duckdb_get_table(
                    project_id=project_id,
                    alias=f"corr_log_{alias}",
                    db_name="logs",
                )

                # add new entry to the log
                log = pl.concat([current_log, pl.DataFrame(new_log_entry)])

                duckdb_save_table(
                    project_id,
                    log,
                    alias=f"corr_log_{alias}",
                    db_name="logs",
                )


# get list of HFC pages from session state
corr_tabs = st.tabs(hfc_pages)

for i, tab in enumerate(corr_tabs):
    with tab:
        # get page name for current index from polars dataframe hfc_config_logs
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
            page_row_index=i,
        )

        st.subheader(f"{page_name}")

        # get current corrected data, if empty, get prepped data and save
        # as corrected data
        corrected_data = duckdb_get_table(
            project_id,
            alias=survey_data_name,
            db_name="corrected",
        )

        if corrected_data.is_empty():
            corrected_data = duckdb_get_table(
                project_id,
                alias=survey_data_name,
                db_name="prep",
            )

        duckdb_save_table(
            project_id,
            corrected_data,
            alias=survey_data_name,
            db_name="corrected",
        )

        st.write("Add corrections to the data based on issues identified in checks.")

        correction_input_form(
            project_id=project_id,
            key_col=survey_key,
            alias=survey_data_name,
        )

        # load correction log
        correction_log = duckdb_get_table(
            project_id=project_id,
            alias=f"corr_log_{survey_data_name}",
            db_name="logs",
        )

        with st.container(border=True):
            if correction_log.is_empty():
                st.info(
                    "No corrections have been made yet. You can add corrections using the form above."
                )
            else:
                st.subheader("Correction Log")
                st.dataframe(
                    data=correction_log,
                    use_container_width=True,
                )

        row_count, col_count = corrected_data.shape

        # calculate missing values percentage
        miss_count = corrected_data.select(pl.all().is_null().sum())
        miss_count = miss_count.with_columns(
            sum_of_missing_values=pl.sum_horizontal(pl.all())
        )
        miss_perc = round(
            (miss_count["sum_of_missing_values"][0] / (row_count * col_count)) * 100,
            2,
        )

        # display preview of peppered data
        with st.container(border=True):
            st.subheader("Preview Corrected Data")
            st.write("---")

            mc1, mc2, mc3 = st.columns((0.3, 0.3, 0.4))

            mc1.metric(label="Rows", value=row_count)
            mc2.metric(label="Columns", value=col_count)
            mc3.metric(label="Missing Values", value=f"{miss_perc}%")

            # display data
            st.dataframe(
                data=corrected_data,
                use_container_width=True,
            )
