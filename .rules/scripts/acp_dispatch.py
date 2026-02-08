"""ACP Sub-Agent Dispatcher.

A robust, protocol-compliant tool for orchestrating sub-agents via the Agent Client Protocol (ACP).
Features include session persistence, interactive turn-taking, and Windows-specific optimizations.

[WARNING] STATUS: UNVERIFIED
This implementation has not been robustly tested beyond simple scenarios.
Expect potential breaking changes or regressions in complex, multi-turn task runs.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import dataclasses
import datetime
import gc
import json
import os
import pathlib
import re
import sys
import uuid
import warnings
from typing import Any, Dict, Optional, Tuple, Union

# Import local providers package
try:
    from agent_providers.base import AgentProvider
    from agent_providers.gemini import GeminiProvider
    from agent_providers.claude import ClaudeProvider
except ImportError:
    # Fallback for when running from a different directory (though not expected with current setup)
    sys.path.append(str(pathlib.Path(__file__).parent))
    from agent_providers.base import AgentProvider
    from agent_providers.gemini import GeminiProvider
    from agent_providers.claude import ClaudeProvider

from acp import spawn_agent_process, text_block
from acp.client.connection import ClientSideConnection
from acp.interfaces import Client
from acp.schema import (
    AgentMessageChunk,
    AgentPlanUpdate,
    AgentThoughtChunk,
    AvailableCommandsUpdate,
    ClientCapabilities,
    CurrentModeUpdate,
    FileSystemCapability,
    Implementation,
    SessionInfoUpdate,
    TextContentBlock,
    ToolCallProgress,
    ToolCallStart,
    UserMessageChunk,
)

# Silence Windows-specific asyncio transport warnings that trigger during GC
warnings.filterwarnings(
    "ignore", category=ResourceWarning, message="unclosed transport"
)

# Feature gate: ACP session resume (unstable API in acp v0.28+).
# Set PP_DISPATCH_SESSION_RESUME=1 to enable.
_SESSION_RESUME_ENABLED = os.environ.get(
    "PP_DISPATCH_SESSION_RESUME", ""
).lower() in ("1", "true", "yes")

# Constants

def _find_project_root() -> pathlib.Path:
    """Walk up from CWD looking for the git repository root.

    Security-critical: uses CWD as the starting point and walks up to find
    the nearest .git directory, which defines the workspace boundary.
    """
    candidate = pathlib.Path.cwd().resolve()
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            return candidate
        candidate = candidate.parent
    # No .git found — fall back to CWD (non-git usage)
    return pathlib.Path.cwd().resolve()

ROOT_DIR = _find_project_root()

# Provider-specific agent directories, resolved relative to workspace root.
# The canonical source of truth is .rules/agents/; provider dirs are sync mirrors.
AGENT_DIRS = {
    "gemini":      ROOT_DIR / ".gemini" / "agents",
    "claude":      ROOT_DIR / ".claude" / "agents",
    "antigravity": ROOT_DIR / ".agent" / "agents",
    "rules":       ROOT_DIR / ".rules" / "agents",  # canonical fallback
}


class SecurityError(Exception):
    """Raised when a path access violates workspace boundaries."""
    pass


class AgentNotFoundError(Exception):
    """Raised when an agent definition cannot be found."""
    pass


class TaskFileNotFoundError(Exception):
    """Raised when a task file cannot be found."""
    pass


class DispatchError(Exception):
    """Raised when agent dispatch fails."""
    pass


@dataclasses.dataclass(frozen=True)
class DispatchResult:
    """Return value from run_dispatch() containing response text and file write log."""

    response_text: str
    written_files: list[str] = dataclasses.field(default_factory=list)
    session_id: str | None = None


def safe_read_text(path: pathlib.Path) -> str:
    """Reads text from a path after verifying it is within the workspace."""
    resolved_path = path.resolve()
    if not resolved_path.is_relative_to(ROOT_DIR):
        raise SecurityError(f"Attempted to access path outside workspace: {path}")

    if not resolved_path.exists():
        return ""
    return resolved_path.read_text(encoding="utf-8")


def parse_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    """Extracts YAML-style frontmatter from markdown content."""
    frontmatter: Dict[str, str] = {}
    body = content
    match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
    if not match:
        return frontmatter, body

    yaml_content = match.group(1)
    body = match.group(2)
    for line in yaml_content.split("\n"):
        if ":" in line:
            key, value = line.split(":", 1)
            frontmatter[key.strip()] = value.strip()
    return frontmatter, body


def load_agent(agent_name: str, provider_name: str | None = None) -> Tuple[Dict[str, str], str]:
    """Loads an agent definition, searching provider-specific then canonical directories.

    Resolution order:
      1. Provider-specific dir (e.g. .claude/agents/ or .gemini/agents/)
      2. Canonical dir (.rules/agents/)
    """
    search_order: list[pathlib.Path] = []
    if provider_name and provider_name in AGENT_DIRS:
        search_order.append(AGENT_DIRS[provider_name])
    search_order.append(AGENT_DIRS["rules"])

    for agent_dir in search_order:
        agent_path = agent_dir / f"{agent_name}.md"
        if agent_path.exists():
            content = safe_read_text(agent_path)
            meta, persona = parse_frontmatter(content)
            return meta, persona

    searched = ", ".join(str(d) for d in search_order)
    raise AgentNotFoundError(f"Agent '{agent_name}' not found. Searched: {searched}")


def parse_task_file(file_path_str: str) -> Tuple[str, Optional[str]]:
    """Reads a task description from a markdown file."""
    path = pathlib.Path(file_path_str)
    if not path.exists():
        raise TaskFileNotFoundError(f"Task file not found: {path}")

    content = safe_read_text(path)
    agent = None
    match = re.search(r"Agent:\s*([a-zA-Z0-9_-]+)", content)
    if match:
        agent = match.group(1)
    return content, agent


class SessionLogger:
    """Handles persistent logging of agent session events to disk."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.log_dir = ROOT_DIR / ".rules" / "logs"
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / f"{session_id}.log"
        self.start_time = datetime.datetime.now()

    def log(self, event_type: str, data: Any) -> None:
        timestamp = datetime.datetime.now().isoformat()
        log_entry = {"timestamp": timestamp, "type": event_type, "data": data}
        with self.log_file.open("a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry) + "\n")


class _Terminal:
    """Tracks a subprocess spawned via the ACP terminal API."""

    def __init__(self, proc: asyncio.subprocess.Process, byte_limit: int):
        self.proc = proc
        self.output_chunks: list[bytes] = []
        self.total_bytes = 0
        self.byte_limit = byte_limit
        self.reader_task: Optional[asyncio.Task] = None


class GeminiDispatchClient(Client):
    """ACP Client implementation that handles protocol messages."""

    def __init__(self, debug: bool = False, quiet: bool = False, mode: str = "read-write"):
        self.debug = debug
        self.quiet = quiet
        self.mode = mode
        self.response_text = ""
        self.written_files: list[str] = []
        self.logger: Optional[SessionLogger] = None
        self._terminals: Dict[str, _Terminal] = {}
        self.agent_capabilities: Optional[Any] = None
        self._conn: Optional[Any] = None
        self._session_id: Optional[str] = None

    def set_logger(self, logger: SessionLogger) -> None:
        self.logger = logger

    def _log(self, event_type: str, data: Any) -> None:
        if self.logger:
            self.logger.log(event_type, data)

    async def request_permission(
        self, options: Any, session_id: str, tool_call: Any, **kwargs: Any
    ) -> Dict[str, Any]:
        """Auto-approves tool call permissions (Emulates YOLO mode).

        Selects the first 'allow' option per ACP AllowedOutcome schema.
        """
        if self.debug:
            print(f"[DEBUG] Auto-approving tool call: {tool_call}", file=sys.stderr)

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

        return {"outcome": {"outcome": "selected", "optionId": selected_id}}

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        """Handles and displays protocol updates from the agent."""
        data = update.model_dump() if hasattr(update, "model_dump") else str(update)
        self._log("session_update", data)

        if self.debug:
            print(f"[DEBUG] Update Received: {type(update).__name__}", file=sys.stderr)

        if isinstance(update, (AgentMessageChunk, AgentThoughtChunk)):
            self._handle_content_chunk(update)
            return

        if isinstance(update, UserMessageChunk):
            content = update.content
            if isinstance(content, TextContentBlock):
                sys.stderr.write(f"\033[93m{content.text}\033[0m")
                sys.stderr.flush()
            return

        if isinstance(update, (AvailableCommandsUpdate, CurrentModeUpdate, SessionInfoUpdate)):
            if self.debug:
                sys.stderr.write(f"\033[90m[{type(update).__name__}]\033[0m\n")
                sys.stderr.flush()
            return

        if isinstance(update, ToolCallStart):
            sys.stderr.write(
                f"\033[94m[Tool] {update.title} ({update.tool_call_id})\033[0m\n"
            )
            sys.stderr.flush()
            return

        if isinstance(update, ToolCallProgress):
            if update.title or update.status:
                status_str = f" [{update.status}]" if update.status else ""
                sys.stderr.write(
                    f"\033[94m[Tool Update] {update.tool_call_id}{status_str}\033[0m\n"
                )
                sys.stderr.flush()
            return

        if isinstance(update, AgentPlanUpdate):
            sys.stderr.write("\033[96m[Plan Update]\033[0m\n")
            for entry in update.entries:
                status_icon = "✓" if entry.status == "completed" else "○"
                sys.stderr.write(f"  {status_icon} {entry.content}\n")
            sys.stderr.flush()
            return

    def _handle_content_chunk(
        self, update: Union[AgentMessageChunk, AgentThoughtChunk]
    ) -> None:
        content = update.content
        if not isinstance(content, TextContentBlock):
            return

        text = content.text
        if isinstance(update, AgentMessageChunk):
            if not self.quiet:
                sys.stdout.write(text)
                sys.stdout.flush()
            self.response_text += text
        else:
            sys.stderr.write(f"\033[90m{text}\033[0m")
            sys.stderr.flush()

    # -- File I/O (required by ACP Client protocol) --

    async def read_text_file(
        self, path: str, session_id: str, limit: int | None = None, line: int | None = None, **kwargs: Any
    ) -> Dict[str, Any]:
        """Read a text file from the workspace."""
        file_path = pathlib.Path(path).resolve()
        if not file_path.is_relative_to(ROOT_DIR):
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
        return {"content": content}

    async def write_text_file(
        self, content: str, path: str, session_id: str, **kwargs: Any
    ) -> Dict[str, Any] | None:
        """Write a text file to the workspace.

        In read-only mode, only writes to `.docs/` are permitted.
        All other writes are rejected with a ValueError.
        """
        file_path = pathlib.Path(path).resolve()
        if not file_path.is_relative_to(ROOT_DIR):
            raise ValueError(f"Path outside workspace: {path}")

        # Enforce read-only mode: only .docs/ writes allowed.
        if self.mode == "read-only":
            rel_path = file_path.relative_to(ROOT_DIR).as_posix()
            if not rel_path.startswith(".docs/") and not rel_path.startswith(".docs\\"):
                self._log("write_blocked", {"path": path, "reason": "read-only mode"})
                raise ValueError(
                    f"Write rejected: read-only mode only allows writes to .docs/ "
                    f"(attempted: {path})"
                )

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")

        self._log("write_text_file", {"path": path, "size": len(content)})
        self.written_files.append(path)
        return {}

    # -- Terminal management (optional but needed for Claude Code ACP) --

    async def create_terminal(
        self, command: str, session_id: str, args: Any = None, cwd: str | None = None,
        env: Any = None, output_byte_limit: int | None = None, **kwargs: Any,
    ) -> Dict[str, Any]:
        """Spawn a subprocess and track it as an ACP terminal."""
        terminal_id = str(uuid.uuid4())

        cmd_parts = [command] + (args or [])
        env_dict = os.environ.copy()
        if env:
            for var in env:
                env_dict[getattr(var, "name", "")] = getattr(var, "value", "")

        proc = await asyncio.create_subprocess_exec(
            *cmd_parts,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
            cwd=cwd or str(ROOT_DIR),
            env=env_dict,
        )

        terminal = _Terminal(proc, output_byte_limit or 1_000_000)

        async def _reader() -> None:
            assert proc.stdout is not None
            try:
                while True:
                    chunk = await proc.stdout.read(8192)
                    if not chunk:
                        break
                    terminal.output_chunks.append(chunk)
                    terminal.total_bytes += len(chunk)
            except asyncio.CancelledError:
                pass

        terminal.reader_task = asyncio.create_task(_reader())
        self._terminals[terminal_id] = terminal

        if self.debug:
            print(f"[DEBUG] Terminal created: {terminal_id} ({command})", file=sys.stderr)
        self._log("create_terminal", {"terminal_id": terminal_id, "command": command})
        return {"terminalId": terminal_id}

    async def terminal_output(self, session_id: str, terminal_id: str, **kwargs: Any) -> Dict[str, Any]:
        """Return current output from a tracked terminal."""
        terminal = self._terminals.get(terminal_id)
        if terminal is None:
            return {"output": "", "truncated": False}

        raw = b"".join(terminal.output_chunks)
        truncated = len(raw) > terminal.byte_limit
        if truncated:
            raw = raw[-terminal.byte_limit:]

        text = raw.decode("utf-8", errors="replace")
        result: Dict[str, Any] = {"output": text, "truncated": truncated}
        if terminal.proc.returncode is not None:
            result["exitStatus"] = {"exitCode": terminal.proc.returncode}
        return result

    async def wait_for_terminal_exit(self, session_id: str, terminal_id: str, **kwargs: Any) -> Dict[str, Any]:
        """Wait for a terminal process to finish."""
        terminal = self._terminals.get(terminal_id)
        if terminal is None:
            return {"exitCode": None}

        exit_code = await terminal.proc.wait()
        if terminal.reader_task:
            with contextlib.suppress(asyncio.CancelledError):
                await terminal.reader_task
        return {"exitCode": exit_code}

    async def kill_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> Dict[str, Any] | None:
        """Kill a tracked terminal process."""
        terminal = self._terminals.get(terminal_id)
        if terminal is None:
            return {}

        with contextlib.suppress(ProcessLookupError):
            terminal.proc.kill()
        return {}

    async def release_terminal(self, session_id: str, terminal_id: str, **kwargs: Any) -> Dict[str, Any] | None:
        """Release and clean up a tracked terminal."""
        terminal = self._terminals.pop(terminal_id, None)
        if terminal is None:
            return {}

        if terminal.reader_task and not terminal.reader_task.done():
            terminal.reader_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await terminal.reader_task

        if terminal.proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                terminal.proc.kill()
            await terminal.proc.wait()
        return {}

    # -- Extension methods (gracefully handled by router via getattr) --

    async def ext_method(self, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        if self.debug:
            print(f"[DEBUG] Extension method: {method}", file=sys.stderr)
        return {}

    async def ext_notification(self, method: str, params: Dict[str, Any]) -> None:
        if self.debug:
            print(f"[DEBUG] Extension notification: {method}", file=sys.stderr)

    def on_connect(self, conn: Any) -> None:
        pass

    async def graceful_cancel(self) -> None:
        """Send ACP session/cancel notification before termination.

        Gives the agent a chance to clean up before the process is killed.
        """
        if self._conn and self._session_id:
            try:
                await self._conn.cancel(session_id=self._session_id)
            except Exception:
                pass  # Best-effort; process will be killed regardless.


def get_provider_for_model(model_name: Optional[str]) -> AgentProvider:
    """Selects the appropriate provider for the requested model."""
    gemini = GeminiProvider()
    
    # Default to Gemini if no model specified or if model starts with gemini
    if not model_name:
        return gemini
        
    if model_name.startswith("gemini"):
        return gemini
    
    if model_name.startswith("claude"):
        return ClaudeProvider()

    # Fallback to Gemini for unknown models for now
    return gemini


async def run_dispatch(
    agent_name: str, initial_task: str,    model_override: str | None = None,
    provider_override: str | None = None,
    interactive: bool = False,
    debug: bool = False,
    quiet: bool = False,
    mode: str = "read-write",
    client_ref: Optional[list] = None,
    resume_session_id: str | None = None,
) -> DispatchResult:
    """Orchestrates the agent lifecycle with fallback support.

    Args:
        quiet: If True, suppress stdout writes from the ACP client.
            Used when called from MCP server context where stdout is
            reserved for JSON-RPC messages.
        mode: Permission mode ("read-write" or "read-only"). When "read-only",
            file writes outside `.docs/` are rejected at the protocol level.
        client_ref: If provided, a single-element list that will be populated
            with the GeminiDispatchClient instance for external cancellation.
        resume_session_id: If provided and session resume is enabled
            (PP_DISPATCH_SESSION_RESUME=1), attempt to resume this ACP
            session instead of creating a new one.

    Returns:
        A DispatchResult containing the agent's response text and list of written files.

    Raises:
        AgentNotFoundError: If the agent definition cannot be found.
        DispatchError: If agent execution fails with no fallback available.
    """

    current_model = model_override

    # Resolve the initial provider hint for agent definition lookup.
    # provider_override takes precedence, otherwise infer from model_override.
    initial_provider_hint = provider_override
    if not initial_provider_hint and model_override:
        if model_override.startswith("claude"):
            initial_provider_hint = "claude"
        elif model_override.startswith("gemini"):
            initial_provider_hint = "gemini"

    # 1. Load Agent Definition (raises AgentNotFoundError on failure)
    if debug:
        print(f"Loading sub-agent: {agent_name}...", file=sys.stderr)
    meta, persona = load_agent(agent_name, provider_name=initial_provider_hint)
    
    # Determine initial model
    # If provider override is set, we might need to resolve model immediately if model_override is not set?
    if not current_model:
        current_model = meta.get("model", "gemini-2.5-flash") # Default
    
    gemini = GeminiProvider() # Default/Primary provider

    while True:
        # 2. Select Provider
        if provider_override:
            if provider_override == "gemini":
                provider = gemini
            elif provider_override == "claude":
                provider = ClaudeProvider()
            else:
                 provider = gemini
            
            # If provider override mismatches current model type, resolve equivalent.
            # Simple heuristic: if provider is claude but model starts with gemini (or vice versa)
            is_mismatch = (provider.name == "claude" and current_model.startswith("gemini")) or \
                          (provider.name == "gemini" and current_model.startswith("claude"))
            
            if is_mismatch:
                 if debug: print(f"Provider mismatch detected (Provider: {provider.name}, Model: {current_model}). resolving equivalent...", file=sys.stderr)
                 # We need source provider to get capability of current model
                 source_provider = get_provider_for_model(current_model)
                 try:
                     level = source_provider.get_model_capability(current_model)
                 except Exception:
                     level = 2 # Default Medium
                 
                 current_model = provider.get_best_model_for_capability(level)
                 if debug: print(f"Resolved equivalent model: {current_model}", file=sys.stderr)

        else:
            try:
                provider = get_provider_for_model(current_model)
            except ValueError:
                 # Fallback default if unknown model, usually shouldn't happen with get_provider_for_model implementation
                 provider = gemini
        
        if debug:
            print(f"Using provider: {provider.name} with model: {current_model}", file=sys.stderr)
        
        try:
            # 3. Prepare Process
            spec = provider.prepare_process(
                agent_name, meta, persona, initial_task, ROOT_DIR, model_override=current_model
            )
            cleanup_paths = spec.cleanup_paths
            
            if debug:
                 print(
                    f"Spawning agent process: {spec.executable} {' '.join(spec.args)}",
                    file=sys.stderr,
                )
            
            client = GeminiDispatchClient(debug=debug, quiet=quiet, mode=mode)
            if client_ref is not None:
                client_ref.clear()
                client_ref.append(client)
            
            async def _read_stderr(proc: asyncio.subprocess.Process, debug: bool):
                """Consumes stderr to prevent buffer filling and hangs."""
                if proc.stderr:
                    try:
                        while True:
                            line = await proc.stderr.readline()
                            if not line:
                                break
                            if debug:
                                try:
                                    print(f"[AGENT-STDERR] {line.decode().strip()}", file=sys.stderr)
                                except Exception:
                                    pass
                    except asyncio.CancelledError:
                        pass
                    except Exception:
                        pass

            # Main Execution Block
            async with spawn_agent_process(
                client,
                spec.executable,
                *spec.args,
                env=spec.env,
                transport_kwargs={
                    "limit": 100 * 1024 * 1024,      # 100MB limit for large outputs
                    "shutdown_timeout": 5.0,         # 5s grace period for clean exit
                },
            ) as (conn, _proc):
                stderr_task = asyncio.create_task(_read_stderr(_proc, debug))
                
                try:
                    if debug:
                        print("Connected to agent.", file=sys.stderr)
                    # In read-only mode, disable terminal capability and
                    # advertise write_text_file=True (enforced in callback).
                    terminal_enabled = mode != "read-only"
                    init_response = await conn.initialize(
                        protocol_version=1,
                        client_capabilities=ClientCapabilities(
                            fs=FileSystemCapability(
                                read_text_file=True,
                                write_text_file=True,
                            ),
                            terminal=terminal_enabled,
                        ),
                        client_info=Implementation(
                            name="pp-dispatch",
                            version="0.5.0",
                        ),
                    )

                    # Store and log agent capabilities from InitializeResponse.
                    if init_response and hasattr(init_response, "agent_capabilities"):
                        client.agent_capabilities = init_response.agent_capabilities
                        if debug:
                            agent_info = getattr(init_response, "agent_info", None)
                            caps = init_response.agent_capabilities
                            print(
                                f"[DEBUG] Agent info: {agent_info}, "
                                f"capabilities: {caps.model_dump() if caps and hasattr(caps, 'model_dump') else caps}",
                                file=sys.stderr,
                            )

                    # Session creation: resume existing or start new.
                    if _SESSION_RESUME_ENABLED and resume_session_id:
                        try:
                            session = await conn.load_session(
                                session_id=resume_session_id,
                            )
                            if debug:
                                print(
                                    f"Resumed session: {session.session_id}",
                                    file=sys.stderr,
                                )
                        except Exception as exc:
                            if debug:
                                print(
                                    f"Session resume failed ({exc}), creating new session",
                                    file=sys.stderr,
                                )
                            session = await conn.new_session(
                                cwd=str(ROOT_DIR),
                                mcp_servers=getattr(spec, "mcp_servers", []),
                                **getattr(spec, "session_meta", {}),
                            )
                    else:
                        session = await conn.new_session(
                            cwd=str(ROOT_DIR),
                            mcp_servers=getattr(spec, "mcp_servers", []),
                            **getattr(spec, "session_meta", {}),
                        )
                    # Store connection and session_id for graceful cancellation.
                    client._conn = conn
                    client._session_id = session.session_id
                    if debug:
                        print(f"Session started: {session.session_id}", file=sys.stderr)

                    logger = SessionLogger(session.session_id)
                    client.set_logger(logger)
                    if debug:
                        print(f"Logging to: {logger.log_file}", file=sys.stderr)

                    # Interactive Loop
                    start_prompt = getattr(spec, "initial_prompt_override", None) or initial_task
                    
                    await _interactive_loop(
                        conn, session.session_id, agent_name, start_prompt, debug, interactive, _proc, logger
                    )
                    
                    if debug:
                        print("\n[DEBUG] Interaction loop finished. Shutting down...", file=sys.stderr)

                finally:
                    stderr_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await stderr_task
                    
                    # Explicity close all transports to avoid GC-triggered "unclosed transport" warnings on Windows
                    # We do this while the loop is definitely active.
                    if hasattr(_proc, "_transport") and _proc._transport:
                        with contextlib.suppress(Exception):
                            _proc._transport.close()
                    
                    # Close individual pipe transports if accessible
                    for stream_name in ["stdin", "stdout", "stderr"]:
                        stream = getattr(_proc, stream_name, None)
                        if stream and hasattr(stream, "transport"):
                             with contextlib.suppress(Exception):
                                 stream.transport.close()

                    # Yield to allow the close events to be processed
                    await asyncio.sleep(0.1)
                    gc.collect()

            # Final Reap and Loop Drain for Windows
            try:
                # Give it some time to finish any lingering IO
                await asyncio.wait_for(_proc.wait(), timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                with contextlib.suppress(Exception):
                    _proc.kill()
                    await _proc.wait()

            gc.collect()
            await asyncio.sleep(0.5) # Longer grace period for the Proactor loop
            
            if debug:
                print("\nTask completed.", file=sys.stderr)
            return DispatchResult(
                response_text=client.response_text,
                written_files=list(client.written_files),
                session_id=client._session_id,
            )
        except Exception as e:
            # Execution Failed (e.g. Quota exhausted, crash, or prepare failure)
            print(f"\n[Warning] Agent execution failed with {provider.name}: {e}", file=sys.stderr)

            # Fallback Logic:
            # If provider override is set, WE DO NOT FALLBACK (unless user wants resilience even with override? User said "when provided must use provider")
            if provider_override:
                 print(f"Execution failed with forced provider {provider_override}. Fallback disabled.", file=sys.stderr)
                 raise DispatchError(f"Execution failed with provider {provider_override}: {e}") from e

            # Only fallback if primary failure and NO override
            if provider.name == "gemini":
                print("Attempting fallback to Claude...", file=sys.stderr)

                # 1. Determine capability of failed model
                try:
                    level = provider.get_model_capability(current_model)
                except Exception as cap_err:
                    if debug:
                            print(f"Could not determine capability: {cap_err}", file=sys.stderr)
                    # Default to MEDIUM (2) if unsure
                    level = 2

                # 2. Switch Provider
                fallback_provider = ClaudeProvider()
                fallback_model = fallback_provider.get_best_model_for_capability(level)

                current_model = fallback_model
                print(f"Fallback selected: {current_model}", file=sys.stderr)
                continue # Retry loop with new model

            else:
                # No more fallbacks
                print("No further fallback providers available.", file=sys.stderr)
                raise DispatchError(f"Execution failed, no fallback available: {e}") from e
        finally:
            # Cleanup
            if 'cleanup_paths' in locals():
                for path in cleanup_paths:
                    if path.exists():
                        try:
                            path.unlink()
                        except OSError:
                            pass


async def _interactive_loop(
    conn: "ClientSideConnection",
    session_id: str,
    agent_name: str,
    initial_prompt: str | None,
    debug: bool,
    interactive: bool,
    proc: asyncio.subprocess.Process,
    logger: SessionLogger,
) -> None:
    """Run an interactive conversation loop with the agent."""
    current_prompt = initial_prompt
    async def _get_user_input() -> str | None:
        loop = asyncio.get_event_loop()
        try:
            return await loop.run_in_executor(None, sys.stdin.readline)
        except EOFError:
            return None

    while True:
        try:
            # Send prompt and wait for response
            response = await conn.prompt(
                prompt=[TextContentBlock(type="text", text=current_prompt)],
                session_id=session_id,
            )
        except Exception as e:
            if debug:
                print(f"[DEBUG] Prompt failed: {e}", file=sys.stderr)
            # Try to cancel
            with contextlib.suppress(Exception):
                await conn.cancel(session_id=session_id)
            raise

        if logger:
             logger.log("prompt_response", response.model_dump(mode="json"))
        if debug:
            print(f"\n[DEBUG] stop_reason: {response.stop_reason}", file=sys.stderr)

        # In one-shot mode, we always exit after one turn regardless of stop_reason
        # This prevents hanging for user input when it's not expected.
        if not interactive:
            if debug:
                print(f"\n[DEBUG] Turn finished ({response.stop_reason}). Exiting one-shot task.", file=sys.stderr)
            break
        
        # Check if process is still alive
        if proc.returncode is not None:
            if debug:
                print(f"\n[DEBUG] Agent process exited with code {proc.returncode}. Exiting loop.", file=sys.stderr)
            break

        # If we got here, we decide whether to prompt for more input
        if not sys.stdin.isatty():
            if debug:
                print("\n[DEBUG] Not a TTY, breaking loop.", file=sys.stderr)
            break

        print(
            "\nType your response (or press Enter to exit): ", end="", file=sys.stderr
        )
        
        # Wait for either user input or process exit
        input_task = asyncio.create_task(_get_user_input())
        proc_task = asyncio.create_task(proc.wait())
        
        done, pending = await asyncio.wait(
            [input_task, proc_task],
            return_when=asyncio.FIRST_COMPLETED
        )
        
        for t in pending:
            t.cancel()
            
        # Reap pending tasks to avoid loop closure issues
        if pending:
            await asyncio.gather(*pending, return_exceptions=True)

        if input_task in done:
            user_input = await input_task
            if not user_input or not user_input.strip():
                break
            current_prompt = user_input.strip()
        else:
            # Process exited
            if debug:
                print(f"\n[DEBUG] Agent process terminated while waiting for input.", file=sys.stderr)
            break


def list_available_agents() -> list[Dict[str, str]]:
    """List all available agents from .rules/agents/ directory.

    Returns a list of dicts with name, tier, and description for each agent.
    """
    agents_dir = AGENT_DIRS["rules"]
    agents: list[Dict[str, str]] = []

    if not agents_dir.is_dir():
        return agents

    for agent_path in sorted(agents_dir.glob("*.md")):
        try:
            content = safe_read_text(agent_path)
            meta, _body = parse_frontmatter(content)
            description = meta.get("description", "")
            # Strip surrounding quotes from YAML values.
            if len(description) >= 2 and description[0] == '"' and description[-1] == '"':
                description = description[1:-1]
            agents.append({
                "name": agent_path.stem,
                "tier": meta.get("tier", "UNKNOWN"),
                "description": description,
            })
        except Exception as exc:
            agents.append({
                "name": agent_path.stem,
                "tier": "UNKNOWN",
                "description": f"(parse error: {exc})",
            })

    return agents


# Permission prompt injected for read-only mode (CLI).
_CLI_READONLY_PERMISSION_PROMPT = (
    "PERMISSION MODE: READ-ONLY\n"
    "You MUST only write files within the `.docs/` directory. "
    "Do not modify any source code files.\n\n"
)


def main() -> None:
    """CLI Entrypoint for the dispatcher."""
    parser = argparse.ArgumentParser(description="ACP Sub-Agent Dispatcher")
    parser.add_argument("--agent", "-a", help="Sub-agent name")
    parser.add_argument("--task", "-t", help="Task description string")
    parser.add_argument(
        "--task-file", "-f", help="Path to markdown file describing the task"
    )
    parser.add_argument(
        "--model", "-m", help="Override default model"
    )
    parser.add_argument(
        "--provider", "-p", choices=["gemini", "claude", "antigravity"], help="Explicitly force a provider (overrides fallback chain)"
    )
    parser.add_argument(
        "--mode", choices=["read-write", "read-only"],
        default="read-write",
        help="Permission mode for the agent (default: read-write)"
    )
    parser.add_argument(
        "--interactive", "-i", action="store_true", help="Keep the session open for multi-turn interaction."
    )
    parser.add_argument(
        "--list-agents", action="store_true", help="List available agents and exit"
    )
    parser.add_argument(
        "--debug", action="store_true", help="Enable verbose debug output"
    )

    args = parser.parse_args()

    # Handle --list-agents action.
    if args.list_agents:
        agents = list_available_agents()
        if not agents:
            print("No agents found.", file=sys.stderr)
            sys.exit(0)
        for agent in agents:
            print(f"  {agent['name']:30s} [{agent['tier']:6s}]  {agent['description']}")
        sys.exit(0)

    # Require --agent for dispatch operations.
    if not args.agent:
        parser.error("--agent is required (unless using --list-agents)")

    task_context = args.task or ""
    if args.task_file:
        file_content, file_agent = parse_task_file(args.task_file)
        task_context = f"{task_context}\n\n{file_content}".strip()
        if not args.agent and file_agent:
            args.agent = file_agent

    if not task_context:
        print("Error: No task provided via --task or --task-file", file=sys.stderr)
        sys.exit(1)

    # Inject read-only permission prompt when mode is read-only.
    if args.mode == "read-only":
        task_context = _CLI_READONLY_PERMISSION_PROMPT + task_context

    # Final global safety for Windows Proactor cleanup noise
    warnings.simplefilter("ignore", ResourceWarning)

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    try:
        loop.run_until_complete(
            run_dispatch(args.agent, task_context, args.model, args.provider, args.interactive, args.debug, mode=args.mode)
        )
    except (KeyboardInterrupt, SystemExit):
        pass
    except Exception as e:
        print(f"Unhandled error in dispatcher: {e}", file=sys.stderr)
    finally:
        try:
            # Well-orchestrated loop pump to ensure all transports are reaped
            # while the loop is still open and the Proactor can finish its jobs.
            loop.run_until_complete(asyncio.sleep(0.5))

            # Close the loop
            loop.close()
        except Exception:
            pass

        sys.exit(0)


if __name__ == "__main__":
    main()
