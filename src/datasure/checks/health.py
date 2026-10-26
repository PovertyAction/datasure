"""Summary's check health rows: one row per check, grouped like the navigation.

``health_rows`` builds the rows from the checks' navigation items and their
headline functions. Headlines are cached on the page's data and settings, so
Summary only recomputes them when something they depend on changes.
``render_health_rows`` draws the rows. Streamlit is imported inside the
drawing function, as in ``ui_utils``.

A row's state comes from the check's configuration status (``CheckStatus``)
and, for a ready check, from its headline: outstanding issues flag the row.
"""

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import astuple, dataclass
from datetime import date
from enum import StrEnum
from itertools import groupby
from pathlib import Path

import polars as pl

from datasure.checks.context import CheckContext
from datasure.checks.headline import CheckHeadline
from datasure.utils.duckdb_utils import database_path
from datasure.utils.navigation import CheckStatus, NavItem
from datasure.utils.view_state import without_view_state

logger = logging.getLogger(__name__)

Headline = Callable[[CheckContext], CheckHeadline | None]

OPEN_ACTION = "Open →"
SET_UP_ACTION = "Set up →"
# Shown in place of a number a row does not have.
NO_NUMBER = "—"


class RowState(StrEnum):
    """What a check's health row reports, shown as its status pill."""

    NOT_SET_UP = "not_set_up"
    NOT_APPLICABLE = "not_applicable"
    # The status or a number could not be computed.
    ERROR = "error"
    # Ready, with outstanding issues.
    FLAGGED = "flagged"
    # Ready with no outstanding issues, or an informational check.
    NO_ISSUES = "no_issues"

    @property
    def pill(self) -> tuple[str, str, str]:
        """The pill's colour, icon and label, so status is not colour alone."""
        return _PILLS[self]


_PILLS: dict[RowState, tuple[str, str, str]] = {
    RowState.NOT_SET_UP: ("gray", ":material/build:", "Not set up"),
    RowState.NOT_APPLICABLE: (
        "gray",
        ":material/do_not_disturb_on:",
        "Not applicable",
    ),
    RowState.ERROR: ("red", ":material/error:", "Error"),
    RowState.FLAGGED: ("orange", ":material/warning:", "Flagged"),
    RowState.NO_ISSUES: ("green", ":material/check_circle:", "No issues"),
}

_STATE_BY_STATUS = {
    CheckStatus.NOT_SET_UP: RowState.NOT_SET_UP,
    CheckStatus.NOT_APPLICABLE: RowState.NOT_APPLICABLE,
    CheckStatus.ERROR: RowState.ERROR,
}


@dataclass(frozen=True)
class HealthRow:
    """One check's row in the check health list.

    Attributes
    ----------
    item : NavItem
        The check's navigation item: label, group, status and reason.
    headline : CheckHeadline | None
        The check's numbers; None for checks that are not ready or have no
        headline.
    error : str
        Why the numbers could not be computed; empty when they could.
    """

    item: NavItem
    headline: CheckHeadline | None = None
    error: str = ""

    @property
    def state(self) -> RowState:
        """The row's state, from the check's status and outstanding issues."""
        if self.item.status in _STATE_BY_STATUS:
            return _STATE_BY_STATUS[self.item.status]
        if self.error:
            return RowState.ERROR
        if self.headline is not None and self.headline.flagged:
            return RowState.FLAGGED
        return RowState.NO_ISSUES

    @property
    def pill(self) -> tuple[str, str, str]:
        """The status pill's colour, icon and label."""
        return self.state.pill

    @property
    def action(self) -> str | None:
        """The row's button label, or None when there is nothing to do."""
        if self.item.status is CheckStatus.NOT_SET_UP:
            return SET_UP_ACTION
        if self.item.status is CheckStatus.NOT_APPLICABLE:
            return None
        return OPEN_ACTION

    @property
    def value(self) -> str:
        """The outstanding number as shown."""
        return self.headline.value if self.headline else NO_NUMBER

    @property
    def detail(self) -> str:
        """The line under the value: the check's detail, the error or reason."""
        if self.error:
            return f"Could not compute the numbers: {self.error}"
        if self.headline:
            return self.headline.detail
        return self.item.reason

    @property
    def resolved(self) -> str:
        """The resolved count as shown."""
        if self.headline is None or self.headline.resolved is None:
            return NO_NUMBER
        return f"{self.headline.resolved:,}"


# --- Headline cache --------------------------------------------------------

_CACHE_SIZE = 256
_cache: "OrderedDict[Hashable, CheckHeadline | None]" = OrderedDict()
_cache_lock = threading.Lock()


def clear_headline_cache() -> None:
    """Forget every cached headline."""
    with _cache_lock:
        _cache.clear()


def _frame_fingerprint(data: pl.DataFrame | None) -> Hashable | None:
    if data is None:
        return None
    return (data.height, str(data.schema), int(data.hash_rows().sum()))


def _file_stamp(path: Path) -> Hashable | None:
    try:
        stat = path.stat()
    except FileNotFoundError:
        # Normal before a database or its WAL file exists.
        return None
    except OSError:
        logger.warning("Could not stat %s", path, exc_info=True)
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _content_hash(path: Path) -> Hashable | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except FileNotFoundError:
        # Normal before the settings file is first saved.
        return None
    except OSError:
        logger.warning("Could not read %s", path, exc_info=True)
        return None


def _settings_hash(path: Path) -> Hashable | None:
    """Hash a page settings file, leaving out its view state.

    View state (the selected check, saved filters) does not change any
    headline, so changing it must not recompute them.
    """
    try:
        settings = json.loads(path.read_text())
    except FileNotFoundError:
        # Normal before the settings file is first saved.
        return None
    except (OSError, ValueError):
        logger.warning("Could not parse settings %s", path, exc_info=True)
        return _content_hash(path)
    if not isinstance(settings, dict):
        return _content_hash(path)
    return hashlib.sha256(
        json.dumps(without_view_state(settings), sort_keys=True).encode()
    ).hexdigest()


def _page_fingerprint(ctx: CheckContext) -> Hashable:
    """What headlines depend on: data, page settings and settings tables.

    The settings files are hashed. The logs database (outlier and backcheck
    columns, missing codes, accepted flags, backcheck attributions) and the
    intermediate database (consent and outcome data, corrections) are stamped
    by modification time and size. Enumerator activity is measured against
    today, so the date is included.
    """
    config = ctx.config
    databases = [
        database_path(ctx.project_id, name) for name in ("logs", "intermediate")
    ]
    return (
        ctx.project_id,
        astuple(config),
        _frame_fingerprint(ctx.data.page_data),
        _frame_fingerprint(ctx.data.backcheck_data),
        _settings_hash(Path(config.setting_file)),
        _content_hash(Path(config.missing_setting_file)),
        tuple(
            _file_stamp(path.with_name(path.name + suffix))
            for path in databases
            for suffix in ("", ".wal")
        ),
        date.today(),
    )


def _cached(
    key: Hashable, compute: Callable[[], CheckHeadline | None]
) -> CheckHeadline | None:
    with _cache_lock:
        if key in _cache:
            _cache.move_to_end(key)
            return _cache[key]
    value = compute()
    with _cache_lock:
        _cache[key] = value
        while len(_cache) > _CACHE_SIZE:
            _cache.popitem(last=False)
    return value


def _fingerprint_or_none(ctx: CheckContext) -> Hashable | None:
    try:
        return _page_fingerprint(ctx)
    except (pl.exceptions.PolarsError, TypeError):
        # Data that cannot be hashed is not cached; the numbers still show.
        logger.warning("Could not fingerprint the page data", exc_info=True)
        return None


def health_rows(
    ctx: CheckContext,
    items: Iterable[NavItem],
    headlines: Mapping[str, Headline],
) -> tuple[HealthRow, ...]:
    """Build a health row for each check.

    Ready checks with a headline function get their numbers, cached on the
    page's data and settings. A headline that raises gives its row the error
    state and is not cached, so the next run tries again; the other rows are
    still built.

    Parameters
    ----------
    ctx : CheckContext
        The check page's context.
    items : Iterable[NavItem]
        The checks to show, with their status, in display order.
    headlines : Mapping[str, Headline]
        Headline function by check slug.

    Returns
    -------
    tuple[HealthRow, ...]
        One row per item.
    """
    fingerprint = _fingerprint_or_none(ctx)
    rows = []
    for item in items:
        headline = headlines.get(item.slug)
        if item.status is not CheckStatus.READY or headline is None:
            rows.append(HealthRow(item))
            continue
        try:
            if fingerprint is None:
                value = headline(ctx)
            else:
                value = _cached((item.slug, fingerprint), lambda h=headline: h(ctx))
        # UI boundary: one check's numbers must not stop the other rows. The
        # error is shown on the row by render_health_rows (deferred display,
        # see CONTRIBUTING "Error Handling Conventions").
        except Exception as exc:
            logger.exception("Could not compute the headline of %r", item.slug)
            rows.append(HealthRow(item, error=f"{type(exc).__name__}: {exc}"))
            continue
        rows.append(HealthRow(item, headline=value))
    return tuple(rows)


# Relative widths of the Check, Status, Outstanding, Resolved and action
# columns, shared by the header and every row so the columns line up.
_COLUMN_WIDTHS = (2.0, 1.4, 2.6, 1.0, 1.1)
_HEADERS = ("Check", "Status", "Outstanding", "Resolved", "")


def render_health_rows(
    rows: Sequence[HealthRow], on_select: Callable[[str], None]
) -> None:
    """Draw the check health list: a row per check, grouped like the navigation.

    One column header is shared by every group. Each row shows the check's
    label, status pill, outstanding number with its detail line (or the
    reason the check is not ready, or the error), resolved count and action
    button. "Open →" and "Set up →" call ``on_select`` with the check's slug.
    """
    import streamlit as st

    from datasure.utils.ui_utils import section_header

    st.divider()
    section_header("Check health", ":material/health_and_safety:")
    for column, header in zip(st.columns(_COLUMN_WIDTHS), _HEADERS, strict=True):
        if header:
            column.caption(f"**{header.upper()}**")
    for group, group_rows in groupby(rows, key=lambda row: row.item.group):
        if group:
            st.caption(f"**{group}**")
        with st.container(border=True):
            for row in group_rows:
                _render_row(st, row, on_select)


def _render_row(st, row: HealthRow, on_select: Callable[[str], None]) -> None:
    item = row.item
    name, status, outstanding, resolved, action = st.columns(
        _COLUMN_WIDTHS, vertical_alignment="center"
    )
    name.markdown(f"**{item.label}**")
    colour, icon, label = row.pill
    status.badge(label, icon=icon, color=colour)
    outstanding.markdown(f"**{row.value}**")
    if row.detail:
        outstanding.caption(row.detail)
    resolved.markdown(row.resolved)
    if row.action:
        action.button(
            row.action,
            key=f"health_row_{item.slug}",
            on_click=on_select,
            args=(item.slug,),
            width="stretch",
        )
