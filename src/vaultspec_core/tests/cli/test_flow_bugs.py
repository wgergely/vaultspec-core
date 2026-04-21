"""Regression tests for GH issue 80 install-layer hygiene defects.

Covers the five problem domains ratified in
``2026-04-21-flow-bugs-adr``:

* D1 - ``_untrack_managed_paths`` drops historically-tracked
  ``.vaultspec/providers.json`` from the git index on install.
* D2 - lock sentinels are absent from ``git status --porcelain`` after
  install because the managed block now ignores them.
* D3 - ``_scaffold_precommit`` skips when ``prek.toml`` is present.
* D4 - ``check_staged_provider_artifacts`` ignores staged deletions.
* D5 - ``_fix_filename`` rewrites incoming ``related:`` wiki-link
  references so renames do not leave dangling links.

All tests drive the real filesystem and a real ``git`` subprocess where
relevant; no mocks, patches, or stubs.
"""

from __future__ import annotations

import subprocess
from typing import TYPE_CHECKING

import pytest

from vaultspec_core.core.commands import (
    _scaffold_precommit,
    _untrack_managed_paths,
    check_staged_provider_artifacts,
    install_run,
)

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.integration]


def _null_device() -> str:
    """Return a platform-correct null device path for git config isolation."""
    import sys

    return "NUL" if sys.platform == "win32" else "/dev/null"


def _run_git(cwd: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """Invoke ``git`` inside *cwd* with deterministic author/committer env.

    Uses the platform-correct null device for ``GIT_CONFIG_GLOBAL`` /
    ``GIT_CONFIG_SYSTEM`` so host filter/core settings (``filter.lfs.*``,
    ``core.autocrlf``) cannot leak into the test repo.
    """
    null = _null_device()
    env = {
        "GIT_AUTHOR_NAME": "vaultspec-test",
        "GIT_AUTHOR_EMAIL": "test@vaultspec.local",
        "GIT_COMMITTER_NAME": "vaultspec-test",
        "GIT_COMMITTER_EMAIL": "test@vaultspec.local",
        "GIT_CONFIG_GLOBAL": null,
        "GIT_CONFIG_SYSTEM": null,
        "HOME": str(cwd),
    }
    import os

    full_env = {**os.environ, **env}
    result = subprocess.run(
        ["git", "-C", str(cwd), *args],
        capture_output=True,
        text=True,
        env=full_env,
        check=False,
    )
    return result


def _init_git_repo(path: Path) -> None:
    """Initialise a git repo at *path* with an initial empty commit."""
    _run_git(path, "init", "-q", "-b", "main")
    _run_git(path, "commit", "--allow-empty", "-q", "-m", "init")


# ---- Domain 4: staged deletions ---------------------------------------------


class TestCheckProvidersIgnoresDeletions:
    """``check_staged_provider_artifacts`` must allow remediation commits."""

    def test_staged_deletion_is_not_flagged(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        # Track .mcp.json then stage its removal.
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        _run_git(tmp_path, "add", ".mcp.json")
        _run_git(tmp_path, "commit", "-q", "-m", "track mcp")
        _run_git(tmp_path, "rm", "--cached", ".mcp.json")

        # Sanity check: confirm the staged change is indeed a deletion.
        staged = _run_git(
            tmp_path, "diff", "--cached", "--name-only", "--diff-filter=D"
        )
        assert ".mcp.json" in staged.stdout.splitlines()

        violations = check_staged_provider_artifacts(cwd=tmp_path)

        assert violations == []

    def test_staged_addition_is_flagged(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        _run_git(tmp_path, "add", ".mcp.json")

        violations = check_staged_provider_artifacts(cwd=tmp_path)

        assert ".mcp.json" in violations


# ---- Domain 1: untrack historically-committed managed paths -----------------


class TestUntrackManagedPaths:
    """``_untrack_managed_paths`` drops tracked files from the index."""

    def test_untracks_providers_json_when_tracked(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        vaultspec_dir = tmp_path / ".vaultspec"
        vaultspec_dir.mkdir()
        manifest = vaultspec_dir / "providers.json"
        manifest.write_text('{"version": "2.0"}', encoding="utf-8")

        _run_git(tmp_path, "add", ".vaultspec/providers.json")
        _run_git(tmp_path, "commit", "-q", "-m", "track manifest")
        assert (
            _run_git(
                tmp_path, "ls-files", "--error-unmatch", ".vaultspec/providers.json"
            ).returncode
            == 0
        )

        untracked = _untrack_managed_paths(tmp_path, [".vaultspec/"])

        assert untracked == [".vaultspec/providers.json"]
        assert (
            _run_git(
                tmp_path, "ls-files", "--error-unmatch", ".vaultspec/providers.json"
            ).returncode
            != 0
        )
        assert manifest.exists(), "working tree copy must be preserved"

    def test_does_not_untrack_root_mcp_json(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        (tmp_path / ".mcp.json").write_text("{}", encoding="utf-8")
        _run_git(tmp_path, "add", ".mcp.json")
        _run_git(tmp_path, "commit", "-q", "-m", "track mcp")

        untracked = _untrack_managed_paths(tmp_path, [".mcp.json"])

        assert untracked == []
        assert (
            _run_git(tmp_path, "ls-files", "--error-unmatch", ".mcp.json").returncode
            == 0
        )

    def test_untracks_root_lock_sentinel(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        sentinel = tmp_path / ".mcp.json.lock"
        sentinel.write_bytes(b"")
        _run_git(tmp_path, "add", ".mcp.json.lock")
        _run_git(tmp_path, "commit", "-q", "-m", "accidentally committed sentinel")

        untracked = _untrack_managed_paths(tmp_path, ["/.mcp.json.lock"])

        assert untracked == [".mcp.json.lock"]
        assert (
            _run_git(
                tmp_path, "ls-files", "--error-unmatch", ".mcp.json.lock"
            ).returncode
            != 0
        )

    def test_no_git_repo_is_noop(self, tmp_path: Path) -> None:
        untracked = _untrack_managed_paths(tmp_path, [".vaultspec/"])
        assert untracked == []

    def test_does_not_untrack_uv_lock(self, tmp_path: Path) -> None:
        """Sibling lockfiles (uv.lock, Cargo.lock, etc.) must survive."""
        _init_git_repo(tmp_path)
        (tmp_path / "uv.lock").write_text("version = 1", encoding="utf-8")
        _run_git(tmp_path, "add", "uv.lock")
        _run_git(tmp_path, "commit", "-q", "-m", "track uv.lock")

        untracked = _untrack_managed_paths(tmp_path, ["uv.lock"])

        assert untracked == []
        assert (
            _run_git(tmp_path, "ls-files", "--error-unmatch", "uv.lock").returncode == 0
        )

    def test_does_not_untrack_arbitrary_lock_file(self, tmp_path: Path) -> None:
        """Only explicitly-managed lock sentinels are eligible for untracking."""
        _init_git_repo(tmp_path)
        (tmp_path / "custom.lock").write_text("", encoding="utf-8")
        _run_git(tmp_path, "add", "custom.lock")
        _run_git(tmp_path, "commit", "-q", "-m", "track custom.lock")

        untracked = _untrack_managed_paths(tmp_path, ["/custom.lock"])

        assert untracked == []
        assert (
            _run_git(tmp_path, "ls-files", "--error-unmatch", "custom.lock").returncode
            == 0
        )

    def test_untracks_committed_claude_dir_content(self, tmp_path: Path) -> None:
        """Files under a provider scope directory (.claude/, .gemini/, .agents/,
        .codex/) must be eligible for untracking when passed in via the
        managed gitignore entries (ADR D1 scope).
        """
        _init_git_repo(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir()
        stale = claude_dir / "settings.json"
        stale.write_text("{}", encoding="utf-8")
        _run_git(tmp_path, "add", ".claude/settings.json")
        _run_git(tmp_path, "commit", "-q", "-m", "legacy tracked claude settings")

        untracked = _untrack_managed_paths(tmp_path, [".claude/"])

        assert untracked == [".claude/settings.json"]
        assert (
            _run_git(
                tmp_path, "ls-files", "--error-unmatch", ".claude/settings.json"
            ).returncode
            != 0
        )
        assert stale.exists(), "working tree copy must be preserved"

    def test_does_not_untrack_subdir_sentinel_match(self, tmp_path: Path) -> None:
        """Sentinel basenames only match at the workspace root.

        A user-authored ``docs/.gitignore.lock`` must not be swept up even
        though its basename matches :data:`_MANAGED_LOCK_SENTINELS`.
        """
        _init_git_repo(tmp_path)
        docs = tmp_path / "docs"
        docs.mkdir()
        subdir_sentinel = docs / ".gitignore.lock"
        subdir_sentinel.write_text("custom content", encoding="utf-8")
        _run_git(tmp_path, "add", "docs/.gitignore.lock")
        _run_git(tmp_path, "commit", "-q", "-m", "track subdir sentinel")

        untracked = _untrack_managed_paths(tmp_path, ["docs/.gitignore.lock"])

        assert untracked == []
        assert (
            _run_git(
                tmp_path, "ls-files", "--error-unmatch", "docs/.gitignore.lock"
            ).returncode
            == 0
        )


# ---- Domain 3: prek.toml short-circuit --------------------------------------


class TestPrekShortCircuit:
    """``_scaffold_precommit`` must not write YAML when ``prek.toml`` exists."""

    def test_skips_when_prek_toml_present(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        (tmp_path / "prek.toml").write_text("", encoding="utf-8")

        caplog.set_level("INFO", logger="vaultspec_core.core.commands")
        result = _scaffold_precommit(tmp_path)

        assert result == []
        assert not (tmp_path / ".pre-commit-config.yaml").exists()
        assert any("prek.toml detected" in rec.message for rec in caplog.records)

    def test_scaffolds_when_prek_toml_absent(self, tmp_path: Path) -> None:
        result = _scaffold_precommit(tmp_path)

        assert result == [(".pre-commit-config.yaml", "precommit")]
        assert (tmp_path / ".pre-commit-config.yaml").exists()


# ---- Domain 2 + domain 1 end-to-end: install leaves a clean tree -------------


class TestInstallLeavesCleanTree:
    """Post-install ``git status --porcelain`` must be empty."""

    def test_fresh_install_no_untracked_lock_sentinels(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        (tmp_path / ".gitignore").write_text("", encoding="utf-8")
        _run_git(tmp_path, "add", ".gitignore")
        _run_git(tmp_path, "commit", "-q", "-m", "seed gitignore")

        install_run(
            path=tmp_path,
            provider="all",
            upgrade=False,
            dry_run=False,
            force=True,
        )

        # After install, the working tree contains freshly created
        # scaffolds; we only assert that no ``.lock`` sentinel appears as
        # a dirty entry in git status.  The managed block should ignore
        # them via the ``.vaultspec/*.lock`` and ``/.*.lock`` patterns.
        status = _run_git(tmp_path, "status", "--porcelain")
        lock_entries = [
            line for line in status.stdout.splitlines() if line.endswith(".lock")
        ]
        assert lock_entries == [], (
            f"Expected no lock sentinels in git status, saw: {lock_entries!r}"
        )

    def test_legacy_tracked_providers_json_gets_untracked(self, tmp_path: Path) -> None:
        _init_git_repo(tmp_path)
        vaultspec_dir = tmp_path / ".vaultspec"
        vaultspec_dir.mkdir()
        (vaultspec_dir / "providers.json").write_text(
            '{"version": "2.0", "installed": []}', encoding="utf-8"
        )
        _run_git(tmp_path, "add", ".vaultspec/providers.json")
        _run_git(tmp_path, "commit", "-q", "-m", "legacy tracked manifest")

        install_run(
            path=tmp_path,
            provider="all",
            upgrade=False,
            dry_run=False,
            force=True,
        )

        ls = _run_git(
            tmp_path, "ls-files", "--error-unmatch", ".vaultspec/providers.json"
        )
        assert ls.returncode != 0, (
            "providers.json must no longer be tracked after install"
        )


# ---- Domain 5: rename updates incoming wiki-link references ------------------


class TestStructureRenameUpdatesRefs:
    """``check_structure(fix=True)`` must rewrite incoming wiki-links."""

    def test_rename_updates_related_refs(self, tmp_path: Path) -> None:
        from vaultspec_core.graph import VaultGraph
        from vaultspec_core.vaultcore.checks import check_structure

        vault = tmp_path / ".vault"
        audit_dir = vault / "audit"
        adr_dir = vault / "adr"
        audit_dir.mkdir(parents=True)
        adr_dir.mkdir(parents=True)

        # Source doc with a non-canonical suffix (``-review`` instead of
        # ``-audit``) - triggers a rename.
        misnamed = audit_dir / "2026-03-01-widget-review.md"
        misnamed.write_text(
            "---\n"
            "tags:\n"
            '  - "#audit"\n'
            '  - "#widget"\n'
            "date: '2026-03-01'\n"
            "related:\n"
            '  - "[[2026-03-01-widget-research]]"\n'
            "---\n\n"
            "# widget audit\n",
            encoding="utf-8",
        )

        # Doc that links to the misnamed doc via its current stem.
        backref = adr_dir / "2026-03-02-widget-adr.md"
        backref.write_text(
            "---\n"
            "tags:\n"
            '  - "#adr"\n'
            '  - "#widget"\n'
            "date: '2026-03-02'\n"
            "related:\n"
            '  - "[[2026-03-01-widget-review]]"\n'
            "---\n\n"
            "# widget adr\n",
            encoding="utf-8",
        )

        graph = VaultGraph(tmp_path)
        snapshot = graph.to_snapshot()
        result = check_structure(tmp_path, snapshot=snapshot, fix=True)

        renamed = audit_dir / "2026-03-01-widget-review-audit.md"
        assert renamed.exists(), "expected file to be renamed to -audit suffix"
        assert not misnamed.exists()

        backref_text = backref.read_text(encoding="utf-8")
        assert "[[2026-03-01-widget-review-audit]]" in backref_text
        assert "[[2026-03-01-widget-review]]" not in backref_text
        expected_msg = (
            "Updated wiki-link: [[2026-03-01-widget-review]] -> "
            "[[2026-03-01-widget-review-audit]]"
        )
        assert any(expected_msg in d.message for d in result.diagnostics), (
            f"Expected precise rewrite diagnostic; saw "
            f"{[d.message for d in result.diagnostics]!r}"
        )

    def test_rename_survives_bom_prefixed_backref(self, tmp_path: Path) -> None:
        """Files with UTF-8 BOM must still get their related: refs rewritten."""
        from vaultspec_core.graph import VaultGraph
        from vaultspec_core.vaultcore.checks import check_structure

        vault = tmp_path / ".vault"
        audit_dir = vault / "audit"
        adr_dir = vault / "adr"
        audit_dir.mkdir(parents=True)
        adr_dir.mkdir(parents=True)

        misnamed = audit_dir / "2026-03-01-bom-review.md"
        misnamed.write_text(
            "---\n"
            "tags:\n"
            '  - "#audit"\n'
            '  - "#bom"\n'
            "date: '2026-03-01'\n"
            "---\n\n# bom audit\n",
            encoding="utf-8",
        )

        # BOM-prefixed document referencing the misnamed doc.
        backref = adr_dir / "2026-03-02-bom-adr.md"
        backref.write_bytes(
            b"\xef\xbb\xbf"
            + (
                b"---\n"
                b"tags:\n"
                b'  - "#adr"\n'
                b'  - "#bom"\n'
                b"date: '2026-03-02'\n"
                b"related:\n"
                b'  - "[[2026-03-01-bom-review]]"\n'
                b"---\n\n# bom adr\n"
            )
        )

        graph = VaultGraph(tmp_path)
        snapshot = graph.to_snapshot()
        check_structure(tmp_path, snapshot=snapshot, fix=True)

        written = backref.read_bytes()
        assert written.startswith(b"\xef\xbb\xbf"), "BOM must be preserved"
        text = written.decode("utf-8-sig")
        assert "[[2026-03-01-bom-review-audit]]" in text
        assert "[[2026-03-01-bom-review]]" not in text

    def test_rename_preserves_crlf_endings(self, tmp_path: Path) -> None:
        """CRLF-authored files must not get mixed LF endings on rewrite."""
        from vaultspec_core.graph import VaultGraph
        from vaultspec_core.vaultcore.checks import check_structure

        vault = tmp_path / ".vault"
        audit_dir = vault / "audit"
        adr_dir = vault / "adr"
        audit_dir.mkdir(parents=True)
        adr_dir.mkdir(parents=True)

        misnamed = audit_dir / "2026-03-01-crlf-review.md"
        misnamed.write_bytes(
            b"---\r\n"
            b"tags:\r\n"
            b'  - "#audit"\r\n'
            b'  - "#crlf"\r\n'
            b"date: '2026-03-01'\r\n"
            b"---\r\n\r\n# crlf audit\r\n"
        )

        backref = adr_dir / "2026-03-02-crlf-adr.md"
        backref.write_bytes(
            b"---\r\n"
            b"tags:\r\n"
            b'  - "#adr"\r\n'
            b'  - "#crlf"\r\n'
            b"date: '2026-03-02'\r\n"
            b"related:\r\n"
            b'  - "[[2026-03-01-crlf-review]]"\r\n'
            b"---\r\n\r\n# crlf adr\r\n"
        )

        graph = VaultGraph(tmp_path)
        snapshot = graph.to_snapshot()
        check_structure(tmp_path, snapshot=snapshot, fix=True)

        written = backref.read_bytes()
        assert b"[[2026-03-01-crlf-review-audit]]" in written
        assert b"\r\n" in written, "CRLF convention must be preserved"
        # Guard against mixed endings - no lone LFs outside a CRLF pair.
        stripped = written.replace(b"\r\n", b"")
        assert b"\n" not in stripped, (
            "Rewrite must not introduce lone LFs alongside CRLF"
        )

    def test_rename_collision_emits_error(self, tmp_path: Path) -> None:
        """When two source files would rename to the same target, emit ERROR."""
        from vaultspec_core.graph import VaultGraph
        from vaultspec_core.vaultcore.checks import check_structure
        from vaultspec_core.vaultcore.checks._base import Severity

        vault = tmp_path / ".vault"
        audit_dir = vault / "audit"
        audit_dir.mkdir(parents=True)

        # Pre-existing canonical target that matches the fix output
        # of the stale file (stale "-review.md" fix target is
        # "-review-audit.md").
        (audit_dir / "2026-03-01-collision-review-audit.md").write_text(
            "---\n"
            "tags:\n"
            '  - "#audit"\n'
            '  - "#collision"\n'
            "date: '2026-03-01'\n"
            "---\n\n# collision canonical\n",
            encoding="utf-8",
        )
        # Misnamed sibling whose fix target collides with the canonical.
        stale = audit_dir / "2026-03-01-collision-review.md"
        stale.write_text(
            "---\n"
            "tags:\n"
            '  - "#audit"\n'
            '  - "#collision"\n'
            "date: '2026-03-01'\n"
            "---\n\n# collision stale\n",
            encoding="utf-8",
        )

        graph = VaultGraph(tmp_path)
        snapshot = graph.to_snapshot()
        result = check_structure(tmp_path, snapshot=snapshot, fix=True)

        assert stale.exists(), "stale file must remain since rename collided"
        assert any(
            d.severity == Severity.ERROR and "target already exists" in d.message
            for d in result.diagnostics
        ), "collision must surface as ERROR diagnostic"

    def test_rename_chain_resolved_transitively(self, tmp_path: Path) -> None:
        """Chained renames (A -> B -> C) rewrite [[A]] directly to [[C]]."""
        from vaultspec_core.vaultcore.checks._base import (
            CheckResult,
        )
        from vaultspec_core.vaultcore.checks.structure import (
            _rewrite_incoming_refs,
        )

        vault = tmp_path / ".vault"
        adr_dir = vault / "adr"
        adr_dir.mkdir(parents=True)
        backref = adr_dir / "2026-03-02-chain-adr.md"
        backref.write_text(
            "---\n"
            "tags:\n"
            '  - "#adr"\n'
            '  - "#chain"\n'
            "date: '2026-03-02'\n"
            "related:\n"
            '  - "[[alpha]]"\n'
            "---\n\n# chain adr\n",
            encoding="utf-8",
        )

        result = CheckResult(check_name="structure", supports_fix=True)
        _rewrite_incoming_refs(tmp_path, [("alpha", "beta"), ("beta", "gamma")], result)

        written = backref.read_text(encoding="utf-8")
        assert "[[gamma]]" in written
        assert "[[alpha]]" not in written
        assert "[[beta]]" not in written
        # Exactly one rewrite should fire; the chain collapse must not
        # double-count when both [[alpha]] and [[beta]] resolve to gamma.
        assert result.fixed_count == 1
        rewrite_diags = [
            d for d in result.diagnostics if "Updated wiki-link" in d.message
        ]
        assert len(rewrite_diags) == 1
        assert "[[alpha]] -> [[gamma]]" in rewrite_diags[0].message

    def test_rewrite_preserves_trailing_yaml_comment(self, tmp_path: Path) -> None:
        """A ``related:`` entry with a trailing YAML comment must be rewritten."""
        from vaultspec_core.vaultcore.checks._base import CheckResult
        from vaultspec_core.vaultcore.checks.structure import (
            _rewrite_incoming_refs,
        )

        vault = tmp_path / ".vault"
        adr_dir = vault / "adr"
        adr_dir.mkdir(parents=True)
        backref = adr_dir / "2026-03-02-comment-adr.md"
        backref.write_text(
            "---\n"
            "tags:\n"
            '  - "#adr"\n'
            '  - "#comment"\n'
            "date: '2026-03-02'\n"
            "related:\n"
            '  - "[[alpha]]"  # see research note\n'
            "---\n\n# comment adr\n",
            encoding="utf-8",
        )

        result = CheckResult(check_name="structure", supports_fix=True)
        _rewrite_incoming_refs(tmp_path, [("alpha", "beta")], result)

        written = backref.read_text(encoding="utf-8")
        assert '"[[beta]]"' in written
        assert "# see research note" in written, (
            "Trailing YAML comment must survive the rewrite"
        )
        assert result.fixed_count == 1

    def test_rewrite_detects_indented_related_key(self, tmp_path: Path) -> None:
        """An indented ``related:`` key must still enter the rewrite scan.

        YAML frontmatter permits (though the vault template does not
        typically use) indentation of top-level keys.  The scanner must
        not assume column-zero anchoring.
        """
        from vaultspec_core.vaultcore.checks._base import CheckResult
        from vaultspec_core.vaultcore.checks.structure import (
            _rewrite_incoming_refs,
        )

        vault = tmp_path / ".vault"
        adr_dir = vault / "adr"
        adr_dir.mkdir(parents=True)
        backref = adr_dir / "2026-03-02-indent-adr.md"
        # `related:` intentionally indented by two spaces.
        backref.write_text(
            "---\n"
            "tags:\n"
            '  - "#adr"\n'
            '  - "#indent"\n'
            "date: '2026-03-02'\n"
            "  related:\n"
            '    - "[[alpha]]"\n'
            "---\n\n# indent adr\n",
            encoding="utf-8",
        )

        result = CheckResult(check_name="structure", supports_fix=True)
        _rewrite_incoming_refs(tmp_path, [("alpha", "beta")], result)

        written = backref.read_text(encoding="utf-8")
        assert '"[[beta]]"' in written
        assert '"[[alpha]]"' not in written
        assert result.fixed_count == 1

    def test_rewrite_warns_on_frontmatter_budget_overflow(self, tmp_path: Path) -> None:
        """Frontmatter exceeding the line budget must surface a WARNING."""
        from vaultspec_core.vaultcore.checks._base import (
            CheckResult,
            Severity,
        )
        from vaultspec_core.vaultcore.checks.structure import (
            _FRONTMATTER_LINE_BUDGET,
            _rewrite_incoming_refs,
        )

        vault = tmp_path / ".vault"
        adr_dir = vault / "adr"
        adr_dir.mkdir(parents=True)
        # Build a pathological doc: opening fence, then enough filler lines
        # to overflow the budget before the scanner could reach the
        # related: block or the closing fence.
        filler_lines = ["filler: value" for _ in range(_FRONTMATTER_LINE_BUDGET + 20)]
        pathological = adr_dir / "2026-03-02-budget-adr.md"
        pathological.write_text(
            "---\n" + "\n".join(filler_lines) + "\n",
            encoding="utf-8",
        )

        result = CheckResult(check_name="structure", supports_fix=True)
        _rewrite_incoming_refs(tmp_path, [("alpha", "beta")], result)

        warnings = [d for d in result.diagnostics if d.severity == Severity.WARNING]
        assert any("Frontmatter exceeds" in d.message for d in warnings), (
            f"expected budget WARNING, saw {[d.message for d in warnings]!r}"
        )

    def test_rewrite_skips_hidden_obsidian_docs(self, tmp_path: Path) -> None:
        """Files under ``.vault/.obsidian/`` and ``.vault/.trash/`` must not
        be rewritten - they hold editor state, not vault content.
        """
        from vaultspec_core.vaultcore.checks._base import CheckResult
        from vaultspec_core.vaultcore.checks.structure import (
            _rewrite_incoming_refs,
        )

        vault = tmp_path / ".vault"
        obsidian_dir = vault / ".obsidian"
        obsidian_dir.mkdir(parents=True)
        trash_dir = vault / ".trash"
        trash_dir.mkdir(parents=True)

        obsidian_doc = obsidian_dir / "workspace.md"
        trash_doc = trash_dir / "2026-03-01-old-reference-research.md"
        original = (
            "---\n"
            "tags:\n"
            '  - "#research"\n'
            '  - "#internal"\n'
            "date: '2026-03-01'\n"
            "related:\n"
            '  - "[[alpha]]"\n'
            "---\n\n# internal\n"
        )
        obsidian_doc.write_text(original, encoding="utf-8")
        trash_doc.write_text(original, encoding="utf-8")

        result = CheckResult(check_name="structure", supports_fix=True)
        _rewrite_incoming_refs(tmp_path, [("alpha", "beta")], result)

        assert obsidian_doc.read_text(encoding="utf-8") == original, (
            ".obsidian/ docs must not be mutated"
        )
        assert trash_doc.read_text(encoding="utf-8") == original, (
            ".trash/ docs must not be mutated"
        )
        assert result.fixed_count == 0

    def test_rewrite_skips_three_node_rename_cycle(self, tmp_path: Path) -> None:
        """A 3-cycle (A -> B -> C -> A) must be detected and dropped."""
        from vaultspec_core.vaultcore.checks._base import CheckResult
        from vaultspec_core.vaultcore.checks.structure import (
            _rewrite_incoming_refs,
        )

        vault = tmp_path / ".vault"
        adr_dir = vault / "adr"
        adr_dir.mkdir(parents=True)
        backref = adr_dir / "2026-03-02-tri-cycle-adr.md"
        original = (
            "---\n"
            "tags:\n"
            '  - "#adr"\n'
            '  - "#tri-cycle"\n'
            "date: '2026-03-02'\n"
            "related:\n"
            '  - "[[alpha]]"\n'
            "---\n\n# tri-cycle adr\n"
        )
        backref.write_text(original, encoding="utf-8")

        result = CheckResult(check_name="structure", supports_fix=True)
        _rewrite_incoming_refs(
            tmp_path,
            [("alpha", "beta"), ("beta", "gamma"), ("gamma", "alpha")],
            result,
        )

        assert backref.read_text(encoding="utf-8") == original, (
            "3-cycle must produce no rewrite; file must be byte-identical"
        )
        assert result.fixed_count == 0
        assert not any("Updated wiki-link" in d.message for d in result.diagnostics)

    def test_rewrite_skips_rename_cycles(self, tmp_path: Path) -> None:
        """A 2-cycle in raw_map must not produce phantom self-rewrites."""
        from vaultspec_core.vaultcore.checks._base import CheckResult
        from vaultspec_core.vaultcore.checks.structure import (
            _rewrite_incoming_refs,
        )

        vault = tmp_path / ".vault"
        adr_dir = vault / "adr"
        adr_dir.mkdir(parents=True)
        backref = adr_dir / "2026-03-02-cycle-adr.md"
        original = (
            "---\n"
            "tags:\n"
            '  - "#adr"\n'
            '  - "#cycle"\n'
            "date: '2026-03-02'\n"
            "related:\n"
            '  - "[[alpha]]"\n'
            "---\n\n# cycle adr\n"
        )
        backref.write_text(original, encoding="utf-8")

        result = CheckResult(check_name="structure", supports_fix=True)
        _rewrite_incoming_refs(tmp_path, [("alpha", "beta"), ("beta", "alpha")], result)

        # Cycle resolution must drop both entries; file must be unchanged.
        assert backref.read_text(encoding="utf-8") == original
        assert result.fixed_count == 0
        assert not any("Updated wiki-link" in d.message for d in result.diagnostics)
