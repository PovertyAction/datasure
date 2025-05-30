import polars as pl


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


def id_correction(
    data: pl.DataFrame, corrections_log: pl.DataFrame, id_col: str, key_col: str
) -> pl.DataFrame:
    """
    Apply ID corrections to a DataFrame based on a corrections log.

    Args:
        data (pl.DataFrame): The DataFrame to apply corrections to.
        corrections_log (pl.DataFrame): The corrections log containing ID changes.
        id_col (str): The name of the Survey ID column in the DataFrame.
        key_col (str): The name of the key column in the DataFrame.

    Returns
    -------
        pl.DataFrame: The DataFrame with applied ID corrections.
    """
    for _, row in corrections_log.iterrows():
        key = row["KEY"]
        current_id = row["current id"]
        new_id = row["new id"]
        action = row["action"]

        if action == "replace":
            # replace current_id with new_id for row with matching key
            data = data.with_columns(
                pl.when(pl.col(key_col) == key)
                .then(pl.col(id_col).replace(current_id, new_id))
                .otherwise(pl.col(id_col))
                .alias(id_col)
            )

        elif action == "drop":
            # drop row with matching key
            data = data.filter(pl.col(key_col) != key)

    return data


def other_correction(
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
