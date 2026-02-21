"""Bidirectional mapping between TaskEngine states and A2A TaskState."""

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
