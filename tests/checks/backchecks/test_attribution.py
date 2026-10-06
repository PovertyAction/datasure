"""Tests for datasure.checks.backchecks.attribution."""

from datetime import datetime
from unittest.mock import patch

import polars as pl
import pytest

from datasure.checks.backchecks.attribution import (
    ATTRIBUTION_LOG_SCHEMA,
    ERROR_SOURCE_COL,
    ErrorSource,
    adjusted_error_rate,
    attributed_share,
    attribution_history,
    attribution_table,
    build_attribution_entries,
    count_error_sources,
    excused_mismatches,
    load_attribution_log,
    mark_error_sources,
    note_required,
    rows_to_review,
    save_attributions,
)

SURVEY_KEY = "KEY"
BC_KEY = "KEY__BCCL"
NOW = datetime(2026, 10, 6, 12, 0)


def _analysis(**overrides) -> pl.DataFrame:
    """Comparison results: two mismatches, a match and a missing value."""
    data = {
        SURVEY_KEY: ["s1", "s2", "s3", "s4"],
        BC_KEY: ["b1", "b2", "b3", "b4"],
        "column_name": ["age", "age", "age", "age"],
        "survey_value": [30, 41, 25, None],
        "backcheck_value": [31, 40, 25, 50],
        "category": [1, 1, 1, 1],
        "match_status": ["mismatch", "mismatch", "match", "missing"],
    }
    data.update(overrides)
    return pl.DataFrame(data)


def _log(rows: list[dict]) -> pl.DataFrame:
    defaults = {"note": None, "user": "ana", "date": NOW}
    return pl.DataFrame(
        [{**defaults, **row} for row in rows], schema=ATTRIBUTION_LOG_SCHEMA
    )


def _entry(survey_key, backcheck_key, survey_value, backcheck_value, source, **kw):
    return {
        "survey_key": survey_key,
        "backcheck_key": backcheck_key,
        "column_name": kw.pop("column_name", "age"),
        "survey_value": survey_value,
        "backcheck_value": backcheck_value,
        "source": source,
        **kw,
    }


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------


def test_attribution_table_is_per_page():
    assert attribution_table("page_1") == "bc_attribution_page_1"


@pytest.mark.parametrize(
    ("source", "required"),
    [
        (ErrorSource.ENUMERATOR, False),
        (ErrorSource.BACKCHECKER, True),
        (ErrorSource.RESPONDENT, True),
        (ErrorSource.UNATTRIBUTED, False),
    ],
)
def test_note_required_for_backchecker_and_respondent(source, required):
    assert note_required(source) is required


# ---------------------------------------------------------------------------
# Selecting rows to attribute
# ---------------------------------------------------------------------------


def test_rows_to_review_clicked_mismatch_alone():
    rows = rows_to_review(_analysis(), clicked_row=1, selected_rows=[])
    assert rows[SURVEY_KEY].to_list() == ["s2"]


def test_rows_to_review_clicked_non_mismatch_is_empty():
    rows = rows_to_review(_analysis(), clicked_row=2, selected_rows=[2])
    assert rows.is_empty()


def test_rows_to_review_clicked_inside_selection_takes_selected_mismatches():
    rows = rows_to_review(_analysis(), clicked_row=0, selected_rows=[0, 1, 2, 3])
    assert rows[SURVEY_KEY].to_list() == ["s1", "s2"]


def test_rows_to_review_clicked_outside_selection_takes_clicked_row_only():
    rows = rows_to_review(_analysis(), clicked_row=1, selected_rows=[0])
    assert rows[SURVEY_KEY].to_list() == ["s2"]


def test_rows_to_review_ignores_stale_positions():
    assert rows_to_review(_analysis(), clicked_row=9, selected_rows=[]).is_empty()
    rows = rows_to_review(_analysis(), clicked_row=0, selected_rows=[0, 9])
    assert rows[SURVEY_KEY].to_list() == ["s1"]


# ---------------------------------------------------------------------------
# Building log entries
# ---------------------------------------------------------------------------


def test_build_attribution_entries_records_values_user_and_date():
    rows = _analysis().filter(pl.col("match_status") == "mismatch")
    entries = build_attribution_entries(
        rows, SURVEY_KEY, ErrorSource.ENUMERATOR, "", user="ana", date=NOW
    )
    assert entries.schema == pl.Schema(ATTRIBUTION_LOG_SCHEMA)
    assert entries.to_dicts() == [
        {
            "survey_key": "s1",
            "backcheck_key": "b1",
            "column_name": "age",
            "survey_value": "30",
            "backcheck_value": "31",
            "source": "Enumerator",
            "note": None,
            "user": "ana",
            "date": NOW,
        },
        {
            "survey_key": "s2",
            "backcheck_key": "b2",
            "column_name": "age",
            "survey_value": "41",
            "backcheck_value": "40",
            "source": "Enumerator",
            "note": None,
            "user": "ana",
            "date": NOW,
        },
    ]


@pytest.mark.parametrize("source", [ErrorSource.BACKCHECKER, ErrorSource.RESPONDENT])
@pytest.mark.parametrize("note", ["", "   ", None])
def test_build_attribution_entries_requires_note(source, note):
    rows = _analysis().head(1)
    with pytest.raises(ValueError, match="note"):
        build_attribution_entries(rows, SURVEY_KEY, source, note, user="a", date=NOW)


def test_build_attribution_entries_strips_note():
    rows = _analysis().head(1)
    entries = build_attribution_entries(
        rows, SURVEY_KEY, ErrorSource.RESPONDENT, "  changed answer ", "a", NOW
    )
    assert entries["note"].to_list() == ["changed answer"]


def test_build_attribution_entries_rejects_non_mismatch_rows():
    with pytest.raises(ValueError, match="mismatch"):
        build_attribution_entries(
            _analysis(), SURVEY_KEY, ErrorSource.ENUMERATOR, "", "a", NOW
        )


def test_build_attribution_entries_rejects_no_rows():
    with pytest.raises(ValueError, match="No"):
        build_attribution_entries(
            _analysis().clear(), SURVEY_KEY, ErrorSource.ENUMERATOR, "", "a", NOW
        )


def test_build_attribution_entries_shared_key_when_survey_key_is_merge_id():
    rows = _analysis().drop(BC_KEY).head(1)
    entries = build_attribution_entries(
        rows, SURVEY_KEY, ErrorSource.ENUMERATOR, None, "a", NOW
    )
    assert entries["backcheck_key"].to_list() == ["s1"]


# ---------------------------------------------------------------------------
# Marking error sources, latest entry and lapse
# ---------------------------------------------------------------------------


def test_mark_error_sources_without_log_marks_mismatches_unattributed():
    marked = mark_error_sources(_analysis(), _log([]), SURVEY_KEY)
    assert marked[ERROR_SOURCE_COL].to_list() == [
        "Unattributed",
        "Unattributed",
        None,
        None,
    ]
    assert marked.drop(ERROR_SOURCE_COL).equals(_analysis())


def test_mark_error_sources_latest_entry_wins():
    log = _log(
        [
            _entry("s1", "b1", "30", "31", "Respondent", note="moved"),
            _entry("s1", "b1", "30", "31", "Enumerator"),
        ]
    )
    marked = mark_error_sources(_analysis(), log, SURVEY_KEY)
    assert marked[ERROR_SOURCE_COL].to_list()[:2] == ["Enumerator", "Unattributed"]


def test_mark_error_sources_can_be_reset_to_unattributed():
    log = _log(
        [
            _entry("s1", "b1", "30", "31", "Backchecker", note="typo"),
            _entry("s1", "b1", "30", "31", "Unattributed"),
        ]
    )
    marked = mark_error_sources(_analysis(), log, SURVEY_KEY)
    assert marked[ERROR_SOURCE_COL][0] == "Unattributed"


@pytest.mark.parametrize(
    ("survey_value", "backcheck_value"), [("29", "31"), ("30", "32")]
)
def test_mark_error_sources_attribution_lapses_when_a_value_changes(
    survey_value, backcheck_value
):
    log = _log([_entry("s1", "b1", survey_value, backcheck_value, "Backchecker")])
    marked = mark_error_sources(_analysis(), log, SURVEY_KEY)
    assert marked[ERROR_SOURCE_COL][0] == "Unattributed"


def test_mark_error_sources_ignores_attribution_once_pair_matches():
    log = _log([_entry("s3", "b3", "25", "25", "Enumerator")])
    marked = mark_error_sources(_analysis(), log, SURVEY_KEY)
    assert marked[ERROR_SOURCE_COL][2] is None


def test_mark_error_sources_matches_column_and_backcheck_key():
    log = _log(
        [
            _entry("s1", "b1", "30", "31", "Enumerator", column_name="income"),
            _entry("s2", "bX", "41", "40", "Enumerator"),
        ]
    )
    marked = mark_error_sources(_analysis(), log, SURVEY_KEY)
    assert marked[ERROR_SOURCE_COL].to_list()[:2] == ["Unattributed", "Unattributed"]


def test_mark_error_sources_when_survey_key_is_merge_id():
    analysis = _analysis().drop(BC_KEY)
    log = _log([_entry("s1", "s1", "30", "31", "Enumerator")])
    marked = mark_error_sources(analysis, log, SURVEY_KEY)
    assert marked[ERROR_SOURCE_COL][0] == "Enumerator"


def test_mark_error_sources_empty_analysis():
    assert mark_error_sources(pl.DataFrame(), _log([]), SURVEY_KEY).is_empty()


# ---------------------------------------------------------------------------
# Counts and rates
# ---------------------------------------------------------------------------


def _marked(sources: list[str | None], statuses: list[str]) -> pl.DataFrame:
    return pl.DataFrame({"match_status": statuses, ERROR_SOURCE_COL: sources})


def test_count_error_sources():
    rows = _marked(
        ["Enumerator", "Backchecker", "Backchecker", "Unattributed", None],
        ["mismatch", "mismatch", "mismatch", "mismatch", "match"],
    )
    assert count_error_sources(rows) == {
        ErrorSource.ENUMERATOR: 1,
        ErrorSource.BACKCHECKER: 2,
        ErrorSource.RESPONDENT: 0,
        ErrorSource.UNATTRIBUTED: 1,
    }


def test_count_error_sources_without_source_column_counts_unattributed():
    rows = pl.DataFrame({"match_status": ["mismatch", "match", "mismatch"]})
    assert count_error_sources(rows)[ErrorSource.UNATTRIBUTED] == 2


# Ten values compared: 6 mismatches, of which 1 Enumerator, 2 Backchecker,
# 1 Respondent and 2 Unattributed.
_RATE_ROWS = _marked(
    ["Enumerator", "Backchecker", "Backchecker", "Respondent"]
    + ["Unattributed"] * 2
    + [None] * 4,
    ["mismatch"] * 6 + ["match"] * 4,
)


def test_excused_mismatches_per_staff_type():
    assert excused_mismatches(_RATE_ROWS, "enumerator") == 3
    assert excused_mismatches(_RATE_ROWS, "backchecker") == 2


def test_adjusted_error_rate_for_enumerators():
    # (6 mismatches - 2 Backchecker - 1 Respondent) / 10 compared
    assert adjusted_error_rate(6, 10, _RATE_ROWS, "enumerator") == 30.0


def test_adjusted_error_rate_for_backcheckers():
    # (6 mismatches - 1 Enumerator - 1 Respondent) / 10 compared
    assert adjusted_error_rate(6, 10, _RATE_ROWS, "backchecker") == 40.0


def test_adjusted_error_rate_counts_unattributed_and_handles_no_values():
    rows = _marked(["Unattributed"], ["mismatch"])
    assert adjusted_error_rate(1, 4, rows, "enumerator") == 25.0
    assert adjusted_error_rate(0, 0, rows.clear(), "enumerator") == 0.0


def test_adjusted_error_rate_rejects_unknown_staff_type():
    with pytest.raises(ValueError, match="staff type"):
        adjusted_error_rate(1, 1, _RATE_ROWS, "respondent")


def test_attributed_share():
    rows = _marked(
        ["Enumerator", "Respondent", "Unattributed", "Unattributed", None],
        ["mismatch"] * 4 + ["match"],
    )
    assert attributed_share(rows) == 50.0


def test_attributed_share_none_without_mismatches():
    assert attributed_share(_marked([None], ["match"])) is None
    assert attributed_share(pl.DataFrame()) is None


# ---------------------------------------------------------------------------
# Storage
# ---------------------------------------------------------------------------


def test_save_attributions_appends_to_existing_log():
    existing = _log([_entry("s1", "b1", "30", "31", "Enumerator")])
    new = _log([_entry("s1", "b1", "30", "31", "Respondent", note="moved")])
    with (
        patch(
            "datasure.checks.backchecks.attribution.duckdb_get_table",
            return_value=existing,
        ) as get_table,
        patch("datasure.checks.backchecks.attribution.duckdb_save_table") as save,
    ):
        save_attributions("proj", "page", new)

    get_table.assert_called_once_with("proj", "bc_attribution_page", "logs")
    saved = save.call_args.args[1]
    assert save.call_args.args[0] == "proj"
    assert save.call_args.args[2:] == ("bc_attribution_page", "logs")
    assert saved["source"].to_list() == ["Enumerator", "Respondent"]


def test_load_attribution_log_empty_table_has_schema():
    with patch(
        "datasure.checks.backchecks.attribution.duckdb_get_table",
        return_value=pl.DataFrame(),
    ):
        log = load_attribution_log("proj", "page")
    assert log.is_empty()
    assert log.schema == pl.Schema(ATTRIBUTION_LOG_SCHEMA)


def test_attribution_history_lists_newest_first():
    log = _log(
        [
            _entry("s1", "b1", "30", "31", "Enumerator", date=datetime(2026, 1, 1)),
            _entry("s2", "b2", "41", "40", "Respondent", date=datetime(2026, 2, 1)),
        ]
    )
    assert attribution_history(log)["survey_key"].to_list() == ["s2", "s1"]
