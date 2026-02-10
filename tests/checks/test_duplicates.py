"""Tests for duplicates module.

This module tests the refactored duplicate detection system using Polars DataFrames
and Pydantic models for validation and configuration.
"""

import datetime
import json
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from pydantic import ValidationError

from datasure.checks.duplicates import (
    TAB_NAME,
    _apply_numeric_condition,
    _apply_string_condition,
    _build_filter_expression,
    _cast_col_for_date_comparison,
    _coerce_condition_value,
    _coerce_datetime_value,
    _coerce_numeric_value,
    _create_search_type_info,
    _delete_duplicates_column,
    _ensure_duplicates_column_formats,
    _filter_data_on_conditions,
    _has_date_values,
    _has_valid_filter_conditions,
    _is_date_not_datetime,
    _render_column_locking_options,
    _render_condition_value_input,
    _render_duplicates_column_actions,
    _render_duplicates_settings_table,
    _render_id_duplicates_metrics,
    _render_id_duplicates_table,
    _render_numeric_condition_input,
    _render_other_duplicates_metrics,
    _render_other_duplicates_table,
    _render_search_type_selection,
    _render_string_condition_input,
    _serialize_condition_value_for_json,
    _update_duplicates_column_config,
    _update_unlocked_duplicates_cols,
    _validate_duplicates_condition_date_value,
    compute_column_duplicates,
    compute_duplicates_statistics,
    compute_id_duplicates,
    duplicates_report,
    duplicates_report_settings,
    expand_col_names,
    load_default_duplicates_settings,
)
from datasure.models.enums import NumCondition, SearchType, StrCondition
from datasure.models.schemas import (
    DateDefaults,
    DuplicatesColumnConfig,
    DuplicatesSettings,
    DuplicatesStats,
    FilterCondition,
)

# ============================================
# FIXTURES
# ============================================


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest to disable database mocking
    for these tests.
    """
    # These tests don't use database functions in the same way
    pass


@pytest.fixture
def sample_data_pl():
    """Create sample data as Polars DataFrame."""
    return pl.DataFrame(
        {
            "survey_id": ["S001", "S002", "S003", "S004", "S005", "S002", "S004"],
            "survey_key": ["K001", "K002", "K003", "K004", "K005", "K006", "K007"],
            "survey_date": [
                datetime.date(2024, 1, 1),
                datetime.date(2024, 1, 2),
                datetime.date(2024, 1, 3),
                datetime.date(2024, 1, 4),
                datetime.date(2024, 1, 5),
                datetime.date(2024, 1, 6),
                datetime.date(2024, 1, 7),
            ],
            "enumerator": ["E1", "E1", "E2", "E2", "E3", "E1", "E2"],
            "age": [25, 30, 35, 28, 32, 30, 28],
            "income": [50000, 60000, 55000, 52000, 58000, 60000, 52000],
            "gender": ["M", "F", "M", "F", "M", "F", "F"],
        }
    )


@pytest.fixture
def duplicates_settings_file(tmp_path):
    """Create a temporary duplicates settings file."""
    settings = {
        "duplicates": {
            "survey_key": "survey_key",
            "survey_id": "survey_id",
            "survey_date": "survey_date",
            "enumerator": "enumerator",
        }
    }
    file_path = tmp_path / "duplicates_settings.json"
    file_path.write_text(json.dumps(settings))
    return str(file_path)


# ============================================
# CONSTANTS TESTS
# ============================================


def test_constants():
    """Test that all constants are defined correctly."""
    assert TAB_NAME == "duplicates"


# ============================================
# ENUMS TESTS
# ============================================


def test_search_type_enum():
    """Test SearchType enum values."""
    assert SearchType.EXACT.value == "exact"
    assert SearchType.STARTSWITH.value == "startswith"
    assert SearchType.ENDSWITH.value == "endswith"
    assert SearchType.CONTAINS.value == "contains"
    assert SearchType.REGEX.value == "regex"


def test_num_condition_enum():
    """Test NumCondition enum values."""
    assert NumCondition.EQUALS.value == "Value is equal"
    assert NumCondition.NOT_EQUALS.value == "Value is not equal"
    assert NumCondition.GREATER_THAN.value == "Value is greater than"
    assert (
        NumCondition.GREATER_THAN_OR_EQUAL.value == "Value is greater than or equal to"
    )
    assert NumCondition.LESS_THAN.value == "Value is less than"
    assert NumCondition.LESS_THAN_OR_EQUAL.value == "Value is less than or equal to"
    assert NumCondition.INCLUDES.value == "Values includes"
    assert NumCondition.EXCLUDES.value == "Value does not include"
    assert NumCondition.IN_RANGE.value == "Value is in range"


def test_str_condition_enum():
    """Test StrCondition enum values."""
    assert StrCondition.EQUALS.value == "Value is equal"
    assert StrCondition.NOT_EQUALS.value == "Value is not equal"
    assert StrCondition.STARTWITH.value == "Value starts with"
    assert StrCondition.ENDWITH.value == "Value ends with"
    assert StrCondition.CONTAINS.value == "Value contains"
    assert StrCondition.INCLUDES.value == "Values includes"
    assert StrCondition.EXCLUDES.value == "Value does not include"


# ============================================
# PYDANTIC MODELS TESTS
# ============================================


def test_duplicates_column_config_valid():
    """Test DuplicatesColumnConfig with valid data."""
    config = DuplicatesColumnConfig(
        search_type=SearchType.EXACT,
        pattern=None,
        dup_cols=["age", "income"],
        lock_cols=False,
    )
    assert config.search_type == SearchType.EXACT
    assert config.pattern is None
    assert config.dup_cols == ["age", "income"]
    assert config.lock_cols is False


def test_duplicates_column_config_pattern_required():
    """Test DuplicatesColumnConfig validation for non-exact search types."""
    # Pattern is required for non-exact search types
    with pytest.raises(ValidationError):
        DuplicatesColumnConfig(
            search_type=SearchType.STARTSWITH,
            pattern=None,
            dup_cols=["age"],
        )


def test_duplicates_column_config_empty_dup_cols():
    """Test DuplicatesColumnConfig validation for empty dup_cols."""
    with pytest.raises(ValidationError):
        DuplicatesColumnConfig(
            search_type=SearchType.EXACT,
            dup_cols=[],
        )


def test_duplicates_stats_model():
    """Test DuplicatesStats model."""
    stats = DuplicatesStats(
        number_of_columns_checked=5,
        total_duplicates=10,
        number_of_cols_with_duplicates=3,
        number_of_cols_without_duplicates=2,
    )
    assert stats.number_of_columns_checked == 5
    assert stats.total_duplicates == 10
    assert stats.number_of_cols_with_duplicates == 3
    assert stats.number_of_cols_without_duplicates == 2


def test_duplicates_stats_negative_values():
    """Test DuplicatesStats validation for negative values."""
    with pytest.raises(ValidationError):
        DuplicatesStats(
            number_of_columns_checked=-1,
            total_duplicates=10,
            number_of_cols_with_duplicates=3,
            number_of_cols_without_duplicates=2,
        )


def test_filter_condition_valid():
    """Test FilterCondition with valid data."""
    condition = FilterCondition(
        condition_col="age",
        condition_type=NumCondition.EQUALS.value,
        condition_value=25,
        missing_as_duplicates=False,
    )
    assert condition.condition_col == "age"
    assert condition.condition_type == NumCondition.EQUALS.value
    assert condition.condition_value == 25
    assert condition.missing_as_duplicates is False


def test_filter_condition_in_range_validation():
    """Test FilterCondition validation for IN_RANGE condition."""
    # IN_RANGE requires a list/tuple of 2 values
    condition = FilterCondition(
        condition_col="age",
        condition_type=NumCondition.IN_RANGE.value,
        condition_value=[20, 30],
    )
    assert condition.condition_value == [20, 30]

    # Invalid: not a list/tuple
    with pytest.raises(ValidationError):
        FilterCondition(
            condition_col="age",
            condition_type=NumCondition.IN_RANGE.value,
            condition_value=25,
        )

    # Invalid: list with wrong number of values
    with pytest.raises(ValidationError):
        FilterCondition(
            condition_col="age",
            condition_type=NumCondition.IN_RANGE.value,
            condition_value=[20],
        )


def test_filter_condition_includes_validation():
    """Test FilterCondition validation for INCLUDES condition."""
    condition = FilterCondition(
        condition_col="gender",
        condition_type=StrCondition.INCLUDES.value,
        condition_value=["M", "F"],
    )
    assert condition.condition_value == ["M", "F"]

    # Invalid: not a list/tuple/set
    with pytest.raises(ValidationError):
        FilterCondition(
            condition_col="gender",
            condition_type=StrCondition.INCLUDES.value,
            condition_value="M",
        )


def test_duplicates_settings_valid():
    """Test DuplicatesSettings with valid data."""
    settings = DuplicatesSettings(
        survey_key="survey_key",
        survey_id="survey_id",
        survey_date="survey_date",
        enumerator="enumerator",
        conditions={},
    )
    assert settings.survey_key == "survey_key"
    assert settings.survey_id == "survey_id"
    assert settings.survey_date == "survey_date"
    assert settings.enumerator == "enumerator"


def test_duplicates_settings_survey_id_required():
    """Test DuplicatesSettings validation for required survey_id."""
    # survey_id is required and must not be None or empty
    with pytest.raises(ValidationError):
        DuplicatesSettings(
            survey_id="",  # Empty string should fail validation
        )


def test_date_defaults_model():
    """Test DateDefaults model."""
    defaults = DateDefaults()
    assert defaults.start_date == datetime.date(1970, 1, 1)
    assert defaults.end_date == datetime.date(2100, 12, 31)
    assert isinstance(defaults.default_start_date, datetime.date)
    assert isinstance(defaults.default_end_date, datetime.date)


# ============================================
# SETTINGS TESTS
# ============================================


def test_load_default_duplicates_settings_valid(duplicates_settings_file):
    """Test loading duplicates settings from valid file."""
    config = DuplicatesSettings(
        survey_key="default_key",
        survey_id="default_id",
    )
    result = load_default_duplicates_settings(duplicates_settings_file, config)

    # Saved settings should override defaults
    assert result.survey_key == "survey_key"
    assert result.survey_id == "survey_id"


def test_load_default_duplicates_settings_missing_file():
    """Test loading duplicates settings when file doesn't exist."""
    config = DuplicatesSettings(
        survey_key="default_key",
        survey_id="default_id",
        enumerator="default_enum",
    )
    result = load_default_duplicates_settings("nonexistent.json", config)

    # Should return default config when file doesn't exist
    assert result.survey_key == "default_key"
    assert result.survey_id == "default_id"
    assert result.enumerator == "default_enum"


# ============================================
# EXPAND_COL_NAMES TESTS
# ============================================


def test_expand_col_names_exact():
    """Test expand_col_names with exact match."""
    col_names = ["age", "income", "age_group", "income_total"]
    result = expand_col_names(col_names, "age", "exact")
    assert result == ["age"]


def test_expand_col_names_startswith():
    """Test expand_col_names with startswith pattern."""
    col_names = ["age", "income", "age_group", "income_total"]
    result = expand_col_names(col_names, "age", "startswith")
    assert set(result) == {"age", "age_group"}


def test_expand_col_names_endswith():
    """Test expand_col_names with endswith pattern."""
    col_names = ["age", "income", "age_group", "income_total"]
    result = expand_col_names(col_names, "total", "endswith")
    assert result == ["income_total"]


def test_expand_col_names_contains():
    """Test expand_col_names with contains pattern."""
    col_names = ["age", "income", "age_group", "income_total"]
    result = expand_col_names(col_names, "group", "contains")
    assert result == ["age_group"]


def test_expand_col_names_regex():
    """Test expand_col_names with regex pattern."""
    col_names = ["age", "income", "age_group", "income_total", "age2"]
    result = expand_col_names(col_names, r"^age\d+$", "regex")
    assert result == ["age2"]


def test_expand_col_names_invalid_regex():
    """Test expand_col_names with invalid regex pattern."""
    col_names = ["age", "income"]
    result = expand_col_names(col_names, "[", "regex")  # Invalid regex
    assert result == []


def test_expand_col_names_unknown_search_type():
    """Test expand_col_names with unknown search type."""
    col_names = ["age", "income"]
    result = expand_col_names(col_names, "age", "invalid_type")
    assert result == []


# ============================================
# CONDITION VALIDATION AND SERIALIZATION TESTS
# ============================================


def test_validate_duplicates_condition_date_value_none():
    """Test _validate_duplicates_condition_date_value with None value."""
    default = datetime.date(2024, 1, 1)
    result = _validate_duplicates_condition_date_value(None, default)
    assert result == default


def test_validate_duplicates_condition_date_value_single_date():
    """Test _validate_duplicates_condition_date_value with single date."""
    value = "2024-01-15"
    default = datetime.date(2024, 1, 1)
    result = _validate_duplicates_condition_date_value(value, default)
    assert result == datetime.date(2024, 1, 15)


def test_validate_duplicates_condition_date_value_date_range():
    """Test _validate_duplicates_condition_date_value with date range."""
    value = ["2024-01-01", "2024-01-31"]
    default = (datetime.date(2024, 1, 1), datetime.date(2024, 1, 31))
    result = _validate_duplicates_condition_date_value(value, default)
    assert result == (datetime.date(2024, 1, 1), datetime.date(2024, 1, 31))


def test_validate_duplicates_condition_date_value_invalid():
    """Test _validate_duplicates_condition_date_value with invalid date."""
    value = "invalid-date"
    default = datetime.date(2024, 1, 1)
    result = _validate_duplicates_condition_date_value(value, default)
    assert result == default


def test_serialize_condition_value_for_json_date():
    """Test _serialize_condition_value_for_json with date."""
    value = datetime.date(2024, 1, 15)
    result = _serialize_condition_value_for_json(value)
    assert result == "2024-01-15"


def test_serialize_condition_value_for_json_list():
    """Test _serialize_condition_value_for_json with list of dates."""
    value = [datetime.date(2024, 1, 1), datetime.date(2024, 1, 31)]
    result = _serialize_condition_value_for_json(value)
    assert result == ["2024-01-01", "2024-01-31"]


def test_serialize_condition_value_for_json_primitive():
    """Test _serialize_condition_value_for_json with primitive types."""
    assert _serialize_condition_value_for_json(25) == 25
    assert _serialize_condition_value_for_json(3.14) == 3.14
    assert _serialize_condition_value_for_json("text") == "text"


# ============================================
# NUMERIC CONDITION TESTS
# ============================================


def test_apply_numeric_condition_equals():
    """Test _apply_numeric_condition with EQUALS."""
    col = pl.col("age")
    result_expr = _apply_numeric_condition(col, NumCondition.EQUALS.value, 25)
    data = pl.DataFrame({"age": [20, 25, 30]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [False, True, False]


def test_apply_numeric_condition_not_equals():
    """Test _apply_numeric_condition with NOT_EQUALS."""
    col = pl.col("age")
    result_expr = _apply_numeric_condition(col, NumCondition.NOT_EQUALS.value, 25)
    data = pl.DataFrame({"age": [20, 25, 30]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [True, False, True]


def test_apply_numeric_condition_greater_than():
    """Test _apply_numeric_condition with GREATER_THAN."""
    col = pl.col("age")
    result_expr = _apply_numeric_condition(col, NumCondition.GREATER_THAN.value, 25)
    data = pl.DataFrame({"age": [20, 25, 30]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [False, False, True]


def test_apply_numeric_condition_greater_than_or_equal():
    """Test _apply_numeric_condition with GREATER_THAN_OR_EQUAL."""
    col = pl.col("age")
    result_expr = _apply_numeric_condition(
        col, NumCondition.GREATER_THAN_OR_EQUAL.value, 25
    )
    data = pl.DataFrame({"age": [20, 25, 30]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [False, True, True]


def test_apply_numeric_condition_less_than():
    """Test _apply_numeric_condition with LESS_THAN."""
    col = pl.col("age")
    result_expr = _apply_numeric_condition(col, NumCondition.LESS_THAN.value, 25)
    data = pl.DataFrame({"age": [20, 25, 30]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [True, False, False]


def test_apply_numeric_condition_less_than_or_equal():
    """Test _apply_numeric_condition with LESS_THAN_OR_EQUAL."""
    col = pl.col("age")
    result_expr = _apply_numeric_condition(
        col, NumCondition.LESS_THAN_OR_EQUAL.value, 25
    )
    data = pl.DataFrame({"age": [20, 25, 30]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [True, True, False]


def test_apply_numeric_condition_includes():
    """Test _apply_numeric_condition with INCLUDES."""
    col = pl.col("age")
    result_expr = _apply_numeric_condition(col, NumCondition.INCLUDES.value, [20, 30])
    data = pl.DataFrame({"age": [20, 25, 30]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [True, False, True]


def test_apply_numeric_condition_excludes():
    """Test _apply_numeric_condition with EXCLUDES."""
    col = pl.col("age")
    result_expr = _apply_numeric_condition(col, NumCondition.EXCLUDES.value, [20, 30])
    data = pl.DataFrame({"age": [20, 25, 30]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [False, True, False]


def test_apply_numeric_condition_in_range():
    """Test _apply_numeric_condition with IN_RANGE."""
    col = pl.col("age")
    result_expr = _apply_numeric_condition(col, NumCondition.IN_RANGE.value, [20, 30])
    data = pl.DataFrame({"age": [15, 20, 25, 30, 35]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [False, True, True, True, False]


def test_apply_numeric_condition_with_date():
    """Test _apply_numeric_condition with date values."""
    col = pl.col("date_col")
    date_val = datetime.date(2024, 1, 15)
    result_expr = _apply_numeric_condition(col, NumCondition.EQUALS.value, date_val)
    data = pl.DataFrame(
        {
            "date_col": [
                datetime.date(2024, 1, 14),
                datetime.date(2024, 1, 15),
                datetime.date(2024, 1, 16),
            ]
        }
    )
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [False, True, False]


def test_apply_numeric_condition_invalid_type():
    """Test _apply_numeric_condition with invalid condition type."""
    col = pl.col("age")
    with pytest.raises(ValueError, match="Unsupported numeric condition type"):
        _apply_numeric_condition(col, "invalid_condition", 25)


# ============================================
# STRING CONDITION TESTS
# ============================================


def test_apply_string_condition_equals():
    """Test _apply_string_condition with EQUALS."""
    col = pl.col("gender")
    result_expr = _apply_string_condition(col, StrCondition.EQUALS.value, "M")
    data = pl.DataFrame({"gender": ["M", "F", "M"]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [True, False, True]


def test_apply_string_condition_not_equals():
    """Test _apply_string_condition with NOT_EQUALS."""
    col = pl.col("gender")
    result_expr = _apply_string_condition(col, StrCondition.NOT_EQUALS.value, "M")
    data = pl.DataFrame({"gender": ["M", "F", "M"]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [False, True, False]


def test_apply_string_condition_startswith():
    """Test _apply_string_condition with STARTWITH."""
    col = pl.col("name")
    result_expr = _apply_string_condition(col, StrCondition.STARTWITH.value, "Jo")
    data = pl.DataFrame({"name": ["John", "Jane", "Joe"]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [True, False, True]


def test_apply_string_condition_endswith():
    """Test _apply_string_condition with ENDWITH."""
    col = pl.col("name")
    result_expr = _apply_string_condition(col, StrCondition.ENDWITH.value, "e")
    data = pl.DataFrame({"name": ["John", "Jane", "Joe"]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [False, True, True]


def test_apply_string_condition_contains():
    """Test _apply_string_condition with CONTAINS."""
    col = pl.col("name")
    result_expr = _apply_string_condition(col, StrCondition.CONTAINS.value, "an")
    data = pl.DataFrame({"name": ["John", "Jane", "Joe"]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [False, True, False]


def test_apply_string_condition_includes():
    """Test _apply_string_condition with INCLUDES."""
    col = pl.col("gender")
    result_expr = _apply_string_condition(col, StrCondition.INCLUDES.value, ["M", "F"])
    data = pl.DataFrame({"gender": ["M", "F", "O"]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [True, True, False]


def test_apply_string_condition_excludes():
    """Test _apply_string_condition with EXCLUDES."""
    col = pl.col("gender")
    result_expr = _apply_string_condition(col, StrCondition.EXCLUDES.value, ["M", "F"])
    data = pl.DataFrame({"gender": ["M", "F", "O"]})
    result = data.select(result_expr.alias("result"))
    assert result["result"].to_list() == [False, False, True]


def test_apply_string_condition_invalid_type():
    """Test _apply_string_condition with invalid condition type."""
    col = pl.col("gender")
    with pytest.raises(ValueError, match="Unsupported string condition type"):
        _apply_string_condition(col, "invalid_condition", "M")


# ============================================
# BUILD_FILTER_EXPRESSION TESTS
# ============================================


def test_build_filter_expression_numeric():
    """Test _build_filter_expression with numeric condition."""
    condition = FilterCondition(
        condition_col="age",
        condition_type=NumCondition.GREATER_THAN.value,
        condition_value=25,
        missing_as_duplicates=False,
    )
    col_expr = pl.col("age")
    filter_expr = _build_filter_expression(condition, col_expr)

    data = pl.DataFrame({"age": [20, 25, 30]})
    result = data.filter(filter_expr)
    assert result["age"].to_list() == [30]


def test_build_filter_expression_string():
    """Test _build_filter_expression with string condition."""
    condition = FilterCondition(
        condition_col="gender",
        condition_type=StrCondition.EQUALS.value,
        condition_value="M",
        missing_as_duplicates=False,
    )
    col_expr = pl.col("gender")
    filter_expr = _build_filter_expression(condition, col_expr)

    data = pl.DataFrame({"gender": ["M", "F", "M"]})
    result = data.filter(filter_expr)
    assert result["gender"].to_list() == ["M", "M"]


def test_build_filter_expression_with_nulls():
    """Test _build_filter_expression with missing_as_duplicates=True."""
    condition = FilterCondition(
        condition_col="age",
        condition_type=NumCondition.EQUALS.value,
        condition_value=25,
        missing_as_duplicates=True,
    )
    col_expr = pl.col("age")
    filter_expr = _build_filter_expression(condition, col_expr)

    data = pl.DataFrame({"age": [20, 25, None]})
    result = data.filter(filter_expr)
    assert len(result) == 2  # 25 and None


def test_build_filter_expression_invalid_condition():
    """Test _build_filter_expression with invalid condition type."""
    condition = FilterCondition(
        condition_col="age",
        condition_type="invalid_type",
        condition_value=25,
    )
    col_expr = pl.col("age")

    with pytest.raises(ValueError, match="Unknown condition type"):
        _build_filter_expression(condition, col_expr)


# ============================================
# FILTER_DATA_ON_CONDITIONS TESTS
# ============================================


def test_filter_data_on_conditions_empty(sample_data_pl, tmp_path, monkeypatch):
    """Test _filter_data_on_conditions with empty conditions."""
    # Mock duckdb_save_table
    saved_data = []

    def mock_save(project_id, data, alias, db_name):
        saved_data.append(data)

    monkeypatch.setattr("datasure.checks.duplicates.duckdb_save_table", mock_save)

    _filter_data_on_conditions("project1", sample_data_pl, {})

    assert len(saved_data) == 1
    assert saved_data[0].height == sample_data_pl.height


def test_filter_data_on_conditions_numeric(sample_data_pl, monkeypatch):
    """Test _filter_data_on_conditions with numeric condition."""
    saved_data = []

    def mock_save(project_id, data, alias, db_name):
        saved_data.append(data)

    monkeypatch.setattr("datasure.checks.duplicates.duckdb_save_table", mock_save)

    conditions = {
        "condition_col": "age",
        "condition_type": NumCondition.GREATER_THAN.value,
        "condition_value": 28,
        "missing_as_duplicates": False,
    }

    _filter_data_on_conditions("project1", sample_data_pl, conditions)

    assert len(saved_data) == 1
    filtered = saved_data[0]
    assert all(age > 28 for age in filtered["age"].to_list())


def test_filter_data_on_conditions_string(sample_data_pl, monkeypatch):
    """Test _filter_data_on_conditions with string condition."""
    saved_data = []

    def mock_save(project_id, data, alias, db_name):
        saved_data.append(data)

    monkeypatch.setattr("datasure.checks.duplicates.duckdb_save_table", mock_save)

    conditions = {
        "condition_col": "gender",
        "condition_type": StrCondition.EQUALS.value,
        "condition_value": "M",
        "missing_as_duplicates": False,
    }

    _filter_data_on_conditions("project1", sample_data_pl, conditions)

    assert len(saved_data) == 1
    filtered = saved_data[0]
    assert all(g == "M" for g in filtered["gender"].to_list())


def test_filter_data_on_conditions_date(sample_data_pl, monkeypatch):
    """Test _filter_data_on_conditions with date condition."""
    saved_data = []

    def mock_save(project_id, data, alias, db_name):
        saved_data.append(data)

    monkeypatch.setattr("datasure.checks.duplicates.duckdb_save_table", mock_save)

    conditions = {
        "condition_col": "survey_date",
        "condition_type": NumCondition.GREATER_THAN.value,
        "condition_value": datetime.date(2024, 1, 3),  # Use date object, not string
        "missing_as_duplicates": False,
    }

    _filter_data_on_conditions("project1", sample_data_pl, conditions)

    assert len(saved_data) == 1
    filtered = saved_data[0]
    assert all(d > datetime.date(2024, 1, 3) for d in filtered["survey_date"].to_list())


# ============================================
# DUPLICATES COLUMN CONFIG TESTS
# ============================================


def test_update_duplicates_column_config(monkeypatch):
    """Test _update_duplicates_column_config function."""
    saved_data = []
    loaded_data = pl.DataFrame()

    def mock_get(project_id, alias, db_name):
        return loaded_data

    def mock_save(project_id, data, alias, db_name):
        saved_data.append(data)

    monkeypatch.setattr("datasure.checks.duplicates.duckdb_get_table", mock_get)
    monkeypatch.setattr("datasure.checks.duplicates.duckdb_save_table", mock_save)

    _update_duplicates_column_config(
        "project1",
        "page1",
        "exact",
        None,
        ["age", "income"],
        False,
    )

    assert len(saved_data) == 1
    config = saved_data[0]
    assert config["search_type"][0] == "exact"
    # Extract the list value from the Polars Series
    assert config["column_name"].to_list()[0] == ["age", "income"]
    assert config["locked"][0] is False


def test_ensure_duplicates_column_formats():
    """Test _ensure_duplicates_column_formats function."""
    data = pl.DataFrame(
        {
            "search_type": ["exact"],
            "pattern": [None],
            "column_name": [["age"]],
            "locked": [False],
        }
    )

    result = _ensure_duplicates_column_formats(data)

    assert result.schema["search_type"] == pl.Utf8
    assert result.schema["pattern"] == pl.Utf8
    assert result.schema["column_name"] == pl.List(pl.Utf8)
    assert result.schema["locked"] == pl.Boolean


def test_update_unlocked_duplicates_cols():
    """Test _update_unlocked_duplicates_cols function."""
    config = pl.DataFrame(
        {
            "search_type": ["startswith", "exact"],
            "pattern": ["age", None],
            "column_name": [["age"], ["income"]],
            "locked": [False, True],
        }
    )

    all_columns = ["age", "age_group", "age_total", "income"]

    result = _update_unlocked_duplicates_cols(config, all_columns)

    # Unlocked row should be updated with new matches - extract from Series
    assert set(result["column_name"].to_list()[0]) == {"age", "age_group", "age_total"}
    # Locked row should remain unchanged - extract from Series
    assert result["column_name"].to_list()[1] == ["income"]


def test_update_unlocked_duplicates_cols_empty():
    """Test _update_unlocked_duplicates_cols with empty config."""
    config = pl.DataFrame()
    all_columns = ["age", "income"]

    result = _update_unlocked_duplicates_cols(config, all_columns)

    assert result.is_empty()


# ============================================
# COMPUTE DUPLICATES TESTS
# ============================================


def test_compute_duplicates_statistics(sample_data_pl):
    """Test compute_duplicates_statistics function."""
    settings = DuplicatesSettings(
        survey_id="survey_id",
        survey_key="survey_key",
    )

    dup_cols = ["age", "income", "gender"]

    result = compute_duplicates_statistics(sample_data_pl, settings, dup_cols)

    assert result.number_of_columns_checked == 3
    assert result.total_duplicates > 0
    assert result.number_of_cols_with_duplicates > 0


def test_compute_duplicates_statistics_empty_cols():
    """Test compute_duplicates_statistics with empty columns."""
    data = pl.DataFrame({"survey_id": ["S001", "S002"]})
    settings = DuplicatesSettings(
        survey_id="survey_id",
    )

    result = compute_duplicates_statistics(data, settings, [])

    assert result.number_of_columns_checked == 0
    assert result.total_duplicates == 0
    assert result.number_of_cols_with_duplicates == 0
    assert result.number_of_cols_without_duplicates == 0


def test_compute_duplicates_statistics_no_survey_id():
    """Test compute_duplicates_statistics without survey_id or survey_key."""
    data = pl.DataFrame({"age": [25, 30]})
    settings = DuplicatesSettings(
        survey_id=None,
        survey_key=None,
    )

    with pytest.raises(
        ValueError, match="Either survey_id or survey_key must be provided"
    ):
        compute_duplicates_statistics(data, settings, ["age"])


def test_compute_id_duplicates(sample_data_pl):
    """Test compute_id_duplicates function."""
    result = compute_id_duplicates(
        sample_data_pl,
        "survey_id",
        "survey_date",
        "survey_key",
    )

    # S002 and S004 are duplicated
    assert not result.is_empty()
    assert "id_dup_count" in result.columns
    assert "id_dup_percent" in result.columns

    # Check that only duplicated IDs are present
    unique_ids = result["survey_id"].unique().to_list()
    assert "S002" in unique_ids
    assert "S004" in unique_ids


def test_compute_id_duplicates_no_duplicates():
    """Test compute_id_duplicates with no duplicates."""
    data = pl.DataFrame(
        {
            "survey_id": ["S001", "S002", "S003"],
            "survey_key": ["K001", "K002", "K003"],
            "survey_date": [
                datetime.date(2024, 1, 1),
                datetime.date(2024, 1, 2),
                datetime.date(2024, 1, 3),
            ],
        }
    )

    result = compute_id_duplicates(data, "survey_id", "survey_date", "survey_key")

    assert result.is_empty()


def test_compute_column_duplicates(sample_data_pl):
    """Test compute_column_duplicates function."""
    result = compute_column_duplicates(
        sample_data_pl,
        "survey_id",
        "survey_date",
        "age",
    )

    # age=30 and age=28 appear twice
    assert not result.is_empty()
    assert "age_dup_count" in result.columns
    assert "age_dup_percent" in result.columns

    # Check duplicate counts
    age_30_count = result.filter(pl.col("age") == 30)["age_dup_count"][0]
    assert age_30_count == 2


def test_compute_column_duplicates_no_duplicates():
    """Test compute_column_duplicates with no duplicates."""
    data = pl.DataFrame(
        {
            "survey_id": ["S001", "S002", "S003"],
            "survey_date": [
                datetime.date(2024, 1, 1),
                datetime.date(2024, 1, 2),
                datetime.date(2024, 1, 3),
            ],
            "age": [25, 30, 35],
        }
    )

    result = compute_column_duplicates(data, "survey_id", "survey_date", "age")

    assert result.is_empty()


def test_compute_column_duplicates_missing_columns():
    """Test compute_column_duplicates with missing optional columns."""
    data = pl.DataFrame(
        {
            "age": [25, 30, 30, 35],
        }
    )

    result = compute_column_duplicates(data, None, None, "age")

    assert not result.is_empty()
    assert "age_dup_count" in result.columns
    # survey_id and survey_date should not be in result since they don't exist
    assert "survey_id" not in result.columns
    assert "survey_date" not in result.columns


# ============================================
# EDGE CASES AND ERROR HANDLING
# ============================================


def test_edge_case_empty_dataframe():
    """Test handling of empty dataframes."""
    empty_data = pl.DataFrame(schema={"survey_id": pl.Utf8, "age": pl.Int64})
    settings = DuplicatesSettings(
        survey_id="survey_id",
    )

    result = compute_duplicates_statistics(empty_data, settings, ["age"])

    assert result.number_of_columns_checked == 1
    assert result.total_duplicates == 0
    assert result.number_of_cols_with_duplicates == 0
    assert result.number_of_cols_without_duplicates == 1


def test_edge_case_all_duplicates():
    """Test handling when all values are duplicates."""
    data = pl.DataFrame(
        {
            "survey_id": ["S001", "S001", "S001"],
            "survey_key": ["K001", "K002", "K003"],
            "age": [25, 25, 25],
        }
    )

    result = compute_id_duplicates(data, "survey_id", None, "survey_key")

    assert result.height == 3
    assert all(count == 3 for count in result["id_dup_count"].to_list())


def test_edge_case_single_row():
    """Test handling of single row datasets."""
    data = pl.DataFrame(
        {
            "survey_id": ["S001"],
            "age": [25],
        }
    )
    settings = DuplicatesSettings(
        survey_id="survey_id",
    )

    result = compute_duplicates_statistics(data, settings, ["age"])

    assert result.number_of_columns_checked == 1
    assert result.total_duplicates == 0


def test_edge_case_null_values():
    """Test handling of null values in data."""
    data = pl.DataFrame(
        {
            "survey_id": ["S001", "S002", None, None],
            "survey_key": ["K001", "K002", "K003", "K004"],
            "age": [25, None, None, 30],
        }
    )

    result = compute_id_duplicates(data, "survey_id", None, "survey_key")

    # Null values are considered duplicates
    assert not result.is_empty()


# ============================================
# INTEGRATION TESTS
# ============================================


def test_full_duplicates_workflow(sample_data_pl, monkeypatch):
    """Test complete duplicates workflow."""
    # Step 1: Configure settings
    settings = DuplicatesSettings(
        survey_id="survey_id",
        survey_key="survey_key",
        survey_date="survey_date",
        enumerator="enumerator",
    )

    # Step 2: Compute ID duplicates
    id_dups = compute_id_duplicates(
        sample_data_pl,
        settings.survey_id,
        settings.survey_date,
        settings.survey_key,
    )
    assert not id_dups.is_empty()

    # Step 3: Compute statistics
    dup_cols = ["age", "income"]
    stats = compute_duplicates_statistics(sample_data_pl, settings, dup_cols)
    assert stats.number_of_columns_checked == 2

    # Step 4: Compute column duplicates
    col_dups = compute_column_duplicates(
        sample_data_pl,
        settings.survey_id,
        settings.survey_date,
        "age",
    )
    assert not col_dups.is_empty()


def test_duplicates_workflow_with_filtering(sample_data_pl, monkeypatch):
    """Test duplicates workflow with data filtering."""
    saved_data = []

    def mock_save(project_id, data, alias, db_name):
        saved_data.append(data)

    monkeypatch.setattr("datasure.checks.duplicates.duckdb_save_table", mock_save)

    # Apply filter
    conditions = {
        "condition_col": "age",
        "condition_type": NumCondition.GREATER_THAN.value,
        "condition_value": 25,
        "missing_as_duplicates": False,
    }

    _filter_data_on_conditions("project1", sample_data_pl, conditions)

    filtered_data = saved_data[0]

    # Compute duplicates on filtered data
    settings = DuplicatesSettings(
        survey_id="survey_id",
        survey_key="survey_key",
    )

    stats = compute_duplicates_statistics(filtered_data, settings, ["age", "income"])

    assert stats.number_of_columns_checked == 2
    # All age values in filtered data should be > 25
    assert all(age > 25 for age in filtered_data["age"].to_list())


# ============================================
# DATE HELPER FUNCTION TESTS
# ============================================


class TestIsDateNotDatetime:
    """Tests for _is_date_not_datetime helper."""

    def test_date_object_returns_true(self):
        assert _is_date_not_datetime(datetime.date(2024, 1, 1)) is True

    def test_datetime_object_returns_false(self):
        assert _is_date_not_datetime(datetime.datetime(2024, 1, 1, 12, 0)) is False

    def test_string_returns_false(self):
        assert _is_date_not_datetime("2024-01-01") is False

    def test_int_returns_false(self):
        assert _is_date_not_datetime(42) is False

    def test_none_returns_false(self):
        assert _is_date_not_datetime(None) is False


class TestHasDateValues:
    """Tests for _has_date_values helper."""

    def test_list_with_dates(self):
        assert (
            _has_date_values([datetime.date(2024, 1, 1), datetime.date(2024, 2, 1)])
            is True
        )

    def test_list_without_dates(self):
        assert _has_date_values([1, 2, 3]) is False

    def test_mixed_list_with_date(self):
        assert _has_date_values([1, datetime.date(2024, 1, 1)]) is True

    def test_tuple_with_dates(self):
        assert _has_date_values((datetime.date(2024, 1, 1),)) is True

    def test_empty_list(self):
        assert _has_date_values([]) is False

    def test_list_with_datetimes(self):
        assert _has_date_values([datetime.datetime(2024, 1, 1, 12, 0)]) is False


class TestCastColForDateComparison:
    """Tests for _cast_col_for_date_comparison helper."""

    def test_single_date_value_casts(self):
        col = pl.col("dt")
        result = _cast_col_for_date_comparison(
            col, NumCondition.EQUALS.value, datetime.date(2024, 1, 1)
        )
        # Verify cast is applied by evaluating on a DataFrame
        data = pl.DataFrame({"dt": [datetime.datetime(2024, 1, 1, 12, 0)]})
        result_data = data.select(result)
        assert result_data["dt"].dtype == pl.Date

    def test_non_date_scalar_no_cast(self):
        col = pl.col("val")
        result = _cast_col_for_date_comparison(col, NumCondition.EQUALS.value, 42)
        data = pl.DataFrame({"val": [1, 2, 3]})
        result_data = data.select(result)
        assert result_data["val"].dtype == pl.Int64

    def test_includes_with_date_list_casts(self):
        col = pl.col("dt")
        dates = [datetime.date(2024, 1, 1), datetime.date(2024, 2, 1)]
        result = _cast_col_for_date_comparison(col, NumCondition.INCLUDES.value, dates)
        data = pl.DataFrame({"dt": [datetime.datetime(2024, 1, 1, 12, 0)]})
        result_data = data.select(result)
        assert result_data["dt"].dtype == pl.Date

    def test_in_range_with_date_tuple_casts(self):
        col = pl.col("dt")
        dates = (datetime.date(2024, 1, 1), datetime.date(2024, 12, 31))
        result = _cast_col_for_date_comparison(col, NumCondition.IN_RANGE.value, dates)
        data = pl.DataFrame({"dt": [datetime.datetime(2024, 6, 1, 12, 0)]})
        result_data = data.select(result)
        assert result_data["dt"].dtype == pl.Date

    def test_numeric_list_no_cast(self):
        col = pl.col("val")
        result = _cast_col_for_date_comparison(
            col, NumCondition.INCLUDES.value, [1, 2, 3]
        )
        data = pl.DataFrame({"val": [1, 2, 3]})
        result_data = data.select(result)
        assert result_data["val"].dtype == pl.Int64

    def test_excludes_with_date_list_no_cast(self):
        """EXCLUDES is not in the needs_cast conditions."""
        col = pl.col("val")
        dates = [datetime.date(2024, 1, 1)]
        result = _cast_col_for_date_comparison(col, NumCondition.EXCLUDES.value, dates)
        data = pl.DataFrame({"val": [1]})
        result_data = data.select(result)
        assert result_data["val"].dtype == pl.Int64


# ============================================
# COERCION FUNCTION TESTS
# ============================================


class TestCoerceDatetimeValue:
    """Tests for _coerce_datetime_value."""

    def test_string_to_date(self):
        result = _coerce_datetime_value("2024-01-15")
        assert result == datetime.date(2024, 1, 15)

    def test_list_of_strings_to_dates(self):
        result = _coerce_datetime_value(["2024-01-01", "2024-01-31"])
        assert result == [datetime.date(2024, 1, 1), datetime.date(2024, 1, 31)]

    def test_invalid_string_returns_unchanged(self):
        result = _coerce_datetime_value("not-a-date")
        assert result == "not-a-date"

    def test_none_returns_unchanged(self):
        result = _coerce_datetime_value(None)
        assert result is None

    def test_int_returns_unchanged(self):
        result = _coerce_datetime_value(42)
        assert result == 42

    def test_list_with_mixed_types(self):
        result = _coerce_datetime_value(["2024-01-01", 42])
        assert result[0] == datetime.date(2024, 1, 1)
        assert result[1] == 42

    def test_invalid_list_returns_unchanged(self):
        """List with values that can't be parsed returns original list."""
        result = _coerce_datetime_value([None, None])
        assert result == [None, None]


class TestCoerceNumericValue:
    """Tests for _coerce_numeric_value."""

    def test_string_to_int(self):
        result = _coerce_numeric_value("42", pl.Int64)
        assert result == 42
        assert isinstance(result, int)

    def test_string_to_float(self):
        result = _coerce_numeric_value("3.14", pl.Float64)
        assert result == 3.14
        assert isinstance(result, float)

    def test_list_of_strings_to_ints(self):
        result = _coerce_numeric_value(["1", "2", "3"], pl.Int32)
        assert result == [1, 2, 3]

    def test_list_of_strings_to_floats(self):
        result = _coerce_numeric_value(["1.1", "2.2"], pl.Float64)
        assert result == [1.1, 2.2]

    def test_invalid_string_returns_unchanged(self):
        result = _coerce_numeric_value("abc", pl.Int64)
        assert result == "abc"

    def test_none_returns_unchanged(self):
        result = _coerce_numeric_value(None, pl.Int64)
        assert result is None

    def test_int_returns_unchanged(self):
        result = _coerce_numeric_value(42, pl.Int64)
        assert result == 42

    def test_list_with_mixed_types(self):
        result = _coerce_numeric_value(["1", 2], pl.Int64)
        assert result == [1, 2]


class TestCoerceConditionValue:
    """Tests for _coerce_condition_value."""

    def test_coerce_datetime_column(self):
        conditions = {
            "condition_col": "date_col",
            "condition_value": "2024-01-15",
        }
        data = pl.DataFrame({"date_col": [datetime.datetime(2024, 1, 1, 12, 0)]})
        _coerce_condition_value(conditions, data)
        assert conditions["condition_value"] == datetime.date(2024, 1, 15)

    def test_coerce_numeric_column(self):
        conditions = {
            "condition_col": "age",
            "condition_value": "25",
        }
        data = pl.DataFrame({"age": [20, 30]})
        _coerce_condition_value(conditions, data)
        assert conditions["condition_value"] == 25

    def test_string_column_not_coerced(self):
        conditions = {
            "condition_col": "name",
            "condition_value": "John",
        }
        data = pl.DataFrame({"name": ["John", "Jane"]})
        _coerce_condition_value(conditions, data)
        assert conditions["condition_value"] == "John"

    def test_missing_condition_value_returns_early(self):
        conditions = {
            "condition_col": "age",
            "condition_value": None,
        }
        data = pl.DataFrame({"age": [20, 30]})
        _coerce_condition_value(conditions, data)
        assert conditions["condition_value"] is None

    def test_missing_column_returns_early(self):
        conditions = {
            "condition_col": "nonexistent",
            "condition_value": "42",
        }
        data = pl.DataFrame({"age": [20, 30]})
        _coerce_condition_value(conditions, data)
        assert conditions["condition_value"] == "42"


# ============================================
# HAS_VALID_FILTER_CONDITIONS TESTS
# ============================================


class TestHasValidFilterConditions:
    """Tests for _has_valid_filter_conditions."""

    def test_valid_conditions(self):
        conditions = {
            "condition_col": "age",
            "condition_type": NumCondition.EQUALS.value,
        }
        assert _has_valid_filter_conditions(conditions) is True

    def test_missing_condition_col(self):
        conditions = {"condition_type": NumCondition.EQUALS.value}
        assert _has_valid_filter_conditions(conditions) is False

    def test_missing_condition_type(self):
        conditions = {"condition_col": "age"}
        assert _has_valid_filter_conditions(conditions) is False

    def test_empty_dict(self):
        assert _has_valid_filter_conditions({}) is False

    def test_none_condition_col(self):
        conditions = {
            "condition_col": None,
            "condition_type": NumCondition.EQUALS.value,
        }
        assert _has_valid_filter_conditions(conditions) is False


# ============================================
# CREATE_SEARCH_TYPE_INFO TESTS
# ============================================


class TestCreateSearchTypeInfo:
    """Tests for _create_search_type_info."""

    @patch("datasure.checks.duplicates.st")
    def test_exact_search_type(self, mock_st):
        _create_search_type_info(SearchType.EXACT.value)
        mock_st.info.assert_called_once()
        assert "dropdown" in mock_st.info.call_args[0][0].lower()

    @patch("datasure.checks.duplicates.st")
    def test_startswith_search_type(self, mock_st):
        _create_search_type_info(SearchType.STARTSWITH.value)
        mock_st.info.assert_called_once()
        assert "start with" in mock_st.info.call_args[0][0].lower()

    @patch("datasure.checks.duplicates.st")
    def test_endswith_search_type(self, mock_st):
        _create_search_type_info(SearchType.ENDSWITH.value)
        mock_st.info.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    def test_contains_search_type(self, mock_st):
        _create_search_type_info(SearchType.CONTAINS.value)
        mock_st.info.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    def test_regex_search_type(self, mock_st):
        _create_search_type_info(SearchType.REGEX.value)
        mock_st.info.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    def test_unknown_search_type(self, mock_st):
        _create_search_type_info("unknown")
        mock_st.info.assert_not_called()


# ============================================
# FILTER_DATA_ON_CONDITIONS WITH COERCION TESTS
# ============================================


class TestFilterDataCoercion:
    """Test _filter_data_on_conditions with string values needing coercion."""

    def test_coerces_string_numeric_value(self, sample_data_pl, monkeypatch):
        """String condition values should be coerced to match column dtype."""
        saved_data = []

        def mock_save(project_id, data, alias, db_name):
            saved_data.append(data)

        monkeypatch.setattr("datasure.checks.duplicates.duckdb_save_table", mock_save)

        conditions = {
            "condition_col": "age",
            "condition_type": NumCondition.EQUALS.value,
            "condition_value": "30",
            "missing_as_duplicates": False,
        }

        _filter_data_on_conditions("project1", sample_data_pl, conditions)
        filtered = saved_data[0]
        assert all(age == 30 for age in filtered["age"].to_list())

    def test_no_conditions_returns_full_data(self, sample_data_pl, monkeypatch):
        """None conditions should save full dataset."""
        saved_data = []

        def mock_save(project_id, data, alias, db_name):
            saved_data.append(data)

        monkeypatch.setattr("datasure.checks.duplicates.duckdb_save_table", mock_save)

        _filter_data_on_conditions("project1", sample_data_pl, None)
        assert saved_data[0].height == sample_data_pl.height

    def test_invalid_conditions_raises(self, sample_data_pl, monkeypatch):
        """Invalid conditions should raise ValueError."""
        saved_data = []

        def mock_save(project_id, data, alias, db_name):
            saved_data.append(data)

        monkeypatch.setattr("datasure.checks.duplicates.duckdb_save_table", mock_save)

        conditions = {
            "condition_col": "age",
            "condition_type": NumCondition.IN_RANGE.value,
            "condition_value": 25,  # IN_RANGE requires list of 2
            "missing_as_duplicates": False,
        }

        with pytest.raises(ValueError, match="Invalid conditions"):
            _filter_data_on_conditions("project1", sample_data_pl, conditions)

    def test_missing_condition_col_saves_full_data(self, sample_data_pl, monkeypatch):
        """Conditions without condition_col should save full dataset."""
        saved_data = []

        def mock_save(project_id, data, alias, db_name):
            saved_data.append(data)

        monkeypatch.setattr("datasure.checks.duplicates.duckdb_save_table", mock_save)

        conditions = {
            "condition_type": NumCondition.EQUALS.value,
            "condition_value": 25,
        }

        _filter_data_on_conditions("project1", sample_data_pl, conditions)
        assert saved_data[0].height == sample_data_pl.height


# ============================================
# COMPUTE DUPLICATES STATISTICS EDGE CASES
# ============================================


class TestComputeDuplicatesStatisticsEdgeCases:
    """Additional tests for compute_duplicates_statistics."""

    def test_dup_cols_only_survey_ids(self):
        """When dup_cols only contain survey_id/key, should return zeros."""
        data = pl.DataFrame(
            {
                "survey_id": ["S001", "S002"],
                "survey_key": ["K001", "K002"],
            }
        )
        settings = DuplicatesSettings(
            survey_id="survey_id",
            survey_key="survey_key",
        )
        result = compute_duplicates_statistics(
            data, settings, ["survey_id", "survey_key"]
        )
        assert result.number_of_columns_checked == 0
        assert result.total_duplicates == 0

    def test_columns_without_duplicates(self):
        """Columns with all unique values."""
        data = pl.DataFrame(
            {
                "survey_id": ["S001", "S002", "S003"],
                "unique_col": [1, 2, 3],
            }
        )
        settings = DuplicatesSettings(survey_id="survey_id")
        result = compute_duplicates_statistics(data, settings, ["unique_col"])
        assert result.number_of_cols_without_duplicates == 1
        assert result.number_of_cols_with_duplicates == 0
        assert result.total_duplicates == 0


# ============================================
# UPDATE DUPLICATES COLUMN CONFIG EDGE CASES
# ============================================


class TestUpdateDuplicatesColumnConfigEdgeCases:
    """Additional tests for _update_duplicates_column_config."""

    def test_append_to_existing_config(self, monkeypatch):
        """Test appending new config to existing one."""
        existing = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["age"]],
                "locked": [False],
            },
            schema={
                "search_type": pl.Utf8,
                "pattern": pl.Utf8,
                "column_name": pl.List(pl.Utf8),
                "locked": pl.Boolean,
            },
        )

        saved_data = []

        def mock_get(project_id, alias, db_name):
            return existing

        def mock_save(project_id, data, alias, db_name):
            saved_data.append(data)

        monkeypatch.setattr("datasure.checks.duplicates.duckdb_get_table", mock_get)
        monkeypatch.setattr("datasure.checks.duplicates.duckdb_save_table", mock_save)

        _update_duplicates_column_config(
            "project1", "page1", "startswith", "inc", ["income", "income_total"], True
        )

        assert len(saved_data) == 1
        result = saved_data[0]
        assert result.height == 2
        assert result["search_type"].to_list() == ["exact", "startswith"]


# ============================================
# RENDER COLUMN LOCKING OPTIONS TESTS
# ============================================


class TestRenderColumnLockingOptions:
    """Tests for _render_column_locking_options."""

    def test_returns_initial_value_when_not_none(self):
        """When lock_cols_initial is not None, should return it directly."""
        result = _render_column_locking_options(["col1", "col2"], "exact", True)
        assert result is True

    def test_returns_initial_false_when_not_none(self):
        result = _render_column_locking_options(["col1", "col2"], "exact", False)
        assert result is False

    @patch("datasure.checks.duplicates.st")
    def test_calls_toggle_when_initial_is_none(self, mock_st):
        mock_st.toggle.return_value = True
        result = _render_column_locking_options(
            ["col1", "col2", "col3"], "startswith", None
        )
        mock_st.toggle.assert_called_once()
        assert result is True


# ============================================
# RENDER DUPLICATES SETTINGS TABLE TESTS
# ============================================


class TestRenderDuplicatesSettingsTable:
    """Tests for _render_duplicates_settings_table."""

    @patch("datasure.checks.duplicates.st")
    def test_renders_table(self, mock_st):
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_st.expander.return_value = mock_ctx

        data = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["age"]],
                "locked": [False],
            }
        )

        _render_duplicates_settings_table(data)
        mock_st.expander.assert_called_once()
        mock_st.dataframe.assert_called_once()


# ============================================
# RENDER ID DUPLICATES METRICS TESTS
# ============================================


class TestRenderIdDuplicatesMetrics:
    """Tests for _render_id_duplicates_metrics."""

    @patch("datasure.checks.duplicates.st")
    def test_no_survey_id(self, mock_st):
        """When survey_id is None, should show info message."""
        settings = DuplicatesSettings(survey_id="sid")
        settings_dict = settings.__dict__.copy()
        settings_dict["survey_id"] = None
        # Create a mock settings with survey_id = None
        mock_settings = MagicMock()
        mock_settings.survey_id = None

        _render_id_duplicates_metrics(pl.DataFrame(), mock_settings)
        mock_st.info.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    def test_empty_duplicates(self, mock_st):
        """When no duplicates found, should show info message."""
        settings = MagicMock()
        settings.survey_id = "survey_id"

        empty_data = pl.DataFrame(schema={"survey_id": pl.Utf8})
        _render_id_duplicates_metrics(empty_data, settings)
        mock_st.info.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    def test_with_duplicates(self, mock_st):
        """When duplicates exist, should show metrics."""
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_st.columns.return_value = [mock_ctx, mock_ctx, mock_ctx, mock_ctx]
        mock_st.container.return_value = mock_ctx

        settings = MagicMock()
        settings.survey_id = "survey_id"

        dup_data = pl.DataFrame(
            {
                "survey_id": ["S001", "S001", "S002", None],
                "id_dup_count": [2, 2, 1, 1],
            }
        )

        _render_id_duplicates_metrics(dup_data, settings)
        assert mock_st.metric.call_count == 3


# ============================================
# RENDER ID DUPLICATES TABLE TESTS
# ============================================


class TestRenderIdDuplicatesTable:
    """Tests for _render_id_duplicates_table."""

    @patch("datasure.checks.duplicates.st")
    def test_no_survey_id(self, mock_st):
        """When survey_id is None, should show info and return."""
        settings = MagicMock()
        settings.survey_id = None

        _render_id_duplicates_table(
            pl.DataFrame(), pl.DataFrame(), settings, "settings.json"
        )
        mock_st.info.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    @patch("datasure.checks.duplicates.load_check_settings")
    @patch("datasure.checks.duplicates.save_check_settings")
    def test_with_data_no_extra_cols(
        self, mock_save_settings, mock_load_settings, mock_st
    ):
        """When data exists but no extra columns selected."""
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_st.expander.return_value = mock_ctx
        mock_st.multiselect.return_value = []
        mock_load_settings.return_value = {}

        settings = MagicMock()
        settings.survey_id = "survey_id"
        settings.survey_key = "survey_key"

        data = pl.DataFrame(
            {
                "survey_id": ["S001", "S002"],
                "survey_key": ["K001", "K002"],
                "age": [25, 30],
            }
        )

        id_dups = pl.DataFrame(
            {
                "survey_id": ["S001"],
                "survey_key": ["K001"],
                "id_dup_count": [2],
                "id_dup_percent": [50.0],
            }
        )

        _render_id_duplicates_table(data, id_dups, settings, "settings.json")
        mock_st.dataframe.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    @patch("datasure.checks.duplicates.load_check_settings")
    @patch("datasure.checks.duplicates.save_check_settings")
    def test_with_extra_cols_and_join_keys(
        self, mock_save_settings, mock_load_settings, mock_st
    ):
        """When extra columns selected and join keys exist."""
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_st.expander.return_value = mock_ctx
        mock_st.multiselect.return_value = ["age"]
        mock_load_settings.return_value = {}

        settings = MagicMock()
        settings.survey_id = "survey_id"
        settings.survey_key = "survey_key"

        data = pl.DataFrame(
            {
                "survey_id": ["S001", "S002"],
                "survey_key": ["K001", "K002"],
                "age": [25, 30],
            }
        )

        id_dups = pl.DataFrame(
            {
                "survey_id": ["S001"],
                "survey_key": ["K001"],
                "id_dup_count": [2],
                "id_dup_percent": [50.0],
            }
        )

        _render_id_duplicates_table(data, id_dups, settings, "settings.json")
        mock_st.dataframe.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    @patch("datasure.checks.duplicates.load_check_settings")
    @patch("datasure.checks.duplicates.save_check_settings")
    def test_with_extra_cols_no_join_keys(
        self, mock_save_settings, mock_load_settings, mock_st
    ):
        """When extra columns selected but no matching join keys."""
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_st.expander.return_value = mock_ctx
        mock_st.multiselect.return_value = ["age"]
        mock_load_settings.return_value = {}

        settings = MagicMock()
        settings.survey_id = "id_col"
        settings.survey_key = "key_col"

        data = pl.DataFrame(
            {
                "id_col": ["S001"],
                "key_col": ["K001"],
                "age": [25],
            }
        )

        # id_dups doesn't have the join key columns
        id_dups = pl.DataFrame(
            {
                "other_col": ["X"],
                "id_dup_count": [2],
                "id_dup_percent": [50.0],
            }
        )

        _render_id_duplicates_table(data, id_dups, settings, "settings.json")
        mock_st.warning.assert_called_once()


# ============================================
# RENDER OTHER DUPLICATES METRICS TESTS
# ============================================


class TestRenderOtherDuplicatesMetrics:
    """Tests for _render_other_duplicates_metrics."""

    @patch("datasure.checks.duplicates.st")
    def test_empty_data(self, mock_st):
        """Empty data should return early."""
        settings = MagicMock()
        empty = pl.DataFrame(schema={"age": pl.Int64})
        _render_other_duplicates_metrics(empty, settings, ["age"])
        mock_st.metric.assert_not_called()

    @patch("datasure.checks.duplicates.st")
    def test_no_dup_cols(self, mock_st):
        """No dup_cols should show info message."""
        data = pl.DataFrame({"age": [25, 30]})
        settings = MagicMock()
        _render_other_duplicates_metrics(data, settings, None)
        mock_st.info.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    def test_empty_dup_cols(self, mock_st):
        """Empty dup_cols list should show info message."""
        data = pl.DataFrame({"age": [25, 30]})
        settings = MagicMock()
        _render_other_duplicates_metrics(data, settings, [])
        mock_st.info.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    def test_with_valid_data(self, mock_st):
        """With valid data and dup_cols should show 4 metrics."""
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        mock_st.columns.return_value = [mock_ctx, mock_ctx, mock_ctx, mock_ctx]
        mock_st.container.return_value = mock_ctx

        data = pl.DataFrame(
            {
                "survey_id": ["S001", "S002", "S003"],
                "age": [25, 25, 30],
            }
        )
        settings = DuplicatesSettings(survey_id="survey_id")

        _render_other_duplicates_metrics(data, settings, ["age"])
        assert mock_st.metric.call_count == 4


# ============================================
# RENDER NUMERIC CONDITION INPUT TESTS
# ============================================


class TestRenderNumericConditionInput:
    """Tests for _render_numeric_condition_input."""

    @patch("datasure.checks.duplicates.st")
    def test_in_range_condition(self, mock_st):
        """IN_RANGE should render a slider."""
        mock_st.slider.return_value = (10, 50)
        result = _render_numeric_condition_input(
            NumCondition.IN_RANGE.value, None, [10, 20, 30, 40, 50]
        )
        mock_st.slider.assert_called_once()
        assert result == (10, 50)

    @patch("datasure.checks.duplicates.st")
    def test_includes_condition(self, mock_st):
        """INCLUDES should render a multiselect."""
        mock_st.multiselect.return_value = [10, 20]
        result = _render_numeric_condition_input(
            NumCondition.INCLUDES.value, None, [10, 20, 30]
        )
        mock_st.multiselect.assert_called_once()
        assert result == [10, 20]

    @patch("datasure.checks.duplicates.st")
    def test_excludes_condition(self, mock_st):
        """EXCLUDES should render a multiselect."""
        mock_st.multiselect.return_value = [30]
        _render_numeric_condition_input(NumCondition.EXCLUDES.value, None, [10, 20, 30])
        mock_st.multiselect.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    def test_equals_condition(self, mock_st):
        """EQUALS should render a number_input."""
        mock_st.number_input.return_value = 25
        result = _render_numeric_condition_input(
            NumCondition.EQUALS.value, None, [10, 20, 30]
        )
        mock_st.number_input.assert_called_once()
        assert result == 25

    @patch("datasure.checks.duplicates.st")
    def test_default_value_used(self, mock_st):
        """When default_condition_value is provided, should use it."""
        mock_st.slider.return_value = (15, 45)
        result = _render_numeric_condition_input(
            NumCondition.IN_RANGE.value, (15, 45), [10, 20, 30, 40, 50]
        )
        assert result == (15, 45)

    @patch("datasure.checks.duplicates.st")
    def test_includes_with_non_list_default(self, mock_st):
        """INCLUDES with non-list default should wrap in list."""
        mock_st.multiselect.return_value = [10]
        _render_numeric_condition_input(NumCondition.INCLUDES.value, 10, [10, 20, 30])
        mock_st.multiselect.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    def test_equals_with_list_default(self, mock_st):
        """EQUALS with list default should extract first value."""
        mock_st.number_input.return_value = 10
        _render_numeric_condition_input(
            NumCondition.EQUALS.value, [10, 20], [10, 20, 30]
        )
        mock_st.number_input.assert_called_once()


# ============================================
# RENDER STRING CONDITION INPUT TESTS
# ============================================


class TestRenderStringConditionInput:
    """Tests for _render_string_condition_input."""

    @patch("datasure.checks.duplicates.st")
    def test_includes_condition(self, mock_st):
        """INCLUDES should render a multiselect."""
        mock_st.multiselect.return_value = ["M", "F"]
        result = _render_string_condition_input(
            StrCondition.INCLUDES.value, {}, ["M", "F", "O"]
        )
        mock_st.multiselect.assert_called_once()
        assert result == ["M", "F"]

    @patch("datasure.checks.duplicates.st")
    def test_excludes_condition(self, mock_st):
        """EXCLUDES should render a multiselect."""
        mock_st.multiselect.return_value = ["O"]
        _render_string_condition_input(StrCondition.EXCLUDES.value, {}, ["M", "F", "O"])
        mock_st.multiselect.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    def test_equals_condition(self, mock_st):
        """EQUALS should render a text_input."""
        mock_st.text_input.return_value = "M"
        result = _render_string_condition_input(
            StrCondition.EQUALS.value, {}, ["M", "F"]
        )
        mock_st.text_input.assert_called_once()
        assert result == "M"

    @patch("datasure.checks.duplicates.st")
    def test_with_saved_default_string(self, mock_st):
        """Saved condition_value string should be wrapped in list for multiselect."""
        mock_st.multiselect.return_value = ["M"]
        _render_string_condition_input(
            StrCondition.INCLUDES.value,
            {"condition_value": "M"},
            ["M", "F"],
        )
        mock_st.multiselect.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    def test_text_input_with_string_default(self, mock_st):
        """Text input with string default should use it directly."""
        mock_st.text_input.return_value = "test"
        _render_string_condition_input(
            StrCondition.EQUALS.value,
            {"condition_value": "test"},
            ["M", "F"],
        )
        mock_st.text_input.assert_called_once()


# ============================================
# RENDER CONDITION VALUE INPUT TESTS
# ============================================


class TestRenderConditionValueInput:
    """Tests for _render_condition_value_input."""

    @patch("datasure.checks.duplicates.st")
    @patch("datasure.checks.duplicates._render_datetime_condition_input")
    def test_datetime_column(self, mock_dt_input, mock_st):
        """Datetime column should call _render_datetime_condition_input."""
        mock_dt_input.return_value = (
            datetime.date(2024, 1, 1),
            {"condition_value": "2024-01-01"},
        )
        data = pl.DataFrame({"dt": [datetime.datetime(2024, 1, 1, 12, 0)]})

        result = _render_condition_value_input(
            data, "dt", NumCondition.EQUALS.value, {}, [datetime.datetime(2024, 1, 1)]
        )
        mock_dt_input.assert_called_once()
        assert result[0] == datetime.date(2024, 1, 1)

    @patch("datasure.checks.duplicates.st")
    @patch("datasure.checks.duplicates._render_numeric_condition_input")
    def test_numeric_column(self, mock_num_input, mock_st):
        """Numeric column should call _render_numeric_condition_input."""
        mock_num_input.return_value = 25
        data = pl.DataFrame({"age": [20, 25, 30]})

        result = _render_condition_value_input(
            data, "age", NumCondition.EQUALS.value, {}, [20, 25, 30]
        )
        mock_num_input.assert_called_once()
        assert result == (25, {})

    @patch("datasure.checks.duplicates.st")
    @patch("datasure.checks.duplicates._render_string_condition_input")
    def test_string_column(self, mock_str_input, mock_st):
        """String column should call _render_string_condition_input."""
        mock_str_input.return_value = "M"
        data = pl.DataFrame({"gender": ["M", "F"]})

        result = _render_condition_value_input(
            data, "gender", StrCondition.EQUALS.value, {}, ["M", "F"]
        )
        mock_str_input.assert_called_once()
        assert result == ("M", {})


# ============================================
# SERIALIZE CONDITION VALUE EDGE CASES
# ============================================


class TestSerializeConditionValueEdgeCases:
    """Additional edge case tests for _serialize_condition_value_for_json."""

    def test_tuple_of_dates(self):
        value = (datetime.date(2024, 1, 1), datetime.date(2024, 12, 31))
        result = _serialize_condition_value_for_json(value)
        assert result == ["2024-01-01", "2024-12-31"]

    def test_nested_list(self):
        value = [datetime.date(2024, 1, 1), 42, "text"]
        result = _serialize_condition_value_for_json(value)
        assert result == ["2024-01-01", 42, "text"]

    def test_datetime_not_serialized_as_date(self):
        value = datetime.datetime(2024, 1, 1, 12, 0, 0)
        result = _serialize_condition_value_for_json(value)
        assert result == value  # datetime is returned as-is

    def test_none_value(self):
        result = _serialize_condition_value_for_json(None)
        assert result is None


# ============================================
# VALIDATE DATE VALUE EDGE CASES
# ============================================


class TestValidateDateValueEdgeCases:
    """Additional edge case tests for _validate_duplicates_condition_date_value."""

    def test_empty_string_returns_default(self):
        default = datetime.date(2024, 1, 1)
        result = _validate_duplicates_condition_date_value("", default)
        assert result == default

    def test_list_wrong_length_returns_default(self):
        default = (datetime.date(2024, 1, 1), datetime.date(2024, 12, 31))
        result = _validate_duplicates_condition_date_value(["2024-01-01"], default)
        # Single-element list goes to else branch, tries fromisoformat on the list
        assert result == default

    def test_list_with_invalid_dates_returns_default(self):
        default = (datetime.date(2024, 1, 1), datetime.date(2024, 12, 31))
        result = _validate_duplicates_condition_date_value(
            ["invalid", "also-invalid"], default
        )
        assert result == default


# ============================================
# APPLY NUMERIC CONDITION WITH DATE CASTING TESTS
# ============================================


class TestApplyNumericConditionDateCasting:
    """Tests for _apply_numeric_condition with datetime columns and date values."""

    def test_includes_with_date_values(self):
        """INCLUDES with date values should cast datetime column to date."""
        col = pl.col("dt")
        dates = [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)]
        result_expr = _apply_numeric_condition(col, NumCondition.INCLUDES.value, dates)

        data = pl.DataFrame(
            {
                "dt": [
                    datetime.datetime(2024, 1, 1, 12, 0),
                    datetime.datetime(2024, 1, 2, 8, 0),
                    datetime.datetime(2024, 1, 3, 15, 0),
                ]
            }
        )
        result = data.select(result_expr.alias("result"))
        assert result["result"].to_list() == [True, True, False]

    def test_in_range_with_date_values(self):
        """IN_RANGE with date values should cast datetime column to date."""
        col = pl.col("dt")
        date_range = [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)]
        result_expr = _apply_numeric_condition(
            col, NumCondition.IN_RANGE.value, date_range
        )

        data = pl.DataFrame(
            {
                "dt": [
                    datetime.datetime(2024, 1, 1, 12, 0),
                    datetime.datetime(2024, 1, 2, 8, 0),
                    datetime.datetime(2024, 1, 3, 15, 0),
                ]
            }
        )
        result = data.select(result_expr.alias("result"))
        assert result["result"].to_list() == [True, True, False]


# ============================================
# UPDATE UNLOCKED DUPLICATES COLS EDGE CASES
# ============================================


class TestUpdateUnlockedDuplicatesColsEdgeCases:
    """Additional tests for _update_unlocked_duplicates_cols."""

    def test_locked_exact_search_not_updated(self):
        """Locked rows should never be updated."""
        config = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["old_col"]],
                "locked": [True],
            }
        )
        result = _update_unlocked_duplicates_cols(config, ["new_col"])
        assert result["column_name"].to_list()[0] == ["old_col"]

    def test_unlocked_exact_search_not_updated(self):
        """Unlocked exact search should not be re-evaluated (no pattern)."""
        config = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["col1"]],
                "locked": [False],
            }
        )
        result = _update_unlocked_duplicates_cols(config, ["col1", "col2"])
        assert result["column_name"].to_list()[0] == ["col1"]

    def test_unlocked_pattern_search_updated(self):
        """Unlocked pattern search should be re-evaluated."""
        config = pl.DataFrame(
            {
                "search_type": ["contains"],
                "pattern": ["age"],
                "column_name": [["age"]],
                "locked": [False],
            }
        )
        result = _update_unlocked_duplicates_cols(config, ["age", "age_group", "wage"])
        col_names = result["column_name"].to_list()[0]
        assert set(col_names) == {"age", "age_group", "wage"}


# ============================================
# BUILD FILTER EXPRESSION STRING-ONLY BRANCH
# ============================================


def test_build_filter_expression_string_only_condition():
    """Test _build_filter_expression with a string-only condition type (STARTWITH)."""
    condition = FilterCondition(
        condition_col="name",
        condition_type=StrCondition.STARTWITH.value,
        condition_value="Jo",
        missing_as_duplicates=False,
    )
    col_expr = pl.col("name")
    filter_expr = _build_filter_expression(condition, col_expr)

    data = pl.DataFrame({"name": ["John", "Jane", "Joe"]})
    result = data.filter(filter_expr)
    assert set(result["name"].to_list()) == {"John", "Joe"}


# ============================================
# FILTER DATA ON CONDITIONS - ERROR PATH
# ============================================


def test_filter_data_on_conditions_filter_error(monkeypatch):
    """Test _filter_data_on_conditions when filter application raises an error."""
    saved_data = []

    def mock_save(project_id, data, alias, db_name):
        saved_data.append(data)

    monkeypatch.setattr("datasure.checks.duplicates.duckdb_save_table", mock_save)

    # Use a condition type that will pass validation but fail on filter
    # by providing a string value for a numeric column with IN_RANGE
    data = pl.DataFrame({"age": [20, 25, 30]})
    conditions = {
        "condition_col": "age",
        "condition_type": NumCondition.IN_RANGE.value,
        "condition_value": ["not_a_number", "also_not"],
        "missing_as_duplicates": False,
    }

    with pytest.raises(ValueError, match="Error applying filter"):
        _filter_data_on_conditions("project1", data, conditions)


# ============================================
# HELPER FOR MOCKED ST CONTEXT MANAGER
# ============================================


def _make_mock_st():
    """Create a properly configured mock streamlit module."""
    mock_st = MagicMock()
    mock_ctx = MagicMock()
    mock_ctx.__enter__ = MagicMock(return_value=mock_ctx)
    mock_ctx.__exit__ = MagicMock(return_value=False)

    def _columns_side_effect(spec=None, **kwargs):
        if isinstance(spec, int):
            return [mock_ctx] * spec
        if isinstance(spec, list):
            return [mock_ctx] * len(spec)
        return [mock_ctx, mock_ctx, mock_ctx]

    mock_st.columns.side_effect = _columns_side_effect
    mock_st.container.return_value = mock_ctx
    mock_st.expander.return_value = mock_ctx
    mock_st.popover.return_value = mock_ctx
    return mock_st, mock_ctx


# ============================================
# RENDER OTHER DUPLICATES TABLE TESTS
# ============================================


class TestRenderOtherDuplicatesTable:
    """Tests for _render_other_duplicates_table."""

    @patch("datasure.checks.duplicates.save_check_settings")
    @patch("datasure.checks.duplicates.load_check_settings")
    @patch("datasure.checks.duplicates.compute_column_duplicates")
    @patch("datasure.checks.duplicates.st")
    def test_no_duplicates_shows_info(
        self, mock_st, mock_compute, mock_load, mock_save
    ):
        """When no duplicates found for column, should show info."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))
        mock_st.columns.return_value = [mock_ctx, mock_ctx]
        mock_st.selectbox.return_value = "age"
        mock_st.multiselect.return_value = []
        mock_load.return_value = {}
        mock_compute.return_value = pl.DataFrame(
            schema={
                "age": pl.Int64,
                "age_dup_count": pl.Int64,
                "age_dup_percent": pl.Float64,
            }
        )

        data = pl.DataFrame(
            {
                "survey_id": ["S001", "S002"],
                "age": [25, 30],
            }
        )
        settings = MagicMock()
        settings.survey_id = "survey_id"
        settings.survey_key = "survey_key"
        settings.survey_date = None

        _render_other_duplicates_table(data, ["age"], settings, "settings.json")
        mock_st.info.assert_called()

    @patch("datasure.checks.duplicates.save_check_settings")
    @patch("datasure.checks.duplicates.load_check_settings")
    @patch("datasure.checks.duplicates.compute_column_duplicates")
    @patch("datasure.checks.duplicates.st")
    def test_with_duplicates_no_extra_cols(
        self, mock_st, mock_compute, mock_load, mock_save
    ):
        """With duplicates and no extra columns, should show dataframe."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))
        mock_st.columns.return_value = [mock_ctx, mock_ctx]
        mock_st.selectbox.return_value = "age"
        mock_st.multiselect.return_value = []
        mock_load.return_value = {}
        mock_compute.return_value = pl.DataFrame(
            {
                "age": [25, 25],
                "age_dup_count": [2, 2],
                "age_dup_percent": [50.0, 50.0],
            }
        )

        data = pl.DataFrame({"survey_id": ["S001", "S002"], "age": [25, 25]})
        settings = MagicMock()
        settings.survey_id = "survey_id"
        settings.survey_key = "survey_key"
        settings.survey_date = None

        _render_other_duplicates_table(data, ["age"], settings, "settings.json")
        mock_st.dataframe.assert_called_once()

    @patch("datasure.checks.duplicates.save_check_settings")
    @patch("datasure.checks.duplicates.load_check_settings")
    @patch("datasure.checks.duplicates.compute_column_duplicates")
    @patch("datasure.checks.duplicates.st")
    def test_with_extra_cols_and_join(
        self, mock_st, mock_compute, mock_load, mock_save
    ):
        """With extra display columns and valid join keys."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))
        mock_st.columns.return_value = [mock_ctx, mock_ctx]
        mock_st.selectbox.return_value = "age"
        mock_st.multiselect.return_value = ["income"]
        mock_load.return_value = {}
        mock_compute.return_value = pl.DataFrame(
            {
                "survey_id": ["S001"],
                "age": [25],
                "age_dup_count": [2],
                "age_dup_percent": [50.0],
            }
        )

        data = pl.DataFrame(
            {
                "survey_id": ["S001", "S002"],
                "age": [25, 25],
                "income": [50000, 60000],
            }
        )
        settings = MagicMock()
        settings.survey_id = "survey_id"
        settings.survey_key = None
        settings.survey_date = None

        _render_other_duplicates_table(data, ["age"], settings, "settings.json")
        mock_st.dataframe.assert_called_once()

    @patch("datasure.checks.duplicates.save_check_settings")
    @patch("datasure.checks.duplicates.load_check_settings")
    @patch("datasure.checks.duplicates.compute_column_duplicates")
    @patch("datasure.checks.duplicates.st")
    def test_with_extra_cols_no_join_keys(
        self, mock_st, mock_compute, mock_load, mock_save
    ):
        """With extra display columns but no matching join keys."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))
        mock_st.columns.return_value = [mock_ctx, mock_ctx]
        mock_st.selectbox.return_value = "age"
        mock_st.multiselect.return_value = ["income"]
        mock_load.return_value = {}
        mock_compute.return_value = pl.DataFrame(
            {
                "age": [25],
                "age_dup_count": [2],
                "age_dup_percent": [50.0],
            }
        )

        data = pl.DataFrame(
            {
                "other_id": ["S001"],
                "age": [25],
                "income": [50000],
            }
        )
        settings = MagicMock()
        settings.survey_id = "missing_id"
        settings.survey_key = "missing_key"
        settings.survey_date = None

        _render_other_duplicates_table(data, ["age"], settings, "settings.json")
        mock_st.warning.assert_called_once()


# ============================================
# DELETE DUPLICATES COLUMN TESTS
# ============================================


class TestDeleteDuplicatesColumn:
    """Tests for _delete_duplicates_column."""

    @patch("datasure.checks.duplicates.st")
    def test_empty_settings(self, mock_st):
        """With empty settings, should show info message."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))

        empty_settings = pl.DataFrame(
            schema={
                "search_type": pl.Utf8,
                "pattern": pl.Utf8,
                "column_name": pl.List(pl.Utf8),
                "locked": pl.Boolean,
            }
        )

        _delete_duplicates_column("project1", "page1", empty_settings)
        mock_st.info.assert_called_once()

    @patch("datasure.checks.duplicates.duckdb_save_table")
    @patch("datasure.checks.duplicates.st")
    def test_with_settings_no_confirm(self, mock_st, mock_save):
        """With settings but no confirm click."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))
        mock_st.selectbox.return_value = "0 - exact - "
        mock_st.button.return_value = False

        settings = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["age"]],
                "locked": [False],
            }
        )

        _delete_duplicates_column("project1", "page1", settings)
        mock_save.assert_not_called()

    @patch("datasure.checks.duplicates.duckdb_save_table")
    @patch("datasure.checks.duplicates.st")
    def test_with_confirm_delete(self, mock_st, mock_save):
        """With confirm delete, should save updated settings and rerun."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))
        mock_st.selectbox.return_value = "0 - exact - "
        mock_st.button.return_value = True

        settings = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["age"]],
                "locked": [False],
            }
        )

        _delete_duplicates_column("project1", "page1", settings)
        mock_save.assert_called_once()
        mock_st.rerun.assert_called_once()

    @patch("datasure.checks.duplicates.st")
    def test_no_selected_index(self, mock_st):
        """When selectbox returns None, should not show confirm button."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))
        mock_st.selectbox.return_value = None

        settings = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["age"]],
                "locked": [False],
            }
        )

        _delete_duplicates_column("project1", "page1", settings)
        # button for confirm should not be called since selected_index is None
        mock_st.button.assert_not_called()


# ============================================
# RENDER DUPLICATES COLUMN ACTIONS TESTS
# ============================================


class TestRenderDuplicatesColumnActions:
    """Tests for _render_duplicates_column_actions."""

    @patch("datasure.checks.duplicates._render_duplicates_settings_table")
    @patch("datasure.checks.duplicates._delete_duplicates_column")
    @patch("datasure.checks.duplicates.duckdb_get_table")
    @patch("datasure.checks.duplicates.st")
    def test_empty_settings_shows_info(
        self, mock_st, mock_get, mock_delete, mock_render
    ):
        """When no duplicates settings exist, should show info message."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))
        mock_get.return_value = pl.DataFrame()

        _render_duplicates_column_actions("project1", "page1", ["age", "income"])
        mock_st.info.assert_called_once()

    @patch("datasure.checks.duplicates._render_duplicates_settings_table")
    @patch("datasure.checks.duplicates._delete_duplicates_column")
    @patch("datasure.checks.duplicates.duckdb_get_table")
    @patch("datasure.checks.duplicates.st")
    def test_with_settings_renders_table(
        self, mock_st, mock_get, mock_delete, mock_render
    ):
        """When settings exist, should render the settings table."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))

        settings_df = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["age"]],
                "locked": [False],
            }
        )
        mock_get.return_value = settings_df

        _render_duplicates_column_actions("project1", "page1", ["age", "income"])
        mock_render.assert_called_once_with(settings_df)


# ============================================
# RENDER SEARCH TYPE SELECTION TESTS
# ============================================


class TestRenderSearchTypeSelection:
    """Tests for _render_search_type_selection."""

    @patch("datasure.checks.duplicates._create_search_type_info")
    @patch("datasure.checks.duplicates.st")
    def test_exact_search_type(self, mock_st, mock_info):
        """Exact search should return multiselect columns."""
        mock_st.selectbox.return_value = SearchType.EXACT.value
        mock_st.multiselect.return_value = ["age", "income"]

        search_type, pattern, dup_cols, lock_cols = _render_search_type_selection(
            ["age", "income", "gender"]
        )
        assert search_type == SearchType.EXACT.value
        assert pattern is None
        assert dup_cols == ["age", "income"]
        assert lock_cols is None

    @patch("datasure.checks.duplicates.expand_col_names")
    @patch("datasure.checks.duplicates._create_search_type_info")
    @patch("datasure.checks.duplicates.st")
    def test_startswith_with_pattern(self, mock_st, mock_info, mock_expand):
        """Non-exact search with pattern should expand column names."""
        mock_st.selectbox.return_value = SearchType.STARTSWITH.value
        mock_st.text_input.return_value = "inc"
        mock_expand.return_value = ["income", "income_total"]

        search_type, pattern, dup_cols, lock_cols = _render_search_type_selection(
            ["age", "income", "income_total"]
        )
        assert search_type == SearchType.STARTSWITH.value
        assert pattern == "inc"
        assert dup_cols == ["income", "income_total"]
        assert lock_cols is None

    @patch("datasure.checks.duplicates._create_search_type_info")
    @patch("datasure.checks.duplicates.st")
    def test_startswith_without_pattern(self, mock_st, mock_info):
        """Non-exact search without pattern should return empty columns."""
        mock_st.selectbox.return_value = SearchType.STARTSWITH.value
        mock_st.text_input.return_value = ""

        search_type, pattern, dup_cols, lock_cols = _render_search_type_selection(
            ["age", "income"]
        )
        assert dup_cols == []


# ============================================
# DUPLICATES REPORT SETTINGS TESTS
# ============================================


class TestDuplicatesReportSettings:
    """Tests for duplicates_report_settings."""

    @patch("datasure.checks.duplicates._filter_data_on_conditions")
    @patch("datasure.checks.duplicates._render_duplicates_condition_options")
    @patch("datasure.checks.duplicates.save_check_settings")
    @patch("datasure.checks.duplicates.load_default_duplicates_settings")
    @patch("datasure.checks.duplicates.st")
    def test_basic_settings(
        self, mock_st, mock_load_default, mock_save, mock_render_cond, mock_filter
    ):
        """Test basic duplicates report settings UI."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))

        mock_load_default.return_value = DuplicatesSettings(
            survey_key="survey_key",
            survey_id="survey_id",
            survey_date="survey_date",
            enumerator="enumerator",
        )
        mock_st.selectbox.return_value = "survey_key"
        mock_render_cond.return_value = {}

        data = pl.DataFrame({"survey_id": ["S001"], "age": [25]})
        config = DuplicatesSettings(survey_id="survey_id")
        cat_cols = ["survey_key", "survey_id", "enumerator"]
        dt_cols = ["survey_date"]

        result = duplicates_report_settings(
            "project1", "settings.json", data, config, cat_cols, dt_cols
        )
        assert isinstance(result, DuplicatesSettings)

    @patch("datasure.checks.duplicates._filter_data_on_conditions")
    @patch("datasure.checks.duplicates._render_duplicates_condition_options")
    @patch("datasure.checks.duplicates.save_check_settings")
    @patch("datasure.checks.duplicates.load_default_duplicates_settings")
    @patch("datasure.checks.duplicates.st")
    def test_settings_with_defaults_in_columns(
        self, mock_st, mock_load_default, mock_save, mock_render_cond, mock_filter
    ):
        """Test settings when default values are found in column lists."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))

        mock_load_default.return_value = DuplicatesSettings(
            survey_key="survey_key",
            survey_id="survey_id",
            survey_date="survey_date",
            enumerator="enumerator",
        )
        mock_st.selectbox.return_value = "survey_id"
        mock_render_cond.return_value = {"condition_col": "age"}

        data = pl.DataFrame({"survey_id": ["S001"]})
        config = DuplicatesSettings(survey_id="survey_id")
        cat_cols = ["survey_key", "survey_id", "enumerator"]
        dt_cols = ["survey_date"]

        result = duplicates_report_settings(
            "project1", "settings.json", data, config, cat_cols, dt_cols
        )
        assert result.conditions == {"condition_col": "age"}


# ============================================
# DUPLICATES REPORT MAIN FUNCTION TESTS
# ============================================


class TestDuplicatesReport:
    """Tests for duplicates_report main function."""

    @patch("datasure.checks.duplicates._render_other_duplicates_table")
    @patch("datasure.checks.duplicates._render_other_duplicates_metrics")
    @patch("datasure.checks.duplicates._update_unlocked_duplicates_cols")
    @patch("datasure.checks.duplicates._render_duplicates_column_actions")
    @patch("datasure.checks.duplicates._render_id_duplicates_table")
    @patch("datasure.checks.duplicates._render_id_duplicates_metrics")
    @patch("datasure.checks.duplicates.compute_id_duplicates")
    @patch("datasure.checks.duplicates.duckdb_save_table")
    @patch("datasure.checks.duplicates.duckdb_get_table")
    @patch("datasure.checks.duplicates.duplicates_report_settings")
    @patch("datasure.checks.duplicates.st")
    def test_full_report_empty_config(
        self,
        mock_st,
        mock_report_settings,
        mock_get,
        mock_save,
        mock_compute_id,
        mock_render_id_metrics,
        mock_render_id_table,
        mock_render_col_actions,
        mock_update_unlocked,
        mock_render_other_metrics,
        mock_render_other_table,
    ):
        """Test duplicates report when column config is empty."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))

        settings = DuplicatesSettings(
            survey_id="survey_id",
            survey_key="survey_key",
            survey_date="survey_date",
        )
        mock_report_settings.return_value = settings

        # First call: filtered_duplicates_data (empty)
        # Second call: duplicates_column_actions loads config
        # Third call: duplicates_column_config (empty)
        mock_get.side_effect = [pl.DataFrame(), pl.DataFrame()]
        mock_compute_id.return_value = pl.DataFrame()

        data = pl.DataFrame(
            {
                "survey_id": ["S001"],
                "survey_key": ["K001"],
                "survey_date": [datetime.date(2024, 1, 1)],
                "age": [25],
            }
        )

        from datasure.utils.dataframe_utils import ColumnByType

        survey_columns = ColumnByType(
            categorical_columns=["survey_key", "survey_id"],
            datetime_columns=["survey_date"],
        )

        duplicates_report(
            "project1",
            "page1",
            data,
            "settings.json",
            {"survey_id": "survey_id"},
            survey_columns,
        )

        # Should return early since column config is empty
        mock_render_other_metrics.assert_not_called()

    @patch("datasure.checks.duplicates._render_other_duplicates_table")
    @patch("datasure.checks.duplicates._render_other_duplicates_metrics")
    @patch("datasure.checks.duplicates._update_unlocked_duplicates_cols")
    @patch("datasure.checks.duplicates._render_duplicates_column_actions")
    @patch("datasure.checks.duplicates._render_id_duplicates_table")
    @patch("datasure.checks.duplicates._render_id_duplicates_metrics")
    @patch("datasure.checks.duplicates.compute_id_duplicates")
    @patch("datasure.checks.duplicates.duckdb_save_table")
    @patch("datasure.checks.duplicates.duckdb_get_table")
    @patch("datasure.checks.duplicates.duplicates_report_settings")
    @patch("datasure.checks.duplicates.st")
    def test_full_report_with_config(
        self,
        mock_st,
        mock_report_settings,
        mock_get,
        mock_save,
        mock_compute_id,
        mock_render_id_metrics,
        mock_render_id_table,
        mock_render_col_actions,
        mock_update_unlocked,
        mock_render_other_metrics,
        mock_render_other_table,
    ):
        """Test full duplicates report with column configuration."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))

        settings = DuplicatesSettings(
            survey_id="survey_id",
            survey_key="survey_key",
            survey_date="survey_date",
        )
        mock_report_settings.return_value = settings

        config_df = pl.DataFrame(
            {
                "search_type": ["exact"],
                "pattern": [None],
                "column_name": [["age", "income"]],
                "locked": [True],
            }
        )
        mock_update_unlocked.return_value = config_df

        # filtered_duplicates_data (non-empty), duplicates_column_config
        filtered = pl.DataFrame(
            {
                "survey_id": ["S001"],
                "survey_key": ["K001"],
                "survey_date": [datetime.date(2024, 1, 1)],
                "age": [25],
                "income": [50000],
            }
        )
        mock_get.side_effect = [filtered, config_df]
        mock_compute_id.return_value = pl.DataFrame()

        data = pl.DataFrame(
            {
                "survey_id": ["S001", "S002"],
                "survey_key": ["K001", "K002"],
                "survey_date": [datetime.date(2024, 1, 1), datetime.date(2024, 1, 2)],
                "age": [25, 30],
                "income": [50000, 60000],
            }
        )

        from datasure.utils.dataframe_utils import ColumnByType

        survey_columns = ColumnByType(
            categorical_columns=["survey_key", "survey_id"],
            datetime_columns=["survey_date"],
        )

        duplicates_report(
            "project1",
            "page1",
            data,
            "settings.json",
            {"survey_id": "survey_id"},
            survey_columns,
        )

        mock_render_other_metrics.assert_called_once()
        mock_render_other_table.assert_called_once()

    @patch("datasure.checks.duplicates._render_other_duplicates_table")
    @patch("datasure.checks.duplicates._render_other_duplicates_metrics")
    @patch("datasure.checks.duplicates._update_unlocked_duplicates_cols")
    @patch("datasure.checks.duplicates._render_duplicates_column_actions")
    @patch("datasure.checks.duplicates._render_id_duplicates_table")
    @patch("datasure.checks.duplicates._render_id_duplicates_metrics")
    @patch("datasure.checks.duplicates.compute_id_duplicates")
    @patch("datasure.checks.duplicates.duckdb_save_table")
    @patch("datasure.checks.duplicates.duckdb_get_table")
    @patch("datasure.checks.duplicates.duplicates_report_settings")
    @patch("datasure.checks.duplicates.st")
    def test_report_removes_survey_id_key_from_columns(
        self,
        mock_st,
        mock_report_settings,
        mock_get,
        mock_save,
        mock_compute_id,
        mock_render_id_metrics,
        mock_render_id_table,
        mock_render_col_actions,
        mock_update_unlocked,
        mock_render_other_metrics,
        mock_render_other_table,
    ):
        """Test that survey_id and key are removed from other columns list."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))

        settings = DuplicatesSettings(
            survey_id="survey_id",
            survey_key="survey_key",
        )
        mock_report_settings.return_value = settings
        mock_get.side_effect = [pl.DataFrame(), pl.DataFrame()]
        mock_compute_id.return_value = pl.DataFrame()

        data = pl.DataFrame(
            {
                "survey_id": ["S001"],
                "survey_key": ["K001"],
                "age": [25],
            }
        )

        from datasure.utils.dataframe_utils import ColumnByType

        survey_columns = ColumnByType(
            categorical_columns=["survey_key", "survey_id"],
            datetime_columns=[],
        )

        duplicates_report(
            "project1",
            "page1",
            data,
            "settings.json",
            {"survey_id": "survey_id"},
            survey_columns,
        )

        # _render_duplicates_column_actions should be called with
        # columns that exclude survey_id and survey_key
        call_args = mock_render_col_actions.call_args
        all_columns = call_args[0][2]
        assert "survey_id" not in all_columns
        assert "survey_key" not in all_columns

    @patch("datasure.checks.duplicates._render_other_duplicates_table")
    @patch("datasure.checks.duplicates._render_other_duplicates_metrics")
    @patch("datasure.checks.duplicates._update_unlocked_duplicates_cols")
    @patch("datasure.checks.duplicates._render_duplicates_column_actions")
    @patch("datasure.checks.duplicates._render_id_duplicates_table")
    @patch("datasure.checks.duplicates._render_id_duplicates_metrics")
    @patch("datasure.checks.duplicates.compute_id_duplicates")
    @patch("datasure.checks.duplicates.duckdb_save_table")
    @patch("datasure.checks.duplicates.duckdb_get_table")
    @patch("datasure.checks.duplicates.duplicates_report_settings")
    @patch("datasure.checks.duplicates.st")
    def test_report_only_key_in_columns(
        self,
        mock_st,
        mock_report_settings,
        mock_get,
        mock_save,
        mock_compute_id,
        mock_render_id_metrics,
        mock_render_id_table,
        mock_render_col_actions,
        mock_update_unlocked,
        mock_render_other_metrics,
        mock_render_other_table,
    ):
        """Test when survey_id is not set, only key is removed from columns."""
        mock_st_obj, mock_ctx = _make_mock_st()
        for attr in dir(mock_st_obj):
            if not attr.startswith("_"):
                setattr(mock_st, attr, getattr(mock_st_obj, attr))

        settings = DuplicatesSettings(
            survey_id=None,
            survey_key="survey_key",
        )
        mock_report_settings.return_value = settings
        mock_get.side_effect = [pl.DataFrame(), pl.DataFrame()]
        mock_compute_id.return_value = pl.DataFrame()

        data = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "age": [25],
            }
        )

        from datasure.utils.dataframe_utils import ColumnByType

        survey_columns = ColumnByType(
            categorical_columns=["survey_key"],
            datetime_columns=[],
        )

        duplicates_report(
            "project1",
            "page1",
            data,
            "settings.json",
            {"survey_id": None, "survey_key": "survey_key"},
            survey_columns,
        )

        call_args = mock_render_col_actions.call_args
        all_columns = call_args[0][2]
        assert "survey_key" not in all_columns
