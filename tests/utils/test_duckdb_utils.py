"""Tests for the DuckDB utilities module."""

from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl

from datasure.utils.duckdb_utils import (
    _validate_table_name,
    duckdb_get_aliases,
    duckdb_get_imported_datasets,
    duckdb_get_table,
    duckdb_row_filter,
    duckdb_save_table,
)


class TestValidateTableName:
    """Test the _validate_table_name function."""

    def test_valid_table_name(self):
        """Test with a valid table name."""
        result = _validate_table_name("valid_table_name")
        assert result == "valid_table_name"

    def test_table_name_with_spaces(self):
        """Test table name with spaces gets sanitized."""
        result = _validate_table_name("table with spaces")
        assert result == "table_with_spaces"

    def test_table_name_with_special_chars(self):
        """Test table name with special characters gets sanitized."""
        result = _validate_table_name("table-name.with@special#chars!")
        assert result == "table_name_with_special_chars_"

    def test_table_name_starts_with_number(self):
        """Test table name starting with number gets prefixed."""
        result = _validate_table_name("123_table")
        assert result == "table_123_table"

    def test_table_name_sql_keyword(self):
        """Test table name that's a SQL keyword gets suffixed."""
        result = _validate_table_name("select")
        assert result == "select_table"

    def test_table_name_uppercase_keyword(self):
        """Test uppercase SQL keyword gets handled."""
        result = _validate_table_name("SELECT")
        assert result == "SELECT_table"

    def test_table_name_mixed_case_keyword(self):
        """Test mixed case SQL keyword gets handled."""
        result = _validate_table_name("Select")
        assert result == "Select_table"

    def test_empty_table_name(self):
        """Test empty table name gets prefixed."""
        result = _validate_table_name("")
        assert result == "table_"

    def test_table_name_starting_with_underscore(self):
        """Test table name starting with underscore is valid."""
        result = _validate_table_name("_valid_name")
        assert result == "_valid_name"


class TestDuckdbSaveTable:
    """Test the duckdb_save_table function."""

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    def test_save_table_logs_database(
        self, mock_connect, mock_get_cache_path, tmp_path
    ):
        """Test saving table to logs database."""
        db_path = tmp_path / "logs.duckdb"
        mock_get_cache_path.return_value = db_path

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        # Mock table doesn't exist initially
        mock_conn.execute.return_value.fetchone.return_value = [0]

        test_df = pl.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})

        duckdb_save_table("test_project", test_df, "test_alias", "logs")

        mock_get_cache_path.assert_called_with(
            "test_project", "settings", "logs.duckdb"
        )
        mock_connect.assert_called_with(db_path)
        # Should call CREATE TABLE since table doesn't exist
        assert any(
            "CREATE TABLE" in str(call) for call in mock_conn.execute.call_args_list
        )

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    def test_save_table_data_database(
        self, mock_connect, mock_get_cache_path, tmp_path
    ):
        """Test saving table to data database."""
        db_path = tmp_path / "raw.duckdb"
        mock_get_cache_path.return_value = db_path

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        # Mock table exists
        mock_conn.execute.return_value.fetchone.return_value = [1]

        test_df = pd.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})

        duckdb_save_table("test_project", test_df, "test_alias", "raw")

        mock_get_cache_path.assert_called_with("test_project", "data", "raw.duckdb")
        mock_connect.assert_called_with(db_path)
        # Should call CREATE OR REPLACE TABLE since table exists
        assert any(
            "CREATE OR REPLACE TABLE" in str(call)
            for call in mock_conn.execute.call_args_list
        )

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    def test_save_table_with_special_alias(
        self, mock_connect, mock_get_cache_path, tmp_path
    ):
        """Test saving table with alias that needs sanitization."""
        db_path = tmp_path / "test.duckdb"
        mock_get_cache_path.return_value = db_path

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = [0]

        test_df = pl.DataFrame({"col1": [1, 2, 3]})

        duckdb_save_table("test_project", test_df, "Test-Alias With Spaces!", "data")

        # Verify the table name was sanitized
        calls = [str(call) for call in mock_conn.execute.call_args_list]
        sanitized_calls = [call for call in calls if "test_alias_with_spaces_" in call]
        assert len(sanitized_calls) > 0


class TestDuckdbGetTable:
    """Test the duckdb_get_table function."""

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    def test_get_table_exists(self, mock_connect, mock_get_cache_path, tmp_path):
        """Test getting table that exists."""
        db_path = tmp_path / "logs.duckdb"
        mock_get_cache_path.return_value = db_path

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        # Mock table exists
        mock_conn.execute.return_value.fetchone.return_value = [1]

        # Mock the table data
        expected_df = pl.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
        mock_conn.execute.return_value.pl.return_value = expected_df

        duckdb_get_table("test_project", "test_alias", "logs")

        mock_get_cache_path.assert_called_with(
            "test_project", "settings", "logs.duckdb"
        )
        mock_connect.assert_called_with(db_path)

        # Verify the SELECT query was called
        select_calls = [
            call
            for call in mock_conn.execute.call_args_list
            if "SELECT * FROM" in str(call)
        ]
        assert len(select_calls) > 0

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    def test_get_table_not_exists(self, mock_connect, mock_get_cache_path, tmp_path):
        """Test getting table that doesn't exist."""
        db_path = tmp_path / "data.duckdb"
        mock_get_cache_path.return_value = db_path

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        # Mock table doesn't exist
        mock_conn.execute.return_value.fetchone.return_value = [0]

        result = duckdb_get_table("test_project", "nonexistent_alias", "data")

        # Should return empty DataFrame
        assert isinstance(result, pl.DataFrame)
        assert result.is_empty()

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    def test_get_table_data_database(self, mock_connect, mock_get_cache_path, tmp_path):
        """Test getting table from data database (not logs)."""
        db_path = tmp_path / "raw.duckdb"
        mock_get_cache_path.return_value = db_path

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = [1]

        expected_df = pl.DataFrame({"col1": [1, 2, 3]})
        mock_conn.execute.return_value.pl.return_value = expected_df

        duckdb_get_table("test_project", "test_alias", "raw")

        mock_get_cache_path.assert_called_with("test_project", "data", "raw.duckdb")


class TestDuckdbRowFilter:
    """Test the duckdb_row_filter function."""

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    def test_row_filter_basic(self, mock_connect, mock_get_cache_path, tmp_path):
        """Test basic row filtering functionality."""
        db_path = tmp_path / "data.duckdb"
        mock_get_cache_path.return_value = db_path

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        # Mock filtered result
        expected_df = pl.DataFrame({"col1": [1, 3], "col2": ["a", "c"]})
        mock_conn.execute.return_value.pl.return_value = expected_df

        duckdb_row_filter("test_project", "test_alias", "data", "col1 > 0")

        # Verify the SELECT query with WHERE clause was called
        select_calls = [str(call) for call in mock_conn.execute.call_args_list]
        where_calls = [
            call for call in select_calls if "WHERE" in call and "col1 > 0" in call
        ]
        assert len(where_calls) > 0

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    def test_row_filter_complex_condition(
        self, mock_connect, mock_get_cache_path, tmp_path
    ):
        """Test row filtering with complex condition."""
        db_path = tmp_path / "data.duckdb"
        mock_get_cache_path.return_value = db_path

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        expected_df = pl.DataFrame({"name": ["Alice"], "age": [25]})
        mock_conn.execute.return_value.pl.return_value = expected_df

        complex_filter = "age >= 18 AND name LIKE 'A%'"
        duckdb_row_filter("test_project", "people", "data", complex_filter)

        # Verify the complex filter was used
        select_calls = [str(call) for call in mock_conn.execute.call_args_list]
        complex_calls = [call for call in select_calls if complex_filter in call]
        assert len(complex_calls) > 0


class TestDuckdbGetAliases:
    """Test the duckdb_get_aliases function."""

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    def test_get_aliases_with_data(self, mock_connect, mock_get_cache_path, tmp_path):
        """Test getting aliases when import_log has data."""
        db_path = tmp_path / "logs.duckdb"
        mock_get_cache_path.return_value = db_path

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        # Mock the fetchall result for to_load=True
        mock_conn.execute.return_value.fetchall.return_value = [
            ("dataset1",),
            ("dataset3",),
        ]

        result = duckdb_get_aliases("test_project", to_load=True)

        # Should return only aliases where load=True
        expected = ["dataset1", "dataset3"]
        assert result == expected

        # Verify the query was called
        query_calls = [str(call) for call in mock_conn.execute.call_args_list]
        load_query_calls = [call for call in query_calls if "WHERE load = TRUE" in call]
        assert len(load_query_calls) > 0

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    def test_get_aliases_all(self, mock_connect, mock_get_cache_path, tmp_path):
        """Test getting all aliases regardless of load status."""
        db_path = tmp_path / "logs.duckdb"
        mock_get_cache_path.return_value = db_path

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        # Mock the fetchall result for to_load=False
        mock_conn.execute.return_value.fetchall.return_value = [
            ("dataset1",),
            ("dataset2",),
            ("dataset3",),
        ]

        result = duckdb_get_aliases("test_project", to_load=False)

        # Should return all aliases
        expected = ["dataset1", "dataset2", "dataset3"]
        assert result == expected

        # Verify the query was called without WHERE clause for load
        query_calls = [str(call) for call in mock_conn.execute.call_args_list]
        all_query_calls = [
            call
            for call in query_calls
            if "SELECT DISTINCT alias FROM import_log" in call
            and "WHERE load" not in call
        ]
        assert len(all_query_calls) > 0

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    def test_get_aliases_empty_log(self, mock_connect, mock_get_cache_path, tmp_path):
        """Test getting aliases when import_log is empty."""
        db_path = tmp_path / "logs.duckdb"
        mock_get_cache_path.return_value = db_path

        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn

        # Mock empty result
        mock_conn.execute.return_value.fetchall.return_value = []

        result = duckdb_get_aliases("test_project")

        assert result == []


class TestDuckdbGetImportedDatasets:
    """Test the duckdb_get_imported_datasets function."""

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    @patch("datasure.utils.duckdb_utils.duckdb_get_aliases")
    def test_get_imported_datasets_with_data(
        self, mock_get_aliases, mock_connect, mock_get_cache_path, tmp_path
    ):
        """Test getting imported datasets when import_log has data."""
        # Mock path
        db_path = tmp_path / "raw.duckdb"
        mock_get_cache_path.return_value = db_path

        # Mock database connection - return tables that exist in DB
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = [
            ("dataset1",),
            ("dataset3",),
        ]

        # Mock aliases that are loaded (from import log)
        mock_get_aliases.return_value = ["dataset1", "dataset2", "dataset3"]

        result = duckdb_get_imported_datasets("test_project")

        # Should return aliases that exist in both import log and database
        expected = ["dataset1", "dataset3"]
        assert result == expected
        mock_get_aliases.assert_called_once_with("test_project", to_load=True)

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    @patch("datasure.utils.duckdb_utils.duckdb_get_aliases")
    def test_get_imported_datasets_empty_log(
        self, mock_get_aliases, mock_connect, mock_get_cache_path, tmp_path
    ):
        """Test getting imported datasets when import_log is empty."""
        # Mock path
        db_path = tmp_path / "raw.duckdb"
        mock_get_cache_path.return_value = db_path

        # Mock database connection
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []

        mock_get_aliases.return_value = []

        result = duckdb_get_imported_datasets("test_project")

        assert result == []

    @patch("datasure.utils.duckdb_utils.get_cache_path")
    @patch("duckdb.connect")
    @patch("datasure.utils.duckdb_utils.duckdb_get_aliases")
    def test_get_imported_datasets_no_tables_in_db(
        self, mock_get_aliases, mock_connect, mock_get_cache_path, tmp_path
    ):
        """Test getting imported datasets when no tables exist in database."""
        # Mock path
        db_path = tmp_path / "raw.duckdb"
        mock_get_cache_path.return_value = db_path

        # Mock database connection - no tables in DB
        mock_conn = MagicMock()
        mock_connect.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchall.return_value = []

        # But aliases exist in import log
        mock_get_aliases.return_value = ["dataset1", "dataset2"]

        result = duckdb_get_imported_datasets("test_project")

        # Should return empty list since no tables exist in DB
        assert result == []


class TestIntegration:
    """Integration tests for DuckDB utilities."""

    def test_save_and_get_table_integration(self, tmp_path):
        """Test the full workflow of saving and retrieving a table."""
        # Create a temporary database
        project_id = "test_project"

        with patch("datasure.utils.duckdb_utils.get_cache_path") as mock_path:
            db_file = tmp_path / "test.duckdb"
            mock_path.return_value = db_file

            # Create test data
            test_df = pl.DataFrame(
                {
                    "id": [1, 2, 3],
                    "name": ["Alice", "Bob", "Charlie"],
                    "score": [85.5, 92.0, 78.5],
                }
            )

            # Save the table
            duckdb_save_table(project_id, test_df, "test_data", "raw")

            # Retrieve the table
            retrieved_df = duckdb_get_table(project_id, "test_data", "raw")

            # Compare the data
            assert retrieved_df.shape == test_df.shape
            assert list(retrieved_df.columns) == list(test_df.columns)

            # Compare values (convert to pandas for easier comparison)
            test_pd = test_df.to_pandas().sort_values("id").reset_index(drop=True)
            retrieved_pd = (
                retrieved_df.to_pandas().sort_values("id").reset_index(drop=True)
            )
            pd.testing.assert_frame_equal(test_pd, retrieved_pd)
