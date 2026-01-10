import pandas as pd
import polars as pl
from pydantic import BaseModel, Field, validator

class ColumnByType(BaseModel):
    """Class to hold columns by type."""

    all_columns: list[str] = Field(
        default_factory=list, description="List of all column names"
    )
    string_columns: list[str] = Field(
        default_factory=list, description="List of string column names"
    )
    numeric_columns: list[str] = Field(
        default_factory=list, description="List of numeric column names"
    )
    datetime_columns: list[str] = Field(
        default_factory=list, description="List of datetime column names"
    )
    categorical_columns: list[str] = Field(
        default_factory=list, description="List of categorical column names"
    )

    @validator("*", pre=True)
    def ensure_list(cls, v):
        if v is None:
            return []
        return v



def get_columns_info(
        df:pl.DataFrame | pd.DataFrame) -> ColumnByType:
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
        numeric_columns = df.select_dtypes(include=["number"]).columns.tolist()
        datetime_columns = df.select_dtypes(include=["datetime"]).columns.tolist()
        categorical_columns = df.select_dtypes(
            include=["category"]
        ).columns.tolist()

    else:  # get info from polars dataframe
        all_columns = df.columns
        string_columns = df.select(pl.col(pl.Utf8)).columns
        numeric_columns = df.select(pl.col(pl.NUMERIC_DTYPES)).columns
        datetime_columns = df.select(pl.col(pl.Date, pl.Datetime)).columns
        categorical_columns = df.select(pl.col(pl.Categorical)).columns

    return ColumnByType(
        all_columns=all_columns,
        string_columns=string_columns,
        numeric_columns=numeric_columns,
        datetime_columns=datetime_columns,
        categorical_columns=categorical_columns,
    )


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
    if isinstance(stats_df, pd.DataFrame):  # get info from pandas dataframe
        all_columns = stats_df.columns.tolist()
        string_columns = stats_df.select_dtypes(include=["object"]).columns.tolist()
        numeric_columns = stats_df.select_dtypes(include=["number"]).columns.tolist()
        datetime_columns = stats_df.select_dtypes(include=["datetime"]).columns.tolist()
        categorical_columns = stats_df.select_dtypes(
            include=["category"]
        ).columns.tolist()

        num_rows = stats_df.shape[0]
        num_columns = stats_df.shape[1]
        num_missing = stats_df.isna().sum().sum()
        perc_missing = (num_missing / (num_rows * num_columns)) * 100
    else:  # get info from polars dataframe
        all_columns = stats_df.columns
        string_columns = stats_df.select(pl.col(pl.Utf8)).columns
        numeric_columns = stats_df.select(pl.col(pl.NUMERIC_DTYPES)).columns
        datetime_columns = stats_df.select(pl.col(pl.Date, pl.Datetime)).columns
        categorical_columns = stats_df.select(pl.col(pl.Categorical)).columns

        num_rows = stats_df.height
        num_columns = stats_df.width
        num_missing = stats_df.null_count().sum()
        num_missing = num_missing.with_columns(
            pl.sum_horizontal(pl.all()).alias("row_total")
        )
        num_missing = num_missing["row_total"][0]
        perc_missing = (num_missing / (num_rows * num_columns)) * 100

    if cols_only:
        return (
            all_columns,
            string_columns,
            numeric_columns,
            datetime_columns,
            categorical_columns,
        )

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
                data = data.with_columns(
                    [
                        pl.col(col)
                        .str.strip_chars()  # Remove leading/trailing whitespace
                        .replace(
                            missing_values, None
                        )  # Replace missing value representations
                        .map_elements(
                            lambda x: None if x == "" else x, return_dtype=pl.Utf8
                        )  # Handle empty strings after stripping
                    ]
                )
            else:
                # For non-string columns, just replace the missing values
                data = data.with_columns([pl.col(col).replace(missing_values, None)])
        except Exception as e:
            # Log warning but continue processing other columns
            print(
                f"Warning: Could not standardize missing values for column '{col}': {e}"
            )
            continue

    return data
