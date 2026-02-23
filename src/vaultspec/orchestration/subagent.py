"""Subagent dispatch: spawn ACP agent processes and collect their output."""

from __future__ import annotations

import asyncio
import contextlib
import gc
import logging
import sys
import uuid
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pathlib

    from acp.client.connection import ClientSideConnection

    from ..protocol.providers import AgentProvider

from acp import spawn_agent_process
from acp.schema import (
    ClientCapabilities,
    FileSystemCapability,
    Implementation,
    TextContentBlock,
)

from ..vaultcore import parse_frontmatter
from .utils import safe_read_text

__all__ = [
    "AgentNotFoundError",
    "get_provider_for_model",
    "list_available_agents",
    "load_agent",
    "run_subagent",
]

from ..protocol.acp import (
    SubagentClient,
    SubagentError,
    SubagentResult,
)
from ..protocol.acp.client import SessionLogger as _AcpSessionLogger
from ..protocol.providers import ClaudeProvider, GeminiProvider

logger = logging.getLogger(__name__)

# Timeout (seconds) for the ACP handshake sequence (initialize + session setup).
_ACP_HANDSHAKE_TIMEOUT: float = 30.0

_CLAUDE_PATTERNS = ("claude-",)


def list_available_agents(content_root: pathlib.Path) -> None:
    """Print all agent names found under ``content_root/rules/agents/``.

    Args:
        content_root: Root directory of the vaultspec framework content tree.
    """
    agents_dir = content_root / "rules" / "agents"
    if not agents_dir.exists():
        logger.warning("No agents directory found at %s", agents_dir)
        return

    print(f"Agents in {agents_dir}:")
    for agent_file in sorted(agents_dir.glob("*.md")):
        print(f"  {agent_file.stem}")


_GEMINI_PATTERNS = ("gemini-",)


def _kill_process_tree(pid: int) -> None:
    """Kill a process and all its descendants.

    On Windows, asyncio's proc.terminate() kills only the bridge process;
    node.exe children spawned by claude-agent-sdk become orphaned and
    persist indefinitely.  taskkill /F /T kills the entire tree recursively.

    On Unix, orphaned children are reparented to PID 1 and eventually reaped
    by init/systemd, so no intervention is needed.

    Args:
        pid: Process ID of the root process to terminate.
    """
    if sys.platform != "win32":
        return
    import subprocess

    try:
        subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            timeout=5,
        )
    except Exception as exc:
        logger.debug("Process tree kill for PID %s failed: %s", pid, exc)


class AgentNotFoundError(Exception):
    """Raised when an agent definition file cannot be located on disk."""

    pass


def load_agent(
    agent_name: str,
    root_dir: pathlib.Path,
    provider_name: str | None = None,
    *,
    content_root: pathlib.Path | None = None,
) -> tuple[dict[str, str], str]:
    """Load an agent definition, searching provider-specific then canonical directories.

    Resolution order:
    1. ``{agents_base}/{provider_name}/{agent_name}.md`` (provider-specific)
    2. ``{agents_base}/{agent_name}.md`` (canonical fallback)

    Args:
        agent_name: Name of the agent to load (without ``.md`` extension).
        root_dir: Workspace root; used to resolve the framework directory when
            ``content_root`` is not supplied.
        provider_name: Optional provider subdirectory to search first (e.g.
            ``"claude"`` or ``"gemini"``).
        content_root: Explicit content root (e.g. ``.vaultspec/``).  In
            split-root mode agents live under the content tree, not
            ``root_dir``.  When ``None``, falls back to
            ``root_dir / framework_dir``.

    Returns:
        A ``(metadata_dict, persona_text)`` tuple parsed from the agent's
        Markdown frontmatter.

    Raises:
        AgentNotFoundError: If the agent file is not found in any search
            location.
    """
    from ..config import get_config

    if content_root is not None:
        agents_base = content_root / "rules" / "agents"
    else:
        fw_dir = get_config().framework_dir
        agents_base = root_dir / fw_dir / "rules" / "agents"

    searched = []
    # 1. Provider-specific: agents/<provider>/<name>.md
    if provider_name:
        p_path = agents_base / provider_name / f"{agent_name}.md"
        searched.append(p_path)
        if p_path.exists():
            return parse_frontmatter(p_path.read_text(encoding="utf-8"))

    # 2. Canonical: agents/<name>.md
    c_path = agents_base / f"{agent_name}.md"
    searched.append(c_path)
    if c_path.exists():
        return parse_frontmatter(c_path.read_text(encoding="utf-8"))

    raise AgentNotFoundError(f"Agent '{agent_name}' not found. Searched: {searched}")


def get_provider_for_model(model_name: str | None) -> AgentProvider:
    """Select the appropriate provider for the requested model name.

    Matches ``claude-*`` patterns to :class:`ClaudeProvider` and
    ``gemini-*`` patterns to :class:`GeminiProvider`.  Falls back to
    :class:`GeminiProvider` when the model name is ``None`` or unrecognised.

    Args:
        model_name: Model identifier string (e.g. ``"claude-opus-4-6"``).

    Returns:
        An instantiated :class:`AgentProvider` appropriate for the model.
    """
    if not model_name:
        return GeminiProvider()

    if any(p in model_name for p in _CLAUDE_PATTERNS):
        return ClaudeProvider()

    if any(p in model_name for p in _GEMINI_PATTERNS):
        return GeminiProvider()

    # Fallback: default to Gemini
    logger.warning("Unrecognised model '%s', defaulting to GeminiProvider", model_name)
    return GeminiProvider()


def _build_task_prompt(
    goal: str,
    context_files: list[pathlib.Path],
    plan_file: pathlib.Path | None,
    root_dir: pathlib.Path,
) -> str:
    """Construct a structured task prompt from a goal, optional plan, and context files.

    Sections are ordered: plan (if any), context files (if any), then the task
    goal.  Each section is separated by a blank line.

    Args:
        goal: The primary task description for the agent.
        context_files: Additional files whose contents are inlined into the
            prompt under ``# CONTEXT FILES``.
        plan_file: Optional plan document to include under ``# CURRENT PLAN``.
        root_dir: Workspace root passed to :func:`safe_read_text` for safe
            file reading.

    Returns:
        A multi-section Markdown string suitable for use as the agent prompt.
    """
    parts = []

    if plan_file:
        parts.append(f"# CURRENT PLAN\n{safe_read_text(plan_file, root_dir)}")

    if context_files:
        parts.append("# CONTEXT FILES")
        for cf in context_files:
            content = safe_read_text(cf, root_dir)
            parts.append(f"## File: {cf}\n{content}")

    parts.append(f"# TASK\n{goal}")

    return "\n\n".join(parts)


async def _interactive_loop(
    conn: ClientSideConnection,
    session_id: str,
    agent_name: str,
    initial_prompt: str | None,
    debug: bool,
    interactive: bool,
    proc: asyncio.subprocess.Process,
    logger_instance: Any,
) -> None:
    """Run a conversation loop with the agent, optionally accepting stdin input.

    Sends ``initial_prompt`` (if provided), then — when ``interactive`` is
    ``True`` — reads further prompts from stdin until the user types
    ``exit``/``quit``/``bye`` or EOF, or until the agent process exits.

    Args:
        conn: Active ACP client-side connection to the spawned agent process.
        session_id: ACP session identifier for the current session.
        agent_name: Agent name, reserved for future logging use.
        initial_prompt: First prompt to send; skipped when ``None``.
        debug: When ``True``, log agent responses and process exit codes at
            DEBUG level.
        interactive: When ``True``, read additional prompts from stdin after
            the initial prompt.
        proc: The underlying agent subprocess, used to detect early exit.
        logger_instance: Optional session logger; reserved for future event
            logging.
    """
    _ = agent_name
    _ = logger_instance
    current_prompt = initial_prompt
    while True:
        if current_prompt:
            # ACP prompt expects list of content blocks
            prompt_blocks = [TextContentBlock(type="text", text=current_prompt)]
            res = await conn.prompt(prompt=prompt_blocks, session_id=session_id)
            if debug:
                logger.debug("Agent Response: %s", res)

        if not interactive:
            break

        # Check if process is still alive
        if proc.returncode is not None:
            if debug:
                logger.debug("Process exited with %s", proc.returncode)
            break

        try:
            # Using loop.run_in_executor for non-blocking input
            loop = asyncio.get_running_loop()
            user_input = await loop.run_in_executor(None, input, "\nUser: ")
            if user_input.lower() in ("exit", "quit", "bye"):
                break
            current_prompt = user_input
        except EOFError:
            break


async def run_subagent(
    agent_name: str,
    root_dir: pathlib.Path,
    initial_task: str = "",
    context_files: list[pathlib.Path] | None = None,
    plan_file: pathlib.Path | None = None,
    model_override: str | None = None,
    provider_override: str | None = None,
    interactive: bool = False,
    debug: bool = False,
    quiet: bool = False,
    mode: str = "read-write",
    client_ref: list | None = None,
    resume_session_id: str | None = None,
    client_class: type[SubagentClient] = SubagentClient,
    provider_instance: AgentProvider | None = None,
    max_turns: int | None = None,
    budget: float | None = None,
    effort: str | None = None,
    output_format: str | None = None,
    content_root: pathlib.Path | None = None,
    mcp_servers: dict[str, Any] | None = None,
) -> SubagentResult:
    """Orchestrate the full agent lifecycle: load, spawn, converse, and clean up.

    Resolves the provider, loads the agent definition (with provider-specific
    fallback), spawns the ACP agent process, performs the ACP handshake and
    session setup, runs the conversation loop, and then shuts everything down.

    Runtime parameter overrides (``max_turns``, ``budget``, ``effort``,
    ``output_format``) take precedence over values embedded in the agent's
    YAML frontmatter.

    Args:
        agent_name: Name of the agent definition to load (without extension).
        root_dir: Workspace root; passed to the agent process as its ``cwd``.
        initial_task: Task description sent as the first prompt.
        context_files: Extra files whose contents are inlined into the prompt.
        plan_file: Optional plan document inlined before the task prompt.
        model_override: Override the model specified in the agent definition.
        provider_override: Force a specific provider (``"claude"`` or
            ``"gemini"``); takes precedence over model-name detection.
        interactive: When ``True``, read further prompts from stdin after the
            initial task.
        debug: Enable verbose DEBUG-level logging for the session.
        quiet: Suppress non-essential output from the client.
        mode: Filesystem permission mode for the agent (``"read-write"`` or
            ``"read-only"``).
        client_ref: If provided, the constructed :class:`SubagentClient` is
            appended to this list so callers can inspect it after the call.
        resume_session_id: ACP session ID to resume rather than starting a new
            session.
        client_class: :class:`SubagentClient` subclass to instantiate.
        provider_instance: Pre-constructed provider; skips provider resolution
            when supplied.
        max_turns: Override maximum conversation turns from the agent spec.
        budget: Override token/cost budget from the agent spec.
        effort: Override effort level from the agent spec.
        output_format: Override output format from the agent spec.
        content_root: Explicit content root for agent resolution in split-root
            mode.
        mcp_servers: Additional MCP server configurations merged with those
            from the agent spec.

    Returns:
        A :class:`SubagentResult` containing the session ID, concatenated
        response text, and the list of files written by the agent.

    Raises:
        ValueError: If ``max_turns`` is not positive or ``budget`` is negative.
        SubagentError: If the agent process raises an unexpected exception
            during execution.
    """
    if max_turns is not None and max_turns <= 0:
        raise ValueError(f"max_turns must be positive, got {max_turns}")
    if budget is not None and budget < 0:
        raise ValueError(f"budget must be non-negative, got {budget}")

    if context_files is None:
        context_files = []

    current_model = model_override
    effective_mcp_servers = mcp_servers or {}

    # 1. Resolve Provider and Load Agent
    provider_map = {"gemini": GeminiProvider, "claude": ClaudeProvider}
    if provider_instance:
        provider = provider_instance
    elif provider_override and provider_override in provider_map:
        provider = provider_map[provider_override]()
    else:
        provider = get_provider_for_model(current_model)
    try:
        agent_meta, agent_persona = load_agent(
            agent_name,
            root_dir,
            provider_name=provider.name,
            content_root=content_root,
        )
    except AgentNotFoundError:
        # Fallback if provider-specific fails
        agent_meta, agent_persona = load_agent(
            agent_name,
            root_dir,
            content_root=content_root,
        )

    # 1b. Apply runtime overrides (take precedence over YAML defaults)
    if max_turns is not None:
        agent_meta["max_turns"] = str(max_turns)
    if budget is not None:
        agent_meta["budget"] = str(budget)
    if effort is not None:
        agent_meta["effort"] = effort
    if output_format is not None:
        agent_meta["output_format"] = output_format

    # 2. Build Task Context
    task_context = _build_task_prompt(initial_task, context_files, plan_file, root_dir)

    # 3. Prepare Process Spec
    spec = provider.prepare_process(
        agent_name,
        agent_meta,
        agent_persona,
        task_context,
        root_dir,
        model_override=current_model,
        mode=mode,
    )
    # 4. Spawn and Connect
    correlation_id = str(uuid.uuid4())
    logger_instance = _AcpSessionLogger(correlation_id, root_dir)

    client = client_class(
        root_dir=root_dir,
        debug=debug,
        quiet=quiet,
        mode=mode,
        logger_instance=logger_instance,
    )

    # Store client reference if requested
    if client_ref is not None:
        client_ref.append(client)

    background_tasks = set()

    try:
        async with contextlib.AsyncExitStack() as stack:
            # Internal context manager for stderr consumption
            async def _read_stderr(proc: asyncio.subprocess.Process, debug: bool):
                """Consumes stderr to prevent buffer filling and hangs.

                Args:
                    proc: The subprocess whose stderr stream to drain.
                    debug: When ``True``, log each line at DEBUG level.
                """
                if proc.stderr:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        while True:
                            line = await proc.stderr.readline()
                            if not line:
                                break
                            with contextlib.suppress(Exception):
                                text = line.decode().strip()
                                if debug:
                                    logger.debug("[AGENT-STDERR] %s", text)
                                else:
                                    logger.warning("[AGENT-STDERR] %s", text)

            # Main Execution Block
            async with spawn_agent_process(
                client,
                spec.executable,
                *spec.args,
                env=spec.env,
                cwd=str(root_dir),
            ) as (conn, _proc):
                # Start stderr consumer
                t = asyncio.create_task(_read_stderr(_proc, debug))
                background_tasks.add(t)
                t.add_done_callback(background_tasks.discard)

                # Protocol Handshake (ACP spec: protocolVersion=1, uint16)
                try:
                    init_res = await asyncio.wait_for(
                        conn.initialize(
                            protocol_version=1,
                            client_capabilities=ClientCapabilities(
                                terminal=True,
                                fs=FileSystemCapability(
                                    read_text_file=True,
                                    write_text_file=True,
                                ),
                            ),
                            client_info=Implementation(
                                name="vaultspec-mcp",
                                version="0.1.0",
                            ),
                        ),
                        timeout=_ACP_HANDSHAKE_TIMEOUT,
                    )
                except TimeoutError:
                    raise SubagentError(
                        f"Agent '{agent_name}' failed to complete ACP "
                        f"initialize within {_ACP_HANDSHAKE_TIMEOUT:.0f}s "
                        "— the agent process may be stuck on authentication "
                        "or unresponsive"
                    ) from None
                logger.debug("Handshake Result: %s", init_res)

                # Session setup
                # Note: We pass MCP servers if supported by the provider/spec
                spec_mcp_servers = getattr(spec, "mcp_servers", {})
                if isinstance(spec_mcp_servers, list):
                    # Handle legacy list format if any
                    spec_mcp_servers = {
                        s.get("name", str(i)): s for i, s in enumerate(spec_mcp_servers)
                    }

                merged_dict = {**spec_mcp_servers, **effective_mcp_servers}

                # Convert dict to list of objects for ACP protocol
                # Each object must have 'name', 'command', 'args', etc.
                final_mcp_servers_list = []
                for name, config in merged_dict.items():
                    server_obj = dict(config)
                    server_obj["name"] = name

                    # Fix env: ACP expects a list of {'name': ..., 'value': ...}
                    if "env" in server_obj and isinstance(server_obj["env"], dict):
                        server_obj["env"] = [
                            {"name": k, "value": str(v)}
                            for k, v in server_obj["env"].items()
                        ]

                    final_mcp_servers_list.append(server_obj)

                try:
                    if resume_session_id:
                        await asyncio.wait_for(
                            conn.resume_session(
                                cwd=str(root_dir),
                                session_id=resume_session_id,
                                mcp_servers=final_mcp_servers_list,
                            ),
                            timeout=_ACP_HANDSHAKE_TIMEOUT,
                        )
                        session = type(
                            "_Session", (), {"session_id": resume_session_id}
                        )()
                    else:
                        session = await asyncio.wait_for(
                            conn.new_session(
                                cwd=str(root_dir),
                                mcp_servers=final_mcp_servers_list,
                            ),
                            timeout=_ACP_HANDSHAKE_TIMEOUT,
                        )
                except TimeoutError:
                    raise SubagentError(
                        f"Agent '{agent_name}' failed to complete ACP "
                        f"session setup within {_ACP_HANDSHAKE_TIMEOUT:.0f}s "
                        "— the agent process may be stuck on authentication "
                        "or unresponsive"
                    ) from None

                # Initial Task
                initial_prompt = spec.initial_prompt_override or task_context

                # Run conversation loop
                await _interactive_loop(
                    conn=conn,
                    session_id=session.session_id,
                    agent_name=agent_name,
                    initial_prompt=initial_prompt,
                    debug=debug,
                    interactive=interactive,
                    proc=_proc,
                    logger_instance=logger_instance,
                )

                # Shutdown
                await conn.cancel(session_id=session.session_id)

                # Windows: kill the entire bridge process tree so node.exe
                # children (spawned by claude-agent-sdk) don't become orphans.
                _kill_process_tree(_proc.pid)
                try:
                    await asyncio.wait_for(_proc.wait(), timeout=5.0)
                except TimeoutError:
                    _proc.kill()
                    await _proc.wait()

                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t

                return SubagentResult(
                    session_id=session.session_id,
                    response_text=client.response_text,
                    written_files=client.written_files,
                )

    except Exception as exc:
        logger.exception("Subagent execution failed")
        raise SubagentError(f"Subagent execution failed: {exc}") from exc

    finally:
        # Cleanup
        await client.close()

        if "spec" in locals():
            for path in spec.cleanup_paths:
                if path.exists():
                    with contextlib.suppress(OSError):
                        path.unlink()

        # Explicitly clear client callbacks to break potential cycles
        client.on_message_chunk = None
        client.on_thought_chunk = None
        client.on_tool_update = None
        gc.collect()
