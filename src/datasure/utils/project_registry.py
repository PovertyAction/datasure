"""Safe reads and writes of the project registry (``cache/projects.json``).

Two guarantees, for every caller that goes through this module:

- **No torn writes.** The new registry is written to a temp file in the same
  directory and swapped in with ``os.replace``, so a failed write (disk full,
  I/O error on a synced cache) leaves the previous registry intact instead of
  an empty or half-written file.
- **No lost updates.** Reads and read-modify-write updates hold an exclusive
  OS lock on a sidecar ``<registry>.lock`` file, so two sessions sharing one
  cache (for example several browser tabs) can't overwrite each other's
  changes. The OS releases the lock if its holder dies, so a crash never
  leaves the registry stuck.

The lock is not reentrant: never call :func:`read_registry` or
:func:`update_registry` from inside an ``update_registry`` mutator.

Callers pass the registry path (normally ``get_cache_path("projects.json")``)
so this module never decides on its own where the cache lives.
"""

import contextlib
import json
import logging
import os
import sys
import tempfile
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path

if sys.platform == "win32":
    import msvcrt
else:
    import fcntl

logger = logging.getLogger(__name__)


def _lock_path(projects_file: Path) -> Path:
    return projects_file.with_name(projects_file.name + ".lock")


def _corrupt_path(projects_file: Path) -> Path:
    return projects_file.with_name(projects_file.name + ".corrupt")


@contextlib.contextmanager
def _registry_lock(projects_file: Path) -> Iterator[None]:
    """Hold an exclusive cross-process lock on the registry.

    On Windows, ``msvcrt.locking`` retries for about 10 seconds and then
    raises ``OSError``. On POSIX, ``flock`` waits until the lock is free.
    """
    lock_file = _lock_path(projects_file)
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_file, "a+b") as fh:
        fd = fh.fileno()
        if sys.platform == "win32":
            fh.seek(0)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            try:
                yield
            finally:
                fh.seek(0)
                msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd, fcntl.LOCK_UN)


def _read_unlocked(projects_file: Path) -> dict:
    """Return the registry; raise ``json.JSONDecodeError`` if it is corrupt."""
    if not projects_file.exists():
        return {}
    with open(projects_file) as f:
        return json.load(f)


def _write_atomic(projects_file: Path, projects: dict) -> None:
    """Replace the registry file in one step; the caller holds the lock."""
    fd, tmp_name = tempfile.mkstemp(
        dir=projects_file.parent, prefix=f".{projects_file.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(projects, f, indent=4)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp_name, projects_file)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp_name)
        raise


def read_registry(projects_file: Path) -> dict:
    """Return the registry, or ``{}`` if it is missing or corrupt.

    A corrupt registry is logged, not raised, so the home page still renders.
    The next update moves the corrupt file aside (see :func:`update_registry`).
    """
    if not projects_file.exists():
        return {}  # nothing to read; don't create a lock file just to look
    try:
        with _registry_lock(projects_file):
            return _read_unlocked(projects_file)
    except json.JSONDecodeError:
        logger.exception("Project registry %s is corrupt", projects_file)
        return {}


def update_registry(projects_file: Path, mutate: Callable[[dict], bool]) -> bool:
    """Apply ``mutate`` to the registry under the lock and save it.

    ``mutate`` changes the dict in place and returns ``True`` if it changed
    anything; the registry is written only then. Returns what ``mutate``
    returned.

    If the existing registry is corrupt, ``mutate`` starts from ``{}`` and,
    before the new registry is written, the corrupt file is kept as
    ``<registry>.corrupt`` so it can be recovered by hand.
    """
    with _registry_lock(projects_file):
        corrupt = False
        try:
            projects = _read_unlocked(projects_file)
        except json.JSONDecodeError:
            logger.exception("Project registry %s is corrupt", projects_file)
            corrupt = True
            projects = {}

        changed = mutate(projects)
        if changed:
            if corrupt:
                os.replace(projects_file, _corrupt_path(projects_file))
                logger.warning(
                    "Moved corrupt project registry to %s",
                    _corrupt_path(projects_file),
                )
            _write_atomic(projects_file, projects)
        return changed


def stamp_last_used(projects_file: Path, project_id: str) -> bool:
    """Record now as ``last_used`` for a registered project.

    Returns ``False``, leaving the registry untouched, if ``project_id`` is
    not registered.
    """

    def _stamp(projects: dict) -> bool:
        if project_id not in projects:
            return False
        projects[project_id]["last_used"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return True

    return update_registry(projects_file, _stamp)
