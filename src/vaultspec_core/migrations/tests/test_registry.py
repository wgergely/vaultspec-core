"""Mechanics tests for the migration registry driver.

Exercises :func:`vaultspec_core.migrations.run_pending_migrations`
against a real on-disk manifest with synthetic single-purpose
:class:`~vaultspec_core.migrations.Migration` entries. No mocks or
module-state patching; each test passes an explicit registry list into
the production migration driver.

The driver bumps the manifest version on success and leaves it
untouched on failure. Both branches are covered.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.manifest import (
    read_manifest_data,
    write_manifest_data,
)
from vaultspec_core.graph import cache as cache_mod
from vaultspec_core.migrations import (
    Migration,
    MigrationResult,
    MigrationStatus,
    list_pending,
    migration_status,
    reset_workspace_cache,
    run_pending_migrations,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]


def _noop(name: str, target_version: str) -> tuple[Migration, dict[str, int]]:
    """Build a :class:`Migration` whose body records its invocation count.

    Returns the migration instance and the per-test counter dict so tests
    can assert on the call count without mutating the frozen dataclass.
    """
    counter = {"calls": 0}

    def _migrate(_workspace: Path) -> MigrationResult:
        counter["calls"] += 1
        return MigrationResult(
            name=name,
            target_version=target_version,
            summary=f"{name} ran",
            counts={"calls": counter["calls"]},
        )

    m = Migration(target_version=target_version, name=name, migrate=_migrate)
    return m, counter


def _raising(name: str, target_version: str) -> Migration:
    """Build a :class:`Migration` whose body raises on every invocation."""

    def _migrate(_workspace: Path) -> MigrationResult:
        raise RuntimeError(f"{name} intentionally failed")

    return Migration(target_version=target_version, name=name, migrate=_migrate)


class TestEmptyRegistry:
    def test_no_op_returns_empty_list(self, workspace: Path):
        results = run_pending_migrations(workspace, registry=[])
        assert results == []

    def test_no_op_does_not_bump_version(self, workspace: Path):
        before = read_manifest_data(workspace).vaultspec_version
        run_pending_migrations(workspace, registry=[])
        after = read_manifest_data(workspace).vaultspec_version
        assert before == after == "0.1.0"


class TestSingleMigration:
    def test_runs_once_when_target_above_manifest(self, workspace: Path):
        m, counter = _noop("alpha", "0.2.0")
        results = run_pending_migrations(workspace, registry=[m])

        assert len(results) == 1
        assert results[0].name == "alpha"
        assert counter["calls"] == 1

    def test_bumps_manifest_version_on_success(self, workspace: Path):
        m, _ = _noop("alpha", "0.2.0")
        run_pending_migrations(workspace, registry=[m])
        after = read_manifest_data(workspace).vaultspec_version
        # The driver bumps to whichever is higher: the running package
        # version, or the highest applied target. The post-bump version
        # must at least cover the migration we just ran.
        from vaultspec_core.core.helpers import parse_version_tuple

        assert parse_version_tuple(after) >= parse_version_tuple("0.2.0")

    def test_second_run_is_no_op(self, workspace: Path):
        m, counter = _noop("alpha", "0.2.0")
        registry = [m]
        run_pending_migrations(workspace, registry=registry)
        version_after_first = read_manifest_data(workspace).vaultspec_version
        reset_workspace_cache()

        results = run_pending_migrations(workspace, registry=registry)
        assert results == []
        assert counter["calls"] == 1
        version_after_second = read_manifest_data(workspace).vaultspec_version
        assert version_after_first == version_after_second


class TestOrdering:
    def test_runs_in_version_order_on_stale_workspace(self, workspace: Path):
        # Two migrations on the same stale 0.1.0 manifest. The driver
        # must apply them in version order regardless of registry
        # insertion order.
        order: list[str] = []

        def make_recording(name: str, target_version: str):
            def _migrate(_w: Path) -> MigrationResult:
                order.append(name)
                return MigrationResult(
                    name=name,
                    target_version=target_version,
                    summary=f"{name} ran",
                )

            return Migration(
                target_version=target_version,
                name=name,
                migrate=_migrate,
            )

        m_late = make_recording("late", "0.3.0")
        m_early = make_recording("early", "0.2.0")
        # Insertion order is intentionally late-then-early so the
        # driver's version sort actually has work to do.
        run_pending_migrations(
            workspace,
            registry=[m_late, m_early],
        )
        assert order == ["early", "late"]


class TestVersionGating:
    def test_equal_version_does_not_run(self, workspace: Path):
        # Strict greater-than: target_version == manifest must skip.
        data = read_manifest_data(workspace)
        data.vaultspec_version = "0.2.0"
        write_manifest_data(workspace, data)
        m, counter = _noop("alpha", "0.2.0")

        results = run_pending_migrations(workspace, registry=[m])
        assert results == []
        assert counter["calls"] == 0

    def test_target_below_manifest_does_not_run(self, workspace: Path):
        data = read_manifest_data(workspace)
        data.vaultspec_version = "0.5.0"
        write_manifest_data(workspace, data)
        m, counter = _noop("ancient", "0.2.0")

        results = run_pending_migrations(workspace, registry=[m])
        assert results == []
        assert counter["calls"] == 0

    def test_empty_manifest_version_does_not_run(self, tmp_path: Path):
        # No manifest on disk at all.
        m, counter = _noop("alpha", "0.2.0")

        results = run_pending_migrations(tmp_path, registry=[m])
        assert results == []
        assert counter["calls"] == 0


class TestIncrementalVersionBump:
    def test_partial_failure_records_completed_target(self, workspace: Path):
        # Two migrations: 0.2.0 succeeds, 0.3.0 raises. After the
        # exception the manifest version must reflect 0.2.0 (the
        # successful step) so the next invocation only re-runs 0.3.0.
        m_first, first_counter = _noop("first", "0.2.0")
        m_second = _raising("second", "0.3.0")

        with pytest.raises(RuntimeError, match="second intentionally failed"):
            run_pending_migrations(workspace, registry=[m_first, m_second])

        recorded = read_manifest_data(workspace).vaultspec_version
        from vaultspec_core.core.helpers import parse_version_tuple

        assert parse_version_tuple(recorded) >= parse_version_tuple("0.2.0")
        assert parse_version_tuple(recorded) < parse_version_tuple("0.3.0")
        assert first_counter["calls"] == 1

        # Second invocation: replace the broken entry with a working
        # one and confirm the first migration is NOT re-run because
        # the manifest already records its completion.
        m_second_fixed, second_counter = _noop("second_fixed", "0.3.0")
        run_pending_migrations(workspace, registry=[m_first, m_second_fixed])
        assert first_counter["calls"] == 1, (
            "successful first migration must not be re-run after a "
            "failure of a later entry"
        )
        assert second_counter["calls"] == 1


class TestCacheKeyNormalisation:
    def test_relative_and_resolved_paths_share_cache(
        self,
        workspace: Path,
        tmp_path: Path,
    ):
        # Up-to-date workspace; first call populates the cache. A
        # second call via an equivalent but differently-spelled path
        # (e.g. relative) must hit the cache rather than performing
        # another manifest read.
        data = read_manifest_data(workspace)
        data.vaultspec_version = "9.9.9"
        write_manifest_data(workspace, data)
        m, counter = _noop("alpha", "0.2.0")
        registry = [m]

        # First call resolves the path; cache populated.
        run_pending_migrations(workspace, use_cache=True, registry=registry)
        assert counter["calls"] == 0

        # Mutate the manifest behind the registry's back to a stale
        # version. If the cache key were path-sensitive, the second
        # call via the unresolved path would miss the cache and
        # observe the stale version, running the migration. With
        # resolve()-keyed cache, both spellings hit the same entry
        # and the migration stays skipped.
        unresolved = workspace / "."
        data2 = read_manifest_data(workspace)
        data2.vaultspec_version = "0.0.1"
        write_manifest_data(workspace, data2)

        run_pending_migrations(unresolved, use_cache=True, registry=registry)
        assert counter["calls"] == 0, (
            "cache hit via equivalent path must short-circuit before "
            "the manifest read; migration must not run"
        )


class TestFailureDoesNotBumpVersion:
    def test_raising_migration_propagates(self, workspace: Path):
        registry = [_raising("broken", "0.2.0")]

        with pytest.raises(RuntimeError, match="broken intentionally failed"):
            run_pending_migrations(workspace, registry=registry)

    def test_raising_migration_leaves_version_untouched(self, workspace: Path):
        before = read_manifest_data(workspace).vaultspec_version
        registry = [_raising("broken", "0.2.0")]

        with pytest.raises(RuntimeError, match="broken intentionally failed"):
            run_pending_migrations(workspace, registry=registry)

        after = read_manifest_data(workspace).vaultspec_version
        assert before == after == "0.1.0"

    def test_failure_is_retried_on_next_call(self, workspace: Path):
        # First call raises. After the failing entry is replaced, the
        # next call should pick up where it left off.
        with pytest.raises(RuntimeError, match="broken intentionally failed"):
            run_pending_migrations(workspace, registry=[_raising("broken", "0.2.0")])

        # Replace with a successful version of the same target.
        m_fixed, counter = _noop("fixed", "0.2.0")
        results = run_pending_migrations(workspace, registry=[m_fixed])
        assert len(results) == 1
        assert counter["calls"] == 1


class TestStatusHelpers:
    def test_unknown_when_no_manifest(self, tmp_path: Path):
        status, names = migration_status(tmp_path)
        assert status == MigrationStatus.UNKNOWN
        assert names == []

    def test_pending_when_target_above(self, workspace: Path):
        m, _ = _noop("alpha", "0.2.0")
        status, names = migration_status(workspace, registry=[m])
        assert status == MigrationStatus.PENDING
        assert names == ["alpha"]

    def test_up_to_date_when_all_applied(self, workspace: Path):
        data = read_manifest_data(workspace)
        data.vaultspec_version = "9.9.9"
        write_manifest_data(workspace, data)
        m, _ = _noop("alpha", "0.2.0")
        status, names = migration_status(workspace, registry=[m])
        assert status == MigrationStatus.UP_TO_DATE
        assert names == []

    def test_legacy_manifest_is_pending_not_unknown(self, workspace: Path):
        """A manifest with no version is legacy, not absent (issue #408).

        Both read back as an empty ``vaultspec_version``, and the two used to
        share one short-circuit. That made the workspaces most in need of the
        data-shape migrations the only ones that never received them.
        """
        data = read_manifest_data(workspace)
        data.vaultspec_version = ""
        write_manifest_data(workspace, data)
        m, _ = _noop("alpha", "0.2.0")

        status, names = migration_status(workspace, registry=[m])

        assert status == MigrationStatus.PENDING
        assert names == ["alpha"]

    def test_every_migration_is_pending_for_a_legacy_manifest(
        self, workspace: Path
    ) -> None:
        """A legacy workspace predates the whole registry, so all of it applies."""
        data = read_manifest_data(workspace)
        data.vaultspec_version = ""
        write_manifest_data(workspace, data)
        ancient, _ = _noop("ancient", "0.1.5")
        middle, _ = _noop("middle", "0.2.0")
        future, _ = _noop("future", "0.3.0")

        pending = list_pending(workspace, registry=[ancient, middle, future])

        assert [m.name for m in pending] == ["ancient", "middle", "future"]

    def test_a_legacy_manifest_actually_runs_its_migrations(
        self, workspace: Path
    ) -> None:
        """The driver runs them, rather than certifying them as applied.

        The sequence that made this invisible: the driver reported nothing to
        do, a later upgrade stamped the running version, and ``status`` then
        reported every migration as applied - none of which had run.
        """
        data = read_manifest_data(workspace)
        data.vaultspec_version = ""
        write_manifest_data(workspace, data)
        m, counter = _noop("alpha", "0.2.0")

        results = run_pending_migrations(workspace, registry=[m])

        assert counter["calls"] == 1
        assert len(results) == 1
        status, _names = migration_status(workspace, registry=[m])
        assert status == MigrationStatus.UP_TO_DATE

    def test_an_absent_manifest_still_reports_nothing_to_do(
        self, tmp_path: Path
    ) -> None:
        """The other half of the distinction must not move.

        A directory with a ``.vaultspec/`` but no manifest is not installed,
        so the registry has nothing to say about it and nothing to run.
        """
        (tmp_path / ".vaultspec").mkdir()
        m, counter = _noop("alpha", "0.2.0")

        assert list_pending(tmp_path, registry=[m]) == []
        assert migration_status(tmp_path, registry=[m])[0] is MigrationStatus.UNKNOWN
        assert run_pending_migrations(tmp_path, registry=[m]) == []
        assert counter["calls"] == 0

    def test_list_pending_filters_to_above_manifest_only(self, workspace: Path):
        data = read_manifest_data(workspace)
        data.vaultspec_version = "0.2.0"
        write_manifest_data(workspace, data)
        # 0.1.5 < 0.2.0 (skip), 0.2.0 == 0.2.0 (skip), 0.3.0 > 0.2.0 (include).
        ancient, _ = _noop("ancient", "0.1.5")
        equal, _ = _noop("equal", "0.2.0")
        future, _ = _noop("future", "0.3.0")
        pending = list_pending(workspace, registry=[ancient, equal, future])
        assert [m.name for m in pending] == ["future"]


class TestGraphCacheInvalidation:
    """A migration that mutates ``.vault/`` documents drops the graph cache.

    Migration bodies write directly to disk (``modified_stamp_backfill``,
    ``index_subfolder``) instead of going through the mutating CLI verbs, so
    they never pass through
    :func:`vaultspec_core.cli._cache_hook.invalidate_graph_cache`. Without
    the driver's own invalidation call, a stale graph cache would only be
    caught by the per-file fingerprint self-healing - sound for today's two
    migrations (both change a file's size or its manifest key) but not a
    guarantee for a future same-size in-place rewrite. These tests pin the
    driver's own safety net directly, independent of what any particular
    migration body happens to touch.
    """

    def _prime_cache(self, workspace: Path) -> Path:
        """Write a real, loadable graph cache file for *workspace*."""
        cache_file = cache_mod.cache_path(workspace)
        cache_mod.save(
            cache_file,
            manifest={},
            graph={"nodes": [], "edges": []},
            dangling_links=[],
        )
        assert cache_file.exists()
        return cache_file

    def test_applied_migration_drops_the_cache(self, workspace: Path) -> None:
        cache_file = self._prime_cache(workspace)

        def _migrate(w: Path) -> MigrationResult:
            # A real content mutation, mirroring how a live migration body
            # rewrites a `.vault/` document directly.
            doc = w / ".vault" / "adr" / "2026-01-01-example-adr.md"
            doc.parent.mkdir(parents=True, exist_ok=True)
            doc.write_text("# migrated\n", encoding="utf-8")
            return MigrationResult(
                name="rewrites-doc", target_version="0.2.0", summary=""
            )

        m = Migration(target_version="0.2.0", name="rewrites-doc", migrate=_migrate)

        run_pending_migrations(workspace, registry=[m])

        assert not cache_file.exists(), (
            "run_pending_migrations must drop the graph cache after applying "
            "a migration, not rely solely on the per-file fingerprint"
        )

    def test_no_pending_migration_leaves_cache_untouched(self, workspace: Path) -> None:
        # Manifest already covers every registered migration: the driver
        # short-circuits before running anything and must not touch a cache
        # it never had reason to invalidate.
        data = read_manifest_data(workspace)
        data.vaultspec_version = "9.9.9"
        write_manifest_data(workspace, data)
        cache_file = self._prime_cache(workspace)
        m, _ = _noop("alpha", "0.2.0")

        run_pending_migrations(workspace, registry=[m])

        assert cache_file.exists()

    def test_raising_migration_still_drops_the_cache(self, workspace: Path) -> None:
        # The failing migration's own bump is suppressed, but a prior
        # successful migration in the same run may already have mutated the
        # corpus; the cache must not survive as a stale artifact.
        cache_file = self._prime_cache(workspace)
        m_first, _ = _noop("first", "0.2.0")
        m_second = _raising("second", "0.3.0")

        with pytest.raises(RuntimeError, match="second intentionally failed"):
            run_pending_migrations(workspace, registry=[m_first, m_second])

        assert not cache_file.exists()
