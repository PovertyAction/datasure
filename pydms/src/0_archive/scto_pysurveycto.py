<<<<<<< HEAD
<<<<<<< HEAD
from io import StringIO
import streamlit as st
import pandas as pd
=======
<<<<<<< HEAD
>>>>>>> 31b8063 (scto_connector_new)
=======
<<<<<<< HEAD
>>>>>>> ce1922b (format and lint pydms/src/0_archive)
import datetime
import time
import re
import os
from functools import lru_cache


import pysurveycto

# --- SurveyCTO Server Connect Button Click Action --- #

def scto_server_connect(servername: str, username: str , password: str ) -> str:
	
	"""
	
	Validate SurveyCTO account details and load user data

	PARAMS
	------
	servername: SurveyCTO server name
	username: SurveyCTO account username (email address)
	password: SurveyCTO account password

	RETURN:
	------- 
	SurveyCTO object

	"""
	# check that required fields are not empty
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

	# if all fields are valid, create SurveyCTO object
		# Future Improvements: After SurveyCTO API improvements, add try-except block to catch connection errors
	else:
		scto = pysurveycto.SurveyCTOObject(servername, username, password)
		st.write("Connection successful")
		return scto

# --- Load Login Information --- #
def scto_load_login() -> tuple:
	
	"""
	Load Login details from previous session

	PARAMS:
	-------
	servername: SurveyCTO server name

	RETURN:
	-------
	servername: SurveyCTO server name
	username: SurveyCTO account username (email address) 
	   
	Returned as tuple of servername and username. 
	Returns empty tuple if no previous session
	"""
	
	# load server login details from last session
	try:
		file = pd.read_json(f'cache/pyDMS_server_cache.json')
		server_details = file.to_dict()
		return (server_details['name'][0], server_details['user'][0])

	except FileNotFoundError:
		return ('', '')
	
# --- SurveyCTO load form details --- #

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
		form_inputs = file.to_dict()
		return pd.DataFrame(form_inputs)

	# if file not found, return empty dataframe
	except FileNotFoundError:
		return pd.DataFrame(
			[						
				{"alias":"", "server dataset":False, "get data":False, "get media":False, "form id": "", "encryption key":"", "save as":""},
				{"alias":"", "server dataset":False, "get data":False, "get media":False, "form id": "", "encryption key":"", "save as":""},
				{"alias":"", "server dataset":False, "get data":False, "get media":False, "form id": "", "encryption key":"", "save as":""},
			]
		)
	
# --- Import SurveyCTO KEY --- #

def scto_import_key(key_file: str) -> str:
	
	"""
	Import SurveyCTO key from file

	PARAMS:
	-------
	key_file: path to key file

	RETURN:
	-------
	key: SurveyCTO key
	"""

	# check if key file exist
	try:
		with open(key_file, 'r') as file:
			key = file.read()
			return key

	except FileNotFoundError:
		st.warning("Key file not found.")
		st.stop()

# --- Load existing SurveyCTO in storage --- #

def scto_load_existing_data(saveas: str) -> tuple:
	
	"""
	Load existing SurveyCTO data from storage

	PARAMS:
	-------
	saveas: path to saved data

	RETURN:
	-------
	scto_data: pandas dataframe of existing data
	oldest_completion_date: datetime of oldest completion date in the dataset

	Returns tuple of (scto_data, oldest_completion_date)
	Returns empty dataframe and datetime(2024, 1, 1, 13, 40, 40) if file not found or saveas not specified
	"""

	try:
		scto_data = pd.DataFrame(pd.read_csv(saveas))
	except FileNotFoundError:
		return (pd.DataFrame(), datetime.datetime(2024, 1, 1, 13, 40, 40))
	except pd.errors.EmptyDataError:
		return (pd.DataFrame(), datetime.datetime(2024, 1, 1, 13, 40, 40))
	else:
		# convert the SubmissionDate field to datetime
		scto_data['SubmissionDate'] = pd.to_datetime(scto_data['SubmissionDate'])

		# get the latest date in the dataset
		return (scto_data, scto_data['SubmissionDate'].max())
	
# --- Import SurveyCTO form definition --- #

def scto_get_xls(scto: object, form_id: str) -> tuple:
	
	"""
	Import SurveyCTO form definition

	PARAMS:
	-------
	scto: SurveyCTO object
	form_id: SurveyCTO form ID

	RETURN:
	-------
	questions: pandas dataframe of questions
	choices: pandas dataframe of choices

	Returns tuple of (questions, choices)
	"""

	# download form definition
	scto_form = scto.get_form_definition(form_id)

	questions = pd.DataFrame(scto_form['fieldsRowsAndColumns'][1:], 
						   		 columns = scto_form['fieldsRowsAndColumns'][0],)

	choices = pd.DataFrame(scto_form['choicesRowsAndColumns'][1:],
								 columns = scto_form['choicesRowsAndColumns'][0],)

	return (questions, choices)

# --- Get List of Repeat Fields in SurveyCTO Form --- #
def scto_get_repeat_fields(questions: pd.DataFrame) -> list:

	"""
	Get list of repeat fields in SurveyCTO form

	PARAMS:
	-------
	questions: pandas dataframe of questions

	RETURN:
	-------
	list of repeat fields
	"""

	fields: pd.DataFrame = questions[['type', 'name']]

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
			questions.at[i, 'group'] = current_group
		
		repeat_fields = questions[questions['group'].notna()]['name'].tolist()

	# Return list of repeat fields as a list
	return repeat_fields

# --- Get repeat columns from repeat fields --- #

def scto_get_repeat_cols(field: str, repeat_fields: list) -> list:

	"""
	Get repeat columns from repeat fields

	PARAMS:
	-------
	field: field name
	repeat_fields: list of repeat fields

	RETURN:
	-------
	list of repeat columns
	"""

	regex = r'\b' + field + r'_[0-9]+[_]{,1}.*\b'
	cols = [x for x in repeat_fields if re.fullmatch(regex, x)]
		
	cols = cols or field.split()
	return cols

# --- Download SurveyCTO Media Files --- #

def scto_download_media(scto: object, media_fields: list, repeat_fields: list, new_data: pd.DataFrame, media_folder: str, key: str = None) -> None:

	# loop through media fields and download media files
	for field in media_fields:
		# get repeat group columns
		cols = scto_get_repeat_cols(field, repeat_fields)

		# get media files
		for col in cols:

			media_data = new_data[new_data[col].notna()]
			media_data = media_data[[col, 'KEY']].reset_index()
			media_count = len(media_data.index)	
			
			if media_count > 0:
					media_progress_bar = st.progress(0, text = f'Downloading media files for {col} ...')
				
					for j in range(0, len(media_data.index)):

						# get url at index j or row['name']

						url = media_data[col][j]
						submission_key = media_data['KEY'][j].replace("uuid:", "")
						fileext = url.split('.')[-1] or "csv"
						filename = col + '_' + submission_key + '.' + fileext
						media_file = scto.get_attachment(url, key = key)
						
						# save media files
						with open(f'{media_folder}/{filename}', 'wb') as file:
							file.write(media_file)
						progress = round(((j + 1)/media_count) * 100, 2)
						media_progress_bar.progress((j + 1)/media_count, \
								  text = f'Downloading media files for {col} ... % complete')
	

# Using pysurveycto library, import survey data from SurveyCTO
def scto_import_data(scto: object, form_id: str, key: str = None, server_dataset: bool = False, saveas: str = None, media: bool = False) -> tuple:

	"""
	- Import SurveyCTO Data and save to file
	- Adjust data types based on XLS form definition
	- Also import media files

	PARAMS:
	-------	
	scto: SurveyCTO object
	form_id: SurveyCTO form ID
	key: SurveyCTO encryption key
	server_dataset: boolean, True if using server dataset
	saveas: string, path to save dataset
	media: boolean, True if downloading media files

	RETURN:
	-------
	scto_data: pandas dataframe of imported data
	new_data_count: number of new data imported

	Returns tuple of (scto_data, new_data_count)
	"""

	
	# download server databases
	if server_dataset:
		scto_data = scto.get_server_dataset(form_id)
		scto_data = pd.read_csv(StringIO(scto_data))

		# count the number of new data
		new_data_count = len(scto_data.index)
		
	else:

		# key is not missing, import encryption key from key file
		if key:
			key = scto_import_key(key)

		# if saves is not missing, check if file exist and load
		scto_data, oldest_completion_date = scto_load_existing_data(saveas)

		# Download new data (from the oldest completion date)
		new_data: pd.DataFrame = scto.get_form_data(form_id = form_id, format = 'json', oldest_completion_date=oldest_completion_date, key = key)
		new_data: pd.DataFrame = pd.DataFrame(new_data)
		new_data_count = len(new_data.index)

		# if scto_data is not empty, append new_data to scto_data, else set scto_data to new_data
		if not scto_data.empty:
			scto_data = pd.concat([scto_data, new_data], ignore_index = True)

			# drop duplicates from the dataset on key column (key) and keep the first
			scto_data.drop_duplicates(subset = 'KEY', keep = 'first', inplace = True)

		else:
			scto_data = new_data

		# download form definition
		questions, _ = scto_get_xls(scto, form_id)

		# Mark all repeat fields in the XLS file
		
		repeat_fields = scto_get_repeat_fields(questions)
	
		# convert default str datetime cols to datetime
		for col in ['CompletionDate', 'SubmissionDate', 'starttime', 'endtime']:
			if col in scto_data.columns:
				scto_data[col] = pd.to_datetime(scto_data[col])

		# convert default numeric variables to numeric
		for col in ['duration', 'formdef_version']:
			if col in scto_data.columns:
				scto_data[col] = pd.to_numeric(scto_data[col], errors = 'ignore')

		# loop through fields and convert numeric variables to appropriate data types
		fields: pd.DataFrame = questions[['type', 'name']]
		scto_data_cols = list(scto_data.columns)
		for i, row in fields.iterrows():
			# check if field is a repeat group col, if yes, get all repeat columns
			cols = scto_get_repeat_cols(row['name'], repeat_fields)
			
			if row['type'] in ['date']:
				scto_data[cols] = scto_data[cols].astype('datetime64[ns]')
			elif row['type'] in ['datetime', 'time']:
				scto_data[cols] = pd.to_datetime(scto_data[cols])
			elif row['type'] in ['integer', 'decimal']:
				scto_data[cols] = pd.to_numeric(scto_data[cols])
			elif row['type'] in ['note']:
				if cols in scto_data_cols:
					# remove note fields from dataset
					scto_data.drop(columns = cols, axis = 1, inplace = True)
			else:
				# for all other types, ignore
				pass
	
		# -- download media files --# 

		# get a list of media fields form fields
		if media:
			media_fields = fields[fields['type'].isin(['image', 'audio', 'video', 
											 		  'file', 
													  'comments', 'text audit', 'audio audit', 'sensor stream'])]['name'].tolist()


			# use default saveas folder as media folder, removing filename
			media_folder = saveas.split('/')
			media_folder = '/'.join(media_folder[:-1]) + '/media'

			# check if director exist, create if not
			if not os.path.exists(media_folder):
				os.makedirs(media_folder)

			# download media files
			scto_download_media(scto, media_fields, repeat_fields, new_data, media_folder, key)

		

	# save dataset
	if saveas:
		scto_data.to_csv(saveas, index = False)

	return (scto_data, new_data_count)

# Configure SurveyCTO form
def scto_login_form() -> pd.DataFrame:
	
	"""
	Creats input form for SurveyCTO login

	PARAMS:
	------

	None

	RETURNS:
	-------

	pd.DataFrame - Dataframe of forms from previous session or empty dataset

	"""
	# define server details input
	with st.form(key="server_form"):
		st.image("asserts/SurveyCTO-Logo-CMYK.png", width = 200)
		st.markdown("*Server Details:*")

		name_default, user_default = scto_load_login()

		scto_server_name = st.text_input(label = "Server name*", 
									value = name_default, 
									help = "Enter SurveyCTO server name. eg. girlpower")
		scto_server_user = st.text_input(label = "Email address*", 
									value = user_default, 
									help = "Enter valid email username")
		scto_server_password = st.text_input(label = "Password*", 
										type = "password")

		# mark required fields
		st.markdown("**required*")

		# create submit button
		submit_button = st.form_submit_button(label="Connect to server")

		if submit_button:

			# modify session state
			st.session_state.scto = scto_server_connect(scto_server_name, 
											   			scto_server_user, 
														scto_server_password)
			st.session_state.scto_show_forms = True
			st.session_state.scto_disable_download_btn = False

		scto_forms = scto_load_forms(scto_server_name)

		return scto_forms, scto_server_name, scto_server_user
	

# --- SCTO Download button action --- #
def scto_download_action(form_inputs: pd.DataFrame) -> None:
<<<<<<< HEAD
=======
    """Trigger Action to download SurveyCTO data based on form inputs.

    PARAMS:
    -------
    form_inputs: pandas dataframe of form inputs

    Return:
    ------
    None

    """
    # remove empty rows
    form_inputs = form_inputs[form_inputs["get data"] == True]  # noqa: E712

    # Check data and flag errors
    if form_inputs.empty:
        st.warning("No data selected for download. Please select data to download")
        st.stop()

    form_count = len(form_inputs.index)

    progress_bar = st.progress(0, text="Downloading from SurveyCTO ...")

    st.write(f"Downloading {form_count} datasets from SurveyCTO")

    # download data
    for i in range(0, form_count):
        if f"scto_raw_data{i}" in st.session_state:
            form_id = form_inputs["form id"][i]
            key = form_inputs["encryption key"][i]
            server_dataset = form_inputs["server dataset"][i]
            saveas = form_inputs["save as"][i]
            media = form_inputs["get media"][i]

            st.session_state[f"scto_raw_data{i}"], new_data_count = scto_import_data(
                scto=st.session_state.scto,
                form_id=form_id,
                key=key,
                server_dataset=server_dataset,
                saveas=saveas,
                media=media,
            )
            time.sleep(3)
            progress_bar.progress(
                (i + 1) / form_count,
                text=f"Download in progress...{i + 1}/{form_count}",
            )

            if saveas is not None:
                st.write(
                    f"{i + 1}/{form_count}: downloaded {new_data_count} new data successfully and saved as {saveas}"
                )
            else:
                st.write(f"{i + 1}/{form_count}: downloaded successfully")

    st.success("Data download complete")

    # modify session state for preview
    st.session_state.scto_show_preview = True
=======
from io import StringIO
import streamlit as st
import pandas as pd
=======
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)
import datetime
import os
import re
import time
from io import StringIO

import pandas as pd
import pysurveycto
import streamlit as st

# --- SurveyCTO Server Connect Button Click Action --- #


def scto_server_connect(servername: str, username: str, password: str) -> str:
    """Validate SurveyCTO account details and load user data.

    PARAMS
    ------
    servername: SurveyCTO server name
    username: SurveyCTO account username (email address)
    password: SurveyCTO account password

    Return:
    ------
    SurveyCTO object

    """
    # check that required fields are not empty
    if not servername or not username or not password:
        st.warning("Complete all required fields.")
        st.stop()

    # check that servername is valid
    elif not re.fullmatch(r"\b[a-z]+[a-z0-9]+\b", servername):
        st.warning("Invalid server name.")
        st.stop()

    # check that user field is a valid email
    elif not re.fullmatch(
        r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,7}\b", username
    ):
        st.warning("Invalid email address")
        st.stop()

    # if all fields are valid, create SurveyCTO object
    # Future Improvements: After SurveyCTO API improvements, add try-except block to catch connection errors
    else:
        scto = pysurveycto.SurveyCTOObject(servername, username, password)
        st.write("Connection successful")
        return scto


# --- Load Login Information --- #
def scto_load_login() -> tuple:
    """Load Login details from previous session.

    PARAMS:
    -------
    servername: SurveyCTO server name

    Return:
    ------
    servername: SurveyCTO server name
    username: SurveyCTO account username (email address)

    Returned as tuple of servername and username.
    Returns empty tuple if no previous session

    """
    # load server login details from last session
    try:
        file = pd.read_json("cache/pyDMS_server_cache.json")
        server_details = file.to_dict()
        return (server_details["name"][0], server_details["user"][0])

    except FileNotFoundError:
        return ("", "")


# --- SurveyCTO load form details --- #


def scto_load_forms(servername: str) -> pd.DataFrame:
    """Load saved form details from previous session.

    PARAMS:
    -------
    servername: SurveyCTO server name

    return: pandas dataframe of form details
    """
    # load form details from last session
    try:
        file = pd.read_json(f"cache/{servername}_pyDMS_forms_cache.json")
        form_inputs = file.to_dict()
        return pd.DataFrame(form_inputs)

    # if file not found, return empty dataframe
    except FileNotFoundError:
        return pd.DataFrame(
            [
                {
                    "alias": "",
                    "server dataset": False,
                    "get data": False,
                    "get media": False,
                    "form id": "",
                    "encryption key": "",
                    "save as": "",
                },
                {
                    "alias": "",
                    "server dataset": False,
                    "get data": False,
                    "get media": False,
                    "form id": "",
                    "encryption key": "",
                    "save as": "",
                },
                {
                    "alias": "",
                    "server dataset": False,
                    "get data": False,
                    "get media": False,
                    "form id": "",
                    "encryption key": "",
                    "save as": "",
                },
            ]
        )


# --- Import SurveyCTO KEY --- #


def scto_import_key(key_file: str) -> str:
    """Import SurveyCTO key from file.

    PARAMS:
    -------
    key_file: path to key file

    Return:
    ------
    key: SurveyCTO key

    """
    # check if key file exist
    try:
        with open(key_file) as file:
            key = file.read()
            return key

    except FileNotFoundError:
        st.warning("Key file not found.")
        st.stop()


# --- Load existing SurveyCTO in storage --- #


def scto_load_existing_data(saveas: str) -> tuple:
    """Load existing SurveyCTO data from storage.

    PARAMS:
    -------
    saveas: path to saved data

    Return:
    ------
    scto_data: pandas dataframe of existing data
    oldest_completion_date: datetime of oldest completion date in the dataset

    Returns tuple of (scto_data, oldest_completion_date)
    Returns empty dataframe and datetime(2024, 1, 1, 13, 40, 40) if file not found or saveas not specified

    """
    try:
        scto_data = pd.DataFrame(pd.read_csv(saveas))
    except FileNotFoundError:
        return (pd.DataFrame(), datetime.datetime(2024, 1, 1, 13, 40, 40))
    except pd.errors.EmptyDataError:
        return (pd.DataFrame(), datetime.datetime(2024, 1, 1, 13, 40, 40))
    else:
        # convert the SubmissionDate field to datetime
        scto_data["SubmissionDate"] = pd.to_datetime(scto_data["SubmissionDate"])

        # get the latest date in the dataset
        return (scto_data, scto_data["SubmissionDate"].max())


# --- Import SurveyCTO form definition --- #


def scto_get_xls(scto: object, form_id: str) -> tuple:
    """Import SurveyCTO form definition.

    PARAMS:
    -------
    scto: SurveyCTO object
    form_id: SurveyCTO form ID

    Return:
    ------
    questions: pandas dataframe of questions
    choices: pandas dataframe of choices

    Returns tuple of (questions, choices)

    """
    # download form definition
    scto_form = scto.get_form_definition(form_id)

    questions = pd.DataFrame(
        scto_form["fieldsRowsAndColumns"][1:],
        columns=scto_form["fieldsRowsAndColumns"][0],
    )

    choices = pd.DataFrame(
        scto_form["choicesRowsAndColumns"][1:],
        columns=scto_form["choicesRowsAndColumns"][0],
    )

    return (questions, choices)


# --- Get List of Repeat Fields in SurveyCTO Form --- #
def scto_get_repeat_fields(questions: pd.DataFrame) -> list:
    """Get list of repeat fields in SurveyCTO form.

    PARAMS:
    -------
    questions: pandas dataframe of questions

    Return:
    ------
    list of repeat fields

    """
    fields: pd.DataFrame = questions[["type", "name"]]

    current_group: str = ""

    # Iterate through rows
    for i, row in fields.iterrows():
        if "begin repeat" in row["type"]:
            if current_group == "":
                current_group = row["name"]
            else:
                current_group = "/".join(row["name"])

            fields.at[i, "group"] = current_group

        elif "end repeat" in row["type"]:
            fields.at[i, "group"] = current_group
            current_group = current_group.split("/")[1:]
            current_group = "/".join(current_group)
        else:
            questions.at[i, "group"] = current_group

        repeat_fields = questions[questions["group"].notna()]["name"].tolist()

    # Return list of repeat fields as a list
    return repeat_fields


# --- Get repeat columns from repeat fields --- #


def scto_get_repeat_cols(field: str, repeat_fields: list) -> list:
    """Get repeat columns from repeat fields.

    PARAMS:
    -------
    field: field name
    repeat_fields: list of repeat fields

    Return:
    ------
    list of repeat columns

    """
    regex = r"\b" + field + r"_[0-9]+[_]{,1}.*\b"
    cols = [x for x in repeat_fields if re.fullmatch(regex, x)]

    cols = cols or field.split()
    return cols


# --- Download SurveyCTO Media Files --- #


def scto_download_media(
    scto: object,
    media_fields: list,
    repeat_fields: list,
    new_data: pd.DataFrame,
    media_folder: str,
    key: str = None,
) -> None:
    """Download media files from SurveyCTO.

    PARAMS:
    -------
    scto: SurveyCTO object
    media_fields: list of media fields
    repeat_fields: list of repeat fields
    new_data: pandas dataframe of new data
    media_folder: path to save media files
    key: SurveyCTO encryption key (optional)

    Return:
    ------
    None

    """
    # loop through media fields and download media files
    for field in media_fields:
        # get repeat group columns
        cols = scto_get_repeat_cols(field, repeat_fields)

        # get media files
        for col in cols:
            media_data = new_data[new_data[col].notna()]
            media_data = media_data[[col, "KEY"]].reset_index()
            media_count = len(media_data.index)

            if media_count > 0:
                media_progress_bar = st.progress(
                    0, text=f"Downloading media files for {col} ..."
                )

                for j in range(0, len(media_data.index)):
                    # get url at index j or row['name']

                    url = media_data[col][j]
                    submission_key = media_data["KEY"][j].replace("uuid:", "")
                    fileext = url.split(".")[-1] or "csv"
                    filename = col + "_" + submission_key + "." + fileext
                    media_file = scto.get_attachment(url, key=key)

                    # save media files
                    with open(f"{media_folder}/{filename}", "wb") as file:
                        file.write(media_file)
                    progress = round(((j + 1) / media_count) * 100, 2)  # noqa: F841
                    media_progress_bar.progress(
                        (j + 1) / media_count,
                        text=f"Downloading media files for {col} ... % complete",
                    )


# Using pysurveycto library, import survey data from SurveyCTO
def scto_import_data(
    scto: object,
    form_id: str,
    key: str = None,
    server_dataset: bool = False,
    saveas: str = None,
    media: bool = False,
) -> tuple:
    """Import SurveyCTO data.

    Import SurveyCTO Data and save to file, adjust data types based on XLS form definition, and import media files.


    PARAMS:
    -------
    scto: SurveyCTO object
    form_id: SurveyCTO form ID
    key: SurveyCTO encryption key
    server_dataset: boolean, True if using server dataset
    saveas: string, path to save dataset
    media: boolean, True if downloading media files

    Return:
    ------
    scto_data: pandas dataframe of imported data
    new_data_count: number of new data imported

    Returns tuple of (scto_data, new_data_count)

    """
    # download server databases
    if server_dataset:
        scto_data = scto.get_server_dataset(form_id)
        scto_data = pd.read_csv(StringIO(scto_data))

        # count the number of new data
        new_data_count = len(scto_data.index)

    else:
        # key is not missing, import encryption key from key file
        if key:
            key = scto_import_key(key)

        # if saves is not missing, check if file exist and load
        scto_data, oldest_completion_date = scto_load_existing_data(saveas)

        # Download new data (from the oldest completion date)
        new_data: pd.DataFrame = scto.get_form_data(
            form_id=form_id,
            format="json",
            oldest_completion_date=oldest_completion_date,
            key=key,
        )
        new_data: pd.DataFrame = pd.DataFrame(new_data)
        new_data_count = len(new_data.index)

        # if scto_data is not empty, append new_data to scto_data, else set scto_data to new_data
        if not scto_data.empty:
            scto_data = pd.concat([scto_data, new_data], ignore_index=True)

            # drop duplicates from the dataset on key column (key) and keep the first
            scto_data.drop_duplicates(subset="KEY", keep="first", inplace=True)

        else:
            scto_data = new_data

        # download form definition
        questions, _ = scto_get_xls(scto, form_id)

        # Mark all repeat fields in the XLS file

        repeat_fields = scto_get_repeat_fields(questions)

        # convert default str datetime cols to datetime
        for col in ["CompletionDate", "SubmissionDate", "starttime", "endtime"]:
            if col in scto_data.columns:
                scto_data[col] = pd.to_datetime(scto_data[col])

        # convert default numeric variables to numeric
        for col in ["duration", "formdef_version"]:
            if col in scto_data.columns:
                scto_data[col] = pd.to_numeric(scto_data[col], errors="ignore")

        # loop through fields and convert numeric variables to appropriate data types
        fields: pd.DataFrame = questions[["type", "name"]]
        scto_data_cols = list(scto_data.columns)
        for i, row in fields.iterrows():
            # check if field is a repeat group col, if yes, get all repeat columns
            cols = scto_get_repeat_cols(row["name"], repeat_fields)

            if row["type"] in ["date"]:
                scto_data[cols] = scto_data[cols].astype("datetime64[ns]")
            elif row["type"] in ["datetime", "time"]:
                scto_data[cols] = pd.to_datetime(scto_data[cols])
            elif row["type"] in ["integer", "decimal"]:
                scto_data[cols] = pd.to_numeric(scto_data[cols])
            elif row["type"] in ["note"]:
                if cols in scto_data_cols:
                    # remove note fields from dataset
                    scto_data.drop(columns=cols, axis=1, inplace=True)
            else:
                # for all other types, ignore
                pass

        # -- download media files --#

        # get a list of media fields form fields
        if media:
            media_fields = fields[
                fields["type"].isin(
                    [
                        "image",
                        "audio",
                        "video",
                        "file",
                        "comments",
                        "text audit",
                        "audio audit",
                        "sensor stream",
                    ]
                )
            ]["name"].tolist()

            # use default saveas folder as media folder, removing filename
            media_folder = saveas.split("/")
            media_folder = "/".join(media_folder[:-1]) + "/media"

            # check if director exist, create if not
            if not os.path.exists(media_folder):
                os.makedirs(media_folder)

            # download media files
            scto_download_media(
                scto, media_fields, repeat_fields, new_data, media_folder, key
            )

    # save dataset
    if saveas:
        scto_data.to_csv(saveas, index=False)

    return (scto_data, new_data_count)


# Configure SurveyCTO form
def scto_login_form() -> pd.DataFrame:
    """Create input form for SurveyCTO login.

    PARAMS:
    ------

    None

    Returns
    -------
    pd.DataFrame - Dataframe of forms from previous session or empty dataset

    """
    # define server details input
    with st.form(key="server_form"):
        st.image("asserts/SurveyCTO-Logo-CMYK.png", width=200)
        st.markdown("*Server Details:*")

        name_default, user_default = scto_load_login()

        scto_server_name = st.text_input(
            label="Server name*",
            value=name_default,
            help="Enter SurveyCTO server name. eg. girlpower",
        )
        scto_server_user = st.text_input(
            label="Email address*",
            value=user_default,
            help="Enter valid email username",
        )
        scto_server_password = st.text_input(label="Password*", type="password")

        # mark required fields
        st.markdown("**required*")

        # create submit button
        submit_button = st.form_submit_button(label="Connect to server")

        if submit_button:
            # modify session state
            st.session_state.scto = scto_server_connect(
                scto_server_name, scto_server_user, scto_server_password
            )
            st.session_state.scto_show_forms = True
            st.session_state.scto_disable_download_btn = False

        scto_forms = scto_load_forms(scto_server_name)

        return scto_forms, scto_server_name, scto_server_user


# --- SCTO Download button action --- #
def scto_download_action(form_inputs: pd.DataFrame) -> None:
<<<<<<< HEAD
>>>>>>> 31b8063 (scto_connector_new)
=======
<<<<<<< HEAD
>>>>>>> ce1922b (format and lint pydms/src/0_archive)

	"""
	Trigger Action to download SurveyCTO data based on form inputs

	PARAMS:
	-------
	form_inputs: pandas dataframe of form inputs

	RETURN:
	-------
	None
	
	"""
	
	# remove empty rows
	form_inputs = form_inputs[form_inputs['get data'] == True]

	# Check data and flag errors
	if form_inputs.empty:
		st.warning("No data selected for download. Please select data to download")
		st.stop()

	form_count = len(form_inputs.index)

	progress_bar = st.progress(0, text = "Downloading from SurveyCTO ...")

	st.write(f'Downloading {form_count} datasets from SurveyCTO')

	# download data
	for i in range(0, form_count):
		if f'scto_raw_data{i}' in st.session_state:
			
			form_id = form_inputs['form id'][i]
			key = form_inputs['encryption key'][i]
			server_dataset = form_inputs['server dataset'][i]
			saveas = form_inputs['save as'][i]
			media = form_inputs['get media'][i]

			st.session_state[f'scto_raw_data{i}'], new_data_count = scto_import_data(scto = st.session_state.scto, 
																form_id = form_id,
																key = key, 
																server_dataset = server_dataset, 
																saveas = saveas, 
																media = media)
			time.sleep(3)
			progress_bar.progress((i + 1)/form_count, text = f'Download in progress...{i + 1}/{form_count}')

			if saveas is not None:
				st.write(f'{i + 1}/{form_count}: downloaded {new_data_count} new data successfully and saved as {saveas}')
			else:
				st.write(f'{i + 1}/{form_count}: downloaded successfully')

	st.success("Data download complete")

	# modify session state for preview
<<<<<<< HEAD
	st.session_state.scto_show_preview = True
=======
	st.session_state.scto_show_preview = True
>>>>>>> a9d57df (scto_connector_new)
<<<<<<< HEAD
>>>>>>> 31b8063 (scto_connector_new)
=======
=======
    """Trigger Action to download SurveyCTO data based on form inputs.

    PARAMS:
    -------
    form_inputs: pandas dataframe of form inputs

    Return:
    ------
    None

    """
    # remove empty rows
    form_inputs = form_inputs[form_inputs["get data"] == True]  # noqa: E712

    # Check data and flag errors
    if form_inputs.empty:
        st.warning("No data selected for download. Please select data to download")
        st.stop()

    form_count = len(form_inputs.index)

    progress_bar = st.progress(0, text="Downloading from SurveyCTO ...")

    st.write(f"Downloading {form_count} datasets from SurveyCTO")

    # download data
    for i in range(0, form_count):
        if f"scto_raw_data{i}" in st.session_state:
            form_id = form_inputs["form id"][i]
            key = form_inputs["encryption key"][i]
            server_dataset = form_inputs["server dataset"][i]
            saveas = form_inputs["save as"][i]
            media = form_inputs["get media"][i]

            st.session_state[f"scto_raw_data{i}"], new_data_count = scto_import_data(
                scto=st.session_state.scto,
                form_id=form_id,
                key=key,
                server_dataset=server_dataset,
                saveas=saveas,
                media=media,
            )
            time.sleep(3)
            progress_bar.progress(
                (i + 1) / form_count,
                text=f"Download in progress...{i + 1}/{form_count}",
            )

            if saveas is not None:
                st.write(
                    f"{i + 1}/{form_count}: downloaded {new_data_count} new data successfully and saved as {saveas}"
                )
            else:
                st.write(f"{i + 1}/{form_count}: downloaded successfully")

    st.success("Data download complete")

    # modify session state for preview
    st.session_state.scto_show_preview = True
>>>>>>> 0a91510 (format and lint pydms/src/0_archive)
>>>>>>> ce1922b (format and lint pydms/src/0_archive)
