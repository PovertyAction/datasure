import hashlib
import json
import os
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import streamlit as st

from datasure.utils.cache_utils import get_cache_path
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
    """Get a list of project names from the local directory."""
    projects_file = get_cache_path(PROJECTS_FILE)
    project_names = []
    if projects_file.exists():
        with open(projects_file) as f:
            projects = json.load(f)
        project_names = [
            project["name"]
            for project in projects.values()
            if not project.get("is_demo", False)
        ]
    return ["DataSure Demo"] + project_names + ["Create New Project"]


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

    if not project_path.exists():
        project_path.mkdir(parents=True, exist_ok=True)
        (project_path / "data").mkdir(exist_ok=True)
        (project_path / "settings").mkdir(exist_ok=True)
        created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        last_used = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    else:
        # get created at date from existing project
        project_info_path = project_path / "settings" / "project_info.json"
        if project_info_path.exists():
            with open(project_info_path) as f:
                project_info = json.load(f)
            created_at = project_info.get("created_at")
        else:
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
            for root, dirs, files in os.walk(project_path, topdown=False):
                for name in files:
                    os.remove(os.path.join(root, name))
                for name in dirs:
                    os.rmdir(os.path.join(root, name))
            project_path.rmdir()
        st.success(f"Project '{project_id}' deleted successfully!")
    else:
        st.error(f"Project '{project_id}' does not exist.")


def _handle_demo_project():
    """Handle demo project selection and initialization."""
    show_demo_intro()

    if st.button("Start Demo", type="primary", width="stretch"):
        demo_project_id = create_demo_project()
        st.session_state.st_project_id = demo_project_id
        set_onboarding_step(1)

        with st.spinner("Loading demo data..."):
            if load_demo_data():
                st.success("Demo data loaded successfully!")
                st.session_state.st_project_id = demo_project_id
                set_onboarding_step(2)
                st.switch_page(st.session_state.st_import_data_page)
            else:
                st.error("Failed to load demo data. Please try again.")


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
    select_project = st.button("Load Project", type="primary", width="stretch")

    if select_project:
        st.write(f"Loading project '{project}'...")
        st.session_state.st_project_id = project_id
        st.switch_page(st.session_state.st_import_data_page)

    # Only show delete option for non-demo projects
    if project_id != DEMO_PROJECT_ID:
        _show_delete_project_option(project, project_id, projects)


def _show_delete_project_option(project: str, project_id: str, projects: dict):
    """Show delete project option for non-demo projects."""
    with st.expander(":material/delete: delete project"):
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

    with pc1, st.container(border=True):
        st.markdown(
            "Select a DataSure project to get started. If you don't have a project yet, you can create a new project "
            "by selection the **'Create New Project'** option. If you are new to DataSure, try the **'DataSure Demo'** "
            "project for a guided experience."
        )
        project = st.selectbox(
            label="Select Project",
            options=project_list,
            index=None,
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
    st.write(f"version {version('DataSure')}")
    # Get the path to the assets directory relative to the package
    assets_dir = Path(__file__).parent.parent / "assets"
    image_path = assets_dir / "LinkedIn Cover IPA20.png"
    st.image(str(image_path), width="stretch")

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

        # Benefits in a clean grid
        st.subheader("Why DataSure?")

        benefits = st.columns(3)

        with benefits[0]:
            st.metric("Time Saved", "70%", "on QA tasks")
            st.caption("Automate repetitive validation")

        with benefits[1]:
            st.metric("Error Rate", "-95%", "reduction")
            st.caption("Catch issues early")

        with benefits[2]:
            st.metric("Processing", "10x", "faster")
            st.caption("Batch operations")

        st.divider()

        # User types - simplified
        st.subheader("Built For")

        st.write(
            "Research teams, data managers, field coordinators, and quality assurance specialists "
            "working with survey data at any scale."
        )

        # Main workflow stages
        st.subheader("How It Works")

        workflow_tabs = st.tabs(["1️⃣ Import", "2️⃣ Validate", "3️⃣ Correct", "4️⃣ Report"])

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

        st.divider()

        # Simple CTA
        st.success(
            "Ready to improve your data workflow? Start with our quick setup guide →"
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
