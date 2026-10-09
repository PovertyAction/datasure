"""Cards for ID problems on the Duplicates tab.

Renders one card per duplicate ID, and in the backcheck view one card per
unmatched backcheck, with metrics, search, sort, pagination and a CSV export
above them. The logic lives in `id_duplicates`.
"""

import datetime
from dataclasses import dataclass

import polars as pl
import streamlit as st

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
from datasure.utils.settings_utils import (
    load_check_settings,
    save_check_settings,
    trigger_save,
)
from datasure.utils.ui_utils import metric_row, row_styler, styled_dataframe

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


def render_dataset_switcher(has_backcheck: bool) -> str:
    """Render the Survey data / Backcheck data switcher and return the choice.

    The switcher is shown only when the page has backcheck data; otherwise
    the survey data is always chosen.
    """
    if not has_backcheck:
        return SURVEY_DATA
    return st.segmented_control(
        "Dataset",
        options=[SURVEY_DATA, BACKCHECK_DATA],
        default=SURVEY_DATA,
        required=True,
        key="duplicates_dataset",
        help="Find ID problems in the survey data or in the backcheck data.",
    )


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
    metrics.append(("Resolved", 0, "Duplicate IDs resolved on this page."))
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


def _render_unmatched_card(view: IdView, card: dict, fields: list[str]) -> None:
    with st.container(border=True):
        _render_card_header(view, card, "not found in the survey data")
        records = card_records(view.data, card)
        st.dataframe(
            comparison_grid(records, fields).drop("differs"),
            hide_index=True,
            width="stretch",
        )


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
    if not view.id_col or view.id_col not in view.data.columns:
        st.info(
            f"The {view.name} ID column is not configured or not in the "
            f"{view.name} data."
        )
        return

    extra = _render_display_cols(view, settings_file)
    # Only a date-typed column can give date ranges and sort by latest date.
    has_date = bool(
        view.date_col
        and view.date_col in view.data.columns
        and view.data[view.date_col].dtype.is_temporal()
    )
    fields = default_fields(
        view.data.columns,
        key=view.key_col,
        date=view.date_col if has_date else None,
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
