import pandas as pd

<<<<<<< HEAD
<<<<<<< HEAD
=======
=======
>>>>>>> b70f1c6 (format and lint pydms/src/utils)
<<<<<<< HEAD

>>>>>>> 31b8063 (scto_connector_new)
# Function to move a row up or down in a DataFrame
<<<<<<< HEAD
def move_row(df, row_index, direction='up'):
	if direction == 'up':
		if row_index == 0:
			return df
		else:
			row = df.iloc[row_index]
			df = df.drop(row_index)
			df = pd.concat([df.iloc[:row_index-1], pd.DataFrame(row).T, df.iloc[row_index-1:]]).reset_index(drop=True)
			return df
	elif direction == 'down':
		if row_index == len(df)-1:
			return df
		else:
			row = df.iloc[row_index]
			df = df.drop(row_index)
			df = pd.concat([df.iloc[:row_index], pd.DataFrame(row).T, df.iloc[row_index:]]).reset_index(drop=True)
			return df
	else:
		raise ValueError('Invalid direction. Please choose either "up" or "down".')
	
=======
def move_row(df, row_index, direction="up"):  # noqa: D417, RUF100
<<<<<<< HEAD
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


>>>>>>> 8bdaf0d (linter clean-up)
# Function to add a row to a DataFrame from a dictionary
def add_row(df, row_dict):
	row = pd.DataFrame(row_dict, index=[0])
	df = pd.concat([df, row]).reset_index(drop=True)
	return df

# Function to remove a row from a DataFrame
<<<<<<< HEAD
def remove_row(df, row_index):
	df = df.drop(row_index).reset_index(drop=True)
=======
def remove_row(df, row_index):  # noqa: D417, RUF100
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
=======
=======

>>>>>>> 809bfa0 (format and lint pydms/src/utils)
# Function to move a row up or down in a DataFrame
def move_row(df, row_index, direction="up"):  # noqa: D417
=======
>>>>>>> c350dfc (linter clean-up)
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
def add_row(df, row_dict):  # noqa: D417, RUF100
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
<<<<<<< HEAD
<<<<<<< HEAD
def remove_row(df, row_index):
<<<<<<< HEAD
	df = df.drop(row_index).reset_index(drop=True)
<<<<<<< HEAD
>>>>>>> a9d57df (scto_connector_new)
<<<<<<< HEAD
>>>>>>> 31b8063 (scto_connector_new)
=======
=======
>>>>>>> 224f63f (added form editor)
<<<<<<< HEAD
>>>>>>> d1b4532 (added form editor)
=======
=======
	df = df.drop(row_index).reset_index(drop = True)
>>>>>>> 38921a1 (wp - scto)
<<<<<<< HEAD
>>>>>>> d72d672 (wp - scto)
=======
=======
def remove_row(df, row_index):  # noqa: D417
=======
def remove_row(df, row_index):  # noqa: D417, RUF100
>>>>>>> c350dfc (linter clean-up)
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
>>>>>>> 809bfa0 (format and lint pydms/src/utils)
>>>>>>> b70f1c6 (format and lint pydms/src/utils)
