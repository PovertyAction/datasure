"""Tests for correcting and accepting outliers from the GPS outliers table."""

import json
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl
import pytest
from pandas.io.formats.style import Styler

from datasure.checks.gpschecks.report_ui import (
    REVIEW_BUTTON_COL,
    GPSReview,
    _render_gps_correction_form,
    _render_gps_outliers_checks,
    _render_outliers_data_table,
    gpschecks_report,
    plot_clusters_on_map,
)
from datasure.checks.gpschecks.review import (
    CoordinateColumns,
    GPSAction,
    GPSSelection,
)
from datasure.checks.outliers.review import REVIEW_REASON_COL, REVIEW_STATUS_COL
from datasure.models.enums import GPSFormatType, GPSOutlierMethod
from datasure.processing.correction_log import Action
from datasure.utils.dataframe_utils import ColumnByType

MODULE = "datasure.checks.gpschecks.report_ui"
COLUMNS = CoordinateColumns(latitude="gps_lat", longitude="gps_lon")


@pytest.fixture
def data() -> pl.DataFrame:
    """Corrected survey data."""
    return pl.DataFrame(
        {
            "KEY": ["K1", "K2", "K3"],
            "hhid": ["H1", "H2", "H3"],
            "gps_lat": [6.7, 6.5, 6.6],
            "gps_lon": [-0.2, -0.3, -0.25],
            "gps_acc": [4.0, 5.0, 3.0],
        }
    )


@pytest.fixture
def outlier_df() -> pd.DataFrame:
    """Detection output for `data`: K1 and K2 are outliers."""
    return pd.DataFrame(
        {
            "KEY": ["K1", "K2", "K3"],
            "latitude": [6.7, 6.5, 6.6],
            "longitude": [-0.2, -0.3, -0.25],
            "Outlier": [True, True, False],
        }
    )


def _gps_acceptances(*keys: str) -> pl.DataFrame:
    snapshot = json.dumps({"gps_lat": "6.7", "gps_lon": "-0.2"})
    return pl.DataFrame(
        {
            "KEY": list(keys),
            "column": [None] * len(keys),
            "current_value": [snapshot] * len(keys),
            "reason": ["Market trip"] * len(keys),
        },
        schema={
            "KEY": pl.String,
            "column": pl.String,
            "current_value": pl.String,
            "reason": pl.String,
        },
    )


def _review(data, columns=COLUMNS, accepted=()) -> GPSReview:
    processor = MagicMock()
    processor.get_active_acceptances.return_value = _gps_acceptances(*accepted)
    return GPSReview(
        processor=processor,
        alias="survey",
        data=data,
        columns=columns,
        survey_id="hhid",
    )


def _expander_st(clicked_row=None, show_reviewed=False) -> MagicMock:
    st_mock = MagicMock()
    st_mock.toggle.return_value = show_reviewed
    st_mock.session_state = {}
    if clicked_row is not None:
        st_mock.session_state["gps_outlier_review_click_gps1"] = {
            "row": clicked_row,
            "label": "Review",
        }
    return st_mock


def _shown_table(st_mock) -> pl.DataFrame:
    shown = st_mock.dataframe.call_args.args[0]
    if isinstance(shown, Styler):
        shown = pl.from_pandas(shown.data)
    return shown


# =============================================================================
# The outliers table
# =============================================================================


class TestOutliersTable:
    def _render(self, outlier_df, review, st_mock):
        from datasure.checks.gpschecks.report_ui import _mark_accepted_outliers

        marked = _mark_accepted_outliers(outlier_df, "KEY", review)
        with (
            patch(f"{MODULE}.st", st_mock),
            patch(f"{MODULE}._gps_correction_dialog") as dialog,
            # styled_dataframe imports streamlit itself; forward to the mock.
            patch(
                f"{MODULE}.styled_dataframe",
                side_effect=lambda styler, **kw: st_mock.dataframe(styler, **kw),
            ),
        ):
            _render_outliers_data_table(
                marked, "gps1", "KEY", None, None, "Auto", None, review
            )
        return dialog

    def test_first_column_is_a_review_button(self, data, outlier_df):
        st_mock = _expander_st()
        self._render(outlier_df, _review(data), st_mock)

        shown = _shown_table(st_mock)
        assert shown.columns[0] == REVIEW_BUTTON_COL
        assert shown["KEY"].to_list() == ["K1", "K2"]
        assert REVIEW_BUTTON_COL in st_mock.dataframe.call_args.kwargs["column_config"]

    def test_accepted_outliers_are_hidden(self, data, outlier_df):
        st_mock = _expander_st()
        self._render(outlier_df, _review(data, accepted=["K1"]), st_mock)

        shown = _shown_table(st_mock)
        assert shown["KEY"].to_list() == ["K2"]
        assert REVIEW_STATUS_COL not in shown.columns

    def test_show_reviewed_shows_them_green_with_the_reason(self, data, outlier_df):
        st_mock = _expander_st(show_reviewed=True)
        self._render(outlier_df, _review(data, accepted=["K1"]), st_mock)

        styler = st_mock.dataframe.call_args.args[0]
        assert isinstance(styler, Styler)
        shown = _shown_table(st_mock)
        assert shown["KEY"].to_list() == ["K1", "K2"]
        assert shown[REVIEW_REASON_COL].to_list()[0] == "Market trip"

    def test_all_outliers_accepted_says_none_left(self, data, outlier_df):
        st_mock = _expander_st()
        self._render(outlier_df, _review(data, accepted=["K1", "K2"]), st_mock)

        st_mock.success.assert_called_once_with("No outliers left to review!")

    def test_clicking_review_opens_the_dialog_for_the_row(self, data, outlier_df):
        # K1 is accepted and hidden, so K2 is the first row.
        st_mock = _expander_st(clicked_row=0)
        review = _review(data, accepted=["K1"])
        dialog = self._render(outlier_df, review, st_mock)

        dialog.assert_called_once_with(
            "KEY", GPSSelection("K2", reviewed=False), review
        )

    def test_clicking_a_shown_accepted_row_marks_it_reviewed(self, data, outlier_df):
        st_mock = _expander_st(clicked_row=0, show_reviewed=True)
        dialog = self._render(outlier_df, _review(data, accepted=["K1"]), st_mock)

        assert dialog.call_args.args[1] == GPSSelection("K1", reviewed=True)

    def test_no_click_opens_no_dialog(self, data, outlier_df):
        dialog = self._render(outlier_df, _review(data), _expander_st())
        dialog.assert_not_called()

    def test_acceptances_for_another_configuration_are_ignored(self, data, outlier_df):
        st_mock = _expander_st()
        other = CoordinateColumns(latitude="bc_lat", longitude="bc_lon")
        self._render(outlier_df, _review(data, other, accepted=["K1"]), st_mock)

        assert _shown_table(st_mock)["KEY"].to_list() == ["K1", "K2"]


def test_without_review_the_table_has_no_button(outlier_df):
    st_mock = _expander_st()
    with patch(f"{MODULE}.st", st_mock):
        _render_outliers_data_table(outlier_df, "gps1", "KEY", None, None, "Auto", None)

    st_mock.toggle.assert_not_called()
    shown = st_mock.dataframe.call_args.args[0]
    assert REVIEW_BUTTON_COL not in shown.columns


# =============================================================================
# The correction form
# =============================================================================


def _form_st(action, reason="Checked on device", lat="", lon="", apply=True):
    st_mock = MagicMock()
    st_mock.selectbox.return_value = action
    lat_col, lon_col = MagicMock(), MagicMock()
    lat_col.text_input.return_value = lat
    lon_col.text_input.return_value = lon
    st_mock.columns.return_value = (lat_col, lon_col)
    st_mock.text_input.return_value = reason
    st_mock.button.return_value = apply
    return st_mock


class TestCorrectionForm:
    def _render(self, review, st_mock, selection=None, applied=True):
        selection = selection or GPSSelection("K1", reviewed=False)
        with (
            patch(f"{MODULE}.st", st_mock),
            patch(f"{MODULE}.apply_correction_entries", return_value=applied) as apply,
            patch(f"{MODULE}.queue_notice") as notice,
        ):
            _render_gps_correction_form("KEY", selection, review)
        return apply, notice

    def test_offers_every_action_for_an_unreviewed_outlier(self, data):
        st_mock = _form_st(GPSAction.REMOVE_OBSERVATION, apply=False)
        self._render(_review(data), st_mock)

        assert st_mock.selectbox.call_args.kwargs["options"] == list(GPSAction)

    def test_accept_is_not_offered_for_an_accepted_outlier(self, data):
        st_mock = _form_st(GPSAction.REMOVE_OBSERVATION, apply=False)
        self._render(_review(data), st_mock, GPSSelection("K1", reviewed=True))

        assert GPSAction.ACCEPT not in st_mock.selectbox.call_args.kwargs["options"]

    def test_modify_saves_both_coordinates_with_gps_as_source(self, data):
        st_mock = _form_st(GPSAction.MODIFY_COORDINATES, lat="6.61", lon="-0.21")
        apply, notice = self._render(_review(data), st_mock)

        _processor, alias, key_col, entries = apply.call_args.args
        assert (alias, key_col) == ("survey", "KEY")
        assert apply.call_args.kwargs["source"] == "gps"
        assert [
            (e.action, e.column, e.current_value, e.new_value) for e in entries
        ] == [
            (Action.MODIFY_VALUE, "gps_lat", 6.7, "6.61"),
            (Action.MODIFY_VALUE, "gps_lon", -0.2, "-0.21"),
        ]
        assert {e.reason for e in entries} == {"Checked on device"}
        assert {e.survey_id_value for e in entries} == {"H1"}
        notice.assert_called_once()
        assert notice.call_args.args[1] == "toast"
        st_mock.rerun.assert_called_once()

    def test_modify_is_disabled_until_both_coordinates_are_entered(self, data):
        st_mock = _form_st(GPSAction.MODIFY_COORDINATES, lat="6.61", apply=False)
        self._render(_review(data), st_mock)

        assert st_mock.button.call_args.kwargs["disabled"] is True

    def test_out_of_range_coordinates_show_an_error_and_disable_apply(self, data):
        st_mock = _form_st(GPSAction.MODIFY_COORDINATES, lat="96", lon="1", apply=False)
        self._render(_review(data), st_mock)

        st_mock.error.assert_called_once_with("Latitude must be between -90 and 90")
        assert st_mock.button.call_args.kwargs["disabled"] is True

    def test_apply_is_disabled_without_a_reason(self, data):
        st_mock = _form_st(GPSAction.REMOVE_COORDINATES, reason="  ", apply=False)
        self._render(_review(data), st_mock)

        assert st_mock.button.call_args.kwargs["disabled"] is True

    def test_remove_coordinates_clears_only_the_coordinate_columns(self, data):
        st_mock = _form_st(GPSAction.REMOVE_COORDINATES)
        apply, _ = self._render(_review(data), st_mock)

        entries = apply.call_args.args[3]
        assert [(e.action, e.column) for e in entries] == [
            (Action.REMOVE_VALUE, "gps_lat"),
            (Action.REMOVE_VALUE, "gps_lon"),
        ]

    def test_remove_observation_removes_the_row(self, data):
        st_mock = _form_st(GPSAction.REMOVE_OBSERVATION)
        apply, _ = self._render(_review(data), st_mock)

        entries = apply.call_args.args[3]
        assert [(e.action, e.key_value) for e in entries] == [(Action.REMOVE_ROW, "K1")]

    def test_accept_records_both_coordinates(self, data):
        st_mock = _form_st(GPSAction.ACCEPT)
        apply, _ = self._render(_review(data), st_mock)

        (entry,) = apply.call_args.args[3]
        assert entry.action == Action.ACCEPT
        assert entry.check_type == "gps"
        assert entry.column is None
        assert entry.current_value == {"gps_lat": 6.7, "gps_lon": -0.2}

    def test_failed_save_does_not_rerun(self, data):
        st_mock = _form_st(GPSAction.REMOVE_OBSERVATION)
        _, notice = self._render(_review(data), st_mock, applied=False)

        notice.assert_not_called()
        st_mock.rerun.assert_not_called()

    def test_single_column_configuration_only_removes_observations(self, data):
        st_mock = _form_st(GPSAction.REMOVE_OBSERVATION, apply=False)
        self._render(_review(data, columns=None), st_mock)

        assert st_mock.selectbox.call_args.kwargs["options"] == [
            GPSAction.REMOVE_OBSERVATION
        ]
        st_mock.info.assert_called_once()

    def test_numeric_keys_are_saved_with_their_native_type(self):
        data = pl.DataFrame({"KEY": [7], "gps_lat": [1.0], "gps_lon": [2.0]})
        st_mock = _form_st(GPSAction.REMOVE_OBSERVATION)
        review = GPSReview(MagicMock(), "survey", data, COLUMNS)
        apply, _ = self._render(review, st_mock, GPSSelection(7, reviewed=False))

        assert apply.call_args.args[3][0].key_value == 7

    def test_duplicate_key_with_different_coordinates_cannot_be_reviewed(self):
        data = pl.DataFrame(
            {"KEY": ["K1", "K1"], "gps_lat": [1.0, 1.5], "gps_lon": [2.0, 2.0]}
        )
        st_mock = _form_st(GPSAction.REMOVE_OBSERVATION)
        apply, _ = self._render(GPSReview(MagicMock(), "s", data, COLUMNS), st_mock)

        st_mock.warning.assert_called_once()
        st_mock.selectbox.assert_not_called()
        apply.assert_not_called()

    def test_widget_keys_are_unique_per_configuration(self, data):
        keys = []
        for columns in (COLUMNS, CoordinateColumns("bc_lat", "bc_lon")):
            frame = data.with_columns(
                pl.col("gps_lat").alias("bc_lat"), pl.col("gps_lon").alias("bc_lon")
            )
            st_mock = _form_st(GPSAction.REMOVE_OBSERVATION, apply=False)
            self._render(_review(frame, columns), st_mock)
            keys.append(st_mock.selectbox.call_args.kwargs["key"])
        assert keys[0] != keys[1]


# =============================================================================
# Metrics, map and wiring
# =============================================================================


def _columns_mock(spec):
    count = spec if isinstance(spec, int) else len(spec)
    return [MagicMock() for _ in range(count)]


@patch(f"{MODULE}._render_outliers_data_table")
@patch(f"{MODULE}.plot_clusters_on_map")
@patch(f"{MODULE}._run_lof_detection")
@patch(f"{MODULE}.CorrectionProcessor")
@patch(f"{MODULE}._load_and_parse_gps_data")
@patch(f"{MODULE}.st")
def test_outlier_count_leaves_out_accepted_outliers(
    st_mock,
    mock_load,
    mock_processor,
    mock_lof,
    mock_plot,
    mock_table,
    data,
    outlier_df,
):
    st_mock.columns.side_effect = _columns_mock
    st_mock.selectbox.return_value = GPSOutlierMethod.auto_lof.value
    settings = pl.DataFrame(
        {
            "alias": ["gps1"],
            "format_type": [GPSFormatType.SEPARATE_COLUMNS.value],
            "latitude_column": ["gps_lat"],
            "longitude_column": ["gps_lon"],
        }
    )
    mock_load.return_value = (settings, "gps1", data)
    mock_lof.return_value = outlier_df
    mock_processor.return_value.get_active_acceptances.return_value = _gps_acceptances(
        "K1"
    )

    _render_gps_outliers_checks.__wrapped__(
        "proj", "page", data, "KEY", None, None, alias="survey", survey_id="hhid"
    )

    metrics = {c.args[0]: c.args[1] for c in st_mock.metric.call_args_list}
    assert metrics["Outliers Detected"] == "1"
    plotted = mock_plot.call_args.args[0]
    assert plotted[REVIEW_STATUS_COL].tolist()[0] == "Reviewed"
    review = mock_table.call_args.args[-1]
    assert review.columns == COLUMNS
    assert review.survey_id == "hhid"


@patch(f"{MODULE}._render_outliers_data_table")
@patch(f"{MODULE}.plot_clusters_on_map")
@patch(f"{MODULE}._run_lof_detection")
@patch(f"{MODULE}._load_and_parse_gps_data")
@patch(f"{MODULE}.st")
def test_without_alias_outliers_are_not_reviewable(
    st_mock, mock_load, mock_lof, mock_plot, mock_table, data, outlier_df
):
    st_mock.columns.side_effect = _columns_mock
    st_mock.selectbox.return_value = GPSOutlierMethod.auto_lof.value
    mock_load.return_value = (pl.DataFrame({"alias": ["gps1"]}), "gps1", data)
    mock_lof.return_value = outlier_df

    _render_gps_outliers_checks.__wrapped__("proj", "page", data, "KEY", None, None)

    metrics = {c.args[0]: c.args[1] for c in st_mock.metric.call_args_list}
    assert metrics["Outliers Detected"] == "2"
    assert mock_table.call_args.args[-1] is None


@patch(f"{MODULE}._render_scatterplot_map")
def test_map_draws_accepted_outliers_green(mock_map, outlier_df):
    marked = outlier_df.assign(
        **{REVIEW_STATUS_COL: ["Reviewed", None, None], REVIEW_REASON_COL: None}
    )
    plot_clusters_on_map(
        marked, "latitude", "longitude", None, None, "KEY", None, "Outlier"
    )

    plotted = mock_map.call_args.args[0]
    assert plotted["outlier_status"].tolist() == ["Accepted", "Outlier", "Normal"]
    assert plotted["color"].tolist() == [
        [25, 135, 84, 200],
        [255, 0, 0, 160],
        [0, 0, 255, 160],
    ]


@patch(f"{MODULE}._render_gps_comparison_checks")
@patch(f"{MODULE}._render_gps_outliers_checks")
@patch(f"{MODULE}._render_gps_coordinates")
@patch(f"{MODULE}._render_gps_column_actions")
@patch(f"{MODULE}.gpschecks_report_settings")
@patch(f"{MODULE}.pydeck.settings")
@patch(f"{MODULE}.st")
def test_report_passes_alias_and_survey_id_to_outliers(
    st_mock, _pydeck, mock_settings_fn, _actions, _coords, mock_outliers, _comparison
):
    mock_settings_fn.return_value = MagicMock(mapbox_custom_key="token")
    survey_columns = ColumnByType(
        string_columns=[],
        numeric_columns=[],
        datetime_columns=[],
        categorical_columns=[],
    )
    config = {"survey_key": "KEY", "survey_id": "hhid"}
    with patch(f"{MODULE}._show_saved_toast") as toast:
        gpschecks_report(
            "proj",
            "page",
            pl.DataFrame({"KEY": ["K1"]}),
            "settings.json",
            config,
            survey_columns,
            alias="survey",
        )

    toast.assert_called_once()
    kwargs = mock_outliers.call_args.kwargs
    assert kwargs == {"alias": "survey", "survey_id": "hhid"}
