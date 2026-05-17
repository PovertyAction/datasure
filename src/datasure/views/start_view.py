import hashlib
import json
import shutil
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import streamlit as st

from datasure.utils.cache_utils import get_cache_path
from datasure.utils.config_utils import ConfigurationService
from datasure.utils.onboarding_utils import (
    DEMO_PROJECT_ID,
    create_demo_project,
    load_demo_data,
    set_onboarding_step,
    show_demo_intro,
)

PROJECTS_FILE: str = "projects.json"


def _validate_project_id(project_id: str) -> bool:
    """Validate project ID to prevent path traversal attacks."""
    # Project ID should only contain alphanumeric characters
    return project_id.isalnum() and len(project_id) == 8


def get_project_id(project_name: str) -> str:
    """Generate a unique project ID."""
    hash_val = hashlib.sha256(project_name.encode()).hexdigest()
    return hash_val[:8]  # Return the first 8 characters of the hash as the project ID


def get_project_names() -> list[str]:
    """Get a list of project names sorted by last used date (most recent first)."""
    projects_file = get_cache_path(PROJECTS_FILE)
    project_names: list[str] = []
    if projects_file.exists():
        with open(projects_file) as f:
            projects = json.load(f)
        sorted_projects = sorted(
            (p for p in projects.values() if not p.get("is_demo", False)),
            key=lambda p: p.get("last_used", ""),
            reverse=True,
        )
        project_names = [p["name"] for p in sorted_projects]
    return ["DataSure Demo"] + project_names + ["Create New Project"]


def _get_last_used_project_name() -> str | None:
    """Return the name of the most recently used non-demo project, or None."""
    projects_file = get_cache_path(PROJECTS_FILE)
    if not projects_file.exists():
        return None
    with open(projects_file) as f:
        projects = json.load(f)
    candidates = [
        p
        for p in projects.values()
        if not p.get("is_demo", False) and p.get("last_used")
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p["last_used"])["name"]


def valid_project_name(project_name: str) -> bool:
    """Validate the project name."""
    if not project_name:
        st.error("Project name cannot be empty.")
        return False
    if len(project_name) < 3:
        st.error("Project name must be at least 3 characters long.")
        return False
    if not all(c.isalnum() or c in "-_ " for c in project_name):
        st.error(
            "Project name can only contain alphanumeric characters, dash, underscore, and space."
        )
        return False
    return True


def load_projects() -> dict:
    """Load available projects from the local directory."""
    projects_file = get_cache_path(PROJECTS_FILE)
    if projects_file.exists():
        with open(projects_file) as f:
            projects = json.load(f)
        return projects
    return {}


def save_project(project_name: str, project_id: str):
    """Save a new project to the local directory."""
    if not _validate_project_id(project_id):
        raise ValueError(f"Invalid project ID: {project_id}")

    project_path = get_cache_path(project_id)

    project_info_path = project_path / "settings" / "project_info.json"
    if not project_path.exists():
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / "data").mkdir(exist_ok=True)
        (project_path / "settings").mkdir(exist_ok=True)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        last_used = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(project_info_path, "w") as f:
            json.dump({"created_at": created_at}, f, indent=4)
    else:
        if project_info_path.exists():
            with open(project_info_path) as f:
                project_info = json.load(f)
            created_at = project_info.get(
                "created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            )
        else:
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with open(project_info_path, "w") as f:
                json.dump({"created_at": created_at}, f, indent=4)
        last_used = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    projects = load_projects() or {}
    new_project = {
        "name": project_name,
        "created_at": created_at,
        "last_used": last_used,
    }
    projects[project_id] = new_project

    projects_file = get_cache_path(PROJECTS_FILE)
    with open(projects_file, "w") as f:
        json.dump(projects, f, indent=4)


def delete_project(project_id: str):
    """Delete a project from the local directory."""
    if not _validate_project_id(project_id):
        st.error(f"Invalid project ID: {project_id}")
        return

    projects = load_projects()
    if project_id in projects:
        projects.pop(project_id)
        projects_file = get_cache_path(PROJECTS_FILE)
        with open(projects_file, "w") as f:
            json.dump(projects, f, indent=4)

        project_path = get_cache_path(project_id)

        if project_path.exists():
            shutil.rmtree(project_path)
        st.success(f"Project '{project_id}' deleted successfully!")
    else:
        st.error(f"Project '{project_id}' does not exist.")


def _launch_fresh_demo():
    """Create a clean demo project and navigate to the import page."""
    demo_project_id = create_demo_project()
    st.session_state.st_project_id = demo_project_id
    set_onboarding_step(1)
    with st.spinner("Loading demo data..."):
        if load_demo_data():
            st.session_state.st_project_id = demo_project_id
            set_onboarding_step(2)
            st.switch_page(st.session_state.st_import_data_page)
        else:
            st.error("Failed to load demo data. Please try again.")


def _handle_demo_project():
    """Handle demo project selection and initialization."""
    show_demo_intro()

    demo_exists = DEMO_PROJECT_ID in load_projects()

    if demo_exists:
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Resume Demo", type="primary", width="stretch"):
                st.session_state.st_project_id = DEMO_PROJECT_ID
                ConfigurationService(DEMO_PROJECT_ID).sync_output_view_files()
                st.switch_page(st.session_state.st_import_data_page)
        with col2:
            if st.button("Restart Demo", type="secondary", width="stretch"):
                st.session_state["_demo_confirm_restart"] = True

        if st.session_state.get("_demo_confirm_restart"):
            st.warning(
                "**Restarting will permanently delete all your demo progress**, "
                "including any corrections and data preparation steps you have made. "
                "This cannot be undone.",
                icon=":material/warning:",
            )
            if st.button("Confirm Restart", type="primary"):
                st.session_state.pop("_demo_confirm_restart", None)
                _launch_fresh_demo()
    else:
        if st.button("Start Demo", type="primary", width="stretch"):
            _launch_fresh_demo()


def _handle_create_new_project():
    """Handle new project creation workflow."""
    project_name = st.text_input("Enter Project Name", placeholder="My New Project")
    if st.button(
        "Create Project", type="primary", disabled=not project_name
    ) and valid_project_name(project_name):
        project_id = get_project_id(project_name)
        existing_projects = load_projects()
        if existing_projects and project_id in existing_projects:
            st.error(
                f"Project '{project_name}' already exists. Please choose a different name."
            )
            st.stop()
        save_project(project_name, project_id)
        st.success(f"Project '{project_name}' created successfully!")
        st.rerun()


def _handle_existing_project_selection(project: str):
    """Handle selection of an existing project."""
    project_id = get_project_id(project)
    projects = load_projects()
    project_info = projects.get(project_id, {})
    if project_info:
        created_at = project_info.get("created_at", "Unknown")
        last_used = project_info.get("last_used", "Unknown")
        st.caption(f"Created: {created_at} | Last used: {last_used}")
    select_project = st.button("Load Project", type="primary", width="stretch")

    if select_project:
        st.write(f"Loading project '{project}'...")
        save_project(project, project_id)
        st.session_state.st_project_id = project_id
        ConfigurationService(project_id).sync_output_view_files()
        st.switch_page(st.session_state.st_import_data_page)

    # Only show delete option for non-demo projects
    if project_id != DEMO_PROJECT_ID:
        _show_delete_project_option(project, project_id, projects)


def _show_delete_project_option(project: str, project_id: str, projects: dict):
    """Show delete project option for non-demo projects."""
    with st.expander(":material/delete: delete project"):
        st.warning(
            f"Permanently deletes **{project}** and all its data, corrections, and logs. "
            "This cannot be undone.",
            icon=":material/warning:",
        )
        if st.button("Confirm delete", width="stretch") and project_id in projects:
            delete_project(project_id)
            st.success(f"Project '{project}' deleted successfully!")
            if "st_project_id" in st.session_state:
                st.session_state.st_project_id = ""
            st.rerun()


def _render_project_selection_ui():
    """Render the project selection interface."""
    st.header("Select Your Project")
    _, pc1, _ = st.columns([0.25, 0.5, 0.25])
    project_list = get_project_names()
    last_used_name = _get_last_used_project_name()
    default_index = (
        project_list.index(last_used_name)
        if last_used_name and last_used_name in project_list
        else None
    )

    with pc1, st.container(border=True):
        st.markdown(
            "Select a DataSure project to get started. If you don't have a project yet, you can create a new project "
            "by selecting the **'Create New Project'** option. If you are new to DataSure, try the **'DataSure Demo'** "
            "project for a guided experience."
        )
        project = st.selectbox(
            label="Select Project",
            options=project_list,
            index=default_index,
            key="project_select_key",
        )

        if project == "DataSure Demo":
            _handle_demo_project()
        elif project == "Create New Project":
            _handle_create_new_project()
        elif project:
            _handle_existing_project_selection(project)


def _render_page_header():
    """Render the page header with logo and description."""
    # Get the path to the assets directory relative to the package
    assets_dir = Path(__file__).parent.parent / "assets"
    image_path = assets_dir / "datasure_logo.svg"
    _, logo_col, _ = st.columns([0.35, 0.4, 0.35])
    logo_col.image(str(image_path), width="stretch")

    st.title("Welcome to DataSure")

    st.markdown("""
    **DataSure** is a comprehensive Data Management System designed to streamline survey data quality assurance and management workflows.
    """)


def _render_learn_more_section():
    """Render the expandable 'Learn more' section."""
    with st.expander(":material/info: Learn more"):
        st.header("What is DataSure?")

        st.write(
            "DataSure is a Python-based system that simplifies survey data management from collection to final analysis. "
            "It ensures data quality through automated checks, streamlined corrections, and comprehensive reporting."
        )

        st.divider()

        st.subheader("Why DataSure?")

        st.markdown(
            "DataSure automates the repetitive parts of survey data QA: connecting to your data "
            "sources, running consistency and coverage checks, flagging issues for review, and "
            "generating a documented audit trail. It is designed for research teams that run "
            "high-frequency checks and need a reproducible record of every correction made to the data."
        )

        st.divider()

        # User types - simplified
        st.subheader("Built For")

        st.write(
            "Research teams, data managers, field coordinators, and quality assurance specialists "
            "working with survey data at any scale."
        )

        # Main workflow stages
        st.subheader("How It Works")

        workflow_tabs = st.tabs(
            [
                ":material/upload: Import",
                ":material/rule: Validate",
                ":material/edit: Correct",
                ":material/bar_chart: Report",
                ":material/folder_zip: Replicate",
            ]
        )

        with workflow_tabs[0]:
            st.write("""
            **Connect your data sources:**
            - SurveyCTO direct integration
            - Local file uploads (CSV, Excel, SPSS)
            """)

        with workflow_tabs[1]:
            st.write("""
            **Automatic quality checks:**
            - Duplicate detection
            - Missing data analysis
            - GPS validation
            - Outlier detection
            - Progress tracking
            - Back-check analysis
            """)

        with workflow_tabs[2]:
            st.write("""
            **Streamlined correction:**
            - Flag problematic entries
            - Batch corrections
            - Audit trail
            """)

        with workflow_tabs[3]:
            st.write("""
            **Generate insights:**
            - Interactive dashboards
            - Custom report templates
            - Real-time analytics
            """)

        with workflow_tabs[4]:
            st.write("""
            **Export a self-contained replication package:**
            - Raw survey data (CSV)
            - Stata do-files that reproduce every import, preparation, and correction step
            - Audit logs for all recorded changes
            - README with instructions for running the package

            The package allows anyone with Stata to reproduce your corrected dataset
            from the original source data, supporting transparency and reproducibility
            standards for IPA research projects.
            """)

        st.divider()
        st.link_button(
            "Ready to improve your data workflow? Start with our comprehensive guide",
            "https://data.poverty-action.org/data-quality/datasure/how-to-datasure.html",
            icon=":material/open_in_new:",
            width="stretch",
            type="primary",
        )


st.set_page_config(
    page_title="DataSure - Data Management System",
    page_icon=":material/home_app_logo:",
    layout="wide",
)

_, page_canvas, _ = st.columns([0.1, 0.8, 0.1])
with page_canvas:
    _render_page_header()
    _render_learn_more_section()
    st.write("---")
    _render_project_selection_ui()

try:
    _app_version = version("DataSure")
except PackageNotFoundError:
    _app_version = "dev"

st.divider()
left, mid, right = st.columns(3, border=True)

with left:
    st.caption("ABOUT GRDS AND IPA")
    st.caption(
        "**DataSure** is a product of the "
        "[Global Research and Data Science (GRDS)](https://data.poverty-action.org/teams/grds.html) "
        "team at [Innovations for Poverty Action (IPA)](https://www.poverty-action.org/)."
    )
    st.caption(
        f"Version {_app_version} | Released under the [MIT License](https://github.com/PovertyAction/datasure/blob/main/LICENSE)"
    )

with mid:
    st.caption("PARTNER WITH US")
    st.caption(
        "We welcome contributions from the community! If you're interested in contributing to DataSure, please check out our [Contributing guide](https://github.com/PovertyAction/datasure/blob/main/CONTRIBUTING.md)."
    )

with right:
    st.caption("CONNECT WITH US")
    st.caption(
        ":material/mail: [researchsupport@poverty-action.org](mailto:researchsupport@poverty-action.org)  \n"
        ":material/bug_report: [Open a GitHub issue](https://github.com/PovertyAction/datasure/issues)"
    )
