"""Tests for file security utilities."""

import json
import os
import subprocess
import tempfile
from unittest.mock import Mock, patch

import polars as pl
import pytest

from datasure.utils.file_security import (
    FileSecurityConfig,
    SecurityError,
    VirusScanner,
    _contains_suspicious_content,
    _validate_csv_content,
    _validate_dataframe_security,
    _validate_json_content,
    _validate_mime_type,
    calculate_file_hash,
    get_file_info,
    secure_read_data,
    validate_file_security,
)


class TestFileSecurityConfig:
    """Test FileSecurityConfig constants."""

    def test_max_file_sizes(self):
        """Test that file size limits are reasonable."""
        assert FileSecurityConfig.MAX_FILE_SIZES["csv"] == 100 * 1024 * 1024
        assert FileSecurityConfig.MAX_FILE_SIZES["xlsx"] == 50 * 1024 * 1024
        assert FileSecurityConfig.MAX_FILE_SIZES["json"] == 10 * 1024 * 1024

    def test_allowed_mime_types(self):
        """Test MIME type mappings exist for all supported extensions."""
        for ext in ["csv", "xlsx", "xls", "json", "dta"]:
            assert ext in FileSecurityConfig.ALLOWED_MIME_TYPES
            assert isinstance(FileSecurityConfig.ALLOWED_MIME_TYPES[ext], list)

    def test_suspicious_patterns(self):
        """Test suspicious content patterns are defined."""
        assert len(FileSecurityConfig.SUSPICIOUS_PATTERNS) > 0
        assert any(
            "script" in pattern for pattern in FileSecurityConfig.SUSPICIOUS_PATTERNS
        )


class TestSuspiciousContentDetection:
    """Test suspicious content detection functions."""

    def test_contains_suspicious_content_clean(self):
        """Test clean content is not flagged."""
        clean_texts = [
            "John Doe",
            "Survey Response 123",
            "2023-01-01",
            "Normal data value",
            "",
            None,
        ]

        for text in clean_texts:
            if text is not None:
                assert not _contains_suspicious_content(text)

    def test_contains_suspicious_content_malicious(self):
        """Test malicious content is detected."""
        malicious_texts = [
            "<script>alert('xss')</script>",
            "javascript:void(0)",
            "<?php echo 'test'; ?>",
            "<%= malicious %>",
            "data:text/html;base64,PHNjcmlwdD4=",
            "union select * from users",
        ]

        for text in malicious_texts:
            assert _contains_suspicious_content(text)

    def test_contains_suspicious_content_case_insensitive(self):
        """Test detection is case insensitive."""
        assert _contains_suspicious_content("JAVASCRIPT:alert(1)")
        assert _contains_suspicious_content("Script src=evil")

    def test_contains_suspicious_content_long_strings(self):
        """Test very long strings are handled safely."""
        long_string = "a" * 20000
        assert not _contains_suspicious_content(long_string)


class TestFileValidation:
    """Test file validation functions."""

    def test_validate_file_security_nonexistent(self):
        """Test validation fails for non-existent files."""
        is_valid, error = validate_file_security("/nonexistent/file.csv")
        assert not is_valid
        assert "does not exist" in error

    def test_validate_file_security_unsupported_extension(self):
        """Test validation fails for unsupported extensions."""
        with tempfile.NamedTemporaryFile(suffix=".exe", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            is_valid, error = validate_file_security(temp_path)
            assert not is_valid
            assert "Unsupported file type" in error
        finally:
            os.unlink(temp_path)

    def test_validate_file_security_too_large(self):
        """Test validation fails for oversized files."""
        # Create a file larger than JSON limit (10MB)
        large_content = "x" * (11 * 1024 * 1024)

        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(large_content.encode())
            temp_path = f.name

        try:
            is_valid, error = validate_file_security(temp_path)
            assert not is_valid
            assert "too large" in error
        finally:
            os.unlink(temp_path)


class TestCSVValidation:
    """Test CSV file validation."""

    def test_validate_csv_content_clean(self):
        """Test clean CSV content passes validation."""
        csv_content = "name,age,city\nJohn,25,NYC\nJane,30,LA"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            assert _validate_csv_content(temp_path)
        finally:
            os.unlink(temp_path)

    def test_validate_csv_content_too_many_columns(self):
        """Test CSV with too many columns fails validation."""
        # Create CSV with more than MAX_COLUMNS
        headers = [f"col_{i}" for i in range(FileSecurityConfig.MAX_COLUMNS + 1)]
        csv_content = ",".join(headers) + "\n" + ",".join(["value"] * len(headers))

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            assert not _validate_csv_content(temp_path)
        finally:
            os.unlink(temp_path)

    def test_validate_csv_content_suspicious_headers(self):
        """Test CSV with suspicious headers fails validation."""
        csv_content = "name,<script>alert(1)</script>,city\nJohn,25,NYC"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            assert not _validate_csv_content(temp_path)
        finally:
            os.unlink(temp_path)


class TestJSONValidation:
    """Test JSON file validation."""

    def test_validate_json_content_clean(self):
        """Test clean JSON content passes validation."""
        json_data = {"name": "John", "age": 25, "city": "NYC"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_data, f)
            temp_path = f.name

        try:
            assert _validate_json_content(temp_path)
        finally:
            os.unlink(temp_path)

    def test_validate_json_content_too_many_keys(self):
        """Test JSON with too many keys fails validation."""
        json_data = {f"key_{i}": f"value_{i}" for i in range(10001)}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_data, f)
            temp_path = f.name

        try:
            assert not _validate_json_content(temp_path)
        finally:
            os.unlink(temp_path)

    def test_validate_json_content_suspicious_values(self):
        """Test JSON with suspicious values fails validation."""
        json_data = {"name": "John", "script": "<script>alert(1)</script>"}

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(json_data, f)
            temp_path = f.name

        try:
            assert not _validate_json_content(temp_path)
        finally:
            os.unlink(temp_path)


class TestDataFrameValidation:
    """Test DataFrame security validation."""

    def test_validate_dataframe_security_clean(self):
        """Test clean DataFrame passes validation."""
        df = pl.DataFrame(
            {"name": ["John", "Jane"], "age": [25, 30], "city": ["NYC", "LA"]}
        )

        # Should not raise any exception
        _validate_dataframe_security(df)

    def test_validate_dataframe_security_too_many_rows(self):
        """Test DataFrame with too many rows fails validation."""
        # Create DataFrame with more than 1M rows
        large_data = {"col1": list(range(1000001))}
        df = pl.DataFrame(large_data)

        with pytest.raises(SecurityError, match="too large"):
            _validate_dataframe_security(df)

    def test_validate_dataframe_security_too_many_columns(self):
        """Test DataFrame with too many columns fails validation."""
        # Create DataFrame with more than MAX_COLUMNS
        wide_data = {f"col_{i}": [1] for i in range(FileSecurityConfig.MAX_COLUMNS + 1)}
        df = pl.DataFrame(wide_data)

        with pytest.raises(SecurityError, match="Too many columns"):
            _validate_dataframe_security(df)

    def test_validate_dataframe_security_suspicious_content(self):
        """Test DataFrame with suspicious content fails validation."""
        df = pl.DataFrame(
            {
                "name": ["John", "Jane"],
                "comment": ["Normal comment", "<script>alert(1)</script>"],
            }
        )

        with pytest.raises(SecurityError, match="Suspicious content detected"):
            _validate_dataframe_security(df)


class TestSecureReadData:
    """Test secure data reading functions."""

    def test_secure_read_data_csv(self):
        """Test secure CSV reading."""
        csv_content = "name,age,city\nJohn,25,NYC\nJane,30,LA"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            df = secure_read_data(temp_path)
            assert isinstance(df, pl.DataFrame)
            assert df.height == 2
            assert df.width == 3
        finally:
            os.unlink(temp_path)

    def test_secure_read_data_invalid_file(self):
        """Test secure reading fails for invalid files."""
        with pytest.raises(SecurityError):
            secure_read_data("/nonexistent/file.csv")

    def test_secure_read_data_unsupported_extension(self):
        """Test secure reading fails for unsupported extensions."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as f:
            f.write(b"test content")
            temp_path = f.name

        try:
            with pytest.raises(SecurityError, match="Unsupported file type"):
                secure_read_data(temp_path)
        finally:
            os.unlink(temp_path)


class TestFileInfo:
    """Test file information functions."""

    def test_calculate_file_hash(self):
        """Test file hash calculation."""
        content = b"test file content"

        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            file_hash = calculate_file_hash(temp_path)
            assert isinstance(file_hash, str)
            assert len(file_hash) == 64  # SHA-256 hex length
            assert file_hash != "error"
        finally:
            os.unlink(temp_path)

    def test_calculate_file_hash_nonexistent(self):
        """Test hash calculation for non-existent file."""
        file_hash = calculate_file_hash("/nonexistent/file.txt")
        assert file_hash == "error"

    def test_get_file_info(self):
        """Test comprehensive file information retrieval."""
        content = b"test file content"

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
            f.write(content)
            temp_path = f.name

        try:
            file_info = get_file_info(temp_path)

            assert "size_bytes" in file_info
            assert "size_mb" in file_info
            assert "extension" in file_info
            assert "hash" in file_info
            assert "hash_short" in file_info

            assert file_info["size_bytes"] == len(content)
            assert file_info["extension"] == ".CSV"
            assert len(file_info["hash_short"]) == 16
        finally:
            os.unlink(temp_path)


class TestVirusScanner:
    """Test virus scanner functionality."""

    def test_virus_scanner_availability_detection(self):
        """Test virus scanner availability detection."""
        # This will depend on the system, so we just test it doesn't crash
        is_available = VirusScanner.is_available()
        assert isinstance(is_available, bool)

    @patch("subprocess.run")
    def test_virus_scanner_windows_defender(self, mock_run):
        """Test Windows Defender integration."""
        mock_run.return_value = Mock(returncode=0, stdout="", stderr="")

        with patch("os.name", "nt"):
            is_clean, result = VirusScanner.scan_file("test_file.txt")
            assert isinstance(is_clean, bool)
            assert isinstance(result, str)

    @patch("subprocess.run")
    def test_virus_scanner_clamav(self, mock_run):
        """Test ClamAV integration."""
        mock_run.return_value = Mock(returncode=0, stdout="OK", stderr="")

        with patch("os.name", "posix"):
            is_clean, result = VirusScanner.scan_file("test_file.txt")
            assert isinstance(is_clean, bool)
            assert isinstance(result, str)

    @patch("subprocess.run")
    def test_virus_scanner_timeout_handling(self, mock_run):
        """Test virus scanner timeout handling."""
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 30)

        is_clean, result = VirusScanner.scan_file("test_file.txt")
        assert is_clean  # Should default to clean on timeout
        assert "failed" in result.lower()


class TestMimeValidation:
    """Test MIME type validation."""

    def test_validate_mime_type_without_magic(self):
        """Test MIME validation gracefully handles missing python-magic."""
        with patch("datasure.utils.file_security.magic", None):
            # Should return True when magic is not available
            result = _validate_mime_type("test.csv", "csv")
            assert result is True

    @patch("datasure.utils.file_security.magic")
    def test_validate_mime_type_with_magic(self, mock_magic):
        """Test MIME validation with python-magic."""
        mock_magic.from_file.return_value = "text/csv"

        result = _validate_mime_type("test.csv", "csv")
        assert result is True

        mock_magic.from_file.assert_called_once_with("test.csv", mime=True)


# Integration tests
class TestSecurityIntegration:
    """Integration tests for security features."""

    def test_full_security_validation_pipeline(self):
        """Test complete security validation pipeline."""
        # Create a valid CSV file
        csv_content = "name,age,city\nJohn,25,NYC\nJane,30,LA"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(csv_content)
            temp_path = f.name

        try:
            # Test security validation
            is_valid, error = validate_file_security(temp_path)
            assert is_valid
            assert error is None

            # Test secure reading
            df = secure_read_data(temp_path)
            assert isinstance(df, pl.DataFrame)
            assert df.height == 2

            # Test file info
            file_info = get_file_info(temp_path)
            assert file_info["extension"] == ".CSV"

        finally:
            os.unlink(temp_path)

    def test_security_error_handling(self):
        """Test proper error handling throughout security pipeline."""
        # Test with malicious CSV
        malicious_csv = "name,<script>alert(1)</script>\nJohn,hack"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
            f.write(malicious_csv)
            temp_path = f.name

        try:
            # Security validation should catch this
            is_valid, error = validate_file_security(temp_path)
            assert not is_valid
            assert error is not None

            # Secure reading should also fail
            with pytest.raises(SecurityError):
                secure_read_data(temp_path)

        finally:
            os.unlink(temp_path)
