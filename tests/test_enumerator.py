import pandas as pd
import pytest

from src.checks.enumerator import (
    compute_enumerator_overview,
    compute_enumerator_statistics,
    load_default_settings,
)


# Test fixtures
@pytest.fixture
def sample_data():
    """Create sample dataset for testing."""
    return pd.DataFrame(
        {
            "submission_date": ["2024-01-01", "2024-01-01", "2024-01-02", "2024-01-02"],
            "enumerator": ["E1", "E1", "E2", "E2"],
            "team": ["T1", "T1", "T2", "T2"],
            "duration": [10, 15, 20, 25],
            "consent": ["Yes", "Yes", "No", "Yes"],
            "outcome": ["Complete", "Complete", "Refused", "Complete"],
            "value1": [1, None, 3, 4],
            "value2": [10, 20, None, 40],
        }
    )


@pytest.fixture
def settings_file(tmp_path):
    """Create temporary settings file."""
    settings = {
        "enumerator": {
            "date": "submission_date",
            "enumerator": "enumerator",
            "team": "team",
            "duration": "duration",
            "consent": "consent",
            "consent_vals": ["Yes", "No"],
            "outcome": "outcome",
            "outcome_vals": ["Complete", "Refused"],
        }
    }
    file_path = tmp_path / "settings.json"
    pd.to_json(file_path, settings)
    return str(file_path)


@pytest.fixture
def date_format_data():
    """Create datasets with different date formats for testing."""
    return {
        "iso_dates": pd.DataFrame(
            {
                "submission_date": ["2024-01-01", "2024-01-02", "2024-01-03"],
                "enumerator": ["E1", "E1", "E2"],
                "team": ["T1", "T1", "T2"],
            }
        ),
        "datetime_obj": pd.DataFrame(
            {
                "submission_date": pd.date_range(start="2024-01-01", periods=3),
                "enumerator": ["E1", "E1", "E2"],
                "team": ["T1", "T1", "T2"],
            }
        ),
        "uk_format": pd.DataFrame(
            {
                "submission_date": ["01/01/2024", "02/01/2024", "03/01/2024"],
                "enumerator": ["E1", "E1", "E2"],
                "team": ["T1", "T1", "T2"],
            }
        ),
        "month_name": pd.DataFrame(
            {
                "submission_date": ["Jan 01, 2024", "Jan 02, 2024", "Jan 03, 2024"],
                "enumerator": ["E1", "E1", "E2"],
                "team": ["T1", "T1", "T2"],
            }
        ),
    }


# Test load_default_settings
def test_load_default_settings_valid(settings_file):
    """Test loading settings from valid file."""
    date, enumerator, team, duration, consent, consent_vals, outcome, outcome_vals = (
        load_default_settings(settings_file, 1)
    )
    assert date == "submission_date"
    assert enumerator == "enumerator"
    assert team == "team"
    assert duration == "duration"


def test_load_default_settings_missing_file():
    """Test handling of missing settings file."""
    date, enumerator, team, duration, consent, consent_vals, outcome, outcome_vals = (
        load_default_settings("nonexistent.json", 1)
    )
    assert date is None
    assert enumerator is None
    assert team is None
    assert duration is None


# Test compute_enumerator_overview
def test_compute_enumerator_overview(sample_data):
    """Test computation of enumerator overview metrics."""
    (
        all_submissions,
        num_active_enumerators,
        num_enumerators,
        num_teams,
        min_submissions,
        max_submissions,
        avg_submissions,
        pct_active_enumerators,
    ) = compute_enumerator_overview(
        sample_data, "submission_date", "enumerator", "team"
    )

    assert all_submissions == 4
    assert num_enumerators == 2
    assert num_teams == 2
    assert min_submissions == 2
    assert max_submissions == 2
    assert avg_submissions == 2
    assert pct_active_enumerators == "100%"


# Test compute_enumerator_statistics
def test_compute_enumerator_statistics(sample_data):
    """Test computation of enumerator statistics."""
    stats = compute_enumerator_statistics(
        sample_data, "enumerator", "duration", "consent", ["Yes", "No"]
    )

    assert not stats.empty
    assert "total_surveys" in stats.columns
    assert "avg_duration" in stats.columns
    assert "consent_rate" in stats.columns


# Test edge cases
def test_empty_dataframe():
    """Test handling of empty dataframe."""
    empty_df = pd.DataFrame()
    with pytest.raises(ValueError):
        compute_enumerator_overview(empty_df, "date", "enumerator", "team")


def test_missing_columns():
    """Test handling of missing required columns."""
    bad_df = pd.DataFrame({"A": [1, 2], "B": [3, 4]})
    with pytest.raises(KeyError):
        compute_enumerator_overview(bad_df, "date", "enumerator", "team")


def test_large_dataset():
    """Test performance with large dataset."""
    large_df = pd.DataFrame(
        {
            "submission_date": pd.date_range("2024-01-01", periods=10000),
            "enumerator": ["E" + str(i % 100) for i in range(10000)],
            "team": ["T" + str(i % 10) for i in range(10000)],
            "duration": range(10000),
        }
    )

    result = compute_enumerator_overview(
        large_df, "submission_date", "enumerator", "team"
    )
    assert result is not None


# Test handling of different date formats
def test_date_format_handling(date_format_data):
    """Test handling of different date formats."""
    for format_name, df in date_format_data.items():
        print(f"Testing {format_name} format")
        try:
            if format_name == "uk_format":
                # Convert UK format dates
                df["submission_date"] = pd.to_datetime(
                    df["submission_date"], format="%d/%m/%Y"
                )
            elif format_name == "month_name":
                # Convert month name format
                df["submission_date"] = pd.to_datetime(
                    df["submission_date"], format="%b %d, %Y"
                )

            result = compute_enumerator_overview(
                df, "submission_date", "enumerator", "team"
            )

            # Validate results
            assert result is not None
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

            assert all_submissions == 3
            assert num_enumerators == 2
            assert num_teams == 2
            assert isinstance(avg_submissions, (int | float))

        except Exception as e:
            pytest.fail(f"Failed to process {format_name} format: {e!s}")


def test_mixed_date_formats():
    """Test handling of mixed date formats in same dataset."""
    mixed_dates_df = pd.DataFrame(
        {
            "submission_date": ["2024-01-01", "Jan 02, 2024", "03/01/2024"],
            "enumerator": ["E1", "E1", "E2"],
            "team": ["T1", "T1", "T2"],
        }
    )

    # Convert mixed dates using coerce to handle errors
    mixed_dates_df["submission_date"] = pd.to_datetime(
        mixed_dates_df["submission_date"],
        format="mixed",
        dayfirst=True,  # Handle UK format dates correctly
    )

    result = compute_enumerator_overview(
        mixed_dates_df, "submission_date", "enumerator", "team"
    )

    assert result is not None
    assert result[0] == 3  # all_submissions
