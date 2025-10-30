"""Comprehensive tests for configuration utilities module."""

from unittest.mock import Mock, mock_open, patch

import polars as pl
import pytest
from pydantic import ValidationError

from datasure.utils.config_utils import (
    BackcheckColumnSelectors,
    CheckConfiguration,
    ConfigurationFormState,
    ConfigurationService,
    DatasetService,
    SurveyColumnSelections,
    _handle_configuration_submission,
    add_check_configuration_form,
    remove_check_configuration_form,
    render_backcheck_column_selectors,
    render_backcheck_dataset_selector,
    render_configuration_table,
    render_page_name_input,
    render_survey_column_selectors,
    render_survey_dataset_selector,
)

# ============================================================================
# PYDANTIC MODELS TESTS
# ============================================================================


class TestCheckConfiguration:
    """Test CheckConfiguration Pydantic model."""

    def test_valid_configuration_all_fields(self):
        """Test creating a valid configuration with all fields."""
        config = CheckConfiguration(
            page_name="Test Page",
            survey_data_name="survey_data",
            survey_key="key_column",
            survey_id="id_column",
            survey_date="date_column",
            enumerator="enum_column",
            backcheck_data_name="backcheck_data",
            backcheck_date="backcheck_date_col",
            backchecker="backchecker_col",
            tracking_data_name="tracking_data",
        )
        assert config.page_name == "Test Page"
        assert config.survey_data_name == "survey_data"
        assert config.survey_key == "key_column"
        assert config.survey_id == "id_column"
        assert config.survey_date == "date_column"
        assert config.enumerator == "enum_column"
        assert config.backcheck_data_name == "backcheck_data"
        assert config.backcheck_date == "backcheck_date_col"
        assert config.backchecker == "backchecker_col"
        assert config.tracking_data_name == "tracking_data"

    def test_valid_configuration_minimum_fields(self):
        """Test creating a valid configuration with only required fields."""
        config = CheckConfiguration(
            page_name="Test",
            survey_data_name="survey",
            survey_key="key",
            survey_id="id",
            survey_date=None,
            enumerator=None,
            backcheck_data_name="backcheck",
            backcheck_date=None,
            backchecker=None,
        )
        assert config.page_name == "Test"
        assert config.survey_data_name == "survey"
        assert config.survey_key == "key"
        assert config.survey_id == "id"
        assert config.survey_date is None
        assert config.enumerator is None
        assert config.backcheck_data_name == "backcheck"
        assert config.backcheck_date is None
        assert config.backchecker is None
        assert config.tracking_data_name is None

    def test_page_name_too_long(self):
        """Test that page name over 20 characters raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CheckConfiguration(
                page_name="This is a very long page name that exceeds twenty characters",
                survey_data_name="survey_data",
                survey_key="key_column",
                survey_id="id",
                backcheck_data_name="backcheck",
            )
        errors = exc_info.value.errors()
        assert any("page_name" in str(e.get("loc")) for e in errors)

    def test_page_name_empty_string(self):
        """Test that empty page name raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CheckConfiguration(
                page_name="",
                survey_data_name="survey_data",
                survey_key="key_column",
                survey_id="id",
                backcheck_data_name="backcheck",
            )
        errors = exc_info.value.errors()
        assert any("page_name" in str(e.get("loc")) for e in errors)

    def test_page_name_whitespace_only(self):
        """Test that whitespace-only page name raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CheckConfiguration(
                page_name="   ",
                survey_data_name="survey_data",
                survey_key="key_column",
                survey_id="id",
                backcheck_data_name="backcheck",
            )
        errors = exc_info.value.errors()
        assert any("page_name" in str(e.get("loc")) for e in errors)

    def test_page_name_whitespace_stripped(self):
        """Test that page name whitespace is stripped."""
        config = CheckConfiguration(
            page_name="  Test Page  ",
            survey_data_name="survey_data",
            survey_key="key_column",
            survey_id="id",
            survey_date=None,
            enumerator=None,
            backcheck_data_name="backcheck",
            backcheck_date=None,
            backchecker=None,
        )
        assert config.page_name == "Test Page"

    def test_page_name_exactly_20_chars(self):
        """Test page name with exactly 20 characters is valid."""
        page_name = "a" * 20
        config = CheckConfiguration(
            page_name=page_name,
            survey_data_name="survey",
            survey_key="key",
            survey_id="id",
            survey_date=None,
            enumerator=None,
            backcheck_data_name="backcheck",
            backcheck_date=None,
            backchecker=None,
        )
        assert config.page_name == page_name
        assert len(config.page_name) == 20

    def test_missing_required_page_name(self):
        """Test that missing page_name raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CheckConfiguration(
                survey_data_name="survey_data",
                survey_key="key_column",
                survey_id="id",
                backcheck_data_name="backcheck",
            )
        errors = exc_info.value.errors()
        assert any("page_name" in str(e.get("loc")) for e in errors)

    def test_missing_required_survey_data_name(self):
        """Test that missing survey_data_name raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CheckConfiguration(
                page_name="Test",
                survey_key="key_column",
                survey_id="id",
                backcheck_data_name="backcheck",
            )
        errors = exc_info.value.errors()
        assert any("survey_data_name" in str(e.get("loc")) for e in errors)

    def test_missing_required_survey_key(self):
        """Test that missing survey_key raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CheckConfiguration(
                page_name="Test",
                survey_data_name="survey",
                survey_id="id",
                backcheck_data_name="backcheck",
            )
        errors = exc_info.value.errors()
        assert any("survey_key" in str(e.get("loc")) for e in errors)

    def test_empty_survey_data_name(self):
        """Test that empty survey_data_name raises error."""
        with pytest.raises(ValidationError):
            CheckConfiguration(
                page_name="Test",
                survey_data_name="",
                survey_key="key",
                survey_id="id",
                backcheck_data_name="backcheck",
            )

    def test_empty_survey_key(self):
        """Test that empty survey_key raises error."""
        with pytest.raises(ValidationError):
            CheckConfiguration(
                page_name="Test",
                survey_data_name="survey",
                survey_key="",
                survey_id="id",
                backcheck_data_name="backcheck",
            )

    def test_to_dict_all_fields(self):
        """Test conversion to dictionary with all fields."""
        config = CheckConfiguration(
            page_name="Test",
            survey_data_name="survey",
            survey_key="key",
            survey_id="id",
            survey_date="date",
            enumerator="enum",
            backcheck_data_name="backcheck",
            backcheck_date="bc_date",
            backchecker="bc_checker",
            tracking_data_name="tracking",
        )
        result = config.to_dict()
        assert isinstance(result, dict)
        assert result["page_name"] == "Test"
        assert result["survey_data_name"] == "survey"
        assert result["survey_key"] == "key"
        assert result["survey_id"] == "id"
        assert result["survey_date"] == "date"
        assert result["enumerator"] == "enum"
        assert result["backcheck_data_name"] == "backcheck"
        assert result["backcheck_date"] == "bc_date"
        assert result["backchecker"] == "bc_checker"
        assert result["tracking_data_name"] == "tracking"

    def test_to_dict_minimum_fields(self):
        """Test conversion to dictionary with only required fields."""
        config = CheckConfiguration(
            page_name="Test",
            survey_data_name="survey",
            survey_key="key",
            survey_id="id",
            survey_date=None,
            enumerator=None,
            backcheck_data_name="backcheck",
            backcheck_date=None,
            backchecker=None,
        )
        result = config.to_dict()
        assert isinstance(result, dict)
        assert result["page_name"] == "Test"
        assert result["survey_id"] == "id"
        assert result["survey_date"] is None


class TestSurveyColumnSelections:
    """Test SurveyColumnSelections model."""

    def test_all_fields_none_by_default(self):
        """Test that all fields are None by default."""
        selections = SurveyColumnSelections()
        assert selections.survey_key is None
        assert selections.survey_id is None
        assert selections.survey_date is None
        assert selections.enumerator is None

    def test_set_all_fields(self):
        """Test setting all fields."""
        selections = SurveyColumnSelections(
            survey_key="key",
            survey_id="id",
            survey_date="date",
            enumerator="enum",
        )
        assert selections.survey_key == "key"
        assert selections.survey_id == "id"
        assert selections.survey_date == "date"
        assert selections.enumerator == "enum"


class TestBackcheckColumnSelectors:
    """Test BackcheckColumnSelectors model."""

    def test_all_fields_none_by_default(self):
        """Test that all fields are None by default."""
        selections = BackcheckColumnSelectors()
        assert selections.backcheck_date is None
        assert selections.backchecker is None

    def test_set_all_fields(self):
        """Test setting all fields."""
        selections = BackcheckColumnSelectors(
            backcheck_date="bc_date",
            backchecker="bc_checker",
        )
        assert selections.backcheck_date == "bc_date"
        assert selections.backchecker == "bc_checker"


# ============================================================================
# CONFIGURATION SERVICE TESTS
# ============================================================================


class TestConfigurationService:
    """Test ConfigurationService business logic."""

    @pytest.fixture
    def mock_empty_df(self):
        """Return an empty Polars DataFrame."""
        return pl.DataFrame()

    @pytest.fixture
    def mock_config_df(self):
        """Return a sample configuration DataFrame."""
        return pl.DataFrame(
            [
                {
                    "page_name": "Existing Page",
                    "survey_data_name": "survey_1",
                    "survey_key": "key",
                    "survey_id": "id",
                    "survey_date": "date",
                    "enumerator": "enum",
                    "backcheck_data_name": "backcheck",
                    "backcheck_date": "bc_date",
                    "backchecker": "bc_checker",
                    "tracking_data_name": "tracking",
                }
            ]
        )

    @pytest.fixture
    def mock_multi_config_df(self):
        """Return a DataFrame with multiple configurations."""
        return pl.DataFrame(
            [
                {
                    "page_name": "Page One",
                    "survey_data_name": "survey_1",
                    "survey_key": "key1",
                    "survey_id": "id1",
                    "survey_date": None,
                    "enumerator": None,
                    "backcheck_data_name": "backcheck_1",
                    "backcheck_date": None,
                    "backchecker": None,
                    "tracking_data_name": None,
                },
                {
                    "page_name": "Page Two",
                    "survey_data_name": "survey_2",
                    "survey_key": "key2",
                    "survey_id": "id2",
                    "survey_date": None,
                    "enumerator": None,
                    "backcheck_data_name": "backcheck_2",
                    "backcheck_date": None,
                    "backchecker": None,
                    "tracking_data_name": None,
                },
            ]
        )

    def test_initialization(self):
        """Test service initialization."""
        service = ConfigurationService("test_project_123")
        assert service.project_id == "test_project_123"

    @patch("datasure.utils.config_utils.duckdb_get_table")
    def test_get_all_configurations(self, mock_get_table, mock_config_df):
        """Test getting all configurations."""
        mock_get_table.return_value = mock_config_df
        service = ConfigurationService("test_project")

        result = service.get_all_configurations()

        mock_get_table.assert_called_once_with(
            project_id="test_project",
            alias="check_config",
            db_name="logs",
        )
        assert result.equals(mock_config_df)

    def test_get_page_names_empty(self, mock_empty_df):
        """Test getting page names from empty configuration."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_empty_df)

        result = service.get_page_names()

        assert result == []
        assert isinstance(result, list)

    def test_get_page_names_with_data(self, mock_config_df):
        """Test getting page names from configuration with data."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_config_df)

        names = service.get_page_names()

        assert names == ["Existing Page"]
        assert len(names) == 1

    def test_get_page_names_multiple(self, mock_multi_config_df):
        """Test getting multiple page names."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_multi_config_df)

        names = service.get_page_names()

        assert len(names) == 2
        assert "Page One" in names
        assert "Page Two" in names

    def test_page_name_exists_empty_config(self, mock_empty_df):
        """Test page name check with empty configuration."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_empty_df)

        assert service.page_name_exists("Test Page") is False
        assert service.page_name_exists("Any Name") is False

    def test_page_name_exists_with_existing(self, mock_config_df):
        """Test page name check with existing configuration."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_config_df)

        assert service.page_name_exists("Existing Page") is True
        assert service.page_name_exists("New Page") is False
        assert service.page_name_exists("existing page") is False  # Case sensitive

    def test_validate_configuration_success(self, mock_empty_df):
        """Test successful configuration validation."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_empty_df)

        config_data = {
            "page_name": "New Page",
            "survey_data_name": "survey_1",
            "survey_key": "key_column",
            "survey_id": "id_column",
            "survey_date": None,
            "enumerator": None,
            "backcheck_data_name": "backcheck_1",
            "backcheck_date": None,
            "backchecker": None,
        }

        is_valid, error_msg, config = service.validate_configuration(config_data)

        assert is_valid is True
        assert error_msg is None
        assert config is not None
        assert isinstance(config, CheckConfiguration)
        assert config.page_name == "New Page"

    def test_validate_configuration_duplicate_name(self, mock_config_df):
        """Test validation fails for duplicate page name."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_config_df)

        config_data = {
            "page_name": "Existing Page",
            "survey_data_name": "survey_1",
            "survey_key": "key_column",
            "survey_id": "id_column",
            "survey_date": None,
            "enumerator": None,
            "backcheck_data_name": "backcheck_1",
            "backcheck_date": None,
            "backchecker": None,
        }

        is_valid, error_msg, config = service.validate_configuration(config_data)

        assert is_valid is False
        assert "already exists" in error_msg
        assert "Existing Page" in error_msg
        assert config is None

    def test_validate_configuration_invalid_page_name_too_long(self, mock_empty_df):
        """Test validation fails for too long page name."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_empty_df)

        config_data = {
            "page_name": "This page name is way too long and exceeds the maximum",
            "survey_data_name": "survey_1",
            "survey_key": "key_column",
            "survey_id": "id_column",
            "survey_date": None,
            "enumerator": None,
            "backcheck_data_name": "backcheck_1",
            "backcheck_date": None,
            "backchecker": None,
        }

        is_valid, error_msg, config = service.validate_configuration(config_data)

        assert is_valid is False
        assert error_msg is not None
        assert config is None

    def test_validate_configuration_invalid_empty_page_name(self, mock_empty_df):
        """Test validation fails for empty page name."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_empty_df)

        config_data = {
            "page_name": "",
            "survey_data_name": "survey_1",
            "survey_key": "key_column",
            "survey_id": "id_column",
            "survey_date": None,
            "enumerator": None,
            "backcheck_data_name": "backcheck_1",
            "backcheck_date": None,
            "backchecker": None,
        }

        is_valid, error_msg, config = service.validate_configuration(config_data)

        assert is_valid is False
        assert error_msg is not None
        assert config is None

    def test_validate_configuration_missing_required_field(self, mock_empty_df):
        """Test validation fails for missing required field."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_empty_df)

        config_data = {
            "page_name": "Test",
            "survey_data_name": "survey_1",
            # Missing survey_key
        }

        is_valid, error_msg, config = service.validate_configuration(config_data)

        assert is_valid is False
        assert error_msg is not None
        assert config is None

    def test_format_validation_error_with_errors(self):
        """Test formatting of Pydantic validation errors."""
        service = ConfigurationService("test_project")

        try:
            CheckConfiguration(
                page_name="",
                survey_data_name="survey",
                survey_key="key",
                survey_id="id",
                backcheck_data_name="backcheck",
            )
        except ValidationError as e:
            formatted_error = service._format_validation_error(e)
            assert isinstance(formatted_error, str)
            assert len(formatted_error) > 0
            # Should contain field name and message
            assert ":" in formatted_error

    def test_format_validation_error_empty(self):
        """Test formatting validation error with no errors."""
        service = ConfigurationService("test_project")

        # Create a mock ValidationError with no errors
        mock_error = Mock(spec=ValidationError)
        mock_error.errors.return_value = []

        formatted = service._format_validation_error(mock_error)
        assert formatted == "Validation error occurred"

    @patch("builtins.open", new_callable=mock_open, read_data="template content")
    def test_add_page_file_creates_new_file(self, mock_file):
        """Test that _add_page_file creates a new output view file."""
        service = ConfigurationService("test_project")

        with patch("pathlib.Path.exists", return_value=False):
            service._add_page_file(page_number=1)

        # Check that file was read and written
        assert mock_file.call_count == 2  # One for reading, one for writing

    @patch("builtins.open", new_callable=mock_open, read_data="template content")
    def test_add_page_file_skip_if_exists_no_replace(self, mock_file):
        """Test that _add_page_file skips if file exists and replace=False."""
        service = ConfigurationService("test_project")

        with patch("pathlib.Path.exists", return_value=True):
            service._add_page_file(page_number=1, replace=False)

        # File should not be opened
        mock_file.assert_not_called()

    @patch("builtins.open", new_callable=mock_open, read_data="template content")
    def test_add_page_file_replace_if_exists(self, mock_file):
        """Test that _add_page_file replaces file if exists and replace=True."""
        service = ConfigurationService("test_project")

        with patch("pathlib.Path.exists", return_value=True):
            service._add_page_file(page_number=1, replace=True)

        # File should be read and written
        assert mock_file.call_count == 2

    @patch("datasure.utils.config_utils.duckdb_save_table")
    @patch.object(ConfigurationService, "_add_page_file")
    def test_add_configuration_empty_log(
        self, mock_add_page_file, mock_save_table, mock_empty_df
    ):
        """Test adding configuration when log is empty."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_empty_df)

        config = CheckConfiguration(
            page_name="New Page",
            survey_data_name="survey_1",
            survey_key="key",
            survey_id="id",
            survey_date=None,
            enumerator=None,
            backcheck_data_name="backcheck_1",
            backcheck_date=None,
            backchecker=None,
        )

        result = service.add_configuration(config)

        assert result is True
        mock_save_table.assert_called_once()
        mock_add_page_file.assert_called_once_with(1)
        call_args = mock_save_table.call_args
        assert call_args[0][0] == "test_project"
        saved_df = call_args[0][1]
        assert len(saved_df) == 1
        assert saved_df["page_name"][0] == "New Page"

    @patch("datasure.utils.config_utils.duckdb_save_table")
    @patch.object(ConfigurationService, "_add_page_file")
    def test_add_configuration_existing_log(
        self, mock_add_page_file, mock_save_table, mock_config_df
    ):
        """Test adding configuration when log already has data."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_config_df)

        config = CheckConfiguration(
            page_name="New Page",
            survey_data_name="survey_2",
            survey_key="key2",
            survey_id="id2",
            survey_date=None,
            enumerator=None,
            backcheck_data_name="backcheck_2",
            backcheck_date=None,
            backchecker=None,
        )

        result = service.add_configuration(config)

        assert result is True
        mock_save_table.assert_called_once()
        mock_add_page_file.assert_called_once_with(2)
        call_args = mock_save_table.call_args
        saved_df = call_args[0][1]
        assert len(saved_df) == 2  # Original + new
        page_names = saved_df["page_name"].to_list()
        assert "Existing Page" in page_names
        assert "New Page" in page_names

    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists")
    def test_remove_page_file_deletes_file(self, mock_exists, mock_unlink):
        """Test that _remove_page_file deletes the file if it exists."""
        service = ConfigurationService("test_project")
        mock_exists.return_value = True

        service._remove_page_file(page_number=1)

        mock_exists.assert_called_once()
        mock_unlink.assert_called_once()

    @patch("pathlib.Path.unlink")
    @patch("pathlib.Path.exists")
    def test_remove_page_file_skip_if_not_exists(self, mock_exists, mock_unlink):
        """Test that _remove_page_file does nothing if file doesn't exist."""
        service = ConfigurationService("test_project")
        mock_exists.return_value = False

        service._remove_page_file(page_number=1)

        mock_exists.assert_called_once()
        mock_unlink.assert_not_called()

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.duckdb_save_table")
    @patch.object(ConfigurationService, "_remove_page_file")
    def test_remove_configuration_success(
        self, mock_remove_page_file, mock_save_table, mock_st, mock_config_df
    ):
        """Test successfully removing a configuration."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_config_df)

        result = service.remove_configuration("Existing Page")

        assert result is True
        mock_save_table.assert_called_once()
        mock_remove_page_file.assert_called_once_with(1)
        call_args = mock_save_table.call_args
        saved_df = call_args[0][1]
        assert len(saved_df) == 0  # All removed

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.duckdb_save_table")
    @patch.object(ConfigurationService, "_remove_page_file")
    def test_remove_configuration_from_multiple(
        self, mock_remove_page_file, mock_save_table, mock_st, mock_multi_config_df
    ):
        """Test removing one configuration from multiple."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_multi_config_df)

        result = service.remove_configuration("Page One")

        assert result is True
        mock_save_table.assert_called_once()
        mock_remove_page_file.assert_called_once_with(1)
        call_args = mock_save_table.call_args
        saved_df = call_args[0][1]
        assert len(saved_df) == 1
        assert saved_df["page_name"][0] == "Page Two"

    def test_remove_configuration_empty_log(self, mock_empty_df):
        """Test removing configuration from empty log returns False."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_empty_df)

        result = service.remove_configuration("Any Page")

        assert result is False


# ============================================================================
# DATASET SERVICE TESTS
# ============================================================================


class TestDatasetService:
    """Test DatasetService utilities."""

    def test_initialization(self):
        """Test service initialization."""
        service = DatasetService("test_project_456")
        assert service.project_id == "test_project_456"

    @patch("datasure.utils.config_utils.duckdb_get_table")
    @patch("datasure.utils.config_utils.get_df_info")
    def test_get_dataset_columns(self, mock_get_df_info, mock_get_table):
        """Test getting categorized columns from a dataset."""
        # Mock the dataframe
        mock_df = Mock()
        mock_get_table.return_value = mock_df

        # Mock get_df_info return value
        mock_get_df_info.return_value = (
            None,
            ["col1", "col2"],  # string_columns
            ["num1", "num2", "num3"],  # numeric_columns
            ["date1"],  # datetime_columns
            None,
        )

        service = DatasetService("test_project")
        datetime_cols, categorical_cols = service.get_dataset_columns("survey_1")

        mock_get_table.assert_called_once_with(
            project_id="test_project",
            alias="survey_1",
            db_name="prep",
            type="pd",
        )
        mock_get_df_info.assert_called_once_with(mock_df, cols_only=True)

        assert datetime_cols == ["date1"]
        assert categorical_cols == ["col1", "col2", "num1", "num2", "num3"]

    def test_get_available_aliases_excluding_none(self):
        """Test filtering aliases with empty exclusion list."""
        service = DatasetService("test_project")

        all_aliases = ["survey_1", "survey_2", "backcheck_1"]
        exclude = []

        result = service.get_available_aliases_excluding(all_aliases, exclude)

        assert result == ["backcheck_1", "survey_1", "survey_2"]
        assert len(result) == 3

    def test_get_available_aliases_excluding_some(self):
        """Test filtering aliases by exclusion list."""
        service = DatasetService("test_project")

        all_aliases = ["survey_1", "survey_2", "backcheck_1", "tracking_1"]
        exclude = ["survey_1", "backcheck_1"]

        result = service.get_available_aliases_excluding(all_aliases, exclude)

        assert result == ["survey_2", "tracking_1"]
        assert len(result) == 2
        assert "survey_1" not in result
        assert "backcheck_1" not in result

    def test_get_available_aliases_excluding_all(self):
        """Test filtering aliases when all are excluded."""
        service = DatasetService("test_project")

        all_aliases = ["survey_1", "survey_2"]
        exclude = ["survey_1", "survey_2"]

        result = service.get_available_aliases_excluding(all_aliases, exclude)

        assert result == []

    def test_get_available_aliases_sorted(self):
        """Test that results are sorted alphabetically."""
        service = DatasetService("test_project")

        all_aliases = ["z_survey", "a_survey", "m_survey", "b_survey"]
        exclude = []

        result = service.get_available_aliases_excluding(all_aliases, exclude)

        assert result == ["a_survey", "b_survey", "m_survey", "z_survey"]

    def test_get_available_aliases_nonexistent_exclude(self):
        """Test excluding items that don't exist in the list."""
        service = DatasetService("test_project")

        all_aliases = ["survey_1", "survey_2"]
        exclude = ["survey_3", "survey_4"]

        result = service.get_available_aliases_excluding(all_aliases, exclude)

        assert result == ["survey_1", "survey_2"]


# ============================================================================
# UI COMPONENTS TESTS
# ============================================================================


class TestConfigurationFormState:
    """Test ConfigurationFormState class."""

    def test_initialization(self):
        """Test form state initialization."""
        state = ConfigurationFormState()

        assert state.page_name is None
        assert state.survey_data_name is None
        assert isinstance(state.columns, SurveyColumnSelections)

    def test_columns_is_survey_column_selections(self):
        """Test that columns attribute is SurveyColumnSelections instance."""
        state = ConfigurationFormState()

        assert isinstance(state.columns, SurveyColumnSelections)
        assert state.columns.survey_key is None


class TestRenderPageNameInput:
    """Test render_page_name_input function."""

    @patch("datasure.utils.config_utils.st")
    def test_renders_text_input(self, mock_st):
        """Test that text input is rendered with correct parameters."""
        mock_st.text_input.return_value = "Test Page"

        result = render_page_name_input()

        mock_st.text_input.assert_called_once_with(
            "Page Name",
            placeholder="eg. Household HFC, Individual HFC, etc.",
            help="This name will be used to create a new page for the checks.",
        )
        assert result == "Test Page"

    @patch("datasure.utils.config_utils.st")
    def test_returns_none_when_empty(self, mock_st):
        """Test that None is returned when input is empty."""
        mock_st.text_input.return_value = None

        result = render_page_name_input()

        assert result is None


class TestRenderSurveyDatasetSelector:
    """Test render_survey_dataset_selector function."""

    @patch("datasure.utils.config_utils.st")
    def test_renders_selectbox_sorted(self, mock_st):
        """Test that selectbox is rendered with sorted options."""
        mock_st.selectbox.return_value = "survey_1"
        alias_list = ["z_survey", "a_survey", "m_survey"]

        result = render_survey_dataset_selector(alias_list)

        mock_st.selectbox.assert_called_once_with(
            "Select Survey Dataset",
            options=["a_survey", "m_survey", "z_survey"],
            index=None,
            help="Select the survey dataset to check.",
        )
        assert result == "survey_1"

    @patch("datasure.utils.config_utils.st")
    def test_returns_none_when_no_selection(self, mock_st):
        """Test that None is returned when no selection made."""
        mock_st.selectbox.return_value = None

        result = render_survey_dataset_selector(["survey_1"])

        assert result is None


class TestRenderSurveyColumnSelectors:
    """Test render_survey_column_selectors function."""

    @patch("datasure.utils.config_utils.st")
    def test_renders_all_selectors(self, mock_st):
        """Test that all column selectors are rendered."""
        mock_st.container.return_value.__enter__ = Mock()
        mock_st.container.return_value.__exit__ = Mock()
        mock_st.selectbox.side_effect = ["key_col", "id_col", "date_col", "enum_col"]

        datetime_cols = ["date1", "date2"]
        categorical_cols = ["col1", "col2"]

        result = render_survey_column_selectors(datetime_cols, categorical_cols)

        assert mock_st.container.called
        assert mock_st.subheader.called
        assert mock_st.selectbox.call_count == 4
        assert isinstance(result, SurveyColumnSelections)
        assert result.survey_key == "key_col"
        assert result.survey_id == "id_col"
        assert result.survey_date == "date_col"
        assert result.enumerator == "enum_col"

    @patch("datasure.utils.config_utils.st")
    def test_handles_none_columns(self, mock_st):
        """Test handling of None column lists."""
        mock_st.container.return_value.__enter__ = Mock()
        mock_st.container.return_value.__exit__ = Mock()
        mock_st.selectbox.side_effect = [None, None, None, None]

        result = render_survey_column_selectors(None, None)

        assert mock_st.selectbox.call_count == 4
        assert isinstance(result, SurveyColumnSelections)


class TestRenderBackcheckDatasetSelector:
    """Test render_backcheck_dataset_selector function."""

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.DatasetService")
    def test_renders_selectbox_with_exclusions(self, mock_service_class, mock_st):
        """Test that backcheck selector excludes survey dataset."""
        mock_service = Mock()
        mock_service.get_available_aliases_excluding.return_value = [
            "backcheck_1",
            "tracking_1",
        ]
        mock_service_class.return_value = mock_service

        mock_st.selectbox.return_value = "backcheck_1"

        all_aliases = ["survey_1", "backcheck_1", "tracking_1"]
        result = render_backcheck_dataset_selector(all_aliases, "survey_1")

        mock_service.get_available_aliases_excluding.assert_called_once_with(
            all_aliases, ["survey_1"]
        )
        assert result == "backcheck_1"

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.DatasetService")
    def test_returns_none_when_no_selection(self, mock_service_class, mock_st):
        """Test that None is returned when no selection made."""
        mock_service = Mock()
        mock_service.get_available_aliases_excluding.return_value = ["backcheck_1"]
        mock_service_class.return_value = mock_service

        mock_st.selectbox.return_value = None

        result = render_backcheck_dataset_selector(
            ["survey_1", "backcheck_1"], "survey_1"
        )

        assert result is None


class TestRenderBackcheckColumnSelectors:
    """Test render_backcheck_column_selectors function."""

    @patch("datasure.utils.config_utils.st")
    def test_renders_all_selectors(self, mock_st):
        """Test that all backcheck column selectors are rendered."""
        mock_st.container.return_value.__enter__ = Mock()
        mock_st.container.return_value.__exit__ = Mock()
        mock_st.selectbox.side_effect = ["bc_date_col", "bc_checker_col"]

        datetime_cols = ["date1", "date2"]
        categorical_cols = ["col1", "col2"]

        result = render_backcheck_column_selectors(datetime_cols, categorical_cols)

        assert mock_st.container.called
        assert mock_st.subheader.called
        assert mock_st.selectbox.call_count == 2
        assert isinstance(result, BackcheckColumnSelectors)
        assert result.backcheck_date == "bc_date_col"
        assert result.backchecker == "bc_checker_col"

    @patch("datasure.utils.config_utils.st")
    def test_handles_none_columns(self, mock_st):
        """Test handling of None column lists."""
        mock_st.container.return_value.__enter__ = Mock()
        mock_st.container.return_value.__exit__ = Mock()
        mock_st.selectbox.side_effect = [None, None]

        result = render_backcheck_column_selectors(None, None)

        assert mock_st.selectbox.call_count == 2
        assert isinstance(result, BackcheckColumnSelectors)


class TestHandleConfigurationSubmission:
    """Test _handle_configuration_submission function."""

    @patch("datasure.utils.config_utils.st")
    def test_successful_submission(self, mock_st):
        """Test successful configuration submission."""
        mock_service = Mock()
        mock_service.validate_configuration.return_value = (
            True,
            None,
            CheckConfiguration(
                page_name="Test",
                survey_data_name="survey_1",
                survey_key="key",
                survey_id="id",
                survey_date=None,
                enumerator=None,
                backcheck_data_name="backcheck_1",
                backcheck_date=None,
                backchecker=None,
            ),
        )
        mock_service.add_configuration.return_value = True

        column_selections = {
            "survey_key": "key",
            "survey_id": "id",
            "survey_date": "date",
            "enumerator": "enum",
            "backcheck_date": "bc_date",
            "backchecker": "bc_checker",
        }

        _handle_configuration_submission(
            config_service=mock_service,
            column_selections=column_selections,
            page_name="Test",
            survey_data_name="survey_1",
            backcheck_data_name="backcheck_1",
        )

        mock_service.validate_configuration.assert_called_once()
        mock_service.add_configuration.assert_called_once()
        mock_st.success.assert_called_once()

    @patch("datasure.utils.config_utils.st")
    def test_validation_failure(self, mock_st):
        """Test handling of validation failure."""
        mock_service = Mock()
        mock_service.validate_configuration.return_value = (
            False,
            "Validation error message",
            None,
        )

        _handle_configuration_submission(
            config_service=mock_service,
            column_selections={},
            page_name="Test",
            survey_data_name="survey_1",
            backcheck_data_name=None,
        )

        mock_service.add_configuration.assert_not_called()
        mock_st.error.assert_called_once_with("Validation error message")

    @patch("datasure.utils.config_utils.st")
    def test_add_configuration_failure(self, mock_st):
        """Test handling of add configuration failure."""
        mock_service = Mock()
        mock_service.validate_configuration.return_value = (
            True,
            None,
            CheckConfiguration(
                page_name="Test",
                survey_data_name="survey_1",
                survey_key="key",
                survey_id="id",
                survey_date=None,
                enumerator=None,
                backcheck_data_name="backcheck_1",
                backcheck_date=None,
                backchecker=None,
            ),
        )
        mock_service.add_configuration.return_value = False

        _handle_configuration_submission(
            config_service=mock_service,
            column_selections={"survey_key": "key"},
            page_name="Test",
            survey_data_name="survey_1",
            backcheck_data_name=None,
        )

        mock_st.error.assert_called_once_with(
            "Failed to add configuration. Please try again."
        )


class TestAddCheckConfigurationForm:
    """Test add_check_configuration_form function."""

    @patch("datasure.utils.config_utils.render_page_name_input")
    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    @patch("datasure.utils.config_utils.DatasetService")
    def test_early_return_when_no_page_name(
        self, mock_dataset_service, mock_config_service, mock_st, mock_render_page_name
    ):
        """Test that form returns early when no page name entered."""
        mock_st.popover.return_value.__enter__ = Mock()
        mock_st.popover.return_value.__exit__ = Mock()
        mock_render_page_name.return_value = None

        add_check_configuration_form("project_id", ["survey_1"])

        mock_st.info.assert_called_once_with("Enter a page name to continue")

    @patch("datasure.utils.config_utils.render_page_name_input")
    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    @patch("datasure.utils.config_utils.DatasetService")
    def test_shows_error_when_page_name_exists(
        self, mock_dataset_service, mock_config_service, mock_st, mock_render_page_name
    ):
        """Test that error is shown when page name already exists."""
        mock_st.popover.return_value.__enter__ = Mock()
        mock_st.popover.return_value.__exit__ = Mock()
        mock_render_page_name.return_value = "Existing"

        mock_service = Mock()
        mock_service.validate_configuration.return_value = (
            False,
            "Page name 'Existing' already exists. Please choose a different name.",
            None,
        )
        mock_config_service.return_value = mock_service

        add_check_configuration_form("project_id", ["survey_1"])

        mock_st.error.assert_called()


class TestRemoveCheckConfigurationForm:
    """Test remove_check_configuration_form function."""

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_shows_info_when_no_configurations(self, mock_service_class, mock_st):
        """Test that info message is shown when no configurations exist."""
        mock_st.popover.return_value.__enter__ = Mock()
        mock_st.popover.return_value.__exit__ = Mock()

        mock_service = Mock()
        mock_service.get_page_names.return_value = []
        mock_service_class.return_value = mock_service

        remove_check_configuration_form("project_id")

        mock_st.info.assert_called_once_with(
            "No check configurations found. Please add a check configuration."
        )

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_renders_selectbox_with_sorted_names(self, mock_service_class, mock_st):
        """Test that selectbox is rendered with sorted page names."""
        mock_st.popover.return_value.__enter__ = Mock()
        mock_st.popover.return_value.__exit__ = Mock()
        mock_st.selectbox.return_value = None
        mock_st.button.return_value = False

        mock_service = Mock()
        mock_service.get_page_names.return_value = ["Z Page", "A Page", "M Page"]
        mock_service_class.return_value = mock_service

        remove_check_configuration_form("project_id")

        mock_st.selectbox.assert_called_once()
        call_args = mock_st.selectbox.call_args
        assert call_args[1]["options"] == ["A Page", "M Page", "Z Page"]

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_removes_configuration_on_button_click(self, mock_service_class, mock_st):
        """Test that configuration is removed when button clicked."""
        mock_st.popover.return_value.__enter__ = Mock()
        mock_st.popover.return_value.__exit__ = Mock()
        mock_st.selectbox.return_value = "Test Page"
        mock_st.button.return_value = True

        mock_service = Mock()
        mock_service.get_page_names.return_value = ["Test Page"]
        mock_service.remove_configuration.return_value = True
        mock_service_class.return_value = mock_service

        remove_check_configuration_form("project_id")

        mock_service.remove_configuration.assert_called_once_with("Test Page")
        mock_st.success.assert_called_once()

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_shows_error_on_removal_failure(self, mock_service_class, mock_st):
        """Test that error is shown when removal fails."""
        mock_st.popover.return_value.__enter__ = Mock()
        mock_st.popover.return_value.__exit__ = Mock()
        mock_st.selectbox.return_value = "Test Page"
        mock_st.button.return_value = True

        mock_service = Mock()
        mock_service.get_page_names.return_value = ["Test Page"]
        mock_service.remove_configuration.return_value = False
        mock_service_class.return_value = mock_service

        remove_check_configuration_form("project_id")

        mock_st.error.assert_called_once_with(
            "Failed to remove configuration. Please try again."
        )


class TestRenderConfigurationTable:
    """Test render_configuration_table function."""

    @patch("datasure.utils.config_utils.st")
    def test_renders_dataframe_with_config(self, mock_st):
        """Test that dataframe is rendered with correct configuration."""
        mock_df = pl.DataFrame([{"page_name": "Test", "survey_key": "key"}])

        render_configuration_table(mock_df)

        mock_st.dataframe.assert_called_once()
        call_args = mock_st.dataframe.call_args

        assert call_args[0][0].equals(mock_df)
        assert call_args[1]["width"] == "stretch"
        assert call_args[1]["hide_index"] is True
        assert call_args[1]["key"] == "check_config_log"
        assert "column_config" in call_args[1]
        assert "page_name" in call_args[1]["column_config"]
