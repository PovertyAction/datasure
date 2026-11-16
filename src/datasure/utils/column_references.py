"""Find where check configs and corrections use a dataset's columns.

Before a Prep rename saves, the rename form asks this module which check
settings and correction-log entries name the columns being renamed, so it
can warn that they will stop matching. Nothing here writes: references are
reported, never rewritten.

Streamlit-free: it reads DuckDB tables and settings files directly.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from collections.abc import Iterable, Iterator
from dataclasses import dataclass

import polars as pl

from datasure.processing.correction_log import ensure_log_columns
from datasure.utils.cache_utils import get_cache_path
from datasure.utils.duckdb_utils import (
    BACKCHECKS_TABLE,
    DESCRIPTIVE_COLUMNS_TABLE,
    DUPLICATES_TABLE,
    GPS_COLUMNS_TABLE,
    OUTLIERS_TABLE,
    check_table_name,
    duckdb_get_table,
    name_id,
)
from datasure.utils.view_state import read_settings, without_view_state

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ColumnReference:
    """One place that uses ``column``: ``source`` says where, ``detail`` how."""

    column: str
    source: str
    detail: str


# Page config fields naming a column of the page's survey dataset.
_SURVEY_CONFIG_FIELDS = {
    "survey_key": "survey KEY",
    "survey_id": "survey ID",
    "survey_date": "survey date",
    "enumerator": "enumerator",
    "team": "team",
    "formversion": "form version",
    "duration": "duration",
}

# Fields naming a column of the page's backcheck dataset. The survey KEY and
# ID columns are also looked up in the backcheck data.
_BACKCHECK_CONFIG_FIELDS = {
    "backcheck_date": "backcheck date",
    "backchecker": "backchecker",
    "backchecker_team": "backchecker team",
    "survey_key": "survey KEY",
    "survey_id": "survey ID",
}

# Check tables whose ``column_name`` lists hold survey columns.
_LIST_TABLES = {
    DUPLICATES_TABLE: "Duplicates check",
    OUTLIERS_TABLE: "Outliers check",
    BACKCHECKS_TABLE: "Backchecks",
}

_GPS_FIELDS = {
    "gps_column": "GPS column",
    "latitude_column": "latitude column",
    "longitude_column": "longitude column",
    "altitude_column": "altitude column",
    "accuracy_column": "accuracy column",
}

_SETTINGS_SECTIONS = {
    "duplicates": "Duplicates",
    "progress": "Progress",
    "summary": "Summary",
    "enumerators": "Enumerator stats",
    "outliers": "Outliers",
    "gpschecks": "GPS checks",
    "backchecks": "Backchecks",
}

# Settings keys naming a survey column, in any section.
_SURVEY_SETTING_KEYS = (
    "survey_key",
    "survey_id",
    "survey_date",
    "enumerator",
    "team",
    "formversion",
    "duration",
    "consent",
    "outcome",
    "condition_col",
    "date",
    "eligibility_column",
)

# Settings keys naming a backcheck column, by section.
_BACKCHECK_SETTING_KEYS = {
    "backchecks": ("backcheck_date", "backchecker", "survey_key", "survey_id"),
    "duplicates": ("backcheck_condition_col",),
}

_KEY_LABELS = {"survey_key": "survey KEY", "survey_id": "survey ID"}


def find_column_references(
    project_id: str, alias: str, columns: Iterable[str]
) -> list[ColumnReference]:
    """Return where the check pages and correction log of ``alias`` use ``columns``.

    Covers each check page's configuration, check tables and settings for
    pages on the dataset (as survey or backcheck data), then the dataset's
    correction log, with entries counted per column.
    """
    wanted = set(columns)
    if not wanted:
        return []
    references = [
        ref
        for page in _pages(project_id)
        for ref in _page_references(project_id, alias, page)
        if ref.column in wanted
    ]
    references.extend(_correction_references(project_id, alias, wanted))
    return references


def format_references(references: Iterable[ColumnReference]) -> str:
    """Return a Markdown list with one line per column and where it's used."""
    by_column: dict[str, list[str]] = {}
    for ref in references:
        by_column.setdefault(ref.column, []).append(f"{ref.source} ({ref.detail})")
    return "\n".join(
        f"- **{column}**: {'; '.join(places)}" for column, places in by_column.items()
    )


def _pages(project_id: str) -> list[dict]:
    config = duckdb_get_table(project_id, "check_config", "logs")
    return [] if config.is_empty() else config.to_dicts()


def _page_references(
    project_id: str, alias: str, page: dict
) -> Iterator[ColumnReference]:
    """Yield every column reference a check page makes to ``alias``."""
    page_name = str(page.get("page_name") or "")
    source = f"Check page '{page_name}'"
    is_survey = page.get("survey_data_name") == alias
    is_backcheck = page.get("backcheck_data_name") == alias
    if not (is_survey or is_backcheck):
        return

    fields = _SURVEY_CONFIG_FIELDS if is_survey else _BACKCHECK_CONFIG_FIELDS
    for field, label in fields.items():
        if page.get(field):
            yield ColumnReference(str(page[field]), source, label)

    for prefix, label in _LIST_TABLES.items():
        if is_survey or prefix == BACKCHECKS_TABLE:
            for column in _table_lists(project_id, prefix, page_name, "column_name"):
                yield ColumnReference(column, source, label)

    if is_survey:
        yield from _gps_references(project_id, page_name, source)
        yield from _descriptive_references(project_id, page_name, source)
    yield from _settings_references(project_id, page_name, source, is_survey)


def _check_table(project_id: str, prefix: str, page_name: str) -> pl.DataFrame:
    return duckdb_get_table(project_id, check_table_name(prefix, page_name), "logs")


def _table_lists(
    project_id: str, prefix: str, page_name: str, field: str
) -> Iterator[str]:
    """Yield each column named in a check table's list column."""
    table = _check_table(project_id, prefix, page_name)
    if field not in table.columns:
        return
    for value in table[field].to_list():
        yield from _names(value)


def _gps_references(
    project_id: str, page_name: str, source: str
) -> Iterator[ColumnReference]:
    table = _check_table(project_id, GPS_COLUMNS_TABLE, page_name)
    for row in table.to_dicts():
        for field, label in _GPS_FIELDS.items():
            if row.get(field):
                yield ColumnReference(str(row[field]), source, f"GPS check ({label})")


def _descriptive_references(
    project_id: str, page_name: str, source: str
) -> Iterator[ColumnReference]:
    table = _check_table(project_id, DESCRIPTIVE_COLUMNS_TABLE, page_name)
    if "column" not in table.columns:
        return
    if "Selected" in table.columns:
        table = table.filter(pl.col("Selected").fill_null(False))
    for column in table["column"].drop_nulls().to_list():
        yield ColumnReference(str(column), source, "Descriptive stats")


def _settings_references(
    project_id: str, page_name: str, source: str, is_survey: bool
) -> Iterator[ColumnReference]:
    """Yield columns a page's check settings name, leaving out view state."""
    path = get_cache_path(
        project_id, "settings", f"page_{name_id(page_name)}_settings.json"
    )
    try:
        settings = without_view_state(read_settings(path))
    except (OSError, ValueError):
        # The warning then leaves this page's settings out, so log it.
        logger.warning("Could not read check settings %s", path, exc_info=True)
        return
    for section, section_label in _SETTINGS_SECTIONS.items():
        values = settings.get(section)
        if not isinstance(values, dict):
            continue
        keys = (
            _SURVEY_SETTING_KEYS
            if is_survey
            else _BACKCHECK_SETTING_KEYS.get(section, ())
        )
        for key in keys:
            label = _KEY_LABELS.get(key, key.replace("_", " "))
            for column in _names(values.get(key)):
                yield ColumnReference(
                    column, source, f"{section_label} settings: {label}"
                )


def _correction_references(
    project_id: str, alias: str, wanted: set[str]
) -> list[ColumnReference]:
    """Count the correction-log entries naming each wanted column."""
    log = ensure_log_columns(duckdb_get_table(project_id, f"corr_log_{alias}", "logs"))
    if log.is_empty():
        return []
    counts: Counter[str] = Counter()
    for entry in log.to_dicts():
        for column in _entry_columns(entry):
            if column in wanted:
                counts[column] += 1
    return [
        ColumnReference(
            column, "Correction log", f"{n} {'entry' if n == 1 else 'entries'}"
        )
        for column, n in counts.items()
    ]


def _entry_columns(entry: dict) -> list[str]:
    """Return the columns a correction-log entry names.

    A GPS acceptance has no ``column``; its accepted coordinates are stored
    as a JSON object keyed by column in ``current_value``.
    """
    if entry.get("column"):
        return [str(entry["column"])]
    if entry.get("check_type") == "gps" and entry.get("current_value"):
        try:
            values = json.loads(str(entry["current_value"]))
        except ValueError:
            logger.debug("GPS acceptance value is not JSON: %r", entry["current_value"])
            return []
        if isinstance(values, dict):
            return [str(key) for key in values]
    return []


def _names(value: object) -> list[str]:
    """Return a stored column name or list of names as a list."""
    if isinstance(value, str):
        return [value] if value else []
    if isinstance(value, list | tuple):
        return [str(v) for v in value if v]
    return []
