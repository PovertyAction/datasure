"""Test the reapply_utils module."""

from unittest.mock import patch

from datasure.utils.reapply_utils import (
    ReapplyFailure,
    highlight_status,
    warn_reapply_failures,
)


class TestHighlightStatus:
    """Test the shared Change Log status-cell styling helper."""

    def test_failed_is_highlighted_red(self):
        style = highlight_status("Failed")
        assert "background-color" not in style
        assert "color: #dc3545" in style

    def test_successful_is_highlighted_green(self):
        style = highlight_status("Successful")
        assert "background-color" not in style
        assert "color: #198754" in style

    def test_unknown_status_is_not_highlighted(self):
        assert highlight_status("") == ""


class TestWarnReapplyFailures:
    """Test the shared bulk-reapply warning banner helper."""

    def test_no_op_when_no_failures(self):
        with patch("streamlit.warning") as mock_warning:
            warn_reapply_failures([], "Some steps could not be reapplied")
        mock_warning.assert_not_called()

    def test_renders_one_warning_summarizing_all_failures(self):
        failures = [
            ReapplyFailure(step="Remove columns [a, b]", reason="Columns not found"),
            ReapplyFailure(step="Modify value for key1", reason="Key not found"),
        ]
        with patch("streamlit.warning") as mock_warning:
            warn_reapply_failures(failures, "Some steps could not be reapplied")

        mock_warning.assert_called_once()
        message = mock_warning.call_args[0][0]
        assert "Some steps could not be reapplied" in message
        assert "2 skipped" in message
        assert "Remove columns [a, b]: Columns not found" in message
        assert "Modify value for key1: Key not found" in message
