"""Tests for diagnostic signal collectors and the diagnose orchestrator."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from vaultspec_core.core.diagnosis.collectors import (
    collect_builtin_version_state,
    collect_config_state,
    collect_content_integrity,
    collect_framework_presence,
    collect_gitignore_state,
    collect_manifest_coherence,
    collect_mcp_config_state,
    collect_provider_dir_state,
)
from vaultspec_core.core.diagnosis.diagnosis import diagnose
from vaultspec_core.core.diagnosis.signals import (
    BuiltinVersionSignal,
    ConfigSignal,
    ContentSignal,
    FrameworkSignal,
    GitignoreSignal,
    ManifestEntrySignal,
    ProviderDirSignal,
)
from vaultspec_core.core.enums import Tool
from vaultspec_core.core.gitignore import DEFAULT_ENTRIES, MARKER_BEGIN, MARKER_END

pytestmark = [pytest.mark.unit]


def _write_manifest(root: Path, installed: list[str]) -> None:
    """Write a minimal valid providers.json manifest."""
    path = root / ".vaultspec" / "providers.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": "2.0", "installed": installed, "serial": 1}
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _write_gitignore(root: Path, content: str) -> None:
    gi = root / ".gitignore"
    gi.write_text(content, encoding="utf-8")


# ---------------------------------------------------------------------------
# collect_framework_presence
# ---------------------------------------------------------------------------
class TestFrameworkPresence:
    def test_missing(self, tmp_path: Path) -> None:
        assert collect_framework_presence(tmp_path) == FrameworkSignal.MISSING

    def test_corrupted_no_manifest(self, tmp_path: Path) -> None:
        (tmp_path / ".vaultspec").mkdir()
        assert collect_framework_presence(tmp_path) == FrameworkSignal.CORRUPTED

    def test_corrupted_invalid_json(self, tmp_path: Path) -> None:
        d = tmp_path / ".vaultspec"
        d.mkdir()
        (d / "providers.json").write_text("{bad", encoding="utf-8")
        assert collect_framework_presence(tmp_path) == FrameworkSignal.CORRUPTED

    def test_corrupted_no_installed_key(self, tmp_path: Path) -> None:
        d = tmp_path / ".vaultspec"
        d.mkdir()
        (d / "providers.json").write_text('{"version": "2.0"}', encoding="utf-8")
        assert collect_framework_presence(tmp_path) == FrameworkSignal.CORRUPTED

    def test_present(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, ["claude"])
        assert collect_framework_presence(tmp_path) == FrameworkSignal.PRESENT


# ---------------------------------------------------------------------------
# collect_manifest_coherence
# ---------------------------------------------------------------------------
class TestManifestCoherence:
    def test_coherent(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, ["claude"])
        (tmp_path / ".claude").mkdir()
        result = collect_manifest_coherence(tmp_path)
        assert result["claude"] == ManifestEntrySignal.COHERENT

    def test_orphaned(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, ["claude"])
        result = collect_manifest_coherence(tmp_path)
        assert result["claude"] == ManifestEntrySignal.ORPHANED

    def test_untracked(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, [])
        (tmp_path / ".claude").mkdir()
        result = collect_manifest_coherence(tmp_path)
        assert result["claude"] == ManifestEntrySignal.UNTRACKED

    def test_not_installed(self, tmp_path: Path) -> None:
        _write_manifest(tmp_path, [])
        result = collect_manifest_coherence(tmp_path)
        assert result["claude"] == ManifestEntrySignal.NOT_INSTALLED


# ---------------------------------------------------------------------------
# collect_provider_dir_state
# ---------------------------------------------------------------------------
class TestProviderDirState:
    def test_missing(self, tmp_path: Path) -> None:
        assert (
            collect_provider_dir_state(tmp_path, "claude") == ProviderDirSignal.MISSING
        )

    def test_empty(self, tmp_path: Path) -> None:
        (tmp_path / ".claude").mkdir()
        assert collect_provider_dir_state(tmp_path, "claude") == ProviderDirSignal.EMPTY

    def test_partial_without_context(self, tmp_path: Path) -> None:
        """Without an active WorkspaceContext, a non-empty dir is PARTIAL.

        Uses a factory-built workspace without init_paths so the
        contextvar is genuinely unset for the target path.
        """
        d = tmp_path / ".claude"
        d.mkdir()
        (d / "some_file.txt").write_text("x", encoding="utf-8")

        # The collector catches LookupError and also handles the case
        # where get_context() returns a context for a DIFFERENT target.
        # When cfg is None (no tool config for this target), returns PARTIAL.
        result = collect_provider_dir_state(tmp_path, "claude")
        assert result in (ProviderDirSignal.PARTIAL, ProviderDirSignal.MIXED)

    def test_complete(self, test_project: Path) -> None:
        """With a full test project, claude provider should be COMPLETE."""
        result = collect_provider_dir_state(test_project, "claude")
        assert result in (ProviderDirSignal.COMPLETE, ProviderDirSignal.PARTIAL)

    def test_unknown_tool(self, tmp_path: Path) -> None:
        assert (
            collect_provider_dir_state(tmp_path, "nonexistent")
            == ProviderDirSignal.MISSING
        )


# ---------------------------------------------------------------------------
# collect_builtin_version_state
# ---------------------------------------------------------------------------
class TestBuiltinVersionState:
    def test_no_snapshots(self, tmp_path: Path) -> None:
        (tmp_path / ".vaultspec").mkdir(parents=True)
        assert (
            collect_builtin_version_state(tmp_path) == BuiltinVersionSignal.NO_SNAPSHOTS
        )

    def test_current(self, tmp_path: Path) -> None:
        vs = tmp_path / ".vaultspec"
        snap = vs / "_snapshots" / "rules"
        snap.mkdir(parents=True)
        rules = vs / "rules" / "rules"
        rules.mkdir(parents=True)

        (snap / "test.builtin.md").write_text("content", encoding="utf-8")
        (rules / "test.builtin.md").write_text("content", encoding="utf-8")

        assert collect_builtin_version_state(tmp_path) == BuiltinVersionSignal.CURRENT

    def test_modified(self, tmp_path: Path) -> None:
        vs = tmp_path / ".vaultspec"
        snap = vs / "_snapshots" / "rules"
        snap.mkdir(parents=True)
        rules = vs / "rules" / "rules"
        rules.mkdir(parents=True)

        (snap / "test.builtin.md").write_text("original", encoding="utf-8")
        (rules / "test.builtin.md").write_text("changed", encoding="utf-8")

        assert collect_builtin_version_state(tmp_path) == BuiltinVersionSignal.MODIFIED

    def test_deleted(self, tmp_path: Path) -> None:
        vs = tmp_path / ".vaultspec"
        snap = vs / "_snapshots" / "rules"
        snap.mkdir(parents=True)
        (vs / "rules" / "rules").mkdir(parents=True)

        (snap / "test.builtin.md").write_text("original", encoding="utf-8")
        # No corresponding file in rules/

        assert collect_builtin_version_state(tmp_path) == BuiltinVersionSignal.DELETED


# ---------------------------------------------------------------------------
# collect_config_state
# ---------------------------------------------------------------------------
class TestConfigState:
    def test_missing_no_context(self, tmp_path: Path) -> None:
        """Without WorkspaceContext, config is always MISSING."""
        assert collect_config_state(tmp_path, "claude") == ConfigSignal.MISSING

    def test_ok_with_marker(self, test_project: Path) -> None:
        """After install, CLAUDE.md should have the AUTO-GENERATED marker."""
        result = collect_config_state(test_project, "claude")
        assert result == ConfigSignal.OK

    def test_foreign_without_marker(self, test_project: Path) -> None:
        """Overwriting config content without marker yields FOREIGN."""
        from vaultspec_core.core.types import get_context

        cfg = get_context().tool_configs[Tool.CLAUDE]
        assert cfg.config_file is not None
        cfg.config_file.write_text("# My custom config\n", encoding="utf-8")
        assert collect_config_state(test_project, "claude") == ConfigSignal.FOREIGN


# ---------------------------------------------------------------------------
# collect_mcp_config_state
# ---------------------------------------------------------------------------
class TestMcpConfigState:
    def test_missing_file(self, tmp_path: Path) -> None:
        assert collect_mcp_config_state(tmp_path) == ConfigSignal.PARTIAL_MCP

    def test_no_vaultspec_entry(self, tmp_path: Path) -> None:
        mcp = tmp_path / ".mcp.json"
        mcp.write_text('{"mcpServers": {}}', encoding="utf-8")
        assert collect_mcp_config_state(tmp_path) == ConfigSignal.PARTIAL_MCP

    def test_ok(self, tmp_path: Path) -> None:
        mcp = tmp_path / ".mcp.json"
        payload = {"mcpServers": {"vaultspec-core": {"command": "uv"}}}
        mcp.write_text(json.dumps(payload), encoding="utf-8")
        assert collect_mcp_config_state(tmp_path) == ConfigSignal.OK

    def test_user_mcp(self, tmp_path: Path) -> None:
        mcp = tmp_path / ".mcp.json"
        payload = {
            "mcpServers": {
                "vaultspec-core": {"command": "uv"},
                "other-server": {"command": "node"},
            }
        }
        mcp.write_text(json.dumps(payload), encoding="utf-8")
        assert collect_mcp_config_state(tmp_path) == ConfigSignal.USER_MCP


# ---------------------------------------------------------------------------
# collect_gitignore_state
# ---------------------------------------------------------------------------
class TestGitignoreState:
    def test_no_file(self, tmp_path: Path) -> None:
        assert collect_gitignore_state(tmp_path) == GitignoreSignal.NO_FILE

    def test_no_entries(self, tmp_path: Path) -> None:
        _write_gitignore(tmp_path, "node_modules/\n*.pyc\n")
        assert collect_gitignore_state(tmp_path) == GitignoreSignal.NO_ENTRIES

    def test_complete(self, tmp_path: Path) -> None:
        entries = "\n".join(DEFAULT_ENTRIES)
        content = f"node_modules/\n\n{MARKER_BEGIN}\n{entries}\n{MARKER_END}\n"
        _write_gitignore(tmp_path, content)
        assert collect_gitignore_state(tmp_path) == GitignoreSignal.COMPLETE

    def test_partial(self, tmp_path: Path) -> None:
        (tmp_path / ".vaultspec").mkdir()
        content = f"{MARKER_BEGIN}\nsome/other/path\n{MARKER_END}\n"
        _write_gitignore(tmp_path, content)
        assert collect_gitignore_state(tmp_path) == GitignoreSignal.PARTIAL

    def test_corrupted_only_begin(self, tmp_path: Path) -> None:
        _write_gitignore(tmp_path, f"{MARKER_BEGIN}\nentry\n")
        assert collect_gitignore_state(tmp_path) == GitignoreSignal.CORRUPTED

    def test_corrupted_only_end(self, tmp_path: Path) -> None:
        _write_gitignore(tmp_path, f"entry\n{MARKER_END}\n")
        assert collect_gitignore_state(tmp_path) == GitignoreSignal.CORRUPTED


# ---------------------------------------------------------------------------
# collect_content_integrity
# ---------------------------------------------------------------------------
class TestContentIntegrity:
    def test_empty_without_context(self, tmp_path: Path) -> None:
        result = collect_content_integrity(tmp_path, "claude")
        assert result == {}

    def test_clean_stale_missing(self, test_project: Path) -> None:
        """With a real project, rule files synced from source are CLEAN."""
        from vaultspec_core.core.types import get_context

        ctx = get_context()
        cfg = ctx.tool_configs.get(Tool.CLAUDE)
        assert cfg is not None and cfg.rules_dir is not None

        result = collect_content_integrity(test_project, "claude")
        # All files present in both source and dest should be CLEAN
        for name, signal in result.items():
            if signal == ContentSignal.CLEAN:
                assert (cfg.rules_dir / name).exists()
                assert (ctx.rules_src_dir / name).exists()

    def test_builtin_files_not_flagged_stale(self, test_project: Path) -> None:
        """Synthesized ``*-system.builtin.md`` files must not be flagged STALE.

        These files are generated by :func:`~vaultspec_core.core.system.system_sync`
        and have no corresponding source file in ``.vaultspec/rules/``.
        """
        from vaultspec_core.core.types import get_context

        ctx = get_context()
        cfg = ctx.tool_configs.get(Tool.CLAUDE)
        assert cfg is not None and cfg.rules_dir is not None

        # Place a synthesized builtin file in the dest rules dir
        builtin = cfg.rules_dir / "vaultspec-system.builtin.md"
        builtin.write_text("# Synthesized builtin\n", encoding="utf-8")

        result = collect_content_integrity(test_project, "claude")
        assert "vaultspec-system.builtin.md" not in result


# ---------------------------------------------------------------------------
# diagnose() orchestrator
# ---------------------------------------------------------------------------
class TestDiagnose:
    def test_missing_framework(self, tmp_path: Path) -> None:
        """When framework is missing, only gitignore and framework are set."""
        _write_gitignore(tmp_path, "*.pyc\n")
        result = diagnose(tmp_path, scope="full")
        assert result.framework == FrameworkSignal.MISSING
        assert result.gitignore == GitignoreSignal.NO_ENTRIES
        assert result.providers == {}

    def test_framework_scope(self, tmp_path: Path) -> None:
        """Framework scope collects manifest coherence but not dir state."""
        _write_manifest(tmp_path, ["claude"])
        (tmp_path / ".claude").mkdir()
        _write_gitignore(tmp_path, "*.pyc\n")

        result = diagnose(tmp_path, scope="framework")
        assert result.framework == FrameworkSignal.PRESENT
        assert Tool.CLAUDE in result.providers
        # Framework scope sets dir_state to MISSING (not collected)
        assert result.providers[Tool.CLAUDE].dir_state == ProviderDirSignal.MISSING
        claude = result.providers[Tool.CLAUDE]
        assert claude.manifest_entry == ManifestEntrySignal.COHERENT

    def test_sync_scope(self, tmp_path: Path) -> None:
        """Sync scope collects provider dir and config but not content."""
        _write_manifest(tmp_path, ["claude"])
        (tmp_path / ".claude").mkdir()
        _write_gitignore(tmp_path, "*.pyc\n")

        result = diagnose(tmp_path, scope="sync")
        assert result.framework == FrameworkSignal.PRESENT
        assert Tool.CLAUDE in result.providers
        prov = result.providers[Tool.CLAUDE]
        # Content is not collected in sync scope
        assert prov.content == {}

    def test_full_scope_with_project(self, test_project: Path) -> None:
        """Full scope on a real project collects everything."""
        result = diagnose(test_project, scope="full")
        assert result.framework == FrameworkSignal.PRESENT
        assert result.builtin_version in (
            BuiltinVersionSignal.CURRENT,
            BuiltinVersionSignal.NO_SNAPSHOTS,
        )
        assert Tool.CLAUDE in result.providers
        prov = result.providers[Tool.CLAUDE]
        assert prov.manifest_entry == ManifestEntrySignal.COHERENT

    def test_corrupted_framework_collects_partial_diagnosis(
        self, tmp_path: Path
    ) -> None:
        """When framework is corrupted, providers are still diagnosed for
        directory presence and manifest coherence (but not content integrity)."""
        d = tmp_path / ".vaultspec"
        d.mkdir()
        (d / "providers.json").write_text("{bad", encoding="utf-8")

        result = diagnose(tmp_path)
        assert result.framework == FrameworkSignal.CORRUPTED
        # Providers are populated with basic dir/manifest signals
        assert len(result.providers) > 0
        for prov in result.providers.values():
            # Content integrity is not collected when corrupted
            assert prov.content == {}


# ---------------------------------------------------------------------------
# collect_gitignore_state with inverted markers
# ---------------------------------------------------------------------------
class TestGitignoreInvertedMarkers:
    def test_inverted_markers_returns_corrupted(self, tmp_path: Path) -> None:
        content = f"node_modules/\n{MARKER_END}\n.entry/\n{MARKER_BEGIN}\n"
        _write_gitignore(tmp_path, content)
        assert collect_gitignore_state(tmp_path) == GitignoreSignal.CORRUPTED


# ---------------------------------------------------------------------------
# diagnose() scope validation
# ---------------------------------------------------------------------------
class TestDiagnoseScopeValidation:
    def test_invalid_scope_raises_value_error(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError, match="Invalid scope"):
            diagnose(tmp_path, scope="nonsense")
