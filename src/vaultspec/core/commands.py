"""CLI command implementations for the vaultspec CLI.

These are the business-logic functions invoked by the CLI dispatcher.
They operate on core types and use vaultspec.core for all domain operations.
"""

from __future__ import annotations

import argparse
import logging
import subprocess
import sys

from . import types as _t
from .helpers import ensure_dir

logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"all", "unit", "api", "search", "index", "quality"}

MODULE_PATHS = {
    "cli": ["src/vaultspec/tests/cli"],
    "rag": ["src/vaultspec/rag/tests"],
    "vault": ["src/vaultspec/vaultcore/tests"],
    "protocol": [
        "src/vaultspec/protocol/tests",
        "src/vaultspec/protocol/a2a/tests",
        "src/vaultspec/protocol/acp/tests",
    ],
    "orchestration": ["src/vaultspec/orchestration/tests"],
    "subagent": ["src/vaultspec/subagent_server/tests"],
    "core": ["src/vaultspec/core/tests"],
    "mcp_tools": ["src/vaultspec/mcp_tools/tests"],
}


def test_run(args: argparse.Namespace) -> None:
    """Run the pytest test suite, optionally filtered by category and module.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``category`` (pytest
            marker filter, defaults to ``"all"``), ``module`` (restrict to a
            named module path group), and ``extra_args`` (list of additional
            pytest arguments).
    """
    category = getattr(args, "category", "all") or "all"
    module = getattr(args, "module", None)
    extra = getattr(args, "extra_args", []) or []

    cmd = [sys.executable, "-m", "pytest"]

    if category != "all":
        cmd.extend(["-m", category])

    if module:
        if module not in MODULE_PATHS:
            valid = ", ".join(sorted(MODULE_PATHS))
            logger.error("Error: Unknown module '%s'. Valid: %s", module, valid)
            return
        for p in MODULE_PATHS[module]:
            cmd.append(str(_t.ROOT_DIR / p))
    else:
        cmd.append(str(_t.ROOT_DIR / "src" / "vaultspec"))
        cmd.append(str(_t.ROOT_DIR / "tests"))

    cmd.extend(extra)

    logger.info("Running: %s", " ".join(cmd))
    result = subprocess.run(cmd, cwd=str(_t.ROOT_DIR))
    sys.exit(result.returncode)


def doctor_run(_args: argparse.Namespace) -> None:
    """Check prerequisites and system health.

    Args:
        _args: Parsed CLI arguments (unused).
    """
    import importlib

    issues = []

    # Python version
    ver = sys.version_info
    print(f"Python: {ver.major}.{ver.minor}.{ver.micro}", end="")
    if ver >= (3, 13):
        print(" [OK]")
    else:
        print(" [WARN] Python 3.13+ recommended")
        issues.append("Python 3.13+ recommended")

    # CUDA/GPU
    try:
        torch = importlib.import_module("torch")

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            mem = getattr(props, "total_memory", None) or getattr(props, "total_mem", 0)
            mem_gb = mem / (1024**3)
            print(f"CUDA: {torch.version.cuda} [OK]")
            print(f"GPU: {props.name} ({mem_gb:.1f} GB) [OK]")
        else:
            print("CUDA: Not available [FAIL]")
            issues.append("CUDA not available - GPU required")
    except ImportError:
        print("PyTorch: Not installed [FAIL]")
        issues.append("PyTorch not installed")

    # Optional deps
    for pkg, group in [
        ("lancedb", "rag"),
        ("sentence_transformers", "rag"),
        ("pytest", "dev"),
        ("ruff", "dev"),
    ]:
        try:
            importlib.import_module(pkg)
            print(f"{pkg}: installed [OK]")
        except ImportError:
            print(
                f"{pkg}: not installed [WARN]"
                f" (install with pip install -e '.[{group}]')"
            )
            issues.append(f"{pkg} not installed")

    # .lance directory
    lance_dir = _t.ROOT_DIR / ".vault" / ".lance"
    if lance_dir.exists():
        size = sum(f.stat().st_size for f in lance_dir.rglob("*") if f.is_file())
        size_mb = size / (1024 * 1024)
        print(f".lance index: {size_mb:.1f} MB [OK]")
    else:
        print(".lance index: not built [INFO] (run 'vault.py index' to build)")

    # Summary
    if issues:
        print(f"\n{len(issues)} issue(s) found:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\nAll checks passed.")


def init_run(args: argparse.Namespace) -> None:
    """Initialize vaultspec in a project.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``force`` (bool to
            allow reinitializing an existing ``.vaultspec/`` directory).
    """
    from vaultspec.config import get_config

    cfg = get_config()
    fw_dir = _t.ROOT_DIR / cfg.framework_dir
    vault_dir = _t.ROOT_DIR / ".vault"

    if fw_dir.exists() and not getattr(args, "force", False):
        logger.error("Error: %s already exists. Use --force to overwrite.", fw_dir)
        return

    # Create .vaultspec/ structure
    created = []
    for subdir in [
        "rules/rules",
        "rules/agents",
        "rules/skills",
        "rules/templates",
        "rules/system",
    ]:
        d = fw_dir / subdir
        ensure_dir(d)
        created.append(str(d.relative_to(_t.ROOT_DIR)))

    # Create .vault/ structure
    for subdir in ["adr", "audit", "exec", "plan", "reference", "research"]:
        d = vault_dir / subdir
        ensure_dir(d)
        created.append(str(d.relative_to(_t.ROOT_DIR)))

    # Create minimal stubs if they don't exist
    sys_dir = fw_dir / "rules" / "system"
    fw_md = sys_dir / "framework.md"
    if not fw_md.exists():
        fw_md.write_text(
            "# Framework Configuration\n\nAdd framework bootstrap content here.\n",
            encoding="utf-8",
        )
        created.append(str(fw_md.relative_to(_t.ROOT_DIR)))

    proj_md = sys_dir / "project.md"
    if not proj_md.exists():
        proj_md.write_text(
            "# Project Configuration\n\nAdd project-specific content here.\n",
            encoding="utf-8",
        )
        created.append(str(proj_md.relative_to(_t.ROOT_DIR)))

    print("Initialized vaultspec structure:")
    for path in created:
        print(f"  {path}")
    logger.info(
        "Created %d directories/files. Run 'cli.py sync-all' to sync.", len(created)
    )


def readiness_run(args: argparse.Namespace) -> None:
    """Assess codebase governance readiness across 6 dimensions.

    Scores documentation, framework structure, rules and governance, agent
    coverage, test infrastructure, and environment on a 1-5 scale each.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``json`` (bool to
            emit machine-readable JSON output instead of the table).

    Returns:
        None. Prints a formatted readiness table (or JSON) to stdout.
    """
    import json

    from vaultspec.config import get_config
    from vaultspec.vaultcore import parse_frontmatter

    cfg = get_config()
    fw_dir = _t.ROOT_DIR / cfg.framework_dir
    vault_dir = _t.ROOT_DIR / ".vault"

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
        has_agents = (fw_dir / "rules" / "agents").exists() and any(
            (fw_dir / "rules" / "agents").glob("*.md")
        )
        has_skills = (fw_dir / "rules" / "skills").exists() and any(
            (fw_dir / "rules" / "skills").glob("*.md")
        )
        has_rules = (fw_dir / "rules" / "rules").exists() and any(
            (fw_dir / "rules" / "rules").glob("*.md")
        )
        has_system = (fw_dir / "rules" / "system").exists()
        has_templates = (fw_dir / "rules" / "templates").exists()

        if any([has_agents, has_skills, has_rules]):
            fw_score = 3
            parts = []
            if has_agents:
                parts.append("agents")
            if has_skills:
                parts.append("skills")
            if has_rules:
                parts.append("rules")
            fw_detail = f"Has {', '.join(parts)}"
        else:
            fw_score = 2
            fw_detail = ".vaultspec/ exists but minimal content"

        if has_agents and has_skills and has_rules and has_system:
            fw_score = 4
            fw_detail = "Complete structure with system/"

        if fw_score == 4 and has_templates:
            custom_count = 0
            for d in [
                fw_dir / "rules" / "agents",
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
            if synced_count >= 3:
                rules_score = 5
                rules_detail += ", synced to all tools"

    # Dimension 4: Agent Coverage
    agent_score = 1
    agent_detail = "No agents"
    if (fw_dir / "rules" / "agents").exists():
        agents = list((fw_dir / "rules" / "agents").glob("*.md"))
        agent_count = len(agents)

        if agent_count == 0:
            agent_score = 1
            agent_detail = "No agents"
        elif agent_count <= 2:
            agent_score = 2
            agent_detail = f"{agent_count} agent(s)"
        elif agent_count <= 5:
            agent_score = 3
            agent_detail = f"{agent_count} agents covering basic roles"
        else:
            tier_count = 0
            for agent_file in agents:
                content = agent_file.read_text(encoding="utf-8")
                meta, _body = parse_frontmatter(content)
                if "tier" in meta:
                    tier_count += 1

            agent_score = 4
            agent_detail = f"{agent_count} agents with tier assignments"

            synced_count = 0
            for cfg_item in _t.TOOL_CONFIGS.values():
                if (
                    cfg_item.agents_dir
                    and cfg_item.agents_dir.exists()
                    and any(cfg_item.agents_dir.glob("*.md"))
                ):
                    synced_count += 1
            if synced_count >= 2 and tier_count == agent_count:
                agent_score = 5
                agent_detail = f"{agent_count} agents, all synced"

    # Dimension 5: Test Infrastructure
    test_score = 1
    test_detail = "No test files found"
    test_dirs = [
        _t.ROOT_DIR / ".vaultspec" / "lib" / "tests",
        _t.ROOT_DIR / ".vaultspec" / "lib" / "src",
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
            _t.ROOT_DIR / ".github" / "workflows",
            _t.ROOT_DIR / ".vaultspec" / "lib" / "tests" / "benchmarks",
        ]
        has_ci = any(d.exists() for d in ci_files)
        if has_ci:
            test_score = 5
            test_detail = f"{len(test_files)} tests + CI/benchmarks"

    # Dimension 6: Environment (GPU/deps)
    env_score = 1
    env_detail = "Missing Python or critical deps"

    try:
        env_score = 2
        py_ver = f"{sys.version_info.major}.{sys.version_info.minor}"
        env_detail = f"Python {py_ver}, no GPU detected"

        try:
            import importlib as _rl

            torch = _rl.import_module("torch")

            if torch.cuda.is_available():
                env_score = 3
                props = torch.cuda.get_device_properties(0)
                gpu_name = props.name
                env_detail = f"GPU: {gpu_name}"

                try:
                    _rl.import_module("lancedb")
                    _rl.import_module("sentence_transformers")

                    env_score = 4
                    env_detail = f"GPU + all deps, {gpu_name}"
                except ImportError:
                    env_detail = f"GPU: {gpu_name}, missing optional deps"

                lance_dir = _t.ROOT_DIR / ".vault" / ".lance"
                if lance_dir.exists():
                    env_score = 5
                    env_detail = f"Full env + .lance index, {gpu_name}"
        except ImportError:
            pass
    except Exception:
        env_score = 1
        env_detail = "Environment check failed"

    # Build results
    dimensions: dict[str, dict[str, int | str]] = {
        "documentation": {"score": doc_score, "max": 5, "detail": doc_detail},
        "framework": {"score": fw_score, "max": 5, "detail": fw_detail},
        "rules_governance": {
            "score": rules_score,
            "max": 5,
            "detail": rules_detail,
        },
        "agent_coverage": {
            "score": agent_score,
            "max": 5,
            "detail": agent_detail,
        },
        "test_infrastructure": {
            "score": test_score,
            "max": 5,
            "detail": test_detail,
        },
        "environment": {"score": env_score, "max": 5, "detail": env_detail},
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
        recommendations.append("Run 'cli.py sync-all' to sync rules to all tools")
    if agent_score < 4:
        recommendations.append("Add more agents with tier assignments")
    if agent_score == 4:
        recommendations.append("Run 'cli.py agents sync' to sync agents")
    if test_score < 5:
        recommendations.append("Add CI pipeline for automated testing")
    if env_score < 4:
        recommendations.append("Install optional dependencies (lancedb, etc.)")
    if env_score == 4:
        recommendations.append("Run 'vault.py index' to build .lance index")

    if getattr(args, "json", False):
        result = {
            "dimensions": dimensions,
            "overall": round(overall, 1),
            "total": total_score,
            "max_total": max_total,
            "recommendations": recommendations,
        }
        print(json.dumps(result, indent=2))
    else:
        print("vaultspec Readiness Assessment")
        print("=" * 62)
        print()

        def _bar(score: int, max_score: int = 5) -> str:
            """Render a simple ASCII progress bar for a score.

            Args:
                score: Current score value (number of filled positions).
                max_score: Maximum score value (total bar width).

            Returns:
                A string of ``#`` characters followed by ``-`` characters,
                e.g. ``"###--"`` for score=3, max_score=5.
            """
            filled = "#" * score
            empty = "-" * (max_score - score)
            return filled + empty

        labels = [
            ("Documentation", "documentation"),
            ("Framework", "framework"),
            ("Rules & Governance", "rules_governance"),
            ("Agent Coverage", "agent_coverage"),
            ("Test Infrastructure", "test_infrastructure"),
            ("Environment", "environment"),
        ]
        for label, key in labels:
            dim = dimensions[key]
            bar = _bar(int(dim["score"]), int(dim["max"]))
            score_str = f"{dim['score']}/{dim['max']}"
            detail = dim["detail"]
            print(f"{label:<22} {bar} {score_str:>3}  ({detail})")

        print()
        print(f"Overall: {overall:.1f}/5 ({total_score}/{max_total})")

        if recommendations:
            print()
            print("Recommendations:")
            for rec in recommendations:
                print(f"  - {rec}")


def hooks_list(_args: argparse.Namespace) -> None:
    """List all defined hooks.

    Args:
        _args: Parsed CLI arguments (unused).
    """
    from vaultspec.hooks import SUPPORTED_EVENTS, load_hooks

    hooks = load_hooks(_t.HOOKS_DIR)
    if not hooks:
        logger.info("No hooks defined.")
        logger.info("  Add .yaml files to %s/", _t.HOOKS_DIR.relative_to(_t.ROOT_DIR))
        logger.info("\nSupported events: %s", ", ".join(sorted(SUPPORTED_EVENTS)))
        return

    for hook in hooks:
        status = "enabled" if hook.enabled else "disabled"
        print(f"  {hook.name} [{status}]")
        print(f"    event: {hook.event}")
        for action in hook.actions:
            if action.action_type == "shell":
                print(f"    -> shell: {action.command}")
            elif action.action_type == "agent":
                print(f"    -> agent: {action.agent_name}")


def hooks_run(args: argparse.Namespace) -> None:
    """Manually trigger hooks for a given event.

    Args:
        args: Parsed CLI arguments. Expected attributes: ``event`` (the event
            name to trigger) and optionally ``path`` (context path value passed
            to hook actions).
    """
    from vaultspec.hooks import SUPPORTED_EVENTS, load_hooks, trigger

    event = args.event
    if event not in SUPPORTED_EVENTS:
        logger.error("Unknown event: %s", event)
        logger.error("Supported: %s", ", ".join(sorted(SUPPORTED_EVENTS)))
        return

    hooks = load_hooks(_t.HOOKS_DIR)
    matching = [h for h in hooks if h.event == event and h.enabled]
    if not matching:
        logger.info("No enabled hooks for event: %s", event)
        return

    ctx = {"root": str(_t.ROOT_DIR), "event": event}
    if hasattr(args, "path") and args.path:
        ctx["path"] = args.path

    logger.info("Triggering %d hook(s) for '%s'...", len(matching), event)
    results = trigger(hooks, event, ctx)
    for r in results:
        icon = "[OK]" if r.success else "[FAIL]"
        print(f"  {r.hook_name} ({r.action_type}): {icon}")
        if r.output:
            for line in r.output.splitlines()[:5]:
                print(f"    {line}")
        if r.error:
            print(f"    error: {r.error}")
