"""A2A Server Management CLI.

Provides tools for starting, stopping, and monitoring daemonized A2A servers
across the workspace.
"""

import argparse
import logging
import os
import subprocess
import sys
import time
from pathlib import Path

from .cli_common import add_common_args, add_verbosity_args
from .protocol.a2a.server_registry import ServerRegistry, ServerState

logger = logging.getLogger(__name__)


def command_server_list(args) -> None:
    """List active A2A servers tracked in the registry."""
    registry = ServerRegistry(args.root)
    active = registry.list_active()

    if not active:
        args.printer.out("No active A2A servers found.")
        return

    # Table header
    args.printer.out(f"{'SESSION ID':<38} {'PID':<8} {'PORT':<8} {'EXECUTABLE':<30}")
    args.printer.out("-" * 86)

    for sid, state in active.items():
        # Check if process is actually alive
        alive = True
        if sys.platform == "win32":
            try:
                output = subprocess.check_output(
                    ["tasklist", "/FI", f"PID eq {state.pid}", "/NH"],
                    text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW,
                )
                if str(state.pid) not in output:
                    alive = False
            except Exception:
                alive = False
        else:
            try:
                os.kill(state.pid, 0)
            except OSError as e:
                import errno

                if getattr(e, "errno", None) == errno.ESRCH:
                    alive = False

        status = " (DEAD)" if not alive else ""
        exe_short = Path(state.executable).name if state.executable else "unknown"
        args.printer.out(
            f"{sid:<38} {state.pid:<8} {state.port:<8} {exe_short}{status}"
        )


def command_server_start(args) -> None:
    """Spawn an A2A server in the background and detach."""
    import uuid

    from .protocol.providers import ProcessSpec

    # 1. Prepare process spec as if we were subagent a2a-serve
    spec = ProcessSpec(
        executable=sys.executable,
        args=[
            "-m",
            "vaultspec",
            "subagent",
            "--root",
            str(args.root),
            "a2a-serve",
            "--executor",
            args.executor,
            "--port",
            str(args.port),
        ],
        env=dict(os.environ),
        cleanup_paths=[],
    )
    if args.model:
        spec.args.extend(["--model", args.model])

    # Inject parent PID for tracking
    env = dict(spec.env)
    env["VAULTSPEC_PARENT_PID"] = str(os.getpid())

    # Ensure log directory exists
    log_dir = args.root / ".vault" / "logs" / "teams"
    log_dir.mkdir(parents=True, exist_ok=True)

    session_id = str(uuid.uuid4())
    log_file = log_dir / f"{session_id}.log"

    args.printer.out(f"Starting {args.executor} server in background...")
    args.printer.out(f"Session ID: {session_id}")
    args.printer.out(f"Logs: {log_file}")

    # Spawn detached process
    creationflags = 0
    if sys.platform == "win32":
        creationflags = subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS

    with log_file.open("w", encoding="utf-8") as out_f:
        proc = subprocess.Popen(
            [spec.executable, *spec.args],
            env=env,
            cwd=str(args.root),
            stdout=out_f,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            creationflags=creationflags,
            start_new_session=(sys.platform != "win32"),  # Unix detach
        )

    args.printer.out("Waiting for server to announce port...")
    port = args.port
    start_time = time.time()
    while time.time() - start_time < 10.0:
        content = log_file.read_text(encoding="utf-8")
        if "PORT=" in content:
            for line in content.splitlines():
                if line.startswith("PORT="):
                    port = int(line.split("PORT=")[1])
                    break
            break
        time.sleep(0.1)

    registry = ServerRegistry(args.root)
    state = ServerState(
        session_id=session_id,
        pid=proc.pid,
        port=port,
        executable=spec.executable,
        args=spec.args,
        model=args.model or "unknown",
        provider="gemini" if "gemini" in args.executor else "claude",
        spawn_time=time.time(),
        cwd=str(args.root),
    )
    registry.register(state)

    args.printer.out(f"Spawned server PID: {proc.pid} on port {port}")
    args.printer.out("Note: Run `vaultspec server list` to manage active servers.")


def command_server_stop(args) -> None:
    """Kill an active A2A server by session ID."""
    from .orchestration.utils import kill_process_tree

    registry = ServerRegistry(args.root)
    state = registry.read(args.session_id)

    if not state:
        args.printer.error(f"No active server found with session ID {args.session_id}")
        return

    args.printer.out(f"Stopping server {args.session_id} (PID {state.pid})...")
    kill_process_tree(state.pid)

    registry.unregister(args.session_id)
    args.printer.out("Server stopped and unregistered.")


def command_server_logs(args) -> None:
    """Tail or read the logs for an active server."""
    log_file = args.root / ".vault" / "logs" / "teams" / f"{args.session_id}.log"

    if not log_file.exists():
        args.printer.error(f"Log file not found: {log_file}")
        return

    args.printer.out(f"--- LOGS FOR {args.session_id} ---")
    with log_file.open("r", encoding="utf-8") as f:
        print(f.read(), end="")


def _make_parser() -> argparse.ArgumentParser:
    """Build and return the server CLI argument parser."""
    parser = argparse.ArgumentParser(description="Manage daemonized A2A servers")
    add_common_args(parser)
    server_subparsers = parser.add_subparsers(dest="server_command", required=True)

    # --- LIST ---
    list_parser = server_subparsers.add_parser("list", help="List active servers")
    add_verbosity_args(list_parser)
    list_parser.set_defaults(func=command_server_list)

    # --- START ---
    start_parser = server_subparsers.add_parser(
        "start", help="Spawn a detached A2A server"
    )
    add_verbosity_args(start_parser)

    from .core.enums import Tool

    start_parser.add_argument(
        "--executor",
        "-e",
        choices=[Tool.CLAUDE.value, Tool.GEMINI.value],
        default=Tool.CLAUDE.value,
        help=f"Executor type (default: {Tool.CLAUDE.value})",
    )
    start_parser.add_argument(
        "--port",
        type=int,
        default=0,  # 0 means auto-assign
        help="Port to listen on (default: 0 for auto)",
    )
    start_parser.add_argument("--model", "-m", help="Override default model")
    start_parser.set_defaults(func=command_server_start)

    # --- STOP ---
    stop_parser = server_subparsers.add_parser("stop", help="Stop an active server")
    add_verbosity_args(stop_parser)
    stop_parser.add_argument("session_id", help="Session ID of the server to stop")
    stop_parser.set_defaults(func=command_server_stop)

    # --- LOGS ---
    logs_parser = server_subparsers.add_parser("logs", help="View logs for a server")
    add_verbosity_args(logs_parser)
    logs_parser.add_argument("session_id", help="Session ID of the server")
    logs_parser.set_defaults(func=command_server_logs)

    return parser


def main() -> None:
    """Parse arguments and dispatch to the appropriate subcommand handler."""
    from .cli_common import get_default_layout, resolve_args_workspace, setup_logging

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
