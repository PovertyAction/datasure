"""Test the corrections module."""

from datetime import datetime
from unittest.mock import patch

import polars as pl
import pytest

from datasure.processing.corrections import CorrectionProcessor


@pytest.fixture
def sample_data():
    """Sample data for testing."""
    return pl.DataFrame(
        {
            "survey_key": ["key1", "key2", "key3"],
            "name": ["John", "Jane", "Bob"],
            "age": [25, 30, 35],
        }
    )


@pytest.fixture
def sample_corrections_log():
    """Sample corrections log for testing."""
    return pl.DataFrame(
        {
            "date": [datetime.now()] * 3,
            "KEY": ["key1", "key2", "key3"],
            "ID": [None, None, None],
            "action": ["modify value", "remove value", "remove row"],
            "column": ["name", "name", None],
            "current_value": ["John", "Jane", None],
            "new_value": ["Johnny", None, None],
            "reason": ["Name correction", "Remove name", "Remove row"],
        }
    )


@pytest.fixture
def mock_streamlit():
    """Mock Streamlit session state."""
    with patch("datasure.processing.corrections.st") as mock_st:
        mock_st.session_state = {}
        yield mock_st


@pytest.fixture
def correction_processor(mock_streamlit):
    """Create a CorrectionProcessor with mocked dependencies."""
    with (
        patch("datasure.processing.corrections.duckdb_get_table") as mock_get,
        patch("datasure.processing.corrections.duckdb_save_table") as mock_save,
    ):
        processor = CorrectionProcessor("test_project")
        yield processor, mock_get, mock_save


def test_get_corrected_data_existing(correction_processor, sample_data):
    """Test getting existing corrected data."""
    processor, mock_get, _ = correction_processor
    mock_get.return_value = sample_data

    result = processor.get_corrected_data("test_alias")

    assert result.equals(sample_data)
    mock_get.assert_called_once_with(
        project_id="test_project", alias="test_alias", db_name="corrected"
    )


def test_get_corrected_data_initialize_from_prep(correction_processor, sample_data):
    """Test initializing corrected data from prepped data."""
    processor, mock_get, mock_save = correction_processor

    # First call returns empty, second call returns prep data
    mock_get.side_effect = [pl.DataFrame(), sample_data]

    result = processor.get_corrected_data("test_alias")

    assert result.equals(sample_data)
    assert mock_get.call_count == 2
    mock_save.assert_called_once_with(
        project_id="test_project",
        table_data=sample_data,
        alias="test_alias",
        db_name="corrected",
    )


def test_save_corrected_data(correction_processor, sample_data):
    """Test saving corrected data."""
    processor, _, mock_save = correction_processor

    processor.save_corrected_data("test_alias", sample_data)

    mock_save.assert_called_once_with(
        project_id="test_project",
        table_data=sample_data,
        alias="test_alias",
        db_name="corrected",
    )


def test_get_correction_log(correction_processor, sample_corrections_log):
    """Test getting correction log."""
    processor, mock_get, _ = correction_processor
    mock_get.return_value = sample_corrections_log

    result = processor.get_correction_log("test_alias")

    assert result.equals(sample_corrections_log)
    mock_get.assert_called_once_with(
        project_id="test_project", alias="corr_log_test_alias", db_name="logs"
    )


def test_add_correction_entry(correction_processor):
    """Test adding correction entry to log."""
    processor, mock_get, mock_save = correction_processor
    mock_get.return_value = pl.DataFrame(
        {
            "date": [],
            "KEY": [],
            "ID": [],
            "action": [],
            "column": [],
            "current_value": [],
            "new_value": [],
            "reason": [],
        }
    )

    processor.add_correction_entry(
        alias="test_alias",
        key_value="key1",
        current_id=None,
        action="modify value",
        column="name",
        current_value="John",
        new_value="Johnny",
        reason="Name correction",
    )

    mock_save.assert_called_once()
    # Check that the saved data has the correct parameters
    call_args = mock_save.call_args
    assert call_args[1]["project_id"] == "test_project"
    assert call_args[1]["alias"] == "corr_log_test_alias"
    assert call_args[1]["db_name"] == "logs"

    saved_df = call_args[1]["table_data"]
    assert len(saved_df) == 1
    assert saved_df["action"][0] == "modify value"
    assert saved_df["new_value"][0] == "Johnny"


def test_apply_correction_modify_value(correction_processor, sample_data):
    """Test applying modify value correction."""
    processor, mock_get, mock_save = correction_processor
    # Mock sequence: get corrected data, get log for add_correction_entry
    mock_get.side_effect = [
        sample_data,
        pl.DataFrame(
            {
                "date": [],
                "KEY": [],
                "ID": [],
                "action": [],
                "column": [],
                "current_value": [],
                "new_value": [],
                "reason": [],
            }
        ),
    ]

    result = processor.apply_correction(
        alias="test_alias",
        key_col="survey_key",
        key_value="key2",
        action="modify value",
        column="name",
        current_value="Jane",
        new_value="Janet",
        reason="Name correction",
    )

    # Check that the value was modified
    modified_row = result.filter(pl.col("survey_key") == "key2")
    assert modified_row[0, "name"] == "Janet"

    # Check that save was called twice (data and log)
    assert mock_save.call_count == 2


def test_apply_correction_remove_value(correction_processor, sample_data):
    """Test applying remove value correction."""
    processor, mock_get, mock_save = correction_processor
    # Mock sequence: get corrected data, get log for add_correction_entry
    mock_get.side_effect = [
        sample_data,
        pl.DataFrame(
            {
                "date": [],
                "KEY": [],
                "ID": [],
                "action": [],
                "column": [],
                "current_value": [],
                "new_value": [],
                "reason": [],
            }
        ),
    ]

    result = processor.apply_correction(
        alias="test_alias",
        key_col="survey_key",
        key_value="key2",
        action="remove value",
        column="name",
        current_value="Jane",
        reason="Remove name",
    )

    # Check that the value was removed (set to None)
    modified_row = result.filter(pl.col("survey_key") == "key2")
    assert modified_row[0, "name"] is None


def test_apply_correction_remove_row(correction_processor, sample_data):
    """Test applying remove row correction."""
    processor, mock_get, mock_save = correction_processor
    # Mock sequence: get corrected data, get log for add_correction_entry
    mock_get.side_effect = [
        sample_data,
        pl.DataFrame(
            {
                "date": [],
                "KEY": [],
                "ID": [],
                "action": [],
                "column": [],
                "current_value": [],
                "new_value": [],
                "reason": [],
            }
        ),
    ]

    result = processor.apply_correction(
        alias="test_alias",
        key_col="survey_key",
        key_value="key2",
        action="remove row",
        reason="Remove duplicate",
    )

    # Check that the row was removed
    assert len(result) == 2
    assert not (result["survey_key"] == "key2").any()


def test_get_data_summary(correction_processor, sample_data):
    """Test getting data summary."""
    processor, _, _ = correction_processor

    summary = processor.get_data_summary(sample_data)

    assert summary["rows"] == 3
    assert summary["columns"] == 3
    assert summary["missing_percentage"] == 0.0


def test_get_data_summary_empty(correction_processor):
    """Test getting summary of empty data."""
    processor, _, _ = correction_processor
    empty_data = pl.DataFrame()

    summary = processor.get_data_summary(empty_data)

    assert summary["rows"] == 0
    assert summary["columns"] == 0
    assert summary["missing_percentage"] == 0.0


def test_validate_correction_input_valid(correction_processor, sample_data):
    """Test validation of valid correction input."""
    processor, _, _ = correction_processor

    is_valid, error_msg = processor.validate_correction_input(
        data=sample_data,
        key_col="survey_key",
        key_value="key1",
        action="modify value",
        column="name",
        new_value="Johnny",
    )

    assert is_valid
    assert error_msg == ""


def test_validate_correction_input_invalid_key_col(correction_processor, sample_data):
    """Test validation with invalid key column."""
    processor, _, _ = correction_processor

    is_valid, error_msg = processor.validate_correction_input(
        data=sample_data,
        key_col="invalid_col",
        key_value="key1",
        action="modify value",
        column="name",
        new_value="Johnny",
    )

    assert not is_valid
    assert "Key column 'invalid_col' not found" in error_msg


def test_validate_correction_input_invalid_key_value(correction_processor, sample_data):
    """Test validation with invalid key value."""
    processor, _, _ = correction_processor

    is_valid, error_msg = processor.validate_correction_input(
        data=sample_data,
        key_col="survey_key",
        key_value="invalid_key",
        action="modify value",
        column="name",
        new_value="Johnny",
    )

    assert not is_valid
    assert "Key value 'invalid_key' not found" in error_msg


def test_validate_correction_input_missing_column(correction_processor, sample_data):
    """Test validation with missing column for modify value."""
    processor, _, _ = correction_processor

    is_valid, error_msg = processor.validate_correction_input(
        data=sample_data,
        key_col="survey_key",
        key_value="key1",
        action="modify value",
        column=None,
        new_value="Johnny",
    )

    assert not is_valid
    assert "Column must be specified" in error_msg


def test_validate_correction_input_missing_new_value(correction_processor, sample_data):
    """Test validation with missing new value for modify value."""
    processor, _, _ = correction_processor

    is_valid, error_msg = processor.validate_correction_input(
        data=sample_data,
        key_col="survey_key",
        key_value="key1",
        action="modify value",
        column="name",
        new_value=None,
    )

    assert not is_valid
    assert "New value must be provided" in error_msg


def test_get_key_options(correction_processor, sample_data):
    """Test getting key options for dropdown."""
    processor, mock_get, _ = correction_processor
    mock_get.return_value = sample_data

    key_options = processor.get_key_options("test_alias", "survey_key")

    assert key_options == ["key1", "key2", "key3"]


def test_get_correction_summary_empty(correction_processor):
    """Test getting correction summary when no corrections exist."""
    processor, mock_get, _ = correction_processor
    mock_get.return_value = pl.DataFrame()

    summary = processor.get_correction_summary("test_alias")

    assert summary == []


def test_get_correction_summary_with_data(correction_processor, sample_corrections_log):
    """Test getting correction summary with data."""
    processor, mock_get, _ = correction_processor
    mock_get.return_value = sample_corrections_log

    summary = processor.get_correction_summary("test_alias")

    assert len(summary) == 3
    assert summary[0]["action"] == "modify value"
    assert summary[0]["key_value"] == "key1"
    assert "Modify name for key key1 to 'Johnny'" in summary[0]["description"]
    assert summary[1]["action"] == "remove value"
    assert summary[2]["action"] == "remove row"


def test_remove_correction_entry(
    correction_processor, sample_corrections_log, sample_data
):
    """Test removing a correction entry."""
    processor, mock_get, mock_save = correction_processor
    # Mock sequence: get log for removal, get prep data
    # for reapply, get updated log (empty)
    mock_get.side_effect = [
        sample_corrections_log,
        sample_data,  # prep data for reapply
        pl.DataFrame(),  # empty log after removal
    ]

    processor.remove_correction_entry("test_alias", 1)

    # Should save the updated log and reapplied data
    assert mock_save.call_count == 2


def test_apply_correction_without_reason(correction_processor, sample_data):
    """Test applying correction without reason (should not log)."""
    processor, mock_get, mock_save = correction_processor
    mock_get.return_value = sample_data

    result = processor.apply_correction(
        alias="test_alias",
        key_col="survey_key",
        key_value="key2",
        action="modify value",
        column="name",
        current_value="Jane",
        new_value="Janet",
        reason=None,  # No reason provided
    )

    # Check that the value was modified
    modified_row = result.filter(pl.col("survey_key") == "key2")
    assert modified_row[0, "name"] == "Janet"

    # Should only save data, not log (since no reason)
    assert mock_save.call_count == 1


def test_remove_correction_entry_invalid_index(
    correction_processor, sample_corrections_log
):
    """Test removing correction entry with invalid index."""
    processor, mock_get, _ = correction_processor
    mock_get.return_value = sample_corrections_log

    with pytest.raises(ValueError, match="Invalid correction index"):
        processor.remove_correction_entry("test_alias", 10)


def test_remove_correction_entry_empty_log(correction_processor):
    """Test removing correction entry when log is empty."""
    processor, mock_get, _ = correction_processor
    mock_get.return_value = pl.DataFrame()

    with pytest.raises(ValueError, match="No corrections to remove"):
        processor.remove_correction_entry("test_alias", 0)
