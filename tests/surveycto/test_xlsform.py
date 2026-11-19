"""Tests for rebuilding a design-shaped form definition from the compiled XML."""

from datasure.surveycto.xlsform import design_from_xml
from tests.surveycto.farm_form import XML as FARM_XML

MEDIA_XML = """<?xml version="1.0"?>
<h:html xmlns="http://www.w3.org/2002/xforms" xmlns:h="http://www.w3.org/1999/xhtml">
  <h:head><h:title>Media form</h:title><model>
    <instance><media id="media" version="1">
      <photo/><voice/><clip/><doc/><all_comments/><text_audit/><audio_audit/>
      <meta><instanceID/></meta>
    </media></instance>
    <bind nodeset="/media/photo" type="binary"/>
    <bind nodeset="/media/voice" type="binary"/>
    <bind nodeset="/media/clip" type="binary"/>
    <bind nodeset="/media/doc" type="binary"/>
    <bind nodeset="/media/all_comments" type="binary" appearance="class=comments"/>
    <bind nodeset="/media/text_audit" type="binary" appearance="class=textAudit;p=100"/>
    <bind nodeset="/media/audio_audit" type="binary" appearance="class=audioAudit;s=10"/>
  </model></h:head>
  <h:body>
    <upload ref="/media/photo" mediatype="image/*"><label>Photo</label></upload>
    <upload ref="/media/voice" mediatype="audio/*"><label>Voice</label></upload>
    <upload ref="/media/clip" mediatype="video/*"><label>Clip</label></upload>
    <upload ref="/media/doc" mediatype="application/*"><label>Doc</label></upload>
  </h:body>
</h:html>
"""


def _rows(design: dict, sheet: str) -> list[dict]:
    header, *rows = design[sheet]
    return [dict(zip(header, row, strict=True)) for row in rows]


def _types(design: dict) -> list[tuple[str, str]]:
    return [(r["type"], r["name"]) for r in _rows(design, "fieldsRowsAndColumns")]


class TestDesignFromXml:
    def test_survey_rows_follow_form_order_with_xlsform_types(self):
        """Fields get XLSForm types, repeats get begin/end rows, meta is left out."""
        assert _types(design_from_xml(FARM_XML.encode())) == [
            ("start", "starttime"),
            ("end", "endtime"),
            ("deviceid", "deviceid"),
            ("calculate", "duration"),
            ("note", "intro"),
            ("text", "owner"),
            ("text", "phone"),
            ("text", "plot_code"),
            ("text", "village"),
            ("calculate", "tag"),
            ("calculate", "prev"),
            ("integer", "plots"),
            ("decimal", "area"),
            ("calculate", "per_plot"),
            ("date", "visit"),
            ("select_one crop", "crop"),
            ("select_multiple tools", "tools"),
            ("image", "photo"),
            ("begin repeat", "plot"),
            ("select_multiple plot_crop", "plot_crop"),
            ("decimal", "plot_size"),
            ("end repeat", "plot"),
        ]

    def test_expressions_use_field_references(self):
        """Absolute XPath paths read as ${field}, as in the XLSForm."""
        rows = {
            r["name"]: r
            for r in _rows(design_from_xml(FARM_XML.encode()), "fieldsRowsAndColumns")
        }

        assert rows["area"]["relevance"] == "${plots} > 0"
        assert rows["area"]["constraint"] == ". >= 0"
        assert rows["per_plot"]["calculation"] == "${area} div ${plots}"
        assert rows["owner"]["label"] == "Owner"

    def test_choices_per_select(self):
        """Each select gets its own list, named after the field."""
        choices = _rows(design_from_xml(FARM_XML.encode()), "choicesRowsAndColumns")

        assert [(c["list_name"], c["name"], c["label"]) for c in choices] == [
            ("crop", "01", "Maize"),
            ("crop", "02", "Rice"),
            ("tools", "1", "Hoe"),
            ("tools", "2", "Plough"),
            ("tools", "77", "Other"),
            ("plot_crop", "1", "Maize"),
            ("plot_crop", "2", "Rice"),
        ]

    def test_media_types(self):
        """Uploads by mediatype; comments and audits by their bind class."""
        design = design_from_xml(MEDIA_XML.encode())

        assert _types(design) == [
            ("image", "photo"),
            ("audio", "voice"),
            ("video", "clip"),
            ("file", "doc"),
            ("comments", "all_comments"),
            ("text audit", "text_audit"),
            ("audio audit", "audio_audit"),
        ]

    def test_title_and_marker(self):
        """The title comes from the XML; the definition says it was rebuilt."""
        design = design_from_xml(MEDIA_XML.encode())

        assert design["title"] == "Media form"
        assert design["rebuilt_from_xml"] is True

    def test_title_falls_back_to_form_id(self):
        """A form without a title uses its form ID."""
        assert design_from_xml(FARM_XML.encode())["title"] == "farm"
