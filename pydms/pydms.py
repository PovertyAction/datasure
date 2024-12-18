import pandas as pd
import streamlit as st

# --- PAGE SETUP --- #

# initialize session states
if "show_prep_section" not in st.session_state:
    st.session_state.show_prep_section = True

if "show_config_section" not in st.session_state:
    st.session_state.show_config_section = False

if "show_checks_section" not in st.session_state:
    st.session_state.show_checks_section = False

for i in range(0, 10):
    if f"check_page_name_{i}" not in st.session_state:
        st.session_state[f"check_page_name_{i}"] = ""
    if f"show_checks_page_{i}" not in st.session_state:
        st.session_state[f"show_checks_page_{i}"] = False

# initiate session states for 10 datasets from SCTO
for i in range(0, 10):
    if f"scto_raw_data{i}" not in st.session_state:
        st.session_state[f"scto_raw_data{i}"] = pd.DataFrame()

# initiate session states for 10 datasets from local storage
for i in range(0, 10):
    if f"local_raw_data{i}" not in st.session_state:
        st.session_state[f"local_raw_data{i}"] = pd.DataFrame()

# initiate session states for 10 datasets from script
for i in range(0, 10):
    if f"script_raw_data{i}" not in st.session_state:
        st.session_state[f"script_raw_data{i}"] = pd.DataFrame()

# initiate session states for 10 output pages
for i in range(0, 10):
    if f"config_page_{i}" not in st.session_state:
        st.session_state[f"config_page_{i}"] = False

# collate data aliases
if "alias_list" not in st.session_state:
    st.session_state.alias_list = []
else:
    st.session_state.alias_list = list(filter(None, st.session_state.alias_list))

if "alias_list_index" not in st.session_state:
    st.session_state.alias_list_index = [0, 0, 0, 0]

# config data import page
import_data_page = st.Page(
    page="views/import_view.py",
    title="Import Data",
    icon=":material/sync:",
    default=True,
)

# config data prep page
prep_data_page = st.Page(
    page="views/prep_view.py", title="Prepare Data", icon=":material/rule_settings:"
)

# config data checks config page
config_checks_page = st.Page(
    page="views/config_view.py",
    title="Configure Checks",
    icon=":material/manufacturing:",
)

# config check output pages
check_output_page_1 = st.Page(
    page="views/output_view_1.py",
    title=f"{st.session_state.config_page_1}",
    icon=":material/frame_inspect:",
)

# --- NAVIGATION MENU --- #

# Dynamically load pages
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
