"""Test the corrections module."""

import json
import os
import tempfile
from unittest.mock import patch

import polars as pl
import pytest

from src.processing.corrections import correction_apply_action, correction_load_log


@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Clean up temporary files
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_corrections_log():
    """Sample corrections log for testing."""
    return pl.DataFrame(
        {
            "KEY": ["key1", "key2", "key3"],
            "ID": ["id1", "id2", "id3"],
            "action": ["modify value", "remove value", "remove row"],
            "column": ["col1", "col2", "col3"],
            "current value": ["old1", "old2", "old3"],
            "new value": ["new1", "", ""],
            "reason": ["reason1", "reason2", "reason3"],
        }
    )


def test_correction_load_log_file_exists(temp_dir):
    """Test loading corrections log when file exists."""
    # Create a temporary JSON file with sample data
    log_data = [
        {
            "KEY": "key1",
            "ID": "id1",
            "action": "modify value",
            "column": "col1",
            "current value": "old_value",
            "new value": "new_value",
            "reason": "test reason",
        },
        {
            "KEY": "key2",
            "ID": "id2",
            "action": "remove value",
            "column": "col2",
            "current value": "remove_this",
            "new value": "",
            "reason": "removal reason",
        },
    ]

    # Create the expected directory structure
    project_id = "test_project"
    alias = "Test Log"
    settings_dir = os.path.join(temp_dir, project_id, "settings")
    os.makedirs(settings_dir, exist_ok=True)

    temp_file = os.path.join(settings_dir, "test_log.json")
    with open(temp_file, "w") as f:
        json.dump(log_data, f)

    # Mock the cache directory to point to our temp directory
    with patch("src.processing.corrections.pl.read_json") as mock_read_json:
        mock_read_json.return_value = pl.DataFrame(log_data)

        # Test loading the file
        result = correction_load_log(project_id, alias)

        # Verify the result
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 2
        assert result.item(0, "KEY") == "key1"
        assert result.item(0, "action") == "modify value"
        assert result.item(1, "KEY") == "key2"
        assert result.item(1, "action") == "remove value"

        # Verify the correct file path was used
        mock_read_json.assert_called_once_with(
            f"cache/{project_id}/settings/test_log.json"
        )


def test_correction_load_log_file_not_found():
    """Test loading corrections log when file doesn't exist."""
    project_id = "non_existent_project"
    alias = "Non Existent Log"

    result = correction_load_log(project_id, alias)

    # Verify empty DataFrame with correct schema
    assert isinstance(result, pl.DataFrame)
    assert len(result) == 0
    expected_columns = [
        "KEY",
        "ID",
        "action",
        "column",
        "current value",
        "new value",
        "reason",
    ]
    assert list(result.columns) == expected_columns

    # Verify column types
    assert result["KEY"].dtype == pl.String
    assert result["ID"].dtype == pl.String
    assert result["action"].dtype == pl.String


def test_correction_load_log_alias_transformation():
    """Test that alias parameter is properly transformed to filename."""
    project_id = "test_project"
    alias = "My Test Log-Name"

    # Mock pl.read_json to verify the correct file path is used
    with patch("src.processing.corrections.pl.read_json") as mock_read_json:
        mock_read_json.side_effect = FileNotFoundError()

        result = correction_load_log(project_id, alias)

        # Verify the file path transformation: spaces and hyphens should
        # become underscores
        expected_path = f"cache/{project_id}/settings/my_test_log_name.json"
        mock_read_json.assert_called_once_with(expected_path)

        # Should return empty DataFrame when file not found
        assert isinstance(result, pl.DataFrame)
        assert len(result) == 0


@patch("src.processing.corrections.st")
def test_correction_apply_action_modify_value_string_column(mock_st):
    """Test applying modify value action on string column."""
    # Setup mock session state
    mock_session_state = {
        "id_correction_log_0": pl.DataFrame(
            {
                "KEY": pl.Series([], dtype=pl.String),
                "ID": pl.Series([], dtype=pl.String),
                "action": pl.Series([], dtype=pl.String),
                "column": pl.Series([], dtype=pl.String),
                "current value": pl.Series([], dtype=pl.String),
                "new value": pl.Series([], dtype=pl.String),
                "reason": pl.Series([], dtype=pl.String),
            }
        ),
        "st_raw_dataset_list": ["Dataset 1"],
        "config_pages": {"Survey Data": ["Dataset 1"]},
        "prepped_data0": pl.DataFrame(
            {
                "survey_key": ["key1", "key2", "key3"],
                "name": ["John", "Jane", "Bob"],
                "age": [25, 30, 35],
            }
        ).to_pandas(),
    }
    mock_st.session_state = mock_session_state

    # Apply correction
    correction_apply_action(
        data_index=0,
        key_col="survey_key",
        project_id="test_project",
        action="modify value",
        key_value="key2",
        current_id="id2",
        current_value="Jane",
        col_to_modify="name",
        new_value="Janet",
        reason="Name correction",
    )

    # Verify the correction was applied
    corrected_data = mock_st.session_state["corrected_data0"]
    assert (
        corrected_data.filter(pl.col("survey_key") == "key2").item(0, "name") == "Janet"
    )

    # Verify the correction was logged
    log = mock_st.session_state["id_correction_log_0"]
    assert len(log) == 1
    assert log.item(0, "action") == "modify value"
    assert log.item(0, "new value") == "Janet"


@patch("src.processing.corrections.st")
def test_correction_apply_action_modify_value_numeric_column(mock_st):
    """Test applying modify value action on numeric column."""
    # Setup mock session state
    mock_session_state = {
        "id_correction_log_0": pl.DataFrame(
            {
                "KEY": pl.Series([], dtype=pl.String),
                "ID": pl.Series([], dtype=pl.String),
                "action": pl.Series([], dtype=pl.String),
                "column": pl.Series([], dtype=pl.String),
                "current value": pl.Series([], dtype=pl.String),
                "new value": pl.Series([], dtype=pl.String),
                "reason": pl.Series([], dtype=pl.String),
            }
        ),
        "st_raw_dataset_list": ["Dataset 1"],
        "config_pages": {"Survey Data": ["Dataset 1"]},
        "prepped_data0": pl.DataFrame(
            {
                "survey_key": ["key1", "key2", "key3"],
                "name": ["John", "Jane", "Bob"],
                "age": [25, 30, 35],
            }
        ).to_pandas(),
    }
    mock_st.session_state = mock_session_state

    # Apply correction to numeric column
    correction_apply_action(
        data_index=0,
        key_col="survey_key",
        project_id="test_project",
        action="modify value",
        key_value="key2",
        current_id="id2",
        current_value="30",
        col_to_modify="age",
        new_value="31",
        reason="Age correction",
    )

    # Verify the correction was applied
    corrected_data = mock_st.session_state["corrected_data0"]
    assert corrected_data.filter(pl.col("survey_key") == "key2").item(0, "age") == 31


@patch("src.processing.corrections.st")
def test_correction_apply_action_remove_value(mock_st):
    """Test applying remove value action."""
    # Setup mock session state
    mock_session_state = {
        "id_correction_log_0": pl.DataFrame(
            {
                "KEY": pl.Series([], dtype=pl.String),
                "ID": pl.Series([], dtype=pl.String),
                "action": pl.Series([], dtype=pl.String),
                "column": pl.Series([], dtype=pl.String),
                "current value": pl.Series([], dtype=pl.String),
                "new value": pl.Series([], dtype=pl.String),
                "reason": pl.Series([], dtype=pl.String),
            }
        ),
        "st_raw_dataset_list": ["Dataset 1"],
        "config_pages": {"Survey Data": ["Dataset 1"]},
        "prepped_data0": pl.DataFrame(
            {
                "survey_key": ["key1", "key2", "key3"],
                "name": ["John", "Jane", "Bob"],
                "age": [25, 30, 35],
            }
        ).to_pandas(),
    }
    mock_st.session_state = mock_session_state

    # Apply remove value correction
    correction_apply_action(
        data_index=0,
        key_col="survey_key",
        project_id="test_project",
        action="remove value",
        key_value="key2",
        current_id="id2",
        current_value="Jane",
        col_to_modify="name",
        new_value="",
        reason="Remove name",
    )

    # Verify the value was removed (set to None)
    corrected_data = mock_st.session_state["corrected_data0"]
    assert corrected_data.filter(pl.col("survey_key") == "key2").item(0, "name") is None


@patch("src.processing.corrections.st")
def test_correction_apply_action_remove_row(mock_st):
    """Test applying remove row action."""
    # Setup mock session state
    mock_session_state = {
        "id_correction_log_0": pl.DataFrame(
            {
                "KEY": pl.Series([], dtype=pl.String),
                "ID": pl.Series([], dtype=pl.String),
                "action": pl.Series([], dtype=pl.String),
                "column": pl.Series([], dtype=pl.String),
                "current value": pl.Series([], dtype=pl.String),
                "new value": pl.Series([], dtype=pl.String),
                "reason": pl.Series([], dtype=pl.String),
            }
        ),
        "st_raw_dataset_list": ["Dataset 1"],
        "config_pages": {"Survey Data": ["Dataset 1"]},
        "prepped_data0": pl.DataFrame(
            {
                "survey_key": ["key1", "key2", "key3"],
                "name": ["John", "Jane", "Bob"],
                "age": [25, 30, 35],
            }
        ).to_pandas(),
    }
    mock_st.session_state = mock_session_state

    # Apply remove row correction
    correction_apply_action(
        data_index=0,
        key_col="survey_key",
        project_id="test_project",
        action="remove row",
        key_value="key2",
        current_id="id2",
        current_value="Jane",
        col_to_modify="name",
        new_value="",
        reason="Remove entire row",
    )

    # Verify the row was removed
    corrected_data = mock_st.session_state["corrected_data0"]
    assert len(corrected_data) == 2
    assert not (corrected_data["survey_key"] == "key2").any()


@patch("src.processing.corrections.st")
def test_correction_apply_action_with_page_name(mock_st):
    """Test applying correction with page_name parameter."""
    # Setup mock session state
    mock_session_state = {
        "st_raw_dataset_list": ["Dataset 1"],
        "config_pages": {"Survey Data": ["Dataset 1"]},
    }
    mock_st.session_state = mock_session_state

    # Mock the correction_load_log function call
    with patch("src.processing.corrections.correction_load_log") as mock_load_log:
        mock_load_log.return_value = pl.DataFrame(
            {
                "KEY": pl.Series([], dtype=pl.String),
                "ID": pl.Series([], dtype=pl.String),
                "action": pl.Series([], dtype=pl.String),
                "column": pl.Series([], dtype=pl.String),
                "current value": pl.Series([], dtype=pl.String),
                "new value": pl.Series([], dtype=pl.String),
                "reason": pl.Series([], dtype=pl.String),
            }
        )

        mock_session_state["prepped_data0"] = pl.DataFrame(
            {"survey_key": ["key1", "key2"], "name": ["John", "Jane"]}
        ).to_pandas()

        # Apply correction with page_name
        correction_apply_action(
            data_index=0,
            key_col="survey_key",
            project_id="test_project",
            page_name="test_page",
            action="modify value",
            key_value="key1",
            current_id="id1",
            current_value="John",
            col_to_modify="name",
            new_value="Johnny",
            reason="Name update",
        )

        # Verify the log was loaded with correct parameters
        mock_load_log.assert_called_once_with("test_project", "test_page")


@patch("src.processing.corrections.st")
def test_correction_apply_action_multiple_corrections(mock_st):
    """Test applying multiple corrections in sequence."""
    # Setup mock session state with existing corrections
    existing_log = pl.DataFrame(
        {
            "KEY": ["key1"],
            "ID": ["id1"],
            "action": ["modify value"],
            "column": ["name"],
            "current value": ["John"],
            "new value": ["Johnny"],
            "reason": ["Initial correction"],
        }
    )

    mock_session_state = {
        "id_correction_log_0": existing_log,
        "st_raw_dataset_list": ["Dataset 1"],
        "config_pages": {"Survey Data": ["Dataset 1"]},
        "prepped_data0": pl.DataFrame(
            {
                "survey_key": ["key1", "key2", "key3"],
                "name": ["John", "Jane", "Bob"],
                "age": [25, 30, 35],
            }
        ).to_pandas(),
    }
    mock_st.session_state = mock_session_state

    # Apply first correction (should apply existing correction)
    correction_apply_action(
        data_index=0,
        key_col="survey_key",
        project_id="test_project",
        action=None,  # No new action, just apply existing log
    )

    # Verify existing correction was applied
    corrected_data = mock_st.session_state["corrected_data0"]
    assert (
        corrected_data.filter(pl.col("survey_key") == "key1").item(0, "name")
        == "Johnny"
    )

    # Apply second correction
    correction_apply_action(
        data_index=0,
        key_col="survey_key",
        project_id="test_project",
        action="modify value",
        key_value="key2",
        current_id="id2",
        current_value="Jane",
        col_to_modify="name",
        new_value="Janet",
        reason="Second correction",
    )

    # Verify both corrections are in the log
    log = mock_st.session_state["id_correction_log_0"]
    assert len(log) == 2
    assert log.item(1, "new value") == "Janet"


@patch("src.processing.corrections.st")
def test_correction_apply_action_string_conversion(mock_st):
    """Test that all correction values are converted to strings."""
    # Setup mock session state
    mock_session_state = {
        "id_correction_log_0": pl.DataFrame(
            {
                "KEY": pl.Series([], dtype=pl.String),
                "ID": pl.Series([], dtype=pl.String),
                "action": pl.Series([], dtype=pl.String),
                "column": pl.Series([], dtype=pl.String),
                "current value": pl.Series([], dtype=pl.String),
                "new value": pl.Series([], dtype=pl.String),
                "reason": pl.Series([], dtype=pl.String),
            }
        ),
        "st_raw_dataset_list": ["Dataset 1"],
        "config_pages": {"Survey Data": ["Dataset 1"]},
        "prepped_data0": pl.DataFrame(
            {"survey_key": ["key1"], "age": [25]}
        ).to_pandas(),
    }
    mock_st.session_state = mock_session_state

    # Apply correction with numeric values
    correction_apply_action(
        data_index=0,
        key_col="survey_key",
        project_id="test_project",
        action="modify value",
        key_value="key1",
        current_id=123,  # numeric ID
        current_value=25,  # numeric current value
        col_to_modify="age",
        new_value=26,  # numeric new value
        reason=None,  # None reason
    )

    # Verify all values were converted to strings in the log
    log = mock_st.session_state["id_correction_log_0"]
    assert log.item(0, "ID") == "123"
    assert log.item(0, "current value") == "25"
    assert log.item(0, "new value") == "26"
    assert log.item(0, "reason") == ""  # None converted to empty string


@patch("src.processing.corrections.st")
def test_correction_apply_action_no_action_parameter(mock_st):
    """Test applying corrections when no action parameter is provided."""
    # Setup mock session state with existing corrections
    existing_log = pl.DataFrame(
        {
            "KEY": ["key1", "key2"],
            "ID": ["id1", "id2"],
            "action": ["modify value", "remove row"],
            "column": ["name", ""],
            "current value": ["John", "Jane"],
            "new value": ["Johnny", ""],
            "reason": ["Name correction", "Remove duplicate"],
        }
    )

    mock_session_state = {
        "id_correction_log_0": existing_log,
        "st_raw_dataset_list": ["Dataset 1"],
        "config_pages": {"Survey Data": ["Dataset 1"]},
        "prepped_data0": pl.DataFrame(
            {
                "survey_key": ["key1", "key2", "key3"],
                "name": ["John", "Jane", "Bob"],
            }
        ).to_pandas(),
    }
    mock_st.session_state = mock_session_state

    # Apply corrections without adding new ones
    correction_apply_action(
        data_index=0, key_col="survey_key", project_id="test_project"
    )

    # Verify corrections were applied
    corrected_data = mock_st.session_state["corrected_data0"]
    assert len(corrected_data) == 2  # One row removed
    assert (
        corrected_data.filter(pl.col("survey_key") == "key1").item(0, "name")
        == "Johnny"
    )
    assert not (corrected_data["survey_key"] == "key2").any()  # Row removed
