"""A2A AgentExecutor wrapping claude-agent-sdk.

Bridges A2A task model -> Claude SDK streaming conversation model.
Reuses sandboxing logic from protocol.a2a.executors.base.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

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
from claude_agent_sdk._errors import MessageParseError

from .base import _make_sandbox_callback

if TYPE_CHECKING:
    from a2a.server.events import EventQueue

logger = logging.getLogger(__name__)

__all__ = ["ClaudeA2AExecutor"]


def _default_client_factory(options: Any) -> ClaudeSDKClient:
    """Default factory: create a real ClaudeSDKClient."""
    return ClaudeSDKClient(options)


def _default_options_factory(**kwargs: Any) -> ClaudeAgentOptions:
    """Default factory: create real ClaudeAgentOptions."""
    return ClaudeAgentOptions(**kwargs)


class ClaudeA2AExecutor(AgentExecutor):
    """Execute A2A tasks by delegating to Claude via ``claude-agent-sdk``.

    Parameters
    ----------
    model:
        Claude model identifier (e.g. ``ClaudeModels.MEDIUM``).
    root_dir:
        Workspace root directory for the agent.
    mode:
        Sandboxing mode: ``"read-only"`` or ``"read-write"``.
    mcp_servers:
        Optional dict of MCP server configurations to pass to the SDK.
    system_prompt:
        Optional system prompt prepended to every conversation.
    client_factory:
        Callable ``(options) -> client``.  Defaults to real
        ``ClaudeSDKClient``.  Override in tests to inject a test double.
    options_factory:
        Callable ``(**kwargs) -> options``.  Defaults to real
        ``ClaudeAgentOptions``.  Override in tests to record kwargs.
    """

    def __init__(
        self,
        *,
        model: str,
        root_dir: str,
        mode: str = "read-only",
        mcp_servers: dict[str, Any] | None = None,
        system_prompt: str | None = None,
        client_factory: Callable[..., Any] | None = None,
        options_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._model = model
        self._root_dir = root_dir
        self._mode = mode
        self._mcp_servers = mcp_servers or {}
        self._system_prompt = system_prompt
        self._client_factory = client_factory or _default_client_factory
        self._options_factory = options_factory or _default_options_factory
        self._active_clients: dict[str, Any] = {}
        self._clients_lock = asyncio.Lock()
        self._cli_path: str | None = shutil.which("claude")

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)
        prompt = context.get_user_input()

        await updater.start_work()

        sandbox_cb = _make_sandbox_callback(self._mode, self._root_dir)
        kwargs: dict[str, Any] = {
            "model": self._model,
            "cwd": self._root_dir,
            "mcp_servers": self._mcp_servers,
            "can_use_tool": sandbox_cb,
            "permission_mode": "bypassPermissions",
            "system_prompt": self._system_prompt,
        }
        if self._cli_path:
            kwargs["cli_path"] = self._cli_path
        options = self._options_factory(**kwargs)
        sdk_client = self._client_factory(options)
        async with self._clients_lock:
            self._active_clients[task_id] = sdk_client

        # Build a clean env for the SDK subprocess — strip CLAUDECODE so the
        # child claude process doesn't refuse to start inside an existing
        # Claude Code session.  We use a copy to avoid thread-unsafe mutation
        # of os.environ when multiple executors run concurrently.
        sdk_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
        options.env = sdk_env
        try:
            await sdk_client.connect()
            await sdk_client.query(prompt)
            collected: list[str] = []

            _stream = sdk_client.receive_messages().__aiter__()
            _finalised = False
            while True:
                try:
                    msg = await _stream.__anext__()
                except StopAsyncIteration:
                    break
                except MessageParseError as exc:
                    logger.debug("Skipping unparseable SDK message: %s", exc)
                    continue
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
                    _finalised = True
                    break
            if not _finalised:
                # Stream ended without a ResultMessage. This is expected
                # when the CLI emits events the SDK can't parse (e.g.
                # rate_limit_event) — the stream dies but the response
                # text was already collected.
                text = "".join(collected)
                if text:
                    await updater.add_artifact(
                        parts=[Part(root=TextPart(text=text))],
                        name="response",
                    )
                    await updater.complete(
                        message=updater.new_agent_message(
                            parts=[Part(root=TextPart(text=text))]
                        )
                    )
                else:
                    await updater.failed(
                        message=updater.new_agent_message(
                            parts=[
                                Part(root=TextPart(text="Stream ended without result"))
                            ]
                        )
                    )
        except Exception as e:
            logger.exception("ClaudeA2AExecutor error for task %s", task_id)
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[Part(root=TextPart(text=str(e)))]
                )
            )
        finally:
            await sdk_client.disconnect()
            async with self._clients_lock:
                self._active_clients.pop(task_id, None)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)
        async with self._clients_lock:
            client = self._active_clients.pop(task_id, None)
        if client is not None:
            try:
                client.interrupt()
            except Exception:
                logger.exception("Error interrupting SDK client for task %s", task_id)
            try:
                await client.disconnect()
            except Exception:
                logger.exception("Error disconnecting SDK client for task %s", task_id)
        await updater.cancel()
