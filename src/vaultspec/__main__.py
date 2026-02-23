"""Unified vaultspec CLI entry point — routes subcommands to namespace CLIs.

Routes the first positional argument to one of the registered namespace CLIs
(vault, team, subagent, mcp) or falls through to ``spec_cli`` for spec
resource commands.

Commands:
    vault:    Vault document management (audit, create, index, search).
    team:     Multi-agent team lifecycle (create, assign, dissolve).
    subagent: Sub-agent dispatch and serving (run, serve, a2a-serve).
    mcp:      MCP tool server.
    rules:    Manage rules (spec_cli passthrough).
    agents:   Manage agents (spec_cli passthrough).
    skills:   Manage skills (spec_cli passthrough).
    config:   Manage tool configs (spec_cli passthrough).
    system:   Manage system prompts (spec_cli passthrough).
    sync-all: Sync all resources (spec_cli passthrough).
    test:     Run tests (spec_cli passthrough).
    doctor:   Check prerequisites and system health (spec_cli passthrough).
    init:     Initialize vaultspec in a project (handled early, no workspace needed).
    readiness: Assess codebase governance readiness (spec_cli passthrough).
    hooks:    Manage event-driven hooks (spec_cli passthrough).
"""

import sys

NAMESPACES = {
    "vault": "Vault document management (audit, create, index, search)",
    "team": "Multi-agent team lifecycle (create, assign, dissolve)",
    "subagent": "Sub-agent dispatch and serving (run, serve, a2a-serve)",
    "mcp": "MCP tool server",
}

# Commands handled directly by spec_cli (shown in help alongside namespaces)
SPEC_COMMANDS = {
    "rules": "Manage rules",
    "agents": "Manage agents",
    "skills": "Manage skills",
    "config": "Manage tool configs (CLAUDE.md, GEMINI.md)",
    "system": "Manage system prompts",
    "sync-all": "Sync all resources",
    "test": "Run tests",
    "doctor": "Check prerequisites and system health",
    "init": "Initialize vaultspec in a project",
    "readiness": "Assess codebase governance readiness",
    "hooks": "Manage event-driven hooks",
}


def _print_help() -> None:
    """Print the top-level help message listing all commands and namespaces."""
    from .cli_common import get_version

    print(f"vaultspec {get_version()} — governed AI agent development\n")
    print("Usage: vaultspec <command> [options]\n")
    print("Commands:")
    for name, desc in SPEC_COMMANDS.items():
        print(f"  {name:12} {desc}")
    print()
    for name, desc in NAMESPACES.items():
        print(f"  {name:12} {desc}")
    print(f"\n  {'--version':12} Show version")
    print(f"  {'--help':12} Show this message")


def main() -> None:
    """Dispatch ``sys.argv`` to the appropriate namespace CLI or spec_cli.

    Checks the first argument against known namespaces and delegates to the
    matching CLI module's ``main()``.  Unknown arguments fall through to
    ``spec_cli.main()``.  Prints help when invoked with no arguments or
    ``--help``/``-h``.
    """
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _print_help()
        return

    if sys.argv[1] in ("-V", "--version"):
        from .cli_common import get_version

        print(f"vaultspec {get_version()}")
        return

    first_arg = sys.argv[1]

    # Handle `init` early — before importing spec_cli, which runs workspace
    # validation at import time and would exit with WorkspaceError in a fresh
    # project where .vaultspec/ doesn't exist yet.
    if first_arg == "init":
        import argparse as _argparse
        from pathlib import Path as _Path

        from .core import types as _t
        from .core.commands import init_run

        _t.ROOT_DIR = _Path.cwd()
        _args = _argparse.Namespace(force="--force" in sys.argv)
        init_run(_args)
        return

    if first_arg in NAMESPACES:
        sys.argv = [f"vaultspec {first_arg}", *sys.argv[2:]]

        if first_arg == "vault":
            from .vault_cli import main as run
        elif first_arg == "team":
            from .team_cli import main as run
        elif first_arg == "subagent":
            from .subagent_cli import main as run
        elif first_arg == "mcp":
            from .mcp_server.app import main as run
        else:
            print(f"Unknown namespace: {first_arg}")
            return

        try:
            run()
        except (ImportError, Exception) as exc:
            print(f"Error running 'vaultspec {first_arg}': {exc}", file=sys.stderr)
            sys.exit(1)
    else:
        # Everything else falls through to spec_cli (rules, agents, skills, etc.)
        from .spec_cli import main as run

        try:
            run()
        except (ImportError, Exception) as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
