"""Tests for the settings utilities module."""

import json
from unittest.mock import MagicMock, patch

from datasure.utils.settings_utils import (
    get_check_config_settings,
    get_hash_id,
    load_check_settings,
    save_check_settings,
    trigger_save,
)


class TestSaveCheckSettings:
    """Test the save_check_settings function."""

    def test_save_check_settings_new_file(self, tmp_path):
        """Test saving settings to a new file."""
        settings_file = tmp_path / "test_settings.json"
        check_name = "test_check"
        check_settings = {"param1": "value1", "param2": 42}

        save_check_settings(str(settings_file), check_name, check_settings)

        # Verify file was created and contains correct data
        assert settings_file.exists()
        with open(settings_file) as f:
            data = json.load(f)

        assert check_name in data
        assert data[check_name] == check_settings

    def test_save_check_settings_existing_file(self, tmp_path):
        """Test saving settings to an existing file."""
        settings_file = tmp_path / "test_settings.json"

        # Create initial file with some data
        initial_data = {"existing_check": {"old_param": "old_value"}}
        with open(settings_file, "w") as f:
            json.dump(initial_data, f)

        check_name = "new_check"
        check_settings = {"param1": "value1", "param2": 42}

        save_check_settings(str(settings_file), check_name, check_settings)

        # Verify both old and new data exist
        with open(settings_file) as f:
            data = json.load(f)

        assert "existing_check" in data
        assert "new_check" in data
        assert data["existing_check"] == {"old_param": "old_value"}
        assert data["new_check"] == check_settings

    def test_save_check_settings_update_existing(self, tmp_path):
        """Test updating settings for an existing check."""
        settings_file = tmp_path / "test_settings.json"
        check_name = "test_check"

        # Save initial settings
        initial_settings = {"param1": "value1", "param2": 42}
        save_check_settings(str(settings_file), check_name, initial_settings)

        # Update with new settings
        update_settings = {"param2": 100, "param3": "new_value"}
        save_check_settings(str(settings_file), check_name, update_settings)

        # Verify settings were merged correctly
        with open(settings_file) as f:
            data = json.load(f)

        expected = {"param1": "value1", "param2": 100, "param3": "new_value"}
        assert data[check_name] == expected


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

    @patch("datasure.utils.settings_utils.duckdb_get_table")
    def test_get_check_config_settings_success(self, mock_duckdb_get_table):
        """Test successful retrieval of check config settings."""
        # Mock the polars DataFrame returned by duckdb_get_table
        mock_df = MagicMock()
        mock_df.row.return_value = [
            "test_page",  # page_name
            "survey_data",  # survey_data_name
            "survey_key_123",  # survey_key
            "survey_id_456",  # survey_id
            "2024-01-01",  # survey_date
            "enumerator_1",  # enumerator
            100,  # survey_target
            "backcheck_data",  # backcheck_data_name
            "2024-01-15",  # backcheck_date
            "backchecker_1",  # backchecker
            10,  # backcheck_target_percent
            "tracking_data",  # tracking_data_name
        ]
        mock_duckdb_get_table.return_value = mock_df

        project_id = "test_project"
        page_row_index = 0

        result = get_check_config_settings(project_id, page_row_index)

        # Verify duckdb_get_table was called correctly
        mock_duckdb_get_table.assert_called_once_with(
            project_id=project_id, alias="check_config", db_name="logs"
        )

        # Verify the row method was called with correct index
        assert mock_df.row.call_count == 12  # Called once for each column
        mock_df.row.assert_called_with(page_row_index)

        # Verify the returned tuple
        expected_result = (
            "test_page",
            "survey_data",
            "survey_key_123",
            "survey_id_456",
            "2024-01-01",
            "enumerator_1",
            100,
            "backcheck_data",
            "2024-01-15",
            "backchecker_1",
            10,
            "tracking_data",
        )
        assert result == expected_result

    @patch("datasure.utils.settings_utils.duckdb_get_table")
    def test_get_check_config_settings_different_row(self, mock_duckdb_get_table):
        """Test retrieval with different row index."""
        mock_df = MagicMock()
        mock_df.row.return_value = [
            "page2",
            "data2",
            "key2",
            "id2",
            "2024-02-01",
            "enum2",
            200,
            "back2",
            "2024-02-15",
            "backchecker2",
            20,
            "track2",
        ]
        mock_duckdb_get_table.return_value = mock_df

        project_id = "test_project"
        page_row_index = 5

        result = get_check_config_settings(project_id, page_row_index)

        # Verify the row method was called with correct index
        assert mock_df.row.call_count == 12  # Called once for each column
        mock_df.row.assert_called_with(page_row_index)

        assert result[0] == "page2"
        assert result[1] == "data2"


class TestSettingsUtilsIntegration:
    """Integration tests for settings utilities."""

    def test_save_and_load_integration(self, tmp_path):
        """Test full workflow of saving and loading settings."""
        settings_file = tmp_path / "integration_test.json"
        check_name = "integration_check"
        original_settings = {
            "threshold": 0.95,
            "enabled": True,
            "categories": ["A", "B", "C"],
            "metadata": {"version": "1.0", "author": "test"},
        }

        # Save settings
        save_check_settings(str(settings_file), check_name, original_settings)

        # Load settings
        loaded_settings = load_check_settings(str(settings_file), check_name)

        # Verify they match
        assert loaded_settings == original_settings

    def test_multiple_checks_workflow(self, tmp_path):
        """Test workflow with multiple checks in same file."""
        settings_file = tmp_path / "multi_check_test.json"

        # Save multiple checks
        checks = {
            "check1": {"param1": "value1"},
            "check2": {"param2": "value2", "param3": 123},
            "check3": {"param4": [1, 2, 3]},
        }

        for check_name, settings in checks.items():
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
