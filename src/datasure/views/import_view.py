import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field

import polars as pl
import streamlit as st

from datasure.connectors.local import import_local_file
from datasure.connectors.scto import (
    FormConfig,
    FormDefinitionNotSavedError,
    SurveyCTOClient,
)
from datasure.processing.corrections import CorrectionProcessor
from datasure.processing.prep import prep_apply_action
from datasure.utils.dataset_list import (
    LOCAL_SOURCE,
    SOURCE_FILTERS,
    SURVEYCTO_SOURCE,
    LoadResult,
    build_dataset_list,
    filter_rows,
    load_outcome,
    result_line,
)
from datasure.utils.duckdb_utils import (
    duckdb_get_aliases,
    duckdb_get_imported_datasets,
    duckdb_get_table,
    duckdb_row_counts,
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

logger = logging.getLogger(__name__)

# --- CONFIGURE PAGE --- #
# Page title and layout are set globally in app.py via st.set_page_config; the
# per-page title is supplied by st.Page(title=...) in the navigation menu.

# Add demo navigation; its sidebar help is added below, once no load is running.
add_demo_navigation("import_view.py", step=2)

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


def _datasets_caption(count: int) -> str:
    return f"{count} dataset" if count == 1 else f"{count} datasets"


# --- Load raw dataset list from import configurations --- #
def load_raw_datasets(
    project_id: str,
) -> tuple[list[LoadResult], list[ReapplyFailure]]:
    """Load the datasets marked Load, refreshing those marked Refresh.

    Returns one result per dataset, empty when nothing is marked Load, and
    the downstream steps that could not be reapplied.
    """
    import_log = _get_filtered_import_log(project_id)

    if import_log.is_empty():
        return [], []

    return _process_import_log(project_id, import_log)


def _get_filtered_import_log(project_id: str) -> pl.DataFrame:
    """Get import log filtered by load flag."""
    import_log = duckdb_get_table(
        project_id=project_id,
        alias="import_log",
        db_name="logs",
    )
    return import_log.filter(pl.col("load"))


def _process_import_log(
    project_id: str, import_log: pl.DataFrame
) -> tuple[list[LoadResult], list[ReapplyFailure]]:
    """Load each dataset, showing which one is loading and how each went."""
    rows = list(import_log.iter_rows(named=True))
    total = len(rows)
    results: list[LoadResult] = []
    all_failures: list[ReapplyFailure] = []
    with st.status(f"Loading {_datasets_caption(total)}...", expanded=True) as status:
        progress = st.progress(0.0)
        for index, row in enumerate(rows):
            prefix = f"Loading {index + 1} of {total}: {row['alias']}"

            def report(stage: str, prefix: str = prefix) -> None:
                status.update(label=f"{prefix} · {stage}")

            progress.progress(index / total, text=prefix)
            result, failures = _process_single_import(project_id, row, report)
            results.append(result)
            all_failures.extend(failures)
            st.markdown(result_line(result))
        progress.empty()
        label, state = load_outcome(results)
        # Collapse when all went well; the rows above show the new loads.
        status.update(label=label, state=state, expanded=state == "error")
    return results, all_failures


# --- Load data lock --- #
# Load data runs in a script run of its own. Clicking anything (a page in the
# menu, a widget) starts a new run, which stops the load partway through a
# dataset. So the button only sets this flag; while it is set, app.py hides
# the page menu and this page shows only the load progress. The outcome is
# kept in session state across the rerun that brings the full page back.
_LOAD_RUNNING_KEY = "st_import_running"
_LOAD_OUTCOME_KEY = "import_load_outcome"


@dataclass
class _LoadOutcome:
    """How the last Load data went, shown once after the page comes back."""

    results: list[LoadResult] = field(default_factory=list)
    failures: list[ReapplyFailure] = field(default_factory=list)
    error: str | None = None


def _start_load() -> None:
    """Load data callback: lock the app on this page for the next run."""
    st.session_state[_LOAD_RUNNING_KEY] = True


def _load_running() -> bool:
    return bool(st.session_state.get(_LOAD_RUNNING_KEY, False))


def _run_locked_load(project_id: str) -> None:
    """Run Load data, then always unlock and rerun to bring the page back.

    An unexpected error is logged and reported after the rerun rather than
    raised, so the app is never left on a page without its menu.
    """
    try:
        results, failures = load_raw_datasets(project_id)
        st.session_state.st_prep_dataset_list = duckdb_get_imported_datasets(project_id)
        outcome = _LoadOutcome(results=results, failures=failures)
    except Exception as e:
        # UI boundary: report the failure on the page and keep the traceback.
        logger.exception("Load data failed")
        outcome = _LoadOutcome(error=str(e) or type(e).__name__)
    finally:
        st.session_state[_LOAD_RUNNING_KEY] = False
    st.session_state[_LOAD_OUTCOME_KEY] = outcome
    st.rerun()


def _show_load_outcome() -> None:
    """Show, once, how the last Load data went."""
    outcome = st.session_state.pop(_LOAD_OUTCOME_KEY, None)
    if outcome is None:
        return
    if outcome.error:
        st.error(
            f"Load data stopped: {outcome.error}. Datasets loaded before the "
            "error are kept. Click **Load data** to try again.",
            icon=":material/error:",
        )
        return
    if not outcome.results:
        st.error("No import configurations found. Please add import configurations.")
        return
    label, state = load_outcome(outcome.results)
    with st.status(label, state=state, expanded=state == "error"):
        for result in outcome.results:
            st.markdown(result_line(result))
    warn_reapply_failures(
        outcome.failures,
        "Some downstream data could not be fully reapplied after import",
    )
    if all(result.ok for result in outcome.results):
        st.success(
            "Data loaded. Preview it below, then prepare it on the Prep page.",
            icon=":material/check_circle:",
        )


def _no_report(_stage: str) -> None:
    """Default stage reporter: say nothing."""


def _process_single_import(
    project_id: str, row: dict, report: Callable[[str], None] = _no_report
) -> tuple[LoadResult, list[ReapplyFailure]]:
    """Load one dataset; return how it went and any steps not reapplied.

    A dataset that fails to load is reported and skipped, so the others
    still load, and its imported copy is left as it was. A failure after the
    raw import (bookkeeping, rebuilding prep and corrections) is reported as
    a problem on a loaded dataset, and doesn't stop the batch either.
    """
    alias = row["alias"]
    refreshed = bool(row["refresh"]) and row["source"] in _LOADERS
    failures: list[ReapplyFailure] = []
    problems: list[str] = []
    error = None
    new_rows = None
    started = time.monotonic()
    if refreshed:
        report(_STAGE_LABELS[row["source"]])
        try:
            new_rows = _load_dataset_by_source(project_id, row)
        except FormDefinitionNotSavedError as e:
            # Raw already holds the new data: carry on so downstream data
            # is rebuilt from it, and say what wasn't saved.
            logger.exception("Form definition not saved for dataset %s", alias)
            new_rows = e.new_rows
            problems.append(str(e))
        except Exception as e:
            # UI boundary: one failed dataset must not stop the batch, but
            # the traceback has to land in the logs.
            logger.exception("Failed to load dataset %s", alias)
            error = str(e) or type(e).__name__
        if error is None:
            report("reapplying prep and corrections")
            rebuild_failures, rebuild_problem = _after_raw_import(project_id, alias)
            failures = rebuild_failures
            if rebuild_problem:
                problems.append(rebuild_problem)

    _add_to_session_state(alias)
    result = LoadResult(
        alias=alias,
        source=row["source"],
        refreshed=refreshed,
        error=error,
        rows=_raw_row_count(project_id, alias),
        new_rows=new_rows if row["source"] == SURVEYCTO_SOURCE else None,
        seconds=time.monotonic() - started,
        reapply_failures=len(failures),
        problems=tuple(problems),
    )
    return result, failures


def _after_raw_import(
    project_id: str, alias: str
) -> tuple[list[ReapplyFailure], str | None]:
    """Record the load and rebuild downstream data after a raw import.

    Returns the steps not reapplied, and a description of the failure when
    this work couldn't finish.
    """
    try:
        _record_load(project_id, alias)
        return _refresh_downstream_data(project_id, alias), None
    except Exception as e:
        # UI boundary: raw has loaded, so report the rest as a problem on
        # this dataset instead of stopping the batch.
        logger.exception("Failed to rebuild prep and corrections for %s", alias)
        detail = str(e) or type(e).__name__
        return [], f"prep and corrections not rebuilt: {detail}"


def _raw_row_count(project_id: str, alias: str) -> int | None:
    """Return a dataset's imported row count, or ``None`` if it can't be read."""
    try:
        return duckdb_row_counts(project_id, [alias], "raw").get(alias)
    except Exception:
        # UI boundary: a count is only shown, never worth stopping the batch.
        logger.exception("Could not count the rows of %s", alias)
        return None


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


def _load_dataset_by_source(project_id: str, row: dict) -> int | None:
    """Load a dataset from its source; return the rows it imported or added.

    Raises when the dataset can't be loaded. Other sources (the demo
    datasets) aren't loaded and return ``None``.
    """
    loader = _LOADERS.get(row["source"])
    return loader(project_id, row) if loader else None


def _load_from_local_storage(project_id: str, row: dict) -> int:
    """Read a dataset's local file; return its row count."""
    return import_local_file(
        project_id=project_id,
        alias=row["alias"],
        filename=row["filename"],
        sheet_name=row["sheet_name"] if row["sheet_name"] else None,
    )


def _load_from_surveycto(project_id: str, row: dict) -> int:
    """Download a dataset's SurveyCTO form; return how many rows it added."""
    return SurveyCTOClient(project_id).import_data(_create_form_config(row))


_LOADERS = {
    LOCAL_SOURCE: _load_from_local_storage,
    SURVEYCTO_SOURCE: _load_from_surveycto,
}
_STAGE_LABELS = {
    LOCAL_SOURCE: "reading the file",
    SURVEYCTO_SOURCE: "downloading from SurveyCTO",
}


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


# --- Load data in progress --- #
# Only the progress renders: any other widget could start a new run.
if _load_running():
    page_header("Import Data", project_name(project_id), divider=False)
    st.info(
        "Loading data. Stay on this page: the menu comes back when the load finishes.",
        icon=":material/hourglass_top:",
    )
    _run_locked_load(project_id)

demo_sidebar_help()

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
        st.button(
            "Load data",
            type="primary",
            icon=":material/download:",
            key="load_data_key",
            on_click=_start_load,
            # With nothing marked Load, the summary beside it says so.
            disabled=not import_log["load"].any(),
        )
        summary_slot = st.empty()

    _show_load_outcome()

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
