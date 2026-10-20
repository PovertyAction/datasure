"""Summary's check health grid: one card per check with its status and headline.

``health_cards`` builds the cards from the checks' navigation items and their
headline functions. Headlines are cached on the page's data and settings, so
Summary only recomputes them when something they depend on changes.
``render_health_grid`` draws the cards. Streamlit is imported inside the
drawing function, as in ``ui_utils``.
"""

import hashlib
import json
import logging
import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence
from dataclasses import astuple, dataclass
from datetime import date
from pathlib import Path

import polars as pl

from datasure.checks.context import CheckContext
from datasure.utils.duckdb_utils import database_path
from datasure.utils.navigation import CheckStatus, NavItem
from datasure.utils.view_state import without_view_state

logger = logging.getLogger(__name__)

Headline = Callable[[CheckContext], str | None]

OPEN_ACTION = "Open →"
SET_UP_ACTION = "Set up →"

# Status text and icon on a card, so status does not rely on colour alone.
_STATUS_LINES: dict[CheckStatus, tuple[str, str, str]] = {
    CheckStatus.READY: ("green", ":material/check_circle:", "Ready"),
    CheckStatus.NOT_SET_UP: ("gray", ":material/build:", "Not set up"),
    CheckStatus.NOT_APPLICABLE: (
        "gray",
        ":material/do_not_disturb_on:",
        "Not applicable",
    ),
    CheckStatus.ERROR: ("red", ":material/error:", "Error"),
}

_CARDS_PER_ROW = 3


@dataclass(frozen=True)
class HealthCard:
    """One check's card on the health grid.

    Attributes
    ----------
    item : NavItem
        The check's navigation item: label, group, status and reason.
    headline : str | None
        The check's headline, such as "14 duplicate IDs"; None for checks
        that are not ready or have no headline.
    headline_error : str
        Why the headline could not be computed; empty when it could.
    """

    item: NavItem
    headline: str | None = None
    headline_error: str = ""

    @property
    def action(self) -> str | None:
        """The card's button label, or None when there is nothing to do."""
        if self.item.status is CheckStatus.NOT_SET_UP:
            return SET_UP_ACTION
        if self.item.status is CheckStatus.NOT_APPLICABLE:
            return None
        return OPEN_ACTION

    @property
    def status_line(self) -> str:
        """The status as Markdown text with an icon."""
        colour, icon, text = _STATUS_LINES[self.item.status]
        return f":{colour}[{icon} {text}]"


# --- Headline cache --------------------------------------------------------

_CACHE_SIZE = 256
_cache: "OrderedDict[Hashable, str | None]" = OrderedDict()
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
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


def _content_hash(path: Path) -> Hashable | None:
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return None


def _settings_hash(path: Path) -> Hashable | None:
    """Hash a page settings file, leaving out its view state.

    View state (the selected check, saved filters) does not change any
    headline, so changing it must not recompute them.
    """
    try:
        settings = json.loads(path.read_text())
    except (OSError, ValueError):
        return _content_hash(path)
    if not isinstance(settings, dict):
        return _content_hash(path)
    return hashlib.sha256(
        json.dumps(without_view_state(settings), sort_keys=True).encode()
    ).hexdigest()


def _page_fingerprint(ctx: CheckContext) -> Hashable:
    """What headlines depend on: data, page settings and settings tables.

    The settings files are hashed. The logs database (outlier and backcheck
    columns, missing codes, accepted flags) and the intermediate database
    (consent and outcome data) are stamped by modification time and size.
    Enumerator activity is measured against today, so the date is included.
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


def _cached(key: Hashable, compute: Callable[[], str | None]) -> str | None:
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
        # Data that cannot be hashed is not cached; headlines still show.
        logger.warning("Could not fingerprint the page data", exc_info=True)
        return None


def health_cards(
    ctx: CheckContext,
    items: Iterable[NavItem],
    headlines: Mapping[str, Headline],
) -> tuple[HealthCard, ...]:
    """Build a health card for each check.

    Ready checks with a headline function get their headline, cached on the
    page's data and settings. A headline that raises is reported on its card
    and is not cached, so the next run tries again.

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
    tuple[HealthCard, ...]
        One card per item.
    """
    fingerprint = _fingerprint_or_none(ctx)
    cards = []
    for item in items:
        headline = headlines.get(item.slug)
        if item.status is not CheckStatus.READY or headline is None:
            cards.append(HealthCard(item))
            continue
        try:
            if fingerprint is None:
                value = headline(ctx)
            else:
                value = _cached((item.slug, fingerprint), lambda h=headline: h(ctx))
        except Exception as exc:  # UI boundary: one headline must not stop the grid
            logger.exception("Could not compute the headline of %r", item.slug)
            cards.append(
                HealthCard(item, headline_error=f"{type(exc).__name__}: {exc}")
            )
            continue
        cards.append(HealthCard(item, headline=value))
    return tuple(cards)


def render_health_grid(
    cards: Sequence[HealthCard], on_select: Callable[[str], None]
) -> None:
    """Draw the health grid: a bordered card per check, three to a row.

    Each card shows the check's label, group, status, and its headline or
    the reason it is not ready. "Open →" and "Set up →" call ``on_select``
    with the check's slug.
    """
    import streamlit as st

    st.divider()
    st.markdown("## Check health")
    for start in range(0, len(cards), _CARDS_PER_ROW):
        columns = st.columns(_CARDS_PER_ROW)
        for offset, card in enumerate(cards[start : start + _CARDS_PER_ROW]):
            with columns[offset], st.container(border=True):
                _render_card(st, card, on_select)


def _render_card(st, card: HealthCard, on_select: Callable[[str], None]) -> None:
    item = card.item
    st.markdown(f"**{item.label}**")
    st.caption(item.group or "")
    st.markdown(card.status_line)
    if card.headline_error:
        st.error(
            f"Could not compute the headline: {card.headline_error}",
            icon=":material/error:",
        )
    elif card.headline:
        st.markdown(f"### {card.headline}")
    elif item.reason:
        st.caption(item.reason)
    if card.action:
        st.button(
            card.action,
            key=f"health_card_{item.slug}",
            on_click=on_select,
            args=(item.slug,),
        )
