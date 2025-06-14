import re

import duckdb
import pandas as pd
import polars as pl


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
        f"cache/{project_id}/settings/logs.duckdb"
        if db_name == "logs"
        else f"cache/{project_id}/data/{db_name}.duckdb"
    )

    table_id = alias.lower().replace(" ", "_").replace(" ", "_")
    # Create a DuckDB connection
    db_path = f"cache/{project_id}/data/{db_name}.duckdb"
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


def duckdb_get_table(project_id: str, alias: str, db_name: str) -> pl.DataFrame:
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
    db_path = f"cache/{project_id}/data/{db_name}.duckdb"
    table_id = _validate_table_name(alias.lower().replace(" ", "_").replace("-", "_"))

    with duckdb.connect(db_path) as conn:
        return conn.execute(f'SELECT * FROM "{table_id}"').pl()
