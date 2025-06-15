import streamlit as st

# --- PAGE SETUP --- #

# initialize session states
if "st_load_project" not in st.session_state:
    st.session_state.st_load_project = False

if "st_project_id" not in st.session_state:
    st.session_state.st_project_id = ""

if "show_checks_section" not in st.session_state:
    st.session_state.show_checks_section = False


# start page
start_page = st.Page(
    page="views/start_view.py",
    title="start here",
    icon=":material/home:",
    default=True,
)

# config data import page
import_data_page = st.Page(
    page="views/import_view.py",
    title="Import Data",
    icon=":material/sync:",
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


# --- NAVIGATION MENU --- #

nav_menu = st.navigation({"": [start_page]})
if st.session_state.st_load_project:
    nav_menu = st.navigation(
        {
            "": [start_page],
            "Import Data": [import_data_page],
        }
    )
if st.session_state.show_prep_section:
    nav_menu = st.navigation(
        {
            "": [start_page],
            "Import Data": [import_data_page],
            "Prepare Data": [prep_data_page],
            "Configure Checks": [config_checks_page],
        }
    )

# create a session state to hold all pages, update in config page
st.session_state.static_pages = {
    "": [start_page],
    "Import Data": [import_data_page],
    "Prepare Data": [prep_data_page],
    "Configure Checks": [config_checks_page],
}

if st.session_state.show_checks_section:
    nav_menu = st.navigation(st.session_state.all_pages)

# --- GLOBAL ASSETS --- #

st.logo("assets/IPA-primary-full-color-abbreviated.png")

# --- RUN NAVIGATION --- #

nav_menu.run()
