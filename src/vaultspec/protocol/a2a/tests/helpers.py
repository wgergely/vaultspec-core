"""Shared test helpers for A2A protocol tests.

Contains reusable executor implementations and request-context builders
that are shared between conftest fixtures and direct test imports.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart

if TYPE_CHECKING:
    from a2a.server.events import EventQueue


class EchoExecutor(AgentExecutor):
    """Echoes input back as completed task."""

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id is not None
        assert context.context_id is not None
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        text = context.get_user_input()
        await updater.start_work()
        await updater.complete(
            message=updater.new_agent_message(
                parts=[Part(root=TextPart(text=f"Echo: {text}"))]
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id is not None
        assert context.context_id is not None
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()


class PrefixExecutor(AgentExecutor):
    """Prepends a prefix to input text."""

    def __init__(self, prefix: str) -> None:
        self._prefix = prefix

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id is not None
        assert context.context_id is not None
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        text = context.get_user_input()
        await updater.start_work()
        await updater.complete(
            message=updater.new_agent_message(
                parts=[Part(root=TextPart(text=f"{self._prefix}{text}"))]
            )
        )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        assert context.task_id is not None
        assert context.context_id is not None
        updater = TaskUpdater(event_queue, context.task_id, context.context_id)
        await updater.cancel()
