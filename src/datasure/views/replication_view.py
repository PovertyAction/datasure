"""Replication Package Export view.

Exports a self-contained Stata replication package (raw CSV, do-files,
audit logs, README) as a zip file for download to the local drive.
"""

import json

import polars as pl
import streamlit as st

from datasure.processing import pii
from datasure.replication.package_builder import build_replication_package
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.config_utils import ConfigurationService
from datasure.utils.duckdb_utils import duckdb_get_table
from datasure.utils.navigations_utils import (
    add_demo_navigation,
    demo_callout,
    demo_sidebar_help,
)
from datasure.utils.scto_api import (
    SurveyCTOAPIClient,
    SurveyCTOAPIConfig,
    SurveyCTOAPIError,
)
from datasure.utils.secure_credentials import retrieve_scto_credentials
from datasure.utils.ui_utils import page_header, section_header

_PROJECTS_FILE = "projects.json"


# ── Data access ───────────────────────────────────────────────────────────────


@st.cache_data(ttl=60)
def _get_project_name(project_id: str) -> str:
    """Return the human-readable project name, falling back to project_id."""
    projects_file = get_cache_path(_PROJECTS_FILE)
    if projects_file.exists():
        with open(projects_file) as f:
            projects = json.load(f)
        return projects.get(project_id, {}).get("name", project_id)
    return project_id


def _get_import_log_row(project_id: str, alias: str) -> dict | None:
    """Return the import_log row for *alias*, or None if not found."""
    try:
        import_log = duckdb_get_table(project_id, "import_log", "logs")
        row_df = import_log.filter(pl.col("alias") == alias)
        if row_df.is_empty():
            return None
        return row_df.row(0, named=True)
    except Exception:
        return None


# ── Configuration helpers (pure) ──────────────────────────────────────────────


def _resolve_page_config(
    configs: pl.DataFrame, page_name: str
) -> tuple[str, str] | None:
    """Return ``(alias, key_col)`` for *page_name*, or None if not found.

    Parameters
    ----------
    configs:
        DataFrame returned by ``ConfigurationService.get_all_configurations()``.
    page_name:
        The selected page / check-configuration name.
    """
    page_configs = configs.filter(pl.col("page_name") == page_name)
    if page_configs.is_empty():
        return None
    alias = page_configs[0, "survey_data_name"] or ""
    key_col = page_configs[0, "survey_key"] or ""
    return alias, key_col


def _zip_filename(project_name: str, page_name: str, deidentified: bool = False) -> str:
    """Return the download filename for the replication package zip.

    Example: ``replication_ors_zinc_community_hfc.zip`` (or with a
    ``_deidentified`` suffix for de-identified exports).
    """
    safe_p = project_name.lower().replace(" ", "_")
    safe_pg = page_name.lower().replace(" ", "_")
    suffix = "_deidentified" if deidentified else ""
    return f"replication_{safe_p}_{safe_pg}{suffix}.zip"


def _package_tree(
    safe_project: str, safe_page: str, is_scto: bool, include_pii: bool = False
) -> str:
    """Return the zip contents as a plain-text directory tree."""
    surveys_line = (
        f"│   ├── 1_surveys/{safe_page}_questionnaire.xlsx\n"
        if is_scto
        else "│   ├── 1_surveys/\n"
    )
    scripts_tail = (
        "│   ├── 4_corrections.do / .py\n"
        "│   └── 5_deidentify_data.py   (de-identify bundled datasets)\n"
        if include_pii
        else "│   └── 4_corrections.do / .py\n"
    )
    return (
        f"replication_{safe_project}_{safe_page}/\n"
        f"├── README.md\n"
        f"├── 1_docs/\n"
        f"{surveys_line}"
        f"│   ├── 2_codebooks/\n"
        f"│   │   ├── codebook.csv\n"
        f"│   │   ├── data-dict.yaml\n"
        f"│   │   └── codebook.xlsx      (generated when scripts are run)\n"
        f"│   └── 3_notes/\n"
        f"├── 2_scripts/\n"
        f"│   ├── 0_main.do / 0_main.py\n"
        f"│   ├── 1_install_packages.do\n"
        f"│   ├── 2_import_data.do       (Stata only)\n"
        f"│   ├── 3_prepare_data.do / .py\n"
        f"{scripts_tail}"
        f"├── 3_data/\n"
        f"│   ├── 1_raw/{safe_page}_raw.csv, {safe_page}_raw.parquet\n"
        f"│   ├── 2_intermediate/{safe_page}_prepped.parquet\n"
        f"│   │                  (+ .dta when scripts are run)\n"
        f"│   └── 3_final/{safe_page}_corrected.parquet\n"
        f"│                      (+ .dta when scripts are run)\n"
        f"└── 4_output/\n"
        f"    ├── 1_tables/\n"
        f"    ├── 2_figures/\n"
        f"    └── 3_logs/\n"
        f"        ├── <date>/\n"
        f"        │   ├── 0_main.log\n"
        f"        │   └── ...per-script logs\n"
        f"        ├── correction_log.csv\n"
        + (
            "        ├── prep_log.csv\n        └── pii_flags.csv"
            if include_pii
            else "        └── prep_log.csv"
        )
    )


# ── SurveyCTO integration ─────────────────────────────────────────────────────


def _fetch_scto_assets(
    project_id: str, alias: str
) -> tuple[bytes | None, dict | None, str, str]:
    """Fetch the SurveyCTO questionnaire XLS and form definition for *alias*.

    Returns
    -------
    tuple[bytes | None, dict | None, str, str]
        ``(xlsx_bytes, form_def, form_id, error_msg)``.
        *error_msg* is an empty string on success or for non-SurveyCTO datasets.
        Both *xlsx_bytes* and *form_def* are ``None`` when the download failed.
    """
    row = _get_import_log_row(project_id, alias)
    if row is None or row.get("source") != "SurveyCTO":
        return None, None, "", ""

    server = row.get("server", "")
    username = row.get("username", "")
    form_id = row.get("form_id", "") or ""

    if not (server and form_id):
        return None, None, form_id, "Server or form ID missing from import log."

    cred = retrieve_scto_credentials(project_id, server)
    if not cred.get("success"):
        return (
            None,
            None,
            form_id,
            (
                f"Could not retrieve stored credentials for server **{server}**: "
                f"{cred.get('error', 'unknown error')}. "
                "Try re-importing the dataset to refresh your credentials."
            ),
        )

    password = cred.get("credentials", {}).get("password", "")
    if not password:
        return (
            None,
            None,
            form_id,
            (f"Password not found in keyring for server **{server}**."),
        )

    try:
        api_config = SurveyCTOAPIConfig(
            server_name=server,
            username=username or cred["credentials"].get("username", ""),
            password=password,
        )
        xlsx_bytes, form_def = SurveyCTOAPIClient(api_config).download_form_xlsx(
            form_id
        )
        return xlsx_bytes, form_def, form_id, ""  # noqa: TRY300
    except SurveyCTOAPIError as exc:
        return (
            None,
            None,
            form_id,
            (
                f"Could not download the questionnaire from SurveyCTO: {exc}  \n"
                "The package will be built without the questionnaire file."
            ),
        )
    except Exception as exc:
        return (
            None,
            None,
            form_id,
            (
                f"Unexpected error fetching questionnaire: {exc}  \n"
                "The package will be built without the questionnaire file."
            ),
        )


# ── UI helpers ────────────────────────────────────────────────────────────────


def _on_progress(msg: str) -> None:
    st.write(f":material/check_circle: {msg}")


def _render_config_details(page_configs: pl.DataFrame) -> None:
    """Show an expanded table of configuration fields for the selected page."""
    with st.expander("Selected page details", expanded=True):
        st.write("**Configurations for this page:**")
        st.dataframe(
            page_configs.select(
                "survey_data_name",
                "backcheck_data_name",
                "survey_key",
                "survey_id",
                "survey_date",
                "enumerator",
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "survey_data_name": "Dataset name",
                "backcheck_data_name": "Backcheck dataset name",
                "survey_key": "Key column",
                "survey_id": "Survey ID",
                "survey_date": "Survey date column",
                "enumerator": "Enumerator column",
            },
        )


def _render_package_preview(
    safe_project: str, safe_page: str, is_scto: bool, include_pii: bool = False
) -> None:
    """Render the collapsible zip-contents preview."""
    with st.expander("What's inside the zip?", expanded=False):
        st.code(
            _package_tree(safe_project, safe_page, is_scto, include_pii),
            language="text",
        )


def _render_pii_flags_summary(project_id: str, alias: str, include_pii: bool) -> None:
    """Show what the export will do with each PII-flagged column."""
    flags = pii.load_pii_flags(project_id, alias)
    if flags.is_empty():
        st.info(
            "No PII scan has been run for this dataset. Nothing will be "
            "redacted — run **Scan for PII** on the Prepare Data page to "
            "flag columns first.",
            icon=":material/shield:",
        )
        return

    if include_pii:
        action_expr = pl.lit("exported as-is (PII included)")
    else:
        action_expr = (
            pl.when(pl.col("decision").is_in(["mask", "undecided"]))
            .then(pl.lit("masked"))
            .when(pl.col("decision") == "drop")
            .then(pl.lit("dropped"))
            .otherwise(pl.lit("kept (reviewer decision)"))
        )
    summary = flags.select(
        pl.col("column"),
        pl.col("source").alias("flagged by"),
        pl.col("decision"),
        action_expr.alias("export action"),
    )
    st.dataframe(summary, hide_index=True, width="stretch")

    kept = flags.filter(pl.col("decision") == "keep")
    if not include_pii and not kept.is_empty():
        st.warning(
            f"{kept.height} flagged column(s) will be exported unredacted "
            "because the reviewer chose **keep**: "
            + ", ".join(f"`{c}`" for c in kept["column"].to_list()),
            icon=":material/warning:",
        )


# ── Page ──────────────────────────────────────────────────────────────────────

project_id: str = st.session_state.get("st_project_id", "")
if not project_id:
    st.info("Select a project from the Start Here page before exporting.")
    st.stop()

config_service = ConfigurationService(project_id)
configs: pl.DataFrame = config_service.get_all_configurations()
if configs.is_empty():
    st.info(
        "No check configurations found. "
        "Set up your checks in **Configure Checks** before exporting."
    )
    st.stop()

# ── Header ────────────────────────────────────────────────────────────────────

demo_sidebar_help()
add_demo_navigation("replication_view.py", step=7)

page_header(
    "Export Replication Package",
    "Bundle a self-contained Stata replication package so anyone can reproduce "
    "your corrected dataset from the raw source data.",
)

demo_callout(
    """
    This page bundles everything needed to reproduce your corrected dataset into a
    single downloadable zip file — raw data, Stata do-files (import, prepare,
    correct), correction and prep logs, codebooks, and a README.

    ##### Instructions for Demo:
    1. Under **Page Name**, select **Household HFCs**.
    2. Review the configuration details that appear below the selector, then
       expand **What's inside the zip?** to see the full directory structure.
    3. Click **Build Replication Package**. DataSure will assemble the zip in seconds.
    4. Once the build completes, check the PII confirmation box and click
       **Download replication package (.zip)**.

    The demo dataset is synthetic and contains no real PII. In a live project the
    zip would include raw respondent data and must be stored on an encrypted,
    access-controlled drive in accordance with IPA data policy.
    """
)

st.divider()

# ── Page selector ─────────────────────────────────────────────────────────────

section_header("Configure export")

page_name_col, export_mode_col = st.columns(2)
with page_name_col:
    selected_page: str | None = st.selectbox(
        "Page Name",
        options=[None] + configs["page_name"].unique().to_list(),
        index=0,
        help=(
            "Select the check configuration to export. "
            "The associated dataset will be included as raw data in the package."
        ),
    )
with export_mode_col:
    export_mode = st.radio(
        "Export mode",
        options=["De-identified (recommended)", "Include PII"],
        help=(
            "De-identified: columns flagged in the PII review are masked or "
            "dropped in every exported file. Include PII: data is exported "
            "as-is, with a de-identification script bundled."
        ),
        key="_replication_export_mode",
    )
include_pii = export_mode == "Include PII"

if include_pii:
    st.error(
        "**This package will contain personally identifiable information "
        "(PII).** The zip file includes raw survey data with respondent PII. "
        "You must download it only to an **encrypted, access-controlled "
        "storage location** in compliance with IPA data security and "
        "confidentiality policies. Do not store this package on unencrypted "
        "drives, shared folders, or cloud services that are not approved for "
        "confidential data. The recorded PII decisions are bundled as "
        "`2_scripts/5_deidentify_data.py` so recipients can de-identify "
        "downstream.",
        icon=":material/lock:",
    )
else:
    st.warning(
        "**De-identification is not anonymization.** Columns flagged in the "
        "PII review will be masked or dropped, but subjects may remain "
        "identifiable through combinations of the remaining variables "
        "(e.g. age, location, occupation, household composition). Review "
        "the flagged-column summary below and the exported data before "
        "sharing.",
        icon=":material/warning:",
    )

alias: str = ""
key_col: str = ""

# Clear any previously built zip when the page selection or mode changes.
if st.session_state.get("_replication_page_sel") != (selected_page, include_pii):
    st.session_state.pop("_replication_zip", None)
    st.session_state.pop("_replication_filename", None)
    st.session_state.pop("_replication_zip_include_pii", None)
    st.session_state["_replication_page_sel"] = (selected_page, include_pii)

if selected_page:
    resolved = _resolve_page_config(configs, selected_page)
    if not resolved:
        st.warning(
            "No configurations found for the selected page. "
            "The package will be built without a key column."
        )
    else:
        alias, key_col = resolved
        _render_config_details(configs.filter(pl.col("page_name") == selected_page))
        _render_pii_flags_summary(project_id, alias, include_pii)
else:
    st.info("Select a page to see its details here.")

# ── Build ─────────────────────────────────────────────────────────────────────

st.divider()

project_name = _get_project_name(project_id)
safe_project = project_name.lower().replace(" ", "_")

if st.button(
    "Build Replication Package",
    type="primary",
    disabled=not selected_page or not alias,
):
    with st.status("Building replication package…", expanded=True) as build_status:
        st.write("Fetching SurveyCTO questionnaire…")
        scto_xlsx, scto_form_def, scto_form_id, scto_error = _fetch_scto_assets(
            project_id, alias
        )
        if scto_error:
            st.warning(f"Questionnaire not included: {scto_error}")
        elif scto_xlsx:
            st.write(":material/check_circle: Questionnaire downloaded")

        zip_bytes = build_replication_package(
            project_id=project_id,
            project_name=project_name,
            survey_name=selected_page,
            alias=alias,
            key_col=key_col,
            scto_form_xlsx=scto_xlsx,
            form_def=scto_form_def,
            form_id=scto_form_id,
            include_pii=include_pii,
            on_progress=_on_progress,
        )
        build_status.update(label="Package ready!", state="complete", expanded=False)

    st.session_state["_replication_zip"] = zip_bytes
    st.session_state["_replication_zip_include_pii"] = include_pii
    st.session_state["_replication_filename"] = _zip_filename(
        project_name, selected_page, deidentified=not include_pii
    )

# ── Download ──────────────────────────────────────────────────────────────────

if "_replication_zip" in st.session_state:
    built_with_pii = st.session_state.get("_replication_zip_include_pii", True)
    if built_with_pii:
        st.success("Package ready — confirm the PII notice above, then download.")
        pii_confirmed = st.checkbox(
            "I confirm I am downloading this package to an encrypted, "
            "access-controlled storage location.",
            key="_replication_pii_confirmed",
        )
    else:
        st.success(
            "De-identified package ready — acknowledge the indirect-identifier "
            "notice, then download."
        )
        pii_confirmed = st.checkbox(
            "I understand that de-identification does not guarantee anonymity: "
            "subjects may remain indirectly identifiable through combinations "
            "of the remaining variables.",
            key="_replication_pii_confirmed",
        )
    st.download_button(
        label="Download replication package (.zip)",
        data=st.session_state["_replication_zip"],
        file_name=st.session_state["_replication_filename"],
        mime="application/zip",
        icon=":material/download:",
        type="primary",
        disabled=not pii_confirmed,
    )

    if pii_confirmed:
        demo_callout(
            "You have completed the DataSure demo! You have gone through the full "
            "workflow — importing data, preparing it, configuring quality checks, "
            "reviewing reports, correcting data issues, and exporting a replication "
            "package.\n\n"
            "To exit the demo and return to the project selection screen, click the "
            "**Exit Demo** button in the sidebar.",
            type="success",
        )

# ── Preview ───────────────────────────────────────────────────────────────────

if selected_page and alias:
    import_row = _get_import_log_row(project_id, alias)
    is_scto = import_row is not None and import_row.get("source") == "SurveyCTO"
    _render_package_preview(
        safe_project,
        selected_page.lower().replace(" ", "_"),
        is_scto,
        include_pii,
    )
