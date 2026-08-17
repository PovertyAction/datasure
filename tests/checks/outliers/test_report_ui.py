"""Tests for datasure.checks.outliers.report_ui."""

import importlib
import sys
from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from pydantic import ValidationError

from datasure.checks.outliers.models import (
    ConstraintBounds,
    OutlierMethod,
    OutlierOptionsConfig,
    OutlierSettings,
    SearchType,
)
from datasure.checks.outliers.report_ui import (
    _create_search_type_info,
    _delete_outlier_column,
    _ensure_column_formats,
    _format_constraint_validation_error,
    _format_outlier_validation_error,
    _render_column_grouping_options,
    _render_constraint_metrics,
    _render_constraint_options,
    _render_constraint_violations_table,
    _render_outlier_column_actions,
    _render_outlier_column_inspection,
    _render_outlier_metrics,
    _render_outlier_options,
    _render_outlier_settings_table,
    _render_outlier_table,
    _render_search_type_selection,
    _update_outlier_column_config,
    _validate_constraint_settings,
    _validate_outlier_settings,
    outliers_report,
)
from tests.checks.outliers.conftest import _columns_side_effect, _make_st_mock

# ============================================================================
# REPORT_UI_MOD FIXTURE (reload compute/settings_ui/report_ui with mocked
# streamlit for @st.dialog decorator tests)
# ============================================================================


@pytest.fixture
def report_ui_mod():
    """Reload the outliers submodules with mocked Streamlit for decorator tests."""
    mock_st = _make_st_mock()
    original_st = sys.modules.get("streamlit")
    sys.modules["streamlit"] = mock_st

    import datasure.checks.outliers.compute as compute_module
    import datasure.checks.outliers.report_ui as report_ui_module
    import datasure.checks.outliers.settings_ui as settings_ui_module

    try:
        with patch(
            "datasure.utils.onboarding_utils.demo_output_onboarding",
            lambda tab: lambda f: f,
        ):
            # Reload in dependency order so decorators pick up the mocked st and
            # cross-module references (report_ui imports from settings_ui) stay wired.
            importlib.reload(compute_module)
            importlib.reload(settings_ui_module)
            importlib.reload(report_ui_module)
        yield report_ui_module
    finally:
        if original_st is not None:
            sys.modules["streamlit"] = original_st
        else:
            sys.modules.pop("streamlit", None)
        importlib.reload(compute_module)
        importlib.reload(settings_ui_module)
        importlib.reload(report_ui_module)


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def sample_violation_data():
    """Create sample constraint violation data."""
    return pl.DataFrame(
        {
            "survey_key": ["K001", "K002", "K003"],
            "column name": ["col1", "col1", "col2"],
            "violation reason": [
                "below hard minimum",
                "above soft maximum",
                "no violation",
            ],
        }
    )


@pytest.fixture
def sample_outlier_data():
    """Create sample outlier data."""
    return pl.DataFrame(
        {
            "survey_key": ["K001", "K002"],
            "column name": ["col1", "col1"],
            "outlier reason": ["Value is below lower bound 5.00", "no outlier"],
            "enumerator": ["E001", "E001"],
        }
    )


@pytest.fixture
def base_survey_data():
    """Create base survey data for rendering tests."""
    return pl.DataFrame(
        {
            "survey_key": ["K001", "K002"],
            "survey_id": ["S001", "S002"],
            "survey_date": ["2024-01-01", "2024-01-02"],
            "enumerator": ["E001", "E002"],
            "team": ["T1", "T2"],
        }
    )


@pytest.fixture
def survey_columns_mock():
    """Create a mock ColumnByType for outliers_report tests."""
    from datasure.utils.dataframe_utils import ColumnByType

    return ColumnByType(
        all_columns=[
            "survey_key",
            "survey_id",
            "survey_date",
            "enumerator",
            "team",
            "col1",
        ],
        categorical_columns=["survey_key", "survey_id", "enumerator", "team"],
        datetime_columns=["survey_date"],
        numeric_columns=["col1"],
        boolean_columns=[],
    )


@pytest.fixture
def outlier_config_dict():
    """Create a default outlier config dict for outliers_report tests."""
    return {
        "survey_key": "survey_key",
        "survey_id": "survey_id",
        "survey_date": "survey_date",
        "enumerator": "enumerator",
        "team": "team",
    }


# ============================================================================
# TESTS: _validate_constraint_settings
# ============================================================================


class TestValidateConstraintSettings:
    """Test _validate_constraint_settings function."""

    def test_valid_settings_returns_bounds_and_true(self):
        result, valid = _validate_constraint_settings(
            {"soft_min": 0.0, "soft_max": 100.0}
        )
        assert valid is True
        assert result is not None

    def test_invalid_hierarchy_returns_none_and_false(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            result, valid = _validate_constraint_settings(
                {"hard_min": 50.0, "soft_min": 10.0}
            )
        assert valid is False
        assert result is None
        st_mock.error.assert_called_once()

    def test_all_none_settings_valid(self):
        _result, valid = _validate_constraint_settings(
            {"hard_min": None, "soft_min": None, "soft_max": None, "hard_max": None}
        )
        assert valid is True


# ============================================================================
# TESTS: _validate_outlier_settings
# ============================================================================


class TestValidateOutlierSettings:
    """Test _validate_outlier_settings function."""

    def test_valid_settings_returns_config_and_true(self):
        result, valid = _validate_outlier_settings(
            {
                "outlier_method": OutlierMethod.IQR.value,
                "outlier_multiplier": 1.5,
                "outlier_threshold": 20,
            }
        )
        assert valid is True
        assert result is not None

    def test_invalid_multiplier_returns_none_and_false(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            result, valid = _validate_outlier_settings(
                {
                    "outlier_method": OutlierMethod.IQR.value,
                    "outlier_multiplier": 0.0,
                    "outlier_threshold": 20,
                }
            )
        assert valid is False
        assert result is None
        st_mock.error.assert_called_once()


# ============================================================================
# TESTS: _format_constraint_validation_error
# ============================================================================


class TestFormatConstraintValidationError:
    """Test _format_constraint_validation_error function."""

    def test_value_error_type(self):
        try:
            ConstraintBounds(hard_min=50.0, soft_min=10.0)
        except ValidationError as e:
            msg = _format_constraint_validation_error(e)
        assert "Invalid constraint configuration" in msg

    def test_float_not_finite_type(self):
        """Test float_not_finite error type produces finite-number message."""
        mock_error = MagicMock()
        mock_error.errors.return_value = [
            {
                "loc": ("hard_min",),
                "msg": "value is not a finite number",
                "type": "float_not_finite",
            }
        ]
        msg = _format_constraint_validation_error(mock_error)
        assert "Invalid constraint configuration" in msg
        assert "finite number" in msg

    def test_value_error_type_uses_msg(self):
        """Test value_error type includes the custom validation message."""
        mock_error = MagicMock()
        mock_error.errors.return_value = [
            {
                "loc": ("hard_min",),
                "msg": "Bounds must follow hierarchy",
                "type": "value_error",
            }
        ]
        msg = _format_constraint_validation_error(mock_error)
        assert "Bounds must follow hierarchy" in msg

    def test_other_error_type(self):
        """Test other error types fall through to field: msg format."""
        try:
            ConstraintBounds(hard_min="not_a_number")
        except ValidationError as e:
            msg = _format_constraint_validation_error(e)
        assert "Invalid constraint configuration" in msg


# ============================================================================
# TESTS: _format_outlier_validation_error
# ============================================================================


class TestFormatOutlierValidationError:
    """Test _format_outlier_validation_error function."""

    def test_formats_error_message(self):
        """Test that a ValidationError is formatted into a user-friendly string."""
        try:
            OutlierOptionsConfig(
                outlier_method=OutlierMethod.IQR.value,
                outlier_multiplier=0.0,
                outlier_threshold=20,
            )
        except ValidationError as e:
            msg = _format_outlier_validation_error(e)
        assert "Invalid outlier configuration" in msg

    def test_includes_field_name(self):
        """Test that the field name appears in the formatted error."""
        try:
            OutlierOptionsConfig(
                outlier_method=OutlierMethod.IQR.value,
                outlier_multiplier=0.0,
                outlier_threshold=20,
            )
        except ValidationError as e:
            msg = _format_outlier_validation_error(e)
        assert "outlier_multiplier" in msg

    def test_value_error_number_not_ge_branch(self):
        """Test the value_error.number.not_ge branch via mocked error."""
        mock_error = MagicMock()
        mock_error.errors.return_value = [
            {
                "loc": ("outlier_multiplier",),
                "msg": "value must be greater than 0",
                "type": "value_error.number.not_ge",
            }
        ]
        msg = _format_outlier_validation_error(mock_error)
        assert "Invalid outlier configuration" in msg
        assert "greater than or equal" in msg

    def test_value_error_number_not_le_branch(self):
        """Test the value_error.number.not_le branch via mocked error."""
        mock_error = MagicMock()
        mock_error.errors.return_value = [
            {
                "loc": ("outlier_multiplier",),
                "msg": "value must be less than or equal to 10",
                "type": "value_error.number.not_le",
            }
        ]
        msg = _format_outlier_validation_error(mock_error)
        assert "Invalid outlier configuration" in msg
        assert "less than or equal" in msg


# ============================================================================
# TESTS: _ensure_column_formats
# ============================================================================


class TestEnsureColumnFormats:
    """Test _ensure_column_formats function."""

    def test_returns_polars_dataframe(self, outlier_column_config):
        result = _ensure_column_formats(outlier_column_config)
        assert isinstance(result, pl.DataFrame)

    def test_preserves_column_names(self, outlier_column_config):
        result = _ensure_column_formats(outlier_column_config)
        assert set(outlier_column_config.columns) == set(result.columns)

    def test_casts_types_correctly(self, outlier_column_config):
        result = _ensure_column_formats(outlier_column_config)
        assert result.schema["outlier_multiplier"] == pl.Float64
        assert result.schema["outlier_threshold"] == pl.Int64


# ============================================================================
# TESTS: _render_constraint_metrics
# ============================================================================


class TestRenderConstraintMetrics:
    """Test _render_constraint_metrics function."""

    def test_calls_st_metric(self, sample_violation_data):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            _render_constraint_metrics(sample_violation_data)
        assert st_mock.metric.called or st_mock.columns.called


# ============================================================================
# TESTS: _render_outlier_metrics
# ============================================================================


class TestRenderOutlierMetrics:
    """Test _render_outlier_metrics function."""

    def test_with_enumerator(self, sample_outlier_data, outlier_settings):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            _render_outlier_metrics(sample_outlier_data, outlier_settings)
        assert st_mock.metric.called or st_mock.columns.called

    def test_without_enumerator(self, sample_outlier_data):
        settings = OutlierSettings(
            survey_key="survey_key",
            survey_id="survey_id",
            survey_date=None,
            enumerator=None,
            team=None,
        )
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            _render_outlier_metrics(sample_outlier_data, settings)
        assert st_mock.columns.called


# ============================================================================
# TESTS: _render_constraint_violations_table
# ============================================================================


class TestRenderConstraintViolationsTable:
    """Test _render_constraint_violations_table function."""

    def test_empty_data_shows_info(self, base_survey_data, outlier_settings):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            _render_constraint_violations_table(
                base_survey_data,
                pl.DataFrame(),
                outlier_settings,
                "settings.json",
            )
        st_mock.info.assert_called_once()

    def test_non_empty_data_shows_dataframe(self, base_survey_data, outlier_settings):
        violation_data = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "column name": ["col1"],
                "violation reason": ["below soft minimum"],
            }
        )
        with (
            patch("datasure.checks.outliers.report_ui.st") as st_mock,
            patch(
                "datasure.checks.outliers.report_ui.load_check_settings",
                return_value={},
            ),
            patch("datasure.checks.outliers.report_ui.save_check_settings"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.multiselect.return_value = []
            _render_constraint_violations_table(
                base_survey_data,
                violation_data,
                outlier_settings,
                "settings.json",
            )
        st_mock.dataframe.assert_called_once()

    def test_non_empty_with_extra_display_cols(
        self, base_survey_data, outlier_settings
    ):
        violation_data = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "violation reason": ["above hard maximum"],
            }
        )
        with (
            patch("datasure.checks.outliers.report_ui.st") as st_mock,
            patch(
                "datasure.checks.outliers.report_ui.load_check_settings",
                return_value={},
            ),
            patch("datasure.checks.outliers.report_ui.save_check_settings"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.multiselect.return_value = []
            _render_constraint_violations_table(
                base_survey_data,
                violation_data,
                outlier_settings,
                "settings.json",
            )
        st_mock.dataframe.assert_called_once()


# ============================================================================
# TESTS: _render_outlier_table
# ============================================================================


class TestRenderOutlierTable:
    """Test _render_outlier_table function."""

    def test_empty_data_shows_info(self, base_survey_data, outlier_settings):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            _render_outlier_table(
                base_survey_data,
                pl.DataFrame(),
                outlier_settings,
                "settings.json",
            )
        st_mock.info.assert_called_once()

    def test_non_empty_data_shows_dataframe(self, base_survey_data, outlier_settings):
        outliers_data = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "column name": ["col1"],
                "outlier reason": ["Value is above upper bound 50.00"],
            }
        )
        with (
            patch("datasure.checks.outliers.report_ui.st") as st_mock,
            patch(
                "datasure.checks.outliers.report_ui.load_check_settings",
                return_value={},
            ),
            patch("datasure.checks.outliers.report_ui.save_check_settings"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.multiselect.return_value = []
            _render_outlier_table(
                base_survey_data,
                outliers_data,
                outlier_settings,
                "settings.json",
            )
        st_mock.dataframe.assert_called_once()


# ============================================================================
# TESTS: _render_outlier_column_inspection
# ============================================================================


class TestRenderOutlierColumnInspection:
    """Test _render_outlier_column_inspection function."""

    def test_empty_outlier_data_shows_info(self, base_survey_data, outlier_settings):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            _render_outlier_column_inspection(
                base_survey_data, pl.DataFrame(), outlier_settings, "settings.json"
            )
        st_mock.info.assert_called_once()

    def test_no_selected_col_returns_early(self, base_survey_data, outlier_settings):
        outliers_data = pl.DataFrame(
            {"survey_key": ["K001"], "column name": ["survey_key"]}
        )
        with (
            patch("datasure.checks.outliers.report_ui.st") as st_mock,
            patch(
                "datasure.checks.outliers.report_ui.load_check_settings",
                return_value={},
            ),
            patch("datasure.checks.outliers.report_ui.save_check_settings"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.selectbox.return_value = None
            _render_outlier_column_inspection(
                base_survey_data, outliers_data, outlier_settings, "settings.json"
            )
        st_mock.info.assert_called()

    def test_col_not_in_data_raises(self, base_survey_data, outlier_settings):
        outliers_data = pl.DataFrame(
            {"survey_key": ["K001"], "column name": ["nonexistent_col"]}
        )
        with (
            patch("datasure.checks.outliers.report_ui.st") as st_mock,
            patch(
                "datasure.checks.outliers.report_ui.load_check_settings",
                return_value={},
            ),
            patch("datasure.checks.outliers.report_ui.save_check_settings"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.selectbox.return_value = "nonexistent_col"
            with pytest.raises(ValueError, match="not present in the data"):
                _render_outlier_column_inspection(
                    base_survey_data,
                    outliers_data,
                    outlier_settings,
                    "settings.json",
                )

    def test_normal_path_renders_chart_and_table(self, outlier_settings):
        data = pl.DataFrame(
            {
                "survey_key": ["K001", "K002"],
                "survey_id": ["S001", "S002"],
                "survey_date": ["2024-01-01", "2024-01-02"],
                "enumerator": ["E001", "E002"],
                "team": ["T1", "T2"],
                "numeric_col1": [1.0, 100.0],
            }
        )
        outliers_data = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "column name": ["numeric_col1"],
                "outlier reason": ["Value is above upper bound 50.00"],
            }
        )
        with (
            patch("datasure.checks.outliers.report_ui.st") as st_mock,
            patch(
                "datasure.checks.outliers.report_ui.load_check_settings",
                return_value={},
            ),
            patch("datasure.checks.outliers.report_ui.save_check_settings"),
            patch(
                "datasure.checks.outliers.report_ui._create_descriptive_stats"
            ) as mock_desc,
            patch("datasure.checks.outliers.report_ui._create_box_plot") as mock_box,
        ):
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.selectbox.return_value = "numeric_col1"
            st_mock.multiselect.return_value = []
            mock_desc.return_value = pl.DataFrame(
                {"statistic": ["count"], "value": ["2"]}
            )
            mock_box.return_value = MagicMock()
            _render_outlier_column_inspection(
                data, outliers_data, outlier_settings, "settings.json"
            )
        st_mock.dataframe.assert_called()


# ============================================================================
# TESTS: _create_search_type_info
# ============================================================================


class TestCreateSearchTypeInfo:
    """Test _create_search_type_info function."""

    def test_exact_search_type(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            _create_search_type_info(SearchType.EXACT.value)
        st_mock.info.assert_called_once()

    def test_startswith_search_type(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            _create_search_type_info(SearchType.STARTSWITH.value)
        st_mock.info.assert_called_once()

    def test_endswith_search_type(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            _create_search_type_info(SearchType.ENDSWITH.value)
        st_mock.info.assert_called_once()

    def test_contains_search_type(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            _create_search_type_info(SearchType.CONTAINS.value)
        st_mock.info.assert_called_once()

    def test_regex_search_type(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            _create_search_type_info(SearchType.REGEX.value)
        st_mock.info.assert_called_once()

    def test_unknown_type(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            _create_search_type_info("unknown_type")
        st_mock.info.assert_called_once()


# ============================================================================
# TESTS: _render_search_type_selection
# ============================================================================


class TestRenderSearchTypeSelection:
    """Test _render_search_type_selection function."""

    def test_exact_search_type(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.selectbox.return_value = SearchType.EXACT.value
            st_mock.multiselect.return_value = ["col1"]
            search_type, pattern, cols, _lock = _render_search_type_selection(
                ["col1", "col2"]
            )
        assert search_type == SearchType.EXACT.value
        assert pattern is None
        assert cols == ["col1"]

    def test_pattern_search_type_with_pattern(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.selectbox.return_value = SearchType.STARTSWITH.value
            st_mock.text_input.return_value = "num"
            search_type, pattern, cols, _lock = _render_search_type_selection(
                ["num_col1", "num_col2", "other"]
            )
        assert search_type == SearchType.STARTSWITH.value
        assert pattern == "num"
        assert "num_col1" in cols

    def test_pattern_search_type_no_pattern(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.selectbox.return_value = SearchType.CONTAINS.value
            st_mock.text_input.return_value = ""
            _search_type, _pattern, cols, lock = _render_search_type_selection(
                ["col1", "col2"]
            )
        assert cols == []
        assert lock is None


# ============================================================================
# TESTS: _render_column_grouping_options
# ============================================================================


class TestRenderColumnGroupingOptions:
    """Test _render_column_grouping_options function."""

    def test_basic_render(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.toggle.return_value = False
            group_cols, lock_cols = _render_column_grouping_options(
                ["col1", "col2"], SearchType.EXACT.value
            )
        assert isinstance(group_cols, bool)
        assert isinstance(lock_cols, bool)

    def test_returns_toggle_values(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.toggle.side_effect = [True, False]
            group_cols, lock_cols = _render_column_grouping_options(
                ["col1", "col2"], SearchType.STARTSWITH.value
            )
        assert group_cols is True
        assert lock_cols is False


# ============================================================================
# TESTS: _render_outlier_options
# ============================================================================


class TestRenderOutlierOptions:
    """Test _render_outlier_options function."""

    def test_outliers_enabled_returns_settings(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.toggle.return_value = True
            st_mock.selectbox.return_value = OutlierMethod.IQR.value
            st_mock.number_input.side_effect = [1.5, 20]
            enabled, settings, valid = _render_outlier_options()
        assert enabled is True
        assert settings is not None
        assert valid is True

    def test_outliers_enabled_sd_method(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.toggle.return_value = True
            st_mock.selectbox.return_value = OutlierMethod.SD.value
            st_mock.number_input.side_effect = [3.0, 30]
            enabled, _settings, valid = _render_outlier_options()
        assert enabled is True
        assert valid is True

    def test_outliers_disabled_returns_none(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.toggle.return_value = False
            enabled, settings, valid = _render_outlier_options()
        assert enabled is False
        assert settings is None
        assert valid is True


# ============================================================================
# TESTS: _render_constraint_options
# ============================================================================


class TestRenderConstraintOptions:
    """Test _render_constraint_options function."""

    def test_valid_settings_returns_true(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.number_input.return_value = None
            _settings, valid = _render_constraint_options()
        assert valid is True

    def test_invalid_settings_calls_error(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.columns.side_effect = _columns_side_effect
            st_mock.number_input.side_effect = [50.0, 10.0, None, None]
            _settings, valid = _render_constraint_options()
        assert valid is False
        st_mock.error.assert_called_once()


# ============================================================================
# TESTS: _render_outlier_settings_table
# ============================================================================


class TestRenderOutlierSettingsTable:
    """Test _render_outlier_settings_table function."""

    def test_renders_dataframe(self, outlier_column_config):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            _render_outlier_settings_table(outlier_column_config)
        st_mock.dataframe.assert_called_once()


# ============================================================================
# TESTS: _render_outlier_column_actions
# ============================================================================


class TestRenderOutlierColumnActions:
    """Test _render_outlier_column_actions function."""

    def test_empty_settings_shows_info(self):
        with (
            patch("datasure.checks.outliers.report_ui.st") as st_mock,
            patch(
                "datasure.checks.outliers.report_ui.duckdb_get_table",
                return_value=pl.DataFrame(),
            ),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            _render_outlier_column_actions("proj1", "page1", ["col1"])
        assert st_mock.info.call_count >= 1

    def test_non_empty_settings_calls_render_table(self, outlier_column_config):
        with (
            patch("datasure.checks.outliers.report_ui.st") as st_mock,
            patch(
                "datasure.checks.outliers.report_ui.duckdb_get_table",
                return_value=outlier_column_config,
            ),
            patch(
                "datasure.checks.outliers.report_ui._render_outlier_settings_table"
            ) as mock_render,
            patch("datasure.checks.outliers.report_ui._delete_outlier_column"),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            _render_outlier_column_actions("proj1", "page1", ["col1"])
        mock_render.assert_called_once()


# ============================================================================
# TESTS: _update_outlier_column_config
# ============================================================================


class TestUpdateOutlierColumnConfig:
    """Test _update_outlier_column_config function."""

    def test_empty_existing_config_saves_new(self):
        settings = OutlierOptionsConfig(
            outlier_method=OutlierMethod.IQR,
            outlier_multiplier=1.5,
            outlier_threshold=20,
        )
        bounds = ConstraintBounds(soft_min=0.0, soft_max=100.0)
        with (
            patch(
                "datasure.checks.outliers.report_ui.duckdb_get_table",
                return_value=pl.DataFrame(),
            ),
            patch("datasure.checks.outliers.report_ui.duckdb_save_table") as mock_save,
        ):
            _update_outlier_column_config(
                "proj1",
                "page1",
                "exact",
                None,
                ["col1"],
                False,
                False,
                True,
                settings,
                bounds,
            )
        mock_save.assert_called_once()

    def test_non_empty_existing_config_concatenates(self, outlier_column_config):
        settings = OutlierOptionsConfig(
            outlier_method=OutlierMethod.IQR,
            outlier_multiplier=1.5,
            outlier_threshold=20,
        )
        bounds = ConstraintBounds(soft_min=0.0, soft_max=100.0)
        with (
            patch(
                "datasure.checks.outliers.report_ui.duckdb_get_table",
                return_value=outlier_column_config,
            ),
            patch("datasure.checks.outliers.report_ui.duckdb_save_table") as mock_save,
        ):
            _update_outlier_column_config(
                "proj1",
                "page1",
                "exact",
                None,
                ["col2"],
                False,
                False,
                True,
                settings,
                bounds,
            )
        mock_save.assert_called_once()
        saved_df = mock_save.call_args[0][1]
        assert len(saved_df) == 2

    def test_outlier_settings_none(self):
        bounds = ConstraintBounds(soft_min=0.0, soft_max=100.0)
        with (
            patch(
                "datasure.checks.outliers.report_ui.duckdb_get_table",
                return_value=pl.DataFrame(),
            ),
            patch("datasure.checks.outliers.report_ui.duckdb_save_table") as mock_save,
        ):
            _update_outlier_column_config(
                "proj1",
                "page1",
                "exact",
                None,
                ["col1"],
                False,
                False,
                False,
                None,
                bounds,
            )
        mock_save.assert_called_once()


# ============================================================================
# TESTS: _delete_outlier_column
# ============================================================================


class TestDeleteOutlierColumn:
    """Test _delete_outlier_column function."""

    def test_empty_settings_shows_info(self):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            _delete_outlier_column("proj1", "page1", pl.DataFrame())
        st_mock.info.assert_called_once()

    def test_non_empty_shows_selectbox_and_button(self, outlier_column_config):
        with patch("datasure.checks.outliers.report_ui.st") as st_mock:
            st_mock.selectbox.return_value = "0 - exact - "
            st_mock.button.return_value = False
            _delete_outlier_column("proj1", "page1", outlier_column_config)
        st_mock.selectbox.assert_called_once()

    def test_delete_on_button_click(self, outlier_column_config):
        with (
            patch("datasure.checks.outliers.report_ui.st") as st_mock,
            patch("datasure.checks.outliers.report_ui.duckdb_save_table") as mock_save,
        ):
            st_mock.selectbox.return_value = "0 - exact - "
            st_mock.button.return_value = True
            _delete_outlier_column("proj1", "page1", outlier_column_config)
        mock_save.assert_called_once()


# ============================================================================
# TESTS: _add_outlier_column (via reimport)
# ============================================================================


class TestAddOutlierColumn:
    """Test _add_outlier_column function."""

    def test_no_cols_selected_does_not_save(self, report_ui_mod):
        """When no columns selected, skip grouping/options rendering."""
        mock_sel = MagicMock(return_value=(SearchType.EXACT.value, None, [], None))
        with patch.object(report_ui_mod, "_render_search_type_selection", mock_sel):
            report_ui_mod._add_outlier_column("proj1", "page1", ["col1", "col2"])
        mock_sel.assert_called_once()

    def test_with_cols_selected_renders_options(self, report_ui_mod):
        """When columns are selected, all option panels are rendered."""
        settings = OutlierOptionsConfig(
            outlier_method=OutlierMethod.IQR,
            outlier_multiplier=1.5,
            outlier_threshold=20,
        )
        mock_sel = MagicMock(
            return_value=(SearchType.EXACT.value, None, ["col1"], None)
        )
        mock_grp = MagicMock(return_value=(False, False))
        mock_out = MagicMock(return_value=(True, settings, True))
        mock_con = MagicMock(return_value=(ConstraintBounds(), True))
        with (
            patch.object(report_ui_mod, "_render_search_type_selection", mock_sel),
            patch.object(report_ui_mod, "_render_column_grouping_options", mock_grp),
            patch.object(report_ui_mod, "_render_outlier_options", mock_out),
            patch.object(report_ui_mod, "_render_constraint_options", mock_con),
        ):
            report_ui_mod.st.button.return_value = False
            report_ui_mod._add_outlier_column("proj1", "page1", ["col1", "col2"])
        mock_grp.assert_called_once()
        mock_out.assert_called_once()
        mock_con.assert_called_once()


# ============================================================================
# TESTS: outliers_report (main function)
# ============================================================================


class TestOutliersReport:
    """Test outliers_report main function."""

    def test_empty_column_config_returns_early(
        self, base_survey_data, survey_columns_mock, outlier_config_dict
    ):
        settings = OutlierSettings(**outlier_config_dict)
        with (
            patch("datasure.checks.outliers.report_ui.st") as st_mock,
            patch(
                "datasure.checks.outliers.report_ui.outliers_report_settings",
                return_value=settings,
            ),
            patch("datasure.checks.outliers.report_ui._render_outlier_column_actions"),
            patch(
                "datasure.checks.outliers.report_ui.duckdb_get_table",
                return_value=pl.DataFrame(),
            ),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            outliers_report(
                "proj1",
                "page1",
                base_survey_data,
                "settings.json",
                outlier_config_dict,
                survey_columns_mock,
            )
        st_mock.title.assert_called()

    def test_with_constraint_violations(
        self,
        base_survey_data,
        survey_columns_mock,
        outlier_config_dict,
        outlier_column_config,
    ):
        settings = OutlierSettings(**outlier_config_dict)
        constraint_violations = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "column name": ["col1"],
                "violation reason": ["below soft minimum"],
            }
        )
        with (
            patch("datasure.checks.outliers.report_ui.st") as st_mock,
            patch(
                "datasure.checks.outliers.report_ui.outliers_report_settings",
                return_value=settings,
            ),
            patch("datasure.checks.outliers.report_ui._render_outlier_column_actions"),
            patch(
                "datasure.checks.outliers.report_ui.duckdb_get_table",
                return_value=outlier_column_config,
            ),
            patch("datasure.checks.outliers.report_ui.duckdb_save_table"),
            patch(
                "datasure.checks.outliers.report_ui.compute_constraint_violations",
                return_value=constraint_violations,
            ),
            patch(
                "datasure.checks.outliers.report_ui.compute_outlier_output",
                return_value=pl.DataFrame(),
            ),
            patch("datasure.checks.outliers.report_ui._render_constraint_metrics"),
            patch(
                "datasure.checks.outliers.report_ui._render_constraint_violations_table"
            ),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            outliers_report(
                "proj1",
                "page1",
                base_survey_data,
                "settings.json",
                outlier_config_dict,
                survey_columns_mock,
            )
        st_mock.info.assert_called()

    def test_with_outliers(
        self,
        base_survey_data,
        survey_columns_mock,
        outlier_config_dict,
        outlier_column_config,
    ):
        settings = OutlierSettings(**outlier_config_dict)
        outlier_data = pl.DataFrame(
            {
                "survey_key": ["K001"],
                "column name": ["col1"],
                "outlier reason": ["Value is above upper bound 50.00"],
            }
        )
        with (
            patch("datasure.checks.outliers.report_ui.st") as st_mock,
            patch(
                "datasure.checks.outliers.report_ui.outliers_report_settings",
                return_value=settings,
            ),
            patch("datasure.checks.outliers.report_ui._render_outlier_column_actions"),
            patch(
                "datasure.checks.outliers.report_ui.duckdb_get_table",
                return_value=outlier_column_config,
            ),
            patch("datasure.checks.outliers.report_ui.duckdb_save_table"),
            patch(
                "datasure.checks.outliers.report_ui.compute_constraint_violations",
                return_value=pl.DataFrame(),
            ),
            patch(
                "datasure.checks.outliers.report_ui.compute_outlier_output",
                return_value=outlier_data,
            ),
            patch("datasure.checks.outliers.report_ui._render_outlier_metrics"),
            patch(
                "datasure.checks.outliers.report_ui._render_outlier_column_inspection"
            ),
        ):
            st_mock.columns.side_effect = _columns_side_effect
            outliers_report(
                "proj1",
                "page1",
                base_survey_data,
                "settings.json",
                outlier_config_dict,
                survey_columns_mock,
            )
        st_mock.info.assert_called()
