"""A2A AgentExecutor wrapping Gemini via existing ACP subprocess.

Uses run_subagent() to delegate to GeminiProvider's ACP flow,
mapping results back to A2A events.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart

from orchestration.subagent import run_subagent as _default_run_subagent
from protocol.providers.base import GeminiModels

if TYPE_CHECKING:
    import pathlib

    from a2a.server.events import EventQueue


class GeminiA2AExecutor(AgentExecutor):
    """A2A executor that delegates to Gemini via the existing ACP subprocess flow.

    Wraps ``run_subagent()`` from ``orchestration.subagent``, mapping the
    ``SubagentResult`` back to A2A task lifecycle events.

    Parameters
    ----------
    root_dir:
        Workspace root for the agent subprocess.
    model:
        Gemini model identifier.
    agent_name:
        Name of the agent definition to load.
    run_subagent:
        Callable to spawn the subagent.  Defaults to the real
        ``orchestration.subagent.run_subagent``.  Override in tests to
        inject a test implementation via constructor DI.
    """

    def __init__(
        self,
        *,
        root_dir: pathlib.Path,
        model: str = GeminiModels.LOW,
        agent_name: str = "researcher",
        run_subagent: Callable[..., Any] | None = None,
    ) -> None:
        self._root_dir = root_dir
        self._model = model
        self._agent_name = agent_name
        self._run_subagent = run_subagent or _default_run_subagent

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)
        prompt = context.get_user_input()

        await updater.start_work()

        try:
            result = await self._run_subagent(
                agent_name=self._agent_name,
                root_dir=self._root_dir,
                initial_task=prompt,
                model_override=self._model,
            )
            text = result.response_text or ""
            if text:
                await updater.add_artifact(
                    parts=[Part(root=TextPart(text=text))],
                    name="response",
                )
            await updater.complete(
                message=updater.new_agent_message(
                    parts=[Part(root=TextPart(text=text or "Done"))]
                )
            )
        except Exception as e:
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[Part(root=TextPart(text=str(e)))]
                )
            )

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)
        await updater.cancel()
