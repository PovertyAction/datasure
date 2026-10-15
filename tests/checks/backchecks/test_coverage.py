"""Tests for backcheck target resolution and coverage against the target."""

import json

import polars as pl
import pytest

from datasure.checks.backchecks.compute import load_default_backchecks_settings
from datasure.checks.backchecks.coverage import (
    compute_backcheck_coverage,
    compute_staff_coverage,
    effective_target_percent,
    settings_from_page_config,
)
from datasure.checks.backchecks.models import BackcheckSettings


def _settings_file(tmp_path, saved: dict) -> str:
    file_path = tmp_path / "settings.json"
    file_path.write_text(json.dumps({"backchecks": saved}))
    return str(file_path)


# ============================================
# TARGET RESOLUTION: panel, then page config, then default
# ============================================


def test_cleared_panel_target_falls_back_to_page_config(tmp_path):
    """A cleared panel value does not hide the page config target."""
    settings_file = _settings_file(tmp_path, {"backcheck_target_percent": None})
    page_config = BackcheckSettings(survey_key="key", backcheck_target_percent=15)

    result = load_default_backchecks_settings(settings_file, page_config)

    assert result.backcheck_target_percent == 15


def test_saved_panel_target_wins_over_page_config(tmp_path):
    """A target saved in the panel overrides the page config target."""
    settings_file = _settings_file(tmp_path, {"backcheck_target_percent": 25})
    page_config = BackcheckSettings(survey_key="key", backcheck_target_percent=15)

    result = load_default_backchecks_settings(settings_file, page_config)

    assert result.backcheck_target_percent == 25


def test_saved_target_outside_percent_range_is_ignored(tmp_path):
    """A saved value from the old count-based input does not break loading."""
    settings_file = _settings_file(tmp_path, {"backcheck_target_percent": 250})
    page_config = BackcheckSettings(survey_key="key", backcheck_target_percent=15)

    result = load_default_backchecks_settings(settings_file, page_config)

    assert result.backcheck_target_percent == 15


def test_page_config_without_targets_builds_settings():
    """A page config with no targets builds settings with targets unset."""
    settings = settings_from_page_config(
        {
            "survey_key": "key",
            "backcheck_target_percent": None,
            "survey_target": None,
        }
    )

    assert settings.backcheck_target_percent is None
    assert settings.survey_target is None


def test_page_config_zero_targets_mean_not_set():
    """The page config stores 0 when a target is left blank."""
    settings = settings_from_page_config(
        {"survey_key": "key", "backcheck_target_percent": 0.0, "survey_target": 0}
    )

    assert settings.backcheck_target_percent is None
    assert settings.survey_target is None


def test_page_config_targets_are_kept():
    """Page config targets carry through to the settings."""
    settings = settings_from_page_config(
        {"survey_key": "key", "backcheck_target_percent": 12.0, "survey_target": 500}
    )

    assert settings.backcheck_target_percent == 12
    assert settings.survey_target == 500


def test_effective_target_defaults_to_ten_percent():
    """With no target set anywhere, 10% is used."""
    settings = BackcheckSettings(survey_key="key")

    assert effective_target_percent(settings) == 10


def test_effective_target_uses_set_target():
    """A set target, including 0, is used as is."""
    assert (
        effective_target_percent(
            BackcheckSettings(survey_key="key", backcheck_target_percent=0)
        )
        == 0
    )


# ============================================
# OVERALL COVERAGE
# ============================================


def _coverage_settings(**overrides) -> BackcheckSettings:
    return BackcheckSettings(
        survey_key="KEY",
        survey_id="hhid",
        enumerator="enum",
        backchecker="bcer",
        **overrides,
    )


def test_on_track_leaves_out_duplicated_survey_ids():
    """Duplicated survey IDs are left out of the base before counting."""
    survey = pl.DataFrame(
        {
            "KEY": ["k1", "k2", "k3", "k4", "k5"],
            "hhid": ["H1", "H1", "H2", "H3", "H4"],
            "enum": ["E1", "E1", "E1", "E2", "E2"],
        }
    )
    backcheck = pl.DataFrame({"KEY": ["b1", "b2"], "hhid": ["H1", "H2"]})

    coverage = compute_backcheck_coverage(survey, backcheck, _coverage_settings())

    # H1 is duplicated and dropped: base H2-H4, of which H2 is backchecked.
    assert coverage.eligible == 3
    assert coverage.backchecked == 1
    assert coverage.on_track_percent == pytest.approx(100 / 3)


def test_eligibility_filter_restricts_the_base():
    """Only surveys whose eligibility column is in the chosen values count."""
    survey = pl.DataFrame(
        {
            "KEY": ["k1", "k2", "k3", "k4"],
            "hhid": ["H1", "H2", "H3", "H4"],
            "consent": [1, 0, 1, 1],
        }
    )
    backcheck = pl.DataFrame({"KEY": ["b1", "b2"], "hhid": ["H1", "H2"]})
    settings = _coverage_settings(
        eligibility_column="consent", eligibility_values=["1"]
    )

    coverage = compute_backcheck_coverage(survey, backcheck, settings)

    # H2 did not consent, so its backcheck does not count either.
    assert coverage.eligible == 3
    assert coverage.backchecked == 1


def _surveys_with_backchecks(n_surveys: int, n_backchecked: int):
    ids = [f"H{i}" for i in range(n_surveys)]
    survey = pl.DataFrame({"KEY": [f"k{i}" for i in ids], "hhid": ids})
    backcheck = pl.DataFrame(
        {"KEY": [f"b{i}" for i in ids[:n_backchecked]], "hhid": ids[:n_backchecked]}
    )
    return survey, backcheck


def test_points_vs_target_is_negative_when_behind():
    """1 of 20 backchecked is 5%, 5 points behind a 10% target."""
    survey, backcheck = _surveys_with_backchecks(20, 1)

    coverage = compute_backcheck_coverage(
        survey, backcheck, _coverage_settings(backcheck_target_percent=10)
    )

    assert coverage.on_track_percent == pytest.approx(5)
    assert coverage.points_vs_target == pytest.approx(-5)


def test_expected_backchecks_rounds_up():
    """10% of a 95-response target is 9.5, so 10 backchecks are expected."""
    survey, backcheck = _surveys_with_backchecks(20, 4)

    coverage = compute_backcheck_coverage(
        survey,
        backcheck,
        _coverage_settings(backcheck_target_percent=10, survey_target=95),
    )

    assert coverage.expected_backchecks == 10
    assert coverage.expected_progress_percent == pytest.approx(40)


def test_expected_progress_can_exceed_100_percent():
    """Backchecks past the expected total show the real percentage."""
    survey, backcheck = _surveys_with_backchecks(20, 3)

    coverage = compute_backcheck_coverage(
        survey,
        backcheck,
        _coverage_settings(backcheck_target_percent=10, survey_target=20),
    )

    assert coverage.expected_backchecks == 2
    assert coverage.expected_progress_percent == pytest.approx(150)


def test_expected_backchecks_unset_without_survey_target():
    """Without a survey target there is no expected total."""
    survey, backcheck = _surveys_with_backchecks(20, 3)

    coverage = compute_backcheck_coverage(survey, backcheck, _coverage_settings())

    assert coverage.expected_backchecks is None
    assert coverage.expected_progress_percent is None


def test_coverage_unavailable_without_survey_id_in_backcheck_data():
    """Coverage needs the survey ID in both datasets."""
    survey, _ = _surveys_with_backchecks(5, 0)
    backcheck = pl.DataFrame({"KEY": ["b1"]})

    assert compute_backcheck_coverage(survey, backcheck, _coverage_settings()) is None


# ============================================
# PER-STAFF COVERAGE
# ============================================


def _staff_data():
    survey = pl.DataFrame(
        {
            "KEY": ["k1", "k2", "k3", "k4"],
            "hhid": ["H1", "H2", "H3", "H4"],
            "enum": ["E1", "E1", "E1", "E2"],
        }
    )
    backcheck = pl.DataFrame(
        {
            "KEY": ["b1", "b2", "b3"],
            "hhid": ["H1", "H2", "H9"],
            "bcer": ["B1", "B2", "B2"],
        }
    )
    return survey, backcheck


def test_enumerator_coverage_includes_enumerators_without_backchecks():
    """Each enumerator's eligible surveys and how many were backchecked."""
    survey, backcheck = _staff_data()

    result = compute_staff_coverage(
        survey, backcheck, _coverage_settings(backcheck_target_percent=10), "enumerator"
    ).sort("enum")

    assert result.to_dicts() == [
        {
            "enum": "E1",
            "Surveys": 3,
            "Backchecks": 2,
            "Coverage %": pytest.approx(200 / 3),
            "vs target": pytest.approx(200 / 3 - 10),
        },
        {
            "enum": "E2",
            "Surveys": 1,
            "Backchecks": 0,
            "Coverage %": 0.0,
            "vs target": -10.0,
        },
    ]


def test_backchecker_view_counts_matched_backchecks_only():
    """Backcheckers get unique backchecked survey IDs and no coverage columns."""
    survey, backcheck = _staff_data()

    result = compute_staff_coverage(
        survey, backcheck, _coverage_settings(), "backchecker"
    ).sort("bcer")

    # B2's backcheck of H9 matches no survey, so it does not count.
    assert result.to_dicts() == [
        {"bcer": "B1", "Backchecks": 1},
        {"bcer": "B2", "Backchecks": 1},
    ]


def test_staff_coverage_empty_without_staff_column():
    """No table when the enumerator column is missing from the survey data."""
    survey, backcheck = _staff_data()

    result = compute_staff_coverage(
        survey.drop("enum"), backcheck, _coverage_settings(), "enumerator"
    )

    assert result.is_empty()
