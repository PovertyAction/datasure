import hashlib
import json
import shutil
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

import streamlit as st
from pydantic import ValidationError

from datasure.models.schemas import ProjectConfigBundle
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.config_utils import ConfigurationService
from datasure.utils.duckdb_utils import duckdb_get_aliases
from datasure.utils.onboarding_utils import (
    DEMO_PROJECT_ID,
    create_demo_project,
    load_demo_data,
    set_onboarding_step,
    show_demo_intro,
)
from datasure.utils.project_config import (
    export_project_config,
    parse_project_config,
    render_config_resolution_and_apply,
    render_project_config_wizard,
)
from datasure.utils.ui_utils import confirm_dialog

PROJECTS_FILE: str = "projects.json"


def _validate_project_id(project_id: str) -> bool:
    """Validate project ID to prevent path traversal attacks."""
    # Project ID should only contain alphanumeric characters
    return project_id.isalnum() and len(project_id) == 8


def get_project_id(project_name: str) -> str:
    """Generate a unique project ID."""
    hash_val = hashlib.sha256(project_name.encode()).hexdigest()
    return hash_val[:8]  # Return the first 8 characters of the hash as the project ID


def _non_demo_projects(projects: dict) -> list[tuple[str, dict]]:
    """Return (project_id, info) for every non-demo project."""
    return [
        (pid, info)
        for pid, info in projects.items()
        if not info.get("is_demo", False) and pid != DEMO_PROJECT_ID
    ]


def _filter_and_sort_projects(
    rows: list[tuple[str, dict]], search: str, sort_by: str
) -> list[tuple[str, dict]]:
    """Filter projects by name (case-insensitive substring) and sort them.

    Parameters
    ----------
    rows : list[tuple[str, dict]]
        (project_id, info) pairs, as returned by `_non_demo_projects`.
    search : str
        Substring to filter project names by. Empty string matches all.
    sort_by : str
        "Name" for alphabetical order, anything else for most-recently-used
        first.
    """
    if search:
        needle = search.strip().lower()
        rows = [row for row in rows if needle in row[1].get("name", "").lower()]
    if sort_by == "Name":
        return sorted(rows, key=lambda row: row[1].get("name", "").lower())
    return sorted(rows, key=lambda row: row[1].get("last_used", ""), reverse=True)


def _project_stats(project_id: str) -> tuple[int, int]:
    """Return (dataset count, HFC page count) for a project."""
    dataset_count = len(duckdb_get_aliases(project_id, to_load=True))
    page_count = ConfigurationService(project_id).get_all_configurations().height
    return dataset_count, page_count


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


def _now_str() -> str:
    """Return the current timestamp in the project metadata format."""
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _save_projects(projects: dict) -> None:
    """Write the full projects registry back to disk."""
    projects_file = get_cache_path(PROJECTS_FILE)
    with open(projects_file, "w") as f:
        json.dump(projects, f, indent=4)


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
        created_at = _now_str()
        with open(project_info_path, "w") as f:
            json.dump({"created_at": created_at}, f, indent=4)
    else:
        if project_info_path.exists():
            with open(project_info_path) as f:
                project_info = json.load(f)
            created_at = project_info.get("created_at", _now_str())
        else:
            created_at = _now_str()
            with open(project_info_path, "w") as f:
                json.dump({"created_at": created_at}, f, indent=4)
    last_used = _now_str()
    projects = load_projects() or {}
    new_project = {
        "name": project_name,
        "created_at": created_at,
        "last_used": last_used,
    }
    projects[project_id] = new_project
    _save_projects(projects)


def delete_project(project_id: str):
    """Delete a project from the local directory."""
    if not _validate_project_id(project_id):
        st.error(f"Invalid project ID: {project_id}")
        return

    projects = load_projects()
    if project_id in projects:
        projects.pop(project_id)
        _save_projects(projects)

        project_path = get_cache_path(project_id)

        if project_path.exists():
            shutil.rmtree(project_path)
        st.success(f"Project '{project_id}' deleted successfully!", width="stretch")
    else:
        st.error(f"Project '{project_id}' does not exist.")


def _activate_project(project_id: str) -> None:
    """Set the active project and jump to the Import Data page."""
    st.session_state.st_project_id = project_id
    ConfigurationService(project_id).sync_output_view_files()
    st.switch_page(st.session_state.st_import_data_page)


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


def _render_demo_row() -> None:
    """Render the pinned DataSure Demo row."""
    demo_exists = DEMO_PROJECT_ID in load_projects()

    if not demo_exists:
        show_demo_intro()

    with st.container(border=True):
        name_col, action_col = st.columns([0.7, 0.3])
        with name_col:
            st.markdown(":material/school: **DataSure Demo**")
            st.caption("A pre-loaded sample project for exploring DataSure.")
        with action_col:
            if demo_exists:
                resume_col, restart_col = st.columns(2)
                with resume_col:
                    if st.button(
                        "Resume", type="primary", width="stretch", key="demo_resume"
                    ):
                        _activate_project(DEMO_PROJECT_ID)
                with restart_col:
                    if st.button("Restart", width="stretch", key="demo_restart"):
                        confirm_dialog(
                            "Restart demo",
                            "Restarting will permanently delete all your demo "
                            "progress, including any corrections and data "
                            "preparation steps you have made. This cannot be "
                            "undone.",
                            confirm_label="Restart demo",
                            on_confirm=_launch_fresh_demo,
                        )
            else:
                if st.button(
                    "Start Demo", type="primary", width="stretch", key="demo_start"
                ):
                    _launch_fresh_demo()


def _create_and_load_project(project_name: str, project_id: str):
    """Create a new project, set it as active, and navigate to the import page."""
    save_project(project_name, project_id)
    _activate_project(project_id)


def _check_new_project_name(project_name: str) -> str | None:
    """Validate a new project name and its uniqueness.

    Returns
    -------
        The project ID if the name is valid and unique, or None (after
        showing an error) otherwise.
    """
    if not valid_project_name(project_name):
        return None
    project_id = get_project_id(project_name)
    existing_projects = load_projects()
    if existing_projects and project_id in existing_projects:
        st.error(
            f"Project '{project_name}' already exists. Please choose a different name."
        )
        st.stop()
    return project_id


def _render_new_project_mode_switch() -> str:
    """Render the "Start from scratch" / "From a configuration file" switch.

    A plain `st.button` only reports True on the single rerun right after
    it's clicked, so it can't act as a toggle by itself - the current mode
    is held in `st.session_state["new_project_mode"]` instead, and each
    button just sets it. "blank" is the default every time the dialog is
    freshly opened (see the "+ New Project" button in
    `_render_project_toolbar`).

    Returns
    -------
        The current mode: "blank" or "config".
    """
    mode = st.session_state.get("new_project_mode", "blank")

    blank_col, config_col = st.columns(2)
    with blank_col:
        if st.button(
            ":material/lightbulb: Start from scratch",
            type="primary" if mode == "blank" else "secondary",
            width="stretch",
        ):
            mode = "blank"
            st.session_state.new_project_mode = mode
    with config_col:
        if st.button(
            ":material/upload_file: From a configuration file",
            type="primary" if mode == "config" else "secondary",
            width="stretch",
        ):
            mode = "config"
            st.session_state.new_project_mode = mode

    return mode


def _render_new_project_config_upload() -> ProjectConfigBundle | None:
    """Render the configuration file uploader and parse the result.

    Returns
    -------
        The parsed bundle once a valid file is uploaded, else None.
    """
    uploaded = st.file_uploader(
        "Configuration file", type=["json"], key="new_project_cfg_upload"
    )
    if uploaded is None:
        return None

    try:
        bundle = parse_project_config(uploaded.getvalue())
    except (json.JSONDecodeError, ValidationError) as e:
        st.error(f"This doesn't look like a valid configuration file: {e}")
        return None

    st.caption(f"Exported from **{bundle.exported_from_project}**")
    return bundle


def _render_new_project_form() -> None:
    """Render the new-project name + start-mode form.

    Split out from `_new_project_dialog` so the form logic stays testable as
    a plain function - `@st.dialog`-wrapped functions can't be exercised
    directly under this test suite's mocked streamlit module.

    Once a project has been created from a configuration file, this skips
    straight to resolving/applying it on every later rerun (tracked via
    `st.session_state["new_project_created_id"]`) instead of showing the
    name/mode form again - a dialog can't open a second dialog for that
    step, so it has to render inline in this same one.
    """
    created_id = st.session_state.get("new_project_created_id")
    if created_id:
        bundle = st.session_state.get("new_project_bundle")
        render_config_resolution_and_apply(
            created_id, bundle, on_complete=lambda: _activate_project(created_id)
        )
        return

    project_name = st.text_input("Project name", placeholder="My New Project")
    mode = _render_new_project_mode_switch()

    if mode == "config":
        st.caption(
            "We'll create the project, then walk through matching it to a "
            "configuration file exported from another DataSure project."
        )
        bundle = _render_new_project_config_upload()

        if st.button(
            ":material/rocket_launch: Create Project & Continue",
            type="primary",
            width="stretch",
            disabled=not project_name or bundle is None,
        ):
            project_id = _check_new_project_name(project_name)
            if project_id:
                save_project(project_name, project_id)
                st.session_state.new_project_created_id = project_id
                st.session_state.new_project_bundle = bundle
                # scope="fragment": a dialog is implemented as a fragment,
                # and a plain (app-scoped) rerun exits that fragment,
                # closing the dialog instead of just refreshing its content.
                st.rerun(scope="fragment")
        return

    if st.button(
        ":material/rocket_launch: Create Project",
        type="primary",
        disabled=not project_name,
        width="stretch",
    ):
        project_id = _check_new_project_name(project_name)
        if project_id:
            _create_and_load_project(project_name, project_id)


@st.dialog(title="New Project", width="small")
def _new_project_dialog() -> None:
    """Open the new-project creation dialog."""
    _render_new_project_form()


def _render_project_row(project_id: str, info: dict, projects: dict) -> None:
    """Render one row in the project list: name/meta, stats, Open, and a "more" menu."""
    name = info.get("name", project_id)
    last_used = info.get("last_used", "Unknown")
    dataset_count, page_count = _project_stats(project_id)
    dataset_word = "dataset" if dataset_count == 1 else "datasets"
    page_word = "HFC page" if page_count == 1 else "HFC pages"

    with st.container(border=True):
        name_col, stats_col, open_col, menu_col = st.columns(
            [0.45, 0.25, 0.15, 0.15], vertical_alignment="center"
        )
        with name_col:
            st.markdown(f"**{name}**")
            st.caption(f"Last used {last_used}")
        with stats_col:
            st.caption(f"{dataset_count} {dataset_word} · {page_count} {page_word}")
        with open_col:
            if st.button(
                "Open", type="primary", width="stretch", key=f"open_{project_id}"
            ):
                save_project(name, project_id)
                _activate_project(project_id)
        with (
            menu_col,
            st.popover(
                ":material/more_vert: More",
                width="stretch",
                key=f"project_menu_{project_id}",
            ),
        ):
            _show_export_config_option(name, project_id)
            _show_update_from_config_option(name, project_id)
            _show_delete_project_option(name, project_id, projects)


def _show_export_config_option(project: str, project_id: str) -> None:
    """Show the option to export this project's configuration to a file."""
    bundle = export_project_config(project_id, project)
    export_date = datetime.now().strftime("%Y%m%d")
    file_name = (
        f"{project.lower().replace(' ', '_')}_datasure_config_{export_date}.json"
    )
    st.download_button(
        ":material/download: Export configuration",
        data=bundle.model_dump_json(indent=2),
        file_name=file_name,
        mime="application/json",
        width="stretch",
        key=f"export_config_{project_id}",
    )


def _show_update_from_config_option(project: str, project_id: str) -> None:
    """Show the option to update an existing project from a configuration file."""
    if st.button(
        ":material/upload_file: Update from configuration",
        width="stretch",
        key=f"update_config_{project_id}",
    ):
        render_project_config_wizard(
            project_id, project, on_complete=lambda: _activate_project(project_id)
        )


def _delete_project_and_reset(project_id: str):
    """Delete a project and clear it from session state."""
    delete_project(project_id)
    if "st_project_id" in st.session_state:
        st.session_state.st_project_id = ""


def _show_delete_project_option(project: str, project_id: str, projects: dict):
    """Show delete project option for non-demo projects."""
    if st.button(
        ":material/delete: Delete project",
        width="stretch",
        key=f"delete_project_{project_id}",
    ):
        confirm_dialog(
            "Delete project",
            f"This permanently deletes **{project}** and all its data, corrections, "
            "and logs. This cannot be undone.",
            confirm_label="Delete project",
            on_confirm=lambda: _delete_project_and_reset(project_id),
        )


def _render_project_toolbar() -> tuple[str, str]:
    """Render the search / sort / new-project toolbar.

    Returns
    -------
        The current (search text, sort field) selections.
    """
    search_col, sort_col, new_col = st.columns([0.5, 0.25, 0.25])
    with search_col:
        search = st.text_input(
            "Search projects",
            placeholder="Search projects...",
            label_visibility="collapsed",
            key="project_search",
        )
    with sort_col:
        sort_by = st.selectbox(
            "Sort by",
            options=["Last used", "Name"],
            label_visibility="collapsed",
            key="project_sort_by",
        )
    with new_col:
        if st.button(":material/add: New Project", type="primary", width="stretch"):
            st.session_state.new_project_mode = "blank"
            st.session_state.pop("new_project_created_id", None)
            st.session_state.pop("new_project_bundle", None)
            _new_project_dialog()
    return search, sort_by


def _render_project_selection_ui():
    """Render the project selection interface."""
    st.header("Your Projects")
    st.caption("Open a project to continue, or start a new one.")

    search, sort_by = _render_project_toolbar()

    _render_demo_row()
    st.divider()

    projects = load_projects()
    rows = _filter_and_sort_projects(_non_demo_projects(projects), search, sort_by)

    if not rows:
        if search:
            st.info("No projects match your search.")
        else:
            st.info("No projects yet. Use **+ New Project** above to create one.")
        return

    for project_id, info in rows:
        _render_project_row(project_id, info, projects)


def _render_page_header():
    """Render the page header with logo and description."""
    # Get the path to the assets directory relative to the package
    assets_dir = Path(__file__).parent.parent / "assets"
    image_path = assets_dir / "datasure-stacked.svg"
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


# Page title and layout are set globally in app.py via st.set_page_config; the
# per-page title is supplied by st.Page(title=...) in the navigation menu.

_, page_canvas, _ = st.columns([0.1, 0.8, 0.1])
with page_canvas:
    _render_page_header()
    _render_learn_more_section()
    st.divider()
    _render_project_selection_ui()

try:
    _app_version = version("DataSure")
except PackageNotFoundError:
    _app_version = "dev"

st.divider()
left, mid, right = st.columns(3, border=True)

with left:
    _ipa_logo_path = (
        Path(__file__).parent.parent / "assets" / "IPA-primary-color-RGB.png"
    )
    st.image(str(_ipa_logo_path), width=180)
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
