"""Live integration tests for every vaultspec-core CLI command.

Tests run against a synthetic vault corpus.  No mocks, patches, or stubs.
Every command receives ``--target`` at the *subcommand* level (not the root
callback) to prove uniform support.

The ``synthetic_project`` fixture from conftest.py provides a fresh
synthetic vault corpus for each test so mutations are isolated and cleanup
is automatic.

Tests are parametrized wherever possible so ``pytest-randomly`` (or
``-p randomly``) can shuffle execution order and surface state leakage.
"""

from __future__ import annotations

import os
import subprocess
import sys
from typing import TYPE_CHECKING

import pytest
from typer.testing import CliRunner, Result

from vaultspec_core.cli import app
from vaultspec_core.vaultcore import vault_today

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration]


@pytest.fixture(scope="module")
def cli() -> CliRunner:
    return CliRunner(env={"NO_COLOR": "1"})


# ── helpers ─────────────────────────────────────────────────────────


def _run(cli: CliRunner, project: Path, *args: str, input: str | None = None) -> Result:
    """Invoke CLI with ``--target`` on the **subcommand**, not the root.

    This proves that every command accepts ``--target`` directly.
    The target flag is inserted at a random valid position among the
    trailing options to surface ordering bugs.
    """
    cmd_args = [*list(args), "--target", str(project)]
    return cli.invoke(app, cmd_args, input=input)


def _run_root_target(cli: CliRunner, project: Path, *args: str) -> Result:
    """Invoke CLI with ``--target`` on the **root** callback (legacy form)."""
    return cli.invoke(app, ["--target", str(project), *args])


# ═══════════════════════════════════════════════════════════════════
# Parametrized: --target accepted by every read-only command
# ═══════════════════════════════════════════════════════════════════

# Commands that MUST exit 0.
_COMMANDS_EXIT_0: list[tuple[str, list[str]]] = [
    # sync
    ("sync-all", ["sync"]),
    ("sync-dry-run", ["sync", "--dry-run"]),
    ("sync-force", ["sync", "--force"]),
    ("sync-claude", ["sync", "claude"]),
    ("sync-gemini", ["sync", "gemini"]),
    ("sync-antigravity", ["sync", "antigravity"]),
    ("sync-codex", ["sync", "codex"]),
    # spec rules
    ("spec-rules-list", ["spec", "rules", "list"]),
    ("spec-rules-sync", ["spec", "rules", "sync"]),
    ("spec-rules-sync-dry", ["spec", "rules", "sync", "--dry-run"]),
    # spec skills
    ("spec-skills-list", ["spec", "skills", "list"]),
    ("spec-skills-sync", ["spec", "skills", "sync"]),
    ("spec-skills-sync-dry", ["spec", "skills", "sync", "--dry-run"]),
    # spec agents
    ("spec-agents-list", ["spec", "agents", "list"]),
    ("spec-agents-sync", ["spec", "agents", "sync"]),
    ("spec-agents-sync-dry", ["spec", "agents", "sync", "--dry-run"]),
    # spec system
    ("spec-system-show", ["spec", "system", "show"]),
    ("spec-system-sync", ["spec", "system", "sync"]),
    ("spec-system-sync-dry", ["spec", "system", "sync", "--dry-run"]),
    # spec hooks
    ("spec-hooks-list", ["spec", "hooks", "list"]),
    # vault query
    ("vault-stats", ["vault", "stats"]),
    ("vault-stats-feature", ["vault", "stats", "--feature", "dispatch"]),
    ("vault-list", ["vault", "list"]),
    ("vault-list-adr", ["vault", "list", "adr"]),
    ("vault-list-feature", ["vault", "list", "--feature", "dispatch"]),
    # vault graph
    ("vault-graph-tree", ["vault", "graph"]),
    ("vault-graph-json", ["vault", "graph", "--json"]),
    ("vault-graph-metrics", ["vault", "graph", "--metrics"]),
    ("vault-graph-ascii", ["vault", "graph", "--ascii"]),
    ("vault-graph-feature", ["vault", "graph", "--feature", "dispatch"]),
    # vault feature
    ("vault-feature-list", ["vault", "feature", "list"]),
    ("vault-feature-list-orphaned", ["vault", "feature", "list", "--orphaned"]),
]

# Check commands: exit 1 means "issues found" (correct diagnostic behavior).
# These are tested separately to verify --target acceptance AND that they
# produce diagnostic output (not that the corpus is clean).
_COMMANDS_CHECK: list[tuple[str, list[str]]] = [
    ("vault-check-all", ["vault", "check", "all"]),
    ("vault-check-orphans", ["vault", "check", "orphans"]),
    ("vault-check-frontmatter", ["vault", "check", "frontmatter"]),
    ("vault-check-links", ["vault", "check", "links"]),
    ("vault-check-features", ["vault", "check", "features"]),
    ("vault-check-references", ["vault", "check", "references"]),
    ("vault-check-schema", ["vault", "check", "schema"]),
    ("vault-check-structure", ["vault", "check", "structure"]),
    ("vault-check-verbose", ["vault", "check", "all", "--verbose"]),
    ("vault-check-feature", ["vault", "check", "all", "--feature", "dispatch"]),
]


@pytest.mark.parametrize(
    "cmd_id, args",
    _COMMANDS_EXIT_0,
    ids=[c[0] for c in _COMMANDS_EXIT_0],
)
def test_subcommand_target_exit_0(
    cli: CliRunner, synthetic_project: Path, cmd_id: str, args: list[str]
) -> None:
    """Every non-check command accepts --target on the subcommand and exits 0."""
    result = _run(cli, synthetic_project, *args)
    assert result.exit_code == 0, f"[{cmd_id}] exit={result.exit_code}\n{result.output}"


@pytest.mark.parametrize(
    "cmd_id, args",
    _COMMANDS_EXIT_0,
    ids=[c[0] for c in _COMMANDS_EXIT_0],
)
def test_root_target_exit_0(
    cli: CliRunner, synthetic_project: Path, cmd_id: str, args: list[str]
) -> None:
    """Same commands accept --target on the root callback (backward compat)."""
    result = _run_root_target(cli, synthetic_project, *args)
    assert result.exit_code == 0, f"[{cmd_id}] exit={result.exit_code}\n{result.output}"


@pytest.mark.parametrize(
    "cmd_id, args",
    _COMMANDS_CHECK,
    ids=[c[0] for c in _COMMANDS_CHECK],
)
def test_check_subcommand_target(
    cli: CliRunner, synthetic_project: Path, cmd_id: str, args: list[str]
) -> None:
    """Check commands accept --target on the subcommand and produce output.

    These commands exit 1 when they find issues in the corpus  - that's
    correct diagnostic behavior.  The test verifies the command accepted
    ``--target``, ran against the correct directory, and produced output.
    An exit code of 2+ would indicate a crash, not a diagnostic finding.
    """
    result = _run(cli, synthetic_project, *args)
    assert result.exit_code != 2, (
        f"[{cmd_id}] crashed: exit={result.exit_code}\n{result.output}"
    )
    assert len(result.output.strip()) > 0, f"[{cmd_id}] produced no output"


@pytest.mark.parametrize(
    "cmd_id, args",
    _COMMANDS_CHECK,
    ids=[c[0] for c in _COMMANDS_CHECK],
)
def test_check_root_target(
    cli: CliRunner, synthetic_project: Path, cmd_id: str, args: list[str]
) -> None:
    """Check commands accept root --target and produce output."""
    result = _run_root_target(cli, synthetic_project, *args)
    assert result.exit_code != 2, (
        f"[{cmd_id}] crashed: exit={result.exit_code}\n{result.output}"
    )
    assert len(result.output.strip()) > 0, f"[{cmd_id}] produced no output"


# ═══════════════════════════════════════════════════════════════════
# Parametrized: --target in help text
# ═══════════════════════════════════════════════════════════════════

_HELP_SURFACES: list[list[str]] = [
    ["--help"],
    ["install", "--help"],
    ["uninstall", "--help"],
    ["sync", "--help"],
    ["spec", "--help"],
    ["spec", "rules", "list", "--help"],
    ["spec", "rules", "add", "--help"],
    ["spec", "rules", "show", "--help"],
    ["spec", "rules", "edit", "--help"],
    ["spec", "rules", "remove", "--help"],
    ["spec", "rules", "rename", "--help"],
    ["spec", "rules", "sync", "--help"],
    ["spec", "skills", "list", "--help"],
    ["spec", "skills", "add", "--help"],
    ["spec", "skills", "show", "--help"],
    ["spec", "skills", "sync", "--help"],
    ["spec", "agents", "list", "--help"],
    ["spec", "agents", "add", "--help"],
    ["spec", "agents", "show", "--help"],
    ["spec", "agents", "sync", "--help"],
    ["spec", "system", "show", "--help"],
    ["spec", "system", "sync", "--help"],
    ["spec", "hooks", "list", "--help"],
    ["spec", "hooks", "run", "--help"],
    ["vault", "--help"],
    ["vault", "add", "--help"],
    ["vault", "stats", "--help"],
    ["vault", "list", "--help"],
    ["vault", "graph", "--help"],
    ["vault", "check", "all", "--help"],
    ["vault", "check", "orphans", "--help"],
    ["vault", "check", "frontmatter", "--help"],
    ["vault", "check", "links", "--help"],
    ["vault", "check", "features", "--help"],
    ["vault", "check", "references", "--help"],
    ["vault", "check", "schema", "--help"],
    ["vault", "check", "structure", "--help"],
    ["vault", "feature", "list", "--help"],
    ["vault", "feature", "archive", "--help"],
    ["vault", "feature", "unarchive", "--help"],
]


@pytest.mark.parametrize(
    "args",
    _HELP_SURFACES,
    ids=[" ".join(a) for a in _HELP_SURFACES],
)
def test_help_exits_zero(cli: CliRunner, args: list[str]) -> None:
    result = cli.invoke(app, args)
    assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"


# Commands where --target MUST appear in help text (leaf commands, not groups)
_TARGET_IN_HELP: list[list[str]] = [
    a
    for a in _HELP_SURFACES
    if a != ["--help"]
    and a != ["spec", "--help"]
    and a != ["vault", "--help"]
    and a != ["vault", "check", "--help"]
]


@pytest.mark.parametrize(
    "args",
    _TARGET_IN_HELP,
    ids=[" ".join(a) for a in _TARGET_IN_HELP],
)
def test_target_in_help_text(cli: CliRunner, args: list[str]) -> None:
    """Every leaf command advertises --target in its help output."""
    result = cli.invoke(app, args)
    assert result.exit_code == 0
    assert "--target" in result.output, (
        f"--target missing from help: {' '.join(args)}\n{result.output[:500]}"
    )


# ═══════════════════════════════════════════════════════════════════
# install (parametrized providers)
# ═══════════════════════════════════════════════════════════════════

_INSTALL_PROVIDERS = ["all", "core", "claude", "gemini", "antigravity", "codex"]


class TestInstall:
    @pytest.mark.parametrize("provider", _INSTALL_PROVIDERS)
    def test_install_provider(
        self, cli: CliRunner, tmp_path: Path, provider: str
    ) -> None:
        target = tmp_path / f"inst-{provider}"
        target.mkdir()
        result = cli.invoke(app, ["install", "--target", str(target), provider])
        assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"
        assert (target / ".vaultspec").is_dir()

    def test_install_creates_single_level_dir(
        self, cli: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "new-project"
        result = cli.invoke(app, ["install", "--target", str(target)])
        assert result.exit_code == 0
        assert target.is_dir()
        assert (target / ".vaultspec").is_dir()

    def test_install_rejects_deep_nonexistent(
        self, cli: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "a" / "b" / "c"
        result = cli.invoke(app, ["install", "--target", str(target)])
        assert result.exit_code != 0
        assert not (tmp_path / "a").exists()

    def test_install_dry_run_no_side_effects(
        self, cli: CliRunner, tmp_path: Path
    ) -> None:
        target = tmp_path / "dry"
        target.mkdir()
        result = cli.invoke(app, ["install", "--target", str(target), "--dry-run"])
        assert result.exit_code == 0
        assert not (target / ".vaultspec").exists()

    def test_install_force_over_existing(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        result = cli.invoke(
            app, ["install", "--target", str(synthetic_project), "--force"]
        )
        assert result.exit_code == 0
        assert (synthetic_project / ".vaultspec").is_dir()

    def test_install_upgrade(self, cli: CliRunner, synthetic_project: Path) -> None:
        result = cli.invoke(
            app, ["install", "--target", str(synthetic_project), "--upgrade"]
        )
        assert result.exit_code == 0

    def test_install_without_force_fails_if_exists(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        result = cli.invoke(app, ["install", "--target", str(synthetic_project)])
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# sync (parametrized providers)
# ═══════════════════════════════════════════════════════════════════

_SYNC_PROVIDERS = ["all", "claude", "gemini", "antigravity", "codex"]


class TestSync:
    @pytest.mark.parametrize("provider", _SYNC_PROVIDERS)
    def test_sync_provider(
        self, cli: CliRunner, synthetic_project: Path, provider: str
    ) -> None:
        result = _run(cli, synthetic_project, "sync", provider)
        assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"

    def test_sync_writes_to_target_not_cwd(self, synthetic_project: Path) -> None:
        """Remove a synced file, re-sync, confirm it reappears at --target."""
        synced = synthetic_project / ".claude" / "rules" / "vaultspec.builtin.md"
        if synced.exists():
            synced.unlink()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vaultspec_core",
                "sync",
                "--target",
                str(synthetic_project),
            ],
            cwd=synthetic_project,
            env={**os.environ, "NO_COLOR": "1"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert synced.exists(), "sync did not regenerate file at --target"

    def test_sync_all_fires_the_targets_own_hooks_not_the_cwds(
        self, tmp_path: Path
    ) -> None:
        """The ``config.synced`` hook fired by ``sync --target`` must load
        its definition from the *target* workspace, not the process CWD.

        ``sync --target`` deliberately reads its source content (rules,
        skills, agents) from the CWD workspace while writing to the target -
        the right model for a sync. Hooks are different: they react to an
        event that just happened *to* a workspace, so the hook that fires
        must be declared by the workspace that was actually synced. Uses a
        real subprocess (not ``CliRunner``) with a genuinely different
        process CWD, and clears ``PYTEST_CURRENT_TEST`` from its environment
        so the real CWD/target split path activates exactly as it does
        outside tests (see ``_resolve_framework_root``'s pytest guard in
        ``cli/_target.py``) - the actual bug only reproduces in that path.
        """
        from vaultspec_core.core.commands import install_run

        cwd_workspace = tmp_path / "cwd-workspace"
        target_workspace = tmp_path / "target-workspace"
        cwd_workspace.mkdir()
        target_workspace.mkdir()
        install_run(path=cwd_workspace, provider="all", dry_run=False, force=True)
        install_run(path=target_workspace, provider="all", dry_run=False, force=True)

        marker_cwd = cwd_workspace / "fired-from-cwd.txt"
        marker_target = target_workspace / "fired-from-target.txt"
        # A helper script per marker avoids the Windows shlex quoting pitfall
        # of embedding quoted Python source directly in a YAML command
        # string (see TestFireHooksIntegration in hooks/tests/test_hooks.py).
        script_cwd = tmp_path / "mark_cwd.py"
        script_target = tmp_path / "mark_target.py"
        script_cwd.write_text(
            f"import pathlib; pathlib.Path({str(marker_cwd)!r}).touch()",
            encoding="utf-8",
        )
        script_target.write_text(
            f"import pathlib; pathlib.Path({str(marker_target)!r}).touch()",
            encoding="utf-8",
        )
        (cwd_workspace / ".vaultspec" / "hooks" / "marker.yaml").write_text(
            "event: config.synced\nenabled: true\nactions:\n"
            f"  - type: shell\n    command: {sys.executable} {script_cwd}\n",
            encoding="utf-8",
        )
        (target_workspace / ".vaultspec" / "hooks" / "marker.yaml").write_text(
            "event: config.synced\nenabled: true\nactions:\n"
            f"  - type: shell\n    command: {sys.executable} {script_target}\n",
            encoding="utf-8",
        )

        env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
        env["NO_COLOR"] = "1"
        # Point the child process's consent ledger at a directory this test
        # owns, so approving hooks here never reaches the developer's own
        # ledger, and no approval the developer already holds can reach here.
        operator_home = tmp_path / "operator-home"
        operator_home.mkdir()
        env["HOME"] = str(operator_home)
        env["USERPROFILE"] = str(operator_home)

        def _run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, "-m", "vaultspec_core", *args],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=30,
            )

        # Approve BOTH workspaces' hooks. Approving only the target's would
        # leave "the CWD hook did not fire" explainable by it being untrusted
        # rather than by it never having been loaded, which is the claim this
        # test exists to make. With both approved, consent cannot be the
        # reason, so the markers speak only about which workspace was read.
        for workspace in (cwd_workspace, target_workspace):
            approved = _run_cli(
                "spec", "hooks", "trust", "--target", str(workspace), cwd=workspace
            )
            assert approved.returncode == 0, approved.stdout + approved.stderr

        result = _run_cli(
            "sync",
            "all",
            "--target",
            str(target_workspace),
            "--force",
            cwd=cwd_workspace,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        assert marker_target.exists(), (
            "config.synced must fire the target workspace's own hook, not "
            "the CWD workspace's"
        )
        assert not marker_cwd.exists(), (
            "config.synced must not execute the CWD workspace's hook when "
            "syncing a different --target"
        )

    def test_sync_asks_about_the_targets_hooks_not_the_cwds(
        self, tmp_path: Path
    ) -> None:
        """The consent notice must name the hooks that are about to run.

        ``sync --target`` fires the target workspace's hooks while its
        ambient context still reflects the CWD/source split. A consent gate
        that resolved the hooks directory its own way would therefore show
        the operator one workspace's commands and withhold the other's - and
        an operator who approved what they were shown would still not have
        approved what would run. The gate must read the same directory the
        firing code reads.

        Same real-subprocess shape as the sibling test above, and for the
        same reason: the CWD/target split path only activates outside pytest.
        """
        from vaultspec_core.core.commands import install_run

        cwd_workspace = tmp_path / "cwd-workspace"
        target_workspace = tmp_path / "target-workspace"
        cwd_workspace.mkdir()
        target_workspace.mkdir()
        install_run(path=cwd_workspace, provider="all", dry_run=False, force=True)
        install_run(path=target_workspace, provider="all", dry_run=False, force=True)

        # Two commands that differ only by a token unique to each workspace,
        # so the notice's text says unambiguously which one it is describing.
        for workspace, tag in (
            (cwd_workspace, "cwd-only-token"),
            (target_workspace, "target-only-token"),
        ):
            (workspace / ".vaultspec" / "hooks" / "marker.yaml").write_text(
                "event: config.synced\nenabled: true\nactions:\n"
                f"  - type: shell\n    command: {sys.executable} -c {tag}\n",
                encoding="utf-8",
            )

        env = {k: v for k, v in os.environ.items() if k != "PYTEST_CURRENT_TEST"}
        env["NO_COLOR"] = "1"
        operator_home = tmp_path / "operator-home"
        operator_home.mkdir()
        env["HOME"] = str(operator_home)
        env["USERPROFILE"] = str(operator_home)

        # Neither workspace is approved, so the run refuses and explains.
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vaultspec_core",
                "sync",
                "all",
                "--target",
                str(target_workspace),
                "--force",
            ],
            cwd=cwd_workspace,
            env=env,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr

        notice = result.stdout + result.stderr
        assert "target-only-token" in notice, (
            "the consent notice must describe the hooks the target workspace "
            "declares, because those are the ones this sync would run"
        )
        assert "cwd-only-token" not in notice, (
            "the consent notice must not describe the CWD workspace's hooks, "
            "which this sync will never run"
        )

    @pytest.mark.parametrize("flag", ["--dry-run", "--force"])
    def test_sync_flags(
        self, cli: CliRunner, synthetic_project: Path, flag: str
    ) -> None:
        result = _run(cli, synthetic_project, "sync", flag)
        assert result.exit_code == 0

    def test_sync_core_rejected(self, cli: CliRunner, synthetic_project: Path) -> None:
        result = _run(cli, synthetic_project, "sync", "core")
        assert result.exit_code != 0

    def test_sync_unknown_provider_fails(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        result = _run(cli, synthetic_project, "sync", "nonexistent")
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# uninstall (parametrized providers)
# ═══════════════════════════════════════════════════════════════════


class TestUninstall:
    def test_requires_force(self, cli: CliRunner, synthetic_project: Path) -> None:
        result = _run(cli, synthetic_project, "uninstall")
        assert result.exit_code != 0
        assert "--force" in result.output

    def test_dry_run_no_removal(self, cli: CliRunner, synthetic_project: Path) -> None:
        result = _run(cli, synthetic_project, "uninstall", "--dry-run")
        assert result.exit_code == 0
        assert (synthetic_project / ".vaultspec").exists()

    def test_force_preserves_vault(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        result = cli.invoke(
            app, ["uninstall", "--target", str(synthetic_project), "--force"]
        )
        assert result.exit_code == 0
        assert (synthetic_project / ".vault").is_dir()
        assert not (synthetic_project / ".vaultspec").exists()

    def test_force_remove_vault(self, cli: CliRunner, synthetic_project: Path) -> None:
        result = cli.invoke(
            app,
            [
                "uninstall",
                "--target",
                str(synthetic_project),
                "--force",
                "--remove-vault",
            ],
        )
        assert result.exit_code == 0
        assert not (synthetic_project / ".vault").exists()
        assert not (synthetic_project / ".vaultspec").exists()

    @pytest.mark.parametrize(
        "provider",
        ["claude", "gemini", "antigravity", "codex"],
    )
    def test_per_provider_uninstall(
        self, cli: CliRunner, synthetic_project: Path, provider: str
    ) -> None:
        result = cli.invoke(
            app,
            ["uninstall", "--target", str(synthetic_project), provider, "--force"],
        )
        assert result.exit_code == 0
        assert (synthetic_project / ".vaultspec").exists()


# ═══════════════════════════════════════════════════════════════════
# spec rules lifecycle (CRUD)
# ═══════════════════════════════════════════════════════════════════


class TestSpecRules:
    def test_add_show_remove_lifecycle(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        # add -- use a unique name to avoid collisions with builtins
        result = _run(
            cli,
            synthetic_project,
            "spec",
            "rules",
            "add",
            "lifecycle-test-rule",
            input="Live rule body",
        )
        assert result.exit_code == 0
        rule_path = (
            synthetic_project / ".vaultspec" / "rules" / "lifecycle-test-rule.md"
        )
        assert rule_path.exists()

        # show
        result = _run(
            cli, synthetic_project, "spec", "rules", "show", "lifecycle-test-rule"
        )
        assert result.exit_code == 0
        assert "Live rule body" in result.output

        # remove
        result = _run(
            cli,
            synthetic_project,
            "spec",
            "rules",
            "remove",
            "lifecycle-test-rule",
            "--force",
        )
        assert result.exit_code == 0
        assert not rule_path.exists()

    def test_rename(self, cli: CliRunner, synthetic_project: Path) -> None:
        _run(
            cli,
            synthetic_project,
            "spec",
            "rules",
            "add",
            "rename-src",
            "--body",
            "To rename",
        )
        result = _run(
            cli,
            synthetic_project,
            "spec",
            "rules",
            "rename",
            "rename-src",
            "rename-dst",
        )
        assert result.exit_code == 0
        dst = synthetic_project / ".vaultspec" / "rules" / "rename-dst.md"
        assert dst.exists()

    def test_add_force_overwrites(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        _run(
            cli,
            synthetic_project,
            "spec",
            "rules",
            "add",
            "overwrite-me",
            "--body",
            "v1",
        )
        result = _run(
            cli,
            synthetic_project,
            "spec",
            "rules",
            "add",
            "overwrite-me",
            "--body",
            "v2",
            "--force",
        )
        assert result.exit_code == 0
        content = (
            synthetic_project / ".vaultspec" / "rules" / "overwrite-me.md"
        ).read_text(encoding="utf-8")
        assert "v2" in content

    @pytest.mark.parametrize(
        "subcmd",
        ["show", "edit"],
    )
    def test_missing_resource_fails(
        self, cli: CliRunner, synthetic_project: Path, subcmd: str
    ) -> None:
        result = _run(
            cli, synthetic_project, "spec", "rules", subcmd, "nonexistent-xyz"
        )
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# spec skills lifecycle (CRUD)
# ═══════════════════════════════════════════════════════════════════


class TestSpecSkills:
    def test_add_show_remove_lifecycle(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        # add
        result = _run(
            cli,
            synthetic_project,
            "spec",
            "skills",
            "add",
            "vaultspec-live-skill",
            "--description",
            "Live skill test",
        )
        assert result.exit_code == 0
        skill_dir = synthetic_project / ".vaultspec" / "skills" / "vaultspec-live-skill"
        assert skill_dir.is_dir()

        # show
        result = _run(
            cli, synthetic_project, "spec", "skills", "show", "vaultspec-live-skill"
        )
        assert result.exit_code == 0

        # remove
        result = _run(
            cli,
            synthetic_project,
            "spec",
            "skills",
            "remove",
            "vaultspec-live-skill",
            "--force",
        )
        assert result.exit_code == 0
        assert not skill_dir.exists()

    def test_rename(self, cli: CliRunner, synthetic_project: Path) -> None:
        _run(
            cli,
            synthetic_project,
            "spec",
            "skills",
            "add",
            "vaultspec-old-skill",
            "--description",
            "Old",
        )
        result = _run(
            cli,
            synthetic_project,
            "spec",
            "skills",
            "rename",
            "vaultspec-old-skill",
            "vaultspec-new-skill",
        )
        assert result.exit_code == 0
        new = synthetic_project / ".vaultspec" / "skills" / "vaultspec-new-skill"
        assert new.is_dir()

    @pytest.mark.parametrize("subcmd", ["show", "edit"])
    def test_missing_resource_fails(
        self, cli: CliRunner, synthetic_project: Path, subcmd: str
    ) -> None:
        result = _run(
            cli, synthetic_project, "spec", "skills", subcmd, "nonexistent-xyz"
        )
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# spec agents lifecycle (CRUD)
# ═══════════════════════════════════════════════════════════════════


class TestSpecAgents:
    def test_add_show_remove_lifecycle(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        # add
        result = _run(
            cli,
            synthetic_project,
            "spec",
            "agents",
            "add",
            "live-agent",
            "--description",
            "Live agent test",
        )
        assert result.exit_code == 0
        agent_path = synthetic_project / ".vaultspec" / "agents" / "live-agent.md"
        assert agent_path.exists()

        # show
        result = _run(cli, synthetic_project, "spec", "agents", "show", "live-agent")
        assert result.exit_code == 0

        # remove
        result = _run(
            cli,
            synthetic_project,
            "spec",
            "agents",
            "remove",
            "live-agent",
            "--force",
        )
        assert result.exit_code == 0
        assert not agent_path.exists()

    def test_rename(self, cli: CliRunner, synthetic_project: Path) -> None:
        _run(
            cli,
            synthetic_project,
            "spec",
            "agents",
            "add",
            "old-agent",
            "--description",
            "Old",
        )
        result = _run(
            cli,
            synthetic_project,
            "spec",
            "agents",
            "rename",
            "old-agent",
            "new-agent",
        )
        assert result.exit_code == 0
        new = synthetic_project / ".vaultspec" / "agents" / "new-agent.md"
        assert new.exists()

    def test_show_missing_fails(self, cli: CliRunner, synthetic_project: Path) -> None:
        result = _run(
            cli, synthetic_project, "spec", "agents", "show", "nonexistent-xyz"
        )
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# spec hooks
# ═══════════════════════════════════════════════════════════════════


class TestSpecHooks:
    def test_run_unknown_event_fails(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        result = _run(
            cli, synthetic_project, "spec", "hooks", "run", "nonexistent.event"
        )
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# vault add (parametrized doc types)
# ═══════════════════════════════════════════════════════════════════

_DOC_TYPES = ["adr", "audit", "plan", "research", "reference"]


class TestVaultAdd:
    @pytest.mark.parametrize("doc_type", _DOC_TYPES)
    def test_add_doc_type(
        self, cli: CliRunner, synthetic_project: Path, doc_type: str
    ) -> None:
        feat = f"live-{doc_type}"
        result = _run(
            cli, synthetic_project, "vault", "add", doc_type, "--feature", feat
        )
        assert result.exit_code == 0

    def test_add_exec_is_refused(self, cli: CliRunner, synthetic_project: Path) -> None:
        """Execution is logged with `vault exec log`, never scaffolded."""
        result = _run(
            cli, synthetic_project, "vault", "add", "exec", "--feature", "live-exec"
        )
        assert result.exit_code == 1
        assert "vault exec log" in result.output

    def test_add_invalid_type_fails(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        result = _run(
            cli, synthetic_project, "vault", "add", "invalid", "--feature", "x"
        )
        assert result.exit_code != 0

    def test_add_requires_feature(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        result = _run(cli, synthetic_project, "vault", "add", "adr")
        assert result.exit_code != 0

    def test_add_strips_hash_from_feature(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        result = _run(
            cli,
            synthetic_project,
            "vault",
            "add",
            "adr",
            "--feature",
            "#hash-feat",
        )
        assert result.exit_code == 0
        date_str = vault_today().isoformat()
        expected = synthetic_project / ".vault" / "adr" / f"{date_str}-hash-feat-adr.md"
        assert expected.exists()

    def test_add_rejects_invalid_feature(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        result = _run(
            cli,
            synthetic_project,
            "vault",
            "add",
            "adr",
            "--feature",
            "Invalid_Feature!",
        )
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# vault check --fix rejection (parametrized)
# ═══════════════════════════════════════════════════════════════════


class TestVaultCheckFixRejection:
    @pytest.mark.parametrize("check", ["orphans", "features"])
    def test_fix_rejected(
        self, cli: CliRunner, synthetic_project: Path, check: str
    ) -> None:
        result = _run(cli, synthetic_project, "vault", "check", check, "--fix")
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# vault feature archive
# ═══════════════════════════════════════════════════════════════════


class TestVaultFeature:
    def test_feature_archive_dry_run_and_execution(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        # Create a document for archive-me
        _run(cli, synthetic_project, "vault", "add", "adr", "--feature", "archive-me")

        # Run archive in dry-run mode
        result = _run(
            cli,
            synthetic_project,
            "vault",
            "feature",
            "archive",
            "archive-me",
            "--dry-run",
        )
        assert result.exit_code == 0
        assert "Dry-run: Previewing feature archive for 'archive-me'" in result.output
        assert "Planned movements:" in result.output

        # Verify no files were actually moved to archive yet
        archive_dir = synthetic_project / ".vault" / "_archive"
        assert not archive_dir.exists() or len(list(archive_dir.rglob("*.md"))) == 0

        # Now archive for real
        result = _run(
            cli, synthetic_project, "vault", "feature", "archive", "archive-me"
        )
        assert result.exit_code == 0
        assert "Archived 1 documents." in result.output

        # Verify it is in _archive
        assert archive_dir.is_dir()
        archived_files = list(archive_dir.rglob("*.md"))
        assert len(archived_files) == 1

        # Run unarchive in dry-run mode
        result = _run(
            cli,
            synthetic_project,
            "vault",
            "feature",
            "unarchive",
            "archive-me",
            "--dry-run",
        )
        assert result.exit_code == 0
        assert "Dry-run: Previewing feature unarchive for 'archive-me'" in result.output
        assert "Planned restorations:" in result.output

        # Verify it is still in _archive
        assert len(list(archive_dir.rglob("*.md"))) == 1

        # Unarchive for real
        result = _run(
            cli, synthetic_project, "vault", "feature", "unarchive", "archive-me"
        )
        assert result.exit_code == 0
        assert "Unarchived 1 documents." in result.output

        # Verify archive dir is empty or deleted
        assert not archive_dir.exists() or len(list(archive_dir.rglob("*.md"))) == 0

    def test_feature_archive_nonexistent(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        result = _run(
            cli, synthetic_project, "vault", "feature", "archive", "nonexistent-tag"
        )
        assert result.exit_code == 1
        assert "matches zero documents" in result.output

    def test_feature_unarchive_nonexistent(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        result = _run(
            cli, synthetic_project, "vault", "feature", "unarchive", "nonexistent-tag"
        )
        assert result.exit_code == 1
        assert "matches zero archived documents" in result.output

    def test_feature_archive_and_unarchive_json(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        # Create a document
        _run(cli, synthetic_project, "vault", "add", "adr", "--feature", "json-me")

        # Dry-run archive with JSON output
        result = _run(
            cli,
            synthetic_project,
            "vault",
            "feature",
            "archive",
            "json-me",
            "--dry-run",
            "--json",
        )
        assert result.exit_code == 0
        import json

        data = json.loads(result.output)
        assert data["status"] == "unchanged"
        assert data["data"]["dry_run"] is True
        assert data["data"]["archived_count"] == 1

        # Run archive with JSON output
        result = _run(
            cli, synthetic_project, "vault", "feature", "archive", "json-me", "--json"
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "removed"
        assert data["data"]["dry_run"] is False
        assert data["data"]["archived_count"] == 1

        # Dry-run unarchive with JSON output
        result = _run(
            cli,
            synthetic_project,
            "vault",
            "feature",
            "unarchive",
            "json-me",
            "--dry-run",
            "--json",
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "unchanged"
        assert data["data"]["dry_run"] is True
        assert data["data"]["unarchived_count"] == 1

        # Run unarchive with JSON output
        result = _run(
            cli, synthetic_project, "vault", "feature", "unarchive", "json-me", "--json"
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "restored"
        assert data["data"]["dry_run"] is False
        assert data["data"]["unarchived_count"] == 1

    def test_feature_archive_cross_links_warning(
        self, cli: CliRunner, synthetic_project: Path
    ) -> None:
        # Create doc-a in feature-a
        res_a = _run(
            cli, synthetic_project, "vault", "add", "adr", "--feature", "feature-a"
        )
        assert res_a.exit_code == 0

        # Create doc-b in feature-b
        res_b = _run(
            cli, synthetic_project, "vault", "add", "adr", "--feature", "feature-b"
        )
        assert res_b.exit_code == 0

        # Identify the two documents by the feature segment their filenames
        # already carry, not by mtime order. Both were scaffolded back to back,
        # so an `st_mtime` sort is only as reliable as the filesystem's
        # timestamp granularity - two seconds on FAT, one second on many
        # network filesystems - and a same-tick pair sorts arbitrarily, which
        # would silently swap the two documents and assert the wrong linkage.
        adr_dir = synthetic_project / ".vault" / "adr"
        doc_a_path = next(adr_dir.glob("*-feature-a-adr.md"))
        doc_b_path = next(adr_dir.glob("*-feature-b-adr.md"))

        # Add cross-feature link from doc-b to doc-a
        new_content = f"""---
tags:
  - '#adr'
  - '#feature-b'
date: 2026-05-22
related:
  - '[[{doc_a_path.name}]]'
---
# Test Document B
"""
        doc_b_path.write_text(new_content, encoding="utf-8")

        # Now run dry-run archive on feature-a
        result = _run(
            cli,
            synthetic_project,
            "vault",
            "feature",
            "archive",
            "feature-a",
            "--dry-run",
        )
        assert result.exit_code == 0
        assert (
            "Warning: The following external documents link to feature documents"
            in result.output
        )
        assert doc_b_path.name in result.output


# ═══════════════════════════════════════════════════════════════════
# target propagation (pipeline + isolation)
# ═══════════════════════════════════════════════════════════════════


class TestTargetPropagation:
    """Prove --target on subcommands correctly directs all operations."""

    def test_install_then_sync_pipeline(self, cli: CliRunner, tmp_path: Path) -> None:
        """Full pipeline: install --target + sync --target on the SAME dir."""
        target = tmp_path / "pipeline"
        target.mkdir()
        r = cli.invoke(app, ["install", "--target", str(target)])
        assert r.exit_code == 0
        assert (target / ".vaultspec").is_dir()

        r = cli.invoke(app, ["sync", "--target", str(target)])
        assert r.exit_code == 0
        assert (target / ".claude" / "rules").is_dir()
        assert any((target / ".claude" / "rules").iterdir())

    def test_sync_regenerates_at_target(self, synthetic_project: Path) -> None:
        """Remove a synced file, re-sync, verify it reappears at target."""
        synced = synthetic_project / ".claude" / "rules" / "vaultspec.builtin.md"
        if synced.exists():
            synced.unlink()
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "vaultspec_core",
                "sync",
                "--target",
                str(synthetic_project),
            ],
            cwd=synthetic_project,
            env={**os.environ, "NO_COLOR": "1"},
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        assert result.returncode == 0, result.stdout + result.stderr
        assert synced.exists(), "sync did not write to --target"

    def test_sync_does_not_leak_to_cwd(
        self, cli: CliRunner, synthetic_project: Path, tmp_path: Path
    ) -> None:
        """sync --target must not create artifacts outside the target."""
        r = cli.invoke(app, ["sync", "--target", str(synthetic_project)])
        assert r.exit_code == 0
        assert not (tmp_path / ".vaultspec").exists()
        assert not (tmp_path / ".claude").exists()

    def test_target_without_vaultspec_fails(
        self, cli: CliRunner, tmp_path: Path
    ) -> None:
        empty = tmp_path / "empty"
        empty.mkdir()
        r = cli.invoke(app, ["sync", "--target", str(empty)])
        assert r.exit_code == 1

    @pytest.mark.parametrize(
        "cmd_args",
        [
            ["vault", "stats"],
            ["vault", "list"],
            ["spec", "rules", "list"],
            ["spec", "skills", "list"],
            ["spec", "system", "show"],
        ],
    )
    def test_subcommand_target_reads_correct_project(
        self, cli: CliRunner, synthetic_project: Path, cmd_args: list[str]
    ) -> None:
        """Various commands with subcommand-level --target read from the project."""
        result = cli.invoke(app, [*cmd_args, "--target", str(synthetic_project)])
        assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"


# ═══════════════════════════════════════════════════════════════════
# global options
# ═══════════════════════════════════════════════════════════════════


class TestGlobalOptions:
    @pytest.mark.parametrize("flag", ["--version", "-V"])
    def test_version(self, cli: CliRunner, flag: str) -> None:
        result = cli.invoke(app, [flag])
        assert result.exit_code == 0

    def test_no_args_prints_help(self, cli: CliRunner, synthetic_project: Path) -> None:
        result = cli.invoke(app, ["--target", str(synthetic_project)])
        assert result.exit_code == 0
        assert "vaultspec-core" in result.output

    def test_unknown_command_fails(self, cli: CliRunner) -> None:
        result = cli.invoke(app, ["nonexistent"])
        assert result.exit_code != 0
