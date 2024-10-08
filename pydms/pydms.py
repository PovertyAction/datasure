import streamlit as st

# --- PAGE SETUP --- #

# initialize session states
if 'prep_section' not in st.session_state:
    st.session_state.prep_section = False

if 'config_section' not in st.session_state:
    st.session_state.config_section = False

if 'checks_section' not in st.session_state:
    st.session_state.checks_section = False

# config data import page
import_data_page = st.Page(
    page = "views/import.py", 
    title = "Import Data", 
    icon = ":material/sync:", 
    default = True,
)

# config data prep page
prep_data_page = st.Page(
    page = "views/prep.py", 
    title = "Prepare Data", 
    icon = ":material/rule_settings:"
)

# config data checks config page
config_checks_page = st.Page(
    page = "views/config.py", 
    title = "Configure Checks", 
    icon = ":material/manufacturing:"
)

# config check output page
check_output_page = st.Page(
    page = "views/output.py", 
    title = "Data Quality Checks", 
    icon = ":material/frame_inspect:"
)

# --- NAVIGATION MENU --- #

# Dynamically load pages
if st.session_state.prep_section:
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

# --- GLOBAL ASSERTS --- #

st.logo("asserts/IPA-primary-full-color-abbreviated.png")

# --- RUN NAVIGATION --- #

nav_menu.run()