"""Tests for the shared correction form component."""

import sys
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock

import polars as pl

from datasure.processing.corrections import CorrectionEntry
from datasure.utils.correction_form import (
    apply_correction_entries,
    get_current_value,
    parse_date_value,
    render_correction_form,
    render_correction_inputs,
)

_st = sys.modules["streamlit"]

_DATA = pl.DataFrame(
    {"KEY": ["k1", "k2"], "age": [25, 99], "lat": [5.6, 5.7], "lon": [-0.1, -0.2]}
)


@contextmanager
def _widgets(values: dict[str, Any]):
    """Mock the form's widgets, answering each by its widget key.

    `values` maps a widget key to what the widget returns. Unlisted
    selectboxes return their first option, text inputs "", buttons False.
    Yields the mocks, which keep their recorded calls after the block exits.
    """
    names = ("selectbox", "text_input", "button", "write", "warning", "error")
    names += ("success", "rerun", "date_input")
    originals = {name: getattr(_st, name) for name in names}

    def selectbox(label, options, key, **kwargs):
        return values.get(key, next(iter(options)) if options else None)

    def text_input(label, key, **kwargs):
        return values.get(key, "")

    def button(label, key, **kwargs):
        return values.get(key, False)

    mocks = SimpleNamespace(
        selectbox=MagicMock(side_effect=selectbox),
        text_input=MagicMock(side_effect=text_input),
        button=MagicMock(side_effect=button),
        **{
            name: MagicMock()
            for name in ("write", "warning", "error", "success", "rerun", "date_input")
        },
    )
    try:
        for name in names:
            setattr(_st, name, getattr(mocks, name))
        yield mocks
    finally:
        for name, value in originals.items():
            setattr(_st, name, value)


def _widget_keys(mock: MagicMock) -> list[str]:
    return [c.kwargs["key"] for c in mock.call_args_list]


class TestRenderCorrectionInputs:
    """The inputs collect one entry for a prefilled or chosen target."""

    def test_prefilled_column_skips_the_column_selector(self):
        with _widgets(
            {
                "correction_action_outliers_0": "modify value",
                "correction_new_value_outliers_0": "30",
                "correction_reason_outliers_0": "typo",
            }
        ) as st:
            state = render_correction_inputs(
                _DATA,
                "KEY",
                "k2",
                key_namespace="outliers_0",
                column="age",
                current_value=99,
            )

        assert "correction_col_to_modify_outliers_0" not in _widget_keys(st.selectbox)
        assert state.to_entry() == CorrectionEntry(
            key_value="k2",
            action="modify value",
            column="age",
            current_value=99,
            new_value="30",
            reason="typo",
        )

    def test_current_value_is_looked_up_when_only_the_column_is_given(self):
        with _widgets({"correction_action_x": "remove value"}):
            state = render_correction_inputs(
                _DATA, "KEY", "k2", key_namespace="x", column="age"
            )

        assert state.current_value == 99

    def test_offers_only_the_allowed_actions(self):
        with _widgets({}) as st:
            render_correction_inputs(
                _DATA,
                "KEY",
                "k2",
                key_namespace="x",
                column="age",
                actions=("accept", "modify value"),
                check_type="outliers",
            )

        (action_call,) = [
            c
            for c in st.selectbox.call_args_list
            if c.kwargs["key"] == "correction_action_x"
        ]
        assert list(action_call.kwargs["options"]) == ["accept", "modify value"]

    def test_widget_keys_are_namespaced(self):
        with _widgets({"correction_action_a": "modify value"}) as st:
            render_correction_inputs(_DATA, "KEY", "k1", key_namespace="a")
        keys_a = _widget_keys(st.selectbox) + _widget_keys(st.text_input)

        with _widgets({"correction_action_b": "modify value"}) as st:
            render_correction_inputs(_DATA, "KEY", "k1", key_namespace="b")
        keys_b = _widget_keys(st.selectbox) + _widget_keys(st.text_input)

        assert keys_a
        assert not set(keys_a) & set(keys_b)

    def test_accept_entry_carries_the_check_type(self):
        with _widgets(
            {"correction_action_x": "accept", "correction_reason_x": "verified"}
        ):
            state = render_correction_inputs(
                _DATA,
                "KEY",
                "k2",
                key_namespace="x",
                column="age",
                current_value=99,
                actions=("accept",),
                check_type="outliers",
            )

        assert state.to_entry() == CorrectionEntry(
            key_value="k2",
            action="accept",
            column="age",
            current_value=99,
            reason="verified",
            check_type="outliers",
        )

    def test_gps_accept_keeps_the_coordinate_pair(self):
        with _widgets(
            {"correction_action_x": "accept", "correction_reason_x": "moved"}
        ) as st:
            state = render_correction_inputs(
                _DATA,
                "KEY",
                "k1",
                key_namespace="x",
                current_value={"lat": 5.6, "lon": -0.1},
                actions=("accept",),
                check_type="gps",
            )

        assert "correction_col_to_modify_x" not in _widget_keys(st.selectbox)
        assert state.column is None
        assert state.current_value == {"lat": 5.6, "lon": -0.1}


class TestRenderCorrectionForm:
    """The form applies its entry atomically, tagged with its source."""

    def _render(self, processor, values, **overrides):
        kwargs = dict(
            correction_processor=processor,
            alias="survey",
            key_col="KEY",
            data=_DATA,
            key_value="k2",
            key_namespace="x",
            source="outliers",
            column="age",
            current_value=99,
            actions=("accept", "modify value"),
            check_type="outliers",
        )
        kwargs.update(overrides)
        with _widgets(values) as st:
            render_correction_form(**kwargs)
            return st

    def test_apply_saves_the_entry_with_the_source(self):
        processor = MagicMock()

        st = self._render(
            processor,
            {
                "correction_action_x": "accept",
                "correction_reason_x": "verified",
                "correction_apply_x": True,
            },
        )

        processor.apply_corrections.assert_called_once()
        kwargs = processor.apply_corrections.call_args.kwargs
        assert kwargs["source"] == "outliers"
        assert kwargs["entries"][0].action == "accept"
        assert st.rerun.called

    def test_apply_is_disabled_without_a_reason(self):
        processor = MagicMock()

        st = self._render(processor, {"correction_action_x": "accept"})

        (apply_call,) = [
            c
            for c in st.button.call_args_list
            if c.kwargs["key"] == "correction_apply_x"
        ]
        assert apply_call.kwargs["disabled"] is True
        processor.apply_corrections.assert_not_called()

    def test_on_apply_replaces_the_default_save(self):
        processor = MagicMock()
        submitted = []

        self._render(
            processor,
            {
                "correction_action_x": "accept",
                "correction_reason_x": "verified",
                "correction_apply_x": True,
            },
            on_apply=submitted.append,
        )

        assert [s.action for s in submitted] == ["accept"]
        processor.apply_corrections.assert_not_called()


class TestApplyCorrectionEntries:
    """Several entries are saved in one all-or-nothing call."""

    _ENTRIES = (
        CorrectionEntry(key_value="k1", action="remove row", reason="dup"),
        CorrectionEntry(
            key_value="k2",
            action="modify value",
            column="age",
            new_value="30",
            reason="dup",
        ),
    )

    def test_saves_every_entry_in_one_call(self):
        processor = MagicMock()

        with _widgets({}) as st:
            ok = apply_correction_entries(
                processor, "survey", "KEY", self._ENTRIES, source="duplicates"
            )

        assert ok is True
        processor.apply_corrections.assert_called_once_with(
            alias="survey",
            key_col="KEY",
            entries=list(self._ENTRIES),
            source="duplicates",
        )
        assert st.success.called

    def test_reports_an_invalid_entry_and_saves_nothing(self):
        processor = MagicMock()
        processor.apply_corrections.side_effect = ValueError("Column 'x' not found")

        with _widgets({}) as st:
            ok = apply_correction_entries(
                processor, "survey", "KEY", self._ENTRIES, source="duplicates"
            )
            message = st.error.call_args.args[0]

        assert ok is False
        assert "Column 'x' not found" in message
        assert not st.success.called


class TestFormErrorLogging:
    """Failures are logged, not swallowed."""

    def test_failed_apply_logs_the_traceback(self, caplog):
        processor = MagicMock()
        processor.apply_corrections.side_effect = OSError("disk full")

        with _widgets({}), caplog.at_level("ERROR"):
            apply_correction_entries(
                processor,
                "survey",
                "KEY",
                [CorrectionEntry(key_value="k1", action="remove row", reason="dup")],
                source="duplicates",
            )

        (record,) = [r for r in caplog.records if r.levelname == "ERROR"]
        assert record.exc_info is not None

    def test_missing_lookup_is_logged_before_returning_none(self, caplog):
        with caplog.at_level("DEBUG"):
            value = get_current_value(_DATA, "KEY", "k1", "no_such_column")

        assert value is None
        assert any("no_such_column" in r.getMessage() for r in caplog.records)

    def test_unparseable_date_is_logged_before_returning_none(self, caplog):
        with caplog.at_level("DEBUG"):
            value = parse_date_value("not-a-date")

        assert value is None
        assert any("not-a-date" in r.getMessage() for r in caplog.records)
