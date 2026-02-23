"""Session persistence helpers for team lifecycle management."""

import json
import logging
from pathlib import Path

from .team import MemberStatus, TeamCoordinator, TeamMember, TeamSession, TeamStatus

logger = logging.getLogger(__name__)


class SessionNotFoundError(Exception):
    """Raised when a team session file does not exist on disk."""


def teams_dir(root: Path) -> Path:
    """Return the directory where team session files are stored.

    Args:
        root: Workspace root directory.

    Returns:
        Path to ``{root}/.vault/logs/teams/``.
    """
    return root / ".vault" / "logs" / "teams"


def session_path(root: Path, name: str) -> Path:
    """Return the JSON file path for a named team session.

    Args:
        root: Workspace root directory.
        name: Team session name (used as the filename stem).

    Returns:
        Path to ``{root}/.vault/logs/teams/{name}.json``.
    """
    return teams_dir(root) / f"{name}.json"


def save_session(
    root: Path,
    session: TeamSession,
    spawned_pids: dict[str, int] | None = None,
) -> None:
    """Persist a team session to disk as a JSON file.

    Creates the teams directory if it does not exist.  If *spawned_pids* is
    provided it is stored alongside the session data and can be recovered
    with :func:`load_spawned_pids`.

    Args:
        root: Workspace root directory.
        session: The team session to serialise.
        spawned_pids: Optional mapping of agent name to OS process ID for
            subprocesses spawned during the session.
    """
    tdir = teams_dir(root)
    tdir.mkdir(parents=True, exist_ok=True)
    data: dict[str, object] = {
        "team_id": session.team_id,
        "name": session.name,
        "context_id": session.context_id,
        "status": session.status.value,
        "created_at": session.created_at,
        "members": {
            member_name: {
                "name": m.name,
                "display_name": m.display_name,
                "url": m.url,
                "status": m.status.value,
                "card": m.card.model_dump(mode="json"),
            }
            for member_name, m in session.members.items()
        },
    }
    if spawned_pids:
        data["spawned_pids"] = spawned_pids
    path = session_path(root, session.name)
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def load_spawned_pids(root: Path, name: str) -> dict[str, int]:
    """Load the spawned-PID map from a saved team session file.

    Args:
        root: Workspace root directory.
        name: Team session name.

    Returns:
        Mapping of agent name to OS process ID, or an empty dict if the
        session file does not exist or contains no PID data.
    """
    path = session_path(root, name)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in data.get("spawned_pids", {}).items()}


def load_session(root: Path, name: str) -> TeamSession:
    """Load and deserialise a team session from disk.

    Args:
        root: Workspace root directory.
        name: Team session name.

    Returns:
        A fully reconstructed :class:`~.team.TeamSession` instance.

    Raises:
        SessionNotFoundError: If no session file exists for *name*.
    """
    path = session_path(root, name)
    if not path.exists():
        raise SessionNotFoundError(
            f"No team session found: {name!r} (looked in {path})"
        )

    from a2a.types import AgentCard

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SessionNotFoundError(f"corrupt session file: {path}") from exc
    members: dict[str, TeamMember] = {}
    for mname, mdata in data.get("members", {}).items():
        card = AgentCard.model_validate(mdata["card"])
        # "display_name" was added in the URL-keyed member scheme; fall back
        # to "name" for session files written by older versions.
        display_name = mdata.get("display_name") or mdata["name"]
        members[mname] = TeamMember(
            name=mdata["name"],
            display_name=display_name,
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


def delete_session(root: Path, name: str) -> None:
    """Delete a team session file from disk if it exists.

    Args:
        root: Workspace root directory.
        name: Team session name to remove.
    """
    path = session_path(root, name)
    if path.exists():
        path.unlink()


def restore_coordinator(
    session: TeamSession,
    api_key: str | None = None,
    spawned_pids: dict[str, int] | None = None,
) -> TeamCoordinator:
    """Create a :class:`~.team.TeamCoordinator` restored from a saved session.

    Args:
        session: Previously saved team session to restore.
        api_key: Optional Anthropic API key; falls back to the environment if
            not provided.
        spawned_pids: Optional mapping of agent name to OS PID for
            subprocesses spawned in a previous session.  Passed through to
            :meth:`TeamCoordinator.restore_session` so that
            :meth:`~TeamCoordinator.dissolve_team` can terminate them.

    Returns:
        A ``TeamCoordinator`` with its session state already restored.
    """
    coordinator = TeamCoordinator(api_key=api_key)
    coordinator.restore_session(session, spawned_pids=spawned_pids)
    return coordinator


def parse_agents(agents_str: str) -> list[str]:
    """Parse a comma-separated list of ``host:port`` agent specs into URLs.

    Each entry is expected in the form ``host:port`` or
    ``scheme://host:port``.  Entries that cannot be parsed are logged as
    warnings and skipped.

    Args:
        agents_str: Comma-separated agent specs
            (e.g. ``"localhost:8001,localhost:8002"``).

    Returns:
        List of normalised agent base URLs with trailing slash
        (e.g. ``["http://localhost:8001/", "http://localhost:8002/"]``).
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
            if not host:
                logger.warning(
                    "Warning: Cannot parse agent spec %r; host is empty",
                    entry,
                )
                continue
            urls.append(f"http://{host}:{port}/")
        else:
            logger.warning(
                "Warning: Cannot parse agent spec %r; expected host:port",
                entry,
            )
    return urls
