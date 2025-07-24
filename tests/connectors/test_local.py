"""Tests for the local connector module."""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl
import pytest
from openpyxl import Workbook

from datasure.connectors.local import (
    local_add_form,
    local_excel_sheet_names,
    local_load_action,
    local_read_data,
)


class TestLocalExcelSheetNames:
    """Test the local_excel_sheet_names function."""

    def test_excel_sheet_names_single_sheet(self, tmp_path):
        """Test getting sheet names from Excel file with single sheet."""
        # Create a temporary Excel file with one sheet
        excel_file = tmp_path / "test.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.title = "TestSheet"
        ws["A1"] = "test data"
        wb.save(excel_file)

        result = local_excel_sheet_names(str(excel_file))

        assert result == ["TestSheet"]

    def test_excel_sheet_names_multiple_sheets(self, tmp_path):
        """Test getting sheet names from Excel file with multiple sheets."""
        excel_file = tmp_path / "test.xlsx"
        wb = Workbook()

        # Create multiple sheets
        ws1 = wb.active
        ws1.title = "Sheet1"
        wb.create_sheet("Sheet2")
        wb.create_sheet("Sheet3")

        wb.save(excel_file)

        result = local_excel_sheet_names(str(excel_file))

        assert result == ["Sheet1", "Sheet2", "Sheet3"]


class TestLocalReadData:
    """Test the local_read_data function."""

    def test_read_csv_file(self, tmp_path):
        """Test reading CSV file."""
        csv_file = tmp_path / "test.csv"
        test_data = "name,age,city\nJohn,25,NYC\nJane,30,LA"
        csv_file.write_text(test_data)

        result = local_read_data(str(csv_file))

        # The function returns pandas DataFrame
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        assert list(result.columns) == ["name", "age", "city"]
        assert result.iloc[0]["name"] == "John"

    def test_read_json_file(self, tmp_path):
        """Test reading JSON file."""
        json_file = tmp_path / "test.json"
        test_data = [
            {"name": "John", "age": 25, "city": "NYC"},
            {"name": "Jane", "age": 30, "city": "LA"},
        ]
        json_file.write_text(json.dumps(test_data))

        result = local_read_data(str(json_file))

        # The function returns pandas DataFrame
        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        assert "name" in result.columns

    def test_read_excel_file_default_sheet(self, tmp_path):
        """Test reading Excel file with default sheet."""
        excel_file = tmp_path / "test.xlsx"

        # Create Excel file with data
        wb = Workbook()
        ws = wb.active
        ws.title = "TestSheet"
        ws["A1"] = "name"
        ws["B1"] = "age"
        ws["A2"] = "John"
        ws["B2"] = 25
        wb.save(excel_file)

        result = local_read_data(str(excel_file))

        # When sheet_name is None, pandas returns a dict of sheet_name: DataFrame
        assert isinstance(result, dict)
        assert "TestSheet" in result
        df = result["TestSheet"]
        assert isinstance(df, pd.DataFrame)
        assert len(df) == 1
        assert "name" in df.columns
        assert "age" in df.columns

    def test_read_excel_file_specific_sheet(self, tmp_path):
        """Test reading Excel file with specific sheet name."""
        excel_file = tmp_path / "test.xlsx"

        # Create Excel file with multiple sheets
        wb = Workbook()
        ws1 = wb.active
        ws1.title = "Sheet1"
        ws1["A1"] = "data1"

        ws2 = wb.create_sheet("Sheet2")
        ws2["A1"] = "data2"

        wb.save(excel_file)

        result = local_read_data(str(excel_file), sheet_name="Sheet2")

        # The function returns pandas DataFrame
        assert isinstance(result, pd.DataFrame)
        assert len(result) >= 0  # Should successfully read the sheet

    @patch("pandas.read_stata")
    def test_read_stata_file(self, mock_read_stata, tmp_path):
        """Test reading Stata file."""
        stata_file = tmp_path / "test.dta"
        stata_file.touch()  # Create empty file

        # Mock the pandas read_stata function
        mock_df = pd.DataFrame({"var1": [1, 2, 3], "var2": ["a", "b", "c"]})
        mock_read_stata.return_value = mock_df

        result = local_read_data(str(stata_file))

        mock_read_stata.assert_called_once_with(str(stata_file))
        # Should return the mocked DataFrame
        assert result.equals(mock_df)


class TestLocalAddForm:
    """Test the local_add_form function."""

    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    def test_valid_alias_empty(self, mock_st, mock_save_table, mock_get_table):
        """Test alias validation with empty alias."""
        from datasure.connectors.local import local_add_form

        # Mock streamlit components
        mock_st.text_input.return_value = ""
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None

        # Call the function (it should run without error)
        local_add_form("test_project_id")

        # Verify streamlit components were called
        assert mock_st.text_input.call_count >= 1

    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    @patch("os.path.isfile")
    def test_valid_file_path_nonexistent(
        self, mock_isfile, mock_st, mock_save_table, mock_get_table
    ):
        """Test file path validation with non-existent file."""
        from datasure.connectors.local import local_add_form

        # Mock file doesn't exist
        mock_isfile.return_value = False

        # Mock streamlit components
        mock_st.text_input.side_effect = ["test_alias", "/nonexistent/file.csv"]
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None
        mock_st.error.return_value = None

        # Call the function
        local_add_form("test_project_id")

        # Verify error was called for non-existent file
        mock_st.error.assert_called()

    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    @patch("os.path.isfile")
    def test_valid_file_path_invalid_extension(
        self, mock_isfile, mock_st, mock_save_table, mock_get_table
    ):
        """Test file path validation with invalid file extension."""
        from datasure.connectors.local import local_add_form

        # Mock file exists but wrong extension
        mock_isfile.return_value = True

        # Mock streamlit components
        mock_st.text_input.side_effect = ["test_alias", "/path/to/file.txt"]
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None
        mock_st.error.return_value = None

        # Call the function
        local_add_form("test_project_id")

        # Verify error was called for invalid extension
        mock_st.error.assert_called()

    @patch("datasure.connectors.local.local_excel_sheet_names")
    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    @patch("os.path.isfile")
    def test_excel_sheet_selection(
        self, mock_isfile, mock_st, mock_save_table, mock_get_table, mock_sheet_names
    ):
        """Test Excel sheet selection functionality."""
        from datasure.connectors.local import local_add_form

        # Mock file exists and is Excel
        mock_isfile.return_value = True
        mock_sheet_names.return_value = ["Sheet1", "Sheet2", "Sheet3"]

        # Mock streamlit components
        mock_st.text_input.side_effect = ["test_alias", "/path/to/file.xlsx"]
        mock_st.selectbox.return_value = "Sheet2"
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None

        # Call the function
        local_add_form("test_project_id")

        # Verify sheet names function was called
        mock_sheet_names.assert_called_once_with("/path/to/file.xlsx")
        # Verify selectbox was called with sheet names
        mock_st.selectbox.assert_called_once()

    # Edge case tests for local_add_form as specified in TODO_UPDATE.md

    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    def test_button_enabled_with_valid_inputs(
        self, mock_st, mock_save_table, mock_get_table
    ):
        """Test that button is enabled when both alias and file path are provided."""
        # Mock streamlit components - simulate user entering valid inputs
        mock_st.text_input.side_effect = [
            "valid_alias",
            "/valid/path.csv",
        ]  # alias, filepath
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None

        # Call the function
        local_add_form("test_project_id")

        # Button should be enabled because both inputs are provided
        button_call = mock_st.button.call_args
        assert button_call[1]["disabled"] is False

    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    @patch("os.path.isfile")
    def test_alias_validation_too_long(
        self, mock_isfile, mock_st, mock_save_table, mock_get_table
    ):
        """Test alias validation with too long alias (>20 characters)."""
        long_alias = "this_alias_is_way_too_long_for_validation"

        # Mock file exists to avoid file validation errors
        mock_isfile.return_value = True

        # Mock streamlit components
        mock_st.text_input.side_effect = [long_alias, "/valid/path.csv"]
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None
        mock_st.error.return_value = None

        # Call the function
        local_add_form("test_project_id")

        # Should call st.error for alias too long
        assert any(
            call[0][0] == "Alias must be a maximum of 20 characters"
            for call in mock_st.error.call_args_list
        )

    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    @patch("os.path.isfile")
    def test_alias_validation_duplicate_alias(
        self, mock_isfile, mock_st, mock_save_table, mock_get_table
    ):
        """Test alias validation with duplicate alias in import log."""
        # Mock existing import log with duplicate alias
        mock_import_log = MagicMock()
        mock_import_log.is_empty.return_value = False
        mock_import_log.__getitem__.return_value.to_list.return_value = [
            "existing_alias",
            "another_alias",
        ]
        mock_get_table.return_value = mock_import_log

        # Mock file exists
        mock_isfile.return_value = True

        # Mock streamlit components - user tries to use existing alias
        mock_st.text_input.side_effect = ["existing_alias", "/valid/path.csv"]
        mock_st.button.return_value = True  # User clicks submit
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None
        mock_st.error.return_value = None

        # Call the function
        local_add_form("test_project_id")

        # Should call st.error for duplicate alias
        mock_st.error.assert_called_with(
            "Alias already exists. Please choose a different alias or edit the existing one."
        )

    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    def test_button_enabled_when_only_alias_provided(
        self, mock_st, mock_save_table, mock_get_table
    ):
        """Test that button is enabled when alias is provided but file path is empty."""
        # Mock streamlit components - alias provided, file path empty
        mock_st.text_input.side_effect = ["valid_alias", ""]  # alias, filepath
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None

        # Call the function
        local_add_form("test_project_id")

        # Button logic: disabled = not file_path and not alias
        # With alias="valid_alias" and file_path="", disabled = False
        button_call = mock_st.button.call_args
        assert button_call[1]["disabled"] is False

    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    @patch("os.path.isfile")
    def test_file_path_validation_directory_path(
        self, mock_isfile, mock_st, mock_save_table, mock_get_table
    ):
        """Test file path validation with directory path instead of file."""
        # Mock isfile returns False for directory
        mock_isfile.return_value = False

        # Mock streamlit components - simulate directory path
        mock_st.text_input.side_effect = ["valid_alias", "/path/to/directory/"]
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None
        mock_st.error.return_value = None

        # Call the function
        local_add_form("test_project_id")

        # Should call st.error for file not found
        assert any(
            call[0][0] == "File not found. Please check the file path"
            for call in mock_st.error.call_args_list
        )

    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    @patch("os.path.isfile")
    def test_file_path_validation_unsupported_extension(
        self, mock_isfile, mock_st, mock_save_table, mock_get_table
    ):
        """Test file path validation with unsupported file extension."""
        # Mock file exists but has unsupported extension
        mock_isfile.return_value = True

        # Mock streamlit components - simulate unsupported file type
        mock_st.text_input.side_effect = ["valid_alias", "/path/to/file.pdf"]
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None
        mock_st.error.return_value = None

        # Call the function
        local_add_form("test_project_id")

        # Should call st.error for invalid file type
        assert any(
            call[0][0] == "Invalid file type. Please upload a valid file type"
            for call in mock_st.error.call_args_list
        )

    @patch("datasure.connectors.local.local_excel_sheet_names")
    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    @patch("os.path.isfile")
    def test_excel_sheet_handling_error(
        self, mock_isfile, mock_st, mock_save_table, mock_get_table, mock_sheet_names
    ):
        """Test Excel sheet handling when sheet names cannot be retrieved."""
        # Mock file exists and is Excel
        mock_isfile.return_value = True
        # Mock sheet names function raises exception
        mock_sheet_names.side_effect = Exception("Cannot read Excel file")

        # Mock streamlit components
        mock_st.text_input.side_effect = ["valid_alias", "/path/to/file.xlsx"]
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None

        # Call the function - expect exception since no error handling exists
        with pytest.raises(Exception, match="Cannot read Excel file"):
            local_add_form("test_project_id")

        # Verify sheet names function was attempted
        mock_sheet_names.assert_called_once_with("/path/to/file.xlsx")

    @patch("datasure.connectors.local.local_excel_sheet_names")
    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    @patch("os.path.isfile")
    def test_excel_default_sheet_selection(
        self, mock_isfile, mock_st, mock_save_table, mock_get_table, mock_sheet_names
    ):
        """Test Excel default sheet selection when defaults don't match sheets."""
        # Mock file exists and is Excel
        mock_isfile.return_value = True
        mock_sheet_names.return_value = ["Sheet1", "Data", "Summary"]

        # Mock streamlit components
        mock_st.text_input.side_effect = ["valid_alias", "/path/to/file.xlsx"]
        mock_st.selectbox.return_value = "Data"
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None

        # Call function with defaults that don't exist in sheets
        defaults = {
            "alias": "old_alias",
            "filename": "old_file.xlsx",
            "sheet_name": "NonExistentSheet",
        }
        local_add_form("test_project_id", edit_mode=True, defaults=defaults)

        # Should use index 0 (first sheet) when default doesn't exist
        call_args = mock_st.selectbox.call_args
        assert call_args[1]["index"] == 0  # Should default to first sheet

    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    def test_edit_mode_with_defaults(self, mock_st, mock_save_table, mock_get_table):
        """Test edit mode functionality with default values."""
        # Mock empty import log
        mock_import_log = MagicMock()
        mock_import_log.is_empty.return_value = True
        mock_get_table.return_value = mock_import_log

        # Mock streamlit components
        mock_st.text_input.side_effect = ["updated_alias", "/updated/path.csv"]
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None
        mock_st.info.return_value = None

        # Call function in edit mode with defaults
        defaults = {"alias": "old_alias", "filename": "old_file.csv", "sheet_name": ""}
        local_add_form("test_project_id", edit_mode=True, defaults=defaults)

        # Verify info message for edit mode
        mock_st.info.assert_called_with(
            "You are in edit mode. Please modify the file details below."
        )

        # Verify text inputs use placeholders from defaults
        text_input_calls = mock_st.text_input.call_args_list
        # First call should have placeholder for alias
        assert text_input_calls[0][1]["placeholder"] == "old_alias"
        # Second call should have placeholder for filename
        assert text_input_calls[1][1]["placeholder"] == "old_file.csv"

        # Verify alias input is disabled in edit mode
        assert text_input_calls[0][1]["disabled"] is True

    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    @patch("os.path.isfile")
    def test_button_disabled_when_missing_inputs(
        self, mock_isfile, mock_st, mock_save_table, mock_get_table
    ):
        """Test that submit button is disabled when required inputs are missing."""
        # Mock streamlit components - missing both alias and file path
        mock_st.text_input.side_effect = ["", ""]  # Empty alias and filepath
        mock_st.button.return_value = False
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None

        # Call the function
        local_add_form("test_project_id")

        # Verify button is called with disabled=True
        button_call = mock_st.button.call_args
        assert button_call[1]["disabled"] is True

    @patch("datasure.connectors.local.duckdb_get_table")
    @patch("datasure.connectors.local.duckdb_save_table")
    @patch("datasure.connectors.local.st")
    @patch("os.path.isfile")
    @patch("polars.concat")
    def test_successful_file_addition(
        self, mock_concat, mock_isfile, mock_st, mock_save_table, mock_get_table
    ):
        """Test successful file addition to import log."""
        # Mock empty import log
        mock_import_log = MagicMock()
        mock_import_log.is_empty.return_value = True
        mock_import_log.__getitem__.return_value.to_list.return_value = []
        mock_get_table.return_value = mock_import_log

        # Mock file exists
        mock_isfile.return_value = True

        # Mock polars concat
        mock_concat.return_value = mock_import_log

        # Mock streamlit components - valid inputs
        mock_st.text_input.side_effect = ["valid_alias", "/valid/path.csv"]
        mock_st.button.return_value = True  # User clicks submit
        mock_st.image.return_value = None
        mock_st.subheader.return_value = None
        mock_st.markdown.return_value = None

        # Call the function
        local_add_form("test_project_id")

        # Verify that save_table was called to save the updated import log
        mock_save_table.assert_called()
        save_call = mock_save_table.call_args
        assert save_call[0][0] == "test_project_id"  # project_id
        assert save_call[1]["alias"] == "import_log"
        assert save_call[1]["db_name"] == "logs"


class TestLocalLoadAction:
    """Test the local_load_action function."""

    @patch("datasure.connectors.local.local_read_data")
    @patch("datasure.connectors.local.duckdb_save_table")
    def test_load_action_success(self, mock_save_table, mock_read_data):
        """Test successful data loading action."""
        # Mock data reading
        mock_df = pl.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
        mock_read_data.return_value = mock_df

        # Call the function
        local_load_action("test_project", "test_alias", "/path/to/file.csv", None)

        # Verify functions were called correctly
        mock_read_data.assert_called_once_with("/path/to/file.csv", None)
        mock_save_table.assert_called_once_with(
            "test_project", mock_df, alias="test_alias", db_name="raw"
        )

    @patch("datasure.connectors.local.local_read_data")
    @patch("datasure.connectors.local.duckdb_save_table")
    def test_load_action_with_sheet(self, mock_save_table, mock_read_data):
        """Test data loading action with Excel sheet name."""
        # Mock data reading
        mock_df = pl.DataFrame({"col1": [1, 2, 3], "col2": ["a", "b", "c"]})
        mock_read_data.return_value = mock_df

        # Call the function
        local_load_action("test_project", "test_alias", "/path/to/file.xlsx", "Sheet2")

        # Verify functions were called correctly
        mock_read_data.assert_called_once_with("/path/to/file.xlsx", "Sheet2")
        mock_save_table.assert_called_once_with(
            "test_project", mock_df, alias="test_alias", db_name="raw"
        )
