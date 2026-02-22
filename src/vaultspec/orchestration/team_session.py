"""Session persistence helpers for team lifecycle management."""

import json
import logging
from pathlib import Path

from .team import MemberStatus, TeamCoordinator, TeamMember, TeamSession, TeamStatus

logger = logging.getLogger(__name__)


class SessionNotFoundError(Exception):
    """Raised when a team session file does not exist on disk."""


def teams_dir(root: Path) -> Path:
    return root / ".vault" / "logs" / "teams"


def session_path(root: Path, name: str) -> Path:
    return teams_dir(root) / f"{name}.json"


def save_session(
    root: Path,
    session: TeamSession,
    spawned_pids: dict[str, int] | None = None,
) -> None:
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
    path = session_path(root, name)
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(k): int(v) for k, v in data.get("spawned_pids", {}).items()}


def load_session(root: Path, name: str) -> TeamSession:
    path = session_path(root, name)
    if not path.exists():
        raise SessionNotFoundError(
            f"No team session found: {name!r} (looked in {path})"
        )

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


def delete_session(root: Path, name: str) -> None:
    path = session_path(root, name)
    if path.exists():
        path.unlink()


def restore_coordinator(
    session: TeamSession, api_key: str | None = None
) -> TeamCoordinator:
    coordinator = TeamCoordinator(api_key=api_key)
    coordinator.restore_session(session)
    return coordinator


def parse_agents(agents_str: str) -> list[str]:
    urls: list[str] = []
    for entry in agents_str.split(","):
        entry = entry.strip()
        if not entry:
            continue
        if ":" in entry:
            parts = entry.rsplit(":", 1)
            host = parts[0].strip()
            port = parts[1].strip()
            if not host.startswith("http"):
                host = f"http://{host}"
            urls.append(f"{host}:{port}/")
        else:
            logger.warning(
                "Warning: Cannot parse agent spec %r; expected host:port",
                entry,
            )
    return urls
