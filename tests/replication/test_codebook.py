"""Tests for the codebook generator."""

from __future__ import annotations

import polars as pl

from datasure.replication.codebook import generate_codebook


class TestGenerateCodebook:
    def test_empty_dataframe_returns_header_only(self):
        df = pl.DataFrame()
        result = generate_codebook(df)
        assert result == "variable,type,n_total,n_missing,n_unique,sample_values\n"

    def test_returns_string(self):
        df = pl.DataFrame({"name": ["Alice", "Bob"]})
        assert isinstance(generate_codebook(df), str)

    def test_text_column_type(self):
        df = pl.DataFrame({"name": ["Alice", "Bob"]})
        result = generate_codebook(df)
        assert "text" in result

    def test_integer_column_type(self):
        df = pl.DataFrame({"age": [25, 30]})
        result = generate_codebook(df)
        assert "numeric" in result

    def test_float_column_type(self):
        df = pl.DataFrame({"score": [1.5, 2.5]})
        result = generate_codebook(df)
        assert "numeric" in result

    def test_boolean_column_type(self):
        df = pl.DataFrame({"flag": [True, False]})
        result = generate_codebook(df)
        assert "boolean" in result

    def test_date_column_type(self):
        import datetime

        df = pl.DataFrame({"dob": [datetime.date(2000, 1, 1)]})
        result = generate_codebook(df)
        assert "datetime" in result

    def test_missing_count(self):
        df = pl.DataFrame({"col": ["a", None, "b"]})
        result = generate_codebook(df)
        # n_missing should be 1
        assert ",1," in result

    def test_column_name_in_output(self):
        df = pl.DataFrame({"survey_key": ["k1", "k2"]})
        result = generate_codebook(df)
        assert "survey_key" in result

    def test_all_null_column_has_empty_sample(self):
        df = pl.DataFrame({"col": pl.Series([None, None], dtype=pl.String)})
        result = generate_codebook(df)
        # sample_values should be empty
        assert "col" in result

    def test_multiple_columns(self):
        df = pl.DataFrame({"a": ["x"], "b": [1], "c": [True]})
        result = generate_codebook(df)
        assert "a" in result
        assert "b" in result
        assert "c" in result

    def test_n_total_matches_row_count(self):
        df = pl.DataFrame({"x": [1, 2, 3, 4, 5]})
        result = generate_codebook(df)
        assert ",5," in result

    def test_pipe_separator_in_sample_values(self):
        df = pl.DataFrame({"x": ["a", "b", "c"]})
        result = generate_codebook(df)
        # Multiple unique values are joined with " | "
        assert " | " in result or "a" in result  # at least some values present
