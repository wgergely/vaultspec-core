"""An authoring verb converges where its write lands, and nothing else.

Issue #458.  The write side of the migration boundary was drawn correctly -
``vaultspec-core vault add``, ``vaultspec-core vault feature index`` and the
MCP ``create`` tool write to a location the schema decides, so they must not
author into a layout a pending migration is about to move - but it was drawn
too wide.  The hook ran the *whole* registry, so a user returning to a
months-stale workspace and typing ``vault add adr --feature auth`` got one new
ADR and, on the same keystroke, the execution-record folds across the entire
corpus: per-Step records and Phase Summaries removed, nothing prompted,
nothing previewed, the deletions reported only in retrospect.  That is the
same class of event as issue #443, differing only in that the triggering verb
also wrote something.

The boundary is now scoped by what each registry entry *does*.  An authoring
verb runs the entries that decide where its write lands
(``MigrationScope.WRITE_PLACEMENT``) and none of the entries that rewrite or
remove documents it never named.  Both halves are pinned here, because either
one alone is a different bug: without the relocation, one feature ends up with
two tracked indexes; without the refusal, one document written costs an
unbounded number deleted.

Every fixture is a real installed workspace over a real temp directory driven
through the real CLI and the real in-memory MCP server.  No mocks, no patches,
no skips: the defect is a filesystem side effect, so only the filesystem can
witness its absence.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from mcp import Client
from mcp.types import TextContent

from vaultspec_core.config import reset_config
from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data
from vaultspec_core.core.types import init_paths
from vaultspec_core.migrations import (
    MIGRATION_LOGGER,
    MigrationStatus,
    migration_status,
    reset_workspace_cache,
)
from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.unit]

_FOLDER = "2026-05-17-boundary"
_PLAN_STEM = "2026-05-17-boundary-plan"
_INDEX_FEATURE = "alpha"

# Below the ``index_subfolder`` target (0.1.17), so every registered entry is
# genuinely pending: the relocation the authoring verb is entitled to run and
# the content folds it is not.
_REWIND_TO = "0.1.0"

# What the manifest must read after a scoped run: the relocation's target, and
# not one release higher.  Advancing past a skipped entry would record it as
# applied and retire it permanently.
_SCOPED_VERSION = "0.1.17"


def _seed(root: Path) -> None:
    """Write both halves of the fixture into an installed workspace.

    The legacy shape ``index_subfolder`` converges - a generated feature index
    at the ``.vault/`` root instead of under ``.vault/index/`` - alongside the
    document set the execution-record folds consume: an L2 plan with a
    two-Step Phase, a per-Step record for each Step, and the Phase Summary
    those records make removable.  One workspace carrying both is what makes
    the two assertions a single statement about one command rather than two
    scenarios that never meet.
    """
    vault = root / ".vault"

    (vault / f"{_INDEX_FEATURE}.index.md").write_text(
        "---\ngenerated: true\ntags:\n  - '#index'\n"
        f"  - '#{_INDEX_FEATURE}'\ndate: '2026-04-30'\nrelated: []\n---\n\n"
        f"# {_INDEX_FEATURE} index\n",
        encoding="utf-8",
    )
    (vault / "adr").mkdir(parents=True, exist_ok=True)
    (vault / "adr" / f"2026-04-30-{_INDEX_FEATURE}-adr.md").write_text(
        f"---\ntags:\n  - '#adr'\n  - '#{_INDEX_FEATURE}'\n"
        "date: '2026-04-30'\nmodified: '2026-04-30'\nrelated: []\n---\n\n"
        f"# `{_INDEX_FEATURE}` adr\n\n## Description\n\nProse.\n",
        encoding="utf-8",
    )

    (vault / "plan").mkdir(parents=True, exist_ok=True)
    (vault / "plan" / f"{_PLAN_STEM}.md").write_text(
        "---\ntags:\n  - '#plan'\n  - '#boundary'\ndate: '2026-05-17'\n"
        "modified: '2026-05-17'\ntier: L2\nrelated: []\n---\n\n"
        "# `boundary` plan\n\n## Description\n\nProse.\n\n"
        "### Phase `P01` - one\n\n"
        "- [x] `P01.S01` - first; `src/foo.py`.\n"
        "- [x] `P01.S02` - second; `src/bar.py`.\n\n"
        "## Parallelization\n\nProse.\n\n## Verification\n\nProse.\n",
        encoding="utf-8",
    )
    folder = vault / "exec" / _FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    # ``body-v2`` deliberately: the 0.1.58 fold leaves that schema alone,
    # because the verb that authored it was still current in that release, and
    # the 0.1.74 fold is what consumes it - the records *and* the Phase
    # Summary their rows make removable. Seeding v2 therefore puts all three
    # deletions in one entry, so a single run of this fixture witnesses the
    # whole loss the authoring verb used to cause rather than part of it.
    for step in ("S01", "S02"):
        (folder / f"{_FOLDER}-P01-{step}.md").write_text(
            "---\ntags:\n  - '#exec'\n  - '#boundary'\ndate: '2026-05-17'\n"
            f"body_schema: 'body-v2'\nstep_id: '{step}'\n"
            f"related:\n  - '[[{_PLAN_STEM}]]'\n---\n\n"
            "# did a thing\n\n## Changes\n\n- `M` `src/foo.py`\n\n"
            "## Notes\n\nProse a consumer still reads.\n",
            encoding="utf-8",
        )
    (folder / f"{_FOLDER}-P01-summary.md").write_text(
        "---\ntags:\n  - '#exec'\n  - '#boundary'\ndate: '2026-05-17'\n"
        f"related:\n  - '[[{_PLAN_STEM}]]'\n---\n\n# summary\n\n## Changes\n\n"
        "- `M` `src/foo.py`\n",
        encoding="utf-8",
    )


def _exec_documents(root: Path) -> dict[str, bytes]:
    """Snapshot the execution records and Phase Summary by path and bytes.

    These are the documents the folds consume.  Comparing exact bytes rather
    than existence catches a fold that rewrote a record in place as well as one
    that unlinked it.
    """
    folder = root / ".vault" / "exec" / _FOLDER
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(folder.rglob("*"))
        if path.is_file()
    }


def _feature_indexes(root: Path) -> list[str]:
    """Every generated feature index in the workspace, by relative path."""
    return sorted(
        path.relative_to(root).as_posix()
        for path in (root / ".vault").rglob("*.index.md")
        if path.is_file()
    )


def _pending(root: Path) -> list[str]:
    """Names of the migrations the workspace still has outstanding."""
    _status, names = migration_status(root)
    return names


@pytest.fixture
def stale_workspace() -> Iterator[Path]:
    """An installed workspace rewound below every registered migration."""
    reset_config()
    reset_workspace_cache()
    root = Path(tempfile.mkdtemp(prefix="vsc-458-")).resolve()
    try:
        WorkspaceFactory(root).install("core")
        _seed(root)
        data = read_manifest_data(root)
        data.vaultspec_version = _REWIND_TO
        write_manifest_data(root, data)
        init_paths(root)
        reset_workspace_cache()
        yield root
    finally:
        reset_config()
        reset_workspace_cache()
        shutil.rmtree(root, ignore_errors=True)


def _assert_fixture_is_stale(root: Path) -> None:
    """Fail loudly if the fixture is not in the state the tests assume.

    Without this the untouched-bytes assertions below would pass vacuously the
    moment an entry retires or a manifest key is renamed - the failure mode
    where a data-safety test quietly stops testing anything.
    """
    status, names = migration_status(root)
    assert status is MigrationStatus.PENDING, f"fixture is not pending: {status}"
    for expected in ("index_subfolder", "exec_ledger_fold", "exec_ledger_only"):
        assert expected in names, names


class TestVaultAdd:
    """``vault add`` writes one document and converges one thing."""

    def test_it_relocates_the_legacy_index(self, stale_workspace: Path) -> None:
        """The half of the hook that must survive the narrowing.

        Removing the trigger outright was the other candidate resolution, and
        this is what it would have cost: a workspace left with the legacy
        layout under a verb that resolves its destination from the current
        schema, which is how one feature ends up with two tracked indexes.
        """
        _assert_fixture_is_stale(stale_workspace)
        assert _feature_indexes(stale_workspace) == [
            f".vault/{_INDEX_FEATURE}.index.md"
        ]

        result = WorkspaceFactory.wrap(stale_workspace).run(
            "vault", "add", "adr", "-f", "delta", "--title", "scoped-convergence"
        )

        assert result.exit_code == 0, result.stdout
        assert _feature_indexes(stale_workspace) == [
            f".vault/index/{_INDEX_FEATURE}.index.md"
        ], "the relocation an authoring write depends on must still happen"

    def test_it_relocates_the_index_and_deletes_no_record_or_summary(
        self, stale_workspace: Path
    ) -> None:
        """The whole decision of issue #458, in one command on one workspace.

        One ADR asked for; two execution records and a Phase Summary
        previously destroyed alongside it. ``exec_ledger_only`` is pending
        against this fixture and consumes every file compared here, as the
        paired recoverability test demonstrates by letting it. What the verb
        *does* converge is the relocation its own write depends on - so the
        assertions are stated together, because a fix that dropped either half
        would be a different defect rather than a partial one.
        """
        _assert_fixture_is_stale(stale_workspace)
        before = _exec_documents(stale_workspace)
        assert len(before) == 3, before

        result = WorkspaceFactory.wrap(stale_workspace).run(
            "vault", "add", "adr", "-f", "delta", "--title", "scoped-convergence"
        )

        assert result.exit_code == 0, result.stdout
        assert _exec_documents(stale_workspace) == before, (
            "an authoring verb must not rewrite or remove documents its "
            "caller never named"
        )
        assert _feature_indexes(stale_workspace) == [
            f".vault/index/{_INDEX_FEATURE}.index.md"
        ], "and must still converge where its own write lands"

    def test_it_writes_the_document_it_was_asked_for(
        self, stale_workspace: Path
    ) -> None:
        """The refusal must not be achieved by refusing the verb."""
        result = WorkspaceFactory.wrap(stale_workspace).run(
            "vault", "add", "adr", "-f", "delta", "--title", "scoped-convergence"
        )

        assert result.exit_code == 0, result.stdout
        created = sorted((stale_workspace / ".vault" / "adr").glob("*-delta-adr.md"))
        assert len(created) == 1, created

    def test_it_records_only_the_migration_it_ran(self, stale_workspace: Path) -> None:
        """The manifest must not claim work the verb declined to do.

        This is the assertion that separates a deferral from a data loss. If
        the version were bumped to the running package release, the content
        entries would read as applied, never run again, and no command would
        report them outstanding - the corpus would be permanently
        half-migrated with nothing saying so.
        """
        WorkspaceFactory.wrap(stale_workspace).run(
            "vault", "add", "adr", "-f", "delta", "--title", "scoped-convergence"
        )

        assert read_manifest_data(stale_workspace).vaultspec_version == _SCOPED_VERSION
        outstanding = _pending(stale_workspace)
        assert "index_subfolder" not in outstanding
        assert "exec_ledger_only" in outstanding
        assert "exec_ledger_fold" in outstanding

    def test_it_names_what_it_left_outstanding(
        self, stale_workspace: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        """Deferred is not the same as forgotten.

        A scoped run leaves the content entries pending on purpose, so the
        verb has to say so and name the command that applies them - otherwise
        the narrowing trades an unannounced deletion for an unannounced drift,
        which is the failure mode of issue #408 one layer up.
        """
        with caplog.at_level(logging.WARNING, logger=MIGRATION_LOGGER):
            WorkspaceFactory.wrap(stale_workspace).run(
                "vault", "add", "adr", "-f", "delta", "--title", "scoped-convergence"
            )

        notices = [
            record.getMessage()
            for record in caplog.records
            if record.name == MIGRATION_LOGGER
        ]
        assert notices, "an authoring verb must report the drift it left behind"
        assert any("exec_ledger_only" in notice for notice in notices), notices
        assert any("migrations run" in notice for notice in notices), notices


class TestFeatureIndex:
    """``vault feature index`` is the verb the split brain was reported against."""

    def test_it_ends_with_exactly_one_index_and_all_records_intact(
        self, stale_workspace: Path
    ) -> None:
        """Both halves of the boundary, in the one command that needs both.

        Regenerating an index against a legacy layout is what produced two
        tracked indexes for one feature with divergent ``related:``; folding
        the corpus while doing it is what produced the deletions. The verb
        must do the first and not the second.
        """
        _assert_fixture_is_stale(stale_workspace)
        before = _exec_documents(stale_workspace)

        result = WorkspaceFactory.wrap(stale_workspace).run(
            "vault", "feature", "index", "-f", _INDEX_FEATURE
        )

        assert result.exit_code == 0, result.stdout
        assert _feature_indexes(stale_workspace) == [
            f".vault/index/{_INDEX_FEATURE}.index.md"
        ]
        assert _exec_documents(stale_workspace) == before


class TestMcpCreate:
    """The rule is a property of the write, not of the surface."""

    async def test_create_converges_placement_and_deletes_nothing(
        self, stale_workspace: Path
    ) -> None:
        """The agent-facing authoring surface takes the same scoped hook.

        ``create`` is the surface an agent drives unattended, which makes the
        blast radius of a full-registry run there strictly worse than on the
        CLI: nobody is watching the retrospective report.
        """
        from vaultspec_core.mcp_server.app import create_server

        _assert_fixture_is_stale(stale_workspace)
        before = _exec_documents(stale_workspace)

        async with Client(create_server()) as client:
            result = await client.call_tool(
                "create",
                {
                    "documents": [
                        {
                            "type": "research",
                            "feature": _INDEX_FEATURE,
                            "title": "scoped convergence over mcp",
                        }
                    ]
                },
            )
        errors = [c.text for c in result.content if isinstance(c, TextContent)]
        assert not result.is_error, errors

        assert _feature_indexes(stale_workspace) == [
            f".vault/index/{_INDEX_FEATURE}.index.md"
        ]
        assert _exec_documents(stale_workspace) == before


class TestTheDeferralIsRecoverable:
    """A boundary that only refuses is a boundary that strands the workspace."""

    def test_an_explicit_run_after_an_authoring_verb_still_converges(
        self, stale_workspace: Path
    ) -> None:
        """The operator verb finishes what the authoring verb declined.

        Guards against "fixing" the deletion by making the content entries
        unreachable. They must still be one typed command away, and that
        command must find them pending rather than recorded as done.
        """
        WorkspaceFactory.wrap(stale_workspace).run(
            "vault", "add", "adr", "-f", "delta", "--title", "scoped-convergence"
        )
        assert len(_exec_documents(stale_workspace)) == 3, (
            "the authoring verb must have left all three alone"
        )

        result = WorkspaceFactory.wrap(stale_workspace).run("migrations", "run")

        assert result.exit_code == 0, result.stdout
        remaining = _exec_documents(stale_workspace)
        assert not [name for name in remaining if name.endswith("-summary.md")], (
            f"the authorised path must still remove the Phase Summary: {remaining}"
        )
        assert not [name for name in remaining if name.endswith("-P01-S01.md")], (
            f"the authorised path must still fold the records: {remaining}"
        )
        status, names = migration_status(stale_workspace)
        assert status is MigrationStatus.UP_TO_DATE, (status, names)
