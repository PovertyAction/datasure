"""Test the corrections module."""

from datetime import datetime
from unittest.mock import patch

import polars as pl
import pytest

from datasure.processing.corrections import CorrectionEntry, CorrectionProcessor


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

        # Persisted columns come back unchanged; later columns are backfilled.
        assert result.select(sample_corrections_log.columns).equals(
            sample_corrections_log
        )
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
        # A freshly applied correction is always logged as successful
        assert saved_df["status"][0] == "Successful"
        assert saved_df["status_reason"][0] is None

    def test_add_correction_entry_clears_log_cache(self, correction_processor):
        """Adding an entry must invalidate the cached log/summary.

        Without clearing the cache, the correction log and summary keep
        serving the pre-add snapshot for up to the cache TTL, so a freshly
        added correction doesn't show up right away.
        """
        processor, mock_get, _ = correction_processor

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

        # Prime the cache (simulates the log already having been displayed)
        processor.get_correction_log("test_alias")
        processor.get_correction_summary("test_alias")
        calls_before = mock_get.call_count

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

        # A fresh read after adding must hit the database again, not the
        # stale cached snapshot from before the correction was added.
        processor.get_correction_log("test_alias")
        processor.get_correction_summary("test_alias")
        assert mock_get.call_count > calls_before

    def test_add_correction_entry_with_existing_log(
        self, correction_processor, sample_corrections_log
    ):
        """Test adding correction entry to existing log.

        `sample_corrections_log` predates the status columns, so this also
        exercises backfilling a legacy log before concatenating the new row.
        """
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
        # Legacy rows backfilled, new row logged as successful
        assert saved_df["status"].to_list() == ["Successful"] * 4
        assert saved_df["status_reason"].to_list() == [None] * 4

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

    def test_apply_correction_records_survey_id(
        self, correction_processor, sample_data
    ):
        """The Survey ID for the corrected KEY is recorded in the log's ID column."""
        processor, mock_get, mock_save = correction_processor
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

        processor.apply_correction(
            alias="test_alias",
            key_col="survey_key",
            key_value="key2",
            action="modify value",
            column="name",
            current_value="Jane",
            new_value="Janet",
            reason="Name correction",
            survey_id_value="HH002",
        )

        saved_log = mock_save.call_args[1]["table_data"]
        assert saved_log["ID"][0] == "HH002"

    def test_apply_correction_without_survey_id_leaves_id_blank(
        self, correction_processor, sample_data
    ):
        """No Survey ID configured/available means the ID column stays blank."""
        processor, mock_get, mock_save = correction_processor
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

        processor.apply_correction(
            alias="test_alias",
            key_col="survey_key",
            key_value="key2",
            action="modify value",
            column="name",
            current_value="Jane",
            new_value="Janet",
            reason="Name correction",
        )

        saved_log = mock_save.call_args[1]["table_data"]
        assert saved_log["ID"][0] is None

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

        # Should save: the trimmed log, the reapply's refreshed log (with
        # status), and the reapplied corrected data
        assert mock_save.call_count == 3
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

        # Should save the refreshed (empty) log and the fresh prep data
        assert mock_save.call_count == 2
        assert failures == []

    def test_reapply_all_corrections_with_data(
        self, correction_processor, sample_data, sample_corrections_log
    ):
        """Test reapplying corrections with correction log data."""
        processor, mock_get, mock_save = correction_processor
        # Mock sequence: get prep data, get correction log
        mock_get.side_effect = [sample_data, sample_corrections_log]

        failures = processor._reapply_all_corrections("test_alias")

        # Should save the refreshed log, then corrected data after applying
        # all corrections
        assert mock_save.call_count == 2
        call_args = mock_save.call_args_list[-1]
        assert call_args[1]["alias"] == "test_alias"
        assert call_args[1]["db_name"] == "corrected"
        assert failures == []

        # The refreshed log records every step as successful
        saved_log = mock_save.call_args_list[0][1]["table_data"]
        assert saved_log["status"].to_list() == ["Successful"] * 3

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
        assert mock_save.call_count == 2
        # ... and the skipped correction should be reported, not swallowed
        assert len(failures) == 1
        assert "nonexistent_key" in failures[0].reason

        # ... and the log itself records the failure
        saved_log = mock_save.call_args_list[0][1]["table_data"]
        assert saved_log["status"][0] == "Failed"
        assert "nonexistent_key" in saved_log["status_reason"][0]

    def test_reapply_corrections_column_no_longer_available(
        self, correction_processor, sample_data
    ):
        """Failure reason 1: the targeted column was dropped upstream."""
        processor, mock_get, mock_save = correction_processor

        log = pl.DataFrame(
            {
                "date": [datetime.now()],
                "KEY": ["key1"],
                "ID": [None],
                "action": ["modify value"],
                "column": ["retired_column"],
                "current_value": ["old"],
                "new_value": ["new"],
                "reason": ["test correction"],
            }
        )
        mock_get.side_effect = [sample_data, log]

        failures = processor._reapply_all_corrections("test_alias")

        assert len(failures) == 1
        assert "retired_column" in failures[0].reason
        assert "no longer available" in failures[0].reason

        saved_log = mock_save.call_args_list[0][1]["table_data"]
        assert saved_log["status"][0] == "Failed"
        assert "no longer available" in saved_log["status_reason"][0]

    def test_reapply_corrections_current_value_changed(
        self, correction_processor, sample_data
    ):
        """Failure reason 2: the value has changed since the correction was
        logged, so blindly reapplying could clobber a legitimate update.
        """
        processor, mock_get, mock_save = correction_processor

        # Recorded current_value ("Something Else") no longer matches
        # sample_data's actual value for key1's name column ("John").
        log = pl.DataFrame(
            {
                "date": [datetime.now()],
                "KEY": ["key1"],
                "ID": [None],
                "action": ["modify value"],
                "column": ["name"],
                "current_value": ["Something Else"],
                "new_value": ["Johnny"],
                "reason": ["test correction"],
            }
        )
        mock_get.side_effect = [sample_data, log]

        failures = processor._reapply_all_corrections("test_alias")

        assert len(failures) == 1
        assert "changed since this correction was recorded" in failures[0].reason
        assert "Something Else" in failures[0].reason
        assert "John" in failures[0].reason

        # The name column must be untouched since the correction was skipped
        saved_data = mock_save.call_args_list[-1][1]["table_data"]
        assert saved_data.filter(pl.col("survey_key") == "key1")["name"][0] == "John"

    def test_reapply_corrections_current_value_unchanged_still_applies(
        self, correction_processor, sample_data
    ):
        """No recorded current_value, or a matching one, applies normally."""
        processor, mock_get, mock_save = correction_processor

        log = pl.DataFrame(
            {
                "date": [datetime.now()],
                "KEY": ["key1"],
                "ID": [None],
                "action": ["modify value"],
                "column": ["name"],
                "current_value": ["John"],
                "new_value": ["Johnny"],
                "reason": ["test correction"],
            }
        )
        mock_get.side_effect = [sample_data, log]

        failures = processor._reapply_all_corrections("test_alias")

        assert failures == []
        saved_data = mock_save.call_args_list[-1][1]["table_data"]
        assert saved_data.filter(pl.col("survey_key") == "key1")["name"][0] == "Johnny"

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

        assert mock_save.call_count == 2
        saved_data = mock_save.call_args_list[-1][1]["table_data"]
        assert saved_data.filter(pl.col("survey_key") == "key1")["name"][0] == "Johnny"
        assert len(failures) == 1
        assert "nonexistent_key" in failures[0].reason

        saved_log = mock_save.call_args_list[0][1]["table_data"]
        assert saved_log["status"].to_list() == ["Failed", "Successful"]

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
        assert mock_save.call_count == 2
        # ... and report the skipped correction instead of swallowing it
        assert len(failures) == 1
        assert failures[0].reason
        assert "nonexistent_column" in failures[0].reason
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


# ---------------------------------------------------------------------------
# Behavior tests against an in-memory store
#
# Storage is the only collaborator replaced here: the fake keeps tables in a
# dict keyed by (project_id, db_name, alias), so these tests observe behavior
# through the processor's public methods rather than inspecting save calls.
# ---------------------------------------------------------------------------


@pytest.fixture
def store():
    """Patch DuckDB storage with an in-memory dict and reset processor caches."""
    tables: dict[tuple[str, str, str], pl.DataFrame] = {}

    def fake_get(project_id, alias, db_name, type="pl"):
        return tables.get((project_id, db_name, alias), pl.DataFrame())

    def fake_save(project_id, table_data, alias, db_name="raw"):
        tables[(project_id, db_name, alias)] = table_data

    def fake_exists(project_id, alias, db_name):
        return (project_id, db_name, alias) in tables

    with (
        patch("datasure.processing.corrections.duckdb_get_table", fake_get),
        patch("datasure.processing.corrections.duckdb_save_table", fake_save),
        patch("datasure.processing.corrections.duckdb_table_exists", fake_exists),
    ):
        _clear_processor_caches()
        yield tables
        _clear_processor_caches()


def _clear_processor_caches():
    processor = CorrectionProcessor("any")
    processor.get_corrected_data.clear()
    processor.get_correction_log.clear()
    processor.get_data_summary.clear()
    processor.get_correction_summary.clear()


def _seed_prep(store, data: pl.DataFrame, project_id="p1", alias="survey"):
    store[(project_id, "prep", alias)] = data


class TestCorrectionLogSource:
    """Every log entry records which page produced it."""

    def test_new_entry_defaults_source_to_corrections_page(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        processor.apply_correction(
            alias="survey",
            key_col="survey_key",
            key_value="key1",
            action="modify value",
            column="name",
            current_value="John",
            new_value="Johnny",
            reason="typo",
        )

        log = processor.get_correction_log("survey")
        assert log["source"].to_list() == ["corrections_page"]

    def test_new_entry_records_given_source(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        processor.add_correction_entry(
            alias="survey",
            key_value="key1",
            current_id=None,
            action="remove row",
            column=None,
            current_value=None,
            new_value=None,
            reason="duplicate",
            source="duplicates",
        )

        log = processor.get_correction_log("survey")
        assert log["source"].to_list() == ["duplicates"]

    def test_legacy_log_loads_with_backfilled_source_and_no_data_loss(
        self, store, sample_corrections_log
    ):
        store[("p1", "logs", "corr_log_survey")] = sample_corrections_log
        processor = CorrectionProcessor("p1")

        log = processor.get_correction_log("survey")

        assert log["source"].to_list() == ["corrections_page"] * 3
        assert log["status"].to_list() == ["Successful"] * 3
        assert log.select(sample_corrections_log.columns).equals(sample_corrections_log)

    def test_removing_the_only_entry_leaves_an_empty_log_with_full_schema(
        self, store, sample_corrections_log
    ):
        # No prep table, so removal does not replay (and re-save) the log.
        store[("p1", "logs", "corr_log_survey")] = sample_corrections_log[:1]
        processor = CorrectionProcessor("p1")

        processor.remove_correction_entry("survey", 0)

        persisted = store[("p1", "logs", "corr_log_survey")]
        assert persisted.is_empty()
        assert persisted.columns == [
            "date",
            "KEY",
            "ID",
            "action",
            "column",
            "current_value",
            "new_value",
            "reason",
            "status",
            "status_reason",
            "source",
            "check_type",
        ]


class TestAcceptAction:
    """Accepting a flagged value records a decision without changing data."""

    def _accept_age(self, processor, key="key1", value=25, reason="verified"):
        processor.accept_value(
            alias="survey",
            key_col="survey_key",
            key_value=key,
            check_type="outliers",
            column="age",
            current_value=value,
            reason=reason,
        )

    def test_accept_logs_entry_and_leaves_corrected_data_unchanged(
        self, store, sample_data
    ):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        self._accept_age(processor)

        assert processor.get_corrected_data("survey").equals(sample_data)
        log = processor.get_correction_log("survey")
        assert log.select(
            "KEY", "action", "check_type", "column", "current_value", "reason"
        ).rows() == [("key1", "accept", "outliers", "age", "25", "verified")]

    def test_accept_requires_a_reason(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match="reason"):
            self._accept_age(processor, reason="  ")

        assert processor.get_correction_log("survey").is_empty()

    def test_accept_rejects_unknown_check_type(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match="check type"):
            processor.accept_value(
                alias="survey",
                key_col="survey_key",
                key_value="key1",
                check_type="missing",
                column="age",
                current_value=25,
                reason="ok",
            )

    def test_acceptance_is_active_while_value_is_unchanged(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")
        self._accept_age(processor)

        active = processor.get_active_acceptances("survey", "outliers", "survey_key")

        assert active.select("KEY", "column").rows() == [("key1", "age")]

    def test_acceptance_is_inactive_once_value_changes(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")
        self._accept_age(processor)

        processor.apply_correction(
            alias="survey",
            key_col="survey_key",
            key_value="key1",
            action="modify value",
            column="age",
            current_value=25,
            new_value=26,
            reason="re-interview",
        )

        active = processor.get_active_acceptances("survey", "outliers", "survey_key")
        assert active.is_empty()

    def test_acceptances_are_scoped_to_their_check_type(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")
        self._accept_age(processor)

        active = processor.get_active_acceptances("survey", "constraints", "survey_key")

        assert active.is_empty()

    def _gps_data(self):
        return pl.DataFrame(
            {
                "survey_key": ["key1", "key2"],
                "gps_lat": [5.6037, 6.6885],
                "gps_lon": [-0.187, -1.6244],
            }
        )

    def _accept_gps(self, processor):
        processor.accept_value(
            alias="survey",
            key_col="survey_key",
            key_value="key1",
            check_type="gps",
            column=None,
            current_value={"gps_lat": 5.6037, "gps_lon": -0.187},
            reason="Household relocated",
        )

    def test_gps_acceptance_is_active_while_both_coordinates_match(self, store):
        _seed_prep(store, self._gps_data())
        processor = CorrectionProcessor("p1")
        self._accept_gps(processor)

        active = processor.get_active_acceptances("survey", "gps", "survey_key")

        assert active["KEY"].to_list() == ["key1"]
        assert active["column"].to_list() == [None]

    def test_gps_acceptance_is_inactive_when_one_coordinate_changes(self, store):
        _seed_prep(store, self._gps_data())
        processor = CorrectionProcessor("p1")
        self._accept_gps(processor)

        processor.apply_correction(
            alias="survey",
            key_col="survey_key",
            key_value="key1",
            action="modify value",
            column="gps_lon",
            current_value=-0.187,
            new_value=-0.2,
            reason="re-recorded",
        )

        assert processor.get_active_acceptances(
            "survey", "gps", "survey_key"
        ).is_empty()

    def test_gps_acceptance_requires_a_coordinate_mapping(self, store):
        _seed_prep(store, self._gps_data())
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match="GPS"):
            processor.accept_value(
                alias="survey",
                key_col="survey_key",
                key_value="key1",
                check_type="gps",
                column="gps_lat",
                current_value=5.6037,
                reason="ok",
            )

    @pytest.mark.parametrize(
        "current_value",
        [{}, {"gps_lat": 5.6037}],
        ids=["empty", "latitude_only"],
    )
    def test_gps_acceptance_requires_both_coordinates(self, store, current_value):
        _seed_prep(store, self._gps_data())
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match="GPS"):
            processor.accept_value(
                alias="survey",
                key_col="survey_key",
                key_value="key1",
                check_type="gps",
                column=None,
                current_value=current_value,
                reason="ok",
            )

        assert processor.get_correction_log("survey").is_empty()

    def test_accept_rejects_a_value_that_changed_since_it_was_flagged(
        self, store, sample_data
    ):
        # key1's age is 25; the check page still shows the stale value 99
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match="has changed since it was flagged"):
            self._accept_age(processor, value=99)

        assert processor.get_correction_log("survey").is_empty()

    def test_gps_accept_rejects_a_changed_coordinate(self, store):
        _seed_prep(store, self._gps_data())
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match=r"'gps_lon'.*has changed"):
            processor.accept_value(
                alias="survey",
                key_col="survey_key",
                key_value="key1",
                check_type="gps",
                column=None,
                current_value={"gps_lat": 5.6037, "gps_lon": -0.2},
                reason="ok",
            )

        assert processor.get_correction_log("survey").is_empty()

    @pytest.mark.parametrize(
        ("key", "column", "message"),
        [
            ("missing", "age", "Key value 'missing' not found"),
            ("key1", "height", "Column 'height' not found"),
        ],
    )
    def test_accept_rejects_unknown_key_or_column(
        self, store, sample_data, key, column, message
    ):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match=message):
            processor.accept_value(
                alias="survey",
                key_col="survey_key",
                key_value=key,
                check_type="outliers",
                column=column,
                current_value=25,
                reason="ok",
            )

        assert processor.get_correction_log("survey").is_empty()

    def test_apply_corrections_rejects_a_stale_acceptance_atomically(
        self, store, sample_data
    ):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match="has changed since it was flagged"):
            processor.apply_corrections(
                alias="survey",
                key_col="survey_key",
                entries=[
                    CorrectionEntry(
                        key_value="key2",
                        action="modify value",
                        column="age",
                        current_value=30,
                        new_value=31,
                        reason="typo",
                    ),
                    CorrectionEntry(
                        key_value="key1",
                        action="accept",
                        check_type="outliers",
                        column="age",
                        current_value=99,
                        reason="verified",
                    ),
                ],
                source="outliers",
            )

        assert processor.get_corrected_data("survey").equals(sample_data)
        assert processor.get_correction_log("survey").is_empty()

    def test_replay_skips_accept_rows(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")
        self._accept_age(processor, key="key1", value=25)
        processor.apply_correction(
            alias="survey",
            key_col="survey_key",
            key_value="key2",
            action="modify value",
            column="name",
            current_value="Jane",
            new_value="Janet",
            reason="typo",
        )
        # The accepted record is later dropped from prep, so a replayed
        # accept row would have no KEY to match.
        _seed_prep(store, sample_data.filter(pl.col("survey_key") != "key1"))

        failures = processor.refresh_corrected_data("survey")

        assert failures == []
        corrected = processor.get_corrected_data("survey")
        assert corrected["name"].to_list() == ["Janet", "Bob"]
        assert processor.get_correction_log("survey")["status"].to_list() == [
            "Successful",
            "Successful",
        ]

    def test_accept_rows_can_be_removed(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")
        self._accept_age(processor)

        summaries = processor.get_correction_summary("survey")
        processor.remove_correction_entry("survey", summaries[0]["index"])

        assert processor.get_correction_log("survey").is_empty()
        assert processor.get_active_acceptances(
            "survey", "outliers", "survey_key"
        ).is_empty()


class TestCacheIsScopedToProject:
    """Cached reads are keyed on project as well as alias."""

    def test_projects_sharing_an_alias_do_not_share_corrected_data(self, store):
        _seed_prep(store, pl.DataFrame({"KEY": ["a"]}), project_id="p1")
        _seed_prep(store, pl.DataFrame({"KEY": ["b"]}), project_id="p2")

        first = CorrectionProcessor("p1").get_corrected_data("survey")
        second = CorrectionProcessor("p2").get_corrected_data("survey")

        assert first["KEY"].to_list() == ["a"]
        assert second["KEY"].to_list() == ["b"]

    def test_projects_sharing_an_alias_do_not_share_correction_logs(
        self, store, sample_corrections_log
    ):
        store[("p1", "logs", "corr_log_survey")] = sample_corrections_log

        assert CorrectionProcessor("p1").get_correction_log("survey").height == 3
        assert CorrectionProcessor("p2").get_correction_log("survey").is_empty()
        assert CorrectionProcessor("p2").get_correction_summary("survey") == []


class TestApplyCorrectionsAtomically:
    """Several entries apply together, or not at all."""

    def test_applies_every_entry_and_logs_each_with_the_source(
        self, store, sample_data
    ):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        processor.apply_corrections(
            alias="survey",
            key_col="survey_key",
            entries=[
                CorrectionEntry(
                    key_value="key1",
                    action="modify value",
                    column="name",
                    current_value="John",
                    new_value="Jon",
                    reason="keep first",
                ),
                CorrectionEntry(
                    key_value="key1",
                    action="modify value",
                    column="age",
                    current_value=25,
                    new_value=26,
                    reason="keep first",
                ),
                CorrectionEntry(
                    key_value="key2", action="remove row", reason="duplicate"
                ),
            ],
            source="duplicates",
        )

        corrected = processor.get_corrected_data("survey")
        assert corrected.select("survey_key", "name", "age").rows() == [
            ("key1", "Jon", 26),
            ("key3", "Bob", 35),
        ]
        log = processor.get_correction_log("survey")
        assert log["action"].to_list() == ["modify value", "modify value", "remove row"]
        assert log["source"].to_list() == ["duplicates"] * 3

    def test_an_invalid_entry_applies_nothing(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match="no_such_column"):
            processor.apply_corrections(
                alias="survey",
                key_col="survey_key",
                entries=[
                    CorrectionEntry(
                        key_value="key1",
                        action="modify value",
                        column="name",
                        current_value="John",
                        new_value="Jon",
                        reason="fix",
                    ),
                    CorrectionEntry(
                        key_value="key2",
                        action="modify value",
                        column="no_such_column",
                        new_value="x",
                        reason="fix",
                    ),
                ],
            )

        assert processor.get_corrected_data("survey").equals(sample_data)
        assert processor.get_correction_log("survey").is_empty()

    def test_an_entry_invalidated_by_an_earlier_entry_applies_nothing(
        self, store, sample_data
    ):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match="key1"):
            processor.apply_corrections(
                alias="survey",
                key_col="survey_key",
                entries=[
                    CorrectionEntry(
                        key_value="key1", action="remove row", reason="dup"
                    ),
                    CorrectionEntry(
                        key_value="key1",
                        action="remove value",
                        column="name",
                        reason="dup",
                    ),
                ],
            )

        assert processor.get_corrected_data("survey").equals(sample_data)
        assert processor.get_correction_log("survey").is_empty()

    def test_can_mix_an_acceptance_with_corrections(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        processor.apply_corrections(
            alias="survey",
            key_col="survey_key",
            entries=[
                CorrectionEntry(
                    key_value="key1",
                    action="accept",
                    check_type="outliers",
                    column="age",
                    current_value=25,
                    reason="verified",
                ),
                CorrectionEntry(
                    key_value="key2",
                    action="modify value",
                    column="age",
                    current_value=30,
                    new_value=31,
                    reason="typo",
                ),
            ],
            source="outliers",
        )

        assert processor.get_corrected_data("survey")["age"].to_list() == [25, 31, 35]
        active = processor.get_active_acceptances("survey", "outliers", "survey_key")
        assert active["KEY"].to_list() == ["key1"]

    def test_every_entry_needs_a_reason(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match="reason"):
            processor.apply_corrections(
                alias="survey",
                key_col="survey_key",
                entries=[
                    CorrectionEntry(key_value="key1", action="remove row", reason="")
                ],
            )


class TestCorrectionSummaryDescribesAcceptances:
    def test_accept_rows_are_listed_with_their_check_type(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")
        processor.accept_value(
            alias="survey",
            key_col="survey_key",
            key_value="key1",
            check_type="outliers",
            column="age",
            current_value=25,
            reason="verified",
        )

        (summary,) = processor.get_correction_summary("survey")

        assert summary["action"] == "accept"
        assert summary["check_type"] == "outliers"
        assert summary["description"] == "Accept outliers flag on age for key key1"

    def test_gps_accept_rows_describe_the_coordinates(self, store):
        _seed_prep(store, pl.DataFrame({"KEY": ["k1"], "lat": [1.0], "lon": [2.0]}))
        processor = CorrectionProcessor("p1")
        processor.accept_value(
            alias="survey",
            key_col="KEY",
            key_value="k1",
            check_type="gps",
            column=None,
            current_value={"lat": 1.0, "lon": 2.0},
            reason="verified",
        )

        (summary,) = processor.get_correction_summary("survey")

        assert summary["description"] == "Accept gps flag on coordinates for key k1"


class TestAcceptanceMatching:
    """Acceptances compare values, not their pandas/polars string forms."""

    def _accept(self, processor, key, column, value, key_col="KEY"):
        processor.accept_value(
            alias="survey",
            key_col=key_col,
            key_value=key,
            check_type="constraints",
            column=column,
            current_value=value,
            reason="verified",
        )

    def test_nan_accepted_value_matches_a_missing_cell(self, store):
        _seed_prep(
            store,
            pl.DataFrame(
                {"KEY": ["k1"], "age": [None]},
                schema={"KEY": pl.String, "age": pl.Int64},
            ),
        )
        processor = CorrectionProcessor("p1")
        self._accept(processor, "k1", "age", float("nan"))

        active = processor.get_active_acceptances("survey", "constraints", "KEY")

        assert active["KEY"].to_list() == ["k1"]

    def test_float_form_of_an_integer_matches(self, store):
        # pandas turns an int column with nulls into floats: 25 arrives as 25.0
        _seed_prep(store, pl.DataFrame({"KEY": ["k1"], "age": [25]}))
        processor = CorrectionProcessor("p1")
        self._accept(processor, "k1", "age", 25.0)

        active = processor.get_active_acceptances("survey", "constraints", "KEY")

        assert active["KEY"].to_list() == ["k1"]

    def test_a_different_number_does_not_match(self, store):
        _seed_prep(store, pl.DataFrame({"KEY": ["k1"], "age": [25]}))
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match="has changed since it was flagged"):
            self._accept(processor, "k1", "age", 25.5)

        assert processor.get_correction_log("survey").is_empty()

    def test_non_string_key_column_is_supported(self, store):
        _seed_prep(store, pl.DataFrame({"hhid": [101, 102], "age": [25, 30]}))
        processor = CorrectionProcessor("p1")
        self._accept(processor, "102", "age", 30, key_col="hhid")

        active = processor.get_active_acceptances("survey", "constraints", "hhid")

        assert active["KEY"].to_list() == ["102"]

    def test_duplicate_keys_must_all_hold_the_accepted_value(self, store):
        _seed_prep(store, pl.DataFrame({"KEY": ["k1", "k1"], "age": [25, 40]}))
        processor = CorrectionProcessor("p1")

        with pytest.raises(ValueError, match="has changed since it was flagged"):
            self._accept(processor, "k1", "age", 25)

        assert processor.get_correction_log("survey").is_empty()


class TestApplyCorrectionsStorageFailure:
    def test_failed_log_save_leaves_corrected_data_unchanged(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")
        processor.get_corrected_data("survey")  # materialize the corrected table

        def failing_save(project_id, table_data, alias, db_name="raw"):
            if db_name == "logs":
                raise OSError("disk full")
            store[(project_id, db_name, alias)] = table_data

        with (
            patch("datasure.processing.corrections.duckdb_save_table", failing_save),
            pytest.raises(OSError, match="disk full"),
        ):
            processor.apply_corrections(
                alias="survey",
                key_col="survey_key",
                entries=[
                    CorrectionEntry(key_value="key1", action="remove row", reason="dup")
                ],
            )

        assert processor.get_corrected_data("survey").equals(sample_data)
        assert processor.get_correction_log("survey").is_empty()


class TestRefreshExistingCorrectedData:
    """Replays corrections after an upstream change, only once corrections exist."""

    def _fix_name(self, processor):
        processor.apply_correction(
            alias="survey",
            key_col="survey_key",
            key_value="key1",
            action="modify value",
            column="name",
            current_value="John",
            new_value="Johnny",
            reason="typo",
        )

    def test_does_nothing_without_a_corrected_table(self, store, sample_data):
        _seed_prep(store, sample_data)

        failures = CorrectionProcessor("p1").refresh_existing_corrected_data("survey")

        assert failures == []
        assert ("p1", "corrected", "survey") not in store

    def test_rebuilds_corrected_table_from_new_prep(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")
        self._fix_name(processor)

        # A prep step drops a column after the correction was made.
        _seed_prep(store, sample_data.drop("age"))
        failures = processor.refresh_existing_corrected_data("survey")

        assert failures == []
        corrected = processor.get_corrected_data("survey")
        assert "age" not in corrected.columns
        assert corrected["name"].to_list() == ["Johnny", "Jane", "Bob"]

    def test_reports_corrections_that_no_longer_apply(self, store, sample_data):
        _seed_prep(store, sample_data)
        processor = CorrectionProcessor("p1")
        self._fix_name(processor)

        # A prep step drops the corrected column.
        _seed_prep(store, sample_data.drop("name"))
        failures = processor.refresh_existing_corrected_data("survey")

        assert len(failures) == 1
        assert processor.get_correction_log("survey")["status"].to_list() == ["Failed"]
