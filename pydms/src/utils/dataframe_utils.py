import pandas as pd


# Function to move a row up or down in a DataFrame
def move_row(df, row_index, direction="up"):  # noqa: D417
    """Move a row up or down in a DataFrame.

    Parameters
    ----------
    df (pd.DataFrame): The DataFrame to modify.
        The DataFrame in which the row will be moved.
    row_index (int): The index of the row to move.
        The position of the row to be moved.
    direction (str): The direction to move the row, either "up" or "down".
        The direction in which to move the row.

    Returns
    -------
    pd.DataFrame: The modified DataFrame with the row moved.

    """
    if direction == "up":
        if row_index == 0:
            return df
        else:
            row = df.iloc[row_index]
            df = df.drop(row_index)
            df = pd.concat(
                [
                    df.iloc[: row_index - 1],
                    pd.DataFrame(row).T,
                    df.iloc[row_index - 1 :],
                ]
            ).reset_index(drop=True)
            return df
    elif direction == "down":
        if row_index == len(df) - 1:
            return df
        else:
            row = df.iloc[row_index]
            df = df.drop(row_index)
            df = pd.concat(
                [df.iloc[:row_index], pd.DataFrame(row).T, df.iloc[row_index:]]
            ).reset_index(drop=True)
            return df
    else:
        raise ValueError('Invalid direction. Please choose either "up" or "down".')


# Function to add a row to a DataFrame from a dictionary
def add_row(df, row_dict):  # noqa: D417
    """Add a row to a DataFrame from a dictionary.

    Parameters
    ----------
    df (pd.DataFrame): The DataFrame to modify.
        The DataFrame to which the row will be added.
    row_dict (dict): The dictionary representing the row to add.
        The dictionary containing the data for the new row.

    Returns
    -------
    pd.DataFrame: The modified DataFrame with the new row added.

    """
    row = pd.DataFrame(row_dict, index=[0])
    df = pd.concat([df, row]).reset_index(drop=True)
    return df


# Function to remove a row from a DataFrame
def remove_row(df, row_index):  # noqa: D417
    """Remove a row from a DataFrame.

    Parameters
    ----------
    df (pd.DataFrame): The DataFrame to modify.
        The DataFrame from which the row will be removed.
    row_index (int): The index of the row to remove.
        The position of the row to be removed.

    Returns
    -------
    pd.DataFrame: The modified DataFrame with the row removed.

    """
    df = df.drop(row_index).reset_index(drop=True)
