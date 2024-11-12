import pandas as pd

<<<<<<< HEAD
=======
<<<<<<< HEAD

>>>>>>> 31b8063 (scto_connector_new)
# Function to move a row up or down in a DataFrame
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
# Function to move a row up or down in a DataFrame
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
	
# Function to add a row to a DataFrame from a dictionary
def add_row(df, row_dict):
	row = pd.DataFrame(row_dict, index=[0])
	df = pd.concat([df, row]).reset_index(drop=True)
	return df

# Function to remove a row from a DataFrame
def remove_row(df, row_index):
	df = df.drop(row_index).reset_index(drop=True)
>>>>>>> a9d57df (scto_connector_new)
>>>>>>> 31b8063 (scto_connector_new)
