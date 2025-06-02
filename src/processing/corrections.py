import polars as pl
import streamlit as st


def load_corrections_log(file_path: str, type: str = "id") -> pl.DataFrame:
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
        if type == "id":
            log = pl.DataFrame(
                {
                    "KEY": pl.Series([], dtype=pl.String),
                    "current id": pl.Series([], dtype=pl.String),
                    "action": pl.Series([], dtype=pl.String),
                    "new id": pl.Series([], dtype=pl.String),
                    "reason": pl.Series([], dtype=pl.String),
                }
            )
        elif type == "other":
            log = pl.DataFrame(
                {
                    "id": pl.Series([], dtype=pl.String),
                    "column": pl.Series([], dtype=pl.String),
                    "action": pl.Series([], dtype=pl.String),
                    "current value": pl.Series([], dtype=pl.String),
                    "new value": pl.Series([], dtype=pl.String),
                    "reason": pl.Series([], dtype=pl.String),
                }
            )

    return log


def apply_id_correction(
    data_index: int,
    action: str | None,
    key_col: str | None,
    id_col: str | None,
    key_value: any,
    current_id: any,
    new_id: any,
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
            "current id": current_id,
            "action": action,
            "new id": new_id,
            "reason": reason,
        }
        # check if current_id and new_id are not strings and convert them to strings
        if not isinstance(current_id, str):
            new_correction["current id"] = str(current_id)
        corrections_log = pl.concat([corrections_log, pl.DataFrame([new_correction])])

    # Apply corrections based on the corrections log
    for row in range(len(corrections_log)):
        key_value = corrections_log.item(row, "KEY")
        current_id = corrections_log.item(row, "current id")
        action = corrections_log.item(row, "action")
        new_id = corrections_log.item(row, "new id")

        if action == "modify id":
            if isinstance(new_id, str):
                corrected_data = corrected_data.with_columns(
                    pl.when(pl.col(key_col) == key_value)
                    .then(pl.lit(new_id))
                    .otherwise(pl.col(id_col))
                    .alias(id_col)
                )
            else:
                if not isinstance(new_id, str):
                    new_id = int(new_id)
                corrected_data = corrected_data.with_columns(
                    pl.when(pl.col(key_col) == key_value)
                    .then(new_id)
                    .otherwise(pl.col(id_col))
                    .alias(id_col)
                )
        elif action == "remove row":
            # remove rows with matching key_value
            corrected_data = corrected_data.filter(pl.col(key_col) != key_value)

    # Update the session state with the corrections log and corrected data
    st.session_state[f"id_correction_log_{data_index}"] = corrections_log
    st.session_state[f"corrected_data{data_index}"] = corrected_data


def apply_other_correction(
    data: pl.DataFrame, corrections_log: pl.DataFrame, id_col: str
) -> pl.DataFrame:
    """
    Apply other corrections to a DataFrame based on a corrections log.

    Args:
        data (pl.DataFrame): The DataFrame to apply corrections to.
        corrections_log (pl.DataFrame): The corrections log containing other changes.
        id_col (str): The name of the Survey ID column in the DataFrame.

    Returns
    -------
        pl.DataFrame: The DataFrame with applied other corrections.
    """
    for _, row in corrections_log.iterrows():
        id_value = row["id"]
        column = row["column"]
        current_value = row["current value"]
        new_value = row["new value"]
        action = row["action"]

        if action == "replace":
            # replace current_value with new_value for rows with matching id
            data = data.with_columns(
                pl.when(
                    (pl.col(id_col) == id_value) & (pl.col(column) == current_value)
                )
                .then(new_value)
                .otherwise(pl.col(column))
                .alias(column)
            )
        elif action == "remove":
            # remove value from column for rows with matching id
            data = data.with_columns(
                pl.when(pl.col(id_col) == id_value)
                .then(pl.lit(None).cast(pl.String))
                .otherwise(pl.col(column))
                .alias(column)
            )

    return data
