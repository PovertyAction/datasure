"""Tests for correcting and accepting flags from the outliers report tables."""

from unittest.mock import MagicMock, patch

import polars as pl
import pytest
from pandas.io.formats.style import Styler

from datasure.checks.outliers.models import OutlierSettings
from datasure.checks.outliers.report_ui import (
    REVIEW_BUTTON_COL,
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


def _acceptances(*rows: tuple[str, ...]) -> pl.DataFrame:
    """Active acceptances with (KEY, column, reason[, severity]) rows."""
    return pl.DataFrame(
        {
            "KEY": [r[0] for r in rows],
            "action": ["accept"] * len(rows),
            "column": [r[1] for r in rows],
            "reason": [r[2] for r in rows],
            "severity": [r[3] if len(r) > 3 else None for r in rows],
        },
        schema={
            "KEY": pl.String,
            "action": pl.String,
            "column": pl.String,
            "reason": pl.String,
            "severity": pl.String,
        },
    )


def _review(
    acceptances_by_check: dict[str, pl.DataFrame] | None = None,
    corrections: pl.DataFrame | None = None,
):
    """A review context; `corrections` are active value corrections."""
    acceptances_by_check = acceptances_by_check or {}
    processor = MagicMock()
    processor.get_active_acceptances.side_effect = lambda alias, check_type, key_col: (
        acceptances_by_check.get(check_type, _acceptances())
    )
    processor.get_active_corrections.return_value = (
        _acceptances() if corrections is None else corrections
    )
    return ReviewContext(processor=processor, alias="survey")


def _st_mock(
    clicked: tuple[str, int] | None = None,
    show_reviewed=False,
    flagged_only=True,
    reviewed_only=False,
):
    """A Streamlit mock; `clicked` is (check type, row) of a Review click."""
    st_mock = MagicMock()
    st_mock.columns.side_effect = _columns_side_effect
    st_mock.multiselect.return_value = []
    toggle_values = {
        "_flagged_only": flagged_only,
        "_show_reviewed": show_reviewed,
        "_reviewed_only": reviewed_only,
    }
    st_mock.toggle.side_effect = lambda label, *, key, **kwargs: next(
        value for suffix, value in toggle_values.items() if key.endswith(suffix)
    )
    st_mock.session_state = {}
    # Widget state is in session_state before the widget renders.
    for suffix, value in toggle_values.items():
        for check_type in ("constraints", "outliers"):
            st_mock.session_state[f"{check_type}{suffix}"] = value
    if clicked is not None:
        check_type, row = clicked
        st_mock.session_state[f"{check_type}_flag_review_click"] = {
            "row": row,
            "label": "Review",
        }
    return st_mock


def _shown_table(st_mock) -> pl.DataFrame:
    """The flags shown, without the Review button column."""
    shown = st_mock.dataframe.call_args.args[0]
    if isinstance(shown, Styler):
        shown = pl.from_pandas(shown.data)
    return shown.drop(REVIEW_BUTTON_COL, strict=False)


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


class TestConstraintTableReviewButton:
    def _render(self, data, violations, settings, st_mock, review):
        with (
            patch(f"{MODULE}.st", st_mock),
            patch(f"{MODULE}.load_check_settings", return_value={}),
            patch(f"{MODULE}.save_check_settings"),
            patch(f"{MODULE}._flag_correction_dialog") as dialog,
            # styled_dataframe imports streamlit itself; forward to the mock.
            patch(
                f"{MODULE}.styled_dataframe",
                side_effect=lambda styler, **kw: st_mock.dataframe(styler, **kw),
            ),
        ):
            _render_constraint_violations_table(
                data, violations, settings, "settings.json", review=review
            )
        return dialog

    def test_first_column_is_a_review_button_on_every_flag(
        self, data, violations, settings
    ):
        st_mock = _st_mock()

        self._render(data, violations, settings, st_mock, _review())

        shown = st_mock.dataframe.call_args.args[0]
        assert shown.columns[0] == REVIEW_BUTTON_COL
        assert all("Review" in label for label in shown[REVIEW_BUTTON_COL])
        button_config = st_mock.dataframe.call_args.kwargs["column_config"][
            REVIEW_BUTTON_COL
        ]
        assert button_config is st_mock.column_config.ButtonColumn.return_value
        button_kwargs = st_mock.column_config.ButtonColumn.call_args.kwargs
        assert button_kwargs["key"] == "constraints_flag_review_click"
        assert button_kwargs["pinned"] is True

    def test_button_column_does_not_clash_with_a_survey_column(
        self, violations, settings
    ):
        """A survey field named like the button column can be shown too."""
        data = pl.DataFrame(
            {
                "KEY": ["K1", "K2", "K3"],
                "hhid": ["H1", "H2", "H3"],
                "_review": [1, 2, 3],
            }
        )
        st_mock = _st_mock(clicked=("constraints", 0))
        st_mock.multiselect.return_value = ["_review"]

        dialog = self._render(data, violations, settings, st_mock, _review())

        shown = st_mock.dataframe.call_args.args[0]
        (button_col,) = st_mock.dataframe.call_args.kwargs["column_config"]
        assert button_col != REVIEW_BUTTON_COL
        assert shown.columns[0] == button_col
        assert shown["_review"].to_list() == [1, 2]
        assert dialog.call_args.args[2].key_value == "K1"

    def test_rows_are_not_selectable(self, data, violations, settings):
        st_mock = _st_mock()

        self._render(data, violations, settings, st_mock, _review())

        assert "on_select" not in st_mock.dataframe.call_args.kwargs

    def test_clicking_review_opens_the_dialog_prefilled_from_the_row(
        self, data, violations, settings
    ):
        st_mock = _st_mock(clicked=("constraints", 0))
        review = _review()

        dialog = self._render(data, violations, settings, st_mock, review)

        dialog.assert_called_once()
        _, _, selection, passed_review = dialog.call_args.args
        assert selection == FlagSelection(
            key_value="K1",
            column="age",
            check_type="constraints",
            flagged=True,
            reviewed=False,
            hard=True,
        )
        assert passed_review is review

    def test_no_click_opens_no_dialog(self, data, violations, settings):
        dialog = self._render(data, violations, settings, _st_mock(), _review())

        dialog.assert_not_called()

    def test_a_click_on_the_other_table_opens_no_dialog(
        self, data, violations, settings
    ):
        st_mock = _st_mock(clicked=("outliers", 0))

        dialog = self._render(data, violations, settings, st_mock, _review())

        dialog.assert_not_called()

    def test_accepted_violations_are_hidden(self, data, violations, settings):
        st_mock = _st_mock()
        review = _review(
            {"constraints": _acceptances(("K1", "age", "verified", "hard"))}
        )

        self._render(data, violations, settings, st_mock, review)

        assert _shown_table(st_mock)["KEY"].to_list() == ["K2"]

    def test_show_reviewed_shows_them_with_badge_and_reason(
        self, data, violations, settings
    ):
        st_mock = _st_mock(show_reviewed=True)
        review = _review(
            {"constraints": _acceptances(("K1", "age", "verified", "hard"))}
        )

        self._render(data, violations, settings, st_mock, review)

        table = _shown_table(st_mock)
        assert table.select("KEY", "review status", "review reason").rows() == [
            ("K1", "Reviewed", "verified"),
            ("K2", None, None),
        ]

    def test_show_reviewed_colours_reviewed_rows_green(
        self, data, violations, settings
    ):
        st_mock = _st_mock(show_reviewed=True)
        review = _review(
            {"constraints": _acceptances(("K1", "age", "verified", "hard"))}
        )

        self._render(data, violations, settings, st_mock, review)

        shown = st_mock.dataframe.call_args.args[0]
        assert isinstance(shown, Styler)
        # Styler.ctx maps (row, column) to the CSS properties applied to it.
        cell_styles = shown._compute().ctx
        styled_rows = {row for (row, _), props in cell_styles.items() if props}
        assert styled_rows == {0}
        assert all(
            prop == "background-color"
            for props in cell_styles.values()
            for prop, _ in props
        )

    def test_corrected_value_shows_highlighted_with_show_reviewed(
        self, data, violations, settings
    ):
        """K3 was corrected into range: no longer flagged, but reviewed."""
        st_mock = _st_mock(show_reviewed=True, flagged_only=False)
        review = _review(corrections=_acceptances(("K3", "age", "typo fixed")))

        self._render(data, violations, settings, st_mock, review)

        table = _shown_table(st_mock)
        assert table.filter(pl.col("KEY") == "K3").select(
            "review status", "review reason"
        ).rows() == [("Corrected", "typo fixed")]
        cell_styles = st_mock.dataframe.call_args.args[0]._compute().ctx
        styled_rows = {row for (row, _), props in cell_styles.items() if props}
        assert styled_rows == {2}
        review.processor.get_active_corrections.assert_called_with("survey", "KEY")

    def test_show_only_reviewed_lists_accepted_and_corrected_rows(
        self, data, violations, settings
    ):
        st_mock = _st_mock(reviewed_only=True)
        review = _review(
            {"constraints": _acceptances(("K1", "age", "verified", "hard"))},
            corrections=_acceptances(("K3", "age", "typo fixed")),
        )

        self._render(data, violations, settings, st_mock, review)

        table = _shown_table(st_mock)
        assert table.select("KEY", "review status").rows() == [
            ("K1", "Reviewed"),
            ("K3", "Corrected"),
        ]
        assert isinstance(st_mock.dataframe.call_args.args[0], Styler)

    def test_show_only_reviewed_disables_the_other_toggles(
        self, data, violations, settings
    ):
        st_mock = _st_mock(reviewed_only=True)

        self._render(data, violations, settings, st_mock, _review())

        disabled = {
            c.kwargs["key"]: c.kwargs.get("disabled", False)
            for c in st_mock.toggle.call_args_list
        }
        assert disabled == {
            "constraints_flagged_only": True,
            "constraints_show_reviewed": True,
            "constraints_reviewed_only": False,
        }

    def test_without_review_there_is_no_show_only_reviewed_toggle(
        self, data, violations, settings
    ):
        st_mock = _st_mock()

        self._render(data, violations, settings, st_mock, None)

        keys = [c.kwargs["key"] for c in st_mock.toggle.call_args_list]
        assert keys == ["constraints_flagged_only"]

    def test_without_show_reviewed_the_table_is_not_styled(
        self, data, violations, settings
    ):
        st_mock = _st_mock()
        review = _review(
            {"constraints": _acceptances(("K1", "age", "verified", "hard"))}
        )

        self._render(data, violations, settings, st_mock, review)

        assert not isinstance(st_mock.dataframe.call_args.args[0], Styler)

    def test_soft_acceptance_does_not_hide_a_hard_violation(
        self, data, violations, settings
    ):
        """K1 was accepted as a soft violation; bounds now make it hard."""
        st_mock = _st_mock()
        review = _review({"constraints": _acceptances(("K1", "age", "verified"))})

        self._render(data, violations, settings, st_mock, review)

        assert _shown_table(st_mock)["KEY"].to_list() == ["K1", "K2"]

    def test_outlier_acceptance_does_not_hide_a_constraint_violation(
        self, data, violations, settings
    ):
        st_mock = _st_mock()
        review = _review({"outliers": _acceptances(("K1", "age", "verified"))})

        self._render(data, violations, settings, st_mock, review)

        assert _shown_table(st_mock)["KEY"].to_list() == ["K1", "K2"]

    def test_flagged_only_toggle_is_on_by_default(self, data, violations, settings):
        st_mock = _st_mock()

        self._render(data, violations, settings, st_mock, _review())

        toggle_kwargs = {
            c.kwargs["key"]: c.kwargs for c in st_mock.toggle.call_args_list
        }
        assert toggle_kwargs["constraints_flagged_only"]["value"] is True

    def test_turning_flagged_only_off_shows_every_checked_value(
        self, data, violations, settings
    ):
        st_mock = _st_mock(flagged_only=False)

        self._render(data, violations, settings, st_mock, _review())

        table = _shown_table(st_mock)
        assert table.select("KEY", "violation type").rows() == [
            ("K1", "Hard Max"),
            ("K2", "Soft Max"),
            ("K3", None),
        ]

    def test_unflagged_rows_offer_a_review_button_too(self, data, violations, settings):
        st_mock = _st_mock(clicked=("constraints", 2), flagged_only=False)

        dialog = self._render(data, violations, settings, st_mock, _review())

        selection = dialog.call_args.args[2]
        assert selection.key_value == "K3"
        assert selection.flagged is False

    def test_flagged_only_toggle_works_without_review(self, data, violations, settings):
        st_mock = _st_mock(flagged_only=False)

        self._render(data, violations, settings, st_mock, None)

        assert _shown_table(st_mock)["KEY"].to_list() == ["K1", "K2", "K3"]

    def test_without_review_the_table_has_no_button(self, data, violations, settings):
        st_mock = _st_mock()

        self._render(data, violations, settings, st_mock, None)

        assert REVIEW_BUTTON_COL not in st_mock.dataframe.call_args.args[0].columns
        assert "column_config" not in st_mock.dataframe.call_args.kwargs


class TestOutlierTableReviewButton:
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
            patch(f"{MODULE}._flag_correction_dialog") as dialog,
            # styled_dataframe imports streamlit itself; forward to the mock.
            patch(
                f"{MODULE}.styled_dataframe",
                side_effect=lambda styler, **kw: st_mock.dataframe(styler, **kw),
            ),
        ):
            st_mock.selectbox.return_value = "age"
            _render_outlier_column_inspection(
                data, outliers, settings, "settings.json", review=review
            )
        return dialog

    def test_clicking_review_opens_the_dialog_for_outliers(
        self, data, outliers, settings
    ):
        st_mock = _st_mock(clicked=("outliers", 0))

        dialog = self._render(data, outliers, settings, st_mock, _review())

        selection = dialog.call_args.args[2]
        assert selection.key_value == "K1"
        assert selection.column == "age"
        assert selection.check_type == "outliers"
        assert selection.hard is False

    def test_index_is_hidden_like_the_constraint_table(self, data, outliers, settings):
        st_mock = _st_mock()

        self._render(data, outliers, settings, st_mock, _review())

        assert st_mock.dataframe.call_args.kwargs["hide_index"] is True

    def test_show_reviewed_keeps_values_as_displayed(self, data, outliers, settings):
        """Styling for "Show reviewed" must not turn 150 into 150.000000."""
        st_mock = _st_mock(show_reviewed=True, flagged_only=False)
        review = _review({"outliers": _acceptances(("K1", "age", "verified"))})

        self._render(data, outliers, settings, st_mock, review)

        styler = st_mock.dataframe.call_args.args[0]
        body = styler._translate(False, False)["body"]
        value_col = list(styler.data.columns).index("column value")
        assert [row[value_col + 1]["display_value"] for row in body] == [
            "150.0",
            "70.0",
            "30.0",
        ]

    def test_flagged_only_shows_only_outliers(self, data, outliers, settings):
        st_mock = _st_mock()

        self._render(data, outliers, settings, st_mock, _review())

        assert _shown_table(st_mock)["KEY"].to_list() == ["K1"]

    def test_turning_flagged_only_off_shows_every_checked_value(
        self, data, outliers, settings
    ):
        st_mock = _st_mock(flagged_only=False)

        self._render(data, outliers, settings, st_mock, _review())

        assert _shown_table(st_mock)["KEY"].to_list() == ["K1", "K2", "K3"]

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

    def test_numeric_keys_are_saved_with_their_native_type(self, settings):
        """The form shows KEY 7 as text, but validation compares native values."""
        numeric = pl.DataFrame({"KEY": [7, 8], "hhid": ["H7", "H8"], "age": [150, 30]})

        _, inputs, apply_entries = self._render(
            numeric,
            settings,
            _selection(key_value=7),
            _review(),
            _form_state(key_value="7", action=Action.MODIFY_VALUE, new_value="90"),
            apply=True,
            confirm=False,
        )

        assert inputs.call_args.args[2] == "7"
        assert inputs.call_args.kwargs["current_value"] == 150
        (entry,) = apply_entries.call_args.args[3]
        assert entry.key_value == 7

    def test_widget_keys_are_unique_per_cell(self, data, settings):
        """KEY "survey_1"/column "age" and KEY "survey"/column "1_age" differ."""
        namespaces = []
        for key, column in (("survey_1", "age"), ("survey", "1_age")):
            _, inputs, _ = self._render(
                data,
                settings,
                _selection(key_value=key, column=column),
                _review(),
                _form_state(key_value=key, column=column),
                apply=False,
                confirm=False,
            )
            namespaces.append(inputs.call_args.kwargs["key_namespace"])

        assert namespaces[0] != namespaces[1]

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
        self.processor = processor
        return constraint_metrics, table, outlier_metrics, inspection

    def test_constraint_metrics_do_not_count_accepted_violations(
        self, data, violations, outliers
    ):
        metrics, table, _, _ = self._run_report(
            data,
            violations,
            outliers,
            {"constraints": _acceptances(("K1", "age", "verified", "hard"))},
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

    def test_corrections_are_looked_up_once_per_report_run(
        self, data, violations, outliers
    ):
        self._run_report(data, violations, outliers, {})

        assert self.processor.get_active_corrections.call_count == 1
