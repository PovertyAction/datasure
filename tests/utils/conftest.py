"""Local conftest for utils tests to override global fixtures."""

import pytest


@pytest.fixture(autouse=True)
def mock_database_functions():
    """Override the global mock_database_functions fixture.

    Chart utils tests don't need database mocking, so we provide
    a no-op fixture here to prevent the global autouse fixture
    from interfering with these tests.
    """
    # No-op: chart utilities don't need database mocking
    yield
