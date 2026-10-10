"""Cards for ID problems on the Duplicates tab.

Renders one card per duplicate ID, and in the backcheck view one card per
unmatched backcheck, with metrics, search, sort, pagination and a CSV export
above them. When the view has a dataset alias to correct, each card also has
the controls that resolve it (see `id_corrections`). The card logic lives in
`id_duplicates`.
"""

import datetime
import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass

import polars as pl
import streamlit as st

from datasure.checks.id_corrections import (
    DUPLICATE_DECISIONS,
    REASONS,
    SOURCE,
    UNMATCHED_DECISIONS,
    Decision,
    RecordDecision,
    all_dropped,
    build_entries,
    has_repeated_keys,
    log_reason,
    save_blockers,
)
from datasure.checks.id_duplicates import (
    CARDS_PER_PAGE,
    DUPLICATE,
    SortBy,
    build_export,
    card_records,
    comparison_grid,
    count_missing_ids,
    default_fields,
    find_duplicate_groups,
    find_unmatched_ids,
    paginate_cards,
    search_cards,
    sort_cards,
)
from datasure.processing.corrections import CorrectionEntry, CorrectionProcessor
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)
from datasure.utils.ui_utils import (
    confirm_dialog,
    metric_row,
    queue_notice,
    row_styler,
    show_queued_notices,
    styled_dataframe,
)

logger = logging.getLogger(__name__)

TAB_NAME = "duplicates"

SURVEY_DATA = "Survey data"
BACKCHECK_DATA = "Backcheck data"

_DIFFERS_STYLE = "background-color: rgba(255, 193, 7, 0.25)"


@dataclass(frozen=True)
class IdView:
    """One dataset's ID duplicates, as shown by `render_id_duplicates`.

    Attributes
    ----------
    name : str
        ``"survey"`` or ``"backcheck"``; prefixes widget keys and file names.
    data : pl.DataFrame
        The records to check, after Records to Include.
    id_col, key_col, date_col : str | None
        The ID, KEY and date columns.
    staff_col, team_col : str | None
        The enumerator (or backchecker) and team columns.
    display_cols_setting : str
        Settings key under which the extra columns to show are saved.
    survey_data : pl.DataFrame | None
        Survey data to match backcheck IDs against. When set, the view also
        shows unmatched ID cards.
    alias : str | None
        The dataset's alias, whose correction log the cards' saves go to.
        When None, the cards have no correction controls.
    processor : CorrectionProcessor | None
        Applies and logs the cards' corrections. Required with `alias`.
    resolved : int
        Duplicate IDs resolved by corrections, for the Resolved metric.
    """

    name: str
    data: pl.DataFrame
    id_col: str | None
    key_col: str | None
    date_col: str | None
    staff_col: str | None
    team_col: str | None
    display_cols_setting: str
    survey_data: pl.DataFrame | None = None
    alias: str | None = None
    processor: CorrectionProcessor | None = None
    resolved: int = 0


_SWITCHER_KEY = "duplicates_dataset"

# A segmented control cannot disable one option, so grey out the Backcheck
# data button and ignore clicks on it.
_DISABLED_BACKCHECK_CSS = f"""<style>
.st-key-{_SWITCHER_KEY} button:last-of-type {{
    opacity: 0.5;
    pointer-events: none;
    cursor: not-allowed;
}}
</style>"""


def count_duplicate_ids(view: IdView) -> int:
    """Return the number of unresolved duplicate IDs in `view`.

    Returns 0 when the ID column is not configured or not in the data.
    """
    if not view.id_col or view.id_col not in view.data.columns:
        return 0
    return find_duplicate_groups(
        view.data, view.id_col, view.key_col, view.date_col
    ).height


def _keep_survey_data() -> None:
    st.session_state[_SWITCHER_KEY] = SURVEY_DATA


def render_dataset_switcher(survey_count: int, backcheck_count: int | None) -> str:
    """Render the Survey data / Backcheck data switcher and return the choice.

    Each option shows its number of unresolved duplicate IDs, for example
    "Survey data (3)". When `backcheck_count` is None the page has no
    backchecks: the option shows "Backcheck data (N/A)", cannot be chosen,
    and the survey data is always returned.
    """
    has_backcheck = backcheck_count is not None
    labels = {
        SURVEY_DATA: f"{SURVEY_DATA} ({survey_count})",
        BACKCHECK_DATA: (
            f"{BACKCHECK_DATA} ({backcheck_count if has_backcheck else 'N/A'})"
        ),
    }
    if not has_backcheck:
        st.html(_DISABLED_BACKCHECK_CSS)
        if st.session_state.get(_SWITCHER_KEY) == BACKCHECK_DATA:
            _keep_survey_data()

    chosen = st.segmented_control(
        "Dataset",
        options=[SURVEY_DATA, BACKCHECK_DATA],
        format_func=labels.get,
        default=SURVEY_DATA,
        required=True,
        key=_SWITCHER_KEY,
        on_change=None if has_backcheck else _keep_survey_data,
        help=(
            "Find ID problems in the survey data or in the backcheck data. "
            "The number is the count of unresolved duplicate IDs."
        ),
    )
    return chosen if has_backcheck else SURVEY_DATA


def _render_display_cols(view: IdView, settings_file: str) -> list[str]:
    """Render the "Show more columns in report" picker and return its choice."""
    with st.expander(":material/clarify: Show more columns in report", expanded=False):
        saved = load_check_settings(settings_file, TAB_NAME)
        options = [c for c in view.data.columns if c not in (view.id_col, view.key_col)]
        default = [c for c in saved.get(view.display_cols_setting, []) if c in options]
        chosen = st.multiselect(
            label="Select additional columns to display",
            options=options,
            default=default,
            help="Columns to show on every card and in the CSV download.",
            key=f"iddup_{view.name}_display_cols",
            on_change=trigger_save,
            kwargs={"state_name": f"{TAB_NAME}_{view.display_cols_setting}"},
        )
        save_check_settings(
            settings_file, TAB_NAME, {view.display_cols_setting: chosen}
        )
    return chosen


def _render_metrics(view: IdView, groups: pl.DataFrame, unmatched) -> None:
    metrics = [
        ("Duplicate IDs", groups.height, "IDs shared by two or more records."),
        (
            "Records involved",
            int(groups["n_records"].sum()),
            "Records that share an ID with another record.",
        ),
        (
            "Missing IDs",
            count_missing_ids(view.data, view.id_col),
            "Records with no ID. They are not grouped into cards.",
        ),
    ]
    if unmatched is not None:
        metrics.append(
            (
                "Unmatched IDs",
                unmatched.height,
                "Backchecks whose ID is not in the survey data.",
            )
        )
    metrics.append(
        (
            "Resolved",
            view.resolved,
            "Duplicate IDs that corrections have resolved, from any page.",
        )
    )
    metric_row(metrics)


def _reset_page(page_key: str) -> None:
    st.session_state[page_key] = 1


def _date_text(value) -> str:
    if isinstance(value, datetime.datetime):
        return value.strftime("%Y-%m-%d")
    return str(value)


def _date_range_text(card: dict) -> str | None:
    first, latest = card["first_date"], card["latest_date"]
    if first is None:
        return None
    if _date_text(first) == _date_text(latest):
        return _date_text(first)
    return f"{_date_text(first)} to {_date_text(latest)}"


def _render_grid(grid: pl.DataFrame) -> None:
    differing = set(grid.filter(pl.col("differs"))["Field"].to_list())
    shown = grid.drop("differs")

    def style(row):
        # Highlight the record cells of a differing field, not its label.
        css = _DIFFERS_STYLE if row["Field"] in differing else ""
        return ["", *[css] * (len(row) - 1)]

    styled_dataframe(
        row_styler(shown, style),
        hide_index=True,
        width="stretch",
        column_config={"Field": st.column_config.Column("Field", pinned=True)},
    )


def _render_card_header(view: IdView, card: dict, summary: str) -> None:
    header = [f"**{view.id_col}: {card['id']}**", summary]
    if date_range := _date_range_text(card):
        header.append(date_range)
    st.markdown(" · ".join(header))


def _notice_scope(view: IdView) -> str:
    return f"iddup_{view.name}"


def _logged_key(view: IdView) -> str:
    return f"iddup_{view.name}_logged"


def _save_corrections(view: IdView, card_id: str, entries: list[CorrectionEntry]):
    """Apply and log a card's entries, all or none, then rerun the page.

    The outcome is queued, so it survives the rerun, and the rerun drops a
    resolved card. Used directly and as a `confirm_dialog` callback.
    """
    try:
        view.processor.apply_corrections(
            alias=view.alias, key_col=view.key_col, entries=entries, source=SOURCE
        )
    except Exception as e:
        # UI boundary: report a failed save instead of crashing the page.
        logger.exception("Failed to save corrections for ID %s", card_id)
        queue_notice(
            _notice_scope(view),
            "error",
            f"The corrections for {view.id_col} {card_id} were not saved: {e}",
        )
    else:
        st.session_state[_logged_key(view)] = st.session_state.get(
            _logged_key(view), 0
        ) + len(entries)
        n = len(entries)
        queue_notice(
            _notice_scope(view),
            "toast",
            f"Saved {n} correction{'' if n == 1 else 's'} for {view.id_col} {card_id}.",
        )
    st.rerun()


def _render_record_decision(
    view: IdView, namespace: str, label: str, key, options: Sequence[Decision]
) -> RecordDecision:
    """Render one record's decision and, for Modify ID, its new ID input."""
    c1, c2, c3 = st.columns([0.3, 0.4, 0.3], vertical_alignment="center")
    with c1:
        st.markdown(f"{label} · KEY **{key}**")
    widget_key = json.dumps([namespace, str(key)])
    with c2:
        decision = st.radio(
            f"Decision for KEY {key}",
            options=options,
            horizontal=True,
            label_visibility="collapsed",
            key=f"iddup_decision_{widget_key}",
        )
    new_id = None
    if decision == Decision.MODIFY_ID:
        with c3:
            new_id = st.text_input(
                f"New {view.id_col} for KEY {key}",
                label_visibility="collapsed",
                placeholder=f"New {view.id_col}",
                key=f"iddup_new_id_{widget_key}",
            )
    return RecordDecision(key, decision, new_id)


def _render_card_corrections(
    view: IdView, card: dict, records: pl.DataFrame, options: Sequence[Decision]
) -> None:
    """Render the decisions, reason and Save button that resolve a card.

    Save stays disabled, with the reasons listed, until at most one record
    keeps the ID, every new ID is valid, and a reason and note are given.
    Dropping every record needs a confirmation.
    """
    if not view.key_col or view.key_col not in records.columns:
        st.caption("Set the KEY column to correct these records.")
        return
    if has_repeated_keys(records, view.key_col):
        st.warning(
            "Some of these records share a KEY, and a correction applies to "
            "every row with its KEY, so they can't be corrected here. Give "
            "each record a unique KEY in the source data first."
        )
        return

    namespace = json.dumps([view.name, card["kind"], card["id"]])
    st.markdown("**Resolve**")
    keys = records[view.key_col].to_list()
    labels = [f"Record {i}" for i in range(1, len(keys) + 1)]
    if card["kind"] != DUPLICATE:
        labels = ["Backcheck"]
    decisions = [
        _render_record_decision(view, namespace, label, key, options)
        for label, key in zip(labels, keys, strict=True)
    ]

    r1, r2 = st.columns([0.35, 0.65])
    with r1:
        reason = st.selectbox(
            "Reason",
            options=REASONS,
            index=None,
            placeholder="Choose a reason",
            key=f"iddup_reason_{namespace}",
        )
    with r2:
        note = st.text_input(
            "Note",
            placeholder="What you checked, for the correction log",
            key=f"iddup_note_{namespace}",
        )

    survey_ids = None
    if card["kind"] != DUPLICATE and view.survey_data is not None:
        survey_ids = (
            view.survey_data[view.id_col].cast(pl.String).drop_nulls().to_list()
        )
    blockers = save_blockers(
        decisions,
        original_id=card["id"],
        included=view.data,
        id_col=view.id_col,
        key_col=view.key_col,
        reason=reason,
        note=note,
        survey_ids=survey_ids,
    )
    for blocker in blockers:
        st.caption(f":material/info: {blocker}")

    if not st.button(
        "Save",
        type="primary",
        disabled=bool(blockers),
        key=f"iddup_save_{namespace}",
        help="Log one correction per changed record. Undo on the Correct Data page.",
    ):
        return

    entries = build_entries(
        decisions,
        original_id=card["id"],
        id_col=view.id_col,
        reason=log_reason(reason, note),
    )
    if all_dropped(decisions):
        n = len(decisions)
        confirm_dialog(
            "Drop every record",
            f"This drops {'all ' if n > 1 else ''}{n} record"
            f"{'s' if n > 1 else ''} with {view.id_col} {card['id']}, which "
            f"removes the ID from the {view.name} data.",
            confirm_label="Drop",
            on_confirm=lambda: _save_corrections(view, card["id"], entries),
        )
    else:
        _save_corrections(view, card["id"], entries)


def _render_logged_caption(view: IdView) -> None:
    """Show how many corrections the cards logged, with a link to undo them."""
    logged = st.session_state.get(_logged_key(view), 0)
    if not logged:
        return
    c1, c2 = st.columns([0.6, 0.4], vertical_alignment="center")
    with c1:
        st.caption(
            f"{logged} correction{'' if logged == 1 else 's'} logged this session. "
            "To undo one, remove it from the Correction Log."
        )
    # A markdown link would open a new browser session and lose the selected
    # project; a page link navigates within this session.
    corrections_page = st.session_state.get("st_corr_page")
    if corrections_page is not None:
        with c2:
            st.page_link(
                corrections_page,
                label="View in Correction Log",
                icon=":material/cleaning_services:",
            )


def _render_duplicate_card(
    view: IdView, card: dict, fields: list[str], all_fields: list[str]
) -> None:
    with st.container(border=True):
        _render_card_header(view, card, f"{card['n_records']} records")

        toggle_key = f"iddup_{view.name}_{card['id']}"
        c1, c2, _ = st.columns([0.25, 0.25, 0.5])
        with c1:
            compare_all = st.toggle(
                "Compare all fields",
                key=f"{toggle_key}_all",
                help="Show every column, not only the default fields.",
            )
        with c2:
            only_differing = st.toggle(
                "Only differing fields",
                key=f"{toggle_key}_diff",
                help="Hide fields that are the same in every record.",
            )

        records = card_records(view.data, card)
        grid = comparison_grid(records, all_fields if compare_all else fields)
        if only_differing:
            grid = grid.filter(pl.col("differs"))
        if grid.is_empty():
            st.caption("No differing fields.")
        else:
            _render_grid(grid)

        if view.alias:
            _render_card_corrections(view, card, records, DUPLICATE_DECISIONS)


def _render_unmatched_card(view: IdView, card: dict, fields: list[str]) -> None:
    with st.container(border=True):
        _render_card_header(view, card, "not found in the survey data")
        records = card_records(view.data, card)
        st.dataframe(
            comparison_grid(records, fields).drop("differs"),
            hide_index=True,
            width="stretch",
        )
        if view.alias:
            _render_card_corrections(view, card, records, UNMATCHED_DECISIONS)


def _csv(export: pl.DataFrame) -> bytes:
    """Write `export` as CSV, with nested values written as text."""
    nested = [c for c, t in export.schema.items() if t.is_nested()]
    if nested:
        export = export.with_columns(
            pl.col(c).map_elements(str, return_dtype=pl.String) for c in nested
        )
    return export.write_csv().encode("utf-8")


def render_id_duplicates(view: IdView, settings_file: str) -> None:
    """Render the ID duplicate (and unmatched ID) cards for one dataset.

    Parameters
    ----------
    view : IdView
        The dataset and its columns.
    settings_file : str
        The page's settings file, where the extra columns are saved.
    """
    show_queued_notices(_notice_scope(view))
    if not view.id_col or view.id_col not in view.data.columns:
        st.info(
            f"The {view.name} ID column is not configured or not in the "
            f"{view.name} data."
        )
        return

    extra = _render_display_cols(view, settings_file)
    # Only a date-typed column can give date ranges and sort by latest date;
    # a text date is still compared as a field.
    has_date = bool(
        view.date_col
        and view.date_col in view.data.columns
        and view.data[view.date_col].dtype.is_temporal()
    )
    fields = default_fields(
        view.data.columns,
        key=view.key_col,
        date=view.date_col,
        staff=view.staff_col,
        team=view.team_col,
        extra=extra,
    )
    # Unmatched cards show only the KEY, date and backchecker.
    unmatched_fields = [
        f for f in fields if f in (view.key_col, view.date_col, view.staff_col)
    ]
    all_fields = view.data.columns

    groups = find_duplicate_groups(view.data, view.id_col, view.key_col, view.date_col)
    unmatched = None
    if view.survey_data is not None:
        unmatched = find_unmatched_ids(
            view.data, view.survey_data, view.id_col, view.key_col, view.date_col
        )
    cards = groups if unmatched is None else pl.concat([groups, unmatched])

    _render_metrics(view, groups, unmatched)
    _render_logged_caption(view)

    if cards.is_empty():
        message = "No duplicate IDs found."
        if unmatched is not None:
            message = "No duplicate or unmatched IDs found."
        st.success(message, icon=":material/check_circle:")
        return

    page_key = f"iddup_{view.name}_page"
    sort_options = [SortBy.GROUP_SIZE.value]
    if has_date:
        sort_options.append(SortBy.LATEST_DATE.value)

    sc1, sc2, sc3 = st.columns([0.5, 0.25, 0.25], vertical_alignment="bottom")
    with sc1:
        query = st.text_input(
            "Search by ID or KEY",
            key=f"iddup_{view.name}_search",
            placeholder="Search by ID or KEY",
            on_change=_reset_page,
            args=(page_key,),
        )
    with sc2:
        sort_by = st.selectbox(
            "Sort by",
            options=sort_options,
            key=f"iddup_{view.name}_sort",
            on_change=_reset_page,
            args=(page_key,),
        )

    found = sort_cards(search_cards(cards, query), SortBy(sort_by))

    with sc3:
        st.download_button(
            "Download duplicates (CSV)",
            data=_csv(build_export(view.data, found, view.id_col, fields)),
            file_name=f"{view.name}_id_duplicates.csv",
            mime="text/csv",
            icon=":material/download:",
            width="stretch",
            help="Every record on the cards below, across all pages.",
        )

    if found.is_empty():
        st.info("No cards match your search.")
        return

    _, n_pages, _ = paginate_cards(found, 1)
    if st.session_state.get(page_key, 1) > n_pages:
        st.session_state[page_key] = n_pages
    pc1, pc2 = st.columns([0.2, 0.8], vertical_alignment="center")
    with pc1:
        page = st.number_input(
            "Page", min_value=1, max_value=n_pages, step=1, key=page_key
        )
    page_cards, _, page = paginate_cards(found, int(page))
    with pc2:
        first = (page - 1) * CARDS_PER_PAGE + 1
        st.caption(
            f"Showing {first} to {first + page_cards.height - 1} of {found.height} "
            f"cards · page {page} of {n_pages}"
        )

    for card in page_cards.iter_rows(named=True):
        if card["kind"] == DUPLICATE:
            _render_duplicate_card(view, card, fields, all_fields)
        else:
            _render_unmatched_card(view, card, unmatched_fields)
