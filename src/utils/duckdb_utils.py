import duckdb
import pandas as pd
import polars as pl

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
    db_path = (
        f"cache/{project_id}/settings/logs.duckdb"
        if db_name == "logs"
        else f"cache/{project_id}/data/{db_name}.duckdb"
    )

    table_id = alias.lower().replace(" ", "_").replace("-", "_")

    with duckdb.connect(db_path) as conn:
        # Check if the table exists
        table_exists = (
            conn.execute(
                f"SELECT COUNT(*) FROM information_schema.tables WHERE table_name = '{table_id}'"
            ).fetchone()[0]
            > 0
        )
        if table_exists:
            return conn.execute(f"SELECT * FROM {table_id}").pl()
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
        f"cache/{project_id}/settings/logs.duckdb"
        if db_name == "logs"
        else f"cache/{project_id}/data/{db_name}.duckdb"
    )
    table_id = alias.lower().replace(" ", "_").replace("-", "_")
    with duckdb.connect(db_path) as conn:
        # Create a new table with filtered rows
        conn.execute(
            f"CREATE OR REPLACE TABLE {table_id} AS SELECT * FROM {table_id} WHERE {filter_condition}"
        )
        # Optionally, return the filtered data
        return conn.execute(f"SELECT * FROM {table_id}").pl()


def duckdb_get_aliases(project_id: str, to_load: bool = True) -> list[str]:
    """Get all aliases (table names) from import log.

    PARAMS:
    -------
    project_id: str : project ID

    Returns
    -------
    list[str] : list of aliases (table names)
    """
    db_path = f"cache/{project_id}/settings/logs.duckdb"

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
