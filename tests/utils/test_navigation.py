"""Table-driven tests for the pure navigation resolver (no Streamlit)."""

import pytest

from datasure.utils.navigation import (
    CheckStatus,
    NavItem,
    group_selection,
    nav_label,
    resolve_nav,
    with_errors,
)

GROUPED = (
    NavItem("summary", "Summary", ":material/dashboard:", "Overview"),
    NavItem("progress", "Progress", ":material/trending_up:", "Overview"),
    NavItem("missing", "Missing Values", ":material/block:", "Data integrity"),
    NavItem(
        "gps",
        "GPS Checks",
        ":material/location_on:",
        "Data integrity",
        CheckStatus.NOT_APPLICABLE,
        "No GPS column found in this dataset.",
    ),
    NavItem(
        "backchecks",
        "Backchecks",
        ":material/fact_check:",
        "Field team",
        CheckStatus.NOT_SET_UP,
        "No backcheck dataset is selected.",
    ),
)

# Prepare Data and Corrections use flat lists: items without a group.
FLAT = (
    NavItem("household", "household", ":material/table:", None),
    NavItem(
        "members",
        "members",
        ":material/table:",
        None,
        CheckStatus.NOT_SET_UP,
        "No rows imported.",
    ),
)


class TestSelectionPrecedence:
    @pytest.mark.parametrize(
        ("url", "saved", "default", "expected"),
        [
            # A valid URL value wins over everything else.
            ("gps", "progress", "summary", "gps"),
            # Without a URL value, the saved selection is used.
            (None, "progress", "summary", "progress"),
            ("", "progress", "summary", "progress"),
            # Without either, the default is used.
            (None, None, "summary", "summary"),
            # Invalid or stale values are ignored without an error.
            ("debrief", "progress", "summary", "progress"),
            ("debrief", "removed_check", "summary", "summary"),
            (None, "removed_check", "missing", "missing"),
            # Not-ready checks can still be selected.
            ("backchecks", None, "summary", "backchecks"),
            # With no valid default, the first item is used.
            (None, None, None, "summary"),
            (None, None, "not_a_check", "summary"),
        ],
    )
    def test_grouped(self, url, saved, default, expected):
        state = resolve_nav(GROUPED, url=url, saved=saved, default=default)

        assert state.selected == expected
        assert state.selected_item.slug == expected

    @pytest.mark.parametrize(
        ("url", "saved", "expected"),
        [
            ("members", "household", "members"),
            (None, "members", "members"),
            ("gone", None, "household"),
        ],
    )
    def test_flat(self, url, saved, expected):
        state = resolve_nav(FLAT, url=url, saved=saved)

        assert state.selected == expected
        assert state.groups == ()

    def test_no_items_is_an_error(self):
        with pytest.raises(ValueError, match="at least one item"):
            resolve_nav(())


class TestGroups:
    def test_groups_keep_catalogue_order(self):
        state = resolve_nav(GROUPED)

        assert state.groups == ("Overview", "Data integrity", "Field team")

    def test_selected_group_and_its_items(self):
        state = resolve_nav(GROUPED, url="gps")

        assert state.group == "Data integrity"
        assert [item.slug for item in state.group_items()] == ["missing", "gps"]

    @pytest.mark.parametrize(
        ("group", "remembered", "expected"),
        [
            # Switching group selects the first check in that group...
            ("Data integrity", {}, "missing"),
            ("Field team", None, "backchecks"),
            # ...or the one last selected there.
            ("Data integrity", {"Data integrity": "gps"}, "gps"),
            ("Overview", {"Overview": "progress"}, "progress"),
            # A remembered check that is gone or in another group is ignored.
            ("Overview", {"Overview": "gps"}, "summary"),
            ("Overview", {"Overview": "removed"}, "summary"),
            # An unknown group falls back to the first item.
            ("Exploration", {}, "summary"),
        ],
    )
    def test_group_selection(self, group, remembered, expected):
        assert group_selection(GROUPED, group, remembered) == expected


class TestDimmingAndReasons:
    @pytest.mark.parametrize(
        ("slug", "dimmed", "reason"),
        [
            ("summary", False, ""),
            ("gps", True, "No GPS column found in this dataset."),
            ("backchecks", True, "No backcheck dataset is selected."),
        ],
    )
    def test_items_carry_dimmed_state_and_reason(self, slug, dimmed, reason):
        state = resolve_nav(GROUPED)
        item = state.item(slug)

        assert item.dimmed is dimmed
        assert item.reason == reason

    def test_errors_mark_items_with_the_error_status(self):
        items = with_errors(GROUPED, {"missing": "ValueError: boom"})

        missing = next(item for item in items if item.slug == "missing")
        assert missing.status is CheckStatus.ERROR
        assert missing.reason == "ValueError: boom"
        assert missing.dimmed
        # Other items are unchanged.
        assert items[0] == GROUPED[0]

    def test_errors_for_unknown_items_are_ignored(self):
        assert with_errors(GROUPED, {"gone": "boom"}) == GROUPED


class TestNavLabel:
    @pytest.mark.parametrize(
        ("status", "marker"),
        [
            (CheckStatus.NOT_SET_UP, "not set up"),
            (CheckStatus.NOT_APPLICABLE, "not applicable"),
            (CheckStatus.ERROR, "error"),
        ],
    )
    def test_not_ready_labels_have_a_text_marker_and_are_muted(self, status, marker):
        label = nav_label(NavItem("gps", "GPS Checks", ":material/x:", None, status))

        assert "GPS Checks" in label
        assert marker in label
        assert ":material/" in label

    def test_ready_label_shows_icon_and_label_only(self):
        item = NavItem("gps", "GPS Checks", ":material/location_on:", None)

        assert nav_label(item) == ":material/location_on: GPS Checks"
