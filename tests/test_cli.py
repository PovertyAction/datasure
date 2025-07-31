"""Tests for the CLI module."""

import sys  # noqa: F401
from pathlib import Path  # noqa: F401
from unittest.mock import patch

from datasure.cli import get_version, main  # noqa: F401


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
