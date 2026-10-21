"""Progress, Missing Values and Summary keep their view filters in view state.

Filters, selections and sort order are personal view state: they are saved
under the check's ``view_state`` scope, left out of exports and templates,
and cleared by "Reset filters". Older versions saved them with the check's
settings; such a file still loads, and the values move to view state.
Configuration (targets, column mappings) stays with the check's settings.
"""

import json
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import polars as pl
import pytest

from datasure.checks import missing, progress, summary
from datasure.utils.view_state import ViewState, without_view_state


def _context() -> MagicMock:
    mock = MagicMock()
    mock.__enter__ = MagicMock(return_value=mock)
    mock.__exit__ = MagicMock(return_value=False)
    return mock


def _st() -> MagicMock:
    """A Streamlit mock whose widgets return their session value or default."""
    st = MagicMock()
    st.session_state = {}

    def widget(*args, **kwargs):
        key = kwargs["key"]
        if key in st.session_state:
            return st.session_state[key]
        if "index" in kwargs:
            options = list(kwargs.get("options", args[1] if len(args) > 1 else []))
            index = kwargs["index"]
            return None if index is None else options[index]
        return kwargs.get("default", kwargs.get("value"))

    for name in ("selectbox", "multiselect", "pills", "slider", "toggle"):
        setattr(st, name, MagicMock(side_effect=widget))
    st.columns.side_effect = lambda spec, **_: [
        _context() for _ in range(spec if isinstance(spec, int) else len(spec))
    ]
    st.container.return_value = _context()
    st.expander.return_value = _context()
    return st


@pytest.fixture
def settings_file(tmp_path):
    return tmp_path / "page_hfcs_settings.json"


def _write(path, settings: dict) -> None:
    path.write_text(json.dumps(settings))


def _read(path) -> dict:
    return json.loads(path.read_text())


def _run(module, st, render) -> None:
    with (
        patch.object(module, "st", st),
        patch.dict(sys.modules, {"streamlit": st}),
        patch("datasure.utils.onboarding_utils.is_demo_project", return_value=False),
    ):
        render()


def _change(st, widget: str, key: str, value) -> None:
    """The user changes a widget: its value is set and its callback runs."""
    call = next(c for c in getattr(st, widget).call_args_list if c.kwargs["key"] == key)
    st.session_state[key] = value
    with patch.dict(sys.modules, {"streamlit": st}):
        call.kwargs["on_change"](*call.kwargs.get("args", ()))


# --- Missing Values -------------------------------------------------------- #

MISSING_DATA = pl.DataFrame({"a": [0, 1], "b": [0, 0]})
CODES = pl.DataFrame(schema={"label": pl.Utf8, "codes": pl.Utf8})


def _missing_columns(st, settings_file) -> None:
    _run(
        missing,
        st,
        lambda: missing.missing_columns(MISSING_DATA, CODES, str(settings_file)),
    )


class TestMissingValues:
    def test_threshold_is_saved_as_view_state(self, settings_file):
        st = _st()
        _missing_columns(st, settings_file)

        _change(st, "slider", "mv_threshold", 40)

        assert ViewState(settings_file, "missing").values() == {"mv_threshold": 40}
        assert "mv_threshold" not in _read(settings_file).get("missing", {})

    def test_an_old_settings_file_still_loads_and_moves_to_view_state(
        self, settings_file
    ):
        _write(settings_file, {"missing": {"mv_threshold": 25, "other": 1}})
        st = _st()

        _missing_columns(st, settings_file)

        assert st.session_state["mv_threshold"] == 25
        assert ViewState(settings_file, "missing").values() == {"mv_threshold": 25}
        # Out of the check settings, so exports and templates leave it out.
        assert without_view_state(_read(settings_file)) == {"missing": {"other": 1}}

    def test_reset_filters_returns_to_the_default(self, settings_file):
        _write(settings_file, {"missing": {"mv_threshold": 25}})
        _missing_columns(_st(), settings_file)

        ViewState(settings_file, "missing").reset()
        st = _st()
        _missing_columns(st, settings_file)

        assert "mv_threshold" not in st.session_state
        assert st.slider.call_args.kwargs["value"] == 0


# --- Progress -------------------------------------------------------------- #


class TestProgress:
    def test_an_old_time_period_still_loads_and_moves_to_view_state(
        self, settings_file
    ):
        _write(settings_file, {"progress": {"time_period": "Week", "target": 300}})
        st = _st()

        _run(
            progress,
            st,
            lambda: progress.render_time_period_selector(
                str(settings_file), progress.TAB_NAME
            ),
        )

        assert st.session_state["time_period_progress_overtime"] == "Week"
        assert ViewState(settings_file, "progress").values() == {
            "time_period_progress_overtime": "Week"
        }
        # The target is configuration: it stays with the check settings.
        assert _read(settings_file)["progress"] == {"target": 300}

    def test_a_new_time_period_is_view_state(self, settings_file):
        st = _st()
        render = lambda: progress.render_time_period_selector(  # noqa: E731
            str(settings_file), progress.TAB_NAME
        )
        _run(progress, st, render)

        _change(st, "pills", "time_period_progress_overtime", "Month")

        assert ViewState(settings_file, "progress").values() == {
            "time_period_progress_overtime": "Month"
        }
        assert "progress" not in _read(settings_file)


# --- Summary --------------------------------------------------------------- #


class TestSummary:
    def test_old_progress_by_selections_still_load(self, settings_file):
        _write(
            settings_file,
            {
                "summary": {
                    "progress_by_col": "region",
                    "progress_time_period": "Weekly",
                    "target": 100,
                }
            },
        )
        st = _st()
        data = pd.DataFrame(
            {"region": ["A", "B"], "date": pd.date_range("2024-01-01", periods=2)}
        )

        with patch.object(
            summary,
            "compute_summary_progress_by_col",
            return_value=(pd.DataFrame({"region": ["A"]}), 0, 1, []),
        ) as compute:
            _run(
                summary,
                st,
                # Unwrapped from @st.fragment, which needs a running app.
                lambda: summary._render_progress_by_column.__wrapped__(
                    data, "date", str(settings_file)
                ),
            )

        assert compute.call_args.kwargs["progress_by_col"] == "region"
        assert compute.call_args.kwargs["progress_time_period"] == "Weekly"
        assert ViewState(settings_file, "summary").values() == {
            "progress_by_col_key": "region",
            "summary_progress_time_period_pill": "Weekly",
        }
        assert _read(settings_file)["summary"] == {"target": 100}
