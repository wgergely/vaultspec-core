"""Team CLI Interface.

Entry point for multi-agent team lifecycle management.

Commands:
  create   Form a new named team from agent URLs
  status   Show the current team session state
  assign   Dispatch a task to a single team member
  broadcast  Dispatch the same message to all members
  message  Send a message to a member (optionally relaying from another)
  dissolve  Tear down the team session
  list     List all active team sessions
"""

import argparse
import asyncio
import json
import sys
import warnings
from pathlib import Path

from vaultspec.core import WorkspaceLayout, resolve_workspace
from vaultspec.logging_config import configure_logging

# Resolve workspace layout at import time (replaces _paths.py bootstrap)
_default_layout: WorkspaceLayout = resolve_workspace(framework_dir_name=".vaultspec")
ROOT_DIR = _default_layout.output_root


def _get_version() -> str:
    """Read version from pyproject.toml."""
    toml_path = ROOT_DIR / "pyproject.toml"
    if toml_path.exists():
        for line in toml_path.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("version"):
                return line.split("=", 1)[1].strip().strip('"').strip("'")
    return "unknown"


try:
    from vaultspec.orchestration.team import (
        MemberStatus,
        TeamCoordinator,
        TeamMember,
        TeamSession,
        TeamStatus,
    )
except ImportError as e:
    print(f"Failed to import team library: {e}", file=sys.stderr)
    sys.exit(1)


# ---------------------------------------------------------------------------
# Session persistence helpers
# ---------------------------------------------------------------------------


def _teams_dir(root: Path) -> Path:
    """Return the directory where team session JSON files are stored."""
    return root / ".vault" / "logs" / "teams"


def _session_path(root: Path, name: str) -> Path:
    return _teams_dir(root) / f"{name}.json"


def _save_session(root: Path, session: TeamSession) -> None:
    """Persist a TeamSession to JSON on disk."""
    teams_dir = _teams_dir(root)
    teams_dir.mkdir(parents=True, exist_ok=True)
    data = {
        "team_id": session.team_id,
        "name": session.name,
        "context_id": session.context_id,
        "status": session.status.value,
        "created_at": session.created_at,
        "members": {
            member_name: {
                "name": m.name,
                "url": m.url,
                "status": m.status.value,
                "card": m.card.model_dump(mode="json"),
            }
            for member_name, m in session.members.items()
        },
    }
    path = _session_path(root, session.name)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_session(root: Path, name: str) -> TeamSession:
    """Load a TeamSession from disk. Raises SystemExit on missing/corrupt file."""
    path = _session_path(root, name)
    if not path.exists():
        print(f"No team session found: {name!r} (looked in {path})", file=sys.stderr)
        sys.exit(1)

    from a2a.types import AgentCard

    data = json.loads(path.read_text(encoding="utf-8"))
    members: dict[str, TeamMember] = {}
    for mname, mdata in data.get("members", {}).items():
        card = AgentCard.model_validate(mdata["card"])
        members[mname] = TeamMember(
            name=mdata["name"],
            url=mdata["url"],
            card=card,
            status=MemberStatus(mdata["status"]),
        )

    return TeamSession(
        team_id=data["team_id"],
        name=data["name"],
        context_id=data["context_id"],
        status=TeamStatus(data["status"]),
        created_at=data["created_at"],
        members=members,
    )


def _delete_session(root: Path, name: str) -> None:
    path = _session_path(root, name)
    if path.exists():
        path.unlink()


def _restore_coordinator(
    session: TeamSession, api_key: str | None = None
) -> TeamCoordinator:
    """Re-create a TeamCoordinator from a loaded session (no network needed)."""
    coordinator = TeamCoordinator(api_key=api_key)
    coordinator.restore_session(session)
    return coordinator


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def _parse_agents(agents_str: str) -> list[str]:
    """Parse 'agent1:port1,agent2:port2,...' into URL list."""
    urls: list[str] = []
    for entry in agents_str.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            # Could be host:port or just name:port
            parts = entry.rsplit(":", 1)
            host = parts[0].strip()
            port = parts[1].strip()
            if not host.startswith("http"):
                host = f"http://{host}"
            urls.append(f"{host}:{port}/")
        else:
            print(
                f"Warning: Cannot parse agent spec {entry!r}; expected host:port",
                file=sys.stderr,
            )
    return urls


def command_create(args) -> None:
    """Form a new team from agent URLs."""
    agent_urls = _parse_agents(args.agents)
    if not agent_urls:
        print(
            "Error: --agents must specify at least one agent (e.g. localhost:10010)",
            file=sys.stderr,
        )
        sys.exit(1)

    async def _create():
        coordinator = TeamCoordinator(api_key=args.api_key)
        async with coordinator:
            session = await coordinator.form_team(
                name=args.name,
                agent_urls=agent_urls,
                api_key=args.api_key,
            )
        return session

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            session = asyncio.run(_create())
        _save_session(args.root, session)
        print(session.team_id)
        if args.verbose:
            print(f"Team {session.name!r} formed (id={session.team_id})")
            print(f"Members: {', '.join(session.members.keys())}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


def command_status(args) -> None:
    """Print team session status."""
    session = _load_session(args.root, args.name)
    print(f"Team: {session.name}")
    print(f"  ID:       {session.team_id}")
    print(f"  Status:   {session.status.value}")
    print(f"  Members ({len(session.members)}):")
    for name, member in session.members.items():
        print(f"    {name}: {member.status.value} ({member.url})")


def command_list(args) -> None:
    """List all active team sessions."""
    teams_dir = _teams_dir(args.root)
    if not teams_dir.exists() or not any(teams_dir.glob("*.json")):
        print("No active teams.")
        return

    for path in sorted(teams_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            print(f"{data['name']}: id={data['team_id']} status={data['status']}")
        except (KeyError, json.JSONDecodeError):
            print(f"(corrupt session file: {path.name})")


def command_assign(args) -> None:
    """Dispatch a task to a single team member."""
    session = _load_session(args.root, args.name)

    async def _assign():
        coordinator = _restore_coordinator(session, api_key=args.api_key)
        async with coordinator:
            results = await coordinator.dispatch_parallel({args.agent: args.task})
            task = results.get(args.agent)
            if task is None:
                print(f"Error: dispatch to {args.agent!r} failed.", file=sys.stderr)
                sys.exit(1)
            return task

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            task = asyncio.run(_assign())
        print(f"Task {task.id}: {task.status.state.value}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


def command_broadcast(args) -> None:
    """Dispatch the same message to all team members in parallel."""
    session = _load_session(args.root, args.name)

    async def _broadcast():
        coordinator = _restore_coordinator(session, api_key=args.api_key)
        async with coordinator:
            assignments = dict.fromkeys(session.members, args.message)
            results = await coordinator.dispatch_parallel(assignments)
            return results

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            results = asyncio.run(_broadcast())
        for agent_name, task in results.items():
            print(f"{agent_name}: task={task.id} state={task.status.state.value}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


def command_message(args) -> None:
    """Send a message to a team member, optionally relaying from another."""
    session = _load_session(args.root, args.name)

    async def _message():
        coordinator = _restore_coordinator(session, api_key=args.api_key)
        async with coordinator:
            if args.from_agent:
                # Relay mode: fetch src task from args.src_task_id, relay to --to
                if not args.src_task_id:
                    print(
                        "Error: --src-task-id is required when using --from",
                        file=sys.stderr,
                    )
                    sys.exit(1)
                import uuid as _uuid

                from a2a.types import (
                    GetTaskRequest,
                    GetTaskSuccessResponse,
                    JSONRPCErrorResponse,
                    TaskQueryParams,
                )

                src_client = coordinator._get_client(args.from_agent)
                resp = await src_client.get_task(
                    GetTaskRequest(
                        id=str(_uuid.uuid4()),
                        params=TaskQueryParams(id=args.src_task_id),
                    )
                )
                result = resp.root
                if isinstance(result, JSONRPCErrorResponse):
                    raise RuntimeError(
                        f"A2A error fetching task from "
                        f"{args.from_agent!r}: {result.error}"
                    )
                assert isinstance(result, GetTaskSuccessResponse)
                src_task = result.result
                task = await coordinator.relay_output(src_task, args.to, args.content)
            else:
                # Direct dispatch
                results = await coordinator.dispatch_parallel({args.to: args.content})
                task = results.get(args.to)
                if task is None:
                    print(f"Error: dispatch to {args.to!r} failed.", file=sys.stderr)
                    sys.exit(1)
            return task

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            task = asyncio.run(_message())
        print(f"Task {task.id}: {task.status.state.value}")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


def command_dissolve(args) -> None:
    """Dissolve a team session."""
    session = _load_session(args.root, args.name)

    if not args.force:
        answer = input(f"Dissolve team {args.name!r}? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            print("Aborted.")
            return

    async def _dissolve():
        coordinator = _restore_coordinator(session, api_key=args.api_key)
        async with coordinator:
            await coordinator.dissolve_team()

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", ResourceWarning)
            asyncio.run(_dissolve())
        _delete_session(args.root, args.name)
        if args.verbose:
            print(f"Team {args.name!r} dissolved.")
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        if args.debug:
            import traceback

            traceback.print_exc()
        sys.exit(1)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Team CLI — multi-agent team lifecycle"
    )
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
        "--verbose", "-v", action="store_true", help="Enable verbose output"
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument(
        "--version", "-V", action="version", version=f"%(prog)s {_get_version()}"
    )
    subparsers = parser.add_subparsers(
        dest="command", required=True, help="Command to execute"
    )

    # --- CREATE ---
    create_parser = subparsers.add_parser("create", help="Form a new team")
    create_parser.add_argument("--name", required=True, help="Team name")
    create_parser.add_argument(
        "--agents",
        required=True,
        help="Comma-separated list of agent host:port pairs",
    )
    create_parser.add_argument(
        "--api-key", default=None, help="API key for X-API-Key header"
    )
    create_parser.set_defaults(func=command_create)

    # --- STATUS ---
    status_parser = subparsers.add_parser("status", help="Show team session status")
    status_parser.add_argument("--name", required=True, help="Team name")
    status_parser.set_defaults(func=command_status)

    # --- LIST ---
    list_parser = subparsers.add_parser("list", help="List all active teams")
    list_parser.set_defaults(func=command_list)

    # --- ASSIGN ---
    assign_parser = subparsers.add_parser(
        "assign", help="Dispatch a task to one member"
    )
    assign_parser.add_argument("--name", required=True, help="Team name")
    assign_parser.add_argument("--agent", required=True, help="Agent name to assign to")
    assign_parser.add_argument("--task", required=True, help="Task description")
    assign_parser.add_argument("--api-key", default=None, help="API key")
    assign_parser.set_defaults(func=command_assign)

    # --- BROADCAST ---
    broadcast_parser = subparsers.add_parser(
        "broadcast", help="Send the same message to all members"
    )
    broadcast_parser.add_argument("--name", required=True, help="Team name")
    broadcast_parser.add_argument("--message", required=True, help="Message text")
    broadcast_parser.add_argument("--api-key", default=None, help="API key")
    broadcast_parser.set_defaults(func=command_broadcast)

    # --- MESSAGE ---
    message_parser = subparsers.add_parser(
        "message", help="Send a message to a specific member"
    )
    message_parser.add_argument("--name", required=True, help="Team name")
    message_parser.add_argument("--to", required=True, help="Destination agent name")
    message_parser.add_argument("--content", required=True, help="Message content")
    message_parser.add_argument(
        "--from",
        dest="from_agent",
        default=None,
        help="Source agent name (enables relay mode)",
    )
    message_parser.add_argument(
        "--src-task-id",
        default=None,
        help="Source task ID to relay (required with --from)",
    )
    message_parser.add_argument("--api-key", default=None, help="API key")
    message_parser.set_defaults(func=command_message)

    # --- DISSOLVE ---
    dissolve_parser = subparsers.add_parser("dissolve", help="Dissolve a team session")
    dissolve_parser.add_argument("--name", required=True, help="Team name")
    dissolve_parser.add_argument(
        "--force", action="store_true", help="Skip confirmation prompt"
    )
    dissolve_parser.add_argument("--api-key", default=None, help="API key")
    dissolve_parser.set_defaults(func=command_dissolve)

    args = parser.parse_args()

    # Resolve workspace layout
    if args.root is not None or getattr(args, "content_dir", None) is not None:
        _layout = resolve_workspace(
            root_override=args.root,
            content_override=getattr(args, "content_dir", None),
            framework_dir_name=".vaultspec",
        )
        args.root = _layout.output_root
    else:
        args.root = ROOT_DIR

    args.root = args.root.resolve()

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
