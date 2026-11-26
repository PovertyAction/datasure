"""Codebook generation from a Polars DataFrame."""

from __future__ import annotations

from collections.abc import Mapping

import polars as pl


def final_columns(df: pl.DataFrame, name_map: Mapping[str, str]) -> dict[str, dict]:
    """Return each final-data column's Stata name and counts, for the dictionary.

    Keyed by the column's name before Stata renaming, as the data dictionary's
    variables are. ``name_map`` holds only the names Stata can't use. Sample
    values are left out: the dictionary never shows values of PII columns.
    """
    return {
        col: {
            "stata_name": name_map.get(col, col),
            "final_missing_rate": df[col].null_count() / df.height
            if df.height
            else None,
            "final_unique": df[col].n_unique(),
        }
        for col in df.columns
    }


def generate_codebook(df: pl.DataFrame) -> str:
    """Generate a codebook CSV from a DataFrame.

    Produces one row per column with type, missing count, unique count,
    and a pipe-separated sample of up to five non-null values.

    Parameters
    ----------
    df : pl.DataFrame
        The dataset to describe (typically the corrected dataset).

    Returns
    -------
    str
        CSV content as a string.
    """
    if df.is_empty():
        header = "variable,type,n_total,n_missing,n_unique,sample_values\n"
        return header

    rows: list[dict] = []
    for col in df.columns:
        series = df[col]
        dtype = series.dtype

        if dtype in (
            pl.Int8,
            pl.Int16,
            pl.Int32,
            pl.Int64,
            pl.UInt8,
            pl.UInt16,
            pl.UInt32,
            pl.UInt64,
            pl.Float32,
            pl.Float64,
        ):
            col_type = "numeric"
        elif dtype == pl.Date or isinstance(dtype, pl.Datetime):
            col_type = "datetime"
        elif dtype == pl.Boolean:
            col_type = "boolean"
        else:
            col_type = "text"

        n_missing = series.null_count()
        n_unique = series.n_unique()

        non_null = series.drop_nulls()
        if non_null.is_empty():
            sample_values = ""
        else:
            sample = non_null.unique().head(5).cast(pl.String).to_list()
            sample_values = " | ".join(str(v) for v in sample)

        rows.append(
            {
                "variable": col,
                "type": col_type,
                "n_total": df.height,
                "n_missing": n_missing,
                "n_unique": n_unique,
                "sample_values": sample_values,
            }
        )

    return pl.DataFrame(rows).write_csv()
