import pandas as pd

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
