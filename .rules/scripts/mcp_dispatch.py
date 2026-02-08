"""MCP Dispatch Server.

A typed MCP server that wraps the existing ACP dispatch client as MCP tools.
Exposes `dispatch_agent`, `list_agents`, `get_task_status`, and `cancel_task`
as MCP tools over stdio transport.  Agent definitions are also exposed as MCP
resources for richer metadata discovery.

Phase 4: Advisory locking and permission enforcement.
"""

from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import re
import sys
import time

# Ensure sibling modules are importable (agent_providers, acp_dispatch)
_SCRIPTS_DIR = pathlib.Path(__file__).resolve().parent
if str(_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_DIR))

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.resources.types import FunctionResource

from acp_dispatch import (
    AgentNotFoundError,
    DispatchError,
    DispatchResult,
    parse_frontmatter,
    run_dispatch,
    safe_read_text,
)
from task_engine import (
    InvalidTransitionError,
    LockManager,
    TaskEngine,
    TaskNotFoundError,
    TaskStatus,
)

# Configure logging to stderr (stdout is reserved for MCP JSON-RPC messages)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    stream=sys.stderr,
)
logger = logging.getLogger("pp-dispatch")

# ---------------------------------------------------------------------------
# Server initialization
# ---------------------------------------------------------------------------

mcp = FastMCP(
    name="pp-dispatch",
    instructions="MCP server for dispatching sub-agents via ACP. "
    "Use `list_agents` to discover available agents, "
    "`dispatch_agent` to run a sub-agent with a task, "
    "`get_task_status` to check on a running task, "
    "`cancel_task` to cancel a running task, "
    "and `get_locks` to view active advisory file locks.",
)

# Advisory lock manager for workspace coordination (Phase 4).
lock_manager = LockManager()

# Internal task engine (Layer 2) for tracking dispatch task lifecycle.
# Receives lock_manager for automatic lock release on terminal transitions.
task_engine = TaskEngine(ttl_seconds=3600.0, lock_manager=lock_manager)

# Maps task_id -> asyncio.Task for background dispatch coroutines.
# Used by cancel_task to terminate in-flight sub-agent processes.
_background_tasks: dict[str, asyncio.Task[None]] = {}

# Maps task_id -> GeminiDispatchClient for graceful ACP cancellation.
# Populated by _run_dispatch_background via client_ref.
_active_clients: dict[str, list] = {}


# ---------------------------------------------------------------------------
# Permission enforcement helpers
# ---------------------------------------------------------------------------

# Permission prompt injected for read-only mode.
_READONLY_PERMISSION_PROMPT = (
    "PERMISSION MODE: READ-ONLY\n"
    "You MUST only write files within the `.docs/` directory. "
    "Do not modify any source code files.\n\n"
)


def _resolve_effective_mode(agent: str, mode: str | None) -> str:
    """Resolve the effective permission mode for a dispatch.

    Priority: per-dispatch override > agent frontmatter default_mode > "read-write".
    """
    # Caller explicitly specified a mode -- use it directly.
    if mode is not None:
        return mode
    # No explicit mode: check agent cache for frontmatter default_mode.
    agent_meta = _agent_cache.get(agent)
    if agent_meta and agent_meta.get("default_mode"):
        return str(agent_meta["default_mode"])
    return "read-write"


def _inject_permission_prompt(task_content: str, mode: str) -> str:
    """Prepend permission instructions to the task content if read-only."""
    if mode == "read-only":
        return _READONLY_PERMISSION_PROMPT + task_content
    return task_content


# ---------------------------------------------------------------------------
# Artifact extraction
# ---------------------------------------------------------------------------

# Matches workspace-relative file paths in agent response text.
# Captures paths starting with known prefixes or ending with known extensions.
_ARTIFACT_PATTERN = re.compile(
    r"""(?:^|[\s"'`(])"""               # word boundary or quote/backtick
    r"""("""
    r"""\.docs/[\w./-]+"""              # .docs/ paths
    r"""|\.rules/[\w./-]+"""            # .rules/ paths
    r"""|src/[\w./-]+"""                # src/ paths
    r"""|crates/[\w./-]+"""             # crates/ paths
    r"""|tests?/[\w./-]+"""             # test(s)/ paths
    r"""|[\w./-]+\.(?:md|rs|toml|py)""" # files with known extensions
    r""")"""
    r"""(?=[\s"'`),;:]|$)""",           # word boundary or quote/backtick
    re.MULTILINE,
)


def _extract_artifacts(text: str) -> list[str]:
    """Extract unique file path references from agent response text.

    Scans for workspace-relative paths (e.g. `.docs/plan.md`, `src/main.rs`)
    and returns a deduplicated, sorted list.
    """
    if not text:
        return []
    matches = _ARTIFACT_PATTERN.findall(text)
    # Deduplicate while preserving discovery order, then sort.
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

    Normalizes paths to forward slashes and returns a deduplicated, sorted list.
    Written files are the authoritative source (actual I/O); text artifacts
    supplement with paths the agent mentioned but did not write through our client.
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
# Workspace helpers
# ---------------------------------------------------------------------------

def _find_project_root() -> pathlib.Path:
    """Walk up from CWD to find the git repository root."""
    candidate = pathlib.Path.cwd().resolve()
    while candidate != candidate.parent:
        if (candidate / ".git").exists():
            return candidate
        candidate = candidate.parent
    return pathlib.Path.cwd().resolve()


ROOT_DIR = _find_project_root()
AGENTS_DIR = ROOT_DIR / ".rules" / "agents"


# ---------------------------------------------------------------------------
# Agent resource cache and helpers
# ---------------------------------------------------------------------------

# In-memory cache of parsed agent metadata, keyed by agent name.
# Populated at startup by _build_agent_cache(), refreshed on file changes.
_agent_cache: dict[str, dict[str, object]] = {}

# Stored mtimes for change detection.  Maps agent name -> mtime_ns.
_agent_mtimes: dict[str, float] = {}

# Polling interval for background file-watcher (seconds).
_POLL_INTERVAL = 5.0


def _strip_quotes(value: str) -> str:
    """Remove surrounding double quotes from a YAML string value."""
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _parse_tools(raw: str) -> list[str]:
    """Split a comma-separated tools string into a list."""
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_agent_metadata(agent_path: pathlib.Path) -> dict[str, object]:
    """Parse an agent .md file into the resource content schema.

    Returns a dict with keys: name, description, tier, default_model,
    default_mode, tools.
    """
    content = agent_path.read_text(encoding="utf-8")
    meta, _body = parse_frontmatter(content)
    return {
        "name": agent_path.stem,
        "description": _strip_quotes(meta.get("description", "")),
        "tier": meta.get("tier", "UNKNOWN"),
        "default_model": meta.get("model") or None,
        "default_mode": meta.get("mode") or None,
        "tools": _parse_tools(meta["tools"]) if "tools" in meta else [],
    }


def _snapshot_mtimes() -> dict[str, float]:
    """Return a name -> mtime_ns snapshot for all agent files."""
    mtimes: dict[str, float] = {}
    if not AGENTS_DIR.is_dir():
        return mtimes
    for agent_path in AGENTS_DIR.glob("*.md"):
        try:
            mtimes[agent_path.stem] = agent_path.stat().st_mtime_ns
        except OSError:
            pass
    return mtimes


def _has_changes() -> bool:
    """Return True if agent files were added, removed, or modified."""
    current = _snapshot_mtimes()
    if set(current) != set(_agent_mtimes):
        return True
    return any(current[k] != _agent_mtimes[k] for k in current)


def _build_agent_cache() -> dict[str, dict[str, object]]:
    """Scan AGENTS_DIR and build the agent metadata cache."""
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
    """Register (or re-register) each agent as a concrete MCP resource.

    Resources use URI scheme ``agents://<name>`` and return JSON metadata
    when read.  On re-registration the internal ``_resources`` dict is
    replaced so that ``resources/list`` reflects the current state.
    """
    global _agent_cache, _agent_mtimes  # noqa: PLW0603
    _agent_cache = _build_agent_cache()
    _agent_mtimes = _snapshot_mtimes()

    # Replace the resource manager's concrete resources for agents.
    # Remove stale agent resources first, then add current ones.
    rm = mcp._resource_manager
    stale_keys = [k for k in rm._resources if k.startswith("agents://")]
    for k in stale_keys:
        del rm._resources[k]

    for name, metadata in _agent_cache.items():
        def _make_reader(meta: dict[str, object]):  # noqa: E301
            return lambda: json.dumps(meta, indent=2)

        resource = FunctionResource(
            uri=f"agents://{name}",
            name=name,
            description=str(metadata.get("description", "")),
            mime_type="application/json",
            fn=_make_reader(metadata),
        )
        rm.add_resource(resource)

    logger.info("Registered %d agent resources", len(_agent_cache))


def _refresh_if_changed() -> bool:
    """Check for file changes and refresh the cache if needed.

    Returns True if the cache was refreshed.
    """
    if not _has_changes():
        return False
    logger.info("Agent files changed, refreshing resource cache")
    _register_agent_resources()
    return True


async def _send_list_changed() -> None:
    """Emit a resources/list_changed notification if a session is available.

    This is best-effort: if no session is active (e.g., server just started
    and no client has connected yet), the notification is silently skipped.
    """
    try:
        ctx = mcp._mcp_server.request_context
        await ctx.session.send_resource_list_changed()
        logger.info("Sent resources/list_changed notification")
    except (LookupError, AttributeError):
        logger.debug("No active session, skipping list_changed notification")


async def _poll_agent_files() -> None:
    """Background coroutine that polls for agent file changes.

    Runs every ``_POLL_INTERVAL`` seconds.  When changes are detected,
    refreshes the cache and emits a ``list_changed`` notification.
    """
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            if _refresh_if_changed():
                await _send_list_changed()
        except Exception as exc:
            logger.warning("Agent file poll error: %s", exc)


# Populate the cache and register resources at import time.
_register_agent_resources()


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------

@mcp.tool(structured_output=False)
async def list_agents() -> str:
    """List available agents and their capabilities.

    Returns a JSON summary of all agents defined in .rules/agents/,
    including their name, tier, and description.
    """
    agents = []

    if not AGENTS_DIR.is_dir():
        logger.warning("Agents directory not found: %s", AGENTS_DIR)
        return json.dumps({"agents": [], "error": f"Agents directory not found: {AGENTS_DIR}"})

    for agent_path in sorted(AGENTS_DIR.glob("*.md")):
        try:
            content = agent_path.read_text(encoding="utf-8")
            meta, _body = parse_frontmatter(content)
            agents.append({
                "name": agent_path.stem,
                "tier": meta.get("tier", "UNKNOWN"),
                "description": _strip_quotes(meta.get("description", "")),
            })
        except Exception as exc:
            logger.warning("Failed to parse agent %s: %s", agent_path.name, exc)
            agents.append({
                "name": agent_path.stem,
                "tier": "UNKNOWN",
                "description": f"(parse error: {exc})",
            })

    return json.dumps({
        "agents": agents,
        "hint": "Use resources/read with URI 'agents://{name}' for detailed agent metadata",
    }, indent=2)


@mcp.tool(structured_output=False)
async def dispatch_agent(
    agent: str,
    task: str,
    model: str | None = None,
    mode: str | None = None,
) -> str:
    """Dispatch a sub-agent to perform a task asynchronously.

    Creates a task, spawns the sub-agent in the background, and returns
    immediately with a taskId. Use `get_task_status` to poll for results.

    Args:
        agent: Agent name from .rules/agents/ (e.g. "adr-researcher")
        task: Task description or path to a plan document
        model: Model override (optional, e.g. "gemini-3-pro-preview")
        mode: Permission mode -- "read-write" or "read-only".
              If not specified, uses agent frontmatter default, then "read-write".
    """
    # Resolve effective mode: per-dispatch > agent default > "read-write".
    effective_mode = _resolve_effective_mode(agent, mode)

    if effective_mode not in ("read-write", "read-only"):
        return json.dumps({
            "status": "failed",
            "agent": agent,
            "error": f"Invalid mode '{effective_mode}'. Must be 'read-write' or 'read-only'.",
        })

    # If task is a file path, read its contents (with workspace boundary check)
    task_content = task
    task_path = (ROOT_DIR / task).resolve()
    if task_path.is_file() and task_path.is_relative_to(ROOT_DIR):
        try:
            task_content = safe_read_text(task_path)
            logger.info("Loaded task from file: %s", task_path)
        except Exception as exc:
            logger.warning("Failed to read task file %s: %s", task_path, exc)

    # Create task in the engine (status: working).
    dispatch_task = task_engine.create_task(
        agent, model=model, mode=effective_mode,
    )
    task_id = dispatch_task.task_id

    # Register advisory lock.
    # For read-only mode, the lock covers .docs/ paths.
    # For read-write mode, lock covers the whole workspace (represented as ".").
    lock_paths: set[str] = {".docs/"} if effective_mode == "read-only" else {"."}
    _lock, lock_warnings = lock_manager.acquire_lock(
        task_id, lock_paths, effective_mode,
    )
    for warning in lock_warnings:
        logger.warning("Advisory lock: %s (taskId=%s)", warning, task_id)

    # Inject permission prompt for read-only mode.
    enforced_content = _inject_permission_prompt(task_content, effective_mode)

    logger.info(
        "Dispatching agent=%s model=%s mode=%s taskId=%s",
        agent, model, effective_mode, task_id,
    )

    # Spawn background coroutine to execute the dispatch.
    bg_task = asyncio.create_task(
        _run_dispatch_background(task_id, agent, enforced_content, model, effective_mode)
    )
    _background_tasks[task_id] = bg_task

    # Cleanup reference when the background task finishes.
    bg_task.add_done_callback(lambda _t: _background_tasks.pop(task_id, None))

    # Return immediately with taskId and status.
    return json.dumps({
        "taskId": task_id,
        "status": "working",
        "agent": agent,
        "model": model,
        "mode": effective_mode,
    }, indent=2)


async def _run_dispatch_background(
    task_id: str,
    agent: str,
    task_content: str,
    model: str | None,
    mode: str = "read-write",
) -> None:
    """Execute run_dispatch() in background and update the task engine."""
    start_time = time.monotonic()

    # Client reference for graceful cancellation.
    client_ref: list = []
    _active_clients[task_id] = client_ref

    try:
        dispatch_result: DispatchResult = await run_dispatch(
            agent_name=agent,
            initial_task=task_content,
            model_override=model,
            interactive=False,
            debug=False,
            quiet=True,
            mode=mode,
            client_ref=client_ref,
        )

        # Store session_id for potential session resume (best-effort).
        if dispatch_result.session_id:
            try:
                task_engine.set_session_id(task_id, dispatch_result.session_id)
            except Exception:
                pass  # Best-effort

        duration = time.monotonic() - start_time

        response_text = dispatch_result.response_text or ""

        # Build the structured result per ADR schema.
        # Merge file paths extracted from response text with actual file write log.
        text_artifacts = _extract_artifacts(response_text)
        all_artifacts = _merge_artifacts(text_artifacts, dispatch_result.written_files)
        result = {
            "taskId": task_id,
            "status": "completed",
            "agent": agent,
            "model_used": model or "(default)",
            "duration_seconds": round(duration, 1),
            "summary": response_text[:500],
            "response": response_text,
            "artifacts": all_artifacts,
        }

        try:
            task_engine.complete_task(task_id, result)
        except InvalidTransitionError:
            # Task was cancelled (or otherwise moved to terminal state) while
            # we were running. The cancel_task path already set the state.
            logger.info("Task %s already terminal, skipping complete", task_id)
            return
        logger.info("Task %s completed (agent=%s, %.1fs)", task_id, agent, duration)

    except asyncio.CancelledError:
        # Task was cancelled via cancel_task -- engine state already updated.
        logger.info("Task %s cancelled (agent=%s)", task_id, agent)

    except (AgentNotFoundError, DispatchError) as exc:
        duration = time.monotonic() - start_time
        try:
            task_engine.fail_task(task_id, str(exc))
        except InvalidTransitionError:
            logger.info("Task %s already terminal, skipping fail", task_id)
            return
        logger.warning(
            "Task %s failed (agent=%s, %.1fs): %s", task_id, agent, duration, exc,
        )

    except Exception as exc:
        duration = time.monotonic() - start_time
        try:
            task_engine.fail_task(task_id, f"Unexpected error: {exc}")
        except InvalidTransitionError:
            logger.info("Task %s already terminal, skipping fail", task_id)
            return
        logger.exception(
            "Task %s unexpected failure (agent=%s, %.1fs)", task_id, agent, duration,
        )

    # NOTE: Lock release is handled by TaskEngine on terminal state transitions
    # (complete_task, fail_task, cancel_task all call _release_lock).
    # No explicit lock_manager.release_lock() needed here.

    # Clean up client reference.
    _active_clients.pop(task_id, None)


@mcp.tool(structured_output=False)
async def get_task_status(task_id: str) -> str:
    """Get the current status of a dispatched task.

    Returns the task's state, metadata, and result (if completed) or
    error (if failed). Use this to poll a task after async dispatch.

    Args:
        task_id: The task identifier returned by dispatch_agent.
    """
    task = task_engine.get_task(task_id)
    if task is None:
        return json.dumps({
            "error": f"Task not found: {task_id}",
        })

    response: dict[str, object] = {
        "taskId": task.task_id,
        "status": task.status.value,
        "agent": task.agent,
        "model": task.model,
        "mode": task.mode,
    }

    if task.status_message:
        response["statusMessage"] = task.status_message

    if task.result is not None:
        response["result"] = task.result

    if task.error is not None:
        response["error"] = task.error

    # Include advisory lock info if the task holds one.
    lock = lock_manager.get_lock(task.task_id)
    if lock is not None:
        response["lock"] = {
            "paths": sorted(lock.paths),
            "mode": lock.mode,
            "acquired_at": lock.acquired_at,
        }

    return json.dumps(response, indent=2)


@mcp.tool(structured_output=False)
async def cancel_task(task_id: str) -> str:
    """Cancel a running or pending task.

    Transitions the task to 'cancelled' state and terminates the
    background sub-agent process if still running. Cannot cancel tasks
    that have already completed, failed, or been cancelled.

    Args:
        task_id: The task identifier to cancel.
    """
    try:
        task = task_engine.cancel_task(task_id)

        # Lock release is handled by TaskEngine.cancel_task() via
        # update_status() -> _release_lock(). No explicit call needed.

        # Send graceful ACP session/cancel before killing the asyncio task.
        client_ref = _active_clients.pop(task_id, None)
        if client_ref:
            client = client_ref[0] if client_ref else None
            if client and hasattr(client, "graceful_cancel"):
                try:
                    await client.graceful_cancel()
                except Exception:
                    pass  # Best-effort

        # Terminate the background asyncio task if still running.
        bg_task = _background_tasks.pop(task_id, None)
        if bg_task is not None and not bg_task.done():
            bg_task.cancel()

        logger.info("Cancelled task %s (agent=%s)", task_id, task.agent)
        return json.dumps({
            "taskId": task.task_id,
            "status": task.status.value,
            "agent": task.agent,
        })
    except TaskNotFoundError:
        return json.dumps({
            "error": f"Task not found: {task_id}",
        })
    except InvalidTransitionError as exc:
        return json.dumps({
            "error": str(exc),
            "taskId": task_id,
        })


@mcp.tool(structured_output=False)
async def get_locks() -> str:
    """List all active advisory file locks.

    Returns a JSON array of active locks showing which tasks hold locks,
    their paths, modes, and when they were acquired. Useful for diagnosing
    workspace coordination issues.
    """
    locks = lock_manager.get_locks()
    result = []
    for lock in locks:
        task = task_engine.get_task(lock.task_id)
        result.append({
            "taskId": lock.task_id,
            "agent": task.agent if task else "(unknown)",
            "paths": sorted(lock.paths),
            "mode": lock.mode,
            "acquired_at": lock.acquired_at,
        })
    return json.dumps({"locks": result, "count": len(result)}, indent=2)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the MCP dispatch server over stdio."""
    logger.info("Starting pp-dispatch MCP server (Phase 4, advisory locking)")

    # Override run_stdio_async to inject the background file-watcher.
    _original_run = mcp.run_stdio_async

    async def _run_with_polling() -> None:
        poll_task = asyncio.create_task(_poll_agent_files())
        try:
            await _original_run()
        finally:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass

    mcp.run_stdio_async = _run_with_polling  # type: ignore[assignment]
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
