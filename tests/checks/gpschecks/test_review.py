"""Tests for correcting and accepting GPS outliers (gpschecks.review)."""

import json

import pandas as pd
import polars as pl
import pytest

from datasure.checks.gpschecks.review import (
    ACCEPTED_STATUS,
    GPS_CHECK_TYPE,
    CoordinateColumns,
    GPSAction,
    GPSSelection,
    accepted_gps_keys,
    allowed_gps_actions,
    build_gps_entries,
    coordinate_columns,
    count_unreviewed_outliers,
    mark_gps_reviewed,
    outlier_status,
    outliers_table,
    select_gps_outlier,
    validate_coordinates,
)
from datasure.checks.outliers.review import (
    REVIEW_REASON_COL,
    REVIEW_STATUS_COL,
    REVIEWED_BADGE,
)
from datasure.models.enums import GPSFormatType
from datasure.processing.correction_log import Action
from datasure.processing.corrections import CorrectionEntry, CorrectionProcessor

COLUMNS = CoordinateColumns(latitude="gps_lat", longitude="gps_lon")


# =============================================================================
# coordinate_columns
# =============================================================================


def test_coordinate_columns_separate_format():
    config = {
        "format_type": GPSFormatType.SEPARATE_COLUMNS.value,
        "latitude_column": "gps_lat",
        "longitude_column": "gps_lon",
        "accuracy_column": "gps_acc",
    }
    assert coordinate_columns(config) == COLUMNS


def test_coordinate_columns_single_column_format_is_none():
    config = {
        "format_type": GPSFormatType.SINGLE_COLUMN.value,
        "gps_column": "gps",
        "latitude_column": None,
        "longitude_column": None,
    }
    assert coordinate_columns(config) is None


# =============================================================================
# allowed_gps_actions
# =============================================================================


def test_allowed_actions_for_an_unreviewed_outlier():
    assert allowed_gps_actions(COLUMNS, reviewed=False) == [
        GPSAction.MODIFY_COORDINATES,
        GPSAction.REMOVE_COORDINATES,
        GPSAction.REMOVE_OBSERVATION,
        GPSAction.ACCEPT,
    ]


def test_allowed_actions_for_an_accepted_outlier_omit_accept():
    assert GPSAction.ACCEPT not in allowed_gps_actions(COLUMNS, reviewed=True)


def test_allowed_actions_without_coordinate_columns_only_remove_observation():
    assert allowed_gps_actions(None, reviewed=False) == [GPSAction.REMOVE_OBSERVATION]


# =============================================================================
# validate_coordinates
# =============================================================================


@pytest.mark.parametrize(
    ("latitude", "longitude"),
    [("6.6", "-0.18"), ("-90", "180"), ("0", "0")],
)
def test_validate_coordinates_accepts_valid_pairs(latitude, longitude):
    assert validate_coordinates(latitude, longitude) is None


@pytest.mark.parametrize(
    ("latitude", "longitude", "message"),
    [
        ("north", "1", "Latitude must be a number"),
        ("1", "", "Longitude must be a number"),
        ("90.5", "1", "Latitude must be between -90 and 90"),
        ("1", "-180.1", "Longitude must be between -180 and 180"),
        ("nan", "1", "Latitude must be a number"),
    ],
)
def test_validate_coordinates_rejects_invalid_pairs(latitude, longitude, message):
    assert validate_coordinates(latitude, longitude) == message


# =============================================================================
# build_gps_entries
# =============================================================================


CURRENT = {"gps_lat": 6.7, "gps_lon": -0.2}


def test_modify_coordinates_builds_two_entries_with_one_reason():
    entries = build_gps_entries(
        GPSAction.MODIFY_COORDINATES,
        "K1",
        "Re-read from device",
        columns=COLUMNS,
        current=CURRENT,
        new_latitude="6.6",
        new_longitude="-0.19",
        survey_id_value="H1",
    )
    assert entries == [
        CorrectionEntry(
            key_value="K1",
            action=Action.MODIFY_VALUE,
            reason="Re-read from device",
            column="gps_lat",
            current_value=6.7,
            new_value="6.6",
            survey_id_value="H1",
        ),
        CorrectionEntry(
            key_value="K1",
            action=Action.MODIFY_VALUE,
            reason="Re-read from device",
            column="gps_lon",
            current_value=-0.2,
            new_value="-0.19",
            survey_id_value="H1",
        ),
    ]


def test_remove_coordinates_clears_only_latitude_and_longitude():
    entries = build_gps_entries(
        GPSAction.REMOVE_COORDINATES, "K1", "Bad fix", columns=COLUMNS, current=CURRENT
    )
    assert [(e.action, e.column, e.current_value) for e in entries] == [
        (Action.REMOVE_VALUE, "gps_lat", 6.7),
        (Action.REMOVE_VALUE, "gps_lon", -0.2),
    ]
    assert {e.reason for e in entries} == {"Bad fix"}


def test_remove_observation_builds_one_remove_row_entry():
    entries = build_gps_entries(
        GPSAction.REMOVE_OBSERVATION, "K1", "Test interview", columns=None, current={}
    )
    assert entries == [
        CorrectionEntry(
            key_value="K1", action=Action.REMOVE_ROW, reason="Test interview"
        )
    ]


def test_accept_builds_a_gps_acceptance_without_column():
    entries = build_gps_entries(
        GPSAction.ACCEPT, "K1", "Market trip", columns=COLUMNS, current=CURRENT
    )
    assert entries == [
        CorrectionEntry(
            key_value="K1",
            action=Action.ACCEPT,
            reason="Market trip",
            column=None,
            current_value=CURRENT,
            check_type=GPS_CHECK_TYPE,
        )
    ]


@pytest.mark.parametrize(
    "action",
    [GPSAction.MODIFY_COORDINATES, GPSAction.REMOVE_COORDINATES, GPSAction.ACCEPT],
)
def test_coordinate_actions_need_coordinate_columns(action):
    with pytest.raises(ValueError, match="latitude and longitude columns"):
        build_gps_entries(
            action,
            "K1",
            "why",
            columns=None,
            current={},
            new_latitude="1",
            new_longitude="1",
        )


# =============================================================================
# accepted_gps_keys and mark_gps_reviewed
# =============================================================================


def _gps_acceptances(*rows: tuple[str, dict, str]) -> pl.DataFrame:
    """Active GPS acceptances with (KEY, coordinate snapshot, reason) rows."""
    return pl.DataFrame(
        {
            "KEY": [r[0] for r in rows],
            "action": ["accept"] * len(rows),
            "column": [None] * len(rows),
            "current_value": [json.dumps(r[1]) for r in rows],
            "reason": [r[2] for r in rows],
            "check_type": ["gps"] * len(rows),
        },
        schema={
            "KEY": pl.String,
            "action": pl.String,
            "column": pl.String,
            "current_value": pl.String,
            "reason": pl.String,
            "check_type": pl.String,
        },
    )


def test_accepted_gps_keys_maps_keys_to_reasons():
    acceptances = _gps_acceptances(
        ("K1", {"gps_lat": "6.7", "gps_lon": "-0.2"}, "Market trip"),
    )
    assert accepted_gps_keys(acceptances, COLUMNS) == {"K1": "Market trip"}


def test_accepted_gps_keys_ignores_another_configurations_columns():
    acceptances = _gps_acceptances(
        ("K1", {"bc_lat": "6.7", "bc_lon": "-0.2"}, "Other config"),
    )
    assert accepted_gps_keys(acceptances, COLUMNS) == {}


def test_accepted_gps_keys_keeps_the_latest_reason():
    snapshot = {"gps_lat": "6.7", "gps_lon": "-0.2"}
    acceptances = _gps_acceptances(
        ("K1", snapshot, "first"), ("K1", snapshot, "second")
    )
    assert accepted_gps_keys(acceptances, COLUMNS) == {"K1": "second"}


def test_accepted_gps_keys_of_an_empty_log():
    assert accepted_gps_keys(pl.DataFrame(), COLUMNS) == {}


@pytest.fixture
def outliers() -> pd.DataFrame:
    """Detection output: one row per point, with the Outlier flag."""
    return pd.DataFrame(
        {
            "KEY": ["K3", "K1", "K2", 7],
            "latitude": [6.0, 6.7, 6.5, 6.1],
            "longitude": [-0.1, -0.2, -0.3, -0.1],
            "Outlier": [False, True, True, True],
        }
    )


def test_mark_gps_reviewed_marks_only_accepted_outliers(outliers):
    marked = mark_gps_reviewed(outliers, {"K1": "Market trip", "K3": "x"}, "KEY")
    assert marked[REVIEW_STATUS_COL].tolist() == [None, REVIEWED_BADGE, None, None]
    assert marked[REVIEW_REASON_COL].tolist() == [None, "Market trip", None, None]


def test_mark_gps_reviewed_compares_keys_as_text(outliers):
    marked = mark_gps_reviewed(outliers, {"7": "ok"}, "KEY")
    assert marked[REVIEW_STATUS_COL].tolist()[-1] == REVIEWED_BADGE


def test_mark_gps_reviewed_does_not_modify_its_input(outliers):
    mark_gps_reviewed(outliers, {"K1": "ok"}, "KEY")
    assert REVIEW_STATUS_COL not in outliers.columns


def test_count_unreviewed_outliers_leaves_out_accepted_ones(outliers):
    marked = mark_gps_reviewed(outliers, {"K1": "ok"}, "KEY")
    assert count_unreviewed_outliers(marked) == 2
    assert count_unreviewed_outliers(outliers) == 3


def test_outlier_status_labels_accepted_points(outliers):
    marked = mark_gps_reviewed(outliers, {"K1": "ok"}, "KEY")
    assert outlier_status(marked).tolist() == [
        "Normal",
        ACCEPTED_STATUS,
        "Outlier",
        "Outlier",
    ]


# =============================================================================
# outliers_table and select_gps_outlier
# =============================================================================


def test_outliers_table_hides_accepted_outliers_and_review_columns(outliers):
    marked = mark_gps_reviewed(outliers, {"K1": "ok"}, "KEY")
    table = outliers_table(marked, show_reviewed=False)
    assert table["KEY"].tolist() == ["K2", 7]
    assert REVIEW_STATUS_COL not in table.columns
    assert table.index.tolist() == [0, 1]


def test_outliers_table_shows_accepted_outliers_on_request(outliers):
    marked = mark_gps_reviewed(outliers, {"K1": "ok"}, "KEY")
    table = outliers_table(marked, show_reviewed=True)
    assert table["KEY"].tolist() == ["K1", "K2", 7]
    assert table[REVIEW_STATUS_COL].tolist() == [REVIEWED_BADGE, None, None]


def test_outliers_table_without_review_columns(outliers):
    table = outliers_table(outliers, show_reviewed=False)
    assert table["KEY"].tolist() == ["K1", "K2", 7]


def test_select_gps_outlier_returns_the_clicked_row(outliers):
    marked = mark_gps_reviewed(outliers, {"K1": "ok"}, "KEY")
    table = outliers_table(marked, show_reviewed=True)
    assert select_gps_outlier(table, [0], "KEY") == GPSSelection("K1", reviewed=True)
    assert select_gps_outlier(table, [1], "KEY") == GPSSelection("K2", reviewed=False)


def test_select_gps_outlier_returns_native_keys(outliers):
    table = outliers_table(outliers, show_reviewed=False)
    selection = select_gps_outlier(table, [2], "KEY")
    assert selection == GPSSelection(7, reviewed=False)
    assert type(selection.key_value) is int


@pytest.mark.parametrize("rows", [[], [9], [-1]])
def test_select_gps_outlier_without_a_valid_row(outliers, rows):
    table = outliers_table(outliers, show_reviewed=False)
    assert select_gps_outlier(table, rows, "KEY") is None


# =============================================================================
# Applying through the correction processor
# =============================================================================


@pytest.fixture
def processor(monkeypatch) -> CorrectionProcessor:
    """A processor whose corrected data and log live in memory."""
    store = {
        "data": pl.DataFrame(
            {
                "KEY": ["K1", "K2"],
                "gps_lat": [6.7, 6.5],
                "gps_lon": [-0.2, -0.3],
                "gps_acc": [4.0, 5.0],
            }
        ),
        "log": pl.DataFrame(),
    }
    proc = CorrectionProcessor("project")
    monkeypatch.setattr(proc, "get_corrected_data", lambda alias: store["data"])
    monkeypatch.setattr(
        proc, "save_corrected_data", lambda alias, data: store.update(data=data)
    )
    monkeypatch.setattr(proc, "get_correction_log", lambda alias: store["log"])

    def append(alias, rows):
        store["log"] = pl.concat(
            [store["log"], pl.DataFrame(rows)], how="diagonal_relaxed"
        )

    monkeypatch.setattr(proc, "_append_log_rows", append)
    proc.store = store
    return proc


def test_modify_coordinates_applies_both_columns(processor):
    entries = build_gps_entries(
        GPSAction.MODIFY_COORDINATES,
        "K1",
        "fix",
        columns=COLUMNS,
        current=CURRENT,
        new_latitude="6.6",
        new_longitude="-0.19",
    )
    processor.apply_corrections("survey", "KEY", entries, source="gps")

    row = processor.store["data"].row(0, named=True)
    assert (row["gps_lat"], row["gps_lon"], row["gps_acc"]) == (6.6, -0.19, 4.0)
    assert processor.store["log"]["column"].to_list() == ["gps_lat", "gps_lon"]
    assert processor.store["log"]["source"].unique().to_list() == ["gps"]


def test_a_failing_coordinate_entry_applies_and_logs_neither(processor):
    original = processor.store["data"]
    entries = build_gps_entries(
        GPSAction.MODIFY_COORDINATES,
        "K1",
        "fix",
        columns=CoordinateColumns(latitude="gps_lat", longitude="missing_lon"),
        current={"gps_lat": 6.7, "missing_lon": None},
        new_latitude="6.6",
        new_longitude="-0.19",
    )
    with pytest.raises(ValueError, match="missing_lon"):
        processor.apply_corrections("survey", "KEY", entries, source="gps")

    assert processor.store["data"].equals(original)
    assert processor.store["log"].is_empty()


def test_remove_coordinates_keeps_accuracy(processor):
    entries = build_gps_entries(
        GPSAction.REMOVE_COORDINATES, "K1", "bad", columns=COLUMNS, current=CURRENT
    )
    processor.apply_corrections("survey", "KEY", entries, source="gps")

    row = processor.store["data"].row(0, named=True)
    assert (row["gps_lat"], row["gps_lon"], row["gps_acc"]) == (None, None, 4.0)


def test_remove_observation_drops_the_row(processor):
    entries = build_gps_entries(
        GPSAction.REMOVE_OBSERVATION, "K1", "test", columns=COLUMNS, current=CURRENT
    )
    processor.apply_corrections("survey", "KEY", entries, source="gps")

    assert processor.store["data"]["KEY"].to_list() == ["K2"]


@pytest.mark.parametrize("changed", ["gps_lat", "gps_lon"])
def test_an_acceptance_lapses_when_either_coordinate_changes(processor, changed):
    accept = build_gps_entries(
        GPSAction.ACCEPT, "K1", "ok", columns=COLUMNS, current=CURRENT
    )
    processor.apply_corrections("survey", "KEY", accept, source="gps")
    active = processor.get_active_acceptances("survey", GPS_CHECK_TYPE, "KEY")
    assert accepted_gps_keys(active, COLUMNS) == {"K1": "ok"}

    processor.apply_corrections(
        "survey",
        "KEY",
        [
            CorrectionEntry(
                key_value="K1",
                action=Action.MODIFY_VALUE,
                reason="fix",
                column=changed,
                current_value=CURRENT[changed],
                new_value="1.5",
            )
        ],
        source="gps",
    )
    active = processor.get_active_acceptances("survey", GPS_CHECK_TYPE, "KEY")
    assert accepted_gps_keys(active, COLUMNS) == {}


def test_an_acceptance_survives_an_accuracy_change(processor):
    accept = build_gps_entries(
        GPSAction.ACCEPT, "K1", "ok", columns=COLUMNS, current=CURRENT
    )
    processor.apply_corrections("survey", "KEY", accept, source="gps")
    processor.apply_corrections(
        "survey",
        "KEY",
        [
            CorrectionEntry(
                key_value="K1",
                action=Action.REMOVE_VALUE,
                reason="drop accuracy",
                column="gps_acc",
                current_value=4.0,
            )
        ],
        source="gps",
    )
    active = processor.get_active_acceptances("survey", GPS_CHECK_TYPE, "KEY")
    assert accepted_gps_keys(active, COLUMNS) == {"K1": "ok"}
