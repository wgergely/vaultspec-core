"""A2A AgentExecutor wrapping claude-agent-sdk.

Bridges A2A task model -> Claude SDK streaming conversation model.
Reuses sandboxing logic from protocol.a2a.executors.base.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import shutil
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.tasks import TaskUpdater
from a2a.types import Part, TaskState, TextPart
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

# Minimum interval between status updates to avoid flooding the event queue.
_STATUS_THROTTLE_SECS = 0.25


def _default_client_factory(options: Any) -> ClaudeSDKClient:
    """Default factory: create a real ClaudeSDKClient."""
    return ClaudeSDKClient(options)


def _default_options_factory(**kwargs: Any) -> ClaudeAgentOptions:
    """Default factory: create real ClaudeAgentOptions."""
    return ClaudeAgentOptions(**kwargs)


def _is_rate_limit_parse_error(exc: MessageParseError) -> bool:
    """Return True if a MessageParseError looks rate-limit-related."""
    return "rate_limit" in str(exc).lower()


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
    max_retries:
        Maximum number of retries on rate-limit errors before failing.
    retry_base_delay:
        Base delay in seconds for exponential back-off between retries.
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
        max_retries: int = 3,
        retry_base_delay: float = 1.0,
    ) -> None:
        self._model = model
        self._root_dir = root_dir
        self._mode = mode
        self._mcp_servers = mcp_servers or {}
        self._system_prompt = system_prompt
        self._client_factory = client_factory or _default_client_factory
        self._options_factory = options_factory or _default_options_factory
        self._max_retries = max_retries
        self._retry_base_delay = retry_base_delay
        self._active_clients: dict[str, Any] = {}
        self._clients_lock = asyncio.Lock()
        self._cli_path: str | None = shutil.which("claude")
        self._session_ids: dict[str, str] = {}
        self._session_ids_lock = asyncio.Lock()
        self._cancel_events: dict[str, asyncio.Event] = {}

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)
        prompt = context.get_user_input()

        await updater.start_work()

        cancel_event = asyncio.Event()
        self._cancel_events[task_id] = cancel_event

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

        # Session resume: reuse session_id from a previous execution on the
        # same context_id so the SDK can restore conversation state.
        async with self._session_ids_lock:
            prev_session = self._session_ids.get(context_id)
        if prev_session:
            kwargs["resume"] = prev_session

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

        cancelled = False
        try:
            await sdk_client.connect()

            attempt = 0
            while True:
                should_retry = await self._run_stream(
                    sdk_client=sdk_client,
                    prompt=prompt,
                    updater=updater,
                    context_id=context_id,
                    cancel_event=cancel_event,
                )
                if cancel_event.is_set():
                    cancelled = True
                    # The stream may have already completed before the
                    # cancel event was observed — guard against duplicate
                    # terminal state.
                    with contextlib.suppress(RuntimeError):
                        await updater.cancel()
                    break
                if not should_retry:
                    break

                # Rate-limit retry with exponential back-off.
                attempt += 1
                if attempt > self._max_retries:
                    await updater.failed(
                        message=updater.new_agent_message(
                            parts=[
                                Part(
                                    root=TextPart(
                                        text=(
                                            "Rate limited: exhausted "
                                            f"{self._max_retries} retries"
                                        )
                                    )
                                )
                            ]
                        )
                    )
                    break
                delay = self._retry_base_delay * (2**attempt)
                await updater.update_status(
                    TaskState.working,
                    message=updater.new_agent_message(
                        parts=[
                            Part(
                                root=TextPart(
                                    text=(
                                        f"Rate limited, retrying "
                                        f"(attempt {attempt}"
                                        f"/{self._max_retries})"
                                    )
                                )
                            )
                        ]
                    ),
                )
                logger.info(
                    "Rate limited on task %s, retrying in %.1fs (attempt %d/%d)",
                    task_id,
                    delay,
                    attempt,
                    self._max_retries,
                )
                await asyncio.sleep(delay)

        except Exception as e:
            logger.exception("ClaudeA2AExecutor error for task %s", task_id)
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[Part(root=TextPart(text=str(e)))]
                )
            )
        finally:
            # Only disconnect and remove from active clients when NOT
            # cancelled — cancel() leaves the client alive so the SDK
            # session can be resumed later.
            if not cancelled:
                await sdk_client.disconnect()
                async with self._clients_lock:
                    self._active_clients.pop(task_id, None)
            self._cancel_events.pop(task_id, None)

    async def _run_stream(
        self,
        *,
        sdk_client: Any,
        prompt: str,
        updater: TaskUpdater,
        context_id: str,
        cancel_event: asyncio.Event,
    ) -> bool:
        """Execute one query+stream cycle.

        Returns True if the caller should retry (rate-limit hit), False
        otherwise (task completed, failed, or cancelled).
        """
        await sdk_client.query(prompt)
        collected: list[str] = []
        last_status_time = 0.0

        try:
            async for msg in sdk_client.receive_response():
                if cancel_event.is_set():
                    return False

                if isinstance(msg, AssistantMessage):
                    if msg.error == "rate_limit":
                        return True

                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            collected.append(block.text)

                    # Throttled streaming progress updates.
                    now = time.monotonic()
                    if now - last_status_time >= _STATUS_THROTTLE_SECS and collected:
                        await updater.update_status(
                            TaskState.working,
                            message=updater.new_agent_message(
                                parts=[Part(root=TextPart(text="".join(collected)))]
                            ),
                        )
                        last_status_time = now

                elif isinstance(msg, ResultMessage):
                    # Persist session_id for future resume.
                    if msg.session_id:
                        async with self._session_ids_lock:
                            self._session_ids[context_id] = msg.session_id

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
                    return False

        except MessageParseError as exc:
            # Belt-and-suspenders: the SDK now handles rate_limit_event
            # natively, but if an unparseable message still slips through
            # we check whether it looks rate-limit-related.
            logger.debug("Skipping unparseable SDK message: %s", exc)
            if _is_rate_limit_parse_error(exc):
                return True

        # Stream ended without a ResultMessage — fall back to collected text.
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
                    parts=[Part(root=TextPart(text="Stream ended without result"))]
                )
            )
        return False

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)

        # Signal the streaming loop to break.
        cancel_event = self._cancel_events.get(task_id)
        if cancel_event is not None:
            cancel_event.set()

        # Interrupt the SDK client but do NOT disconnect or remove it — the
        # execute() finally block will skip cleanup when it sees the cancel.
        async with self._clients_lock:
            client = self._active_clients.get(task_id)
        if client is not None:
            try:
                client.interrupt()
            except Exception:
                logger.exception("Error interrupting SDK client for task %s", task_id)

        await updater.cancel()
