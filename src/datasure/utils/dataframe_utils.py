import logging

import pandas as pd
import polars as pl

from datasure.models.schemas import ColumnByType

logger = logging.getLogger(__name__)


def get_df_columns(df: pl.DataFrame | pd.DataFrame) -> ColumnByType:
    """Get columns by type from a DataFrame.
    PARAMS:
    -------
    df: pl.DataFrame | pd.DataFrame : DataFrame to analyze

    Returns
    -------
    ColumnByType: Object containing lists of columns by type
    """
    if isinstance(df, pd.DataFrame):  # get info from pandas dataframe
        all_columns = df.columns.tolist()
        string_columns = df.select_dtypes(include=["object"]).columns.tolist()
        integer_columns = df.select_dtypes(include=["int"]).columns.tolist()
        numeric_columns = df.select_dtypes(include=["number"]).columns.tolist()
        datetime_columns = df.select_dtypes(include=["datetime"]).columns.tolist()
        categorical_columns = list(
            set(
                integer_columns
                + string_columns
                + df.select_dtypes(include=["category"]).columns.tolist()
            )
        )

    else:  # get info from polars dataframe
        all_columns = df.columns
        string_columns = df.select(pl.col(pl.Utf8)).columns
        integer_columns = df.select(
            pl.col(pl.Int64, pl.Int32, pl.Int16, pl.Int8)
        ).columns
        numeric_columns = df.select(pl.col(pl.NUMERIC_DTYPES)).columns
        datetime_columns = df.select(pl.col(pl.Date, pl.Datetime)).columns
        categorical_columns = list(
            set(
                integer_columns
                + string_columns
                + df.select(pl.col(pl.Categorical)).columns
            )
        )

    return ColumnByType(
        all_columns=all_columns,
        string_columns=string_columns,
        integer_columns=integer_columns,
        numeric_columns=numeric_columns,
        datetime_columns=datetime_columns,
        categorical_columns=categorical_columns,
    )


def standardize_missing_values(data: pd.DataFrame | pl.DataFrame) -> pl.DataFrame:
    """Convert data to polars dataframe and standardize missing values"""
    # if pandas dataframe, convert to polars
    if isinstance(data, pd.DataFrame):
        data = pl.from_pandas(data)

    # Define common missing value representations to standardize
    missing_values = [
        "",
        "   ",
        "\t",
        "\n",  # Empty/whitespace strings
        "NULL",
        "null",
        "Null",
        "None",
        "none",
        "NONE",  # Explicit nulls
        "N/A",
        "n/a",
        "NA",
        "na",
        "#N/A",
        "N/a",  # Not available
        "-",
        "--",
        ".",
        "?",
        "???",  # Common placeholders
        "Missing",
        "missing",
        "MISSING",  # Explicit missing
        "Unknown",
        "unknown",
        "UNKNOWN",  # Unknown values
        "NaN",
        "NAN",  # String representations of NaN
        "nan",
        "NaT",  # Additional representations
    ]
    # Loop through columns and convert all missing values to polars null
    for col in data.columns:
        try:
            # For string columns, also handle whitespace-only strings
            if data[col].dtype == pl.Utf8:
                # Strip whitespace first
                data = data.with_columns(pl.col(col).str.strip_chars().alias(col))

                # Replace all missing value representations with null using is_in
                data = data.with_columns(
                    pl.when(pl.col(col).is_in(missing_values))
                    .then(None)
                    .otherwise(pl.col(col))
                    .alias(col)
                )
            else:
                # For non-string columns, check if values are in missing_values list
                # This handles cases where non-string types might have been imported
                data = data.with_columns(
                    pl.when(pl.col(col).cast(pl.Utf8).is_in(missing_values))
                    .then(None)
                    .otherwise(pl.col(col))
                    .alias(col)
                )
        except Exception as e:
            # Log warning but continue processing other columns
            logger.warning(
                "Could not standardize missing values for column '%s': %s", col, e
            )
            continue

    return data


def sanitize_df_for_join(
    main_df: pl.DataFrame,
    join_df: pl.DataFrame,
    join_key: str,
) -> pl.DataFrame:
    """Sanitize join DataFrame to avoid column name conflicts.

    Parameters
    ----------
    main_df : pl.DataFrame
        Main DataFrame.
    join_df : pl.DataFrame
        DataFrame to join.
    join_key : str
        Column name to join on.

    Returns
    -------
    pl.DataFrame
        Sanitized join DataFrame.
    """
    main_cols = main_df.columns
    join_cols = join_df.columns

    sanitized_cols = [
        col for col in join_cols if col not in main_cols or col == join_key
    ]

    return join_df.select(sanitized_cols)


def convert_series_to_numeric(series: pl.Series) -> pl.Series:
    """Convert a Polars Series to numeric type.

    Parameters
    ----------
    series : pl.Series
        Series to convert.

    Returns
    -------
    pl.Series
        Converted series.

    Raises
    ------
    ValueError
        If conversion fails.
    """
    if series.dtype in pl.NUMERIC_DTYPES:
        return series.cast(pl.Float64)

    try:
        return series.cast(pl.Float64, strict=False)
    except Exception as e:
        raise ValueError(
            f"Could not convert Series to numeric: {e}, keeping as {series.dtype}"
        ) from e


def convert_dataframe_column_to_numeric(df: pl.DataFrame, column: str) -> pl.DataFrame:
    """Convert a DataFrame column to numeric type.

    Parameters
    ----------
    df : pl.DataFrame
        DataFrame containing the column.
    column : str
        Column name to convert.

    Returns
    -------
    pl.DataFrame
        DataFrame with converted column.

    Raises
    ------
    ValueError
        If conversion fails.
    """
    if df[column].dtype in pl.NUMERIC_DTYPES:
        return df.with_columns(pl.col(column).cast(pl.Float64).alias(column))

    try:
        return df.with_columns(
            pl.col(column).cast(pl.Float64, strict=False).alias(column)
        )
    except Exception as e:
        raise ValueError(
            f"Could not convert column '{column}' to numeric: {e}, keeping as {df[column].dtype}"
        ) from e


def safe_to_numeric(
    data: pl.DataFrame | pl.Series, column: str | None = None
) -> pl.DataFrame | pl.Series:
    """Safely convert columns to numeric, keeping original if conversion fails.

    Parameters
    ----------
    data : pl.DataFrame | pl.Series
        Data to convert.
    column : str | None
        Column name to convert (required for DataFrames).

    Returns
    -------
    pl.DataFrame | pl.Series
        Converted data.

    Raises
    ------
    ValueError
        If conversion fails or invalid inputs provided.
    TypeError
        If input is not a Polars DataFrame or Series.
    """
    if isinstance(data, pl.Series):
        return convert_series_to_numeric(data)

    if isinstance(data, pl.DataFrame):
        if not column:
            raise ValueError("Column is required with dataframes")
        return convert_dataframe_column_to_numeric(data, column)

    raise TypeError("Input data must be a Polars DataFrame or Series.")
