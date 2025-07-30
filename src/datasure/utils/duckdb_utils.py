import re

import duckdb
import pandas as pd
import polars as pl

from .cache_utils import get_cache_path


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


#     ------- Save data to database ---#


def duckdb_save_table(
    project_id: str, table_data: pl.DataFrame | pd.DataFrame, alias: str, db_name: str
) -> None:
    """Save a DataFrame to a DuckDB database.

    PARAMS:
    -------
    project_id: str : project ID
    data: pl.DataFrame | pd.DataFrame : data to save
    alias: str : alias for the data
    db_name: str : name of the DuckDB database
    """
    db_path = (
        get_cache_path(project_id, "settings", "logs.duckdb")
        if db_name == "logs"
        else get_cache_path(project_id, "data", f"{db_name}.duckdb")
    )

    # convert alias to table name format and validate
    table_id = _validate_table_name(alias.lower().replace(" ", "_").replace("-", "_"))

    with duckdb.connect(db_path) as conn:
        table_exists = (
            conn.execute(
                f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table_id}'"
            ).fetchone()[0]
            > 0
        )
        if table_exists:
            conn.execute(
                f"CREATE OR REPLACE TABLE {table_id} AS SELECT * FROM table_data"
            )
        else:
            conn.execute(f"CREATE TABLE {table_id} AS SELECT * FROM table_data")
        table_exists = (
            conn.execute(
                f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table_id}'"
            ).fetchone()[0]
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
    db_path = (
        get_cache_path(project_id, "settings", "logs.duckdb")
        if db_name == "logs"
        else get_cache_path(project_id, "data", f"{db_name}.duckdb")
    )

    table_id = _validate_table_name(alias.lower().replace(" ", "_").replace("-", "_"))

    with duckdb.connect(db_path) as conn:
        # Check if the table exists
        table_exists = (
            conn.execute(
                f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table_id}'"
            ).fetchone()[0]
            > 0
        )
        if table_exists:
            if type == "pd":
                return conn.execute(f"SELECT * FROM {table_id}").fetchdf()
            else:
                return conn.execute(f"SELECT * FROM {table_id}").pl()
        else:
            if type == "pd":
                return pd.DataFrame()
            else:
                return pl.DataFrame()


def duckdb_row_filter(
    project_id: str, alias: str, db_name: str, filter_condition: str
) -> pl.DataFrame:
    """Filter rows inplace from a DuckDB table based on a condition.

    PARAMS:
    -------
    project_id: str : project ID
    alias: str : alias for the data
    db_name: str : name of the DuckDB database
    filter_condition: str : condition to filter rows

    Returns
    -------
    None
    """
    db_path = (
        get_cache_path(project_id, "settings", "logs.duckdb")
        if db_name == "logs"
        else get_cache_path(project_id, "data", f"{db_name}.duckdb")
    )
    table_id = alias.lower().replace(" ", "_").replace("-", "_")
    with duckdb.connect(db_path) as conn:
        # Create a new table with filtered rows
        conn.execute(
            f"CREATE OR REPLACE TABLE {table_id} AS SELECT * FROM {table_id} WHERE {filter_condition}"
        )
        # Optionally, return the filtered data
        return conn.execute(f"SELECT * FROM {table_id}").pl()


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
    db_path = get_cache_path(project_id, "settings", "logs.duckdb")

    with duckdb.connect(db_path) as conn:
        # create the import_log table if it doesn't exist
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

        if to_load:
            result = conn.execute(
                "SELECT DISTINCT alias FROM import_log WHERE load = TRUE"
            ).fetchall()
        else:
            result = conn.execute("SELECT DISTINCT alias FROM import_log").fetchall()
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
    with duckdb.connect(db_path) as conn:
        table_names = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'"
        ).fetchall()
        table_names = {name[0] for name in table_names}
    table_list = [x for x in aliases if x.lower().replace(" ", "_") in table_names]
    return table_list
