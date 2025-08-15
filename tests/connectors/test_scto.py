"""Tests for the SurveyCTO connector module."""

import json
from datetime import datetime
from unittest.mock import Mock, patch

import pandas as pd
import polars as pl
import pytest
import requests
from pydantic_core import ValidationError

from datasure.connectors.scto import (
    CacheManager,
    ConnectionError,
    DataProcessor,
    FormConfig,
    FormType,
    MediaDownloader,
    MediaType,
    ProjectID,
    ServerCredentials,
    SurveyCTOClient,
    SurveyCTOConfig,
    SurveyCTOError,
    SurveyCTOUI,
    download_forms,
)


class TestFormType:
    """Test FormType enum."""

    def test_form_type_values(self):
        """Test FormType enum values."""
        assert FormType.REGULAR == "regular"
        assert FormType.SERVER_DATASET == "server_dataset"


class TestMediaType:
    """Test MediaType enum."""

    def test_media_type_values(self):
        """Test MediaType enum values."""
        assert MediaType.IMAGE == "image"
        assert MediaType.AUDIO == "audio"
        assert MediaType.VIDEO == "video"
        assert MediaType.FILE == "file"
        assert MediaType.COMMENTS == "comments"
        assert MediaType.TEXT_AUDIT == "text audit"
        assert MediaType.AUDIO_AUDIT == "audio audit"
        assert MediaType.SENSOR_STREAM == "sensor stream"


class TestSurveyCTOConfig:
    """Test SurveyCTOConfig dataclass."""

    def test_config_defaults(self):
        """Test default configuration values."""
        config = SurveyCTOConfig()
        assert config.max_retries == 3
        assert config.timeout == 30
        assert config.chunk_size == 1000
        assert config.default_date == datetime(2024, 1, 1, 13, 40, 40)

    def test_config_custom_values(self):
        """Test custom configuration values."""
        custom_date = datetime(2023, 1, 1, 12, 0, 0)
        config = SurveyCTOConfig(
            max_retries=5, timeout=60, chunk_size=2000, default_date=custom_date
        )
        assert config.max_retries == 5
        assert config.timeout == 60
        assert config.chunk_size == 2000
        assert config.default_date == custom_date


class TestProjectID:
    """Test ProjectID validation model."""

    def test_valid_project_id(self):
        """Test valid project IDs."""
        valid_ids = ["abc12345", "test1234", "project1", "12345678"]

        for project_id in valid_ids:
            obj = ProjectID(project_id=project_id)
            assert obj.project_id == project_id

    def test_invalid_project_id_length(self):
        """Test invalid project ID lengths."""
        with pytest.raises(
            ValueError, match="String should have at least 8 characters"
        ):
            ProjectID(project_id="short")

        with pytest.raises(ValueError, match="String should have at most 8 characters"):
            ProjectID(project_id="toolongid")

    def test_invalid_project_id_format(self):
        """Test invalid project ID formats."""
        invalid_ids = [
            "ABC12345",  # uppercase
            "test-123",  # hyphen
            "test_123",  # underscore
            "test.123",  # dot
            "test 123",  # space
        ]

        for project_id in invalid_ids:
            with pytest.raises(
                ValueError,
                match="Project ID must be alphanumeric and 8 characters long",
            ):
                ProjectID(project_id=project_id)


class TestServerCredentials:
    """Test ServerCredentials validation model."""

    def test_valid_credentials(self):
        """Test valid server credentials."""
        creds = ServerCredentials(
            server="testserver", user="user@example.com", password="password123"
        )
        assert creds.server == "testserver"
        assert creds.user == "user@example.com"
        assert creds.password == "password123"

    def test_invalid_server_name(self):
        """Test invalid server names."""
        invalid_servers = [
            "A",  # too short
            "Server",  # uppercase
            "123server",  # starts with number
            "server-name",  # hyphen
            "server.com",  # dot
        ]

        for server in invalid_servers:
            with pytest.raises(ValidationError):
                ServerCredentials(
                    server=server, user="user@example.com", password="password"
                )

    def test_invalid_email(self):
        """Test invalid email formats."""
        invalid_emails = [
            "notanemail",
            "@domain.com",
            "user@",
            "user@domain",
            "user name@domain.com",
        ]

        for email in invalid_emails:
            with pytest.raises(
                ValueError, match="Invalid email format for SurveyCTO user"
            ):
                ServerCredentials(server="testserver", user=email, password="password")

    def test_empty_password(self):
        """Test empty password validation."""
        with pytest.raises(ValueError, match="String should have at least 1 character"):
            ServerCredentials(server="testserver", user="user@example.com", password="")


class TestFormConfig:
    """Test FormConfig model."""

    def test_form_config_defaults(self):
        """Test FormConfig default values."""
        config = FormConfig(alias="test", form_id="form123", server="testserver")
        assert config.alias == "test"
        assert config.form_id == "form123"
        assert config.server == "testserver"
        assert config.private_key is None
        assert config.save_to is None
        assert config.attachments is False
        assert config.refresh is True

    def test_form_config_all_fields(self):
        """Test FormConfig with all fields."""
        config = FormConfig(
            alias="survey",
            form_id="survey123",
            server="myserver",
            private_key="/path/to/key.pem",
            save_to="/path/to/data.csv",
            attachments=True,
            refresh=False,
        )
        assert config.alias == "survey"
        assert config.form_id == "survey123"
        assert config.server == "myserver"
        assert config.private_key == "/path/to/key.pem"
        assert config.save_to == "/path/to/data.csv"
        assert config.attachments is True
        assert config.refresh is False


class TestSurveyCTOExceptions:
    """Test SurveyCTO exceptions."""

    def test_surveycto_error(self):
        """Test SurveyCTOError base exception."""
        error = SurveyCTOError("Test error")
        assert str(error) == "Test error"
        assert isinstance(error, Exception)

    def test_connection_error(self):
        """Test ConnectionError exception."""
        error = ConnectionError("Connection failed")
        assert str(error) == "Connection failed"
        assert isinstance(error, SurveyCTOError)


class TestCacheManager:
    """Test CacheManager class."""

    def test_cache_manager_init(self):
        """Test CacheManager initialization."""
        manager = CacheManager("test1234")
        assert manager.project_id == "test1234"
        assert hasattr(manager, "logger")

    @patch("datasure.connectors.scto.retrieve_scto_credentials")
    def test_get_server_cache_secure_credentials_exist(self, mock_retrieve_credentials):
        """Test getting server cache from secure credential storage."""
        # Mock successful credential retrieval from secure storage
        mock_retrieve_credentials.return_value = {
            "success": True,
            "credentials": {
                "server": "testserver",
                "username": "user@example.com",
                "password": "secure_password_123",
            },
        }

    @patch("datasure.connectors.scto.retrieve_scto_credentials")
    @patch("datasure.connectors.scto.migrate_plaintext_credentials")
    def test_get_server_cache_migration_success(
        self, mock_migrate_credentials, mock_retrieve_credentials
    ):
        """Test getting server cache with successful plaintext migration."""
        # Mock initial retrieval failure, then migration success, then retry success
        mock_retrieve_credentials.side_effect = [
            {"success": False, "error": "No credentials found"},
            {
                "success": True,
                "credentials": {
                    "server": "migrated_server",
                    "username": "migrated@example.com",
                    "password": "migrated_password",
                },
            },
        ]

        mock_migrate_credentials.return_value = {"success": True}

    @patch("datasure.connectors.scto.retrieve_scto_credentials")
    @patch("datasure.connectors.scto.migrate_plaintext_credentials")
    def test_get_server_cache_no_credentials_found(
        self, mock_migrate_credentials, mock_retrieve_credentials
    ):
        """Test getting server cache when no credentials exist."""
        # Mock both secure retrieval and migration failure
        mock_retrieve_credentials.return_value = {
            "success": False,
            "error": "No credentials found",
        }
        mock_migrate_credentials.return_value = {
            "success": False,
            "error": "No plaintext file found",
        }

        manager = CacheManager("test1234")
        result = manager.get_server_cache()

        assert result == {}


class TestSctoLoadForms:
    """Test the scto_load_forms function."""

    @patch("datasure.connectors.scto.get_cache_path")
    def test_save_server_cache(self, mock_get_cache_path, tmp_path):
        """Test saving server cache."""
        cache_file = tmp_path / "scto.json"
        mock_get_cache_path.return_value = cache_file

        manager = CacheManager("test1234")
        credentials = ServerCredentials(
            server="testserver", user="test@example.com", password="password"
        )

        manager.save_server_cache(credentials)

        assert cache_file.exists()
        assert cache_file.parent.exists()
        saved_data = json.loads(cache_file.read_text())
        assert saved_data["server"] == "testserver"
        assert saved_data["user"] == "test@example.com"

    def test_get_existing_data_no_file(self):
        """Test getting existing data when file doesn't exist."""
        manager = CacheManager("test1234")
        data, date = manager.get_existing_data("/nonexistent/file.csv")

        assert data.empty
        assert date == SurveyCTOConfig.default_date

    def test_get_existing_data_empty_file(self, tmp_path):
        """Test getting existing data from empty file."""
        data_file = tmp_path / "empty.csv"
        data_file.write_text("")

        manager = CacheManager("test1234")
        data, date = manager.get_existing_data(str(data_file))

        assert data.empty
        assert date == SurveyCTOConfig.default_date

    def test_get_existing_data_no_submission_date(self, tmp_path):
        """Test getting existing data without SubmissionDate column."""
        data_file = tmp_path / "data.csv"
        data_file.write_text("name,age\nJohn,25\nJane,30")

        manager = CacheManager("test1234")
        data, date = manager.get_existing_data(str(data_file))

        assert len(data) == 2
        assert date == SurveyCTOConfig.default_date

    def test_get_existing_data_with_submission_date(self, tmp_path):
        """Test getting existing data with SubmissionDate column."""
        data_file = tmp_path / "data.csv"
        csv_content = "name,age,SubmissionDate\nJohn,25,2024-01-15 10:30:00\nJane,30,2024-01-20 15:45:00"
        data_file.write_text(csv_content)

        manager = CacheManager("test1234")
        data, date = manager.get_existing_data(str(data_file))

        assert len(data) == 2
        assert date == pd.to_datetime("2024-01-20 15:45:00")

    def test_get_existing_data_exception(self, caplog):
        """Test getting existing data with exception."""
        manager = CacheManager("test1234")

        # Use invalid file path that would cause an exception
        data, date = manager.get_existing_data("/invalid/path/that/causes/error")

        assert data.empty
        assert date == SurveyCTOConfig.default_date


class TestDataProcessor:
    """Test DataProcessor class."""

    def test_data_processor_init(self):
        """Test DataProcessor initialization."""
        processor = DataProcessor()
        assert hasattr(processor, "logger")

    def test_get_repeat_fields_empty(self):
        """Test getting repeat fields from empty DataFrame."""
        processor = DataProcessor()
        questions = pd.DataFrame({"type": [], "name": []})

        result = processor.get_repeat_fields(questions)
        assert result == []

    def test_get_repeat_fields_no_repeats(self):
        """Test getting repeat fields with no repeat groups."""
        processor = DataProcessor()
        questions = pd.DataFrame(
            {
                "type": ["text", "integer", "select_one"],
                "name": ["name", "age", "gender"],
            }
        )

        result = processor.get_repeat_fields(questions)
        assert result == []

    def test_get_repeat_fields_with_repeats(self):
        """Test getting repeat fields with repeat groups."""
        processor = DataProcessor()
        questions = pd.DataFrame(
            {
                "type": [
                    "begin repeat",
                    "text",
                    "integer",
                    "end repeat",
                    "begin repeat",
                    "text",
                    "end repeat",
                    "text",
                ],
                "name": [
                    "household",
                    "member_name",
                    "member_age",
                    "",
                    "assets",
                    "asset_name",
                    "",
                    "notes",
                ],
            }
        )

        result = processor.get_repeat_fields(questions)
        assert "member_name" in result
        assert "member_age" in result
        assert "asset_name" in result
        assert "notes" not in result

    def test_get_repeat_fields_nested_repeats(self):
        """Test getting repeat fields with nested repeat groups."""
        processor = DataProcessor()
        questions = pd.DataFrame(
            {
                "type": [
                    "begin repeat",
                    "begin repeat",
                    "text",
                    "end repeat",
                    "end repeat",
                ],
                "name": ["household", "members", "name", "", ""],
            }
        )

        result = processor.get_repeat_fields(questions)
        assert "name" in result

    def test_get_repeat_columns_no_matches(self):
        """Test getting repeat columns with no matches."""
        processor = DataProcessor()
        result = processor.get_repeat_columns("nonexistent", ["col1", "col2"])
        assert result == ["nonexistent"]

    def test_get_repeat_columns_with_matches(self):
        """Test getting repeat columns with matches."""
        processor = DataProcessor()
        data_cols = [
            "household_1",
            "household_2",
            "household_1_2",
            "other_field",
            "household_info",
        ]

        result = processor.get_repeat_columns("household", data_cols)
        expected = ["household_1", "household_2", "household_1_2"]
        assert result == expected

    def test_convert_data_types_datetime_columns(self):
        """Test converting datetime columns."""
        processor = DataProcessor()
        data = pd.DataFrame(
            {
                "CompletionDate": ["2024-01-15 10:30:00", "2024-01-16 11:30:00"],
                "SubmissionDate": ["2024-01-15", "2024-01-16"],
                "starttime": ["2024-01-15T10:30:00", "2024-01-16T11:30:00"],
                "endtime": ["2024-01-15T12:30:00", "2024-01-16T13:30:00"],
            }
        )
        questions = pd.DataFrame({"type": [], "name": []})

        result = processor.convert_data_types(data, questions)

        assert pd.api.types.is_datetime64_any_dtype(result["CompletionDate"])
        assert pd.api.types.is_datetime64_any_dtype(result["SubmissionDate"])
        assert pd.api.types.is_datetime64_any_dtype(result["starttime"])
        assert pd.api.types.is_datetime64_any_dtype(result["endtime"])

    def test_convert_data_types_numeric_columns(self):
        """Test converting numeric columns."""
        processor = DataProcessor()
        data = pd.DataFrame({"duration": ["120", "180"], "formdef_version": ["1", "2"]})
        questions = pd.DataFrame({"type": [], "name": []})

        result = processor.convert_data_types(data, questions)

        assert pd.api.types.is_numeric_dtype(result["duration"])
        assert pd.api.types.is_numeric_dtype(result["formdef_version"])

    def test_convert_data_types_form_based(self):
        """Test converting data types based on form definition."""
        processor = DataProcessor()
        data = pd.DataFrame(
            {
                "age": ["25", "30"],
                "birth_date": ["2000-01-15", "1995-05-20"],
                "survey_time": ["10:30:00", "14:15:00"],
                "notes": ["Note 1", "Note 2"],
            }
        )
        questions = pd.DataFrame(
            {
                "type": ["integer", "date", "time", "note"],
                "name": ["age", "birth_date", "survey_time", "notes"],
            }
        )

        result = processor.convert_data_types(data, questions)

        assert pd.api.types.is_numeric_dtype(result["age"])
        assert pd.api.types.is_datetime64_any_dtype(result["birth_date"])
        assert pd.api.types.is_datetime64_any_dtype(result["survey_time"])
        assert "notes" not in result.columns  # Note fields are dropped

    def test_convert_data_types_with_repeat_fields(self):
        """Test converting data types with repeat fields."""
        processor = DataProcessor()
        data = pd.DataFrame(
            {"member_age_1": ["25", "30"], "member_age_2": ["28", "35"]}
        )
        questions = pd.DataFrame(
            {
                "type": ["begin repeat", "integer", "end repeat"],
                "name": ["members", "member_age", ""],
            }
        )

        result = processor.convert_data_types(data, questions)

        assert pd.api.types.is_numeric_dtype(result["member_age_1"])
        assert pd.api.types.is_numeric_dtype(result["member_age_2"])

    def test_convert_data_types_error_handling(self, caplog):
        """Test data type conversion error handling."""
        processor = DataProcessor()
        data = pd.DataFrame({"invalid_date": ["not-a-date", "also-not-date"]})
        questions = pd.DataFrame({"type": ["date"], "name": ["invalid_date"]})

        result = processor.convert_data_types(data, questions)

        # Should handle errors gracefully
        assert "invalid_date" in result.columns


class TestMediaDownloader:
    """Test MediaDownloader class."""

    def test_media_downloader_init(self):
        """Test MediaDownloader initialization."""
        mock_client = Mock()
        config = SurveyCTOConfig()

        downloader = MediaDownloader(mock_client, config)
        assert downloader.scto_client == mock_client
        assert downloader.config == config
        assert hasattr(downloader, "logger")

    def test_download_single_file(self, tmp_path):
        """Test downloading a single media file."""
        mock_client = Mock()
        mock_client.get_attachment.return_value = b"fake_image_content"

        config = SurveyCTOConfig()
        downloader = MediaDownloader(mock_client, config)

        media_folder = tmp_path / "media"
        media_folder.mkdir()

        downloader._download_single_file(
            url="photo.jpg",
            submission_key="uuid:123456",
            field_name="photo",
            media_folder=media_folder,
            encryption_key=None,
        )

        # Check file was created with correct name
        expected_file = media_folder / "photo_123456.jpg"
        assert expected_file.exists()
        assert expected_file.read_bytes() == b"fake_image_content"

        # Check that get_attachment was called with correct parameters
        mock_client.get_attachment.assert_called_once_with("photo.jpg", key=None)

    def test_download_single_file_with_extension(self, tmp_path):
        """Test downloading a single file that needs extension."""
        mock_client = Mock()
        mock_client.get_attachment.return_value = b"csv_content"

        config = SurveyCTOConfig()
        downloader = MediaDownloader(mock_client, config)

        media_folder = tmp_path / "media"
        media_folder.mkdir()

        downloader._download_single_file(
            url="data",  # No extension
            submission_key="uuid:789",
            field_name="data_export",
            media_folder=media_folder,
            encryption_key="test_key",
        )

        # Check file was created with .csv extension
        expected_file = media_folder / "data_export_789.csv"
        assert expected_file.exists()

        # Check encryption key was passed
        mock_client.get_attachment.assert_called_once_with("data", key="test_key")


class TestSurveyCTOClient:
    """Test SurveyCTOClient class."""

    def test_client_init(self):
        """Test SurveyCTOClient initialization."""
        client = SurveyCTOClient("test1234")
        assert client.project_id == "test1234"
        assert isinstance(client.config, SurveyCTOConfig)
        assert isinstance(client.cache_manager, CacheManager)
        assert isinstance(client.data_processor, DataProcessor)
        assert client._scto_client is None

    def test_client_init_with_config(self):
        """Test SurveyCTOClient initialization with custom config."""
        config = SurveyCTOConfig(max_retries=5, timeout=60)
        client = SurveyCTOClient("test1234", config)
        assert client.config == config

    @patch("datasure.connectors.scto.pysurveycto.SurveyCTOObject")
    @patch("datasure.connectors.scto.st")
    def test_connect_success_with_validation(self, mock_st, mock_scto_class):
        """Test successful connection with validation."""
        # Setup mocks
        mock_scto_instance = Mock()
        mock_scto_class.return_value = mock_scto_instance
        mock_scto_instance.list_forms.return_value = [
            {"id": "form1", "title": "Form 1", "encrypted": False},
            {"id": "form2", "title": "Form 2", "encrypted": True},
        ]

        mock_st.spinner.return_value.__enter__ = Mock()
        mock_st.spinner.return_value.__exit__ = Mock()

        client = SurveyCTOClient("test1234")
        credentials = ServerCredentials(
            server="testserver", user="test@example.com", password="password"
        )

        result = client.connect(credentials, validate_permissions=True)

        # Check connection info
        assert result["server"] == "testserver"
        assert result["connected"] is True
        assert result["forms_count"] == 2
        assert len(result["forms_list"]) == 2
        assert result["validation_attempted"] is True

        # Check SurveyCTO client was created
        mock_scto_class.assert_called_once_with(
            "testserver", "test@example.com", "password"
        )
        mock_scto_instance.list_forms.assert_called_once()
        mock_st.success.assert_called()

    @patch("datasure.connectors.scto.pysurveycto.SurveyCTOObject")
    @patch("datasure.connectors.scto.st")
    def test_connect_success_no_validation(self, mock_st, mock_scto_class):
        """Test successful connection without validation."""
        mock_scto_instance = Mock()
        mock_scto_class.return_value = mock_scto_instance

        client = SurveyCTOClient("test1234")
        credentials = ServerCredentials(
            server="testserver", user="test@example.com", password="password"
        )

        result = client.connect(credentials, validate_permissions=False)

        assert result["connected"] is True
        assert result["validation_attempted"] is False
        mock_scto_instance.list_forms.assert_not_called()
        mock_st.success.assert_called()

    @patch("datasure.connectors.scto.pysurveycto.SurveyCTOObject")
    @patch("datasure.connectors.scto.st")
    def test_connect_http_error_401(self, mock_st, mock_scto_class):
        """Test connection with HTTP 401 error."""
        mock_scto_instance = Mock()
        mock_scto_class.return_value = mock_scto_instance

        # Create HTTP error with 401 status
        http_error = requests.exceptions.HTTPError("Unauthorized")
        mock_response = Mock()
        mock_response.status_code = 401
        http_error.response = mock_response
        mock_scto_instance.list_forms.side_effect = http_error

        mock_st.spinner.return_value.__enter__ = Mock()
        mock_st.spinner.return_value.__exit__ = Mock()

        client = SurveyCTOClient("test1234")
        credentials = ServerCredentials(
            server="testserver", user="test@example.com", password="password"
        )

        with pytest.raises(ConnectionError):
            client.connect(credentials)

    @patch("datasure.connectors.scto.pysurveycto.SurveyCTOObject")
    def test_connect_connection_error(self, mock_scto_class):
        """Test connection with network connection error."""
        mock_scto_instance = Mock()
        mock_scto_class.return_value = mock_scto_instance
        mock_scto_instance.list_forms.side_effect = (
            requests.exceptions.ConnectionError()
        )

        client = SurveyCTOClient("test1234")
        credentials = ServerCredentials(
            server="testserver", user="test@example.com", password="password"
        )

        with pytest.raises(ConnectionError, match="Cannot connect to server"):
            client.connect(credentials)

    @patch("datasure.connectors.scto.pysurveycto.SurveyCTOObject")
    def test_connect_timeout_error(self, mock_scto_class):
        """Test connection with timeout error."""
        mock_scto_instance = Mock()
        mock_scto_class.return_value = mock_scto_instance
        mock_scto_instance.list_forms.side_effect = requests.exceptions.Timeout()

        client = SurveyCTOClient("test1234")
        credentials = ServerCredentials(
            server="testserver", user="test@example.com", password="password"
        )

        with pytest.raises(ConnectionError, match="Connection timeout"):
            client.connect(credentials)

    @patch("datasure.connectors.scto.pysurveycto.SurveyCTOObject")
    def test_connect_invalid_server_name(self, mock_scto_class):
        """Test connection with invalid server name."""
        mock_scto_class.side_effect = Exception("Invalid server name")

        client = SurveyCTOClient("test1234")
        credentials = ServerCredentials(
            server="testserver", user="test@example.com", password="password"
        )

        with pytest.raises(ConnectionError, match="Invalid server name"):
            client.connect(credentials)

    def test_get_form_definition_not_connected(self):
        """Test getting form definition when not connected."""
        client = SurveyCTOClient("test1234")

        with pytest.raises(ConnectionError, match="Not connected to server"):
            client.get_form_definition("form123")

    def test_get_form_definition_success(self):
        """Test getting form definition successfully."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        form_def = {
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
        mock_scto_client.get_form_definition.return_value = form_def

        questions, choices = client.get_form_definition("form123")

        assert len(questions) == 2
        assert list(questions.columns) == ["name", "type", "label"]
        assert questions.iloc[0]["name"] == "question1"

        assert len(choices) == 2
        assert list(choices.columns) == ["list name", "name", "label"]
        assert choices.iloc[0]["name"] == "red"

    def test_get_form_definition_error(self):
        """Test getting form definition with error."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client
        mock_scto_client.get_form_definition.side_effect = Exception("API Error")

        with pytest.raises(SurveyCTOError, match="Failed to get form definition"):
            client.get_form_definition("form123")

    @patch("datasure.connectors.scto.pl.read_csv")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_server_dataset(self, mock_save_table, mock_read_csv):
        """Test importing from server dataset."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        csv_data = "name,age\nJohn,25\nJane,30"
        mock_scto_client.get_server_dataset.return_value = csv_data

        mock_df = pl.DataFrame({"name": ["John", "Jane"], "age": [25, 30]})
        mock_read_csv.return_value = mock_df

        form_config = FormConfig(
            alias="test_dataset", form_id="dataset123", server="testserver"
        )

        result = client._import_server_dataset(form_config)

        assert result == 2
        mock_scto_client.get_server_dataset.assert_called_once_with("dataset123")
        mock_read_csv.assert_called_once_with(csv_data.encode())
        mock_save_table.assert_called_once_with(
            "test1234", mock_df, alias="test_dataset", db_name="raw"
        )

    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_regular_form_no_refresh(self, mock_save_table):
        """Test importing regular form with refresh=False."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        form_config = FormConfig(
            alias="test_form", form_id="form123", server="testserver", refresh=False
        )

        result = client._import_regular_form(form_config)

        assert result == 0
        mock_scto_client.get_form_data.assert_not_called()
        mock_save_table.assert_not_called()

    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_regular_form_with_refresh(self, mock_save_table):
        """Test importing regular form with refresh=True."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        # Mock form data response
        form_data = [
            {"name": "John", "age": 25, "CompletionDate": "2024-01-15"},
            {"name": "Jane", "age": 30, "CompletionDate": "2024-01-16"},
        ]
        mock_scto_client.get_form_data.return_value = form_data

        # Mock form definition
        mock_scto_client.get_form_definition.return_value = {
            "fieldsRowsAndColumns": [
                ["name", "type", "disabled"],
                ["name", "text", "no"],
                ["age", "integer", "no"],
            ],
            "choicesRowsAndColumns": [["list name", "name", "label"]],
        }

        form_config = FormConfig(
            alias="test_form", form_id="form123", server="testserver", refresh=True
        )

        result = client._import_regular_form(form_config)

        assert result == 2
        mock_scto_client.get_form_data.assert_called_once()
        mock_save_table.assert_called_once()

    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_data_connection_fallback(self, mock_save_table):
        """Test import_data with connection fallback."""
        client = SurveyCTOClient("test1234")

        # Mock cache manager to return credentials
        client.cache_manager.get_server_cache = Mock(
            return_value={
                "server": "testserver",
                "user": "test@example.com",
                "password": "password",
            }
        )

        # Mock connect method
        client.connect = Mock()

        # Mock _import_server_dataset to fail and _import_regular_form to succeed
        client._import_server_dataset = Mock(side_effect=Exception("Not a dataset"))
        client._import_regular_form = Mock(return_value=5)

        form_config = FormConfig(
            alias="test_form", form_id="form123", server="testserver"
        )

        result = client.import_data(form_config)

        assert result == 5
        client.connect.assert_called_once()
        client._import_server_dataset.assert_called_once_with(form_config)
        client._import_regular_form.assert_called_once_with(form_config)

    def test_import_data_no_connection_no_cache(self):
        """Test import_data with no connection and no cached credentials."""
        client = SurveyCTOClient("test1234")
        client.cache_manager.get_server_cache = Mock(return_value={})

        form_config = FormConfig(
            alias="test_form", form_id="form123", server="testserver"
        )

        with pytest.raises(ConnectionError, match="Not connected to server"):
            client.import_data(form_config)

    @patch("datasure.connectors.scto.MediaDownloader")
    def test_download_attachments(self, mock_downloader_class, tmp_path):
        """Test downloading attachments."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        # Mock MediaDownloader
        mock_downloader = Mock()
        mock_downloader_class.return_value = mock_downloader

        questions = pd.DataFrame(
            {
                "type": ["text", "image", "audio", "note"],
                "name": ["name", "photo", "voice", "notes"],
            }
        )

        data = pd.DataFrame(
            {"name": ["John"], "photo": ["photo1.jpg"], "voice": ["audio1.wav"]}
        )

        form_config = FormConfig(
            alias="test_form",
            form_id="form123",
            server="testserver",
            save_to=str(tmp_path / "data.csv"),
            private_key="test_key",
        )

        client._download_attachments(questions, data, form_config)

        # Check MediaDownloader was created and called
        mock_downloader_class.assert_called_once_with(mock_scto_client, client.config)
        mock_downloader.download_media_files.assert_called_once()

        # Check the call arguments
        args = mock_downloader.download_media_files.call_args[0]
        media_fields, _, media_folder, encryption_key = args

        assert "photo" in media_fields
        assert "voice" in media_fields
        assert "name" not in media_fields  # text field
        assert "notes" not in media_fields  # note field
        assert str(media_folder) == str(tmp_path / "media")
        assert encryption_key == "test_key"


class TestSurveyCTOUI:
    """Test SurveyCTOUI class."""

    def test_ui_init(self):
        """Test SurveyCTOUI initialization."""
        ui = SurveyCTOUI("test1234")
        assert ui.project_id == "test1234"
        assert isinstance(ui.client, SurveyCTOClient)

    def test_get_logo_path(self):
        """Test getting logo path."""
        ui = SurveyCTOUI("test1234")
        logo_path = ui._get_logo_path()
        assert "SurveyCTO-Logo-CMYK.png" in logo_path

    @patch("datasure.connectors.scto.st")
    def test_render_login_form(self, mock_st):
        """Test rendering login form."""
        ui = SurveyCTOUI("test1234")

        # Mock Streamlit inputs
        mock_st.text_input.side_effect = [
            "testserver",
            "user@example.com",
            "password123",
        ]
        mock_st.button.return_value = True

        # Mock other Streamlit functions
        mock_st.container.return_value.__enter__ = Mock()
        mock_st.container.return_value.__exit__ = Mock()
        mock_st.image.return_value = None
        mock_st.markdown.return_value = None

        # Mock client.connect
        ui.client.connect = Mock()

        ui.render_login_form()

        # Check that connect was called with correct credentials
        ui.client.connect.assert_called_once()
        args = ui.client.connect.call_args[0][0]
        assert args.server == "testserver"
        assert args.user == "user@example.com"
        assert args.password == "password123"

    @patch("datasure.connectors.scto.st")
    def test_render_login_form_error(self, mock_st):
        """Test rendering login form with connection error."""
        ui = SurveyCTOUI("test1234")

        # Mock Streamlit inputs
        mock_st.text_input.side_effect = [
            "testserver",
            "user@example.com",
            "password123",
        ]
        mock_st.button.return_value = True

        # Mock other Streamlit functions
        mock_st.container.return_value.__enter__ = Mock()
        mock_st.container.return_value.__exit__ = Mock()
        mock_st.image.return_value = None
        mock_st.markdown.return_value = None

        # Mock client.connect to raise error
        ui.client.connect = Mock(side_effect=ConnectionError("Connection failed"))

        ui.render_login_form()

        # Check that error was displayed
        mock_st.error.assert_called_once_with("Connection failed: Connection failed")


class TestDownloadForms:
    """Test download_forms function."""

    @patch("datasure.connectors.scto.st")
    def test_download_forms_empty_list(self, mock_st):
        """Test download_forms with empty form list."""
        download_forms("test1234", [])
        mock_st.warning.assert_called_once_with("No forms selected for download")

    @patch("datasure.connectors.scto.SurveyCTOClient")
    @patch("datasure.connectors.scto.st")
    def test_download_forms_success(self, mock_st, mock_client_class):
        """Test download_forms with successful downloads."""
        # Setup mocks
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.import_data.return_value = 5

        mock_progress = Mock()
        mock_st.progress.return_value = mock_progress

        # Create form configs
        form_configs = [
            FormConfig(alias="form1", form_id="f1", server="server1"),
            FormConfig(alias="form2", form_id="f2", server="server1"),
        ]

        download_forms("test1234", form_configs)

        # Check client was created and import_data was called
        mock_client_class.assert_called_once_with("test1234")
        assert mock_client.import_data.call_count == 2

    @patch("datasure.connectors.scto.SurveyCTOClient")
    @patch("datasure.connectors.scto.st")
    def test_download_forms_with_error(self, mock_st, mock_client_class):
        """Test download_forms with import error."""
        # Setup mocks
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.import_data.side_effect = [5, Exception("Import failed")]

        mock_progress = Mock()
        mock_st.progress.return_value = mock_progress

        # Create form configs
        form_configs = [
            FormConfig(alias="form1", form_id="f1", server="server1"),
            FormConfig(alias="form2", form_id="f2", server="server1"),
        ]

        download_forms("test1234", form_configs)

        # Check error was displayed for second form
        error_calls = [
            call
            for call in mock_st.error.call_args_list
            if "Failed to download form2" in str(call)
        ]
        assert len(error_calls) == 1
