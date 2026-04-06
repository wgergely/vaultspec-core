"""Workspace condition factory for on-disk test state generation.

Builds workspace states compositionally via chainable methods.  Every
mutation method returns ``self`` so callers can compose conditions fluently::

    factory = WorkspaceFactory(tmp_path)
    factory.install().corrupt_manifest()

    factory = WorkspaceFactory(tmp_path)
    factory.install().add_user_content("claude").outdated_vaultspec_rules("claude")

Named presets combine common conditions::

    factory = WorkspaceFactory(tmp_path)
    factory.install().preset_partially_managed("claude")
"""

from __future__ import annotations

import json
import shutil
from typing import TYPE_CHECKING, Self

from typer.testing import CliRunner

from vaultspec_core.cli import app
from vaultspec_core.core.enums import DirName, FileName

if TYPE_CHECKING:
    from pathlib import Path

    from click.testing import Result

    from vaultspec_core.core.manifest import ManifestData

# Provider name -> top-level directory mapping derived from DirName.
_PROVIDER_DIR: dict[str, str] = {
    "claude": DirName.CLAUDE,
    "gemini": DirName.GEMINI,
    "antigravity": DirName.ANTIGRAVITY,
    "codex": DirName.CODEX,
}

# Provider name -> root config filename mapping derived from FileName.
_PROVIDER_CONFIG: dict[str, str] = {
    "claude": FileName.CLAUDE,
    "gemini": FileName.GEMINI,
    "codex": FileName.AGENTS,
}


def _provider_dir(root: Path, provider: str) -> Path:
    """Resolve the on-disk directory for *provider*."""
    return root / _PROVIDER_DIR[provider]


class WorkspaceFactory:
    """Compositional builder for on-disk workspace test states.

    Each method returns ``self`` so calls can be chained.  Methods are
    grouped by the workspace aspect they mutate: base states, manifest,
    provider directories, gitignore, config files, MCP, and framework.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self._installed = False
        self._runner = CliRunner(env={"NO_COLOR": "1"})

    @classmethod
    def wrap(cls, root: Path) -> WorkspaceFactory:
        """Wrap an existing directory with factory inspection/mutation."""
        f = cls(root)
        f._installed = (root / ".vaultspec").is_dir()
        return f

    # ---- Properties --------------------------------------------------------

    @property
    def path(self) -> Path:
        """The workspace root path (for use as --target)."""
        return self.root

    @property
    def manifest_path(self) -> Path:
        """Path to ``providers.json``."""
        return self.root / DirName.VAULTSPEC / "providers.json"

    @property
    def is_installed(self) -> bool:
        """Whether ``.vaultspec/`` exists on disk."""
        return (self.root / DirName.VAULTSPEC).is_dir()

    # ---- CLI runner integration --------------------------------------------

    def run(self, *args: str) -> Result:
        """Invoke a CLI command against this workspace.

        Passes ``-t <root>`` at the root level **and** ``--target <root>``
        after the subcommand so both the root callback (``set_root_target``)
        and per-command ``TargetOption`` parameters receive the path.
        """
        target = str(self.root)
        cmd = ["-t", target, *args, "--target", target]
        return self._runner.invoke(app, cmd)

    # ---- State inspection --------------------------------------------------

    def read_manifest(self) -> ManifestData:
        """Read and return the current :class:`ManifestData`."""
        from vaultspec_core.core.manifest import read_manifest_data

        return read_manifest_data(self.root)

    def provider_dir_exists(self, provider: str) -> bool:
        """Check whether a provider's directory exists on disk."""
        return _provider_dir(self.root, provider).is_dir()

    def provider_has_rules(self, provider: str) -> bool:
        """Check whether a provider has synced rule files."""
        rules = _provider_dir(self.root, provider) / "rules"
        return rules.is_dir() and any(rules.glob("*.md"))

    def gitignore_has_block(self) -> bool:
        """Check whether ``.gitignore`` contains the managed block."""
        from vaultspec_core.core.gitignore import MARKER_BEGIN

        gi = self.root / ".gitignore"
        if not gi.exists():
            return False
        return MARKER_BEGIN in gi.read_text(encoding="utf-8")

    def gitattributes_has_block(self) -> bool:
        """Check whether ``.gitattributes`` contains the managed block."""
        from vaultspec_core.core.gitattributes import MARKER_BEGIN

        ga = self.root / ".gitattributes"
        if not ga.exists():
            return False
        return MARKER_BEGIN in ga.read_text(encoding="utf-8")

    def manifest_is_valid_json(self) -> bool:
        """Check whether ``providers.json`` is parseable JSON."""
        try:
            json.loads(self.manifest_path.read_text(encoding="utf-8"))
            return True
        except (json.JSONDecodeError, OSError):
            return False

    def mcp_has_vaultspec_entry(self) -> bool:
        """Check whether ``.mcp.json`` has the vaultspec-core server."""
        mcp = self.root / ".mcp.json"
        if not mcp.exists():
            return False
        try:
            raw = json.loads(mcp.read_text(encoding="utf-8"))
            return "vaultspec-core" in raw.get("mcpServers", {})
        except (json.JSONDecodeError, OSError):
            return False

    def mcp_has_user_entry(self, name: str = "my-custom-server") -> bool:
        """Check whether ``.mcp.json`` has a specific user server."""
        mcp = self.root / ".mcp.json"
        if not mcp.exists():
            return False
        try:
            raw = json.loads(mcp.read_text(encoding="utf-8"))
            return name in raw.get("mcpServers", {})
        except (json.JSONDecodeError, OSError):
            return False

    # ---- Base states -------------------------------------------------------

    def create_gitignore(self, content: str = "# project\n") -> Self:
        """Create ``.gitignore`` with the given content."""
        (self.root / ".gitignore").write_text(content, encoding="utf-8")
        return self

    def install(
        self,
        provider: str = "all",
        *,
        skip_gitignore: bool = False,
        upgrade: bool = False,
        force: bool = False,
        dry_run: bool = False,
        skip: set[str] | None = None,
    ) -> Self:
        """Run a real ``install_run``.

        Creates a minimal ``.gitignore`` first if one does not exist so
        the gitignore block writer has something to append to.  Pass
        ``skip_gitignore=True`` to suppress automatic ``.gitignore``
        creation.
        """
        from vaultspec_core.core.commands import install_run

        if not skip_gitignore and not (self.root / ".gitignore").exists():
            self.create_gitignore()
        install_run(
            path=self.root,
            provider=provider,
            upgrade=upgrade,
            force=force,
            dry_run=dry_run,
            skip=skip,
        )
        self._installed = True
        return self

    def sync(
        self,
        provider: str = "all",
        *,
        force: bool = False,
        dry_run: bool = False,
        skip: set[str] | None = None,
    ) -> Self:
        """Run a real ``sync_provider``."""
        from vaultspec_core.config import reset_config
        from vaultspec_core.config.workspace import resolve_workspace
        from vaultspec_core.core.commands import sync_provider
        from vaultspec_core.core.types import init_paths

        reset_config()
        layout = resolve_workspace(target_override=self.root)
        init_paths(layout)
        sync_provider(provider, force=force, dry_run=dry_run, skip=skip)
        return self

    def uninstall(
        self,
        provider: str = "all",
        *,
        force: bool = True,
        keep_vault: bool = True,
        dry_run: bool = False,
    ) -> Self:
        """Run a real ``uninstall_run``."""
        from vaultspec_core.core.commands import uninstall_run

        uninstall_run(
            path=self.root,
            provider=provider,
            keep_vault=keep_vault,
            dry_run=dry_run,
            force=force,
        )
        return self

    # ---- Manifest conditions -----------------------------------------------

    def corrupt_manifest(self) -> Self:
        """Write invalid JSON to ``providers.json``."""
        manifest = self.root / DirName.VAULTSPEC / "providers.json"
        manifest.write_text("{{{BROKEN", encoding="utf-8")
        return self

    def empty_manifest(self) -> Self:
        """Write valid JSON with an empty installed set."""
        from vaultspec_core.core.manifest import ManifestData, write_manifest_data

        write_manifest_data(self.root, ManifestData())
        return self

    def remove_provider_from_manifest(self, provider: str) -> Self:
        """Remove *provider* from the manifest without touching its directory."""
        from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data

        data = read_manifest_data(self.root)
        data.installed.discard(provider)
        data.provider_state.pop(provider, None)
        write_manifest_data(self.root, data)
        return self

    def add_phantom_provider(self, provider: str) -> Self:
        """Record *provider* in the manifest with no corresponding directory."""
        from vaultspec_core.core.manifest import add_providers

        add_providers(self.root, [provider])
        return self

    def set_old_vaultspec_version(self, version: str = "0.0.1") -> Self:
        """Set the manifest ``vaultspec_version`` to a stale value."""
        from vaultspec_core.core.manifest import read_manifest_data, write_manifest_data

        data = read_manifest_data(self.root)
        data.vaultspec_version = version
        write_manifest_data(self.root, data)
        return self

    # ---- Provider directory conditions -------------------------------------

    def delete_provider_dir(self, provider: str) -> Self:
        """Delete a provider's directory, orphaning its manifest entry."""
        d = _provider_dir(self.root, provider)
        if d.exists():
            shutil.rmtree(d)
        return self

    def empty_provider_dir(self, provider: str) -> Self:
        """Replace a provider's directory with an empty one."""
        d = _provider_dir(self.root, provider)
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
        return self

    def create_bare_provider_dir(self, provider: str) -> Self:
        """Create just the top-level provider directory (never managed)."""
        _provider_dir(self.root, provider).mkdir(parents=True, exist_ok=True)
        return self

    def add_user_content(
        self,
        provider: str,
        files: dict[str, str] | None = None,
    ) -> Self:
        """Add non-vaultspec user files to a provider directory."""
        d = _provider_dir(self.root, provider)
        d.mkdir(parents=True, exist_ok=True)
        if files is None:
            files = {
                "my-notes.txt": "User's personal notes",
                "rules/my-custom-rule.md": "---\nname: custom\n---\nMy rule",
            }
        for rel_path, content in files.items():
            f = d / rel_path
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(content, encoding="utf-8")
        return self

    def outdated_vaultspec_rules(self, provider: str) -> Self:
        """Overwrite the first synced rule to simulate stale content."""
        rules_dir = _provider_dir(self.root, provider) / "rules"
        if rules_dir.exists():
            for md in rules_dir.glob("*.md"):
                md.write_text(
                    "<!-- AUTO-GENERATED by cli.py config sync. -->\n"
                    "---\nname: outdated\n---\nOLD CONTENT FROM v0.0.1",
                    encoding="utf-8",
                )
                break
        return self

    def add_stale_rule(self, provider: str, name: str = "stale-orphan.md") -> Self:
        """Add a synced-looking rule file that has no builtin source."""
        rules_dir = _provider_dir(self.root, provider) / "rules"
        rules_dir.mkdir(parents=True, exist_ok=True)
        (rules_dir / name).write_text(
            "<!-- AUTO-GENERATED by cli.py config sync. -->\n"
            "---\nname: stale\n---\nThis file has no source",
            encoding="utf-8",
        )
        return self

    # ---- Gitignore conditions ----------------------------------------------

    def corrupt_gitignore_block(self) -> Self:
        """Remove the end marker, leaving an orphaned begin marker."""
        from vaultspec_core.core.gitignore import MARKER_END

        gi = self.root / ".gitignore"
        if gi.exists():
            content = gi.read_text(encoding="utf-8")
            content = content.replace(MARKER_END, "")
            gi.write_text(content, encoding="utf-8")
        return self

    def remove_gitignore_block(self) -> Self:
        """Remove the vaultspec-managed block entirely."""
        from vaultspec_core.core.enums import ManagedState
        from vaultspec_core.core.gitignore import ensure_gitignore_block

        ensure_gitignore_block(self.root, [], state=ManagedState.ABSENT)
        return self

    def delete_gitignore(self) -> Self:
        """Delete ``.gitignore`` entirely."""
        gi = self.root / ".gitignore"
        if gi.exists():
            gi.unlink()
        return self

    # ---- Gitattributes conditions ------------------------------------------

    def corrupt_gitattributes_block(self) -> Self:
        """Remove the end marker, leaving an orphaned begin marker."""
        from vaultspec_core.core.gitattributes import MARKER_END

        ga = self.root / ".gitattributes"
        if ga.exists():
            content = ga.read_text(encoding="utf-8")
            content = content.replace(MARKER_END, "")
            ga.write_text(content, encoding="utf-8")
        return self

    def remove_gitattributes_block(self) -> Self:
        """Remove the vaultspec-managed block entirely."""
        from vaultspec_core.core.enums import ManagedState
        from vaultspec_core.core.gitattributes import ensure_gitattributes_block

        ensure_gitattributes_block(self.root, state=ManagedState.ABSENT)
        return self

    def delete_gitattributes(self) -> Self:
        """Delete ``.gitattributes`` entirely."""
        ga = self.root / ".gitattributes"
        if ga.exists():
            ga.unlink()
        return self

    # ---- Config file conditions --------------------------------------------

    def delete_root_config(self, provider: str) -> Self:
        """Delete a provider's root config file (e.g. ``CLAUDE.md``)."""
        if provider in _PROVIDER_CONFIG:
            f = self.root / _PROVIDER_CONFIG[provider]
            if f.exists():
                f.unlink()
        return self

    def replace_root_config_with_user_content(self, provider: str) -> Self:
        """Replace root config with pure user-authored content."""
        if provider in _PROVIDER_CONFIG:
            f = self.root / _PROVIDER_CONFIG[provider]
            f.write_text("# My custom config\nNo vaultspec here.\n", encoding="utf-8")
        return self

    # ---- MCP conditions ----------------------------------------------------

    def add_user_mcp_servers(self) -> Self:
        """Merge a user MCP server entry into ``.mcp.json``."""
        mcp = self.root / ".mcp.json"
        if mcp.exists():
            raw = json.loads(mcp.read_text(encoding="utf-8"))
        else:
            raw = {"mcpServers": {}}
        raw["mcpServers"]["my-custom-server"] = {
            "command": "node",
            "args": ["server.js"],
        }
        mcp.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        return self

    def create_user_only_mcp(self) -> Self:
        """Create ``.mcp.json`` with only user-defined servers."""
        mcp = self.root / ".mcp.json"
        raw = {"mcpServers": {"my-server": {"command": "node", "args": []}}}
        mcp.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        return self

    def delete_mcp_json(self) -> Self:
        """Delete ``.mcp.json`` entirely."""
        mcp = self.root / ".mcp.json"
        if mcp.exists():
            mcp.unlink()
        return self

    def remove_mcp_vaultspec_entry(self) -> Self:
        """Remove only the ``vaultspec-core`` key from ``.mcp.json``."""
        mcp = self.root / ".mcp.json"
        if mcp.exists():
            raw = json.loads(mcp.read_text(encoding="utf-8"))
            servers = raw.get("mcpServers", {})
            servers.pop("vaultspec-core", None)
            mcp.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8")
        return self

    # ---- Framework conditions ----------------------------------------------

    def delete_vaultspec_dir(self) -> Self:
        """Delete ``.vaultspec/`` entirely."""
        d = self.root / DirName.VAULTSPEC
        if d.exists():
            shutil.rmtree(d)
        return self

    def vaultspec_as_file(self) -> Self:
        """Replace ``.vaultspec/`` with a plain file."""
        d = self.root / DirName.VAULTSPEC
        if d.exists():
            shutil.rmtree(d)
        d.write_text("not a directory", encoding="utf-8")
        return self

    def delete_builtins(self) -> Self:
        """Delete all ``*.builtin.md`` files from the rules source tree."""
        rules = self.root / DirName.VAULTSPEC / "rules" / "rules"
        if rules.exists():
            for f in rules.glob("*.builtin.md"):
                f.unlink()
        return self

    # ---- Presets (common combinations) -------------------------------------

    def preset_partially_managed(self, provider: str) -> Self:
        """Provider directory with a mix of vaultspec and user content."""
        return self.add_user_content(provider).add_stale_rule(provider)

    def preset_outdated_install(self) -> Self:
        """Workspace installed by an older vaultspec version."""
        return self.set_old_vaultspec_version("0.0.1").outdated_vaultspec_rules(
            "claude"
        )

    def preset_pre_existing_provider(self, provider: str) -> Self:
        """Provider directory that existed before vaultspec was installed."""
        return self.create_bare_provider_dir(provider).add_user_content(provider)
