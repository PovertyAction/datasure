"""Enumerator performance analysis module for survey data quality checks.

This module provides comprehensive enumerator performance tracking with:
- Enumerator overview metrics and statistics
- Productivity tracking over time (daily, weekly, monthly)
- Summary tables with missing data, duration, consent, and outcome analysis
- Statistical analysis across enumerators
- Time-series analysis of enumerator performance
- Configurable settings with Pydantic validation
- Modular, testable architecture
- Polars-based data processing for performance
"""

from datasure.checks.enumerator.report_ui import enumerator_report
from datasure.checks.enumerator.settings_ui import enumerator_report_settings

__all__ = ["enumerator_report", "enumerator_report_settings"]
