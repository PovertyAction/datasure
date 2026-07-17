"""Tests for the PII detection and redaction module."""

from __future__ import annotations

from unittest.mock import patch

import polars as pl
import pytest

from datasure.processing.pii import (
    DEFAULT_MASK,
    PII_MODEL_OPTIONS,
    apply_pii_decisions,
    empty_flags,
    installed_models,
    load_pii_flags,
    mask_label_for,
    merge_with_existing,
    redact_correction_log,
    run_pii_scan,
    save_pii_flags,
    scan_column_names,
    scan_values,
)


def _en_model_installed() -> bool:
    import spacy.util

    return spacy.util.is_package(PII_MODEL_OPTIONS["en"])


requires_en_model = pytest.mark.skipif(
    not _en_model_installed(),
    reason="spaCy model en_core_web_sm not installed (see CONTRIBUTING.md)",
)


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse fixture from conftest.

    Disables database mocking for these tests (pure-Polars unit tests).
    """
    pass


def _flags(rows: list[dict]) -> pl.DataFrame:
    base = {
        "column": "",
        "source": "name_match",
        "entity_type": None,
        "hit_rate": 1.0,
        "sample_matches": "",
        "decision": "undecided",
        "mask_label": DEFAULT_MASK,
        "scanned_at": "2026-01-01T00:00:00",
    }
    return pl.DataFrame([{**base, **row} for row in rows], schema=empty_flags().schema)


# ---------------------------------------------------------------------------
# Pass 1: column-name heuristics
# ---------------------------------------------------------------------------


class TestScanColumnNames:
    def test_strict_match(self):
        df = pl.DataFrame({"age": [30, 40]})
        flags = scan_column_names(df)
        assert flags["column"].to_list() == ["age"]
        assert flags["source"].to_list() == ["name_match"]

    def test_fuzzy_substring_match(self):
        df = pl.DataFrame({"enum_name": ["a"], "household_latitude": [1.0]})
        flags = scan_column_names(df)
        assert set(flags["column"].to_list()) == {"enum_name", "household_latitude"}
        assert set(flags["source"].to_list()) == {"fuzzy"}

    def test_clean_columns_not_flagged(self):
        df = pl.DataFrame({"consent": ["yes", "no"], "outcome": [1, 2]})
        assert scan_column_names(df).is_empty()

    def test_sparsity_flags_high_cardinality_strings(self):
        values = [f"unique text {i}" for i in range(30)]
        df = pl.DataFrame({"notes": values})
        flags = scan_column_names(df)
        assert flags["column"].to_list() == ["notes"]
        assert flags["source"].to_list() == ["sparsity"]

    def test_sparsity_skips_small_columns(self):
        df = pl.DataFrame({"notes": ["a", "b", "c"]})
        assert scan_column_names(df).is_empty()

    def test_sparsity_skips_low_cardinality(self):
        df = pl.DataFrame({"category": ["a", "b"] * 20})
        assert scan_column_names(df).is_empty()

    def test_sparsity_skips_numeric_columns(self):
        df = pl.DataFrame({"measurement": list(range(100))})
        assert scan_column_names(df).is_empty()

    def test_multilingual_matches(self):
        df = pl.DataFrame({"nombre": ["x"], "adresse": ["y"], "jina": ["z"]})
        flags = scan_column_names(df)
        assert set(flags["column"].to_list()) == {"nombre", "adresse", "jina"}


# ---------------------------------------------------------------------------
# Pass 2: Presidio value scan (needs spaCy model)
# ---------------------------------------------------------------------------


@requires_en_model
class TestScanValues:
    def test_person_names_flagged(self):
        df = pl.DataFrame({"contact": ["John Smith", "Mary Johnson", "Robert Brown"]})
        flags = scan_values(df, language="en")
        assert "contact" in flags["column"].to_list()
        row = flags.filter(pl.col("column") == "contact").row(0, named=True)
        assert row["entity_type"] == "PERSON"
        assert row["mask_label"] == "[PERSON]"
        assert row["sample_matches"] != ""

    def test_emails_flagged(self):
        df = pl.DataFrame(
            {"reach": ["a@example.org", "b@example.org", "c@example.org"]}
        )
        flags = scan_values(df, language="en")
        row = flags.filter(pl.col("column") == "reach").row(0, named=True)
        assert row["entity_type"] == "EMAIL_ADDRESS"

    def test_clean_values_not_flagged(self):
        df = pl.DataFrame({"answer": ["yes", "no", "maybe", "yes", "no"]})
        flags = scan_values(df, language="en")
        assert "answer" not in flags["column"].to_list()

    def test_numeric_columns_skipped(self):
        df = pl.DataFrame({"amount": [1.5, 2.5, 3.5]})
        assert scan_values(df, language="en").is_empty()


@requires_en_model
class TestRunPiiScan:
    def test_combines_passes_and_joins_sources(self):
        df = pl.DataFrame({"enum_name": ["John Smith", "Mary Johnson", "Robert Brown"]})
        flags = run_pii_scan(df, language="en", use_value_scan=True)
        row = flags.filter(pl.col("column") == "enum_name").row(0, named=True)
        assert row["source"] == "fuzzy+value_scan"
        assert row["entity_type"] == "PERSON"


class TestRunPiiScanNoModel:
    def test_name_scan_only(self):
        df = pl.DataFrame({"age": [30, 40]})
        flags = run_pii_scan(df, use_value_scan=False)
        assert flags["column"].to_list() == ["age"]


# ---------------------------------------------------------------------------
# Merge with existing flags
# ---------------------------------------------------------------------------


class TestMergeWithExisting:
    def test_no_old_flags_returns_new(self):
        new = _flags([{"column": "age"}])
        assert merge_with_existing(new, empty_flags()).equals(new)

    def test_decision_preserved_on_rescan(self):
        new = _flags([{"column": "age", "hit_rate": 0.5}])
        old = _flags([{"column": "age", "decision": "keep"}])
        merged = merge_with_existing(new, old)
        row = merged.row(0, named=True)
        assert row["decision"] == "keep"
        assert row["hit_rate"] == 0.5

    def test_undecided_stale_flags_dropped(self):
        new = _flags([{"column": "age"}])
        old = _flags([{"column": "old_col", "decision": "undecided"}])
        merged = merge_with_existing(new, old)
        assert merged["column"].to_list() == ["age"]

    def test_decided_stale_flags_retained(self):
        new = _flags([{"column": "age"}])
        old = _flags([{"column": "old_col", "decision": "mask"}])
        merged = merge_with_existing(new, old)
        assert set(merged["column"].to_list()) == {"age", "old_col"}


# ---------------------------------------------------------------------------
# Redaction
# ---------------------------------------------------------------------------


class TestApplyPiiDecisions:
    def test_mask_replaces_non_null_values(self):
        df = pl.DataFrame({"name": ["Alice", None, "Bob"], "age": [1, 2, 3]})
        flags = _flags(
            [{"column": "name", "decision": "mask", "mask_label": "[PERSON]"}]
        )
        result = apply_pii_decisions(df, flags)
        assert result["name"].to_list() == ["[PERSON]", None, "[PERSON]"]
        assert result["age"].to_list() == [1, 2, 3]

    def test_mask_casts_numeric_to_string(self):
        df = pl.DataFrame({"latitude": [26.08, 25.91]})
        flags = _flags([{"column": "latitude", "decision": "mask"}])
        result = apply_pii_decisions(df, flags)
        assert result["latitude"].dtype == pl.String
        assert result["latitude"].to_list() == [DEFAULT_MASK, DEFAULT_MASK]

    def test_drop_removes_column(self):
        df = pl.DataFrame({"name": ["a"], "age": [1]})
        flags = _flags([{"column": "name", "decision": "drop"}])
        result = apply_pii_decisions(df, flags)
        assert "name" not in result.columns

    def test_keep_leaves_column_untouched(self):
        df = pl.DataFrame({"name": ["Alice"]})
        flags = _flags([{"column": "name", "decision": "keep"}])
        result = apply_pii_decisions(df, flags)
        assert result["name"].to_list() == ["Alice"]

    def test_undecided_untouched_by_default(self):
        df = pl.DataFrame({"name": ["Alice"]})
        flags = _flags([{"column": "name", "decision": "undecided"}])
        result = apply_pii_decisions(df, flags)
        assert result["name"].to_list() == ["Alice"]

    def test_undecided_masked_when_mask_undecided(self):
        df = pl.DataFrame({"name": ["Alice"]})
        flags = _flags([{"column": "name", "decision": "undecided"}])
        result = apply_pii_decisions(df, flags, mask_undecided=True)
        assert result["name"].to_list() == [DEFAULT_MASK]

    def test_protected_columns_never_redacted(self):
        df = pl.DataFrame({"key": ["k1"], "name": ["Alice"]})
        flags = _flags(
            [
                {"column": "key", "decision": "mask"},
                {"column": "name", "decision": "mask"},
            ]
        )
        result = apply_pii_decisions(df, flags, protect=("key",))
        assert result["key"].to_list() == ["k1"]
        assert result["name"].to_list() == [DEFAULT_MASK]

    def test_missing_columns_ignored(self):
        df = pl.DataFrame({"age": [1]})
        flags = _flags([{"column": "ghost", "decision": "mask"}])
        assert apply_pii_decisions(df, flags).equals(df)

    def test_empty_flags_no_change(self):
        df = pl.DataFrame({"name": ["Alice"]})
        assert apply_pii_decisions(df, empty_flags()).equals(df)


class TestRedactCorrectionLog:
    def _corr_log(self) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "column": ["name", "consent"],
                "current_value": ["Alice", "no"],
                "new_value": ["Alicia", "yes"],
            }
        )

    def test_masks_values_for_redacted_columns(self):
        flags = _flags([{"column": "name", "decision": "mask"}])
        result = redact_correction_log(self._corr_log(), flags)
        assert result["current_value"].to_list() == [DEFAULT_MASK, "no"]
        assert result["new_value"].to_list() == [DEFAULT_MASK, "yes"]

    def test_dropped_columns_also_masked(self):
        flags = _flags([{"column": "name", "decision": "drop"}])
        result = redact_correction_log(self._corr_log(), flags)
        assert result["current_value"].to_list() == [DEFAULT_MASK, "no"]

    def test_kept_columns_untouched(self):
        flags = _flags([{"column": "name", "decision": "keep"}])
        result = redact_correction_log(self._corr_log(), flags)
        assert result["current_value"].to_list() == ["Alice", "no"]

    def test_protected_columns_untouched(self):
        flags = _flags([{"column": "name", "decision": "mask"}])
        result = redact_correction_log(self._corr_log(), flags, protect=("name",))
        assert result["current_value"].to_list() == ["Alice", "no"]

    def test_empty_log_passthrough(self):
        flags = _flags([{"column": "name", "decision": "mask"}])
        empty = pl.DataFrame()
        assert redact_correction_log(empty, flags).is_empty()


# ---------------------------------------------------------------------------
# Persistence and helpers
# ---------------------------------------------------------------------------


class TestPersistence:
    @patch("datasure.utils.duckdb_utils.duckdb_save_table")
    def test_save_uses_pii_flags_table(self, mock_save):
        flags = _flags([{"column": "age"}])
        save_pii_flags("proj", "baseline", flags)
        assert mock_save.call_args.kwargs["alias"] == "pii_flags_baseline"
        assert mock_save.call_args.kwargs["db_name"] == "logs"

    @patch("datasure.utils.duckdb_utils.duckdb_get_table")
    def test_load_returns_stored_flags(self, mock_get):
        stored = _flags([{"column": "age"}])
        mock_get.return_value = stored
        assert load_pii_flags("proj", "baseline").equals(stored)

    @patch("datasure.utils.duckdb_utils.duckdb_get_table")
    def test_load_missing_returns_empty(self, mock_get):
        mock_get.side_effect = RuntimeError("no table")
        assert load_pii_flags("proj", "baseline").is_empty()


class TestHelpers:
    def test_mask_label_known_entity(self):
        assert mask_label_for("PERSON") == "[PERSON]"

    def test_mask_label_unknown_entity(self):
        assert mask_label_for("SOMETHING_ELSE") == DEFAULT_MASK

    def test_mask_label_none(self):
        assert mask_label_for(None) == DEFAULT_MASK

    def test_installed_models_shape(self):
        models = installed_models()
        assert set(models) == {"en", "es", "fr"}
        assert all(isinstance(v, bool) for v in models.values())
