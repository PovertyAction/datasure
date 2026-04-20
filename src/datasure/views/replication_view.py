"""Replication Package Export view.

Exports a self-contained Stata replication package (raw CSV, do-files,
audit logs, README) as a zip file for download to the local drive.
"""

from __future__ import annotations

import json
import time

import polars as pl
import streamlit as st

from datasure.processing.replication.package_builder import build_replication_package
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.config_utils import ConfigurationService
from datasure.utils.duckdb_utils import duckdb_get_table
from datasure.utils.scto_api import (
    SurveyCTOAPIClient,
    SurveyCTOAPIConfig,
    SurveyCTOAPIError,
)
from datasure.utils.secure_credentials import retrieve_scto_credentials

_PROJECTS_FILE = "projects.json"


def _get_project_name(project_id: str) -> str:
    """Look up the human-readable project name from projects.json."""
    projects_file = get_cache_path(_PROJECTS_FILE)
    if projects_file.exists():
        with open(projects_file) as f:
            projects = json.load(f)
        return projects.get(project_id, {}).get("name", project_id)
    return project_id


def _get_import_log_row(project_id: str, alias: str) -> dict | None:
    """Return the import_log row for this alias, or None if not found."""
    try:
        import_log = duckdb_get_table(project_id, "import_log", "logs")
        row_df = import_log.filter(pl.col("alias") == alias)
        if row_df.is_empty():
            return None
        return row_df.row(0, named=True)
    except Exception:
        return None


def _fetch_scto_form_xlsx(
    project_id: str, alias: str
) -> tuple[bytes | None, dict | None, str]:
    """Attempt to download the SurveyCTO XLS form for the given alias.

    Returns
    -------
    tuple[bytes | None, dict | None, str]
        ``(xlsx_bytes, form_def, message)`` where *message* describes any
        failure.  Both ``xlsx_bytes`` and ``form_def`` are ``None`` when the
        dataset is not from SurveyCTO or the download failed.
    """
    row = _get_import_log_row(project_id, alias)
    if row is None:
        return None, None, "Dataset not found in import log."

    if row.get("source") != "SurveyCTO":
        return None, None, ""  # Not a SurveyCTO dataset — silently skip

    server = row.get("server", "")
    username = row.get("username", "")
    form_id = row.get("form_id", "")

    if not (server and form_id):
        return None, None, "Server or form ID missing from import log."

    cred = retrieve_scto_credentials(project_id, server)
    if not cred.get("success"):
        return (
            None,
            None,
            (
                f"Could not retrieve stored credentials for server **{server}**: "
                f"{cred.get('error', 'unknown error')}. "
                "Try re-importing the dataset to refresh your credentials."
            ),
        )

    password = cred.get("credentials", {}).get("password", "")
    if not password:
        return None, None, f"Password not found in keyring for server **{server}**."

    try:
        api_config = SurveyCTOAPIConfig(
            server_name=server,
            username=username or cred["credentials"]["username"],
            password=password,
        )
        client = SurveyCTOAPIClient(api_config)
        xlsx_bytes, form_def = client.download_form_xlsx(form_id)
    except SurveyCTOAPIError as exc:
        return (
            None,
            None,
            (
                f"Could not download the questionnaire from SurveyCTO: {exc}  \n"
                "The package will be built without the questionnaire file."
            ),
        )
    except Exception as exc:
        return (
            None,
            None,
            (
                f"Unexpected error fetching questionnaire: {exc}  \n"
                "The package will be built without the questionnaire file."
            ),
        )
    else:
        return xlsx_bytes, form_def, ""


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
    scto_form_xlsx: bytes | None = None
    scto_form_def: dict | None = None
    scto_form_id: str = ""

    def _on_progress(msg: str) -> None:
        st.write(f":white_check_mark: {msg}")
        time.sleep(1)

    with st.status("Building replication package…", expanded=True) as build_status:
        # ── Step 1: SurveyCTO questionnaire + form definition ─────────────────
        log_row = _get_import_log_row(project_id, selected_alias)
        if log_row is not None and log_row.get("source") == "SurveyCTO":
            scto_form_id = log_row.get("form_id", "") or ""
            st.write("Fetching SurveyCTO questionnaire…")
            scto_form_xlsx, scto_form_def, scto_error = _fetch_scto_form_xlsx(
                project_id, selected_alias
            )
            if scto_error:
                st.warning(f"Questionnaire not included: {scto_error}")
            else:
                st.write(":white_check_mark: Questionnaire downloaded")
            time.sleep(1)

        # ── Steps 2+: data loading + script generation + zip assembly ────────
        zip_bytes = build_replication_package(
            project_id=project_id,
            project_name=project_name,
            survey_name=survey_name,
            alias=selected_alias,
            key_col=key_col,
            scto_form_xlsx=scto_form_xlsx,
            form_def=scto_form_def,
            form_id=scto_form_id,
            on_progress=_on_progress,
        )

        build_status.update(label="Package ready!", state="complete", expanded=False)

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

        # Show questionnaire line only for SurveyCTO datasets
        log_row = _get_import_log_row(project_id, selected_alias)
        is_scto = log_row is not None and log_row.get("source") == "SurveyCTO"
        questionnaire_line = (
            f"    ├── {safe_s}_questionnaire.xlsx (SurveyCTO form)\n" if is_scto else ""
        )

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
            f"{questionnaire_line}"
            f"    ├── correction_log.csv\n"
            f"    └── prep_log.csv",
            language="text",
        )
    else:
        st.info("Fill in the fields above to preview the package structure.")
