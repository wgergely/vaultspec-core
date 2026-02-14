from __future__ import annotations

import dataclasses


class SubagentError(Exception):
    """Raised when subagent execution fails."""

    pass


@dataclasses.dataclass(frozen=True)
class SubagentResult:
    """Return value from run_subagent() containing response text and file write log."""

    response_text: str
    written_files: list[str] = dataclasses.field(default_factory=list)
    session_id: str | None = None
