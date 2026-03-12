"""Load, validate, and execute declarative vaultspec hooks.

This module is the runtime for hook definitions stored as YAML files under
``.vaultspec/hooks/``. It parses hook documents into typed models, filters them
by supported event, and executes their actions while guarding against
re-entrant event loops.

Usage centers on ``load_hooks()`` to read hook definitions and ``trigger()`` or
``fire_hooks()`` to execute the hooks bound to a specific event.
"""

from __future__ import annotations

import logging
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from ..core.helpers import kill_process_tree

if TYPE_CHECKING:
    from pathlib import Path

logger = logging.getLogger(__name__)

__all__ = [
    "SUPPORTED_EVENTS",
    "Hook",
    "HookAction",
    "HookResult",
    "fire_hooks",
    "load_hooks",
    "trigger",
]

SUPPORTED_EVENTS = frozenset(
    {
        "vault.document.created",
        "config.synced",
        "audit.completed",
    }
)


@dataclass
class HookAction:
    """A single action within a hook.

    Attributes:
        action_type: Kind of action — currently only ``"shell"`` is supported.
        command: Shell command string; used only when ``action_type`` is
            ``"shell"``.
    """

    action_type: str  # "shell"
    command: str = ""  # for shell actions


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
        action_type: Type of the action that was executed (``"shell"``).
        success: ``True`` if the action completed without error.
        output: Captured stdout (shell actions).
        error: Captured stderr or exception message on failure.
    """

    hook_name: str
    action_type: str
    success: bool
    output: str = ""
    error: str = ""


def _parse_yaml(text: str) -> dict[str, Any]:
    """Parse YAML text into a dict.

    Args:
        text: Raw YAML text to parse.

    Returns:
        Parsed mapping; empty dict if the text is empty or blank.
    """
    import yaml

    return yaml.safe_load(text) or {}


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

    seen: dict[str, Path] = {}
    for ext in ("*.yaml", "*.yml"):
        for path in sorted(hooks_dir.glob(ext)):
            if path.stem in seen:
                logger.warning(
                    "Duplicate hook '%s': using %s, ignoring %s",
                    path.stem,
                    seen[path.stem].name,
                    path.name,
                )
                continue
            seen[path.stem] = path

    for path in seen.values():
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
            require ``command``.

    Returns:
        A :class:`HookAction` instance, or ``None`` if the dict is missing
        required fields or has an unknown type.
    """
    action_type = raw.get("type", "")
    if action_type == "shell":
        cmd = raw.get("command", "")
        if not cmd:
            logger.warning(
                "Skipping action: shell action missing 'command' field (raw=%r)", raw
            )
            return None
        return HookAction(action_type="shell", command=cmd)

    logger.warning("Skipping action: unknown action type %r (raw=%r)", action_type, raw)
    return None


_triggering: set[str] = set()


def trigger(
    hooks: list[Hook],
    event: str,
    context: dict[str, str] | None = None,
) -> list[HookResult]:
    """Trigger all hooks matching the given event.

    Iterates over ``hooks``, filters to those whose ``event`` matches and
    ``enabled`` is ``True``, and executes each action in order.  Guards
    against re-entrant triggers for the same event.

    Args:
        hooks: List of loaded hooks to evaluate.
        event: Event name to match against hook definitions.
        context: Optional mapping of ``{key}`` placeholder names to
            substitution values used in command and task templates.

    Returns:
        List of :class:`HookResult` objects, one per executed action.
        Empty if no hooks matched the event.
    """
    if event in _triggering:
        logger.warning("Re-entrant hook trigger blocked: %s", event)
        return []

    ctx = context or {}
    results: list[HookResult] = []

    matching = [h for h in hooks if h.event == event and h.enabled]
    if not matching:
        return results

    _triggering.add(event)
    try:
        logger.info("Triggering %d hook(s) for event '%s'", len(matching), event)
        for hook in matching:
            for action in hook.actions:
                result = _execute_action(hook.name, action, ctx)
                results.append(result)
    finally:
        _triggering.discard(event)

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
    from ..core import types as _t

    env = os.environ.copy()
    if _t.TARGET_DIR:
        env["VAULTSPEC_TARGET_DIR"] = str(_t.TARGET_DIR)
        cwd = str(_t.TARGET_DIR)
    else:
        cwd = None

    try:
        cmd_args = shlex.split(cmd, posix=(os.name != "nt"))
        process = subprocess.Popen(
            cmd_args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            cwd=cwd,
        )
        try:
            stdout, stderr = process.communicate(timeout=60)
        except subprocess.TimeoutExpired:
            kill_process_tree(process.pid)
            process.kill()
            process.communicate()
            logger.warning("Shell hook '%s' timed out (60s)", hook_name)
            return HookResult(
                hook_name=hook_name,
                action_type="shell",
                success=False,
                error="Hook timed out (60s)",
            )
        return HookResult(
            hook_name=hook_name,
            action_type="shell",
            success=process.returncode == 0,
            output=stdout.strip(),
            error=stderr.strip(),
        )
    except Exception as e:
        logger.error("Shell hook '%s' failed: %s", hook_name, e, exc_info=True)
        return HookResult(
            hook_name=hook_name,
            action_type="shell",
            success=False,
            error=str(e),
        )


def fire_hooks(event: str, context: dict[str, str] | None = None) -> None:
    """Fire hooks for a lifecycle event, silently catching all errors.

    Args:
        event: Event name to trigger.
        context: Optional context dict passed through to hook actions.
    """
    try:
        from ..core import types as _t

        hooks = load_hooks(_t.HOOKS_DIR)
        trigger(hooks, event, context)
    except Exception:
        logger.debug("Hook trigger failed for %s", event, exc_info=True)
