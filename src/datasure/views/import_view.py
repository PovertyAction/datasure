import polars as pl
import streamlit as st

from datasure.connectors.local import load_local_data
from datasure.connectors.scto import (
    FormConfig,
    download_forms,
)
from datasure.processing.corrections import CorrectionProcessor
from datasure.processing.prep import prep_apply_action
from datasure.utils.dataset_list import (
    LOCAL_SOURCE,
    SOURCE_FILTERS,
    SURVEYCTO_SOURCE,
    build_dataset_list,
    filter_rows,
)
from datasure.utils.duckdb_utils import (
    duckdb_get_aliases,
    duckdb_get_imported_datasets,
    duckdb_get_table,
    duckdb_table_exists,
)
from datasure.utils.import_log import dataset_entry, get_load_info, record_load
from datasure.utils.import_ui import (
    NOTICE_SCOPE,
    open_add_dialog,
    open_edit_dialog,
    open_remove_dialog,
    project_name,
    render_connections,
    render_dataset_row,
)
from datasure.utils.names import STORED_NAME
from datasure.utils.navigations_utils import (
    add_demo_navigation,
    demo_callout,
    demo_sidebar_help,
    page_navigation,
    show_demo_next_action,
)
from datasure.utils.onboarding_utils import (
    DEMO_PROJECT_ID,
    ImportDemoInfo,
    is_demo_project,
)
from datasure.utils.reapply_utils import ReapplyFailure, warn_reapply_failures
from datasure.utils.ui_utils import (
    metric_row,
    page_header,
    section_header,
    show_queued_notices,
)

# --- CONFIGURE PAGE --- #
# Page title and layout are set globally in app.py via st.set_page_config; the
# per-page title is supplied by st.Page(title=...) in the navigation menu.

# Add demo navigation and guidance
add_demo_navigation("import_view.py", step=2)
demo_sidebar_help()

# --- define project ID --- #
project_id = st.session_state.st_project_id

if not project_id:
    page_header("Import Data", divider=False)
    st.info(
        "Please select a project from the Start page to import data. "
        "You can also create a new project from the Start page."
    )
    st.stop()

# add session state for raw dataset list
if "st_raw_dataset_list" not in st.session_state:
    st.session_state.st_raw_dataset_list = duckdb_get_aliases(project_id, to_load=True)

# Demo-specific setup
if (
    is_demo_project()
    and project_id == DEMO_PROJECT_ID
    and "demo_survey" not in st.session_state.st_raw_dataset_list
):
    # Ensure demo datasets are in the list
    st.session_state.st_raw_dataset_list.extend(["demo_survey", "demo_backcheck"])

if "st_prep_dataset_list" not in st.session_state:
    st.session_state.st_prep_dataset_list = None


# --- Load raw dataset list from import configurations --- #
def load_raw_datasets(project_id: str) -> None:
    """Load raw dataset list from the cache file.

    PARAMS:
    -------
    project_id: str : project ID

    Returns
    -------
    None
    """
    import_log = _get_filtered_import_log(project_id)

    if import_log.is_empty():
        st.error("No import configurations found. Please add import configurations.")
        return

    _process_import_log(project_id, import_log)


def _get_filtered_import_log(project_id: str) -> pl.DataFrame:
    """Get import log filtered by load flag."""
    import_log = duckdb_get_table(
        project_id=project_id,
        alias="import_log",
        db_name="logs",
    )
    return import_log.filter(pl.col("load"))


def _process_import_log(project_id: str, import_log: pl.DataFrame) -> None:
    """Process all rows in import log with status updates."""
    all_failures: list[ReapplyFailure] = []
    with st.status("Loading datasets ...", expanded=True) as status:
        for row in import_log.iter_rows(named=True):
            all_failures.extend(_process_single_import(project_id, row))
        status.update(
            label="Data loaded successfully!", state="complete", expanded=True
        )
    warn_reapply_failures(
        all_failures,
        "Some downstream data could not be fully reapplied after import",
    )


def _process_single_import(project_id: str, row: dict) -> list[ReapplyFailure]:
    """Process a single import configuration row."""
    failures: list[ReapplyFailure] = []
    if row["refresh"]:
        _load_dataset_by_source(project_id, row)
        _record_load(project_id, row["alias"])
        failures = _refresh_downstream_data(project_id, row["alias"])

    _add_to_session_state(row["alias"])
    return failures


def _record_load(project_id: str, alias: str) -> None:
    """Note the load time of a refreshed dataset that has imported data."""
    if duckdb_table_exists(project_id, alias=alias, db_name="raw"):
        record_load(project_id, alias)


def _refresh_downstream_data(project_id: str, alias: str) -> list[ReapplyFailure]:
    """Rebuild prep and corrected data after a raw dataset refresh.

    Without this, the Prep and Correction pages keep showing data derived
    from the previous import, since both stages are cached copies that are
    otherwise only rebuilt when their own logs change.
    """
    failures: list[ReapplyFailure] = []

    if duckdb_table_exists(project_id, alias=alias, db_name="prep"):
        failures.extend(prep_apply_action(project_id, alias))

    failures.extend(
        CorrectionProcessor(project_id).refresh_existing_corrected_data(alias)
    )

    return failures


def _load_dataset_by_source(project_id: str, row: dict) -> None:
    """Load dataset based on source type."""
    if row["source"] == LOCAL_SOURCE:
        _load_from_local_storage(project_id, row)
    elif row["source"] == SURVEYCTO_SOURCE:
        _load_from_surveycto(project_id, row)


def _load_from_local_storage(project_id: str, row: dict) -> None:
    """Load dataset from local storage."""
    load_local_data(
        project_id=project_id,
        alias=row["alias"],
        filename=row["filename"],
        sheet_name=row["sheet_name"] if row["sheet_name"] else None,
    )


def _load_from_surveycto(project_id: str, row: dict) -> None:
    """Load dataset from SurveyCTO."""
    form_configs = _create_form_config(row)
    download_forms(
        project_id=project_id,
        form_configs=[form_configs],
    )


def _create_form_config(row: dict) -> FormConfig:
    """Create FormConfig from import log row."""
    return FormConfig.model_validate(
        {
            "alias": row["alias"],
            "form_id": row["form_id"],
            "server": row["server"],
            "username": row["username"] if row["username"] else None,
            "private_key": row["private_key"] if row["private_key"] else None,
            "save_to": row["save_to"] if row["save_to"] else None,
            "attachments": row["attachments"],
            "refresh": row["refresh"],
        },
        # Aliases saved before the name rule still load.
        context=STORED_NAME,
    )


def _add_to_session_state(alias: str) -> None:
    """Add alias to session state if not already present."""
    if alias not in st.session_state.st_raw_dataset_list:
        st.session_state.st_raw_dataset_list.append(alias)

        # Demo success message
        if is_demo_project():
            demo_callout(ImportDemoInfo.get_info_message("add_to_session_info"))


def _percent_missing(data: pl.DataFrame) -> float:
    """Return the share of cells in `data` that are null, as a percentage.

    A dataset with no rows or no columns has no cells, so it reports 0%
    rather than dividing by zero.
    """
    total_cells = data.height * data.width
    if total_cells == 0:
        return 0.0
    return data.null_count().sum_horizontal().item() / total_cells * 100


def _datasets_caption(count: int) -> str:
    return f"{count} dataset" if count == 1 else f"{count} datasets"


def _edit_dataset(alias: str) -> None:
    entry = dataset_entry(project_id, alias)
    if entry:
        open_edit_dialog(project_id, entry)


def _after_remove(_alias: str) -> None:
    st.session_state.st_raw_dataset_list = duckdb_get_aliases(project_id)


def _remove_dataset(alias: str) -> None:
    open_remove_dialog(project_id, alias, on_removed=_after_remove)


def _render_preview(preview_options: list[str]) -> None:
    """Preview one imported dataset: its metrics, its data and its dictionary."""
    section_header("Preview", icon=":material/table_view:")

    if is_demo_project():
        demo_callout(ImportDemoInfo.get_info_message("preview_data_info"))

    selected_dataset = st.selectbox(
        "Dataset",
        options=sorted(preview_options),
        key="imported_data_select",
        width=320,
    )
    preview_data = duckdb_get_table(project_id, alias=selected_dataset, db_name="raw")

    metric_row(
        [
            (
                "Rows",
                f"{preview_data.height:,}",
                "Number of rows in the imported dataset.",
            ),
            (
                "Columns",
                f"{preview_data.width:,}",
                "Number of columns in the imported dataset.",
            ),
            (
                "Missing Data",
                f"{_percent_missing(preview_data):.2f}%",
                "Percentage of missing data in the imported dataset.",
            ),
        ]
    )

    data_tab, dictionary_tab = st.tabs(["Data", "Dictionary"])
    with data_tab:
        if preview_data.is_empty():
            st.info(
                f"**{selected_dataset}** has no rows yet. If it comes from "
                "SurveyCTO, the form may have no submissions."
            )
        else:
            st.dataframe(preview_data, width="stretch")
    with dictionary_tab:
        st.info("No dictionary yet.", icon=":material/menu_book:")


# --- Header --- #
import_log = duckdb_get_table(project_id, alias="import_log", db_name="logs")
dataset_count = 0 if import_log.is_empty() else import_log.height

with st.container(horizontal=True, vertical_alignment="bottom"):
    with st.container(gap=None):
        page_header(
            "Import Data",
            f"{project_name(project_id)} · {_datasets_caption(dataset_count)}",
            divider=False,
        )
    if st.button(
        "Add dataset",
        type="primary",
        icon=":material/add:",
        key="add_dataset_button",
    ):
        open_add_dialog(project_id)

show_queued_notices(NOTICE_SCOPE)

# --- Connections --- #
if is_demo_project():
    demo_callout(ImportDemoInfo.get_info_message("surveycto_info"))
render_connections(project_id)

if import_log.is_empty():
    st.info(
        "This project has no datasets yet. If your data is on SurveyCTO, "
        "connect a server under **Connections** first. Then click "
        "**Add dataset** to add a form or a file on this computer.",
        icon=":material/info:",
    )
else:
    # --- Dataset rows --- #
    # Filled after Load data runs below, so rows show the new load times.
    rows_area = st.container()

    if is_demo_project():
        demo_callout(
            "Your demo data is already loaded. You do not need to click "
            "**Load data**. Scroll down to **Preview** to continue."
        )
    with st.container(horizontal=True, vertical_alignment="center"):
        load_btn = st.button(
            "Load data",
            type="primary",
            icon=":material/download:",
            key="load_data_key",
            # With nothing marked Load, the summary beside it says so.
            disabled=not import_log["load"].any(),
        )
        summary_slot = st.empty()

    if load_btn:
        load_raw_datasets(project_id)
        st.session_state.st_prep_dataset_list = duckdb_get_imported_datasets(project_id)
        st.success(
            "Data loaded. Preview it below, then prepare it on the Prep page.",
            icon=":material/check_circle:",
        )

    aliases = import_log["alias"].to_list()
    dataset_list = build_dataset_list(import_log, get_load_info(project_id, aliases))
    summary_slot.caption(dataset_list.load_summary)

    with rows_area:
        rows = dataset_list.rows
        if dataset_list.show_source_filter:
            source_filter = st.segmented_control(
                "Source",
                options=SOURCE_FILTERS,
                default=SOURCE_FILTERS[0],
                key="import_source_filter",
                label_visibility="collapsed",
            )
            rows = filter_rows(rows, source_filter)
        for row in rows:
            render_dataset_row(
                project_id, row, on_edit=_edit_dataset, on_remove=_remove_dataset
            )

    # --- Preview imported data --- #
    preview_options = duckdb_get_imported_datasets(project_id)
    if preview_options:
        _render_preview(preview_options)

        if is_demo_project():
            st.divider()
            show_demo_next_action(2, "st_prep_data_page", "Prepare Your Data")

# Previous and next pages (import, prep) - only for non-demo projects
if not is_demo_project():
    page_navigation(
        next={
            "page_name": st.session_state.st_prep_data_page,
            "label": "Next: Prepare Data →",
        }
    )
