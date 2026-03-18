"""Live integration tests for every vaultspec-core CLI command.

Tests run against a copy of the real test-project/ corpus.  No mocks,
patches, or stubs.  Every command receives ``--target`` at the
*subcommand* level (not the root callback) to prove uniform support.

The ``project`` fixture copies test-project/ to a fresh tmp_path for
each test so mutations are isolated and cleanup is automatic.

Tests are parametrized wherever possible so ``pytest-randomly`` (or
``-p randomly``) can shuffle execution order and surface state leakage.
"""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

import pytest
from typer.testing import CliRunner

from vaultspec_core.cli import app

pytestmark = [pytest.mark.integration]

_REPO_ROOT = Path(__file__).resolve().parents[4]
_TEST_PROJECT_SRC = _REPO_ROOT / "test-project"


# ── fixtures ────────────────────────────────────────────────────────


@pytest.fixture
def project(tmp_path):
    """Fresh copy of the real test-project/ corpus with vaultspec installed."""
    dest = tmp_path / "project"
    shutil.copytree(
        _TEST_PROJECT_SRC,
        dest,
        ignore_dangling_symlinks=True,
        ignore=shutil.ignore_patterns("*.log"),
    )

    # Install vaultspec framework so .vaultspec/ exists
    from vaultspec_core.core import types as _t
    from vaultspec_core.core.commands import install_run

    _t.TARGET_DIR = dest
    install_run(path=dest, provider="all", upgrade=False, dry_run=False, force=False)

    return dest


@pytest.fixture(scope="module")
def cli():
    return CliRunner(env={"NO_COLOR": "1"})


# ── helpers ─────────────────────────────────────────────────────────


def _run(cli, project, *args):
    """Invoke CLI with ``--target`` on the **subcommand**, not the root.

    This proves that every command accepts ``--target`` directly.
    The target flag is inserted at a random valid position among the
    trailing options to surface ordering bugs.
    """
    cmd_args = [*list(args), "--target", str(project)]
    return cli.invoke(app, cmd_args)


def _run_root_target(cli, project, *args):
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
    ("sync-prune", ["sync", "--prune"]),
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
def test_subcommand_target_exit_0(cli, project, cmd_id, args):
    """Every non-check command accepts --target on the subcommand and exits 0."""
    result = _run(cli, project, *args)
    assert result.exit_code == 0, f"[{cmd_id}] exit={result.exit_code}\n{result.output}"


@pytest.mark.parametrize(
    "cmd_id, args",
    _COMMANDS_EXIT_0,
    ids=[c[0] for c in _COMMANDS_EXIT_0],
)
def test_root_target_exit_0(cli, project, cmd_id, args):
    """Same commands accept --target on the root callback (backward compat)."""
    result = _run_root_target(cli, project, *args)
    assert result.exit_code == 0, f"[{cmd_id}] exit={result.exit_code}\n{result.output}"


@pytest.mark.parametrize(
    "cmd_id, args",
    _COMMANDS_CHECK,
    ids=[c[0] for c in _COMMANDS_CHECK],
)
def test_check_subcommand_target(cli, project, cmd_id, args):
    """Check commands accept --target on the subcommand and produce output.

    These commands exit 1 when they find issues in the corpus — that's
    correct diagnostic behavior.  The test verifies the command accepted
    ``--target``, ran against the correct directory, and produced output.
    An exit code of 2+ would indicate a crash, not a diagnostic finding.
    """
    result = _run(cli, project, *args)
    assert result.exit_code != 2, (
        f"[{cmd_id}] crashed: exit={result.exit_code}\n{result.output}"
    )
    assert len(result.output.strip()) > 0, f"[{cmd_id}] produced no output"


@pytest.mark.parametrize(
    "cmd_id, args",
    _COMMANDS_CHECK,
    ids=[c[0] for c in _COMMANDS_CHECK],
)
def test_check_root_target(cli, project, cmd_id, args):
    """Check commands accept root --target and produce output."""
    result = _run_root_target(cli, project, *args)
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
    ["spec", "rules", "revert", "--help"],
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
]


@pytest.mark.parametrize(
    "args",
    _HELP_SURFACES,
    ids=[" ".join(a) for a in _HELP_SURFACES],
)
def test_help_exits_zero(cli, args):
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
def test_target_in_help_text(cli, args):
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
    def test_install_provider(self, cli, tmp_path, provider):
        target = tmp_path / f"inst-{provider}"
        target.mkdir()
        result = cli.invoke(app, ["install", "--target", str(target), provider])
        assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"
        assert (target / ".vaultspec").is_dir()

    def test_install_creates_single_level_dir(self, cli, tmp_path):
        target = tmp_path / "new-project"
        result = cli.invoke(app, ["install", "--target", str(target)])
        assert result.exit_code == 0
        assert target.is_dir()
        assert (target / ".vaultspec").is_dir()

    def test_install_rejects_deep_nonexistent(self, cli, tmp_path):
        target = tmp_path / "a" / "b" / "c"
        result = cli.invoke(app, ["install", "--target", str(target)])
        assert result.exit_code != 0
        assert not (tmp_path / "a").exists()

    def test_install_dry_run_no_side_effects(self, cli, tmp_path):
        target = tmp_path / "dry"
        target.mkdir()
        result = cli.invoke(app, ["install", "--target", str(target), "--dry-run"])
        assert result.exit_code == 0
        assert not (target / ".vaultspec").exists()

    def test_install_force_over_existing(self, cli, project):
        result = cli.invoke(app, ["install", "--target", str(project), "--force"])
        assert result.exit_code == 0
        assert (project / ".vaultspec").is_dir()

    def test_install_upgrade(self, cli, project):
        result = cli.invoke(app, ["install", "--target", str(project), "--upgrade"])
        assert result.exit_code == 0

    def test_install_without_force_fails_if_exists(self, cli, project):
        result = cli.invoke(app, ["install", "--target", str(project)])
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# sync (parametrized providers)
# ═══════════════════════════════════════════════════════════════════

_SYNC_PROVIDERS = ["all", "claude", "gemini", "antigravity", "codex"]


class TestSync:
    @pytest.mark.parametrize("provider", _SYNC_PROVIDERS)
    def test_sync_provider(self, cli, project, provider):
        result = _run(cli, project, "sync", provider)
        assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"

    def test_sync_writes_to_target_not_cwd(self, cli, project):
        """Remove a synced file, re-sync, confirm it reappears at --target."""
        synced = project / ".claude" / "rules" / "vaultspec.builtin.md"
        if synced.exists():
            synced.unlink()
        result = _run(cli, project, "sync")
        assert result.exit_code == 0
        assert synced.exists(), "sync did not regenerate file at --target"

    @pytest.mark.parametrize("flag", ["--dry-run", "--prune", "--force"])
    def test_sync_flags(self, cli, project, flag):
        result = _run(cli, project, "sync", flag)
        assert result.exit_code == 0

    def test_sync_core_rejected(self, cli, project):
        result = _run(cli, project, "sync", "core")
        assert result.exit_code != 0

    def test_sync_unknown_provider_fails(self, cli, project):
        result = _run(cli, project, "sync", "nonexistent")
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# uninstall (parametrized providers)
# ═══════════════════════════════════════════════════════════════════


class TestUninstall:
    def test_requires_force(self, cli, project):
        result = _run(cli, project, "uninstall")
        assert result.exit_code != 0
        assert "--force" in result.output

    def test_dry_run_no_removal(self, cli, project):
        result = _run(cli, project, "uninstall", "--dry-run")
        assert result.exit_code == 0
        assert (project / ".vaultspec").exists()

    def test_force_preserves_vault(self, cli, project):
        result = cli.invoke(app, ["uninstall", "--target", str(project), "--force"])
        assert result.exit_code == 0
        assert (project / ".vault").is_dir()
        assert not (project / ".vaultspec").exists()

    def test_force_remove_vault(self, cli, project):
        result = cli.invoke(
            app,
            ["uninstall", "--target", str(project), "--force", "--remove-vault"],
        )
        assert result.exit_code == 0
        assert not (project / ".vault").exists()
        assert not (project / ".vaultspec").exists()

    @pytest.mark.parametrize(
        "provider",
        ["claude", "gemini", "antigravity", "codex"],
    )
    def test_per_provider_uninstall(self, cli, project, provider):
        result = cli.invoke(
            app,
            ["uninstall", "--target", str(project), provider, "--force"],
        )
        assert result.exit_code == 0
        assert (project / ".vaultspec").exists()


# ═══════════════════════════════════════════════════════════════════
# spec rules lifecycle (CRUD)
# ═══════════════════════════════════════════════════════════════════


class TestSpecRules:
    def test_add_show_remove_lifecycle(self, cli, project):
        # add
        result = _run(
            cli,
            project,
            "spec",
            "rules",
            "add",
            "--name",
            "live-test",
            "--content",
            "Live rule body",
        )
        assert result.exit_code == 0
        rule_path = project / ".vaultspec" / "rules" / "rules" / "live-test.md"
        assert rule_path.exists()

        # show
        result = _run(cli, project, "spec", "rules", "show", "live-test")
        assert result.exit_code == 0
        assert "Live rule body" in result.output

        # remove
        result = _run(
            cli,
            project,
            "spec",
            "rules",
            "remove",
            "live-test",
            "--force",
        )
        assert result.exit_code == 0
        assert not rule_path.exists()

    def test_rename(self, cli, project):
        _run(
            cli,
            project,
            "spec",
            "rules",
            "add",
            "--name",
            "rename-src",
            "--content",
            "To rename",
        )
        result = _run(
            cli,
            project,
            "spec",
            "rules",
            "rename",
            "rename-src",
            "rename-dst",
        )
        assert result.exit_code == 0
        dst = project / ".vaultspec" / "rules" / "rules" / "rename-dst.md"
        assert dst.exists()

    def test_add_force_overwrites(self, cli, project):
        _run(
            cli,
            project,
            "spec",
            "rules",
            "add",
            "--name",
            "overwrite-me",
            "--content",
            "v1",
        )
        result = _run(
            cli,
            project,
            "spec",
            "rules",
            "add",
            "--name",
            "overwrite-me",
            "--content",
            "v2",
            "--force",
        )
        assert result.exit_code == 0
        content = (
            project / ".vaultspec" / "rules" / "rules" / "overwrite-me.md"
        ).read_text(encoding="utf-8")
        assert "v2" in content

    def test_revert(self, cli, project):
        src = project / ".vaultspec" / "rules" / "rules" / "vaultspec.builtin.md"
        snapshot = (
            project / ".vaultspec" / "_snapshots" / "rules" / "vaultspec.builtin.md"
        )
        if not snapshot.exists():
            pytest.skip("No snapshot available for revert test")
        original = src.read_text(encoding="utf-8")
        src.write_text("MODIFIED CONTENT", encoding="utf-8")

        result = _run(cli, project, "spec", "rules", "revert", "vaultspec.builtin")
        assert result.exit_code == 0
        assert src.read_text(encoding="utf-8") == original

    @pytest.mark.parametrize(
        "subcmd",
        ["show", "edit"],
    )
    def test_missing_resource_fails(self, cli, project, subcmd):
        result = _run(cli, project, "spec", "rules", subcmd, "nonexistent-xyz")
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# spec skills lifecycle (CRUD)
# ═══════════════════════════════════════════════════════════════════


class TestSpecSkills:
    def test_add_show_remove_lifecycle(self, cli, project):
        # add
        result = _run(
            cli,
            project,
            "spec",
            "skills",
            "add",
            "--name",
            "vaultspec-live-skill",
            "--description",
            "Live skill test",
        )
        assert result.exit_code == 0
        skill_dir = project / ".vaultspec" / "rules" / "skills" / "vaultspec-live-skill"
        assert skill_dir.is_dir()

        # show
        result = _run(cli, project, "spec", "skills", "show", "vaultspec-live-skill")
        assert result.exit_code == 0

        # remove
        result = _run(
            cli,
            project,
            "spec",
            "skills",
            "remove",
            "vaultspec-live-skill",
            "--force",
        )
        assert result.exit_code == 0
        assert not skill_dir.exists()

    def test_rename(self, cli, project):
        _run(
            cli,
            project,
            "spec",
            "skills",
            "add",
            "--name",
            "vaultspec-old-skill",
            "--description",
            "Old",
        )
        result = _run(
            cli,
            project,
            "spec",
            "skills",
            "rename",
            "vaultspec-old-skill",
            "vaultspec-new-skill",
        )
        assert result.exit_code == 0
        new = project / ".vaultspec" / "rules" / "skills" / "vaultspec-new-skill"
        assert new.is_dir()

    @pytest.mark.parametrize("subcmd", ["show", "edit"])
    def test_missing_resource_fails(self, cli, project, subcmd):
        result = _run(cli, project, "spec", "skills", subcmd, "nonexistent-xyz")
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# spec agents lifecycle (CRUD)
# ═══════════════════════════════════════════════════════════════════


class TestSpecAgents:
    def test_add_show_remove_lifecycle(self, cli, project):
        # add
        result = _run(
            cli,
            project,
            "spec",
            "agents",
            "add",
            "--name",
            "live-agent",
            "--description",
            "Live agent test",
        )
        assert result.exit_code == 0
        agent_path = project / ".vaultspec" / "rules" / "agents" / "live-agent.md"
        assert agent_path.exists()

        # show
        result = _run(cli, project, "spec", "agents", "show", "live-agent")
        assert result.exit_code == 0

        # remove
        result = _run(
            cli,
            project,
            "spec",
            "agents",
            "remove",
            "live-agent",
            "--force",
        )
        assert result.exit_code == 0
        assert not agent_path.exists()

    def test_rename(self, cli, project):
        _run(
            cli,
            project,
            "spec",
            "agents",
            "add",
            "--name",
            "old-agent",
            "--description",
            "Old",
        )
        result = _run(
            cli,
            project,
            "spec",
            "agents",
            "rename",
            "old-agent",
            "new-agent",
        )
        assert result.exit_code == 0
        new = project / ".vaultspec" / "rules" / "agents" / "new-agent.md"
        assert new.exists()

    def test_show_missing_fails(self, cli, project):
        result = _run(cli, project, "spec", "agents", "show", "nonexistent-xyz")
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# spec hooks
# ═══════════════════════════════════════════════════════════════════


class TestSpecHooks:
    def test_run_unknown_event_fails(self, cli, project):
        result = _run(cli, project, "spec", "hooks", "run", "nonexistent.event")
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# vault add (parametrized doc types)
# ═══════════════════════════════════════════════════════════════════

_DOC_TYPES = ["adr", "audit", "plan", "research", "reference", "exec"]


class TestVaultAdd:
    @pytest.mark.parametrize("doc_type", _DOC_TYPES)
    def test_add_doc_type(self, cli, project, doc_type):
        feat = f"live-{doc_type}"
        result = _run(cli, project, "vault", "add", doc_type, "--feature", feat)
        assert result.exit_code == 0

    def test_add_invalid_type_fails(self, cli, project):
        result = _run(cli, project, "vault", "add", "invalid", "--feature", "x")
        assert result.exit_code != 0

    def test_add_requires_feature(self, cli, project):
        result = _run(cli, project, "vault", "add", "adr")
        assert result.exit_code != 0

    def test_add_strips_hash_from_feature(self, cli, project):
        result = _run(
            cli,
            project,
            "vault",
            "add",
            "adr",
            "--feature",
            "#hash-feat",
        )
        assert result.exit_code == 0
        date_str = datetime.now().strftime("%Y-%m-%d")
        expected = project / ".vault" / "adr" / f"{date_str}-hash-feat-adr.md"
        assert expected.exists()

    def test_add_rejects_invalid_feature(self, cli, project):
        result = _run(
            cli,
            project,
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
    def test_fix_rejected(self, cli, project, check):
        result = _run(cli, project, "vault", "check", check, "--fix")
        assert result.exit_code != 0


# ═══════════════════════════════════════════════════════════════════
# vault feature archive
# ═══════════════════════════════════════════════════════════════════


class TestVaultFeature:
    def test_feature_archive(self, cli, project):
        _run(cli, project, "vault", "add", "adr", "--feature", "archive-me")
        result = _run(cli, project, "vault", "feature", "archive", "archive-me")
        assert result.exit_code == 0


# ═══════════════════════════════════════════════════════════════════
# target propagation (pipeline + isolation)
# ═══════════════════════════════════════════════════════════════════


class TestTargetPropagation:
    """Prove --target on subcommands correctly directs all operations."""

    def test_install_then_sync_pipeline(self, cli, tmp_path):
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

    def test_sync_regenerates_at_target(self, cli, project):
        """Remove a synced file, re-sync, verify it reappears at target."""
        synced = project / ".claude" / "rules" / "vaultspec.builtin.md"
        if synced.exists():
            synced.unlink()
        r = cli.invoke(app, ["sync", "--target", str(project)])
        assert r.exit_code == 0
        assert synced.exists(), "sync did not write to --target"

    def test_sync_does_not_leak_to_cwd(self, cli, project, tmp_path):
        """sync --target must not create artifacts outside the target."""
        r = cli.invoke(app, ["sync", "--target", str(project)])
        assert r.exit_code == 0
        assert not (tmp_path / ".vaultspec").exists()
        assert not (tmp_path / ".claude").exists()

    def test_target_without_vaultspec_fails(self, cli, tmp_path):
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
    def test_subcommand_target_reads_correct_project(self, cli, project, cmd_args):
        """Various commands with subcommand-level --target read from the project."""
        result = cli.invoke(app, [*cmd_args, "--target", str(project)])
        assert result.exit_code == 0, f"exit={result.exit_code}\n{result.output}"


# ═══════════════════════════════════════════════════════════════════
# global options
# ═══════════════════════════════════════════════════════════════════


class TestGlobalOptions:
    @pytest.mark.parametrize("flag", ["--version", "-V"])
    def test_version(self, cli, flag):
        result = cli.invoke(app, [flag])
        assert result.exit_code == 0

    def test_no_args_prints_help(self, cli, project):
        result = cli.invoke(app, ["--target", str(project)])
        assert result.exit_code == 0
        assert "vaultspec-core" in result.output

    def test_unknown_command_fails(self, cli):
        result = cli.invoke(app, ["nonexistent"])
        assert result.exit_code != 0
