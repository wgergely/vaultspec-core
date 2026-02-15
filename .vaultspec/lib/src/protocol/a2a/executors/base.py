"""Base executor utilities shared across A2A executors.

Re-exports sandbox logic from ``protocol.sandbox`` (the single source of
truth) for convenient import by ``ClaudeA2AExecutor`` and
``GeminiA2AExecutor``.
"""

from protocol.sandbox import (
    _SHELL_TOOLS,
    _WRITE_TOOLS,
    _is_vault_path,
    _make_sandbox_callback,
)

__all__ = [
    "_SHELL_TOOLS",
    "_WRITE_TOOLS",
    "_is_vault_path",
    "_make_sandbox_callback",
]
