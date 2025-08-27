"""Tests for security settings utilities."""

from unittest.mock import patch

from datasure.utils.settings_utils import (
    SECURITY_SETTINGS,
    get_file_size_limit,
    get_security_setting,
    is_security_feature_enabled,
    validate_security_settings,
)


class TestSecuritySettings:
    """Test security settings configuration."""

    def test_security_settings_structure(self):
        """Test that security settings have expected structure."""
        assert "file_upload" in SECURITY_SETTINGS
        assert "data_processing" in SECURITY_SETTINGS

        file_upload = SECURITY_SETTINGS["file_upload"]
        assert "max_file_size_mb" in file_upload
        assert "enable_virus_scanning" in file_upload
        assert "enable_content_validation" in file_upload
        assert "allowed_extensions" in file_upload

    def test_security_settings_defaults(self):
        """Test security settings have reasonable defaults."""
        file_upload = SECURITY_SETTINGS["file_upload"]

        # Security features should be enabled by default (except virus scanning)
        assert file_upload["enable_content_validation"] is True
        assert file_upload["enable_mime_validation"] is True
        assert file_upload["enable_file_hashing"] is True
        assert file_upload["enable_suspicious_content_detection"] is True

        # Virus scanning disabled by default for compatibility
        assert file_upload["enable_virus_scanning"] is False

    def test_file_size_limits(self):
        """Test file size limits are reasonable."""
        size_limits = SECURITY_SETTINGS["file_upload"]["max_file_size_mb"]

        # CSV and DTA should have higher limits (data files)
        assert size_limits["csv"] >= 50
        assert size_limits["dta"] >= 50

        # Excel files should have moderate limits
        assert size_limits["xlsx"] >= 25
        assert size_limits["xls"] >= 25

        # JSON should have lower limit
        assert size_limits["json"] <= 25


class TestGetSecuritySetting:
    """Test get_security_setting function."""

    def test_get_existing_setting(self):
        """Test retrieving existing security setting."""
        result = get_security_setting("file_upload", "enable_content_validation")
        assert result is True

    def test_get_nonexistent_setting(self):
        """Test retrieving non-existent setting returns default."""
        result = get_security_setting(
            "file_upload", "nonexistent_setting", "default_value"
        )
        assert result == "default_value"

    def test_get_nonexistent_category(self):
        """Test retrieving from non-existent category returns default."""
        result = get_security_setting(
            "nonexistent_category", "setting", "default_value"
        )
        assert result == "default_value"

    def test_get_setting_none_default(self):
        """Test default None is handled correctly."""
        result = get_security_setting("file_upload", "nonexistent_setting")
        assert result is None


class TestIsSecurityFeatureEnabled:
    """Test is_security_feature_enabled function."""

    def test_content_validation_enabled(self):
        """Test content validation feature check."""
        result = is_security_feature_enabled("content_validation")
        assert result is True

    def test_virus_scanning_disabled(self):
        """Test virus scanning feature check (disabled by default)."""
        result = is_security_feature_enabled("virus_scanning")
        assert result is False

    def test_nonexistent_feature(self):
        """Test non-existent feature returns False."""
        result = is_security_feature_enabled("nonexistent_feature")
        assert result is False

    def test_all_expected_features(self):
        """Test all expected security features are recognized."""
        expected_features = [
            "virus_scanning",
            "content_validation",
            "mime_validation",
            "file_hashing",
            "suspicious_content_detection",
            "chunk_processing",
        ]

        for feature in expected_features:
            result = is_security_feature_enabled(feature)
            assert isinstance(result, bool)


class TestGetFileSizeLimit:
    """Test get_file_size_limit function."""

    def test_get_csv_limit(self):
        """Test CSV file size limit."""
        limit = get_file_size_limit("csv")
        assert limit == 100

    def test_get_excel_limit(self):
        """Test Excel file size limits."""
        xlsx_limit = get_file_size_limit("xlsx")
        xls_limit = get_file_size_limit("xls")
        assert xlsx_limit == 50
        assert xls_limit == 50

    def test_get_json_limit(self):
        """Test JSON file size limit."""
        limit = get_file_size_limit("json")
        assert limit == 10

    def test_get_stata_limit(self):
        """Test Stata file size limit."""
        limit = get_file_size_limit("dta")
        assert limit == 100

    def test_get_unsupported_extension_limit(self):
        """Test unsupported extension returns default."""
        limit = get_file_size_limit("unsupported")
        assert limit == 50  # Default value

    def test_case_insensitive_extension(self):
        """Test extension matching is case insensitive."""
        limit_lower = get_file_size_limit("csv")
        limit_upper = get_file_size_limit("CSV")
        assert limit_lower == limit_upper


class TestValidateSecuritySettings:
    """Test validate_security_settings function."""

    def test_validate_returns_expected_structure(self):
        """Test validation returns expected result structure."""
        result = validate_security_settings()

        assert "valid" in result
        assert "warnings" in result
        assert "recommendations" in result
        assert "status" in result

        assert isinstance(result["warnings"], list)
        assert isinstance(result["recommendations"], list)
        assert isinstance(result["status"], dict)

    @patch("datasure.utils.settings_utils.VirusScanner")
    def test_validate_with_virus_scanner_available(self, mock_scanner):
        """Test validation when virus scanner is available."""
        mock_scanner.is_available.return_value = True

        result = validate_security_settings()

        assert "virus_scanning" in result["status"]
        virus_status = result["status"]["virus_scanning"]
        assert virus_status["available"] is True
        assert virus_status["recommended"] is True

    @patch("datasure.utils.settings_utils.VirusScanner")
    def test_validate_with_virus_scanner_unavailable(self, mock_scanner):
        """Test validation when virus scanner is unavailable."""
        mock_scanner.is_available.return_value = False

        result = validate_security_settings()

        assert "virus_scanning" in result["status"]
        virus_status = result["status"]["virus_scanning"]
        assert virus_status["available"] is False

    @patch("datasure.utils.settings_utils.VirusScanner")
    def test_validate_virus_scanner_import_error(self, mock_scanner):
        """Test validation handles VirusScanner import errors."""
        # Simulate import error
        with patch(
            "datasure.utils.settings_utils.VirusScanner", side_effect=ImportError
        ):
            result = validate_security_settings()

            assert "virus_scanning" in result["status"]
            virus_status = result["status"]["virus_scanning"]
            assert virus_status["available"] is False

    def test_validate_content_validation_status(self):
        """Test content validation status in validation."""
        result = validate_security_settings()

        assert "content_validation" in result["status"]
        content_status = result["status"]["content_validation"]
        assert content_status["enabled"] is True
        assert content_status["recommended"] is True

    @patch.dict(
        "datasure.utils.settings_utils.SECURITY_SETTINGS",
        {
            "file_upload": {
                "enable_content_validation": False,
                "max_file_size_mb": {"csv": 300},
            }
        },
    )
    def test_validate_with_warnings(self):
        """Test validation generates warnings for risky settings."""
        result = validate_security_settings()

        # Should warn about disabled content validation
        assert len(result["warnings"]) > 0
        assert any(
            "content validation" in warning.lower() for warning in result["warnings"]
        )

        # Should warn about large file size limit
        assert any(
            "large file size" in warning.lower() for warning in result["warnings"]
        )

    @patch("datasure.utils.settings_utils.VirusScanner")
    def test_validate_generates_recommendations(self, mock_scanner):
        """Test validation generates recommendations."""
        mock_scanner.is_available.return_value = True

        result = validate_security_settings()

        # Should recommend enabling virus scanning if available but disabled
        assert len(result["recommendations"]) > 0
        assert any("virus scanning" in rec.lower() for rec in result["recommendations"])


class TestSecuritySettingsIntegration:
    """Integration tests for security settings."""

    def test_settings_consistency(self):
        """Test that settings are internally consistent."""
        # File extensions in size limits should match allowed extensions
        size_limits = SECURITY_SETTINGS["file_upload"]["max_file_size_mb"]
        allowed_extensions = SECURITY_SETTINGS["file_upload"]["allowed_extensions"]

        for ext in allowed_extensions:
            assert ext in size_limits, f"Missing size limit for {ext}"

    def test_all_features_testable(self):
        """Test that all security features can be tested."""
        # Get all features from the feature mapping
        test_features = [
            "virus_scanning",
            "content_validation",
            "mime_validation",
            "file_hashing",
            "suspicious_content_detection",
            "chunk_processing",
        ]

        for feature in test_features:
            # Should not raise exception
            result = is_security_feature_enabled(feature)
            assert isinstance(result, bool)

    def test_size_limits_reasonable(self):
        """Test that all file size limits are reasonable."""
        size_limits = SECURITY_SETTINGS["file_upload"]["max_file_size_mb"]

        for ext, limit in size_limits.items():
            assert isinstance(limit, int)
            assert 1 <= limit <= 500, f"Unreasonable size limit for {ext}: {limit}MB"

    def test_validation_comprehensive(self):
        """Test that validation covers all important settings."""
        result = validate_security_settings()

        # Should check virus scanning
        assert "virus_scanning" in result["status"]

        # Should check content validation
        assert "content_validation" in result["status"]

        # Should be able to generate both warnings and recommendations
        # (Even if empty, the lists should exist)
        assert isinstance(result["warnings"], list)
        assert isinstance(result["recommendations"], list)


# Edge case and error handling tests
class TestSecuritySettingsEdgeCases:
    """Test edge cases and error handling."""

    def test_get_security_setting_malformed_settings(self):
        """Test get_security_setting with malformed settings structure."""
        with patch("datasure.utils.settings_utils.SECURITY_SETTINGS", None):
            result = get_security_setting("category", "setting", "default")
            assert result == "default"

    def test_get_security_setting_attribute_error(self):
        """Test get_security_setting handles AttributeError."""
        with patch("datasure.utils.settings_utils.SECURITY_SETTINGS", "not_a_dict"):
            result = get_security_setting("category", "setting", "default")
            assert result == "default"

    def test_file_size_limit_empty_settings(self):
        """Test file size limit with empty settings."""
        with patch.dict(
            "datasure.utils.settings_utils.SECURITY_SETTINGS",
            {"file_upload": {"max_file_size_mb": {}}},
        ):
            limit = get_file_size_limit("csv")
            assert limit == 50  # Default

    def test_validation_with_empty_settings(self):
        """Test validation with minimal settings."""
        with patch.dict("datasure.utils.settings_utils.SECURITY_SETTINGS", {}):
            result = validate_security_settings()

            # Should still return valid structure
            assert "valid" in result
            assert "warnings" in result
            assert "recommendations" in result
            assert "status" in result
