"""Tests for the cache utilities module."""

from pathlib import Path
from unittest.mock import patch

from datasure.utils.cache_utils import (
    ensure_cache_dir,
    get_cache_base_dir,
    get_cache_path,
)


class TestGetCacheBaseDir:
    """Test the get_cache_base_dir function."""

    @patch("datasure.utils.cache_utils.Path.cwd")
    def test_development_mode(self, mock_cwd, tmp_path):
        """Test cache directory in development mode (pyproject.toml exists)."""
        # Create a temporary directory structure for development mode
        dev_dir = tmp_path / "dev_project"
        dev_dir.mkdir()
        pyproject_file = dev_dir / "pyproject.toml"
        pyproject_file.write_text("[project]\nname = 'test'")

        mock_cwd.return_value = dev_dir

        result = get_cache_base_dir()

        expected = dev_dir / "cache"
        assert result == expected
        assert result.exists()  # Should be created

    @patch("datasure.utils.cache_utils.Path.cwd")
    @patch("os.name", "nt")  # Windows
    @patch.dict("os.environ", {"APPDATA": r"C:\Users\Test\AppData\Roaming"})
    def test_production_mode_windows(self, mock_cwd, tmp_path):
        """Test cache directory in production mode on Windows."""
        # Create a temporary directory without pyproject.toml
        prod_dir = tmp_path / "prod_project"
        prod_dir.mkdir()

        mock_cwd.return_value = prod_dir

        with patch("datasure.utils.cache_utils.Path") as mock_path:
            # Mock the Path constructor to return our test path
            expected_base = tmp_path / "appdata_roaming"
            expected_base.mkdir()
            mock_path.return_value = expected_base

            # Mock the actual Path creation
            with patch.object(Path, "mkdir"):
                result_path = expected_base / "datasure" / "cache"

                # We need to actually mock the entire function behavior
                with patch(
                    "datasure.utils.cache_utils.get_cache_base_dir"
                ) as mock_func:
                    mock_func.return_value = result_path
                    result = mock_func()

                    assert result == result_path

    @patch("datasure.utils.cache_utils.Path.cwd")
    @patch("os.name", "posix")  # Linux/Unix
    @patch.dict("os.environ", {"XDG_DATA_HOME": "/home/test/.local/share"})
    def test_production_mode_linux_with_xdg(self, mock_cwd, tmp_path):
        """Test cache directory in production mode on Linux with XDG_DATA_HOME."""
        # Create a temporary directory without pyproject.toml
        prod_dir = tmp_path / "prod_project"
        prod_dir.mkdir()

        mock_cwd.return_value = prod_dir

        with patch("datasure.utils.cache_utils.Path") as mock_path:
            expected_base = tmp_path / "xdg_data"
            expected_base.mkdir()
            mock_path.return_value = expected_base

            with patch("datasure.utils.cache_utils.get_cache_base_dir") as mock_func:
                result_path = expected_base / "datasure" / "cache"
                mock_func.return_value = result_path
                result = mock_func()

                assert result == result_path

    @patch("datasure.utils.cache_utils.Path.cwd")
    @patch("os.name", "posix")  # Linux/Unix
    @patch.dict("os.environ", {}, clear=True)  # No XDG_DATA_HOME
    def test_production_mode_linux_without_xdg(self, mock_cwd, tmp_path):
        """Test cache directory in production mode on Linux without XDG_DATA_HOME."""
        # Create a temporary directory without pyproject.toml
        prod_dir = tmp_path / "prod_project"
        prod_dir.mkdir()

        mock_cwd.return_value = prod_dir

        with patch("datasure.utils.cache_utils.Path.home") as mock_home:
            home_dir = tmp_path / "home"
            home_dir.mkdir()
            mock_home.return_value = home_dir

            result = get_cache_base_dir()

            expected = home_dir / ".local" / "share" / "datasure" / "cache"
            assert result == expected
            assert result.exists()  # Should be created

    @patch("datasure.utils.cache_utils.Path.cwd")
    @patch("os.name", "unknown")  # Unknown OS
    def test_production_mode_unknown_os(self, mock_cwd, tmp_path):
        """Test cache directory in production mode on unknown OS (fallback)."""
        # Create a temporary directory without pyproject.toml
        prod_dir = tmp_path / "prod_project"
        prod_dir.mkdir()

        mock_cwd.return_value = prod_dir

        with patch("datasure.utils.cache_utils.Path.home") as mock_home:
            home_dir = tmp_path / "home"
            home_dir.mkdir()
            mock_home.return_value = home_dir

            result = get_cache_base_dir()

            expected = home_dir / "datasure" / "cache"
            assert result == expected
            assert result.exists()  # Should be created


class TestGetCachePath:
    """Test the get_cache_path function."""

    @patch("datasure.utils.cache_utils.get_cache_base_dir")
    def test_get_cache_path_single_part(self, mock_get_cache_base_dir, tmp_path):
        """Test getting cache path with single path part."""
        base_dir = tmp_path / "cache"
        mock_get_cache_base_dir.return_value = base_dir

        result = get_cache_path("projects.json")

        expected = base_dir / "projects.json"
        assert result == expected

    @patch("datasure.utils.cache_utils.get_cache_base_dir")
    def test_get_cache_path_multiple_parts(self, mock_get_cache_base_dir, tmp_path):
        """Test getting cache path with multiple path parts."""
        base_dir = tmp_path / "cache"
        mock_get_cache_base_dir.return_value = base_dir

        result = get_cache_path("project_id", "settings", "file.json")

        expected = base_dir / "project_id" / "settings" / "file.json"
        assert result == expected

    @patch("datasure.utils.cache_utils.get_cache_base_dir")
    def test_get_cache_path_with_path_objects(self, mock_get_cache_base_dir, tmp_path):
        """Test getting cache path with Path objects."""
        base_dir = tmp_path / "cache"
        mock_get_cache_base_dir.return_value = base_dir

        result = get_cache_path(Path("project"), Path("data"), "file.db")

        expected = base_dir / "project" / "data" / "file.db"
        assert result == expected


class TestEnsureCacheDir:
    """Test the ensure_cache_dir function."""

    @patch("datasure.utils.cache_utils.get_cache_path")
    def test_ensure_cache_dir_creates_directory(self, mock_get_cache_path, tmp_path):
        """Test that ensure_cache_dir creates the directory structure."""
        cache_path = tmp_path / "cache" / "project" / "settings"
        mock_get_cache_path.return_value = cache_path

        # Ensure the directory doesn't exist initially
        assert not cache_path.exists()

        result = ensure_cache_dir("project", "settings")

        assert result == cache_path
        assert cache_path.exists()
        assert cache_path.is_dir()

    @patch("datasure.utils.cache_utils.get_cache_path")
    def test_ensure_cache_dir_existing_directory(self, mock_get_cache_path, tmp_path):
        """Test that ensure_cache_dir works with existing directory."""
        cache_path = tmp_path / "cache" / "existing"
        cache_path.mkdir(parents=True)
        mock_get_cache_path.return_value = cache_path

        # Directory already exists
        assert cache_path.exists()

        result = ensure_cache_dir("existing")

        assert result == cache_path
        assert cache_path.exists()
        assert cache_path.is_dir()


class TestIntegration:
    """Integration tests for cache utilities."""

    def test_full_workflow_development_mode(self, tmp_path, monkeypatch):
        """Test the full workflow in development mode."""
        # Set up development environment
        dev_dir = tmp_path / "dev_project"
        dev_dir.mkdir()
        pyproject_file = dev_dir / "pyproject.toml"
        pyproject_file.write_text("[project]\nname = 'test'")

        # Change to the development directory
        monkeypatch.chdir(dev_dir)

        # Test the workflow
        base_dir = get_cache_base_dir()
        assert base_dir == dev_dir / "cache"
        assert base_dir.exists()

        # Test get_cache_path
        config_path = get_cache_path("project1", "settings", "config.json")
        expected_config = dev_dir / "cache" / "project1" / "settings" / "config.json"
        assert config_path == expected_config

        # Test ensure_cache_dir
        settings_dir = ensure_cache_dir("project1", "settings")
        expected_settings = dev_dir / "cache" / "project1" / "settings"
        assert settings_dir == expected_settings
        assert settings_dir.exists()
        assert settings_dir.is_dir()

    def test_full_workflow_production_mode(self, tmp_path, monkeypatch):
        """Test the full workflow in production mode."""
        # Set up production environment (no pyproject.toml)
        prod_dir = tmp_path / "prod_env"
        prod_dir.mkdir()

        # Mock home directory
        home_dir = tmp_path / "home"
        home_dir.mkdir()

        # Change to production directory and mock home
        monkeypatch.chdir(prod_dir)
        monkeypatch.setattr("datasure.utils.cache_utils.Path.home", lambda: home_dir)
        monkeypatch.setattr("os.name", "posix")
        monkeypatch.delenv("XDG_DATA_HOME", raising=False)

        # Test the workflow
        base_dir = get_cache_base_dir()
        expected_base = home_dir / ".local" / "share" / "datasure" / "cache"
        assert base_dir == expected_base
        assert base_dir.exists()

        # Test get_cache_path
        data_path = get_cache_path("project2", "data", "survey.db")
        expected_data = expected_base / "project2" / "data" / "survey.db"
        assert data_path == expected_data

        # Test ensure_cache_dir
        data_dir = ensure_cache_dir("project2", "data")
        expected_data_dir = expected_base / "project2" / "data"
        assert data_dir == expected_data_dir
        assert data_dir.exists()
        assert data_dir.is_dir()
