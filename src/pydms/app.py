from pathlib import Path

import streamlit as st

# --- PAGE SETUP --- #

# initialize session states
if "st_load_project" not in st.session_state:
    st.session_state.st_load_project = False

if "st_project_id" not in st.session_state:
    st.session_state.st_project_id = ""

if "show_prep_section" not in st.session_state:
    st.session_state.show_prep_section = False

if "show_checks_section" not in st.session_state:
    st.session_state.show_checks_section = False


# Get the directory where this module is located
_package_dir = Path(__file__).parent
_views_dir = _package_dir / "views"

# start page
start_page = st.Page(
    page=str(_views_dir / "start_view.py"),
    title="start here",
    icon=":material/home:",
    default=True,
)

# config data import page
import_data_page = st.Page(
    page=str(_views_dir / "import_view.py"),
    title="Import Data",
    icon=":material/sync:",
)

# config data prep page
prep_data_page = st.Page(
    page=str(_views_dir / "prep_view.py"),
    title="Prepare Data",
    icon=":material/rule_settings:",
)

# config data checks config page
config_checks_page = st.Page(
    page=str(_views_dir / "config_view.py"),
    title="Configure Checks",
    icon=":material/manufacturing:",
)


# --- NAVIGATION MENU --- #


nav_menu = st.navigation(
    {
        "": [start_page],
        "Import Data": [import_data_page],
        "Prepare Data": [prep_data_page],
    },
    position="hidden",
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

# Try to find assets in package first, then fallback to project root
_assets_dir = _package_dir / "assets"
if not _assets_dir.exists():
    # Fallback for development
    _assets_dir = Path.cwd() / "assets"

_logo_path = _assets_dir / "IPA-primary-full-color-abbreviated.png"
if _logo_path.exists():
    st.logo(str(_logo_path))

# --- RUN NAVIGATION --- #

nav_menu.run()
