"""Centralized session logging for agent orchestration.

Writes structured JSONL events to the vault logs directory.
"""

from __future__ import annotations

import datetime
import json
import logging
import uuid
from typing import TYPE_CHECKING, Any

from core.config import get_config

if TYPE_CHECKING:
    import pathlib

logger = logging.getLogger(__name__)


class SessionLogger:
    """Handles persistent logging of agent session events to disk.

    Log files use the naming convention:
        {YYYY-MM-DDTHH-MM-SS}_{agent_name}_{task_id_short}.jsonl
    """

    def __init__(
        self,
        root_dir: pathlib.Path,
        agent_name: str = "unknown",
        task_id: str | None = None,
    ):
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
        """Workspace-relative path to the log file."""
        try:
            return self.log_file.relative_to(self._root_dir).as_posix()
        except ValueError:
            return self.log_file.as_posix()

    def log(self, event_type: str, data: Any) -> None:
        """Append a structured JSONL event to the log file."""
        timestamp = datetime.datetime.now(datetime.UTC).isoformat()
        log_entry = {"timestamp": timestamp, "type": event_type, "data": data}
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")


def cleanup_old_logs(root_dir: pathlib.Path) -> int:
    """Delete session log files older than the configured retention period.

    Scans ``{root_dir}/{docs_dir}/{logs_dir}`` for ``.jsonl`` files whose
    filename starts with an ISO-8601 date-time prefix
    (``YYYY-MM-DDTHH-MM-SS``).  Files older than ``log_retention_days`` are
    removed.

    Returns the number of files deleted.
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
