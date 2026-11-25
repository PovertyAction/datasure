"""Dictionary, PII rules, stats and the workbook from in-memory objects."""

import io

import pytest
from openpyxl import load_workbook

from datasure.surveycto.cast import cast_wide
from datasure.surveycto.codebook import save_codebook
from datasure.surveycto.dictionary import build_dictionary
from datasure.surveycto.pii import PiiConfig, attach, classify, shows_values
from datasure.surveycto.questions import build_questions
from datasure.surveycto.stats import stats_rows
from datasure.surveycto.xml_contract import parse_contract
from tests.surveycto.farm_form import ROWS, SENTINELS, XML

# Media SurveyCTO fills itself: no body control, typed by the bind's class.
MEDIA_XML = """<?xml version="1.0"?>
<h:html xmlns="http://www.w3.org/2002/xforms" xmlns:h="http://www.w3.org/1999/xhtml">
  <h:head><h:title>Media form</h:title><model>
    <instance><media id="media" version="1">
      <photo/><all_comments/><text_audit/><audio_audit/>
      <meta><instanceID/></meta>
    </media></instance>
    <bind nodeset="/media/photo" type="binary"/>
    <bind nodeset="/media/all_comments" type="binary" appearance="class=comments"/>
    <bind nodeset="/media/text_audit" type="binary" appearance="class=textAudit;p=100"/>
    <bind nodeset="/media/audio_audit" type="binary" appearance="class=audioAudit;s=10"/>
    <bind nodeset="/media/meta/instanceID" type="string" calculate="concat('uuid:', uuid())"/>
  </model></h:head>
  <h:body>
    <upload ref="/media/photo" mediatype="image/*"><label>Photo</label></upload>
  </h:body>
</h:html>
"""


@pytest.fixture
def built(tmp_path):
    path = tmp_path / "farm.xml"
    path.write_text(XML, encoding="utf-8")
    contract = parse_contract(path)
    questions = build_questions(contract)
    table = cast_wide(ROWS, contract)
    vardict = build_dictionary(table, questions, contract, SENTINELS)
    blocks = classify(table, vardict, questions, PiiConfig(), None)
    attach(vardict, blocks, questions, [])
    return table, questions, vardict, blocks


def test_rules_alone_leave_open_columns_flagged_unscanned(built):
    *_, blocks = built
    assert blocks["owner"] == {
        "status": "may_contain_pii",
        "basis": ["type:text", "unscanned"],
    }
    assert not shows_values(blocks["owner"]["status"])
    # The rules still decide what they can.
    assert blocks["village"]["status"] == "cleared_by_form"
    assert blocks["plots"]["status"] == "cleared_by_form"
    assert blocks["deviceid"]["status"] == "contains_pii"
    assert blocks["visit"]["status"] == "whitelisted"


def test_stats_rows_follow_skip_logic(built):
    table, questions, vardict, _ = built
    stats = {r["variable"]: r for r in stats_rows(table, questions, vardict, SENTINELS)}
    area = stats["area"]
    assert area["relevance"]
    assert area["eligible"] + area["skipped_by_logic"] == area["rows"]


def test_save_codebook_to_a_file_object(built):
    table, questions, vardict, _ = built
    buffer = io.BytesIO()
    save_codebook(buffer, vardict, stats_rows(table, questions, vardict, SENTINELS))

    workbook = load_workbook(io.BytesIO(buffer.getvalue()), read_only=True)
    assert workbook.sheetnames == [
        "Instructions",
        "Variables",
        "Choices",
        "Summary stats",
    ]


def test_parse_contract_reads_bytes(tmp_path):
    path = tmp_path / "farm.xml"
    path.write_text(XML, encoding="utf-8")
    assert (
        parse_contract(XML.encode()).nodes.keys() == parse_contract(path).nodes.keys()
    )


def test_media_surveycto_fills_itself_gets_a_dictionary():
    """Comments and audit fields have no control; their bind class names the type."""
    contract = parse_contract(MEDIA_XML.encode())
    questions = build_questions(contract)
    types = {q["variable_name"]: q["type"] for q in questions}
    assert types["all_comments"] == "comments"
    assert types["text_audit"] == "text audit"
    assert types["audio_audit"] == "audio audit"

    url = "https://example.surveycto.com/api/v1/forms/files/{}/{}"
    row = {
        "KEY": "uuid:1",
        "SubmissionDate": "Mar 7, 2025 4:06:12 PM",
        **{name: url.format(name, "f.csv") for name in types if name != "KEY"},
    }
    table = cast_wide([row], contract)
    vardict = build_dictionary(table, questions, contract, {})
    attach(
        vardict, classify(table, vardict, questions, PiiConfig(), None), questions, []
    )
    buffer = io.BytesIO()
    save_codebook(buffer, vardict, stats_rows(table, questions, vardict, {}))
    assert load_workbook(io.BytesIO(buffer.getvalue()), read_only=True).sheetnames
