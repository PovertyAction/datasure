import base64
import logging
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import streamlit as st

from datasure.utils.config_utils import ConfigurationService


@st.cache_data
def _image_data_uri(path: str) -> str:
    """Return a base64 data URI for an image, cached so it is encoded once."""
    encoded = base64.b64encode(Path(path).read_bytes()).decode()
    return f"data:image/png;base64,{encoded}"


# Root logging config belongs to the application entry point, not to
# library modules. No-op if the root logger is already configured.
logging.basicConfig(level=logging.INFO)

# Get the directory where this module is located
_package_dir = Path(__file__).parent
_views_dir = _package_dir / "views"

# --- PAGE SETUP --- #

# Resolve assets (package first, then fallback to project root for dev)
_assets_dir = _package_dir / "assets"
if not _assets_dir.exists():
    _assets_dir = Path.cwd() / "assets"

# set_page_config must be the first Streamlit command and run only once.
# page_icon accepts what st.image accepts: SVG is supported as an inline
# string (not a .svg file path), so read the markup and pass it directly.
_favicon_file = _assets_dir / "datasure-icon.svg"
_favicon = _favicon_file.read_text() if _favicon_file.exists() else ":material/home:"
st.set_page_config(
    page_title="DataSure",
    page_icon=_favicon,
    layout="wide",
)

# initialize session states
if "st_project_id" not in st.session_state:
    st.session_state.st_project_id = ""

if "st_import_data_page" not in st.session_state:
    st.session_state.st_import_data_page = None

if "st_prep_data_page" not in st.session_state:
    st.session_state.st_prep_data_page = None

if "st_output_page1" not in st.session_state:
    st.session_state.st_output_page1 = None

if "st_config_checks_page" not in st.session_state:
    st.session_state.st_config_checks_page = None

if "st_output_pages" not in st.session_state:
    st.session_state.st_output_pages = []

if "st_corr_page" not in st.session_state:
    st.session_state.st_corr_page = None

if "st_replication_page" not in st.session_state:
    st.session_state.st_replication_page = None

# start page
start_page = st.Page(
    page=str(_views_dir / "start_view.py"),
    title="Start Here",
    icon=":material/home:",
    default=True,
)

st.session_state.st_start_page = start_page

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

st.session_state.st_prep_data_page = prep_data_page

# config data checks config page
config_checks_page = st.Page(
    page=str(_views_dir / "config_view.py"),
    title="Configure Checks",
    icon=":material/manufacturing:",
)

st.session_state.st_config_checks_page = config_checks_page

if not st.session_state.st_project_id:
    # --- NAVIGATION MENU WITH START PAGE ONLY #
    nav_menu = st.navigation(
        {
            "": [start_page],
        },
    )
else:
    # get list of current config page_names
    page_names = ConfigurationService(st.session_state.st_project_id).get_page_names()
    page_count = len(page_names)

    if page_count >= 1:
        st.session_state.st_output_pages = []
        for i in range(0, page_count):
            page_name = page_names[i]
            page_number = i + 1
            output_page = st.Page(
                page=str(_views_dir / f"output_view_{page_number}.py"),
                title=page_name,
                icon=f":material/counter_{page_number}:",
            )

            st.session_state.st_output_pages.append(output_page)

        corr_page = st.Page(
            page=str(_views_dir / "correction_view.py"),
            title="Correct Data",
            icon=":material/cleaning_services:",
        )

        replication_page = st.Page(
            page=str(_views_dir / "replication_view.py"),
            title="Export Replication Package",
            icon=":material/package_2:",
        )

        st.session_state.st_output_page1 = st.session_state.st_output_pages[
            0
        ]  # for demo
        st.session_state.st_corr_page = corr_page
        st.session_state.st_replication_page = replication_page

        # --- NAVIGATION MENU WITH CHECK OUTPUTS AND CORRECTION PAGES--- #
        nav_menu = st.navigation(
            {
                "": [start_page, import_data_page, prep_data_page, config_checks_page],
                "DQA Reports": st.session_state.st_output_pages,
                "---": [corr_page, replication_page],
            },
        )
    else:
        # --- NAVIGATION MENU WITHOUT CHECK OUTPUTS AND CORRECTION PAGES--- #
        nav_menu = st.navigation(
            {
                "": [start_page, import_data_page, prep_data_page, config_checks_page],
            },
        )


# --- GLOBAL ASSETS --- #

_logo_path = _assets_dir / "datasure-icon.svg"
if _logo_path.exists():
    st.logo(str(_logo_path))

# --- SIDEBAR FOOTER --- #
# Rendered before nav_menu.run() so it is never skipped when the active page
# calls st.stop() (which unwinds the whole run). It therefore sits under the
# nav menu and above any sidebar content the active page adds during its run
# (e.g. the demo Help section).

try:
    _app_version = version("DataSure")
except PackageNotFoundError:
    _app_version = "dev"

with st.sidebar:
    st.divider()
    _horizontal_logo = _assets_dir / "datasure-horizontal.svg"
    if _horizontal_logo.exists():
        st.image(str(_horizontal_logo), width="stretch")
    st.caption(
        f"Version {_app_version} | [Documentation](https://data.poverty-action.org/data-quality/datasure/)"
    )
    st.caption(
        "Released under the "
        "[MIT License](https://github.com/PovertyAction/datasure/blob/main/LICENSE) by"
    )
    _ipa_logo_path = _assets_dir / "IPA-primary-color-RGB.png"
    if _ipa_logo_path.exists():
        _ipa_logo_uri = _image_data_uri(str(_ipa_logo_path))
        st.markdown(
            f'<a href="https://www.poverty-action.org" target="_blank" rel="noopener noreferrer">'
            f'<img src="{_ipa_logo_uri}" alt="Innovations for Poverty Action (IPA) logo" style="width:60%;"></a>',
            unsafe_allow_html=True,
        )

    st.caption(
        ":material/bug_report: [Report an issue](https://github.com/PovertyAction/datasure/issues)"
    )

# --- RUN NAVIGATION --- #

nav_menu.run()
