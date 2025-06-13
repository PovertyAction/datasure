import duckdb
import pandas as pd
import polars as pl


#     ------- Save data to database ---#
def save_to_duckdb(
    project_id: str, data: pl.DataFrame | pd.DataFrame, alias: str, db_name: str
) -> None:
    """Save data to a DuckDB database.

    PARAMS:
    -------
    project_id: str : project ID
    data: pl.DataFrame | pd.DataFrame : data to save
    alias: str : alias for the data
    db_name: str : name of the DuckDB database
    """
    # Create a DuckDB connection
    db_path = f"cache/{project_id}/data/{db_name}.duckdb"
    # convert alias to table name format
    table_id = alias.lower().replace(" ", "_").replace(" ", "_")

    with duckdb.connect(db_path) as conn:
        # Create a new table and insert data
        conn.execute(
            f"CREATE TABLE IF NOT EXISTS {table_id} AS SELECT * FROM data LIMIT 0"
        )
        conn.execute(f"CREATE OR REPLACE TABLE {table_id} AS SELECT * FROM data")


def get_duckdb_table(project_id: str, alias: str, db_name: str) -> pl.DataFrame:
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
    table_id = alias.lower().replace(" ", "_").replace("-", "_")

    with duckdb.connect(db_path) as conn:
        return conn.execute(f"SELECT * FROM {table_id}").pl()
