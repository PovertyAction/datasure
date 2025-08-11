import hashlib
import json
import os
from datetime import datetime
from importlib.metadata import version
from pathlib import Path

import streamlit as st

from datasure.utils.cache_utils import get_cache_path


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
    projects_file = get_cache_path("projects.json")
    project_names = []
    if projects_file.exists():
        with open(projects_file) as f:
            projects = json.load(f)
        project_names = [project["name"] for project in projects.values()]
    return project_names + ["Create New Project"]


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
    projects_file = get_cache_path("projects.json")
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

    projects_file = get_cache_path("projects.json")
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
        projects_file = get_cache_path("projects.json")
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


st.set_page_config(
    page_title="DataSure - Data Management System",
    page_icon=":material/home_app_logo:",
    layout="wide",
)

_, page_canvas, _ = st.columns([0.1, 0.8, 0.1])
with page_canvas:
    st.write(f"version {version('DataSure')}")
    # Get the path to the assets directory relative to the package
    assets_dir = Path(__file__).parent.parent / "assets"
    image_path = assets_dir / "LinkedIn Cover IPA20.png"
    st.image(str(image_path), use_container_width=True)

    st.title("Welcome to DataSure")

    st.markdown("""
    **DataSure** is a comprehensive Data Management System designed to streamline survey data quality assurance and management workflows.
    """)

    with st.expander(":material/info: Learn more"):
        st.header("What is DataSure?")

        st.write(
            "DataSure is a Python-based Data Management System that simplifies the process of managing survey data. "
            "It provides tools for data import, preparation, quality assurance, correction, and reporting. "
            "Whether you're a researcher, data manager, or field coordinator, DataSure helps you ensure the integrity and quality of your survey data."
        )

        st.write("It provides intuitive interface for:")

        st.write("""
        - **Data Import**: Connect to SurveyCTO, upload local files, or run custom scripts
        - **Data Preparation**: Clean and prepare your datasets for analysis
        - **Quality Assurance**: Run comprehensive data quality checks including:
            - Duplicate detection
            - Missing data analysis
            - GPS coordinate validation
            - Outlier detection
            - Progress tracking
            - Back-check validation
        - **Data Correction**: Identify and correct data issues with built-in workflows
        - **Reporting**: Generate detailed reports and visualizations
        """)

        st.header("Key Features")

        st.write("""
        - **Multi-source Data Integration**: Import from SurveyCTO, local files, or custom scripts
        - **Automated Quality Checks**: Built-in validation rules for common data issues
        - **Interactive Dashboard**: Real-time data exploration and visualization
        - **Correction Workflows**: Streamlined process for data cleaning and validation
        - **Export Capabilities**: Generate reports in multiple formats
        """)

        st.header("Who Uses DataSure?")
        st.write("""
        - Survey researchers
        - Data managers
        - Field coordinators
        - Quality assurance teams
        - Anyone working with survey data collection and management
        """)

    st.write("---")

    st.header("Select Your Project")
    _, pc1, _ = st.columns([0.25, 0.5, 0.25])
    project_list = get_project_names()
    with pc1, st.container(border=True):
        st.write(
            "Select a DataSure project to get started. If you don't have a project yet, you can create a new project by selection the 'Create New Project' option."
        )
        project = st.selectbox(
            label="Select Project",
            options=project_list,
            index=None,
            key="project_select_key",
        )
        if project == "Create New Project":
            project_name = st.text_input(
                "Enter Project Name", placeholder="My New Project"
            )
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
        elif project:
            project_id = get_project_id(project)
            projects = load_projects()
            select_project = st.button(
                "Load Project", type="primary", use_container_width=True
            )
            if select_project:
                views_dir = Path(__file__).parent
                st.write(f"Loading project '{project}'...")
                st.session_state.st_project_id = project_id
                st.switch_page(st.session_state.st_import_data_page)
            with st.expander(":material/delete: delete project"):
                if (
                    st.button("Confirm delete", use_container_width=True)
                    and project_id in projects
                ):
                    delete_project(project_id)
                    st.success(f"Project '{project}' deleted successfully!")
                    if "st_project_id" in st.session_state:
                        st.session_state.st_project_id = ""
                    st.rerun()
