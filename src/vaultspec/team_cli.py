"""Team CLI — multi-agent team lifecycle management (create, assign, dissolve, etc.)."""

import argparse
import json
import logging
import sys

from .cli_common import (
    add_common_args,
    cli_error_handler,
    get_default_layout,
    resolve_args_workspace,
    run_async,
    setup_logging,
)
from .orchestration.team import TeamCoordinator
from .orchestration.team_session import (
    SessionNotFoundError,
    delete_session,
    load_session,
    load_spawned_pids,
    parse_agents,
    restore_coordinator,
    save_session,
    teams_dir,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------


def command_create(args) -> None:
    """Form a new named team from one or more agent URLs.

    Contacts each agent to discover its card, creates a shared context, and
    persists the resulting ``TeamSession`` to disk.

    Args:
        args: Parsed argument namespace from the ``create`` subparser.

    Returns:
        None. Prints the new team ID to stdout.
    """
    agent_urls = parse_agents(args.agents)
    if not agent_urls:
        logger.error(
            "Error: --agents must specify at least one agent (e.g. localhost:10010)"
        )
        sys.exit(1)

    async def _create():
        """Form the team and return the resulting session.

        Returns:
            The created team session object.
        """
        coordinator = TeamCoordinator(api_key=args.api_key)
        async with coordinator:
            session = await coordinator.form_team(
                name=args.name,
                agent_urls=agent_urls,
                api_key=args.api_key,
            )
        return session

    with cli_error_handler(args.debug):
        session = run_async(_create(), debug=args.debug)
        save_session(args.root, session)
        print(session.team_id)
        if args.verbose:
            logger.info("Team %r formed (id=%s)", session.name, session.team_id)
            logger.info("Members: %s", ", ".join(session.members.keys()))


def command_status(args) -> None:
    """Print the status of a team session, including all member states.

    Args:
        args: Parsed argument namespace from the ``status`` subparser.
    """
    try:
        session = load_session(args.root, args.name)
    except SessionNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    print(f"Team: {session.name}")
    print(f"  ID:       {session.team_id}")
    print(f"  Status:   {session.status.value}")
    print(f"  Members ({len(session.members)}):")
    for name, member in session.members.items():
        print(f"    {name}: {member.status.value} ({member.url})")


def command_list(args) -> None:
    """List all persisted team sessions from the teams store directory.

    Args:
        args: Parsed argument namespace from the ``list`` subparser.
    """
    tdir = teams_dir(args.root)
    if not tdir.exists() or not any(tdir.glob("*.json")):
        print("No active teams.")
        return

    for path in sorted(tdir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            print(f"{data['name']}: id={data['team_id']} status={data['status']}")
        except (KeyError, json.JSONDecodeError):
            print(f"(corrupt session file: {path.name})")


def command_assign(args) -> None:
    """Dispatch a task description to a single named team member.

    Args:
        args: Parsed argument namespace from the ``assign`` subparser.

    Returns:
        None. Prints the resulting task ID and state to stdout.
    """
    try:
        session = load_session(args.root, args.name)
    except SessionNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    async def _assign():
        """Dispatch the task and return the resulting A2A task object.

        Returns:
            The A2A task object for the assigned agent.
        """
        coordinator = restore_coordinator(session, api_key=args.api_key)
        async with coordinator:
            results = await coordinator.dispatch_parallel({args.agent: args.task})
            task = results.get(args.agent)
            if task is None:
                logger.error("Error: dispatch to %r failed.", args.agent)
                sys.exit(1)
            return task

    with cli_error_handler(args.debug):
        task = run_async(_assign(), debug=args.debug)
        print(f"Task {task.id}: {task.status.state.value}")


def command_broadcast(args) -> None:
    """Dispatch the same message to every team member in parallel.

    Args:
        args: Parsed argument namespace from the ``broadcast`` subparser.

    Returns:
        None. Prints each agent's task ID and state to stdout.
    """
    try:
        session = load_session(args.root, args.name)
    except SessionNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    async def _broadcast():
        """Broadcast to all members and return the task result mapping.

        Returns:
            Mapping of agent names to their A2A task results.
        """
        coordinator = restore_coordinator(session, api_key=args.api_key)
        async with coordinator:
            assignments = dict.fromkeys(session.members, args.message)
            results = await coordinator.dispatch_parallel(assignments)
            return results

    with cli_error_handler(args.debug):
        results = run_async(_broadcast(), debug=args.debug)
        for agent_name, task in results.items():
            print(f"{agent_name}: task={task.id} state={task.status.state.value}")


def command_message(args) -> None:
    """Send a message to a specific team member, with optional relay from another.

    In relay mode (``--from`` provided) the output of a previous task is
    fetched from the source agent and forwarded to the destination agent.

    Args:
        args: Parsed argument namespace from the ``message`` subparser.

    Returns:
        None. Prints the resulting task ID and state to stdout.
    """
    try:
        session = load_session(args.root, args.name)
    except SessionNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)

    async def _message():
        """Send or relay the message and return the resulting A2A task object.

        Returns:
            The A2A task object from the target agent.
        """
        coordinator = restore_coordinator(session, api_key=args.api_key)
        async with coordinator:
            if args.from_agent:
                # Relay mode: fetch src task from args.src_task_id, relay to --to
                if not args.src_task_id:
                    logger.error("Error: --src-task-id is required when using --from")
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
                    logger.error("Error: dispatch to %r failed.", args.to)
                    sys.exit(1)
            return task

    with cli_error_handler(args.debug):
        task = run_async(_message(), debug=args.debug)
        print(f"Task {task.id}: {task.status.state.value}")


def command_spawn(args) -> None:
    """Spawn a new agent subprocess and register it as a team member.

    Starts the Python script at ``args.script`` on the given port, waits
    for the process to become ready, then persists the updated session with
    the new member's PID.

    Args:
        args: Parsed argument namespace from the ``spawn`` subparser.

    Returns:
        None. Logs the spawned agent name, port, and URL.
    """
    try:
        session = load_session(args.root, args.name)
    except SessionNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    existing_pids = load_spawned_pids(args.root, args.name)

    async def _spawn():
        """Spawn the agent process and return spawn results.

        Returns:
            Tuple of (member card, updated session, list of new PIDs).
        """
        coordinator = restore_coordinator(session, api_key=args.api_key)
        async with coordinator:
            member = await coordinator.spawn_agent(
                script_path=args.script,
                port=args.port,
                name=args.agent,
            )
            new_pids = {
                agent_name: proc.pid
                for agent_name, proc in coordinator._spawned.items()
                if proc.pid is not None
            }
            return member, coordinator.session, new_pids

    with cli_error_handler(args.debug):
        member, updated_session, new_pids = run_async(_spawn(), debug=args.debug)
        all_pids = {**existing_pids, **new_pids}
        save_session(args.root, updated_session, spawned_pids=all_pids)
        logger.info("Spawned %s on port %d (%s)", member.name, args.port, member.url)


def command_dissolve(args) -> None:
    """Dissolve a team session and terminate any spawned agent processes.

    Prompts for confirmation unless ``--force`` is passed.  Sends the
    dissolve signal via the coordinator, then SIGTERMs any previously
    spawned processes and removes the session file.

    Args:
        args: Parsed argument namespace from the ``dissolve`` subparser.
    """
    import os
    import signal

    try:
        session = load_session(args.root, args.name)
    except SessionNotFoundError as exc:
        logger.error("%s", exc)
        sys.exit(1)
    spawned_pids = load_spawned_pids(args.root, args.name)

    if not args.force:
        answer = input(f"Dissolve team {args.name!r}? [y/N] ")
        if answer.strip().lower() not in ("y", "yes"):
            logger.info("Aborted.")
            return

    async def _dissolve():
        """Send the dissolve signal via the coordinator."""
        coordinator = restore_coordinator(session, api_key=args.api_key)
        async with coordinator:
            await coordinator.dissolve_team()

    with cli_error_handler(args.debug):
        run_async(_dissolve(), debug=args.debug)

        for agent_name, pid in spawned_pids.items():
            try:
                os.kill(pid, signal.SIGTERM)
                logger.debug("Terminated spawned process %s (pid=%d)", agent_name, pid)
            except ProcessLookupError:
                logger.debug(
                    "Spawned process %s (pid=%d) already exited", agent_name, pid
                )
            except OSError as exc:
                logger.warning(
                    "Failed to terminate spawned process %s (pid=%d): %s",
                    agent_name,
                    pid,
                    exc,
                )

        delete_session(args.root, args.name)
        if args.verbose:
            logger.info("Team %r dissolved.", args.name)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------


def main() -> None:
    """Parse arguments and dispatch to the appropriate team subcommand handler."""
    parser = argparse.ArgumentParser(
        description="Team CLI — multi-agent team lifecycle"
    )
    add_common_args(parser)
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

    # --- SPAWN ---
    spawn_parser = subparsers.add_parser(
        "spawn", help="Spawn a new agent process and add it to the team"
    )
    spawn_parser.add_argument("--name", required=True, help="Team name")
    spawn_parser.add_argument(
        "--agent", required=True, help="Logical name for the new agent"
    )
    spawn_parser.add_argument(
        "--script",
        required=True,
        help="Path to Python script that starts the A2A server",
    )
    spawn_parser.add_argument(
        "--port", type=int, required=True, help="TCP port for the agent"
    )
    spawn_parser.add_argument("--api-key", default=None, help="API key")
    spawn_parser.set_defaults(func=command_spawn)

    # --- DISSOLVE ---
    dissolve_parser = subparsers.add_parser("dissolve", help="Dissolve a team session")
    dissolve_parser.add_argument("--name", required=True, help="Team name")
    dissolve_parser.add_argument(
        "--force", action="store_true", help="Skip confirmation prompt"
    )
    dissolve_parser.add_argument("--api-key", default=None, help="API key")
    dissolve_parser.set_defaults(func=command_dissolve)

    args = parser.parse_args()

    _default_layout = get_default_layout()
    resolve_args_workspace(args, _default_layout)
    setup_logging(args)

    if hasattr(args, "func"):
        args.func(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
