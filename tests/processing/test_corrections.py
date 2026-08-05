"""Test the corrections module."""

from datetime import datetime
from unittest.mock import patch

import polars as pl
import pytest

from datasure.processing.corrections import CorrectionProcessor


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests.
    """
    pass


@pytest.fixture
def sample_data():
    """Sample data for testing."""
    return pl.DataFrame(
        {
            "survey_key": ["key1", "key2", "key3"],
            "name": ["John", "Jane", "Bob"],
            "age": [25, 30, 35],
            "date_col": ["2023-01-01", "2023-01-02", "2023-01-03"],
        }
    )


@pytest.fixture
def sample_data_with_missing():
    """Sample data with missing values for testing."""
    return pl.DataFrame(
        {
            "survey_key": ["key1", "key2", "key3"],
            "name": ["John", None, "Bob"],
            "age": [25, None, 35],
            "score": [100, 85, None],
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
    """Mock Streamlit session state and caching."""
    with patch("datasure.processing.corrections.st") as mock_st:
        mock_st.session_state = {}
        # Mock cache_data decorator to return the original function
        mock_st.cache_data = lambda ttl=60, show_spinner=False: lambda func: func
        yield mock_st


@pytest.fixture
def correction_processor(mock_streamlit):
    """Create a CorrectionProcessor with mocked dependencies."""
    with (
        patch("datasure.processing.corrections.duckdb_get_table") as mock_get,
        patch("datasure.processing.corrections.duckdb_save_table") as mock_save,
    ):
        processor = CorrectionProcessor("test_project")
        # Clear all caches before each test
        processor.get_corrected_data.clear()
        processor.get_correction_log.clear()
        processor.get_data_summary.clear()
        processor.get_correction_summary.clear()
        yield processor, mock_get, mock_save


class TestCorrectionProcessor:
    """Test cases for CorrectionProcessor class."""

    def test_initialization(self, mock_streamlit):
        """Test CorrectionProcessor initialization."""
        processor = CorrectionProcessor("test_project_id")
        assert processor.project_id == "test_project_id"

    def test_get_corrected_data_existing(self, correction_processor, sample_data):
        """Test getting existing corrected data."""
        processor, mock_get, _ = correction_processor
        mock_get.return_value = sample_data

        result = processor.get_corrected_data("test_alias")

        assert result.equals(sample_data)
        mock_get.assert_called_once_with(
            project_id="test_project", alias="test_alias", db_name="corrected"
        )

    def test_get_corrected_data_initialize_from_prep(
        self, correction_processor, sample_data
    ):
        """Test initializing corrected data from prepped data."""
        processor, mock_get, mock_save = correction_processor

        # First call returns empty, second call returns prep data
        mock_get.side_effect = [pl.DataFrame(), sample_data]

        result = processor.get_corrected_data("test_alias")

        assert result.equals(sample_data)
        assert mock_get.call_count == 2
        # Note: save_corrected_data is called from get_corrected_data
        mock_save.assert_called_once()

    def test_get_corrected_data_both_empty(self, correction_processor):
        """Test getting corrected data when both corrected and prep are empty."""
        processor, mock_get, _ = correction_processor
        mock_get.return_value = pl.DataFrame()

        result = processor.get_corrected_data("test_alias")

        assert result.is_empty()
        assert mock_get.call_count == 2  # Called for both corrected and prep

    def test_save_corrected_data(self, correction_processor, sample_data):
        """Test saving corrected data."""
        processor, _, mock_save = correction_processor

        processor.save_corrected_data("test_alias", sample_data)

        mock_save.assert_called_once_with(
            project_id="test_project",
            table_data=sample_data,
            alias="test_alias",
            db_name="corrected",
        )

    def test_get_correction_log(self, correction_processor, sample_corrections_log):
        """Test getting correction log."""
        processor, mock_get, _ = correction_processor
        mock_get.return_value = sample_corrections_log

        result = processor.get_correction_log("test_alias")

        assert result.equals(sample_corrections_log)
        mock_get.assert_called_once_with(
            project_id="test_project", alias="corr_log_test_alias", db_name="logs"
        )

    def test_add_correction_entry(self, correction_processor):
        """Test adding correction entry to log."""
        processor, mock_get, mock_save = correction_processor

        # Mock empty log
        empty_log = pl.DataFrame(
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
        mock_get.return_value = empty_log

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

        # Check saved data structure
        call_args = mock_save.call_args
        saved_df = call_args[1]["table_data"]
        assert len(saved_df) == 1
        assert saved_df["action"][0] == "modify value"
        assert saved_df["new_value"][0] == "Johnny"
        assert saved_df["KEY"][0] == "key1"

    def test_add_correction_entry_with_existing_log(
        self, correction_processor, sample_corrections_log
    ):
        """Test adding correction entry to existing log."""
        processor, mock_get, mock_save = correction_processor
        mock_get.return_value = sample_corrections_log

        processor.add_correction_entry(
            alias="test_alias",
            key_value="key4",
            current_id=None,
            action="modify value",
            column="age",
            current_value=40,
            new_value=41,
            reason="Age correction",
        )

        mock_save.assert_called_once()

        # Check that the log was extended
        call_args = mock_save.call_args
        saved_df = call_args[1]["table_data"]
        assert len(saved_df) == 4  # 3 original + 1 new

    def test_apply_correction_modify_value_string(
        self, correction_processor, sample_data
    ):
        """Test applying modify value correction to string column."""
        processor, mock_get, _mock_save = correction_processor
        # Mock sequence: get corrected data, get log for add_correction_entry
        empty_log = pl.DataFrame(
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
        mock_get.side_effect = [sample_data, empty_log]

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

        # Check that other rows are unchanged
        unchanged_row = result.filter(pl.col("survey_key") == "key1")
        assert unchanged_row[0, "name"] == "John"

    def test_apply_correction_modify_value_numeric(
        self, correction_processor, sample_data
    ):
        """Test applying modify value correction to numeric column."""
        processor, mock_get, _mock_save = correction_processor
        empty_log = pl.DataFrame(
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
        mock_get.side_effect = [sample_data, empty_log]

        result = processor.apply_correction(
            alias="test_alias",
            key_col="survey_key",
            key_value="key1",
            action="modify value",
            column="age",
            current_value=25,
            new_value=26,
            reason="Age correction",
        )

        # Check that the numeric value was modified
        modified_row = result.filter(pl.col("survey_key") == "key1")
        assert modified_row[0, "age"] == 26

    def test_apply_correction_modify_value_type_conversion_fallback(
        self, correction_processor, sample_data
    ):
        """Test modify value with type conversion fallback."""
        processor, mock_get, _mock_save = correction_processor
        empty_log = pl.DataFrame(
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
        mock_get.side_effect = [sample_data, empty_log]

        # Try to set an invalid numeric value (should fallback to string)
        result = processor.apply_correction(
            alias="test_alias",
            key_col="survey_key",
            key_value="key1",
            action="modify value",
            column="age",
            current_value=25,
            new_value="invalid_number",
            reason="Test fallback",
        )

        # Check that it falls back to string conversion
        modified_row = result.filter(pl.col("survey_key") == "key1")
        assert modified_row[0, "age"] == "invalid_number"

    def test_apply_correction_remove_value(self, correction_processor, sample_data):
        """Test applying remove value correction."""
        processor, mock_get, _mock_save = correction_processor
        empty_log = pl.DataFrame(
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
        mock_get.side_effect = [sample_data, empty_log]

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

    def test_apply_correction_remove_row(self, correction_processor, sample_data):
        """Test applying remove row correction."""
        processor, mock_get, _mock_save = correction_processor
        empty_log = pl.DataFrame(
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
        mock_get.side_effect = [sample_data, empty_log]

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

    def test_apply_correction_without_reason(self, correction_processor, sample_data):
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

    def test_get_data_summary(self, correction_processor, sample_data):
        """Test getting data summary."""
        processor, _, _ = correction_processor

        summary = processor.get_data_summary(sample_data)

        assert summary["rows"] == 3
        assert summary["columns"] == 4
        assert summary["missing_percentage"] == 0.0

    def test_get_data_summary_with_missing_values(
        self, correction_processor, sample_data_with_missing
    ):
        """Test getting data summary with missing values."""
        processor, _, _ = correction_processor

        summary = processor.get_data_summary(sample_data_with_missing)

        assert summary["rows"] == 3
        assert summary["columns"] == 4
        # 3 missing values out of 12 total cells = 25%
        assert summary["missing_percentage"] == 25.0

    def test_validate_correction_input_valid(self, correction_processor, sample_data):
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

    def test_validate_correction_input_invalid_key_col(
        self, correction_processor, sample_data
    ):
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

    def test_validate_correction_input_invalid_key_value(
        self, correction_processor, sample_data
    ):
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

    def test_validate_correction_input_missing_column(
        self, correction_processor, sample_data
    ):
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

    def test_validate_correction_input_invalid_column(
        self, correction_processor, sample_data
    ):
        """Test validation with invalid column name."""
        processor, _, _ = correction_processor

        is_valid, error_msg = processor.validate_correction_input(
            data=sample_data,
            key_col="survey_key",
            key_value="key1",
            action="modify value",
            column="invalid_column",
            new_value="Johnny",
        )

        assert not is_valid
        assert "Column 'invalid_column' not found" in error_msg

    def test_validate_correction_input_missing_new_value(
        self, correction_processor, sample_data
    ):
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

    def test_validate_correction_input_remove_row_valid(
        self, correction_processor, sample_data
    ):
        """Test validation for remove row action."""
        processor, _, _ = correction_processor

        is_valid, error_msg = processor.validate_correction_input(
            data=sample_data,
            key_col="survey_key",
            key_value="key1",
            action="remove row",
        )

        assert is_valid
        assert error_msg == ""

    def test_get_correction_summary_empty(self, correction_processor):
        """Test getting correction summary when no corrections exist."""
        processor, mock_get, _ = correction_processor
        mock_get.return_value = pl.DataFrame()

        summary = processor.get_correction_summary("test_alias")

        assert summary == []

    def test_get_correction_summary_with_data(
        self, correction_processor, sample_corrections_log
    ):
        """Test getting correction summary with data."""
        processor, mock_get, _ = correction_processor
        mock_get.return_value = sample_corrections_log

        summary = processor.get_correction_summary("test_alias")

        assert len(summary) == 3

        # Check first entry (modify value)
        assert summary[0]["action"] == "modify value"
        assert summary[0]["key_value"] == "key1"
        assert "Modify name for key key1 to 'Johnny'" in summary[0]["description"]
        assert summary[0]["index"] == 0

        # Check second entry (remove value)
        assert summary[1]["action"] == "remove value"
        assert summary[1]["key_value"] == "key2"
        assert "Remove name value for key key2" in summary[1]["description"]

        # Check third entry (remove row)
        assert summary[2]["action"] == "remove row"
        assert summary[2]["key_value"] == "key3"
        assert "Remove entire row for key key3" in summary[2]["description"]

    def test_remove_correction_entry(
        self, correction_processor, sample_corrections_log, sample_data
    ):
        """Test removing a correction entry."""
        processor, mock_get, mock_save = correction_processor

        # Mock sequence: get log for removal, get prep data for reapply,
        # get updated log (empty)
        mock_get.side_effect = [
            sample_corrections_log,
            sample_data,  # prep data for reapply
            pl.DataFrame(),  # empty log after removal
        ]

        failures = processor.remove_correction_entry("test_alias", 1)

        # Should save the updated log and reapplied data
        assert mock_save.call_count == 2
        assert failures == []

    def test_remove_correction_entry_invalid_index(
        self, correction_processor, sample_corrections_log
    ):
        """Test removing correction entry with invalid index."""
        processor, mock_get, _ = correction_processor
        mock_get.return_value = sample_corrections_log

        with pytest.raises(ValueError, match="Invalid correction index"):
            processor.remove_correction_entry("test_alias", 10)

    def test_remove_correction_entry_negative_index(
        self, correction_processor, sample_corrections_log
    ):
        """Test removing correction entry with negative index."""
        processor, mock_get, _ = correction_processor
        mock_get.return_value = sample_corrections_log

        with pytest.raises(ValueError, match="Invalid correction index"):
            processor.remove_correction_entry("test_alias", -1)

    def test_remove_correction_entry_empty_log(self, correction_processor):
        """Test removing correction entry when log is empty."""
        processor, mock_get, _ = correction_processor
        mock_get.return_value = pl.DataFrame()

        with pytest.raises(ValueError, match="No corrections to remove"):
            processor.remove_correction_entry("test_alias", 0)

    def test_reapply_all_corrections_empty_prep_data(self, correction_processor):
        """Test reapplying corrections when prep data is empty."""
        processor, mock_get, mock_save = correction_processor
        mock_get.return_value = pl.DataFrame()  # Empty prep data

        failures = processor._reapply_all_corrections("test_alias")

        # Should not save anything when prep data is empty
        mock_save.assert_not_called()
        assert failures == []

    def test_reapply_all_corrections_empty_log(self, correction_processor, sample_data):
        """Test reapplying corrections when correction log is empty."""
        processor, mock_get, mock_save = correction_processor
        # Mock sequence: get prep data, get empty log
        mock_get.side_effect = [sample_data, pl.DataFrame()]

        failures = processor._reapply_all_corrections("test_alias")

        # Should save the fresh prep data as corrected data
        mock_save.assert_called_once()
        assert failures == []

    def test_reapply_all_corrections_with_data(
        self, correction_processor, sample_data, sample_corrections_log
    ):
        """Test reapplying corrections with correction log data."""
        processor, mock_get, mock_save = correction_processor
        # Mock sequence: get prep data, get correction log
        mock_get.side_effect = [sample_data, sample_corrections_log]

        failures = processor._reapply_all_corrections("test_alias")

        # Should save corrected data after applying all corrections
        mock_save.assert_called_once()
        call_args = mock_save.call_args
        assert call_args[1]["alias"] == "test_alias"
        assert call_args[1]["db_name"] == "corrected"
        assert failures == []

    def test_reapply_corrections_key_not_found(self, correction_processor, sample_data):
        """Test reapplying corrections when key value not found in data."""
        processor, mock_get, mock_save = correction_processor

        # Create correction log with non-existent key
        invalid_log = pl.DataFrame(
            {
                "date": [datetime.now()],
                "KEY": ["nonexistent_key"],
                "ID": [None],
                "action": ["modify value"],
                "column": ["name"],
                "current_value": ["test"],
                "new_value": ["changed"],
                "reason": ["test correction"],
            }
        )

        mock_get.side_effect = [sample_data, invalid_log]

        failures = processor._reapply_all_corrections("test_alias")

        # Should still save data even if some corrections fail
        mock_save.assert_called_once()
        # ... and the skipped correction should be reported, not swallowed
        assert len(failures) == 1
        assert "nonexistent_key" in failures[0].reason

    def test_reapply_corrections_partial_failure_continues(
        self, correction_processor, sample_data
    ):
        """One bad correction is skipped and reported; the rest still apply."""
        processor, mock_get, mock_save = correction_processor

        mixed_log = pl.DataFrame(
            {
                "date": [datetime.now()] * 2,
                "KEY": ["nonexistent_key", "key1"],
                "ID": [None, None],
                "action": ["modify value", "modify value"],
                "column": ["name", "name"],
                "current_value": ["test", "John"],
                "new_value": ["changed", "Johnny"],
                "reason": ["bad correction", "good correction"],
            }
        )

        mock_get.side_effect = [sample_data, mixed_log]

        failures = processor._reapply_all_corrections("test_alias")

        mock_save.assert_called_once()
        saved_data = mock_save.call_args[1]["table_data"]
        assert saved_data.filter(pl.col("survey_key") == "key1")["name"][0] == "Johnny"
        assert len(failures) == 1
        assert "nonexistent_key" in failures[0].reason

    def test_reapply_corrections_exception_handling(
        self, correction_processor, sample_data
    ):
        """Test that reapply handles exceptions gracefully."""
        processor, mock_get, mock_save = correction_processor

        # Create correction log that will cause an exception
        problematic_log = pl.DataFrame(
            {
                "date": [datetime.now()],
                "KEY": ["key1"],
                "ID": [None],
                "action": ["modify value"],
                "column": ["nonexistent_column"],
                "current_value": ["test"],
                "new_value": ["changed"],
                "reason": ["test correction"],
            }
        )

        mock_get.side_effect = [sample_data, problematic_log]

        # Should not raise exception, just skip problematic corrections
        failures = processor._reapply_all_corrections("test_alias")

        # Should still save data
        mock_save.assert_called_once()
        # ... and report the skipped correction instead of swallowing it
        assert len(failures) == 1
        assert failures[0].reason
        assert "key1" in failures[0].step

    def test_private_apply_modify_value_string(self, correction_processor, sample_data):
        """Test private method _apply_modify_value with string column."""
        processor, _, _ = correction_processor

        result = processor._apply_modify_value(
            sample_data, "survey_key", "key1", "name", "Johnny"
        )

        modified_row = result.filter(pl.col("survey_key") == "key1")
        assert modified_row[0, "name"] == "Johnny"

    def test_private_apply_modify_value_numeric(
        self, correction_processor, sample_data
    ):
        """Test private method _apply_modify_value with numeric column."""
        processor, _, _ = correction_processor

        result = processor._apply_modify_value(
            sample_data, "survey_key", "key1", "age", 26
        )

        modified_row = result.filter(pl.col("survey_key") == "key1")
        assert modified_row[0, "age"] == 26

    def test_private_apply_remove_value(self, correction_processor, sample_data):
        """Test private method _apply_remove_value."""
        processor, _, _ = correction_processor

        result = processor._apply_remove_value(
            sample_data, "survey_key", "key1", "name"
        )

        modified_row = result.filter(pl.col("survey_key") == "key1")
        assert modified_row[0, "name"] is None

    def test_private_apply_remove_row(self, correction_processor, sample_data):
        """Test private method _apply_remove_row."""
        processor, _, _ = correction_processor

        result = processor._apply_remove_row(sample_data, "survey_key", "key1")

        assert len(result) == 2
        assert not (result["survey_key"] == "key1").any()
