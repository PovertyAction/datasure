"""Each check saves its view state under its catalogue slug.

"Reset filters" on the check page clears the scope named after the selected
check's slug, so a check saving under any other name could not be reset.
"""

import pytest

from datasure.checks import catalogue, id_duplicates_ui
from datasure.checks.backchecks import report_ui as backchecks
from datasure.checks.enumerator import report_ui as enumerator
from datasure.checks.gpschecks import report_ui as gps
from datasure.checks.outliers import report_ui as outliers

MODULES = [
    (id_duplicates_ui, "duplicates"),
    (outliers, "outliers"),
    (gps, "gps"),
    (enumerator, "enumerator"),
    (backchecks, "backchecks"),
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
