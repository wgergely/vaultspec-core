"""ACP bridge server that wraps claude-agent-sdk.

This module is the ACP server process spawned by ``ClaudeProvider``.  It
implements the ACP ``Agent`` protocol interface and uses
``AgentSideConnection`` from the ``acp`` package for JSON-RPC framing over
stdin/stdout.  Internally it drives Claude via ``claude-agent-sdk``'s
``ClaudeSDKClient``.

Usage::

    python -m vaultspec.protocol.acp.claude_bridge --model ClaudeModels.MEDIUM

The bridge reads ``VAULTSPEC_AGENT_MODE`` from the environment to decide
sandboxing policy and ``VAULTSPEC_ROOT_DIR`` for the workspace root.
"""

from __future__ import annotations

import argparse
import asyncio
import dataclasses
import datetime
import logging
import shutil
import sys
import uuid
from typing import TYPE_CHECKING, Any, cast

from ...logging_config import configure_logging

if TYPE_CHECKING:
    from collections.abc import Callable

from acp import PROTOCOL_VERSION, Agent, run_agent
from acp.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    AuthenticateResponse,
    ContentToolCallContent,
    FileEditToolCallContent,
    ForkSessionResponse,
    Implementation,
    InitializeResponse,
    ListSessionsResponse,
    LoadSessionResponse,
    NewSessionResponse,
    PlanEntry,
    PlanEntryPriority,
    PlanEntryStatus,
    PromptCapabilities,
    PromptResponse,
    ResumeSessionResponse,
    SessionCapabilities,
    SessionForkCapabilities,
    SessionInfo,
    SessionInfoUpdate,
    SessionListCapabilities,
    SessionResumeCapabilities,
    TerminalToolCallContent,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolKind,
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
from claude_agent_sdk._errors import MessageParseError
from claude_agent_sdk.types import (
    McpStdioServerConfig,
    StreamEvent,
)

from ..providers import ClaudeModels
from ..sandbox import (
    _make_sandbox_callback,
)

__all__ = ["ClaudeACPBridge", "main"]

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

    Args:
        acp_servers: List of ACP MCP server specs (pydantic models or dicts).

    Returns:
        A dict mapping server name to ``McpStdioServerConfig``.
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


def _build_sdk_message_payload(
    prompt: list[
        TextContentBlock
        | ImageContentBlock
        | AudioContentBlock
        | ResourceContentBlock
        | EmbeddedResourceContentBlock
    ],
) -> dict[str, Any]:
    """Convert ACP prompt blocks into a Claude SDK message dict.

    Args:
        prompt: List of ACP content blocks (text, image, audio, resource, etc.).

    Returns:
        A dict with ``type`` and ``message`` keys suitable for the Claude SDK.
    """
    content: list[dict[str, Any]] = []
    text_parts: list[str] = []

    for block in prompt:
        if isinstance(block, TextContentBlock):
            text_parts.append(block.text)
        elif hasattr(block, "text") and block.text:  # Fallback for text-like
            text_parts.append(str(block.text))
        elif hasattr(block, "uri") and block.uri:  # Resource/Link
            # Map file:// URI to @path for Claude CLI
            uri = str(block.uri)
            if uri.startswith("file://"):
                path = uri[7:]  # Strip file://
                text_parts.append(f"@{path}")
            else:
                text_parts.append(uri)
        elif hasattr(block, "data") and block.data:  # Image
            mime_type = getattr(block, "mime_type", "image/jpeg")
            content.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": block.data,
                    },
                }
            )

    # Append accumulated text as a single text block if present
    if text_parts:
        content.append({"type": "text", "text": "\n".join(text_parts)})

    return {
        "type": "user",
        "message": {
            "role": "user",
            "content": content,
        },
    }


async def _to_async_iter(item: Any) -> Any:
    """Wrap an item in an async iterable.

    Args:
        item: Any value to yield as a single-element async generator.
    """
    yield item


def _map_tool_kind(tool_name: str) -> str:
    """Map a Claude tool name to an ACP tool kind via substring matching.

    Follows the reference pattern from acp-claude-code ``mapToolKind()``.

    Args:
        tool_name: The Claude tool name (e.g. ``"Read"``, ``"Bash"``).

    Returns:
        An ACP ``ToolKind`` string such as ``"read"``, ``"edit"``, or
        ``"other"``.
    """
    name = tool_name.lower()
    for keyword, kind in (
        ("read", "read"),
        ("view", "read"),
        ("get", "read"),
        ("write", "edit"),
        ("create", "edit"),
        ("update", "edit"),
        ("edit", "edit"),
        ("delete", "delete"),
        ("remove", "delete"),
        ("move", "move"),
        ("rename", "move"),
        ("search", "search"),
        ("find", "search"),
        ("grep", "search"),
        ("run", "execute"),
        ("execute", "execute"),
        ("bash", "execute"),
        ("think", "think"),
        ("plan", "think"),
        ("fetch", "fetch"),
        ("download", "fetch"),
    ):
        if keyword in name:
            return kind
    return "other"


def _get_tool_call_content(
    tool_name: str, tool_input: dict[str, Any] | None
) -> list[ContentToolCallContent | FileEditToolCallContent | TerminalToolCallContent]:
    """Produce initial ACP content blocks for a tool call.

    For ``Edit``/``MultiEdit`` tools, generates structured diff blocks.
    For all others, returns an empty list.

    Args:
        tool_name: The Claude tool name (e.g. ``"Edit"``, ``"MultiEdit"``).
        tool_input: The tool's input parameters dict, or ``None``.

    Returns:
        A list of ACP content blocks — ``FileEditToolCallContent`` for edit
        tools, empty list for everything else.
    """
    if tool_input is None:
        return []
    if tool_name == "Edit":
        path = tool_input.get("file_path", "")
        old = tool_input.get("old_string", "")
        new = tool_input.get("new_string", "")
        if path:
            return [
                FileEditToolCallContent(
                    type="diff", path=path, old_text=old, new_text=new
                )
            ]
    elif tool_name == "MultiEdit":
        path = tool_input.get("file_path", "")
        edits = tool_input.get("edits", [])
        if path and edits:
            return [
                FileEditToolCallContent(
                    type="diff",
                    path=path,
                    old_text=e.get("old_string", ""),
                    new_text=e.get("new_string", ""),
                )
                for e in edits
            ]
    return []


@dataclasses.dataclass
class _SessionState:
    """Per-session state tracked by the Claude ACP bridge.

    Attributes:
        session_id: Bridge-level unique session identifier.
        cwd: Working directory for this session.
        model: Claude model identifier in use.
        mode: Sandboxing mode (``"read-only"`` or ``"read-write"``).
        mcp_servers: ACP MCP server configurations for this session.
        created_at: ISO-8601 timestamp of session creation.
        sdk_client: The active ``ClaudeSDKClient``, or ``None`` if not yet
            connected.
        connected: Whether the SDK client is currently connected.
        claude_session_id: Claude's native session ID extracted from SDK
            messages; used to resume multi-turn conversations.
        cancel_event: Per-session asyncio event set by ``cancel()`` to
            interrupt the active ``prompt()`` stream.
        tool_call_contents: Accumulated ACP content blocks keyed by
            ``tool_call_id``, used to build complete ``ToolCallProgress``
            updates.
        todo_write_tool_call_ids: IDs of ``TodoWrite`` tool calls that should
            be converted to plan updates rather than tool call events.
        permission_mode: SDK permission mode for this session (e.g.
            ``"bypassPermissions"`` or ``"acceptEdits"``).
    """

    session_id: str
    cwd: str
    model: str
    mode: str
    mcp_servers: list[Any]
    created_at: str
    sdk_client: ClaudeSDKClient | None = None
    connected: bool = True
    # Claude's native session ID — extracted from SDK messages for multi-turn resume
    claude_session_id: str | None = None
    # Per-session cancel event — replaces bridge-level _cancelled boolean
    cancel_event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    # Tool call content accumulation: tool_call_id → list of content models
    tool_call_contents: dict[
        str,
        list[
            ContentToolCallContent | FileEditToolCallContent | TerminalToolCallContent
        ],
    ] = dataclasses.field(default_factory=dict)
    # IDs of TodoWrite tool calls — suppressed from tool call events
    todo_write_tool_call_ids: set[str] = dataclasses.field(default_factory=set)
    # Permission mode for this session
    permission_mode: str = "bypassPermissions"


class ClaudeACPBridge(Agent):
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
        """Initialise the ACP bridge with SDK configuration and DI overrides.

        Config parameters default to ``None`` which causes them to be read from
        the vaultspec config system (which itself falls back to env vars).

        Args:
            model: Claude model identifier (e.g. ``ClaudeModels.MEDIUM``).
            debug: If True, emit verbose debug log messages.
            mode: Sandboxing mode — ``"read-only"`` or ``"read-write"``.
                Overrides the ``VAULTSPEC_AGENT_MODE`` env var.
            max_turns: Maximum number of conversation turns.  Non-positive
                values are ignored.
            budget_usd: Maximum spend in USD.  Negative values are ignored.
            allowed_tools: Explicit allow-list of tool names forwarded to the SDK.
            disallowed_tools: Explicit deny-list of tool names forwarded to the SDK.
            effort: Effort level string forwarded to the SDK.
            output_format: Output format string (e.g. ``"json"``).
            fallback_model: Model to fall back to on errors.
            include_dirs: Additional directories to include in the SDK context.
            system_prompt: System prompt appended after the preset.
            client_factory: Callable ``(options) -> ClaudeSDKClient``.  Defaults
                to the real ``ClaudeSDKClient``.
            options_factory: Callable ``(**kwargs) -> ClaudeAgentOptions``.
                Defaults to the real ``ClaudeAgentOptions``.
        """
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
        from ...config import get_config

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

        # Path to the authenticated Claude CLI — overrides the SDK's bundled v2.1.42
        self._cli_path: str | None = shutil.which("claude")

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

        # NOTE: No persistent stream — each prompt() call uses
        # receive_response() which creates a fresh generator per turn,
        # avoiding the generator-death bug from upstream MessageParseError.

    def on_connect(self, conn: Any) -> None:
        """Called by ``AgentSideConnection`` with the client-facing connection.

        The *conn* object exposes ``session_update()``,
        ``request_permission()``, etc. — mirroring ``SubagentClient``'s
        interface.

        Args:
            conn: The ACP client-side connection used to send notifications.
        """
        self._conn = conn

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: ClientCapabilities | None = None,
        client_info: Implementation | None = None,
        **kwargs: Any,
    ) -> InitializeResponse:
        """Return bridge capabilities in response to the ACP initialize handshake.

        Args:
            protocol_version: ACP protocol version negotiated by the client.
            client_capabilities: Capabilities advertised by the client, if any.
            client_info: Implementation info of the connecting client, if any.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            An ``InitializeResponse`` advertising the bridge's capabilities.
        """
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
                prompt_capabilities=PromptCapabilities(
                    image=True,
                    embedded_context=True,
                ),
            ),
        )

    def _build_options(
        self,
        cwd: str,
        sdk_mcp: dict[str, Any],
        sandbox_cb: Any,
        permission_mode: str = "bypassPermissions",
    ) -> ClaudeAgentOptions:
        """Build ``ClaudeAgentOptions`` with all configured features.

        Centralises option construction so that ``new_session``,
        ``load_session``, ``resume_session``, and ``fork_session`` all
        use the same set of features.

        Args:
            cwd: Working directory for the SDK session.
            sdk_mcp: MCP server configs in SDK format (name → config dict).
            sandbox_cb: ``can_use_tool`` callback for permission enforcement.
            permission_mode: SDK permission mode string (e.g.
                ``"bypassPermissions"`` or ``"acceptEdits"``).

        Returns:
            A fully configured ``ClaudeAgentOptions`` instance.
        """
        kwargs: dict[str, Any] = {
            "model": self._model,
            "cwd": cwd,
            "mcp_servers": sdk_mcp,
            "can_use_tool": sandbox_cb,
            "permission_mode": permission_mode,
            "system_prompt": (
                {
                    "type": "preset",
                    "preset": "claude_code",
                    "append": self._system_prompt,
                }
                if self._system_prompt
                else {"type": "preset", "preset": "claude_code"}
            ),
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
        if self._cli_path:
            kwargs["cli_path"] = self._cli_path

        return self._options_factory(**kwargs)

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        """Create a new Claude SDK session.

        Converts ACP MCP server specs to SDK format, builds a sandboxed
        ``ClaudeAgentOptions``, creates a ``ClaudeSDKClient``, and opens
        the SDK connection without an initial prompt.

        Args:
            cwd: Working directory for the session.
            mcp_servers: Optional list of ACP MCP server configurations.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``NewSessionResponse`` containing the new session ID.
        """
        _ = kwargs
        session_id = str(uuid.uuid4())
        self._session_id = session_id
        self._root_dir = cwd

        # Convert ACP MCP server specs → SDK format
        sdk_mcp = _convert_mcp_servers(mcp_servers or [])

        # Build sandbox callback
        sandbox_cb = _make_sandbox_callback(self._mode, self._root_dir)

        # Create SDK client
        options = self._build_options(
            cwd, sdk_mcp, sandbox_cb, permission_mode="bypassPermissions"
        )
        sdk_client = self._client_factory(options)

        # Open the SDK connection without a prompt (streaming mode).
        # This ensures can_use_tool callbacks are active.  The actual
        # prompt is sent later via query() in prompt().
        await sdk_client.connect()
        self._sdk_client = sdk_client

        # Track session state — store SDK client per-session
        self._sessions[session_id] = _SessionState(
            session_id=session_id,
            cwd=cwd,
            model=self._model,
            mode=self._mode,
            mcp_servers=mcp_servers or [],
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
            sdk_client=sdk_client,
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
        """Send a prompt to Claude and stream the response as ACP session updates.

        Converts the ACP prompt blocks to an SDK message payload, queries the
        SDK client, and forwards each SDK event (text deltas, tool calls, tool
        results, system messages, result) as ``session/update`` notifications
        on the parent ACP connection.  Handles dynamic permission mode
        switching via magic strings embedded in the prompt.

        Args:
            prompt: List of ACP content blocks (text, image, resource, etc.).
            session_id: The session ID returned by ``new_session``.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``PromptResponse`` with ``stop_reason`` set to ``"end_turn"``
            or ``"cancelled"``.

        Raises:
            RuntimeError: If no active SDK session exists.
        """
        _ = kwargs
        # Resolve per-session SDK client (fall back to bridge-level for compat)
        state = self._sessions.get(session_id)
        sdk_client = (state.sdk_client if state else None) or self._sdk_client
        if sdk_client is None:
            raise RuntimeError("No active session — call new_session first")

        # Reset per-session cancel event
        if state:
            state.cancel_event.clear()

        # Clear stale tool correlation dicts from previous turns
        self._pending_tools.clear()
        self._block_index_to_tool.clear()

        # Build structured message payload (text + images + resources)
        message_payload = _build_sdk_message_payload(prompt)

        # Handle dynamic permission mode switching via magic strings
        full_text = ""
        # The message payload is nested: {"type": "user", "message": {"content": [...]}}
        msg_content = message_payload.get("message", {}).get("content", [])
        if isinstance(msg_content, list):
            for block in msg_content:
                if block.get("type") == "text":
                    full_text += block.get("text", "")

        new_mode = None
        if "[ACP:PERMISSION:ACCEPT_EDITS]" in full_text:
            new_mode = "acceptEdits"
        elif "[ACP:PERMISSION:BYPASS]" in full_text:
            new_mode = "bypassPermissions"
        elif "[ACP:PERMISSION:DEFAULT]" in full_text:
            new_mode = "default"

        if new_mode and state and new_mode != state.permission_mode:
            if self._debug:
                logger.debug(
                    "Switching permission mode: %s -> %s",
                    state.permission_mode,
                    new_mode,
                )
            state.permission_mode = new_mode

            # Recreate SDK client with new permission mode
            if state.sdk_client:
                try:
                    state.sdk_client.disconnect()
                except Exception:
                    logger.exception(
                        "Error disconnecting SDK client during mode switch"
                    )

            effective_mcp = state.mcp_servers
            sdk_mcp = _convert_mcp_servers(effective_mcp)
            sandbox_cb = _make_sandbox_callback(state.mode, self._root_dir)

            options = self._build_options(
                self._root_dir,
                sdk_mcp,
                sandbox_cb,
                permission_mode=state.permission_mode,
            )
            # Preserve resume context if available
            if state.claude_session_id:
                options.resume = state.claude_session_id

            sdk_client = self._client_factory(options)
            await sdk_client.connect()
            state.sdk_client = sdk_client
            # Note: self._sdk_client also updated in case of fallback usage
            self._sdk_client = sdk_client

        if self._debug:
            logger.debug("Prompting (session=%s): %r", session_id, message_payload)

        # Send prompt via query() as an async stream of messages
        await sdk_client.query(_to_async_iter(message_payload))

        # Stream SDK events → ACP session/update notifications.
        # Uses receive_response() which creates a fresh generator per turn
        # and stops cleanly at ResultMessage.  This avoids the generator-death
        # bug: if the upstream SDK emits an unparseable event (e.g.
        # rate_limit_event) AFTER ResultMessage, it would raise
        # MessageParseError inside the generator, finalising it.  A
        # persistent iterator across turns would then be dead on turn 2.
        stop_reason: str = "end_turn"
        msg_count = 0
        result_seen = False

        while not result_seen:
            try:
                async for message in sdk_client.receive_response():
                    msg_count += 1
                    if self._debug:
                        logger.debug(
                            "Bridge msg #%d: %s",
                            msg_count,
                            type(message).__name__,
                        )

                    # Extract Claude's native session_id for multi-turn resume
                    msg_session_id = getattr(message, "session_id", None)
                    if (
                        state
                        and msg_session_id
                        and msg_session_id != state.claude_session_id
                    ):
                        state.claude_session_id = msg_session_id
                        if self._debug:
                            logger.debug(
                                "Captured Claude session_id: %s", msg_session_id
                            )

                    # Check per-session cancel (fall back to bridge-level for compat)
                    cancelled = (
                        state.cancel_event.is_set() if state else self._cancelled
                    )
                    if cancelled:
                        stop_reason = "cancelled"
                        break

                    await self._emit_updates(message, session_id)

                    if isinstance(message, ResultMessage):
                        result_seen = True
                        if getattr(message, "is_error", False):
                            error_text = (
                                getattr(message, "result", "") or "Unknown error"
                            )
                            if self._conn is not None:
                                await self._conn.session_update(
                                    session_id=session_id,
                                    update=AgentMessageChunk(
                                        session_update="agent_message_chunk",
                                        content=TextContentBlock(
                                            type="text", text=error_text
                                        ),
                                    ),
                                )
                            # Clear stale session ID so next attempt starts fresh
                            if state and state.claude_session_id:
                                logger.debug(
                                    "Clearing stale claude_session_id after error"
                                )
                                state.claude_session_id = None
                            stop_reason = "end_turn"
            except MessageParseError as exc:
                logger.debug("Skipping unparseable SDK message: %s", exc)
                continue
            except Exception:
                logger.exception(
                    "Error streaming SDK messages after %d msgs", msg_count
                )
                try:
                    if self._conn is not None:
                        error_text = str(sys.exc_info()[1]) or "Unknown error"
                        await self._conn.session_update(
                            session_id=session_id,
                            update=AgentMessageChunk(
                                session_update="agent_message_chunk",
                                content=TextContentBlock(type="text", text=error_text),
                            ),
                        )
                except Exception:
                    logger.debug("Failed to emit error as AgentMessageChunk")
                stop_reason = "end_turn"
                break

            if stop_reason == "cancelled":
                break

            if not result_seen:
                logger.warning("Stream ended without ResultMessage")
                break

        return PromptResponse(stop_reason=stop_reason)

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Cancel the active prompt for the given session.

        Sets the per-session cancel event so the streaming loop in
        ``prompt()`` terminates at the next iteration, then interrupts (but
        does not disconnect) the SDK client so the session can receive future
        prompts.

        Args:
            session_id: The session to cancel.
            **kwargs: Additional fields forwarded by the ACP library.
        """
        _ = kwargs
        # Set per-session cancel event (also set bridge-level for compat)
        self._cancelled = True
        state = self._sessions.get(session_id)
        if state:
            state.cancel_event.set()

        # Interrupt (not disconnect!) — session stays alive for future prompts
        sdk_client = (state.sdk_client if state else None) or self._sdk_client
        if sdk_client is not None:
            try:
                await sdk_client.interrupt()
            except Exception:
                logger.exception("Error interrupting SDK client")

    async def authenticate(
        self,
        method_id: str,
        **kwargs: Any,
    ) -> AuthenticateResponse | None:
        """Authenticate using the specified method.

        Claude SDK handles authentication internally — no protocol-level
        authentication is needed.  This method returns an empty
        ``AuthenticateResponse`` to satisfy ACP callers.

        Args:
            method_id: The authentication method identifier requested by the
                client.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            An empty ``AuthenticateResponse``.
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

        If the session ID is not found (e.g. after bridge restart), a new
        session is created with default configuration to allow recovery.

        .. note::

           The Claude SDK does not persist conversation history across
           client instances.  This restores the session *configuration*
           (model, mode, cwd, MCP servers) but not the chat context.

        Args:
            cwd: Working directory to use for the loaded session.
            session_id: The session ID to load.
            mcp_servers: Optional MCP server overrides; falls back to stored
                config if ``None``.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            An empty ``LoadSessionResponse`` on success.
        """
        _ = kwargs
        state = self._sessions.get(session_id)

        # Session recovery: if not found, create a new session state
        if state is None:
            if self._debug:
                logger.debug(
                    "load_session(%s) — not found, creating recovery session",
                    session_id,
                )
            state = _SessionState(
                session_id=session_id,
                cwd=cwd,
                model=self._model,
                mode=self._mode,
                mcp_servers=mcp_servers or [],
                created_at=datetime.datetime.now(datetime.UTC).isoformat(),
            )
            self._sessions[session_id] = state

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
        options = self._build_options(
            cwd, sdk_mcp, sandbox_cb, permission_mode=state.permission_mode
        )
        # Pass stored Claude session_id for conversation resume
        if state.claude_session_id:
            options.resume = state.claude_session_id
        sdk_client = self._client_factory(options)
        await sdk_client.connect()
        self._sdk_client = sdk_client
        state.sdk_client = sdk_client

        self._session_id = session_id
        self._root_dir = cwd
        state.connected = True

        if self._debug:
            logger.debug(
                "load_session(%s) — restored (model=%s, resume=%s)",
                session_id,
                state.model,
                state.claude_session_id,
            )

        return LoadSessionResponse()

    async def resume_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[HttpMcpServer | SseMcpServer | McpServerStdio] | None = None,
        **kwargs: Any,
    ) -> ResumeSessionResponse:
        """Resume a previously created session.

        Functionally equivalent to ``load_session`` — reconnects the SDK
        client with the stored session configuration.  The ACP spec treats
        ``resume`` as reconnecting to a paused/hibernated session.

        .. note::

           The Claude SDK does not support true session resumption with
           conversation history.  This restores configuration only.

        Args:
            cwd: Working directory for the resumed session.
            session_id: The session ID to resume.
            mcp_servers: Optional MCP server overrides; falls back to stored
                config if ``None``.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            An empty ``ResumeSessionResponse``.
        """
        _ = kwargs
        state = self._sessions.get(session_id)
        if state is None:
            logger.warning("resume_session(%s) — session not found", session_id)
            return ResumeSessionResponse()

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
        # Pass stored Claude session_id for conversation resume
        if state.claude_session_id:
            options.resume = state.claude_session_id
        sdk_client = self._client_factory(options)
        await sdk_client.connect()
        self._sdk_client = sdk_client
        state.sdk_client = sdk_client

        self._session_id = session_id
        self._root_dir = cwd
        state.connected = True

        if self._debug:
            logger.debug(
                "resume_session(%s) — reconnected (resume=%s)",
                session_id,
                state.claude_session_id,
            )

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

        Args:
            cwd: Working directory for the forked session.
            session_id: The source session ID to fork from.
            mcp_servers: Optional MCP server overrides; falls back to source
                session config if ``None``.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``ForkSessionResponse`` containing the new session ID.

        Raises:
            RuntimeError: If the source session does not exist.
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
        sdk_client = self._client_factory(options)
        await sdk_client.connect()
        self._sdk_client = sdk_client

        self._session_id = new_id
        self._root_dir = cwd

        self._sessions[new_id] = _SessionState(
            session_id=new_id,
            cwd=cwd,
            model=source.model,
            mode=source.mode,
            mcp_servers=list(effective_mcp),
            created_at=datetime.datetime.now(datetime.UTC).isoformat(),
            sdk_client=sdk_client,
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

        Args:
            cursor: Pagination cursor (unused; all sessions are returned).
            cwd: Optional working-directory filter; only sessions whose
                ``cwd`` matches are included.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``ListSessionsResponse`` containing matching session info objects.
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

        Args:
            mode_id: The new sandboxing mode (``"read-only"`` or
                ``"read-write"``).
            session_id: The session to update.
            **kwargs: Additional fields forwarded by the ACP library.
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

        Args:
            model_id: The Claude model identifier to switch to.
            session_id: The session to update.
            **kwargs: Additional fields forwarded by the ACP library.
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

    async def set_config_option(
        self, config_id: str, session_id: str, value: str, **_kwargs: Any
    ) -> None:
        """Set a session configuration option. No-op for Claude bridge.

        Args:
            config_id: The configuration key to set.
            session_id: The session to configure.
            value: The new value for the configuration key.

        Returns:
            ``None`` — this method is a no-op for the Claude bridge.
        """
        _ = session_id  # required by ACP interface
        if self._debug:
            logger.debug("set_config_option(%s=%s) -- no-op", config_id, value)
        return None

    async def close(self) -> None:
        """Close all active sessions and disconnect SDK clients."""
        for state in list(self._sessions.values()):
            if state.sdk_client:
                try:
                    await state.sdk_client.disconnect()
                except Exception as exc:
                    logger.debug("SDK client disconnect failed: %s", exc)
        self._sessions.clear()

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle an ACP extension method call.  Returns an empty dict.

        Args:
            method: The extension method name.
            params: Arbitrary parameters sent by the caller.

        Returns:
            An empty dict — no extension methods are implemented.
        """
        _ = params
        if self._debug:
            logger.debug("ext_method: %s", method)
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle an ACP extension notification.  No-op.

        Args:
            method: The extension notification name.
            params: Arbitrary parameters sent by the caller.
        """
        _ = params
        if self._debug:
            logger.debug("ext_notification: %s", method)

    async def _emit_updates(self, message: Any, session_id: str) -> None:
        """Map an SDK message to ACP ``session/update`` notifications.

        Args:
            message: An SDK message object (``StreamEvent``,
                ``AssistantMessage``, ``UserMessage``, ``SystemMessage``, or
                ``ResultMessage``).
            session_id: The session ID for routing ACP notifications.
        """
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

        Args:
            msg: The SDK ``StreamEvent`` containing the raw Anthropic API
                event dict.
            session_id: The session ID for routing ACP notifications.
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

                if content_block.get("name") == "TodoWrite":
                    todos = content_block.get("input", {}).get("todos", [])
                    if todos:
                        state = self._sessions.get(session_id)
                        if state:
                            state.todo_write_tool_call_ids.add(tool_id)

                        await self._conn.session_update(
                            session_id=session_id,
                            update=AgentPlanUpdate(
                                session_update="plan",
                                entries=[
                                    PlanEntry(
                                        content=t.get("content", ""),
                                        status=cast(
                                            "PlanEntryStatus",
                                            t.get("status", "pending"),
                                        ),
                                        priority=cast(
                                            "PlanEntryPriority",
                                            t.get("priority", "low"),
                                        ),
                                    )
                                    for t in todos
                                ],
                            ),
                        )

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

        elif event_type == "tool_use_error":
            # Explicit tool error event (e.g. from Claude CLI)
            error_message = event.get("error", "Unknown tool error")
            tool_use_id = event.get("tool_use_id", "")

            # If no ID in event, we can't route it. But usually it should have one.
            # If not, we might try to infer from index if provided?
            # The reference implementation uses ID.

            if tool_use_id:
                # Retrieve cached title
                title = self._pending_tools.get(tool_use_id)
                await self._conn.session_update(
                    session_id=session_id,
                    update=ToolCallProgress(
                        session_update="tool_call_update",
                        tool_call_id=tool_use_id,
                        title=title,
                        status="failed",
                        raw_output={"error": error_message},
                        content=[
                            ContentToolCallContent(
                                type="content",
                                content=TextContentBlock(
                                    type="text", text=f"Error: {error_message}"
                                ),
                            )
                        ],
                    ),
                )

        elif self._debug:
            logger.debug("Unhandled stream event type: %s", event_type)

    async def _emit_assistant(self, msg: AssistantMessage, session_id: str) -> None:
        """Emit ACP updates for each content block in an AssistantMessage.

        TextBlock and ThinkingBlock are skipped here because they were
        already streamed incrementally via ``_emit_stream_event``
        (``include_partial_messages=True`` is always on).  Only ToolUseBlock
        needs emission — streaming only tracks the block index mapping, not
        the full tool call notification.

        Args:
            msg: The SDK ``AssistantMessage`` containing content blocks.
            session_id: The session ID for routing ACP notifications.
        """
        state = self._sessions.get(session_id)
        for block in msg.content:
            if isinstance(block, (TextBlock, ThinkingBlock)):
                continue
            elif isinstance(block, ToolUseBlock):
                if block.name == "TodoWrite":
                    todos = (block.input or {}).get("todos", [])
                    if todos:
                        if state:
                            state.todo_write_tool_call_ids.add(block.id)

                        await self._conn.session_update(
                            session_id=session_id,
                            update=AgentPlanUpdate(
                                session_update="plan",
                                entries=[
                                    PlanEntry(
                                        content=t.get("content", ""),
                                        status=cast(
                                            "PlanEntryStatus",
                                            t.get("status", "pending"),
                                        ),
                                        priority=cast(
                                            "PlanEntryPriority",
                                            t.get("priority", "low"),
                                        ),
                                    )
                                    for t in todos
                                ],
                            ),
                        )
                        continue

                # Cache the tool use so we can correlate with the tool_result
                self._pending_tools[block.id] = block.name

                # Generate initial content (e.g. diffs for Edit tools)
                content = _get_tool_call_content(block.name, block.input)
                if state:
                    state.tool_call_contents[block.id] = content

                await self._conn.session_update(
                    session_id=session_id,
                    update=ToolCallStart(
                        session_update="tool_call",
                        tool_call_id=block.id,
                        title=block.name,
                        kind=cast("ToolKind", _map_tool_kind(block.name)),
                        status="pending",
                        content=content,
                        raw_input=block.input,
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

        Args:
            msg: The SDK ``UserMessage`` carrying tool result blocks.
            session_id: The session ID for routing ACP notifications.
        """
        tool_use_id = getattr(msg, "parent_tool_use_id", None) or ""
        if not tool_use_id:
            return

        state = self._sessions.get(session_id)
        if state and tool_use_id in state.todo_write_tool_call_ids:
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

        # Accumulate tool result text into content
        state = self._sessions.get(session_id)
        content_updates: list[
            ContentToolCallContent | FileEditToolCallContent | TerminalToolCallContent
        ] = []
        full_text = ""

        if isinstance(content, list):
            for block in content:
                if isinstance(block, ToolResultBlock):
                    block_text = block.content or ""
                    full_text += block_text
                    if block_text:
                        content_updates.append(
                            ContentToolCallContent(
                                type="content",
                                content=TextContentBlock(type="text", text=block_text),
                            )
                        )

        # Add to state and get accumulated content
        current_content: list[
            ContentToolCallContent | FileEditToolCallContent | TerminalToolCallContent
        ] = []
        if state:
            current_content = state.tool_call_contents.get(tool_use_id, [])
            current_content.extend(content_updates)
            state.tool_call_contents[tool_use_id] = current_content

        if self._conn is not None:
            await self._conn.session_update(
                session_id=session_id,
                update=ToolCallProgress(
                    session_update="tool_call_update",
                    tool_call_id=tool_use_id,
                    title=title,
                    status=status,
                    content=current_content,
                    raw_output={"output": full_text} if full_text else None,
                ),
            )

    async def _emit_system_message(self, msg: SystemMessage, session_id: str) -> None:
        """Emit a SessionInfoUpdate for system messages.

        Args:
            msg: The SDK ``SystemMessage`` (carries a ``subtype`` attribute).
            session_id: The session ID for routing ACP notifications.
        """
        title = str(getattr(msg, "subtype", "system"))
        await self._conn.session_update(
            session_id=session_id,
            update=SessionInfoUpdate(
                session_update="session_info_update",
                title=title,
            ),
        )

    async def _emit_result(self, msg: ResultMessage, session_id: str) -> None:
        """Emit a final SessionInfoUpdate with result summary.

        Args:
            msg: The SDK ``ResultMessage`` containing the final result text.
            session_id: The session ID for routing ACP notifications.
        """
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
    """Entry point for the Claude ACP bridge subprocess.

    Parses CLI arguments, configures logging, and runs the bridge with
    ``acp.run_agent()`` until the connection closes.
    """
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
    try:
        await run_agent(bridge)
    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
