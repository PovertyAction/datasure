"""Data dictionary and skip-logic stats built from an imported SurveyCTO form."""

import io
from unittest.mock import Mock, patch

import duckdb
import polars as pl
import pytest
from openpyxl import load_workbook

from datasure.connectors.scto import FormConfig, SurveyCTOClient
from datasure.processing.form_dictionary import (
    build_form_dictionary,
    dictionary_xlsx,
    form_table,
    sentinels_from_missing_codes,
)
from datasure.surveycto.cast import cast_wide
from datasure.surveycto.xml_contract import parse_contract
from datasure.utils.duckdb_utils import (
    database_path,
    duckdb_get_table,
    load_form_definition,
)
from tests.surveycto.farm_form import ROWS, XML

MISSING_CODES = pl.DataFrame(
    {"label": ["Don't know", "Refused", "Stata"], "codes": ["-99", "-88.0", ".d, -9.5"]}
)


@pytest.fixture(autouse=True)
def mock_database_functions():
    """Use real DuckDB files instead of the conftest mocks."""


@pytest.fixture
def project(tmp_path):
    """A project with the farm form imported from a mocked SurveyCTO server."""

    def cache_path(project_id, *parts):
        path = tmp_path.joinpath(project_id, *parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    with patch("datasure.utils.duckdb_utils.get_cache_path", side_effect=cache_path):
        client = SurveyCTOClient("proj")
        client._scto_client = Mock()
        client._scto_client.list_datasets.return_value = []
        client._scto_client.download_form_xml.return_value = XML.encode()
        client._scto_client.download_form_data_json.return_value = ROWS
        client.import_data(
            FormConfig(alias="farm", form_id="farm", server="srv", username="a@b.org")
        )
        yield "proj"


@pytest.fixture
def built(project):
    raw = duckdb_get_table(project, "farm", "raw")
    return build_form_dictionary(project, "farm", raw, MISSING_CODES)


def test_sentinels_are_the_projects_whole_number_codes():
    assert sentinels_from_missing_codes(MISSING_CODES) == {
        -99: "Don't know",
        -88: "Refused",
    }


def test_a_code_under_two_labels_raises():
    codes = pl.DataFrame({"label": ["Don't know", "N/A"], "codes": ["-99", "-99, -97"]})
    with pytest.raises(ValueError, match="-99 is listed under both"):
        sentinels_from_missing_codes(codes)


def test_no_missing_codes_no_sentinels():
    empty = pl.DataFrame(schema={"label": pl.String, "codes": pl.String})
    assert sentinels_from_missing_codes(empty) == {}


def test_form_table_restores_the_cast_table(project):
    _, arrow_schema = load_form_definition(project, "farm")
    table = form_table(duckdb_get_table(project, "farm", "raw"), arrow_schema)

    cast = cast_wide(ROWS, parse_contract(XML.encode()))
    assert table.schema.equals(cast.schema, check_metadata=True)
    assert table.to_pylist() == cast.to_pylist()


def test_form_table_raises_when_raw_and_schema_differ(project):
    _, arrow_schema = load_form_definition(project, "farm")
    raw = duckdb_get_table(project, "farm", "raw").drop("area")
    with pytest.raises(ValueError, match=r"missing \['area'\]"):
        form_table(raw, arrow_schema)


def test_no_definition_no_dictionary(project):
    raw = duckdb_get_table(project, "farm", "raw")
    assert build_form_dictionary(project, "listing", raw, MISSING_CODES) is None


def test_a_project_from_1_3_0a4_refreshes_and_gets_a_dictionary(tmp_path):
    """1.3.0a4 kept the form XML without the cast schema.

    The first refresh on this version upgrades the table and stores a schema,
    so the import succeeds and the dictionary can be built. The refresh
    downloads every submission again, as the import does today.
    """

    def cache_path(project_id, *parts):
        path = tmp_path.joinpath(project_id, *parts)
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    config = FormConfig(alias="farm", form_id="farm", server="srv", username="a@b.org")
    with patch("datasure.utils.duckdb_utils.get_cache_path", side_effect=cache_path):
        client = SurveyCTOClient("proj")
        client._scto_client = Mock()
        client._scto_client.list_datasets.return_value = []
        client._scto_client.download_form_xml.return_value = XML.encode()
        client._scto_client.download_form_data_json.return_value = ROWS[:1]
        client.import_data(config)

        # The logs table as 1.3.0a4 left it: no arrow_schema column.
        with duckdb.connect(database_path("proj", "logs")) as conn:
            conn.execute(
                "CREATE TABLE a4 (alias VARCHAR, form_id VARCHAR, "
                "formdef_version VARCHAR, xml BLOB, downloaded_at TIMESTAMP, "
                "PRIMARY KEY (alias, formdef_version))"
            )
            conn.execute(
                "INSERT INTO a4 SELECT alias, form_id, formdef_version, xml, "
                "downloaded_at FROM form_definitions"
            )
            conn.execute("DROP TABLE form_definitions")
            conn.execute("ALTER TABLE a4 RENAME TO form_definitions")
        raw = duckdb_get_table("proj", "farm", "raw")
        assert build_form_dictionary("proj", "farm", raw, MISSING_CODES) is None

        client._scto_client.download_form_data_json.return_value = ROWS
        client.import_data(config)

        raw = duckdb_get_table("proj", "farm", "raw")
        assert len(raw) == len(ROWS)
        built = build_form_dictionary("proj", "farm", raw, MISSING_CODES)
        assert built is not None
        assert {row["variable"] for row in built.stats} <= set(raw.columns)


def test_stats_follow_skip_logic_and_set_codes_apart(built):
    stats = {row["variable"]: row for row in built.stats}
    # area is asked only when plots > 0; the row with plots = -99 skips it.
    assert stats["area"]["eligible"] == 1
    assert stats["area"]["skipped_by_logic"] == 1
    assert stats["plots"]["sentinel"] == 1
    assert "Don't know" in stats["plots"]["sentinel_detail"]


def test_pii_from_the_form_rules_trusting_publishable(built):
    status = {
        name: entry["pii"]["status"]
        for name, entry in built.dictionary["variables"].items()
    }
    assert status["village"] == "cleared_by_form"
    assert status["deviceid"] == "contains_pii"
    assert status["owner"] == "may_contain_pii"


def test_dictionary_workbook_hides_flagged_values(built):
    workbook = load_workbook(io.BytesIO(dictionary_xlsx(built)), read_only=True)
    assert workbook.sheetnames == [
        "Instructions",
        "Variables",
        "Choices",
        "Summary stats",
    ]
    cells = {
        str(cell)
        for sheet in workbook.worksheets
        for row in sheet.iter_rows(values_only=True)
        for cell in row
        if cell is not None
    }
    assert not any("Ana Maria" in c or "3104567890" in c for c in cells)


def test_dictionary_workbook_lists_each_choice_list_once(built):
    """Choices holds each select's list once; Variables names it per column."""
    workbook = load_workbook(io.BytesIO(dictionary_xlsx(built)), read_only=True)
    choices = list(workbook["Choices"].iter_rows(values_only=True))
    assert choices == [
        ("list_name", "value", "label"),
        ("crop", "01", "Maize"),
        ("crop", "02", "Rice"),
        ("tools", "1", "Hoe"),
        ("tools", "2", "Plough"),
        ("tools", "77", "Other"),
        ("plot_crop", "1", "Maize"),
        ("plot_crop", "2", "Rice"),
    ]

    header, *rows = workbook["Variables"].iter_rows(values_only=True)
    named = {row[0]: row[header.index("choices")] for row in rows}
    assert named["crop"] == "crop"
    assert named["tools_77"] == "tools"
    assert named["plot_crop_2_1"] == "plot_crop"
    assert named["plots"] is None


def _variables(workbook) -> dict[str, dict]:
    header, *rows = workbook["Variables"].iter_rows(values_only=True)
    # Read-only rows drop trailing empty cells.
    padded = [(*row, *[None] * (len(header) - len(row))) for row in rows]
    return {row[0]: dict(zip(header, row, strict=True)) for row in padded}


def test_a_calculate_shows_its_formula_as_calculation_not_label(built):
    workbook = load_workbook(io.BytesIO(dictionary_xlsx(built)), read_only=True)
    variables = _variables(workbook)
    assert variables["duration"]["label"] is None
    assert variables["duration"]["calculation"] == "duration()"
    assert variables["owner"]["label"] == "Owner"
    assert variables["owner"]["calculation"] is None


def test_final_data_columns_merge_into_variables(built):
    """Stata names and final counts join by name; prep-added columns go last."""
    final = {
        "owner": {"stata_name": "owner", "final_missing_rate": 0.5, "final_unique": 2},
        "visit": {
            "stata_name": "visit_date",
            "final_missing_rate": 0.0,
            "final_unique": 1,
        },
        "plots_x2": {
            "stata_name": "plots_x2",
            "final_missing_rate": 0.0,
            "final_unique": 2,
        },
    }
    workbook = load_workbook(io.BytesIO(dictionary_xlsx(built, final)), read_only=True)
    variables = _variables(workbook)
    assert variables["owner"]["final_unique"] == 2
    assert variables["visit"]["stata_name"] == "visit_date"
    # In raw but not in the final data: dropped in Prepare Data.
    assert variables["area"]["stata_name"] is None
    # Only in the final data: added in Prepare Data, with no form details.
    assert list(variables)[-1] == "plots_x2"
    assert variables["plots_x2"]["type"] is None


def test_instructions_describe_every_variables_column(built):
    workbook = load_workbook(io.BytesIO(dictionary_xlsx(built)), read_only=True)
    header, *rows = workbook["Instructions"].iter_rows(values_only=True)
    assert header == ("sheet", "column", "description")
    described = [column for sheet, column, _ in rows if sheet == "Variables" and column]
    assert described == list(_variables(workbook)["owner"])
    assert all(description for *_, description in rows)
