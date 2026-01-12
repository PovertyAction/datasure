"""Comprehensive tests for dataframe utilities module."""

from datetime import datetime
from unittest.mock import patch

import pandas as pd
import polars as pl
import pytest

from datasure.utils.dataframe_utils import (
    ColumnByType,
    get_df_columns,
    standardize_missing_values,
)

# ============================================================================
# PYDANTIC MODEL TESTS
# ============================================================================


class TestColumnByType:
    """Test ColumnByType Pydantic model."""

    def test_initialization_with_defaults(self):
        """Test that ColumnByType initializes with empty lists by default."""
        col_type = ColumnByType()

        assert col_type.all_columns == []
        assert col_type.string_columns == []
        assert col_type.integer_columns == []
        assert col_type.numeric_columns == []
        assert col_type.datetime_columns == []
        assert col_type.categorical_columns == []

    def test_initialization_with_values(self):
        """Test initializing ColumnByType with all fields."""
        col_type = ColumnByType(
            all_columns=["col1", "col2", "col3"],
            string_columns=["col1"],
            integer_columns=["col2"],
            numeric_columns=["col2", "col3"],
            datetime_columns=["col4"],
            categorical_columns=["col1", "col2"],
        )

        assert col_type.all_columns == ["col1", "col2", "col3"]
        assert col_type.string_columns == ["col1"]
        assert col_type.integer_columns == ["col2"]
        assert col_type.numeric_columns == ["col2", "col3"]
        assert col_type.datetime_columns == ["col4"]
        assert col_type.categorical_columns == ["col1", "col2"]

    def test_validator_converts_none_to_empty_list(self):
        """Test that None values are converted to empty lists."""
        col_type = ColumnByType(
            all_columns=None,
            string_columns=None,
            integer_columns=None,
            numeric_columns=None,
            datetime_columns=None,
            categorical_columns=None,
        )

        assert col_type.all_columns == []
        assert col_type.string_columns == []
        assert col_type.integer_columns == []
        assert col_type.numeric_columns == []
        assert col_type.datetime_columns == []
        assert col_type.categorical_columns == []

    def test_partial_initialization(self):
        """Test initializing with some fields and leaving others default."""
        col_type = ColumnByType(
            all_columns=["a", "b"],
            string_columns=["a"],
        )

        assert col_type.all_columns == ["a", "b"]
        assert col_type.string_columns == ["a"]
        assert col_type.integer_columns == []
        assert col_type.numeric_columns == []
        assert col_type.datetime_columns == []
        assert col_type.categorical_columns == []

    def test_empty_lists_explicitly_set(self):
        """Test that explicitly setting empty lists works."""
        col_type = ColumnByType(
            all_columns=[],
            string_columns=[],
            integer_columns=[],
            numeric_columns=[],
            datetime_columns=[],
            categorical_columns=[],
        )

        assert col_type.all_columns == []
        assert col_type.string_columns == []
        assert col_type.integer_columns == []
        assert col_type.numeric_columns == []
        assert col_type.datetime_columns == []
        assert col_type.categorical_columns == []


# ============================================================================
# GET_DF_COLUMNS TESTS
# ============================================================================


class TestGetDfColumnsPolars:
    """Test get_df_columns function with Polars DataFrames."""

    def test_polars_with_string_columns(self):
        """Test get_df_columns with Polars DataFrame containing string columns."""
        df = pl.DataFrame({"str_col": ["a", "b", "c"]})

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert "str_col" in result.all_columns
        assert "str_col" in result.string_columns
        assert "str_col" in result.categorical_columns
        assert len(result.integer_columns) == 0
        assert len(result.numeric_columns) == 0
        assert len(result.datetime_columns) == 0

    def test_polars_with_integer_columns(self):
        """Test get_df_columns with Polars DataFrame containing integer columns."""
        df = pl.DataFrame(
            {
                "int64_col": [1, 2, 3],
                "int32_col": pl.Series([4, 5, 6], dtype=pl.Int32),
                "int16_col": pl.Series([7, 8, 9], dtype=pl.Int16),
                "int8_col": pl.Series([1, 2, 3], dtype=pl.Int8),
            }
        )

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert "int64_col" in result.integer_columns
        assert "int32_col" in result.integer_columns
        assert "int16_col" in result.integer_columns
        assert "int8_col" in result.integer_columns
        assert len(result.integer_columns) == 4

        # Integer columns should also be in numeric columns
        assert "int64_col" in result.numeric_columns
        assert "int32_col" in result.numeric_columns

        # Integer columns should also be in categorical columns
        assert "int64_col" in result.categorical_columns

    def test_polars_with_numeric_columns(self):
        """Test get_df_columns with Polars DataFrame containing numeric columns."""
        df = pl.DataFrame(
            {
                "float_col": [1.1, 2.2, 3.3],
                "int_col": [1, 2, 3],
            }
        )

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert "float_col" in result.numeric_columns
        assert "int_col" in result.numeric_columns
        assert len(result.numeric_columns) == 2

    def test_polars_with_datetime_columns(self):
        """Test get_df_columns with Polars DataFrame containing datetime columns."""
        df = pl.DataFrame(
            {
                "datetime_col": [
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 2),
                    datetime(2024, 1, 3),
                ],
                "date_col": pl.Series(
                    [datetime(2024, 1, 1).date()], dtype=pl.Date
                ).extend_constant(None, 2),
            }
        )

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert "datetime_col" in result.datetime_columns
        assert "date_col" in result.datetime_columns
        assert len(result.datetime_columns) == 2

    def test_polars_with_categorical_columns(self):
        """Test get_df_columns with Polars DataFrame containing categorical columns."""
        df = pl.DataFrame(
            {
                "cat_col": pl.Series(["a", "b", "c"], dtype=pl.Categorical),
                "str_col": ["x", "y", "z"],
                "int_col": [1, 2, 3],
            }
        )

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert "cat_col" in result.categorical_columns
        assert "str_col" in result.categorical_columns
        assert "int_col" in result.categorical_columns

    def test_polars_with_mixed_types(self):
        """Test get_df_columns with Polars DataFrame containing mixed types."""
        df = pl.DataFrame(
            {
                "string_col": ["a", "b", None],
                "int_col": [1, 2, 3],
                "float_col": [1.1, 2.2, None],
                "datetime_col": [
                    datetime(2024, 1, 1),
                    None,
                    datetime(2024, 1, 3),
                ],
                "categorical_col": pl.Series(["cat1", "cat2", None], dtype=pl.Categorical),
            }
        )

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert len(result.all_columns) == 5
        assert "string_col" in result.string_columns
        assert "int_col" in result.integer_columns
        assert "int_col" in result.numeric_columns
        assert "float_col" in result.numeric_columns
        assert "datetime_col" in result.datetime_columns
        assert "categorical_col" in result.categorical_columns
        assert "string_col" in result.categorical_columns

    def test_polars_empty_dataframe(self):
        """Test get_df_columns with empty Polars DataFrame."""
        df = pl.DataFrame()

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert len(result.all_columns) == 0
        assert len(result.string_columns) == 0
        assert len(result.integer_columns) == 0
        assert len(result.numeric_columns) == 0
        assert len(result.datetime_columns) == 0
        assert len(result.categorical_columns) == 0

    def test_polars_single_column(self):
        """Test get_df_columns with single column Polars DataFrame."""
        df = pl.DataFrame({"single": [1, 2, 3]})

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert result.all_columns == ["single"]
        assert "single" in result.integer_columns
        assert "single" in result.numeric_columns


class TestGetDfColumnsPandas:
    """Test get_df_columns function with Pandas DataFrames."""

    def test_pandas_with_string_columns(self):
        """Test get_df_columns with Pandas DataFrame containing string columns."""
        df = pd.DataFrame({"str_col": ["a", "b", "c"]})

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert "str_col" in result.all_columns
        assert "str_col" in result.string_columns
        assert "str_col" in result.categorical_columns

    def test_pandas_with_integer_columns(self):
        """Test get_df_columns with Pandas DataFrame containing integer columns."""
        df = pd.DataFrame(
            {
                "int_col": [1, 2, 3],
                "int32_col": pd.Series([4, 5, 6], dtype="int32"),
            }
        )

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert "int_col" in result.integer_columns
        assert "int32_col" in result.integer_columns
        # Integers should also be in numeric
        assert "int_col" in result.numeric_columns
        # Integers should also be in categorical
        assert "int_col" in result.categorical_columns

    def test_pandas_with_numeric_columns(self):
        """Test get_df_columns with Pandas DataFrame containing numeric columns."""
        df = pd.DataFrame(
            {
                "float_col": [1.1, 2.2, 3.3],
                "int_col": [1, 2, 3],
            }
        )

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert "float_col" in result.numeric_columns
        assert "int_col" in result.numeric_columns

    def test_pandas_with_datetime_columns(self):
        """Test get_df_columns with Pandas DataFrame containing datetime columns."""
        df = pd.DataFrame(
            {
                "datetime_col": pd.to_datetime(
                    ["2024-01-01", "2024-01-02", "2024-01-03"]
                ),
            }
        )

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert "datetime_col" in result.datetime_columns

    def test_pandas_with_categorical_columns(self):
        """Test get_df_columns with Pandas DataFrame containing categorical columns."""
        df = pd.DataFrame(
            {
                "cat_col": pd.Categorical(["a", "b", "c"]),
                "str_col": ["x", "y", "z"],
                "int_col": [1, 2, 3],
            }
        )

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert "cat_col" in result.categorical_columns
        assert "str_col" in result.categorical_columns
        assert "int_col" in result.categorical_columns

    def test_pandas_with_mixed_types(self):
        """Test get_df_columns with Pandas DataFrame containing mixed types."""
        df = pd.DataFrame(
            {
                "string_col": ["a", "b", None],
                "int_col": [1, 2, 3],
                "float_col": [1.1, 2.2, None],
                "datetime_col": pd.to_datetime(["2024-01-01", None, "2024-01-03"]),
                "cat_col": pd.Categorical(["cat1", "cat2", None]),
            }
        )

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert len(result.all_columns) == 5
        assert "string_col" in result.string_columns
        assert "int_col" in result.integer_columns
        assert "float_col" in result.numeric_columns
        assert "datetime_col" in result.datetime_columns
        assert "cat_col" in result.categorical_columns

    def test_pandas_empty_dataframe(self):
        """Test get_df_columns with empty Pandas DataFrame."""
        df = pd.DataFrame()

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert len(result.all_columns) == 0

    def test_pandas_single_column(self):
        """Test get_df_columns with single column Pandas DataFrame."""
        df = pd.DataFrame({"single": [1, 2, 3]})

        result = get_df_columns(df)

        assert isinstance(result, ColumnByType)
        assert result.all_columns == ["single"]
        assert "single" in result.integer_columns


# ============================================================================
# STANDARDIZE_MISSING_VALUES TESTS
# ============================================================================


class TestStandardizeMissingValues:
    """Test standardize_missing_values function."""

    def test_pandas_to_polars_conversion(self):
        """Test that Pandas DataFrame is converted to Polars."""
        df = pd.DataFrame({"col1": ["a", "b", "c"]})

        result = standardize_missing_values(df)

        assert isinstance(result, pl.DataFrame)
        assert result.shape == (3, 1)

    def test_polars_remains_polars(self):
        """Test that Polars DataFrame remains Polars."""
        df = pl.DataFrame({"col1": ["a", "b", "c"]})

        result = standardize_missing_values(df)

        assert isinstance(result, pl.DataFrame)
        assert result.shape == (3, 1)

    def test_empty_string_becomes_null(self):
        """Test that empty strings are converted to null."""
        df = pl.DataFrame({"col1": ["a", "", "c"]})

        result = standardize_missing_values(df)

        assert result["col1"][1] is None

    def test_whitespace_strings_become_null(self):
        """Test that whitespace-only strings are converted to null."""
        df = pl.DataFrame({"col1": ["a", "   ", "\t", "\n", "b"]})

        result = standardize_missing_values(df)

        assert result["col1"][1] is None
        assert result["col1"][2] is None
        assert result["col1"][3] is None
        assert result["col1"][0] == "a"
        assert result["col1"][4] == "b"

    def test_null_variants_become_null(self):
        """Test that various null representations are converted to null."""
        df = pl.DataFrame(
            {"col1": ["NULL", "null", "Null", "None", "none", "NONE", "a"]}
        )

        result = standardize_missing_values(df)

        assert result["col1"][0] is None
        assert result["col1"][1] is None
        assert result["col1"][2] is None
        assert result["col1"][3] is None
        assert result["col1"][4] is None
        assert result["col1"][5] is None
        assert result["col1"][6] == "a"

    def test_na_variants_become_null(self):
        """Test that various N/A representations are converted to null."""
        df = pl.DataFrame({"col1": ["N/A", "n/a", "NA", "na", "#N/A", "N/a", "a"]})

        result = standardize_missing_values(df)

        assert result["col1"][0] is None
        assert result["col1"][1] is None
        assert result["col1"][2] is None
        assert result["col1"][3] is None
        assert result["col1"][4] is None
        assert result["col1"][5] is None
        assert result["col1"][6] == "a"

    def test_placeholder_symbols_become_null(self):
        """Test that placeholder symbols are converted to null."""
        df = pl.DataFrame({"col1": ["-", "--", ".", "?", "???", "a"]})

        result = standardize_missing_values(df)

        assert result["col1"][0] is None
        assert result["col1"][1] is None
        assert result["col1"][2] is None
        assert result["col1"][3] is None
        assert result["col1"][4] is None
        assert result["col1"][5] == "a"

    def test_missing_variants_become_null(self):
        """Test that 'missing' variants are converted to null."""
        df = pl.DataFrame({"col1": ["Missing", "missing", "MISSING", "a"]})

        result = standardize_missing_values(df)

        assert result["col1"][0] is None
        assert result["col1"][1] is None
        assert result["col1"][2] is None
        assert result["col1"][3] == "a"

    def test_unknown_variants_become_null(self):
        """Test that 'unknown' variants are converted to null."""
        df = pl.DataFrame({"col1": ["Unknown", "unknown", "UNKNOWN", "a"]})

        result = standardize_missing_values(df)

        assert result["col1"][0] is None
        assert result["col1"][1] is None
        assert result["col1"][2] is None
        assert result["col1"][3] == "a"

    def test_nan_variants_become_null(self):
        """Test that NaN variants are converted to null."""
        df = pl.DataFrame({"col1": ["NaN", "NAN", "nan", "NaT", "a"]})

        result = standardize_missing_values(df)

        assert result["col1"][0] is None
        assert result["col1"][1] is None
        assert result["col1"][2] is None
        assert result["col1"][3] is None
        assert result["col1"][4] == "a"

    def test_whitespace_trimming(self):
        """Test that leading/trailing whitespace is trimmed."""
        df = pl.DataFrame({"col1": ["  a  ", "  b", "c  ", "d"]})

        result = standardize_missing_values(df)

        assert result["col1"][0] == "a"
        assert result["col1"][1] == "b"
        assert result["col1"][2] == "c"
        assert result["col1"][3] == "d"

    def test_non_string_columns_unchanged(self):
        """Test that non-string columns are not affected by whitespace trimming."""
        df = pl.DataFrame(
            {
                "int_col": [1, 2, 3],
                "float_col": [1.1, 2.2, 3.3],
            }
        )

        result = standardize_missing_values(df)

        assert result["int_col"].to_list() == [1, 2, 3]
        assert result["float_col"].to_list() == [1.1, 2.2, 3.3]

    def test_multiple_columns(self):
        """Test standardization across multiple columns."""
        df = pl.DataFrame(
            {
                "col1": ["a", "NULL", "c"],
                "col2": ["", "b", "N/A"],
                "col3": [1, 2, 3],
            }
        )

        result = standardize_missing_values(df)

        assert result["col1"][0] == "a"
        assert result["col1"][1] is None
        assert result["col1"][2] == "c"

        assert result["col2"][0] is None
        assert result["col2"][1] == "b"
        assert result["col2"][2] is None

        assert result["col3"].to_list() == [1, 2, 3]

    def test_preserves_valid_strings(self):
        """Test that valid strings are not modified."""
        df = pl.DataFrame(
            {"col1": ["hello", "world", "test", "data"]}
        )

        result = standardize_missing_values(df)

        assert result["col1"].to_list() == ["hello", "world", "test", "data"]

    def test_pandas_input_conversion(self):
        """Test that Pandas DataFrame is converted and standardized."""
        df = pd.DataFrame(
            {
                "col1": ["a", "NULL", "c"],
                "col2": ["", "b", "N/A"],
            }
        )

        result = standardize_missing_values(df)

        assert isinstance(result, pl.DataFrame)
        assert result["col1"][1] is None
        assert result["col2"][0] is None
        assert result["col2"][2] is None

    def test_empty_dataframe(self):
        """Test standardization with empty DataFrame."""
        df = pl.DataFrame()

        result = standardize_missing_values(df)

        assert isinstance(result, pl.DataFrame)
        assert result.shape == (0, 0)

    def test_all_null_values(self):
        """Test DataFrame where all values become null."""
        df = pl.DataFrame(
            {"col1": ["NULL", "N/A", "", "   "], "col2": ["nan", "missing", "-", "?"]}
        )

        result = standardize_missing_values(df)

        assert all(val is None for val in result["col1"])
        assert all(val is None for val in result["col2"])

    @patch("builtins.print")
    def test_exception_handling_continues_processing(self, mock_print):
        """Test that exceptions in one column don't stop processing others."""
        df = pl.DataFrame(
            {
                "col1": ["a", "NULL", "c"],
                "col2": [1, 2, 3],
            }
        )

        # The function should handle any exceptions gracefully
        result = standardize_missing_values(df)

        assert isinstance(result, pl.DataFrame)
        # At minimum, the DataFrame should be returned
        assert result.shape[0] == 3

    def test_single_column_dataframe(self):
        """Test standardization with single column DataFrame."""
        df = pl.DataFrame({"col1": ["a", "NULL", "N/A", "b"]})

        result = standardize_missing_values(df)

        assert result["col1"][0] == "a"
        assert result["col1"][1] is None
        assert result["col1"][2] is None
        assert result["col1"][3] == "b"

    def test_mixed_valid_and_missing(self):
        """Test DataFrame with mixed valid and missing values."""
        df = pl.DataFrame(
            {
                "name": ["Alice", "NULL", "Bob", "N/A", "Charlie"],
                "age": ["25", "30", "unknown", "35", "40"],
                "city": ["NYC", "", "LA", "   ", "SF"],
            }
        )

        result = standardize_missing_values(df)

        assert result["name"][0] == "Alice"
        assert result["name"][1] is None
        assert result["name"][3] is None

        assert result["age"][0] == "25"
        assert result["age"][2] is None

        assert result["city"][1] is None
        assert result["city"][3] is None
