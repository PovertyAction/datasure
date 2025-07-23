"""
Compatibility layer for DataSure imports.

This module provides backward compatibility for the existing import structure
while the code is being transitioned to a proper package structure.
"""

import contextlib

# Re-export all modules from the datasure package for backward compatibility
with contextlib.suppress(ImportError):
    from .datasure import *  # noqa: F403
