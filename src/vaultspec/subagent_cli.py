"""Sub-agent CLI — entry point for running, serving, and listing sub-agents.

Commands:
    run:       Execute a named sub-agent one-shot or interactively.
    serve:     Start the subagent MCP server.
    a2a-serve: Start an A2A HTTP server backed by a Claude or Gemini executor.
    list:      Print all available agents discovered under the content root.
"""

import argparse
import json
import logging
import sys
from pathlib import Path

from .cli_common import (
    add_common_args,
    get_default_layout,
    resolve_args_workspace,
    run_async,
    setup_logging,
)
from .mcp_server.app import main as server_main
from .orchestration.subagent import (
    AgentNotFoundError,
    list_available_agents,
    load_agent,
    run_subagent,
)
from .protocol.acp import SubagentClient
from .protocol.providers import ClaudeModels, GeminiModels

logger = logging.getLogger(__name__)


def command_run(args):
    """Execute a sub-agent in one-shot or interactive mode.

    Resolves context files, plan file, and goal from ``args``, then
    dispatches to ``run_subagent`` via the async runner.  Prints the
    agent's response text when one is returned.

    Args:
        args: Parsed argument namespace from the ``run`` subparser.
    """
    if not args.agent:
        logger.error("Error: --agent is required for 'run'")
        sys.exit(1)

    # Resolve Context Files
    context_files = []
    if args.context:
        for ctx_path in args.context:
            p = Path(ctx_path)
            if not p.exists():
                logger.warning("Warning: Context file not found: %s", p)
            else:
                context_files.append(p)

    # Resolve Plan File
    plan_file = None
    if args.plan:
        p = Path(args.plan)
        if not p.exists():
            logger.error("Error: Plan file not found: %s", p)
            sys.exit(1)
        plan_file = p

    # Determine Task/Goal
    task_goal = args.goal or args.task or ""
    if not task_goal and not plan_file:
        logger.error("Error: You must provide a --goal, --task, or a --plan.")
        sys.exit(1)

    # Legacy Task File Support
    if args.task_file:
        p = Path(args.task_file)
        if p.exists():
            content = p.read_text(encoding="utf-8")
            task_goal = f"{task_goal}\n\n{content}".strip()
        else:
            logger.error("Task file not found: %s", args.task_file)
            sys.exit(1)

    # Permission prompt for read-only
    if args.mode == "read-only":
        from .orchestration.constants import READONLY_PERMISSION_PROMPT

        task_goal = READONLY_PERMISSION_PROMPT + task_goal

    project_root = args.root

    # Parse MCP servers JSON if provided
    mcp_servers = None
    if args.mcp_servers:
        try:
            mcp_servers = json.loads(args.mcp_servers)
        except json.JSONDecodeError as e:
            logger.error("Error: Invalid JSON for --mcp-servers: %s", e)
            sys.exit(1)

    result = run_async(
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
            resume_session_id=args.resume_session,
            max_turns=args.max_turns,
            budget=args.budget,
            effort=args.effort,
            output_format=args.output_format,
            mcp_servers=mcp_servers,
        ),
        debug=args.debug,
    )
    if result is not None and result.response_text:
        args.printer.out("\n--- Response ---\n")
        args.printer.out(result.response_text)


def command_serve(_args):
    """Start the subagent MCP server.

    Args:
        _args: Parsed argument namespace from the ``serve`` subparser.
    """
    server_main()


def command_a2a_serve(args):
    """Start an A2A HTTP server backed by a Claude or Gemini executor.

    Loads the agent definition, instantiates the appropriate executor, builds
    an agent card, and serves the A2A ASGI app via uvicorn.

    Args:
        args: Parsed argument namespace from the ``a2a-serve`` subparser.
    """
    import uvicorn

    from .protocol.a2a import agent_card_from_definition, create_app

    root = args.root
    content_root = args.content_root
    agent_name = args.agent or "vaultspec-researcher"
    port = args.port or 10010

    try:
        agent_meta, agent_persona = load_agent(
            agent_name,
            root,
            content_root=content_root,
        )
    except AgentNotFoundError:
        logger.warning("Agent '%s' not found — starting with stub metadata", agent_name)
        agent_meta = {
            "name": agent_name,
            "description": f"Vaultspec agent: {agent_name}",
        }
        agent_persona = None

    # Create executor based on --executor flag
    executor_type = args.executor or "claude"
    if executor_type == "claude":
        from .protocol.a2a.executors import ClaudeA2AExecutor

        executor = ClaudeA2AExecutor(
            model=args.model or ClaudeModels.MEDIUM,
            root_dir=str(root),
            mode=args.mode or "read-only",
            system_prompt=agent_persona,
        )
    elif executor_type == "gemini":
        from .protocol.a2a.executors import GeminiA2AExecutor

        executor = GeminiA2AExecutor(
            root_dir=root,
            model=args.model or GeminiModels.LOW,
            agent_name=agent_name,
        )
    else:
        logger.error("Unknown executor: %s", executor_type)
        sys.exit(1)

    card = agent_card_from_definition(agent_name, agent_meta, port=port)
    app = create_app(executor, card)

    from .config import get_config

    cfg = get_config()

    logger.info(
        "Starting A2A server: %s (%s) on port %d", agent_name, executor_type, port
    )
    uvicorn.run(app, host=cfg.mcp_host, port=port)


def command_list(args):
    """Print all available agents found under the content root.

    Args:
        args: Parsed argument namespace from the ``list`` subparser.
    """
    list_available_agents(args.content_root)


def _make_parser() -> argparse.ArgumentParser:
    """Build and return the subagent CLI argument parser."""
    parser = argparse.ArgumentParser(description="Sub-agent CLI")
    add_common_args(parser)
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
        "--resume-session",
        type=str,
        default=None,
        help="Resume an existing ACP session by ID.",
    )
    run_parser.add_argument(
        "--max-turns",
        type=int,
        default=None,
        help="Maximum number of agent turns.",
    )
    run_parser.add_argument(
        "--budget",
        type=float,
        default=None,
        help="Token budget limit for the agent run.",
    )
    run_parser.add_argument(
        "--effort",
        choices=["low", "medium", "high"],
        default=None,
        help="Effort level for the agent run.",
    )
    run_parser.add_argument(
        "--output-format",
        choices=["text", "json", "stream-json"],
        default=None,
        help="Output format for agent responses.",
    )
    run_parser.add_argument(
        "--mcp-servers",
        type=str,
        default=None,
        help=(
            "MCP server configuration as JSON string "
            '(e.g. \'{"server": {"command": "..."}}\').'
        ),
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

    return parser


def main() -> None:
    """Parse arguments and dispatch to the appropriate subcommand handler."""
    parser = _make_parser()
    args = parser.parse_args()

    resolve_args_workspace(args, get_default_layout())
    setup_logging(args, default_format="%(message)s")

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
