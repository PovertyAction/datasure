"""Tests for the rename plan shared by the Prep rename step and its form."""

import pytest

from datasure.processing.rename_plan import (
    ByName,
    ChangeCase,
    RegexRename,
    Wildcard,
    plan_rename,
)


class TestByName:
    """Renaming listed old → new pairs."""

    def test_swap_resolves_both_pairs_without_collisions(self):
        plan = plan_rename(["a", "b", "c"], ByName((("a", "b"), ("b", "a"))))

        assert plan.pairs == (("a", "b"), ("b", "a"))
        assert plan.collisions == ()
        assert plan.can_apply

    def test_chain_is_allowed_because_names_are_judged_after_renaming(self):
        plan = plan_rename(["a", "b"], ByName((("a", "b"), ("b", "c"))))

        assert plan.pairs == (("a", "b"), ("b", "c"))
        assert plan.can_apply

    def test_pairs_follow_column_order(self):
        plan = plan_rename(["a", "b", "c"], ByName((("c", "z"), ("a", "x"))))

        assert plan.pairs == (("a", "x"), ("c", "z"))

    def test_new_name_taken_by_a_column_that_stays_is_a_collision(self):
        plan = plan_rename(["a", "b"], ByName((("a", "b"),)))

        assert plan.collisions == ("b",)
        assert plan.problems == {"a": "'b' is already a column and isn't renamed."}
        assert not plan.can_apply

    def test_two_pairs_with_the_same_new_name_both_collide(self):
        plan = plan_rename(["a", "b"], ByName((("a", "x"), ("b", "x"))))

        assert plan.collisions == ("x", "x")
        assert plan.problems["a"] == "'b' is also renamed to 'x'."
        assert plan.problems["b"] == "'a' is also renamed to 'x'."

    def test_collisions_ignore_case(self):
        plan = plan_rename(["a", "Age"], ByName((("a", "age"),)))

        assert plan.collisions == ("age",)

    def test_changing_only_the_case_of_a_name_is_allowed(self):
        plan = plan_rename(["Age"], ByName((("Age", "age"),)))

        assert plan.pairs == (("Age", "age"),)
        assert plan.can_apply

    def test_missing_old_names_are_reported_and_the_rest_still_resolve(self):
        plan = plan_rename(["a", "b"], ByName((("a", "x"), ("gone", "y"))))

        assert plan.pairs == (("a", "x"),)
        assert plan.missing == ("gone",)
        assert plan.can_apply

    def test_no_old_name_present_leaves_nothing_to_apply(self):
        plan = plan_rename(["a"], ByName((("gone", "y"),)))

        assert plan.pairs == ()
        assert not plan.can_apply

    def test_renaming_a_column_to_itself_is_not_a_pair(self):
        plan = plan_rename(["a"], ByName((("a", "a"),)))

        assert plan.pairs == ()

    def test_empty_new_name_is_invalid(self):
        plan = plan_rename(["a"], ByName((("a", " "),)))

        assert plan.invalid == (" ",)
        assert plan.problems == {"a": "Enter a new name."}
        assert not plan.can_apply

    def test_old_name_listed_twice_is_an_error(self):
        plan = plan_rename(["a"], ByName((("a", "x"), ("a", "y"))))

        assert plan.error == "'a' is listed more than once."
        assert not plan.can_apply


class TestWildcard:
    """Stata-style wildcard renames: * is any run of characters, ? is one."""

    @pytest.mark.parametrize(
        ("old", "new", "columns", "expected"),
        [
            ("x*", "y*", ["x1", "x_b", "ax1"], (("x1", "y1"), ("x_b", "y_b"))),
            ("*_old", "*_new", ["a_old", "old", "b_old_2"], (("a_old", "a_new"),)),
            ("grp_*", "*", ["grp_age", "age2"], (("grp_age", "age"),)),
            ("*", "*_r", ["a", "b"], (("a", "a_r"), ("b", "b_r"))),
            ("q?", "Q?", ["q1", "q10", "q"], (("q1", "Q1"),)),
            (
                "q*_*",
                "*_q*",
                ["q1_a", "q2_b", "q3"],
                (("q1_a", "1_qa"), ("q2_b", "2_qb")),
            ),
            ("x*", "x*", ["x1"], ()),
        ],
    )
    def test_patterns_behave_as_in_stata(self, old, new, columns, expected):
        assert plan_rename(columns, Wildcard(old, new)).pairs == expected

    def test_star_matches_an_empty_run(self):
        plan = plan_rename(["x"], Wildcard("x*", "y*"))

        assert plan.pairs == (("x", "y"),)

    def test_earlier_star_takes_as_much_as_it_can(self):
        plan = plan_rename(["a_b_c"], Wildcard("*_*", "*-*"))

        assert plan.pairs == (("a_b_c", "a_b-c"),)

    def test_a_pattern_that_leaves_an_empty_name_is_invalid(self):
        plan = plan_rename(["grp_"], Wildcard("grp_*", "*"))

        assert plan.pairs == (("grp_", ""),)
        assert plan.invalid == ("",)

    def test_old_pattern_must_match_the_whole_name(self):
        plan = plan_rename(["ax1", "x1a"], Wildcard("x?", "y?"))

        assert plan.pairs == ()

    def test_different_wildcard_counts_are_rejected(self):
        plan = plan_rename(["q1_a"], Wildcard("q*_*", "*"))

        assert plan.error == (
            "The old and new patterns need the same number of wildcards "
            "(the old pattern has 2, the new pattern has 1)."
        )

    @pytest.mark.parametrize(("old", "new"), [("x#", "y#"), ("x=", "y=")])
    def test_hash_and_equals_wildcards_are_not_supported(self, old, new):
        plan = plan_rename(["x1"], Wildcard(old, new))

        assert "aren't supported" in plan.error

    def test_empty_patterns_are_an_error(self):
        assert plan_rename(["x"], Wildcard("", "y")).error == "Enter the old pattern."
        assert plan_rename(["x"], Wildcard("x", "")).error == "Enter the new pattern."

    def test_matched_lists_every_column_the_pattern_fits(self):
        plan = plan_rename(["x1", "y1"], Wildcard("x*", "y*"))

        assert plan.matched == ("x1",)
        assert plan.collisions == ("y1",)

    def test_nothing_matched_leaves_nothing_to_apply(self):
        plan = plan_rename(["a"], Wildcard("x*", "y*"))

        assert plan.matched == ()
        assert not plan.can_apply


class TestChangeCase:
    """Lowercasing or uppercasing names, optionally filtered by a wildcard."""

    def test_lowercase_every_column_and_skip_names_that_dont_change(self):
        plan = plan_rename(["Q1", "q2", "AGE"], ChangeCase("lower"))

        assert plan.pairs == (("Q1", "q1"), ("AGE", "age"))
        assert plan.matched == ("Q1", "q2", "AGE")

    def test_uppercase_only_columns_matching_the_filter(self):
        plan = plan_rename(["q1", "q2", "age"], ChangeCase("upper", "q*"))

        assert plan.pairs == (("q1", "Q1"), ("q2", "Q2"))

    def test_nothing_changes_leaves_nothing_to_apply(self):
        plan = plan_rename(["q1"], ChangeCase("lower"))

        assert plan.pairs == ()
        assert not plan.can_apply

    def test_two_names_that_differ_only_in_case_collide(self):
        plan = plan_rename(["Q1", "q1"], ChangeCase("lower"))

        assert plan.collisions == ("q1",)

    def test_empty_filter_means_every_column(self):
        plan = plan_rename(["A"], ChangeCase("lower", ""))

        assert plan.pairs == (("A", "a"),)

    def test_unknown_case_is_an_error(self):
        assert plan_rename(["A"], ChangeCase("title")).error == (
            "Choose lower or upper case."
        )


class TestRegexRename:
    """Python regex find and replace, matched against the whole name."""

    def test_back_references_fill_the_replacement(self):
        plan = plan_rename(["q1_a", "q2_b"], RegexRename(r"q(\d+)_(\w)", r"\2_q\1"))

        assert plan.pairs == (("q1_a", "a_q1"), ("q2_b", "b_q2"))

    def test_pattern_must_match_the_whole_name(self):
        plan = plan_rename(["q1", "q10", "aq1"], RegexRename("q1", "question1"))

        assert plan.pairs == (("q1", "question1"),)
        assert plan.matched == ("q1",)

    def test_regex_that_wont_compile_is_an_error(self):
        plan = plan_rename(["q1"], RegexRename("q(", "x"))

        assert plan.error.startswith("The regex can't be used:")

    def test_reference_to_a_missing_group_is_an_error(self):
        plan = plan_rename(["q1"], RegexRename("q1", r"\2"))

        assert plan.error.startswith("The replacement can't be used:")

    def test_empty_pattern_is_an_error(self):
        assert plan_rename(["q1"], RegexRename("", "x")).error == "Enter a regex."

    def test_empty_replacement_result_is_invalid(self):
        plan = plan_rename(["q1"], RegexRename("q1", ""))

        assert plan.invalid == ("",)
