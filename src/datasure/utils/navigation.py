"""Pure navigation model shared by the check, Prepare Data and Corrections pages.

Nothing here calls Streamlit. ``resolve_nav`` decides which item is selected
and how each item looks; ``utils/nav_ui.py`` draws the result.

An item belongs to a group (check page: two rows, a group control and the
group's items) or has no group (Prepare Data, Corrections: one row of items).
"""

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import NamedTuple


class CheckStatus(StrEnum):
    """Whether an item can show results."""

    READY = "ready"
    # Something the user can configure is missing.
    NOT_SET_UP = "not_set_up"
    # The data cannot support the item, for example no GPS column.
    NOT_APPLICABLE = "not_applicable"
    # The item raised while computing its status or rendering.
    ERROR = "error"


class StatusResult(NamedTuple):
    """A status and the human-readable reason for it."""

    status: CheckStatus
    reason: str = ""


READY = StatusResult(CheckStatus.READY)


def rows_status(row_count: int) -> StatusResult:
    """Status for a check that works on any survey data with rows."""
    if row_count:
        return READY
    return StatusResult(
        CheckStatus.NOT_APPLICABLE, "The survey data has no rows to check."
    )


@dataclass(frozen=True)
class NavItem:
    """One selectable item in the navigation.

    Attributes
    ----------
    slug : str
        Stable identifier, used as the URL query parameter value.
    label : str
        Short label shown in the navigation.
    icon : str
        Material icon shortcode.
    group : str | None
        Group the item belongs to, or None in a flat list.
    status : CheckStatus
        The item's status.
    reason : str
        Why the item is not ready; empty when it is.
    """

    slug: str
    label: str
    icon: str
    group: str | None = None
    status: CheckStatus = CheckStatus.READY
    reason: str = ""

    @property
    def dimmed(self) -> bool:
        """Whether the navigation shows the item muted (not ready)."""
        return self.status is not CheckStatus.READY


@dataclass(frozen=True)
class NavState:
    """The resolved navigation: the selected item and every item to draw."""

    selected: str
    items: tuple[NavItem, ...]

    def item(self, slug: str) -> NavItem:
        """Return the item with the given slug."""
        return next(item for item in self.items if item.slug == slug)

    @property
    def selected_item(self) -> NavItem:
        """The selected item."""
        return self.item(self.selected)

    @property
    def groups(self) -> tuple[str, ...]:
        """Groups in the order their first item appears; empty for flat lists."""
        return _groups(self.items)

    @property
    def group(self) -> str | None:
        """The selected item's group."""
        return self.selected_item.group

    def group_items(self, group: str | None = None) -> tuple[NavItem, ...]:
        """Items in a group (default: the selected group), in order."""
        group = self.group if group is None else group
        return tuple(item for item in self.items if item.group == group)


def _groups(items: Iterable[NavItem]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(item.group for item in items if item.group))


def resolve_nav(
    items: Sequence[NavItem],
    *,
    url: str | None = None,
    saved: str | None = None,
    default: str | None = None,
) -> NavState:
    """Decide which item is selected.

    Precedence: a valid URL value, then a valid saved selection, then the
    default, then the first item. An invalid URL value skips the saved
    selection and goes to the default; a stale saved value is ignored.

    Parameters
    ----------
    items : Sequence[NavItem]
        Every item, in display order.
    url : str | None
        The page's URL query parameter value.
    saved : str | None
        The remembered selection.
    default : str | None
        The item to select when neither is valid.

    Returns
    -------
    NavState
        The selected slug and the items.

    Raises
    ------
    ValueError
        If there are no items.
    """
    if not items:
        raise ValueError("Navigation needs at least one item.")
    slugs = {item.slug for item in items}
    candidates = (default,) if url and url not in slugs else (url, saved, default)
    selected = next(
        (value for value in candidates if value in slugs),
        items[0].slug,
    )
    return NavState(selected=selected, items=tuple(items))


def group_selection(
    items: Sequence[NavItem],
    group: str,
    remembered: Mapping[str, str] | None = None,
) -> str:
    """Return the item to select when the user switches to a group.

    Parameters
    ----------
    items : Sequence[NavItem]
        Every item, in display order.
    group : str
        The group switched to.
    remembered : Mapping[str, str] | None
        The last selected slug for each group.

    Returns
    -------
    str
        The remembered item if it is still in the group, otherwise the
        group's first item. For an unknown group, the first item overall.
    """
    in_group = [item.slug for item in items if item.group == group]
    if not in_group:
        return items[0].slug
    last = (remembered or {}).get(group)
    return last if last in in_group else in_group[0]


def with_errors(
    items: Sequence[NavItem], errors: Mapping[str, str]
) -> tuple[NavItem, ...]:
    """Mark items that raised as errors, with the error as the reason."""
    return tuple(
        replace(item, status=CheckStatus.ERROR, reason=errors[item.slug])
        if item.slug in errors
        else item
        for item in items
    )


# Text and icon markers, so status does not rely on colour alone.
_MARKERS: dict[CheckStatus, tuple[str, str, str]] = {
    CheckStatus.NOT_SET_UP: ("gray", ":material/build:", "not set up"),
    CheckStatus.NOT_APPLICABLE: (
        "gray",
        ":material/do_not_disturb_on:",
        "not applicable",
    ),
    CheckStatus.ERROR: ("red", ":material/error:", "error"),
}


def nav_label(item: NavItem) -> str:
    """Return the Markdown label for an item.

    Ready items show their icon and label. Other items are muted and show a
    status icon and text marker, for example
    ``:gray[:material/build: Backchecks · not set up]``.
    """
    if item.status is CheckStatus.READY:
        return f"{item.icon} {item.label}"
    colour, icon, text = _MARKERS[item.status]
    return f":{colour}[{icon} {item.label} · {text}]"
