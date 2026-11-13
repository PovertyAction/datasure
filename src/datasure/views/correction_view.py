"""
Correction view for making data corrections based on identified issues.

This module provides an interactive interface for applying, tracking, and managing
data corrections across multiple datasets. Corrections are logged and can be
removed or modified as needed.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import polars as pl
import streamlit as st
from pydantic import BaseModel, Field

from datasure.checks.backchecks.models import backcheck_id_columns
from datasure.checks.gpschecks.review import GPS_CHECK_TYPE
from datasure.processing.correction_log import (
    CORRECTION_ACTIONS,
    CORRECTIONS_PAGE_SOURCE,
    HARD_SEVERITY,
    Action,
    ensure_log_columns,
)
from datasure.processing.corrections import CorrectionProcessor
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.correction_form import (
    get_current_value,
    render_correction_form,
)
from datasure.utils.correction_form import (
    render_value_input_widget as render_shared_value_input_widget,
)
from datasure.utils.dataframe_utils import TableState, get_table_state
from datasure.utils.duckdb_utils import (
    duckdb_get_table,
    duckdb_table_exists,
    name_id,
)
from datasure.utils.nav_ui import (
    LAST_CHECK_PAGE,
    PROJECT_VIEW_FILE,
    draw_nav,
    guarded_status,
    project_nav_key,
    render_empty_state,
    resolve_selection,
    run_guarded,
    select_nav_item,
)
from datasure.utils.navigation import READY, CheckStatus, NavItem, StatusResult
from datasure.utils.navigations_utils import (
    add_demo_navigation,
    demo_sidebar_help,
    page_navigation,
)
from datasure.utils.reapply_utils import highlight_status, warn_reapply_failures
from datasure.utils.settings_utils import (
    get_check_config_settings,
    page_settings_file,
)
from datasure.utils.ui_utils import (
    confirm_dialog,
    metric_row,
    page_header,
    row_styler,
    section_header,
    styled_dataframe,
)
from datasure.utils.view_state import (
    ViewState,
    bind_widget,
    forget_remembered,
    remembered,
    reset_filters_button,
    save_selection,
    saved_selection,
)

# The check page navigation's session state key (before ``project_nav_key``)
# and URL query parameter, and
# the settings file holding the remembered page, dataset choice and filters
# (its view_state section).
CORRECTIONS_NAV_KEY = "corrections_nav"
PAGE_PARAM = "page"
CORRECTIONS_SETTINGS_FILE = "correction_view_settings.json"


class TabConfig(BaseModel):
    """Configuration for one check page on the Corrections page."""

    page_name: str = Field(..., description="Name of the page/check")
    survey_data_name: str = Field(..., description="Name of the survey data alias")
    survey_key: str = Field(..., description="Name of the survey KEY column")
    survey_id: str | None = Field(
        None, description="Name of the survey ID column, if configured"
    )
    backcheck_data_name: str | None = Field(
        None, description="Name of the backcheck data alias, if configured"
    )
    backcheck_key: str | None = Field(
        None, description="Name of the backcheck KEY column"
    )
    backcheck_id: str | None = Field(
        None, description="Name of the backcheck ID column, if configured"
    )


SURVEY_DATA = "Survey data"
BACKCHECK_DATA = "Backcheck data"

# Backcheck data measures data quality, so the only backcheck corrections are
# fixing an ID and removing a record, as on the duplicate cards.
BACKCHECK_ACTIONS = (Action.MODIFY_VALUE, Action.REMOVE_ROW)


@dataclass(frozen=True)
class CorrectionDataset:
    """A dataset a Corrections check page corrects, and what it may change.

    Attributes
    ----------
    label : str
        `SURVEY_DATA` or `BACKCHECK_DATA`, shown on the switcher.
    alias : str
        The data alias whose corrected table and log are used.
    key_col : str
        The KEY column.
    id_col : str | None
        The ID column, if configured.
    actions : tuple[Action, ...]
        The correction actions offered.
    column : str | None
        The only column "modify value" may change, or None for any column.
    key_namespace : str | int
        Suffix for the dataset's widget keys, unique across check pages and datasets.
    """

    label: str
    alias: str
    key_col: str
    id_col: str | None
    actions: tuple[Action, ...]
    column: str | None
    key_namespace: str | int


def correction_datasets(
    config: TabConfig, tab_index: int = 0
) -> list[CorrectionDataset]:
    """Return the datasets a check page corrects: survey data, then any backcheck data.

    On backcheck data only the ID can be modified, and rows removed; with no
    ID column configured, rows can only be removed.
    """
    datasets = [
        CorrectionDataset(
            label=SURVEY_DATA,
            alias=config.survey_data_name,
            key_col=config.survey_key,
            id_col=config.survey_id,
            actions=CORRECTION_ACTIONS,
            column=None,
            key_namespace=tab_index,
        )
    ]
    if config.backcheck_data_name:
        id_col = config.backcheck_id
        datasets.append(
            CorrectionDataset(
                label=BACKCHECK_DATA,
                alias=config.backcheck_data_name,
                key_col=config.backcheck_key or config.survey_key,
                id_col=id_col,
                actions=BACKCHECK_ACTIONS if id_col else (Action.REMOVE_ROW,),
                column=id_col,
                key_namespace=f"{tab_index}_backcheck",
            )
        )
    return datasets


def render_value_input_widget(
    column: str,
    col_dtype: pl.DataType,
    current_value: Any,
    tab_index: int,
) -> tuple[Any, str | None]:
    """
    Render the new-value input for a column on the Corrections page.

    Parameters
    ----------
    column : str
        The column name being modified.
    col_dtype : pl.DataType
        The column data type.
    current_value : Any
        The current value in the column.
    tab_index : int
        The check page index for unique widget keys.

    Returns
    -------
    tuple[Any, str | None]
        A tuple of (new_value, error_message).
    """
    return render_shared_value_input_widget(column, col_dtype, current_value, tab_index)


def load_hfc_config(project_id: str) -> tuple[pl.DataFrame, list[str]]:
    """
    Load HFC configuration data and extract page list.

    Parameters
    ----------
    project_id : str
        The project identifier.

    Returns
    -------
    tuple[pl.DataFrame, list[str]]
        A tuple containing the HFC configuration logs and list of page names.

    """
    hfc_config_logs = duckdb_get_table(
        project_id=project_id, alias="check_config", db_name="logs"
    )
    if hfc_config_logs.is_empty():
        return hfc_config_logs, []
    return hfc_config_logs, hfc_config_logs["page_name"].to_list()


def get_key_options(data: pl.DataFrame, key_col: str) -> list:
    """
    Extract unique key values from data for correction selection.

    Parameters
    ----------
    data : pl.DataFrame
        The dataset containing the key column.
    key_col : str
        The name of the key column.

    Returns
    -------
    list
        List of unique key values.
    """
    return data.select(key_col).unique(maintain_order=True).to_series().to_list()


def load_tab_config(project_id: str, tab_index: int) -> TabConfig | None:
    """
    Load the configuration of one check page.

    Parameters
    ----------
    project_id : str
        The project identifier.
    tab_index : int
        The check page's position in the check configuration.

    Returns
    -------
    TabConfig | None
        Check page configuration or None if loading fails.
    """
    page_config = get_check_config_settings(
        project_id=project_id,
        page_row_index=tab_index,
    )

    backcheck_key = backcheck_id = None
    backcheck_data_name = page_config.get("backcheck_data_name")
    if backcheck_data_name:
        backcheck_key, backcheck_id = backcheck_id_columns(
            str(page_settings_file(project_id, page_config.get("page_name"))),
            page_config.get("survey_key"),
            page_config.get("survey_id"),
        )

    return TabConfig(
        page_name=page_config.get("page_name"),
        survey_data_name=page_config.get("survey_data_name"),
        survey_key=page_config.get("survey_key"),
        survey_id=page_config.get("survey_id"),
        backcheck_data_name=backcheck_data_name,
        backcheck_key=backcheck_key,
        backcheck_id=backcheck_id,
    )


def validate_prerequisites(project_id: str | None) -> tuple[pl.DataFrame, list[str]]:
    """
    Validate that all prerequisites are met before rendering the page.

    Parameters
    ----------
    project_id : str | None
        The project identifier.

    Returns
    -------
    tuple[pl.DataFrame, list[str]]
        HFC configuration logs and page list.

    Raises
    ------
    SystemExit
        If prerequisites are not met (via st.stop()).
    """
    if not project_id:
        st.info(
            "Select a project from the Start page and import data. "
            "You can also create a new project from the Start page."
        )
        st.stop()

    hfc_config_logs, hfc_pages = load_hfc_config(project_id)

    if hfc_config_logs.is_empty():
        st.info(
            "No checks configured. Please configure checks on the Configure Checks page."
        )
        st.stop()

    if not hfc_pages:
        st.info(
            "No data available to prepare. Load a dataset from the import page to continue."
        )
        st.stop()

    return hfc_config_logs, hfc_pages


def render_add_correction_form(
    correction_processor: CorrectionProcessor,
    key_col: str,
    alias: str,
    tab_index: str | int,
    survey_id_col: str | None = None,
    actions: Sequence[Action] = CORRECTION_ACTIONS,
    column: str | None = None,
) -> None:
    """
    Render the add correction step form.

    The page picks the KEY and shows its Survey ID; the shared correction
    form renders the action, new-value and reason inputs and the Apply
    button. The page offers any KEY, any column and every correction action.
    Apply saves through the form's default `apply_correction_entries`, so
    the page gets the same checks as the check pages: the entry is rejected
    if the value changed since it was shown.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    key_col : str
        The name of the Survey KEY column in the DataFrame.
    alias : str
        The data alias/table name.
    tab_index : str | int
        Suffix for unique widget keys: the check page index, plus the dataset for
        backcheck data.
    survey_id_col : str | None
        The name of the configured Survey ID column, if any. When set (and
        present in the data), the corresponding Survey ID is shown once a
        KEY is selected.
    actions : Sequence[Action]
        The correction actions to offer.
    column : str | None
        The only column to offer, or None to let the user pick any column.
    """
    corrected_data = correction_processor.get_corrected_data(alias)

    # The page already warns about data with no rows; there is no KEY to offer.
    state = get_table_state(corrected_data)
    if state is TableState.MISSING:
        st.warning("No data available for correction.")
        return
    if state is TableState.NO_ROWS:
        return

    with st.popover(":material/add: Add correction step", width="stretch"):
        st.markdown("*Add new correction step*")

        # Step 1: Select key
        key_options = get_key_options(corrected_data, key_col)
        corr_key_val = st.selectbox(
            label="Select KEY",
            options=key_options,
            key=f"correction_key_value_{tab_index}",
        )

        if not corr_key_val:
            return

        survey_id_value = None
        if survey_id_col and survey_id_col in corrected_data.columns:
            survey_id_value = get_current_value(
                corrected_data, key_col, corr_key_val, survey_id_col
            )
            st.write(f"**Survey ID:** {survey_id_value}")

        # Steps 2-5: action, new value, reason and Apply
        render_correction_form(
            correction_processor=correction_processor,
            alias=alias,
            key_col=key_col,
            data=corrected_data,
            key_value=corr_key_val,
            key_namespace=tab_index,
            source=CORRECTIONS_PAGE_SOURCE,
            actions=actions,
            column=column,
            survey_id_value=survey_id_value,
        )


def render_correction_input_form(
    correction_processor: CorrectionProcessor,
    key_col: str,
    alias: str,
    tab_index: str | int,
    survey_id_col: str | None = None,
    actions: Sequence[Action] = CORRECTION_ACTIONS,
    column: str | None = None,
) -> None:
    """
    Render input form for corrections with add and remove functionality.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    key_col : str
        The name of the Survey KEY column in the DataFrame.
    alias : str
        The data alias/table name.
    tab_index : str | int
        Suffix for unique widget keys.
    survey_id_col : str | None
        The name of the configured Survey ID column, if any.
    actions : Sequence[Action]
        The correction actions the add form offers.
    column : str | None
        The only column the add form offers, or None for any column.
    """
    corrected_data = correction_processor.get_corrected_data(alias)

    # A table with no rows, such as one whose every record was dropped, still
    # has corrections to remove; only a missing table skips the forms.
    if get_table_state(corrected_data) is TableState.MISSING:
        st.warning("No data available for correction.")
        return

    fc1, fc2, _ = st.columns([0.4, 0.3, 0.3])

    with fc1:
        render_add_correction_form(
            correction_processor=correction_processor,
            key_col=key_col,
            alias=alias,
            tab_index=tab_index,
            survey_id_col=survey_id_col,
            actions=actions,
            column=column,
        )

    with fc2:
        render_remove_correction_form(
            correction_processor=correction_processor,
            alias=alias,
            tab_index=tab_index,
        )


@st.fragment
def render_remove_correction_form(
    correction_processor: CorrectionProcessor,
    alias: str,
    tab_index: str | int,
) -> None:
    """
    Render the remove correction step form.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    alias : str
        The data alias/table name.
    tab_index : str | int
        The check page index for unique widget keys.
    """
    correction_summaries = correction_processor.get_correction_summary(alias)

    with st.popover(":material/delete: Remove correction step", width="stretch"):
        if not correction_summaries:
            st.info("No correction steps available to remove.")

        # Create selectbox with action descriptions
        action_options = [summary["action_index"] for summary in correction_summaries]
        selected_action = st.selectbox(
            label="Select Correction to Remove",
            options=action_options,
            key=f"remove_correction_{tab_index}",
            index=None,
            help="Select the correction you want to remove from the log",
            disabled=not correction_summaries,
        )

        # Show details of selected correction
        if selected_action:
            _display_correction_details(correction_summaries, selected_action)

        # Confirm removal button
        if st.button(
            label="Remove",
            key=f"confirm_remove_correction_{tab_index}",
            width="stretch",
            type="primary",
            help="Remove the selected correction step from the log",
            disabled=not selected_action,
        ):
            confirm_dialog(
                "Remove correction step",
                "This removes the selected correction step from the log and "
                "reapplies the remaining corrections. This cannot be undone.",
                confirm_label="Remove",
                on_confirm=lambda: _handle_remove_correction(
                    correction_processor, correction_summaries, alias, selected_action
                ),
            )


def _display_correction_details(
    correction_summaries: list[dict], selected_action: str
) -> None:
    """
    Display details of the selected correction.

    Parameters
    ----------
    correction_summaries : list[dict]
        List of correction summaries.
    selected_action : str
        The selected action index.
    """
    selected_summary = next(
        s for s in correction_summaries if s["action_index"] == selected_action
    )
    st.write(f"**Action:** {selected_summary['action']}")
    if selected_summary.get("check_type"):
        st.write(f"**Check type:** {selected_summary['check_type']}")
    st.write(f"**Key:** {selected_summary['key_value']}")
    if selected_summary["column"]:
        st.write(f"**Column:** {selected_summary['column']}")
    if selected_summary["new_value"]:
        st.write(f"**New Value:** {selected_summary['new_value']}")
    st.write(f"**Reason:** {selected_summary['reason']}")


def _handle_remove_correction(
    correction_processor: CorrectionProcessor,
    correction_summaries: list[dict],
    alias: str,
    selected_action: str,
) -> None:
    """
    Handle the removal of a correction entry.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    correction_summaries : list[dict]
        List of correction summaries.
    alias : str
        The data alias/table name.
    selected_action : str
        The selected action index to remove.
    """
    try:
        # Find the index of the selected correction
        correction_index = next(
            s["index"]
            for s in correction_summaries
            if s["action_index"] == selected_action
        )

        # Remove the correction
        failures = correction_processor.remove_correction_entry(alias, correction_index)

        st.success(f"Correction '{selected_action}' removed successfully!")
        warn_reapply_failures(
            failures, "Some remaining corrections could not be reapplied"
        )
        st.rerun()

    except Exception as e:
        st.error(f"Error removing correction: {e!s}")


def _build_correction_log_display(correction_log: pl.DataFrame) -> pl.DataFrame:
    """Prepare a correction log for display in the Correction Log table.

    Backfills columns missing from logs saved before they existed, orders
    columns so status/status_reason sit right after action, and relabels the
    "ID" column as "Survey ID" for display. "accept" rows carry the check
    whose flag was accepted in check_type and, for a hard constraint
    violation, severity "hard"; source names the page that made each entry
    and user names who made it (empty for entries logged before it was
    recorded).

    Parameters
    ----------
    correction_log : pl.DataFrame
        The raw correction log, as persisted.

    Returns
    -------
    pl.DataFrame
        The log with status columns present, in display column order, ready
        for display.
    """
    correction_log = ensure_log_columns(correction_log)

    display_columns = [
        "date",
        "user",
        "KEY",
        "ID",
        "action",
        "status",
        "status_reason",
        "check_type",
        "severity",
        "column",
        "current_value",
        "new_value",
        "reason",
        "source",
    ]
    # "ID" holds the Survey ID value recorded for the KEY, if one was
    # configured - rename it for display so the column reads clearly.
    return correction_log.select(display_columns).rename({"ID": "Survey ID"})


# Display labels for log sources whose stored value doesn't read well
# capitalized. Other sources (outliers, constraints, duplicates) are capitalized.
_SOURCE_LABELS = {CORRECTIONS_PAGE_SOURCE: "Corrections page", GPS_CHECK_TYPE: "GPS"}


def _source_label(source: str) -> str:
    return _SOURCE_LABELS.get(source, source.capitalize())


def filter_correction_log(
    log: pl.DataFrame, sources: Sequence[str], actions: Sequence[str]
) -> pl.DataFrame:
    """Keep the log entries matching the selected sources and actions.

    An empty selection does not filter on that column, so both filters
    together keep entries that match every non-empty selection.
    """
    if sources:
        log = log.filter(pl.col("source").is_in(list(sources)))
    if actions:
        log = log.filter(pl.col("action").is_in(list(actions)))
    return log


def _render_log_filters(
    log: pl.DataFrame, tab_index: str | int, view: ViewState | None = None
) -> tuple[list[str], list[str]]:
    """Render source and action pills for the Correction Log.

    Only values present in the log are offered. Returns the selected
    sources and actions; an empty list means no filter. With a ``view``, the
    selections are remembered; values no longer in the log are dropped.
    """
    source_options = sorted(log["source"].drop_nulls().unique().to_list())
    action_options = sorted(log["action"].drop_nulls().unique().to_list())
    source_col, action_col = st.columns(2)
    with source_col:
        sources = st.pills(
            "Source",
            options=source_options,
            selection_mode="multi",
            format_func=_source_label,
            help="Show only entries made from these pages. Select none to show all.",
            **bind_widget(
                view,
                f"correction_log_source_filter_{tab_index}",
                options=source_options,
                multi=True,
            ),
        )
    with action_col:
        actions = st.pills(
            "Action",
            options=action_options,
            selection_mode="multi",
            format_func=lambda action: action.capitalize(),
            help="Show only entries with these actions. Select none to show all.",
            **bind_widget(
                view,
                f"correction_log_action_filter_{tab_index}",
                options=action_options,
                multi=True,
            ),
        )
    return list(sources or []), list(actions or [])


def highlight_hard_acceptance(row: Any) -> list[str]:
    """Style every cell of a hard-violation acceptance in the Correction Log.

    Used with a pandas ``Styler`` (``df.style.apply(highlight_hard_acceptance,
    axis=1)``). Accepting a value that breaks a hard constraint overrides a
    bound meant to be absolute, so those rows stand out for review.
    """
    action, severity = row.get("action"), row.get("severity")
    # Missing values may be pd.NA, which can't be used in a boolean test.
    is_hard_accept = (
        isinstance(action, str)
        and isinstance(severity, str)
        and action == Action.ACCEPT
        and severity == HARD_SEVERITY
    )
    style = "background-color: rgba(220, 53, 69, 0.15)" if is_hard_accept else ""
    return [style] * len(row)


@st.fragment
def render_correction_log(
    correction_processor: CorrectionProcessor,
    alias: str,
    tab_index: str | int,
    view: ViewState | None = None,
) -> None:
    """
    Render the correction log display.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    alias : str
        The data alias/table name.
    tab_index : str | int
        The check page and dataset namespace for unique widget keys.
    view : ViewState | None
        Where the log filters are remembered.
    """
    correction_log = correction_processor.get_correction_log(alias)

    with st.container(border=True):
        _render_correction_log_contents(correction_log, tab_index, view)


def _render_correction_log_contents(
    correction_log: pl.DataFrame,
    tab_index: str | int,
    view: ViewState | None = None,
) -> None:
    """Render the Correction Log filters, entry count and table.

    Parameters
    ----------
    correction_log : pl.DataFrame
        The raw correction log, as persisted.
    tab_index : str | int
        The check page and dataset namespace for unique widget keys.
    view : ViewState | None
        Where the log filters are remembered.
    """
    if correction_log.is_empty():
        st.info(
            "No corrections have been made yet. You can add corrections "
            "using the form above."
        )
        return

    section_header("Correction Log")

    log_display = _build_correction_log_display(correction_log)
    sources, actions = _render_log_filters(log_display, tab_index, view)
    log_display = filter_correction_log(log_display, sources, actions)
    # Show the count whenever a filter is active, including when nothing
    # matches, so "Showing 0 of Y" explains the empty result.
    if sources or actions:
        st.caption(
            f"Showing {log_display.height:,} of {correction_log.height:,} entries."
        )
    if log_display.is_empty():
        st.info("No log entries match the selected filters.")
        return
    styled_dataframe(
        row_styler(log_display, highlight_hard_acceptance).map(
            highlight_status, subset=["status"]
        ),
        width="stretch",
    )


@st.fragment
def render_data_summary(
    correction_processor: CorrectionProcessor, data: pl.DataFrame
) -> None:
    """
    Render data summary metrics and preview.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    data : pl.DataFrame
        The data to summarize.
    """
    summary = correction_processor.get_data_summary(data)

    with st.container(border=True):
        section_header("Preview Corrected Data")
        st.divider()

        metric_row(
            [
                ("Rows", summary["rows"]),
                ("Columns", summary["columns"]),
                ("Missing Values", f"{summary['missing_percentage']}%"),
            ]
        )

        st.dataframe(data=data, width="stretch")


def warn_about_corrected_data(state: TableState, alias: str) -> None:
    """
    Warn when corrected data is missing or has no rows.

    A table with no rows keeps the forms and the Correction Log, so the
    correction that dropped every record can be undone.

    Parameters
    ----------
    state : TableState
        The state of the corrected data for the dataset.
    alias : str
        The data alias/table name, shown in the warning.
    """
    if state is TableState.MISSING:
        st.warning(f"No data available for {alias}")
    elif state is TableState.NO_ROWS:
        st.warning(
            f"**{alias}** has no rows. A correction or a step on the Prepare "
            "Data page removed every record. Remove that correction with "
            "**Remove correction step**, or that step on the Prepare Data "
            "page, to restore the data."
        )


def choose_dataset(
    datasets: list[CorrectionDataset], tab_index: int, view: ViewState | None
) -> CorrectionDataset:
    """Let the user pick survey or backcheck data when a page has both.

    The choice is remembered in ``view``, so it survives switching check
    pages and new sessions.
    """
    if len(datasets) == 1:
        return datasets[0]
    labels = [d.label for d in datasets]
    chosen = st.segmented_control(
        "Dataset",
        options=labels,
        required=True,
        help=(
            "Backcheck data can only have its ID modified or rows "
            "removed, for example to resolve duplicate or unmatched IDs."
        ),
        **bind_widget(
            view, f"correction_dataset_{tab_index}", options=labels, default=SURVEY_DATA
        ),
    )
    return datasets[labels.index(chosen)] if chosen in labels else datasets[0]


@st.fragment
def render_correction_tab(
    correction_processor: CorrectionProcessor,
    project_id: str,
    tab_index: int,
    view: ViewState | None = None,
) -> None:
    """
    Render the corrections of one check page with all components.

    Parameters
    ----------
    correction_processor : CorrectionProcessor
        The correction processor instance.
    project_id : str
        The project identifier.
    tab_index : int
        The check page's position in the check configuration.
    view : ViewState | None
        Where the page's dataset choice and log filters are remembered.
    """
    config: TabConfig = load_tab_config(project_id, tab_index)

    if not config:
        st.error(f"Error loading configuration for check page {tab_index + 1}")
        return

    section_header(f"{config.page_name}")
    st.write("Add corrections to the data based on issues identified in checks.")

    dataset = choose_dataset(correction_datasets(config, tab_index), tab_index, view)

    # Ensure corrected data exists
    corrected_data = correction_processor.get_corrected_data(dataset.alias)

    state = get_table_state(corrected_data)
    warn_about_corrected_data(state, dataset.alias)
    if state is TableState.MISSING:
        return

    # Render components
    render_correction_input_form(
        correction_processor=correction_processor,
        key_col=dataset.key_col,
        alias=dataset.alias,
        tab_index=dataset.key_namespace,
        survey_id_col=dataset.id_col,
        actions=dataset.actions,
        column=dataset.column,
    )

    render_correction_log(
        correction_processor=correction_processor,
        alias=dataset.alias,
        tab_index=dataset.key_namespace,
        view=view,
    )

    render_data_summary(
        correction_processor=correction_processor,
        data=corrected_data,
    )


def render_page_header() -> None:
    """Render the page header.

    In the demo, the Correct Data step guidance above the header is the page's
    only instruction set.
    """
    page_header(
        "Correct Data",
        "Make corrections to data based on issues identified in checks.",
    )


def render_page_navigation() -> None:
    """Render the page navigation controls."""
    replication_page = st.session_state.get("st_replication_page")
    page_navigation(
        prev={
            "page_name": st.session_state.get("st_output_page1", "output_view_1"),
            "label": "← Back: Output Page 1",
        },
        next={
            "page_name": replication_page,
            "label": "Export Replication Package →",
        }
        if replication_page
        else None,
    )


def check_page_status(project_id: str, page_config: dict) -> StatusResult:
    """Return whether a check page has anything to correct, and why not.

    Corrections need the page's survey KEY column and its survey data. Only
    the configuration and whether a table exists are read.
    """
    if not page_config.get("survey_key"):
        return StatusResult(
            CheckStatus.NOT_SET_UP,
            "No survey KEY column is configured for this check page. Set one "
            "on the Configure Checks page.",
        )
    alias = page_config.get("survey_data_name")
    if not alias or not any(
        duckdb_table_exists(project_id, alias, db_name)
        for db_name in ("corrected", "prep", "raw")
    ):
        return StatusResult(
            CheckStatus.NOT_SET_UP,
            f"Its survey data, **{alias}**, has not been imported. Import it "
            "on the Import Data page.",
        )
    return READY


def check_page_items(
    project_id: str, hfc_config_logs: pl.DataFrame, hfc_pages: list[str]
) -> list[NavItem]:
    """Return one navigation item per check page, in configuration order.

    Pages with nothing to correct are dimmed with the reason.
    """
    items = []
    for page_name, page_config in zip(
        hfc_pages, hfc_config_logs.to_dicts(), strict=False
    ):
        slug = name_id(page_name)
        status = guarded_status(
            slug, lambda config=page_config: check_page_status(project_id, config)
        )
        items.append(
            NavItem(
                slug=slug,
                label=page_name,
                icon=":material/fact_check:",
                status=status.status,
                reason=status.reason,
            )
        )
    return items


def open_last_viewed_check_page(project_id: str, slugs: Sequence[str]) -> None:
    """Select the check page the user last viewed, once.

    The check page records itself in the project-level view state file when
    it renders, so the record survives a new session. Using the record here
    clears it, so a page chosen on Corrections is kept until another check
    page is viewed. A ``page`` URL value wins, and the record is then kept
    for the next visit without one.
    """
    if PAGE_PARAM in st.query_params:
        return
    project_view_file = get_cache_path(project_id, "settings", PROJECT_VIEW_FILE)
    last = remembered(project_view_file, LAST_CHECK_PAGE)
    if last is None:
        return
    forget_remembered(project_view_file, LAST_CHECK_PAGE)
    if last in slugs:
        select_nav_item(
            project_nav_key(CORRECTIONS_NAV_KEY, project_id), PAGE_PARAM, last
        )


def render_selected_check_page(
    correction_processor: CorrectionProcessor,
    project_id: str,
    hfc_config_logs: pl.DataFrame,
    hfc_pages: list[str],
) -> None:
    """Draw the check page pills and the selected page's corrections.

    Selection: the ``page`` URL value, then the check page last viewed, then
    the page chosen here before (also in earlier sessions), then the first.
    Configuration is loaded by the page's position in the check
    configuration.
    """
    items = check_page_items(project_id, hfc_config_logs, hfc_pages)
    slugs = [item.slug for item in items]
    settings_file = get_cache_path(project_id, "settings", CORRECTIONS_SETTINGS_FILE)
    open_last_viewed_check_page(project_id, slugs)

    # The pills sit above the page but are drawn after it, so a page that
    # fails while rendering is already marked in them.
    nav_slot = st.container()
    nav_key = project_nav_key(CORRECTIONS_NAV_KEY, project_id)
    state = resolve_selection(
        items,
        key=nav_key,
        param=PAGE_PARAM,
        saved=saved_selection(settings_file),
    )
    save_selection(settings_file, state.selected)
    item = state.selected_item
    if item.dimmed:
        # Each reason names the page where the setup happens.
        render_empty_state(item, setup_hint="")
    else:
        view = ViewState(settings_file, state.selected)
        reset_filters_button(view, key=nav_key)
        run_guarded(
            nav_key,
            item,
            lambda: render_correction_tab(
                correction_processor, project_id, slugs.index(item.slug), view
            ),
        )
    with nav_slot:
        draw_nav(state, key=nav_key, param=PAGE_PARAM, label="Check page")


def main() -> None:
    """
    Main entry point for the correction view.

    This function orchestrates the entire page rendering process, including:
    - Setting up navigation and demo helpers
    - Validating prerequisites
    - Creating correction processor
    - Rendering the selected check page's corrections
    """
    # Set up demo navigation
    demo_sidebar_help()
    add_demo_navigation("correction_view", step=6)

    # Render page header
    render_page_header()

    # Get project ID from session state
    project_id: str = st.session_state["st_project_id"]

    # Validate prerequisites
    hfc_config_logs, hfc_pages = validate_prerequisites(project_id)

    # Initialize correction processor
    correction_processor = CorrectionProcessor(project_id)

    render_selected_check_page(
        correction_processor, project_id, hfc_config_logs, hfc_pages
    )

    # Render navigation
    render_page_navigation()


# Execute main function when run as a Streamlit page
if __name__ == "__main__":
    main()
