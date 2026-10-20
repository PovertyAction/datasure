"""Each check saves its view state under its catalogue slug.

"Reset filters" on the check page clears the scope named after the selected
check's slug, so a check saving under any other name could not be reset.
"""

import pytest

from datasure.checks import catalogue
from datasure.checks.backchecks import report_ui as backchecks
from datasure.checks.enumerator import report_ui as enumerator
from datasure.checks.gpschecks import report_ui as gps
from datasure.checks.id_duplicates_ui import VIEW_SCOPE as DUPLICATES_SCOPE
from datasure.checks.outliers import report_ui as outliers


@pytest.mark.parametrize(
    ("scope", "slug"),
    [
        (DUPLICATES_SCOPE, "duplicates"),
        (outliers.VIEW_SCOPE, "outliers"),
        (gps.VIEW_SCOPE, "gps"),
        (enumerator.VIEW_SCOPE, "enumerator"),
        (backchecks.VIEW_SCOPE, "backchecks"),
    ],
)
def test_view_scope_is_the_catalogue_slug(scope, slug):
    assert scope == slug
    assert catalogue.get_check(scope).slug == slug
