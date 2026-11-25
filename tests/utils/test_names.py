"""Tests for the shared name rule for dataset aliases and check page names."""

import pytest

from datasure.utils.names import (
    NAME_MAX_LENGTH,
    name_clash,
    name_id,
    name_problem,
    suggest_name,
)

VALID_NAMES = [
    "baseline",
    "Baseline 1",
    "baseline-1",
    "baseline_1",
    "HH HFC",
    "hh-hfc",
    "Survey",
    "select",
    "a",
    "a" * NAME_MAX_LENGTH,
]

INVALID_NAMES = [
    "",
    "   ",
    "baseline.1",
    "HH/HFC",
    "HH\\HFC",
    "Round 1: HH",
    "HH?",
    "HH*",
    "a<b",
    "a>b",
    "a|b",
    'say "hi"',
    "data (v2)",
    "2024 HH",
    "_hidden",
    "-dash",
    "école",
    "a" * (NAME_MAX_LENGTH + 1),
]


class TestNameProblem:
    """name_problem says why a name is not allowed, or nothing if it is."""

    @pytest.mark.parametrize("name", VALID_NAMES)
    def test_accepts_valid_names(self, name):
        assert name_problem(name) is None

    @pytest.mark.parametrize("name", INVALID_NAMES)
    def test_rejects_invalid_names(self, name):
        assert name_problem(name)

    def test_message_lists_allowed_characters(self):
        message = name_problem("HH/HFC")
        assert "letters, digits, spaces" in message
        assert "_" in message
        assert "-" in message

    def test_message_says_name_must_start_with_letter(self):
        assert "start with a letter" in name_problem("2024 HH")

    def test_message_gives_length_limit(self):
        assert str(NAME_MAX_LENGTH) in name_problem("a" * (NAME_MAX_LENGTH + 1))


class TestNameId:
    """Every accepted name keeps the ID existing projects already use."""

    @pytest.mark.parametrize("name", VALID_NAMES)
    def test_id_matches_stored_formula(self, name):
        expected = name.lower().replace(" ", "_").replace("-", "_")
        assert name_id(name) == expected

    @pytest.mark.parametrize(
        ("name", "expected"),
        [
            ("Household Survey", "household_survey"),
            ("Follow-up 2", "follow_up_2"),
            ("HH HFC", "hh_hfc"),
        ],
    )
    def test_known_ids(self, name, expected):
        assert name_id(name) == expected


class TestNameClash:
    """Two names clash when they share an ID."""

    @pytest.mark.parametrize("name", ["baseline-1", "Baseline 1", "BASELINE_1"])
    def test_clash_names_the_existing_entry(self, name):
        message = name_clash(name, ["other", "baseline_1"], kind="alias")
        assert message == (
            f"'{name}' is too similar to existing alias 'baseline_1'. "
            "Please choose a different name."
        )

    def test_page_names_clash_by_id(self):
        message = name_clash("hh-hfc", ["HH HFC"], kind="page name")
        assert "existing page name 'HH HFC'" in message

    def test_case_only_difference_clashes(self):
        assert name_clash("survey", ["Survey"], kind="alias")

    def test_distinct_names_do_not_clash(self):
        assert name_clash("baseline_2", ["baseline_1"], kind="alias") is None

    def test_renaming_an_entry_to_its_own_id_is_allowed(self):
        assert (
            name_clash("hh hfc", ["HH HFC", "other"], kind="page name", own="HH HFC")
            is None
        )

    def test_renaming_onto_another_entry_clashes(self):
        assert name_clash("other", ["HH HFC", "Other"], kind="page name", own="HH HFC")


class TestSuggestName:
    """suggest_name turns free text, such as a form title, into a valid name."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            ("Household Survey", "Household Survey"),
            ("HH survey (v2)", "HH survey _v2_"),
            ("Round 1: HH", "Round 1_ HH"),
        ],
    )
    def test_cleans_disallowed_characters(self, text, expected):
        assert suggest_name(text) == expected

    def test_truncates_to_length_limit(self):
        suggestion = suggest_name("A very long household survey title")
        assert len(suggestion) <= NAME_MAX_LENGTH
        assert name_problem(suggestion) is None

    @pytest.mark.parametrize("text", ["2024 Household", "", "école"])
    def test_returns_empty_when_no_valid_name(self, text):
        assert suggest_name(text) == ""
