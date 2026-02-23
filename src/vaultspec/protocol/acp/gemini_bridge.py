"""ACP bridge server that wraps Gemini CLI.

This module is the ACP server process spawned by ``GeminiProvider``.  It
implements the ACP ``Agent`` protocol interface and proxies prompts to
the Gemini CLI subprocess running in ``--experimental-acp`` mode.

Usage::

    python -m vaultspec.protocol.acp.gemini_bridge --model gemini-2.5-flash

The bridge reads configuration from environment variables (set by the
provider) or from constructor parameters (for testing).  It does NOT
call ``get_config()`` — this decouples the bridge subprocess from the
config system and makes it testable via constructor DI.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import dataclasses
import datetime
import logging
import os
import shutil
import uuid
from typing import TYPE_CHECKING, Any, cast

from acp import PROTOCOL_VERSION, Agent, run_agent, spawn_agent_process
from acp.interfaces import Client
from acp.schema import (
    AgentCapabilities,
    AgentMessageChunk,
    AgentPlanUpdate,
    AuthenticateResponse,
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
    SessionCapabilities,
    SessionForkCapabilities,
    SessionInfo,
    SessionListCapabilities,
    SessionResumeCapabilities,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolKind,
)

from ...logging_config import configure_logging
from ..providers import GeminiModels

if TYPE_CHECKING:
    from collections.abc import Callable

    from acp.schema import ClientCapabilities

logger = logging.getLogger(__name__)

__all__ = ["_ACP_HANDSHAKE_TIMEOUT", "GeminiACPBridge", "main"]

# Timeout (seconds) for the child ACP handshake (initialize + new_session).
# If the Gemini CLI is stuck on OAuth or crashes silently, these calls
# would otherwise block indefinitely.
_ACP_HANDSHAKE_TIMEOUT: float = 30.0


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _map_tool_kind(tool_name: str) -> str:
    """Map a Gemini tool name to an ACP tool kind via substring matching.

    Args:
        tool_name: The raw tool name reported by Gemini (e.g. ``"ReadFile"``).

    Returns:
        An ACP tool kind string such as ``"read"``, ``"edit"``, ``"execute"``,
        or ``"other"`` when no keyword matches.
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
    tool_name: str,
    tool_input: dict[str, Any] | None,
) -> list[Any]:
    """Produce initial ACP content blocks for a tool call.

    For ``Edit``/``MultiEdit`` tools, generates structured diff blocks.

    Args:
        tool_name: The Gemini tool name (e.g. ``"Edit"``, ``"MultiEdit"``).
        tool_input: The raw input dict for the tool call, or ``None``.

    Returns:
        A list of ACP content blocks (e.g. ``FileEditToolCallContent``), or
        an empty list if no structured content applies.
    """
    if tool_input is None:
        return []
    if tool_name in ("Edit", "replace"):
        path = tool_input.get("file_path", tool_input.get("path", ""))
        old = tool_input.get("old_string", tool_input.get("oldText", ""))
        new = tool_input.get("new_string", tool_input.get("newText", ""))
        if path:
            return [
                FileEditToolCallContent(
                    type="diff",
                    path=path,
                    old_text=old,
                    new_text=new,
                ),
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


# ---------------------------------------------------------------------------
# Per-session state
# ---------------------------------------------------------------------------


@dataclasses.dataclass
class _SessionState:
    """Per-session state tracked by the Gemini ACP bridge.

    Attributes:
        session_id: Bridge-level unique session identifier.
        cwd: Working directory for this session.
        model: Gemini model identifier in use.
        mode: Sandboxing mode (``"read-only"`` or ``"read-write"``).
        child_conn: ``ClientSideConnection`` to the child Gemini ACP process.
        child_proc: The running child ``asyncio.subprocess.Process``.
        child_session_id: Session ID assigned by the child ACP server.
        exit_stack: Async exit stack that owns the child process lifetime.
        mcp_servers: ACP MCP server configurations for this session.
        gemini_session_id: Gemini's native session ID if provided by the CLI.
        background_tasks: asyncio tasks (proxy worker, stderr reader) that
            must be cancelled on cleanup.
        created_at: ISO-8601 timestamp of session creation.
        cancel_event: Per-session asyncio event set by ``cancel()`` to
            interrupt the racing ``prompt()`` task.
        tool_call_contents: Accumulated ACP content blocks keyed by
            ``tool_call_id``.
        todo_write_tool_call_ids: IDs of ``TodoWrite`` tool calls that should
            be converted to plan updates rather than tool call events.
    """

    session_id: str
    cwd: str
    model: str
    mode: str
    child_conn: Any  # ClientSideConnection from ACP SDK
    child_proc: Any  # asyncio.subprocess.Process
    child_session_id: str
    exit_stack: contextlib.AsyncExitStack
    mcp_servers: list[Any] = dataclasses.field(default_factory=list)
    gemini_session_id: str | None = None
    background_tasks: list[asyncio.Task[None]] = dataclasses.field(
        default_factory=list,
    )
    created_at: str = dataclasses.field(
        default_factory=lambda: datetime.datetime.now(datetime.UTC).isoformat(),
    )
    cancel_event: asyncio.Event = dataclasses.field(default_factory=asyncio.Event)
    tool_call_contents: dict[str, list[Any]] = dataclasses.field(default_factory=dict)
    todo_write_tool_call_ids: set[str] = dataclasses.field(default_factory=set)


# ---------------------------------------------------------------------------
# Proxy client — forwards child ACP updates to the parent bridge
# ---------------------------------------------------------------------------


class GeminiProxyClient(Client):
    """Proxy client forwarding child session updates to the parent bridge.

    The child Gemini process calls methods on this client (e.g.
    ``session_update``, ``request_permission``).  Session updates are
    queued for async forwarding via a worker task; other calls are
    proxied directly to the parent bridge's connection.
    """

    def __init__(self, bridge: GeminiACPBridge, session_id: str) -> None:
        """Initialise the proxy for the given parent bridge and session.

        Args:
            bridge: The parent ``GeminiACPBridge`` that owns this session.
            session_id: The bridge-level session ID to forward updates to.
        """
        self.bridge = bridge
        self.session_id = session_id
        self._queue: asyncio.Queue[Any] = asyncio.Queue()
        self._worker_task: asyncio.Task[None] | None = None

    def start(self) -> asyncio.Task[None]:
        """Start the worker loop.

        Returns:
            The created ``asyncio.Task`` so the caller can track and cancel it
            during cleanup.
        """
        self._worker_task = asyncio.create_task(self._worker())
        return self._worker_task

    async def _worker(self) -> None:
        """Process queued session updates in order, forwarding each to the bridge."""
        while True:
            try:
                update = await self._queue.get()
                await self.bridge.forward_update(self.session_id, update)
                self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in proxy client worker")

    async def session_update(
        self,
        session_id: str,
        update: Any,
        **kwargs: Any,
    ) -> None:
        """Enqueue a session update for async forwarding to the parent bridge.

        Args:
            session_id: The child session ID (used only for routing context).
            update: The ACP update object to forward.
            **kwargs: Additional fields (ignored).
        """
        await self._queue.put(update)

    async def request_permission(self, **kwargs: Any) -> Any:  # ty: ignore[invalid-method-override]
        """Proxy a permission request to the parent bridge's connection.

        Args:
            **kwargs: Permission request parameters forwarded verbatim.

        Returns:
            The permission response from the parent, or a default ``allow``
            outcome if no parent connection is available.
        """
        if self.bridge._conn:
            return await self.bridge._conn.request_permission(**kwargs)
        return {"outcome": {"outcome": "selected", "optionId": "allow"}}

    async def read_text_file(self, **kwargs: Any) -> Any:  # ty: ignore[invalid-method-override]
        """Proxy a read-text-file request to the parent bridge's connection.

        Args:
            **kwargs: File read parameters forwarded verbatim.

        Returns:
            The ``ReadTextFileResponse`` from the parent, or ``None`` if
            no parent connection is available.
        """
        return (
            await self.bridge._conn.read_text_file(**kwargs)
            if self.bridge._conn
            else None
        )

    async def write_text_file(self, **kwargs: Any) -> Any:  # ty: ignore[invalid-method-override]
        """Proxy a write-text-file request to the parent bridge's connection.

        Args:
            **kwargs: File write parameters forwarded verbatim.

        Returns:
            The ``WriteTextFileResponse`` from the parent, or ``None`` if
            no parent connection is available.
        """
        return (
            await self.bridge._conn.write_text_file(**kwargs)
            if self.bridge._conn
            else None
        )

    async def create_terminal(self, **kwargs: Any) -> Any:  # ty: ignore[invalid-method-override]
        """Proxy a create-terminal request to the parent bridge's connection.

        Args:
            **kwargs: Terminal creation parameters forwarded verbatim.

        Returns:
            The ``CreateTerminalResponse`` from the parent, or ``None``.
        """
        return (
            await self.bridge._conn.create_terminal(**kwargs)
            if self.bridge._conn
            else None
        )

    async def terminal_output(self, **kwargs: Any) -> Any:  # ty: ignore[invalid-method-override]
        """Proxy a terminal-output request to the parent bridge's connection.

        Args:
            **kwargs: Terminal output parameters forwarded verbatim.

        Returns:
            The ``TerminalOutputResponse`` from the parent, or ``None``.
        """
        return (
            await self.bridge._conn.terminal_output(**kwargs)
            if self.bridge._conn
            else None
        )

    async def wait_for_terminal_exit(self, **kwargs: Any) -> Any:  # ty: ignore[invalid-method-override]
        """Proxy a wait-for-terminal-exit request to the parent connection.

        Args:
            **kwargs: Wait parameters forwarded verbatim.

        Returns:
            The ``WaitForTerminalExitResponse`` from the parent, or ``None``.
        """
        return (
            await self.bridge._conn.wait_for_terminal_exit(**kwargs)
            if self.bridge._conn
            else None
        )

    async def kill_terminal(self, **kwargs: Any) -> Any:  # ty: ignore[invalid-method-override]
        """Proxy a kill-terminal request to the parent bridge's connection.

        Args:
            **kwargs: Kill parameters forwarded verbatim.

        Returns:
            The ``KillTerminalCommandResponse`` from the parent, or ``None``.
        """
        return (
            await self.bridge._conn.kill_terminal(**kwargs)
            if self.bridge._conn
            else None
        )

    async def release_terminal(self, **kwargs: Any) -> Any:  # ty: ignore[invalid-method-override]
        """Proxy a release-terminal request to the parent bridge's connection.

        Args:
            **kwargs: Release parameters forwarded verbatim.

        Returns:
            The ``ReleaseTerminalResponse`` from the parent, or ``None``.
        """
        return (
            await self.bridge._conn.release_terminal(**kwargs)
            if self.bridge._conn
            else None
        )


# ---------------------------------------------------------------------------
# Main bridge — all 15 Agent protocol methods
# ---------------------------------------------------------------------------


class GeminiACPBridge(Agent):
    """ACP ``Agent`` implementation that wraps the Gemini CLI.

    This class implements the ``acp.interfaces.Agent`` protocol.  When
    used with ``acp.run_agent()`` or ``AgentSideConnection``, the ACP
    library handles all JSON-RPC framing and method dispatch.

    The lifecycle is:

    1. ``on_connect`` — receives the ``conn`` (``Client`` interface)
    2. ``initialize`` — returns bridge capabilities
    3. ``new_session`` — spawns a Gemini CLI child process via ACP
    4. ``prompt`` — proxies to child, races against cancel event
    5. ``cancel`` — sets cancel event and delegates to child

    Parameters
    ----------
    model:
        Gemini model identifier (e.g. ``GeminiModels.LOW``).
    debug:
        Enable verbose debug logging.
    spawn_fn:
        Callable for spawning the child process.  Defaults to
        ``spawn_agent_process`` from the ACP SDK.  Override in tests.
    gemini_path:
        Explicit path to the ``gemini`` CLI binary.  If ``None``,
        resolved via ``shutil.which("gemini")``.  Override in tests
        to skip CLI resolution.
    mode:
        Sandboxing mode: ``"read-only"`` or ``"read-write"``.
        Falls back to ``VAULTSPEC_AGENT_MODE`` env var.
    root_dir:
        Workspace root directory.
        Falls back to ``VAULTSPEC_ROOT_DIR`` env var.
    allowed_tools:
        List of allowed tool names.
        Falls back to ``VAULTSPEC_ALLOWED_TOOLS`` env var.
    approval_mode:
        Gemini approval mode (``default|auto_edit|yolo|plan``).
        Falls back to ``VAULTSPEC_GEMINI_APPROVAL_MODE`` env var.
    output_format:
        Output format (``text|json|stream-json``).
        Falls back to ``VAULTSPEC_OUTPUT_FORMAT`` env var.
    """

    def __init__(
        self,
        *,
        model: str = GeminiModels.LOW,
        debug: bool = False,
        spawn_fn: Callable[..., Any] | None = None,
        gemini_path: str | None = None,
        mode: str | None = None,
        root_dir: str | None = None,
        allowed_tools: list[str] | None = None,
        approval_mode: str | None = None,
        output_format: str | None = None,
        include_dirs: list[str] | None = None,
    ) -> None:
        """Initialise the bridge with Gemini CLI configuration.

        Config parameters default to ``None`` which causes them to be resolved
        from environment variables.  Constructor params always take precedence.

        Args:
            model: Gemini model identifier (e.g. ``GeminiModels.LOW``).
            debug: If True, emit verbose debug log messages.
            spawn_fn: Callable for spawning the child ACP process.  Defaults
                to ``spawn_agent_process`` from the ACP SDK.
            gemini_path: Explicit path to the Gemini CLI binary.  If ``None``,
                resolved via ``shutil.which("gemini")``.
            mode: Sandboxing mode — ``"read-only"`` or ``"read-write"``.
                Falls back to ``VAULTSPEC_AGENT_MODE`` env var.
            root_dir: Workspace root directory.  Falls back to
                ``VAULTSPEC_ROOT_DIR`` env var.
            allowed_tools: Allow-list of tool names forwarded to the CLI.
                Falls back to ``VAULTSPEC_ALLOWED_TOOLS`` env var.
            approval_mode: Gemini approval mode (``default|auto_edit|yolo|plan``).
                Falls back to ``VAULTSPEC_GEMINI_APPROVAL_MODE`` env var.
            output_format: Output format (``text|json|stream-json``).
                Falls back to ``VAULTSPEC_OUTPUT_FORMAT`` env var.
            include_dirs: Additional directories to include in the CLI context.
                Falls back to ``VAULTSPEC_INCLUDE_DIRS`` env var.
        """
        self._model = model
        self._debug = debug
        self._spawn_fn = spawn_fn or spawn_agent_process
        self._gemini_path = gemini_path

        # Set by on_connect
        self._conn: Any = None
        self._client_capabilities: ClientCapabilities | None = None

        # Session state
        self._sessions: dict[str, _SessionState] = {}

        # Config: constructor param > env var > default
        self._root_dir = root_dir or os.environ.get("VAULTSPEC_ROOT_DIR", ".")
        self._mode = mode or os.environ.get("VAULTSPEC_AGENT_MODE", "read-write")

        if allowed_tools is not None:
            self._allowed_tools = allowed_tools
        else:
            env_tools = os.environ.get("VAULTSPEC_ALLOWED_TOOLS", "")
            self._allowed_tools = [t.strip() for t in env_tools.split(",") if t.strip()]

        self._approval_mode = approval_mode or os.environ.get(
            "VAULTSPEC_GEMINI_APPROVAL_MODE"
        )
        self._output_format = output_format or os.environ.get("VAULTSPEC_OUTPUT_FORMAT")

        if include_dirs is not None:
            self._include_dirs = include_dirs
        else:
            env_dirs = os.environ.get("VAULTSPEC_INCLUDE_DIRS", "")
            self._include_dirs = [d.strip() for d in env_dirs.split(",") if d.strip()]

    # -- Protocol: on_connect -----------------------------------------------

    def on_connect(self, conn: Any) -> None:
        """Store the client-side connection for sending notifications.

        Args:
            conn: The ``Client`` connection provided by the ACP library after
                the agent handshake completes.
        """
        self._conn = conn

    # -- Protocol: initialize -----------------------------------------------

    async def initialize(
        self,
        protocol_version: int,
        client_capabilities: Any = None,
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
        self._client_capabilities = client_capabilities
        return InitializeResponse(
            protocol_version=PROTOCOL_VERSION,
            agent_info=Implementation(name="gemini-acp-bridge", version="0.1.0"),
            agent_capabilities=AgentCapabilities(
                load_session=True,
                session_capabilities=SessionCapabilities(
                    fork=SessionForkCapabilities(),
                    list=SessionListCapabilities(),
                    resume=SessionResumeCapabilities(),
                ),
                prompt_capabilities=PromptCapabilities(
                    image=True,
                    audio=True,
                    embedded_context=True,
                ),
            ),
        )

    # -- Internal: spawn + cleanup helpers ----------------------------------

    async def _spawn_child_session(
        self,
        session_id: str,
        cwd: str,
        model: str,
        mode: str,
        mcp_servers: list[Any] | None = None,
    ) -> _SessionState:
        """Spawn a Gemini child process and create an ACP session.

        Resolves the CLI path, builds args, spawns via ``spawn_fn``,
        performs the ACP handshake, and returns a fully initialised
        ``_SessionState``.

        Args:
            session_id: Bridge-level session ID to assign to the new state.
            cwd: Working directory passed to the Gemini CLI subprocess.
            model: Gemini model identifier (e.g. ``GeminiModels.LOW``).
            mode: Sandboxing mode — ``"read-only"`` or ``"read-write"``.
            mcp_servers: Optional ACP MCP server configurations forwarded to
                the child process.

        Returns:
            A fully initialised ``_SessionState`` with a live child connection.

        Raises:
            FileNotFoundError: If the ``gemini`` CLI binary cannot be located.
        """
        gemini_path = self._gemini_path or shutil.which("gemini")
        if gemini_path is None:
            raise FileNotFoundError(
                "Cannot locate 'gemini' CLI. Install it or ensure it is on PATH."
            )

        args: list[str] = ["--experimental-acp", "--model", model]
        if mode == "read-only":
            args.append("--sandbox")
        for tool in self._allowed_tools:
            args.extend(["--allowed-tools", tool])
        if self._approval_mode:
            args.extend(["--approval-mode", self._approval_mode])
        if self._output_format:
            args.extend(["--output-format", self._output_format])
        for d in self._include_dirs:
            args.extend(["--include-directories", d])

        # Forward Gemini-specific env vars to the child process so auth
        # and system prompt configuration reach the CLI.  The ACP SDK's
        # default_environment() only inherits platform-safe variables.
        child_env: dict[str, str] = {}
        for key, value in os.environ.items():
            if key.startswith("GEMINI_") or key == "GOOGLE_API_KEY":
                child_env[key] = value

        proxy_client = GeminiProxyClient(self, session_id)

        stack = contextlib.AsyncExitStack()
        child_conn, proc = await stack.enter_async_context(
            self._spawn_fn(
                proxy_client,
                gemini_path,
                *args,
                cwd=cwd,
                env=child_env,
            ),
        )

        bg_tasks: list[asyncio.Task[None]] = []
        worker_task = proxy_client.start()
        bg_tasks.append(worker_task)

        # Track whether the handshake has completed so the stderr reader
        # can downgrade from WARNING to DEBUG once the session is live.
        handshake_done = asyncio.Event()

        if proc.stderr:

            async def _read_stderr(p: Any) -> None:
                """Drain stderr from the child process.

                During the spawn/handshake phase, lines are logged at WARNING
                so that authentication failures are visible.  After the
                handshake succeeds, the level drops to DEBUG.

                Args:
                    p: The subprocess whose stderr stream to read.
                """
                try:
                    while True:
                        line = await p.stderr.readline()
                        if not line:
                            break
                        text = line.decode().strip()
                        if not text:
                            continue
                        if handshake_done.is_set():
                            if self._debug:
                                logger.debug("[GEMINI-STDERR] %s", text)
                        else:
                            logger.warning("[GEMINI-STDERR] %s", text)
                except Exception as exc:
                    logger.debug("Stderr reader error: %s", exc)

            bg_tasks.append(asyncio.create_task(_read_stderr(proc)))

        try:
            try:
                await asyncio.wait_for(
                    child_conn.initialize(
                        protocol_version=1,
                        client_capabilities=self._client_capabilities,
                        client_info=Implementation(
                            name="gemini-bridge-proxy",
                            version="0.1.0",
                        ),
                    ),
                    timeout=_ACP_HANDSHAKE_TIMEOUT,
                )
            except TimeoutError:
                raise TimeoutError(
                    "Gemini CLI failed to complete ACP initialize within "
                    f"{_ACP_HANDSHAKE_TIMEOUT:.0f}s — check authentication "
                    "and ensure the 'gemini' CLI is responsive"
                ) from None

            try:
                child_session = await asyncio.wait_for(
                    child_conn.new_session(
                        cwd=cwd,
                        mcp_servers=mcp_servers,
                    ),
                    timeout=_ACP_HANDSHAKE_TIMEOUT,
                )
            except TimeoutError:
                raise TimeoutError(
                    "Gemini CLI failed to complete ACP new_session within "
                    f"{_ACP_HANDSHAKE_TIMEOUT:.0f}s — check authentication "
                    "and ensure the 'gemini' CLI is responsive"
                ) from None

            handshake_done.set()
        except BaseException:
            for t in bg_tasks:
                if not t.done():
                    t.cancel()
            for t in bg_tasks:
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await t
            with contextlib.suppress(Exception):
                await stack.aclose()
            raise

        if self._debug:
            logger.debug(
                "Child session created: %s (bridge session: %s)",
                child_session.session_id,
                session_id,
            )

        return _SessionState(
            session_id=session_id,
            cwd=cwd,
            model=model,
            mode=mode,
            child_conn=child_conn,
            child_proc=proc,
            child_session_id=child_session.session_id,
            exit_stack=stack,
            mcp_servers=list(mcp_servers or []),
            background_tasks=bg_tasks,
        )

    async def _cleanup_session(self, state: _SessionState) -> None:
        """Cancel background tasks and close the exit stack.

        Args:
            state: The ``_SessionState`` to clean up.
        """
        for task in state.background_tasks:
            if not task.done():
                task.cancel()
        for task in state.background_tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        with contextlib.suppress(Exception):
            await state.exit_stack.aclose()

    # -- Protocol: new_session ----------------------------------------------

    async def new_session(
        self,
        cwd: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> NewSessionResponse:
        """Spawn a Gemini CLI child process and open an ACP session.

        Args:
            cwd: Working directory for the child process.
            mcp_servers: Optional ACP MCP server configurations forwarded to
                the child.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``NewSessionResponse`` containing the new session ID.
        """
        session_id = str(uuid.uuid4())

        if self._debug:
            logger.debug("Creating new bridge session: %s", session_id)

        state = await self._spawn_child_session(
            session_id,
            cwd,
            self._model,
            self._mode,
            mcp_servers,
        )
        self._sessions[session_id] = state

        return NewSessionResponse(session_id=session_id)

    # -- Protocol: prompt ---------------------------------------------------

    async def prompt(
        self,
        prompt: list[Any],
        session_id: str,
        **kwargs: Any,
    ) -> PromptResponse:
        """Proxy a prompt to the child Gemini process and return its response.

        Races the child prompt coroutine against a per-session cancel event
        so that ``cancel()`` can interrupt a long-running request immediately.
        If the child raises, the error is emitted as an ``AgentMessageChunk``
        and the method returns with ``stop_reason="end_turn"``.

        Args:
            prompt: List of ACP content blocks to forward to the child.
            session_id: The session ID returned by ``new_session``.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``PromptResponse`` with ``stop_reason`` set to ``"end_turn"``
            or ``"cancelled"``.

        Raises:
            RuntimeError: If the session ID is not active.
        """
        state = self._sessions.get(session_id)
        if not state:
            raise RuntimeError(f"Session {session_id} not active")

        state.cancel_event.clear()
        state.todo_write_tool_call_ids.clear()
        state.tool_call_contents.clear()

        # Race the child prompt against the cancel event so that
        # cancel() can interrupt a long-running prompt.
        prompt_task = asyncio.create_task(
            state.child_conn.prompt(
                prompt=prompt,
                session_id=state.child_session_id,
            ),
        )
        cancel_task = asyncio.create_task(state.cancel_event.wait())

        done, pending = await asyncio.wait(
            {prompt_task, cancel_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        for task in pending:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        if cancel_task in done:
            return PromptResponse(stop_reason="cancelled")

        # If the child prompt raised, recover gracefully by emitting the
        # error as an AgentMessageChunk and returning a normal end_turn.
        exc = prompt_task.exception()
        if exc is not None:
            logger.exception(
                "Child prompt error in session %s",
                session_id,
                exc_info=exc,
            )
            if self._conn is not None:
                error_text = str(exc) or "Unknown error"
                try:
                    await self._conn.session_update(
                        session_id=session_id,
                        update=AgentMessageChunk(
                            session_update="agent_message_chunk",
                            content=TextContentBlock(
                                type="text",
                                text=error_text,
                            ),
                        ),
                    )
                except Exception:
                    logger.debug("Failed to emit error as AgentMessageChunk")
            return PromptResponse(stop_reason="end_turn")

        return prompt_task.result()

    # -- Forwarding: child → parent -----------------------------------------

    async def forward_update(self, session_id: str, update: Any) -> None:
        """Forward a session update from the child to the parent connection.

        Args:
            session_id: The bridge-level session ID the update belongs to.
            update: The ACP update object received from the child process.
        """
        if not self._conn:
            return
        state = self._sessions.get(session_id)
        if not state:
            await self._conn.session_update(
                session_id=session_id,
                update=update,
            )
            return
        if isinstance(update, ToolCallStart):
            await self._emit_tool_call(state, session_id, update)
        elif isinstance(update, ToolCallProgress):
            await self._emit_tool_call_update(state, session_id, update)
        else:
            await self._conn.session_update(
                session_id=session_id,
                update=update,
            )

    async def _emit_tool_call(
        self,
        state: _SessionState,
        session_id: str,
        update: ToolCallStart,
    ) -> None:
        """Enrich and emit a ToolCallStart.

        Converts TodoWrite to ``AgentPlanUpdate`` instead of dropping it.
        Maps tool kind via ``_map_tool_kind`` and generates diff content
        for Edit/MultiEdit tools.

        Args:
            state: The active session state for the current session.
            session_id: The bridge-level session ID to forward the update to.
            update: The ``ToolCallStart`` event from the child process.
        """
        if update.title == "TodoWrite":
            state.todo_write_tool_call_ids.add(update.tool_call_id)
            todos = (update.raw_input or {}).get("todos", [])
            if todos and self._conn:
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
            return

        if not update.kind or update.kind == "other":
            update.kind = cast("ToolKind", _map_tool_kind(update.title))

        content = _get_tool_call_content(update.title, update.raw_input)
        if content:
            state.tool_call_contents[update.tool_call_id] = content
            update.content = content

        await self._conn.session_update(
            session_id=session_id,
            update=update,
        )

    async def _emit_tool_call_update(
        self,
        state: _SessionState,
        session_id: str,
        update: ToolCallProgress,
    ) -> None:
        """Accumulate content and emit a ToolCallProgress.

        Args:
            state: The active session state for the current session.
            session_id: The bridge-level session ID to forward the update to.
            update: The ``ToolCallProgress`` event from the child process.
        """
        if update.tool_call_id in state.todo_write_tool_call_ids:
            return
        if update.content:
            current = state.tool_call_contents.get(update.tool_call_id, [])
            current.extend(update.content)
            state.tool_call_contents[update.tool_call_id] = current
            update.content = current
        await self._conn.session_update(
            session_id=session_id,
            update=update,
        )

    # -- Protocol: cancel ---------------------------------------------------

    async def cancel(self, session_id: str, **kwargs: Any) -> None:
        """Cancel a running prompt.

        Sets the per-session cancel event (which causes the ``prompt()``
        ``asyncio.wait`` to return early) and delegates to the child.

        Args:
            session_id: The session ID whose active prompt should be cancelled.
            **kwargs: Additional fields forwarded by the ACP library.
        """
        state = self._sessions.get(session_id)
        if not state:
            return
        state.cancel_event.set()
        with contextlib.suppress(Exception):
            await state.child_conn.cancel(
                session_id=state.child_session_id,
            )

    # -- Protocol: authenticate ---------------------------------------------

    async def authenticate(
        self,
        method_id: str,
        **kwargs: Any,
    ) -> AuthenticateResponse | None:
        """Gemini auth is env-based, not ACP-negotiated.

        Args:
            method_id: The authentication method identifier requested by the
                client (ignored — Gemini uses environment-variable auth).
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            An empty ``AuthenticateResponse`` to satisfy the protocol contract.
        """
        if self._debug:
            logger.debug(
                "authenticate(method=%s) — env-based, no ACP negotiation",
                method_id,
            )
        return AuthenticateResponse()

    # -- Protocol: load_session ---------------------------------------------

    async def load_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> LoadSessionResponse | None:
        """Load a previously created session by ID.

        If the child process is alive, reuses the existing connection.
        If the child has exited, respawns with stored configuration.
        If the session is not found, creates a recovery session.

        Args:
            cwd: Working directory used if a new child process must be spawned.
            session_id: The bridge-level session ID to load.
            mcp_servers: Optional MCP server configurations; falls back to the
                ones stored on the existing session state.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``LoadSessionResponse`` on success.
        """
        state = self._sessions.get(session_id)

        if state is None:
            if self._debug:
                logger.debug(
                    "load_session(%s) — not found, creating recovery",
                    session_id,
                )
            state = await self._spawn_child_session(
                session_id,
                cwd,
                self._model,
                self._mode,
                mcp_servers,
            )
            self._sessions[session_id] = state
            return LoadSessionResponse()

        # Child still alive — reuse
        if state.child_proc.returncode is None:
            if self._debug:
                logger.debug(
                    "load_session(%s) — child alive, reusing",
                    session_id,
                )
            return LoadSessionResponse()

        # Child dead — respawn with stored config
        if self._debug:
            logger.debug(
                "load_session(%s) — child dead, respawning",
                session_id,
            )

        await self._cleanup_session(state)

        effective_mcp = mcp_servers if mcp_servers is not None else state.mcp_servers
        new_state = await self._spawn_child_session(
            session_id,
            cwd,
            state.model,
            state.mode,
            effective_mcp,
        )
        self._sessions[session_id] = new_state

        return LoadSessionResponse()

    # -- Protocol: list_sessions --------------------------------------------

    async def list_sessions(
        self,
        cursor: str | None = None,
        cwd: str | None = None,
        **kwargs: Any,
    ) -> ListSessionsResponse:
        """List all tracked sessions, optionally filtered by ``cwd``.

        Args:
            cursor: Pagination cursor (not currently used).
            cwd: If provided, only sessions whose working directory matches
                this value are returned.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``ListSessionsResponse`` containing matching ``SessionInfo``
            entries.
        """
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
                ),
            )
        return ListSessionsResponse(sessions=sessions)

    # -- Protocol: fork_session ---------------------------------------------

    async def fork_session(
        self,
        cwd: str,
        session_id: str,
        mcp_servers: list[Any] | None = None,
        **kwargs: Any,
    ) -> ForkSessionResponse:
        """Fork an existing session into a new independent session.

        Args:
            cwd: Working directory for the forked child process.
            session_id: The source session ID to fork from.
            mcp_servers: Optional MCP server configurations; falls back to
                those of the source session.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``ForkSessionResponse`` containing the new session ID.

        Raises:
            RuntimeError: If the source session ID is not found.
        """
        source = self._sessions.get(session_id)
        if source is None:
            raise RuntimeError(
                f"Cannot fork: session {session_id!r} not found",
            )

        new_id = str(uuid.uuid4())
        effective_mcp = mcp_servers if mcp_servers is not None else source.mcp_servers

        state = await self._spawn_child_session(
            new_id,
            cwd,
            source.model,
            source.mode,
            effective_mcp,
        )
        self._sessions[new_id] = state

        if self._debug:
            logger.debug("fork_session(%s) → %s", session_id, new_id)

        return ForkSessionResponse(session_id=new_id)

    # -- Protocol: set_session_mode -----------------------------------------

    async def set_session_mode(
        self,
        mode_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> None:
        """Store the new mode for the next child spawn.

        Args:
            mode_id: New sandboxing mode — ``"read-only"`` or ``"read-write"``.
            session_id: The session ID whose mode should be updated.
            **kwargs: Additional fields forwarded by the ACP library.
        """
        state = self._sessions.get(session_id)
        if state:
            state.mode = mode_id
        if self._debug:
            logger.debug("Session mode changed to: %s", mode_id)

    # -- Protocol: set_session_model ----------------------------------------

    async def set_session_model(
        self,
        model_id: str,
        session_id: str,
        **kwargs: Any,
    ) -> None:
        """Store the new model for the next child spawn.

        Args:
            model_id: Gemini model identifier (e.g. ``GeminiModels.LOW``).
            session_id: The session ID whose model should be updated.
            **kwargs: Additional fields forwarded by the ACP library.
        """
        state = self._sessions.get(session_id)
        if state:
            state.model = model_id
        if self._debug:
            logger.debug("Session model changed to: %s", model_id)

    # -- Protocol: set_config_option ----------------------------------------

    async def set_config_option(
        self,
        config_id: str,
        session_id: str,
        value: str,
        **_kwargs: Any,
    ) -> None:
        """No-op for Gemini bridge.

        Args:
            config_id: The configuration option identifier (logged when debug
                is enabled, otherwise ignored).
            session_id: The session ID for this configuration change (unused).
            value: The new configuration value (logged when debug is enabled).
            **_kwargs: Additional fields forwarded by the ACP library.
        """
        if self._debug:
            logger.debug(
                "set_config_option(%s=%s) — no-op",
                config_id,
                value,
            )

    # -- Protocol: ext_method / ext_notification ----------------------------

    async def ext_method(
        self,
        method: str,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        """Handle an ACP extension method call.  Returns an empty dict.

        Args:
            method: The extension method name.
            params: Arbitrary parameters sent by the caller.

        Returns:
            An empty dict — no extension methods are implemented.
        """
        if self._debug:
            logger.debug("ext_method: %s", method)
        return {}

    async def ext_notification(
        self,
        method: str,
        params: dict[str, Any],
    ) -> None:
        """Handle an ACP extension notification.  No-op.

        Args:
            method: The extension notification name.
            params: Arbitrary parameters sent by the caller.
        """
        if self._debug:
            logger.debug("ext_notification: %s", method)

    # -- Protocol: close ----------------------------------------------------

    async def close(self) -> None:
        """Close all active sessions and release resources."""
        for state in list(self._sessions.values()):
            await self._cleanup_session(state)
        self._sessions.clear()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    """Entry point for the Gemini ACP bridge subprocess.

    Parses CLI arguments, configures logging, and runs the bridge with
    ``acp.run_agent()`` until the connection closes.
    """
    parser = argparse.ArgumentParser(description="Gemini ACP Bridge")
    parser.add_argument(
        "--model",
        default=GeminiModels.LOW,
        help=f"Gemini model to use (default: {GeminiModels.LOW})",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    args = parser.parse_args()

    configure_logging(debug=args.debug)

    bridge = GeminiACPBridge(model=args.model, debug=args.debug)
    try:
        await run_agent(bridge, use_unstable_protocol=True)
    finally:
        await bridge.close()


if __name__ == "__main__":
    asyncio.run(main())
