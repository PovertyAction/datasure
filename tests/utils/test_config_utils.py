"""Comprehensive tests for configuration utilities module."""

from unittest.mock import MagicMock, Mock, mock_open, patch

import pandas as pd
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
    _get_index_or_none,
    _handle_configuration_submission,
    _handle_edit_configuration_submission,
    add_check_configuration_form,
    edit_check_configuration_form,
    remove_check_configuration_form,
    render_backcheck_column_selectors,
    render_backcheck_column_selectors_edit,
    render_backcheck_dataset_selector,
    render_configuration_table,
    render_page_name_input,
    render_survey_column_selectors,
    render_survey_column_selectors_edit,
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
                page_name=None,
                survey_data_name="survey_data",
                survey_key="key_column",
                survey_id="id",
                survey_date=None,
                enumerator=None,
                backcheck_data_name="backcheck",
                backcheck_date=None,
                backchecker=None,
            )
        errors = exc_info.value.errors()
        assert any("page_name" in str(e.get("loc")) for e in errors)

    def test_missing_required_survey_data_name(self):
        """Test that missing survey_data_name raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CheckConfiguration(
                page_name="Test",
                survey_data_name=None,
                survey_key="key_column",
                survey_id="id",
                survey_date=None,
                enumerator=None,
                backcheck_data_name="backcheck",
                backcheck_date=None,
                backchecker=None,
            )
        errors = exc_info.value.errors()
        assert any("survey_data_name" in str(e.get("loc")) for e in errors)

    def test_missing_required_survey_key(self):
        """Test that missing survey_key raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CheckConfiguration(
                page_name="Test",
                survey_data_name="survey",
                survey_key=None,
                survey_id="id",
                survey_date=None,
                enumerator=None,
                backcheck_data_name="backcheck",
                backcheck_date=None,
                backchecker=None,
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

    def test_survey_target_validation_negative(self):
        """Test that negative survey_target raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CheckConfiguration(
                page_name="Test",
                survey_data_name="survey",
                survey_key="key",
                survey_id="id",
                survey_target=-1,
                backcheck_data_name="backcheck",
            )
        errors = exc_info.value.errors()
        assert any("survey_target" in str(e.get("loc")) for e in errors)

    def test_survey_target_validation_zero(self):
        """Test that zero survey_target is valid."""
        config = CheckConfiguration(
            page_name="Test",
            survey_data_name="survey",
            survey_key="key",
            survey_id="id",
            survey_target=0,
            survey_date=None,
            enumerator=None,
            backcheck_data_name="backcheck",
            backcheck_date=None,
            backchecker=None,
        )
        assert config.survey_target == 0

    def test_survey_target_validation_positive(self):
        """Test that positive survey_target is valid."""
        config = CheckConfiguration(
            page_name="Test",
            survey_data_name="survey",
            survey_key="key",
            survey_id="id",
            survey_target=1000,
            survey_date=None,
            enumerator=None,
            backcheck_data_name="backcheck",
            backcheck_date=None,
            backchecker=None,
        )
        assert config.survey_target == 1000

    def test_backcheck_target_percent_validation_negative(self):
        """Test that negative backcheck_target_percent raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CheckConfiguration(
                page_name="Test",
                survey_data_name="survey",
                survey_key="key",
                survey_id="id",
                backcheck_data_name="backcheck",
                backcheck_target_percent=-1,
            )
        errors = exc_info.value.errors()
        assert any("backcheck_target_percent" in str(e.get("loc")) for e in errors)

    def test_backcheck_target_percent_validation_over_100(self):
        """Test that backcheck_target_percent over 100 raises error."""
        with pytest.raises(ValidationError) as exc_info:
            CheckConfiguration(
                page_name="Test",
                survey_data_name="survey",
                survey_key="key",
                survey_id="id",
                backcheck_data_name="backcheck",
                backcheck_target_percent=101,
            )
        errors = exc_info.value.errors()
        assert any("backcheck_target_percent" in str(e.get("loc")) for e in errors)

    def test_backcheck_target_percent_validation_zero(self):
        """Test that zero backcheck_target_percent is valid."""
        config = CheckConfiguration(
            page_name="Test",
            survey_data_name="survey",
            survey_key="key",
            survey_id="id",
            backcheck_target_percent=0,
            survey_date=None,
            enumerator=None,
            backcheck_data_name="backcheck",
            backcheck_date=None,
            backchecker=None,
        )
        assert config.backcheck_target_percent == 0

    def test_backcheck_target_percent_validation_hundred(self):
        """Test that 100 backcheck_target_percent is valid."""
        config = CheckConfiguration(
            page_name="Test",
            survey_data_name="survey",
            survey_key="key",
            survey_id="id",
            backcheck_target_percent=100,
            survey_date=None,
            enumerator=None,
            backcheck_data_name="backcheck",
            backcheck_date=None,
            backchecker=None,
        )
        assert config.backcheck_target_percent == 100

    def test_all_optional_fields(self):
        """Test configuration with all optional fields set."""
        config = CheckConfiguration(
            page_name="Test",
            survey_data_name="survey",
            survey_key="key",
            survey_id="id",
            survey_date="date",
            enumerator="enum",
            team="team1",
            formversion="v1",
            duration="30",
            survey_target=100,
            backcheck_data_name="backcheck",
            backcheck_date="bc_date",
            backchecker="bc_checker",
            backchecker_team="bc_team",
            backcheck_target_percent=10,
            tracking_data_name="tracking",
        )
        assert config.team == "team1"
        assert config.formversion == "v1"
        assert config.duration == "30"
        assert config.backchecker_team == "bc_team"

    def test_empty_optional_string_fields(self):
        """Test that empty strings in optional fields raise validation errors."""
        with pytest.raises(ValidationError):
            CheckConfiguration(
                page_name="Test",
                survey_data_name="survey",
                survey_key="key",
                survey_id="id",
                team="",  # Empty string should fail min_length=1
                backcheck_data_name="backcheck",
            )


class TestSurveyColumnSelections:
    """Test SurveyColumnSelections model."""

    def test_all_fields_none_by_default(self):
        """Test that survey_key is required and others can be None."""
        # Survey_key is required, so we need to provide it
        selections = SurveyColumnSelections(survey_key=None)
        assert selections.survey_key is None
        assert selections.survey_id is None
        assert selections.survey_date is None
        assert selections.enumerator is None
        assert selections.team is None
        assert selections.formversion is None
        assert selections.duration is None
        assert selections.survey_target is None

    def test_set_all_fields(self):
        """Test setting all fields."""
        selections = SurveyColumnSelections(
            survey_key="key",
            survey_id="id",
            survey_date="date",
            enumerator="enum",
            team="team1",
            formversion="v1",
            duration="30",
            survey_target=100,
        )
        assert selections.survey_key == "key"
        assert selections.survey_id == "id"
        assert selections.survey_date == "date"
        assert selections.enumerator == "enum"
        assert selections.team == "team1"
        assert selections.formversion == "v1"
        assert selections.duration == "30"
        assert selections.survey_target == 100

    def test_survey_target_validation_negative(self):
        """Test that negative survey_target raises error."""
        with pytest.raises(ValidationError) as exc_info:
            SurveyColumnSelections(
                survey_key="key",
                survey_target=-1,
            )
        errors = exc_info.value.errors()
        assert any("survey_target" in str(e.get("loc")) for e in errors)

    def test_survey_target_validation_zero(self):
        """Test that zero survey_target is valid."""
        selections = SurveyColumnSelections(
            survey_key="key",
            survey_target=0,
        )
        assert selections.survey_target == 0

    def test_empty_string_fields(self):
        """Test that empty strings raise validation errors."""
        with pytest.raises(ValidationError):
            SurveyColumnSelections(
                survey_key="",  # Empty string should fail min_length=1
            )


class TestBackcheckColumnSelectors:
    """Test BackcheckColumnSelectors model."""

    def test_all_fields_none_by_default(self):
        """Test that all fields are None by default."""
        selections = BackcheckColumnSelectors()
        assert selections.backcheck_date is None
        assert selections.backchecker is None
        assert selections.backchecker_team is None
        assert selections.backcheck_target_percent is None

    def test_set_all_fields(self):
        """Test setting all fields."""
        selections = BackcheckColumnSelectors(
            backcheck_date="bc_date",
            backchecker="bc_checker",
            backchecker_team="bc_team",
            backcheck_target_percent=10,
        )
        assert selections.backcheck_date == "bc_date"
        assert selections.backchecker == "bc_checker"
        assert selections.backchecker_team == "bc_team"
        assert selections.backcheck_target_percent == 10

    def test_backcheck_target_percent_validation_negative(self):
        """Test that negative backcheck_target_percent raises error."""
        with pytest.raises(ValidationError) as exc_info:
            BackcheckColumnSelectors(
                backcheck_target_percent=-1,
            )
        errors = exc_info.value.errors()
        assert any("backcheck_target_percent" in str(e.get("loc")) for e in errors)

    def test_backcheck_target_percent_validation_over_100(self):
        """Test that backcheck_target_percent over 100 raises error."""
        with pytest.raises(ValidationError) as exc_info:
            BackcheckColumnSelectors(
                backcheck_target_percent=101,
            )
        errors = exc_info.value.errors()
        assert any("backcheck_target_percent" in str(e.get("loc")) for e in errors)

    def test_backcheck_target_percent_validation_zero(self):
        """Test that zero backcheck_target_percent is valid."""
        selections = BackcheckColumnSelectors(
            backcheck_target_percent=0,
        )
        assert selections.backcheck_target_percent == 0

    def test_backcheck_target_percent_validation_hundred(self):
        """Test that 100 backcheck_target_percent is valid."""
        selections = BackcheckColumnSelectors(
            backcheck_target_percent=100,
        )
        assert selections.backcheck_target_percent == 100

    def test_empty_string_fields(self):
        """Test that empty strings raise validation errors."""
        with pytest.raises(ValidationError):
            BackcheckColumnSelectors(
                backcheck_date="",  # Empty string should fail min_length=1
            )


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
                    "team": "team1",
                    "formversion": "v1",
                    "duration": "30",
                    "survey_target": 100,
                    "backcheck_data_name": "backcheck",
                    "backcheck_date": "bc_date",
                    "backchecker": "bc_checker",
                    "backchecker_team": "bc_team",
                    "backcheck_target_percent": 10,
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
                    "team": None,
                    "formversion": None,
                    "duration": None,
                    "survey_target": None,
                    "backcheck_data_name": "backcheck_1",
                    "backcheck_date": None,
                    "backchecker": None,
                    "backchecker_team": None,
                    "backcheck_target_percent": None,
                    "tracking_data_name": None,
                },
                {
                    "page_name": "Page Two",
                    "survey_data_name": "survey_2",
                    "survey_key": "key2",
                    "survey_id": "id2",
                    "survey_date": None,
                    "enumerator": None,
                    "team": None,
                    "formversion": None,
                    "duration": None,
                    "survey_target": None,
                    "backcheck_data_name": "backcheck_2",
                    "backcheck_date": None,
                    "backchecker": None,
                    "backchecker_team": None,
                    "backcheck_target_percent": None,
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
            "survey_key": None,  # Required field set to None
            "survey_id": None,
            "survey_date": None,
            "enumerator": None,
            "backcheck_data_name": None,
            "backcheck_date": None,
            "backchecker": None,
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

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.duckdb_save_table")
    @patch.object(ConfigurationService, "_add_page_file")
    def test_add_configuration_existing_log(
        self, mock_add_page_file, mock_save_table, mock_st, mock_config_df
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
            team=None,
            formversion=None,
            duration=None,
            survey_target=None,
            backcheck_data_name="backcheck_2",
            backcheck_date=None,
            backchecker=None,
            backchecker_team=None,
            backcheck_target_percent=None,
            tracking_data_name=None,
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
        mock_remove_page_file.assert_called_once_with(2)
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

    def test_get_page_configuration_empty_log(self, mock_empty_df):
        """Test getting page configuration from empty log returns empty dict."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_empty_df)

        result = service.get_page_configuration(0)

        assert result == {}

    def test_get_page_configuration_valid_index(self, mock_config_df):
        """Test getting page configuration with valid row index."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_config_df)

        result = service.get_page_configuration(0)

        assert isinstance(result, dict)
        assert result["page_name"] == "Existing Page"
        assert result["survey_data_name"] == "survey_1"
        assert result["survey_key"] == "key"
        assert result["survey_id"] == "id"
        assert result["survey_date"] == "date"
        assert result["enumerator"] == "enum"
        assert result["survey_target"] == 100
        assert result["backcheck_data_name"] == "backcheck"
        assert result["backcheck_date"] == "bc_date"
        assert result["backchecker"] == "bc_checker"
        assert result["backcheck_target_percent"] == 10
        assert result["tracking_data_name"] == "tracking"

    def test_get_page_configuration_index_out_of_range(self, mock_config_df):
        """Test getting page configuration with out of range index."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_config_df)

        result = service.get_page_configuration(999)

        assert result == {}

    def test_get_page_configuration_multiple_pages(self, mock_multi_config_df):
        """Test getting page configuration from multiple configurations."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_multi_config_df)

        # Get first page
        result_first = service.get_page_configuration(0)
        assert result_first["page_name"] == "Page One"
        assert result_first["survey_data_name"] == "survey_1"
        assert result_first["survey_key"] == "key1"

        # Get second page
        result_second = service.get_page_configuration(1)
        assert result_second["page_name"] == "Page Two"
        assert result_second["survey_data_name"] == "survey_2"
        assert result_second["survey_key"] == "key2"

    def test_get_page_configuration_negative_index(self, mock_config_df):
        """Test getting page configuration with negative index."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=mock_config_df)

        # Polars .row() method supports negative indexing like Python lists
        # -1 should return the last row
        result = service.get_page_configuration(-1)

        assert isinstance(result, dict)
        assert result["page_name"] == "Existing Page"
        assert result["survey_data_name"] == "survey_1"


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
    @patch("datasure.utils.config_utils.get_df_columns")
    def test_get_dataset_columns(self, mock_get_df_columns, mock_get_table):
        """Test getting categorized columns from a dataset."""
        # Mock the dataframe
        mock_df = Mock()
        mock_get_table.return_value = mock_df

        # Mock get_df_columns return value (returns an object with attributes)
        mock_column_info = Mock()
        mock_column_info.datetime_columns = ["date1"]
        mock_column_info.numeric_columns = ["num1", "num2", "num3"]
        mock_column_info.categorical_columns = ["col1", "col2"]
        mock_get_df_columns.return_value = mock_column_info

        service = DatasetService("test_project")
        # Function returns 3 values: datetime_cols, numeric_cols, categorical_cols
        datetime_cols, numeric_cols, categorical_cols = service.get_dataset_columns(
            "survey_1"
        )

        mock_get_table.assert_called_once_with(
            project_id="test_project",
            alias="survey_1",
            db_name="prep",
            type="pd",
        )
        mock_get_df_columns.assert_called_once_with(mock_df)

        assert datetime_cols == ["date1"]
        assert numeric_cols == ["num1", "num2", "num3"]
        assert categorical_cols == ["col1", "col2"]

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
        """Test form state initialization raises error due to required survey_key."""
        # ConfigurationFormState tries to instantiate SurveyColumnSelections without
        # required survey_key parameter, which will raise ValidationError
        with pytest.raises(ValidationError):
            ConfigurationFormState()

    def test_columns_is_survey_column_selections(self):
        """Test that SurveyColumnSelections requires survey_key parameter."""
        # This test verifies the Pydantic model requirement
        with pytest.raises(ValidationError):
            SurveyColumnSelections()

        # But works with survey_key provided
        selections = SurveyColumnSelections(survey_key=None)
        assert isinstance(selections, SurveyColumnSelections)
        assert selections.survey_key is None


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
            max_chars=20,
            key="check_config_page_name_input",
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

    @pytest.mark.skip(reason="st.fragment decorator cannot be easily mocked in tests")
    @patch("datasure.utils.config_utils.st")
    def test_renders_all_selectors(self, mock_st):
        """Test that all column selectors are rendered."""
        mock_st.container.return_value.__enter__ = Mock()
        mock_st.container.return_value.__exit__ = Mock()
        # 7 selectboxes + 1 number_input for survey_target
        mock_st.selectbox.side_effect = [
            "key_col",
            "id_col",
            "date_col",
            "enum_col",
            "team_col",
            "formversion_col",
            "duration_col",
        ]
        mock_st.number_input.return_value = 100

        datetime_cols = ["date1", "date2"]
        numeric_cols = ["num1", "num2"]
        categorical_cols = ["col1", "col2"]

        result = render_survey_column_selectors(
            datetime_cols, numeric_cols, categorical_cols
        )

        assert mock_st.container.called
        assert mock_st.subheader.called
        assert mock_st.selectbox.call_count == 7
        assert mock_st.number_input.call_count == 1
        assert isinstance(result, SurveyColumnSelections)
        assert result.survey_key == "key_col"
        assert result.survey_id == "id_col"
        assert result.survey_date == "date_col"
        assert result.enumerator == "enum_col"
        assert result.survey_target == 100

    @pytest.mark.skip(reason="st.fragment decorator cannot be easily mocked in tests")
    @patch("datasure.utils.config_utils.st")
    def test_handles_none_columns(self, mock_st):
        """Test handling of None column lists."""
        mock_st.container.return_value.__enter__ = Mock()
        mock_st.container.return_value.__exit__ = Mock()
        mock_st.selectbox.side_effect = [None, None, None, None, None, None, None]
        mock_st.number_input.return_value = 0

        result = render_survey_column_selectors(None, None, None)

        assert mock_st.selectbox.call_count == 7
        assert mock_st.number_input.call_count == 1
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

    @pytest.mark.skip(reason="st.fragment decorator cannot be easily mocked in tests")
    @patch("datasure.utils.config_utils.st")
    def test_renders_all_selectors(self, mock_st):
        """Test that all backcheck column selectors are rendered."""
        mock_st.container.return_value.__enter__ = Mock()
        mock_st.container.return_value.__exit__ = Mock()
        # 3 selectboxes + 1 number_input for backcheck_target_percent
        mock_st.selectbox.side_effect = [
            "bc_date_col",
            "bc_checker_col",
            "bc_team_col",
        ]
        mock_st.number_input.return_value = 10

        datetime_cols = ["date1", "date2"]
        categorical_cols = ["col1", "col2"]

        result = render_backcheck_column_selectors(datetime_cols, categorical_cols)

        assert mock_st.container.called
        assert mock_st.subheader.called
        assert mock_st.selectbox.call_count == 3
        assert mock_st.number_input.call_count == 1
        assert isinstance(result, BackcheckColumnSelectors)
        assert result.backcheck_date == "bc_date_col"
        assert result.backchecker == "bc_checker_col"
        assert result.backchecker_team == "bc_team_col"
        assert result.backcheck_target_percent == 10

    @pytest.mark.skip(reason="st.fragment decorator cannot be easily mocked in tests")
    @patch("datasure.utils.config_utils.st")
    def test_handles_none_columns(self, mock_st):
        """Test handling of None column lists."""
        mock_st.container.return_value.__enter__ = Mock()
        mock_st.container.return_value.__exit__ = Mock()
        mock_st.selectbox.side_effect = [None, None, None]
        mock_st.number_input.return_value = 0

        result = render_backcheck_column_selectors(None, None)

        assert mock_st.selectbox.call_count == 3
        assert mock_st.number_input.call_count == 1
        assert isinstance(result, BackcheckColumnSelectors)


class TestHandleConfigurationSubmission:
    """Test _handle_configuration_submission function."""

    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.st")
    def test_successful_submission(self, mock_st, mock_dataset_service_class):
        """Test successful configuration submission."""
        mock_dataset_service = Mock()
        mock_dataset_service.validate_key_column.return_value = (True, None)
        mock_dataset_service_class.return_value = mock_dataset_service

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
            project_id="test_project",
        )

        mock_service.validate_configuration.assert_called_once()
        mock_service.add_configuration.assert_called_once()
        mock_st.success.assert_called_once()

    @patch("datasure.utils.config_utils.st")
    def test_validation_failure(self, mock_st):
        """Test handling of validation failure when no survey key."""
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
            project_id="test_project",
        )

        mock_service.add_configuration.assert_not_called()
        mock_st.error.assert_called_once_with("Validation error message")

    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.st")
    def test_add_configuration_failure(self, mock_st, mock_dataset_service_class):
        """Test handling of add configuration failure."""
        mock_dataset_service = Mock()
        mock_dataset_service.validate_key_column.return_value = (True, None)
        mock_dataset_service_class.return_value = mock_dataset_service

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
            project_id="test_project",
        )

        mock_st.error.assert_called_once_with(
            "Failed to add configuration. Please try again."
        )

    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.st")
    def test_invalid_key_column_stops_submission(
        self, mock_st, mock_dataset_service_class
    ):
        """Test that an invalid key column shows error and stops submission."""
        mock_dataset_service = Mock()
        mock_dataset_service.validate_key_column.return_value = (
            False,
            "Key column 'key' has 2 missing value(s).",
        )
        mock_dataset_service_class.return_value = mock_dataset_service

        mock_service = Mock()

        _handle_configuration_submission(
            config_service=mock_service,
            column_selections={"survey_key": "key"},
            page_name="Test",
            survey_data_name="survey_1",
            backcheck_data_name=None,
            project_id="test_project",
        )

        mock_st.error.assert_called_once_with(
            "Key column 'key' has 2 missing value(s)."
        )
        mock_service.validate_configuration.assert_not_called()

    @patch("datasure.utils.config_utils.st")
    def test_no_survey_key_skips_key_validation(self, mock_st):
        """Test that missing survey_key skips DatasetService validation."""
        mock_service = Mock()
        mock_service.validate_configuration.return_value = (True, None, Mock())
        mock_service.add_configuration.return_value = True

        _handle_configuration_submission(
            config_service=mock_service,
            column_selections={"survey_id": "id"},
            page_name="Test",
            survey_data_name="survey_1",
            backcheck_data_name=None,
            project_id="test_project",
        )

        # validate_configuration still called; no DatasetService interaction
        mock_service.validate_configuration.assert_called_once()


class TestAddCheckConfigurationForm:
    """Test add_check_configuration_form function."""

    @pytest.mark.skip(reason="st.dialog decorator cannot be easily mocked in tests")
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

    @pytest.mark.skip(reason="st.dialog decorator cannot be easily mocked in tests")
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


# ============================================================================
# _get_index_or_none TESTS
# ============================================================================


class TestGetIndexOrNone:
    """Test _get_index_or_none utility function."""

    def test_returns_correct_index_when_found(self):
        """Test returns 0-based index when value is in options."""
        assert _get_index_or_none("b", ["a", "b", "c"]) == 1

    def test_returns_zero_for_first_item(self):
        assert _get_index_or_none("a", ["a", "b", "c"]) == 0

    def test_returns_last_index(self):
        assert _get_index_or_none("c", ["a", "b", "c"]) == 2

    def test_returns_none_when_value_not_in_options(self):
        assert _get_index_or_none("z", ["a", "b", "c"]) is None

    def test_returns_none_when_value_is_none(self):
        assert _get_index_or_none(None, ["a", "b", "c"]) is None

    def test_returns_none_for_empty_options(self):
        assert _get_index_or_none("a", []) is None

    def test_returns_none_for_empty_string_value(self):
        """Empty string is falsy so returns None."""
        assert _get_index_or_none("", ["a", "b"]) is None


# ============================================================================
# ConfigurationService — new method tests
# ============================================================================


def _make_single_config_df() -> pl.DataFrame:
    """Return a minimal single-row configuration DataFrame."""
    return pl.DataFrame(
        [
            {
                "page_name": "Existing Page",
                "survey_data_name": "survey_1",
                "survey_key": "key",
                "survey_id": "id",
                "survey_date": None,
                "enumerator": None,
                "team": None,
                "formversion": None,
                "duration": None,
                "survey_target": None,
                "backcheck_data_name": None,
                "backcheck_date": None,
                "backchecker": None,
                "backchecker_team": None,
                "backcheck_target_percent": None,
                "tracking_data_name": None,
            }
        ]
    )


def _make_multi_config_df() -> pl.DataFrame:
    """Return a two-row configuration DataFrame."""
    row = {
        "survey_date": None,
        "enumerator": None,
        "team": None,
        "formversion": None,
        "duration": None,
        "survey_target": None,
        "backcheck_data_name": None,
        "backcheck_date": None,
        "backchecker": None,
        "backchecker_team": None,
        "backcheck_target_percent": None,
        "tracking_data_name": None,
    }
    return pl.DataFrame(
        [
            {
                "page_name": "Page One",
                "survey_data_name": "survey_1",
                "survey_key": "key1",
                "survey_id": "id1",
                **row,
            },
            {
                "page_name": "Page Two",
                "survey_data_name": "survey_2",
                "survey_key": "key2",
                "survey_id": "id2",
                **row,
            },
        ]
    )


class TestConfigurationServiceGetConfigurationByPageName:
    """Test ConfigurationService.get_configuration_by_page_name."""

    def test_returns_empty_dict_when_log_is_empty(self):
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=pl.DataFrame())
        assert service.get_configuration_by_page_name("Any Page") == {}

    def test_returns_config_for_matching_page(self):
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=_make_single_config_df())
        result = service.get_configuration_by_page_name("Existing Page")
        assert isinstance(result, dict)
        assert result["page_name"] == "Existing Page"
        assert result["survey_data_name"] == "survey_1"

    def test_returns_empty_dict_for_nonexistent_page(self):
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=_make_single_config_df())
        assert service.get_configuration_by_page_name("Nonexistent") == {}

    def test_returns_correct_row_from_multi_row_df(self):
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=_make_multi_config_df())
        result = service.get_configuration_by_page_name("Page Two")
        assert result["page_name"] == "Page Two"
        assert result["survey_data_name"] == "survey_2"
        assert result["survey_key"] == "key2"

    def test_is_case_sensitive(self):
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=_make_single_config_df())
        assert service.get_configuration_by_page_name("existing page") == {}


class TestConfigurationServiceValidateEditConfiguration:
    """Test ConfigurationService.validate_edit_configuration."""

    def test_valid_when_page_name_unchanged(self):
        """Keeping the same page name as original should not raise duplicate error."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=_make_single_config_df())

        config_data = {
            "page_name": "Existing Page",
            "survey_data_name": "survey_1",
            "survey_key": "key",
            "survey_id": "id",
            "survey_date": None,
            "enumerator": None,
            "backcheck_data_name": None,
            "backcheck_date": None,
            "backchecker": None,
        }

        is_valid, error_msg, config = service.validate_edit_configuration(
            config_data, "Existing Page"
        )

        assert is_valid is True
        assert error_msg is None
        assert config is not None
        assert config.page_name == "Existing Page"

    def test_valid_when_new_page_name_is_unique(self):
        """Renaming to a page name that doesn't exist should be valid."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=_make_single_config_df())

        config_data = {
            "page_name": "Brand New Page",
            "survey_data_name": "survey_1",
            "survey_key": "key",
            "survey_id": "id",
            "survey_date": None,
            "enumerator": None,
            "backcheck_data_name": None,
            "backcheck_date": None,
            "backchecker": None,
        }

        is_valid, error_msg, config = service.validate_edit_configuration(
            config_data, "Existing Page"
        )

        assert is_valid is True
        assert error_msg is None
        assert config.page_name == "Brand New Page"

    def test_invalid_when_new_name_clashes_with_other_page(self):
        """Renaming to an already-used page name should fail."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=_make_multi_config_df())

        config_data = {
            "page_name": "Page Two",  # already exists
            "survey_data_name": "survey_1",
            "survey_key": "key1",
            "survey_id": "id1",
            "survey_date": None,
            "enumerator": None,
            "backcheck_data_name": None,
            "backcheck_date": None,
            "backchecker": None,
        }

        is_valid, error_msg, config = service.validate_edit_configuration(
            config_data, "Page One"
        )

        assert is_valid is False
        assert "already exists" in error_msg
        assert config is None

    def test_invalid_when_config_data_fails_pydantic_validation(self):
        """Invalid config data (e.g. empty page name) should fail."""
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=pl.DataFrame())

        config_data = {
            "page_name": "",  # fails min_length validation
            "survey_data_name": "survey_1",
            "survey_key": "key",
            "survey_id": "id",
            "survey_date": None,
            "enumerator": None,
            "backcheck_data_name": None,
            "backcheck_date": None,
            "backchecker": None,
        }

        is_valid, error_msg, config = service.validate_edit_configuration(
            config_data, "Any Page"
        )

        assert is_valid is False
        assert error_msg is not None
        assert config is None


class TestConfigurationServiceUpdateConfiguration:
    """Test ConfigurationService.update_configuration."""

    @pytest.fixture
    def new_config(self):
        return CheckConfiguration(
            page_name="Updated Page",
            survey_data_name="survey_1",
            survey_key="key1",
            survey_id="id1",
            survey_date=None,
            enumerator=None,
            team=None,
            formversion=None,
            duration=None,
            survey_target=None,
            backcheck_data_name=None,
            backcheck_date=None,
            backchecker=None,
            backchecker_team=None,
            backcheck_target_percent=None,
            tracking_data_name=None,
        )

    def test_returns_false_when_log_is_empty(self, new_config):
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=pl.DataFrame())
        assert service.update_configuration("Page One", new_config) is False

    def test_returns_false_when_page_name_not_found(self, new_config):
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=_make_single_config_df())
        assert service.update_configuration("Nonexistent Page", new_config) is False

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.duckdb_save_table")
    def test_updates_single_row_successfully(self, mock_save, mock_st, new_config):
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=_make_single_config_df())

        result = service.update_configuration("Existing Page", new_config)

        assert result is True
        mock_save.assert_called_once()
        saved_df = mock_save.call_args[0][1]
        assert len(saved_df) == 1
        assert saved_df["page_name"][0] == "Updated Page"

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.duckdb_save_table")
    def test_updates_first_row_and_preserves_rest(self, mock_save, mock_st, new_config):
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=_make_multi_config_df())

        result = service.update_configuration("Page One", new_config)

        assert result is True
        saved_df = mock_save.call_args[0][1]
        assert len(saved_df) == 2
        assert saved_df["page_name"][0] == "Updated Page"
        assert saved_df["page_name"][1] == "Page Two"

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.duckdb_save_table")
    def test_updates_last_row_and_preserves_rest(self, mock_save, mock_st):
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=_make_multi_config_df())

        updated = CheckConfiguration(
            page_name="Updated Page Two",
            survey_data_name="survey_2",
            survey_key="key2",
            survey_id="id2",
            survey_date=None,
            enumerator=None,
            team=None,
            formversion=None,
            duration=None,
            survey_target=None,
            backcheck_data_name=None,
            backcheck_date=None,
            backchecker=None,
            backchecker_team=None,
            backcheck_target_percent=None,
            tracking_data_name=None,
        )

        result = service.update_configuration("Page Two", updated)

        assert result is True
        saved_df = mock_save.call_args[0][1]
        assert len(saved_df) == 2
        assert saved_df["page_name"][0] == "Page One"
        assert saved_df["page_name"][1] == "Updated Page Two"

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.duckdb_save_table")
    def test_calls_st_rerun_on_success(self, mock_save, mock_st, new_config):
        service = ConfigurationService("test_project")
        service.get_all_configurations = Mock(return_value=_make_single_config_df())

        service.update_configuration("Existing Page", new_config)

        mock_st.rerun.assert_called_once()

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.duckdb_save_table")
    def test_saves_with_correct_project_id_and_alias(
        self, mock_save, mock_st, new_config
    ):
        service = ConfigurationService("my_project")
        service.get_all_configurations = Mock(return_value=_make_single_config_df())

        service.update_configuration("Existing Page", new_config)

        call_args = mock_save.call_args
        assert call_args[0][0] == "my_project"
        assert call_args[1]["alias"] == "check_config"
        assert call_args[1]["db_name"] == "logs"


# ============================================================================
# DatasetService.validate_key_column TESTS
# ============================================================================


class TestDatasetServiceValidateKeyColumn:
    """Test DatasetService.validate_key_column."""

    @patch("datasure.utils.config_utils.duckdb_get_table")
    def test_valid_key_column(self, mock_get_table):
        """Unique, non-null column passes validation."""
        mock_df = pd.DataFrame({"key_col": ["a", "b", "c", "d"]})
        mock_get_table.return_value = mock_df

        service = DatasetService("test_project")
        is_valid, error = service.validate_key_column("survey_1", "key_col")

        assert is_valid is True
        assert error is None

    @patch("datasure.utils.config_utils.duckdb_get_table")
    def test_invalid_when_column_has_nulls(self, mock_get_table):
        """Column with missing values fails validation."""
        mock_df = pd.DataFrame({"key_col": ["a", None, "c", "d"]})
        mock_get_table.return_value = mock_df

        service = DatasetService("test_project")
        is_valid, error = service.validate_key_column("survey_1", "key_col")

        assert is_valid is False
        assert "missing value" in error
        assert "key_col" in error
        assert "1" in error  # 1 null

    @patch("datasure.utils.config_utils.duckdb_get_table")
    def test_invalid_when_column_has_duplicates(self, mock_get_table):
        """Column with duplicate values fails validation."""
        mock_df = pd.DataFrame({"key_col": ["a", "b", "a", "d"]})
        mock_get_table.return_value = mock_df

        service = DatasetService("test_project")
        is_valid, error = service.validate_key_column("survey_1", "key_col")

        assert is_valid is False
        assert "duplicate value" in error
        assert "key_col" in error
        assert "1" in error  # 1 duplicate

    @patch("datasure.utils.config_utils.duckdb_get_table")
    def test_invalid_when_multiple_nulls(self, mock_get_table):
        """Reports the correct null count in the error message."""
        mock_df = pd.DataFrame({"key_col": [None, None, "c"]})
        mock_get_table.return_value = mock_df

        service = DatasetService("test_project")
        is_valid, error = service.validate_key_column("survey_1", "key_col")

        assert is_valid is False
        assert "2" in error

    @patch("datasure.utils.config_utils.duckdb_get_table")
    def test_calls_duckdb_with_correct_args(self, mock_get_table):
        """Verifies duckdb_get_table is called with expected parameters."""
        mock_df = pd.DataFrame({"key_col": ["a", "b"]})
        mock_get_table.return_value = mock_df

        service = DatasetService("proj_123")
        service.validate_key_column("my_survey", "key_col")

        mock_get_table.assert_called_once_with(
            project_id="proj_123",
            alias="my_survey",
            db_name="prep",
            type="pd",
        )


# ============================================================================
# _handle_edit_configuration_submission TESTS
# ============================================================================


class TestHandleEditConfigurationSubmission:
    """Test _handle_edit_configuration_submission function."""

    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.st")
    def test_successful_update(self, mock_st, mock_dataset_service_class):
        """Full happy path: key valid, config valid, update succeeds."""
        mock_ds = Mock()
        mock_ds.validate_key_column.return_value = (True, None)
        mock_dataset_service_class.return_value = mock_ds

        mock_service = Mock()
        mock_service.validate_edit_configuration.return_value = (
            True,
            None,
            CheckConfiguration(
                page_name="Test",
                survey_data_name="survey_1",
                survey_key="key",
                survey_id="id",
                survey_date=None,
                enumerator=None,
                backcheck_data_name=None,
                backcheck_date=None,
                backchecker=None,
            ),
        )
        mock_service.update_configuration.return_value = True

        _handle_edit_configuration_submission(
            config_service=mock_service,
            original_page_name="Old Name",
            column_selections={"survey_key": "key"},
            page_name="Test",
            survey_data_name="survey_1",
            backcheck_data_name=None,
            project_id="test_project",
        )

        mock_service.validate_edit_configuration.assert_called_once()
        mock_service.update_configuration.assert_called_once_with(
            "Old Name", mock_service.validate_edit_configuration.return_value[2]
        )
        mock_st.success.assert_called_once()

    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.st")
    def test_stops_when_key_column_invalid(self, mock_st, mock_dataset_service_class):
        """An invalid key column shows an error and stops processing."""
        mock_ds = Mock()
        mock_ds.validate_key_column.return_value = (
            False,
            "Key column 'key' has 3 duplicate value(s).",
        )
        mock_dataset_service_class.return_value = mock_ds

        mock_service = Mock()

        _handle_edit_configuration_submission(
            config_service=mock_service,
            original_page_name="Old Name",
            column_selections={"survey_key": "key"},
            page_name="Test",
            survey_data_name="survey_1",
            backcheck_data_name=None,
            project_id="test_project",
        )

        mock_st.error.assert_called_once_with(
            "Key column 'key' has 3 duplicate value(s)."
        )
        mock_service.validate_edit_configuration.assert_not_called()

    @patch("datasure.utils.config_utils.st")
    def test_stops_when_edit_validation_fails(self, mock_st):
        """Failed config validation shows error and skips update."""
        mock_service = Mock()
        mock_service.validate_edit_configuration.return_value = (
            False,
            "Page name 'Test' already exists.",
            None,
        )

        _handle_edit_configuration_submission(
            config_service=mock_service,
            original_page_name="Old Name",
            column_selections={},
            page_name="Test",
            survey_data_name="survey_1",
            backcheck_data_name=None,
            project_id="test_project",
        )

        mock_service.update_configuration.assert_not_called()
        mock_st.error.assert_called_once_with("Page name 'Test' already exists.")

    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.st")
    def test_shows_error_when_update_fails(self, mock_st, mock_dataset_service_class):
        """A failed update shows an appropriate error message."""
        mock_ds = Mock()
        mock_ds.validate_key_column.return_value = (True, None)
        mock_dataset_service_class.return_value = mock_ds

        mock_service = Mock()
        mock_service.validate_edit_configuration.return_value = (
            True,
            None,
            CheckConfiguration(
                page_name="Test",
                survey_data_name="survey_1",
                survey_key="key",
                survey_id="id",
                survey_date=None,
                enumerator=None,
                backcheck_data_name=None,
                backcheck_date=None,
                backchecker=None,
            ),
        )
        mock_service.update_configuration.return_value = False

        _handle_edit_configuration_submission(
            config_service=mock_service,
            original_page_name="Old Name",
            column_selections={"survey_key": "key"},
            page_name="Test",
            survey_data_name="survey_1",
            backcheck_data_name=None,
            project_id="test_project",
        )

        mock_st.error.assert_called_once_with(
            "Failed to update configuration. Please try again."
        )

    @patch("datasure.utils.config_utils.st")
    def test_no_survey_key_skips_key_validation(self, mock_st):
        """When no survey_key is present, DatasetService is not invoked."""
        mock_service = Mock()
        mock_service.validate_edit_configuration.return_value = (True, None, Mock())
        mock_service.update_configuration.return_value = True

        _handle_edit_configuration_submission(
            config_service=mock_service,
            original_page_name="Old Name",
            column_selections={"survey_id": "id"},
            page_name="Test",
            survey_data_name="survey_1",
            backcheck_data_name=None,
            project_id="test_project",
        )

        mock_service.validate_edit_configuration.assert_called_once()

    @patch("datasure.utils.config_utils.st")
    def test_builds_config_data_from_column_selections(self, mock_st):
        """Config data passed to validate_edit_configuration includes all selections."""
        mock_service = Mock()
        mock_service.validate_edit_configuration.return_value = (False, "err", None)

        _handle_edit_configuration_submission(
            config_service=mock_service,
            original_page_name="Old Name",
            column_selections={
                "survey_id": "id_col",
                "survey_date": "date_col",
                "enumerator": "enum_col",
                "backcheck_date": "bc_date_col",
            },
            page_name="New Name",
            survey_data_name="survey_1",
            backcheck_data_name="bc_1",
            project_id="test_project",
        )

        call_kwargs = mock_service.validate_edit_configuration.call_args
        config_data = call_kwargs[0][0]
        assert config_data["page_name"] == "New Name"
        assert config_data["survey_data_name"] == "survey_1"
        assert config_data["backcheck_data_name"] == "bc_1"
        assert config_data["survey_id"] == "id_col"
        assert config_data["survey_date"] == "date_col"
        assert config_data["enumerator"] == "enum_col"
        original_passed = call_kwargs[0][1]
        assert original_passed == "Old Name"


# ============================================================================
# @st.fragment function tests (called via __wrapped__ to bypass decorator)
# ============================================================================


def _make_mock_st_for_fragment():
    """Return a mock streamlit with container context manager support."""
    mock_st = MagicMock()
    mock_container = MagicMock()
    mock_container.__enter__ = Mock(return_value=mock_container)
    mock_container.__exit__ = Mock(return_value=False)
    mock_st.container.return_value = mock_container
    mock_st.selectbox.return_value = None
    mock_st.number_input.return_value = 0
    return mock_st


class TestRenderSurveyColumnSelectorsWrapped:
    """Test render_survey_column_selectors inner body via __wrapped__."""

    @patch("datasure.utils.config_utils.st")
    def test_returns_survey_column_selections_instance(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = None
        mock_st.number_input.return_value = 0

        result = render_survey_column_selectors.__wrapped__(
            datetime_columns=["date1"],
            numeric_columns=["num1"],
            categorical_columns=["col1"],
        )

        assert isinstance(result, SurveyColumnSelections)

    @patch("datasure.utils.config_utils.st")
    def test_renders_all_selectboxes_and_number_input(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = None
        mock_st.number_input.return_value = 0

        render_survey_column_selectors.__wrapped__(
            datetime_columns=["date1"],
            numeric_columns=["num1"],
            categorical_columns=["col1"],
        )

        assert mock_st.selectbox.call_count == 7
        assert mock_st.number_input.call_count == 1
        mock_st.subheader.assert_called_once_with("Select survey data columns")

    @patch("datasure.utils.config_utils.st")
    def test_populates_selections_from_st_return_values(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.side_effect = [
            "key_col",
            "id_col",
            "date_col",
            "enum_col",
            "team_col",
            "ver_col",
            "dur_col",
        ]
        mock_st.number_input.return_value = 50

        result = render_survey_column_selectors.__wrapped__(
            datetime_columns=["date_col"],
            numeric_columns=["ver_col", "dur_col"],
            categorical_columns=["key_col", "id_col", "enum_col", "team_col"],
        )

        assert result.survey_key == "key_col"
        assert result.survey_id == "id_col"
        assert result.survey_date == "date_col"
        assert result.enumerator == "enum_col"
        assert result.survey_target == 50

    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.st")
    def test_validates_key_column_when_provided(self, mock_st, mock_ds_class):
        """Calls DatasetService.validate_key_column when key and context are present."""
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.side_effect = ["key_col", None, None, None, None, None, None]
        mock_st.number_input.return_value = 0

        mock_ds = Mock()
        mock_ds.validate_key_column.return_value = (False, "Key has duplicates")
        mock_ds_class.return_value = mock_ds

        render_survey_column_selectors.__wrapped__(
            datetime_columns=[],
            numeric_columns=[],
            categorical_columns=["key_col"],
            project_id="proj",
            dataset_alias="survey_1",
        )

        mock_ds.validate_key_column.assert_called_once_with("survey_1", "key_col")
        mock_st.error.assert_called_once_with("Key has duplicates")

    @patch("datasure.utils.config_utils.st")
    def test_handles_none_column_lists(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = None
        mock_st.number_input.return_value = 0

        result = render_survey_column_selectors.__wrapped__(
            datetime_columns=None,
            numeric_columns=None,
            categorical_columns=None,
        )

        assert isinstance(result, SurveyColumnSelections)


class TestRenderBackcheckColumnSelectorsWrapped:
    """Test render_backcheck_column_selectors inner body via __wrapped__."""

    @patch("datasure.utils.config_utils.st")
    def test_returns_backcheck_column_selectors_instance(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = None
        mock_st.number_input.return_value = 0

        result = render_backcheck_column_selectors.__wrapped__(
            datetime_columns=["date1"],
            categorical_columns=["col1"],
        )

        assert isinstance(result, BackcheckColumnSelectors)

    @patch("datasure.utils.config_utils.st")
    def test_renders_three_selectboxes_and_number_input(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = None
        mock_st.number_input.return_value = 0

        render_backcheck_column_selectors.__wrapped__(
            datetime_columns=["date1"],
            categorical_columns=["col1"],
        )

        assert mock_st.selectbox.call_count == 3
        assert mock_st.number_input.call_count == 1
        mock_st.subheader.assert_called_once_with("Select backcheck data columns")

    @patch("datasure.utils.config_utils.st")
    def test_populates_fields_from_st_return_values(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.side_effect = ["bc_date", "bc_checker", "bc_team"]
        mock_st.number_input.return_value = 20

        result = render_backcheck_column_selectors.__wrapped__(
            datetime_columns=["bc_date"],
            categorical_columns=["bc_checker", "bc_team"],
        )

        assert result.backcheck_date == "bc_date"
        assert result.backchecker == "bc_checker"
        assert result.backchecker_team == "bc_team"
        assert result.backcheck_target_percent == 20


class TestRenderSurveyColumnSelectorsEditWrapped:
    """Test render_survey_column_selectors_edit inner body via __wrapped__."""

    @patch("datasure.utils.config_utils.st")
    def test_returns_survey_column_selections_instance(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = None
        mock_st.number_input.return_value = 0

        result = render_survey_column_selectors_edit.__wrapped__(
            datetime_columns=["date1"],
            numeric_columns=["num1"],
            categorical_columns=["col1"],
        )

        assert isinstance(result, SurveyColumnSelections)

    @patch("datasure.utils.config_utils.st")
    def test_renders_all_selectboxes_and_number_input(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = None
        mock_st.number_input.return_value = 0

        render_survey_column_selectors_edit.__wrapped__(
            datetime_columns=["date1"],
            numeric_columns=["num1"],
            categorical_columns=["col1"],
        )

        assert mock_st.selectbox.call_count == 7
        assert mock_st.number_input.call_count == 1

    @patch("datasure.utils.config_utils.st")
    def test_uses_defaults_for_index_selection(self, mock_st):
        """Verifies _get_index_or_none is used for pre-population."""
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = "col1"
        mock_st.number_input.return_value = 10

        defaults = {"survey_key": "col1", "survey_target": 10}
        render_survey_column_selectors_edit.__wrapped__(
            datetime_columns=[],
            numeric_columns=[],
            categorical_columns=["col1"],
            defaults=defaults,
        )

        # First selectbox call should use index=0 (col1 is at index 0)
        first_call_kwargs = mock_st.selectbox.call_args_list[0][1]
        assert first_call_kwargs["index"] == 0

    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.st")
    def test_validates_key_column_when_provided(self, mock_st, mock_ds_class):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.side_effect = ["key_col", None, None, None, None, None, None]
        mock_st.number_input.return_value = 0

        mock_ds = Mock()
        mock_ds.validate_key_column.return_value = (False, "Duplicate keys")
        mock_ds_class.return_value = mock_ds

        render_survey_column_selectors_edit.__wrapped__(
            datetime_columns=[],
            numeric_columns=[],
            categorical_columns=["key_col"],
            project_id="proj",
            dataset_alias="survey_1",
        )

        mock_ds.validate_key_column.assert_called_once_with("survey_1", "key_col")
        mock_st.error.assert_called_once_with("Duplicate keys")

    @patch("datasure.utils.config_utils.st")
    def test_handles_none_defaults_and_columns(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = None
        mock_st.number_input.return_value = 0

        result = render_survey_column_selectors_edit.__wrapped__(
            datetime_columns=None,
            numeric_columns=None,
            categorical_columns=None,
            defaults=None,
        )

        assert isinstance(result, SurveyColumnSelections)


class TestRenderBackcheckColumnSelectorsEditWrapped:
    """Test render_backcheck_column_selectors_edit inner body via __wrapped__."""

    @patch("datasure.utils.config_utils.st")
    def test_returns_backcheck_column_selectors_instance(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = None
        mock_st.number_input.return_value = 0

        result = render_backcheck_column_selectors_edit.__wrapped__(
            datetime_columns=["date1"],
            categorical_columns=["col1"],
        )

        assert isinstance(result, BackcheckColumnSelectors)

    @patch("datasure.utils.config_utils.st")
    def test_renders_three_selectboxes_and_number_input(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = None
        mock_st.number_input.return_value = 0

        render_backcheck_column_selectors_edit.__wrapped__(
            datetime_columns=["date1"],
            categorical_columns=["col1"],
        )

        assert mock_st.selectbox.call_count == 3
        assert mock_st.number_input.call_count == 1

    @patch("datasure.utils.config_utils.st")
    def test_uses_defaults_for_pre_population(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = "bc_date"
        mock_st.number_input.return_value = 15

        defaults = {"backcheck_date": "bc_date", "backcheck_target_percent": 15}
        render_backcheck_column_selectors_edit.__wrapped__(
            datetime_columns=["bc_date"],
            categorical_columns=[],
            defaults=defaults,
        )

        first_call_kwargs = mock_st.selectbox.call_args_list[0][1]
        assert first_call_kwargs["index"] == 0  # bc_date is at index 0

    @patch("datasure.utils.config_utils.st")
    def test_handles_none_columns_and_defaults(self, mock_st):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.return_value = None
        mock_st.number_input.return_value = 0

        result = render_backcheck_column_selectors_edit.__wrapped__(
            datetime_columns=None,
            categorical_columns=None,
            defaults=None,
        )

        assert isinstance(result, BackcheckColumnSelectors)


# ============================================================================
# @st.dialog function tests (called via __wrapped__ to bypass decorator)
# ============================================================================


class TestAddCheckConfigurationFormWrapped:
    """Test add_check_configuration_form inner body via __wrapped__."""

    @patch("datasure.utils.config_utils.render_page_name_input")
    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    @patch("datasure.utils.config_utils.DatasetService")
    def test_shows_info_when_no_page_name(
        self, mock_ds_class, mock_cs_class, mock_st, mock_render_name
    ):
        """Early return with info when page name is empty."""
        mock_render_name.return_value = ""

        add_check_configuration_form.__wrapped__("project_id", ["survey_1"])

        mock_st.info.assert_called_once_with("Enter a page name to continue")

    @patch("datasure.utils.config_utils.render_page_name_input")
    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_shows_error_when_page_name_already_exists(
        self, mock_cs_class, mock_st, mock_render_name
    ):
        """Shows duplicate-page-name error and returns early."""
        mock_render_name.return_value = "Existing Page"

        mock_service = Mock()
        mock_service.validate_configuration.return_value = (
            False,
            "Page name 'Existing Page' already exists. Please choose a different name.",
            None,
        )
        mock_cs_class.return_value = mock_service

        add_check_configuration_form.__wrapped__("project_id", ["survey_1"])

        mock_st.error.assert_called_once()
        error_msg = mock_st.error.call_args[0][0]
        assert "already exists" in error_msg

    @patch("datasure.utils.config_utils.render_page_name_input")
    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_returns_early_when_no_survey_dataset_selected(
        self, mock_cs_class, mock_st, mock_render_name
    ):
        """Returns early when no survey dataset is chosen."""
        mock_render_name.return_value = "New Page"
        mock_st.selectbox.return_value = None  # No dataset selected

        mock_service = Mock()
        mock_service.validate_configuration.return_value = (True, None, Mock())
        mock_cs_class.return_value = mock_service

        add_check_configuration_form.__wrapped__("project_id", ["survey_1"])

        # DatasetService.get_dataset_columns should not be called
        mock_st.button.assert_not_called()

    @patch("datasure.utils.config_utils._handle_configuration_submission")
    @patch("datasure.utils.config_utils.render_backcheck_column_selectors")
    @patch("datasure.utils.config_utils.render_survey_column_selectors")
    @patch("datasure.utils.config_utils.render_backcheck_dataset_selector")
    @patch("datasure.utils.config_utils.render_survey_dataset_selector")
    @patch("datasure.utils.config_utils.render_page_name_input")
    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_calls_handle_submission_when_add_button_clicked(
        self,
        mock_cs_class,
        mock_ds_class,
        mock_st,
        mock_render_name,
        mock_render_survey_selector,
        mock_render_backcheck_selector,
        mock_render_survey_cols,
        mock_render_backcheck_cols,
        mock_handle_submission,
    ):
        """Calls _handle_configuration_submission when add button is clicked."""
        mock_render_name.return_value = "New Page"

        mock_service = Mock()
        mock_service.validate_configuration.return_value = (True, None, Mock())
        mock_cs_class.return_value = mock_service

        mock_ds = Mock()
        mock_ds.get_dataset_columns.return_value = ([], [], [])
        mock_ds_class.return_value = mock_ds

        mock_render_survey_selector.return_value = "survey_1"
        mock_render_backcheck_selector.return_value = None

        survey_cols = SurveyColumnSelections(survey_key="key")
        mock_render_survey_cols.return_value = survey_cols
        mock_st.button.return_value = True  # Add button clicked

        add_check_configuration_form.__wrapped__("project_id", ["survey_1"])

        mock_handle_submission.assert_called_once()


class TestEditCheckConfigurationFormWrapped:
    """Test edit_check_configuration_form inner body via __wrapped__."""

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_shows_info_when_no_configurations_exist(self, mock_cs_class, mock_st):
        """Shows info and returns early when no pages exist."""
        mock_service = Mock()
        mock_service.get_page_names.return_value = []
        mock_cs_class.return_value = mock_service

        edit_check_configuration_form.__wrapped__("project_id", ["survey_1"])

        mock_st.info.assert_called_once()
        info_msg = mock_st.info.call_args[0][0]
        assert "No check configurations found" in info_msg

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_shows_info_when_no_page_selected(self, mock_cs_class, mock_st):
        """Shows select-prompt info when selectbox returns None."""
        mock_service = Mock()
        mock_service.get_page_names.return_value = ["Page One"]
        mock_cs_class.return_value = mock_service
        mock_st.selectbox.return_value = None

        edit_check_configuration_form.__wrapped__("project_id", ["survey_1"])

        info_calls = [c[0][0] for c in mock_st.info.call_args_list]
        assert any("Select a configuration to edit" in msg for msg in info_calls)

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_shows_error_when_config_load_fails(self, mock_cs_class, mock_st):
        """Shows error when get_configuration_by_page_name returns empty dict."""
        mock_service = Mock()
        mock_service.get_page_names.return_value = ["Page One"]
        mock_service.get_configuration_by_page_name.return_value = {}
        mock_cs_class.return_value = mock_service
        mock_st.selectbox.return_value = "Page One"

        edit_check_configuration_form.__wrapped__("project_id", ["survey_1"])

        mock_st.error.assert_called_once()
        assert "Could not load configuration" in mock_st.error.call_args[0][0]

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_returns_early_when_page_name_cleared(self, mock_cs_class, mock_st):
        """Returns early when user clears the page-name text input."""
        mock_service = Mock()
        mock_service.get_page_names.return_value = ["Page One"]
        mock_service.get_configuration_by_page_name.return_value = {
            "page_name": "Page One",
            "survey_data_name": "survey_1",
        }
        mock_cs_class.return_value = mock_service
        # First selectbox → page selection; text_input → empty
        mock_st.selectbox.return_value = "Page One"
        mock_st.text_input.return_value = ""

        edit_check_configuration_form.__wrapped__("project_id", ["survey_1"])

        info_calls = [c[0][0] for c in mock_st.info.call_args_list]
        assert any("Enter a page name to continue" in msg for msg in info_calls)

    @patch("datasure.utils.config_utils._handle_edit_configuration_submission")
    @patch("datasure.utils.config_utils.render_backcheck_column_selectors_edit")
    @patch("datasure.utils.config_utils.render_survey_column_selectors_edit")
    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_calls_handle_edit_submission_when_save_clicked(
        self,
        mock_cs_class,
        mock_ds_class,
        mock_st,
        mock_render_survey_edit,
        mock_render_bc_edit,
        mock_handle,
    ):
        """Calls _handle_edit_configuration_submission when save button clicked."""
        mock_service = Mock()
        mock_service.get_page_names.return_value = ["Page One"]
        mock_service.get_configuration_by_page_name.return_value = {
            "page_name": "Page One",
            "survey_data_name": "survey_1",
            "backcheck_data_name": None,
        }
        mock_cs_class.return_value = mock_service

        mock_ds = Mock()
        mock_ds.get_dataset_columns.return_value = ([], [], [])
        mock_ds.get_available_aliases_excluding.return_value = []
        mock_ds_class.return_value = mock_ds

        # selectbox calls: page_select, survey_dataset, backcheck_dataset
        mock_st.selectbox.side_effect = ["Page One", "survey_1", None]
        mock_st.text_input.return_value = "Page One"
        mock_st.button.return_value = True  # Save clicked
        mock_st.divider = Mock()

        survey_cols = SurveyColumnSelections(survey_key="key")
        mock_render_survey_edit.return_value = survey_cols

        edit_check_configuration_form.__wrapped__("project_id", ["survey_1"])

        mock_handle.assert_called_once()

    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_returns_early_when_no_survey_dataset_selected(
        self, mock_cs_class, mock_ds_class, mock_st
    ):
        """Returns early when the survey dataset selectbox returns None."""
        mock_service = Mock()
        mock_service.get_page_names.return_value = ["Page One"]
        mock_service.get_configuration_by_page_name.return_value = {
            "page_name": "Page One",
            "survey_data_name": "survey_1",
            "backcheck_data_name": None,
        }
        mock_cs_class.return_value = mock_service

        mock_ds = Mock()
        mock_ds_class.return_value = mock_ds

        mock_st.selectbox.side_effect = [
            "Page One",
            None,
        ]  # page selected, dataset None
        mock_st.text_input.return_value = "Page One"
        mock_st.divider = Mock()

        edit_check_configuration_form.__wrapped__("project_id", ["survey_1"])

        mock_ds.get_dataset_columns.assert_not_called()

    @patch("datasure.utils.config_utils._handle_edit_configuration_submission")
    @patch("datasure.utils.config_utils.render_backcheck_column_selectors_edit")
    @patch("datasure.utils.config_utils.render_survey_column_selectors_edit")
    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_handles_backcheck_dataset_when_selected(
        self,
        mock_cs_class,
        mock_ds_class,
        mock_st,
        mock_render_survey_edit,
        mock_render_bc_edit,
        mock_handle,
    ):
        """When backcheck dataset is selected, renders backcheck column selectors."""
        mock_service = Mock()
        mock_service.get_page_names.return_value = ["Page One"]
        mock_service.get_configuration_by_page_name.return_value = {
            "page_name": "Page One",
            "survey_data_name": "survey_1",
            "backcheck_data_name": "bc_1",
        }
        mock_cs_class.return_value = mock_service

        mock_ds = Mock()
        mock_ds.get_dataset_columns.return_value = ([], [], [])
        mock_ds.get_available_aliases_excluding.return_value = ["bc_1"]
        mock_ds_class.return_value = mock_ds

        # page_select, survey_dataset, backcheck_dataset
        mock_st.selectbox.side_effect = ["Page One", "survey_1", "bc_1"]
        mock_st.text_input.return_value = "Page One"
        mock_st.button.return_value = False
        mock_st.divider = Mock()

        survey_cols = SurveyColumnSelections(survey_key="key")
        mock_render_survey_edit.return_value = survey_cols
        bc_cols = BackcheckColumnSelectors()
        mock_render_bc_edit.return_value = bc_cols

        edit_check_configuration_form.__wrapped__("project_id", ["survey_1", "bc_1"])

        mock_render_bc_edit.assert_called_once()


# ============================================================================
# Branch-coverage gap fill: remaining edge cases
# ============================================================================


class TestRenderSurveyColumnSelectorsValidKeyBranch:
    """Cover the 'key is valid' branch inside render_survey_column_selectors."""

    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.st")
    def test_no_error_shown_when_key_is_valid(self, mock_st, mock_ds_class):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.side_effect = ["key_col", None, None, None, None, None, None]
        mock_st.number_input.return_value = 0

        mock_ds = Mock()
        mock_ds.validate_key_column.return_value = (True, None)  # key IS valid
        mock_ds_class.return_value = mock_ds

        render_survey_column_selectors.__wrapped__(
            datetime_columns=[],
            numeric_columns=[],
            categorical_columns=["key_col"],
            project_id="proj",
            dataset_alias="survey_1",
        )

        mock_st.error.assert_not_called()


class TestRenderSurveyColumnSelectorsEditValidKeyBranch:
    """Cover the 'key is valid' branch inside render_survey_column_selectors_edit."""

    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.st")
    def test_no_error_shown_when_key_is_valid(self, mock_st, mock_ds_class):
        mock_container = MagicMock()
        mock_container.__enter__ = Mock(return_value=mock_container)
        mock_container.__exit__ = Mock(return_value=False)
        mock_st.container.return_value = mock_container
        mock_st.selectbox.side_effect = ["key_col", None, None, None, None, None, None]
        mock_st.number_input.return_value = 0

        mock_ds = Mock()
        mock_ds.validate_key_column.return_value = (True, None)  # key IS valid
        mock_ds_class.return_value = mock_ds

        render_survey_column_selectors_edit.__wrapped__(
            datetime_columns=[],
            numeric_columns=[],
            categorical_columns=["key_col"],
            project_id="proj",
            dataset_alias="survey_1",
        )

        mock_st.error.assert_not_called()


class TestAddCheckConfigurationFormBackcheckBranch:
    """Cover the backcheck-selected branch in add_check_configuration_form."""

    @patch("datasure.utils.config_utils._handle_configuration_submission")
    @patch("datasure.utils.config_utils.render_backcheck_column_selectors")
    @patch("datasure.utils.config_utils.render_survey_column_selectors")
    @patch("datasure.utils.config_utils.render_backcheck_dataset_selector")
    @patch("datasure.utils.config_utils.render_survey_dataset_selector")
    @patch("datasure.utils.config_utils.render_page_name_input")
    @patch("datasure.utils.config_utils.st")
    @patch("datasure.utils.config_utils.DatasetService")
    @patch("datasure.utils.config_utils.ConfigurationService")
    def test_renders_backcheck_selectors_when_dataset_selected(
        self,
        mock_cs_class,
        mock_ds_class,
        mock_st,
        mock_render_name,
        mock_render_survey_selector,
        mock_render_backcheck_selector,
        mock_render_survey_cols,
        mock_render_bc_cols,
        mock_handle,
    ):
        mock_render_name.return_value = "New Page"

        mock_service = Mock()
        mock_service.validate_configuration.return_value = (True, None, Mock())
        mock_cs_class.return_value = mock_service

        mock_ds = Mock()
        mock_ds.get_dataset_columns.return_value = ([], [], [])
        mock_ds_class.return_value = mock_ds

        mock_render_survey_selector.return_value = "survey_1"
        mock_render_backcheck_selector.return_value = "bc_1"  # backcheck selected

        survey_cols = SurveyColumnSelections(survey_key="key")
        mock_render_survey_cols.return_value = survey_cols
        bc_cols = BackcheckColumnSelectors()
        mock_render_bc_cols.return_value = bc_cols

        mock_st.button.return_value = False  # Add button not clicked

        add_check_configuration_form.__wrapped__("project_id", ["survey_1", "bc_1"])

        mock_render_bc_cols.assert_called_once()


class TestHandleSubmissionNoneConfigBranch:
    """Cover the 'validated_config is None when is_valid is True' edge branches."""

    @patch("datasure.utils.config_utils.st")
    def test_does_not_call_add_when_config_is_none(self, mock_st):
        """When validate returns (True, None, None), add_configuration is not called."""
        mock_service = Mock()
        mock_service.validate_configuration.return_value = (True, None, None)

        _handle_configuration_submission(
            config_service=mock_service,
            column_selections={},
            page_name="Test",
            survey_data_name="survey_1",
            backcheck_data_name=None,
            project_id="test_project",
        )

        mock_service.add_configuration.assert_not_called()

    @patch("datasure.utils.config_utils.st")
    def test_edit_does_not_call_update_when_config_is_none(self, mock_st):
        """When validate_edit returns (True, None, None), update is not called."""
        mock_service = Mock()
        mock_service.validate_edit_configuration.return_value = (True, None, None)

        _handle_edit_configuration_submission(
            config_service=mock_service,
            original_page_name="Old Name",
            column_selections={},
            page_name="Test",
            survey_data_name="survey_1",
            backcheck_data_name=None,
            project_id="test_project",
        )

        mock_service.update_configuration.assert_not_called()
