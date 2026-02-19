"""Sub-agent CLI Interface.

The authoritative entry point for all sub-agent operations:
- run: Execute a sub-agent (ACP client mode)
- serve: Run the subagent MCP server
- list: List available agents
"""

import argparse
import asyncio
import pathlib
import sys
import warnings
from pathlib import Path

from _paths import ROOT_DIR  # shared path bootstrap
from _paths import _layout as _paths_layout
from core.workspace import resolve_workspace


def _get_version() -> str:
    """Read version from pyproject.toml."""
    toml_path = ROOT_DIR / "pyproject.toml"
    if toml_path.exists():
        for line in toml_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "unknown"


from logging_config import configure_logging  # noqa: E402

try:
    from subagent_server.server import main as server_main

    from orchestration.subagent import run_subagent
    from protocol.acp.client import SubagentClient
    from protocol.providers.base import ClaudeModels, GeminiModels
except ImportError as e:
    print(f"Failed to import subagent library: {e}", file=sys.stderr)
    sys.exit(1)


def list_available_agents(content_root: Path):
    """List all agents found in the workspace.

    Parameters
    ----------
    content_root:
        The content root directory (e.g. ``.vaultspec/``).  In split-root
        mode this differs from the output root; agents always live under
        the content tree.
    """
    agents_dir = content_root / "rules" / "agents"
    if not agents_dir.exists():
        print("No agents found.", file=sys.stderr)
        return

    print(f"Agents in {agents_dir}:")
    for agent_file in sorted(agents_dir.glob("*.md")):
        print(f"  {agent_file.stem}")


def command_run(args):
    """Handle 'run' subcommand."""
    if not args.agent:
        print("Error: --agent is required for 'run'", file=sys.stderr)
        sys.exit(1)

    # Resolve Context Files
    context_files = []
    if args.context:
        for ctx_path in args.context:
            p = pathlib.Path(ctx_path)
            if not p.exists():
                print(f"Warning: Context file not found: {p}", file=sys.stderr)
            else:
                context_files.append(p)

    # Resolve Plan File
    plan_file = None
    if args.plan:
        p = pathlib.Path(args.plan)
        if not p.exists():
            print(f"Error: Plan file not found: {p}", file=sys.stderr)
            sys.exit(1)
        plan_file = p

    # Determine Task/Goal
    task_goal = args.goal or args.task or ""
    if not task_goal and not plan_file:
        print("Error: You must provide a --goal, --task, or a --plan.", file=sys.stderr)
        sys.exit(1)

    # Legacy Task File Support
    if args.task_file:
        p = pathlib.Path(args.task_file)
        if p.exists():
            content = p.read_text(encoding="utf-8")
            task_goal = f"{task_goal}\n\n{content}".strip()
            # Simple regex to find agent in file if not provided
            import re

            match = re.search(r"Agent:\s*([a-zA-Z0-9_-]+)", content)
            if match and not args.agent:
                args.agent = match.group(1)
        else:
            print(f"Task file not found: {args.task_file}", file=sys.stderr)
            sys.exit(1)

    # Permission prompt for read-only
    if args.mode == "read-only":
        from orchestration.constants import READONLY_PERMISSION_PROMPT

        task_goal = READONLY_PERMISSION_PROMPT + task_goal

    warnings.simplefilter("ignore", ResourceWarning)

    project_root = args.root

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            run_subagent(
                agent_name=args.agent,
                initial_task=task_goal,
                context_files=context_files,
                plan_file=plan_file,
                root_dir=project_root,
                model_override=args.model,
                provider_override=args.provider,
                interactive=args.interactive,
                debug=args.debug,
                mode=args.mode,
                quiet=False,  # CLI should be noisy
                client_class=SubagentClient,
            )
        )
        if result.response_text:
            print("\n--- Response ---\n")
            print(result.response_text)

    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc()
    finally:
        loop.close()


def command_serve(args):
    """Handle 'serve' subcommand."""
    server_main(root_dir=args.root, content_root=args.content_root)


def command_a2a_serve(args):
    """Handle 'a2a-serve' subcommand — start an A2A HTTP server."""
    import uvicorn

    from protocol.a2a.agent_card import agent_card_from_definition
    from protocol.a2a.server import create_app

    root = args.root
    content_root = args.content_root
    agent_name = args.agent or "vaultspec-researcher"
    port = args.port or 10010

    # Load agent metadata (minimal — just name + description)
    agents_dir = content_root / "rules" / "agents"
    agent_file = agents_dir / f"{agent_name}.md"
    agent_meta = {"name": agent_name, "description": f"Vaultspec agent: {agent_name}"}
    if agent_file.exists():
        agent_meta["description"] = f"Vaultspec {agent_name} agent via A2A"

    # Create executor based on --executor flag
    executor_type = args.executor or "claude"
    if executor_type == "claude":
        from protocol.a2a.executors.claude_executor import ClaudeA2AExecutor

        executor = ClaudeA2AExecutor(
            model=args.model or ClaudeModels.MEDIUM,
            root_dir=str(root),
            mode=args.mode or "read-only",
        )
    elif executor_type == "gemini":
        from protocol.a2a.executors.gemini_executor import GeminiA2AExecutor

        executor = GeminiA2AExecutor(
            root_dir=root,
            model=args.model or GeminiModels.LOW,
            agent_name=agent_name,
        )
    else:
        print(f"Unknown executor: {executor_type}", file=sys.stderr)
        sys.exit(1)

    card = agent_card_from_definition(agent_name, agent_meta, port=port)
    app = create_app(executor, card)

    from core.config import get_config

    cfg = get_config()

    print(f"Starting A2A server: {agent_name} ({executor_type}) on port {port}")
    uvicorn.run(app, host=cfg.mcp_host, port=port)


def command_list(args):
    """Handle 'list' subcommand."""
    list_available_agents(args.content_root)


def main() -> None:
    parser = argparse.ArgumentParser(description="Sub-agent CLI")
    parser.add_argument(
        "--root", type=Path, default=None, help="Workspace root directory"
    )
    parser.add_argument(
        "--content-dir",
        type=Path,
        default=None,
        help="Content source directory (rules, agents, skills)",
    )
    parser.add_argument(
        "--version", "-V", action="version", version=f"%(prog)s {_get_version()}"
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Command to execute"
    )

    # --- RUN ---
    run_parser = subparsers.add_parser(
        "run", help="Run a sub-agent interactively or one-shot"
    )
    run_parser.add_argument("--agent", "-a", help="Sub-agent name")

    # New Structured Args
    run_parser.add_argument("--goal", help="The primary objective of the task.")
    run_parser.add_argument(
        "--context",
        action="append",
        help="Path to a context file (ADR, Research, etc). Can be used multiple times.",
    )
    run_parser.add_argument("--plan", help="Path to a plan file.")

    # Legacy/Convenience
    run_parser.add_argument(
        "--task", "-t", help="Task description string (Legacy: prefer --goal)"
    )
    run_parser.add_argument(
        "--task-file", "-f", help="Path to markdown file describing the task (Legacy)"
    )

    run_parser.add_argument("--model", "-m", help="Override default model")
    run_parser.add_argument(
        "--provider",
        "-p",
        choices=["gemini", "claude"],
        help="Explicitly force a provider",
    )
    run_parser.add_argument(
        "--mode",
        choices=["read-write", "read-only"],
        default="read-write",
        help="Permission mode for the agent (default: read-write)",
    )
    run_parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Keep the session open for multi-turn interaction.",
    )
    run_parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output (INFO level)",
    )
    run_parser.add_argument(
        "--debug", action="store_true", help="Enable debug logging (DEBUG level)"
    )
    run_parser.set_defaults(func=command_run)

    # --- SERVE ---
    serve_parser = subparsers.add_parser("serve", help="Run the subagent MCP server")
    serve_parser.set_defaults(func=command_serve)

    # --- A2A-SERVE ---
    a2a_serve_parser = subparsers.add_parser(
        "a2a-serve",
        help="Start an A2A HTTP server for agent-to-agent communication",
    )
    a2a_serve_parser.add_argument(
        "--executor",
        "-e",
        choices=["claude", "gemini"],
        default="claude",
        help="Executor type (default: claude)",
    )
    a2a_serve_parser.add_argument(
        "--port",
        type=int,
        default=10010,
        help="Port to listen on (default: 10010)",
    )
    a2a_serve_parser.add_argument(
        "--agent",
        "-a",
        default="vaultspec-researcher",
        help="Agent name (default: vaultspec-researcher)",
    )
    a2a_serve_parser.add_argument("--model", "-m", help="Override default model")
    a2a_serve_parser.add_argument(
        "--mode",
        choices=["read-write", "read-only"],
        default="read-only",
        help="Permission mode (default: read-only)",
    )
    a2a_serve_parser.set_defaults(func=command_a2a_serve)

    # --- LIST ---
    list_parser = subparsers.add_parser("list", help="List available agents")
    list_parser.set_defaults(func=command_list)

    args = parser.parse_args()

    # Resolve workspace layout when overrides are provided
    if args.root is not None or getattr(args, "content_dir", None) is not None:
        _layout = resolve_workspace(
            root_override=args.root,
            content_override=getattr(args, "content_dir", None),
            framework_root=_paths_layout.framework_root,
        )
        args.root = _layout.output_root
        args.content_root = _layout.content_root
    else:
        args.root = ROOT_DIR
        args.content_root = _paths_layout.content_root

    args.root = args.root.resolve()
    args.content_root = args.content_root.resolve()

    if getattr(args, "debug", False):
        configure_logging(level="DEBUG")
    elif getattr(args, "verbose", False):
        configure_logging(level="INFO")
    else:
        configure_logging()

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
