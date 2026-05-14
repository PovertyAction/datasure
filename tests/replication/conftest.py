"""Replication test configuration.

Mock native-binary packages at import time so the replication package can be
imported in environments where compiled extensions are unavailable (e.g.
Windows-built .pyd files under WSL, or no duckdb binary present).

These mocks are placed in sys.modules before pytest's root autouse fixture
runs so that monkeypatch.setattr calls on these modules find the stubs rather
than triggering fresh imports.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

try:
    import duckdb  # noqa: F401
except Exception:
    sys.modules["duckdb"] = MagicMock()

try:
    from scipy import stats  # noqa: F401
except Exception:
    sys.modules["scipy"] = MagicMock()
    sys.modules["scipy.stats"] = MagicMock()
    _backchecks_stub = MagicMock()
    sys.modules.setdefault("datasure.checks.backchecks", _backchecks_stub)
