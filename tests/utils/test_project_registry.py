"""Tests for utils/project_registry.py: atomic writes and locked updates."""

import json
import threading
from unittest.mock import patch

import pytest

from datasure.utils import project_registry
from datasure.utils.project_registry import read_registry, update_registry


@pytest.fixture
def registry(tmp_path):
    return tmp_path / "projects.json"


def _add(project_id, info):
    def mutate(projects):
        projects[project_id] = info
        return True

    return mutate


class TestReadRegistry:
    def test_missing_file_returns_empty(self, registry):
        assert read_registry(registry) == {}

    def test_reads_file(self, registry):
        registry.write_text(json.dumps({"a": {"name": "A"}}))
        assert read_registry(registry) == {"a": {"name": "A"}}

    def test_corrupt_file_returns_empty_and_is_left_alone(self, registry):
        registry.write_text('{"a": {"na')
        assert read_registry(registry) == {}
        assert registry.read_text() == '{"a": {"na'


class TestUpdateRegistry:
    def test_creates_registry(self, registry):
        assert update_registry(registry, _add("a", {"name": "A"})) is True
        assert json.loads(registry.read_text()) == {"a": {"name": "A"}}

    def test_unchanged_does_not_write(self, registry):
        registry.write_text('{"a": {}}')
        before = registry.stat().st_mtime_ns
        assert update_registry(registry, lambda projects: False) is False
        assert registry.stat().st_mtime_ns == before
        assert registry.read_text() == '{"a": {}}'

    def test_failed_write_keeps_previous_registry(self, registry):
        registry.write_text(json.dumps({"a": {"name": "A"}}))

        def dump_then_fail(obj, f, **kwargs):
            f.write('{"a": {"na')  # partial output, then the disk fills up
            raise OSError("No space left on device")

        with (
            patch.object(project_registry.json, "dump", side_effect=dump_then_fail),
            pytest.raises(OSError, match="No space"),
        ):
            update_registry(registry, _add("b", {"name": "B"}))

        assert json.loads(registry.read_text()) == {"a": {"name": "A"}}
        leftovers = [p.name for p in registry.parent.iterdir()]
        assert sorted(leftovers) == ["projects.json", "projects.json.lock"]

    def test_corrupt_registry_is_moved_aside_on_write(self, registry):
        registry.write_text('{"a": {"na')
        update_registry(registry, _add("b", {"name": "B"}))
        assert json.loads(registry.read_text()) == {"b": {"name": "B"}}
        corrupt = registry.with_name("projects.json.corrupt")
        assert corrupt.read_text() == '{"a": {"na'

    def test_lock_released_after_mutator_raises(self, registry):
        def boom(projects):
            raise RuntimeError("bug")

        with pytest.raises(RuntimeError):
            update_registry(registry, boom)
        # A second update would block (or time out on Windows) if the lock leaked.
        assert update_registry(registry, _add("a", {})) is True

    def test_concurrent_updates_are_not_lost(self, registry):
        """Each thread adds its own entries; none may be overwritten by another."""
        n_threads, per_thread = 8, 10
        errors = []

        def worker(t):
            try:
                for i in range(per_thread):
                    update_registry(registry, _add(f"t{t}_{i}", {"n": i}))
            except Exception as e:  # pragma: no cover - surfaced below
                errors.append(e)

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(n_threads)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()

        assert errors == []
        assert len(read_registry(registry)) == n_threads * per_thread
