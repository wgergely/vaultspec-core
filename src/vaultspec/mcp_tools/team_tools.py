"""Multi-agent team coordination MCP tools.

Surfaces :mod:`vaultspec.orchestration.team.TeamCoordinator` functionality
as MCP tools for team lifecycle management: create, status, list, dispatch,
broadcast, send, spawn, and dissolve.

Session persistence follows the same JSON-on-disk pattern used by
:mod:`vaultspec.team_cli`, storing files in ``.vault/logs/teams/``.

See :mod:`vaultspec.team_cli` for the corresponding CLI implementations.
"""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from mcp.server.fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

if TYPE_CHECKING:
    from pathlib import Path

from vaultspec.orchestration.team import (
    MemberStatus,
    TeamCoordinator,
    TeamMember,
    TeamSession,
    TeamStatus,
    extract_artifact_text,
)

__all__ = [
    "broadcast_message",
    "create_team",
    "dispatch_task",
    "dissolve_team",
    "list_teams",
    "register_tools",
    "send_message",
    "spawn_agent",
    "team_status",
]

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level configuration -- set by register_tools() caller or tests.
# ---------------------------------------------------------------------------

_root_dir: Path | None = None


def set_root_dir(root: Path) -> None:
    """Set the workspace root directory for session persistence."""
    global _root_dir
    _root_dir = root


def _get_root_dir() -> Path:
    """Return the configured workspace root, raising ToolError if unset."""
    if _root_dir is None:
        raise ToolError(
            "Team tools root directory not configured. "
            "Call set_root_dir() before using team tools."
        )
    return _root_dir


# ---------------------------------------------------------------------------
# Session persistence helpers (mirrors team_cli.py private functions)
# ---------------------------------------------------------------------------


def _teams_dir(root: Path) -> Path:
    """Return the directory where team session JSON files are stored."""
    return root / ".vault" / "logs" / "teams"


def _session_path(root: Path, name: str) -> Path:
    return _teams_dir(root) / f"{name}.json"


def _save_session(
    root: Path,
    session: TeamSession,
    spawned_pids: dict[str, int] | None = None,
) -> None:
    """Persist a TeamSession to JSON on disk.

    Args:
        root: Workspace root directory.
        session: The session to persist.
        spawned_pids: Optional mapping of agent name to OS PID for spawned
            subprocesses.  Stored alongside the session so that future
            ``dissolve_team`` calls can terminate them.
    """
    teams_dir = _teams_dir(root)
    teams_dir.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {
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
    if spawned_pids:
        data["spawned_pids"] = spawned_pids
    path = _session_path(root, session.name)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _load_session(root: Path, name: str) -> TeamSession:
    """Load a TeamSession from disk. Raises ToolError on missing/corrupt file."""
    path = _session_path(root, name)
    if not path.exists():
        raise ToolError(f"No team session found: {name!r} (looked in {path})")

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


def _load_spawned_pids(root: Path, name: str) -> dict[str, int]:
    """Load spawned process PIDs from a persisted session file.

    Returns an empty dict if the session has no spawned_pids entry.
    """
    path = _session_path(root, name)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in data.get("spawned_pids", {}).items()}


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
# Tool functions (undecorated -- registered by register_tools())
# ---------------------------------------------------------------------------


def _parse_agent_urls(agents_str: str) -> list[str]:
    """Parse comma-separated agent URL specifications into URL list.

    Accepts ``host:port`` pairs or full URLs. Bare ``host:port`` entries
    are prefixed with ``http://`` and suffixed with ``/``.
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

    Restores the coordinator from the persisted session and calls
    ``dispatch_parallel({agent_name: task})``.

    Args:
        team_name: Name of the team.
        agent_name: Name of the agent to dispatch to.
        task: Task description text.

    Returns:
        JSON string with the task result.
    """
    root = _get_root_dir()
    logger.info(
        "MCP: dispatch_task team=%s agent=%s task=%s",
        team_name,
        agent_name,
        task[:80],
    )

    session = _load_session(root, team_name)
    if agent_name not in session.members:
        raise ToolError(
            f"Agent {agent_name!r} is not a member of team {team_name!r}. "
            f"Members: {', '.join(session.members.keys())}"
        )

    coordinator = _restore_coordinator(session)
    async with coordinator:
        results = await coordinator.dispatch_parallel({agent_name: task})

    task_result = results.get(agent_name)
    if task_result is None:
        raise ToolError(f"Dispatch to {agent_name!r} failed with no result.")

    return json.dumps(
        {
            "agent": agent_name,
            "task_id": task_result.id,
            "state": task_result.status.state.value,
            "result": extract_artifact_text(task_result),
        },
        indent=2,
    )


async def broadcast_message(team_name: str, message: str) -> str:
    """Broadcast a message to all members of a team.

    Dispatches the same message to every member in parallel via
    ``dispatch_parallel()``.

    Args:
        team_name: Name of the team.
        message: Message text to broadcast.

    Returns:
        JSON string with per-agent results.
    """
    root = _get_root_dir()
    logger.info("MCP: broadcast_message team=%s message=%s", team_name, message[:80])

    session = _load_session(root, team_name)

    coordinator = _restore_coordinator(session)
    async with coordinator:
        assignments = dict.fromkeys(session.members, message)
        results = await coordinator.dispatch_parallel(assignments)

    return json.dumps(
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
        indent=2,
    )


async def send_message(team_name: str, to: str, message: str) -> str:
    """Send a message to a specific team member.

    Dispatches a message to a single agent via ``dispatch_parallel()``.

    Args:
        team_name: Name of the team.
        to: Name of the destination agent.
        message: Message content.

    Returns:
        JSON string with the task result.
    """
    root = _get_root_dir()
    logger.info(
        "MCP: send_message team=%s to=%s message=%s", team_name, to, message[:80]
    )

    session = _load_session(root, team_name)
    if to not in session.members:
        raise ToolError(
            f"Agent {to!r} is not a member of team {team_name!r}. "
            f"Members: {', '.join(session.members.keys())}"
        )

    coordinator = _restore_coordinator(session)
    async with coordinator:
        results = await coordinator.dispatch_parallel({to: message})

    task_result = results.get(to)
    if task_result is None:
        raise ToolError(f"Dispatch to {to!r} failed with no result.")

    return json.dumps(
        {
            "to": to,
            "task_id": task_result.id,
            "state": task_result.status.state.value,
            "result": extract_artifact_text(task_result),
        },
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


async def dissolve_team(team_name: str) -> str:
    """Dissolve a team session.

    Restores the coordinator, calls ``dissolve_team()``, terminates any
    spawned subprocesses tracked by PID, and deletes the session file
    from disk.

    Args:
        team_name: Name of the team to dissolve.

    Returns:
        JSON string confirming dissolution.
    """
    import os
    import signal

    root = _get_root_dir()
    logger.info("MCP: dissolve_team team=%s", team_name)

    spawned_pids = _load_spawned_pids(root, team_name)
    session = _load_session(root, team_name)

    coordinator = _restore_coordinator(session)
    async with coordinator:
        await coordinator.dissolve_team()

    # Terminate spawned processes that were persisted across tool calls.
    for agent_name, pid in spawned_pids.items():
        try:
            os.kill(pid, signal.SIGTERM)
            logger.debug("Sent SIGTERM to spawned process %s (pid=%d)", agent_name, pid)
        except ProcessLookupError:
            logger.debug("Spawned process %s (pid=%d) already exited", agent_name, pid)
        except OSError as exc:
            logger.warning(
                "Failed to terminate spawned process %s (pid=%d): %s",
                agent_name,
                pid,
                exc,
            )

    _delete_session(root, team_name)

    return json.dumps(
        {
            "team": team_name,
            "team_id": session.team_id,
            "status": "dissolved",
        },
        indent=2,
    )


# ---------------------------------------------------------------------------
# Registration API -- used by the unified server (vaultspec.server)
# ---------------------------------------------------------------------------


def register_tools(mcp: FastMCP) -> None:
    """Register team coordination tools on the given FastMCP instance.

    Registers all 8 team tools with appropriate ``ToolAnnotations`` hints.
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
        title="Dissolve Team",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )(dissolve_team)
