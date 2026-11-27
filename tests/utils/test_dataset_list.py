"""Tests for the import page's dataset list view model."""

from datetime import datetime

import polars as pl

from datasure.utils.dataset_list import LoadInfo, build_dataset_list, filter_rows

_LOG_COLUMNS = {
    "refresh": True,
    "load": True,
    "alias": "survey",
    "filename": "",
    "sheet_name": "",
    "source": "SurveyCTO",
    "server": "ipa-training",
    "username": "me@example.org",
    "form_id": "hh_main",
    "private_key": "",
    "save_to": "",
    "attachments": False,
}


def _log(*rows: dict) -> pl.DataFrame:
    return pl.DataFrame([{**_LOG_COLUMNS, **row} for row in rows])


def test_surveycto_row_shows_form_server_rows_and_last_load():
    log = _log({"alias": "household", "attachments": True, "refresh": False})
    info = {"household": LoadInfo(datetime(2026, 11, 16, 8, 42), 1284)}

    (row,) = build_dataset_list(log, info).rows

    assert row.alias == "household"
    assert row.source_label == "SurveyCTO"
    assert row.source_detail == "Form hh_main · ipa-training"
    assert row.row_count == 1284
    assert row.last_loaded_label == "Last loaded 16 Nov 2026 08:42"
    assert (row.refresh, row.load, row.media) == (False, True, True)
    assert row.media_disabled_reason is None


def test_local_row_shows_path_and_sheet_and_disables_media():
    log = _log(
        {
            "alias": "roster",
            "source": "local storage",
            "filename": "D:/data/roster.xlsx",
            "sheet_name": "roster",
            "server": "",
            "form_id": "",
        }
    )

    (row,) = build_dataset_list(log, {}).rows

    assert row.source_label == "Local file"
    assert row.source_detail == 'D:/data/roster.xlsx · sheet "roster"'
    assert row.media is False
    assert row.media_disabled_reason == (
        "Local files have no media attachments to download."
    )
    assert row.row_count is None
    assert row.last_loaded_label == "Not loaded yet"


def test_local_csv_has_no_sheet_in_its_detail():
    log = _log({"source": "local storage", "filename": "C:/survey.csv"})

    assert build_dataset_list(log, {}).rows[0].source_detail == "C:/survey.csv"


def test_demo_rows_with_null_fields_are_local_and_media_disabled():
    log = pl.DataFrame(
        [
            {
                **_LOG_COLUMNS,
                "alias": "demo_survey",
                "source": "Demo Data",
                "filename": "demo_survey.csv",
                "sheet_name": None,
                "server": None,
                "form_id": None,
            }
        ]
    )

    (row,) = build_dataset_list(log, {}).rows

    assert row.source_label == "Demo data"
    assert row.source_detail == "demo_survey.csv"
    assert row.media_disabled_reason is not None


def test_imported_before_load_times_were_kept_shows_rows_without_a_time():
    info = {"survey": LoadInfo(None, 12)}

    (row,) = build_dataset_list(_log({}), info).rows

    assert row.row_count == 12
    assert row.last_loaded_label == "Last load time not recorded"


def test_load_summary_counts_load_and_refresh_among_loaded():
    log = _log(
        {"alias": "a", "load": True, "refresh": True},
        {"alias": "b", "load": True, "refresh": True},
        {"alias": "c", "load": True, "refresh": False},
        # Refresh without Load does nothing, as Load data skips the row.
        {"alias": "d", "load": False, "refresh": True},
    )

    assert build_dataset_list(log, {}).load_summary == (
        "Loads 3 datasets · refreshes 2 from source"
    )


def test_load_summary_singular_and_none():
    one = _log({"load": True, "refresh": False})
    nothing = _log({"load": False})

    assert build_dataset_list(one, {}).load_summary == (
        "Loads 1 dataset · refreshes none"
    )
    assert build_dataset_list(nothing, {}).load_summary == (
        "No datasets are marked Load"
    )


def test_source_filter_appears_only_above_eight_datasets():
    eight = _log(*({"alias": f"d{i}"} for i in range(8)))
    nine = _log(*({"alias": f"d{i}"} for i in range(9)))

    assert build_dataset_list(eight, {}).show_source_filter is False
    assert build_dataset_list(nine, {}).show_source_filter is True


def test_empty_import_log_is_an_empty_project():
    result = build_dataset_list(pl.DataFrame(), {})

    assert result.is_empty is True
    assert result.rows == []
    assert result.show_source_filter is False


def test_project_with_datasets_is_not_empty():
    assert build_dataset_list(_log({}), {}).is_empty is False


def test_filter_rows_by_source():
    log = _log(
        {"alias": "scto"},
        {"alias": "file", "source": "local storage", "filename": "x.csv"},
        {"alias": "demo", "source": "Demo Data", "filename": "demo.csv"},
    )
    rows = build_dataset_list(log, {}).rows

    assert [r.alias for r in filter_rows(rows, "All")] == ["scto", "file", "demo"]
    assert [r.alias for r in filter_rows(rows, "SurveyCTO")] == ["scto"]
    assert [r.alias for r in filter_rows(rows, "Local")] == ["file", "demo"]
    assert [r.alias for r in filter_rows(rows, None)] == ["scto", "file", "demo"]
