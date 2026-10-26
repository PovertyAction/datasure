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
from pathlib import Path
from typing import NamedTuple

import polars as pl

from datasure.checks.context import CheckContext
from datasure.checks.headline import CheckDelta, CheckHeadline, DeltaKind
from datasure.checks.health_period import (
    DEFAULT_PERIOD,
    DEFAULT_WEEK_START,
    WEEKDAYS,
    ComparisonPeriod,
    DeltaWindow,
)
from datasure.utils.duckdb_utils import database_path
from datasure.utils.navigation import CheckStatus, NavItem
from datasure.utils.view_state import ViewState, without_view_state

logger = logging.getLogger(__name__)

Headline = Callable[[CheckContext], CheckHeadline | None]
# A check's change over the comparison period, from its headline now.
Delta = Callable[[CheckContext, CheckHeadline, DeltaWindow], CheckDelta | None]

OPEN_ACTION = "Open →"
SET_UP_ACTION = "Set up →"
# Shown in place of a number a row does not have.
NO_NUMBER = "—"
# The detail of a ready check with no numbers, such as Descriptive Stats.
STATUS_ONLY = "Status only"


def status_only_headline(_ctx: CheckContext | None) -> CheckHeadline:
    """Headline of a check that only describes the data and counts nothing.

    Its row is green, as for any informational check, with no number.
    """
    return CheckHeadline(NO_NUMBER, STATUS_ONLY, informational=True)


class Pill(NamedTuple):
    """A status pill: colour, icon and label, so status is not colour alone."""

    colour: str
    icon: str
    label: str


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
    # Ready, but its issues are not counted, so nothing is claimed about them.
    READY = "ready"

    @property
    def pill(self) -> Pill:
        """The state's status pill."""
        return _PILLS[self]

    @property
    def action(self) -> str | None:
        """The row's button label, or None when there is nothing to do."""
        return _ACTIONS.get(self, OPEN_ACTION)


_PILLS: dict[RowState, Pill] = {
    RowState.NOT_SET_UP: Pill("gray", ":material/build:", "Not set up"),
    RowState.NOT_APPLICABLE: Pill(
        "gray", ":material/do_not_disturb_on:", "Not applicable"
    ),
    RowState.ERROR: Pill("red", ":material/error:", "Error"),
    RowState.FLAGGED: Pill("orange", ":material/warning:", "Flagged"),
    RowState.NO_ISSUES: Pill("green", ":material/check_circle:", "No issues"),
    RowState.READY: Pill("blue", ":material/check:", "Ready"),
}

_ACTIONS: dict[RowState, str | None] = {
    RowState.NOT_SET_UP: SET_UP_ACTION,
    RowState.NOT_APPLICABLE: None,
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
    delta : CheckDelta | None
        The change over the comparison period; None when there is none,
        such as for a check with no date column.
    """

    item: NavItem
    headline: CheckHeadline | None = None
    error: str = ""
    delta: CheckDelta | None = None

    @property
    def state(self) -> RowState:
        """The row's state, from the check's status and outstanding issues."""
        if self.item.status in _STATE_BY_STATUS:
            return _STATE_BY_STATUS[self.item.status]
        if self.error:
            return RowState.ERROR
        if self.headline is None:
            return RowState.READY
        if self.headline.flagged:
            return RowState.FLAGGED
        return RowState.NO_ISSUES

    @property
    def action(self) -> str | None:
        """The row's button label, or None when there is nothing to do."""
        return self.state.action

    @property
    def value(self) -> str:
        """The outstanding number as shown."""
        return self.headline.value if self.headline else NO_NUMBER

    @property
    def detail(self) -> str:
        """The line under the value: the check's detail, the error or reason.

        A ready check with no numbers shows ``STATUS_ONLY``.
        """
        if self.error:
            return f"Could not compute the numbers: {self.error}"
        if self.headline:
            return self.headline.detail
        return self.item.reason or STATUS_ONLY

    @property
    def resolved(self) -> str:
        """The resolved count as shown."""
        if self.headline is None or self.headline.resolved is None:
            return NO_NUMBER
        return f"{self.headline.resolved:,}"

    def change(self, since: str) -> str:
        """The outstanding change as shown, such as "▲ 3 new since yesterday".

        Parameters
        ----------
        since : str
            Where the comparison period starts, from `since_label`.
        """
        if self.delta is None or self.delta.outstanding is None:
            return NO_NUMBER
        return _change_text(self.delta.outstanding, self.delta.kind, since)

    def resolved_change(self, since: str) -> str:
        """The resolutions in the period as shown, or "" without any count."""
        if self.delta is None or self.delta.resolved is None:
            return ""
        return f"+{self.delta.resolved:,} since {since}"


def _change_text(change: float, kind: DeltaKind, since: str) -> str:
    if kind is DeltaKind.POINTS:
        change = round(change, 2)
    if change == 0:
        nothing = {
            DeltaKind.NEW: "No new issues",
            DeltaKind.SUBMISSIONS: "No new submissions",
        }.get(kind, "No change")
        return f"{nothing} since {since}"
    arrow = "▲" if change > 0 else "▼"
    size = abs(change)
    if kind is DeltaKind.POINTS:
        return f"{arrow} {size:.2f} pp since {since}"
    size = int(size)
    if kind is DeltaKind.SUBMISSIONS:
        noun = "submission" if size == 1 else "submissions"
        return f"{arrow} {size:,} new {noun} since {since}"
    if kind is DeltaKind.ACTIVE:
        more = "more" if change > 0 else "fewer"
        return f"{arrow} {size:,} {more} active since {since}"
    return f"{arrow} {size:,} new since {since}"


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


def _cached_or_computed(key: Hashable | None, compute: Callable[[], object]) -> object:
    return compute() if key is None else _cached(key, compute)


def _row_delta(
    ctx: CheckContext,
    slug: str,
    delta: Delta,
    headline: CheckHeadline,
    window: DeltaWindow,
    headline_key: Hashable | None,
) -> CheckDelta | None:
    """Compute a row's delta, cached by the period start; None if it fails.

    Cached under the row's headline key, so it depends on what the headline
    depends on, plus the window.
    """
    key = None if headline_key is None else ("delta", headline_key, window)
    try:
        return _cached_or_computed(key, lambda: delta(ctx, headline, window))
    # UI boundary: a delta that cannot be computed leaves the row's numbers;
    # the row shows no change and the cause is logged.
    except Exception:
        logger.exception("Could not compute the change of %r", slug)
        return None


def health_rows(
    ctx: CheckContext,
    items: Iterable[NavItem],
    headlines: Mapping[str, Headline],
    deltas: Mapping[str, Delta] | None = None,
    window: DeltaWindow | None = None,
    view_keys: Mapping[str, Callable[[CheckContext], Hashable]] | None = None,
) -> tuple[HealthRow, ...]:
    """Build a health row for each check.

    Ready checks with a headline function get their numbers, cached on the
    page's data and settings. A headline that raises gives its row the error
    state and is not cached, so the next run tries again; the other rows are
    still built. With a `window`, rows with numbers and a delta function also
    get their change over the comparison period, cached on the period start
    as well, so switching back to a period already viewed is instant.

    Parameters
    ----------
    ctx : CheckContext
        The check page's context.
    items : Iterable[NavItem]
        The checks to show, with their status, in display order.
    headlines : Mapping[str, Headline]
        Headline function by check slug.
    deltas : Mapping[str, Delta] | None
        Delta function by check slug. Called with the context, the check's
        headline now and the window.
    window : DeltaWindow | None
        The comparison period and date columns; None shows no changes.
    view_keys : Mapping[str, Callable[[CheckContext], Hashable]] | None
        By check slug, the saved view values a headline depends on, added
        to its cache key: the page fingerprint leaves view state out.

    Returns
    -------
    tuple[HealthRow, ...]
        One row per item.
    """
    deltas = deltas or {}
    fingerprint = _fingerprint_or_none(ctx)
    rows = []
    for item in items:
        headline = headlines.get(item.slug)
        if item.status is not CheckStatus.READY or headline is None:
            rows.append(HealthRow(item))
            continue
        view_key = (view_keys or {}).get(item.slug)
        key = None
        try:
            if fingerprint is not None:
                key = (item.slug, fingerprint, view_key(ctx) if view_key else None)
            value = _cached_or_computed(key, lambda h=headline: h(ctx))
        # UI boundary: one check's numbers must not stop the other rows. The
        # error is shown on the row by render_health_rows (deferred display,
        # see CONTRIBUTING "Error Handling Conventions").
        except Exception as exc:
            logger.exception("Could not compute the headline of %r", item.slug)
            rows.append(HealthRow(item, error=f"{type(exc).__name__}: {exc}"))
            continue
        delta = deltas.get(item.slug)
        change = (
            None
            if value is None or delta is None or window is None
            else _row_delta(ctx, item.slug, delta, value, window, key)
        )
        rows.append(HealthRow(item, headline=value, delta=change))
    return tuple(rows)


def group_rows(
    rows: Iterable[HealthRow],
) -> tuple[tuple[str | None, tuple[HealthRow, ...]], ...]:
    """Group rows by navigation group, each group once.

    Groups come in order of their first row, as in the navigation, and rows
    keep their order within a group, even when a group's rows are not next
    to each other.
    """
    groups: dict[str | None, list[HealthRow]] = {}
    for row in rows:
        groups.setdefault(row.item.group, []).append(row)
    return tuple((group, tuple(members)) for group, members in groups.items())


# --- Drawing ----------------------------------------------------------------

# Shown instead of the Comparison period box when no row has a date column.
NO_DATE_CAPTION = "Set a date column in Summary settings to see changes over time."

# View state scope of the comparison period, in the project's view file.
PERIOD_SCOPE = "check_health"


def render_health_header() -> None:
    """Draw the divider and the Check health section header."""
    import streamlit as st

    from datasure.utils.ui_utils import section_header

    st.divider()
    section_header("Check health", ":material/health_and_safety:")


def render_comparison_period(
    project_view_file: str | Path, project_id: str
) -> tuple[ComparisonPeriod, str]:
    """Draw the collapsible Comparison period box and return its choice.

    One setting per project, saved as personal view state in the project's
    view file, so it applies to Summary on every check page and project
    exports leave it out.

    Parameters
    ----------
    project_view_file : str | Path
        The project's view settings file (``PROJECT_VIEW_FILE``).
    project_id : str
        The project, so another project opened in the same session does not
        inherit the choice.

    Returns
    -------
    tuple[ComparisonPeriod, str]
        The period and the first day of the week, one of ``WEEKDAYS``.
    """
    import streamlit as st

    view = ViewState(project_view_file, PERIOD_SCOPE)
    periods = [period.value for period in ComparisonPeriod]
    with st.expander("Comparison period", icon=":material/date_range:"):
        left, right = st.columns([3, 1])
        with left:
            period = st.radio(
                "Compare with",
                periods,
                horizontal=True,
                help="Day compares with the end of yesterday; 7 days and 30 days "
                "with that many days ago; Week and Month with the start of this "
                "week or month.",
                **view.bind(
                    f"health_period__{project_id}",
                    options=periods,
                    index=periods.index(DEFAULT_PERIOD.value),
                ),
            )
        with right:
            week_start = st.selectbox(
                "Week starts on",
                WEEKDAYS,
                disabled=period != ComparisonPeriod.WEEK,
                **view.bind(
                    f"health_week_start__{project_id}",
                    options=WEEKDAYS,
                    index=WEEKDAYS.index(DEFAULT_WEEK_START),
                ),
            )
    return ComparisonPeriod(period or DEFAULT_PERIOD), week_start or DEFAULT_WEEK_START


def render_period_caption(since: str | None, latest: date | None) -> None:
    """Caption the rows with the comparison and the latest submission date.

    The latest date explains a change of zero: nothing was submitted since.
    Without `since` no row has a date column, and the caption says how to
    get one.
    """
    import streamlit as st

    if since is None:
        st.caption(NO_DATE_CAPTION)
        return
    latest_text = "no submission has a date" if latest is None else f"{latest:%d %b %Y}"
    st.caption(f"Changes since {since}. Latest submission: {latest_text}.")


# Relative widths of the Check, Status, Outstanding, Change, Resolved and
# action columns, shared by the header and every row so the columns line up.
_COLUMNS = (
    ("Check", 2.0),
    ("Status", 1.4),
    ("Outstanding", 2.4),
    ("Change", 1.6),
    ("Resolved", 1.1),
    ("", 1.1),
)
_CHANGE = "Change"


def _columns(with_changes: bool) -> tuple[tuple[str, float], ...]:
    return tuple(c for c in _COLUMNS if with_changes or c[0] != _CHANGE)


def render_health_rows(
    rows: Sequence[HealthRow],
    on_select: Callable[[str], None],
    since: str | None = None,
) -> None:
    """Draw the check health list: a row per check, grouped like the navigation.

    One column header is shared by every group, and each row sits in its own
    bordered container so its numbers read as one check. Each row shows the
    check's label, status pill, outstanding number with its detail line (or
    the reason the check is not ready, or the error), its change over the
    comparison period, resolved count with the resolutions in the period,
    and action button. "Open →" and "Set up →" call ``on_select`` with the
    check's slug.

    Parameters
    ----------
    rows : Sequence[HealthRow]
        The rows, from `health_rows`.
    on_select : Callable[[str], None]
        Called with the check's slug by the action buttons.
    since : str | None
        Where the comparison period starts (`since_label`). None hides the
        Change column and the resolutions in the period, as when no row has
        a date column.
    """
    import streamlit as st

    columns = _columns(since is not None)
    widths = [width for _, width in columns]
    for column, (header, _) in zip(st.columns(widths), columns, strict=True):
        if header:
            column.caption(f"**{header.upper()}**")
    for group, members in group_rows(rows):
        if group:
            st.caption(f"**{group}**")
        for row in members:
            with st.container(border=True):
                _render_row(st, row, on_select, widths, since)


def _render_row(
    st,
    row: HealthRow,
    on_select: Callable[[str], None],
    widths: list[float],
    since: str | None,
) -> None:
    item = row.item
    cells = st.columns(widths, vertical_alignment="center")
    name, status, outstanding = cells[:3]
    resolved, action = cells[-2:]
    name.markdown(f"**{item.label}**")
    pill = row.state.pill
    status.badge(pill.label, icon=pill.icon, color=pill.colour)
    outstanding.markdown(f"**{row.value}**")
    if row.detail:
        outstanding.caption(row.detail)
    resolved.markdown(row.resolved)
    if since is not None:
        cells[3].caption(row.change(since))
        if row.resolved_change(since):
            resolved.caption(row.resolved_change(since))
    if row.action:
        action.button(
            row.action,
            key=f"health_row_{item.slug}",
            on_click=on_select,
            args=(item.slug,),
            width="stretch",
        )
