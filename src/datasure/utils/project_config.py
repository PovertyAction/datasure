"""Export and import of full project configurations.

Bundles the four layers that make up a DataSure project's setup - import
sources, prep steps, HFC (check) configurations, and corrections - into a
single portable JSON file, and applies that bundle to a new or existing
project. See issue #251.

Credentials, machine-specific file paths, and survey data never travel in
the bundle. Applying a bundle assumes any required SurveyCTO credentials
have already been stored for the target project (via the normal
``SurveyCTOUI.render_login_form`` flow) and that a file path has been
supplied for every "local storage" dataset.
"""

import ast
import json
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import polars as pl
from pydantic import ValidationError

from datasure.connectors.local import FileConfig, load_local_data
from datasure.connectors.scto import FormConfig, SurveyCTOUI, download_forms
from datasure.models.schemas import (
    CheckConfiguration,
    ImportSourceEntry,
    ProjectConfigBundle,
    ProjectPageBundle,
)
from datasure.processing.corrections import CorrectionProcessor
from datasure.processing.prep import prep_apply_action
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.config_utils import ConfigurationService
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.reapply_utils import ReapplyFailure, warn_reapply_failures
from datasure.utils.secure_credentials import list_stored_credentials

# ============================================================================
# EXPORT
# ============================================================================


def _read_json(path: Path) -> dict:
    """Read a JSON settings file, returning {} if it doesn't exist."""
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


def _decode_prep_args_cell(value: str | dict) -> dict:
    """Decode a prep_log prep_args cell (a JSON string, or already a dict)."""
    if isinstance(value, dict):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return ast.literal_eval(value)


def export_project_config(project_id: str, project_name: str) -> ProjectConfigBundle:
    """Build a portable configuration bundle for the given project.

    Parameters
    ----------
    project_id : str
        The project to export.
    project_name : str
        The project's display name, recorded for reference only.

    Returns
    -------
    ProjectConfigBundle
        The assembled bundle, ready to be written to a file.
    """
    import_log = duckdb_get_table(project_id, alias="import_log", db_name="logs")

    datasets: list[ImportSourceEntry] = []
    prep_steps: dict[str, list[dict]] = {}
    corrections: dict[str, list[dict]] = {}

    for row in import_log.iter_rows(named=True):
        alias = row["alias"]
        datasets.append(
            ImportSourceEntry(
                alias=alias,
                source=row.get("source") or "",
                server=row.get("server") or None,
                form_id=row.get("form_id") or None,
                username=row.get("username") or None,
                filename=row.get("filename") or None,
                sheet_name=row.get("sheet_name") or None,
                attachments=bool(row.get("attachments")),
            )
        )

        prep_log = duckdb_get_table(
            project_id, alias=f"prep_log_{alias}", db_name="logs"
        )
        if not prep_log.is_empty():
            prep_steps[alias] = [
                _decode_prep_args_cell(v) for v in prep_log["prep_args"].to_list()
            ]

        corr_log = duckdb_get_table(
            project_id, alias=f"corr_log_{alias}", db_name="logs"
        )
        if not corr_log.is_empty():
            corrections[alias] = [
                {**r, "date": r["date"].isoformat() if r.get("date") else None}
                for r in corr_log.to_dicts()
            ]

    pages: list[ProjectPageBundle] = []
    config_service = ConfigurationService(project_id)
    check_config = config_service.get_all_configurations()
    settings_dir = get_cache_path(project_id, "settings")
    for page_row in check_config.to_dicts() if not check_config.is_empty() else []:
        page_name_id = page_row["page_name"].lower().replace(" ", "_").replace("-", "_")
        pages.append(
            ProjectPageBundle(
                config=page_row,
                settings=_read_json(
                    settings_dir / f"page_{page_name_id}_settings.json"
                ),
                missing_settings=_read_json(
                    settings_dir / f"page_{page_name_id}_missing_settings.json"
                ),
            )
        )

    return ProjectConfigBundle(
        exported_from_project=project_name,
        exported_at=datetime.now().isoformat(timespec="seconds"),
        datasets=datasets,
        prep_steps=prep_steps,
        pages=pages,
        corrections=corrections,
    )


def parse_project_config(raw: bytes | str) -> ProjectConfigBundle:
    """Parse and validate an uploaded configuration file.

    Raises
    ------
    json.JSONDecodeError
        If the file isn't valid JSON.
    pydantic.ValidationError
        If the file isn't a valid configuration bundle.
    """
    data = json.loads(raw)
    return ProjectConfigBundle(**data)


# ============================================================================
# RESOLUTION - what the bundle can't carry, and needs from the user
# ============================================================================


def missing_credentials(project_id: str, bundle: ProjectConfigBundle) -> list[str]:
    """Distinct SurveyCTO servers referenced by the bundle with no stored credentials.

    Returns
    -------
    list[str]
        Server names sorted alphabetically, still needing a sign-in.
    """
    servers = {
        d.server for d in bundle.datasets if d.source == "SurveyCTO" and d.server
    }
    stored = list_stored_credentials(project_id).get("credentials", {})
    stored_servers = {cred.get("server") for cred in stored.values()}
    return sorted(servers - stored_servers)


def missing_local_files(bundle: ProjectConfigBundle) -> list[ImportSourceEntry]:
    """Local-storage datasets that need a file path re-supplied on this machine."""
    return [d for d in bundle.datasets if d.source == "local storage"]


def _stored_username_for_server(project_id: str, server: str) -> str | None:
    """Look up the username a credential was stored under for a server."""
    stored = list_stored_credentials(project_id).get("credentials", {})
    for cred in stored.values():
        if cred.get("server") == server:
            return cred.get("username")
    return None


# ============================================================================
# APPLY
# ============================================================================


@dataclass
class ConfigApplyResult:
    """Outcome of applying a project configuration bundle."""

    datasets_imported: list[str] = field(default_factory=list)
    datasets_skipped: list[ReapplyFailure] = field(default_factory=list)
    prep_failures: list[ReapplyFailure] = field(default_factory=list)
    pages_created: list[str] = field(default_factory=list)
    pages_skipped: list[ReapplyFailure] = field(default_factory=list)
    correction_failures: list[ReapplyFailure] = field(default_factory=list)


def _append_import_log_row(project_id: str, entry: dict) -> None:
    """Append one row to the project's import_log table."""
    import_log = duckdb_get_table(project_id, alias="import_log", db_name="logs")
    new_row = pl.DataFrame([entry])
    updated = (
        pl.concat([import_log, new_row], how="diagonal")
        if not import_log.is_empty()
        else new_row
    )
    duckdb_save_table(project_id, updated, alias="import_log", db_name="logs")


def _seed_prep_log(project_id: str, alias: str, steps: list[dict]) -> None:
    """Write bundled prep steps as the alias's prep_log, ready to be replayed.

    Only the ``prep_args`` column matters here - ``prep_apply_action`` reads
    it to rebuild the data, then rewrites the whole log (action, description,
    status) from what actually happened this time.
    """
    if not steps:
        return
    log_df = pl.DataFrame(
        {
            "action": [s.get("action", "") for s in steps],
            "description": ["" for _ in steps],
            "prep_args": [json.dumps(s) for s in steps],
            "action_index": [str(i) for i in range(len(steps))],
            "status": ["Successful" for _ in steps],
        }
    )
    duckdb_save_table(project_id, log_df, alias=f"prep_log_{alias}", db_name="logs")


def _seed_correction_log(project_id: str, alias: str, rows: list[dict]) -> None:
    """Write bundled corrections as the alias's correction log, ready to be replayed."""
    if not rows:
        return
    log_df = pl.DataFrame(rows)
    if log_df.schema.get("date") == pl.String:
        log_df = log_df.with_columns(pl.col("date").str.to_datetime(strict=False))
    duckdb_save_table(project_id, log_df, alias=f"corr_log_{alias}", db_name="logs")


def _write_page_settings(
    project_id: str, page_name: str, settings: dict, missing_settings: dict
) -> None:
    """Write a page's check settings JSON files."""
    page_name_id = page_name.lower().replace(" ", "_").replace("-", "_")
    settings_dir = get_cache_path(project_id, "settings")
    settings_dir.mkdir(parents=True, exist_ok=True)
    if settings:
        with open(settings_dir / f"page_{page_name_id}_settings.json", "w") as f:
            json.dump(settings, f)
    if missing_settings:
        with open(
            settings_dir / f"page_{page_name_id}_missing_settings.json", "w"
        ) as f:
            json.dump(missing_settings, f)


def _import_dataset(
    project_id: str, ds: ImportSourceEntry, local_file_paths: dict[str, str]
) -> tuple[bool, str | None]:
    """Import one dataset from the bundle.

    Returns
    -------
    tuple[bool, str | None]
        (True, None) on success, or (False, reason) if it was skipped.
    """
    if ds.source == "local storage":
        path = local_file_paths.get(ds.alias)
        if not path:
            return False, "No file path was provided"
        try:
            file_config = FileConfig(
                alias=ds.alias, filename=path, sheet_name=ds.sheet_name
            )
        except ValidationError as e:
            return False, str(e)
        _append_import_log_row(
            project_id,
            {
                "refresh": True,
                "load": True,
                "source": "local storage",
                "alias": file_config.alias,
                "filename": file_config.filename,
                "sheet_name": file_config.sheet_name or "",
                "server": "",
                "username": "",
                "form_id": "",
                "private_key": "",
                "save_to": "",
                "attachments": False,
            },
        )
        load_local_data(
            project_id, file_config.alias, file_config.filename, file_config.sheet_name
        )
        return True, None

    if ds.source == "SurveyCTO":
        username = (
            _stored_username_for_server(project_id, ds.server or "") or ds.username
        )
        if not ds.server or not username:
            return False, "No SurveyCTO credentials were provided for this server"
        form_config = FormConfig(
            alias=ds.alias,
            form_id=ds.form_id or "",
            server=ds.server,
            username=username,
            attachments=ds.attachments,
        )
        _append_import_log_row(
            project_id,
            {
                "refresh": True,
                "load": True,
                "source": "SurveyCTO",
                "alias": form_config.alias,
                "filename": "",
                "sheet_name": "",
                "server": form_config.server,
                "username": form_config.username or "",
                "form_id": form_config.form_id,
                "private_key": "",
                "save_to": "",
                "attachments": form_config.attachments,
            },
        )
        download_forms(project_id, [form_config])
        return True, None

    return False, f"Unknown import source: {ds.source}"


def apply_project_config(
    project_id: str,
    bundle: ProjectConfigBundle,
    local_file_paths: dict[str, str],
) -> ConfigApplyResult:
    """Apply a parsed configuration bundle to a new or existing project.

    Runs the same pipeline a person would run by hand: import each dataset,
    replay its prep steps, create each HFC page, then replay corrections. A
    dataset, page, or step that can't be applied is skipped and reported,
    not fatal to the rest of the bundle.

    Parameters
    ----------
    project_id : str
        The project to apply the configuration to. Must already exist.
    bundle : ProjectConfigBundle
        The parsed configuration.
    local_file_paths : dict[str, str]
        Alias -> file path, for every "local storage" dataset in the bundle.
        SurveyCTO credentials are looked up from the project's stored
        credentials instead, and must already be saved before calling this.

    Returns
    -------
    ConfigApplyResult
        What was imported, applied, created, or skipped (and why).
    """
    result = ConfigApplyResult()
    imported_aliases: set[str] = set()

    for ds in bundle.datasets:
        ok, reason = _import_dataset(project_id, ds, local_file_paths)
        if ok:
            imported_aliases.add(ds.alias)
            result.datasets_imported.append(ds.alias)
        else:
            result.datasets_skipped.append(
                ReapplyFailure(ds.alias, reason or "Unknown error")
            )

    for alias, steps in bundle.prep_steps.items():
        if alias not in imported_aliases:
            continue
        _seed_prep_log(project_id, alias, steps)
        result.prep_failures.extend(prep_apply_action(project_id, alias))

    config_service = ConfigurationService(project_id)
    for page in bundle.pages:
        page_name = page.config.get("page_name", "")
        if config_service.page_name_exists(page_name):
            result.pages_skipped.append(
                ReapplyFailure(page_name, "A page with this name already exists")
            )
            continue
        survey_data_name = page.config.get("survey_data_name")
        if survey_data_name not in imported_aliases:
            result.pages_skipped.append(
                ReapplyFailure(
                    page_name, f"Dataset '{survey_data_name}' was not imported"
                )
            )
            continue
        try:
            check_config = CheckConfiguration(**page.config)
        except ValidationError as e:
            result.pages_skipped.append(ReapplyFailure(page_name, str(e)))
            continue
        config_service.add_configuration(check_config, rerun=False)
        _write_page_settings(
            project_id, page_name, page.settings, page.missing_settings
        )
        result.pages_created.append(page_name)

    for alias, rows in bundle.corrections.items():
        if alias not in imported_aliases:
            continue
        _seed_correction_log(project_id, alias, rows)
        result.correction_failures.extend(
            CorrectionProcessor(project_id).refresh_corrected_data(alias)
        )

    config_service.sync_output_view_files()
    return result


# ============================================================================
# UI COMPONENTS
# ============================================================================


def _count_label(count: int, noun: str) -> str:
    """Format a "N noun(s)" label, or "No nouns" when the count is zero."""
    if count == 0:
        return f"No {noun}s"
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"


def _render_config_summary(bundle: ProjectConfigBundle) -> None:
    """Render the parsed bundle's contents as an ordered checklist.

    One line per layer, in the order it will be applied, with a check when
    the bundle actually has that layer and an X when it doesn't.
    """
    import streamlit as st

    prep_count = sum(len(v) for v in bundle.prep_steps.values())
    correction_count = sum(len(v) for v in bundle.corrections.values())

    st.markdown("**Project loaded.**")

    checklist = [
        (True, f"Project info — *{bundle.exported_from_project}*"),
        (len(bundle.datasets) > 0, _count_label(len(bundle.datasets), "dataset")),
        (prep_count > 0, _count_label(prep_count, "prep step")),
        (len(bundle.pages) > 0, _count_label(len(bundle.pages), "HFC page")),
        (correction_count > 0, _count_label(correction_count, "correction")),
    ]
    for available, label in checklist:
        icon = ":material/check_circle:" if available else ":material/cancel:"
        st.markdown(f"{icon} {label}")


def _render_config_resolution(
    project_id: str, bundle: ProjectConfigBundle
) -> dict[str, str]:
    """Render credential and file-path inputs for what the bundle can't carry.

    Returns
    -------
    dict[str, str]
        Alias -> resolved file path, for local-storage datasets that now
        have a non-empty path entered.
    """
    import streamlit as st

    for server in missing_credentials(project_id, bundle):
        with st.container(border=True):
            st.markdown(f'**SurveyCTO &middot; server "{server}"**')
            SurveyCTOUI(project_id).render_login_form()

    local_paths: dict[str, str] = {}
    for ds in missing_local_files(bundle):
        hint = f" (expected {ds.filename})" if ds.filename else ""
        path = st.text_input(
            f'Local file for "{ds.alias}"{hint}',
            key=f"cfg_local_path_{ds.alias}",
            placeholder="Full path, e.g. C:/data/survey.dta",
        )
        if path:
            local_paths[ds.alias] = path

    return local_paths


def _render_config_apply_result(result: ConfigApplyResult) -> None:
    """Render a summary of what applying a configuration did."""
    import streamlit as st

    st.success(
        f"Imported {len(result.datasets_imported)} dataset(s) and created "
        f"{len(result.pages_created)} HFC page(s)."
    )
    warn_reapply_failures(
        result.datasets_skipped, "Some datasets could not be imported"
    )
    warn_reapply_failures(
        result.prep_failures, "Some prep steps could not be reapplied"
    )
    warn_reapply_failures(result.pages_skipped, "Some HFC pages could not be created")
    warn_reapply_failures(
        result.correction_failures, "Some corrections could not be reapplied"
    )


def render_config_resolution_and_apply(
    project_id: str,
    bundle: ProjectConfigBundle | None,
    on_complete: Callable[[], None],
) -> None:
    """Render the resolve-then-apply steps for an already-parsed bundle.

    Streamlit does not allow opening a dialog from within another dialog, so
    this renders inline into whatever dialog is already open - the
    standalone "Set Up Project From a Configuration File" dialog after its
    own upload step, or the "New Project" dialog directly, since that one
    already has its own uploader.

    Parameters
    ----------
    project_id : str
        The (already-created) project to apply the configuration to.
    bundle : ProjectConfigBundle, optional
        The parsed configuration to resolve and apply. Only read before an
        apply has happened yet - once `apply_project_config` has run, the
        stored result is shown instead and this is ignored.
    on_complete : callable
        Called after the user dismisses a completed apply, to navigate away.
    """
    import streamlit as st

    result_key = f"cfg_result_{project_id}"
    if result_key in st.session_state:
        _render_config_apply_result(st.session_state[result_key])
        if st.button("Continue", type="primary", width="stretch"):
            del st.session_state[result_key]
            on_complete()
        return

    st.caption(f"Exported from **{bundle.exported_from_project}**")
    _render_config_summary(bundle)
    st.divider()

    local_paths = _render_config_resolution(project_id, bundle)

    servers_needed = missing_credentials(project_id, bundle)
    files_needed = [
        ds.alias for ds in missing_local_files(bundle) if ds.alias not in local_paths
    ]
    ready = not servers_needed and not files_needed

    if not ready:
        st.caption(
            f"Resolve the items above before continuing "
            f"({len(servers_needed)} credential(s), "
            f"{len(files_needed)} file(s) remaining)."
        )

    if st.button(
        "Import, Prep & Configure",
        type="primary",
        width="stretch",
        disabled=not ready,
        key=f"apply_config_{project_id}",
    ):
        with st.spinner("Setting up your project..."):
            result = apply_project_config(project_id, bundle, local_paths)
        st.session_state[result_key] = result
        # scope="fragment": a dialog is implemented as a fragment, and a
        # plain (app-scoped) rerun exits that fragment, closing the dialog
        # instead of just refreshing its content to show the result.
        st.rerun(scope="fragment")


def render_project_config_wizard(
    project_id: str, project_name: str, on_complete: Callable[[], None]
) -> None:
    """Render the standalone "set up project from a configuration file" dialog.

    Used by "Update from configuration" on an existing project, which has no
    bundle yet: asks for the file itself, then hands off to
    `render_config_resolution_and_apply`. The New Project dialog already has
    its own uploader and calls that function directly instead, since a
    dialog can't open another dialog from within itself.

    Parameters
    ----------
    project_id : str
        The (already-created) project to apply the configuration to.
    project_name : str
        Display name, used in the dialog heading only.
    on_complete : callable
        Called after the user dismisses a completed apply, to navigate away.
    """
    import streamlit as st

    @st.dialog(title="Set Up Project From a Configuration File", width="large")
    def _dialog() -> None:
        st.caption(f"Applying to **{project_name}**")

        result_key = f"cfg_result_{project_id}"
        if result_key not in st.session_state:
            uploaded = st.file_uploader(
                "Configuration file", type=["json"], key="cfg_upload"
            )
            if not uploaded:
                st.info(
                    "Upload a DataSure configuration file exported from another project."
                )
                return

            try:
                bundle = parse_project_config(uploaded.getvalue())
            except (json.JSONDecodeError, ValidationError) as e:
                st.error(f"This doesn't look like a valid configuration file: {e}")
                return
        else:
            bundle = None  # unused: the stored apply result takes over instead

        render_config_resolution_and_apply(project_id, bundle, on_complete)

    _dialog()
