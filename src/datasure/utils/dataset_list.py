"""The import page's dataset list, worked out from the import log (no Streamlit).

The page renders what :func:`build_dataset_list` returns: one row per dataset
with its source, last load and switch states, the "Load data" summary, and
whether the list is long enough to need a source filter.
"""

from dataclasses import dataclass
from datetime import datetime

import polars as pl

SURVEYCTO_SOURCE = "SurveyCTO"
LOCAL_SOURCE = "local storage"
DEMO_SOURCE = "Demo Data"

# Source filter choices. "Local" covers local files and the demo datasets.
FILTER_ALL = "All"
FILTER_SURVEYCTO = "SurveyCTO"
FILTER_LOCAL = "Local"
SOURCE_FILTERS = (FILTER_ALL, FILTER_SURVEYCTO, FILTER_LOCAL)

# Show the source filter once a project has more datasets than this.
SOURCE_FILTER_THRESHOLD = 8

LOCAL_MEDIA_REASON = "Local files have no media attachments to download."
DEMO_MEDIA_REASON = "The demo datasets have no media attachments to download."

_SOURCE_LABELS = {
    SURVEYCTO_SOURCE: "SurveyCTO",
    LOCAL_SOURCE: "Local file",
    DEMO_SOURCE: "Demo data",
}


@dataclass(frozen=True)
class LoadInfo:
    """What is known about a dataset's last load.

    ``loaded_at`` is ``None`` for a dataset imported before load times were
    recorded; ``rows`` is ``None`` when the dataset has no imported table.
    """

    loaded_at: datetime | None
    rows: int | None


@dataclass(frozen=True)
class DatasetRow:
    """One dataset on the import page."""

    alias: str
    source: str
    source_label: str
    source_detail: str
    row_count: int | None
    last_loaded_label: str
    refresh: bool
    load: bool
    media: bool
    media_disabled_reason: str | None

    @property
    def is_surveycto(self) -> bool:
        """Whether the dataset is downloaded from SurveyCTO."""
        return self.source == SURVEYCTO_SOURCE


@dataclass(frozen=True)
class DatasetList:
    """Everything the import page shows about a project's datasets."""

    rows: list[DatasetRow]
    load_summary: str
    show_source_filter: bool
    is_empty: bool


def _text(value) -> str:
    """Return a stored import-log value as text; nulls become empty."""
    return "" if value is None else str(value)


def _source_detail(entry: dict) -> str:
    """Describe where a dataset comes from: form and server, or path and sheet."""
    if entry["source"] == SURVEYCTO_SOURCE:
        parts = [f"Form {_text(entry.get('form_id'))}", _text(entry.get("server"))]
        return " · ".join(part for part in parts if part)
    detail = _text(entry.get("filename"))
    sheet = _text(entry.get("sheet_name"))
    if sheet:
        detail += f' · sheet "{sheet}"'
    return detail


def _last_loaded_label(info: LoadInfo | None) -> str:
    """Say when a dataset was last loaded."""
    if info is None or (info.loaded_at is None and info.rows is None):
        return "Not loaded yet"
    if info.loaded_at is None:
        return "Last load time not recorded"
    return f"Last loaded {info.loaded_at:%d %b %Y %H:%M}"


def _media_disabled_reason(source: str) -> str | None:
    """Say why Media can't be switched on, or ``None`` when it can."""
    if source == SURVEYCTO_SOURCE:
        return None
    return DEMO_MEDIA_REASON if source == DEMO_SOURCE else LOCAL_MEDIA_REASON


def _row(entry: dict, info: LoadInfo | None) -> DatasetRow:
    source = _text(entry.get("source"))
    reason = _media_disabled_reason(source)
    return DatasetRow(
        alias=entry["alias"],
        source=source,
        source_label=_SOURCE_LABELS.get(source, source),
        source_detail=_source_detail({**entry, "source": source}),
        row_count=info.rows if info else None,
        last_loaded_label=_last_loaded_label(info),
        refresh=bool(entry.get("refresh")),
        load=bool(entry.get("load")),
        media=bool(entry.get("attachments")) and reason is None,
        media_disabled_reason=reason,
    )


def _plural(count: int, word: str) -> str:
    return f"{count} {word}" if count == 1 else f"{count} {word}s"


def _load_summary(rows: list[DatasetRow]) -> str:
    """Say what "Load data" will do: rows marked Load, and which of them refresh.

    Load data skips rows not marked Load, so Refresh only counts on those.
    """
    loads = [row for row in rows if row.load]
    if not loads:
        return "No datasets are marked Load"
    refreshes = sum(row.refresh for row in loads)
    refresh_text = (
        f"refreshes {refreshes} from source" if refreshes else ("refreshes none")
    )
    return f"Loads {_plural(len(loads), 'dataset')} · {refresh_text}"


def build_dataset_list(
    import_log: pl.DataFrame, load_info: dict[str, LoadInfo]
) -> DatasetList:
    """Turn the import log and load information into the import page's list.

    Parameters
    ----------
    import_log : pl.DataFrame
        The project's import log, one row per dataset. Empty for a project
        with no datasets.
    load_info : dict[str, LoadInfo]
        Last load time and row count by alias; aliases never loaded may be
        left out.
    """
    if import_log.is_empty():
        return DatasetList(
            rows=[],
            load_summary=_load_summary([]),
            show_source_filter=False,
            is_empty=True,
        )
    rows = [
        _row(entry, load_info.get(entry["alias"]))
        for entry in import_log.iter_rows(named=True)
    ]
    return DatasetList(
        rows=rows,
        load_summary=_load_summary(rows),
        show_source_filter=len(rows) > SOURCE_FILTER_THRESHOLD,
        is_empty=False,
    )


def filter_rows(rows: list[DatasetRow], source_filter: str | None) -> list[DatasetRow]:
    """Keep the rows matching a source filter; ``None`` or All keeps every row."""
    if source_filter == FILTER_SURVEYCTO:
        return [row for row in rows if row.is_surveycto]
    if source_filter == FILTER_LOCAL:
        return [row for row in rows if not row.is_surveycto]
    return list(rows)
