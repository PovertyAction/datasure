"""Tests for the ID duplicate cards logic."""

import datetime

import polars as pl
import pytest

from datasure.checks.id_duplicates import (
    CARDS_PER_PAGE,
    DUPLICATE,
    UNMATCHED,
    SortBy,
    build_export,
    card_records,
    comparison_grid,
    count_missing_ids,
    default_fields,
    find_duplicate_groups,
    find_unmatched_ids,
    paginate_cards,
    search_cards,
    sort_cards,
)


@pytest.fixture
def survey():
    """Survey data with one pair, one group of three and a missing ID."""
    return pl.DataFrame(
        {
            "hhid": ["A", "B", "A", "C", "B", None, "B"],
            "KEY": ["k1", "k2", "k3", "k4", "k5", "k6", "k7"],
            "date": [
                datetime.date(2024, 1, 1),
                datetime.date(2024, 1, 2),
                datetime.date(2024, 1, 5),
                datetime.date(2024, 1, 3),
                datetime.date(2024, 1, 3),
                datetime.date(2024, 1, 4),
                datetime.date(2024, 1, 4),
            ],
            "enum": ["e1", "e2", "e1", "e3", "e2", "e1", "e9"],
            "age": [30, 40, 31, 50, 40, 20, 40],
        }
    )


# ---------------------------------------------------------------------------
# Grouping
# ---------------------------------------------------------------------------


def test_find_duplicate_groups_one_card_per_duplicated_id(survey):
    groups = find_duplicate_groups(survey, "hhid", "KEY", "date")

    assert sorted(groups["id"].to_list()) == ["A", "B"]
    by_id = {row["id"]: row for row in groups.iter_rows(named=True)}
    assert by_id["A"]["n_records"] == 2
    assert by_id["B"]["n_records"] == 3
    assert by_id["B"]["keys"] == ["k2", "k5", "k7"]
    assert by_id["B"]["first_date"] == datetime.date(2024, 1, 2)
    assert by_id["B"]["latest_date"] == datetime.date(2024, 1, 4)
    assert set(groups["kind"].to_list()) == {DUPLICATE}


def test_find_duplicate_groups_ignores_missing_ids():
    data = pl.DataFrame({"hhid": [None, None, "A"], "KEY": ["k1", "k2", "k3"]})

    groups = find_duplicate_groups(data, "hhid", "KEY", None)

    assert groups.is_empty()


def test_find_duplicate_groups_without_date_column(survey):
    groups = find_duplicate_groups(survey, "hhid", "KEY", None)

    assert groups.height == 2
    assert groups["latest_date"].null_count() == 2


def test_find_duplicate_groups_ignores_unknown_date_column(survey):
    groups = find_duplicate_groups(survey, "hhid", "KEY", "not_a_column")

    assert groups.height == 2
    assert groups["latest_date"].null_count() == 2


def test_find_duplicate_groups_numeric_ids_are_shown_as_text():
    data = pl.DataFrame({"hhid": [1, 1, 2], "KEY": ["k1", "k2", "k3"]})

    groups = find_duplicate_groups(data, "hhid", "KEY", None)

    assert groups["id"].to_list() == ["1"]


def test_find_duplicate_groups_large_group():
    data = pl.DataFrame({"hhid": ["A"] * 12, "KEY": [f"k{i}" for i in range(12)]})

    groups = find_duplicate_groups(data, "hhid", "KEY", None)

    assert groups["n_records"].to_list() == [12]
    assert len(groups["rows"][0]) == 12


def test_card_records_returns_the_cards_rows(survey):
    groups = find_duplicate_groups(survey, "hhid", "KEY", "date")
    card = groups.filter(pl.col("id") == "B").row(0, named=True)

    records = card_records(survey, card)

    assert records["KEY"].to_list() == ["k2", "k5", "k7"]


def test_count_missing_ids(survey):
    assert count_missing_ids(survey, "hhid") == 1


# ---------------------------------------------------------------------------
# Comparison grid and differences
# ---------------------------------------------------------------------------


def test_comparison_grid_has_fields_as_rows_and_records_as_columns(survey):
    records = survey.filter(pl.col("hhid") == "A")

    grid = comparison_grid(records, ["KEY", "enum", "age"])

    assert grid.columns == ["Field", "Record 1", "Record 2", "differs"]
    assert grid["Field"].to_list() == ["KEY", "enum", "age"]
    assert grid.row(0) == ("KEY", "k1", "k3", True)


def test_comparison_grid_marks_differing_fields(survey):
    records = survey.filter(pl.col("hhid") == "B")

    grid = comparison_grid(records, ["enum", "age"])
    differs = dict(zip(grid["Field"], grid["differs"], strict=True))

    assert differs == {"enum": True, "age": False}


def test_comparison_grid_treats_missing_as_a_distinct_value():
    records = pl.DataFrame({"x": [1, None], "y": [None, None]})

    grid = comparison_grid(records, ["x", "y"])

    assert grid["differs"].to_list() == [True, False]


def test_comparison_grid_handles_nested_columns():
    records = pl.DataFrame({"x": [[1, 2], [1, 3]]})

    grid = comparison_grid(records, ["x"])

    assert grid["differs"].to_list() == [True]


def test_default_fields_keeps_configured_columns_in_order():
    columns = ["hhid", "KEY", "date", "enum", "team", "age", "sex"]

    fields = default_fields(
        columns,
        key="KEY",
        date="date",
        staff="enum",
        team="team",
        extra=["sex", "KEY", "missing"],
    )

    assert fields == ["KEY", "date", "enum", "team", "sex"]


def test_default_fields_skips_unconfigured_columns():
    fields = default_fields(
        ["hhid", "KEY"], key="KEY", date=None, staff=None, team=None, extra=[]
    )

    assert fields == ["KEY"]


# ---------------------------------------------------------------------------
# Unmatched backcheck IDs
# ---------------------------------------------------------------------------


def test_find_unmatched_ids_one_card_per_backcheck(survey):
    backcheck = pl.DataFrame(
        {
            "hhid": ["A", "Z", "Z", None, "Y"],
            "KEY": ["b1", "b2", "b3", "b4", "b5"],
            "bc_date": [datetime.date(2024, 2, d) for d in range(1, 6)],
        }
    )

    unmatched = find_unmatched_ids(backcheck, survey, "hhid", "KEY", "bc_date")

    assert unmatched["keys"].to_list() == [["b2"], ["b3"], ["b5"]]
    assert unmatched["id"].to_list() == ["Z", "Z", "Y"]
    assert set(unmatched["kind"].to_list()) == {UNMATCHED}
    assert unmatched["n_records"].to_list() == [1, 1, 1]


def test_find_unmatched_ids_matches_across_id_types():
    survey = pl.DataFrame({"hhid": [1, 2]})
    backcheck = pl.DataFrame({"hhid": ["1", "3"], "KEY": ["b1", "b2"]})

    unmatched = find_unmatched_ids(backcheck, survey, "hhid", "KEY", None)

    assert unmatched["id"].to_list() == ["3"]


def test_find_unmatched_ids_without_id_in_survey():
    survey = pl.DataFrame({"other": [1]})
    backcheck = pl.DataFrame({"hhid": ["1"], "KEY": ["b1"]})

    unmatched = find_unmatched_ids(backcheck, survey, "hhid", "KEY", None)

    assert unmatched["id"].to_list() == ["1"]


# ---------------------------------------------------------------------------
# Search, sort and pagination
# ---------------------------------------------------------------------------


@pytest.fixture
def cards(survey):
    return find_duplicate_groups(survey, "hhid", "KEY", "date")


def test_search_cards_by_id(cards):
    assert search_cards(cards, "a")["id"].to_list() == ["A"]


def test_search_cards_by_key(cards):
    assert search_cards(cards, "K5")["id"].to_list() == ["B"]


def test_search_cards_blank_query_keeps_everything(cards):
    assert search_cards(cards, "  ").height == cards.height


def test_search_cards_treats_query_literally(cards):
    assert search_cards(cards, ".*").is_empty()


def test_sort_cards_by_group_size(cards):
    assert sort_cards(cards, SortBy.GROUP_SIZE)["id"].to_list() == ["B", "A"]


def test_sort_cards_by_latest_date(cards):
    assert sort_cards(cards, SortBy.LATEST_DATE)["id"].to_list() == ["A", "B"]


def test_sort_cards_by_latest_date_puts_undated_last():
    cards = pl.DataFrame(
        {
            "id": ["X", "Y", "Z"],
            "n_records": [2, 2, 2],
            "latest_date": [None, datetime.date(2024, 1, 1), datetime.date(2024, 2, 1)],
        }
    )

    assert sort_cards(cards, SortBy.LATEST_DATE)["id"].to_list() == ["Z", "Y", "X"]


def _numbered_cards(n: int) -> pl.DataFrame:
    return pl.DataFrame({"id": [f"{i:02d}" for i in range(n)]})


def test_paginate_cards_ten_per_page():
    page, n_pages, current = paginate_cards(_numbered_cards(25), 3)

    assert CARDS_PER_PAGE == 10
    assert n_pages == 3
    assert current == 3
    assert page["id"].to_list() == [f"{i:02d}" for i in range(20, 25)]


def test_paginate_cards_clamps_page():
    page, n_pages, current = paginate_cards(_numbered_cards(5), 9)

    assert (n_pages, current) == (1, 1)
    assert page.height == 5


def test_paginate_cards_empty():
    page, n_pages, current = paginate_cards(_numbered_cards(0), 1)

    assert (page.height, n_pages, current) == (0, 1, 1)


def test_search_sort_and_paginate_together():
    data = pl.DataFrame(
        {
            "hhid": [f"H{i // 2:02d}" for i in range(44)] + ["X1", "X1", "X1"],
            "KEY": [f"k{i}" for i in range(47)],
        }
    )
    cards = find_duplicate_groups(data, "hhid", "KEY", None)

    found = sort_cards(search_cards(cards, "h1"), SortBy.GROUP_SIZE)
    page, n_pages, _ = paginate_cards(found, 2)

    assert found.height == 10
    assert n_pages == 1
    assert page["id"].to_list() == [f"H{i}" for i in range(10, 20)]


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def test_build_export_has_every_card_record_in_card_order(survey, cards):
    ordered = sort_cards(cards, SortBy.GROUP_SIZE)

    export = build_export(survey, ordered, "hhid", ["KEY", "date", "enum"])

    assert export.columns == ["issue", "hhid", "KEY", "date", "enum"]
    assert export["KEY"].to_list() == ["k2", "k5", "k7", "k1", "k3"]
    assert set(export["issue"].to_list()) == {"Duplicate ID"}


def test_build_export_includes_unmatched_records(survey):
    backcheck = pl.DataFrame(
        {"hhid": ["A", "A", "Q"], "KEY": ["b1", "b2", "b3"], "bc": ["x", "y", "z"]}
    )
    cards = pl.concat(
        [
            find_duplicate_groups(backcheck, "hhid", "KEY", None),
            find_unmatched_ids(backcheck, survey, "hhid", "KEY", None),
        ]
    )

    export = build_export(backcheck, cards, "hhid", ["KEY", "bc"])

    assert export["issue"].to_list() == [
        "Duplicate ID",
        "Duplicate ID",
        "Unmatched ID",
    ]
    assert export["KEY"].to_list() == ["b1", "b2", "b3"]


def test_build_export_with_no_cards(survey, cards):
    export = build_export(survey, cards.clear(), "hhid", ["KEY"])

    assert export.is_empty()
    assert export.columns == ["issue", "hhid", "KEY"]


def test_build_export_matches_the_searched_cards_across_pages():
    data = pl.DataFrame(
        {
            "hhid": [f"H{i // 2:02d}" for i in range(48)],
            "KEY": [f"k{i}" for i in range(48)],
        }
    )
    found = sort_cards(
        search_cards(find_duplicate_groups(data, "hhid", "KEY", None), "H1"),
        SortBy.GROUP_SIZE,
    )
    shown = []
    for page in (1, 2, 3):
        cards, _, _ = paginate_cards(found, page, per_page=4)
        for card in cards.iter_rows(named=True):
            shown.extend(card_records(data, card)["KEY"].to_list())

    export = build_export(data, found, "hhid", ["KEY"])

    assert found.height == 10
    assert export["KEY"].to_list() == shown
