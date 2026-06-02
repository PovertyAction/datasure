"""Tests for the CLI module."""

import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest  # type: ignore

from datasure.cli import _SuppressStaticSyncRouteError, get_version, main


class TestSuppressStaticSyncRouteError:
    """Tests for the _SuppressStaticSyncRouteError logging filter."""

    def _make_record(self, exc_info=None):
        return logging.LogRecord(
            name="uvicorn.error",
            level=logging.ERROR,
            pathname="",
            lineno=0,
            msg="Exception in ASGI application",
            args=(),
            exc_info=exc_info,
        )

    def _exc_info_for(self, exc):
        return (type(exc), exc, None)

    def test_passes_record_without_exc_info(self):
        """Record with no exception info is not suppressed."""
        f = _SuppressStaticSyncRouteError()
        assert f.filter(self._make_record(exc_info=None)) is True

    def test_passes_non_os_error(self):
        """Record whose exception is not an OSError is not suppressed."""
        f = _SuppressStaticSyncRouteError()
        record = self._make_record(exc_info=self._exc_info_for(ValueError("nope")))
        assert f.filter(record) is True

    def test_passes_os_error_without_winerror_123(self):
        """OSError without winerror=123 is not suppressed."""
        f = _SuppressStaticSyncRouteError()
        record = self._make_record(exc_info=self._exc_info_for(OSError("generic")))
        assert f.filter(record) is True

    def test_passes_winerror_123_without_sync_in_path(self):
        """WinError 123 on a path that does not contain ':sync:' is not suppressed."""
        f = _SuppressStaticSyncRouteError()
        exc = OSError("bad path")
        exc.winerror = 123
        exc.filename = r"C:\some\other\path"
        assert f.filter(self._make_record(exc_info=self._exc_info_for(exc))) is True

    def test_suppresses_winerror_123_with_sync_path(self):
        """WinError 123 on a path containing ':sync:' is suppressed."""
        f = _SuppressStaticSyncRouteError()
        exc = OSError("bad path")
        exc.winerror = 123
        exc.filename = r"C:\path\to\streamlit\static\:sync:"
        assert f.filter(self._make_record(exc_info=self._exc_info_for(exc))) is False

    def test_passes_winerror_123_with_none_filename(self):
        """WinError 123 with None filename is not suppressed."""
        f = _SuppressStaticSyncRouteError()
        exc = OSError("bad path")
        exc.winerror = 123
        exc.filename = None
        assert f.filter(self._make_record(exc_info=self._exc_info_for(exc))) is True


class TestGetVersion:
    """Test the get_version function."""

    @patch("importlib.metadata.version")
    def test_get_version_success(self, mock_version):
        """Test get_version returns the correct version when metadata is available."""
        mock_version.return_value = "1.2.3"

        result = get_version()

        assert result == "1.2.3"
        mock_version.assert_called_once_with("DataSure")

    @patch("importlib.metadata.version")
    def test_get_version_fallback(self, mock_version):
        """Test get_version returns fallback version when metadata fails."""
        mock_version.side_effect = Exception("Module not found")

        result = get_version()

        assert result == "0.2.0"


class TestMain:
    """Test the main CLI function."""

    @patch("datasure.cli.stcli.main", return_value=0)
    @patch("sys.exit")
    @patch.object(Path, "exists", return_value=True)
    def test_main_default_args(self, mock_path_exists, mock_exit, mock_stcli_main):
        """Test main function with default arguments."""
        original_argv = sys.argv[:]
        try:
            sys.argv = ["datasure"]
            main()

            # Verify stcli.main was called
            mock_stcli_main.assert_called_once()
            mock_exit.assert_called_once_with(0)

            # Check that sys.argv was modified for streamlit
            assert sys.argv[0] == "streamlit"
            assert sys.argv[1] == "run"
            assert "--server.address" in sys.argv
            assert "localhost" in sys.argv
            assert "--server.port" in sys.argv
            assert "8501" in sys.argv
        finally:
            sys.argv = original_argv

    @patch("datasure.cli.stcli.main", return_value=0)
    @patch("sys.exit")
    @patch.object(Path, "exists", return_value=True)
    def test_main_custom_host_port(self, mock_path_exists, mock_exit, mock_stcli_main):
        """Test main function with custom host and port."""
        original_argv = sys.argv[:]
        try:
            sys.argv = ["datasure", "--host", "0.0.0.0", "--port", "9000"]
            main()

            # Verify stcli.main was called
            mock_stcli_main.assert_called_once()
            mock_exit.assert_called_once_with(0)

            # Check that custom host and port were used
            assert "0.0.0.0" in sys.argv
            assert "9000" in sys.argv
        finally:
            sys.argv = original_argv

    @patch("builtins.print")
    @patch.object(Path, "exists", return_value=False)
    def test_main_app_not_found(self, mock_path_exists, mock_print):
        """Test main function when app.py is not found."""
        original_argv = sys.argv[:]
        try:
            sys.argv = ["datasure"]
            with pytest.raises(SystemExit) as exc_info:
                main()

            # Check that error messages were printed
            assert mock_print.call_count == 2
            error_calls = [call[0][0] for call in mock_print.call_args_list]
            assert any("Error: Could not find app.py" in call for call in error_calls)
            assert any(
                "Make sure the package is installed properly" in call
                for call in error_calls
            )

            # Check that sys.exit was called with error code 1
            assert exc_info.value.code == 1
        finally:
            sys.argv = original_argv

    def test_main_version_flag(self):
        """Test main function with --version flag."""
        original_argv = sys.argv[:]
        try:
            sys.argv = ["datasure", "--version"]
            # The --version flag should cause argparse to exit
            with pytest.raises(SystemExit):
                main()
        finally:
            sys.argv = original_argv
