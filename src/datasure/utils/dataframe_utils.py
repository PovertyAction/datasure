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
    integer_columns: list[str] = Field(
        default_factory=list, description="List of integer column names"
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
        """Convert None values to empty lists."""
        if v is None:
            return []
        return v


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
            print(
                f"Warning: Could not standardize missing values for column '{col}': {e}"
            )
            continue

    return data
