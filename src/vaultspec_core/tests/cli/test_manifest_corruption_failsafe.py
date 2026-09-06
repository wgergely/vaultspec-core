"""A corrupt provider manifest must refuse to migrate, not replay the registry.

``read_manifest_data`` returns a default :class:`ManifestData` on unreadable
JSON unless asked for ``strict``. On the migration trigger that default is
indistinguishable from a genuine v1.0 manifest - both carry an empty
``vaultspec_version`` - so a truncated ``providers.json`` presented itself as a
legacy workspace with every registered migration pending, including the two
that unlink documents, and the subsequent version bump then persisted the
default object over the evidence (issue #455).

Every test here builds a real installed workspace through ``WorkspaceFactory``
and corrupts the real manifest on disk. No mocks, no patches: the corruption is
a real truncated file and the refusal is the real CLI exit.
"""

from __future__ import annotations

import json
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.config import reset_config
from vaultspec_core.core.exceptions import VaultSpecError
from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data
from vaultspec_core.migrations import REGISTRY, reset_workspace_cache
from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

pytestmark = [pytest.mark.unit]


@pytest.fixture(autouse=True)
def reset_caches() -> Generator[None]:
    reset_config()
    reset_workspace_cache()
    yield
    reset_config()
    reset_workspace_cache()


def _manifest_path(workspace: Path) -> Path:
    return workspace / ".vaultspec" / "providers.json"


def _truncate_manifest(workspace: Path) -> bytes:
    """Truncate the real manifest mid-token and return the surviving bytes.

    This is the shape a kill inside a non-atomic manifest write leaves: a
    prefix of valid JSON that stops in the middle of a value.
    """
    path = _manifest_path(workspace)
    raw = path.read_bytes()
    truncated = raw[: len(raw) // 3]
    assert truncated, "the fixture needs a non-empty prefix to be meaningful"
    path.write_bytes(truncated)
    return truncated


def _plant_replay_victim(workspace: Path) -> Path:
    """Plant a document that only a replayed migration would remove.

    ``m_0_1_17_index_subfolder`` unlinks a ``*.index.md`` living outside the
    index directory whenever the canonical twin already exists. On a workspace
    whose manifest records the running version that migration is not pending,
    so the file is untouched; a replay deletes it outright, with no backup and
    no forward command that restores it.
    """
    docs = workspace / ".vault"
    (docs / "index").mkdir(parents=True, exist_ok=True)
    (docs / "adr").mkdir(parents=True, exist_ok=True)
    (docs / "index" / "auth.index.md").write_text(
        "---\ngenerated: true\ntags:\n  - '#index'\n  - '#auth'\n"
        "date: '2026-04-30'\nrelated: []\n---\n\n# canonical auth index\n",
        encoding="utf-8",
    )
    victim = docs / "adr" / "auth.index.md"
    victim.write_text(
        "# handwritten content the operator wants back\n", encoding="utf-8"
    )
    return victim


class TestCorruptManifestRefusesToMigrate:
    def test_run_pending_migrations_refuses_and_names_the_file(
        self, tmp_path: Path
    ) -> None:
        WorkspaceFactory(tmp_path).install("core")
        _truncate_manifest(tmp_path)

        from vaultspec_core.migrations import run_pending_migrations

        with pytest.raises(VaultSpecError) as caught:
            run_pending_migrations(tmp_path, use_cache=False)

        assert "Corrupt provider manifest" in str(caught.value)
        assert str(_manifest_path(tmp_path)) in str(caught.value)

    def test_refusal_carries_an_actionable_hint(self, tmp_path: Path) -> None:
        # The hard error replaces a silent, destructive recovery. It is only
        # the better trade if the operator is told what to do about it.
        WorkspaceFactory(tmp_path).install("core")
        _truncate_manifest(tmp_path)

        from vaultspec_core.migrations import run_pending_migrations

        with pytest.raises(VaultSpecError) as caught:
            run_pending_migrations(tmp_path, use_cache=False)

        assert caught.value.hint, "a refusal with no remedy is a dead end"
        assert "install" in caught.value.hint or "sync" in caught.value.hint

    def test_corrupt_manifest_does_not_replay_the_registry(
        self, tmp_path: Path
    ) -> None:
        # `vault add` converges through `ensure_migrated` before it authors,
        # because the schema decides where it writes. That is one of the four
        # surfaces still authorised to run the registry after issue #443
        # narrowed the trigger, and it is the one an ordinary user reaches
        # first.
        factory = WorkspaceFactory(tmp_path).install("core")
        victim = _plant_replay_victim(tmp_path)
        original = victim.read_bytes()
        _truncate_manifest(tmp_path)

        result = factory.run("vault", "add", "adr", "-f", "probe", "--title", "t")

        assert result.exit_code != 0
        assert victim.exists(), (
            "a corrupt manifest must not be read as a legacy workspace with "
            f"all {len(REGISTRY)} migrations pending"
        )
        assert victim.read_bytes() == original

    def test_explicit_migrations_run_refuses(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path).install("core")
        victim = _plant_replay_victim(tmp_path)
        _truncate_manifest(tmp_path)

        result = factory.run("migrations", "run")

        assert result.exit_code == 1
        assert victim.exists()

    def test_migrations_run_json_stays_well_formed(self, tmp_path: Path) -> None:
        # A refusal must not break a JSON consumer: the failure envelope is
        # still parseable and carries the remedy alongside the message.
        factory = WorkspaceFactory(tmp_path).install("core")
        _truncate_manifest(tmp_path)

        result = factory.run("migrations", "run", "--json")

        payload = json.loads(result.stdout)
        assert payload["status"] == "failed"
        assert "Corrupt provider manifest" in payload["data"]["error"]
        assert payload["data"]["hint"]

    def test_corrupt_manifest_is_not_overwritten(self, tmp_path: Path) -> None:
        # The second half of the failure: the driver used to persist the
        # default ManifestData it had synthesised, turning the corruption into
        # a valid manifest asserting nothing was ever installed.
        factory = WorkspaceFactory(tmp_path).install("core")
        truncated = _truncate_manifest(tmp_path)

        factory.run("migrations", "run")

        assert _manifest_path(tmp_path).read_bytes() == truncated, (
            "the evidence of corruption must survive the refusal"
        )

    def test_cli_reports_the_refusal_without_a_traceback(self, tmp_path: Path) -> None:
        # Run the real console entry point in a real subprocess: the in-process
        # CliRunner invokes the Typer app directly and so never exercises the
        # entry point's own reporting, which is exactly the surface an upgrading
        # user meets. `vault add` is the case with no handler of its own - the
        # refusal is raised by the convergence hook underneath it, not by
        # anything the command called deliberately.
        WorkspaceFactory(tmp_path).install("core")
        _truncate_manifest(tmp_path)

        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "vaultspec_core",
                "vault",
                "add",
                "adr",
                "-f",
                "probe",
                "--title",
                "t",
                "--target",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            timeout=180,
        )

        output = completed.stdout + completed.stderr
        assert completed.returncode == 1, output
        assert "Corrupt provider manifest" in output
        assert "Hint:" in output
        assert "Traceback" not in output, (
            "a corrupt manifest is a refusal the user has to act on, not a "
            "defect report they have to read a stack for"
        )

    def test_sync_force_recovers_the_workspace(self, tmp_path: Path) -> None:
        # The hint's remedy has to work. `sync --force` rebuilds the manifest
        # from what is actually on disk, after which the converging verbs run
        # again.
        factory = WorkspaceFactory(tmp_path).install("core")
        _truncate_manifest(tmp_path)
        assert factory.run("migrations", "run").exit_code == 1

        assert factory.run("sync", "--force").exit_code == 0

        assert json.loads(_manifest_path(tmp_path).read_text(encoding="utf-8"))
        assert factory.run("migrations", "run").exit_code == 0


class TestHealthyManifestsStillMigrate:
    def test_legacy_version_still_replays_every_migration(self, tmp_path: Path) -> None:
        # The guard must refuse *unreadable* manifests only. A genuine v1.0
        # manifest carries an empty version and must keep meaning "everything
        # is pending" (issue #408), which is the behaviour the corruption was
        # mistaken for in the first place.
        WorkspaceFactory(tmp_path).install("core")
        data = read_manifest_data(tmp_path)
        data.vaultspec_version = ""
        write_manifest_data(tmp_path, data)

        from vaultspec_core.migrations import list_pending

        assert len(list_pending(tmp_path)) == len(REGISTRY)

    def test_missing_manifest_is_still_a_no_op(self, tmp_path: Path) -> None:
        factory = WorkspaceFactory(tmp_path).install("core")
        factory.delete_manifest()

        from vaultspec_core.migrations import run_pending_migrations

        assert run_pending_migrations(tmp_path, use_cache=False) == []
