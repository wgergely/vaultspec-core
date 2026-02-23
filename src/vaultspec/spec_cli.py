"""Primary vaultspec CLI — resource management for rules, agents, skills, configs, and
system prompts.

Commands:
    rules:    List, add, show, edit, remove, rename, and sync rules.
    agents:   List, add, show, edit, remove, rename, sync, and set-tier agents.
    skills:   List, add, show, edit, remove, rename, and sync skills.
    config:   Show or sync tool configuration files (CLAUDE.md, GEMINI.md).
    system:   Show or sync system prompt fragments.
    sync-all: Sync rules, agents, skills, system prompts, and configs in one pass.
    test:     Run the vaultspec test suite (unit, api, search, index, quality).
    doctor:   Check prerequisites and overall system health.
    init:     Scaffold the .vaultspec/ directory structure in a project.
    readiness: Assess codebase governance readiness.
    hooks:    List or trigger event-driven hooks.
"""

from __future__ import annotations

import argparse
import logging
import sys

from .cli_common import (
    add_common_args,
    get_default_layout,
    resolve_args_workspace,
    setup_logging,
)
from .config import WorkspaceError as _WorkspaceError
from .core import (
    agents_add,
    agents_list,
    agents_set_tier,
    agents_sync,
    config_show,
    config_sync,
    init_paths,
    resource_edit,
    resource_remove,
    resource_rename,
    resource_show,
    rules_add,
    rules_list,
    rules_sync,
    skills_add,
    skills_list,
    skills_sync,
    system_show,
    system_sync,
)
from .core import types as _t
from .core.commands import (
    doctor_run,
    hooks_list,
    hooks_run,
    init_run,
    readiness_run,
    test_run,
)

logger = logging.getLogger(__name__)

try:
    _default_layout = get_default_layout()
    init_paths(_default_layout)
except _WorkspaceError as _e:
    logger.error("%s", _e)
    sys.exit(1)


def add_sync_flags(parser: argparse.ArgumentParser) -> None:
    """Add ``--prune`` and ``--dry-run`` flags to a sync subparser.

    Args:
        parser: The argument parser to add the flags to.
    """
    parser.add_argument("--prune", action="store_true", help="Remove unknown files")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes")


def _make_parser() -> argparse.ArgumentParser:
    """Build and return the spec CLI argument parser."""
    parser = argparse.ArgumentParser(
        description="Manage rules, agents, and skills across tool destinations.",
        prog="vaultspec",
    )
    add_common_args(parser)
    resource_parsers = parser.add_subparsers(dest="resource", help="Type")

    # --- rules ---
    rules_parser = resource_parsers.add_parser("rules", help="Manage rules")
    rules_sub = rules_parser.add_subparsers(dest="command")

    rules_sub.add_parser("list", help="List all rules")

    rules_add_parser = rules_sub.add_parser("add", help="Add a custom rule")
    rules_add_parser.add_argument("--name", required=True, help="Rule name")
    rules_add_parser.add_argument("--content", help="Rule content")
    rules_add_parser.add_argument("--force", action="store_true", help="Overwrite")

    rules_show_parser = rules_sub.add_parser("show", help="Show a rule")
    rules_show_parser.add_argument("name", help="Rule name")

    rules_edit_parser = rules_sub.add_parser("edit", help="Edit a rule")
    rules_edit_parser.add_argument("name", help="Rule name")

    rules_remove_parser = rules_sub.add_parser("remove", help="Remove a rule")
    rules_remove_parser.add_argument("name", help="Rule name")
    rules_remove_parser.add_argument(
        "--force", action="store_true", help="Skip confirmation"
    )

    rules_rename_parser = rules_sub.add_parser("rename", help="Rename a rule")
    rules_rename_parser.add_argument("old_name", help="Current name")
    rules_rename_parser.add_argument("new_name", help="New name")

    rules_sync_parser = rules_sub.add_parser("sync", help="Sync rules")
    add_sync_flags(rules_sync_parser)

    # --- agents ---
    agents_parser = resource_parsers.add_parser("agents", help="Manage agents")
    agents_sub = agents_parser.add_subparsers(dest="command")

    agents_sub.add_parser("list", help="List all agents")

    agents_add_parser = agents_sub.add_parser("add", help="Add a new agent")
    agents_add_parser.add_argument("--name", required=True, help="Agent name")
    agents_add_parser.add_argument(
        "--description", default="", help="Agent description"
    )
    agents_add_parser.add_argument(
        "--tier",
        default="MEDIUM",
        choices=["LOW", "MEDIUM", "HIGH"],
        help="Capability tier",
    )
    agents_add_parser.add_argument("--force", action="store_true", help="Overwrite")
    agents_add_parser.add_argument(
        "--template",
        help="Template name from .vaultspec/rules/templates/ to pre-populate",
    )

    agents_show_parser = agents_sub.add_parser("show", help="Show an agent")
    agents_show_parser.add_argument("name", help="Agent name")

    agents_edit_parser = agents_sub.add_parser("edit", help="Edit an agent")
    agents_edit_parser.add_argument("name", help="Agent name")

    agents_remove_parser = agents_sub.add_parser("remove", help="Remove an agent")
    agents_remove_parser.add_argument("name", help="Agent name")
    agents_remove_parser.add_argument(
        "--force", action="store_true", help="Skip confirmation"
    )

    agents_rename_parser = agents_sub.add_parser("rename", help="Rename an agent")
    agents_rename_parser.add_argument("old_name", help="Current name")
    agents_rename_parser.add_argument("new_name", help="New name")

    agents_sync_parser = agents_sub.add_parser("sync", help="Sync agents")
    add_sync_flags(agents_sync_parser)

    agents_tier_parser = agents_sub.add_parser("set-tier", help="Update agent tier")
    agents_tier_parser.add_argument("name", help="Agent name")
    agents_tier_parser.add_argument(
        "--tier", required=True, choices=["LOW", "MEDIUM", "HIGH"], help="Tier"
    )

    # --- skills ---
    skills_parser = resource_parsers.add_parser("skills", help="Manage skills")
    skills_sub = skills_parser.add_subparsers(dest="command")

    skills_sub.add_parser("list", help="List all managed skills")

    skills_add_parser = skills_sub.add_parser("add", help="Add a new skill")
    skills_add_parser.add_argument("--name", required=True, help="Skill name")
    skills_add_parser.add_argument(
        "--description", default="", help="Skill description"
    )
    skills_add_parser.add_argument("--force", action="store_true", help="Overwrite")
    skills_add_parser.add_argument(
        "--template",
        help="Template name from .vaultspec/rules/templates/ to pre-populate",
    )

    skills_show_parser = skills_sub.add_parser("show", help="Show a skill")
    skills_show_parser.add_argument("name", help="Skill name")

    skills_edit_parser = skills_sub.add_parser("edit", help="Edit a skill")
    skills_edit_parser.add_argument("name", help="Skill name")

    skills_remove_parser = skills_sub.add_parser("remove", help="Remove a skill")
    skills_remove_parser.add_argument("name", help="Skill name")
    skills_remove_parser.add_argument(
        "--force", action="store_true", help="Skip confirmation"
    )

    skills_rename_parser = skills_sub.add_parser("rename", help="Rename a skill")
    skills_rename_parser.add_argument("old_name", help="Current name")
    skills_rename_parser.add_argument("new_name", help="New name")

    skills_sync_parser = skills_sub.add_parser("sync", help="Sync skills")
    add_sync_flags(skills_sync_parser)

    # --- config ---
    config_parser = resource_parsers.add_parser(
        "config", help="Manage tool configs (CLAUDE.md, GEMINI.md)"
    )
    config_sub = config_parser.add_subparsers(dest="command")

    config_sub.add_parser("show", help="Display internal/custom content")

    config_sync_parser = config_sub.add_parser("sync", help="Sync configs")
    add_sync_flags(config_sync_parser)
    config_sync_parser.add_argument(
        "--force", action="store_true", help="Overwrite custom content"
    )

    # --- system ---
    system_parser = resource_parsers.add_parser("system", help="Manage system prompts")
    system_sub = system_parser.add_subparsers(dest="command")

    system_sub.add_parser("show", help="Display system parts and targets")

    system_sync_parser = system_sub.add_parser("sync", help="Sync system prompts")
    add_sync_flags(system_sync_parser)
    system_sync_parser.add_argument(
        "--force", action="store_true", help="Overwrite custom content"
    )

    # --- sync-all ---
    sync_all_parser = resource_parsers.add_parser("sync-all", help="Sync all")
    add_sync_flags(sync_all_parser)
    sync_all_parser.add_argument("--force", action="store_true", help="Force overwrite")

    # --- test ---
    test_parser = resource_parsers.add_parser("test", help="Run tests")
    test_parser.add_argument(
        "category",
        nargs="?",
        default="all",
        choices=["all", "unit", "api", "search", "index", "quality"],
        help="Test category (default: all)",
    )
    test_parser.add_argument(
        "--module",
        "-m",
        choices=[
            "cli",
            "rag",
            "vault",
            "protocol",
            "orchestration",
            "subagent",
            "core",
            "mcp_tools",
        ],
        help="Filter by module",
    )
    test_parser.add_argument("extra_args", nargs="*", help="Extra pytest arguments")

    # --- doctor ---
    resource_parsers.add_parser("doctor", help="Check prerequisites and system health")

    # --- init ---
    init_parser = resource_parsers.add_parser(
        "init", help="Initialize vaultspec in a project"
    )
    init_parser.add_argument(
        "--force", action="store_true", help="Overwrite existing structure"
    )

    # --- readiness ---
    readiness_parser = resource_parsers.add_parser(
        "readiness", help="Assess codebase governance readiness"
    )
    readiness_parser.add_argument("--json", action="store_true", help="Output as JSON")

    # --- hooks ---
    hooks_parser = resource_parsers.add_parser(
        "hooks", help="Manage event-driven hooks"
    )
    hooks_sub = hooks_parser.add_subparsers(dest="command")
    hooks_sub.add_parser("list", help="List all hooks")
    hooks_run_parser = hooks_sub.add_parser("run", help="Trigger hooks for an event")
    hooks_run_parser.add_argument("event", help="Event name")
    hooks_run_parser.add_argument("--path", help="Context path variable")

    return parser


def main() -> None:
    """Parse CLI arguments and dispatch to the appropriate resource command handler."""
    parser = _make_parser()

    args = parser.parse_args()

    setup_logging(args)

    if args.root is not None or getattr(args, "content_dir", None) is not None:
        layout = resolve_args_workspace(args, _default_layout)
        init_paths(layout)

    if args.resource == "rules":
        if args.command == "list":
            rules_list(args)
        elif args.command == "add":
            rules_add(args)
        elif args.command == "show":
            resource_show(args, _t.RULES_SRC_DIR, "Rule")
        elif args.command == "edit":
            resource_edit(args, _t.RULES_SRC_DIR, "Rule")
        elif args.command == "remove":
            resource_remove(args, _t.RULES_SRC_DIR, "Rule")
        elif args.command == "rename":
            resource_rename(args, _t.RULES_SRC_DIR, "Rule")
        elif args.command == "sync":
            rules_sync(args)
        else:
            parser.print_help()
    elif args.resource == "agents":
        if args.command == "list":
            agents_list(args)
        elif args.command == "add":
            agents_add(args)
        elif args.command == "show":
            resource_show(args, _t.AGENTS_SRC_DIR, "Agent")
        elif args.command == "edit":
            resource_edit(args, _t.AGENTS_SRC_DIR, "Agent")
        elif args.command == "remove":
            resource_remove(args, _t.AGENTS_SRC_DIR, "Agent")
        elif args.command == "rename":
            resource_rename(args, _t.AGENTS_SRC_DIR, "Agent")
        elif args.command == "sync":
            agents_sync(args)
        elif args.command == "set-tier":
            agents_set_tier(args)
        else:
            parser.print_help()
    elif args.resource == "skills":
        if args.command == "list":
            skills_list(args)
        elif args.command == "add":
            skills_add(args)
        elif args.command == "show":
            resource_show(args, _t.SKILLS_SRC_DIR, "Skill")
        elif args.command == "edit":
            resource_edit(args, _t.SKILLS_SRC_DIR, "Skill")
        elif args.command == "remove":
            resource_remove(args, _t.SKILLS_SRC_DIR, "Skill")
        elif args.command == "rename":
            resource_rename(args, _t.SKILLS_SRC_DIR, "Skill")
        elif args.command == "sync":
            skills_sync(args)
        else:
            parser.print_help()
    elif args.resource == "config":
        if args.command == "show":
            config_show(args)
        elif args.command == "sync":
            config_sync(args)
        else:
            parser.print_help()
    elif args.resource == "system":
        if args.command == "show":
            system_show(args)
        elif args.command == "sync":
            system_sync(args)
        else:
            parser.print_help()
    elif args.resource == "test":
        test_run(args)
    elif args.resource == "sync-all":
        logger.info("Syncing all resources...")
        rules_sync(args)
        agents_sync(args)
        skills_sync(args)
        system_sync(args)
        config_sync(args)

        from .hooks import fire_hooks

        fire_hooks(
            "config.synced",
            {"root": str(_t.ROOT_DIR), "event": "config.synced"},
        )
        logger.info("Done.")
    elif args.resource == "doctor":
        doctor_run(args)
    elif args.resource == "init":
        init_run(args)
    elif args.resource == "readiness":
        readiness_run(args)
    elif args.resource == "hooks":
        if args.command == "list":
            hooks_list(args)
        elif args.command == "run":
            hooks_run(args)
        else:
            parser.print_help()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
