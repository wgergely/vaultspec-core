"""CLI-level consent behaviour for workspace hooks (GHSA-w5xf-54cr-fxcq).

The engine refuses to run an unapproved hook on its own; what these tests pin is
the surface around that refusal. A developer who clones a repository and runs the
documented ``sync`` must not execute the repository author's command, the
refusal must say why and how to resolve it, an unattended run must never answer
the question for the operator, and a developer who does approve must still get
their hooks on every later run.

Everything is real: a real installed workspace, real hook files, and an approved
run that really spawns a process whose only effect is to create an inert marker
inside the test's own ``tmp_path``. The consent ledger lives under the
machine-global VaultSpec home, so every invocation carries an environment whose
home is a directory the test owns - supplied through the CLI runner's own
environment argument, so the code under test still reads its real configuration
sources, and the developer's own ledger is never read or written.
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.cli import app
from vaultspec_core.tests.cli.workspace_factory import WorkspaceFactory

if TYPE_CHECKING:
    from pathlib import Path

    from typer.testing import CliRunner

pytestmark = [pytest.mark.unit]

EVENT = "config.synced"


def attended_env(home: Path) -> dict[str, str | None]:
    """Environment for a run with an operator's home and no CI marker."""
    return {
        "NO_COLOR": "1",
        "HOME": str(home),
        "USERPROFILE": str(home),
        "CI": None,
        "VAULTSPEC_NON_INTERACTIVE": None,
    }


def carried_workspace(tmp_path: Path, marker: Path) -> tuple[Path, Path]:
    """Install a workspace and give it the hook a checkout would carry.

    Returns the workspace root and the operator home the consent ledger will
    live under. The hook's command creates one file and exits: if ``marker``
    exists afterwards, the workspace's command executed.
    """
    root = tmp_path / "project"
    root.mkdir()
    WorkspaceFactory(root).install("claude")

    home = tmp_path / "operator-home"
    home.mkdir()

    script = tmp_path / "payload.py"
    script.write_text(
        f"import pathlib; pathlib.Path({str(marker)!r}).write_text('ran')",
        encoding="utf-8",
    )
    hooks_dir = root / ".vaultspec" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)
    (hooks_dir / "carried.yaml").write_text(
        f"event: {EVENT}\n"
        "enabled: true\n"
        "actions:\n"
        "  - type: shell\n"
        f"    command: {sys.executable.replace(chr(92), '/')} "
        f"{str(script).replace(chr(92), '/')}\n",
        encoding="utf-8",
    )
    return root, home


class TestNonInteractiveRunsFailClosed:
    """No operator means no approval - never an implicit one."""

    def test_hooks_run_without_a_terminal_does_not_execute(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        marker = tmp_path / "marker.txt"
        root, home = carried_workspace(tmp_path, marker)

        result = runner.invoke(
            app,
            ["spec", "hooks", "run", EVENT, "--target", str(root)],
            input="",
            env=attended_env(home),
        )

        assert not marker.exists()
        assert "untrusted" in result.output.lower()
        assert "spec hooks trust" in result.output

    def test_sync_without_a_terminal_does_not_execute_but_still_syncs(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        marker = tmp_path / "marker.txt"
        root, home = carried_workspace(tmp_path, marker)

        result = runner.invoke(
            app,
            ["sync", "all", "--target", str(root)],
            input="",
            env=attended_env(home),
        )

        assert not marker.exists(), "cloning and syncing executed the carried command"
        assert "untrusted" in result.output.lower()
        # Declining costs the hooks, not the sync: the provider pass still ran.
        assert (root / ".claude").is_dir()

    def test_json_mode_never_prompts_and_never_approves(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        marker = tmp_path / "marker.txt"
        root, home = carried_workspace(tmp_path, marker)

        runner.invoke(
            app,
            ["spec", "hooks", "run", EVENT, "--json", "--target", str(root)],
            input="y\n",
            env=attended_env(home),
        )

        assert not marker.exists()
        assert not (home / ".vaultspec" / "hook-trust.json").exists()

    def test_ci_environment_fails_closed(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        marker = tmp_path / "marker.txt"
        root, home = carried_workspace(tmp_path, marker)
        env = attended_env(home)
        env["CI"] = "1"

        runner.invoke(
            app,
            ["spec", "hooks", "run", EVENT, "--target", str(root)],
            input="y\n",
            env=env,
        )

        assert not marker.exists()
        assert not (home / ".vaultspec" / "hook-trust.json").exists()


class TestApprovalRestoresTheWorkflow:
    """One approval, and the legitimate workflow is unchanged from then on."""

    def test_trust_then_run_executes_the_hook(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        marker = tmp_path / "marker.txt"
        root, home = carried_workspace(tmp_path, marker)

        approved = runner.invoke(
            app,
            ["spec", "hooks", "trust", "--target", str(root)],
            env=attended_env(home),
        )
        assert approved.exit_code == 0

        result = runner.invoke(
            app,
            ["spec", "hooks", "run", EVENT, "--target", str(root)],
            input="",
            env=attended_env(home),
        )

        assert result.exit_code == 0
        assert marker.read_text(encoding="utf-8") == "ran"

    def test_approval_survives_across_runs_and_covers_sync(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        marker = tmp_path / "marker.txt"
        root, home = carried_workspace(tmp_path, marker)
        runner.invoke(
            app,
            ["spec", "hooks", "trust", "--target", str(root)],
            env=attended_env(home),
        )

        runner.invoke(
            app,
            ["sync", "all", "--target", str(root)],
            input="",
            env=attended_env(home),
        )

        assert marker.read_text(encoding="utf-8") == "ran"

    def test_revoke_restores_the_refusal(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        marker = tmp_path / "marker.txt"
        root, home = carried_workspace(tmp_path, marker)
        runner.invoke(
            app,
            ["spec", "hooks", "trust", "--target", str(root)],
            env=attended_env(home),
        )
        runner.invoke(
            app,
            ["spec", "hooks", "trust", "--revoke", "--target", str(root)],
            env=attended_env(home),
        )

        runner.invoke(
            app,
            ["spec", "hooks", "run", EVENT, "--target", str(root)],
            input="",
            env=attended_env(home),
        )

        assert not marker.exists()

    def test_list_reports_the_trust_state(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        root, home = carried_workspace(tmp_path, tmp_path / "marker.txt")
        listing = ["spec", "hooks", "list", "--json", "--target", str(root)]

        before = runner.invoke(app, listing, env=attended_env(home))
        assert '"trusted":false' in before.output.lower()

        runner.invoke(
            app,
            ["spec", "hooks", "trust", "--target", str(root)],
            env=attended_env(home),
        )
        after = runner.invoke(app, listing, env=attended_env(home))
        assert '"trusted":false' not in after.output.lower()
