import streamlit as st
import pandas as pd


st.title("Configure Checks")
st.markdown("Add a page for each dataset you want to check")

if 'config_tabs' not in st.session_state:
	st.session_state.config_pages = ''

alias_list = list(filter(None, st.session_state.alias_list))

add_page, check_pages = st.columns((0.35,0.65))

new_page_data = ''

survey_cols = ['enum_id', 'enum_name']

with add_page:
	with st.form(key = "new_tab"):
		st.markdown("*New Check Tab:*")

		new_page_name = st.text_input(label = "Page name*", 
			help = "Enter the name of the new check page. eg. Household Survey")
		
		new_page_data = st.selectbox("Dataset*:", options = alias_list)

		i = alias_list.index(new_page_data)
		survey_cols = st.session_state[f'prepped_data{i}'].columns
		
		if new_page_data != '':

			new_page_tracking_data = st.selectbox("Tracking Data:", options = alias_list)

			new_page_key = st.selectbox("Survey KEY*:", options = survey_cols)
			new_page_id = st.selectbox("Survey ID:", options = survey_cols)
			new_page_enum = st.selectbox("Enumerator ID:", options = survey_cols)
			new_page_date = st.selectbox("Date:", options = survey_cols)

		submit_button = st.form_submit_button(label="Create checks page")

# load existing pages

try:
	st.session_state.config_pages = pd.read_json('cache/pyDMS_config_tabs_cache.json')
except:
	st.session_state.config_pages = pd.DataFrame(columns = ['Page Name', 'Data', 'Tracking Data', 'KEY', 'ID', 'Enumerator', 'Date'])

if submit_button:
	
	if new_page_name == '':
		st.warning("Please enter a name for the new check page")
	elif new_page_data == '':
		st.warning("Please select a dataset for the new check page")

	new_page = pd.DataFrame(data = [[new_page_name, new_page_data, new_page_tracking_data, new_page_key, new_page_id, new_page_enum, new_page_date]], 
									columns = ['Page Name', 'Data', 'Tracking Data', 'KEY', 'ID', 'Enumerator', 'Date'])
	
	config_pages = pd.concat([st.session_state.config_pages, new_page], ignore_index = True)

	config_pages.to_json(f'cache/pyDMS_config_tabs_cache.json')


for i in range(len(st.session_state.config_pages)):
	st.session_state[f'config_page_{i}'] = st.session_state.config_pages['Page Name'][i]
	st.session_state[f'show_checks_page_{i}'] = True


