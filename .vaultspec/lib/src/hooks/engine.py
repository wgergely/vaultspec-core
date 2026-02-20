"""Hook engine: load, validate, and execute hooks.

Hooks are YAML files in ``.vaultspec/hooks/`` with the structure::

    event: vault.document.created
    actions:
      - type: shell
        command: "echo 'New document: {path}'"
      - type: agent
        name: vaultspec-docs-curator
        task: "Review new document at {path}"

Supported events:
    vault.document.created   — after vault.py create
    vault.document.modified  — after vault doc edits
    vault.index.updated      — after vault.py index
    config.synced            — after cli.py sync-all
    audit.completed          — after vault.py audit
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

SUPPORTED_EVENTS = frozenset(
    {
        "vault.document.created",
        "vault.document.modified",
        "vault.index.updated",
        "config.synced",
        "audit.completed",
    }
)


@dataclass
class HookAction:
    """A single action within a hook."""

    action_type: str  # "shell" or "agent"
    command: str = ""  # for shell actions
    agent_name: str = ""  # for agent actions
    task: str = ""  # for agent actions


@dataclass
class Hook:
    """A hook definition loaded from YAML."""

    name: str
    event: str
    actions: list[HookAction] = field(default_factory=list)
    enabled: bool = True
    source_path: Path | None = None


@dataclass
class HookResult:
    """Result of executing a single hook action."""

    hook_name: str
    action_type: str
    success: bool
    output: str = ""
    error: str = ""


def _parse_yaml(text: str) -> dict[str, Any]:
    """Parse YAML with fallback to basic key-value parsing."""
    try:
        import yaml

        return yaml.safe_load(text) or {}
    except ImportError:
        # Minimal fallback for simple YAML
        result: dict[str, Any] = {}
        for line in text.splitlines():
            line = line.strip()
            if ":" in line and not line.startswith("#"):
                key, _, val = line.partition(":")
                result[key.strip()] = val.strip()
        return result


def load_hooks(hooks_dir: Path) -> list[Hook]:
    """Load all hook definitions from the hooks directory."""
    hooks: list[Hook] = []

    if not hooks_dir.exists():
        return hooks

    for path in sorted(hooks_dir.glob("*.yaml")):
        try:
            data = _parse_yaml(path.read_text(encoding="utf-8"))
            hook = _parse_hook(path, data)
            if hook is not None:
                hooks.append(hook)
        except Exception:
            logger.warning("Failed to parse hook: %s", path.name, exc_info=True)

    for path in sorted(hooks_dir.glob("*.yml")):
        try:
            data = _parse_yaml(path.read_text(encoding="utf-8"))
            hook = _parse_hook(path, data)
            if hook is not None:
                hooks.append(hook)
        except Exception:
            logger.warning("Failed to parse hook: %s", path.name, exc_info=True)

    return hooks


def _parse_hook(path: Path, data: dict[str, Any]) -> Hook | None:
    """Parse a hook definition dict into a Hook object."""
    event = data.get("event", "")
    if not event:
        logger.warning("Hook %s missing 'event' field", path.name)
        return None

    if event not in SUPPORTED_EVENTS:
        logger.warning("Hook %s has unsupported event: %s", path.name, event)
        return None

    actions: list[HookAction] = []
    raw_actions = data.get("actions", [])
    if isinstance(raw_actions, list):
        for raw in raw_actions:
            if isinstance(raw, dict):
                action = _parse_action(raw)
                if action is not None:
                    actions.append(action)

    return Hook(
        name=path.stem,
        event=event,
        actions=actions,
        enabled=data.get("enabled", True),
        source_path=path,
    )


def _parse_action(raw: dict[str, Any]) -> HookAction | None:
    """Parse a single action dict."""
    action_type = raw.get("type", "")
    if action_type == "shell":
        cmd = raw.get("command", "")
        if not cmd:
            return None
        return HookAction(action_type="shell", command=cmd)
    elif action_type == "agent":
        name = raw.get("name", "")
        task = raw.get("task", "")
        if not name or not task:
            return None
        return HookAction(
            action_type="agent",
            agent_name=name,
            task=task,
        )
    return None


def trigger(
    hooks: list[Hook],
    event: str,
    context: dict[str, str] | None = None,
) -> list[HookResult]:
    """Trigger all hooks matching the given event.

    The *context* dict provides template variables for
    string interpolation in commands and tasks.
    """
    ctx = context or {}
    results: list[HookResult] = []

    matching = [h for h in hooks if h.event == event and h.enabled]
    if not matching:
        return results

    for hook in matching:
        for action in hook.actions:
            result = _execute_action(hook.name, action, ctx)
            results.append(result)

    return results


def _interpolate(template: str, ctx: dict[str, str]) -> str:
    """Safely interpolate {key} placeholders."""
    result = template
    for key, value in ctx.items():
        result = result.replace(f"{{{key}}}", value)
    return result


def _execute_action(
    hook_name: str,
    action: HookAction,
    ctx: dict[str, str],
) -> HookResult:
    """Execute a single hook action."""
    if action.action_type == "shell":
        return _execute_shell(hook_name, action, ctx)
    elif action.action_type == "agent":
        return _execute_agent(hook_name, action, ctx)
    return HookResult(
        hook_name=hook_name,
        action_type=action.action_type,
        success=False,
        error=f"Unknown action type: {action.action_type}",
    )


def _execute_shell(
    hook_name: str,
    action: HookAction,
    ctx: dict[str, str],
) -> HookResult:
    """Execute a shell command."""
    cmd = _interpolate(action.command, ctx)
    try:
        result = subprocess.run(
            shlex.split(cmd),
            shell=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return HookResult(
            hook_name=hook_name,
            action_type="shell",
            success=result.returncode == 0,
            output=result.stdout.strip(),
            error=result.stderr.strip(),
        )
    except subprocess.TimeoutExpired:
        return HookResult(
            hook_name=hook_name,
            action_type="shell",
            success=False,
            error="Hook timed out (60s)",
        )
    except Exception as e:
        return HookResult(
            hook_name=hook_name,
            action_type="shell",
            success=False,
            error=str(e),
        )


def _execute_agent(
    hook_name: str,
    action: HookAction,
    ctx: dict[str, str],
) -> HookResult:
    """Execute an agent dispatch (delegates to subagent CLI)."""
    task_text = _interpolate(action.task, ctx)
    try:
        from core.config import get_config

        fw = Path(get_config().framework_dir)
        subagent_script = fw / "lib" / "scripts" / "subagent.py"

        result = subprocess.run(
            [
                sys.executable,
                str(subagent_script),
                "run",
                "--agent",
                action.agent_name,
                "--task",
                task_text,
            ],
            capture_output=True,
            text=True,
            timeout=300,
        )
        return HookResult(
            hook_name=hook_name,
            action_type="agent",
            success=result.returncode == 0,
            output=result.stdout.strip(),
            error=result.stderr.strip(),
        )
    except subprocess.TimeoutExpired:
        return HookResult(
            hook_name=hook_name,
            action_type="agent",
            success=False,
            error="Agent dispatch timed out (300s)",
        )
    except Exception as e:
        return HookResult(
            hook_name=hook_name,
            action_type="agent",
            success=False,
            error=str(e),
        )
