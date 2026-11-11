"""The Progress page's By unit and Respondents sections, and tracking issues.

The sections draw from `ProgressResult` fields that `progress_tracking`
computes. The table-building helpers are pure, so they are tested directly;
the render functions only lay them out. Saved view state (the level and the
filter) comes in as a `ViewState`, so this module needs nothing from
`progress`.
"""

from collections.abc import Sequence

import polars as pl
import streamlit as st

from datasure.checks.progress_tracking import (
    UNTRACKED,
    VISIT_STATUSES,
    Respondent,
    TrackingIssue,
    UnitLevel,
    UnitRow,
)
from datasure.utils.ui_utils import metric_row, section_header
from datasure.utils.view_state import ViewState

UNIT_FILTERS = ["All", "Behind", "Over target", "Untracked"]
FILTER_STATUS = {"Behind": "behind", "Over target": "over target"}
STATUS_TEXT = {
    "behind": "Behind",
    "on track": "",
    "over target": "Over target",
    "untracked": "Untracked",
}
LEVEL_KEY = "by_unit_level"
FILTER_KEY = "by_unit_filter"
VISIT_PCT = "Unit % complete"


# =============================================================================
# Pure helpers
# =============================================================================


def filter_units(rows: Sequence[UnitRow], choice: str) -> list[UnitRow]:
    """Keep the rows the By unit filter asks for.

    "Behind" is below 50% of target, "Over target" above 100%, "Untracked"
    the group of submissions outside the tracking dataset.
    """
    if choice == "Untracked":
        return [row for row in rows if row.status == "untracked"]
    if choice in FILTER_STATUS:
        return [row for row in rows if row.status == FILTER_STATUS[choice]]
    return list(rows)


def furthest_behind(rows: Sequence[UnitRow]) -> list[UnitRow]:
    """Return the tracked units with the lowest % complete first."""
    tracked = [row for row in rows if row.percentage is not None]
    return sorted(tracked, key=lambda row: (row.percentage, row.unit))


def lowest_first(rows: Sequence[UnitRow]) -> list[UnitRow]:
    """Order the By unit table: lowest % complete first, Untracked last."""
    untracked = [row for row in rows if row.percentage is None]
    return furthest_behind(rows) + untracked


def unit_frame(rows: Sequence[UnitRow], column: str) -> pl.DataFrame:
    """Return the By unit table, for display and export."""
    return pl.DataFrame(
        [
            [
                row.unit,
                row.target,
                row.submissions,
                row.unique,
                row.completed,
                row.percentage,
                row.remaining,
                STATUS_TEXT[row.status],
            ]
            for row in rows
        ],
        schema={
            column: pl.String,
            "Target": pl.Int64,
            "Submissions": pl.Int64,
            "Unique": pl.Int64,
            "Completed": pl.Int64,
            "% complete": pl.Float64,
            "Remaining": pl.Int64,
            "Status": pl.String,
        },
        orient="row",
    )


def visit_lists(
    respondents: Sequence[Respondent], units: Sequence[UnitRow]
) -> list[tuple[UnitRow, list[Respondent]]]:
    """Group the Pending and Attempted-not-completed respondents by unit.

    Units come lowest % complete first, so the furthest behind is visited
    first; units with no one left to visit are left out.
    """
    by_unit: dict[str, list[Respondent]] = {}
    for respondent in respondents:
        if respondent.status in VISIT_STATUSES:
            by_unit.setdefault(respondent.unit, []).append(respondent)
    return [
        (unit, by_unit[unit.unit])
        for unit in furthest_behind(units)
        if unit.unit in by_unit
    ]


def respondent_frame(
    respondents: Sequence[Respondent], extra: Sequence[str], unit_column: str
) -> pl.DataFrame:
    """Return respondents as a table with the chosen master-list columns."""
    columns = {
        "ID": pl.String,
        unit_column: pl.String,
        "Status": pl.String,
        "Attempts": pl.Int64,
        "Last submission": pl.Date,
    }
    # A display column named like a fixed one would overwrite it
    extra_names = {name: f"{name} " if name in columns else name for name in extra}
    return pl.DataFrame(
        [
            [r.id, r.unit, r.status, r.attempts, r.last_date]
            + [r.extra.get(name) for name in extra]
            for r in respondents
        ],
        schema=columns | dict.fromkeys(extra_names.values(), pl.String),
        orient="row",
    )


def visit_frame(
    lists: Sequence[tuple[UnitRow, list[Respondent]]],
    extra: Sequence[str],
    unit_column: str,
) -> pl.DataFrame:
    """Return the visit lists as one table, with each unit's % complete.

    Rows keep the lists' order: the furthest-behind unit first.
    """
    people = [r for _, group in lists for r in group]
    unit_pct = [unit.percentage for unit, group in lists for _ in group]
    frame = respondent_frame(people, extra, unit_column)
    return frame.insert_column(
        frame.columns.index(unit_column) + 1,
        pl.Series(VISIT_PCT, unit_pct, dtype=pl.Float64),
    )


# =============================================================================
# Rendering
# =============================================================================


def display_issues(issues: Sequence[TrackingIssue]) -> None:
    """Show the tracking dataset's errors and warnings, listing their values."""
    for issue in issues:
        values = ", ".join(f"`{value}`" for value in issue.values[:50])
        more = len(issue.values) - 50
        text = issue.message + (f" {values}" if values else "")
        if more > 0:
            text += f" and {more:,} more"
        if issue.level == "error":
            st.error(text, icon=":material/error:")
        else:
            st.warning(text, icon=":material/warning:")


def _download(frame: pl.DataFrame, label: str, file_name: str, key: str) -> None:
    st.download_button(
        label,
        data=frame.write_csv().encode("utf-8"),
        file_name=file_name,
        mime="text/csv",
        icon=":material/download:",
        key=key,
    )


def display_by_unit(levels: Sequence[UnitLevel], view: ViewState) -> None:
    """Draw By unit: level and filter, the table lowest % first, export.

    Parameters
    ----------
    levels : Sequence[UnitLevel]
        The table at each level, units first; empty when an error stops the
        tracking dataset being used.
    view : ViewState
        The page's saved view state, for the level and the filter.
    """
    if not levels:
        st.info(
            "By unit needs a usable tracking dataset. Fix the problems shown "
            "at the top of the page, in the :material/settings: settings "
            "section or in the tracking dataset."
        )
        return
    names = [level.column for level in levels]
    with st.container(horizontal=True):
        name = names[0]
        if len(names) > 1:
            name = st.segmented_control(
                "Level",
                options=names,
                required=True,
                help="Units, or a parent level that sums its units",
                **view.bind(LEVEL_KEY, options=names, default=names[0]),
            )
        choice = st.segmented_control(
            "Show",
            options=UNIT_FILTERS,
            required=True,
            help="Behind: below 50% of target. Over target: above 100%. "
            "Untracked: submissions in a unit the tracking dataset has no "
            "target for, or with an ID not on the master list.",
            **view.bind(FILTER_KEY, options=UNIT_FILTERS, default=UNIT_FILTERS[0]),
        )
    level = levels[names.index(name)] if name in names else levels[0]

    shown = lowest_first(filter_units(level.rows, choice or UNIT_FILTERS[0]))
    table = unit_frame(shown, level.column)
    _download(
        table,
        "Download table (CSV)",
        f"progress_by_{level.column}.csv",
        key="by_unit_download",
    )
    if not shown:
        st.info("No units match the filter.")
        return
    st.dataframe(
        table,
        hide_index=True,
        width="stretch",
        column_config={
            level.column: st.column_config.Column(pinned=True),
            # The bar fills at 100%; "auto" draws it red below half, which
            # is the Behind cutoff.
            "% complete": st.column_config.ProgressColumn(
                format="%.1f%%",
                min_value=0,
                max_value=100,
                color="auto",
                help="Completed of target. Red below 50% (Behind).",
            ),
        },
    )
    if any(row.unit == UNTRACKED for row in shown):
        st.caption(
            "**Untracked** counts submissions whose unit is not in the "
            "tracking dataset or has a target of 0, and IDs not on the "
            "master list."
        )


def display_respondents(
    respondents: Sequence[Respondent],
    levels: Sequence[UnitLevel],
    extra: Sequence[str],
) -> None:
    """Draw Respondents: status counts, visit lists by unit, Unexpected, Completed.

    Parameters
    ----------
    respondents : Sequence[Respondent]
        The master list's respondents and the unexpected IDs.
    levels : Sequence[UnitLevel]
        The By unit levels; the first orders the visit lists.
    extra : Sequence[str]
        The master-list columns shown and exported with each list.
    """
    if not levels:
        st.info(
            "Respondents needs a usable master list. Fix the problems shown "
            "at the top of the page."
        )
        return
    unit_column = levels[0].column
    by_status: dict[str, list[Respondent]] = {}
    for respondent in respondents:
        by_status.setdefault(respondent.status, []).append(respondent)

    def count(status: str) -> str:
        return f"{len(by_status.get(status, [])):,}"

    metric_row(
        [
            ("Completed", count("Completed"), "Has a submission that qualifies"),
            (
                "Attempted not completed",
                count("Attempted not completed"),
                "Has submissions, none qualifying",
            ),
            ("Pending", count("Pending"), "Has no submissions"),
            ("Unexpected", count("Unexpected"), "Survey IDs not on the master list"),
        ]
    )

    section_header("To visit", icon=":material/directions_walk:")
    lists = visit_lists(respondents, levels[0].rows)
    if not lists:
        st.success(
            "Everyone on the master list has completed.", icon=":material/check_circle:"
        )
    else:
        table = visit_frame(lists, extra, unit_column)
        st.caption(
            f"{table.height:,} pending and attempted respondents in "
            f"{len(lists):,} {unit_column} units, the furthest behind first."
        )
        _download(
            table,
            "Download visit list (CSV)",
            "progress_visit_list.csv",
            key="visit_list_download",
        )
        st.dataframe(
            table,
            hide_index=True,
            width="stretch",
            column_config={
                "ID": st.column_config.Column(pinned=True),
                VISIT_PCT: st.column_config.NumberColumn(
                    format="%.0f%%", help=f"% complete of the {unit_column}"
                ),
            },
        )

    unexpected = by_status.get("Unexpected", [])
    section_header("Unexpected IDs", icon=":material/help:")
    if not unexpected:
        st.success(
            "Every survey ID is on the master list.", icon=":material/check_circle:"
        )
    else:
        st.caption(
            "Survey IDs not on the master list, with their last submission. "
            "They are counted in the Untracked group."
        )
        table = respondent_frame(unexpected, [], unit_column).drop(
            unit_column, "Status"
        )
        _download(
            table,
            "Download unexpected IDs (CSV)",
            "progress_unexpected_ids.csv",
            key="unexpected_download",
        )
        st.dataframe(table, hide_index=True, width="stretch")

    completed = by_status.get("Completed", [])
    section_header("Completed", icon=":material/task_alt:")
    if not completed:
        st.info("No one on the master list has completed yet.")
        return
    table = respondent_frame(completed, extra, unit_column).drop("Status")
    _download(
        table,
        "Download completed (CSV)",
        "progress_completed.csv",
        key="completed_download",
    )
    with st.expander(f"{len(completed):,} completed respondents"):
        st.dataframe(table, hide_index=True, width="stretch")
