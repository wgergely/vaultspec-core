"""Shared types for the ACP subagent protocol."""

from __future__ import annotations

import dataclasses

__all__ = ["SubagentError", "SubagentResult"]


class SubagentError(Exception):
    """Raised when subagent execution fails."""

    pass


@dataclasses.dataclass(frozen=True)
class SubagentResult:
    """Immutable return value from ``run_subagent()``.

    Attributes:
        response_text: The full text response produced by the agent.
        written_files: Paths of files written during the session, as reported
            by the ACP client.
        session_id: Optional session identifier that can be passed to a
            subsequent ``run_subagent()`` call to resume the conversation.
    """

    response_text: str
    written_files: list[str] = dataclasses.field(default_factory=list)
    session_id: str | None = None
