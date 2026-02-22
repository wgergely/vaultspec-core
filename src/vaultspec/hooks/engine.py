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

__all__ = [
    "SUPPORTED_EVENTS",
    "Hook",
    "HookAction",
    "HookResult",
    "load_hooks",
    "trigger",
]

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
    """A single action within a hook.

    Attributes:
        action_type: Kind of action — either ``"shell"`` or ``"agent"``.
        command: Shell command string; used only when ``action_type`` is
            ``"shell"``.
        agent_name: Name of the agent to dispatch; used only when
            ``action_type`` is ``"agent"``.
        task: Task description passed to the agent; used only when
            ``action_type`` is ``"agent"``.
    """

    action_type: str  # "shell" or "agent"
    command: str = ""  # for shell actions
    agent_name: str = ""  # for agent actions
    task: str = ""  # for agent actions


@dataclass
class Hook:
    """A hook definition loaded from YAML.

    Attributes:
        name: Stem of the YAML file that defined this hook (used as identifier).
        event: Event name that triggers this hook (must be in
            :data:`SUPPORTED_EVENTS`).
        actions: Ordered list of actions to execute when the event fires.
        enabled: When ``False`` the hook is loaded but never triggered.
        source_path: Filesystem path to the YAML file this hook was loaded from.
    """

    name: str
    event: str
    actions: list[HookAction] = field(default_factory=list)
    enabled: bool = True
    source_path: Path | None = None


@dataclass
class HookResult:
    """Result of executing a single hook action.

    Attributes:
        hook_name: Name of the hook that produced this result.
        action_type: Type of the action that was executed (``"shell"`` or
            ``"agent"``).
        success: ``True`` if the action completed without error.
        output: Captured stdout (shell actions) or agent output.
        error: Captured stderr or exception message on failure.
    """

    hook_name: str
    action_type: str
    success: bool
    output: str = ""
    error: str = ""


def _parse_yaml(text: str) -> dict[str, Any]:
    """Parse YAML with fallback to basic key-value parsing.

    Args:
        text: Raw YAML text to parse.

    Returns:
        Parsed key-value mapping; empty dict if the text is empty or blank.
    """
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
    """Load all hook definitions from the hooks directory.

    Reads ``*.yaml`` and ``*.yml`` files from ``hooks_dir`` in alphabetical
    order, parses each, and returns valid :class:`Hook` objects.  Files that
    fail to parse or contain unsupported events are skipped with a warning.

    Args:
        hooks_dir: Directory to scan for hook YAML files.

    Returns:
        List of parsed and validated :class:`Hook` instances.
    """
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
    """Parse a hook definition dict into a Hook object.

    Args:
        path: Source YAML file path (used to derive the hook name and for
            warning messages).
        data: Parsed YAML dict containing ``event`` and ``actions`` keys.

    Returns:
        A populated :class:`Hook` instance, or ``None`` if the definition is
        invalid (missing event, unsupported event, etc.).
    """
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
    """Parse a single action dict into a HookAction.

    Args:
        raw: Dict with at minimum a ``type`` key; ``"shell"`` actions also
            require ``command``, ``"agent"`` actions require ``name`` and
            ``task``.

    Returns:
        A :class:`HookAction` instance, or ``None`` if the dict is missing
        required fields or has an unknown type.
    """
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

    Iterates over ``hooks``, filters to those whose ``event`` matches and
    ``enabled`` is ``True``, and executes each action in order.

    Args:
        hooks: List of loaded hooks to evaluate.
        event: Event name to match against hook definitions.
        context: Optional mapping of ``{key}`` placeholder names to
            substitution values used in command and task templates.

    Returns:
        List of :class:`HookResult` objects, one per executed action.
        Empty if no hooks matched the event.
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
    """Safely interpolate ``{key}`` placeholders in a template string.

    Args:
        template: String containing zero or more ``{key}`` placeholders.
        ctx: Mapping of placeholder names to replacement values.

    Returns:
        Template with all matching placeholders replaced by their values.
        Unrecognised placeholders are left as-is.
    """
    result = template
    for key, value in ctx.items():
        result = result.replace(f"{{{key}}}", value)
    return result


def _execute_action(
    hook_name: str,
    action: HookAction,
    ctx: dict[str, str],
) -> HookResult:
    """Execute a single hook action, dispatching to the correct handler.

    Args:
        hook_name: Name of the parent hook (used for result attribution).
        action: The action to execute.
        ctx: Template interpolation context passed through to the handler.

    Returns:
        A :class:`HookResult` describing the outcome.  Returns a failure
        result if ``action.action_type`` is unrecognised.
    """
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
    """Execute a shell command action.

    Interpolates ``{key}`` placeholders in the command string, then runs it
    via :func:`subprocess.run` with a 60-second timeout.

    Args:
        hook_name: Name of the parent hook (for result attribution).
        action: Shell action containing the command template.
        ctx: Template interpolation context.

    Returns:
        A :class:`HookResult` with ``success=True`` when the process exits
        with code 0.  Captures stdout as ``output`` and stderr as ``error``.
    """
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
    """Execute an agent dispatch action by invoking the subagent CLI.

    Interpolates ``{key}`` placeholders in the task string, resolves the
    subagent script path from the framework config, and runs it as a
    subprocess with a 300-second timeout.

    Args:
        hook_name: Name of the parent hook (for result attribution).
        action: Agent action containing ``agent_name`` and ``task`` template.
        ctx: Template interpolation context.

    Returns:
        A :class:`HookResult` with ``success=True`` when the subprocess exits
        with code 0.
    """
    task_text = _interpolate(action.task, ctx)
    try:
        from ..config import get_config

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
