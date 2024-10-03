from io import StringIO
import streamlit as st
import pandas as pd
import datetime
import re


import pysurveycto

# --- SurveyCTO Server Connect Button Click Action ---#

def scto_server_connect(servername: str, username: str , password: str ) -> str:
	
	"""
	
	Validate SurveyCTO account details and load user data

	PARAMS
	------
	servername: SurveyCTO server name
	username: SurveyCTO account username (email address)
	password: SurveyCTO account password

	Return: SurveyCTO object

	"""
	# check that required field are supplied
	if not servername or not username or not password:
		st.warning("Complete all required fields.")
		st.stop()

	# check that servername is valid
	elif not re.fullmatch(r'\b[a-z]+[a-z0-9]+\b', servername):
		st.warning("Invalid server name.")
		st.stop()

	# check that user field is a valid email
	elif not re.fullmatch(r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b', username):
		st.warning("Invalid email address")
		st.stop()

	else:
		scto = pysurveycto.SurveyCTOObject(servername, username, password)
		st.write("Connection successful")
		return scto

# --- Load Login Information ---#
def scto_load_login() -> tuple:
	
	"""
	Load Login details from previous session

	PARAMS:
	-------
	servername: SurveyCTO server name

	return: tuple of servername and username
	"""
	
	# load server login details from last session
	try:
		file = pd.read_json(f'cache/pyDMS_server_cache.json')
		server_details = file.to_dict(orient='data')
		return (server_details['name'][0], server_details['user'][0])

	except FileNotFoundError:
		return ('', '')
	
# --- SurveyCTO load form details ---#

def scto_load_forms(servername: str) -> pd.DataFrame:
	
	"""
	Load saved form details from previous session

	PARAMS:
	-------
	servername: SurveyCTO server name

	return: pandas dataframe of form details
	"""
	
	# load form details from last session
	try:
		file = pd.read_json(f'cache/{servername}_pyDMS_forms_cache.json')
		form_inputs = file.to_dict(orient='data')
		return pd.DataFrame(form_inputs)

	except FileNotFoundError:
		return pd.DataFrame(
			[						
				{"alias":"", "server dataset":False, "get data":False, "get media":False, "form id": "", "encryption key":"", "save as":""},
				{"alias":"", "server dataset":False, "get data":False, "get media":False, "form id": "", "encryption key":"", "save as":""},
				{"alias":"", "server dataset":False, "get data":False, "get media":False, "form id": "", "encryption key":"", "save as":""},
			]
		)

# --- Import SurveyCTO --- #

# Using pysurveycto library, import survey data

def scto_import_data(scto, form_id, key = None, server_dataset = False, saveas = None) -> tuple:

	# download server databases
	if server_dataset:
		scto_data = scto.get_server_dataset(form_id)
		scto_data = pd.read_csv(StringIO(scto_data))

		# count the number of new data
		new_data_count = len(scto_data.index)
		
	else:

		# set the default value for oldest_completion_date & scto_data
		oldest_completion_date: datetime = datetime.datetime(2024, 1, 1, 13, 40, 40)
		scto_data: pd.DataFrame = pd.DataFrame()

		# key is not missing, import encryption key from key file
		if key:
			try:
				with open(key, 'r') as file:
					key: str = file.read()
			except FileNotFoundError:
				st.warning("Key file not found.")
				st.stop()
		else:
			key: str = None

		# if saves is not missing, check if file exist and load
		if saveas:
			try:
				scto_data = pd.DataFrame(pd.read_csv(saveas))
			except FileNotFoundError:
				pass
			except pd.errors.EmptyDataError:
				pass
			else:
				# convert the SubmissionDate field to datetime
				scto_data['SubmissionDate'] = pd.to_datetime(scto_data['SubmissionDate'])

				# get the latest date in the dataset
				oldest_completion_date: datetime = scto_data['SubmissionDate'].max()

		new_data: pd.DataFrame = scto.get_form_data(form_id = form_id, format = 'json', oldest_completion_date=oldest_completion_date, key = key)
		new_data: pd.DataFrame = pd.DataFrame(new_data)
		new_data_count = len(new_data.index)

		# if scto_data is not empty, append new_data to scto_data, else set scto_data to new_data
		if not scto_data.empty:
			scto_data = scto_data.append(new_data, ignore_index = True)

			# drop duplicates from the dataset on key column (key) and keep the first
			scto_data.drop_duplicates(subset = 'KEY', keep = 'first', inplace = True)

		else:
			scto_data = new_data

		# download form definition
		scto_form = scto.get_form_definition(form_id)

		questions = pd.DataFrame(scto_form['fieldsRowsAndColumns'][1:], 
						   		 columns = scto_form['fieldsRowsAndColumns'][0],)

		choices = pd.DataFrame(scto_form['choicesRowsAndColumns'][1:],
    							 columns = scto_form['choicesRowsAndColumns'][0],)

		# Mark all repeat fields in the XLS file
		
		fields:pd.DataFrame = questions[['type', 'name']]

		current_group: str = ''

		# Iterate through rows
		for i, row in fields.iterrows():
			if 'begin repeat' in row['type']:
				if current_group == '':
					current_group = row['name']
				else:
					current_group = '/'.join(row['name'])
					
				fields.at[i, 'group'] = current_group 
					
			elif 'end repeat' in row['type']:
				
				fields.at[i, 'group'] = current_group
				current_group = current_group.split("/")[1:]
				current_group = '/'.join(current_group)
			else: 
				fields.at[i, 'group'] = current_group

		# drop rows with that contain meta info eg, groups, begin repeat, end repeat
		fields = fields[fields['type'].str.contains('select_one') | \
				 		fields['type'].isin(['datetime', 'date', 'time', 'sensor_statistic', \
									 		 'interger', 'decimal'])]
		
		# convert default str datetime cols to datetime
		for col in ['CompletionDate', 'SubmissionDate', 'starttime', 'endtime']:
			if col in scto_data.columns:
				scto_data[col] = pd.to_datetime(scto_data[col])

		# convert default numeric variables to numeric
		scto_data['duration'] = pd.to_numeric(scto_data['duration'], errors = 'ignore')

		# loop through fields and convert numeric variables to appropriate data types
		for i, row in fields.iterrows():
			if row['type'] is ['date']:
				scto_data[row['name']] = datetime.datetime.strptime(scto_data[row['name']], '%Y-%m-%d')
			elif row['type'] in ['datetime', 'time']:
				scto_data[row['name']] = pd.to_datetime(scto_data[row['name']], errors = 'ignore')
			else:
				try:
					scto_data[row['name']] = pd.to_numeric(scto_data[row['name']], errors = 'ignore')
				except KeyError:
					pass
		
		# convert col with object type to str
		object_cols = scto_data.select_dtypes(include = ['object']).columns
		scto_data[object_cols] = scto_data[object_cols].astype(str)
					
	# save dataset
	if saveas:
		scto_data.to_csv(saveas, index = False)

	return (scto_data, new_data_count)