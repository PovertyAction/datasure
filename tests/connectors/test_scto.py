"""Tests for the SurveyCTO connector module."""

from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import polars as pl
import pytest
from pydantic_core import ValidationError

from datasure.connectors.scto import (
    CacheManager,
    ConnectionError,
    DataProcessor,
    FormConfig,
    FormType,
    MediaDownloader,
    MediaType,
    ServerCredentials,
    SurveyCTOClient,
    SurveyCTOConfig,
    SurveyCTOError,
    SurveyCTOUI,
    download_forms,
    scto_server_connect,
)
from datasure.connectors.scto import (
    ValidationError as SctoValidationError,
)
from datasure.utils.scto_api import SurveyCTOAPIError
from datasure.utils.settings_utils import ProjectID


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests.
    """
    pass


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
        assert config.date_format == "%b %d, %Y %I:%M:%S %p"

    def test_config_custom_values(self):
        """Test custom configuration values."""
        custom_date = datetime(2023, 1, 1, 12, 0, 0)
        custom_format = "%Y-%m-%d %H:%M:%S"
        config = SurveyCTOConfig(
            max_retries=5,
            timeout=60,
            chunk_size=2000,
            default_date=custom_date,
            date_format=custom_format,
        )
        assert config.max_retries == 5
        assert config.timeout == 60
        assert config.chunk_size == 2000
        assert config.default_date == custom_date
        assert config.date_format == custom_format


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
                match="Project ID must be alphanumeric only and exactly 8 characters long",
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


class TestSctoServerConnect:
    """Test the scto_server_connect function."""

    @patch("datasure.connectors.scto.st")
    def test_scto_server_connect_empty_fields(self, mock_st):
        """Test scto_server_connect with empty required fields."""
        # Test empty servername
        scto_server_connect("", "user@example.com", "password")
        mock_st.warning.assert_called_with("Complete all required fields.")
        mock_st.stop.assert_called()

        # Reset mocks
        mock_st.reset_mock()

        # Test empty username
        scto_server_connect("testserver", "", "password")
        mock_st.warning.assert_called_with("Complete all required fields.")
        mock_st.stop.assert_called()

        # Reset mocks
        mock_st.reset_mock()

        # Test empty password
        scto_server_connect("testserver", "user@example.com", "")
        mock_st.warning.assert_called_with("Complete all required fields.")
        mock_st.stop.assert_called()

    @patch("datasure.connectors.scto.st")
    def test_scto_server_connect_invalid_servername(self, mock_st):
        """Test scto_server_connect with invalid server name."""
        invalid_servers = [
            "1server",  # starts with number
            "Server",  # uppercase
            "server-name",  # hyphen
            "server.com",  # dot
            "s" * 65,  # too long
        ]

        for server in invalid_servers:
            mock_st.reset_mock()
            scto_server_connect(server, "user@example.com", "password")
            mock_st.warning.assert_called_with("Invalid server name.")
            mock_st.stop.assert_called()

    @patch("datasure.connectors.scto.st")
    def test_scto_server_connect_valid_inputs(self, mock_st):
        """Test scto_server_connect with valid inputs
        (should not call warning or stop).
        """
        scto_server_connect("testserver", "user@example.com", "password")
        mock_st.warning.assert_not_called()
        mock_st.stop.assert_not_called()


class TestSctoFunctions:
    """Test standalone scto functions."""

    @patch("datasure.connectors.scto.duckdb_get_table")
    def test_get_existing_data_no_file(self, mock_get_table):
        """Test getting existing data when file doesn't exist."""
        manager = CacheManager("test1234")

        # Mock empty DataFrame return
        mock_get_table.return_value = pl.DataFrame()

        data, date = manager.get_existing_data("test_alias")

        assert data.is_empty()
        assert date == SurveyCTOConfig().default_date

    @patch("datasure.connectors.scto.duckdb_get_table")
    def test_get_existing_data_empty_file(self, mock_get_table):
        """Test getting existing data from empty file."""
        manager = CacheManager("test1234")

        # Mock empty DataFrame return
        mock_get_table.return_value = pl.DataFrame()

        data, date = manager.get_existing_data("test_alias")

        assert data.is_empty()
        assert date == SurveyCTOConfig().default_date

    @patch("datasure.connectors.scto.duckdb_get_table")
    def test_get_existing_data_no_submission_date(self, mock_get_table):
        """Test getting existing data without SubmissionDate column."""
        manager = CacheManager("test1234")

        # Mock DataFrame without SubmissionDate column
        mock_get_table.return_value = pl.DataFrame(
            {"name": ["John", "Jane"], "age": [25, 30]}
        )

        data, date = manager.get_existing_data("test_alias")

        assert len(data) == 2
        assert date == SurveyCTOConfig().default_date

    @patch("datasure.connectors.scto.duckdb_get_table")
    def test_get_existing_data_with_submission_date(self, mock_get_table):
        """Test getting existing data with SubmissionDate column."""
        manager = CacheManager("test1234")

        # Mock DataFrame with SubmissionDate column
        mock_get_table.return_value = pl.DataFrame(
            {
                "name": ["John", "Jane"],
                "age": [25, 30],
                "SubmissionDate": [
                    datetime(2024, 1, 15, 10, 30, 0),
                    datetime(2024, 1, 20, 15, 45, 0),
                ],
            }
        )

        data, date = manager.get_existing_data("test_alias")

        assert len(data) == 2
        assert date == datetime(2024, 1, 20, 15, 45, 0)

    @patch("datasure.connectors.scto.duckdb_get_table")
    def test_get_existing_data_exception(self, mock_get_table, caplog):
        """Test getting existing data with exception."""
        manager = CacheManager("test1234")

        # Mock an exception
        mock_get_table.side_effect = Exception("Database error")

        # Should return empty DataFrame and default date on exception
        with pytest.raises(Exception):  # noqa: B017
            _, _ = manager.get_existing_data("test_alias")


class TestDataProcessor:
    """Test DataProcessor class."""

    def test_data_processor_init(self):
        """Test DataProcessor initialization."""
        processor = DataProcessor()
        assert hasattr(processor, "logger")

    def test_get_repeat_fields_empty(self):
        """Test getting repeat fields from empty DataFrame."""
        processor = DataProcessor()
        questions = pl.DataFrame({"type": [], "name": []})

        result = processor.get_repeat_fields(questions)
        assert result == []

    def test_get_repeat_fields_no_repeats(self):
        """Test getting repeat fields with no repeat groups."""
        processor = DataProcessor()
        questions = pl.DataFrame(
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
        questions = pl.DataFrame(
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
        questions = pl.DataFrame(
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
        data = pl.DataFrame(
            {
                "CompletionDate": [
                    "Jan 15, 2024 10:30:00 AM",
                    "Jan 16, 2024 11:30:00 AM",
                ],
                "SubmissionDate": [
                    "Jan 15, 2024 10:30:00 AM",
                    "Jan 16, 2024 11:30:00 AM",
                ],
                "starttime": ["Jan 15, 2024 10:30:00 AM", "Jan 16, 2024 11:30:00 AM"],
                "endtime": ["Jan 15, 2024 12:30:00 PM", "Jan 16, 2024 01:30:00 PM"],
            }
        )
        questions = pl.DataFrame({"type": [], "name": []})

        result = processor.convert_data_types(data, questions)

        assert result["CompletionDate"].dtype in [
            pl.Datetime,
            pl.Datetime("ms"),
            pl.Datetime("us"),
            pl.Datetime("ns"),
        ]
        assert result["SubmissionDate"].dtype in [
            pl.Datetime,
            pl.Datetime("ms"),
            pl.Datetime("us"),
            pl.Datetime("ns"),
        ]
        assert result["starttime"].dtype in [
            pl.Datetime,
            pl.Datetime("ms"),
            pl.Datetime("us"),
            pl.Datetime("ns"),
        ]
        assert result["endtime"].dtype in [
            pl.Datetime,
            pl.Datetime("ms"),
            pl.Datetime("us"),
            pl.Datetime("ns"),
        ]

    def test_convert_data_types_numeric_columns(self):
        """Test converting numeric columns."""
        processor = DataProcessor()
        data = pl.DataFrame({"duration": ["120", "180"], "formdef_version": ["1", "2"]})
        questions = pl.DataFrame({"type": [], "name": []})

        result = processor.convert_data_types(data, questions)

        assert result["duration"].dtype == pl.Float64
        assert result["formdef_version"].dtype == pl.Float64

    def test_convert_data_types_form_based(self):
        """Test converting data types based on form definition."""
        processor = DataProcessor()
        data = pl.DataFrame(
            {
                "age": ["25", "30"],
                "birth_date": ["2000-01-15", "1995-05-20"],
                "survey_time": ["10:30:00", "14:15:00"],
                "notes": ["Note 1", "Note 2"],
            }
        )
        questions = pl.DataFrame(
            {
                "type": ["integer", "date", "time", "note"],
                "name": ["age", "birth_date", "survey_time", "notes"],
            }
        )

        result = processor.convert_data_types(data, questions)

        assert result["age"].dtype == pl.Float64
        assert result["birth_date"].dtype in [
            pl.Datetime,
            pl.Datetime("ms"),
            pl.Datetime("us"),
            pl.Datetime("ns"),
        ]
        assert result["survey_time"].dtype in [
            pl.Datetime,
            pl.Datetime("ms"),
            pl.Datetime("us"),
            pl.Datetime("ns"),
        ]
        assert "notes" not in result.columns  # Note fields are dropped

    def test_convert_data_types_with_repeat_fields(self):
        """Test converting data types with repeat fields."""
        processor = DataProcessor()
        data = pl.DataFrame(
            {"member_age_1": ["25", "30"], "member_age_2": ["28", "35"]}
        )
        questions = pl.DataFrame(
            {
                "type": ["begin repeat", "integer", "end repeat"],
                "name": ["members", "member_age", ""],
            }
        )

        result = processor.convert_data_types(data, questions)

        assert result["member_age_1"].dtype == pl.Float64
        assert result["member_age_2"].dtype == pl.Float64

    def test_convert_data_types_error_handling(self, caplog):
        """Test data type conversion error handling."""
        processor = DataProcessor()
        data = pl.DataFrame({"invalid_date": ["not-a-date", "also-not-date"]})
        questions = pl.DataFrame({"type": ["date"], "name": ["invalid_date"]})

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
        mock_client.download_attachment_from_url.return_value = b"fake_image_content"

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

        # Check that download_attachment_from_url was called with correct parameters
        mock_client.download_attachment_from_url.assert_called_once_with(
            "photo.jpg", private_key=None
        )

    def test_download_single_file_file_exists(self, tmp_path):
        """Test downloading a single file when file already exists."""
        mock_client = Mock()
        config = SurveyCTOConfig()
        downloader = MediaDownloader(mock_client, config)

        media_folder = tmp_path / "media"
        media_folder.mkdir()

        # Create existing file
        existing_file = media_folder / "photo_123456.jpg"
        existing_file.write_bytes(b"existing_content")

        downloader._download_single_file(
            url="photo.jpg",
            submission_key="uuid:123456",
            field_name="photo",
            media_folder=media_folder,
            encryption_key=None,
        )

        # Should not call download_attachment_from_url since file exists
        mock_client.download_attachment_from_url.assert_not_called()

        # File should remain unchanged
        assert existing_file.read_bytes() == b"existing_content"

    def test_download_single_file_with_extension(self, tmp_path):
        """Test downloading a single file that needs extension."""
        mock_client = Mock()
        mock_client.download_attachment_from_url.return_value = b"csv_content"

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
        mock_client.download_attachment_from_url.assert_called_once_with(
            "data", private_key=b"test_key"
        )

    def test_download_media_files_creates_folder(self, tmp_path):
        """Test that download_media_files creates the media folder."""
        mock_client = Mock()
        config = SurveyCTOConfig()
        downloader = MediaDownloader(mock_client, config)

        media_folder = tmp_path / "media" / "subfolder"
        data = pl.DataFrame(schema={"KEY": pl.Utf8, "photo": pl.Utf8})

        downloader.download_media_files(["photo"], data, media_folder, None)

        # Folder should be created
        assert media_folder.exists()
        assert media_folder.is_dir()


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

    @patch("datasure.connectors.scto.SurveyCTOAPIClient")
    @patch("datasure.connectors.scto.st")
    def test_connect_success_with_validation(self, mock_st, mock_api_client_class):
        """Test successful connection with validation."""
        # Setup mocks
        mock_api_instance = Mock()
        mock_api_client_class.return_value = mock_api_instance
        mock_api_instance.list_forms.return_value = [
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

        # Check SurveyCTO API client was created
        mock_api_client_class.assert_called_once()
        mock_api_instance.list_forms.assert_called_once()
        mock_st.success.assert_called()

    @patch("datasure.connectors.scto.SurveyCTOAPIClient")
    @patch("datasure.connectors.scto.st")
    def test_connect_success_no_validation(self, mock_st, mock_api_client_class):
        """Test successful connection without validation."""
        mock_api_instance = Mock()
        mock_api_client_class.return_value = mock_api_instance

        client = SurveyCTOClient("test1234")
        credentials = ServerCredentials(
            server="testserver", user="test@example.com", password="password"
        )

        result = client.connect(credentials, validate_permissions=False)

        assert result["connected"] is True
        assert result["validation_attempted"] is False
        mock_api_instance.list_forms.assert_not_called()
        mock_st.success.assert_called()

    @patch("datasure.connectors.scto.SurveyCTOAPIClient")
    @patch("datasure.connectors.scto.st")
    def test_connect_http_error_401(self, mock_st, mock_api_client_class):
        """Test connection with HTTP 401 error."""
        mock_api_instance = Mock()
        mock_api_client_class.return_value = mock_api_instance

        # Create API error with 401 message
        from datasure.utils.scto_api import SurveyCTOAPIError

        api_error = SurveyCTOAPIError("401 Unauthorized")
        mock_api_instance.list_forms.side_effect = api_error

        mock_st.spinner.return_value.__enter__ = Mock()
        mock_st.spinner.return_value.__exit__ = Mock()

        client = SurveyCTOClient("test1234")
        credentials = ServerCredentials(
            server="testserver", user="test@example.com", password="password"
        )

        with pytest.raises(ConnectionError):
            client.connect(credentials, validate_permissions=True)

    @patch("datasure.connectors.scto.SurveyCTOAPIClient")
    def test_connect_connection_error(self, mock_scto_class):
        """Test connection with network connection error."""
        mock_scto_instance = Mock()
        mock_scto_class.return_value = mock_scto_instance

        from datasure.utils.scto_api import SurveyCTOAPIError

        mock_scto_instance.list_forms.side_effect = SurveyCTOAPIError("connection")

        client = SurveyCTOClient("test1234")
        credentials = ServerCredentials(
            server="testserver", user="test@example.com", password="password"
        )

        with pytest.raises(ConnectionError):
            client.connect(credentials, validate_permissions=True)

    @patch("datasure.connectors.scto.SurveyCTOAPIClient")
    def test_connect_timeout_error(self, mock_scto_class):
        """Test connection with timeout error."""
        mock_scto_instance = Mock()
        mock_scto_class.return_value = mock_scto_instance

        from datasure.utils.scto_api import SurveyCTOAPIError

        mock_scto_instance.list_forms.side_effect = SurveyCTOAPIError("timeout")

        client = SurveyCTOClient("test1234")
        credentials = ServerCredentials(
            server="testserver", user="test@example.com", password="password"
        )

        with pytest.raises(ConnectionError):
            client.connect(credentials, validate_permissions=True)

    @patch("datasure.connectors.scto.SurveyCTOAPIClient")
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
        mock_scto_client.download_form_definition.return_value = form_def

        questions, choices = client.get_form_definition("form123")

        assert len(questions) == 2
        assert list(questions.columns) == ["name", "type", "label"]
        assert questions[0, "name"] == "question1"

        assert len(choices) == 2
        assert list(choices.columns) == ["list name", "name", "label"]
        assert choices[0, "name"] == "red"

    def test_get_form_definition_error(self):
        """Test getting form definition with error."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        from datasure.utils.scto_api import SurveyCTOAPIError

        mock_scto_client.download_form_definition.side_effect = SurveyCTOAPIError(
            "API Error"
        )

        with pytest.raises(SurveyCTOError, match="Failed to get form definition"):
            client.get_form_definition("form123")

    @patch("datasure.connectors.scto.pl.read_csv")
    @patch("datasure.connectors.scto.duckdb_save_table")
    @patch("datasure.connectors.scto.standardize_missing_values")
    def test_import_server_dataset(
        self, mock_standardize, mock_save_table, mock_read_csv
    ):
        """Test importing from server dataset."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        csv_data = b"name,age\nJohn,25\nJane,30"
        mock_scto_client.download_dataset_csv.return_value = csv_data

        mock_df = pl.DataFrame({"name": ["John", "Jane"], "age": [25, 30]})
        mock_read_csv.return_value = mock_df
        mock_standardize.return_value = mock_df

        form_config = FormConfig(
            alias="test_dataset", form_id="dataset123", server="testserver"
        )

        result = client._import_server_dataset(form_config)

        assert result == 2
        mock_scto_client.download_dataset_csv.assert_called_once_with("dataset123")
        mock_read_csv.assert_called_once_with(csv_data)

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

    @patch("datasure.connectors.scto.standardize_missing_values")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_regular_form_with_refresh(self, mock_save_table, mock_standardize):
        """Test importing regular form with refresh=True."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        # Mock form data response
        form_data = [
            {"name": "John", "age": 25, "CompletionDate": "2024-01-15"},
            {"name": "Jane", "age": 30, "CompletionDate": "2024-01-16"},
        ]
        mock_scto_client.download_form_data_json.return_value = form_data

        # Mock form definition
        mock_scto_client.download_form_definition.return_value = {
            "fieldsRowsAndColumns": [
                ["name", "type", "disabled"],
                ["name", "text", "no"],
                ["age", "integer", "no"],
            ],
            "choicesRowsAndColumns": [["list name", "name", "label"]],
        }

        # Mock standardize_missing_values to return the data unchanged
        mock_standardize.side_effect = lambda x: x

        form_config = FormConfig(
            alias="test_form", form_id="form123", server="testserver", refresh=True
        )

        result = client._import_regular_form(form_config)

        assert result == 2
        mock_scto_client.download_form_data_json.assert_called_once()
        mock_save_table.assert_called_once()

    @patch("datasure.connectors.scto.retrieve_scto_credentials")
    @patch("datasure.connectors.scto.SurveyCTOAPIClient")
    def test_import_data_connection_fallback(
        self, mock_scto_class, mock_retrieve_credentials
    ):
        """Test import_data with connection fallback."""
        client = SurveyCTOClient("test1234")

        # Mock credential retrieval
        mock_retrieve_credentials.return_value = {
            "credentials": {"password": "password"}
        }

        # Mock SurveyCTO object creation
        mock_scto_instance = Mock()
        mock_scto_class.return_value = mock_scto_instance

        # Mock _import_regular_form to fail and _import_server_dataset to succeed
        client._import_regular_form = Mock(side_effect=Exception("Not a regular form"))
        client._import_server_dataset = Mock(return_value=5)

        form_config = FormConfig(
            alias="test_form",
            form_id="form123",
            server="testserver",
            username="user@example.com",
        )

        result = client.import_data(form_config)

        assert result == 5
        client._import_regular_form.assert_called_once_with(form_config)
        client._import_server_dataset.assert_called_once_with(form_config)

    @patch("datasure.connectors.scto.retrieve_scto_credentials")
    def test_import_data_missing_credentials(self, mock_retrieve_credentials):
        """Test import_data with missing credentials."""
        client = SurveyCTOClient("test1234")

        # Mock missing credentials
        mock_retrieve_credentials.side_effect = KeyError("No credentials")

        form_config = FormConfig(
            alias="test_form",
            form_id="form123",
            server="testserver",
            username="user@example.com",
        )

        with pytest.raises(KeyError, match="Credentials not found in secure storage"):
            client.import_data(form_config)

    @patch("datasure.connectors.scto.retrieve_scto_credentials")
    @patch("datasure.connectors.scto.SurveyCTOAPIClient")
    def test_import_data_connection_error(
        self, mock_scto_class, mock_retrieve_credentials
    ):
        """Test import_data with connection error."""
        client = SurveyCTOClient("test1234")

        # Mock credential retrieval
        mock_retrieve_credentials.return_value = {
            "credentials": {"password": "password"}
        }

        # Mock API error during client creation
        from datasure.utils.scto_api import SurveyCTOAPIError

        mock_scto_class.side_effect = SurveyCTOAPIError("Connection failed")

        form_config = FormConfig(
            alias="test_form",
            form_id="form123",
            server="testserver",
            username="user@example.com",
        )

        with pytest.raises(ConnectionError):
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

        questions = pl.DataFrame(
            {
                "type": ["text", "image", "audio", "note"],
                "name": ["name", "photo", "voice", "notes"],
            }
        )

        data = pl.DataFrame(
            {"name": ["John"], "photo": ["photo1.jpg"], "voice": ["audio1.wav"]}
        )

        form_config = FormConfig(
            alias="test_form",
            form_id="form123",
            server="testserver",
            save_to=str(tmp_path / "data.csv"),
            private_key="test_key",
        )

        client._download_attachments(
            questions, data, form_config, private_key="test_key"
        )

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

    def test_import_private_key_file_not_exists(self):
        """Test importing private key when file doesn't exist."""
        client = SurveyCTOClient("test1234")

        with pytest.raises(
            SctoValidationError, match="Private key file does not exist or is empty"
        ):
            client._import_private_key("/nonexistent/key.pem")

        with pytest.raises(
            SctoValidationError, match="Private key file does not exist or is empty"
        ):
            client._import_private_key("")

    def test_import_private_key_success(self, tmp_path):
        """Test importing private key successfully."""
        client = SurveyCTOClient("test1234")

        key_file = tmp_path / "test_key.pem"
        key_content = (
            "-----BEGIN RSA PRIVATE KEY"
            + "-----\ntest_key_content\n-----END RSA PRIVATE KEY-----"
        )
        key_file.write_text(key_content)

        result = client._import_private_key(str(key_file))
        assert result == key_content.strip()

    def test_import_private_key_read_error(self, tmp_path):
        """Test importing private key with read error."""
        client = SurveyCTOClient("test1234")

        # Create a file but make it unreadable
        key_file = tmp_path / "unreadable_key.pem"
        key_file.write_text("test")

        with patch("builtins.open", side_effect=OSError("Permission denied")):  # noqa: SIM117
            with pytest.raises(SctoValidationError, match="Failed to read private key"):
                client._import_private_key(str(key_file))


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


class TestMediaDownloaderExtended:
    """Extended tests for MediaDownloader class."""

    @patch("datasure.connectors.scto.st")
    def test_download_field_media_with_progress(self, mock_st, tmp_path):
        """Test downloading field media with progress bar."""
        mock_client = Mock()
        mock_client.download_attachment_from_url.return_value = b"fake_content"

        config = SurveyCTOConfig()
        downloader = MediaDownloader(mock_client, config)

        # Mock progress bar
        mock_progress = Mock()
        mock_st.progress.return_value = mock_progress

        data = pl.DataFrame(
            {"KEY": ["uuid:123", "uuid:456"], "photo": ["photo1.jpg", "photo2.jpg"]}
        )

        media_folder = tmp_path / "media"
        media_folder.mkdir(parents=True, exist_ok=True)

        downloader._download_field_media("photo", data, media_folder, None)

        # Verify progress bar was updated
        assert mock_progress.progress.call_count == 2
        mock_st.progress.assert_called_once()

    def test_download_field_media_empty_data(self):
        """Test downloading field media with empty data."""
        mock_client = Mock()
        config = SurveyCTOConfig()
        downloader = MediaDownloader(mock_client, config)

        data = pl.DataFrame(schema={"KEY": pl.Utf8, "photo": pl.Utf8})
        media_folder = Path("/tmp/media")

        # Should not crash with empty data
        downloader._download_field_media("photo", data, media_folder, None)

        # No attachments should be downloaded
        mock_client.download_attachment_from_url.assert_not_called()

    def test_download_field_media_exception_handling(self, caplog, tmp_path):
        """Test downloading field media with exception handling."""
        mock_client = Mock()
        mock_client.download_attachment_from_url.side_effect = OSError(
            "Download failed"
        )

        config = SurveyCTOConfig()
        downloader = MediaDownloader(mock_client, config)

        data = pl.DataFrame({"KEY": ["uuid:123"], "photo": ["photo1.jpg"]})

        media_folder = tmp_path / "media"
        media_folder.mkdir(parents=True, exist_ok=True)

        # Should handle exception gracefully
        downloader._download_field_media("photo", data, media_folder, None)

        # Exception should be logged (tested via logger behavior)

    def test_download_single_file_exists_skip(self, tmp_path):
        """Test that existing files are skipped during download."""
        mock_client = Mock()
        config = SurveyCTOConfig()
        downloader = MediaDownloader(mock_client, config)

        media_folder = tmp_path / "media"
        media_folder.mkdir()

        # Create existing file
        existing_file = media_folder / "photo_123456.jpg"
        existing_file.write_bytes(b"existing_content")

        downloader._download_single_file(
            url="photo.jpg",
            submission_key="uuid:123456",
            field_name="photo",
            media_folder=media_folder,
            encryption_key=None,
        )

        # Should not call download_attachment_from_url since file exists
        mock_client.download_attachment_from_url.assert_not_called()

        # File content should remain unchanged
        assert existing_file.read_bytes() == b"existing_content"

    def test_download_media_files_multiple_fields(self, tmp_path):
        """Test downloading media files for multiple fields."""
        mock_client = Mock()
        mock_client.download_attachment_from_url.return_value = b"fake_content"

        config = SurveyCTOConfig()
        downloader = MediaDownloader(mock_client, config)

        media_fields = ["photo", "audio"]
        data = pl.DataFrame(
            {"KEY": ["uuid:123"], "photo": ["photo1.jpg"], "audio": ["audio1.wav"]}
        )

        media_folder = tmp_path / "media"

        downloader.download_media_files(media_fields, data, media_folder, None)

        # Check that folder was created
        assert media_folder.exists()

        # Should have processed both fields
        # This is tested indirectly through the folder creation and method calls


class TestValidationErrorClass:
    """Test the ValidationError exception class."""

    def test_validation_error_inheritance(self):
        """Test ValidationError inheritance."""
        error = SctoValidationError("Validation failed")
        assert str(error) == "Validation failed"
        assert isinstance(error, SurveyCTOError)
        assert isinstance(error, Exception)


class TestCacheManagerExtended:
    """Extended tests for CacheManager.get_existing_data date branches."""

    @patch("datasure.connectors.scto.duckdb_get_table")
    def test_get_existing_data_string_date_parseable(self, mock_get_table):
        """Test get_existing_data with a string SubmissionDate that parses as ISO."""
        manager = CacheManager("test1234")
        mock_get_table.return_value = pl.DataFrame(
            {"name": ["John"], "SubmissionDate": ["2024-06-15T10:30:00"]}
        )
        _, date = manager.get_existing_data("alias")
        assert date == datetime(2024, 6, 15, 10, 30, 0)

    @patch("datasure.connectors.scto.duckdb_get_table")
    def test_get_existing_data_string_date_invalid(self, mock_get_table):
        """Test get_existing_data with a string SubmissionDate that fails to parse."""
        manager = CacheManager("test1234")
        mock_get_table.return_value = pl.DataFrame(
            {"name": ["John"], "SubmissionDate": ["not-a-date"]}
        )
        _, date = manager.get_existing_data("alias")
        assert date == SurveyCTOConfig().default_date

    @patch("datasure.connectors.scto.duckdb_get_table")
    def test_get_existing_data_unexpected_date_type(self, mock_get_table):
        """Test get_existing_data with an integer SubmissionDate (unexpected type)."""
        manager = CacheManager("test1234")
        mock_get_table.return_value = pl.DataFrame(
            {"name": ["John"], "SubmissionDate": [20240101]}
        )
        _, date = manager.get_existing_data("alias")
        assert date == SurveyCTOConfig().default_date


class TestDataProcessorExtended:
    """Extended tests for DataProcessor covering the PolarsError branch."""

    def test_convert_column_by_type_polars_error(self):
        """Test that PolarsError is caught and original data is returned."""
        processor = DataProcessor()
        mock_data = Mock(spec=pl.DataFrame)
        mock_data.with_columns.side_effect = pl.exceptions.InvalidOperationError(
            "type mismatch"
        )
        result = processor._convert_column_by_type(mock_data, "date_col", "date")
        assert result is mock_data


class TestSurveyCTOClientExtended:
    """Extended tests for SurveyCTOClient covering previously uncovered paths."""

    @patch("datasure.connectors.scto.st")
    def test_show_connection_status_no_forms(self, mock_st):
        """Test _show_connection_status when the server has no forms."""
        client = SurveyCTOClient("test1234")
        client._show_connection_status([], "testserver")
        mock_st.warning.assert_called_once()

    def test_handle_api_error_generic_fallthrough(self):
        """Test _handle_api_error raises ConnectionError for unrecognised errors."""
        from datasure.utils.scto_api import SurveyCTOAPIError as _SurveyCTOAPIError

        client = SurveyCTOClient("test1234")
        api_err = _SurveyCTOAPIError("some completely unmatched error text")
        with pytest.raises(ConnectionError, match="API error"):
            client._handle_api_error(api_err, "testserver")

    def test_handle_connection_error_generic(self):
        """Test _handle_connection_error for non-server-name errors."""
        client = SurveyCTOClient("test1234")
        error = Exception("Something unexpected went wrong")
        with pytest.raises(ConnectionError, match="Failed to create connection"):
            client._handle_connection_error(error, "testserver")

    def test_import_data_missing_server_raises(self):
        """Test import_data raises ValueError when username is absent."""
        client = SurveyCTOClient("test1234")
        # username defaults to None — triggers the guard at the top of import_data
        form_config = FormConfig(alias="test", form_id="form123", server="testserver")
        with pytest.raises(ValueError, match="Server and username must be provided"):
            client.import_data(form_config)

    @patch("datasure.connectors.scto.standardize_missing_values")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_regular_form_loads_private_key(
        self, mock_save, mock_standardize, tmp_path
    ):
        """Test _import_regular_form passes key file PEM content to the API."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        mock_scto_client.download_form_data_json.return_value = [{"name": "John"}]
        mock_scto_client.download_form_definition.return_value = {
            "fieldsRowsAndColumns": [["name", "type"], ["name", "text"]],
            "choicesRowsAndColumns": [["list name", "name", "label"]],
        }
        mock_standardize.side_effect = lambda x: x

        key_file = tmp_path / "key.pem"
        key_content = (
            "-----BEGIN RSA PRIVATE KEY" + "-----\ntest\n-----END RSA PRIVATE KEY-----"
        )
        key_file.write_text(key_content)

        form_config = FormConfig(
            alias="test_form",
            form_id="form123",
            server="testserver",
            private_key=str(key_file),
        )
        result = client._import_regular_form(form_config)

        assert result == 1
        call_kwargs = mock_scto_client.download_form_data_json.call_args.kwargs
        assert call_kwargs.get("private_key") == key_content.strip()

    @patch("datasure.connectors.scto.standardize_missing_values")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_regular_form_concats_existing_data(
        self, mock_save, mock_standardize
    ):
        """Test _import_regular_form concatenates new rows onto existing data."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        existing_df = pl.DataFrame({"name": ["Alice"], "age": ["20"]})
        client.cache_manager.get_existing_data = Mock(
            return_value=(existing_df, datetime(2024, 1, 1))
        )

        mock_scto_client.download_form_data_json.return_value = [
            {"name": "John", "age": "25"}
        ]
        mock_scto_client.download_form_definition.return_value = {
            "fieldsRowsAndColumns": [["name", "type"], ["name", "text"]],
            "choicesRowsAndColumns": [["list name", "name", "label"]],
        }
        mock_standardize.side_effect = lambda x: x

        form_config = FormConfig(
            alias="test_form",
            form_id="form123",
            server="testserver",
            save_to="/some/path/data.csv",
        )
        result = client._import_regular_form(form_config)

        assert result == 1
        saved_df = mock_save.call_args[0][1]
        assert len(saved_df) == 2

    @patch("datasure.connectors.scto.standardize_missing_values")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_regular_form_filters_disabled_questions(
        self, mock_save, mock_standardize
    ):
        """Test _import_regular_form filters out disabled questions."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        mock_scto_client.download_form_data_json.return_value = [{"name": "John"}]
        mock_scto_client.download_form_definition.return_value = {
            "fieldsRowsAndColumns": [
                ["name", "type", "disabled"],
                ["name", "text", "no"],
                ["hidden_field", "text", "yes"],
            ],
            "choicesRowsAndColumns": [["list name", "name", "label"]],
        }
        mock_standardize.side_effect = lambda x: x

        form_config = FormConfig(
            alias="test_form", form_id="form123", server="testserver"
        )
        result = client._import_regular_form(form_config)

        assert result == 1

    @patch("datasure.connectors.scto.standardize_missing_values")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_regular_form_triggers_attachment_download(
        self, mock_save, mock_standardize, tmp_path
    ):
        """Test _import_regular_form calls _download_attachments when configured."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client
        client._download_attachments = Mock()
        client.cache_manager.get_existing_data = Mock(
            return_value=(pl.DataFrame(), SurveyCTOConfig().default_date)
        )

        mock_scto_client.download_form_data_json.return_value = [
            {"name": "John", "photo": "photo1.jpg"}
        ]
        mock_scto_client.download_form_definition.return_value = {
            "fieldsRowsAndColumns": [
                ["name", "type"],
                ["name", "text"],
                ["photo", "image"],
            ],
            "choicesRowsAndColumns": [["list name", "name", "label"]],
        }
        mock_standardize.side_effect = lambda x: x

        form_config = FormConfig(
            alias="test_form",
            form_id="form123",
            server="testserver",
            save_to=str(tmp_path / "data.csv"),
            attachments=True,
        )
        result = client._import_regular_form(form_config)

        assert result == 1
        client._download_attachments.assert_called_once()

    def test_download_attachments_no_media_fields_skips_download(self, tmp_path):
        """Test _download_attachments does nothing when no media fields exist."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        questions = pl.DataFrame({"type": ["text", "integer"], "name": ["name", "age"]})
        data = pl.DataFrame({"name": ["John"], "age": ["25"]})
        form_config = FormConfig(
            alias="test",
            form_id="form123",
            server="testserver",
            save_to=str(tmp_path / "data.csv"),
        )
        client._download_attachments(questions, data, form_config)
        mock_scto_client.download_attachment_from_url.assert_not_called()


class TestSurveyCTOUIExtended:
    """Tests for SurveyCTOUI helper methods."""

    # --- _validate_private_key_text ---

    def test_validate_private_key_text_valid(self):
        """Test valid PEM key passes validation."""
        ui = SurveyCTOUI("test1234")
        key = (
            "-----BEGIN RSA PRIVATE KEY" + "-----\ntest\n-----END RSA PRIVATE KEY-----"
        )
        assert ui._validate_private_key_text(key) is True

    def test_validate_private_key_text_empty_string(self):
        """Test empty string raises ValidationError."""
        ui = SurveyCTOUI("test1234")
        with pytest.raises(SctoValidationError, match="cannot be empty"):
            ui._validate_private_key_text("")

    def test_validate_private_key_text_none(self):
        """Test None raises ValidationError."""
        ui = SurveyCTOUI("test1234")
        with pytest.raises(SctoValidationError, match="cannot be empty"):
            ui._validate_private_key_text(None)

    def test_validate_private_key_text_wrong_format(self):
        """Test key without PEM headers raises ValidationError."""
        ui = SurveyCTOUI("test1234")
        with pytest.raises(SctoValidationError, match="must start with"):
            ui._validate_private_key_text("this is not a PEM key at all")

    # --- _get_default_form_index ---

    def test_get_default_form_index_found(self):
        """Test returns correct index when form_id is present."""
        ui = SurveyCTOUI("test1234")
        assert (
            ui._get_default_form_index(
                {"form_id": "form2"}, ["form1", "form2", "form3"]
            )
            == 1
        )

    def test_get_default_form_index_not_found(self):
        """Test returns None when form_id is not in the list."""
        ui = SurveyCTOUI("test1234")
        assert (
            ui._get_default_form_index({"form_id": "missing"}, ["form1", "form2"])
            is None
        )

    def test_get_default_form_index_no_defaults(self):
        """Test returns None when defaults dict is empty."""
        ui = SurveyCTOUI("test1234")
        assert ui._get_default_form_index({}, ["form1"]) is None

    # --- _parse_selected_form ---

    @patch("datasure.connectors.scto.st")
    def test_parse_selected_form_with_matching_pattern(self, mock_st):
        """Test parsing a 'form_id (title)' formatted selection."""
        mock_st.expander.return_value.__enter__ = Mock(return_value=None)
        mock_st.expander.return_value.__exit__ = Mock(return_value=False)
        ui = SurveyCTOUI("test1234")
        forms_info = {"forms_list": [("form123", "My Survey", True)]}
        form_options = ["form123 (My Survey)"]
        result = ui._parse_selected_form(
            "form123 (My Survey)", form_options, forms_info
        )
        assert result["form_id"] == "form123"
        assert result["form_title"] == "My Survey"
        assert result["encrypted"] is True

    @patch("datasure.connectors.scto.st")
    def test_parse_selected_form_without_matching_pattern(self, mock_st):
        """Test parsing a bare form_id with no title in parentheses."""
        mock_st.expander.return_value.__enter__ = Mock(return_value=None)
        mock_st.expander.return_value.__exit__ = Mock(return_value=False)
        ui = SurveyCTOUI("test1234")
        forms_info = {"forms_list": [("form123", "title", False)]}
        form_options = ["form123"]
        result = ui._parse_selected_form("form123", form_options, forms_info)
        assert result["form_id"] == "form123"
        assert result["form_title"] == "No title"
        assert result["encrypted"] is False

    # --- _validate_private_key_path ---

    @patch("datasure.connectors.scto.st")
    def test_validate_private_key_path_valid(self, mock_st, tmp_path):
        """Test valid .pem path returns True."""
        ui = SurveyCTOUI("test1234")
        key_file = tmp_path / "key.pem"
        key_file.write_text("test")
        assert ui._validate_private_key_path(str(key_file)) is True
        mock_st.error.assert_not_called()

    @patch("datasure.connectors.scto.st")
    def test_validate_private_key_path_not_exists(self, mock_st):
        """Test non-existent path shows error and returns False."""
        ui = SurveyCTOUI("test1234")
        result = ui._validate_private_key_path("/nonexistent/key.pem")
        assert result is False
        mock_st.error.assert_called_once()

    @patch("datasure.connectors.scto.st")
    def test_validate_private_key_path_wrong_extension(self, mock_st, tmp_path):
        """Test non-.pem file shows error and returns False."""
        ui = SurveyCTOUI("test1234")
        key_file = tmp_path / "key.txt"
        key_file.write_text("test")
        result = ui._validate_private_key_path(str(key_file))
        assert result is False
        mock_st.error.assert_called_once()

    # --- _render_save_file_field ---

    @patch("datasure.connectors.scto.st")
    def test_render_save_file_field_empty_input(self, mock_st):
        """Test that an empty save_file input returns empty string."""
        mock_st.text_input.return_value = ""
        ui = SurveyCTOUI("test1234")
        result = ui._render_save_file_field({})
        assert result == ""

    @patch("datasure.connectors.scto.os")
    @patch("datasure.connectors.scto.st")
    def test_render_save_file_field_file_does_not_exist(self, mock_st, mock_os):
        """Test that a non-existent save_file path is returned as-is."""
        mock_st.text_input.return_value = "/path/to/data.csv"
        mock_os.path.exists.return_value = False
        ui = SurveyCTOUI("test1234")
        result = ui._render_save_file_field({})
        assert result == "/path/to/data.csv"

    @patch("datasure.connectors.scto.st")
    def test_render_save_file_field_existing_valid_path(self, mock_st, tmp_path):
        """Test a valid save path whose parent dir exists is returned as-is."""
        save_file = tmp_path / "data.csv"
        save_file.write_text("col1\nval1")
        mock_st.text_input.return_value = str(save_file)
        ui = SurveyCTOUI("test1234")
        result = ui._render_save_file_field({})
        assert result == str(save_file)

    # --- _get_forms_info ---

    def test_get_forms_info_returns_connection_info(self):
        """Test _get_forms_info delegates to client.connect and returns dict."""
        ui = SurveyCTOUI("test1234")
        ui.client.connect = Mock(
            return_value={
                "connected": True,
                "forms_count": 2,
                "forms_list": [
                    ("form1", "Survey 1", False),
                    ("form2", "Survey 2", True),
                ],
            }
        )
        credentials = ServerCredentials(
            server="testserver", user="user@example.com", password="pass"
        )
        result = ui._get_forms_info(credentials)
        assert result["connected"] is True
        assert result["forms_count"] == 2
        assert len(result["forms_list"]) == 2

    # --- _add_form_to_project ---

    @patch("datasure.connectors.scto.duckdb_save_table")
    @patch("datasure.connectors.scto.duckdb_get_table")
    def test_add_form_to_project_success(self, mock_get_table, mock_save_table):
        """Test _add_form_to_project appends a new row to the import log."""
        ui = SurveyCTOUI("test1234")
        mock_get_table.return_value = pl.DataFrame(
            {
                "alias": ["existing_form"],
                "refresh": [True],
                "load": [True],
                "source": ["SurveyCTO"],
                "filename": [""],
                "sheet_name": [""],
                "server": ["testserver"],
                "username": ["user@example.com"],
                "form_id": ["existing123"],
                "private_key": [""],
                "save_to": [""],
                "attachments": [False],
            }
        )
        form_config = FormConfig(
            alias="new_form", form_id="form123", server="testserver"
        )
        ui._add_form_to_project(form_config)
        mock_save_table.assert_called_once()
        saved_df = mock_save_table.call_args[0][1]
        assert len(saved_df) == 2

    @patch("datasure.connectors.scto.duckdb_get_table")
    def test_add_form_to_project_duplicate_alias_raises(self, mock_get_table):
        """Test _add_form_to_project raises ValidationError for a duplicate alias."""
        ui = SurveyCTOUI("test1234")
        mock_get_table.return_value = pl.DataFrame({"alias": ["existing_form"]})
        form_config = FormConfig(
            alias="existing_form", form_id="form123", server="testserver"
        )
        with pytest.raises(SctoValidationError, match="already exists"):
            ui._add_form_to_project(form_config)

    # --- _update_form_on_project ---

    @patch("datasure.connectors.scto.duckdb_save_table")
    @patch("datasure.connectors.scto.duckdb_get_table")
    def test_update_form_on_project_success(self, mock_get_table, mock_save_table):
        """Test _update_form_on_project updates the matching row in the import log."""
        ui = SurveyCTOUI("test1234")
        mock_get_table.return_value = pl.DataFrame(
            {
                "alias": ["existing_form"],
                "refresh": [True],
                "load": [True],
                "source": ["SurveyCTO"],
                "filename": [""],
                "sheet_name": [""],
                "server": ["oldserver"],
                "form_id": ["oldform"],
                "private_key": [""],
                "save_to": [""],
                "attachments": [False],
            }
        )
        form_config = FormConfig(
            alias="existing_form", form_id="newform", server="newserver"
        )
        ui._update_form_on_project(form_config)
        mock_save_table.assert_called_once()

    @patch("datasure.connectors.scto.duckdb_get_table")
    def test_update_form_on_project_not_found_raises(self, mock_get_table):
        """Test _update_form_on_project raises ValidationError when alias is missing."""
        ui = SurveyCTOUI("test1234")
        mock_get_table.return_value = pl.DataFrame({"alias": ["other_form"]})
        form_config = FormConfig(
            alias="missing_form", form_id="form123", server="testserver"
        )
        with pytest.raises(SctoValidationError, match="does not exist"):
            ui._update_form_on_project(form_config)

    # --- _extract_form_title and helpers ---

    def test_extract_form_title_from_settings(self):
        """Test title is extracted from the settings block."""
        ui = SurveyCTOUI("test1234")
        form_def = {
            "settings": [
                ["form_title", "form_id"],
                ["My Survey", "survey123"],
            ],
            "fieldsRowsAndColumns": [["name", "type"]],
        }
        assert ui._extract_form_title(form_def, "fallback") == "My Survey"

    def test_extract_form_title_falls_back_to_form_id(self):
        """Test form_id is returned when no title can be found."""
        ui = SurveyCTOUI("test1234")
        assert (
            ui._extract_form_title({"fieldsRowsAndColumns": [["name"]]}, "my_form")
            == "my_form"
        )

    def test_extract_form_title_exception_returns_form_id(self):
        """Test form_id is returned when extraction raises an exception."""
        ui = SurveyCTOUI("test1234")
        assert ui._extract_form_title({}, "fallback_id") == "fallback_id"

    def test_extract_title_from_settings_no_key(self):
        """Test returns None when settings key is absent."""
        ui = SurveyCTOUI("test1234")
        assert ui._extract_title_from_settings({}) is None

    def test_extract_title_from_settings_too_short(self):
        """Test returns None when settings list has only one row."""
        ui = SurveyCTOUI("test1234")
        assert ui._extract_title_from_settings({"settings": [["form_title"]]}) is None

    def test_find_title_in_headers_found(self):
        """Test returns title value when a recognised header is present."""
        ui = SurveyCTOUI("test1234")
        result = ui._find_title_in_headers(
            ["form_title", "form_id"], ["My Survey", "id123"]
        )
        assert result == "My Survey"

    def test_find_title_in_headers_not_found(self):
        """Test returns None when no recognised title header is present."""
        ui = SurveyCTOUI("test1234")
        assert ui._find_title_in_headers(["other_col"], ["value"]) is None

    def test_extract_title_from_fields_no_key(self):
        """Test returns None when fieldsRowsAndColumns is absent."""
        ui = SurveyCTOUI("test1234")
        assert ui._extract_title_from_fields({}) is None

    def test_extract_title_from_fields_too_short(self):
        """Test returns None when fieldsRowsAndColumns has only a header row."""
        ui = SurveyCTOUI("test1234")
        assert (
            ui._extract_title_from_fields({"fieldsRowsAndColumns": [["headers"]]})
            is None
        )


class TestDownloadFormsExtended:
    """Extended tests for download_forms covering the all-failures branch."""

    @patch("datasure.connectors.scto.SurveyCTOClient")
    @patch("datasure.connectors.scto.st")
    def test_download_forms_all_failures(self, mock_st, mock_client_class):
        """Test download_forms shows only the failure message when every form fails."""
        mock_client = Mock()
        mock_client_class.return_value = mock_client
        mock_client.import_data.side_effect = Exception("always fails")

        mock_progress = Mock()
        mock_st.progress.return_value = mock_progress

        form_configs = [FormConfig(alias="form1", form_id="f1", server="server1")]
        download_forms("test1234", form_configs)

        success_calls = [
            c
            for c in mock_st.success.call_args_list
            if "Successfully downloaded" in str(c)
        ]
        assert len(success_calls) == 0

        error_calls = [
            c
            for c in mock_st.error.call_args_list
            if "Failed to download" in str(c) and "forms" in str(c)
        ]
        assert len(error_calls) == 1


class TestSurveyCTOUIRendering:
    """Tests for SurveyCTOUI render and submission methods."""

    # --- _render_logo ---

    @patch("datasure.connectors.scto.st")
    def test_render_logo_with_valid_path(self, mock_st, tmp_path):
        """Test _render_logo calls st.image when the logo file exists."""
        logo = tmp_path / "logo.png"
        logo.write_bytes(b"PNG")
        ui = SurveyCTOUI("test1234")
        ui._get_logo_path = Mock(return_value=str(logo))
        ui._render_logo()
        mock_st.image.assert_called_once()

    @patch("datasure.connectors.scto.st")
    def test_render_logo_without_valid_path(self, mock_st):
        """Test _render_logo falls back to st.markdown when logo is absent."""
        ui = SurveyCTOUI("test1234")
        ui._get_logo_path = Mock(return_value=None)
        ui._render_logo()
        mock_st.markdown.assert_called_once()

    # --- _get_server_credentials ---

    @patch("datasure.connectors.scto.list_stored_credentials")
    @patch("datasure.connectors.scto.st")
    def test_get_server_credentials_no_credentials(self, mock_st, mock_list_cred):
        """Test returns None and shows warning when no credentials are stored."""
        mock_list_cred.return_value = {"credentials": {}}
        ui = SurveyCTOUI("test1234")
        result = ui._get_server_credentials()
        assert result is None
        mock_st.warning.assert_called_once()

    @patch("datasure.connectors.scto.list_stored_credentials")
    @patch("datasure.connectors.scto.st")
    def test_get_server_credentials_keyerror_shows_info(self, mock_st, mock_list_cred):
        """Test returns None and shows info when nothing is selected."""
        mock_list_cred.return_value = {
            "credentials": {
                "server1": {"server": "test", "username": "user@example.com"}
            }
        }
        mock_st.selectbox.return_value = None
        ui = SurveyCTOUI("test1234")
        result = ui._get_server_credentials()
        assert result is None
        mock_st.info.assert_called_once()

    @patch("datasure.connectors.scto.retrieve_scto_credentials")
    @patch("datasure.connectors.scto.list_stored_credentials")
    @patch("datasure.connectors.scto.st")
    def test_get_server_credentials_connection_fails(
        self, mock_st, mock_list_cred, mock_retrieve
    ):
        """Test returns None and shows error when server connection fails."""
        mock_list_cred.return_value = {
            "credentials": {
                "server1": {"server": "testserver", "username": "user@example.com"}
            }
        }
        mock_st.selectbox.return_value = "server1"
        mock_retrieve.return_value = {"credentials": {"password": "pass"}}
        ui = SurveyCTOUI("test1234")
        ui.client.connect = Mock(side_effect=ConnectionError("connection refused"))
        result = ui._get_server_credentials()
        assert result is None
        mock_st.error.assert_called_once()

    @patch("datasure.connectors.scto.retrieve_scto_credentials")
    @patch("datasure.connectors.scto.list_stored_credentials")
    @patch("datasure.connectors.scto.st")
    def test_get_server_credentials_success(
        self, mock_st, mock_list_cred, mock_retrieve
    ):
        """Test returns ServerCredentials on a successful connection."""
        mock_list_cred.return_value = {
            "credentials": {
                "server1": {"server": "testserver", "username": "user@example.com"}
            }
        }
        mock_st.selectbox.return_value = "server1"
        mock_retrieve.return_value = {"credentials": {"password": "pass"}}
        ui = SurveyCTOUI("test1234")
        ui.client.connect = Mock(return_value=None)
        result = ui._get_server_credentials()
        assert result is not None
        assert result.server == "testserver"

    # --- _render_form_selection ---

    @patch("datasure.connectors.scto.st")
    def test_render_form_selection_no_form_selected(self, mock_st):
        """Test returns None when the user has not picked a form."""
        mock_st.selectbox.return_value = None
        ui = SurveyCTOUI("test1234")
        ui._get_forms_info = Mock(
            return_value={"forms_list": [("form1", "Survey 1", False)]}
        )
        credentials = ServerCredentials(server="test", user="user@ex.com", password="p")
        result = ui._render_form_selection(credentials, {})
        assert result is None

    @patch("datasure.connectors.scto.st")
    def test_render_form_selection_form_selected(self, mock_st):
        """Test returns form data dict when the user selects a form."""
        mock_st.selectbox.return_value = "form1 (Survey 1)"
        ui = SurveyCTOUI("test1234")
        forms_info = {"forms_list": [("form1", "Survey 1", False)]}
        ui._get_forms_info = Mock(return_value=forms_info)
        ui._parse_selected_form = Mock(
            return_value={
                "form_id": "form1",
                "form_title": "Survey 1",
                "encrypted": False,
            }
        )
        credentials = ServerCredentials(server="test", user="user@ex.com", password="p")
        result = ui._render_form_selection(credentials, {})
        assert result is not None
        assert result["form_id"] == "form1"

    # --- _render_alias_field ---

    @patch("datasure.connectors.scto.st")
    def test_render_alias_field(self, mock_st):
        """Test returns the value from the alias text input."""
        mock_st.text_input.return_value = "my_alias"
        ui = SurveyCTOUI("test1234")
        result = ui._render_alias_field({"form_title": "My Survey"}, {}, False)
        assert result == "my_alias"

    # --- _render_private_key_field ---

    @patch("datasure.connectors.scto.st")
    def test_render_private_key_field_not_encrypted(self, mock_st):
        """Test returns empty string for non-encrypted forms."""
        mock_st.text_input.return_value = ""
        ui = SurveyCTOUI("test1234")
        result = ui._render_private_key_field(False, {}, False)
        assert result == ""

    @patch("datasure.connectors.scto.st")
    def test_render_private_key_field_encrypted_no_file(self, mock_st):
        """Test returns empty string with warning when encrypted and no key given."""
        mock_st.text_input.return_value = ""
        ui = SurveyCTOUI("test1234")
        result = ui._render_private_key_field(True, {}, False)
        assert result == ""
        mock_st.warning.assert_called_once()

    @patch("datasure.connectors.scto.st")
    def test_render_private_key_field_encrypted_invalid_path(self, mock_st):
        """Test returns None when the key path fails validation."""
        mock_st.text_input.return_value = "/nonexistent/key.pem"
        ui = SurveyCTOUI("test1234")
        ui._validate_private_key_path = Mock(return_value=False)
        result = ui._render_private_key_field(True, {}, False)
        assert result is None

    @patch("datasure.connectors.scto.st")
    def test_render_private_key_field_encrypted_valid_path(self, mock_st):
        """Test returns the file path when it passes validation."""
        mock_st.text_input.return_value = "/valid/key.pem"
        ui = SurveyCTOUI("test1234")
        ui._validate_private_key_path = Mock(return_value=True)
        result = ui._render_private_key_field(True, {}, False)
        assert result == "/valid/key.pem"

    # --- _render_config_fields ---

    @patch("datasure.connectors.scto.st")
    def test_render_config_fields_private_key_none(self, mock_st):
        """Test returns None when private key field returns None."""
        ui = SurveyCTOUI("test1234")
        ui._render_alias_field = Mock(return_value="alias")
        ui._render_private_key_field = Mock(return_value=None)
        ui._render_save_file_field = Mock(return_value="/save/path")
        result = ui._render_config_fields({"encrypted": True}, {}, False)
        assert result is None

    @patch("datasure.connectors.scto.st")
    def test_render_config_fields_save_file_none(self, mock_st):
        """Test returns None when save file field returns None."""
        ui = SurveyCTOUI("test1234")
        ui._render_alias_field = Mock(return_value="alias")
        ui._render_private_key_field = Mock(return_value="")
        ui._render_save_file_field = Mock(return_value=None)
        result = ui._render_config_fields({"encrypted": False}, {}, False)
        assert result is None

    @patch("datasure.connectors.scto.st")
    def test_render_config_fields_success(self, mock_st):
        """Test returns the full config dict when all fields are valid."""
        mock_st.checkbox.return_value = True
        mock_st.markdown.return_value = None
        ui = SurveyCTOUI("test1234")
        ui._render_alias_field = Mock(return_value="my_alias")
        ui._render_private_key_field = Mock(return_value="")
        ui._render_save_file_field = Mock(return_value="/save/path")
        result = ui._render_config_fields({"encrypted": False}, {}, False)
        assert result is not None
        assert result["alias"] == "my_alias"
        assert result["attachments"] is True

    # --- _render_save_file_field (parent directory missing) ---

    @patch("datasure.connectors.scto.Path")
    @patch("datasure.connectors.scto.os")
    @patch("datasure.connectors.scto.st")
    def test_render_save_file_field_parent_dir_missing(
        self, mock_st, mock_os, mock_path_cls
    ):
        """Test returns None and shows error when save file parent dir is missing."""
        mock_st.text_input.return_value = "/missing/parent/data.csv"
        mock_os.path.exists.return_value = True
        mock_path_inst = Mock()
        mock_path_cls.return_value = mock_path_inst
        mock_path_inst.parent.exists.return_value = False
        ui = SurveyCTOUI("test1234")
        result = ui._render_save_file_field({})
        assert result is None
        mock_st.error.assert_called_once()

    # --- _handle_form_submission ---

    @patch("datasure.connectors.scto.st")
    def test_handle_form_submission_button_not_clicked(self, mock_st):
        """Test early return when the submit button is not clicked."""
        mock_st.button.return_value = False
        ui = SurveyCTOUI("test1234")
        ui._add_form_to_project = Mock()
        ui._handle_form_submission(
            False,
            ServerCredentials(server="srv", user="u@ex.com", password="p"),
            {"form_id": "f1", "form_title": "Survey", "encrypted": False},
            {
                "alias": "alias",
                "private_key_file": "",
                "save_file": "",
                "attachments": False,
            },
        )
        ui._add_form_to_project.assert_not_called()

    @patch("datasure.connectors.scto.st")
    def test_handle_form_submission_no_alias(self, mock_st):
        """Test shows error and aborts when alias is empty."""
        mock_st.button.return_value = True
        ui = SurveyCTOUI("test1234")
        ui._add_form_to_project = Mock()
        ui._handle_form_submission(
            False,
            ServerCredentials(server="srv", user="u@ex.com", password="p"),
            {"form_id": "f1", "form_title": "Survey", "encrypted": False},
            {
                "alias": "",
                "private_key_file": "",
                "save_file": "",
                "attachments": False,
            },
        )
        mock_st.error.assert_called_once()
        ui._add_form_to_project.assert_not_called()

    @patch("datasure.connectors.scto.st")
    def test_handle_form_submission_no_form_id(self, mock_st):
        """Test shows error and aborts when form_id is empty."""
        mock_st.button.return_value = True
        ui = SurveyCTOUI("test1234")
        ui._add_form_to_project = Mock()
        ui._handle_form_submission(
            False,
            ServerCredentials(server="srv", user="u@ex.com", password="p"),
            {"form_id": "", "form_title": "Survey", "encrypted": False},
            {
                "alias": "my_alias",
                "private_key_file": "",
                "save_file": "",
                "attachments": False,
            },
        )
        mock_st.error.assert_called_once()
        ui._add_form_to_project.assert_not_called()

    @patch("datasure.connectors.scto.st")
    def test_handle_form_submission_add_mode_success(self, mock_st):
        """Test calls _add_form_to_project and triggers rerun in add mode."""
        mock_st.button.return_value = True
        ui = SurveyCTOUI("test1234")
        ui._add_form_to_project = Mock()
        ui._handle_form_submission(
            False,
            ServerCredentials(server="testserver", user="u@ex.com", password="p"),
            {"form_id": "form123", "form_title": "Survey", "encrypted": False},
            {
                "alias": "my_alias",
                "private_key_file": "",
                "save_file": "",
                "attachments": False,
            },
        )
        ui._add_form_to_project.assert_called_once()
        mock_st.success.assert_called_once()
        mock_st.rerun.assert_called_once()

    @patch("datasure.connectors.scto.st")
    def test_handle_form_submission_edit_mode_success(self, mock_st):
        """Test calls _update_form_on_project and triggers rerun in edit mode."""
        mock_st.button.return_value = True
        ui = SurveyCTOUI("test1234")
        ui._update_form_on_project = Mock()
        ui._handle_form_submission(
            True,
            ServerCredentials(server="testserver", user="u@ex.com", password="p"),
            {"form_id": "form123", "form_title": "Survey", "encrypted": False},
            {
                "alias": "my_alias",
                "private_key_file": "",
                "save_file": "",
                "attachments": False,
            },
        )
        ui._update_form_on_project.assert_called_once()
        mock_st.success.assert_called_once()
        mock_st.rerun.assert_called_once()

    @patch("datasure.connectors.scto.st")
    def test_handle_form_submission_exception_shows_error(self, mock_st):
        """Test shows error message and does not rerun when add raises."""
        mock_st.button.return_value = True
        ui = SurveyCTOUI("test1234")
        ui._add_form_to_project = Mock(side_effect=Exception("save failed"))
        ui._handle_form_submission(
            False,
            ServerCredentials(server="testserver", user="u@ex.com", password="p"),
            {"form_id": "form123", "form_title": "Survey", "encrypted": False},
            {
                "alias": "my_alias",
                "private_key_file": "",
                "save_file": "",
                "attachments": False,
            },
        )
        mock_st.error.assert_called_once()
        mock_st.rerun.assert_not_called()

    # --- _get_form_options ---

    @patch("datasure.connectors.scto.st")
    def test_get_form_options_success(self, mock_st):
        """Test returns sorted list of (form_id, title) tuples on success."""
        mock_spinner = Mock()
        mock_spinner.__enter__ = Mock(return_value=None)
        mock_spinner.__exit__ = Mock(return_value=False)
        mock_st.spinner.return_value = mock_spinner
        ui = SurveyCTOUI("test1234")
        ui.client._scto_client = Mock()
        ui.client._scto_client.list_forms.return_value = [
            {"id": "form2", "title": "Survey B"},
            {"id": "form1", "title": "Survey A"},
        ]
        result = ui._get_form_options("testserver")
        assert result is not None
        assert len(result) == 2
        assert result[0] == ("form1", "Survey A")

    @patch("datasure.connectors.scto.st")
    def test_get_form_options_api_error_returns_none(self, mock_st):
        """Test returns None and shows error when list_forms raises an API error."""
        mock_spinner = Mock()
        mock_spinner.__enter__ = Mock(return_value=None)
        mock_spinner.__exit__ = Mock(return_value=False)
        mock_st.spinner.return_value = mock_spinner
        ui = SurveyCTOUI("test1234")
        ui.client._scto_client = Mock()
        ui.client._scto_client.list_forms.side_effect = SurveyCTOAPIError("API error")
        result = ui._get_form_options("testserver")
        assert result is None
        mock_st.error.assert_called_once()

    # --- render_form_config ---

    @patch("datasure.connectors.scto.st")
    def test_render_form_config_no_credentials(self, mock_st):
        """Test exits early when _get_server_credentials returns None."""
        mock_container = Mock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        ui = SurveyCTOUI("test1234")
        ui._render_logo = Mock()
        ui._get_server_credentials = Mock(return_value=None)
        ui.render_form_config()
        ui._get_server_credentials.assert_called_once()

    @patch("datasure.connectors.scto.st")
    def test_render_form_config_no_form_data(self, mock_st):
        """Test exits early when _render_form_selection returns None."""
        mock_container = Mock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        ui = SurveyCTOUI("test1234")
        ui._render_logo = Mock()
        ui._get_server_credentials = Mock(return_value=Mock())
        ui._render_form_selection = Mock(return_value=None)
        ui.render_form_config()
        ui._render_form_selection.assert_called_once()

    @patch("datasure.connectors.scto.st")
    def test_render_form_config_no_config_data(self, mock_st):
        """Test exits early when _render_config_fields returns None."""
        mock_container = Mock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        ui = SurveyCTOUI("test1234")
        ui._render_logo = Mock()
        ui._get_server_credentials = Mock(return_value=Mock())
        ui._render_form_selection = Mock(return_value={"form_id": "f1"})
        ui._render_config_fields = Mock(return_value=None)
        ui.render_form_config()
        ui._render_config_fields.assert_called_once()

    @patch("datasure.connectors.scto.st")
    def test_render_form_config_full_path(self, mock_st):
        """Test reaches _handle_form_submission when all steps succeed."""
        mock_container = Mock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        ui = SurveyCTOUI("test1234")
        credentials = Mock()
        form_data = {"form_id": "f1", "form_title": "Survey"}
        config_data = {
            "alias": "a",
            "private_key_file": "",
            "save_file": "",
            "attachments": False,
        }
        ui._render_logo = Mock()
        ui._get_server_credentials = Mock(return_value=credentials)
        ui._render_form_selection = Mock(return_value=form_data)
        ui._render_config_fields = Mock(return_value=config_data)
        ui._handle_form_submission = Mock()
        ui.render_form_config()
        ui._handle_form_submission.assert_called_once()

    # --- _extract_form_title exception handler ---

    def test_extract_form_title_exception_in_settings(self):
        """Test returns form_id when settings extraction raises."""
        ui = SurveyCTOUI("test1234")
        ui._extract_title_from_settings = Mock(side_effect=AttributeError("attr error"))
        result = ui._extract_form_title({}, "fallback_id")
        assert result == "fallback_id"

    def test_extract_form_title_from_fields_fallback(self):
        """Test returns title when _extract_title_from_fields finds one."""
        ui = SurveyCTOUI("test1234")
        ui._extract_title_from_settings = Mock(return_value=None)
        ui._extract_title_from_fields = Mock(return_value="Field Title")
        result = ui._extract_form_title({}, "fallback_id")
        assert result == "Field Title"

    # --- _find_title_in_headers: value present but falsy ---

    def test_find_title_in_headers_empty_value_continues(self):
        """Test returns None when header is present but data value is empty."""
        ui = SurveyCTOUI("test1234")
        result = ui._find_title_in_headers(["form_title", "other"], ["", "something"])
        assert result is None

    # --- _extract_title_from_fields: loop body executed ---

    def test_extract_title_from_fields_with_multiple_rows(self):
        """Test loop runs over rows but returns None (heuristic never matches)."""
        ui = SurveyCTOUI("test1234")
        form_def = {
            "fieldsRowsAndColumns": [
                ["name", "type"],
                ["field_a", "text"],
                ["field_b", "integer"],
            ]
        }
        result = ui._extract_title_from_fields(form_def)
        assert result is None

    # --- import_data when _scto_client is already set (covers 607->632) ---

    @patch("datasure.connectors.scto.standardize_missing_values")
    @patch("datasure.connectors.scto.duckdb_save_table")
    def test_import_data_with_preconfigured_client(self, mock_save, mock_standardize):
        """Test import_data skips connection setup when _scto_client is pre-set."""
        client = SurveyCTOClient("test1234")
        mock_scto_client = Mock()
        client._scto_client = mock_scto_client

        mock_scto_client.download_form_data_json.return_value = [{"name": "Alice"}]
        mock_scto_client.download_form_definition.return_value = {
            "fieldsRowsAndColumns": [["name", "type"], ["name", "text"]],
            "choicesRowsAndColumns": [["list name", "name", "label"]],
        }
        mock_standardize.side_effect = lambda x: x

        form_config = FormConfig(
            alias="test_form", form_id="form123", server="testserver"
        )
        result = client.import_data(form_config)
        assert result == 1
