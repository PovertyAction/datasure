# show table for form_ids
	if st.session_state.show_forms:
		with forms_col:

			# If saved settings exist, load table with saved settings
			try:
				file = pd.read_json(config_filename)
				form_inputs = file.to_dict(orient='data')
		
			except FileNotFoundError:
				# create new blank table if no form data exist
				form_inputs = pd.DataFrame(
					[						
						{"alias":"", "server dataset":False, "get data":False, "get media":False, "form id": "", "encryption key":""},
						{"alias":"", "server dataset":False, "get data":False, "get media":False, "form id": "", "encryption key":""},
						{"alias":"", "server dataset":False, "get data":False, "get media":False, "form id": "", "encryption key":""}
					]
				)

			# get form inputs
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
				dict = {'name':[server_name], 'user':[server_user]}
				server_details = pd.DataFrame(data = dict)
				server_details.to_json("cache/_pyDMS_server_cache.json")

				# save form information
				config_filename = "cache/" + server_name + "_pyDMS_forms_cache.json"
				edited_form_inputs.to_json(config_filename)

# --- DOWNLOAD DATA FROM SURVEYCTO --- #

button_col, progress_col, empty_col = st.columns((0.1, 0.3, 0.6))

if st.session_state.show_download_button:
	with st.container(border = True):

		# Get data
		with button_col:
			get_data = st.button("Start download", type="primary", use_container_width = True)

		# Download Datasets
		if get_data:

			# remove empty rows
			edited_form_inputs = edited_form_inputs[edited_form_inputs['get data'] == True]

			# Check data and flag errors
			if edited_form_inputs['alias'].count() == 0:
				st.warning("No forms Input form details")
				st.stop()
			
			else:
				for row in range(0, edited_form_inputs['alias'].count() - 1):
					# check that form id is not missing
					if pd.isna(edited_form_inputs.iloc[row]['alias']):

						st.warning("Missing Form ID in at least one row")


			# show download progress
			with progress_col:
				progress_bar = st.progress(0, text = "Downloading from SurveyCTO ...")

			# Subset and rename columns to fit function syntax
			form_info = edited_form_inputs[['form id', 'encryption key', 'server dataset']]
			form_info = form_info.rename(columns = {'form id':'form_id', 
										'encryption key':'key', 
										'server dataset':'server_dataset'})

			download_count = edited_form_inputs['alias'].count()
			for row in range(0, download_count):
				data_label = edited_form_inputs.iloc[row]['alias']

				st.session_state[f'raw_data{row}'] = import_scto(scto = st.session_state.scto, **form_info.iloc[row].to_dict())

				progress_bar.progress((row + 1)/download_count, text = f'Download in progress...{row + 1}/{download_count}')
				time.sleep(3)
			
			st.session_state.show_preview = True
			st.session_state.prep_section = True

# --- PREVIEW DOWNLOADED DATA --- #

if st.session_state.show_preview:
	with st.container(border = True):
		st.subheader("Preview Downloaded Data")
		st.write('---')

		select_col, mc1, mc2, mc3, empty_col = st.columns((0.2, 0.1, 0.1, 0.1, 0.5))
		
		st.session_state.alias_list = edited_form_inputs['alias'].tolist()

		with select_col:	
			preview_data = st.selectbox("Select Dataset to preview:", options = st.session_state.alias_list)
			row_num = st.session_state['alias_list'].index(preview_data)
		
		row_count: int = len(st.session_state[f'raw_data{row_num}'].index)
		col_count: int = len(st.session_state[f'raw_data{row_num}'].columns)
		miss_count: int = st.session_state[f'raw_data{row_num}'].isnull().sum().sum()
		miss_perc: float = round((miss_count / (row_count * col_count)) * 100, 2)

		# mc1, mc2, mc3 = st.columns(3)
		mc1.metric(label = "Rows", value = row_count)
		mc2.metric(label = "Columns", value = col_count)
		mc3.metric(label = "Missing Values", value = f'{miss_perc}%')

		st.dataframe(st.session_state[f'raw_data{row_num}'])