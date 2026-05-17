import datetime
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import polars as pl
import pytest
from pydantic import ValidationError

from datasure.checks.missing import (
    MissingCode,
    MissingSummaryStats,
    _compute_missing_data_paired,
    _create_binary_missing_indicator,
    _get_all_missing_codes,
    _get_missing_code_pairs,
    _safe_percentage,
    _try_convert_code_to_column_type,
    compute_filtered_missing_columns,
    compute_missing_columns,
    compute_missing_compare,
    compute_missing_correlation,
    compute_missing_matrix,
    compute_missing_over_time,
    compute_missing_summary,
    get_null_list,
    missing_columns,
    missing_compare,
    missing_correlation,
    missing_matrix,
    missing_over_time,
    missing_report,
    missing_summary,
    render_missing_codes_table,
)

# ==============================================================================
# Mock Streamlit Helper
# ==============================================================================


def _make_mock_st():
    """Create a mock Streamlit module for testing UI render functions."""

    def make_col():
        col = MagicMock()
        col.selectbox.return_value = None
        col.text_input.return_value = ""
        col.multiselect.return_value = []
        col.slider.return_value = 0
        col.toggle.return_value = False
        col.button.return_value = False
        return col

    def _col_factory(n_or_spec, **kwargs):
        if isinstance(n_or_spec, int):
            n = n_or_spec
        elif isinstance(n_or_spec, list | tuple):
            n = len(n_or_spec)
        else:
            n = 2
        return tuple(make_col() for _ in range(n))

    mock_st = MagicMock()
    mock_st.columns.side_effect = _col_factory
    mock_st.selectbox.return_value = None
    mock_st.multiselect.return_value = []
    mock_st.slider.return_value = 0
    mock_st.toggle.return_value = False
    mock_st.button.return_value = False
    mock_st.text_input.return_value = ""
    mock_st.session_state = {}
    return mock_st


#  ==============================================================================
# Test Fixtures
# ==============================================================================


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests.
    """
    pass


@pytest.fixture
def sample_missing_codes_polars():
    """Fixture for Polars DataFrame with missing codes."""
    return pl.DataFrame(
        {
            "label": ["Don't Know", "Refuse", "Not Applicable"],
            "codes": ["-999, -998", "-888", "-777, -776, -775"],
        }
    )


@pytest.fixture
def sample_data_polars():
    """Fixture for Polars DataFrame with sample data."""
    return pl.DataFrame(
        {
            "age": [25, None, 35, -999, 45],
            "gender": [1, 2, None, 2, -888],
            "income": [50000, 60000, 70000, 80000, 90000],
        }
    )


@pytest.fixture
def sample_settings_dict():
    """Fixture that returns a sample settings dictionary for missing values tests."""
    return {
        "Missing Labels": [
            "Don't Know",
            "Refuse to Answer",
            "Not Applicable",
        ],
        "Missing Codes": ["-999, .999", "-888, .888", "-777, .777"],
    }


@pytest.fixture
def sample_settings_df(sample_settings_dict):
    """Fixture that returns a sample settings DataFrame for missing values tests."""
    return pd.DataFrame(sample_settings_dict)


@pytest.fixture
def df_no_missing():
    """Fixture that returns a DataFrame with no missing values."""
    return pd.DataFrame({"age": [1, 2, 3], "gender": [4, 5, 6]})


@pytest.fixture
def df_some_missing():
    """Fixture that returns a DataFrame with some missing values."""
    return pd.DataFrame({"age": [1, np.nan, 3], "gender": [np.nan, 5, 6]})


@pytest.fixture
def df_all_missing():
    """Fixture that returns a DataFrame where all values are missing."""
    return pd.DataFrame(
        {"age": [np.nan, np.nan, np.nan], "gender": [np.nan, np.nan, np.nan]}
    )


@pytest.fixture
def df_with_dates():
    """Fixture that returns a DataFrame with datetime values for time series tests."""
    dates = pd.date_range("2023-01-01", periods=5)
    return pd.DataFrame(
        {
            "date": dates,
            "age": [1, np.nan, 3, np.nan, 5],
            "gender": [np.nan, 2, np.nan, 4, 5],
            "C": [1, 2, 3, 4, 5],
        }
    )


@pytest.fixture
def df_with_groups():
    """Fixture that returns a DataFrame with locations for comparison tests."""
    return pd.DataFrame(
        {
            "location": ["north", "north", "east", "east", "south"],
            "age": [1, np.nan, 3, np.nan, 5],
            "gender": [np.nan, 2, np.nan, 4, 5],
        }
    )


def random_age_gender_df(n):
    """Generate a random DataFrame with
    'age' and   'gender' columns.
    """
    np.random.seed(42)
    return pd.DataFrame(
        {
            "age": np.random.randint(2, 76, size=n),
            "gender": np.random.randint(0, 5, size=n),
        }
    )


@pytest.fixture
def patched_missing():
    """Fixture that patches all Streamlit and external dependencies for UI tests."""
    mock_st = _make_mock_st()
    with (
        patch("datasure.checks.missing.st", mock_st),
        patch("datasure.checks.missing.is_demo_project", return_value=False),
        patch(
            "datasure.checks.missing.load_missing_codes_from_db",
            return_value=pl.DataFrame(schema={"label": pl.Utf8, "codes": pl.Utf8}),
        ),
        patch("datasure.checks.missing.add_missing_code"),
        patch("datasure.checks.missing.duckdb_save_table"),
        patch("datasure.checks.missing.load_check_settings", return_value={}),
        patch("datasure.checks.missing.save_check_settings"),
        patch("datasure.checks.missing.trigger_save"),
        patch("datasure.checks.missing.demo_callout"),
        patch("datasure.utils.onboarding_utils.is_demo_project", return_value=False),
    ):
        yield mock_st


# ==============================================================================
# Tests for Pydantic Models
# ==============================================================================


def test_missing_code_model_with_string_codes():
    """Test MissingCode model with comma-separated string."""
    code = MissingCode(label="Don't Know", codes="-999, -998, -997")

    assert code.label == "Don't Know"
    assert len(code.codes) == 3
    assert "-999" in code.codes
    assert "-998" in code.codes
    assert "-997" in code.codes


def test_missing_code_model_with_list_codes():
    """Test MissingCode model with list of codes."""
    code = MissingCode(label="Refuse", codes=["-888", "-887"])

    assert code.label == "Refuse"
    assert len(code.codes) == 2
    assert "-888" in code.codes
    assert "-887" in code.codes


def test_missing_code_model_codes_as_string():
    """Test MissingCode codes_as_string method."""
    code = MissingCode(label="Test", codes=["-999", "-888", "-777"])

    result = code.codes_as_string()
    assert result == "-999, -888, -777"


def test_missing_code_model_empty_label():
    """Test MissingCode model rejects empty label."""
    with pytest.raises(ValidationError):
        MissingCode(label="", codes="-999")


def test_missing_code_model_empty_codes():
    """Test MissingCode model rejects empty codes list."""
    with pytest.raises(ValidationError):
        MissingCode(label="Test", codes=[])


def test_missing_code_model_strips_whitespace():
    """Test MissingCode model strips whitespace from codes."""
    code = MissingCode(label="Test", codes="  -999  ,  -888  ")

    assert code.codes == ["-999", "-888"]


def test_missing_summary_stats_model():
    """Test MissingSummaryStats model creation."""
    stats = MissingSummaryStats(
        mean_missing_pct=10.5,
        all_missing_pct=5.0,
        any_missing_pct=50.0,
        no_missing_pct=50.0,
    )

    assert stats.mean_missing_pct == 10.5
    assert stats.all_missing_pct == 5.0
    assert stats.any_missing_pct == 50.0
    assert stats.no_missing_pct == 50.0


def test_missing_summary_stats_model_validation():
    """Test MissingSummaryStats model validates percentages."""
    with pytest.raises(ValidationError):
        MissingSummaryStats(
            mean_missing_pct=150.0,  # Invalid: > 100
            all_missing_pct=0.0,
            any_missing_pct=0.0,
            no_missing_pct=100.0,
        )


# ==============================================================================
# Tests for Helper Functions
# ==============================================================================


def test_create_binary_missing_indicator():
    """Test _create_binary_missing_indicator converts to binary."""
    data = pl.DataFrame(
        {
            "col1": [0, 1, 2, 0],
            "col2": [0, 0, 3, 0],
        }
    )

    result = _create_binary_missing_indicator(data)

    assert result["col1"].to_list() == [0, 1, 1, 0]
    assert result["col2"].to_list() == [0, 0, 1, 0]


def test_safe_percentage_normal():
    """Test _safe_percentage with normal values."""
    result = _safe_percentage(25, 100)
    assert result == 25.0


def test_safe_percentage_zero_denominator():
    """Test _safe_percentage handles zero denominator."""
    result = _safe_percentage(10, 0)
    assert result == 0.0


def test_safe_percentage_float_values():
    """Test _safe_percentage with float values."""
    result = _safe_percentage(33.5, 100.0)
    assert result == 33.5


def test_try_convert_code_to_column_type_integer():
    """Test _try_convert_code_to_column_type with integer column."""
    converted, success = _try_convert_code_to_column_type("-999", pl.Int64, "age")

    assert success is True
    assert converted == -999
    assert isinstance(converted, int)


def test_try_convert_code_to_column_type_float():
    """Test _try_convert_code_to_column_type with float column."""
    converted, success = _try_convert_code_to_column_type("-999.5", pl.Float64, "score")

    assert success is True
    assert converted == -999.5
    assert isinstance(converted, float)


def test_try_convert_code_to_column_type_string():
    """Test _try_convert_code_to_column_type with string column."""
    converted, success = _try_convert_code_to_column_type("-999", pl.Utf8, "name")

    assert success is True
    assert converted == "-999"
    assert isinstance(converted, str)


def test_try_convert_code_to_column_type_boolean():
    """Test _try_convert_code_to_column_type with boolean column."""
    converted_true, success_true = _try_convert_code_to_column_type(
        "true", pl.Boolean, "flag"
    )
    converted_false, success_false = _try_convert_code_to_column_type(
        "false", pl.Boolean, "flag"
    )

    assert success_true is True
    assert converted_true is True
    assert success_false is True
    assert converted_false is False


def test_try_convert_code_to_column_type_invalid_conversion():
    """Test _try_convert_code_to_column_type with invalid conversion."""
    converted, success = _try_convert_code_to_column_type("abc", pl.Int64, "age")

    assert success is False
    assert converted is None


def test_try_convert_code_to_column_type_date_returns_failure():
    """Test _try_convert_code_to_column_type returns failure for date types."""
    converted, success = _try_convert_code_to_column_type("-999", pl.Date, "date_col")

    assert success is False
    assert converted is None


def test_get_all_missing_codes():
    """Test _get_all_missing_codes extracts all codes."""
    missing_codes_df = pl.DataFrame(
        {
            "label": ["DontKnow", "Refuse"],
            "codes": ["-999, -998", "-888"],
        }
    )

    result = _get_all_missing_codes(missing_codes_df)

    assert len(result) == 3
    assert "-999" in result
    assert "-998" in result
    assert "-888" in result


def test_get_all_missing_codes_empty_df():
    """Test _get_all_missing_codes with empty DataFrame."""
    missing_codes_df = pl.DataFrame(schema={"label": pl.Utf8, "codes": pl.Utf8})

    result = _get_all_missing_codes(missing_codes_df)

    assert result == []


def test_get_missing_code_pairs():
    """Test _get_missing_code_pairs creates correct mapping."""
    missing_codes_df = pl.DataFrame(
        {
            "label": ["DontKnow", "Refuse"],
            "codes": ["-999, -998", "-888"],
        }
    )

    result = _get_missing_code_pairs(missing_codes_df)

    assert len(result) == 2
    assert result["DontKnow"] == ["-999", "-998"]
    assert result["Refuse"] == ["-888"]


def test_compute_missing_data_paired():
    """Test _compute_missing_data_paired marks missing values correctly."""
    data = pl.DataFrame(
        {
            "age": [25, None, -999, 45],
            "gender": [1, -888, None, 2],
        }
    )

    missing_codes_df = pl.DataFrame(
        {
            "label": ["DontKnow", "Refuse"],
            "codes": ["-999", "-888"],
        }
    )

    result = _compute_missing_data_paired(data, missing_codes_df)

    # Check shape is preserved
    assert result.shape == data.shape

    # Check that nulls are marked as 1
    assert result["age"][1] == 1  # None
    assert result["gender"][2] == 1  # None

    # Check that special codes are marked as 2+ based on position
    assert result["age"][2] == 2  # -999 (DontKnow, first code)
    assert result["gender"][1] == 3  # -888 (Refuse, second code)

    # Check that normal values are marked as 0
    assert result["age"][0] == 0  # 25
    assert result["gender"][0] == 0  # 1


def test_compute_missing_data_paired_with_datetime():
    """Test _compute_missing_data_paired handles datetime columns."""
    data = pl.DataFrame(
        {
            "date": [pl.date(2023, 1, 1), None, pl.date(2023, 1, 3)],
            "value": [1, -999, 3],
        }
    )

    missing_codes_df = pl.DataFrame(
        {
            "label": ["Missing"],
            "codes": ["-999"],
        }
    )

    result = _compute_missing_data_paired(data, missing_codes_df)

    # Date column should only have 0 for non-null and 1 for null
    assert result["date"][0] == 0
    assert result["date"][1] == 1
    assert result["date"][2] == 0

    # Value column should have special code marking
    assert result["value"][1] == 2  # -999 marked as missing code


#  ==============================================================================
# Tests for Core Computation Functions (Updated for Polars)
# ==============================================================================


# ----------------------- compute_missing_summary Tests -----------------------


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_summary_no_missing():
    """Test compute_missing_summary with DataFrame having no missing values."""
    missing_data = pl.DataFrame(
        {
            "age": [0, 0, 0, 0],
            "gender": [0, 0, 0, 0],
            "income": [0, 0, 0, 0],
        }
    )

    result = compute_missing_summary(missing_data)

    assert isinstance(result, MissingSummaryStats)
    assert result.mean_missing_pct == 0.0
    assert result.all_missing_pct == 0.0
    assert result.any_missing_pct == 0.0
    assert result.no_missing_pct == 100.0


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_summary_some_missing():
    """Test compute_missing_summary with DataFrame having some missing values."""
    missing_data = pl.DataFrame(
        {
            "age": [0, 1, 0, 0],  # 25% missing
            "gender": [0, 0, 1, 0],  # 25% missing
            "income": [0, 0, 0, 0],  # 0% missing
        }
    )

    result = compute_missing_summary(missing_data)

    assert isinstance(result, MissingSummaryStats)
    # Mean missing: (25 + 25 + 0) / 3 = 16.67%
    assert 16.0 < result.mean_missing_pct < 17.0
    assert result.all_missing_pct == 0.0  # No columns with all missing
    # 2 out of 3 columns have any missing = 66.67%
    assert 66.0 < result.any_missing_pct < 67.0
    # 1 out of 3 columns have no missing = 33.33%
    assert 33.0 < result.no_missing_pct < 34.0


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_summary_all_missing():
    """Test compute_missing_summary with DataFrame having all missing values."""
    missing_data = pl.DataFrame(
        {
            "age": [1, 1, 1, 1],
            "gender": [2, 2, 2, 2],
            "income": [1, 2, 1, 2],
        }
    )

    result = compute_missing_summary(missing_data)

    assert isinstance(result, MissingSummaryStats)
    assert result.mean_missing_pct == 100.0
    assert result.all_missing_pct == 100.0
    assert result.any_missing_pct == 100.0
    assert result.no_missing_pct == 0.0


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_summary_empty_columns():
    """Test compute_missing_summary with DataFrame having empty columns."""
    missing_data = pl.DataFrame(
        {
            "age": [],
            "gender": [],
        }
    )

    result = compute_missing_summary(missing_data)

    assert isinstance(result, MissingSummaryStats)
    # Empty DataFrame should return default values
    assert result.mean_missing_pct == 0.0
    assert result.all_missing_pct == 0.0
    assert result.any_missing_pct == 0.0
    assert result.no_missing_pct == 100.0


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_summary_single_column():
    """Test compute_missing_summary with single column DataFrame."""
    missing_data = pl.DataFrame(
        {
            "age": [0, 1, 0, 1, 0],  # 40% missing
        }
    )

    result = compute_missing_summary(missing_data)

    assert isinstance(result, MissingSummaryStats)
    assert result.mean_missing_pct == 40.0
    assert result.all_missing_pct == 0.0
    assert result.any_missing_pct == 100.0  # 1 of 1 column has missing
    assert result.no_missing_pct == 0.0


# ----------------------- compute_missing_columns Tests -----------------------


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_columns_basic():
    """Test compute_missing_columns with basic missing values."""
    missing_data = pl.DataFrame(
        {
            "age": [0, 1, 2, 0],  # 1 null, 1 DontKnow
            "gender": [0, 0, 0, 3],  # 1 Refuse
        }
    )

    missing_codes_df = pl.DataFrame(
        {
            "label": ["DontKnow", "Refuse"],
            "codes": ["-999", "-888"],
        }
    )

    result = compute_missing_columns(missing_data, missing_codes_df)

    assert isinstance(result, pd.DataFrame)
    assert result.shape[0] == 2  # 2 columns
    assert "Column" in result.columns
    assert "Null Values" in result.columns
    assert "% Null Values" in result.columns
    assert "DontKnow" in result.columns
    assert "% DontKnow" in result.columns
    assert "Refuse" in result.columns
    assert "% Refuse" in result.columns
    assert "Total Missing" in result.columns
    assert "% Total Missing" in result.columns

    # Check age column
    age_row = result[result["Column"] == "age"].iloc[0]
    assert age_row["Null Values"] == 1
    assert age_row["% Null Values"] == 25.0
    assert age_row["DontKnow"] == 1
    assert age_row["% DontKnow"] == 25.0
    assert age_row["Refuse"] == 0
    assert age_row["Total Missing"] == 2
    assert age_row["% Total Missing"] == 50.0

    # Check gender column
    gender_row = result[result["Column"] == "gender"].iloc[0]
    assert gender_row["Null Values"] == 0
    assert gender_row["Refuse"] == 1
    assert gender_row["% Refuse"] == 25.0
    assert gender_row["Total Missing"] == 1
    assert gender_row["% Total Missing"] == 25.0


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_columns_multiple_codes_per_label():
    """Test compute_missing_columns with multiple codes per label."""
    missing_data = pl.DataFrame(
        {
            "age": [
                0,
                1,
                2,
                2,
                0,
            ],  # 1 null, 2 DontKnow (codes -999 and -998 both map to code 2)
        }
    )

    missing_codes_df = pl.DataFrame(
        {
            "label": ["DontKnow"],
            "codes": ["-999, -998"],
        }
    )

    result = compute_missing_columns(missing_data, missing_codes_df)

    assert isinstance(result, pd.DataFrame)
    age_row = result[result["Column"] == "age"].iloc[0]
    assert age_row["Null Values"] == 1
    assert age_row["DontKnow"] == 2  # Both -999 and -998 counted
    assert age_row["Total Missing"] == 3


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_columns_no_missing():
    """Test compute_missing_columns with no missing values."""
    missing_data = pl.DataFrame(
        {
            "age": [0, 0, 0, 0],
            "gender": [0, 0, 0, 0],
        }
    )

    missing_codes_df = pl.DataFrame(
        {
            "label": ["DontKnow"],
            "codes": ["-999"],
        }
    )

    result = compute_missing_columns(missing_data, missing_codes_df)

    assert isinstance(result, pd.DataFrame)
    assert result.shape[0] == 2
    assert all(result["Total Missing"] == 0)
    assert all(result["% Total Missing"] == 0.0)


# -------------------- compute_filtered_missing_columns Tests ------------------


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_filtered_missing_columns_basic():
    """Test compute_filtered_missing_columns with basic threshold filtering."""
    data = pd.DataFrame(
        {
            "Column": ["A", "B", "C"],
            "Null Values": [5, 10, 0],
            "% Null Values": [25.0, 50.0, 0.0],
            "% Total Missing": [35.0, 80.0, 5.0],
            "% CustomMissing": [10.0, 30.0, 5.0],
        }
    )

    filtered_data, perc_cols, vmin, vmax = compute_filtered_missing_columns(
        data, mv_threshold=40
    )

    assert isinstance(filtered_data, pd.DataFrame)
    assert filtered_data.shape[0] == 1  # Only B should pass threshold
    assert "B" in filtered_data["Column"].values
    assert "% Null Values" in perc_cols
    assert "% Total Missing" in perc_cols
    assert "% CustomMissing" in perc_cols
    assert vmin == 30.0  # Minimum percentage in filtered data
    assert vmax == 80.0  # Maximum percentage in filtered data


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_filtered_missing_columns_no_match():
    """Test compute_filtered_missing_columns when no columns match threshold."""
    data = pd.DataFrame(
        {
            "Column": ["A", "B"],
            "Null Values": [0, 0],
            "% Null Values": [0.0, 0.0],
            "% Total Missing": [10.0, 20.0],
        }
    )

    filtered_data, perc_cols, vmin, vmax = compute_filtered_missing_columns(
        data, mv_threshold=50
    )

    assert filtered_data.empty
    assert isinstance(perc_cols, list)
    assert vmin == 0.0
    assert vmax == 100.0


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_filtered_missing_columns_all_match():
    """Test compute_filtered_missing_columns when all columns match threshold."""
    data = pd.DataFrame(
        {
            "Column": ["A", "B", "C"],
            "Null Values": [10, 20, 30],
            "% Null Values": [50.0, 100.0, 75.0],
            "% Total Missing": [60.0, 100.0, 80.0],
        }
    )

    filtered_data, _perc_cols, vmin, vmax = compute_filtered_missing_columns(
        data, mv_threshold=0
    )

    assert filtered_data.shape[0] == 3  # All columns pass
    assert vmin == 50.0
    assert vmax == 100.0


# ---------------------- compute_missing_over_time Tests ----------------------


def test_compute_missing_over_time_basic():
    """Test compute_missing_over_time with basic date grouping.

    Note: Skipping @patch decorator due to caching hashing issues with datetime columns.
    """
    import datetime

    missing_data = pl.DataFrame(
        {
            "age": [0, 1, 0, 1],
            "gender": [0, 0, 1, 1],
        }
    )

    data = pl.DataFrame(
        {
            "date": [
                datetime.datetime(2023, 1, 1),
                datetime.datetime(2023, 1, 1),
                datetime.datetime(2023, 1, 2),
                datetime.datetime(2023, 1, 2),
            ],
            "age": [25, None, 30, None],
            "gender": [1, 2, None, None],
        }
    )

    result = compute_missing_over_time(missing_data, data, "date")

    assert isinstance(result, pd.DataFrame)
    assert "missingness_trend_date" in result.columns
    assert "missingness_rate" in result.columns
    assert result.shape[0] == 2  # 2 unique dates

    # First date: 1 missing out of 4 values (2 rows * 2 cols) = 25%
    assert result.iloc[0]["missingness_rate"] == 25.0
    # Second date: 3 missing out of 4 values = 75%
    assert result.iloc[1]["missingness_rate"] == 75.0


def test_compute_missing_over_time_single_date():
    """Test compute_missing_over_time with single date.

    Note: Skipping @patch decorator due to caching hashing issues with datetime columns.
    """
    import datetime

    missing_data = pl.DataFrame(
        {
            "age": [0, 1, 0],
            "gender": [0, 0, 1],
        }
    )

    data = pl.DataFrame(
        {
            "date": [
                datetime.datetime(2023, 1, 1),
                datetime.datetime(2023, 1, 1),
                datetime.datetime(2023, 1, 1),
            ],
            "age": [25, None, 30],
            "gender": [1, 2, None],
        }
    )

    result = compute_missing_over_time(missing_data, data, "date")

    assert result.shape[0] == 1
    # 2 missing out of 6 values (3 rows * 2 cols) = 33.33%
    assert 33.0 < result.iloc[0]["missingness_rate"] < 34.0


# ---------------------- compute_missing_compare Tests ------------------------


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_compare_basic():
    """Test compute_missing_compare with basic grouping."""
    missing_data = pl.DataFrame(
        {
            "age": [0, 1, 0, 1],
            "income": [0, 0, 1, 1],
        }
    )

    data = pl.DataFrame(
        {
            "group": ["A", "A", "B", "B"],
            "age": [25, None, 30, None],
            "income": [1000, 2000, None, None],
        }
    )

    result, vmin, vmax = compute_missing_compare(
        missing_data, data, "group", ["age", "income"]
    )

    assert isinstance(result, pd.DataFrame)
    assert "values (count)" in result.columns
    assert "values (%)" in result.columns
    assert "age" in result.columns
    assert "income" in result.columns

    # Group A: 1 missing age out of 2 = 50%, 0 missing income = 0%
    assert result.loc["A", "age"] == 50.0
    assert result.loc["A", "income"] == 0.0

    # Group B: 1 missing age out of 2 = 50%, 2 missing income out of 2 = 100%
    assert result.loc["B", "age"] == 50.0
    assert result.loc["B", "income"] == 100.0

    assert vmin == 0.0
    assert vmax == 100.0


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_compare_no_compare_cols():
    """Test compute_missing_compare with no comparison columns."""
    missing_data = pl.DataFrame(
        {
            "age": [0, 1, 0, 1],
        }
    )

    data = pl.DataFrame(
        {
            "group": ["A", "A", "B", "B"],
            "age": [25, None, 30, None],
        }
    )

    result, vmin, vmax = compute_missing_compare(missing_data, data, "group", [])

    assert isinstance(result, pd.DataFrame)
    assert "values (count)" in result.columns
    assert "values (%)" in result.columns
    # Should only have group counts, no comparison columns
    assert result.shape[1] == 2
    assert vmin == 0.0
    assert vmax == 100.0


# -------------------- compute_missing_correlation Tests ----------------------


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_correlation_basic():
    """Test compute_missing_correlation with basic correlation."""
    missing_data = pl.DataFrame(
        {
            "age": [1, 1, 0, 0, 0],
            "income": [1, 1, 0, 0, 0],  # Perfect correlation with age
            "gender": [0, 0, 1, 1, 0],  # Negative correlation
        }
    )

    result = compute_missing_correlation(missing_data, ["age", "income", "gender"])

    assert isinstance(result, pd.DataFrame)
    assert result.shape == (3, 3)  # 3x3 correlation matrix

    # Check that it's a lower triangle matrix (upper triangle should be NaN)
    assert pd.isna(result.iloc[0, 1])  # Upper triangle
    assert pd.isna(result.iloc[0, 2])  # Upper triangle
    assert not pd.isna(result.iloc[1, 0])  # Lower triangle

    # Age and income should have high positive correlation
    assert result.loc["income", "age"] > 0.9


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_correlation_single_column():
    """Test compute_missing_correlation with single column."""
    missing_data = pl.DataFrame(
        {
            "age": [1, 0, 1, 0, 1],
        }
    )

    result = compute_missing_correlation(missing_data, ["age"])

    assert isinstance(result, pd.DataFrame)
    assert result.shape == (1, 1)


# -------------------------- get_null_list Tests ------------------------------


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_get_null_list_all_cols_true():
    """Test get_null_list returns all columns when all_cols=True."""
    missing_data = pl.DataFrame(
        {
            "age": [0, 1, 0, 1],
            "gender": [0, 0, 0, 0],
            "income": [1, 1, 1, 1],
        }
    )

    result = get_null_list(missing_data, all_cols=True)

    assert isinstance(result, list)
    assert len(result) == 3
    assert "age" in result
    assert "gender" in result
    assert "income" in result


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_get_null_list_partial_missing_only():
    """Test get_null_list returns only partially missing columns."""
    missing_data = pl.DataFrame(
        {
            "age": [0, 1, 0, 1],  # Partial missing
            "gender": [0, 0, 0, 0],  # No missing
            "income": [1, 1, 1, 1],  # All missing
            "city": [0, 1, 1, 0],  # Partial missing
        }
    )

    result = get_null_list(missing_data, all_cols=False)

    assert isinstance(result, list)
    assert len(result) == 2
    assert "age" in result
    assert "city" in result
    assert "gender" not in result  # All non-missing
    assert "income" not in result  # All missing


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_get_null_list_single_column():
    """Test get_null_list with single column DataFrame."""
    missing_data = pl.DataFrame(
        {
            "age": [0, 1, 0, 1],
        }
    )

    result = get_null_list(missing_data, all_cols=True)

    assert isinstance(result, list)
    assert len(result) == 1
    assert "age" in result


# ---------------------- compute_missing_matrix Tests -------------------------


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_matrix_basic():
    """Test compute_missing_matrix returns binary matrix."""
    missing_data = pl.DataFrame(
        {
            "age": [0, 1, 2, 0],
            "gender": [0, 0, 1, 3],
            "income": [0, 0, 0, 0],
        }
    )

    result = compute_missing_matrix(missing_data)

    assert isinstance(result, pd.DataFrame)
    assert result.shape == (4, 3)  # Same shape as input

    # Check binary conversion (0 stays 0, all positive values become 1)
    assert result["age"].tolist() == [0, 1, 1, 0]
    assert result["gender"].tolist() == [0, 0, 1, 1]
    assert result["income"].tolist() == [0, 0, 0, 0]


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_matrix_all_zero():
    """Test compute_missing_matrix with all zero values."""
    missing_data = pl.DataFrame(
        {
            "age": [0, 0, 0, 0],
            "gender": [0, 0, 0, 0],
        }
    )

    result = compute_missing_matrix(missing_data)

    assert result.shape == (4, 2)
    assert all(result["age"] == 0)
    assert all(result["gender"] == 0)


@patch("datasure.checks.missing.st.cache_data", lambda f: f)
def test_compute_missing_matrix_all_missing():
    """Test compute_missing_matrix with all missing values."""
    missing_data = pl.DataFrame(
        {
            "age": [1, 2, 3, 1],
            "gender": [2, 1, 2, 3],
        }
    )

    result = compute_missing_matrix(missing_data)

    assert result.shape == (4, 2)
    assert all(result["age"] == 1)
    assert all(result["gender"] == 1)


# ==============================================================================
# Additional Edge Case Tests (non-UI)
# ==============================================================================


def test_missing_code_invalid_codes_type():
    """MissingCode.parse_codes raises ValidationError for non-str/list input."""
    with pytest.raises(ValidationError):
        MissingCode(label="Test", codes=123)


def test_try_convert_code_float_failure():
    """_try_convert_code_to_column_type returns failure for invalid float string."""
    converted, success = _try_convert_code_to_column_type("abc", pl.Float64, "score")
    assert success is False
    assert converted is None


def test_try_convert_code_boolean_invalid_string():
    """_try_convert_code_to_column_type: failure for unrecognized boolean string."""
    converted, success = _try_convert_code_to_column_type("maybe", pl.Boolean, "flag")
    assert success is False
    assert converted is None


def test_compute_missing_data_paired_temporal_types():
    """_compute_missing_data_paired skips special code checks for temporal columns."""
    data = pl.DataFrame(
        {
            "date": pl.Series(
                [datetime.date(2023, 1, 1), None, datetime.date(2023, 1, 3)]
            ).cast(pl.Date),
            "value": [1, -999, 3],
        }
    )
    missing_codes_df = pl.DataFrame({"label": ["Missing"], "codes": ["-999"]})
    result = _compute_missing_data_paired(data, missing_codes_df)
    assert result["date"][0] == 0
    assert result["date"][1] == 1
    assert result["date"][2] == 0
    assert result["value"][1] == 2


def test_get_missing_code_pairs_empty():
    """_get_missing_code_pairs returns empty dict for empty DataFrame."""
    empty_df = pl.DataFrame(schema={"label": pl.Utf8, "codes": pl.Utf8})
    result = _get_missing_code_pairs(empty_df)
    assert result == {}


# ==============================================================================
# UI Function Tests
# ==============================================================================


def test_render_missing_codes_table_empty(patched_missing):
    """render_missing_codes_table works with no existing codes."""
    render_missing_codes_table("test_project")
    patched_missing.columns.assert_called()


def test_render_missing_codes_table_with_codes(patched_missing):
    """render_missing_codes_table renders dataframe when codes exist."""
    codes_df = pl.DataFrame({"label": ["Don't Know"], "codes": ["-999"]})
    with patch(
        "datasure.checks.missing.load_missing_codes_from_db",
        return_value=codes_df,
    ):
        patched_missing.selectbox.return_value = "Don't Know"
        patched_missing.text_input.return_value = "-999"
        render_missing_codes_table("test_project")
    patched_missing.dataframe.assert_called()


def test_missing_summary_ui(patched_missing):
    """missing_summary renders metric columns."""
    missing_data = pl.DataFrame({"age": [0, 1, 0, 0], "gender": [0, 0, 1, 0]})
    missing_summary(missing_data)
    patched_missing.columns.assert_called()


def test_missing_columns_ui(patched_missing):
    """missing_columns renders with slider and data."""
    missing_data = pl.DataFrame({"age": [0, 1, 0, 0], "gender": [0, 0, 1, 0]})
    missing_codes_df = pl.DataFrame({"label": ["DontKnow"], "codes": ["-999"]})
    patched_missing.slider.return_value = 0
    missing_columns(missing_data, missing_codes_df, "settings.json")
    patched_missing.columns.assert_called()


def test_missing_over_time_no_date_cols(patched_missing):
    """missing_over_time shows info message when no datetime columns."""
    missing_data = pl.DataFrame({"age": [0, 1, 0, 0]})
    data = pl.DataFrame({"age": [25, None, 30, 35]})
    missing_over_time(missing_data, data, "settings.json")
    patched_missing.info.assert_called()


def test_missing_over_time_with_date_col(patched_missing):
    """missing_over_time renders chart when datetime column is present."""
    missing_data = pl.DataFrame({"age": [0, 1, 0, 0], "gender": [0, 0, 1, 0]})
    data = (
        pl.DataFrame(
            {
                "date": pl.Series(
                    [
                        datetime.datetime(2023, 1, 1),
                        datetime.datetime(2023, 1, 2),
                        datetime.datetime(2023, 1, 3),
                        datetime.datetime(2023, 1, 4),
                    ]
                ),
                "age": [25, None, 30, 35],
                "gender": [1, 2, None, 1],
            }
        ),
    )
    patched_missing.selectbox.return_value = "date"
    missing_over_time(missing_data, data[0], "settings.json")
    patched_missing.plotly_chart.assert_called()


def test_missing_compare_no_categorical_cols(patched_missing):
    """missing_compare warns when no categorical columns available."""
    missing_data = pl.DataFrame({"age": [0, 1, 0, 0]})
    data = pl.DataFrame({"age": [25, None, 30, 35]})
    missing_compare(missing_data, data, "settings.json")
    patched_missing.warning.assert_called()


def test_missing_compare_with_group_no_compare_cols(patched_missing):
    """missing_compare renders group-only dataframe when compare cols empty."""
    missing_data = pl.DataFrame({"age": [0, 1, 0, 0], "gender": [0, 0, 1, 0]})
    data = pl.DataFrame(
        {
            "group": ["A", "A", "B", "B"],
            "age": [25, None, 30, None],
            "gender": [1, 2, None, 1],
        }
    )
    patched_missing.selectbox.return_value = "group"
    patched_missing.multiselect.return_value = []
    missing_compare(missing_data, data, "settings.json")
    patched_missing.dataframe.assert_called()


def test_missing_compare_with_compare_cols(patched_missing):
    """missing_compare renders styled dataframe when compare cols selected."""
    missing_data = pl.DataFrame({"age": [0, 1, 0, 0], "gender": [0, 0, 1, 0]})
    data = pl.DataFrame(
        {
            "group": ["A", "A", "B", "B"],
            "age": [25, None, 30, None],
            "gender": [1, 2, None, 1],
        }
    )
    patched_missing.selectbox.return_value = "group"
    patched_missing.multiselect.return_value = ["age"]
    missing_compare(missing_data, data, "settings.json")
    patched_missing.dataframe.assert_called()


def test_missing_correlation_warning_less_than_2_cols(patched_missing):
    """missing_correlation warns when fewer than 2 columns selected."""
    missing_data = pl.DataFrame({"age": [0, 1, 0, 0], "income": [1, 0, 0, 1]})
    patched_missing.toggle.return_value = False
    patched_missing.multiselect.return_value = []
    missing_correlation(missing_data, [[0, "#ff0000"], [1, "#00ff00"]], "settings.json")
    patched_missing.warning.assert_called()


def test_missing_correlation_with_enough_cols(patched_missing):
    """missing_correlation renders chart when 2+ columns selected."""
    missing_data = pl.DataFrame(
        {"age": [0, 1, 0, 0], "income": [1, 0, 0, 1], "gender": [0, 1, 1, 0]}
    )
    patched_missing.toggle.return_value = False
    patched_missing.multiselect.return_value = ["age", "income"]
    missing_correlation(missing_data, [[0, "#ff0000"], [1, "#00ff00"]], "settings.json")
    patched_missing.plotly_chart.assert_called()


def test_missing_matrix_ui(patched_missing):
    """missing_matrix renders plotly chart."""
    missing_data = pl.DataFrame({"age": [0, 1, 0, 0], "gender": [0, 0, 1, 0]})
    missing_matrix(missing_data, [[0, "#3f7f93"], [1, "#da3b46"]])
    patched_missing.plotly_chart.assert_called()


def test_missing_report_calls_title(patched_missing):
    """missing_report calls st.title and sub-functions."""
    data = pl.DataFrame(
        {
            "group": ["A", "A", "B", "B"],
            "age": [25, None, 30, None],
        }
    )
    with (
        patch("datasure.checks.missing.missing_summary"),
        patch("datasure.checks.missing.missing_columns"),
        patch("datasure.checks.missing.missing_compare"),
        patch("datasure.checks.missing.missing_over_time"),
        patch("datasure.checks.missing.missing_correlation"),
        patch("datasure.checks.missing.missing_matrix"),
        patch("datasure.checks.missing.render_missing_codes_table"),
        patch(
            "datasure.checks.missing._compute_missing_data_paired", return_value=data
        ),
    ):
        missing_report("proj_id", "page1", data, "settings.json")
    patched_missing.title.assert_called()
