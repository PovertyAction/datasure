"""Tests for the data-dict.yaml generator."""

from __future__ import annotations

import datetime

import polars as pl
import yaml

from datasure.replication.data_dict import generate_data_dict


def _generate(df: pl.DataFrame, key_col: str = "key") -> dict:
    text = generate_data_dict(
        df,
        table_name="baseline",
        label="Baseline Survey",
        description="Test dataset.",
        key_col=key_col,
        parquet_path="../../3_data/3_final/baseline_corrected.parquet",
        datasure_version="1.2.3",
    )
    assert isinstance(text, str)
    return yaml.safe_load(text)


class TestTopLevel:
    def test_spec_version(self):
        doc = _generate(pl.DataFrame({"key": ["k1"]}))
        assert doc["$version"] == "0.1.0"

    def test_learn_more_url(self):
        doc = _generate(pl.DataFrame({"key": ["k1"]}))
        assert doc["$learn_more"] == "https://data-dict.tidyverse.org/"

    def test_name_and_label(self):
        doc = _generate(pl.DataFrame({"key": ["k1"]}))
        assert doc["name"] == "baseline"
        assert doc["label"] == "Baseline Survey"

    def test_version_date_present(self):
        doc = _generate(pl.DataFrame({"key": ["k1"]}))
        assert "date" in doc["version"]

    def test_single_table(self):
        doc = _generate(pl.DataFrame({"key": ["k1"]}))
        assert len(doc["tables"]) == 1

    def test_table_source_parquet_path(self):
        doc = _generate(pl.DataFrame({"key": ["k1"]}))
        table = doc["tables"][0]
        assert table["source"]["parquet"] == (
            "../../3_data/3_final/baseline_corrected.parquet"
        )


class TestEmptyDataFrame:
    def test_empty_dataframe_has_no_columns(self):
        doc = _generate(pl.DataFrame())
        assert doc["tables"][0]["columns"] == []


class TestColumnTypes:
    def test_numeric_column_type_and_range(self):
        doc = _generate(pl.DataFrame({"key": ["k1", "k2"], "age": [25, 40]}))
        col = next(c for c in doc["tables"][0]["columns"] if c["name"] == "age")
        assert col["type"] == "number"
        assert col["range"] == [25, 40]

    def test_boolean_column_has_no_descriptor(self):
        doc = _generate(pl.DataFrame({"key": ["k1", "k2"], "flag": [True, False]}))
        col = next(c for c in doc["tables"][0]["columns"] if c["name"] == "flag")
        assert col["type"] == "boolean"
        assert "values" not in col
        assert "range" not in col
        assert "examples" not in col

    def test_date_column_type_and_range(self):
        doc = _generate(
            pl.DataFrame(
                {
                    "key": ["k1", "k2"],
                    "dob": [
                        datetime.date(2000, 1, 1),
                        datetime.date(1995, 5, 5),
                    ],
                }
            )
        )
        col = next(c for c in doc["tables"][0]["columns"] if c["name"] == "dob")
        assert col["type"] == "date"
        assert col["range"] == ["1995-05-05", "2000-01-01"]

    def test_low_cardinality_text_becomes_enum(self):
        doc = _generate(
            pl.DataFrame({"key": ["k1", "k2", "k3"], "category": ["a", "b", "a"]})
        )
        col = next(c for c in doc["tables"][0]["columns"] if c["name"] == "category")
        assert col["type"] == "enum"
        assert set(col["values"]) == {"a", "b"}

    def test_high_cardinality_text_uses_examples(self):
        values = [f"note {i}" for i in range(30)]
        doc = _generate(
            pl.DataFrame({"key": [f"k{i}" for i in range(30)], "notes": values})
        )
        col = next(c for c in doc["tables"][0]["columns"] if c["name"] == "notes")
        assert col["type"] == "string"
        assert len(col["examples"]) <= 5


class TestPrimaryKey:
    def test_key_column_gets_primary_key_constraint(self):
        doc = _generate(pl.DataFrame({"key": ["k1", "k2"], "age": [25, 30]}))
        col = next(c for c in doc["tables"][0]["columns"] if c["name"] == "key")
        assert col["constraints"] == ["primary_key"]

    def test_numeric_key_column_is_number_id(self):
        doc = _generate(pl.DataFrame({"id": [1, 2], "age": [25, 30]}), key_col="id")
        col = next(c for c in doc["tables"][0]["columns"] if c["name"] == "id")
        assert col["type"] == "number(id)"

    def test_no_key_col_means_no_primary_key(self):
        doc = _generate(pl.DataFrame({"key": ["k1", "k2"]}), key_col="")
        col = next(c for c in doc["tables"][0]["columns"] if c["name"] == "key")
        assert "constraints" not in col
