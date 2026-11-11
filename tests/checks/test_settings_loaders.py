"""Check settings loaders read the latest saved settings.

The check page renders only the selected check, so a check's widgets are
rebuilt from these loaders each time the user comes back to it. A loader that
returned an older value would undo the user's last change.
"""

import json

import pytest

from datasure.checks.duplicates import (
    DuplicatesSettings,
    load_default_duplicates_settings,
)
from datasure.checks.enumerator.models import EnumeratorSettings
from datasure.checks.enumerator.settings_ui import load_default_enumerator_settings
from datasure.checks.gpschecks.compute import load_default_gpschecks_settings
from datasure.checks.progress import ProgressSettings, load_default_settings
from datasure.models.schemas import GPSSettings

LOADERS = [
    pytest.param(
        load_default_settings,
        "progress",
        ProgressSettings(survey_key="key", survey_id="id"),
        "survey_date",
        id="progress",
    ),
    pytest.param(
        load_default_duplicates_settings,
        "duplicates",
        DuplicatesSettings(survey_key="key", survey_id="id"),
        "enumerator",
        id="duplicates",
    ),
    pytest.param(
        load_default_gpschecks_settings,
        "gpschecks",
        GPSSettings(survey_key="key", survey_id="id"),
        "enumerator",
        id="gps",
    ),
    pytest.param(
        load_default_enumerator_settings,
        "enumerators",
        EnumeratorSettings(survey_key="key", survey_id="id"),
        "enumerator",
        id="enumerator",
    ),
]


@pytest.mark.parametrize(("loader", "section", "defaults", "field"), LOADERS)
def test_loader_returns_the_latest_saved_value(
    tmp_path, loader, section, defaults, field
):
    settings_file = tmp_path / "page_settings.json"
    settings_file.write_text(json.dumps({section: {field: "col_a"}}))
    assert getattr(loader(str(settings_file), defaults), field) == "col_a"

    settings_file.write_text(json.dumps({section: {field: "col_b"}}))

    assert getattr(loader(str(settings_file), defaults), field) == "col_b"
