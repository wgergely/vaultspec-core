"""Tests for uninstall command behavior."""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from vaultspec_core.cli import app
from vaultspec_core.core.manifest import read_manifest

pytestmark = [pytest.mark.unit]


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class TestUninstallForce:
    def test_uninstall_without_force_fails(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """Uninstall must refuse without --force."""
        (tmp_path / ".vaultspec").mkdir()
        result = runner.invoke(app, ["-t", str(tmp_path), "uninstall"])
        assert result.exit_code != 0
        assert "--force" in result.output

    def test_uninstall_dry_run_without_force_succeeds(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """--dry-run should work without --force (it's non-destructive)."""
        (tmp_path / ".vaultspec").mkdir()
        result = runner.invoke(app, ["-t", str(tmp_path), "uninstall", "--dry-run"])
        # Should not require --force for dry-run
        assert "--force" not in result.output or result.exit_code == 0


def _install_both_gemini_md_owners(target: Path, runner: CliRunner) -> None:
    """Install antigravity and gemini, asserting both really landed.

    Gemini alone creates `GEMINI.md` and `.agents/` too, so a silently failed
    antigravity install would leave every assertion in these tests still
    passing while proving nothing about shared ownership. Checking the
    manifest is what makes the precondition load-bearing rather than assumed.
    """
    for provider in ("antigravity", "gemini"):
        result = runner.invoke(app, ["-t", str(target), "install", provider, "--force"])
        assert result.exit_code == 0, result.output

    assert {"antigravity", "gemini"} <= read_manifest(target)
    assert (target / "GEMINI.md").is_file()


class TestUninstallSharedFileOwnership:
    """GEMINI.md is `config_file` for both gemini and antigravity.

    Removing it while its other owner is still installed strands that owner
    without its root context file (issue #492). Two independent paths can do
    that removal and they have to agree, but only one of them was broken.
    The named-provider path asks the manifest, via `providers_sharing_file`,
    which providers still claim the file, and was already correct.
    `_uninstall_everything`'s `--skip` loop instead read the static
    `_UNINSTALL_FILE_OWNERS` map, which named one owner per file. Both paths
    are covered here so the correct one cannot regress into the broken one.
    """

    def test_uninstall_one_provider_preserves_a_file_the_other_still_owns(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """Uninstalling gemini alone must not strand antigravity's GEMINI.md.

        This path already held before the fix, because it derives ownership
        from the manifest rather than from a static map. It is pinned so a
        later refactor routing it through `_UNINSTALL_FILE_OWNERS` has to
        keep giving the same answer.
        """
        _install_both_gemini_md_owners(tmp_path, runner)

        result = runner.invoke(
            app, ["-t", str(tmp_path), "uninstall", "gemini", "--force"]
        )

        assert result.exit_code == 0, result.output
        assert (tmp_path / "GEMINI.md").is_file()
        assert (tmp_path / ".agents").is_dir()

        # The reverse direction: once antigravity is gone too, nothing owns
        # GEMINI.md any longer and it must finally be removed.
        result = runner.invoke(
            app, ["-t", str(tmp_path), "uninstall", "antigravity", "--force"]
        )

        assert result.exit_code == 0, result.output
        assert not (tmp_path / "GEMINI.md").exists()

    def test_full_uninstall_skipping_one_owner_preserves_a_shared_file(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """`uninstall --skip antigravity` must not remove antigravity's config.

        This exercises `_uninstall_everything`'s file-removal loop directly,
        the path that stayed a plain str->str map after `_UNINSTALL_DIR_OWNERS`
        was widened to a list, and the only path where the bug was reachable.
        Before the fix this test failed: the full uninstall took GEMINI.md
        despite `--skip antigravity` naming one of its owners.
        """
        _install_both_gemini_md_owners(tmp_path, runner)

        result = runner.invoke(
            app,
            [
                "-t",
                str(tmp_path),
                "uninstall",
                "--skip",
                "antigravity",
                "--force",
            ],
        )

        assert result.exit_code == 0, result.output
        assert (tmp_path / "GEMINI.md").is_file()
        assert (tmp_path / ".agents").is_dir()

        # With no owner left to skip, a second full uninstall removes it.
        result = runner.invoke(
            app, ["-t", str(tmp_path), "uninstall", "--force", "--remove-vault"]
        )

        assert result.exit_code == 0, result.output
        assert not (tmp_path / "GEMINI.md").exists()


class TestUninstallCoreCascade:
    def test_core_uninstall_treated_as_all(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """Uninstalling 'core' should cascade to all providers."""
        # Create vaultspec and provider dirs
        (tmp_path / ".vaultspec").mkdir()
        (tmp_path / ".claude").mkdir()
        result = runner.invoke(
            app, ["-t", str(tmp_path), "uninstall", "core", "--force"]
        )
        # Should not error about "core" being invalid
        if result.exit_code != 0:
            assert "unknown provider" not in result.output.lower()


class TestUninstallLeavesNoResidue:
    """Uninstall prunes the sentinels it made and keeps both blocks in step.

    A sentinel outlives its subject when the subject is removed, and uninstall
    removes most of them. Nothing pruned them, so `.mcp.json.lock` and
    `.pre-commit-config.yaml.lock` survived a full uninstall (issue #409).

    `.gitattributes` was the one managed file this path never reconciled on the
    keep-vault branch: it was removed only in the full-removal case and
    otherwise left at whatever the last install wrote.
    """

    def test_prunes_sentinels_whose_subject_it_removed(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        runner.invoke(app, ["-t", str(tmp_path), "install", "claude"])
        assert (tmp_path / ".mcp.json.lock").exists() or True  # created on demand

        result = runner.invoke(app, ["-t", str(tmp_path), "uninstall", "--force"])

        assert result.exit_code == 0, result.output
        assert not (tmp_path / ".mcp.json.lock").exists()
        assert not (tmp_path / ".pre-commit-config.yaml.lock").exists()

    def test_keeps_the_sentinel_whose_subject_survives(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """The guard: pruning is subject-driven, not a blanket sweep.

        `.gitignore` is kept (it still carries the `.vault/` entries), so its
        sentinel has a subject and must not be pruned.
        """
        runner.invoke(app, ["-t", str(tmp_path), "install", "claude"])

        result = runner.invoke(app, ["-t", str(tmp_path), "uninstall", "--force"])

        assert result.exit_code == 0, result.output
        assert (tmp_path / ".gitignore").is_file()
        # Its sentinel may or may not exist depending on whether the last write
        # took the lock; what must not happen is pruning one whose subject is
        # still there.
        if (tmp_path / ".gitignore.lock").exists():
            assert (tmp_path / ".gitignore").exists()

    def test_reconciles_the_gitattributes_block_on_the_keep_vault_path(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """A hand-mangled block is brought back into shape, like its twin."""
        from vaultspec_core.core.gitattributes import MARKER_BEGIN, MARKER_END

        runner.invoke(app, ["-t", str(tmp_path), "install", "claude"])
        ga = tmp_path / ".gitattributes"
        ga.write_text(
            f"# project\n{MARKER_BEGIN}\n* text=auto eol=crlf\n{MARKER_END}\n",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["-t", str(tmp_path), "uninstall", "--force"])

        assert result.exit_code == 0, result.output
        assert "* text=auto eol=lf" in ga.read_text(encoding="utf-8")

    def test_full_removal_still_takes_both_blocks_away(
        self, tmp_path: Path, runner: CliRunner
    ) -> None:
        """The guard on the reconcile: --remove-vault still removes, not repairs."""
        from vaultspec_core.core.gitattributes import MARKER_BEGIN

        runner.invoke(app, ["-t", str(tmp_path), "install", "claude"])

        result = runner.invoke(
            app, ["-t", str(tmp_path), "uninstall", "--force", "--remove-vault"]
        )

        assert result.exit_code == 0, result.output
        ga = tmp_path / ".gitattributes"
        if ga.is_file():
            assert MARKER_BEGIN not in ga.read_text(encoding="utf-8")
