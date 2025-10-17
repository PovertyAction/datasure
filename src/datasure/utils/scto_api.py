import logging
from dataclasses import dataclass
from typing import Any

import requests
from requests.auth import HTTPBasicAuth


@dataclass
class SurveyCTOAPIConfig:
    """Configuration for SurveyCTO API v2 client."""

    server_name: str
    username: str
    password: str
    timeout: int = 30
    max_retries: int = 3
    verify_ssl: bool = True

    @property
    def base_url(self) -> str:
        """Get base URL for API requests."""
        return f"https://{self.server_name}.surveycto.com/api/v2"


class SurveyCTOAPIError(Exception):
    """Base exception for SurveyCTO API errors."""

    pass


class SurveyCTOAPIClient:
    """Client for interacting with SurveyCTO Server API v2.

    This client provides methods for accessing datasets, forms, submissions,
    and other server resources through the SurveyCTO API v2.

    Attributes
    ----------
        config: Configuration object containing server and authentication details
        logger: Logger instance for debugging and error tracking
    """

    def __init__(self, config: SurveyCTOAPIConfig):
        """Initialize the SurveyCTO API client.

        Parameters
        ----------
            config: Configuration object with server details and credentials
        """
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.session = self._create_session()

    def _create_session(self) -> requests.Session:
        """Create and configure a requests session with authentication."""
        session = requests.Session()
        session.auth = HTTPBasicAuth(self.config.username, self.config.password)
        session.verify = self.config.verify_ssl
        return session

    def _make_request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        json_data: dict[str, Any] | None = None,
        stream: bool = False,
    ) -> requests.Response:
        """Make an HTTP request to the SurveyCTO API.

        Parameters
        ----------
            method: HTTP method (GET, POST, PUT, DELETE, PATCH)
            endpoint: API endpoint path (e.g., '/datasets')
            params: Query parameters for the request
            json_data: JSON payload for POST/PUT/PATCH requests
            stream: Whether to stream the response

        Returns
        -------
            Response object from the API

        Raises
        ------
            SurveyCTOAPIError: If the request fails
        """
        url = f"{self.config.base_url}{endpoint}"

        try:
            response = self.session.request(
                method=method,
                url=url,
                params=params,
                json=json_data,
                timeout=self.config.timeout,
                stream=stream,
            )
            response.raise_for_status()
            return response  # noqa: TRY300

        except requests.exceptions.HTTPError as e:
            self.logger.exception(f"HTTP error for {method} {url}")
            raise SurveyCTOAPIError(f"API request failed: {e}") from e

        except requests.exceptions.ConnectionError as e:
            self.logger.exception(f"Connection error for {method} {url}")
            raise SurveyCTOAPIError(f"Connection failed: {e}") from e

        except requests.exceptions.Timeout as e:
            self.logger.exception(f"Timeout for {method} {url}")
            raise SurveyCTOAPIError(f"Request timeout: {e}") from e

        except Exception as e:
            self.logger.exception(f"Unexpected error for {method} {url}")
            raise SurveyCTOAPIError(f"Unexpected error: {e}") from e

    # --- Datasets Endpoints --- #

    def list_datasets(self) -> list[dict[str, Any]]:
        """List all datasets on the server.

        Returns
        -------
            List of dataset information dictionaries
        """
        response = self._make_request("GET", "/datasets")
        return response.json()

    def get_dataset_info(self, dataset_id: str) -> dict[str, Any]:
        """Get information about a specific dataset.

        Parameters
        ----------
            dataset_id: Unique identifier for the dataset

        Returns
        -------
            Dataset information dictionary
        """
        response = self._make_request("GET", f"/datasets/{dataset_id}")
        return response.json()

    def download_dataset_csv(
        self, dataset_id: str, params: dict[str, Any] | None = None
    ) -> bytes:
        """Download dataset data in CSV format.

        Parameters
        ----------
            dataset_id: Unique identifier for the dataset
            params: Optional query parameters for filtering data

        Returns
        -------
            CSV data as bytes
        """
        response = self._make_request(
            "GET", f"/datasets/data/csv/{dataset_id}", params=params, stream=True
        )
        return response.content

    # --- Forms Endpoints --- #

    def list_form_ids(self) -> list[str]:
        """List all form IDs on the server.

        Returns
        -------
            List of form ID strings
        """
        response = self._make_request("GET", "/forms/ids")
        return response.json()

    def list_forms(self) -> list[dict[str, Any]]:
        """List all live forms on the server with their metadata.

        Returns
        -------
            List of dictionaries, each containing information for a form.
            Includes only the most recent versions of forms.

        Raises
        ------
            SurveyCTOAPIError: If the request fails

        Notes
        -----
            This uses the /console/forms-groups-datasets/get endpoint
            and requires CSRF token authentication.
        """
        headers = self._get_csrf_auth_headers()
        url = (
            f"https://{self.config.server_name}.surveycto.com/"
            "console/forms-groups-datasets/get"
        )

        try:
            response = self.session.get(
                url,
                cookies=self.session.cookies,
                headers=headers,
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            return response.json()["forms"]

        except requests.exceptions.HTTPError as e:
            self.logger.exception(f"HTTP error listing forms from {url}")
            raise SurveyCTOAPIError(f"Failed to list forms: {e}") from e

        except requests.exceptions.ConnectionError as e:
            self.logger.exception(f"Connection error listing forms from {url}")
            raise SurveyCTOAPIError(f"Connection failed: {e}") from e

        except requests.exceptions.Timeout as e:
            self.logger.exception(f"Timeout listing forms from {url}")
            raise SurveyCTOAPIError(f"Request timeout: {e}") from e

        except KeyError as e:
            self.logger.exception("'forms' key not found in response")
            raise SurveyCTOAPIError(f"Invalid response format: {e}") from e

        except Exception as e:
            self.logger.exception(f"Unexpected error listing forms from {url}")
            raise SurveyCTOAPIError(f"Unexpected error: {e}") from e

    def _get_csrf_auth_headers(self) -> dict[str, str]:
        """Authenticate and get CSRF token headers for form design endpoints.

        Returns
        -------
            Dictionary containing X-csrf-token and X-OpenRosa-Version headers

        Raises
        ------
            SurveyCTOAPIError: If authentication fails
        """
        base_url = f"https://{self.config.server_name}.surveycto.com"

        try:
            # Get initial CSRF token with OpenRosa header
            initial_headers = {"X-OpenRosa-Version": "1.0"}
            response = self.session.head(
                base_url, headers=initial_headers, timeout=self.config.timeout
            )
            response.raise_for_status()

            headers = {
                "X-csrf-token": response.headers["X-csrf-token"],
                "X-OpenRosa-Version": "1.0",
            }

            # Authenticate and get new CSRF token
            auth_response = self.session.post(
                f"{base_url}/login",
                cookies=self.session.cookies,
                headers=headers,
                timeout=self.config.timeout,
            )
            auth_response.raise_for_status()

            # Update headers with new CSRF token
            headers["X-csrf-token"] = auth_response.headers["X-csrf-token"]

            return headers  # noqa: TRY300

        except requests.exceptions.HTTPError as e:
            self.logger.exception(
                f"HTTP error during CSRF authentication to {base_url}"
            )
            raise SurveyCTOAPIError(f"CSRF authentication failed: {e}") from e

        except requests.exceptions.ConnectionError as e:
            self.logger.exception(
                f"Connection error during CSRF authentication to {base_url}"
            )
            raise SurveyCTOAPIError(f"Connection failed: {e}") from e

        except requests.exceptions.Timeout as e:
            self.logger.exception(f"Timeout during CSRF authentication to {base_url}")
            raise SurveyCTOAPIError(f"Request timeout: {e}") from e

        except KeyError as e:
            self.logger.exception("X-csrf-token header not found in response")
            raise SurveyCTOAPIError(f"CSRF token not found: {e}") from e

        except Exception as e:
            self.logger.exception(
                f"Unexpected error during CSRF authentication to {base_url}"
            )
            raise SurveyCTOAPIError(f"Unexpected error: {e}") from e

    def download_form_definition(self, form_id: str) -> dict[str, Any]:
        """Download form definition (design) from SurveyCTO.

        Parameters
        ----------
            form_id: Form identifier

        Returns
        -------
            Form definition data as dictionary

        Raises
        ------
            SurveyCTOAPIError: If the request fails

        Notes
        -----
            This uses the /forms/{form_id}/design/ endpoint to retrieve
            form structure, questions, and metadata. Requires CSRF token
            authentication.
        """
        headers = self._get_csrf_auth_headers()
        url = f"https://{self.config.server_name}.surveycto.com/forms/{form_id}/design/"

        try:
            response = self.session.get(
                url,
                cookies=self.session.cookies,
                headers=headers,
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            self.logger.exception(f"HTTP error downloading form definition from {url}")
            raise SurveyCTOAPIError(f"Failed to download form definition: {e}") from e

        except requests.exceptions.ConnectionError as e:
            self.logger.exception(
                f"Connection error downloading form definition from {url}"
            )
            raise SurveyCTOAPIError(f"Connection failed: {e}") from e

        except requests.exceptions.Timeout as e:
            self.logger.exception(f"Timeout downloading form definition from {url}")
            raise SurveyCTOAPIError(f"Request timeout: {e}") from e

        except Exception as e:
            self.logger.exception(
                f"Unexpected error downloading form definition from {url}"
            )
            raise SurveyCTOAPIError(f"Unexpected error: {e}") from e

    def download_form_data_json(
        self,
        form_id: str,
        params: dict[str, Any] | None = None,
        private_key: bytes | str | None = None,
    ) -> dict[str, Any]:
        """Download form data in JSON wide format.

        Parameters
        ----------
            form_id: Form identifier
            params: Optional query parameters (e.g., date filters)
            private_key: Private key for decrypting encrypted form data.
                Can be provided as bytes or string. Only supported for JSON format.

        Returns
        -------
            Form data in JSON wide format

        Raises
        ------
            SurveyCTOAPIError: If the request fails

        Notes
        -----
            When downloading encrypted forms, the private_key parameter must be
            provided. The private key is uploaded as a file to the server
            for decryption.
        """
        endpoint = f"/forms/data/wide/json/{form_id}"
        url = f"{self.config.base_url}{endpoint}"

        try:
            if private_key is None:
                # Standard GET request for unencrypted data
                response = self._make_request("GET", endpoint, params=params)
                return response.json()
            # POST request with private key file for encrypted data
            files = {"private_key": private_key}
            response = self.session.post(
                url,
                files=files,
                params=params,
                timeout=self.config.timeout,
            )
            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            self.logger.exception(f"HTTP error downloading form data from {url}")
            raise SurveyCTOAPIError(f"Failed to download form data: {e}") from e

        except requests.exceptions.ConnectionError as e:
            self.logger.exception(f"Connection error downloading form data from {url}")
            raise SurveyCTOAPIError(f"Connection failed: {e}") from e

        except requests.exceptions.Timeout as e:
            self.logger.exception(f"Timeout downloading form data from {url}")
            raise SurveyCTOAPIError(f"Request timeout: {e}") from e

        except Exception as e:
            self.logger.exception(f"Unexpected error downloading form data from {url}")
            raise SurveyCTOAPIError(f"Unexpected error: {e}") from e

    # --- Submissions Endpoints --- #

    def download_attachment_from_url(
        self, url: str, private_key: bytes | str | None = None
    ) -> bytes:
        """Download an attachment file from a SurveyCTO URL.

        Parameters
        ----------
            url: The complete URL of the attachment to download
            private_key: Private key for decrypting encrypted attachments.
                Can be provided as bytes or string.

        Returns
        -------
            Attachment file content as bytes

        Raises
        ------
            SurveyCTOAPIError: If the request fails

        Notes
        -----
            This method is useful when you have the complete attachment URL
            from form data or API responses. For encrypted attachments,
            the private_key parameter must be provided.
        """
        try:
            if private_key is None:
                # Standard GET request for unencrypted attachments
                response = self.session.get(
                    url,
                    timeout=self.config.timeout,
                    stream=True,
                )
                response.raise_for_status()
                return response.content
            # POST request with private key file for encrypted attachments
            files = {"private_key": private_key}
            response = self.session.post(
                url,
                files=files,
                timeout=self.config.timeout,
                stream=True,
            )
            response.raise_for_status()
            return response.content  # noqa: TRY300

        except requests.exceptions.HTTPError as e:
            self.logger.exception(f"HTTP error downloading from {url}")
            raise SurveyCTOAPIError(f"Failed to download from URL: {e}") from e

        except requests.exceptions.ConnectionError as e:
            self.logger.exception(f"Connection error downloading from {url}")
            raise SurveyCTOAPIError(f"Connection failed: {e}") from e

        except requests.exceptions.Timeout as e:
            self.logger.exception(f"Timeout downloading from {url}")
            raise SurveyCTOAPIError(f"Request timeout: {e}") from e

        except Exception as e:
            self.logger.exception(f"Unexpected error downloading from {url}")
            raise SurveyCTOAPIError(f"Unexpected error: {e}") from e

    def close(self) -> None:
        """Close the session and clean up resources."""
        if self.session:
            self.session.close()

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.close()
