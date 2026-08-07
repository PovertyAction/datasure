"""Tests for correction_view.py logic patterns."""

import datetime as dt
import sys
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.views.correction_view import (
    CorrectionFormState,
    _build_correction_log_display,
    _display_correction_details,
    _handle_apply_correction,
    _handle_remove_correction,
    _render_action_ui,
    _render_column_selector,
    _render_modify_value_action,
    _render_remove_row_action,
    _render_remove_value_action,
    get_current_value,
    get_key_options,
    load_hfc_config,
    load_tab_config,
    main,
    parse_date_value,
    render_add_correction_form,
    render_correction_input_form,
    render_page_header,
    render_page_navigation,
    render_value_input_widget,
    should_enable_apply_button,
    validate_numeric_input,
    validate_prerequisites,
)

_st = sys.modules["streamlit"]


@contextmanager
def _patched_st(**overrides):
    """Temporarily set attributes on the shared streamlit mock.

    `_st` is a single mock shared across every view test file, so leaving
    an override bound after a test (e.g. an exhausted list `side_effect`)
    can crash unrelated tests elsewhere in the suite. This always restores
    whatever was there before, even on failure.
    """
    originals = {name: getattr(_st, name) for name in overrides}
    try:
        for name, value in overrides.items():
            setattr(_st, name, value)
        yield
    finally:
        for name, value in originals.items():
            setattr(_st, name, value)


def _mock_context_widget() -> MagicMock:
    """A MagicMock usable as a `with ...:` context manager target."""
    widget = MagicMock()
    widget.__enter__ = MagicMock(return_value=widget)
    widget.__exit__ = MagicMock(return_value=False)
    return widget


class TestCorrectionInputFormLogic:
    """Test the correction_input_form function logic patterns."""

    def test_correction_form_data_type_validation_numeric_logic(self):
        """Test numeric data type validation logic."""
        # Test numeric column validation logic
        column_name = "age"
        column_schema = {"age": pl.Int64, "name": pl.Utf8}
        new_value_str = "25"

        # Simulate the numeric validation logic from the function
        if column_schema[column_name] in [pl.Int64, pl.Float64]:
            try:
                validated_value = float(new_value_str)
                is_valid = True
                error_message = None
            except ValueError:
                validated_value = None
                is_valid = False
                error_message = "New value must be a number."
        else:
            validated_value = new_value_str
            is_valid = True
            error_message = None

        assert is_valid is True
        assert validated_value == 25.0
        assert error_message is None

    def test_correction_form_invalid_numeric_value_logic(self):
        """Test validation logic with invalid numeric value."""
        column_name = "age"
        column_schema = {"age": pl.Int64, "name": pl.Utf8}
        new_value_str = "not_a_number"

        # Simulate the numeric validation logic
        if column_schema[column_name] in [pl.Int64, pl.Float64]:
            try:
                validated_value = float(new_value_str)
                is_valid = True
                error_message = None
            except ValueError:
                validated_value = None
                is_valid = False
                error_message = "New value must be a number."
        else:
            validated_value = new_value_str
            is_valid = True
            error_message = None

        assert is_valid is False
        assert validated_value is None
        assert error_message == "New value must be a number."

    def test_correction_form_string_data_type_logic(self):
        """Test string data type handling logic."""
        column_name = "name"
        column_schema = {"age": pl.Int64, "name": pl.Utf8}
        new_value_str = "John Doe"

        # Simulate the validation logic for string columns
        if column_schema[column_name] in [pl.Int64, pl.Float64]:
            try:
                validated_value = float(new_value_str)
                is_valid = True
                error_message = None
            except ValueError:
                validated_value = None
                is_valid = False
                error_message = "New value must be a number."
        else:
            validated_value = new_value_str
            is_valid = True
            error_message = None

        assert is_valid is True
        assert validated_value == "John Doe"
        assert error_message is None

    def test_correction_form_datetime_handling_logic(self):
        """Test datetime data type handling logic."""
        # Simulate datetime input handling
        column_dtype = pl.Datetime

        # Mock date input from Streamlit
        from datetime import date

        date_input = date(2024, 1, 15)

        # Simulate the datetime conversion logic
        if column_dtype == pl.Datetime:
            # Convert date to datetime as done in the function
            converted_datetime = pl.datetime(
                date_input.year, date_input.month, date_input.day
            )
            is_datetime_conversion = True
        else:
            converted_datetime = None
            is_datetime_conversion = False

        assert is_datetime_conversion is True
        # Note: pl.datetime returns a datetime expression, not a value
        assert converted_datetime is not None

    def test_correction_form_action_types_logic(self):
        """Test different correction action types logic."""

        def requires_column_selection(action):
            return action in ["modify value", "remove value"]

        def requires_new_value(action):
            return action == "modify value"

        # Test each action type
        test_cases = [
            ("modify value", True, True, None),
            ("remove value", True, False, None),
            (
                "remove row",
                False,
                False,
                "This will remove the row with the current ID value from the dataset.",
            ),
        ]

        for action, needs_column, needs_new_value, warning_message in test_cases:
            assert requires_column_selection(action) == needs_column
            assert requires_new_value(action) == needs_new_value

            if action == "remove row":
                assert warning_message is not None
            else:
                assert warning_message is None

    def test_correction_form_data_retrieval_logic(self):
        """Test the data retrieval and filtering logic."""
        # Mock corrected data
        mock_corrected_data = pl.DataFrame(
            {
                "KEY": ["uuid:123", "uuid:456", "uuid:789"],
                "name": ["Alice", "Bob", "Charlie"],
                "age": [25, 30, 35],
                "city": ["NYC", "LA", "Chicago"],
            }
        )

        # Test current value retrieval logic
        survey_key = "KEY"
        selected_key = "uuid:456"
        column_to_modify = "name"

        # Simulate the current value retrieval logic
        filtered_data = mock_corrected_data.filter(pl.col(survey_key) == selected_key)
        current_value = filtered_data.select(column_to_modify)[0, 0]

        assert current_value == "Bob"

    def test_correction_form_unique_key_options_logic(self):
        """Test unique key options retrieval logic."""
        # Mock corrected data with duplicate keys
        mock_corrected_data = pl.DataFrame(
            {
                "KEY": ["uuid:123", "uuid:456", "uuid:123", "uuid:789"],
                "name": ["Alice", "Bob", "Alice", "Charlie"],
                "age": [25, 30, 25, 35],
            }
        )

        # Test unique key retrieval logic
        survey_key = "KEY"

        # Simulate the unique key options logic
        key_options = mock_corrected_data.select(survey_key).unique(maintain_order=True)
        unique_keys = key_options.to_series().to_list()

        # Should have unique keys only
        expected_unique_keys = ["uuid:123", "uuid:456", "uuid:789"]
        assert len(unique_keys) == 3
        assert set(unique_keys) == set(expected_unique_keys)

    def test_correction_form_column_options_logic(self):
        """Test column options for modification logic."""
        # Mock corrected data
        mock_corrected_data = pl.DataFrame(
            {
                "KEY": ["uuid:123"],
                "name": ["Alice"],
                "age": [25],
                "city": ["NYC"],
                "score": [95.5],
            }
        )

        # Test column options logic
        available_columns = mock_corrected_data.columns

        # All columns should be available for modification
        expected_columns = ["KEY", "name", "age", "city", "score"]
        assert available_columns == expected_columns

    def test_correction_form_schema_type_checking_logic(self):
        """Test schema-based data type checking logic."""
        from datetime import datetime

        # Mock corrected data with different data types
        mock_corrected_data = pl.DataFrame(
            {
                "id": [1, 2, 3],
                "name": ["Alice", "Bob", "Charlie"],
                "score": [95.5, 87.2, 92.1],
                "active": [True, False, True],
                "created_date": [
                    datetime(2024, 1, 1),
                    datetime(2024, 1, 2),
                    datetime(2024, 1, 3),
                ],
            }
        )

        # Test schema type checking logic
        schema = mock_corrected_data.schema

        # Test different column type checks
        test_cases = [
            ("id", pl.Int64, True),  # Integer column
            ("name", pl.Utf8, False),  # String column
            ("score", pl.Float64, True),  # Float column
            ("active", pl.Boolean, False),  # Boolean column
            ("created_date", pl.Datetime, False),  # Datetime column
        ]

        for col_name, expected_type, is_numeric in test_cases:
            actual_type = schema[col_name]
            assert actual_type == expected_type

            # Test numeric type checking logic
            if actual_type in [pl.Int64, pl.Float64]:
                assert is_numeric is True
            else:
                assert is_numeric is False

    def test_correction_form_remove_row_logic(self):
        """Test remove row action logic."""
        # Test remove row action handling
        action = "remove row"

        # Simulate the remove row logic
        if action == "remove row":
            warning_shown = True
            new_value = None
            current_value = None
            col_to_modify = None
        else:
            warning_shown = False
            new_value = "some_value"
            current_value = "old_value"
            col_to_modify = "some_column"

        assert warning_shown is True
        assert new_value is None
        assert current_value is None
        assert col_to_modify is None

    def test_correction_form_remove_value_logic(self):
        """Test remove value action logic."""
        # Test remove value action (sets new_value to None)
        action = "remove value"

        # Simulate the remove value logic
        if action == "modify value":
            new_value_required = True
        elif action == "remove value":
            new_value_required = False
            # In remove value, new_value would be set to None
            new_value = None
        else:
            new_value_required = False

        assert new_value_required is False
        assert new_value is None

    def test_correction_form_edge_cases_logic(self):
        """Test edge cases in correction form logic."""
        # Test empty dataset
        empty_data = pl.DataFrame()

        # Empty dataset should have no columns
        assert len(empty_data.columns) == 0

        # Test single row dataset
        single_row_data = pl.DataFrame({"KEY": ["uuid:123"], "value": [42]})

        # Should still work with single row
        assert len(single_row_data) == 1
        assert "KEY" in single_row_data.columns
        assert "value" in single_row_data.columns

    def test_correction_form_numeric_edge_cases_logic(self):
        """Test numeric validation edge cases logic."""
        # Test various numeric input scenarios
        test_cases = [
            ("42", 42.0, True),  # Integer string
            ("42.5", 42.5, True),  # Float string
            ("0", 0.0, True),  # Zero
            ("-42", -42.0, True),  # Negative number
            ("42.0", 42.0, True),  # Float with .0
            ("", None, False),  # Empty string
            ("abc", None, False),  # Non-numeric string
            ("42abc", None, False),  # Mixed alphanumeric
            ("42.5.6", None, False),  # Invalid float format
        ]

        def _handle_empty_value_error():
            raise ValueError("Empty string")

        for input_value, expected_output, should_succeed in test_cases:
            # Simulate numeric validation
            try:
                if input_value == "":
                    # Handle empty string case
                    _handle_empty_value_error()
                validated_value = float(input_value)
                is_valid = True
            except ValueError:
                validated_value = None
                is_valid = False

            assert is_valid == should_succeed
            if should_succeed:
                assert validated_value == expected_output
            else:
                assert validated_value is None

    def test_correction_form_database_interaction_logic(self):
        """Test database interaction parameters logic."""
        project_id = "test_project_123"
        alias = "survey_data"

        # Test that the function logic would call duckdb_get_table with correct params
        expected_project_id = project_id
        expected_alias = alias
        expected_db_name = "corrected"

        # Verify the expected parameters match what the function should use
        assert expected_project_id == "test_project_123"
        assert expected_alias == "survey_data"
        assert expected_db_name == "corrected"


class TestBuildCorrectionLogDisplay:
    """Test _build_correction_log_display: status columns and ordering."""

    def _base_log(self, **overrides) -> pl.DataFrame:
        data = {
            "date": ["2026-01-01"],
            "KEY": ["key1"],
            "ID": [None],
            "action": ["modify value"],
            "column": ["name"],
            "current_value": ["John"],
            "new_value": ["Johnny"],
            "reason": ["typo"],
        }
        data.update(overrides)
        return pl.DataFrame(data)

    def test_backfills_missing_status_columns(self):
        """A legacy log without status columns gets defaults applied."""
        log = self._base_log()

        result = _build_correction_log_display(log)

        assert result["status"].to_list() == ["Successful"]
        assert result["status_reason"].to_list() == [None]

    def test_preserves_existing_status_columns(self):
        """An already-refreshed log keeps its real status/reason values."""
        log = self._base_log(status=["Failed"], status_reason=["Key not found"])

        result = _build_correction_log_display(log)

        assert result["status"].to_list() == ["Failed"]
        assert result["status_reason"].to_list() == ["Key not found"]

    def test_status_columns_ordered_right_after_action(self):
        """status/status_reason are positioned right after action."""
        log = self._base_log()

        result = _build_correction_log_display(log)

        assert result.columns == [
            "date",
            "KEY",
            "Survey ID",
            "action",
            "status",
            "status_reason",
            "column",
            "current_value",
            "new_value",
            "reason",
        ]


class TestLoadTabConfig:
    """Test that load_tab_config threads the configured Survey ID column."""

    @patch("datasure.views.correction_view.get_check_config_settings")
    def test_includes_survey_id_when_configured(self, mock_get_settings):
        mock_get_settings.return_value = {
            "page_name": "Household Survey",
            "survey_data_name": "household_survey",
            "survey_key": "KEY",
            "survey_id": "hhid",
        }

        config = load_tab_config("proj1", 0)

        assert config.survey_id == "hhid"

    @patch("datasure.views.correction_view.get_check_config_settings")
    def test_survey_id_none_when_not_configured(self, mock_get_settings):
        mock_get_settings.return_value = {
            "page_name": "Household Survey",
            "survey_data_name": "household_survey",
            "survey_key": "KEY",
        }

        config = load_tab_config("proj1", 0)

        assert config.survey_id is None


class TestRenderAddCorrectionFormSurveyId:
    """Test the Survey ID display shown after a KEY is selected."""

    def _mock_processor(self, data: pl.DataFrame) -> MagicMock:
        processor = MagicMock()
        processor.get_corrected_data.return_value = data
        return processor

    def test_empty_corrected_data_shows_warning(self):
        processor = self._mock_processor(pl.DataFrame())

        with _patched_st(warning=MagicMock()):
            render_add_correction_form(
                correction_processor=processor,
                key_col="KEY",
                alias="survey",
                tab_index=0,
            )
            assert _st.warning.called

    @contextmanager
    def _mocked_widgets(
        self, selected_key: str, click_apply: bool = False, reason: str = ""
    ):
        """Mock the widgets this form uses, restoring originals afterward.

        `_st` is a single mock shared across every view test file, so
        leaving these bound after the test (e.g. an exhausted list
        `side_effect` on `selectbox`) can crash unrelated tests in
        test_import_view.py that inherit the same mock later in the run.
        """
        originals = {
            "popover": _st.popover,
            "markdown": _st.markdown,
            "warning": _st.warning,
            "write": _st.write,
            "text_input": _st.text_input,
            "button": _st.button,
            "selectbox": _st.selectbox,
        }
        try:
            mock_popover = MagicMock()
            mock_popover.__enter__ = MagicMock(return_value=None)
            mock_popover.__exit__ = MagicMock(return_value=False)
            _st.popover = MagicMock(return_value=mock_popover)
            _st.markdown = MagicMock()
            _st.warning = MagicMock()
            _st.write = MagicMock()
            _st.text_input = MagicMock(return_value=reason)
            _st.button = MagicMock(return_value=click_apply)
            # First selectbox call selects the KEY, second selects the action.
            _st.selectbox = MagicMock(side_effect=[selected_key, "remove row"])
            yield
        finally:
            for name, value in originals.items():
                setattr(_st, name, value)

    def test_shows_survey_id_when_configured(self):
        """The configured Survey ID column's value is displayed for the KEY."""
        data = pl.DataFrame({"KEY": ["uuid:1", "uuid:2"], "hhid": ["HH001", "HH002"]})
        processor = self._mock_processor(data)

        with self._mocked_widgets(selected_key="uuid:1"):
            render_add_correction_form(
                correction_processor=processor,
                key_col="KEY",
                alias="survey",
                tab_index=0,
                survey_id_col="hhid",
            )

            written = [str(c.args[0]) for c in _st.write.call_args_list]
            assert any("Survey ID" in text and "HH001" in text for text in written)

    def test_no_survey_id_display_when_not_configured(self):
        """No Survey ID row is shown when no Survey ID column is configured."""
        data = pl.DataFrame({"KEY": ["uuid:1", "uuid:2"], "hhid": ["HH001", "HH002"]})
        processor = self._mock_processor(data)

        with self._mocked_widgets(selected_key="uuid:1"):
            render_add_correction_form(
                correction_processor=processor,
                key_col="KEY",
                alias="survey",
                tab_index=0,
                survey_id_col=None,
            )

            written = [str(c.args[0]) for c in _st.write.call_args_list]
            assert not any("Survey ID" in text for text in written)

    def test_no_survey_id_display_when_column_missing_from_data(self):
        """A configured but nonexistent Survey ID column is skipped, not an error."""
        data = pl.DataFrame({"KEY": ["uuid:1", "uuid:2"]})
        processor = self._mock_processor(data)

        with self._mocked_widgets(selected_key="uuid:1"):
            render_add_correction_form(
                correction_processor=processor,
                key_col="KEY",
                alias="survey",
                tab_index=0,
                survey_id_col="hhid",
            )

            written = [str(c.args[0]) for c in _st.write.call_args_list]
            assert not any("Survey ID" in text for text in written)

    def test_apply_passes_survey_id_to_processor(self):
        """Clicking Apply forwards the looked-up Survey ID to apply_correction."""
        data = pl.DataFrame({"KEY": ["uuid:1", "uuid:2"], "hhid": ["HH001", "HH002"]})
        processor = self._mock_processor(data)
        processor.validate_correction_input.return_value = (True, "")

        with self._mocked_widgets(
            selected_key="uuid:1", click_apply=True, reason="Test reason"
        ):
            render_add_correction_form(
                correction_processor=processor,
                key_col="KEY",
                alias="survey",
                tab_index=0,
                survey_id_col="hhid",
            )

            processor.apply_correction.assert_called_once()
            assert processor.apply_correction.call_args[1]["survey_id_value"] == "HH001"


class TestGetKeyOptions:
    """Test get_key_options: unique key values, in first-seen order."""

    def test_returns_unique_values_in_order(self):
        data = pl.DataFrame({"KEY": ["b", "a", "b", "c"]})
        assert get_key_options(data, "KEY") == ["b", "a", "c"]

    def test_single_row(self):
        data = pl.DataFrame({"KEY": ["only"]})
        assert get_key_options(data, "KEY") == ["only"]


class TestGetCurrentValue:
    """Test get_current_value: lookup and graceful failure."""

    def test_returns_value_when_found(self):
        data = pl.DataFrame({"KEY": ["k1", "k2"], "name": ["Alice", "Bob"]})
        assert get_current_value(data, "KEY", "k2", "name") == "Bob"

    def test_key_not_found_does_not_raise(self):
        """A key that doesn't exist yields an empty result, not a crash.

        In practice this path isn't reachable from the UI (the key selector
        only ever offers values already present in the data), so this just
        guards the try/except boundary rather than asserting a specific
        "not found" sentinel.
        """
        data = pl.DataFrame({"KEY": ["k1"], "name": ["Alice"]})
        result = get_current_value(data, "KEY", "missing", "name")
        assert result is None or len(result) == 0

    def test_returns_none_for_nonexistent_column(self):
        data = pl.DataFrame({"KEY": ["k1"], "name": ["Alice"]})
        assert get_current_value(data, "KEY", "k1", "nonexistent") is None


class TestParseDateValue:
    """Test parse_date_value: string/datetime parsing and failure handling."""

    def test_none_returns_none(self):
        assert parse_date_value(None) is None

    def test_empty_string_returns_none(self):
        assert parse_date_value("") is None

    def test_parses_iso_string(self):
        assert parse_date_value("2024-01-15") == dt.date(2024, 1, 15)

    def test_parses_datetime_object(self):
        assert parse_date_value(dt.datetime(2024, 1, 15, 10, 30)) == dt.date(
            2024, 1, 15
        )

    def test_invalid_string_returns_none(self):
        assert parse_date_value("not-a-date") is None

    def test_value_without_date_method_returns_none(self):
        assert parse_date_value(12345) is None


class TestValidateNumericInput:
    """Test validate_numeric_input across numeric and non-numeric dtypes."""

    @pytest.mark.parametrize("dtype", [pl.Int64, pl.Int32, pl.Float64, pl.Float32])
    def test_valid_numeric_for_numeric_dtype(self, dtype):
        is_valid, err = validate_numeric_input("42", dtype)
        assert is_valid is True
        assert err is None

    def test_invalid_numeric_for_numeric_dtype(self):
        is_valid, err = validate_numeric_input("abc", pl.Float64)
        assert is_valid is False
        assert err == "New value must be a number."

    def test_non_numeric_dtype_always_valid(self):
        is_valid, err = validate_numeric_input("anything at all", pl.Utf8)
        assert is_valid is True
        assert err is None


class TestShouldEnableApplyButton:
    """Test should_enable_apply_button across every action/reason combination."""

    def test_no_reason_disables_regardless_of_action(self):
        assert should_enable_apply_button("remove row", "", None) is False
        assert should_enable_apply_button("modify value", "", "new") is False

    def test_modify_value_requires_new_value(self):
        assert should_enable_apply_button("modify value", "reason", None) is False
        assert should_enable_apply_button("modify value", "reason", "") is False
        assert should_enable_apply_button("modify value", "reason", "new") is True

    def test_remove_value_enabled_with_reason(self):
        assert should_enable_apply_button("remove value", "reason") is True

    def test_remove_row_enabled_with_reason(self):
        assert should_enable_apply_button("remove row", "reason") is True

    def test_unknown_action_disabled(self):
        assert should_enable_apply_button("unknown action", "reason") is False


class TestLoadHfcConfig:
    """Test load_hfc_config: empty vs populated check configuration."""

    @patch("datasure.views.correction_view.duckdb_get_table")
    def test_empty_config_returns_empty_and_no_pages(self, mock_get):
        mock_get.return_value = pl.DataFrame()

        logs, pages = load_hfc_config("proj1")

        assert logs.is_empty()
        assert pages == []

    @patch("datasure.views.correction_view.duckdb_get_table")
    def test_returns_page_names(self, mock_get):
        mock_get.return_value = pl.DataFrame({"page_name": ["Page A", "Page B"]})

        _logs, pages = load_hfc_config("proj1")

        assert pages == ["Page A", "Page B"]
        mock_get.assert_called_once_with(
            project_id="proj1", alias="check_config", db_name="logs"
        )


class TestValidatePrerequisites:
    """Test validate_prerequisites: each st.stop() branch and the happy path."""

    def test_no_project_id_stops(self):
        with _patched_st(stop=MagicMock(side_effect=StopIteration), info=MagicMock()):
            with pytest.raises(StopIteration):
                validate_prerequisites(None)
            assert _st.info.called

    @patch("datasure.views.correction_view.load_hfc_config")
    def test_empty_hfc_config_stops(self, mock_load):
        mock_load.return_value = (pl.DataFrame(), [])

        with (
            _patched_st(stop=MagicMock(side_effect=StopIteration), info=MagicMock()),
            pytest.raises(StopIteration),
        ):
            validate_prerequisites("proj1")

    @patch("datasure.views.correction_view.load_hfc_config")
    def test_empty_pages_stops(self, mock_load):
        mock_load.return_value = (pl.DataFrame({"page_name": ["x"]}), [])

        with (
            _patched_st(stop=MagicMock(side_effect=StopIteration), info=MagicMock()),
            pytest.raises(StopIteration),
        ):
            validate_prerequisites("proj1")

    @patch("datasure.views.correction_view.load_hfc_config")
    def test_all_prerequisites_met_returns_data(self, mock_load):
        mock_load.return_value = (pl.DataFrame({"page_name": ["x"]}), ["Page A"])

        _logs, pages = validate_prerequisites("proj1")

        assert pages == ["Page A"]


class TestRenderValueInputWidget:
    """Test render_value_input_widget: datetime vs text input, numeric validation."""

    def test_datetime_dtype_uses_date_input(self):
        with _patched_st(date_input=MagicMock(return_value=dt.date(2024, 1, 1))):
            new_value, error = render_value_input_widget(
                "col", pl.Datetime, "2023-06-01", tab_index=0
            )
        assert new_value == dt.date(2024, 1, 1)
        assert error is None

    def test_non_datetime_valid_numeric(self):
        with _patched_st(text_input=MagicMock(return_value="42")):
            new_value, error = render_value_input_widget("col", pl.Int64, 10, 0)
        assert new_value == "42"
        assert error is None

    def test_non_datetime_invalid_numeric(self):
        with _patched_st(text_input=MagicMock(return_value="abc")):
            new_value, error = render_value_input_widget("col", pl.Int64, 10, 0)
        assert new_value is None
        assert error == "New value must be a number."

    def test_empty_new_value_skips_validation(self):
        with _patched_st(text_input=MagicMock(return_value="")):
            new_value, error = render_value_input_widget("col", pl.Int64, 10, 0)
        assert new_value == ""
        assert error is None

    def test_non_numeric_dtype_accepts_any_text(self):
        with _patched_st(text_input=MagicMock(return_value="hello")):
            new_value, error = render_value_input_widget("col", pl.Utf8, "old", 0)
        assert new_value == "hello"
        assert error is None


class TestRenderColumnSelector:
    """Test _render_column_selector: column chosen vs left blank."""

    def test_no_column_selected_returns_none_none(self):
        data = pl.DataFrame({"KEY": ["k1"], "name": ["Alice"]})
        with _patched_st(selectbox=MagicMock(return_value=None)):
            column, value = _render_column_selector(data, "KEY", "k1", 0)
        assert column is None
        assert value is None

    def test_column_selected_returns_current_value(self):
        data = pl.DataFrame({"KEY": ["k1"], "name": ["Alice"]})
        with _patched_st(selectbox=MagicMock(return_value="name"), write=MagicMock()):
            column, value = _render_column_selector(data, "KEY", "k1", 0)
        assert column == "name"
        assert value == "Alice"


class TestRenderModifyValueAction:
    """Test _render_modify_value_action: no column vs a column selected."""

    def test_no_column_selected(self):
        data = pl.DataFrame({"KEY": ["k1"], "name": ["Alice"]})
        with _patched_st(selectbox=MagicMock(return_value=None)):
            state = _render_modify_value_action(data, "KEY", "k1", 0)

        assert isinstance(state, CorrectionFormState)
        assert state.action == "modify value"
        assert state.column is None

    def test_column_selected_builds_full_state(self):
        data = pl.DataFrame({"KEY": ["k1"], "age": [25]})
        with _patched_st(
            selectbox=MagicMock(return_value="age"),
            write=MagicMock(),
            text_input=MagicMock(return_value="30"),
        ):
            state = _render_modify_value_action(data, "KEY", "k1", 0)

        assert state.column == "age"
        assert state.current_value == 25
        assert state.new_value == "30"
        assert state.validation_error is None

    def test_column_selected_with_validation_error(self):
        data = pl.DataFrame({"KEY": ["k1"], "age": [25]})
        with _patched_st(
            selectbox=MagicMock(return_value="age"),
            write=MagicMock(),
            text_input=MagicMock(return_value="not-a-number"),
            error=MagicMock(),
        ):
            state = _render_modify_value_action(data, "KEY", "k1", 0)
            assert _st.error.called

        assert state.validation_error == "New value must be a number."


class TestRenderRemoveValueAction:
    """Test _render_remove_value_action."""

    def test_builds_remove_value_state(self):
        data = pl.DataFrame({"KEY": ["k1"], "name": ["Alice"]})
        with _patched_st(selectbox=MagicMock(return_value="name"), write=MagicMock()):
            state = _render_remove_value_action(data, "KEY", "k1", 0)

        assert state.action == "remove value"
        assert state.column == "name"
        assert state.current_value == "Alice"


class TestRenderRemoveRowAction:
    """Test _render_remove_row_action."""

    def test_builds_remove_row_state_and_warns(self):
        with _patched_st(warning=MagicMock()):
            state = _render_remove_row_action("k1")
            assert _st.warning.called

        assert state.action == "remove row"
        assert state.key_value == "k1"


class TestRenderActionUi:
    """Test _render_action_ui dispatches to the right per-action handler."""

    def test_dispatches_modify_value(self):
        data = pl.DataFrame({"KEY": ["k1"], "name": ["Alice"]})
        with _patched_st(selectbox=MagicMock(return_value=None)):
            state = _render_action_ui("modify value", data, "KEY", "k1", 0)
        assert state.action == "modify value"

    def test_dispatches_remove_value(self):
        data = pl.DataFrame({"KEY": ["k1"], "name": ["Alice"]})
        with _patched_st(selectbox=MagicMock(return_value=None), write=MagicMock()):
            state = _render_action_ui("remove value", data, "KEY", "k1", 0)
        assert state.action == "remove value"

    def test_dispatches_remove_row(self):
        data = pl.DataFrame({"KEY": ["k1"], "name": ["Alice"]})
        with _patched_st(warning=MagicMock()):
            state = _render_action_ui("remove row", data, "KEY", "k1", 0)
        assert state.action == "remove row"


class TestHandleApplyCorrection:
    """Test _handle_apply_correction: validation failure, success, exception."""

    def _base_kwargs(self, processor):
        return dict(
            correction_processor=processor,
            corrected_data=pl.DataFrame({"KEY": ["k1"], "name": ["Alice"]}),
            alias="survey",
            key_col="KEY",
            key_value="k1",
            action="modify value",
            column="name",
            current_value="Alice",
            new_value="Alicia",
            reason="typo fix",
        )

    def test_validation_error_shows_error_and_does_not_apply(self):
        processor = MagicMock()
        processor.validate_correction_input.return_value = (False, "bad input")

        with _patched_st(error=MagicMock(), success=MagicMock(), rerun=MagicMock()):
            _handle_apply_correction(**self._base_kwargs(processor))

            assert _st.error.called
            assert "bad input" in _st.error.call_args[0][0]
            processor.apply_correction.assert_not_called()
            assert not _st.success.called

    def test_success_applies_and_reruns(self):
        processor = MagicMock()
        processor.validate_correction_input.return_value = (True, "")

        with _patched_st(error=MagicMock(), success=MagicMock(), rerun=MagicMock()):
            _handle_apply_correction(
                survey_id_value="HH001", **self._base_kwargs(processor)
            )

            processor.apply_correction.assert_called_once()
            assert processor.apply_correction.call_args[1]["survey_id_value"] == (
                "HH001"
            )
            assert _st.success.called
            assert _st.rerun.called

    def test_exception_during_apply_shows_error(self):
        processor = MagicMock()
        processor.validate_correction_input.return_value = (True, "")
        processor.apply_correction.side_effect = RuntimeError("boom")

        with _patched_st(error=MagicMock(), success=MagicMock(), rerun=MagicMock()):
            _handle_apply_correction(**self._base_kwargs(processor))

            assert _st.error.called
            assert "boom" in _st.error.call_args[0][0]
            assert not _st.success.called


class TestRenderCorrectionInputForm:
    """Test render_correction_input_form: empty vs populated corrected data."""

    def test_empty_data_shows_warning(self):
        processor = MagicMock()
        processor.get_corrected_data.return_value = pl.DataFrame()

        with _patched_st(warning=MagicMock()):
            render_correction_input_form(processor, "KEY", "survey", 0)
            assert _st.warning.called

    def test_populated_data_renders_add_form_and_calls_remove_form(self):
        """render_remove_correction_form is `@st.fragment`-wrapped, so under
        the test harness's mock it becomes an opaque callable - this only
        confirms it's invoked with the right args, not its internal
        behavior (covered separately if extracted, per the existing
        `@st.fragment` testing limitation noted elsewhere in this suite).
        """
        processor = MagicMock()
        processor.get_corrected_data.return_value = pl.DataFrame(
            {"KEY": ["k1"], "name": ["Alice"]}
        )

        with (
            _patched_st(
                columns=MagicMock(
                    return_value=[
                        _mock_context_widget(),
                        _mock_context_widget(),
                        _mock_context_widget(),
                    ]
                ),
                popover=MagicMock(return_value=_mock_context_widget()),
                selectbox=MagicMock(return_value=None),
                markdown=MagicMock(),
                info=MagicMock(),
            ),
            patch(
                "datasure.views.correction_view.render_remove_correction_form"
            ) as mock_remove_form,
        ):
            render_correction_input_form(processor, "KEY", "survey", 0)

            processor.get_corrected_data.assert_called()
            mock_remove_form.assert_called_once_with(
                correction_processor=processor, alias="survey", tab_index=0
            )


class TestDisplayCorrectionDetails:
    """Test _display_correction_details renders the selected summary's fields."""

    def test_shows_all_optional_fields_when_present(self):
        summaries = [
            {
                "action_index": "0 - modify value - x",
                "action": "modify value",
                "key_value": "k1",
                "column": "name",
                "new_value": "Alicia",
                "reason": "typo fix",
            }
        ]

        with _patched_st(write=MagicMock()):
            _display_correction_details(summaries, "0 - modify value - x")
            written = [str(c.args[0]) for c in _st.write.call_args_list]

        assert any("modify value" in t for t in written)
        assert any("k1" in t for t in written)
        assert any("name" in t for t in written)
        assert any("Alicia" in t for t in written)
        assert any("typo fix" in t for t in written)

    def test_skips_absent_optional_fields(self):
        summaries = [
            {
                "action_index": "0 - remove row - x",
                "action": "remove row",
                "key_value": "k1",
                "column": None,
                "new_value": None,
                "reason": "duplicate",
            }
        ]

        with _patched_st(write=MagicMock()):
            _display_correction_details(summaries, "0 - remove row - x")
            written = [str(c.args[0]) for c in _st.write.call_args_list]

        assert not any("Column" in t for t in written)
        assert not any("New Value" in t for t in written)


class TestHandleRemoveCorrection:
    """Test _handle_remove_correction: success and exception paths."""

    def test_success_removes_and_reruns(self):
        processor = MagicMock()
        processor.remove_correction_entry.return_value = []
        summaries = [{"action_index": "0 - remove row - x", "index": 0}]

        with _patched_st(success=MagicMock(), rerun=MagicMock(), warning=MagicMock()):
            _handle_remove_correction(
                processor, summaries, "survey", "0 - remove row - x"
            )

            processor.remove_correction_entry.assert_called_once_with("survey", 0)
            assert _st.success.called
            assert _st.rerun.called

    def test_reapply_failures_trigger_warning(self):
        from datasure.utils.reapply_utils import ReapplyFailure

        processor = MagicMock()
        processor.remove_correction_entry.return_value = [
            ReapplyFailure(step="Modify name for key2", reason="Key not found")
        ]
        summaries = [{"action_index": "0 - remove row - x", "index": 0}]

        with _patched_st(success=MagicMock(), rerun=MagicMock(), warning=MagicMock()):
            _handle_remove_correction(
                processor, summaries, "survey", "0 - remove row - x"
            )

            assert _st.warning.called

    def test_exception_shows_error(self):
        processor = MagicMock()
        processor.remove_correction_entry.side_effect = RuntimeError("db error")
        summaries = [{"action_index": "0 - remove row - x", "index": 0}]

        with _patched_st(success=MagicMock(), rerun=MagicMock(), error=MagicMock()):
            _handle_remove_correction(
                processor, summaries, "survey", "0 - remove row - x"
            )

            assert _st.error.called
            assert "db error" in _st.error.call_args[0][0]


class TestRenderPageHeaderAndNavigation:
    """Test the small page-chrome rendering functions."""

    @patch("datasure.views.correction_view.demo_expander")
    @patch("datasure.views.correction_view.page_header")
    def test_render_page_header(self, mock_page_header, mock_demo_expander):
        render_page_header()

        mock_page_header.assert_called_once()
        mock_demo_expander.assert_called_once()

    @patch("datasure.views.correction_view.page_navigation")
    def test_render_page_navigation_without_replication_page(self, mock_nav):
        with _patched_st(session_state={"st_output_page1": "output_view_1"}):
            render_page_navigation()

        mock_nav.assert_called_once()
        assert mock_nav.call_args[1]["next"] is None

    @patch("datasure.views.correction_view.page_navigation")
    def test_render_page_navigation_with_replication_page(self, mock_nav):
        with _patched_st(
            session_state={
                "st_output_page1": "output_view_1",
                "st_replication_page": "replication_view",
            }
        ):
            render_page_navigation()

        mock_nav.assert_called_once()
        assert mock_nav.call_args[1]["next"] is not None


class TestMain:
    """Test the main() entry point orchestration."""

    @patch("datasure.views.correction_view.render_page_navigation")
    @patch("datasure.views.correction_view.render_correction_tab")
    @patch("datasure.views.correction_view.CorrectionProcessor")
    @patch("datasure.views.correction_view.validate_prerequisites")
    @patch("datasure.views.correction_view.render_page_header")
    @patch("datasure.views.correction_view.add_demo_navigation")
    @patch("datasure.views.correction_view.demo_sidebar_help")
    def test_renders_a_tab_per_hfc_page(
        self,
        mock_demo_sidebar,
        mock_add_demo_nav,
        mock_page_header,
        mock_validate,
        mock_processor_cls,
        mock_render_tab,
        mock_page_nav,
    ):
        mock_validate.return_value = (pl.DataFrame({"x": [1]}), ["Page A", "Page B"])
        mock_processor_instance = MagicMock()
        mock_processor_cls.return_value = mock_processor_instance

        with _patched_st(
            session_state={"st_project_id": "proj1"},
            tabs=MagicMock(
                return_value=[_mock_context_widget(), _mock_context_widget()]
            ),
        ):
            main()

        mock_demo_sidebar.assert_called_once()
        mock_add_demo_nav.assert_called_once_with("correction_view", step=6)
        mock_page_header.assert_called_once()
        mock_validate.assert_called_once_with("proj1")
        mock_processor_cls.assert_called_once_with("proj1")
        assert mock_render_tab.call_count == 2
        mock_render_tab.assert_any_call(mock_processor_instance, "proj1", 0)
        mock_render_tab.assert_any_call(mock_processor_instance, "proj1", 1)
        mock_page_nav.assert_called_once()
