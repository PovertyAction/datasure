import hashlib
import json
import os
from datetime import datetime

import streamlit as st


def get_project_id(project_name: str) -> str:
    """Generate a unique project ID."""
    hash_val = hashlib.md5(project_name.encode()).hexdigest()
    return hash_val[:8]  # Return the first 8 characters of the hash as the project ID


def get_project_names() -> list[str]:
    """Get a list of project names from the local directory."""
    projects_file = "cache/projects.json"
    if os.path.exists(projects_file):
        with open(projects_file) as f:
            projects = json.load(f)
        project_names = [project["name"] for project in projects.values()]
    return (
        project_names + ["Create New Project"]
        if project_names
        else ["Create New Project"]
    )


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


def load_projects():
    """Load available projects from the local directory."""
    projects_file = "cache/projects.json"
    if os.path.exists(projects_file):
        with open(projects_file) as f:
            projects = json.load(f)
        return projects


def save_project(
    project_name: str, project_id: str, created_at: str | None, last_used: str | None
):
    """Save a new project to the local directory."""
    if not os.path.exists(f"cache/{project_id}"):
        os.makedirs(f"cache/{project_id}")
    projects = load_projects() or {}

    new_project = {
        "name": project_name,
        "created_at": created_at,
        "last_used": last_used,
    }
    projects[project_id] = new_project

    with open("cache/projects.json", "w") as f:
        json.dump(projects, f, indent=4)


st.set_page_config(
    page_title="pyDMS - Data Management System",
    page_icon=":material/home_app_logo:",
    layout="wide",
)

_, page_canvas, _ = st.columns([0.1, 0.8, 0.1])
with page_canvas:
    st.image("assets/LinkedIn Cover IPA20.png", use_container_width=True)

    st.title("Welcome to pyDMS")

    st.markdown("""
    **pyDMS** is a comprehensive Data Management System designed to streamline survey data quality assurance and management workflows.
    """)

    with st.expander(":material/info: Learn more"):
        st.header("What is pyDMS?")

        st.write(
            "pyDMS is a Python-based Data Management System that simplifies the process of managing survey data. "
            "It provides tools for data import, preparation, quality assurance, correction, and reporting. "
            "Whether you're a researcher, data manager, or field coordinator, pyDMS helps you ensure the integrity and quality of your survey data."
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

        st.header("Who Uses pyDMS?")
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
            "Select a pyDMS project to get started. If you don't have a project yet, you can create a new project by selection the 'Create New Project' option."
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
                created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                last_used = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                save_project(project_name, project_id, created_at, last_used)
                st.success(f"Project '{project_name}' created successfully!")
                st.rerun()
        elif project:
            project_id = get_project_id(project)
            projects = load_projects()
            if st.button("Load Project", type="primary", use_container_width=True):
                st.write(f"Loading project '{project}'...")
                st.session_state.st_load_project = True
                st.session_state.st_project_id = project_id
            with st.expander(":material/delete: delete project"):
                if (
                    st.button("Confirm delete", use_container_width=True)
                    and project_id in projects
                ):
                    projects.pop(project_id)
                    with open("cache/projects.json", "w") as f:
                        json.dump(projects, f, indent=4)
                    project_dir = f"cache/{project_id}"
                    if os.path.exists(project_dir):
                        os.rmdir(project_dir)
                    st.success(f"Project '{project}' deleted successfully!")
                    st.rerun()
