import streamlit as st
import pandas as pd
import datetime
import time

import pysurveycto

from pydms.data_import import scto_import_data, scto_server_connect, scto_load_login, scto_load_forms
from pydms.data_import import get_excel_sheet_names

# --- CONFIGURE PAGE ---#

st.set_page_config("Import Data", page_icon = ":sync:", layout = "wide")
st.title("Import Data")
st.markdown("Import data from multiple sources")


# initiate session state for data aliases
if 'alias_list' not in st.session_state:
	st.session_state['alias_list'] = []

# initiate session states for 10 datasets
for i in range(1, 11):
	if f'raw_data{i}' not in st.session_state:
		st.session_state[f'raw_data{i}'] = ''

# initiate session states for page triggers
if 'show_forms' not in st.session_state:
	st.session_state['show_forms'] = False
if 'disable_download_btn' not in st.session_state:
	st.session_state['disable_download_btn'] = True
if 'show_preview' not in st.session_state:
	st.session_state['show_preview'] = False
if 'show_prep_section' not in st.session_state:
	st.session_state['show_prep_section'] = False
	
# --- CONFIGURE CONNECTOR TABS ---#

scto, azure, local, pyscript = st.tabs(["SurveyCTO", 
									 "Microsoft Azure", 
									 "Local Storage", 
									 "Python Script"])

# --- SURVEYCTO CONNECTOR ---#

with scto:
	
	# tab description
	st.title("Sync your SurveyCTO")
	st.markdown("Enter the details required for fetching your data from the SurveyCTO server")

	# server & form details
	with st.container(border = True):
		
		# define cols fr server and form id
		server_col, forms_col = st.columns((0.4,0.6))

		with server_col:
			
			# define server details input
			with st.form(key="server_form"):
				st.image("asserts/SurveyCTO-Logo-CMYK.png", width = 200)
				st.markdown("*Server Details:*")

				name_default, user_default = scto_load_login()

				server_name = st.text_input(label = "Server name*", 
											value = name_default, 
											help = "Enter SurveyCTO server name. eg. girlpower")
				server_user = st.text_input(label = "Email address*", 
											value = user_default, 
											help = "Enter valid email username")
				server_password = st.text_input(label = "Password*", 
												type = "password")

				# mark required fields
				st.markdown("**required*")

				# create submit button
				submit_button = st.form_submit_button(label="Connect to server")

				# create submit action
				if submit_button:

					# modify session state
					st.session_state.scto = scto_server_connect(server_name, server_user, server_password)
					st.session_state.show_forms = True
					st.session_state.disable_download_btn = False

		with forms_col:
			if st.session_state.show_forms:
				# load form details
				form_inputs = scto_load_forms(server_name)

				edited_form_inputs = st.data_editor(form_inputs, 
													hide_index = True, 
													use_container_width = True, 
													num_rows = "dynamic")	
				
				# Save configuration File
				save_config = st.button("Save setting", type="secondary")

				# change type to pandas dataframe
				edited_form_inputs = pd.DataFrame(edited_form_inputs)	

				if save_config:

					# save login information
					server_details = pd.DataFrame(data = {'name':[server_name], 
										   				  'user':[server_user]})
					server_details.to_json("cache/pyDMS_server_cache.json")

					# save form information
					config_filename = "cache/" + server_name + "_pyDMS_forms_cache.json"
					edited_form_inputs.to_json(config_filename)

	# --- DOWNLOAD DATA FROM SURVEYCTO --- #

	btn_col, prog_col, empty_col = st.columns((0.1, 0.3, 0.6))

	with st.container(border = True):

		# Get data
		with btn_col:
			get_data = st.button("Download", 
						type="primary", 
						use_container_width = True, 
						disabled = st.session_state.disable_download_btn)
			
		# Download Datasets
		if get_data:

			# remove empty rows
			edited_form_inputs = edited_form_inputs[edited_form_inputs['get data'] == True]

			# Check data and flag errors
			if edited_form_inputs.empty:
				st.warning("No data selected for download. Please select data to download")
				st.stop()

			form_count = len(edited_form_inputs.index)

			with prog_col:
				progress_bar = st.progress(0, text = "Downloading from SurveyCTO ...")

			st.write(f'Downloading {form_count} datasets from SurveyCTO')

			# download data
			for i in range(1, form_count + 1):
				if f'raw_data{i}' in st.session_state:
					
					form_id = edited_form_inputs['form id'][i - 1]
					key = edited_form_inputs['encryption key'][i - 1]
					server_dataset = edited_form_inputs['server dataset'][i - 1]
					saveas = edited_form_inputs['save as'][i - 1]
					media = edited_form_inputs['get media'][i - 1]

					st.session_state[f'raw_data{i}'], new_data_count = scto_import_data(scto = st.session_state.scto, 
																		form_id = form_id,
																		key = key, 
																		server_dataset = server_dataset, 
																		saveas = saveas, 
																		media = media)
					time.sleep(3)
					progress_bar.progress(i/form_count, text = f'Download in progress...{i}/{form_count}')

					if saveas is not '':
						st.write(f'{i}/{form_count}: downloaded {new_data_count} new data successfully and saved as {saveas}')
					else:
						st.write(f'{i}/{form_count}: downloaded successfully')

			st.success("Data download complete")

			# modify session state for preview
			st.session_state.show_preview = True
			
if st.session_state.show_preview:
	with st.container(border = True):
		st.subheader("Preview Downloaded Data")
		st.write('---')
		
		select_col, mc1, mc2, mc3, empty_col = st.columns((0.2, 0.1, 0.1, 0.1, 0.5))
		
		st.session_state.alias_list = edited_form_inputs['alias'].tolist()

		with select_col:	
			preview_data = st.selectbox("Select Dataset to preview:", options = st.session_state.alias_list)
			row_num = st.session_state['alias_list'].index(preview_data)
		
		row_count: int = len(st.session_state[f'raw_data{row_num + 1}'].index)
		col_count: int = len(st.session_state[f'raw_data{row_num + 1}'].columns)
		miss_count: int = st.session_state[f'raw_data{row_num + 1}'].isnull().sum().sum()
		miss_perc: float = round((miss_count / (row_count * col_count)) * 100, 2)

		mc1, mc2, mc3 = st.columns(3)
		mc1.metric(label = "Rows", value = row_count)
		mc2.metric(label = "Columns", value = col_count)
		mc3.metric(label = "Missing Values", value = f'{miss_perc}%')
	
		st.dataframe(st.session_state[f'raw_data{row_num + 1}'])


# --- Microsoft Azure Connector ---#




# --- Local Disk Connector ---#

with local:
	# tab description
	st.title("Sync data from Local Storage")
	st.markdown("Add multiple data files from your local storage")

	# define cols adding files and added files
	add_file_col, show_file_col = st.columns((0.4, 0.6))

	with add_file_col:
		with st.container(border = True):
			st.image("asserts/storage.png", width = 100)
			
			
			st.markdown("Add a new file")
			# input for file type
			file_type = st.selectbox(label = "Select File Type", 
										options = ['csv', 'xlsx', 'json'], 
										key = 'file_type')
			
			# adjust for excel file types
			if file_type == 'xlsx':
				file_type = ['xlsx', 'xls']
		
			# file uploader. Limit to 1 file and allow only file types selected
			added_file = st.file_uploader(label = "Upload File", 
										type = file_type)

			if file_type == ['xlsx', 'xls']:
				if added_file:		
					sheets  = get_excel_sheet_names(added_file)
					sheet_name = st.selectbox(label = "Sheet Name", 
											options = sheets)
				
			

			

# --- Python Script Connector ---#