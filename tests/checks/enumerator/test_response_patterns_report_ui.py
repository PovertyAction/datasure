"""AppTest tests for the Response Patterns section (seam B)."""

import json

import polars as pl
import pytest
from streamlit.testing.v1 import AppTest

ENUM = "enum"


def _values(n: int, round_count: int) -> list[int]:
    """Return ``n`` values spanning more than 10, ``round_count`` ending in 0/5."""
    others = [v for v in range(11, 300) if v % 5 != 0]
    return [10 + 5 * i for i in range(round_count)] + others[: n - round_count]


def _frame(values_by_enum: dict[str, list]) -> pl.DataFrame:
    enums, values = [], []
    for name, vals in values_by_enum.items():
        enums.extend([name] * len(vals))
        values.extend(vals)
    return pl.DataFrame(
        {
            "key": [f"k{i}" for i in range(len(values))],
            ENUM: enums,
            "age": values,
            "choice": ["yes", "no"] * (len(values) // 2) + ["yes"] * (len(values) % 2),
        }
    )


def _section_app(data, settings_file):
    from datasure.checks.enumerator.models import EnumeratorSettings
    from datasure.checks.enumerator.response_patterns.report_ui import (
        render_response_patterns,
    )

    render_response_patterns(
        data,
        settings_file,
        EnumeratorSettings(survey_key="key", survey_id="key", enumerator="enum"),
        None,
    )


def _save(settings_file: str, **response_patterns) -> None:
    with open(settings_file, "w") as f:
        json.dump({"enumerators": {"response_patterns": response_patterns}}, f)


def _run(data: pl.DataFrame, settings_file: str) -> AppTest:
    at = AppTest.from_function(_section_app, args=(data, settings_file)).run()
    assert not at.exception, at.exception
    return at


def _texts(elements) -> str:
    return "\n".join(str(e.value) for e in elements)


@pytest.fixture
def settings_file(tmp_path):
    return str(tmp_path / "page_settings.json")


@pytest.fixture
def team_data():
    # "rounder" ends 60% of answers in 0/5, the others 20%
    return _frame(
        {
            "rounder": _values(40, 24),
            "steady": _values(40, 8),
            "careful": _values(40, 8),
        }
    )


class TestMessages:
    def test_no_variables_selected_prompts_for_a_selection(
        self, team_data, settings_file
    ):
        at = _run(team_data, settings_file)

        assert "Select one or more variables" in _texts(at.info)

    def test_single_enumerator_needs_two(self, settings_file):
        _save(settings_file, selected_variables=["age"])

        at = _run(_frame({"solo": _values(40, 8)}), settings_file)

        assert "at least 2 enumerators" in _texts(at.info)

    def test_no_applicable_variables_for_the_sub_tab(self, team_data, settings_file):
        _save(settings_file, selected_variables=["choice"])

        at = _run(team_data, settings_file)

        assert "None of the selected variables are numeric" in _texts(at.info)

    def test_everyone_below_the_minimum(self, team_data, settings_file):
        _save(settings_file, selected_variables=["age"], min_sample=50)

        at = _run(team_data, settings_file)

        assert "fewer than 50 responses" in _texts(at.info)

    def test_skipped_variable_note(self, team_data, settings_file):
        data = team_data.with_columns(pl.lit(3).alias("kids"))
        _save(settings_file, selected_variables=["age", "kids"])

        at = _run(data, settings_file)

        assert "kids" in _texts(at.caption)
        assert "no variation" in _texts(at.caption)

    def test_low_sample_warning(self, settings_file):
        _save(settings_file, selected_variables=["age"])
        data = _frame({"rounder": _values(20, 12), "steady": _values(40, 8)})

        at = _run(data, settings_file)

        assert at.radio(key="rp_dp_enumerator").value == "rounder"
        assert "Low sample size — treat results with caution" in _texts(at.warning)


class TestEnumeratorSelection:
    def test_highest_score_is_selected_and_flagged(self, team_data, settings_file):
        _save(settings_file, selected_variables=["age"])

        at = _run(team_data, settings_file)

        radio = at.radio(key="rp_dp_enumerator")
        assert radio.value == "rounder"
        assert len(radio.options) == 3
        assert "rounder's responses end in 0 or 5 notably more often" in _texts(
            at.warning
        )

    def test_clicking_an_enumerator_shows_their_detail(self, team_data, settings_file):
        _save(settings_file, selected_variables=["age"])
        at = _run(team_data, settings_file)

        at.radio(key="rp_dp_enumerator").set_value("steady").run()

        assert not at.exception
        assert "steady's digit distribution is consistent" in _texts(at.success)


class TestVariableEditor:
    def test_lists_inferred_types_without_id_columns_or_a_selection(
        self, team_data, settings_file
    ):
        at = _run(team_data, settings_file)

        editor = at.dataframe(key="rp_variable_editor").value
        assert editor["Variable"].tolist() == ["age", "choice"]
        assert editor["Inferred type"].tolist() == ["integer", "categorical"]
        assert not editor["Select"].any()

    def test_shows_saved_selection_and_type_overrides(self, team_data, settings_file):
        _save(
            settings_file,
            selected_variables=["age"],
            type_overrides={"age": "continuous"},
        )

        at = _run(team_data, settings_file)

        editor = at.dataframe(key="rp_variable_editor").value
        assert editor["Select"].tolist() == [True, False]
        assert editor["Type"].tolist() == ["continuous", "categorical"]


class TestSettingsPersistence:
    def test_thresholds_survive_a_new_session(self, team_data, settings_file):
        _save(settings_file, selected_variables=["age"])
        at = _run(team_data, settings_file)

        at.number_input(key="rp_min_sample").set_value(10).run()
        at.number_input(key="rp_warn_sample").set_value(20).run()
        at.slider(key="rp_dp_threshold").set_value(70).run()
        assert not at.exception

        new_session = _run(team_data, settings_file)

        assert new_session.number_input(key="rp_min_sample").value == 10
        assert new_session.number_input(key="rp_warn_sample").value == 20
        assert new_session.slider(key="rp_dp_threshold").value == 70
        with open(settings_file) as f:
            saved = json.load(f)["enumerators"]["response_patterns"]
        assert saved["selected_variables"] == ["age"]

    def test_slider_description_follows_the_value(self, team_data, settings_file):
        _save(settings_file, selected_variables=["age"])
        at = _run(team_data, settings_file)

        at.slider(key="rp_dp_threshold").set_value(80).run()

        assert "1.8 times" in _texts(at.caption)
