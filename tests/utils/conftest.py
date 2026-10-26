"""Local conftest for utils tests to override global fixtures."""

import re
from pathlib import Path

import pytest

import datasure

# Check pages generated at runtime from views/output_view_template.py
# (gitignored, so present only in a checkout where the app has run).
_GENERATED_VIEW = re.compile(r"output_view_[0-9a-z]\.py$")


@pytest.fixture(autouse=True)
def mock_database_functions():
    """Override the global mock_database_functions fixture.

    Chart utils tests don't need database mocking, so we provide
    a no-op fixture here to prevent the global autouse fixture
    from interfering with these tests.
    """
    # No-op: chart utilities don't need database mocking
    yield


@pytest.fixture(scope="session")
def datasure_sources() -> list[tuple[Path, str]]:
    """Return (path relative to the package, text) for each datasure source file.

    Generated ``views/output_view_?.py`` pages are skipped: they copy the
    template, so scanning them would count its text twice.
    """
    src = Path(datasure.__file__).parent
    return [
        (path.relative_to(src), path.read_text(encoding="utf-8"))
        for path in sorted(src.rglob("*.py"))
        if not _GENERATED_VIEW.search(path.name)
    ]
