"""Shared constants for the orchestration / dispatch framework."""

from __future__ import annotations

__all__ = ["READONLY_PERMISSION_PROMPT"]

READONLY_PERMISSION_PROMPT = (
    "PERMISSION MODE: READ-ONLY\n"
    "You MUST only write files within the `.vault/` directory. "
    "Do not modify any source code files.\n\n"
)
