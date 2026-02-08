from __future__ import annotations

import asyncio
import contextlib
import gc
import logging
import os
import pathlib
import sys
from typing import Dict, List, Optional, Tuple, Type

from acp import spawn_agent_process
from acp.client.connection import ClientSideConnection
from acp.schema import (
    ClientCapabilities,
    FileSystemCapability,
    Implementation,
    TextContentBlock,
)

from protocol.acp.client import DispatchClient, SessionLogger
from protocol.acp.types import DispatchError, DispatchResult
from protocol.providers.base import AgentProvider
from protocol.providers.claude import ClaudeProvider
from protocol.providers.gemini import GeminiProvider
from orchestration.utils import parse_frontmatter, safe_read_text

logger = logging.getLogger(__name__)

# Feature gate: ACP session resume
_SESSION_RESUME_ENABLED = os.environ.get("PP_DISPATCH_SESSION_RESUME", "").lower() in (
    "1",
    "true",
    "yes",
)


class AgentNotFoundError(Exception):
    """Raised when an agent definition cannot be found."""

    pass


def load_agent(
    agent_name: str,
    root_dir: pathlib.Path,
    provider_name: str | None = None,
    extra_search_paths: List[pathlib.Path] | None = None,
) -> Tuple[Dict[str, str], str]:
    """Loads an agent definition, searching provider-specific then canonical directories."""

    agent_dirs = {
        "gemini": root_dir / ".gemini" / "agents",
        "claude": root_dir / ".claude" / "agents",
        "antigravity": root_dir / ".agent" / "agents",
        "rules": root_dir / ".rules" / "agents",  # canonical fallback
    }

    search_order: list[pathlib.Path] = []
    if extra_search_paths:
        search_order.extend(extra_search_paths)

    if provider_name and provider_name in agent_dirs:
        search_order.append(agent_dirs[provider_name])
    search_order.append(agent_dirs["rules"])

    for agent_dir in search_order:
        agent_path = agent_dir / f"{agent_name}.md"
        if agent_path.exists():
            content = safe_read_text(agent_path, root_dir)
            meta, persona = parse_frontmatter(content)
            return meta, persona

    searched = ", ".join(str(d) for d in search_order)
    raise AgentNotFoundError(f"Agent '{agent_name}' not found. Searched: {searched}")


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


def _build_task_prompt(
    goal: str,
    context_files: List[pathlib.Path],
    plan_file: Optional[pathlib.Path],
    root_dir: pathlib.Path,
) -> str:
    """Constructs a structured task prompt from goal and context files."""
    parts = [
        "# TASK CONTEXT",
        "The following documents define the constraints and design for this task.",
        "You MUST adhere to the decisions recorded here.",
        "",
    ]

    if context_files:
        for path in context_files:
            try:
                content = safe_read_text(path, root_dir)
                rel_path = (
                    path.relative_to(root_dir)
                    if path.is_relative_to(root_dir)
                    else path.name
                )
                parts.append(f"## CONTEXT: {rel_path}")
                parts.append(content)
                parts.append("")
            except Exception as e:
                logger.warning(f"Failed to read context file {path}: {e}")
                parts.append(f"## CONTEXT: {path} (Error reading file)")

    if plan_file:
        try:
            content = safe_read_text(plan_file, root_dir)
            rel_path = (
                plan_file.relative_to(root_dir)
                if plan_file.is_relative_to(root_dir)
                else plan_file.name
            )
            parts.append(f"## PLAN: {rel_path}")
            parts.append(content)
            parts.append("")
        except Exception as e:
            logger.warning(f"Failed to read plan file {plan_file}: {e}")
            parts.append(f"## PLAN: {plan_file} (Error reading file)")

    parts.append("# OBJECTIVE")
    parts.append(goal)

    return "\n".join(parts)


async def _interactive_loop(
    conn: ClientSideConnection,
    session_id: str,
    agent_name: str,
    initial_prompt: str | None,
    debug: bool,
    interactive: bool,
    proc: asyncio.subprocess.Process,
    logger_instance: Optional[SessionLogger],
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
                logger.debug(f"Prompt failed: {e}")
            # Try to cancel
            with contextlib.suppress(Exception):
                await conn.cancel(session_id=session_id)
            raise

        if logger_instance:
            logger_instance.log("prompt_response", response.model_dump(mode="json"))

        if debug:
            logger.debug(f"stop_reason: {response.stop_reason}")

        # In one-shot mode, we always exit after one turn regardless of stop_reason
        if not interactive:
            if debug:
                logger.debug(
                    f"Turn finished ({response.stop_reason}). Exiting one-shot task."
                )
            break

        # Check if process is still alive
        if proc.returncode is not None:
            if debug:
                logger.debug(
                    f"Agent process exited with code {proc.returncode}. Exiting loop."
                )
            break

        # If we got here, we decide whether to prompt for more input
        if not sys.stdin.isatty():
            if debug:
                logger.debug("Not a TTY, breaking loop.")
            break

        print(
            "\nType your response (or press Enter to exit): ", end="", file=sys.stderr
        )

        # Wait for either user input or process exit
        input_task = asyncio.create_task(_get_user_input())
        proc_task = asyncio.create_task(proc.wait())

        done, pending = await asyncio.wait(
            [input_task, proc_task], return_when=asyncio.FIRST_COMPLETED
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
                logger.debug("Agent process terminated while waiting for input.")
            break


async def run_dispatch(
    agent_name: str,
    root_dir: pathlib.Path,
    initial_task: str = "",
    context_files: List[pathlib.Path] = [],
    plan_file: Optional[pathlib.Path] = None,
    model_override: str | None = None,
    provider_override: str | None = None,
    interactive: bool = False,
    debug: bool = False,
    quiet: bool = False,
    mode: str = "read-write",
    client_ref: Optional[list] = None,
    resume_session_id: str | None = None,
    client_class: Type[DispatchClient] = DispatchClient,
    agent_search_paths: List[pathlib.Path] | None = None,
) -> DispatchResult:
    """Orchestrates the agent lifecycle with fallback support."""

    current_model = model_override

    # Resolve the initial provider hint
    initial_provider_hint = provider_override
    if not initial_provider_hint and model_override:
        if model_override.startswith("claude"):
            initial_provider_hint = "claude"
        elif model_override.startswith("gemini"):
            initial_provider_hint = "gemini"

    # 1. Load Agent Definition
    if debug:
        logger.debug(f"Loading sub-agent: {agent_name}...")
    meta, persona = load_agent(
        agent_name,
        root_dir,
        provider_name=initial_provider_hint,
        extra_search_paths=agent_search_paths,
    )

    # Determine initial model
    if not current_model:
        current_model = meta.get("model", "gemini-2.5-flash")  # Default

    gemini = GeminiProvider()  # Default/Primary provider

    # Build Structured Prompt
    full_prompt = _build_task_prompt(initial_task, context_files, plan_file, root_dir)

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
            is_mismatch = (
                provider.name == "claude" and current_model.startswith("gemini")
            ) or (provider.name == "gemini" and current_model.startswith("claude"))

            if is_mismatch:
                if debug:
                    logger.debug(
                        f"Provider mismatch detected (Provider: {provider.name}, Model: {current_model}). resolving equivalent..."
                    )
                source_provider = get_provider_for_model(current_model)
                try:
                    level = source_provider.get_model_capability(current_model)
                except Exception:
                    level = 2  # Default Medium

                current_model = provider.get_best_model_for_capability(level)
                if debug:
                    logger.debug(f"Resolved equivalent model: {current_model}")

        else:
            try:
                provider = get_provider_for_model(current_model)
            except ValueError:
                provider = gemini

        if debug:
            logger.debug(f"Using provider: {provider.name} with model: {current_model}")

        try:
            # 3. Prepare Process
            spec = provider.prepare_process(
                agent_name,
                meta,
                persona,
                full_prompt,
                root_dir,
                model_override=current_model,
            )
            cleanup_paths = spec.cleanup_paths

            if debug:
                logger.debug(
                    f"Spawning agent process: {spec.executable} {' '.join(spec.args)}"
                )

            client = client_class(
                root_dir=root_dir, debug=debug, quiet=quiet, mode=mode
            )
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
                                    logger.debug(
                                        f"[AGENT-STDERR] {line.decode().strip()}"
                                    )
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
                    "limit": 100 * 1024 * 1024,  # 100MB limit for large outputs
                    "shutdown_timeout": 5.0,  # 5s grace period for clean exit
                },
            ) as (conn, _proc):
                stderr_task = asyncio.create_task(_read_stderr(_proc, debug))

                try:
                    if debug:
                        logger.debug("Connected to agent.")

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
                            version="0.6.0",
                        ),
                    )

                    if init_response and hasattr(init_response, "agent_capabilities"):
                        client.agent_capabilities = init_response.agent_capabilities

                    # Session creation
                    if _SESSION_RESUME_ENABLED and resume_session_id:
                        try:
                            session = await conn.load_session(
                                session_id=resume_session_id
                            )
                            if debug:
                                logger.debug(f"Resumed session: {session.session_id}")
                        except Exception as exc:
                            if debug:
                                logger.debug(
                                    f"Session resume failed ({exc}), creating new session"
                                )
                            session = await conn.new_session(
                                cwd=str(root_dir),
                                mcp_servers=getattr(spec, "mcp_servers", []),
                                **getattr(spec, "session_meta", {}),
                            )
                    else:
                        session = await conn.new_session(
                            cwd=str(root_dir),
                            mcp_servers=getattr(spec, "mcp_servers", []),
                            **getattr(spec, "session_meta", {}),
                        )

                    client._conn = conn
                    client._session_id = session.session_id
                    if debug:
                        logger.debug(f"Session started: {session.session_id}")

                    session_logger = SessionLogger(session.session_id, root_dir)
                    client.set_logger(session_logger)
                    if debug:
                        logger.debug(f"Logging to: {session_logger.log_file}")

                    # Interactive Loop
                    # We pass the full_prompt as the initial task prompt.
                    # If there's an override from the provider (e.g. for System Prompt injection), we prefer that,
                    # but typically provider override includes the task.
                    # Here we rely on provider.prepare_process to have incorporated full_prompt into initial_prompt_override if needed.
                    start_prompt = (
                        getattr(spec, "initial_prompt_override", None) or full_prompt
                    )

                    await _interactive_loop(
                        conn,
                        session.session_id,
                        agent_name,
                        start_prompt,
                        debug,
                        interactive,
                        _proc,
                        session_logger,
                    )

                    if debug:
                        logger.debug("Interaction loop finished. Shutting down...")

                finally:
                    stderr_task.cancel()
                    with contextlib.suppress(asyncio.CancelledError):
                        await stderr_task

                    if hasattr(_proc, "_transport") and _proc._transport:
                        with contextlib.suppress(Exception):
                            _proc._transport.close()

                    for stream_name in ["stdin", "stdout", "stderr"]:
                        stream = getattr(_proc, stream_name, None)
                        if stream and hasattr(stream, "transport"):
                            with contextlib.suppress(Exception):
                                stream.transport.close()

                    await asyncio.sleep(0.1)
                    gc.collect()

            # Final Reap
            try:
                await asyncio.wait_for(_proc.wait(), timeout=5.0)
            except (asyncio.TimeoutError, Exception):
                with contextlib.suppress(Exception):
                    _proc.kill()
                    await _proc.wait()

            gc.collect()
            await asyncio.sleep(0.5)

            if debug:
                logger.debug("Task completed.")

            return DispatchResult(
                response_text=client.response_text,
                written_files=list(client.written_files),
                session_id=client._session_id,
            )
        except Exception as e:
            logger.warning(f"Agent execution failed with {provider.name}: {e}")

            if provider_override:
                raise DispatchError(
                    f"Execution failed with provider {provider_override}: {e}"
                ) from e

            if provider.name == "gemini":
                logger.info("Attempting fallback to Claude...")
                try:
                    level = provider.get_model_capability(current_model)
                except Exception:
                    level = 2

                fallback_provider = ClaudeProvider()
                current_model = fallback_provider.get_best_model_for_capability(level)
                logger.info(f"Fallback selected: {current_model}")
                continue

            else:
                raise DispatchError(
                    f"Execution failed, no fallback available: {e}"
                ) from e
        finally:
            if "cleanup_paths" in locals():
                for path in cleanup_paths:
                    if path.exists():
                        try:
                            path.unlink()
                        except OSError:
                            pass
