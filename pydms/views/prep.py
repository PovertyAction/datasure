import streamlit as st
import pandas as pd
import numpy as np

from pydms.data_processing import DP_ACTIONS, DP_FUNCS, DP_DEL_METHODS

#-- DATA PREP PAGE --#
# Creates page for data preprocessing

st.title("Prepare Data")
st.markdown("Make neccesary adjustments to data before check")

# Get list of dataset alias 
alias_list: list[str] = list(filter(None, st.session_state.alias_list))

# create new tab for each dataset
tabs = st.tabs(alias_list)

for i, (label, tab) in enumerate(zip(alias_list, tabs)):
	
	# save a copy of the raw dataset as the intial prepped dataset
	st.session_state[f'prepped_data{i}'] = st.session_state[f'raw_data{i}']
	
	# count rows, columns, number missing & percent missing
	row_count: int = len(st.session_state[f'prepped_data{i}'].index)
	col_count: int = len(st.session_state[f'prepped_data{i}'].columns)
	miss_count: int = st.session_state[f'prepped_data{i}'].isnull().sum().sum()
	miss_perc: float  = round((miss_count / (row_count * col_count)) * 100, 2)

	# collate all string columns in dataset
	string_cols = st.session_state[f'prepped_data{i}'].select_dtypes(include=['object']).columns
	
	# display tab features
	with tab:

		# create columns for change log (& actions) & data view
		log_col, data_view_col = st.columns((0.3, 0.7))
		
		# populate actions and change log
		with log_col:
			with st.container(border = True):
				st.subheader("Apply Changes:")
				st.write("---")

				# create a popver box to accept inputs for new prep actions
				with st.popover(':material/add: Add data prep step', 
								 use_container_width = True):
						st.markdown("*Add new data preparation steps*")
						
						# selectbox for action type
						dp_action = st.selectbox(label = "Select Action:", 
									 options = DP_ACTIONS, 
									 key = f'st_sb_dp_action{i}')

						# selectbox for transforming or adding columns functions
						if dp_action in ["transform column(s)", "add column"]:
							dp_prep_func = st.selectbox(label = "Function type:", 
									 options = DP_FUNCS, 
									 key = f'st_sb_dp_funcs{i}')

						# selectbox (multi) for deleting column functions
						if dp_action in ["delete column(s)"]:
							dp_prep_del_cols = st.multiselect(label = "Select columns", 
											   options = string_cols, 
											   key = f'st_sb_del_cols{i}')
							
							# apply button
							dp_prep_del_btn = st.button(label = "Apply", 
														key = f'st_sb_del_button{i}', 
														use_container_width = True)

						# selectbox (multi) for deleting rows functions
						if dp_action in ["delete rows(s)"]:
							dp_prep_del_rows = st.selectbox(label = "Select Method", 
											   options = DP_DEL_METHODS, 
											   key = f'st_sb_del_rows{i}')



				
		with data_view_col:

			with st.container(border = True):
				mc1, mc2, mc3 = st.columns((0.3, 0.3, 0.4))

				mc1.metric(label = "Rows", value = row_count)
				mc2.metric(label = "Columns", value = col_count)
				mc3.metric(label = "Missing Values", value = f'{miss_perc}%')

			st.dataframe(st.session_state[f'prepped_data{i}'])

		
	i += 1

