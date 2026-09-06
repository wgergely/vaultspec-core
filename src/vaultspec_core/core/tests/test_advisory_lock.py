"""Tests for advisory_lock: file-level locking for scaffold operations."""

from __future__ import annotations

import errno
import json
import logging
import pathlib
import subprocess
import sys
import textwrap
import threading
import time
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.exceptions import (
    AdvisoryLockTimeoutError,
    VaultSpecError,
)
from vaultspec_core.core.helpers import (
    _WINDOWS_LOCK_RETRY_INTERVAL_SECONDS,
    _is_windows_lock_contention,
    _resolve_lock_timeout,
    advisory_lock,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.unit
class TestAdvisoryLock:
    def test_creates_lock_file(self, tmp_path: Path):
        root = tmp_path
        target = root / "test.json"
        target.write_text("{}")

        with advisory_lock(target):
            lock_file = target.with_suffix(".json.lock")
            assert lock_file.exists()

    def test_lock_on_nonexistent_file(self, tmp_path: Path):
        """Lock can be acquired even if the target file does not exist yet."""
        root = tmp_path
        target = root / "new.json"

        with advisory_lock(target):
            target.write_text('{"created": true}')

        assert target.read_text() == '{"created": true}'

    def test_lock_file_suffix_preserves_original(self, tmp_path: Path):
        """Lock file is .ext.lock, not replacing the original suffix."""
        root = tmp_path
        target = root / "config.yaml"
        target.write_text("key: value")

        with advisory_lock(target):
            lock_file = root / "config.yaml.lock"
            assert lock_file.exists()
            assert not (root / "config.lock").exists()


@pytest.mark.unit
class TestAdvisoryLockConcurrency:
    """Verify serialization under multi-process contention."""

    def test_lock_protects_concurrent_writes(self, tmp_path: Path):
        """Spawn a subprocess that holds the lock while we try to acquire.

        Both platforms use blocking lock acquisition, so the parent blocks
        until the child releases, ensuring serialized access.
        """
        root = tmp_path
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
            cwd=str(root),
        )

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

    def test_high_contention_no_deadlock(self, tmp_path: Path):
        """Spawn many subprocesses that all compete for the same lock.

        Each process reads a counter, increments it, and writes it back
        under the advisory lock. If any process deadlocks, the 30-second
        timeout fires and the test fails.
        """
        root = tmp_path
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
                cwd=str(root),
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

    def test_multithreaded_no_deadlock(self, tmp_path: Path):
        """Many threads competing for the same lock must not deadlock.

        advisory_lock uses OS-level file locks which are per-process on
        most platforms. This test verifies the lock mechanism does not
        cause thread-level deadlocks or corruption when many threads
        call it concurrently within a single process.
        """
        root = tmp_path
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

    def test_different_files_no_contention(self, tmp_path: Path):
        """Locks on different files must not interfere with each other.

        Verifies that two threads locking different files proceed
        independently without blocking or deadlocking.
        """
        root = tmp_path
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

    def test_blocks_past_the_windows_retry_budget(self, tmp_path: Path):
        """A hold longer than msvcrt's retry budget must block, not raise.

        ``msvcrt.locking(fd, LK_LOCK, 1)`` is not a blocking acquire despite
        the name: it retries ten times at one-second intervals and then raises
        ``OSError(EDEADLOCK, "Resource deadlock avoided")``. Before this was
        wrapped in a retry, any operation holding a lock past that budget - a
        large repair, a slow or network volume, an antivirus scan mid-write -
        made a concurrent caller crash with an opaque error instead of waiting
        its turn, silently diverging from ``fcntl.flock(LOCK_EX)`` on Unix and
        from this module's own documented contract.

        The hold deliberately exceeds that budget, so a regression fails here
        rather than only under real-world contention.
        """
        target = tmp_path / "slow.json"
        target.write_text('{"value": 0}')
        hold_seconds = 12

        child_script = textwrap.dedent(f"""\
            import time
            from pathlib import Path
            from vaultspec_core.core.helpers import advisory_lock

            target = Path(r"{target}")
            with advisory_lock(target):
                print("held", flush=True)
                time.sleep({hold_seconds})
        """)

        proc = subprocess.Popen(
            [sys.executable, "-c", child_script],
            cwd=str(tmp_path),
            stdout=subprocess.PIPE,
            text=True,
        )
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "held"

        started = time.monotonic()
        with advisory_lock(target):
            waited = time.monotonic() - started

        proc.wait(timeout=30)
        assert proc.returncode == 0
        # Having waited out the holder proves the acquire blocked rather than
        # giving up: the retry budget expires around nine seconds.
        assert waited > 10, f"acquired after only {waited:.1f}s; lock did not block"


class TestWindowsLockContentionClassification:
    """Which `msvcrt.locking` failures mean "wait" rather than "give up".

    `LK_LOCK` reports a LOCKING VIOLATION - someone else holds the range -
    through two different errnos, and Microsoft documents both:

      EDEADLK    the range could not be locked after its ten internal attempts
      EACCES     locking violation (the region is already locked)

    Only EDEADLOCK used to be retried, so contention that arrived as EACCES
    escaped as `PermissionError(13, 'Permission denied')` and was
    indistinguishable from a filesystem permission fault. That is what made the
    Windows concurrency suite intermittently red (issue #321).

    Classified by a pure predicate so this is provable on every platform: the
    acquire loop needs a real Windows descriptor, the decision does not.
    """

    def test_deadlock_is_contention(self) -> None:
        """The documented "could not lock after ten attempts" outcome waits."""
        assert _is_windows_lock_contention(OSError(errno.EDEADLK, "deadlock"))

    def test_access_denied_is_contention_not_a_permission_fault(self) -> None:
        """EACCES from `_locking` means the region is held, not unreachable.

        This is the regression. The exception carries errno 13 and NO
        `winerror`, because it comes from the CRT rather than the Win32 error
        layer - which is exactly why it reads like a permission problem and
        why retrying it is correct rather than papering over a fault.
        """
        exc = PermissionError(errno.EACCES, "Permission denied")

        assert getattr(exc, "winerror", None) is None
        assert _is_windows_lock_contention(exc)

    @pytest.mark.parametrize(
        "code",
        [errno.EBADF, errno.EINVAL, errno.ENOSPC],
    )
    def test_a_genuine_failure_still_propagates(self, code: int) -> None:
        """A bad descriptor or invalid argument must never spin forever."""
        assert not _is_windows_lock_contention(OSError(code, "genuine failure"))

    def test_the_retry_interval_is_short_but_not_a_hot_spin(self) -> None:
        """EACCES can return instantly, so the loop must pause between tries.

        Zero would burn a core while another writer holds the lock; a long
        wait would make every contended acquire feel stalled.
        """
        assert 0 < _WINDOWS_LOCK_RETRY_INTERVAL_SECONDS <= 0.5


class TestManifestReadModifyWriteHoldsTheLock:
    """The RMW cycles outside manifest.py hold the lock (issue #418).

    `write_manifest_data` takes no lock of its own and its docstring says the
    caller must hold one across the whole read-modify-write. Five callers did
    not, so a concurrent writer's edit could be lost in the window between the
    read and the write.

    These are contract tests rather than race tests: the window is real by
    construction but was not observable in three rounds of concurrent syncs,
    so asserting the lock is held is the honest thing to check.
    """

    def test_manifest_lock_is_the_manifest_s_own_lock(self, tmp_path: Path) -> None:
        """The public helper locks the manifest, not some other path."""
        from vaultspec_core.core.manifest import manifest_lock

        (tmp_path / ".vaultspec").mkdir()
        sentinel = tmp_path / ".vaultspec" / "providers.json.lock"

        with manifest_lock(tmp_path):
            assert sentinel.exists()

    def test_the_lock_is_not_reentrant(self, tmp_path: Path) -> None:
        """Recorded deliberately: this is why the cycles are scoped narrowly.

        A second acquisition on the same path blocks forever, so no locked
        cycle may call anything that locks the manifest again. Asserted with a
        thread and a timeout rather than by deadlocking the suite.
        """
        import threading

        from vaultspec_core.core.manifest import manifest_lock

        (tmp_path / ".vaultspec").mkdir()
        acquired_twice = threading.Event()

        def _reenter() -> None:
            with manifest_lock(tmp_path):
                acquired_twice.set()

        with manifest_lock(tmp_path):
            worker = threading.Thread(target=_reenter, daemon=True)
            worker.start()
            worker.join(timeout=0.5)
            assert not acquired_twice.is_set(), (
                "manifest_lock became reentrant; the narrow scoping in "
                "provider_sync and uninstall was written on the assumption "
                "that it is not"
            )


class TestUpgradeFinalizeHoldsTheManifestLock:
    """The upgrade's manifest cycle holds the lock too (issue #418).

    This was the fifth of the five callers and the one that could not simply
    be wrapped: it called `persist_resolved_mode`, whose docstring says it
    must not run inside the manifest lock because the declaration writer takes
    its own. The function is now ordered in two phases - every other-file
    write first, then a manifest cycle that locks nothing else - so the lock
    can cover the whole read-modify-write.

    Proven by holding the lock and observing that the cycle waits for it,
    rather than by asserting on the shape of the code.
    """

    def test_it_waits_for_a_held_manifest_lock(self, tmp_path: Path) -> None:
        import threading

        from vaultspec_core.core.enums import InstallMode
        from vaultspec_core.core.manifest import manifest_lock
        from vaultspec_core.core.provision import _finalize_upgrade_manifest
        from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

        WorkspaceFactory(tmp_path).install("claude")
        finished = threading.Event()

        def _finalize() -> None:
            _finalize_upgrade_manifest(
                tmp_path, force=False, resolved_mode=InstallMode.TOOL
            )
            finished.set()

        with manifest_lock(tmp_path):
            worker = threading.Thread(target=_finalize, daemon=True)
            worker.start()
            # It must not get through the manifest cycle while the lock is held.
            worker.join(timeout=1.0)
            assert not finished.is_set(), (
                "_finalize_upgrade_manifest completed while the manifest lock "
                "was held, so its read-modify-write is not covered by it"
            )

        worker.join(timeout=30.0)
        assert finished.is_set(), "the cycle did not complete once the lock was free"

    def test_the_upgrade_cycle_still_stamps_what_it_should(
        self, tmp_path: Path
    ) -> None:
        """The guard: reordering must not drop any field it used to write."""
        from vaultspec_core.core.enums import InstallMode
        from vaultspec_core.core.manifest import read_manifest_data
        from vaultspec_core.core.provision import _finalize_upgrade_manifest
        from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

        WorkspaceFactory(tmp_path).install("claude")

        _finalize_upgrade_manifest(
            tmp_path, force=False, resolved_mode=InstallMode.TOOL
        )

        mdata = read_manifest_data(tmp_path)
        assert mdata.installed_at
        assert mdata.vaultspec_version
        assert mdata.resolved_mode == InstallMode.TOOL
        assert mdata.gitignore_managed
        assert mdata.gitattributes_managed


# `msvcrt.locking(LK_LOCK)` blocks for about ten seconds inside a single call
# before it reports a locking violation, so a Windows acquire cannot notice an
# exhausted budget any sooner than that. The bound below is what "the timeout
# fired promptly" means on the slowest of the two platforms; POSIX returns
# within a poll interval of the budget itself.
_TIMEOUT_OBSERVATION_CEILING_SECONDS = 25.0


@pytest.mark.unit
class TestAdvisoryLockTimeout:
    """A cycle must surface as a diagnosable error, not a silent hang (#457).

    `advisory_lock` is a non-reentrant `threading.Lock` over a blocking OS
    lock. Both layers used to wait forever, so a caller that reached the same
    sentinel twice on one thread - directly, or through a call graph that
    loops back into a lock-taking helper - stopped dead with no traceback, no
    log line and no way to tell a deadlock from slow I/O. The workspace lock
    graph has such a cycle latent in it today, held shut only by a per-process
    cache documented as a performance optimisation.

    The point of the budget is not to make the cycle correct. It is to make it
    *reportable*, so the next one is a bug report instead of a killed process.
    """

    def test_a_same_thread_reacquire_reports_instead_of_hanging(
        self, tmp_path: Path
    ) -> None:
        """The exact shape of the latent cycle: one thread, one sentinel, twice.

        Without the budget this call never returns and the test process has to
        be killed - which is precisely the failure this fixes, so the
        assertion is that it *returns at all*, with an error that names what
        went wrong.
        """
        target = tmp_path / "cycle.json"
        target.write_text("{}")

        started = time.monotonic()
        with (
            advisory_lock(target),
            pytest.raises(AdvisoryLockTimeoutError) as caught,
            advisory_lock(target, timeout=1.0),
        ):
            pytest.fail("advisory_lock is reentrant; the cycle is silent")
        elapsed = time.monotonic() - started

        assert elapsed < _TIMEOUT_OBSERVATION_CEILING_SECONDS

        error = caught.value
        # The thread layer, not the OS layer: a self-deadlock never reaches
        # the file lock, and saying which layer gave up is what separates
        # "you have a cycle" from "a peer process is holding this".
        assert error.layer == "thread"
        assert error.timeout == 1.0
        assert error.sentinel == tmp_path / "cycle.json.lock"

    def test_the_error_names_the_sentinel_the_budget_and_the_cause(
        self, tmp_path: Path
    ) -> None:
        """An operator reading only the message must be able to act on it."""
        target = tmp_path / "diagnosable.json"
        target.write_text("{}")

        with (
            advisory_lock(target),
            pytest.raises(AdvisoryLockTimeoutError) as caught,
            advisory_lock(target, timeout=0.5),
        ):
            pass

        message = str(caught.value)
        assert "diagnosable.json.lock" in message
        assert "0.5" in message
        assert "thread layer" in message

        hint = caught.value.hint
        assert "cycle" in hint
        # The escape hatch has to be in the hint, or an operator hitting a
        # legitimately slow acquire has no way out but a source change.
        assert "VAULTSPEC_LOCK_TIMEOUT_SECONDS" in hint

    def test_a_timeout_leaves_nothing_held(self, tmp_path: Path) -> None:
        """The failed acquire must not leak the thread lock it timed out on.

        A budget that reported the deadlock but left the sentinel wedged would
        convert a hang into a hang plus an error message.
        """
        target = tmp_path / "released.json"
        target.write_text("{}")

        with (
            advisory_lock(target),
            pytest.raises(AdvisoryLockTimeoutError),
            advisory_lock(target, timeout=0.5),
        ):
            pass

        acquired = False
        with advisory_lock(target, timeout=5.0):
            acquired = True
        assert acquired, "the sentinel stayed held after a timed-out acquire"

    def test_it_is_not_an_oserror(self) -> None:
        """Deliberate: an OSError here would be swallowed by write paths.

        The modules that take advisory locks catch `OSError` in several places
        to log a warning and carry on past an unreadable file. `TimeoutError`
        is an `OSError`, so inheriting from it would let the one failure this
        class exists to make visible disappear into a handler written for
        something else.
        """
        error = AdvisoryLockTimeoutError(pathlib.Path("x.lock"), 1.0, "thread")

        assert not isinstance(error, OSError)
        assert isinstance(error, VaultSpecError)

    def test_a_cross_process_deadline_reports_the_os_layer(
        self, tmp_path: Path
    ) -> None:
        """A peer holding the file lock longer than the budget is diagnosable too.

        The thread layer is uncontended here - the holder is a different
        process - so this exercises the OS layer's deadline specifically, and
        the reported layer is what tells an operator to go looking for another
        process rather than for a cycle in this one.
        """
        target = tmp_path / "peer.json"
        target.write_text("{}")

        child_script = textwrap.dedent(f"""\
            import time
            from pathlib import Path
            from vaultspec_core.core.helpers import advisory_lock

            with advisory_lock(Path(r"{target}")):
                print("held", flush=True)
                time.sleep(40)
        """)
        proc = subprocess.Popen(
            [sys.executable, "-c", child_script],
            cwd=str(tmp_path),
            stdout=subprocess.PIPE,
            text=True,
        )
        try:
            assert proc.stdout is not None
            assert proc.stdout.readline().strip() == "held"

            started = time.monotonic()
            with (
                pytest.raises(AdvisoryLockTimeoutError) as caught,
                advisory_lock(target, timeout=1.0),
            ):
                pytest.fail("acquired a lock another process holds")
            elapsed = time.monotonic() - started
        finally:
            proc.kill()
            proc.wait(timeout=30)

        assert elapsed < _TIMEOUT_OBSERVATION_CEILING_SECONDS
        assert caught.value.layer == "os"
        assert "another" in caught.value.hint.lower()

    def test_the_default_budget_is_read_from_config(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The budget is configurable, because no single number fits every corpus.

        A 1,229-document repair on a network volume and a two-document test
        workspace have wait profiles orders of magnitude apart; an operator
        who hits the ceiling legitimately needs a way past it that is not a
        source change.
        """
        from vaultspec_core.config import get_config, reset_config

        monkeypatch.setenv("VAULTSPEC_LOCK_TIMEOUT_SECONDS", "7.5")
        reset_config()
        try:
            assert get_config().lock_timeout_seconds == 7.5
            assert _resolve_lock_timeout(None) == 7.5
            # An explicit argument still wins over the environment.
            assert _resolve_lock_timeout(2.0) == 2.0
            # A negative budget is clamped rather than passed through:
            # `threading.Lock.acquire` reads -1 as "block forever", which is
            # the unbounded wait this budget exists to remove, and rejects
            # other negatives outright.
            assert _resolve_lock_timeout(-1.0) == 0.0
        finally:
            monkeypatch.delenv("VAULTSPEC_LOCK_TIMEOUT_SECONDS", raising=False)
            reset_config()

    def test_the_default_budget_is_far_longer_than_a_real_critical_section(
        self,
    ) -> None:
        """Guards the number itself against being tightened into a live bug.

        Too short and legitimate contention starts failing: `vault repair`
        holds a feature-index sentinel across a full-corpus graph build, and
        the `exec_ledger_only` migration folds every execution record in the
        workspace under the docs-domain sentinel. Both run in tens of seconds
        on a large vault over a slow volume. Too long and the timeout is
        indistinguishable from the hang it replaced.

        Explicitly *not* `_WINDOWS_REPLACE_RETRY_BUDGET_SECONDS` (2s): that
        budget rides out an antivirus scanner's momentary handle on one file,
        a different phenomenon at a different timescale from a peer holding a
        workspace lock.
        """
        from vaultspec_core.config import VaultSpecConfig
        from vaultspec_core.core.helpers import (
            _WINDOWS_REPLACE_RETRY_BUDGET_SECONDS,
        )

        budget = VaultSpecConfig().lock_timeout_seconds

        assert budget > _WINDOWS_REPLACE_RETRY_BUDGET_SECONDS * 10
        # Longer than msvcrt's own ten-second internal budget by enough that a
        # Windows acquire gets several attempts before giving up.
        assert budget >= 60.0
        assert budget <= 600.0


@pytest.mark.unit
class TestTimeoutDoesNotBreakLegitimateBlocking:
    """The budget must bound deadlock without bounding ordinary contention.

    A timeout that made two processes fail to serialise would trade a rare
    latent hang for a common lost update. These hold the sentinel for real,
    across real processes and real threads, on the *default* budget.
    """

    def test_two_processes_still_serialise_on_the_default_budget(
        self, tmp_path: Path
    ) -> None:
        """A held sentinel is waited out, not abandoned, and both writes land."""
        target = tmp_path / "serialised.json"
        target.write_text(json.dumps({"order": []}))
        hold_seconds = 3

        child_script = textwrap.dedent(f"""\
            import json, time
            from pathlib import Path
            from vaultspec_core.core.helpers import advisory_lock

            target = Path(r"{target}")
            with advisory_lock(target):
                print("held", flush=True)
                time.sleep({hold_seconds})
                data = json.loads(target.read_text())
                data["order"].append("child")
                target.write_text(json.dumps(data))
        """)
        proc = subprocess.Popen(
            [sys.executable, "-c", child_script],
            cwd=str(tmp_path),
            stdout=subprocess.PIPE,
            text=True,
        )
        assert proc.stdout is not None
        assert proc.stdout.readline().strip() == "held"

        started = time.monotonic()
        with advisory_lock(target):
            waited = time.monotonic() - started
            data = json.loads(target.read_text())
            data["order"].append("parent")
            target.write_text(json.dumps(data))

        proc.wait(timeout=60)
        assert proc.returncode == 0, "the holder failed rather than completing"

        # Waiting out the holder is the property: had the budget fired, the
        # parent would have raised, and had the lock not been taken at all the
        # parent would have gone first and lost the child's append.
        assert waited >= hold_seconds - 0.5, (
            f"acquired after only {waited:.1f}s; the lock did not serialise"
        )
        assert json.loads(target.read_text())["order"] == ["child", "parent"]

    def test_sustained_thread_contention_never_times_out(self, tmp_path: Path) -> None:
        """Queued threads wait their turn instead of exhausting the budget.

        Twelve threads each taking the same sentinel means the last one queues
        behind eleven critical sections. That is legitimate contention, and it
        must resolve by waiting.
        """
        target = tmp_path / "queued.json"
        target.write_text(json.dumps({"counter": 0}))
        n_threads = 12
        errors: list[str] = []
        barrier = threading.Barrier(n_threads)

        def worker() -> None:
            try:
                barrier.wait(timeout=30)
                for _ in range(10):
                    with advisory_lock(target):
                        data = json.loads(target.read_text())
                        data["counter"] += 1
                        target.write_text(json.dumps(data))
            except Exception as exc:
                errors.append(f"{threading.current_thread().name}: {exc!r}")

        threads = [
            threading.Thread(target=worker, name=f"queued-{i}")
            for i in range(n_threads)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=120)
            assert not thread.is_alive(), f"{thread.name} never finished"

        assert not errors, f"the budget fired on legitimate contention: {errors}"
        assert json.loads(target.read_text())["counter"] == n_threads * 10


@pytest.mark.unit
class TestAdvisoryLockSkipIsNoLongerSilent:
    """A lock that does nothing must at least leave a trace (#457).

    `advisory_lock` no-ops when the sentinel's parent directory is absent, so
    that a dry run does not create directories as a side effect. The skip is
    load-bearing - `_apply_rename_plan` documents relying on it, and the
    callers that must not skip (`execute_edit` on a real write,
    `generate_feature_index_result`) create the parent themselves first - so
    turning it into an error would break them.

    What was wrong is that it left no trace at all: a caller inside the `with`
    block believes it is protected and nothing, anywhere, recorded that it was
    not. It is recorded at DEBUG rather than WARNING because the function
    cannot tell a preview from a real write, and on a preview the skip is the
    design. Warning unconditionally cried wolf on every `--dry-run` and, since
    the CLI writes log records to stdout, corrupted the `--json` envelope of
    every preview that emitted one - which is what these pin.
    """

    def test_a_skipped_lock_is_recorded_and_names_the_sentinel(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        target = tmp_path / "absent" / "thing.json"

        with (
            caplog.at_level(logging.DEBUG, logger="vaultspec_core.core.helpers"),
            advisory_lock(target),
        ):
            pass

        assert not (tmp_path / "absent").exists(), (
            "the skip must not gain a directory-creating side effect"
        )
        records = [
            r for r in caplog.records if "Advisory lock skipped" in r.getMessage()
        ]
        assert len(records) == 1
        assert records[0].levelno == logging.DEBUG, (
            "a preview skip is the designed behaviour, so it must not be "
            "reported at a level that reaches default CLI output"
        )
        message = records[0].getMessage()
        assert "thing.json.lock" in message
        assert str(tmp_path / "absent") in message

    def test_a_skipped_lock_stays_below_the_default_level(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The regression: an INFO-and-above listener must see nothing.

        The CLI routes log records to stdout, so anything emitted here at INFO
        or above lands inside a `--json` envelope and makes it unparseable.
        Three `vault edit` preview tests and one `exec relink` preview test
        failed on exactly that.
        """
        target = tmp_path / "gone" / "thing.json"

        with (
            caplog.at_level(logging.INFO, logger="vaultspec_core.core.helpers"),
            advisory_lock(target),
        ):
            pass

        assert not caplog.records

    def test_a_real_lock_records_no_skip(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """The guard on the guard: nothing is reported when the lock is real."""
        target = tmp_path / "present.json"
        target.write_text("{}")

        with (
            caplog.at_level(logging.DEBUG, logger="vaultspec_core.core.helpers"),
            advisory_lock(target),
        ):
            pass

        assert (tmp_path / "present.json.lock").exists()
        assert not [
            r for r in caplog.records if "Advisory lock skipped" in r.getMessage()
        ]
