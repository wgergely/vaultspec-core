"""The read side of the workspace must never converge the schema.

Issue #443: a read-only MCP ``find`` call against a workspace one version
behind ran the ``exec_ledger_only`` migration and deleted 47 tracked
documents - per-Step execution records and Phase Summaries - out of a clean
worktree.  The trigger sat inside
:func:`vaultspec_core.vaultcore.scanner.scan_vault`, the single call every
read shares, so every read carried a latent workspace-wide rewrite.

These tests pin the boundary that replaced it: a caller that only reads
observes the corpus as it stands, and a caller that explicitly asked to
converge still converges.  Both halves matter.  A fix that only silenced the
read side would let a workspace upgraded by a bare package install drift
forever, and a fix that only kept the write side would not close the issue.

Every fixture is a real installed workspace over a real temp directory
driven through the real CLI and the real in-memory MCP server.  No mocks, no
patches, no skips: the defect was a filesystem side effect, so only the
filesystem can witness its absence.
"""

from __future__ import annotations

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
from vaultspec_core.migrations import reset_workspace_cache
from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

if TYPE_CHECKING:
    from collections.abc import Iterator

pytestmark = [pytest.mark.unit]

_FOLDER = "2026-05-17-boundary"
_PLAN_STEM = "2026-05-17-boundary-plan"
_FEATURE = "boundary"

# The release whose migration deleted the tracked documents in issue #443.
# The workspace is rewound below it so ``exec_ledger_only`` is genuinely
# pending rather than merely registered.
_REWIND_TO = "0.1.73"


def _seed_incident_shape(root: Path) -> None:
    """Write the document set the incident's migration would consume.

    An L2 plan with a two-Step Phase, a per-Step execution record for each
    Step, and the Phase Summary those records make removable.  This is the
    exact shape ``exec_ledger_only`` folds and then unlinks, so if any read
    path still runs the registry these files are what disappears.
    """
    vault = root / ".vault"
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
    for step in ("S01", "S02"):
        (folder / f"{_FOLDER}-P01-{step}.md").write_text(
            "---\ntags:\n  - '#exec'\n  - '#boundary'\ndate: '2026-05-17'\n"
            f"body_schema: 'body-v1'\nstep_id: '{step}'\n"
            f"related:\n  - '[[{_PLAN_STEM}]]'\n---\n\n"
            "# did a thing\n\n## Scope\n\n- `src/foo.py`\n\n"
            "## Description\n\nProse.\n",
            encoding="utf-8",
        )
    (folder / f"{_FOLDER}-P01-summary.md").write_text(
        "---\ntags:\n  - '#exec'\n  - '#boundary'\ndate: '2026-05-17'\n"
        f"related:\n  - '[[{_PLAN_STEM}]]'\n---\n\n# summary\n\n## Changes\n\n"
        "- `M` `src/foo.py`\n",
        encoding="utf-8",
    )
    (vault / "adr").mkdir(parents=True, exist_ok=True)
    (vault / "adr" / f"2026-05-17-{_FEATURE}-adr.md").write_text(
        "---\ntags:\n  - '#adr'\n  - '#boundary'\ndate: '2026-05-17'\n"
        "modified: '2026-05-17'\nrelated: []\n---\n\n# `boundary` adr\n\n"
        "## Description\n\nProse.\n",
        encoding="utf-8",
    )


def _document_bytes(root: Path) -> dict[str, bytes]:
    """Snapshot every vault *document* by relative path and exact bytes.

    ``.vault/data/`` is excluded: it holds the graph cache and other runtime
    artifacts, which a read is entitled to write.  The boundary this module
    defends is about documents - the files a user tracks in Git - not about
    whether a read may warm a cache.
    """
    vault = root / ".vault"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(vault.rglob("*"))
        if path.is_file() and "data" not in path.relative_to(vault).parts
    }


@pytest.fixture
def pending_workspace() -> Iterator[Path]:
    """An installed workspace, seeded and rewound so a migration is pending."""
    reset_config()
    reset_workspace_cache()
    root = Path(tempfile.mkdtemp(prefix="vsc-443-")).resolve()
    try:
        WorkspaceFactory(root).install("core")
        _seed_incident_shape(root)
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


def _assert_pending(root: Path) -> None:
    """Fail loudly if the fixture is not actually in the pending state.

    Without this the unchanged-bytes assertions below would pass vacuously
    the moment a manifest key is renamed or ``exec_ledger_only`` retires.
    """
    from vaultspec_core.migrations import MigrationStatus, migration_status

    status, names = migration_status(root)
    assert status is MigrationStatus.PENDING, f"fixture is not pending: {status}"
    assert "exec_ledger_only" in names, names


async def test_find_leaves_vault_documents_untouched(pending_workspace: Path) -> None:
    """The incident call itself: ``find`` must not delete a single document.

    Drives the real ``find`` tool over the in-memory MCP transport with the
    arguments from the issue report, against a workspace where
    ``exec_ledger_only`` is genuinely pending, and compares every vault
    document's bytes before and after.  Before the fix this removed the two
    per-Step records and the Phase Summary and wrote a ledger.
    """
    from vaultspec_core.mcp_server.app import create_server

    _assert_pending(pending_workspace)
    before = _document_bytes(pending_workspace)

    async with Client(create_server()) as client:
        result = await client.call_tool(
            "find",
            {"feature": _FEATURE, "type": ["adr"], "body": "full", "limit": 5},
        )
    errors = [c.text for c in result.content if isinstance(c, TextContent)]
    assert not result.is_error, errors

    assert _document_bytes(pending_workspace) == before


def test_graph_construction_leaves_vault_documents_untouched(
    pending_workspace: Path,
) -> None:
    """Graph construction is a read, whichever caller reaches it.

    ``VaultGraph`` is the funnel every MCP query, ``vault list``, and
    ``vault graph`` share, so pinning it here covers the read surface more
    durably than pinning each caller.
    """
    from vaultspec_core.graph import VaultGraph

    _assert_pending(pending_workspace)
    before = _document_bytes(pending_workspace)

    graph = VaultGraph(pending_workspace)
    assert graph.get_features(), "the graph must still read the pre-migration corpus"

    assert _document_bytes(pending_workspace) == before


@pytest.mark.parametrize(
    "argv",
    [
        pytest.param(["vault", "list"], id="vault-list"),
        pytest.param(["vault", "check", "markdown"], id="vault-check-markdown"),
    ],
)
def test_read_verbs_leave_vault_documents_untouched(
    pending_workspace: Path, argv: list[str]
) -> None:
    """Read-only CLI verbs converge nothing either.

    ``vault check markdown`` is included because it used to reach the
    scanner with ``run_migrations`` set from whether a ``--feature`` filter
    was supplied - an unfiltered check therefore migrated the whole
    workspace as a side effect of reporting on it.
    """
    _assert_pending(pending_workspace)
    before = _document_bytes(pending_workspace)

    result = WorkspaceFactory.wrap(pending_workspace).run(*argv)

    assert result.exit_code == 0, result.stdout
    assert _document_bytes(pending_workspace) == before


def test_read_surfaces_the_pending_drift(
    pending_workspace: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """Silence is not the same as safety: a read must still name the drift.

    Refusing to migrate on a read is only half the boundary.  Without a
    notice, a workspace upgraded by a bare package install would be read
    through a legacy layout indefinitely with nothing ever saying so - the
    failure mode of issue #408, one layer up.  The warning names the pending
    entry and the command that applies it.
    """
    import logging

    from vaultspec_core.migrations import MIGRATION_LOGGER
    from vaultspec_core.vaultcore.scanner import scan_vault

    _assert_pending(pending_workspace)

    with caplog.at_level(logging.WARNING, logger=MIGRATION_LOGGER):
        list(scan_vault(pending_workspace))
        list(scan_vault(pending_workspace))

    notices = [
        record.getMessage()
        for record in caplog.records
        if record.name == MIGRATION_LOGGER
    ]
    assert len(notices) == 1, f"one notice per workspace per process: {notices}"
    assert "exec_ledger_only" in notices[0]
    assert "migrations run" in notices[0]


def test_migrations_run_still_converges(pending_workspace: Path) -> None:
    """The other half of the boundary: an explicit request still migrates.

    Guards against "fixing" the incident by making the registry unreachable.
    ``vaultspec-core migrations run`` is the authorised path, and against the
    same fixture it must do exactly what the read refused to do.
    """
    _assert_pending(pending_workspace)
    folder = pending_workspace / ".vault" / "exec" / _FOLDER
    summary = folder / f"{_FOLDER}-P01-summary.md"
    assert summary.exists()

    result = WorkspaceFactory.wrap(pending_workspace).run("migrations", "run")

    assert result.exit_code == 0, result.stdout
    assert not summary.exists(), "the authorised path must still converge"
