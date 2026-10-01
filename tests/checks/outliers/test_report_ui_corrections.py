"""Tests for correcting and accepting flags from the outliers report tables."""

from unittest.mock import MagicMock, patch

import polars as pl
import pytest

from datasure.checks.outliers.models import OutlierSettings
from datasure.checks.outliers.report_ui import (
    ReviewContext,
    _render_constraint_violations_table,
    _render_flag_correction_form,
    _render_outlier_column_inspection,
    outliers_report,
)
from datasure.checks.outliers.review import FlagSelection
from datasure.processing.correction_log import Action
from datasure.utils.correction_form import CorrectionFormState
from datasure.utils.dataframe_utils import ColumnByType
from tests.checks.outliers.conftest import _columns_side_effect

MODULE = "datasure.checks.outliers.report_ui"


@pytest.fixture
def settings() -> OutlierSettings:
    return OutlierSettings(survey_key="KEY", survey_id="hhid")


@pytest.fixture
def data() -> pl.DataFrame:
    return pl.DataFrame(
        {
            "KEY": ["K1", "K2", "K3"],
            "hhid": ["H1", "H2", "H3"],
            "age": [150, 70, 30],
        }
    )


@pytest.fixture
def violations() -> pl.DataFrame:
    """`compute_constraint_violations` output for `data`."""
    return pl.DataFrame(
        {
            "KEY": ["K1", "K2", "K3"],
            "column name": ["age", "age", "age"],
            "column value": [150.0, 70.0, 30.0],
            "hard_min": [0.0] * 3,
            "soft_min": [None] * 3,
            "soft_max": [65.0] * 3,
            "hard_max": [100.0] * 3,
            "violation reason": [
                "Value is above hard maximum 100.0",
                "Value is above soft maximum 65.0",
                "no violation",
            ],
        }
    )


def _acceptances(*rows: tuple[str, str, str]) -> pl.DataFrame:
    """Active acceptances with (KEY, column, reason) rows."""
    return pl.DataFrame(
        {
            "KEY": [r[0] for r in rows],
            "action": ["accept"] * len(rows),
            "column": [r[1] for r in rows],
            "reason": [r[2] for r in rows],
        },
        schema={
            "KEY": pl.String,
            "action": pl.String,
            "column": pl.String,
            "reason": pl.String,
        },
    )


def _review(acceptances_by_check: dict[str, pl.DataFrame] | None = None):
    acceptances_by_check = acceptances_by_check or {}
    processor = MagicMock()
    processor.get_active_acceptances.side_effect = lambda alias, check_type, key_col: (
        acceptances_by_check.get(check_type, _acceptances())
    )
    return ReviewContext(processor=processor, alias="survey")


def _st_mock(selected_rows: list[int] | None = None, show_reviewed=False):
    st_mock = MagicMock()
    st_mock.columns.side_effect = _columns_side_effect
    st_mock.multiselect.return_value = []
    st_mock.toggle.return_value = show_reviewed
    st_mock.session_state = {}
    st_mock.dataframe.return_value.selection.rows = selected_rows or []
    return st_mock


def _shown_table(st_mock) -> pl.DataFrame:
    return st_mock.dataframe.call_args.args[0]


def _selection(**overrides) -> FlagSelection:
    values = {
        "key_value": "K2",
        "column": "age",
        "check_type": "constraints",
        "flagged": True,
        "reviewed": False,
        "hard": False,
    }
    return FlagSelection(**(values | overrides))


def _form_state(action=Action.ACCEPT, reason="verified", **overrides):
    values = {
        "key_value": "K2",
        "action": action,
        "column": "age",
        "current_value": 70,
        "reason": reason,
        "check_type": "constraints" if action == Action.ACCEPT else None,
        "survey_id_value": "H2",
    }
    return CorrectionFormState(**(values | overrides))


class TestConstraintTableSelection:
    def _render(self, data, violations, settings, st_mock, review):
        with (
            patch(f"{MODULE}.st", st_mock),
            patch(f"{MODULE}.load_check_settings", return_value={}),
            patch(f"{MODULE}.save_check_settings"),
            patch(f"{MODULE}._render_flag_correction_form") as form,
        ):
            _render_constraint_violations_table(
                data, violations, settings, "settings.json", review=review
            )
        return form

    def test_table_allows_single_row_selection(self, data, violations, settings):
        st_mock = _st_mock()

        self._render(data, violations, settings, st_mock, _review())

        kwargs = st_mock.dataframe.call_args.kwargs
        assert kwargs["on_select"] == "rerun"
        assert kwargs["selection_mode"] == "single-row"

    def test_selecting_a_row_opens_the_form_prefilled_from_it(
        self, data, violations, settings
    ):
        st_mock = _st_mock(selected_rows=[0])
        review = _review()

        form = self._render(data, violations, settings, st_mock, review)

        form.assert_called_once()
        _, _, selection, passed_review = form.call_args.args
        assert selection == FlagSelection(
            key_value="K1",
            column="age",
            check_type="constraints",
            flagged=True,
            reviewed=False,
            hard=True,
        )
        assert passed_review is review

    def test_no_selection_opens_no_form(self, data, violations, settings):
        form = self._render(data, violations, settings, _st_mock(), _review())

        form.assert_not_called()

    def test_accepted_violations_are_hidden(self, data, violations, settings):
        st_mock = _st_mock()
        review = _review({"constraints": _acceptances(("K1", "age", "verified"))})

        self._render(data, violations, settings, st_mock, review)

        assert _shown_table(st_mock)["KEY"].to_list() == ["K2"]

    def test_show_reviewed_shows_them_with_badge_and_reason(
        self, data, violations, settings
    ):
        st_mock = _st_mock(show_reviewed=True)
        review = _review({"constraints": _acceptances(("K1", "age", "verified"))})

        self._render(data, violations, settings, st_mock, review)

        table = _shown_table(st_mock)
        assert table.select("KEY", "review status", "review reason").rows() == [
            ("K1", "Reviewed", "verified"),
            ("K2", None, None),
        ]

    def test_outlier_acceptance_does_not_hide_a_constraint_violation(
        self, data, violations, settings
    ):
        st_mock = _st_mock()
        review = _review({"outliers": _acceptances(("K1", "age", "verified"))})

        self._render(data, violations, settings, st_mock, review)

        assert _shown_table(st_mock)["KEY"].to_list() == ["K1", "K2"]

    def test_selection_resets_when_the_shown_rows_change(
        self, data, violations, settings
    ):
        """A row position must never carry over to a different set of rows."""
        review = _review({"constraints": _acceptances(("K1", "age", "verified"))})
        hidden, shown = _st_mock(show_reviewed=False), _st_mock(show_reviewed=True)

        self._render(data, violations, settings, hidden, review)
        self._render(data, violations, settings, shown, review)

        assert (
            hidden.dataframe.call_args.kwargs["key"]
            != shown.dataframe.call_args.kwargs["key"]
        )

    def test_selection_is_kept_while_the_rows_are_unchanged(
        self, data, violations, settings
    ):
        first, second = _st_mock(), _st_mock()

        self._render(data, violations, settings, first, _review())
        self._render(data, violations, settings, second, _review())

        assert (
            first.dataframe.call_args.kwargs["key"]
            == second.dataframe.call_args.kwargs["key"]
        )

    def test_without_review_the_table_is_read_only(self, data, violations, settings):
        st_mock = _st_mock()

        self._render(data, violations, settings, st_mock, None)

        assert "on_select" not in st_mock.dataframe.call_args.kwargs


class TestOutlierTableSelection:
    @pytest.fixture
    def outliers(self) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "KEY": ["K1", "K2", "K3"],
                "column name": ["age"] * 3,
                "column value": [150.0, 70.0, 30.0],
                "outlier reason": [
                    "Value is above upper bound 120.00",
                    "no outlier",
                    "no outlier",
                ],
            }
        )

    def _render(self, data, outliers, settings, st_mock, review):
        with (
            patch(f"{MODULE}.st", st_mock),
            patch(f"{MODULE}.load_check_settings", return_value={}),
            patch(f"{MODULE}.save_check_settings"),
            patch(f"{MODULE}._create_descriptive_stats", return_value=pl.DataFrame()),
            patch(f"{MODULE}._create_box_plot"),
            patch(f"{MODULE}._render_flag_correction_form") as form,
        ):
            st_mock.selectbox.return_value = "age"
            _render_outlier_column_inspection(
                data, outliers, settings, "settings.json", review=review
            )
        return form

    def test_selecting_a_row_opens_the_form_for_outliers(
        self, data, outliers, settings
    ):
        st_mock = _st_mock(selected_rows=[0])

        form = self._render(data, outliers, settings, st_mock, _review())

        selection = form.call_args.args[2]
        assert selection.key_value == "K1"
        assert selection.column == "age"
        assert selection.check_type == "outliers"
        assert selection.hard is False

    def test_accepted_outliers_are_hidden(self, data, outliers, settings):
        st_mock = _st_mock()
        review = _review({"outliers": _acceptances(("K1", "age", "verified"))})

        self._render(data, outliers, settings, st_mock, review)

        assert "K1" not in _shown_table(st_mock)["KEY"].to_list()


class TestFlagCorrectionForm:
    def _render(self, data, settings, selection, review, state, *, apply, confirm):
        st_mock = _st_mock()
        st_mock.button.return_value = apply
        st_mock.checkbox.return_value = confirm
        with (
            patch(f"{MODULE}.st", st_mock),
            patch(f"{MODULE}.render_correction_inputs", return_value=state) as inputs,
            patch(
                f"{MODULE}.apply_correction_entries", return_value=True
            ) as apply_entries,
        ):
            _render_flag_correction_form(data, settings, selection, review)
        return st_mock, inputs, apply_entries

    def test_form_is_prefilled_from_the_selection_and_data(self, data, settings):
        _, inputs, _ = self._render(
            data,
            settings,
            _selection(),
            _review(),
            _form_state(),
            apply=False,
            confirm=False,
        )

        args, kwargs = inputs.call_args
        assert args == (data, "KEY", "K2")
        assert kwargs["column"] == "age"
        assert kwargs["current_value"] == 70
        assert kwargs["survey_id_value"] == "H2"
        assert kwargs["check_type"] == "constraints"
        assert kwargs["actions"] == [
            Action.MODIFY_VALUE,
            Action.REMOVE_VALUE,
            Action.ACCEPT,
        ]

    def test_apply_saves_with_the_check_as_source_and_reruns(self, data, settings):
        review = _review()

        st_mock, _, apply_entries = self._render(
            data,
            settings,
            _selection(),
            review,
            _form_state(action=Action.MODIFY_VALUE, new_value="60"),
            apply=True,
            confirm=False,
        )

        args, kwargs = apply_entries.call_args
        assert args[:3] == (review.processor, "survey", "KEY")
        (entry,) = args[3]
        assert entry.action == Action.MODIFY_VALUE
        assert entry.new_value == "60"
        assert kwargs["source"] == "constraints"
        st_mock.rerun.assert_called_once()

    def test_a_save_queues_a_toast_for_after_the_rerun(self, data, settings):
        with patch(f"{MODULE}.queue_notice") as queue_notice:
            self._render(
                data,
                settings,
                _selection(),
                _review(),
                _form_state(),
                apply=True,
                confirm=False,
            )

        scope, level, message = queue_notice.call_args.args
        assert scope == "outliers_corrections"
        assert level == "toast"
        assert "Correction Log" in message

    def test_hard_violation_accept_is_disabled_until_confirmed(self, data, settings):
        st_mock, _, apply_entries = self._render(
            data,
            settings,
            _selection(key_value="K1", hard=True),
            _review(),
            _form_state(key_value="K1", current_value=150),
            apply=False,
            confirm=False,
        )

        st_mock.checkbox.assert_called_once()
        assert st_mock.button.call_args.kwargs["disabled"] is True
        apply_entries.assert_not_called()

    def test_confirmed_hard_violation_accept_is_logged_as_hard(self, data, settings):
        st_mock, _, apply_entries = self._render(
            data,
            settings,
            _selection(key_value="K1", hard=True),
            _review(),
            _form_state(key_value="K1", current_value=150),
            apply=True,
            confirm=True,
        )

        assert st_mock.button.call_args.kwargs["disabled"] is False
        (entry,) = apply_entries.call_args.args[3]
        assert entry.action == Action.ACCEPT
        assert entry.severity == "hard"

    def test_soft_violation_accept_needs_no_confirmation(self, data, settings):
        st_mock, _, apply_entries = self._render(
            data,
            settings,
            _selection(),
            _review(),
            _form_state(),
            apply=True,
            confirm=False,
        )

        st_mock.checkbox.assert_not_called()
        (entry,) = apply_entries.call_args.args[3]
        assert entry.severity is None

    def test_modifying_a_hard_violation_needs_no_confirmation(self, data, settings):
        st_mock, _, _ = self._render(
            data,
            settings,
            _selection(key_value="K1", hard=True),
            _review(),
            _form_state(action=Action.MODIFY_VALUE, new_value="90"),
            apply=False,
            confirm=False,
        )

        st_mock.checkbox.assert_not_called()

    def test_failed_save_does_not_rerun(self, data, settings):
        st_mock = _st_mock()
        st_mock.button.return_value = True
        with (
            patch(f"{MODULE}.st", st_mock),
            patch(f"{MODULE}.render_correction_inputs", return_value=_form_state()),
            patch(f"{MODULE}.apply_correction_entries", return_value=False),
        ):
            _render_flag_correction_form(data, settings, _selection(), _review())

        st_mock.rerun.assert_not_called()


class TestMetricsExcludeAcceptedFlags:
    @pytest.fixture
    def outliers(self) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "KEY": ["K1", "K2", "K3"],
                "column name": ["age"] * 3,
                "column value": [150.0, 70.0, 30.0],
                "outlier reason": [
                    "Value is above upper bound 120.00",
                    "Value is above upper bound 60.00",
                    "no outlier",
                ],
            }
        )

    def _run_report(self, data, violations, outliers, acceptances_by_check):
        config = {"survey_key": "KEY", "survey_id": "hhid"}
        columns = ColumnByType(
            all_columns=data.columns,
            categorical_columns=[],
            datetime_columns=[],
            numeric_columns=["age"],
            string_columns=[],
            integer_columns=["age"],
        )
        processor = _review(acceptances_by_check).processor
        with (
            patch(f"{MODULE}.st", _st_mock()),
            patch(
                f"{MODULE}.outliers_report_settings",
                return_value=OutlierSettings(**config),
            ),
            patch(f"{MODULE}._render_outlier_column_actions"),
            patch(
                f"{MODULE}.duckdb_get_table",
                return_value=pl.DataFrame({"column_name": [["age"]]}),
            ),
            patch(f"{MODULE}._update_unlocked_cols", side_effect=lambda df, _: df),
            patch(f"{MODULE}.duckdb_save_table"),
            patch(f"{MODULE}.compute_constraint_violations", return_value=violations),
            patch(f"{MODULE}.compute_outlier_output", return_value=outliers),
            patch(f"{MODULE}.CorrectionProcessor", return_value=processor),
            patch(f"{MODULE}._render_constraint_metrics") as constraint_metrics,
            patch(f"{MODULE}._render_constraint_violations_table") as table,
            patch(f"{MODULE}._render_outlier_metrics") as outlier_metrics,
            patch(f"{MODULE}._render_outlier_column_inspection") as inspection,
        ):
            outliers_report(
                "proj1",
                "page1",
                data,
                "settings.json",
                config,
                columns,
                alias="survey",
            )
        return constraint_metrics, table, outlier_metrics, inspection

    def test_constraint_metrics_do_not_count_accepted_violations(
        self, data, violations, outliers
    ):
        metrics, table, _, _ = self._run_report(
            data,
            violations,
            outliers,
            {"constraints": _acceptances(("K1", "age", "verified"))},
        )

        counted = metrics.call_args.args[0]
        assert counted.filter(pl.col("violation reason") != "no violation")[
            "KEY"
        ].to_list() == ["K2"]
        assert table.call_args.kwargs["review"].alias == "survey"

    def test_outlier_metrics_do_not_count_accepted_outliers(
        self, data, violations, outliers
    ):
        _, _, metrics, inspection = self._run_report(
            data,
            violations,
            outliers,
            {"outliers": _acceptances(("K2", "age", "verified"))},
        )

        counted = metrics.call_args.args[0]
        assert counted.filter(pl.col("outlier reason") != "no outlier")[
            "KEY"
        ].to_list() == ["K1"]
        # Rows are kept, so the column still counts as checked.
        assert counted.height == outliers.height
        assert inspection.call_args.kwargs["review"].alias == "survey"
