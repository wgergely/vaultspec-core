from __future__ import annotations

import asyncio
import contextlib
import gc
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pathlib

    from acp.client.connection import ClientSideConnection

    from protocol.providers.base import AgentProvider

from acp import spawn_agent_process
from acp.schema import (
    ClientCapabilities,
    FileSystemCapability,
    Implementation,
    TextContentBlock,
)
from vault.parser import parse_frontmatter

from orchestration.utils import safe_read_text
from protocol.acp.client import SessionLogger, SubagentClient
from protocol.acp.types import SubagentResult
from protocol.providers.claude import ClaudeProvider
from protocol.providers.gemini import GeminiProvider

logger = logging.getLogger(__name__)

_CLAUDE_PATTERNS = ("claude-",)
_GEMINI_PATTERNS = ("gemini-",)


class AgentNotFoundError(Exception):
    """Raised when an agent definition cannot be located."""

    pass


def load_agent(
    agent_name: str, root_dir: pathlib.Path, provider_name: str | None = None
) -> tuple[dict[str, str], str]:
    """Loads an agent definition, searching provider-specific then
    canonical directories."""

    searched = []
    # 1. Provider-specific: .vaultspec/agents/<provider>/<name>.md
    if provider_name:
        p_path = root_dir / ".vaultspec" / "agents" / provider_name / f"{agent_name}.md"
        searched.append(p_path)
        if p_path.exists():
            return parse_frontmatter(p_path.read_text(encoding="utf-8"))

    # 2. Canonical: .vaultspec/agents/<name>.md
    c_path = root_dir / ".vaultspec" / "agents" / f"{agent_name}.md"
    searched.append(c_path)
    if c_path.exists():
        return parse_frontmatter(c_path.read_text(encoding="utf-8"))

    raise AgentNotFoundError(f"Agent '{agent_name}' not found. Searched: {searched}")


def get_provider_for_model(model_name: str | None) -> AgentProvider:
    """Selects the appropriate provider for the requested model."""
    if not model_name:
        return GeminiProvider()

    if any(p in model_name for p in _CLAUDE_PATTERNS):
        return ClaudeProvider()

    if any(p in model_name for p in _GEMINI_PATTERNS):
        return GeminiProvider()

    # Fallback: default to Gemini
    return GeminiProvider()


def _build_task_prompt(
    goal: str,
    context_files: list[pathlib.Path],
    plan_file: pathlib.Path | None,
    root_dir: pathlib.Path,
) -> str:
    """Constructs a structured task prompt from goal and context files."""
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
    logger_instance: SessionLogger | None,
) -> None:
    """Run an interactive conversation loop with the agent."""
    _ = agent_name
    _ = logger_instance
    current_prompt = initial_prompt
    while True:
        if current_prompt:
            # ACP prompt expects list of content blocks
            prompt_blocks = [TextContentBlock(type="text", text=current_prompt)]
            res = await conn.prompt(prompt=prompt_blocks, session_id=session_id)
            if debug:
                logger.debug(f"Agent Response: {res}")

        if not interactive:
            break

        # Check if process is still alive
        if proc.returncode is not None:
            if debug:
                logger.debug(f"Process exited with {proc.returncode}")
            break

        try:
            # Using loop.run_in_executor for non-blocking input
            loop = asyncio.get_event_loop()
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
) -> SubagentResult:
    """Orchestrates the agent lifecycle with fallback support."""
    if max_turns is not None and max_turns <= 0:
        raise ValueError(f"max_turns must be positive, got {max_turns}")
    if budget is not None and budget < 0:
        raise ValueError(f"budget must be non-negative, got {budget}")

    if context_files is None:
        context_files = []

    current_model = model_override

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
            agent_name, root_dir, provider_name=provider.name
        )
    except AgentNotFoundError:
        # Fallback if provider-specific fails
        agent_meta, agent_persona = load_agent(agent_name, root_dir)

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
    session_id = resume_session_id or str(asyncio.get_event_loop().time())
    logger_instance = SessionLogger(session_id, root_dir)

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
                """Consumes stderr to prevent buffer filling and hangs."""
                if proc.stderr:
                    with contextlib.suppress(asyncio.CancelledError, Exception):
                        while True:
                            line = await proc.stderr.readline()
                            if not line:
                                break
                            if debug:
                                with contextlib.suppress(Exception):
                                    logger.debug(
                                        f"[AGENT-STDERR] {line.decode().strip()}"
                                    )

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
                init_res = await conn.initialize(
                    protocol_version=1,
                    client_capabilities=ClientCapabilities(
                        terminal=True,
                        fs=FileSystemCapability(
                            read_text_file=True,
                            write_text_file=True,
                        ),
                    ),
                    client_info=Implementation(
                        name="vs-subagent-mcp",
                        version="0.1.0",
                    ),
                )
                logger.debug(f"Handshake Result: {init_res}")

                # Session setup
                # Note: We pass MCP servers if supported by the provider/spec
                mcp_servers = getattr(spec, "mcp_servers", [])

                session = await conn.new_session(
                    cwd=str(root_dir),
                    mcp_servers=mcp_servers,
                )

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

                t.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await t

                return SubagentResult(
                    session_id=session.session_id,
                    response_text=client.response_text,
                    written_files=client.written_files,
                )

    except Exception:
        logger.exception("Subagent execution failed")
        return SubagentResult(
            session_id=session_id,
            response_text=client.response_text,
            written_files=client.written_files,
        )

    finally:
        # Cleanup
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
