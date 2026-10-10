"""Tests for reading and describing a saved Records to Include filter."""

import json

import polars as pl
import pytest

from datasure.checks.duplicates import (
    BACKCHECK_PREFIX,
    apply_records_to_include,
    describe_records_to_include,
    saved_records_to_include,
)


def _settings_file(tmp_path, duplicates: dict) -> str:
    path = tmp_path / "page_settings.json"
    path.write_text(json.dumps({"duplicates": duplicates}))
    return str(path)


class TestSavedRecordsToInclude:
    def test_reads_the_survey_filter(self, tmp_path):
        settings_file = _settings_file(
            tmp_path,
            {
                "condition_col": "status",
                "condition_type": "Value is equal",
                "condition_value": "Complete",
                "missing_as_duplicates": True,
            },
        )

        assert saved_records_to_include(settings_file) == {
            "condition_col": "status",
            "condition_type": "Value is equal",
            "condition_value": "Complete",
            "missing_as_duplicates": True,
        }

    def test_reads_the_backcheck_filter_by_prefix(self, tmp_path):
        settings_file = _settings_file(
            tmp_path,
            {
                "condition_col": "status",
                "condition_type": "Value is equal",
                "condition_value": "Complete",
                "backcheck_condition_col": "bc_status",
                "backcheck_condition_type": "Values includes",
                "backcheck_condition_value": ["Done"],
            },
        )

        conditions = saved_records_to_include(settings_file, BACKCHECK_PREFIX)

        assert conditions == {
            "condition_col": "bc_status",
            "condition_type": "Values includes",
            "condition_value": ["Done"],
            "missing_as_duplicates": False,
        }

    def test_no_filter_saved(self, tmp_path):
        assert saved_records_to_include(_settings_file(tmp_path, {})) == {}

    def test_missing_settings_file(self, tmp_path):
        assert saved_records_to_include(str(tmp_path / "none.json")) == {}

    def test_saved_date_filter_applies(self, tmp_path):
        """A date saved as text in JSON is coerced when the filter applies."""
        import datetime

        data = pl.DataFrame(
            {
                "day": [datetime.datetime(2024, 1, d, 9) for d in (1, 5, 9)],
                "hhid": ["A", "B", "C"],
            }
        )
        settings_file = _settings_file(
            tmp_path,
            {
                "condition_col": "day",
                "condition_type": "Value is greater than",
                "condition_value": "2024-01-04",
            },
        )

        conditions = saved_records_to_include(settings_file)

        assert apply_records_to_include(data, conditions)["hhid"].to_list() == [
            "B",
            "C",
        ]


class TestDescribeRecordsToInclude:
    @pytest.mark.parametrize(
        ("condition_type", "value", "expected"),
        [
            ("Value is equal", "Complete", "status == Complete"),
            ("Value is not equal", "Refused", "status != Refused"),
            ("Value is greater than", 3, "status > 3"),
            ("Value is greater than or equal to", 3, "status >= 3"),
            ("Value is less than", 3, "status < 3"),
            ("Value is less than or equal to", 3, "status <= 3"),
            ("Values includes", ["A", "B"], "status in A, B"),
            ("Value does not include", ["A"], "status not in A"),
            ("Value is in range", [1, 5], "status between 1 and 5"),
            ("Value starts with", "Co", "status starts with Co"),
            ("Value ends with", "te", "status ends with te"),
            ("Value contains", "omp", "status contains omp"),
        ],
    )
    def test_describes_each_condition(self, condition_type, value, expected):
        conditions = {
            "condition_col": "status",
            "condition_type": condition_type,
            "condition_value": value,
        }
        assert describe_records_to_include(conditions) == expected

    def test_inactive_filter_has_no_description(self):
        assert describe_records_to_include({}) is None
        assert (
            describe_records_to_include(
                {
                    "condition_col": "status",
                    "condition_type": "Value is equal",
                    "condition_value": None,
                }
            )
            is None
        )
