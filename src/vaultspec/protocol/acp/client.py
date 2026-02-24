"""ACP client implementation and session event logger for subagent communication."""

from __future__ import annotations

import asyncio
import contextlib
import datetime
import json
import logging
import os
import pathlib
import sys
import uuid
from typing import TYPE_CHECKING, Any

from acp.interfaces import Client
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    AvailableCommandsUpdate,
    CreateTerminalResponse,
    CurrentModeUpdate,
    EnvVariable,
    KillTerminalCommandResponse,
    PermissionOption,
    ReadTextFileResponse,
    ReleaseTerminalResponse,
    RequestPermissionResponse,
    SessionInfoUpdate,
    TerminalExitStatus,
    TerminalOutputResponse,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    ToolCallUpdate,
    UserMessageChunk,
    WaitForTerminalExitResponse,
    WriteTextFileResponse,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from acp.schema import ConfigOptionUpdate, UsageUpdate

from rich.console import Console

logger = logging.getLogger(__name__)

__all__ = ["SessionLogger", "SubagentClient"]

# Shared console for styled agent feed output (stderr, no syntax highlighting)
_console = Console(stderr=True, highlight=False)


class SessionLogger:
    """Handles persistent logging of agent session events to disk."""

    def __init__(self, session_id: str, root_dir: pathlib.Path):
        """Initialise the logger and create the log directory.

        Args:
            session_id: Unique identifier for the session being logged.
            root_dir: Workspace root; logs are written under
                ``{root_dir}/.vaultspec/logs/``.
        """
        self.session_id = session_id
        self.log_dir = root_dir / ".vaultspec" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{session_id}.log"
        self.start_time = datetime.datetime.now()

    def log(self, event_type: str, data: Any) -> None:
        """Append a timestamped JSON event record to the session log file.

        Args:
            event_type: Short label for the event (e.g. ``"session_update"``).
            data: Arbitrary serialisable data to include in the log entry.
        """
        timestamp = datetime.datetime.now().isoformat()
        log_entry = {"timestamp": timestamp, "type": event_type, "data": data}
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")


class _Terminal:
    """Tracks a subprocess spawned via the ACP terminal API."""

    def __init__(self, proc: asyncio.subprocess.Process, byte_limit: int):
        """Initialise terminal tracking for a subprocess.

        Args:
            proc: The running subprocess.
            byte_limit: Maximum bytes of output to retain before truncating.
        """
        self.proc = proc
        self.output_chunks: list[bytes] = []
        self.total_bytes = 0
        self.byte_limit = byte_limit
        self.reader_task: asyncio.Task | None = None


class SubagentClient(Client):
    """ACP Client implementation that handles protocol messages from an agent bridge."""

    def __init__(
        self,
        root_dir: pathlib.Path,
        debug: bool = False,
        quiet: bool = False,
        mode: str = "read-write",
        logger_instance: SessionLogger | None = None,
    ):
        """Initialise the client with workspace settings and optional callbacks.

        Args:
            root_dir: Workspace root directory — all file I/O is scoped here.
            debug: If True, emit verbose debug log messages.
            quiet: If True, suppress informational tool-call log lines.
            mode: Access mode — ``"read-only"`` restricts writes to ``.vault/``.
            logger_instance: Optional pre-configured ``SessionLogger``.
        """
        self.root_dir = root_dir
        self.debug = debug
        self.quiet = quiet
        self.mode = mode
        self.response_text = ""
        self.written_files: list[str] = []
        self.session_logger: SessionLogger | None = logger_instance
        self._terminals: dict[str, _Terminal] = {}
        self.agent_capabilities: Any | None = None
        self._conn: Any | None = None
        self._session_id: str | None = None

        # Callbacks for UI/Output handling
        self.on_message_chunk: Callable[[str], None] | None = None
        self.on_thought_chunk: Callable[[str], None] | None = None
        self.on_tool_update: Callable[[ToolCallStart], None] | None = None

    def set_logger(self, logger_instance: SessionLogger) -> None:
        """Attach a session logger after construction.

        Args:
            logger_instance: The ``SessionLogger`` to use for event logging.
        """
        self.session_logger = logger_instance

    def _log(self, event_type: str, data: Any) -> None:
        """Forward an event to the session logger if one is configured.

        Args:
            event_type: Short label for the event.
            data: Arbitrary data to include in the log entry.
        """
        if self.session_logger:
            self.session_logger.log(event_type, data)

    async def request_permission(
        self,
        options: list[PermissionOption],
        session_id: str,
        tool_call: ToolCallUpdate,
        **kwargs: Any,
    ) -> RequestPermissionResponse:
        """Auto-approves tool call permissions (Emulates YOLO mode).

        Selects the first 'allow' option per ACP AllowedOutcome schema.

        Args:
            options: List of permission options offered by the agent.
            session_id: The current session identifier (unused).
            tool_call: The tool call requiring permission.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``RequestPermissionResponse`` selecting the first allow option,
            or ``"allow"`` if no explicit allow option is found.
        """
        _ = session_id
        _ = kwargs
        if self.debug:
            logger.debug("Auto-approving tool call: %s", tool_call)

        self._log(
            "permission_request",
            {
                "tool_call": tool_call.model_dump()
                if hasattr(tool_call, "model_dump")
                else str(tool_call)
            },
        )

        # ACP requires AllowedOutcome: {outcome: "selected", optionId: <id>}
        selected_id = "allow"
        if options:
            for opt in options:
                opt_kind = getattr(opt, "kind", None)
                if opt_kind in ("allow_once", "allow_always"):
                    selected_id = getattr(opt, "option_id", selected_id)
                    break
            else:
                # No explicit allow option; select the first option
                selected_id = getattr(options[0], "option_id", selected_id)

        # Return typed response
        return RequestPermissionResponse.model_validate(
            {"outcome": {"outcome": "selected", "optionId": selected_id}}
        )

    async def session_update(
        self,
        session_id: str,
        update: UserMessageChunk
        | AgentMessageChunk
        | AgentThoughtChunk
        | ToolCallStart
        | ToolCallProgress
        | AgentPlanUpdate
        | AvailableCommandsUpdate
        | CurrentModeUpdate
        | ConfigOptionUpdate
        | SessionInfoUpdate
        | UsageUpdate,
        **kwargs: Any,
    ) -> None:
        """Handles and displays protocol updates from the agent.

        Args:
            session_id: The session identifier the update belongs to (unused).
            update: The ACP update object received from the agent.
            **kwargs: Additional fields forwarded by the ACP library.
        """
        _ = session_id
        _ = kwargs
        data = update.model_dump() if hasattr(update, "model_dump") else str(update)
        self._log("session_update", data)

        if self.debug:
            logger.debug("Update Received: %s", type(update).__name__)

        if isinstance(update, (AgentMessageChunk, AgentThoughtChunk)):
            self._handle_content_chunk(update)
            return

        # Delegate UI rendering to callbacks or default to styled console
        if isinstance(update, ToolCallStart):
            if self.on_tool_update:
                self.on_tool_update(update)
            elif not self.quiet:
                _console.print(f"({update.title})", style="dim")

    def _handle_content_chunk(
        self, update: AgentMessageChunk | AgentThoughtChunk
    ) -> None:
        """Dispatch a text content chunk to the appropriate callback or logger.

        For ``AgentMessageChunk``, also accumulates text in
        ``self.response_text`` so callers can retrieve the full response.

        Args:
            update: The chunk update from the agent, either a message chunk
                or a thought chunk.
        """
        content = update.content
        if not isinstance(content, TextContentBlock):
            return

        text = content.text
        if isinstance(update, AgentMessageChunk):
            if self.on_message_chunk:
                self.on_message_chunk(text)
            elif not self.quiet:
                _console.print(text, end="")

            self.response_text += text
        else:
            if self.on_thought_chunk:
                self.on_thought_chunk(text)
            elif not self.quiet:
                _console.print(text, style="italic", end="")

    # -- File I/O (required by ACP Client protocol) --

    async def read_text_file(
        self,
        path: str,
        session_id: str,
        limit: int | None = None,
        line: int | None = None,
        **kwargs: Any,
    ) -> ReadTextFileResponse:
        """Read a text file from the workspace.

        Args:
            path: Absolute or workspace-relative path to the file.
            session_id: The current session identifier (unused).
            limit: Maximum number of lines to return.
            line: 1-based line number to start reading from.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``ReadTextFileResponse`` containing the file content.

        Raises:
            ValueError: If ``path`` resolves outside the workspace root.
            FileNotFoundError: If the file does not exist.
        """
        _ = session_id
        _ = kwargs
        file_path = pathlib.Path(path).resolve()
        if not file_path.is_relative_to(self.root_dir):
            raise ValueError(f"Path outside workspace: {path}")

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")

        content = file_path.read_text(encoding="utf-8")

        if line is not None or limit is not None:
            lines = content.splitlines(keepends=True)
            start = (line - 1) if line and line > 0 else 0
            end = (start + limit) if limit else len(lines)
            content = "".join(lines[start:end])

        self._log("read_text_file", {"path": path})
        return ReadTextFileResponse(content=content)

    async def write_text_file(
        self, content: str, path: str, session_id: str, **kwargs: Any
    ) -> WriteTextFileResponse | None:
        """Write a text file to the workspace.

        In read-only mode, only writes to `.vault/` are permitted.
        All other writes are rejected with a ValueError.

        Args:
            content: Text content to write to the file.
            path: Workspace-relative or absolute destination path.
            session_id: The current session identifier (unused).
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``WriteTextFileResponse`` on success, or ``None`` if the write
            was silently skipped.

        Raises:
            ValueError: If ``path`` resolves outside the workspace root, or if
                read-only mode blocks the write target.
        """
        _ = session_id
        _ = kwargs
        file_path = pathlib.Path(path).resolve()
        if not file_path.is_relative_to(self.root_dir):
            raise ValueError(f"Path outside workspace: {path}")

        # Enforce read-only mode: only .vault/ writes allowed.
        if self.mode == "read-only":
            rel_path = file_path.relative_to(self.root_dir).as_posix()
            from ...config import get_config

            _docs_dir = get_config().docs_dir
            docs_prefix = f"{_docs_dir}/"
            docs_prefix_win = f"{_docs_dir}\\"
            if not rel_path.startswith(docs_prefix) and not rel_path.startswith(
                docs_prefix_win
            ):
                self._log("write_blocked", {"path": path, "reason": "read-only mode"})
                raise ValueError(
                    f"Write rejected: read-only mode only allows writes to .vault/ "
                    f"(attempted: {path})"
                )

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        self._log("write_text_file", {"path": path, "size": len(content)})
        self.written_files.append(path)
        return WriteTextFileResponse()

    # -- Terminal management --

    async def create_terminal(
        self,
        command: str,
        session_id: str,
        args: list[str] | None = None,
        cwd: str | None = None,
        env: list[EnvVariable] | None = None,
        output_byte_limit: int | None = None,
        **kwargs: Any,
    ) -> CreateTerminalResponse:
        """Spawn a subprocess and track it as an ACP terminal.

        Args:
            command: Executable to run.
            session_id: The current session identifier (unused).
            args: Additional command-line arguments passed to ``command``.
            cwd: Working directory for the subprocess; defaults to the
                workspace root.
            env: Extra environment variables merged with the current process
                environment.
            output_byte_limit: Maximum bytes of stdout/stderr to retain;
                defaults to the configured ``terminal_output_limit``.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``CreateTerminalResponse`` containing the new terminal ID.

        Raises:
            ValueError: If the client is in read-only mode.
            RuntimeError: On Windows when the event loop is not a
                ``ProactorEventLoop``.
        """
        if self.mode == "read-only":
            raise ValueError(
                "Terminal creation denied: read-only mode "
                "does not permit shell access. "
                "Use read_text_file for file access instead."
            )
        if sys.platform == "win32":
            loop = asyncio.get_running_loop()
            if not isinstance(loop, asyncio.ProactorEventLoop):
                raise RuntimeError(
                    "SubagentClient requires ProactorEventLoop on Windows for"
                    " subprocess support. Set asyncio.WindowsProactorEventLoopPolicy()"
                    " before starting the event loop."
                )
        _ = session_id
        _ = kwargs
        terminal_id = str(uuid.uuid4())

        cmd_parts = [command] + (args or [])
        env_dict = os.environ.copy()
        if env:
            for var in env:
                env_dict[var.name] = var.value

        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd or str(self.root_dir),
            env=env_dict,
        )

        from ...config import get_config

        cfg = get_config()
        terminal = _Terminal(proc, output_byte_limit or cfg.terminal_output_limit)

        async def _reader() -> None:
            """Continuously read stdout chunks into the terminal buffer."""
            assert proc.stdout is not None
            try:
                while True:
                    chunk = await proc.stdout.read(cfg.io_buffer_size)
                    if not chunk:
                        break
                    terminal.output_chunks.append(chunk)
                    terminal.total_bytes += len(chunk)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("Terminal reader error: %s", exc)

        terminal.reader_task = asyncio.create_task(_reader())
        self._terminals[terminal_id] = terminal

        if self.debug:
            logger.debug("Terminal created: %s (%s)", terminal_id, command)
        self._log("create_terminal", {"terminal_id": terminal_id, "command": command})
        return CreateTerminalResponse(terminal_id=terminal_id)

    async def terminal_output(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> TerminalOutputResponse:
        """Return current output from a tracked terminal.

        Args:
            session_id: The current session identifier (unused).
            terminal_id: The terminal ID returned by ``create_terminal``.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``TerminalOutputResponse`` with accumulated stdout/stderr text,
            a ``truncated`` flag if output exceeded the byte limit, and the
            ``exit_status`` if the process has already finished.
        """
        _ = session_id
        _ = kwargs
        terminal = self._terminals.get(terminal_id)

        if terminal is None:
            logger.warning(
                "terminal_output called for unknown terminal_id=%s", terminal_id
            )
            return TerminalOutputResponse(output="", truncated=False)

        raw = b"".join(terminal.output_chunks)

        truncated = len(raw) > terminal.byte_limit

        if truncated:
            raw = raw[-terminal.byte_limit :]

        text = raw.decode("utf-8", errors="replace")

        exit_status = None

        if terminal.proc.returncode is not None:
            exit_status = TerminalExitStatus(exit_code=terminal.proc.returncode)

        return TerminalOutputResponse(
            output=text, truncated=truncated, exit_status=exit_status
        )

    async def wait_for_terminal_exit(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> WaitForTerminalExitResponse:
        """Wait for a terminal process to finish.

        Args:
            session_id: The current session identifier (unused).
            terminal_id: The terminal ID returned by ``create_terminal``.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``WaitForTerminalExitResponse`` containing the process exit code,
            or ``None`` if the terminal ID is unknown.
        """
        _ = session_id
        _ = kwargs
        terminal = self._terminals.get(terminal_id)

        if terminal is None:
            return WaitForTerminalExitResponse(exit_code=None)

        exit_code = await terminal.proc.wait()

        if terminal.reader_task:
            with contextlib.suppress(asyncio.CancelledError):
                await terminal.reader_task

        return WaitForTerminalExitResponse(exit_code=exit_code)

    async def kill_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> KillTerminalCommandResponse:
        """Kill a tracked terminal process.

        Args:
            session_id: The current session identifier (unused).
            terminal_id: The terminal ID returned by ``create_terminal``.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``KillTerminalCommandResponse`` (empty acknowledgement).
        """
        _ = session_id
        _ = kwargs
        terminal = self._terminals.get(terminal_id)
        if terminal is not None:
            with contextlib.suppress(ProcessLookupError):
                from ...orchestration.utils import kill_process_tree
                kill_process_tree(terminal.proc.pid)
                terminal.proc.kill()
            
            # Clean up asyncio subprocess transport to avoid ResourceWarning
            from ...orchestration.utils import cleanup_subprocess_transports
            await cleanup_subprocess_transports(terminal.proc)
        return KillTerminalCommandResponse()

    async def release_terminal(
        self, session_id: str, terminal_id: str, **kwargs: Any
    ) -> ReleaseTerminalResponse:
        """Release and clean up a tracked terminal.

        Cancels the background reader task and kills the process if it is
        still running.

        Args:
            session_id: The current session identifier (unused).
            terminal_id: The terminal ID returned by ``create_terminal``.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            A ``ReleaseTerminalResponse`` (empty acknowledgement).
        """
        _ = session_id
        _ = kwargs
        terminal = self._terminals.pop(terminal_id, None)
        if terminal is not None:
            if terminal.reader_task and not terminal.reader_task.done():
                terminal.reader_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await terminal.reader_task

            if terminal.proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    from ...orchestration.utils import kill_process_tree
                    kill_process_tree(terminal.proc.pid)
                    terminal.proc.kill()
                await terminal.proc.wait()

            # Clean up asyncio subprocess transport to avoid ResourceWarning
            from ...orchestration.utils import cleanup_subprocess_transports
            await cleanup_subprocess_transports(terminal.proc)

        return ReleaseTerminalResponse()

    # -- Extension methods --

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Handle an ACP extension method call.  Returns an empty dict.

        Args:
            method: The extension method name.
            params: Arbitrary parameters sent by the caller.

        Returns:
            An empty dict — no extension methods are implemented.
        """
        _ = params
        if self.debug:
            logger.debug("Extension method: %s", method)
        return {}

    async def ext_notification(self, method: str, params: dict[str, Any]) -> None:
        """Handle an ACP extension notification.  No-op.

        Args:
            method: The extension notification name.
            params: Arbitrary parameters sent by the caller.
        """
        _ = params
        if self.debug:
            logger.debug("Extension notification: %s", method)

    def on_connect(self, conn: Any) -> None:
        """Store the agent-side connection for later use.

        Args:
            conn: The connection object provided by the ACP library.
        """
        self._conn = conn

    async def close(self) -> None:
        """Release all tracked terminals to prevent zombie processes."""
        for terminal_id in list(self._terminals):
            terminal = self._terminals.pop(terminal_id, None)
            if terminal is None:
                continue
            if terminal.reader_task and not terminal.reader_task.done():
                terminal.reader_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await terminal.reader_task
            if terminal.proc.returncode is None:
                with contextlib.suppress(ProcessLookupError):
                    from ...orchestration.utils import kill_process_tree
                    kill_process_tree(terminal.proc.pid)
                    terminal.proc.kill()
                try:
                    await terminal.proc.wait()
                except Exception as exc:
                    logger.debug(
                        "proc.wait() failed for terminal %s: %s",
                        terminal_id,
                        exc,
                    )
            
            # Clean up asyncio subprocess transport to avoid ResourceWarning
            from ...orchestration.utils import cleanup_subprocess_transports
            await cleanup_subprocess_transports(terminal.proc)

    async def graceful_cancel(self) -> None:
        """Send ACP session/cancel notification before termination."""
        if self._conn and self._session_id:
            try:
                await self._conn.cancel(session_id=self._session_id)
            except Exception:
                logger.warning("Failed to send cancel notification", exc_info=True)

    async def call_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        session_id: str,
        **kwargs: Any,
    ) -> Any:
        """Execute a tool call and return the result.

        Args:
            tool_name: The name of the tool to execute (e.g. ``"dispatch_agent"``).
            tool_input: Input parameters for the tool.
            session_id: The active ACP session identifier.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            The tool result dictionary.
        """
        _ = session_id
        _ = kwargs
        
        if tool_name == "dispatch_agent":
            # Simplified direct call to the tool implementation
            from ...mcp_server.subagent_tools import dispatch_agent as _dispatch_impl
            try:
                res_json = await _dispatch_impl(
                    agent=tool_input.get("agent", ""),
                    task=tool_input.get("task", ""),
                    model=tool_input.get("model"),
                    mode=tool_input.get("mode"),
                )
                return json.loads(res_json)
            except Exception as e:
                logger.exception("dispatch_agent tool call failed")
                return {"error": str(e)}
        
        return {"error": f"Tool '{tool_name}' not implemented in SubagentClient"}

    async def call_tool(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        session_id: str,
        **kwargs: Any,
    ) -> Any:
        """Execute a tool call and return the result.

        Supports both the explicit 'dispatch_agent' tool and direct sub-agent
        calls by name (where the sub-agent name is used as the tool title).

        Args:
            tool_name: The name of the tool to execute.
            tool_input: Input parameters for the tool.
            session_id: The active ACP session identifier.
            **kwargs: Additional fields forwarded by the ACP library.

        Returns:
            The tool result dictionary.
        """
        _ = session_id
        _ = kwargs
        
        from ...mcp_server.subagent_tools import dispatch_agent as _dispatch_impl
        
        # 1. Handle explicit dispatch_agent tool
        if tool_name == "dispatch_agent":
            try:
                res_json = await _dispatch_impl(
                    agent=tool_input.get("agent", ""),
                    task=tool_input.get("task", ""),
                    model=tool_input.get("model"),
                    mode=tool_input.get("mode"),
                )
                return json.loads(res_json)
            except Exception as e:
                logger.exception("dispatch_agent tool call failed")
                return {"error": str(e)}
        
        # 2. Handle sub-agents exposed as tools named after themselves
        # SubagentClient allows any tool call to be interpreted as a dispatch
        # if the tool_name matches an available agent.
        try:
            # We use the same dispatch implementation but map tool_name to agent
            res_json = await _dispatch_impl(
                agent=tool_name,
                task=tool_input.get("task", tool_input.get("initial_task", "")),
                model=tool_input.get("model"),
                mode=tool_input.get("mode"),
            )
            return json.loads(res_json)
        except Exception as e:
            # If it's not an agent, fall back to error
            if "not found" in str(e):
                return {"error": f"Tool '{tool_name}' not implemented in SubagentClient"}
            logger.exception("Implicit sub-agent dispatch failed for '%s'", tool_name)
            return {"error": str(e)}
