import polars as pl
import streamlit as st

from src.processing import (
    correction_apply_action,
    correction_load_log,
)

# DEFINE CONSTANTS FOR CORRECTION'

CORRECTION_ACTIONS = ("modify value", "remove value", "remove row")

# -- DATA CORERCTIONS PAGE --#
# Creates page for data preprocessing

st.title("Correct Data")
st.markdown("Make necessary corrections to data based on issues identified in checks.")

# get dataset alias and project ID from session state
alias_list: list[str] = st.session_state.st_raw_dataset_list
project_id: str = st.session_state.st_project_id

# show/hide data prep page

show_corr_page_info = False
if not alias_list:
    st.info(
        "No data available to prepare. Load a dataset from the import page to continue."
    )
else:
    show_corr_page_info = True


def correction_input_form(
    id_col: str,
    key_col: str,
    data_index: int,
    project_id: str,
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
    # get dataset
    if not isinstance(st.session_state[f"corrected_data{data_index}"], pl.DataFrame):
        corrected_data = pl.from_pandas(st.session_state[f"corrected_data{data_index}"])
    else:
        corrected_data = st.session_state[f"corrected_data{data_index}"]

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
            key=f"ID_correction_key_value__{i}",
        )
        if corr_key_val:
            current_id_val = corrected_data.filter(
                pl.col(survey_key) == corr_key_val
            ).select(id_col)[0, 0]
            st.text_input(
                label="Current ID Value",
                value=current_id_val,
                key=f"ID_correction_current_id_{i}",
                disabled=True,
            )
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
                    current_id=current_id_val,
                    key_value=corr_key_val,
                    current_value=current_value,
                    col_to_modify=col_to_modify,
                    new_value=new_value,
                    reason=reason,
                    data_index=data_index,
                )
                st.success("ID correction applied successfully!")

            # save corrections log to setting file
            log_name = alias.lower().replace(" ", "_").replace("-", "_")
            st.session_state[f"id_correction_log_{data_index}"].write_json(
                f"cache/{project_id}/settings/{log_name}.json"
            )


if show_corr_page_info:
    # get list of HFC pages from session state
    hfc_pages = st.session_state.config_pages["Page Name"].tolist()
    corr_tabs = st.tabs(hfc_pages)

    for idx, tab in enumerate(corr_tabs):
        with tab:
            page_name = hfc_pages[idx]
            st.subheader(f"{page_name}")
            # get value of survey key if Page Name is tab
            survey_key = st.session_state.config_pages["Survey KEY"][idx]
            survey_id = st.session_state.config_pages["Survey ID"][idx]
            survey_data = st.session_state.config_pages["Survey Data"][idx]

            i = alias_list.index(survey_data)

            # define session state for correction
            if f"corrected_data{i}" not in st.session_state:
                st.session_state[f"corrected_data{i}"] = pl.from_pandas(
                    st.session_state[f"prepped_data{i}"]
                )
            else:
                if isinstance(st.session_state[f"corrected_data{i}"], pl.DataFrame):
                    st.session_state[f"corrected_data{i}"] = st.session_state[
                        f"corrected_data{i}"
                    ].to_pandas()
                st.session_state[f"corrected_data{i}"] = pl.from_pandas(
                    st.session_state[f"corrected_data{i}"]
                )

            # load corrections log
            if f"id_correction_log_{i}" not in st.session_state:
                st.session_state[f"id_correction_log_{i}"] = correction_load_log(
                    project_id, page_name
                )

            st.write(
                "Correct ID duplicates by either modifying the ID or removing the row. "
                "Select the action from the dropdown and provide the necessary input."
            )

            correction_input_form(
                key_col=survey_key,
                id_col=survey_id,
                data_index=i,
                project_id=project_id,
                alias=page_name,
            )

            st.session_state[f"id_correction_log_{i}"] = st.data_editor(
                data=st.session_state[f"id_correction_log_{i}"],
                use_container_width=True,
                key=f"id_correction_log_displ_{i}",
                num_rows="dynamic",
            )

            row_count, col_count = st.session_state[f"corrected_data{i}"].shape

            # calculate missing values percentage
            miss_count = st.session_state[f"corrected_data{i}"].select(
                pl.all().is_null().sum()
            )
            miss_count = miss_count.with_columns(
                sum_of_missing_values=pl.sum_horizontal(pl.all())
            )
            miss_perc = round(
                (miss_count["sum_of_missing_values"][0] / (row_count * col_count))
                * 100,
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
                    data=st.session_state[f"corrected_data{i}"],
                    use_container_width=True,
                )
