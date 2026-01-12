"""Tests for duplicates module.

This module tests the refactored duplicate detection system using Polars DataFrames
and Pydantic models for validation and configuration.
"""

import datetime
import json

import polars as pl
import pytest
from pydantic import ValidationError

from datasure.checks.duplicates import (
    TAB_NAME,
    DateDefaults,
    DuplicatesColumnConfig,
    DuplicatesSettings,
    DuplicatesStats,
    FilterCondition,
    NumCondition,
    SearchType,
    StrCondition,
    _apply_numeric_condition,
    _apply_string_condition,
    _build_filter_expression,
    _ensure_duplicates_column_formats,
    _filter_data_on_conditions,
    _serialize_condition_value_for_json,
    _update_duplicates_column_config,
    _update_unlocked_duplicates_cols,
    _validate_duplicates_condition_date_value,
    compute_column_duplicates,
    compute_duplicates_statistics,
    compute_id_duplicates,
    expand_col_names,
    load_default_duplicates_settings,
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
