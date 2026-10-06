"""Tests for mismatch attribution on the Backchecks page (report_ui)."""

from datetime import datetime
from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks.backchecks.attribution import (
    ATTRIBUTION_LOG_SCHEMA,
    ERROR_SOURCE_COL,
    ErrorSource,
)
from datasure.checks.backchecks.models import BackcheckSettings
from datasure.checks.backchecks.report_ui import (
    AttributionContext,
    _build_display_columns,
    _error_rate_columns,
    _highlight_above_target,
    _render_attribution_form,
    _render_attribution_log,
    _render_backcheck_summary,
    _render_comparison_table,
)
from tests.checks.backchecks.conftest import make_mock_st

MODULE = "datasure.checks.backchecks.report_ui"


@pytest.fixture
def mock_st():
    st = make_mock_st()
    st.session_state = {}
    st.text_area.return_value = ""
    with patch(f"{MODULE}.st", st):
        yield st


@pytest.fixture
def review():
    return AttributionContext(
        "proj", "page", pl.DataFrame(schema=ATTRIBUTION_LOG_SCHEMA)
    )


def _table() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "KEY": ["s1", "s2", "s3"],
            "KEY__BCCL": ["b1", "b2", "b3"],
            "column_name": ["age", "age", "age"],
            "survey_value": [30, 41, 25],
            "backcheck_value": [31, 40, 25],
            "match_status": ["mismatch", "mismatch", "match"],
            "category": [1, 1, 1],
            ERROR_SOURCE_COL: ["Unattributed", "Unattributed", None],
        }
    )


# ---------------------------------------------------------------------------
# Comparison table
# ---------------------------------------------------------------------------


def test_display_columns_show_error_source_after_match_status():
    columns = _build_display_columns(_table(), "KEY", None, "KEY__BCCL")
    assert columns.index(ERROR_SOURCE_COL) == columns.index("match_status") + 1


def test_comparison_table_review_buttons_only_on_mismatches(mock_st, review):
    _render_comparison_table(_table(), {}, "KEY", review)

    shown = mock_st.dataframe.call_args.args[0]
    labels = shown.to_series(0).to_list()
    assert labels[2] is None
    assert labels[0] == labels[1] is not None
    assert mock_st.dataframe.call_args.kwargs["selection_mode"] == "multi-row"


def test_comparison_table_pins_review_then_error_source(mock_st, review):
    _render_comparison_table(_table(), {}, "KEY", review)

    shown = mock_st.dataframe.call_args.args[0]
    button_col = shown.columns[0]
    assert shown.columns[1] == ERROR_SOURCE_COL
    config = mock_st.dataframe.call_args.kwargs["column_config"]
    assert mock_st.column_config.ButtonColumn.call_args.kwargs["pinned"] is True
    assert isinstance(mock_st.column_config.ButtonColumn.call_args.kwargs["width"], int)
    assert config[button_col] is mock_st.column_config.ButtonColumn.return_value
    error_source_config = next(
        c
        for c in mock_st.column_config.TextColumn.call_args_list
        if c.args and c.args[0] == "Error Source"
    )
    assert error_source_config.kwargs["pinned"] is True
    assert config[ERROR_SOURCE_COL] is mock_st.column_config.TextColumn.return_value


def test_comparison_table_without_click_opens_no_dialog(mock_st, review):
    with patch(f"{MODULE}._attribution_dialog") as dialog:
        _render_comparison_table(_table(), {}, "KEY", review)
    dialog.assert_not_called()


def test_comparison_table_click_inside_selection_reviews_selected_mismatches(
    mock_st, review
):
    mock_st.session_state["backchecks_attribution_review_click"] = {"row": 1}
    mock_st.dataframe.return_value = MagicMock(selection=MagicMock(rows=[0, 1, 2]))
    with patch(f"{MODULE}._attribution_dialog") as dialog:
        _render_comparison_table(_table(), {}, "KEY", review)

    rows = dialog.call_args.args[0]
    assert rows["KEY"].to_list() == ["s1", "s2"]


def test_comparison_table_without_review_is_plain(mock_st):
    _render_comparison_table(_table(), {}, "KEY", None)
    assert "on_select" not in mock_st.dataframe.call_args.kwargs


# ---------------------------------------------------------------------------
# Attribution form
# ---------------------------------------------------------------------------


def _mismatches() -> pl.DataFrame:
    return _table().head(2)


@pytest.mark.parametrize("source", [ErrorSource.BACKCHECKER, ErrorSource.RESPONDENT])
def test_attribution_form_needs_note_to_save(mock_st, review, source):
    mock_st.radio.return_value = source
    mock_st.text_area.return_value = "  "
    with patch(f"{MODULE}.save_attributions") as save:
        _render_attribution_form(_mismatches(), "KEY", review)

    assert mock_st.button.call_args.kwargs["disabled"] is True
    save.assert_not_called()


def test_attribution_form_saves_enumerator_without_note(mock_st, review):
    mock_st.radio.return_value = ErrorSource.ENUMERATOR
    mock_st.button.return_value = True
    with (
        patch(f"{MODULE}.save_attributions") as save,
        patch(f"{MODULE}.get_reviewer_name", return_value="ana"),
        patch(f"{MODULE}.queue_notice") as notice,
    ):
        _render_attribution_form(_mismatches(), "KEY", review)

    assert mock_st.button.call_args.kwargs["disabled"] is False
    project_id, page_name_id, entries = save.call_args.args
    assert (project_id, page_name_id) == ("proj", "page")
    assert entries["source"].to_list() == ["Enumerator", "Enumerator"]
    assert entries["user"].to_list() == ["ana", "ana"]
    assert isinstance(entries["date"][0], datetime)
    assert notice.call_args.args[1] == "toast"
    mock_st.rerun.assert_called_once()


def test_attribution_form_saves_note(mock_st, review):
    mock_st.radio.return_value = ErrorSource.RESPONDENT
    mock_st.text_area.return_value = "respondent changed the answer"
    mock_st.button.return_value = True
    with (
        patch(f"{MODULE}.save_attributions") as save,
        patch(f"{MODULE}.get_reviewer_name", return_value="ana"),
        patch(f"{MODULE}.queue_notice"),
    ):
        _render_attribution_form(_mismatches(), "KEY", review)

    entries = save.call_args.args[2]
    assert entries["note"].to_list() == ["respondent changed the answer"] * 2


def test_attribution_form_shows_error_when_save_fails(mock_st, review):
    mock_st.radio.return_value = ErrorSource.ENUMERATOR
    mock_st.button.return_value = True
    with (
        patch(f"{MODULE}.save_attributions", side_effect=OSError("disk full")),
        patch(f"{MODULE}.get_reviewer_name", return_value="ana"),
    ):
        _render_attribution_form(_mismatches(), "KEY", review)

    mock_st.error.assert_called_once()
    mock_st.rerun.assert_not_called()


def test_attribution_form_shows_values_read_only(mock_st, review):
    mock_st.radio.return_value = ErrorSource.ENUMERATOR
    _render_attribution_form(_mismatches(), "KEY", review)

    shown = mock_st.dataframe.call_args.args[0]
    assert {"survey_value", "backcheck_value"} <= set(shown.columns)
    mock_st.data_editor.assert_not_called()


# ---------------------------------------------------------------------------
# Attribution log, summary metric and rate highlighting
# ---------------------------------------------------------------------------


def test_attribution_log_empty(mock_st):
    _render_attribution_log(pl.DataFrame(schema=ATTRIBUTION_LOG_SCHEMA))
    mock_st.info.assert_called_once()


def test_attribution_log_lists_history(mock_st):
    log = pl.DataFrame(
        [
            {
                "survey_key": "s1",
                "backcheck_key": "b1",
                "column_name": "age",
                "survey_value": "30",
                "backcheck_value": "31",
                "source": source,
                "note": None,
                "user": "ana",
                "date": datetime(2026, 1, day),
            }
            for day, source in [(1, "Enumerator"), (2, "Unattributed")]
        ],
        schema=ATTRIBUTION_LOG_SCHEMA,
    )
    _render_attribution_log(log)
    shown = mock_st.dataframe.call_args.args[0]
    assert shown["source"].to_list() == ["Unattributed", "Enumerator"]


def _summary_metric(analysis):
    survey = pl.DataFrame({"key": [1, 2]})
    backcheck = pl.DataFrame({"key": [1]})
    settings = BackcheckSettings(survey_key="key", survey_id="key")
    with patch(f"{MODULE}.metric_row") as metric_row:
        _render_backcheck_summary(survey, backcheck, settings, analysis)
    metrics = metric_row.call_args.args[0]
    return next(m for m in metrics if m[0] == "Mismatches Attributed")


def test_summary_shows_share_of_mismatches_attributed(mock_st):
    analysis = _table().with_columns(
        pl.Series(ERROR_SOURCE_COL, ["Respondent", "Unattributed", None])
    )
    assert _summary_metric(analysis)[1] == "50.0%"


def test_summary_attributed_share_na_without_mismatches(mock_st):
    assert _summary_metric(pl.DataFrame())[1] == "N/A"


def test_error_rate_columns_cover_regular_and_adjusted_rates():
    columns = [
        "enumerator",
        "Coverage %",
        "Error Rate % (Cat 1)",
        "Adjusted Error Rate % (Cat 1)",
        "Error Rate % (Total)",
        "Adjusted Error Rate % (Total)",
    ]
    assert _error_rate_columns(columns) == columns[2:]


def test_highlight_above_target():
    style = _highlight_above_target(5.0)
    assert style(5.01)
    assert style(5.0) == ""
    assert style(None) == ""


def test_attribution_form_when_survey_key_is_merge_id(mock_st, review):
    mock_st.radio.return_value = ErrorSource.ENUMERATOR
    _render_attribution_form(_mismatches().drop("KEY__BCCL"), "KEY", review)

    shown = mock_st.dataframe.call_args.args[0]
    assert shown.columns.count("KEY") == 1


def test_comparison_results_section_is_a_fragment():
    """Selecting rows or clicking Review reruns only the comparison section."""
    import importlib
    import sys

    import datasure.checks.backchecks.report_ui as report_ui

    fragments = []
    st = make_mock_st()
    st.fragment = lambda func: fragments.append(func.__name__) or func
    original_st = sys.modules["streamlit"]
    sys.modules["streamlit"] = st
    try:
        importlib.reload(report_ui)
    finally:
        sys.modules["streamlit"] = original_st
        importlib.reload(report_ui)

    assert "_render_comparison_results_section" in fragments


def test_attribution_save_reruns_the_whole_app(mock_st, review):
    """A saved attribution refreshes the rates outside the fragment too."""
    mock_st.radio.return_value = ErrorSource.ENUMERATOR
    mock_st.button.return_value = True
    with (
        patch(f"{MODULE}.save_attributions"),
        patch(f"{MODULE}.get_reviewer_name", return_value="ana"),
        patch(f"{MODULE}.queue_notice"),
    ):
        _render_attribution_form(_mismatches(), "KEY", review)

    mock_st.rerun.assert_called_once_with(scope="app")


def _error_rate_cards(mock_st, analysis):
    survey = pl.DataFrame({"key": [1, 2]})
    backcheck = pl.DataFrame({"key": [1]})
    settings = BackcheckSettings(survey_key="key", survey_id="key")
    with patch(f"{MODULE}.metric_row"):
        _render_backcheck_summary(survey, backcheck, settings, analysis)
    return {
        c.args[0]: c
        for c in mock_st.metric.call_args_list
        if c.args[0].startswith("Error Rate")
    }


def test_summary_error_rate_cards_show_adjusted_rate_as_delta(mock_st):
    # Two mismatches out of three compared, one attributed to the respondent.
    analysis = _table().with_columns(
        pl.lit(1).alias("category"),
        pl.Series(ERROR_SOURCE_COL, ["Respondent", "Unattributed", None]),
    )
    cards = _error_rate_cards(mock_st, analysis)

    assert list(cards) == [
        "Error Rate (Total)",
        "Error Rate (Cat 1)",
        "Error Rate (Cat 2)",
        "Error Rate (Cat 3)",
    ]
    total = cards["Error Rate (Total)"]
    assert total.args[1] == "66.67%"
    assert total.kwargs["delta"] == "33.33% adjusted"
    assert total.kwargs["delta_color"] == "off"
    assert total.kwargs["delta_arrow"] == "off"
    assert "33.33%" in total.kwargs["help"]  # backchecker adjusted rate
    cat2 = cards["Error Rate (Cat 2)"]
    assert cat2.args[1] == "N/A"
    # Every card has a delta line, so the cards are the same height.
    assert cat2.kwargs["delta"] == "No values compared"


def test_summary_error_rate_cards_need_configured_columns(mock_st):
    assert _error_rate_cards(mock_st, pl.DataFrame()) == {}
    assert any("Error rates" in c.args[0] for c in mock_st.info.call_args_list)
