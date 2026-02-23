"""Multi-agent team coordination MCP tools.

Surfaces :mod:`vaultspec.orchestration.team.TeamCoordinator` functionality
as MCP tools for team lifecycle management: create, status, list, dispatch,
broadcast, send, spawn, and dissolve.

Session persistence follows the same JSON-on-disk pattern used by
:mod:`vaultspec.team_cli`, storing files in ``.vault/logs/teams/``.

See :mod:`vaultspec.team_cli` for the corresponding CLI implementations.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

if TYPE_CHECKING:
    from pathlib import Path

from ..orchestration import (
    TeamCoordinator,
    TeamSession,
    TeamTaskEngine,
    extract_artifact_text,
    resolve_member_key,
)
from ..orchestration.team_session import (
    SessionNotFoundError,
)
from ..orchestration.team_session import (
    delete_session as _delete_session,
)
from ..orchestration.team_session import (
    load_session as _load_session_canonical,
)
from ..orchestration.team_session import (
    load_spawned_pids as _load_spawned_pids,
)
from ..orchestration.team_session import (
    restore_coordinator as _restore_coordinator,
)
from ..orchestration.team_session import (
    save_session as _save_session,
)
from ..orchestration.team_session import (
    teams_dir as _teams_dir,
)

__all__ = [
    "broadcast_message",
    "create_team",
    "dispatch_task",
    "dissolve_team",
    "get_team_task_status",
    "list_teams",
    "register_tools",
    "relay_output",
    "send_message",
    "spawn_agent",
    "team_status",
]

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

_root_dir: Path | None = None
_team_task_engine = TeamTaskEngine()


def _log_bg_exception(task: asyncio.Task) -> None:
    """Done-callback for background asyncio tasks — logs unhandled exceptions.

    Args:
        task: The completed asyncio Task to inspect for exceptions.
    """
    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        logger.error("Background team task failed: %s", exc, exc_info=exc)


def set_root_dir(root: Path) -> None:
    """Set the workspace root directory for session persistence.

    Args:
        root: Absolute path to the workspace root used for resolving
            ``.vault/logs/teams/`` session files.
    """
    global _root_dir
    _root_dir = root


def _get_root_dir() -> Path:
    """Return the configured workspace root, raising ToolError if unset.

    Returns:
        The workspace root path previously set via :func:`set_root_dir`.

    Raises:
        ToolError: If :func:`set_root_dir` has not been called.
    """
    if _root_dir is None:
        raise ToolError(
            "Team tools root directory not configured. "
            "Call set_root_dir() before using team tools."
        )
    return _root_dir


def _load_session(root: Path, name: str) -> TeamSession:
    """Load a TeamSession from disk. Raises ToolError on missing file.

    Thin wrapper around :func:`team_session.load_session` that converts
    :class:`SessionNotFoundError` to :class:`ToolError` for the MCP layer.
    """
    try:
        return _load_session_canonical(root, name)
    except SessionNotFoundError as exc:
        raise ToolError(str(exc)) from exc


def _parse_agent_urls(agents_str: str) -> list[str]:
    """Parse comma-separated agent URL specifications into URL list.

    Accepts ``host:port`` pairs or full URLs. Bare ``host:port`` entries
    are prefixed with ``http://`` and suffixed with ``/``.

    Args:
        agents_str: Comma-separated string of agent specs, each either a
            full URL (``http://host:port/``) or a bare ``host:port`` pair.

    Returns:
        List of normalised agent URLs, each ending with ``/``.

    Raises:
        ToolError: If an entry cannot be parsed as a URL or ``host:port``.
    """
    urls: list[str] = []
    for entry in agents_str.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if entry.startswith("http://") or entry.startswith("https://"):
            if not entry.endswith("/"):
                entry += "/"
            urls.append(entry)
        elif ":" in entry:
            parts = entry.rsplit(":", 1)
            host = parts[0].strip()
            port = parts[1].strip()
            urls.append(f"http://{host}:{port}/")
        else:
            raise ToolError(
                f"Cannot parse agent spec {entry!r}; expected host:port or full URL"
            )
    return urls


async def create_team(name: str, agent_urls: str) -> str:
    """Create a new multi-agent team from comma-separated agent URLs.

    Instantiates a :class:`TeamCoordinator`, calls ``form_team()`` to
    discover agent cards and assemble the team, then persists the session
    to ``.vault/logs/teams/{name}.json``.

    Args:
        name: Human-readable team name.
        agent_urls: Comma-separated list of agent URLs or host:port pairs.

    Returns:
        JSON string with ``team_id`` and ``members`` list.
    """
    root = _get_root_dir()
    urls = _parse_agent_urls(agent_urls)
    if not urls:
        raise ToolError("agent_urls must specify at least one agent")

    logger.info("MCP: create_team name=%s urls=%s", name, urls)

    coordinator = TeamCoordinator()
    async with coordinator:
        session = await coordinator.form_team(name=name, agent_urls=urls)

    _save_session(root, session)

    return json.dumps(
        {
            "team_id": session.team_id,
            "name": session.name,
            "members": [
                {"name": m.name, "url": m.url, "status": m.status.value}
                for m in session.members.values()
            ],
        },
        indent=2,
    )


async def team_status(name: str) -> str:
    """Get the current status of a team session.

    Loads the session from ``.vault/logs/teams/{name}.json`` and returns
    its status, member list, and member states.

    Args:
        name: Team name to look up.

    Returns:
        JSON string with ``name``, ``team_id``, ``status``, and ``members``.
    """
    root = _get_root_dir()
    logger.info("MCP: team_status name=%s", name)

    session = _load_session(root, name)

    return json.dumps(
        {
            "name": session.name,
            "team_id": session.team_id,
            "status": session.status.value,
            "created_at": session.created_at,
            "members": {
                mname: {
                    "display_name": m.display_name,
                    "url": m.url,
                    "status": m.status.value,
                }
                for mname, m in session.members.items()
            },
        },
        indent=2,
    )


async def list_teams() -> str:
    """List all active team sessions.

    Scans ``.vault/logs/teams/`` for ``.json`` files and returns a list
    of team names.

    Returns:
        JSON string with a ``teams`` list of team name strings.
    """
    root = _get_root_dir()
    logger.info("MCP: list_teams")

    teams_dir = _teams_dir(root)
    teams: list[str] = []
    if teams_dir.exists():
        for path in sorted(teams_dir.glob("*.json")):
            teams.append(path.stem)

    return json.dumps({"teams": teams, "count": len(teams)}, indent=2)


async def dispatch_task(team_name: str, agent_name: str, task: str) -> str:
    """Dispatch a task to a specific team member.

    Returns immediately with a taskId. The dispatch runs in the background;
    poll with ``get_team_task_status`` for results.

    Args:
        team_name: Name of the team.
        agent_name: Name of the agent to dispatch to.
        task: Task description text.

    Returns:
        JSON string with ``status`` and ``taskId``.
    """
    root = _get_root_dir()
    logger.info(
        "MCP: dispatch_task team=%s agent=%s task=%s",
        team_name,
        agent_name,
        task[:80],
    )

    session = _load_session(root, team_name)
    try:
        resolved_key = resolve_member_key(session.members, agent_name)
    except KeyError as exc:
        raise ToolError(str(exc)) from exc

    tt = _team_task_engine.create_task(team_name, "dispatch_task", agent=resolved_key)

    async def _run():
        """Dispatch the task to the target agent and record the result."""
        try:
            coordinator = _restore_coordinator(session)
            async with coordinator:
                results = await coordinator.dispatch_parallel({resolved_key: task})
            task_result = results.get(resolved_key)
            if task_result is None:
                _team_task_engine.fail_task(
                    tt.task_id, f"Dispatch to {resolved_key!r} returned no result."
                )
            else:
                _team_task_engine.complete_task(
                    tt.task_id,
                    {
                        "agent": resolved_key,
                        "task_id": task_result.id,
                        "state": task_result.status.state.value,
                        "result": extract_artifact_text(task_result),
                    },
                )
        except Exception as exc:
            logger.error(
                "dispatch_task failed team=%s agent=%s: %s",
                team_name,
                resolved_key,
                exc,
                exc_info=True,
            )
            _team_task_engine.fail_task(tt.task_id, str(exc))

    bg = asyncio.create_task(_run())
    bg.add_done_callback(_log_bg_exception)
    _team_task_engine.register_bg_task(tt.task_id, bg)

    return json.dumps(
        {"status": "working", "taskId": tt.task_id, "agent": resolved_key},
        indent=2,
    )


async def broadcast_message(team_name: str, message: str) -> str:
    """Broadcast a message to all members of a team.

    Returns immediately with a taskId. The broadcast runs in the background.

    Args:
        team_name: Name of the team.
        message: Message text to broadcast.

    Returns:
        JSON string with ``status`` and ``taskId``.
    """
    root = _get_root_dir()
    logger.info("MCP: broadcast_message team=%s message=%s", team_name, message[:80])

    session = _load_session(root, team_name)

    tt = _team_task_engine.create_task(team_name, "broadcast_message")

    async def _run():
        """Broadcast the message to all team members and record all results."""
        try:
            coordinator = _restore_coordinator(session)
            async with coordinator:
                assignments = dict.fromkeys(session.members, message)
                results = await coordinator.dispatch_parallel(assignments)
            _team_task_engine.complete_task(
                tt.task_id,
                {
                    "team": team_name,
                    "results": {
                        agent_name: {
                            "task_id": task.id,
                            "state": task.status.state.value,
                            "result": extract_artifact_text(task),
                        }
                        for agent_name, task in results.items()
                    },
                },
            )
        except Exception as exc:
            logger.error(
                "broadcast_message failed team=%s: %s",
                team_name,
                exc,
                exc_info=True,
            )
            _team_task_engine.fail_task(tt.task_id, str(exc))

    bg = asyncio.create_task(_run())
    bg.add_done_callback(_log_bg_exception)
    _team_task_engine.register_bg_task(tt.task_id, bg)

    return json.dumps(
        {"status": "working", "taskId": tt.task_id, "team": team_name},
        indent=2,
    )


async def send_message(team_name: str, to: str, message: str) -> str:
    """Send a message to a specific team member.

    Returns immediately with a taskId. The dispatch runs in the background.

    Args:
        team_name: Name of the team.
        to: Name of the destination agent.
        message: Message content.

    Returns:
        JSON string with ``status`` and ``taskId``.
    """
    root = _get_root_dir()
    logger.info(
        "MCP: send_message team=%s to=%s message=%s", team_name, to, message[:80]
    )

    session = _load_session(root, team_name)
    try:
        resolved_to = resolve_member_key(session.members, to)
    except KeyError as exc:
        raise ToolError(str(exc)) from exc

    tt = _team_task_engine.create_task(team_name, "send_message", to=resolved_to)

    async def _run():
        """Send the message to the target agent and record the result."""
        try:
            coordinator = _restore_coordinator(session)
            async with coordinator:
                results = await coordinator.dispatch_parallel({resolved_to: message})
            task_result = results.get(resolved_to)
            if task_result is None:
                _team_task_engine.fail_task(
                    tt.task_id, f"Dispatch to {resolved_to!r} returned no result."
                )
            else:
                _team_task_engine.complete_task(
                    tt.task_id,
                    {
                        "to": resolved_to,
                        "task_id": task_result.id,
                        "state": task_result.status.state.value,
                        "result": extract_artifact_text(task_result),
                    },
                )
        except Exception as exc:
            logger.error(
                "send_message failed team=%s to=%s: %s",
                team_name,
                resolved_to,
                exc,
                exc_info=True,
            )
            _team_task_engine.fail_task(tt.task_id, str(exc))

    bg = asyncio.create_task(_run())
    bg.add_done_callback(_log_bg_exception)
    _team_task_engine.register_bg_task(tt.task_id, bg)

    return json.dumps(
        {"status": "working", "taskId": tt.task_id, "to": resolved_to},
        indent=2,
    )


async def spawn_agent(team_name: str, script_path: str, port: int, name: str) -> str:
    """Spawn a subprocess running an A2A agent and add it to an existing team.

    Restores the coordinator from the persisted session, calls
    ``coordinator.spawn_agent()`` to start the subprocess, then saves the
    updated session with the new member.

    Args:
        team_name: Name of the team to add the agent to.
        script_path: Path to a Python script that starts an A2A server.
        port: TCP port the spawned agent will listen on.
        name: Logical name for the new team member.

    Returns:
        JSON string with the new agent's ``name`` and ``url``.
    """
    root = _get_root_dir()
    logger.info(
        "MCP: spawn_agent team=%s script=%s port=%d name=%s",
        team_name,
        script_path,
        port,
        name,
    )

    session = _load_session(root, team_name)
    existing_pids = _load_spawned_pids(root, team_name)

    coordinator = _restore_coordinator(session)
    async with coordinator:
        member = await coordinator.spawn_agent(script_path, port, name)
        # Capture PIDs before the context manager closes.
        new_pids = {
            agent_name: proc.pid
            for agent_name, proc in coordinator._spawned.items()
            if proc.pid is not None
        }

    # Merge existing and new PIDs, then persist.
    all_pids = {**existing_pids, **new_pids}
    _save_session(root, coordinator.session, spawned_pids=all_pids)

    return json.dumps(
        {
            "name": member.name,
            "url": member.url,
            "status": member.status.value,
        },
        indent=2,
    )


async def get_team_task_status(task_id: str) -> str:
    """Check the status of a team background task.

    Args:
        task_id: The taskId returned by dispatch_task, send_message, or
            broadcast_message.

    Returns:
        JSON string with task status and result (if completed).
    """
    logger.info("MCP: get_team_task_status task_id=%s", task_id)
    task = _team_task_engine.get_task(task_id)
    if task is None:
        raise ToolError(f"Team task '{task_id}' not found or expired.")

    res: dict[str, Any] = {
        "taskId": task.task_id,
        "status": task.status.value,
        "team": task.team_name,
        "operation": task.operation,
    }
    if task.result:
        res["result"] = task.result
    if task.error:
        res["error"] = task.error
    return json.dumps(res, indent=2)


async def relay_output(
    team_name: str,
    from_agent: str,
    to_agent: str,
    instructions: str = "",
) -> str:
    """Relay the output of one agent to another within the same team.

    Fetches the latest task from ``from_agent`` and sends its artifact
    text to ``to_agent`` via ``TeamCoordinator.relay_output()``.

    Args:
        team_name: Name of the team.
        from_agent: Source agent whose output to relay.
        to_agent: Destination agent to receive the relayed output.
        instructions: Optional instructions to pass to the destination agent
            alongside the relayed output.

    Returns:
        JSON string with the relay task result.
    """
    root = _get_root_dir()
    logger.info(
        "MCP: relay_output team=%s from=%s to=%s",
        team_name,
        from_agent,
        to_agent,
    )

    session = _load_session(root, team_name)
    try:
        resolved_from = resolve_member_key(session.members, from_agent)
        resolved_to = resolve_member_key(session.members, to_agent)
    except KeyError as exc:
        raise ToolError(str(exc)) from exc

    coordinator = _restore_coordinator(session)
    async with coordinator:
        tasks = await coordinator.collect_tasks()
        src_task = tasks.get(resolved_from)
        if src_task is None:
            raise ToolError(f"No results available from {from_agent!r}.")
        relayed = await coordinator.relay_output(src_task, resolved_to, instructions)

    return json.dumps(
        {
            "from": resolved_from,
            "to": resolved_to,
            "task_id": relayed.id,
            "state": relayed.status.state.value,
            "result": extract_artifact_text(relayed),
        },
        indent=2,
    )


async def dissolve_team(team_name: str) -> str:
    """Dissolve a team session.

    Restores the coordinator with persisted spawned PIDs, calls
    ``dissolve_team()`` (which terminates spawned processes internally),
    and deletes the session file from disk.

    Args:
        team_name: Name of the team to dissolve.

    Returns:
        JSON string confirming dissolution.
    """
    root = _get_root_dir()
    logger.info("MCP: dissolve_team team=%s", team_name)

    spawned_pids = _load_spawned_pids(root, team_name)
    session = _load_session(root, team_name)

    coordinator = _restore_coordinator(session, spawned_pids=spawned_pids)
    async with coordinator:
        await coordinator.dissolve_team()

    _delete_session(root, team_name)

    return json.dumps(
        {
            "team": team_name,
            "team_id": session.team_id,
            "status": "dissolved",
        },
        indent=2,
    )


def register_tools(mcp: FastMCP) -> None:
    """Register team coordination tools on the given FastMCP instance.

    Registers all 10 team tools with appropriate ``ToolAnnotations`` hints.

    Args:
        mcp: The FastMCP server instance to register tools on.
    """
    mcp.tool(
        title="Create Team",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )(create_team)

    mcp.tool(
        title="Team Status",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )(team_status)

    mcp.tool(
        title="List Teams",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )(list_teams)

    mcp.tool(
        title="Dispatch Task",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )(dispatch_task)

    mcp.tool(
        title="Broadcast Message",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )(broadcast_message)

    mcp.tool(
        title="Send Message",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )(send_message)

    mcp.tool(
        title="Spawn Agent",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )(spawn_agent)

    mcp.tool(
        title="Get Team Task Status",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )(get_team_task_status)

    mcp.tool(
        title="Relay Output",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=True,
        ),
    )(relay_output)

    mcp.tool(
        title="Dissolve Team",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )(dissolve_team)
