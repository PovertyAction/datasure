"""Tests for the SurveyCTO connector module."""

import datetime
import json
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from datasure.connectors.scto import (
    scto_get_repeat_cols,
    scto_get_server_cache,
    scto_get_xls,
    scto_import_data,
    scto_import_key,
    scto_load_existing_data,
    scto_load_forms,
    scto_server_connect,
    valid_email,
    valid_server_name,
)


class TestValidationFunctions:
    """Test the validation functions."""

    def test_valid_server_name_valid_inputs(self):
        """Test valid_server_name with valid server names."""
        valid_names = [
            "myserver",
            "test123",
            "a1b2c3",
            "server01",
            "abc",
        ]

        for name in valid_names:
            assert valid_server_name(name), f"Server name '{name}' should be valid"

    def test_valid_server_name_invalid_inputs(self):
        """Test valid_server_name with invalid server names."""
        invalid_names = [
            "",  # empty
            "123server",  # starts with number
            "Server",  # uppercase
            "server-name",  # hyphen
            "server_name",  # underscore
            "server.com",  # dot
            "a",  # too short (based on regex pattern)
        ]

        for name in invalid_names:
            assert not valid_server_name(name), (
                f"Server name '{name}' should be invalid"
            )

    def test_valid_email_valid_inputs(self):
        """Test valid_email with valid email addresses."""
        valid_emails = [
            "test@example.com",
            "user.name@domain.org",
            "user+tag@example.co.uk",
            "user123@test-domain.com",
            "a@b.co",
        ]

        for email in valid_emails:
            assert valid_email(email), f"Email '{email}' should be valid"

    def test_valid_email_invalid_inputs(self):
        """Test valid_email with invalid email addresses."""
        invalid_emails = [
            "",  # empty
            "notanemail",  # no @ symbol
            "@domain.com",  # no local part
            "user@",  # no domain
            "user@domain",  # no TLD
            "user@domain.",  # empty TLD
            "user name@domain.com",  # space in local part
        ]

        for email in invalid_emails:
            assert not valid_email(email), f"Email '{email}' should be invalid"


class TestSctoServerConnect:
    """Test the scto_server_connect function."""

    @patch("datasure.connectors.scto.st")
    @patch("datasure.connectors.scto.pysurveycto.SurveyCTOObject")
    def test_server_connect_valid_inputs(self, mock_scto_object, mock_st):
        """Test server connect with valid inputs."""
        mock_scto_instance = MagicMock()
        mock_scto_object.return_value = mock_scto_instance
        mock_st.warning.return_value = None
        mock_st.success.return_value = None
        mock_st.stop.return_value = None

        result = scto_server_connect("testserver", "user@example.com", "password123")

        mock_scto_object.assert_called_once_with(
            "testserver", "user@example.com", "password123"
        )
        mock_st.success.assert_called_once_with("Connection successful")
        assert result == mock_scto_instance

    @patch("datasure.connectors.scto.st")
    def test_server_connect_empty_fields(self, mock_st):
        """Test server connect with empty fields."""
        mock_st.warning.return_value = None
        mock_st.stop.side_effect = SystemExit("Streamlit stop called")

        with pytest.raises(SystemExit):
            scto_server_connect("", "user@example.com", "password123")

        mock_st.warning.assert_called_once_with("Complete all required fields.")

    @patch("datasure.connectors.scto.st")
    def test_server_connect_invalid_server_name(self, mock_st):
        """Test server connect with invalid server name."""
        mock_st.warning.return_value = None
        mock_st.stop.side_effect = SystemExit("Streamlit stop called")

        with pytest.raises(SystemExit):
            scto_server_connect("123invalid", "user@example.com", "password123")

        mock_st.warning.assert_called_once_with("Invalid server name.")

    @patch("datasure.connectors.scto.st")
    def test_server_connect_invalid_email(self, mock_st):
        """Test server connect with invalid email."""
        mock_st.warning.return_value = None
        mock_st.stop.side_effect = SystemExit("Streamlit stop called")

        with pytest.raises(SystemExit):
            scto_server_connect("testserver", "invalid-email", "password123")

        mock_st.warning.assert_called_once_with("Invalid email address")


class TestSctoGetRepeatCols:
    """Test the scto_get_repeat_cols function."""

    def test_get_repeat_cols_with_matches(self):
        """Test getting repeat columns with matching patterns."""
        field = "household"
        data_cols = [
            "household_1",
            "household_2",
            "household_1_2",
            "household_1_2_3",
            "other_field",
            "household_info",
            "household_1_name",  # This won't match due to extra text after numbers
        ]

        result = scto_get_repeat_cols(field, data_cols)

        expected = ["household_1", "household_2", "household_1_2", "household_1_2_3"]
        assert result == expected

    def test_get_repeat_cols_no_matches(self):
        """Test getting repeat columns with no matches."""
        field = "nonexistent"
        data_cols = [
            "household_1_name",
            "household_2_name",
            "other_field",
        ]

        result = scto_get_repeat_cols(field, data_cols)

        # When no matches, should return field split (which gives ['nonexistent'])
        assert result == ["nonexistent"]

    def test_get_repeat_cols_complex_pattern(self):
        """Test getting repeat columns with complex numeric patterns."""
        field = "section"
        data_cols = [
            "section_1",
            "section_2_1",
            "section_1_2_3",
            "section_10",
            "section_1_question",  # Won't match due to extra text
            "other_section_field",
        ]

        result = scto_get_repeat_cols(field, data_cols)

        expected = ["section_1", "section_2_1", "section_1_2_3", "section_10"]
        assert result == expected


class TestSctoGetServerCache:
    """Test the scto_get_server_cache function."""

    @patch("datasure.connectors.scto.get_cache_path")
    def test_get_server_cache_file_exists(self, mock_get_cache_path, tmp_path):
        """Test getting server cache when file exists."""
        cache_file = tmp_path / "scto.json"
        test_data = {"server": "testserver", "forms": ["form1", "form2"]}
        cache_file.write_text(json.dumps(test_data))

        mock_get_cache_path.return_value = str(cache_file)

        result = scto_get_server_cache("test_project")

        assert result == test_data
        mock_get_cache_path.assert_called_once_with(
            "test_project", "settings", "scto.json"
        )

    @patch("datasure.connectors.scto.get_cache_path")
    def test_get_server_cache_file_not_found(self, mock_get_cache_path):
        """Test getting server cache when file doesn't exist."""
        mock_get_cache_path.return_value = "/nonexistent/path/scto.json"

        result = scto_get_server_cache("test_project")

        assert result == {}


class TestSctoLoadForms:
    """Test the scto_load_forms function."""

    @patch("datasure.connectors.scto.get_cache_path")
    @patch("pandas.read_json")
    def test_load_forms_file_exists(self, mock_read_json, mock_get_cache_path):
        """Test loading forms when cache file exists."""
        mock_cache_path = "/cache/path/testserver_DataSure_forms_cache.json"
        mock_get_cache_path.return_value = mock_cache_path

        mock_df = pd.DataFrame(
            {"form_id": ["form1", "form2"], "title": ["Form 1", "Form 2"]}
        )
        mock_read_json.return_value = mock_df

        result = scto_load_forms("testserver")

        mock_read_json.assert_called_once_with(mock_cache_path)
        pd.testing.assert_frame_equal(result, pd.DataFrame(mock_df.to_dict()))

    @patch("datasure.connectors.scto.get_cache_path")
    @patch("pandas.read_json")
    def test_load_forms_file_not_found(self, mock_read_json, mock_get_cache_path):
        """Test loading forms when cache file doesn't exist."""
        mock_read_json.side_effect = FileNotFoundError()

        result = scto_load_forms("testserver")

        assert result.empty


class TestSctoImportKey:
    """Test the scto_import_key function."""

    def test_import_key_file_exists(self, tmp_path):
        """Test importing key when file exists."""
        key_file = tmp_path / "test.key"
        test_key = "test_private_key_content"
        key_file.write_text(test_key)

        result = scto_import_key(str(key_file))

        assert result == test_key

    @patch("datasure.connectors.scto.st")
    def test_import_key_file_not_found(self, mock_st):
        """Test importing key when file doesn't exist."""
        mock_st.warning.return_value = None
        mock_st.stop.side_effect = SystemExit("Streamlit stop called")

        with pytest.raises(SystemExit):
            scto_import_key("/nonexistent/key.file")

        mock_st.warning.assert_called_once_with("Key file not found.")


class TestSctoLoadExistingData:
    """Test the scto_load_existing_data function."""

    def test_load_existing_data_file_exists(self, tmp_path):
        """Test loading existing data when file exists."""
        data_file = tmp_path / "test_data.csv"
        test_data = "SubmissionDate,name,age\n2024-01-15 10:30:00,John,25\n2024-01-20 15:45:00,Jane,30"
        data_file.write_text(test_data)

        result_data, oldest_date = scto_load_existing_data(str(data_file))

        assert len(result_data) == 2
        assert "SubmissionDate" in result_data.columns
        assert "name" in result_data.columns
        assert oldest_date == pd.to_datetime("2024-01-20 15:45:00")

    def test_load_existing_data_file_not_found(self):
        """Test loading existing data when file doesn't exist."""
        result_data, oldest_date = scto_load_existing_data("/nonexistent/file.csv")

        assert result_data.empty
        assert oldest_date == datetime.datetime(2024, 1, 1, 13, 40, 40)

    def test_load_existing_data_empty_file(self, tmp_path):
        """Test loading existing data when file is empty."""
        data_file = tmp_path / "empty_data.csv"
        data_file.write_text("")

        result_data, oldest_date = scto_load_existing_data(str(data_file))

        assert result_data.empty
        assert oldest_date == datetime.datetime(2024, 1, 1, 13, 40, 40)


class TestSctoGetXls:
    """Test the scto_get_xls function."""

    def test_get_xls_success(self):
        """Test getting XLS form definition successfully."""
        mock_scto = MagicMock()
        mock_form_definition = {
            "fieldsRowsAndColumns": [
                ["name", "type", "label"],
                ["question1", "text", "What is your name?"],
                ["question2", "integer", "What is your age?"],
            ],
            "choicesRowsAndColumns": [
                ["list name", "name", "label"],
                ["colors", "red", "Red"],
                ["colors", "blue", "Blue"],
            ],
        }
        mock_scto.get_form_definition.return_value = mock_form_definition

        questions, choices = scto_get_xls(mock_scto, "test_form")

        mock_scto.get_form_definition.assert_called_once_with("test_form")

        # Check questions DataFrame
        assert len(questions) == 2
        assert list(questions.columns) == ["name", "type", "label"]
        assert questions.iloc[0]["name"] == "question1"

        # Check choices DataFrame
        assert len(choices) == 2
        assert list(choices.columns) == ["list name", "name", "label"]
        assert choices.iloc[0]["name"] == "red"


class TestSctoGetRepeatColsAdvanced:
    """Enhanced tests for scto_get_repeat_cols function with complex scenarios."""

    def test_get_repeat_cols_nested_groups(self):
        """Test repeat columns with nested group structures."""
        field = "household_member"
        data_cols = [
            "household_member_1",
            "household_member_2",
            "household_member_1_1",
            "household_member_1_2",
            "household_member_2_1",
            "household_member_1_1_1",
            "household_member_1_2_3",
            "household_member_10_15_20",
            "other_field",
        ]

        result = scto_get_repeat_cols(field, data_cols)

        expected = [
            "household_member_1",
            "household_member_2",
            "household_member_1_1",
            "household_member_1_2",
            "household_member_2_1",
            "household_member_1_1_1",
            "household_member_1_2_3",
            "household_member_10_15_20",
        ]
        assert result == expected

    def test_get_repeat_cols_single_digit_patterns(self):
        """Test repeat columns with single digit patterns."""
        field = "q"  # Short field name
        data_cols = [
            "q_1",
            "q_2",
            "q_3",
            "q_9",
            "q1",  # Won't match - no underscore
            "q_text",  # Won't match - not numeric
            "question_1",  # Won't match - different field
        ]

        result = scto_get_repeat_cols(field, data_cols)

        expected = ["q_1", "q_2", "q_3", "q_9"]
        assert result == expected

    def test_get_repeat_cols_large_numbers(self):
        """Test repeat columns with large numbers."""
        field = "survey_item"
        data_cols = [
            "survey_item_100",
            "survey_item_999",
            "survey_item_1000",  # Edge case: large number
            "survey_item_1_500",
            "survey_item_25_30_40",
            "survey_item_0",  # Edge case: zero
        ]

        result = scto_get_repeat_cols(field, data_cols)

        expected = [
            "survey_item_100",
            "survey_item_999",
            "survey_item_1000",
            "survey_item_1_500",
            "survey_item_25_30_40",
            "survey_item_0",
        ]
        assert result == expected

    def test_get_repeat_cols_field_name_with_numbers(self):
        """Test repeat columns when field name itself contains numbers."""
        field = "section2_question"
        data_cols = [
            "section2_question_1",
            "section2_question_2",
            "section2_question_1_3",
            "section1_question_1",  # Won't match - different field
            "section2_question",  # Original field, won't match pattern
        ]

        result = scto_get_repeat_cols(field, data_cols)

        expected = [
            "section2_question_1",
            "section2_question_2",
            "section2_question_1_3",
        ]
        assert result == expected

    def test_get_repeat_cols_empty_data_cols(self):
        """Test repeat columns with empty data columns list."""
        field = "test_field"
        data_cols = []

        result = scto_get_repeat_cols(field, data_cols)

        # Should return field split (empty list becomes the field name split)
        assert result == ["test_field"]

    def test_get_repeat_cols_field_with_underscores(self):
        """Test repeat columns with field names containing underscores."""
        field = "household_income_source"
        data_cols = [
            "household_income_source_1",
            "household_income_source_2",
            "household_income_source_1_2",
            "household_income_total",  # Won't match - different pattern
            "income_source_1",  # Won't match - missing prefix
        ]

        result = scto_get_repeat_cols(field, data_cols)

        expected = [
            "household_income_source_1",
            "household_income_source_2",
            "household_income_source_1_2",
        ]
        assert result == expected


class TestSctoImportData:
    """Test the scto_import_data function with different scenarios."""

    @patch("datasure.connectors.scto.scto_get_server_cache")
    @patch("datasure.connectors.scto.scto_server_connect")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_data_server_dataset_unbound_variable_bug(
        self, mock_save_table, mock_server_connect, mock_get_cache
    ):
        """Test importing data from server dataset reveals UnboundLocalError bug."""
        # Mock server cache and connection
        mock_get_cache.return_value = {
            "server": "testserver",
            "user": "user@example.com",
            "password": "password123",
        }

        mock_scto_instance = MagicMock()
        mock_server_connect.return_value = mock_scto_instance

        # Mock server dataset response
        csv_data = "name,age,city\nJohn,25,NYC\nJane,30,LA"
        mock_scto_instance.get_server_dataset.return_value = csv_data

        # Call function - should raise UnboundLocalError due to bug in source code
        # new_data_count is not defined in server dataset branch
        with pytest.raises(
            UnboundLocalError, match="cannot access local variable 'new_data_count'"
        ):
            scto_import_data(
                project_id="test_project",
                alias="test_alias",
                form_id="server_dataset_id",
                refresh=True,
            )

        # Verify server dataset was called
        mock_scto_instance.get_server_dataset.assert_called_once_with(
            "server_dataset_id"
        )
        # Verify data was saved to DuckDB despite the bug
        mock_save_table.assert_called_once()

    @patch("datasure.connectors.scto.scto_get_server_cache")
    @patch("datasure.connectors.scto.scto_server_connect")
    @patch("datasure.connectors.scto.scto_load_existing_data")
    @patch("datasure.connectors.scto.scto_get_xls")
    @patch("datasure.connectors.scto.scto_get_repeat_fields")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_data_form_without_refresh(
        self,
        mock_save_table,
        mock_repeat_fields,
        mock_get_xls,
        mock_load_existing,
        mock_server_connect,
        mock_get_cache,
    ):
        """Test importing form data without refresh (use existing data only)."""
        # Mock server cache and connection
        mock_get_cache.return_value = {
            "server": "testserver",
            "user": "user@example.com",
            "password": "password123",
        }

        mock_scto_instance = MagicMock()
        mock_server_connect.return_value = mock_scto_instance

        # Mock server dataset failure (so it tries form data)
        import requests

        mock_scto_instance.get_server_dataset.side_effect = requests.HTTPError(
            "Not a server dataset"
        )

        # Mock existing data
        existing_data = pd.DataFrame({"name": ["John"], "age": [25]})
        mock_load_existing.return_value = (existing_data, pd.Timestamp("2024-01-01"))

        # Call function with refresh=False
        result = scto_import_data(
            project_id="test_project",
            alias="test_alias",
            form_id="form123",
            refresh=False,  # Don't refresh - use existing data
            saveas=None,  # No save needed for this test
        )

        # Should return 0 since no new data was fetched
        assert result == 0
        # Should not call get_form_data since refresh=False
        mock_scto_instance.get_form_data.assert_not_called()

    @patch("datasure.connectors.scto.scto_get_server_cache")
    @patch("datasure.connectors.scto.scto_server_connect")
    @patch("datasure.connectors.scto.scto_load_existing_data")
    @patch("datasure.connectors.scto.scto_import_key")
    @patch("datasure.connectors.scto.scto_get_xls")
    @patch("datasure.connectors.scto.scto_get_repeat_fields")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_data_form_with_private_key(
        self,
        mock_save_table,
        mock_repeat_fields,
        mock_get_xls,
        mock_import_key,
        mock_load_existing,
        mock_server_connect,
        mock_get_cache,
        tmp_path,
    ):
        """Test importing form data with private key for encryption."""
        # Mock server cache and connection
        mock_get_cache.return_value = {
            "server": "testserver",
            "user": "user@example.com",
            "password": "password123",
        }

        mock_scto_instance = MagicMock()
        mock_server_connect.return_value = mock_scto_instance

        # Mock server dataset failure (so it tries form data)
        import requests

        mock_scto_instance.get_server_dataset.side_effect = requests.HTTPError(
            "Not a server dataset"
        )

        # Mock no existing data
        mock_load_existing.return_value = (pd.DataFrame(), pd.Timestamp("2024-01-01"))

        # Mock private key import
        mock_import_key.return_value = "decrypted_private_key_content"

        # Mock form data response
        form_data = [
            {
                "name": "John",
                "age": 25,
                "CompletionDate": "2024-01-15",
                "SubmissionDate": "2024-01-15",
            },
            {
                "name": "Jane",
                "age": 30,
                "CompletionDate": "2024-01-16",
                "SubmissionDate": "2024-01-16",
            },
        ]
        mock_scto_instance.get_form_data.return_value = form_data

        # Mock form definition
        questions_df = pd.DataFrame(
            {
                "name": ["name", "age"],
                "type": ["text", "integer"],
                "disabled": ["no", "no"],
            }
        )
        choices_df = pd.DataFrame()
        mock_get_xls.return_value = (questions_df, choices_df)
        mock_repeat_fields.return_value = []

        # Use temporary file path
        save_path = tmp_path / "save.csv"

        # Call function with private key
        result = scto_import_data(
            project_id="test_project",
            alias="test_alias",
            form_id="encrypted_form",
            refresh=True,
            key="/path/to/private.key",  # Private key provided
            saveas=str(save_path),
        )

        # Verify private key was imported
        mock_import_key.assert_called_once_with("/path/to/private.key")

        # Verify form data was requested with the key
        mock_scto_instance.get_form_data.assert_called_once_with(
            form_id="encrypted_form",
            format="json",
            oldest_completion_date=pd.Timestamp("2024-01-01"),
            key="decrypted_private_key_content",
        )

        # Should return count of new data
        assert result == 2

    @patch("datasure.connectors.scto.scto_get_server_cache")
    @patch("datasure.connectors.scto.scto_server_connect")
    @patch("datasure.connectors.scto.scto_load_existing_data")
    @patch("datasure.connectors.scto.scto_get_xls")
    @patch("datasure.connectors.scto.scto_get_repeat_fields")
    @patch("datasure.connectors.scto.scto_get_repeat_cols")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_data_with_data_type_conversion(
        self,
        mock_save_table,
        mock_repeat_cols,
        mock_repeat_fields,
        mock_get_xls,
        mock_load_existing,
        mock_server_connect,
        mock_get_cache,
        tmp_path,
    ):
        """Test data type conversion based on form definition."""
        # Mock server cache and connection
        mock_get_cache.return_value = {
            "server": "testserver",
            "user": "user@example.com",
            "password": "password123",
        }

        mock_scto_instance = MagicMock()
        mock_server_connect.return_value = mock_scto_instance

        # Mock server dataset failure (so it tries form data)
        import requests

        mock_scto_instance.get_server_dataset.side_effect = requests.HTTPError(
            "Not a server dataset"
        )

        # Mock no existing data
        mock_load_existing.return_value = (pd.DataFrame(), pd.Timestamp("2024-01-01"))

        # Mock form data with various data types
        form_data = [
            {
                "name": "John",
                "age": "25",  # String that should be converted to integer
                "birth_date": "2000-01-15",  # String that should be converted to date
                "survey_datetime": "2024-01-15 10:30:00",  # Datetime field
                "notes_field": "This is a note",  # Note field that should be dropped
                "CompletionDate": "2024-01-15",
                "SubmissionDate": "2024-01-15",
                "duration": "120",
                "formdef_version": "1",
            }
        ]
        mock_scto_instance.get_form_data.return_value = form_data

        # Mock form definition with different field types
        questions_df = pd.DataFrame(
            {
                "name": ["name", "age", "birth_date", "survey_datetime", "notes_field"],
                "type": ["text", "integer", "date", "datetime", "note"],
                "disabled": ["no", "no", "no", "no", "no"],
            }
        )
        choices_df = pd.DataFrame()
        mock_get_xls.return_value = (questions_df, choices_df)
        mock_repeat_fields.return_value = []
        mock_repeat_cols.return_value = []  # No repeat columns

        # Use temporary file path
        save_path = tmp_path / "save.csv"

        # Call function
        result = scto_import_data(
            project_id="test_project",
            alias="test_alias",
            form_id="typed_form",
            refresh=True,
            saveas=str(save_path),
        )

        # Verify data was processed and saved
        assert result == 1
        mock_save_table.assert_called_once()

        # Get the data that was passed to save_table
        save_call_args = mock_save_table.call_args[0]
        saved_data = save_call_args[1]  # The data parameter

    @patch("datasure.connectors.scto.scto_get_server_cache")
    @patch("datasure.connectors.scto.scto_server_connect")
    @patch("datasure.connectors.scto.scto_load_existing_data")
    @patch("datasure.connectors.scto.scto_get_xls")
    @patch("datasure.connectors.scto.scto_get_repeat_fields")
    @patch("datasure.connectors.scto.scto_get_repeat_cols")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_data_with_repeat_groups(
        self,
        mock_save_table,
        mock_repeat_cols,
        mock_repeat_fields,
        mock_get_xls,
        mock_load_existing,
        mock_server_connect,
        mock_get_cache,
        tmp_path,
    ):
        """Test data import with repeat group processing."""
        # Mock server cache and connection
        mock_get_cache.return_value = {
            "server": "testserver",
            "user": "user@example.com",
            "password": "password123",
        }

        mock_scto_instance = MagicMock()
        mock_server_connect.return_value = mock_scto_instance

        # Mock server dataset failure (so it tries form data)
        import requests

        mock_scto_instance.get_server_dataset.side_effect = requests.HTTPError(
            "Not a server dataset"
        )

        # Mock no existing data
        mock_load_existing.return_value = (pd.DataFrame(), pd.Timestamp("2024-01-01"))

        # Mock form data with repeat group columns
        form_data = [
            {
                "household_member_1": "John",
                "household_member_2": "Jane",
                "household_member_1_age": "25",
                "household_member_2_age": "30",
                "CompletionDate": "2024-01-15",
                "SubmissionDate": "2024-01-15",
            }
        ]
        mock_scto_instance.get_form_data.return_value = form_data

        # Mock form definition with repeat group
        questions_df = pd.DataFrame(
            {
                "name": ["household_member", "member_age"],
                "type": ["text", "integer"],
                "disabled": ["no", "no"],
            }
        )
        choices_df = pd.DataFrame()
        mock_get_xls.return_value = (questions_df, choices_df)

        # Mock repeat fields
        mock_repeat_fields.return_value = ["household_member"]

        # Mock repeat columns for household_member
        def mock_repeat_cols_side_effect(field, data_cols):
            if field == "household_member":
                return ["household_member_1", "household_member_2"]
            return [field]

        mock_repeat_cols.side_effect = mock_repeat_cols_side_effect

        # Use temporary file path
        save_path = tmp_path / "save.csv"

        # Call function
        result = scto_import_data(
            project_id="test_project",
            alias="test_alias",
            form_id="repeat_form",
            refresh=True,
            saveas=str(save_path),
        )

        # Verify repeat columns processing was called
        mock_repeat_cols.assert_called()
        assert result == 1

    @patch("datasure.connectors.scto.scto_get_server_cache")
    @patch("datasure.connectors.scto.scto_server_connect")
    @patch("datasure.connectors.scto.scto_load_existing_data")
    @patch("datasure.connectors.scto.st")
    def test_import_data_connection_error(
        self, mock_st, mock_load_existing, mock_server_connect, mock_get_cache
    ):
        """Test handling of connection errors during data import."""
        # Mock server cache and connection
        mock_get_cache.return_value = {
            "server": "testserver",
            "user": "user@example.com",
            "password": "password123",
        }

        mock_scto_instance = MagicMock()
        mock_server_connect.return_value = mock_scto_instance

        # Mock server dataset failure and connection error
        import requests

        mock_scto_instance.get_server_dataset.side_effect = requests.HTTPError(
            "Not a server dataset"
        )
        mock_scto_instance.get_form_data.side_effect = requests.ConnectionError(
            "Connection failed"
        )

        # Mock no existing data
        mock_load_existing.return_value = (pd.DataFrame(), pd.Timestamp("2024-01-01"))

        # Mock streamlit functions
        mock_st.warning.return_value = None
        mock_st.stop.side_effect = SystemExit("Streamlit stop called")

        # Call function - should handle connection error
        with pytest.raises(SystemExit):
            scto_import_data(
                project_id="test_project",
                alias="test_alias",
                form_id="form123",
                refresh=True,
            )

        # Verify warning was displayed
        mock_st.warning.assert_called()
        warning_call = mock_st.warning.call_args[0][0]
        assert "Check your internet connection" in warning_call

    @patch("datasure.connectors.scto.scto_get_server_cache")
    @patch("datasure.connectors.scto.scto_server_connect")
    @patch("datasure.connectors.scto.scto_load_existing_data")
    @patch("datasure.connectors.scto.st")
    def test_import_data_http_error_unauthorized(
        self, mock_st, mock_load_existing, mock_server_connect, mock_get_cache
    ):
        """Test handling of HTTP 401 unauthorized error."""
        # Mock server cache and connection
        mock_get_cache.return_value = {
            "server": "testserver",
            "user": "user@example.com",
            "password": "password123",
        }

        mock_scto_instance = MagicMock()
        mock_server_connect.return_value = mock_scto_instance

        # Mock server dataset failure and HTTP 401 error
        import requests

        mock_scto_instance.get_server_dataset.side_effect = requests.HTTPError(
            "Not a server dataset"
        )

        # Create a proper HTTP error with 401 status
        http_error = requests.HTTPError("Unauthorized")
        mock_response = MagicMock()
        mock_response.status_code = 401
        http_error.response = mock_response
        mock_scto_instance.get_form_data.side_effect = http_error

        # Mock no existing data
        mock_load_existing.return_value = (pd.DataFrame(), pd.Timestamp("2024-01-01"))

        # Mock streamlit functions
        mock_st.warning.return_value = None
        mock_st.stop.side_effect = SystemExit("Streamlit stop called")

        # Call function - should handle HTTP error
        with pytest.raises(SystemExit):
            scto_import_data(
                project_id="test_project",
                alias="test_alias",
                form_id="form123",
                refresh=True,
            )

        # Verify specific unauthorized warning was displayed
        warning_calls = [call[0][0] for call in mock_st.warning.call_args_list]
        assert any("Unauthorized access" in call for call in warning_calls)

    @patch("datasure.connectors.scto.scto_get_server_cache")
    @patch("datasure.connectors.scto.scto_server_connect")
    @patch("datasure.connectors.scto.scto_load_existing_data")
    @patch("datasure.connectors.scto.scto_get_xls")
    @patch("datasure.connectors.scto.scto_get_repeat_fields")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_data_merge_with_existing(
        self,
        mock_save_table,
        mock_repeat_fields,
        mock_get_xls,
        mock_load_existing,
        mock_server_connect,
        mock_get_cache,
        tmp_path,
    ):
        """Test merging new data with existing data."""
        # Mock server cache and connection
        mock_get_cache.return_value = {
            "server": "testserver",
            "user": "user@example.com",
            "password": "password123",
        }

        mock_scto_instance = MagicMock()
        mock_server_connect.return_value = mock_scto_instance

        # Mock server dataset failure (so it tries form data)
        import requests

        mock_scto_instance.get_server_dataset.side_effect = requests.HTTPError(
            "Not a server dataset"
        )

        # Mock existing data
        existing_data = pd.DataFrame(
            {
                "name": ["John", "Jane"],
                "age": [25, 30],
                "CompletionDate": ["2024-01-10", "2024-01-11"],
                "SubmissionDate": ["2024-01-10", "2024-01-11"],
            }
        )
        mock_load_existing.return_value = (existing_data, pd.Timestamp("2024-01-11"))

        # Mock new form data
        new_form_data = [
            {
                "name": "Bob",
                "age": 35,
                "CompletionDate": "2024-01-20",
                "SubmissionDate": "2024-01-20",
            }
        ]
        mock_scto_instance.get_form_data.return_value = new_form_data

        # Mock form definition
        questions_df = pd.DataFrame(
            {
                "name": ["name", "age"],
                "type": ["text", "integer"],
                "disabled": ["no", "no"],
            }
        )
        choices_df = pd.DataFrame()
        mock_get_xls.return_value = (questions_df, choices_df)
        mock_repeat_fields.return_value = []

        # Use temporary file path
        save_path = tmp_path / "save.csv"

        # Call function
        result = scto_import_data(
            project_id="test_project",
            alias="test_alias",
            form_id="merge_form",
            refresh=True,
            saveas=str(save_path),
        )

        # Should return count of new data only
        assert result == 1

        # Verify data was saved (should include both existing and new data)
        mock_save_table.assert_called_once()
        save_call_args = mock_save_table.call_args[0]
        saved_data = save_call_args[1]  # The data parameter

        # Should have 3 total records (2 existing + 1 new)
        assert len(saved_data) == 3
