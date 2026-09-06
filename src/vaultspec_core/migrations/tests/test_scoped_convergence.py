"""Driver mechanics for a scoped migration run.

Issue #458. ``ensure_migrated`` used to run the whole registry on behalf of a
verb that writes one document, so ``vaultspec-core vault add`` on a stale
workspace could remove an unbounded number of documents the user never named.
The registry now classifies each entry by :class:`MigrationScope` and the
driver accepts a ``scopes`` entitlement, so an authoring write converges only
what decides where it lands.

These tests exercise the driver directly with synthetic entries, because the
properties that matter are properties of the *bookkeeping*, not of any
particular migration: which entries run, which are skipped, what the manifest
records afterwards, and - the one that could lose data if it were wrong - that
a skipped entry is still pending when an operator next asks. The integration
side, over the real CLI and the real MCP transport, is in
``vaultspec_core.tests.cli.test_scoped_migration_convergence``.

No mocks and no patching: every test writes a real manifest to a real
directory and passes an explicit registry list into the production driver.
"""

from __future__ import annotations

import inspect
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data
from vaultspec_core.migrations import (
    REGISTRY,
    WRITE_PLACEMENT_SCOPES,
    Migration,
    MigrationResult,
    MigrationScope,
    MigrationStatus,
    list_pending,
    migration_status,
    run_pending_migrations,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.unit]


def _recording(
    name: str, target_version: str, scope: MigrationScope
) -> tuple[Migration, list[str]]:
    """Build a scoped :class:`Migration` that appends its name when it runs.

    Returns the entry and the shared log, so a test can assert on the exact
    execution order rather than only on a call count.
    """
    ran: list[str] = []

    def _migrate(_workspace: Path) -> MigrationResult:
        ran.append(name)
        return MigrationResult(
            name=name, target_version=target_version, summary=f"{name} ran"
        )

    return (
        Migration(
            target_version=target_version, name=name, migrate=_migrate, scope=scope
        ),
        ran,
    )


class TestRegistryClassification:
    """Every registered entry declares what it does to the workspace."""

    def test_every_entry_declares_its_scope_explicitly(self) -> None:
        """A default is a safety net, not a substitute for a declaration.

        ``Migration.scope`` defaults to ``DOCUMENT_CONTENT`` so an entry added
        without thinking about the boundary is excluded from the authoring
        hook rather than silently admitted to it. But a registry that leans on
        the default cannot be reviewed: the reader cannot tell a considered
        ``DOCUMENT_CONTENT`` from an unconsidered one. This reads the defining
        source of each entry and requires the keyword to be present, so the
        classification is a decision recorded at the call site.
        """
        undeclared: list[str] = []
        for migration in REGISTRY:
            module = inspect.getmodule(migration.migrate)
            assert module is not None, migration.name
            if "scope=MigrationScope." not in inspect.getsource(module):
                undeclared.append(migration.name)
        assert not undeclared, (
            f"registry entries must declare scope= explicitly: {undeclared}"
        )

    def test_write_placement_is_confined_to_the_index_relocation(self) -> None:
        """The entitlement an authoring verb receives is one entry wide.

        Not a name list being restated - the point is the size of the set. If
        a future entry declares ``WRITE_PLACEMENT`` it joins what every
        ``vault add`` runs unattended, and that has to be a change somebody
        makes on purpose and defends here.
        """
        placement = [
            m.name for m in REGISTRY if m.scope is MigrationScope.WRITE_PLACEMENT
        ]
        assert placement == ["index_subfolder"]

    def test_no_entry_that_removes_documents_is_write_placement(self) -> None:
        """The folds are what an authoring verb must never reach.

        ``exec_ledger_fold`` and ``exec_ledger_only`` are the two entries that
        unlink documents a human wrote; they are the deletions issue #458 was
        raised about.
        """
        for name in ("exec_ledger_fold", "exec_ledger_only"):
            entry = next(m for m in REGISTRY if m.name == name)
            assert entry.scope is MigrationScope.DOCUMENT_CONTENT

    def test_an_undeclared_entry_is_not_eligible(self) -> None:
        """The default has to be the safe reading, so silence cannot widen it."""

        def _migrate(_workspace: Path) -> MigrationResult:
            return MigrationResult(
                name="undeclared", target_version="0.2.0", summary="ran"
            )

        entry = Migration(target_version="0.2.0", name="undeclared", migrate=_migrate)
        assert entry.scope is MigrationScope.DOCUMENT_CONTENT
        assert entry.scope not in WRITE_PLACEMENT_SCOPES


class TestScopedRun:
    """What a scoped call runs, skips, and records."""

    def test_out_of_scope_entries_do_not_run(self, workspace: Path) -> None:
        placement, placement_ran = _recording(
            "placement", "0.2.0", MigrationScope.WRITE_PLACEMENT
        )
        content, content_ran = _recording(
            "content", "0.3.0", MigrationScope.DOCUMENT_CONTENT
        )

        results = run_pending_migrations(
            workspace,
            registry=[placement, content],
            scopes=WRITE_PLACEMENT_SCOPES,
        )

        assert placement_ran == ["placement"]
        assert content_ran == []
        assert [r.name for r in results] == ["placement"]

    def test_an_in_scope_entry_above_a_skipped_one_still_runs(
        self, workspace: Path
    ) -> None:
        """Skipping is not stopping.

        The entitlement is per entry, not a ceiling. A workspace stale enough
        to have a content entry pending must still get every relocation the
        schema needs, or the split brain the hook exists to prevent reopens
        for exactly the oldest workspaces.
        """
        first, first_ran = _recording(
            "first_placement", "0.2.0", MigrationScope.WRITE_PLACEMENT
        )
        content, content_ran = _recording(
            "content", "0.3.0", MigrationScope.DOCUMENT_CONTENT
        )
        second, second_ran = _recording(
            "second_placement", "0.4.0", MigrationScope.WRITE_PLACEMENT
        )

        run_pending_migrations(
            workspace,
            registry=[first, content, second],
            scopes=WRITE_PLACEMENT_SCOPES,
        )

        assert first_ran == ["first_placement"]
        assert second_ran == ["second_placement"]
        assert content_ran == []

    def test_the_version_bumps_only_through_the_unbroken_run_prefix(
        self, workspace: Path
    ) -> None:
        """The manifest scalar must keep meaning what it says.

        ``vaultspec_version`` asserts that every entry at or below it has run.
        A scoped run that advanced past the entry it skipped would retire that
        entry forever - the deletions would then never happen, and no command
        would ever report them as outstanding. So the bump stops at the first
        skip, even though a later in-scope entry ran after it.
        """
        first, _ = _recording(
            "first_placement", "0.2.0", MigrationScope.WRITE_PLACEMENT
        )
        content, _ = _recording("content", "0.3.0", MigrationScope.DOCUMENT_CONTENT)
        second, _ = _recording(
            "second_placement", "0.4.0", MigrationScope.WRITE_PLACEMENT
        )

        run_pending_migrations(
            workspace,
            registry=[first, content, second],
            scopes=WRITE_PLACEMENT_SCOPES,
        )

        assert read_manifest_data(workspace).vaultspec_version == "0.2.0"

    def test_a_skipped_entry_is_still_pending_afterwards(self, workspace: Path) -> None:
        """The residue stays visible to status, to warnings, and to the next run.

        The registry deliberately puts an in-scope entry *above* the skipped
        one, because that is the arrangement that can silently retire it: a
        run that bumped the version to the last entry it executed would record
        0.4.0, and the skipped 0.3.0 would read as applied from then on.
        """
        first, _ = _recording(
            "first_placement", "0.2.0", MigrationScope.WRITE_PLACEMENT
        )
        content, _ = _recording("content", "0.3.0", MigrationScope.DOCUMENT_CONTENT)
        second, _ = _recording(
            "second_placement", "0.4.0", MigrationScope.WRITE_PLACEMENT
        )
        registry = [first, content, second]

        run_pending_migrations(
            workspace, registry=registry, scopes=WRITE_PLACEMENT_SCOPES
        )

        status, names = migration_status(workspace, registry=registry)
        assert status is MigrationStatus.PENDING
        assert "content" in names

    def test_an_explicit_run_afterwards_applies_the_skipped_entry(
        self, workspace: Path
    ) -> None:
        """The deferral has to be recoverable, or it is just a refusal.

        Same three-entry arrangement as above: the entry that could have
        retired the skipped one already ran, so this asserts the skipped one
        is not merely reported as pending but genuinely runs when asked.
        """
        first, _ = _recording(
            "first_placement", "0.2.0", MigrationScope.WRITE_PLACEMENT
        )
        content, content_ran = _recording(
            "content", "0.3.0", MigrationScope.DOCUMENT_CONTENT
        )
        second, _ = _recording(
            "second_placement", "0.4.0", MigrationScope.WRITE_PLACEMENT
        )
        registry = [first, content, second]

        run_pending_migrations(
            workspace, registry=registry, scopes=WRITE_PLACEMENT_SCOPES
        )
        run_pending_migrations(workspace, registry=registry)

        assert content_ran == ["content"]
        assert list_pending(workspace, registry=registry) == []

    def test_a_scoped_run_with_nothing_in_scope_changes_nothing(
        self, workspace: Path
    ) -> None:
        content, content_ran = _recording(
            "content", "0.3.0", MigrationScope.DOCUMENT_CONTENT
        )

        results = run_pending_migrations(
            workspace, registry=[content], scopes=WRITE_PLACEMENT_SCOPES
        )

        assert results == []
        assert content_ran == []
        assert read_manifest_data(workspace).vaultspec_version == "0.1.0"

    def test_an_unscoped_run_is_unchanged(self, workspace: Path) -> None:
        """The operator verbs keep the whole registry and the full bump."""
        placement, placement_ran = _recording(
            "placement", "0.2.0", MigrationScope.WRITE_PLACEMENT
        )
        content, content_ran = _recording(
            "content", "0.3.0", MigrationScope.DOCUMENT_CONTENT
        )
        registry = [placement, content]

        run_pending_migrations(workspace, registry=registry)

        assert placement_ran == ["placement"]
        assert content_ran == ["content"]
        assert list_pending(workspace, registry=registry) == []


class TestScopedCacheInteraction:
    """The per-process cache must not launder a scoped run into an unscoped one."""

    def test_a_scoped_run_does_not_mark_the_workspace_up_to_date(
        self, workspace: Path
    ) -> None:
        """The bug this forecloses would lose the deletions entirely.

        The hook passes ``use_cache=True``. If a scoped run cached "nothing
        left to do", a later unscoped caller in the same process - the MCP
        server runs for hours - would short-circuit on that entry and skip the
        content entries that really were pending, while the manifest still
        said they were outstanding.
        """
        placement, _ = _recording("placement", "0.2.0", MigrationScope.WRITE_PLACEMENT)
        content, content_ran = _recording(
            "content", "0.3.0", MigrationScope.DOCUMENT_CONTENT
        )
        registry = [placement, content]

        run_pending_migrations(
            workspace,
            registry=registry,
            use_cache=True,
            scopes=WRITE_PLACEMENT_SCOPES,
        )
        run_pending_migrations(workspace, registry=registry, use_cache=True)

        assert content_ran == ["content"]

    def test_the_settled_workspace_is_cached_with_nothing_in_scope(
        self, workspace: Path
    ) -> None:
        """The steady state this design creates must not be the uncached one.

        Once the relocation has applied, an authoring verb finds nothing it is
        entitled to run while the content entries stay pending indefinitely -
        which is the normal condition under scoped convergence, not an edge
        case. A cache entry withheld because *something* is pending would mean
        a long-lived MCP server pays an advisory lock and a manifest read on
        every ``create`` forever.

        Rewinding the manifest between the calls is what makes the assertion
        real: a second call that re-read the file would find the relocation
        pending and run it, so a still-empty log is the cache having answered.
        """
        placement, placement_ran = _recording(
            "placement", "0.2.0", MigrationScope.WRITE_PLACEMENT
        )
        content, _ = _recording("content", "0.3.0", MigrationScope.DOCUMENT_CONTENT)
        registry = [placement, content]
        settled = read_manifest_data(workspace)
        settled.vaultspec_version = "0.2.0"
        write_manifest_data(workspace, settled)

        run_pending_migrations(
            workspace,
            registry=registry,
            use_cache=True,
            scopes=WRITE_PLACEMENT_SCOPES,
        )
        assert placement_ran == []
        rewound = read_manifest_data(workspace)
        rewound.vaultspec_version = "0.1.0"
        write_manifest_data(workspace, rewound)

        run_pending_migrations(
            workspace,
            registry=registry,
            use_cache=True,
            scopes=WRITE_PLACEMENT_SCOPES,
        )

        assert placement_ran == []

    def test_that_cache_entry_does_not_hide_the_content_entries(
        self, workspace: Path
    ) -> None:
        """The other half: caching a version must not retire what is pending.

        The entry written above records the manifest version, not a verdict.
        An unscoped caller arriving afterwards in the same process compares it
        against its own tail, finds the content entry above it, and runs it.
        Were the entry ever read as "this workspace is done", the deletions
        would be skipped while the manifest still reported them outstanding.
        """
        placement, _ = _recording("placement", "0.2.0", MigrationScope.WRITE_PLACEMENT)
        content, content_ran = _recording(
            "content", "0.3.0", MigrationScope.DOCUMENT_CONTENT
        )
        registry = [placement, content]
        settled = read_manifest_data(workspace)
        settled.vaultspec_version = "0.2.0"
        write_manifest_data(workspace, settled)

        run_pending_migrations(
            workspace,
            registry=registry,
            use_cache=True,
            scopes=WRITE_PLACEMENT_SCOPES,
        )
        run_pending_migrations(workspace, registry=registry, use_cache=True)

        assert content_ran == ["content"]
        assert list_pending(workspace, registry=registry) == []

    def test_a_warm_scoped_caller_short_circuits_on_a_stale_workspace(
        self, workspace: Path
    ) -> None:
        """A workspace that is permanently short of up to date stays cheap.

        Under scoped convergence a stale workspace never reaches the
        up-to-date state the cache was written for, so a short-circuit keyed
        on the tail of the whole registry would never fire and every authoring
        verb would pay an advisory lock and a manifest read forever. It reads
        the tail of the caller's *eligible* subset instead.

        Proven by rewinding the manifest on disk between the two calls: a call
        that re-read it would find the relocation pending again and re-run it,
        so a single recorded run is the cache having answered without touching
        the file.
        """
        placement, placement_ran = _recording(
            "placement", "0.2.0", MigrationScope.WRITE_PLACEMENT
        )
        content, _ = _recording("content", "0.3.0", MigrationScope.DOCUMENT_CONTENT)
        registry = [placement, content]

        run_pending_migrations(
            workspace,
            registry=registry,
            use_cache=True,
            scopes=WRITE_PLACEMENT_SCOPES,
        )
        assert read_manifest_data(workspace).vaultspec_version == "0.2.0"
        rewound = read_manifest_data(workspace)
        rewound.vaultspec_version = "0.1.0"
        write_manifest_data(workspace, rewound)

        run_pending_migrations(
            workspace,
            registry=registry,
            use_cache=True,
            scopes=WRITE_PLACEMENT_SCOPES,
        )

        assert placement_ran == ["placement"]
