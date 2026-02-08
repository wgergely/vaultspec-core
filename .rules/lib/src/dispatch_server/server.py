from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import re
import sys
import time

from mcp.server.fastmcp import FastMCP
from mcp.server.fastmcp.resources.types import FunctionResource

from orchestration.dispatch import (
    AgentNotFoundError,
    DispatchError,
    DispatchResult,
    run_dispatch,
)
from orchestration.task_engine import (
    InvalidTransitionError,
    LockManager,
    TaskEngine,
    TaskNotFoundError,
)
from orchestration.utils import find_project_root, parse_frontmatter, safe_read_text

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

ROOT_DIR = find_project_root()
AGENTS_DIR = ROOT_DIR / ".rules" / "agents"

# Advisory lock manager for workspace coordination (Phase 4).
lock_manager = LockManager()

# Internal task engine (Layer 2) for tracking dispatch task lifecycle.
task_engine = TaskEngine(ttl_seconds=3600.0, lock_manager=lock_manager)

# Maps task_id -> asyncio.Task for background dispatch coroutines.
_background_tasks: dict[str, asyncio.Task[None]] = {}

# Maps task_id -> Client for graceful ACP cancellation.
_active_clients: dict[str, list] = {}


# ---------------------------------------------------------------------------
# Permission enforcement helpers
# ---------------------------------------------------------------------------

_READONLY_PERMISSION_PROMPT = (
    "PERMISSION MODE: READ-ONLY\n"
    "You MUST only write files within the `.docs/` directory. "
    "Do not modify any source code files.\n\n"
)


def _resolve_effective_mode(agent: str, mode: str | None) -> str:
    """Resolve the effective permission mode for a dispatch."""
    if mode is not None:
        return mode
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

_ARTIFACT_PATTERN = re.compile(
    r"""(?:^|[\s"'`(])"""  # word boundary or quote/backtick
    r"""("""
    r"""\.docs/[\w./-]+"""  # .docs/ paths
    r"""|\.rules/[\w./-]+"""  # .rules/ paths
    r"""|src/[\w./-]+"""  # src/ paths
    r"""|crates/[\w./-]+"""  # crates/ paths
    r"""|tests?/[\w./-]+"""  # test(s)/ paths
    r"""|[\w./-]+\.(?:md|rs|toml|py)"""  # files with known extensions
    r""")"""
    r"""(?=[\s"'`),;:]|$)""",  # word boundary or quote/backtick
    re.MULTILINE,
)


def _extract_artifacts(text: str) -> list[str]:
    """Extract unique file path references from agent response text."""
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
    """Merge regex-extracted artifacts with the file write log."""
    seen: set[str] = set()
    merged: list[str] = []
    for path in (*written_files, *text_artifacts):
        normalized = path.replace("\\", "/")
        if normalized not in seen:
            seen.add(normalized)
            merged.append(normalized)
    return sorted(merged)


# ---------------------------------------------------------------------------
# Agent resource cache and helpers
# ---------------------------------------------------------------------------

_agent_cache: dict[str, dict[str, object]] = {}
_agent_mtimes: dict[str, float] = {}
_POLL_INTERVAL = 5.0


def _strip_quotes(value: str) -> str:
    if len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        return value[1:-1]
    return value


def _parse_tools(raw: str) -> list[str]:
    return [t.strip() for t in raw.split(",") if t.strip()]


def _parse_agent_metadata(agent_path: pathlib.Path) -> dict[str, object]:
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
    current = _snapshot_mtimes()
    if set(current) != set(_agent_mtimes):
        return True
    return any(current[k] != _agent_mtimes[k] for k in current)


def _build_agent_cache() -> dict[str, dict[str, object]]:
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
    global _agent_cache, _agent_mtimes  # noqa: PLW0603
    _agent_cache = _build_agent_cache()
    _agent_mtimes = _snapshot_mtimes()

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
    if not _has_changes():
        return False
    logger.info("Agent files changed, refreshing resource cache")
    _register_agent_resources()
    return True


async def _send_list_changed() -> None:
    try:
        ctx = mcp._mcp_server.request_context
        await ctx.session.send_resource_list_changed()
        logger.info("Sent resources/list_changed notification")
    except (LookupError, AttributeError):
        logger.debug("No active session, skipping list_changed notification")


async def _poll_agent_files() -> None:
    while True:
        await asyncio.sleep(_POLL_INTERVAL)
        try:
            if _refresh_if_changed():
                await _send_list_changed()
        except Exception as exc:
            logger.warning("Agent file poll error: %s", exc)


_register_agent_resources()


# ---------------------------------------------------------------------------
# MCP Tools
# ---------------------------------------------------------------------------


@mcp.tool(structured_output=False)
async def list_agents() -> str:
    """List available agents and their capabilities."""
    agents = []

    if not AGENTS_DIR.is_dir():
        return json.dumps(
            {"agents": [], "error": f"Agents directory not found: {AGENTS_DIR}"}
        )

    for agent_path in sorted(AGENTS_DIR.glob("*.md")):
        try:
            content = agent_path.read_text(encoding="utf-8")
            meta, _body = parse_frontmatter(content)
            agents.append(
                {
                    "name": agent_path.stem,
                    "tier": meta.get("tier", "UNKNOWN"),
                    "description": _strip_quotes(meta.get("description", "")),
                }
            )
        except Exception as exc:
            logger.warning("Failed to parse agent %s: %s", agent_path.name, exc)
            agents.append(
                {
                    "name": agent_path.stem,
                    "tier": "UNKNOWN",
                    "description": f"(parse error: {exc})",
                }
            )

    return json.dumps(
        {
            "agents": agents,
            "hint": "Use resources/read with URI 'agents://{name}' for detailed agent metadata",
        },
        indent=2,
    )


@mcp.tool(structured_output=False)
async def dispatch_agent(
    agent: str,
    task: str,
    model: str | None = None,
    mode: str | None = None,
) -> str:
    """Dispatch a sub-agent to perform a task asynchronously."""
    effective_mode = _resolve_effective_mode(agent, mode)

    if effective_mode not in ("read-write", "read-only"):
        return json.dumps(
            {
                "status": "failed",
                "agent": agent,
                "error": f"Invalid mode '{effective_mode}'. Must be 'read-write' or 'read-only'.",
            }
        )

    task_content = task
    task_path = (ROOT_DIR / task).resolve()
    if task_path.is_file() and task_path.is_relative_to(ROOT_DIR):
        try:
            task_content = safe_read_text(task_path, ROOT_DIR)
            logger.info("Loaded task from file: %s", task_path)
        except Exception as exc:
            logger.warning("Failed to read task file %s: %s", task_path, exc)

    dispatch_task = task_engine.create_task(
        agent,
        model=model,
        mode=effective_mode,
    )
    task_id = dispatch_task.task_id

    lock_paths: set[str] = {".docs/"} if effective_mode == "read-only" else {"."}
    _lock, lock_warnings = lock_manager.acquire_lock(
        task_id,
        lock_paths,
        effective_mode,
    )
    for warning in lock_warnings:
        logger.warning("Advisory lock: %s (taskId=%s)", warning, task_id)

    enforced_content = _inject_permission_prompt(task_content, effective_mode)

    logger.info(
        "Dispatching agent=%s model=%s mode=%s taskId=%s",
        agent,
        model,
        effective_mode,
        task_id,
    )

    bg_task = asyncio.create_task(
        _run_dispatch_background(
            task_id, agent, enforced_content, model, effective_mode
        )
    )
    _background_tasks[task_id] = bg_task
    bg_task.add_done_callback(lambda _t: _background_tasks.pop(task_id, None))

    return json.dumps(
        {
            "taskId": task_id,
            "status": "working",
            "agent": agent,
            "model": model,
            "mode": effective_mode,
        },
        indent=2,
    )


async def _run_dispatch_background(
    task_id: str,
    agent: str,
    task_content: str,
    model: str | None,
    mode: str = "read-write",
) -> None:
    """Execute run_dispatch() in background and update the task engine."""
    start_time = time.monotonic()
    client_ref: list = []
    _active_clients[task_id] = client_ref

    try:
        dispatch_result: DispatchResult = await run_dispatch(
            agent_name=agent,
            initial_task=task_content,
            root_dir=ROOT_DIR,
            model_override=model,
            interactive=False,
            debug=False,
            quiet=True,
            mode=mode,
            client_ref=client_ref,
        )

        if dispatch_result.session_id:
            try:
                task_engine.set_session_id(task_id, dispatch_result.session_id)
            except Exception:
                pass

        duration = time.monotonic() - start_time
        response_text = dispatch_result.response_text or ""
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
            logger.info("Task %s already terminal, skipping complete", task_id)
            return
        logger.info("Task %s completed (agent=%s, %.1fs)", task_id, agent, duration)

    except asyncio.CancelledError:
        logger.info("Task %s cancelled (agent=%s)", task_id, agent)

    except (AgentNotFoundError, DispatchError) as exc:
        duration = time.monotonic() - start_time
        try:
            task_engine.fail_task(task_id, str(exc))
        except InvalidTransitionError:
            logger.info("Task %s already terminal, skipping fail", task_id)
            return
        logger.warning(
            "Task %s failed (agent=%s, %.1fs): %s",
            task_id,
            agent,
            duration,
            exc,
        )

    except Exception as exc:
        duration = time.monotonic() - start_time
        try:
            task_engine.fail_task(task_id, f"Unexpected error: {exc}")
        except InvalidTransitionError:
            logger.info("Task %s already terminal, skipping fail", task_id)
            return
        logger.exception(
            "Task %s unexpected failure (agent=%s, %.1fs)",
            task_id,
            agent,
            duration,
        )

    _active_clients.pop(task_id, None)


@mcp.tool(structured_output=False)
async def get_task_status(task_id: str) -> str:
    """Get the current status of a dispatched task."""
    task = task_engine.get_task(task_id)
    if task is None:
        return json.dumps(
            {
                "error": f"Task not found: {task_id}",
            }
        )

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
    """Cancel a running or pending task."""
    try:
        task = task_engine.cancel_task(task_id)

        client_ref = _active_clients.pop(task_id, None)
        if client_ref:
            client = client_ref[0] if client_ref else None
            if client and hasattr(client, "graceful_cancel"):
                try:
                    await client.graceful_cancel()
                except Exception:
                    pass

        bg_task = _background_tasks.pop(task_id, None)
        if bg_task is not None and not bg_task.done():
            bg_task.cancel()

        logger.info("Cancelled task %s (agent=%s)", task_id, task.agent)
        return json.dumps(
            {
                "taskId": task.task_id,
                "status": task.status.value,
                "agent": task.agent,
            }
        )
    except TaskNotFoundError:
        return json.dumps(
            {
                "error": f"Task not found: {task_id}",
            }
        )
    except InvalidTransitionError as exc:
        return json.dumps(
            {
                "error": str(exc),
                "taskId": task_id,
            }
        )


@mcp.tool(structured_output=False)
async def get_locks() -> str:
    """List all active advisory file locks."""
    locks = lock_manager.get_locks()
    result = []
    for lock in locks:
        task = task_engine.get_task(lock.task_id)
        result.append(
            {
                "taskId": lock.task_id,
                "agent": task.agent if task else "(unknown)",
                "paths": sorted(lock.paths),
                "mode": lock.mode,
                "acquired_at": lock.acquired_at,
            }
        )
    return json.dumps({"locks": result, "count": len(result)}, indent=2)


def main() -> None:
    logger.info("Starting pp-dispatch MCP server (Library Version)")

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
