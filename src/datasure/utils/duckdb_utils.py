import logging
import random
import re
import time
from pathlib import Path

import duckdb  # type: ignore
import pandas as pd
import polars as pl

from .cache_utils import get_cache_path

# Set up logging
logger = logging.getLogger(__name__)


def name_id(name: str) -> str:
    """Return the identifier form of a page or dataset name.

    Lower case, with spaces and hyphens as underscores. Used for table names,
    settings file names and the Corrections ``page`` URL value.
    """
    return name.lower().replace(" ", "_").replace("-", "_")


# Per-page check tables in the ``logs`` database are named
# ``{prefix}_{page_name_id}``. Checks build their table names from these
# prefixes with ``check_table_name``, and ``CHECK_TABLE_PREFIXES`` lists the
# ones exported with project configurations, so a rename stays in sync.
DUPLICATES_TABLE = "duplicates"
OUTLIERS_TABLE = "outliers"
GPS_COLUMNS_TABLE = "gps_columns"
BACKCHECKS_TABLE = "backchecks"
DESCRIPTIVE_COLUMNS_TABLE = "descriptive_columns"
BC_ATTRIBUTION_TABLE = "bc_attribution"

# Older versions saved one descriptive selection for the whole project in
# this ``intermediate`` table instead of one per page.
LEGACY_DESCRIPTIVE_SELECTION_TABLE = "selected_columns_df"

CHECK_TABLE_PREFIXES: tuple[str, ...] = (
    DUPLICATES_TABLE,
    OUTLIERS_TABLE,
    GPS_COLUMNS_TABLE,
    BACKCHECKS_TABLE,
    DESCRIPTIVE_COLUMNS_TABLE,
    BC_ATTRIBUTION_TABLE,
)


def check_table_name(prefix: str, page_name: str) -> str:
    """Return the ``logs`` table name of a page's check table.

    ``page_name`` may be the page's display name or its ``name_id``.
    """
    return f"{prefix}_{name_id(page_name)}"


def missing_codes_table_name(project_id: str) -> str:
    """Return the ``logs`` table name of a project's missing codes."""
    return f"missing_codes_{project_id}"


def _validate_table_name(table_name: str) -> str:
    """Validate and sanitize table name to prevent SQL injection.

    Args:
        table_name: The table name to validate

    Returns
    -------
        str: Sanitized table name

    Raises
    ------
        ValueError: If table name contains invalid characters
    """
    # Remove dangerous characters and ensure only alphanumeric and underscores
    sanitized = re.sub(r"[^a-zA-Z0-9_]", "_", table_name)

    # Ensure it starts with a letter or underscore
    if not re.match(r"^[a-zA-Z_]", sanitized):
        sanitized = f"table_{sanitized}"

    # Check for SQL keywords (basic list)
    sql_keywords = {
        "select",
        "insert",
        "update",
        "delete",
        "drop",
        "create",
        "alter",
        "table",
        "database",
        "index",
        "view",
        "union",
        "where",
        "from",
    }

    if sanitized.lower() in sql_keywords:
        sanitized = f"{sanitized}_table"

    return sanitized


def database_path(project_id: str, db_name: str) -> Path:
    """Return the path of a project's DuckDB database file.

    The ``logs`` database lives with the project's settings; the others
    (``raw``, ``prep``, ``corrected``, ``intermediate``) with its data.
    """
    if db_name == "logs":
        return get_cache_path(project_id, "settings", "logs.duckdb")
    return get_cache_path(project_id, "data", f"{db_name}.duckdb")


# How long to wait for a database that is open elsewhere in a conflicting
# mode before giving up.
_BUSY_TIMEOUT_SECONDS = 5.0


def _connect(db_path: Path, *, read_only: bool = False):
    """Open a project database, waiting while it is busy.

    DuckDB lets a database file be open for writing by one process, or for
    reading by several, never both. Reads therefore open read-only, so that
    two sessions, browser tabs or processes on one project can read at the
    same time, and every open waits up to ``_BUSY_TIMEOUT_SECONDS`` for a
    conflicting connection to close instead of failing at once. Within one
    process DuckDB refuses to mix read-only and writable connections to the
    same file (``ConnectionException``); across processes the file is locked
    (``IOException``). Both are retried.

    A database that doesn't exist yet can't be opened read-only, so it is
    opened writable, which creates it empty as before.

    An ``IOException`` with another cause (an unreadable or corrupt file) is
    raised after the same wait.
    """
    kwargs = {"read_only": True} if read_only and Path(db_path).exists() else {}
    deadline = time.monotonic() + _BUSY_TIMEOUT_SECONDS
    while True:
        try:
            return duckdb.connect(db_path, **kwargs)
        except (duckdb.IOException, duckdb.ConnectionException):
            if time.monotonic() >= deadline:
                raise
            # Random, so two waiting connections don't retry in step.
            time.sleep(random.uniform(0.005, 0.03))


#     ------- Save data to database ---#


def duckdb_save_table(
    project_id: str, table_data, alias: str, db_name: str = "raw"
) -> None:
    """Save a DataFrame to a DuckDB database.

    PARAMS:
    -------
    project_id: str : project ID
    data: pl.DataFrame | pd.DataFrame : data to save
    alias: str : alias for the data
    db_name: str : name of the DuckDB database
    """
    db_path = database_path(project_id, db_name)

    # convert alias to table name format and validate
    table_id = _validate_table_name(name_id(alias))

    with _connect(db_path) as conn:
        table_exists = (
            conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                [table_id],
            ).fetchall()[0][0]
            > 0
        )
        if table_exists:
            conn.execute(
                f"CREATE OR REPLACE TABLE {table_id} AS SELECT * FROM table_data"
            )
        else:
            conn.execute(f"CREATE TABLE {table_id} AS SELECT * FROM table_data")


def duckdb_get_table(
    project_id: str, alias: str, db_name: str, type: str = "pl"
) -> pl.DataFrame:
    """Get a table from a DuckDB database.

    PARAMS:
    -------
    project_id: str : project ID
    alias: str : alias for the data
    db_name: str : name of the DuckDB database

    Returns
    -------
    pl.DataFrame : data from the DuckDB table
    """
    # validate return type
    if type not in ["pl", "pd"]:
        raise ValueError(
            "Invalid type specified. Use 'pl' for Polars or 'pd' for Pandas."
        )
    db_path = database_path(project_id, db_name)

    table_id = _validate_table_name(name_id(alias))

    with _connect(db_path, read_only=True) as conn:
        # Check if the table exists
        table_exists = (
            conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                [table_id],
            ).fetchall()[0][0]
            > 0
        )
        if table_exists:
            if type == "pd":
                return conn.execute(f"SELECT * FROM {table_id}").fetchdf()
            else:
                # Relation .pl(): DuckDB 2.0 dropped .pl() on execute() results.
                return conn.sql(f"SELECT * FROM {table_id}").pl()
        else:
            if type == "pd":
                return pd.DataFrame()
            else:
                return pl.DataFrame()


def duckdb_remove_table(project_id: str, alias: str, db_name: str) -> None:
    """Delete a table from a DuckDB database.

    PARAMS:
    -------
    project_id: str : project ID
    alias: str : alias for the data
    db_name: str : name of the DuckDB database

    Returns
    -------
    None
    """
    db_path = database_path(project_id, db_name)
    table_id = _validate_table_name(name_id(alias))
    with _connect(db_path) as conn:
        # Check if the table exists
        table_exists = (
            conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                [table_id],
            ).fetchall()[0][0]
            > 0
        )
        if table_exists:
            conn.execute(f"DROP TABLE {table_id}")


def _validate_column_name(column_name: str) -> str:
    """Validate a column name used in a SQL statement.

    Unlike table aliases, column names are not sanitized: a silently
    rewritten column would target the wrong data, so invalid names are
    rejected instead.

    Args:
        column_name: The column name to validate

    Returns
    -------
        str: The validated column name

    Raises
    ------
        ValueError: If the column name is not a valid SQL identifier
    """
    if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", column_name):
        raise ValueError(f"Invalid column name: {column_name!r}")
    return column_name


def duckdb_delete_rows(
    project_id: str, alias: str, db_name: str, column: str, value: str
) -> None:
    """Delete rows from a DuckDB table where a column equals a value.

    The value is passed as a prepared-statement parameter, so it is safe
    for arbitrary user-supplied strings.

    PARAMS:
    -------
    project_id: str : project ID
    alias: str : alias for the data
    db_name: str : name of the DuckDB database
    column: str : column to match rows on
    value: str : rows with this value in `column` are deleted

    Returns
    -------
    None
    """
    db_path = database_path(project_id, db_name)
    table_id = _validate_table_name(name_id(alias))
    column_id = _validate_column_name(column)
    with _connect(db_path) as conn:
        conn.execute(f"DELETE FROM {table_id} WHERE {column_id} = ?", [value])


# --- Get aliases from import log ---#


def duckdb_get_aliases(project_id: str, to_load: bool = True) -> list[str]:
    """Get all aliases (table names) from import log.

    PARAMS:
    -------
    project_id: str : project ID

    Returns
    -------
    list[str] : list of aliases (table names)
    """
    db_path = database_path(project_id, "logs")
    query = "SELECT DISTINCT alias FROM import_log"
    if to_load:
        query += " WHERE load = TRUE"

    try:
        with _connect(db_path, read_only=True) as conn:
            result = conn.execute(query).fetchall()
    except duckdb.CatalogException:
        # No import log yet. Creating it needs a writable connection, which
        # is why the read above doesn't do it.
        with _connect(db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS import_log (
                    refresh BOOLEAN,
                    load BOOLEAN,
                    source VARCHAR,
                    alias VARCHAR,
                    filename VARCHAR,
                    sheet_name VARCHAR,
                    server VARCHAR,
                    form_id VARCHAR,
                    private_key VARCHAR,
                    save_to VARCHAR,
                    attachments BOOLEAN
                )
                """
            )
        result = []
    return [row[0] for row in result] if result else []


# --- Get list of imported and loaded datasets ---#
def duckdb_get_imported_datasets(project_id: str) -> list[str]:
    """Get a list of imported and loaded datasets from the import log.

    Compare databases in import log with the database in db and return
    the list of imported datasets.

    PARAMS:
    -------
    project_id: str : project ID

    Returns
    -------
    list
    """
    # get aliases from import log
    aliases = duckdb_get_aliases(project_id, to_load=True)

    # get list of tables in the database
    db_path = get_cache_path(project_id, "data", "raw.duckdb")
    with _connect(db_path, read_only=True) as conn:
        table_names = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        table_names = {name[0] for name in table_names}
    table_list = [x for x in aliases if x.lower().replace(" ", "_") in table_names]
    return table_list


def duckdb_table_exists(project_id: str, alias: str, db_name: str) -> bool:
    """Check if a table exists in a DuckDB database.

    PARAMS:
    -------
    project_id: str : project ID
    alias: str : alias for the data
    db_name: str : name of the DuckDB database

    Returns
    -------
    bool : True if table exists, False otherwise
    """
    db_path = database_path(project_id, db_name)

    table_id = _validate_table_name(name_id(alias))

    with _connect(db_path, read_only=True) as conn:
        # Check if the table exists
        table_exists = (
            conn.execute(
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_name = ?",
                [table_id],
            ).fetchall()[0][0]
            > 0
        )
        return table_exists


# =============================================================================
# DuckDB Storage Functions for Missing Codes
# =============================================================================


def load_missing_codes_from_db(project_id: str) -> pl.DataFrame:
    """Load missing codes from DuckDB.

    Parameters
    ----------
    project_id : str
        The project identifier.

    Returns
    -------
    list[MissingCode]
        List of missing code configurations.
    """
    table_name = missing_codes_table_name(project_id)

    return duckdb_get_table(project_id, table_name, "logs")


def save_missing_codes_to_db(project_id: str, new_codes: dict | None = None) -> None:
    """Save missing codes to DuckDB.

    Parameters
    ----------
    project_id : str
        The project identifier.
    missing_codes : list[MissingCode]
        List of missing code configurations.
    """
    table_name = missing_codes_table_name(project_id)

    # get current missing codes from db
    existing_missing_codes = load_missing_codes_from_db(project_id)

    if new_codes:
        # append new missing codes dict to pl.DataFrame
        new_codes_df = pl.DataFrame(new_codes)
        if existing_missing_codes.is_empty():
            missing_df = new_codes_df
        else:
            missing_df = pl.concat([existing_missing_codes, new_codes_df])

    else:
        missing_df = existing_missing_codes

    duckdb_save_table(project_id, missing_df, table_name, "logs")


def add_missing_code(project_id: str, label: str, codes: str | list[str]) -> None:
    """Add a new missing code configuration.

    Parameters
    ----------
    project_id : str
        The project identifier.
    label : str
        Label for the missing value type.
    codes : str | list[str]
        Missing codes (comma-separated string or list).
    """
    # check for duplicates
    existing_codes = load_missing_codes_from_db(project_id)
    if not existing_codes.is_empty():
        existing_labels = existing_codes["label"].to_list()
        if label in existing_labels:
            raise ValueError(f"Missing code with label '{label}' already exists.")

    new_code = {"label": label, "codes": codes}
    save_missing_codes_to_db(project_id, new_code)


def update_missing_code(project_id: str, label: str, codes: str | list[str]) -> None:
    """Update an existing missing code configuration.

    Parameters
    ----------
    project_id : str
        The project identifier.
    code_id : str
        The ID of the missing code to update.
    label : str
        New label for the missing value type.
    codes : str | list[str]
        New missing codes.
    """
    existing_codes = load_missing_codes_from_db(project_id)
    # replace the code with matching label in pl.DataFrame
    existing_codes = existing_codes.with_columns(
        pl.when(pl.col("label") == label)
        .then(pl.struct([pl.lit(label).alias("label"), pl.lit(codes).alias("codes")]))
        .otherwise(pl.struct([pl.col("label"), pl.col("codes")]))
        .alias("codes")
    ).unnest("codes")

    save_missing_codes_to_db(project_id, existing_codes)


def delete_missing_code(project_id: str, code_id: str) -> None:
    """Delete a missing code configuration.

    Parameters
    ----------
    project_id : str
        The project identifier.
    code_id : str
        The ID of the missing code to delete.
    """
    existing_codes = load_missing_codes_from_db(project_id)
    existing_codes = [mc for mc in existing_codes if mc.id != code_id]
    save_missing_codes_to_db(project_id, existing_codes)
