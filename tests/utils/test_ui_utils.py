"""Tests for the shared UI helpers module."""

import sys
from unittest.mock import MagicMock

import pytest

from datasure.utils.ui_utils import (
    confirm_dialog,
    metric_row,
    page_header,
    queue_notice,
    section_header,
    show_queued_notices,
)


@pytest.fixture
def mock_st():
    """Install a mock streamlit in sys.modules for the duration of a test.

    The ui_utils helpers import streamlit at call time, so replacing the
    module here makes them use the mock.
    """
    original = sys.modules.get("streamlit")
    st = MagicMock()
    sys.modules["streamlit"] = st
    try:
        yield st
    finally:
        if original is not None:
            sys.modules["streamlit"] = original
        else:  # pragma: no cover - streamlit is always importable in tests
            del sys.modules["streamlit"]


class TestPageHeader:
    """Test the page_header function."""

    def test_title_only(self, mock_st):
        """Title renders; no caption when subtitle omitted; divider by default."""
        page_header("Import Data")

        mock_st.title.assert_called_once_with("Import Data")
        mock_st.caption.assert_not_called()
        mock_st.divider.assert_called_once()

    def test_title_with_subtitle(self, mock_st):
        """Subtitle renders as a caption."""
        page_header("Prepare Data", "Clean and reshape your data.")

        mock_st.title.assert_called_once_with("Prepare Data")
        mock_st.caption.assert_called_once_with("Clean and reshape your data.")

    def test_divider_can_be_disabled(self, mock_st):
        """No divider when divider=False."""
        page_header("Correct Data", divider=False)

        mock_st.divider.assert_not_called()


class TestSectionHeader:
    """Test the section_header function."""

    def test_plain_label(self, mock_st):
        """Plain text label renders as a subheader without an icon."""
        section_header("Change Log")

        mock_st.subheader.assert_called_once_with("Change Log")

    def test_icon_prefixed_label(self, mock_st):
        """Icon shortcode is prefixed to the label."""
        section_header("Manage Credentials", icon=":material/key:")

        mock_st.subheader.assert_called_once_with(":material/key: Manage Credentials")


class TestMetricRow:
    """Test the metric_row function."""

    def test_equal_width_bordered_columns(self, mock_st):
        """Columns are created equal-width with borders, one per metric."""
        cols = [MagicMock(), MagicMock(), MagicMock()]
        mock_st.columns.return_value = cols

        metric_row([("Rows", 100), ("Columns", 12), ("Missing", 3)])

        mock_st.columns.assert_called_once_with(3, border=True)

    def test_metric_values_and_help(self, mock_st):
        """Each metric renders label, value, and optional help text."""
        cols = [MagicMock(), MagicMock()]
        mock_st.columns.return_value = cols

        metric_row([("Rows", 100), ("Missing", 3, "Missing cells")])

        cols[0].metric.assert_called_once_with("Rows", 100, help=None)
        cols[1].metric.assert_called_once_with("Missing", 3, help="Missing cells")


class TestConfirmDialog:
    """Test the confirm_dialog function."""

    @staticmethod
    def _passthrough_dialog(mock_st):
        """Make @st.dialog(title) a no-op decorator so the body runs."""
        mock_st.dialog.return_value = lambda fn: fn

    def test_dialog_registered_with_title(self, mock_st):
        """st.dialog is invoked with the provided title."""
        self._passthrough_dialog(mock_st)
        mock_st.columns.return_value = [MagicMock(), MagicMock()]
        mock_st.button.return_value = False

        confirm_dialog(
            "Delete project", "This cannot be undone.", on_confirm=lambda: None
        )

        mock_st.dialog.assert_called_once_with("Delete project")

    def test_danger_shows_warning(self, mock_st):
        """Danger dialogs render the body as a warning callout."""
        self._passthrough_dialog(mock_st)
        mock_st.columns.return_value = [MagicMock(), MagicMock()]
        mock_st.button.return_value = False

        confirm_dialog("Restart demo", "Progress is lost.", on_confirm=lambda: None)

        mock_st.warning.assert_called_once()
        assert mock_st.warning.call_args[0][0] == "Progress is lost."

    def test_non_danger_shows_plain_text(self, mock_st):
        """Non-danger dialogs render the body as plain text."""
        self._passthrough_dialog(mock_st)
        mock_st.columns.return_value = [MagicMock(), MagicMock()]
        mock_st.button.return_value = False

        confirm_dialog(
            "Proceed?", "Continue with export.", on_confirm=lambda: None, danger=False
        )

        mock_st.write.assert_called_once_with("Continue with export.")
        mock_st.warning.assert_not_called()

    def test_confirm_button_runs_callback_and_reruns(self, mock_st):
        """Clicking confirm invokes on_confirm then reruns to dismiss."""
        self._passthrough_dialog(mock_st)
        mock_st.columns.return_value = [MagicMock(), MagicMock()]
        # confirm clicked, cancel not
        mock_st.button.side_effect = [True, False]
        callback = MagicMock()

        confirm_dialog("Delete", "Gone forever.", on_confirm=callback)

        callback.assert_called_once_with()
        mock_st.rerun.assert_called_once()

    def test_cancel_button_reruns_without_callback(self, mock_st):
        """Clicking cancel reruns without invoking on_confirm."""
        self._passthrough_dialog(mock_st)
        mock_st.columns.return_value = [MagicMock(), MagicMock()]
        # confirm not clicked, cancel clicked
        mock_st.button.side_effect = [False, True]
        callback = MagicMock()

        confirm_dialog("Delete", "Gone forever.", on_confirm=callback)

        callback.assert_not_called()
        mock_st.rerun.assert_called_once()

    def test_custom_button_labels(self, mock_st):
        """Custom confirm/cancel labels are forwarded to the buttons."""
        self._passthrough_dialog(mock_st)
        mock_st.columns.return_value = [MagicMock(), MagicMock()]
        mock_st.button.return_value = False

        confirm_dialog(
            "Delete",
            "Gone forever.",
            on_confirm=lambda: None,
            confirm_label="Yes, delete",
            cancel_label="Keep it",
        )

        labels = [c.args[0] for c in mock_st.button.call_args_list]
        assert "Yes, delete" in labels
        assert "Keep it" in labels


class TestQueuedNotices:
    """Notices queued before a rerun are shown once on the next run."""

    @pytest.fixture
    def st_with_state(self, mock_st):
        mock_st.session_state = {}
        return mock_st

    def test_shows_notices_in_queue_order_at_their_level(self, st_with_state):
        queue_notice("prep_survey", "success", "Step added")
        queue_notice("prep_survey", "warning", "Some skipped")
        queue_notice("prep_survey", "error", "Rebuild failed")

        show_queued_notices("prep_survey")

        st_with_state.success.assert_called_once_with("Step added")
        st_with_state.warning.assert_called_once_with("Some skipped")
        st_with_state.error.assert_called_once_with("Rebuild failed")

    def test_notices_are_shown_only_once(self, st_with_state):
        queue_notice("prep_survey", "success", "Step added")

        show_queued_notices("prep_survey")
        show_queued_notices("prep_survey")

        st_with_state.success.assert_called_once()

    def test_notices_are_scoped(self, st_with_state):
        queue_notice("prep_survey", "success", "Step added")

        show_queued_notices("prep_other")

        st_with_state.success.assert_not_called()

    def test_showing_with_nothing_queued_is_a_no_op(self, st_with_state):
        show_queued_notices("prep_survey")

        st_with_state.success.assert_not_called()
        st_with_state.warning.assert_not_called()
        st_with_state.error.assert_not_called()
