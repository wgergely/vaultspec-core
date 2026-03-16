"""Implement the top-level operational commands mounted into the root CLI.

This module contains the business logic behind workspace initialization,
readiness and health checks, and test execution. It sits above the lower-level
resource-management modules and provides the user-facing command behaviors that
do not belong to a dedicated nested Typer namespace.
"""

from __future__ import annotations

import logging
import subprocess
import sys
from pathlib import Path

import typer

from . import types as _t
from .enums import ProviderCapability, Tool
from .helpers import ensure_dir

logger = logging.getLogger(__name__)

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

VALID_CATEGORIES = {"all", "unit", "api", "quality"}

# Paths relative to the vaultspec-core package dir (dev src-layout + installed)
MODULE_PATHS = {
    "cli": ["tests/cli"],
    "vault": ["vaultcore/tests"],
    "protocol": [
        "protocol/tests",
    ],
    "core": ["core/tests"],
}


def _get_package_dir() -> Path:
    """Return the vaultspec-core package directory, whether src-layout or installed."""
    src_dir = _t.TARGET_DIR / "src" / "vaultspec_core"
    if src_dir.is_dir():
        return src_dir
    import vaultspec_core

    return Path(vaultspec_core.__file__).parent


def test_run(
    category: str = "all",
    module: str | None = None,
    extra_args: list[str] | None = None,
) -> None:
    """Run the pytest test suite, optionally filtered by category and module."""
    category = category or "all"
    extra = extra_args or []

    cmd = ["uv", "run", "pytest"]

    if category != "all":
        cmd.extend(["-m", category])

    pkg_dir = _get_package_dir()

    if module:
        if module not in MODULE_PATHS:
            valid = ", ".join(sorted(MODULE_PATHS))
            logger.error("Error: Unknown module '%s'. Valid: %s", module, valid)
            raise typer.Exit(code=1)
        for p in MODULE_PATHS[module]:
            cmd.append(str(pkg_dir / p))
    else:
        cmd.append(str(pkg_dir))
        tests_dir = _t.TARGET_DIR / "tests"
        if tests_dir.is_dir():
            cmd.append(str(tests_dir))

    cmd.extend(extra)

    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(_t.TARGET_DIR))

    # Explicitly cast to int to satisfy ty type checker
    raw_code = getattr(result, "exit_code", None)
    if raw_code is None:
        raw_code = result.returncode

    exit_code: int = int(raw_code)
    raise typer.Exit(code=exit_code)


def doctor_run() -> None:
    """Check prerequisites and overall system health."""
    import importlib

    from vaultspec_core.console import get_console

    console = get_console()
    issues = []

    console.print(f"Workspace Root: {_t.TARGET_DIR}")

    # Python version
    ver = sys.version_info
    ver_str = f"{ver.major}.{ver.minor}.{ver.micro}"
    if ver >= (3, 13):
        console.print(f"Python: {ver_str}  [bold green]✓ OK[/bold green]")
    else:
        console.print(
            f"Python: {ver_str}  [bold yellow]⚠ WARN[/bold yellow] 3.13+ recommended"
        )
        logger.warning("Python 3.13+ recommended")
        issues.append("Python 3.13+ recommended")

    # Optional deps
    for pkg, group in [
        ("pytest", "dev"),
        ("ruff", "dev"),
    ]:
        try:
            importlib.import_module(pkg)
            console.print(f"{pkg}: installed  [bold green]✓ OK[/bold green]")
        except ImportError:
            console.print(
                f"{pkg}: not installed  [bold yellow]⚠ WARN[/bold yellow]"
                f" (uv sync --extra {group})"
            )
            logger.warning("%s not installed", pkg)
            issues.append(f"{pkg} not installed")

    # Summary
    if issues:
        console.print(f"\n[bold]{len(issues)} issue(s) found:[/bold]")
        for issue in issues:
            console.print(f"  [dim]-[/dim] {issue}")
    else:
        console.print("\n[bold green]All checks passed.[/bold green]")


def _scaffold_core(target: Path) -> list[str]:
    """Scaffold the .vaultspec/ and .vault/ directory structures.

    Returns a list of relative paths that were created.
    """
    from vaultspec_core.config import get_config

    cfg = get_config()
    fw_dir = target / cfg.framework_dir
    vault_dir = target / ".vault"
    created: list[str] = []

    for subdir in [
        "rules/rules",
        "rules/skills",
        "rules/agents",
        "rules/templates",
        "rules/system",
    ]:
        d = fw_dir / subdir
        ensure_dir(d)
        created.append(str(d.relative_to(target)))

    for subdir in ["adr", "audit", "exec", "plan", "reference", "research"]:
        d = vault_dir / subdir
        ensure_dir(d)
        created.append(str(d.relative_to(target)))

    sys_dir = fw_dir / "rules" / "system"
    fw_md = sys_dir / "framework.md"
    if not fw_md.exists():
        fw_md.write_text(
            "# Framework Configuration\n\nAdd framework bootstrap content here.\n",
            encoding="utf-8",
        )
        created.append(str(fw_md.relative_to(target)))

    proj_md = sys_dir / "project.md"
    if not proj_md.exists():
        proj_md.write_text(
            "# Project Configuration\n\nAdd project-specific content here.\n",
            encoding="utf-8",
        )
        created.append(str(proj_md.relative_to(target)))

    return created


def _scaffold_provider(target: Path, tool: Tool) -> list[str]:
    """Scaffold directories for a single provider based on its ToolConfig.

    Returns a list of relative paths that were created.
    """
    cfg = _t.TOOL_CONFIGS.get(tool)
    if cfg is None:
        return []

    created: list[str] = []
    caps = cfg.capabilities

    if ProviderCapability.RULES in caps and cfg.rules_dir:
        ensure_dir(cfg.rules_dir)
        created.append(str(cfg.rules_dir.relative_to(target)))

    if ProviderCapability.SKILLS in caps and cfg.skills_dir:
        ensure_dir(cfg.skills_dir)
        rel = str(cfg.skills_dir.relative_to(target))
        if rel not in created:
            created.append(rel)

    if ProviderCapability.AGENTS in caps and cfg.agents_dir:
        ensure_dir(cfg.agents_dir)
        created.append(str(cfg.agents_dir.relative_to(target)))

    if ProviderCapability.WORKFLOWS in caps:
        wf_dir = target / ".agents" / "workflows"
        ensure_dir(wf_dir)
        rel = str(wf_dir.relative_to(target))
        if rel not in created:
            created.append(rel)

    if cfg.native_config_file:
        ensure_dir(cfg.native_config_file.parent)
        if not cfg.native_config_file.exists():
            cfg.native_config_file.write_text("", encoding="utf-8")
            created.append(str(cfg.native_config_file.relative_to(target)))

    return created


def _scaffold_mcp_json(target: Path) -> list[str]:
    """Scaffold .mcp.json for MCP server integration."""
    import json

    mcp_json = target / ".mcp.json"
    if mcp_json.exists():
        return []

    mcp_config = {
        "mcpServers": {
            "vaultspec-core": {
                "command": "vaultspec-mcp",
                "args": [],
                "env": {"VAULTSPEC_TARGET_DIR": str(target.resolve())},
            }
        }
    }
    mcp_json.write_text(json.dumps(mcp_config, indent=2) + "\n", encoding="utf-8")
    return [".mcp.json"]


def init_run(force: bool = False, provider: str = "all") -> None:
    """Scaffold the .vaultspec/ and .vault/ directory structure."""
    from vaultspec_core.config import get_config, reset_config
    from vaultspec_core.config.workspace import resolve_workspace
    from vaultspec_core.core.types import init_paths

    cfg = get_config()
    fw_dir = _t.TARGET_DIR / cfg.framework_dir

    if fw_dir.exists() and not force:
        logger.error("Error: %s already exists. Use --force to overwrite.", fw_dir)
        raise typer.Exit(code=1)

    created = _scaffold_core(_t.TARGET_DIR)

    # Re-resolve workspace after writing framework.md stubs
    reset_config()
    layout = resolve_workspace(target_override=_t.TARGET_DIR)
    init_paths(layout)

    # Scaffold provider directories
    tools = _PROVIDER_TO_TOOLS.get(provider, [])
    for tool in tools:
        created.extend(_scaffold_provider(_t.TARGET_DIR, tool))

    created.extend(_scaffold_mcp_json(_t.TARGET_DIR))

    # Write provider manifest
    from .manifest import add_providers

    provider_names = [t.value for t in tools]
    if provider_names:
        add_providers(_t.TARGET_DIR, provider_names)

    from vaultspec_core.console import get_console

    console = get_console()
    console.print("[bold]Initialized vaultspec-core structure:[/bold]")
    for path in dict.fromkeys(created):
        console.print(f"  {path}")
    console.print(
        f"Created [bold]{len(created)}[/bold] directories/files. "
        "Run [bold]vaultspec-core sync[/bold] to sync."
    )


def install_run(
    path: Path,
    provider: str = "all",
    upgrade: bool = False,
    dry_run: bool = False,
) -> None:
    """Deploy the vaultspec framework to a project directory.

    Args:
        path: Target directory.
        provider: Provider to install (``all``, ``core``, ``claude``, etc.).
        upgrade: Re-sync builtin rules without re-scaffolding.
        dry_run: Preview the manifest of files that would be created.
    """
    from vaultspec_core.config import reset_config
    from vaultspec_core.config.workspace import WorkspaceError, resolve_workspace
    from vaultspec_core.console import get_console
    from vaultspec_core.core.types import init_paths

    if provider not in VALID_PROVIDERS:
        logger.error(
            "Unknown provider '%s'. Valid: %s",
            provider,
            ", ".join(sorted(VALID_PROVIDERS)),
        )
        raise typer.Exit(code=1)

    console = get_console()
    _t.TARGET_DIR = path

    if dry_run:
        # Dry-run: compute and display the manifest without writing
        try:
            reset_config()
            layout = resolve_workspace(target_override=path)
            init_paths(layout)
        except Exception:
            # For dry-run on a fresh project, init_paths may fail;
            # fall back to basic path computation.
            pass

        console.print("[bold]Would create:[/bold]")
        manifest = _scaffold_core(path) if not (path / ".vaultspec").exists() else []
        tools = _PROVIDER_TO_TOOLS.get(provider, [])
        for tool in tools:
            cfg = _t.TOOL_CONFIGS.get(tool)
            if cfg is None:
                continue
            caps = cfg.capabilities
            for d in (cfg.rules_dir, cfg.skills_dir, cfg.agents_dir):
                if d is not None:
                    manifest.append(str(d.relative_to(path)))
            if ProviderCapability.WORKFLOWS in caps:
                manifest.append(".agents/workflows")
            if cfg.config_file:
                manifest.append(str(cfg.config_file.relative_to(path)))
            if cfg.native_config_file:
                manifest.append(str(cfg.native_config_file.relative_to(path)))
            if cfg.rule_ref_config_file:
                manifest.append(str(cfg.rule_ref_config_file.relative_to(path)))

        for item in dict.fromkeys(manifest):
            console.print(f"  {item}")
        console.print(f"\n[bold]Dry run:[/bold] {len(dict.fromkeys(manifest))} items")
        return

    if upgrade:
        try:
            layout = resolve_workspace(target_override=path)
            init_paths(layout)
        except WorkspaceError as e:
            logger.error("Cannot upgrade: %s", e)
            logger.error("Run 'vaultspec-core install %s' first.", path)
            raise typer.Exit(code=1) from e

        console.print(f"[bold]Upgrading vaultspec framework at {path}[/bold]")

        from vaultspec_core.spec_cli import _sync_provider

        sync_target = provider if provider not in ("all", "core") else "all"
        _sync_provider(sync_target, force=True)
        console.print("[bold green]Upgrade complete.[/bold green]")
    else:
        fw_dir = path / ".vaultspec"
        if fw_dir.exists():
            logger.error(
                "vaultspec is already installed at %s. "
                "Use --upgrade to update, or remove it first with "
                "'vaultspec-core uninstall %s'.",
                path,
                path,
            )
            raise typer.Exit(code=1)

        console.print(f"[bold]Installing vaultspec framework to {path}[/bold]")
        init_run(force=False, provider=provider)

        reset_config()
        layout = resolve_workspace(target_override=path)
        init_paths(layout)

        from vaultspec_core.spec_cli import _sync_provider

        sync_target = provider if provider not in ("all", "core") else "all"
        _sync_provider(sync_target)
        console.print("[bold green]Installation complete.[/bold green]")


def _collect_provider_artifacts(
    path: Path, tool: Tool
) -> tuple[list[Path], list[Path]]:
    """Return (directories, files) managed by a single provider."""
    from .enums import DirName, FileName

    cfg = _t.TOOL_CONFIGS.get(tool)
    dirs: list[Path] = []
    files: list[Path] = []

    if tool == Tool.CLAUDE:
        dirs.append(path / DirName.CLAUDE.value)
        files.append(path / FileName.CLAUDE.value)
    elif tool == Tool.GEMINI:
        dirs.append(path / DirName.GEMINI.value)
        # Root GEMINI.md is shared with Antigravity — handled below
    elif tool == Tool.ANTIGRAVITY:
        dirs.append(path / DirName.ANTIGRAVITY.value)
        files.append(path / FileName.GEMINI.value)
    elif tool == Tool.CODEX:
        dirs.append(path / DirName.CODEX.value)
        files.append(path / FileName.AGENTS.value)

    if cfg and cfg.native_config_file and cfg.native_config_file.parent not in dirs:
        dirs.append(cfg.native_config_file.parent)

    return dirs, files


def uninstall_run(
    path: Path,
    provider: str = "all",
    keep_vault: bool = False,
    dry_run: bool = False,
) -> None:
    """Remove the vaultspec framework from a project directory.

    Args:
        path: Target directory.
        provider: Provider to uninstall (``all``, ``core``, ``<provider>``).
        keep_vault: Preserve ``.vault/`` documentation directory.
        dry_run: Preview what would be removed without deleting.
    """
    import shutil

    from vaultspec_core.console import get_console

    from .manifest import providers_sharing_dir, remove_provider

    if provider not in VALID_PROVIDERS:
        logger.error(
            "Unknown provider '%s'. Valid: %s",
            provider,
            ", ".join(sorted(VALID_PROVIDERS)),
        )
        raise typer.Exit(code=1)

    console = get_console()
    removed: list[str] = []

    if provider == "all":
        # Remove everything
        managed_dirs = [
            path / ".vaultspec",
            path / ".claude",
            path / ".gemini",
            path / ".agents",
            path / ".codex",
        ]
        if not keep_vault:
            managed_dirs.append(path / ".vault")

        managed_files = [
            path / "CLAUDE.md",
            path / "GEMINI.md",
            path / "AGENTS.md",
            path / ".mcp.json",
        ]

        for d in managed_dirs:
            if d.exists():
                rel = str(d.relative_to(path))
                if dry_run:
                    console.print(f"  [dim]would remove[/dim] {rel}/")
                else:
                    shutil.rmtree(d)
                removed.append(f"{rel}/")

        for f in managed_files:
            if f.exists():
                rel = str(f.relative_to(path))
                if dry_run:
                    console.print(f"  [dim]would remove[/dim] {rel}")
                else:
                    f.unlink()
                removed.append(rel)

    elif provider == "core":
        d = path / ".vaultspec"
        if d.exists():
            rel = str(d.relative_to(path))
            if dry_run:
                console.print(f"  [dim]would remove[/dim] {rel}/")
            else:
                shutil.rmtree(d)
            removed.append(f"{rel}/")

    else:
        # Per-provider uninstall with shared directory protection
        tools = _PROVIDER_TO_TOOLS.get(provider, [])
        for tool in tools:
            dirs, files = _collect_provider_artifacts(path, tool)

            for d in dirs:
                if not d.exists():
                    continue
                # Check if another installed provider still needs this dir
                sharing = providers_sharing_dir(path, d, exclude=provider)
                if sharing:
                    logger.info(
                        "Preserving %s (still used by: %s)",
                        d.relative_to(path),
                        ", ".join(sorted(sharing)),
                    )
                    continue

                rel = str(d.relative_to(path))
                if dry_run:
                    console.print(f"  [dim]would remove[/dim] {rel}/")
                else:
                    shutil.rmtree(d)
                removed.append(f"{rel}/")

            for f in files:
                if not f.exists():
                    continue
                rel = str(f.relative_to(path))
                if dry_run:
                    console.print(f"  [dim]would remove[/dim] {rel}")
                else:
                    f.unlink()
                removed.append(rel)

        # Update manifest
        if not dry_run:
            for tool in tools:
                remove_provider(path, tool.value)

    if dry_run:
        console.print(f"\n[bold]Dry run:[/bold] would remove {len(removed)} items")
    elif removed:
        console.print("[bold]Removed vaultspec framework:[/bold]")
        for item in removed:
            console.print(f"  {item}")
        console.print(f"Removed [bold]{len(removed)}[/bold] items.")
        if keep_vault:
            console.print(
                "[dim].vault/ preserved (use without --keep-vault to remove)[/dim]"
            )
    else:
        console.print("Nothing to remove — vaultspec is not installed at this path.")


def readiness_run(json_output: bool = False) -> None:
    """Assess codebase governance readiness.

    Scores documentation, framework structure, rules and governance,
    and test infrastructure on a 1-5 scale each.
    """

    from vaultspec_core.config import get_config

    cfg = get_config()
    fw_dir = _t.TARGET_DIR / cfg.framework_dir
    vault_dir = _t.TARGET_DIR / ".vault"

    # Dimension 1: Documentation (.vault/ health)
    doc_score = 1
    doc_detail = "No .vault/ directory"
    if vault_dir.exists():
        doc_types = ["adr", "plan", "research", "reference", "exec"]
        all_docs = list(vault_dir.rglob("*.md"))
        doc_count = len(all_docs)
        present_types = {
            dt
            for dt in doc_types
            if (vault_dir / dt).exists() and any((vault_dir / dt).glob("*.md"))
        }

        if doc_count < 5:
            doc_score = 2
            doc_detail = f"{doc_count} docs, needs more coverage"
        elif doc_count < 20:
            doc_score = 3
            missing = set(doc_types) - present_types
            if missing:
                doc_detail = f"{doc_count} docs, missing: {', '.join(missing)}"
            else:
                doc_detail = f"{doc_count} docs, all types present"
        elif doc_count < 50:
            doc_score = 4
            doc_detail = f"{doc_count} docs, all types present"
        else:
            doc_score = 5
            doc_detail = f"{doc_count} docs, comprehensive coverage"

    # Dimension 2: Framework (.vaultspec/ structure)
    fw_score = 1
    fw_detail = "No .vaultspec/ directory"
    if fw_dir.exists():
        has_skills = (fw_dir / "rules" / "skills").exists() and any(
            (fw_dir / "rules" / "skills").glob("*.md")
        )
        has_rules = (fw_dir / "rules" / "rules").exists() and any(
            (fw_dir / "rules" / "rules").glob("*.md")
        )
        has_system = (fw_dir / "rules" / "system").exists()
        has_templates = (fw_dir / "rules" / "templates").exists()

        if any([has_skills, has_rules]):
            fw_score = 3
            parts = []
            if has_skills:
                parts.append("skills")
            if has_rules:
                parts.append("rules")
            fw_detail = f"Has {', '.join(parts)}"
        else:
            fw_score = 2
            fw_detail = ".vaultspec/ exists but minimal content"

        if has_skills and has_rules and has_system:
            fw_score = 4
            fw_detail = "Complete structure with system/"

        if fw_score == 4 and has_templates:
            custom_count = 0
            for d in [
                fw_dir / "rules" / "skills",
                fw_dir / "rules" / "rules",
            ]:
                if d.exists():
                    custom_count += len(
                        [
                            f
                            for f in d.glob("*.md")
                            if not f.name.endswith(".builtin.md")
                        ]
                    )
            if custom_count > 0:
                fw_score = 5
                fw_detail = f"Complete + {custom_count} custom resources"

    # Dimension 3: Rules & Governance
    rules_score = 1
    rules_detail = "No rules defined"
    if (fw_dir / "rules" / "rules").exists():
        all_rules = list((fw_dir / "rules" / "rules").glob("*.md"))
        builtin = [r for r in all_rules if r.name.endswith(".builtin.md")]
        custom = [r for r in all_rules if not r.name.endswith(".builtin.md")]
        total_rules = len(all_rules)

        if total_rules == 0:
            rules_score = 1
            rules_detail = "No rules defined"
        elif total_rules <= 2:
            rules_score = 2
            rules_detail = f"{total_rules} rule(s)"
        elif len(custom) == 0:
            rules_score = 3
            rules_detail = f"{total_rules} builtin rules"
        elif len(custom) > 0:
            rules_score = 4
            rules_detail = f"{len(builtin)} builtin + {len(custom)} custom"

        if rules_score >= 4:
            synced_count = 0
            for cfg_item in _t.TOOL_CONFIGS.values():
                if (
                    cfg_item.rules_dir
                    and cfg_item.rules_dir.exists()
                    and any(cfg_item.rules_dir.glob("*.md"))
                ):
                    synced_count += 1
            if synced_count >= 2:
                rules_score = 5
                rules_detail += ", synced to all tools"

    # Dimension 4: Test Infrastructure
    test_score = 1
    test_detail = "No test files found"
    test_dirs = [
        _t.TARGET_DIR / "tests",
        _t.TARGET_DIR / "src",
    ]
    test_files = []
    for test_dir in test_dirs:
        if test_dir.exists():
            test_files.extend(list(test_dir.rglob("test_*.py")))

    if test_files:
        test_score = 2
        test_detail = f"{len(test_files)} test files"

        has_markers = False
        for tf in test_files[:10]:
            content = tf.read_text(encoding="utf-8")
            if "@pytest.mark." in content:
                has_markers = True
                break

        if has_markers:
            test_score = 3
            test_detail = f"{len(test_files)} tests with pytest markers"

        conftest_files = []
        for test_dir in test_dirs:
            if test_dir.exists():
                conftest_files.extend(list(test_dir.rglob("conftest.py")))
        if conftest_files:
            test_score = 4
            test_detail = f"{len(test_files)} tests, {len(conftest_files)} fixtures"

        ci_files = [
            _t.TARGET_DIR / ".github" / "workflows",
        ]
        has_ci = any(d.exists() for d in ci_files)
        if has_ci:
            test_score = 5
            test_detail = f"{len(test_files)} tests + CI"

    # Build results
    dimensions: dict[str, dict[str, int | str]] = {
        "documentation": {"score": doc_score, "max": 5, "detail": doc_detail},
        "framework": {"score": fw_score, "max": 5, "detail": fw_detail},
        "rules_governance": {
            "score": rules_score,
            "max": 5,
            "detail": rules_detail,
        },
        "test_infrastructure": {
            "score": test_score,
            "max": 5,
            "detail": test_detail,
        },
    }

    total_score = sum(int(d["score"]) for d in dimensions.values())
    max_total = sum(int(d["max"]) for d in dimensions.values())
    overall = total_score / max_total * 5 if max_total > 0 else 0

    recommendations = []
    if doc_score < 4:
        recommendations.append(
            "Add more documentation across ADRs, plans, research, references"
        )
    if fw_score < 4:
        recommendations.append("Complete .vaultspec/ structure with rules/system/")
    if rules_score < 4:
        recommendations.append("Create custom rules for project conventions")
    if rules_score == 4:
        recommendations.append("Run 'vaultspec-core sync' to sync rules to all tools")
    if test_score < 5:
        recommendations.append("Add CI pipeline for automated testing")

    if json_output:
        import json

        result = {
            "dimensions": dimensions,
            "overall": round(overall, 1),
            "total": total_score,
            "max_total": max_total,
            "recommendations": recommendations,
        }
        typer.echo(json.dumps(result))
    else:
        from rich.rule import Rule
        from rich.table import Table

        from vaultspec_core.console import get_console

        console = get_console()

        def _bar(score: int, max_score: int = 5) -> str:
            return (
                "[green]"
                + "█" * score
                + "[/green]"
                + "[dim]"
                + "░" * (max_score - score)
                + "[/dim]"
            )

        console.print("[bold]vaultspec-core Readiness Assessment[/bold]")
        console.print(Rule())
        console.print()

        dim_table = Table(box=None, show_header=False, show_edge=False, padding=(0, 1))
        dim_table.add_column("Label", width=22)
        dim_table.add_column("Bar")
        dim_table.add_column("Score", justify="right", width=5)
        dim_table.add_column("Detail", style="dim")

        labels = [
            ("Documentation", "documentation"),
            ("Framework", "framework"),
            ("Rules & Governance", "rules_governance"),
            ("Test Infrastructure", "test_infrastructure"),
        ]
        for label, key in labels:
            dim = dimensions[key]
            bar = _bar(int(dim["score"]), int(dim["max"]))
            score_str = f"{dim['score']}/{dim['max']}"
            dim_table.add_row(label, bar, score_str, str(dim["detail"]))

        console.print(dim_table)
        console.print()
        console.print(
            f"[bold]Overall:[/bold] {overall:.1f}/5 ({total_score}/{max_total})"
        )

        if recommendations:
            console.print()
            console.print("[bold]Recommendations:[/bold]")
            for rec in recommendations:
                console.print(f"  [dim]-[/dim] {rec}")


def hooks_list() -> None:
    """List all defined hooks."""
    from rich import box
    from rich.table import Table

    from vaultspec_core.console import get_console
    from vaultspec_core.hooks import SUPPORTED_EVENTS, load_hooks

    console = get_console()
    hooks = load_hooks(_t.HOOKS_DIR)
    if not hooks:
        rel = _t.HOOKS_DIR.relative_to(_t.TARGET_DIR)
        console.print("No hooks defined.")
        console.print(f"  Add [dim].yaml[/dim] files to [bold]{rel}/[/bold]")
        console.print(
            "\n[dim]Supported events:[/dim] " + ", ".join(sorted(SUPPORTED_EVENTS))
        )
        return

    table = Table(box=box.SIMPLE_HEAD, highlight=False, show_edge=False)
    table.add_column("Name", no_wrap=True)
    table.add_column("Status")
    table.add_column("Event")
    table.add_column("Actions")

    for hook in hooks:
        if hook.enabled:
            status = "[bold green]enabled[/bold green]"
        else:
            status = "[dim]disabled[/dim]"
        actions = ", ".join(a.command for a in hook.actions if a.action_type == "shell")
        table.add_row(hook.name, status, hook.event, actions)

    console.print(table)


def hooks_run(event: str, path: str | None = None) -> None:
    """Trigger hooks for an event."""
    from vaultspec_core.hooks import SUPPORTED_EVENTS, load_hooks, trigger

    if event not in SUPPORTED_EVENTS:
        logger.error("Unknown event: %s", event)
        logger.error("Supported: %s", ", ".join(sorted(SUPPORTED_EVENTS)))
        raise typer.Exit(code=1)

    hooks = load_hooks(_t.HOOKS_DIR)
    matching = [h for h in hooks if h.event == event and h.enabled]
    if not matching:
        logger.info("No enabled hooks for event: %s", event)
        return

    ctx = {"root": str(_t.TARGET_DIR), "event": event}
    if path:
        ctx["path"] = path

    from vaultspec_core.console import get_console

    console = get_console()
    logger.info("Triggering %d hook(s) for '%s'...", len(matching), event)
    results = trigger(hooks, event, ctx)
    for r in results:
        if r.success:
            icon = "[bold green]OK[/bold green]"
        else:
            icon = "[bold red]FAIL[/bold red]"
        console.print(f"  {r.hook_name} ({r.action_type}): {icon}")
        if r.output:
            for line in r.output.splitlines()[:5]:
                console.print(f"    {line}")
        if r.error:
            console.print(f"    [red]error:[/red] {r.error}")
