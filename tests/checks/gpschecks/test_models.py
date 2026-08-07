import pytest
from pydantic import ValidationError

from datasure.models.enums import DelimiterType, GPSFormatType
from datasure.models.schemas import GPSColumnConfig, GPSSettings

# =============================================================================
# Tests for Pydantic Models
# =============================================================================


def test_gps_settings_model():
    """Test GPSSettings Pydantic model creation."""
    settings = GPSSettings(
        survey_key="key_column",
        survey_id="id_column",
        survey_date="date_column",
        enumerator="enum_column",
        team="team_column",
        mapbox_custom_key="test_key_123",
    )

    assert settings.survey_key == "key_column"
    assert settings.survey_id == "id_column"
    assert settings.survey_date == "date_column"
    assert settings.enumerator == "enum_column"
    assert settings.team == "team_column"
    assert settings.mapbox_custom_key == "test_key_123"


def test_gps_settings_model_optional_fields():
    """Test GPSSettings model with optional fields."""
    settings = GPSSettings(survey_key="key_column")

    assert settings.survey_key == "key_column"
    assert settings.survey_id is None
    assert settings.survey_date is None
    assert settings.enumerator is None


def test_gps_column_config_single_column_format():
    """Test GPSColumnConfig for single column format."""
    config = GPSColumnConfig(
        alias="main_gps",
        format_type=GPSFormatType.SINGLE_COLUMN,
        delimiter=DelimiterType.SPACE,
        gps_column="gps_coords",
    )

    assert config.alias == "main_gps"
    assert config.format_type == GPSFormatType.SINGLE_COLUMN
    assert config.delimiter == DelimiterType.SPACE
    assert config.gps_column == "gps_coords"


def test_gps_column_config_separate_columns_format():
    """Test GPSColumnConfig for separate columns format."""
    config = GPSColumnConfig(
        alias="separate_gps",
        format_type=GPSFormatType.SEPARATE_COLUMNS,
        latitude_column="lat",
        longitude_column="lon",
        altitude_column="alt",
        accuracy_column="acc",
    )

    assert config.alias == "separate_gps"
    assert config.format_type == GPSFormatType.SEPARATE_COLUMNS
    assert config.latitude_column == "lat"
    assert config.longitude_column == "lon"
    assert config.altitude_column == "alt"
    assert config.accuracy_column == "acc"


def test_gps_column_config_validation_creates_valid_config():
    """Test GPSColumnConfig can be created without optional fields.

    Tests different format types with optional fields.
    """
    # Single column format allows missing latitude/longitude
    config1 = GPSColumnConfig(
        alias="test",
        format_type=GPSFormatType.SINGLE_COLUMN,
        delimiter=DelimiterType.SPACE,
        gps_column="gps_coords",
    )
    assert config1.latitude_column is None
    assert config1.longitude_column is None

    # Separate columns format allows missing altitude/accuracy
    config2 = GPSColumnConfig(
        alias="test",
        format_type=GPSFormatType.SEPARATE_COLUMNS,
        latitude_column="lat",
        longitude_column="lon",
    )
    assert config2.altitude_column is None
    assert config2.accuracy_column is None


def test_gps_column_config_empty_alias():
    """Test GPSColumnConfig validation with empty alias."""
    with pytest.raises(ValidationError) as exc_info:
        GPSColumnConfig(
            alias="",  # Empty alias should fail
            format_type=GPSFormatType.SINGLE_COLUMN,
            delimiter=DelimiterType.SPACE,
            gps_column="gps",
        )

    errors = exc_info.value.errors()
    assert any("alias" in str(e) for e in errors)
