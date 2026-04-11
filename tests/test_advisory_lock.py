"""Tests for advisory_lock: file-level locking for scaffold operations."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
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

    def test_lock_is_reentrant_from_same_process_unix(self):
        """On Unix, flock is reentrant per-process; on Windows msvcrt is not.

        This test verifies the fallback path works - if the inner lock
        acquisition fails, the OSError handler lets execution proceed.
        """
        root = _tmp_path()
        target = root / "test.json"
        target.write_text("{}")

        with advisory_lock(target):  # noqa: SIM117 - intentional nesting to test reentrancy
            # Nested acquisition: on Unix this succeeds (flock is reentrant),
            # on Windows the OSError fallback kicks in.
            with advisory_lock(target):
                target.write_text('{"nested": true}')

        assert "nested" in target.read_text()

    def test_lock_protects_concurrent_writes(self):
        """Spawn a subprocess that holds the lock while we try to acquire it.

        On Unix with LOCK_EX this serializes; on Windows with LK_NBLCK
        the second acquisition falls through to the OSError handler, which
        is the documented graceful-degradation behavior.
        """
        root = _tmp_path()
        target = root / "data.json"
        target.write_text('{"value": 0}')

        # Child script: acquire lock, write a marker, sleep briefly, release
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

        # Give child time to acquire the lock
        import time

        time.sleep(0.1)

        # Parent acquires the same lock - on Unix this blocks until child
        # releases; on Windows the fallback proceeds immediately.
        with advisory_lock(target):
            data = __import__("json").loads(target.read_text())
            data["parent"] = True
            target.write_text(__import__("json").dumps(data))

        proc.wait(timeout=10)
        assert proc.returncode == 0

        final = __import__("json").loads(target.read_text())
        # Both writers must have run
        assert final.get("parent") is True
        assert final.get("child") is True

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
            # Must NOT create config.lock (that would replace .yaml)
            assert not (root / "config.lock").exists()
