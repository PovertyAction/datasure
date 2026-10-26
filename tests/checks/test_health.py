"""Summary's check health rows: status, numbers and cached headlines."""

import sys
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import polars as pl
import pytest

from datasure.checks.context import CheckContext, CheckData, PageConfig
from datasure.checks.headline import CheckHeadline
from datasure.checks.health import (
    HealthRow,
    RowState,
    clear_headline_cache,
    group_rows,
    health_rows,
    render_health_rows,
    status_only_headline,
)
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

        with patch("datasure.utils.ui_utils.section_header"):
            render_health_rows(rows, on_select=MagicMock())

        assert st.container.call_args_list == [call(border=True)] * len(rows)


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
