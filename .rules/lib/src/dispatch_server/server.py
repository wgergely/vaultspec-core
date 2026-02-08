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
from pydantic import AnyUrl

from orchestration.dispatch import (
    DispatchError,
    run_dispatch,
)
from orchestration.task_engine import (
    LockManager,
    TaskEngine,
)
from orchestration.utils import (
    find_project_root,
    parse_frontmatter,
    safe_read_text,
)

# Configure logging to stderr
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
    global _agent_cache, _agent_mtimes
    _agent_cache = _build_agent_cache()
    _agent_mtimes = _snapshot_mtimes()

    rm = mcp._resource_manager
    stale_keys = [k for k in rm._resources if k.startswith("agents://")]
    for k in stale_keys:
        del rm._resources[k]

    for name, metadata in _agent_cache.items():

        def _make_reader(meta: dict[str, object]):
            return lambda: json.dumps(meta, indent=2)

        resource = FunctionResource(
            uri=AnyUrl(f"agents://{name}"),
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
        if _refresh_if_changed():
            await _send_list_changed()


# ---------------------------------------------------------------------------
# MCP Tool implementations
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_agents() -> str:
    """Return a list of all available sub-agents and their tiers."""
    _refresh_if_changed()
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


@mcp.tool()
async def dispatch_agent(
    agent: str,
    task: str,
    model: str | None = None,
    mode: str | None = None,
) -> str:
    """
    Run a sub-agent asynchronously to perform a task.
    Returns immediately with a taskId.
    """
    _refresh_if_changed()

    if agent not in _agent_cache:
        return json.dumps({"status": "failed", "error": f"Agent '{agent}' not found."})

    effective_mode = _resolve_effective_mode(agent, mode)
    if effective_mode not in ("read-write", "read-only"):
        return json.dumps(
            {
                "status": "failed",
                "agent": agent,
                "error": f"Invalid mode '{effective_mode}'. Use 'read-write'.",
            }
        )

    # Pre-acquire advisory lock for .docs/ if read-only
    try:
        task_obj = task_engine.create_task(agent, model=model, mode=effective_mode)
    except ValueError as e:
        return json.dumps({"status": "failed", "error": str(e)})

    task_id = task_obj.task_id

    # Background execution
    async def _run_in_background():
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
                except Exception:
                    pass

            full_task = _inject_permission_prompt(task_content, effective_mode)

            result = await run_dispatch(
                agent_name=agent,
                initial_task=full_task,
                root_dir=ROOT_DIR,
                model_override=model,
                interactive=False,
                debug=False,
                quiet=True,
                mode=effective_mode,
                client_ref=client_ref,
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
        except DispatchError as e:
            task_engine.fail_task(task_id, str(e))
        except Exception as e:
            logger.exception("Unexpected error in background dispatch")
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


@mcp.tool()
async def get_task_status(task_id: str) -> str:
    """Check the status and result of a previously dispatched task."""
    task = task_engine.get_task(task_id)
    if not task:
        return json.dumps({"error": f"Task '{task_id}' not found or expired."})

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
        res["error"] = task.error

    # Add active lock info if working
    lock = lock_manager.get_lock(task_id)
    if lock:
        res["lock"] = {
            "paths": list(lock.paths),
            "mode": lock.mode,
            "acquired_at": lock.acquired_at,
        }

    return json.dumps(res, indent=2)


@mcp.tool()
async def cancel_task(task_id: str) -> str:
    """Cancel a running task and its agent session."""
    task = task_engine.get_task(task_id)
    if not task:
        return json.dumps({"error": f"Task '{task_id}' not found."})

    if task.completed_at:
        return json.dumps({"error": "Task already completed."})

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


@mcp.tool()
async def get_locks() -> str:
    """List all active advisory file locks across the workspace."""
    locks = lock_manager.get_locks()
    res = []
    for lock in locks:
        res.append(
            {
                "taskId": lock.task_id,
                "agent": task_engine.get_task(lock.task_id).agent
                if task_engine.get_task(lock.task_id)
                else "unknown",
                "paths": list(lock.paths),
                "mode": lock.mode,
                "acquired_at": lock.acquired_at,
            }
        )
    return json.dumps({"locks": res, "count": len(res)}, indent=2)


def main():
    """Start the MCP server."""
    _register_agent_resources()
    asyncio.create_task(_poll_agent_files())
    mcp.run()


if __name__ == "__main__":
    main()
