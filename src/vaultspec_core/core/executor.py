"""Execute resolution plan steps against a workspace.

Maps each :class:`ResolutionAction` to a concrete handler that performs
the repair, scaffold, or adoption on the real filesystem. Only
preflight-safe actions are executed during pre-command diagnosis;
SYNC, PRUNE, and REMOVE are left for the main command to handle.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from .diagnosis.signals import ResolutionAction
from .enums import DirName, ManagedState, Tool
from .gitignore import ensure_gitignore_block, get_recommended_entries
from .manifest import (
    ManifestData,
    add_providers,
    read_manifest_data,
    write_manifest_data,
)

if TYPE_CHECKING:
    from .resolver import ResolutionPlan, ResolutionStep

logger = logging.getLogger(__name__)

PREFLIGHT_ACTIONS: frozenset[ResolutionAction] = frozenset(
    {
        ResolutionAction.REPAIR_MANIFEST,
        ResolutionAction.REPAIR_GITIGNORE,
        ResolutionAction.ADOPT_DIRECTORY,
        ResolutionAction.SCAFFOLD,
    }
)


@dataclass
class StepResult:
    """Outcome of executing a single :class:`ResolutionStep`.

    Attributes:
        step: The resolution step that was executed.
        success: Whether the step completed without error.
        error: Error message if the step failed, ``None`` otherwise.
    """

    step: ResolutionStep
    success: bool
    error: str | None = None


@dataclass
class ExecutionResult:
    """Accumulated results from executing a :class:`ResolutionPlan`.

    Attributes:
        results: Per-step outcomes in execution order.
    """

    results: list[StepResult] = field(default_factory=list)

    @property
    def all_succeeded(self) -> bool:
        """Return ``True`` when every executed step succeeded."""
        return all(r.success for r in self.results)

    @property
    def failed(self) -> list[StepResult]:
        """Return the subset of results that failed."""
        return [r for r in self.results if not r.success]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def execute_plan(
    plan: ResolutionPlan,
    target: Path,
    *,
    dry_run: bool = False,
    preflight_only: bool = True,
) -> ExecutionResult:
    """Execute the steps in *plan* against the workspace at *target*.

    When *preflight_only* is ``True`` (the default), only steps whose action
    is in :data:`PREFLIGHT_ACTIONS` are executed. The remaining steps are
    informational and left for the main command to handle.

    Args:
        plan: Resolution plan produced by
            :func:`~vaultspec_core.core.resolver.resolve`.
        target: Workspace root directory.
        dry_run: When ``True``, records every step as succeeded without
            performing any filesystem changes.
        preflight_only: When ``True``, filters to preflight-safe actions.

    Returns:
        An :class:`ExecutionResult` with per-step outcomes.
    """
    result = ExecutionResult()
    steps = plan.steps
    if preflight_only:
        steps = [s for s in steps if s.action in PREFLIGHT_ACTIONS]

    if not steps:
        return result

    _bootstrapped = False

    for step in steps:
        if dry_run:
            result.results.append(StepResult(step=step, success=True))
            continue

        # Lazy bootstrap: ensure tool configs are available before the first
        # SCAFFOLD or ADOPT_DIRECTORY step that needs them.
        if not _bootstrapped and step.action in (
            ResolutionAction.SCAFFOLD,
            ResolutionAction.ADOPT_DIRECTORY,
        ):
            try:
                from .commands import _ensure_tool_configs

                _ensure_tool_configs(target)
            except Exception:
                logger.debug("Tool config bootstrap failed", exc_info=True)
            _bootstrapped = True

        try:
            _dispatch(target, step)
            result.results.append(StepResult(step=step, success=True))
        except Exception as exc:
            logger.debug("Step %s failed: %s", step.action, exc, exc_info=True)
            result.results.append(StepResult(step=step, success=False, error=str(exc)))

    return result


# ---------------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------------

_HANDLERS: dict[ResolutionAction, str] = {
    ResolutionAction.REPAIR_MANIFEST: "_execute_repair_manifest",
    ResolutionAction.REPAIR_GITIGNORE: "_execute_repair_gitignore",
    ResolutionAction.SCAFFOLD: "_execute_scaffold",
    ResolutionAction.ADOPT_DIRECTORY: "_execute_adopt_directory",
}


def _dispatch(target: Path, step: ResolutionStep) -> None:
    handler_name = _HANDLERS.get(step.action)
    if handler_name is None:
        raise ValueError(f"No handler for action {step.action!r}")
    handler = globals()[handler_name]
    handler(target, step)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _execute_repair_manifest(target: Path, _step: ResolutionStep) -> None:
    """Rebuild the manifest by scanning for provider directories on disk."""
    # Read existing data (may be corrupt - fall back to defaults)
    try:
        data = read_manifest_data(target)
    except Exception:
        data = ManifestData()

    _tool_dir_map: dict[Tool, str] = {
        Tool.CLAUDE: DirName.CLAUDE.value,
        Tool.GEMINI: DirName.GEMINI.value,
        Tool.ANTIGRAVITY: DirName.ANTIGRAVITY.value,
        Tool.CODEX: DirName.CODEX.value,
    }

    detected: set[str] = set()
    for tool, dir_name in _tool_dir_map.items():
        if (target / dir_name).is_dir():
            detected.add(tool.value)

    data.installed = detected
    write_manifest_data(target, data)


def _execute_scaffold(target: Path, step: ResolutionStep) -> None:
    """Scaffold directories for a single provider."""
    from .commands import _ensure_tool_configs, _scaffold_provider

    _ensure_tool_configs(target)

    try:
        tool = Tool(step.target)
    except ValueError as exc:
        raise ValueError(f"Unknown provider {step.target!r} for scaffold") from exc

    _scaffold_provider(target, tool)


def _execute_adopt_directory(target: Path, step: ResolutionStep) -> None:
    """Register an untracked provider directory in the manifest."""
    add_providers(target, [step.target])


def _execute_repair_gitignore(target: Path, _step: ResolutionStep) -> None:
    """Repair the managed gitignore block."""
    entries = get_recommended_entries(target)
    ensure_gitignore_block(target, entries, state=ManagedState.PRESENT)
