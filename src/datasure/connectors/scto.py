import contextlib
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

import polars as pl
import streamlit as st
from pydantic import BaseModel, Field, field_validator

from datasure.utils.dataframe_utils import standardize_missing_values
from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table
from datasure.utils.scto_api import (
    SurveyCTOAPIClient,
    SurveyCTOAPIConfig,
    SurveyCTOAPIError,
)

# Import secure credential storage
from datasure.utils.secure_credentials import (
    list_stored_credentials,
    retrieve_scto_credentials,
    store_scto_credentials,
)

# --- Constants --- #
SCTO_KEY_IMPORT_OPTIONS = ("Import from File", "Paste private key text")

# --- Configuration and Models --- #


class FormType(str, Enum):
    """Enum for form types."""

    REGULAR = "regular"
    SERVER_DATASET = "server_dataset"


class MediaType(str, Enum):
    """Enum for media types."""

    IMAGE = "image"
    AUDIO = "audio"
    VIDEO = "video"
    FILE = "file"
    COMMENTS = "comments"
    TEXT_AUDIT = "text audit"
    AUDIO_AUDIT = "audio audit"
    SENSOR_STREAM = "sensor stream"


@dataclass
class SurveyCTOConfig:
    """Configuration for SurveyCTO operations."""

    max_retries: int = 3
    timeout: int = 30
    chunk_size: int = 1000
    default_date: datetime = datetime(2024, 1, 1, 13, 40, 40)
    date_format: str = "%b %d, %Y %I:%M:%S %p"


class ServerCredentials(BaseModel):
    """Model for server credentials with validation."""

    server: str = Field(..., min_length=2, max_length=64)
    user: str = Field(..., min_length=4, max_length=128)
    password: str = Field(..., min_length=1)

    @field_validator("server")
    def validate_server(cls, v):
        """Validate server name format."""
        if not re.fullmatch(r"^[a-z][a-z0-9]{1,63}", v):
            raise ValueError("Invalid SurveyCTO server name format")
        return v

    @field_validator("user")
    def validate_user(cls, v):
        """Validate user email format."""
        if not re.fullmatch(
            r"^[A-Za-z0-9\._\-\+%]+@[A-Za-z0-9\.\-]+\.[A-Z|a-z]{2,7}$", v
        ):
            raise ValueError("Invalid email format for SurveyCTO user")
        return v


class FormConfig(BaseModel):
    """Model for form configuration."""

    alias: str = Field(..., min_length=1, max_length=64)
    form_id: str = Field(..., min_length=1, max_length=64)
    server: str = Field(..., min_length=2, max_length=64)
    username: str | None = Field(None, min_length=4, max_length=128)
    private_key: str | None = None
    save_to: str | None = None
    attachments: bool = False
    refresh: bool = True


# --- Exceptions --- #


class SurveyCTOError(Exception):
    """Base exception for SurveyCTO operations."""

    pass


class ConnectionError(SurveyCTOError):
    """Exception for connection errors."""

    pass


class ValidationError(SurveyCTOError):
    """Exception for validation errors."""

    pass


# --- SurveyCTO Server Connect Button Click Action --- #


# --- Get cache data for SurveyCTO serves --- #
def scto_server_connect(servername: str, username: str, password: str) -> str:
    """Validate SurveyCTO account details and load user data.

    PARAMS
    ------
    servername: SurveyCTO server name
    username: SurveyCTO account username (email address)
    password: SurveyCTO account password

    Return:
    ------
    SurveyCTO object

    """
    # check that required fields are not empty
    if not servername or not username or not password:
        st.warning("Complete all required fields.")
        st.stop()

    # check that servername is valid
    elif not re.fullmatch(r"^[a-z][a-z0-9]{1,63}$", servername):
        st.warning("Invalid server name.")
        st.stop()


# --- Core Classes --- #


class CacheManager:
    """Manages caching operations for SurveyCTO data."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.default_date = SurveyCTOConfig().default_date
        self.logger = logging.getLogger(__name__)

    def get_existing_data(self, alias) -> tuple[pl.DataFrame, datetime]:
        """Load existing data from duckdb and return with latest submission date."""
        existing_data = duckdb_get_table(
            self.project_id,
            db_name="raw",
            alias=alias,
        )
        if existing_data.is_empty():
            return existing_data, self.default_date
        else:
            if "SubmissionDate" in existing_data.columns:
                latest_date = (
                    existing_data.select(pl.col("SubmissionDate").max()).to_dicts()[0]
                ).get("SubmissionDate", self.default_date)
                if isinstance(latest_date, datetime):
                    return existing_data, latest_date
                elif isinstance(latest_date, str):
                    try:
                        parsed_date = datetime.fromisoformat(latest_date)
                        return existing_data, parsed_date  # noqa: TRY300
                    except ValueError:
                        self.logger.warning(
                            f"Failed to parse SubmissionDate '{latest_date}' as ISO format. Using default date."
                        )
                        return existing_data, self.default_date
                else:
                    self.logger.warning(
                        f"Unexpected type for SubmissionDate: {type(latest_date)}. Using default date."
                    )
                    return existing_data, self.default_date
            else:
                self.logger.warning(
                    "SubmissionDate column not found in existing data. Using default date."
                )
                return existing_data, self.default_date


class DataProcessor:
    """Handles data processing and type conversion."""

    def __init__(self):
        self.date_format = SurveyCTOConfig().date_format
        self.logger = logging.getLogger(__name__)

    def get_repeat_fields(self, questions: pl.DataFrame) -> list[str]:
        """Extract repeat field names from form definition."""
        fields = questions.select(["type", "name"])
        repeat_fields = []
        begin_count = 0
        end_count = 0

        for row in fields.iter_rows(named=True):
            if row["type"] == "begin repeat":
                begin_count += 1
            elif row["type"] == "end repeat":
                end_count += 1
            elif (
                begin_count > end_count
                and len(str(row["name"])) > 1
                and row["type"] not in ["begin group", "end group"]
            ):
                repeat_fields.append(row["name"])

        return repeat_fields

    def get_repeat_columns(self, field: str, data_cols: list[str]) -> list[str]:
        """Get all columns that belong to a repeat group."""
        pattern = rf"\b{re.escape(field)}_[0-9]+_{{,1}}[0-9]*_{{,1}}[0-9]*\b"
        return [col for col in data_cols if re.fullmatch(pattern, col)] or [field]

    def _convert_standard_datetime_columns(self, data: pl.DataFrame) -> pl.DataFrame:
        """Convert standard datetime columns to datetime type."""
        datetime_cols = ["CompletionDate", "SubmissionDate", "starttime", "endtime"]
        for col in datetime_cols:
            if col in data.columns:
                with contextlib.suppress(Exception):
                    data = data.with_columns(
                        pl.col(col).str.strptime(
                            pl.Datetime, format=self.date_format, strict=False
                        )
                    )
        return data

    def _convert_standard_numeric_columns(self, data: pl.DataFrame) -> pl.DataFrame:
        """Convert standard numeric columns to float type."""
        numeric_cols = ["duration", "formdef_version"]
        for col in numeric_cols:
            if col in data.columns:
                with contextlib.suppress(Exception):
                    data = data.with_columns(pl.col(col).cast(pl.Float64, strict=False))
        return data

    def _get_field_columns(
        self, field_name: str, repeat_fields: list[str], data_cols: list[str]
    ) -> list[str]:
        """Get all columns for a field, including repeat columns."""
        if field_name in repeat_fields:
            cols = self.get_repeat_columns(field_name, data_cols)
        else:
            cols = [field_name]
        return [col for col in cols if col in data_cols]

    def _convert_column_by_type(
        self, data: pl.DataFrame, col: str, field_type: str
    ) -> pl.DataFrame:
        """Convert a single column based on its field type."""
        try:
            if field_type in ["date", "datetime", "time"]:
                return data.with_columns(
                    pl.col(col).str.strptime(pl.Datetime, format="%+", strict=False)
                )
            elif field_type in ["integer", "decimal"]:
                return data.with_columns(pl.col(col).cast(pl.Float64, strict=False))
            elif field_type == "note":
                return data.drop(col)
            return data  # noqa: TRY300
        except Exception as e:
            self.logger.warning(f"Failed to convert column {col}: {e}")
            return data

    def _convert_form_definition_fields(
        self, data: pl.DataFrame, questions: pl.DataFrame
    ) -> pl.DataFrame:
        """Convert fields based on form definition."""
        repeat_fields = self.get_repeat_fields(questions)
        data_cols = data.columns

        for row in questions.select(["type", "name"]).iter_rows(named=True):
            field_name = row["name"]
            field_type = row["type"]

            cols = self._get_field_columns(field_name, repeat_fields, data_cols)

            for col in cols:
                data = self._convert_column_by_type(data, col, field_type)

        return data

    def convert_data_types(
        self, data: pl.DataFrame, questions: pl.DataFrame
    ) -> pl.DataFrame:
        """Convert data types based on form definition."""
        data = self._convert_standard_datetime_columns(data)
        data = self._convert_standard_numeric_columns(data)
        data = self._convert_form_definition_fields(data, questions)
        return data


class MediaDownloader:
    """Handles media file downloads."""

    def __init__(self, scto_client: SurveyCTOAPIClient, config: SurveyCTOConfig):
        self.scto_client = scto_client
        self.config = config
        self.logger = logging.getLogger(__name__)

    def download_media_files(
        self,
        media_fields: list[str],
        data: pl.DataFrame,
        media_folder: Path,
        encryption_key: str | None = None,
    ) -> None:
        """Download all media files for the given data."""
        media_folder.mkdir(parents=True, exist_ok=True)

        for field in media_fields:
            self._download_field_media(field, data, media_folder, encryption_key)

    def _download_field_media(
        self,
        field: str,
        data: pl.DataFrame,
        media_folder: Path,
        encryption_key: str | None,
    ) -> None:
        """Download media files for a specific field."""
        processor = DataProcessor()
        cols = processor.get_repeat_columns(field, data.columns)

        for col in cols:
            media_data = (
                data.filter(pl.col(col).is_not_null())
                .select(["KEY", col])
                .filter(pl.col(col).str.strip_chars() != "")
            )

            if media_data.is_empty():
                self.logger.info(f"No media files found for field '{col}'")
                continue

            if len(media_data) > 0:
                progress_bar = st.progress(0, text=f"Downloading {col} media files...")

                for idx, row in enumerate(media_data.iter_rows(named=True)):
                    try:
                        self._download_single_file(
                            row[col], row["KEY"], col, media_folder, encryption_key
                        )
                        progress_bar.progress(
                            (idx + 1) / len(media_data),
                            text=f"Downloading {col}... {idx + 1}/{len(media_data)}",
                        )
                    except Exception:
                        self.logger.exception(
                            f"Failed to download {col} for {row['KEY']}"
                        )

    def _download_single_file(
        self,
        url: str,
        submission_key: str,
        field_name: str,
        media_folder: Path,
        encryption_key: str | None,
    ) -> None:
        """Download a single media file."""
        file_ext = Path(url).suffix or ".csv"
        clean_key = submission_key.replace("uuid:", "")
        filename = f"{field_name}_{clean_key}{file_ext}"

        # if file exists, skip download
        if not (media_folder / filename).exists():
            # Convert encryption key to bytes if provided
            private_key = encryption_key.encode() if encryption_key else None
            media_content = self.scto_client.download_attachment_from_url(
                url, private_key=private_key
            )
            (media_folder / filename).write_bytes(media_content)


class SurveyCTOClient:
    """Main client for SurveyCTO operations."""

    def __init__(self, project_id: str, config: SurveyCTOConfig | None = None):
        self.project_id = project_id
        self.config = config or SurveyCTOConfig()
        self.cache_manager = CacheManager(project_id)
        self.data_processor = DataProcessor()
        self.logger = logging.getLogger(__name__)
        self._scto_client: SurveyCTOAPIClient | None = None

    def connect(
        self, credentials: ServerCredentials, validate_permissions: bool = False
    ) -> dict[str, any]:
        """
        Establish connection to SurveyCTO server and validate credentials.

        Args:
            credentials: Server credentials to use for connection
            validate_permissions: Whether to validate permissions by listing forms

        Returns
        -------
            Dict containing connection info and available form

        Raises
        ------
            ConnectionError: If connection or validation fails
        """
        connection_info = self._initialize_connection_info(
            credentials.server, validate_permissions
        )

        try:
            self._create_api_client(credentials)

            if validate_permissions:
                self._validate_connection(credentials, connection_info)
            else:
                self._skip_validation(credentials.server, connection_info)

        except Exception as e:
            self._handle_connection_error(e, credentials.server)

        return connection_info

    def _initialize_connection_info(
        self, server: str, validate_permissions: bool
    ) -> dict[str, any]:
        """Initialize connection info dictionary."""
        return {
            "server": server,
            "connected": False,
            "forms_count": 0,
            "forms_list": [],
            "validation_attempted": validate_permissions,
        }

    def _create_api_client(self, credentials: ServerCredentials) -> None:
        """Create SurveyCTO API client."""
        api_config = SurveyCTOAPIConfig(
            server_name=credentials.server,
            username=credentials.user,
            password=credentials.password,
            timeout=self.config.timeout,
            max_retries=self.config.max_retries,
        )
        self._scto_client = SurveyCTOAPIClient(api_config)

    def _validate_connection(
        self, credentials: ServerCredentials, connection_info: dict[str, any]
    ) -> None:
        """Validate connection by listing forms."""
        try:
            forms_list = self._fetch_forms_list(credentials.server)
            self._update_connection_info(
                connection_info, forms_list, credentials.server
            )
        except SurveyCTOAPIError as api_err:
            self._handle_api_error(api_err, credentials.server)
        except Exception as validation_err:
            self._handle_validation_error(validation_err)

    def _fetch_forms_list(self, server: str) -> list[tuple[str, str, bool]]:
        """Fetch forms list from server."""
        with st.spinner(f"Validating connection to {server}..."):
            server_response = self._scto_client.list_forms()
            return [
                (
                    form.get("id", "no id"),
                    form.get("title", "No title"),
                    form.get("encrypted", False),
                )
                for form in server_response
            ]

    def _update_connection_info(
        self, connection_info: dict[str, any], forms_list: list, server: str
    ) -> None:
        """Update connection info with forms data."""
        connection_info.update(
            {
                "connected": True,
                "forms_count": len(forms_list),
                "forms_list": forms_list,
            }
        )

        self.logger.info(
            f"Successfully connected to {server}. Found {len(forms_list)} forms."
        )

        self._show_connection_status(forms_list, server)

    def _show_connection_status(self, forms_list: list, server: str) -> None:
        """Display connection status message."""
        if len(forms_list) > 0:
            st.success(f"✅ Connection to server '{server}' successful!.")
        else:
            st.warning(
                f"⚠️ Connection successful, but no forms found on server '{server}'."
            )

    def _handle_api_error(self, api_err: SurveyCTOAPIError, server: str) -> None:
        """Handle API errors with user-friendly messages."""
        self._scto_client = None
        error_msg = str(api_err)

        error_mapping = {
            (
                "401",
                "Invalid credentials",
            ): "🔐 Invalid credentials. Please check your username and password.",
            (
                "403",
                "forbidden",
            ): "🚫 Access forbidden. Your account may not have permission to access this server.",
            ("404",): f"🔍 Server '{server}' not found. Please verify the server name.",
            (
                "timeout",
            ): f"⏱️ Connection timeout to server '{server}'. The server may be slow or unavailable. Please try again.",
            (
                "connection",
            ): f"🔌 Cannot connect to server '{server}'. Please check your internet connection and verify the server name.",
        }

        for keywords, message in error_mapping.items():
            if any(
                keyword in error_msg or keyword in error_msg.lower()
                for keyword in keywords
            ):
                raise ConnectionError(message) from api_err

        raise ConnectionError(f"❌ API error: {api_err}") from api_err

    def _handle_validation_error(self, validation_err: Exception) -> None:
        """Handle validation errors."""
        self._scto_client = None
        self.logger.exception(f"Validation error: {validation_err}")
        raise ConnectionError(
            f"❌ Failed to validate credentials: {validation_err}"
        ) from validation_err

    def _skip_validation(self, server: str, connection_info: dict[str, any]) -> None:
        """Skip validation and mark connection as successful."""
        connection_info["connected"] = True
        st.success(f"✅ Connection created for server '{server}' (validation skipped).")

    def _handle_connection_error(self, error: Exception, server: str) -> None:
        """Handle connection creation errors."""
        self._scto_client = None
        self.logger.exception("Connection creation error")

        if "Invalid server name" in str(error):
            raise ConnectionError(
                f"🏷️ Invalid server name '{server}'. "
                f"Server names should contain only lowercase letters and numbers."
            )
        raise ConnectionError(f"❌ Failed to create connection: {error}")

    def get_form_definition(self, form_id: str) -> tuple[pl.DataFrame, pl.DataFrame]:
        """Get form definition (questions and choices)."""
        if not self._scto_client:
            raise ConnectionError("Not connected to server")

        try:
            form_def = self._scto_client.download_form_definition(form_id)

        except SurveyCTOAPIError as e:
            raise SurveyCTOError(f"Failed to get form definition: {e}") from e

        questions = pl.DataFrame(
            form_def["fieldsRowsAndColumns"][1:],
            schema=form_def["fieldsRowsAndColumns"][0],
            orient="row",
        )

        choices = pl.DataFrame(
            form_def["choicesRowsAndColumns"][1:],
            schema=form_def["choicesRowsAndColumns"][0],
            orient="row",
        )

        return questions, choices

    def import_data(self, form_config: FormConfig) -> int:
        """Import data from SurveyCTO form."""
        if not self._scto_client:
            server = form_config.server
            user = form_config.username
            if not server or not user:
                raise ValueError("Server and username must be provided")
            try:
                scto_cred = retrieve_scto_credentials(
                    self.project_id, type="scto_login", server=server
                )
                password = scto_cred.get("credentials", {}).get("password", "")
            except KeyError:
                raise KeyError("Credentials not found in secure storage") from None

            credentials = ServerCredentials(server=server, user=user, password=password)
            try:
                api_config = SurveyCTOAPIConfig(
                    server_name=credentials.server,
                    username=credentials.user,
                    password=credentials.password,
                    timeout=self.config.timeout,
                    max_retries=self.config.max_retries,
                )
                self._scto_client = SurveyCTOAPIClient(api_config)
            except SurveyCTOAPIError as e:
                raise ConnectionError(f"Not connected to server: {e}") from e
        try:
            # Try server dataset first
            return self._import_server_dataset(form_config)
        except Exception:
            return self._import_regular_form(form_config)

    def _import_server_dataset(self, form_config: FormConfig) -> int:
        """Import from server dataset."""
        data_csv = self._scto_client.download_dataset_csv(form_config.form_id)
        data = pl.read_csv(data_csv)

        # standardize missing values
        data = standardize_missing_values(data)

        # Save to DuckDB
        duckdb_save_table(self.project_id, data, alias=form_config.alias, db_name="raw")

        return len(data)

    def _import_private_key(self, private_key: str) -> str:
        """Import private key from file."""
        if not private_key or not Path(private_key).exists():
            raise ValidationError("Private key file does not exist or is empty")

        try:
            with open(private_key) as f:
                return f.read().strip()
        except Exception as e:
            raise ValidationError(f"Failed to read private key: {e}")  # noqa: B904

    def _import_regular_form(self, form_config: FormConfig) -> int:
        """Import from regular form with incremental updates."""
        # Load existing data
        existing_data, last_date = (
            self.cache_manager.get_existing_data(form_config.save_to)
            if form_config.save_to
            else (pl.DataFrame(), self.config.default_date)
        )

        if not form_config.refresh:
            return 0

        # Prepare parameters for API request
        params = {"date": int(last_date.timestamp())} if last_date else None

        # Prepare private key if provided
        private_key = None
        if form_config.private_key:
            private_key = self._import_private_key(form_config.private_key)

        # Get new data
        new_data_json = self._scto_client.download_form_data_json(
            form_id=form_config.form_id,
            params=params,
            private_key=private_key,
        )

        new_data = pl.DataFrame(new_data_json)
        new_count = len(new_data)

        # Combine data
        if not existing_data.is_empty():
            combined_data = pl.concat([existing_data, new_data], how="diagonal")
        else:
            combined_data = new_data

        # Standardize missing values BEFORE type conversion
        combined_data = standardize_missing_values(combined_data)

        # Process data types
        questions, _ = self.get_form_definition(form_config.form_id)
        if "disabled" in questions.columns:
            questions = questions.filter(pl.col("disabled") != "yes")
        combined_data = self.data_processor.convert_data_types(combined_data, questions)

        # Download media if requested
        if form_config.attachments and form_config.save_to:
            self._download_attachments(questions, new_data, form_config)

        # Save to DuckDB
        duckdb_save_table(
            self.project_id, combined_data, alias=form_config.alias, db_name="raw"
        )

        return new_count

    def _download_attachments(
        self, questions: pl.DataFrame, data: pl.DataFrame, form_config: FormConfig
    ) -> None:
        """Download media attachments."""
        media_types = {e.value for e in MediaType}
        media_fields = (
            questions.filter(pl.col("type").is_in(media_types))
            .select("name")
            .to_series()
            .to_list()
        )

        if media_fields:
            media_folder = Path(form_config.save_to).parent / "media"

            downloader = MediaDownloader(self._scto_client, self.config)
            downloader.download_media_files(
                media_fields, data, media_folder, form_config.private_key
            )


# --- Streamlit UI Components --- #


class SurveyCTOUI:
    """Streamlit UI components for SurveyCTO integration."""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.client = SurveyCTOClient(project_id)
        self.logger = logging.getLogger(__name__)

    def _get_logo_path(self) -> str:
        """Get path to SurveyCTO logo."""
        assets_dir = Path(__file__).parent.parent / "assets"
        image_path = assets_dir / "SurveyCTO-Logo-CMYK.png"
        return str(image_path)

    def _get_forms_info(self, credentials: ServerCredentials) -> dict[str, any]:
        """Get connection info for the current server."""
        connection_info = self.client.connect(
            credentials=credentials,
            validate_permissions=True,
        )
        return {
            "connected": connection_info["connected"],
            "forms_count": connection_info["forms_count"],
            "forms_list": connection_info["forms_list"],
        }

    def render_login_form(self) -> None:
        """Render server login form."""
        with st.container(border=True):
            st.image(self._get_logo_path(), width=200)
            st.markdown("*Server Details:*")

            server = st.text_input("Server name*", help="e.g., 'myserver'")
            email = st.text_input("Email address*", help="Your SurveyCTO account email")
            password = st.text_input("Password*", type="password")

            st.markdown("**required*")

            if st.button(
                ":material/key_vertical: Connect & Save Credentials",
                type="primary",
                width="stretch",
            ):
                try:
                    credentials = ServerCredentials(
                        server=server, user=email, password=password
                    )
                    self.client.connect(credentials, validate_permissions=True)
                    store_scto_credentials(
                        self.project_id,
                        username=email,
                        password=password,
                        server=server,
                        type="scto_login",
                    )
                except Exception as e:
                    st.error(f"Connection failed: {e}")

    def _validate_private_key_text(self, private_key_text: str) -> bool:
        """Validate the private key text format."""
        if (
            not private_key_text
            or private_key_text is None
            or not isinstance(private_key_text, str)
        ):
            raise ValidationError("Private key text cannot be empty")

        startswith_p = "-----BEGIN RSA PRIVATE KEY-----"
        endswith_p = "-----END RSA PRIVATE KEY-----"

        # Check for PEM format
        if not private_key_text.startswith(
            startswith_p
        ) or not private_key_text.endswith(endswith_p):
            raise ValidationError(
                f"Private key must start with '{startswith_p}' and end with '{endswith_p}'"
            )

        return True

    def render_form_config(
        self, edit_mode: bool = False, defaults: dict | None = None
    ) -> None:
        """Render form configuration interface with form selection."""
        defaults = defaults or {}

        with st.container(border=True):
            self._render_logo()

            # Get and validate credentials
            credentials = self._get_server_credentials(edit_mode)
            if not credentials:
                return

            # Get form selection
            form_data = self._render_form_selection(credentials, defaults)
            if not form_data:
                return

            # Render form configuration fields
            config_data = self._render_config_fields(form_data, defaults, edit_mode)
            if config_data is None:
                return

            # Handle form submission
            self._handle_form_submission(edit_mode, credentials, form_data, config_data)

    def _render_logo(self) -> None:
        """Render logo or header."""
        logo_path = self._get_logo_path()
        if logo_path and Path(logo_path).exists():
            st.image(logo_path, width=200)
        else:
            st.markdown("### SurveyCTO Form Configuration")

    def _get_server_credentials(
        self, edit_mode: bool = False
    ) -> ServerCredentials | None:
        """Get and validate server credentials."""
        login_credentials = list_stored_credentials(self.project_id).get(
            "credentials", {}
        )
        if not login_credentials:
            st.warning(
                "No SurveyCTO servers configured. Please connect to a server using the credential manager."
            )
            return None

        select_cred = st.selectbox(
            "Select Server Credentials*",
            options=list(login_credentials.keys()),
            index=None,
            help="Select the server credentials to use for this form",
            key=f"scto_select_cred{edit_mode}",
        )

        try:
            server = login_credentials[select_cred]["server"]
            user = login_credentials[select_cred]["username"]
            scto_cred = retrieve_scto_credentials(
                self.project_id, type="scto_login", server=server
            )
            password = (
                scto_cred.get("credentials", {}).get("password", "")
                if scto_cred
                else ""
            )

            credentials = ServerCredentials(server=server, user=user, password=password)

            # Validate credentials
            try:
                self.client.connect(credentials, validate_permissions=False)
            except ConnectionError as e:
                st.error(f"Connection failed: {e}")
                return None

            return credentials  # noqa: TRY300

        except KeyError:
            st.info("Select SurveyCTO server credentials to proceed.")
            return None

    def _render_form_selection(
        self, credentials: ServerCredentials, defaults: dict
    ) -> dict | None:
        """Render form selection dropdown and return form data."""
        forms_info = self._get_forms_info(credentials)

        form_options = [f"{form[0]} ({form[1]})" for form in forms_info["forms_list"]]
        form_ids_only = [form[0] for form in forms_info["forms_list"]]

        default_index = self._get_default_form_index(defaults, form_ids_only)

        selected_form = st.selectbox(
            "Select Form ID*",
            options=form_options,
            index=default_index,
            help="Select a form from the available forms on the server",
        )

        if not selected_form:
            return None

        return self._parse_selected_form(selected_form, form_options, forms_info)

    def _get_default_form_index(
        self, defaults: dict, form_ids_only: list
    ) -> int | None:
        """Get default index for form selection."""
        if defaults and defaults.get("form_id", "") in form_ids_only:
            return form_ids_only.index(defaults.get("form_id", ""))
        return None

    def _parse_selected_form(
        self, selected_form: str, form_options: list, forms_info: dict
    ) -> dict:
        """Parse selected form and return form data."""
        selected_form_split = re.match(r"^(.*?) \((.*)\)$", selected_form)
        form_id = selected_form_split.group(1) if selected_form_split else selected_form
        form_title = selected_form_split.group(2) if selected_form_split else "No title"

        form_index = form_options.index(selected_form)
        encrypted = (
            forms_info["forms_list"][form_index][2]
            if len(forms_info["forms_list"]) > form_index
            else False
        )

        with st.expander("📋 Form Details", expanded=False):
            st.write(f"**Form ID:** {form_id}")
            st.write(f"**Title:** {form_title}")
            st.write(f"**Encrypted:** {'Yes' if encrypted else 'No'}")

        return {
            "form_id": form_id,
            "form_title": form_title,
            "encrypted": encrypted,
        }

    def _render_config_fields(
        self, form_data: dict, defaults: dict, edit_mode: bool
    ) -> dict | None:
        """Render configuration fields and return values."""
        alias = self._render_alias_field(form_data, defaults, edit_mode)

        private_key_file = self._render_private_key_field(
            form_data["encrypted"], defaults, edit_mode
        )
        if private_key_file is None:
            return None

        save_file = self._render_save_file_field(defaults)
        if save_file is None:
            return None

        attachments = st.checkbox(
            "Download attachments",
            value=defaults.get("attachments", False),
            disabled=False,
            help="Download media files (images, audio, etc.)",
        )

        st.markdown("**required*")

        return {
            "alias": alias,
            "private_key_file": private_key_file,
            "save_file": save_file,
            "attachments": attachments,
        }

    def _render_alias_field(
        self, form_data: dict, defaults: dict, edit_mode: bool
    ) -> str:
        """Render alias input field."""
        alias_default = re.sub(r"[^\w]", "_", form_data["form_title"])
        return st.text_input(
            "Alias*",
            help="Unique identifier for this form",
            value=defaults.get("alias", alias_default),
            key=f"surveyctoui_alias{edit_mode}",
            disabled=edit_mode,
        )

    def _render_private_key_field(
        self, encrypted: bool, defaults: dict, edit_mode: bool
    ) -> str | None:
        """Render and validate private key field."""
        private_key_file = st.text_input(
            "File path for Private Key",
            value=defaults.get("private_key", ""),
            disabled=not encrypted,
            key=f"surveyctoui_private_key{edit_mode}",
            help="Enter encryption key if the form is encrypted (optional) eg. C/Users/documents/Surevy_PRIVATEKEY.pem",
        )

        if not encrypted:
            return ""

        if not private_key_file:
            st.warning(
                "Encryption key is required for encrypted forms. Only published fields will be downloaded."
            )
            return ""

        if not self._validate_private_key_path(private_key_file):
            return None

        return private_key_file

    def _validate_private_key_path(self, private_key_file: str) -> bool:
        """Validate private key file path."""
        if not os.path.exists(str(private_key_file)):
            st.error("Encryption key must be a valid file path to a key file.")
            return False

        if not private_key_file.endswith(".pem"):
            st.error("Encryption key file must have a .pem extension.")
            return False

        return True

    def _render_save_file_field(self, defaults: dict) -> str | None:
        """Render and validate save file field."""
        save_file = st.text_input(
            "File path to save data",
            value=defaults.get("save_to", ""),
            disabled=False,
            help="File path to save the data (e.g., C:/Users/documents/data/survey.csv)",
        )

        if save_file and os.path.exists(str(save_file)):
            save_path = Path(str(save_file)).parent
            if not save_path.exists():
                st.error(
                    f"Save directory '{save_path}' does not exist. Please create it first."
                )
                return None

        return save_file

    def _handle_form_submission(
        self,
        edit_mode: bool,
        credentials: ServerCredentials,
        form_data: dict,
        config_data: dict,
    ) -> None:
        """Handle form submission button click."""
        if not st.button(
            "Add Form" if not edit_mode else "Update Form",
            type="primary",
            width="stretch",
        ):
            return

        if not config_data["alias"]:
            st.error("Please enter an alias for the form.")
            return

        if not form_data["form_id"]:
            st.error("Please select or enter a form ID.")
            return

        form_config = FormConfig(
            alias=config_data["alias"],
            form_id=form_data["form_id"],
            server=credentials.server,
            username=credentials.user,
            private_key=str(config_data["private_key_file"]) or None,
            save_to=str(config_data["save_file"]) or None,
            attachments=config_data["attachments"],
        )

        try:
            if edit_mode:
                self._update_form_on_project(form_config)
                st.success("Form updated successfully")
            else:
                self._add_form_to_project(form_config)
                st.success("Form added successfully")

            st.rerun()
        except Exception as e:
            st.error(f"Failed to {'update' if edit_mode else 'add'} form: {e}")

    def _get_form_options(self, server: str) -> list[tuple[str, str]] | None:
        """
        Get list of available forms for the selected server.

        Returns
        -------
            List of tuples (form_id, form_title) or None if connection failed
        """
        try:
            with st.spinner(f"Loading forms from {server}..."):
                # Get list of forms with metadata
                forms = self.client._scto_client.list_forms()

                form_options = []
                for form in forms:
                    try:
                        form_id = form.get("id", "unknown")
                        title = form.get("title", "Title unavailable")
                        form_options.append((form_id, title))

                    except Exception as e:
                        # If we can't get the title, just use the form ID
                        self.logger.warning(f"Could not get title for form {form}: {e}")
                        form_options.append((str(form), "Title unavailable"))

                # Sort by form ID for consistency
                form_options.sort(key=lambda x: x[0])
                return form_options

        except SurveyCTOAPIError as e:
            self.logger.exception(f"Failed to load forms for server {server}")
            st.error(f"Failed to load forms: {e}")
            return None

    def _extract_form_title(self, form_def: dict, form_id: str) -> str:
        """
        Extract form title from form definition.

        Args:
            form_def: Form definition dictionary from SurveyCTO
            form_id: Form ID as fallback

        Returns
        -------
            Form title or form_id if title not found
        """
        try:
            # Try settings first
            title = self._extract_title_from_settings(form_def)
            if title:
                return title

            # Try survey sheet as fallback
            title = self._extract_title_from_fields(form_def)
            if title:
                return title

            return form_id  # noqa: TRY300

        except Exception as e:
            self.logger.warning(f"Error extracting title for form {form_id}: {e}")
            return form_id

    def _extract_title_from_settings(self, form_def: dict) -> str | None:
        """Extract title from form settings."""
        if "settings" not in form_def:
            return None

        settings = form_def["settings"]
        if not isinstance(settings, list) or len(settings) <= 1:
            return None

        headers = settings[0] if settings else []
        data = settings[1] if len(settings) > 1 else []

        return self._find_title_in_headers(headers, data)

    def _find_title_in_headers(self, headers: list, data: list) -> str | None:
        """Find title value from headers and data rows."""
        title_fields = ["form_title", "title", "form_name", "name"]

        for field in title_fields:
            if field in headers:
                index = headers.index(field)
                if index < len(data) and data[index]:
                    return str(data[index])

        return None

    def _extract_title_from_fields(self, form_def: dict) -> str | None:
        """Extract title from survey fields (fieldsRowsAndColumns)."""
        if "fieldsRowsAndColumns" not in form_def:
            return None

        fields = form_def["fieldsRowsAndColumns"]
        if len(fields) <= 1:
            return None

        # Look for a title field in the first few rows
        for i in range(1, min(5, len(fields))):
            row = fields[i]
            if len(row) > 1 and "title" in str(row).lower():
                # This is a heuristic - might need adjustment
                continue

        return None

    def _add_form_to_project(self, form_config: FormConfig) -> None:
        """Add form configuration to project."""
        # Check for duplicate alias
        import_log = duckdb_get_table(
            self.project_id, alias="import_log", db_name="logs"
        )
        if form_config.alias in import_log.get_column("alias").to_list():
            raise ValidationError(f"Alias '{form_config.alias}' already exists")

        # Add to import log
        new_entry = {
            "refresh": True,
            "load": True,
            "source": "SurveyCTO",
            "alias": form_config.alias,
            "filename": "",
            "sheet_name": "",
            "server": form_config.server,
            "username": form_config.username or "",
            "form_id": form_config.form_id,
            "private_key": form_config.private_key or "",
            "save_to": form_config.save_to or "",
            "attachments": form_config.attachments,
        }

        updated_log = pl.concat([import_log, pl.DataFrame([new_entry])], how="diagonal")
        duckdb_save_table(
            self.project_id, updated_log, alias="import_log", db_name="logs"
        )

    def _update_form_on_project(self, form_config: FormConfig) -> None:
        """Update existing form configuration in project."""
        import_log = duckdb_get_table(
            self.project_id, alias="import_log", db_name="logs"
        )

        # Find existing entry
        existing_entry = import_log.filter(pl.col("alias") == form_config.alias)
        if existing_entry.is_empty():
            raise ValidationError(f"Alias '{form_config.alias}' does not exist")

        # Update entry
        updated_entry = {
            "refresh": True,
            "load": True,
            "source": "SurveyCTO",
            "alias": form_config.alias,
            "filename": "",
            "sheet_name": "",
            "server": form_config.server,
            "form_id": form_config.form_id,
            "private_key": form_config.private_key,
            "save_to": form_config.save_to,
            "attachments": form_config.attachments,
        }

        updated_log = import_log.with_columns(
            [
                pl.when(pl.col("alias") == form_config.alias)
                .then(pl.lit(value))
                .otherwise(pl.col(column))
                .alias(column)
                for column, value in updated_entry.items()
            ]
        )

        duckdb_save_table(
            self.project_id, updated_log, alias="import_log", db_name="logs"
        )


# --- Main Functions --- #


def download_forms(project_id: str, form_configs: list[FormConfig]) -> None:
    """Download data for multiple forms with progress tracking."""
    if not form_configs:
        st.warning("No forms selected for download")
        return

    client = SurveyCTOClient(project_id)
    progress_bar = st.progress(0, text="Downloading from SurveyCTO...")

    success_count = 0
    failed_count = 0
    for i, form_config in enumerate(form_configs):
        try:
            new_count = client.import_data(form_config)
            st.write(
                f"{i + 1}/{len(form_configs)}: Downloaded {new_count} new records for {form_config.alias}"
            )
            success_count += 1
        except Exception as e:
            st.error(f"Failed to download {form_config.alias}: {e}")
            failed_count += 1
        finally:
            progress_bar.progress(
                (i + 1) / len(form_configs),
                text=f"Progress: {i + 1}/{len(form_configs)}",
            )

    if success_count > 0:
        st.success(f"Successfully downloaded {success_count} forms")
    if failed_count > 0:
        st.error(f"Failed to download {failed_count} forms")
