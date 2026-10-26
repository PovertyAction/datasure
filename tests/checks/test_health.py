"""Summary's check health rows: status, numbers and cached headlines."""

import gc
import json
import sys
import weakref
from dataclasses import replace
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import polars as pl
import pytest

from datasure.checks.context import CheckContext, CheckData, PageConfig
from datasure.checks.headline import CheckDelta, CheckHeadline, DeltaKind
from datasure.checks.health import (
    HealthRow,
    RowState,
    clear_headline_cache,
    group_rows,
    health_rows,
    render_comparison_period,
    render_health_rows,
    status_only_headline,
)
from datasure.checks.health_period import ComparisonPeriod, DeltaWindow
from datasure.utils.dataframe_utils import get_df_columns
from datasure.utils.duckdb_utils import duckdb_save_table
from datasure.utils.navigation import CheckStatus, NavItem
from datasure.utils.view_state import ViewState, save_selection

PROJECT_ID = "health01"


@pytest.fixture(autouse=True)
def mock_database_functions():
    """Override the autouse fixture from conftest to use real DuckDB files."""


@pytest.fixture(autouse=True)
def cache_dir(tmp_path):
    """Point every DuckDB database at a temporary cache directory."""

    def fake_cache_path(*parts):
        path = tmp_path.joinpath(*map(str, parts))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    with patch("datasure.utils.duckdb_utils.get_cache_path", fake_cache_path):
        yield tmp_path


@pytest.fixture(autouse=True)
def _empty_cache():
    clear_headline_cache()
    yield
    clear_headline_cache()


def _config(tmp_path: Path) -> PageConfig:
    settings = tmp_path / "settings.json"
    settings.write_text("{}")
    return PageConfig(
        page_number=1,
        page_name="HFCs",
        page_name_id="hfcs",
        survey_data_name="survey",
        survey_key="key",
        survey_id="key",
        survey_date=None,
        enumerator=None,
        team=None,
        formversion=None,
        duration=None,
        survey_target=None,
        backcheck_data_name=None,
        backcheck_date=None,
        backchecker=None,
        backchecker_team=None,
        backcheck_target_percent=None,
        tracking_data_name=None,
        setting_file=settings,
        missing_setting_file=tmp_path / "missing.json",
    )


def _ctx(config: PageConfig, data: pl.DataFrame) -> CheckContext:
    return CheckContext(PROJECT_ID, config, CheckData(data), get_df_columns(data))


DATA = pl.DataFrame({"key": ["k1", "k2"], "age": [30, 40]})

DUPLICATES = NavItem("duplicates", "Duplicates", ":material/content_copy:", "Data")
GPS = NavItem(
    "gps",
    "GPS Checks",
    ":material/location_on:",
    "Data",
    CheckStatus.NOT_APPLICABLE,
    "No GPS column found in this dataset.",
)
OUTLIERS = NavItem(
    "outliers",
    "Outliers",
    ":material/warning:",
    "Data",
    CheckStatus.NOT_SET_UP,
    "No outlier or constraint columns are set up yet.",
)
DESCRIPTIVE = NavItem("descriptive", "Descriptive Stats", ":material/bar_chart:", "X")


def _rows(ctx, items, headlines):
    return {row.item.slug: row for row in health_rows(ctx, items, headlines)}


TWO_DUPLICATES = CheckHeadline("2", "duplicate IDs", outstanding=2, resolved=1)
NO_DUPLICATES = CheckHeadline("0", "duplicate IDs", outstanding=0, resolved=3)
PROGRESS = CheckHeadline("5 / 20", "25.0% of target", informational=True)
STATUS_ONLY = status_only_headline(None)
ERROR_ITEM = NavItem(
    "enumerator",
    "Enumerator Stats",
    ":material/groups:",
    "Field team",
    CheckStatus.ERROR,
    "KeyError: 'enum'",
)


class TestHealthRows:
    def test_ready_checks_show_their_numbers_and_open(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)

        row = _rows(ctx, [DUPLICATES], {"duplicates": lambda _: TWO_DUPLICATES})[
            "duplicates"
        ]

        assert row.headline == TWO_DUPLICATES
        assert row.action == "Open →"

    def test_not_ready_checks_show_their_reason_without_numbers(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)
        headline = MagicMock(return_value=TWO_DUPLICATES)

        rows = _rows(ctx, [GPS, OUTLIERS], {"gps": headline, "outliers": headline})

        headline.assert_not_called()
        assert rows["gps"].headline is None
        assert rows["gps"].item.reason == "No GPS column found in this dataset."
        assert rows["gps"].action is None
        assert rows["outliers"].action == "Set up →"

    def test_checks_without_a_headline_show_status_only(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)

        row = _rows(ctx, [DESCRIPTIVE], {})["descriptive"]

        assert row.headline is None
        assert row.action == "Open →"
        assert (row.value, row.detail, row.resolved) == ("—", "Status only", "—")

    def test_a_number_that_fails_shows_an_error_row_only(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)
        headlines = {
            "duplicates": MagicMock(side_effect=ValueError("boom")),
            "descriptive": lambda _: PROGRESS,
        }

        rows = _rows(ctx, [DUPLICATES, DESCRIPTIVE], headlines)

        assert rows["duplicates"].headline is None
        assert "ValueError: boom" in rows["duplicates"].error
        assert rows["duplicates"].state is RowState.ERROR
        assert rows["descriptive"].headline == PROGRESS
        assert rows["descriptive"].state is RowState.NO_ISSUES


class TestRowStatus:
    """The status pill: colour, icon and label for each row state."""

    @pytest.mark.parametrize(
        ("item", "headline", "state", "colour", "label"),
        [
            (OUTLIERS, None, RowState.NOT_SET_UP, "gray", "Not set up"),
            (GPS, None, RowState.NOT_APPLICABLE, "gray", "Not applicable"),
            (ERROR_ITEM, None, RowState.ERROR, "red", "Error"),
            (DUPLICATES, TWO_DUPLICATES, RowState.FLAGGED, "orange", "Flagged"),
            (DUPLICATES, NO_DUPLICATES, RowState.NO_ISSUES, "green", "No issues"),
            (DUPLICATES, PROGRESS, RowState.NO_ISSUES, "green", "No issues"),
            (DESCRIPTIVE, STATUS_ONLY, RowState.NO_ISSUES, "green", "No issues"),
            (DESCRIPTIVE, None, RowState.READY, "blue", "Ready"),
        ],
        ids=[
            "not-set-up",
            "not-applicable",
            "status-error",
            "outstanding",
            "none-outstanding",
            "informational",
            "status-only",
            "uncounted",
        ],
    )
    def test_status_follows_the_check_status_and_outstanding_number(
        self, tmp_path, item, headline, state, colour, label
    ):
        ctx = _ctx(_config(tmp_path), DATA)
        headlines = {} if headline is None else {item.slug: lambda _: headline}

        row = _rows(ctx, [item], headlines)[item.slug]

        assert row.state is state
        pill = row.state.pill
        assert (pill.colour, pill.label) == (colour, label)
        assert pill.icon.startswith(":material/")

    def test_informational_checks_are_never_flagged(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)
        progress = CheckHeadline("5 / 20", "", outstanding=15, informational=True)

        row = _rows(ctx, [DUPLICATES], {"duplicates": lambda _: progress})

        assert row["duplicates"].state is RowState.NO_ISSUES

    def test_each_state_has_its_own_icon_and_label(self):
        pills = {RowState(state).pill for state in RowState}

        assert len({pill.icon for pill in pills}) == len(RowState)
        assert len({pill.label for pill in pills}) == len(RowState)

    @pytest.mark.parametrize(
        ("item", "action"),
        [
            (OUTLIERS, "Set up →"),
            (GPS, None),
            (ERROR_ITEM, "Open →"),
            (DUPLICATES, "Open →"),
        ],
        ids=["not-set-up", "not-applicable", "error", "ready"],
    )
    def test_action_follows_the_state(self, item, action):
        assert HealthRow(item).action == action


class TestGroupRows:
    def test_each_group_once_in_order_of_first_appearance(self):
        rows = [
            HealthRow(NavItem("a", "A", ":material/a:", "Overview")),
            HealthRow(NavItem("b", "B", ":material/b:", "Data")),
            HealthRow(NavItem("c", "C", ":material/c:", "Overview")),
        ]

        grouped = group_rows(rows)

        assert [
            (group, [row.item.slug for row in members]) for group, members in grouped
        ] == [("Overview", ["a", "c"]), ("Data", ["b"])]


class TestRenderHealthRows:
    def test_each_check_gets_its_own_bordered_container(self, monkeypatch):
        st = MagicMock()
        st.columns.side_effect = lambda spec, **_: [MagicMock() for _ in spec]
        monkeypatch.setitem(sys.modules, "streamlit", st)
        rows = [
            HealthRow(NavItem("a", "A", ":material/a:", "Overview")),
            HealthRow(NavItem("b", "B", ":material/b:", "Data")),
            HealthRow(NavItem("c", "C", ":material/c:", "Data")),
        ]

        render_health_rows(rows, on_select=MagicMock())

        assert st.container.call_args_list == [call(border=True)] * len(rows)

    @staticmethod
    def _drawn(monkeypatch, since, row=None):
        """Draw one row; return the column counts and every caption shown."""
        st = MagicMock()
        cells: list[MagicMock] = []

        def columns(spec, **_):
            made = [MagicMock() for _ in spec]
            cells.extend(made)
            return made

        st.columns.side_effect = columns
        monkeypatch.setitem(sys.modules, "streamlit", st)
        row = row or HealthRow(
            DUPLICATES, TWO_DUPLICATES, delta=CheckDelta(outstanding=2, resolved=1)
        )
        render_health_rows([row], on_select=MagicMock(), since=since)
        counts = [len(c.args[0]) for c in st.columns.call_args_list]
        captions = [c.args[0] for cell in cells for c in cell.caption.call_args_list]
        return counts, captions

    def test_changes_show_in_their_own_column(self, monkeypatch):
        counts, captions = self._drawn(monkeypatch, "yesterday")

        assert counts == [6, 6]
        assert "▲ 2 new since yesterday" in captions
        assert "+1 since yesterday" in captions

    def test_a_failed_change_shows_its_error_in_the_change_column(self, monkeypatch):
        counts, captions = self._drawn(
            monkeypatch,
            "yesterday",
            HealthRow(DUPLICATES, TWO_DUPLICATES, delta_error="ValueError: boom"),
        )

        assert counts == [6, 6]
        assert (
            ":material/error: Could not compute the change: ValueError: boom"
            in captions
        )

    def test_without_dates_the_change_column_is_hidden(self, monkeypatch):
        counts, captions = self._drawn(monkeypatch, None)

        assert counts == [5, 5]
        assert not [text for text in captions if "since" in text]


def _widget_st(monkeypatch) -> MagicMock:
    """A mock Streamlit whose radios and selectboxes return their state."""
    st = MagicMock(session_state={})

    def widget(_label, options, index=0, key=None, **_):
        return st.session_state.get(key, options[index])

    st.radio.side_effect = widget
    st.selectbox.side_effect = widget
    st.columns.side_effect = lambda spec, **_: [MagicMock() for _ in spec]
    monkeypatch.setitem(sys.modules, "streamlit", st)
    return st


class TestComparisonPeriodBox:
    def test_day_with_a_sunday_week_start_by_default(self, tmp_path, monkeypatch):
        _widget_st(monkeypatch)

        chosen = render_comparison_period(tmp_path / "project_view.json", PROJECT_ID)

        assert chosen == (ComparisonPeriod.DAY, "Sunday")

    def test_the_saved_period_is_restored_for_the_project(self, tmp_path, monkeypatch):
        view_file = tmp_path / "project_view.json"
        st = _widget_st(monkeypatch)
        render_comparison_period(view_file, PROJECT_ID)
        period_key = st.radio.call_args.kwargs["key"]
        week_key = st.selectbox.call_args.kwargs["key"]
        # The user picks Week starting on Monday.
        for key, value in ((period_key, "Week"), (week_key, "Monday")):
            st.session_state[key] = value
        for call_ in (st.radio.call_args, st.selectbox.call_args):
            call_.kwargs["on_change"]()

        st.session_state.clear()  # a new session, on any check page
        chosen = render_comparison_period(view_file, PROJECT_ID)

        assert chosen == (ComparisonPeriod.WEEK, "Monday")
        saved = json.loads(view_file.read_text())
        assert "view_state" in saved


class TestHeadlineCache:
    def test_headlines_are_cached_for_the_same_data_and_settings(self, tmp_path):
        config = _config(tmp_path)
        headline = MagicMock(return_value=TWO_DUPLICATES)

        _rows(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})
        rows = _rows(_ctx(config, DATA.clone()), [DUPLICATES], {"duplicates": headline})

        headline.assert_called_once()
        assert rows["duplicates"].headline == TWO_DUPLICATES

    def test_recomputed_when_the_data_changes(self, tmp_path):
        config = _config(tmp_path)
        headline = MagicMock(return_value=TWO_DUPLICATES)

        _rows(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})
        changed = DATA.with_columns(pl.Series("age", [30, 41]))
        _rows(_ctx(config, changed), [DUPLICATES], {"duplicates": headline})

        assert headline.call_count == 2

    def test_recomputed_when_the_page_settings_change(self, tmp_path):
        config = _config(tmp_path)
        headline = MagicMock(return_value=TWO_DUPLICATES)

        _rows(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})
        config.setting_file.write_text('{"duplicates": {"survey_id": "age"}}')
        _rows(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})

        assert headline.call_count == 2

    def test_not_recomputed_when_only_view_state_changes(self, tmp_path):
        config = _config(tmp_path)
        headline = MagicMock(return_value=TWO_DUPLICATES)

        _rows(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})
        save_selection(config.setting_file, "gps")
        ViewState(config.setting_file, "gps").save("gps_color_by", "team")
        _rows(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})

        headline.assert_called_once()

    def test_recomputed_when_a_rows_own_view_key_changes(self, tmp_path):
        # The GPS headline uses the saved LOF sliders, which are view state,
        # so its row adds them to the key.
        config = _config(tmp_path)
        ready_gps = NavItem("gps", "GPS Checks", ":material/location_on:", "Data")
        headline = MagicMock(return_value=TWO_DUPLICATES)
        view = ViewState(config.setting_file, "gps")

        def lof_settings(_ctx):
            return view.values().get("outlier_n_neighbors")

        def rows():
            health_rows(
                _ctx(config, DATA),
                [ready_gps],
                {"gps": headline},
                view_keys={"gps": lof_settings},
            )

        rows()
        view.save("gps_color_by", "team")
        rows()
        assert headline.call_count == 1

        view.save("outlier_n_neighbors", 8)
        rows()
        assert headline.call_count == 2

        # Switching back is a cache hit.
        view.forget("outlier_n_neighbors")
        rows()
        assert headline.call_count == 2

    def test_recomputed_when_a_settings_table_changes(self, tmp_path):
        config = _config(tmp_path)
        headline = MagicMock(return_value=TWO_DUPLICATES)

        _rows(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})
        duckdb_save_table(PROJECT_ID, pl.DataFrame({"a": [1]}), "outliers_hfcs", "logs")
        _rows(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})

        assert headline.call_count == 2

    def test_a_failed_headline_is_not_cached(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)
        headline = MagicMock(side_effect=[ValueError("boom"), TWO_DUPLICATES])

        _rows(ctx, [DUPLICATES], {"duplicates": headline})
        rows = _rows(ctx, [DUPLICATES], {"duplicates": headline})

        assert rows["duplicates"].headline == TWO_DUPLICATES


YESTERDAY = DeltaWindow(as_of=date(2026, 10, 25), survey_date="when")
WEEK_AGO = DeltaWindow(as_of=date(2026, 10, 19), survey_date="when")


def _delta_rows(ctx, items, headlines, deltas, window=YESTERDAY):
    rows = health_rows(ctx, items, headlines, deltas=deltas, window=window)
    return {row.item.slug: row for row in rows}


class TestDeltas:
    """Each row's change over the comparison period."""

    def test_ready_rows_get_their_delta(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)
        delta = MagicMock(return_value=CheckDelta(outstanding=2, resolved=1))

        row = _delta_rows(
            ctx,
            [DUPLICATES],
            {"duplicates": lambda _: TWO_DUPLICATES},
            {"duplicates": delta},
        )["duplicates"]

        assert row.delta == CheckDelta(outstanding=2, resolved=1)
        delta.assert_called_once_with(ctx, TWO_DUPLICATES, YESTERDAY)

    def test_no_window_means_no_deltas(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)
        delta = MagicMock(return_value=CheckDelta(outstanding=2))

        row = _delta_rows(
            ctx,
            [DUPLICATES],
            {"duplicates": lambda _: TWO_DUPLICATES},
            {"duplicates": delta},
            window=None,
        )["duplicates"]

        delta.assert_not_called()
        assert row.delta is None

    def test_rows_without_numbers_get_no_delta(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)
        delta = MagicMock(return_value=CheckDelta(outstanding=2))

        rows = _delta_rows(
            ctx,
            [GPS, DUPLICATES],
            {"duplicates": lambda _: None},
            {"gps": delta, "duplicates": delta},
        )

        delta.assert_not_called()
        assert rows["gps"].delta is None

    def test_a_failing_delta_keeps_the_row_numbers(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)

        row = _delta_rows(
            ctx,
            [DUPLICATES],
            {"duplicates": lambda _: TWO_DUPLICATES},
            {"duplicates": MagicMock(side_effect=ValueError("boom"))},
        )["duplicates"]

        assert row.headline == TWO_DUPLICATES
        assert row.delta is None
        assert row.state is RowState.FLAGGED

    def test_a_failing_delta_shows_an_error_not_no_change(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)

        row = _delta_rows(
            ctx,
            [DUPLICATES],
            {"duplicates": lambda _: TWO_DUPLICATES},
            {"duplicates": MagicMock(side_effect=ValueError("boom"))},
        )["duplicates"]

        assert row.delta_error == "ValueError: boom"
        assert row.change(SINCE) == (
            ":material/error: Could not compute the change: ValueError: boom"
        )
        assert row.resolved_change(SINCE) == ""

    def test_a_failed_delta_is_not_cached(self, tmp_path):
        config = _config(tmp_path)
        delta = MagicMock(side_effect=[ValueError("boom"), CheckDelta(outstanding=2)])
        args = ([DUPLICATES], {"duplicates": lambda _: TWO_DUPLICATES})

        _delta_rows(_ctx(config, DATA), *args, {"duplicates": delta})
        row = _delta_rows(_ctx(config, DATA), *args, {"duplicates": delta})[
            "duplicates"
        ]

        assert (row.delta, row.delta_error) == (CheckDelta(outstanding=2), "")

    def test_cached_per_period_start(self, tmp_path):
        config = _config(tmp_path)
        headline = MagicMock(return_value=TWO_DUPLICATES)
        delta = MagicMock(return_value=CheckDelta(outstanding=2))
        args = ([DUPLICATES], {"duplicates": headline}, {"duplicates": delta})

        _delta_rows(_ctx(config, DATA), *args, window=YESTERDAY)
        _delta_rows(_ctx(config, DATA), *args, window=WEEK_AGO)
        rows = _delta_rows(_ctx(config, DATA), *args, window=YESTERDAY)

        headline.assert_called_once()
        assert [c.args[2] for c in delta.call_args_list] == [YESTERDAY, WEEK_AGO]
        assert rows["duplicates"].delta == CheckDelta(outstanding=2)

    def test_a_delta_reuses_what_the_headline_computed(self, tmp_path):
        # The basis outlives the computed headline, so switching the period
        # does not compute the check's flags again.
        config = _config(tmp_path)
        flags = object()
        headline = MagicMock(return_value=replace(TWO_DUPLICATES, basis=flags))
        delta = MagicMock(return_value=CheckDelta(outstanding=2))
        args = ([DUPLICATES], {"duplicates": headline}, {"duplicates": delta})

        _delta_rows(_ctx(config, DATA), *args, window=YESTERDAY)
        _delta_rows(_ctx(config, DATA), *args, window=WEEK_AGO)

        headline.assert_called_once()
        assert [c.args[1].basis for c in delta.call_args_list] == [flags, flags]

    def test_a_basis_is_never_reused_for_other_data(self, tmp_path):
        config = _config(tmp_path)
        bases = iter([object(), object()])
        delta = MagicMock(return_value=CheckDelta(outstanding=2))

        def headline(_ctx):
            return replace(TWO_DUPLICATES, basis=next(bases))

        headlines, deltas = {"duplicates": headline}, {"duplicates": delta}
        _delta_rows(_ctx(config, DATA), [DUPLICATES], headlines, deltas)
        _delta_rows(_ctx(config, DATA.head(1)), [DUPLICATES], headlines, deltas)

        first, second = (c.args[1].basis for c in delta.call_args_list)
        assert first is not second

    def test_only_the_latest_basis_of_a_check_is_kept(self, tmp_path):
        # A basis can hold a copy of the data, so the cache must not keep
        # one per data version.
        class Flags:
            pass

        config = _config(tmp_path)
        made: list[weakref.ref] = []

        def headline(_ctx):
            flags = Flags()
            made.append(weakref.ref(flags))
            return replace(TWO_DUPLICATES, basis=flags)

        delta = MagicMock(return_value=CheckDelta(outstanding=2))
        for data in (DATA, DATA.head(1)):
            _delta_rows(
                _ctx(config, data),
                [DUPLICATES],
                {"duplicates": headline},
                {"duplicates": delta},
            )
        delta.reset_mock()
        gc.collect()

        assert [ref() is None for ref in made] == [True, False]


SINCE = "yesterday"


class TestDeltaText:
    """How a row shows its changes, with the period's "since" label."""

    @pytest.mark.parametrize(
        ("delta", "text"),
        [
            (CheckDelta(outstanding=3), "▲ 3 new since yesterday"),
            (CheckDelta(outstanding=0), "No new issues since yesterday"),
            (
                CheckDelta(outstanding=1.5, kind=DeltaKind.POINTS),
                "▲ 1.50 pp since yesterday",
            ),
            (
                CheckDelta(outstanding=-0.25, kind=DeltaKind.POINTS),
                "▼ 0.25 pp since yesterday",
            ),
            (
                CheckDelta(outstanding=0, kind=DeltaKind.POINTS),
                "No change since yesterday",
            ),
            (
                CheckDelta(outstanding=12, kind=DeltaKind.SUBMISSIONS),
                "▲ 12 new submissions since yesterday",
            ),
            (
                CheckDelta(outstanding=1, kind=DeltaKind.SUBMISSIONS),
                "▲ 1 new submission since yesterday",
            ),
            (
                CheckDelta(outstanding=0, kind=DeltaKind.SUBMISSIONS),
                "No new submissions since yesterday",
            ),
            (
                CheckDelta(outstanding=2, kind=DeltaKind.ACTIVE),
                "▲ 2 more active since yesterday",
            ),
            (
                CheckDelta(outstanding=-1, kind=DeltaKind.ACTIVE),
                "▼ 1 fewer active since yesterday",
            ),
            (
                CheckDelta(outstanding=0, kind=DeltaKind.ACTIVE),
                "No change since yesterday",
            ),
            (CheckDelta(), "—"),
        ],
    )
    def test_outstanding_change(self, delta, text):
        row = HealthRow(DUPLICATES, TWO_DUPLICATES, delta=delta)

        assert row.change(SINCE) == text

    def test_a_row_without_a_delta_shows_no_change(self):
        assert HealthRow(DUPLICATES, TWO_DUPLICATES).change(SINCE) == "—"

    def test_resolved_change(self):
        row = HealthRow(DUPLICATES, TWO_DUPLICATES, delta=CheckDelta(resolved=4))

        assert row.resolved_change(SINCE) == "+4 since yesterday"
        assert HealthRow(DUPLICATES, TWO_DUPLICATES).resolved_change(SINCE) == ""
