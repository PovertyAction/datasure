"""Tests for Stata column-name validation."""

import pytest

from datasure.processing.column_names import (
    existing_name_error,
    stata_name_edit_errors,
    stata_name_error,
    stata_name_map,
)


class TestExistingNameError:
    """A new column name must not clash with an existing one, ignoring case."""

    def test_new_name_has_no_error(self):
        assert existing_name_error("age_copy", ["hhid", "age"]) is None

    def test_exact_match_is_rejected(self):
        assert existing_name_error("age", ["hhid", "age"]) == (
            "Column 'age' already exists."
        )

    @pytest.mark.parametrize("name", ["Age", "AGE", "aGe"])
    def test_case_variant_is_rejected_and_names_the_existing_column(self, name):
        assert "already exists as 'age'" in existing_name_error(name, ["age"])

    def test_exact_match_wins_over_an_earlier_case_variant(self):
        assert existing_name_error("age", ["Age", "age"]) == (
            "Column 'age' already exists."
        )


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


class TestStataNameMap:
    """Every name Stata can't use gets a unique Stata-safe name."""

    def test_names_stata_accepts_are_never_changed(self):
        assert stata_name_map(["key", "age", "_merge", "Q1"]) == {}

    def test_issue_examples(self):
        mapping = stata_name_map(["visit date", "2nd_visit", "âge", "in"])
        assert mapping == {
            "visit date": "visit_date",
            "2nd_visit": "_2nd_visit",
            "âge": "age",
            "in": "in_",
        }

    def test_two_names_that_map_alike_get_numbered_suffixes(self):
        mapping = stata_name_map(["visit date", "visit-date", "visit.date"])
        assert mapping == {
            "visit date": "visit_date",
            "visit-date": "visit_date_2",
            "visit.date": "visit_date_3",
        }

    def test_a_proposal_never_takes_a_name_already_used(self):
        """``visit_date`` exists, even later in the list, so the proposal moves on."""
        mapping = stata_name_map(["visit date", "age", "visit_date"])
        assert mapping == {"visit date": "visit_date_2"}

    def test_long_names_are_cut_to_32_characters_and_stay_unique(self):
        first = "household_member_" + "a" * 20 + " one"
        second = "household_member_" + "a" * 20 + " two"
        mapping = stata_name_map([first, second])
        assert mapping[first] == ("household_member_" + "a" * 20)[:32]
        assert mapping[second] == ("household_member_" + "a" * 20)[:30] + "_2"
        assert all(stata_name_error(new) is None for new in mapping.values())

    def test_a_valid_but_too_long_name_is_shortened(self):
        name = "x" * 40
        assert stata_name_map([name]) == {name: "x" * 32}

    @pytest.mark.parametrize(
        ("name", "expected"),
        [("str80", "str80_"), ("_n", "_n_"), ("using", "using_"), ("", "var")],
    )
    def test_reserved_and_empty_names(self, name, expected):
        assert stata_name_map([name]) == {name: expected}

    def test_letters_without_a_plain_ascii_form_become_underscores(self):
        assert stata_name_map(["straße"]) == {"straße": "stra_e"}


class TestStataNameEdits:
    """People can edit a proposed name; good edits are used, bad ones reported."""

    def test_a_valid_edit_replaces_the_proposal(self):
        mapping = stata_name_map(["visit date"], edits={"visit date": "vdate"})
        assert mapping == {"visit date": "vdate"}

    def test_an_edit_wins_its_name_over_another_proposal(self):
        mapping = stata_name_map(
            ["visit date", "visit-date"], edits={"visit-date": "visit_date"}
        )
        assert mapping == {"visit date": "visit_date_2", "visit-date": "visit_date"}

    def test_edits_for_names_stata_accepts_or_unknown_names_are_ignored(self):
        mapping = stata_name_map(["age", "in"], edits={"age": "age2", "gone": "g"})
        assert mapping == {"in": "in_"}

    @pytest.mark.parametrize("bad", ["visit date", "1v", "in", "x" * 33, "age"])
    def test_an_edit_stata_cant_use_or_already_used_falls_back(self, bad):
        mapping = stata_name_map(["visit date", "age"], edits={"visit date": bad})
        assert mapping == {"visit date": "visit_date"}

    def test_edit_errors_name_the_problem(self):
        errors = stata_name_edit_errors(
            ["visit date", "age", "in", "2nd"],
            {"visit date": "age", "in": "in", "2nd": "second"},
        )
        assert set(errors) == {"visit date", "in"}
        assert "already" in errors["visit date"]
        assert "reserved" in errors["in"]

    def test_two_edits_with_the_same_name_are_both_errors(self):
        errors = stata_name_edit_errors(["a b", "c d"], {"a b": "x", "c d": "x"})
        assert set(errors) == {"a b", "c d"}


class TestReservedVariables:
    """Variables the package's scripts create are never given to a column."""

    def test_a_proposal_skips_a_reserved_variable(self):
        assert stata_name_map(["_ds row"], reserved=["_ds_row"]) == {
            "_ds row": "_ds_row_2"
        }

    def test_an_edit_to_a_reserved_variable_is_an_error(self):
        errors = stata_name_edit_errors(["a b"], {"a b": "_ds_row"}, ["_ds_row"])
        assert "already" in errors["a b"]
        assert stata_name_map(["a b"], {"a b": "_ds_row"}, ["_ds_row"]) == {
            "a b": "a_b"
        }
