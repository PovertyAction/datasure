"""Read and write a project's import log and load records (no Streamlit).

The import log (``import_log`` in the ``logs`` database) holds one row per
dataset: where it comes from and its Refresh, Load and Media switches.
Adding or editing a dataset only changes its row; "Load data" does the
import. ``dataset_loads`` records when each dataset was last loaded.
"""

from datetime import datetime

import polars as pl

from datasure.connectors.local import FileConfig, ImportLogEntry
from datasure.connectors.scto import FormConfig
from datasure.utils.dataset_list import SURVEYCTO_SOURCE, LoadInfo
from datasure.utils.duckdb_utils import (
    alias_clash,
    delete_dataset_load,
    delete_form_definitions,
    duckdb_delete_rows,
    duckdb_get_table,
    duckdb_remove_table,
    duckdb_row_counts,
    duckdb_save_table,
    duckdb_table_exists,
    load_dataset_load_times,
    save_dataset_load,
)

IMPORT_LOG = "import_log"

# The switches shown on each dataset's row, by import-log column.
FLAG_COLUMNS = ("refresh", "load", "attachments")


class DatasetExistsError(ValueError):
    """A new dataset's alias would share a table with an existing dataset."""


def _get_log(project_id: str) -> pl.DataFrame:
    return duckdb_get_table(project_id, IMPORT_LOG, "logs")


def _save_log(project_id: str, import_log: pl.DataFrame) -> None:
    duckdb_save_table(project_id, import_log, alias=IMPORT_LOG, db_name="logs")


def dataset_aliases(project_id: str) -> list[str]:
    """Return the alias of every dataset in the import log."""
    import_log = _get_log(project_id)
    return [] if import_log.is_empty() else import_log["alias"].to_list()


def dataset_entry(project_id: str, alias: str) -> dict | None:
    """Return a dataset's import-log row, or ``None`` when it isn't there."""
    import_log = _get_log(project_id)
    if import_log.is_empty():
        return None
    rows = import_log.filter(pl.col("alias") == alias).to_dicts()
    return rows[0] if rows else None


def alias_clash_message(project_id: str, alias: str) -> str | None:
    """Say why a new alias can't be used, or ``None`` when it's free."""
    return alias_clash(alias, dataset_aliases(project_id))


def _check_new_alias(import_log: pl.DataFrame, alias: str) -> None:
    """Raise if a new alias would share a DuckDB table with an existing one."""
    if import_log.is_empty():
        return
    clash = alias_clash(alias, import_log["alias"].to_list())
    if clash:
        raise DatasetExistsError(clash)


def _append(import_log: pl.DataFrame, entry: dict) -> pl.DataFrame:
    new_row = pl.DataFrame([entry])
    if import_log.is_empty():
        return new_row
    return pl.concat([import_log, new_row], how="diagonal_relaxed")


def _update_row(import_log: pl.DataFrame, alias: str, values: dict) -> pl.DataFrame:
    """Set ``values`` on the row of ``alias``; other rows are unchanged."""
    if import_log.filter(pl.col("alias") == alias).is_empty():
        raise ValueError(f"Dataset '{alias}' is not in the import log")
    return import_log.with_columns(
        pl.when(pl.col("alias") == alias)
        .then(pl.lit(value))
        .otherwise(pl.col(column) if column in import_log.columns else None)
        .alias(column)
        for column, value in values.items()
    )


def save_local_dataset(
    project_id: str, config: FileConfig, *, edit: bool = False
) -> None:
    """Add a local file to the import log, or update its path and sheet.

    A new dataset is marked Refresh and Load. Editing keeps its switches.

    Raises
    ------
    DatasetExistsError
        When adding an alias that clashes with an existing dataset.
    """
    import_log = _get_log(project_id)
    if edit:
        import_log = _update_row(
            import_log,
            config.alias,
            {"filename": config.filename, "sheet_name": config.sheet_name or ""},
        )
    else:
        _check_new_alias(import_log, config.alias)
        entry = ImportLogEntry(
            alias=config.alias,
            filename=config.filename,
            sheet_name=config.sheet_name or "",
        )
        import_log = _append(import_log, entry.model_dump())
    _save_log(project_id, import_log)


def _surveycto_values(config: FormConfig) -> dict:
    return {
        "refresh": True,
        "load": True,
        "source": SURVEYCTO_SOURCE,
        "alias": config.alias,
        "filename": "",
        "sheet_name": "",
        "server": config.server,
        "username": config.username or "",
        "form_id": config.form_id,
        "private_key": config.private_key or "",
        "save_to": config.save_to or "",
        "attachments": config.attachments,
    }


def save_surveycto_dataset(
    project_id: str, config: FormConfig, *, edit: bool = False
) -> None:
    """Add a SurveyCTO form to the import log, or update its row.

    Adding or editing marks the dataset Refresh and Load, as the SurveyCTO
    form did before the import page redesign.

    Raises
    ------
    DatasetExistsError
        When adding an alias that clashes with an existing dataset.
    """
    import_log = _get_log(project_id)
    values = _surveycto_values(config)
    if edit:
        import_log = _update_row(import_log, config.alias, values)
    else:
        _check_new_alias(import_log, config.alias)
        import_log = _append(import_log, values)
    _save_log(project_id, import_log)


def set_dataset_flag(project_id: str, alias: str, column: str, value: bool) -> None:
    """Switch a dataset's Refresh, Load or Media (``attachments``) on or off."""
    if column not in FLAG_COLUMNS:
        raise ValueError(f"'{column}' is not a dataset switch: {FLAG_COLUMNS}")
    import_log = _update_row(_get_log(project_id), alias, {column: bool(value)})
    _save_log(project_id, import_log)


def remove_dataset(project_id: str, alias: str) -> None:
    """Remove a dataset: its import-log row, its imported, prepared and
    corrected data, its stored form definitions and its load record.
    """
    duckdb_delete_rows(
        project_id=project_id,
        alias=IMPORT_LOG,
        db_name="logs",
        column="alias",
        value=alias,
    )
    duckdb_remove_table(project_id, alias=alias, db_name="raw")
    delete_form_definitions(project_id, alias)
    for db_name in ("prep", "corrected"):
        if duckdb_table_exists(project_id, alias=alias, db_name=db_name):
            duckdb_remove_table(project_id, alias=alias, db_name=db_name)
    delete_dataset_load(project_id, alias)


def record_load(project_id: str, alias: str) -> None:
    """Record that a dataset was just loaded from its source."""
    save_dataset_load(project_id, alias, datetime.now().replace(microsecond=0))


def get_load_info(project_id: str, aliases: list[str]) -> dict[str, LoadInfo]:
    """Return the last load time and imported row count of each loaded alias.

    Aliases with neither a load record nor an imported table are left out.
    A table imported before load times were recorded has no time.
    """
    times = load_dataset_load_times(project_id)
    counts = duckdb_row_counts(project_id, aliases, "raw")
    return {
        alias: LoadInfo(times.get(alias), counts.get(alias))
        for alias in aliases
        if alias in counts or alias in times
    }
