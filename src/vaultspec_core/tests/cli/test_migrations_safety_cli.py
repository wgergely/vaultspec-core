"""Operator-facing behaviour of the destructive-migration safety net.

Covers the surface an operator actually touches:

- ``migrations run --dry-run`` enumerates every deletion and performs none,
  and its enumeration is *equal* to what the real run then removes;
- a non-interactive run proceeds rather than hanging on a dead stdin, and
  says what it is about to remove;
- ``--yes`` skips the question; declining it changes nothing;
- ``vault repair`` warns about the deletions before its preflight converges,
  not afterwards.

Real installed workspaces through the real CLI. No mocks, no patches, no
skips.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.config import reset_config
from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data
from vaultspec_core.migrations import reset_workspace_cache
from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory
from vaultspec_core.vaultcore.trash import trash_root

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path

pytestmark = [pytest.mark.unit]

_FOLDER = "2026-05-17-safety"
_PLAN_STEM = "2026-05-17-safety-plan"


@pytest.fixture(autouse=True)
def reset_caches() -> Generator[None]:
    reset_config()
    reset_workspace_cache()
    yield
    reset_config()
    reset_workspace_cache()


def _plant_foldable_corpus(root: Path, count: int = 3) -> list[Path]:
    """Plant per-Step records the ledger fold will remove, plus their plan."""
    plan_dir = root / ".vault" / "plan"
    plan_dir.mkdir(parents=True, exist_ok=True)
    steps = "\n".join(
        f"- [x] `P01.S{index:02d}` - step {index}; `src/mod{index}.py`."
        for index in range(1, count + 1)
    )
    (plan_dir / f"{_PLAN_STEM}.md").write_text(
        "---\ntags:\n  - '#plan'\n  - '#safety'\ndate: '2026-05-17'\n"
        "modified: '2026-05-17'\ntier: L2\nrelated: []\n---\n\n"
        "# `safety` plan\n\n## Description\n\nProse.\n\n"
        f"### Phase `P01` - one\n\n{steps}\n\n"
        "## Parallelization\n\nProse.\n\n## Verification\n\nProse.\n",
        encoding="utf-8",
    )
    folder = root / ".vault" / "exec" / _FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    records: list[Path] = []
    for index in range(1, count + 1):
        record = folder / f"{_FOLDER}-P01-S{index:02d}.md"
        record.write_text(
            "---\ntags:\n  - '#exec'\n  - '#safety'\ndate: '2026-05-17'\n"
            f"body_schema: 'body-v1'\nstep_id: 'S{index:02d}'\nrelated:\n"
            f"  - '[[{_PLAN_STEM}]]'\n---\n\n# step\n\n"
            f"## Scope\n\n- `src/mod{index}.py`\n\n## Description\n\nProse.\n",
            encoding="utf-8",
        )
        records.append(record)
    return records


def _rewind(root: Path, version: str = "0.1.57") -> None:
    data = read_manifest_data(root)
    data.vaultspec_version = version
    write_manifest_data(root, data)


def _stale_workspace(
    tmp_path: Path, count: int = 3
) -> tuple[WorkspaceFactory, list[Path]]:
    factory = WorkspaceFactory(tmp_path).install("core")
    records = _plant_foldable_corpus(factory.path, count)
    _rewind(factory.path)
    reset_workspace_cache()
    return factory, records


class TestDryRun:
    def test_dry_run_lists_the_deletions_and_removes_nothing(
        self, tmp_path: Path
    ) -> None:
        factory, records = _stale_workspace(tmp_path)
        before = {record: record.read_bytes() for record in records}

        result = factory.run("migrations", "run", "--dry-run")

        assert result.exit_code == 0, result.output
        for record in records:
            assert record.read_bytes() == before[record], (
                "a dry run must not touch a single byte"
            )
            assert record.name in result.output
        assert not trash_root(factory.path).exists()
        assert read_manifest_data(factory.path).vaultspec_version == "0.1.57"

    def test_dry_run_enumeration_equals_what_the_real_run_removes(
        self, tmp_path: Path
    ) -> None:
        """The equivalence that makes the preview worth reading.

        The JSON dry run's path list and the set of documents missing after
        a real run must be the same list, not merely the same size.
        """
        factory, _records = _stale_workspace(tmp_path, count=4)
        vault = factory.path / ".vault"
        before = {path for path in vault.rglob("*.md") if path.is_file()}

        preview = factory.run("migrations", "run", "--dry-run", "--json")
        assert preview.exit_code == 0, preview.output
        payload = json.loads(preview.output)["data"]
        previewed = sorted(
            path for migration in payload["migrations"] for path in migration["deletes"]
        )

        reset_workspace_cache()
        applied = factory.run("migrations", "run", "--yes")
        assert applied.exit_code == 0, applied.output

        after = {path for path in vault.rglob("*.md") if path.is_file()}
        removed = sorted(str(path) for path in before - after)
        assert previewed, "the fixture must give the migration something to remove"
        assert previewed == removed

    def test_dry_run_on_a_current_workspace_reports_nothing_pending(
        self, tmp_path: Path
    ) -> None:
        factory = WorkspaceFactory(tmp_path).install("core")

        result = factory.run("migrations", "run", "--dry-run")

        assert result.exit_code == 0, result.output
        assert "no pending migrations" in result.output


class TestConfirmation:
    def test_a_non_interactive_run_proceeds_and_warns(self, tmp_path: Path) -> None:
        """CI, MCP and piped stdin must never hang; they proceed, loudly."""
        factory, records = _stale_workspace(tmp_path)

        result = factory.run("migrations", "run")

        assert result.exit_code == 0, result.output
        assert "warning" in result.output
        assert ".trash" in result.output
        assert all(not record.exists() for record in records)

    def test_yes_skips_the_question(self, tmp_path: Path) -> None:
        factory, records = _stale_workspace(tmp_path)

        result = factory.run("migrations", "run", "--yes")

        assert result.exit_code == 0, result.output
        assert all(not record.exists() for record in records)
        assert "Remove" not in result.output

    def test_declining_at_a_terminal_changes_nothing(self, tmp_path: Path) -> None:
        from vaultspec_core.cli.migrations_cmd import _confirm_deletions

        factory, records = _stale_workspace(tmp_path)
        asked: list[str] = []

        def decline(prompt: str) -> bool:
            asked.append(prompt)
            return False

        proceed = _confirm_deletions(
            len(records), json_output=False, interactive=True, confirm_fn=decline
        )

        assert proceed is False
        assert asked and ".trash" in asked[0]
        assert all(record.exists() for record in records)
        assert not trash_root(factory.path).exists()

    def test_a_run_reports_where_the_backups_went(self, tmp_path: Path) -> None:
        factory, _records = _stale_workspace(tmp_path)

        result = factory.run("migrations", "run", "--yes")

        assert result.exit_code == 0, result.output
        snapshots = sorted(
            item for item in trash_root(factory.path).iterdir() if item.is_dir()
        )
        assert len(snapshots) == 1
        assert "backup" in result.output


class TestRepairWarnsBeforeConverging:
    def test_repair_reports_the_deletions_it_is_about_to_make(
        self, tmp_path: Path
    ) -> None:
        from vaultspec_core.vaultcore.repair import run_repair_pipeline

        factory, records = _stale_workspace(tmp_path)
        expected = sorted(
            record.relative_to(factory.path).as_posix() for record in records
        )

        run = run_repair_pipeline(factory.path)

        preflight = next(phase for phase in run.phases if phase["phase"] == "preflight")
        section = preflight["pending_deletions"]
        assert sorted(section["items"]) == expected, (
            "the warning must name the documents the preflight then removes"
        )
        assert section["total"] == len(records)
        assert any(
            entry.get("action") == "migration_deletions"
            and ".trash" in entry.get("message", "")
            for entry in run.journal
        ), "the run must record the warning it printed before converging"
        assert preflight["snapshots"], "the preflight must say where the copies went"
        assert all(not record.exists() for record in records)

    def test_a_clean_workspace_gets_no_deletion_warning(self, tmp_path: Path) -> None:
        from vaultspec_core.vaultcore.repair import run_repair_pipeline

        factory = WorkspaceFactory(tmp_path).install("core")

        run = run_repair_pipeline(factory.path)

        preflight = next(phase for phase in run.phases if phase["phase"] == "preflight")
        assert "pending_deletions" not in preflight

    def test_repair_dry_run_previews_the_deletions_without_making_them(
        self, tmp_path: Path
    ) -> None:
        from vaultspec_core.vaultcore.repair import run_repair_pipeline

        factory, records = _stale_workspace(tmp_path)

        run = run_repair_pipeline(factory.path, dry_run=True)

        preflight = next(phase for phase in run.phases if phase["phase"] == "preflight")
        assert preflight["pending_deletions"]["total"] == len(records)
        assert all(record.exists() for record in records)
        assert not trash_root(factory.path).exists()
