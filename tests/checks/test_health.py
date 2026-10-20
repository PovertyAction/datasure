"""Summary's check health cards: status, headline and cached headlines."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks.context import CheckContext, CheckData, PageConfig
from datasure.checks.health import clear_headline_cache, health_cards
from datasure.utils.dataframe_utils import get_df_columns
from datasure.utils.duckdb_utils import duckdb_save_table
from datasure.utils.navigation import CheckStatus, NavItem

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


def _cards(ctx, items, headlines):
    return {card.item.slug: card for card in health_cards(ctx, items, headlines)}


class TestHealthCards:
    def test_ready_checks_show_their_headline_and_open(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)

        card = _cards(ctx, [DUPLICATES], {"duplicates": lambda _: "2 duplicate IDs"})[
            "duplicates"
        ]

        assert card.headline == "2 duplicate IDs"
        assert card.action == "Open →"

    def test_not_ready_checks_show_their_reason_without_a_headline(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)
        headline = MagicMock(return_value="12 outliers")

        cards = _cards(ctx, [GPS, OUTLIERS], {"gps": headline, "outliers": headline})

        headline.assert_not_called()
        assert cards["gps"].headline is None
        assert cards["gps"].item.reason == "No GPS column found in this dataset."
        assert cards["gps"].action is None
        assert cards["outliers"].action == "Set up →"

    def test_checks_without_a_headline_show_status_only(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)

        card = _cards(ctx, [DESCRIPTIVE], {})["descriptive"]

        assert card.headline is None
        assert card.action == "Open →"

    def test_a_headline_that_raises_is_reported_on_its_card_only(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)
        headlines = {
            "duplicates": MagicMock(side_effect=ValueError("boom")),
            "descriptive": lambda _: "fine",
        }

        cards = _cards(ctx, [DUPLICATES, DESCRIPTIVE], headlines)

        assert cards["duplicates"].headline is None
        assert "ValueError: boom" in cards["duplicates"].headline_error
        assert cards["descriptive"].headline == "fine"


class TestHeadlineCache:
    def test_headlines_are_cached_for_the_same_data_and_settings(self, tmp_path):
        config = _config(tmp_path)
        headline = MagicMock(return_value="2 duplicate IDs")

        _cards(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})
        cards = _cards(
            _ctx(config, DATA.clone()), [DUPLICATES], {"duplicates": headline}
        )

        headline.assert_called_once()
        assert cards["duplicates"].headline == "2 duplicate IDs"

    def test_recomputed_when_the_data_changes(self, tmp_path):
        config = _config(tmp_path)
        headline = MagicMock(return_value="x")

        _cards(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})
        changed = DATA.with_columns(pl.Series("age", [30, 41]))
        _cards(_ctx(config, changed), [DUPLICATES], {"duplicates": headline})

        assert headline.call_count == 2

    def test_recomputed_when_the_page_settings_change(self, tmp_path):
        config = _config(tmp_path)
        headline = MagicMock(return_value="x")

        _cards(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})
        config.setting_file.write_text('{"duplicates": {"survey_id": "age"}}')
        _cards(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})

        assert headline.call_count == 2

    def test_recomputed_when_a_settings_table_changes(self, tmp_path):
        config = _config(tmp_path)
        headline = MagicMock(return_value="x")

        _cards(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})
        duckdb_save_table(PROJECT_ID, pl.DataFrame({"a": [1]}), "outliers_hfcs", "logs")
        _cards(_ctx(config, DATA), [DUPLICATES], {"duplicates": headline})

        assert headline.call_count == 2

    def test_a_failed_headline_is_not_cached(self, tmp_path):
        ctx = _ctx(_config(tmp_path), DATA)
        headline = MagicMock(side_effect=[ValueError("boom"), "2 duplicate IDs"])

        _cards(ctx, [DUPLICATES], {"duplicates": headline})
        cards = _cards(ctx, [DUPLICATES], {"duplicates": headline})

        assert cards["duplicates"].headline == "2 duplicate IDs"
