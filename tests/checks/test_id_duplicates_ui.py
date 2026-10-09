"""Tests for the ID duplicate cards UI, run through Streamlit's AppTest."""

import datetime

import polars as pl
import pytest
from streamlit.testing.v1 import AppTest


def _cards_app(data, settings_file, survey_data=None, date_col="date"):
    """Render the ID duplicate cards for `data`."""
    from datasure.checks.id_duplicates_ui import IdView, render_id_duplicates

    view = IdView(
        name="backcheck" if survey_data is not None else "survey",
        data=data,
        id_col="hhid",
        key_col="KEY",
        date_col=date_col,
        staff_col="enum",
        team_col=None,
        display_cols_setting="id_table_display_cols",
        survey_data=survey_data,
    )
    render_id_duplicates(view, settings_file)


def _switcher_app(survey_count, backcheck_count):
    import streamlit as st

    from datasure.checks.id_duplicates_ui import render_dataset_switcher

    st.session_state["chosen"] = render_dataset_switcher(survey_count, backcheck_count)


@pytest.fixture
def survey():
    return pl.DataFrame(
        {
            "hhid": ["A", "B", "A", "C", "B", None, "B"],
            "KEY": ["k1", "k2", "k3", "k4", "k5", "k6", "k7"],
            "date": [datetime.date(2024, 1, d) for d in (1, 2, 5, 3, 3, 4, 4)],
            "enum": ["e1", "e2", "e1", "e3", "e2", "e1", "e9"],
            "age": [30, 40, 31, 50, 40, 20, 40],
        }
    )


@pytest.fixture
def settings_file(tmp_path):
    return str(tmp_path / "page_settings.json")


def _run(survey, settings_file, **kwargs):
    at = AppTest.from_function(
        _cards_app, args=(survey, settings_file), kwargs=kwargs, default_timeout=30
    )
    at.run()
    assert not at.exception, at.exception
    return at


def _metrics(at):
    return {m.label: m.value for m in at.metric}


def test_survey_view_metrics_and_one_card_per_duplicate_id(survey, settings_file):
    at = _run(survey, settings_file)

    assert _metrics(at) == {
        "Duplicate IDs": "2",
        "Records involved": "5",
        "Missing IDs": "1",
        "Resolved": "0",
    }
    assert len(at.dataframe) == 2


def test_card_grid_shows_default_fields_and_records(survey, settings_file):
    at = _run(survey, settings_file)

    # Sorted by group size, so B (3 records) is first.
    grid = at.dataframe[0].value
    assert list(grid.columns) == ["Field", "Record 1", "Record 2", "Record 3"]
    assert list(grid["Field"]) == ["KEY", "date", "enum"]


def test_compare_all_fields_and_only_differing(survey, settings_file):
    at = _run(survey, settings_file)

    at.toggle(key="iddup_survey_B_all").set_value(True).run()
    assert list(at.dataframe[0].value["Field"]) == list(survey.columns)

    at.toggle(key="iddup_survey_B_diff").set_value(True).run()
    # B: KEY, date and enum differ; hhid and age are the same.
    assert list(at.dataframe[0].value["Field"]) == ["KEY", "date", "enum"]


def test_search_by_key(survey, settings_file):
    at = _run(survey, settings_file)

    at.text_input(key="iddup_survey_search").input("k3").run()

    assert len(at.dataframe) == 1
    assert list(at.dataframe[0].value.iloc[0, 1:]) == ["k1", "k3"]


def test_pagination_shows_ten_cards_per_page(settings_file):
    data = pl.DataFrame(
        {
            "hhid": [f"H{i // 2:02d}" for i in range(24)],
            "KEY": [f"k{i}" for i in range(24)],
            "enum": ["e"] * 24,
        }
    )
    at = _run(data, settings_file, date_col=None)
    assert len(at.dataframe) == 10

    at.number_input(key="iddup_survey_page").set_value(2).run()
    assert len(at.dataframe) == 2


def test_search_resets_to_the_first_page(settings_file):
    data = pl.DataFrame(
        {
            "hhid": [f"H{i // 2:02d}" for i in range(24)],
            "KEY": [f"k{i}" for i in range(24)],
        }
    )
    at = _run(data, settings_file, date_col=None)
    at.number_input(key="iddup_survey_page").set_value(2).run()

    at.text_input(key="iddup_survey_search").input("H0").run()

    assert at.number_input(key="iddup_survey_page").value == 1
    assert len(at.dataframe) == 10


def test_without_date_column_sort_by_group_size_only(survey, settings_file):
    at = _run(survey.drop("date"), settings_file, date_col=None)

    assert at.selectbox(key="iddup_survey_sort").options == ["Group size"]
    assert len(at.dataframe) == 2


def test_text_date_column_is_not_offered_for_sorting(survey, settings_file):
    data = survey.with_columns(pl.col("date").cast(pl.String))

    at = _run(data, settings_file)

    assert at.selectbox(key="iddup_survey_sort").options == ["Group size"]
    # Shown as an ordinary field instead.
    assert "date" not in list(at.dataframe[0].value["Field"])


def test_no_duplicates_shows_a_message(settings_file):
    data = pl.DataFrame({"hhid": ["A", "B"], "KEY": ["k1", "k2"]})

    at = _run(data, settings_file, date_col=None)

    assert len(at.dataframe) == 0
    assert any("No duplicate IDs" in s.value for s in at.success)


def test_download_button_is_shown(survey, settings_file):
    at = _run(survey, settings_file)

    assert len(at.get("download_button")) == 1


def test_backcheck_view_lists_duplicate_and_unmatched_cards(survey, settings_file):
    backcheck = pl.DataFrame(
        {
            "hhid": ["A", "A", "Z", "C"],
            "KEY": ["b1", "b2", "b3", "b4"],
            "date": [datetime.date(2024, 2, d) for d in (1, 2, 3, 4)],
            "enum": ["bc1", "bc2", "bc1", "bc2"],
        }
    )

    at = _run(backcheck, settings_file, survey_data=survey)

    assert _metrics(at) == {
        "Duplicate IDs": "1",
        "Records involved": "2",
        "Missing IDs": "0",
        "Unmatched IDs": "1",
        "Resolved": "0",
    }
    assert len(at.dataframe) == 2
    unmatched_grid = at.dataframe[1].value
    assert list(unmatched_grid.columns) == ["Field", "Record 1"]
    assert list(unmatched_grid["Record 1"]) == ["b3", "2024-02-03", "bc1"]


def _switcher_labels(at):
    return list(at.button_group[0].proto.options[i].content for i in range(2))


def test_switcher_shows_duplicate_counts():
    at = AppTest.from_function(_switcher_app, args=(3, 0)).run()

    assert not at.exception
    assert _switcher_labels(at) == ["Survey data (3)", "Backcheck data (0)"]
    assert at.session_state["chosen"] == "Survey data"


def test_switcher_chooses_backcheck_data():
    at = AppTest.from_function(_switcher_app, args=(3, 0)).run()

    at.button_group[0].set_value("Backcheck data").run()

    assert at.session_state["chosen"] == "Backcheck data"


def test_switcher_without_backcheck_shows_na_and_keeps_survey_data():
    at = AppTest.from_function(_switcher_app, args=(2, None)).run()

    assert not at.exception
    assert _switcher_labels(at) == ["Survey data (2)", "Backcheck data (N/A)"]

    at.button_group[0].set_value("Backcheck data").run()

    assert at.session_state["chosen"] == "Survey data"
    assert at.button_group[0].value == "Survey data"
