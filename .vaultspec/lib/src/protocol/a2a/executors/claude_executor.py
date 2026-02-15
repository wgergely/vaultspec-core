"""A2A AgentExecutor wrapping claude-agent-sdk.

Bridges A2A task model -> Claude SDK streaming conversation model.
Reuses sandboxing logic from protocol.a2a.executors.base.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TextPart
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    TextBlock,
)

from protocol.a2a.executors.base import _make_sandbox_callback

if TYPE_CHECKING:
    from a2a.server.events import EventQueue

logger = logging.getLogger(__name__)


class ClaudeA2AExecutor(AgentExecutor):
    """Execute A2A tasks by delegating to Claude via ``claude-agent-sdk``.

    Parameters
    ----------
    model:
        Claude model identifier (e.g. ``"claude-sonnet-4-5"``).
    root_dir:
        Workspace root directory for the agent.
    mode:
        Sandboxing mode: ``"read-only"`` or ``"read-write"``.
    mcp_servers:
        Optional dict of MCP server configurations to pass to the SDK.
    system_prompt:
        Optional system prompt prepended to every conversation.
    """

    def __init__(
        self,
        *,
        model: str,
        root_dir: str,
        mode: str = "read-only",
        mcp_servers: dict[str, Any] | None = None,
        system_prompt: str | None = None,
    ) -> None:
        self._model = model
        self._root_dir = root_dir
        self._mode = mode
        self._mcp_servers = mcp_servers or {}
        self._system_prompt = system_prompt
        self._active_clients: dict[str, ClaudeSDKClient] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)
        prompt = context.get_user_input()

        await updater.start_work()

        sandbox_cb = _make_sandbox_callback(self._mode, self._root_dir)
        sdk_client = ClaudeSDKClient(
            ClaudeAgentOptions(
                model=self._model,
                cwd=self._root_dir,
                mcp_servers=self._mcp_servers,
                can_use_tool=sandbox_cb,
                permission_mode="bypassPermissions",
                system_prompt=self._system_prompt,
            )
        )
        self._active_clients[task_id] = sdk_client

        try:
            await sdk_client.connect()
            await sdk_client.query(prompt)
            collected: list[str] = []

            async for msg in sdk_client.receive_messages():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            collected.append(block.text)
                elif isinstance(msg, ResultMessage):
                    text = "".join(collected) or msg.result or ""
                    if text:
                        await updater.add_artifact(
                            parts=[Part(root=TextPart(text=text))],
                            name="response",
                        )
                    if msg.is_error:
                        await updater.failed(
                            message=updater.new_agent_message(
                                parts=[Part(root=TextPart(text=text))]
                            )
                        )
                    else:
                        await updater.complete(
                            message=updater.new_agent_message(
                                parts=[Part(root=TextPart(text=text))]
                            )
                        )
                    break
        except Exception as e:
            logger.exception("ClaudeA2AExecutor error for task %s", task_id)
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[Part(root=TextPart(text=str(e)))]
                )
            )
        finally:
            await sdk_client.disconnect()
            self._active_clients.pop(task_id, None)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)
        client = self._active_clients.pop(task_id, None)
        if client is not None:
            try:
                client.interrupt()
            except Exception:
                logger.exception("Error interrupting SDK client for task %s", task_id)
            try:
                client.disconnect()
            except Exception:
                logger.exception("Error disconnecting SDK client for task %s", task_id)
        await updater.cancel()
