"""Replication Package Export view.

Exports a self-contained Stata replication package (raw CSV, do-files,
audit logs, README) as a zip file for download to the local drive.
"""

from __future__ import annotations

import json

import polars as pl
import streamlit as st

from datasure.processing.replication.package_builder import build_replication_package
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.config_utils import ConfigurationService

_PROJECTS_FILE = "projects.json"


def _get_project_name(project_id: str) -> str:
    """Look up the human-readable project name from projects.json."""
    projects_file = get_cache_path(_PROJECTS_FILE)
    if projects_file.exists():
        with open(projects_file) as f:
            projects = json.load(f)
        return projects.get(project_id, {}).get("name", project_id)
    return project_id


# ── Guard: project must be loaded ────────────────────────────────────────────

project_id: str = st.session_state.get("st_project_id", "")

if not project_id:
    st.info("Select a project from the Start Here page before exporting.")
    st.stop()

# ── Load check configurations ────────────────────────────────────────────────

config_service = ConfigurationService(project_id)
configs: pl.DataFrame = config_service.get_all_configurations()

if configs.is_empty():
    st.info(
        "No check configurations found. "
        "Set up your checks in **Configure Checks** before exporting."
    )
    st.stop()

# ── Page header ──────────────────────────────────────────────────────────────

st.title("Replication Package")
st.markdown(
    "Export a self-contained Stata replication package that allows anyone to "
    "reproduce your corrected dataset from the raw source data."
)
st.divider()

# ── Configuration form ───────────────────────────────────────────────────────

st.subheader("Configure export")

survey_aliases = sorted(configs["survey_data_name"].unique().to_list())

selected_alias = st.selectbox(
    "Dataset",
    options=survey_aliases,
    help="Choose the survey dataset to include in the replication package.",
)

# Resolve key column from the first matching configuration
key_col = ""
if selected_alias:
    match = configs.filter(pl.col("survey_data_name") == selected_alias)
    if not match.is_empty():
        key_col = match[0, "survey_key"] or ""

col_left, col_right = st.columns(2)
with col_left:
    default_project_name = _get_project_name(project_id)
    project_name = st.text_input(
        "Project name",
        value=default_project_name,
        help="Used to name the root folder inside the zip file.",
    )
with col_right:
    survey_name = st.text_input(
        "Survey name",
        value=selected_alias or "",
        help="Used to name the raw data file and output datasets.",
    )

# ── Build button ─────────────────────────────────────────────────────────────

st.divider()

build_disabled = not (selected_alias and project_name and survey_name and key_col)

if not key_col and selected_alias:
    st.warning(
        "No key column is configured for the selected dataset. "
        "Edit the check configuration to add one before exporting."
    )

if st.button(
    "Build Replication Package",
    type="primary",
    disabled=build_disabled,
):
    safe_project = project_name.lower().replace(" ", "_")

    with st.spinner("Building replication package…"):
        zip_bytes = build_replication_package(
            project_id=project_id,
            project_name=project_name,
            survey_name=survey_name,
            alias=selected_alias,
            key_col=key_col,
        )

    st.session_state["_replication_zip"] = zip_bytes
    st.session_state["_replication_filename"] = f"{safe_project}_replication.zip"

# ── Download button (persists after build) ───────────────────────────────────

if "_replication_zip" in st.session_state:
    st.success("Package ready — click below to save it to your local drive.")
    st.download_button(
        label="Download replication package (.zip)",
        data=st.session_state["_replication_zip"],
        file_name=st.session_state["_replication_filename"],
        mime="application/zip",
        icon=":material/download:",
        type="primary",
    )

# ── Package contents preview ─────────────────────────────────────────────────

with st.expander("What's inside the zip?", expanded=False):
    if selected_alias and project_name and survey_name:
        safe_p = project_name.lower().replace(" ", "_")
        safe_s = survey_name.lower().replace(" ", "_")
        st.code(
            f"{safe_p}_replication/\n"
            f"├── raw/\n"
            f"│   └── {safe_s}_raw.csv\n"
            f"├── scripts/\n"
            f"│   ├── master.do\n"
            f"│   ├── import_data.do\n"
            f"│   ├── prepare_data.do\n"
            f"│   └── corrections.do\n"
            f"├── output/               (generated when scripts are run)\n"
            f"│   ├── {safe_s}_raw.dta\n"
            f"│   ├── {safe_s}_prepped.dta\n"
            f"│   └── {safe_s}_corrected.dta\n"
            f"└── docs/\n"
            f"    ├── README.md\n"
            f"    ├── codebook.xlsx     (generated by ipacodebook)\n"
            f"    ├── correction_log.csv\n"
            f"    └── prep_log.csv",
            language="text",
        )
    else:
        st.info("Fill in the fields above to preview the package structure.")
