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

def scto_import_data(scto, form_id, key = None, server_dataset = False, saveas = None) -> pd.DataFrame:

	# download server databases
	if server_dataset:
		scto_data = scto.get_server_dataset(form_id)
		scto_data = pd.read_csv(StringIO(scto_data))
		
	else:
		date_input = datetime.datetime(2024, 1, 1, 13, 40, 40)
		scto_data = scto.get_form_data(form_id = form_id, format = 'json', oldest_completion_date=date_input)
		scto_data = pd.DataFrame(scto_data)
	
	# save dataset
	if saveas:
		scto_data.to_csv(saveas, index = False)

	return scto_data