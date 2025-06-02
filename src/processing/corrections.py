import polars as pl
import streamlit as st


def correction_load_log(file_path: str) -> pl.DataFrame:
    """
    Load the corrections log from a json file into a polars DataFrame.

    Args:
        file_path (str): The path to the corrections log CSV file.
        type (str): The type of corrections log, default is "id".
            - If the type is "id" and file is missing, it will load an empty ID
                correction log.
            - if type is "other" and file is missing, it will load an empty other
                correction log.

    Returns
    -------
        pl.DataFrame: A DataFrame containing the corrections log.
    """
    try:
        log = pl.read_json(file_path)

    except FileNotFoundError:
        log = pl.DataFrame(
            {
                "KEY": pl.Series([], dtype=pl.String),
                "ID": pl.Series([], dtype=pl.String),
                "action": pl.Series([], dtype=pl.String),
                "column": pl.Series([], dtype=pl.String),
                "current value": pl.Series([], dtype=pl.String),
                "new value": pl.Series([], dtype=pl.String),
                "reason": pl.Series([], dtype=pl.String),
            }
        )
    return log


def correction_apply_action(
    data_index: int,
    action: str | None,
    key_col: str | None,
    key_value: any,
    current_id: any,
    current_value: any,
    col_to_modify: any,
    new_value: any,
    reason: str | None,
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

    corrections_log = st.session_state[f"id_correction_log_{data_index}"]
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
