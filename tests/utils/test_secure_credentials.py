"""Tests for secure credential storage functionality.

Tests cover keyring backend failures, migration scenarios, and cross-platform
compatibility for the secure_credentials module used in scto.py and import_view.py.
"""

import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from keyring.errors import KeyringError

from datasure.utils.secure_credentials import (
    SecureCredentialError,
    _get_metadata_path,
    _get_service_name,
    delete_stored_credentials,
    has_scto_credentials,
    list_stored_credentials,
    migrate_plaintext_credentials,
    retrieve_scto_credentials,
    store_scto_credentials,
    test_keyring_availability,
)


class TestKeyringAvailability:
    """Test keyring availability and backend detection."""

    @patch("datasure.utils.secure_credentials.keyring")
    def test_keyring_working_correctly(self, mock_keyring):
        """Test successful keyring operation."""
        # Mock successful keyring operations
        mock_keyring.set_password.return_value = None
        mock_keyring.get_password.return_value = "test_password_123"
        mock_keyring.delete_password.return_value = None

        # Mock backend name
        mock_backend = MagicMock()
        mock_backend.__class__.__name__ = "WinVaultKeyring"
        mock_keyring.get_keyring.return_value = mock_backend

        result = test_keyring_availability()

        assert result["success"] is True
        assert result["available"] is True
        assert result["backend"] == "WinVaultKeyring"
        assert "working correctly" in result["message"]

        # Verify keyring operations were called correctly
        mock_keyring.set_password.assert_called_once_with(
            "datasure_keyring_test", "test_user", "test_password_123"
        )
        mock_keyring.get_password.assert_called_once_with(
            "datasure_keyring_test", "test_user"
        )
        mock_keyring.delete_password.assert_called_once_with(
            "datasure_keyring_test", "test_user"
        )

    @patch("datasure.utils.secure_credentials.keyring")
    def test_keyring_password_mismatch(self, mock_keyring):
        """Test keyring test failure due to password mismatch."""
        mock_keyring.set_password.return_value = None
        mock_keyring.get_password.return_value = "wrong_password"
        mock_keyring.delete_password.return_value = None

        result = test_keyring_availability()

        assert result["success"] is False
        assert result["available"] is False
        assert "password mismatch" in result["error"]
        assert result["error_type"] == "test_failure"

    @patch("datasure.utils.secure_credentials.keyring")
    def test_keyring_backend_failure(self, mock_keyring):
        """Test keyring backend failure scenarios."""
        mock_keyring.set_password.side_effect = KeyringError("Backend not available")

        result = test_keyring_availability()

        assert result["success"] is False
        assert result["available"] is False
        assert "Keyring error" in result["error"]
        assert result["error_type"] == "keyring_error"

    @patch("datasure.utils.secure_credentials.keyring")
    def test_keyring_unexpected_error(self, mock_keyring):
        """Test unexpected errors during keyring testing."""
        mock_keyring.set_password.side_effect = Exception("Unexpected error")

        result = test_keyring_availability()

        assert result["success"] is False
        assert result["available"] is False
        assert "Unexpected error" in result["error"]
        assert result["error_type"] == "unknown_error"

    @pytest.mark.parametrize(
        "backend_name,expected",
        [
            ("WinVaultKeyring", "WinVaultKeyring"),
            ("MacOSKeyring", "MacOSKeyring"),
            ("SecretServiceKeyring", "SecretServiceKeyring"),
            ("ChainerBackend", "ChainerBackend"),
        ],
    )
    @patch("datasure.utils.secure_credentials.keyring")
    def test_cross_platform_backends(self, mock_keyring, backend_name, expected):
        """Test detection of different platform-specific keyring backends."""
        mock_keyring.set_password.return_value = None
        mock_keyring.get_password.return_value = "test_password_123"
        mock_keyring.delete_password.return_value = None

        mock_backend = MagicMock()
        mock_backend.__class__.__name__ = backend_name
        mock_keyring.get_keyring.return_value = mock_backend

        result = test_keyring_availability()

        assert result["success"] is True
        assert result["backend"] == expected


class TestCredentialStorage:
    """Test credential storage and retrieval operations."""

    @patch("datasure.utils.secure_credentials.keyring")
    @patch("datasure.utils.secure_credentials._get_metadata_path")
    def test_store_credentials_success(self, mock_metadata_path, mock_keyring):
        """Test successful credential storage."""
        # Setup mocks
        mock_keyring.set_password.return_value = None

        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_file = Path(temp_dir) / "metadata.json"
            mock_metadata_path.return_value = metadata_file

            result = store_scto_credentials(
                project_id="test_project",
                server="testserver",
                username="test@example.com",
                password="secret123",
            )

            service_name = _get_service_name(
                "test_project", server="testserver", credential_type="scto_login"
            )

            assert result["success"] is True
            assert "stored securely" in result["message"]
            assert result["metadata"][service_name]["server"] == "testserver"
            assert result["metadata"][service_name]["username"] == "test@example.com"

            # Verify keyring was called
            mock_keyring.set_password.assert_called_once()

            # Verify metadata file was created
            assert metadata_file.exists()
            with open(metadata_file) as f:
                metadata = json.load(f)
                assert metadata[service_name]["server"] == "testserver"
                assert metadata[service_name]["username"] == "test@example.com"

    @patch("datasure.utils.secure_credentials.keyring")
    def test_store_credentials_keyring_error(self, mock_keyring):
        """Test credential storage with keyring failure."""
        mock_keyring.set_password.side_effect = KeyringError("Access denied")

        result = store_scto_credentials(
            project_id="test_project",
            server="testserver",
            username="test@example.com",
            password="secret123",
        )

        assert result["success"] is False
        assert "Failed to store credentials in system keyring" in result["error"]
        assert result["error_type"] == "keyring_error"

    @patch("datasure.utils.secure_credentials.keyring")
    @patch("datasure.utils.secure_credentials._get_metadata_path")
    def test_retrieve_credentials_success(self, mock_metadata_path, mock_keyring):
        """Test successful credential retrieval."""
        # Setup metadata file
        service_name = _get_service_name(
            "test_project", server="testserver", credential_type="scto_login"
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_file = Path(temp_dir) / "metadata.json"
            metadata = {
                service_name: {
                    "server": "testserver",
                    "username": "test@example.com",
                    "credential_type": "scto_login",
                }
            }
            with open(metadata_file, "w") as f:
                json.dump(metadata, f)

            mock_metadata_path.return_value = metadata_file
            mock_keyring.get_password.return_value = "secret123"

            result = retrieve_scto_credentials(
                "test_project", "testserver", "scto_login"
            )

            assert result["success"] is True
            assert result["credentials"]["server"] == "testserver"
            assert result["credentials"]["username"] == "test@example.com"
            assert result["credentials"]["password"] == "secret123"

    @patch("datasure.utils.secure_credentials._get_metadata_path")
    def test_retrieve_credentials_not_found(self, mock_metadata_path):
        """Test credential retrieval when no credentials exist."""
        mock_metadata_path.return_value = Path("/nonexistent/path")

        result = retrieve_scto_credentials("test_project", "testserver", "scto_login")

        assert result["success"] is False
        assert "No credentials found" in result["error"]
        assert result["error_type"] == "not_found"

    @patch("datasure.utils.secure_credentials.keyring")
    @patch("datasure.utils.secure_credentials._get_metadata_path")
    def test_retrieve_credentials_password_missing(
        self, mock_metadata_path, mock_keyring
    ):
        """Test credential retrieval when password not found in keyring."""
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_file = Path(temp_dir) / "metadata.json"
            metadata = {
                "server": "testserver",
                "username": "test@example.com",
                "service_name": "datasure_scto_scto_test_project",
            }
            with open(metadata_file, "w") as f:
                json.dump(metadata, f)

            mock_metadata_path.return_value = metadata_file
            mock_keyring.get_password.return_value = None

            result = retrieve_scto_credentials(
                "test_project", "testserver", "scto_login"
            )

            assert result["success"] is False


class TestCredentialMigration:
    """Test migration of legacy plaintext credentials."""

    @patch("datasure.utils.secure_credentials.store_scto_credentials")
    @patch("datasure.utils.secure_credentials.get_cache_path")
    def test_migrate_plaintext_success(self, mock_cache_path, mock_store):
        """Test successful migration of plaintext credentials."""
        # Setup legacy credential file
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_file = Path(temp_dir) / "scto.json"
            legacy_creds = {
                "server": "testserver",
                "user": "test@example.com",  # Note: legacy format uses "user"
                "password": "secret123",
            }
            with open(legacy_file, "w") as f:
                json.dump(legacy_creds, f)

            mock_cache_path.return_value = legacy_file
            mock_store.return_value = {"success": True, "message": "Stored"}

            result = migrate_plaintext_credentials(
                "test_project", delete_plaintext=True
            )

            assert result["success"] is True
            assert "migrated successfully" in result["message"]

            # Verify store_scto_credentials was called with correct parameters
            mock_store.assert_called_once_with(
                project_id="test_project",
                server="testserver",
                username="test@example.com",
                password="secret123",
                migration_source=str(legacy_file),
                migrated_at=str(Path.cwd()),
            )

            # Verify file was deleted (secure deletion with overwrite)
            assert not legacy_file.exists()

    @patch("datasure.utils.secure_credentials.get_cache_path")
    def test_migrate_plaintext_file_not_found(self, mock_cache_path):
        """Test migration when legacy file doesn't exist."""
        mock_cache_path.return_value = Path("/nonexistent/file.json")

        result = migrate_plaintext_credentials("test_project")

        assert result["success"] is False
        assert "Plaintext credential file not found" in result["error"]
        assert result["error_type"] == "file_not_found"

    @patch("datasure.utils.secure_credentials.get_cache_path")
    def test_migrate_plaintext_invalid_format(self, mock_cache_path):
        """Test migration with invalid credential format."""
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_file = Path(temp_dir) / "scto.json"
            invalid_creds = {"server": "testserver"}  # Missing user and password
            with open(legacy_file, "w") as f:
                json.dump(invalid_creds, f)

            mock_cache_path.return_value = legacy_file

            result = migrate_plaintext_credentials("test_project")

            assert result["success"] is False
            assert "Invalid plaintext credential format" in result["error"]
            assert result["error_type"] == "invalid_format"

    @patch("datasure.utils.secure_credentials.store_scto_credentials")
    @patch("datasure.utils.secure_credentials.get_cache_path")
    def test_migrate_plaintext_store_failure(self, mock_cache_path, mock_store):
        """Test migration when secure storage fails."""
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_file = Path(temp_dir) / "scto.json"
            legacy_creds = {
                "server": "testserver",
                "user": "test@example.com",
                "password": "secret123",
            }
            with open(legacy_file, "w") as f:
                json.dump(legacy_creds, f)

            mock_cache_path.return_value = legacy_file
            mock_store.return_value = {
                "success": False,
                "error": "Keyring not available",
            }

            result = migrate_plaintext_credentials("test_project")

            assert result["success"] is False
            assert result["error"] == "Keyring not available"

    @patch("datasure.utils.secure_credentials.store_scto_credentials")
    @patch("datasure.utils.secure_credentials.get_cache_path")
    def test_migrate_plaintext_delete_failure(self, mock_cache_path, mock_store):
        """Test migration when plaintext file deletion fails."""
        with tempfile.TemporaryDirectory() as temp_dir:
            legacy_file = Path(temp_dir) / "scto.json"

            # Create the file first
            legacy_creds = {
                "server": "testserver",
                "user": "test@example.com",
                "password": "secret123",
            }
            with open(legacy_file, "w") as f:
                json.dump(legacy_creds, f)

            mock_cache_path.return_value = legacy_file
            mock_store.return_value = {"success": True, "message": "Stored"}

            # Mock the file operations to fail during deletion
            original_open = open

            def mock_open_side_effect(*args, **kwargs):
                path_str = str(args[0]) if args else ""
                mode = kwargs.get("mode", args[1] if len(args) > 1 else "r")

                # Allow reading the file normally
                if "r" in mode and "+" not in mode:
                    return original_open(*args, **kwargs)
                # Fail on write operations for deletion
                if "r+b" in mode or ("w" in mode and legacy_file.name in path_str):
                    raise OSError("Permission denied")
                return original_open(*args, **kwargs)

            with patch("builtins.open", side_effect=mock_open_side_effect):
                result = migrate_plaintext_credentials(
                    "test_project", delete_plaintext=True
                )

            assert result["success"] is True
            assert "warning" in result
            assert "could not delete plaintext file" in result["warning"]


class TestCredentialHelpers:
    """Test helper functions for credential management."""

    @patch("datasure.utils.secure_credentials._get_metadata_path")
    def test_has_scto_credentials_true(self, mock_metadata_path):
        """Test has_scto_credentials when credentials exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_file = Path(temp_dir) / "metadata.json"
            metadata_file.touch()
            mock_metadata_path.return_value = metadata_file

            result = has_scto_credentials("test_project")
            assert result is True

    @patch("datasure.utils.secure_credentials._get_metadata_path")
    def test_has_scto_credentials_false(self, mock_metadata_path):
        """Test has_scto_credentials when credentials don't exist."""
        mock_metadata_path.return_value = Path("/nonexistent/file.json")

        result = has_scto_credentials("test_project")
        assert result is False

    @patch("datasure.utils.secure_credentials.get_cache_path")
    def test_list_stored_credentials(self, mock_cache_path):
        """Test listing all stored credentials."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            mock_cache_path.return_value = cache_dir

            # Create mock project directories with credential metadata
            project1_dir = cache_dir / "project1" / "settings"
            project1_dir.mkdir(parents=True)
            metadata1 = {
                "datasure_scto_login_server1_project1": {
                    "server": "server1",
                    "username": "user1@example.com",
                    "credential_type": "scto_login",
                }
            }
            with open(project1_dir / "credential_metadata.json", "w") as f:
                json.dump(metadata1, f)

            result = list_stored_credentials(project_id="project1")

            assert result["success"] is True
            assert result["count"] == 1


class TestCrossPlatformCompatibility:
    """Test cross-platform compatibility scenarios."""

    @pytest.mark.parametrize(
        "platform,expected_backend",
        [
            ("win32", "WinVaultKeyring"),
            ("darwin", "MacOSKeyring"),
            ("linux", "SecretServiceKeyring"),
        ],
    )
    @patch("datasure.utils.secure_credentials.keyring")
    def test_platform_specific_backends(self, mock_keyring, platform, expected_backend):
        """Test that different platforms use appropriate keyring backends."""
        mock_keyring.set_password.return_value = None
        mock_keyring.get_password.return_value = "test_password_123"
        mock_keyring.delete_password.return_value = None

        mock_backend = MagicMock()
        mock_backend.__class__.__name__ = expected_backend
        mock_keyring.get_keyring.return_value = mock_backend

        with patch("sys.platform", platform):
            result = test_keyring_availability()

        assert result["success"] is True
        assert result["backend"] == expected_backend

    @patch("datasure.utils.secure_credentials.keyring")
    def test_fallback_backend_handling(self, mock_keyring):
        """Test handling of fallback/unsupported keyring backends."""
        mock_keyring.set_password.return_value = None
        mock_keyring.get_password.return_value = "test_password_123"
        mock_keyring.delete_password.return_value = None

        # Simulate unsupported/fallback backend
        mock_backend = MagicMock()
        mock_backend.__class__.__name__ = "PlaintextKeyring"
        mock_keyring.get_keyring.return_value = mock_backend

        result = test_keyring_availability()

        assert result["success"] is True
        assert result["backend"] == "PlaintextKeyring"
        # Should still work but with warning that it's not secure

    @patch("datasure.utils.secure_credentials.Path.chmod")
    def test_permission_setting_cross_platform(self, mock_chmod):
        """Test file permission setting across platforms."""
        # Test when chmod is not supported (e.g., Windows)
        mock_chmod.side_effect = NotImplementedError("chmod not supported")

        with (
            tempfile.TemporaryDirectory() as temp_dir,
            patch("datasure.utils.secure_credentials._get_metadata_path") as mock_path,
        ):
            metadata_file = Path(temp_dir) / "metadata.json"
            mock_path.return_value = metadata_file

            with patch("datasure.utils.secure_credentials.keyring") as mock_keyring:
                mock_keyring.set_password.return_value = None

                result = store_scto_credentials(
                    project_id="test_project",
                    server="testserver",
                    username="test@example.com",
                    password="secret123",
                )

                # Should succeed even if chmod fails
                assert result["success"] is True


# Integration test for the main workflows used in the application
class TestIntegrationWorkflows:
    """Integration tests for complete workflows used in scto.py and import_view.py."""

    @patch("datasure.utils.secure_credentials.keyring")
    @patch("datasure.utils.secure_credentials.get_cache_path")
    def test_complete_credential_workflow(self, mock_cache_path, mock_keyring):
        """Test complete workflow: test keyring -> store -> retrieve -> migrate."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Setup keyring mocks - need to handle both test and actual credentials
            def mock_get_password(service, username):
                if service == "datasure_keyring_test" and username == "test_user":
                    return "test_password_123"  # For keyring availability test
                elif username == "test@example.com":
                    return "secret123"  # For actual credentials
                return None

            mock_keyring.set_password.return_value = None
            mock_keyring.get_password.side_effect = mock_get_password
            mock_keyring.delete_password.return_value = None

            mock_backend = MagicMock()
            mock_backend.__class__.__name__ = "WinVaultKeyring"
            mock_keyring.get_keyring.return_value = mock_backend

            # Setup cache path
            cache_dir = Path(temp_dir)
            settings_dir = cache_dir / "test_project" / "settings"
            settings_dir.mkdir(parents=True)

            def cache_path_side_effect(*args):
                if len(args) == 1:
                    return cache_dir
                elif len(args) == 3:
                    return settings_dir / args[2]
                return (
                    cache_dir / "test_project" / "settings" / "credential_metadata.json"
                )

            mock_cache_path.side_effect = cache_path_side_effect

            # 1. Test keyring availability (as used in scto_login_form)
            keyring_result = test_keyring_availability()
            assert keyring_result["success"] is True
            assert keyring_result["backend"] == "WinVaultKeyring"

            # 2. Store credentials (as used in scto_login_form)
            store_result = store_scto_credentials(
                project_id="test_project",
                server="testserver",
                username="test@example.com",
                password="secret123",
            )
            assert store_result["success"] is True

            # 3. Check if credentials exist (as used in scto_add_form)
            has_creds = has_scto_credentials("test_project")
            assert has_creds is True

            # 4. Retrieve credentials (as used in scto_get_server_cache)
            retrieve_result = retrieve_scto_credentials(
                "test_project", "testserver", "scto_login"
            )
            assert retrieve_result["success"] is True
            assert retrieve_result["credentials"]["server"] == "testserver"

            # 5. Test migration scenario with legacy file
            legacy_file = settings_dir / "scto.json"
            legacy_creds = {
                "server": "testserver",
                "user": "test@example.com",
                "password": "secret123",
            }
            with open(legacy_file, "w") as f:
                json.dump(legacy_creds, f)

            migrate_result = migrate_plaintext_credentials(
                "test_project", delete_plaintext=True
            )
            assert migrate_result["success"] is True
            assert not legacy_file.exists()  # Should be deleted after migration

    @patch("datasure.utils.secure_credentials.keyring")
    def test_keyring_failure_workflow(self, mock_keyring):
        """Test workflow when keyring fails (fallback scenarios)."""
        # Simulate keyring failure
        mock_keyring.set_password.side_effect = KeyringError(
            "No keyring backend available"
        )

        # 1. Test keyring availability shows failure
        keyring_result = test_keyring_availability()
        assert keyring_result["success"] is False
        assert keyring_result["error_type"] == "keyring_error"

        # 2. Store credentials should fail gracefully
        store_result = store_scto_credentials(
            project_id="test_project",
            server="testserver",
            username="test@example.com",
            password="secret123",
        )
        assert store_result["success"] is False
        assert store_result["error_type"] == "keyring_error"

        # 3. Has credentials should return False
        has_creds = has_scto_credentials("test_project")
        assert has_creds is False

        # 4. Retrieve should fail
        retrieve_result = retrieve_scto_credentials("test_project", "testserver")
        assert retrieve_result["success"] is False
        assert retrieve_result["error_type"] == "not_found"


class TestHelperFunctions:
    """Test internal helper functions."""

    def test_get_service_name_default(self):
        """Test service name generation with defaults."""
        service_name = _get_service_name("test1234")
        expected = "datasure_scto_login__test1234"
        assert service_name == expected

    def test_get_service_name_with_server(self):
        """Test service name generation with server."""
        service_name = _get_service_name("test1234", server="testserver")
        expected = "datasure_scto_login_testserver_test1234"
        assert service_name == expected

    def test_get_service_name_custom_type(self):
        """Test service name generation with custom type."""
        service_name = _get_service_name(
            "test1234", server="testserver", credential_type="custom"
        )
        expected = "datasure_custom_testserver_test1234"
        assert service_name == expected

    @patch("datasure.utils.secure_credentials.get_cache_path")
    def test_get_metadata_path(self, mock_get_cache_path):
        """Test metadata path generation."""
        expected_path = Path("/cache/test1234/settings/credential_metadata.json")
        mock_get_cache_path.return_value = expected_path

        result = _get_metadata_path("test1234")
        assert result == expected_path
        mock_get_cache_path.assert_called_once_with(
            "test1234", "settings", "credential_metadata.json"
        )


class TestSecureCredentialError:
    """Test SecureCredentialError exception."""

    def test_secure_credential_error_creation(self):
        """Test creating SecureCredentialError."""
        error = SecureCredentialError("Test error message")
        assert str(error) == "Test error message"
        assert isinstance(error, Exception)


class TestExtendedStorageScenarios:
    """Test extended storage scenarios and edge cases."""

    @patch("datasure.utils.secure_credentials._get_metadata_path")
    @patch("datasure.utils.secure_credentials.keyring")
    def test_store_credentials_with_additional_metadata(
        self, mock_keyring, mock_metadata_path
    ):
        """Test storing credentials with additional metadata."""
        mock_keyring.set_password.return_value = None

        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_file = Path(temp_dir) / "metadata.json"
            mock_metadata_path.return_value = metadata_file

            result = store_scto_credentials(
                project_id="test_project",
                server="testserver",
                username="test@example.com",
                password="secret123",
                custom_field="custom_value",
                migration_source="/old/path",
            )

            assert result["success"] is True

            # Check additional metadata was stored
            with open(metadata_file, encoding="utf-8") as f:
                metadata = json.load(f)
                service_data = next(iter(metadata.values()))
                assert service_data["custom_field"] == "custom_value"
                assert service_data["migration_source"] == "/old/path"

    @patch("datasure.utils.secure_credentials._get_metadata_path")
    @patch("datasure.utils.secure_credentials.keyring")
    def test_store_credentials_unexpected_error(self, mock_keyring, mock_metadata_path):
        """Test handling of unexpected errors during storage."""
        mock_keyring.set_password.side_effect = RuntimeError("Unexpected error")

        result = store_scto_credentials(
            project_id="test_project",
            server="testserver",
            username="test@example.com",
            password="secret123",
        )

        assert result["success"] is False
        assert "Unexpected error storing credentials" in result["error"]
        assert result["error_type"] == "unknown_error"


class TestExtendedRetrievalScenarios:
    """Test extended retrieval scenarios and edge cases."""

    @patch("datasure.utils.secure_credentials._get_metadata_path")
    @patch("datasure.utils.secure_credentials.keyring")
    def test_retrieve_credentials_keyring_error(self, mock_keyring, mock_metadata_path):
        """Test credential retrieval with keyring error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_file = Path(temp_dir) / "metadata.json"
            service_name = "datasure_scto_login_testserver_test_project"
            metadata = {
                service_name: {
                    "server": "testserver",
                    "username": "test@example.com",
                    "credential_type": "scto_login",
                }
            }
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f)

            mock_metadata_path.return_value = metadata_file
            mock_keyring.get_password.side_effect = KeyringError(
                "Keyring access denied"
            )

            result = retrieve_scto_credentials("test_project", "testserver")

            assert result["success"] is False
            assert "Failed to retrieve password from keyring" in result["error"]
            assert result["error_type"] == "keyring_error"

    @patch("datasure.utils.secure_credentials._get_metadata_path")
    def test_retrieve_credentials_metadata_missing_service(self, mock_metadata_path):
        """Test credential retrieval when service not found in metadata."""
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_file = Path(temp_dir) / "metadata.json"
            metadata = {"other_service": {"username": "other@example.com"}}
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f)

            mock_metadata_path.return_value = metadata_file

            result = retrieve_scto_credentials("test_project", "testserver")

            assert result["success"] is False
            assert "Invalid credential metadata" in result["error"]
            assert result["error_type"] == "invalid_metadata"

    @patch("datasure.utils.secure_credentials._get_metadata_path")
    def test_retrieve_credentials_unexpected_error(self, mock_metadata_path):
        """Test handling of unexpected errors during retrieval."""
        mock_metadata_path.side_effect = RuntimeError("Unexpected error")

        result = retrieve_scto_credentials("test_project", "testserver")

        assert result["success"] is False
        assert "Unexpected error retrieving credentials" in result["error"]
        assert result["error_type"] == "unknown_error"


class TestDeleteCredentials:
    """Test credential deletion functionality."""

    @patch("datasure.utils.secure_credentials._get_metadata_path")
    @patch("datasure.utils.secure_credentials.keyring")
    def test_delete_credentials_success(self, mock_keyring, mock_metadata_path):
        """Test successful credential deletion."""
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_file = Path(temp_dir) / "metadata.json"
            service_name = "datasure_scto_login_testserver_test_project"
            metadata = {
                service_name: {
                    "server": "testserver",
                    "username": "test@example.com",
                    "credential_type": "scto_login",
                },
                "other_service": {
                    "server": "otherserver",
                    "username": "other@example.com",
                    "credential_type": "scto_login",
                },
            }
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f)

            mock_metadata_path.return_value = metadata_file
            mock_keyring.delete_password.return_value = None

            result = delete_stored_credentials("test_project", "testserver")

            assert result["success"] is True
            assert "deleted successfully" in result["message"]

            # Verify service was removed from metadata
            with open(metadata_file, encoding="utf-8") as f:
                updated_metadata = json.load(f)
            assert service_name not in updated_metadata
            assert "other_service" in updated_metadata  # Other services remain

    @patch("datasure.utils.secure_credentials._get_metadata_path")
    def test_delete_credentials_not_found(self, mock_metadata_path):
        """Test deleting non-existent credentials."""
        mock_metadata_path.return_value = Path("/nonexistent/path")

        result = delete_stored_credentials("test_project", "testserver")

        assert result["success"] is True
        assert "No credentials found to delete" in result["message"]

    @patch("datasure.utils.secure_credentials._get_metadata_path")
    @patch("datasure.utils.secure_credentials.keyring")
    def test_delete_credentials_keyring_warning(self, mock_keyring, mock_metadata_path):
        """Test deletion with keyring warning."""
        with tempfile.TemporaryDirectory() as temp_dir:
            metadata_file = Path(temp_dir) / "metadata.json"
            service_name = "datasure_scto_login_testserver_test_project"
            metadata = {
                service_name: {
                    "server": "testserver",
                    "username": "test@example.com",
                    "credential_type": "scto_login",
                }
            }
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f)

            mock_metadata_path.return_value = metadata_file
            mock_keyring.delete_password.side_effect = KeyringError("Access denied")

            result = delete_stored_credentials("test_project", "testserver")

            # Should still succeed but log warning
            assert result["success"] is True

    @patch("datasure.utils.secure_credentials._get_metadata_path")
    def test_delete_credentials_unexpected_error(self, mock_metadata_path):
        """Test handling unexpected error during deletion."""
        mock_metadata_path.side_effect = RuntimeError("Unexpected error")

        result = delete_stored_credentials("test_project", "testserver")

        assert result["success"] is False
        assert "Error deleting credentials" in result["error"]
        assert result["error_type"] == "deletion_error"


class TestListCredentialsExtended:
    """Test extended list credentials functionality."""

    @patch("datasure.utils.secure_credentials.get_cache_path")
    def test_list_stored_credentials_empty(self, mock_cache_path):
        """Test listing credentials when none exist."""
        with tempfile.TemporaryDirectory() as temp_dir:
            mock_cache_path.return_value = Path(temp_dir)

            result = list_stored_credentials("test_project")

            assert result["success"] is True
            assert result["count"] == 0
            assert result["credentials"] == {}

    @patch("datasure.utils.secure_credentials.get_cache_path")
    def test_list_stored_credentials_json_error(self, mock_cache_path):
        """Test listing credentials with JSON decode error."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            project_dir = cache_dir / "test_project" / "settings"
            project_dir.mkdir(parents=True)

            # Create invalid JSON file
            metadata_file = project_dir / "credential_metadata.json"
            metadata_file.write_text("invalid json")

            mock_cache_path.return_value = cache_dir

            result = list_stored_credentials("test_project")

            # Should handle error gracefully
            assert result["success"] is True
            assert result["count"] == 0

    @patch("datasure.utils.secure_credentials.get_cache_path")
    def test_list_stored_credentials_unexpected_error(self, mock_cache_path):
        """Test handling unexpected error during listing."""
        mock_cache_path.side_effect = RuntimeError("Unexpected error")

        result = list_stored_credentials("test_project")

        assert result["success"] is False
        assert "Error listing stored credentials" in result["error"]
        assert result["error_type"] == "listing_error"

    @patch("datasure.utils.secure_credentials.get_cache_path")
    def test_list_stored_credentials_with_data(self, mock_cache_path):
        """Test listing credentials with actual data."""
        with tempfile.TemporaryDirectory() as temp_dir:
            cache_dir = Path(temp_dir)
            project_dir = cache_dir / "test_project" / "settings"
            project_dir.mkdir(parents=True)

            # Create valid metadata
            metadata = {
                "datasure_scto_login_server1_test_project": {
                    "server": "server1",
                    "username": "user1@example.com",
                    "credential_type": "scto_login",
                },
                "datasure_scto_login_server2_test_project": {
                    "server": "server2",
                    "username": "user2@example.com",
                    "credential_type": "scto_login",
                },
            }

            metadata_file = project_dir / "credential_metadata.json"
            with open(metadata_file, "w", encoding="utf-8") as f:
                json.dump(metadata, f)

            mock_cache_path.return_value = cache_dir

            result = list_stored_credentials("test_project")

            assert result["success"] is True
            assert result["count"] == 2
            assert len(result["credentials"]) == 2

            # Check credential structure
            creds = result["credentials"]
            keys = list(creds.keys())
            assert any("server1" in key for key in keys)
            assert any("server2" in key for key in keys)
