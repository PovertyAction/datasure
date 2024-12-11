import streamlit as st
import pandas as pd
import os

from src.connectors import scto_login_form, scto_forms_edit, scto_download_action
from src.connectors import local_load_files,local_add_form, local_load_action
from src.connectors import script_add_form, script_load_action, script_load_files

# --- CONFIGURE PAGE --- #

st.set_page_config("Import Data", page_icon = ":sync:", layout = "wide")
st.title("Import Data")
st.markdown("Import data from multiple sources")

# --- CONFIGURE CONNECTOR TABS ---#

# create tabs for different data sources
tabs = ["SurveyCTO", "Microsoft Azure", "Local Storage", "Python Script"]
scto, azure, local, script = st.tabs(tabs)

# --- INITIALIZING GLOBAL SESSION STATES --- #


# --- SURVEYCTO CONNECTOR ---#

# initate alias list for SurveyCTO forms
if 'scto_alias_list' not in st.session_state:
	st.session_state.scto_alias_list = []

# show/hide SurveyCTO forms
if 'scto_show_forms' not in st.session_state:
	st.session_state.scto_show_forms = False
# enable/disable SurevyCTO download button
if 'scto_disable_download_btn' not in st.session_state:
	st.session_state.scto_disable_download_btn = True
# Show/hide preview page
if 'scto_show_preview' not in st.session_state:
	st.session_state.scto_show_preview = False
if 'scto_forms' not in st.session_state:
	st.session_state.scto_forms = pd.DataFrame()



with scto:
	
	# tab description
	st.title("Sync your SurveyCTO")
	st.markdown("Enter the details required for fetching your data from the SurveyCTO server")

	# server & form details
	with st.container(border = True):
		
		# define cols fr server and form id
		scto_server_col, scto_forms_col = st.columns((0.4,0.6))

		with scto_server_col:
			scto_form_inputs, scto_servername, scto_username = scto_login_form()
			st.session_state.scto_forms = scto_form_inputs

		with scto_forms_col:
			if st.session_state.scto_show_forms:

				# display forms and additional functions
				scto_forms_edit(scto_servername)	
				
	
	# --- DOWNLOAD DATA FROM SURVEYCTO --- #

	scto_download_btn_col, scto_download_prog_col, _ = st.columns((0.1, 0.3, 0.6))

	with st.container(border = True):

		# Get data
		with scto_download_btn_col:
			scto_download_btn = st.button("Download", 
								type="primary", 
								key = "scto_download_btn_key",
								use_container_width = True, 
								disabled = st.session_state.scto_disable_download_btn)
			
		# import data 
		with scto_download_prog_col:
			if scto_download_btn:
				scto_download_action(st.session_state.scto_forms)


	# --- PREVIEW SURVEYCTO DATA --- #
	if st.session_state.scto_show_preview:
		with st.container(border = True):
			st.subheader("Preview Downloaded Data")
			st.write('---')
			
			scto_prev_select_col, scto_prev_mc1, scto_prev_mc2, scto_prev_mc3, _ = \
				st.columns((0.2, 0.1, 0.1, 0.1, 0.5))
			
			st.session_state.scto_alias_list = st.session_state.scto_forms['alias'].tolist()

			st.session_state.alias_list_index[0] = len(st.session_state.scto_alias_list)

			with scto_prev_select_col:	
				scto_preview_data = st.selectbox("Select Dataset to preview:", options = st.session_state.scto_alias_list)
				
				if scto_preview_data is not None:
					scto_row_num = st.session_state.scto_alias_list.index(scto_preview_data)
			
					scto_row_count: int = len(st.session_state[f'scto_raw_data{scto_row_num}'].index)
					scto_col_count: int = len(st.session_state[f'scto_raw_data{scto_row_num}'].columns)
					scto_miss_count: int = st.session_state[f'scto_raw_data{scto_row_num}'].isnull().sum().sum()
					scto_miss_perc: float = round((scto_miss_count / (scto_row_count * scto_col_count)) * 100, 2)

					scto_prev_mc1.metric(label = "Rows", value = scto_row_count)
					scto_prev_mc2.metric(label = "Columns", value = scto_col_count)
					scto_prev_mc3.metric(label = "Missing Values", value = f'{scto_miss_perc}%')
		
			if scto_preview_data is not None:
				st.dataframe(st.session_state[f'scto_raw_data{scto_row_num}'])


# --- LOCAL STORAGE CONNECTOR ---#

# initiate data alias list for local data
if 'local_alias_list' not in st.session_state:
	st.session_state.local_alias_list = []

# show/hide local files
if 'local_show_files' not in st.session_state:
	st.session_state.local_show_files = False

# show/hide files page
if 'local_show_files' not in st.session_state:
	st.session_state.local_show_files = False
# show/hide preview page
if 'local_show_preview' not in st.session_state:
	st.session_state.local_show_preview = True
# enable/disable load data button
if 'local_disable_load' not in st.session_state:
	st.session_state.local_disable_load = False
if 'local_files' not in st.session_state:
	st.session_state.local_files = local_load_files()

with local:

	# tab description
	st.title("Sync data from Local Storage")
	st.markdown("Add multiple data files from your local storage")

	# define cols adding files and added files
	local_add_col, local_show_col = st.columns((0.4, 0.6))

	with local_add_col:
		
		local_files = local_add_form()

	with local_show_col:
		with st.container(border = True):
			
			if len(st.session_state.local_files.index) > 0:
				
				st.session_state.local_disable_load = False

				local_inputs_mod = st.data_editor(data = st.session_state.local_files, 
										 			use_container_width = True, 
													num_rows = "dynamic")

				# Save configuration File
				local_save_config = st.button("Save setting", type="secondary", 
								  							  key = "local_save_config_key")

				if local_save_config:

					# save form information
					local_config_filename = "cache/pyDMS_local_files_cache.json"
					local_inputs_mod.to_json(local_config_filename)

					st.session_state.local_files = local_inputs_mod

					st.success("Configuration saved successfully!")

	# --- LOAD DATA FROM LOCAL STORAGE --- #

	local_load_btn_col, local_load_prog_col, _ = st.columns((0.1, 0.3, 0.6))

	with local_load_btn_col:

		# Get data
		load_local_data = st.button("Load Data", 
									type = "primary", 
									key = "local_get_data_key",
									use_container_width = True, 
									disabled = st.session_state.local_disable_load)
		
	# import data
	if load_local_data:
		with local_load_prog_col:
			local_load_action(local_inputs_mod)

	# --- PREVIEW LOCAL DATA --- #

	if st.session_state.local_show_preview:

		with st.container(border = True):
			st.subheader("Preview Loaded Data")
			st.write('---')
			
			local_select_col, local_prev_mc1, local_prev_mc2, local_prev_mc3, _ = \
					st.columns((0.2, 0.1, 0.1, 0.1, 0.5))

			st.session_state.local_alias_list = local_inputs_mod['alias'].tolist()
			st.session_state.alias_list_index[2] = len(st.session_state.local_alias_list)

			with local_select_col:	
				local_preview_data = st.selectbox("Select Dataset to preview:", options = st.session_state.local_alias_list)
				local_row_num = st.session_state['local_alias_list'].index(local_preview_data)

			local_row_count: int = len(st.session_state[f'local_raw_data{local_row_num}'].index)
			local_col_count: int = len(st.session_state[f'local_raw_data{local_row_num}'].columns)
			local_miss_count: int = st.session_state[f'local_raw_data{local_row_num}'].isnull().sum().sum()
			local_miss_perc: float = round((local_miss_count / (local_row_count * local_col_count)) * 100, 2)

			local_prev_mc1.metric(label = "Rows", value = local_row_count)
			local_prev_mc2.metric(label = "Columns", value = local_col_count)
			local_prev_mc3.metric(label = "Missing Values", value = f'{local_miss_perc}%')
	
			st.dataframe(st.session_state[f'local_raw_data{local_row_num}']) 


# --- PYTHON SCRIPT CONNECTOR ---#

# initiate data alias list for script data
if 'script_alias_list' not in st.session_state:
	st.session_state.script_alias_list = []

# show/hide script files
if 'script_show_files' not in st.session_state:
	st.session_state.script_show_files = False
# show/hide preview page
if 'script_show_preview' not in st.session_state:
	st.session_state.script_show_preview = False
# enable/disable load data button
if 'script_disable_load' not in st.session_state:
	st.session_state.script_disable_load = True
if 'script_files' not in st.session_state:
	st.session_state.script_files = script_load_files()


with script:
	# tab description
	st.title("Import data using a python script")
	st.markdown("Connect other sources of data using a custom pyscript")

	# define cols adding files and added files
	script_add_col, script_show_col = st.columns((0.4, 0.6))

	with script_add_col:
		
		with st.container(border = True):
			script_add_form()

	with script_show_col:
		with st.container(border = True):
			
			if len(st.session_state.script_files.index) > 0:
				
				st.session_state.script_disable_load = False
				
				script_inputs_mod = st.data_editor(data = st.session_state.script_files, 
										 			use_container_width = True, 
													num_rows = "dynamic")

				# Save configuration File
				script_save_config = st.button("Save setting", type="secondary", 
								  							  key = "script_save_config_key")

				if script_save_config:

					# save form information
					script_config_filename = "cache/pyDMS_script_files_cache.json"
					script_inputs_mod.to_json(script_config_filename)

					st.session_state.script_files = script_inputs_mod

					st.success("Configuration saved successfully!")

	# --- LOAD DATA FROM SCRIPT --- #

	script_load_btn_col, script_load_prog_col, _ = st.columns((0.1, 0.3, 0.6))

	with script_load_btn_col:

		# Get data
		load_script_data = st.button("Load Data from Scripts", 
									type = "primary", 
									key = "script_get_data_key",
									use_container_width = True, 
									disabled = st.session_state.script_disable_load)
		
	# import data
	if load_script_data:
		with script_load_prog_col:
			script_load_action(st.session_state.script_files)

	# --- PREVIEW SCRIPT DATA --- #

	if st.session_state.script_show_preview:
		with st.container(border = True):
			st.subheader("Preview Downloaded Data")
			st.write('---')
			
			script_select_col, script_prev_mc1, script_prev_mc2, script_prev_mc3, _ = \
				st.columns((0.2, 0.1, 0.1, 0.1, 0.5))
			
			st.session_state.script_alias_list = st.session_state.script_files['alias'].tolist()
			st.session_state.alias_list_index[3] = len(st.session_state.script_alias_list)

			with script_select_col:	
				script_preview_data = st.selectbox("Select Dataset to preview:", options = st.session_state.script_alias_list)
				script_row_num = st.session_state['script_alias_list'].index(script_preview_data)
			
			script_row_count: int = len(st.session_state[f'script_raw_data{script_row_num}'].index)
			script_col_count: int = len(st.session_state[f'script_raw_data{script_row_num}'].columns)
			script_miss_count: int = st.session_state[f'script_raw_data{script_row_num}'].isnull().sum().sum()
			script_miss_perc: float = round((script_miss_count / (script_row_count * script_col_count)) * 100, 2)

			script_prev_mc1.metric(label = "Rows", value = script_row_count)
			script_prev_mc2.metric(label = "Columns", value = script_col_count)
			script_prev_mc3.metric(label = "Missing Values", value = f'{script_miss_perc}%')
		
			st.dataframe(st.session_state[f'script_raw_data{script_row_num + 1}'])


# --- Collate List of Data Aliases --- #

st.session_state.alias_list = st.session_state.scto_alias_list + \
							st.session_state.local_alias_list + \
							st.session_state.script_alias_list
