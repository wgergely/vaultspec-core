from __future__ import annotations

import dataclasses

class SecurityError(Exception):
    """Raised when a path access violates workspace boundaries."""
    pass


class DispatchError(Exception):
    """Raised when agent dispatch fails."""
    pass


@dataclasses.dataclass(frozen=True)
class DispatchResult:
    """Return value from run_dispatch() containing response text and file write log."""

    response_text: str
    written_files: list[str] = dataclasses.field(default_factory=list)
    session_id: str | None = None
