import polars as pl
import streamlit as st


def correction_apply_action(
    data_index: int,
    key_col: str,
    project_id: str,
    page_name=None,
    action=None,
    key_value=None,
    current_id=None,
    current_value=None,
    col_to_modify=None,
    new_value=None,
    reason: str | None = None,
) -> None:
    """
    Apply ID corrections to a DataFrame based on a corrections log.

    Parameters
    ----------
        action (str): Action to apply to the DataFrame.
        key_col (str): The name of the Survey KEY column in the DataFrame.
        id_col (str): The name of the Survey ID column in the DataFrame.
        new_id (str | int | None): The new ID value to apply if the action
        is "modify id".

    Returns
    -------
        pl.DataFrame: The DataFrame with applied ID corrections.
    """
    # if action_col is provided, we add new column to corrections log
    # and apply new ID correction
    # else, we apply corrections to existing correction log
    if page_name and (f"id_correction_log_{data_index}" not in st.session_state):
        st.session_state[f"id_correction_log_{data_index}"] = "None"
    corrections_log = st.session_state[f"id_correction_log_{data_index}"]
    if f"corrected_data{data_index}" not in st.session_state:
        alias_list = st.session_state["st_raw_dataset_list"]
        config_pages = st.session_state["config_pages"]
        survey_data = config_pages["Survey Data"][data_index]
        prep_data_index = alias_list.index(survey_data)
        st.session_state[f"corrected_data{data_index}"] = pl.from_pandas(
            st.session_state[f"prepped_data{prep_data_index}"]
        )
    corrected_data = st.session_state[f"corrected_data{data_index}"]

    if action is not None:
        # Add new ID correction to the corrections log
        new_correction = {
            "KEY": key_value,
            "ID": current_id,
            "action": action,
            "column": col_to_modify,
            "current value": current_value,
            "new value": new_value,
            "reason": reason,
        }
        # check all values in new correction are strings, else convert them to strings
        new_correction = {
            k: str(v) if v is not None else "" for k, v in new_correction.items()
        }
        corrections_log = pl.concat([corrections_log, pl.DataFrame([new_correction])])

    # Apply corrections based on the corrections log
    for row in range(len(corrections_log)):
        key_value = corrections_log.item(row, "KEY")
        current_value = corrections_log.item(row, "current value")
        action = corrections_log.item(row, "action")
        col_to_modify = corrections_log.item(row, "column")
        current_id = corrections_log.item(row, "ID")
        new_value = corrections_log.item(row, "new value")

        if action == "modify value":
            # check if col_to_modify is a string column
            if corrected_data[col_to_modify].dtype == pl.String:
                corrected_data = corrected_data.with_columns(
                    pl.when(pl.col(key_col) == key_value)
                    .then(pl.lit(new_value))
                    .otherwise(pl.col(col_to_modify))
                    .alias(col_to_modify)
                )
            else:
                if isinstance(new_value, str):
                    # convert new_value to the same type as col_to_modify
                    new_value = pl.lit(new_value).cast(
                        corrected_data[col_to_modify].dtype
                    )
                    corrected_data = corrected_data.with_columns(
                        pl.when(pl.col(key_col) == key_value)
                        .then(new_value)
                        .otherwise(pl.col(col_to_modify))
                        .alias(col_to_modify)
                    )
        elif action == "remove value":
            # replace the value in col_to_modify with None
            corrected_data = corrected_data.with_columns(
                pl.when(pl.col(key_col) == key_value)
                .then(None)
                .otherwise(pl.col(col_to_modify))
                .alias(col_to_modify)
            )
        elif action == "remove row":
            # remove rows with matching key_value
            corrected_data = corrected_data.filter(pl.col(key_col) != key_value)

    # Update the session state with the corrections log and corrected data
    st.session_state[f"id_correction_log_{data_index}"] = corrections_log
    st.session_state[f"corrected_data{data_index}"] = corrected_data
