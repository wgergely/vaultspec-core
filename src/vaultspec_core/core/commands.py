"""Implement the top-level operational commands mounted into the root CLI.

This module contains the business logic behind workspace initialization,
install, uninstall, and sync. It sits above the lower-level resource-management
modules and provides the user-facing command behaviors that do not belong
to a dedicated nested Typer namespace.
"""

from __future__ import annotations

import contextvars
import logging
import shutil
from dataclasses import replace
from pathlib import Path
from typing import Any

from . import types as _t
from .enums import ManagedState, PrecommitHook, ProviderCapability, Tool
from .exceptions import (
    ProviderError,
    ProviderNotInstalledError,
    VaultSpecError,
    WorkspaceNotInitializedError,
)
from .gitattributes import ensure_gitattributes_block
from .gitattributes import has_valid_block as _ga_has_valid_block
from .gitignore import (
    _collect_provider_artifacts,
    _find_markers,
    ensure_gitignore_block,
    get_recommended_entries,
)
from .helpers import _rmtree_robust, atomic_write, ensure_dir
from .manifest import (
    ManifestData,
    add_providers,
    providers_sharing_dir,
    providers_sharing_file,
    read_manifest,
    read_manifest_data,
    remove_provider,
    write_manifest_data,
)

logger = logging.getLogger(__name__)


def _get_package_version() -> str:
    """Return the installed vaultspec-core version string."""
    try:
        from importlib.metadata import version

        return version("vaultspec-core")
    except Exception:
        return "unknown"


# Valid provider arguments for install/uninstall commands.
VALID_PROVIDERS = {"all", "core", "claude", "gemini", "antigravity", "codex"}

# Map provider argument names to Tool enum members.
_PROVIDER_TO_TOOLS: dict[str, list[Tool]] = {
    "claude": [Tool.CLAUDE],
    "gemini": [Tool.GEMINI],
    "antigravity": [Tool.ANTIGRAVITY],
    "codex": [Tool.CODEX],
    "all": [Tool.CLAUDE, Tool.GEMINI, Tool.ANTIGRAVITY, Tool.CODEX],
    "core": [],
}


def _rel(target: Path, p: Path) -> str:
    return str(p.relative_to(target)).replace("\\", "/")


def _scaffold_core(target: Path, *, dry_run: bool = False) -> list[tuple[str, str]]:
    """Scaffold the ``.vaultspec/`` and ``.vault/`` directory structures.

    Args:
        target: Workspace root directory.
        dry_run: When ``True``, returns the manifest without creating anything.

    Returns:
        List of ``(relative_path, label)`` tuples for all directories created
        or that would be created.
    """
    fw_dir = target / ".vaultspec"
    vault_dir = target / ".vault"
    created: list[tuple[str, str]] = []

    # Ensure the framework root exists unconditionally before builtins
    # discovery.  In editable installs _builtins_root() resolves to
    # .vaultspec/rules/ which may not yet exist after a full uninstall.
    if not dry_run:
        ensure_dir(fw_dir / "rules")
    created.append((_rel(target, fw_dir / "rules"), "core (.vaultspec)"))

    # Dynamically discover resource categories from the builtins package
    # so that new categories (e.g. hooks) are scaffolded automatically.
    from vaultspec_core.builtins import _builtins_root

    builtins_root = _builtins_root()
    subdirs = sorted(
        f"rules/{d.name}"
        for d in builtins_root.iterdir()
        if d.is_dir() and d.name not in ("__pycache__",)
    )
    for subdir in subdirs:
        d = fw_dir / subdir
        if not dry_run:
            ensure_dir(d)
        created.append((_rel(target, d), "core (.vaultspec)"))

    for subdir in ["adr", "audit", "exec", "plan", "reference", "research"]:
        d = vault_dir / subdir
        if not dry_run:
            ensure_dir(d)
        created.append((_rel(target, d), "vault (.vault)"))

    return created


def _scaffold_provider(
    target: Path, tool: Tool, *, dry_run: bool = False
) -> list[tuple[str, str]]:
    """Scaffold directories for a single provider.

    Uses its :class:`~vaultspec_core.core.types.ToolConfig`.

    Args:
        target: Workspace root directory.
        tool: :class:`~vaultspec_core.core.enums.Tool` to scaffold.
        dry_run: When ``True``, returns the manifest without creating anything.

    Returns:
        Deduplicated list of ``(relative_path, label)`` tuples, one per
        directory or file created (or that would be created).
    """
    cfg = _t.get_context().tool_configs.get(tool)
    if cfg is None:
        return []

    created: list[tuple[str, str]] = []
    caps = cfg.capabilities
    label = tool.value
    seen_rels: set[str] = set()

    def _add(rel: str, sublabel: str) -> None:
        if rel not in seen_rels:
            seen_rels.add(rel)
            created.append((rel, f"{label} ({sublabel})"))

    if ProviderCapability.RULES in caps and cfg.rules_dir:
        if not dry_run:
            ensure_dir(cfg.rules_dir)
        _add(_rel(target, cfg.rules_dir), "rules")

    if ProviderCapability.SKILLS in caps and cfg.skills_dir:
        if not dry_run:
            ensure_dir(cfg.skills_dir)
        _add(_rel(target, cfg.skills_dir), "skills")

    if ProviderCapability.AGENTS in caps and cfg.agents_dir:
        if not dry_run:
            ensure_dir(cfg.agents_dir)
        _add(_rel(target, cfg.agents_dir), "agents")

    if ProviderCapability.WORKFLOWS in caps and cfg.workflows_dir:
        if not dry_run:
            ensure_dir(cfg.workflows_dir)
        _add(_rel(target, cfg.workflows_dir), "workflows")

    if cfg.config_file:
        if not dry_run and not cfg.config_file.exists():
            ensure_dir(cfg.config_file.parent)
            atomic_write(cfg.config_file, "")
        _add(_rel(target, cfg.config_file), "config")

    if cfg.rule_ref_config_file:
        _add(_rel(target, cfg.rule_ref_config_file), "config")

    if cfg.native_config_file:
        if not dry_run:
            ensure_dir(cfg.native_config_file.parent)
            if not cfg.native_config_file.exists():
                atomic_write(cfg.native_config_file, "")
        _add(_rel(target, cfg.native_config_file), "config")

    return created


def _scaffold_mcp_json(target: Path, *, dry_run: bool = False) -> list[tuple[str, str]]:
    """Scaffold or merge ``vaultspec-core`` into ``.mcp.json``.

    If ``.mcp.json`` already exists the function merges the ``vaultspec-core``
    server entry into the existing ``mcpServers`` dict, preserving user entries.
    When the entry already exists the file is left untouched.

    Args:
        target: Workspace root directory.
        dry_run: When ``True``, returns the manifest without writing anything.

    Returns:
        List with a single ``(".mcp.json", "mcp")`` tuple when a write
        occurred (or would occur), otherwise empty.
    """
    import json

    from .helpers import atomic_write

    mcp_json = target / ".mcp.json"
    server_entry = {
        "command": "uv",
        "args": ["run", "python", "-m", "vaultspec_core.mcp_server.app"],
    }

    if mcp_json.exists():
        try:
            raw = json.loads(mcp_json.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return []
        if not isinstance(raw, dict):
            return []
        servers = raw.setdefault("mcpServers", {})
        if not isinstance(servers, dict):
            return []
        if "vaultspec-core" in servers:
            return []
        servers["vaultspec-core"] = server_entry
        if not dry_run:
            atomic_write(mcp_json, json.dumps(raw, indent=2) + "\n")
        return [(".mcp.json", "mcp")]

    if not dry_run:
        mcp_config = {"mcpServers": {"vaultspec-core": server_entry}}
        atomic_write(mcp_json, json.dumps(mcp_config, indent=2) + "\n")
    return [(".mcp.json", "mcp")]


CANONICAL_ENTRY_PREFIX = "uv run --no-sync vaultspec-core"

# Patterns that must never be committed.  Used by the
# check-provider-artifacts pre-commit hook.
PROVIDER_ARTIFACT_PATTERNS: tuple[str, ...] = (
    ".mcp.json",
    "providers.lock",
    "CLAUDE.md",
    "GEMINI.md",
    "AGENTS.md",
    ".claude/",
    ".gemini/",
    ".codex/",
    ".agents/",
    ".vaultspec/_snapshots/",
)


def check_staged_provider_artifacts() -> list[str]:
    """Return staged file paths that match provider artifact patterns.

    Runs ``git diff --cached --name-only`` and filters against
    :data:`PROVIDER_ARTIFACT_PATTERNS`.
    """
    import subprocess

    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
            check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []

    staged = result.stdout.strip().splitlines()
    violations: list[str] = []
    for path in staged:
        normalized = path.replace("\\", "/")
        for pattern in PROVIDER_ARTIFACT_PATTERNS:
            if pattern.endswith("/"):
                if normalized.startswith(pattern) or f"/{pattern}" in normalized:
                    violations.append(path)
                    break
            elif normalized == pattern or normalized.endswith(f"/{pattern}"):
                violations.append(path)
                break
    return violations


# Hook definitions keyed by PrecommitHook enum.
# Each value is a dict of pre-commit hook fields (merged with defaults).
_HOOK_DEFS: dict[PrecommitHook, dict[str, object]] = {
    PrecommitHook.VAULT_FIX: {
        "name": "Vault fix",
        "entry": f"{CANONICAL_ENTRY_PREFIX} vault check all --fix",
        "types": ["markdown"],
    },
    PrecommitHook.CHECK_PROVIDER_ARTIFACTS: {
        "name": "Check provider artifacts",
        "entry": f"{CANONICAL_ENTRY_PREFIX} check-providers",
        "always_run": True,
    },
    PrecommitHook.SPEC_CHECK: {
        "name": "Spec check",
        "entry": f"{CANONICAL_ENTRY_PREFIX} doctor",
        "types": ["markdown"],
    },
}

CANONICAL_PRECOMMIT_HOOKS: list[dict[str, object]] = [
    {
        "id": hook.value,
        **meta,
        "language": "system",
        "pass_filenames": False,
    }
    for hook, meta in _HOOK_DEFS.items()
]

CANONICAL_HOOK_IDS: frozenset[str] = frozenset(h.value for h in PrecommitHook)

# Old hook IDs that should be replaced during scaffold/sync.
# Maps every previously-used ID to its canonical replacement.
_DEPRECATED_HOOK_IDS: dict[str, str] = {
    "vault-doctor": PrecommitHook.VAULT_FIX.value,
    "vault-doctor-deep": PrecommitHook.SPEC_CHECK.value,
    "check-naming": PrecommitHook.VAULT_FIX.value,
    "check-dangling": PrecommitHook.VAULT_FIX.value,
    "check-body-links": PrecommitHook.VAULT_FIX.value,
    "vault-check": PrecommitHook.VAULT_FIX.value,
}


def _scaffold_precommit(
    target: Path, *, dry_run: bool = False
) -> list[tuple[str, str]]:
    """Scaffold or merge vaultspec-core hooks into .pre-commit-config.yaml.

    Ensures the full canonical hook set is present with canonical entry
    patterns.  Existing hooks with matching IDs are updated to the
    canonical entry; missing hooks are appended.
    """
    import yaml

    from .helpers import atomic_write

    config_file = target / ".pre-commit-config.yaml"

    if config_file.exists():
        try:
            raw = config_file.read_text(encoding="utf-8")
            data = yaml.safe_load(raw) or {}
            if not isinstance(data, dict):
                return []
        except (yaml.YAMLError, OSError):
            return []

        repos = data.setdefault("repos", [])
        if not isinstance(repos, list):
            return []

        # Find or create local repo
        local_repos = [
            r for r in repos if isinstance(r, dict) and r.get("repo") == "local"
        ]
        if local_repos:
            local_repo = local_repos[0]
            existing_hooks = local_repo.setdefault("hooks", [])
            if not isinstance(existing_hooks, list):
                return []

            existing_by_id = {
                h.get("id"): h for h in existing_hooks if isinstance(h, dict)
            }

            # Migrate deprecated hook IDs to their canonical replacements
            changed = False
            for old_id, new_id in _DEPRECATED_HOOK_IDS.items():
                if old_id in existing_by_id and new_id not in existing_by_id:
                    existing_by_id[old_id]["id"] = new_id
                    existing_by_id[new_id] = existing_by_id.pop(old_id)
                    changed = True
                elif old_id in existing_by_id:
                    existing_hooks[:] = [
                        h
                        for h in existing_hooks
                        if not (isinstance(h, dict) and h.get("id") == old_id)
                    ]
                    del existing_by_id[old_id]
                    changed = True
            for canonical in CANONICAL_PRECOMMIT_HOOKS:
                hook_id = str(canonical["id"])
                if hook_id in existing_by_id:
                    existing = existing_by_id[hook_id]
                    if existing.get("entry") != canonical["entry"]:
                        existing["entry"] = canonical["entry"]
                        changed = True
                else:
                    existing_hooks.append(dict(canonical))
                    changed = True

            if not changed:
                return []
        else:
            repos.append(
                {
                    "repo": "local",
                    "hooks": [dict(h) for h in CANONICAL_PRECOMMIT_HOOKS],
                }
            )

        if not dry_run:
            atomic_write(
                config_file,
                yaml.dump(
                    data,
                    sort_keys=False,
                    default_flow_style=False,
                    allow_unicode=True,
                ),
            )
        return [(".pre-commit-config.yaml", "precommit")]

    if not dry_run:
        data = {
            "repos": [
                {
                    "repo": "local",
                    "hooks": [dict(h) for h in CANONICAL_PRECOMMIT_HOOKS],
                }
            ]
        }
        atomic_write(
            config_file,
            yaml.dump(
                data, sort_keys=False, default_flow_style=False, allow_unicode=True
            ),
        )
    return [(".pre-commit-config.yaml", "precommit")]


def _validate_provider(provider: str) -> None:
    """Validate that *provider* is a known provider name.

    Raises:
        ProviderError: If *provider* is not in :data:`VALID_PROVIDERS`.
    """
    if provider not in VALID_PROVIDERS:
        raise ProviderError(
            f"Unknown provider '{provider}'. "
            f"Valid: {', '.join(sorted(VALID_PROVIDERS))}"
        )


def _validate_skip(skip: set[str] | None) -> set[str]:
    """Validate and normalise a *skip* set.

    Raises:
        ProviderError: If any value in *skip* is not a valid component name.
    """
    if not skip:
        return set()
    # "all" is not a valid skip target  - you'd just not run the command.
    # "mcp" is a valid skip target but is not a provider.
    allowed = (VALID_PROVIDERS - {"all"}) | {"mcp", "precommit"}
    bad = skip - allowed
    if bad:
        raise ProviderError(
            f"Invalid --skip value(s): {', '.join(sorted(bad))}. "
            f"Valid: {', '.join(sorted(allowed))}"
        )
    return skip


def _filter_tools(tools: list[Tool], skip: set[str]) -> list[Tool]:
    """Remove tools whose provider name is in *skip*."""
    if not skip:
        return tools
    return [t for t in tools if t.value not in skip]


def init_run(
    force: bool = False, provider: str = "all", skip: set[str] | None = None
) -> list[tuple[str, str]]:
    """Scaffold the .vaultspec/ and .vault/ directory structure.

    Args:
        force: Override contents if already exists.
        provider: Provider to install.
        skip: Set of component names to skip (``core`` and/or provider names).

    Returns:
        A deduplicated list of ``(relative_path, label)`` tuples for all
        created directories and files.
    """
    from vaultspec_core.config import get_config, reset_config
    from vaultspec_core.config.workspace import resolve_workspace
    from vaultspec_core.core.types import init_paths

    from .exceptions import ResourceExistsError

    skip = skip or set()
    skip_core = "core" in skip

    cfg = get_config()
    target = _t.get_context().target_dir
    fw_dir = target / cfg.framework_dir

    created: list[tuple[str, str]] = []

    if not skip_core:
        if fw_dir.exists() and not force:
            raise ResourceExistsError(
                f"{fw_dir} already exists. Use --force to overwrite."
            )

        created = _scaffold_core(target)

        # Seed builtin content into .vaultspec/rules/
        from vaultspec_core.builtins import seed_builtins

        rules_dir = fw_dir / "rules"
        seeded = seed_builtins(rules_dir, force=force)
        for rel in seeded:
            created.append((f".vaultspec/rules/{rel}", "builtin"))

        # Snapshot builtins for revert support
        from .revert import snapshot_builtins

        snapshot_builtins(fw_dir)

    # Re-resolve workspace after scaffolding
    reset_config()
    layout = resolve_workspace(target_override=target)
    init_paths(layout)

    # Scaffold provider directories
    tools = _filter_tools(_PROVIDER_TO_TOOLS.get(provider, []), skip)
    for tool in tools:
        created.extend(_scaffold_provider(target, tool))

    if "mcp" not in skip:
        created.extend(_scaffold_mcp_json(target))
    if "precommit" not in skip:
        created.extend(_scaffold_precommit(target))

    # Write provider manifest
    provider_names = [t.value for t in tools]
    if provider_names:
        add_providers(target, provider_names)

    # Deduplicate by relative path, preserving order
    seen: dict[str, str] = {}
    for rel, label in created:
        seen.setdefault(rel, label)

    return list(seen.items())


def _ensure_tool_configs(path: Path) -> None:
    """Ensure TOOL_CONFIGS is populated, bootstrapping if needed.

    On a fresh project where ``.vaultspec/`` doesn't exist yet, uses a
    temporary directory as the workspace root so ``init_paths()`` can resolve
    the layout and populate TOOL_CONFIGS without touching the real filesystem.
    """
    import tempfile

    from vaultspec_core.config import reset_config
    from vaultspec_core.config.workspace import resolve_workspace
    from vaultspec_core.core.types import init_paths

    try:
        if _t.get_context().tool_configs:
            return
    except LookupError:
        pass

    fw_dir = path / ".vaultspec"
    if fw_dir.exists():
        reset_config()
        layout = resolve_workspace(target_override=path)
        init_paths(layout)
        return

    # Bootstrap in a temporary directory to avoid TOCTOU on the real path.
    # Resolve workspace against the temp dir, then re-initialize with the
    # real target so tool_config paths reference the actual workspace.
    tmp = Path(tempfile.mkdtemp())
    try:
        tmp_fw = tmp / ".vaultspec"
        tmp_fw.mkdir(parents=True, exist_ok=True)

        reset_config()
        layout = resolve_workspace(target_override=tmp)
        # Replace the temp target with the real path so tool_configs point correctly
        from vaultspec_core.config.workspace import WorkspaceLayout

        real_layout = WorkspaceLayout(
            target_dir=path,
            vault_dir=path / ".vault",
            vaultspec_dir=path / ".vaultspec",
            mode=layout.mode,
            git=layout.git,
        )
        init_paths(real_layout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def install_run(
    path: Path,
    provider: str = "all",
    upgrade: bool = False,
    dry_run: bool = False,
    force: bool = False,
    skip: set[str] | None = None,
) -> dict[str, Any]:
    """Deploy the vaultspec framework to a project directory.

    Args:
        path: Target directory.
        provider: Provider to install (``all``, ``core``, ``claude``, etc.).
        upgrade: Re-sync builtin rules without re-scaffolding.
        dry_run: Preview the manifest of files that would be created.
        force: Override contents if installation already exists.
        skip: Set of component names to skip (``core`` and/or provider names).

    Returns:
        A dict describing the result:
        - ``"action"``: ``"dry_run"``, ``"upgrade"``, or ``"install"``
        - ``"items"``: list of ``(path, label)`` tuples (for dry_run)
        - ``"seeded_count"``: number of re-seeded files (for upgrade)

    Raises:
        ProviderError: If *provider* is invalid.
        ResourceExistsError: If already installed and *force*/*upgrade* not set.
    """
    from vaultspec_core.config import reset_config
    from vaultspec_core.config.workspace import WorkspaceError, resolve_workspace
    from vaultspec_core.core.types import init_paths

    from .exceptions import ResourceExistsError
    from .guards import guard_dev_repo

    _validate_provider(provider)
    skip = _validate_skip(skip)

    guard_dev_repo(path)

    # Bootstrap a minimal context so downstream code can read target_dir
    _t.set_context(
        _t.WorkspaceContext(
            root_dir=path,
            target_dir=path,
            rules_src_dir=path,
            skills_src_dir=path,
            agents_src_dir=path,
            system_src_dir=path,
            templates_dir=path,
            hooks_dir=path,
        )
    )

    skip_core = "core" in skip

    if skip_core and not (path / ".vaultspec").exists():
        raise VaultSpecError(
            f"Cannot skip core: .vaultspec/ does not exist at {path}.",
            hint="Install core first, then use --skip core on subsequent installs.",
        )

    if upgrade and dry_run:
        _ensure_tool_configs(path)
        return {
            "action": "dry_run",
            "upgrade": True,
            "items": [],
        }

    if dry_run:
        _ensure_tool_configs(path)

        manifest: list[tuple[str, str]] = []

        if not skip_core:
            manifest = _scaffold_core(path, dry_run=True)

            # Include builtin files that would be seeded
            from vaultspec_core.builtins import list_builtins

            for builtin_rel in list_builtins():
                manifest.append((f".vaultspec/rules/{builtin_rel}", "builtin"))

        tools = _filter_tools(_PROVIDER_TO_TOOLS.get(provider, []), skip)
        for tool in tools:
            manifest.extend(_scaffold_provider(path, tool, dry_run=True))
        if "mcp" not in skip:
            manifest.extend(_scaffold_mcp_json(path, dry_run=True))
        if "precommit" not in skip:
            manifest.extend(_scaffold_precommit(path, dry_run=True))

        # Deduplicate preserving order (by relative path)
        seen: dict[str, str] = {}
        for rel, label in manifest:
            seen.setdefault(rel, label)

        return {"action": "dry_run", "items": list(seen.items()), "path": path}

    if upgrade:
        try:
            layout = resolve_workspace(target_override=path)
            init_paths(layout)
        except WorkspaceError as e:
            raise WorkspaceNotInitializedError(
                f"Cannot upgrade: {e}",
                hint=f"Run 'vaultspec-core install {path}' first.",
            ) from e

        seeded: list[str] = []
        if not skip_core:
            # Re-seed builtins (force=True overwrites existing)
            from vaultspec_core.builtins import seed_builtins

            fw_dir = path / ".vaultspec"
            seeded = seed_builtins(fw_dir / "rules", force=True)

            # Re-snapshot builtins for revert support
            from .revert import snapshot_builtins

            snapshot_builtins(fw_dir)

        sync_target = provider if provider not in ("all", "core") else "all"
        sync_provider(sync_target, force=True, skip=skip)

        # Re-scaffold MCP entry if missing (repair)
        if "mcp" not in skip:
            _scaffold_mcp_json(path)
        if "precommit" not in skip:
            _scaffold_precommit(path)

        # Update manifest timestamps and version
        import datetime

        mdata = read_manifest_data(path)
        if not mdata.installed_at:
            mdata.installed_at = datetime.datetime.now(tz=datetime.UTC).isoformat()
        mdata.vaultspec_version = _get_package_version()

        # Re-opt-in gitignore management on --upgrade --force
        if force:
            ensure_gitignore_block(
                path, get_recommended_entries(path), state=ManagedState.PRESENT
            )
            mdata.gitignore_managed = True

        write_manifest_data(path, mdata)

        return {"action": "upgrade", "seeded_count": len(seeded), "path": path}

    fw_dir = path / ".vaultspec"
    if fw_dir.exists() and not force and not skip_core:
        raise ResourceExistsError(
            f"vaultspec is already installed at {path}. "
            "Use --upgrade to update, --force to override, or remove it "
            f"first with 'vaultspec-core uninstall {path}'."
        )

    created = init_run(force=force, provider=provider, skip=skip)

    reset_config()
    layout = resolve_workspace(target_override=path)
    init_paths(layout)

    post_errors: list[str] = []

    sync_target = provider if provider not in ("all", "core") else "all"
    try:
        sync_provider(sync_target, skip=skip)
    except (VaultSpecError, OSError) as exc:
        logger.warning("Sync failed during install: %s", exc)
        post_errors.append(f"sync: {exc}")

    # Count actual source resources (what the user authored)
    from .agents import collect_agents
    from .rules import collect_rules
    from .skills import collect_skills

    source_counts = {
        "rules": len(collect_rules()),
        "skills": len(collect_skills()),
        "agents": len(collect_agents()),
    }

    tools = _filter_tools(_PROVIDER_TO_TOOLS.get(provider, []), skip)
    provider_names = [t.value for t in tools]
    has_mcp = (path / ".mcp.json").exists()

    # Manage gitignore block
    recommended = get_recommended_entries(path)

    gi_written = ensure_gitignore_block(path, recommended, state=ManagedState.PRESENT)
    if gi_written:
        logger.info("Added vaultspec managed block to .gitignore")

    # Manage gitattributes block
    ga_written = ensure_gitattributes_block(path, state=ManagedState.PRESENT)
    if ga_written:
        logger.info("Added vaultspec managed block to .gitattributes")

    # Populate v2.0 manifest fields
    import datetime

    gi_path = path / ".gitignore"
    ga_path = path / ".gitattributes"
    mdata = read_manifest_data(path, strict=True)

    # Robust detection: if it's there, it's managed.
    block_present = False
    if gi_path.exists():
        try:
            content = gi_path.read_text(encoding="utf-8")
            begins, ends = _find_markers(content.splitlines())
            block_present = len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0]

        except (OSError, UnicodeDecodeError):
            pass

    ga_block_present = False
    if ga_path.exists():
        try:
            content = ga_path.read_text(encoding="utf-8")
            ga_block_present = _ga_has_valid_block(content.splitlines())
        except (OSError, UnicodeDecodeError):
            pass

    mdata.gitignore_managed = block_present
    mdata.gitattributes_managed = ga_block_present
    mdata.vaultspec_version = _get_package_version()
    mdata.installed_at = datetime.datetime.now(tz=datetime.UTC).isoformat()
    for name in provider_names:
        mdata.provider_state.setdefault(name, {})
        mdata.provider_state[name]["installed_at"] = mdata.installed_at
    write_manifest_data(path, mdata)

    result: dict[str, Any] = {
        "action": "install",
        "items": created,
        "source_counts": source_counts,
        "providers": provider_names,
        "has_mcp": has_mcp,
        "path": path,
    }
    if post_errors:
        result["errors"] = post_errors
    return result


def uninstall_run(
    path: Path,
    provider: str = "all",
    keep_vault: bool = False,
    dry_run: bool = False,
    force: bool = False,
    skip: set[str] | None = None,
) -> dict[str, Any]:
    """Remove the vaultspec framework from a project directory.

    Args:
        path: Target directory.
        provider: Provider to uninstall (``all``, ``core``, ``<provider>``).
        keep_vault: Preserve ``.vault/`` documentation directory.
        dry_run: Preview what would be removed without deleting.
        force: Required to execute. Uninstall is destructive.
        skip: Set of component names to skip (``core`` and/or provider names).

    Returns:
        A dict describing the result:
        - ``"action"``: ``"dry_run"`` or ``"uninstall"``
        - ``"removed"``: list of ``(path, label)`` tuples

    Raises:
        ProviderError: If *provider* is invalid or *force* not set.
    """
    from .guards import guard_dev_repo

    guard_dev_repo(path)

    # Validate inputs before any state mutation
    _validate_provider(provider)
    skip = _validate_skip(skip)

    # Safety gate: require --force for destructive operations
    if not force and not dry_run:
        raise ProviderError(
            "Uninstall is destructive. Pass --force to confirm, "
            "or use --dry-run to preview."
        )

    # Bootstrap a minimal context so _ensure_tool_configs can proceed
    _t.set_context(
        _t.WorkspaceContext(
            root_dir=path,
            target_dir=path,
            rules_src_dir=path,
            skills_src_dir=path,
            agents_src_dir=path,
            system_src_dir=path,
            templates_dir=path,
            hooks_dir=path,
        )
    )
    _ensure_tool_configs(path)

    # Uninstalling "core" cascades to all providers
    effective_provider = "all" if provider == "core" else provider

    removed: list[tuple[str, str]] = []  # (path, label)

    # Map directory names → component owners (for skip filtering).
    # .agents/ is shared by antigravity, gemini, and codex (all place
    # skills there via init_paths), so it must be preserved when any of
    # its owners is skipped.
    _dir_owners: dict[str, list[str]] = {
        ".vaultspec": ["core"],
        ".vault": ["vault"],
        ".claude": ["claude"],
        ".gemini": ["gemini"],
        ".agents": ["antigravity", "gemini", "codex"],
        ".codex": ["codex"],
    }
    dir_labels: dict[str, str] = {
        ".vaultspec": "core",
        ".vault": "vault",
        ".claude": "claude",
        ".gemini": "gemini",
        ".agents": "antigravity",
        ".codex": "codex",
    }
    file_labels: dict[str, str] = {
        "CLAUDE.md": "claude (config)",
        "GEMINI.md": "gemini (config)",
        "AGENTS.md": "codex (config)",
        ".mcp.json": "mcp",
    }
    # Map file names → owning component for skip checks
    _file_owner: dict[str, str] = {
        "CLAUDE.md": "claude",
        "GEMINI.md": "gemini",
        "AGENTS.md": "codex",
    }

    errors: list[str] = []

    # Capture manifest state before potential destruction
    try:
        mdata_before = read_manifest_data(path)
    except Exception:
        # Fallback if manifest is already gone or corrupted
        mdata_before = ManifestData()

    if effective_provider == "all":
        import json

        from .helpers import atomic_write

        # Remove everything (respecting skip).
        # .vaultspec is deleted LAST so the manifest survives partial failures.
        managed_dirs = [
            path / ".claude",
            path / ".gemini",
            path / ".agents",
            path / ".codex",
        ]
        if not keep_vault:
            managed_dirs.append(path / ".vault")
        managed_dirs.append(path / ".vaultspec")

        managed_files = [
            path / "CLAUDE.md",
            path / "GEMINI.md",
            path / "AGENTS.md",
        ]

        for d in managed_dirs:
            owners = _dir_owners.get(d.name, [])
            if owners and any(o in skip for o in owners):
                skipped = [o for o in owners if o in skip]
                logger.info("Skipping %s (--skip %s)", d.name, ", ".join(skipped))
                continue
            owner = dir_labels.get(d.name, "")
            if d.exists():
                if not dry_run:
                    try:
                        _rmtree_robust(d)
                    except OSError as exc:
                        errors.append(f"Failed to remove {_rel(path, d)}: {exc}")
                        continue
                removed.append((str(d).replace("\\", "/") + "/", owner))

        for f in managed_files:
            owner = _file_owner.get(f.name, "")
            if owner in skip:
                logger.info("Skipping %s (--skip %s)", f.name, owner)
                continue
            if f.exists():
                if not dry_run:
                    try:
                        f.unlink()
                    except OSError as exc:
                        errors.append(f"Failed to remove {_rel(path, f)}: {exc}")
                        continue
                label = file_labels.get(f.name, "")
                removed.append((str(f).replace("\\", "/"), label))

        # Surgical .mcp.json cleanup: remove only the vaultspec-core key
        mcp_path = path / ".mcp.json"
        if "mcp" not in skip:
            if mcp_path.exists() and not dry_run:
                try:
                    raw = json.loads(mcp_path.read_text(encoding="utf-8"))
                    if isinstance(raw, dict):
                        servers = raw.get("mcpServers", {})
                        if isinstance(servers, dict) and "vaultspec-core" in servers:
                            del servers["vaultspec-core"]
                            if servers:
                                atomic_write(mcp_path, json.dumps(raw, indent=2) + "\n")
                            else:
                                mcp_path.unlink()
                            removed.append((_rel(path, mcp_path), "mcp"))
                except (json.JSONDecodeError, OSError):
                    pass
            elif mcp_path.exists() and dry_run:
                removed.append((_rel(path, mcp_path), "mcp"))

        # Surgical .pre-commit-config.yaml cleanup: remove vaultspec-core hooks
        precommit_path = path / ".pre-commit-config.yaml"
        if "precommit" not in skip:
            if precommit_path.exists() and not dry_run:
                try:
                    import yaml

                    raw = precommit_path.read_text(encoding="utf-8")
                    data = yaml.safe_load(raw)
                    if isinstance(data, dict):
                        repos = data.get("repos", [])
                        if isinstance(repos, list):
                            changed = False
                            new_repos = []
                            for r in repos:
                                if isinstance(r, dict) and r.get("repo") == "local":
                                    hooks = r.get("hooks", [])
                                    if isinstance(hooks, list):
                                        _all_managed = CANONICAL_HOOK_IDS | frozenset(
                                            _DEPRECATED_HOOK_IDS
                                        )
                                        new_hooks = [
                                            h
                                            for h in hooks
                                            if isinstance(h, dict)
                                            and h.get("id") not in _all_managed
                                        ]
                                        if len(new_hooks) != len(hooks):
                                            r["hooks"] = new_hooks
                                            changed = True
                                        if new_hooks:
                                            new_repos.append(r)
                                    else:
                                        new_repos.append(r)
                                else:
                                    new_repos.append(r)

                            if changed:
                                if new_repos:
                                    data["repos"] = new_repos
                                    atomic_write(
                                        precommit_path,
                                        yaml.dump(
                                            data,
                                            sort_keys=False,
                                            default_flow_style=False,
                                            allow_unicode=True,
                                        ),
                                    )
                                else:
                                    del data["repos"]
                                    if not data:
                                        precommit_path.unlink()
                                    else:
                                        atomic_write(
                                            precommit_path,
                                            yaml.dump(
                                                data,
                                                sort_keys=False,
                                                default_flow_style=False,
                                                allow_unicode=True,
                                            ),
                                        )
                                removed.append(
                                    (_rel(path, precommit_path), "precommit")
                                )
                except (yaml.YAMLError, OSError):
                    pass
            elif precommit_path.exists() and dry_run:
                try:
                    raw = precommit_path.read_text(encoding="utf-8")
                    _all_ids = CANONICAL_HOOK_IDS | frozenset(_DEPRECATED_HOOK_IDS)
                    if any(f"id: {hid}" in raw for hid in _all_ids):
                        removed.append((_rel(path, precommit_path), "precommit"))
                except OSError:
                    pass

    else:
        # Per-provider uninstall with shared directory protection
        tools = _filter_tools(_PROVIDER_TO_TOOLS.get(effective_provider, []), skip)
        for tool in tools:
            dirs, files = _collect_provider_artifacts(path, tool)

            for d in dirs:
                if not d.exists():
                    continue
                sharing = providers_sharing_dir(path, d, exclude=effective_provider)
                if sharing:
                    logger.info(
                        "Preserving %s (still used by: %s)",
                        d.relative_to(path),
                        ", ".join(sorted(sharing)),
                    )
                    continue

                if not dry_run:
                    try:
                        _rmtree_robust(d)
                    except OSError as exc:
                        errors.append(f"Failed to remove {_rel(path, d)}: {exc}")
                        continue
                removed.append((str(d).replace("\\", "/") + "/", tool.value))

            for f in files:
                if not f.exists():
                    continue
                sharing = providers_sharing_file(path, f, exclude=effective_provider)
                if sharing:
                    logger.info(
                        "Preserving %s (still used by: %s)",
                        f.relative_to(path),
                        ", ".join(sorted(sharing)),
                    )
                    continue
                if not dry_run:
                    try:
                        f.unlink()
                    except OSError as exc:
                        errors.append(f"Failed to remove {_rel(path, f)}: {exc}")
                        continue
                removed.append((str(f).replace("\\", "/"), f"{tool.value} (config)"))

        # Update manifest once after all tools are removed from disk
        if not dry_run:
            for tool in tools:
                remove_provider(path, tool.value)

    # Re-sync gitignore and gitattributes blocks
    if not dry_run:
        try:
            mdata_after = read_manifest_data(path)
        except Exception:
            mdata_after = ManifestData()

        recommended = get_recommended_entries(path)
        # If no providers remain and we are not keeping the vault, remove the block.
        # Otherwise, we sync it if it was managed before.
        if not mdata_after.installed and not keep_vault:
            ensure_gitignore_block(path, [], state=ManagedState.ABSENT)
            ensure_gitattributes_block(path, state=ManagedState.ABSENT)
        elif recommended and mdata_before.gitignore_managed:
            ensure_gitignore_block(path, recommended, state=ManagedState.PRESENT)

    action = "dry_run" if dry_run else "uninstall"
    result: dict[str, Any] = {
        "action": action,
        "removed": removed,
        "keep_vault": keep_vault,
        "path": path,
    }
    if errors:
        result["errors"] = errors
    return result


def hooks_list_data() -> dict[str, Any]:
    """Return structured data about all defined hooks.

    Returns:
        A dict with:
        - ``"hooks"``: list of dicts with ``"name"``, ``"enabled"``,
          ``"event"``, ``"actions"`` keys.
        - ``"supported_events"``: sorted list of supported event names.
        - ``"hooks_dir"``: relative path to hooks directory.
    """
    from vaultspec_core.hooks import SUPPORTED_EVENTS, load_hooks

    ctx = _t.get_context()
    hooks = load_hooks(ctx.hooks_dir)
    hooks_data = []
    for hook in hooks:
        actions = ", ".join(a.command for a in hook.actions if a.action_type == "shell")
        hooks_data.append(
            {
                "name": hook.name,
                "enabled": hook.enabled,
                "event": hook.event,
                "actions": actions,
            }
        )

    try:
        rel = str(ctx.hooks_dir.relative_to(ctx.target_dir))
    except ValueError:
        # HOOKS_DIR may live in the CWD workspace, not under TARGET_DIR,
        # when --target points to a separate directory.
        rel = str(ctx.hooks_dir)
    return {
        "hooks": hooks_data,
        "supported_events": sorted(SUPPORTED_EVENTS),
        "hooks_dir": rel,
    }


def hooks_run(event: str, path: str | None = None) -> list[dict[str, Any]]:
    """Trigger hooks for an event.

    Returns:
        A list of result dicts with ``"hook_name"``, ``"action_type"``,
        ``"success"``, ``"output"``, ``"error"`` keys.

    Raises:
        ProviderError: If the event is not in SUPPORTED_EVENTS.
    """
    from vaultspec_core.hooks import SUPPORTED_EVENTS, load_hooks, trigger

    if event not in SUPPORTED_EVENTS:
        raise ProviderError(
            f"Unknown event: {event}. Supported: {', '.join(sorted(SUPPORTED_EVENTS))}"
        )

    ws_ctx = _t.get_context()
    hooks = load_hooks(ws_ctx.hooks_dir)
    matching = [h for h in hooks if h.event == event and h.enabled]
    if not matching:
        logger.info("No enabled hooks for event: %s", event)
        return []

    ctx = {"root": str(ws_ctx.target_dir), "event": event}
    if path:
        ctx["path"] = path

    logger.info("Triggering %d hook(s) for '%s'...", len(matching), event)
    results = trigger(hooks, event, ctx)
    return [
        {
            "hook_name": r.hook_name,
            "action_type": r.action_type,
            "success": r.success,
            "output": r.output,
            "error": r.error,
        }
        for r in results
    ]


# Valid sync provider targets exposed to the CLI.
SYNC_PROVIDERS = {"all", "claude", "gemini", "antigravity", "codex"}


def sync_provider(
    provider: str,
    *,
    dry_run: bool = False,
    force: bool = False,
    skip: set[str] | None = None,
) -> list[_t.SyncResult]:
    """Sync resources for a single provider target.

    ``provider`` must be one of :data:`SYNC_PROVIDERS`.  The special value
    ``"all"`` syncs every provider and fires post-sync hooks.

    When *force* is ``True``, stale destination files are pruned and
    user-authored system/config files are overwritten.  When ``False``
    (the default), the sync is additive-only and any divergences are
    reported as warnings on the returned :class:`SyncResult` objects.

    Args:
        provider: Provider target to sync.
        dry_run: Preview changes without writing.
        force: Prune stale files and overwrite user-authored content.
        skip: Set of provider names to exclude from the sync.

    Returns:
        A list of :class:`SyncResult` objects from each sync pass.

    Raises:
        ProviderError: If *provider* is invalid.
        WorkspaceNotInitializedError: If ``.vaultspec/`` does not exist.
        ProviderNotInstalledError: If the specified provider is not installed.
    """
    if provider not in SYNC_PROVIDERS:
        raise ProviderError(
            f"Unknown sync target '{provider}'. "
            f"Valid: {', '.join(sorted(SYNC_PROVIDERS))}"
        )

    skip = _validate_skip(skip)

    from .agents import agents_sync
    from .config_gen import config_sync
    from .guards import guard_dev_repo
    from .rules import rules_sync
    from .skills import skills_sync
    from .system import system_sync

    ctx = _t.get_context()
    guard_dev_repo(ctx.target_dir)

    def _run_all_syncs() -> list[_t.SyncResult]:
        results: list[_t.SyncResult] = []
        for sync_fn, label in [
            (lambda: rules_sync(prune=force, dry_run=dry_run), "rules"),
            (lambda: skills_sync(prune=force, dry_run=dry_run), "skills"),
            (lambda: agents_sync(prune=force, dry_run=dry_run), "agents"),
            (lambda: system_sync(dry_run=dry_run, force=force), "system"),
            (lambda: config_sync(dry_run=dry_run, force=force), "config"),
        ]:
            try:
                results.append(sync_fn())
            except Exception as exc:
                logger.error("Sync pass '%s' failed: %s", label, exc)
                error_result = _t.SyncResult()
                error_result.errors.append(f"{label} sync failed: {exc}")
                results.append(error_result)
        return results

    # Guard: refuse to sync if vaultspec isn't installed at the target
    vaultspec_dir = ctx.target_dir / ".vaultspec"
    if not vaultspec_dir.exists():
        raise WorkspaceNotInitializedError(
            f"No .vaultspec/ found at {ctx.target_dir}.",
            hint=f"Run 'vaultspec-core install {ctx.target_dir}' first.",
        )

    if provider == "all":
        # When skipping providers, narrow tool_configs in a copied context
        skipped_tools = {Tool(name) for name in skip if name in {t.value for t in Tool}}

        def _sync_all_with_configs(
            narrowed_configs: dict[Tool, _t.ToolConfig] | None,
        ) -> list[_t.SyncResult]:
            if narrowed_configs is not None:
                _t.set_context(replace(ctx, tool_configs=narrowed_configs))
            logger.info("Syncing all resources...")
            results = _run_all_syncs()
            if not dry_run:
                from vaultspec_core.hooks import fire_hooks

                fire_hooks(
                    "config.synced",
                    {"root": str(ctx.target_dir), "event": "config.synced"},
                )
                logger.info("Done.")
            return results

        narrowed_configs: dict[Tool, _t.ToolConfig] | None = None
        if skipped_tools:
            narrowed_configs = {
                k: v for k, v in ctx.tool_configs.items() if k not in skipped_tools
            }

        copied = contextvars.copy_context()
        results = copied.run(_sync_all_with_configs, narrowed_configs)

        if not dry_run:
            import datetime

            from .gitignore import ensure_gitignore_block

            # Repair MCP entry if missing (unless mcp is skipped)
            if "mcp" not in skip:
                _scaffold_mcp_json(ctx.target_dir)
            if "precommit" not in skip:
                _scaffold_precommit(ctx.target_dir)

            # Respect gitignore opt-out: check whether the user removed
            # the managed block BEFORE re-creating it.  If the block is
            # gone but the manifest still says managed=True, the user
            # opted out -- honour that by flipping the flag.
            mdata = read_manifest_data(ctx.target_dir)
            if mdata.gitignore_managed:
                gi_path = ctx.target_dir / ".gitignore"
                if gi_path.exists():
                    try:
                        content = gi_path.read_text(encoding="utf-8")
                        begins, ends = _find_markers(content.splitlines())
                        block_present = (
                            len(begins) == 1 and len(ends) == 1 and begins[0] < ends[0]
                        )
                    except (OSError, UnicodeDecodeError):
                        block_present = False

                if block_present:
                    ensure_gitignore_block(
                        ctx.target_dir, get_recommended_entries(ctx.target_dir)
                    )
                else:
                    mdata.gitignore_managed = False
                    write_manifest_data(ctx.target_dir, mdata)

            # Respect gitattributes opt-out (same pattern as gitignore).
            mdata = read_manifest_data(ctx.target_dir)
            if mdata.gitattributes_managed:
                ga_path = ctx.target_dir / ".gitattributes"
                ga_block_present = False
                if ga_path.exists():
                    try:
                        content = ga_path.read_text(encoding="utf-8")
                        ga_block_present = _ga_has_valid_block(content.splitlines())
                    except (OSError, UnicodeDecodeError):
                        pass

                if ga_block_present:
                    ensure_gitattributes_block(ctx.target_dir)
                else:
                    mdata.gitattributes_managed = False
                    write_manifest_data(ctx.target_dir, mdata)

            # Update last_synced timestamps for installed providers only
            now = datetime.datetime.now(tz=datetime.UTC).isoformat()
            mdata = read_manifest_data(ctx.target_dir)
            for tool_type in ctx.tool_configs:
                name = tool_type.value
                if name not in mdata.installed:
                    continue
                mdata.provider_state.setdefault(name, {})
                mdata.provider_state[name]["last_synced"] = now
            mdata.vaultspec_version = _get_package_version()
            write_manifest_data(ctx.target_dir, mdata)

        return results

    # Validate provider is installed
    installed = read_manifest(ctx.target_dir)
    if installed and provider not in installed:
        raise ProviderNotInstalledError(
            f"Provider '{provider}' is not installed.",
            hint=(
                f"Run 'vaultspec-core install "
                f"--target {ctx.target_dir} {provider}' first."
            ),
        )

    # Per-provider sync: filter tool_configs to only the requested tool.
    requested: set[Tool] = set()
    if provider == "claude":
        requested = {Tool.CLAUDE}
    elif provider == "gemini":
        requested = {Tool.GEMINI}
    elif provider == "antigravity":
        requested = {Tool.ANTIGRAVITY}
    elif provider == "codex":
        requested = {Tool.CODEX}

    def _sync_single_provider(
        provider_configs: dict[Tool, _t.ToolConfig],
    ) -> list[_t.SyncResult]:
        _t.set_context(replace(ctx, tool_configs=provider_configs))
        logger.info("Syncing provider: %s ...", provider)
        results = _run_all_syncs()
        if not dry_run:
            logger.info("Done.")
        return results

    narrowed = {k: v for k, v in ctx.tool_configs.items() if k in requested}
    copied = contextvars.copy_context()
    results = copied.run(_sync_single_provider, narrowed)

    if not dry_run:
        import datetime

        now = datetime.datetime.now(tz=datetime.UTC).isoformat()
        mdata = read_manifest_data(ctx.target_dir)
        for tool_type in requested:
            name = tool_type.value
            if name not in mdata.installed:
                continue
            mdata.provider_state.setdefault(name, {})
            mdata.provider_state[name]["last_synced"] = now
        mdata.vaultspec_version = _get_package_version()
        write_manifest_data(ctx.target_dir, mdata)

    return results
