"""Sub-agent CLI Interface.

The authoritative entry point for all sub-agent operations:
- run: Execute a sub-agent (ACP client mode)
- serve: Run the dispatch server (MCP mode)
- list: List available agents
"""

import argparse
import asyncio
import pathlib
import sys
import warnings

# Add library logic to path
CURRENT_DIR = pathlib.Path(__file__).resolve().parent
ROOT_DIR = CURRENT_DIR.parent.parent
LIB_SRC_DIR = ROOT_DIR / ".rules" / "lib" / "src"

if str(LIB_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(LIB_SRC_DIR))

try:
    from dispatch_server.server import main as server_main

    from orchestration.dispatch import run_dispatch
    from orchestration.utils import find_project_root
    from protocol.acp.client import DispatchClient
except ImportError as e:
    print(f"Failed to import dispatch library: {e}", file=sys.stderr)
    sys.exit(1)


def list_available_agents():
    """List all agents found in the workspace."""
    agents_dir = ROOT_DIR / ".rules" / "agents"
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
        task_goal = (
            "PERMISSION MODE: READ-ONLY\n"
            "You MUST only write files within the `.docs/` directory. "
            "Do not modify any source code files.\n\n" + task_goal
        )

    warnings.simplefilter("ignore", ResourceWarning)

    project_root = find_project_root()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            run_dispatch(
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
                client_class=DispatchClient,
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


def command_serve(_args):
    """Handle 'serve' subcommand."""
    server_main()


def command_list(_args):
    """Handle 'list' subcommand."""
    list_available_agents()


def main() -> None:
    parser = argparse.ArgumentParser(description="Sub-agent Dispatch CLI")
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
        choices=["gemini", "claude", "antigravity"],
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
        "--debug", action="store_true", help="Enable verbose debug output"
    )
    run_parser.set_defaults(func=command_run)

    # --- SERVE ---
    serve_parser = subparsers.add_parser("serve", help="Run the MCP dispatch server")
    serve_parser.set_defaults(func=command_serve)

    # --- LIST ---
    list_parser = subparsers.add_parser("list", help="List available agents")
    list_parser.set_defaults(func=command_list)

    args = parser.parse_args()
    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
