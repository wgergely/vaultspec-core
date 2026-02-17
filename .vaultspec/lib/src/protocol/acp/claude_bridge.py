"""ACP bridge server that wraps claude-agent-sdk.

This module is the ACP server process spawned by ``ClaudeProvider``.  It
implements the ACP ``Agent`` protocol interface and uses
``AgentSideConnection`` from the ``acp`` package for JSON-RPC framing over
stdin/stdout.  Internally it drives Claude via ``claude-agent-sdk``'s
``ClaudeSDKClient``.

Usage::

    python -m protocol.acp.claude_bridge --model ClaudeModels.MEDIUM

The bridge reads ``VAULTSPEC_AGENT_MODE`` from the environment to decide
sandboxing policy and ``VAULTSPEC_ROOT_DIR`` for the workspace root.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime
import logging
import uuid
from typing import TYPE_CHECKING, Any

from logging_config import configure_logging

if TYPE_CHECKING:
    from collections.abc import Callable

from acp import PROTOCOL_VERSION, run_agent
from acp.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    AgentThoughtChunk,
    AuthenticateResponse,
    ForkSessionResponse,
    Implementation,
    InitializeResponse,
    ListSessionsResponse,
    LoadSessionResponse,
    NewSessionResponse,
    PromptResponse,
    ResumeSessionResponse,
    SessionCapabilities,
    SessionForkCapabilities,
    SessionInfo,
    SessionInfoUpdate,
    SessionListCapabilities,
    SessionResumeCapabilities,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
)
from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    ResultMessage,
    SystemMessage,
    TextBlock,
    ThinkingBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
)
from claude_agent_sdk.types import (
    McpStdioServerConfig,
    StreamEvent,
)

from protocol.providers.base import ClaudeModels
from protocol.sandbox import (
    _make_sandbox_callback,
)

if TYPE_CHECKING:
    from acp.schema import (
        AudioContentBlock,
        ClientCapabilities,
        EmbeddedResourceContentBlock,
        HttpMcpServer,
        ImageContentBlock,
        McpServerStdio,
        ResourceContentBlock,
        SseMcpServer,
    )

logger = logging.getLogger(__name__)


def _convert_mcp_servers(
    acp_servers: list[Any],
) -> dict[str, Any]:
    """Convert ACP ``McpServerStdio`` specs into SDK ``McpStdioServerConfig``.

    ACP sends a *list* of pydantic models or dicts.  The SDK expects a *dict*
    keyed by server name.
    """
    result: dict[str, Any] = {}
    for server in acp_servers:
        # Handle both pydantic models and raw dicts
        if hasattr(server, "model_dump"):
            server = server.model_dump()
        elif not isinstance(server, dict):
            continue

        command = server.get("command")
        if not command:
            continue

        name: str = server.get("name", command)
        config: McpStdioServerConfig = {
            "command": command,
        }
        if server.get("args"):
            config["args"] = server["args"]
        if server.get("env"):
            config["env"] = server["env"]
        result[name] = config
    return result


def _extract_prompt_text(
    prompt: list[
        TextContentBlock
        | ImageContentBlock
        | AudioContentBlock
        | ResourceContentBlock
        | EmbeddedResourceContentBlock
    ],
) -> str:
    """Extract plain text from ACP prompt content blocks."""
    parts = []
    for block in prompt:
        if isinstance(block, TextContentBlock):
            parts.append(block.text)
        elif hasattr(block, "text"):
            parts.append(str(block.text))
    return "\n".join(parts)


@dataclasses.dataclass
class _SessionState:
    """Per-session state tracked by the bridge."""

    session_id: str
    cwd: str
    model: str
    mode: str
    mcp_servers: list[Any]
    created_at: str
    sdk_client: ClaudeSDKClient | None = None
    connected: bool = True


class ClaudeACPBridge:
    """ACP ``Agent`` implementation that wraps ``claude-agent-sdk``.

    This class implements the ``acp.interfaces.Agent`` protocol.  When used
    with ``acp.run_agent()`` or ``AgentSideConnection``, the ACP library
    handles all JSON-RPC framing and method dispatch.

    The lifecycle is:

    1. ``on_connect`` — receives the ``conn`` (``Client`` interface) for
       sending notifications back to the ACP client
    2. ``initialize`` — returns bridge capabilities
    3. ``new_session`` — creates a ``ClaudeSDKClient`` with the requested config
    4. ``prompt`` — sends a prompt, streams SDK events as ACP
       ``session/update`` notifications, returns ``PromptResponse``
    5. ``cancel`` — interrupts the running query
    """

    def __init__(
        self,
        *,
        model: str = ClaudeModels.MEDIUM,
        debug: bool = False,
        # DI: override env-var config (None = read from env)
        mode: str | None = None,
        max_turns: int | None = None,
        budget_usd: float | None = None,
        allowed_tools: list[str] | None = None,
        disallowed_tools: list[str] | None = None,
        effort: str | None = None,
        output_format: str | None = None,
        fallback_model: str | None = None,
        include_dirs: list[str] | None = None,
        system_prompt: str | None = None,
        # DI: SDK factories (None = use real SDK)
        client_factory: Callable[..., Any] | None = None,
        options_factory: Callable[..., Any] | None = None,
    ) -> None:
        self._model = model
        self._debug = debug

        # SDK factories — DI or real
        self._client_factory = client_factory or ClaudeSDKClient
        self._options_factory = options_factory or ClaudeAgentOptions

        # Set by on_connect — the client-side connection for sending notifications
        self._conn: Any = None

        # Session state
        self._sdk_client: Any = None
        self._session_id: str | None = None

        # Config: DI param takes precedence, else config (which reads env vars)
        from core.config import get_config

        cfg = get_config()

        self._root_dir: str = str(cfg.root_dir)
        self._mode: str = mode if mode is not None else cfg.agent_mode
        self._system_prompt: str | None = (
            system_prompt if system_prompt is not None else cfg.system_prompt
        )
        self._max_turns: int | None = (
            max_turns if max_turns is not None else cfg.max_turns
        )
        self._budget_usd: float | None = (
            budget_usd if budget_usd is not None else cfg.budget_usd
        )

        # Range validation: ignore invalid values
        if self._max_turns is not None and self._max_turns <= 0:
            self._max_turns = None
        if self._budget_usd is not None and self._budget_usd < 0:
            self._budget_usd = None

        self._allowed_tools: list[str] = (
            allowed_tools if allowed_tools is not None else cfg.allowed_tools
        )
        self._disallowed_tools: list[str] = (
            disallowed_tools if disallowed_tools is not None else cfg.disallowed_tools
        )
        self._effort: str | None = effort if effort is not None else cfg.effort
        self._output_format: str | None = (
            output_format if output_format is not None else cfg.output_format
        )
        self._fallback_model: str | None = (
            fallback_model if fallback_model is not None else cfg.fallback_model
        )
        self._include_dirs: list[str] = (
            include_dirs if include_dirs is not None else cfg.include_dirs
        )

        # All sessions tracked by this bridge instance
        self._sessions: dict[str, _SessionState] = {}

        # Cache of pending tool uses: tool_call_id → tool_name
        # Used to correlate tool_result (UserMessage) with the originating
        # tool_use (AssistantMessage) — mirrors Zed's caching pattern.
        self._pending_tools: dict[str, str] = {}

        # Index-based content block tracking for input_json_delta correlation.
        # Maps block index → tool_call_id, populated by content_block_start.
        self._block_index_to_tool: dict[int, str] = {}

        # Cancel tracking — set by cancel(), checked in prompt()
        self._cancelled: bool = False

    def on_connect(self, conn: Any) -> None:
        """Called by ``AgentSideConnection`` with the client-facing connection.

        The *conn* object exposes ``session_update()``,
        ``request_permission()``, etc. — mirroring ``SubagentClient``'s
        interface.
        """
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        _ = protocol_version
        _ = client_capabilities
        _ = client_info
        _ = kwargs
        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_info=Implementation(
                name="claude-acp-bridge",
                version="0.1.0",
            ),
            agent_capabilities=AgentCapabilities(
                load_session=True,
                session_capabilities=SessionCapabilities(
                    fork=SessionForkCapabilities(),
                    list=SessionListCapabilities(),
                    resume=SessionResumeCapabilities(),
                ),
            ),
        )

    def _build_options(
        self,
        cwd: str,
        sdk_mcp: dict[str, Any],
        sandbox_cb: Any,
    ) -> ClaudeAgentOptions:
        """Build ``ClaudeAgentOptions`` with all configured features.

        Centralises option construction so that ``new_session``,
        ``load_session``, ``resume_session``, and ``fork_session`` all
        use the same set of features.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "cwd": cwd,
            "mcp_servers": sdk_mcp,
            "can_use_tool": sandbox_cb,
            "permission_mode": "bypassPermissions",
            "system_prompt": self._system_prompt,
            "include_partial_messages": True,
        }

        # Safety & control
        if self._max_turns is not None:
            kwargs["max_turns"] = self._max_turns
        if self._budget_usd is not None:
            kwargs["max_budget_usd"] = self._budget_usd
        if self._allowed_tools:
            kwargs["allowed_tools"] = self._allowed_tools
        if self._disallowed_tools:
            kwargs["disallowed_tools"] = self._disallowed_tools

        # Quality & behavior
        if self._effort:
            kwargs["effort"] = self._effort
        if self._output_format == "json":
            kwargs["output_format"] = {"type": "json_object"}
        if self._fallback_model:
            kwargs["fallback_model"] = self._fallback_model
        if self._include_dirs:
            kwargs["add_dirs"] = self._include_dirs

        return self._options_factory(**kwargs)

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        _ = kwargs
        session_id = str(uuid.uuid4())
        self._session_id = session_id
        self._root_dir = cwd

        # Convert ACP MCP server specs → SDK format
        sdk_mcp = _convert_mcp_servers(mcp_servers or [])

        # Build sandbox callback
        sandbox_cb = _make_sandbox_callback(self._mode, self._root_dir)

        # Create SDK client
        options = self._build_options(cwd, sdk_mcp, sandbox_cb)
        self._sdk_client = self._client_factory(options)

        # Open the SDK connection without a prompt (streaming mode).
        # This ensures can_use_tool callbacks are active.  The actual
        # prompt is sent later via query() in prompt().
        await self._sdk_client.connect()

        # Track session state
        self._sessions[session_id] = _SessionState(
            session_id=session_id,
            cwd=cwd,
            model=self._model,
            mode=self._mode,
            mcp_servers=mcp_servers or [],
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        if self._debug:
            logger.debug(
                "Session %s created (model=%s, mode=%s, cwd=%s)",
                session_id,
                self._model,
                self._mode,
                cwd,
            )

        return NewSessionResponse(session_id=session_id)

    async def prompt(
        self,
        prompt: list[
            TextContentBlock
            | ImageContentBlock
            | AudioContentBlock
            | ResourceContentBlock
            | EmbeddedResourceContentBlock
        ],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        _ = kwargs
        if self._sdk_client is None:
            raise RuntimeError("No active session — call new_session first")

        # Reset cancel flag at start of new prompt
        self._cancelled = False

        prompt_text = _extract_prompt_text(prompt)

        if self._debug:
            logger.debug("Prompting (session=%s): %.200s...", session_id, prompt_text)

        # Send prompt via query() — connection was opened in new_session()
        await self._sdk_client.query(prompt_text)

        # Stream SDK events → ACP session/update notifications
        stop_reason: str = "end_turn"
        try:
            async for message in self._sdk_client.receive_messages():
                if self._cancelled:
                    stop_reason = "cancelled"
                    break

                await self._emit_updates(message, session_id)

                if isinstance(message, ResultMessage) and getattr(
                    message, "is_error", False
                ):
                    stop_reason = "refusal"
        except Exception:
            logger.exception("Error streaming SDK messages")
            stop_reason = "refusal"

        return PromptResponse(stop_reason=stop_reason)

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        _ = kwargs
        self._cancelled = True
        if self._sdk_client is not None:
            try:
                self._sdk_client.interrupt()
            except Exception:
                logger.exception("Error interrupting SDK client")
            try:
                self._sdk_client.disconnect()
            except Exception:
                logger.exception("Error disconnecting SDK client")

        # Mark session as disconnected
        if session_id in self._sessions:
            self._sessions[session_id].connected = False

    async def authenticate(
        self,
        method_id: str,
        **kwargs: Any,
    ) -> AuthenticateResponse | None:
        """Authenticate using the specified method.

        Claude SDK handles authentication internally — no protocol-level
        authentication is needed.  This method returns an empty
        ``AuthenticateResponse`` to satisfy ACP callers.
        """
        _ = method_id
        _ = kwargs
        if self._debug:
            logger.debug(
                "authenticate(method=%s) — SDK handles auth internally", method_id
            )
        return AuthenticateResponse()

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> LoadSessionResponse | None:
        """Load a previously created session by ID.

        Looks up the session in ``self._sessions``.  If found, disconnects
        the current SDK client (if any) and creates a new one with the
        stored session configuration.

        .. note::

           The Claude SDK does not persist conversation history across
           client instances.  This restores the session *configuration*
           (model, mode, cwd, MCP servers) but not the chat context.
        """
        _ = kwargs
        state = self._sessions.get(session_id)
        if state is None:
            if self._debug:
                logger.debug("load_session(%s) — not found", session_id)
            return None

        # Disconnect current session if active
        if self._sdk_client is not None:
            try:
                self._sdk_client.disconnect()
            except Exception:
                logger.exception("Error disconnecting previous SDK client")

        # Rebuild SDK client from stored config
        effective_mcp = mcp_servers if mcp_servers is not None else state.mcp_servers
        sdk_mcp = _convert_mcp_servers(effective_mcp)
        sandbox_cb = _make_sandbox_callback(state.mode, cwd)

        self._model = state.model
        self._mode = state.mode
        options = self._build_options(cwd, sdk_mcp, sandbox_cb)
        self._sdk_client = self._client_factory(options)
        await self._sdk_client.connect()

        self._session_id = session_id
        self._root_dir = cwd
        state.connected = True

        if self._debug:
            logger.debug(
                "load_session(%s) — restored (model=%s)", session_id, state.model
            )

        return LoadSessionResponse()

    async def resume_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> ResumeSessionResponse | None:
        """Resume a previously created session.

        Functionally equivalent to ``load_session`` — reconnects the SDK
        client with the stored session configuration.  The ACP spec treats
        ``resume`` as reconnecting to a paused/hibernated session.

        .. note::

           The Claude SDK does not support true session resumption with
           conversation history.  This restores configuration only.
        """
        _ = kwargs
        state = self._sessions.get(session_id)
        if state is None:
            if self._debug:
                logger.debug("resume_session(%s) — not found", session_id)
            return None

        # Disconnect current session if active
        if self._sdk_client is not None:
            try:
                self._sdk_client.disconnect()
            except Exception:
                logger.exception("Error disconnecting previous SDK client")

        # Rebuild SDK client from stored config
        effective_mcp = mcp_servers if mcp_servers is not None else state.mcp_servers
        sdk_mcp = _convert_mcp_servers(effective_mcp)
        sandbox_cb = _make_sandbox_callback(state.mode, cwd)

        self._model = state.model
        self._mode = state.mode
        options = self._build_options(cwd, sdk_mcp, sandbox_cb)
        self._sdk_client = self._client_factory(options)
        await self._sdk_client.connect()

        self._session_id = session_id
        self._root_dir = cwd
        state.connected = True

        if self._debug:
            logger.debug("resume_session(%s) — reconnected", session_id)

        return ResumeSessionResponse()

    async def fork_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> ForkSessionResponse:
        """Fork an existing session into a new independent session.

        Creates a new session with the same configuration (model, mode) as
        the source session but a new unique ID.  The new session becomes
        the active session.

        Raises ``RuntimeError`` if the source session does not exist.
        """
        _ = kwargs
        source = self._sessions.get(session_id)
        if source is None:
            raise RuntimeError(f"Cannot fork: session {session_id!r} not found")

        # Disconnect current session if active
        if self._sdk_client is not None:
            try:
                self._sdk_client.disconnect()
            except Exception:
                logger.exception("Error disconnecting previous SDK client")

        # Create new session with cloned config
        new_id = str(uuid.uuid4())
        effective_mcp = mcp_servers if mcp_servers is not None else source.mcp_servers
        sdk_mcp = _convert_mcp_servers(effective_mcp)
        sandbox_cb = _make_sandbox_callback(source.mode, cwd)

        self._model = source.model
        self._mode = source.mode
        options = self._build_options(cwd, sdk_mcp, sandbox_cb)
        self._sdk_client = self._client_factory(options)
        await self._sdk_client.connect()

        self._session_id = new_id
        self._root_dir = cwd

        self._sessions[new_id] = _SessionState(
            session_id=new_id,
            cwd=cwd,
            model=source.model,
            mode=source.mode,
            mcp_servers=list(effective_mcp),
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
        )

        if self._debug:
            logger.debug("fork_session(%s) → %s", session_id, new_id)

        return ForkSessionResponse(session_id=new_id)

    async def list_sessions(
        self,
        cursor: str | None = None,
        cwd: str | None = None,
        **kwargs: Any,
    ) -> ListSessionsResponse:
        """List all tracked sessions.

        Optionally filters by ``cwd``.  Returns ``SessionInfo`` objects
        with session metadata.  No pagination (``next_cursor`` omitted).

        .. note::

           Only sessions created during this bridge instance's lifetime
           are tracked.  The Claude SDK does not provide a session
           enumeration API.
        """
        _ = cursor
        _ = kwargs
        sessions = []
        for state in self._sessions.values():
            if cwd is not None and state.cwd != cwd:
                continue
            sessions.append(
                SessionInfo(
                    session_id=state.session_id,
                    cwd=state.cwd,
                    title=f"{state.model} ({state.mode})",
                    updated_at=state.created_at,
                )
            )
        return ListSessionsResponse(sessions=sessions)

    async def set_session_mode(
        self, mode_id: str, session_id: str, **kwargs: Any
    ) -> None:
        """Update the agent's sandboxing mode.

        Supported modes: ``read-only`` (writes restricted to ``.vault/``),
        ``read-write`` (no restrictions).  Updates the sandbox callback on
        the current SDK client options if a session is active.
        """
        _ = session_id
        _ = kwargs
        self._mode = mode_id

        # Rebuild sandbox callback for the new mode
        if self._sdk_client is not None:
            new_cb = _make_sandbox_callback(self._mode, self._root_dir)
            opts = getattr(self._sdk_client, "_options", None)
            if opts is not None:
                opts.can_use_tool = new_cb

        if self._debug:
            logger.debug("Session mode changed to: %s", mode_id)

    async def set_session_model(
        self, model_id: str, session_id: str, **kwargs: Any
    ) -> None:
        """Update the model used for subsequent prompts.

        The new model takes effect on the next ``prompt()`` call.  If
        a session is active, the SDK client options are updated in place.
        """
        _ = session_id
        _ = kwargs
        self._model = model_id

        # Update SDK client options if session is active
        if self._sdk_client is not None:
            opts = getattr(self._sdk_client, "_options", None)
            if opts is not None:
                opts.model = model_id

        if self._debug:
            logger.debug("Session model changed to: %s", model_id)

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        _ = params
        if self._debug:
            logger.debug("ext_method: %s", method)
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        _ = params
        if self._debug:
            logger.debug("ext_notification: %s", method)

    async def _emit_updates(self, message: Any, session_id: str) -> None:
        """Map an SDK message to ACP ``session/update`` notifications."""
        if self._conn is None:
            return

        if isinstance(message, StreamEvent):
            await self._emit_stream_event(message, session_id)
        elif isinstance(message, AssistantMessage):
            await self._emit_assistant(message, session_id)
        elif isinstance(message, UserMessage):
            await self._emit_user_message(message, session_id)
        elif isinstance(message, SystemMessage):
            await self._emit_system_message(message, session_id)
        elif isinstance(message, ResultMessage):
            await self._emit_result(message, session_id)
        elif self._debug:
            logger.debug("Unmapped SDK message: %s", type(message).__name__)

    async def _emit_stream_event(self, msg: StreamEvent, session_id: str) -> None:
        """Emit incremental ACP updates for SDK streaming delta events.

        When ``include_partial_messages=True``, the SDK yields
        ``StreamEvent`` objects whose ``.event`` dict contains raw
        Anthropic API events such as ``content_block_delta`` with
        ``text_delta`` or ``thinking_delta`` payloads.  We parse these
        and emit the corresponding ACP chunk notifications so clients
        receive incremental text as it is generated.

        Additionally handles:
        - ``content_block_start`` with ``tool_use`` to track the block
          index → tool_call_id mapping for ``input_json_delta`` correlation.
        - ``input_json_delta`` to emit ``ToolCallProgress`` with partial
          tool arguments as they are streamed.
        """
        event = msg.event
        event_type = event.get("type", "")

        if event_type == "content_block_start":
            content_block = event.get("content_block", {})
            if content_block.get("type") == "tool_use":
                index = event.get("index")
                tool_id = content_block.get("id", "")
                if index is not None and tool_id:
                    self._block_index_to_tool[index] = tool_id

        elif event_type == "content_block_delta":
            delta = event.get("delta", {})
            delta_type = delta.get("type", "")

            if delta_type == "text_delta":
                text = delta.get("text", "")
                if text:
                    await self._conn.session_update(
                        session_id=session_id,
                        update=AgentMessageChunk(
                            session_update="agent_message_chunk",
                            content=TextContentBlock(type="text", text=text),
                        ),
                    )
            elif delta_type == "thinking_delta":
                thinking = delta.get("thinking", "")
                if thinking:
                    await self._conn.session_update(
                        session_id=session_id,
                        update=AgentThoughtChunk(
                            session_update="agent_thought_chunk",
                            content=TextContentBlock(type="text", text=thinking),
                        ),
                    )
            elif delta_type == "input_json_delta":
                partial_json = delta.get("partial_json", "")
                if partial_json:
                    index = event.get("index", -1)
                    tool_call_id = self._block_index_to_tool.get(int(index), "")
                    title = self._pending_tools.get(tool_call_id)
                    await self._conn.session_update(
                        session_id=session_id,
                        update=ToolCallProgress(
                            session_update="tool_call_update",
                            tool_call_id=tool_call_id,
                            title=title,
                            status="in_progress",
                            raw_input=partial_json,
                        ),
                    )
            elif self._debug:
                logger.debug("Unhandled delta type: %s", delta_type)

        elif self._debug:
            logger.debug("Unhandled stream event type: %s", event_type)

    async def _emit_assistant(self, msg: AssistantMessage, session_id: str) -> None:
        """Emit ACP updates for each content block in an AssistantMessage."""
        for block in msg.content:
            if isinstance(block, TextBlock):
                await self._conn.session_update(
                    session_id=session_id,
                    update=AgentMessageChunk(
                        session_update="agent_message_chunk",
                        content=TextContentBlock(type="text", text=block.text),
                    ),
                )
            elif isinstance(block, ThinkingBlock):
                await self._conn.session_update(
                    session_id=session_id,
                    update=AgentThoughtChunk(
                        session_update="agent_thought_chunk",
                        content=TextContentBlock(type="text", text=block.thinking),
                    ),
                )
            elif isinstance(block, ToolUseBlock):
                # Cache the tool use so we can correlate with the tool_result
                self._pending_tools[block.id] = block.name
                await self._conn.session_update(
                    session_id=session_id,
                    update=ToolCallStart(
                        session_update="tool_call",
                        tool_call_id=block.id,
                        title=block.name,
                        status="pending",
                    ),
                )
            else:
                block_type = type(block).__name__
                logger.warning(
                    "Unsupported AssistantMessage content block type: %s "
                    "(expected TextBlock, ThinkingBlock, or ToolUseBlock)",
                    block_type,
                )
                if self._debug:
                    logger.debug("Block details: %r", block)

    async def _emit_user_message(self, msg: UserMessage, session_id: str) -> None:
        """Emit a ToolCallProgress for a tool result (UserMessage).

        Correlates with the cached tool use from the preceding
        AssistantMessage.  Checks ``ToolResultBlock.is_error`` to determine
        whether the status is ``completed`` or ``failed``.
        """
        tool_use_id = getattr(msg, "parent_tool_use_id", None) or ""
        if not tool_use_id:
            return

        # Determine status from tool result content
        status = "completed"
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for block in content:
                if isinstance(block, ToolResultBlock) and getattr(
                    block, "is_error", False
                ):
                    status = "failed"
                    break

        # Look up cached tool name for the title
        title = self._pending_tools.pop(tool_use_id, None)
        if title is None:
            logger.warning(
                "Tool result received for untracked tool_use_id: %s "
                "(possible out-of-order or duplicate result)",
                tool_use_id,
            )

        await self._conn.session_update(
            session_id=session_id,
            update=ToolCallProgress(
                session_update="tool_call_update",
                tool_call_id=tool_use_id,
                title=title,
                status=status,
            ),
        )

    async def _emit_system_message(self, msg: SystemMessage, session_id: str) -> None:
        """Emit a SessionInfoUpdate for system messages."""
        title = str(getattr(msg, "subtype", "system"))
        await self._conn.session_update(
            session_id=session_id,
            update=SessionInfoUpdate(
                session_update="session_info_update",
                title=title,
            ),
        )

    async def _emit_result(self, msg: ResultMessage, session_id: str) -> None:
        """Emit a final SessionInfoUpdate with result summary."""
        result_text = ""
        if msg.result:
            result_text = msg.result if isinstance(msg.result, str) else str(msg.result)
        title = f"Result: {result_text[:100]}" if result_text else "Result"
        await self._conn.session_update(
            session_id=session_id,
            update=SessionInfoUpdate(
                session_update="session_info_update",
                title=title,
            ),
        )


async def main() -> None:
    parser = argparse.ArgumentParser(
        description="ACP bridge server wrapping claude-agent-sdk",
    )
    parser.add_argument(
        "--model",
        default=ClaudeModels.MEDIUM,
        help=f"Claude model to use (default: {ClaudeModels.MEDIUM})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)

    bridge = ClaudeACPBridge(model=args.model, debug=args.debug)
    await run_agent(bridge)  # type: ignore[arg-type]  # structural Agent protocol


if __name__ == "__main__":
    asyncio.run(main())
