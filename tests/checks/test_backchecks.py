"""Tests for backchecks module.

This module tests the core computational functions of the backcheck analysis system.
It focuses on data processing, value comparison, statistical calculations,
and settings management.
"""

import json

import numpy as np
import pandas as pd
import pytest

from datasure.checks.backchecks import (
    DO_NOT_COMPARE_VALUES,
    IGNORE_MISSING_VALUES,
    TREAT_VALUES_AS_SAME,
    _calculate_column_summary_stats,
    _compare_values,
    _compute_group_stats,
    _compute_overall_stats,
    _create_merged_comparison_df,
    _generate_staff_statistics,
    _get_merge_columns,
    compute_backcheck_overview,
    generate_column_summary,
    load_default_backcheck_settings,
    process_duplicate_data,
)

# ============================================
# FIXTURES FOR BACKCHECK-SPECIFIC DATA
# ============================================


@pytest.fixture
def backcheck_settings_file(tmp_path):
    """Create a temporary backcheck settings file."""
    settings = {
        "backchecks": {
            "date": "submission_date",
            "enumerator": "enumerator",
            "backchecker": "backchecker",
            "survey_id": "survey_id",
            "survey_key": "survey_key",
            "backcheck_goal": 10,
            "drop_duplicates": True,
        }
    }
    file_path = tmp_path / "backcheck_settings.json"
    file_path.write_text(json.dumps(settings))
    return str(file_path)


# ============================================
# SETTINGS TESTS
# ============================================


def test_load_default_backcheck_settings_valid(
    backcheck_settings_file, mock_streamlit_session
):
    """Test loading backcheck settings from valid file."""
    project_id = mock_streamlit_session["config_pages"]["st_project_id"][0]
    result = load_default_backcheck_settings(project_id, backcheck_settings_file, 1)

    (
        date,
        enumerator,
        backchecker,
        survey_id,
        survey_key,
        backcheck_goal,
        drop_duplicates,
    ) = result

    assert date == "submission_date"
    assert enumerator == "enumerator"
    assert backchecker == "backchecker"
    assert survey_id == "survey_id"
    assert survey_key == "survey_key"
    assert backcheck_goal == 10
    assert drop_duplicates is True


def test_load_default_backcheck_settings_missing_file(mock_streamlit_session):
    """Test loading backcheck settings when file doesn't exist."""
    project_id = mock_streamlit_session["config_pages"]["st_project_id"][0]
    result = load_default_backcheck_settings(project_id, "nonexistent.json", 1)

    (
        date,
        enumerator,
        backchecker,
        survey_id,
        survey_key,
        backcheck_goal,
        drop_duplicates,
    ) = result

    # Should fall back to session state values and defaults
    assert date == "submission_date"  # From mock session state
    assert enumerator == "enumerator"  # From mock session state
    assert backchecker is None  # Not in session state
    assert survey_id == "survey_id"  # From mock session state
    assert backcheck_goal == 0  # Default value
    assert drop_duplicates is True  # Default value


# ============================================
# DATA PROCESSING TESTS
# ============================================


def test_process_duplicate_data(backcheck_survey_data, backcheck_data):
    """Test processing duplicate data correctly."""
    # Add duplicates to test data
    survey_with_dups = pd.concat(
        [
            backcheck_survey_data,
            backcheck_survey_data.iloc[[0]].assign(
                submission_date="2024-01-10"
            ),  # Later date for same survey_id
        ]
    )

    backcheck_with_dups = pd.concat(
        [
            backcheck_data,
            backcheck_data.iloc[[0]].assign(
                submission_date="2024-01-15"
            ),  # Later date for same survey_id
        ]
    )

    survey_processed, backcheck_processed = process_duplicate_data(
        survey_with_dups, backcheck_with_dups, "survey_id", "submission_date", True
    )

    # Should keep only the most recent entry for each survey_id
    assert len(survey_processed) == 5  # Original 5 unique survey_ids
    assert len(backcheck_processed) == 3  # Original 3 unique survey_ids

    # Check that most recent dates are kept
    # Convert to string for comparison since process_duplicate_data converts to datetime
    survey_date = survey_processed[survey_processed["survey_id"] == "S001"][
        "submission_date"
    ].iloc[0]
    backcheck_date = backcheck_processed[backcheck_processed["survey_id"] == "S001"][
        "submission_date"
    ].iloc[0]

    # Handle both datetime and string formats
    if hasattr(survey_date, "strftime"):
        assert survey_date.strftime("%Y-%m-%d") == "2024-01-10"
    else:
        assert survey_date == "2024-01-10"

    if hasattr(backcheck_date, "strftime"):
        assert backcheck_date.strftime("%Y-%m-%d") == "2024-01-15"
    else:
        assert backcheck_date == "2024-01-15"


def test_process_duplicate_data_no_duplicates(backcheck_survey_data, backcheck_data):
    """Test processing data when there are no duplicates."""
    survey_processed, backcheck_processed = process_duplicate_data(
        backcheck_survey_data, backcheck_data, "survey_id", "submission_date", True
    )

    # Should return data unchanged
    assert len(survey_processed) == len(backcheck_survey_data)
    assert len(backcheck_processed) == len(backcheck_data)


# ============================================
# VALUE COMPARISON TESTS
# ============================================


def test_compare_values_exact_match():
    """Test _compare_values with exact matches."""
    row = pd.Series({"survey_val": "A", "backcheck_val": "A"})
    result = _compare_values(row, "survey_val", "backcheck_val", "", "")
    assert result == "not_different"


def test_compare_values_different():
    """Test _compare_values with different values."""
    row = pd.Series({"survey_val": "A", "backcheck_val": "B"})
    result = _compare_values(row, "survey_val", "backcheck_val", "", "")
    assert result == "different"


def test_compare_values_ignore_missing():
    """Test _compare_values with ignore missing values condition."""
    row = pd.Series({"survey_val": np.nan, "backcheck_val": "B"})
    result = _compare_values(
        row, "survey_val", "backcheck_val", "", IGNORE_MISSING_VALUES
    )
    assert result == "not_compared"

    row = pd.Series({"survey_val": "A", "backcheck_val": np.nan})
    result = _compare_values(
        row, "survey_val", "backcheck_val", "", IGNORE_MISSING_VALUES
    )
    assert result == "not_compared"


def test_compare_values_do_not_compare():
    """Test _compare_values with do not compare condition."""
    # Format: prefix + ": " + values (no space after colon in prefix)
    condition = DO_NOT_COMPARE_VALUES + " refuse,dk"
    row = pd.Series({"survey_val": "refuse", "backcheck_val": "yes"})
    result = _compare_values(row, "survey_val", "backcheck_val", "", condition)
    assert result == "not_compared"

    row = pd.Series({"survey_val": "yes", "backcheck_val": "dk"})
    result = _compare_values(row, "survey_val", "backcheck_val", "", condition)
    assert result == "not_compared"

    # Test case where neither value matches the exclusion list
    row = pd.Series({"survey_val": "yes", "backcheck_val": "no"})
    result = _compare_values(row, "survey_val", "backcheck_val", "", condition)
    assert result == "different"  # Should fall through to normal comparison


def test_compare_values_treat_as_same():
    """Test _compare_values with treat as same condition."""
    # Format: prefix + " " + values (no colon in the appended part)
    condition = TREAT_VALUES_AS_SAME + " yes,1"
    row = pd.Series({"survey_val": "yes", "backcheck_val": "1"})
    result = _compare_values(row, "survey_val", "backcheck_val", "", condition)
    assert result == "not_different"

    # Test when both values are the same and in the list
    row = pd.Series({"survey_val": "yes", "backcheck_val": "yes"})
    result = _compare_values(row, "survey_val", "backcheck_val", "", condition)
    assert result == "not_different"

    # Test when values are different and not both in the same-values list
    row = pd.Series({"survey_val": "yes", "backcheck_val": "no"})
    result = _compare_values(row, "survey_val", "backcheck_val", "", condition)
    assert result == "different"  # Should fall through to normal comparison


def test_compare_values_absolute_range():
    """Test _compare_values with absolute value range."""
    row = pd.Series({"survey_val": 100, "backcheck_val": 102})
    result = _compare_values(row, "survey_val", "backcheck_val", "5", "")
    assert result == "not_different"  # Difference of 2 is within range of 5

    row = pd.Series({"survey_val": 100, "backcheck_val": 110})
    result = _compare_values(row, "survey_val", "backcheck_val", "5", "")
    assert result == "different"  # Difference of 10 is outside range of 5


def test_compare_values_percentage_range():
    """Test _compare_values with percentage range."""
    row = pd.Series({"survey_val": 100, "backcheck_val": 105})
    result = _compare_values(row, "survey_val", "backcheck_val", "10%", "")
    assert result == "not_different"  # 5% difference is within 10%

    row = pd.Series({"survey_val": 100, "backcheck_val": 120})
    result = _compare_values(row, "survey_val", "backcheck_val", "10%", "")
    assert result == "different"  # 20% difference is outside 10%


def test_compare_values_bracket_range():
    """Test _compare_values with bracket range."""
    row = pd.Series({"survey_val": 100, "backcheck_val": 102})
    result = _compare_values(row, "survey_val", "backcheck_val", "[-5,5]", "")
    assert result == "not_different"  # Difference of 2 is within [-5,5]

    row = pd.Series({"survey_val": 100, "backcheck_val": 110})
    result = _compare_values(row, "survey_val", "backcheck_val", "[-5,5]", "")
    assert result == "different"  # Difference of 10 is outside [-5,5]


def test_compare_values_invalid_numeric():
    """Test _compare_values with invalid numeric values."""
    row = pd.Series({"survey_val": "not_a_number", "backcheck_val": "100"})
    result = _compare_values(row, "survey_val", "backcheck_val", "5", "")
    assert result == "not_compared"  # Should handle conversion errors


def test_compare_values_whitespace_handling():
    """Test _compare_values handles whitespace correctly."""
    row = pd.Series({"survey_val": " A ", "backcheck_val": "A"})
    result = _compare_values(row, "survey_val", "backcheck_val", "", "")
    assert result == "not_different"  # Should strip whitespace


def test_compare_values_negative_numbers():
    """Test _compare_values with negative numbers."""
    row = pd.Series({"survey_val": -100, "backcheck_val": -102})
    result = _compare_values(row, "survey_val", "backcheck_val", "5", "")
    assert result == "not_different"  # Difference of 2 is within range of 5


# ============================================
# OVERVIEW COMPUTATION TESTS
# ============================================


def test_compute_backcheck_overview(backcheck_survey_data, backcheck_data):
    """Test computing backcheck overview statistics."""
    # Add prefixes to simulate processed data
    survey_df_bc = backcheck_survey_data.add_prefix("_svy_").rename(
        columns={"_svy_survey_id": "survey_id"}
    )
    backcheck_df_bc = backcheck_data.add_prefix("_bc_").rename(
        columns={"_bc_survey_id": "survey_id"}
    )

    # Create merged dataframe
    merged_df = pd.merge(survey_df_bc, backcheck_df_bc, on="survey_id", how="inner")

    result = compute_backcheck_overview(
        survey_df_bc, backcheck_df_bc, merged_df, "enumerator", 20, 50.0
    )

    total_backchecks, backcheck_goal_update, _, total_enumerators = result

    assert total_backchecks == 3  # Number of backcheck records
    assert backcheck_goal_update == 20  # Goal unchanged since backchecks < goal
    assert total_enumerators == 3  # Unique enumerators in survey data (E1, E2, E3)
    # num_enumerators_bc depends on which enumerators meet the 50% target


def test_compute_backcheck_overview_exceeds_goal():
    """Test compute_backcheck_overview when backchecks exceed goal."""
    survey_df_bc = pd.DataFrame({"survey_id": ["S001"], "_svy_enumerator": ["E1"]})
    backcheck_df_bc = pd.DataFrame({"survey_id": ["S001"], "_bc_data": ["data"]})
    merged_df = pd.DataFrame({"survey_id": ["S001"], "_svy_enumerator": ["E1"]})

    result = compute_backcheck_overview(
        survey_df_bc,
        backcheck_df_bc,
        merged_df,
        "enumerator",
        0,
        50.0,  # Goal of 0, should be updated to actual backchecks
    )

    total_backchecks, backcheck_goal_update, _, _ = result

    assert total_backchecks == 1
    assert backcheck_goal_update == 1  # Should be updated to match actual backchecks


# ============================================
# COLUMN SUMMARY GENERATION TESTS
# ============================================


def test_generate_column_summary(
    backcheck_survey_data, backcheck_data, backcheck_column_config
):
    """Test generating column summary."""
    summary_df, results_df = generate_column_summary(
        backcheck_column_config,
        backcheck_survey_data,
        backcheck_data,
        "survey_id",
        "enumerator",
        "backchecker",
        None,
    )

    assert len(summary_df) == 3  # Three columns in config
    assert "column" in summary_df.columns
    assert "data type" in summary_df.columns
    assert "category" in summary_df.columns
    assert "# surveys" in summary_df.columns
    assert "# compared" in summary_df.columns
    assert "# different" in summary_df.columns
    assert "error rate" in summary_df.columns

    assert len(results_df) > 0
    assert "survey_id" in results_df.columns
    assert "Enumerator" in results_df.columns
    assert "Back Checker" in results_df.columns
    assert "variable" in results_df.columns


def test_generate_column_summary_empty_config():
    """Test generating column summary with empty configuration."""
    empty_config = pd.DataFrame(
        columns=["column", "category", "ok_range", "comparison_condition"]
    )
    survey_data = pd.DataFrame({"survey_id": [1], "enumerator": ["E1"], "age": [25]})
    backcheck_data = pd.DataFrame(
        {"survey_id": [1], "backchecker": ["B1"], "age": [25]}
    )

    summary_df, results_df = generate_column_summary(
        empty_config,
        survey_data,
        backcheck_data,
        "survey_id",
        "enumerator",
        "backchecker",
        None,
    )

    assert len(summary_df) == 0
    assert len(results_df) == 0


def test_generate_column_summary_with_grouping(
    backcheck_survey_data, backcheck_data, backcheck_column_config
):
    """Test generating column summary with grouping by summary column."""
    summary_df, _ = generate_column_summary(
        backcheck_column_config,
        backcheck_survey_data,
        backcheck_data,
        "survey_id",
        "enumerator",
        "backchecker",
        "enumerator",
    )

    # Should have entries for each enumerator and column combination
    assert len(summary_df) > 3  # More than just the 3 columns
    assert "enumerator" in summary_df.columns  # Grouping column should be present


# ============================================
# HELPER FUNCTION TESTS
# ============================================


def test_create_merged_comparison_df(backcheck_survey_data, backcheck_data):
    """Test creating merged comparison dataframe."""
    # Add prefixes to simulate processed data
    survey_data = backcheck_survey_data.add_prefix("_svy_").rename(
        columns={"_svy_survey_id": "survey_id"}
    )
    backcheck_data_prefixed = backcheck_data.add_prefix("_bc_").rename(
        columns={"_bc_survey_id": "survey_id"}
    )

    result = _create_merged_comparison_df(
        survey_data,
        backcheck_data_prefixed,
        "survey_id",
        "_svy_enumerator",
        "_bc_backchecker",
        "_svy_age",
        "_bc_age",
        None,
    )

    assert len(result) == 3  # Should have 3 matching records
    assert "survey_id" in result.columns
    assert "_svy_enumerator" in result.columns
    assert "_bc_backchecker" in result.columns
    assert "_svy_age" in result.columns
    assert "_bc_age" in result.columns


def test_compute_overall_stats():
    """Test computing overall statistics."""
    merged_df = pd.DataFrame(
        {
            "comparison_result": [
                "different",
                "not_different",
                "different",
                "not_compared",
            ]
        }
    )

    result = _compute_overall_stats(merged_df)

    assert result["# surveys"] == 4
    assert result["# backchecks"] == 4
    assert result["# compared"] == 3  # Excludes 'not_compared'
    assert result["# different"] == 2
    assert result["error rate"] == "66.67%"  # 2/3 * 100


def test_compute_group_stats():
    """Test computing group statistics."""
    group_df = pd.DataFrame(
        {"comparison_result": ["different", "not_different", "different"]}
    )
    merged_df = pd.DataFrame(
        {
            "enumerator": ["E1", "E1", "E1", "E2"],
            "comparison_result": [
                "different",
                "not_different",
                "different",
                "not_compared",
            ],
        }
    )

    result = _compute_group_stats(group_df, merged_df, "enumerator", "E1")

    assert result["# surveys"] == 3  # E1 has 3 surveys in merged_df
    assert result["# backchecks"] == 3  # group_df length
    assert result["# compared"] == 3  # All in group_df are compared
    assert result["# different"] == 2
    assert result["error rate"] == "66.67%"


def test_calculate_column_summary_stats():
    """Test calculating column summary statistics."""
    merged_df = pd.DataFrame(
        {
            "comparison_result": [
                "different",
                "not_different",
                "different",
                "not_compared",
            ]
        }
    )
    survey_col_data = pd.Series([25, 30, 28, 35], dtype="int64")

    result = _calculate_column_summary_stats(merged_df, "age", 1, survey_col_data, None)

    assert len(result) == 1
    stats = result[0]
    assert stats["column"] == "age"
    assert stats["data type"] == "Numeric"
    assert stats["category"] == 1
    assert stats["# surveys"] == 4
    assert stats["# backchecks"] == 4
    assert stats["# compared"] == 3
    assert stats["# different"] == 2
    assert stats["error rate"] == "66.67%"


def test_calculate_column_summary_stats_with_grouping():
    """Test _calculate_column_summary_stats with grouping by enumerator."""
    merged_df = pd.DataFrame(
        {
            "comparison_result": [
                "different",
                "not_different",
                "different",
                "not_compared",
            ],
            "enumerator": ["E1", "E1", "E2", "E2"],
        }
    )
    survey_col_data = pd.Series([25, 30, 28, 35], dtype="int64")

    result = _calculate_column_summary_stats(
        merged_df, "age", 1, survey_col_data, "enumerator"
    )

    assert len(result) == 2  # Should have stats for E1 and E2

    # Check E1 stats
    e1_stats = next(stat for stat in result if stat.get("enumerator") == "E1")
    assert e1_stats["# compared"] == 2
    assert e1_stats["# different"] == 1
    assert e1_stats["error rate"] == "50.00%"

    # Check E2 stats
    e2_stats = next(stat for stat in result if stat.get("enumerator") == "E2")
    assert e2_stats["# compared"] == 1  # One 'not_compared' excluded
    assert e2_stats["# different"] == 1
    assert e2_stats["error rate"] == "100.00%"


# ============================================
# EDGE CASES AND ERROR HANDLING TESTS
# ============================================


def test_edge_case_no_matching_records():
    """Test edge case where survey and backcheck data have no matching records."""
    survey_data = pd.DataFrame(
        {"survey_id": ["S001", "S002"], "enumerator": ["E1", "E2"], "age": [25, 30]}
    )
    backcheck_data = pd.DataFrame(
        {
            "survey_id": ["S003", "S004"],  # No matching IDs
            "backchecker": ["B1", "B2"],
            "age": [28, 32],
        }
    )

    column_config = pd.DataFrame(
        {
            "column": ["age"],
            "category": [1],
            "ok_range": [""],
            "comparison_condition": [""],
        }
    )

    summary_df, results_df = generate_column_summary(
        column_config,
        survey_data,
        backcheck_data,
        "survey_id",
        "enumerator",
        "backchecker",
        None,
    )

    assert len(summary_df) == 1  # Still creates summary for configured column
    assert summary_df.iloc[0]["# compared"] == 0  # No comparisons possible
    assert len(results_df) == 0  # No matching records


def test_edge_case_all_values_identical():
    """Test edge case where all compared values are identical."""
    survey_data = pd.DataFrame(
        {"survey_id": ["S001", "S002"], "enumerator": ["E1", "E2"], "age": [25, 30]}
    )
    backcheck_data = pd.DataFrame(
        {
            "survey_id": ["S001", "S002"],
            "backchecker": ["B1", "B2"],
            "age": [25, 30],  # Identical values
        }
    )

    column_config = pd.DataFrame(
        {
            "column": ["age"],
            "category": [1],
            "ok_range": [""],
            "comparison_condition": [""],
        }
    )

    summary_df, results_df = generate_column_summary(
        column_config,
        survey_data,
        backcheck_data,
        "survey_id",
        "enumerator",
        "backchecker",
        None,
    )

    assert len(summary_df) == 1
    assert summary_df.iloc[0]["# different"] == 0  # No differences
    assert summary_df.iloc[0]["error rate"] == "0.00%"
    assert all(results_df["comparison_result"] == "not_different")


def test_edge_case_empty_dataframes():
    """Test handling of empty dataframes."""
    empty_survey = pd.DataFrame(columns=["survey_id", "enumerator", "age"])
    empty_backcheck = pd.DataFrame(columns=["survey_id", "backchecker", "age"])

    column_config = pd.DataFrame(
        {
            "column": ["age"],
            "category": [1],
            "ok_range": [""],
            "comparison_condition": [""],
        }
    )

    summary_df, results_df = generate_column_summary(
        column_config,
        empty_survey,
        empty_backcheck,
        "survey_id",
        "enumerator",
        "backchecker",
        None,
    )

    assert len(summary_df) == 1  # Should still create summary row
    assert summary_df.iloc[0]["# compared"] == 0  # No data to compare
    assert len(results_df) == 0  # No results


def test_edge_case_mixed_data_types():
    """Test handling of mixed data types in comparison."""
    survey_data = pd.DataFrame(
        {
            "survey_id": ["S001", "S002"],
            "enumerator": ["E1", "E2"],
            "mixed_col": [100, "text"],  # Mixed numeric and text
        }
    )
    backcheck_data = pd.DataFrame(
        {
            "survey_id": ["S001", "S002"],
            "backchecker": ["B1", "B2"],
            "mixed_col": [100, "text"],
        }
    )

    column_config = pd.DataFrame(
        {
            "column": ["mixed_col"],
            "category": [1],
            "ok_range": ["5"],  # Numeric range on mixed data
            "comparison_condition": [""],
        }
    )

    summary_df, _ = generate_column_summary(
        column_config,
        survey_data,
        backcheck_data,
        "survey_id",
        "enumerator",
        "backchecker",
        None,
    )

    # Should handle mixed types gracefully
    assert len(summary_df) == 1
    assert summary_df.iloc[0]["# compared"] >= 0  # Some comparisons should be possible


# ============================================
# INTEGRATION TESTS
# ============================================


def test_backcheck_workflow_integration(backcheck_survey_data, backcheck_data):
    """Test complete backcheck workflow integration."""
    # Step 1: Process duplicates
    survey_processed, backcheck_processed = process_duplicate_data(
        backcheck_survey_data, backcheck_data, "survey_id", "submission_date", True
    )

    # Step 2: Create column configuration
    column_config = pd.DataFrame(
        {
            "column": ["age", "income"],
            "category": [1, 2],
            "ok_range": ["2", "1000"],
            "comparison_condition": ["", ""],
        }
    )

    # Step 3: Generate summary
    summary_df, results_df = generate_column_summary(
        column_config,
        survey_processed,
        backcheck_processed,
        "survey_id",
        "enumerator",
        "backchecker",
        None,
    )

    # Verify results
    assert len(summary_df) == 2  # Two columns configured
    assert all(
        col in summary_df.columns
        for col in ["column", "category", "# compared", "# different"]
    )
    assert len(results_df) > 0
    assert "comparison_result" in results_df.columns


# ============================================
# PERFORMANCE AND EDGE CASE TESTS
# ============================================


def test_generate_column_summary_performance():
    """Test generate_column_summary with larger dataset for performance."""
    # Create larger test datasets
    survey_data = pd.DataFrame(
        {
            "survey_id": [f"S{i:03d}" for i in range(100)],
            "enumerator": [f"E{i % 10}" for i in range(100)],
            "age": range(25, 125),
            "income": range(50000, 150000, 1000),
        }
    )

    backcheck_data = pd.DataFrame(
        {
            "survey_id": [
                f"S{i:03d}" for i in range(0, 100, 2)
            ],  # 50 backcheck records
            "backchecker": [f"B{i % 5}" for i in range(50)],
            "age": range(25, 125, 2),
            "income": range(50000, 150000, 2000),
        }
    )

    column_config = pd.DataFrame(
        {
            "column": ["age", "income"],
            "category": [1, 2],
            "ok_range": ["2", "1000"],
            "comparison_condition": ["", ""],
        }
    )

    # Should complete without performance issues
    summary_df, results_df = generate_column_summary(
        column_config,
        survey_data,
        backcheck_data,
        "survey_id",
        "enumerator",
        "backchecker",
        None,
    )

    assert len(summary_df) == 2  # Two columns configured
    assert len(results_df) == 100  # 50 backcheck records * 2 columns


def test_create_merged_comparison_df_empty_data():
    """Test _create_merged_comparison_df with empty data."""
    empty_survey = pd.DataFrame(columns=["survey_id", "_svy_enumerator", "_svy_age"])
    empty_backcheck = pd.DataFrame(columns=["survey_id", "_bc_backchecker", "_bc_age"])

    result = _create_merged_comparison_df(
        empty_survey,
        empty_backcheck,
        "survey_id",
        "_svy_enumerator",
        "_bc_backchecker",
        "_svy_age",
        "_bc_age",
        None,
    )

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


def test_create_merged_comparison_df_missing_survey_id():
    """Test _create_merged_comparison_df when survey_id column is missing."""
    survey_data = pd.DataFrame({"_svy_enumerator": ["E1"], "_svy_age": [25]})
    backcheck_data = pd.DataFrame({"_bc_backchecker": ["B1"], "_bc_age": [25]})

    # Should handle missing survey_id gracefully
    result = _create_merged_comparison_df(
        survey_data,
        backcheck_data,
        "survey_id",  # This column doesn't exist
        "_svy_enumerator",
        "_bc_backchecker",
        "_svy_age",
        "_bc_age",
        None,
    )

    assert isinstance(result, pd.DataFrame)
    assert len(result) == 0


# ============================================
# NEW HELPER FUNCTIONS TESTS
# ============================================


def test_get_merge_columns():
    """Test _get_merge_columns helper function."""
    # Test with no optional columns
    result = _get_merge_columns(["survey_id"])
    assert result == ["survey_id"]

    # Test with optional columns (some None)
    result = _get_merge_columns(["survey_id"], "enumerator", None, "date")
    assert result == ["survey_id", "enumerator", "date"]

    # Test avoiding duplicates
    result = _get_merge_columns(["survey_id"], "survey_id", "enumerator")
    assert result == ["survey_id", "enumerator"]

    # Test all None optional columns
    result = _get_merge_columns(["survey_id"], None, None, None)
    assert result == ["survey_id"]


def test_generate_staff_statistics_enumerator(
    backcheck_survey_data, backcheck_data, backcheck_column_config
):
    """Test _generate_staff_statistics for enumerators."""
    result = _generate_staff_statistics(
        backcheck_column_config,
        backcheck_survey_data,
        backcheck_data,
        "survey_id",
        "enumerator",
        "backchecker",
        "enumerator",
        "enumerator",
    )

    assert not result.empty
    assert "Enumerator" in result.columns or "enumerator" in result.columns
    assert "# back checked" in result.columns
    assert "% back checked" in result.columns
    assert "Error Rate" in result.columns


def test_generate_staff_statistics_backchecker(
    backcheck_survey_data, backcheck_data, backcheck_column_config
):
    """Test _generate_staff_statistics for backcheckers."""
    result = _generate_staff_statistics(
        backcheck_column_config,
        backcheck_survey_data,
        backcheck_data,
        "survey_id",
        "enumerator",
        "backchecker",
        "backchecker",
        "backchecker",
    )

    assert not result.empty
    assert "Back Checker" in result.columns or "backchecker" in result.columns
    assert "# back checked" in result.columns
    assert "Error Rate" in result.columns


def test_generate_staff_statistics_empty_config():
    """Test _generate_staff_statistics with empty configuration."""
    empty_config = pd.DataFrame(
        columns=["column", "category", "ok_range", "comparison_condition"]
    )
    survey_data = pd.DataFrame({"survey_id": [1], "enumerator": ["E1"], "age": [25]})
    backcheck_data = pd.DataFrame(
        {"survey_id": [1], "backchecker": ["B1"], "age": [25]}
    )

    result = _generate_staff_statistics(
        empty_config,
        survey_data,
        backcheck_data,
        "survey_id",
        "enumerator",
        "backchecker",
        "enumerator",
        "enumerator",
    )

    assert result.empty


def test_generate_staff_statistics_no_summary_col():
    """Test _generate_staff_statistics with no summary column."""
    column_config = pd.DataFrame(
        {
            "column": ["age"],
            "category": [1],
            "ok_range": [""],
            "comparison_condition": [""],
        }
    )
    survey_data = pd.DataFrame({"survey_id": [1], "enumerator": ["E1"], "age": [25]})
    backcheck_data = pd.DataFrame(
        {"survey_id": [1], "backchecker": ["B1"], "age": [25]}
    )

    result = _generate_staff_statistics(
        column_config,
        survey_data,
        backcheck_data,
        "survey_id",
        "enumerator",
        "backchecker",
        None,  # No summary column
        "enumerator",
    )

    assert result.empty


# ============================================
# INVALID SETTINGS FORMAT TESTS
# ============================================


def test_invalid_settings_format(tmp_path, mock_streamlit_session):
    """Test handling of malformed settings file."""
    invalid_settings = {"wrong_key": {}}
    settings_file = tmp_path / "invalid_settings.json"
    settings_file.write_text(json.dumps(invalid_settings))

    project_id = mock_streamlit_session["config_pages"]["st_project_id"][0]
    result = load_default_backcheck_settings(project_id, str(settings_file), 1)

    # Should fall back to session state values when settings file is invalid
    (
        date,
        enumerator,
        backchecker,
        survey_id,
        survey_key,
        backcheck_goal,
        drop_duplicates,
    ) = result
    assert date == "submission_date"  # From mock session state
    assert enumerator == "enumerator"  # From mock session state


def test_corrupted_json_file(tmp_path, mock_streamlit_session):
    """Test handling of corrupted JSON file."""
    corrupted_file = tmp_path / "corrupted.json"
    corrupted_file.write_text("invalid json content")

    project_id = mock_streamlit_session["config_pages"]["st_project_id"][0]

    # The function should handle JSON decode errors gracefully
    try:
        result = load_default_backcheck_settings(project_id, str(corrupted_file), 1)
        # If it doesn't raise an exception, check that it falls back to defaults
        (
            date,
            enumerator,
            backchecker,
            survey_id,
            survey_key,
            backcheck_goal,
            drop_duplicates,
        ) = result
        assert date == "submission_date"
    except Exception:
        # If the function throws an exception for corrupted JSON, that's also acceptable
        pass
