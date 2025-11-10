"""Tests for the settings utilities module."""

import json
from unittest.mock import Mock, patch

import pytest
from pydantic import ValidationError

from datasure.utils.settings_utils import (
    ProjectID,
    get_check_config_settings,
    get_hash_id,
    load_check_settings,
    save_check_settings,
    trigger_save,
)


class TestProjectID:
    """Test the ProjectID Pydantic model."""

    def test_valid_project_id(self):
        """Test creating a valid project ID."""
        valid_ids = ["abc12345", "12345678", "a1b2c3d4", "00000000"]

        for project_id in valid_ids:
            obj = ProjectID(project_id=project_id)
            assert obj.project_id == project_id

    def test_invalid_project_id_length_too_short(self):
        """Test that project ID shorter than 8 characters is invalid."""
        with pytest.raises(ValidationError):
            ProjectID(project_id="abc123")

    def test_invalid_project_id_length_too_long(self):
        """Test that project ID longer than 8 characters is invalid."""
        with pytest.raises(ValidationError):
            ProjectID(project_id="abc123456")

    def test_invalid_project_id_special_characters(self):
        """Test that project ID with special characters is invalid."""
        invalid_ids = ["abc@1234", "abc-1234", "abc_1234", "abc 1234"]

        for project_id in invalid_ids:
            with pytest.raises(ValidationError, match="alphanumeric only"):
                ProjectID(project_id=project_id)

    def test_invalid_project_id_uppercase(self):
        """Test that project ID with uppercase is invalid."""
        with pytest.raises(ValidationError, match="alphanumeric only"):
            ProjectID(project_id="ABC12345")

    def test_project_id_edge_cases(self):
        """Test edge cases for project ID validation."""
        # All lowercase letters
        ProjectID(project_id="abcdefgh")

        # All numbers
        ProjectID(project_id="12345678")

        # Mixed
        ProjectID(project_id="a1b2c3d4")


class TestSaveCheckSettings:
    """Test the save_check_settings function."""

    @patch("datasure.utils.settings_utils.st")
    def test_save_check_settings_new_file(self, mock_st, tmp_path):
        """Test saving settings to a new file."""
        settings_file = tmp_path / "test_settings.json"
        check_name = "test_check"
        check_settings = {"param1": "value1", "param2": 42}

        # Mock session state to allow save
        state_name = check_name + "_param1"
        mock_st.session_state = {state_name: True}

        save_check_settings(str(settings_file), check_name, check_settings)

        # Verify file was created and contains correct data
        assert settings_file.exists()
        with open(settings_file) as f:
            data = json.load(f)

        assert check_name in data
        assert data[check_name] == check_settings
        # Verify session state was reset to False
        assert mock_st.session_state[state_name] is False

    @patch("datasure.utils.settings_utils.st")
    def test_save_check_settings_existing_file(self, mock_st, tmp_path):
        """Test saving settings to an existing file."""
        settings_file = tmp_path / "test_settings.json"

        # Create initial file with some data
        initial_data = {"existing_check": {"old_param": "old_value"}}
        with open(settings_file, "w") as f:
            json.dump(initial_data, f)

        check_name = "new_check"
        check_settings = {"param1": "value1", "param2": 42}

        # Mock session state to allow save
        state_name = check_name + "_param1"
        mock_st.session_state = {state_name: True}

        save_check_settings(str(settings_file), check_name, check_settings)

        # Verify both old and new data exist
        with open(settings_file) as f:
            data = json.load(f)

        assert "existing_check" in data
        assert "new_check" in data
        assert data["existing_check"] == {"old_param": "old_value"}
        assert data["new_check"] == check_settings

    @patch("datasure.utils.settings_utils.st")
    def test_save_check_settings_update_existing(self, mock_st, tmp_path):
        """Test updating settings for an existing check."""
        settings_file = tmp_path / "test_settings.json"
        check_name = "test_check"

        # Save initial settings
        initial_settings = {"param1": "value1", "param2": 42}
        state_name1 = check_name + "_param1"
        mock_st.session_state = {state_name1: True}
        save_check_settings(str(settings_file), check_name, initial_settings)

        # Update with new settings
        update_settings = {"param2": 100, "param3": "new_value"}
        state_name2 = check_name + "_param2"
        mock_st.session_state = {state_name2: True}
        save_check_settings(str(settings_file), check_name, update_settings)

        # Verify settings were merged correctly
        with open(settings_file) as f:
            data = json.load(f)

        expected = {"param1": "value1", "param2": 100, "param3": "new_value"}
        assert data[check_name] == expected

    @patch("datasure.utils.settings_utils.st")
    def test_save_check_settings_no_session_state(self, mock_st, tmp_path):
        """Test that save is skipped when session state is False."""
        settings_file = tmp_path / "test_settings.json"
        check_name = "test_check"
        check_settings = {"param1": "value1"}

        # Mock session state to False - should not save
        state_name = check_name + "_param1"
        mock_st.session_state = {state_name: False}

        save_check_settings(str(settings_file), check_name, check_settings)

        # Verify file was NOT created
        assert not settings_file.exists()

    @patch("datasure.utils.settings_utils.st")
    def test_save_check_settings_missing_session_state(self, mock_st, tmp_path):
        """Test that save is skipped when session state key is missing."""
        settings_file = tmp_path / "test_settings.json"
        check_name = "test_check"
        check_settings = {"param1": "value1"}

        # Mock session state without the key
        mock_st.session_state = {}

        save_check_settings(str(settings_file), check_name, check_settings)

        # Verify file was NOT created
        assert not settings_file.exists()


class TestLoadCheckSettings:
    """Test the load_check_settings function."""

    def test_load_check_settings_existing_file_and_check(self, tmp_path):
        """Test loading settings from existing file with existing check."""
        settings_file = tmp_path / "test_settings.json"
        check_name = "test_check"
        check_settings = {"param1": "value1", "param2": 42}

        # Create file with settings
        data = {check_name: check_settings}
        with open(settings_file, "w") as f:
            json.dump(data, f)

        result = load_check_settings(str(settings_file), check_name)

        assert result == check_settings

    def test_load_check_settings_nonexistent_file(self, tmp_path):
        """Test loading settings from non-existent file."""
        settings_file = tmp_path / "nonexistent.json"
        check_name = "test_check"

        result = load_check_settings(str(settings_file), check_name)

        assert result is None

    def test_load_check_settings_nonexistent_check(self, tmp_path):
        """Test loading settings for non-existent check."""
        settings_file = tmp_path / "test_settings.json"

        # Create file with different check
        data = {"other_check": {"param": "value"}}
        with open(settings_file, "w") as f:
            json.dump(data, f)

        result = load_check_settings(str(settings_file), "nonexistent_check")

        assert result is None

    def test_load_check_settings_empty_file(self, tmp_path):
        """Test loading settings from empty JSON file."""
        settings_file = tmp_path / "test_settings.json"

        # Create empty JSON file
        with open(settings_file, "w") as f:
            json.dump({}, f)

        result = load_check_settings(str(settings_file), "any_check")

        assert result is None


class TestTriggerSave:
    """Test the trigger_save function."""

    @patch("datasure.utils.settings_utils.st")
    def test_trigger_save_sets_session_state(self, mock_st):
        """Test that trigger_save sets session state to True."""
        state_name = "test_state"
        mock_st.session_state = {}

        trigger_save(state_name)

        assert mock_st.session_state[state_name] is True

    @patch("datasure.utils.settings_utils.st")
    def test_trigger_save_multiple_states(self, mock_st):
        """Test trigger_save with multiple different state names."""
        mock_st.session_state = {}

        trigger_save("state1")
        trigger_save("state2")

        assert mock_st.session_state["state1"] is True
        assert mock_st.session_state["state2"] is True


class TestGetHashId:
    """Test the get_hash_id function."""

    def test_get_hash_id_default_length(self):
        """Test get_hash_id with default length."""
        name = "test_project"
        result = get_hash_id(name)

        assert len(result) == 6
        assert isinstance(result, str)
        assert result.isalnum()  # Should be alphanumeric

    def test_get_hash_id_custom_length(self):
        """Test get_hash_id with custom length."""
        name = "test_project"
        custom_length = 10
        result = get_hash_id(name, length=custom_length)

        assert len(result) == custom_length
        assert isinstance(result, str)

    def test_get_hash_id_consistency(self):
        """Test that get_hash_id returns consistent results for same input."""
        name = "test_project"
        result1 = get_hash_id(name)
        result2 = get_hash_id(name)

        assert result1 == result2

    def test_get_hash_id_different_inputs(self):
        """Test that get_hash_id returns different results for different inputs."""
        name1 = "project1"
        name2 = "project2"
        result1 = get_hash_id(name1)
        result2 = get_hash_id(name2)

        assert result1 != result2

    def test_get_hash_id_edge_cases(self):
        """Test get_hash_id with edge case inputs."""
        # Empty string
        empty_result = get_hash_id("")
        assert len(empty_result) == 6

        # Very long string
        long_name = "a" * 1000
        long_result = get_hash_id(long_name)
        assert len(long_result) == 6

        # Special characters
        special_name = "test@#$%^&*(){}[]"
        special_result = get_hash_id(special_name)
        assert len(special_result) == 6

    def test_get_hash_id_unicode(self):
        """Test get_hash_id with Unicode characters."""
        unicode_name = "测试项目"  # Chinese characters
        result = get_hash_id(unicode_name)

        assert len(result) == 6
        assert isinstance(result, str)

    def test_get_hash_id_caching(self):
        """Test that get_hash_id uses LRU cache correctly."""
        name = "cache_test_project"

        # Clear any existing cache
        get_hash_id.cache_clear()

        # First call
        result1 = get_hash_id(name)
        cache_info1 = get_hash_id.cache_info()

        # Second call with same input
        result2 = get_hash_id(name)
        cache_info2 = get_hash_id.cache_info()

        assert result1 == result2
        assert cache_info1.hits == 0
        assert cache_info2.hits == 1


class TestGetCheckConfigSettings:
    """Test the get_check_config_settings function."""

    @patch("datasure.utils.settings_utils.ConfigurationService")
    def test_get_check_config_settings_success(self, mock_config_service):
        """Test successful retrieval of check config settings."""
        # Mock the ConfigurationService
        mock_service = Mock()
        mock_config_data = {
            "survey_id": "survey_id_456",
            "survey_date": "2024-01-01",
            "survey_target": 100,
        }
        mock_service.get_page_configuration.return_value = mock_config_data
        mock_config_service.return_value = mock_service

        project_id = "test_proj"
        page_row_index = 0

        result = get_check_config_settings(project_id, page_row_index)

        # Verify ConfigurationService was instantiated with correct project_id
        mock_config_service.assert_called_once_with(project_id)

        # Verify get_page_configuration was called with correct index
        mock_service.get_page_configuration.assert_called_once_with(page_row_index)

        # Verify the returned dict
        assert result == mock_config_data

    @patch("datasure.utils.settings_utils.ConfigurationService")
    def test_get_check_config_settings_different_row(self, mock_config_service):
        """Test retrieval with different row index."""
        mock_service = Mock()
        mock_config_data = {
            "survey_id": "id2",
            "survey_date": "2024-02-01",
            "survey_target": 200,
        }
        mock_service.get_page_configuration.return_value = mock_config_data
        mock_config_service.return_value = mock_service

        project_id = "test_proj"
        page_row_index = 5

        result = get_check_config_settings(project_id, page_row_index)

        # Verify get_page_configuration was called with correct index
        mock_service.get_page_configuration.assert_called_once_with(page_row_index)

        assert result == mock_config_data

    @patch("datasure.utils.settings_utils.ConfigurationService")
    def test_get_check_config_settings_empty_config(self, mock_config_service):
        """Test retrieval when config is None."""
        mock_service = Mock()
        mock_service.get_page_configuration.return_value = None
        mock_config_service.return_value = mock_service

        project_id = "test_proj"
        page_row_index = 0

        result = get_check_config_settings(project_id, page_row_index)

        # Should return empty dict when config is None
        assert result == {}


class TestSettingsUtilsIntegration:
    """Integration tests for settings utilities."""

    @patch("datasure.utils.settings_utils.st")
    def test_save_and_load_integration(self, mock_st, tmp_path):
        """Test full workflow of saving and loading settings."""
        settings_file = tmp_path / "integration_test.json"
        check_name = "integration_check"
        original_settings = {
            "threshold": 0.95,
            "enabled": True,
            "categories": ["A", "B", "C"],
            "metadata": {"version": "1.0", "author": "test"},
        }

        # Mock session state to allow save
        state_name = check_name + "_threshold"
        mock_st.session_state = {state_name: True}

        # Save settings
        save_check_settings(str(settings_file), check_name, original_settings)

        # Load settings
        loaded_settings = load_check_settings(str(settings_file), check_name)

        # Verify they match
        assert loaded_settings == original_settings

    @patch("datasure.utils.settings_utils.st")
    def test_multiple_checks_workflow(self, mock_st, tmp_path):
        """Test workflow with multiple checks in same file."""
        settings_file = tmp_path / "multi_check_test.json"

        # Save multiple checks
        checks = {
            "check1": {"param1": "value1"},
            "check2": {"param2": "value2", "param3": 123},
            "check3": {"param4": [1, 2, 3]},
        }

        for check_name, settings in checks.items():
            # Get first key from settings
            first_key = next(iter(settings.keys()))
            state_name = check_name + "_" + first_key
            mock_st.session_state = {state_name: True}
            save_check_settings(str(settings_file), check_name, settings)

        # Load all checks
        for check_name, expected_settings in checks.items():
            loaded_settings = load_check_settings(str(settings_file), check_name)
            assert loaded_settings == expected_settings

    def test_hash_consistency_across_calls(self):
        """Test that hash generation is consistent across multiple calls."""
        test_names = ["project1", "project2", "long_project_name_with_spaces"]

        # Generate hashes multiple times
        for name in test_names:
            hash1 = get_hash_id(name)
            hash2 = get_hash_id(name, length=6)
            hash3 = get_hash_id(name)

            assert hash1 == hash2 == hash3

        # Different lengths should give different results
        name = "test_project"
        hash_6 = get_hash_id(name, length=6)
        hash_8 = get_hash_id(name, length=8)
        hash_10 = get_hash_id(name, length=10)

        assert len(hash_6) == 6
        assert len(hash_8) == 8
        assert len(hash_10) == 10
        assert hash_6 == hash_8[:6]  # Should be prefix
        assert hash_6 == hash_10[:6]  # Should be prefix
