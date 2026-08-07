"""Tests for datasure.checks.backchecks.models."""

import math

import pytest
from pydantic import ValidationError

from datasure.checks.backchecks.models import (
    TAB_NAME,
    WEEKDAY_NAMES,
    WEEKDAY_OFFSET_MAP,
    WEEKDAY_OFFSET_TO_NUMERIC,
    BackcheckSettings,
    BackcheckTestOptions,
    OkRangeOptions,
    OkRangeType,
    OkRangeValues,
    SearchType,
    StrCompareOptions,
)

# ============================================
# CONSTANTS TESTS
# ============================================


def test_constants():
    """Test that all constants are defined correctly."""
    assert TAB_NAME == "backchecks"
    assert len(WEEKDAY_NAMES) == 7
    assert len(WEEKDAY_OFFSET_MAP) == 7
    assert len(WEEKDAY_OFFSET_TO_NUMERIC) == 7
    assert WEEKDAY_OFFSET_MAP["Monday"] == "SUN"
    assert WEEKDAY_OFFSET_TO_NUMERIC["SUN"] == 0


# ============================================
# PYDANTIC MODELS TESTS
# ============================================


def test_search_type_enum():
    """Test SearchType enum values."""
    assert SearchType.EXACT.value == "exact"
    assert SearchType.STARTSWITH.value == "startswith"
    assert SearchType.ENDSWITH.value == "endswith"
    assert SearchType.CONTAINS.value == "contains"
    assert SearchType.REGEX.value == "regex"


def test_backcheck_settings_model_valid():
    """Test BackcheckSettings model with valid data."""
    settings = BackcheckSettings(
        survey_key="survey_id",
        survey_id="survey_id",
        survey_date="submission_date",
        backcheck_date="backcheck_date",
        enumerator="enumerator",
        backchecker="backchecker",
        backcheck_target_percent=10,
        drop_duplicates_option="drop",
    )
    assert settings.survey_key == "survey_id"
    assert settings.backcheck_target_percent == 10
    assert settings.drop_duplicates_option == "drop"


def test_backcheck_settings_model_defaults():
    """Test BackcheckSettings model with default values."""
    settings = BackcheckSettings(survey_key="survey_id")
    assert settings.backcheck_target_percent == 10
    assert settings.drop_duplicates_option == "drop"
    assert settings.no_differences_list is None
    assert settings.exclude_values_list is None
    assert settings.trimspaces_option is False


def test_backcheck_settings_model_optional_fields():
    """Test BackcheckSettings model with optional fields."""
    settings = BackcheckSettings(
        survey_key="survey_id",
        no_differences_list=["refuse", "dk"],
        exclude_values_list=["na"],
        case_option="lowercase",
        trimspaces_option=True,
        nosymbols_option=True,
    )
    assert settings.no_differences_list == ["refuse", "dk"]
    assert settings.exclude_values_list == ["na"]
    assert settings.case_option == "lowercase"
    assert settings.trimspaces_option is True
    assert settings.nosymbols_option is True


def test_str_compare_options_model():
    """Test StrCompareOptions model."""
    options = StrCompareOptions(
        case_option="lowercase",
        trimspaces_option=True,
        nosymbols_option=False,
    )
    assert options.case_option == "lowercase"
    assert options.trimspaces_option is True
    assert options.nosymbols_option is False


def test_str_compare_options_defaults():
    """Test StrCompareOptions model with default values."""
    options = StrCompareOptions()
    assert options.case_option is None
    assert options.trimspaces_option is False
    assert options.nosymbols_option is False


def test_ok_range_values_model_valid():
    """Test OkRangeValues model with valid values."""
    values = OkRangeValues(ok_range_neg=-5.0, ok_range_pos=5.0)
    assert math.isclose(values.ok_range_neg, -5.0)
    assert math.isclose(values.ok_range_pos, 5.0)


def test_ok_range_values_model_validation():
    """Test OkRangeValues model validation."""
    # Negative value must be <= 0
    with pytest.raises(ValidationError):
        OkRangeValues(ok_range_neg=5.0, ok_range_pos=5.0)

    # Positive value must be >= 0
    with pytest.raises(ValidationError):
        OkRangeValues(ok_range_neg=-5.0, ok_range_pos=-5.0)


def test_ok_range_options_model():
    """Test OkRangeOptions model."""
    values = OkRangeValues(ok_range_neg=-5.0, ok_range_pos=5.0)
    options = OkRangeOptions(ok_range_type="number", ok_range_values=values)
    assert options.ok_range_type == "number"
    assert options.ok_range_values.ok_range_neg == -5.0


def test_ok_range_type_enum():
    """Test OkRangeType enum."""
    assert OkRangeType.NUMBER.value == "number"
    assert OkRangeType.PERCENTAGE.value == "percentage"


def test_backcheck_test_options_model():
    """Test BackcheckTestOptions model."""
    options = BackcheckTestOptions(
        ttest=True,
        prtest=False,
        signrank=True,
        reliability=False,
    )
    assert options.ttest is True
    assert options.prtest is False
    assert options.signrank is True
    assert options.reliability is False


def test_backcheck_test_options_defaults():
    """Test BackcheckTestOptions model with defaults."""
    options = BackcheckTestOptions()
    assert options.ttest is False
    assert options.prtest is False
    assert options.signrank is False
    assert options.reliability is False
