from datetime import datetime

import pandas as pd
import polars as pl
import pytest

from datasure.utils.dataframe_utils import get_df_info


class TestGetDfInfo:
    """Test cases for get_df_info function."""

    def test_get_df_info_with_polars_dataframe(self):
        """Test get_df_info with a Polars DataFrame."""
        # Create test data with various column types
        df = pl.DataFrame(
            {
                "string_col": ["a", "b", None, "d"],
                "int_col": [1, 2, 3, None],
                "float_col": [1.1, 2.2, None, 4.4],
                "datetime_col": [
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 2),
                    None,
                    datetime(2024, 1, 4),
                ],
                "categorical_col": pl.Series(
                    ["cat1", "cat2", "cat1", None], dtype=pl.Categorical
                ),
            }
        )

        result = get_df_info(df)

        # Check return tuple structure
        assert len(result) == 9
        (
            num_rows,
            num_columns,
            num_missing,
            perc_missing,
            all_columns,
            string_columns,
            numeric_columns,
            datetime_columns,
            categorical_columns,
        ) = result

        # Check basic dimensions
        assert num_rows == 4
        assert num_columns == 5
        assert num_missing == 5  # 5 null values total
        assert perc_missing == 25.0  # 5 missing out of 20 total values

        # Check column classifications
        assert "string_col" in string_columns
        assert "int_col" in numeric_columns
        assert "float_col" in numeric_columns
        assert "datetime_col" in datetime_columns
        assert "categorical_col" in categorical_columns

        # Check all columns are present
        assert set(all_columns) == {
            "string_col",
            "int_col",
            "float_col",
            "datetime_col",
            "categorical_col",
        }

    def test_get_df_info_with_pandas_dataframe(self):
        """Test get_df_info with a Pandas DataFrame (should be converted to Polars)."""
        # Create test data
        df = pd.DataFrame(
            {
                "name": ["Alice", "Bob", None],
                "age": [25, 30, 35],
                "score": [85.5, None, 92.0],
            }
        )

        result = get_df_info(df)

        # Check return tuple structure
        assert len(result) == 9
        (
            num_rows,
            num_columns,
            num_missing,
            perc_missing,
            all_columns,
            string_columns,
            numeric_columns,
            datetime_columns,
            categorical_columns,
        ) = result

        # Check basic dimensions
        assert num_rows == 3
        assert num_columns == 3
        assert num_missing == 2  # 2 null values total
        assert perc_missing == pytest.approx(
            22.222, rel=1e-3
        )  # 2 missing out of 9 total values

        # Check column classifications
        assert "name" in string_columns
        assert "age" in numeric_columns
        assert "score" in numeric_columns
        assert len(datetime_columns) == 0
        assert len(categorical_columns) == 0

    def test_get_df_info_cols_only_true(self):
        """Test get_df_info with cols_only=True."""
        df = pl.DataFrame(
            {
                "text": ["hello", "world"],
                "number": [1, 2],
                "date": [datetime(2024, 1, 1), datetime(2024, 1, 2)],
                "category": pl.Series(["A", "B"], dtype=pl.Categorical),
            }
        )

        result = get_df_info(df, cols_only=True)

        # Check return tuple structure - should only return column info
        assert len(result) == 5
        (
            all_columns,
            string_columns,
            numeric_columns,
            datetime_columns,
            categorical_columns,
        ) = result

        # Check column classifications
        assert "text" in string_columns
        assert "number" in numeric_columns
        assert "date" in datetime_columns
        assert "category" in categorical_columns
        assert set(all_columns) == {"text", "number", "date", "category"}

    def test_get_df_info_no_missing_values(self):
        """Test get_df_info with a DataFrame containing no missing values."""
        df = pl.DataFrame(
            {
                "name": ["Alice", "Bob", "Charlie"],
                "age": [25, 30, 35],
                "active": [True, False, True],
            }
        )

        result = get_df_info(df)

        (
            num_rows,
            num_columns,
            num_missing,
            perc_missing,
            all_columns,
            string_columns,
            numeric_columns,
            datetime_columns,
            categorical_columns,
        ) = result

        # Check basic dimensions
        assert num_rows == 3
        assert num_columns == 3
        assert num_missing == 0
        assert perc_missing == 0.0

        # Check column classifications
        assert "name" in string_columns
        assert "age" in numeric_columns
        # Note: boolean columns might be classified differently in Polars

    def test_get_df_info_all_missing_values(self):
        """Test get_df_info with a DataFrame where all values are missing."""
        df = pl.DataFrame({"col1": [None, None], "col2": [None, None]}).cast(
            {"col1": pl.Utf8, "col2": pl.Int64}
        )

        result = get_df_info(df)

        (
            num_rows,
            num_columns,
            num_missing,
            perc_missing,
            all_columns,
            string_columns,
            numeric_columns,
            datetime_columns,
            categorical_columns,
        ) = result

        # Check basic dimensions
        assert num_rows == 2
        assert num_columns == 2
        assert num_missing == 4  # All 4 values are missing
        assert perc_missing == 100.0

    def test_get_df_info_single_column(self):
        """Test get_df_info with a single column DataFrame."""
        df = pl.DataFrame({"single_col": ["a", "b", None, "d"]})

        result = get_df_info(df)

        (
            num_rows,
            num_columns,
            num_missing,
            perc_missing,
            all_columns,
            string_columns,
            numeric_columns,
            datetime_columns,
            categorical_columns,
        ) = result

        # Check basic dimensions
        assert num_rows == 4
        assert num_columns == 1
        assert num_missing == 1
        assert perc_missing == 25.0

        # Check column classifications
        assert all_columns == ["single_col"]
        assert string_columns == ["single_col"]
        assert len(numeric_columns) == 0
        assert len(datetime_columns) == 0
        assert len(categorical_columns) == 0

    def test_get_df_info_mixed_numeric_types(self):
        """Test get_df_info with mixed numeric types (Int64, Float64)."""
        df = pl.DataFrame({"int_col": [1, 2, 3], "float_col": [1.1, 2.2, 3.3]})

        result = get_df_info(df)

        (
            num_rows,
            num_columns,
            num_missing,
            perc_missing,
            all_columns,
            string_columns,
            numeric_columns,
            datetime_columns,
            categorical_columns,
        ) = result

        # Both int and float columns should be in numeric_columns
        assert "int_col" in numeric_columns
        assert "float_col" in numeric_columns
        assert len(numeric_columns) == 2

    def test_get_df_info_datetime_column(self):
        """Test get_df_info specifically with datetime columns."""
        df = pl.DataFrame(
            {"date_col": [datetime(2024, 1, 1), datetime(2024, 1, 2), None]}
        )

        result = get_df_info(df)

        (
            num_rows,
            num_columns,
            num_missing,
            perc_missing,
            all_columns,
            string_columns,
            numeric_columns,
            datetime_columns,
            categorical_columns,
        ) = result

        # Check datetime column is properly classified
        assert "date_col" in datetime_columns
        assert len(datetime_columns) == 1
        assert len(string_columns) == 0
        assert len(numeric_columns) == 0

    def test_get_df_info_categorical_column(self):
        """Test get_df_info specifically with categorical columns."""
        df = pl.DataFrame(
            {"cat_col": pl.Series(["A", "B", "A", None], dtype=pl.Categorical)}
        )

        result = get_df_info(df)

        (
            num_rows,
            num_columns,
            num_missing,
            perc_missing,
            all_columns,
            string_columns,
            numeric_columns,
            datetime_columns,
            categorical_columns,
        ) = result

        # Check categorical column is properly classified
        assert "cat_col" in categorical_columns
        assert len(categorical_columns) == 1
        assert len(string_columns) == 0
        assert len(numeric_columns) == 0
        assert len(datetime_columns) == 0
