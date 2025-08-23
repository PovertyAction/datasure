from pathlib import Path

import streamlit as st

# --- PAGE SETUP --- #

# initialize session states
if "st_project_id" not in st.session_state:
    st.session_state.st_project_id = ""

if "st_import_data_page" not in st.session_state:
    st.session_state.st_import_data_page = None

# Get the directory where this module is located
_package_dir = Path(__file__).parent
_views_dir = _package_dir / "views"

# start page
start_page = st.Page(
    page=str(_views_dir / "start_view.py"),
    title="Start Here",
    icon=":material/home:",
    default=True,
)

# config data import page
import_data_page = st.Page(
    page=str(_views_dir / "import_view.py"),
    title="Import Data",
    icon=":material/sync:",
)

st.session_state.st_import_data_page = import_data_page

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

output_page_1 = st.Page(
    page=str(_views_dir / "output_view_1.py"),
    title="Report 1",
    icon=":material/counter_1:",
)

corr_page = st.Page(
    page=str(_views_dir / "correction_view.py"),
    title="Correct Data",
    icon=":material/cleaning_services:",
)


# --- NAVIGATION MENU --- #


nav_menu = st.navigation(
    {
        "": [start_page, import_data_page, prep_data_page, config_checks_page],
        "DQA Reports": [output_page_1],
        "---": [corr_page],
    },
)

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
