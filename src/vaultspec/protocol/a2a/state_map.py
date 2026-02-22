"""Bidirectional lookup tables: vaultspec TaskEngine states <-> A2A TaskState values.

``VAULTSPEC_TO_A2A`` maps internal status strings (e.g. ``"pending"``) to the
corresponding :class:`a2a.types.TaskState` enum values used by the A2A protocol.
``A2A_TO_VAULTSPEC`` maps inbound A2A states back to internal strings, with
edge-case states (``rejected``, ``auth_required``, ``unknown``) coerced to the
nearest vaultspec equivalent.
"""

from a2a.types import TaskState

__all__ = ["A2A_TO_VAULTSPEC", "VAULTSPEC_TO_A2A"]

# Vaultspec TaskEngine -> A2A
VAULTSPEC_TO_A2A: dict[str, TaskState] = {
    "pending": TaskState.submitted,
    "working": TaskState.working,
    "input_required": TaskState.input_required,
    "completed": TaskState.completed,
    "failed": TaskState.failed,
    "cancelled": TaskState.canceled,  # British -> American
}

# A2A -> Vaultspec TaskEngine
A2A_TO_VAULTSPEC: dict[TaskState, str] = {
    TaskState.submitted: "pending",
    TaskState.working: "working",
    TaskState.input_required: "input_required",
    TaskState.completed: "completed",
    TaskState.failed: "failed",
    TaskState.canceled: "cancelled",
    TaskState.rejected: "failed",  # Map rejection to failure
    TaskState.auth_required: "input_required",  # Auth = needs input
    TaskState.unknown: "failed",  # Unknown = failure
}
