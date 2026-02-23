"""Centralized session logging for agent orchestration.

Writes structured JSONL events to the vault logs directory.
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from ..config import get_config

__all__ = ["SessionLogger", "cleanup_old_logs"]

if TYPE_CHECKING:
    import pathlib

logger = logging.getLogger(__name__)


class SessionLogger:
    """Handles persistent logging of agent session events to disk.

    Each logger creates a JSONL file under ``{root_dir}/{docs_dir}/{logs_dir}``
    and writes a ``session_start`` entry on construction.  Subsequent events
    are appended via :meth:`log`.

    Log files use the naming convention:
        ``{YYYY-MM-DDTHH-MM-SS}_{agent_name}_{task_id_short}.jsonl``

    Attributes:
        start_time: UTC datetime when this logger was created.
        log_dir: Resolved directory where the log file is written.
        log_file: Full path to the JSONL log file for this session.
    """

    def __init__(
        self,
        root_dir: pathlib.Path,
        agent_name: str = "unknown",
        task_id: str | None = None,
    ):
        """Initialize the session logger and write the session_start event.

        Args:
            root_dir: Workspace root used to resolve the log directory and to
                make the log path workspace-relative.
            agent_name: Human-readable name of the agent being logged.
            task_id: Optional task identifier; a random UUID is generated when
                not provided.
        """
        cfg = get_config()
        self._root_dir = root_dir
        self._agent_name = agent_name
        self._task_id = task_id or str(uuid.uuid4())
        self.start_time = datetime.datetime.now(datetime.UTC)

        # Resolve log directory from config
        self.log_dir = root_dir / cfg.docs_dir / cfg.logs_dir
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Build filename: YYYY-MM-DDTHH-MM-SS_agent_taskid8.jsonl
        ts = self.start_time.strftime("%Y-%m-%dT%H-%M-%S")
        task_short = self._task_id[:8]
        self.log_file = self.log_dir / f"{ts}_{agent_name}_{task_short}.jsonl"

        # Write session_start header
        self.log(
            "session_start",
            {
                "agent_name": agent_name,
                "task_id": self._task_id,
                "start_time": self.start_time.isoformat(),
                "root_dir": str(root_dir),
            },
        )

    @property
    def log_path(self) -> str:
        """Return the workspace-relative path to the log file.

        Falls back to the absolute POSIX path if the log file is outside the
        workspace root.

        Returns:
            Workspace-relative POSIX path string, or absolute POSIX path if the
            log file lives outside the workspace root.
        """
        try:
            return self.log_file.relative_to(self._root_dir).as_posix()
        except ValueError:
            return self.log_file.as_posix()

    def log(self, event_type: str, data: Any) -> None:
        """Append a structured JSONL event to the log file.

        Each line written has the shape:
        ``{"timestamp": "<iso>", "type": "<event_type>", "data": <data>}``

        Args:
            event_type: Short string identifying the event category (e.g.
                ``"session_start"``, ``"tool_call"``).
            data: Arbitrary JSON-serialisable payload for the event.
        """
        try:
            timestamp = datetime.datetime.now(datetime.UTC).isoformat()
            log_entry = {"timestamp": timestamp, "type": event_type, "data": data}
            with self.log_file.open("a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry, default=str) + "\n")
        except Exception as exc:
            logger.warning(
                "Failed to write session log event '%s': %s", event_type, exc
            )


def cleanup_old_logs(root_dir: pathlib.Path) -> int:
    """Delete session log files older than the configured retention period.

    Scans ``{root_dir}/{docs_dir}/{logs_dir}`` for ``.jsonl`` files whose
    filename starts with an ISO-8601 date-time prefix
    (``YYYY-MM-DDTHH-MM-SS``).  Files older than ``log_retention_days`` are
    removed.  Files with an unrecognised name format are silently skipped.

    Args:
        root_dir: Workspace root used to resolve the log directory.

    Returns:
        The number of log files that were successfully deleted.
    """
    cfg = get_config()
    log_dir = root_dir / cfg.docs_dir / cfg.logs_dir
    if not log_dir.is_dir():
        return 0

    retention = datetime.timedelta(days=cfg.log_retention_days)
    cutoff = datetime.datetime.now(datetime.UTC) - retention
    deleted = 0

    for log_file in log_dir.glob("*.jsonl"):
        # Parse date prefix: YYYY-MM-DDTHH-MM-SS
        name = log_file.stem
        date_prefix = name[:19]  # "2026-02-19T16-30-00"
        try:
            file_time = datetime.datetime.strptime(
                date_prefix, "%Y-%m-%dT%H-%M-%S"
            ).replace(tzinfo=datetime.UTC)
        except ValueError:
            continue

        if file_time < cutoff:
            try:
                log_file.unlink()
                deleted += 1
            except OSError as exc:
                logger.warning("Failed to delete old log %s: %s", log_file, exc)

    if deleted:
        logger.info("Cleaned up %d old log file(s) from %s", deleted, log_dir)
    return deleted
