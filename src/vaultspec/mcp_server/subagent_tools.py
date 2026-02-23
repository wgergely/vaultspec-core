"""MCP tool implementations for subagent dispatch, task management, and agent
discovery."""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import re
import time
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pathlib
    from collections.abc import AsyncIterator, Awaitable, Callable

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.resources.types import FunctionResource
from mcp.types import ToolAnnotations
from pydantic import AnyUrl

from ..orchestration import (
    READONLY_PERMISSION_PROMPT as _READONLY_PERMISSION_PROMPT,
)
from ..orchestration import (
    LockManager,
    TaskEngine,
    run_subagent,
    safe_read_text,
)
from ..protocol.acp import SubagentError
from ..vaultcore import parse_frontmatter

__all__ = [
    "cancel_task",
    "dispatch_agent",
    "get_locks",
    "get_task_status",
    "initialize_server",
    "list_agents",
    "register_tools",
    "subagent_lifespan",
]

# Configure logging
# configure_logging() - Removed to avoid side effects on import
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Globals -- must be initialized via initialize_server() before use.
# Thread-safe: single-event-loop assumption (one asyncio loop per process).
# ---------------------------------------------------------------------------
ROOT_DIR: pathlib.Path
CONTENT_ROOT: pathlib.Path
AGENTS_DIR: pathlib.Path
lock_manager: LockManager
task_engine: TaskEngine
_agent_cache: dict[str, dict[str, object]] = {}
_background_tasks: dict[str, asyncio.Task[None]] = {}
_active_clients: dict[str, list] = {}

# Injectable callbacks -- overridden via initialize_server() for testing.
_refresh_fn: Callable[[], bool]
_run_subagent_fn: Callable[..., Awaitable[Any]]

# Reference to the FastMCP instance used for resource management.
# Set by register_tools() or _create_standalone_server().
_mcp_ref: FastMCP | None = None


def initialize_server(
    root_dir: pathlib.Path,
    ttl_seconds: float | None = None,
    *,
    content_root: pathlib.Path | None = None,
    refresh_callback: Callable[[], bool] | None = None,
    run_subagent_fn: Callable[..., Awaitable[Any]] | None = None,
) -> None:
    """Initialize server configuration.  MUST be called before mcp.run().

    Args:
        root_dir: Workspace root directory (required).
        ttl_seconds: Task TTL in seconds (default 3600).
        content_root: Content source root.  When ``None``, falls back to
            ``root_dir / framework_dir``.
        refresh_callback: Override for ``_refresh_if_changed`` (testing).
        run_subagent_fn: Override for ``run_subagent`` (testing).
    """
    from ..config import get_config

    cfg = get_config()

    global ROOT_DIR, CONTENT_ROOT, AGENTS_DIR, lock_manager, task_engine
    global _refresh_fn, _run_subagent_fn

    ROOT_DIR = root_dir
    CONTENT_ROOT = (
        content_root if content_root is not None else (root_dir / cfg.framework_dir)
    )
    AGENTS_DIR = CONTENT_ROOT / "rules" / "agents"
    lock_manager = LockManager()
    task_engine = TaskEngine(ttl_seconds=ttl_seconds, lock_manager=lock_manager)
    _refresh_fn = refresh_callback or _refresh_if_changed
    _run_subagent_fn = run_subagent_fn or run_subagent

    logger.info(
        "MCP server initialized: root=%s, agents_dir=%s, ttl=%s",
        ROOT_DIR,
        AGENTS_DIR,
        ttl_seconds,
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _resolve_effective_mode(agent: str, mode: str | None) -> str:
    """Resolve the effective permission mode for a subagent invocation.

    Args:
        agent: Agent name used to look up the cached default mode.
        mode: Caller-supplied override; takes precedence if not ``None``.

    Returns:
        The resolved mode string — either the override, the agent's default,
        or ``"read-write"`` as the fallback.
    """
    if mode is not None:
        return mode
    agent_meta = _agent_cache.get(agent)
    if agent_meta and agent_meta.get("default_mode"):
        return str(agent_meta["default_mode"])
    return "read-write"


def _inject_permission_prompt(task_content: str, mode: str) -> str:
    """Prepend permission instructions to the task content if read-only.

    Args:
        task_content: The agent's task description or plan text.
        mode: Permission mode — ``"read-only"`` triggers injection.

    Returns:
        Task content prepended with the read-only permission prompt, or the
        original content unchanged for ``"read-write"`` mode.
    """
    if mode == "read-only":
        return _READONLY_PERMISSION_PROMPT + task_content
    return task_content


def _prepare_dispatch_kwargs(
    agent_name: str,
    task: str,
    root_dir: pathlib.Path,
    mode: str,
    model: str | None = None,
    max_turns: int | None = None,
    budget: float | None = None,
    effort: str | None = None,
    output_format: str | None = None,
    resume_session_id: str | None = None,
    content_root: pathlib.Path | None = None,
    client_ref: list | None = None,
) -> dict:
    """Build kwargs dict for ``run_subagent`` from dispatch parameters.

    Pure function -- no server globals needed.  Extracted for testability.

    Args:
        agent_name: Name of the agent to dispatch.
        task: Task description passed as ``initial_task``.
        root_dir: Workspace root directory.
        mode: Permission mode (``"read-write"`` or ``"read-only"``).
        model: Optional model override.
        max_turns: Maximum conversation turns; ``None`` uses agent default.
        budget: Cost budget in USD; ``None`` uses agent default.
        effort: Effort level (``"low"``, ``"medium"``, or ``"high"``).
        output_format: Response format (``"text"``, ``"json"``, etc.).
        resume_session_id: Session ID to resume; ``None`` starts fresh.
        content_root: Content source root; ``None`` uses server default.
        client_ref: Mutable list used to surface the ACP client handle.

    Returns:
        Keyword-argument dict ready for ``await run_subagent(**kwargs)``.
    """
    kwargs: dict[str, Any] = {
        "agent_name": agent_name,
        "initial_task": task,
        "root_dir": root_dir,
        "model_override": model,
        "interactive": False,
        "debug": False,
        "quiet": True,
        "mode": mode,
        "max_turns": max_turns,
        "budget": budget,
        "effort": effort,
        "output_format": output_format,
    }
    if resume_session_id is not None:
        kwargs["resume_session_id"] = resume_session_id
    if content_root is not None:
        kwargs["content_root"] = content_root
    if client_ref is not None:
        kwargs["client_ref"] = client_ref
    return kwargs


_ARTIFACT_PATTERN = re.compile(
    r"""(?:^|[\s"'`(])"""  # word boundary or quote/backtick
    r"""("""
    r"""\.vault/[\w./-]+"""  # .vault/ paths
    r"""|\.vaultspec/[\w./-]+"""  # .vaultspec/ paths
    r"""|src/[\w./-]+"""  # src/ paths
    r"""|crates/[\w./-]+"""  # crates/ paths
    r"""|tests?/[\w./-]+"""  # test(s)/ paths
    r"""|[\w./-]+\.(?:md|rs|toml|py)"""  # files with known extensions
    r""")"""
    r"""(?=[\s"'`),;:]|$)""",  # word boundary or quote/backtick
    re.MULTILINE,
)


def _extract_artifacts(text: str) -> list[str]:
    """Extract unique file path references from agent response text.

    Args:
        text: Agent response string to scan for path references.

    Returns:
        Sorted list of unique, forward-slash-normalised path strings found
        in the text, or an empty list if ``text`` is blank.
    """
    if not text:
        return []
    matches = _ARTIFACT_PATTERN.findall(text)
    seen: set[str] = set()
    unique: list[str] = []
    for m in matches:
        normalized = m.replace("\\", "/")
        if normalized not in seen:
            seen.add(normalized)
            unique.append(normalized)
    return sorted(unique)


def _merge_artifacts(text_artifacts: list[str], written_files: list[str]) -> list[str]:
    """Merge regex-extracted artifacts with the file write log.

    Args:
        text_artifacts: Paths extracted from agent response text.
        written_files: Paths recorded by the file-write hook.

    Returns:
        Sorted, deduplicated list of all artifact paths with forward-slash
        normalisation applied.
    """
    seen: set[str] = set()
    merged: list[str] = []
    for path in (*written_files, *text_artifacts):
        normalized = path.replace("\\", "/")
        if normalized not in seen:
            seen.add(normalized)
            merged.append(normalized)
    return sorted(merged)


# ---------------------------------------------------------------------------
# Agent file polling and resource management
# ---------------------------------------------------------------------------

_agent_mtimes: dict[str, float] = {}


def _poll_interval() -> float:
    """Return the configured agent-file polling interval in seconds.

    Returns:
        The ``mcp_poll_interval`` value from the active configuration.
    """
    from ..config import get_config

    return get_config().mcp_poll_interval


def _strip_quotes(value: str) -> str:
    """Remove surrounding double-quotes from a YAML scalar string if present.

    Args:
        value: Raw YAML scalar that may be wrapped in double-quotes.

    Returns:
        The value with one layer of surrounding double-quotes removed, or
        the original string if it is not double-quoted.
    """
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _parse_tools(raw: str) -> list[str]:
    """Split a comma-separated tool/allow-list string into a cleaned list.

    Args:
        raw: Comma-separated string of tool names (e.g. ``"Read,Write,Bash"``).

    Returns:
        List of stripped, non-empty tool name strings.
    """
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_agent_metadata(agent_path: pathlib.Path) -> dict[str, object]:
    """Parse an agent Markdown file and return its metadata as a dict.

    Reads YAML frontmatter from the agent file and extracts standard fields
    (name, description, tier, model, mode, tools) plus any extended
    configuration keys (max_turns, budget, effort, output_format, etc.).

    Args:
        agent_path: Path to the agent ``.md`` file.

    Returns:
        Dictionary of agent metadata suitable for caching and resource registration.
    """
    content = agent_path.read_text(encoding="utf-8")
    meta, _body = parse_frontmatter(content)
    result: dict[str, object] = {
        "name": agent_path.stem,
        "description": _strip_quotes(meta.get("description", "")),
        "tier": meta.get("tier", "UNKNOWN"),
        "default_model": meta.get("model") or None,
        "default_mode": meta.get("mode") or None,
        "tools": _parse_tools(meta["tools"]) if "tools" in meta else [],
    }

    # Extended agent configuration (all optional)
    if "max_turns" in meta:
        result["max_turns"] = int(meta["max_turns"])
    if "budget" in meta:
        result["budget"] = float(meta["budget"])
    if "allowed_tools" in meta:
        result["allowed_tools"] = _parse_tools(meta["allowed_tools"])
    if "disallowed_tools" in meta:
        result["disallowed_tools"] = _parse_tools(meta["disallowed_tools"])
    if meta.get("effort"):
        result["effort"] = meta["effort"]
    if meta.get("output_format"):
        result["output_format"] = meta["output_format"]
    if meta.get("fallback_model"):
        result["fallback_model"] = meta["fallback_model"]
    if meta.get("approval_mode"):
        result["approval_mode"] = meta["approval_mode"]
    if "include_dirs" in meta:
        result["include_dirs"] = _parse_tools(meta["include_dirs"])

    return result


def _snapshot_mtimes() -> dict[str, float]:
    """Snapshot the nanosecond mtimes of all agent files in AGENTS_DIR.

    Returns:
        Mapping of agent stem to ``st_mtime_ns`` for each ``.md`` file found.
    """
    mtimes: dict[str, float] = {}
    if not AGENTS_DIR.is_dir():
        return mtimes
    for agent_path in AGENTS_DIR.glob("*.md"):
        with contextlib.suppress(OSError):
            mtimes[agent_path.stem] = agent_path.stat().st_mtime_ns
    return mtimes


def _has_changes() -> bool:
    """Return True if any agent file changed since last snapshot.

    Returns:
        ``True`` if the agent file set differs from the snapshot,
        ``False`` if nothing has changed.
    """
    current = _snapshot_mtimes()
    if set(current) != set(_agent_mtimes):
        return True
    return any(current[k] != _agent_mtimes[k] for k in current)


def _build_agent_cache() -> dict[str, dict[str, object]]:
    """Scan AGENTS_DIR and return a fresh cache of all parsed agent metadata.

    Returns:
        Mapping of agent name to its parsed metadata dict.
    """
    cache: dict[str, dict[str, object]] = {}
    if not AGENTS_DIR.is_dir():
        logger.warning("Agents directory not found: %s", AGENTS_DIR)
        return cache
    for agent_path in sorted(AGENTS_DIR.glob("*.md")):
        try:
            metadata = _parse_agent_metadata(agent_path)
            cache[str(metadata["name"])] = metadata
        except Exception as exc:
            logger.warning("Failed to parse agent %s: %s", agent_path.name, exc)
    return cache


def _register_agent_resources() -> None:
    """Rebuild the agent cache and register dynamic agent resources.

    Requires ``_mcp_ref`` to be set (via ``register_tools()``).

    Returns:
        None. Side effect: updates ``_agent_cache``, ``_agent_mtimes``,
        and the ``FastMCP`` resource manager with fresh ``agents://`` URIs.
    """
    global _agent_cache, _agent_mtimes
    _agent_cache = _build_agent_cache()
    _agent_mtimes = _snapshot_mtimes()

    if _mcp_ref is None:
        logger.warning("No FastMCP instance set; skipping resource registration")
        return

    # NOTE: FastMCP ResourceManager has no public remove_resource() API.
    # We access _resource_manager._resources (dict[str, Resource]) directly
    # to clear stale agent entries before re-registering.  Pinned to
    # mcp>=1.20.0 in pyproject.toml; revisit if ResourceManager gains a
    # public removal method.
    resources = _mcp_ref._resource_manager._resources
    stale_keys = [k for k in resources if k.startswith("agents://")]
    for k in stale_keys:
        del resources[k]

    for name, metadata in _agent_cache.items():

        def _make_reader(meta: dict[str, object]):
            """Return a zero-argument callable that serialises *meta* to JSON.

            Args:
                meta: Agent metadata dict to capture in the closure.

            Returns:
                A ``lambda`` that produces a pretty-printed JSON string.
            """
            return lambda: json.dumps(meta, indent=2)

        resource = FunctionResource(
            uri=AnyUrl(f"agents://{name}"),
            name=name,
            description=str(metadata.get("description", "")),
            mime_type="application/json",
            fn=_make_reader(metadata),
        )
        _mcp_ref._resource_manager.add_resource(resource)

    logger.info("Registered %d agent resources", len(_agent_cache))


def _refresh_if_changed() -> bool:
    """Refresh the agent cache and resources if any agent files have changed.

    Returns:
        True if a refresh was performed, False if nothing changed.
    """
    if not _has_changes():
        return False
    logger.info("Agent files changed, refreshing resource cache")
    _register_agent_resources()
    return True


async def _send_list_changed() -> None:
    """Send ``resources/list_changed`` to the active session."""
    if _mcp_ref is None:
        return
    try:
        ctx = _mcp_ref._mcp_server.request_context
        await ctx.session.send_resource_list_changed()
        logger.info("Sent resources/list_changed notification")
    except (LookupError, AttributeError):
        logger.debug("No active session, skipping list_changed notification")


async def _poll_agent_files() -> None:
    """Continuously poll for agent file changes and emit list_changed notifications."""
    while True:
        await asyncio.sleep(_poll_interval())
        try:
            if _refresh_fn():
                await _send_list_changed()
        except Exception:
            logger.exception("Error in agent file poll loop")


# ---------------------------------------------------------------------------
# Tool functions (undecorated -- registered by register_tools())
# ---------------------------------------------------------------------------


async def list_agents() -> str:
    """Return a list of all available sub-agents and their tiers.

    Returns:
        JSON string with an ``agents`` array (name, tier, description per entry)
        and a ``hint`` for reading full metadata via ``agents://`` resources.
    """
    logger.info("MCP: list_agents called")
    _refresh_fn()
    agents = []
    for name, metadata in _agent_cache.items():
        agents.append(
            {
                "name": name,
                "tier": metadata.get("tier", "UNKNOWN"),
                "description": metadata.get("description", ""),
            }
        )

    return json.dumps(
        {
            "agents": agents,
            "hint": "Use resources/read with agents://{name} for metadata",
        },
        indent=2,
    )


async def dispatch_agent(
    agent: str,
    task: str,
    model: str | None = None,
    mode: str | None = None,
    max_turns: int | None = None,
    budget: float | None = None,
    effort: str | None = None,
    output_format: str | None = None,
    resume_session_id: str | None = None,
) -> str:
    """Run a sub-agent asynchronously and return a task ID.

    Optional overrides (``max_turns``, ``budget``, ``effort``,
    ``output_format``) take precedence over the agent's defaults.

    Args:
        agent: Name of the agent to dispatch (must appear in the agent cache).
        task: Task description or path to a ``.md`` plan file.
        model: Optional model override for the agent invocation.
        mode: Permission mode — ``"read-write"`` or ``"read-only"``.
        max_turns: Maximum number of turns; overrides the agent default.
        budget: Maximum cost budget in USD; overrides the agent default.
        effort: Effort level — ``"low"``, ``"medium"``, or ``"high"``.
        output_format: Output format — ``"text"``, ``"json"``, or ``"stream-json"``.
        resume_session_id: Session ID to resume a previous agent session.

    Returns:
        JSON string with ``status``, ``agent``, ``taskId``, ``model``, and ``mode``.

    Raises:
        ToolError: If the agent is not found, parameters are invalid, or the task is too
            large.
    """
    _refresh_fn()

    if agent not in _agent_cache:
        raise ToolError(f"Agent '{agent}' not found.")

    if max_turns is not None and max_turns <= 0:
        raise ToolError(f"max_turns must be positive, got {max_turns}")
    if budget is not None and budget < 0:
        raise ToolError(f"budget must be non-negative, got {budget}")

    effective_mode = _resolve_effective_mode(agent, mode)
    logger.info(
        "MCP: dispatch_agent agent=%s mode=%s model=%s", agent, effective_mode, model
    )

    if effective_mode not in ("read-write", "read-only"):
        raise ToolError(
            f"Invalid mode '{effective_mode}'. Use 'read-write' or 'read-only'."
        )

    # Validate effort
    if effort is not None and effort not in {"low", "medium", "high"}:
        raise ToolError(f"Invalid effort '{effort}'. Use 'low', 'medium', or 'high'.")

    # Validate output_format
    if output_format is not None and output_format not in {
        "text",
        "json",
        "stream-json",
    }:
        raise ToolError(
            f"Invalid output_format '{output_format}'."
            " Use 'text', 'json', or 'stream-json'."
        )

    max_task_len = 100_000  # 100KB
    if len(task) > max_task_len:
        raise ToolError(f"Task too large ({len(task)} chars). Max is {max_task_len}.")

    # Pre-acquire advisory lock for .vault/ if read-only
    try:
        task_obj = task_engine.create_task(agent, model=model, mode=effective_mode)
    except ValueError as e:
        raise ToolError(str(e)) from e

    task_id = task_obj.task_id

    # Background execution
    async def _run_in_background():
        """Execute the subagent task and update the task engine with the result."""
        client_ref = []
        _active_clients[task_id] = client_ref

        try:
            # Task resolution
            task_content = task
            if task.endswith(".md") or "/" in task or "\\" in task:
                try:
                    p = ROOT_DIR / task
                    if p.exists() and p.is_file():
                        task_content = safe_read_text(p, ROOT_DIR)
                except Exception as exc:
                    logger.warning(
                        "Failed to resolve task file %s: %s",
                        task,
                        exc,
                        exc_info=True,
                    )
                    pass

            full_task = _inject_permission_prompt(task_content, effective_mode)

            result = await _run_subagent_fn(
                agent_name=agent,
                initial_task=full_task,
                root_dir=ROOT_DIR,
                model_override=model,
                interactive=False,
                debug=False,
                quiet=True,
                mode=effective_mode,
                client_ref=client_ref,
                resume_session_id=resume_session_id,
                max_turns=max_turns,
                budget=budget,
                effort=effort,
                output_format=output_format,
                content_root=CONTENT_ROOT,
            )

            # Record session ID for potential resume
            if result.session_id:
                task_engine.set_session_id(task_id, result.session_id)

            # Artifacts
            text_artifacts = _extract_artifacts(result.response_text)
            final_artifacts = _merge_artifacts(text_artifacts, result.written_files)

            # Final summary (truncated)
            summary = result.response_text[:500]
            if len(result.response_text) > 500:
                summary += "..."

            task_engine.complete_task(
                task_id,
                {
                    "taskId": task_id,
                    "status": "completed",
                    "agent": agent,
                    "model_used": model or "(default)",
                    "duration_seconds": time.monotonic() - task_obj.created_at,
                    "summary": summary,
                    "response": result.response_text,
                    "artifacts": final_artifacts,
                },
            )
        except asyncio.CancelledError:
            task_engine.cancel_task(task_id)
            raise
        except SubagentError as e:
            logger.error("Subagent failed task_id=%s agent=%s: %s", task_id, agent, e)
            task_engine.fail_task(task_id, str(e))
        except Exception as e:
            logger.exception("Unexpected error in background subagent")
            task_engine.fail_task(task_id, f"Unexpected error: {e}")
        finally:
            _background_tasks.pop(task_id, None)
            _active_clients.pop(task_id, None)

    bg_task = asyncio.create_task(_run_in_background())
    _background_tasks[task_id] = bg_task

    return json.dumps(
        {
            "status": "working",
            "agent": agent,
            "taskId": task_id,
            "model": model,
            "mode": effective_mode,
        },
        indent=2,
    )


async def get_task_status(task_id: str) -> str:
    """Check the status and result of a previously dispatched task.

    Args:
        task_id: The task ID returned by ``dispatch_agent``.

    Returns:
        JSON string with ``taskId``, ``status``, ``agent``, ``model``, ``mode``,
        and — when complete — ``result``, ``error``, ``session_id``, and ``lock``.

    Raises:
        ToolError: If the task ID is not found or has expired.
    """
    logger.info("MCP: get_task_status task_id=%s", task_id)
    task = task_engine.get_task(task_id)
    if not task:
        raise ToolError(f"Task '{task_id}' not found or expired.")

    res = {
        "taskId": task.task_id,
        "status": task.status.value,
        "agent": task.agent,
        "model": task.model,
        "mode": task.mode,
    }

    if task.result:
        res["result"] = task.result
    if task.error:
        # Truncate error to avoid leaking sensitive paths
        error_msg = task.error[:500] if len(task.error) > 500 else task.error
        res["error"] = error_msg

    if task.session_id:
        res["session_id"] = task.session_id

    # Add active lock info if working
    lock = lock_manager.get_lock(task_id)
    if lock:
        res["lock"] = {
            "paths": list(lock.paths),
            "mode": lock.mode,
            "acquired_at": lock.acquired_at,
        }

    return json.dumps(res, indent=2)


async def cancel_task(task_id: str) -> str:
    """Cancel a running task and its agent session.

    Args:
        task_id: The task ID returned by ``dispatch_agent``.

    Returns:
        JSON string with ``status``, ``taskId``, and ``agent``.

    Raises:
        ToolError: If the task is not found or has already completed.
    """
    logger.info("MCP: cancel_task task_id=%s", task_id)
    task = task_engine.get_task(task_id)
    if not task:
        raise ToolError(f"Task '{task_id}' not found.")

    if task.completed_at:
        raise ToolError("Task already completed.")

    # 1. Graceful ACP cancel if client is active
    client_ref = _active_clients.get(task_id)
    if client_ref:
        client = client_ref[0]
        await client.graceful_cancel()

    # 2. Stop the background coroutine
    bg_task = _background_tasks.get(task_id)
    if bg_task:
        bg_task.cancel()

    # 3. Update engine state
    task_engine.cancel_task(task_id)

    return json.dumps({"status": "cancelled", "taskId": task_id, "agent": task.agent})


async def get_locks() -> str:
    """List all active advisory file locks across the workspace.

    Returns:
        JSON string with a ``locks`` array (taskId, agent, paths, mode,
        acquired_at per entry) and a ``count`` field.
    """
    logger.info("MCP: get_locks called")
    locks = lock_manager.get_locks()
    res = []
    for lock in locks:
        task = task_engine.get_task(lock.task_id)
        res.append(
            {
                "taskId": lock.task_id,
                "agent": task.agent if task else "unknown",
                "paths": list(lock.paths),
                "mode": lock.mode,
                "acquired_at": lock.acquired_at,
            }
        )
    return json.dumps({"locks": res, "count": len(res)}, indent=2)


# ---------------------------------------------------------------------------
# Registration API -- used by the unified server (vaultspec.mcp_server.app)
# ---------------------------------------------------------------------------


@asynccontextmanager
async def subagent_lifespan() -> AsyncIterator[None]:
    """Lifespan context: starts agent-file polling, cleans up on exit."""
    _register_agent_resources()
    poller = asyncio.create_task(_poll_agent_files())
    _background_tasks["agent_poller"] = poller
    try:
        yield None
    finally:
        poller.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await poller
        _background_tasks.pop("agent_poller", None)


def register_tools(mcp: FastMCP) -> None:
    """Register all subagent MCP tools and resources on the given instance.

    This is the primary integration point for the unified ``vaultspec-mcp``
    server.  Call this once after creating the ``FastMCP`` instance.

    Args:
        mcp: The ``FastMCP`` application instance to register tools on.
    """
    global _mcp_ref
    _mcp_ref = mcp

    # -- Tools ---------------------------------------------------------------

    mcp.tool(
        title="List Available Agents",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )(list_agents)

    mcp.tool(
        title="Dispatch Sub-Agent",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=False,
            idempotentHint=False,
            openWorldHint=False,
        ),
    )(dispatch_agent)

    mcp.tool(
        title="Get Task Status",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )(get_task_status)

    mcp.tool(
        title="Cancel Task",
        annotations=ToolAnnotations(
            readOnlyHint=False,
            destructiveHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )(cancel_task)

    mcp.tool(
        title="Get Active Locks",
        annotations=ToolAnnotations(
            readOnlyHint=True,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )(get_locks)
