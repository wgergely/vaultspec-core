"""Unified vaultspec CLI — routes to namespace CLIs or falls through to spec
commands."""

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
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help"):
        _print_help()
        return

    if sys.argv[1] in ("-V", "--version"):
        from .cli_common import get_version

        print(f"vaultspec {get_version()}")
        return

    first_arg = sys.argv[1]

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

        run()
    else:
        # Everything else falls through to spec_cli (rules, agents, skills, etc.)
        from .spec_cli import main as run

        run()


if __name__ == "__main__":
    main()
