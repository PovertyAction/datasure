"""Each check saves its view state under its catalogue slug.

"Reset filters" on the check page clears the scope named after the selected
check's slug, so a check saving under any other name could not be reset.
"""

import json

import pytest

from datasure.checks import (
    catalogue,
    descriptive,
    id_duplicates_ui,
    missing,
    progress,
    summary,
)
from datasure.checks.backchecks import report_ui as backchecks
from datasure.checks.enumerator import report_ui as enumerator
from datasure.checks.gpschecks import report_ui as gps
from datasure.checks.outliers import report_ui as outliers

MODULES = [
    (summary, "summary"),
    (progress, "progress"),
    (missing, "missing"),
    (id_duplicates_ui, "duplicates"),
    (outliers, "outliers"),
    (gps, "gps"),
    (enumerator, "enumerator"),
    (backchecks, "backchecks"),
    (descriptive, "descriptive"),
]


@pytest.mark.parametrize(("module", "slug"), MODULES)
def test_view_scope_is_the_catalogue_slug(module, slug):
    assert slug == module.VIEW_SCOPE
    assert catalogue.get_check(module.VIEW_SCOPE).slug == slug


@pytest.mark.parametrize(("module", "slug"), MODULES)
def test_check_view_opens_the_slug_scope(module, slug, tmp_path):
    view = module.check_view(tmp_path / "page_settings.json")

    assert view.scope == slug
    assert view.settings_file == tmp_path / "page_settings.json"


LEGACY = [
    (descriptive, "descriptive_stats", "col_to_plot", "desc_hist_col"),
    (enumerator, "enumerators", "stat", "enumerator_statistics_overtime_stat"),
    (backchecks, "backchecks", "enum_bcer_stats_view", "enum_bcer_stats_view_key"),
    (outliers, "outliers", "selected_col", "outlier_inspect_col"),
]


@pytest.mark.parametrize(("module", "section", "legacy_key", "widget_key"), LEGACY)
def test_view_values_saved_with_check_settings_move_to_view_state(
    module, section, legacy_key, widget_key, tmp_path
):
    """Older versions saved these in the exported check settings."""
    settings_file = tmp_path / "page_settings.json"
    settings_file.write_text(json.dumps({section: {legacy_key: "x", "kept": 1}}))

    view = module.check_view(settings_file)

    assert view.values() == {widget_key: "x"}
    assert json.loads(settings_file.read_text())[section] == {"kept": 1}
