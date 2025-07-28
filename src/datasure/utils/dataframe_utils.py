import pandas as pd
import polars as pl


def get_df_info(stats_df: pl.DataFrame | pd.DataFrame, cols_only=False) -> tuple:
    """Get a description of the DataFrame.

    PARAMS:
    -------
    df: pl.DataFrame | pd.DataFrame : DataFrame to describe

    Returns
    -------
    tuple:
        int: number of rows in the DataFrame
        int: number of columns in the DataFrame
        int: number of missing values in the DataFrame
        float: percentage of missing values in the DataFrame
        list[str]: list of column names in the DataFrame
        list[str]: list of string column types in the DataFrame
        list[str]: list of numeric column types in the DataFrame
        list[str]: list of datetime column types in the DataFrame
        list[str]: list of categorical column types in the DataFrame
    """
    if isinstance(stats_df, pd.DataFrame):
        stats_df = pl.from_pandas(stats_df)

    # return column types
    all_columns = stats_df.columns
    string_columns = stats_df.select(pl.col(pl.Utf8)).columns
    numeric_columns = stats_df.select(pl.col(pl.NUMERIC_DTYPES)).columns
    datetime_columns = stats_df.select(pl.col(pl.Date, pl.Datetime)).columns
    categorical_columns = stats_df.select(pl.col(pl.Categorical)).columns

    if cols_only:
        return (
            all_columns,
            string_columns,
            numeric_columns,
            datetime_columns,
            categorical_columns,
        )

    num_rows = stats_df.height
    num_columns = stats_df.width
    num_missing = stats_df.null_count().sum()
    num_missing = num_missing.with_columns(
        pl.sum_horizontal(pl.all()).alias("row_total")
    )
    num_missing = num_missing["row_total"][0]
    perc_missing = (num_missing / (num_rows * num_columns)) * 100

    return (
        num_rows,
        num_columns,
        num_missing,
        perc_missing,
        all_columns,
        string_columns,
        numeric_columns,
        datetime_columns,
        categorical_columns,
    )
