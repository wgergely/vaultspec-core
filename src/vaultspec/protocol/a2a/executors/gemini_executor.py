"""A2A AgentExecutor wrapping the Gemini CLI over A2A.

This is a stub, as Gemini natively speaks A2A and no longer needs an ACP bridge wrapper.
"""

from __future__ import annotations

import asyncio
import logging

from .base import BaseA2AExecutor

logger = logging.getLogger(__name__)

__all__ = ["GeminiA2AExecutor"]


class GeminiA2AExecutor(BaseA2AExecutor):
    """Stubbed executor since Gemini natively speaks A2A."""

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(max_retries=3, retry_base_delay=1.0)
        raise NotImplementedError("Gemini natively speaks A2A; wrapper is deprecated.")

    async def _on_task_start(
        self, task_id: str, context_id: str, cancel_event: asyncio.Event
    ) -> None:
        pass

    async def _on_task_end(
        self, task_id: str, context_id: str, cancelled: bool, errored: bool
    ) -> None:
        pass

    async def _on_task_cancel(self, task_id: str, context_id: str) -> None:
        pass

    async def _on_cleanup(self) -> None:
        pass

    async def _run_stream(self, *args, **kwargs) -> bool:
        return False
