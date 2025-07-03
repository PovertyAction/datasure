"""
Compatibility layer for pyDMS imports.

This module provides backward compatibility for the existing import structure
while the code is being transitioned to a proper package structure.
"""

import contextlib

# Re-export all modules from the pydms package for backward compatibility
with contextlib.suppress(ImportError):
    from .pydms import *  # noqa: F403
