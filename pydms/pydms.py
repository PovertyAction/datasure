<<<<<<< HEAD
=======
<<<<<<< HEAD
import pandas as pd
=======
>>>>>>> 801c54a (init commit)
>>>>>>> 15d81c3 (init commit)
import streamlit as st
import pandas as pd

# --- PAGE SETUP --- #

# initialize session states
<<<<<<< HEAD
if 'show_prep_section' not in st.session_state:
=======
<<<<<<< HEAD
if "show_prep_section" not in st.session_state:
>>>>>>> 15d81c3 (init commit)
    st.session_state.show_prep_section = True

if 'show_config_section' not in st.session_state:
    st.session_state.show_config_section = False

if 'show_checks_section' not in st.session_state:
    st.session_state.show_checks_section = False
	
for i in range(0, 10):
	if f'check_page_name_{i}' not in st.session_state:
		st.session_state[f'check_page_name_{i}'] = ''
	if f'show_checks_page_{i}' not in st.session_state:
		st.session_state[f'show_checks_page_{i}'] = False

# initiate session states for 10 datasets from SCTO
for i in range(0, 10):
	if f'scto_raw_data{i}' not in st.session_state:
		st.session_state[f'scto_raw_data{i}'] = pd.DataFrame()
          
# initiate session states for 10 datasets from local storage
for i in range(0, 10):
	if f'local_raw_data{i}' not in st.session_state:
		st.session_state[f'local_raw_data{i}'] = pd.DataFrame()
            
# initiate session states for 10 datasets from script
for i in range(0, 10):
	if f'script_raw_data{i}' not in st.session_state:
		st.session_state[f'script_raw_data{i}'] = pd.DataFrame()
		
# collate data aliases
if 'alias_list' not in st.session_state:
	st.session_state.alias_list = []
else:
    st.session_state.alias_list = list(filter(None, st.session_state.alias_list))
	
if 'alias_list_index' not in st.session_state:
	st.session_state.alias_list_index = [0, 0, 0, 0]
	
# config data import page
import_data_page = st.Page(
<<<<<<< HEAD
    page = "views/import_view.py", 
    title = "Import Data", 
    icon = ":material/sync:", 
    default = True,
=======
    page="views/import_view.py",
    title="Import Data",
    icon=":material/sync:",
    default=True,
=======
if 'prep_section' not in st.session_state:
    st.session_state.prep_section = False

if 'config_section' not in st.session_state:
    st.session_state.config_section = False

if 'checks_section' not in st.session_state:
    st.session_state.checks_section = False

# config data import page
import_data_page = st.Page(
    page = "views/01_import_data.py", 
    title = "Import Data", 
    icon = ":material/sync:", 
    default = True,
>>>>>>> 801c54a (init commit)
>>>>>>> 15d81c3 (init commit)
)

# config data prep page
prep_data_page = st.Page(
<<<<<<< HEAD
    page = "views/prep_view.py", 
    title = "Prepare Data", 
    icon = ":material/rule_settings:"
=======
<<<<<<< HEAD
    page="views/prep_view.py", title="Prepare Data", icon=":material/rule_settings:"
=======
    page = "views/02_prep_data.py", 
    title = "Prepare Data", 
    icon = ":material/rule_settings:"
>>>>>>> 801c54a (init commit)
>>>>>>> 15d81c3 (init commit)
)

# config data checks config page
config_checks_page = st.Page(
<<<<<<< HEAD
    page = "views/config_view.py", 
    title = "Configure Checks", 
    icon = ":material/manufacturing:"
=======
<<<<<<< HEAD
    page="views/config_view.py",
    title="Configure Checks",
    icon=":material/manufacturing:",
>>>>>>> 15d81c3 (init commit)
)

# config check output pages
check_output_page_1 = st.Page(
<<<<<<< HEAD
    page = "views/output_view_1.py", 
    title = f'{st.session_state.config_page_1}', 
    icon = ":material/frame_inspect:"
=======
    page="views/output_view_1.py",
    title=f"{st.session_state.config_page_1}",
    icon=":material/frame_inspect:",
=======
    page = "views/03_config_checks.py", 
    title = "Configure Checks", 
    icon = ":material/manufacturing:"
)

# config check output page
check_output_page = st.Page(
    page = "views/04_check_output.py", 
    title = "Data Quality Checks", 
    icon = ":material/frame_inspect:"
>>>>>>> 801c54a (init commit)
>>>>>>> 15d81c3 (init commit)
)

# --- NAVIGATION MENU --- #

# Dynamically load pages
<<<<<<< HEAD
if st.session_state.show_checks_page_1:
    nav_menu = st.navigation(
        {
            "Import Data": [import_data_page],
            "Prepare Data": [prep_data_page],
            "Configure Checks": [config_checks_page],
            f"{st.session_state.config_page_1}": [check_output_page_1],
        }
    )
elif st.session_state.show_prep_section:
=======
if st.session_state.prep_section:
>>>>>>> 801c54a (init commit)
    nav_menu = st.navigation(
        {
            "Import Data": [import_data_page],
            "Prepare Data": [prep_data_page],
            "Configure Checks": [config_checks_page],
        }
    )
else:
    nav_menu = st.navigation(
        {
            "Import Data": [import_data_page],
        }
    )

<<<<<<< HEAD
# --- GLOBAL ASSERTS --- #
=======
<<<<<<< HEAD
# --- GLOBAL ASSETS --- #
>>>>>>> 15d81c3 (init commit)

st.logo("asserts/IPA-primary-full-color-abbreviated.png")

# --- RUN NAVIGATION --- #

<<<<<<< HEAD
nav_menu.run()
=======
nav_menu.run()
=======
# --- GLOBAL ASSERTS --- #

st.logo("asserts/IPA-primary-full-color-abbreviated.png")

# --- RUN NAVIGATION --- #

nav_menu.run()
>>>>>>> 801c54a (init commit)
>>>>>>> 15d81c3 (init commit)
