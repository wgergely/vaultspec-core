"""ACP Dispatch CLI Entrypoint.

Delegates to the modular implementation in .rules/lib/src/orchestration/dispatch.py
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
    from orchestration.dispatch import run_dispatch
    from orchestration.utils import find_project_root
    from protocol.acp.client import DispatchClient
except ImportError as e:
    print(f"Failed to import dispatch library: {e}", file=sys.stderr)
    sys.exit(1)


def list_available_agents():
    # Helper to list agents (simplified version of what was there)
    agents_dir = ROOT_DIR / ".rules" / "agents"
    if not agents_dir.exists():
        print("No agents found.", file=sys.stderr)
        return

    print(f"Agents in {agents_dir}:")
    for agent_file in sorted(agents_dir.glob("*.md")):
        print(f"  {agent_file.stem}")


def main() -> None:
    parser = argparse.ArgumentParser(description="ACP Sub-Agent Dispatcher (Modular)")
    parser.add_argument("--agent", "-a", help="Sub-agent name")
    parser.add_argument("--task", "-t", help="Task description string")
    parser.add_argument(
        "--task-file", "-f", help="Path to markdown file describing the task"
    )
    parser.add_argument(
        "--model", "-m", help="Override default model"
    )
    parser.add_argument(
        "--provider", "-p", choices=["gemini", "claude", "antigravity"], help="Explicitly force a provider"
    )
    parser.add_argument(
        "--mode", choices=["read-write", "read-only"],
        default="read-write",
        help="Permission mode for the agent (default: read-write)"
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Keep the session open for multi-turn interaction."
    )
    parser.add_argument(
        "--list-agents", action="store_true", help="List available agents and exit"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable verbose debug output"
    )

    args = parser.parse_args()

    if args.list_agents:
        list_available_agents()
        sys.exit(0)

    if not args.agent:
        parser.error("--agent is required")

    task_context = args.task or ""
    if args.task_file:
        task_path = pathlib.Path(args.task_file)
        if task_path.exists():
            content = task_path.read_text(encoding="utf-8")
            task_context = f"{task_context}\n\n{content}".strip()
            # Simple regex to find agent in file if not provided
            import re
            match = re.search(r"Agent:\s*([a-zA-Z0-9_-]+)", content)
            if match and not args.agent:
                args.agent = match.group(1)
        else:
             print(f"Task file not found: {args.task_file}", file=sys.stderr)
             sys.exit(1)

    if not task_context:
        print("Error: No task provided", file=sys.stderr)
        sys.exit(1)

    # Permission prompt for read-only
    if args.mode == "read-only":
        task_context = (
            "PERMISSION MODE: READ-ONLY\n"
            "You MUST only write files within the `.docs/` directory. "
            "Do not modify any source code files.\n\n"
            + task_context
        )

    warnings.simplefilter("ignore", ResourceWarning)
    
    project_root = find_project_root()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        result = loop.run_until_complete(
            run_dispatch(
                agent_name=args.agent,
                initial_task=task_context,
                root_dir=project_root,
                model_override=args.model,
                provider_override=args.provider,
                interactive=args.interactive,
                debug=args.debug,
                mode=args.mode,
                quiet=False, # CLI should be noisy
                client_class=DispatchClient
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

if __name__ == "__main__":
    main()