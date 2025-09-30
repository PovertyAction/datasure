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

    def download_form_data_json(
        self, form_id: str, params: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Download form data in JSON wide format.

        Parameters
        ----------
            form_id: Form identifier
            params: Optional query parameters (e.g., date filters)

        Returns
        -------
            Form data in JSON wide format
        """
        response = self._make_request("GET", f"/forms/data/wide/json/{form_id}", params=params)
        return response.json()

    # --- Submissions Endpoints --- #

    def download_attachment(
        self, form_id: str, submission_id: str, attachment_name: str
    ) -> bytes:
        """Download a submission attachment file.

        Parameters
        ----------
            form_id: Form identifier
            submission_id: Submission identifier
            attachment_name: Name of the attachment file

        Returns
        -------
            Attachment file content as bytes
        """
        response = self._make_request(
            "GET",
            f"/forms/{form_id}/submissions/{submission_id}/attachments/{attachment_name}",
            stream=True,
        )
        return response.content

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
