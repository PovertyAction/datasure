"""Cache directory utilities for DataSure."""

import os
from pathlib import Path


def get_cache_base_dir() -> Path:
    """Get the base cache directory path.

    Returns the cache directory path, creating it if it doesn't exist.
    When running as an installed package, this will be in a user data directory.
    When running from development, this will be in the project root.

    Returns
    -------
    Path
        The base cache directory path.
    """
    # Check if we're running from a development environment
    # (project root has pyproject.toml)
    current_dir = Path.cwd()

    # Look for pyproject.toml to determine if we're in development mode
    pyproject_path = current_dir / "pyproject.toml"

    if pyproject_path.exists():
        # Development mode - use cache in project root
        cache_dir = current_dir / "cache"
    else:
        os_name = os.name
        # Production mode - use user data directory
        if os_name == "nt":  # Windows
            base_dir = Path(
                os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming")
            )
        elif os_name == "posix":  # Unix/Linux/macOS
            # Use XDG Base Directory specification
            xdg_data_home = os.environ.get("XDG_DATA_HOME")
            if xdg_data_home:
                base_dir = Path(xdg_data_home)
            else:
                base_dir = Path.home() / ".local" / "share"
        else:
            # Fallback to home directory
            base_dir = Path.home()

        cache_dir = base_dir / "datasure" / "cache"

    # Create the cache directory if it doesn't exist
    cache_dir.mkdir(parents=True, exist_ok=True)

    return cache_dir


def get_cache_path(*path_parts: str | Path) -> Path:
    """Get a path within the cache directory.

    Parameters
    ----------
    *path_parts : Union[str, Path]
        Path components to join with the cache directory.

    Returns
    -------
    Path
        The full path within the cache directory.

    Examples
    --------
    >>> get_cache_path("projects.json")
    Path("/path/to/cache/projects.json")

    >>> get_cache_path("project_id", "settings", "file.json")
    Path("/path/to/cache/project_id/settings/file.json")
    """
    cache_base = get_cache_base_dir()
    return cache_base.joinpath(*path_parts)


def ensure_cache_dir(*path_parts: str | Path) -> Path:
    """Ensure a directory exists within the cache directory.

    Parameters
    ----------
    *path_parts : Union[str, Path]
        Path components to join with the cache directory.

    Returns
    -------
    Path
        The full path within the cache directory (created if it didn't exist).
    """
    cache_path = get_cache_path(*path_parts)
    cache_path.mkdir(parents=True, exist_ok=True)
    return cache_path


# Marker a host (e.g. a multi-user deployment) drops into a project's
# settings folder when the project is opened read-only, for example because
# another user holds its write lock. DataSure never writes it.
READ_ONLY_MARKER = ".readonly"
_READ_ONLY_DEFAULT = "This project is open read-only. Changes will not be saved."
_READ_ONLY_MAX_CHARS = 300


def read_only_reason(project_id: str) -> str | None:
    """Return why a project is read-only, or None if it is writable.

    The reason is the marker file's text (trimmed); an empty marker gives a
    generic message. An unreadable marker counts as not read-only so a stray
    file can never block the app.
    """
    if not project_id:
        return None
    marker = get_cache_path(project_id, "settings", READ_ONLY_MARKER)
    try:
        if not marker.is_file():
            return None
        text = marker.read_text(encoding="utf-8").strip()
    except (OSError, UnicodeDecodeError):
        return None
    return text[:_READ_ONLY_MAX_CHARS] or _READ_ONLY_DEFAULT
