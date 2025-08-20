import contextlib
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path

import pandas as pd
import polars as pl
import pysurveycto
import requests
import streamlit as st
from pydantic import BaseModel, Field, field_validator

from datasure.utils.duckdb_utils import duckdb_get_table, duckdb_save_table

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
        self.logger = logging.getLogger(__name__)

    def get_existing_data(self, file_path: str) -> tuple[pd.DataFrame, datetime]:
        """Load existing data and return with latest submission date."""
        try:
            if not Path(file_path).exists():
                return pd.DataFrame(), SurveyCTOConfig.default_date

            data = pd.read_csv(file_path)
            if data.empty or "SubmissionDate" not in data.columns:
                return data, SurveyCTOConfig.default_date

            data["SubmissionDate"] = pd.to_datetime(data["SubmissionDate"])
            return data, data["SubmissionDate"].max()

        except Exception as e:
            self.logger.warning(f"Failed to load existing data: {e}")
            return pd.DataFrame(), SurveyCTOConfig.default_date


class DataProcessor:
    """Handles data processing and type conversion."""

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    def get_repeat_fields(self, questions: pd.DataFrame) -> list[str]:
        """Extract repeat field names from form definition."""
        fields = questions[["type", "name"]].copy()
        repeat_fields = []
        begin_count = 0
        end_count = 0

        for _, row in fields.iterrows():
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

    def convert_data_types(
        self, data: pd.DataFrame, questions: pd.DataFrame
    ) -> pd.DataFrame:
        """Convert data types based on form definition."""
        # Convert standard datetime columns
        datetime_cols = ["CompletionDate", "SubmissionDate", "starttime", "endtime"]
        for col in datetime_cols:
            if col in data.columns:
                with contextlib.suppress(ValueError, TypeError):
                    data[col] = pd.to_datetime(data[col], format="mixed")

        # Convert standard numeric columns
        numeric_cols = ["duration", "formdef_version"]
        for col in numeric_cols:
            if col in data.columns:
                with contextlib.suppress(ValueError, TypeError):
                    data[col] = pd.to_numeric(data[col])

        # Process fields based on form definition
        repeat_fields = self.get_repeat_fields(questions)
        data_cols = list(data.columns)

        for _, row in questions[["type", "name"]].iterrows():
            field_name = row["name"]
            field_type = row["type"]

            # Get columns for this field (including repeat columns)
            if field_name in repeat_fields:
                cols = self.get_repeat_columns(field_name, data_cols)
            else:
                cols = [field_name]

            cols = [col for col in cols if col in data.columns]

            # Apply type conversions
            for col in cols:
                try:
                    if field_type in ["date", "datetime", "time"]:
                        data[col] = pd.to_datetime(data[col], errors="coerce")
                    elif field_type in ["integer", "decimal"]:
                        data[col] = pd.to_numeric(data[col], errors="coerce")
                    elif field_type == "note":
                        data.drop(columns=[col], inplace=True)
                except Exception as e:
                    self.logger.warning(f"Failed to convert column {col}: {e}")

        return data


class MediaDownloader:
    """Handles media file downloads."""

    def __init__(self, scto_client, config: SurveyCTOConfig):
        self.scto_client = scto_client
        self.config = config
        self.logger = logging.getLogger(__name__)

    def download_media_files(
        self,
        media_fields: list[str],
        data: pd.DataFrame,
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
        data: pd.DataFrame,
        media_folder: Path,
        encryption_key: str | None,
    ) -> None:
        """Download media files for a specific field."""
        processor = DataProcessor()
        cols = processor.get_repeat_columns(field, list(data.columns))

        for col in cols:
            media_data = data[data[col].notna()][["KEY", col]].reset_index()
            if media_data.empty:
                self.logger.info(f"No media files found for field '{col}'")
                continue
            media_data = media_data[media_data[col].str.strip() != ""]

            if len(media_data) > 0:
                progress_bar = st.progress(0, text=f"Downloading {col} media files...")

                for idx, row in media_data.iterrows():
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
            media_content = self.scto_client.get_attachment(url, key=encryption_key)
            (media_folder / filename).write_bytes(media_content)


class SurveyCTOClient:
    """Main client for SurveyCTO operations."""

    def __init__(self, project_id: str, config: SurveyCTOConfig | None = None):
        self.project_id = project_id
        self.config = config or SurveyCTOConfig()
        self.cache_manager = CacheManager(project_id)
        self.data_processor = DataProcessor()
        self.logger = logging.getLogger(__name__)
        self._scto_client = None

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
        connection_info = {
            "server": credentials.server,
            "connected": False,
            "forms_count": 0,
            "forms_list": [],
            "validation_attempted": validate_permissions,
        }

        try:
            # Create SurveyCTO client object
            self._scto_client = pysurveycto.SurveyCTOObject(
                credentials.server, credentials.user, credentials.password
            )

            if validate_permissions:
                # Validate credentials by making an API call
                try:
                    with st.spinner(
                        f"Validating connection to {credentials.server}..."
                    ):
                        server_response = self._scto_client.list_forms()
                        # extract form list with titles
                        forms_list = [
                            (
                                form.get("id", "no id"),
                                form.get("title", "No title"),
                                form.get("encrypted", False),
                            )
                            for form in server_response
                        ]

                        server_forms_count = len(forms_list)

                    connection_info.update(
                        {
                            "connected": True,
                            "forms_count": server_forms_count,
                            "forms_list": forms_list,
                        }
                    )

                    self.logger.info(
                        f"Successfully connected to {credentials.server}. Found {server_forms_count} forms."
                    )

                    # Show success message with details
                    if len(forms_list) > 0:
                        st.success(
                            f"✅ Connection to server '{credentials.server}' successful!."
                        )

                    else:
                        st.warning(
                            f"⚠️ Connection successful, but no forms found on server '{credentials.server}'."
                        )

                except requests.exceptions.HTTPError as http_err:
                    self._handle_http_error(http_err, credentials.server)

                except requests.exceptions.ConnectionError:
                    self._scto_client = None
                    raise ConnectionError(  # noqa: B904
                        f"🔌 Cannot connect to server '{credentials.server}'. "
                        f"Please check your internet connection and verify the server name."
                    )

                except requests.exceptions.Timeout:
                    self._scto_client = None
                    raise ConnectionError(  # noqa: B904
                        f"⏱️ Connection timeout to server '{credentials.server}'. "
                        f"The server may be slow or unavailable. Please try again."
                    )

                except Exception as validation_err:
                    self._scto_client = None
                    self.logger.exception(f"Validation error: {validation_err}")  # noqa: TRY401
                    raise ConnectionError(
                        f"❌ Failed to validate credentials: {validation_err}"
                    ) from validation_err
            else:
                # Skip validation, just create connection
                connection_info["connected"] = True
                st.success(
                    f"✅ Connection created for server '{credentials.server}' (validation skipped)."
                )

        except Exception as e:
            # Handle SurveyCTO object creation errors
            self._scto_client = None
            self.logger.exception("Connection creation error")

            if "Invalid server name" in str(e):
                raise ConnectionError(  # noqa: B904
                    f"🏷️ Invalid server name '{credentials.server}'. "
                    f"Server names should contain only lowercase letters and numbers."
                )
            else:
                raise ConnectionError(f"❌ Failed to create connection: {e}")  # noqa: B904

        return connection_info

    def _handle_http_error(
        self, http_err: requests.exceptions.HTTPError, server_name: str
    ) -> None:
        """Handle specific HTTP errors with user-friendly messages."""
        self._scto_client = None

        if hasattr(http_err, "response") and http_err.response is not None:
            status_code = http_err.response.status_code

            error_messages = {
                401: "🔐 Invalid credentials. Please check your username and password.",
                403: "🚫 Access forbidden. Your account may not have permission to access this server.",
                404: f"🔍 Server '{server_name}' not found. Please verify the server name.",
                429: "⏱️ Too many requests. Please wait a moment and try again.",
                500: "🔧 Server error. The SurveyCTO server is experiencing issues. Please try again later.",
                502: "🌐 Bad gateway. There may be a network issue. Please try again.",
                503: "⚠️ Service unavailable. The server is temporarily down. Please try again later.",
            }

            error_msg = error_messages.get(
                status_code,
                f"❌ Server error (HTTP {status_code}). Please try again later.",
            )

            self.logger.error(
                f"HTTP {status_code} error for server {server_name}: {http_err}"
            )
            raise ConnectionError(error_msg)
        else:
            raise ConnectionError(f"❌ Authentication failed: {http_err}")

    def get_form_definition(self, form_id: str) -> tuple[pd.DataFrame, pd.DataFrame]:
        """Get form definition (questions and choices)."""
        if not self._scto_client:
            raise ConnectionError("Not connected to server")

        try:
            form_def = self._scto_client.get_form_definition(form_id)

        except Exception as e:
            raise SurveyCTOError(f"Failed to get form definition: {e}")  # noqa: B904

        questions = pd.DataFrame(
            form_def["fieldsRowsAndColumns"][1:],
            columns=form_def["fieldsRowsAndColumns"][0],
        )

        choices = pd.DataFrame(
            form_def["choicesRowsAndColumns"][1:],
            columns=form_def["choicesRowsAndColumns"][0],
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
                self._scto_client = self._scto_client = pysurveycto.SurveyCTOObject(
                    credentials.server, credentials.user, credentials.password
                )
            except ConnectionError:
                raise ConnectionError("Not connected to server") from None
        try:
            # Try server dataset first
            return self._import_server_dataset(form_config)
        except:
            return self._import_regular_form(form_config)

    def _import_server_dataset(self, form_config: FormConfig) -> int:
        """Import from server dataset."""
        data_csv = self._scto_client.get_server_dataset(form_config.form_id)
        data = pl.read_csv(data_csv.encode())

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
            else (pd.DataFrame(), self.config.default_date)
        )

        if not form_config.refresh:
            return 0

        # Get new data
        new_data_json = self._scto_client.get_form_data(
            form_id=form_config.form_id,
            format="json",
            oldest_completion_date=last_date,
            key=self._import_private_key(form_config.private_key)
            if form_config.private_key
            else False,
        )

        new_data = pd.DataFrame(new_data_json)
        new_count = len(new_data)

        # Combine data
        if not existing_data.empty:
            combined_data = pd.concat([existing_data, new_data], ignore_index=True)
        else:
            combined_data = new_data

        # Process data types
        questions, _ = self.get_form_definition(form_config.form_id)
        questions = questions[questions.get("disabled", "") != "yes"]
        combined_data = self.data_processor.convert_data_types(combined_data, questions)

        # Download media if requested
        if form_config.attachments and form_config.save_to:
            self._download_attachments(questions, new_data, form_config)

        # Save data
        if form_config.save_to:
            combined_data.to_csv(form_config.save_to, index=False)

        # Save to DuckDB
        duckdb_save_table(
            self.project_id, combined_data, alias=form_config.alias, db_name="raw"
        )

        return new_count

    def _download_attachments(
        self, questions: pd.DataFrame, data: pd.DataFrame, form_config: FormConfig
    ) -> None:
        """Download media attachments."""
        media_types = {e.value for e in MediaType}
        media_fields = questions[questions["type"].isin(media_types)]["name"].tolist()

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
                use_container_width=True,
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
            logo_path = self._get_logo_path()
            if logo_path and Path(logo_path).exists():
                st.image(logo_path, width=200)
            else:
                st.markdown("### SurveyCTO Form Configuration")

            # Credential selection
            login_credentials = list_stored_credentials(self.project_id).get(
                "credentials", {}
            )
            if not login_credentials:
                st.warning(
                    "No SurveyCTO servers configured. Please connect to a server using the credential manager."
                )
                return

            select_cred = st.selectbox(
                "Select Server Credentials*",
                options=list(login_credentials.keys()),
                index=None,
                help="Select the server credentials to use for this form",
                key="scto_select_cred",
            )

            try:
                server = login_credentials[select_cred]["server"]
                user = login_credentials[select_cred]["username"]
                scto_cred = retrieve_scto_credentials(
                    self.project_id, type="scto_login", server=server
                )
                if scto_cred:
                    password = scto_cred.get("credentials", "").get("password", "")

                # Validate credentials
                try:
                    self.client.connect(
                        ServerCredentials(server=server, user=user, password=password),
                        validate_permissions=False,
                    )
                except ConnectionError as e:
                    st.error(f"Connection failed: {e}")
                    return
            except KeyError:
                st.error(
                    "Invalid credentials selected. Please check your credential manager."
                )
                return
            # Form selection with dynamic loading
            forms_info = self._get_forms_info(
                ServerCredentials(server=server, user=user, password=password)
            )
            # concat form id and form names to create options
            form_options = [
                form[0] + " (" + form[1] + ")" for form in forms_info["forms_list"]
            ]

            form_ids_only = [form[0] for form in forms_info["forms_list"]]

            # Show form selection dropdown
            default_index = (
                form_ids_only.index(defaults.get("form_id", ""))
                if defaults and defaults.get("form_id", "") in form_ids_only
                else None
            )

            selected_form = st.selectbox(
                "Select Form ID*",
                options=form_options,
                index=default_index,
                help="Select a form from the available forms on the server",
            )

            # Show form details in an expander
            if selected_form:
                # split selected form into id and title
                selected_form_split = re.match(r"^(.*?) \((.*)\)$", selected_form)
                form_id = (
                    selected_form_split.group(1)
                    if selected_form_split
                    else selected_form
                )
                form_title = (
                    selected_form_split.group(2) if selected_form_split else "No title"
                )

                # get selected form index from form_options
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
            else:
                encrypted = False
                form_title = ""

            # remove symbols from form tile to create alias
            alias_default = re.sub(r"[^\w]", "_", form_title)
            alias = st.text_input(
                "Alias*",
                help="Unique identifier for this form",
                value=defaults.get("alias", alias_default),
                key=f"surveyctoui_alias{edit_mode}",
                disabled=edit_mode or not selected_form,
            )

            # Rest of the form fields
            private_key_file = st.text_input(
                "File path for Private Key",
                value=defaults.get("private_key", ""),
                disabled=not encrypted,
                key=f"surveyctoui_private_key{edit_mode}",
                help="Enter encryption key if the form is encrypted (optional) eg. C/Users/documents/Surevy_PRIVATEKEY.pem",
            )

            if not encrypted:
                private_key_file = ""

            if encrypted and not private_key_file:
                st.warning(
                    "Encryption key is required for encrypted forms. Only published fields will be downloaded."
                )

            # validate encryption key is a valid file path
            if private_key_file and not os.path.exists(str(private_key_file)):
                st.error("Encryption key must be a valid file path to a key file.")
                return

            # validate file has extension.pem
            if private_key_file and not private_key_file.endswith(".pem"):
                st.error("Encryption key file must have a .pem extension.")
                return

            save_file = st.text_input(
                "File path to save data",
                value=defaults.get("save_to", ""),
                disabled=not selected_form,
                help="File path to save the data (e.g., C:/Users/documents/data/survey.csv)",
            )

            # check that save file is a valid file path
            if save_file and os.path.exists(str(save_file)):
                save_path = Path(str(save_file)).parent
                if not save_path.exists():
                    st.error(
                        f"Save directory '{save_path}' does not exist. Please create it first."
                    )
                    return

            attachments = st.checkbox(
                "Download attachments",
                value=defaults.get("attachments", False),
                disabled=not selected_form,
                help="Download media files (images, audio, etc.)",
            )

            st.markdown("**required*")

            if st.button(
                "Add Form" if not edit_mode else "Update Form",
                type="primary",
                use_container_width=True,
                disabled=not selected_form,
            ):
                if not alias:
                    st.error("Please enter an alias for the form.")
                    return

                if not form_id:
                    st.error("Please select or enter a form ID.")
                    return

                form_config = FormConfig(
                    alias=alias,
                    form_id=form_id,
                    server=server,
                    username=user,
                    private_key=str(private_key_file) or None,
                    save_to=str(save_file) or None,
                    attachments=attachments,
                )

                if not edit_mode:
                    try:
                        self._add_form_to_project(form_config)
                        st.success("Form added successfully")
                    except Exception as e:
                        st.error(f"Failed to add form: {e}")
                        return
                else:
                    # Update existing form configuration
                    try:
                        self._update_form_on_project(form_config)
                        st.success("Form updated successfully")
                    except Exception as e:
                        st.error(f"Failed to update form: {e}")
                        return

                st.rerun()

    def _get_form_options(self, server: str) -> list[tuple[str, str]] | None:
        """
        Get list of available forms for the selected server.

        Returns
        -------
            List of tuples (form_id, form_title) or None if connection failed
        """
        try:
            with st.spinner(f"Loading forms from {server}..."):
                # Get list of forms
                forms = self._scto_client.list_forms()

                form_options = []
                for form in forms:
                    try:
                        # Get form definition to extract title
                        form_def = self._scto_client.get_form_definition(form)

                        # Extract title from form definition
                        title = self._extract_form_title(form_def, form)
                        form_options.append((form, title))

                    except Exception as e:
                        # If we can't get the title, just use the form ID
                        self.logger.warning(f"Could not get title for form {form}: {e}")
                        form_options.append((form, "Title unavailable"))

                # Sort by form ID for consistency
                form_options.sort(key=lambda x: x[0])
                return form_options

        except Exception as e:
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
            # Try to get title from settings
            if "settings" in form_def:
                settings = form_def["settings"]
                if isinstance(settings, list) and len(settings) > 1:
                    # Settings is usually a list where first row is headers
                    headers = settings[0] if settings else []
                    data = settings[1] if len(settings) > 1 else []

                    # Look for title in common field names
                    title_fields = ["form_title", "title", "form_name", "name"]
                    for field in title_fields:
                        if field in headers:
                            index = headers.index(field)
                            if index < len(data) and data[index]:
                                return str(data[index])

            # Try to get title from survey sheet
            if "fieldsRowsAndColumns" in form_def:
                fields = form_def["fieldsRowsAndColumns"]
                if len(fields) > 1:
                    headers = fields[0]
                    # Look for a title field in the first few rows
                    for i in range(1, min(5, len(fields))):
                        row = fields[i]
                        if len(row) > 1 and "title" in str(row).lower():
                            # This is a heuristic - might need adjustment
                            continue
            else:
                # If no title found, return form_id
                return form_id

        except Exception as e:
            self.logger.warning(f"Error extracting title for form {form_id}: {e}")
            return form_id

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
