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

    @pytest.mark.parametrize(
        "name",
        [
            "alias",
            "_all",
            "_b",
            "byte",
            "_coef",
            "_cons",
            "double",
            "float",
            "if",
            "in",
            "int",
            "long",
            "_n",
            "_N",
            "_pi",
            "_pred",
            "_r_b",
            "_r_ci",
            "_r_cri",
            "_r_crlb",
            "_r_crub",
            "_r_df",
            "_r_lb",
            "_r_p",
            "_r_se",
            "_r_ub",
            "_r_z",
            "_r_z_abs",
            "_rc",
            "_se",
            "_skip",
            "str1",
            "str80",
            "str2045",
            "strL",
            "using",
            "with",
        ],
    )
    def test_stata_reserved_names_are_rejected(self, name):
        assert "reserved" in stata_name_error(name)

    @pytest.mark.parametrize(
        "name", ["IN", "Byte", "strl", "string", "str_", "_merge", "inc", "with_id"]
    )
    def test_names_that_only_resemble_reserved_names_are_allowed(self, name):
        """Stata names are case-sensitive, and only exact matches are reserved."""
        assert stata_name_error(name) is None
