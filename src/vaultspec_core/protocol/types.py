"""Typed execution results and protocol-level failure contracts.

These types model the immutable outputs returned by execution providers and the
error semantics used when a provider cannot produce a valid execution result.
They define the stable contract shared across provider implementations.
"""

from __future__ import annotations

import dataclasses


@dataclasses.dataclass(frozen=True)
class ExecutionResult:
    """Immutable return value from execution.

    Attributes:
        response_text: The main text response from the model.
        written_files: List of absolute paths to files created or modified.
        session_id: An opaque identifier for the conversation session,
            allowing stateful continuation. This should be passed to a
            subsequent execution call to resume the conversation.
    """

    response_text: str
    written_files: list[str] = dataclasses.field(default_factory=list)
    session_id: str | None = None


class ExecutionError(Exception):
    """Raised when an execution provider fails to process a request."""
