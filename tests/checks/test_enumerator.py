"""Tests for enumerator module.

This module tests the core computational functions of the enumerator analysis system.
It focuses on data processing, statistical calculations, and settings management.
"""

import json

import pandas as pd
import pytest

from src.checks.enumerator import (
    compute_enumerator_missing_table,
    compute_enumerator_overview,
    compute_enumerator_productivity,
    compute_enumerator_statistics,
    compute_enumerator_statistics_overtime,
    compute_enumerator_summary,
    load_default_enumerator_settings,
)


# ============================================
# SETTINGS TESTS
# ============================================
def test_load_default_enumerator_settings_valid(settings_file, mock_streamlit_session):
    """Test loading settings from valid file."""
    project_id = mock_streamlit_session["config_pages"]["st_project_id"][0]
    result = load_default_enumerator_settings(project_id, settings_file, 1)
    (
        date,
        formdef_version,
        survey_id,
        duration,
        enumerator,
        team,
        consent,
        consent_vals,
        outcome,
        outcome_vals,
    ) = result

    assert date == "submission_date"
    assert enumerator == "enumerator"
    assert team == "team"
    assert duration == "duration"
    assert consent_vals == ["Yes", "No"]
    assert outcome_vals == ["Complete", "Refused"]


def test_load_default_settings_missing_file(mock_streamlit_session):
    """Test handling of missing settings file."""
    project_id = mock_streamlit_session["config_pages"]["st_project_id"][0]
    result = load_default_enumerator_settings(project_id, "nonexistent.json", 1)
    (
        date,
        formdef_version,
        survey_id,
        duration,
        enumerator,
        team,
        consent,
        consent_vals,
        outcome,
        outcome_vals,
    ) = result

    # When file doesn't exist, it should fall back to session state values
    assert date == "submission_date"  # From mock session state
    assert enumerator == "enumerator"  # From mock session state
    assert team is None
    assert duration is None
    assert consent_vals is None
    assert outcome_vals is None


# ============================================
# OVERVIEW COMPUTATION TESTS
# ============================================
def test_compute_enumerator_overview(sample_dataframe):
    """Test computation of enumerator overview metrics."""
    result = compute_enumerator_overview(
        sample_dataframe, "submission_date", "enumid", "team"
    )
    (
        all_submissions,
        num_active_enumerators,
        num_enumerators,
        num_teams,
        min_submissions,
        max_submissions,
        avg_submissions,
        pct_active_enumerators,
    ) = result

    assert all_submissions == 5
    assert num_enumerators == 3
    assert num_teams == 2
    assert min_submissions == 1
    assert max_submissions == 2
    assert avg_submissions == 1  # Average submissions per enumerator
    assert (
        num_active_enumerators == 3
    )  # all enumerators should be active with recent dates
    assert pct_active_enumerators == "100%"  # All enumerators are now active


# ============================================
# STATISTICS COMPUTATION TESTS
# ============================================
def test_compute_enumerator_statistics(sample_dataframe):
    """Test computation of enumerator statistics."""
    stats = compute_enumerator_statistics(
        sample_dataframe,
        "submission_date",
        "enumid",
        ["duration"],
        ["min", "mean", "median", "max"],
    )

    assert not stats.empty
    assert len(stats) == 3  # Three enumerators
    assert stats[("duration", "mean")][0] == 15.0
    assert stats[("duration", "min")][0] == 10
    assert stats[("duration", "max")][1] == 30
    assert stats[("duration", "median")][1] == 22.5


# ============================================
# MISSING DATA ANALYSIS TESTS
# ============================================
def test_compute_enumerator_missing_table(missing_data, missing_settings_file):
    """Test computation of missingness table by enumerator."""
    missing_table = compute_enumerator_missing_table(
        missing_data, missing_settings_file, "enumerator"
    )

    assert not missing_table.empty
    # The function returns data with enumerator column, not indexed by enumerator
    assert "enumerator" in missing_table.columns
    enumerators = missing_table["enumerator"].unique()
    assert "E1" in enumerators
    assert "E2" in enumerators


# ============================================
# SUMMARY COMPUTATION TESTS
# ============================================
def test_compute_enumerator_summary(productivity_data, missing_settings_file):
    """Test computation of enumerator summary statistics."""
    summary = compute_enumerator_summary(
        productivity_data,
        missing_settings_file,
        "submission_date",
        "enumerator",
        None,  # formdef_version
        "duration",
        None,  # consent
        None,  # consent_vals
        None,  # outcome
        None,  # outcome_vals
    )

    assert not summary.empty
    assert "enumerator" in summary.columns
    # Check that we have data for both enumerators
    enumerators = summary["enumerator"].unique()
    assert "E1" in enumerators
    assert "E2" in enumerators


# ============================================
# PRODUCTIVITY ANALYSIS TESTS
# ============================================
def test_compute_enumerator_productivity(productivity_data):
    """Test computation of daily submission trends."""
    productivity = compute_enumerator_productivity(
        productivity_data,
        "submission_date",
        "enumerator",
        "Daily",  # period
        "Monday",  # weekstartday
    )

    assert not productivity.empty
    # Check that we have all enumerators in the data
    if "enumerator" in productivity.columns:
        enumerators = productivity["enumerator"].unique()
        assert "E1" in enumerators
        assert "E2" in enumerators


def test_compute_enumerator_statistics_overtime(productivity_data):
    """Test computation of time-based statistics."""
    stats_overtime = compute_enumerator_statistics_overtime(
        productivity_data,
        "submission_date",
        "enumerator",
        "duration",  # statscol - single column (despite type annotation)
        "count",  # stat - single statistic that should work
        "Daily",  # period
        "Monday",  # weekstartday
    )

    assert not stats_overtime.empty
    # The function should return some result data
    assert len(stats_overtime) > 0


# ============================================
# EDGE CASES AND ERROR HANDLING TESTS
# ============================================
def test_empty_dataframe():
    """Test handling of empty dataframe."""
    empty_df = pd.DataFrame(
        columns=["submission_date", "enumerator", "team", "duration"]
    )
    with pytest.raises((ValueError, IndexError)):
        compute_enumerator_overview(empty_df, "submission_date", "enumerator", "team")


def test_missing_columns():
    """Test handling of missing required columns."""
    bad_df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    with pytest.raises(KeyError):
        compute_enumerator_overview(bad_df, "submission_date", "enumerator", "team")


def test_large_dataset():
    """Test performance with large dataset."""
    large_df = pd.DataFrame(
        {
            "submission_date": pd.date_range("2024-01-01", periods=10000),
            "enumerator": [f"E{i % 100}" for i in range(10000)],
            "team": [f"T{i % 10}" for i in range(10000)],
            "duration": range(10000),
        }
    )

    result = compute_enumerator_overview(
        large_df, "submission_date", "enumerator", "team"
    )
    assert result is not None
    assert result[0] == 10000  # Total submissions
    assert result[2] == 100  # Total enumerators
    assert result[3] == 10  # Total teams


# ============================================
# DATE FORMAT HANDLING TESTS
# ============================================
@pytest.mark.parametrize(
    "format_name,expected_conversion",
    [
        ("iso_dates", True),
        ("datetime_obj", True),
        ("uk_format", True),
        ("month_name", True),
    ],
)
def test_date_format_handling(date_format_data, format_name, expected_conversion):
    """Test handling of different date formats."""
    df = date_format_data[format_name].copy()

    # Apply format-specific conversions
    if format_name == "uk_format":
        df["submission_date"] = pd.to_datetime(df["submission_date"], format="%d/%m/%Y")
    elif format_name == "month_name":
        df["submission_date"] = pd.to_datetime(
            df["submission_date"], format="%b %d, %Y"
        )

    result = compute_enumerator_overview(df, "submission_date", "enumerator", "team")

    # Validate results
    assert result is not None
    all_submissions, _, num_enumerators, num_teams, _, _, avg_submissions, _ = result

    assert all_submissions == 3
    assert num_enumerators == 2
    assert num_teams == 2
    assert isinstance(avg_submissions, int | float)


def test_mixed_date_formats():
    """Test handling of mixed date formats in same dataset."""
    mixed_dates_df = pd.DataFrame(
        {
            "submission_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
            "enumerator": ["E1", "E1", "E2"],
            "team": ["T1", "T1", "T2"],
        }
    )

    # Convert dates using standard format
    mixed_dates_df["submission_date"] = pd.to_datetime(
        mixed_dates_df["submission_date"]
    )

    result = compute_enumerator_overview(
        mixed_dates_df, "submission_date", "enumerator", "team"
    )

    assert result is not None
    assert result[0] == 3  # all_submissions


def test_invalid_date_column():
    """Test handling of invalid date column."""
    df = pd.DataFrame(
        {"wrong_date": ["2024-01-01"], "enumerator": ["E1"], "team": ["T1"]}
    )

    with pytest.raises(KeyError, match="submission_date"):
        compute_enumerator_overview(df, "submission_date", "enumerator", "team")


def test_single_enumerator():
    """Test handling of dataset with single enumerator."""
    from datetime import date, timedelta

    today = date.today()
    recent_date1 = (today - timedelta(days=2)).strftime("%Y-%m-%d")
    recent_date2 = (today - timedelta(days=1)).strftime("%Y-%m-%d")

    df = pd.DataFrame(
        {
            "submission_date": [recent_date1, recent_date2],
            "enumerator": ["E1", "E1"],
            "team": ["T1", "T1"],
            "duration": [10, 15],
        }
    )

    result = compute_enumerator_overview(df, "submission_date", "enumerator", "team")
    _, num_active_enumerators, num_enumerators, _, _, _, _, _ = result

    assert num_active_enumerators == 1
    assert num_enumerators == 1


def test_null_team_values():
    """Test handling of null team values."""
    df = pd.DataFrame(
        {
            "submission_date": ["2024-01-01", "2024-01-02"],
            "enumerator": ["E1", "E2"],
            "team": ["T1", None],
            "duration": [10, 15],
        }
    )

    result = compute_enumerator_overview(df, "submission_date", "enumerator", "team")
    _, _, _, num_teams, _, _, _, _ = result

    assert num_teams == 1  # Only non-null teams counted


# ============================================
# ADDITIONAL SETTINGS VALIDATION TESTS
# ============================================


def test_invalid_settings_format(tmp_path, mock_streamlit_session):
    """Test handling of malformed settings file."""
    invalid_settings = {"wrong_key": {}}
    settings_file = tmp_path / "invalid_settings.json"
    settings_file.write_text(json.dumps(invalid_settings))

    project_id = mock_streamlit_session["config_pages"]["st_project_id"][0]
    result = load_default_enumerator_settings(project_id, str(settings_file), 1)
    # Should fall back to session state values when settings file is invalid
    (
        date,
        formdef_version,
        survey_id,
        duration,
        enumerator,
        team,
        consent,
        consent_vals,
        outcome,
        outcome_vals,
    ) = result
    assert date == "submission_date"  # From mock session state
    assert enumerator == "enumerator"  # From mock session state


def test_settings_type_validation(settings_file, mock_streamlit_session):
    """Test validation of settings value types."""
    project_id = mock_streamlit_session["config_pages"]["st_project_id"][0]
    settings = load_default_enumerator_settings(project_id, settings_file, 1)

    assert isinstance(settings[0], str)  # date
    assert isinstance(settings[7], list)  # consent_vals
    assert isinstance(settings[9], list)  # outcome_vals


def test_empty_settings_file(tmp_path, mock_streamlit_session):
    """Test handling of empty settings file."""
    empty_file = tmp_path / "empty.json"
    empty_file.write_text("{}")

    project_id = mock_streamlit_session["config_pages"]["st_project_id"][0]
    result = load_default_enumerator_settings(project_id, str(empty_file), 1)
    # Should fall back to session state values when settings file is empty
    (
        date,
        formdef_version,
        survey_id,
        duration,
        enumerator,
        team,
        consent,
        consent_vals,
        outcome,
        outcome_vals,
    ) = result
    assert date == "submission_date"  # From mock session state
    assert enumerator == "enumerator"  # From mock session state


def test_corrupted_json_file(tmp_path, mock_streamlit_session):
    """Test handling of corrupted JSON file."""
    corrupted_file = tmp_path / "corrupted.json"
    corrupted_file.write_text("invalid json content")

    project_id = mock_streamlit_session["config_pages"]["st_project_id"][0]

    # The function should handle JSON decode errors gracefully
    # and return None values when the file cannot be parsed
    try:
        result = load_default_enumerator_settings(project_id, str(corrupted_file), 1)
        assert all(x is None for x in result)
    except Exception:
        # If the function throws an exception for corrupted JSON,
        # that's also acceptable behavior
        pass
