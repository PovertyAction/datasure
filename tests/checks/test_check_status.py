"""Each check module's status function: config and data shape only.

Status functions decide whether the check page shows a check as ready, not
set up or not applicable, and why. They never compute check results.
"""

import json
from unittest.mock import patch

import polars as pl
import pytest

from datasure.checks.backchecks.report_ui import backchecks_status
from datasure.checks.catalogue import get_check
from datasure.checks.context import CheckContext, CheckData, PageConfig
from datasure.checks.duplicates import duplicates_status
from datasure.checks.enumerator.report_ui import enumerator_status
from datasure.checks.gpschecks.compute import find_gps_columns
from datasure.checks.gpschecks.report_ui import gpschecks_status
from datasure.checks.outliers.report_ui import outliers_status
from datasure.utils.dataframe_utils import get_df_columns
from datasure.utils.duckdb_utils import duckdb_save_table
from datasure.utils.navigation import CheckStatus

PROJECT_ID = "status01"
PAGE = "hfcs"

READY = CheckStatus.READY
NOT_SET_UP = CheckStatus.NOT_SET_UP
NOT_APPLICABLE = CheckStatus.NOT_APPLICABLE


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


@pytest.fixture
def settings_file(tmp_path):
    return tmp_path / "page_hfcs_settings.json"


SURVEY = pl.DataFrame(
    {
        "key": ["k1", "k2"],
        "hhid": ["h1", "h2"],
        "age": [30, 41],
        "enum": ["a", "b"],
    }
)


def _ctx(settings_file, data: pl.DataFrame, **config) -> CheckContext:
    """A check page context for status functions read through the catalogue."""
    values = dict.fromkeys(
        (
            "survey_id",
            "survey_date",
            "enumerator",
            "team",
            "formversion",
            "duration",
            "survey_target",
            "backcheck_data_name",
            "backcheck_date",
            "backchecker",
            "backchecker_team",
            "backcheck_target_percent",
            "tracking_data_name",
        )
    )
    values.update(config)
    page = PageConfig(
        page_number=1,
        page_name=PAGE,
        page_name_id=PAGE,
        survey_data_name="survey",
        survey_key="key",
        setting_file=settings_file,
        missing_setting_file=settings_file.with_name("missing.json"),
        **values,
    )
    return CheckContext(PROJECT_ID, page, CheckData(data), get_df_columns(data))


ROW_COUNT_CHECKS = ["summary", "progress", "missing", "descriptive"]


class TestAlwaysReadyChecks:
    """Checks that work on any survey data with rows share one status."""

    @pytest.mark.parametrize("slug", ROW_COUNT_CHECKS)
    def test_ready_with_survey_rows(self, slug, settings_file):
        assert get_check(slug).status(_ctx(settings_file, SURVEY)) == (READY, "")

    @pytest.mark.parametrize("slug", ROW_COUNT_CHECKS)
    def test_not_applicable_without_rows(self, slug, settings_file):
        status, reason = get_check(slug).status(_ctx(settings_file, SURVEY.clear()))

        assert status is NOT_APPLICABLE
        assert "no rows" in reason


class TestDuplicatesStatus:
    def test_ready_with_a_survey_id_in_the_page_config(self, settings_file):
        assert duplicates_status(settings_file, {"survey_id": "hhid"}) == (READY, "")

    def test_not_set_up_without_a_survey_id(self, settings_file):
        status, reason = duplicates_status(settings_file, {"survey_id": None})

        assert status is NOT_SET_UP
        assert "survey ID" in reason

    def test_a_saved_survey_id_counts(self, settings_file):
        settings_file.write_text(json.dumps({"duplicates": {"survey_id": "hhid"}}))

        assert duplicates_status(settings_file, {"survey_id": None}) == (READY, "")


class TestOutliersStatus:
    def test_not_applicable_without_numeric_columns(self):
        columns = get_df_columns(SURVEY.drop("age"))

        status, reason = outliers_status(PROJECT_ID, PAGE, columns)

        assert status is NOT_APPLICABLE
        assert "numeric" in reason

    def test_not_set_up_without_configured_columns(self):
        status, reason = outliers_status(PROJECT_ID, PAGE, get_df_columns(SURVEY))

        assert status is NOT_SET_UP
        assert "columns" in reason

    def test_ready_with_configured_columns(self):
        duckdb_save_table(
            PROJECT_ID,
            pl.DataFrame({"search_type": ["exact"], "column_name": ["age"]}),
            f"outliers_{PAGE}",
            "logs",
        )

        assert outliers_status(PROJECT_ID, PAGE, get_df_columns(SURVEY)) == (
            READY,
            "",
        )


class TestFindGpsColumns:
    @pytest.mark.parametrize(
        ("columns", "expected"),
        [
            ({"household_latitude": [1.0], "household_longitude": [2.0]}, 2),
            ({"gps_lat": [1.0]}, 1),
            ({"gpsLatitude": [1.0]}, 1),
            ({"geopoint": ["1 2 3 4"]}, 1),
            ({"relationship": ["x"], "long_answer": ["y"], "age": [3]}, 0),
        ],
    )
    def test_by_name(self, columns, expected):
        assert len(find_gps_columns(pl.DataFrame(columns))) == expected

    def test_by_surveycto_geopoint_values(self):
        data = pl.DataFrame({"where": ["-1.2921 36.8219 1700.5 5.0", None]})

        assert find_gps_columns(data) == ["where"]


class TestGpsChecksStatus:
    def test_not_applicable_without_a_gps_column(self):
        status, reason = gpschecks_status(PROJECT_ID, PAGE, SURVEY)

        assert status is NOT_APPLICABLE
        assert reason == "No GPS column found in this dataset."

    def test_not_set_up_without_a_gps_configuration(self):
        data = SURVEY.with_columns(pl.lit(1.0).alias("gps_latitude"))

        status, reason = gpschecks_status(PROJECT_ID, PAGE, data)

        assert status is NOT_SET_UP
        assert "GPS" in reason

    def test_ready_with_a_gps_configuration(self):
        data = SURVEY.with_columns(pl.lit(1.0).alias("gps_latitude"))
        duckdb_save_table(
            PROJECT_ID,
            pl.DataFrame({"alias": ["household"], "latitude_column": ["gps_latitude"]}),
            f"gps_columns_{PAGE}",
            "logs",
        )

        assert gpschecks_status(PROJECT_ID, PAGE, data) == (READY, "")

    @pytest.mark.parametrize(
        "config",
        [
            {"alias": ["home"], "latitude_column": ["y"], "longitude_column": ["x"]},
            {"alias": ["home"], "gps_column": ["where"]},
        ],
    )
    def test_ready_when_configured_columns_exist_whatever_their_names(self, config):
        """A configured project is never locked out by the name heuristic."""
        data = SURVEY.with_columns(
            pl.lit(1.0).alias("y"), pl.lit(2.0).alias("x"), pl.lit("n/a").alias("where")
        )
        assert not find_gps_columns(data)
        duckdb_save_table(
            PROJECT_ID, pl.DataFrame(config), f"gps_columns_{PAGE}", "logs"
        )

        assert gpschecks_status(PROJECT_ID, PAGE, data) == (READY, "")

    def test_configured_columns_missing_from_the_data_do_not_count(self):
        duckdb_save_table(
            PROJECT_ID,
            pl.DataFrame(
                {"alias": ["home"], "latitude_column": ["y"], "longitude_column": ["x"]}
            ),
            f"gps_columns_{PAGE}",
            "logs",
        )

        status, _ = gpschecks_status(PROJECT_ID, PAGE, SURVEY)

        assert status is NOT_APPLICABLE


class TestEnumeratorStatus:
    def test_ready_with_enumerator_and_date(self, settings_file):
        config = {"enumerator": "enum", "survey_date": "date"}

        assert enumerator_status(settings_file, config) == (READY, "")

    @pytest.mark.parametrize(
        ("config", "missing"),
        [
            ({"enumerator": None, "survey_date": "date"}, "enumerator"),
            ({"enumerator": "enum", "survey_date": None}, "date"),
        ],
    )
    def test_not_set_up_without_enumerator_or_date(
        self, settings_file, config, missing
    ):
        status, reason = enumerator_status(settings_file, config)

        assert status is NOT_SET_UP
        assert missing in reason

    def test_saved_settings_count(self, settings_file):
        settings_file.write_text(
            json.dumps({"enumerators": {"enumerator": "enum", "survey_date": "d"}})
        )

        assert enumerator_status(settings_file, {}) == (READY, "")


class TestBackchecksStatus:
    def test_not_set_up_without_a_backcheck_dataset(self):
        status, reason = backchecks_status(None, None)

        assert status is NOT_SET_UP
        assert "Configure Checks" in reason

    def test_not_set_up_when_the_dataset_is_not_imported(self):
        status, reason = backchecks_status("bc", pl.DataFrame())

        assert status is NOT_SET_UP
        assert "Import Data" in reason

    def test_not_applicable_when_the_dataset_has_no_rows(self):
        status, reason = backchecks_status("bc", SURVEY.clear())

        assert status is NOT_APPLICABLE
        assert reason.startswith("**bc** has no rows")

    def test_ready_with_backcheck_rows(self):
        assert backchecks_status("bc", SURVEY) == (READY, "")
