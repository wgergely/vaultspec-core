"""A2A Server Registry.

Manages the persistence of active A2A server configurations to disk
in ``.vault/logs/teams/`` so they can be safely tracked and reaped
by CLI commands, surviving orchestrator restarts.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path  # noqa: TC003
from typing import Any

logger = logging.getLogger(__name__)

__all__ = ["ServerRegistry", "ServerState"]


@dataclass
class ServerState:
    """Persistent state record for an active A2A server."""

    session_id: str
    pid: int
    port: int
    executable: str
    args: list[str]
    model: str
    provider: str
    spawn_time: float
    mcp_servers: dict[str, Any] = field(default_factory=dict)
    cwd: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "pid": self.pid,
            "port": self.port,
            "executable": self.executable,
            "args": self.args,
            "model": self.model,
            "provider": self.provider,
            "spawn_time": self.spawn_time,
            "mcp_servers": self.mcp_servers,
            "cwd": self.cwd,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ServerState:
        return cls(
            session_id=data["session_id"],
            pid=data["pid"],
            port=data["port"],
            executable=data.get("executable", ""),
            args=data.get("args", []),
            model=data.get("model", ""),
            provider=data.get("provider", ""),
            spawn_time=data["spawn_time"],
            mcp_servers=data.get("mcp_servers", {}),
            cwd=data.get("cwd", ""),
        )


class ServerRegistry:
    """Manages reading and writing A2A server state to the workspace."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.registry_dir = self.root_dir / ".vault" / "logs" / "teams"

        # Ensure registry directory exists
        self.registry_dir.mkdir(parents=True, exist_ok=True)

    def _state_file(self, session_id: str) -> Path:
        """Get the path to the state JSON file for a given session."""
        return self.registry_dir / f"{session_id}.json"

    def register(self, state: ServerState) -> None:
        """Write a new server state record to disk."""
        target = self._state_file(state.session_id)

        # Perform an atomic or safe write via a temp file to prevent torn reads
        tmp = target.with_suffix(".tmp")
        try:
            with tmp.open("w", encoding="utf-8") as f:
                json.dump(state.to_dict(), f, indent=2)
            os.replace(tmp, target)
        except Exception as e:
            logger.error("Failed to write server registry state to %s: %s", target, e)
            if tmp.exists():
                tmp.unlink(missing_ok=True)

    def unregister(self, session_id: str) -> None:
        """Remove a server state record from disk."""
        target = self._state_file(session_id)
        if target.exists():
            try:
                target.unlink()
            except OSError as e:
                logger.warning(
                    "Failed to unlink server registry file %s: %s", target, e
                )

    def read(self, session_id: str) -> ServerState | None:
        """Read a server state record by its session ID."""
        target = self._state_file(session_id)
        if not target.exists():
            return None

        try:
            with target.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return ServerState.from_dict(data)
        except Exception as e:
            logger.warning(
                "Failed to read server registry file %s (file may be corrupted): %s",
                target,
                e,
            )
            return None

    def list_active(self) -> dict[str, ServerState]:
        """Scan the registry directory and return all valid server states.

        Returns:
            A dictionary mapping session_id to ServerState. Corrupted files
            are ignored but NOT automatically deleted.
        """
        active: dict[str, ServerState] = {}
        for file in self.registry_dir.glob("*.json"):
            session_id = file.stem
            state = self.read(session_id)
            if state:
                active[session_id] = state
        return active
