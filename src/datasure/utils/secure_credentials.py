"""Secure credential storage using system keyring.

This module provides secure credential storage for DataSure, replacing
plaintext JSON credential storage with OS-level secure storage.
"""

import json
import logging
from pathlib import Path
from typing import Any

import keyring
from keyring.errors import KeyringError

from .cache_utils import get_cache_path

logger = logging.getLogger(__name__)

# Service identifiers for keyring
SCTO_SERVICE_PREFIX = "datasure"
CREDENTIAL_METADATA_FILE = "credential_metadata.json"


class SecureCredentialError(Exception):
    """Exception raised when credential operations fail."""


def _get_service_name(
    project_id: str, server: str = "", credential_type: str = "scto_login"
) -> str:
    """Generate service name for keyring storage.

    Args:
        project_id: Project identifier
        credential_type: Type of credential (default: scto_login)

    Returns
    -------
        Service name for keyring
    """
    return f"{SCTO_SERVICE_PREFIX}_{credential_type}_{server}_{project_id}"


def _get_metadata_path(project_id: str) -> Path:
    """Get path to credential metadata file.

    Args:
        project_id: Project identifier

    Returns
    -------
        Path to metadata file
    """
    return get_cache_path(project_id, "settings", CREDENTIAL_METADATA_FILE)


def store_scto_credentials(
    project_id: str,
    username: str,
    password: str,
    server: str | None = None,
    type: str = "scto_login",
    **metadata: Any,
) -> dict[str, Any]:
    """Store SurveyCTO credentials securely using system keyring.

    Args:
        project_id: Project identifier
        server: SurveyCTO server name | None
        username: SurveyCTO username/email | Alias
        password: SurveyCTO password | private key
        **metadata: Additional metadata to store

    Returns
    -------
        Result dictionary with success/error status
    """
    if type not in ["scto_login"]:
        raise SecureCredentialError(
            f"Invalid credential type: {type}. Must be 'scto_login'"
        )
    try:
        service_name = _get_service_name(project_id, server, type)

        # Store password in system keyring
        keyring.set_password(service_name, username, password)

        # Store non-sensitive metadata in JSON file
        metadata_info = {
            service_name: {
                "server": server,
                "username": username,
                "credential_type": type,
                **metadata,
            }
        }

        metadata_path = _get_metadata_path(project_id)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing metadata
        if metadata_path.exists():
            try:
                with open(metadata_path, encoding="utf-8") as f:
                    existing_metadata = json.load(f)
            except Exception:
                print(f"Warning: Invalid JSON in {metadata_path}, starting fresh")
                logger.warning(f"Invalid JSON in {metadata_path}, starting fresh")
                existing_metadata = {}
        else:
            existing_metadata = {}

        # Update with new service info
        existing_metadata[service_name] = {
            "server": server,
            "username": username,
            "credential_type": type,
            **metadata,
        }

        # Save updated metadata
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(existing_metadata, f, indent=2)

            # Set restrictive permissions on metadata file (owner read/write only)
            try:
                metadata_path.chmod(0o600)
            except (OSError, NotImplementedError):
                # Windows or other systems may not support chmod
                logger.warning("Could not set restrictive permissions on metadata file")

            logger.info(f"Stored {type} credentials for project {project_id}")

    except KeyringError as e:
        error_msg = f"Failed to store credentials in system keyring: {e}"
        logger.exception(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "keyring_error",
        }

    except OSError as e:
        error_msg = f"Failed to store credential metadata: {e}"
        logger.exception(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "metadata_error",
        }

    except Exception as e:
        error_msg = f"Unexpected error storing credentials: {e}"
        logger.exception(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "unknown_error",
        }
    else:
        return {
            "success": True,
            "message": "Credentials stored securely",
            "metadata": metadata_info,
        }


def retrieve_scto_credentials(
    project_id: str, server: str, type: str = "scto_login"
) -> dict[str, Any]:
    """Retrieve SurveyCTO credentials from secure storage.

    Args:
        project_id: Project identifier

    Returns
    -------
        Result dictionary with credentials or error status
    """
    try:
        metadata_path = _get_metadata_path(project_id)

        if not metadata_path.exists():
            return {
                "success": False,
                "error": "No credentials found for this project",
                "error_type": "not_found",
            }

        # Load metadata
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)

        service_name = _get_service_name(project_id, server, type)
        if not service_name or service_name not in metadata:
            return {
                "success": False,
                "error": f"Invalid credential metadata: missing service '{service_name}'",
                "error_type": "invalid_metadata",
            }
        username = metadata.get(service_name).get("username")

        if not username:
            return {
                "success": False,
                "error": "Invalid credential metadata: missing username",
                "error_type": "invalid_metadata",
            }

        # Retrieve password from keyring
        password = keyring.get_password(service_name, username)

        if password is None:
            return {
                "success": False,
                "error": "Password not found in system keyring",
                "error_type": "password_not_found",
            }
        else:
            logger.info(f"Retrieved SCTO credentials for project {project_id}")
            return {
                "success": True,
                "credentials": {
                    "server": server,
                    "username": username,
                    "password": password,
                },
                "metadata": metadata,
            }
    except KeyringError as e:
        error_msg = f"Failed to retrieve password from keyring: {e}"
        logger.exception(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "keyring_error",
        }

    except (OSError, json.JSONDecodeError) as e:
        error_msg = f"Failed to read credential metadata: {e}"
        logger.exception(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "metadata_error",
        }

    except Exception as e:
        error_msg = f"Unexpected error retrieving credentials: {e}"
        logger.exception(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "unknown_error",
        }


def delete_stored_credentials(
    project_id: str, server: str, credential_type: str = "scto_login"
) -> dict[str, Any]:
    """Delete SurveyCTO credentials from secure storage.

    Args:
        project_id: Project identifier

    Returns
    -------
        Result dictionary with success/error status
    """
    try:
        metadata_path = _get_metadata_path(project_id)

        if not metadata_path.exists():
            return {
                "success": True,
                "message": "No credentials found to delete",
            }

        # Load metadata to get service info
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)

        service_name = metadata.get(
            "service_name", _get_service_name(project_id, server, credential_type)
        )
        username = metadata.get("username")

        # Delete from keyring
        if username:
            try:
                keyring.delete_password(service_name, username)
                logger.info(
                    f"Deleted password from keyring for {service_name}/{username}"
                )
            except KeyringError as e:
                logger.warning(f"Could not delete password from keyring: {e}")

        # Delete metadata file
        try:
            # remove service-specific metadata
            if service_name in metadata:
                del metadata[service_name]
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
            logger.info(
                f"Deleted credential {service_name} from metadata file: {metadata_path}"
            )
        except OSError as e:
            logger.warning(f"Could not delete metadata file: {e}")

    except Exception as e:
        error_msg = f"Error deleting credentials: {e}"
        logger.exception(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "deletion_error",
        }
    else:
        return {
            "success": True,
            "message": "Credentials deleted successfully",
        }


def has_scto_credentials(project_id: str) -> bool:
    """Check if SurveyCTO credentials exist for a project.

    Args:
        project_id: Project identifier

    Returns
    -------
        True if credentials exist, False otherwise
    """
    metadata_path = _get_metadata_path(project_id)
    return metadata_path.exists()


def list_stored_credentials(project_id: str) -> dict[str, Any]:
    """List stored credentials for current project.

    Returns
    -------
        Result dictionary with project list or error status
    """
    try:
        cache_base = get_cache_path()
        credentials = {}

        if cache_base.exists():
            metadata_path = (
                cache_base / project_id / "settings" / CREDENTIAL_METADATA_FILE
            )
            if metadata_path.exists():
                try:
                    with open(metadata_path, encoding="utf-8") as f:
                        metadata = json.load(f)

                    for k in metadata:
                        cred = metadata.get(k, {})
                        dict_key = f"{cred.get('credential_type', 'scto_login')} - {cred.get('server', '')} - {cred.get('username', '')}"
                        credentials[dict_key] = {
                            "server": cred.get("server"),
                            "username": cred.get("username"),
                            "credential_type": cred.get(
                                "credential_type", "scto_login"
                            ),
                        }
                except (json.JSONDecodeError, OSError):
                    logger.warning(f"Could not read metadata for {project_id}")
    except Exception as e:
        error_msg = f"Error listing stored credentials: {e}"
        logger.exception(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "listing_error",
        }

    return {
        "success": True,
        "credentials": credentials,
        "count": len(credentials),
    }


def test_keyring_availability() -> dict[str, Any]:
    """Test if keyring is available and working.

    Returns
    -------
        Result dictionary with keyring status
    """
    try:
        # Test storing and retrieving a test credential
        test_service = "datasure_keyring_test"
        test_username = "test_user"
        test_password = "test_password_123"

        # Store test credential
        keyring.set_password(test_service, test_username, test_password)

        # Retrieve test credential
        retrieved_password = keyring.get_password(test_service, test_username)

        # Clean up test credential
        keyring.delete_password(test_service, test_username)

        if retrieved_password == test_password:
            backend_name = keyring.get_keyring().__class__.__name__
            return {
                "success": True,
                "available": True,
                "backend": backend_name,
                "message": "Keyring is working correctly",
            }
        else:
            return {
                "success": False,
                "available": False,
                "error": "Keyring test failed: password mismatch",
                "error_type": "test_failure",
            }

    except KeyringError as e:
        return {
            "success": False,
            "available": False,
            "error": f"Keyring error: {e}",
            "error_type": "keyring_error",
        }

    except Exception as e:
        return {
            "success": False,
            "available": False,
            "error": f"Unexpected error: {e}",
            "error_type": "unknown_error",
        }


# Migration utilities for existing plaintext credentials


def migrate_plaintext_credentials(
    project_id: str,
    plaintext_file_path: Path | str | None = None,
    delete_plaintext: bool = False,
) -> dict[str, Any]:
    """Migrate existing plaintext credentials to secure storage.

    Args:
        project_id: Project identifier
        plaintext_file_path: Path to existing plaintext credential file
        delete_plaintext: Whether to delete plaintext file after migration

    Returns
    -------
        Result dictionary with migration status
    """
    try:
        # Default path for existing SCTO credentials
        if plaintext_file_path is None:
            plaintext_file_path = get_cache_path(project_id, "settings", "scto.json")
        else:
            plaintext_file_path = Path(plaintext_file_path)

        if not plaintext_file_path.exists():
            return {
                "success": False,
                "error": f"Plaintext credential file not found: {plaintext_file_path}",
                "error_type": "file_not_found",
            }

        # Read existing credentials
        with open(plaintext_file_path, encoding="utf-8") as f:
            plaintext_creds = json.load(f)

        server = plaintext_creds.get("server")
        username = plaintext_creds.get("user")  # Note: legacy format uses "user"
        password = plaintext_creds.get("password")

        if not all([server, username, password]):
            return {
                "success": False,
                "error": "Invalid plaintext credential format: missing server, user, or password",
                "error_type": "invalid_format",
            }

        # Store credentials securely
        result = store_scto_credentials(
            project_id=project_id,
            server=server,
            username=username,
            password=password,
            migration_source=str(plaintext_file_path),
            migrated_at=str(Path.cwd()),  # Simple timestamp replacement
        )

        if not result["success"]:
            return result

        # Optionally delete plaintext file after successful migration
        if delete_plaintext:
            try:
                # Secure deletion by overwriting with random data first
                import secrets

                file_size = plaintext_file_path.stat().st_size
                with open(plaintext_file_path, "r+b") as f:
                    f.write(secrets.token_bytes(file_size))
                    f.flush()

                plaintext_file_path.unlink()
                logger.info(
                    f"Securely deleted plaintext credential file: {plaintext_file_path}"
                )

            except Exception as e:
                logger.warning(f"Could not delete plaintext file: {e}")
                result["warning"] = (
                    f"Migration successful but could not delete plaintext file: {e}"
                )

        result["message"] = "Credentials migrated successfully to secure storage"
        result["plaintext_file"] = str(plaintext_file_path)
        result["delete_plaintext"] = delete_plaintext

    except Exception as e:
        error_msg = f"Error migrating plaintext credentials: {e}"
        logger.exception(error_msg)
        return {
            "success": False,
            "error": error_msg,
            "error_type": "migration_error",
        }
    else:
        return result
