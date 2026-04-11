"""Tests for advisory_lock: file-level locking for scaffold operations."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import textwrap
import threading
from pathlib import Path  # noqa: TC003 - used at runtime in _tmp_path()
from uuid import uuid4

import pytest

from tests.constants import PROJECT_ROOT
from vaultspec_core.core.helpers import advisory_lock


def _tmp_path() -> Path:
    p = PROJECT_ROOT / ".pytest-tmp" / f"lock-{uuid4().hex}"
    p.mkdir(parents=True, exist_ok=True)
    return p


@pytest.mark.unit
class TestAdvisoryLock:
    def test_creates_lock_file(self):
        root = _tmp_path()
        target = root / "test.json"
        target.write_text("{}")

        with advisory_lock(target):
            lock_file = target.with_suffix(".json.lock")
            assert lock_file.exists()

    def test_lock_on_nonexistent_file(self):
        """Lock can be acquired even if the target file does not exist yet."""
        root = _tmp_path()
        target = root / "new.json"

        with advisory_lock(target):
            target.write_text('{"created": true}')

        assert target.read_text() == '{"created": true}'

    def test_lock_file_suffix_preserves_original(self):
        """Lock file is .ext.lock, not replacing the original suffix."""
        root = _tmp_path()
        target = root / "config.yaml"
        target.write_text("key: value")

        with advisory_lock(target):
            lock_file = root / "config.yaml.lock"
            assert lock_file.exists()
            assert not (root / "config.lock").exists()


@pytest.mark.unit
class TestAdvisoryLockConcurrency:
    """Verify serialization under multi-process contention."""

    def test_lock_protects_concurrent_writes(self):
        """Spawn a subprocess that holds the lock while we try to acquire.

        Both platforms use blocking lock acquisition, so the parent blocks
        until the child releases, ensuring serialized access.
        """
        root = _tmp_path()
        target = root / "data.json"
        target.write_text('{"value": 0}')

        child_script = textwrap.dedent(f"""\
            import time, json
            from pathlib import Path
            from vaultspec_core.core.helpers import advisory_lock

            target = Path(r"{target}")
            with advisory_lock(target):
                data = json.loads(target.read_text())
                data["child"] = True
                target.write_text(json.dumps(data))
                time.sleep(0.3)
        """)

        proc = subprocess.Popen(
            [sys.executable, "-c", child_script],
            cwd=str(PROJECT_ROOT),
            env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
        )

        import time

        time.sleep(0.1)

        # Parent blocks until child releases, then reads child's write.
        with advisory_lock(target):
            data = json.loads(target.read_text())
            data["parent"] = True
            target.write_text(json.dumps(data))

        proc.wait(timeout=10)
        assert proc.returncode == 0

        final = json.loads(target.read_text())
        assert final.get("parent") is True
        assert final.get("child") is True

    def test_high_contention_no_deadlock(self):
        """Spawn many subprocesses that all compete for the same lock.

        Each process reads a counter, increments it, and writes it back
        under the advisory lock. If any process deadlocks, the 30-second
        timeout fires and the test fails.
        """
        root = _tmp_path()
        target = root / "counter.json"
        n_workers = 8
        target.write_text(json.dumps({"counter": 0}))

        worker_script = textwrap.dedent(f"""\
            import json
            from pathlib import Path
            from vaultspec_core.core.helpers import advisory_lock

            target = Path(r"{target}")
            for _ in range(10):
                with advisory_lock(target):
                    data = json.loads(target.read_text())
                    data["counter"] += 1
                    target.write_text(json.dumps(data))
        """)

        procs = [
            subprocess.Popen(
                [sys.executable, "-c", worker_script],
                cwd=str(PROJECT_ROOT),
                env={**os.environ, "PYTHONPATH": str(PROJECT_ROOT / "src")},
            )
            for _ in range(n_workers)
        ]

        for proc in procs:
            proc.wait(timeout=30)
            assert proc.returncode == 0, (
                f"Worker exited with {proc.returncode} (deadlock or error)"
            )

        final = json.loads(target.read_text())
        assert final["counter"] == n_workers * 10

    def test_multithreaded_no_deadlock(self):
        """Many threads competing for the same lock must not deadlock.

        advisory_lock uses OS-level file locks which are per-process on
        most platforms. This test verifies the lock mechanism does not
        cause thread-level deadlocks or corruption when many threads
        call it concurrently within a single process.
        """
        root = _tmp_path()
        target = root / "threaded.json"
        n_threads = 20
        increments_per_thread = 50
        target.write_text(json.dumps({"counter": 0}))

        errors: list[str] = []
        barrier = threading.Barrier(n_threads)

        def worker():
            try:
                barrier.wait(timeout=5)
                for _ in range(increments_per_thread):
                    with advisory_lock(target):
                        data = json.loads(target.read_text())
                        data["counter"] += 1
                        target.write_text(json.dumps(data))
            except Exception as exc:
                errors.append(f"{threading.current_thread().name}: {exc}")

        threads = [
            threading.Thread(target=worker, name=f"worker-{i}")
            for i in range(n_threads)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
            assert not t.is_alive(), f"Thread {t.name} still alive after 30s (deadlock)"

        assert not errors, f"Thread errors: {errors}"

        final = json.loads(target.read_text())
        expected = n_threads * increments_per_thread
        assert final["counter"] == expected

    def test_different_files_no_contention(self):
        """Locks on different files must not interfere with each other.

        Verifies that two threads locking different files proceed
        independently without blocking or deadlocking.
        """
        root = _tmp_path()
        file_a = root / "a.json"
        file_b = root / "b.json"
        file_a.write_text(json.dumps({"owner": ""}))
        file_b.write_text(json.dumps({"owner": ""}))

        results: dict[str, bool] = {}
        barrier = threading.Barrier(2)

        def lock_file(path: Path, name: str):
            barrier.wait(timeout=5)
            with advisory_lock(path):
                data = json.loads(path.read_text())
                data["owner"] = name
                path.write_text(json.dumps(data))
                results[name] = True

        t1 = threading.Thread(target=lock_file, args=(file_a, "thread-a"))
        t2 = threading.Thread(target=lock_file, args=(file_b, "thread-b"))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        assert not t1.is_alive()
        assert not t2.is_alive()
        assert results == {"thread-a": True, "thread-b": True}
        assert json.loads(file_a.read_text())["owner"] == "thread-a"
        assert json.loads(file_b.read_text())["owner"] == "thread-b"
