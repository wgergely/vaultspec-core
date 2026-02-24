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
import uuid
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
    """Create a real ClaudeSDKClient from the given options.

    Args:
        options: A ``ClaudeAgentOptions`` instance used to configure the client.

    Returns:
        A new ``ClaudeSDKClient`` instance.
    """
    return ClaudeSDKClient(options)


def _default_options_factory(**kwargs: Any) -> ClaudeAgentOptions:
    """Create a real ``ClaudeAgentOptions`` from the given keyword arguments.

    Args:
        **kwargs: Option fields forwarded directly to ``ClaudeAgentOptions``.

    Returns:
        A new ``ClaudeAgentOptions`` instance.
    """
    return ClaudeAgentOptions(**kwargs)


def _is_rate_limit_parse_error(exc: MessageParseError) -> bool:
    """Return True if a ``MessageParseError`` looks rate-limit-related.

    Args:
        exc: The parse error raised by the SDK.

    Returns:
        True if the stringified exception contains ``"rate_limit"``.
    """
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
        """Initialise the executor with SDK configuration and DI overrides.

        Args:
            model: Claude model identifier (e.g. ``ClaudeModels.MEDIUM``).
            root_dir: Workspace root directory for the agent subprocess.
            mode: Sandboxing mode — ``"read-only"`` or ``"read-write"``.
            mcp_servers: Optional MCP server configs forwarded to the SDK.
            system_prompt: Optional system prompt prepended to every conversation.
            client_factory: Callable ``(options) -> client``.  Defaults to
                ``_default_client_factory``.
            options_factory: Callable ``(**kwargs) -> options``.  Defaults to
                ``_default_options_factory``.
            max_retries: Maximum retries on rate-limit errors before failing.
            retry_base_delay: Base delay in seconds for exponential back-off.
        """
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

    async def _disconnect_sdk_client(self, sdk_client: Any) -> None:
        """Disconnect the SDK client and explicitly clean up its subprocess transports."""
        if sdk_client is None:
            return
        proc = getattr(sdk_client, "_process", None)
        try:
            res = sdk_client.disconnect()
            if asyncio.iscoroutine(res) or hasattr(res, "__await__"):
                await res
        except Exception:
            logger.exception("Error disconnecting SDK client")
        if proc is not None:
            from ....orchestration.utils import cleanup_subprocess_transports
            await cleanup_subprocess_transports(proc)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        """Execute an A2A task by streaming a Claude SDK conversation.

        Connects to the Claude SDK, sends the user prompt, and streams
        assistant content back as A2A task lifecycle events.  Implements
        exponential back-off retry on rate-limit errors.

        Args:
            context: The A2A request context carrying the task ID, context ID,
                and user input prompt.
            event_queue: The A2A event queue used to emit status updates,
                artifacts, and terminal events.
        """
        task_id = context.task_id or ""
        context_id = context.context_id or ""
        updater = TaskUpdater(event_queue, task_id, context_id)
        prompt = context.get_user_input()

        logger.info(
            "ClaudeA2AExecutor executing task %s (context=%s, model=%s, prompt_len=%d)",
            task_id,
            context_id,
            self._model,
            len(prompt),
        )

        cancel_event = asyncio.Event()
        self._cancel_events[task_id] = cancel_event

        # Check for a live persistent client from a previous turn on this context.
        async with self._clients_lock:
            existing_client = self._active_clients.get(context_id)

        if existing_client is not None:
            sdk_client = existing_client
            logger.debug(
                "Reusing persistent SDK client for context %s (task %s)",
                context_id,
                task_id,
            )
            # Register under task_id so cancel() can interrupt it.
            async with self._clients_lock:
                self._active_clients[task_id] = sdk_client
        else:
            sandbox_cb = _make_sandbox_callback(self._mode, self._root_dir)
            # The SDK merges options.env ON TOP of os.environ:
            #   process_env = {**os.environ, **options.env, "CLAUDE_...": ..}
            # Simply omitting CLAUDECODE from options.env is not enough — the parent
            # value from os.environ would survive the merge.  Setting it to "" (empty
            # string) overrides the parent value; the Claude CLI treats an empty
            # CLAUDECODE as falsy and allows the subprocess to start normally.
            sdk_env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE"}
            sdk_env["CLAUDECODE"] = ""  # empty string overrides parent "1" in SDK merge
            kwargs: dict[str, Any] = {
                "model": self._model,
                "cwd": self._root_dir,
                "mcp_servers": self._mcp_servers,
                "can_use_tool": sandbox_cb,
                "permission_mode": "bypassPermissions",
                "system_prompt": self._system_prompt,
                "env": sdk_env,
            }
            if self._cli_path:
                kwargs["cli_path"] = self._cli_path

            # Session resume: reuse session_id from a previous execution on the
            # same context_id so the SDK can restore conversation state.
            async with self._session_ids_lock:
                prev_session = self._session_ids.get(context_id)
            if prev_session:
                kwargs["resume"] = prev_session
                logger.debug(
                    "Resuming session %s for context %s", prev_session, context_id
                )

            options = self._options_factory(**kwargs)
            sdk_client = self._client_factory(options)
            async with self._clients_lock:
                self._active_clients[task_id] = sdk_client

        cancelled = False
        errored = False
        try:
            if existing_client is None:
                logger.debug("Connecting SDK client for task %s", task_id)
                await sdk_client.connect()
                logger.debug("SDK client connected for task %s", task_id)

            # Only signal working after the subprocess is confirmed started —
            # avoids a window where the task appears working but connect failed.
            await updater.start_work()

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
            errored = True
            logger.exception("ClaudeA2AExecutor error for task %s", task_id)
            await updater.failed(
                message=updater.new_agent_message(
                    parts=[Part(root=TextPart(text=str(e)))]
                )
            )
        finally:
            if cancelled:
                # Cancelled: keep the client alive under context_id for future resume.
                # Remove the task_id entry but store the client under context_id.
                async with self._clients_lock:
                    self._active_clients.pop(task_id, None)
                    self._active_clients[context_id] = sdk_client
                logger.debug(
                    "Task %s cancelled: keeping SDK client alive for context %s",
                    task_id,
                    context_id,
                )
            elif errored:
                # Error path: disconnect and evict so the next attempt starts fresh.
                async with self._clients_lock:
                    self._active_clients.pop(task_id, None)
                    if self._active_clients.get(context_id) is sdk_client:
                        self._active_clients.pop(context_id, None)
                logger.debug(
                    "Disconnecting SDK client for task %s after error", task_id
                )
                await self._disconnect_sdk_client(sdk_client)
            else:
                # Successful completion: persist the live client under context_id
                # so the next turn can reuse it without reconnecting.
                async with self._clients_lock:
                    self._active_clients.pop(task_id, None)
                    self._active_clients[context_id] = sdk_client
                    logger.debug(
                        "Persisting SDK client for context %s after task %s completion",
                        context_id,
                        task_id,
                    )
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

        Args:
            sdk_client: Connected Claude SDK client used to send the prompt
                and stream the response.
            prompt: The user-facing prompt text to send.
            updater: Task updater used to emit status and artifact events.
            context_id: A2A context identifier for the current task.
            cancel_event: Asyncio event; when set the stream loop exits early.

        Returns:
            True if the caller should retry (rate-limit hit), False
            otherwise (task completed, failed, or cancelled).
        """
        await sdk_client.query(prompt)
        # Fixed artifact_id for this stream: all append=True chunks and the
        # final last_chunk=True emit share the same ID so the client assembles
        # them into one artifact object.
        artifact_id = str(uuid.uuid4())
        collected: list[str] = []
        chunk_emitted = False
        last_chunk_time = 0.0

        try:
            async for msg in sdk_client.receive_response():
                if cancel_event.is_set():
                    return False

                if isinstance(msg, AssistantMessage):
                    if msg.error and "rate_limit" in str(msg.error).lower():
                        return True

                    new_text = ""
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            collected.append(block.text)
                            new_text += block.text

                    # Throttled incremental artifact chunks (append=True).
                    now = time.monotonic()
                    if now - last_chunk_time >= _STATUS_THROTTLE_SECS and new_text:
                        await updater.add_artifact(
                            parts=[Part(root=TextPart(text=new_text))],
                            artifact_id=artifact_id,
                            name="response",
                            append=chunk_emitted,
                            last_chunk=False,
                        )
                        chunk_emitted = True
                        last_chunk_time = now

                elif isinstance(msg, ResultMessage):
                    logger.debug(
                        "ResultMessage for context %s (error=%s, session_id=%s)",
                        context_id,
                        msg.is_error,
                        msg.session_id,
                    )
                    # Persist session_id for future resume.
                    if msg.session_id:
                        async with self._session_ids_lock:
                            self._session_ids[context_id] = msg.session_id
                        logger.debug(
                            "Persisted session_id %s for context %s",
                            msg.session_id,
                            context_id,
                        )

                    text = "".join(collected) or msg.result or ""
                    if text:
                        await updater.add_artifact(
                            parts=[Part(root=TextPart(text=text))],
                            artifact_id=artifact_id,
                            name="response",
                            append=chunk_emitted,
                            last_chunk=True,
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
        logger.warning("Task %s: stream ended without ResultMessage", context_id)
        text = "".join(collected)
        if text:
            await updater.add_artifact(
                parts=[Part(root=TextPart(text=text))],
                artifact_id=artifact_id,
                name="response",
                append=chunk_emitted,
                last_chunk=True,
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
        """Cancel a running A2A task.

        Sets the cancel event so the streaming loop terminates at the next
        iteration, then interrupts the SDK client without disconnecting it so
        the session can be resumed later.

        Only emits the ``TaskState.canceled`` terminal event when the task is
        actually in flight (i.e. its cancel_event was registered by execute()).
        This prevents duplicate terminal-state events when cancel() races with
        a naturally completing execute().

        Args:
            context: The A2A request context carrying the task ID to cancel.
            event_queue: The A2A event queue used to emit the cancelled status.
        """
        task_id = context.task_id or ""
        context_id = context.context_id or ""

        # Signal the streaming loop to break.  cancel_event is present only
        # while execute() is in flight — if it's absent the task has already
        # reached a terminal state and we must not emit a second one.
        cancel_event = self._cancel_events.get(task_id)
        in_flight = cancel_event is not None
        if cancel_event is not None:
            cancel_event.set()

        # Interrupt the SDK client but do NOT disconnect or remove it — the
        # execute() finally block will skip cleanup when it sees the cancel.
        async with self._clients_lock:
            client = self._active_clients.get(task_id)
        if client is not None:
            try:
                await client.interrupt()
            except Exception:
                logger.exception("Error interrupting SDK client for task %s", task_id)

        if in_flight:
            updater = TaskUpdater(event_queue, task_id, context_id)
            await updater.cancel()

    async def cleanup(self) -> None:
        """Disconnect all persistent SDK clients.

        Call this on server shutdown to cleanly terminate any Claude subprocesses
        kept alive for multi-turn resume.
        """
        async with self._clients_lock:
            clients = list(self._active_clients.values())
            self._active_clients.clear()
        for client in clients:
            try:
                await self._disconnect_sdk_client(client)
            except Exception:
                logger.exception("Error disconnecting SDK client during cleanup")
