"""Stage 4: wide JSON cast to a typed Arrow table through the contract."""

import datetime as dt

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from datasure.surveycto.cast import cast_wide
from datasure.surveycto.xml_contract import parse_contract
from tests.surveycto.farm_form import ROWS as _ROWS
from tests.surveycto.farm_form import XML as _XML


@pytest.fixture
def contract(tmp_path):
    path = tmp_path / "farm.xml"
    path.write_text(_XML, encoding="utf-8")
    return parse_contract(path)


@pytest.fixture
def table(contract):
    return cast_wide(_ROWS, contract)


def _col(table, name):
    return table.column(name).to_pylist()


def test_row_count(table):
    assert table.num_rows == len(_ROWS)


def test_types(table):
    types = {f.name: f.type for f in table.schema}
    utc_ms = pa.timestamp("ms", tz="UTC")
    assert types["SubmissionDate"] == utc_ms
    assert types["starttime"] == utc_ms
    assert types["duration"] == pa.int64()
    assert types["deviceid"] == pa.string()
    assert types["KEY"] == pa.string()
    assert types["formdef_version"] == pa.string()
    assert types["owner"] == pa.string()
    assert types["plots"] == pa.int64()
    assert types["area"] == pa.float64()
    assert types["visit"] == pa.date32()
    assert types["crop"] == pa.string()
    assert types["tools_2"] == pa.int8()
    assert types["photo"] == pa.string()
    assert types["plot_size_1"] == pa.float64()


def test_values(table):
    assert _col(table, "SubmissionDate")[0] == dt.datetime(
        2025, 3, 7, 16, 6, 12, tzinfo=dt.UTC
    )
    assert _col(table, "visit") == [dt.date(2025, 3, 6), None]
    assert _col(table, "plots") == [2, -99]  # sentinels stay ints
    assert _col(table, "crop") == ["01", "02"]  # codes stay strings
    assert _col(table, "duration") == [478, 540]


def test_empty_and_absent_are_null(table):
    assert _col(table, "owner") == ["Ana Maria Gomez Restrepo", None]
    assert _col(table, "area") == [1.5, None]
    assert _col(table, "plot_size_2") == [None, None]


def test_unchosen_binary_is_zero_when_a_sibling_is_chosen(table):
    # Row 0 chose tools 2; row 1 answered no tools option at all -> null.
    assert _col(table, "tools_2") == [1, None]


def test_binary_columns_for_every_choice_exist(table):
    """A choice nobody picked still gets its column, 0 where it was answered."""
    assert _col(table, "tools_1") == [0, None]
    assert _col(table, "tools_77") == [0, None]


def test_binary_zero_fill_is_per_repeat_instance(table):
    assert _col(table, "plot_crop_1_1") == [1, None]
    assert _col(table, "plot_crop_2_1") == [0, None]
    assert _col(table, "plot_crop_1_2") == [None, 0]
    assert _col(table, "plot_crop_2_2") == [None, 1]


def test_column_order_system_then_form_order(table):
    names = table.schema.names
    assert names[0] == "KEY"
    assert (
        names.index("owner")
        < names.index("plots")
        < names.index("tools_1")
        < names.index("tools_2")
    )
    assert names.index("tools_2") < names.index("tools_77") < names.index("photo")


def test_field_metadata(table):
    meta = table.schema.field("plot_size_1").metadata
    assert meta[b"xml_type"] == b"decimal"
    assert meta[b"node_path"] == b"plot/plot_size"
    assert meta[b"repeat_path"] == b'["plot"]'
    assert table.schema.field("KEY").metadata[b"system"] == b"true"


def test_parquet_round_trip_keeps_schema(table, tmp_path):
    out = tmp_path / "farm.parquet"
    pq.write_table(table, out)
    assert pq.read_schema(out).equals(table.schema, check_metadata=True)


def _fallback(table, name):
    return table.schema.field(name).metadata.get(b"cast_fallback", b"").decode()


def test_typed_columns_carry_no_fallback(table):
    assert all(b"cast_fallback" not in (f.metadata or {}) for f in table.schema)


def test_unparseable_value_keeps_column_as_text(contract):
    rows = [dict(_ROWS[0], area="about two"), _ROWS[1]]
    table = cast_wide(rows, contract)
    assert table.schema.field("area").type == pa.string()
    assert _col(table, "area") == ["about two", None]
    assert _fallback(table, "area") == "1 of 1 values do not parse as double"
    assert table.schema.field("area").metadata[b"node_path"] == b"area"


@pytest.mark.parametrize("value", ["1_0", "1_000", "nan", "inf", " 3 ", "+3", "٣"])
def test_python_literal_syntax_is_not_a_number(contract, value):
    table = cast_wide([dict(_ROWS[0], plots=value, area=value)], contract)
    assert _col(table, "plots") == [value]
    assert _col(table, "area") == [value]
    assert _fallback(table, "plots") == "1 of 1 values do not parse as int64"
    assert _fallback(table, "area") == "1 of 1 values do not parse as double"


def test_numbers_as_the_server_writes_them_parse(contract):
    rows = [
        dict(_ROWS[0], plots="-99", area="0.75"),
        dict(_ROWS[0], plots="0", area="-1.5"),
        dict(_ROWS[0], plots="12", area="1.2345678E7"),
        dict(_ROWS[0], plots="3", area="1.0E-4"),
    ]
    table = cast_wide(rows, contract)
    assert _col(table, "plots") == [-99, 0, 12, 3]
    assert _col(table, "area") == [0.75, -1.5, 12345678.0, 0.0001]


def test_fallback_reason_never_quotes_a_value(contract):
    table = cast_wide([dict(_ROWS[0], plots="two", area="about two")], contract)
    reasons = " ".join(_fallback(table, n) for n in table.schema.names)
    assert "two" not in reasons


def test_binary_value_other_than_one_keeps_text_and_still_counts_as_answered(contract):
    table = cast_wide([dict(_ROWS[0], tools_2="yes")], contract)
    assert table.schema.field("tools_2").type == pa.string()
    assert _fallback(table, "tools_2") == "1 of 1 values do not parse as int8"
    assert _col(table, "tools_1") == [0]


def test_choice_code_not_in_form_is_text_and_counts_as_answered(contract):
    table = cast_wide([dict(_ROWS[1], tools_9="1")], contract)
    assert _col(table, "tools_9") == ["1"]
    assert "not among the form's choices" in _fallback(table, "tools_9")
    assert _col(table, "tools_1") == [0]
    names = table.schema.names
    assert (
        names.index("tools_77") < names.index("tools_9") < names.index("plot_crop_1_2")
    )


def test_cast_fallback_never_quotes_a_code(contract):
    """A code can be a value from the data: a picked name no longer in the list."""
    table = cast_wide([dict(_ROWS[1], tools_Qzorvane="1")], contract)
    assert _fallback(table, "tools_Qzorvane") == (
        "a choice code not among the form's choices"
    )


def test_unmapped_column_is_text_at_the_end(contract):
    table = cast_wide([dict(_ROWS[0], mystery="x")], contract)
    assert _col(table, "mystery") == ["x"]
    assert _fallback(table, "mystery") == "maps to no form field"
    assert table.schema.names[-1] == "mystery"


_CODES_XML = """<?xml version="1.0"?>
<h:html xmlns="http://www.w3.org/2002/xforms" xmlns:h="http://www.w3.org/1999/xhtml">
  <h:head><model>
    <instance><f id="f" version="1"><level/><grade/><answer/></f></instance>
    <bind nodeset="/f/level" type="select1"/>
    <bind nodeset="/f/grade" type="select1"/>
    <bind nodeset="/f/answer" type="select1"/>
  </model></h:head>
  <h:body>
    <select1 ref="/f/level"><label>Level</label>
      <item><label>None</label><value>0</value></item><item><label>High</label><value>3</value></item>
      <item><label>Don't know</label><value>-99</value></item>
    </select1>
    <select1 ref="/f/grade"><label>Grade</label>
      <item><label>First</label><value>01</value></item><item><label>Second</label><value>02</value></item>
    </select1>
    <select1 ref="/f/answer"><label>Answer</label>
      <item><label>Yes</label><value>yes</value></item><item><label>No</label><value>no</value></item>
    </select1>
  </h:body>
</h:html>
"""


@pytest.fixture
def codes_contract(tmp_path):
    path = tmp_path / "f.xml"
    path.write_text(_CODES_XML, encoding="utf-8")
    return parse_contract(path)


def test_select_one_with_integer_codes_is_int64(codes_contract):
    table = cast_wide(
        [{"KEY": "k1", "level": "3"}, {"KEY": "k2", "level": "-99"}], codes_contract
    )
    assert table.schema.field("level").type == pa.int64()
    assert table.column("level").to_pylist() == [3, -99]


def test_select_one_with_leading_zero_or_text_codes_stays_string(codes_contract):
    table = cast_wide([{"KEY": "k1", "grade": "01", "answer": "yes"}], codes_contract)
    assert table.schema.field("grade").type == pa.string()
    assert table.schema.field("answer").type == pa.string()
    assert table.column("grade").to_pylist() == ["01"]


def test_select_one_code_outside_its_choices_falls_back_to_text(codes_contract):
    table = cast_wide([{"KEY": "k1", "level": "2.5"}], codes_contract)
    assert table.schema.field("level").type == pa.string()


_FILTERED_XML = """<?xml version="1.0"?>
<h:html xmlns="http://www.w3.org/2002/xforms" xmlns:h="http://www.w3.org/1999/xhtml">
  <h:head><model>
    <instance><shop id="shop" version="1"><n/><pick/></shop></instance>
    <instance id="towns"><root>
      <item><label>North</label><name>11</name><zone>1</zone></item>
      <item><label>South</label><name>21</name><zone>2</zone></item>
      <item><label>East</label><name>31</name><zone>3</zone></item>
    </root></instance>
    <bind nodeset="/shop/n" type="int"/>
    <bind nodeset="/shop/pick" type="select"/>
  </model></h:head>
  <h:body>
    <input ref="/shop/n"><label>N</label></input>
    <select ref="/shop/pick"><label>Towns</label>
      <itemset nodeset="instance('towns')/root/item[zone &lt;=  /shop/n ]">
        <value ref="name"/><label ref="label"/>
      </itemset>
    </select>
  </h:body>
</h:html>
"""


def test_list_filtered_per_submission_gets_only_picked_binaries(tmp_path):
    path = tmp_path / "shop.xml"
    path.write_text(_FILTERED_XML, encoding="utf-8")
    rows = [
        {"KEY": "uuid:a", "n": "1", "pick_11": "1"},
        {"KEY": "uuid:b", "n": "2", "pick_21": "1"},
    ]
    table = cast_wide(rows, parse_contract(path))
    assert [c for c in table.schema.names if c.startswith("pick_")] == [
        "pick_11",
        "pick_21",
    ]
    assert table.column("pick_11").to_pylist() == [1, 0]


def test_a_select_multiple_exported_raw_is_split_into_binaries(contract):
    row = {k: v for k, v in _ROWS[0].items() if k not in ("tools_2", "plot_crop_1_1")}
    table = cast_wide([{**row, "tools": "2", "plot_crop_1": "1 2"}], contract)
    assert "tools" not in table.schema.names
    assert "plot_crop_1" not in table.schema.names
    assert (_col(table, "tools_1"), _col(table, "tools_2")) == ([0], [1])
    assert (_col(table, "plot_crop_1_1"), _col(table, "plot_crop_2_1")) == ([1], [1])


_DIGITS_XML = """<?xml version="1.0"?>
<h:html xmlns="http://www.w3.org/2002/xforms" xmlns:h="http://www.w3.org/1999/xhtml"
        xmlns:jr="http://openrosa.org/javarosa">
  <h:head><model>
    <instance><f id="f" version="1"><s4_1/><r jr:template=""><s5_2/></r></f></instance>
    <bind nodeset="/f/s4_1" type="select"/>
    <bind nodeset="/f/r/s5_2" type="select"/>
  </model></h:head>
  <h:body>
    <select ref="/f/s4_1"><label>S4</label>
      <item><label>a</label><value>1</value></item><item><label>b</label><value>2</value></item>
    </select>
    <group ref="/f/r"><repeat nodeset="/f/r">
      <select ref="/f/r/s5_2"><label>S5</label>
        <item><label>a</label><value>1</value></item><item><label>b</label><value>2</value></item>
      </select>
    </repeat></group>
  </h:body>
</h:html>
"""


def test_raw_select_multiple_named_with_trailing_digits_is_split(tmp_path):
    path = tmp_path / "f.xml"
    path.write_text(_DIGITS_XML, encoding="utf-8")
    table = cast_wide(
        [{"KEY": "k1", "s4_1": "1 2", "s5_2_1": "2"}], parse_contract(path)
    )
    assert "s4_1" not in table.schema.names
    assert "s5_2_1" not in table.schema.names
    assert (_col(table, "s4_1_1"), _col(table, "s4_1_2")) == ([1], [1])
    assert (_col(table, "s5_2_1_1"), _col(table, "s5_2_2_1")) == ([0], [1])


_GEO_XML = """<?xml version="1.0"?>
<h:html xmlns="http://www.w3.org/2002/xforms" xmlns:h="http://www.w3.org/1999/xhtml">
  <h:head><model>
    <instance><f id="f" version="1"><gps/><path/><area/><at/></f></instance>
    <bind nodeset="/f/gps" type="geopoint"/>
    <bind nodeset="/f/path" type="geotrace"/>
    <bind nodeset="/f/area" type="geoshape"/>
    <bind nodeset="/f/at" type="time"/>
  </model></h:head>
  <h:body>
    <input ref="/f/gps"><label>GPS</label></input>
    <input ref="/f/path"><label>Path</label></input>
    <input ref="/f/area"><label>Area</label></input>
    <input ref="/f/at"><label>At</label></input>
  </h:body>
</h:html>
"""


def test_geo_and_time_columns_are_text_without_fallback(tmp_path):
    path = tmp_path / "f.xml"
    path.write_text(_GEO_XML, encoding="utf-8")
    row = {
        "KEY": "k1",
        "gps": "4.6 -74.1 2600 5",
        "path": "4.6 -74.1 0 0;4.7 -74.2 0 0",
        "area": "4.6 -74.1 0 0;4.7 -74.2 0 0;4.6 -74.1 0 0",
        "at": "09:30:00.000-05:00",
    }
    table = cast_wide([row], parse_contract(path))
    for name in ("gps", "path", "area", "at"):
        assert table.schema.field(name).type == pa.string()
        assert _fallback(table, name) == ""
        assert _col(table, name) == [row[name]]


def test_no_submissions_is_the_columns_every_submission_carries(contract):
    table = cast_wide([], contract)
    assert table.num_rows == 0
    assert [(f.name, f.type) for f in table.schema] == [
        ("KEY", pa.string()),
        ("SubmissionDate", pa.timestamp("ms", tz="UTC")),
        ("formdef_version", pa.string()),
    ]
