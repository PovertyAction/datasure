"""Tests for the SurveyCTO API client module."""

from unittest.mock import MagicMock, Mock, patch  # noqa: F401

import pytest
import requests

from datasure.utils.scto_api import (
    SurveyCTOAPIClient,
    SurveyCTOAPIConfig,
    SurveyCTOAPIError,
)


@pytest.fixture
def api_config():
    """Create a test API configuration."""
    return SurveyCTOAPIConfig(
        server_name="testserver",
        username="testuser",
        password="testpass",
        timeout=30,
        max_retries=3,
        verify_ssl=True,
    )


@pytest.fixture
def api_client(api_config):
    """Create a test API client."""
    return SurveyCTOAPIClient(api_config)


class TestSurveyCTOAPIConfig:
    """Test the SurveyCTOAPIConfig dataclass."""

    def test_config_initialization(self):
        """Test config initialization with required parameters."""
        config = SurveyCTOAPIConfig(
            server_name="myserver", username="user", password="pass"
        )

        assert config.server_name == "myserver"
        assert config.username == "user"
        assert config.password == "pass"
        assert config.timeout == 30  # Default value
        assert config.max_retries == 3  # Default value
        assert config.verify_ssl is True  # Default value

    def test_config_with_custom_values(self):
        """Test config initialization with custom values."""
        config = SurveyCTOAPIConfig(
            server_name="custom",
            username="customuser",
            password="custompass",
            timeout=60,
            max_retries=5,
            verify_ssl=False,
        )

        assert config.timeout == 60
        assert config.max_retries == 5
        assert config.verify_ssl is False

    def test_base_url_property(self, api_config):
        """Test base_url property generation."""
        expected_url = "https://testserver.surveycto.com/api/v2"
        assert api_config.base_url == expected_url


class TestSurveyCTOAPIError:
    """Test the SurveyCTOAPIError exception."""

    def test_error_creation(self):
        """Test error exception creation."""
        error = SurveyCTOAPIError("Test error message")
        assert str(error) == "Test error message"

    def test_error_inheritance(self):
        """Test that SurveyCTOAPIError inherits from Exception."""
        error = SurveyCTOAPIError("Test")
        assert isinstance(error, Exception)


class TestSurveyCTOAPIClient:
    """Test the SurveyCTOAPIClient class."""

    def test_client_initialization(self, api_config):
        """Test client initialization."""
        client = SurveyCTOAPIClient(api_config)

        assert client.config == api_config
        assert client.session is not None
        assert client.logger is not None

    def test_create_session(self, api_client):
        """Test session creation with authentication."""
        session = api_client.session

        assert session.auth is not None
        assert session.auth.username == "testuser"
        assert session.auth.password == "testpass"
        assert session.verify is True

    def test_context_manager_enter(self, api_client):
        """Test context manager entry."""
        with api_client as client:
            assert client == api_client

    def test_context_manager_exit(self, api_client):
        """Test context manager exit and cleanup."""
        with patch.object(api_client.session, "close") as mock_close:
            with api_client:
                pass
            mock_close.assert_called_once()

    def test_close_method(self, api_client):
        """Test close method."""
        with patch.object(api_client.session, "close") as mock_close:
            api_client.close()
            mock_close.assert_called_once()

    def test_close_method_no_session(self, api_client):
        """Test close method when session is None."""
        api_client.session = None
        # Should not raise an error
        api_client.close()


class TestMakeRequest:
    """Test the _make_request method."""

    def test_successful_get_request(self, api_client):
        """Test successful GET request."""
        mock_response = Mock()
        mock_response.json.return_value = {"data": "test"}

        with patch.object(
            api_client.session, "request", return_value=mock_response
        ) as mock_request:
            result = api_client._make_request("GET", "/test", params={"key": "value"})

            mock_request.assert_called_once_with(
                method="GET",
                url="https://testserver.surveycto.com/api/v2/test",
                params={"key": "value"},
                json=None,
                timeout=30,
                stream=False,
            )
            assert result == mock_response

    def test_successful_post_request(self, api_client):
        """Test successful POST request with JSON data."""
        mock_response = Mock()

        with patch.object(
            api_client.session, "request", return_value=mock_response
        ) as mock_request:
            api_client._make_request(
                "POST", "/test", json_data={"field": "value"}, stream=True
            )

            mock_request.assert_called_once_with(
                method="POST",
                url="https://testserver.surveycto.com/api/v2/test",
                params=None,
                json={"field": "value"},
                timeout=30,
                stream=True,
            )

    def test_http_error(self, api_client):
        """Test handling of HTTP errors."""
        mock_response = Mock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            "404 Not Found"
        )

        with patch.object(api_client.session, "request", return_value=mock_response):  # noqa: SIM117
            with pytest.raises(SurveyCTOAPIError, match="API request failed"):
                api_client._make_request("GET", "/test")

    def test_connection_error(self, api_client):
        """Test handling of connection errors."""
        with patch.object(  # noqa: SIM117
            api_client.session,
            "request",
            side_effect=requests.exceptions.ConnectionError("Connection failed"),
        ):
            with pytest.raises(SurveyCTOAPIError, match="Connection failed"):
                api_client._make_request("GET", "/test")

    def test_timeout_error(self, api_client):
        """Test handling of timeout errors."""
        with patch.object(  # noqa: SIM117
            api_client.session,
            "request",
            side_effect=requests.exceptions.Timeout("Request timeout"),
        ):
            with pytest.raises(SurveyCTOAPIError, match="Request timeout"):
                api_client._make_request("GET", "/test")

    def test_unexpected_error(self, api_client):
        """Test handling of unexpected errors."""
        with patch.object(  # noqa: SIM117
            api_client.session,
            "request",
            side_effect=ValueError("Unexpected error"),
        ):
            with pytest.raises(SurveyCTOAPIError, match="Unexpected error"):
                api_client._make_request("GET", "/test")


class TestDatasetEndpoints:
    """Test dataset-related endpoints."""

    def test_list_datasets(self, api_client):
        """Test listing all datasets."""
        expected_data = [
            {"id": "dataset1", "name": "Dataset 1"},
            {"id": "dataset2", "name": "Dataset 2"},
        ]

        with patch.object(api_client, "_make_request") as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = expected_data
            mock_request.return_value = mock_response

            result = api_client.list_datasets()

            mock_request.assert_called_once_with("GET", "/datasets")
            assert result == expected_data

    def test_get_dataset_info(self, api_client):
        """Test getting dataset information."""
        expected_data = {"id": "dataset1", "name": "Dataset 1", "rows": 100}

        with patch.object(api_client, "_make_request") as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = expected_data
            mock_request.return_value = mock_response

            result = api_client.get_dataset_info("dataset1")

            mock_request.assert_called_once_with("GET", "/datasets/dataset1")
            assert result == expected_data

    def test_download_dataset_csv(self, api_client):
        """Test downloading dataset in CSV format."""
        csv_content = b"id,name,value\n1,test,100"

        with patch.object(api_client, "_make_request") as mock_request:
            mock_response = Mock()
            mock_response.content = csv_content
            mock_request.return_value = mock_response

            result = api_client.download_dataset_csv(
                "dataset1", params={"date": "2024-01-01"}
            )

            mock_request.assert_called_once_with(
                "GET",
                "/datasets/data/csv/dataset1",
                params={"date": "2024-01-01"},
                stream=True,
            )
            assert result == csv_content


class TestFormEndpoints:
    """Test form-related endpoints."""

    def test_list_form_ids(self, api_client):
        """Test listing all form IDs."""
        expected_ids = ["form1", "form2", "form3"]

        with patch.object(api_client, "_make_request") as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = expected_ids
            mock_request.return_value = mock_response

            result = api_client.list_form_ids()

            mock_request.assert_called_once_with("GET", "/forms/ids")
            assert result == expected_ids

    def test_download_form_data_json_unencrypted(self, api_client):
        """Test downloading unencrypted form data in JSON format."""
        expected_data = {
            "submissions": [
                {"id": 1, "name": "Test 1"},
                {"id": 2, "name": "Test 2"},
            ]
        }

        with patch.object(api_client, "_make_request") as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = expected_data
            mock_request.return_value = mock_response

            result = api_client.download_form_data_json(
                "form1", params={"date": "2024-01-01"}
            )

            mock_request.assert_called_once_with(
                "GET", "/forms/data/wide/json/form1", params={"date": "2024-01-01"}
            )
            assert result == expected_data

    def test_download_form_data_json_encrypted(self, api_client):
        """Test downloading encrypted form data with private key."""
        expected_data = {
            "submissions": [
                {"id": 1, "name": "Test 1"},
            ]
        }
        private_key = b"test_private_key_content"

        with patch.object(api_client.session, "post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = expected_data
            mock_post.return_value = mock_response

            result = api_client.download_form_data_json(
                "form1", params={"date": "2024-01-01"}, private_key=private_key
            )

            expected_url = "https://testserver.surveycto.com/api/v2/forms/data/wide/json/form1"
            mock_post.assert_called_once_with(
                expected_url,
                files={"private_key": private_key},
                params={"date": "2024-01-01"},
                timeout=30,
            )
            assert result == expected_data

    def test_download_form_data_json_encrypted_http_error(self, api_client):
        """Test downloading encrypted form data with HTTP error."""
        with patch.object(api_client.session, "post") as mock_post:
            mock_response = Mock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                "403"
            )
            mock_post.return_value = mock_response

            with pytest.raises(SurveyCTOAPIError, match="Failed to download form data"):
                api_client.download_form_data_json(
                    "form1", private_key=b"test_key"
                )

    def test_download_form_data_json_encrypted_connection_error(self, api_client):
        """Test downloading encrypted form data with connection error."""
        with patch.object(  # noqa: SIM117
            api_client.session,
            "post",
            side_effect=requests.exceptions.ConnectionError("Connection error"),
        ):
            with pytest.raises(SurveyCTOAPIError, match="Connection failed"):
                api_client.download_form_data_json(
                    "form1", private_key=b"test_key"
                )

    def test_download_form_data_json_encrypted_timeout_error(self, api_client):
        """Test downloading encrypted form data with timeout error."""
        with patch.object(  # noqa: SIM117
            api_client.session,
            "post",
            side_effect=requests.exceptions.Timeout("Timeout"),
        ):
            with pytest.raises(SurveyCTOAPIError, match="Request timeout"):
                api_client.download_form_data_json(
                    "form1", private_key=b"test_key"
                )

    def test_download_form_data_json_encrypted_unexpected_error(self, api_client):
        """Test downloading encrypted form data with unexpected error."""
        with patch.object(  # noqa: SIM117
            api_client.session, "post", side_effect=RuntimeError("Unexpected")
        ):
            with pytest.raises(SurveyCTOAPIError, match="Unexpected error"):
                api_client.download_form_data_json(
                    "form1", private_key=b"test_key"
                )


class TestSubmissionEndpoints:
    """Test submission-related endpoints."""

    def test_download_attachment_from_url_unencrypted(self, api_client):
        """Test downloading attachment from URL without encryption."""
        attachment_content = b"url file content"
        url = "https://testserver.surveycto.com/api/v2/attachments/file.pdf"

        with patch.object(api_client.session, "get") as mock_get:
            mock_response = Mock()
            mock_response.content = attachment_content
            mock_get.return_value = mock_response

            result = api_client.download_attachment_from_url(url)

            mock_get.assert_called_once_with(url, timeout=30, stream=True)
            assert result == attachment_content

    def test_download_attachment_from_url_encrypted(self, api_client):
        """Test downloading attachment from URL with encryption."""
        attachment_content = b"encrypted url file content"
        private_key = b"private_key"
        url = "https://testserver.surveycto.com/api/v2/attachments/encrypted.pdf"

        with patch.object(api_client.session, "post") as mock_post:
            mock_response = Mock()
            mock_response.content = attachment_content
            mock_post.return_value = mock_response

            result = api_client.download_attachment_from_url(url, private_key=private_key)

            mock_post.assert_called_once_with(
                url,
                files={"private_key": private_key},
                timeout=30,
                stream=True,
            )
            assert result == attachment_content

    def test_download_attachment_from_url_http_error(self, api_client):
        """Test downloading from URL with HTTP error."""
        url = "https://testserver.surveycto.com/api/v2/attachments/file.pdf"

        with patch.object(api_client.session, "get") as mock_get:
            mock_response = Mock()
            mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(
                "404"
            )
            mock_get.return_value = mock_response

            with pytest.raises(SurveyCTOAPIError, match="Failed to download from URL"):
                api_client.download_attachment_from_url(url)

    def test_download_attachment_from_url_connection_error(self, api_client):
        """Test downloading from URL with connection error."""
        url = "https://testserver.surveycto.com/api/v2/attachments/file.pdf"

        with patch.object(  # noqa: SIM117
            api_client.session,
            "get",
            side_effect=requests.exceptions.ConnectionError("Connection error"),
        ):
            with pytest.raises(SurveyCTOAPIError, match="Connection failed"):
                api_client.download_attachment_from_url(url)

    def test_download_attachment_from_url_timeout_error(self, api_client):
        """Test downloading from URL with timeout error."""
        url = "https://testserver.surveycto.com/api/v2/attachments/file.pdf"

        with patch.object(  # noqa: SIM117
            api_client.session,
            "get",
            side_effect=requests.exceptions.Timeout("Timeout"),
        ):
            with pytest.raises(SurveyCTOAPIError, match="Request timeout"):
                api_client.download_attachment_from_url(url)

    def test_download_attachment_from_url_unexpected_error(self, api_client):
        """Test downloading from URL with unexpected error."""
        url = "https://testserver.surveycto.com/api/v2/attachments/file.pdf"

        with patch.object(  # noqa: SIM117
            api_client.session, "get", side_effect=RuntimeError("Unexpected")
        ):
            with pytest.raises(SurveyCTOAPIError, match="Unexpected error"):
                api_client.download_attachment_from_url(url)


class TestIntegration:
    """Integration tests for SurveyCTO API client."""

    def test_full_workflow_with_context_manager(self, api_config):
        """Test full workflow using context manager."""
        with SurveyCTOAPIClient(api_config) as client:
            assert client.config == api_config
            assert client.session is not None

            # Mock a successful request
            with patch.object(client, "_make_request") as mock_request:
                mock_response = Mock()
                mock_response.json.return_value = ["form1", "form2"]
                mock_request.return_value = mock_response

                forms = client.list_form_ids()
                assert forms == ["form1", "form2"]

    def test_multiple_api_calls(self, api_client):
        """Test multiple API calls in sequence."""
        with patch.object(api_client, "_make_request") as mock_request:
            # First call - list datasets
            mock_response1 = Mock()
            mock_response1.json.return_value = [{"id": "dataset1"}]

            # Second call - list form IDs
            mock_response2 = Mock()
            mock_response2.json.return_value = ["form1"]

            # Third call - download dataset
            mock_response3 = Mock()
            mock_response3.content = b"csv,data"

            mock_request.side_effect = [mock_response1, mock_response2, mock_response3]

            # Execute calls
            datasets = api_client.list_datasets()
            forms = api_client.list_form_ids()
            csv_data = api_client.download_dataset_csv("dataset1")

            assert datasets == [{"id": "dataset1"}]
            assert forms == ["form1"]
            assert csv_data == b"csv,data"
            assert mock_request.call_count == 3

    def test_encrypted_and_unencrypted_downloads(self, api_client):
        """Test mixing encrypted and unencrypted downloads."""
        # Download unencrypted form data
        with patch.object(api_client, "_make_request") as mock_request:
            mock_response = Mock()
            mock_response.json.return_value = {"data": "unencrypted"}
            mock_request.return_value = mock_response

            unencrypted_data = api_client.download_form_data_json("form1")
            assert unencrypted_data == {"data": "unencrypted"}

        # Download encrypted form data
        with patch.object(api_client.session, "post") as mock_post:
            mock_response = Mock()
            mock_response.json.return_value = {"data": "encrypted"}
            mock_post.return_value = mock_response

            encrypted_data = api_client.download_form_data_json(
                "form2", private_key=b"key"
            )
            assert encrypted_data == {"data": "encrypted"}
