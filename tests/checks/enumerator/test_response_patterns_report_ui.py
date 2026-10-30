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


def _section_app(data, settings_file, missing_codes=None):
    from datasure.checks.enumerator.models import EnumeratorSettings
    from datasure.checks.enumerator.response_patterns.report_ui import (
        render_response_patterns,
    )

    render_response_patterns(
        data,
        settings_file,
        EnumeratorSettings(survey_key="key", survey_id="key", enumerator="enum"),
        missing_codes,
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

        assert "rounder: terminal digits" in _texts(at.markdown)
        assert "Low sample size — treat results with caution" in _texts(at.warning)


class TestEnumeratorTable:
    def test_lists_enumerators_by_score_with_interviews_and_rates(
        self, team_data, settings_file
    ):
        _save(settings_file, selected_variables=["age"])

        at = _run(team_data, settings_file)

        table = at.dataframe(key="rp_dp_enumerators").value
        assert table["Enumerator"].tolist() == ["rounder", "careful", "steady"]
        assert table["Interviews"].tolist() == [40, 40, 40]
        assert table["Ending in 0 or 5 (%)"].tolist()[0] == pytest.approx(60)
        assert table["Rest of team (%)"].tolist()[0] == pytest.approx(20)
        assert table["Flag"].tolist() == ["High", "Low", "Low"]

    def test_highest_score_is_selected_by_default(self, team_data, settings_file):
        _save(settings_file, selected_variables=["age"])

        at = _run(team_data, settings_file)

        assert "rounder's responses end in 0 or 5 notably more often" in _texts(
            at.warning
        )

    def test_chart_y_axis_always_spans_0_to_100(self, team_data, settings_file):
        _save(settings_file, selected_variables=["age"])

        at = _run(team_data, settings_file)

        spec = json.loads(at.get("plotly_chart")[0].proto.spec)
        assert spec["layout"]["yaxis"]["range"] == [0, 100]

    def test_selecting_a_row_shows_that_enumerator(self, team_data, settings_file):
        _save(settings_file, selected_variables=["age"])
        at = _run(team_data, settings_file)

        at.session_state["rp_dp_enumerators"] = {
            "selection": {"rows": [2], "columns": [], "cells": []}
        }
        at.run()

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

    def test_infers_types_after_masking_missing_codes(self, team_data, settings_file):
        # -99.5 is a missing code, so the remaining values are all whole
        data = team_data.with_columns(
            pl.when(pl.col("age") == 11)
            .then(-99.5)
            .otherwise(pl.col("age").cast(pl.Float64))
            .alias("age")
        )
        codes = pl.DataFrame({"label": ["Refused"], "codes": ["-99.5"]})

        at = AppTest.from_function(
            _section_app, args=(data, settings_file, codes)
        ).run()

        editor = at.dataframe(key="rp_variable_editor").value
        assert editor["Inferred type"].tolist()[0] == "integer"

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


def _navigable_app(data, settings_file):
    """Render the section unless the test has navigated away from the page."""
    import streamlit as st

    from datasure.checks.enumerator.models import EnumeratorSettings
    from datasure.checks.enumerator.response_patterns.report_ui import (
        render_response_patterns,
    )

    if st.session_state.get("away"):
        st.write("Another page")
        return
    render_response_patterns(
        data,
        settings_file,
        EnumeratorSettings(survey_key="key", survey_id="key", enumerator="enum"),
        None,
    )


class TestSettingsPersistence:
    def test_returning_to_the_page_shows_the_saved_selection(
        self, team_data, settings_file
    ):
        at = AppTest.from_function(_navigable_app, args=(team_data, settings_file))
        at.run()
        # The user ticks "age"; the edit is saved, then they leave the page
        _save(settings_file, selected_variables=["age"])
        at.session_state["away"] = True
        at.run()

        at.session_state["away"] = False
        at.run()

        assert not at.exception
        editor = at.dataframe(key="rp_variable_editor").value
        assert editor["Select"].tolist() == [True, False]
        assert "rp_dp_enumerators" in [d.key for d in at.dataframe]

    def test_selection_of_a_column_now_excluded_is_dropped(
        self, team_data, settings_file
    ):
        # "key" became the survey key after it was selected; "gone" is not in
        # this data, so its selection is kept for when it returns
        _save(settings_file, selected_variables=["age", "key", "gone"])
        at = _run(team_data, settings_file)

        at.number_input(key="rp_min_sample").set_value(10).run()
        assert not at.exception

        with open(settings_file) as f:
            saved = json.load(f)["enumerators"]["response_patterns"]
        assert saved["selected_variables"] == ["age", "gone"]
        assert "Skipped" not in _texts(at.caption)

    def test_thresholds_survive_a_new_session(self, team_data, settings_file):
        _save(settings_file, selected_variables=["age"])
        at = _run(team_data, settings_file)

        at.number_input(key="rp_min_sample").set_value(10).run()
        at.number_input(key="rp_warn_sample").set_value(20).run()
        at.segmented_control(key="rp_dp_threshold").set_value(65).run()
        assert not at.exception

        new_session = _run(team_data, settings_file)

        assert new_session.number_input(key="rp_min_sample").value == 10
        assert new_session.number_input(key="rp_warn_sample").value == 20
        assert new_session.segmented_control(key="rp_dp_threshold").value == 65
        with open(settings_file) as f:
            saved = json.load(f)["enumerators"]["response_patterns"]
        assert saved["selected_variables"] == ["age"]


class TestFlagThresholds:
    def test_five_fixed_levels_default_to_medium(self, team_data, settings_file):
        at = _run(team_data, settings_file)

        control = at.segmented_control(key="rp_dp_threshold")
        assert control.options == [
            "Very high",
            "High",
            "Medium",
            "Low",
            "Very low",
        ]
        assert control.value == 50

    def test_description_follows_the_level(self, team_data, settings_file):
        at = _run(team_data, settings_file)

        at.segmented_control(key="rp_dp_threshold").set_value(80).run()

        assert "1.8 times" in _texts(at.caption)

    def test_level_changes_the_flags(self, team_data, settings_file):
        # rounder's 25% against careful's 20% scores 25
        data = _frame({"rounder": _values(40, 10), "careful": _values(40, 8)})
        _save(settings_file, selected_variables=["age"])
        at = _run(data, settings_file)  # rounder scores 25: Low at Medium

        at.segmented_control(key="rp_dp_threshold").set_value(20).run()

        table = at.dataframe(key="rp_dp_enumerators").value
        assert table["Flag"].tolist()[0] == "High"


# =============================================================================
# Range Compression
# =============================================================================

SPREAD = [float(v) for v in range(30, 70)]


def _narrowed(values: list[float], factor: float, shift: float = 0.0) -> list[float]:
    mean = sum(values) / len(values)
    return [mean + (v - mean) * factor + shift for v in values]


def _range_frame(values_by_enum: dict[str, list[float]]) -> pl.DataFrame:
    """Build the section's data with ``income`` and a matching ``age``."""
    frame = _frame(values_by_enum).with_columns(pl.col("age").cast(pl.Float64))
    return frame.with_columns((pl.col("age") * 100).alias("income"))


@pytest.fixture
def range_data():
    # "anchor" answers within half the spread of the others
    return _range_frame(
        {"anchor": _narrowed(SPREAD, 0.4), "steady": SPREAD, "careful": SPREAD}
    )


def _range_tab(at: AppTest):
    return next(t for t in at.tabs if t.label == "Range Compression")


class TestRangeCompressionTab:
    def test_lists_enumerators_by_score_with_flags(self, range_data, settings_file):
        _save(settings_file, selected_variables=["age"])

        at = _run(range_data, settings_file)

        table = at.dataframe(key="rp_rc_enumerators").value
        assert table["Enumerator"].tolist()[0] == "anchor"
        assert table["Flag"].tolist()[0] == "High"
        assert table["SD ratio"].tolist()[0] == pytest.approx(0.4, abs=0.01)
        assert table["Signal"].tolist()[0] == "Compression"

    def test_highest_score_shows_tiles_and_compression_verdict(
        self, range_data, settings_file
    ):
        _save(settings_file, selected_variables=["age"])

        at = _run(range_data, settings_file)

        tab = _range_tab(at)
        assert "anchor: spread and level" in _texts(tab.markdown)
        assert "spread much less widely" in _texts(tab.warning)
        labels = [m.label for m in tab.metric]
        assert labels == ["Mean", "Standard deviation", "SD ratio", "Score set by"]
        assert tab.metric[2].value.startswith("0.4")
        assert tab.metric[3].value == "Compression on age"

    def test_compressed_bars_are_amber_on_shared_buckets(
        self, range_data, settings_file
    ):
        _save(settings_file, selected_variables=["age"])

        at = _run(range_data, settings_file)

        spec = json.loads(at.get("plotly_chart")[1].proto.spec)
        enum_bars, team_bars = spec["data"]
        assert team_bars["name"] == "Rest of team"
        assert enum_bars["x"] == team_bars["x"]
        assert len(enum_bars["x"]) == 10
        assert set(enum_bars["marker"]["color"]) == {"#f5cb57"}

    def test_both_verdicts_show_compression_first(self, settings_file):
        data = _range_frame(
            {
                "drifter": _narrowed(SPREAD, 0.4, shift=30),
                "steady": SPREAD,
                "careful": SPREAD,
            }
        )
        _save(settings_file, selected_variables=["age"])

        at = _run(data, settings_file)

        warnings = [w.value for w in _range_tab(at).warning]
        assert "spread much less widely" in warnings[0]
        assert "above the rest of the team's" in warnings[1]
        # Compressed as well as shifted, so the bars are amber
        spec = json.loads(at.get("plotly_chart")[1].proto.spec)
        assert set(spec["data"][0]["marker"]["color"]) == {"#f5cb57"}

    def test_shift_only_keeps_the_usual_bar_colour(self, settings_file):
        data = _range_frame(
            {
                "high": _narrowed(SPREAD, 1, shift=30),
                "steady": SPREAD,
                "careful": SPREAD,
            }
        )
        _save(settings_file, selected_variables=["age"])

        at = _run(data, settings_file)

        warnings = [w.value for w in _range_tab(at).warning]
        assert len(warnings) == 1
        assert "above the rest of the team's" in warnings[0]
        spec = json.loads(at.get("plotly_chart")[1].proto.spec)
        assert set(spec["data"][0]["marker"]["color"]) == {"#155240"}

    def test_switching_the_variable_redraws_the_histogram(
        self, range_data, settings_file
    ):
        _save(settings_file, selected_variables=["age", "income"])
        at = _run(range_data, settings_file)
        (select,) = _range_tab(at).selectbox
        assert select.value == "age"

        select.set_value("income").run()

        assert not at.exception
        spec = json.loads(at.get("plotly_chart")[1].proto.spec)
        assert "income" in spec["layout"]["xaxis"]["title"]["text"]

    def test_selecting_a_row_shows_that_enumerator(self, range_data, settings_file):
        _save(settings_file, selected_variables=["age"])
        at = _run(range_data, settings_file)

        at.session_state["rp_rc_enumerators"] = {
            "selection": {"rows": [2], "columns": [], "cells": []}
        }
        at.run()

        assert not at.exception
        assert "spread and centred like the rest of the team's" in _texts(
            _range_tab(at).success
        )

    def test_team_without_variation_is_noted(self, settings_file):
        # varied's rest of team is flat, which always answers 50
        data = _range_frame({"varied": SPREAD, "flat": [50.0] * 40})
        _save(settings_file, selected_variables=["age"])
        at = _run(data, settings_file)

        at.session_state["rp_rc_enumerators"] = {
            "selection": {"rows": [1], "columns": [], "cells": []}
        }
        at.run()

        assert not at.exception
        assert "no variation in the rest of the team's responses" in _texts(
            _range_tab(at).caption
        )

    def test_no_applicable_variables(self, range_data, settings_file):
        _save(settings_file, selected_variables=["choice"])

        at = _run(range_data, settings_file)

        assert "Range Compression has nothing to check" in _texts(_range_tab(at).info)

    def test_threshold_survives_a_new_session(self, range_data, settings_file):
        _save(settings_file, selected_variables=["age"])
        at = _run(range_data, settings_file)

        at.segmented_control(key="rp_rc_threshold").set_value(65).run()
        assert not at.exception
        assert "0.35 times as widely" in _texts(at.caption)

        new_session = _run(range_data, settings_file)

        assert new_session.segmented_control(key="rp_rc_threshold").value == 65
        table = new_session.dataframe(key="rp_rc_enumerators").value
        assert table["Flag"].tolist()[0] == "Moderate"
