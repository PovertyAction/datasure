"""Tests for Stata column-name validation."""

import pytest

from datasure.processing.column_names import stata_name_error


class TestStataNameError:
    """A new column name must be one Stata can use."""

    @pytest.mark.parametrize(
        "name",
        ["age", "_age", "Q1_b", "x" * 32, "_", "a1"],
    )
    def test_valid_names_have_no_error(self, name):
        assert stata_name_error(name) is None

    def test_33_characters_is_too_long(self):
        assert "32 characters" in stata_name_error("x" * 33)

    @pytest.mark.parametrize("name", ["1age", "9"])
    def test_leading_digit_is_rejected(self, name):
        assert "start with a letter or _" in stata_name_error(name)

    @pytest.mark.parametrize(
        "name", ["age-1", "age 1", "age.1", "âge", "a$b", "q1é", "a\tb"]
    )
    def test_characters_outside_letters_digits_underscore_are_rejected(self, name):
        assert "letters, digits and _" in stata_name_error(name)

    def test_empty_name_is_rejected(self):
        assert stata_name_error("") is not None
