"""Unit tests for datasure.models.schemas module.

Tests all Pydantic model classes: DuplicatesColumnConfig, DuplicatesStats,
FilterCondition, DuplicatesSettings, and DateDefaults, including field
validation, default values, and error handling.
"""

import datetime

import polars as pl
import pytest
from pydantic import ValidationError

from datasure.models.enums import (
    DelimiterType,
    GPSFormatType,
    NumCondition,
    SearchType,
    StrCondition,
)
from datasure.models.schemas import (
    BackcheckColumnSelectors,
    CheckConfiguration,
    DateDefaults,
    DuplicatesColumnConfig,
    DuplicatesSettings,
    DuplicatesStats,
    FilterCondition,
    GPSColumnConfig,
    GPSSettings,
    SurveyColumnSelections,
)

# ── DuplicatesColumnConfig ───────────────────────────────────────────


class TestDuplicatesColumnConfig:
    """Tests for the DuplicatesColumnConfig Pydantic model."""

    def test_valid_exact_search_no_pattern(self):
        """Create config with EXACT search type and no pattern succeeds."""
        config = DuplicatesColumnConfig(
            search_type=SearchType.EXACT,
            dup_cols=["col_a"],
        )
        assert config.search_type == SearchType.EXACT
        assert config.pattern is None
        assert config.dup_cols == ["col_a"]
        assert config.lock_cols is False

    def test_valid_exact_search_with_pattern(self):
        """Create config with EXACT search type and an optional pattern succeeds."""
        config = DuplicatesColumnConfig(
            search_type=SearchType.EXACT,
            pattern="some_pattern",
            dup_cols=["col_a"],
        )
        assert config.pattern == "some_pattern"

    def test_valid_startswith_search_with_pattern(self):
        """Create config with STARTSWITH search type and a pattern succeeds."""
        config = DuplicatesColumnConfig(
            search_type=SearchType.STARTSWITH,
            pattern="prefix_",
            dup_cols=["col_a", "col_b"],
        )
        assert config.search_type == SearchType.STARTSWITH
        assert config.pattern == "prefix_"

    def test_valid_endswith_search_with_pattern(self):
        """Create config with ENDSWITH search type and a pattern succeeds."""
        config = DuplicatesColumnConfig(
            search_type=SearchType.ENDSWITH,
            pattern="_suffix",
            dup_cols=["col_x"],
        )
        assert config.search_type == SearchType.ENDSWITH
        assert config.pattern == "_suffix"

    def test_valid_contains_search_with_pattern(self):
        """Create config with CONTAINS search type and a pattern succeeds."""
        config = DuplicatesColumnConfig(
            search_type=SearchType.CONTAINS,
            pattern="mid",
            dup_cols=["col_1"],
        )
        assert config.search_type == SearchType.CONTAINS
        assert config.pattern == "mid"

    def test_valid_regex_search_with_pattern(self):
        """Create config with REGEX search type and a pattern succeeds."""
        config = DuplicatesColumnConfig(
            search_type=SearchType.REGEX,
            pattern=r"^col_\d+$",
            dup_cols=["col_1"],
        )
        assert config.search_type == SearchType.REGEX
        assert config.pattern == r"^col_\d+$"

    def test_lock_cols_true(self):
        """Create config with lock_cols set to True succeeds."""
        config = DuplicatesColumnConfig(
            search_type=SearchType.EXACT,
            dup_cols=["col_a"],
            lock_cols=True,
        )
        assert config.lock_cols is True

    def test_multiple_dup_cols(self):
        """Create config with multiple duplicate columns succeeds."""
        cols = ["col_a", "col_b", "col_c", "col_d"]
        config = DuplicatesColumnConfig(
            search_type=SearchType.EXACT,
            dup_cols=cols,
        )
        assert config.dup_cols == cols
        assert len(config.dup_cols) == 4

    def test_non_exact_search_with_explicit_none_raises(self):
        """Non-exact search with explicit pattern=None raises ValidationError."""
        with pytest.raises(ValidationError, match="Pattern is required"):
            DuplicatesColumnConfig(
                search_type=SearchType.STARTSWITH,
                pattern=None,
                dup_cols=["col_a"],
            )

    def test_contains_search_with_explicit_none_raises(self):
        """CONTAINS search with explicit pattern=None raises ValidationError."""
        with pytest.raises(ValidationError, match="Pattern is required"):
            DuplicatesColumnConfig(
                search_type=SearchType.CONTAINS,
                pattern=None,
                dup_cols=["col_a"],
            )

    def test_regex_search_with_explicit_none_raises(self):
        """REGEX search with explicit pattern=None raises ValidationError."""
        with pytest.raises(ValidationError, match="Pattern is required"):
            DuplicatesColumnConfig(
                search_type=SearchType.REGEX,
                pattern=None,
                dup_cols=["col_a"],
            )

    def test_endswith_search_with_explicit_none_raises(self):
        """ENDSWITH search with explicit pattern=None raises ValidationError."""
        with pytest.raises(ValidationError, match="Pattern is required"):
            DuplicatesColumnConfig(
                search_type=SearchType.ENDSWITH,
                pattern=None,
                dup_cols=["col_a"],
            )

    def test_non_exact_search_without_pattern_uses_default(self):
        """Non-exact search without explicit pattern uses default None."""
        config = DuplicatesColumnConfig(
            search_type=SearchType.STARTSWITH,
            dup_cols=["col_a"],
        )
        assert config.pattern is None

    def test_empty_dup_cols_raises(self):
        """Empty dup_cols list raises ValidationError due to min_length=1."""
        with pytest.raises(ValidationError):
            DuplicatesColumnConfig(
                search_type=SearchType.EXACT,
                dup_cols=[],
            )

    def test_missing_dup_cols_raises(self):
        """Missing dup_cols field raises ValidationError."""
        with pytest.raises(ValidationError):
            DuplicatesColumnConfig(
                search_type=SearchType.EXACT,
            )

    def test_missing_search_type_raises(self):
        """Missing search_type field raises ValidationError."""
        with pytest.raises(ValidationError):
            DuplicatesColumnConfig(
                dup_cols=["col_a"],
            )

    def test_non_exact_with_empty_string_pattern_raises(self):
        """Non-exact search type with empty string pattern raises ValidationError."""
        with pytest.raises(ValidationError, match="Pattern is required"):
            DuplicatesColumnConfig(
                search_type=SearchType.STARTSWITH,
                pattern="",
                dup_cols=["col_a"],
            )


# ── DuplicatesStats ──────────────────────────────────────────────────


class TestDuplicatesStats:
    """Tests for the DuplicatesStats Pydantic model."""

    def test_valid_stats(self):
        """Create valid stats with all non-negative integers succeeds."""
        stats = DuplicatesStats(
            number_of_columns_checked=10,
            total_duplicates=5,
            number_of_cols_with_duplicates=3,
            number_of_cols_without_duplicates=7,
        )
        assert stats.number_of_columns_checked == 10
        assert stats.total_duplicates == 5
        assert stats.number_of_cols_with_duplicates == 3
        assert stats.number_of_cols_without_duplicates == 7

    def test_all_zero_stats(self):
        """Create stats with all zero values succeeds (boundary for ge=0)."""
        stats = DuplicatesStats(
            number_of_columns_checked=0,
            total_duplicates=0,
            number_of_cols_with_duplicates=0,
            number_of_cols_without_duplicates=0,
        )
        assert stats.number_of_columns_checked == 0
        assert stats.total_duplicates == 0

    def test_large_values(self):
        """Create stats with large integer values succeeds."""
        stats = DuplicatesStats(
            number_of_columns_checked=1_000_000,
            total_duplicates=500_000,
            number_of_cols_with_duplicates=250_000,
            number_of_cols_without_duplicates=750_000,
        )
        assert stats.number_of_columns_checked == 1_000_000

    def test_negative_columns_checked_raises(self):
        """Negative number_of_columns_checked raises ValidationError (ge=0)."""
        with pytest.raises(ValidationError):
            DuplicatesStats(
                number_of_columns_checked=-1,
                total_duplicates=0,
                number_of_cols_with_duplicates=0,
                number_of_cols_without_duplicates=0,
            )

    def test_negative_total_duplicates_raises(self):
        """Negative total_duplicates raises ValidationError (ge=0)."""
        with pytest.raises(ValidationError):
            DuplicatesStats(
                number_of_columns_checked=10,
                total_duplicates=-5,
                number_of_cols_with_duplicates=0,
                number_of_cols_without_duplicates=10,
            )

    def test_negative_cols_with_duplicates_raises(self):
        """Negative number_of_cols_with_duplicates raises ValidationError."""
        with pytest.raises(ValidationError):
            DuplicatesStats(
                number_of_columns_checked=10,
                total_duplicates=0,
                number_of_cols_with_duplicates=-1,
                number_of_cols_without_duplicates=10,
            )

    def test_negative_cols_without_duplicates_raises(self):
        """Negative number_of_cols_without_duplicates raises ValidationError."""
        with pytest.raises(ValidationError):
            DuplicatesStats(
                number_of_columns_checked=10,
                total_duplicates=0,
                number_of_cols_with_duplicates=0,
                number_of_cols_without_duplicates=-1,
            )

    def test_missing_required_field_raises(self):
        """Missing a required field raises ValidationError."""
        with pytest.raises(ValidationError):
            DuplicatesStats(
                number_of_columns_checked=10,
                total_duplicates=5,
                # missing number_of_cols_with_duplicates
                number_of_cols_without_duplicates=5,
            )


# ── FilterCondition ──────────────────────────────────────────────────


class TestFilterCondition:
    """Tests for the FilterCondition Pydantic model."""

    def test_valid_numeric_equals(self):
        """Create FilterCondition with numeric EQUALS condition succeeds."""
        fc = FilterCondition(
            condition_col="age",
            condition_type=NumCondition.EQUALS.value,
            condition_value=25,
        )
        assert fc.condition_col == "age"
        assert fc.condition_type == "Value is equal"
        assert fc.condition_value == 25
        assert fc.missing_as_duplicates is False

    def test_valid_string_equals(self):
        """Create FilterCondition with string EQUALS condition succeeds."""
        fc = FilterCondition(
            condition_col="name",
            condition_type=StrCondition.EQUALS.value,
            condition_value="Alice",
        )
        assert fc.condition_value == "Alice"

    def test_valid_in_range_with_tuple(self):
        """Create FilterCondition with IN_RANGE and a 2-element tuple succeeds."""
        fc = FilterCondition(
            condition_col="score",
            condition_type=NumCondition.IN_RANGE.value,
            condition_value=(10, 100),
        )
        assert fc.condition_value == (10, 100)

    def test_valid_in_range_with_list(self):
        """Create FilterCondition with IN_RANGE and a 2-element list succeeds."""
        fc = FilterCondition(
            condition_col="score",
            condition_type=NumCondition.IN_RANGE.value,
            condition_value=[10, 100],
        )
        assert fc.condition_value == [10, 100]

    def test_valid_num_includes_with_list(self):
        """Create FilterCondition with numeric INCLUDES and a list succeeds."""
        fc = FilterCondition(
            condition_col="category",
            condition_type=NumCondition.INCLUDES.value,
            condition_value=[1, 2, 3],
        )
        assert fc.condition_value == [1, 2, 3]

    def test_valid_str_includes_with_tuple(self):
        """Create FilterCondition with string INCLUDES and a tuple succeeds."""
        fc = FilterCondition(
            condition_col="status",
            condition_type=StrCondition.INCLUDES.value,
            condition_value=("active", "pending"),
        )
        assert fc.condition_value == ("active", "pending")

    def test_valid_str_includes_with_set(self):
        """Create FilterCondition with string INCLUDES and a set succeeds."""
        fc = FilterCondition(
            condition_col="status",
            condition_type=StrCondition.INCLUDES.value,
            condition_value={"active", "pending"},
        )
        # Pydantic may coerce set to list; verify it's a collection
        assert isinstance(fc.condition_value, list | tuple | set)

    def test_valid_with_date_value(self):
        """Create FilterCondition with a date condition_value succeeds."""
        d = datetime.date(2024, 6, 15)
        fc = FilterCondition(
            condition_col="survey_date",
            condition_type=NumCondition.EQUALS.value,
            condition_value=d,
        )
        assert fc.condition_value == d

    def test_valid_with_none_value(self):
        """Create FilterCondition with None condition_value succeeds."""
        fc = FilterCondition(
            condition_col="col",
            condition_type=NumCondition.EQUALS.value,
            condition_value=None,
        )
        assert fc.condition_value is None

    def test_missing_as_duplicates_true(self):
        """Create FilterCondition with missing_as_duplicates=True succeeds."""
        fc = FilterCondition(
            condition_col="col",
            condition_type=NumCondition.EQUALS.value,
            condition_value=1,
            missing_as_duplicates=True,
        )
        assert fc.missing_as_duplicates is True

    def test_in_range_with_single_value_raises(self):
        """IN_RANGE with a scalar value raises ValidationError."""
        with pytest.raises(ValidationError, match="requires a tuple/list of 2 values"):
            FilterCondition(
                condition_col="score",
                condition_type=NumCondition.IN_RANGE.value,
                condition_value=50,
            )

    def test_in_range_with_three_element_list_raises(self):
        """IN_RANGE with a 3-element list raises ValidationError."""
        with pytest.raises(ValidationError, match="requires a tuple/list of 2 values"):
            FilterCondition(
                condition_col="score",
                condition_type=NumCondition.IN_RANGE.value,
                condition_value=[10, 50, 100],
            )

    def test_in_range_with_one_element_list_raises(self):
        """IN_RANGE with a 1-element list raises ValidationError."""
        with pytest.raises(ValidationError, match="requires a tuple/list of 2 values"):
            FilterCondition(
                condition_col="score",
                condition_type=NumCondition.IN_RANGE.value,
                condition_value=[10],
            )

    def test_in_range_with_string_raises(self):
        """IN_RANGE with a string value raises ValidationError."""
        with pytest.raises(ValidationError, match="requires a tuple/list of 2 values"):
            FilterCondition(
                condition_col="score",
                condition_type=NumCondition.IN_RANGE.value,
                condition_value="invalid",
            )

    def test_num_includes_with_scalar_raises(self):
        """Numeric INCLUDES with a scalar value raises ValidationError."""
        with pytest.raises(
            ValidationError, match="requires a list/tuple/set of values"
        ):
            FilterCondition(
                condition_col="category",
                condition_type=NumCondition.INCLUDES.value,
                condition_value=42,
            )

    def test_str_includes_with_scalar_raises(self):
        """String INCLUDES with a scalar string raises ValidationError."""
        with pytest.raises(
            ValidationError, match="requires a list/tuple/set of values"
        ):
            FilterCondition(
                condition_col="status",
                condition_type=StrCondition.INCLUDES.value,
                condition_value="active",
            )

    def test_empty_condition_col_raises(self):
        """Empty condition_col raises ValidationError (min_length=1)."""
        with pytest.raises(ValidationError):
            FilterCondition(
                condition_col="",
                condition_type=NumCondition.EQUALS.value,
                condition_value=1,
            )

    def test_missing_condition_col_raises(self):
        """Missing condition_col raises ValidationError."""
        with pytest.raises(ValidationError):
            FilterCondition(
                condition_type=NumCondition.EQUALS.value,
                condition_value=1,
            )

    def test_missing_condition_type_raises(self):
        """Missing condition_type raises ValidationError."""
        with pytest.raises(ValidationError):
            FilterCondition(
                condition_col="col",
                condition_value=1,
            )

    def test_float_condition_value(self):
        """Create FilterCondition with a float condition_value succeeds."""
        fc = FilterCondition(
            condition_col="weight",
            condition_type=NumCondition.GREATER_THAN.value,
            condition_value=3.14,
        )
        assert fc.condition_value == 3.14

    def test_greater_than_condition(self):
        """Create FilterCondition with GREATER_THAN condition succeeds."""
        fc = FilterCondition(
            condition_col="age",
            condition_type=NumCondition.GREATER_THAN.value,
            condition_value=18,
        )
        assert fc.condition_type == NumCondition.GREATER_THAN.value

    def test_not_equals_condition(self):
        """Create FilterCondition with NOT_EQUALS condition succeeds."""
        fc = FilterCondition(
            condition_col="status",
            condition_type=StrCondition.NOT_EQUALS.value,
            condition_value="inactive",
        )
        assert fc.condition_type == StrCondition.NOT_EQUALS.value


# ── DuplicatesSettings ───────────────────────────────────────────────


class TestDuplicatesSettings:
    """Tests for the DuplicatesSettings Pydantic model."""

    def test_valid_minimal(self):
        """Create DuplicatesSettings with only required survey_id succeeds."""
        settings = DuplicatesSettings(survey_id="survey_id_col")
        assert settings.survey_id == "survey_id_col"
        assert settings.filtered_data is None
        assert settings.survey_key is None
        assert settings.survey_date is None
        assert settings.enumerator is None
        assert settings.conditions == {}

    def test_valid_all_fields(self):
        """Create DuplicatesSettings with all fields populated succeeds."""
        df = pl.DataFrame({"a": [1, 2], "b": [3, 4]})
        settings = DuplicatesSettings(
            filtered_data=df,
            survey_key="key_col",
            survey_id="id_col",
            survey_date="date_col",
            enumerator="enum_col",
            conditions={"col_a": {"type": "exact"}},
        )
        assert settings.filtered_data is not None
        assert settings.filtered_data.shape == (2, 2)
        assert settings.survey_key == "key_col"
        assert settings.survey_date == "date_col"
        assert settings.enumerator == "enum_col"
        assert settings.conditions == {"col_a": {"type": "exact"}}

    def test_polars_dataframe_accepted(self):
        """Polars DataFrame is accepted via arbitrary_types_allowed."""
        df = pl.DataFrame({"x": [10, 20, 30]})
        settings = DuplicatesSettings(
            filtered_data=df,
            survey_id="sid",
        )
        assert isinstance(settings.filtered_data, pl.DataFrame)
        assert settings.filtered_data.shape == (3, 1)

    def test_empty_polars_dataframe(self):
        """Empty Polars DataFrame is accepted as filtered_data."""
        df = pl.DataFrame()
        settings = DuplicatesSettings(
            filtered_data=df,
            survey_id="sid",
        )
        assert settings.filtered_data.shape == (0, 0)

    def test_missing_survey_id_raises(self):
        """Missing survey_id raises ValidationError (required field)."""
        with pytest.raises(ValidationError):
            DuplicatesSettings()

    def test_empty_survey_id_raises(self):
        """Empty string survey_id raises ValidationError (min_length=1)."""
        with pytest.raises(ValidationError):
            DuplicatesSettings(survey_id="")

    def test_none_survey_id_accepted(self):
        """None survey_id is accepted since field type is str | None."""
        settings = DuplicatesSettings(survey_id=None)
        assert settings.survey_id is None

    def test_conditions_default_is_empty_dict(self):
        """Conditions defaults to an empty dict when not provided."""
        settings = DuplicatesSettings(survey_id="sid")
        assert settings.conditions == {}
        assert isinstance(settings.conditions, dict)

    def test_conditions_with_data(self):
        """Conditions accepts a populated dictionary."""
        conds = {
            "filter_1": {"col": "age", "op": "gt", "val": 18},
            "filter_2": {"col": "status", "op": "eq", "val": "active"},
        }
        settings = DuplicatesSettings(survey_id="sid", conditions=conds)
        assert len(settings.conditions) == 2
        assert "filter_1" in settings.conditions

    def test_optional_string_fields_accept_none(self):
        """Optional string fields (survey_key, survey_date, enumerator) accept None."""
        settings = DuplicatesSettings(
            survey_id="sid",
            survey_key=None,
            survey_date=None,
            enumerator=None,
        )
        assert settings.survey_key is None
        assert settings.survey_date is None
        assert settings.enumerator is None


# ── DateDefaults ─────────────────────────────────────────────────────


class TestDateDefaults:
    """Tests for the DateDefaults Pydantic model."""

    def test_default_values(self):
        """Create DateDefaults with no arguments uses correct defaults."""
        defaults = DateDefaults()
        assert defaults.start_date == datetime.date(1970, 1, 1)
        assert defaults.end_date == datetime.date(2100, 12, 31)

    def test_default_start_date_is_30_days_ago(self):
        """Default start date is approximately 30 days before today."""
        defaults = DateDefaults()
        expected = datetime.date.today() - datetime.timedelta(days=30)
        assert defaults.default_start_date == expected

    def test_default_end_date_is_30_days_ahead(self):
        """Default end date is approximately 30 days after today."""
        defaults = DateDefaults()
        expected = datetime.date.today() + datetime.timedelta(days=30)
        assert defaults.default_end_date == expected

    def test_custom_start_date(self):
        """Create DateDefaults with a custom start_date succeeds."""
        custom_date = datetime.date(2000, 1, 1)
        defaults = DateDefaults(start_date=custom_date)
        assert defaults.start_date == custom_date

    def test_custom_end_date(self):
        """Create DateDefaults with a custom end_date succeeds."""
        custom_date = datetime.date(2050, 6, 15)
        defaults = DateDefaults(end_date=custom_date)
        assert defaults.end_date == custom_date

    def test_custom_default_start_date(self):
        """Create DateDefaults with a custom default_start_date succeeds."""
        custom_date = datetime.date(2024, 1, 1)
        defaults = DateDefaults(default_start_date=custom_date)
        assert defaults.default_start_date == custom_date

    def test_custom_default_end_date(self):
        """Create DateDefaults with a custom default_end_date succeeds."""
        custom_date = datetime.date(2025, 12, 31)
        defaults = DateDefaults(default_end_date=custom_date)
        assert defaults.default_end_date == custom_date

    def test_all_custom_values(self):
        """Create DateDefaults with all custom values succeeds."""
        defaults = DateDefaults(
            start_date=datetime.date(1990, 1, 1),
            end_date=datetime.date(2090, 12, 31),
            default_start_date=datetime.date(2024, 6, 1),
            default_end_date=datetime.date(2024, 12, 31),
        )
        assert defaults.start_date == datetime.date(1990, 1, 1)
        assert defaults.end_date == datetime.date(2090, 12, 31)
        assert defaults.default_start_date == datetime.date(2024, 6, 1)
        assert defaults.default_end_date == datetime.date(2024, 12, 31)

    def test_start_date_type_is_date(self):
        """All date fields are datetime.date instances."""
        defaults = DateDefaults()
        assert isinstance(defaults.start_date, datetime.date)
        assert isinstance(defaults.end_date, datetime.date)
        assert isinstance(defaults.default_start_date, datetime.date)
        assert isinstance(defaults.default_end_date, datetime.date)


# ── GPSSettings ─────────────────────────────────────────────────────


class TestGPSSettings:
    """Tests for the GPSSettings Pydantic model."""

    def test_valid_minimal(self):
        """Create GPSSettings with only required survey_key succeeds."""
        settings = GPSSettings(survey_key="key_col")
        assert settings.survey_key == "key_col"
        assert settings.survey_id is None
        assert settings.survey_date is None
        assert settings.enumerator is None
        assert settings.team is None
        assert settings.mapbox_custom_key is None

    def test_valid_all_fields(self):
        """Create GPSSettings with all fields populated succeeds."""
        settings = GPSSettings(
            survey_key="key_col",
            survey_id="id_col",
            survey_date="date_col",
            enumerator="enum_col",
            team="team_col",
            mapbox_custom_key="pk.test123",
        )
        assert settings.survey_key == "key_col"
        assert settings.survey_id == "id_col"
        assert settings.survey_date == "date_col"
        assert settings.enumerator == "enum_col"
        assert settings.team == "team_col"
        assert settings.mapbox_custom_key == "pk.test123"

    def test_none_survey_key(self):
        """None survey_key is accepted since field type is str | None."""
        settings = GPSSettings(survey_key=None)
        assert settings.survey_key is None

    def test_missing_survey_key_raises(self):
        """Missing survey_key raises ValidationError (required field)."""
        with pytest.raises(ValidationError):
            GPSSettings()

    def test_empty_survey_id_raises(self):
        """Empty string survey_id raises ValidationError (min_length=1)."""
        with pytest.raises(ValidationError):
            GPSSettings(survey_key="key", survey_id="")


# ── GPSColumnConfig ─────────────────────────────────────────────────


class TestGPSColumnConfig:
    """Tests for the GPSColumnConfig Pydantic model."""

    def test_valid_single_column_format(self):
        """Create GPSColumnConfig with single column format succeeds."""
        config = GPSColumnConfig(
            alias="gps1",
            format_type=GPSFormatType.SINGLE_COLUMN,
            delimiter=DelimiterType.SPACE,
            gps_column="gps_data",
        )
        assert config.alias == "gps1"
        assert config.format_type == GPSFormatType.SINGLE_COLUMN
        assert config.delimiter == DelimiterType.SPACE
        assert config.gps_column == "gps_data"

    def test_valid_separate_columns_format(self):
        """Create GPSColumnConfig with separate columns format succeeds."""
        config = GPSColumnConfig(
            alias="gps2",
            format_type=GPSFormatType.SEPARATE_COLUMNS,
            latitude_column="lat",
            longitude_column="lon",
            altitude_column="alt",
            accuracy_column="acc",
        )
        assert config.format_type == GPSFormatType.SEPARATE_COLUMNS
        assert config.latitude_column == "lat"
        assert config.longitude_column == "lon"
        assert config.altitude_column == "alt"
        assert config.accuracy_column == "acc"

    def test_separate_columns_without_optional_fields(self):
        """Separate columns format without altitude/accuracy succeeds."""
        config = GPSColumnConfig(
            alias="gps3",
            format_type=GPSFormatType.SEPARATE_COLUMNS,
            latitude_column="lat",
            longitude_column="lon",
        )
        assert config.altitude_column is None
        assert config.accuracy_column is None

    def test_single_column_missing_delimiter_raises(self):
        """Single column format with explicit None delimiter raises ValidationError."""
        with pytest.raises(ValidationError, match="Delimiter is required"):
            GPSColumnConfig(
                alias="gps1",
                format_type=GPSFormatType.SINGLE_COLUMN,
                delimiter=None,
                gps_column="gps_data",
            )

    def test_single_column_missing_gps_column_raises(self):
        """Single column format with explicit None gps_column raises ValidationError."""
        with pytest.raises(ValidationError, match="GPS column is required"):
            GPSColumnConfig(
                alias="gps1",
                format_type=GPSFormatType.SINGLE_COLUMN,
                delimiter=DelimiterType.COMMA,
                gps_column=None,
            )

    def test_separate_columns_missing_latitude_raises(self):
        """Separate columns with None latitude raises ValidationError."""
        with pytest.raises(ValidationError, match="Latitude Column is required"):
            GPSColumnConfig(
                alias="gps1",
                format_type=GPSFormatType.SEPARATE_COLUMNS,
                latitude_column=None,
                longitude_column="lon",
            )

    def test_separate_columns_missing_longitude_raises(self):
        """Separate columns with None longitude raises ValidationError."""
        with pytest.raises(ValidationError, match="Longitude Column is required"):
            GPSColumnConfig(
                alias="gps1",
                format_type=GPSFormatType.SEPARATE_COLUMNS,
                latitude_column="lat",
                longitude_column=None,
            )

    def test_empty_alias_raises(self):
        """Empty alias raises ValidationError (min_length=1)."""
        with pytest.raises(ValidationError):
            GPSColumnConfig(
                alias="",
                format_type=GPSFormatType.SINGLE_COLUMN,
                delimiter=DelimiterType.SPACE,
                gps_column="gps_data",
            )

    def test_missing_alias_raises(self):
        """Missing alias raises ValidationError."""
        with pytest.raises(ValidationError):
            GPSColumnConfig(
                format_type=GPSFormatType.SINGLE_COLUMN,
                delimiter=DelimiterType.SPACE,
                gps_column="gps_data",
            )

    def test_comma_delimiter(self):
        """Single column format with comma delimiter succeeds."""
        config = GPSColumnConfig(
            alias="gps1",
            format_type=GPSFormatType.SINGLE_COLUMN,
            delimiter=DelimiterType.COMMA,
            gps_column="gps_data",
        )
        assert config.delimiter == DelimiterType.COMMA


# ── CheckConfiguration ───────────────────────────────────────────────


class TestCheckConfiguration:
    """Tests for the CheckConfiguration Pydantic model."""

    def test_valid_minimal(self):
        """Create CheckConfiguration with required fields only succeeds."""
        config = CheckConfiguration(
            page_name="Page1",
            survey_data_name="survey_data",
            survey_key="key_col",
            survey_id="id_col",
        )
        assert config.page_name == "Page1"
        assert config.survey_data_name == "survey_data"
        assert config.survey_key == "key_col"
        assert config.survey_id == "id_col"
        assert config.survey_date is None
        assert config.enumerator is None
        assert config.team is None
        assert config.formversion is None
        assert config.duration is None
        assert config.survey_target is None
        assert config.backcheck_data_name is None
        assert config.tracking_data_name is None

    def test_valid_all_fields(self):
        """Create CheckConfiguration with all fields populated succeeds."""
        config = CheckConfiguration(
            page_name="Household",
            survey_data_name="hh_data",
            survey_key="uuid",
            survey_id="hhid",
            survey_date="submission_date",
            enumerator="enum_id",
            team="team_id",
            formversion="version",
            duration="duration_col",
            survey_target=500,
            backcheck_data_name="bc_data",
            backcheck_date="bc_date",
            backchecker="bc_id",
            backchecker_team="bc_team",
            backcheck_target_percent=20,
            tracking_data_name="track_data",
        )
        assert config.survey_date == "submission_date"
        assert config.enumerator == "enum_id"
        assert config.survey_target == 500
        assert config.backcheck_data_name == "bc_data"
        assert config.backcheck_target_percent == 20
        assert config.tracking_data_name == "track_data"

    def test_validate_page_name_strips_whitespace(self):
        """validate_page_name strips leading/trailing whitespace."""
        config = CheckConfiguration(
            page_name="  Page1  ",
            survey_data_name="data",
            survey_key="key",
            survey_id="id",
        )
        assert config.page_name == "Page1"

    def test_validate_page_name_empty_raises(self):
        """validate_page_name with empty string raises ValidationError."""
        with pytest.raises(ValidationError):
            CheckConfiguration(
                page_name="",
                survey_data_name="data",
                survey_key="key",
                survey_id="id",
            )

    def test_validate_page_name_whitespace_only_raises(self):
        """validate_page_name with whitespace-only string raises ValidationError."""
        with pytest.raises(ValidationError, match="Page name cannot be empty"):
            CheckConfiguration(
                page_name="   ",
                survey_data_name="data",
                survey_key="key",
                survey_id="id",
            )

    def test_page_name_max_length_raises(self):
        """page_name exceeding max_length=20 raises ValidationError."""
        with pytest.raises(ValidationError):
            CheckConfiguration(
                page_name="A" * 21,
                survey_data_name="data",
                survey_key="key",
                survey_id="id",
            )

    def test_page_name_exactly_20_chars(self):
        """page_name of exactly 20 characters succeeds."""
        config = CheckConfiguration(
            page_name="A" * 20,
            survey_data_name="data",
            survey_key="key",
            survey_id="id",
        )
        assert len(config.page_name) == 20

    def test_survey_target_zero(self):
        """survey_target=0 passes the ge=0 constraint."""
        config = CheckConfiguration(
            page_name="P1",
            survey_data_name="data",
            survey_key="key",
            survey_id="id",
            survey_target=0,
        )
        assert config.survey_target == 0

    def test_survey_target_negative_raises(self):
        """Negative survey_target raises ValidationError (ge=0)."""
        with pytest.raises(ValidationError):
            CheckConfiguration(
                page_name="P1",
                survey_data_name="data",
                survey_key="key",
                survey_id="id",
                survey_target=-1,
            )

    def test_backcheck_target_percent_boundaries(self):
        """backcheck_target_percent 0 and 100 pass boundary constraints."""
        for val in (0, 100):
            config = CheckConfiguration(
                page_name="P1",
                survey_data_name="data",
                survey_key="key",
                survey_id="id",
                backcheck_target_percent=val,
            )
            assert config.backcheck_target_percent == val

    def test_backcheck_target_percent_over_100_raises(self):
        """backcheck_target_percent > 100 raises ValidationError (le=100)."""
        with pytest.raises(ValidationError):
            CheckConfiguration(
                page_name="P1",
                survey_data_name="data",
                survey_key="key",
                survey_id="id",
                backcheck_target_percent=101,
            )

    def test_to_dict_returns_dict(self):
        """to_dict() returns a plain dictionary of the model fields."""
        config = CheckConfiguration(
            page_name="DictPage",
            survey_data_name="data",
            survey_key="key",
            survey_id="id",
            survey_target=10,
        )
        result = config.to_dict()
        assert isinstance(result, dict)
        assert result["page_name"] == "DictPage"
        assert result["survey_target"] == 10
        assert result["survey_date"] is None

    def test_to_dict_contains_all_fields(self):
        """to_dict() contains all model field keys."""
        config = CheckConfiguration(
            page_name="P1",
            survey_data_name="data",
            survey_key="key",
            survey_id="id",
        )
        result = config.to_dict()
        expected_keys = {
            "page_name",
            "survey_data_name",
            "survey_key",
            "survey_id",
            "survey_date",
            "enumerator",
            "team",
            "formversion",
            "duration",
            "survey_target",
            "backcheck_data_name",
            "backcheck_date",
            "backchecker",
            "backchecker_team",
            "backcheck_target_percent",
            "tracking_data_name",
        }
        assert expected_keys == set(result.keys())


# ── SurveyColumnSelections ───────────────────────────────────────────


class TestSurveyColumnSelections:
    """Tests for the SurveyColumnSelections Pydantic model."""

    def test_valid_minimal(self):
        """Create SurveyColumnSelections with required survey_key succeeds."""
        sel = SurveyColumnSelections(survey_key="key_col")
        assert sel.survey_key == "key_col"
        assert sel.survey_id is None
        assert sel.survey_date is None
        assert sel.enumerator is None
        assert sel.team is None
        assert sel.formversion is None
        assert sel.duration is None
        assert sel.survey_target is None

    def test_valid_all_fields(self):
        """Create SurveyColumnSelections with all fields populated succeeds."""
        sel = SurveyColumnSelections(
            survey_key="key",
            survey_id="id",
            survey_date="date",
            enumerator="enum",
            team="team",
            formversion="version",
            duration="dur",
            survey_target=200,
        )
        assert sel.survey_id == "id"
        assert sel.survey_date == "date"
        assert sel.enumerator == "enum"
        assert sel.team == "team"
        assert sel.formversion == "version"
        assert sel.duration == "dur"
        assert sel.survey_target == 200

    def test_none_survey_key_accepted(self):
        """None survey_key is accepted since type is str | None."""
        sel = SurveyColumnSelections(survey_key=None)
        assert sel.survey_key is None

    def test_missing_survey_key_raises(self):
        """Missing survey_key raises ValidationError (required field)."""
        with pytest.raises(ValidationError):
            SurveyColumnSelections()

    def test_empty_string_survey_id_raises(self):
        """Empty string survey_id raises ValidationError (min_length=1)."""
        with pytest.raises(ValidationError):
            SurveyColumnSelections(survey_key="key", survey_id="")

    def test_survey_target_zero(self):
        """survey_target=0 passes the ge=0 constraint."""
        sel = SurveyColumnSelections(survey_key="key", survey_target=0)
        assert sel.survey_target == 0

    def test_survey_target_negative_raises(self):
        """Negative survey_target raises ValidationError (ge=0)."""
        with pytest.raises(ValidationError):
            SurveyColumnSelections(survey_key="key", survey_target=-1)


# ── BackcheckColumnSelectors ─────────────────────────────────────────


class TestBackcheckColumnSelectors:
    """Tests for the BackcheckColumnSelectors Pydantic model."""

    def test_valid_defaults(self):
        """Create BackcheckColumnSelectors with no args uses None defaults."""
        sel = BackcheckColumnSelectors()
        assert sel.backcheck_date is None
        assert sel.backchecker is None
        assert sel.backchecker_team is None
        assert sel.backcheck_target_percent is None

    def test_valid_all_fields(self):
        """Create BackcheckColumnSelectors with all fields succeeds."""
        sel = BackcheckColumnSelectors(
            backcheck_date="bc_date",
            backchecker="bc_id",
            backchecker_team="bc_team",
            backcheck_target_percent=15,
        )
        assert sel.backcheck_date == "bc_date"
        assert sel.backchecker == "bc_id"
        assert sel.backchecker_team == "bc_team"
        assert sel.backcheck_target_percent == 15

    def test_backcheck_target_percent_zero(self):
        """backcheck_target_percent=0 passes ge=0 constraint."""
        sel = BackcheckColumnSelectors(backcheck_target_percent=0)
        assert sel.backcheck_target_percent == 0

    def test_backcheck_target_percent_100(self):
        """backcheck_target_percent=100 passes le=100 constraint."""
        sel = BackcheckColumnSelectors(backcheck_target_percent=100)
        assert sel.backcheck_target_percent == 100

    def test_backcheck_target_percent_over_100_raises(self):
        """backcheck_target_percent > 100 raises ValidationError (le=100)."""
        with pytest.raises(ValidationError):
            BackcheckColumnSelectors(backcheck_target_percent=101)

    def test_backcheck_target_percent_negative_raises(self):
        """Negative backcheck_target_percent raises ValidationError (ge=0)."""
        with pytest.raises(ValidationError):
            BackcheckColumnSelectors(backcheck_target_percent=-1)

    def test_empty_string_backcheck_date_raises(self):
        """Empty string backcheck_date raises ValidationError (min_length=1)."""
        with pytest.raises(ValidationError):
            BackcheckColumnSelectors(backcheck_date="")
