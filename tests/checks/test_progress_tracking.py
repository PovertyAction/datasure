"""Tests for the Progress check's tracking-file and master-list modes (#410).

All data here is synthetic: master lists in real projects hold names and
phone numbers, which must never appear in tests or fixtures.
"""

import datetime
import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks import progress as progress_module
from datasure.checks import progress_tracking_ui as ui
from datasure.checks.context import CheckContext, CheckData
from datasure.checks.progress import (
    ProgressSettings,
    TrackingSource,
    attention_text,
    compute_progress,
    describe_target,
    progress_headline,
    progress_report,
    resolve_progress,
)
from datasure.checks.progress_tracking import UnitRow, normalize_keys
from datasure.utils.dataframe_utils import ColumnByType


@pytest.fixture(autouse=True)
def mock_database_functions(monkeypatch):
    """Override the autouse database fixture from conftest: not needed here."""


AS_OF = datetime.date(2026, 10, 14)

CONDITION = {"outcome": "outcome", "outcome_vals": ["complete"]}


def _survey(rows: list[tuple]) -> pl.DataFrame:
    """Survey rows of (id, date, village, outcome); dates are ISO text."""
    return pl.DataFrame(
        rows,
        schema={
            "hhid": pl.String,
            "when": pl.String,
            "village": pl.String,
            "outcome": pl.String,
        },
        orient="row",
    )


def _settings(**overrides) -> ProgressSettings:
    values = {"survey_id": "hhid", "survey_date": "when", **CONDITION, **overrides}
    return ProgressSettings(**values)


# v1 has h1 (completed twice) and h2 (refused); v2 has h3 completed;
# v9 is not in the tracking file.
SURVEY = _survey(
    [
        ("h1", "2026-10-12", "v1", "complete"),
        ("h1", "2026-10-13", "v1", "complete"),
        ("h2", "2026-10-12", "v1", "refused"),
        ("h3", "2026-10-12", "v2", "complete"),
        ("h4", "2026-10-13", "v9", "complete"),
    ]
)

TRACKING = pl.DataFrame(
    {
        "village_code": ["v1", "v2", "v3"],
        "district": ["d1", "d1", "d2"],
        "target": [4, 2, 6],
    }
)

TRACKING_SETTINGS = {
    "tracking_target": "target",
    "tracking_unit": "village_code",
    "survey_unit": "village",
}


class TestMode:
    def test_without_a_tracking_dataset_the_target_is_fixed(self):
        result = compute_progress(SURVEY, _settings(survey_target=10), AS_OF)

        assert result.mode == "fixed"
        assert result.sections == ["Overview", "Follow-up"]

    def test_a_target_column_makes_a_tracking_file(self):
        result = compute_progress(
            SURVEY, _settings(**TRACKING_SETTINGS), AS_OF, tracking=TRACKING
        )

        assert result.mode == "tracking file"
        assert result.sections == ["Overview", "Follow-up", "By unit"]

    def test_no_target_column_makes_a_master_list(self):
        result = compute_progress(
            SURVEY, _settings(tracking_id="hhid"), AS_OF, tracking=TRACKING
        )

        assert result.mode == "master list"
        assert result.sections == ["Overview", "Follow-up", "By unit", "Respondents"]


class TestNormalizeKeys:
    def test_trims_spaces(self):
        keys = normalize_keys(
            pl.Series([" R-0012 ", "R-0012"]), strip_leading_zeros=False
        )

        assert keys.to_list() == ["R-0012", "R-0012"]

    def test_keeps_leading_zeros_by_default(self):
        keys = normalize_keys(pl.Series(["0123", "123"]), strip_leading_zeros=False)

        assert keys.to_list() == ["0123", "123"]

    def test_strips_leading_zeros_when_asked(self):
        keys = normalize_keys(pl.Series(["0123", "123", "000", "R-0012"]), True)

        assert keys.to_list() == ["123", "123", "0", "R-0012"]

    def test_does_not_fold_case(self):
        assert normalize_keys(pl.Series(["ab", "AB"]), False).to_list() == ["ab", "AB"]

    def test_whole_number_floats_match_their_integers(self):
        keys = normalize_keys(pl.Series([12.0, None]), strip_leading_zeros=False)

        assert keys.to_list() == ["12", None]

    def test_blank_text_is_missing(self):
        assert normalize_keys(pl.Series(["  ", None]), False).to_list() == [None, None]


def _table(level) -> list[tuple]:
    """A unit level's rows as (unit, target, submissions, unique, completed, status)."""
    return [
        (r.unit, r.target, r.submissions, r.unique, r.completed, r.status)
        for r in level.rows
    ]


class TestTrackingFile:
    def result(self, tracking=TRACKING, survey=SURVEY, **overrides):
        settings = _settings(
            **TRACKING_SETTINGS, tracking_parents=["district"], **overrides
        )
        return compute_progress(survey, settings, AS_OF, tracking=tracking)

    def test_the_target_is_the_sum_of_the_units(self):
        counts = self.result().counts

        assert counts.target == 12
        assert counts.completed == 3
        assert counts.remaining == 9
        assert counts.percentage == 25.0

    def test_the_fixed_target_is_ignored(self):
        assert self.result(survey_target=999).counts.target == 12

    def test_counts_each_unit_against_its_target(self):
        level = self.result().unit_levels[0]

        assert level.column == "village_code"
        assert _table(level) == [
            ("v1", 4, 3, 2, 1, "behind"),
            ("v2", 2, 1, 1, 1, "on track"),
            ("v3", 6, 0, 0, 0, "behind"),
            ("Untracked", None, 1, 1, 1, "untracked"),
        ]
        v1 = level.rows[0]
        assert (v1.percentage, v1.remaining) == (25.0, 3)

    def test_parents_sum_their_children(self):
        level = self.result().unit_levels[1]

        assert level.column == "district"
        assert _table(level) == [
            ("d1", 6, 4, 3, 2, "behind"),
            ("d2", 6, 0, 0, 0, "behind"),
            ("Untracked", None, 1, 1, 1, "untracked"),
        ]

    def test_units_past_their_target_are_over_target(self):
        tracking = TRACKING.with_columns(target=pl.Series([1, 2, 6]))
        survey = SURVEY.with_columns(outcome=pl.lit("complete"))

        rows = self.result(tracking, survey).unit_levels[0].rows
        assert [(r.unit, r.status) for r in rows[:2]] == [
            ("v1", "over target"),  # 2 completed of 1
            ("v2", "on track"),  # 1 of 1 is not over
        ]
        assert rows[0].remaining == 0

    def test_a_unit_with_a_target_of_0_is_untracked(self):
        tracking = TRACKING.with_columns(target=pl.Series([4, 0, 6]))

        rows = self.result(tracking).unit_levels[0].rows
        assert [r.unit for r in rows] == ["v1", "v3", "Untracked"]
        assert (rows[-1].submissions, rows[-1].completed) == (2, 2)

    def test_counts_untracked_units(self):
        assert self.result().untracked_units == 1

    def test_units_match_after_normalization(self):
        tracking = TRACKING.with_columns(village_code=pl.Series([" v1", "v2 ", "v3"]))

        assert self.result(tracking).untracked_units == 1

    def test_to_dos_link_to_by_unit(self):
        todos = {t.label: (t.count, t.section) for t in self.result().todos}

        assert todos["Units below 50% of target"] == (2, "By unit")
        assert todos["Untracked units"] == (1, "By unit")


# h1 completed and h2 refused in v1; h3 completed in v2; h5 never visited.
# h4 is in the survey but not on the list.
MASTER = pl.DataFrame(
    {
        "resp_id": ["h1", " h2", "h3", "h5"],
        "vill": ["v1", "v1", "v2", "v2"],
        "landmark": ["blue gate", "red roof", "near well", "by school"],
    }
)

MASTER_SETTINGS = {"tracking_id": "resp_id", "tracking_unit": "vill"}


class TestMasterList:
    def result(self, master=MASTER, survey=SURVEY, **overrides):
        settings = _settings(**{**MASTER_SETTINGS, **overrides})
        return compute_progress(survey, settings, AS_OF, tracking=master)

    def test_the_target_is_the_number_of_respondents(self):
        assert self.result().counts.target == 4

    def test_units_come_from_the_master_list_through_the_id(self):
        survey = SURVEY.drop("village")

        level = self.result(survey=survey).unit_levels[0]

        assert level.column == "vill"
        assert _table(level) == [
            ("v1", 2, 3, 2, 1, "on track"),
            ("v2", 2, 1, 1, 1, "on track"),
            ("Untracked", None, 1, 1, 1, "untracked"),
        ]

    def test_every_respondent_has_a_status(self):
        statuses = {r.id: (r.status, r.unit) for r in self.result().respondents}

        assert statuses == {
            "h1": ("Completed", "v1"),
            "h2": ("Attempted not completed", "v1"),
            "h3": ("Completed", "v2"),
            "h5": ("Pending", "v2"),
            "h4": ("Unexpected", None),
        }

    def test_unexpected_ids_keep_their_last_submission_date(self):
        unexpected = [r for r in self.result().respondents if r.status == "Unexpected"]

        assert unexpected[0].last_date == datetime.date(2026, 10, 13)

    def test_respondents_carry_the_extra_columns(self):
        result = self.result(tracking_display=["landmark"])

        h5 = next(r for r in result.respondents if r.id == "h5")
        assert h5.extra == {"landmark": "by school"}

    def test_the_unexpected_ids_to_do_links_to_respondents(self):
        todos = {t.label: (t.count, t.section) for t in self.result().todos}

        assert todos == {"Unexpected IDs": (1, "Respondents")}
        assert self.result().untracked_units == 0

    def test_leading_zeros_match_only_with_the_toggle(self):
        master = pl.DataFrame({"resp_id": ["0123"], "vill": ["v1"]})
        survey = _survey([("123", "2026-10-12", None, "complete")])

        off = self.result(master, survey).respondents
        on = self.result(master, survey, strip_leading_zeros=True).respondents

        assert {r.status for r in off} == {"Pending", "Unexpected"}
        assert [(r.id, r.status) for r in on] == [("123", "Completed")]

    def test_without_a_unit_column_every_respondent_is_in_one_unit(self):
        result = self.result(tracking_unit=None)

        assert [r.unit for r in result.unit_levels[0].rows] == ["All", "Untracked"]

    def test_without_a_unit_column_the_finest_parent_is_the_unit(self):
        master = MASTER.with_columns(district=pl.Series(["d1", "d1", "d2", "d2"]))

        result = self.result(
            master, tracking_unit=None, tracking_parents=["vill", "district"]
        )

        levels = {
            level.column: [(r.unit, r.target) for r in level.rows]
            for level in result.unit_levels
        }
        assert levels == {
            "vill": [("v1", 2), ("v2", 2), ("Untracked", None)],
            "district": [("d1", 2), ("d2", 2), ("Untracked", None)],
        }
        assert {r.id: r.unit for r in result.respondents}["h5"] == "v2"
        assert result.issues == []


def _issues(result) -> list[tuple]:
    return [(i.level, i.values) for i in result.issues]


class TestValidation:
    def tracking_file(self, tracking, **overrides):
        settings = _settings(**{**TRACKING_SETTINGS, **overrides})
        return compute_progress(SURVEY, settings, AS_OF, tracking=tracking)

    def master_list(self, master):
        settings = _settings(**MASTER_SETTINGS)
        return compute_progress(SURVEY, settings, AS_OF, tracking=master)

    def test_a_repeated_unit_is_a_blocking_error(self):
        tracking = pl.DataFrame(
            {"village_code": ["v1", "v1 ", "v2", "v2", "v3"], "target": [1] * 5}
        )

        result = self.tracking_file(tracking)

        assert _issues(result) == [("error", ["v1", "v2"])]
        assert result.unit_levels == []
        assert result.counts.target is None

    def test_a_missing_unit_drops_the_row_with_a_warning(self):
        tracking = pl.DataFrame(
            {"village_code": ["v1", None, " "], "target": [4, 5, 6]}
        )

        result = self.tracking_file(tracking)

        assert [(i.level, i.message[:2]) for i in result.issues] == [("warning", "2 ")]
        assert result.counts.target == 4

    def test_bad_targets_count_as_0_with_a_warning(self):
        tracking = pl.DataFrame(
            {
                "village_code": ["v1", "v2", "v3", "v4"],
                "target": ["4", "", "lots", "-2"],
            }
        )

        result = self.tracking_file(tracking)

        assert _issues(result) == [("warning", ["v2", "v3", "v4"])]
        assert result.counts.target == 4

    def test_infinite_targets_count_as_0_and_fractions_are_rounded_down(self):
        tracking = pl.DataFrame(
            {"village_code": ["v1", "v2", "v3"], "target": ["4.5", "inf", "2"]}
        )

        result = self.tracking_file(tracking)

        assert _issues(result) == [("warning", ["v2"]), ("warning", ["v1"])]
        assert result.counts.target == 6

    def test_a_master_list_row_without_a_unit_is_kept_with_a_warning(self):
        master = pl.DataFrame({"resp_id": ["h1", "h2"], "vill": ["v1", None]})

        result = self.master_list(master)

        assert [i.level for i in result.issues] == ["warning"]
        assert [r.unit for r in result.unit_levels[0].rows][:2] == ["(blank)", "v1"]

    def test_a_unit_with_conflicting_parents_is_warned_about(self):
        master = pl.DataFrame(
            {
                "resp_id": ["h1", "h2", "h3"],
                "vill": ["v1", "v1", "v2"],
                "district": ["d1", "d2", "d1"],
            }
        )
        settings = _settings(**MASTER_SETTINGS, tracking_parents=["district"])

        result = compute_progress(SURVEY, settings, AS_OF, tracking=master)

        assert _issues(result) == [("warning", ["v1"])]

    def test_blank_survey_units_are_not_counted_as_an_untracked_unit(self):
        survey = SURVEY.with_columns(village=pl.Series(["v1", "v1", None, "v2", "v9"]))
        settings = _settings(**TRACKING_SETTINGS)

        result = compute_progress(survey, settings, AS_OF, tracking=TRACKING)

        assert result.untracked_units == 1  # v9

    def test_a_repeated_id_is_a_blocking_error(self):
        master = pl.DataFrame({"resp_id": ["h1", "h1", "h2"], "vill": ["v1"] * 3})

        result = self.master_list(master)

        assert _issues(result) == [("error", ["h1"])]
        assert result.respondents == []

    def test_a_missing_id_drops_the_row_with_a_warning(self):
        master = pl.DataFrame({"resp_id": ["h1", None], "vill": ["v1", "v1"]})

        result = self.master_list(master)

        assert [i.level for i in result.issues] == ["warning"]
        assert result.counts.target == 1

    def test_unchosen_columns_are_a_blocking_error(self):
        result = self.tracking_file(TRACKING, survey_unit=None)

        assert [i.level for i in result.issues] == ["error"]
        assert "unit column in the survey" in result.issues[0].message
        assert result.unit_levels == []

    def test_a_column_the_data_no_longer_has_is_a_blocking_error(self):
        result = self.tracking_file(TRACKING, tracking_target="gone")

        assert _issues(result) == [("error", ["gone"])]


def _context(tmp_path, saved: dict, tracking=None, survey_target=None):
    """A check context whose settings file holds the saved progress settings."""
    setting_file = tmp_path / "settings.json"
    setting_file.write_text(json.dumps({"progress": saved}))
    config = SimpleNamespace(
        survey_key=None,
        survey_id="hhid",
        survey_date="when",
        survey_target=survey_target,
        enumerator=None,
        tracking_data_name="tracking" if tracking is not None else None,
        setting_file=setting_file,
    )
    return CheckContext(
        project_id="project",
        config=config,
        data=CheckData(page_data=SURVEY, tracking_data=tracking),
        survey_columns=None,
    )


class TestResolveProgress:
    def test_a_fixed_target_without_a_condition_counts_unique_ids(self, tmp_path):
        resolved = resolve_progress(_context(tmp_path, {}, survey_target=10))

        assert (resolved.mode, resolved.target, resolved.achieved) == ("fixed", 10, 4)
        assert resolved.basis == "unique IDs"

    def test_a_tracking_file_gives_its_total_and_unit_targets(self, tmp_path):
        saved = {**TRACKING_SETTINGS, **CONDITION, "tracking_parents": ["district"]}

        resolved = resolve_progress(_context(tmp_path, saved, TRACKING))

        assert (resolved.target, resolved.achieved) == (12, 3)
        assert resolved.basis == "completed interviews"
        targets = {
            level.column: {r.unit: r.target for r in level.rows}
            for level in resolved.unit_levels
        }
        assert targets["district"] == {"d1": 6, "d2": 6, "Untracked": None}

    def test_an_empty_tracking_dataset_falls_back_to_the_fixed_target(self, tmp_path):
        context = _context(tmp_path, TRACKING_SETTINGS, TRACKING.clear(), 10)

        assert resolve_progress(context).target == 10

    def test_the_summary_headline_agrees(self, tmp_path):
        saved = {**MASTER_SETTINGS, **CONDITION}
        context = _context(tmp_path, saved, MASTER)

        headline = progress_headline(
            SURVEY,
            context.config.setting_file,
            {"survey_id": "hhid", "survey_date": "when"},
            MASTER,
        )

        assert headline.count == resolve_progress(context).achieved == 3
        assert headline.value == "3 / 4"


# ==============================================================================
# Page: sections, header strip, attention pill, By unit and Respondents
# ==============================================================================


def _mock_st():
    mock_st = MagicMock()
    mock_st.columns.side_effect = lambda spec, **kwargs: [
        MagicMock() for _ in range(spec if isinstance(spec, int) else len(spec))
    ]
    mock_st.segmented_control.return_value = "All"
    mock_st.pills.return_value = "Day"
    mock_st.session_state = {}
    return mock_st


def _page_sections(tmp_path, settings, tracking) -> list[str]:
    survey_cols = ColumnByType(
        categorical_columns=["hhid", "village"], datetime_columns=["when"]
    )
    with (
        patch.object(progress_module, "st", _mock_st()),
        patch("datasure.utils.onboarding_utils.is_demo_project", return_value=False),
        patch.object(
            progress_module, "progress_report_settings", return_value=settings
        ),
        patch.object(progress_module, "section_header") as headers,
        patch.object(
            progress_module,
            "render_chart_controls",
            return_value=("Cumulative", "Day"),
        ),
        patch.object(progress_module, "display_progress_header"),
        patch.object(progress_module, "display_overview"),
        patch.object(progress_module, "display_follow_up"),
        patch.object(progress_module, "display_by_unit") as by_unit,
        patch.object(progress_module, "display_respondents") as respondents,
    ):
        progress_report(
            SURVEY,
            str(tmp_path / "s.json"),
            {"survey_id": "hhid"},
            survey_cols,
            tracking,
        )
    # Without the Follow-up queue badge
    titles = [c.args[0].split(" :")[0] for c in headers.call_args_list]
    assert by_unit.called == ("By unit" in titles)
    assert respondents.called == ("Respondents" in titles)
    return titles


class TestPageSections:
    def test_fixed_shows_overview_and_follow_up(self, tmp_path):
        titles = _page_sections(tmp_path, _settings(), None)

        assert titles == ["Overview", "Follow-up"]

    def test_a_tracking_file_adds_by_unit(self, tmp_path):
        tracking = TrackingSource("tracking", TRACKING)

        titles = _page_sections(tmp_path, _settings(**TRACKING_SETTINGS), tracking)

        assert titles == ["Overview", "Follow-up", "By unit"]

    def test_a_master_list_adds_by_unit_and_respondents(self, tmp_path):
        tracking = TrackingSource("master", MASTER)

        titles = _page_sections(tmp_path, _settings(**MASTER_SETTINGS), tracking)

        assert titles == ["Overview", "Follow-up", "By unit", "Respondents"]

    def test_a_tracking_dataset_without_rows_stays_fixed(self, tmp_path):
        tracking = TrackingSource("tracking", None)

        titles = _page_sections(tmp_path, _settings(**TRACKING_SETTINGS), tracking)

        assert titles == ["Overview", "Follow-up"]


class TestHeader:
    def test_the_strip_names_the_mode_and_dataset(self):
        tracking = compute_progress(
            SURVEY, _settings(**TRACKING_SETTINGS), AS_OF, tracking=TRACKING
        )
        master = compute_progress(
            SURVEY, _settings(**MASTER_SETTINGS), AS_OF, tracking=MASTER
        )
        fixed = compute_progress(SURVEY, _settings(survey_target=10), AS_OF)

        assert describe_target(tracking, "villages") == (
            "tracking file **villages**, 12 across 3 units"
        )
        assert describe_target(master, "roster") == (
            "master list **roster**, 4 respondents"
        )
        assert describe_target(fixed, None) == "fixed number, 10"

    def test_the_pill_appears_only_with_to_dos(self):
        busy = compute_progress(
            SURVEY, _settings(**TRACKING_SETTINGS), AS_OF, tracking=TRACKING
        )
        quiet = compute_progress(SURVEY, _settings(survey_target=10), AS_OF)

        assert attention_text(busy) == (
            "[:orange-badge[:material/warning: 2 things need attention]](#overview)"
        )
        assert attention_text(quiet) is None


def _unit(name, target, completed, status) -> UnitRow:
    return UnitRow(
        unit=name,
        target=target,
        submissions=completed,
        unique=completed,
        completed=completed,
        percentage=None if target is None else completed / target * 100,
        remaining=None if target is None else max(target - completed, 0),
        status=status,
    )


UNITS = [
    _unit("a", 10, 6, "on track"),
    _unit("b", 10, 1, "behind"),
    _unit("c", 2, 3, "over target"),
    _unit("Untracked", None, 4, "untracked"),
]


class TestByUnitHelpers:
    @pytest.mark.parametrize(
        ("choice", "units"),
        [
            ("All", ["a", "b", "c", "Untracked"]),
            ("Behind", ["b"]),
            ("Over target", ["c"]),
            ("Untracked", ["Untracked"]),
        ],
    )
    def test_filters(self, choice, units):
        assert [r.unit for r in ui.filter_units(UNITS, choice)] == units

    def test_furthest_behind_puts_the_lowest_first_and_skips_untracked(self):
        assert [r.unit for r in ui.furthest_behind(UNITS)] == ["b", "a", "c"]

    def test_the_table_tags_units_over_target(self):
        table = ui.unit_frame(UNITS, "village")

        assert table.columns[0] == "village"
        assert table["Status"].to_list() == ["", "Behind", "Over target", "Untracked"]
        assert table["% complete"].to_list()[:3] == [60.0, 10.0, 150.0]


class TestRespondentHelpers:
    def respondents(self):
        return compute_progress(
            SURVEY,
            _settings(**MASTER_SETTINGS, tracking_display=["landmark"]),
            AS_OF,
            tracking=MASTER,
        ).respondents

    def test_visit_lists_hold_pending_and_attempted_furthest_behind_first(self):
        units = [_unit("v1", 2, 1, "on track"), _unit("v2", 2, 0, "behind")]

        lists = ui.visit_lists(self.respondents(), units)

        assert [(u.unit, [r.id for r in people]) for u, people in lists] == [
            ("v2", ["h5"]),
            ("v1", ["h2"]),
        ]

    def test_the_respondent_table_carries_the_extra_columns(self):
        table = ui.respondent_frame(self.respondents(), ["landmark"], "vill")

        assert table.columns == [
            "ID",
            "vill",
            "Status",
            "Attempts",
            "Last submission",
            "landmark",
        ]
        assert table.filter(pl.col("ID") == "h5")["landmark"].item() == "by school"


class TestTargetSourceSettings:
    """The Target source pickers can be cleared after a choice."""

    def render(self, saved: ProgressSettings, picks: dict[str, str | None]):
        mock_st = _mock_st()
        mock_st.selectbox.side_effect = lambda label, **kwargs: picks.get(label)
        mock_st.multiselect.return_value = []
        with (
            patch.object(progress_module, "st", mock_st),
            patch.object(progress_module, "section_header"),
            patch.object(progress_module, "save_check_settings") as save,
        ):
            chosen = progress_module._tracking_settings_section(
                "settings.json",
                saved,
                TrackingSource("master", MASTER),
                ["village"],
            )
        options = {
            c.args[0]: c.kwargs["options"] for c in mock_st.selectbox.call_args_list
        }
        return chosen, options, save

    @pytest.mark.parametrize(
        "label", ["Target column", "Unit column (tracking dataset)"]
    )
    def test_optional_pickers_offer_an_empty_choice(self, label):
        _, options, _ = self.render(_settings(), {})
        assert options[label][0] is None

    def test_the_survey_unit_picker_offers_an_empty_choice(self):
        _, options, _ = self.render(_settings(), {"Target column": "vill"})
        assert options["Unit column (survey)"][0] is None

    def test_clearing_the_unit_column_saves_no_unit(self):
        saved = _settings(**MASTER_SETTINGS)
        picks = {"ID column (master list)": "resp_id"}

        chosen, _, save = self.render(saved, picks)

        assert chosen.tracking_unit is None
        save.assert_any_call(
            "settings.json", progress_module.TAB_NAME, {"tracking_unit": None}
        )


class TestSectionsRender:
    """The sections draw without error from real results."""

    def test_by_unit_and_respondents_draw(self):
        result = compute_progress(
            SURVEY, _settings(**MASTER_SETTINGS), AS_OF, tracking=MASTER
        )
        mock_st = _mock_st()
        view = MagicMock()
        view.bind.return_value = {}
        with (
            patch.object(ui, "st", mock_st),
            patch.object(ui, "metric_row") as metrics,
            patch.object(ui, "section_header"),
        ):
            ui.display_by_unit(result.unit_levels, view)
            ui.display_respondents(result.respondents, result.unit_levels, [])

        mock_st.plotly_chart.assert_called_once()
        # By unit, visit list, unexpected IDs, completed
        assert mock_st.download_button.call_count == 4
        values = [metric[1] for metric in metrics.call_args.args[0]]
        assert values == ["2", "1", "1", "1"]

    def test_issues_are_shown_with_their_values(self):
        result = compute_progress(
            SURVEY,
            _settings(**MASTER_SETTINGS),
            AS_OF,
            tracking=pl.DataFrame({"resp_id": ["h1", "h1"], "vill": ["v1", "v1"]}),
        )
        mock_st = _mock_st()
        with patch.object(ui, "st", mock_st):
            ui.display_issues(result.issues)

        assert "`h1`" in mock_st.error.call_args.args[0]
