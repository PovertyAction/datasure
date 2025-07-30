"""Tests for the CLI module."""

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from datasure.cli import get_version, main


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
    @patch("subprocess.run")
    @patch.object(Path, "exists", return_value=True)
    def test_main_default_args(
        self, mock_path_exists, mock_subprocess, mock_exit, mock_stcli_main
    ):
        """Test main function with default arguments."""
        original_argv = sys.argv[:]
        try:
            sys.argv = ["datasure"]
            main()

            # Verify subprocess.run was called with correct arguments
            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args[0][0]
            assert call_args[0] == "streamlit"
            assert call_args[1] == "run"
            assert "--server.address" in call_args
            assert "localhost" in call_args
            assert "--server.port" in call_args
            assert "8501" in call_args
            assert "--browser.gatherUsageStats" in call_args
            assert "false" in call_args

            # Verify stcli.main was called and sys.exit called with its return value
            mock_stcli_main.assert_called_once()
            mock_exit.assert_called_once_with(0)
        finally:
            sys.argv = original_argv

    @patch("datasure.cli.stcli.main", return_value=1)
    @patch("sys.exit")
    @patch("subprocess.run")
    @patch.object(Path, "exists", return_value=True)
    def test_main_custom_host_port(
        self, mock_path_exists, mock_subprocess, mock_exit, mock_stcli_main
    ):
        """Test main function with custom host and port."""
        original_argv = sys.argv[:]
        try:
            sys.argv = ["datasure", "--host", "0.0.0.0", "--port", "9000"]
            main()

            # Verify subprocess.run was called with custom host and port
            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args[0][0]
            assert "0.0.0.0" in call_args
            assert "9000" in call_args

            # Verify stcli.main was called and sys.exit called with its return value
            mock_stcli_main.assert_called_once()
            mock_exit.assert_called_once_with(1)
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

    @patch("datasure.cli.stcli.main", return_value=2)
    @patch("sys.exit")
    @patch("subprocess.run")
    @patch.object(Path, "exists", return_value=True)
    def test_main_stcli_nonzero_return(
        self, mock_path_exists, mock_subprocess, mock_exit, mock_stcli_main
    ):
        """Test main function when stcli.main returns non-zero exit code."""
        original_argv = sys.argv[:]
        try:
            sys.argv = ["datasure"]
            main()

            # Verify subprocess.run was called
            mock_subprocess.assert_called_once()

            # Verify stcli.main was called and sys.exit called with its return value
            mock_stcli_main.assert_called_once()
            mock_exit.assert_called_once_with(2)
        finally:
            sys.argv = original_argv

    @patch("datasure.cli.stcli.main", return_value=0)
    @patch("sys.exit")
    @patch("subprocess.run")
    @patch.object(Path, "exists", return_value=True)
    def test_main_app_path_construction(
        self, mock_path_exists, mock_subprocess, mock_exit, mock_stcli_main
    ):
        """Test that app.py path is constructed correctly."""
        original_argv = sys.argv[:]
        try:
            sys.argv = ["datasure"]
            main()

            # Verify subprocess.run was called with correct app path
            mock_subprocess.assert_called_once()
            call_args = mock_subprocess.call_args[0][0]
            app_path_arg = call_args[2]  # Third argument should be the app path
            assert app_path_arg.endswith("app.py")
        finally:
            sys.argv = original_argv
