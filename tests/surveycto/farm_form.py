"""Synthetic farm form in SurveyCTO's compiled shape, with API-shaped fictional rows."""

import json

XML = """<?xml version="1.0"?>
<h:html xmlns="http://www.w3.org/2002/xforms" xmlns:h="http://www.w3.org/1999/xhtml"
        xmlns:jr="http://openrosa.org/javarosa">
  <h:head><model>
    <instance><farm id="farm" version="3">
      <starttime/><endtime/><deviceid/><duration/>
      <intro/><owner/><phone/><plot_code/><village/><tag/><prev/><plots/><area/><per_plot/><visit/><crop/><tools/><photo/>
      <plot jr:template=""><plot_crop/><plot_size/></plot>
      <meta><instanceID/></meta>
    </farm></instance>
    <bind nodeset="/farm/starttime" type="dateTime" jr:preload="timestamp" jr:preloadParams="start"/>
    <bind nodeset="/farm/endtime" type="dateTime" jr:preload="timestamp" jr:preloadParams="end"/>
    <bind nodeset="/farm/deviceid" type="string" jr:preload="property" jr:preloadParams="deviceid"/>
    <bind nodeset="/farm/duration" type="string" calculate="duration()"/>
    <bind nodeset="/farm/intro" type="string" readonly="true()" original="note"/>
    <bind nodeset="/farm/owner" type="string"/>
    <bind nodeset="/farm/phone" type="string"/>
    <bind nodeset="/farm/plot_code" type="string"/>
    <bind nodeset="/farm/village" type="string" publishable="true()"/>
    <bind nodeset="/farm/tag" type="string" calculate="concat( /farm/owner , ' ',  /farm/phone )"/>
    <bind nodeset="/farm/prev" type="string" calculate="pulldata('prev_round', 'owner', 'phone',  /farm/phone )"/>
    <bind nodeset="/farm/plots" type="int" publishable="true()"/>
    <bind nodeset="/farm/area" type="decimal" constraint=". &gt;= 0" relevant=" /farm/plots  &gt; 0"/>
    <bind nodeset="/farm/per_plot" type="decimal" calculate=" /farm/area  div  /farm/plots "/>
    <bind nodeset="/farm/visit" type="date"/>
    <bind nodeset="/farm/crop" type="select1"/>
    <bind nodeset="/farm/tools" type="select"/>
    <bind nodeset="/farm/photo" type="binary"/>
    <bind nodeset="/farm/plot" relevant=" /farm/plots  &gt; 0"/>
    <bind nodeset="/farm/plot/plot_crop" type="select"/>
    <bind nodeset="/farm/plot/plot_size" type="decimal"/>
    <bind nodeset="/farm/meta/instanceID" type="string" calculate="concat('uuid:', uuid())"/>
  </model></h:head>
  <h:body>
    <input ref="/farm/intro"><label>Welcome</label></input>
    <input ref="/farm/owner"><label>Owner</label></input>
    <input ref="/farm/phone"><label>Phone</label></input>
    <input ref="/farm/plot_code"><label>Plot code</label></input>
    <input ref="/farm/village"><label>Village</label></input>
    <input ref="/farm/plots"><label>Plots</label></input>
    <input ref="/farm/area"><label>Area</label></input>
    <input ref="/farm/visit"><label>Visit</label></input>
    <select1 ref="/farm/crop"><label>Crop</label>
      <item><label>Maize</label><value>01</value></item><item><label>Rice</label><value>02</value></item>
    </select1>
    <select ref="/farm/tools"><label>Tools</label>
      <item><label>Hoe</label><value>1</value></item><item><label>Plough</label><value>2</value></item>
      <item><label>Other</label><value>77</value></item>
    </select>
    <upload ref="/farm/photo" mediatype="image/*"><label>Photo</label></upload>
    <group ref="/farm/plot"><label>Plot</label><repeat nodeset="/farm/plot" jr:count=" /farm/plots ">
      <select ref="/farm/plot/plot_crop"><label>Plot crop</label>
        <item><label>Maize</label><value>1</value></item><item><label>Rice</label><value>2</value></item>
      </select>
      <input ref="/farm/plot/plot_size"><label>Plot size</label></input>
    </repeat></group>
  </h:body>
</h:html>
"""

# Shapes as the API returns them: all strings, keys sparse per row, select_multiple
# only as per-choice binaries present when chosen, timestamps in UTC.
ROWS = [
    {
        "SubmissionDate": "Mar 7, 2025 4:06:12 PM",
        "starttime": "Mar 7, 2025 3:58:01 PM",
        "endtime": "Mar 7, 2025 4:05:59 PM",
        "deviceid": "(web)",
        "duration": "478",
        "intro": "",
        "owner": "Ana Maria Gomez Restrepo",
        "phone": "3104567890",
        "plot_code": "LT-0042",
        "village": "Villa Ficticia Uno",
        "tag": "Ana Maria Gomez Restrepo 3104567890",
        "prev": "Jorge Perez",
        "per_plot": "0.75",
        "plots": "2",
        "area": "1.5",
        "visit": "Mar 6, 2025",
        "crop": "01",
        "tools_2": "1",
        "photo": "https://example.surveycto.com/view/submission-attachment/x.jpg",
        "plot_crop_1_1": "1",
        "plot_size_1": "0.75",
        "plot_size_2": "",
        "formdef_version": "2503071606",
        "KEY": "uuid:aaa",
    },
    {
        "SubmissionDate": "Mar 12, 2025 11:00:00 AM",
        "starttime": "Mar 12, 2025 10:50:00 AM",
        "endtime": "Mar 12, 2025 10:59:00 AM",
        "deviceid": "(web)",
        "duration": "540",
        "intro": "",
        "owner": "",
        "phone": "3204561122",
        "plot_code": "0042",
        "plots": "-99",
        "area": "",
        "crop": "02",
        "plot_crop_2_2": "1",
        "formdef_version": "2503071606",
        "KEY": "uuid:bbb",
    },
]


# The study's non-response codes, as SCTO_SENTINELS would give them.
SENTINELS = {
    -99: "Don't know",
    -88: "Refused to answer",
    -77: "Not applicable",
    -66: "Other (specify)",
    -55: "Not in list",
}


# The form list a pull saves: farm attaches prev_round.csv, which its pulldata() reads.
FORM_LIST = b"""<?xml version="1.0"?>
<xforms xmlns="http://openrosa.org/xforms/xformsList">
  <xform><formID>farm</formID><version>3</version><datasets></datasets>
    <files>{"files":[{"filename":"prev_round.csv","timestamp":1}]}</files></xform>
</xforms>"""


def write_pull(cfg, prev_round="phone,owner\n", xml=XML, rows=ROWS):
    """Write what ``pull`` leaves for a config whose only form is farm."""
    cfg.raw_dir.mkdir(parents=True)
    (cfg.raw_dir / "formList.xml").write_bytes(FORM_LIST)
    (cfg.raw_dir / "datasets.json").write_text("[]", encoding="utf-8")
    raw = cfg.form_raw("farm")
    (raw / "files").mkdir(parents=True)
    (raw / "form.xml").write_text(xml, encoding="utf-8")
    (raw / "wide.json").write_text(json.dumps(rows), encoding="utf-8")
    (raw / "files" / "prev_round.csv").write_text(prev_round, encoding="utf-8")
